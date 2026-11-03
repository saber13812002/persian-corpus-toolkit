# -*- coding: utf-8 -*-
"""tasnim.transform — تبدیل رکوردهای منبع به پیکره‌ی رسمی (PCM-20.3 §2-3).

نکته‌ی پیوستگی: ترتیب نهایی صفحات درون هر جلد (item_index, dup_rank,
position منبع) است؛ برای item_indexهای تکراری «ردیف اول در منبع» canonical
می‌ماند و بقیه __d1/__d2... می‌گیرند — هیچ ردیفی حذف نمی‌شود.

جریان:
  source (reconcile.load_source) → reconcile.gate_report + flags هر رکورد
  → گروه‌بندی جلد (زنجیره‌ی استراتژی) → شناسه‌های قطعی
  → corpus.json (هدر/جلد/آمار) + pages.jsonl (همه‌ی رکوردها، بدون هیچ حذفی)

قطعی بودن: ترتیب صفحات تابعی از (volume order, item_index, dup_rank,
position منبع) است و هیچ field وابسته به زمان ندارد (created_at فقط در
manifest — بیرون از content).
"""
from __future__ import annotations

import os

from . import common as C
from . import normalize as N
from . import reconcile as R
from . import schema as S


def _span(nums):
    nums = [n for n in nums if n is not None]
    if not nums:
        return None
    return (min(nums), max(nums))


def _volume_sort_key(vol: dict):
    """جلدهای شماره‌دار اول (صعودی)، بعد «نامشخص»."""
    return (1, vol["volume_id"]) if vol["volume_no"] is None else (0, vol["volume_no"], vol["volume_id"])


def build_corpus(source: dict, policy_id: str = N.POLICY_DEFAULT,
                 work_name: str = None, work_description: str = None) -> dict:
    """ساخت پیکره از Source Snapshot.

    برگشت: {"corpus": <meta dict>, "pages": [<page record>... مرتب‌شده]}
    """
    N.policy_spec(policy_id)  # اعتبار policy
    pages = source["pages"]
    gate = R.gate_report(source)

    # ---- ردیف‌های درون‌حافظه‌ای (فلات، برای گروه‌بندی) -------------------------
    dup_set = set()
    for poslist in gate["duplicate_item_index"]["values"].values():
        dup_set.update(poslist)

    rows = []
    for p in pages:
        t = R.text_of(p)
        raw_barg = R.raw_barg_of(p)
        barg = C.parse_barg_all_runs(raw_barg)
        idx = p.get("item_index")
        flags = R.quality_flags(p, barg, dup_index=(p["_position"] in dup_set))
        rows.append({
            "page": p,
            "text": t,
            "text_norm": N.normalize_text(t, policy_id),
            "barg": barg,
            "raw_barg": raw_barg,
            "item_index": idx,
            "flags": flags,
            "vkey": S.assign_volume(p, t, None),
        })

    # dup_rank: ترتیب ردیف در منبع برای item_indexهای تکراری
    seen_idx = {}
    for r in rows:
        i = r["item_index"]
        if i is not None and i in gate["duplicate_item_index"]["values"]:
            r["dup_rank"] = seen_idx.get(i, 0)
            seen_idx[i] = seen_idx.get(i, 0) + 1
        else:
            r["dup_rank"] = 0

    # ---- گروه‌بندی جلد ---------------------------------------------------------
    groups = {}
    for r in rows:
        v = r["vkey"]
        key = ("vol", v["vol"]) if v["vol"] is not None else ("unknown",)
        groups.setdefault(key, []).append(r)

    work = S.make_work()
    if work_name:
        work["work_name"] = work_name
    if work_description:
        work["description"] = work_description

    edition = S.make_edition(work, {
        "source_manifest_sha256": source.get("summary_sha256") or source["jsonl_sha256"],
        "jsonl_sha256": source["jsonl_sha256"],
        "exported_at_utc": (source.get("json_meta") or {}).get("exported_at_utc"),
        "page_count": source["record_count"],
    })

    volume_objs = []
    for key, grp in groups.items():
        grp_sorted = sorted(grp, key=lambda r: r["page"]["_position"])
        first = grp_sorted[0]["vkey"]
        if key[0] == "vol":
            vol_no = key[1]
            label = "جلد %d" % vol_no
        else:
            vol_no = None
            label = S.DEFAULT_VOL_LABEL
        # استراتژی غالب = استراتژی اولین رکورد (به ترتیب منبع)
        strategy = first["strategy"]
        section = None
        for r in grp_sorted:
            sec = C.section_of_url(r["page"].get("url") or "")
            if sec:
                section = sec
                break
        volume_objs.append((S.make_volume(
            edition["edition_id"], vol_no, label,
            key={"section": section, "vol": vol_no},
            strategy=strategy,
            page_count=len(grp),
            item_index_span=_span([r["item_index"] for r in grp]),
            barg_span=_span([r["barg"] for r in grp if r["barg"] is not None]),
        ), key, grp_sorted))

    volume_objs.sort(key=lambda t: _volume_sort_key(t[0]))

    # ---- صفحات مرتب‌شده ---------------------------------------------------------
    ordered = []
    for vol, _key, grp in volume_objs:
        for r in sorted(grp, key=lambda r: (
                r["item_index"] is None,
                r["item_index"] if r["item_index"] is not None else 0,
                r["dup_rank"],
                r["page"]["_position"])):
            rec = S.make_page(vol["volume_id"], r["item_index"], r["dup_rank"],
                              r["page"], r["barg"], r["raw_barg"], r["text"],
                              r["text_norm"], r["flags"])
            rec["position"] = r["page"]["_position"]
            rec["volume"] = {
                "volume_id": vol["volume_id"],
                "volume_no": vol["volume_no"],
                "volume_title": vol["volume_title"],
            }
            ordered.append(rec)

    # ---- آمار ------------------------------------------------------------------
    flag_counts = {f: 0 for f in S.FLAGS_ALL}
    for rec in ordered:
        for f in rec["quality_status"]["flags"]:
            flag_counts[f] += 1
    flag_counts["ok"] = sum(1 for rec in ordered if not rec["quality_status"]["flags"])

    per_volume = []
    for vol, _key, grp in volume_objs:
        lens = sorted(len(r["text"]) for r in grp)
        per_volume.append({
            "volume_id": vol["volume_id"],
            "volume_no": vol["volume_no"],
            "volume_title": vol["volume_title"],
            "volume_strategy": vol["volume_strategy"],
            "page_count": vol["page_count"],
            "item_index_span": vol["item_index_span"],
            "barg_span": vol["barg_span"],
            "text_len_p50": C.percentile(lens, 50),
            "empty_count": sum(1 for r in grp if S.F_EMPTY in r["flags"]),
            "short_count": sum(1 for r in grp if S.F_SHORT in r["flags"]),
        })

    corpus = {
        "schema_version": S.SCHEMA_VERSION,
        "kind": "tasnim-corpus",
        "work": work,
        "edition": edition,
        "volumes": [v for v, _k, _g in volume_objs],
        "source": {
            "jsonl_path": source["jsonl_path"],
            "jsonl_sha256": source["jsonl_sha256"],
            "jsonl_size_bytes": source["jsonl_size_bytes"],
            "json_path": source.get("json_path"),
            "json_meta": source.get("json_meta"),
            "summary_path": source.get("summary_path"),
            "summary_sha256": source.get("summary_sha256"),
        },
        "config": {
            "policy_id": policy_id,
            "policy": N.policy_spec(policy_id),
            "work_name": work["work_name"],
            "built_by": "corpus.tasnim/" + "1.0.0",
        },
        "stats": {
            "page_count": len(ordered),
            "volume_count": len(volume_objs),
            "quality_flag_counts": flag_counts,
            "text_len": gate["text_len"],
            "item_index": gate["item_index"],
            "barg_reparse": gate["barg_reparse"],
            "duplicates": {
                "item_index_values": gate["duplicate_item_index"]["value_count"],
                "item_index_extra_rows": gate["duplicate_item_index"]["extra_rows"],
                "content_hash_values": gate["duplicate_content_hash"]["value_count"],
                "content_hash_extra_rows": gate["duplicate_content_hash"]["extra_rows"],
            },
            "volume_strategy_census": gate["volume_strategy_census"],
            "volumes": per_volume,
        },
    }
    return {"corpus": corpus, "pages": ordered, "gate": gate}


# --------------------------------------------------------------------------- write
def content_files(corpus: dict, pages: list) -> dict:
    """SHA/size فایل‌های نسخه مستقیم از محتوای درون‌حافظه (بدون نوشتن)."""
    cbytes = C.canonical_json(corpus)
    pbytes = b"".join(C.canonical_json_line(p) for p in pages)
    return {
        "corpus.json": {"sha256": C.sha256_bytes(cbytes), "size_bytes": len(cbytes)},
        "pages.jsonl": {"sha256": C.sha256_bytes(pbytes), "size_bytes": len(pbytes)},
    }


def content_sha256_of_files(files: dict) -> str:
    """files: {name: {"sha256":..., "size_bytes":...}} → شناسه‌ی قطعی محتوای نسخه."""
    blob = "".join("%s:%s:%d\n" % (name, meta["sha256"], meta["size_bytes"])
                   for name, meta in sorted(files.items())).encode("utf-8")
    return C.sha256_bytes(blob)


def write_corpus(build_dir: str, corpus: dict, pages: list) -> dict:
    """نوشتن corpus.json + pages.jsonl + بازتأیید SHA پس از نوشتن."""
    os.makedirs(build_dir, exist_ok=True)
    corpus_path = os.path.join(build_dir, "corpus.json")
    pages_path = os.path.join(build_dir, "pages.jsonl")
    C.write_json(corpus_path, corpus)
    C.write_jsonl(pages_path, pages)
    expected = content_files(corpus, pages)
    files = {}
    for name, meta in expected.items():
        p = os.path.join(build_dir, name)
        sha = C.sha256_file(p)
        if sha != meta["sha256"]:
            raise RuntimeError("write verify failed: %s" % name)
        files[name] = meta
    return {"files": files,
            "content_sha256": content_sha256_of_files(files),
            "paths": {"corpus.json": corpus_path, "pages.jsonl": pages_path},
            "build_dir": build_dir}

# -*- coding: utf-8 -*-
"""tasnim.dataset — خط تولید دیتاست (PCM-20.3 §4).

انتخاب قطعی و تکرارپذیر:
  * 1/10/50/90/100٪ + حالت تک‌جلد (--volume N).
  * لایه‌بندی (stratified) بر اساس جلد: سهم هر جلد با largest-remainder
    (در شکست → جلد با شماره‌ی کوچک‌تر اولویت دارد؛ «نامشخص» آخر).
  * درون هر جلد، انتخاب «بلوک‌های متوالیِ یکنواخت و هم‌فاصله» در ترتیب
    صفحه است تا پیوستگی صفحات حفظ شود (قاعده: «انتخاب نباید بی‌دلیل
    پیوستگی صفحه را بشکند»).
  * رکوردهای کوتاه/ناقص هم انتخاب می‌شوند (حذف ممنوع) — فقط در آمار شمارش.
  * 100٪ = همه‌ی صفحات.

خروجی: datasets/<pct>/vNNNN/{dataset.json, pages.jsonl, manifest.json}.
"""
from __future__ import annotations

import os

from . import common as C
from . import manifest as M
from . import versioning as V
from .transform import content_sha256_of_files

DEFAULT_BLOCKS = 5


# --------------------------------------------------------------------------- selection
def stratify_targets(total_pages: int, pct: int, vol_list) -> dict:
    """سهم هر جلد از انتخاب (largest-remainder؛ جمع دقیقاً target_total).

    vol_list: [(volume_id, volume_no_or_None, page_count)] به ترتیب نمایش.
    برگشت: {volume_id: target}.
    """
    target_total = int(round(total_pages * pct / 100.0))
    if target_total >= total_pages:
        return {vid: n for vid, _vno, n in vol_list}
    if target_total <= 0:
        return {vid: 0 for vid, _vno, _n in vol_list}

    exact = {vid: target_total * n / float(total_pages) for vid, _vno, n in vol_list}
    base = {vid: int(v) for vid, v in exact.items()}
    rem = target_total - sum(base.values())
    vno_of = {vid: vno for vid, vno, _n in vol_list}
    order = sorted(
        exact,
        key=lambda k: (round(exact[k] - int(exact[k]), 9) * -1,
                       0 if vno_of[k] is not None else 1,
                       vno_of[k] if vno_of[k] is not None else 0, k))
    for k in order[:rem]:
        base[k] += 1
    return base


def even_spaced_indexes(count: int, target: int, blocks: int = DEFAULT_BLOCKS) -> set:
    """target شاخص از 0..count-1 به‌صورت بلوک‌های متوالیِ یکنواخت و هم‌فاصله.

    - بلوک‌ها در ترتیب صفحه‌اند → پیوستگی داخلِ هر بلوک حفظ می‌شود.
    - بلوک‌ها در فاصله‌های مساوی از ابتدا تا انتها پخش می‌شوند.
    - اندازه‌ی بلوک‌ها متفاوت‌ترین 1 (توزیع largest-remainder).
    - اگر target > count/2 باشد، تعداد بلوک محدود می‌شود تا هم‌پوشانی
      ایجاد نشود (بدترین حالت: یک بلوک متوالی از ابتدا).
    - کاملاً قطعی (بدون زمان/تصادف).
    """
    if target <= 0:
        return set()
    if target >= count:
        return set(range(count))
    if 2 * target <= count:
        kmax = int(blocks)
    else:
        kmax = max(1, int(target // (2 * target - count)))
    k = max(1, min(kmax, target))
    s = target // k
    extra = target % k
    sizes = [s + (1 if i < extra else 0) for i in range(k)]
    out = set()
    if k == 1:
        out.update(range(0, sizes[0]))
        return out
    span = count - target
    for i, sz in enumerate(sizes):
        start = int(round(i * span / float(k - 1)))
        out.update(range(start, start + sz))
    return out


def _volume_order(pages, by_vol) -> list:
    """[(volume_id, volume_no, count)] — جلد 1، 2، ... و «نامشخص» آخر."""
    return sorted(
        ((vid, recs[0]["volume"]["volume_no"], len(recs)) for vid, recs in by_vol.items()),
        key=lambda t: (0 if t[1] is not None else 1,
                       t[1] if t[1] is not None else 0, t[0]))


def select_dataset(pages, pct: int, volume_no: int = None,
                   blocks: int = DEFAULT_BLOCKS) -> dict:
    """انتخاب صفحات یک دیتاست از صفحات پیکره (قطعی و تکرارپذیر)."""
    pct = int(pct)
    if not 1 <= pct <= 100:
        raise ValueError("pct must be in 1..100")

    by_vol = {}
    if volume_no is not None:
        vol_pages = [p for p in pages if (p.get("volume") or {}).get("volume_no") == volume_no]
        if not vol_pages:
            raise ValueError("volume %d not found in corpus" % volume_no)
        by_vol["__single__"] = vol_pages
    else:
        for p in pages:
            by_vol.setdefault(p["volume_id"], []).append(p)

    vol_order = _volume_order(pages, by_vol)
    total = sum(n for _vid, _vno, n in vol_order)
    targets = stratify_targets(total, pct, vol_order)

    selected, distribution = [], []
    for vid, vno, n in vol_order:
        recs = by_vol[vid]
        tgt = targets[vid]
        full = pct >= 100 or tgt >= n
        picked = list(range(n)) if full else sorted(even_spaced_indexes(n, tgt, blocks))
        for i in picked:
            selected.append(recs[i])
        distribution.append({
            "volume_id": vid,
            "volume_no": vno,
            "volume_title": recs[0]["volume"]["volume_title"],
            "pages_in_volume": n,
            "selected": len(picked),
            "coverage_pct": 100.0 if full else round(100.0 * len(picked) / n, 2),
        })

    selected.sort(key=lambda p: p["page_id"])
    stats = {
        "selected_page_count": len(selected),
        "pct_of_corpus": (100.0 if total == 0 else round(100.0 * len(selected) / total, 2)),
        "volume_distribution": distribution,
        "flag_counts_in_dataset": _flag_counts(selected),
        "text_len_in_dataset": _text_len_stats(selected),
    }
    policy = {
        "id": "stratified-even-blocks",
        "version": "2",
        "percentage": pct,
        "stratify_by": "volume",
        "blocks_per_volume": int(blocks),
        "within_volume": ("contiguous blocks in page order, evenly spaced across the "
                          "volume (continuity preserved; deterministic)"),
        "remainder_rule": "largest-remainder; tie -> smaller volume_no first (unknown last)",
        "volume_scope": ("volume=%d" % volume_no) if volume_no is not None else "all volumes",
        "note": "کوتاه/ناقص حذف نمی‌شوند؛ در آمار شمارش می‌شوند. 100 = همه‌ی صفحات.",
    }
    return {"pages": selected, "policy": policy, "stats": stats}


def _flag_counts(pages) -> dict:
    from . import schema as S
    counts = {f: 0 for f in S.FLAGS_ALL}
    for p in pages:
        for f in p["quality_status"]["flags"]:
            counts[f] += 1
    counts["ok"] = sum(1 for p in pages if not p["quality_status"]["flags"])
    return counts


def _text_len_stats(pages) -> dict:
    lens = sorted(len(p.get("text_normalized") or "") for p in pages)
    if not lens:
        return {"count": 0}
    return {"count": len(lens), "min": lens[0], "p50": C.percentile(lens, 50),
            "p90": C.percentile(lens, 90), "max": lens[-1]}


# --------------------------------------------------------------------------- meta / write
def dataset_meta(corpus_manifest: dict, result: dict, pct: int = None) -> dict:
    """dataset.json — meta + policy + provenance به پیکره و Source Snapshot."""
    cdata = corpus_manifest.get("data") or {}
    if pct is None:
        pct = int(result["policy"].get("percentage") or 0)
    meta = {
        "kind": "tasnim-dataset",
        "dataset_id": "tasnim__%s" % V.pct_dirname(pct),
        "policy": result["policy"],
        "corpus": {
            "version": corpus_manifest.get("version"),
            "content_sha256": cdata.get("content_sha256"),
            "source_snapshot_sha256": (cdata.get("source") or {}).get("jsonl_sha256"),
            "normalization_policy_id": (cdata.get("config") or {}).get("policy_id"),
        },
        "stats": result["stats"],
    }
    return meta


def write_dataset(data_root: str, pct: int, corpus_manifest: dict,
                  result: dict, volume_no: int = None) -> dict:
    """نوشتن یک نسخه‌ی دیتاست (فقط افزایشی) + manifest + registry."""
    paths = V.root_paths(data_root)
    pdir = V.pct_dirname(pct)
    builds_root = os.path.join(paths["datasets"], pdir)
    tag = V.version_tag(V.next_version_number(builds_root))
    out_dir = V.version_dir(builds_root, tag)
    os.makedirs(out_dir, exist_ok=True)

    meta = dataset_meta(corpus_manifest, result, pct)
    ds_path = os.path.join(out_dir, "dataset.json")
    pages_path = os.path.join(out_dir, "pages.jsonl")
    C.write_json(ds_path, meta)
    C.write_jsonl(pages_path, result["pages"])
    files = {
        "dataset.json": {"sha256": C.sha256_file(ds_path), "size_bytes": C.file_size(ds_path)},
        "pages.jsonl": {"sha256": C.sha256_file(pages_path), "size_bytes": C.file_size(pages_path)},
    }
    content_sha256 = content_sha256_of_files(files)

    corpus_ver = str(corpus_manifest.get("version") or "")
    prev_rel = os.path.relpath(os.path.join(paths["corpus_builds"], corpus_ver),
                               paths["root"]).replace(os.sep, "/") + "/manifest.json"
    manifest = M.build_manifest("dataset", tag, {
        "percentage": pct,
        "volume_scope": ({"volume_no": volume_no} if volume_no is not None else None),
        "content_sha256": content_sha256,
        "files": files,
        "dataset_meta": meta,
        "_prev": M.chain_entry(corpus_manifest, prev_rel),
    })
    M.write_manifest(out_dir, manifest)
    V.update_registry(paths["manifests"], "dataset:%s" % pdir, tag,
                      {"corpus": corpus_manifest.get("version"),
                       "content_sha256": content_sha256,
                       "sha256": C.sha256_file(os.path.join(out_dir, "manifest.json"))})
    return {"version": tag, "dir": out_dir, "files": files,
            "content_sha256": content_sha256, "reused": False}

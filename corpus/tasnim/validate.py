# -*- coding: utf-8 -*-
"""tasnim.validate — اعتبارسنجی پیکره (PCM-20.3 §3, §9).

بررسی‌ها (روی یک build: corpus.json + pages.jsonl):
  V01  ساختار: فیلدهای الزامی کار/ویرایش/جلد/صفحه.
  V02  ارجاعات: volume_id هر صفحه باید در volumes باشد.
  V03  شناسه‌ها: page_id یکتا + با فرمول قطعی سازگار (برای صفحات دارای item_index).
  V04  provenance: source_page_id + content_hash موجود و متناسخ با هدر منبع.
  V05  بازسازی barg: raw_barg → parse همه‌ی ریک‌های ارقام == barg.
  V06  RAW/NORMALIZED: textNormalized مطابق policy از text بازتولید می‌شود.
  V07  آمار: page_count و شمارنده‌های کیفیت با شمارش واقعی یکسان.
  V08  manifest: SHAهای ثبت‌شده با فایل‌ها یکسان + زنجیره‌ی prev.

برگشت: (ok, errors, warnings) — همان قرارداد validateهای PCT.
"""
from __future__ import annotations

import os

from . import common as C
from . import normalize as N
from . import manifest as M
from . import schema as S


def load_build(build_dir: str) -> dict:
    corpus = C.read_json(os.path.join(build_dir, "corpus.json"))
    pages = C.read_jsonl(os.path.join(build_dir, "pages.jsonl"))
    return {"corpus": corpus, "pages": pages, "dir": build_dir}


def validate_corpus(build_dir: str) -> tuple:
    errors, warnings = [], []
    try:
        b = load_build(build_dir)
    except Exception as e:
        return False, ["corpus unreadable: %s" % e], []
    corpus, pages = b["corpus"], b["pages"]

    # V01 structure
    for k in ("work", "edition", "volumes", "source", "config", "stats"):
        if k not in corpus:
            errors.append("V01 corpus.%s missing" % k)
    vols = {v["volume_id"]: v for v in corpus.get("volumes", [])}
    for v in corpus.get("volumes", []):
        for k in ("volume_id", "edition_id", "volume_no", "volume_title",
                  "source_section", "page_count", "volume_strategy"):
            if k not in v:
                errors.append("V01 volume field %r missing: %s" % (k, v.get("volume_id")))
    for p in pages:
        for k in ("page_id", "volume_id", "item_index", "barg", "raw_barg",
                  "text", "text_normalized", "url", "captured_at",
                  "content_hash", "source_page_id", "quality_status", "metadata"):
            if k not in p:
                errors.append("V01 page field %r missing: %s" % (k, p.get("page_id")))
                break

    # V02 references
    orphan = [p["page_id"] for p in pages if p.get("volume_id") not in vols]
    if orphan:
        errors.append("V02 %d pages with unknown volume_id (first: %s)"
                      % (len(orphan), orphan[0]))

    # V03 ids unique + deterministic
    seen = set()
    dup_ids = 0
    for p in pages:
        pid = p["page_id"]
        if pid in seen:
            dup_ids += 1
        else:
            seen.add(pid)
    if dup_ids:
        errors.append("V03 %d duplicate page_id" % dup_ids)
    # page_id برای صفحات دارای item_index باید با فرمول قطعی سازگار باشد
    bad_formula = 0
    for p in pages:
        if p.get("item_index") is None:
            continue
        base = "%s__p%d" % (p["volume_id"], p["item_index"])
        if not p["page_id"].startswith(base):
            bad_formula += 1
            if bad_formula > 5:
                break
    if bad_formula:
        errors.append("V03 %d page_ids not matching the deterministic formula" % bad_formula)

    # V04 provenance
    no_src = sum(1 for p in pages if p.get("source_page_id") in (None, ""))
    no_hash = sum(1 for p in pages if p.get("content_hash") in (None, ""))
    if no_src:
        errors.append("V04 %d pages without source_page_id" % no_src)
    if no_hash:
        warnings.append("V04 %d pages without content_hash" % no_hash)

    # V05 barg reconstruction
    bad_barg = 0
    for p in pages:
        if p.get("raw_barg") is None:
            if p.get("barg") is not None:
                bad_barg += 1
            continue
        expect = C.parse_barg_all_runs(p["raw_barg"])
        if expect != p.get("barg"):
            bad_barg += 1
            if bad_barg > 5:
                break
    if bad_barg:
        errors.append("V05 %d pages where raw_barg does not reparse to barg" % bad_barg)

    # V06 normalized reconstruction
    policy_id = (corpus.get("config") or {}).get("policy_id")
    if policy_id:
        bad_norm = 0
        for p in pages:
            expect = N.normalize_text(p.get("text") or "", policy_id)
            if expect != p.get("text_normalized"):
                bad_norm += 1
                if bad_norm > 5:
                    break
        if bad_norm:
            errors.append("V06 %d pages where text_normalized != policy(text)" % bad_norm)
    else:
        warnings.append("V06 policy_id missing in config")

    # V07 stats
    st = corpus.get("stats") or {}
    if st.get("page_count") != len(pages):
        errors.append("V07 stats.page_count=%r != actual %d" % (st.get("page_count"), len(pages)))
    if st.get("volume_count") != len(corpus.get("volumes", [])):
        errors.append("V07 stats.volume_count mismatch")
    actual_flags = {f: 0 for f in S.FLAGS_ALL}
    for p in pages:
        for f in p["quality_status"]["flags"]:
            actual_flags[f] += 1
    actual_flags["ok"] = sum(1 for p in pages if not p["quality_status"]["flags"])
    rec_flags = st.get("quality_flag_counts") or {}
    for f in S.FLAGS_ALL:
        if rec_flags.get(f) != actual_flags[f]:
            errors.append("V07 flag %s: recorded=%r actual=%r" % (f, rec_flags.get(f), actual_flags[f]))

    # V08 manifest
    mpath = os.path.join(build_dir, "manifest.json")
    if os.path.exists(mpath):
        ok, merr, mwarn = M.validate_manifest(build_dir)
        if not ok:
            errors.extend("V08 %s" % e for e in merr)
        warnings.extend(mwarn)
    else:
        warnings.append("V08 manifest.json missing in build dir")

    return (not errors), errors, warnings

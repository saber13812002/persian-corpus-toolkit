# -*- coding: utf-8 -*-
"""tasnim.backfill.gap — گزارش شکاف (gap-report-2) برای Backfill (PCM-20.6.3).

ورودی: `pages.jsonl` یک build پیکره (v0003 یا جدیدتر) — همان فرمت خط
تولید (فیلدهای `item_index` و `volume{volume_id,volume_no,volume_title}`).

خروجی: dict با قرارداد `gap-report-2`:
    * بازحساب **همان 6 بازه‌ی مفقود** (45,243 صفحه در دیتای واقعی v0003)
      از خودِ pages.jsonl — بدون تکیه بر گزارش قبلی (دست‌اول / from scratch).
    * نسبت‌دادن هر run به همسایه‌های موجود + جلد(های) مرز (فقط به‌عنوان
      شواهد؛ ابهام جلد در Backfill هرگز «تخمین» نیست — ر.ک. parse.py).
    * بدون شبکه؛ قطعی (content_sha256 روی هسته‌ی بدون generated_at).

ارتباط با `gap_report.py` (bf-1): همان الگوریتم `missing_runs` و
`attribute_run` به‌استفاده می‌رود تا دو گزارش هیچ‌گاه از هم انحراف نگیرند.
"""
from __future__ import annotations

import bisect
import os

from .. import common as C
from .. import gap_report as GR

CONTRACT = "gap-report-2"
MISSION = "PCM-20.6.3"


# --------------------------------------------------------------------------- load
def load_pages_item_indexes(pages_jsonl: str) -> dict:
    """بارگذاری item_indexها از pages.jsonl یک build.

    برگشت: {"distinct": [...], "dup_count": n, "total_records": n,
            "no_index": n}
    """
    present, seen = [], set()
    total = 0
    no_index = 0
    for p in C.read_jsonl(pages_jsonl):
        total += 1
        idx = p.get("item_index")
        if idx is None:
            no_index += 1
            continue
        if idx in seen:
            continue
        seen.add(idx)
        present.append(idx)
    present.sort()
    dup_count = (total - no_index) - len(seen)
    return {"distinct": present, "dup_count": dup_count,
            "total_records": total, "no_index": no_index}


def volume_map_from_pages(pages_jsonl: str) -> dict:
    """item_index -> (volume_no, volume_title) از pages.jsonl.

    نکته‌ی مهم (PCM-20.6.0 §4): روی item_index تکراری، **اولین رکورد
    دیده‌شده برنده می‌ماند** (setdefault) — این یک انتخاب خاموش است و
    برای نسبت‌دادن «تقریبی» (نمایش/راهنما) قابل قبول است، اما Backfill
    برای تخصیص جلد واقعی از شواهد رکورد خود (section در URL + متن)
    استفاده می‌کند و ابهام را flag می‌کند (parse.volume_candidates).
    """
    out = {}
    for p in C.read_jsonl(pages_jsonl):
        idx = p.get("item_index")
        if idx is None:
            continue
        vol = p.get("volume") or {}
        out.setdefault(idx, (vol.get("volume_no"), vol.get("volume_title")))
    return out


# --------------------------------------------------------------------------- report
def build_gap_report_v2(pages_jsonl: str) -> dict:
    """بازحساب کامل شکاف‌ها از pages.jsonl (قطعی، بدون شبکه).

    اگر `pages.jsonl` دیتای واقعی v0003 باشد، این تابع اعداد
    Phase-0-verified را بازتولید می‌کند: 45,844 رکورد؛ 45,835 متمایز؛
    9 تکراری؛ 45,243 مفقود در 6 بازه.
    """
    if not os.path.exists(pages_jsonl):
        raise FileNotFoundError(pages_jsonl)
    loaded = load_pages_item_indexes(pages_jsonl)
    present = loaded["distinct"]
    if not present:
        raise ValueError("no item_index values in %s" % pages_jsonl)
    lo, hi = present[0], present[-1]
    runs = GR.missing_runs(present, lo, hi)
    vol_map = volume_map_from_pages(pages_jsonl)
    detail = [GR.attribute_run(r, vol_map, present) for r in runs]

    report = {
        "contract": CONTRACT,
        "mission": MISSION,
        "source": {
            "pages_jsonl": os.path.abspath(pages_jsonl),
            "pages_sha256": C.sha256_file(pages_jsonl),
        },
        "pages": {
            "total_records": loaded["total_records"],
            "with_item_index": loaded["total_records"] - loaded["no_index"],
            "distinct_item_index": len(present),
            "dup_count": loaded["dup_count"],
            "no_index": loaded["no_index"],
            "range_min": lo,
            "range_max": hi,
            "span": hi - lo + 1,
        },
        "gaps": {
            "missing_count": sum(d["count"] for d in detail),
            "runs_count": len(detail),
            "runs": detail,
        },
        "summary_fa": [],
    }
    g = report["gaps"]
    p = report["pages"]
    report["summary_fa"] = [
        "بازه‌ی موجود item_index: %d تا %d (گستره‌ی %d موقعیت)."
        % (p["range_min"], p["range_max"], p["span"]),
        "رکوردهای build: %d؛ item_index متمایز: %d (تکراری: %d)."
        % (p["total_records"], p["distinct_item_index"], p["dup_count"]),
        "مفقودیِ item_index: %d صفحه در %d بازه‌ی پیوسته."
        % (g["missing_count"], g["runs_count"]),
    ]
    for d in detail:
        report["summary_fa"].append(
            "  * [%d..%d] (%d صفحه) — همسایه‌های موجود: قبل %s، بعد %s"
            % (d["start"], d["end"], d["count"],
               d.get("before_item_index"), d.get("after_item_index")))

    # قطعی: SHA روی هسته‌ی بدون generated_at (همان قرارداد gap-report-1)
    core = report
    report["content_sha256"] = C.sha256_text(
        C.canonical_json(core).decode("utf-8"))
    report["generated_at"] = C.now_utc()
    return report


def write_gap_report_v2(report: dict, out_path: str) -> str:
    d = os.path.dirname(out_path)
    if d:
        os.makedirs(d, exist_ok=True)
    C.write_bytes(out_path, C.canonical_json(report))
    return out_path


def runs_of(report: dict) -> list:
    """فهرست [start, end] بازه‌های مفقود (برای plan/fetch)."""
    return [list(r) for r in
            ((d["start"], d["end"]) for d in report["gaps"]["runs"])]


if __name__ == "__main__":
    import argparse
    C.force_utf8_stdio()
    ap = argparse.ArgumentParser(prog="backfill-gap-report")
    ap.add_argument("--pages", required=True, help="pages.jsonl یک build")
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv=None)
    rep = build_gap_report_v2(args.pages)
    write_gap_report_v2(rep, args.out)
    print("=== BACKFILL GAP REPORT (PCM-20.6.3) ===")
    print("runs        : %d" % rep["gaps"]["runs_count"])
    print("missing     : %d / span %d"
          % (rep["gaps"]["missing_count"], rep["pages"]["span"]))
    print("content sha : %s" % rep["content_sha256"])
    print("out         : %s" % args.out)
    for line in rep["summary_fa"]:
        print("  %s" % line)

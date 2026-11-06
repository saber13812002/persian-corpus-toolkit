# -*- coding: utf-8 -*-
"""tasnim.gap_report — تحلیل شکاف‌های item_index (PCM-20.6 SUBTASK 02 / D2).

ورودی: snapshot خام (tasnim-corpus.jsonl) + (اختیاری) pages.jsonl یک build
پیکره برای نسبت‌دادن شکاف‌ها به جلد.

خروجی:
  * gap-report.json — ماشین‌خوان (runs پیوسته + نسبت به جلد + نمونه‌گیری زنده
    + طرح Backfill نسخه‌شده، فقط طرح — اجرا نمی‌شود) + خلاصه‌ی فارسی.

قواعد:
  * قطعی (deterministic): بدون شبکه به‌طور پیش‌فرض؛ `--live` اختیاری است و
    فقط GET‌های read-only می‌زند (حداکثر 10 درخواست).
  * هرگز رکوردی حذف/تغییر نمی‌شود؛ این ماژুল فقط خواندنی است.
  * اگر سایت دسترس‌ناپذیر باشد → live_sampling.status = "BLOCKED" با شواهد
    (خطا + زمان + شمارش تلاش)؛ گزارش به‌جای خود ادامه می‌یابد.
"""
from __future__ import annotations

import bisect
import json
import os
import time
import urllib.error
import urllib.request
import hashlib

from . import common as C

LIVE_BASE = ("https://tasnim.hamtaa.org/api/v1/files/tasnim/chunk-detail"
             "?item_index=")
MAX_LIVE_PROBES = 10
MISSION = "PCM-20.6 SUBTASK 02 / D2"
BACKFILL_ID = "bf-1"
BACKFILL_STATUS = "design-only (not executed)"


# --------------------------------------------------------------------------- core
def load_item_indexes(jsonl_path: str) -> dict:
    """بارگذاری item_indexها از snapshot خام.

    برگشت: {"distinct": [...], "dup_count": n, "total_records": n,
            "no_index": n}
    """
    present, seen = [], set()
    total = 0
    no_index = 0
    with open(jsonl_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            total += 1
            idx = rec.get("item_index")
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


def missing_runs(present_sorted: list, lo: int, hi: int) -> list:
    """شکاف‌های پیوسته (start, end) در بازه‌ی [lo, hi].

    `present_sorted` باید صعودی و بدون تکرار باشد.
    """
    runs = []
    i = 0
    n = len(present_sorted)
    while i < n and present_sorted[i] < lo:
        i += 1
    gap_start = lo
    while i < n:
        x = present_sorted[i]
        if x > hi:
            break
        if x > gap_start:
            # شکافِ [gap_start, x-1] بین موجودِ قبل و x
            runs.append([gap_start, x - 1])
        gap_start = x + 1
        i += 1
    if gap_start <= hi:
        runs.append([gap_start, hi])
    return runs


def volume_map_from_pages(pages_jsonl: str) -> dict:
    """item_index -> (volume_no, volume_title) از pages.jsonl یک build."""
    out = {}
    if not pages_jsonl or not os.path.exists(pages_jsonl):
        return out
    for p in C.read_jsonl(pages_jsonl):
        idx = p.get("item_index")
        if idx is None:
            continue
        vol = p.get("volume") or {}
        out.setdefault(idx, (vol.get("volume_no"), vol.get("volume_title")))
    return out


def _neighbor_volume(vol_map: dict, candidates: list):
    for c in candidates:
        if c in vol_map:
            return {"volume_no": vol_map[c][0], "volume_title": vol_map[c][1]}
    return None


def attribute_run(run: list, vol_map: dict, present_sorted: list) -> dict:
    """نسبت‌دادن یک run به جلد(های) همسایه (آخرین موجود قبل / اولین بعد)."""
    lo, hi = run
    before, after = None, None
    # جست‌وجوی دودویی برای همسایه‌های موجود
    j = bisect.bisect_left(present_sorted, lo)
    if j > 0:
        before = present_sorted[j - 1]
    k = bisect.bisect_right(present_sorted, hi)
    if k < len(present_sorted):
        after = present_sorted[k]
    return {
        "start": lo,
        "end": hi,
        "count": hi - lo + 1,
        "before_item_index": before,
        "after_item_index": after,
        "volume_before": _neighbor_volume(vol_map, [before]),
        "volume_after": _neighbor_volume(vol_map, [after]),
    }


# --------------------------------------------------------------------------- live
def live_pick(runs: list, present_sorted: list, max_n: int = MAX_LIVE_PROBES) -> list:
    """انتخاب قطعی ≤10 نقطه‌ی نمونه‌گیری.

    * وسطِ هر run (یک برای هر run)؛
    * دو کنترل: آخرین موجودِ قبل و اولین موجودِ بعدِ بزرگ‌ترین run
      (سند صحت endpoint + موجودبودن صفحات مرزی).
    """
    picks = []
    for r in runs:
        mid = r[0] + (r[1] - r[0]) // 2
        picks.append({"item_index": mid,
                      "reason": "midpoint of missing run [%d,%d]" % (r[0], r[1])})
    if runs:
        big = max(runs, key=lambda r: r[1] - r[0])
        j = bisect.bisect_left(present_sorted, big[0])
        k = bisect.bisect_right(present_sorted, big[1])
        if j > 0:
            picks.append({"item_index": present_sorted[j - 1],
                          "reason": "control: last present before largest run"})
        if k < len(present_sorted):
            picks.append({"item_index": present_sorted[k],
                          "reason": "control: first present after largest run"})
    seen = set()
    out = []
    for p in picks:
        if p["item_index"] in seen:
            continue
        seen.add(p["item_index"])
        out.append(p)
        if len(out) >= max_n:
            break
    return out


def live_probe(item_index: int, base: str = None,
               timeout: float = 40.0, tries: int = 3, sleep: float = 3.0) -> dict:
    """یک GET read-only. برگشت: {item_index, url, status, ...}."""
    url = (base or LIVE_BASE) + str(item_index)
    out = {"item_index": item_index, "url": url, "status": None}
    last_err = None
    for a in range(tries):
        try:
            req = urllib.request.Request(url,
                                         headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                body = r.read().decode("utf-8", "replace")
                data = json.loads(body)
                text = data.get("original_text") or ""
                out.update({
                    "status": "present" if text.strip() else "empty",
                    "http": r.status,
                    "text_len": len(text),
                    "text_sha256": C.sha256_text(text),
                    "section": data.get("section"),
                })
                return out
        except urllib.error.HTTPError as e:
            out.update({"status": "not_found", "http": e.code})
            return out
        except Exception as e:  # noqa: BLE001 — هر خطای شبکه
            last_err = "%s: %s" % (type(e).__name__, e)
            if a < tries - 1:
                time.sleep(sleep)
    out.update({"status": "blocked", "error": last_err})
    return out


def live_sampling(runs: list, present_sorted: list, base: str = None,
                  timeout: float = 40.0, tries: int = 3,
                  sleep: float = 0.1, max_n: int = MAX_LIVE_PROBES) -> dict:
    """نمونه‌گیری زنده‌ی ≤10 URL (read-only). هرگز build را متاثر نمی‌کند."""
    base = base or LIVE_BASE
    picks = live_pick(runs, present_sorted, max_n)
    probes = []
    blocked = 0
    for p in picks:
        r = live_probe(p["item_index"], base=base, timeout=timeout,
                       tries=tries, sleep=sleep)
        r["reason"] = p["reason"]
        if r["status"] == "blocked":
            blocked += 1
        probes.append(r)
        time.sleep(1.5)
    if not picks:
        status = "none"
    elif blocked == len(probes):
        status = "BLOCKED"
    elif blocked:
        status = "PARTIAL"
    else:
        status = "OK"
    return {
        "status": status,
        "base": base,
        "max_probes": max_n,
        "probed": len(probes),
        "blocked": blocked,
        "probes": probes,
    }


# --------------------------------------------------------------------------- backfill design
def backfill_design(missing_count: int, pages_per_minute: float) -> dict:
    """طرح نسخه‌شده‌ی Backfill — فقط طرح (executed=False)."""
    hours = (missing_count / pages_per_minute) / 60.0
    return {
        "id": BACKFILL_ID,
        "status": BACKFILL_STATUS,
        "executed": False,
        "note_fa": ("این طرح برای اجرا نیست؛ اجرای واقعی فقط در مأموریت بعدی و با "
                    "تأیید دسترسی زنده‌ی سایت صورت می‌گیرد."),
        "approach_fa": (
            "بازکراول item_indexهای مفقود با همان مکانیزم اصلی (payload URL)، "
            "append-only: رکوردهای جدید در snapshot جدید افزوده می‌شوند؛ "
            "هیچ رکورد موجودی حذف یا بازنویسی نمی‌شود."),
        "approach": (
            "Re-crawl the missing item_index values via the site payload URL "
            "(same mechanism as the original crawl), append-only: new records "
            "go into a new source snapshot; existing records are never "
            "modified or deleted."),
        "steps": [
            "1. reachability + rate probe (this report, <=10 read-only GETs)",
            "2. build a queue of the missing item_index values (contiguous "
               "runs), rate-limited to the observed ~%d pages/min" % pages_per_minute,
            "3. crawl into data/tasnim/<next>/source-snapshot-backfill/"
               "tasnim-corpus-backfill.jsonl with per-record provenance "
               "(url + captured_at + content_hash)",
            "4. register the backfill as a new source snapshot version "
               "(content-sha chained, append-only)",
            "5. rebuild: build-corpus on the merged snapshot; the gap ledger "
               "shrinks; on content-hash conflict the OLD record wins and the "
               "conflict is logged (no silent overwrite)",
            "6. re-validate V01..V09 + S01..S10 before any dataset/dump is "
               "cut from the new version",
        ],
        "safety": [
            "no record deletion without evidence",
            "no overwrite of existing snapshot records",
            "append-only snapshot versions with provenance chain",
            "rate-limited to not disturb the live site",
        ],
        "estimates": {
            "requests": missing_count,
            "pages_per_minute_observed": pages_per_minute,
            "estimated_hours_at_observed_rate": round(hours, 1),
            "estimated_days_at_observed_rate": round(hours / 24.0, 1),
        },
    }


# --------------------------------------------------------------------------- report
def build_gap_report(jsonl_path: str, pages_jsonl: str = None,
                     live: bool = False,
                     live_timeout: float = 40.0, live_tries: int = 3,
                     pages_per_minute: float = 4.0) -> dict:
    """محاسبه‌ی کامل گزارش شکاف (قطعی؛ شبکه فقط با live=True)."""
    loaded = load_item_indexes(jsonl_path)
    present = loaded["distinct"]
    if not present:
        raise ValueError("no item_index values in %s" % jsonl_path)
    lo, hi = present[0], present[-1]
    runs = missing_runs(present, lo, hi)
    detail = [attribute_run(r, volume_map_from_pages(pages_jsonl), present)
              for r in runs]

    # نسبت به جلد: هر run یا یک‌جلدی است یا دو مرز را می‌پوشد
    by_vol = {}
    for d in detail:
        vb = d.get("volume_before") or {}
        va = d.get("volume_after") or {}
        vno = vb.get("volume_no") or va.get("volume_no")
        if vno is None:
            key = "unknown"
        elif vb.get("volume_no") and va.get("volume_no") \
                and vb["volume_no"] != va["volume_no"]:
            key = "%s->%s (boundary)" % (vb["volume_no"], va["volume_no"])
        else:
            key = str(vno)
        e = by_vol.setdefault(key, {
            "volume_no": None if vno is None else vno,
            "run_count": 0, "missing_count": 0})
        e["run_count"] += 1
        e["missing_count"] += d["count"]

    report = {
        "mission": MISSION,
        "contract": "gap-report-1",
        "source": {
            "jsonl_path": jsonl_path,
            "jsonl_sha256": C.sha256_file(jsonl_path),
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
            "missing_by_volume": sorted(by_vol.values(),
                                        key=lambda e: (e["volume_no"] is None,
                                                       e["volume_no"])),
        },
        "live_sampling": None,
        "backfill": backfill_design(sum(d["count"] for d in detail),
                                    pages_per_minute),
        "summary_fa": [],
    }
    if live:
        report["live_sampling"] = live_sampling(
            runs, present, timeout=live_timeout, tries=live_tries)

    g = report["gaps"]
    p = report["pages"]
    report["summary_fa"] = [
        "بازه‌ی موجود item_index: %d تا %d (گستره‌ی %d موقعیت)."
        % (p["range_min"], p["range_max"], p["span"]),
        "رکوردهای snapshot: %d؛ item_index متمایز: %d (تکراری: %d)."
        % (p["total_records"], p["distinct_item_index"], p["dup_count"]),
        "مفقودیِ item_index: %d صفحه در %d بازه‌ی پیوسته."
        % (g["missing_count"], g["runs_count"]),
    ]
    for d in detail:
        vb = (d.get("volume_before") or {}).get("volume_no")
        va = (d.get("volume_after") or {}).get("volume_no")
        vol_fa = "جلد %s" % vb if vb is not None else "جلد نامشخص"
        if va is not None and vb is not None and va != vb:
            vol_fa = "مرز جلد %s تا %s" % (vb, va)
        report["summary_fa"].append(
            "  * [%d..%d] (%d صفحه) — نزدیک‌ترین موجود: قبل %s، بعد %s — %s"
            % (d["start"], d["end"], d["count"],
               d.get("before_item_index"), d.get("after_item_index"), vol_fa))
    ls = report.get("live_sampling")
    if ls is not None:
        if ls["status"] == "OK":
            report["summary_fa"].append(
                "نمونه‌گیری زنده: %d نقطه — همه‌ی درخواستها پاسخ دادند."
                % ls["probed"])
        elif ls["status"] == "BLOCKED":
            report["summary_fa"].append(
                "نمونه‌گیری زنده: BLOCKED — سایت دسترس‌پذیر نبود "
                "(%d/%d در خواست خطا داد). شواهد در live_sampling."
                % (ls["blocked"], ls["probed"]))
        else:
            report["summary_fa"].append(
                "نمونه‌گیری زنده: %s — %d از %d در خواست خطا داد."
                % (ls["status"], ls["blocked"], ls["probed"]))
    report["summary_fa"].append(
        "طرح Backfill: %s — فقط طرح، اجرا نشده است." % BACKFILL_ID)

    # قطعی بودن: SHA روی گزارشِ بدون generated_at / بدون sample زنده
    core = {k: v for k, v in report.items() if k != "live_sampling"}
    report["content_sha256"] = C.sha256_text(
        C.canonical_json(core).decode("utf-8"))
    report["generated_at"] = C.now_utc()
    return report


def write_gap_report(report: dict, out_path: str) -> str:
    d = os.path.dirname(out_path)
    if d:
        os.makedirs(d, exist_ok=True)
    C.write_bytes(out_path, C.canonical_json(report))
    return out_path


def main(argv=None) -> int:
    """CLI مستقیم (خارج از cli.py برای ساده‌بودن): gap-report."""
    import argparse
    C.force_utf8_stdio()
    ap = argparse.ArgumentParser(prog="gap-report")
    ap.add_argument("--jsonl", required=True)
    ap.add_argument("--pages", default=None,
                    help="pages.jsonl یک build برای نسبت‌دادن به جلد")
    ap.add_argument("--out", required=True)
    ap.add_argument("--live", action="store_true",
                    help="نمونه‌گیری زنده‌ی <=10 GET (read-only)")
    ap.add_argument("--timeout", type=float, default=40.0)
    ap.add_argument("--tries", type=int, default=3)
    ap.add_argument("--pages-per-minute", type=float, default=4.0)
    args = ap.parse_args(argv)
    report = build_gap_report(args.jsonl, args.pages, live=args.live,
                              live_timeout=args.timeout, live_tries=args.tries,
                              pages_per_minute=args.pages_per_minute)
    write_gap_report(report, args.out)
    print("=== GAP REPORT (PCM-20.6 D2) ===")
    print("runs        : %d" % report["gaps"]["runs_count"])
    print("missing     : %d / span %d"
          % (report["gaps"]["missing_count"], report["pages"]["span"]))
    ls = report.get("live_sampling")
    print("live        : %s" % (ls["status"] if ls else "not run"))
    print("backfill    : %s (%s)" % (report["backfill"]["id"],
                                     report["backfill"]["status"]))
    print("content sha : %s" % report["content_sha256"])
    print("out         : %s" % args.out)
    for line in report["summary_fa"]:
        print("  %s" % line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

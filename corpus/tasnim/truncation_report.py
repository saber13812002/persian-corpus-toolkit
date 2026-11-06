# -*- coding: utf-8 -*-
"""tasnim.truncation_report — رسمی‌سازی سقف ۲۰۰۰ کاراکتر (PCM-20.6 SUBTASK 02 / D3).

ورودی: pages.jsonl یک build پیکره (فقط خواندنی).

خروجی:
  * truncation-report.json — ماشین‌خوان:
      - census صفحاتِ دقیقاً در سقف (len(text) == 2000) + صفحاتِ فراسقف؛
      - فهرست کامل صفحات متاثر (page_id/item_index/جلد/پایان‌بندی)؛
      - (اختیاری، --live) بازبینی زنده‌ی ۲-۳ صفحه از همان ۲۸ صفحه از
        endpoint رسمیِ سایت (read-only GET) برای تأییدِ مجددِ اینکه
        سقف در سمت منبع است (تأیید مستقل از شواهد GATE 1.5 در PCM-20.4)؛
      - نتیجه‌ی قطعی + ارجاع به شواهد GATE 1.5 (path_rel + sha256).

قواعد:
  * deterministic: بدون شبکه به‌طور پیش‌فرض؛ `--live` اختیاری است و فقط
    GET‌های read-only می‌زند (حداکثر ۳ درخواست).
  * هیچ رکوردی حذف/تغییر نمی‌شود؛ این ماژول فقط خواندنی است.
  * اگر سایت دسترس‌ناپذیر باشد → live_recheck.status = "BLOCKED" با شواهد؛
    گزارش به‌جای خود ادامه می‌یابد (نتیجه‌ی GATE 1.5 مستقل از این بازبینی است).

سند شواهد: data/tasnim/pcm20_4/validation/gate1_5_truncation_conclusion.json
(E1: نبود truncation در کل pipeline، E2: نبود pile-up حول مرز،
E3: هم‌توزعی شکل پایان‌ها، E4: تطبیق زنده‌ی ۵ آیتم در PCM-20.4).
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request

from . import common as C
from . import schema as S

LIVE_BASE = ("https://tasnim.hamtaa.org/api/v1/files/tasnim/chunk-detail"
             "?item_index=")
MAX_LIVE_RECHECK = 3
DEFAULT_LIVE_N = 3
MISSION = "PCM-20.6 SUBTASK 02 / D3"
CONTRACT = "truncation-report-1"


# --------------------------------------------------------------------------- census
def at_cap_pages(pages_jsonl: str) -> list:
    """فهرست صفحاتی که دقیقاً در سقف ۲۰۰۰ کاراکتر هستند (قطعی، read-only).

    برگشت: [{"page_id", "item_index", "volume_no", "text_len", "tail"}, ...]
    مرتب بر اساس (جلد صعودی بدون‌جلد آخر، item_index صعودی، page_id).
    """
    out = []
    if not pages_jsonl or not os.path.exists(pages_jsonl):
        return out
    for p in C.read_jsonl(pages_jsonl):
        text = p.get("text") or ""
        if len(text) != S.SOURCE_CHAR_CAP:
            continue
        vol = p.get("volume") or {}
        out.append({
            "page_id": p.get("page_id"),
            "item_index": p.get("item_index"),
            "volume_no": vol.get("volume_no"),
            "text_len": len(text),
            "tail": text[-40:],
        })
    out.sort(key=lambda e: (e["volume_no"] is None,
                            e["volume_no"] if e["volume_no"] is not None else 0,
                            e["item_index"] if e["item_index"] is not None
                            else 10 ** 9,
                            e["page_id"] or ""))
    return out


def census(pages_jsonl: str) -> dict:
    """شمارش کل/در‌سقف/فراسقف (read-only)."""
    total = 0
    at_cap = 0
    over_cap = 0
    if not pages_jsonl or not os.path.exists(pages_jsonl):
        return {"total_pages": 0, "at_cap_count": 0, "over_cap_count": 0}
    for p in C.read_jsonl(pages_jsonl):
        total += 1
        n = len(p.get("text") or "")
        if n == S.SOURCE_CHAR_CAP:
            at_cap += 1
        elif n > S.SOURCE_CHAR_CAP:
            over_cap += 1
    return {"total_pages": total, "at_cap_count": at_cap,
            "over_cap_count": over_cap}


def by_volume(pages_list: list) -> dict:
    """گروه‌بندی صفحات در‌سقف بر اساس جلد."""
    out = {}
    for e in pages_list:
        key = str(e["volume_no"]) if e["volume_no"] is not None else "unknown"
        out[key] = out.get(key, 0) + 1
    return out


# --------------------------------------------------------------------------- live re-check
def _norm_ws(text: str) -> str:
    """همان policy crawler: هر whitespace پیوسته → یک فاصله."""
    import re
    return re.sub(r"\s+", " ", text or "").strip()


def live_recheck_page(item_index: int, base: str = None,
                      timeout: float = 40.0, tries: int = 3,
                      sleep: float = 3.0) -> dict:
    """یک GET read-only بر روی endpoint رسمیِ سایت.

    برگشت: {item_index, url, status, http, live_len, text_sha256, ...}
    status ∈ {"at_cap", "longer", "shorter", "empty", "not_found", "blocked"}
    """
    base = base or LIVE_BASE
    url = base + str(item_index)
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
                n = len(text)
                if n == S.SOURCE_CHAR_CAP:
                    status = "at_cap"
                elif n > S.SOURCE_CHAR_CAP:
                    status = "longer"
                elif n > 0:
                    status = "shorter"
                else:
                    status = "empty"
                out.update({
                    "status": status,
                    "http": r.status,
                    "live_len": n,
                    "live_tail": text[-40:],
                    "live_ws_norm_sha256": C.sha256_text(_norm_ws(text)),
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


def pick_recheck_pages(pages_list: list, n: int = DEFAULT_LIVE_N) -> list:
    """انتخاب قطعی ≤3 صفحه‌ی در‌سقف برای بازبینی زنده.

    صفحه‌هایی که قبلاً در GATE 1.5 (PCM-20.4) زنده چک شده‌اند
    (39137, 66532) تکرار نمی‌شوند؛ باقی‌مانده به ترتیب قطعی.
    """
    already = {39137, 66532}
    cand = [e for e in pages_list if e["item_index"] not in already]
    if not cand:
        cand = list(pages_list)
    return cand[:n]


def live_recheck(pages_jsonl: str, n: int = DEFAULT_LIVE_N, base: str = None,
                 timeout: float = 40.0, tries: int = 3,
                 sleep: float = 1.5) -> dict:
    """بازبینی زنده‌ی ≤3 صفحه از صفحات در‌سقف (read-only)."""
    pages_list = at_cap_pages(pages_jsonl)
    picked = pick_recheck_pages(pages_list, n)
    checks = []
    for e in picked:
        if e["item_index"] is None:
            checks.append({"item_index": None, "page_id": e["page_id"],
                           "status": "skipped",
                           "reason": "no item_index"})
            continue
        r = live_recheck_page(e["item_index"], base=base, timeout=timeout,
                              tries=tries, sleep=sleep)
        r["page_id"] = e["page_id"]
        r["volume_no"] = e["volume_no"]
        checks.append(r)
        time.sleep(sleep)
    if not picked:
        status = "none"
    elif all(c["status"] == "blocked" for c in checks):
        status = "BLOCKED"
    elif any(c["status"] == "blocked" for c in checks):
        status = "PARTIAL"
    else:
        status = "OK"
    return {
        "status": status,
        "base": base or LIVE_BASE,
        "max_checks": n,
        "checked": len([c for c in checks if c["status"] != "skipped"]),
        "blocked": sum(1 for c in checks if c["status"] == "blocked"),
        "live_also_at_cap": sum(1 for c in checks if c["status"] == "at_cap"),
        "checks": checks,
    }


# --------------------------------------------------------------------------- report
def build_truncation_report(pages_jsonl: str, live: bool = False,
                            live_n: int = DEFAULT_LIVE_N,
                            live_timeout: float = 40.0,
                            live_tries: int = 3,
                            live_base: str = None) -> dict:
    """گزارش رسمی‌سازی سقف ۲۰۰۰ کاراکتر (قطعی؛ شبکه فقط با live=True)."""
    census_ = census(pages_jsonl)
    pages_list = at_cap_pages(pages_jsonl)
    report = {
        "mission": MISSION,
        "contract": CONTRACT,
        "source": {
            "pages_jsonl": pages_jsonl,
            "pages_sha256": (C.sha256_file(pages_jsonl)
                             if os.path.exists(pages_jsonl) else None),
        },
        "cap": {
            "source_char_cap": S.SOURCE_CHAR_CAP,
            "where": "source-side (API chunk-detail / شاخص RAG سایت)",
            "gate": "PCM-20.5 GATE 1.5",
            "evidence": {
                "path_rel": S.GATE_1_5_EVIDENCE_REL,
                "sha256": S.GATE_1_5_EVIDENCE_SHA,
            },
            "statement_fa": (
                "سقف ۲۰۰۰ کاراکتری از سمت منبع است (سایت/شاخص RAG آن)؛ "
                "هیچ حلقه‌ای از pipeline (Export/Crawl/Crawler/Factory) متن را "
                "قطع نمی‌کند (شواهد E1-E4 در سند GATE 1.5). factory این "
                "صفحات را با پرچم truncated_at_2000 علامت می‌زند و حذف نمی‌کند؛ "
                "بخش فراتر از ۲۰۰۰ قابل بازیابی نیست چون منبع بستر آن را "
                "در chunk خود ذخیره نمی‌کند."),
            "formalized_in": [
                "corpus/tasnim/schema.py:SOURCE_CHAR_CAP (ثابت واحد)",
                "corpus/tasnim/validate.py:V09 (flag ⟺ len(text)==2000)",
                "corpus/tasnim/semantic.py:build_semantic_v3 (semantic.truncation)",
            ],
        },
        "census": census_,
        "affected_pages": pages_list,
        "by_volume": by_volume(pages_list),
        "live_recheck": None,
    }
    if live:
        report["live_recheck"] = live_recheck(
            pages_jsonl, n=live_n, base=live_base,
            timeout=live_timeout, tries=live_tries)

    c = census_
    lr = report.get("live_recheck")
    summary = [
        "سقف ۲۰۰۰ کاراکتری سمت منبع است (GATE 1.5: PASS) — رسمی‌سازی‌شده در "
        "SOURCE_CHAR_CAP + V09 + semantic.truncation.",
        "صفحات دقیقاً در سقف: %d از %d (%.2f%%)؛ فراسقف: %d."
        % (c["at_cap_count"], c["total_pages"],
           100.0 * c["at_cap_count"] / c["total_pages"] if c["total_pages"]
           else 0.0, c["over_cap_count"]),
    ]
    if lr is not None:
        if lr["status"] == "OK":
            summary.append(
                "بازبینی زنده: %d صفحه — %d بار دیگر دقیقاً %d کاراکتر "
                "(تأیید مستقل سقف سمت‌منبع)."
                % (lr["checked"], lr["live_also_at_cap"], S.SOURCE_CHAR_CAP))
        elif lr["status"] == "BLOCKED":
            summary.append(
                "بازبینی زنده: BLOCKED — سایت دسترس‌پذیر نبود. نتیجه‌ی GATE 1.5 "
                "مستقل از این بازبینی برقرار است (شواهد E1-E4 در PCM-20.4).")
        else:
            summary.append("بازبینی زنده: %s." % lr["status"])
    report["summary_fa"] = summary

    # قطعی بودن: SHA فقط روی «هسته‌ی قطعی» — بدون live_recheck و بدون
    # summary_fa (چون یک خط آن به نتیجه‌ی زنده وابسته است)
    core = {k: v for k, v in report.items()
            if k not in ("live_recheck", "summary_fa")}
    report["content_sha256"] = C.sha256_text(
        C.canonical_json(core).decode("utf-8"))
    report["generated_at"] = C.now_utc()
    return report


def write_truncation_report(report: dict, out_path: str) -> str:
    d = os.path.dirname(out_path)
    if d:
        os.makedirs(d, exist_ok=True)
    C.write_bytes(out_path, C.canonical_json(report))
    return out_path


def main(argv=None) -> int:
    """CLI مستقیم: truncation-report."""
    import argparse
    C.force_utf8_stdio()
    ap = argparse.ArgumentParser(prog="truncation-report")
    ap.add_argument("--pages", required=True,
                    help="pages.jsonl یک build پیکره")
    ap.add_argument("--out", required=True)
    ap.add_argument("--live", action="store_true",
                    help="بازبینی زنده‌ی <=3 صفحه (read-only GET)")
    ap.add_argument("--n-live", type=int, default=DEFAULT_LIVE_N)
    ap.add_argument("--timeout", type=float, default=40.0)
    ap.add_argument("--tries", type=int, default=3)
    ap.add_argument("--base", default=None,
                    help="پیشوند URL (فقط برای تست؛ پیش‌فرض endpoint رسمی)")
    args = ap.parse_args(argv)
    report = build_truncation_report(args.pages, live=args.live,
                                     live_n=args.n_live,
                                     live_timeout=args.timeout,
                                     live_tries=args.tries,
                                     live_base=args.base)
    write_truncation_report(report, args.out)
    print("=== TRUNCATION REPORT (PCM-20.6 D3) ===")
    print("cap         : %d (source-side, GATE 1.5)" % S.SOURCE_CHAR_CAP)
    print("census      : at-cap=%d over-cap=%d total=%d"
          % (report["census"]["at_cap_count"],
             report["census"]["over_cap_count"],
             report["census"]["total_pages"]))
    lr = report.get("live_recheck")
    print("live recheck: %s" % (lr["status"] if lr else "not run"))
    print("by volume   : %s" % report["by_volume"])
    print("content sha : %s" % report["content_sha256"])
    print("out         : %s" % args.out)
    for line in report["summary_fa"]:
        print("  %s" % line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

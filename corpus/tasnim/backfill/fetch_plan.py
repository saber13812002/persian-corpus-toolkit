# -*- coding: utf-8 -*-
"""tasnim.backfill.fetch_plan — برنامه‌ی Fetch + نرخ/بودجه (PCM-20.6.3).

وظیفه:
    * تبدیل گزارش شکاف (gap-report-2) به **برنامه‌ی مرتب Fetch**:
      فهرست item_indexهای مفقود در ترتیب صعودی (ترتیب crawl اصلی)،
      هر کدام با URL قطعیِ endpoint اثبات‌شده.
    * محاسبه‌ی نرخ/بودجه: target ≤ ~4 صفحه/دقیقه (نرخ مشاهده‌شده در
      PCM-20.5) با jitter قطعی (مبنای SHA، نه random زمان‌بسته)، timeout،
      budget هر اجرا و تخمین زمان کل.

قواعد:
    * **هیچ درخواستی در این ماژول انجام نمی‌شود** — فقط محاسبات قطعی.
      transport واقعی در `runner.py` پشت یک interface تزریق‌شونده است.
    * endpoint ثابت: `chunk-detail` API — همان endpointی که در
      PCM-20.5 GATE 1.5 / PCM-20.6 D2/D3 پاسخ زنده داده است. مسیر
      `/payload` دیگر SPA shell برمی‌گرداند و استفاده نمی‌شود.
"""
from __future__ import annotations

import hashlib

from .. import common as C

# endpoint اثبات‌شده (read-only) — PCM-20.5 GATE 1.5 (E4)، PCM-20.6 D2/D3
LIVE_BASE = "https://tasnim.hamtaa.org/api/v1/files/tasnim/chunk-detail?item_index="

# نرخ هدف: 4 صفحه/دقیقه (نرخ مشاهده‌شده در crawl اصلی PCM-20)
TARGET_PAGES_PER_MINUTE = 4.0
# فاصله‌ی پایه بین درخواست‌ها (ثانیه) = 60/4 = 15 ثانیه؛ jitter ±30٪
BASE_DELAY_SECONDS = 60.0 / TARGET_PAGES_PER_MINUTE
JITTER_FRACTION = 0.30
DEFAULT_TIMEOUT_SECONDS = 40.0
DEFAULT_MAX_ATTEMPTS = 3          # هر item: حداکثر 3 تلاش
DEFAULT_RETRY_BASE_SECONDS = 30.0  # backoff: 30s → 90s → (بعدش permanent)
DEFAULT_UA = "pct-tasnim-backfill/1.0 (read-only; corpus repair; contact: saber@ismc.ir)"


# --------------------------------------------------------------------------- urls
def url_for_item_index(item_index: int) -> str:
    """URL قطعیِ endpoint chunk-detail برای یک item_index."""
    return LIVE_BASE + str(int(item_index))


def parse_item_index_from_url(url: str):
    """معکوس‌سازی: item_index از URL (برای cross-check و provenance)."""
    return C.parse_item_index_from_url(url)


# --------------------------------------------------------------------------- plan
def build_fetch_plan(gap_report: dict,
                     max_requests_per_run: int = 500,
                     base_delay: float = BASE_DELAY_SECONDS,
                     jitter_fraction: float = JITTER_FRACTION,
                     timeout: float = DEFAULT_TIMEOUT_SECONDS,
                     max_attempts: int = DEFAULT_MAX_ATTEMPTS,
                     retry_base: float = DEFAULT_RETRY_BASE_SECONDS,
                     user_agent: str = DEFAULT_UA) -> dict:
    """برنامه‌ی Fetch مرتب از گزارش شکاف.

    خروجی قطعی است (بدون شبکه/زمان): ترتیب = item_index صعودی؛
    jitter با seed SHA (قطعی) محاسبه می‌شود تا اجراهای tکراری/تقسیم‌شده
    هم‌نظم بمانند، ولی ترافیک یک‌دست نباشد.
    """
    runs = gap_report["gaps"]["runs"]
    missing = gap_report["gaps"]["missing_count"]
    items = []
    for d in runs:
        for i in range(d["start"], d["end"] + 1):
            url = url_for_item_index(i)
            # jitter قطعی: [1-f, 1+f] با seed از item_index
            h = hashlib.sha256(("%d" % i).encode("utf-8")).digest()
            frac = int.from_bytes(h[:4], "big") / float(1 << 32)  # 0..1
            delay = base_delay * (1.0 + jitter_fraction * (2.0 * frac - 1.0))
            items.append({
                "item_index": i,
                "url": url,
                "run_start": d["start"],
                "run_end": d["end"],
                "planned_delay_seconds": round(delay, 3),
            })
    items.sort(key=lambda x: x["item_index"])

    per_min = 60.0 / base_delay if base_delay > 0 else 0.0
    total_minutes = (len(items) * base_delay) / 60.0
    n_runs = (len(items) + max_requests_per_run - 1) // max_requests_per_run if items else 0
    plan = {
        "contract": "fetch-plan-1",
        "source": {
            "gap_report_sha256": gap_report.get("content_sha256"),
            "gap_pages_sha256": (gap_report.get("source") or {}).get("pages_sha256"),
        },
        "endpoint": LIVE_BASE,
        "rate": {
            "target_pages_per_minute": per_min,
            "base_delay_seconds": base_delay,
            "jitter_fraction": jitter_fraction,
            "timeout_seconds": timeout,
            "user_agent": user_agent,
            "retry": {
                "max_attempts": max_attempts,
                "backoff_base_seconds": retry_base,
                "backoff_factor": 3,
            },
            "budget_per_run": max_requests_per_run,
        },
        "totals": {
            "missing": missing,
            "planned_requests": len(items),
            "runs_count": gap_report["gaps"]["runs_count"],
            "estimated_minutes_at_target": round(total_minutes, 1),
            "estimated_hours_at_target": round(total_minutes / 60.0, 1),
            "estimated_runs_at_budget": n_runs,
        },
        "items": items,
    }
    if plan["totals"]["planned_requests"] != missing:
        raise ValueError("plan count mismatch: %d != %d"
                         % (plan["totals"]["planned_requests"], missing))
    return plan


def split_plan(plan: dict, run_index: int,
               budget_per_run: int = None) -> list:
    """یک «جعبه‌ی» قابل‌اجرا از plan: run_index (0-based) × budget.

    خروجی = فهرست آیتم‌ها (سریع‌ترین: صرفاً slice روی ترتیب صعودی).
    برای اجراهای tکراری: هر آیتم فقط در یک run تعلق دارد → resume
    روی checkpoint کافی است.
    """
    budget = budget_per_run or plan["rate"]["budget_per_run"]
    items = plan["items"]
    lo = run_index * budget
    hi = lo + budget
    return items[lo:hi]


def plan_summary_fa(plan: dict) -> list:
    t = plan["totals"]
    return [
        "برنامه‌ی Fetch: %d درخواست در %d بازه؛ ترتیب صعودی item_index."
        % (t["planned_requests"], t["runs_count"]),
        "نرخ هدف: %g صفحه/دقیقه (فاصله‌ی پایه %g ثانیه، jitter ±%g%%)."
        % (plan["rate"]["target_pages_per_minute"],
           plan["rate"]["base_delay_seconds"],
           plan["rate"]["jitter_fraction"] * 100.0),
        "بودجه‌ی هر اجرا: %d درخواست → حدود %d اجرا برای تکمیل."
        % (plan["rate"]["budget_per_run"], t["estimated_runs_at_budget"]),
        "زمان تخمینی کل: %g ساعت (≈ %g روز) در نرخ هدف."
        % (t["estimated_hours_at_target"],
           t["estimated_hours_at_target"] / 24.0),
    ]

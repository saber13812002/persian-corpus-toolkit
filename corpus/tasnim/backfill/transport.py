# -*- coding: utf-8 -*-
"""tasnim.backfill.transport — interface شبکه + transport‌های قابل‌تزریق (PCM-20.6.3).

interface (کنتراکت):
    transport.get(url: str, user_agent: str, timeout: float)
        → {"status": int, "body_text": str}

    * status = کد HTTP (200/404/5xx/...)
    * body_text = متن بدنه (برای 404 ممکن است "" باشد)
    * خطا (timeout/DNS/TLS) به‌صورت exception از get برمی‌گردد → runner
      آن را «شکست موقتی» (retry) می‌شمارد؛ 404 = شکست دائمی (نه retry).

Transport‌ها:
    * FakeTransport  — قطعی، بدون شبکه: پاسخ‌های ازپیش‌تعیین‌شده (canned)
      keyed بر item_index. **تنها transport مجاز در تست‌ها و dry-run.**
    * LiveTransport  — urllib (فقط‌خواندن). **فقط** وقتی guard CLI عبور
      کرده باشد (‒‒allow-live AND BACKFILL_APPROVED) ساخته می‌شود.
"""
from __future__ import annotations

import urllib.request


class TransportError(Exception):
    """شکست موقتِ شبکه (timeout/DNS/TLS) — قابل retry با backoff."""


class TransportGuardError(RuntimeError):
    """ساخت LiveTransport بدون عبور guard (‒‒allow-live + BACKFILL_APPROVED)."""


def live_guard(allow_live: bool, approved_token) -> None:
    """guard سختِ درخواست زنده.

    هر دو شرط لازم:
      1. allow_live=True (‒‒allow-live در CLI)
      2. approved_token == "approved" (معمولا‌ً از env BACKFILL_APPROVED)
    هرچه کمتر → TransportGuardError (قبل از هر درخواست).
    """
    if not allow_live:
        raise TransportGuardError(
            "live transport requires --allow-live flag")
    if approved_token != "approved":
        raise TransportGuardError(
            "live transport requires BACKFILL_APPROVED=approved env token")


# --------------------------------------------------------------------------- fake
class FakeTransport:
    """transport قطعی و بدون شبکه (تست + dry-run).

    responses: {item_index: {"status": int, "body_text": str} | str}
        * dict  → مستقیم؛ str → body با status 200.
    default:   رفتار برای item_indexهای بدون entry (default 404).
    log:       فهرست URLهای درخواست‌شده (برای assert در تست).
    """

    def __init__(self, responses: dict = None, default_status: int = 404):
        self.responses = dict(responses or {})
        self.default_status = default_status
        self.log = []

    def add(self, item_index: int, body: str) -> None:
        """افزودن پاسخ 200 برای یک item_index."""
        self.responses[item_index] = {"status": 200, "body_text": body}

    def add_status(self, item_index: int, status: int, body: str = "") -> None:
        self.responses[item_index] = {"status": status, "body_text": body}

    def get(self, url: str, user_agent: str = None, timeout: float = None) -> dict:
        self.log.append({"url": url, "user_agent": user_agent})
        from . import fetch_plan as FP
        idx = FP.parse_item_index_from_url(url)
        r = self.responses.get(idx) if idx is not None else None
        if r is None:
            r = {"status": self.default_status, "body_text": ""}
        if isinstance(r, str):
            r = {"status": 200, "body_text": r}
        return {"status": r["status"], "body_text": r.get("body_text", "")}


# --------------------------------------------------------------------------- live
class LiveTransport:
    """urllib GET فقط‌خواندن (ساخت آن خود پشت guard است)."""

    def __init__(self, user_agent: str, timeout: float,
                 allow_live: bool, approved_token):
        live_guard(allow_live, approved_token)
        self.user_agent = user_agent
        self.timeout = timeout

    def get(self, url: str, user_agent: str = None, timeout: float = None) -> dict:
        req = urllib.request.Request(
            url, headers={"User-Agent": user_agent or self.user_agent})
        try:
            with urllib.request.urlopen(req,
                                        timeout=timeout or self.timeout) as r:
                body = r.read().decode("utf-8", errors="replace")
                return {"status": r.status, "body_text": body}
        except urllib.error.HTTPError as e:
            # 404 و بقیه‌ی کدهای HTTP → status (بدون exception)
            try:
                body = e.read().decode("utf-8", errors="replace")
            except Exception:
                body = ""
            return {"status": e.code, "body_text": body}
        except Exception as e:
            raise TransportError("%s: %s" % (type(e).__name__, e))

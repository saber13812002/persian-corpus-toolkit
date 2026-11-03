# -*- coding: utf-8 -*-
"""tasnim.normalize — سیاست‌های نرمال‌سازی متن (PCM-20.3).

قاعده‌ی خانه: سیاست نرمال‌سازی باید **ثبت‌شده** باشد (policy_id در manifest) و
خروجی NORMALIZED همیشه قابل بازسازی از RAW + policy است. RAW هرگز تغییر
نمی‌کند (قاعده‌ی «هیچ داده‌ای را قربانی ساده‌سازی Pipeline نکن»).

سیاست‌ها:
  * tasnim-p1-ascii-digits  (پیش‌فرض):
      - حذف ZWNJ؟ خیر — پیمایش بدون حذف (محتوا حفظ می‌شود).
      - ارقام فارسی/عربی → ASCII
      - فاصله‌های سفید فاصله‌های متوالی → یک فاصله
      - strip ابتدایی/انتهای خط
  * none : دست‌نخورده (مقایسه‌ای).
"""
from __future__ import annotations

from . import common as C

POLICY_DEFAULT = "tasnim-p1-ascii-digits"
POLICY_NONE = "none"

POLICIES = {
    POLICY_DEFAULT: {
        "id": POLICY_DEFAULT,
        "description": "digits→ASCII + collapse whitespace + strip (بدون حذف ZWNJ/محتوا)",
        "steps": ["ascii_digits", "collapse_ws", "strip"],
    },
    POLICY_NONE: {
        "id": POLICY_NONE,
        "description": "دست‌نخورده (RAW == NORMALIZED)",
        "steps": [],
    },
}


def _collapse_ws(text: str) -> str:
    return " ".join(text.split())


def normalize_text(text: str, policy_id: str = POLICY_DEFAULT) -> str:
    """نرمال‌سازی متن مطابق policy (بدون خطا برای ورودی None → "")."""
    if text is None:
        return ""
    if policy_id == POLICY_NONE:
        return text
    if policy_id != POLICY_DEFAULT:
        raise ValueError("unknown policy: %r" % policy_id)
    t = C.to_ascii_digits(text)
    t = _collapse_ws(t)
    return t.strip()


def policy_spec(policy_id: str) -> dict:
    if policy_id not in POLICIES:
        raise ValueError("unknown policy: %r" % policy_id)
    return dict(POLICIES[policy_id])

# -*- coding: utf-8 -*-
"""tasnim.common — ابزارهای مشترک و قطعی خط تولید تسنیم (PCM-20.3).

مهارت‌ها:
  * فقط کتابخانه‌ی استاندارد (بدون pip) — سازگار با Python 3.8+.
  * همه‌ی توابع قطعی هستند: همان ورودی → همان خروجی (بدون زمان/تصادف).
  * سریالیزه‌ی JSON «canonical»: کلیدها مرتب، UTF-8، پایان خط LF — مبنای SHAها.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import unicodedata
from urllib.parse import parse_qs, urlparse

# ---- کلیدهای فارسیِ رکوردهای منبع (با code point تا متن کد گلیف‌محور نشود) ----
BARG_KEY = "\u0628\u0631\u06af"   # «برگ»
TEXT_KEY = "\u0645\u062A\u0646"   # «متن»

# ارقام فارسی U+06F0..U+06F9 + عربی-هندی U+0660..U+0669 → ASCII
_DIGIT_MAP = {}
for _i in range(10):
    _DIGIT_MAP[chr(0x06F0 + _i)] = str(_i)
    _DIGIT_MAP[chr(0x0660 + _i)] = str(_i)

DIGITS_RE = re.compile(r"\d+")
# «جلد 12» / «جلد (12)» / «جلد(12)» — روی متنِ بعد از to_ascii_digits اعمال می‌شود
VOL_LABEL_RE = re.compile(r"جلد\s*\(?\s*(\d+)\s*\)?")
# عدد آخرِ section (مثلا «تفسیر تسنیم جلد (80)») — همان تعریف PCM-20.2
SECTION_TAIL_RE = re.compile(r"(\d+)\s*\)?$")


def force_utf8_stdio() -> None:
    """Windows/terminal safety: stdout/stderr → UTF-8 (replace)."""
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


# --------------------------------------------------------------------------- digits
def to_ascii_digits(value: str) -> str:
    """ارقام فارسی/عربی → ASCII؛ بقیه‌ی کاراکترها دست‌نخورده."""
    return "".join(_DIGIT_MAP.get(c, c) for c in value)


def parse_barg_all_runs(raw):
    """بازپارسِ صحیح «برگ» (اصلاح PCM-20.2): همه‌ی ریک‌های ارقام، بعد از
    نرمال‌سازی ارقام، با چسباندن — یعنی جداکننده‌های هزارگان (٬ , / -)
    بی‌اثر می‌شوند.

    `parse_barg` اسکریپت خروجی PCM-20 فقط اولین ریک را می‌گرفت؛ برای اعداد
    >= 1000 (نمونه‌ی واقعی «۳۹٬۰۰۵» → خروجی 39) مقدار نادرست برمی‌گشت.
    این تابع مرجع رسمی است: None فقط اگر اصلاً رقمی نباشد.
    """
    if raw is None:
        return None
    runs = DIGITS_RE.findall(to_ascii_digits(str(raw)))
    if not runs:
        return None
    try:
        return int("".join(runs))
    except ValueError:
        return None


# --------------------------------------------------------------------------- urls
def parse_item_index_from_url(url: str):
    """item_index از query-string URL (همان تعریف خروجی PCM-20)."""
    qs = parse_qs(urlparse(url or "").query)
    raw = (qs.get("item_index") or [""])[0].strip()
    return int(raw) if raw.isdigit() else None


def section_of_url(url: str) -> str:
    """مقدار پارامتر section در URL ("" اگر نبود)."""
    qs = parse_qs(urlparse(url or "").query)
    return (qs.get("section") or [""])[0].strip()


def volume_no_from_section(section: str):
    """شماره‌ی جلد از برچسب section (عدد آخر)؛ None اگر نبود/نامشخص بود."""
    s = to_ascii_digits(section or "")
    if not s:
        return None
    m = SECTION_TAIL_RE.search(s)
    return int(m.group(1)) if m else None


def volume_no_from_text(text: str):
    """شماره‌ی جلد از متن (الگوی پیش‌فرض «جلد N» روی متن ارقام‌نرمال‌شده)."""
    m = VOL_LABEL_RE.search(to_ascii_digits(text or ""))
    return int(m.group(1)) if m else None


# --------------------------------------------------------------------------- hashes / io
def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


def sha256_file(path: str, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def file_size(path: str) -> int:
    return os.path.getsize(path)


def read_json(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def read_jsonl(path: str) -> list:
    out = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def canonical_json(obj) -> bytes:
    """سریالیزه‌ی قطعی JSON: کلیدها مرتب، UTF-8، indent ثابت + پایان‌خط LF.

    مبنای SHA-256 همه‌ی فایل‌های JSON در این خط تولید است.
    """
    return (json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=1) + "\n").encode("utf-8")


def canonical_json_line(obj) -> bytes:
    """یک خط JSONL قطعی (کلیدها مرتب، UTF-8)."""
    return (json.dumps(obj, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")


def write_bytes(path: str, data: bytes) -> None:
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)


def write_jsonl(path: str, records) -> None:
    with open(path, "wb") as f:
        for r in records:
            f.write(canonical_json_line(r))


def write_json(path: str, obj) -> None:
    write_bytes(path, canonical_json(obj))


# --------------------------------------------------------------------------- stats
def runs(sorted_numbers) -> list:
    """بازه‌های پیوسته [lo, hi] از اعداد مرتب‌شده."""
    out = []
    for n in sorted_numbers:
        if out and n == out[-1][1] + 1:
            out[-1][1] = n
        else:
            out.append([n, n])
    return [tuple(r) for r in out]


def gap_stats(numbers) -> dict:
    """آمار پیوستگی: count/min/max/distinct/missing/dup (Noneها حذف می‌شوند)."""
    numbers = [n for n in numbers if n is not None]
    if not numbers:
        return {"count": 0, "min": None, "max": None, "distinct": 0,
                "missing_count": 0, "missing_runs": [], "dup_count": 0}
    present = sorted(set(numbers))
    lo, hi = present[0], present[-1]
    missing = sorted(set(range(lo, hi + 1)) - set(present))
    return {
        "count": len(numbers),
        "min": lo,
        "max": hi,
        "distinct": len(present),
        "missing_count": len(missing),
        "missing_runs": [list(r) for r in runs(missing)],
        "dup_count": len(numbers) - len(present),
    }


def percentile(sorted_values, pct):
    """درصده از آرایه‌ی مرتب (خطی، round به int) — تعریف گزارش‌های PCM-20.x."""
    if not sorted_values:
        return None
    if len(sorted_values) == 1:
        return sorted_values[0]
    k = (len(sorted_values) - 1) * pct / 100.0
    f = int(k)
    c = min(f + 1, len(sorted_values) - 1)
    if f == c:
        return sorted_values[f]
    return int(round(sorted_values[f] + (sorted_values[c] - sorted_values[f]) * (k - f)))


def text_histogram(lens) -> dict:
    """توزیع طول متن در سدهای مکتوب (برای گزارش کیفیت)."""
    h = {"0_empty": 0, "1_19": 0, "20_99": 0, "100_499": 0, "500_1999": 0,
         "2000_exact": 0, "gt_2000": 0}
    for n in lens:
        if n == 0:
            h["0_empty"] += 1
        elif n < 20:
            h["1_19"] += 1
        elif n < 100:
            h["20_99"] += 1
        elif n < 500:
            h["100_499"] += 1
        elif n < 2000:
            h["500_1999"] += 1
        elif n == 2000:
            h["2000_exact"] += 1
        else:
            h["gt_2000"] += 1
    return h


# --------------------------------------------------------------------------- misc
def slugify_latin(text: str, max_len: int = 48) -> str:
    """کد لاتین ایمن برای dap_code/اسم دایرکتوری: فقط [a-z0-9_]."""
    s = unicodedata.normalize("NFKD", str(text))
    s = s.encode("ascii", "ignore").decode("ascii").lower()
    s = re.sub(r"[^a-z0-9_]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s[:max_len] or "x"


def now_utc() -> str:
    """زمان UTC با دقت ثانیه (فقط برای fieldهای created_at در manifest؛
    خارج از محاسبه‌ی content_sha256 است)."""
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def words_count(text: str) -> int:
    return len((text or "").split())

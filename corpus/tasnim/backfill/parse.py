# -*- coding: utf-8 -*-
"""tasnim.backfill.parse — ساخت رکورد Backfill + شواهد و flags (PCM-20.6.3).

وظیفه:
    * پارس پاسخ endpoint `chunk-detail` (JSON: `original_text`, `section`,
      و اختیاری `values.برگ`/`item_index`) و cross-check با URL.
    * استخراج `item_index` از URL (و پاسخ) + cross-check.
    * نسبت‌دادن به جلد **فقط با شواهد** (section در URL ← الگوی «جلد N»
      در متن ← همسایه‌های موجود) + flag ابهام؛ هیچ تخمینی صورت نمی‌گیرد.
    * پارس `barg` **فقط** با parser اصلاح‌شده‌ی مرجع
      `common.parse_barg_all_runs` (باگ `parse_barg` قدیمی PCM-20: فقط
      اولین ریک ارقام — «۳۹٬۰۰۵» → 39 به‌جای 39005).
    * SHA-256 متن + تشخیص تکرار (item_index موجود در base) + تشخیص
      تغییر محتوا (تفاوت SHA متن با رکورد base).

قواعد:
    * این ماژول **بدون شبکه** است و قطعی (بدون زمان/تصادف در خروجی‌های
      کلیدی؛ `fetched_at` فقط provenance است).
    * هیچ رکورد base دست‌نخورده می‌ماند (read-only).
"""
from __future__ import annotations

import bisect
import hashlib
import json

from .. import common as C
from .. import reconcile as R
from .. import schema as S

PARSER_VERSION = "backfill-parse/1"
POLICY_VERSION = "bf-2"

# وضعیت‌های نسبت‌دادن جلد
VOL_RESOLVED = "resolved"        # دقیقاً یک شواهد سازگار
VOL_AMBIGUOUS = "ambiguous"      # بیش از یک volume_no متفاوت
VOL_UNRESOLVED = "unresolved"    # هیچ شواهدی


class ParseError(ValueError):
    """پارس نامعتبر (بدنه‌ی غیر-JSON، field حیاتی خالی، item_index ناسازگار)."""


# --------------------------------------------------------------------------- response
def parse_chunk_detail(body_text: str, url: str) -> dict:
    """پارس پاسخ `chunk-detail` + cross-check با URL.

    برگشت: {"text", "section", "raw_barg", "payload_item_index",
            "payload_sha256", "parse_error": None|str}
    اگر بدنه JSON نباشد یا `original_text` نباشد → ParseError.
    """
    try:
        data = json.loads(body_text)
    except (ValueError, TypeError) as e:
        raise ParseError("response is not JSON: %s" % e)
    if not isinstance(data, dict):
        raise ParseError("response JSON is not an object")
    text = data.get("original_text")
    if not isinstance(text, str):
        raise ParseError("original_text missing or not a string")
    section = data.get("section")
    if isinstance(section, str):
        section = section.strip() or None
    else:
        section = None
    # item_index در پاسخ (اختیاری) — اگر بود، باید با URL یکی باشد
    pidx = data.get("item_index")
    if pidx is not None and (not isinstance(pidx, int)
                             or isinstance(pidx, bool)):
        raise ParseError("payload item_index not an int: %r" % (pidx,))
    # cross-check با item_index در URL
    url_idx = C.parse_item_index_from_url(url)
    if pidx is not None and url_idx is not None and pidx != url_idx:
        raise ParseError("item_index mismatch: url=%s payload=%s"
                         % (url_idx, pidx))
    # raw barg (اختیاری — ممکن است API «برگ» را فرستاده باشد)
    values = data.get("values") or {}
    raw_barg = values.get(S.BARG_KEY) if isinstance(values, dict) else None
    return {
        "text": text,
        "section": section,
        "raw_barg": raw_barg,
        "payload_item_index": pidx,
        "payload_sha256": C.sha256_text(C.canonical_json(data).decode("utf-8")),
        "parse_error": None,
    }


def extract_item_index(url: str, payload_item_index=None):
    """item_index معتبر از URL (و اختیاری از payload — باید یکی باشند)."""
    idx = C.parse_item_index_from_url(url)
    if idx is None:
        raise ParseError("no valid item_index in url: %r" % (url,))
    if payload_item_index is not None and payload_item_index != idx:
        raise ParseError("item_index mismatch: url=%s payload=%s"
                         % (idx, payload_item_index))
    return idx


# --------------------------------------------------------------------------- volume
def volume_candidates(url: str, text: str, section: str = None,
                      vol_map: dict = None, item_index: int = None,
                      present_sorted: list = None) -> dict:
    """نسبت‌دادن به جلد **فقط با شواهد** + flag ابهام.

    شواهد (به ترتیب اولویت ثبت):
      1. `payload_section` — field `section` در پاسخ chunk-detail (برچسب
        رسمی سایت برای همین chunk — معتبرترین؛ endpoint فعلی section را
        در URL ندارد و در payload می‌فرستد).
      2. `url_section` — پارامتر `section` در URL (ساختار legacy /payload).
      3. `text` — الگوی «جلد N» در متن صفحه.
      4. `neighbor` — جلد همسایه‌های موجودِ item_index (فقط راهنما؛
        در فهرست شواهد قرار نمی‌گیرد).
    نتیجه:
      * `resolved`   — دقیقاً یک volume_no از شواهد (یا همه‌ی شواهد
        موجود روی یک عدد یکی‌اند).
      * `ambiguous`  — بیش از یک volume_no متفاوت در شواهد → هرگز
        انتخاب نمی‌شود؛ همه‌ی گزینه‌ها ثبت می‌شوند برای تصمیم بعدی.
      * `unresolved` — هیچ شواهد رقم‌دار نبود.
    """
    cands = []
    vol_map = vol_map or {}
    present_sorted = present_sorted or []
    if item_index is None:
        item_index = C.parse_item_index_from_url(url)

    vol_payload = C.volume_no_from_section(section) if section else None
    if vol_payload is not None:
        cands.append({"volume_no": vol_payload,
                      "evidence": "payload_section", "section": section})

    section_url = C.section_of_url(url) or None
    vol_url = C.volume_no_from_section(section_url) if section_url else None
    if vol_url is not None and \
            not any(c["volume_no"] == vol_url
                    for c in cands):
        cands.append({"volume_no": vol_url, "evidence": "url_section",
                      "section": section_url})

    vol_text = C.volume_no_from_text(text)
    if vol_text is not None and \
            not any(c["volume_no"] == vol_text for c in cands):
        cands.append({"volume_no": vol_text, "evidence": "text"})

    # همسایه‌های موجود (راهنما — weight پایین‌تر؛ فقط با item_index)
    neighbors = {}
    if item_index is not None:
        j = bisect.bisect_left(present_sorted, item_index)
        if j > 0:
            b = present_sorted[j - 1]
            if b in vol_map and vol_map[b][0] is not None:
                neighbors["before"] = {"item_index": b,
                                       "volume_no": vol_map[b][0]}
        k = bisect.bisect_right(present_sorted, item_index)
        if k < len(present_sorted):
            a = present_sorted[k]
            if a in vol_map and vol_map[a][0] is not None:
                neighbors["after"] = {"item_index": a,
                                      "volume_no": vol_map[a][0]}

    distinct = sorted({c["volume_no"] for c in cands})
    if len(distinct) == 0:
        status = VOL_UNRESOLVED
        volume_no = None
    elif len(distinct) == 1:
        status = VOL_RESOLVED
        volume_no = distinct[0]
    else:
        status = VOL_AMBIGUOUS
        volume_no = None
    return {
        "status": status,
        "volume_no": volume_no,
        "candidates": cands,
        "neighbors": neighbors,
        "ambiguous": status == VOL_AMBIGUOUS,
    }


# --------------------------------------------------------------------------- quality / change
def quality_flags(text: str, barg: int, item_index=None,
                  dup_in_base: bool = False) -> list:
    """flags کیفیت — همان ترتیب خط تولید (reconcile.quality_flags)."""
    flags = []
    if text == "":
        flags.append(S.F_EMPTY)
    elif len(text) < R.MIN_TEXT_CHARS:
        flags.append(S.F_SHORT)
    if len(text) == S.SOURCE_CHAR_CAP:
        flags.append(S.F_TRUNCATED_2000)
    if barg is None:
        flags.append(S.F_NO_BARG)
    if item_index is None:
        flags.append(S.F_MISSING_INDEX)
    if dup_in_base:
        flags.append(S.F_DUP_INDEX)
    return flags


def text_sha(text: str) -> str:
    """SHA-256 متن (UTF-8) — مبنای تشخیص تغییر/تکرار."""
    return C.sha256_text(text)


def classify_change(fetched_text_sha: str,
                    base_text_sha, base_present: bool) -> str:
    """تشخیص وضعیت محتوا نسبت به base.

    * base_present=False → "new"
    * برابر SHA → "unchanged"
    * متفاوت → "changed" (سیاست **old-wins**: رکورد base برتر است؛
      رکورد backfill فقط ثبت می‌شود، هرگز جایگزین نمی‌کند).
    """
    if not base_present:
        return "new"
    if base_text_sha is None:
        return "changed"
    return "unchanged" if fetched_text_sha == base_text_sha else "changed"


# --------------------------------------------------------------------------- record
def build_backfill_record(item_index: int, url: str, http_status: int,
                          parsed: dict, fetched_at: str,
                          attempts: int, base_index: dict,
                          vol_map: dict, present_sorted: list) -> dict:
    """ساخت رکورد Backfill کامل (قرارداد JSONL — ر.ک. DESIGN §7).

    base_index: ورودی dict از base برای همین item_index:
        {"present": bool, "dup_in_base": bool, "base_text_sha": str|None,
         "base_page_ids": [...], "base_content_hash": str|None}
    """
    text = parsed["text"]
    tsha = text_sha(text)
    barg = C.parse_barg_all_runs(parsed.get("raw_barg"))  # parser اصلاح‌شده
    vol = volume_candidates(url, text, parsed.get("section"),
                            vol_map, item_index, present_sorted)
    dup_in_base = bool(base_index.get("dup_in_base"))
    flags = quality_flags(text, barg, item_index, dup_in_base=dup_in_base)
    change = classify_change(tsha, base_index.get("base_text_sha"),
                             base_index.get("present", False))
    rec = {
        "item_index": item_index,
        "url": url,
        "fetched_at": fetched_at,
        "http_status": http_status,
        "attempts": attempts,
        "text": text,
        "text_sha256": tsha,
        "text_len": len(text),
        "section": parsed.get("section"),
        "raw_barg": parsed.get("raw_barg"),
        "barg": barg,
        "barg_parse": "ok" if parsed.get("raw_barg") is not None
                      and barg is not None else ("no_barg"
                                                 if parsed.get("raw_barg") is None
                                                 else "unparseable"),
        "payload_item_index": parsed.get("payload_item_index"),
        "payload_sha256": parsed.get("payload_sha256"),
        "volume": vol,
        "quality_flags": flags,
        "base_state": {
            "present_in_base": bool(base_index.get("present", False)),
            "dup_in_base": dup_in_base,
            "base_page_ids": list(base_index.get("base_page_ids") or []),
            "base_content_hash": base_index.get("base_content_hash"),
        },
        "change": change,
        "parser_version": PARSER_VERSION,
        "policy_version": POLICY_VERSION,
    }
    return rec

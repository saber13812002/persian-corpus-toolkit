# -*- coding: utf-8 -*-
"""tasnim.schema — پیکره‌ی رسمی (Canonical Corpus) تسنیم + شناسه‌های قطعی.

سلسله‌مراتب (مأموریت PCM-20.3 §2):
    Work  →  Edition  →  Volume  →  Page

قواعد:
  * همه‌ی شناسه‌ها قطعی هستند (تابعی از داده، نه از زمان/ترتیب فیزیکی فایل).
  * `item_index` و `barg` دو فیلد جدا: item_index = موقعیت کراول در URL؛
    barg = شماره‌ی برگ چاپی (از متن raw، با بازپارس همه‌ی ریک‌های ارقام).
  * RAW (`text`) و NORMALIZED (`text_normalized`) همیشه جدا نگهداری می‌شوند.
  * هر Page به رکورد production بازمی‌گردد (source_page_id + content_hash + url).
  * هیچ رکوردی حذف نمی‌شود؛ رکوردهای ناقص/کوتاه با quality_status ثبت می‌شوند.
"""
from __future__ import annotations

import hashlib

from . import common as C

# کلیدهای فارسیِ values در رکوردهای منبع (میراث از common — قرارداد فیلد)
BARG_KEY = C.BARG_KEY
TEXT_KEY = C.TEXT_KEY

WORK = "tasnim_hamta"              # شناسه‌ی اثر (ثابت برای این خط تولید)
EDITION = "hamta-2026"             # ویرایش منبع (خروجی کراول PCM-20 از tasnim.hamtaa.org)
WORK_NAME = "تفسیر تسنیم"
SOURCE_LABEL = "tasnim.hamtaa.org (کراول PCT، پروژه‌ی 2 — PCM-20)"

SCHEMA_VERSION = "c-20.3"

# ---- استراتژی‌های شناسایی جلد (به ترتیب اولویت) ----
STRATEGY_URL_SECTION = "url_section"     # پارامتر section در URL (رقم آخر)
STRATEGY_TEXT = "text"                   # الگوی «جلد N» در متن صفحه
STRATEGY_NONE = "none"                   # هیچ‌کدام — جلد نامعلوم (page در «جلد نامشخص»)

DEFAULT_VOL_LABEL = "نامشخص"

# ---- flags کیفیت (هیچ‌کدام رکورد را حذف نمی‌کنند) ----
F_OK = "ok"
F_EMPTY = "empty"                      # متن خالی/غیرمتنی
F_SHORT = "short"                      # 1..19 کاراکتر (زیر min_text_chars Builder = 20)
F_TRUNCATED_2000 = "truncated_at_2000"  # len==2000 (اشتباه به‌نظر می‌رسد؛ NOT VERIFIED)
F_DUP_INDEX = "dup_item_index"         # item_index تکراری بین رکوردها
F_NO_BARG = "no_barg"                  # «برگ» بدون رقم (raw وجود دارد ولی ارقمی نیست)
F_MISSING_INDEX = "missing_item_index"  # item_index در URL نیست/نامعتبر

FLAGS_ALL = (F_EMPTY, F_SHORT, F_TRUNCATED_2000, F_DUP_INDEX, F_NO_BARG, F_MISSING_INDEX)


def _h8(obj) -> str:
    return hashlib.sha256(C.canonical_json(obj)).hexdigest()[:8]


# --------------------------------------------------------------------------- Work
def make_work() -> dict:
    return {
        "work_id": WORK,
        "work_name": WORK_NAME,
        "source": SOURCE_LABEL,
        "description": ("تفسیر تسنیم — مجموعه‌ی تفاسیر قرآن بر اساس روایات؛ "
                        "مستند در tasnim.hamtaa.org. کراول با PCT (پروژه‌ی 2) "
                        "و خروجی PCM-20."),
    }


# --------------------------------------------------------------------------- Edition
def make_edition(work: dict, source_manifest_meta: dict) -> dict:
    meta = source_manifest_meta or {}
    return {
        "edition_id": "%s__%s" % (work["work_id"], EDITION),
        "work_id": work["work_id"],
        "edition_name": "خروجی کراول %s" % EDITION,
        "source_version": (
            "export sha256=%s | jsonl sha256=%s" % (
                meta.get("source_manifest_sha256") or "?",
                meta.get("jsonl_sha256") or "?",
            )),
        "exported_at_utc": meta.get("exported_at_utc"),
        "page_count_source": meta.get("page_count"),
    }


# --------------------------------------------------------------------------- Volumes
def make_volume(edition_id: str, volume_no, label: str, key: dict,
                strategy: str, page_count: int,
                item_index_span: tuple, barg_span: tuple) -> dict:
    """volume_no: int یا None (جلد نامشخص → volume_id قطعی از کلید گروه)."""
    if volume_no is None:
        vol_id = "%s__volkey%s" % (edition_id, _h8(key))
    else:
        vol_id = "%s__vol%03d" % (edition_id, volume_no)
    return {
        "volume_id": vol_id,
        "edition_id": edition_id,
        "volume_no": volume_no,
        "volume_title": label,
        "source_section": key.get("section"),
        "page_count": page_count,
        "item_index_span": [item_index_span[0], item_index_span[1]] if item_index_span else None,
        "barg_span": [barg_span[0], barg_span[1]] if barg_span else None,
        "volume_strategy": strategy,
    }


def unknown_volume_key() -> dict:
    return {"section": None, "vol": None}


def _span(nums):
    nums = [n for n in nums if n is not None]
    if not nums:
        return None
    return (min(nums), max(nums))


# --------------------------------------------------------------------------- Pages
def page_id_of(volume_id: str, item_index, dup_rank: int = 0) -> str:
    """شناسه‌ی قطعی صفحه در پیکره:
       - صفحات با item_index:  <volume_id>__p<item_index>  (+ __d<n> برای ردیف‌های تکراری)
       - بدون item_index:      <volume_id>__pkey<sha8(values)>
    """
    base = "%s__p%d" % (volume_id, item_index) if item_index is not None else None
    if base is None:
        base = "%s__pkey%s" % (volume_id, _h8({"k": "noindex"}))
    if dup_rank:
        base = "%s__d%d" % (base, dup_rank)
    return base


def make_page(volume_id: str, item_index, dup_rank: int, page: dict,
              barg: int, raw_barg, text: str, text_norm: str,
              quality_flags: list) -> dict:
    values = page.get("values") or {}
    meta = {
        "barg_raw": raw_barg,
        "url": page.get("url"),
        "content_hash": page.get("content_hash"),
        "captured_at": page.get("captured_at"),
        "item_index": item_index,
        "export_barg": page.get("barg"),
        "section": C.section_of_url(page.get("url") or ""),
        "values_keys": sorted(values.keys()),
    }
    return {
        "page_id": page_id_of(volume_id, item_index, dup_rank),
        "volume_id": volume_id,
        "item_index": item_index,
        "barg": barg,
        "raw_barg": raw_barg,
        "text": text,                       # RAW — دست‌نخورده از خروجی PCM-20
        "text_normalized": text_norm,       # NORMALIZED — مطابق سیاست ثبت‌شده در manifest
        "url": page.get("url"),
        "captured_at": page.get("captured_at"),
        "content_hash": page.get("content_hash"),
        "source_page_id": page.get("page_id"),   # traceability → project_pages.id در s52
        "quality_status": {
            "status": F_OK if not quality_flags else quality_flags[0],
            "flags": quality_flags,
        },
        "metadata": meta,
    }


# --------------------------------------------------------------------------- assembly
def assign_volume(page: dict, text: str, strategies) -> dict:
    """استخراج کلید جلد + استراتژی از یک رکورد.

    برمی‌گرداند {"vol": int|None, "section": str|None, "strategy": str}.
    ترتیب: 1) section در URL (اگر رقم داشت) 2) الگوی متن 3) نامشخص.
    """
    url = page.get("url") or ""
    section = C.section_of_url(url) or None
    vol = C.volume_no_from_section(section) if section else None
    if vol is not None:
        return {"vol": vol, "section": section, "strategy": STRATEGY_URL_SECTION}
    vol = C.volume_no_from_text(text)
    if vol is not None:
        return {"vol": vol, "section": section, "strategy": STRATEGY_TEXT}
    return {"vol": None, "section": section, "strategy": STRATEGY_NONE}

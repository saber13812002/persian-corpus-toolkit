"""factory.metadata — MetadataExtractor (stage 6: کتاب‌شناسی extract-only).

قانون extract-only (Master Prompt PRD §4.3):
- فقط از محتوای فایل (core properties + front matter)؛ هیچ حدس از نام فایل
  به‌عنوان «محتوای کتاب» (volume فقط از front matter).
- هر فیلد: value + source_ref + confidence. اگر نبود → value=None + flag=absent.
- هیچ فیلدی اختراع نمی‌شود.
"""
from __future__ import annotations

import re

from .models import DocumentMetadata, FieldValue

# فیلدهای core-properties (python-docx core_properties) → نام منطقی
_CORE_FIELDS = {
    "title": ("title", "core-properties", 0.9),
    "author": ("author", "core-properties", 0.9),
    "subject": ("subject", "core-properties", 0.8),
    "keywords": ("keywords", "core-properties", 0.8),
    "last_modified_by": ("last_modified_by", "core-properties", 0.6),
    "comments": ("description", "core-properties", 0.6),
    "category": ("category", "core-properties", 0.5),
}

# patterns front matter (extract-only از متن ۱۰ بلوک اول)
_FRONT_PATTERNS = {
    "title": re.compile(r"^(?:عنوان|Title)\s*[:：]\s*(.+)$", re.I | re.M),
    "author": re.compile(r"^(?:نویسنده|آثار|Author)\s*[:：]\s*(.+)$", re.I | re.M),
    "publisher": re.compile(r"^(?:ناشر|انتشارات|Publisher)\s*[:：]\s*(.+)$", re.I | re.M),
    "publish_year": re.compile(r"^(?:سال(?:\s+انتشار)?|انتشار|Year)\s*[:：]\s*(.+)$", re.I | re.M),
}
_VOLUME_RE = re.compile(r"(?:جلد|جلد\s*شماره|Volume)\s*[:：]?\s*([0-9۰-۹]+|یک|دو|سه|چهار|پنج|شش)", re.I)
_FA_NUM = {"یک": 1, "دو": 2, "سه": 3, "چهار": 4, "پنج": 5, "شش": 6,
           "۱": 1, "۲": 2, "۳": 3, "۴": 4, "۵": 5, "۶": 6}


def _vol_no(raw: str):
    raw = raw.strip()
    if raw in _FA_NUM:
        return _FA_NUM[raw]
    digits = re.sub(r"[^0-9۰-۹]", "", raw)
    if digits:
        try:
            return int(digits.translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")))
        except ValueError:
            return None
    return None


class MetadataExtractor:
    """extract-only؛ خروجی DocumentMetadata با confidence هر فیلد."""

    def extract(self, doc, blocks: list) -> DocumentMetadata:
        meta = DocumentMetadata()
        cp = doc.core_properties

        for attr, (name, src, conf) in _CORE_FIELDS.items():
            try:
                val = getattr(cp, attr, None)
            except Exception:
                val = None
            if val is not None:
                val = str(val).strip() or None
            meta.fields[name] = FieldValue(
                value=val, source_ref=src, confidence=conf if val else 0.0)

        # front matter: فقط ۱۰ بلوک اول
        front_text = "\n".join(b.raw_text for b in blocks[:10])
        for name, pat in _FRONT_PATTERNS.items():
            if name in meta.fields and meta.fields[name].value:
                continue  # core properties اولویت دارد
            m = pat.search(front_text)
            if m:
                meta.fields[name] = FieldValue(
                    value=m.group(1).strip(),
                    source_ref="frontmatter", confidence=0.7)

        # volume: فقط از front matter (نه از نام فایل)
        mv = _VOLUME_RE.search(front_text)
        if mv:
            no = _vol_no(mv.group(1))
            if no:
                meta.volume_no = no
                meta.volume_source = "book-frontmatter"

        # فیلدهای غایب را صریح absent علامت بزن (برای report شفاف)
        for name in ("title", "author", "publisher", "publish_year"):
            if name not in meta.fields:
                meta.fields[name] = FieldValue(
                    value=None, source_ref="absent", confidence=0.0)
        return meta

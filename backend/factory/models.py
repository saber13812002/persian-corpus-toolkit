"""factory.models — مدل داده درون‌حافظه‌ای خط لوله Word Factory (V0.1).

لایه‌های داده (اصل حفظ داده خام):
  RAW         : متن دقیق‌الکلمه از فایل
  NORMALIZED  : نسخه‌ی استانداردشده (norm_version)
  ENRICHED    : در V0.1 تولید نمی‌شود (LLM ممنوع)

هر Block هم‌زمان raw و normalized را حمل می‌کند تا خروجی `blocks.jsonl`
تک‌فایل و قابل اعتبارسنجی بماند (تسلسل با DATA-CONTRACTS §2:
`page` فقط اگر معتبر — در docx موتور رندر تعیین می‌کند → همیشه null).
"""
from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Optional

PARSER_VERSION = "p-1"
NORM_VERSION = "n-1"
MANIFEST_VERSION = "m-2"      # m-2 (PCM-14C.3): norm_policy کامل + blocks_hash + factory_version
SCHEMA_VERSION = "wf-schema-1"
FACTORY_VERSION = "0.1"       # نسخهٔ خط لولهٔ Word Factory (CLI/manifest)

BLOCK_TYPES = (
    "heading", "paragraph", "table", "footnote", "endnote",
    "pagebreak", "image", "empty", "list_item",
)


def content_hash(text: str) -> str:
    """sha256 کوتاه (16 hex) — برای idempotency و dedup."""
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _sha8(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:8]


@dataclass
class Block:
    """یک بلوک ساختاریافته از سند."""
    block_index: int
    type: str                      # یکی از BLOCK_TYPES
    raw_text: str
    normalized_text: str = ""
    style: Optional[str] = None            # نام style در docx (Heading1, Normal, ...)
    heading_level: Optional[int] = None    # 1..9 فقط برای heading
    parent_block_id: Optional[str] = None  # block_id تیتر والد (None = سطح سند)
    table_rows: Optional[list] = None      # فقط برای table: list[list[str]]
    ref_id: Optional[str] = None           # fn-3 / en-2 برای footnote/endnote
    source_ref: dict = field(default_factory=dict)  # {section, page: None, ...}
    page: Optional[int] = None             # همیشه None در docx (حدس ممنوع)
    norm_stats: dict = field(default_factory=dict)  # شمارش اعمال هر قانون norm
    warnings: list = field(default_factory=list)

    @property
    def block_id(self) -> str:
        # deterministic: index + type + hash raw
        return f"b{self.block_index:05d}:{self.type}"

    def raw_record(self) -> dict:
        rec = {
            "block_id": self.block_id,
            "block_index": self.block_index,
            "type": self.type,
            "raw_text": self.raw_text,
            "style": self.style,
            "parent_block_id": self.parent_block_id,
            "position": self.block_index,
            "source_ref": self.source_ref or None,
            "page": None,  # docx → شماره صفحه بدون مبنای معتبر (حدس ممنوع)
        }
        if self.type == "table":
            rec["table_rows"] = self.table_rows
        if self.ref_id:
            rec["ref_id"] = self.ref_id
        return rec

    def normalized_record(self) -> dict:
        return {
            "block_id": self.block_id,
            "block_index": self.block_index,
            "norm_version": NORM_VERSION,
            "normalized_text": self.normalized_text,
        }

    def unified_record(self) -> dict:
        """یک رکورد ترکیبی برای blocks.jsonl (raw + normalized + قرارداد)."""
        rec = self.raw_record()
        rec["normalized_text"] = self.normalized_text
        rec["norm_version"] = NORM_VERSION
        rec["content_hash"] = content_hash(self.normalized_text)
        if self.warnings:
            rec["warnings"] = list(self.warnings)
        return rec


@dataclass
class FileRecord:
    """stage 1 — دریافت فایل (DocumentIntakeService)."""
    file_id: str
    filename: str
    path: str
    size_bytes: int
    sha256: str
    format: str                    # docx | doc | unknown
    detected_by: str               # magic-zip | magic-ole2 | extension-fallback
    created_at: str

    def to_dict(self) -> dict:
        return {
            "file_id": self.file_id,
            "filename": self.filename,
            "size_bytes": self.size_bytes,
            "sha256": self.sha256,
            "format": self.format,
            "detected_by": self.detected_by,
            "created_at": self.created_at,
        }


@dataclass
class FieldValue:
    """یک فیلد کتاب‌شناختی با confidence (extract-only — حدس ممنوع)."""
    value: Optional[str]
    source_ref: str                # core-properties | frontmatter | absent
    confidence: float              # 0..1

    def to_dict(self) -> dict:
        if self.value is None:
            return {"value": None, "source_ref": self.source_ref,
                    "confidence": 0.0, "flag": "absent"}
        return {"value": self.value, "source_ref": self.source_ref,
                "confidence": self.confidence}


@dataclass
class DocumentMetadata:
    """stage 6 — metadata استخراج‌شده (extract-only)."""
    fields: dict[str, FieldValue] = field(default_factory=dict)
    volume_no: Optional[int] = None
    volume_source: str = "absent"   # book-frontmatter | filename | absent

    def to_dict(self) -> dict:
        return {
            "fields": {k: v.to_dict() for k, v in self.fields.items()},
            "volume": self.volume_no,
            "volume_source": self.volume_source,
        }


@dataclass
class StructureTree:
    """stage 5 — سلسله‌مراتب تیترها."""
    headings: list[dict] = field(default_factory=list)   # {block_id, level, text, parent}
    chapters: list[dict] = field(default_factory=list)   # level-1 sections
    front_matter_blocks: int = 0
    total_blocks: int = 0
    confidence: float = 1.0
    notes: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "headings": self.headings,
            "chapters": self.chapters,
            "front_matter_blocks": self.front_matter_blocks,
            "total_blocks": self.total_blocks,
            "confidence": self.confidence,
            "notes": self.notes,
        }


@dataclass
class QualityReport:
    """stage 8 — گزارش کیفیت (خروجی quality-report.json)."""
    passed: bool
    score: float
    status: str                    # ok | manual_review | failed
    checks: list[dict] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)
    unextracted: dict = field(default_factory=dict)   # footnotes/links/images...
    warnings: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "score": self.score,
            "status": self.status,
            "checks": self.checks,
            "metrics": self.metrics,
            "unextracted": self.unextracted,
            "warnings": self.warnings,
        }


@dataclass
class ProcessedDocument:
    """نتیجه‌ی کامل پردازش یک فایل."""
    file: FileRecord
    blocks: list[Block]
    structure: StructureTree
    metadata: DocumentMetadata
    quality: QualityReport
    work_id: str
    edition_id: str
    volume_id: Optional[str]
    parser_version: str = PARSER_VERSION
    norm_version: str = NORM_VERSION
    normalizer_policy: Optional[dict] = None  # m-2: نگاشت کامل سیاست نرمال‌سازی
    started_at: str = ""
    finished_at: str = ""
    duration_ms: int = 0

    @property
    def total_chars(self) -> int:
        return sum(len(b.raw_text) for b in self.blocks)

    def blocks_hash(self) -> str:
        """hash مجموع خروجی بلوک‌ها — برای WF-10 (idempotency)."""
        h = hashlib.sha256()
        for b in self.blocks:
            h.update(b.unified_record().__repr__().encode("utf-8", "replace"))
        return h.hexdigest()


def utc_now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def short_id(prefix: str, key: str) -> str:
    """'f-<sha8>' deterministic مطابق DATA-CONTRACTS §1.1."""
    return f"{prefix}-{hashlib.sha256(key.encode('utf-8')).hexdigest()[:8]}"

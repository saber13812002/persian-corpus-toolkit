"""factory.validator — FileValidator (stage 3: اعتبارسنجی بازپذیری + حد حجم).

ورودی: FileRecord (از intake). خروجی: ValidationResult.
- checksum ثانی (sha256 مجددا‌ محاسبه می‌شود — WF-08)
- بازپذیری با python-docx (بدون اجرای محتوای مخرب — فقط خواندن XML)
- حد حجم قابل‌تنظیم
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .errors import ValidationFailedError
from .intake import sha256_file
from .models import FileRecord

DEFAULT_MAX_BYTES = 200 * (1 << 20)  # 200MB — حد محافظتی


@dataclass
class ValidationOutcome:
    ok: bool
    reasons: list = field(default_factory=list)
    sha256_verified: bool = False
    size_bytes: int = 0
    paragraphs_seen: Optional[int] = None


class FileValidator:
    def __init__(self, max_bytes: int = DEFAULT_MAX_BYTES):
        self.max_bytes = max_bytes

    def validate(self, rec: FileRecord) -> ValidationOutcome:
        reasons = []
        outcome = ValidationOutcome(ok=False, reasons=reasons)

        # 1) حد حجم
        if rec.size_bytes > self.max_bytes:
            reasons.append(f"file_too_large: {rec.size_bytes} > {self.max_bytes}")

        # 2) checksum ثانی
        try:
            actual = sha256_file(rec.path)
            outcome.sha256_verified = (actual == rec.sha256)
            if not outcome.sha256_verified:
                reasons.append("sha256_mismatch")
        except OSError as e:
            reasons.append(f"unreadable: {e}")

        # 3) بازپذیری (lazy import — python-docx فقط اینجا و در parser لازم است)
        try:
            from docx import Document
            doc = Document(rec.path)
            outcome.paragraphs_seen = len(doc.paragraphs)
        except Exception as e:  # BadZipFile, KeyError, ParseError...
            reasons.append(f"not_openable: {type(e).__name__}: {e}")

        outcome.size_bytes = rec.size_bytes
        outcome.ok = not reasons
        if not outcome.ok:
            rec._validation = outcome  # type: ignore[attr-defined]
            raise ValidationFailedError(
                "اعتبارسنجی فایل ناموفق بود", reasons=reasons)
        rec._validation = outcome  # type: ignore[attr-defined]
        return outcome

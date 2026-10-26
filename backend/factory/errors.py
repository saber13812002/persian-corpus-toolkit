"""factory.errors — استثنائهای خط لوله Word Factory (V0.1).

هر خطا یک `code` پایدار دارد (برای quality-report و manifest).
"""
from __future__ import annotations

FACTORY_ERROR_VERSION = "e-1"


class FactoryError(Exception):
    """ریشه‌ی تمام خطاهای factory."""

    code = "factory_error"

    def __init__(self, message: str, **details):
        super().__init__(message)
        self.message = message
        self.details = details

    def to_dict(self) -> dict:
        return {"code": self.code, "message": self.message, "details": self.details}


class IntakeError(FactoryError):
    code = "intake_error"


class FileMissingError(IntakeError):
    code = "file_missing"


class FormatDetectionError(FactoryError):
    code = "format_detection_error"


class UnsupportedFormatError(FactoryError):
    """فرمت شناخته‌شده ولی بدون parser معتبر (مثلا‌ .doc قدیمی).

    مهم: این خطا برای .doc باید به‌جای تلاش برای بازشدن به‌عنوان docx برود.
    """

    code = "unsupported_format"

    def __init__(self, message: str, format: str, **details):
        super().__init__(message, **details)
        self.format = format


class ValidationFailedError(FactoryError):
    code = "validation_failed"

    def __init__(self, message: str, reasons: list, **details):
        super().__init__(message, **details)
        self.reasons = reasons


class ParseError(FactoryError):
    code = "parse_error"


class QualityCheckFailed(FactoryError):
    """quality score زیر threshold — processing ادامه می‌یابد اما status=manual_review."""

    code = "quality_check_failed"

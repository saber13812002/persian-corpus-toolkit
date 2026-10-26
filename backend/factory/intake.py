"""factory.intake — DocumentIntakeService (stage 1: دریافت فایل + شناسایی فرمت).

قواعد:
- فرمت با **magic bytes** تشخیص داده می‌شود، نه صرفا‌ پسوند (قاعده WF-03:
  `.doc` قدیمی هرگز نباید به‌عنوان docx فرض شود).
- SHA-256 کل فایل ثبت می‌شود (WF-08).
- فایل در فضای ایزوله (out_dir/files) کپی می‌شود؛ ورودی اصلی دست‌نخورده می‌ماند
  (قاعده PCM-13: خطای پردازش به فایل اصلی آسیب نمی‌زند).
"""
from __future__ import annotations

import hashlib
import os
import shutil
import zipfile

from .errors import (FileMissingError, FormatDetectionError,
                     UnsupportedFormatError, ValidationFailedError)
from .models import FileRecord, short_id, utc_now_iso

ZIP_MAGIC = b"PK\x03\x04"
OLE2_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"

DOCX_REQUIRED_PARTS = ("[Content_Types].xml", "word/document.xml")


def detect_format(path: str) -> tuple[str, str]:
    """بازگشت (format, detected_by).

    format ∈ {'docx', 'doc', 'unknown'}
    """
    with open(path, "rb") as f:
        head = f.read(64)
    if not head:
        return "unknown", "empty-file"
    if head[:4] == ZIP_MAGIC:
        # باید واقعی docx باشد؛ zip عمومی (مثلا‌ عکس فشرده) رد می‌شود
        try:
            with zipfile.ZipFile(path) as zf:
                names = set(zf.namelist())
        except zipfile.BadZipFile:
            return "unknown", "bad-zip"
        if all(p in names for p in DOCX_REQUIRED_PARTS):
            return "docx", "magic-zip"
        return "unknown", "zip-not-docx"
    if head[:8] == OLE2_MAGIC:
        return "doc", "magic-ole2"
    return "unknown", "magic-miss"


def sha256_file(path: str, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


class DocumentIntakeService:
    """دریافت فایل ورودی → FileRecord در فضای ایزوله."""

    def __init__(self, out_dir: str):
        self.out_dir = os.path.abspath(out_dir)
        self.files_dir = os.path.join(self.out_dir, "files")

    def intake(self, src_path: str) -> FileRecord:
        if not os.path.isfile(src_path):
            raise FileMissingError(f"فایل ورودی پیدا نشد: {src_path}")
        size = os.path.getsize(src_path)
        if size == 0:
            raise ValidationFailedError("فایل خالی (0 بایت) است", reasons=["empty_file"])

        fmt, how = detect_format(src_path)
        if fmt == "doc":
            raise UnsupportedFormatError(
                "فایل .doc (OLE2 قدیمی) تشخیص داده شد؛ parser معتبر در V0.1 نیست. "
                "با تبدیل به .docx (مثلا‌ LibreOffice headless) دوباره تلاش کنید.",
                format="doc", detected_by=how)
        if fmt != "docx":
            raise FormatDetectionError(
                "فرمت فایل قابل تشخیص نیست (نه docx معتبر، نه doc شناخته‌شده).",
                detected_by=how, extension=os.path.splitext(src_path)[1])

        os.makedirs(self.files_dir, exist_ok=True)
        sha = sha256_file(src_path)
        file_id = short_id("f", sha)
        dst = os.path.join(self.files_dir, f"{file_id}{os.path.splitext(src_path)[1] or '.docx'}")
        if not os.path.exists(dst):
            shutil.copy2(src_path, dst)

        return FileRecord(
            file_id=file_id,
            filename=os.path.basename(src_path),
            path=dst,
            size_bytes=size,
            sha256=sha,
            format="docx",
            detected_by=how,
            created_at=utc_now_iso(),
        )

"""factory.cli — رابط اجرای محلی Word Factory (V0.1).

استفاده:
    cd backend
    python -m factory.cli path/to/book.docx --out ./wf-out
    python -m factory.cli book.docx --out ./wf-out --digits persian --threshold 0.7

خروجی: ./wf-out/<file_id>/{manifest.json, document.json, blocks.jsonl,
                                  quality-report.json, report.md}
کد خروجی: 0=done · 1=failed/quality-review · 2=unsupported-format · 3=usage

قاعده: فقط فایل تکیِ داده‌شده؛ هیچ مانیتور/انبارداری خودکار پوشه‌ای نیست.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_UNSUPPORTED = 2
EXIT_USAGE = 3


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m factory.cli",
        description="Word Factory V0.1 — Word → JSONL ساختاریافته (ایزوله، بدون DB/LLM/ES)")
    p.add_argument("input", help="مسیر فایل Word ورودی (.docx)")
    p.add_argument("--out", default="./wf-out",
                   help="پوشه‌ی خروجی (پیش‌فرض: ./wf-out) — زیرمجموعه‌ای از آن برای file_id ساخته می‌شود")
    p.add_argument("--digits", choices=["keep", "persian", "ascii"], default="keep",
                   help="سیاست ارقام نرمال‌سازی (پیش‌فرض: keep — بدون تغییر)")
    p.add_argument("--threshold", type=float, default=0.6,
                   help="threshold کیفیت برای ok (پیش‌فرض: 0.6)")
    p.add_argument("--max-mb", type=int, default=200,
                   help="سقف حجم فایل مگابایت (پیش‌فرض: 200)")
    p.add_argument("--no-zwnj", action="store_true", help="غیرفعال‌کردن قانون نیم‌فاصله")
    p.add_argument("--no-arabic", action="store_true",
                   help="غیرفعال‌کردن یکسان‌سازی عربی→فارسی")
    p.add_argument("--quiet", action="store_true", help="فقط مسیر خروجی را چاپ کند")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not os.path.isfile(args.input):
        print(f"خطا: فایل ورودی پیدا نشد: {args.input}", file=sys.stderr)
        return EXIT_USAGE

    from .errors import FactoryError, UnsupportedFormatError, ValidationFailedError
    from .normalize import NormalizationPolicy
    from .service import DocumentProcessingService

    policy = NormalizationPolicy(
        digits=args.digits,
        zwnj=not args.no_zwnj,
        arabic_to_persian=not args.no_arabic,
    )
    svc = DocumentProcessingService(
        out_dir=args.out,
        norm_policy=policy,
        quality_threshold=args.threshold,
        max_bytes=args.max_mb * (1 << 20),
    )

    try:
        doc = svc.process(args.input)
    except UnsupportedFormatError as e:
        print(f"نپشتیبانی‌شده ({e.code}): {e.message}", file=sys.stderr)
        return EXIT_UNSUPPORTED
    except ValidationFailedError as e:
        print(f"اعتبارسنجی ناموفق: {e.reasons}", file=sys.stderr)
        return EXIT_FAILED
    except FactoryError as e:
        print(f"خطای خط لوله ({e.code}): {e.message}", file=sys.stderr)
        return EXIT_FAILED

    if args.quiet:
        print(os.path.join(args.out, doc.file.file_id))
        return EXIT_OK if doc.quality.passed else EXIT_FAILED

    q = doc.quality
    print("=" * 64)
    print(f"Word Factory V0.1 — {doc.file.filename}")
    print(f"  file_id      : {doc.file.file_id}")
    print(f"  sha256       : {doc.file.sha256}")
    print(f"  blocks       : {len(doc.blocks)}  ({doc.total_chars:,} chars)")
    print(f"  work/edition : {doc.work_id} / {doc.edition_id}")
    print(f"  quality      : {q.status}  (score={q.score})")
    for c in q.checks:
        print(f"    [{'ok' if c['ok'] else 'NG'}] {c['name']}  {c['detail']}")
    if q.unextracted["losses"]:
        print(f"  unextracted  : {q.unextracted['losses']}")
    out = os.path.join(args.out, doc.file.file_id)
    print(f"  outputs      : {out}")
    print("    - manifest.json  document.json  blocks.jsonl")
    print("    - quality-report.json  report.md")
    print("=" * 64)
    return EXIT_OK if q.passed else EXIT_FAILED


if __name__ == "__main__":
    sys.exit(main())

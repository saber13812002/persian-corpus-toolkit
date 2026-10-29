"""factory.cli — رابط اجرای محلی Word Factory (V0.1).

پردازش (رفتار سنتی — بدون تغییر):
    cd backend
    python -m factory.cli path/to/book.docx --out ./wf-out
    python -m factory.cli book.docx --out ./wf-out --digits persian --threshold 0.7

خروجی: ./wf-out/<file_id>/{manifest.json, document.json, blocks.jsonl,
                              quality-report.json, report.md}
کد خروجی: 0=done · 1=failed/quality-review · 2=unsupported-format · 3=usage

Dump (PCM-14C.3 — قرارداد d-1، بدون DB/ES/شبکه):
    python -m factory.cli make-dump ./wf-out/<file_id> --dump-dir ./book-dump \
        [--input book.docx] [--json]
    python -m factory.cli validate-dump ./book-dump [--json]
    python -m factory.cli dump-summary ./book-dump [--json]
کد خروجی دامپ: 0=معتبر/ساخت‌شده · 1=نامعتبر/خطا · 3=usage

قاعده: فقط فایل تکیِ داده‌شده؛ هیچ مانیتور/انبارداری خودکار پوشه‌ای نیست.

Corpus (PCM-16 — قرارداد c-1، از Dumpهای معتبر d-1، بدون DB/ES/شبکه):
    python -m factory.cli build-corpus ./dump1 ./dump2 --out ./corpus \
        [--require-quality ok] [--json]
کد خروجی پیکره: 0=ساخت‌شده · 1=خطا/رد دامپ · 3=usage
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


def _dump_main(argv: list[str]) -> int:
    """Dispatch زیردستورات dump (PCM-14C.3)."""
    sub = argv[0]
    p = argparse.ArgumentParser(prog=f"python -m factory.cli {sub}")
    if sub == "make-dump":
        p.add_argument("wf_dir", help="دایرکتوری خروجی WF (حاوی manifest.json + 5 فایل)")
        p.add_argument("--dump-dir", required=True, help="مقصد Dump")
        p.add_argument("--input", default=None,
                       help="فایل docx اصلی — SHA-256 آن با مانیفست WF راستی‌آزمایی می‌شود")
        p.add_argument("--json", action="store_true", dest="as_json",
                       help="فقط dump-manifest.json را چاپ کند")
    elif sub == "build-corpus":
        p.add_argument("dumps", nargs="+", help="دایرکتوری‌های Dump معتبر (d-1)")
        p.add_argument("--out", required=True, help="مقصد پیکره")
        p.add_argument("--require-quality", choices=["ok"], default=None,
                       help="فقط دامپ‌های quality_status=ok")
        p.add_argument("--json", action="store_true", dest="as_json",
                       help="فقط corpus-manifest.json را چاپ کند")
    else:
        p.add_argument("dump_dir", help="دایرکتوری Dump")
        p.add_argument("--json", action="store_true", dest="as_json",
                       help="خروجی JSON (machine-readable)")
    args = p.parse_args(argv[1:])

    from .corpus import CorpusError, build_corpus
    from .dump import DumpError, dump_summary, generate_dump, validate_dump

    try:
        if sub == "make-dump":
            if not os.path.isdir(args.wf_dir):
                print(f"خطا: دایرکتوری WF پیدا نشد: {args.wf_dir}", file=sys.stderr)
                return EXIT_USAGE
            dm = generate_dump(args.wf_dir, args.dump_dir, source_docx=args.input)
            if args.as_json:
                print(json.dumps(dm, ensure_ascii=False, indent=2))
            else:
                print("=" * 64)
                print(f"Dump {dm['dump_contract_version']} — {dm['identifiers']['file_id']}")
                print(f"  title        : {dm['document'].get('title') or '(بدون تیتر)'}")
                print(f"  input sha256 : {dm['integrity']['input_sha256']} "
                      f"({dm['source']['input_file']['sha256_source']})")
                print(f"  blocks       : {dm['counts']['blocks']}")
                print(f"  quality      : {dm['quality'].get('quality_status')} "
                      f"(score={dm['quality'].get('score')})")
                print(f"  dump dir     : {os.path.abspath(args.dump_dir)}")
                print("    - dump-manifest.json + 5 فایل WF (SHA-256 ثبت‌شده)")
                print("=" * 64)
            return EXIT_OK
        if sub == "build-corpus":
            m = build_corpus(args.dumps, args.out,
                             require_quality=args.require_quality)
            if args.as_json:
                print(json.dumps(m, ensure_ascii=False, indent=2))
            else:
                c = m["counts"]
                print("=" * 64)
                print(f"Corpus {m['corpus_contract_version']} — "
                      f"{m['generator']}")
                print(f"  dumps        : {c['dumps']} (همه تاییدشده d-1)")
                print(f"  blocks       : {c['blocks_total']} "
                      f"(raw unique {c['blocks_unique_raw']}, "
                      f"norm unique {c['blocks_unique_normalized']})")
                print(f"  chars        : raw {c['raw_chars']:,} · "
                      f"norm {c['normalized_chars']:,}")
                print(f"  files        : " + ", ".join(
                    f['name'] for f in m['files']) + f" + {m['archive']['name']}")
                print(f"  out dir      : {os.path.abspath(args.out)}")
                print("=" * 64)
            return EXIT_OK
        if sub == "validate-dump":
            if not os.path.isdir(args.dump_dir):
                print(f"خطا: دایرکتوری Dump پیدا نشد: {args.dump_dir}", file=sys.stderr)
                return EXIT_USAGE
            ok, errors, warnings = validate_dump(args.dump_dir)
            if args.as_json:
                print(json.dumps({"valid": ok, "errors": errors,
                                  "warnings": warnings}, ensure_ascii=False, indent=2))
            else:
                print(f"dump: {args.dump_dir}")
                for e in errors:
                    print(f"  [NG] {e}")
                for w in warnings:
                    print(f"  [warn] {w}")
                print(f"  result: {'VALID' if ok else 'INVALID'} "
                      f"({len(errors)} error, {len(warnings)} warning)")
            return EXIT_OK if ok else EXIT_FAILED
        # dump-summary
        if not os.path.isdir(args.dump_dir):
            print(f"خطا: دایرکتوری Dump پیدا نشد: {args.dump_dir}", file=sys.stderr)
            return EXIT_USAGE
        s = dump_summary(args.dump_dir)
        if args.as_json:
            print(json.dumps(s, ensure_ascii=False, indent=2))
        else:
            d = s.get("document") or {}
            v = s.get("versions") or {}
            i = s.get("integrity") or {}
            print("=" * 64)
            print(f"Dump {s.get('contract')} — {s.get('generator')}")
            print(f"  valid        : {s['valid']}")
            print(f"  title        : {d.get('title') or '(بدون تیتر)'}")
            print(f"  file_id      : {(s.get('identifiers') or {}).get('file_id')}")
            print(f"  manifest     : {v.get('manifest')} · schema {v.get('schema')} "
                  f"· norm {v.get('normalizer')}")
            print(f"  blocks       : {(s.get('counts') or {}).get('blocks')}")
            print(f"  quality      : {(s.get('quality') or {}).get('quality_status')}")
            print(f"  input sha256 : {i.get('input_sha256')}")
            for e in s["errors"]:
                print(f"  [NG] {e}")
            for w in s["warnings"]:
                print(f"  [warn] {w}")
            print("=" * 64)
        return EXIT_OK if s["valid"] else EXIT_FAILED
    except (DumpError, CorpusError) as e:
        print(f"خطای Dump/Corpus ({e.code}): {e.message}", file=sys.stderr)
        return EXIT_FAILED


def main(argv: list[str] | None = None) -> int:
    # Windows: خروجی فارسی/JSON روی کنسول cp1252 نمی‌شود — UTF-8 قائل شو
    for _s in (sys.stdout, sys.stderr):
        if hasattr(_s, "reconfigure"):
            try:
                _s.reconfigure(encoding="utf-8")
            except (ValueError, OSError):
                pass
    if argv is None:
        argv = sys.argv[1:]
    if argv and argv[0] in ("make-dump", "validate-dump", "dump-summary",
                            "build-corpus"):
        return _dump_main(list(argv))
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

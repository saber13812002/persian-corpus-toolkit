# -*- coding: utf-8 -*-
"""tasnim.backfill.cli — CLI خط لوله‌ی Backfill (PCM-20.6.3).

subcommandها:
    gap-report   گزارش شکاف v0004 از pages.jsonl (gap-report-2)
    plan         برنامه‌ی Fetch از گزارش شکاف (fetch-plan-1)
    run          اجرای pipeline (فقط با transport تزریق‌شده در تست؛
                 اجرا روی شبکه فقط با --allow-live AND BACKFILL_APPROVED)
    verify       بازتأیید خروجی run (run-report + records + checkpoint)
    register     ثبت خروجی در registry + نوشتن manifest backfill

guard سخت (دفاع در عمق):
    هر مسیر که **LiveTransport** می‌سازد (فقط `run` بدون --fake-body)
    ابتدا `transport.live_guard(allow_live, approved_token)` را صدا می‌زند:
      1. flag `--allow-live`
      2. env `BACKFILL_APPROVED` == "approved"
    کمتر از هر دو → TransportGuardError → خروج 2 (بدون هیچ درخواست).

کدخروجی‌ها (همان قرارداد خط تولید):
    0 = موفق  1 = validation fail  2 = input/guard error
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from .. import common as C
from .. import manifest as M
from .. import versioning as V
from . import checkpoint as CK
from . import fetch_plan as FP
from . import gap as BG
from . import manifest as BM
from . import parse as P
from . import runner as RN
from . import transport as TR


def _emit(msg: str) -> None:
    print(msg)


def _fail(msg: str, code: int) -> int:
    print("ERROR: %s" % msg, file=sys.stderr)
    return code


# --------------------------------------------------------------------------- gap-report
def cmd_gap_report(args) -> int:
    try:
        report = BG.build_gap_report_v2(args.pages)
    except (FileNotFoundError, ValueError) as e:
        return _fail(str(e), 2)
    out = BG.write_gap_report_v2(report, args.out)
    _emit("=== BACKFILL GAP REPORT (PCM-20.6.3) ===")
    for line in report["summary_fa"]:
        _emit(line)
    _emit("content sha : %s" % report["content_sha256"])
    _emit("out         : %s" % out)
    return 0


# --------------------------------------------------------------------------- plan
def cmd_plan(args) -> int:
    if not os.path.exists(args.gap_report):
        return _fail("gap report not found: %s" % args.gap_report, 2)
    report = C.read_json(args.gap_report)
    try:
        plan = FP.build_fetch_plan(report,
                                   max_requests_per_run=args.budget,
                                   base_delay=args.delay,
                                   jitter_fraction=args.jitter,
                                   timeout=args.timeout,
                                   max_attempts=args.attempts)
    except (KeyError, ValueError) as e:
        return _fail("bad gap report: %s" % e, 2)
    out_path = args.out or os.path.join(
        os.path.dirname(os.path.abspath(args.gap_report)),
        "fetch-plan.json")
    C.write_json(out_path, plan)
    _emit("=== FETCH PLAN ===")
    for line in FP.plan_summary_fa(plan):
        _emit(line)
    _emit("plan sha    : %s" % RN.plan_sha_of(plan))
    _emit("out         : %s" % out_path)
    return 0


# --------------------------------------------------------------------------- run
def _resolve_transport(args, plan: dict):
    """transport برای run — guard سخت قبل از ساخت LiveTransport."""
    if args.fake_bodies:
        # حالت تست/dry-run محلی: پاسخ‌های ازپیش‌تعیین‌شده از فایل JSON
        # {item_index: body_text} — هیچ درخواست زنده‌ای نمی‌رود.
        bodies = C.read_json(args.fake_bodies)
        ft = TR.FakeTransport()
        for k, v in bodies.items():
            ft.add(int(k), v)
        return ft
    token = os.environ.get("BACKFILL_APPROVED", "")
    lt = TR.LiveTransport(user_agent=plan["rate"]["user_agent"],
                          timeout=plan["rate"]["timeout_seconds"],
                          allow_live=args.allow_live,
                          approved_token=token)
    return lt


def cmd_run(args) -> int:
    if not os.path.exists(args.plan):
        return _fail("plan not found: %s" % args.plan, 2)
    if not os.path.exists(args.base_pages):
        return _fail("base pages not found: %s" % args.base_pages, 2)
    plan = C.read_json(args.plan)
    if plan.get("contract") != "fetch-plan-1":
        return _fail("not a fetch-plan-1 file", 2)

    base = BM.base_index_from_pages(args.base_pages)
    vol_map = BG.volume_map_from_pages(args.base_pages)
    present = base["present_sorted"]

    # dry-run: درخواستی نمی‌رود → transport اصلاً لازم نیست (guard هم لازم نیست)
    if args.dry_run and not args.fake_bodies:
        transport = None
    else:
        try:
            transport = _resolve_transport(args, plan)
        except TR.TransportGuardError as e:
            return _fail("LIVE GUARD: %s" % e, 2)

    out_dir = args.out_dir or os.path.join(
        os.path.dirname(os.path.abspath(args.plan)), "run")
    budget = args.budget if args.budget is not None \
        else plan["rate"]["budget_per_run"]
    try:
        report = RN.run_pipeline(
            plan, base, vol_map, present, transport,
            out_dir=out_dir, budget=budget,
            dry_run=args.dry_run)
    except CK.CheckpointError as e:
        return _fail("checkpoint: %s" % e, 2)

    _emit("=== BACKFILL RUN %s ==="
          % ("(dry-run)" if args.dry_run else ""))
    _emit("budget used : %d" % report["counts"]["budget_used"])
    _emit("fetched     : %d" % report["counts"]["fetched"])
    _emit("permanent   : %d" % report["counts"]["permanent"])
    _emit("parse errs  : %d" % report["counts"]["parse_errors"])
    _emit("changes     : %s" % json.dumps(report["changes"]))
    _emit("pending left: %d" % report["pending_remaining"])
    _emit("out dir     : %s" % out_dir)
    return 0


# --------------------------------------------------------------------------- verify
def cmd_verify(args) -> int:
    if not os.path.exists(args.plan):
        return _fail("plan not found: %s" % args.plan, 2)
    plan = C.read_json(args.plan)
    out_dir = args.out_dir or os.path.join(
        os.path.dirname(os.path.abspath(args.plan)), "run")
    result = RN.verify_output(out_dir, plan,
                              base_pages_jsonl=args.base_pages)
    _emit("=== VERIFY ===")
    for e in result["errors"]:
        _emit("  ERROR: %s" % e)
    for w in result["warnings"]:
        _emit("  WARN: %s" % w)
    _emit("records     : %d" % result["records"])
    _emit("checkpoint  : %s" % json.dumps(result["checkpoint_counts"]))
    _emit("base sha    : %s" % result["base_pages_sha256"])
    _emit("verify      : %s" % ("PASS" if result["ok"] else "FAIL"))
    return 0 if result["ok"] else 1


# --------------------------------------------------------------------------- register
def cmd_register(args) -> int:
    if not os.path.exists(args.plan):
        return _fail("plan not found: %s" % args.plan, 2)
    if not os.path.exists(args.base):
        return _fail("base build dir not found: %s" % args.base, 2)
    plan = C.read_json(args.plan)
    base_manifest = M.load_manifest(args.base)

    # verify قبل از ثبت
    out_dir = args.out_dir or os.path.join(
        os.path.dirname(os.path.abspath(args.plan)), "run")
    result = RN.verify_output(out_dir, plan,
                              base_pages_jsonl=args.base_pages)
    if not result["ok"]:
        for e in result["errors"]:
            _fail("verify FAIL — ثبت نمی‌شود: %s" % e, 1)
        return 1

    # manifest خروجی: فایل‌های backfill + diff
    backfill_files = {}
    rec_p = os.path.join(out_dir, "backfill-records.jsonl")
    if os.path.exists(rec_p):
        backfill_files["backfill-records.jsonl"] = {
            "sha256": C.sha256_file(rec_p),
            "size_bytes": C.file_size(rec_p),
        }
    records = C.read_jsonl(rec_p) if os.path.exists(rec_p) else []
    diff = BM.build_diff(
        BM.base_index_from_pages(args.base_pages),
        records, plan_items=plan["items"])

    data_root = args.data_root
    out_tag = "v%04d" % args.version
    out_dir2 = os.path.join(data_root, "corpus", "builds", out_tag,
                            "backfill")
    os.makedirs(out_dir2, exist_ok=True)
    # رکوردها را در دایرکتوری نسخه‌ی پیکره کپی می‌کنیم (append-only)
    if os.path.exists(rec_p):
        with open(rec_p, "rb") as f:
            C.write_bytes(os.path.join(out_dir2, "backfill-records.jsonl"),
                          f.read())
    data = BM.backfill_manifest_data(
        base_manifest, args.base, data_root, out_dir2,
        {"backfill-records.jsonl": backfill_files[
            "backfill-records.jsonl"]} if backfill_files else {},
        diff, plan,
        C.read_json(os.path.join(out_dir, "run-report.json"))
        .get("permanent_failures", []),
        rollback_ready=True)
    manifest = BM.write_backfill_manifest(out_dir2, out_tag, data)
    entry = {
        "content_sha256": (base_manifest.get("data") or {})
                          .get("content_sha256"),
        "sha256": C.sha256_file(os.path.join(out_dir2, "manifest.json")),
        "manifest_sha": C.sha256_text(
            C.canonical_json(manifest).decode("utf-8")),
        "diff": diff["counts"],
        "rollback_ready": True,
    }
    BM.register(data_root, "backfill", out_tag, entry)
    _emit("=== REGISTER BACKFILL ===")
    _emit("version  : %s" % out_tag)
    _emit("base     : %s (immutable)" % base_manifest.get("version"))
    _emit("diff     : %s" % json.dumps(diff["counts"]))
    _emit("manifest : %s" % os.path.join(out_dir2, "manifest.json"))
    _emit("registry : appended (append-only)")
    return 0


# --------------------------------------------------------------------------- parser
def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="backfill",
                                 description="Backfill pipeline (PCM-20.6.3)")
    sub = ap.add_subparsers(dest="cmd")

    g = sub.add_parser("gap-report", help="gap-report-2 از pages.jsonl")
    g.add_argument("--pages", required=True, help="pages.jsonl base build")
    g.add_argument("--out", required=True, help="خروجی JSON گزارش")
    g.set_defaults(func=cmd_gap_report)

    p = sub.add_parser("plan", help="برنامه‌ی Fetch از گزارش شکاف")
    p.add_argument("--gap-report", required=True)
    p.add_argument("--out", default=None)
    p.add_argument("--budget", type=int, default=500,
                   help="درخواست‌های مجاز هر اجرا")
    p.add_argument("--delay", type=float, default=FP.BASE_DELAY_SECONDS)
    p.add_argument("--jitter", type=float, default=FP.JITTER_FRACTION)
    p.add_argument("--timeout", type=float,
                   default=FP.DEFAULT_TIMEOUT_SECONDS)
    p.add_argument("--attempts", type=int,
                   default=FP.DEFAULT_MAX_ATTEMPTS)
    p.set_defaults(func=cmd_plan)

    r = sub.add_parser("run", help="اجرای pipeline (budget هر اجرا)")
    r.add_argument("--plan", required=True)
    r.add_argument("--base-pages", required=True,
                   help="pages.jsonl base (read-only)")
    r.add_argument("--out-dir", default=None,
                   help="دایرکتوری خروجی (default: <plan-dir>/run)")
    r.add_argument("--budget", type=int, default=None)
    r.add_argument("--dry-run", action="store_true",
                   help="بدون درخواست — فقط شمارش آیتم‌های فعال")
    r.add_argument("--fake-bodies", default=None,
                   help="فایل JSON {item_index: body} — transport آفلاین "
                        "(بدون --allow-live هم مجاز)")
    r.add_argument("--allow-live", action="store_true",
                   help="اجازه‌ی transport زنده (با BACKFILL_APPROVED)")
    r.set_defaults(func=cmd_run)

    v = sub.add_parser("verify", help="بازتأیید خروجی run")
    v.add_argument("--plan", required=True)
    v.add_argument("--out-dir", default=None)
    v.add_argument("--base-pages", default=None,
                   help="pages.jsonl base (برای ثبت SHA immutable)")
    v.set_defaults(func=cmd_verify)

    rg = sub.add_parser("register", help="manifest + registry (append-only)")
    rg.add_argument("--plan", required=True)
    rg.add_argument("--base", required=True,
                    help="دایرکتوری base build (manifest.json)")
    rg.add_argument("--base-pages", required=True)
    rg.add_argument("--out-dir", default=None)
    rg.add_argument("--data-root", required=True,
                    help="ریشه‌ی data (corpus/builds + manifests)")
    rg.add_argument("--version", type=int, required=True,
                    help="شماره‌ی نسخه‌ی خروجی (مثلا‌ً 4 → v0004)")
    rg.set_defaults(func=cmd_register)
    return ap


def main(argv=None) -> int:
    C.force_utf8_stdio()
    ap = build_parser()
    args = ap.parse_args(argv)
    if not getattr(args, "func", None):
        ap.print_help()
        return 2
    try:
        return args.func(args)
    except SystemExit as e:
        return e.code if isinstance(e.code, int) else 2
    except (OSError, ValueError) as e:
        return _fail(str(e), 2)


if __name__ == "__main__":
    sys.exit(main())

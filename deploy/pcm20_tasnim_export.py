#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""pcm20_tasnim_export.py — خروجی کامل JSON پروژه «تفسیر تسنیم همتا» + ممیزی شماره صفحه.

اجرا روی s52 (read-only؛ هرگز چیزی در DB نمی‌نویسد):

    cd /home/saber/saberprojects/persian-corpus-toolkit
    python3 deploy/pcm20_tasnim_export.py \
        [--db backend/thesaurus.db] \
        [--project 2] \
        [--out-dir /home/saber/tasnim-export-<TS>] \
        [--gap-list-max 500]

خروجی‌ها (در --out-dir):
    tasnim-corpus.json    — یک فایل JSON کامل: متادیتای پروژه + تمام صفحات (هر صفحه یک record)
    tasnim-corpus.jsonl   — همان صفحات، هر خط یک JSON (برای streaming)
    export-summary.json   — آمار + ممیزی شماره صفحه (حاضر/غایب) + SHA-256 فایل‌ها

قواعد امن (مطابق AGENTS.md):
  * اتصال فقط read-only (URI mode=ro) — بدون WAL checkpoint، بدون نوشتن.
  * هیچ secret/رمز در خروجی؛ خروجی فقط داده‌ی کراول + متادیتای عمومی پروژه.
  * فقط stdlib؛ بدون وابستگی.

دو مقیاس شماره‌گذاری (مهم):
  * item_index — ایندکس پیوسته‌ی سایت در URL (کراول با next_step=1 می‌رود؛
    «کدام صفحات هست و کدام نیست» روی همین مقیاس معنادار است — حفره‌ها).
  * برگ — شماره‌ی برگِ کتاب درون متن که **بین جلد‌ها تکرار می‌شود** (پروژه چندجلد است)،
    پس برای آن فقط شمارش/محدوده گزارش می‌شود، نه فهرست حفره (معنا ندارد).
"""

import argparse
import hashlib
import json
import os
import re
import sqlite3
import sys
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlparse

PERSIAN_DIGITS = "۰۱۲۳۴۵۶۷۸۹"
ARABIC_DIGITS = "٠١٢٣٤٥٦٧٨٩"
_DIGIT_MAP = {c: str(i) for i, c in enumerate(PERSIAN_DIGITS + ARABIC_DIGITS)}

PAGE_NO_TAG = "برگ"
DIGITS_RE = re.compile(r"\d+")


def force_utf8_stdio() -> None:
    """Windows/Windows-terminal safety: cp1252 -> utf-8 (replace)."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def to_ascii_digits(value: str) -> str:
    return "".join(_DIGIT_MAP.get(c, c) for c in value)


def parse_barg(values: dict):
    """شماره‌ی «برگ» (اعداد فارسی/عربی نرمال می‌شوند) — None اگر نبود/نامعتبر بود."""
    raw = values.get(PAGE_NO_TAG)
    if raw is None:
        return None
    digits = DIGITS_RE.search(to_ascii_digits(str(raw)))
    return int(digits.group()) if digits else None


def parse_item_index(url: str):
    qs = parse_qs(urlparse(url or "").query)
    raw = (qs.get("item_index") or [""])[0].strip()
    return int(raw) if raw.isdigit() else None


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def gap_stats(numbers):
    """(min, max, distinct, missing_list, dup_count) for a list of ints."""
    if not numbers:
        return None, None, 0, [], 0
    lo, hi = min(numbers), max(numbers)
    present = set(numbers)
    missing = sorted(set(range(lo, hi + 1)) - present)
    dup = len(numbers) - len(present)
    return lo, hi, len(present), missing, dup


def main(argv=None) -> int:
    force_utf8_stdio()
    ap = argparse.ArgumentParser(description="Read-only Tasnim corpus export + page audit (s52)")
    ap.add_argument("--db", default="backend/thesaurus.db", help="path to thesaurus.db")
    ap.add_argument("--project", type=int, default=2, help="project id (default 2 = تفسیر تسنیم همتا)")
    ap.add_argument("--out-dir", default=None, help="output dir (default /home/saber/tasnim-export-<TS>)")
    ap.add_argument("--gap-list-max", type=int, default=500,
                    help="max gap entries to inline in the printed summary (full list stays in export-summary.json)")
    args = ap.parse_args(argv)

    if not os.path.exists(args.db):
        print("DB not found: %s" % args.db, file=sys.stderr)
        return 2

    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir = args.out_dir or os.path.join(os.path.expanduser("~"), "tasnim-export-%s" % ts)
    os.makedirs(out_dir, exist_ok=True)

    # ---- read-only connection -------------------------------------------------
    conn = sqlite3.connect("file:%s?mode=ro" % os.path.abspath(args.db), uri=True)
    conn.row_factory = sqlite3.Row
    try:
        proj = conn.execute("SELECT * FROM projects WHERE id=?", (args.project,)).fetchone()
        if proj is None:
            print("project %d not found" % args.project, file=sys.stderr)
            return 2
        proj = dict(proj)
        points = [dict(r) for r in conn.execute(
            "SELECT tag, source, selector, transform FROM project_points WHERE project_id=? ORDER BY id",
            (args.project,))]
        rows = conn.execute(
            "SELECT id, url, values_json, content_hash, captured_at "
            "FROM project_pages WHERE project_id=? ORDER BY id", (args.project,)).fetchall()
    finally:
        conn.close()

    # ---- build records ---------------------------------------------------------
    pages = []
    for r in rows:
        try:
            values = json.loads(r["values_json"] or "{}")
        except json.JSONDecodeError:
            values = {"_raw": r["values_json"]}
        pages.append({
            "page_id": r["id"],
            "url": r["url"],
            "captured_at": r["captured_at"],
            "content_hash": r["content_hash"],
            "item_index": parse_item_index(r["url"] or ""),
            "barg": parse_barg(values),
            "values": values,
        })

    idx_numbers = [p["item_index"] for p in pages if p["item_index"] is not None]
    idx_lo, idx_hi, idx_dist, idx_missing, idx_dup = gap_stats(idx_numbers)
    barg_numbers = [p["barg"] for p in pages if p["barg"] is not None]
    b_lo, b_hi, b_dist, _b_missing, b_dup = gap_stats(barg_numbers)

    audit = {
        "document_count": len(pages),
        "item_index": {
            "min": idx_lo, "max": idx_hi, "distinct": idx_dist,
            "missing_count": len(idx_missing),
            "missing_first_%d" % args.gap_list_max: idx_missing[:args.gap_list_max],
            "duplicate_item_index_rows": idx_dup,
            "note": ("پیوستگی ایندکس کراول: item_index‌های بین min..max که در DB نیستند. "
                     "فهرست کامل در field: item_index.missing_full (فایل summary)."),
        },
        "barg": {
            "pages_with_barg": len(barg_numbers),
            "pages_without_barg": len(pages) - len(barg_numbers),
            "min": b_lo, "max": b_hi, "distinct": b_dist,
            "duplicate_barg_rows": b_dup,
            "note": ("«برگ» شماره‌ی برگِ کتاب است و بین جلد‌ها تکرار می‌شود؛ "
                     "برای آن فهرست حفره گزارش نمی‌شود (معنا ندارد)."),
        },
    }

    # ---- write files -------------------------------------------------------------
    json_path = os.path.join(out_dir, "tasnim-corpus.json")
    jsonl_path = os.path.join(out_dir, "tasnim-corpus.jsonl")
    summary_path = os.path.join(out_dir, "export-summary.json")

    proj_public = {k: proj.get(k) for k in (
        "id", "name", "host", "start_url", "status", "saved_count", "skipped_count",
        "failed_count", "cursor_url", "created_at", "updated_at", "pages_per_minute",
        "next_mode", "next_param", "next_step")}

    with open(jsonl_path, "w", encoding="utf-8", newline="\n") as f:
        for p in pages:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")

    with open(json_path, "w", encoding="utf-8", newline="\n") as f:
        header = json.dumps({
            "corpus": "تفسیر تسنیم همتا (tasnim.hamtaa.org)",
            "exported_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "source_db": os.path.abspath(args.db),
            "mode": "read-only",
            "project": proj_public,
            "points": points,
            "page_count": len(pages),
            "page_audit": audit,
        }, ensure_ascii=False, indent=1)
        # open the object, keep the header fields, then append "pages" as the last member
        f.write(header[:-1].rstrip() + ",\n\"pages\": [\n")
        for i, p in enumerate(pages):
            f.write(json.dumps(p, ensure_ascii=False))
            f.write(",\n" if i + 1 < len(pages) else "\n")
        f.write("]\n}\n")

    summary = {
        "exported_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "server": {"db_path": os.path.abspath(args.db), "mode": "read-only"},
        "project": proj_public,
        "point_tags": [p["tag"] for p in points],
        "document_count": len(pages),
        "page_audit": audit,
        "item_index_missing_full": idx_missing,
        "files": {},
    }

    for name, path in (("tasnim-corpus.json", json_path),
                       ("tasnim-corpus.jsonl", jsonl_path)):
        summary["files"][name] = {
            "path": path,
            "size_bytes": os.path.getsize(path),
            "sha256": sha256_file(path),
        }
    with open(summary_path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(summary, f, ensure_ascii=False, indent=1)

    # ---- console report -------------------------------------------------------------
    print("\n=== EXPORT DONE (read-only) ===")
    print("out dir      : %s" % out_dir)
    print("documents    : %d page records (project %d «%s»)" % (len(pages), proj["id"], proj["name"]))
    print("item_index   : %d with index, min=%s max=%s distinct=%d missing=%d duplicates=%d"
          % (len(idx_numbers), idx_lo, idx_hi, idx_dist, len(idx_missing), idx_dup))
    if idx_missing:
        print("missing first %d: %s%s"
              % (args.gap_list_max, idx_missing[:args.gap_list_max],
                 " ..." if len(idx_missing) > args.gap_list_max else ""))
    print("barg         : %d with, %d without, min=%s max=%s distinct=%d duplicates=%d (تکرار بین جلد‌ها طبیعی است)"
          % (len(barg_numbers), len(pages) - len(barg_numbers), b_lo, b_hi, b_dist, b_dup))
    for name, meta in summary["files"].items():
        print("%-22s %12d bytes  sha256=%s" % (name, meta["size_bytes"], meta["sha256"]))
    print("summary      : %s" % summary_path)
    print("DONE — read-only; nothing was written to the DB.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

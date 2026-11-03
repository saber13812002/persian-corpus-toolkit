# -*- coding: utf-8 -*-
"""tasnim.reconcile — درگاه آشتیابی (Reconciliation Gate) و بارگذاری منبع.

وظیفه:
  1. بارگذاری فقط‌خواندنِ خروجی PCM-20 (JSONL + JSON + export-summary).
  2. ثبت SHA-256 ورودی (شناسه‌ی Source Snapshot).
  3. طبقه‌بندی کیفیت هر رکورد (empty/short/truncated/no_barg/...) —
     هیچ رکوردی حذف نمی‌شود؛ فقط flag می‌خورد.
  4. شناسایی تکراری‌ها (item_index و content_hash) با جزئیات.
  5. آمارهای درگاه آشتیابی (PCM-20.3 §1) — همان تعاریف PCM-20.2.
"""
from __future__ import annotations

import json
import os

from . import common as C
from . import schema as S

MIN_TEXT_CHARS = 20          # هم‌راستا با min_text_chars Builder
TRUNCATED_LEN = 2000         # max=2000 در ممیزی PCM-20.2 (خاستگاه: NOT VERIFIED)


# --------------------------------------------------------------------------- load
def _read_json_header(json_path: str) -> dict:
    """هدر tasnim-corpus.json را بدون بارگذاری کل فایل 73MB می‌خواند.

    ساختار فایل (خروجی PCM-20): هدر JSON + ",\n\"pages\": [...]"؛
    متن قبل از مارکر + "}" → همان شیء هدر کامل است.
    """
    marker = '"pages": ['
    with open(json_path, "rb") as f:
        buf = f.read()
    i = buf.find(marker.encode("utf-8"))
    if i < 0:
        raise ValueError("marker not found in %s" % json_path)
    head = buf[:i].decode("utf-8").rstrip()
    if head.endswith(","):
        head = head[:-1]
    head = head.rstrip()
    return json.loads(head + "}")


def load_source(jsonl_path: str, json_path: str = None, summary_path: str = None) -> dict:
    """بارگذاری و ثبت شناسه‌ی Source Snapshot.

    برگشت: {
      "jsonl_path", "jsonl_sha256", "jsonl_size_bytes", "record_count",
      "pages": [records...],                # با position (ایندس خط)
      "json_meta": dict|None, "json_path": str|None,
      "summary": dict|None, "summary_path": str|None, "summary_sha256": str|None,
    }
    """
    if not os.path.exists(jsonl_path):
        raise FileNotFoundError(jsonl_path)
    pages = []
    with open(jsonl_path, "r", encoding="utf-8") as f:
        for pos, line in enumerate(f):
            line = line.strip()
            if line:
                rec = json.loads(line)
                rec["_position"] = pos
                pages.append(rec)

    out = {
        "jsonl_path": os.path.abspath(jsonl_path),
        "jsonl_sha256": C.sha256_file(jsonl_path),
        "jsonl_size_bytes": C.file_size(jsonl_path),
        "record_count": len(pages),
        "pages": pages,
        "json_path": None,
        "json_meta": None,
        "summary_path": None,
        "summary": None,
        "summary_sha256": None,
    }

    # .json اختیاری: مسیر داده‌شده یا همسایه‌ی «tasnim-corpus.json»
    if json_path is None:
        guess = os.path.join(os.path.dirname(os.path.abspath(jsonl_path)), "tasnim-corpus.json")
        json_path = guess if os.path.exists(guess) else None
    if json_path and os.path.exists(json_path):
        try:
            out["json_meta"] = _read_json_header(json_path)
            out["json_path"] = os.path.abspath(json_path)
        except Exception:
            out["json_meta"] = None

    # export-summary اختیاری (کوچک است)
    if summary_path is None:
        guess = os.path.join(os.path.dirname(os.path.abspath(jsonl_path)), "export-summary.json")
        summary_path = guess if os.path.exists(guess) else None
    if summary_path and os.path.exists(summary_path):
        out["summary"] = C.read_json(summary_path)
        out["summary_path"] = os.path.abspath(summary_path)
        out["summary_sha256"] = C.sha256_file(summary_path)
    return out


# --------------------------------------------------------------------------- fields
def text_of(page: dict) -> str:
    v = page.get("values") or {}
    t = v.get(S.TEXT_KEY)
    return t if isinstance(t, str) else ""


def raw_barg_of(page: dict):
    v = page.get("values") or {}
    return v.get(S.BARG_KEY)


def reparsed_barg(page: dict):
    """بازپارسِ مرجع (همه‌ی ریک‌های ارقام) — اصلاح PCM-20.2."""
    return C.parse_barg_all_runs(raw_barg_of(page))


# --------------------------------------------------------------------------- quality
def quality_flags(page: dict, barg: int, dup_index: bool = False) -> list:
    """flags کیفیت یک رکورد — ترتیب ثابت (مبنای quality_status.status)."""
    text = text_of(page)
    flags = []
    if text == "":
        flags.append(S.F_EMPTY)
    elif len(text) < MIN_TEXT_CHARS:
        flags.append(S.F_SHORT)
    if len(text) == TRUNCATED_LEN:
        flags.append(S.F_TRUNCATED_2000)
    if barg is None:
        flags.append(S.F_NO_BARG)
    if page.get("item_index") is None:
        flags.append(S.F_MISSING_INDEX)
    if dup_index:
        flags.append(S.F_DUP_INDEX)
    return flags


def _flag_counts(pages_flags) -> dict:
    counts = {f: 0 for f in S.FLAGS_ALL}
    for flags in pages_flags:
        for f in flags:
            counts[f] += 1
    counts["ok"] = sum(1 for flags in pages_flags if not flags)
    return counts


# --------------------------------------------------------------------------- duplicates
def find_duplicate_indexes(pages) -> dict:
    """item_index تکراری: {value: [positions...]} + شمارنده‌ها."""
    by_idx = {}
    for p in pages:
        i = p.get("item_index")
        if i is None:
            continue
        by_idx.setdefault(i, []).append(p["_position"])
    dups = {i: pos for i, pos in sorted(by_idx.items()) if len(pos) > 1}
    return {
        "values": dups,
        "value_count": len(dups),
        "extra_rows": sum(len(v) - 1 for v in dups.values()),
    }


def find_duplicate_hashes(pages) -> dict:
    """content_hash تکراری (بدون None)."""
    by_h = {}
    for p in pages:
        h = p.get("content_hash")
        if not h:
            continue
        by_h.setdefault(h, []).append(p["_position"])
    dups = {h: pos for h, pos in sorted(by_h.items()) if len(pos) > 1}
    return {
        "values": {h: pos for h, pos in list(dups.items())[:20]},
        "value_count": len(dups),
        "extra_rows": sum(len(v) - 1 for v in dups.values()),
    }


# --------------------------------------------------------------------------- gate report
def gate_report(source: dict) -> dict:
    """خروجی درگاه آشتیابی (PCM-20.3 §1) — روی همان تعاریف PCM-20.2.

    اعداد: incomplete (متن خالی/غیرمتنی) / short / truncated_2000 / barg
    reparse counters / gaps item_index / duplicates / volume strategy census.
    """
    pages = source["pages"]
    n = len(pages)
    lens = []
    flags_all = []
    barg_null = 0
    idx_numbers = []
    vol_census = {S.STRATEGY_URL_SECTION: 0, S.STRATEGY_TEXT: 0, S.STRATEGY_NONE: 0}
    sections = {}
    dups_idx = find_duplicate_indexes(pages)
    dups_hash = find_duplicate_hashes(pages)
    dup_set = set()
    for i, poslist in dups_idx["values"].items():
        dup_set.update(poslist)

    for p in pages:
        t = text_of(p)
        lens.append(len(t))
        raw = raw_barg_of(p)
        barg = C.parse_barg_all_runs(raw)
        if barg is None:
            barg_null += 1
        idx = p.get("item_index")
        if idx is not None:
            idx_numbers.append(idx)
        flags = quality_flags(p, barg, dup_index=(p["_position"] in dup_set))
        flags_all.append(flags)
        vkey = S.assign_volume(p, t, None)
        vol_census[vkey["strategy"]] += 1
        sec = C.section_of_url(p.get("url") or "") or ""
        sections[sec] = sections.get(sec, 0) + 1

    lens_sorted = sorted(lens)
    return {
        "record_count": n,
        "incomplete_empty": sum(1 for f in flags_all if S.F_EMPTY in f),
        "short_lt_%d" % MIN_TEXT_CHARS: sum(1 for f in flags_all if S.F_SHORT in f),
        "truncated_at_2000": sum(1 for f in flags_all if S.F_TRUNCATED_2000 in f),
        "no_barg": barg_null,
        "missing_item_index": sum(1 for f in flags_all if S.F_MISSING_INDEX in f),
        "text_len": {
            "p50": C.percentile(lens_sorted, 50),
            "p90": C.percentile(lens_sorted, 90),
            "p99": C.percentile(lens_sorted, 99),
            "max": lens_sorted[-1] if lens_sorted else None,
            "histogram": C.text_histogram(lens),
        },
        "item_index": C.gap_stats(idx_numbers),
        "duplicate_item_index": dups_idx,
        "duplicate_content_hash": dups_hash,
        "barg_reparse": {
            "with_raw_barg": sum(1 for p in pages if raw_barg_of(p) is not None),
            "with_parsed_barg": n - barg_null,
            "equals_item_index_plus_1": sum(
                1 for p in pages
                if p.get("item_index") is not None
                and C.parse_barg_all_runs(raw_barg_of(p)) == p["item_index"] + 1),
            "differs_from_export_barg": sum(
                1 for p in pages
                if p.get("barg") is not None
                and C.parse_barg_all_runs(raw_barg_of(p)) != p["barg"]),
        },
        "volume_strategy_census": vol_census,
        "distinct_url_sections": len(sections),
        "url_section_histogram": dict(sorted(sections.items(), key=lambda kv: -kv[1])),
        "quality_flag_counts": _flag_counts(flags_all),
    }

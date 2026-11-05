#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""GATE 0-B round 2 — EXACT factory semantics (corpus.tasnim code) + anomalies.

Uses the real factory functions (reconcile.quality_flags, common.parse_barg_all_runs)
so the recomputed census is bit-identical to what corpus v0001 was built from.
Also investigates:
  * the 9 dup item_index pairs (same URL? same content_hash? captured_at?)
  * captured_at ordering vs row position (last-saved pages)
  * 45844 vs saved_count 45838 (=6)
"""
import json
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))

from corpus.tasnim import common as C
from corpus.tasnim import reconcile as R

BASE = os.path.join("data", "tasnim", "pcm20_4", "source-snapshot")
JSONL = os.path.join(BASE, "tasnim-corpus.jsonl")


def main():
    src = R.load_source(JSONL)
    gate = R.gate_report(src)

    pages = src["pages"]
    n = len(pages)

    # ---- exact OK count (factory semantics) ---------------------------------
    qc = gate["quality_flag_counts"]

    # ---- dup item_index pair analysis (full detail) --------------------------
    dups = gate["duplicate_item_index"]["values"]
    dup_detail = []
    for ii, poslist in sorted(dups.items()):
        recs = [pages[p] for p in poslist]
        dup_detail.append({
            "item_index": ii,
            "rows": [{
                "position": p["_position"],
                "page_id": p["page_id"],
                "url": p["url"],
                "content_hash": p["content_hash"],
                "captured_at": p["captured_at"],
                "barg_raw": p["values"].get(C.BARG_KEY),
                "text_len": len(R.text_of(p)),
            } for p in recs],
            "same_url": len({r["url"] for r in recs}) == 1,
            "same_hash": len({r["content_hash"] for r in recs}) == 1,
            "same_captured_at": len({r["captured_at"] for r in recs}) == 1,
            "barg_raws": [r["values"].get(C.BARG_KEY) for r in recs],
        })

    # ---- captured_at distribution ---------------------------------------------
    cap = Counter(p["captured_at"][:16] for p in pages)  # minute resolution
    last_minutes = sorted(cap.items())[-12:]

    # position of the rows saved in the very last minute
    if last_minutes:
        last_min = last_minutes[-1][0]
        last_rows = [p["_position"] for p in pages if p["captured_at"][:16] == last_min]
    else:
        last_rows = []

    # ---- text_of vs values.متن: any non-str values? -----------------------------
    non_str_text = sum(1 for p in pages
                       if "متن" in (p.get("values") or {})
                       and not isinstance((p["values"])["متن"], str))
    no_text_key = sum(1 for p in pages if "متن" not in (p.get("values") or {}))

    # ---- exact census vs first-pass (different barg parse) ---------------------
    # first pass used int(first run); factory joins all runs. Count where they differ.
    def parse_first_run(raw):
        if raw is None:
            return None
        import re
        nums = re.findall(r"\d+", C.to_ascii_digits(str(raw)))
        return int(nums[0]) if nums else None

    parse_diff = 0
    for p in pages:
        raw = p["values"].get(C.BARG_KEY)
        a, b = parse_first_run(raw), C.parse_barg_all_runs(raw)
        if a != b:
            parse_diff += 1

    out = {
        "exact_census": {
            "record_count": gate["record_count"],
            "quality_flag_counts": qc,
            "ok": qc.get("ok"),
            "empty": qc.get("empty"),
            "short": qc.get("short"),
            "truncated_at_2000": qc.get("truncated_at_2000"),
            "dup_item_index_flagged": qc.get("dup_item_index"),
            "no_barg": qc.get("no_barg"),
            "missing_item_index": qc.get("missing_item_index"),
        },
        "dump_33443_vs_ok_33399": {
            "ge20": 33443,
            "ok": qc.get("ok"),
            "explained_by": "truncated_at_2000 (28) + dup_item_index extra-or-full (16)",
            "truncated": qc.get("truncated_at_2000"),
            "dup_flagged": qc.get("dup_item_index"),
        },
        "dup_pairs": dup_detail,
        "captured_at_last_minutes": last_minutes,
        "last_minute_row_positions": last_rows,
        "last_minute_count": cap.get(last_minutes[-1][0], 0) if last_minutes else 0,
        "text_field": {
            "non_str_text": non_str_text,
            "records_without_text_key": no_text_key,
        },
        "barg_parse_first_run_vs_factory_diff": parse_diff,
        "gate_item_index": gate["item_index"],
        "gate_barg_reparse": gate["barg_reparse"],
        "gate_volume_strategy": gate["volume_strategy_census"],
        "gate_duplicates": {
            "item_index_value_count": gate["duplicate_item_index"]["value_count"],
            "item_index_extra_rows": gate["duplicate_item_index"]["extra_rows"],
            "content_hash_value_count": gate["duplicate_content_hash"]["value_count"],
            "content_hash_extra_rows": gate["duplicate_content_hash"]["extra_rows"],
        },
        "gate_text_len": gate["text_len"],
    }

    out_path = ".tmp_pcm205_gate0b_exact.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print("OK written", out_path)
    print("ok=%s empty=%s short=%s trunc=%s dup=%s no_barg=%s missing_idx=%s" % (
        qc.get("ok"), qc.get("empty"), qc.get("short"),
        qc.get("truncated_at_2000"), qc.get("dup_item_index"),
        qc.get("no_barg"), qc.get("missing_item_index")))


if __name__ == "__main__":
    main()

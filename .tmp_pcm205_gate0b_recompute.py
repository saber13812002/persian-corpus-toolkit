#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""GATE 0-B — recomputation of all PCM-20.4 stats directly from the real
source-snapshot file (no reuse of previously reported numbers).

Input:  data/tasnim/pcm20_4/source-snapshot/tasnim-corpus.jsonl
Output: .tmp_pcm205_gate0b_recompute.json
"""
import hashlib
import json
import os
import re
import sys
from collections import Counter
from urllib.parse import parse_qs, urlparse

PERSIAN = "۰۱۲۳۴۵۶۷۸۹"
ARABIC = "٠١٢٣٤۵۶۷۸۹"
DIGIT_MAP = {c: str(i) for i, c in enumerate(PERSIAN + ARABIC)}
DIGITS_RE = re.compile(r"\d+")


def to_ascii(v):
    return "".join(DIGIT_MAP.get(c, c) for c in str(v))


def parse_barg_all_runs(raw):
    """همان منطق common.parse_barg_all_runs (همه‌ی ریک‌های ارقام)."""
    if raw is None:
        return None
    nums = DIGITS_RE.findall(to_ascii(raw))
    if not nums:
        return None
    # all runs: first number of each run group — matches factory reparse
    # factory: parses ALL digit runs and takes... verify against factory code.
    return int(nums[0])


def main():
    base = os.path.join("data", "tasnim", "pcm20_4", "source-snapshot")
    jsonl_path = os.path.join(base, "tasnim-corpus.jsonl")
    json_path = os.path.join(base, "tasnim-corpus.json")
    summary_path = os.path.join(base, "export-summary.json")

    with open(summary_path, "r", encoding="utf-8") as f:
        summary = json.load(f)

    pages = []
    with open(jsonl_path, "r", encoding="utf-8") as f:
        for pos, line in enumerate(f):
            line = line.strip()
            if line:
                rec = json.loads(line)
                rec["_position"] = pos
                pages.append(rec)

    n = len(pages)

    # ---- text -----------------------------------------------------------------
    def text_of(p):
        v = p.get("values") or {}
        t = v.get("متن")
        return t if isinstance(t, str) else ""

    empty = [p["_position"] for p in pages if text_of(p) == ""]
    short = [p["_position"] for p in pages if 0 < len(text_of(p)) < 20]
    ge20 = [p for p in pages if len(text_of(p)) >= 20]
    truncated = [p["_position"] for p in ge20 if len(text_of(p)) == 2000]
    over2000 = [p["_position"] for p in ge20 if len(text_of(p)) > 2000]
    max_len = max((len(text_of(p)) for p in pages), default=0)
    len_hist = Counter()
    for p in pages:
        L = len(text_of(p))
        if L == 0:
            len_hist["0"] += 1
        elif L < 20:
            len_hist["1-19"] += 1
        elif L < 100:
            len_hist["20-99"] += 1
        elif L < 500:
            len_hist["100-499"] += 1
        elif L < 2000:
            len_hist["500-1999"] += 1
        elif L == 2000:
            len_hist["2000"] += 1
        else:
            len_hist[">2000"] += 1

    # ---- barg -------------------------------------------------------------------
    def barg_of(p):
        v = p.get("values") or {}
        raw = v.get("برگ")
        return raw

    raw_barg_present = [p["_position"] for p in pages if barg_of(p) is not None]

    def parsed_barg(p):
        raw = barg_of(p)
        if raw is None:
            return None
        nums = DIGITS_RE.findall(to_ascii(raw))
        return int(nums[0]) if nums else None

    no_barg_all = [p["_position"] for p in pages if parsed_barg(p) is None]
    no_barg_in_ge20 = [p["_position"] for p in ge20 if parsed_barg(p) is None]

    # export-barg vs reparsed
    export_barg_differs = 0
    export_barg_present = 0
    for p in pages:
        e = p.get("barg")
        r = parsed_barg(p)
        if e is not None:
            export_barg_present += 1
            if e != r:
                export_barg_differs += 1

    # ---- item_index ---------------------------------------------------------------
    def idx_of(p):
        url = p.get("url") or ""
        qs = parse_qs(urlparse(url).query)
        raw = (qs.get("item_index") or [""])[0].strip()
        return int(raw) if raw.isdigit() else p.get("item_index")

    for p in pages:
        p["_ii"] = idx_of(p)

    ii_missing_field = [p["_position"] for p in pages if p["_ii"] is None]
    ii_vals = [p["_ii"] for p in pages if p["_ii"] is not None]
    ii_set = set(ii_vals)
    ii_lo, ii_hi = min(ii_vals), max(ii_vals)
    missing = sorted(set(range(ii_lo, ii_hi + 1)) - ii_set)

    def runs(nums):
        out, s, prev = [], None, None
        for x in nums:
            if s is None:
                s = prev = x
            elif x == prev + 1:
                prev = x
            else:
                out.append([s, prev])
                s = prev = x
        if s is not None:
            out.append([s, prev])
        return out

    missing_runs = runs(missing)
    by_idx = {}
    for p in pages:
        if p["_ii"] is not None:
            by_idx.setdefault(p["_ii"], []).append(p["_position"])
    dup_idx = {i: pos for i, pos in sorted(by_idx.items()) if len(pos) > 1}
    dup_rows_all = [pos for poslist in dup_idx.values() for pos in poslist]
    dup_rows_ge20 = [p["_position"] for p in ge20 if p["_ii"] in dup_idx]

    # ---- content_hash ---------------------------------------------------------------
    by_hash = {}
    for p in pages:
        h = p.get("content_hash")
        if h:
            by_hash.setdefault(h, []).append(p["_position"])
    dup_hash = {h: pos for h, pos in by_hash.items() if len(pos) > 1}

    # ---- page_id integrity -------------------------------------------------------------
    pids = [p.get("page_id") for p in pages]
    pids_int = all(isinstance(x, int) for x in pids)
    pid_unique = len(set(pids)) == len(pids)
    pid_min, pid_max = min(pids), max(pids)

    # ---- volume (re-derive like factory: section in URL) ----------------------------------
    sec_counter = Counter()
    vol_pages = Counter()
    for p in pages:
        url = p.get("url") or ""
        qs = parse_qs(urlparse(url).query)
        sec = (qs.get("section") or [""])[0]
        m = re.search(r"\((\d+)\)\s*$", sec)
        vol = int(m.group(1)) if m else None
        sec_counter[sec or "<none>"] += 1
        vol_pages[vol] += 1

    # ---- cross sets for the 33,443 vs 33,399 question ------------------------------------
    ge20_set = set(p["_position"] for p in ge20)
    flag_sets = {
        "empty": set(empty),
        "short": set(short),
        "truncated_2000": set(truncated),
        "no_barg": set(no_barg_all),
        "dup_index_rows": set(dup_rows_all),
        "missing_index": set(ii_missing_field),
    }
    ok_recomputed = sum(1 for pos in range(n)
                        if not (set().union(*[s for s in flag_sets.values() if pos in s])))
    flagged_in_ge20 = sorted(ge20_set & set().union(*[s for s in flag_sets.values()]))
    overlap_nb_dup = sorted(set(no_barg_all) & set(dup_rows_all))
    overlap_empty_nb = sorted(set(empty) & set(no_barg_all))
    overlap_trunc_dup = sorted(set(truncated) & set(dup_rows_all))
    overlap_trunc_nb = sorted(set(truncated) & set(no_barg_all))

    def sample(pos, k=3):
        out = []
        for x in pos[:k]:
            p = pages[x]
            out.append({
                "position": x,
                "page_id": p.get("page_id"),
                "item_index": p["_ii"],
                "barg_export": p.get("barg"),
                "barg_raw": barg_of(p),
                "text_len": len(text_of(p)),
                "text_head": text_of(p)[:40],
                "url": (p.get("url") or "")[:120],
            })
        return out

    result = {
        "inputs": {
            "jsonl": jsonl_path,
            "jsonl_sha256": sha256_file(jsonl_path),
            "json_sha256": sha256_file(json_path) if os.path.exists(json_path) else None,
            "summary_sha256": sha256_file(summary_path),
            "jsonl_lines": n,
        },
        "header_vs_recomputed": {
            "summary_document_count": summary.get("document_count"),
            "recomputed_records": n,
            "summary_saved_count": (summary.get("project") or {}).get("saved_count"),
            "summary_skipped_count": (summary.get("project") or {}).get("skipped_count"),
            "summary_failed_count": (summary.get("project") or {}).get("failed_count"),
            "summary_status": (summary.get("project") or {}).get("status"),
            "rows_minus_saved": n - (summary.get("project") or {}).get("saved_count", 0),
        },
        "text_census": {
            "histogram": dict(len_hist),
            "empty": len(empty),
            "short_1_19": len(short),
            "ge20_dump_records": len(ge20),
            "truncated_at_2000": len(truncated),
            "over_2000": len(over2000),
            "max_len": max_len,
        },
        "dump_vs_ok": {
            "ge20": len(ge20),
            "ok_recomputed": ok_recomputed,
            "diff": len(ge20) - ok_recomputed,
            "flagged_in_ge20": len(flagged_in_ge20),
            "truncated_in_ge20": len(set(truncated) & ge20_set),
            "no_barg_in_ge20": len(no_barg_in_ge20),
            "dup_rows_in_ge20": len(dup_rows_ge20),
            "overlap_no_barg_dup": len(overlap_nb_dup),
            "overlap_empty_no_barg": len(overlap_empty_nb),
            "overlap_trunc_dup": len(overlap_trunc_dup),
            "overlap_trunc_no_barg": len(overlap_trunc_nb),
            "sample_flagged_in_ge20": sample(flagged_in_ge20, 10),
        },
        "barg": {
            "raw_present": len(raw_barg_present),
            "parsed_none": len(no_barg_all),
            "export_barg_present": export_barg_present,
            "export_differs_from_reparse": export_barg_differs,
            "no_barg_samples": sample(no_barg_all, 3),
        },
        "item_index": {
            "missing_field": len(ii_missing_field),
            "lo": ii_lo,
            "hi": ii_hi,
            "range_size": ii_hi - ii_lo + 1,
            "distinct": len(ii_set),
            "missing_count": len(missing),
            "missing_runs": missing_runs,
            "summary_missing_count": (summary.get("page_audit", {}).get("item_index") or {}).get("missing_count"),
            "summary_missing_full_len": len((summary.get("item_index_missing_full") or [])),
            "dup_values": len(dup_idx),
            "dup_rows_total": len(dup_rows_all),
            "dup_extra_rows": len(dup_rows_all) - len(dup_idx),
            "dup_detail": {str(k): {"positions": v, "page_ids": [pages[x]["page_id"] for x in v],
                                     "barg": [pages[x].get("barg") for x in v],
                                     "text_len": [len(text_of(pages[x])) for x in v]}
                            for k, v in list(dup_idx.items())[:12]},
        },
        "content_hash": {
            "present": len(by_hash),
            "dup_values": len(dup_hash),
            "dup_rows": sum(len(v) for v in dup_hash.values()),
            "none_count": sum(1 for p in pages if not p.get("content_hash")),
        },
        "page_id": {
            "all_int": pids_int,
            "unique": pid_unique,
            "min": pid_min,
            "max": pid_max,
            "count": len(pids),
            "sequential_1n": pids_int and pid_unique and pid_min == 1 and pid_max == n,
        },
        "volumes_rederived": {
            "sections": dict(sec_counter),
            "volume_counts": {str(k): v for k, v in sorted(vol_pages.items(), key=lambda kv: (kv[0] is None, kv[0] or 0))},
        },
        "summary_audit_item_index": (summary.get("page_audit") or {}).get("item_index"),
    }

    # dup detail sample with text
    out_path = ".tmp_pcm205_gate0b_recompute.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=1)
    print("OK written", out_path)


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


if __name__ == "__main__":
    main()

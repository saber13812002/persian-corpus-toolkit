# -*- coding: utf-8 -*-
"""PCM-20.4 Stage 1 — snapshot validation (read-only).

1) SHA-256 re-assert of the 4 snapshot files vs mission reference table.
2) JSON <-> JSONL record-level consistency (count, order, every field).
3) Header / summary cross-checks (page_count, document_count, sizes).
4) Full recomputation of PCM-20.2 statistics using the EXACT logic of
   deploy/pcm20_2_tasnim_audit.py (incomplete/empty/short, percentiles,
   dup item_index, dup content_hash, barg reparse, gaps/runs, sections).
5) Compare recomputation against the shipped pcm20_2_audit.json.
6) Identify the 6th section (the one without a volume number).
7) Three full real records: start / middle / end (different volumes).

Outputs:
  data/tasnim/pcm20_4/validation/stage1_snapshot_audit.json  (machine)
  .tmp_pcm204_stage1_out.txt                                  (human)
"""
import hashlib
import io
import json
import os
import re
import sys
from collections import Counter, defaultdict
from urllib.parse import parse_qs, urlparse

ROOT = "data/tasnim/pcm20_4/source-snapshot"
JSONL = os.path.join(ROOT, "tasnim-corpus.jsonl")
JSON = os.path.join(ROOT, "tasnim-corpus.json")
AUDIT = os.path.join(ROOT, "pcm20_2_audit.json")
SUMMARY = os.path.join(ROOT, "export-summary.json")
OUT_JSON = "data/tasnim/pcm20_4/validation/stage1_snapshot_audit.json"
OUT_TXT = ".tmp_pcm204_stage1_out.txt"

# mission reference SHAs (task spec)
REF = {
    "tasnim-corpus.json": ("72959214",
                           "cee2c08aae1862d0bde029868af29f1512a0faec8ac9a5c3b41d70d8260f1676"),
    "tasnim-corpus.jsonl": ("72906133",
                            "fd927b663733fe0530afdf76d6deb6b42f3b40d807297e60722fe3b0e79e96b5"),
    "pcm20_2_audit.json": ("63188",
                           "db6c30f415372c6ae7cb9709286e0d4f0ac42db78c5b7aa38de2e7996c7260d7"),
}

# ---------------------------------------------------------------- helpers
# (copied verbatim from deploy/pcm20_2_tasnim_audit.py)
_DIGIT_MAP = {}
for _i in range(10):
    _DIGIT_MAP[chr(0x06F0 + _i)] = str(_i)
    _DIGIT_MAP[chr(0x0660 + _i)] = str(_i)
DIGITS_RE = re.compile(r"\d+")
SECTION_RE = re.compile(r"(\d+)\s*\)?$")


def to_ascii(value):
    return "".join(_DIGIT_MAP.get(c, c) for c in value)


def section_of(url):
    qs = parse_qs(urlparse(url or "").query)
    return (qs.get("section") or [""])[0].strip()


def volume_no_from_section(section):
    s = to_ascii(section)
    if not s:
        return None
    m = SECTION_RE.search(s)
    return int(m.group(1)) if m else None


def text_of(rec):
    v = rec.get("values") or {}
    t = v.get("\u0645\u062a\u0646")
    return t if isinstance(t, str) else ""


def reparsed_barg(rec):
    v = rec.get("values") or {}
    raw = v.get("\u0628\u0631\u06af")
    if raw is None:
        return None
    runs = DIGITS_RE.findall(to_ascii(str(raw)))
    if not runs:
        return None
    try:
        return int("".join(runs))
    except ValueError:
        return None


def runs(sorted_numbers):
    out = []
    for n in sorted_numbers:
        if out and n == out[-1][1] + 1:
            out[-1][1] = n
        else:
            out.append([n, n])
    return out


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


L = []


def p(s=""):
    L.append(str(s))


# ---------------------------------------------------------------- 1. SHAs
p("=== 1) SHA-256 vs mission reference ===")
sha_ok = True
for name, (size_s, sha) in REF.items():
    path = os.path.join(ROOT, name)
    size = os.path.getsize(path)
    sha_now = sha256_file(path)
    ok = (size == int(size_s)) and (sha_now == sha)
    sha_ok = sha_ok and ok
    p("%-24s size=%d (ref %s) sha=%s ok=%s"
      % (name, size, size_s, sha_now[:16], ok))
p("sha_ok=%s" % sha_ok)

# ---------------------------------------------------------------- load
p("\n=== load ===")
with io.open(JSONL, "r", encoding="utf-8") as f:
    jsonl_pages = [json.loads(line) for line in f if line.strip()]
p("jsonl_pages=%d" % len(jsonl_pages))

with io.open(JSON, "r", encoding="utf-8") as f:
    doc = json.load(f)
json_pages = doc["pages"]
p("json_pages=%d  header_keys=%s" % (len(json_pages), sorted(doc.keys())))

# ---------------------------------------------------------------- 2. JSON<->JSONL
p("\n=== 2) JSON <-> JSONL consistency ===")
cons = {
    "jsonl_count": len(jsonl_pages),
    "json_count": len(json_pages),
    "counts_equal": len(jsonl_pages) == len(json_pages),
    "mismatches": [],
    "page_id_order_equal": None,
    "url_order_equal": None,
    "item_index_order_equal": None,
    "barg_order_equal": None,
    "captured_at_order_equal": None,
    "content_hash_order_equal": None,
    "text_order_equal": None,
}
n_cmp = min(len(jsonl_pages), len(json_pages))
field_mismatch = Counter()
for i in range(n_cmp):
    a, b = jsonl_pages[i], json_pages[i]
    if a == b:
        continue
    bad = []
    keys = set(a) | set(b)
    for k in keys:
        if a.get(k) != b.get(k):
            bad.append(k)
            field_mismatch[k] += 1
    cons["mismatches"].append({"pos": i,
                               "page_id": (a or {}).get("page_id"),
                               "bad_keys": bad})
    if len(cons["mismatches"]) >= 20:
        break
cons["mismatch_count_total"] = None  # filled below if all-scan done
# full-scan count (cheap: dict equality)
mm = sum(1 for i in range(n_cmp) if jsonl_pages[i] != json_pages[i])
cons["mismatch_count_total"] = mm
cons["field_mismatch_counts"] = dict(field_mismatch)
cons["page_id_order_equal"] = all(
    jsonl_pages[i].get("page_id") == json_pages[i].get("page_id") for i in range(n_cmp))
cons["url_order_equal"] = all(
    jsonl_pages[i].get("url") == json_pages[i].get("url") for i in range(n_cmp))
cons["item_index_order_equal"] = all(
    jsonl_pages[i].get("item_index") == json_pages[i].get("item_index") for i in range(n_cmp))
cons["barg_order_equal"] = all(
    jsonl_pages[i].get("barg") == json_pages[i].get("barg") for i in range(n_cmp))
cons["captured_at_order_equal"] = all(
    jsonl_pages[i].get("captured_at") == json_pages[i].get("captured_at") for i in range(n_cmp))
cons["content_hash_order_equal"] = all(
    jsonl_pages[i].get("content_hash") == json_pages[i].get("content_hash") for i in range(n_cmp))
cons["text_order_equal"] = all(
    text_of(jsonl_pages[i]) == text_of(json_pages[i]) for i in range(n_cmp))
p(json.dumps(cons, ensure_ascii=False, indent=1))

# ---------------------------------------------------------------- 3. header
p("\n=== 3) header / summary cross-checks ===")
header = {k: doc[k] for k in doc if k != "pages"}
summary = json.load(io.open(SUMMARY, "r", encoding="utf-8"))
hdr = {
    "page_count": doc.get("page_count"),
    "summary_document_count": summary.get("document_count"),
    "jsonl_count": len(jsonl_pages),
    "consistent": doc.get("page_count") == len(jsonl_pages)
    == summary.get("document_count") == len(json_pages),
    "exported_at_utc": doc.get("exported_at_utc"),
    "mode": doc.get("mode"),
    "source_db": doc.get("source_db"),
    "project": {k: doc.get("project", {}).get(k)
                for k in ("id", "name", "status", "saved_count",
                          "skipped_count", "failed_count")},
    "point_tags": [pt.get("tag") for pt in doc.get("points", [])],
    "header_page_audit_item_index": doc.get("page_audit", {}).get("item_index"),
    "header_page_audit_barg": doc.get("page_audit", {}).get("barg"),
}
p(json.dumps(hdr, ensure_ascii=False, indent=1))

# ---------------------------------------------------------------- 4. recompute
p("\n=== 4) recompute PCM-20.2 statistics (JSONL, exact audit logic) ===")
records = jsonl_pages
n = len(records)

incomplete, empty_text = [], []
short_text = 0
text_lens = []
for i, r in enumerate(records):
    v = r.get("values") or {}
    miss = [k for k in ("page_id", "url", "captured_at", "content_hash")
            if r.get(k) in (None, "")]
    if r.get("item_index") is None:
        miss.append("item_index")
    if not v:
        miss.append("values(empty)")
    t = text_of(r)
    if not t.strip():
        miss.append("values.متن(empty)")
    if miss:
        incomplete.append({"pos": i, "page_id": r.get("page_id"),
                           "url": r.get("url"), "missing": miss})
    if not t.strip():
        empty_text.append({"pos": i, "page_id": r.get("page_id"),
                           "item_index": r.get("item_index"), "url": r.get("url")})
    elif len(t.strip()) < 20:
        short_text += 1
    text_lens.append(len(t))

by_idx = defaultdict(list)
for i, r in enumerate(records):
    ix = r.get("item_index")
    if ix is not None:
        by_idx[ix].append(i)
dup_idx = {ix: [{"pos": p_, "page_id": records[p_].get("page_id"),
                 "url": records[p_].get("url"),
                 "content_hash": records[p_].get("content_hash"),
                 "barg": records[p_].get("barg"),
                 "section": section_of(records[p_].get("url") or ""),
                 "captured_at": records[p_].get("captured_at")}
                for p_ in pos]
            for ix, pos in sorted(by_idx.items()) if len(pos) > 1}

by_hash = defaultdict(list)
for i, r in enumerate(records):
    h = r.get("content_hash")
    if h:
        by_hash[h].append(i)
dup_hash = {h: [{"pos": p_, "page_id": records[p_].get("page_id"),
                 "item_index": records[p_].get("item_index"),
                 "url": records[p_].get("url")} for p_ in ps]
            for h, ps in by_hash.items() if len(ps) > 1}

barg_with_raw = barg_diff_count = barg_eq_ix1 = 0
barg_diff_samples = []
for i, r in enumerate(records):
    raw = (r.get("values") or {}).get("\u0628\u0631\u06af")
    if raw is None:
        continue
    barg_with_raw += 1
    rp = reparsed_barg(r)
    ex = r.get("barg")
    if rp != ex:
        barg_diff_count += 1
        if len(barg_diff_samples) < 10:
            barg_diff_samples.append({"pos": i, "item_index": r.get("item_index"),
                                      "raw": str(raw), "export_barg": ex,
                                      "reparsed": rp})
    if rp is not None and r.get("item_index") is not None \
            and rp == r["item_index"] + 1:
        barg_eq_ix1 += 1

idx_numbers = sorted(x for x in (r.get("item_index") for r in records)
                     if x is not None)
lo, hi = idx_numbers[0], idx_numbers[-1]
present = set(idx_numbers)
missing = [x for x in range(lo, hi + 1) if x not in present]
pres_runs = runs(sorted(present))
miss_runs = runs(missing)
miss_sizes = Counter(b - a + 1 for a, b in miss_runs)
big_miss = [{"lo": a, "hi": b, "size": b - a + 1}
            for a, b in miss_runs if b - a + 1 >= 50]

by_sec = defaultdict(list)
for i, r in enumerate(records):
    by_sec[section_of(r.get("url") or "")].append(i)

volumes = []
for sec, pos in sorted(by_sec.items(),
                       key=lambda kv: (volume_no_from_section(kv[0]) is None,
                                       volume_no_from_section(kv[0]) or 0,
                                       kv[0])):
    idxs = [x for x in (records[p_].get("item_index") for p_ in pos)
            if x is not None]
    bargs = [records[p_].get("barg") for p_ in pos
             if records[p_].get("barg") is not None]
    volumes.append({
        "section": sec,
        "volume_no": volume_no_from_section(sec),
        "sample_url": records[pos[0]].get("url"),
        "pages": len(pos),
        "item_index_min": min(idxs) if idxs else None,
        "item_index_max": max(idxs) if idxs else None,
        "item_index_span": (max(idxs) - min(idxs) + 1) if idxs else 0,
        "item_index_dup_within": len(idxs) - len(set(idxs)),
        "barg_min": min(bargs) if bargs else None,
        "barg_max": max(bargs) if bargs else None,
        "barg_distinct": len(set(bargs)),
        "empty_text": sum(1 for p_ in pos if not text_of(records[p_]).strip()),
    })

textl = sorted(text_lens)
def pct(p_):
    return textl[min(n - 1, int(p_ * n))] if n else 0

recalc = {
    "document_count": n,
    "records_with_missing_fields": len(incomplete),
    "incomplete_records": incomplete[:50],
    "empty_text_count": len(empty_text),
    "empty_text_records": empty_text[:50],
    "text_lt_20_chars_count": short_text,
    "text_len_min": textl[0] if n else None,
    "text_len_p50": pct(0.5), "text_len_p90": pct(0.9),
    "text_len_p95": pct(0.95), "text_len_p99": pct(0.99),
    "text_len_max": textl[-1] if n else None,
    "item_index_duplicates": {"count": len(dup_idx), "details": dup_idx},
    "content_hash_duplicates": {"count": len(dup_hash),
                                "details": {h: d for h, d in
                                             list(dup_hash.items())[:20]}},
    "barg_reparse_check": {
        "with_raw_barg": barg_with_raw,
        "reparsed_differs_from_export_barg": barg_diff_count,
        "sample_mismatches": barg_diff_samples,
        "reparsed_equals_item_index_plus_1": barg_eq_ix1,
    },
    "gaps": {
        "range": [lo, hi], "range_size": hi - lo + 1,
        "present_count": len(idx_numbers), "present_runs": pres_runs,
        "missing_count": len(missing), "missing_runs": miss_runs,
        "missing_size_distribution": dict(sorted(miss_sizes.items())),
        "big_missing_runs_ge_50": big_miss,
    },
    "volumes": {
        "distinct_sections": len(volumes),
        "sections_with_volume_no": sum(1 for v in volumes
                                       if v["volume_no"] is not None),
        "volume_nos": sorted(v["volume_no"] for v in volumes
                             if v["volume_no"] is not None),
        "per_volume": volumes,
    },
}
p(json.dumps({k: recalc[k] for k in
              ("document_count", "records_with_missing_fields",
               "empty_text_count", "text_lt_20_chars_count", "text_len_min",
               "text_len_p50", "text_len_p90", "text_len_p95",
               "text_len_p99", "text_len_max")}, ensure_ascii=False))
p("dup_item_index=%d (extra rows %d)  dup_content_hash=%d"
  % (len(dup_idx), sum(len(v) - 1 for v in dup_idx.values()), len(dup_hash)))
p("barg: with_raw=%d differs_from_export=%d eq_ix_plus_1=%d"
  % (barg_with_raw, barg_diff_count, barg_eq_ix1))
p("gaps: range=%s..%s present=%d missing=%d miss_runs=%d present_runs=%d"
  % (lo, hi, len(idx_numbers), len(missing), len(miss_runs), len(pres_runs)))
p("miss_runs=%s" % miss_runs)
p("big_miss=%s" % big_miss)
p("sections=%d with_volno=%d vol_nos=%s..%s (n=%d)"
  % (len(volumes), recalc["volumes"]["sections_with_volume_no"],
     recalc["volumes"]["volume_nos"][0],
     recalc["volumes"]["volume_nos"][-1],
     len(recalc["volumes"]["volume_nos"])))

# ---------------------------------------------------------------- 5. vs shipped audit
p("\n=== 5) recompute vs shipped pcm20_2_audit.json ===")
ref_audit = json.load(io.open(AUDIT, "r", encoding="utf-8"))
ref_int = ref_audit.get("integrity", {})
ref_gaps = ref_audit.get("gaps", {})
ref_vol = ref_audit.get("volumes", {})
refb = ref_int.get("barg_reparse_check", {})
cmp_pairs = [
    ("document_count", ref_audit.get("document_count"), recalc["document_count"]),
    ("records_with_missing_fields", ref_int.get("records_with_missing_fields"),
     recalc["records_with_missing_fields"]),
    ("empty_text_count", ref_int.get("empty_text_count"), recalc["empty_text_count"]),
    ("text_lt_20_chars", ref_int.get("text_lt_20_chars_count"),
     recalc["text_lt_20_chars_count"]),
    ("text_len_min", ref_int.get("text_len_min"), recalc["text_len_min"]),
    ("text_len_p50", ref_int.get("text_len_p50"), recalc["text_len_p50"]),
    ("text_len_p90", ref_int.get("text_len_p90"), recalc["text_len_p90"]),
    ("text_len_max", ref_int.get("text_len_max"), recalc["text_len_max"]),
    ("dup_item_index", ref_int.get("item_index_duplicates", {}).get("count"),
     len(dup_idx)),
    ("dup_content_hash", ref_int.get("content_hash_duplicates", {}).get("count"),
     len(dup_hash)),
    ("barg_with_raw", refb.get("with_raw_barg"), barg_with_raw),
    ("barg_diff", refb.get("reparsed_differs_from_export_barg"), barg_diff_count),
    ("barg_eq_ix1", refb.get("reparsed_equals_item_index_plus_1"), barg_eq_ix1),
    ("gap_range", ref_gaps.get("range"), [lo, hi]),
    ("missing_count", ref_gaps.get("missing_count"), len(missing)),
    ("missing_runs", len(ref_gaps.get("missing_runs") or []), len(miss_runs)),
    ("distinct_sections", ref_vol.get("distinct_sections"), len(volumes)),
    ("sections_with_volno", ref_vol.get("sections_with_volume_no"),
     recalc["volumes"]["sections_with_volume_no"]),
    ("volume_nos", ref_vol.get("volume_nos"), recalc["volumes"]["volume_nos"]),
]
all_match = True
for name, a, b in cmp_pairs:
    ok = a == b
    all_match = all_match and ok
    p("%-24s ref=%s recalc=%s match=%s" % (name, a, b, ok))
p("ALL_MATCH=%s" % all_match)

# ---------------------------------------------------------------- 6. 6th section
p("\n=== 6) the section WITHOUT a volume number ===")
for v in volumes:
    if v["volume_no"] is None:
        p(json.dumps(v, ensure_ascii=False, indent=1))
        pos = by_sec[v["section"]]
        # sample 5 records from it
        step = max(1, len(pos) // 5)
        for p_ in pos[::step][:5]:
            r = records[p_]
            t = text_of(r)
            p("  sample pos=%d item_index=%s barg_raw=%r url=%s"
              % (p_, r.get("item_index"),
                 (r.get("values") or {}).get("\u0628\u0631\u06af"),
                 r.get("url")))
            p("    text(%d)=%r" % (len(t), t[:160]))
        # section distribution of its item_indexes vs known volumes
        idxs = sorted(x for x in (records[p_].get("item_index") for p_ in pos)
                      if x is not None)
        p("  item_index count=%d min=%s max=%s"
          % (len(idxs), idxs[0] if idxs else None, idxs[-1] if idxs else None))

# ---------------------------------------------------------------- 7. samples
p("\n=== 7) three full real records (start / middle / end) ===")
def full_rec(i):
    r = records[i]
    t = text_of(r)
    return {"pos": i, "page_id": r.get("page_id"), "url": r.get("url"),
            "captured_at": r.get("captured_at"),
            "content_hash": r.get("content_hash"),
            "item_index": r.get("item_index"), "barg": r.get("barg"),
            "values": {
                "ادرس صفحه": (r.get("values") or {}).get("ادرس صفحه"),
                "برگ": (r.get("values") or {}).get("برگ"),
                "لینک صفحه بعد": (r.get("values") or {}).get("لینک صفحه بعد"),
                "لینک صفحه قبل": (r.get("values") or {}).get("لینک صفحه قبل"),
                "متن_len": len(t),
                "متن_head": t[:120],
                "متن_tail": t[-120:],
            }}

s_start, s_mid, s_end = full_rec(0), full_rec(n // 2), full_rec(n - 1)
p(json.dumps(s_start, ensure_ascii=False, indent=1))
p(json.dumps(s_mid, ensure_ascii=False, indent=1))
p(json.dumps(s_end, ensure_ascii=False, indent=1))

# also first & last record by item_index (for volume coverage)
i0 = idx_numbers[0]
iN = idx_numbers[-1]
pos0 = next(i for i, r in enumerate(records) if r.get("item_index") == i0)
posN = next(i for i, r in enumerate(records) if r.get("item_index") == iN)
p(json.dumps(full_rec(pos0), ensure_ascii=False, indent=1))
p(json.dumps(full_rec(posN), ensure_ascii=False, indent=1))

# ---------------------------------------------------------------- write
os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)
report = {
    "sha_check": {k: {"size": os.path.getsize(os.path.join(ROOT, k)),
                      "sha256": sha256_file(os.path.join(ROOT, k)),
                      "expected_sha": v[1], "expected_size": v[0]}
                  for k, v in REF.items()},
    "sha_ok": sha_ok,
    "json_jsonl_consistency": cons,
    "header_crosscheck": hdr,
    "recomputed": recalc,
    "vs_shipped_audit": [{"field": a, "ref": b, "recalc": c, "match": b == c}
                         for a, b, c in cmp_pairs],
    "all_match": all_match,
    "section_without_volume_no": [v for v in volumes if v["volume_no"] is None],
    "samples": {"pos0": s_start, "pos_mid": s_mid, "pos_end": s_end,
                "min_item_index": full_rec(pos0),
                "max_item_index": full_rec(posN)},
}
with io.open(OUT_JSON, "w", encoding="utf-8", newline="\n") as f:
    json.dump(report, f, ensure_ascii=False, indent=1)
with io.open(OUT_TXT, "w", encoding="utf-8", newline="\n") as f:
    f.write("\n".join(L))
print("stage1 audit done. json=%s txt=%s" % (OUT_JSON, OUT_TXT))

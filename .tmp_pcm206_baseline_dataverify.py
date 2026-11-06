#!/usr/bin/env python3
"""PCM-20.6 BASELINE - Part D: read-only verification of local data state.

Recomputes SHA-256 of every artifact recorded in .tmp_pcm205_readiness_s1.json
and compares against the recorded values. Also recomputes the item_index gap
(45,243 missing) directly from the source snapshot, and locates the
truncated_at_2000 evidence. STRICTLY READ-ONLY: opens no file for writing.
"""
import hashlib
import json
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def size(path):
    return os.path.getsize(path)


def count_lines(path):
    n = 0
    with open(path, "rb") as f:
        for _ in f:
            n += 1
    return n


def main():
    out = {"mission": "PCM-20.6 baseline - Part D local data verification",
           "mode": "read-only", "data_modified": False, "checks": []}

    def check(kind, path, expected, actual, ok=None, **extra):
        row = {"kind": kind, "path": path, "expected": expected,
               "actual": actual, "match": (expected == actual) if ok is None else ok}
        row.update(extra)
        out["checks"].append(row)
        return row["match"]

    # --- 1. S1 audit SHAs for key artifacts -------------------------------
    s1 = json.load(open(os.path.join(ROOT, ".tmp_pcm205_readiness_s1.json"),
                        encoding="utf-8"))

    # source snapshot
    snap = s1["A_source_snapshot"]["files"]
    for name, rec in snap.items():
        p = os.path.join(ROOT, "data/tasnim/pcm20_4/source-snapshot", name)
        if os.path.exists(p):
            check("file_sha", p, rec["sha256"], sha256_file(p),
                  size=size(p), size_match=size(p) == rec["size_bytes"])
        else:
            check("file_sha", p, rec["sha256"], "MISSING", False)

    # corpora
    build_dir_map = {
        "pcm20_4/v0001": "data/tasnim/pcm20_4/corpus/builds/v0001",
        "pcm20_4/v0002": "data/tasnim/pcm20_4/corpus/builds/v0002",
        "pcm20_4/v0003": "data/tasnim/pcm20_4/corpus/builds/v0003",
        "pcm20_5/v0001": "data/tasnim/pcm20_5/corpus/builds/v0001",
        "pcm20_5/v0002": "data/tasnim/pcm20_5/corpus/builds/v0002",
        "crossroot/v0001": "data/tasnim/pcm20_5_crossroot/corpus/builds/v0001",
        "crossroot/v0002": "data/tasnim/pcm20_5_crossroot/corpus/builds/v0002",
    }
    for build, rec in s1["B_corpora"]["builds"].items():
        files = rec.get("files", {})
        base = os.path.join(ROOT, *build_dir_map[build].split("/"))
        for fname, f in files.items():
            expected = f["sha256"] if isinstance(f, dict) else f
            p = os.path.join(base, fname)
            if os.path.exists(p):
                check("corpus_file_sha", p, expected, sha256_file(p))
            else:
                check("corpus_file_sha", p, expected, "MISSING", False)

    # datasets
    for ds, rec in s1["D_datasets"]["datasets"].items():
        d, v = ds.split("/", 1)
        p = os.path.join(ROOT, "data/tasnim/pcm20_4/datasets", d, v, "manifest.json")
        check("dataset_manifest_sha", p, rec["manifest_sha256_recomputed"],
              sha256_file(p))

    # dumps
    for ds, rec in s1["E_dumps"]["dumps"].items():
        d, v = ds.split("/", 1)
        base = os.path.join(ROOT, "data/tasnim/pcm20_4/dumps", d, v)
        for fname, f in rec["files"].items():
            p = os.path.join(base, fname)
            check("dump_file_sha", p, f["sha256"], sha256_file(p))

    # registries
    reg_map = {"pcm20_4": "pcm20_4", "pcm20_5": "pcm20_5",
               "crossroot": "pcm20_5_crossroot"}
    for name, sha in s1["G_cross_checks"]["registries_sha256"].items():
        p = os.path.join(ROOT, "data/tasnim", reg_map[name], "manifests/registry.json")
        check("registry_sha", p, sha, sha256_file(p))

    # --- 2. recompute gap from snapshot jsonl -----------------------------
    snap_path = os.path.join(ROOT, "data/tasnim/pcm20_4/source-snapshot/tasnim-corpus.jsonl")
    PERSIAN = "۰۱۲۳۴۵۶۷۸۹"
    ARABIC = "٠١٢٣٤٥٦٧٨٩"
    trans = str.maketrans(PERSIAN + ARABIC, "0123456789" * 2)

    total = 0
    have = set()
    missing_count = 0
    dup_extra = 0
    seen = set()
    with open(snap_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            total += 1
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            url = rec.get("url") or ""
            ii = rec.get("item_index")
            if ii is None or ii == "":
                # try to parse from url
                import re
                m = re.search(r"index=(\d+)", url)
                if m:
                    ii = int(m.group(1))
            if ii is None or ii == "":
                missing_count += 1
                continue
            try:
                ii = int(str(ii).translate(trans))
            except (ValueError, TypeError):
                missing_count += 1
                continue
            if ii in seen:
                dup_extra += 1
            else:
                seen.add(ii)

    ii_min = min(seen) if seen else None
    ii_max = max(seen) if seen else None
    span = (ii_max - ii_min + 1) if seen else 0
    coverage_gap = span - len(seen)
    out["gap_recompute"] = {
        "source": snap_path,
        "total_lines": total,
        "distinct_item_index": len(seen),
        "min_item_index": ii_min,
        "max_item_index": ii_max,
        "span_inclusive": span,
        "coverage_gap_recomputed": coverage_gap,
        "note": "45243 = values in [min..max] not present = span - distinct (not missing fields: every row carries an item_index)",
        "declared_missing": s1["B_corpora"]["gaps"]["missing_item_index_count"],
        "match_declared": coverage_gap == s1["B_corpora"]["gaps"]["missing_item_index_count"],
        "declared_runs": s1["B_corpora"]["gaps"]["missing_runs"],
    }
    # contiguous gap runs
    runs = []
    if seen:
        g = ii_min
        missing = set(range(ii_min, ii_max + 1)) - seen
        mstart = None
        for v in range(ii_min, ii_max + 1):
            if v not in seen and mstart is None:
                mstart = v
            elif v in seen and mstart is not None:
                runs.append([mstart, v - 1])
                mstart = None
        if mstart is not None:
            runs.append([mstart, ii_max])
    out["gap_recompute"]["recomputed_runs"] = runs
    out["gap_recompute"]["runs_match_declared"] = runs == s1["B_corpora"]["gaps"]["missing_runs"]
    out["gap_recompute"]["runs_sum"] = sum(b - a + 1 for a, b in runs)

    # --- 3. truncated_at_2000 evidence ------------------------------------
    g15 = os.path.join(ROOT, "data/tasnim/pcm20_4/validation/gate1_5_truncation_conclusion.json")
    if os.path.exists(g15):
        t = json.load(open(g15, encoding="utf-8"))
        out["truncation_evidence"] = {
            "path": g15,
            "sha256": sha256_file(g15),
            "keys": sorted(t.keys())[:20],
            "summary": {k: t[k] for k in t if k in (
                "conclusion", "status", "count", "page_count",
                "truncated_pages", "sample_ids", "evidence")},
        }

    # --- 4. v0002 semantic quick stats ------------------------------------
    v2pages = os.path.join(ROOT, "data/tasnim/pcm20_5/corpus/builds/v0002/pages.jsonl")
    v2ctx = os.path.join(ROOT, "data/tasnim/pcm20_5/corpus/builds/v0002/context-records.jsonl")
    out["v0002_stats"] = {
        "pages_lines": count_lines(v2pages),
        "context_lines": count_lines(v2ctx),
        "pages_sha": sha256_file(v2pages),
        "ctx_sha": sha256_file(v2ctx),
    }

    mismatches = [c for c in out["checks"] if not c["match"]]
    out["result"] = "ALL_MATCH" if not mismatches else f"{len(mismatches)} MISMATCH"
    out["mismatches"] = mismatches[:20]

    json.dump(out, sys.stdout, ensure_ascii=False, indent=1)
    print()
    return 0 if not mismatches else 1


if __name__ == "__main__":
    sys.exit(main())

# -*- coding: utf-8 -*-
"""PCM-20.5 readiness audit S1 — read-only probe.

No writes anywhere except the single evidence file (handled by the caller).
All data under data/ is opened read-only.
"""
import hashlib
import json
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

from corpus.tasnim import transform as T  # read-only import for content_sha256_of_files

OUT = {}


def sha256_file(path, chunk=1024 * 1024):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def file_info(path):
    return {"sha256": sha256_file(path), "size_bytes": os.path.getsize(path)}


def count_lines(path, chunk=4 * 1024 * 1024):
    n = 0
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            n += b.count(b"\n")
    return n


def first_line(path):
    with open(path, "rb") as f:
        return f.readline()


# ---------------------------------------------------------------- A. source snapshot
SS = "data/tasnim/pcm20_4/source-snapshot"
ss_files = {}
for name in ("tasnim-corpus.jsonl", "tasnim-corpus.json", "export-summary.json", "pcm20_2_audit.json"):
    p = os.path.join(SS, name)
    ss_files[name] = file_info(p)
OUT["A_source_snapshot"] = {
    "path": SS,
    "files": ss_files,
    "jsonl_line_count": count_lines(os.path.join(SS, "tasnim-corpus.jsonl")),
}

# ---------------------------------------------------------------- B. builds
BUILDS = [
    ("pcm20_4/v0001", "data/tasnim/pcm20_4/corpus/builds/v0001"),
    ("pcm20_4/v0002", "data/tasnim/pcm20_4/corpus/builds/v0002"),
    ("pcm20_4/v0003", "data/tasnim/pcm20_4/corpus/builds/v0003"),
    ("pcm20_5/v0001", "data/tasnim/pcm20_5/corpus/builds/v0001"),
    ("pcm20_5/v0002", "data/tasnim/pcm20_5/corpus/builds/v0002"),
    ("crossroot/v0001", "data/tasnim/pcm20_5_crossroot/corpus/builds/v0001"),
    ("crossroot/v0002", "data/tasnim/pcm20_5_crossroot/corpus/builds/v0002"),
]

OUT["B_builds"] = {}
for tag, d in BUILDS:
    m = json.load(open(os.path.join(d, "manifest.json"), encoding="utf-8"))
    files_actual = {}
    for name in m["data"]["files"]:
        files_actual[name] = file_info(os.path.join(d, name))
    decl_files = m["data"]["files"]
    files_match = all(files_actual[n]["sha256"] == decl_files[n]["sha256"]
                      and files_actual[n]["size_bytes"] == decl_files[n]["size_bytes"]
                      for n in decl_files)
    recomputed_content = T.content_sha256_of_files(decl_files)
    manifest_sha = file_info(os.path.join(d, "manifest.json"))["sha256"]
    entry = {
        "manifest_path": os.path.join(d, "manifest.json"),
        "manifest_sha256_recomputed": manifest_sha,
        "version": m.get("version"),
        "kind": m.get("kind"),
        "declared_content_sha256": m["data"]["content_sha256"],
        "recomputed_content_sha256": recomputed_content,
        "content_sha_match": recomputed_content == m["data"]["content_sha256"],
        "files_declared_match_disk": files_match,
        "files_actual": {k: v["sha256"] for k, v in files_actual.items()},
        "pages_line_count": count_lines(os.path.join(d, "pages.jsonl")),
        "prev": m.get("prev"),
    }
    if "context-records.jsonl" in files_actual:
        entry["context_records_line_count"] = count_lines(os.path.join(d, "context-records.jsonl"))
    OUT["B_builds"][tag] = entry

# pcm20_5 v0001 raw/normalized completeness probe (spot: full scan, cheap)
def pages_probe(d, with_semantic=False):
    missing_text = 0
    missing_norm = 0
    missing_hash = 0
    semantic_next = 0
    n = 0
    with open(os.path.join(d, "pages.jsonl"), encoding="utf-8") as f:
        for line in f:
            n += 1
            p = json.loads(line)
            if "text" not in p:
                missing_text += 1
            if "text_normalized" not in p:
                missing_norm += 1
            if "content_hash" not in p:
                missing_hash += 1
            if with_semantic:
                s = p.get("semantic") or {}
                if s.get("next_page_id") is not None:
                    semantic_next += 1
    return {"pages": n, "missing_text": missing_text, "missing_text_normalized": missing_norm,
            "missing_content_hash": missing_hash, "pages_with_semantic_next_page_id": semantic_next}

OUT["B_builds"]["pcm20_5/v0001"]["raw_normalized_probe"] = pages_probe("data/tasnim/pcm20_5/corpus/builds/v0001")
OUT["B_builds"]["pcm20_5/v0002"]["raw_normalized_probe"] = pages_probe("data/tasnim/pcm20_5/corpus/builds/v0002", with_semantic=True)

# ---------------------------------------------------------------- C. semantic context records
CTX = "data/tasnim/pcm20_5/corpus/builds/v0002/context-records.jsonl"
recs = []
with open(CTX, encoding="utf-8") as f:
    for line in f:
        recs.append(json.loads(line))

ids = [r.get("record_id") for r in recs]
idset = set(ids)
first = recs[0]
mid = recs[len(recs) // 2]
last = recs[-1]


def sample(rec):
    ht = rec.get("heading_text") or ""
    summary = rec.get("next_page_summary") or ""
    return {
        "record_id": rec.get("record_id"),
        "visibility": rec.get("visibility"),
        "heading_text_len": len(ht),
        "heading_text_first30": ht[:30],
        "next_page_id": rec.get("next_page_id"),
        "next_item_index": rec.get("next_item_index"),
        "next_page_summary_lines": len([l for l in summary.splitlines() if l.strip()]),
        "next_page_summary_chars": len(summary),
        "internal_tags": rec.get("internal_tags"),
        "context_hash_present": bool(rec.get("context_hash")),
        "summary_meta": rec.get("summary_meta"),
        "keys": sorted(rec.keys()),
    }

# 5 samples for summary line-count verification (1st, mid, last, plus 2 fixed)
five = [recs[0], recs[1000], recs[5000], recs[len(recs) // 2], recs[-1]]
OUT["C_semantic"] = {
    "context_record_count": len(recs),
    "duplicate_record_ids": len(ids) - len(idset),
    "first": sample(first),
    "middle": sample(mid),
    "last": sample(last),
    "summary_line_counts_5_samples": [sample(r)["next_page_summary_lines"] for r in five],
    "all_visibilities": sorted({r.get("visibility") for r in recs}),
    "all_have_summary": all(r.get("next_page_summary") for r in recs),
    "all_methods": sorted({(r.get("summary_meta") or {}).get("method") for r in recs}),
    "all_models": sorted({(r.get("summary_meta") or {}).get("model") for r in recs}),
}

# delta-11 recompute: join heading pages (semantic.record_class) with context records
HEADING_CLASSES = ("SECTION_HEADING", "CHAPTER_HEADING")
ctx_heading_ids = {r.get("heading_page_id") for r in recs}
pages_idx = {}       # page_id -> (record_class, next_page_id, text_len)
last_of_volume = {}  # volume_id -> last page_id (file order == order_key order)
class_counts = {}
heading_info = []
sample_page_semantic = None
with open("data/tasnim/pcm20_5/corpus/builds/v0002/pages.jsonl", encoding="utf-8") as f:
    for line in f:
        p = json.loads(line)
        s = p.get("semantic") or {}
        cls = s.get("record_class")
        if cls:
            class_counts[cls] = class_counts.get(cls, 0) + 1
        pid = p.get("page_id")
        vid = p.get("volume_id")
        pages_idx[pid] = (cls, s.get("next_page_id"), len(p.get("text") or ""))
        last_of_volume[vid] = pid
        if cls in HEADING_CLASSES:
            if sample_page_semantic is None:
                sample_page_semantic = {
                    "page_id": pid,
                    "semantic_keys": sorted(s.keys()),
                    "record_class": s.get("record_class"),
                    "next_page_id": s.get("next_page_id"),
                    "basis": s.get("basis"),
                }
            heading_info.append((pid, vid, s.get("next_page_id"), cls))

missing_ctx = []
for pid, vid, npi, cls in heading_info:
    if pid in ctx_heading_ids:
        continue
    detail = {
        "page_id": pid,
        "volume_id": vid,
        "record_class": cls,
        "next_page_id": npi,
        "is_volume_last_page": last_of_volume.get(vid) == pid,
    }
    if npi:
        ncls, _nnpi, nlen = pages_idx.get(npi, (None, None, None))
        detail["next_page_record_class"] = ncls
        detail["next_page_text_len"] = nlen
    missing_ctx.append(detail)

m2 = json.load(open("data/tasnim/pcm20_5/corpus/builds/v0002/manifest.json", encoding="utf-8"))
mi2 = m2["data"]["stats"]["item_index"]
runs2 = mi2.get("missing_runs") or []
OUT["C_semantic"]["class_counts_recomputed"] = class_counts
OUT["C_semantic"]["sample_page_semantic_block"] = sample_page_semantic
OUT["C_semantic"]["heading_pages_matched"] = len(heading_info)
OUT["C_semantic"]["headings_without_context_record"] = missing_ctx
OUT["C_semantic"]["gap_runs"] = runs2
OUT["C_semantic"]["gap_runs_sum_inclusive"] = sum(b - a + 1 for a, b in runs2)
OUT["C_semantic"]["declared_missing_count"] = mi2.get("missing_count")

# ---------------------------------------------------------------- D. datasets
DS = [
    ("1pct/v0001", "data/tasnim/pcm20_4/datasets/1pct/v0001"),
    ("10pct/v0001", "data/tasnim/pcm20_4/datasets/10pct/v0001"),
    ("10pct/v0002", "data/tasnim/pcm20_4/datasets/10pct/v0002"),
    ("50pct/v0001", "data/tasnim/pcm20_4/datasets/50pct/v0001"),
    ("90pct/v0001", "data/tasnim/pcm20_4/datasets/90pct/v0001"),
    ("100pct/v0001", "data/tasnim/pcm20_4/datasets/100pct/v0001"),
]
OUT["D_datasets"] = {}
for tag, d in DS:
    m = json.load(open(os.path.join(d, "manifest.json"), encoding="utf-8"))
    dm = m["data"]["dataset_meta"]
    files_actual = {n: file_info(os.path.join(d, n)) for n in m["data"]["files"]}
    recomputed = T.content_sha256_of_files(m["data"]["files"])
    OUT["D_datasets"][tag] = {
        "manifest_sha256_recomputed": file_info(os.path.join(d, "manifest.json"))["sha256"],
        "version": m.get("version"),
        "percentage": m["data"].get("percentage"),
        "volume_scope": m["data"].get("volume_scope"),
        "declared_content_sha256": m["data"]["content_sha256"],
        "recomputed_content_sha256": recomputed,
        "content_sha_match": recomputed == m["data"]["content_sha256"],
        "files_match_disk": all(files_actual[n]["sha256"] == m["data"]["files"][n]["sha256"]
                                and files_actual[n]["size_bytes"] == m["data"]["files"][n]["size_bytes"]
                                for n in m["data"]["files"]),
        "selected_page_count": dm["stats"]["selected_page_count"],
        "pages_jsonl_lines": count_lines(os.path.join(d, "pages.jsonl")),
        "corpus_ref": dm["corpus"],
        "volume_distribution": dm["stats"]["volume_distribution"],
        "flag_counts": dm["stats"]["flag_counts_in_dataset"],
        "policy_id": dm["policy"]["id"],
        "prev": m.get("prev"),
    }

# 10pct v0001 empty-text count among selected pages
n_empty = 0
n_total = 0
with open("data/tasnim/pcm20_4/datasets/10pct/v0001/pages.jsonl", encoding="utf-8") as f:
    for line in f:
        n_total += 1
        p = json.loads(line)
        if not (p.get("text") or "").strip():
            n_empty += 1
OUT["D_datasets"]["10pct/v0001"]["empty_text_pages_in_dataset"] = {"total": n_total, "empty_text": n_empty}

# ---------------------------------------------------------------- E. dumps
DUMPS = [
    ("10pct/v0001", "data/tasnim/pcm20_4/dumps/10pct/v0001"),
    ("10pct/v0002", "data/tasnim/pcm20_4/dumps/10pct/v0002"),
    ("100pct/v0001", "data/tasnim/pcm20_4/dumps/100pct/v0001"),
]
OUT["E_dumps"] = {}
for tag, d in DUMPS:
    m = json.load(open(os.path.join(d, "manifest.json"), encoding="utf-8"))
    files_actual = {n: file_info(os.path.join(d, n)) for n in m["data"]["files"]}
    recomputed = T.content_sha256_of_files(m["data"]["files"])
    entry = {
        "manifest_sha256_recomputed": file_info(os.path.join(d, "manifest.json"))["sha256"],
        "version": m.get("version"),
        "declared_content_sha256": m["data"].get("content_sha256"),
        "recomputed_content_sha256": recomputed,
        "content_sha_match": recomputed == m["data"].get("content_sha256"),
        "files_match_disk": all(files_actual[n]["sha256"] == m["data"]["files"][n]["sha256"]
                                and files_actual[n]["size_bytes"] == m["data"]["files"][n]["size_bytes"]
                                for n in m["data"]["files"]),
        "files": {n: {"sha256": v["sha256"], "size_bytes": v["size_bytes"]} for n, v in files_actual.items()},
        "dump_meta_keys": sorted(m["data"].get("dump_meta", {}).keys()) if "dump_meta" in m["data"] else sorted(m["data"].keys()),
        "dataset_ref": m["data"].get("dump_meta", {}).get("dataset") if "dump_meta" in m["data"] else None,
    }
    OUT["E_dumps"][tag] = entry

# builder-input chunks: line counts + first record schema + embedding check
BI = "data/tasnim/pcm20_4/builder-input"
for case in ("tasnim_tafsir_vol56", "tasnim_tafsir_10pct", "tasnim_tafsir_100pct"):
    bd = None
    for b in os.listdir(os.path.join(BI, case, "builds")):
        bd = os.path.join(BI, case, "builds", b)
    chunks = os.path.join(bd, "chunks.jsonl")
    n_lines = count_lines(chunks)
    first_rec = None
    emb_dim = None
    with open(chunks, encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            first_rec = {k: (v if not isinstance(v, list) else "<list len=%d>" % len(v)) for k, v in r.items()}
            if isinstance(r.get("embedding"), list):
                emb_dim = len(r["embedding"])
            break
    m = json.load(open(os.path.join(bd, "manifest.json"), encoding="utf-8"))
    OUT["E_dumps"].setdefault("builder_chunks", {})[case] = {
        "build_dir": bd,
        "chunks_lines": n_lines,
        "first_record_keys": sorted(first_rec.keys()),
        "first_record_nonlist": {k: v for k, v in first_rec.items() if not isinstance(v, str) or not v.startswith("<list")},
        "embedding_dim": emb_dim,
        "build_manifest_keys": sorted(m.keys()) if isinstance(m, dict) else None,
        "build_manifest_embedding_backend": m.get("embedding") or m.get("embedding_backend") if isinstance(m, dict) else None,
    }

# ---------------------------------------------------------------- G. registries sha
for reg in ("data/tasnim/pcm20_4/manifests/registry.json", "data/tasnim/pcm20_5/manifests/registry.json",
            "data/tasnim/pcm20_5_crossroot/manifests/registry.json"):
    if reg not in OUT:
        OUT.setdefault("G_registries", {})[reg] = file_info(reg)["sha256"]

OUT["G_registries"] = OUT.get("G_registries", {})
OUT["G_registries"]["pcm20_4/manifests/registry.json"] = file_info("data/tasnim/pcm20_4/manifests/registry.json")["sha256"]
OUT["G_registries"]["pcm20_5/manifests/registry.json"] = file_info("data/tasnim/pcm20_5/manifests/registry.json")["sha256"]
OUT["G_registries"]["pcm20_5_crossroot/manifests/registry.json"] = file_info("data/tasnim/pcm20_5_crossroot/manifests/registry.json")["sha256"]

if "--digest" in sys.argv and OUT:
    def _b(tag):
        e = OUT["B_builds"][tag]
        return {k: e[k] for k in ("version", "kind", "manifest_sha256_recomputed",
                                  "declared_content_sha256", "recomputed_content_sha256",
                                  "content_sha_match", "files_declared_match_disk",
                                  "files_actual", "pages_line_count", "prev")
                if k in e}
    def _d(tag):
        e = OUT["D_datasets"][tag]
        return {k: e[k] for k in ("version", "percentage", "volume_scope",
                                  "manifest_sha256_recomputed", "declared_content_sha256",
                                  "recomputed_content_sha256", "content_sha_match", "files_match_disk",
                                  "selected_page_count", "pages_jsonl_lines", "corpus_ref", "policy_id", "prev")
                if k in e}
    def _e(tag):
        e = OUT["E_dumps"][tag]
        return {k: e[k] for k in ("version", "manifest_sha256_recomputed", "declared_content_sha256",
                                  "recomputed_content_sha256", "content_sha_match", "files_match_disk",
                                  "files", "dataset_ref", "dump_meta_keys") if k in e}
    DIG = {
        "source_snapshot": OUT["A_source_snapshot"],
        "builds": {t: _b(t) for t in OUT["B_builds"]},
        "raw_norm_probe": {
            "pcm20_5/v0001": OUT["B_builds"]["pcm20_5/v0001"]["raw_normalized_probe"],
            "pcm20_5/v0002": OUT["B_builds"]["pcm20_5/v0002"]["raw_normalized_probe"],
        },
        "semantic_c": {
            k: OUT["C_semantic"][k] for k in
            ("context_record_count", "duplicate_record_ids", "class_counts_recomputed",
             "heading_pages_matched", "headings_without_context_record", "gap_runs",
             "gap_runs_sum_inclusive", "declared_missing_count", "all_visibilities",
             "all_have_summary", "all_methods", "all_models", "summary_line_counts_5_samples",
             "sample_page_semantic_block")
        },
        "ctx_samples": {
            k: {kk: OUT["C_semantic"][k][kk] for kk in
                ("record_id", "visibility", "heading_text_len", "heading_text_first30",
                 "next_page_id", "next_item_index", "next_page_summary_lines",
                 "next_page_summary_chars", "internal_tags", "context_hash_present", "summary_meta")}
            for k in ("first", "middle", "last")
        },
        "datasets": {t: _d(t) for t in OUT["D_datasets"]},
        "dataset_10pct_v1_empty_text": OUT["D_datasets"]["10pct/v0001"]["empty_text_pages_in_dataset"],
        "dumps": {t: _e(t) for t in OUT["E_dumps"] if t != "builder_chunks"},
        "builder_chunks": OUT["E_dumps"].get("builder_chunks", {}),
        "registries": OUT["G_registries"],
    }
    sys.stdout.write(json.dumps(DIG, ensure_ascii=False, indent=1))
    raise SystemExit(0)

if __name__ == "__main__":
    if "--compact" in sys.argv:
        c = OUT["C_semantic"]
        sys.stdout.write(json.dumps({
            "class_counts": c["class_counts_recomputed"],
            "headings": c["heading_pages_matched"],
            "ctx_records": c["context_record_count"],
            "delta": c["heading_pages_matched"] - c["context_record_count"],
            "missing_ctx_detail": c["headings_without_context_record"],
            "gap_runs_sum": c["gap_runs_sum_inclusive"],
            "declared_missing": c["declared_missing_count"],
            "sample_semantic_keys": (c["sample_page_semantic_block"] or {}).get("semantic_keys"),
            "sample_semantic": c["sample_page_semantic_block"],
        }, ensure_ascii=False, indent=1))
    else:
        sys.stdout.write(json.dumps(OUT, ensure_ascii=False, indent=1))

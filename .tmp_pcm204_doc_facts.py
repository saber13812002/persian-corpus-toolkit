# -*- coding: utf-8 -*-
"""Compact fact sheet for PCM-20.4 docs (read-only)."""
import io
import json
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", newline="\n")

ROOT = r"C:\Users\s.tabatabaei\Documents\saberprojects\persian-corpus-toolkit\data\tasnim\pcm20_4"

def jload(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)

facts = {}

# corpus volumes
cm = jload(os.path.join(ROOT, "corpus", "builds", "v0001", "manifest.json"))
facts["corpus_v0001"] = {
    "content_sha256": cm["data"]["content_sha256"],
    "page_count": cm["data"]["stats"]["page_count"],
    "volumes": [
        {"id": v["volume_id"], "no": v["volume_no"], "pages": v["page_count"],
         "short": v["short_count"], "empty": v["empty_count"], "title": v["volume_title"]}
        for v in cm["data"]["stats"]["volumes"]
    ],
}

# datasets
for sub in ["1pct", "10pct", "50pct", "90pct", "100pct"]:
    d = os.path.join(ROOT, "datasets", sub)
    out = {}
    for v in sorted(os.listdir(d)):
        m = jload(os.path.join(d, v, "manifest.json"))
        meta = m["data"]["dataset_meta"]
        out[v] = {
            "content_sha256": m["data"]["content_sha256"],
            "selected": meta["stats"]["selected_page_count"],
            "pct_of_corpus": meta["stats"]["pct_of_corpus"],
            "flags": meta["stats"]["flag_counts_in_dataset"],
            "text_len": meta["stats"]["text_len_in_dataset"],
            "volume_scope": m["data"].get("volume_scope"),
            "per_vol": {x["volume_id"]: {"sel": x["selected"], "cov": x["coverage_pct"],
                                          "in_vol": x["pages_in_volume"]}
                         for x in meta["stats"]["volume_distribution"]},
            "prev": m["prev"],
        }
    facts["dataset_" + sub] = out

# dumps
for sub in ["10pct", "100pct"]:
    d = os.path.join(ROOT, "dumps", sub)
    out = {}
    for v in sorted(os.listdir(d)):
        m = jload(os.path.join(d, v, "manifest.json"))
        chk = jload(os.path.join(d, v, "dump-check.json"))
        books = jload(os.path.join(d, v, "books.json"))
        n_pages = sum(len(b.get("pages", [])) for b in books)
        out[v] = {
            "content_sha256": m["data"]["content_sha256"],
            "books": len(books),
            "book_pages": n_pages,
            "prev": m["prev"],
            "check": chk,
        }
    facts["dump_" + sub] = out

# change manifest (incremental fixture)
try:
    cm2 = jload(os.path.join(ROOT, "reports", "change-manifest.json"))
    facts["change_manifest"] = {k: cm2[k] for k in cm2 if not isinstance(cm2[k], list)}
except Exception as e:
    facts["change_manifest"] = {"error": str(e)}

# source-snapshot manifest
sdir = os.path.join(ROOT, "sources")
if os.path.isdir(sdir):
    for s in sorted(os.listdir(sdir)):
        try:
            m = jload(os.path.join(sdir, s, "manifest.json"))
            facts["source_" + s] = {k: m[k] for k in ("version", "kind", "created_at")}
        except Exception as e:
            facts["source_" + s] = {"error": str(e)}

print(json.dumps(facts, ensure_ascii=False, indent=1, sort_keys=True))

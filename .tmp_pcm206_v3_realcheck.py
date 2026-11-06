# -*- coding: utf-8 -*-
"""PCM-20.6 D1: spot-check the real v0003 build (read-only)."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from corpus.tasnim import common as C        # noqa: E402
from corpus.tasnim import manifest as M      # noqa: E402
from corpus.tasnim import semantic as SEM    # noqa: E402
from corpus.tasnim import validate as VAL    # noqa: E402

ROOT = os.path.join("data", "tasnim", "pcm20_5")
V2 = os.path.join(ROOT, "corpus", "builds", "v0002")
V3 = os.path.join(ROOT, "corpus", "builds", "v0003")

corpus3 = C.read_json(os.path.join(V3, "corpus.json"))
man3 = M.load_manifest(V3)
man2 = M.load_manifest(V2)

sem = corpus3["semantic"]
print("schema_version:", sem["schema_version"])
print("prev_contract :", sem["prev_contract"])
print("base          :", sem["base_corpus"]["version"], sem["base_corpus"]["content_sha256"][:16])
hc = sem["hidden_context"]
print("hc headings   :", hc["heading_records"]["count"])
print("hc contexts   :", hc["context_records"]["count"])
t = sem["truncation"]
print("trunc cap     :", t["source_char_cap"], "affected:", t["affected_count"])
print("trunc first 3 :", t["affected_pages"][:3])
print("evidence sha  :", t["evidence"]["sha256"][:16])

print("files in man  :", sorted(man3["data"]["files"]))
print("content sha   :", man3["data"]["content_sha256"][:16])
print("prev          :", man3["prev"]["version"], man3["prev"]["path_rel"])

# one heading record + one context record
hr = C.read_jsonl(os.path.join(V3, "heading-records.jsonl"))
gc = C.read_jsonl(os.path.join(V3, "hidden-context-records.jsonl"))
print("heading rows  :", len(hr), "context rows:", len(gc))
h0 = hr[0]
print("H0 record_id  :", h0["record_id"])
print("H0 heading    :", h0["heading_text"], "| vol", h0["volume_no"],
      "| parent", h0["parent_heading_page_id"],
      "| children", len(h0["children_page_ids"]), "| next", h0["next_page_id"])
# verify a children range
g0 = gc[0]
print("G0 record_id  :", g0["record_id"], "page", g0["page_id"])
print("G0 summary    :", repr(g0["hidden_summary"])[:60],
      "| lines", g0["summary_lines"], "| next_vol", g0["next_volume_no"])
# hash recompute spot check
meta = {k: v for k, v in h0.items() if k != "heading_hash"}
assert h0["heading_hash"] == C.sha256_text(
    C.canonical_json(meta).decode("utf-8")), "heading_hash recompute failed"
cmeta = {k: v for k, v in g0.items() if k != "context_hash"}
assert g0["context_hash"] == C.sha256_text(
    C.canonical_json(cmeta).decode("utf-8")), "context_hash recompute failed"
print("hash recompute: OK (H0, G0)")

# cs-20.5 base untouched: v0002 content sha + files
print("v2 content sha:", man2["data"]["content_sha256"][:16],
      "files:", sorted(man2["data"]["files"]))
assert man2["data"]["content_sha256"] == \
    "12a93e218bbc7a38d450749eca5ce25d0833b537cc13446048d430eade54f4a5", \
    "v0002 base changed!"
# validate both
ok, err, warn = VAL.validate_corpus(V3)
print("validate_corpus v3:", ok, err[:3], warn[:3])
ok2, serr, swarn = SEM.validate_semantic(V3, ROOT)
print("validate_semantic v3:", ok2, serr[:3], swarn[:3])
ok3, err3, warn3 = VAL.validate_corpus(V2)
print("validate_corpus v2:", ok3, err3[:3], warn3[:3])

# a truncated page's block
pages = C.read_jsonl(os.path.join(V3, "pages.jsonl"))
tp = [p for p in pages if p["page_id"] == t["affected_pages"][0]][0]
print("trunc page    :", tp["page_id"], "len", len(tp["text"]),
      "block:", tp["semantic"]["truncation"])
print("ALL CHECKS DONE")

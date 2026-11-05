# -*- coding: utf-8 -*-
"""First record of a real builder chunks.jsonl (embedding clipped)."""
import io
import json
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", newline="\n")

p = (r"C:\Users\s.tabatabaei\Documents\saberprojects\persian-corpus-toolkit"
     r"\data\tasnim\pcm20_4\builder-input\tasnim_tafsir_10pct"
     r"\builds\qwen3-embed-06b_20261104-041457\chunks.jsonl")
with open(p, encoding="utf-8") as f:
    rec = json.loads(f.readline())
emb = rec.get("embedding")
if isinstance(emb, list):
    rec["embedding"] = [round(x, 6) for x in emb[:4]] + ["…(%d dims total)" % len(emb)]
if "chunk_text" in rec and isinstance(rec["chunk_text"], str) and len(rec["chunk_text"]) > 300:
    rec["chunk_text"] = rec["chunk_text"][:300] + "…"
print(json.dumps(rec, ensure_ascii=False, indent=1))

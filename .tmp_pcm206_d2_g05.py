# -*- coding: utf-8 -*-
"""Probe: why does load_item_indexes report 45844 distinct on the real snapshot?"""
import json
import io

P = r"data/tasnim/pcm20_4/source-snapshot/tasnim-corpus.jsonl"

total = 0
no_idx = 0
seen = set()
dup = 0
non_int = 0
sample_nonint = None
sample_first = None
with io.open(P, "r", encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        rec = json.loads(line)
        if sample_first is None:
            sample_first = {k: (v if not isinstance(v, str) or len(v) < 60 else v[:60] + "...")
                            for k, v in rec.items()}
        total += 1
        idx = rec.get("item_index")
        if idx is None:
            no_idx += 1
            continue
        if not isinstance(idx, int):
            non_int += 1
            if sample_nonint is None:
                sample_nonint = (line[:200], type(idx).__name__, idx)
            continue
        if idx in seen:
            dup += 1
            continue
        seen.add(idx)

print("total        :", total)
print("no_index     :", no_idx)
print("non_int_idx  :", non_int)
print("dups         :", dup)
print("distinct     :", len(seen))
print("min/max      :", min(seen), max(seen))
print("first keys   :", sorted((sample_first or {}).keys()))
print("sample_first :", sample_first)
print("sample_nonint:", sample_nonint)

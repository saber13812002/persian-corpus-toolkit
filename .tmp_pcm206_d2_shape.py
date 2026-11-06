# -*- coding: utf-8 -*-
import io
import json

JL = "data/tasnim/pcm20_4/source-snapshot/tasnim-corpus.jsonl"
with io.open(JL, "r", encoding="utf-8") as f:
    line = f.readline()
rec = json.loads(line)
print("KEYS:", sorted(rec.keys()))
v = rec.get("values") or {}
print("VALUES KEYS:", sorted(v.keys()))
print(json.dumps(rec, ensure_ascii=False)[:600])
print("--- summary head ---")
s = json.load(open("data/tasnim/pcm20_4/source-snapshot/export-summary.json",
                  encoding="utf-8"))
print(json.dumps(s, ensure_ascii=False, indent=1)[:1200])

# -*- coding: utf-8 -*-
"""Sample records for PCM-20.4 docs (read-only, truncate long text)."""
import io
import json
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", newline="\n")

ROOT = r"C:\Users\s.tabatabaei\Documents\saberprojects\persian-corpus-toolkit\data\tasnim\pcm20_4"

def first_jsonl_line(path):
    with open(path, encoding="utf-8") as f:
        return json.loads(f.readline())

def clip(o, limit=220):
    if isinstance(o, dict):
        return {k: clip(v, limit) for k, v in o.items()}
    if isinstance(o, list):
        return [clip(x, limit) for x in o[:2]]
    if isinstance(o, str) and len(o) > limit:
        return o[:limit] + "…"
    return o

print("=== corpus v0001 pages.jsonl (first line, clipped) ===")
print(json.dumps(clip(first_jsonl_line(ROOT + r"\corpus\builds\v0001\pages.jsonl")),
                  ensure_ascii=False, indent=1))

print("=== dataset 10pct/v0001 pages.jsonl (first line, clipped) ===")
print(json.dumps(clip(first_jsonl_line(ROOT + r"\datasets\10pct\v0001\pages.jsonl")),
                  ensure_ascii=False, indent=1))

print("=== dump 10pct/v0001 books.json (book 0, first page, clipped) ===")
with open(ROOT + r"\dumps\10pct\v0001\books.json", encoding="utf-8") as f:
    books = json.load(f)
b0 = dict(books[0])
b0["pages"] = [clip(b0["pages"][0])]
print(json.dumps(b0, ensure_ascii=False, indent=1))

print("=== product.json (dump 10pct/v0001) ===")
with open(ROOT + r"\dumps\10pct\v0001\product.json", encoding="utf-8") as f:
    print(f.read())

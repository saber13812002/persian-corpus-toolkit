# -*- coding: utf-8 -*-
import io, json
f = io.open("data/tasnim/pcm20_4/source-snapshot/tasnim-corpus.jsonl", encoding="utf-8")
found = []
for i, l in enumerate(f):
    r = json.loads(l)
    t = (r.get("values") or {}).get("\u0645\u062a\u0646")
    if not isinstance(t, str) or t == "":
        found.append((i, r.get("item_index"), r.get("page_id")))
    if len(found) >= 3:
        break
print("first empty:", found)

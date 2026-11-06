# -*- coding: utf-8 -*-
"""Extract the 28 at-2000 pages from the real v0001 build."""
import json
import io

P = r"data/tasnim/pcm20_5/corpus/builds/v0001/pages.jsonl"

at_cap = []
total = 0
with io.open(P, "r", encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        r = json.loads(line)
        total += 1
        t = r.get("text") or ""
        if len(t) == 2000:
            v = r.get("volume") or {}
            at_cap.append({
                "page_id": r["page_id"],
                "item_index": r.get("item_index"),
                "volume_no": v.get("volume_no"),
                "volume_title": v.get("volume_title"),
                "text_len": len(t),
                "tail": t[-40:],
            })

print("total pages:", total)
print("at-2000   :", len(at_cap))
for e in at_cap:
    print("%-18s idx=%-6s vol=%-4s %s" % (
        e["page_id"], e["item_index"], e["volume_no"], e["tail"]))

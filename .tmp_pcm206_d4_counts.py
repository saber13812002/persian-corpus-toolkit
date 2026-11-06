# -*- coding: utf-8 -*-
"""پرو브: چند عنوانِ دارای next_page در هر جلد است؟"""
import io
import json
import os
import sys

sys.path.insert(0, "deploy")
import pcm206_hc_pilot as P

build = "data/tasnim/pcm20_5/corpus/builds/v0003"
headings = P.load_headings(build)
pages = P.load_pages(build)
cands = [h for h in headings if h.get("next_page_id")]
by_vol = {}
for h in cands:
    by_vol.setdefault(h.get("volume_no"), []).append(h)
out = []
for v in sorted(by_vol, key=lambda x: (x is None, x or 0)):
    g = by_vol[v]
    # next-text موجودی هم چک کن
    ok = sum(1 for h in g if h["next_page_id"] in pages)
    out.append("vol %-4s candidates=%-6d with_next_text=%d"
               % (v, len(g), ok))
picked = P.select(headings, n=40, per_volume=8)
out.append("picked n=%d" % len(picked))
out.append("picked vol census: " + str(
    {k: sum(1 for h in picked if h.get("volume_no") == k)
     for k in sorted({h.get("volume_no") for h in picked},
                     key=lambda x: (x is None, x or 0))}))
out.append("picked missing next text: "
           + str([h["record_id"] for h in picked
                  if h["next_page_id"] not in pages]))
with io.open(".tmp_pcm206_d4_counts.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(out) + "\n")
print("\n".join(out))

# -*- coding: utf-8 -*-
"""D4 — بررسی دستی FAILهای باقی‌مانده (p90316, p39055, p39018)."""
import io
import json

RE = "data/tasnim/pcm20_6/pilot/hc-pilot.json"
PAGES = "data/tasnim/pcm20_5/corpus/builds/v0003/pages.jsonl"

WANT = {
    "hctx:tasnim_hamta__hamta-2026__vol080__p90316",
    "hctx:tasnim_hamta__hamta-2026__volkeyd531f422__p39055",
    "hctx:tasnim_hamta__hamta-2026__volkeyd531f422__p39018",
}

pg = {}
with io.open(PAGES, "r", encoding="utf-8") as f:
    for ln in f:
        ln = ln.strip()
        if not ln:
            continue
        r = json.loads(ln)
        pg[r["page_id"]] = r.get("text") or ""

with io.open(RE, "r", encoding="utf-8") as f:
    rep = json.load(f)

buf = []
for it in rep["items"]:
    if it["record_id"] not in WANT:
        continue
    nxt = pg.get(it["next_page_id"], "")
    buf.append("=== %s (next_len=%d, overlap=%.3f)"
               % (it["record_id"], len(nxt),
                  it["score"]["word_overlap"]))
    buf.append("heading: %s" % it["heading_text"])
    buf.append("NEXT PAGE: %r" % nxt[:700])
    buf.append("OUTPUT: %r" % it["output"])
    buf.append("")

with io.open(".tmp_pcm206_d4_inspect5.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(buf) + "\n")
print("written")

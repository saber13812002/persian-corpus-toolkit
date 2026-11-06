# -*- coding: utf-8 -*-
"""پرو브 ۴: بررسی دستی FAILهای صفحه‌ی بلند (>=500) — پارافرازی یا هالو؟"""
import io
import json

r = json.load(io.open("data/tasnim/pcm20_6/pilot/hc-pilot.json",
                      encoding="utf-8"))
pages = {}
with io.open("data/tasnim/pcm20_5/corpus/builds/v0003/pages.jsonl",
             encoding="utf-8") as f:
    for ln in f:
        if ln.strip():
            p = json.loads(ln)
            pages[p["page_id"]] = p.get("text") or ""

out = []
for i in r["items"]:
    if i.get("status") != "ok":
        continue
    if i["score"]["verdict"] != "FAIL":
        continue
    n = i.get("next_text_len") or 0
    if n < 500:
        continue
    nt = pages.get(i["next_page_id"], "")
    out.append("=== FAIL %s (vol %s, next_len=%d)" % (
        i["record_id"], i["volume_no"], n))
    out.append("heading: %s" % i["heading_text"])
    out.append("NEXT PAGE (first 600 chars): %r" % nt[:600])
    out.append("OUTPUT: %r" % i["output"])
    out.append("overlap: %s" % i["score"]["word_overlap"])
    out.append("")
with io.open(".tmp_pcm206_d4_inspect4.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(out))
print("written")

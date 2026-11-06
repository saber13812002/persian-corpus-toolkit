# -*- coding: utf-8 -*-
"""پرو브 ۳: شکست‌ها بر اساس طول صفحه‌ی بعدی + متن واقعی صفحات کوتاه."""
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

items = [i for i in r["items"] if i.get("status") == "ok"]
out = []


def bucket(n):
    if n < 100:
        return "<100"
    if n < 500:
        return "100..500"
    return ">=500"


buck = {}
for i in items:
    v = i["score"]["verdict"]
    b = bucket(i.get("next_text_len") or 0)
    d = buck.setdefault((v, b), [])
    d.append(i)

out.append("verdict x next-page-length:")
for (v, b), lst in sorted(buck.items(),
                           key=lambda x: (x[0][0], x[0][1])):
    ovl = [x["score"]["word_overlap"] for x in lst]
    out.append("  %-5s %-8s n=%-3d overlap min=%.3f max=%.3f" % (
        v, b, len(lst), min(ovl), max(ovl)))
out.append("")
out.append("=== FAILs with short next pages (<100): real text check ===")
for i in [x for x in items
          if x["score"]["verdict"] == "FAIL"
          and (x.get("next_text_len") or 0) < 100][:3]:
    nt = pages.get(i["next_page_id"], "<missing>")
    out.append("--- %s next_len=%d" % (i["record_id"], len(nt)))
    out.append("next: %r" % nt)
    out.append("out : %r" % i["output"])
    out.append("")
with io.open(".tmp_pcm206_d4_inspect3.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(out))
print("written")

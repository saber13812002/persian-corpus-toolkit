# -*- coding: utf-8 -*-
"""پرو브: شکل رکوردهای heading در v0003 واقعی (برای طراحی پایلوت D4)."""
import io
import json
import os

D = "data/tasnim/pcm20_5/corpus/builds/v0003"
out = []


def p(*a):
    out.append(" ".join(str(x) for x in a))


lines = io.open(os.path.join(D, "heading-records.jsonl"),
                encoding="utf-8").read().splitlines()
p("heading records:", len(lines))
recs = [json.loads(l) for l in lines if l.strip()]
p("keys:", sorted(recs[0].keys()))
p(json.dumps(recs[0], ensure_ascii=False, indent=1))

n_next = sum(1 for r in recs
             if r.get("next_page_ref") or r.get("next_page")
             or r.get("next_page_id"))
cls = {}
for r in recs:
    k = r.get("heading_type") or r.get("class") or "?"
    cls[k] = cls.get(k, 0) + 1
p("with next-page ref:", n_next)
p("type census:", cls)

# نمونه‌ای که next page دارد
for r in recs:
    if r.get("next_page_ref") or r.get("next_page") or r.get("next_page_id"):
        p("--- sample with next page ---")
        p(json.dumps(r, ensure_ascii=False, indent=1))
        break

with io.open(".tmp_pcm206_d4_shape.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(out) + "\n")
print("written .tmp_pcm206_d4_shape.txt")

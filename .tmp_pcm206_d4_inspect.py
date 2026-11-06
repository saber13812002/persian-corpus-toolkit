# -*- coding: utf-8 -*-
"""پرو브: چرا همه FAIL شدند؟ نمونه‌های واقعی خروجی + نمره."""
import io
import json

D = "data/tasnim/pcm20_6/pilot/hc-pilot.json"
r = json.load(io.open(D, encoding="utf-8"))
out = []
out.append("model_id: %s" % r["model_id"])
out.append("summary: %s" % json.dumps(r["summary"], ensure_ascii=False))
out.append("")
items = [i for i in r["items"] if i.get("status") == "ok"]
out.append("ok items: %d" % len(items))
# توزیع دلایل FAIL
reasons = {}
for i in items:
    s = i["score"]
    key = "lines=%d(%s) persian=%.2f(%s) overlap=%.2f(%s)" % (
        s["n_lines"], s["lines_ok"], s["persian_ratio"], s["persian_ok"],
        s["word_overlap"], s["overlap_ok"])
    reasons[key] = reasons.get(key, 0) + 1
out.append("score distribution:")
for k, v in sorted(reasons.items(), key=lambda x: -x[1]):
    out.append("  %-70s x%d" % (k, v))
out.append("")
for i in items[:4]:
    out.append("=== %s (vol %s, %s)" % (
        i["record_id"], i["volume_no"], i["source_class"]))
    out.append("heading: %s" % i["heading_text"])
    out.append("next_text_len: %s" % i.get("next_text_len"))
    out.append("meta: %s" % json.dumps(i.get("meta"), ensure_ascii=False))
    out.append("--- output ---")
    out.append(i["output"])
    out.append("--- score ---")
    out.append(json.dumps(i["score"], ensure_ascii=False))
    out.append("")
with io.open(".tmp_pcm206_d4_inspect.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(out))
print("written")

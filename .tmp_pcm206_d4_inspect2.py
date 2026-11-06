# -*- coding: utf-8 -*-
"""پرو브 ۲: دلایل FAIL + نمونه‌های واقعی (با thinking خاموش)."""
import io
import json

r = json.load(io.open("data/tasnim/pcm20_6/pilot/hc-pilot.json",
                      encoding="utf-8"))
out = []
items = [i for i in r["items"] if i.get("status") == "ok"]

reasons = {}
for i in items:
    s = i["score"]
    key = "lines=%d persian=%.2f overlap=%.2f" % (
        s["n_lines"], s["persian_ratio"], s["word_overlap"])
    if s["verdict"] == "FAIL":
        reasons[key] = reasons.get(key, 0) + 1
out.append("FAIL distribution:")
for k, v in sorted(reasons.items(), key=lambda x: -x[1]):
    out.append("  %-45s x%d" % (k, v))
out.append("")
fails = [i for i in items if i["score"]["verdict"] == "FAIL"]
for i in fails[:6]:
    out.append("=== FAIL %s (vol %s, next_len=%s)" % (
        i["record_id"], i["volume_no"], i.get("next_text_len")))
    out.append("heading: %s" % i["heading_text"])
    out.append("output: %r" % i["output"])
    out.append("score: %s" % json.dumps(i["score"], ensure_ascii=False))
    out.append("")
out.append("=== PASS samples ===")
for i in [x for x in items if x["score"]["verdict"] == "PASS"][:2]:
    out.append("--- %s (vol %s)" % (i["record_id"], i["volume_no"]))
    out.append("heading: %s" % i["heading_text"])
    out.append("output: %r" % i["output"])
    out.append("score: %s" % json.dumps(i["score"], ensure_ascii=False))
    out.append("")
# latency stats
lats = [i["meta"]["latency_ms"] for i in items]
out.append("latency ms: min=%d med=%d max=%d" % (
    min(lats), sorted(lats)[len(lats) // 2], max(lats)))
with io.open(".tmp_pcm206_d4_inspect2.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(out))
print("written")

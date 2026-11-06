# -*- coding: utf-8 -*-
"""D5 — جمع‌آوری اعداد دقیق برای سند PCM-20.6-CORPUS-V0003.md"""
import io
import json
import os

buf = []

# 1) gap report
gp = "data/tasnim/pcm20_6/gap/gap-report.json"
if os.path.exists(gp):
    with io.open(gp, "r", encoding="utf-8") as f:
        g = json.load(f)
    buf.append("GAP: " + json.dumps(
        {k: g.get(k) for k in
         ("item_index_min", "item_index_max", "distinct", "duplicates",
          "missing", "n_runs", "live") if k in g},
        ensure_ascii=False))
else:
    buf.append("GAP: file missing: " + gp)

# 2) truncation report
tp = "data/tasnim/pcm20_5/reports/truncation/truncation-report.json"
if os.path.exists(tp):
    with io.open(tp, "r", encoding="utf-8") as f:
        t = json.load(f)
    buf.append("TRUNC: " + json.dumps(
        {k: t.get(k) for k in
         ("census", "by_volume", "content_sha256") if k in t},
        ensure_ascii=False))
    lr = t.get("live_recheck") or {}
    buf.append("TRUNC live: " + json.dumps(
        {k: lr.get(k) for k in ("status", "n", "results") if k in lr},
        ensure_ascii=False))
else:
    buf.append("TRUNC: file missing: " + tp)

# 3) pilot
pp = "data/tasnim/pcm20_6/pilot/hc-pilot.json"
with io.open(pp, "r", encoding="utf-8") as f:
    p = json.load(f)
buf.append("PILOT model_id: " + str(p.get("model_id")))
buf.append("PILOT selection: " + json.dumps(p.get("selection")))
buf.append("PILOT summary: " + json.dumps(p.get("summary")))
lats = [it["meta"]["latency_ms"] for it in p["items"]
        if it.get("meta", {}).get("latency_ms") is not None]
lats.sort()
import statistics
buf.append("PILOT latency ms: min=%d med=%d max=%d n=%d"
           % (lats[0], statistics.median(lats), lats[-1], len(lats)))
fails = [it for it in p["items"] if it.get("score", {}).get("verdict") == "FAIL"]
ol = sorted(it["score"]["word_overlap"] for it in fails)
buf.append("PILOT fail overlap: min=%.3f max=%.3f" % (ol[0], ol[-1]))
short = sum(1 for it in fails if it.get("next_text_len", 9999) < 100)
buf.append("PILOT fails next<100: %d/%d" % (short, len(fails)))
mid = sum(1 for it in fails if 100 <= it.get("next_text_len", 0) < 500)
long_ = sum(1 for it in fails if it.get("next_text_len", 0) >= 500)
buf.append("PILOT fails 100-500: %d, >=500: %d" % (mid, long_))
for it in p["items"]:
    if it["record_id"] == "hctx:tasnim_hamta__hamta-2026__vol080__p90314":
        buf.append("PILOT sample PASS: " + it["output"].replace("\n", " | "))
        break

with io.open(".tmp_pcm206_d5_docfacts.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(buf) + "\n")
print("written")

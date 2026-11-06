# -*- coding: utf-8 -*-
"""D5 — اعداد تکمیلی برای سند: live recheck truncation + manifest v0003."""
import io
import json

buf = []

with io.open("data/tasnim/pcm20_5/reports/truncation/truncation-report.json",
             "r", encoding="utf-8") as f:
    t = json.load(f)
lr = t.get("live_recheck") or {}
buf.append("TRUNC live keys: " + str(sorted(lr.keys())))
for r in lr.get("results", [])[:10]:
    buf.append("  %s -> %s live_len=%s section=%r"
               % (r.get("item_index"), r.get("status"),
                  r.get("live_len"), r.get("section")))
buf.append("TRUNC gate1_5 ref: " + str(t.get("gate1_5")))
buf.append("TRUNC contract: " + str(t.get("contract")))

with io.open("data/tasnim/pcm20_5/corpus/builds/v0003/manifest.json",
             "r", encoding="utf-8") as f:
    m = json.load(f)
d = m.get("data", m)
buf.append("V3 manifest kind/version: %s / %s"
           % (m.get("kind"), m.get("version")))
buf.append("V3 content_sha256: " + str(m.get("content_sha256")
                                        or d.get("content_sha256")))
for k in sorted(d.keys()):
    v = d[k]
    if isinstance(v, dict):
        buf.append("V3 data.%s: %s" % (k,
             json.dumps({kk: vv for kk, vv in list(v.items())[:6]
                         if not isinstance(vv, (list, dict))},
                        ensure_ascii=False)))

# شمارش رکوردها
import os
for fn in ("heading-records.jsonl", "hidden-context-records.jsonl",
           "context-records.jsonl", "pages.jsonl"):
    p = os.path.join("data/tasnim/pcm20_5/corpus/builds/v0003", fn)
    n = 0
    with io.open(p, "r", encoding="utf-8") as f:
        for ln in f:
            if ln.strip():
                n += 1
    buf.append("V3 %s: %d lines" % (fn, n))

with io.open(".tmp_pcm206_d5_docfacts2.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(buf) + "\n")
print("written")

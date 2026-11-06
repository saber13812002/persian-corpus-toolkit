# -*- coding: utf-8 -*-
"""D5 — جزئیات live_recheck truncation (کلید checks)."""
import io
import json

with io.open("data/tasnim/pcm20_5/reports/truncation/truncation-report.json",
             "r", encoding="utf-8") as f:
    t = json.load(f)
lr = t.get("live_recheck") or {}
buf = ["status=%s checked=%s blocked=%s live_also_at_cap=%s max_checks=%s"
       % (lr.get("status"), lr.get("checked"), lr.get("blocked"),
          lr.get("live_also_at_cap"), lr.get("max_checks"))]
for r in lr.get("checks", []):
    buf.append("  idx=%s http=%s live_len=%s status=%s section=%r"
               % (r.get("item_index"), r.get("http"),
                  r.get("live_len"), r.get("status"),
                  r.get("section")))
buf.append("at_cap page ids (first 10):")
ac = t.get("at_cap") or t.get("at_cap_pages") or []
for p in ac[:10]:
    if isinstance(p, dict):
        buf.append("  %s" % p)
    else:
        buf.append("  %s" % p)
# کلیدهای ریشه‌ای گزارش
buf.append("report top keys: " + str(sorted(t.keys())))
with io.open(".tmp_pcm206_d5_docfacts3.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(buf) + "\n")
print("written")

# -*- coding: utf-8 -*-
"""پایلوت D4 — محاسبه‌ی متریک جایگزین v2 (next→output coverage) روی اجرای
واقعی ذخیره‌شده. بدون شبکه. فقط تحلیل توزیع برای تصمیم‌گیری آستانه."""
import io
import json
import re

RE = "data/tasnim/pcm20_6/pilot/hc-pilot.json"


def norm(t):
    t = (t or "").replace("ی", "ي").replace("ک", "K")
    return re.sub(r"\s+", " ", t).strip()


def words(text, min_len=3):
    t = norm(text)
    out = set()
    for w in t.split(" "):
        w = w.strip(
            "\u060c.\u061b:!?\u0028\u0029\u005b\u005d\u007b\u007d\u00ab\u00bb"
            "\u201c\u201d\u2018\u2019\u0640-\u2014\u2026\u003c\u003e")
        if len(w) >= min_len and any(c.isalpha() for c in w):
            out.add(w)
    return out


with io.open(RE, "r", encoding="utf-8") as f:
    rep = json.load(f)

rows = []
for it in rep["items"]:
    if it.get("output") is None:
        continue
    nxt = ""
    # next_text خود را نگه نداشتیم؛ باید از pages.jsonl برداریم
    rows.append(it)

# متن صفحات بعدی را از build بیاور
import os

PAGES = "data/tasnim/pcm20_5/corpus/builds/v0003/pages.jsonl"
pg = {}
with io.open(PAGES, "r", encoding="utf-8") as f:
    for ln in f:
        ln = ln.strip()
        if not ln:
            continue
        r = json.loads(ln)
        pg[r["page_id"]] = r.get("text") or ""

out_lines = []
for it in rows:
    nxt = pg.get(it["next_page_id"])
    if nxt is None:
        continue
    nw = words(nxt)
    ow = words(it["output"])
    hits = sum(1 for w in nw if w in ow)
    cov = hits / len(nw) if nw else 0.0
    v1 = it["score"]["word_overlap"]
    out_lines.append(
        "%-52s nlen=%-5d v1_out2next=%.3f v2_next2out=%.3f v1=%s"
        % (it["record_id"], len(nxt), v1, cov,
           it["score"]["verdict"]))

out_lines.sort(key=lambda l: int(re.search(r"nlen=(\d+)", l).group(1)))
buf = "\n".join(out_lines)
with io.open(".tmp_pcm206_d4_rescore_probe.txt", "w", encoding="utf-8") as f:
    f.write(buf + "\n")

# جمع‌بندی آماری
import statistics
cavs = [float(re.search(r"v2_next2out=([\d.]+)", l).group(1))
        for l in out_lines]
fails = [float(re.search(r"v2_next2out=([\d.]+)", l).group(1))
         for l in out_lines if l.endswith("v1=FAIL")]
passes = [float(re.search(r"v2_next2out=([\d.]+)", l).group(1))
          for l in out_lines if l.endswith("v1=PASS")]
sumlines = [
    "n=%d" % len(cavs),
    "v2 min/med/max: %.3f / %.3f / %.3f"
    % (min(cavs), statistics.median(cavs), max(cavs)),
    "v1=FAIL  (n=%d) v2 min/med/max: %.3f / %.3f / %.3f"
    % (len(fails), min(fails), statistics.median(fails), max(fails)),
    "v1=PASS  (n=%d) v2 min/med/max: %.3f / %.3f / %.3f"
    % (len(passes), min(passes), statistics.median(passes), max(passes)),
    "v2 >= 0.25 : %d/37" % sum(1 for c in cavs if c >= 0.25),
    "v2 >= 0.30 : %d/37" % sum(1 for c in cavs if c >= 0.30),
    "v2 >= 0.35 : %d/37" % sum(1 for c in cavs if c >= 0.35),
    "v2 >= 0.40 : %d/37" % sum(1 for c in cavs if c >= 0.40),
    "v2 <  0.25 : %d" % sum(1 for c in cavs if c < 0.25),
]
with io.open(".tmp_pcm206_d4_rescore_probe.txt", "a", encoding="utf-8") as f:
    f.write("\n--- summary ---\n" + "\n".join(sumlines) + "\n")
print("written")

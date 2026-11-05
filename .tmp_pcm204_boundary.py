# -*- coding: utf-8 -*-
"""PCM-20.4 gate check: text-length boundary analysis (read-only, local snapshot).
Writes findings to .tmp_pcm204_boundary_out.txt (Persian-safe via file read).
"""
import json, io, os, sys

BASE = os.path.join("data", "tasnim", "pcm20_4", "source-snapshot")
L = []

with open(os.path.join(BASE, "tasnim-corpus.jsonl"), encoding="utf-8") as f:
    rows = [json.loads(l) for l in f if l.strip()]

lens = []
for r in rows:
    v = (r.get("values") or {})
    t = (v.get("متن") or "") if isinstance(v, dict) else ""
    lens.append(len(t))

import bisect
srt = sorted(lens)
def pct(p):
    if not srt: return None
    k = (len(srt)-1)*p/100
    f = int(k)
    c = min(f+1, len(srt)-1)
    return srt[f] + (srt[c]-srt[f])*(k-f)

L.append("total=%d" % len(lens))
L.append("max=%d min=%d" % (max(lens), min(lens)))
L.append("p50=%d p90=%d p95=%d p99=%d" % (pct(50), pct(90), pct(95), pct(99)))

# histogram of the upper region
buckets = {}
for x in lens:
    if x >= 1800:
        b = x//10*10
        buckets[b] = buckets.get(b, 0) + 1
L.append("--- bucket (1800+) ---")
for b in sorted(buckets):
    L.append("%d-%d: %d" % (b, b+9, buckets[b]))

# exact 2000: count + tails
at2000 = [i for i, x in enumerate(lens) if x == 2000]
L.append("count exactly 2000: %d" % len(at2000))
L.append("--- TAILS of first 6 at-2000 texts (last 120 chars, repr) ---")
for i in at2000[:6]:
    r = rows[i]
    t = (r.get("values") or {}).get("متن") or ""
    L.append("row=%d item_index=%s url=...%s" % (i, r.get("item_index"),
            (r.get("url") or "")[-40:]))
    L.append("  TAIL: %r" % t[-120:])
    L.append("  ends_with_punct: %s  last_char=%r" % (t.rstrip()[-1:] in "۔.!؟!؟.،:؛;\"'»”)", t[-1:] if t else None))

# comparison: texts of length 1950-1999 (near boundary, below cap)
near = [i for i, x in enumerate(lens) if 1900 <= x < 2000]
L.append("--- TAILS of first 4 texts in 1900..1999 (control group) ---")
for i in near[:4]:
    t = (rows[i].get("values") or {}).get("متن") or ""
    L.append("row=%d len=%d" % (i, len(t)))
    L.append("  TAIL: %r" % t[-120:])

# how many texts end with a complete-looking sentence vs mid-word (whole corpus)
import re
def tail_class(t):
    t2 = t.rstrip()
    if not t2: return "empty"
    return "punct" if t2[-1] in "۔.!؟.؟!،:؛;»”" else "other"
cls = {}
for i, x in enumerate(lens):
    if x == 2000:
        t = (rows[i].get("values") or {}).get("متن") or ""
        c = tail_class(t)
        cls[c] = cls.get(c, 0) + 1
L.append("--- tail class of at-2000 texts: %s" % cls)

# control: tail class of all non-empty texts
cls2 = {}
for i, x in enumerate(lens):
    if x > 0 and x < 2000:
        t = (rows[i].get("values") or {}).get("متن") or ""
        c = tail_class(t)
        cls2[c] = cls2.get(c, 0) + 1
tot2 = sum(cls2.values())
L.append("--- tail class of non-empty <2000 (n=%d): %s" % (tot2, cls2))

# check the site: does the payload JSON itself cap at 2000? sample one at-2000 URL
L.append("--- sample at-2000 records (full record, truncated values.متن) ---")
for i in at2000[:2]:
    r = dict(rows[i])
    vv = dict(r.get("values") or {})
    if "متن" in vv: vv["متن"] = vv["متن"][-160:]
    L.append(json.dumps(r, ensure_ascii=False)[:900])

with open(".tmp_pcm204_boundary_out.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(L))
print("written .tmp_pcm204_boundary_out.txt")

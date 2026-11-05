# -*- coding: utf-8 -*-
"""PCM-20.5 GATE 1 probe: short/empty record patterns (design data for
classification rules). Read-only on the PCM-20.4 source snapshot."""
import io
import json
import os
import re
import sys
from collections import Counter

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

from corpus.tasnim import reconcile as R  # noqa: E402
from corpus.tasnim import schema as S  # noqa: E402

JSONL = os.path.join(ROOT, "data", "tasnim", "pcm20_4", "source-snapshot",
                     "tasnim-corpus.jsonl")
OUT = os.path.join(ROOT, ".tmp_pcm205_gate1_classify_probe.json")

source = R.load_source(JSONL)
pages = source["pages"]
gate = R.gate_report(source)

# ---- patterns (candidates — evaluated against data, not hardcoded guesses) ----
SURAH_RE = re.compile(r"سوره")
JILD_RE = re.compile(r"جلد")
BAB_RE = re.compile(r"باب")
FASSL_RE = re.compile(r"فصل")
MAGHAZ_RE = re.compile(r"مغاز")
MOQADDMA_RE = re.compile(r"مقدمه")
AYAT_RE = re.compile(r"آیت|آیه")
BASMALA_RE = re.compile(r"بسم")
SURA_NAME_TAIL_RE = re.compile(r"سوره\s+(\S+)\s*$")

def lines_of(t):
    return [ln.strip() for ln in t.splitlines() if ln.strip()]

out = {
    "total": len(pages),
    "flag_counts": gate["quality_flag_counts"],
    "short_census": {},
    "pattern_hits": {},
    "samples": {},
    "multi_line_shorts": 0,
    "values_key_census": Counter(),
}

shorts = []
truncs = []
empties = []
for p in pages:
    t = R.text_of(p)
    flags = R.quality_flags(p, R.reparsed_barg(p), dup_index=False)
    if S.F_EMPTY in flags:
        empties.append(p)
    elif S.F_SHORT in flags:
        shorts.append(p)
    if S.F_TRUNCATED_2000 in flags:
        truncs.append(p)

# length histogram of shorts
lh = Counter()
for p in shorts:
    t = R.text_of(p)
    ln = len(t)
    if ln < 5:
        lh["1_4"] += 1
    elif ln < 10:
        lh["5_9"] += 1
    elif ln < 15:
        lh["10_14"] += 1
    else:
        lh["15_19"] += 1
out["short_census"]["length_hist"] = dict(sorted(lh.items()))
out["short_census"]["count"] = len(shorts)

# pattern census on shorts (non-empty)
hits = Counter()
multi = 0
for p in shorts:
    t = R.text_of(p)
    for k in p.get("values") or {}:
        out["values_key_census"][k] += 1
    if len(lines_of(t)) > 1:
        multi += 1
        hits["multi_line"] += 1
    if SURAH_RE.search(t):
        hits["has_sura_word"] += 1
        m = SURA_NAME_TAIL_RE.search(t)
        if m:
            hits["sura_name_tail"] += 1
            out.setdefault("sura_tail_values", Counter())[m.group(1)] += 1
    if JILD_RE.search(t):
        hits["has_jild"] += 1
    if BAB_RE.search(t):
        hits["has_bab"] += 1
    if FASSL_RE.search(t):
        hits["has_fasl"] += 1
    if MAGHAZ_RE.search(t):
        hits["has_maghaz"] += 1
    if MOQADDMA_RE.search(t):
        hits["has_moqaddma"] += 1
    if AYAT_RE.search(t):
        hits["has_ayat"] += 1
    if BASMALA_RE.search(t):
        hits["has_basmala"] += 1
    if t == t.strip():
        pass
out["short_census"]["pattern_hits"] = dict(hits)
out["multi_line_shorts"] = multi

# samples: 40 deterministic samples of shorts (every Nth)
n = len(shorts)
step = max(1, n // 40)
samples = []
for i in range(0, n, step):
    p = shorts[i]
    t = R.text_of(p)
    samples.append({
        "pos": p["_position"], "item_index": p.get("item_index"),
        "len": len(t), "text": t[:120],
        "url": (p.get("url") or "")[:110],
    })
out["samples"]["shorts"] = samples

# empty samples
out["samples"]["empties"] = [{
    "pos": p["_position"], "item_index": p.get("item_index"),
    "values_keys": sorted((p.get("values") or {}).keys()),
    "url": (p.get("url") or "")[:110],
} for p in empties[:10]]

# truncated samples: tail behavior (do they end mid-word? same tail pattern?)
t_samples = []
for p in truncs[:12]:
    t = R.text_of(p)
    t_samples.append({
        "pos": p["_position"], "item_index": p.get("item_index"),
        "tail_60": t[-60:], "head_60": t[:60],
    })
out["samples"]["truncated"] = t_samples

# what does a typical CONTENT page's first 3 lines look like (for summary design)
content_pages = [p for p in pages if len(R.text_of(p)) >= 2000]
cstep = max(1, len(content_pages) // 6)
out["samples"]["content_first3"] = []
for i in range(0, len(content_pages), cstep):
    t = R.text_of(content_pages[i])
    out["samples"]["content_first3"].append({
        "pos": content_pages[i]["_position"],
        "lines": [ln[:80] for ln in lines_of(t)[:3]],
    })

with io.open(OUT, "w", encoding="utf-8", newline="\n") as f:
    f.write(json.dumps(out, ensure_ascii=False, indent=1))
print("WROTE", OUT)

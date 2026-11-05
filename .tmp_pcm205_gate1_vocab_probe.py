# -*- coding: utf-8 -*-
"""GATE 1 read-only probe: exact short-text vocabulary + codepoints.

Reads data/tasnim/pcm20_4/source-snapshot/tasnim-corpus.jsonl (read-only),
censuses all short records (0 < len < 20) and writes
.tmp_pcm205_gate1_vocab_probe.json. No network, no writes elsewhere.
"""
import json
import os
import re
import sys
import unicodedata
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from corpus.tasnim import common as C  # noqa: E402
from corpus.tasnim import reconcile as R  # noqa: E402
from corpus.tasnim import schema as S  # noqa: E402

SRC = os.path.join("data", "tasnim", "pcm20_4", "source-snapshot",
                   "tasnim-corpus.jsonl")
OUT = ".tmp_pcm205_gate1_vocab_probe.json"

NUM_RE = re.compile(r"^\s*(\d+)[\.\u066b\u060c,\u202f\u00a0 ]+\s*\S")
SEP_RE = re.compile(r"^[\s\*\u00b7\u2022\.\-\u00b0]+$")
LETTER_RE = re.compile(r"[\u0600-\u06FF\u0750-\u077Fa-zA-Z]")


def main():
    source = R.load_source(SRC)
    shorts = Counter()
    empties = 0
    non_str_text = 0
    sura_cp = {}
    for p in source["pages"]:
        v = p.get("values") or {}
        t = v.get(S.TEXT_KEY)
        if not isinstance(t, str):
            non_str_text += 1
            continue
        if t == "":
            empties += 1
            continue
        if len(t) < 20:
            shorts[t] += 1
            nf = unicodedata.normalize("NFKC", t)
            if "سور" in nf and nf.count("سور") and len(sura_cp) < 30:
                m = re.search("سور.{0,3}", nf)
                if m and m.group(0)[:5] not in sura_cp:
                    sura_cp[m.group(0)[:5]] = [hex(ord(c)) for c in m.group(0)[:5]]

    items = sorted(shorts.items(), key=lambda kv: (-kv[1], kv[0]))
    top = items[:400]
    rare = [kv for kv in items if kv[1] < 5]

    numbered = [(t, c) for t, c in items if NUM_RE.match(C.to_ascii_digits(t))]
    seps = [(t, c) for t, c in items if SEP_RE.match(t)]
    noletters = [(t, c) for t, c in items
                 if not LETTER_RE.search(C.to_ascii_digits(t))]

    # NFKC effect on the corpus short texts: which change under NFKC?
    nfkc_changed = sum(1 for t in shorts
                       if unicodedata.normalize("NFKC", t) != t)

    out = {
        "total_pages": source["record_count"],
        "empty_exact": empties,
        "non_string_text": non_str_text,
        "short_count": sum(shorts.values()),
        "short_unique": len(shorts),
        "nfkc_changed_uniques": nfkc_changed,
        "sura_codepoints": sura_cp,
        "numbered_count": sum(c for _t, c in numbered),
        "numbered_uniques": len(numbered),
        "numbered_samples": numbered[:40],
        "separator_count": sum(c for _t, c in seps),
        "separator_uniques": len(seps),
        "separator_samples": seps[:40],
        "no_letter_count": sum(c for _t, c in noletters),
        "no_letter_uniques": len(noletters),
        "no_letter_samples": noletters[:40],
        "top_400": [{"text": t, "count": c} for t, c in top],
        "rare_lt5": {"count": sum(c for _t, c in rare),
                     "uniques": len(rare),
                     "samples": [{"text": t, "count": c} for t, c in rare[:60]]},
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print("written", OUT)
    print("short_count=%d unique=%d empties=%d nonstr=%d" %
          (out["short_count"], out["short_unique"], empties, non_str_text))
    print("numbered=%d seps=%d noletters=%d nfkc_changed=%d" %
          (out["numbered_count"], out["separator_count"],
           out["no_letter_count"], nfkc_changed))


if __name__ == "__main__":
    main()

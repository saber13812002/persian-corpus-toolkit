# -*- coding: utf-8 -*-
"""PCM-20.5 GATE 1 — probe: v0001 real build (read-only).

Check before designing the semantic layer:
  * page_id uniqueness (does the no-index page_id formula collide?)
  * how many pages have item_index None
  * quality flag census + item_index gap stats
"""
import io
import json
import os
import sys
from collections import Counter

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

BUILDS = os.path.join("data", "tasnim", "pcm20_4", "corpus", "builds", "v0001")


def main():
    with open(os.path.join(BUILDS, "corpus.json"), "r", encoding="utf-8") as f:
        corpus = json.load(f)
    st = corpus["stats"]
    out = {
        "quality_flag_counts": st["quality_flag_counts"],
        "item_index_stats": {k: st["item_index"][k] for k in
                             ("count", "min", "max", "distinct",
                              "missing_count", "dup_count")},
        "missing_runs": st["item_index"]["missing_runs"],
    }
    pages = []
    with open(os.path.join(BUILDS, "pages.jsonl"), "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                pages.append(json.loads(line))
    pids = [p["page_id"] for p in pages]
    cnt = Counter(pids)
    out["page_count"] = len(pages)
    out["distinct_page_id"] = len(set(pids))
    out["duplicate_page_id_rows"] = sum(1 for _ in pids if cnt[_] > 1)
    out["dup_pid_examples"] = sorted(
        [k for k, v in cnt.items() if v > 1])[:5]

    noidx = [p for p in pages if p["item_index"] is None]
    out["no_index_pages"] = len(noidx)
    out["no_index_sample_page_ids"] = sorted({p["page_id"] for p in noidx})[:10]
    volc = {}
    for p in noidx:
        volc[p["volume_id"]] = volc.get(p["volume_id"], 0) + 1
    out["no_index_volume_counts_top10"] = dict(
        sorted(volc.items(), key=lambda kv: -kv[1])[:10])

    with open(".tmp_pcm205_gate1_v0001_probe.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print("written .tmp_pcm205_gate1_v0001_probe.json")
    print(json.dumps({k: out[k] for k in
                      ("page_count", "distinct_page_id",
                       "duplicate_page_id_rows", "no_index_pages")},
                     ensure_ascii=False))
    print("flags:", json.dumps(out["quality_flag_counts"], ensure_ascii=False))
    print("idx  :", json.dumps(out["item_index_stats"], ensure_ascii=False))
    print("runs :", json.dumps(out["missing_runs"], ensure_ascii=False))


if __name__ == "__main__":
    main()

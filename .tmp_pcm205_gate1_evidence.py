# -*- coding: utf-8 -*-
"""GATE 1 read-only evidence collector for the report.

Writes .tmp_pcm205_gate1_evidence.json:
  * content/manifest shas of pcm20_5 v0001+v0002 and crossroot v0002
  * semantic block summary + stats.semantic from the real v0002 corpus.json
  * semantic-change.json sha
  * probe file shas
  * pcm20_4 untouched check (v0001 content sha + manifest shas of v0001/v0002/v0003)
  * registry chain listing for pcm20_5
No writes anywhere else; read-only.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from corpus.tasnim import common as C  # noqa: E402

ROOT = os.path.dirname(os.path.abspath(__file__))


def sha_file(p):
    return C.sha256_file(p) if os.path.exists(p) else None


def load(p):
    return C.read_json(p)


def main():
    out = {}

    for root in ("data/tasnim/pcm20_5", "data/tasnim/pcm20_5_crossroot"):
        entry = {}
        for v in ("v0001", "v0002"):
            b = os.path.join(ROOT, root, "corpus", "builds", v)
            mp = os.path.join(b, "manifest.json")
            if not os.path.exists(mp):
                entry[v] = None
                continue
            man = load(mp)
            d = man.get("data") or {}
            entry[v] = {
                "version": man.get("version"),
                "kind": man.get("kind"),
                "manifest_sha256": sha_file(mp),
                "content_sha256": d.get("content_sha256"),
                "pages": (d.get("stats") or {}).get("page_count"),
                "files": {k: v.get("sha256") for k, v in (d.get("files") or {}).items()},
                "prev": man.get("prev"),
                "gaps": d.get("gaps"),
            }
        out[root] = entry

    # real v0002 corpus.json semantic block (first ~600 chars of json dump)
    cpath = os.path.join(ROOT, "data/tasnim/pcm20_5/corpus/builds/v0002/corpus.json")
    corpus = load(cpath)
    sem = corpus.get("semantic") or {}
    out["v0002_semantic_block"] = sem
    out["v0002_stats_semantic"] = (corpus.get("stats") or {}).get("semantic")
    out["v0002_corpus_json_sha"] = sha_file(cpath)

    sc = os.path.join(ROOT, "data/tasnim/pcm20_5/reports/diff_v0001_v0002/semantic-change.json")
    scd = load(sc)
    out["semantic_change"] = {
        "sha256": sha_file(sc),
        "kind": scd.get("kind"),
        "counts": {k: v for k, v in scd.items()
                   if isinstance(v, int)},
        "from": scd.get("from"),
        "to": scd.get("to"),
    }

    for f in (".tmp_pcm205_gate1_v0001_probe.json",
              ".tmp_pcm205_gate1_vocab_probe.json",
              ".tmp_pcm205_gate1_classify_probe.json"):
        out.setdefault("probe_shas", {})[f] = sha_file(os.path.join(ROOT, f))

    # pcm20_4 untouched check
    p4 = {}
    for v in ("v0001", "v0002", "v0003"):
        mp = os.path.join(ROOT, "data/tasnim/pcm20_4/corpus/builds", v, "manifest.json")
        if not os.path.exists(mp):
            continue
        man = load(mp)
        p4[v] = {
            "manifest_sha256": sha_file(mp),
            "content_sha256": (man.get("data") or {}).get("content_sha256"),
        }
    out["pcm20_4_manifests"] = p4

    reg = os.path.join(ROOT, "data/tasnim/pcm20_5/manifests/registry.json")
    out["pcm20_5_registry"] = load(reg) if os.path.exists(reg) else None

    with open(os.path.join(ROOT, ".tmp_pcm205_gate1_evidence.json"),
              "w", encoding="utf-8", newline="\n") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print("written .tmp_pcm205_gate1_evidence.json")
    print("pcm20_5 v0002 content sha :",
          out["data/tasnim/pcm20_5"]["v0002"]["content_sha256"])
    print("crossroot v0002 content sha:",
          out["data/tasnim/pcm20_5_crossroot"]["v0002"]["content_sha256"])
    print("equal:", out["data/tasnim/pcm20_5"]["v0002"]["content_sha256"]
          == out["data/tasnim/pcm20_5_crossroot"]["v0002"]["content_sha256"])


if __name__ == "__main__":
    C.force_utf8_stdio()
    main()

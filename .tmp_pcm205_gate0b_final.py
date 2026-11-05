#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""GATE 0-B final: missing page_ids + live-site probes (gap recovery feasibility,
truncation feasibility) — read-only HTTP GETs to the public site only."""
import json
import os
import urllib.request

BASE = os.path.join("data", "tasnim", "pcm20_4", "source-snapshot")
JSONL = os.path.join(BASE, "tasnim-corpus.jsonl")


def main():
    pids = []
    samples = {}
    with open(JSONL, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            pids.append(r["page_id"])
            # keep one truncated-2000 url + one gap-adjacent url for probing
            t = (r.get("values") or {}).get("\u0645\u062A\u0646") or ""
            if len(t) == 2000 and "trunc_url" not in samples:
                samples["trunc_url"] = r["url"]
                samples["trunc_ii"] = r.get("item_index")

    pset = set(pids)
    lo, hi = min(pids), max(pids)
    missing_pids = sorted(set(range(lo, hi + 1)) - pset)

    probes = {
        "page_id_range": [lo, hi],
        "page_id_count": len(pids),
        "missing_page_ids": missing_pids,
        "missing_page_id_count": len(missing_pids),
        "saved_count": 45838,
        "note_saved": "45844 rows vs saved_count 45838 -> 6 rows not counted by saved_count; page_id holes = %d" % len(missing_pids),
    }

    # ---- live site probes (read-only) ------------------------------------------
    def probe(url):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (compatibility-check)"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                body = resp.read().decode("utf-8", errors="replace")
                out = {"status": resp.status, "bytes": len(body)}
                try:
                    data = json.loads(body)
                    # site payload shape: dict with 'متن' / values?
                    if isinstance(data, dict):
                        keys = list(data.keys())[:10]
                        out["top_keys"] = keys
                        for k in ("\u0645\u062A\u0646", "text", "content", "payload"):
                            if k in data and isinstance(data[k], str):
                                out["text_len"] = len(data[k])
                                out["text_head"] = data[k][:60]
                        # nested
                        for k in ("values", "data"):
                            if k in data and isinstance(data[k], dict):
                                sub = data[k]
                                out[k + "_keys"] = list(sub.keys())[:10]
                                for k2 in ("\u0645\u062A\u0646", "text"):
                                    if k2 in sub and isinstance(sub[k2], str):
                                        out[k2 + "_len"] = len(sub[k2])
                    elif isinstance(data, list):
                        out["list_len"] = len(data)
                        if data and isinstance(data[0], dict):
                            out["first_keys"] = list(data[0].keys())[:10]
                except Exception as e:
                    out["not_json"] = str(e)[:60]
                    out["head"] = body[:120]
                return out
        except Exception as e:
            return {"error": "%s: %s" % (type(e).__name__, str(e)[:100])}

    base_q = "https://tasnim.hamtaa.org/payload?file_id=tasnim&item_index=%d"
    gap_probes = {}
    for ii in (5000, 20000, 46000, 56000, 89900):  # inside the 5 big missing runs
        gap_probes[ii] = probe(base_q % ii)

    known_probe = probe(base_q % 39004)  # known-present (ii=39004 exists in snapshot)
    trunc_probe = probe(samples.get("trunc_url", base_q % 39137))

    probes["site_probes"] = {
        "gap_positions": gap_probes,
        "known_present_39004": known_probe,
        "truncated_39137": {"url": samples.get("trunc_url"), "result": trunc_probe},
    }

    out_path = ".tmp_pcm205_gate0b_final.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(probes, f, ensure_ascii=False, indent=1)
    print("OK written", out_path)


if __name__ == "__main__":
    main()

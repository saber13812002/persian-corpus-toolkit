#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""GATE 0 — anomaly #6 (saved 45838 vs rows 45844) + infra connectivity probe.

Part 1: find rows whose captured_at breaks monotonicity vs page_id order
(hypothesis: the 6 missing saved_count = 'updated' rows — save_page()
increments saved_count only on INSERT, not on UPDATE; see backend/projects.py).

Part 2: connectivity probes (short timeouts, no secrets printed):
  - LITELLM_API_KEY presence (existence only)
  - TCP 172.20.1.52:4000 (LiteLLM)  :22 (SSH)  :2222 (GitLab)
  - HTTPS tasnim.hamtaa.org
  - local Neo4j 7474/7687, local Docker daemon (com.docker.ip / named pipe)
  - if 4000 reachable and key set: GET /v1/models (model list is not a secret)
"""
import json
import os
import socket
import sys

BASE = os.path.join("data", "tasnim", "pcm20_4", "source-snapshot")
JSONL = os.path.join(BASE, "tasnim-corpus.jsonl")


def part1():
    rows = []
    with open(JSONL, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            rows.append({"page_id": r["page_id"], "captured_at": r["captured_at"]})
    rows.sort(key=lambda r: r["page_id"])
    n = len(rows)

    # monotonicity violations: row i earlier (smaller id) has later timestamp
    later_ts = []   # rows whose captured_at > next row's (row captured later than a newer row)
    earlier_ts = []  # rows whose captured_at < previous row's
    for i in range(1, n):
        a, b = rows[i - 1], rows[i]
        if a["captured_at"] > b["captured_at"]:
            later_ts.append({"page_id": a["page_id"], "captured_at": a["captured_at"],
                             "next_page_id": b["page_id"], "next_captured_at": b["captured_at"]})
        if a["captured_at"] < b["captured_at"] * 0 + a["captured_at"] and False:
            pass
    # also: big jumps — rows whose ts is much later than the ts at ~same crawl phase
    # find rows whose captured_at exceeds ALL rows' max in a window... simpler:
    # per-page_id ts should be non-decreasing; count total decreases:
    decreases = sum(1 for i in range(1, n) if rows[i - 1]["captured_at"] > rows[i]["captured_at"])
    max_ts = rows[-1]["captured_at"]

    # candidate updated rows: small page_id but captured_at near the end of crawl
    late_start = "2026-11-0"  # crawl tail
    tail = [r for r in rows if r["captured_at"] >= "2026-11-03 00:00"]
    # rows with page_id < 45000 but captured_at in last 3 days
    suspects = [r for r in rows if r["page_id"] < 40000 and r["captured_at"] >= "2026-11-01"]

    # global timeline
    from collections import Counter
    per_day = Counter(r["captured_at"][:10] for r in rows)

    return {
        "rows": n,
        "monotonicity_decreases": decreases,
        "decrease_examples": later_ts[:15],
        "first_row": rows[0],
        "last_row": rows[-1],
        "max_captured_at": max_ts,
        "captured_at_per_day": dict(sorted(per_day.items())),
        "tail_rows_after_11_03": len(tail),
        "suspects_early_id_late_ts": suspects,
        "suspects_count": len(suspects),
    }


def tcp(host, port, timeout=4):
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except Exception as e:
        return "%s: %s" % (type(e).__name__, str(e)[:80])


def part2():
    import urllib.request

    out = {"LITELLM_API_KEY_set": bool(os.environ.get("LITELLM_API_KEY")),
           "LITELLM_BASE_URL_env": bool(os.environ.get("LITELLM_BASE_URL"))}
    out["tcp_172.20.1.52_4000_litellm"] = tcp("172.20.1.52", 4000)
    out["tcp_172.20.1.52_22_ssh"] = tcp("172.20.1.52", 22)
    out["tcp_172.20.1.52_2222_gitlab"] = tcp("172.20.1.52", 2222)

    # local Neo4j
    out["tcp_localhost_7474"] = tcp("127.0.0.1", 7474, 2)
    out["tcp_localhost_7687"] = tcp("127.0.0.1", 7687, 2)

    # local docker daemon (Windows named pipe)
    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(3)
        s.connect(r"\\.\pipe\docker_engine")
        s.close()
        out["docker_daemon_pipe"] = True
    except Exception as e:
        out["docker_daemon_pipe"] = "%s: %s" % (type(e).__name__, str(e)[:80])

    # site reachability
    try:
        req = urllib.request.Request(
            "https://tasnim.hamtaa.org/payload?file_id=tasnim&item_index=39004",
            headers={"User-Agent": "Mozilla/5.0 (compatibility-check)"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            body = resp.read(600)
            out["site_https"] = {"status": resp.status, "bytes_head": len(body)}
    except Exception as e:
        out["site_https"] = "%s: %s" % (type(e).__name__, str(e)[:120])

    # litellm models (only if reachable + key)
    if out["tcp_172.20.1.52_4000_litellm"] is True and out["LITELLM_API_KEY_set"]:
        try:
            req = urllib.request.Request(
                "http://172.20.1.52:4000/v1/models",
                headers={"Authorization": "Bearer " + os.environ["LITELLM_API_KEY"]})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            models = [m.get("id") for m in data.get("data", [])]
            out["litellm_models"] = models
        except Exception as e:
            out["litellm_models"] = "%s: %s" % (type(e).__name__, str(e)[:120])

    return out


def main():
    res = {"saved_vs_rows_6": part1(), "infra": part2()}
    out_path = ".tmp_pcm205_gate0d_probe.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=1)
    print("OK written", out_path)


if __name__ == "__main__":
    main()

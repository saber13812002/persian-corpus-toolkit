# -*- coding: utf-8 -*-
"""GATE 0-B: extract the key audit numbers (no huge arrays) to a small file."""
import json, sys

ROOT = "data/tasnim/pcm20_4"
m = json.load(open(ROOT + r"\source-snapshot\pcm20_2_audit.json", encoding="utf-8"))

out = {}
out["gaps"] = m.get("gaps")

v = m.get("volumes", {})
out["volumes_summary"] = {
    "sections_with_volume_no": v.get("sections_with_volume_no"),
    "volume_nos": v.get("volume_nos"),
    "per_volume": [
        {k: pv[k] for k in pv if k != "missing_first_500"}
        for pv in v.get("per_volume", [])
    ],
}

swv = m.get("section_without_volume_no")
if isinstance(swv, dict):
    out["section_without_volume_no"] = {k: val for k, val in swv.items() if k != "missing_first_500"}
elif isinstance(swv, list):
    out["section_without_volume_no"] = [
        {k: val for k, val in s.items() if k != "missing_first_500"} for s in swv
    ]

iid = m.get("item_index_duplicates", {})
out["item_index_duplicates"] = {
    "keys": list(iid.keys()),
    "count": iid.get("count"),
    "rows": iid.get("duplicate_item_index_rows") or iid.get("rows"),
}
out["content_hash_duplicates"] = m.get("content_hash_duplicates")
brc = m.get("barg_reparse_check", {})
out["barg_reparse_check"] = {k: val for k, val in brc.items() if k != "examples"}
out["top_level_keys"] = list(m.keys())

with open(r".tmp_pcm205_gate0b_extract.json", "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=1)
print("OK written .tmp_pcm205_gate0b_extract.json")

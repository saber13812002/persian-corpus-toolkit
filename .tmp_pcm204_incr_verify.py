# -*- coding: utf-8 -*-
"""Verify incremental fixture outcomes in corpus v0002 (base) and v0003 (fixture)."""
import io, json, os

ROOT = "data/tasnim/pcm20_4"

def load(tag):
    d = os.path.join(ROOT, "corpus", "builds", tag)
    with io.open(os.path.join(d, "pages.jsonl"), encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]

E = []
def chk(name, cond, detail=""):
    print(("OK  " if cond else "ERR ") + name + ("" if cond else "  " + str(detail)))
    if not cond:
        E.append(name)

v2 = load("v0002")   # base (21 records)
v3 = load("v0003")   # fixture (22 records)

chk("I1 v0002 has 21 pages", len(v2) == 21, len(v2))
chk("I2 v0003 has 22 pages", len(v3) == 22, len(v3))

# dup pair in v0003 for ix 39004 (source_page_id 1)
s1_v3 = [p for p in v3 if p["source_page_id"] == 1]
chk("I3a dup row count=2 (v0003, spid=1)", len(s1_v3) == 2, len(s1_v3))
ids = sorted(p["page_id"] for p in s1_v3)
# note: ix 39004 record has a section-less URL -> unknown volume (volkey...), not vol047
chk("I3b dup ids d0/d1",
    ids == ["tasnim_hamta__hamta-2026__volkeyd531f422__p39004",
            "tasnim_hamta__hamta-2026__volkeyd531f422__p39004__d1"], ids)
chk("I3c both carry dup flag",
    all("dup_item_index" in p["quality_status"]["flags"] for p in s1_v3))
s1_v2 = [p for p in v2 if p["source_page_id"] == 1]
chk("I3d v0002 single row, no dup flag",
    len(s1_v2) == 1 and "dup_item_index" not in s1_v2[0]["quality_status"]["flags"])

# healed: spid 488 (ix 39490) — empty in v0002, ok in v0003
h2 = [p for p in v2 if p["source_page_id"] == 488]
h3 = [p for p in v3 if p["source_page_id"] == 488]
chk("I4a healed empty in v0002",
    len(h2) == 1 and "empty" in h2[0]["quality_status"]["flags"],
    h2[0]["quality_status"]["flags"] if h2 else None)
chk("I4b healed: empty flag gone",
    len(h3) == 1 and "empty" not in h3[0]["quality_status"]["flags"],
    h3[0]["quality_status"]["flags"] if h3 else None)
# no_barg may legitimately remain (source barg has no digits — data, not fixture)
print("  e488 flags v0002:", h2[0]["quality_status"]["flags"] if h2 else None)
print("  e488 flags v0003:", h3[0]["quality_status"]["flags"] if h3 else None)
print("  e488 raw_barg    :", h3[0]["raw_barg"] if h3 else None)
chk("I4c healed text non-empty", len(h3[0]["text"]) > 100 if h3 else False)

# changed: spid 4 (ix 39007)
c2 = [p for p in v2 if p["source_page_id"] == 4][0]
c3 = [p for p in v3 if p["source_page_id"] == 4][0]
chk("I5 changed text differs", c2["text"] != c3["text"])

# removed: spid 20 (ix 39023)
chk("I6a removed present in v0002", any(p["source_page_id"] == 20 for p in v2))
chk("I6b removed absent in v0003", not any(p["source_page_id"] == 20 for p in v3))

# new: ix 990001
n3 = [p for p in v3 if p["item_index"] == 990001]
chk("I7a new page in v0003", len(n3) == 1)
chk("I7b new page not in v0002", not any(p["item_index"] == 990001 for p in v2))
chk("I7c new page id",
    n3 and n3[0]["page_id"] == "tasnim_hamta__hamta-2026__vol047__p990001",
    n3[0]["page_id"] if n3 else None)
chk("I7d new page vol47", n3 and n3[0]["volume_id"].endswith("vol047"))

print()
print("INCR VERIFY: %s (%d errors)" % ("PASS" if not E else "FAIL", len(E)))
if E:
    print("failed:", E)

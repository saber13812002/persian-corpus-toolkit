# -*- coding: utf-8 -*-
"""20.4-A independent QC of the built corpus (external-consumer view).

Checks (all recomputed from files on disk, NOT from the factory's own
validate output):
  A1. pages.jsonl count == corpus.stats.page_count == source count (45844)
  A2. every page_id unique
  A3. 1:1 join source<->corpus by source_page_id; RAW text byte-identical
  A4. text_normalized == recompute policy on RAW text
  A5. content_hash / captured_at / item_index / url passthrough intact
  A6. Work -> Edition -> Volume -> Page ID chain consistent + deterministic
  A7. exactly the expected 6 volumes (1,12,47,56,80,unknown) with right counts
  A8. quality flag census matches stage-1 reference (35 empty / 12366 short
      / 28 truncated / 9 dup-index)
  A9. pages ordered by (volume, item_index) — deterministic ordering
  A10. no page deleted or invented vs source (set equality both ways)
"""
import io, json, os, sys

sys.path.insert(0, os.getcwd())
from corpus.tasnim import normalize as N

ROOT = "data/tasnim/pcm20_4"
BUILD = os.path.join(ROOT, "corpus", "builds", "v0001")
SNAP = os.path.join(ROOT, "source-snapshot", "tasnim-corpus.jsonl")

corpus = json.load(io.open(os.path.join(BUILD, "corpus.json"), encoding="utf-8"))
with io.open(os.path.join(BUILD, "pages.jsonl"), encoding="utf-8") as f:
    pages = [json.loads(l) for l in f if l.strip()]

with io.open(SNAP, encoding="utf-8") as f:
    src = [json.loads(l) for l in f if l.strip()]

E = []  # errors
def chk(name, cond, detail=""):
    tag = "OK " if cond else "ERR"
    print("%s %-28s %s" % (tag, name, detail if not cond else ""))
    if not cond:
        E.append(name)

# A1
chk("A1 counts", len(pages) == corpus["stats"]["page_count"] == len(src) == 45844,
    "pages=%d stats=%d src=%d" % (len(pages), corpus["stats"]["page_count"], len(src)))

# A2
pids = [p["page_id"] for p in pages]
chk("A2 page_id unique", len(set(pids)) == len(pids),
    "dup=%d" % (len(pids) - len(set(pids))))

# A3/A5 join + passthrough
src_by_id = {s["page_id"]: s for s in src}
corpus_by_id = {p["source_page_id"]: p for p in pages}

chk("A10a no invented page", set(corpus_by_id) <= set(src_by_id),
    "invented=%d" % len(set(corpus_by_id) - set(src_by_id)))
chk("A10b no dropped page", set(src_by_id) <= set(corpus_by_id),
    "dropped=%d" % len(set(src_by_id) - set(corpus_by_id)))

raw_mismatch = norm_mismatch = passthrough_bad = 0
policy = corpus["config"]["policy_id"]
import re
WS = re.compile(r"\s+")
for s in src:
    p = corpus_by_id.get(s["page_id"])
    if p is None:
        continue
    stext = (s.get("values") or {}).get("\u0645\u062a\u0646") or ""
    if p["text"] != stext:
        raw_mismatch += 1
        if raw_mismatch <= 3:
            print("  RAW mismatch at", s["page_id"], len(stext), len(p["text"]))
    # recompute normalized per policy spec
    expect_norm = N.normalize_text(stext, policy)
    if p["text_normalized"] != expect_norm:
        norm_mismatch += 1
        if norm_mismatch <= 3:
            print("  NORM mismatch at", s["page_id"])
    if (p["content_hash"] != s.get("content_hash")
            or p["captured_at"] != s.get("captured_at")
            or p["item_index"] != s.get("item_index")
            or p["url"] != s.get("url")):
        passthrough_bad += 1
chk("A3 RAW text identical", raw_mismatch == 0, "mismatch=%d" % raw_mismatch)
chk("A4 normalized == policy(RAW)", norm_mismatch == 0, "mismatch=%d" % norm_mismatch)
chk("A5 passthrough intact", passthrough_bad == 0, "bad=%d" % passthrough_bad)
print("  policy=%s" % policy)

# A6 ID chain
work = corpus["work"]; edition = corpus["edition"]
vols = corpus["volumes"]
vol_ids = {v["volume_id"] for v in vols}
chk("A6a edition links work", edition["work_id"] == work["work_id"])
bad_link = 0
for v in vols:
    if v["edition_id"] != edition["edition_id"]:
        bad_link += 1
for p in pages:
    if p["volume_id"] not in vol_ids:
        bad_link += 1
chk("A6b volume->edition, page->volume", bad_link == 0, "bad=%d" % bad_link)
# deterministic page_id format
import re as _re
fmt_bad = 0
for p in pages:
    m = _re.match(r"^tasnim_hamta__hamta-2026__vol(?:\d{3}|key[0-9a-f]{8})__p(?:\d+(?:__d\d+)?|key[0-9a-f]{8})$", p["page_id"])
    if not m:
        fmt_bad += 1
        if fmt_bad <= 3:
            print("  page_id fmt:", p["page_id"])
chk("A6c page_id format deterministic", fmt_bad == 0, "bad=%d" % fmt_bad)

# A7 expected volumes
got = sorted([(v["volume_no"], v["page_count"], v["volume_id"]) for v in vols],
             key=lambda t: (t[0] is None, t[0] or 0))
for g in got:
    print("  vol:", g)
expect_nos = [1, 12, 47, 56, 80, None]
chk("A7a six volumes", len(vols) == 6 and
    sorted([v["volume_no"] for v in vols], key=lambda x: (x is None, x or 0)) == expect_nos)
# volume page counts sum
chk("A7b vol counts sum", sum(v["page_count"] for v in vols) == 45844)
# per-volume expected counts from stage-1: 9,22,9391,29689,767,5966
exp_counts = {1: 9, 12: 22, 47: 9391, 56: 29689, 80: 767, None: 5966}
got_counts = {v["volume_no"]: v["page_count"] for v in vols}
chk("A7c vol counts == stage-1", got_counts == exp_counts,
    str(got_counts))

# A8 flag census
fc = corpus["stats"]["quality_flag_counts"]
print("  flags:", json.dumps(fc, ensure_ascii=False))
chk("A8a empty=35", fc.get("empty", 0) == 35, str(fc.get("empty")))
chk("A8b short=12366", fc.get("short", 0) == 12366, str(fc.get("short")))
chk("A8c truncated=28", fc.get("truncated_at_2000", 0) == 28, str(fc.get("truncated_at_2000")))
# dup index rows = 9 extra rows -> 18 rows carry dup flag
dup_flag = sum(1 for p in pages if "dup_item_index" in p["quality_status"]["flags"])
chk("A8d dup-flag rows=18", dup_flag == 18, "got=%d" % dup_flag)

# A9 ordering: pages sorted by (volume order in corpus.volumes, item_index)
vol_order = {v["volume_id"]: i for i, v in enumerate(vols)}
keys = [(vol_order[p["volume_id"]], p["item_index"] is None,
         p["item_index"] if p["item_index"] is not None else 0) for p in pages]
chk("A9 deterministic order", keys == sorted(keys))

print()
print("QC A RESULT: %s (%d errors)" % ("PASS" if not E else "FAIL", len(E)))
if E:
    print("failed:", E)

# -*- coding: utf-8 -*-
"""Gate 1.5 final check: compare snapshot texts vs LIVE site item-detail API.

Endpoint (from site bundle audit):
    GET https://tasnim.hamtaa.org/api/v1/files/tasnim/chunk-detail?item_index=N
    -> {"original_text": ..., "section": ..., "metadata": {...}, ...}

Picks: 2 items whose snapshot text is exactly 2000 chars + 3 controls
(start / mid / end of the item_index range).
"""
import io, json, re, time, urllib.request

ROOT = "data/tasnim/pcm20_4/source-snapshot"
JSONL = ROOT + r"/tasnim-corpus.jsonl"
BASE = "https://tasnim.hamtaa.org/api/v1/files/tasnim/chunk-detail?item_index="

def text_of(rec):
    v = rec.get("values") or {}
    return v.get("\u0645\u062a\u0646") or ""  # 'متن'

# ---- load snapshot, collect candidates -------------------------------------
at2000, items = [], []
with io.open(JSONL, "r", encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        rec = json.loads(line)
        idx = rec.get("item_index")
        if idx is None:
            continue
        items.append(idx)
        if len(text_of(rec)) == 2000:
            at2000.append(idx)

items_sorted = sorted(items)
picks = []
# 2 at-2000 items (spread apart)
if len(at2000) >= 2:
    picks += [at2000[0], at2000[len(at2000)//2]]
elif at2000:
    picks += at2000[:1]
# 3 controls: start, mid, end
picks += [items_sorted[50], items_sorted[len(items_sorted)//2],
          items_sorted[-50]]
picks = list(dict.fromkeys(picks))

# snapshot lookup by item_index for the picked ones (dupes possible)
snap = {}
with io.open(JSONL, "r", encoding="utf-8") as f:
    for line in f:
        rec = json.loads(line)
        if rec.get("item_index") in picks:
            snap.setdefault(rec["item_index"], []).append(rec)
snap = {k: v[0] for k, v in snap.items()}

# ---- live fetch + compare ---------------------------------------------------
def fetch(idx, tries=3):
    for a in range(tries):
        try:
            req = urllib.request.Request(BASE + str(idx),
                                         headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=40) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:
            if a == tries - 1:
                return {"_error": str(e)}
            time.sleep(3)

lines = []
lines.append("items_total=%d at2000_count=%d at2000_first=%s"
             % (len(items_sorted), len(at2000), at2000[:10]))
lines.append("range=%s..%s" % (items_sorted[0], items_sorted[-1]))
lines.append("picks=%s" % picks)

for idx in picks:
    s = snap.get(idx, {})
    st = text_of(s)
    live = fetch(idx)
    time.sleep(1.5)
    if "_error" in live:
        lines.append("\n== item %s : FETCH ERROR %s" % (idx, live["_error"]))
        continue
    lt = live.get("original_text") or ""
    lines.append("\n== item %s ==" % idx)
    lines.append("  snap_len=%d live_len=%d" % (len(st), len(lt)))
    lines.append("  exact_match=%s" % (st == lt))
    if st != lt:
        lines.append("  live_contains_snap=%s snap_contains_live=%s"
                     % (st in lt, lt in st))
        # show divergence zone
        for k in range(min(len(st), len(lt))):
            if st[k] != lt[k]:
                lines.append("  first_diff@%d: snap=%r live=%r"
                             % (k, st[k-20:k+20], lt[k-20:k+20]))
                break
    lines.append("  snap_tail=%r" % st[-60:])
    lines.append("  live_tail=%r" % lt[-60:])
    lines.append("  live_section=%r live_meta_keys=%s"
                 % (live.get("section"),
                    list((live.get("metadata") or {}).keys())
                    if isinstance(live.get("metadata"), dict) else None))

with io.open(".tmp_pcm204_livecompare_out.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(lines))
print("done", len(picks))

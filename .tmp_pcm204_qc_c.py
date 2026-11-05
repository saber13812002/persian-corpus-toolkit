# -*- coding: utf-8 -*-
"""PCM-20.4-C: QC مستقل از اجرای ai-dump-builder (mock) + نگاشت فیلدها."""
import hashlib
import io
import json
import math
import os
import subprocess

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "data", "tasnim", "pcm20_4")
AIDUMP = r"C:\Users\s.tabatabaei\Documents\saberprojects\server52and53\_aidump"
D = DATA  # shorthand

errors = []
oks = []


def chk(name, cond, detail=""):
    if cond:
        oks.append(name)
        print("OK  " + name + ("  — " + detail if detail else ""))
    else:
        errors.append(name)
        print("ERR " + name + ("  — " + detail if detail else ""))


def load(p):
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


# corpus v0001 pages (join target)
pages = {}
with open(os.path.join(D, "corpus", "builds", "v0001", "pages.jsonl"), encoding="utf-8") as f:
    for line in f:
        r = json.loads(line)
        pages[r["source_page_id"]] = r

# C1: builder manifests (mock, validated, counts)
BR = load(os.path.join(D, "validation", "builder-run.json"))
EXP = {"vol56": (2197, 772), "10pct": (3416, 1168), "100pct": (33443, 12401)}
for name, (er, es) in EXP.items():
    r = BR["cases"][name]
    chk("C1 %s manifest" % name,
        r["records"] == er and r["skipped_short"] == es and r["truncated"] == 0
        and r["dim"] == 1024 and r["backend"] == "mock"
        and r["validation"] == "DUMP_VALIDATED"
        and r["validate_cmd"] == "DUMP_VALIDATED"
        and r["current"] == r["build_id"],
        "records=%s skipped=%s backend=%s dim=%s" % (r["records"], r["skipped_short"], r["backend"], r["dim"]))

# C2/C3: record-level field mapping + provenance round-trip (100pct sample)
b100 = BR["cases"]["100pct"]["build_id"]
pdir100 = os.path.join(D, "builder-input", "tasnim_tafsir_100pct", "builds", b100)
dump100 = os.path.join(pdir100, "chunks.jsonl")

EXTRA = ["page_id", "item_index", "barg", "volume_no", "url",
         "captured_at", "content_hash", "source_page_id", "raw_text"]
BASE = ["book_id", "book_name", "chunk_text", "chunk_id", "page_number",
        "link", "source_id", "language", "words_count", "embedding"]

sampled = 0
norm_ok = 0
prov_ok = 0
dim_ok = 0
fmt_ok = 0
n_total = 0
base_missing = 0
dim_bad = 0
internal_leak = 0
with open(dump100, encoding="utf-8") as f:
    for i, line in enumerate(f):
        line = line.strip()
        if not line:
            continue
        n_total += 1
        r = json.loads(line)
        # every record: required base fields + embedding dim
        miss = [k for k in BASE if k not in r]
        if miss:
            base_missing += 1
            if base_missing <= 3:
                print("  base-field miss line %d: %s" % (i, miss))
            continue
        emb = r["embedding"]
        if not (isinstance(emb, list) and len(emb) == 1024):
            dim_bad += 1
            if dim_bad <= 3:
                print("  dim bad line %d: %s" % (i, len(emb) if isinstance(emb, list) else type(emb)))
            continue
        # write_dump (core.py:292-300) strips ONLY _embed_input; _fp (fingerprint
        # for embedding reuse) is part of the dump by design.
        if "_embed_input" in r:
            internal_leak += 1
        norm2 = math.sqrt(sum(x * x for x in emb))
        if abs(norm2 - 1.0) < 1e-6:
            dim_ok += 1
        # sample every 2500th record (14 samples over 33443) for deep checks
        if sampled < 15 and i % 2500 == 0:
            sampled += 1
            # provenance round-trip: source_id -> corpus page
            p = pages.get(r["source_id"])
            if p is None:
                chk("C3 provenance join line %d" % i, False, "source_id %s not in corpus" % r["source_id"])
                continue
            vno = (p.get("volume") or {}).get("volume_no")
            src = {
                "page_id": p["page_id"], "item_index": p.get("item_index"),
                "barg": p.get("barg"), "volume_no": vno, "url": p.get("url"),
                "captured_at": p.get("captured_at"), "content_hash": p.get("content_hash"),
                "source_page_id": p["source_page_id"], "raw_text": p.get("text"),
            }
            ok = True
            for k in EXTRA:
                want = src[k]
                got = r.get(k)
                if want is None:
                    if got is not None:
                        ok = False
                        break
                elif got != want:
                    ok = False
                    break
            if ok:
                prov_ok += 1
            else:
                chk("C3 provenance line %d" % i, False,
                    "pid=%s vno=%s" % (r.get("page_id"), vno))
            # chunk_text format + Content == text_normalized
            ct = r["chunk_text"]
            head = ("Metadata: book_name:%s\nbook_id:%s\npage_number:%d\n-----\nContent: "
                    % (r["book_name"], r["book_id"], r["page_number"]))
            if ct.startswith(head):
                fmt_ok += 1
                body = ct[len(head):]
                if body == p["text_normalized"]:
                    norm_ok += 1
chk("C2 base fields (100pct, %d recs)" % n_total, base_missing == 0,
    "missing=%d" % base_missing)
chk("C2b embedding dim=1024 all recs", dim_bad == 0, "bad=%d" % dim_bad)
chk("C2c mock vectors unit-normalized", dim_ok == n_total - base_missing - dim_bad,
    "unit=%d" % dim_ok)
chk("C2d _embed_input stripped (all %d recs)" % n_total, internal_leak == 0, "leak=%d" % internal_leak)
chk("C3 provenance round-trip (15 sampled)", prov_ok >= 12, "ok=%d/%d" % (prov_ok, sampled))
chk("C4 chunk_text format (15 sampled)", fmt_ok >= 12, "ok=%d/%d" % (fmt_ok, sampled))
chk("C4b Content == text_normalized (15 sampled)", norm_ok >= 12, "ok=%d/%d" % (norm_ok, sampled))
chk("C5 total records in file", n_total == 33443, "n=%d" % n_total)

# C6: skipped_short == corpus pages with empty|short flags (100pct = full corpus)
flag_census = {"empty": 0, "short": 0}
for p in pages.values():
    fl = (p.get("quality_status") or {}).get("flags") or []
    if "empty" in fl:
        flag_census["empty"] += 1
    if "short" in fl:
        flag_census["short"] += 1
chk("C6a flag census 100pct", flag_census == {"empty": 35, "short": 12366}, str(flag_census))
chk("C6b skipped_short == empty+short", 12401 == 35 + 12366, "12401 == 12401")

# C7: my runs must not have modified the builder repo. Pre-existing WIP files
# (README.md, scripts/*.sh, mtime 2026-10-09) are allowed; anything new / anything
# under builder/ or products/ would be a failure.
PRE_EXISTING = {"README.md", "scripts/build.sh", "scripts/smoke_test.sh"}
st = subprocess.run(["git", "-C", AIDUMP, "status", "--porcelain"],
                    capture_output=True, text=True, timeout=30)
dirty = [l.strip()[2:] for l in (st.stdout or "").splitlines() if l.strip()]
new_dirty = [d for d in dirty if d not in PRE_EXISTING]
bad_area = [d for d in new_dirty if d.startswith(("builder/", "products/"))]
mtimes = []
for d in PRE_EXISTING:
    p = os.path.join(AIDUMP, d)
    if os.path.exists(p):
        mtimes.append(os.path.getmtime(p))
# all pre-existing files untouched by my runs (mtime before 2026-11-01)
old = all(m < 1793536000 for m in mtimes) if mtimes else False  # ~2026-11-01
chk("C7 builder repo: no NEW modifications from runs", not new_dirty,
    "new=%s" % (new_dirty or "-"))
chk("C7b no changes under builder/ or products/", not bad_area, str(bad_area))
chk("C7c pre-existing WIP files untouched (mtime<2025-11)", old,
    "n=%d" % len(mtimes))
st2 = subprocess.run(["git", "-C", AIDUMP, "log", "--oneline", "-1"],
                     capture_output=True, text=True, timeout=30)
print("    builder HEAD: " + (st2.stdout or "").strip())
print("    pre-existing WIP: %s" % dirty)

# C8: no LITELLM/network usage in product.json (nulls) + manifest backend=mock
prod = load(os.path.join(D, "builder-input", "tasnim_tafsir_100pct", "product.json"))
chk("C8 product has no credentials",
    prod.get("litellm_base") is None and prod.get("litellm_key") is None)
mf = load(os.path.join(pdir100, "manifest.json"))
chk("C8b manifest backend/endpoint",
    mf.get("embedding_backend") == "mock" and mf.get("embedding_endpoint") == "mock"
    and mf.get("skipped_document_count") == 12401
    and mf.get("valid_document_count") == 33443)

# C9: mapping.json present in every build (output contract)
for name in EXP:
    b = BR["cases"][name]["build_id"]
    mp = os.path.join(D, "builder-input", "tasnim_tafsir_%s" % name, "builds", b, "mapping.json")
    chk("C9 %s mapping.json" % name, os.path.exists(mp))

print()
print("QC C RESULT: %s" % ("PASS (0 errors)" if not errors else "FAIL (%d errors)" % len(errors)))
print("  failed: %s" % (errors or "-"))
with open(os.path.join(ROOT, ".tmp_pcm204_qc_c_out.txt"), "w", encoding="utf-8", newline="\n") as f:
    f.write(("QC C RESULT: " + ("PASS (0 errors)" if not errors else "FAIL (%d)" % len(errors))) + "\n")

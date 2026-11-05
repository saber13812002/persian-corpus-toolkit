# -*- coding: utf-8 -*-
"""20.4-B independent QC of the built datasets (external-consumer view).

Checks per dataset (recomputed from files on disk, NOT from CLI output):
  B1. pages.jsonl count == expected == dataset.stats == manifest stats
  B2. page_id unique within dataset
  B3. every dataset page exists in corpus v0001 with identical RAW text
  B4. order preserved (page_id sorted, i.e. corpus order subset)
  B5. manifest._prev -> corpus v0001 + corpus content_sha256 match
  B6. file sha256 recompute == manifest.files (tamper check)
  B7. volume distribution == expected per-volume counts
  B8. vol56 dataset: only volume_no==56 pages
"""
import io, json, os, sys, hashlib

ROOT = "data/tasnim/pcm20_4"
CORPUS = os.path.join(ROOT, "corpus", "builds", "v0001")
CORPUS_CSHA = "ee87686ac49ce9c08a4a492f4f54c23ace571bb8f048aa8a0a863bece3d542d8"

def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()

with io.open(os.path.join(CORPUS, "pages.jsonl"), encoding="utf-8") as f:
    corpus_pages = {json.loads(l)["page_id"]: json.loads(l) for l in f if l.strip()}

E = []
def chk(name, cond, detail=""):
    tag = "OK " if cond else "ERR"
    print("%s %-30s %s" % (tag, name, detail if not cond else ""))
    if not cond:
        E.append(name)

# (pct_dir, version, expected_count, expected_per_vol {vol_no: selected}, is_vol_only)
CASES = [
    ("1pct",   "v0001", 458,   {47: 94, 56: 297, 80: 8, None: 59}, False),  # vol 1/12: 0 selected
    ("10pct",  "v0001", 4584,  {1: 1, 12: 2, 47: 939, 56: 2969, 80: 77, None: 596}, False),
    ("50pct",  "v0001", 22922, {1: 5, 12: 11, 47: 4696, 56: 14844, 80: 383, None: 2983}, False),
    ("90pct",  "v0001", 41260, {1: 8, 12: 20, 47: 8452, 56: 26720, 80: 690, None: 5370}, False),
    ("100pct", "v0001", 45844, {1: 9, 12: 22, 47: 9391, 56: 29689, 80: 767, None: 5966}, False),
    ("10pct",  "v0002", 2969,  {56: 2969}, True),
]

for pdir, ver, exp_count, exp_vol, vol_only in CASES:
    d = os.path.join(ROOT, "datasets", pdir, ver)
    label = "%s/%s" % (pdir, ver)
    ds = json.load(io.open(os.path.join(d, "dataset.json"), encoding="utf-8"))
    man = json.load(io.open(os.path.join(d, "manifest.json"), encoding="utf-8"))
    with io.open(os.path.join(d, "pages.jsonl"), encoding="utf-8") as f:
        pages = [json.loads(l) for l in f if l.strip()]

    # B1 counts
    ds_count = (ds.get("stats") or {}).get("selected_page_count")
    man_count = ((man.get("data") or {}).get("dataset_meta") or {}).get("stats", {}).get("selected_page_count")
    chk("%s B1 count" % label,
        len(pages) == exp_count == ds_count == man_count,
        "file=%d expect=%d ds=%s man=%s" % (len(pages), exp_count, ds_count, man_count))

    # B2 unique
    pids = [p["page_id"] for p in pages]
    chk("%s B2 unique" % label, len(set(pids)) == len(pids),
        "dup=%d" % (len(pids) - len(set(pids))))

    # B3 subset of corpus + identical text
    missing = sum(1 for pid in pids if pid not in corpus_pages)
    text_bad = sum(1 for p in pages
                   if corpus_pages.get(p["page_id"], {}).get("text") != p["text"])
    chk("%s B3 subset+text" % label, missing == 0 and text_bad == 0,
        "missing=%d textbad=%d" % (missing, text_bad))

    # B4 order
    chk("%s B4 order" % label, pids == sorted(pids))

    # B5 manifest chain
    prev = man.get("prev") or {}
    corpus_meta = (man.get("data") or {}).get("dataset_meta", {}).get("corpus", {})
    chk("%s B5 chain->corpus" % label,
        prev.get("version") == "v0001"
        and prev.get("kind") == "corpus"
        and prev.get("path_rel") == "corpus/builds/v0001/manifest.json"
        and corpus_meta.get("version") == "v0001"
        and corpus_meta.get("content_sha256") == CORPUS_CSHA,
        "prev=%s corpus=%s" % (
            json.dumps(prev, ensure_ascii=False)[:200],
            json.dumps(corpus_meta, ensure_ascii=False)[:200]))

    # B6 tamper
    files = (man.get("data") or {}).get("files") or {}
    tamper = []
    for fname, meta in files.items():
        fp = os.path.join(d, fname)
        if sha256_file(fp) != meta.get("sha256"):
            tamper.append(fname)
    chk("%s B6 sha files" % label, not tamper, str(tamper))

    # B7 volume distribution
    got_vol = {}
    for p in pages:
        vno = (p.get("volume") or {}).get("volume_no")
        got_vol[vno] = got_vol.get(vno, 0) + 1
    got_vol = {k: v for k, v in got_vol.items() if v}
    chk("%s B7 vol dist" % label, got_vol == exp_vol, str(got_vol))

    # B8 vol-only
    if vol_only:
        bad = sum(1 for p in pages if (p.get("volume") or {}).get("volume_no") != 56)
        chk("%s B8 only vol56" % label, bad == 0, "bad=%d" % bad)
        scope = (man.get("data") or {}).get("volume_scope")
        chk("%s B8b scope=56" % label,
            scope == {"volume_no": 56}, str(scope))

print()
print("QC B RESULT: %s (%d errors)" % ("PASS" if not E else "FAIL", len(E)))
if E:
    print("failed:", E)

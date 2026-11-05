# -*- coding: utf-8 -*-
"""20.4-B incremental fixture: 5 scenarios over a 21-record source.

base (v1)  = first 20 records of the real snapshot (positions 0..19,
             page_id 1..20, item_index 39004..39023)
           + record at position 486 (item_index 39490, page_id 488) —
             the FIRST genuinely EMPTY record in the snapshot.
v2 (fixture):
  HEALED   : e486 (was empty -> given a real text; flag empty -> ok)
  CHANGED  : record idx 3 (page_id 4, ix 39007) -> text edited
  REMOVED  : record idx 19 (page_id 20, ix 39023) dropped
  DUP      : exact copy of record idx 0 (page_id 1, ix 39004) appended
  NEW      : fresh page (page_id 999999, ix 990001, section-47 URL)
Expected:
  v1 corpus: 21 pages, 1 empty-flag (e486), no dup flag
  v2 corpus: 21 pages, dup pair ix 39004 (__d0/__d1), e486 flag-free
  diff v1->v2: added=1 (new), changed=2 (idx3, e486), removed=1 (idx19)
  v0001 files byte-identical after (additive — no auto-delete).
"""
import hashlib, io, json, os, subprocess, sys

ROOT = "data/tasnim/pcm20_4"
FIX = os.path.join(ROOT, "validation", "incremental-fixture")
SRC = os.path.join(ROOT, "source-snapshot", "tasnim-corpus.jsonl")

os.makedirs(os.path.join(FIX, "source-v2"), exist_ok=True)

with io.open(SRC, encoding="utf-8") as f:
    lines = []
    for i, l in enumerate(f):
        if i > 486:
            break
        lines.append(l)

base20 = [json.loads(lines[i]) for i in range(20)]
empty_rec = json.loads(lines[486])
assert (empty_rec.get("values") or {}).get("\u0645\u062a\u0646") in (None, ""), \
    "record 486 must be empty"
print("empty record:", empty_rec["page_id"], empty_rec["item_index"])

def clone(r):
    return json.loads(json.dumps(r, ensure_ascii=False))

base = [clone(r) for r in base20] + [clone(empty_rec)]

# ---------- v1 (base) ----------
jsonl_v1 = os.path.join(FIX, "source-v2", "tasnim-corpus-v1.jsonl")
with io.open(jsonl_v1, "w", encoding="utf-8", newline="\n") as f:
    for r in base:
        f.write(json.dumps(r, ensure_ascii=False) + "\n")

# ---------- v2 (fixture) ----------
v2 = [clone(r) for r in base]

# HEALED: e486 gets a real text
v2[-1]["values"]["\u0645\u062a\u0646"] = (
    "متن جبرانی: این صفحه در اسنپ‌شات اولیه بدون متن بود و در نسخه‌ی دوم "
    "منبع، متن کامل آن بازمحصول شد تا جریان ترمیم نواقص (healed) شبیه‌سازی شود."
)
# CHANGED: idx 3 text edited
v2[3]["values"]["\u0645\u062a\u0646"] = (v2[3]["values"].get("\u0645\u062a\u0646") or "") \
    + " [ویرایش‌شده در نسخه‌ی دوم منبع]"
# REMOVED: drop last of the first 20 (page_id 20, ix 39023)
removed = v2.pop(19)
# DUP: exact copy of original idx 0 (page_id 1, ix 39004)
dup = clone(base[0])
# NEW: fresh page
new = {
    "page_id": 999999,
    "url": "https://tasnim.hamtaa.org/payload?file_id=tasnim&item_index=990001&section=%D8%AC%D9%84%D8%AF-47",
    "captured_at": "2026-11-04 00:00:00",
    "content_hash": "f" * 64,
    "item_index": 990001,
    "barg": 990001,
    "values": {
        "\u0627\u062f\u0631\u0633 \u0635\u0641\u062d\u0647": "https://tasnim.hamtaa.org/payload?file_id=tasnim&item_index=990001&section=%D8%AC%D9%84%D8%AF-47",
        "\u0628\u0631\u06af": "\u0628\u0631\u06af \u06F9\u06F9\u06F0\u066A\u06F0\u06F0\u06F2",
        "\u0644\u06CC\u0646\u06A9 \u0635\u0641\u062D\u0647 \u0628\u0639\u062F": "",
        "\u0644\u06CC\u0646\u06A9 \u0635\u0641\u062D\u0647 \u0642\u0628\u0644": "",
        "\u0645\u062A\u0646": "یک صفحه‌ی کاملاً تازه که در اسنپ‌شات اول نبود و فقط در نسخه‌ی دوم منبع ظاهر شد تا جریان افزودن رکورد جدید را شبیه‌سازی کند.",
    },
}
v2.append(dup)
v2.append(new)

jsonl_v2 = os.path.join(FIX, "source-v2", "tasnim-corpus-v2.jsonl")
with io.open(jsonl_v2, "w", encoding="utf-8", newline="\n") as f:
    for r in v2:
        f.write(json.dumps(r, ensure_ascii=False) + "\n")
print("v1: %d records -> %s" % (len(base), jsonl_v1))
print("v2: %d records -> %s" % (len(v2), jsonl_v2))

# ---------- sha helper ----------
def sha256_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for c in iter(lambda: fh.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()

# ---------- run: v1 build ----------
def run_cli(args):
    r = subprocess.run([sys.executable, "-X", "utf8", "-m", "corpus.tasnim.cli"] + args,
                       capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    return r

def build_files(tag):
    d = os.path.join(ROOT, "corpus", "builds", tag)
    return {fn: sha256_file(os.path.join(d, fn))
            for fn in ("corpus.json", "pages.jsonl", "manifest.json")}

def parse_tag(out):
    for ln in out.splitlines():
        if ln.startswith("version"):
            return ln.split(":", 1)[1].strip()
    raise RuntimeError("no version line in: %s" % out)

# capture real v0001 state BEFORE any fixture build
before_real_v0001 = build_files("v0001")

r_v1 = run_cli(["build-corpus", "--jsonl", jsonl_v1, "--data-root", ROOT])
io.open(os.path.join(FIX, "build_v1_console.txt"), "w", encoding="utf-8").write(
    "rc=%d\n%s\n%s\n" % (r_v1.returncode, r_v1.stdout, r_v1.stderr))
print("v1 build rc:", r_v1.returncode)
print(r_v1.stdout)
if r_v1.returncode != 0:
    print(r_v1.stderr); sys.exit(1)
v1_tag = parse_tag(r_v1.stdout)

r_v2 = run_cli(["build-corpus", "--jsonl", jsonl_v2, "--data-root", ROOT])
io.open(os.path.join(FIX, "build_v2_console.txt"), "w", encoding="utf-8").write(
    "rc=%d\n%s\n%s\n" % (r_v2.returncode, r_v2.stdout, r_v2.stderr))
print("v2 build rc:", r_v2.returncode)
print(r_v2.stdout)
if r_v2.returncode != 0:
    print(r_v2.stderr); sys.exit(1)
v2_tag = parse_tag(r_v2.stdout)
print("v2 tag:", v2_tag)

r_val = run_cli(["validate-corpus", "--data-root", ROOT, "--build", v2_tag])
io.open(os.path.join(FIX, "validate_v2_console.txt"), "w", encoding="utf-8").write(
    "rc=%d\n%s\n%s\n" % (r_val.returncode, r_val.stdout, r_val.stderr))
print("validate v2 rc:", r_val.returncode)
print(r_val.stdout)

r_diff = run_cli(["diff", "--data-root", ROOT, "--from", v1_tag, "--to", v2_tag])
io.open(os.path.join(FIX, "diff_console.txt"), "w", encoding="utf-8").write(
    "rc=%d\n%s\n%s\n" % (r_diff.returncode, r_diff.stdout, r_diff.stderr))
print("diff rc:", r_diff.returncode)
print(r_diff.stdout)

# ---------- real v0001 untouched after fixture builds? ----------
after_real_v0001 = build_files("v0001")
print("real v0001 untouched:", before_real_v0001 == after_real_v0001)

summary = {
    "v1": v1_tag, "v2": v2_tag,
    "v1_records": len(base), "v2_records": len(v2),
    "healed": {"page_id": 488, "item_index": 39490, "was": "empty", "now": "ok"},
    "changed": {"page_id": 4, "item_index": 39007},
    "removed": {"page_id": removed["page_id"], "item_index": removed["item_index"]},
    "duplicate_of": {"page_id": 1, "item_index": 39004},
    "new": {"page_id": 999999, "item_index": 990001},
    "v0001_untouched_after_incremental_build": before_real_v0001 == after_real_v0001,
    "rc": {"build_v1": r_v1.returncode, "build_v2": r_v2.returncode,
           "validate_v2": r_val.returncode, "diff": r_diff.returncode},
}
io.open(os.path.join(FIX, "fixture_summary.json"), "w", encoding="utf-8").write(
    json.dumps(summary, ensure_ascii=False, indent=1))
print("SUMMARY WRITTEN:", json.dumps(summary, ensure_ascii=False))

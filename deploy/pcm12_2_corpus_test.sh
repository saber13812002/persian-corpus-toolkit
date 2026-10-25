#!/bin/bash
# PCM-12.2 — AT-15/16: build the corpus on an ISOLATED snapshot of the production DB.
# Read-only with respect to production: takes an online .backup, runs the unmodified
# corpus/build_corpus.py against the copy, validates JSONL, then deletes the temp tree.
# No live DB is opened for writing, no crawl is touched, no production file is modified.
set -e

D=/tmp/pct_at15
SRC=/home/saber/saberprojects/persian-corpus-toolkit

rm -rf "$D"
mkdir -p "$D/backend" "$D/work/output"

echo "=== [1] online snapshot (sqlite3 .backup — consistent, no lock on production) ==="
sqlite3 "$SRC/backend/thesaurus.db" ".backup $D/backend/thesaurus.db"
ls -lh "$D/backend/thesaurus.db"
echo "snapshot integrity_check: $(sqlite3 "$D/backend/thesaurus.db" 'PRAGMA integrity_check;')"

echo ""
echo "=== [2] snapshot counts (expected crawled_data=1099) ==="
sqlite3 "$D/backend/thesaurus.db" \
  "SELECT 'crawled_data_total', COUNT(*) FROM crawled_data;
   SELECT 'crawled_data_nonempty_title', COUNT(*) FROM crawled_data WHERE TRIM(IFNULL(title,'')) <> '';"

echo ""
echo "=== [3] copy build script UNMODIFIED ==="
cp "$SRC/corpus/build_corpus.py" "$D/work/build_corpus.py"
# DB_PATH = dirname(__file__)/../backend/thesaurus.db
# script at $D/work/build_corpus.py, cwd=$D/work  ->  DB_PATH = $D/backend/thesaurus.db  (snapshot!)
grep -n "DB_PATH\|OUTPUT_DIR" "$D/work/build_corpus.py" | head -3

echo ""
echo "=== [4] run build (isolated) ==="
PY=python3
command -v python3 >/dev/null 2>&1 || PY="$SRC/backend/.venv/bin/python"
echo "python: $PY ($("$PY" --version 2>&1))"
cd "$D/work" && "$PY" build_corpus.py

echo ""
echo "=== [5] outputs ==="
ls -lh "$D/work/output/"
echo "jsonl records: $(grep -c '' "$D/work/output/thesaurus_corpus.jsonl")"
echo "terms lines:   $(grep -c '' "$D/work/output/thesaurus_terms.txt")"
echo "--- sample records (first 2 lines of JSONL) ---"
head -2 "$D/work/output/thesaurus_corpus.jsonl"

echo ""
echo "=== [6] validate JSONL (every line must parse) ==="
"$PY" - "$D/work/output/thesaurus_corpus.jsonl" <<'PYEOF'
import json, sys
n = bad = empty = 0
for i, line in enumerate(open(sys.argv[1], encoding='utf-8'), 1):
    line = line.strip()
    if not line:
        continue
    n += 1
    try:
        o = json.loads(line)
    except Exception as e:
        bad += 1
        print(f"BAD line {i}: {e}")
        continue
    if not o.get('title'):
        empty += 1
print(f"jsonl: {n} records, {bad} invalid, {empty} empty-title")
PYEOF

echo ""
echo "=== [7] cleanup temp tree ==="
rm -rf "$D"
echo "AT-15/16 done"

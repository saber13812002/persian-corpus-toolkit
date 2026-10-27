#!/bin/bash
# PCM-14B.3 — Phase 4d: full test regression on s52, ISOLATED from production.
#
# Same model as pcm12_3_s52_test.sh: copy the backend package to /tmp (no
# .venv, no thesaurus.db, no data), run the whole unittest suite (5 modules)
# with the deployed .venv python. pct_test_support gives every module a
# fresh temp DB — the production DB is only QUERIED (read-only) for the
# before/after guard. The live crawl keeps running untouched.
#
# NOTE: run this BEFORE the deploy (against the old code it still passes —
# the new modules test new code and will only run meaningfully after the
# deploy; this script is re-runnable in both directions).
set -e
SRC=/home/saber/saberprojects/persian-corpus-toolkit
W=/tmp/pct14b3reg
PY="$SRC/backend/.venv/bin/python"

rm -rf "$W"
mkdir -p "$W/backend"
tar -C "$SRC/backend" --exclude=.venv --exclude=__pycache__ \
    --exclude=thesaurus.db --exclude='thesaurus.db-*' \
    -cf - . | tar -xf - -C "$W/backend"
# static dashboard next to backend so STATIC_DIR (../dashboard) resolves,
# exactly like the real deploy layout (read-only static files, no state)
cp -r "$SRC/dashboard" "$W/dashboard"

cd "$W/backend"

echo "=== [0] isolation guard: server.DB_PATH must be a temp file ==="
"$PY" - <<'PYEOF'
import tempfile
import pct_test_support, server
print("server.DB_PATH:", server.DB_PATH)
assert server.DB_PATH.startswith(tempfile.gettempdir()), "NOT ISOLATED"
assert "thesaurus" not in server.DB_PATH.lower(), "NOT ISOLATED"
print("ISOLATED: OK")
PYEOF

before_projects=$(sqlite3 "$SRC/backend/thesaurus.db" "SELECT COUNT(*) FROM projects;")
before_pages=$(sqlite3 "$SRC/backend/thesaurus.db" "SELECT COUNT(*) FROM project_pages;")
before_colls=$(sqlite3 "$SRC/backend/thesaurus.db" "SELECT COUNT(*) FROM knowledge_collections;" 2>/dev/null || echo 0)
echo "prod BEFORE: projects=$before_projects project_pages=$before_pages knowledge_collections=$before_colls"

echo ""
echo "=== [1] solo modules (5) ==="
"$PY" -m unittest test_api 2>&1 | tail -1
"$PY" -m unittest test_projects 2>&1 | tail -1
"$PY" -m unittest test_dashboard 2>&1 | tail -1
"$PY" -m unittest test_knowledge_api 2>&1 | tail -1
"$PY" -m unittest test_word_factory 2>&1 | tail -1

echo ""
echo "=== [2] combined (documented order) ==="
"$PY" -m unittest test_api test_projects test_dashboard test_knowledge_api test_word_factory 2>&1 | tail -1

echo ""
echo "=== [3] combined (reversed order) ==="
"$PY" -m unittest test_word_factory test_knowledge_api test_dashboard test_projects test_api 2>&1 | tail -1

echo ""
echo "=== [4] consecutive runs x2 ==="
"$PY" -m unittest test_api test_projects test_dashboard test_knowledge_api test_word_factory 2>&1 | tail -1
"$PY" -m unittest test_api test_projects test_dashboard test_knowledge_api test_word_factory 2>&1 | tail -1

echo ""
echo "=== [5] test discovery ==="
"$PY" -m unittest discover -s . -p "test_*.py" 2>&1 | tail -1

echo ""
echo "=== [6] prod AFTER guard (counts must be unchanged) ==="
after_projects=$(sqlite3 "$SRC/backend/thesaurus.db" "SELECT COUNT(*) FROM projects;")
after_pages=$(sqlite3 "$SRC/backend/thesaurus.db" "SELECT COUNT(*) FROM project_pages;")
after_colls=$(sqlite3 "$SRC/backend/thesaurus.db" "SELECT COUNT(*) FROM knowledge_collections;" 2>/dev/null || echo 0)
echo "prod AFTER:  projects=$after_projects project_pages=$after_pages knowledge_collections=$after_colls"
[ "$before_projects" = "$after_projects" ] || { echo "!!! projects count changed"; exit 1; }
echo "REGRESSION-OK (prod untouched)"

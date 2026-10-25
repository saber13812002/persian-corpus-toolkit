#!/bin/bash
# PCM-12.3 — verify the fixed test harness on s52 (post-migration prod host).
# READ-ONLY w.r.t. production: runs the suite in an isolated /tmp copy of the
# backend package (no .venv, no thesaurus.db copy), using the deployed .venv
# python. The live DB is only QUERIED (read-only sqlite3 CLI) for guard
# checks; the live crawl keeps running untouched.
set -e

SRC=/home/saber/saberprojects/persian-corpus-toolkit
W=/tmp/pct123
PY="$SRC/backend/.venv/bin/python"

# NB: /tmp/pct123_newtests (overlay files) is owned by the caller; keep it.
rm -rf "$W"
mkdir -p "$W/backend"
# Copy the backend package WITHOUT the venv, the production DB and pycache
tar -C "$SRC/backend" --exclude=.venv --exclude=__pycache__ \
    --exclude=thesaurus.db --exclude='thesaurus.db-*' \
    -cf - . | tar -xf - -C "$W/backend"
# Overlay the PCM-12.3 test files (scp'd to /tmp/pct123_newtests)
cp /tmp/pct123_newtests/pct_test_support.py /tmp/pct123_newtests/test_api.py \
   /tmp/pct123_newtests/test_projects.py /tmp/pct123_newtests/test_dashboard.py "$W/backend/"

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
echo "prod BEFORE: projects=$before_projects project_pages=$before_pages"

echo ""
echo "=== [1] solo modules ==="
"$PY" -m unittest test_api 2>&1 | tail -1
"$PY" -m unittest test_projects 2>&1 | tail -1
"$PY" -m unittest test_dashboard 2>&1 | tail -1

echo ""
echo "=== [2] combined (documented order) ==="
"$PY" -m unittest test_api test_projects test_dashboard 2>&1 | tail -1

echo "=== [3] combined (reversed order) ==="
"$PY" -m unittest test_dashboard test_projects test_api 2>&1 | tail -1

echo "=== [4] consecutive runs x3 ==="
"$PY" -m unittest test_api test_projects test_dashboard 2>&1 | tail -1
"$PY" -m unittest test_api test_projects test_dashboard 2>&1 | tail -1
"$PY" -m unittest test_api test_projects test_dashboard 2>&1 | tail -1

echo "=== [5] test discovery ==="
"$PY" -m unittest discover -s . -p "test_*.py" 2>&1 | tail -1

after_projects=$(sqlite3 "$SRC/backend/thesaurus.db" "SELECT COUNT(*) FROM projects;")
after_pages=$(sqlite3 "$SRC/backend/thesaurus.db" "SELECT COUNT(*) FROM project_pages;")
echo ""
echo "prod AFTER: projects=$after_projects project_pages=$after_pages"

echo ""
echo "=== [6] contamination check (must all be 0) ==="
echo -n "test-named projects in prod DB: "
sqlite3 "$SRC/backend/thesaurus.db" \
 "SELECT COUNT(*) FROM projects WHERE name LIKE 'Proj-%'
    OR name IN ('PCM-E2E-Test','DataProj','PagesProj','OtherProj','no-auth-write','Sel','Persist','Dup','T11','P1','P2','P3','A','تست','آزمایش','تفسیر تسنیم');" \
    || echo "(query failed)"
echo -n "khamenei speech_id 999001 (test fixture) in prod: "
sqlite3 "$SRC/backend/thesaurus.db" "SELECT COUNT(*) FROM khamenei_speeches WHERE speech_id='999001';" \
    || echo "(query failed)"

echo ""
echo "=== [7] live crawl still healthy ==="
sqlite3 "$SRC/backend/thesaurus.db" \
 "SELECT 'p2 cursor: ' || cursor_url FROM projects WHERE id=2;
  SELECT 'p2 saved_count: ' || saved_count FROM projects WHERE id=2;"
docker ps --format '{{.Names}} {{.Status}}' | grep -i backend || true

echo ""
echo "=== [8] cleanup ==="
rm -rf "$W" /tmp/pct123_newtests
rm -f /tmp/pct_test_*.db /tmp/pct_test_*.db-wal /tmp/pct_test_*.db-shm
echo "s52 PCM-12.3 verification done"

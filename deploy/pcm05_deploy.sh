#!/bin/bash
# PCM-05: deploy page-by-page browsing on s52 (additive, non-breaking).
# - pre/post comparison of project 2 (counters, cursor, page count)
# - online DB backup + code snapshot (rollback point)
# - rebuilds image, recreates ONLY the backend container (no down -v)
# - smoke: auth, dashboard, NEW pages list/detail endpoints, extension write API
# - regression: extension write API still works end-to-end (project + page),
#   then cleans up the throwaway project so production data is untouched
set -euo pipefail
APP=~/saberprojects/persian-corpus-toolkit
TS=$(date +%Y%m%d-%H%M%S)
mkdir -p /home/saber/backups

echo "=== 1. PRE-DEPLOY STATE (project 2 baseline) ==="
sqlite3 "$APP/backend/thesaurus.db" "SELECT 'pre', status, saved_count, skipped_count, failed_count, cursor_url FROM projects WHERE id=2;"
sqlite3 "$APP/backend/thesaurus.db" "SELECT 'pre_pages', COUNT(*), MIN(captured_at), MAX(captured_at) FROM project_pages WHERE project_id=2;"

echo "=== 2. DB online backup (rollback point) ==="
sqlite3 "$APP/backend/thesaurus.db" ".backup /home/saber/backups/thesaurus-${TS}-pcm05.db"
echo "integrity:"
sqlite3 "/home/saber/backups/thesaurus-${TS}-pcm05.db" "PRAGMA integrity_check;"
echo "backup: /home/saber/backups/thesaurus-${TS}-pcm05.db"

echo "=== 3. snapshot current deploy dir (excludes DB) ==="
tar czf /home/saber/backups/pct-deploy-${TS}-pcm05.tar.gz --exclude=backend/thesaurus.db --exclude='backend/thesaurus.db-*' -C "$(dirname $APP)" "$(basename $APP)"
echo "snapshot: /home/saber/backups/pct-deploy-${TS}-pcm05.tar.gz"

echo "=== 4. extract new code (DB file not in tar) ==="
tar xzf /tmp/pct-code.tgz -C "$APP"
ls -la "$APP/backend/" | grep -E '\.(py|txt)$'
ls -la "$APP/dashboard/"

echo "=== 5. rebuild image + recreate backend container (no down) ==="
cd "$APP"
docker compose build backend
docker compose up -d backend

echo "=== 6. wait for health ==="
ok=0
for i in $(seq 1 30); do
  if curl -sf http://127.0.0.1:5055/api/stats >/dev/null 2>&1; then ok=1; echo "healthy after ${i}s"; break; fi
  sleep 1
done
[ "$ok" = "1" ] || { echo "HEALTH CHECK FAILED"; exit 1; }

echo "=== 7. auth + dashboard smoke ==="
# password comes from the server's .env (chmod 600, gitignored) — never from the command line
ENV_PW=$(grep '^PCT_DASHBOARD_PASSWORD=' "$APP/.env" 2>/dev/null | cut -d= -f2- || true)
PCT_DASH_PW="${PCT_DASH_PW:-$ENV_PW}"
[ -n "$PCT_DASH_PW" ] || { echo "no dashboard password available (.env missing?)"; exit 1; }
echo "--- /api/auth/status ---"
curl -s http://127.0.0.1:5055/api/auth/status; echo
echo "--- /api/dashboard/projects WITHOUT cookie (expect 401) ---"
curl -s -o /dev/null -w "HTTP:%{http_code}\n" http://127.0.0.1:5055/api/dashboard/projects
echo "--- login with correct password (expect 200 + ok true) ---"
curl -s -c /tmp/pct-cookies.txt -o /dev/null -w "HTTP:%{http_code}\n" -X POST http://127.0.0.1:5055/api/auth/login -H 'Content-Type: application/json' -d "{\"password\": \"$PCT_DASH_PW\"}"
echo "--- /api/dashboard/projects WITH cookie (expect 200) ---"
curl -s -o /dev/null -w "HTTP:%{http_code}\n" -b /tmp/pct-cookies.txt "http://127.0.0.1:5055/api/dashboard/projects?per_page=5"
echo "--- /dashboard/ page (expect 200) ---"
curl -s -o /dev/null -w "HTTP:%{http_code}\n" http://127.0.0.1:5055/dashboard/

echo "=== 8. PCM-05 pages endpoints (WITH cookie) ==="
echo "--- pages list for project 2 (per_page=3, sorted id ASC) ---"
curl -s -b /tmp/pct-cookies.txt "http://127.0.0.1:5055/api/dashboard/projects/2/pages?per_page=3&sort=id&order=ASC" | python3 -c "import sys,json; d=json.load(sys.stdin); print('total:', d['total'], 'page:', d['page'], 'total_pages:', d['total_pages']); [print(' row', r['id'], r['url'][:60], 'prev:', r['prev_id'], 'next:', r['next_id']) for r in d['pages']]"
FIRST_PAGE_ID=$(curl -s -b /tmp/pct-cookies.txt "http://127.0.0.1:5055/api/dashboard/projects/2/pages?per_page=1&sort=id&order=ASC" | python3 -c "import sys,json; print(json.load(sys.stdin)['pages'][0]['id'])")
echo "--- page detail for id=$FIRST_PAGE_ID ---"
curl -s -b /tmp/pct-cookies.txt "http://127.0.0.1:5055/api/dashboard/projects/2/pages/$FIRST_PAGE_ID" | python3 -c "import sys,json; d=json.load(sys.stdin); print('id:', d['id'], 'position:', d['position'], 'field_errors:', d['field_errors']); print('url:', d['url'][:80])"
echo "--- pages list WITHOUT cookie (expect 401) ---"
curl -s -o /dev/null -w "HTTP:%{http_code}\n" "http://127.0.0.1:5055/api/dashboard/projects/2/pages"
echo "--- pages list for unknown project (expect 404) ---"
curl -s -o /dev/null -w "HTTP:%{http_code}\n" -b /tmp/pct-cookies.txt "http://127.0.0.1:5055/api/dashboard/projects/99999/pages"

echo "=== 9. extension write APIs still OPEN + write regression ==="
echo "--- GET /api/projects (expect 200, open) ---"
curl -s -o /dev/null -w "HTTP:%{http_code}\n" http://127.0.0.1:5055/api/projects
echo "--- create throwaway project (expect 200) ---"
REG_PID=$(curl -s -X POST http://127.0.0.1:5055/api/projects -H 'Content-Type: application/json' -d '{"name":"pcm05-regression","host":"pcm05-test.example"}' | python3 -c "import sys,json; print(json.load(sys.stdin)['project']['id'])")
echo "regression project id: $REG_PID"
echo "--- save a page to it (expect 200, inserted) ---"
curl -s -X POST "http://127.0.0.1:5055/api/projects/$REG_PID/pages" -H 'Content-Type: application/json' -d '{"url":"https://pcm05-test.example/page?item_index=1","values":{"متن":"pcm05 regression page"}}' | python3 -c "import sys,json; d=json.load(sys.stdin); print('ok:', d['ok'], 'status:', d['status'], 'id:', d['id'])"
echo "--- clean up regression rows (only the rows created seconds ago) ---"
sqlite3 "$APP/backend/thesaurus.db" "DELETE FROM project_pages WHERE project_id=$REG_PID; DELETE FROM project_points WHERE project_id=$REG_PID; DELETE FROM projects WHERE id=$REG_PID;"
echo "--- projects count back to 2 (expect 2) ---"
sqlite3 "$APP/backend/thesaurus.db" "SELECT COUNT(*) FROM projects;"
echo "--- regression project gone (expect 0) ---"
sqlite3 "$APP/backend/thesaurus.db" "SELECT COUNT(*) FROM projects WHERE id=$REG_PID;"

echo "=== 10. POST-DEPLOY STATE (compare with step 1) ==="
sqlite3 "$APP/backend/thesaurus.db" "SELECT 'post', status, saved_count, skipped_count, failed_count, cursor_url FROM projects WHERE id=2;"
sqlite3 "$APP/backend/thesaurus.db" "SELECT 'post_pages', COUNT(*), MIN(captured_at), MAX(captured_at) FROM project_pages WHERE project_id=2;"
echo "--- crawl continuity: sample again in 15s (page count should grow) ---"
sleep 15
sqlite3 "$APP/backend/thesaurus.db" "SELECT 'post_pages_15s', COUNT(*), MAX(captured_at) FROM project_pages WHERE project_id=2;"

echo "=== 11. DB integrity + schema ==="
sqlite3 "$APP/backend/thesaurus.db" "PRAGMA integrity_check;"
sqlite3 "$APP/backend/thesaurus.db" "PRAGMA table_info(projects);" | grep -E 'created_at|id '
sqlite3 "$APP/backend/thesaurus.db" "SELECT 'auth tables', COUNT(*) FROM sqlite_master WHERE name LIKE 'auth_%';"
rm -f /tmp/pct-cookies.txt
echo "=== DONE ==="

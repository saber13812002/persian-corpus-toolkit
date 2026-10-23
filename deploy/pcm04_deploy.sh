#!/bin/bash
# PCM-04+09: deploy dashboard projects view + password auth on s52
# - sqlite3 online backup of thesaurus.db (rollback point)
# - snapshots current deploy dir (excludes DB)
# - ensures .env exists with PCT_DASHBOARD_PASSWORD (chmod 600, never in git)
# - extracts synced code (DB file not in tar)
# - rebuilds image, recreates ONLY the backend container (no down)
set -e
APP=~/saberprojects/persian-corpus-toolkit
TS=$(date +%Y%m%d-%H%M%S)
mkdir -p /home/saber/backups

echo "=== 1. DB online backup ==="
sqlite3 "$APP/backend/thesaurus.db" ".backup /home/saber/backups/thesaurus-${TS}.db"
echo "integrity:"
sqlite3 /home/saber/backups/thesaurus-${TS}.db "PRAGMA integrity_check;"
echo "backup: /home/saber/backups/thesaurus-${TS}.db"

echo "=== 2. snapshot current deploy dir (excludes DB) ==="
tar czf /home/saber/backups/pct-deploy-${TS}.tar.gz --exclude=backend/thesaurus.db --exclude='backend/thesaurus.db-*' -C "$(dirname $APP)" "$(basename $APP)"
echo "snapshot: /home/saber/backups/pct-deploy-${TS}.tar.gz"

echo "=== 3. .env with dashboard password (chmod 600) ==="
if [ -f "$APP/.env" ]; then
  if grep -q '^PCT_DASHBOARD_PASSWORD=' "$APP/.env"; then
    echo ".env already has PCT_DASHBOARD_PASSWORD - leaving untouched"
  else
    printf '\n# PCM-09: dashboard password (plaintext only here; hashed into DB at first boot)\nPCT_DASHBOARD_PASSWORD=%s\n' "$PCT_DASH_PW" >> "$APP/.env"
  fi
else
  printf '# Persian Corpus Toolkit - server-local env (gitignored)\n\n# PCM-09: dashboard password (plaintext only here; hashed into DB at first boot)\nPCT_DASHBOARD_PASSWORD=%s\n' "$PCT_DASH_PW" > "$APP/.env"
fi
chmod 600 "$APP/.env"
echo ".env: $(wc -l < "$APP/.env") lines, perms $(stat -c '%a' "$APP/.env")"

echo "=== 4. page count BEFORE deploy (live crawl baseline) ==="
sqlite3 "$APP/backend/thesaurus.db" "SELECT 'pages', COUNT(*) FROM project_pages; SELECT 'status', status FROM projects WHERE id=2;"

echo "=== 5. extract new code (DB file not in tar) ==="
tar xzf /tmp/pct-code.tgz -C "$APP"
ls -la "$APP/backend/" | grep -E '\.(py|txt)$'

echo "=== 6. rebuild image + recreate backend container (no down) ==="
cd "$APP"
docker compose build backend
docker compose up -d backend

echo "=== 7. wait for health ==="
for i in $(seq 1 30); do
  if curl -sf http://127.0.0.1:5055/api/stats >/dev/null 2>&1; then
    echo "healthy after ${i}s"
    break
  fi
  sleep 1
done

echo "=== 8. auth + dashboard checks ==="
echo "--- /api/auth/status (expect auth_enabled true) ---"
curl -s http://127.0.0.1:5055/api/auth/status
echo
echo "--- /api/dashboard/projects WITHOUT cookie (expect 401) ---"
curl -s -w "\nHTTP:%{http_code}\n" http://127.0.0.1:5055/api/dashboard/projects
echo "--- login with correct password (expect ok true + Set-Cookie) ---"
curl -s -c /tmp/pct-cookies.txt -w "\nHTTP:%{http_code}\n" -X POST http://127.0.0.1:5055/api/auth/login -H 'Content-Type: application/json' -d @- <<EOF
{"password": "$PCT_DASH_PW"}
EOF
echo "--- /api/dashboard/projects WITH cookie (expect 200 + projects) ---"
curl -s -b /tmp/pct-cookies.txt "http://127.0.0.1:5055/api/dashboard/projects?per_page=5" | head -c 600
echo
echo "--- extension write API still OPEN (expect 200) ---"
curl -s -w "\nHTTP:%{http_code}\n" http://127.0.0.1:5055/api/projects

echo "=== 9. DB integrity + schema ==="
sqlite3 "$APP/backend/thesaurus.db" "PRAGMA integrity_check;"
sqlite3 "$APP/backend/thesaurus.db" "PRAGMA table_info(projects);" | grep -E 'created_at|id '
sqlite3 "$APP/backend/thesaurus.db" "SELECT 'auth tables', COUNT(*) FROM sqlite_master WHERE name LIKE 'auth_%';"
rm -f /tmp/pct-cookies.txt
echo "=== DONE ==="

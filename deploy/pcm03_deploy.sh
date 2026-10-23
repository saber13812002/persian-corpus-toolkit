#!/bin/bash
# PCM-03: deploy new persian-corpus-toolkit backend on s52
# - snapshots current dir (rollback), keeps thesaurus.db untouched
# - rebuilds image, recreates ONLY the backend container
set -e
APP=~/saberprojects/persian-corpus-toolkit
TS=$(date +%Y%m%d-%H%M%S)

echo "=== 1. snapshot current deploy dir (excludes DB) ==="
tar czf /home/saber/backups/pct-deploy-${TS}.tar.gz --exclude=backend/thesaurus.db --exclude='backend/thesaurus.db-*' -C "$(dirname $APP)" "$(basename $APP)"
echo "snapshot: /home/saber/backups/pct-deploy-${TS}.tar.gz"

echo "=== 2. extract new code (DB file not in tar) ==="
tar xzf /tmp/pct-code.tgz -C "$APP"
ls -la "$APP/backend/" | grep -E '\.(py|txt)$'

echo "=== 3. rebuild image + recreate backend container (no down) ==="
cd "$APP"
docker compose build backend
docker compose up -d backend

echo "=== 4. wait for health ==="
for i in $(seq 1 30); do
  if curl -sf http://127.0.0.1:5055/api/stats >/dev/null 2>&1; then
    echo "healthy after ${i}s"
    break
  fi
  sleep 1
done

echo "=== 5. endpoint checks ==="
echo "--- /api/stats ---"
curl -s http://127.0.0.1:5055/api/stats
echo
echo "--- /api/sites ---"
curl -s http://127.0.0.1:5055/api/sites | head -c 300
echo
echo "--- /api/projects (must be 200 JSON, not 404) ---"
curl -s -w "\nHTTP:%{http_code}\n" http://127.0.0.1:5055/api/projects

echo "=== 6. DB integrity + counts (unchanged?) ==="
sqlite3 "$APP/backend/thesaurus.db" "PRAGMA integrity_check;"
sqlite3 "$APP/backend/thesaurus.db" "SELECT 'crawled_data', COUNT(*) FROM crawled_data; SELECT 'crawl_queue', COUNT(*) FROM crawl_queue;"
echo "=== DONE ==="

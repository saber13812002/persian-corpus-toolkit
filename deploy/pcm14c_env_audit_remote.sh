#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════════
# PCM-14C.0 — read-only audit: which exact code is deployed/running on s52
#
# Purpose (per user request before PCM-14C planning):
#   - The deploy script pinned the *code* to commit 2ad6c53, while the repo
#     HEAD on GitHub is a855b9a (docs/scripts/report only).
#   - This script proves, file by file, which blob is on the s52 host disk,
#     which blob is baked into the running container image, and which file
#     is served from the bind-mounted ./dashboard.
#
# READ-ONLY: no mutations, no DB writes, no container recreation.
# Safe to run while the live crawl continues.
# ═══════════════════════════════════════════════════════════════════════════
set -u
APP=/home/saber/saberprojects/persian-corpus-toolkit
C=persian-corpus-toolkit-backend-1
cd "$APP" || { echo "FATAL: $APP missing"; exit 1; }

echo "== 1. host disk code identity (git blob sha) =="
for f in backend/server.py backend/knowledge_api.py backend/auth.py \
         backend/dashboard_api.py backend/projects.py backend/sciences.py \
         backend/sites.py backend/pct_test_support.py \
         backend/Dockerfile backend/requirements.txt docker-compose.yml \
         dashboard/studio.html dashboard/index.html; do
  if [ -f "$f" ]; then
    echo "$(git hash-object "$f")  $f"
  else
    echo "MISSING  $f"
  fi
done

echo "== 2. container / image identity =="
docker ps --format '{{.Names}} | {{.Image}} | {{.Status}}'
docker inspect "$C" --format 'container: image={{.Image}} created={{.Created}}' 2>/dev/null
IMG=$(docker inspect "$C" --format '{{.Image}}' 2>/dev/null)
[ -n "$IMG" ] && docker image inspect "$IMG" --format 'image:    id={{.Id}} created={{.Created}}' 2>/dev/null

echo "== 3. in-container code identity (md5 via container python) =="
docker exec "$C" python -c '
import hashlib, os
files = ["/app/server.py","/app/sciences.py","/app/sites.py","/app/projects.py",
         "/app/auth.py","/app/dashboard_api.py","/app/knowledge_api.py"]
for f in sorted(os.listdir("/app/factory")):
    files.append("/app/factory/" + f)
for p in files:
    if os.path.isfile(p):
        print(hashlib.md5(open(p,"rb").read()).hexdigest(), p)
    else:
        print("MISSING", p)
'

echo "== 4. host dashboard (bind-mounted, served to /dashboard) md5 =="
md5sum dashboard/studio.html dashboard/index.html 2>/dev/null

echo "== 5. service probes (127.0.0.1:5055) =="
curl -s -o /dev/null -w 'GET /dashboard/studio.html -> %{http_code}\n' http://127.0.0.1:5055/dashboard/studio.html
echo -n 'GET /api/auth/status -> '; curl -s http://127.0.0.1:5055/api/auth/status; echo
curl -s -o /dev/null -w 'GET /api/knowledge/collections (no cookie) -> %{http_code}\n' http://127.0.0.1:5055/api/knowledge/collections
curl -s -o /dev/null -w 'GET /api/projects (extension, open) -> %{http_code}\n' http://127.0.0.1:5055/api/projects
curl -s -o /dev/null -w 'GET /api/dashboard/projects (no cookie) -> %{http_code}\n' http://127.0.0.1:5055/api/dashboard/projects
curl -s -o /dev/null -w 'GET /api/knowledge/compatibility (no cookie) -> %{http_code}\n' http://127.0.0.1:5055/api/knowledge/compatibility

echo "== 6. DB state (read-only) =="
sqlite3 backend/thesaurus.db "PRAGMA integrity_check;
SELECT 'proj2', status, updated_at FROM projects WHERE id=2;
SELECT 'proj2_pages', COUNT(*) FROM project_pages WHERE project_id=2;
SELECT 'all_pages', COUNT(*) FROM project_pages;
SELECT 'queue', COUNT(*) FROM crawl_queue;
SELECT 'knowledge_collections', COUNT(*) FROM knowledge_collections;
SELECT 'knowledge_documents', COUNT(*) FROM knowledge_collection_documents;
SELECT 'knowledge_jobs', COUNT(*) FROM knowledge_jobs;
SELECT 'knowledge_tables', COUNT(*) FROM sqlite_master WHERE type='table' AND name LIKE 'knowledge_%';
SELECT 'v2_columns(retry_count,documents.status)',
       (SELECT COUNT(*) FROM pragma_table_info('knowledge_jobs') WHERE name='retry_count') || '/' ||
       (SELECT COUNT(*) FROM pragma_table_info('knowledge_collection_documents') WHERE name='status');" 2>&1

echo "== 7. data dir (Word store) =="
du -sh data 2>/dev/null
echo -n 'files: '; ls data/knowledge/files 2>/dev/null | wc -l
echo -n 'out:   '; ls data/knowledge/out 2>/dev/null | wc -l

echo "AUDIT-14C-DONE"

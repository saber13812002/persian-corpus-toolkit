#!/bin/bash
# PCM-14B.3 — post-deploy verification of the lazily-created knowledge schema.
# The knowledge_* tables are created on the first authenticated /api/knowledge
# request (ensure_knowledge_schema). We warm up with one login+GET, then
# verify the schema and crawl health.
set -u
APP=/home/saber/saberprojects/persian-corpus-toolkit
cd "$APP"
PW=$(grep '^PCT_DASHBOARD_PASSWORD=' .env | cut -d= -f2-)
[ -n "$PW" ] || { echo "FATAL: no password"; exit 1; }

curl -s -c /tmp/warmup-jar -X POST http://127.0.0.1:5055/api/auth/login \
  -H 'Content-Type: application/json' -d "{\"password\":\"$PW\"}" > /dev/null
code=$(curl -s -o /dev/null -w '%{http_code}' -b /tmp/warmup-jar \
  http://127.0.0.1:5055/api/knowledge/collections)
echo "warmup /api/knowledge/collections -> $code"
rm -f /tmp/warmup-jar

echo "-- integrity --"
sqlite3 backend/thesaurus.db 'PRAGMA integrity_check;'
echo "-- schema --"
sqlite3 backend/thesaurus.db \
  "SELECT 'knowledge_tables', COUNT(*) FROM sqlite_master WHERE name LIKE 'knowledge_%';
   SELECT 'jobs_retry_count_col', COUNT(*) FROM pragma_table_info('knowledge_jobs') WHERE name='retry_count';
   SELECT 'documents_status_col', COUNT(*) FROM pragma_table_info('knowledge_collection_documents') WHERE name='status';
   SELECT 'collections', COUNT(*) FROM knowledge_collections;"
echo "-- crawl after deploy --"
sqlite3 backend/thesaurus.db \
  "SELECT 'proj2_status', status FROM projects WHERE id=2;
   SELECT 'proj2_cursor', substr(cursor_url,1,80) FROM projects WHERE id=2;
   SELECT 'proj2_pages', COUNT(*) FROM project_pages WHERE project_id=2;
   SELECT 'all_pages', COUNT(*) FROM project_pages;"
echo "-- container --"
docker ps --filter name=persian-corpus-toolkit --format '{{.Names}} | {{.Status}}'

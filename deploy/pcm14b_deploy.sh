#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════════
# PCM-14B.3 — controlled deploy of PCM-14B(.2) to s52 (172.20.1.52)
#
# Code identity: commit 2ad6c53 (HEAD origin/main, GitHub)
#   blobs verified below via `git hash-object` after extraction.
#
# Safety model (AGENTS.md §2/§3 + mission PCM-14B.3):
#   1. sqlite3 online backup (WAL-safe) + integrity_check BEFORE any change
#   2. tar snapshot of the whole deploy dir (DB excluded)
#   3. code extracted from a tar built with `git archive 2ad6c53` on Windows
#      -> never rewrites thesaurus.db, .env, or data/ (untracked paths)
#   4. blob-hash verification of key files against commit 2ad6c53
#   5. `docker compose build backend && docker compose up -d backend`
#      ONLY the backend service is touched. NO `docker compose down`,
#      NO volume removal. (AGENTS.md hard rule 3)
#   6. migrations are additive-only (knowledge_schema_version 1->2,
#      ALTER TABLE ADD COLUMN / CREATE TABLE IF NOT EXISTS) and run
#      inside the single container process -> no concurrent migration.
#   7. live-crawl protection: the crawl is driven by the Chrome extension
#      (1 req / ~15s, cursor persisted per page in projects.cursor_url +
#      project_pages). A container recreation loses at most one in-flight
#      request; the UNIQUE(project_id,url) dedup + persisted cursor make
#      retries gap-free and duplicate-free. BEFORE/AFTER counters are
#      logged for the report.
#
# ROLLBACK (if step 6+ shows inconsistency):
#   a) code:   tar xzf /home/saber/backups/pct-deploy-<TS>.tar.gz -C /home/saber/saberprojects
#              docker compose build backend && docker compose up -d backend
#   b) DB:     sqlite3 /home/saber/backups/thesaurus-<TS>.db ".restore /home/saber/saberprojects/persian-corpus-toolkit/backend/thesaurus.db"
#              (only if knowledge_* tables corrupted the DB; schema change is
#              additive, so old code ignores new tables and still runs)
#   c) files:  data/ is never touched by this script; nothing to restore.
# ═══════════════════════════════════════════════════════════════════════════
set -euo pipefail
APP=/home/saber/saberprojects/persian-corpus-toolkit
TS=$(date +%Y%m%d-%H%M%S)
BK=/home/saber/backups
CODE_TGZ=/tmp/pct-code-14b3.tgz
mkdir -p "$BK"

# expected blob SHAs (git rev-parse 2ad6c53:<path>) — commit identity check
declare -A EXPECT=(
  [backend/knowledge_api.py]=b9c42b2916d948d1fefb2870b8ffc26d9ed37307
  [backend/server.py]=b0cfa21357928aa125f70f7e47a647f087fc8b78
  [backend/Dockerfile]=0d211b9b1cb4f02a229189ed8d516c7ea7262032
  [docker-compose.yml]=fc05c99800a3c70d7516ee4aa3b1332ddd2df2ec
  [dashboard/studio.html]=4c7c2a5499d8194769b9bd22d45ad272e462de7d
  [backend/test_knowledge_api.py]=2395a89169feec2540dc050e082d409b3081f845
)

STEP="init"
fail() { echo "!!! FAILED at [$STEP]: $1" ; echo "!!! rollback: see header (snapshot + DB backup at TS=$TS)" ; exit 1 ; }
trap 'fail "abnormal exit (line $LINENO)"' ERR

echo "=== 0. preconditions ==="
command -v docker >/dev/null || fail "docker missing"
[ -f "$CODE_TGZ" ] || fail "code tar not found at $CODE_TGZ (scp from Windows: git archive 2ad6c53)"
[ -f "$APP/.env" ] || fail ".env missing (refusing to touch auth config)"
cd "$APP"
docker compose config -q || fail "compose file invalid"

echo "=== 1. DB online backup (WAL-safe) + integrity ==="
sqlite3 "$APP/backend/thesaurus.db" ".backup $BK/thesaurus-${TS}.db"
[ "$(sqlite3 "$BK/thesaurus-${TS}.db" 'PRAGMA integrity_check;')" = "ok" ] || fail "backup integrity_check"
echo "backup ok: $BK/thesaurus-${TS}.db"

echo "=== 2. snapshot current deploy dir (DB excluded) ==="
tar czf "$BK/pct-deploy-${TS}.tar.gz" \
  --exclude=backend/thesaurus.db --exclude='backend/thesaurus.db-*' \
  --exclude=data \
  -C /home/saber/saberprojects persian-corpus-toolkit
echo "snapshot ok: $BK/pct-deploy-${TS}.tar.gz"

echo "=== 3. crawl BEFORE (live baseline) ==="
sqlite3 "$APP/backend/thesaurus.db" \
  "SELECT 'proj2_status', status FROM projects WHERE id=2;
   SELECT 'proj2_cursor', substr(cursor_url,1,80) FROM projects WHERE id=2;
   SELECT 'proj2_pages', COUNT(*) FROM project_pages WHERE project_id=2;
   SELECT 'all_pages', COUNT(*) FROM project_pages;
   SELECT 'queue', COUNT(*) FROM crawl_queue;"
PROJ2_BEFORE=$(sqlite3 "$APP/backend/thesaurus.db" "SELECT COUNT(*) FROM project_pages WHERE project_id=2;")

echo "=== 4. code tar (must be git archive of 2ad6c53) ==="
ls -la "$CODE_TGZ"

echo "=== 5. extract new code (DB/.env/data untouched by definition) ==="
# tar carries prefix 'persian-corpus-toolkit/' -> extract into the PARENT dir
tar xzf "$CODE_TGZ" -C "$(dirname "$APP")"
echo "-- blob-identity check vs commit 2ad6c53 --"
for f in "${!EXPECT[@]}"; do
  [ -f "$APP/$f" ] || fail "missing $f after extract"
  got=$(git hash-object "$APP/$f")
  [ "$got" = "${EXPECT[$f]}" ] || fail "blob mismatch $f: got $got want ${EXPECT[$f]}"
  echo "ok  $f"
done
[ -d "$APP/backend/factory" ] || fail "backend/factory missing after extract"

echo "=== 6. data dir (persistent Word store) — pre-create if absent, never delete ==="
if [ -d "$APP/data" ]; then
  echo "data/ exists — preserving: $(du -sh "$APP/data" | cut -f1)"
  ls "$APP/data" | head -5
else
  mkdir -p "$APP/data/knowledge/files" "$APP/data/knowledge/out"
  echo "data/ created (fresh install — nothing to preserve)"
fi

echo "=== 7. .env ensure (password untouched, chmod 600) ==="
if grep -q '^PCT_DASHBOARD_PASSWORD=' "$APP/.env"; then
  echo ".env already has PCT_DASHBOARD_PASSWORD — leaving untouched"
else
  fail ".env lacks PCT_DASHBOARD_PASSWORD (refusing to guess)"
fi
chmod 600 "$APP/.env"

echo "=== 8. rebuild image + recreate backend container (NO down, NO volume removal) ==="
OLD_IMAGE=$(docker inspect persian-corpus-toolkit-backend-1 --format '{{.Image}}' 2>/dev/null || echo none)
docker compose build backend
docker compose up -d backend
NEW_IMAGE=$(docker inspect persian-corpus-toolkit-backend-1 --format '{{.Image}}')
echo "image: $OLD_IMAGE -> $NEW_IMAGE"

echo "=== 9. health wait ==="
ok=""
for i in $(seq 1 45); do
  if curl -sf http://127.0.0.1:5055/api/stats >/dev/null 2>&1; then ok=yes; break; fi
  sleep 1
done
[ -n "$ok" ] || fail "server not healthy after 45s"
echo "healthy after ~${i}s"

echo "=== 10. smoke: new code live + auth + extension API open ==="
echo "-- /api/auth/status --"
curl -s http://127.0.0.1:5055/api/auth/status; echo
echo "-- /api/knowledge/collections NO cookie (expect 401 = new code live) --"
curl -s -o /dev/null -w 'HTTP:%{http_code}\n' http://127.0.0.1:5055/api/knowledge/collections
echo "-- /api/projects (extension, must stay OPEN, expect 200) --"
curl -s -o /dev/null -w 'HTTP:%{http_code}\n' http://127.0.0.1:5055/api/projects
echo "-- /dashboard/studio.html (expect 200) --"
curl -s -o /dev/null -w 'HTTP:%{http_code}\n' http://127.0.0.1:5055/dashboard/studio.html
echo "-- /api/dashboard/projects NO cookie (expect 401) --"
curl -s -o /dev/null -w 'HTTP:%{http_code}\n' http://127.0.0.1:5055/api/dashboard/projects

echo "=== 11. DB integrity + knowledge schema (additive) ==="
STEP="11"
[ "$(sqlite3 "$APP/backend/thesaurus.db" 'PRAGMA integrity_check;')" = "ok" ] || fail "post-deploy integrity_check"
# knowledge_* tables are created lazily (ensure_knowledge_schema) on the first
# authenticated request — warm up so the check below is meaningful.
PW11=$(grep '^PCT_DASHBOARD_PASSWORD=' "$APP/.env" | cut -d= -f2-)
curl -s -c /tmp/pct14b-warmup -X POST http://127.0.0.1:5055/api/auth/login \
  -H 'Content-Type: application/json' -d "{\"password\":\"$PW11\"}" > /dev/null
curl -s -o /dev/null -b /tmp/pct14b-warmup http://127.0.0.1:5055/api/knowledge/collections
rm -f /tmp/pct14b-warmup
[ "$(sqlite3 "$APP/backend/thesaurus.db" "SELECT COUNT(*) FROM sqlite_master WHERE name='knowledge_collections';")" = "1" ] \
  || fail "knowledge schema not created after warmup"
sqlite3 "$APP/backend/thesaurus.db" \
  "SELECT 'knowledge_tables', COUNT(*) FROM sqlite_master WHERE name LIKE 'knowledge_%';
   SELECT 'jobs_table', COUNT(*) FROM sqlite_master WHERE name='knowledge_jobs';
   SELECT 'jobs_retry_count_col', COUNT(*) FROM pragma_table_info('knowledge_jobs') WHERE name='retry_count';
   SELECT 'documents_status_col', COUNT(*) FROM pragma_table_info('knowledge_collection_documents') WHERE name='status';
   SELECT 'collections', COUNT(*) FROM knowledge_collections;"

echo "=== 12. crawl AFTER (must be >= before; cursor must advance) ==="
sleep 5
sqlite3 "$APP/backend/thesaurus.db" \
  "SELECT 'proj2_status', status FROM projects WHERE id=2;
   SELECT 'proj2_cursor', substr(cursor_url,1,80) FROM projects WHERE id=2;
   SELECT 'proj2_pages', COUNT(*) FROM project_pages WHERE project_id=2;"
PROJ2_AFTER=$(sqlite3 "$APP/backend/thesaurus.db" "SELECT COUNT(*) FROM project_pages WHERE project_id=2;")
echo "proj2 pages: before=$PROJ2_BEFORE after=$PROJ2_AFTER"
[ "$PROJ2_AFTER" -ge "$PROJ2_BEFORE" ] || fail "crawl page count decreased!"

echo "=== DEPLOY OK (TS=$TS) ==="
echo "backups: $BK/thesaurus-${TS}.db + $BK/pct-deploy-${TS}.tar.gz"
echo "next: production test suite (deploy/pcm14b3_prod_test.sh)"

#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════════
# PCM-20.9.6 — rollback for deploy/pcm2096_deploy.sh (AI-TOOLS 172.30.0.133)
#
# Usage (on AI-TOOLS, as saber):
#   PCT_TS=<TS printed by the failed deploy> bash pcm2096_rollback.sh
#   # optionally, if data rows were corrupted by the new code:
#   PCT_TS=... PCT_DB_RESTORE=1 bash pcm2096_rollback.sh
#
# What it does:
#   a) code: restore the snapshot tar that the deploy created
#            (/home/saber/backups/pct-deploy-<TS>.tar.gz, PCM-20.8-era code)
#            over the deploy dir, then `docker compose build backend &&
#            docker compose up -d backend` — ONLY the backend service,
#            NO `docker compose down`, NO volume removal.
#            The old code ignores the knowledge_pipeline_* tables (the
#            schema is purely additive), so no DB rollback is needed for
#            a code-only rollback.
#   b) DB:   only with PCT_DB_RESTORE=1: sqlite3 .restore the backup
#            /home/saber/backups/thesaurus-<TS>.db over the live DB.
#            NOTE: .restore over a WAL database needs the DB to be idle —
#            this script recreates the container AFTER the restore.
#   c) files: data/ (the persistent Word store) is NEVER touched.
#
# Pre-flight checks (read-only) run first: backup files exist, integrity
# of the backup DB, container exists, compose valid.
# ═══════════════════════════════════════════════════════════════════════════
set -euo pipefail
APP=/home/saber/saberprojects/persian-corpus-toolkit
BK=/home/saber/backups

TS="${PCT_TS:-}"
[ -n "$TS" ] || { echo "!!! set PCT_TS=<the TS printed by pcm2096_deploy.sh>"; exit 1; }
SNAP="$BK/pct-deploy-${TS}.tar.gz"
DBBAK="$BK/thesaurus-${TS}.db"

echo "=== 0. preconditions (read-only) ==="
command -v docker  >/dev/null || { echo "docker missing"; exit 1; }
command -v sqlite3 >/dev/null || { echo "sqlite3 missing"; exit 1; }
[ -f "$SNAP" ]  || { echo "snapshot missing: $SNAP (no TS=$TS found in $BK)"; exit 1; }
[ -f "$DBBAK" ] || { echo "DB backup missing: $DBBAK"; exit 1; }
[ "$(sqlite3 "$DBBAK" 'PRAGMA integrity_check;')" = "ok" ] \
  || { echo "backup integrity_check failed"; exit 1; }
[ -f "$APP/backend/thesaurus.db" ] || { echo "live DB missing — something else is wrong; stop"; exit 1; }
[ -d "$APP/data" ] && echo "data/ exists: $(du -sh "$APP/data" | cut -f1) (will be preserved)"
cd "$APP"
docker compose config -q || { echo "compose file invalid"; exit 1; }

echo "=== 1. live DB state BEFORE rollback (evidence) ==="
sqlite3 "$APP/backend/thesaurus.db" "
  SELECT 'project_pages', COUNT(*) FROM project_pages;
  SELECT 'collections',   COUNT(*) FROM knowledge_collections;
  SELECT 'documents',     COUNT(*) FROM knowledge_collection_documents;
  SELECT 'jobs',          COUNT(*) FROM knowledge_jobs;
  SELECT 'pipeline_tables', COUNT(*) FROM sqlite_master WHERE name IN ('knowledge_pipeline_runs','knowledge_pipeline_schedules');"
echo "integrity(live): $(sqlite3 "$APP/backend/thesaurus.db" 'PRAGMA integrity_check;')"

echo "=== 2. restore code snapshot (PCM-20.8-era) ==="
tar xzf "$SNAP" -C /home/saber/saberprojects
[ -f "$APP/backend/thesaurus.db" ] || { echo "live DB vanished after extract (impossible — not in tar)"; exit 1; }
[ ! -f "$APP/backend/pipeline_orchestrator.py" ] \
  && echo "pipeline_orchestrator.py gone (PCM-20.8 code restored)" \
  || echo "NOTE: pipeline_orchestrator.py still present (harmless if not imported by old server.py)"

echo "=== 3. optional DB restore (PCT_DB_RESTORE=1) ==="
if [ "${PCT_DB_RESTORE:-0}" = "1" ]; then
  # stop the writer, restore, restart (order matters for .restore on WAL)
  docker compose stop backend
  sqlite3 "$DBBAK" ".restore $APP/backend/thesaurus.db"
  [ "$(sqlite3 "$APP/backend/thesaurus.db" 'PRAGMA integrity_check;')" = "ok" ] \
    || { echo "restored DB integrity_check failed"; exit 1; }
  echo "DB restored from $DBBAK (integrity ok)"
else
  echo "PCT_DB_RESTORE not set — DB left as-is (the additive schema is safe under old code)"
fi

echo "=== 4. rebuild image + recreate backend (NO down, NO -v) ==="
docker compose build backend
docker compose up -d backend

echo "=== 5. health wait + smoke ==="
ok=""
for i in $(seq 1 60); do
  if curl -sf http://127.0.0.1:5055/api/stats >/dev/null 2>&1; then ok=yes; break; fi
  sleep 1
done
[ -n "$ok" ] || { echo "server not healthy after 60s — investigate"; exit 1; }
echo "healthy after ~${i}s"
echo "-- /api/auth/status --"
curl -s http://127.0.0.1:5055/api/auth/status; echo
echo "-- /dashboard/studio.html (expect 200) --"
curl -s -o /dev/null -w 'HTTP:%{http_code}\n' http://127.0.0.1:5055/dashboard/studio.html
echo "-- /api/knowledge/collections NO cookie (expect 401) --"
curl -s -o /dev/null -w 'HTTP:%{http_code}\n' http://127.0.0.1:5055/api/knowledge/collections

echo "=== 6. AFTER rollback (evidence) ==="
sqlite3 "$APP/backend/thesaurus.db" "
  SELECT 'project_pages', COUNT(*) FROM project_pages;
  SELECT 'collections',   COUNT(*) FROM knowledge_collections;
  SELECT 'documents',     COUNT(*) FROM knowledge_collection_documents;
  SELECT 'jobs',          COUNT(*) FROM knowledge_jobs;"
echo "integrity(after): $(sqlite3 "$APP/backend/thesaurus.db" 'PRAGMA integrity_check;')"
echo "container: $(docker inspect persian-corpus-toolkit-backend-1 --format '{{.State.Status}} (restarts: {{.RestartCount}})')"

echo "=== ROLLBACK OK (TS=$TS) ==="
echo "note: a fresh backup was taken by the deploy at $TS; the NEW deploy's"
echo "backups (if it got past step 1) are the ones used here. The next deploy"
echo "after a rollback starts from the PCM-20.8-era snapshot state."

#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════════
# PCM-20.8 — controlled deploy to s52 (172.20.1.52)
#
# What this deploy ships:
#   1. Word Factory parse perf fix (backend/factory/parser.py):
#      python-docx `para.style` is O(styles-part) PER PARAGRAPH and dominated
#      parse time on large volumes (measured: 5,344 ms for 4000 paragraphs).
#      The fix caches the resolved style name per distinct `w:pStyle` val —
#      first encounter still resolves via python-docx itself, so names /
#      blocks / losses are byte-identical. Measured: 5,344 ms -> 428 ms
#      (12.5x) on a representative Mizan-style volume; total pipeline
#      6,480 ms -> 1,555 ms. 200/200 tests green after the change.
#   2. deploy/pcm208_mizan_audit.py — read-only live audit of the Mizan
#      collection (password login support: PCT_PASSWORD or --password-file).
#   3. deploy/pcm208_mizan_local_e2e.py — local E2E driver (never touches prod).
#
# Code identity: commit 6f2ad869f50d107bc6272db635a20fd856d9bc00 (branch
#   pcm-20.6, GitHub). Blobs verified below via `git hash-object` after
#   extraction.
#
# PREP (on Windows, before SSH works):
#   git archive --format=tar.gz --prefix=persian-corpus-toolkit/ \
#       6f2ad869f50d107bc6272db635a20fd856d9bc00 -o pct-code-208.tgz
#   scp pct-code-208.tgz saber@172.20.1.52:/tmp/
#   (SSH port 22 was unreachable at audit time — see report §5.)
#
# Safety model (AGENTS.md §2/§3):
#   1. sqlite3 online backup (WAL-safe) + integrity_check BEFORE any change
#   2. tar snapshot of the whole deploy dir (DB excluded)
#   3. code extracted from `git archive 6f2ad86` — NEVER rewrites
#      thesaurus.db, .env, or data/ (all untracked -> not in the tar)
#   4. blob-hash verification of key files against commit 6f2ad86
#   5. `docker compose build backend && docker compose up -d backend` —
#      ONLY the backend service. NO `docker compose down`, NO volume removal.
#   6. No schema migration in this deploy: the new code's lazy schema
#      (knowledge_file_queue / knowledge_queue_control / works registry)
#      is additive CREATE TABLE IF NOT EXISTS, created on first request.
#   7. Live-crawl protection: crawl_queue / project_pages counters logged
#      BEFORE/AFTER and asserted not-decreasing.
#
# OPTIONAL RESUME (the «stuck» Mizan batch):
#   PCT_RESUME_BATCH=<batch_id> ./pcm208_deploy.sh
#     -> after smoke tests, POSTs /api/knowledge/import/batches/<id>/process
#     -> _submit_job is idempotent: interrupted/failed jobs re-execute,
#        successful ones are no-ops. Safe to run on an already-done batch.
#   If the batch id is unknown, run this script WITHOUT the variable:
#   step 12 prints every knowledge batch + its job state, so you can copy
#   the id and re-run with PCT_RESUME_BATCH set (or resume from the
#   Studio UI).
#
# ROLLBACK (if anything looks wrong):
#   a) code:  tar xzf /home/saber/backups/pct-deploy-<TS>.tar.gz \
#              -C /home/saber/saberprojects
#             docker compose build backend && docker compose up -d backend
#   b) DB:    sqlite3 /home/saber/backups/thesaurus-<TS>.db \
#              ".restore /home/saber/saberprojects/persian-corpus-toolkit/backend/thesaurus.db"
#             (only if data rows were corrupted; schema is additive, so old
#              code ignores new tables and keeps running)
#   c) files: data/ is never touched by this script.
# ═══════════════════════════════════════════════════════════════════════════
set -euo pipefail
APP=/home/saber/saberprojects/persian-corpus-toolkit
TS=$(date +%Y%m%d-%H%M%S)
BK=/home/saber/backups
CODE_TGZ=/tmp/pct-code-208.tgz
mkdir -p "$BK"

# expected blob SHAs (git rev-parse 6f2ad86:<path>) — commit identity check
declare -A EXPECT=(
  [backend/factory/parser.py]=f271f4ffb49a7f0e58a6f63794d47888e774dced
  [backend/knowledge_api.py]=adbbc3c509fe0dd337e9b52f00beba0e64542b87
  [backend/server.py]=b0cfa21357928aa125f70f7e47a647f087fc8b78
  [backend/Dockerfile]=0d211b9b1cb4f02a229189ed8d516c7ea7262032
  [docker-compose.yml]=fc05c99800a3c70d7516ee4aa3b1332ddd2df2ec
  [dashboard/studio.html]=12c2b78bb1a81318dbda5813354718f15e82eaa0
  [deploy/pcm208_mizan_audit.py]=a5645e1f28be5185a8c12ffdcd6eda04faffc23e
)

STEP="init"
fail() { echo "!!! FAILED at [$STEP]: $1"; echo "!!! rollback: see header (snapshot + DB backup at TS=$TS)"; exit 1; }
trap 'fail "abnormal exit (line $LINENO)"' ERR

knowledge_tables() {
  sqlite3 "$1" "SELECT COUNT(*) FROM sqlite_master WHERE name LIKE 'knowledge_%';"
}

knowledge_state() {
  # one line per metric: label value
  sqlite3 "$1" "
    SELECT 'collections', COUNT(*) FROM knowledge_collections;
    SELECT 'documents',   COUNT(*) FROM knowledge_collection_documents;
    SELECT 'docs_uploaded',  COUNT(*) FROM knowledge_collection_documents WHERE status='uploaded';
    SELECT 'docs_parsing',   COUNT(*) FROM knowledge_collection_documents WHERE status IN ('validating','parsing');
    SELECT 'docs_parsed',    COUNT(*) FROM knowledge_collection_documents WHERE status='parsed';
    SELECT 'docs_failed',    COUNT(*) FROM knowledge_collection_documents WHERE status='failed';
    SELECT 'batches',   COUNT(*) FROM knowledge_import_batches;
    SELECT 'jobs',      COUNT(*) FROM knowledge_jobs;
    SELECT 'jobs_running',     COUNT(*) FROM knowledge_jobs WHERE status='running';
    SELECT 'jobs_interrupted', COUNT(*) FROM knowledge_jobs WHERE status='interrupted';
    SELECT 'jobs_failed',      COUNT(*) FROM knowledge_jobs WHERE status='failed';" || true
}

echo "=== 0. preconditions ==="
command -v docker >/dev/null || fail "docker missing"
[ -f "$CODE_TGZ" ] || fail "code tar not found at $CODE_TGZ (build with git archive 6f2ad86, scp to s52:/tmp)"
[ -f "$APP/.env" ] || fail ".env missing (refusing to touch auth config)"
[ -f "$APP/backend/thesaurus.db" ] || fail "production DB missing — refusing"
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

echo "=== 3. BEFORE: crawl + knowledge state ==="
sqlite3 "$APP/backend/thesaurus.db" \
  "SELECT 'crawl_queue', COUNT(*) FROM crawl_queue;
   SELECT 'crawl_queue_pending', COUNT(*) FROM crawl_queue WHERE status='pending';
   SELECT 'all_pages', COUNT(*) FROM project_pages;"
KN_TABLES_BEFORE=$(knowledge_tables "$APP/backend/thesaurus.db" || echo 0)
echo "-- knowledge state (empty/absent tables tolerated on older live build) --"
knowledge_state "$APP/backend/thesaurus.db" | sed 's/^/  /'
PAGES_BEFORE=$(sqlite3 "$APP/backend/thesaurus.db" "SELECT COUNT(*) FROM project_pages;")

echo "=== 4. code tar ==="
ls -la "$CODE_TGZ"

echo "=== 5. extract new code (DB/.env/data untouched by definition) ==="
# tar carries prefix 'persian-corpus-toolkit/' -> extract into the PARENT dir
tar xzf "$CODE_TGZ" -C "$(dirname "$APP")"
echo "-- blob-identity check vs commit 6f2ad86 --"
for f in "${!EXPECT[@]}"; do
  [ -f "$APP/$f" ] || fail "missing $f after extract"
  got=$(git hash-object "$APP/$f")
  [ "$got" = "${EXPECT[$f]}" ] || fail "blob mismatch $f: got $got want ${EXPECT[$f]}"
  echo "ok  $f"
done
[ -d "$APP/backend/factory" ] || fail "backend/factory missing after extract"
[ -f "$APP/backend/thesaurus.db" ] || fail "production DB vanished after extract (should be impossible — not in tar)"

echo "=== 6. data dir (persistent Word store) — pre-create if absent, never delete ==="
if [ -d "$APP/data" ]; then
  echo "data/ exists — preserving: $(du -sh "$APP/data" | cut -f1)"
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
for i in $(seq 1 60); do
  if curl -sf http://127.0.0.1:5055/api/stats >/dev/null 2>&1; then ok=yes; break; fi
  sleep 1
done
[ -n "$ok" ] || fail "server not healthy after 60s"
echo "healthy after ~${i}s"

echo "=== 10. smoke: new code live + auth + extension API open ==="
echo "-- /api/auth/status --"
curl -s http://127.0.0.1:5055/api/auth/status; echo
echo "-- /api/knowledge/collections NO cookie (expect 401) --"
curl -s -o /dev/null -w 'HTTP:%{http_code}\n' http://127.0.0.1:5055/api/knowledge/collections
echo "-- /api/knowledge/queue/summary NO cookie (expect 401 = PCM-15 code live) --"
curl -s -o /dev/null -w 'HTTP:%{http_code}\n' http://127.0.0.1:5055/api/knowledge/queue/summary
echo "-- /api/knowledge/metadata/resolve NO cookie (expect 401/400 = PCM-14D code live) --"
curl -s -o /dev/null -w 'HTTP:%{http_code}\n' http://127.0.0.1:5055/api/knowledge/metadata/resolve
echo "-- /api/projects (extension, must stay OPEN, expect 200) --"
curl -s -o /dev/null -w 'HTTP:%{http_code}\n' http://127.0.0.1:5055/api/projects
echo "-- /dashboard/studio.html (expect 200) --"
curl -s -o /dev/null -w 'HTTP:%{http_code}\n' http://127.0.0.1:5055/dashboard/studio.html
echo "-- /api/dashboard/projects NO cookie (expect 401) --"
curl -s -o /dev/null -w 'HTTP:%{http_code}\n' http://127.0.0.1:5055/api/dashboard/projects

echo "=== 11. DB integrity + schema warmup (additive, lazy) ==="
[ "$(sqlite3 "$APP/backend/thesaurus.db" 'PRAGMA integrity_check;')" = "ok" ] || fail "post-deploy integrity_check"
PW11=$(grep '^PCT_DASHBOARD_PASSWORD=' "$APP/.env" | cut -d= -f2-)
curl -s -c /tmp/pct208-warmup -X POST http://127.0.0.1:5055/api/auth/login \
  -H 'Content-Type: application/json' -d "{\"password\":\"$PW11\"}" > /dev/null
curl -s -o /dev/null -b /tmp/pct208-warmup http://127.0.0.1:5055/api/knowledge/collections
curl -s -o /dev/null -b /tmp/pct208-warmup http://127.0.0.1:5055/api/knowledge/queue/summary
rm -f /tmp/pct208-warmup
[ "$(sqlite3 "$APP/backend/thesaurus.db" "SELECT COUNT(*) FROM sqlite_master WHERE name='knowledge_collections';")" = "1" ] \
  || fail "knowledge schema not created after warmup"
KN_TABLES_AFTER=$(knowledge_tables "$APP/backend/thesaurus.db")
echo "knowledge tables: before=$KN_TABLES_BEFORE after=$KN_TABLES_AFTER (additive growth only)"
[ "$KN_TABLES_AFTER" -ge "$KN_TABLES_BEFORE" ] || fail "knowledge table count decreased (impossible)"

echo "=== 12. AFTER: knowledge state + batches/jobs report (resume candidates) ==="
knowledge_state "$APP/backend/thesaurus.db" | sed 's/^/  /'
echo "-- collections (look for المیزان) --"
sqlite3 -header "$APP/backend/thesaurus.db" \
  "SELECT c.id, c.collection_id, c.name, c.book_count FROM knowledge_collections c ORDER BY c.id;"
echo "-- batches + latest job per batch (resume candidates: job interrupted/failed) --"
sqlite3 -header "$APP/backend/thesaurus.db" \
  "SELECT b.batch_id, b.collection_id, b.folder_name, b.file_count, b.processed_count,
          b.failed_count, b.status AS batch_status,
          j.job_id, j.status AS job_status, j.stage, j.progress, j.total,
          substr(COALESCE(j.error,''),1,80) AS job_error
   FROM knowledge_import_batches b
   LEFT JOIN knowledge_jobs j ON j.job_key = 'process_batch:' || b.batch_id
   ORDER BY b.created_at DESC;" || true
echo "-- per-file queue (PCM-15; empty on first run) --"
sqlite3 -header "$APP/backend/thesaurus.db" \
  "SELECT collection_id, file_key, file_name, status, stage, attempts,
          substr(COALESCE(last_error,''),1,80) AS last_error
   FROM knowledge_file_queue ORDER BY updated_at DESC LIMIT 30;" 2>/dev/null || true
sleep 5
PAGES_AFTER=$(sqlite3 "$APP/backend/thesaurus.db" "SELECT COUNT(*) FROM project_pages;")
echo "crawl project_pages: before=$PAGES_BEFORE after=$PAGES_AFTER"
[ "$PAGES_AFTER" -ge "$PAGES_BEFORE" ] || fail "crawl page count decreased!"

echo "=== 13. optional resume (PCT_RESUME_BATCH) ==="
if [ -n "${PCT_RESUME_BATCH:-}" ]; then
  echo "POST /api/knowledge/import/batches/${PCT_RESUME_BATCH}/process"
  curl -s -c /tmp/pct208-resume -X POST http://127.0.0.1:5055/api/auth/login \
    -H 'Content-Type: application/json' -d "{\"password\":\"$PW11\"}" > /dev/null
  curl -s -b /tmp/pct208-resume -X POST \
    "http://127.0.0.1:5055/api/knowledge/import/batches/${PCT_RESUME_BATCH}/process"; echo
  rm -f /tmp/pct208-resume
  echo "resume submitted (idempotent). Track via Studio or:"
  echo "  sqlite3 backend/thesaurus.db \"SELECT job_id,status,stage,progress,total,substr(COALESCE(error,''),1,80) FROM knowledge_jobs ORDER BY created_at DESC LIMIT 5;\""
else
  echo "PCT_RESUME_BATCH not set — no resume submitted."
  echo "If a Mizan batch is stuck, copy its batch_id from step 12 and run:"
  echo "  PCT_RESUME_BATCH=<batch_id> bash deploy/pcm208_deploy.sh"
  echo "(steps 1-13 are idempotent-safe; or resume from the Studio UI.)"
fi

echo "=== DEPLOY OK (TS=$TS) ==="
echo "backups: $BK/thesaurus-${TS}.db + $BK/pct-deploy-${TS}.tar.gz"
echo "post-deploy: run deploy/pcm208_mizan_audit.py from a machine that can reach"
echo "the server (PCT_PASSWORD=... python deploy/pcm208_mizan_audit.py) for the full Mizan state."

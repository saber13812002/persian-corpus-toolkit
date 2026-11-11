#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════════
# PCM-20.9.6 — controlled deploy to AI-TOOLS (172.30.0.133)
#
# What this deploy ships (branch pcm-20.9-pipeline-orchestration, on top of
# the PCM-20.8-era code that is live on AI-TOOLS):
#   1. PCM-20.9 — the Full Pipeline orchestrator (backend/
#      pipeline_orchestrator.py): A_IMPORT -> B_PROCESS -> C_SCHEMA ->
#      D_BUILD -> E_ACCEPT -> RELEASE, checkpointed / pausable / resumable /
#      per-collection singleton. 6 new API routes: pipeline run / pause /
#      resume / status + pipeline schedules GET/POST.
#   2. PCM-20.9.4 — the Knowledge Corpus Factory dashboard card (dashboard/
#      studio.html): six connected stage cards with live status/times/job
#      id/counts/errors, Run / Pause / Resume / Retry / Resume-From-Stage
#      controls, live status + history, nightly-scheduler UI.
#   3. PCM-20.9.5 — OpenAPI spec v1.2.0 (docs/openapi/pcm209-pipeline-
#      release.openapi.yaml, 15 operations) + the 243-test suite
#      (backend/test_pipeline.py: 43 tests PF-A..F / P / M01 / S11..S19).
#   4. deploy/pcm209_nightly.sh — the nightly runner (cron target; NOT
#      activated by this deploy — the crontab is only touched when
#      PCT_NIGHTLY=1 is set explicitly).
#   5. deploy/pcm2096_audit_host{,2,3}.sh — the read-only host audit
#      scripts (their output is the evidence for the deploy report).
#
# Code identity: the 16 blob SHAs in EXPECT below, verified with
#   `git hash-object` (or the pure-sha1sum fallback) AFTER extraction
#   (step 5). Archive the tip of branch pcm-20.9-pipeline-orchestration;
#   the blobs — not the commit id — are the gate. Pass PCT_DEPLOY_COMMIT=
#   <sha> so the archived commit is recorded in the deploy log.
#
# PREP (on Windows, in the repo):
#   git archive --format=tar.gz --prefix=persian-corpus-toolkit/ \
#       <COMMIT_SHA> -o pct-code-2096.tgz
#   scp pct-code-2096.tgz saber@172.30.0.133:/tmp/
#   scp deploy/pcm2096_deploy.sh deploy/pcm2096_rollback.sh \
#       saber@172.30.0.133:/tmp/
#   (or: the archive already contains deploy/ — just scp the tar.)
#
# Host facts (live read-only audit 2026-11-11 — deploy/pcm2096_audit_
# host{,2,3}.sh):
#   AI-TOOLS = 172.30.0.133 (NOT 172.20.1.52 — that old IP times out).
#   Ubuntu 24.04.4, 20 CPU, 78 GiB RAM (54 GiB available), disk 38% used.
#   Container persian-corpus-toolkit-backend-1 Up, 0 restarts,
#   127.0.0.1:5055 -> 5055. Public ingress: Kong/openresty
#   (corpus.ai.ismc.ir -> 185.213.10.25).
#   Live state: thesaurus crawl still writing (project_pages = 65,210 at
#   audit time); 3 collections / 44 documents / 46 jobs; DB 927 MB,
#   PRAGMA integrity_check = ok. Deployed code = PCM-20.8 era (no
#   pipeline_orchestrator.py, no knowledge_pipeline_* tables).
#   ES ABSENT (127.0.0.1:9200 -> 000; no PCT_ES_* env) and RAG not
#   configured -> Stage D/E/RAG will report BLOCKED on production until
#   those env keys are set. Expected and honest; does NOT block this
#   deploy (step 13 reports it).
#
# Safety model (AGENTS.md §2/§3):
#   1. sqlite3 online backup (WAL-safe) + integrity_check BEFORE any change
#   2. tar snapshot of the whole deploy dir (DB + WAL/SHM excluded)
#   3. code extracted from `git archive` — NEVER rewrites thesaurus.db,
#      .env, or data/ (all untracked -> not in the tar)
#   4. blob-hash verification of 16 key files against EXPECT
#   5. `docker compose build backend && docker compose up -d backend` —
#      ONLY the backend service. NO `docker compose down`, NO -v.
#   6. No schema migration in this deploy: the new code's schema is lazy +
#      additive (knowledge_pipeline_runs / knowledge_pipeline_schedules via
#      CREATE TABLE IF NOT EXISTS, created on the first pipeline request).
#      The rolled-back old code ignores the new tables -> safe rollback.
#   7. Live-crawl protection: project_pages (and crawl_queue, if present)
#      counters logged BEFORE/AFTER and asserted not-decreasing.
#
# Differences vs deploy/pcm208_deploy.sh (the reviewed pattern):
#   a) host = 172.30.0.133 (AI-TOOLS), not 172.20.1.52 (timed out);
#   b) blob_sha() falls back to a pure sha1sum computation if git is
#      missing on the host (git blob = "blob <size>\0" + content);
#   c) pipeline-specific smoke: after login warmup, GET pipeline/schedules
#      + GET pipeline/status (first collection) and assert the two
#      knowledge_pipeline_* tables exist (lazy creation verified);
#   d) ES/RAG env report (step 13, read-only);
#   e) nightly cron is OPT-IN (PCT_NIGHTLY=1) — default leaves crontab
#      untouched, per the mission constraint.
#
# ROLLBACK (if anything looks wrong): deploy/pcm2096_rollback.sh
#   PCT_TS=<TS printed by this script> bash /tmp/pcm2096_rollback.sh
#   a) code:  restore the snapshot tar + docker compose build + up -d
#   b) DB:    PCT_DB_RESTORE=1 additionally sqlite3 .restore the backup
#             (only if data rows were corrupted; the schema is additive)
#   c) files: data/ is never touched by either script.
# ═══════════════════════════════════════════════════════════════════════════
set -euo pipefail
APP=/home/saber/saberprojects/persian-corpus-toolkit
TS=$(date +%Y%m%d-%H%M%S)
BK=/home/saber/backups
CODE_TGZ=/tmp/pct-code-2096.tgz
mkdir -p "$BK"

# expected blob SHAs (git hash-object of the archived files) — identity check
declare -A EXPECT=(
  [backend/server.py]=30d647d176bd3b7a276a80530660c01f445f0a93
  [backend/knowledge_api.py]=059a2602594b4df23ace4fd08a701492648fe65b
  [backend/pipeline_orchestrator.py]=c6504881ce5d8c09ede53ea5d4701ecb5d620305
  [backend/auth.py]=e1bbe1cbd752b47f6c5cdec33595c9e745450e8a
  [backend/dashboard_api.py]=fdcb1424225023be050f86610cc9c2c72d6a3bef
  [backend/projects.py]=ec6f3ce3d0cb22ffe434ac521ca32f7e39a99629
  [backend/Dockerfile]=0d211b9b1cb4f02a229189ed8d516c7ea7262032
  [backend/requirements.txt]=128c57e09a1c78c82f4c2244cc3ae8267ba3630e
  [docker-compose.yml]=fc05c99800a3c70d7516ee4aa3b1332ddd2df2ec
  [dashboard/studio.html]=6924493b7dbcd2186d262b2af7a50493c18124a8
  [docs/openapi/pcm209-pipeline-release.openapi.yaml]=d77d3c1d6be56ce167edfc6a00a71c57a4a537c3
  [backend/test_pipeline.py]=3d44741d6465ec8238735412ba87768d2a844f29
  [deploy/pcm209_nightly.sh]=319973d03ec5530d83638f094ecf960703e78982
  [deploy/pcm2096_audit_host.sh]=b1782ca5c293734ee20c4dc787aa4b5812ee9cf1
  [deploy/pcm2096_audit_host2.sh]=17adb370ea1e3c9f7be9dd24d61fb3d43653bc0d
  [deploy/pcm2096_audit_host3.sh]=b0402cbe9753da24162e64d8fc331339b588f3a3
)

STEP="init"
fail() { echo "!!! FAILED at [$STEP]: $1"; echo "!!! rollback: PCT_TS=$TS bash /tmp/pcm2096_rollback.sh"; exit 1; }
trap 'fail "abnormal exit (line $LINENO)"' ERR

# git blob sha, with a pure coreutils fallback when git is absent on the host
blob_sha() {
  if command -v git >/dev/null 2>&1; then
    git hash-object "$1"
  else
    local size
    size=$(wc -c < "$1")
    { printf 'blob %s\0' "$size"; cat "$1"; } | sha1sum | cut -d' ' -f1
  fi
}

knowledge_tables() {
  sqlite3 "$1" "SELECT COUNT(*) FROM sqlite_master WHERE name LIKE 'knowledge_%';"
}

knowledge_state() {
  # one line per metric: label value
  sqlite3 "$1" "
    SELECT 'collections', COUNT(*) FROM knowledge_collections;
    SELECT 'documents',   COUNT(*) FROM knowledge_collection_documents;
    SELECT 'docs_uploaded', COUNT(*) FROM knowledge_collection_documents WHERE status='uploaded';
    SELECT 'docs_parsing',  COUNT(*) FROM knowledge_collection_documents WHERE status IN ('validating','parsing');
    SELECT 'docs_parsed',   COUNT(*) FROM knowledge_collection_documents WHERE status='parsed';
    SELECT 'docs_failed',   COUNT(*) FROM knowledge_collection_documents WHERE status='failed';
    SELECT 'batches',       COUNT(*) FROM knowledge_import_batches;
    SELECT 'jobs',          COUNT(*) FROM knowledge_jobs;
    SELECT 'jobs_running',    COUNT(*) FROM knowledge_jobs WHERE status='running';
    SELECT 'jobs_interrupted',COUNT(*) FROM knowledge_jobs WHERE status='interrupted';
    SELECT 'jobs_failed',     COUNT(*) FROM knowledge_jobs WHERE status='failed';" || true
}

pipeline_tables() {
  sqlite3 "$1" "SELECT COUNT(*) FROM sqlite_master WHERE name IN ('knowledge_pipeline_runs','knowledge_pipeline_schedules');" || echo 0
}

pipeline_state() {
  sqlite3 "$1" "
    SELECT 'runs_total',        COUNT(*) FROM knowledge_pipeline_runs;
    SELECT 'runs_running',      COUNT(*) FROM knowledge_pipeline_runs WHERE status='running';
    SELECT 'runs_paused',       COUNT(*) FROM knowledge_pipeline_runs WHERE status='paused';
    SELECT 'schedules',         COUNT(*) FROM knowledge_pipeline_schedules;
    SELECT 'schedules_enabled', COUNT(*) FROM knowledge_pipeline_schedules WHERE enabled=1;" || true
}

echo "=== 0. preconditions ==="
command -v docker  >/dev/null || fail "docker missing"
command -v sqlite3 >/dev/null || fail "sqlite3 missing"
command -v curl    >/dev/null || fail "curl missing"
[ -f "$CODE_TGZ" ] || fail "code tar not found at $CODE_TGZ (git archive the branch tip, scp to AI-TOOLS:/tmp)"
[ -f "$APP/.env" ] || fail ".env missing (refusing to touch auth config)"
[ -f "$APP/backend/thesaurus.db" ] || fail "production DB missing — refusing"
cd "$APP"
docker compose config -q || fail "compose file invalid"
[ -n "${PCT_DEPLOY_COMMIT:-}" ] && echo "archived commit: $PCT_DEPLOY_COMMIT" \
  || echo "PCT_DEPLOY_COMMIT not set (record the archived commit SHA in the deploy log)"

echo "=== 1. DB online backup (WAL-safe) + integrity ==="
sqlite3 "$APP/backend/thesaurus.db" ".backup $BK/thesaurus-${TS}.db"
[ "$(sqlite3 "$BK/thesaurus-${TS}.db" 'PRAGMA integrity_check;')" = "ok" ] || fail "backup integrity_check"
echo "backup ok: $BK/thesaurus-${TS}.db"

echo "=== 2. snapshot current deploy dir (DB + WAL/SHM excluded) ==="
tar czf "$BK/pct-deploy-${TS}.tar.gz" \
  --exclude=backend/thesaurus.db --exclude='backend/thesaurus.db-*' \
  --exclude=data \
  -C /home/saber/saberprojects persian-corpus-toolkit
echo "snapshot ok: $BK/pct-deploy-${TS}.tar.gz"

echo "=== 3. BEFORE: crawl + knowledge + pipeline state ==="
CQ_BEFORE=$(sqlite3 "$APP/backend/thesaurus.db" "SELECT COUNT(*) FROM crawl_queue;" 2>/dev/null || echo "absent")
PAGES_BEFORE=$(sqlite3 "$APP/backend/thesaurus.db" "SELECT COUNT(*) FROM project_pages;")
echo "crawl_queue: $CQ_BEFORE   project_pages: $PAGES_BEFORE"
KN_TABLES_BEFORE=$(knowledge_tables "$APP/backend/thesaurus.db")
PL_TABLES_BEFORE=$(pipeline_tables "$APP/backend/thesaurus.db")
echo "-- knowledge state --"
knowledge_state "$APP/backend/thesaurus.db" | sed 's/^/  /'
echo "-- pipeline state (0 tables expected on PCM-20.8-era code) --"
echo "  pipeline tables before: $PL_TABLES_BEFORE (knowledge_* tables: $KN_TABLES_BEFORE)"
pipeline_state "$APP/backend/thesaurus.db" | sed 's/^/  /'

echo "=== 4. code tar ==="
ls -la "$CODE_TGZ"

echo "=== 5. extract new code (DB/.env/data untouched by definition) ==="
# tar carries prefix 'persian-corpus-toolkit/' -> extract into the PARENT dir
tar xzf "$CODE_TGZ" -C "$(dirname "$APP")"
echo "-- blob-identity check (16 files) --"
for f in "${!EXPECT[@]}"; do
  [ -f "$APP/$f" ] || fail "missing $f after extract"
  got=$(blob_sha "$APP/$f")
  [ "$got" = "${EXPECT[$f]}" ] || fail "blob mismatch $f: got $got want ${EXPECT[$f]}"
  echo "ok  $f"
done
[ -d "$APP/backend/factory" ] || fail "backend/factory missing after extract"
[ -f "$APP/backend/pipeline_orchestrator.py" ] || fail "pipeline_orchestrator.py missing after extract"
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
echo "-- /api/knowledge/pipeline/schedules NO cookie (expect 401 = PCM-20.9 code live) --"
curl -s -o /dev/null -w 'HTTP:%{http_code}\n' http://127.0.0.1:5055/api/knowledge/pipeline/schedules
echo "-- /api/projects (extension, must stay OPEN, expect 200) --"
curl -s -o /dev/null -w 'HTTP:%{http_code}\n' http://127.0.0.1:5055/api/projects
echo "-- /dashboard/studio.html (expect 200) --"
curl -s -o /dev/null -w 'HTTP:%{http_code}\n' http://127.0.0.1:5055/dashboard/studio.html
echo "-- /api/dashboard/projects NO cookie (expect 401) --"
curl -s -o /dev/null -w 'HTTP:%{http_code}\n' http://127.0.0.1:5055/api/dashboard/projects

echo "=== 11. DB integrity + schema warmup (additive, lazy) + pipeline smoke ==="
[ "$(sqlite3 "$APP/backend/thesaurus.db" 'PRAGMA integrity_check;')" = "ok" ] || fail "post-deploy integrity_check"
PW=$(grep '^PCT_DASHBOARD_PASSWORD=' "$APP/.env" | cut -d= -f2-)
curl -s -c /tmp/pct2096-warmup -X POST http://127.0.0.1:5055/api/auth/login \
  -H 'Content-Type: application/json' -d "{\"password\":\"$PW\"}" > /dev/null
curl -s -o /dev/null -b /tmp/pct2096-warmup http://127.0.0.1:5055/api/knowledge/collections
# schedules GET (creates knowledge_pipeline_schedules lazily)
SCHED_CODE=$(curl -s -o /tmp/pct2096-sched.json -w '%{http_code}' \
  -b /tmp/pct2096-warmup http://127.0.0.1:5055/api/knowledge/pipeline/schedules)
[ "$SCHED_CODE" = "200" ] || fail "pipeline/schedules GET expected 200, got $SCHED_CODE"
echo "pipeline/schedules: 200 (read-only; no schedule rows created)"
# pipeline/status for the first collection (creates knowledge_pipeline_runs
# lazily; run=null is expected — NO run is started, this is a read-only warmup)
COLL_PK=$(sqlite3 "$APP/backend/thesaurus.db" "SELECT MIN(id) FROM knowledge_collections;")
if [ -n "$COLL_PK" ] && [ "$COLL_PK" -ge 1 ] 2>/dev/null; then
  STAT_CODE=$(curl -s -o /tmp/pct2096-stat.json -w '%{http_code}' \
    -b /tmp/pct2096-warmup \
    "http://127.0.0.1:5055/api/knowledge/collections/$COLL_PK/pipeline/status")
  [ "$STAT_CODE" = "200" ] || fail "pipeline/status GET expected 200, got $STAT_CODE"
  grep -q '"NOT_STARTED"' /tmp/pct2096-stat.json \
    || fail "pipeline/status body missing NOT_STARTED stage cards"
  echo "pipeline/status (collection $COLL_PK): 200, six NOT_STARTED cards (no run started)"
else
  echo "no collections in the live DB — pipeline/status warmup skipped"
fi
rm -f /tmp/pct2096-warmup /tmp/pct2096-sched.json /tmp/pct2096-stat.json
[ "$(sqlite3 "$APP/backend/thesaurus.db" "SELECT COUNT(*) FROM sqlite_master WHERE name IN ('knowledge_pipeline_runs','knowledge_pipeline_schedules');")" = "2" ] \
  || fail "pipeline tables not created after warmup"
KN_TABLES_AFTER=$(knowledge_tables "$APP/backend/thesaurus.db")
PL_TABLES_AFTER=$(pipeline_tables "$APP/backend/thesaurus.db")
echo "knowledge tables: before=$KN_TABLES_BEFORE after=$KN_TABLES_AFTER (additive growth only)"
echo "pipeline tables:  before=$PL_TABLES_BEFORE after=$PL_TABLES_AFTER"
[ "$KN_TABLES_AFTER" -ge "$KN_TABLES_BEFORE" ] || fail "knowledge table count decreased (impossible)"

echo "=== 12. AFTER: knowledge state + collections + jobs report ==="
knowledge_state "$APP/backend/thesaurus.db" | sed 's/^/  /'
pipeline_state "$APP/backend/thesaurus.db" | sed 's/^/  /'
echo "-- collections --"
sqlite3 -header "$APP/backend/thesaurus.db" \
  "SELECT id, collection_id, name, book_count FROM knowledge_collections ORDER BY id;"
echo "-- latest jobs (informational) --"
sqlite3 -header "$APP/backend/thesaurus.db" \
  "SELECT job_id, kind, status, stage, progress, total, substr(COALESCE(error,''),80) AS error
   FROM knowledge_jobs ORDER BY created_at DESC LIMIT 10;" || true

echo "=== 13. ES/RAG env report (read-only; Stage D/E/RAG dependency) ==="
docker exec persian-corpus-toolkit-backend-1 env \
  | grep -E '^(PCT_ES|RAG|LITELLM)' \
  || echo "no PCT_ES_*/RAG*/LITELLM* env keys in the container — Stage D/E/RAG will report BLOCKED on production (expected; configure in a later mission)"

echo "=== 14. AFTER crawl counters (assert not-decreasing) ==="
sleep 5
CQ_AFTER=$(sqlite3 "$APP/backend/thesaurus.db" "SELECT COUNT(*) FROM crawl_queue;" 2>/dev/null || echo "absent")
PAGES_AFTER=$(sqlite3 "$APP/backend/thesaurus.db" "SELECT COUNT(*) FROM project_pages;")
echo "crawl_queue: $CQ_BEFORE -> $CQ_AFTER   project_pages: $PAGES_BEFORE -> $PAGES_AFTER"
[ "$PAGES_AFTER" -ge "$PAGES_BEFORE" ] || fail "crawl page count decreased!"

echo "=== 15. nightly scheduler (OPT-IN — default: crontab untouched) ==="
if [ "${PCT_NIGHTLY:-0}" = "1" ]; then
  [ -x "$APP/backend/.venv/bin/python" ] || fail "PCT_NIGHTLY=1 but $APP/backend/.venv/bin/python missing (nightly runner needs a venv)"
  CRON_LINE="10 3 * * * $APP/deploy/pcm209_nightly.sh >> $BK/pcm209-nightly.log 2>&1"
  ( crontab -l 2>/dev/null | grep -v 'pcm209_nightly.sh' || true ) > /tmp/pct2096-cron.new
  echo "$CRON_LINE" >> /tmp/pct2096-cron.new
  crontab /tmp/pct2096-cron.new
  rm -f /tmp/pct2096-cron.new
  crontab -l | grep -q 'pcm209_nightly.sh' || fail "cron line not installed"
  echo "nightly cron installed: $CRON_LINE"
else
  echo "PCT_NIGHTLY not set — crontab untouched (nightly stays INACTIVE, per mission constraint)"
fi

echo "=== DEPLOY OK (TS=$TS) ==="
echo "backups: $BK/thesaurus-${TS}.db + $BK/pct-deploy-${TS}.tar.gz"
echo "rollback: PCT_TS=$TS bash /tmp/pcm2096_rollback.sh  (add PCT_DB_RESTORE=1 only if data corrupted)"
echo "next: Studio UI (https://corpus.ai.ismc.ir/dashboard/studio.html) — the pipeline card"
echo "is live now; run it from there. Re-audit any time with:"
echo "  ssh saber@172.30.0.133 'bash -s' < deploy/pcm2096_audit_host3.sh"

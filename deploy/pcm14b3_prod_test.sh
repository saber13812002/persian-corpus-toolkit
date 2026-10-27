#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════════
# PCM-14B.3 — Phase 4a: production API + security tests (on s52, live server)
#
# Runs against http://127.0.0.1:5055 (the deployed container). Password is
# read server-side from .env (chmod 600) and NEVER echoed.
#
# Scope:
#   - auth: 401s, wrong password, login, logout, post-logout 401
#   - knowledge API: collections CRUD, jobs, compatibility, subjects, metadata
#   - extension API stays OPEN (crawl-facing, unauthenticated)
#   - static: studio.html, dashboard
#   - DB: no crash, counts sane
#   - cleanup: test collection removed (no test records left in prod)
# ═══════════════════════════════════════════════════════════════════════════
set -u
APP=/home/saber/saberprojects/persian-corpus-toolkit
BASE=http://127.0.0.1:5055
TS=$(date +%H%M%S)
SLUG="pcm14b3-test-${TS}"
CJ=/tmp/pct14b3-cookies.txt
CJ2=/tmp/pct14b3-cookies2.txt
rm -f "$CJ" "$CJ2"
PASS=0; FAIL=0

# read password server-side, never echo
PW=$(grep '^PCT_DASHBOARD_PASSWORD=' "$APP/.env" | cut -d= -f2-)
[ -n "$PW" ] || { echo "FATAL: no password in .env"; exit 1; }

t() { # t <name> <expected> <method> <path> [json]
  local name=$1 exp=$2 meth=$3 path=$4 json=${5:-}
  local out code body
  if [ "$meth" = "POST" ] && [ -n "$json" ]; then
    body=$(curl -s -o /dev/null -w '%{http_code}' -b "$CJ" -X POST "$BASE$path" -H 'Content-Type: application/json' -d "$json")
  elif [ "$meth" = "PATCH" ] && [ -n "$json" ]; then
    body=$(curl -s -o /dev/null -w '%{http_code}' -b "$CJ" -X PATCH "$BASE$path" -H 'Content-Type: application/json' -d "$json")
  elif [ "$meth" = "POST" ]; then
    body=$(curl -s -o /dev/null -w '%{http_code}' -b "$CJ" -X POST "$BASE$path" -H 'Content-Type: application/json' -d '{}')
  else
    body=$(curl -s -o /dev/null -w '%{http_code}' -b "$CJ" -X GET "$BASE$path")
  fi
  if [ "$body" = "$exp" ]; then
    PASS=$((PASS+1)); echo "PASS  $name -> $body"
  else
    FAIL=$((FAIL+1)); echo "FAIL  $name -> got $body want $exp"
  fi
}
# unauthenticated variant (fresh empty jar = no session)
t401() { # t401 <name> <method> <path>
  local name=$1 meth=$2 path=$3
  local body
  body=$(curl -s -o /dev/null -w '%{http_code}' -b "$CJ2" -X "$meth" "$BASE$path")
  if [ "$body" = "401" ]; then
    PASS=$((PASS+1)); echo "PASS  [no-auth] $name -> 401"
  else
    FAIL=$((FAIL+1)); echo "FAIL  [no-auth] $name -> got $body want 401"
  fi
}
# open (unauthenticated, no cookie at all)
topen() { # topen <name> <expected> <path>
  local name=$1 exp=$2 path=$3
  local body
  body=$(curl -s -o /dev/null -w '%{http_code}' -X GET "$BASE$path")
  if [ "$body" = "$exp" ]; then
    PASS=$((PASS+1)); echo "PASS  [open] $name -> $body"
  else
    FAIL=$((FAIL+1)); echo "FAIL  [open] $name -> got $body want $exp"
  fi
}

echo "=== A. security: no-session 401s ==="
t401 collections GET  /api/knowledge/collections
t401 jobs GET         /api/knowledge/jobs
t401 compat GET       /api/knowledge/compatibility
t401 subjects GET     /api/knowledge/subjects
t401 meta GET         /api/knowledge/metadata/fields
t401 dash-proj GET    /api/dashboard/projects
t401 doc-process POST /api/knowledge/documents/d-x/process

echo "=== B. auth flow ==="
code=$(curl -s -o /dev/null -w '%{http_code}' -X POST "$BASE/api/auth/login" -H 'Content-Type: application/json' -d '{"password":"WRONG-PASSWORD-14b3"}')
if [ "$code" = "401" ]; then PASS=$((PASS+1)); echo "PASS  wrong password -> 401"; else FAIL=$((FAIL+1)); echo "FAIL  wrong password -> $code"; fi

code=$(curl -s -c "$CJ" -o /dev/null -w '%{http_code}' -X POST "$BASE/api/auth/login" -H 'Content-Type: application/json' -d "{\"password\":\"$PW\"}")
if [ "$code" = "200" ]; then PASS=$((PASS+1)); echo "PASS  login -> 200 (cookie jar set)"; else FAIL=$((FAIL+1)); echo "FAIL  login -> $code"; fi

echo "=== B2. logout flow (second session jar) ==="
curl -s -c "$CJ2" -o /dev/null -X POST "$BASE/api/auth/login" -H 'Content-Type: application/json' -d "{\"password\":\"$PW\"}"
code=$(curl -s -o /dev/null -w '%{http_code}' -b "$CJ2" "$BASE/api/knowledge/collections")
[ "$code" = "200" ] && { PASS=$((PASS+1)); echo "PASS  second session authenticated -> 200"; } || { FAIL=$((FAIL+1)); echo "FAIL  second session -> $code"; }
code=$(curl -s -b "$CJ2" -c "$CJ2" -o /dev/null -w '%{http_code}' -X POST "$BASE/api/auth/logout")
[ "$code" = "200" ] && { PASS=$((PASS+1)); echo "PASS  logout -> 200"; } || { FAIL=$((FAIL+1)); echo "FAIL  logout -> $code"; }
code=$(curl -s -o /dev/null -w '%{http_code}' -b "$CJ2" "$BASE/api/knowledge/collections")
[ "$code" = "401" ] && { PASS=$((PASS+1)); echo "PASS  post-logout -> 401"; } || { FAIL=$((FAIL+1)); echo "FAIL  post-logout -> $code"; }

echo "=== C. knowledge API (authenticated) ==="
t collections-list  200 GET  "/api/knowledge/collections"
t subjects          200 GET  "/api/knowledge/subjects"
t compatibility     200 GET  "/api/knowledge/compatibility"
t jobs              200 GET  "/api/knowledge/jobs"
t meta-fields       200 GET  "/api/knowledge/metadata/fields"

t coll-create       201 POST "/api/knowledge/collections" "{\"name\":\"PCM14B3 Test $TS\",\"slug\":\"$SLUG\",\"subject\":\"test\",\"language\":\"fa\"}"
t coll-dup          409 POST "/api/knowledge/collections" "{\"name\":\"dup\",\"slug\":\"$SLUG\"}"
t coll-badslug      400 POST "/api/knowledge/collections" "{\"name\":\"x\",\"slug\":\"UPPER_case\"}"
t coll-empty        400 POST "/api/knowledge/collections" "{\"name\":\"\",\"slug\":\"abc\"}"

# collection_id = stable string id (meta/batch APIs); id = int rowid (detail/patch/builds URL routes)
CID=$(sqlite3 "$APP/backend/thesaurus.db" "SELECT collection_id FROM knowledge_collections WHERE slug='$SLUG';")
RID=$(sqlite3 "$APP/backend/thesaurus.db" "SELECT id FROM knowledge_collections WHERE slug='$SLUG';")
echo "test collection: collection_id=$CID rowid=$RID"
t coll-detail       200 GET  "/api/knowledge/collections/$RID"
t coll-patch        200 PATCH "/api/knowledge/collections/$RID" '{"description":"updated by pcm14b3 test"}'
t coll-builds       200 GET  "/api/knowledge/collections/$RID/builds"
t coll-404          404 GET  "/api/knowledge/collections/999999"
t doc-404           404 GET  "/api/knowledge/documents/d-nonexistent"

echo "=== D. metadata field (collection-scoped, then cleanup) ==="
t meta-create       201 POST "/api/knowledge/metadata/fields" "{\"scope\":\"collection\",\"collection_id\":\"$CID\",\"field_key\":\"pcm14b3_flag\",\"display_name\":\"PCM14B3 Flag\",\"data_type\":\"string\"}"
t meta-list         200 GET  "/api/knowledge/metadata/fields?collection_id=$CID"

echo "=== E. extension API stays OPEN (crawl-facing) ==="
topen api/projects  200 /api/projects
topen api/sites     200 /api/sites
topen api/stats     200 /api/stats
topen proj2         200 /api/projects/2

echo "=== F. static / dashboard ==="
topen studio        200 /dashboard/studio.html
topen dashboard     200 /dashboard/
t dash-with-cookie  200 GET "/api/dashboard/projects?per_page=3"

echo "=== G. crawl unaffected (live cursor still advancing) ==="
C1=$(sqlite3 "$APP/backend/thesaurus.db" "SELECT cursor_url FROM projects WHERE id=2;")
sleep 16
C2=$(sqlite3 "$APP/backend/thesaurus.db" "SELECT cursor_url FROM projects WHERE id=2;")
if [ -n "$C2" ] && [ "$C2" != "$C1" ]; then
  PASS=$((PASS+1)); echo "PASS  crawl cursor advanced (extension still writing)"
else
  echo "WARN  crawl cursor unchanged in 16s (may be normal if paused/idle) — $C2"
fi

echo "=== H. cleanup: remove test collection + its rows (no test records left) ==="
sqlite3 "$APP/backend/thesaurus.db" "
DELETE FROM knowledge_metadata_values WHERE collection_id='$CID';
DELETE FROM knowledge_metadata_fields WHERE collection_id='$CID';
DELETE FROM knowledge_collection_documents WHERE collection_id='$CID';
DELETE FROM knowledge_import_batches WHERE collection_id='$CID';
DELETE FROM knowledge_jobs WHERE collection_id='$CID';
DELETE FROM knowledge_collections WHERE collection_id='$CID';
SELECT 'leftover', COUNT(*) FROM knowledge_collections WHERE slug='$SLUG';
PRAGMA integrity_check;"
rm -f "$CJ" "$CJ2"

echo "======================================"
echo "RESULT: PASS=$PASS FAIL=$FAIL"
[ "$FAIL" = "0" ] && echo "ALL-TESTS-PASS" || echo "TESTS-FAILED"

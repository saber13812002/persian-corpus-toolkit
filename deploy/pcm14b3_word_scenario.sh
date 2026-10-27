#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════════
# PCM-14B.3 — Phase 4b: end-to-end Word Factory scenario on s52 (live server)
#
# Scenario (real files, real worker, real persistent store):
#   1. create collection
#   2. generate 2 DOCX (python-docx fixtures) + record SHA-256
#   3. upload both (201, sha match, stored under data/knowledge/files)
#   4. duplicate upload -> 409 ; empty file -> 400 ; wrong ext -> 400
#   5. process doc1 -> job -> succeeded ; doc1 parsed (blocks/chars > 0)
#   6. structure / quality / blocks endpoints
#   7. approve doc1
#   8. idempotent reprocess (200, resubmitted=true, no 2nd worker)
#   9. INTERRUPTED-RETRY: process doc2, stop container mid-run, start it,
#      job -> interrupted (recovered), reprocess -> retry_count+1 -> succeeded
#  10. RESTART-PERSISTENCE: stop/start again; doc rows, files, approved
#      status all survive; GET /file 200
#  11. crawl still advancing
#  12. cleanup: registry rows + test files removed from data/
#
# The live crawl (extension-driven) may lose <=1 request during the two
# short stop windows (~8s each); cursor is persisted per page so it resumes.
# ═══════════════════════════════════════════════════════════════════════════
set -u
APP=/home/saber/saberprojects/persian-corpus-toolkit
BASE=http://127.0.0.1:5055
PY="$APP/backend/.venv/bin/python"
DB="$APP/backend/thesaurus.db"
TS=$(date +%H%M%S)
SLUG="pcm14b3-word-${TS}"
CJ=/tmp/pct14b3w-cookies.txt
WORK=/tmp/pct14b3w
rm -rf "$WORK" "$CJ"; mkdir -p "$WORK"
PASS=0; FAIL=0

PW=$(grep '^PCT_DASHBOARD_PASSWORD=' "$APP/.env" | cut -d= -f2-)
[ -n "$PW" ] || { echo "FATAL: no password in .env"; exit 1; }

ok()   { PASS=$((PASS+1)); echo "PASS  $1"; }
bad()  { FAIL=$((FAIL+1)); echo "FAIL  $1"; }
chknum() { # chknum <name> <value> — pass if integer > 0
  case "$2" in ''|*[!0-9]*) bad "$1 (non-numeric: '$2')";;
    0) bad "$1 (zero)";;
    *) ok "$1 ($2)";; esac
}
pj()   { "$PY" -c "import sys,json; d=json.load(sys.stdin); print($1)"; }
sha256() { sha256sum "$1" | cut -d' ' -f1; }

wait_job() { # wait_job <job_key> <max_seconds> -> prints final status
  local key=$1 max=$2 i st
  for i in $(seq 1 "$max"); do
    st=$(curl -s -b "$CJ" "$BASE/api/knowledge/jobs" \
      | "$PY" -c "import sys,json; d=json.load(sys.stdin)
js=[j for j in d['jobs'] if j['job_key']=='$key']
print(js[-1]['status'] if js else 'none')")
    case "$st" in succeeded|failed|interrupted) echo "$st"; return;; esac
    sleep 2
  done
  echo "timeout($st)"
}

echo "=== 1. login + create collection ==="
code=$(curl -s -c "$CJ" -o /dev/null -w '%{http_code}' -X POST "$BASE/api/auth/login" -H 'Content-Type: application/json' -d "{\"password\":\"$PW\"}")
[ "$code" = "200" ] && ok "login" || { bad "login ($code)"; exit 1; }
code=$(curl -s -o /dev/null -w '%{http_code}' -b "$CJ" -X POST "$BASE/api/knowledge/collections" -H 'Content-Type: application/json' -d "{\"name\":\"PCM14B3 Word $TS\",\"slug\":\"$SLUG\",\"subject\":\"test\"}")
[ "$code" = "201" ] && ok "collection created (201)" || bad "collection create ($code)"
# collection_id = stable string id (batch/meta JSON body); rowid = int (URL routes)
CID=$(sqlite3 "$DB" "SELECT collection_id FROM knowledge_collections WHERE slug='$SLUG';")
RID=$(sqlite3 "$DB" "SELECT id FROM knowledge_collections WHERE slug='$SLUG';")
echo "collection_id=$CID rowid=$RID"

echo "=== 2. generate 2 DOCX + SHAs ==="
( cd "$APP/backend" && "$PY" - "$WORK" <<'PYEOF'
import sys, os
from factory._smoke_fixtures import make_sample_book, make_docx
w = sys.argv[1]
make_sample_book(os.path.join(w, "book1.docx"))
make_docx(os.path.join(w, "book2.docx"), [
    ("Normal", "عنوان: کتاب دوم آزمایشی"),
    ("Heading 1", "فصل الف"),
    ("Normal", "متن آزمایشی با اعداد ۱۴۰۵ و 2026 و کلمه English."),
    ("Heading 1", "فصل ب"),
    ("Normal", "پاراگراف پایانی."),
])
print("fixtures-ok")
PYEOF
)
SHA1=$(sha256 "$WORK/book1.docx"); SHA2=$(sha256 "$WORK/book2.docx")
SIZE1=$(stat -c %s "$WORK/book1.docx"); SIZE2=$(stat -c %s "$WORK/book2.docx")
echo "book1.docx  sha=$SHA1  size=$SIZE1"
echo "book2.docx  sha=$SHA2  size=$SIZE2"

echo "=== 3. uploads (201, sha round-trip, persistent store) ==="
code=$(curl -s -o "$WORK/up1.json" -w '%{http_code}' -b "$CJ" -X POST "$BASE/api/knowledge/collections/$RID/documents" -F "file=@$WORK/book1.docx")
D1=$(cat "$WORK/up1.json" | pj "d['document']['document_id']")
SHA_UP=$(cat "$WORK/up1.json" | pj "d['document']['sha256']")
[ "$code" = "201" ] && ok "upload book1 -> 201" || bad "upload book1 ($code)"
[ "$SHA_UP" = "$SHA1" ] && ok "book1 sha round-trip" || bad "book1 sha mismatch ($SHA_UP)"

code=$(curl -s -o "$WORK/up2.json" -w '%{http_code}' -b "$CJ" -X POST "$BASE/api/knowledge/collections/$RID/documents" -F "file=@$WORK/book2.docx")
D2=$(cat "$WORK/up2.json" | pj "d['document']['document_id']")
[ "$code" = "201" ] && ok "upload book2 -> 201" || bad "upload book2 ($code)"
echo "doc1=$D1  doc2=$D2"

STORED=$(ls "$APP/data/knowledge/files/${SHA1:0:12}/" 2>/dev/null | head -1)
[ -n "$STORED" ] && ok "book1 on disk: data/knowledge/files/${SHA1:0:12}/$STORED" || bad "book1 not found in data/ store"

echo "=== 4. invalid uploads ==="
code=$(curl -s -o /dev/null -w '%{http_code}' -b "$CJ" -X POST "$BASE/api/knowledge/collections/$RID/documents" -F "file=@$WORK/book1.docx")
[ "$code" = "409" ] && ok "duplicate sha -> 409" || bad "duplicate ($code)"
: > "$WORK/empty.docx"
code=$(curl -s -o /dev/null -w '%{http_code}' -b "$CJ" -X POST "$BASE/api/knowledge/collections/$RID/documents" -F "file=@$WORK/empty.docx")
[ "$code" = "400" ] && ok "empty file -> 400" || bad "empty ($code)"
code=$(curl -s -o /dev/null -w '%{http_code}' -b "$CJ" -X POST "$BASE/api/knowledge/collections/$RID/documents" -F "file=@$WORK/up1.json;filename=notes.txt")
[ "$code" = "400" ] && ok "wrong extension -> 400" || bad "wrong-ext ($code)"

echo "=== 5. process doc1 (real worker) ==="
code=$(curl -s -o "$WORK/p1.json" -w '%{http_code}' -b "$CJ" -X POST "$BASE/api/knowledge/documents/$D1/process")
[ "$code" = "202" ] && ok "process doc1 -> 202 (job created)" || bad "process doc1 ($code)"
J1=$(wait_job "process_document:$D1" 60)
[ "$J1" = "succeeded" ] && ok "doc1 job succeeded" || bad "doc1 job -> $J1"
ST=$(curl -s -b "$CJ" "$BASE/api/knowledge/documents/$D1" | pj "d['document']['status']")
BC=$(curl -s -b "$CJ" "$BASE/api/knowledge/documents/$D1" | pj "d['document']['blocks_count']")
CC=$(curl -s -b "$CJ" "$BASE/api/knowledge/documents/$D1" | pj "d['document']['chars_count']")
[ "$ST" = "parsed" ] && ok "doc1 status=parsed" || bad "doc1 status=$ST"
chknum "doc1 blocks_count>0" "$BC"
chknum "doc1 chars_count>0" "$CC"

echo "=== 6. structure / quality / blocks ==="
for ep in structure quality blocks; do
  code=$(curl -s -o /dev/null -w '%{http_code}' -b "$CJ" "$BASE/api/knowledge/documents/$D1/$ep")
  [ "$code" = "200" ] && ok "GET /$ep -> 200" || bad "GET /$ep ($code)"
done

echo "=== 7. approve doc1 ==="
code=$(curl -s -o /dev/null -w '%{http_code}' -b "$CJ" -X POST "$BASE/api/knowledge/documents/$D1/approve")
[ "$code" = "200" ] && ok "approve doc1 -> 200" || bad "approve ($code)"
ST=$(curl -s -b "$CJ" "$BASE/api/knowledge/documents/$D1" | pj "d['document']['status']")
[ "$ST" = "approved" ] && ok "doc1 status=approved" || bad "doc1 status after approve=$ST"

echo "=== 8. idempotent reprocess (no 2nd worker) ==="
code=$(curl -s -o "$WORK/p1b.json" -w '%{http_code}' -b "$CJ" -X POST "$BASE/api/knowledge/documents/$D1/process")
RS=$(cat "$WORK/p1b.json" | pj "d['resubmitted']" 2>/dev/null || echo "?")
[ "$code" = "200" ] && ok "reprocess -> 200 (existing job)" || bad "reprocess ($code)"
[ "$RS" = "True" ] && ok "resubmitted=True (same job reused)" || bad "resubmitted=$RS"
sleep 3
NW=$(sqlite3 "$DB" "SELECT COUNT(*) FROM knowledge_jobs WHERE job_key='process_document:$D1';")
[ "$NW" = "1" ] && ok "still exactly 1 job row (no duplicate worker)" || bad "job rows=$NW"

echo "=== 9. INTERRUPTED-RETRY (doc3 = big book, real crash mid-run) ==="
# book3 is large (150k paragraphs) so parsing runs for many seconds. We
# `docker kill` (SIGKILL, hard crash) while its job is in-flight
# (status=running) -> a real interruption, not a graceful finish. After
# restart we backdate the stuck rows past STUCK_AFTER_MOD(-10min) so
# _recover_interrupted deterministically flips them (the live equivalent of
# an outage longer than the 10-min stuck window, which the test cannot wait).
( cd "$APP/backend" && "$PY" - "$WORK" <<'PYEOF'
import sys, os
from factory._smoke_fixtures import make_docx
paras = []
for i in range(150000):
    paras.append((
        "Heading 1" if i % 500 == 0 else "Normal",
        f"پاراگراف شماره {i} از کتاب بزرگ آزمایشی PCM14B3 — متن فارسی برای پارس‌کردن.",
    ))
make_docx(os.path.join(sys.argv[1], "book3.docx"), paras)
print("big-fixture-ok")
PYEOF
)
SHA3=$(sha256 "$WORK/book3.docx"); SIZE3=$(stat -c %s "$WORK/book3.docx")
echo "book3.docx  sha=$SHA3  size=$SIZE3"
code=$(curl -s -o "$WORK/up3.json" -w '%{http_code}' -b "$CJ" -X POST "$BASE/api/knowledge/collections/$RID/documents" -F "file=@$WORK/book3.docx")
[ "$code" = "201" ] && ok "upload book3 (big) -> 201" || bad "upload book3 ($code)"
D3=$(cat "$WORK/up3.json" | pj "d['document']['document_id']")
code=$(curl -s -o /dev/null -w '%{http_code}' -b "$CJ" -X POST "$BASE/api/knowledge/documents/$D3/process")
[ "$code" = "202" ] && ok "process doc3 -> 202" || bad "process doc3 ($code)"
# wait until the worker has picked it up (running) — deterministic crash point.
# Poll via the API, NOT host-side sqlite3: the DB is a single-file bind mount,
# so the -wal sidecar lives in the container overlay and uncheckpointed writes
# (the running job row) are invisible to host sqlite3 queries.
RUN=0
for i in $(seq 1 100); do
  JS=$(curl -s -b "$CJ" "$BASE/api/knowledge/jobs" \
    | "$PY" -c "import sys,json; d=json.load(sys.stdin)
js=[j for j in d['jobs'] if j['job_key']=='process_document:$D3']
print(js[-1]['status'] if js else 'none')")
  case "$JS" in running) RUN=1; break;; succeeded|failed|interrupted) break;; esac
  sleep 0.3
done
[ "$RUN" = "1" ] && ok "doc3 job in-flight (running) at crash moment" || bad "doc3 job never reached running (status=$JS)"
echo "-- crash: docker kill (SIGKILL) while doc3 is running --"
docker kill persian-corpus-toolkit-backend-1 >/dev/null
sleep 2
docker compose -f "$APP/docker-compose.yml" start backend
for i in $(seq 1 30); do curl -sf "$BASE/api/stats" >/dev/null 2>&1 && break; sleep 1; done
sqlite3 "$DB" "
UPDATE knowledge_jobs SET updated_at=datetime('now','-11 minutes')
 WHERE job_key='process_document:$D3';
UPDATE knowledge_collection_documents SET updated_at=datetime('now','-11 minutes')
 WHERE document_id='$D3';"
J2=$(wait_job "process_document:$D3" 30)
[ "$J2" = "interrupted" ] && ok "doc3 job recovered as interrupted" || bad "doc3 job after restart=$J2 (expected interrupted)"
DST=$(sqlite3 "$DB" "SELECT status FROM knowledge_collection_documents WHERE document_id='$D3';")
[ "$DST" = "uploaded" ] && ok "doc3 reset to uploaded (reprocessable, file intact)" || bad "doc3 doc status=$DST (expected uploaded)"
RC1=$(sqlite3 "$DB" "SELECT retry_count FROM knowledge_jobs WHERE job_key='process_document:$D3';")
code=$(curl -s -o "$WORK/p3b.json" -w '%{http_code}' -b "$CJ" -X POST "$BASE/api/knowledge/documents/$D3/process")
RS2=$(cat "$WORK/p3b.json" | pj "d['resubmitted']" 2>/dev/null || echo "?")
# spec B10: re-executing an interrupted job = fresh execution (202, resubmitted=False,
# same job row, retry_count bumped)
[ "$code" = "202" ] && ok "reprocess doc3 -> 202 (re-executes interrupted)" || bad "reprocess doc3 ($code)"
[ "$RS2" = "False" ] && ok "resubmitted=False (fresh execution, same row)" || bad "resubmitted=$RS2"
J2=$(wait_job "process_document:$D3" 120)
[ "$J2" = "succeeded" ] && ok "doc3 retry succeeded" || bad "doc3 retry -> $J2"
RC2=$(sqlite3 "$DB" "SELECT retry_count FROM knowledge_jobs WHERE job_key='process_document:$D3';")
[ "$RC2" = "$((RC1+1))" ] && ok "retry_count bumped ($RC1 -> $RC2)" || bad "retry_count $RC1 -> $RC2"
ST=$(curl -s -b "$CJ" "$BASE/api/knowledge/documents/$D3" | pj "d['document']['status']")
[ "$ST" = "parsed" ] && ok "doc3 status=parsed after retry" || bad "doc3 status=$ST"
ND=$(sqlite3 "$DB" "SELECT COUNT(*) FROM knowledge_collection_documents WHERE document_id='$D3';")
[ "$ND" = "1" ] && ok "no duplicate doc row after retry" || bad "doc3 rows=$ND"

echo "=== 10. RESTART-PERSISTENCE (stop/start again) ==="
docker compose -f "$APP/docker-compose.yml" stop backend
sleep 2
docker compose -f "$APP/docker-compose.yml" start backend
for i in $(seq 1 30); do curl -sf "$BASE/api/stats" >/dev/null 2>&1 && break; sleep 1; done
sleep 2
ST1=$(curl -s -b "$CJ" "$BASE/api/knowledge/documents/$D1" | pj "d['document']['status']")
[ "$ST1" = "approved" ] && ok "doc1 still approved after restart" || bad "doc1 status after 2nd restart=$ST1"
ST2=$(curl -s -b "$CJ" "$BASE/api/knowledge/documents/$D2" | pj "d['document']['status']")
[ "$ST2" = "uploaded" ] && ok "doc2 still uploaded (untouched) after restart" || bad "doc2 status after 2nd restart=$ST2"
code=$(curl -s -o /dev/null -w '%{http_code}' -b "$CJ" "$BASE/api/knowledge/documents/$D1/file")
[ "$code" = "200" ] && ok "GET /file -> 200 after restart (persistent data/)" || bad "GET /file ($code)"
[ -f "$APP/data/knowledge/files/${SHA1:0:12}/$(ls "$APP/data/knowledge/files/${SHA1:0:12}/" 2>/dev/null | head -1)" ] && ok "original file still on disk" || bad "original file missing after restart"

echo "=== 11. crawl still advancing ==="
sleep 16
sqlite3 "$DB" "SELECT 'proj2_after_restart', COUNT(*) FROM project_pages WHERE project_id=2;
               SELECT 'proj2_status', status FROM projects WHERE id=2;"

echo "=== 12. cleanup (no test records/files in prod) ==="
sqlite3 "$DB" "
DELETE FROM knowledge_metadata_values WHERE collection_id='$CID';
DELETE FROM knowledge_metadata_fields WHERE collection_id='$CID';
DELETE FROM knowledge_collection_documents WHERE collection_id='$CID';
DELETE FROM knowledge_import_batches WHERE collection_id='$CID';
DELETE FROM knowledge_jobs WHERE collection_id='$CID';
DELETE FROM knowledge_collections WHERE collection_id='$CID';
SELECT 'leftover_coll', COUNT(*) FROM knowledge_collections WHERE slug='$SLUG';"
# store files are root-owned (container runs as root) -> remove via docker exec
docker exec persian-corpus-toolkit-backend-1 sh -c \
  "rm -rf /data-files/knowledge/files/${SHA1:0:12} /data-files/knowledge/files/${SHA2:0:12} /data-files/knowledge/files/${SHA3:0:12}"
for s in "${SHA1:0:12}" "${SHA2:0:12}" "${SHA3:0:12}"; do
  [ -d "$APP/data/knowledge/files/$s" ] && bad "store dir left: $s" || ok "store dir removed: $s"
done
sqlite3 "$DB" "PRAGMA integrity_check;"
rm -rf "$WORK" "$CJ"

echo "======================================"
echo "RESULT: PASS=$PASS FAIL=$FAIL"
[ "$FAIL" = "0" ] && echo "WORD-SCENARIO-PASS" || echo "WORD-SCENARIO-FAILED"

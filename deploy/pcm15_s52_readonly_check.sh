#!/usr/bin/env bash
# =============================================================================
# PCM-15 — s52 read-only check (NO deploy, NO writes, NO restart)
#
# هدف:
#   1) production دست‌نخورده است: backend healthy + auth مثل قبل
#   2) کد s52 هنوز قبل از PCM-15 است:
#        - marker 'knowledge_file_queue' باید در knowledge_api.py نباشد
#        - marker 'on_stage' باید در factory/service.py نباشد
#        - جدول knowledge_file_queue باید در DB نباشد (additive DDL فقط
#          بعد از deploy + اولین request ساخته می‌شود)
#   3) DB production سالم است (integrity_check فقط-خوانده)
#   4) وضعیت s52 = pre-PCM-14D (مطابق گزارش PCM-14D): endpointهای
#      registry (مثلا /api/knowledge/works) باید 404 بدهند، نه 401؛
#      marker 'knowledge_works' باید در کد s52 نباشد.
#
# اجرا از لپ‌تاپ:
#   ssh -p 22 saber@172.20.1.52 'bash -s' < deploy/pcm15_s52_readonly_check.sh
# =============================================================================
set -u
APP=/home/saber/saberprojects/persian-corpus-toolkit
DB="$APP/backend/thesaurus.db"

echo "== 1. container status (read-only) =="
docker ps --filter name=persian-corpus-toolkit --format 'table {{.Names}}\t{{.Status}}' 2>/dev/null || true
docker image inspect persian-corpus-toolkit-backend --format 'image: {{.Id}}' 2>/dev/null || true

echo
echo "== 2. service probes (127.0.0.1:5055, unauthenticated) =="
curl -s -o /dev/null -w 'GET /api/stats                   -> %{http_code}\n' --max-time 5 http://127.0.0.1:5055/api/stats
curl -s -o /dev/null -w 'GET /api/projects (extension)    -> %{http_code}\n' --max-time 5 http://127.0.0.1:5055/api/projects
curl -s -o /dev/null -w 'GET /api/knowledge/collections   -> %{http_code} (expect 401)\n' --max-time 5 http://127.0.0.1:5055/api/knowledge/collections
curl -s -o /dev/null -w 'GET /api/knowledge/works (pre-14D, expect 404)\n' --max-time 5 http://127.0.0.1:5055/api/knowledge/works
curl -s -o /dev/null -w 'GET /api/knowledge/queue/summary (pre-15, expect 404) -> %{http_code}\n' --max-time 5 http://127.0.0.1:5055/api/knowledge/queue/summary
curl -s -o /dev/null -w 'GET /api/knowledge/import/batches/b-nope/pause (pre-15, expect 404) -> %{http_code}\n' --max-time 5 -X POST http://127.0.0.1:5055/api/knowledge/import/batches/b-nope/pause
curl -s -o /dev/null -w 'GET /api/dashboard/projects      -> %{http_code} (expect 401)\n' --max-time 5 http://127.0.0.1:5055/api/dashboard/projects
curl -s -o /dev/null -w 'GET /dashboard/studio.html       -> %{http_code} (expect 200)\n' --max-time 5 http://127.0.0.1:5055/dashboard/studio.html
echo -n 'GET /api/auth/status -> '; curl -s --max-time 5 http://127.0.0.1:5055/api/auth/status; echo

echo
echo "== 3. code state on s52 (deploy of PCM-15 must NOT be present yet) =="
echo "-- queue marker in knowledge_api.py (should be ABSENT pre-15) --"
if grep -q "knowledge_file_queue" "$APP/backend/knowledge_api.py" 2>/dev/null; then
  echo "WARN: knowledge_file_queue marker EXISTS on s52 — code may already include PCM-15?"
else
  echo "OK: knowledge_file_queue marker absent (s52 is pre-PCM-15, as expected)"
fi
echo "-- on_stage marker in factory/service.py (should be ABSENT pre-15) --"
if grep -q "on_stage" "$APP/backend/factory/service.py" 2>/dev/null; then
  echo "WARN: on_stage marker EXISTS on s52 — code may already include PCM-15?"
else
  echo "OK: on_stage marker absent (s52 is pre-PCM-15, as expected)"
fi
echo "-- PCM-14D marker in knowledge_api.py (s52 is pre-14D: should be ABSENT) --"
if grep -q "knowledge_works" "$APP/backend/knowledge_api.py" 2>/dev/null; then
  echo "NOTE: knowledge_works marker EXISTS — s52 code includes PCM-14D (newer than baseline of this check)"
else
  echo "OK: knowledge_works marker absent (s52 is pre-PCM-14D, matches report PCM-14D)"
fi
echo "-- key file sizes (for diff vs GitHub) --"
for f in backend/knowledge_api.py backend/factory/service.py backend/test_queue.py; do
  if [ -f "$APP/$f" ]; then
    printf '%s %s\n' "$(wc -l < "$APP/$f" | tr -d ' ')" "$f"
  else
    echo "MISSING $f"
  fi
done
echo "-- .env present & perms (never printing content) --"
stat -c '%a %n' "$APP/.env" 2>/dev/null || echo "(no .env)"

echo
echo "== 4. DB integrity (read-only) =="
if command -v sqlite3 >/dev/null 2>&1 && [ -f "$DB" ]; then
  echo -n 'PRAGMA integrity_check: '; sqlite3 "$DB" "PRAGMA integrity_check;"
  echo -n 'projects: ';                       sqlite3 "$DB" "SELECT COUNT(*) FROM projects;" 2>/dev/null
  echo -n 'auth_sessions: ';                  sqlite3 "$DB" "SELECT COUNT(*) FROM auth_sessions;" 2>/dev/null
  echo -n 'knowledge_collections: ';          sqlite3 "$DB" "SELECT COUNT(*) FROM knowledge_collections;" 2>/dev/null
  echo -n 'knowledge_collection_documents: '; sqlite3 "$DB" "SELECT COUNT(*) FROM knowledge_collection_documents;" 2>/dev/null
  echo -n 'knowledge_works (pre-14D expect absent): '; sqlite3 "$DB" "SELECT COUNT(*) FROM knowledge_works;" 2>/dev/null || echo "(table absent — expected pre-14D)"
  echo -n 'knowledge_file_queue (pre-15 should be missing): '; sqlite3 "$DB" "SELECT COUNT(*) FROM knowledge_file_queue;" 2>/dev/null || echo "(table absent — expected pre-15)"
  echo -n 'db mtime: ';                       stat -c '%y' "$DB" 2>/dev/null
else
  echo "(sqlite3 or DB not found — skipped)"
fi

echo
echo "DONE — read-only; nothing was written, restarted, or deployed."

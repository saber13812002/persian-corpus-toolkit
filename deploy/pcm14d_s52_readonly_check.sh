#!/usr/bin/env bash
# =============================================================================
# PCM-14D — s52 read-only check (NO deploy, NO writes, NO restart)
#
# هدف:
#   1) production دست‌نخورده است: backend healthy + auth مثل قبل
#   2) کد s52 هنوز قبل از PCM-14D است (registry باید روی s52 نباشد — deploy نشده)
#   3) DB production سالم است (integrity_check فقط-خوانده)
#   4) endpointهای قدیمی knowledge مثل قبل رفتار می‌کنند (401 بدون cookie)
#
# اجرا از لپ‌تاپ:
#   ssh -p 22 saber@172.20.1.52 'bash -s' < deploy/pcm14d_s52_readonly_check.sh
# =============================================================================
set -u
APP=/home/saber/saberprojects/persian-corpus-toolkit
DB="$APP/backend/thesaurus.db"

echo "== 1. container status (read-only) =="
docker ps --filter name=persian-corpus-toolkit --format 'table {{.Names}}\t{{.Status}}' 2>/dev/null || true
docker image inspect persian-corpus-toolkit-backend --format 'image: {{.Id}}' 2>/dev/null || true

echo
echo "== 2. service probes (127.0.0.1:5055, unauthenticated) =="
curl -s -o /dev/null -w 'GET /api/stats                       -> %{http_code}\n' --max-time 5 http://127.0.0.1:5055/api/stats
curl -s -o /dev/null -w 'GET /api/projects (extension, open)  -> %{http_code}\n' --max-time 5 http://127.0.0.1:5055/api/projects
curl -s -o /dev/null -w 'GET /api/knowledge/collections      -> %{http_code} (expect 401)\n' --max-time 5 http://127.0.0.1:5055/api/knowledge/collections
curl -s -o /dev/null -w 'GET /api/knowledge/works (pre-14D)  -> %{http_code} (expect 404, unauth would be 401/404)\n' --max-time 5 http://127.0.0.1:5055/api/knowledge/works
curl -s -o /dev/null -w 'GET /api/dashboard/projects         -> %{http_code} (expect 401)\n' --max-time 5 http://127.0.0.1:5055/api/dashboard/projects
curl -s -o /dev/null -w 'GET /dashboard/studio.html          -> %{http_code} (expect 200)\n' --max-time 5 http://127.0.0.1:5055/dashboard/studio.html
echo -n 'GET /api/auth/status -> '; curl -s --max-time 5 http://127.0.0.1:5055/api/auth/status; echo

echo
echo "== 3. code state on s52 (deploy of PCM-14D must NOT be present yet) =="
echo "-- registry marker (should be ABSENT on s52 before PCM-14D deploy) --"
if grep -q "knowledge_works" "$APP/backend/knowledge_api.py" 2>/dev/null; then
  echo "WARN: knowledge_works marker EXISTS on s52 — code may already include PCM-14D?"
else
  echo "OK: knowledge_works marker absent (s52 is pre-PCM-14D, as expected)"
fi
echo "-- key file sizes (for diff vs GitHub) --"
for f in backend/knowledge_api.py backend/factory/dump.py; do
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
  echo -n 'project_pages: ';    sqlite3 "$DB" "SELECT COUNT(*) FROM project_pages;" 2>/dev/null
  echo -n 'projects: ';         sqlite3 "$DB" "SELECT COUNT(*) FROM projects;" 2>/dev/null
  echo -n 'auth_sessions: ';    sqlite3 "$DB" "SELECT COUNT(*) FROM auth_sessions;" 2>/dev/null
  echo -n 'knowledge_collections: '; sqlite3 "$DB" "SELECT COUNT(*) FROM knowledge_collections;" 2>/dev/null || true
  echo -n 'knowledge_collection_documents: '; sqlite3 "$DB" "SELECT COUNT(*) FROM knowledge_collection_documents;" 2>/dev/null || true
  echo -n 'knowledge_works (pre-14D should be missing): '; sqlite3 "$DB" "SELECT COUNT(*) FROM knowledge_works;" 2>/dev/null || echo "(table absent — expected pre-14D)"
  echo -n 'db mtime: ';         stat -c '%y' "$DB" 2>/dev/null
else
  echo "(sqlite3 or DB not found — skipped)"
fi

echo
echo "DONE — read-only; nothing was written, restarted, or deployed."

#!/usr/bin/env bash
# =============================================================================
# PCM-14C.3 — s52 read-only check (NO deploy, NO writes, NO restart)
#
# هدف:
#   1) production دست‌نخورده است: backend healthy + auth مثل قبل
#   2) کد s52 هنوز قبل از e367bc7 است (dump.py نباید روی s52 باشد — deploy نشده)
#   3) DB production سالم است (integrity_check فقط-خوانده)
#   4) GitLab (port 2222) زنده است یا خیر (best-effort)
#
# اجرا از لپ‌تاپ:
#   ssh -p 22 saber@172.20.1.52 'bash -s' < deploy/pcm14c3_s52_readonly_check.sh
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
curl -s -o /dev/null -w 'GET /api/dashboard/projects         -> %{http_code} (expect 401)\n' --max-time 5 http://127.0.0.1:5055/api/dashboard/projects
curl -s -o /dev/null -w 'GET /dashboard/studio.html          -> %{http_code} (expect 200)\n' --max-time 5 http://127.0.0.1:5055/dashboard/studio.html
echo -n 'GET /api/auth/status -> '; curl -s --max-time 5 http://127.0.0.1:5055/api/auth/status; echo

echo
echo "== 3. code state on s52 (deploy of e367bc7 must NOT be present yet) =="
echo "-- factory dir --"
ls -1 "$APP/backend/factory/" 2>/dev/null || echo "(factory dir not found!)"
if [ -f "$APP/backend/factory/dump.py" ]; then
  echo "WARN: dump.py EXISTS on s52 — code already includes PCM-14C.3?"
else
  echo "OK: dump.py absent (s52 is pre-PCM-14C.3, as expected)"
fi
echo "-- key file sizes (for diff vs GitHub e367bc7) --"
for f in backend/factory/cli.py backend/factory/export.py backend/factory/models.py backend/factory/normalize.py backend/factory/service.py backend/factory/__init__.py; do
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
  echo -n 'db mtime: ';         stat -c '%y' "$DB" 2>/dev/null
else
  echo "(sqlite3 or DB not found — skipped)"
fi

echo
echo "== 5. GitLab (port 2222) — best effort =="
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 6 http://127.0.0.1:2222/ 2>/dev/null || echo 000)
echo "GET http://127.0.0.1:2222/ -> $code"

echo
echo "== DONE (nothing was modified on s52) =="

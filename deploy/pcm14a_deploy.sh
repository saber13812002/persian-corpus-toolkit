#!/usr/bin/env bash
# ============================================================================
# PCM-14A deploy: Knowledge Studio collections layer (additive only)
#
# WHAT CHANGES:
#   - NEW:  backend/knowledge_api.py      (3 tables + 6 authed endpoints)
#   - NEW:  dashboard/studio.html         (studio skeleton, collections only)
#   - CHG:  backend/server.py             (import + init_knowledge_db + blueprints)
#   - CHG:  dashboard/index.html          (+1 nav entry "استودیوی دانش")
#   - NEW:  backend/test_knowledge_api.py (19 tests, KS-01..KS-05)
#
# NO production DROP/RENAME. init_knowledge_db() is IF-NOT-EXISTS only.
# Extension write APIs (/api/projects*) untouched and stay OPEN.
#
# PREREQ: git push done; s52 has a fresh copy of the repo.
#   cd /home/saber && git clone/update repo, or copy the 6 changed files.
#
# USAGE (on s52):
#   cd /home/saber/saberprojects/persian-corpus-toolkit
#   bash deploy/pcm14a_deploy.sh
#
# ROLLBACK: restore the previous code snapshot (pct-deploy-<TS>.tar.gz) and
#   docker compose build backend && docker compose up -d backend.
#   (New tables are additive; leaving them empty is harmless.)
# ============================================================================
set -euo pipefail
TS=$(date +%Y%m%d-%H%M%S)
DIR="$(cd "$(dirname "$0")/.." && pwd)"
DB="$DIR/backend/thesaurus.db"
BK=/home/saber/backups
mkdir -p "$BK"

echo "=== [1/7] online backup + integrity (BEFORE) ==="
[ -f "$DB" ] || { echo "FATAL: DB not found at $DB"; exit 1; }
BKDB="$BK/thesaurus-$TS.db"
sqlite3 "$DB" ".backup '$BKDB'"
sqlite3 "$DB" "PRAGMA integrity_check;"
du -h "$BKDB" | sed 's/^/backup: /'
BEFORE_COUNT=$(sqlite3 "$DB" "SELECT COUNT(*) FROM projects;")
echo "projects before: $BEFORE_COUNT"

echo "=== [2/7] snapshot deploy dir (code only, no DB) ==="
TARBALL="$BK/pct-deploy-$TS.tar.gz"
tar czf "$TARBALL" -C "$(dirname "$DIR")" "$(basename "$DIR")" \
  --exclude='backend/thesaurus.db' --exclude='backend/thesaurus.db-wal' \
  --exclude='backend/thesaurus.db-shm' --exclude='wf-out' --exclude='.git'
du -h "$TARBALL" | sed 's/^/snapshot: /'

echo "=== [3/7] ensure .env (dashboard password) ==="
if [ ! -f "$DIR/backend/.env" ]; then
  PW=$(openssl rand -base64 18 | tr -d '/+=' | cut -c1-20)
  printf 'PCT_DASHBOARD_PASSWORD=%s\n' "$PW" > "$DIR/backend/.env"
  chmod 600 "$DIR/backend/.env"
  echo "NEW .env created (chmod 600). DASHBOARD PASSWORD: $PW"
  echo "  >>> store it securely now; it will NOT be shown again <<<"
else
  chmod 600 "$DIR/backend/.env"
  echo ".env present (chmod 600), password unchanged"
fi

echo "=== [4/7] ensure fresh code on s52 ==="
cd "$DIR"
if git rev-parse --git-dir >/dev/null 2>&1; then
  git pull --ff-only origin main
else
  echo "not a git repo on s52 — assuming code was copied manually"
fi

echo "=== [5/7] build + up backend (ONLY 'up backend', no -v) ==="
cd "$DIR/backend"
docker compose build backend
docker compose up -d backend

echo "=== [6/7] health-wait + smoke ==="
ok=""
for i in $(seq 1 30); do
  code=$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:5055/api/stats || true)
  if [ "$code" = "200" ]; then ok=1; break; fi
  sleep 2
done
[ -n "$ok" ] || { echo "FATAL: backend did not come up"; docker compose logs --tail=60 backend; exit 1; }
echo "GET /api/stats -> 200 (extension API still OPEN)"
# new endpoints must exist and be authed (401 unauthenticated, not 404)
for p in /api/knowledge/collections /api/knowledge/subjects; do
  c=$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:5055$p")
  [ "$c" = "401" ] || { echo "FATAL: $p expected 401 got $c"; exit 1; }
  echo "GET $p -> 401 (authed, endpoint registered)"
done
c=$(curl -s -o /dev/null -w '%{http_code}' -X POST http://127.0.0.1:5055/api/knowledge/collections -H 'Content-Type: application/json' -d '{}')
[ "$c" = "401" ] || { echo "FATAL: POST collections expected 401 got $c"; exit 1; }
echo "POST /api/knowledge/collections -> 401 (authed)"

echo "=== [7/7] integrity (AFTER) + counts ==="
sqlite3 "$DB" "PRAGMA integrity_check;"
AFTER_COUNT=$(sqlite3 "$DB" "SELECT COUNT(*) FROM projects;")
echo "projects after: $AFTER_COUNT (before: $BEFORE_COUNT)"
[ "$AFTER_COUNT" = "$BEFORE_COUNT" ] || { echo "FATAL: projects count changed!"; exit 1; }
sqlite3 "$DB" "SELECT COUNT(*) FROM knowledge_collections;" | sed 's/^/knowledge_collections: /'

echo ""
echo "PCM-14A deploy complete."
echo "  backup:   $BKDB"
echo "  snapshot: $TARBALL"
echo "  manual QA: https://<host>/dashboard/  -> login -> 'استودیوی دانش'"

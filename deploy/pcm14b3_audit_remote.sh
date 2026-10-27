#!/bin/bash
# PCM-14B.3 Phase 1 — read-only production audit (s52). No mutations.
set -u
cd /home/saber/saberprojects/persian-corpus-toolkit || exit 1

echo "== 1. deployed code identity =="
ls backend/ | tr '\n' ' '; echo
[ -f backend/knowledge_api.py ] && echo "knowledge_api.py: PRESENT" || echo "knowledge_api.py: ABSENT (pre-14B)"
[ -d backend/factory ] && echo "factory/: PRESENT" || echo "factory/: ABSENT"

echo "== 2. container / image =="
docker ps --format '{{.Names}} | {{.Image}} | {{.Status}}'
docker inspect persian-corpus-toolkit-backend-1 --format 'image={{.Image}} created={{.Created}}' 2>/dev/null
docker images --format '{{.Repository}}:{{.Tag}} {{.Size}} {{.CreatedSince}}' | head -5

echo "== 3. volumes / env =="
docker inspect persian-corpus-toolkit-backend-1 --format '{{range .Mounts}}{{.Type}} {{.Source}} -> {{.Destination}} (ro={{.RO}}){{println}}{{end}}' 2>/dev/null
docker inspect persian-corpus-toolkit-backend-1 --format '{{range .Config.Env}}{{println .}}{{end}}' 2>/dev/null | grep -v PASSWORD

echo "== 4. crawl health (BEFORE snapshot) =="
sqlite3 backend/thesaurus.db "SELECT 'projects', COUNT(*) FROM projects; SELECT 'queue', COUNT(*) FROM crawl_queue; SELECT 'crawled', COUNT(*) FROM crawled_data;"
echo "-- proj2 --"
sqlite3 backend/thesaurus.db "SELECT status, cursor_url, updated_at FROM projects WHERE id=2;"
sqlite3 backend/thesaurus.db "SELECT COUNT(*) FROM project_pages WHERE project_id=2;"
sqlite3 backend/thesaurus.db "SELECT url, captured_at FROM project_pages WHERE project_id=2 ORDER BY rowid DESC LIMIT 2;"
echo "-- integrity_check (online, read-only via backup file) --"
sqlite3 backend/thesaurus.db "PRAGMA integrity_check;" 2>&1 | head -2

echo "== 5. nginx / public URL =="
ss -tln | grep -E ':(80|443) ' || echo "no 80/443 in ss"
for f in /etc/nginx/sites-enabled/* /etc/nginx/conf.d/*; do
  [ -f "$f" ] || continue
  echo "-- $f --"
  grep -nE 'server_name|proxy_pass|location |root ' "$f" 2>/dev/null | head -15
done

echo "== 6. service probe (find wiki.js / others) =="
for p in 3000 8000 8087 8088 8099 7575 7777 7779 7810 8050 4870 6010 6011 4112; do
  t=$(curl -s -m 2 -o /dev/null -w '%{http_code}' "http://127.0.0.1:$p/" 2>/dev/null)
  echo "port $p -> $t"
done

echo "== 7. extension API liveness (crawl-facing, unauthenticated) =="
curl -s -o /dev/null -w 'GET /api/projects -> %{http_code}\n' http://127.0.0.1:5055/api/projects
curl -s http://127.0.0.1:5055/api/projects/2 2>/dev/null | head -c 200; echo
curl -s -o /dev/null -w 'GET /api/dashboard/stats (no auth) -> %{http_code}\n' http://127.0.0.1:5055/api/dashboard/stats

echo "== 8. studio.html on server =="
ls dashboard/
curl -s -o /dev/null -w 'GET /dashboard/studio.html -> %{http_code}\n' http://127.0.0.1:5055/dashboard/studio.html

echo "AUDIT-DONE"

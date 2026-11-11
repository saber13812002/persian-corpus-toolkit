#!/usr/bin/env bash
# PCM-20.9.6 — Phase 3 follow-up: per-table counts + table inventory + vhost hunt. READ-ONLY.
# Usage:  ssh -o BatchMode=yes saber@172.30.0.133 'bash -s' < deploy/pcm2096_audit_host2.sh
set -u
D=/home/saber/saberprojects/persian-corpus-toolkit
DB="$D/backend/thesaurus.db"
echo "==TABLES=="
sqlite3 "$DB" "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'knowledge%' OR name IN ('project_pages','auth_password','auth_login_fails','dashboard_settings') ORDER BY name;"
echo "==COUNTS(per-table)=="
for t in knowledge_collections knowledge_documents knowledge_jobs knowledge_file_queue knowledge_releases knowledge_index_builds knowledge_corpus_builds knowledge_audit_log knowledge_pipeline_runs knowledge_pipeline_schedules project_pages; do
  c=$(sqlite3 "$DB" "SELECT COUNT(*) FROM $t;" 2>&1)
  printf "%-32s %s\n" "$t" "$c"
done
echo "==SCHEMA-VERSIONS=="
sqlite3 "$DB" "SELECT COUNT(*) FROM knowledge_schema_versions;" 2>&1
echo "==LATEST-AUDIT=="
sqlite3 "$DB" "SELECT ts, actor, stage, action, status FROM knowledge_audit_log ORDER BY id DESC LIMIT 5;" 2>&1
echo "==CMS-NGINX-ALL-SERVERNAMES=="
docker exec cms_nginx sh -c "grep -rh server_name /etc/nginx/ 2>/dev/null | sort -u"
echo "==CMS-NGINX-PROXYPASS=="
docker exec cms_nginx sh -c "grep -rh proxy_pass /etc/nginx/ 2>/dev/null | sort -u | head -15"
echo "==HOST-NGINX?=="
pgrep -a nginx | head -3 || true
ls /etc/nginx/sites-enabled/ 2>/dev/null || echo no-host-nginx-sites
echo "==DEPLOY-DIR-SHA(markers)=="
md5sum "$D/backend/server.py" "$D/backend/knowledge_api.py" 2>/dev/null
echo "==COMPOSE-FILE=="
head -40 "$D/docker-compose.yml"
echo "==DONE=="

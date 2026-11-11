#!/usr/bin/env bash
# PCM-20.9.6 — Phase 3 production readiness audit, READ-ONLY probes (s53/AI-TOOLS).
# Usage:  ssh -o BatchMode=yes saber@172.30.0.133 'bash -s' < deploy/pcm2096_audit_host.sh
set -u
D=/home/saber/saberprojects/persian-corpus-toolkit
echo "==CODE-MARKER=="
ls "$D/backend/" | grep -E "pipeline_orchestrator|test_pipeline" || echo "NO-pipeline-files (pre-20.9 code deployed)"
echo "==OS=="
grep PRETTY /etc/os-release || true
uname -r
echo "==DB-integrity=="
sqlite3 "$D/backend/thesaurus.db" "PRAGMA integrity_check;"
echo "==DB-counts=="
sqlite3 "$D/backend/thesaurus.db" '
SELECT "collections", COUNT(*) FROM knowledge_collections
UNION ALL SELECT "documents", COUNT(*) FROM knowledge_documents
UNION ALL SELECT "jobs", COUNT(*) FROM knowledge_jobs
UNION ALL SELECT "queue", COUNT(*) FROM knowledge_file_queue
UNION ALL SELECT "audit", COUNT(*) FROM knowledge_audit_log
UNION ALL SELECT "releases", COUNT(*) FROM knowledge_releases
UNION ALL SELECT "builds", COUNT(*) FROM knowledge_corpus_builds
UNION ALL SELECT "project_pages", COUNT(*) FROM project_pages;
' 2>&1
echo "==DB-files=="
ls -la "$D/backend/"thesaurus.db* 2>&1
echo "==LATEST-AUDIT=="
sqlite3 "$D/backend/thesaurus.db" "SELECT ts, actor, stage, action, status FROM knowledge_audit_log ORDER BY id DESC LIMIT 5;" 2>&1
echo "==ES-ENV(in container, keys only)=="
docker exec persian-corpus-toolkit-backend-1 env | grep -i -E "^(PCT_ES|RAG|LITELLM)" | cut -d= -f1 | tr '\n' ' '
echo
echo "==CMS-NGINX-corpus-vhost=="
docker exec cms_nginx sh -c "grep -r -l corpus.ai.ismc /etc/nginx/ 2>/dev/null" || echo no-conf-match
echo "==CMS-NGINX-proxy=="
docker exec cms_nginx sh -c "grep -r -A2 'corpus.ai.ismc' /etc/nginx/ 2>/dev/null | grep -E 'proxy_pass|server_name'" | head -6
echo "==BACKUPS=="
ls -lt /home/saber/backups/ 2>/dev/null | head -6
echo "==CRON-saber=="
crontab -l 2>&1 | head -5
echo "==CRONTAB-root(pct only)=="
sudo -n crontab -l 2>/dev/null | grep -i -E "pct|persian|tasnim" || echo none
echo "==DONE=="

#!/usr/bin/env bash
# PCM-20.9.6 — Phase 3: deployed-version fingerprint + ingress/vhost + ES + live app. READ-ONLY.
# Usage:  ssh -o BatchMode=yes saber@172.30.0.133 'bash -s' < deploy/pcm2096_audit_host3.sh
set -u
D=/home/saber/saberprojects/persian-corpus-toolkit
echo "==DEPLOYED-MARKERS=="
ls "$D/deploy/" | grep -o -E "pcm[0-9.]+" | sort -u -V | tail -6
ls "$D/dashboard/"
ls "$D/docs/openapi/" 2>/dev/null || echo "no docs/openapi"
echo "==KONG-VHOST-corpus=="
kong list routes 2>/dev/null | grep -i -E "corpus|hosts" | head -10 || echo "kong CLI not available"
echo "==KONG-SERVICES-5055=="
kong list services 2>/dev/null | grep -i -B2 -A2 "5055" | head -12 || true
echo "==ES-LOCAL=="
curl -s -m 3 -o /dev/null -w "127.0.0.1:9200 -> HTTP %{http_code}\n" http://127.0.0.1:9200/ || echo "127.0.0.1:9200 unreachable"
echo "==DOC-COUNT=="
sqlite3 "$D/backend/thesaurus.db" "SELECT COUNT(*) FROM knowledge_collection_documents;"
echo "==CONTAINER-APP-HEALTH=="
curl -s -m 5 -w "\nHTTP %{http_code}\n" http://127.0.0.1:5055/api/auth/status
echo "==LIVE-SITE-FROM-HOST=="
curl -sk -m 10 -o /dev/null -w "https://corpus.ai.ismc.ir/dashboard/studio.html -> HTTP %{http_code}\n" https://corpus.ai.ismc.ir/dashboard/studio.html
echo "==LIVE-KNOWLEDGE-API-UNAUTH=="
curl -sk -m 10 -w "\nHTTP %{http_code}\n" https://corpus.ai.ismc.ir/api/knowledge/collections | head -3
echo "==DATA-KNOWLEDGE-STORE=="
du -sh /home/saber/saberprojects/persian-corpus-toolkit/data/knowledge 2>/dev/null
ls /home/saber/saberprojects/persian-corpus-toolkit/data/knowledge 2>/dev/null
echo "==CONTAINER-START-TIME=="
docker inspect --format '{{.State.StartedAt}} image={{.Config.Image}} restarts={{.RestartCount}}' persian-corpus-toolkit-backend-1
echo "==DONE=="

#!/usr/bin/env bash
# PCM-20.6 SUBTASK 01 — read-only probe 2 on s53 (no secrets printed)
set -u
echo "=== s53 IPs ==="
ip -4 addr show 2>/dev/null | grep -E "inet "
echo
echo "=== embedding-deployment compose (4B owner) ==="
head -45 /home/saber/embedding-deployment/docker-compose.yml 2>/dev/null
echo
echo "=== h200-api compose (public tunnel) ==="
head -40 /home/saber/h200-api/docker-compose.public.yml 2>/dev/null
echo
echo "=== graph-rag config.json (keys masked) ==="
python3 - <<'PYEOF'
import json
d = json.load(open('/home/saber/saberprojects/graph-rag/app/config.json'))
def walk(p, o):
    if isinstance(o, dict):
        for k, v in o.items():
            walk(p + '.' + k, v)
    elif isinstance(o, list):
        print(p, "= list[%d]" % len(o))
    else:
        sv = str(o)
        if any(s in p.lower() for s in ("key", "token", "secret", "password", "uri", "url", "host", "base")):
            print(p, "= <masked>")
        else:
            print(p, "=", sv[:60])
walk('', d)
PYEOF
echo
echo "=== graph-rag NEO4J_DATABASE value (from .env, value only) ==="
grep -E "^NEO4J_DATABASE=" /home/saber/saberprojects/graph-rag/.env 2>/dev/null
grep -E "^QA_CORPUS_NEO4J_DB=|^QA_CORPUS_NEO4J_URI=" /home/saber/saberprojects/rag-portal/.env 2>/dev/null
echo
echo "=== kong admin API (read-only) ==="
docker exec kong-gw-oss-kong curl -s -m 5 http://127.0.0.1:8001/routes 2>&1 | python3 -c "import json,sys
try:
    d=json.load(sys.stdin)
    for r in d.get('data',[]):
        print(r.get('name'), '|', r.get('paths'), '|', r.get('hosts'), '|', r.get('strip_path'))
except Exception as e:
    print('kong parse err:', e)"
echo
echo "=== tyk api list (read-only) ==="
curl -s -m 5 "http://127.0.0.1:8290/api/TykAPI/apiDefs" 2>&1 | head -c 300
echo
echo
echo "=== rag-portal RAG_BASE_URLS + LITELLM_BASE (values, non-secret infra) ==="
grep -E "^(LITELLM_BASE|RAG_BASE_URLS)=" /home/saber/saberprojects/rag-portal/.env 2>/dev/null
echo
echo "=== rag-portal frontend nginx conf ==="
cat /home/saber/saberprojects/rag-portal/frontend/nginx.conf 2>/dev/null | head -40
echo
echo "=== which containers map the QA NEOTOK? list QA service containers ==="
docker ps --format '{{.Names}}\t{{.Image}}\t{{.Ports}}' | grep -E "mesbah|eiis|taghrir|sources|radio|ragportal|qdrant|litellm|neo4j|vllm|h200"
echo
echo "=== qdrant health ==="
curl -s -m 5 http://127.0.0.1:6333/healthz 2>&1 | head -c 200
echo
echo "=== mock-litellm env (keys only) ==="
docker inspect mock-litellm --format '{{range $k,$v := .Config.Env}}{{$k}}{{"\n"}}{{end}}' 2>/dev/null | head -20
echo
echo "=== graph-rag app config: collection/db related files ==="
grep -rn "NEO4J_DATABASE\|database" /home/saber/saberprojects/graph-rag/app/config.py 2>/dev/null | head -10
echo
echo "=== DONE2 ==="

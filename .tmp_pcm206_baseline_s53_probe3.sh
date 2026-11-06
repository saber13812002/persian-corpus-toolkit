#!/usr/bin/env bash
# PCM-20.6 baseline - s53 final read-only probes (no state changes)
echo "=== HOST ==="
hostname
uname -r
nproc
grep -m1 "model name" /proc/cpuinfo
free -h | head -3
df -h / /home 2>/dev/null | tail -n +1
uptime

echo "=== GPU ==="
nvidia-smi --query-gpu=index,name,memory.total,memory.used,memory.free,utilization.gpu --format=csv,noheader 2>/dev/null

echo "=== EMBED DIM 4000 (4B) ==="
curl -sS --max-time 60 http://127.0.0.1:4000/v1/embeddings -H "Content-Type: application/json" -d '{"model":"Qwen3-Embedding-4B","input":"test"}' 2>&1 | head -c 300
echo
echo "=== EMBED DIM 4001 (0.6B) ==="
curl -sS --max-time 60 http://127.0.0.1:4001/v1/embeddings -H "Content-Type: application/json" -d '{"model":"Qwen3-Embedding-0.6B","input":"test"}' 2>&1 | head -c 300
echo
echo "=== EMBED DIM via python lens ==="
python3 - <<'EOF'
import json,urllib.request
for port,model in ((4000,"Qwen3-Embedding-4B"),(4001,"Qwen3-Embedding-0.6B")):
    try:
        req=urllib.request.Request(f"http://127.0.0.1:{port}/v1/embeddings",
            data=json.dumps({"model":model,"input":"test"}).encode(),
            headers={"Content-Type":"application/json"})
        d=json.load(urllib.request.urlopen(req,timeout=60))
        e=d["data"][0]["embedding"]
        print(f"port={port} model={model} server_model={d.get('model')} dim={len(e)}")
    except Exception as ex:
        print(f"port={port} FAIL {ex!r}")
EOF

echo "=== QDRANT collections (6333) ==="
curl -sS --max-time 10 http://127.0.0.1:6333/collections 2>&1 | head -c 2000
echo
echo "=== NEO4J http 7474 no-auth ==="
curl -sS -o /dev/null -w "db_neo4j http_code=%{http_code}\n" --max-time 10 http://127.0.0.1:7474/db/neo4j 2>&1
curl -sS --max-time 10 http://127.0.0.1:7474/ 2>&1 | head -c 200
echo
echo "=== graph-rag HEAD ==="
cd /home/saber/saberprojects/graph-rag 2>/dev/null && git log --oneline -1 && git status --short | head -15

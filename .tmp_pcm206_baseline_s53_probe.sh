#!/usr/bin/env bash
# PCM-20.6 SUBTASK 01 — read-only infra probe for s53 (172.20.1.53)
# STRICTLY read-only: no writes, no service changes, no container stops.
set -u
echo "=== HOST ==="
hostname; date -u +%FT%TZ
uname -a
echo
echo "=== CPU ==="
nproc
lscpu 2>/dev/null | grep -E "^(Model name|CPU\(s\)|Thread|Core|Socket|MHz|CPU max|CPU min)" | head -20
echo
echo "=== RAM ==="
free -h
echo
echo "=== DISK ==="
df -h | grep -vE "tmpfs|udev|overlay" | head -15
echo
echo "=== LOAD / UPTIME ==="
uptime
cat /proc/loadavg
echo
echo "=== GPU ==="
if command -v nvidia-smi >/dev/null 2>&1; then
  nvidia-smi --query-gpu=index,name,memory.total,memory.used,memory.free,utilization.gpu,utilization.memory,temperature.gpu,power.draw --format=csv 2>&1
  echo "--- processes ---"
  nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv 2>&1
else
  echo "nvidia-smi: NOT PRESENT"
  ls /dev/nvidia* 2>/dev/null || echo "no /dev/nvidia* devices"
fi
echo
echo "=== DOCKER ==="
if command -v docker >/dev/null 2>&1; then
  docker version --format 'client={{.Client.Version}} server={{.Server.Version}}' 2>&1
  echo "--- compose ls ---"
  docker compose ls 2>&1 | head -30
  echo "--- docker ps ---"
  docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Ports}}\t{{.Status}}' 2>&1 | head -40
  echo "--- compose files ---"
  find /home/saber -maxdepth 4 -name "docker-compose*.y*ml" -o -maxdepth 4 -name "compose.y*ml" 2>/dev/null | head -20
else
  echo "docker: NOT PRESENT"
fi
echo
echo "=== LISTENING PORTS ==="
ss -tlnp 2>/dev/null | head -40
echo
echo "=== EMBEDDING/LLM SERVICE PROBES (curl, read-only) ==="
probe() {
  local name="$1" url="$2"
  local out code
  out=$(curl -sS -m 5 -o /tmp/.pcm206_probe_body -w "%{http_code}" "$url" 2>&1)
  code=$?
  if [ $code -ne 0 ]; then
    echo "$name [$url] -> CURL_ERR code=$code: $out"
  else
    local head
    head=$(head -c 300 /tmp/.pcm206_probe_body | tr '\n' ' ')
    echo "$name [$url] -> HTTP $out | $head"
  fi
  rm -f /tmp/.pcm206_probe_body 2>/dev/null
}
probe "litellm-4000" "http://127.0.0.1:4000/health"
probe "litellm-4000-v1" "http://127.0.0.1:4000/v1/models"
probe "embed-4001" "http://127.0.0.1:4001/v1/models"
probe "embed-4001-health" "http://127.0.0.1:4001/health"
probe "ollama-11434" "http://127.0.0.1:11434/api/tags"
probe "sglang-8000" "http://127.0.0.1:8000/health"
probe "sglang-8001" "http://127.0.0.1:8001/health"
probe "neo4j-7474" "http://127.0.0.1:7474/"
probe "neo4j-7687-tcp" "http://127.0.0.1:7687/"
probe "port-1234" "http://127.0.0.1:1234/"
probe "port-8000-models" "http://127.0.0.1:8000/v1/models"
probe "port-8001-models" "http://127.0.0.1:8001/v1/models"
echo
echo "=== NGINX VHOSTS (ai.ismc.ir) ==="
if [ -d /www/server/panel/vhost/nginx ]; then
  ls /www/server/panel/vhost/nginx/ 2>/dev/null | head -30
  grep -l "ai.ismc.ir" /www/server/panel/vhost/nginx/*.conf 2>/dev/null
  for f in $(grep -l "ai.ismc.ir" /www/server/panel/vhost/nginx/*.conf 2>/dev/null); do
    echo "--- $f ---"
    grep -E "server_name|proxy_pass|ssl_certificate |listen" "$f" 2>/dev/null | head -20
  done
elif [ -d /etc/nginx/conf.d ]; then
  ls /etc/nginx/conf.d/ 2>/dev/null | head -30
  grep -l "ai.ismc.ir" /etc/nginx/conf.d/*.conf 2>/dev/null
  grep -l "ai.ismc.ir" /etc/nginx/sites-enabled/* 2>/dev/null
  for f in $(grep -l "ai.ismc.ir" /etc/nginx/conf.d/*.conf /etc/nginx/sites-enabled/* 2>/dev/null); do
    echo "--- $f ---"
    grep -E "server_name|proxy_pass|ssl_certificate |listen" "$f" 2>/dev/null | head -20
  done
else
  echo "nginx vhost dirs not found"
  command -v nginx && nginx -T 2>/dev/null | grep -E "server_name|proxy_pass" | grep -i "ismc" | head -30 || echo "nginx not present"
fi
echo
echo "=== PCT DEPLOY DIR (read-only check) ==="
if [ -d /home/saber/saberprojects/persian-corpus-toolkit ]; then
  ls -la /home/saber/saberprojects/persian-corpus-toolkit | head -25
  echo "--- git? ---"
  git -C /home/saber/saberprojects/persian-corpus-toolkit rev-parse --is-inside-work-tree 2>&1
  git -C /home/saber/saberprojects/persian-corpus-toolkit log -1 --format="%H %ad %s" --date=iso 2>&1
  git -C /home/saber/saberprojects/persian-corpus-toolkit status --short 2>&1 | head -20
  ls -la /home/saber/saberprojects/persian-corpus-toolkit/backend/thesaurus.db 2>/dev/null
else
  echo "/home/saber/saberprojects/persian-corpus-toolkit NOT FOUND"
  ls /home/saber 2>/dev/null | head -20
fi
echo
echo "=== RAG DIR CHECK ==="
ls -d /home/saber/rag /home/saber/saberprojects/rag /home/saber/rag-graphrag 2>/dev/null
find /home/saber -maxdepth 3 -name "graph-rag" -type d 2>/dev/null | head -5
find /home/saber -maxdepth 3 -name "_aidump" -type d 2>/dev/null | head -5
echo
echo "=== ENV: model names in compose files (read-only) ==="
grep -riE "Qwen3-Embedding|bge-m3|mxbai|model|LITELLM" /home/saber --include="docker-compose*.y*ml" --include="*.env" -l 2>/dev/null | head -10
echo
echo "=== DONE ==="

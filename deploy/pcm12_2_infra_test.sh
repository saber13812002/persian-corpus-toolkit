#!/bin/bash
# PCM-12.2 — AT-17 (Grafana), AT-18 (Word Factory readiness), AT-19 (ES readiness)
# READ-ONLY: no container start/stop, no index creation, no writes to operational dirs.
# The only state change is the backend unit-test run, which uses its own temp DB (PCT_DB).
set -u

SRC=/home/saber/saberprojects/persian-corpus-toolkit

echo "===== AT-17: Grafana state ====="
docker ps -a --format '{{.Names}}|{{.Image}}|{{.Status}}|{{.Ports}}' | grep -i -E 'grafana|prometheus' || echo "(no grafana/prometheus containers)"
(ss -ltn 2>/dev/null | grep -E ':(3000|9090) ') || echo "(ports 3000/9090 not listening)"
G=$(docker ps --format '{{.Names}}' | grep -i grafana | head -1)
if [ -n "$G" ]; then
  echo "--- container: $G ---"
  docker exec "$G" wget -qO- http://localhost:3000/api/health 2>/dev/null || echo "(health via wget failed)"
  echo ""
  echo "--- provisioned datasources ---"
  docker exec "$G" sh -c 'ls -la /etc/grafana/provisioning/datasources/ 2>/dev/null && head -80 /etc/grafana/provisioning/datasources/*.yml 2>/dev/null' || echo "(no datasources dir)"
  echo ""
  echo "--- provisioned dashboards ---"
  docker exec "$G" sh -c 'ls -la /etc/grafana/provisioning/dashboards/ 2>/dev/null; ls -la /var/lib/grafana/dashboards 2>/dev/null' || echo "(no dashboards dir)"
else
  echo "(grafana container not running — nothing to probe)"
fi

echo ""
echo "===== AT-18: Word Factory readiness ====="
echo "--- deployed backend/requirements.txt ---"
cat "$SRC/backend/requirements.txt"
echo ""
V="$SRC/backend/.venv/bin/python"
echo "--- venv python-docx check ---"
if [ -x "$V" ]; then
  "$V" -c "import docx; print('python-docx: INSTALLED')" 2>/dev/null || echo "python-docx: ABSENT in venv"
else
  echo "(no .venv python at expected path)"
fi
echo "--- disk (deploy volume) ---"
df -h /home/saber | tail -1
echo "--- RAM ---"
free -h | head -2
echo ""
echo "--- backend unit test suite (isolated temp DB via PCT_DB) ---"
cd "$SRC/backend"
if [ -x "$V" ]; then
  "$V" -m unittest test_api test_projects test_dashboard 2>&1 | tail -6
else
  python3 -m unittest test_api test_projects test_dashboard 2>&1 | tail -6
fi

echo ""
echo "===== AT-19: Elasticsearch readiness ====="
docker ps -a --format '{{.Names}}|{{.Image}}|{{.Status}}|{{.Ports}}' | grep -i -E 'elastic|(^|/)es' || echo "(no ES containers at all)"
(ss -ltn 2>/dev/null | grep ':9200 ') || echo "(port 9200 not listening)"
echo "--- ES in our docker-compose? ---"
grep -i -n 'elastic' "$SRC/docker-compose.yml" || echo "(no ES service in persian-corpus-toolkit docker-compose.yml)"
echo "--- stopped ES container details (from PCM-12 audit: taghrir-es) ---"
ESN=$(docker ps -a --format '{{.Names}}' | grep -i elastic | head -1)
if [ -n "$ESN" ]; then
  docker inspect "$ESN" --format 'image={{.Config.Image}} state={{.State.Status}} created={{.Created}}' 2>/dev/null
  du -sh "/var/lib/docker/volumes/$(docker inspect "$ESN" --format '{{range .Mounts}}{{.Name}}{{end}}')" 2>/dev/null || true
fi
echo "--- capacity for a future ES instance ---"
free -h | head -2
df -h / | tail -1
nproc
echo ""
echo "AT-17/18/19 done"

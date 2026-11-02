#!/usr/bin/env bash
# =============================================================================
# PCM-18 — s52 read-only OBSERVABILITY audit (NO deploy, NO writes, NO restart,
# NO credential rotation, NO login).
#
# هدف (scope PCM-18):
#   1) زیرساخت مانیتورینگ موجود s52 سالم است؟
#        prometheus / grafana / loki / node-exporter — وضعیت containerها
#        + health endpointهای عمومی (بدون credential)
#   2) آیا backend PCT endpoint مانیتورینگ دارد؟
#        GET /api/metrics باید 404 بدهد (PCM-10 هنوز پیش‌رو؛ در PCM-18 ساخته
#        نمی‌شود — فقط وضعیت فعلی ثبت می‌شود)
#   3) scrape-job PCT در Prometheus هست؟ (باید نباشد؛ PCM-10)
#   4) داشبورد PCT در Grafana هست؟ (باید نباشد؛ PCM-10)
#   5) ممیزی credential — masked: فقط ساختار/کلید/permissions؛ هیچ مقدار
#      رازی چاپ نمی‌شود (دستور §2.5: رمز در لاگ/گزارش نمی‌آید)
#   6) وضعیت production PCT (سالم بودن + DB integrity فقط-خوانده)
#
# اجرای این چک هیچ تغییری ایجاد نمی‌کند.
#
# اجرا از لپ‌تاپ:
#   ssh -p 22 saber@172.20.1.52 "bash -s" < deploy/pcm18_s52_observability_audit.sh
# =============================================================================
set +e
APP=/home/saber/saberprojects/persian-corpus-toolkit
OBS=/home/saber/saberprojects/observability

echo "== 1. observability stack container status (read-only) =="
docker ps -a --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}' 2>/dev/null \
  | grep -E 'NAMES|prometheus|grafana|loki|node.exporter|cadvisor|pg.exporter' || true

echo
echo "== 2. health endpoints (public, no creds) =="
curl -s -m 5 -o /dev/null -w 'prometheus  /-/healthy        -> %{http_code}\n' http://127.0.0.1:9090/-/healthy
curl -s -m 5 -o /dev/null -w 'prometheus  /-/ready           -> %{http_code}\n' http://127.0.0.1:9090/-/ready
curl -s -m 5 -o /dev/null -w 'grafana     /api/health        -> %{http_code}\n' http://127.0.0.1:3001/api/health
curl -s -m 5 -o /dev/null -w 'loki        /ready             -> %{http_code}\n' http://127.0.0.1:3100/ready
curl -s -m 5 -o /dev/null -w 'node-exporter /metrics (200?)  -> %{http_code}\n' http://127.0.0.1:9100/metrics
echo -n 'grafana /api/health body: '; curl -s -m 5 http://127.0.0.1:3001/api/health | head -c 200; echo

echo
echo "== 3. PCT backend: metrics endpoint (expect 404 pre-PCM-10) =="
curl -s -o /dev/null -w 'GET /api/metrics (pre-10, expect 404) -> %{http_code}\n' --max-time 5 http://127.0.0.1:5055/api/metrics
curl -s -o /dev/null -w 'GET /api/stats (existing)            -> %{http_code}\n' --max-time 5 http://127.0.0.1:5055/api/stats

echo
echo "== 4. Prometheus: is a PCT scrape job present? (expect NO pre-PCM-10) =="
PROMCFG=$(docker inspect prometheus 2>/dev/null | grep -oE '"[^"]*prometheus[^"]*\.(yml|yaml)"' | head -1 | tr -d '"')
echo "-- prometheus config file (from container inspect): ${PROMCFG:-<not found>}"
# search all likely config locations for a PCT target
for c in \
  "$OBS/prometheus/prometheus.yml" \
  "$OBS/prometheus/prometheus.yaml" \
  "$OBS/prometheus/config/prometheus.yml" \
  "$OBS/prometheus/config/prometheus.yaml" \
  "$OBS/prometheus/data/prometheus.yml" ; do
  if [ -f "$c" ]; then
    echo "-- config file found: $c (perms: $(stat -c '%a' "$c"))"
    echo -n '  job names: '
    grep -oE '^\s*-\s*job_name:\s*\S+' "$c" | sed 's/.*job_name:\s*//' | tr '\n' ' '; echo
    if grep -nE '5055|persian.corpus|pct' "$c" 2>/dev/null; then
      echo "  NOTE: PCT-looking target found (PCM-10 scrape job present?)"
    else
      echo "  OK: no PCT target in this config (as expected pre-PCM-10)"
    fi
  fi
done
# live targets query (read-only HTTP)
echo "-- live targets (name + state + scrapeUrl, masked host) --"
curl -s -m 5 "http://127.0.0.1:9090/api/v1/targets" 2>/dev/null \
  | python3 -c '
import json,sys
try:
  d=json.load(sys.stdin)
  for t in d.get("data",{}).get("activeTargets",[]):
    lab=t.get("labels",{})
    su=t.get("scrapeUrl","")
    # mask any creds in url (should be none)
    import re
    su=re.sub(r"(?<=://)[^/@:]*:[^/@]*@","user:***@",su)
    print(f"  [{t.get(\"health\")}] job={lab.get(\"job\",\"?\")} url={su}")
except Exception as e:
  print(f"  (targets parse failed: {e})")
' 2>/dev/null || echo "  (targets query failed)"

echo
echo "== 5. Grafana: PCT dashboards? (expect NONE pre-PCM-10) =="
echo "-- dashboards dir on host (names only) --"
for d in "$OBS/grafana/provisioning/dashboards" "$OBS/grafana/dashboards"; do
  [ -d "$d" ] && echo "$d:" && (cd "$d" && find . -name '*.json' 2>/dev/null | sed 's/^\.\///' | head -30)
done
echo "-- dashboard provisioning: folders/paths (names only, no values) --"
for f in "$OBS"/grafana/provisioning/dashboards/*.yml; do
  [ -f "$f" ] && echo "$f:" && sed -E 's#(path:).*#\1 <VALUE-MASKED>#; s#(folders:).*#\1 <VALUE-MASKED>#' "$f" | head -15
done
echo "-- live dashboards via public /api/search (no auth needed? if 401, skip) --"
curl -s -m 5 -o /dev/null -w 'grafana /api/search (no creds) -> %{http_code}\n' http://127.0.0.1:3001/api/search

echo
echo "== 6. credential audit (MASKED — structure/keys/perms only, no values) =="
echo "-- datasource file(s) --"
python3 - <<'PYEOF'
import glob, hashlib, os, re, stat
prov = "/home/saber/saberprojects/observability/grafana/provisioning/datasources"
files = sorted(glob.glob(os.path.join(prov, "datasources.yml*")))
if not files:
    print("  (no datasources.yml found under provisioning/datasources)")
for f in files:
    st = os.stat(f)
    mode = stat.filemode(st.st_mode)
    print(f"FILE: {f}")
    print(f"  perms: {mode}  (600/640 = restricted; 644 = world-readable)")
    data = open(f, encoding="utf-8", errors="replace").read()
    print(f"  md5: {hashlib.md5(data.encode()).hexdigest()}  size={st.st_size}B")
    names = re.findall(r"^\s*-?\s*name:\s*(\S.*)$", data, flags=re.M)
    print(f"  datasource names: {names}")
    keys = sorted(set(re.findall(r"^\s*([a-zA-Z_]+):", data, flags=re.M)))
    print(f"  keys: {keys}")
    for k in ("password","passwd","user","username","secureJsonData","accessToken","apiKey"):
        if re.search(rf"^\s*{k}:", data, flags=re.M):
            print(f"  NOTE: credential-ish key '{k}' present (value NOT shown)")
    urls = re.findall(r"^\s*url:\s*(\S+)", data, flags=re.M)
    for u in urls:
        masked = re.sub(r"(?<=://)[^/@:]*:[^/@]*@", "user:***@", u.strip())
        flag = "INLINE-CREDS-ROTATE" if masked != u.strip() else "no-inline-creds"
        print(f"  url (masked): {masked}  [{flag}]")
PYEOF
echo "-- how is GF_SECURITY_ADMIN_PASSWORD supplied? (masked) --"
for cf in "$OBS"/docker-compose*.yml "$OBS"/compose*.yml; do
  [ -f "$cf" ] || continue
  echo "compose: $cf (perms: $(stat -c '%a' "$cf"))"
  grep -n "GF_SECURITY_ADMIN" "$cf" | sed -E "s#(:[[:space:]]*[\"']?)(\$?[A-Za-z0-9_]*:?[A-Za-z0-9_:/-]*)\1?.*$#\1<REF-MASKED>#" || true
  grep -n "env_file" "$cf" || true
done
for envf in "$OBS"/.env "$OBS"/grafana/.env; do
  [ -f "$envf" ] && echo "env file: $envf (perms: $(stat -c '%a' "$envf")) keys: $(grep -oE '^[A-Z_]+=' "$envf" | tr -d '=' | tr '\n' ' ')"
done

echo
echo "== 7. PCT production status (read-only) =="
docker ps --filter name=persian-corpus-toolkit --format 'table {{.Names}}\t{{.Status}}' 2>/dev/null || true
curl -s -o /dev/null -w 'GET /dashboard/studio.html -> %{http_code}\n' --max-time 5 http://127.0.0.1:5055/dashboard/studio.html
DB="$APP/backend/thesaurus.db"
if command -v sqlite3 >/dev/null 2>&1 && [ -f "$DB" ]; then
  echo -n 'PRAGMA integrity_check: '; sqlite3 "$DB" "PRAGMA integrity_check;"
  echo -n 'db mtime: '; stat -c '%y' "$DB" 2>/dev/null
fi
echo "-- .env present & perms (never printing content) --"
stat -c '%a %n' "$APP/.env" 2>/dev/null || echo "(no .env)"

echo
echo "== 8. host resources (read-only) =="
echo "-- disk --"; df -h / /home 2>/dev/null | head -5
echo "-- memory --"; free -h 2>/dev/null | head -3
echo "-- uptime --"; uptime 2>/dev/null

echo
echo "DONE — read-only; nothing was written, restarted, rotated, or deployed."

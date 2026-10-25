#!/bin/bash
# PCM-12.3 — non-destructive Grafana credential audit (s52).
# READ-ONLY: no restart, no config change, no credential rotation, no login.
# Secrets are NEVER printed: values masked; only structure/names/paths shown.
set +e

echo "=== [4] host-side datasource file: structure, keys, masked values ==="
python3 - <<'PYEOF'
import glob, hashlib, os, re, stat

prov = "/home/saber/saberprojects/observability/grafana/provisioning/datasources"
files = sorted(glob.glob(os.path.join(prov, "datasources.yml*")))
SAFE_KEYS = {"name", "type", "isDefault"}

def mask_url(u):
    m = re.sub(r"(?<=://)[^/@:]*:[^/@]*@", "user:***@", u.strip())
    return m

for f in files:
    st = os.stat(f)
    mode = stat.filemode(st.st_mode)
    print(f"FILE: {f}")
    print(f"  perms: {mode} size={st.st_size}B")
    data = open(f, encoding="utf-8", errors="replace").read()
    print(f"  md5: {hashlib.md5(data.encode()).hexdigest()}")
    # top-level datasource names
    names = re.findall(r"^\s*-?\s*name:\s*(\S.*)$", data, flags=re.M)
    print(f"  datasource entries (name:): {names}")
    # keys present (names only)
    keys = set(re.findall(r"^\s*([a-zA-Z_]+):", data, flags=re.M))
    print(f"  keys: {sorted(keys)}")
    # any inline credentials in url values?
    urls = re.findall(r"^\s*url:\s*(\S+)", data, flags=re.M)
    for u in urls:
        masked = mask_url(u)
        has_creds = masked != u.strip()
        print(f"  url sample (masked): {masked}  [inline-creds: {'YES-ROTATE' if has_creds else 'no'}]")
    # secret-ish keys present?
    for k in ("password", "passwd", "user", "username", "secureJsonData", "accessToken", "apiKey"):
        if re.search(rf"^\s*{k}:", data, flags=re.M):
            print(f"  NOTE: key '{k}' present (value masked, not shown)")

# backup files: identical to current?
cur = os.path.join(prov, "datasources.yml")
if os.path.exists(cur):
    cur_md5 = hashlib.md5(open(cur, "rb").read()).hexdigest()
    for f in files:
        if f != cur and os.path.exists(f):
            m = hashlib.md5(open(f, "rb").read()).hexdigest()
            print(f"  backup {os.path.basename(f)} same-as-current: {m == cur_md5}")
PYEOF

echo ""
echo "=== [5] how is GF_SECURITY_ADMIN_PASSWORD supplied? (masked) ==="
OBS=/home/saber/saberprojects/observability
ls -la "$OBS" 2>/dev/null | head -12
for cf in "$OBS"/docker-compose*.yml "$OBS"/compose*.yml; do
  [ -f "$cf" ] || continue
  echo "--- compose file: $cf"
  grep -n "GF_SECURITY_ADMIN" "$cf" | sed -E "s#(:[[:space:]]*\$?)\S.*#\1<MASKED-OR-VAR-REF>#" || true
  grep -n "env_file" "$cf" || true
done
for envf in "$OBS"/.env "$OBS"/grafana/.env; do
  [ -f "$envf" ] && echo "--- env file: $envf (perms: $(stat -c '%a' "$envf")) keys: $(grep -oE '^[A-Z_]+=' "$envf" | tr -d '=' | tr '\n' ' ')"
done

echo ""
echo "=== [6] Grafana version + public health (no creds used) ==="
docker exec grafana sh -c 'grafana server -v 2>/dev/null' | head -1 || true
curl -s -m 5 -o /dev/null -w "HTTP /api/health (no creds): %{http_code}\n" http://127.0.0.1:3000/api/health
curl -s -m 5 http://127.0.0.1:3000/api/health | head -c 300; echo

echo ""
echo "=== [7] provisioning reload mechanism (no restart needed for rotate) ==="
docker exec grafana grep -i -E "enable|interval" /etc/grafana/provisioning/datasources/datasources.yml 2>/dev/null | head -3 || true
docker logs grafana 2>&1 | grep -i -E "provisioning|datasource" | tail -5

echo ""
echo "grafana audit done (read-only)"

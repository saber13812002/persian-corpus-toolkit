#!/bin/bash
set -u
echo "== nginx.conf includes =="
grep -nE 'include|server_name|proxy_pass|listen' /etc/nginx/nginx.conf 2>/dev/null | head -20
echo "== conf.d =="
for f in /etc/nginx/conf.d/*; do
  [ -f "$f" ] || continue
  echo "-- $f --"
  grep -nE 'server_name|listen|proxy_pass|location ' "$f" | head -12
done
echo "== sites =="
ls /etc/nginx/sites-enabled/ 2>/dev/null
for f in /etc/nginx/sites-enabled/*; do
  [ -f "$f" ] || continue
  echo "-- $f --"
  grep -nE 'server_name|listen|proxy_pass|location |ssl_certificate ' "$f" | head -15
done
echo "== wikijs redirect =="
curl -s -m 3 -o /dev/null -w 'code=%{http_code} loc=%{redirect_url}\n' http://127.0.0.1:3000/
echo "== dashboard api routes (deployed) =="
grep -oE '"/api/dashboard/[a-z_/-]+"' /home/saber/saberprojects/persian-corpus-toolkit/backend/dashboard_api.py 2>/dev/null | sort -u | head -15

#!/bin/bash
# PCM-14B.3 — find how 5055 is (or isn't) exposed externally on s52.
echo "=== containers publishing 80/443 ==="
docker ps --format '{{.Names}} | {{.Ports}}' | grep -E '\-> :?(443|80)( |$)' | head
echo ""
echo "=== nginx/kong inside candidate containers: 5055 ==="
for c in cms_nginx kong-gw-manage-52 kong-admin-auth-52 llmhub-header-test-proxy-1; do
  hit=$(docker exec "$c" sh -c 'grep -rn 5055 /etc/nginx /usr/local/openresty 2>/dev/null | head -3' 2>/dev/null)
  [ -n "$hit" ] && { echo "[$c] $hit"; }
done
echo ""
echo "=== homarr (portable dashboards often list apps) ==="
docker exec homarr sh -c 'cat /app/data/*.json /app/data/*.yaml 2>/dev/null' | grep -i -o '"url"[^,]*' | head -10
echo ""
echo "=== try candidate external URLs (443) ==="
for h in sabermate.ir www.sabermate.ir pct.sabermate.ir studio.sabermate.ir corpus.sabermate.ir dashboard.sabermate.ir; do
  code=$(curl -sk -o /dev/null -w '%{http_code}' --max-time 5 "https://$h/dashboard/studio.html" 2>/dev/null)
  echo "$h/dashboard/studio.html -> $code"
done
echo ""
echo "=== direct 5055 from LAN IP ==="
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 http://172.20.1.52:5055/dashboard/studio.html 2>/dev/null)
echo "http://172.20.1.52:5055/dashboard/studio.html -> $code"

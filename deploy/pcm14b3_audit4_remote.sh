#!/bin/bash
set -u
echo "== BT vhost dir =="
ls /www/server/panel/vhost/nginx/ 2>/dev/null
echo "== all server_name + proxy_pass in BT vhosts =="
grep -rln '5055' /www/server/panel/vhost/nginx/ 2>/dev/null
for f in /www/server/panel/vhost/nginx/*.conf; do
  [ -f "$f" ] || continue
  sn=$(grep -m1 'server_name' "$f" 2>/dev/null)
  pp=$(grep -m3 'proxy_pass' "$f" 2>/dev/null | tr '\n' ' | ')
  echo "$f :: $sn :: $pp"
done
echo "== the PCT vhost (full) =="
f=$(grep -rl '5055' /www/server/panel/vhost/nginx/ 2>/dev/null | head -1)
[ -n "$f" ] && cat "$f"
echo "== wikijs public URL check (443 default?) =="
curl -sk -m 3 http://127.0.0.1:3000/api/config -o /dev/null -w 'wiki 3000 api -> %{http_code}\n'

#!/bin/bash
set -u
echo "== main nginx.conf (readable parts) =="
head -60 /www/server/nginx/conf/nginx.conf 2>/dev/null || echo "(saber cannot read; needs root)"
echo "== grep 5055 anywhere readable =="
grep -rls '5055' /www/server/nginx/conf/ /etc/nginx/ /www/panel/ 2>/dev/null | head
echo "== BT panel web vhosts =="
ls /www/server/panel/vhost/ 2>/dev/null
ls /www/server/panel/vhost/web/ 2>/dev/null | head
echo "== sudo test =="
sudo -n true 2>&1 | head -1
echo "== wiki login page =="
curl -sk -m 3 https://172.20.1.52/login -o /dev/null -w 'code=%{http_code}\n'
curl -sk -m 3 https://172.20.1.52/api/config 2>/dev/null | head -c 200; echo

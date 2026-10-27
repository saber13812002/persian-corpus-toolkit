#!/bin/bash
set -u
echo "== nginx process =="
ps aux | grep -E 'nginx' | grep -v grep | head -4
echo "== nginx binary conf path =="
which nginx && nginx -V 2>&1 | tr ' ' '\n' | grep -E 'conf-path|prefix' | head -3
echo "== find conf files =="
ls /etc/nginx/ 2>/dev/null
find /etc/nginx /www /opt -name '*.conf' -newer /etc/hostname 2>/dev/null | head -10
echo "== nginx -T server_name/proxy_pass (host) =="
nginx -T 2>/dev/null | grep -nE 'server_name|proxy_pass|listen |location /' | head -40
echo "== https redirect target =="
curl -sk -m 3 -o /dev/null -w 'code=%{http_code} loc=%{redirect_url}\n' https://127.0.0.1/
curl -sk -m 3 -o /dev/null -w 'code=%{http_code} loc=%{redirect_url}\n' https://172.20.1.52/
echo "== homarr (port 7575?) =="
curl -s -m 3 -o /dev/null -w '7575: code=%{http_code} loc=%{redirect_url}\n' http://127.0.0.1:7575/

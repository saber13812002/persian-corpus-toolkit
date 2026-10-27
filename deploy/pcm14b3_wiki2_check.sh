#!/bin/bash
# PCM-14B.3 — Wiki.js home page: list existing page links.
W=http://127.0.0.1:8888
curl -s --max-time 8 "$W/" -o /tmp/pct14b3-wiki-home.html
echo "=== internal links on home ==="
grep -o 'href="/[^"]*"' /tmp/pct14b3-wiki-home.html | sort -u | grep -v '_assets\|api\|login\|admin' | head -40
echo "=== h1/h2 ==="
grep -o '<h[12][^>]*>[^<]*</h[12]>' /tmp/pct14b3-wiki-home.html | head -10

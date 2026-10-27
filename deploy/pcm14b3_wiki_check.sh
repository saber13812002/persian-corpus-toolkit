#!/bin/bash
# PCM-14B.3 — Wiki.js status check (does the guide page exist?).
set -u
W=http://127.0.0.1:8888
echo "=== wiki home ==="
curl -s --max-time 8 "$W/" -o /tmp/pct14b3-wiki.html -w "home: %{http_code}\n"
grep -o '<title>[^<]*</title>' /tmp/pct14b3-wiki.html | head -1
echo "=== search: word factory / knowledge / studio ==="
for t in "Word%20Factory" "Word%20Studio" "Knowledge" "PCM14B"; do
  n=$(curl -s --max-time 8 "$W/api/page?search=$t" | head -c 200)
  echo "search $t: $n"
done
echo "=== page list (api) ==="
curl -s --max-time 8 "$W/api/pages?category=/&limit=100" | head -c 800
echo
echo "=== direct page slugs ==="
for p in "word-factory-user-guide" "word-factory" "word-studio" "knowledge-studio" "pcm14b"; do
  c=$(curl -s -o /dev/null -w '%{http_code}' --max-time 8 "$W/$p")
  echo "/$p -> $c"
done

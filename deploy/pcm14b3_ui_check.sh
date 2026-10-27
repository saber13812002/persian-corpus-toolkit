#!/bin/bash
# PCM-14B.3 — Phase 4c: UI checks for /dashboard/studio.html on s52.
# Verifies: serving, content-type, RTL/FA, login overlay markup, and that
# every endpoint the UI calls is live (401 without session, 200 with).
set -u
BASE=http://127.0.0.1:5055
APP=/home/saber/saberprojects/persian-corpus-toolkit
PW=$(grep '^PCT_DASHBOARD_PASSWORD=' "$APP/.env" | cut -d= -f2-)
PASS=0; FAIL=0
ok()   { PASS=$((PASS+1)); echo "PASS  $1"; }
bad()  { FAIL=$((FAIL+1)); echo "FAIL  $1"; }

echo "=== 1. serving & headers ==="
HDRS=$(curl -s -D - -o /tmp/pct14b3-studio.html "$BASE/dashboard/studio.html")
echo "$HDRS" | head -1 | grep -q "200" && ok "studio.html -> 200" || bad "studio.html not 200"
echo "$HDRS" | grep -qi "content-type: text/html" && ok "content-type text/html" || bad "content-type"
echo "$HDRS" | grep -qi "x-frame-options\|content-security" && ok "frame/security header present" || echo "info: no X-Frame-Options/CSP (optional)"
SZ=$(wc -c < /tmp/pct14b3-studio.html)
[ "$SZ" -gt 10000 ] && ok "served size $SZ bytes (real page)" || bad "served size $SZ (suspicious)"

echo "=== 2. RTL / FA / structure ==="
grep -q 'lang="fa"' /tmp/pct14b3-studio.html && ok "lang=fa" || bad "lang=fa missing"
grep -q 'dir="rtl"' /tmp/pct14b3-studio.html && ok "dir=rtl" || bad "dir=rtl missing"
grep -q '<!DOCTYPE html>' /tmp/pct14b3-studio.html && ok "doctype" || bad "doctype missing"
grep -q 'id="loginOverlay"\|id="login-overlay"\|loginPassword' /tmp/pct14b3-studio.html && ok "login overlay markup" || bad "login overlay missing"
grep -q 'charset="UTF-8"\|charset=UTF-8' /tmp/pct14b3-studio.html && ok "utf-8 meta" || bad "utf-8 meta missing"

echo "=== 3. served bytes == repo bytes (no rewrite/proxy tampering) ==="
H1=$(sha256sum /tmp/pct14b3-studio.html | cut -d' ' -f1)
H2=$(sha256sum "$APP/dashboard/studio.html" | cut -d' ' -f1)
[ "$H1" = "$H2" ] && ok "served sha == repo sha" || bad "served sha mismatch ($H1 vs $H2)"

echo "=== 4. every UI endpoint is live (unauth -> 401, auth -> 200) ==="
CJ=/tmp/pct14b3ui-cookies.txt; rm -f "$CJ"
code=$(curl -s -c "$CJ" -o /dev/null -w '%{http_code}' -X POST "$BASE/api/auth/login" -H 'Content-Type: application/json' -d "{\"password\":\"$PW\"}")
[ "$code" = "200" ] && ok "login from UI-check" || bad "login ($code)"
# endpoints the studio UI calls (path without dynamic segments)
# pick a real existing collection id (collections use c-<hex> ids, not integers)
CID=$(curl -s -b "$CJ" "$BASE/api/knowledge/collections?limit=1" \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['collections'][0]['collection_id'] if d['collections'] else '')")
EPTS=(
  "GET /api/auth/status"
  "GET /api/knowledge/collections"
  "GET /api/knowledge/subjects"
  "GET /api/knowledge/collections/$CID"
  "GET /api/knowledge/collections/$CID/documents"
  "GET /api/knowledge/jobs"
  "GET /api/knowledge/compatibility"
  "GET /api/knowledge/metadata/fields"
)
if [ -z "$CID" ]; then echo "info: no collection in prod DB (fresh) — skipping detail endpoints"; fi
for e in "${EPTS[@]}"; do
  m=${e%% *}; p=${e#* }
  case "$p" in *collections/$CID*) [ -z "$CID" ] && continue;; esac
  u=$(curl -s -o /dev/null -w '%{http_code}' -b "$CJ" -X "$m" "$BASE$p")
  [ "$u" = "200" ] && ok "auth  $e -> 200" || bad "auth  $e -> $u"
done
# dynamic ones that 404 legitimately with no data
u=$(curl -s -o /dev/null -w '%{http_code}' -b "$CJ" "$BASE/api/knowledge/collections/999999")
[ "$u" = "404" ] && ok "auth  detail unknown -> 404" || bad "detail unknown -> $u"
# unauth on the protected set
u=$(curl -s -o /dev/null -w '%{http_code}' "$BASE/api/knowledge/collections")
[ "$u" = "401" ] && ok "noauth collections -> 401 (login overlay will trigger)" || bad "noauth -> $u"
rm -f "$CJ" /tmp/pct14b3-studio.html

echo "=== 5. external reachability (is there a 443/80 proxy to 5055?) ==="
LISTEN=$(ss -tlnp 2>/dev/null | grep -E ':(443|80)\s' | head -5)
echo "$LISTEN"
echo "(external URL: http://172.20.1.52:5055/dashboard/studio.html if no proxy)"

echo "======================================"
echo "RESULT: PASS=$PASS FAIL=$FAIL"
[ "$FAIL" = "0" ] && echo "UI-CHECK-PASS" || echo "UI-CHECK-FAILED"

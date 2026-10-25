#!/usr/bin/env bash
# PCM-12.2 — read-only acceptance tests (AT-01..AT-14) against 127.0.0.1:5055
# Safe: only GET requests + one login. Never pauses/stops/deletes anything.
set -u
BASE=http://127.0.0.1:5055
PROJ=2   # running project «تفسیر تسنیم همتا»

# ---- login (password from .env, never displayed) ----
cd /home/saber/saberprojects/persian-corpus-toolkit 2>/dev/null || cd "$(dirname "$0")"
PW=$(grep -oP 'PCT_DASHBOARD_PASSWORD=\K.*' .env 2>/dev/null || true)
JAR=/tmp/pct_acc_$$.jar
if [ -z "$PW" ]; then
  echo "AUTH=DEV_MODE_OPEN (no password seeded)"
else
  LOGIN=$(curl -s -m 10 -c "$JAR" -X POST -H 'Content-Type: application/json' \
    -d "{\"password\":\"$PW\"}" $BASE/api/auth/login)
  echo "AT-01 login response: $LOGIN"
fi

auth() { curl -s -m 15 -b "$JAR" "$@"; }

echo; echo "===== AT-01: auth status ====="
auth $BASE/api/auth/status; echo

echo; echo "===== AT-02: projects list (names, hosts, stats) ====="
auth "$BASE/api/dashboard/projects?page=1&per_page=25&sort=updated_at&order=DESC" \
 | python3 -c "
import json,sys
d=json.load(sys.stdin)
print('total:',d['total'],'page:',d['page'],'/',d['total_pages'])
for p in d['projects']:
    pts=p.get('points') or []
    print(f\"  #{p['id']} {p['name']} | host={p['host']} | status={p['status']} | saved={p['saved_count']} skipped={p['skipped_count']} failed={p['failed_count']} | points={len(pts)} | updated={p['updated_at']}\")
"

echo; echo "===== AT-02b: project search (esra) ====="
auth "$BASE/api/dashboard/projects?page=1&per_page=5&search=esra" \
 | python3 -c "
import json,sys
d=json.load(sys.stdin)
print('search total:',d['total'])
for p in d['projects']: print('  match:',p['id'],p['name'],p['host'])
"

echo; echo "===== AT-03: pages of project 2 (pagination) ====="
auth "$BASE/api/dashboard/projects/2/pages?page=1&per_page=5&sort=id&order=DESC" \
 | python3 -c "
import json,sys
d=json.load(sys.stdin)
print('total pages:',d['total'],'| page',d['page'],'of',d['total_pages'],'| per_page',d['per_page'])
for r in d['pages']:
    vals=r.get('values') or {}
    print(f\"  page_id={r['id']} prev={r.get('prev_id')} next={r.get('next_id')} url={r['url'][:70]}... captured={r['captured_at']} fields={list(vals.keys())}\")
"

echo; echo "===== AT-03b: page 2 of the same list (offset works) ====="
auth "$BASE/api/dashboard/projects/2/pages?page=2&per_page=5&sort=id&order=DESC" \
 | python3 -c "
import json,sys
d=json.load(sys.stdin)
ids=[r['id'] for r in d['pages']]
print('page 2 ids (should be 5 ids lower than page 1):',ids)
"

echo; echo "===== AT-04: search within pages (query 'حم') ====="
auth "$BASE/api/dashboard/projects/2/pages?page=1&per_page=3&search=%D8%AD%D9%85" \
 | python3 -c "
import json,sys
d=json.load(sys.stdin)
print('search total:',d['total'])
for r in d['pages'][:3]:
    vals=r.get('values') or {}
    t=(vals.get('متن') or vals.get('title') or '')[:60]
    print(f\"  hit id={r['id']} url={r['url'][:60]}... sample_text={t}\")
"

echo; echo "===== AT-05: page detail (all stored fields + JSON) ====="
FIRST_ID=$(auth "$BASE/api/dashboard/projects/2/pages?page=1&per_page=1&sort=id&order=DESC" \
  | python3 -c "import json,sys; print(json.load(sys.stdin)['pages'][0]['id'])")
auth "$BASE/api/dashboard/projects/2/pages/$FIRST_ID"; echo

echo; echo "===== AT-06: prev/next consistency (middle row) ====="
auth "$BASE/api/dashboard/projects/2/pages?page=1&per_page=5&sort=id&order=ASC" \
 | python3 -c "
import json,sys
d=json.load(sys.stdin)
rows=d['pages']
ok=True
for i,r in enumerate(rows):
    exp_prev = rows[i-1]['id'] if i>0 else None
    exp_next = rows[i+1]['id'] if i<len(rows)-1 else None
    if r.get('prev_id')!=exp_prev or r.get('next_id')!=exp_next:
        ok=False; print('MISMATCH at',r['id'],r.get('prev_id'),r.get('next_id'),'expected',exp_prev,exp_next)
print('prev/next consistent within window:',ok,'(window size',len(rows),')')
"

echo; echo "===== AT-11: resume capability (cursor vs latest page) ====="
auth "$BASE/api/dashboard/projects/2" \
 | python3 -c "
import json,sys
p=json.load(sys.stdin)
cur=p.get('cursor_url') or ''
last=p.get('pages_summary',{}).get('last_url') or ''
print('cursor_url:',cur[:100])
print('last_page :',last[:100])
print('match:',cur==last)
"

echo; echo "===== AT-12: natural end detection (logic present?) ====="
grep -n "next_mode\|none\|end" /home/saber/saberprojects/persian-corpus-toolkit/backend/projects.py | head -20
grep -n "next\b\|nextMode\|next_url\|endReached\|done" /home/saber/saberprojects/persian-corpus-toolkit/extension/background.js | head -25

echo; echo "===== AT-13: reverse navigation ====="
grep -n "prev\|previous\|back" /home/saber/saberprojects/persian-corpus-toolkit/extension/background.js | head -15
grep -rn "prev_id\|next_id" /home/saber/saberprojects/persian-corpus-toolkit/dashboard/index.html | head -10

echo; echo "===== AT-14: transforms implemented ====="
grep -n "transform" /home/saber/saberprojects/persian-corpus-toolkit/extension/content_picker.js 2>/dev/null | head
grep -n "def \|transform\|strip\|replace" /home/saber/saberprojects/persian-corpus-toolkit/extension/shared.js | head -25
grep -n "transform" /home/saber/saberprojects/persian-corpus-toolkit/backend/projects.py | head -10

rm -f "$JAR"
echo; echo DONE

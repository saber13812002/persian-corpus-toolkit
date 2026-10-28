#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════════
# PCM-14C.1 — read-only audit: orphan files in data/knowledge + ES discovery
# READ-ONLY: no deletes, no mutations, no container restart.
# ═══════════════════════════════════════════════════════════════════════════
set -u
APP=/home/saber/saberprojects/persian-corpus-toolkit
C=persian-corpus-toolkit-backend-1
cd "$APP" || exit 1

echo "== 1. manifests: file/work/edition/volume ids =="
for d in data/knowledge/out/f-*; do
  m="$d/manifest.json"
  [ -f "$m" ] || { echo "== $d: NO MANIFEST"; continue; }
  python3 - "$m" <<'PYEOF'
import json, sys
m = json.load(open(sys.argv[1], encoding="utf-8"))
f = m["file"]
print(f"{sys.argv[1].split('/')[2]}: file_id={f['file_id']} filename={f['filename']} "
      f"sha={f['sha256'][:12]} work={m.get('work_id')} edition={m.get('edition_id')} "
      f"volume={m.get('volume_id')} status={m.get('processing',{}).get('status')}")
PYEOF
done

echo "== 2. DB reference check (live DB, read-only) =="
sqlite3 backend/thesaurus.db <<'SQL'
SELECT 'collections', COUNT(*) FROM knowledge_collections;
SELECT 'documents', COUNT(*) FROM knowledge_collection_documents;
SELECT 'jobs', COUNT(*) FROM knowledge_jobs;
SELECT 'batches', COUNT(*) FROM knowledge_import_batches;
SELECT 'meta_fields', COUNT(*) FROM knowledge_metadata_fields;
SELECT 'meta_values', COUNT(*) FROM knowledge_metadata_values;
SELECT 'index_builds', COUNT(*) FROM knowledge_index_builds;
SELECT 'docs_referencing_works', COUNT(*) FROM knowledge_collection_documents WHERE work_id IS NOT NULL AND work_id != '';
SELECT 'meta_values_scopes', scope, COUNT(*) FROM knowledge_metadata_values GROUP BY scope;
SQL

echo "== 3. sha256 of stored originals (container root view) =="
docker exec "$C" sh -c 'sha256sum /data-files/knowledge/files/*/*.docx 2>/dev/null'

echo "== 4. sha256 of out/files copies (container root view) =="
docker exec "$C" sh -c 'sha256sum /data-files/knowledge/out/files/*.docx 2>/dev/null'

echo "== 5. container user + file owner mismatch =="
docker inspect "$C" --format 'user={{.Config.User}}'
docker exec "$C" sh -c 'id'

echo "== 6. big outputs: line counts (why 125M) =="
for d in f-08c367cb f-8c7f42dd f-f6df45ae; do
  n=$(wc -l < "data/knowledge/out/$d/blocks.jsonl" 2>/dev/null)
  c=$(python3 -c "import json;print(json.load(open('data/knowledge/out/$d/manifest.json'))['file'].get('size_bytes'))" 2>/dev/null)
  echo "$d: blocks_lines=$n input_size=$c"
done
echo "-- sample block sizes in f-08c367cb --"
head -1 data/knowledge/out/f-08c367cb/blocks.jsonl | python3 -c "import json,sys; r=json.loads(sys.stdin.read()); print({k:(len(v) if isinstance(v,str) else v) for k,v in r.items()})"

echo "== 7. ES discovery on s52 =="
docker ps --format '{{.Names}}' | grep -iE 'elastic|opensearch' || echo 'no ES container in docker ps'
ss -tln | grep -E ':(9200|9300) ' || echo 'no 9200/9300 listening'
curl -s -m 3 http://127.0.0.1:9200 2>/dev/null | head -c 300; echo
echo "-- ES vars in .env (names only) --"
grep -oE '^[A-Z_]*ES[A-Z_]*|^PCT_ES[A-Z_]*' "$APP/.env" 2>/dev/null || echo 'no ES vars in .env'
echo "-- ES vars in container env (names only) --"
docker inspect "$C" --format '{{range .Config.Env}}{{println .}}{{end}}' | grep -iE '^ES_|ELASTIC|OPENSEARCH' | sed 's/=.*/=***/' || echo 'no ES env in container'
echo "-- remote thesaurus ES API (the known 'ES' of this project) --"
grep -n 'thesaurus.eiis.iki.ac.ir\|elasticsearch\|ES_URL\|es_url' "$APP/backend/"*.py 2>/dev/null | head -20

echo "== 8. backups on disk (for orphan cross-check) =="
ls -la /home/saber/backups/ 2>/dev/null | tail -15

echo "ORPHAN-ES-AUDIT-DONE"

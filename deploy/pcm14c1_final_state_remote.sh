#!/bin/bash
# PCM-14C.1 final-state snapshot (read-only) for the report.
set -u
C=persian-corpus-toolkit-backend-1
echo "== container =="
docker ps --filter name=persian-corpus --format '{{.Names}} {{.Status}} {{.Image}}'
echo "== crawl projects =="
docker exec "$C" python3 -c "
import sqlite3
c = sqlite3.connect('/data/thesaurus.db')
for r in c.execute('SELECT id, name, status, page_count, updated_at FROM projects').fetchall():
    print(r)
"
echo "== knowledge tables row counts =="
docker exec "$C" python3 -c "
import sqlite3
c = sqlite3.connect('/data/thesaurus.db')
for t in ['knowledge_collections','knowledge_collection_documents','knowledge_index_builds','knowledge_jobs','knowledge_import_batches','knowledge_metadata_fields','knowledge_metadata_values']:
    print(t, c.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0])
"
echo "== integrity =="
docker exec "$C" python3 -c "
import sqlite3
c = sqlite3.connect('/data/thesaurus.db')
print(c.execute('PRAGMA integrity_check').fetchone())
"
echo "FINAL-STATE-DONE"

#!/bin/bash
# PCM-14C.1 read-only: manifest output-sha integrity + crawl fresh counter
set -u
cd /home/saber/saberprojects/persian-corpus-toolkit || exit 1
python3 /tmp/pcm14c1_manifest_check.py
echo "== crawl fresh counter =="
sqlite3 backend/thesaurus.db "SELECT COUNT(*) FROM project_pages WHERE project_id=2;"
sqlite3 backend/thesaurus.db "SELECT status, updated_at FROM projects WHERE id=2;"

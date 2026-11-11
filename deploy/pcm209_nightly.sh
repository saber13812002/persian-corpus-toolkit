#!/bin/bash
# PCM-20.9 — nightly pipeline run (run_nightly) on s52.
#
# What it does (read-only-safe, additive):
#   1. online DB backup (.backup) + PRAGMA integrity_check
#   2. po.run_nightly(db): for each ENABLED schedule, start the Full
#      Pipeline run (trigger_type=nightly); conflicting active runs are
#      skipped honestly (no double-run).
#   3. wait for the started pipeline jobs to reach a terminal status
#      (daemon job-workers die when this script exits, so we must poll
#      until they are done — deadline 6h, sleep 15s).
#   4. integrity_check again + print per-collection results.
#
# It is a plain cron target (no docker compose down -v, no DB writes
# other than the app's own pipeline rows). Cron entry example:
#   10 3 * * * /home/saber/saberprojects/persian-corpus-toolkit/deploy/pcm209_nightly.sh >> /home/saber/backups/pcm209-nightly.log 2>&1

set -e

SRC="${APP_DIR:-/home/saber/saberprojects/persian-corpus-toolkit}"
DB="$SRC/backend/thesaurus.db"
PY="$SRC/backend/.venv/bin/python"
DATA_DIR="${PCT_KNOWLEDGE_DATA_DIR:-$SRC/data/knowledge}"
BACKUP_DIR="${BACKUP_DIR:-/home/saber/backups}"
TS="$(date +%Y%m%d-%H%M%S)"

mkdir -p "$BACKUP_DIR"

echo "[pcm209-nightly] $TS — online backup"
sqlite3 "$DB" ".backup '$BACKUP_DIR/thesaurus-$TS.db'"
echo "[pcm209-nightly] integrity(before): $(sqlite3 "$DB" 'PRAGMA integrity_check;')"

echo "[pcm209-nightly] run_nightly"
( cd "$SRC/backend" && PCT_DB="$DB" PCT_KNOWLEDGE_DATA_DIR="$DATA_DIR" "$PY" -c "
import sqlite3
import time

import server  # noqa: F401  (env + app wiring, like the test suite)
import pipeline_orchestrator as po

DB = '$DB'
db = sqlite3.connect(DB, timeout=60)
db.row_factory = sqlite3.Row
try:
    results = po.run_nightly(db)

    # collect the started pipeline jobs (daemon workers die on exit)
    job_ids = []
    for r in results:
        if r['status'] == 'started':
            row = db.execute(
                'SELECT job_id FROM knowledge_pipeline_runs '
                'WHERE run_id=?', (r['detail'],)).fetchone()
            if row and row['job_id']:
                job_ids.append(row['job_id'])

    # wait for terminal status (deadline 6h, poll 15s)
    deadline = time.time() + 6 * 3600
    while job_ids and time.time() < deadline:
        rows = db.execute(
            'SELECT job_id, status FROM knowledge_jobs WHERE job_id IN (%s)'
            % ','.join('?' * len(job_ids)), job_ids).fetchall()
        if all(x['status'] in ('succeeded', 'failed', 'interrupted')
               for x in rows):
            break
        time.sleep(15)

    for r in results:
        print(' -', r['collection_id'], r['status'], r['detail'])
    if job_ids:
        for x in db.execute(
                'SELECT job_id, status, error FROM knowledge_jobs '
                'WHERE job_id IN (%s)' % ','.join('?' * len(job_ids)),
                job_ids):
            print('   job', x['job_id'], x['status'],
                  (x['error'] or '')[:200])
finally:
    db.close()
")

echo "[pcm209-nightly] integrity(after): $(sqlite3 "$DB" 'PRAGMA integrity_check;')"
echo "[pcm209-nightly] done"

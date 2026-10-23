#!/bin/bash
# PCM-03: safe SQLite backup + baseline (read-only against the live DB)
set -e
DB=~/saberprojects/persian-corpus-toolkit/backend/thesaurus.db
mkdir -p ~/backups
TS=$(date +%Y%m%d-%H%M%S)
BKP=/home/saber/backups/thesaurus-${TS}.db
sqlite3 "$DB" ".backup '$BKP'"
echo "BACKUP: $BKP"
sqlite3 "$BKP" "PRAGMA integrity_check;"
ls -la ~/backups/ | tail -3
echo ---BASELINE-TABLES---
sqlite3 "$DB" "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;"
echo ---BASELINE-COUNTS---
sqlite3 "$DB" "SELECT 'crawled_data', COUNT(*) FROM crawled_data; SELECT 'crawl_queue', COUNT(*) FROM crawl_queue;"
echo ---WAL-STATE---
ls -la ~/saberprojects/persian-corpus-toolkit/backend/ | grep -E '\.db'

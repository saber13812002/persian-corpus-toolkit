#!/bin/bash
# PCM-14C.1 read-only: inspect the one UNKNOWN file (5907102d) via container root
# (host user cannot read root:600 files). No mutations.
set -u
C=persian-corpus-toolkit-backend-1
echo "== magic bytes =="
docker exec "$C" sh -c 'head -c 4 /data-files/knowledge/files/5907102dc727/f-5907102d.docx | od -c | head -1'
echo "== docx text sample (read-only) =="
docker exec "$C" sh -c 'cd /tmp && python3 - <<PYEOF
import zipfile, re, sys
try:
    z = zipfile.ZipFile("/data-files/knowledge/files/5907102dc727/f-5907102d.docx")
    xml = z.read("word/document.xml").decode("utf-8", "replace")
    text = re.sub(r"<[^>]+>", " ", xml)
    text = re.sub(r"\s+", " ", text).strip()
    print("first 300 chars:", text[:300])
    print("chars total:", len(text))
except Exception as e:
    print("NOT-A-DOCX:", e)
PYEOF'
echo "== compare with known small fixture bfc01896 (text sample) =="
docker exec "$C" sh -c 'cd /tmp && python3 - <<PYEOF
import zipfile, re
try:
    z = zipfile.ZipFile("/data-files/knowledge/files/bfc01896a3de/f-bfc01896.docx")
    xml = z.read("word/document.xml").decode("utf-8", "replace")
    text = re.sub(r"<[^>]+>", " ", xml)
    text = re.sub(r"\s+", " ", text).strip()
    print("first 300 chars:", text[:300])
except Exception as e:
    print("ERR:", e)
PYEOF'
echo "UNKNOWN-FILE-CHECK-DONE"

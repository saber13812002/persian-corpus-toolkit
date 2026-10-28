#!/usr/bin/env python3
"""PCM-14C.1 read-only: verify manifest output shas against on-disk files."""
import json, hashlib, os, sys

base = sys.argv[1] if len(sys.argv) > 1 else "data/knowledge/out"
base = os.path.abspath(base)
print("== manifest output-sha integrity (read-only) ==")
for d in sorted(os.listdir(base)):
    m = os.path.join(base, d, "manifest.json")
    if not os.path.isfile(m):
        continue
    man = json.load(open(m, encoding="utf-8"))
    for name, o in man.get("outputs", {}).items():
        p = os.path.join(base, d, os.path.basename(o["path"]))
        if not os.path.isfile(p):
            print(f"{d}/{name}: MISSING on disk")
            continue
        h = hashlib.sha256(open(p, "rb").read()).hexdigest()
        print(f"{d}/{name}: {'OK' if h == o['sha256'] else 'MISMATCH!!'}")
print("MANIFEST-CHECK-DONE")

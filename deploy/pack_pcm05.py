"""Pack the repo (excl .git/.env/DB) into /tmp/pct-code-pcm05.tgz for deploy."""
import os
import tarfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = r"/tmp/pct-code-pcm05.tgz"

with tarfile.open(OUT, "w:gz") as tf:
    for dp, dn, fn in os.walk(ROOT):
        rel = os.path.relpath(dp, ROOT)
        parts = rel.split(os.sep)
        if ".git" in parts:
            dn[:] = []
            continue
        for f in fn:
            full = os.path.join(dp, f)
            arc = os.path.relpath(full, ROOT)
            if f == ".env" and len(parts) == 1:
                continue
            if f.startswith("thesaurus.db") and "backend" in parts:
                continue
            tf.add(full, arcname=arc)

print("OK", OUT, os.path.getsize(OUT))

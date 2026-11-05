# -*- coding: utf-8 -*-
"""Extract ae.CHUNK_DETAIL definition + API base from cached site bundle."""
import io, re

with io.open(".tmp_sitebundle.js", "r", encoding="utf-8") as f:
    js = f.read()

out = []
# Find CHUNK_DETAIL occurrences with context
for m in re.finditer(r"CHUNK_DETAIL", js):
    s = max(0, m.start() - 200)
    out.append("CTX: ..." + js[s:m.end() + 300].replace("\n", " ") + "...\n")

# Find definition of `ae` object: look for CHUNK_DETAIL: pattern
for m in re.finditer(r"CHUNK_DETAIL\s*[:=][^,}]{0,200}", js):
    out.append("DEF: " + m.group(0) + "\n")

# Find other API endpoints in the same const object (list of :`...` URLs)
for m in re.finditer(r"([A-Z_]+)\s*:\s*`(/[^`]{2,80})`", js):
    out.append("ROUTE: %s = %s\n" % (m.group(1), m.group(2)))

# Also find fetch base / api prefix like `/api/v1`
for m in re.finditer(r"\"(/api/[^\"]{2,60})\"", js):
    out.append("APISTR: " + m.group(1) + "\n")
for m in re.finditer(r"\"(/api/v1[^\"]{0,60})\"", js):
    out.append("APISTR: " + m.group(1) + "\n")

with io.open(".tmp_pcm204_findchunk_out.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(out[:80]))
print(len(out))

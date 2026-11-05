# -*- coding: utf-8 -*-
"""Find Nt (the JSON fetch helper) definition + base URL assembly in bundle."""
import io, re

with io.open(".tmp_sitebundle.js", "r", encoding="utf-8") as f:
    js = f.read()

out = []
# Nt definition candidates
for pat in [r"async function Nt\([^)]*\)\{.{0,400}",
            r"function Nt\([^)]*\)\{.{0,400}",
            r"const Nt=.{0,300}",
            r"Nt=async.{0,300}"]:
    for m in re.finditer(pat, js):
        out.append("Nt-DEF: " + m.group(0)[:420] + "\n")

# Where base /api/v1 is assembled: context around each occurrence
for m in re.finditer(r"/api/v1", js):
    s = max(0, m.start() - 250)
    out.append("BASE-CTX: ..." + js[s:m.end() + 250].replace("\n", " ") + "...\n")

with io.open(".tmp_pcm204_findnt_out.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(out[:40]))
print(len(out))

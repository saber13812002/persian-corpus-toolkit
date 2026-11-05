# -*- coding: utf-8 -*-
import re
body = open(".tmp_sitebundle.js", encoding="utf-8").read()
OUT = []
# find definition of On (async function On / function On / const On=)
for pat in (r'async function On\([^)]*\)\{.{0,600}',
            r'function On\([^)]*\)\{.{0,600}',
            r'On=async\([^)]*\)=>\{.{0,600}',
            r'On=\(?[^)]*\)?=>.{0,400}'):
    for m in re.finditer(pat, body):
        OUT.append("DEF(%s): %s" % (pat[:20], m.group(0)[:700].replace("\n", " ")))
# URL strings containing 'payload'
for m in re.finditer(r'.{80}payload.{120}', body):
    s = m.group(0).replace("\n", " ")
    if "encodeURIComponent" in s or "fetch" in s or "api" in s.lower():
        OUT.append("URL-CTX: %s" % s)
open(".tmp_pcm204_findon_out.txt", "w", encoding="utf-8").write("\n".join(OUT))
print(len(OUT))

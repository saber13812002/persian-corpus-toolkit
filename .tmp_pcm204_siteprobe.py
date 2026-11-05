# -*- coding: utf-8 -*-
"""Read-only probe of tasnim.hamtaa.org to find the real data endpoint and
check whether the SOURCE caps text at 2000 (gate 1.5). No auth, 1 request per URL.
Writes findings to .tmp_pcm204_siteprobe_out.txt
"""
import json, re, sys, urllib.request

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
OUT = []

def get(url, timeout=20):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()

html = get("https://tasnim.hamtaa.org/payload?file_id=tasnim&item_index=39137").decode("utf-8", "replace")
OUT.append("shell bytes: %d" % len(html))
js = sorted(set(re.findall(r'src="([^"]+\.js[^"]*)"', html)))
OUT.append("scripts: %s" % js)

# look for API hints in shell
for m in sorted(set(re.findall(r'["\']([a-zA-Z0-9_/.:-]*(?:api|payload|search|index)[a-zA-Z0-9_/.:-]*)["\']', html, re.I))):
    OUT.append("hint: %s" % m)

# try main bundle for API patterns
for j in js:
    if j.startswith("http"):
        u = j
    else:
        u = "https://tasnim.hamtaa.org/" + j.lstrip("/")
    try:
        body = get(u).decode("utf-8", "replace")
    except Exception as e:
        OUT.append("fetch fail %s: %s" % (u, e))
        continue
    OUT.append("bundle %s bytes=%d" % (j, len(body)))
    pats = sorted(set(re.findall(r'["\']([a-zA-Z0-9_/.?&=:-]*(?:payload|/api/|search\?|file_id)[a-zA-Z0-9_/.?&=:-]*)["\']', body)))
    for p in pats[:60]:
        OUT.append("  api: %s" % p)
    # common cap markers
    for marker in ("slice(0, 2000", "substring(0, 2000", ".slice(0,2000", "max_length", "maxLength", "truncate"):
        hits = body.count(marker)
        if hits:
            OUT.append("  MARKER %r x%d" % (marker, hits))
            for m in re.finditer(re.escape(marker), body):
                OUT.append("    ctx: ...%s..." % body[max(0, m.start()-80):m.end()+80].replace("\n", " "))

with open(".tmp_pcm204_siteprobe_out.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(OUT))
print("done")

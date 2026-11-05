# -*- coding: utf-8 -*-
import re, urllib.request
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
req = urllib.request.Request("https://tasnim.hamtaa.org/assets/index-Cve6St2q.js", headers=UA)
body = urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "replace")
OUT = []

# all 4-digit numeric literals near slice/substring/length caps
for m in re.finditer(r'(?:slice|substring|substr)\(\s*0\s*,\s*(\d+)\s*\)', body):
    OUT.append("slice(0,%s) ctx: ...%s..." % (m.group(1), body[max(0,m.start()-60):m.end()+60].replace("\n"," ")))

# contexts of /payload usage
for m in re.finditer(r'.{120}/payload.{160}', body):
    OUT.append("PAYLOAD-CTX: %s" % m.group(0).replace("\n"," "))
    if OUT.count("PAYLOAD-CTX") > 8: break

# contexts of /api/v1 usage (unique-ish)
seen = set()
for m in re.finditer(r'"/api/v1/[a-zA-Z0-9_/-]*"', body):
    if m.group(0) not in seen:
        seen.add(m.group(0))
OUT.append("api-routes: %s" % sorted(seen))

# search for the word 'payload' near 'text' or 'متن'
for m in re.finditer(r'.{80}(?:file_id|payload_id).{160}', body):
    OUT.append("FID-CTX: %s" % m.group(0).replace("\n"," "))
    if sum(1 for o in OUT if o.startswith("FID-CTX")) > 6: break

with open(".tmp_pcm204_siteprobe2_out.txt","w",encoding="utf-8") as f:
    f.write("\n".join(OUT))
print("done", len(OUT))

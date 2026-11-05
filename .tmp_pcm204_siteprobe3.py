# -*- coding: utf-8 -*-
import re, urllib.request
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
req = urllib.request.Request("https://tasnim.hamtaa.org/assets/index-Cve6St2q.js", headers=UA)
body = urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "replace")
OUT = []
# find the item-detail fetch (function Qg area) and all fetch/axios-like URL templates
for m in re.finditer(r'.{200}شناسهٔ آیتم.{300}', body):
    OUT.append("ITEMFN: %s" % m.group(0).replace("\n", " "))
for m in re.finditer(r'`[^`]*(?:items?|documents?|payloads?)/[^`]*`', body):
    OUT.append("TPL: %s" % m.group(0))
for m in re.finditer(r'["\x27]((?:/api/v1|/v1)/[a-z0-9_/${}.-]+)["\x27]', body):
    OUT.append("ROUTE: %s" % m.group(1))
routes = sorted(set(OUT))
with open(".tmp_pcm204_siteprobe3_out.txt","w",encoding="utf-8") as f:
    f.write("\n".join(routes))
print("done")

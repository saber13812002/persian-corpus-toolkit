# -*- coding: utf-8 -*-
import re, time, urllib.request
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
body = None
for i in range(4):
    try:
        req = urllib.request.Request("https://tasnim.hamtaa.org/assets/index-Cve6St2q.js", headers=UA)
        body = urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "replace")
        break
    except Exception as e:
        print("attempt %d failed: %s" % (i + 1, e))
        time.sleep(3)
if body is None:
    raise SystemExit("no bundle")
open(".tmp_sitebundle.js", "w", encoding="utf-8").write(body)
OUT = []
for m in re.finditer(r'.{200}شناسهٔ آیتم.{300}', body):
    OUT.append("ITEMFN: %s" % m.group(0).replace("\n", " "))
tpl = sorted(set(m.group(0) for m in re.finditer(r'`[^`]*(?:items?|documents?|payloads?)/[^`]*`', body)))
OUT += ["TPL: %s" % t for t in tpl]
rt = sorted(set(m.group(1) for m in re.finditer(r'["\x27]((?:/api/v1|/v1)/[a-z0-9_/${}.-]+)["\x27]', body)))
OUT += ["ROUTE: %s" % r for r in rt]
open(".tmp_pcm204_siteprobe3_out.txt", "w", encoding="utf-8").write("\n".join(OUT))
print("done", len(body), len(OUT))

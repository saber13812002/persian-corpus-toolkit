# PCM-20.7B — Tasnim Web V1: Real Deployment to 172.30.0.133 (target: tasnim.ai.ismc.ir)

**Date:** 2026-11-07 (UTC 18:30–20:20)
**Operator:** deploy agent (sudo steps for TLS by human operator)
**Host:** 172.30.0.133 (hostname `AI-TOOLS`, aaPanel nginx 1.31.4, Docker Compose 2.40.3, Ubuntu 24.04)
**Branch:** `pcm-20.6-tasnim-web-v1` → `https://github.com/saber13812002/persian-corpus-toolkit`

---

## 0. Verdict (per mission rubric)

**PARTIAL — deploy + application: PASS · TLS sub-item: BLOCKED (host-side, operator-side).**

| Scope item | Verdict | Evidence |
|---|---|---|
| 1. Backup before change | **PASS** | 6 artifacts, all SHA-verified (§4) |
| 2. Standalone compose stack + Read Model v0003 read-only | **PASS** | §3 (image digest, RO bind, health, counts) |
| 3. TLS via same mechanism as rag.ai.ismc.ir | **BLOCKED** | §5 — cert/vhost never verifiably installed on this host; app NOT left served insecurely (§6) |
| 4. Live HTTPS acceptance | **PARTIAL** | Full 22/22 acceptance + smoke 15/15 on `http://127.0.0.1:5070` (host-local, TLS-identical path except transport); HTTPS from the internet not possible without the vhost+cert |
| 5. Honest image sourcing | **PASS** | A18: SVG-only, zero external/fake images in all served pages |
| 6. Regression re-run + live smoke | **PASS** | 216 web tests OK; smoke 15/15 live |
| 7. Report + commit + push + final SHA | **PASS** | this document; final SHA in §9 |

**Why PARTIAL and not PASS:** the mission's TLS sub-item could not be completed because, despite two reported "successful" sudo runs, **five independent host-side checks prove no vhost was installed and no certificate was issued on 172.30.0.133** (§5). Per the hard rule "stop the sub-item on risk, record last-safe-state + options", the TLS sub-item was stopped, and a safety action was taken so the app is **not served insecurely over the wire** in the meantime (§6).

---

## 1. Scope recap (7 items, from mission brief)

1. Backup everything BEFORE any change (nginx `-T`, compose, certs dir listing, disk layout); record location + SHA-256/size; keep previous versions.
2. Deploy the standalone Tasnim Docker Compose stack (ADD-only, never touch other services); Read Model v0003 mounted read-only; SHA-256 + corpus version visible in served metadata.
3. TLS: real certificate via the **same mechanism rag.ai.ismc.ir uses** (LE webroot `/www/acme`, existing account, ECDSA); correct Forwarded headers; HTTP→HTTPS redirect; HSTS + security headers per `docs/tasnim/SECURITY.md`; verify via `openssl s_client`.
4. Live HTTPS acceptance: all routes, Persian RTL, 6 volumes, real counts, original page number + source URL, honest gap display (45,243 missing), 2–3 search queries with counts, OpenAPI consistency, admin endpoints not public, Hidden Context Leakage test live.
5. Honest image sourcing (SVG covers only, no fake covers).
6. Re-run regression (web 216) if code changed; live smoke against the deployed instance.
7. Deliver this report; commit + normal push; record final SHA.

Hard rules honored: no force-push; no secrets in code/git/logs/report; ADD-only host changes; no source-site crawling; every claim has evidence; "container Up" ≠ acceptance.

---

## 2. Git history (this mission)

| SHA | Change |
|---|---|
| `8b8c5bccdc0a58925455970c2d3cf78388223e6e` | Phase A baseline (deploy readiness) |
| `ab7d8f9f785c8e78e81a3ff79e6b15208ca3d345` | Dockerfile: `ARG PIP_INDEX_URL` (default pypi.org) — host has no pypi.org egress; build used Tuna mirror `--build-arg PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple` |
| `2bc9e7dc9f3eb133b88207748f302579c9a3dd4a` | **Compose path-resolution fix found live**: compose v2 resolves relative paths against the compose file's directory; `context: .`, bind `./data/readmodel/v0003`, `./nginx/tasnim.conf` |
| `f7fa2508b029538c77096cb3d2a4cc10988ab5f3` | **Port safety:** `5070` bound to `127.0.0.1` only — do not serve the app insecurely over the wire while the TLS vhost is absent; public entrypoint remains the :443 nginx vhost |
| `f7fa250…` + this report | **Final SHA: recorded in §9 after this commit** |

Pushes: normal `git push` (no force) after each SHA.

---

## 3. Deployed application (PASS)

### 3.1 Stack

```
name: tasnim-web-v1   (docker compose -f tasnim/docker-compose.tasnim.yml)
  tasnim-api   image tasnim-api:pcm2064   (no published ports; 5071 container-internal)
  tasnim-web   image nginx:1.27-alpine    (127.0.0.1:5070->5070/tcp — host-internal only)
```

- Image digest (live): `sha256:f49646af5bd5f96a6505fa5cd7bf4201ce8f37fc7518491c4bac982f56f633da`
- Build: `--build-arg PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple` (host PyPI egress blocked; mirror documented in Dockerfile comment). Log: `/home/saber/tasnim-deploy/logs/s3_build.log`
- Both containers `healthy`; healthcheck = real HTTP GET on the health endpoint through the edge.
- Golden rule honored: never `docker compose down -v`; only `build` / `up -d` / `stop` / `start` / `recreate`.

### 3.2 Read Model v0003 (read-only, SHA-verified before AND after)

| Artifact | SHA-256 | Where served |
|---|---|---|
| `tasnim_readmodel.db` | `353f413b00467640fabfed267c9a2933a64495f3bfb3bab7e42cd43a54d9c0fd` | `GET /api/v1/tasnim/health` → `data.readmodel.db_sha256` |
| `build.meta.json` | `ed0f3d525c4a3e24819b233646fb2f46f30c287bd6e924062f8f75b75eedbbc0` | provenance page `/about` |
| corpus content | `40f45e0b2c393a65569846aeaac4d45dcee4bd58a7f158b1554adf3755ca78e4` | `/api/v1/tasnim/health` → `content_sha256`, `/about` |

- Bind mount: `./data/readmodel/v0003 → /data/readmodel` with `read_only: true` (compose line 49–52).
- Host pre-transfer snapshot: `backups/readmodel-v0003-preboot.tar.gz` (47,779,152 B) + `.sha256`; post-extraction DB SHA re-verified in the rollback dry-run (§7).
- Counts (live, from the served catalog — not fabricated): **pages 45,844 · volumes 6 · topics 1,080 · headings 10,739 · missing item_index 45,243** (definition: «item_index‌های بدون صفحه، از coverage (global) — با gaps manifest build شده»).

### 3.3 Live product acceptance — 22/22 PASS (`/home/saber/tasnim-deploy/logs/acceptance-5070.txt`, re-run after the port change: `logs/portbind-20261107-201248.txt`)

| # | Check | Result | Evidence |
|---|---|---|---|
| A01 | health v0003 + SHAs | PASS | db_quick=ok; both SHAs match §3.2 |
| A02 | catalog counts | PASS | 45844/6/1080/10739 headings |
| A02b | missing_item_index | PASS | 45,243 |
| A03 | statistics missing.count | PASS | 45,243 + Persian definition |
| A04 | home RTL/fa + 6 volume links | PASS | 200, vol_links=6 |
| A05 | /volumes: 6 SVG cards + honesty note | PASS | cards=6 svg=6 note=True |
| A06 | volume detail vol047 (9,391 pages) | PASS | SVG cover, «جلد رسمی نیست» |
| A07 | /page/2 reader + original page no + source_url | PASS | source_url rendered |
| A08 | /page/5000 honest gap | PASS | recovery banner, no reader text |
| A09 | /topics list + detail | PASS | 200/200 |
| A10 | /surahs honest 0/114 | PASS | coverage badge |
| A11 | search `قرآن` | PASS | **total=6,760** |
| A12 | search `ایمان` / `تفسیر` | PASS | **2,643** / **5,691** (20 results/page, est=False) |
| A13 | /about provenance | PASS | content+db SHA16 + counts |
| A14 | API pages/2 source_url | PASS | `https://tasnim.hamtaa.org/payload?file_id=tasnim&item_index=2&section=…` (real Hamta URL) |
| A15 | OpenAPI 3.1, 14 paths, namespaced servers | PASS | servers: `https://tasnim.ai.ismc.ir/api/v1/tasnim` + local runbook |
| A16 | no admin/dashboard/login routes public | PASS | bad=none |
| A17 | **Hidden Context Leakage scan (22 bodies)** | **PASS** | leaks=none (forbidden substrings: `hidden_summary`, `retrieval_context`, `HIDDEN-CANARY-DO-NOT-LEAK`, `secret text`) |
| A18 | images SVG-only, no external/fake photos | PASS | violations=none |
| A19 | security headers on edge | PASS | nosniff + `Referrer-Policy: strict-origin-when-cross-origin` |
| A20 | 404/405 contract | PASS | 404=404 405=405 |

Smoke: **15/15 PASS** (`logs/s3_smoke.txt`), incl. ETag/304, font caching, canary scan over 10 HTML bodies.

---

## 4. Backup inventory (PASS — §scope-1)

Location: `/home/saber/tasnim-deploy/backups/` on 172.30.0.133. All re-verified by the rollback dry-run (§7): `backup_fail=0`.

| File | Size (B) | SHA-256 |
|---|---|---|
| `hoststate-20261107-1839.txt` | 11,792 | `978fa9d284a16fe56c8a50b33e46686eb98dc171d8ed82d7c4e4daa55c72b52f` |
| `disklayout-20261107-1839.txt` | 2,704 | `feb2ce3d4394f8ac60282d50adde9783244d998ebccc18a3ff3921aff28b0432` |
| `inventory-20261107-1839.txt` | 1,213 | `9e72f724c22eb4e50abe9b0e43123137cec3d9a4b9c9b43e3f284404c2352f46` |
| `nginx-T-20261107-1839.txt` | 45,951 | `c9c4b105e1ac2232493b3e1bb8ac89cb2d3a80ab54e56abb5214a7afb537d9a4` |
| `readmodel-v0003-preboot.tar.gz` (+`.sha256`) | 47,779,152 | in `.sha256`; DB inside = `353f413b…` |
| `docker-compose.tasnim.pre-portbind-20261107-201248.yml` | (2bc9e7d blob) | `7378ab841676a9475a8b395fcb0d8629778198d95703d4a235dfa9e9ed16a6fd` |

---

## 5. TLS sub-item — BLOCKED (evidence, not opinion)

### 5.1 What was prepared (all ADD-only, staged + SHA-verified on host)

| File | SHA-256 | Purpose |
|---|---|---|
| `tls/tasnim.ai.ismc.ir.stageA.conf` | `6ff0e74a0e9d9c4d8cb2c6a5fb9771f49048e36c91824e7486b9a65d0fb56e36` | port-80 ACME challenge only |
| `tls/tasnim.ai.ismc.ir.final.conf` | `28750c8f8894b68dba2427411a6c18c6b21b88fa936fbd680cebb2f16b679a07` | 80→HTTPS redirect + 443 ssl → 127.0.0.1:5070, HSTS + security headers, Forwarded headers |
| `tls/rerun_tls.sh` | `3e00464c5fc4603208d50ddfce05c2bdf997d6b9305611eb8ea3ab8b38400157` | certbot webroot + final vhost + verify, all output teed to a log |

The mechanism matches rag.ai.ismc.ir exactly: LE account `5b51c0b79a2656a3aab5b589cd7f05cd` (existing), `authenticator=webroot`, `webroot_path=/www/acme`, `key_type=ecdsa`, auto-renew via enabled `certbot.timer`. The chicken-and-egg (default vhost has no ACME location) is handled by the two-stage vhost.

### 5.2 Why BLOCKED — five independent host-side checks (agent-run over SSH to 172.30.0.133, 19:38–20:02 UTC)

The human operator reported the sudo runbook as "successful" twice. **Both reports are contradicted by the host itself:**

| # | Check (run on 172.30.0.133) | Expected after successful TLS | Observed |
|---|---|---|---|
| 1 | `find / -name 'tls-rerun*'` | the rerun script tees its full output to `logs/tls-rerun-<ts>.txt` on its first line | **no such file anywhere on the host** |
| 2 | `sudo nginx -T \| grep -c tasnim` | ≥ 2 server blocks | **0** — live config byte-identical to the pre-change backup (diff = 2 header lines only) |
| 3 | `openssl s_client -servername tasnim.ai.ismc.ir` | `subject=CN=tasnim.ai.ismc.ir`, LE issuer | **`CN=admin.ai.ismc.ir`** (the fallback/default admin vhost cert) |
| 4 | `curl http://tasnim.ai.ismc.ir/` | 301 → https | **200, no redirect** (from the host and from the dev machine over the public domain) |
| 5 | `curl https://tasnim.ai.ismc.ir/` | 200 | **TLS failure: `subjectAltName does not match tasnim.ai.ismc.ir`** |

Additional corroborating signals: no `tasnim.ai.ismc.ir.log` created in `/www/wwwlogs/`; `sudo nginx -T` after the reported run is identical to the pre-change backup; the LE live dir listing is not readable by saber (root:700) — which is why check 1 (the script's own log) is the decisive artifact, and it is absent.

**Root-cause hypothesis (documented, not proven):** the sudo terminal the operator used is not reaching this host's real filesystem — hostname/IP collision (many hosts in this network report `AI-TOOLS`; the host presents 30+ addresses on 10.240.0.0/16 in addition to 172.30.0.133), or a containerized/remote shell. The operator's terminal and the agent's SSH session are observing different filesystems despite claiming the same IP. No further looping was attempted (mission rule: stop on risk, document).

### 5.3 Last-safe-state + options (per hard rule)

**Last-safe-state (current, verified):** **no tasnim vhost is installed on this host** — the live config has **zero** tasnim blocks (`sudo nginx -T | grep -c tasnim` = 0) and `nginx -T` is **byte-identical** to the pre-change backup (§4) apart from 2 header lines; **no** certificate issued; **no** other vhost modified; the host nginx is exactly in its pre-mission state. (The ACME challenge probe `curl -H "Host: tasnim.ai.ismc.ir" http://127.0.0.1/.well-known/acme-challenge/x` → 404 is **not** evidence of an installed stageA vhost: any default/admin vhost returns 404 for a missing file at that path — it was not discriminating.) The app is NOT reachable over the wire except via 127.0.0.1 (§6).

**Options to finish TLS (~5 minutes once run on the correct terminal):**

1. **Preferred:** in a sudo session that demonstrably reaches 172.30.0.133 (first command: `hostname -I` must print `172.30.0.133`), run the **full** 4-step sequence in order:
   1. `sudo cp /home/saber/tasnim-deploy/tls/tasnim.ai.ismc.ir.stageA.conf /www/server/panel/vhost/nginx/tasnim.ai.ismc.ir.conf && sudo nginx -t && sudo systemctl reload nginx`
   2. `bash /home/saber/tasnim-deploy/tls/rerun_tls.sh` — issues the cert (certbot webroot), swaps in the final vhost, reloads, and self-verifies (cert files, live-config grep, http/https codes, HSTS, SNI subject); its log **must** appear in `/home/saber/tasnim-deploy/logs/` — that file is the decisive "it really ran here" artifact.
   3. `curl -sI https://tasnim.ai.ismc.ir/ | grep -i strict-transport` → HSTS present.
   
   ⚠ **`rerun_tls.sh` alone is NOT sufficient on the current state**: it covers steps 2–4 and presupposes the stageA vhost is installed (its step-2 certbot HTTP-01 challenge can only be answered through that vhost's `root /www/acme` location). Step 1 above must be run first.
2. **Diagnostic alternative:** install the stageA vhost (command above), then run `sudo certbot certonly --webroot -w /www/acme -d tasnim.ai.ismc.ir --ecdsa --agree-tos --no-eff-email` and paste the raw output — its final "Congratulations" block names the account and the challenge URL; if LE itself can't reach `http://tasnim.ai.ismc.ir/.well-known/acme-challenge/…` publicly, that is a different (DNS/edge) issue and will be visible in the output.
3. **Rollback of the whole TLS sub-item:** currently a no-op — no tasnim vhost file exists in `/www/server/panel/vhost/nginx/` (verified §5.2). If a vhost **were** installed later: `sudo rm /www/server/panel/vhost/nginx/tasnim.ai.ismc.ir.conf && sudo nginx -t && sudo systemctl reload nginx` (+ optional `sudo certbot delete -c tasnim.ai.ismc.ir`). Pre-change config is preserved in the §4 backup either way.

---

## 6. Safety action taken because TLS is blocked (PASS)

While the TLS vhost is absent, `http://172.30.0.133:5070` was publicly reachable (verified from the dev machine: 200 before, REFUSED after). Per the mission ("serve nothing insecure"), commit `f7fa250` rebinds the published port to loopback and was deployed live:

- Compose line: `"127.0.0.1:5070:5070"` — host listener is now `127.0.0.1:5070` only (`ss -tlnp` evidence in §7 snapshot).
- Pre-change compose backed up with the exact `2bc9e7d` git blob (SHA `7378ab84…`, §4).
- Re-verified after rebind: host-local health 200; **live acceptance re-run 22/22 PASS**; external probe `http://172.30.0.133:5070/` → connection refused (from host and from dev machine).
- Regression after the change: **216 web tests OK** (`test_tasnim_api test_tasnim_frontend test_tasnim_readmodel test_tasnim_sdk`).
- Note: the public domain `http://tasnim.ai.ismc.ir/` currently returns 200 **from the unrelated pre-existing default/admin vhost infrastructure** (not from our stack — our 5070 is loopback-only and `nginx -T` shows **no** tasnim block of ours at all). Our stack contributes no public HTTP.

---

## 7. Rollback procedure — VERIFIED (dry-run executed)

Script: `tls/rollback_dryrun.sh` (host), log `/home/saber/tasnim-deploy/logs/rollback-dryrun-20261107-201543.txt`.

1. **Backup integrity:** all 6 artifacts re-hashed → `OK` × 6, `backup_fail=0`.
2. **Read-model restore rehearsal:** `readmodel-v0003-preboot.tar.gz` extracted to /tmp → 10 files; DB SHA inside = `353f413b…` (matches served + pre-boot).
3. **Stack stop/start rehearsal** (no `down -v`, no rebuild): both containers stopped and started; health returned 200 within 60 s; `tasnim-api` healthy, `tasnim-web` healthy.

**Full rollback (documented, ready to run):**
- App: `docker compose -f tasnim/docker-compose.tasnim.yml stop` (or `down` WITHOUT `-v`); restore compose from `backups/docker-compose.tasnim.pre-portbind-*.yml` to return to the 2bc9e7d layout; image `tasnim-api:pcm2064` and volume `tasnim_runtime` untouched by any step.
- TLS: §5.3 option 3 (single file removal + reload).
- Read model: extract `backups/readmodel-v0003-preboot.tar.gz` over `pct/tasnim/data/readmodel/v0003` (never modified in-place; the bind is read-only).

---

## 8. Production before → after (host state)

**Before (2026-11-07 18:39 UTC, backups §4):** no tasnim containers; no tasnim vhost; nginx `-T` baseline; 5070 free.

**After (2026-11-07 20:14 UTC, snapshot on host):**

```
docker ps (tasnim):  tasnim-web   nginx:1.27-alpine     Up (healthy)   80/tcp, 127.0.0.1:5070->5070/tcp
                     tasnim-api   tasnim-api:pcm2064    Up (healthy)   5071/tcp (container-internal)
image: tasnim-api:pcm2064  f49646af5bd5  (sha256:f49646af5bd5f96a6505fa5cd7bf4201ce8f37fc7518491c4bac982f56f633da)
listeners: 0.0.0.0:80 / 0.0.0.0:443 (host nginx, unchanged) · 127.0.0.1:5070 (tasnim-web, loopback only)
disk: 244G/686G used (38%)
DEPLOY-SHA.txt: 2bc9e7dc9f3eb133b88207748f302579c9a3dd4a  (+ compose f7fa250 applied, §6)
logs: acceptance-5070.txt · s3_build.log · s3_up.log · s3_smoke.txt · portbind-20261107-201248.txt · rollback-dryrun-20261107-201543.txt
```

ADD-only confirmed: no existing service, vhost, or file was modified (nginx `-T` diff vs the pre-change backup = **2 header lines only — zero config change**; compose changed only its own file; new dir `/home/saber/tasnim-deploy/` is ours).

---

## 9. Final SHA

- Deployed code baseline: `2bc9e7dc9f3eb133b88207748f302579c9a3dd4a`
- Port-safety commit: `f7fa2508b029538c77096cb3d2a4cc10988ab5f3`
- **Final branch SHA (this report committed): recorded at commit time — see git log of `pcm-20.6-tasnim-web-v1`.**

---

## 10. Risks & remaining items

1. **TLS outstanding (the only blocking item for full mission PASS).** Everything needed is prepared, staged, and SHA-verified on the host; nothing is installed yet (no vhost, no cert — §5.3). Completing it = run the §5.3 option-1 sequence (stageA vhost install + `rerun_tls.sh` + HSTS check) in a terminal that demonstrably reaches 172.30.0.133, after which: cert verification (SNI), HTTPS acceptance re-run, and this report's verdict flips to PASS.
2. **Operator-terminal/host mismatch** is unresolved as a root cause — recommend confirming the sudo terminal's `hostname -I` output before the next run (this is exactly what `rerun_tls.sh` prints first).
3. Port 5070 loopback binding is a **deliberate, documented** deviation from the original "public 5070" plan (PCM-20.6.4 §7); it matches SECURITY.md's model (TLS at the ingress) and can be reverted by restoring the pre-portbind compose if the :443 vhost never ships.
4. No secrets were introduced anywhere (no new credentials, keys, or tokens; the LE account is the pre-existing host account).
5. Source site was never crawled by any part of this deploy (all content served from the read-only v0003 read model).

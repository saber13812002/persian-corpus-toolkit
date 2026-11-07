# PCM-20.7A — Deployment Plan (Phase B Preparation)

**Mission:** PCM-20.7A — Git Integration & Production Readiness
**Date:** 2026-11-07 (Tehran)
**Status:** PLAN — no deployment performed in Phase A (read-only infra probe only).
**Target:** `tasnim.ai.ismc.ir` → `172.30.0.133`, Docker Compose stack `tasnim-web-v1`.

---

## 1. Phase A readiness findings (what the probe proved)

| Check | Result |
|---|---|
| `172.30.0.133` (Tasnim deploy host) reachable | ✅ ping OK; TCP 22/80/443 OPEN |
| `:5070` public (edge) | CLOSED — stack not deployed yet |
| `:5071` internal (API) | CLOSED — expected (internal-only, no host publish) |
| `172.30.0.113` (AI-TOOLS) | ❌ unreachable from this host |
| `172.20.1.52` (s52) | ❌ unreachable from this host (consistent with PCM-18/20.6 reports) |
| DNS `tasnim.ai.ismc.ir` | resolves to 172.30.0.133 (internal split-horizon view; DEPLOYMENT.md cites external edge 185.213.10.25) |
| DNS `rag.ai.ismc.ir` | resolves to 172.30.0.133 |
| HTTPS `tasnim.ai.ismc.ir` | TLS trust failure — default cert (CN=admin.ai.ismc.ir), no valid `tasnim.*` cert yet → **Phase B must install a real cert** |
| HTTPS `rag.ai.ismc.ir` | HTTP 200 (internal/self-signed cert) — confirms 133 hosts RAG already |

**Blockers needing human decision before Phase B:**
1. **Docker not available on the dev host** — all image build/run must happen on
   172.30.0.133 (owner executes steps below, or grants an executor).
2. **Ingress/edge ownership** — 133 already fronts `rag.ai.ismc.ir`; adding
   `tasnim.ai.ismc.ir` needs the edge owner's approval (Kong/Tyk/cloudflared per
   `docs/tasnim/DEPLOYMENT.md`).
3. **TLS certificate** for `tasnim.ai.ismc.ir` (currently default admin cert).
4. **GitLab remote** absence (see GIT-RECONCILIATION §3) — decide second remote.

## 2. What ships (artifacts, all committed on the branch)

| Artifact | Path | Notes |
|---|---|---|
| API image | `tasnim/Dockerfile` | python:3.12-slim, Flask==3.1.3, non-root uid 10001, HEALTHCHECK, `EXPOSE 5071` |
| Compose stack | `tasnim/docker-compose.tasnim.yml` | project `tasnim-web-v1`; `tasnim-api` (no ports, RO bind `./tasnim/data/readmodel/v0003` → `/data/readmodel`, named vol `tasnim_runtime:/var/tasnim`) + `tasnim-web` (nginx:1.27-alpine, `5070:5070`, `depends_on: service_healthy`) |
| Read model v0003 | `tasnim/data/readmodel/v0003/` | gitignored — **must be copied to the host separately** (260 MB DB + files) |
| Nginx edge conf | `tasnim/nginx/tasnim.conf` | 5070 → proxy to `tasnim-api:5071` |
| Docs | `docs/tasnim/{DEPLOYMENT,DOCKER,OPS-RUNBOOK,SECURITY,BACKUP-RESTORE}.md` | operator references |

## 3. Phase B step-by-step (on 172.30.0.133)

Pre-conditions: 496 green tests + smoke 15/15 + E2E 12/12 already re-verified
in Phase A (`PCM-20.7A-TEST-REPORT.md`); secret scan clean.

1. **Snapshot the pre-deploy host state** (read-only baseline):
   ```bash
   date -u > /home/tasnim/backups/pre-deploy-$(date +%Y%m%d-%H%M).txt
   ss -ltnp | grep -E '5070|5071' >> pre-deploy-*.txt
   docker ps -a >> pre-deploy-*.txt
   ```
2. **Copy code** (branch tip) to `/home/tasnim/pct/` (copy, not git clone —
   mirrors s52 convention): `git archive d7cdbb9 | tar -x -C /home/tasnim/pct`.
3. **Copy read model v0003** to `/home/tasnim/pct/tasnim/data/readmodel/v0003/`,
   then **verify integrity** before boot:
   ```bash
   sha256sum tasnim/data/readmodel/v0003/tasnim_readmodel.db
   # expected: 353f413b00467640fabfed267c9a2933a64495f3bfb3bab7e42cd43a54d9c0fd
   ```
4. **Build & start:**
   ```bash
   cd /home/tasnim/pct
   docker compose -f tasnim/docker-compose.tasnim.yml build tasnim-api
   docker compose -f tasnim/docker-compose.tasnim.yml up -d
   ```
   (Never `down -v` — golden rule, `OPS-RUNBOOK.md`.)
5. **Health-wait + smoke** (same 15 checks as Phase A):
   ```bash
   python -m tasnim.e2e.smoke --base http://127.0.0.1:5070
   curl -fsS http://127.0.0.1:5070/api/v1/tasnim/health
   ```
   Required: `status=ok`, `db_quick_check=ok`, version v0003, content sha
   `40f45e0b2c…8e4`.
6. **Edge/ingress** (owner): add `tasnim.ai.ismc.ir` route → `127.0.0.1:5070`
   with the real TLS cert; verify `curl -fsS https://tasnim.ai.ismc.ir/api/v1/tasnim/health`.
7. **Firewall contract:** 5070 = public (via edge/ingress only), 5071 = internal
   (compose network only, no host publish — already enforced by the compose file).
8. **Backup snapshot** (see §4) + final `docker ps`, port, and count checks
   (pages=45,844 / topics=1,080 / volumes=6 via `/statistics` + `/catalog`).

## 4. BACKUP plan (executable, pre-deploy & steady-state)

**Golden rule: no change without backup.**

### 4.1 Pre-deploy (Phase B, before first `up`)
```bash
TS=$(date +%Y%m%d-%H%M)
mkdir -p /home/tasnim/backups
# (a) host state snapshot
{ date -u; ss -ltnp; docker ps -a; df -h; } > /home/tasnim/backups/hoststate-$TS.txt
# (b) read model archive (the only large artifact)
tar czf /home/tasnim/backups/readmodel-v0003-$TS.tar.gz \
  -C /home/tasnim/pct tasnim/data/readmodel/v0003
sha256sum /home/tasnim/backups/readmodel-v0003-$TS.tar.gz \
  > /home/tasnim/backups/readmodel-v0003-$TS.tar.gz.sha256
# (c) rate-limit DB (writable volume — tiny, but reset-able)
docker compose -f tasnim/docker-compose.tasnim.yml cp \
  tasnim-api:/var/tasnim/ratelimit.db /home/tasnim/backups/ratelimit-$TS.db 2>/dev/null || true
# (d) deploy dir snapshot (code, without read model)
tar czf /home/tasnim/backups/pct-deploy-$TS.tar.gz \
  -C /home/tasnim --exclude=pct/tasnim/data --exclude=pct/.git pct
```

### 4.2 Steady-state (weekly, per OPS-RUNBOOK)
- Re-run (b) + (c) above on a schedule; keep 4 generations; verify each with
  `sha256sum -c` and a `sqlite3 … PRAGMA integrity_check` on the rate DB.
- Read model is **immutable** per version; v0004 replaces v0003 by directory
  swap (never in-place overwrite), so the previous version directory remains
  the natural rollback artifact.

## 5. ROLLBACK plan (executable)

**RTO target: ≤ 5 min for app-level rollback; ≤ 15 min for read-model rollback.**

### 5.1 App rollback (bad deploy / broken image)
```bash
cd /home/tasnim/pct
# (a) stop current stack (NO -v: keep tasnim_runtime volume & data)
docker compose -f tasnim/docker-compose.tasnim.yml stop
# (b) restore previous deploy snapshot (the one from §4.1d, taken before this deploy)
tar xzf /home/tasnim/backups/pct-deploy-<PREV_TS>.tar.gz -C /home/tasnim
# (c) restore read model if it was part of the change
tar xzf /home/tasnim/backups/readmodel-v0003-<PREV_TS>.tar.gz -C /home/tasnim/pct
sha256sum -c /home/tasnim/backups/readmodel-v0003-<PREV_TS>.tar.gz.sha256
# (d) rebuild & up
docker compose -f tasnim/docker-compose.tasnim.yml build tasnim-api
docker compose -f tasnim/docker-compose.tasnim.yml up -d
# (e) verify: health + 15-check smoke + page counts (45,844 / 1,080 / 6)
python -m tasnim.e2e.smoke --base http://127.0.0.1:5070
```

### 5.2 Read-model rollback (v0004 → v0003)
```bash
# 1) keep v0004 dir untouched (evidence), swap the bind source
cd /home/tasnim/pct/tasnim/data/readmodel
mv v0004 v0004.disabled   # never delete
ln -sfn v0003 current     # compose mounts the version dir explicitly —
#    edit compose `volumes:` to point at v0003 (or re-point the explicit path)
docker compose -f tasnim/docker-compose.tasnim.yml up -d tasnim-api
# 2) verify: /catalog must show version v0003 + content sha 40f45e0b…
```

### 5.3 Edge/ingress rollback
Remove (or disable) the `tasnim.ai.ismc.ir` route in Kong/Tyk and keep the
previous DNS state; expected time-to-restore ≈ 2 min (per DEPLOYMENT.md). The
internal 5070/5071 stack is unaffected.

### 5.4 Data-loss guardrails
- **Never** `docker compose down -v` (destroys `tasnim_runtime`).
- **Never** write into `tasnim/data/readmodel/*` (read-only bind).
- Rate-limit DB is disposable (reset = delete `ratelimit.db` + restart api).
- If any step shows page/topic/volume counts deviating from 45,844 / 1,080 / 6
  → STOP, do not proceed, capture logs, rollback §5.1.

## 6. Follow-ups (not blocking Phase B start, needed for go-live)

| # | Item | Owner |
|---|---|---|
| 1 | Real TLS cert for `tasnim.ai.ismc.ir` (replace default admin cert) | infra/edge owner |
| 2 | Ingress route approval on 133 (Kong/Tyk/cloudflared) | edge owner |
| 3 | Confirm 172.30.0.113 (AI-TOOLS) & 172.20.1.52 (s52) reachability from 133 (unreachable from dev host) | network owner |
| 4 | Decide internal GitLab mirror for this repo (none configured) | repo owner |
| 5 | `_aidump` uncommitted changes (3 files) — commit or revert | repo owner |

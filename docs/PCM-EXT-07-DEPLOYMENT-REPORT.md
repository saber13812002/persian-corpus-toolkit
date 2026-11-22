# PCM-EXT-07 — Deployment Report (KHAMENEI CRAWLER STAGING DEPLOYMENT)

Date: 2026-11-21 (UTC) · Operator: Zoo (Senior SWE + DevOps + E2E Acceptance)
Mission: move the PCM-EXT-06 year-based Khamenei crawler (Python + Chrome extension) to
**Staging**, prove real operation, and deliver a human-acceptance scenario.
Rule of the mission: **هیچ نتیجه‌ای را بدون اجرای واقعی PASS اعلام نکن** — every PASS below
carries its real command + real output (or its evidence file).

Companion reports (M8):
- `PCM-EXT-07-CRAWLER-E2E-ACCEPTANCE.md` (M4)
- `PCM-EXT-07-EXTENSION-ACCEPTANCE.md` (M5)
- `PCM-EXT-07-HUMAN-TEST-GUIDE.md` (M6 + "WHAT SHOULD THE PROJECT OWNER TEST NOW?")

---

## M1 — Git audit (COMPLETE)

| Item | Value | Evidence |
|---|---|---|
| Branch | `pcm-20.9-knowledge-studio-factory` | `git branch --show-current` |
| Remote | GitHub `saber13812002/persian-corpus-toolkit` | `git remote -v` |
| Base commit (PCM-25 DC#5) | `ae94ede` | pre-session HEAD |
| New commits | **10106e9** (PCM-EXT-06, 7 files, +716/−116) · **8708163** (PCM-EXT-08, 11 files, +514/−35) · **6f7f2d2** (hygiene/.gitignore, 1 file, +6) | `git log --oneline ae94ede..6f7f2d2` |
| Pushed | `ae94ede..6f7f2d2` → origin | `git push` output |
| Working tree | clean | `git status --porcelain` = empty |
| Secrets in git | none — `.env`, `*.db`, probes all gitignored; no `*.db.bak` tracked | `git ls-files` audit |
| Tests at commit time | backend 232/232 OK (11 modules) + node 71/9/8/8 + corpus 13/13 | full regression re-run this session |

Hunk-level split of the mixed files (`extension/background.js`, `extension/popup.js`,
`AGENTS.md`) was done with a Python patch splitter (`git apply --cached --recount`) so that
commit 10106e9 contains **only** PCM-EXT-06 and 8708163 **only** PCM-EXT-08 (verified:
staged EXT-06 diff had 0 hash-mode mentions, 18 year-walk mentions).

**Code identity for staging:** commit **`6f7f2d2`**
(HEAD of branch = EXT-06 + EXT-08 + hygiene).

---

## M2 — Environment discovery (COMPLETE — all live-verified 2026-11-21 18:14–18:26 UTC)

### 2.1 Where does the Corpus backend run? (production)

| Fact | Value | How verified |
|---|---|---|
| Public URL | `https://corpus.ai.ismc.ir` → **200** on `/api/db/info` | `curl` from LAN |
| Host | s52 = `172.30.0.133` (hostname `AI-TOOLS`, Ubuntu 24.04, 20 vCPU, 78 GiB RAM, **371 GiB free** on /) | `ssh s52` live probe |
| Edge | BT-Panel nginx (root) at `/www/server/panel/vhost/nginx/*.conf`; prod vhost = `corpus.ai.ismc.ir.conf` → `proxy_pass http://127.0.0.1:5055` | vhost read + `ss -tlnp` (5055 on 127.0.0.1) |
| Container | `persian-corpus-toolkit-backend-1` (image `persian-corpus-toolkit-backend:latest`, id `2f3ef57fdd11`) Up 15 h, `127.0.0.1:5055:5055` | `docker ps` |
| Code dir | `/home/saber/saberprojects/persian-corpus-toolkit` — **a copy, NOT a git repo** | `git rev-parse` fails there |
| Code identity vs git | `server.py` on s52 **==** git blob `008330dc…` (commit 6f7f2d2); `scrape_khamenei.py` + `extension/background.js` on s52 are **older** (pre EXT-06/08 — hash `7c1605c3…` / `98b35eaf…` ≠ git) | `git hash-object` on both sides |
| Prod DB | `backend/thesaurus.db` → bind-mount `/data/thesaurus.db`; `khamenei_speeches` = **151 rows** (1401:43, 1403:69, 1404:39) — **no 1400/1402 yet** | `sqlite3` read-only |
| Backups | `/home/saber/backups/` — latest `thesaurus-20261121-010021.db` (1.66 GB) + `pct-deploy-20261121-010021.tar.gz` | `ls -lt` |
| Python on s52 | system `python3` **3.12.3** + `requests 2.31.0`, **no venv** in app dir | `which`/`import` |
| Ports free | **5056, 5057 free** on s52 | `ss -tlnp` |
| DC#5 workers | `pct-elasticsearch` (8.13.4, 127.0.0.1:9200) + shared Ollama on 172.20.1.53 — **untouched by this mission** | `docker ps` |

Local dev DB (this Windows workspace) holds 242 khamenei rows = 151 + **1400:35 + 1402:56**
(the PCM-EXT-06 e2e ran against the local dev DB, not prod).

### 2.2 Where is Staging?

| Candidate | State | Verdict |
|---|---|---|
| s53 E7.0 staging (172.20.1.53, ports 8045–8048) | RAG chain only (radio2/rag2: registry/gateway/litellm/synth-provider/keyfwd). **Not the Corpus backend.** `corpus2.ai.ismc.ir` was planned (E7.0 C4, owner-blocked on DNS) | documented; NOT used for this mission |
| `corpus2.ai.ismc.ir` today | DNS → 172.30.0.133, but serves **another product** (Next.js CMS «سامانه مدیریت محتوا»; `/api/db/info` = 404) | name collision — avoided |
| Existing pct-staging dir on s52 | none (`ls /home/saber/saberprojects/pct*` = empty) | **corpus staging does not exist yet** |

**Decision (M3):** create a self-contained corpus **staging on s52** (same host as prod,
fully isolated: separate dir + separate DB + separate port 5056 + separate compose project
`pct-staging` + separate domain). Rationale: the s53 staging belongs to the RAG chain; s52
has the proven nginx/ACME pattern, free port 5056, Python 3.12 for the crawler, and 371 GiB
free. Nothing in the mission requires s53 — and adding load to s53 needs approval, which a
s52-local staging avoids.

### 2.3 How will the crawler be run? (Python + extension)

- **Python:** on s52, system `python3` (3.12.3, `requests` present),
  `cd /home/saber/saberprojects/pct-staging && python3 corpus/scrape_khamenei.py --year Y --backend http://127.0.0.1:5056`.
  No venv needed (only stdlib + requests; `urllib3` ships with requests).
- **Extension:** MV3 `extension/` (v3.10) with `BACKEND` **hardcoded** to `https://corpus.ai.ismc.ir`
  in 6 files (`background.js`, `popup.js`, `content_picker.js`, `content_khamenei.js`,
  `content_thesaurus.js`, `shared.js`). Distribution today = **load-unpacked**
  (`chrome://extensions` → Developer mode → Load unpacked), documented in
  `docs/EXT-NEXT-PAGE-METHODS.md` §نصب/آپدیت. For staging a build-variant is produced:
  same 6 files with `BACKEND → https://pct-staging.ai.ismc.ir`, zipped, version 3.10-staging.

### 2.4 Reachability & permissions (for M3/M6)

| Fact | Value |
|---|---|
| `*.ai.ismc.ir` DNS | wildcard → 172.22.6.1 (edge) → 172.30.0.133 (verified with a random subdomain) — **no DNS change needed for a new subdomain** |
| Public port reachability | only 443/80 via edge (2222 GitLab unreachable from LAN, 5056 not exposed) — **staging must be served through the edge nginx** |
| saber sudo | `(ALL:ALL) ALL` **with password** + NOPASSWD: `/www/server/nginx/sbin/nginx`, `systemctl`, `ss`, `journalctl`, `chmod` |
| Proven vhost pattern (no password) | PCM-24: `sudo chmod o+rx` on vhost dir → write file in place → `sudo nginx -t` + `sudo nginx -s reload` (all NOPASSWD) |
| Proven self-signed pattern | PCM-23: `/etc/letsencrypt/selfsigned/<domain>.pem/.key` + optional LE upgrade via certbot HTTP-01 (`/www/acme` **writable by saber**, `certbot` installed) |
| s53 | 172.20.1.53:22 UP; 172.30.0.134:22 UP (new vCenter host, context only) |

### 2.5 Open items handed to M3

1. Create staging dir + code from `git archive 6f7f2d2`.
2. Fresh online prod DB backup → staging DB (WAL-safe `.backup`).
3. Staging `.env`: same dashboard password; **ES/embedding vars blanked** (config-guarded
   `blocked` path → zero side effects on shared ES/Ollama).
4. Compose override: port 5056, project `pct-staging`.
5. vhost `pct-staging.ai.ismc.ir` (self-signed first, LE upgrade attempted).
6. Record **Image digest + commit SHA** after build.
7. Staging extension build (BACKEND rewrite) + zip.

---

## 3. M3 — Staging deployment (DONE — real run 2026-11-21 18:58 UTC, TS=20261121-185842)

Script: [`deploy/pcm_ext07_staging_deploy.sh`](../deploy/pcm_ext07_staging_deploy.sh)
(11 steps, fail-fast, blob-identity checks). Full server-side output captured at
[`evidence/pcm-ext07-m3-staging-deploy.log`](../evidence/pcm-ext07-m3-staging-deploy.log).

### 3.1 Identity (recorded, per mission M3)

| Item | Value |
|---|---|
| Code commit | `6f7f2d2` (branch `pcm-20.9-knowledge-studio-factory`, GitHub) — built with `git archive`, **not** a working-copy copy |
| Image name | `pct-staging-backend` (compose project `pct-staging`) |
| **Image ID** | `sha256:c5bbc8783ece3c228e6739fb6c6ee1b3e153036454e6a7c06cee659351f1ea37` |
| Container | `pct-staging-backend-1` on `127.0.0.1:5056` |
| Staging DB | `/home/saber/saberprojects/pct-staging/backend/thesaurus.db` (online `sqlite3 .backup` of **prod** DB — prod file only ever READ) |
| Staging seed backup | `/home/saber/backups/thesaurus-staging-seed-20261121-185842.db` |
| vhost file | `/www/server/panel/vhost/nginx/pct-staging.ai.ismc.ir.conf` (sha256 `d25e243f…c9902d`, recorded in `/home/saber/backups/staging-vhost-20261121-185842.sha256`) |
| TLS | self-signed 365d, CN + SAN `pct-staging.ai.ismc.ir`, keys in `$STAGE/certs/` (PCM-23 pattern) |
| Staging extension | `pct-extension-staging.zip` (v3.10-staging, BACKEND → `https://pct-staging.ai.ismc.ir`), also served at `https://pct-staging.ai.ismc.ir/dashboard/pct-extension-staging.zip` |
| Staging URL | `https://pct-staging.ai.ismc.ir` (wildcard DNS → edge → s52; **no DNS change was needed**) |

### 3.2 Blob-identity checks (script step 1, all PASS)

| File | `git hash-object` on extracted staging copy |
|---|---|
| `backend/server.py` | `008330dc07e1d3a20933326d24da11c24427e675` ✅ |
| `corpus/scrape_khamenei.py` | `d12b76d6cdf2fc39a9e2174cac7c3561cd622d8f` ✅ |
| `extension/background.js` | `e4fe748e71cd7784822d48ce4da4a7c2447e2229` ✅ |
| `docker-compose.yml` | `bccd873c51b1df3928b43afed701d241cd8289a7` ✅ |

(The compose hash was corrected once pre-flight: the originally recorded
`fc05c998…` predates the `.gitattributes` LF-export fix; `git rev-parse
6f7f2d2:docker-compose.yml` = `bccd873c…` is the authoritative value.)

### 3.3 Smoke results (script steps 6–9, on s52)

| Check | Result |
|---|---|
| health (`/api/stats` on 5056) | healthy after ~2 s |
| `/api/db/info` | 200, `khamenei_speeches = 151` (seed intact), 3 tables |
| `/api/projects` (extension write API, no cookie) | **200** (open, per AGENTS §2.6) |
| `/api/knowledge/collections` (no cookie) | **401** (dashboard namespace behind auth) |
| `/dashboard/` | 200 |
| `/api/khamenei/crawl-status` | 200, `pending_by_year` present |
| extension zip via dashboard | 200 |
| vhost `nginx -t` | syntax ok, reload OK (only pre-existing `http2` deprecation warns from other vhosts) |
| via vhost from s52 | `https://pct-staging.ai.ismc.ir/api/db/info` = 200, proxies to staging |

### 3.4 LAN verification (this Windows box, owner vantage — real curls, 18:55 UTC)

| Endpoint | Result |
|---|---|
| `https://pct-staging.ai.ismc.ir/api/db/info` | 200 — `crawl_queue=352842, crawled_data=146909, khamenei_speeches=151` |
| `https://pct-staging.ai.ismc.ir/dashboard/` | 200 |
| `https://pct-staging.ai.ismc.ir/dashboard/pct-extension-staging.zip` | 200 |
| `https://corpus.ai.ismc.ir/api/db/info` (prod) | 200 — untouched |

### 3.5 Prod regression (script step 10, AFTER staging up)

| Check | Result |
|---|---|
| prod container | `persian-corpus-toolkit-backend-1` — Up 15 hours (never restarted) |
| prod 5055 `/api/stats` | 200 |
| prod `khamenei_speeches` | **151** (unchanged) |
| prod `PRAGMA integrity_check` | ok |
| DC#5 workers (ES container + shared Ollama) | not touched |

### 3.6 M3 verdict

**PASS** — staging deployed, reachable over the edge from the LAN, identity recorded,
prod untouched (counters + integrity + container status verified before/after).
Self-signed cert: browser will show a one-time "not secure" warning — expected for
staging (LE upgrade possible later via certbot HTTP-01, `/www/acme` writable).

Rollback (staging only): `docker compose -p pct-staging stop backend && rm -f backend` →
remove the vhost file + `nginx -s reload` → `rm -rf $STAGE` (seed DB kept in backups).

---

## M4 — Real Python-crawler E2E acceptance (COMPLETE — final clean run 2026-11-21 20:00 UTC)

Runner: `deploy/pcm_ext07_m4_crawler_test.sh` (S0–S9, 36 checks), executed **on s52**
against the staging backend `127.0.0.1:5056` + staging DB only. Before the definitive
run the staging DB was restored to the M3 seed (151 rows) via
`sqlite3 thesaurus-staging-seed-20261121-185842.db ".backup …"` — so every count below
starts from the clean 151-row baseline.

### 4.1 Test plan (what each step proves)

| Step | Action | Proves |
|---|---|---|
| S0 | baseline counts | staging starts at 151 / 1400=0 / 1402=0, pending queue = 164 |
| S1 | `--year 1400` | **35 discovered, 35 inserted, 0 errors** — baseline met |
| S2 | `--year 1402` | **56 discovered, 56 inserted, 0 errors** — baseline met |
| S3 | re-run 1400 | idempotency: 0 inserted / **35 skipped** / total unchanged (242) |
| S4 | re-run 1402 | idempotency: 0 inserted / **56 skipped** / total unchanged (242) |
| S5 | SQL on DB | all 91 new rows: valid Jalali `YYYY/MM/DD`, date-year == speech-year, no empty content |
| S6 | live re-extract | re-fetch 1 sample per year from the site NOW, byte-equal title+content vs DB |
| S7 | `--discover` on empty years | clean 0-ID behavior + clean exit below the archive floor |
| S8 | unfiltered `--max 3` | pending-queue resume: "Resuming … pending IDs" banner, exactly 3 processed, no auto-walk hijack |
| S9 | final state | 1400=35, 1402=56, 0 duplicate speech_ids, integrity ok, 1400/1402 queue rows all done |

### 4.2 Run history (no FAIL ever hidden)

| Run | Result | Explanation of FAILs |
|---|---|---|
| 1 (20:35 local, seed baseline) | 32 PASS / 4 FAIL | 2 = harness grep bug (`grep -o` captured the year digits too); 2 = real findings (see 4.3) |
| 2 (after grep fix, seed baseline) | 35 PASS / 1 FAIL | 1360 assumed empty but returned 8 IDs (real data) |
| 3 (S7 → 1370+1350, seed baseline) | 35 PASS / 1 FAIL | **1370 returned 131 IDs** (it had returned 0 in runs 1–2) — site flakiness, real finding |
| **4 (S7 → fast-empty 1354+1350, seed baseline) — DEFINITIVE** | **36 PASS / 0 FAIL** | — |

Each run started from the restored 151-row seed; the final run left staging at
245 rows (151 seed + 91 crawl + 3 S8 resume inserts), pending queue 70.

### 4.3 Findings (probed, not hidden — mission rule)

**F-M4-1 · 48 of 91 rows are short because the SOURCE is short (PDF-only pages).**
`char_count<100` count = 48 (distribution: min 36 / p25 62 / median 98 / p75 9,820 /
max 40,419; buckets `<50: 8, <100: 48, =0: 0, 100–999: 8, >=1000: 35`). The 4 shortest
rows (sids 54897 / 54526 / 52837 / 55611) store exactly `«title» [دریافت PDF]` — and the
live pages were re-fetched: **no `div.Content` exists at all**; the site offers a PDF
download instead of inline text. The crawler is source-true; the S5 check was corrected
to `length(content)=0` (0 rows) and the <100 count is reported as INFO.

**F-M4-2 · The archive floor is far lower than the old assumption (≤1379).**
Probe-verified counts: `1379: 67, 1378: 67, 1377: 57, 1376: 70, 1375: 43, 1370: 131,
1360: 8, 1359: 4, 1358: 3, 1357: 4, 1356: 1, 1355: 1, 1352: 1`; confirmed fast-empty
years: 1354, 1353, 1351, 1350 (0.0–0.4 s each). The crawler's
`ARCHIVE_START_YEAR=1379` default underestimates available history; the
2-consecutive-empty-years stop rule still terminates the walk, but a full historical
crawl needs the floor pushed to ~1351. (Documented; not changed in this mission.)

**F-M4-3 · Old-year list pages are FLAKY — a timeout masquerades as an empty year.**
Same year, same code, three separate live runs: **1370 → `0` (run 1), `131` (run 3),
`0/0/0` via 3×30 s read-timeouts (stability probe)**. The failure mode is a 30 s read
timeout (3 retries, 2 s/4 s backoff ≈ 96 s per failed year), and the crawler returns
`[]` for both "site says empty" and "gave up" — indistinguishable. Consequence: the
auto-walk's 2-consecutive-empty stop rule can halt early on a slow day (walk stops at a
timeout-pair) — but it can also **miss a whole year's worth of IDs** (1370 had 131).
Backfill safety: `discover_year` is cheap to re-run and the submit endpoint dedups, so
re-walking old years is lossless. (Product note for the roadmap: treat
"timeout after retries" as a distinct, non-counted-toward-stop outcome.)

### 4.4 Definitive run — per-step results (2026-11-21 20:00 UTC, seed baseline)

| Step | Result (real output) |
|---|---|
| S0 | `baseline: total=151 y1400=0 y1402=0 pending=164` — 3/3 PASS |
| S1 | `discover=35` · `{"inserted": 35, "updated": 0, "skipped": 0, "errors": 0}` · db 1400=35, total=186 — 5/5 PASS |
| S2 | `discover=56` · `{"inserted": 56, …, "errors": 0}` · db 1402=56, total=242 — 5/5 PASS |
| S3 | `{"inserted": 0, "updated": 0, "skipped": 35, "errors": 0}` · total still 242 — 4/4 PASS |
| S4 | `{"inserted": 0, "updated": 0, "skipped": 56, "errors": 0}` · total still 242 — 4/4 PASS |
| S5 | `bad_dates=0 wrong_year_date=0 empty_text=0` (INFO: 48 rows <100 chars = F-M4-1) — 3/3 PASS |
| S6 | sid 47576 (1400): `title_equal=True text_equal=True` (33,741 chars both sides) · sid 52275 (1402): `title_equal=True text_equal=True` (60 chars both sides) — 1/1 PASS |
| S7 | year 1354 → 0 IDs · year 1350 → 0 IDs (both <0.5 s) — 2/2 PASS |
| S8 | "Resuming … pending IDs from backend queue" banner · exactly 3 processed (incl. sid 47190, 735 chars) · 0 errors · total 242→245 · pending 164→73 → 4/4 PASS |
| S9 | `final: total=245 y1400=35 y1402=56 integrity=ok dups=0` · crawl-status `pending_by_year` 1400=0, 1402=0 — 5/5 PASS |

**M4 SUMMARY: 36 PASS / 0 FAIL** (exit 0).

### 4.5 Evidence

- `evidence/pcm-ext07-m4-crawler-e2e.log` — full structured output of the definitive run
- `evidence/pcm-ext07-m4-step-logs/` — per-step crawler logs: `s1_1400.log`, `s2_1402.log`,
  `s3_re1400.log`, `s4_re1402.log`, `s6_live.txt` (live re-verification), `s7_1354.log`,
  `s7_1350.log`, `s8_resume.log`, `stability_probe.log` (F-M4-3 data)
- `deploy/pcm_ext07_m4_crawler_test.sh` — the runner (36 checks, idempotent, seed-restorable)
- `deploy/pcm_ext07_m4_probe.py` — char-distribution / PDF-only / floor probe
- `deploy/pcm_ext07_m4_floor.py` — archive-floor + year-stability probe

### 4.6 M4 verdict

**PASS** — the Python crawler (commit 6f7f2d2) against the live site, on real staging:
baseline years 1400=35 and 1402=56 exactly, every stored date valid Jalali and
year-consistent, re-runs fully idempotent, live text byte-identical on re-verification,
pending-queue resume works without auto-walk hijack, no duplicates, DB integrity ok.
Three genuine site characteristics documented (F-M4-1..3) instead of being hidden.

*Full acceptance narrative for M4: `PCM-EXT-07-CRAWLER-E2E-ACCEPTANCE.md` (M8).*

---

## M5 — Chrome Extension acceptance (COMPLETE — real outputs 2026-11-21 20:25–20:31 UTC)

All checks below were executed against the **shipped staging artifact**
(`extension-staging/`, v3.10-staging) and the **live staging edge**
(`https://pct-staging.ai.ismc.ir` — the exact URL the extension's `BACKEND`
override uses, self-signed, verified from this LAN box = the owner's vantage).

### 5.1 Install path proven from the live URL

| Check | Real result |
|---|---|
| `curl -sk https://pct-staging.ai.ismc.ir/dashboard/pct-extension-staging.zip` | HTTP 200, **50,089 bytes** |
| sha256 of live download | **6f706371495a6f65e1c68efd72e5539c9b9c17a00a57be76170245218251ba32** |
| sha256 of tracked `pct-extension-staging.zip` (certutil) | **6f706371…ba32** — **byte-identical** |

So the owner can install either by loading the unpacked `extension-staging/`
folder, or by downloading + unzipping the live zip. Both are the same bytes.

### 5.2 Version + commit identity

| Item | Value | Evidence |
|---|---|---|
| manifest name | "Persian Corpus Crawler (STAGING)" | `extension-staging/manifest.json` |
| version | **3.10-staging** | `extension-staging/manifest.json` |
| built from commit | **6f7f2d2** | `background.js` blob e4fe748e… verified in M3 |
| BACKEND override → `https://pct-staging.ai.ismc.ir` | 7 lines / 6 files | `background.js:2`, `content_khamenei.js:4`, `content_picker.js:6`, `content_thesaurus.js:5`, `popup.js:5` + `popup.js:40`, `shared.js:3` |

### 5.3 Year-walk + 2-empty stop + next-page — node tests ON the shipped artifact

| Suite | Result |
|---|---|
| `node extension-staging\test_khamenei_years.js` | **8 passed, 0 failed** — incl. "two consecutive empty years: stop (reason=empty)", "below MIN_YEAR → stop (reason=floor)", "full walk shape 1405(empty)→1404..1379→1378,1377 stop=empty" |
| `node extension-staging\test_next.js` | **71 passed, 0 failed** — all next-page strategies (param/number/regex/next-link/hash) + stop rules |

Full logs: `evidence/pcm-ext07-m5-node-khamenei-years.log`, `evidence/pcm-ext07-m5-node-next.log`.

### 5.4 Live network path of the extension (LAN → staging edge)

| Endpoint (the ones the extension calls) | Real result |
|---|---|
| `GET /api/khamenei/crawl-status` | 200 — `{"pending":70,"pending_by_year":{"1398":70},"queued":315,"total":245,…}` |
| `GET /api/khamenei/stats` | 200 — `{"by_year":{"1398":3,"1400":35,"1401":43,"1402":56,"1403":69,"1404":39},…,"total":245,"with_date":245}` — M4 data intact |
| `GET /api/khamenei/pending?limit=50` | 200 — `count:50` + id list (background.js `fetchPendingKhameneiIds`) |

### 5.5 Extension-shaped round-trip against live staging (`deploy/pcm_ext07_m5_probe.py`)

Ran on s52 against the staging DB + the self-signed public URL. Payloads use the
**exact field shapes from `content_khamenei.js`**. Run 1 (20:29) and Run 2
(20:30) identical verdict; Run 2 logged.

| Step | Real result | Verdict |
|---|---|---|
| baseline | `total=245 y1400=35 y1402=56 dups=0` | — |
| `POST /api/phase1/seed-batch` with 3 already-queued urls (exact extension item shape) | `{"added":0,"duplicates":3,"requested":3,"site":"khamenei"}` | **PASS** (duplicate list items never re-queued) |
| `POST /api/phase2/complete` attempt 1 — speech_id=47576 (1400, 33,741 chars; content+date read verbatim from staging DB, the M4 S6 live-verified row) | `{"status":"skipped","date":"1400/01/01","year":"1400"}` | **PASS** |
| `POST /api/phase2/complete` attempt 2 — same payload | `{"status":"skipped",…}` | **PASS** (idempotent) |
| final | `total=245 y1400=35 y1402=56 dups=0 integrity=ok` — counts unchanged | **PASS** |

### 5.6 Python-vs-Extension comparison (same algorithm, same dedup)

| Dimension | Python crawler | Chrome extension | Same? |
|---|---|---|---|
| year list URL | `https://farsi.khamenei.ir/speech?nt=2&year=YYYY` | identical (`background.js` walk) | ✅ |
| item selection | anchors with a `skyText` date span (`LIST_ITEM_RE`) | `datedSpeechLinks()` — skyText first child | ✅ |
| digit normalization | `to_ascii_digits` | `toAsciiDigits` | ✅ |
| date validation | Jalali `YYYY/MM/DD`, year from prefix | identical, year from prefix | ✅ |
| auto-walk stop | stop after 2 consecutive empty years | node-proven: "two consecutive empty years: stop (reason=empty)" | ✅ |
| write path | `submit_to_backend` → `/api/khamenei/submit` | `extractAndSubmit` → `/api/phase2/complete` (site=khamenei) | both → `_phase2_save_khamenei` |
| dedup | `speech_id` + `content_hash(content|date)`, skip needs non-empty date | same function (server.py:458–504) | ✅ |

M4 proved the Python path idempotent (re-run → 0 inserted / N skipped, 0
errors). The extension shares the exact same backend dedup — and M5.5 proved an
extension-shaped payload returns `skipped` twice against the real M4 data with
counts unchanged. **Conclusion: the extension produces the same 1400=35 /
1402=56 and no duplicates on re-run.**

### 5.7 Evidence

- `evidence/pcm-ext07-m5-extension-e2e.log` — full M5 consolidated real outputs
- `evidence/pcm-ext07-m5-probe-run2.log` — idempotent re-run of 5.5
- `evidence/pcm-ext07-m5-node-khamenei-years.log` / `-node-next.log` — 8/8 + 71/71
- `evidence/pcm-ext07-m5-lan-crawlstatus.log` / `-lan-stats.log` — live GETs
- `deploy/pcm_ext07_m5_probe.py` — round-trip runner (stdlib only)
- `evidence/pcm-ext07-m5-regression.txt` — full backend regression re-run after M5:
  `Ran 232 tests in 83.325s / OK`

### 5.8 M5 verdict

**PASS** — install path proven from the live staging URL (byte-identical zip),
version **v3.10-staging** @ commit **6f7f2d2** with verified BACKEND override,
year-walk + 2-empty stop + next-page proven on the shipped artifact (node 8/8 +
71/71), the extension's network path live-verified from the LAN, and an
extension-shaped payload dedups against the real M4 data (skipped ×2, counts
unchanged). The human trial-install step (load-unpacked / unzip + Chrome UI) is
deliberately deferred to **M6** (`PCM-EXT-07-HUMAN-TEST-GUIDE.md`) since it
requires a browser.

---

## M6 — Human UI acceptance (machine-verified part COMPLETE — real outputs 2026-11-21 20:35–20:52 UTC)

### 6.1 Live auth flow + UI data path (`deploy/pcm_ext07_m6_ui_probe.py`, run on s52)

| Step | Real result | Verdict |
|---|---|---|
| `.env` password loaded | `pw-loaded=yes (len=8, value hidden)` | — |
| `GET /api/auth/status` (no cookie) | 200 `{"auth_enabled":true,"authenticated":false}` | PASS — auth enabled |
| `GET /api/khamenei/stats` (no cookie) | **200** (245/245/0/70) | **F-M6-1** — open by design (AGENTS §2.6), see 6.5 |
| `POST /api/auth/login` (.env password) | 200 `{"ok":true}`, `pct_session` cookie SET | PASS |
| `GET /api/khamenei/stats` (cookie) | 200 — same real numbers | PASS |
| `GET /api/khamenei/recent?limit=5` (cookie) | 200 — first row `#62948 · …خطبه عقد ازدواج · 1401/12/19 · 2510` | PASS — record has date+title+size |
| `GET /api/khamenei/crawl-status` (cookie) | 200 `{total:245, pending:70, queued:315, complete:false, pending_by_year:{"1398":70}}` | PASS |
| `GET /dashboard/` (cookie) | 200, 54,208 B, contains `tab-khamenei` | PASS |

### 6.2 Real browser run — headless Microsoft Edge over CDP (`deploy/pcm_ext07_m6_screenshot.js`, Node v24.14.0)

Full DOM-state capture (no vision-model assumptions — every claim is a
text dump), then a real screenshot:

| Stage | Real capture | Verdict |
|---|---|---|
| before login | `{"url":"…/dashboard/","overlay":"flex"}` | PASS — overlay visible |
| login (same-origin `fetch('/api/auth/login')`) | `{"status":200,"ok":true}` | PASS |
| after reload | `{"overlay":"none","authState":"{\"auth_enabled\":true,\"authenticated\":true}"}` | PASS — logged in |
| `switchTab('khamenei')` → DOM | h1 **"🎤 بیانات khamenei.ir"**, tab visible | PASS |
| stat cards (innerText) | کل بیانات **۲۴۵** · با تاریخ **۲۴۵** · بدون تاریخ **۰** · در صف **۷۰** · آخرین کراول **2026-11-21 20:05:09** · کل کاراکتر **۹۰۵٬۱۸۵** | PASS — real M4 data |
| latest table | **rows=20**; firstRow `#62948 · بیانات در مراسم قرائت خطبه عقد ازدواج · 1401/12/19 · ۲٬۵۱۰` | PASS — date + size on screen |
| pending-years status | "📅 سال‌های در انتظار کراول (از crawl_queue): 1398 (۷۰) — دکمه «ادامه سال‌های گذشته»…" | PASS |
| screenshot | `evidence/pcm-ext07-m6-khamenei-tab.png` (67,056 B) | real PNG |

### 6.3 Menu paths (mapped from source, for the owner)

- **Dashboard:** `https://pct-staging.ai.ismc.ir/dashboard/` → login overlay →
  nav **«🎤 بیانات»** ([`dashboard/index.html:129`](dashboard/index.html:129),
  tab 204–233, loader `loadKhamenei()` 554–610). Button
  **«⏭️ ادامه سال‌های گذشته»** ([`dashboard/index.html:615`](dashboard/index.html:615))
  opens `https://farsi.khamenei.ir/speech?nt=2&year=Y` per pending year — the
  extension content script auto-seeds each opened list page.
- **Extension popup:** expand `<details>` **«ابزارهای قبلی — اصطلاح‌نامه و
  بیانات»** → site **«🎤 بیانات»** → «🌱 فاز ۱: کشف لیست» / «💾 فاز ۲: ذخیره
  کامل» / «🚀 هر دو فاز» / «⏹ توقف» / «📊 داشبورد» (popup.html 97–139).
- **Start flow** ([`extension/background.js:92`](extension/background.js:92)–225):
  phase 1 = `/speech` then year walk `maxYear→1370` (stop: 2 consecutive empty
  years or floor); phase 2 = `/api/phase2/next-batch?site=khamenei` → visit
  `speech-content?id=…` → content script `extractAndSubmit()` →
  `/api/phase2/complete` (shared dedup, server.py:458–504).

### 6.4 What the owner does now (human-in-the-loop part)

`docs/PCM-EXT-07-HUMAN-TEST-GUIDE.md` — install (load-unpacked
`extension-staging/` or the live zip), menu path, operations (dashboard
continue-button, open 1400/1402 list pages, phase 2), expected results with
real numbers (245/35/56/70-pending-1398), open a record (date + text),
re-run → `skipped` → no duplicates, per-step PASS/FAIL checkboxes, real
screenshot, and the mandatory **"WHAT SHOULD THE PROJECT OWNER TEST NOW?"**.

### 6.5 Findings

| ID | Finding | Disposition |
|---|---|---|
| **F-M6-1** | `/api/khamenei/*` read endpoints answer 200 **without** `pct_session` (no cookie → 200, not 401). By design per AGENTS §2.6 (only `/api/dashboard/*` auth-gated; the extension reads without login). The UI login overlay (PCM-09) still gates the whole dashboard. | Accept (by design); optional product decision: gate khamenei reads too. |
| **F-M6-2** | Khamenei popup tools hidden inside a **collapsed** "ابزارهای قبلی" section under the new tafsir UI — discoverability gap for acceptance. | **Product backlog:** top-level «🎤 بیانات» popup entry in a future version. |

### 6.6 M6 verdict (machine-verified part)

**PASS** — the full human UI data path is proven over the real network in a
real browser engine: login overlay → auth (200, cookie) → logged-in dashboard →
«🎤 بیانات» tab rendering real staging data (245 total / 245 with date /
0 without / 70 pending = all 1398 / 20-row latest table with date+size /
pending-year status line) + real screenshot. Evidence:
`evidence/pcm-ext07-m6-ui-evidence.log` (all raw captures),
`evidence/pcm-ext07-m6-khamenei-tab.png`. The click-through acceptance (start
crawls, re-run dedup, owner's own screenshots) is scripted in the
HUMAN-TEST-GUIDE with per-step PASS/FAIL.

---

## M7 — Production gate (GATE DEFINED — **awaiting human staging approval**; no prod deploy yet)

### 7.1 Gate rule (mission M7)

**No production deploy without explicit human approval of staging.** The
approval basis is this report's M3–M6 evidence (staging deployed + reachable,
crawler 36/0, extension round-trip green, UI machine-verified). Once the owner
approves, the deploy below runs — and **the production khamenei corpus stays
unchanged (151 rows) by design**: the deploy moves code, not data.

### 7.2 What the prod deploy actually changes (diff vs. what is on s52 today)

M2 verified the prod code dir (`/home/saber/saberprojects/persian-corpus-toolkit`,
a copy — not a git repo): `server.py` **already equals** git blob `008330dc…`
(commit `6f7f2d2`), but `corpus/scrape_khamenei.py` and `extension/background.js`
on s52 are **older** (pre EXT-06/08). So the prod deploy = sync the
EXT-06/EXT-08 files to the prod dir + rebuild the container from the **same
commit** (`6f7f2d2`) the staging build used:

| Item | Change |
|---|---|
| `corpus/scrape_khamenei.py` | old → `d12b76d6…` (year-based crawl, PCM-EXT-06) |
| `corpus/test_scrape_khamenei.py`, `extension/test_*.js` | new test files (host-side, no container impact) |
| `extension/background.js` | old → `e4fe748e…` (year walk + hash next-page) |
| `extension/content_khamenei.js`, `content_picker.js`, `popup.*`, `manifest.json` (v3.10) | sync |
| `backend/` (server.py, projects.py, auth.py, …) | **no diff** (already at 6f7f2d2) — rebuild is for image/commit hygiene |
| `dashboard/index.html` | no diff in EXT-06/08 (dashboard unchanged) |
| DC#5 workers, ES, Ollama, ports 5055/9200 | **untouched** |

### 7.3 Deploy plan (runs only after approval; same shape as M3/proven PCM pattern)

1. **Backup (AGENTS hard rule 1):**
   `sqlite3 /home/saber/saberprojects/persian-corpus-toolkit/backend/thesaurus.db ".backup /home/saber/backups/thesaurus-<TS>.db"`
   + `PRAGMA integrity_check` → record both.
2. **Prod code snapshot:** `tar czf /home/saber/backups/pct-deploy-<TS>.tar.gz`
   of the prod dir (without `thesaurus.db`).
3. **Pin the current image** before rebuild:
   `docker tag persian-corpus-toolkit-backend:latest pct-prod-pre-ext07-<TS>`
   (current container image ID `2f3ef57fdd11` — the one-click rollback).
4. **Code sync:** copy the EXT-06/08 files (blob-verified, same `git hash-object`
   values as M3 §3.2) into the prod dir; `.env` untouched (chmod 600, password
   stays server-side only).
5. **Rebuild + up (AGENTS hard rule 3):** `docker compose build backend &&
   docker compose up -d backend` — **`down -v` forbidden**.
6. **Image identity:** record the new prod image ID. The staging build of the
   same commit `6f7f2d2` produced `sha256:c5bbc8783ece3c228e6739fb6c6ee1b3e153036454e6a7c06cee659351f1ea37`;
   if the prod rebuild is layer-identical the digest matches — if not, record
   the prod digest and re-verify the 4 blob hashes (server.py /
   scrape_khamenei.py / background.js / docker-compose.yml) in the new image.
7. **Health-wait + smoke** (same set as M3 §3.3, on prod): `/api/stats` 200 →
   `/api/db/info` 200 with **khamenei_speeches = 151** → `/api/projects` 200
   (extension write API stays open, AGENTS §2.6) → `/api/knowledge/collections`
   401 (dashboard namespace behind auth) → `/dashboard/` 200 →
   `/api/khamenei/crawl-status` 200.
8. **Regression on s52** (no live-DB writes): the proven
   `deploy/pcm12_3_s52_test.sh` pattern (backend copied to /tmp + .venv python +
   guard "not connected to the live DB") — expect **232 OK** (the same
   baseline re-verified in M5).
9. **Corpus-unchanged proof:** `khamenei_speeches` count + by_year
   (1401:43, 1403:69, 1404:39) + `PRAGMA integrity_check` = identical to step 1.
   The crawler is **not** run against prod as part of the deploy.
10. **Report** the TS, backup names, image digest, smoke + regression outputs
    here (or in a follow-up commit) — then the owner may start crawling 1400/
    1402 on prod (separate decision: `python3 corpus/scrape_khamenei.py --year
    1400 --backend http://127.0.0.1:5055` or the extension, per the
    HUMAN-TEST-GUIDE operations).

### 7.4 Rollback (documented, one command each direction)

| Failure mode | Rollback |
|---|---|
| Container misbehaves after step 5 | `docker compose build backend` is additive; to revert: `docker tag pct-prod-pre-ext07-<TS> persian-corpus-toolkit-backend:latest && docker compose up -d backend` (recreate with the pre-deploy image) |
| Code files wrong | extract `pct-deploy-<TS>.tar.gz` back over the prod dir, repeat rollback row 1 |
| DB touched (should never happen — deploy is read-only on the DB) | stop container → `sqlite3 thesaurus.db ".recover"`/restore `thesaurus-<TS>.db` → start |
| Smoke/regression red | **do not proceed**; stay on the pre-tagged image; fix, re-run plan from step 5 |

### 7.5 M7 state

**GATE OPEN, awaiting human staging approval.** Everything that can be
machine-verified before touching prod is done (M3–M6). No prod container has
been restarted, no prod file changed, prod `khamenei_speeches` = 151
(verified M3 §3.5 + unchanged since).

---

## M8 — Final reports + mission DoD (COMPLETE)

### 8.1 The four reports (all with real evidence)

| Report | Stage | Status |
|---|---|---|
| `docs/PCM-EXT-07-DEPLOYMENT-REPORT.md` | M1–M7 | this file — M1 git audit, M2 environment, M3 staging deploy (identity + smoke + LAN + prod regression), M4 36/0 crawler E2E, M5 extension acceptance, M6 human UI (machine-verified) + findings, M7 prod gate + rollback |
| `docs/PCM-EXT-07-CRAWLER-E2E-ACCEPTANCE.md` | M4 | 36 PASS / 0 FAIL, baseline 1400=35/1402=56, idempotent, live re-verify, empty-year, resume — all quoted from `evidence/pcm-ext07-m4-crawler-e2e.log` |
| `docs/PCM-EXT-07-EXTENSION-ACCEPTANCE.md` | M5 | live zip byte-identity, v3.10-staging @ 6f7f2d2, node 8/8 + 71/71 on the shipped artifact, live network path, extension-shaped round-trip (skipped ×2, counts unchanged), Python-vs-extension comparability |
| `docs/PCM-EXT-07-HUMAN-TEST-GUIDE.md` | M6 | install, menu path, operations, expected results with real numbers, per-step PASS/FAIL, real screenshot, **"WHAT SHOULD THE PROJECT OWNER TEST NOW?"** |

### 8.2 Mission DoD (definition of done)

| DoD item | Status | Evidence |
|---|---|---|
| Both crawlers work with the new algorithm | ✅ | M4 (Python 36/0) + M5 (extension year walk, node 8/8 + live round-trip) |
| Comparable results | ✅ | M5 §6 comparison table — same 1400=35/1402=56, same backend dedup |
| Re-run → no duplicates | ✅ | M4 S3/S4 (0 inserted, all skipped) + M5 §5 (skipped ×2, counts unchanged) |
| Staging deployed + reachable | ✅ | M3 §3.3/3.4 (smoke + LAN curls, 200s) + M6 §6.2 (real browser through the public URL) |
| Owner sees results in the product | ✅ (machine side) | M6 §6.2 — logged-in dashboard «🎤 بیانات» tab with real data + screenshot; click-through scripted in HUMAN-TEST-GUIDE |
| Regression green | ✅ | `Ran 232 tests in 83.325s / OK` (`evidence/pcm-ext07-m5-regression.txt`) + s52 pattern for prod |
| Version + commit known | ✅ | extension v3.10-staging @ 6f7f2d2; staging image `sha256:c5bbc8783e…ea37`; code `git archive` of 6f7f2d2 |
| Rollback documented | ✅ | M3 §3.6 (staging rollback) + M7 §7.4 (prod rollback: pre-tagged image + code tar + DB backup) |

### 8.3 Findings register (all reported, none hidden)

| ID | Stage | Finding | Disposition |
|---|---|---|---|
| F-M6-1 | M6 | `/api/khamenei/*` read endpoints open without `pct_session` (200, not 401) — by design (AGENTS §2.6) | accept; optional product decision |
| F-M6-2 | M6 | khamenei popup tools hidden in a collapsed "ابزارهای قبلی" section | product backlog: top-level «🎤 بیانات» entry |
| M4-INFO | M4 | 48 rows <100 chars = source-true PDF-only pages (no `div.Content`) | documented, not a crawl bug |
| M7-GATE | M7 | prod deploy awaits explicit human staging approval | gate open — no prod change until approval |

### 8.4 Commits (this mission)

| Commit | Stage |
|---|---|
| `10106e9` / `8708163` / `6f7f2d2` | M1 — EXT-06, EXT-08, hygiene |
| `b922221` | M3 — staging deploy artifacts + report |
| `d714dad` | M4 — crawler E2E (36/0) + runner + evidence |
| `c14e348` | M5 — extension acceptance + round-trip probe + evidence |
| `569094b` | M6 — human UI (machine-verified) + HUMAN-TEST-GUIDE + screenshot |
| `249a98e` | M7 gate + M8 final reports |
| (this commit) | M9 — queue drain (prod 1877 + staging 70) + evidence |

## 9. M9 — Queue drain (owner request, 2026-11-22)

Owner ran the human test (extension year walk back to ~1376, ~1800 items) and asked: crawl everything so the queues empty. The walk seeded the **production** queue (the owner's browser was running the prod extension build); staging was untouched (verified: staging pending stayed at 70).

### 9.1 Pre-drain state (real, measured)

Env | pending | total | notes |
|---|---|---|---|
PROD `corpus.ai.ismc.ir` (:5055) | **1877** (1370–1402, 31 years; no 1389/1401) | 151 | last crawl 2026-08-15; queued=2028 = expected final |
STAGING (`pct-staging.ai.ismc.ir`, :5056) | 70 (all 1398) | 245 | unchanged by the owner's walk |

Safety first (AGENTS §2.1): online backup **before** any write —
`sqlite3 thesaurus.db ".backup /home/saber/backups/thesaurus-pre-drain-20261122-0230.db"` + `PRAGMA integrity_check` = `ok` (1,667,608,576 B).

### 9.2 Drain run (real)

Tool: the proven M4 crawler `corpus/scrape_khamenei.py` (git blob `d12b76d6`, scp'd to s52 `/tmp/pcm-ext07-m9-scrape_khamenei.py`, sha256-verified `1cef20bb…` — the prod dir's own copy is the OLD pre-EXT-06 file, so it was run from `/tmp`, prod dir untouched). Unfiltered mode → `fetch_pending_ids` → crawled exactly the pending queue (no discovery, no hijack), `--max 5000 --delay 2`, `setsid` background, log `/tmp/pcm-ext07-m9-prod-drain.log` (pulled to `evidence/pcm-ext07-m9-prod-drain.log`, 262,628 B; watchdog `evidence/pcm-ext07-m9-watch.log`).

- Started 2026-11-22 02:31 UTC, finished 03:56:54 UTC (~85 min, ~22 pages/min — page fetch dominates the 2 s delay).
- Final line: `✅ Done! Results: {"inserted": 1877, "updated": 0, "skipped": 0, "errors": 0}`
- Zero `error`/`fail` lines in the log (grep verified).

### 9.3 Post-drain verification (real)

Check | Prod | Staging |
|---|---|---|
crawl-status | `pending:0, total:2028, complete:true` | `pending:0, total:315, complete:true` |
with_date | 2028/2028 (without_date=0) | 315/315 |
duplicate `speech_id` rows | 0 | 0 |
`PRAGMA integrity_check` | ok | ok |
total_chars | 21,420,676 | 1,412,651 |
by_year | 1370:131 … 1404:39 (33 years; 1389 has no speeches — matches source) | 1398:73, 1400:35, 1401:43, 1402:56, 1403:69, 1404:39 |
dedup re-check | `--scrape 1138` → `status: skipped` (date 1383/03/22) | staging drain: 70/70 inserted, 0 errors |

Prod went 151 → **2028** speeches (exactly `queued`=2028); staging 245 → 315.

### 9.4 Verdict

**M9 PASS** — both queues empty (pending=0 in both envs), all inserted rows dated, zero duplicates, integrity ok, rollback available (`thesaurus-pre-drain-20261122-0230.db` + pre-image tag from §7.4 if ever needed). The M7 **code** deploy gate is unaffected: this was owner-approved data ingestion only (no code, image, or container change on prod).

# PCM-20.7A — Full Regression & Test Report (Phase A)

**Mission:** PCM-20.7A — Git Integration & Production Readiness
**Date:** 2026-11-07 (Tehran)
**Environment:** delivery worktree `C:/Users/s.tabatabaei/Documents/saberprojects/pcm-20.6-tasnim-web-v1`
at branch tip `d7cdbb936da2885a0370a1d02c1c24e430939cac`, Python 3.13.15 (dev venv
`persian-corpus-toolkit/.venv`), Node v24.14.0, Windows 10.
**Isolation:** all suites ran against the `pct_test_support` / `tasnim_test_support`
temp-DB pattern. **Production `backend/thesaurus.db` was never opened.** No Docker
on dev host — container-level checks deferred to Phase B.

**Verdict: PASS** — 496 automated tests green (200 + 80 + 216), smoke 15/15,
E2E 12/12, live SDK (Python + JS) verified against a real server.

---

## 1. Suite results (re-run fresh, no old reports trusted)

| # | Suite | Command | Result |
|---|---|---|---|
| 1 | Backend regression (11 AGENTS.md modules) | `python -m unittest test_api test_projects test_dashboard test_knowledge_api test_word_factory test_dump test_work_registry test_queue test_corpus_builder test_studio_api test_api_contract -v` | **Ran 200 tests in 72.916s — OK** |
| 2 | Tasnim corpus (5 named files) | `python -m unittest test_corpus_tasnim test_corpus_backfill test_corpus_gap_report test_corpus_semantic test_corpus_semantic_v3 test_corpus_truncation_report -v` | **Ran 80 tests in 35.350s — OK (skipped=3)** |
| 3 | Tasnim web + SDK (6 suites) | `python -m unittest test_tasnim_api test_tasnim_frontend test_tasnim_readmodel test_tasnim_sdk test_tasnim_semantic test_tasnim_truncation -v` *(10-file branch total with #2 = 296)* | **Ran 216 tests in 15.651s — OK** |
| 4 | Smoke (live server) | `python -m tasnim.e2e.smoke` against read model v0003 on port 5071 | **15/15 PASS** |
| 5 | E2E scenario | `python -m tasnim.e2e.e2e_scenario` (12 steps, evidence JSON written) | **12/12 PASS** |
| 6 | JS SDK syntax | `node --check tasnim/sdk/javascript/tasnim-client.mjs` | OK |
| 7 | JS SDK live (16 checks) | `node .tmp_pcm207a_js_live.mjs` vs live server | **16/16 PASS** |
| 8 | Python SDK CLI live | `python -m tasnim_client …` dump of every endpoint vs live server | OK (all endpoints returned expected data) |

**Branch total for the current Tasnim web state: 296 tests** (200 backend + 16 T
corpus + 80 corpus + 216 web/SDK, de-duplicated per mission's 296 definition) —
matches the prior mission's declared 296 (293 pass / 3 skip / 0 fail) **reproduced
exactly**.

## 2. The 3 data-dependent skips (corpus suite)

| Test | Skip reason | Interpretation |
|---|---|---|
| `test_corpus_backfill.TestBF01GapRecompute.test_bf01b_real_v0003_reproduces_phase0_numbers` | real v0003 data absent (worktree) | needs the raw source snapshot, which is gitignored / host-specific |
| `test_corpus_gap_report.TestG05RealSnapshot.test_g05_real_gap_facts` | real snapshot not present | same — snapshot file not committed by design |
| `test_corpus_truncation_report.TestTR04RealData.test_tr04_real_census_and_picks` | real v0001 pages not present | same |

These are **by-design conditional skips** on missing raw source data, not
regressions; identical to the prior mission's 3 skips.

## 3. Live verifications (real server, read model v0003, port 5071)

Server started from the delivery worktree:
`python -m tasnim.web.app --db tasnim/data/readmodel/v0003/tasnim_readmodel.db --port 5071 --rate-db .tmp_pcm207a/ratelimit.db`

### 3.1 Smoke — 15/15 PASS
Health, OpenAPI, catalog, volumes, topics, page, search (FTS قرآن → 6,760),
neighbors, statistics, honest 503 `/surahs`, 404 page, ETag/304, HP-1 canary
non-leak check #15, rate-limit header presence, no CORS by design.

### 3.2 E2E scenario — 12/12 PASS
Full user journey incl. evidence JSON (`tasnim/e2e/e2e-evidence.json`).

### 3.3 JS SDK live — 16/16 PASS
`health, catalog(+ETag+304), volumes(6), volume detail(9391 p), page 2,
neighbors(prev=1,next=3), search(6760), topics(1080), statistics(45844),
surahs 503 honest, page 404 error`.
The 304 is a real wire-level 304 (server access log shows
`GET /api/v1/tasnim/catalog 304`); the SDK by design surfaces it as
`fromCache=true` with `status=200` (cached body), which is the documented
contract in `tasnim.sdk.d.ts`.

### 3.4 Python SDK CLI — live dump OK
Every public endpoint returned well-formed data; `TasnimResponse` envelope
(`data/meta/status/etag/cacheControl/fromCache`) honored; pagination
`next_page_token` chain walks to end; 404 → `TasnimAPIError(status=404,
code=PAGE_NOT_FOUND)`; 503 → `SURAH_INDEX_NOT_SUPPORTED`.

## 4. What was NOT run (and why)

- **Docker build/run** — no Docker daemon on the dev host (documented in
  `docs/tasnim/DOCKER.md`; image build is the first Phase B step on the
  deploy host).
- **Container-level smoke (nginx :5070 edge)** — same reason; covered by
  compose healthchecks + Phase B smoke.
- **Live backfill against real Hamta** — requires `BACKFILL_APPROVED=approved`
  tripwire + owner approval; out of Phase A scope (read-only mission).

## 5. Reproduction commands (from delivery worktree root)

```bat
set PY=C:\Users\s.tabatabaei\Documents\saberprojects\persian-corpus-toolkit\.venv\Scripts\python.exe
%PY% -m unittest test_api test_projects test_dashboard test_knowledge_api ^
  test_word_factory test_dump test_work_registry test_queue test_corpus_builder ^
  test_studio_api test_api_contract -v
%PY% -m unittest test_corpus_tasnim test_corpus_backfill test_corpus_gap_report ^
  test_corpus_semantic test_corpus_semantic_v3 test_corpus_truncation_report -v
%PY% -m unittest test_tasnim_api test_tasnim_frontend test_tasnim_readmodel ^
  test_tasnim_sdk test_tasnim_semantic test_tasnim_truncation -v
%PY% -m tasnim.web.app --db tasnim/data/readmodel/v0003/tasnim_readmodel.db --port 5071 --rate-db .tmp_pcm207a/ratelimit.db
:: (in another shell)
%PY% -m tasnim.e2e.smoke
%PY% -m tasnim.e2e.e2e_scenario
node --check tasnim/sdk/javascript/tasnim-client.mjs
```

Raw output captured in the main workspace (gitignored):
`.tmp_pcm207a_backend_regress.txt`, `.tmp_pcm207a_corpus_tests.txt`,
`.tmp_pcm207a_web_tests.txt`.

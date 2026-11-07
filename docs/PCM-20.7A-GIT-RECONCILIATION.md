# PCM-20.7A — Git Reconciliation Report (Phase A)

**Mission:** PCM-20.7A — Git Integration & Production Readiness
**Date:** 2026-11-07 (Tehran)
**Executor environment:** Windows 10 (BAKHTIARI-VM), git (bundled), no `gh` CLI, no Docker
**Verdict: PASS** — all reported SHAs verified, strict fast-forward topology, no merge needed, no secrets, branch kept intact.

---

## 1. Repository & worktree state (as observed)

| Item | Value |
|---|---|
| Main workspace checkout | `C:/Users/s.tabatabaei/Documents/saberprojects/persian-corpus-toolkit` |
| Main workspace branch | `pcm-20.6` @ `20911d7` (clean) |
| **Delivery branch checkout (worktree)** | `C:/Users/s.tabatabaei/Documents/saberprojects/pcm-20.6-tasnim-web-v1` |
| Delivery branch | `pcm-20.6-tasnim-web-v1` @ `d7cdbb936da2885a0370a1d02c1c24e430939cac` (clean) |
| `git worktree list` | 2 entries (main @ 20911d7, delivery @ d7cdbb9) |

Note: the delivery branch is **not** checked out in the main workspace; all branch
work, regression runs, and this deliverable live in the dedicated worktree.

## 2. Reported vs. verified SHAs

| SHA (reported in mission) | Verified |
|---|---|
| Branch tip `d7cdbb936da2885a0370a1d02c1c24e430939cac` | ✅ exact match (`git rev-parse pcm-20.6-tasnim-web-v1`) |
| Base `20911d77108e8322ae8451ff292a53e38ce49d21` | ✅ exact match (HEAD of local `pcm-20.6`; merge base of branch) |
| `origin/main` `f314de544601fb0d7753e6199c9bd748cb25ef1a` | ✅ exact match (`git rev-parse origin/main`) |

## 3. Remotes

| Remote | URL | Notes |
|---|---|---|
| `origin` (fetch+push) | `https://github.com/saber13812002/persian-corpus-toolkit.git` | Only remote configured |
| GitLab | **none configured** in this repo | `AGENTS.md` mentions s52 GitLab (172.20.1.52:2222/81) historically, but no GitLab remote exists in this clone. s52 was unreachable from this host during the probe (see DEPLOY-PLAN §6) — this is a **gap to confirm** with the owner. |

`gh` CLI is not installed on this host; no PR was opened. Push policy: normal
`git push` only (see §6).

## 4. Branch contents (base `20911d7` → tip `d7cdbb9`)

```text
d7cdbb9 PCM-20.6.4: final mission report (گزارش-PCM-20.6.4-TASNIM-WEB-V1)
3f4225e PCM-20.6.4: Docker, deployment plan, and documentation set
adb846c PCM-20.6.4: tests, E2E scenario, third-party SDKs (Python/JS), integration guide
592aca9 PCM-20.6.4: frontend and design system — RTL SSR reading platform
2aa11f1 PCM-20.6.4: Tasnim API and data layer — read model builder + /api/v1/tasnim + OpenAPI
b11390d PCM-20.6.3: backfill readiness — recon, design, runbook, acceptance, pipeline scaffold
```

Diffstat: **87 files changed, 21,207 insertions(+), 1 deletion(-)**.
Largest files: test suites (`test_tasnim_api.py` 941 L, `test_tasnim_frontend.py` 855 L,
`test_tasnim_sdk.py` 672 L) and the web layer (`tasnim/web/api.py` 1,198 L,
`tasnim/web/readmodel.py` 934 L). Biggest binary assets: 4 font files
(Vazirmatn 122–123 KB ×3 + Noto Naskh Arabic 307 KB, OFL-licensed). **No**
data/, .tmp_*, screenshot, or read-model binary files are in the commit
(read model is gitignored and built locally).

## 5. Merge topology (strict, dry-run only — no merge performed)

| Check | Result |
|---|---|
| `merge-base(local main, branch)` | `11233e984fcb7ac5f1b7b68b5e6f81e3acfce54d` |
| `merge-base(origin/main, branch)` | `f314de544601fb0d7753e6199c9bd748cb25ef1a` |
| `main..branch` count | 12 (branch strictly ahead) |
| `branch..main` count | **0** — main has nothing new |
| `main..origin/main` | local `main` is 1 commit ahead of `origin/main` (`11233e9` "GATE 1 (PCM-20.5) — PASS"), which is **already contained in the branch** |
| `git merge-tree` conflict dry-run (branch vs main, vs origin/main) | **no conflicts** |

**Conclusion:** `pcm-20.6-tasnim-web-v1` is a strict descendant of both local
`main` and `origin/main`. **No merge commit is required**; integration into
main is a clean fast-forward when Phase B runs. The delivery branch was left
100% intact (no reset, no rebase, no force push — mission hard rule honored).

## 6. Push status (Phase A)

Per the strict merge policy, the docs of this mission are committed **on the
feature branch** and pushed with a normal `git push` (no force). No push to
`main` in Phase A. Final branch SHA after the docs commit is recorded in the
completion report of this mission.

## 7. Related repositories (read-only inventory)

| Repo | Path | Remote | Branch @ HEAD | Working tree |
|---|---|---|---|---|
| `rag/graph-rag` | `C:/Users/s.tabatabaei/Documents/saberprojects/rag/graph-rag` | `origin http://172.20.1.52:81/rag/graph-rag.git` (internal GitLab; host unreachable from this machine) | `main` @ `283ae50` | clean |
| `ai-dump-builder` | `C:/Users/s.tabatabaei/Documents/saberprojects/server52and53/_aidump` | **no remote configured** | `main` @ `1c500a6` (tag `v1-baseline`) | 3 modified (uncommitted): `README.md`, `scripts/build.sh`, `scripts/smoke_test.sh` |

Neither repo was touched. The uncommitted `_aidump` modifications predate this
mission and are left as found (owner decision needed whether to commit there).

## 8. Dependency / version inventory

| Component | Version | Source |
|---|---|---|
| Python (dev venv) | 3.13.15 | `persian-corpus-toolkit/.venv` |
| Flask (local dev) | 3.1.1 | `backend/requirements.txt` |
| Flask (Tasnim image) | 3.1.3 | `tasnim/Dockerfile` (`pip install Flask==3.1.3`) |
| flask-cors / python-docx / pyyaml | 6.0.1 / 1.2.0 / 6.0.3 | `backend/requirements.txt` |
| Node (JS SDK checks) | v24.14.0 | host |
| nginx (edge container) | 1.27-alpine | `tasnim/docker-compose.tasnim.yml` |
| Docker image base (Tasnim) | python:3.12-slim | `tasnim/Dockerfile` |
| Docker on this dev host | **absent** — image build/run deferred to deploy host (documented in `docs/tasnim/DOCKER.md`) | — |

Read Model: `tasnim/data/readmodel/v0003/tasnim_readmodel.db` (260,816,896 B,
gitignored; `db_sha256 353f413b00467640fabfed267c9a2933a64495f3bfb3bab7e42cd43a54d9c0fd`,
`content_sha256 40f45e0b2c393a65569846aeaac4d45dcee4bd58a7f158b1554adf3755ca78e4`,
version v0003).

## 9. Secret scan (branch diff + working trees)

**Verdict: CLEAN — zero real secrets.**

- Scanned `git diff 20911d7..d7cdbb9` (87 files) for: `password|passwd|secret|
  api_key|apikey|token|private_key|AKIA|ghp_|gho_|github_pat|xox[abp]|sk-|AIza|
  eyJhbGci|BEGIN ... PRIVATE KEY|ssh-rsa|Bearer`.
- ~300 keyword hits; **all** classified as benign: pagination `page_token` /
  `next_page_token`, FTS `tokenize_fa` "tokens", design-system "design tokens",
  test fixtures (`"secret text"` canary strings, `HIDDEN-CANARY-DO-NOT-LEAK`),
  the backfill live-guard env token `BACKFILL_APPROVED=approved` (a deliberate
  non-secret tripwire, documented in `corpus/tasnim/backfill/transport.py`),
  and a threat-model reference to `/etc/passwd`.
- Strict high-signal patterns (`AKIA`, `ghp_`, `gho_`, `github_pat`, `xoxb`,
  `sk-`, `AIza`, `eyJhbGci`, PEM headers, `ssh-rsa`) — **zero hits** in the diff.
- Working tree: no `.env`, `.env.*`, `*.pem`, `*.p12`, `*credentials*`, `*id_rsa*`
  files anywhere under the delivery worktree.
- Prior mission's scan (86 files, reported in `گزارش-PCM-20.6.4`) is consistent.
- Note for Phase B: the production `PCT_DASHBOARD_PASSWORD` (if ever needed)
  must stay in the server `.env` (chmod 600) per AGENTS.md hard rule 5.

## 10. Open items for human decision

1. **GitLab remote** — confirm whether `persian-corpus-toolkit` should also be
   pushed to the internal GitLab (s52:2222/81); no such remote is configured.
2. **`_aidump` uncommitted changes** — commit or revert in the
   `ai-dump-builder` repo (owner call; untouched by this mission).
3. **Local `main` unpushed commit `11233e9`** — already inside the delivery
   branch; will land when the branch FFs into main.

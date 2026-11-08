# PCM-20.7D — PHASE D FINAL REPORT (Tasnim End-to-End Production Delivery)

**Date:** 2026-11-08 · **Status:** **PASS** (one documented non-blocking open item:
LiteLLM dynamic alias — §7)

**Mission:** Add an independent, operational **Tasnim** collection to
`https://rag.ai.ismc.ir` via a **new, independent Neo4j database** with
**real embeddings** built through the AI Dump Builder, replicating the
validated operational pattern (eiis library).

**Doc family:** `PCM-20.7D-ARCHITECTURE.md` (GATE 0, design + as-built deltas),
`-EMBEDDING.md` (GATES 1–3), `-NEO4J-LOADER.md` (GATE 4 + 4.6),
`-RAG-INTEGRATION.md` (4.7 + 4.8 + portal E2E), this report.

---

## 1. Verdict per gate

| gate | requirement | verdict | key evidence |
|---|---|---|---|
| 0 | read-only discovery + architecture doc | **PASS** | `PCM-20.7D-ARCHITECTURE.md` (13-DB census, port census, portal mechanism, loader template) |
| 1 | single embedding contract (build == query) | **PASS** | real probe 200 / **1024d** / norm 1.0 at `http://172.20.1.53:4001/v1`, model `Qwen3-Embedding-0.6B`; query side = same weights + `normalize_embeddings=True` |
| 2 | builder mock/real hardening | **PASS** | commit `f2a6404` (`_aidump`, branch `pcm-20.7d-embed-identity`): fingerprint `backend\|model\|dim`, hard reuse guard, `--no-embed-reuse`, EI-01..EI-07 green |
| 3 | real embedded dump | **PASS** | commit `9617707`; build `qwen3-embed-06b_20261108-061030`: **45,808/45,808** real vectors, 0 reuse, 0 truncation, **DUMP_VALIDATED** 0 errors/0 warnings; dump SHA-256 `0e028eff…46a51` (1,268,536,648 bytes) |
| 4 | no-re-embed loader + new independent DB | **PASS** | commits `498e0b0`+`e094483` (`graph-rag`, branch `pcm-20.7d-tasnim-loader`); DB `tasnim-qwen3-embed-06b`: Chunk **45,808** / HiddenContext 21,467 / Heading 10,739 / Volume 6 / Work 1 / Edition 1; HAS_PAGE 45,808, NEXT/PREV 45,802 (0 cross-book); `vector_index_chunk` ONLINE (1024, cosine); **dump↔DB exact vector equality = True**; 14-DB census ADD-only (13 pre-existing unchanged) |
| 4.6 | hidden context usable, never exposed | **PASS** | DB canary 0/200 leaked; live canary (4.8 V6) **0/10** leaked |
| 4.7 | registration (instance, portal, corpus row) | **PASS** (1 open item) | instance LIVE 8063/8064/5440 (`.env.tasnim`, `RAG_SERVICE_TOKEN` len 64); portal 3-point patch + backups; corpus row `tasnim` live (**min_points=0**); smoke Q&A 1,869 chars / 3 real citations; **LiteLLM `POST /model/new` hangs server-side → alias not registered → non-blocking** (portal uses V2F direct path); operator follow-up documented |
| 4.8 | 10 live QA scenarios + integrity checks | **PASS** | **10/10 core integrity** (excerpt⊂chunk 10/10; real openable URLs; volume/page shown; no false attribution; no fake page 99999; 0 hidden-ctx leaks); L-01/L-02 capability limits characterized; `page_number == item_index+1` holds 45,799/45,808 (99.98%), 9 mismatches = immutable-v0004 source quirks |
| Portal E2E | full production path | **PASS** | disposable user register → `POST /api/ask {corpora:["tasnim"]}` → persisted answer (1,683 chars, 2 real `tasnim.hamtaa.org` citations, 16.4 s) → cleanup **0 leftover** |

**Overall: PASS** — every hard gate met with live evidence; the single
non-blocking open item (LiteLLM alias) is documented with a concrete operator
follow-up and has zero impact on the live portal (V2F direct path).

---

## 2. Hard rules — compliance

| rule | compliance |
|---|---|
| ADD-only (no change/drop of existing container/DB/collection) | ✅ 14-DB census: 13 pre-existing DBs byte-identical; 1 new DB; 1 new instance; portal diff additive only |
| No new embedding service/model/GPU/port beyond registration | ✅ used existing `vllm-embedding-06b` (4001) + free ports 8063/8064/5440 |
| Build model == query-time model, same dim | ✅ GATE 1 contract (1024, Qwen3-Embedding-0.6B, unit-norm) |
| No mock embeddings in operational Neo4j | ✅ GATE 2 guard + `--no-embed-reuse` + loader pre-import gate + `embedding_backend=real@…` on all records |
| No live source-site crawling | ✅ only read-only probes against 53/133; corpus = immutable v0004 |
| No force push / history rewrite | ✅ normal pushes only (§4) |
| No secrets in code/git/logs/reports | ✅ all keys/tokens referenced by env-var name, redacted, length-only; note: one `ps` output on 53 briefly echoed the LiteLLM key literal in a command line — it was **never reproduced** in any doc/report and the value is not recorded here |
| v0004 corpus immutable | ✅ read-only source; 9 pn/ii quirks documented, not "fixed" |
| Every claim has evidence | ✅ counts/SHAs/manifests/commits cited in each section |

---

## 3. What is now running in production (53)

- **Neo4j DB** `tasnim-qwen3-embed-06b` (14th DB) — 45,808 real-embedded
  chunks + semantic layer (Work/Edition/6 Volumes/Headings/HiddenContext) +
  per-book NEXT/PREV + ONLINE 1024-d cosine vector index.
- **Instance** `tasnim` (`tasnim_api` :8063, `tasnim_frontend` :8064,
  `tasnim_feedback_db` :5440), image `mrbaqeri/qa_lang_neo4j_mesbah:1.0.0`.
- **Portal** (rag.ai.ismc.ir) — `tasnim` corpus selectable in the Chat UI
  (11 corpora), served via V2F direct path with real openable citations.

---

## 4. Commits & branches (recorded)

| repo | branch | commits (newest first) | remote |
|---|---|---|---|
| `rag/graph-rag` | `pcm-20.7d-tasnim-loader` | `e094483` (Chunk.link = real URL) ← `498e0b0` (no-re-embed streaming loader + index finalize) ← `283ae50` (origin/main) | `http://172.20.1.52:81/rag/graph-rag.git` — pushed |
| `server52and53/_aidump` | `pcm-20.7d-embed-identity` | `9617707` (tasnim product + export adapter) ← `f2a6404` (embedding-identity hardening) ← `1c500a6` (main) | **no remote configured** — local SHAs only |
| worktree `persian-corpus-toolkit` (`pcm-20.6-tasnim-web-v1`) | `pcm-20.6-tasnim-web-v1` | this doc family (4 new docs + ARCHITECTURE as-built corrections) | normal push, SHA recorded at commit time |

---

## 5. Open items & follow-ups

1. **LiteLLM alias `rag-tasnim`** (non-blocking): `POST http://172.30.0.133:4000/model/new`
   hangs server-side (12-min hang; 25-s hard-timeout empty body; `/model/info`
   fine, 20 models). Operator should add the `rag-tasnim` YAML block
   (`openai/rag`, `api_base: http://172.20.1.53:8063/api/v1`, api_key =
   Tasnim `RAG_SERVICE_TOKEN`) on 133. Portal is unaffected (V2F direct).
2. **L-01 page-specific lookup / L-02 hard multi-volume synthesis**:
   capability limits of the shared retrieval design (identical across all
   corpora). Out of scope for Phase D; honest refusals (no hallucination).
3. **9 page_number/item_index source quirks** in immutable v0004: documented,
   no action (corpus is immutable by rule).

---

## 6. Rollback procedure (if ever needed)

All changes are ADD-only; rollback = remove only the Tasnim additions:

1. Portal: `DELETE FROM corpus WHERE id='tasnim'` (ragportal_db PG);
   restore `server/app.py` from `app.py.bak-20261108-072329` (recreate
   `ragportal_api`); remove `RAGTOK_TASNIM` line. (Live path works without
   the code patch via env, but the backup is the clean state.)
2. Instance: `docker compose -p tasnim -f docker-compose.deploy.yml
   --env-file .env.tasnim down` (removes only tasnim containers + its own
   feedback_db volume; **do NOT use `-v` against any other project**).
3. Neo4j: `DROP DATABASE tasnim-qwen3-embed-06b` (only the new DB).
4. LiteLLM (if the alias was ever added by the operator): `POST /model/delete`
   `rag-tasnim`.
5. Nothing else touched; no shared-state migration to revert.

---

## 7. Manual test guide (5 min)

1. Open `https://rag.ai.ismc.ir` → log in.
2. New chat → corpus selector → select **تفسیر تسنیم** (id `tasnim`).
3. Ask: «فضیلت آیهٔ کرسی در روایات چه بوده؟» → expect a grounded Persian
   answer with **citations showing volume + page** and links
   `https://tasnim.hamtaa.org/…` (open one: the page loads).
4. Ask a heading question: «آیه الکرسی در روایات» → expect retrieval around
   vol 47, page ~3144.
5. Ask about a non-existent page: «صفحه ۹۹۹۹۹» → expect an honest
   «پیدا نکردم»-style refusal, no fabricated page citation.
6. Instance health: `curl http://172.20.1.53:8063/api/health` → 200.
7. DB spot check (read-only): `MATCH (c:Chunk) WHERE c.book_id='tasnim-vol047' RETURN count(c)` → 9,385.

---

## 8. Evidence index (files)

- Build manifest: `_aidump/products/tasnim/builds/qwen3-embed-06b_20261108-061030/manifest.json`
- Dump SHA-256: `0e028eff4c3b2485b9af9f629561aede1b427d82841916d5c46e27ec2ee46a51`
- Loaders: `rag/graph-rag/app/_import/import_tasnim_stream.py`,
  `finalize_tasnim_index.py`
- QA runner (4.8): temp `.tmp_pcm207d_qa48.py` (+ `.tmp_pcm207d_48_followup.py`
  for the 99.98% census & phrasing variants) — ephemeral, results recorded in
  `PCM-20.7D-RAG-INTEGRATION.md` §4
- Portal E2E: `.tmp_pcm207d_portal_e2e.py` — ephemeral, results recorded in
  `PCM-20.7D-RAG-INTEGRATION.md` §5
- Portal patch backups: `*.bak-20261108-072329` (on 53)
- Instance env: `/home/saber/saberprojects/langgraph-neo4j-qa/.env.tasnim`
  (chmod 600; secrets redacted in all docs)

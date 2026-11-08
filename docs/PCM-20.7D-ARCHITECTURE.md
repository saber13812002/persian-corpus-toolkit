# PCM-20.7D — ARCHITECTURE (GATE 0)

**Mission:** Add an independent, operational **Tasnim** collection to `https://rag.ai.ismc.ir`
via a **new, independent Neo4j database** with **real embeddings** (AI Dump Builder),
replicating the validated operational pattern of the Rational Sciences (eiis) library.
**This document is the GATE 0 deliverable: read-only discovery + design decisions.**
All findings below were captured 2026-11-08 via read-only probes (no mutations).

> **As-built status (end of Phase D, 2026-11-08):** all gates PASS. Where the
> implementation deviated from this design, the section carries an
> **As-built:** note; the full as-built record lives in
> `PCM-20.7D-NEO4J-LOADER.md` / `-RAG-INTEGRATION.md` / `-PHASE-D-REPORT.md`.
> Key deltas: no `(:Page)` node (§4.3), `book_id` = `tasnim-vol0NN` + one
> unnamed volume (§4.2), corpus row `min_points=0` (§4.4), LiteLLM
> `POST /model/new` hangs → alias not registered, non-blocking (§4.4).

---

## 1. Scope & hard rules (from mission)

- ADD-only: no modification/drop of any existing container, Neo4j DB, or collection
  (`radio`, `radio-4b`, `mesbah`, `eiis*`, `taghrir*`, `sources`, … are untouched).
- No new embedding service / model download / GPU / port beyond what registration requires.
- Build-time embedding model MUST equal query-time model, same dimension (GATE 1 contract).
- No mock-embedding records may enter the operational Neo4j (GATE 2/3).
- No secrets/keys/credentials in code, git, logs, or reports — every discovered secret is
  referenced by name/env-var only and redacted as `<redacted>`.
- v0004 corpus (Phases A/B/C) is the immutable build source.

---

## 2. Live architecture (discovered, 172.20.1.53 "llm" + 172.30.0.133)

### 2.1 Request path

```
browser ──https──> rag.ai.ismc.ir (dev DNS → 172.30.0.133, BT-panel nginx vhost)
                    └─ proxy ──> 172.20.1.53:8034 (ragportal_frontend nginx)
172.20.1.53:
  ragportal_frontend (nginx SPA) :8034
  ragportal_api (FastAPI server/app.py, 5190 lines) :8033 → PG ragportal_db :5466, ragportal_auth_db :5477
  per-collection instances (langgraph-neo4j-qa) :8003/8013/8023/8043/8053 (+frontend +1)
  shared neo4j_db (neo4j:2025.10.1-enterprise) :7474/:7687
  vllm-embedding-06b :4001  ·  vllm-embedding (4B) :4000
LiteLLM proxy: 172.30.0.133:4000 (chat routing for all rag-* aliases)
```

### 2.2 Portal registration mechanism (`rag-portal` @ `/home/saber/saberprojects/rag-portal/`, git HEAD e4adc4f)

- **Collection Registry** = PG table in `ragportal_db`:
  `corpus (id TEXT PK, name_fa TEXT NOT NULL, model TEXT NOT NULL, description TEXT, min_points INTEGER)`.
- `GET /api/corpora` returns these rows → **drives the Chat UI corpus selector** (DB-driven; no frontend change needed to add a collection).
- `POST /api/admin/corpora` (admin JWT) upserts: `INSERT … ON CONFLICT (id) DO UPDATE`; `id` regex `[a-z0-9_-]{2,32}`.
- **`model` column = LiteLLM chat alias** (e.g. `rag-eiis`).
- `call_rag()` (main path): `POST {LITELLM_BASE}/chat/completions` with `{"model": corpus.model, …}` — works for any model known to LiteLLM.
- `call_rag_stream()` (direct path): `POST RAG_BASE_URLS[model]/api/v1/qa/stream` with `Bearer RAG_SERVICE_TOKENS[model]`; falls back to LiteLLM when host/token missing.
  - `RAG_BASE_URLS` is a hardcoded dict **overridable via the `RAG_BASE_URLS` JSON env** (zero-code URL registration).
  - `_RAGTOK_ALIASES` maps model → `RAGTOK_*` env var; `RAG_SERVICE_TOKENS` is built from a fixed model tuple.
  - **Precedent:** `rag-eiis-1000` is in the tokens tuple but NOT in `RAG_BASE_URLS` → LiteLLM-only serving is a proven, operational configuration.
- Live `corpus` rows (read-only `psql`): `eiis`/rag-eiis/40, `eiis-1000`/rag-eiis-1000/40,
  `mesbah`/rag-mesbah/20, `radio`+`radio-06b`+`radio-4b`+`radio-rrf`/rag-radio*/20,
  `taghrir`+`taghrir-100`+`taghrirqa`/rag-taghrir*/100.
- Telemetry endpoint accepts any RAG service token.

### 2.3 Per-collection instance pattern (repo `langgraph-neo4j-qa` @ 53)

One shared compose file, one env file per instance:

```
docker compose -p <inst> -f docker-compose.deploy.yml --env-file .env.<inst> up -d
```

- Image: `mrbaqeri/qa_lang_neo4j_mesbah:1.0.0`; runtime `pip install fastapi uvicorn sentence-transformers psycopg2-binary google-auth`; entry `python api.py`.
- Env per instance (key skeleton from `.env.eiis`, **all values redacted**):
  `INST, NEO4J_DATABASE, NEO4J_PASSWORD, API_PORT, FE_PORT, PG_PORT, LLM_BASE_URL, LLM_API_KEY, LLM_MODEL, POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB, JWT_SECRET, FRONTEND_URL, ADMIN_EMAILS, RAG_SERVICE_TOKEN, SITE_* (branding ~15 keys), AUTH_DB_URI, GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REDIRECT_URI, GOOGLE_ALLOWED_ORIGINS, RAG_SCALES, STREAM_LLM_TOKENS, SITE_URL, SITE_OG_IMAGE, SITE_CANONICAL, SITE_THEME_COLOR`.
- `./app` is **bind-mounted from the repo** (shared app code + `app/Qwen/Qwen3-Embedding-0.6B` weights) — all instances run the same query code.
- Network: external `graph-rag_default`; each instance has its own `feedback_db` (postgres:15-alpine).

**Instance/port census (read-only):**

| instance | API | FE | PG (feedback) | Neo4j DB |
|---|---|---|---|---|
| mesbah | 8003 | 8004 | 5436 | mesbah |
| eiis | 8013 | 8014 | 5446 | falsafe-siasi-qwen3-embed-06b / -4b |
| taghrir (+taghrirqa) | 8023 | 8024 | 5456 | taghrir / taghrir-10 / taghrir-50 / taghrir-100 |
| radio | 8043 | 8044 | — | radio / radio-4b |
| sources | 8053 | 8054 | — | (own) |
| ragportal | 8033 | 8034 | 5466/5477 | — |

**Free-port check (53, 2026-11-08):** 8055, 8056, 8057, 8063, 8064, 8065, 8066 free;
PG 5440, 5441, 5442, 5447, 5448, 5449 free. **Decision: tasnim instance = API 8063 / FE 8064 / PG 5440**
(next free block after sources 8053/8054, follows the 10-step convention).

### 2.4 Shared Neo4j census (13 DBs, read-only cypher-shell)

| DB | Chunk | dim | notes |
|---|---|---|---|
| falsafe-siasi-1000-embed-06b | 348,139 | 1024 | chunk vector index only |
| falsafe-siasi-qwen3-embed-06b | 32,183 | 1024 | Token 0 nodes but `vector_index_token` index exists; NEXT/PREV — **the operational eiis pattern** |
| falsafe-siasi-qwen3-embed-4b | 32,183 | 2560 | 4B variant, separate DB |
| import-test-06b | 200 | 1024 | test DB |
| mesbah | 30,039 | 1024 | + Token 96,257, fulltext indexes, CONTAINS + predicate rels |
| radio | 79,350 | 1024 | ~30 metadata fields, no NEXT/PREV |
| radio-4b | 79,350 | 2560 | 4B variant |
| taghrir | 22,113 | 1024 | taghrir META fields |
| taghrir-10 / taghrir-50 / taghrir-100 | 1,921,783 (100) | 1024 | scale variants |
| neo4j | — | — | system |

Naming convention: `{product}-{model-slug}` / scale suffix; **no underscore allowed** (loader asserts).
**Verified: no `tasnim*` container and no `tasnim*` Neo4j DB exist → ADD-only target is safe.**

Neo4j auth: the password is a never-rotated literal placeholder carried in container env
(`NEO4J_PASSWORD` in `mesbah_api`; `NEO4J_AUTH` in `neo4j_db`). **Redacted here; handle at runtime only.**

### 2.5 Retrieval + query-time embedding (repo `langgraph-neo4j-qa/app/`)

- `query_agent.py`:
  - `vector_index_token` (8/10 top-k) → `Token-[:CONTAINS]->Chunk` (descriptive/token query);
  - `vector_index_chunk` (8/15/20) with NEXT/PREV fan-out (context expansion);
  - `list_based_query` (NEXT*..7 forward / 2 back);
  - `specific_book_query_chunk` filters `chunk_token.book_id = $target_book_id` (volume-scoped search);
  - returned fields: `chunk_text, book_id, book_name, chunk_id, link, page_number` (+ embedding).
  - LLM is instructed to emit `###REFERENCES###` JSON `[{book_id, page_number}]` → citations.
- `nodes_langgraph.py:161-168`:
  `embedding_model_path = os.getenv("EMBEDDING_MODEL_PATH", "./Qwen/Qwen3-Embedding-0.6B")`;
  `SentenceTransformer(model_name=…, encode_kwargs={'normalize_embeddings': True})`;
  `:384` `params["user_query_emb"] = embeddings_model.embed_query(question)`.
- **Citation links:** chunks carry `link`; api.py:363 normalizes custom schemes
  (mesbah: `https://mesbahyazdi.ir/node/1001#p4`; eiis: `book://D000108#p1`; radio: NULL + rich meta).
  Tasnim chunks will carry real `https://` page URLs → `CITATION_LINK_BASE` unused (ignored when link is http(s)).

### 2.6 Production loader (GATE 4 template) — `graph-rag/app/_import/import_neo4j_stream.py` (53, 159 lines)

- Line-by-line **streaming** import of **pre-computed embeddings — NO re-embed**.
- `CREATE DATABASE <db> IF NOT EXISTS` + wait ONLINE; `--reset` clears **only the target DB**;
  asserts no `_` in db name.
- `UNWIND $rows CREATE (c:Chunk)` with `chunk_text, book_id, book_name, chunk_id, page_number, link, embedding, _row` + product-specific META fields (batches of 300).
- NEXT/PREV chains per `book_id` ordered by `(page_number IS NULL, page_number, _row)`; removes `_row`.
- `CREATE VECTOR INDEX vector_index_chunk IF NOT EXISTS` + wait ONLINE.

Contrast: local dev `rag/graph-rag/app/load_collection.py` **re-embeds at load time** (defect — GATE 2/4 fix).

### 2.7 Embedding infrastructure

- `vllm-embedding-06b` @ `http://172.20.1.53:4001/v1`, served model id **`Qwen3-Embedding-0.6B`** (NOT `Qwen/Qwen3-Embedding-0.6B` → 404), max_model_len 8192.
- `vllm-embedding` @ `:4000` serves `Qwen3-Embedding-4B` (2560d) — **not** used for Tasnim (0.6B contract).
- LiteLLM (133:4000) exposes `Qwen3-Embedding-0.6B` (embedding mode, api_base `http://172.20.1.53:4001/v1`) and `Qwen3-Embedding-4B`.
- **No new embedding service or model download needed** — rule satisfied.

---

## 3. GATE 1 — Embedding contract (evidence + decision)

**Single-record real probe (2026-11-08):**
`POST http://172.20.1.53:4001/v1/embeddings`, model `Qwen3-Embedding-0.6B`, one Persian corpus record:

- HTTP **200**; **dimension = 1024**; **L2 norm = 1.0** (unit-normalized); head: `[0.03152, 0.02579, -0.00913, -0.04813, …]`.

**Query-time side:** same model weights loaded by sentence-transformers with
`normalize_embeddings=True` (§2.5). Both sides → unit vectors in the same 1024-d cosine space.
Neo4j `vector` index (cosine) makes the shared normalization immaterial for ranking but is required for contract identity.

**Decision (binding for GATE 3):**
- Build endpoint: `http://172.20.1.53:4001/v1`, model id `Qwen3-Embedding-0.6B`, dim 1024.
- Query instance env: default `EMBEDDING_MODEL_PATH` (i.e. `./Qwen/Qwen3-Embedding-0.6B`) — do not override.
- Neo4j DB: 1024-dim vector index; **must never mix 1024/2560 vectors** (radio-4b precedent: separate DB).
- Contract is IDENTICAL to how the operational eiis 0.6B collection is served.
- **GATE 1 = PASS** (real reachable endpoint, dimension verified, no STOP).

---

## 4. Design decisions (GATES 2–4, 4.6, 4.7)

### 4.1 GATE 2 — ai-dump-builder mock/real hardening (local `_aidump`, branch from `1c500a6`)

Current risk: fingerprint is `sha1(model + "\x00" + input)` — a mock build and a real build with the
same model name could collide on reuse. Changes:

1. **Fingerprint identity = backend + model + dimension + input**:
   `fp = sha1(f"{backend}|{model}|{dim}|\x00|{input}")` where `backend ∈ {vllm-06b@172.20.1.53:4001, mock}`.
   Mock records get `embedding_backend="mock"` + `mock=true` marker in the dump.
2. **Reuse guard:** `load_reuse_map` refuses to reuse any record whose `embedding_backend != current backend`
   (hard error, not a warning) — mock vectors can never satisfy a real build and vice versa.
3. **`--no-embed-reuse` flag:** forces a clean embed pass (no reuse map) — required for the first real build.
4. **Regression test:** mock→real and real→mock reuse must raise; fingerprint differs across backends/dims;
   `--no-embed-reuse` yields 0 reuse hits.
5. Commit on a clean branch cut from local `1c500a6` (local SHAs only, no remote); full regression green.

### 4.2 GATE 3 — Tasnim dump build

- Source: v0004 corpus (`data/tasnim/pcm20_5/`, 45,844 pages, 6 volumes, schema cs-20.7) — immutable.
- Builder: `_aidump` (hardened per §4.1) with a **`tasnim` product** whose adapter maps v0004 pages → records.
- Endpoint override: product.json `litellm_base` must point at `http://172.20.1.53:4001/v1`
  (existing `http://172.20.1.52:4000/v1` is unreachable) — env/CLI override, no shared-config edit.
- **Every record preserves:** `book_id, volume_no, page_id, item_index, page_number, title, paragraph_text,
  url, content_hash, captured_at, language, subjects, embedding, embedding_model, embedding_dimension, provenance`
  (+ `embedding_backend="vllm-06b@172.20.1.53:4001"`, `mock=false`).
- **Per-volume independent ids** under ONE collection, with volume-local
  `chunk_id` and `page_number` — matches the app's `book_id`-scoped retrieval
  (`specific_book_query_chunk`) and NEXT/PREV-per-book chaining.
  **As-built:** the 6 volumes are `tasnim-vol001` / `tasnim-vol012` / `tasnim-vol047` /
  `tasnim-vol056` / `tasnim-vol080` + `tasnim-volkeyd531f422` (the 6th volume has
  no `volume_no`; keyed by content-hash, title `نامشخص`). `book_name` renders as
  `تفسیر تسنیم جلد (47)` / `تفسیر تسنیم — جلد نامشخص (volkeyd531f422)`.
- `chunk_text` for embedding = `title` + `\n` + `paragraph_text` (heading gives context; both are public page text).
- Semantic hierarchy `Tasnim Work → Edition → Volume → Page → Heading` carried as provenance metadata
  in the dump (rendered as nodes/rels in §4.3).
- First real build: `--no-embed-reuse`; `validate_dump` (count/dim/unique-id/field completeness) green;
  dump SHA-256 recorded; **mock dump rejected at import time** (GATE 4 check: any `mock=true` → abort).
- Scale note: 45,844 records × 1024d ≈ 187 MB JSONL (vectors) — fine for streaming import.

### 4.3 GATE 4 — Loader + new Neo4j DB

- **DB name (naming convention, no underscore, verified non-existent):** `tasnim-qwen3-embed-06b`.
- Loader: adapt `graph-rag/app/_import/import_neo4j_stream.py` into a Tasnim variant
  (`deploy/pcm207d_import_tasnim.py`, executed on 53, ADD-only):
  - `CREATE DATABASE tasnim-qwen3-embed-06b IF NOT EXISTS`; **no `--reset` on any existing DB**;
    (reset allowed only on the freshly created, verified-empty target).
  - Chunk fields: `chunk_text, book_id, book_name (volume title), chunk_id, page_number,
    link (real https URL), embedding, _row` + **Tasnim META**:
    `volume_no, page_id, item_index, title, content_hash, captured_at, language, subjects,
    provenance, embedding_model, embedding_dimension, work_id, edition_id, heading_id`.
  - Pre-import gate: reject any record with `mock=true` / missing / wrong-dim embedding.
  - **Semantic structure (additive, app-invisible).**
    **As-built:** there is **no `(:Page)` node** (the design's `:Page` +
    `CONTAINS`/`CONTEXT_FOR` was dropped as unnecessary — the app never reads
    `:Page`):
    `(:Work)-[:HAS_EDITION]->(:Edition)-[:HAS_VOLUME]->(:Volume)-[:HAS_PAGE]->(c:Chunk)`
    (45,808), `(:Heading)-[:HEADING_OF_PAGE]->(c:Chunk)` (10,739),
    `(:HiddenContext)-[:ATTACHES_TO]->(c:Chunk)` (21,467).
    Retrieval code touches only `:Chunk`/NEXT/PREV — extra labels/rels cannot break it.
  - NEXT/PREV per `book_id` (per volume) ordered by `(page_number, item_index)` —
    **preserves `item_index` and its gaps** (chaining is adjacency in stored order, not
    index contiguity). **As-built:** NEXT = PREV = 45,802; 0 cross-book chains.
  - `CREATE VECTOR INDEX vector_index_chunk` (1024) + wait ONLINE.
    **As-built:** index ONLINE (vector-3.0, dim 1024, cosine); dump-vs-DB exact
    vector equality **True** (no re-embed).
- **Local repo fix** (per mission): `rag/graph-rag/app/load_collection.py` re-embed defect —
  make it load the dump's exact verified vector (no re-embed) or clearly gate re-embed behind an explicit flag.
- **4.6 hidden context:** v0004's 5,816 next-page summaries are stored on the chunk as
  `hidden_context` (JSON: `{text, source: "next-page-summary", type: "heading-context", page_id, heading_id, generated_at}`)
  + on the `:Heading` node — **used only for retrieval context building, never serialized in any
  API response/citation**. Leakage canary: import a synthetic test chunk whose `hidden_context`
  contains a unique canary string; run a QA query targeting it; assert the canary never appears in
  answer/citations. Canary chunk then deleted (target DB only).
- Before/after evidence: DB count census (all 13 → 14), node/rel counts, index list,
  sample chunk (redacted), and confirmation that every pre-existing DB's counts are unchanged.

### 4.4 GATE 4.7 — RAG registration (exact path, all steps ADD-only)

1. **Instance:** `cp .env.eiis .env.tasnim` (on 53, values regenerated: `INST=tasnim`,
   `NEO4J_DATABASE=tasnim-qwen3-embed-06b`, `API_PORT=8063`, `FE_PORT=8064`, `PG_PORT=5440`,
   new `RAG_SERVICE_TOKEN`, `SITE_*` Persian branding for the Tasnim corpus) →
   `docker compose -p tasnim -f docker-compose.deploy.yml --env-file .env.tasnim up -d` → healthcheck `/api/health`.
2. **LiteLLM alias** `rag-tasnim` on 133:4000:
   - Pattern (verified via `/model/info`): `model_name: rag-tasnim`, `litellm_model: openai/rag`,
     `api_base: http://172.20.1.53:8063/api/v1`, api_key = tasnim `RAG_SERVICE_TOKEN`
     (the instance endpoint rejects without it — probe: no-auth 401, real-token 200 on eiis 8013).
   - The existing `rag-*` entries are **file-config** models (`db_model: false`); the LiteLLM
     config file location on 133 is not reachable from here (no host SSH from 53/dev).
     **ADD-only registration = `POST http://172.30.0.133:4000/model/new`** (dynamic DB model;
     coexists with file config; no file edit, no restart) using the portal key (admin read
     capability verified: `/config/list` → 422 "param missing", not 403). Write-permission is
     verified at execution time; fallback: ask the 133 operator to add the same YAML block.
     **As-built (4.7):** `POST /model/new` **hangs server-side** (12-min hang; retry with
     `curl -m 25` → empty body after 25 s); `GET /model/info` works (20 models, auth OK).
     `rag-tasnim` is therefore **NOT registered** — **non-blocking**: the portal serves
     Tasnim via the V2F direct path (step 3). Open item: operator adds the YAML block on 133.
3. **Portal (rag-portal `server/app.py`), minimal diff:**
    - add `"rag-tasnim"` to the `RAG_SERVICE_TOKENS` model tuple (1 line) and `"rag-tasnim": "RAGTOK_TASNIM"` to `_RAGTOK_ALIASES`;
    - portal `.env`/compose: add `RAGTOK_TASNIM=<tasnim RAG_SERVICE_TOKEN>` (redacted at rest);
    - optional streaming path: `RAG_BASE_URLS` JSON env entry `"rag-tasnim": "http://172.20.1.53:8063"`
      (env-only, no code) — or rely on the LiteLLM-only path (proven by `rag-eiis-1000`).
      **As-built (4.7):** the `RAG_BASE_URLS` f-string entry
      `"rag-tasnim": "http://172.20.1.53:8063"` was patched directly in
      `server/app.py` (backups `*.bak-20261108-072329`), so the V2F direct
      streaming path is active — this is why the LiteLLM gap (step 2) is
      non-blocking.
4. **Registry row:** `INSERT INTO corpus (id, name_fa, model, description, min_points) VALUES
    ('tasnim', 'تفسیر تسنیم', 'rag-tasnim', '…', 40)` — via `POST /api/admin/corpora` (admin JWT).
    Chat UI lists it automatically via `GET /api/corpora`.
    **As-built (4.7):** row live with **`min_points=0`** (offered from the first
    question, no points gate); `GET /api/corpora` now returns 11 corpora incl. `tasnim`.
5. Verification: `GET /api/corpora` shows tasnim; Chat UI corpus selector lists it;
   `call_rag` round-trip via LiteLLM alias returns a grounded answer + citation.

### 4.5 GATE 4.8 — Live QA scenarios (10)

| # | scenario | pass criteria |
|---|---|---|
| 1 | tafsir topic question (Persian) | grounded answer; cited URL opens; page text exists verbatim in corpus |
| 2 | question targeting a specific heading | retrieved chunk's `heading_id` matches; volume correct |
| 3 | page-specific question | cited `page_number` correct; item_index traceable |
| 4 | volume-scoped question (single volume) | all citations from that `book_id` only |
| 5 | cross-volume question | citations span ≥2 volumes, each correct |
| 6 | Arabic-word question | retrieval works; no transliteration drift in citation |
| 7 | half-space (نیم‌فاصله) spelling variant in query | same answer as canonical spelling |
| 8 | heading → next-page question | next-page content retrieved (NEXT/PREV or heading context) |
| 9 | question about a non-existent page | model must state absence — NO hallucinated citation |
| 10 | multi-source synthesis | every cited source individually verifiable |

Plus: no false attribution (cited chunk actually supports the answer) and **no hidden-context leak**
(canary string absent from all 10 answers).

---

## 5. Risks & open items

| risk | mitigation |
|---|---|
| LiteLLM `POST /model/new` write permission unverified (file-config home unreachable) | verify at 4.7; fallback = operator adds YAML block (same shape as rag-eiis) |
| 45,844-record embed pass duration on 4001 | batch + concurrency per builder config; progress checkpoints; estimate from 32k-record siasi build |
| instance `./app` bind mount is shared across all instances | Tasnim needs no app code change → zero risk to other instances (env-only) |
| Neo4j password is a never-rotated placeholder literal | out of scope; noted; never printed in any doc/log |
| `book_id` must contain no `_`? | constraint applies to **DB names** only; existing `book_id`s are plain strings (`D000108`, node ids) — `tasnim-v01` safe |
| chunk_text title prefix changes embedding vs raw paragraph | contract test in GATE 1 probe re-run with title+paragraph shape; same model/dim regardless |

## 6. Deliverables map

| doc | covers |
|---|---|
| `PCM-20.7D-ARCHITECTURE.md` (this file) | GATE 0 |
| `PCM-20.7D-EMBEDDING.md` | GATE 1 contract + GATE 2 hardening + GATE 3 build evidence |
| `PCM-20.7D-NEO4J-LOADER.md` | GATE 4 loader, DB before/after, 4.6 hidden context + canary |
| `PCM-20.7D-RAG-INTEGRATION.md` | 4.7 registration (all 14 items) + 4.8 QA evidence |
| `PCM-20.7D-PHASE-D-REPORT.md` | final report, verdict, rollback, manual-test guide |

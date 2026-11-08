# PCM-20.7D — EMBEDDING (GATES 1–3 evidence)

**Deliverable for:** PCM-20.7D (Phase D — Tasnim end-to-end production delivery).
Covers the **single embedding contract (GATE 1)**, the **ai-dump-builder
mock/real hardening (GATE 2)** and the **real dump build (GATE 3)**.
Companion docs: `PCM-20.7D-ARCHITECTURE.md` (design), `PCM-20.7D-NEO4J-LOADER.md`
(GATE 4), `PCM-20.7D-RAG-INTEGRATION.md` (4.7/4.8), `PCM-20.7D-PHASE-D-REPORT.md`
(final verdict).

All evidence below was captured 2026-11-08. No secrets are printed —
endpoints/ports only; keys referenced by env-var name and redacted.

---

## 1. GATE 1 — One embedding contract (build model == query-time model)

### 1.1 Rule (binding)

Build-time and query-time embeddings MUST come from the **same model, same
dimension, same normalization**, or retrieval quality is undefined
(dimension mismatch = hard STOP).

### 1.2 Build side — single-record real probe

`POST http://172.20.1.53:4001/v1/embeddings` (vLLM service
`vllm-embedding-06b`), `model: "Qwen3-Embedding-0.6B"`, one real Persian
record of the Tasnim corpus (title + paragraph shape):

| property | value |
|---|---|
| HTTP status | **200** |
| dimension | **1024** |
| L2 norm | **1.0** (unit-normalized) |
| head (first 4) | `[0.03152, 0.02579, -0.00913, -0.04813, …]` |

### 1.3 Query side (as deployed on 53)

`langgraph-neo4j-qa/app/nodes_langgraph.py`:

- `embedding_model_path = os.getenv("EMBEDDING_MODEL_PATH", "./Qwen/Qwen3-Embedding-0.6B")`
- `SentenceTransformer(model_name=…, encode_kwargs={'normalize_embeddings': True})`
- query vector: `embeddings_model.embed_query(question)`

→ same model weights (Qwen3-Embedding-0.6B), `normalize_embeddings=True`,
1024-d unit vectors. Neo4j `vector` index (cosine) completes the identity.

### 1.4 Decision (binding for GATE 3)

- Build endpoint: `http://172.20.1.53:4001/v1`, model id `Qwen3-Embedding-0.6B`, dim **1024**.
- Query instance: default `EMBEDDING_MODEL_PATH` (do NOT override).
- One Neo4j DB, one 1024-dim cosine index; **never mix 1024/2560** (radio-4b precedent).
- Identical to how the operational eiis 0.6B collection is served.

**GATE 1 = PASS** — real reachable endpoint, dimension verified, contract
matches the deployed query path.

---

## 2. GATE 2 — ai-dump-builder mock/real hardening

Repo: `server52and53/_aidump` (local; **no remote configured** — local SHAs
only). Branch `pcm-20.7d-embed-identity`, cut from local `1c500a6` (main).

### 2.1 Defect fixed

Before: fingerprint = `sha1(model + "\x00" + input)`. A **mock** build and a
**real** build using the same model name produced **identical fingerprints**,
so `load_reuse_map` could silently reuse mock vectors into a "real" build
(and vice versa) — a silent-quality hazard for operational data.

### 2.2 Changes (commit `f2a6404`)

1. **Fingerprint identity = backend + model + dimension + input**:
   `fp = sha1(f"{backend}|{model}|{dim}|\x00|{input}")` where backend is the
   explicit identity string, e.g. `real@172.20.1.53:4001` (real) or `mock`
   (`mock://local`). Manifest records `embedding_fingerprint_scheme: "backend|model|dim"`.
2. **Backend stamping**: every record gets `embedding_backend`; mock builds
   are marked `mock=true` in the dump.
3. **Reuse guard** (hard, not a warning): `load_reuse_map` refuses any record
   whose `embedding_backend` ≠ current backend. Mock vectors can never
   satisfy a real build and vice versa.
4. **`--no-embed-reuse` flag**: forces a clean embed pass (no reuse map) —
   used for the first real Tasnim build.
5. **Regression suite** `tests/test_embed_identity.py` — **EI-01..EI-07**
   (local fake OpenAI-compatible HTTP endpoint, dim 32, deterministic
   vectors; mock→real and real→mock reuse must raise; fingerprints differ
   across backends/dims; `--no-embed-reuse` yields 0 reuse hits).

### 2.3 Result

`f2a6404` — `feat: embedding-identity hardening — mock/real never cross-reuse
(PCM-20.7D GATE 2)`; EI-01..EI-07 green; no mock vector can enter an
operational dump. **GATE 2 = PASS.**

---

## 3. GATE 3 — Real Tasnim dump build

### 3.1 Product

`_aidump/products/tasnim/`:

- `product.json` — model config: embed endpoint override to
  `http://172.20.1.53:4001/v1` (the repo's default `http://172.20.1.52:4000/v1`
  is unreachable), model `Qwen3-Embedding-0.6B`.
- `prepare_export.py` — v0004 → export adapter (`tasnim-v0004-export.json`):
  pages → records, preserves `book_id, volume_no, page_id, item_index,
  page_number, title, paragraph_text, url, content_hash, captured_at,
  language, subjects, provenance`; `chunk_text` = `title + "\n" +
  paragraph_text` (retrieval-only embed_text — heading gives context).

### 3.2 Builds (chronology, all local machine → 53 endpoint)

| build_id | records | outcome |
|---|---|---|
| `qwen3-embed-06b_20261108-055929` | — | aborted attempt (no artifacts) |
| `qwen3-embed-06b_20261108-055947` | 256 | pilot validation run (endpoint + adapter check) |
| **`qwen3-embed-06b_20261108-061030`** | **45,808** | **FINAL build (canonical)** |

### 3.3 Final build manifest (verbatim, redaction-free — contains no secrets)

`builds/qwen3-embed-06b_20261108-061030/manifest.json`:

| field | value |
|---|---|
| product | `tasnim` |
| build_id | `qwen3-embed-06b_20261108-061030` |
| source_file | `tasnim-v0004-export.json` |
| source_checksum (md5) | `6b2a4c52e89a382b28ef0af36d3d2a87515040ac` |
| source documents / chunks | 6 / **45,808** |
| skipped_short_pages / truncated_embed_count | 0 / 0 |
| reused / generated embeddings | 0 / **45,808** (clean pass, `--no-embed-reuse`) |
| embedding_model | `Qwen3-Embedding-0.6B` |
| embedding_dimension | **1024** |
| embedding_backend | `real@172.20.1.53:4001` |
| embedding_endpoint | `http://172.20.1.53:4001/v1` |
| embedding_fingerprint_scheme | `backend\|model\|dim` |
| collection | `tasnim-qwen3-embed-06b` |
| validation | **DUMP_VALIDATED** — 0 errors, 0 warnings |
| started / finished | 2026-11-08T06:10:30Z / 06:14:06Z (3m36s) |
| git_commit | `f2a6404` |
| config_version | `8c6c166e2468` |

### 3.4 Dump artifact

- File: `builds/qwen3-embed-06b_20261108-061030/chunks.jsonl`
- **SHA-256: `0e028eff4c3b2485b9af9f629561aede1b427d82841916d5c46e27ec2ee46a51`**
  (verified with `certutil -hashfile`, 2026-11-08)
- Size: **1,268,536,648 bytes** (≈1.27 GB JSONL, 45,808 lines)
- Every record carries `embedding_backend="real@172.20.1.53:4001"`,
  `mock` flag absent/false, 1024-d vector, full provenance fields.

### 3.5 Result

- **45,808/45,808** records embedded by the real endpoint, zero reuse,
  zero truncation, DUMP_VALIDATED green.
- Commit `9617707` — `feat: tasnim product — v0004 export adapter +
  retrieval-only embed_text (PCM-20.7D GATE 3)`.
- No mock vector in the dump (reuse guard + clean pass + marker check).

**GATE 3 = PASS.**

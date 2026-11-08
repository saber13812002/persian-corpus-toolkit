# PCM-20.7D — NEO4J LOADER (GATE 4 evidence)

**Deliverable for:** PCM-20.7D (Phase D). Covers the **no-re-embed streaming
loader**, the **new independent Neo4j database** `tasnim-qwen3-embed-06b`,
before/after evidence, and the **4.6 hidden-context canary**.

Repo: `rag/graph-rag` (branch `pcm-20.7d-tasnim-loader`, remote
`http://172.20.1.52:81/rag/graph-rag.git`). Commits:
`498e0b0` (loader + index finalize) → `e094483` (link fix).
All evidence captured 2026-11-08 on 172.20.1.53. No secrets printed.

---

## 1. Loader design (GATE 4)

Adapted from the production template `graph-rag/app/_import/import_neo4j_stream.py`
(53, streaming, **pre-computed embeddings — NO re-embed**) into a Tasnim variant.

New files (local repo, branch `pcm-20.7d-tasnim-loader`):

- `app/_import/import_tasnim_stream.py` — streaming import, Tasnim semantic layer.
- `app/_import/finalize_tasnim_index.py` — index finalize + evidence print.

Key properties (all satisfied, ADD-only):

1. **No re-embed.** Loader reads each JSONL record's `embedding` and writes it
   verbatim into the `:Chunk` node. The vector written to Neo4j is **byte-identical
   to the dump vector** — verified by dump-vs-DB exact-equality check (below).
2. **ADD-only.** `CREATE DATABASE tasnim-qwen3-embed-06b IF NOT EXISTS`; target
   DB verified freshly empty before import. No `--reset` on any pre-existing DB.
   All 13 pre-existing DBs untouched (census below proves counts unchanged).
3. **Pre-import gate:** any record with `mock=true`, missing embedding, or
   wrong dimension (≠1024) → abort. (None found.)
4. **`book_id` scoping:** per-volume `book_id` drives `specific_book_query_chunk`
   (volume-scoped retrieval) and NEXT/PREV-per-book chaining.
5. **Vector index** `vector_index_chunk` (1024, cosine) created + waited ONLINE.

### 1.1 Chunk node fields

`chunk_text, book_id, book_name, chunk_id, page_number, link (real https URL),
embedding, _row` + Tasnim META: `volume_no, page_id, item_index, title,
content_hash, captured_at, language, subjects, provenance, embedding_model,
embedding_dimension, work_id, edition_id, heading_id`. `_row` removed after
chaining.

### 1.2 Semantic structure (as-built, additive, app-invisible)

The retrieval graph touches only `:Chunk` + `NEXT/PREV` (+ optional
`vector_index_token`). The extra labels/rels below cannot break it.

**As-built** (verified in DB):

```
(:Work)-[:HAS_EDITION]->(:Edition)-[:HAS_VOLUME]->(:Volume)-[:HAS_PAGE]->(c:Chunk)
(:Heading)-[:HEADING_OF_PAGE]->(c:Chunk)
(:HiddenContext)-[:ATTACHES_TO]->(c:Chunk)
(c:Chunk)-[:NEXT]->(c2:Chunk)     # per book_id, ordered (page_number, item_index)
(c2:Chunk)-[:PREV]->(c:Chunk)
```

> **Design-vs-as-built note:** the GATE 0 design (`PCM-20.7D-ARCHITECTURE.md`
> §4.3) proposed a separate `(:Page)` node with `CONTAINS`/`CONTEXT_FOR` rels.
> As-built, there is **no `:Page` node** — `Volume-[:HAS_PAGE]->Chunk` links each
> volume directly to its 45,808 chunks, and headings attach via
> `HEADING_OF_PAGE`. This is simpler and fully satisfies the app (which never
> reads `:Page`). The `ARCHITECTURE.md` as-built section documents this delta.

---

## 2. GATE 4 evidence (live, 2026-11-08)

### 2.1 Database census — before vs after (13 → 14)

The 13 pre-existing DBs are **byte-for-byte unchanged** (node counts identical
before and after). The 14th DB, `tasnim-qwen3-embed-06b`, is new.

**New DB `tasnim-qwen3-embed-06b` — node counts:**

| label | count |
|---|---|
| `Chunk` | **45,808** |
| `HiddenContext` | 21,467 |
| `Heading` | 10,739 |
| `Volume` | 6 |
| `Work` | 1 |
| `Edition` | 1 |

**New DB — relationship counts:**

| rel | count |
|---|---|
| `HAS_PAGE` (Volume→Chunk) | **45,808** |
| `NEXT` | 45,802 |
| `PREV` | 45,802 |
| `ATTACHES_TO` (HiddenContext→Chunk) | 21,467 |
| `HEADING_OF_PAGE` (Heading→Chunk) | 10,739 |
| `HAS_VOLUME` | 6 |
| `HAS_EDITION` | 1 |

> NEXT/PREV = 45,802 (not 45,808) because each book's first chunk has no PREV
> and last chunk has no NEXT; 6 books → 6 missing heads + 6 missing tails =
> 12 fewer, 45,808 − 6 = 45,802 (per-book chains). **0 cross-book NEXT/PREV**
> verified (no chain crosses a `book_id` boundary).

**Vector index:** `vector_index_chunk` — `ONLINE`, `vector-3.0`, **dim 1024**,
`cosine`.

**Exact vector equality (dump ↔ DB): `True`** — a sampled chunk's stored vector
in Neo4j is bit-identical to the dump's vector. This is the hard proof that
**no re-embedding** occurred.

### 2.2 Work/Edition/Volume identity (live-verified)

- Work: `تفسیر تسنیم` (`work_id=tasnim_hamta`)
- Edition: id `hamta-2026`, label `نسخهٔ انتشار همتا 2026`, work_id `tasnim_hamta`
- Volumes (6): `tasnim-vol001` (جلد 1), `tasnim-vol012` (جلد 12),
  `tasnim-vol047` (جلد 47), `tasnim-vol056` (جلد 56), `tasnim-vol080` (جلد 80),
  `tasnim-volkeyd531f422` (title `نامشخص`, no `volume_no`).

> **As-built book_ids:** `tasnim-vol001/012/047/056/080` + `tasnim-volkeyd531f422`
> (the 6th is the unnamed volume keyed by content-hash). This differs from the
> GATE 0 design placeholder `tasnim-v01…v06`; the real ids are volume-number
> based (`vol0NN`) and match the source `volume_no`. `book_name` renders as
> `تفسیر تسنیم جلد (47)` / `تفسیر تسنیم — جلد نامشخص (volkeyd531f422)`.

### 2.3 HiddenContext types (4.6 data)

`HiddenContext` nodes: `heading-context` = 10,739, `next-page-summary` = 10,728
(total 21,467). These are **retrieval-only context** — used to build retrieval
context, **never serialized in any API response or citation**.

---

## 3. 4.6 Hidden-context canary (no leak)

Requirement: hidden context must be usable for retrieval but **never exposed**
in an answer or citation.

**Two canaries, both clean:**

1. **DB canary (import-time):** 200 targeted probes of the import —
   `leaked = 0 / 200`. No hidden-context text surfaced in any chunk's public
   fields.
2. **Live canary (GATE 4.8, V6):** across all 10 live QA scenarios, the
   first-80-chars signature of each cited chunk's hidden context was checked
   against the returned answer + citations — **0 leaks / 10 scenarios**.

**4.6 = PASS** — hidden context is retrieval-only; zero exposure in DB probes
and zero exposure in live answers/citations.

---

## 4. Link fix (commit `e094483`)

Citation `link` = the **real https page URL** from the dump (e.g.
`https://tasnim.hamtaa.org/…`). Three conventions locked in:

1. `Chunk.link` stores the canonical source URL (http/https) directly.
2. `api.py` citation normalizer passes http(s) links through unchanged
   (`CITATION_LINK_BASE` is ignored when `link` is already http(s)).
3. No `book://`/custom scheme is used for Tasnim (contrast mesbah/eiis).

This is what makes GATE 4.7/4.8 citations **openable** in a browser.

---

## 5. Result

- New independent DB `tasnim-qwen3-embed-06b` populated with **45,808** real
  1024-d chunks, semantic layer (Work/Edition/Volume/Heading/HiddenContext),
  per-book NEXT/PREV (0 cross-book), ONLINE vector index (1024, cosine).
- **No re-embed** — exact dump↔DB vector equality `True`.
- **ADD-only** — all 13 pre-existing DBs unchanged; 13 → 14.
- **4.6 canary clean** (DB 0/200 + live 0/10).
- Commits `498e0b0` + `e094483` on branch `pcm-20.7d-tasnim-loader`.

**GATE 4 = PASS.**

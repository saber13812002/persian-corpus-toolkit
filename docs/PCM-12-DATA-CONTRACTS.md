# PCM-12-DATA-CONTRACTS — قرارداد داده‌ها، APIها و Master Prompt

- تاریخ: 1405/08/03 (2026-10-24)
- همه schemaها **طراحی برای پیاده‌سازی additive در V0.1+** هستند — در PCM-12 اجرا نمی‌شوند.
- قواعد: SQL پارامتری‌شده · `ORDER BY` فقط whitelist · `LIMIT/OFFSET` صفحه‌بندی · خروج DOM با `escHtml` · secret هیچ‌جا در کد/DB/Git/گزارش.

---

## ۱. مدل داده SQLite (Knowledge Registry + Factory State)

### 1.1 شناسه‌ها (4 سطح، جدا)

```sql
works(
  work_id TEXT PRIMARY KEY,        -- 'w-<sha8>' deterministic از (title_norm, author_norm)
  title TEXT NOT NULL,
  author TEXT,                      -- NULL مجاز + reason
  subject_terms TEXT,               -- JSON array (controlled + free)
  language TEXT DEFAULT 'fa',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
)
UNIQUE-ish guard: (title, author) normalized → همان work (upsert)

editions(
  edition_id TEXT PRIMARY KEY,      -- 'e-<sha8>'
  work_id TEXT NOT NULL REFERENCES works(work_id),
  publisher TEXT,
  publish_year TEXT,                -- TEXT (شمسی/میلادی — نگه‌داشتن اوریجینال)
  edition_note TEXT,                -- 'چاپ دوم' و…
  source_url TEXT,                  -- URL صفحه کتاب در سایت منبع (ثبات: S1-Q5)
  source_site TEXT,                 -- 'kaemiyeh' | 'manual' | …
  license_json TEXT,                -- {terms, snapshot_url, retrieved_at, rights_ok: bool}
  created_at TEXT NOT NULL
)

volumes(
  volume_id TEXT PRIMARY KEY,       -- 'v-<sha8>'
  edition_id TEXT NOT NULL REFERENCES editions(edition_id),
  volume_no INTEGER,                -- NULL اگر در کتاب مشخص نباشد (حدس ممنوع)
  volume_title TEXT,
  volume_source TEXT,               -- 'book-frontmatter' | 'filename' | 'absent'
  created_at TEXT NOT NULL
)

files(
  file_id TEXT PRIMARY KEY,         -- 'f-<sha8>'
  volume_id TEXT REFERENCES volumes(volume_id),
  edition_id TEXT REFERENCES editions(edition_id),  -- برای فایل بدون volume روشن
  work_id TEXT REFERENCES works(work_id),
  format TEXT,                      -- docx | doc | odt
  path TEXT NOT NULL,               -- corpus/books/<work>/<edition>/vol<N>/<file>
  size_bytes INTEGER,
  sha256 TEXT NOT NULL,
  download_status TEXT,             -- none(manual) | done | partial | failed
  download_attempts INTEGER DEFAULT 0,
  download_url TEXT,
  copyright_json TEXT,              -- همان license با timestamp دانلود
  processing_status TEXT DEFAULT 'new',  -- new|queued|processing|done|failed|manual_review
  quality_score REAL,               -- 0..1 از stage 8
  created_at TEXT NOT NULL
)
CREATE UNIQUE INDEX idx_files_sha256 ON files(sha256);
```

### 1.2 Processing state

```sql
processing_runs(
  run_id TEXT PRIMARY KEY,
  file_id TEXT NOT NULL REFERENCES files(file_id),
  norm_version TEXT,                -- 'n-1'
  chunking_version TEXT,            -- 'c-1'
  prompt_version TEXT,              -- 'mp-1' (stage 9) یا NULL
  model_name TEXT, model_provider TEXT,
  tokens_in INTEGER, tokens_out INTEGER, cost REAL,
  status TEXT,                      -- running|done|failed
  error_code TEXT, error_detail TEXT,
  started_at TEXT, finished_at TEXT
)

book_stage_state(                   -- checkpoint برای resume (ARCHITECTURE §3.3)
  file_id TEXT NOT NULL,
  stage INTEGER NOT NULL,           -- 1..11
  status TEXT,                      -- pending|running|done|failed
  output_path TEXT,
  output_sha256 TEXT,
  duration_ms INTEGER,
  tokens_in INTEGER, tokens_out INTEGER, cost REAL,
  updated_at TEXT,
  PRIMARY KEY (file_id, stage)
)
```

### 1.3 Queue (گزینه A)

```sql
book_queue_jobs(
  job_id INTEGER PRIMARY KEY AUTOINCREMENT,
  job_key TEXT NOT NULL UNIQUE,     -- sha256(file_id||stage||norm_v||chunk_v)
  file_id TEXT NOT NULL,
  stage INTEGER NOT NULL,           -- stage هدف (یا 'all')
  status TEXT NOT NULL,             -- pending|running|done|failed|dlq|cancelled
  priority INTEGER DEFAULT 0,
  attempts INTEGER DEFAULT 0,
  max_attempts INTEGER DEFAULT 3,
  lease_token TEXT, lease_expires_at TEXT,
  error_code TEXT, error_detail TEXT,
  created_at TEXT, updated_at TEXT, started_at TEXT, finished_at TEXT
)
CREATE INDEX idx_queue_claim ON book_queue_jobs(status, priority DESC, created_at);

queue_dlq(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  job_key TEXT NOT NULL,
  reason TEXT NOT NULL,
  payload_json TEXT,
  created_at TEXT, resolved_at TEXT
)
```

### 1.4 Collections / Index versions

```sql
collections(
  collection_id TEXT PRIMARY KEY,   -- 'c-<sha8>'
  name TEXT NOT NULL, description TEXT,
  subject_terms TEXT,               -- JSON
  created_at TEXT, updated_at TEXT
)
collection_members(
  collection_id TEXT NOT NULL,
  edition_id TEXT NOT NULL,
  added_at TEXT,
  PRIMARY KEY (collection_id, edition_id)
)
index_versions(
  iv_id TEXT PRIMARY KEY,           -- 'iv-1'
  es_index TEXT, es_alias TEXT,
  mapping_version TEXT,
  embedding_model TEXT, embedding_dim INTEGER,
  chunking_version TEXT, norm_version TEXT,
  chunk_count INTEGER,
  collections_json TEXT,            -- collection_ids تحت این index
  status TEXT,                      -- active|superseded
  created_at TEXT
)
```

### 1.5 RAG Registry + LiteLLM usage

```sql
rag_registrations(
  rag_id TEXT PRIMARY KEY,          -- 'pct-rag-1'
  name TEXT NOT NULL, description TEXT,
  kind TEXT,                        -- 'pct-internal' | 'external'
  knowledge_collection_ids TEXT,    -- JSON
  subject_domains TEXT,             -- JSON
  capabilities_json TEXT,           -- {bm25, vector, rerank, metadata_filter, citation}
  public_url TEXT, management_url TEXT, api_endpoint TEXT,
  litellm_enabled INTEGER DEFAULT 0, litellm_model TEXT,
  access_policy TEXT DEFAULT 'auth',-- open|auth|keys
  budget_tokens_day INTEGER,
  active INTEGER DEFAULT 1,
  created_at TEXT, updated_at TEXT
)
rag_semantic_profiles(
  rag_id TEXT NOT NULL,
  version INTEGER NOT NULL,         -- 1,2,3…
  scope_description TEXT,
  intended_use TEXT,
  exclusions TEXT,
  freshness TEXT,                   -- 'live' | 'static-<date>'
  cost_tier TEXT, latency_tier TEXT,
  updated_at TEXT, updated_by TEXT,
  PRIMARY KEY (rag_id, version)
)
registry_health(
  rag_id TEXT NOT NULL,
  last_check_at TEXT, status TEXT,  -- ok|degraded|down
  p95_latency_ms INTEGER, error_rate REAL,
  PRIMARY KEY (rag_id)
)
llm_calls(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  purpose TEXT,                     -- embedding|enrichment|rerank|answer|research
  rag_id TEXT, research_id TEXT,
  model TEXT, provider TEXT,
  tokens_in INTEGER, tokens_out INTEGER,
  latency_ms INTEGER, status TEXT,  -- ok|error|timeout
  cost REAL,
  created_at TEXT
)
```

### 1.6 Persistent Research

```sql
researches(
  research_id TEXT PRIMARY KEY,     -- 'r-<sha8>'
  user_id TEXT NOT NULL,
  main_question TEXT NOT NULL,
  subquestions_json TEXT,
  collection_ids TEXT,
  sources_searched_json TEXT,       -- [{source_id, query_hash, ts}]
  evidence_json TEXT,               -- [{claim, citations[], status}]
  open_gaps_json TEXT,
  last_search_at TEXT, next_run_at TEXT,
  findings_version INTEGER DEFAULT 0,
  delivery_status TEXT DEFAULT 'none',  -- none|pending|delivered|failed|suppressed
  delivery_channel TEXT,            -- email|bale|none
  consent_json TEXT,                -- {granted: bool, ts, scope, channel}
  unsubscribe_at TEXT, paused INTEGER DEFAULT 0,
  created_at TEXT, updated_at TEXT
)
research_runs(
  run_id TEXT PRIMARY KEY,
  research_id TEXT NOT NULL,
  started_at TEXT, finished_at TEXT,
  new_sources INTEGER, new_findings INTEGER,
  changes_json TEXT,                -- فقط تغییرات معنادار
  status TEXT,                      -- ok|no_change|error
  suppressed_reason TEXT
)
CREATE UNIQUE INDEX idx_research_delivery
  ON researches(research_id, findings_version);   -- anti-duplicate delivery
```

---

## ۲. قرارداد خروجی‌های Factory (JSONL)

### 2.1 raw (block-level)
```jsonl
{"file_id":"f-…","block_index":0,"type":"heading|paragraph|table|footnote|endnote|pagebreak|image",
 "text":"…","style":"Heading1|…","ref_id":"fn-3","table_rows":[["…","…"]],"page":null}
```
- `page` فقط اگر معتبر از docx (وگرنه null — **حدس ممنوع**)
- `footnote`: body در `text`، محل anchor در block اصلی با `ref_id`

### 2.2 normalized
```jsonl
{"file_id":"f-…","block_index":0,"norm_version":"n-1","text":"…"}
```
- `norm_version` ثبت‌شده؛ هر norm جدید = نسخه جدید (نسخه‌های قبلی حذف نمی‌شوند)

### 2.3 enriched (metadata کتاب/فصل — مطابق `enrichment_schema_v1` §4)

### 2.4 chunks (index-ready)
```jsonl
{"chunk_id":"kw_w-…_e-…_v1_00012","work_id":"w-…","edition_id":"e-…","volume":1,
 "chapter":"فصل سوم","section":"…",
 "text":"…","norm_version":"n-1","chunking_version":"c-1",
 "source_ref":{"chapter":"…","section":"…","page":null,"paragraph_range":[41,48]},
 "content_hash":"sha256:…","embedding_model":"bge-m3"}
```
- `chunk_id` deterministic: `kw_<work>_<edition>_<vol>_<seq6>` → idempotent bulk
- chunk v1 (c-1): target 500 token، overlap 50 token، شکستن فقط در مرز paragraph/section

---

## ۳. ES Mapping (test index — V0.2)

```json
{
  "mappings": {
    "properties": {
      "chunk_id":       {"type": "keyword"},
      "work_id":        {"type": "keyword"},
      "edition_id":     {"type": "keyword"},
      "volume":         {"type": "integer"},
      "collection_ids": {"type": "keyword"},
      "chapter":        {"type": "text", "analyzer": "persian"},
      "section":        {"type": "text", "analyzer": "persian"},
      "text":           {"type": "text", "analyzer": "persian"},
      "text.keyword":   {"type": "keyword", "ignore_above": 512},
      "source_ref": {
        "properties": {
          "chapter": {"type": "keyword"},
          "section": {"type": "keyword"},
          "page":    {"type": "integer"},
          "paragraph_range": {"type": "integer"}
        }
      },
      "content_hash":    {"type": "keyword"},
      "norm_version":    {"type": "keyword"},
      "chunking_version":{"type": "keyword"},
      "embedding_model": {"type": "keyword"},
      "embedding": {
        "type": "dense_vector", "dims": 1024, "index": true,
        "similarity": "cosine"
      },
      "index_version":   {"type": "keyword"},
      "created_at":      {"type": "date"}
    }
  },
  "settings": {
    "analysis": {
      "analyzer": {
        "persian": {
          "type": "custom",
          "tokenizer": "standard",
          "filter": ["lowercase", "persian_normalizer"]
        }
      }
    }
  }
}
```
- analyzer `persian_normalizer`: custom char_filter (نیم‌فاصله، زیرمختصات) — اگر plugin فارسی موجود نبود، char_filter دستی؛ **test در V0.2** قبل از reindex انبوه
- dims مطابق مدل انتخاب‌شده (bge-m3 = 1024؛ Qwen3-Embedding-0.6B = 1024؛ 4B = 2560 — در V0.6 تنظیم)
- `text.keyword` برای exact-match (عناوین/اصطلاحات)

### 3.1 استراتژی index/alias
- `pct_test_v1` → alias `pct_test` (V0.2..V0.4)
- `pct_prod_v1` → alias `pct_prod` (V1.0+ بعد از تأیید)
- reindex: index جدید ساخته → bulk → **alias atomic switch** → index قدیمی `superseded` (حذف بعد از 7 روز)

---

## ۴. JSON Schema — `enrichment_schema_v1` (خروجی Master Prompt)

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "enrichment_schema_v1",
  "type": "object",
  "additionalProperties": false,
  "required": ["schema_version", "chapter_id", "summary", "topics", "key_terms", "confidence_overall"],
  "properties": {
    "schema_version": {"const": "v1"},
    "chapter_id": {"type": "string", "description": "از ورودی — تکرار بدون تغییر"},
    "chapter_title": {
      "type": ["string", "null"],
      "description": "فقط اگر صریح در متن ذکر شد؛ وگرنه null + flag"
    },
    "summary": {
      "type": "string",
      "maxLength": 1500,
      "description": "خلاصه 3-6 جمله، فقط از محتوای همین بخش"
    },
    "topics": {
      "type": "array", "maxItems": 8,
      "items": {"type": "string", "maxLength": 60},
      "description": "موضوعات اصلی؛ هرکدام باید در متن ریشه داشته باشد"
    },
    "key_terms": {
      "type": "array", "maxItems": 15,
      "items": {
        "type": "object",
        "required": ["term", "evidence"],
        "properties": {
          "term": {"type": "string"},
          "evidence": {"type": "string", "description": "quote کوتاه از متن (≤ 200 char)"},
          "confidence": {"type": "number", "minimum": 0, "maximum": 1}
        }
      }
    },
    "entities": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["name", "type", "evidence"],
        "properties": {
          "name": {"type": "string"},
          "type": {"enum": ["person", "place", "work", "institution", "date", "other"]},
          "evidence": {"type": "string"},
          "confidence": {"type": "number", "minimum": 0, "maximum": 1}
        }
      }
    },
    "quotes": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["text", "attribution"],
        "properties": {
          "text": {"type": "string", "maxLength": 2000},
          "attribution": {"type": ["string", "null"], "description": "مربوط‌کننده صریح در متن؛ وگرنه null"},
          "verbatim": {"const": true}
        }
      },
      "description": "فقط اگر در متن واقعاً نقل‌قول جداگانه/موردنقل وجود دارد؛ وگرنه []"
    },
    "references_cited": {
      "type": "array",
      "items": {"type": "string"},
      "description": "ارجاع‌هایی که داخل همین بخش به آن‌ها اشاره شده (متن اوریجینال)"
    },
    "not_found": {
      "type": "array",
      "items": {"type": "string", "enum": ["chapter_title", "author", "publisher", "edition_info", "page_numbers", "volume_info"]},
      "description": "فیلدهایی که در ورودی نبودند (ممنوعیت حدس)"
    },
    "uncertain": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["field", "reason"],
        "properties": {
          "field": {"type": "string"},
          "value": {"type": ["string", "null"]},
          "reason": {"type": "string"},
          "confidence": {"type": "number", "minimum": 0, "maximum": 1}
        }
      }
    },
    "confidence_overall": {"type": "number", "minimum": 0, "maximum": 1}
  }
}
```

**قواعد اعتبارسنجی خروجی LLM (server-side، stage 9):**
1. validate با schema (نسخه‌شده) — خطا → retry 1 بار → `status=error` (کتاب ادامه می‌یابد)
2. `summary`/`topics` بدون `evidence` در `key_terms` → `confidence_overall` cap 0.5
3. هر `confidence < 0.7` → به Knowledge Registry با flag `uncertain` (badge «نیاز به بررسی»)
4. `quotes[].text` باید substring از متن ورودی باشد (fuzzy ≤ 2%) — وگرنه quote رد می‌شود (ضد-hallucination)
5. ثبت: prompt_version, model, tokens, cost در `processing_runs` + `llm_calls`

---

## ۵. Master Prompt — draft `mp-1` (فقط draft — در production اجرا نمی‌شود)

```text
# SYSTEM (mp-1)
تو یک استخراج‌کننده داده هستی، نه نویسنده. وظیفه‌ی تو فقط استخراج اطلاعات از
متنِ داده‌شده است.

قواعد مطلق:
1. فقط از متن ورودی استفاده کن. از دانش عمومی، حدس، یا حافظه استفاده نکن.
2. هر اطلاعاتی که در متن صریح نیست → مقدار null و نام فیلد در آرایه‌ی
   not_found. هرگز عنوان، نویسنده، ناشر، سال، شماره صفحه، یا منبع را
   اختراع نکن.
3. خروجی فقط یک JSON معتبر مطابق schema باشد (enrichment_schema_v1).
   هیچ متن خارج از JSON، هیچ توضیح، هیچ markdown.
4. برای هر فیلدِ قابل‌استدلال، quote کوتاه از متن (evidence) بیاور.
   quote باید عیناً (verbatim) در متن ورودی موجود باشد.
5. اگر مطمئن نیستی، confidence را پایین بده (زیر 0.7) و فیلد را در
   آرایه‌ی uncertain با دلیل بیاور.
6. نقل‌قول (quotes) فقط اگر در متن واقعاً جملات موردنقل/جداگانه با
   مربوط‌کننده وجود دارد؛ وگرنه آرایه‌ی quotes خالی بگذار.
7. خلاصه (summary) فقط خلاصه‌ی همین بخش است — 3 تا 6 جمله فارسی.
8. اگر ورودی خراب/ناخوانا/غیرفارسی غالب باشد، همه فیلدها null و
   confidence_overall = 0 و در uncertain توضیح بده.

# INPUT (user message)
{chapter_id}: {chapter_id}
{text}:
<<<
{chapter_text}
>>>

# OUTPUT
JSON واحد مطابق enrichment_schema_v1.
```

**نکات عملیاتی (V0.1 test، بعد از S1-Q8):**
- اجرای نمونه: روی front matter + یک فصل از یک کتاب واقعی (نه production)
- budget: max 4K token ورودی per call؛ chunk بزرگ‌تر → 2 call (هرکدام ثبت)
- temperature 0.1 (extractive)
- مقایسه 2 مدل (qwen38 vs deepseek-chat) در یک eval کوچک قبل از انتخاب (V0.6)
- **نسخه‌بندی**: هر تغییر prompt → `mp-N` جدید؛ خروجی‌های قدیمی با `mp-(N-1)` باقی می‌مانند

---

## ۶. API Contracts

### 6.1 الگوی عمومی (همان `dashboard_api.py`)
- خواندنی‌های جدید: `@require_auth` + pagination (`page`, `page_size` ≤ 100) + sort whitelist
- نوشتنی‌های جدید: `@require_auth` + body JSON + 4xx/5xx استاندارد + audit row
- همه endpointهای crawl موجود (اکستنشن) **دست‌نخورده**

### 6.2 Factory (V0.1+)
```
POST /api/factory/files
  body: {work_ref?: {title, author}, edition_ref?: {...}, volume_no?, license?: {...},
         file: multipart}   OR {server_path: "…"} (فقط داخلی)
  → 201 {file_id, work_id, edition_id, volume_id, status: "new"}
  → 409 {error: "duplicate_sha256", existing_file_id}

GET  /api/factory/files/<file_id>/status
  → {file_id, processing_status,
     stages: [{stage: 1..11, name, status, duration_ms, output_sha256?}],
     run: {run_id, norm_version, chunking_version, error?}}

GET  /api/factory/files/<file_id>/outputs
  → {raw: {path, lines, sha256}, normalized: {…}, enriched: {…}|null,
     quality: {score, report}}

POST /api/factory/queue          (V0.3)
  body: {file_ids: [...], stage?: int|"all", priority?: 0..10}
  → 202 {enqueued: N, skipped_duplicate: M}

POST /api/factory/index          (V0.2)
  body: {file_ids|edition_ids: [...], iv_id?: "auto"}
  → 202 {iv_id, es_index, chunks: N}

GET  /api/factory/search?q=…&mode=hybrid|bm25|vector&limit=8&collection_id=…
  → {results: [{chunk_id, score, text,
                citation: {work, edition, volume, chapter, section, page, quote}}],
     took_ms, mode}
```

### 6.3 Knowledge Registry (V0.5)
```
GET /api/registry/knowledge/works?subject=…&q=…&page=&sort=created_at
GET /api/registry/knowledge/works/<work_id>          (با editions + volumes + files)
GET /api/registry/knowledge/editions/<edition_id>
GET /api/registry/knowledge/collections
GET /api/registry/knowledge/collections/<id>          (با members + counts)
GET /api/registry/knowledge/subjects
```
هر response: `{items: […], total, page, page_size}` + فیلدهای RAG-readiness
(`searchable, index_version, embedding_model, last_indexed_at, license_ok, quality_pass`).

### 6.4 RAG Registry (V0.5)
```
GET /api/registry/rags
  → {items: [{rag_id, name, description, kind, collections, subject_domains,
              capabilities, public_url, management_url, access_policy,
              health: {status, p95_latency_ms, error_rate},
              stats: {books, queries_30d, queries_today, users_30d},
              last_activity_at, last_index_update_at,
              profile_version}]}
GET /api/registry/rags/<rag_id>/profile?version=N    (semantic profile + diff with prev)
```

### 6.5 RAG ask (V0.4) — contract پاسخ (تمام RAGها)
```
POST /api/rag/<rag_id>/ask
  body: {question: str, limit?: 3..20, filters?: {collection_id?, edition_id?, volume?},
         include_trace?: bool}

  200 {
    "answer": "…",
    "citations": [
      {"chunk_id": "…", "work_id": "…", "edition_id": "…", "volume": 1,
       "chapter": "…", "section": "…", "page": null,
       "quote": "…(≤ 300 char)", "score": 0.87}
    ],
    "retrieved_sources": [{"chunk_id": "…", "score": 0.87, "collection_id": "…"}],
    "collection_ids": ["c-…"],
    "confidence": 0.81,
    "evidence_sufficiency": "sufficient|partial|insufficient",
    "retrieval_trace": {"bm25_top": 10, "vector_top": 10, "fused": 20,
                        "reranked": 8, "filtered_out": 12,
                        "retrieval_ms": 210, "generation_ms": 3200},
    "versions": {"model": "qwen38", "index_version": "iv-1",
                 "prompt_version": "mp-1", "rag_profile_version": 2,
                 "embedding_model": "bge-m3"},
    "litellm_usage": {"tokens_in": 1200, "tokens_out": 300, "cost": 0.004},
    "degraded": false
  }
  422 {error: "rag_inactive"} · 429 {error: "rate_limited"} · 503 {error: "litellm_unavailable", degraded: true}
       (503 فقط وقتی generation لازم است؛ retrieval-only در این حالت 200 + degraded=true)
```

### 6.6 SuperRAG (V0.7)
```
POST /api/superrag/ask
  body: {question, max_rags?: ≤3, max_latency_ms?: 10000, budget_tokens?: N}
  200 {
    "answer": "…",
    "sections": {
      "answer": "…",
      "evidence": [{"claim": "…", "citations": […], "rag_id": "…"}],
      "contradictions": [{"topic": "…", "side_a": {claim, citations}, "side_b": {…}}],
      "gaps": ["…(خلاءهای شواهد، صریح)"]
    },
    "rag_runs": [{"rag_id": "…", "took_ms": 3100, "sufficiency": "sufficient",
                  "tokens": 1500}],
    "versions": {"orchestrator": "sr-1", "rag_profiles": {"pct-rag-1": 2}},
    "trace": {"subquestions": […], "candidates": […], "selected": […], "rejected": [{"rag_id", "reason"}]}
  }
```

### 6.7 Research (V0.8)
```
POST /api/research
  body: {main_question, subquestions?, collection_ids, channel: "email"|"bale",
         address, consent: {granted: true, ts}}
  → 201 {research_id}          (consent=false → 400)
GET  /api/research/<id>       (state کامل)
POST /api/research/<id>/pause | /resume | /unsubscribe
GET  /api/dashboard/research  (فهرست + delivery status — auth)
```

### 6.8 Metrics (V1.0)
```
GET /metrics   (Prometheus text format — بدون auth در شبکه داخلی)
pct_books_total{status=…}
pct_queue_depth{stage=…}
pct_worker_active
pct_download_failures_total
pct_processing_duration_seconds{stage=…}   (histogram)
pct_chunks_indexed{collection=…}
pct_rag_queries_total{rag=…, status=…}
pct_rag_error_total{rag=…, code=…}
pct_llm_tokens_total{model=…, type=in|out}
pct_research_runs_total{status=…}
pct_research_deliveries_total{channel=…, status=…}
```

---

## ۷. قرارداد یکپارچه‌سازی با RAGهای مستقل (محدوده AGENTS.md §1)

**اصل:** PCT **تغییر** در RAGهای مستقل نمی‌دهد؛ فقط contract مشترک تعریف می‌کند و هر owner می‌تواند اختیاری پیاده کند.

1. **Contract ورودی**: هر RAG خارجی که بخواهد در RAG Registry ثبت شود، باید `POST /ask` با **contract §6.5** (حداقل: `answer`, `citations`, `evidence_sufficiency`, `versions.rag_profile_version`) ارائه دهد.
2. **Contract خروجی (برای ما)**: RAG Registry entry با `kind: "external"` + `api_endpoint` + `access_policy: "keys"` (API key در `.env` سرور — هرگز در Git/گزارش).
3. **Data exchange**: اگر RAG خارجی بخواهد داده‌ی ما (chunks) مصرف کند → **فقط** از طریق JSONL/Parquet export (`index_versions` row) یا alias خواندنی ES — هرگز دسترسی مستقیم به SQLite.
4. **Prior art سازمانی**: `automated/export-sql-chromadb` (mesbahyazdi) الگوی خروجی صفحه‌به‌صفحه موجود سازمان است — contract ما (chunk JSON با content_hash + source_ref) سوپرست سازگار آن است و می‌تواند بعداً (با تصمیم owner) جایگزین/مکمل شود.
5. **LiteLLM**: مصرف مشترک از gateway موجود؛ هر RAG کلید/باجت خود را دارد؛ **بدون تغییر config LiteLLM**.

---

## ۸. قواعد عمومی داده
- **IDها deterministic** (sha8 از فیلدهای هویتی) → upsert idempotent، بدون دوباره
- **هر row زمانی‌بندی**: `created_at` (+ `updated_at` برای mutable)
- **حذف**: soft delete (`status`) — DROP ممنوع (قانون AGENTS.md)
- **عدد آمار**: فقط از شمارنده‌های واقعی (قانون §2.9) — هر gauge/dashboard باید منبع SQL/ES خود را در doc داشته باشد
- **Secret**: API key/رمز فقط در `.env` سرور (chmod 600، gitignored) + DB با scrypt (حالت رمز) — هرگز در body response/log/metric

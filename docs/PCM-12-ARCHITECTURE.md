# PCM-12-ARCHITECTURE — معماری پیشنهادی Document Processing → Knowledge → RAG

- تاریخ: 1405/08/03 (2026-10-24)
- قاعده مطلق: **بدون قطع کراول زنده** — همه APIهای نوشتاری اکستنشن دست‌نخورده می‌مانند؛ سرویس‌های موجود (backend 5055، LiteLLM، RAGهای مستقل) بدون تغییر می‌مانند.
- مبدأ طراحی: شروع با **مسیر عمودی تکی**: `یک فایل Word → JSON ساختاریافته → ES test index → جستجو → ارجاع‌دهی`.

---

## ۰. دیاگرام کلی (هدف نهایی)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                                  s52                                        │
│                                                                             │
│  [Chrome Extension] ──► [backend Flask :5055]  (PCT موجود — دست‌نخورده)      │
│                              │  (فقط: جدول‌های additive جدید + endpointها)  │
│                              ▼                                              │
│   ┌──────────────────────────────────────────────────────────────────┐      │
│   │            NEW: Book Factory (همان container backend، ماژول جدید)   │      │
│   │                                                                  │      │
│   │  Downloader ─► files/ (raw Word) ─► Queue (SQLite, durable)      │      │
│   │                                     │                            │      │
│   │  Worker 1..N (process) ◄────────────┘                            │      │
│   │   stage 1..11 → checkpoints در DB → outputs/ (raw/normalized/    │      │
│   │   enriched JSON) → Indexer → Elasticsearch                       │      │
│   └──────────────┬───────────────────────────────────┬───────────────┘      │
│                  │                                   │                      │
│                  ▼                                   ▼                      │
│   [Knowledge Registry (SQLite)]          [Elasticsearch — ES جدید PCT       │
│   books/editions/collections/…           یا سازمانی — تصمیم J]              │
│   [RAG Registry]                    chunks + vectors (dense) + BM25          │
│                  │                                                           │
│                  ▼                                                           │
│   [RAG Service PCT — V0.4+]: retrieval (BM25+vector+rerank)                  │
│        + LLM call via LiteLLM gateway (4000/4101 — بدون تغییر config)       │
│        + response contract (answer, citations, evidence, trace)             │
│                  ▲                                                           │
│   [SuperRAG Orchestrator] ── انتخاب RAG از RAG Registry (V0.7)              │
│   [Persistent Research Engine] ── research jobs شبانه (V0.8)                │
│   [Dashboard /dashboard/ + 4 بخش جدید]                                     │
│   [Grafana :3001 — 4 داشبورد جدید روی stack موجود]                          │
└─────────────────────────────────────────────────────────────────────────────┘
محدوده دست‌نخورده: RAGها مستقل (automated/Chroma, graph-rag, moshat),
LiteLLM config, notebooklm, QA Bank, GitLab-redis
```

نکته ظرفیتی: 23Gi RAM / 10 CPU روی s52 با 9.7Gi RAM آزاد — Workerها باید محدودیت CPU/RAM صریح داشته باشند (S3) و **دیسک 100% پر** باید قبل از هر بارگذاری حل شود (AUDIT §6).

---

## S2 — Document Processing Factory

### 2.1 وضعیت موجود (ممیزی)
- هیچ parser DOC/DOCX در toolkit وجود ندارد (AUDIT #12). نزدیک‌ترین الگوها: `corpus/build_corpus.py` (تبدیل DB→JSONL) و `_map_elastic_to_item()` (norm/validate روی هر آیتم) و dedup با `content_hash()`.
- الگوی سازمانی قبلی: `book_pages` (mesbahyazdi) — کتاب/بخش/صفحه با HTML خام. Factory ما **ساختاریافته و قابل‌اتکا** است، نه HTML خام.

### 2.2 خط لوله ۱۱ مرحله‌ای

هر stage یک تابع خالص `(input_path, stage_state) -> StageOutput` است؛ خروجی هر stage به DB checkpoint می‌شود و ورودی stage بعدی از checkpoint می‌آید (نه از حافظه). این همان اصل «resume از stage امن بعدی» (S3) است.

| # | Stage | ورودی | خروجی | خطای بحرانی؟ |
|---|---|---|---|---|
| 1 | File Discovery | مسیر دانلود/فایل‌های تحویلی | `files` row (file_id, work/edition/volume ref, size, mtime, sha256) | خیر (skip اگر hash تکراری — dedup) |
| 2 | Format Detection | file bytes (magic) | `format ∈ {docx, doc, odt, pdf?}` + confidence | `.doc` → مرحله تبدیل (libreoffice headless) یا رد با دلیل |
| 3 | Validation | file | checksum ثانی، بازپذیری، حجم حد، اسکن بدافزار (اختیاری) | بله → status=failed + reason |
| 4 | Parsing | docx bytes | sequence of blocks (paragraph/heading/table/image/footnote/endnote) با index و style نام | بله |
| 5 | Structural Extraction | blocks | tree: chapters/sections/subsections، شماره جلد از محتوای کتاب (نه از نام فایل)، front/back matter detection | خیر (tree ناقص → confidence کم) |
| 6 | Metadata Extraction | front matter + blocks | bibliographic JSON (title/author/publisher/subject/edition…) با **confidence** هر فیلد؛ هر فیلد `value, source_ref, confidence` | خیر — هر فیلد می‌تواند null + reason باشد |
| 7 | Persian Normalization | text blocks | normalized text (زیرمختصات، نیم‌فاصله، تکیه، اعداد، خط‌خوردگی) — **دو نسخه**: raw و normalized جدا نگه داشته می‌شوند | خیر |
| 8 | Quality Validation | normalized | quality report: percent فارسی، طول، تکرار، خرابی OCR (اگر بود)، empty-page count، threshold pass/fail | بله → manual review queue |
| 9 | Semantic Enrichment | chapters (تکی‌تکی) | enriched metadata (summary، topics، key_terms، entity hints) **فقط با LLM طبق Master Prompt** — V0.1 بدون LLM (خروجی=null مجاز) | خیر (خطا → field=unavailable، book ادامه می‌یابد) |
| 10 | Chunking | normalized structure | chunks (سایز/overlap از policy، هر chunk با parent section ref) | خیر |
| 11 | Index Preparation | chunks + metadata | index-ready JSONL + ES bulk payload (index/version/alias) | بله → retry |

### 2.3 سه خروجی مستقل (هر کتاب)

| خروجی | محتوا | مصرف‌کننده |
|---|---|---|
| `raw` | متن دقیق‌الکلمه از فایل (با footnotes/tables جدا) | ممیزی، reprocess بدون دانلود مجدد |
| `normalized` | متن بعد از normalization v-N (نسخه‌شده) | جستجو، chunking |
| `enriched` | metadata تولیدشده LLM + confidence + prompt_version/model_version | Knowledge Registry، انتخاب RAG |

**قانون:** enriched هرگز raw/normalized را تغییر نمی‌دهد. reprocess می‌تواند فقط enriched را با prompt/model جدید بازنویسی کند.

### 2.4 Master Prompt (اصل‌ها — متن کامل در DATA-CONTRACTS §5)
- **extract-only**: فقط از متن ورودی؛ هیچ دانش عمومی؛ «اگر در متن نیست → null + `not_found`»
- **حیوان/اختراع ممنوع**: عنوان/نویسنده/شماره صفحه/منبع بدون ذکر صریح در متن → `value: null, flag: "absent"`
- خروجی فقط JSON مطابق schema نسخه‌شده (`enrichment_schema_v1`)
- هر فیلد: `{value, confidence: 0..1, evidence: "quote از متن", source: "section X / page Y"}`
- قابل اجرا روی section‌های کوچک (V0.1 روی front matter یک کتاب واقعی، نه production)
- ثبت: `prompt_version`, `model_name`, `model_provider`, `tokens_in/out`, `cost`, `error` در `processing_runs`

---

## S3 — Queue پردازش مستقل (مقایسه A/B بدون نصب جدید)

### 3.1 وضعیت موجود
`crawl_queue` (جدول SQLite، مصرف‌کننده: extension) + `_HARVEST_JOB` (یک thread in-memory). **هیچ** Celery/RabbitMQ/worker مستقل برای PCT روی s52 نیست (AUDIT #13/#14). VS Code = محیط توسعه، **نه** سرویس queue (قانون مأموریت).

### 3.2 مقایسه

| معیار | A) DB-based durable queue (SQLite در همان DB یا DB جدا) | B) Distributed queue + worker مستقل (مثلاً Redis/Broker + چند پروسه) |
|---|---|---|
| تعداد worker | 1..N پروسه در s52 (همان هاست) — کافی برای ده‌ها/صدها کتاب | بیشتر، ولی نیاز به infra |
| بدون نصب جدید؟ | **بله** (SQLite موجود است) | خیر (بروکر/worker images) |
| Retry | column `attempts` + backoff محاسبه‌شده + max → DLQ | بله (advanced) |
| DLQ | جدول `queue_dlq` (reason, payload, ts) | بله |
| Visibility/lease | `lease_token` + `lease_expires_at`؛ worker مرده → lease منقضی → job قابل‌دوباره‌شدن (reclaim) | بله (native) |
| Idempotency | `job_key` UNIQUE (hash file+stage) + `ON CONFLICT DO NOTHING` | بله (dedup broker) |
| Concurrency control | `BEGIN IMMEDIATE` + `WHERE status='pending' AND ...` (SQLite WAL) — برای 10..100 کتاب در ثانیه‌های کم: کافی | بیشتر |
| Priority (کتاب مهم) | column `priority` int در SELECT `ORDER BY priority DESC, created_at` | بله (بیشتر) |
| Resume بعد از restart | **تمام state در DB** → پس از restart، job با `status='running'` و lease منقضی → reclaim + resume از stage checkpoint | بله |
| جلوگیری از دوباره | UNIQUE job_key + file sha256 | بله |
| کنترل CPU/RAM | `worker_count` + `max_concurrent_books` در config؛ هر worker یک کتاب در stage CPU-heavy | بهتر (autoscale) |
| Monitoring | Prometheus endpoint `/metrics` + جدول `queue_metrics` | بله |
| هزینه/پیچیدگی | **کم** — یک ماژول ~400 خط در backend | بالا — image جدید، network، security، backup جدا |

**نتیجه (بر اساس حجم واقعی = کتاب‌های Word، نه هزاران job):** گزینه **A** برای V0.1..V0.6. شرط ارتقا به B: فقط اگر workerها باید روی هاست‌های جدا باشند یا job rate > ~50/ثانیه شود — در آن لحظه، `queue` interface ثابت می‌ماند و broker swap می‌شود.

### 3.3 جدول‌ها (additive، طراحی)

```sql
book_queue_jobs(
  job_id PK, job_key UNIQUE,        -- hash(file_id||stage||policy_versions)
  file_id FK, stage INT,
  status TEXT,        -- pending|running|done|failed|dlq|cancelled
  priority INT DEFAULT 0,
  attempts INT DEFAULT 0, max_attempts INT DEFAULT 3,
  lease_token, lease_expires_at,
  error_code, error_detail,
  created_at, updated_at, started_at, finished_at
)
book_stage_state(
  file_id FK, stage INT, status,    -- checkpoint هر stage
  output_path, output_sha256,       -- نتیجه stage
  duration_ms, tokens_in, tokens_out, cost,
  PRIMARY KEY (file_id, stage)
)
queue_dlq( id PK, job_key, reason, payload_json, created_at, resolved_at )
```

**کارتابل resume (قانون طلایی):** اگر worker وسط کتاب X بایستد، پس از recovery:
1. job‌های `running` با `lease_expires_at < now` → `pending` (reclaim)
2. worker `book_stage_state` را می‌خواند: stages `done` → skip (خروجی‌شان در disk با sha256)؛ اولین `pending/failed` → از همان شروع
3. stage فقط وقتی `done` می‌شود که خروجی‌اش **روی دیسک commit** شده و sha256 آن ثبت شده → بنابراین هیچ stage نیمه‌تمامی به‌عنوان done شمارده نمی‌شود.

---

## S4 — Data store و Elasticsearch

### 4.1 وضعیت واقعی ES (AUDIT #10)
- فقط `taghrir-es` 8.13.4 — **متوقف** (Exited 3 روز)، 9200 listener ندارد، volume 1.508GB (متعلق به پروژه taghrir — **دست‌نخورده**).
- **ES عملیاتی برای PCT وجود ندارد.** دو مسیر (تصمیم J2):
  - (i) container کوچک ES جدید `pct-es` (image همان 8.13.4 یا نسخه موجود در registry داخلی) با volume **جدید** و دیسک جدا — نیاز به دیسک آزاد (AUDIT §6.1 ⛔)
  - (ii) استفاده از ES سازمانی (اگر وجود دارد و مجوز داده شود) — هنوز شناسایی‌نشده → سؤال J
- **قانون:** هیچ index operation روی `taghrir-es-data` یا هر index غیر-PCT. V0.2 فقط روی **test index** `pct_test_*` با alias بدون ترافیک کاربر.

### 4.2 مفاهیم منطقی (جدا از هم، هرکدام جدول/فهرست مستقل)

| مفهوم | تعریف | کجا |
|---|---|---|
| Books Catalog | شناسه‌های Work/Edition/Volume/File + metadata | SQLite (Knowledge Registry) — **source of truth** |
| Editions | یک چاپ/ناشر/سال یک Work | SQLite |
| Collections | مجموعه منطقی کتاب‌ها برای یک RAG/موضوع | SQLite (members table) |
| Collection Membership | collection_id ↔ edition_id (با added_at) | SQLite |
| Document Chunks | قطعه‌های متن + position + hash | **ES** |
| Embeddings | بردار dense هر chunk (بسته به chunk) | **ES** (dense_vector) |
| Processing Runs | هر اجرای pipeline روی هر فایل (stageها، نسخه‌ها، cost) | SQLite |
| Index Versions | نسخه index + alias + mapping version | SQLite + ES alias |

### 4.3 فیلدهای هر chunk (mapping پیشنهادی)

```json
{
  "chunk_id":        "kw_<work_id>_<edition_id>_<vol>_<seq>",   // deterministic, idempotent
  "work_id": "w-…", "edition_id": "e-…", "collection_ids": ["c-…"],
  "volume": 1, "chapter": "…", "section": "…",
  "text": "…(normalized v-N)",
  "raw_text_ref": "file path / object ref",
  "source_ref": {"section": "…", "page": 12, "paragraph": 3},   // page فقط اگر معتبر (audit S1)
  "content_hash": "sha256(text)",
  "norm_version": "n-2", "chunking_version": "c-1",
  "embedding_model": "bge-m3", "embedding_dim": 1024,
  "index_version": "iv-1", "created_at": "…"
}
```
- `text`: analyzer فارسی (unicode +Persian stemming اگر موجود) → **BM25**
- `embedding`: dense_vector (cosine) — مدل از LiteLLM gateway (bge-m3 یا Qwen3-Embedding-4B — تصمیم بر حسب کیفیت فارسی، J4)
- IDهای deterministic → **bulk idempotent** (reindex بدون دوباره)

### 4.4 جستجوی هیبریدی
```
query → [BM25] + [kNN vector]  → reciprocal rank fusion (top-K≈50)
     → [metadata filter: collection/edition/volume] (جدا پیش از scoring)
     → [rerank: cross-encoder اگر موجود، وگرنه LLM-judge با Master Prompt-lite از LiteLLM]
     → top-N (مثلاً 8) + citation (work/edition/volume/chapter/page + source_ref)
```
هر پاسخ RAG **باید** citations را بیاورد (S6 contract). بدون citation → پاسخ «بدون مستند کافی».

### 4.5 چهار نوع خروجی/نسخه (متمایز)

| نوع | چیست | کجا | کاربرد |
|---|---|---|---|
| **ES snapshot** | snapshot باینری کلانگر ES (repository) | volume جدا + backup dir | disaster recovery خود ES |
| **JSONL/Parquet export** | خروجی logical chunks+metadata (row-based) | backup dir / سارا | تبادلم با سرویس‌های دیگر (مثلاً Chroma exporter سازمانی)، migration، ممیزی داده |
| **Corpus Version** | نام‌گذاری‌شده + content-hash‌شده‌ی مجموعه JSONL (manifest: file hashes + counts + norm/chunking versions) | مستند در Knowledge Registry | «نسخه p-1 از پیکره» — قابل‌استدلال در paper/RAG |
| **RAG Deployment Artifact** | پیکره deploy‌شده روی یک RAG (index alias + embedding model + prompt version + registry entry version) | RAG Registry | **dump نیست** — RAG با API/alias سرویس می‌شود؛ dump فقط برای backup/migration. **قانون: dump هرگز پیش‌نیاز RAG نیست** (RAG با alias زنده سرویس می‌دهد). |

---

## S5 — دو Registry مستقل

### 5.1 Knowledge Registry (source of truth داده)
سطوح:
```
Work (شناسه پایدار) ──► Edition (چاپ/ناشر/سال) ──► Volume ──► File (با checksum)
Edition ──► Collections (چند-به-چند)
Work ──► Subjects (controlled vocab + free text)
Edition/Volume ──► doc/chunk counts (از Index Versions)
Edition ──► data quality score (از stage 8 report)
File ──► license/copyright metadata (source, terms, download_ts)
```
فیلدهای RAG-readiness: `searchable (bool)`, `index_version`, `embedding_model`, `last_indexed_at`, `license_ok (bool)`, `quality_pass (bool)`.
API خواندنی: `GET /api/registry/knowledge/works|editions|collections|subjects` (پشت همان auth داشبورد + بعداً API key برای سرویس‌های دیگر).

### 5.2 RAG Registry
هر entry:
```
rag_id, name, description,
knowledge_collection_ids[], subject_domains[],
capabilities: {bm25, vector, rerank, metadata_filter, citation},
public_url, management_url, api_endpoint,
litellm: {enabled, model, budget},
access_policy: {open|auth|keys},
health: {status, last_check, p95_latency, error_rate},
stats: {books, users_30d, queries_30d, queries_today},
last_activity_at, last_index_update_at,
semantic_profile_version + profile:
  {version, scope_description, intended_use, exclusions,
   freshness, cost_tier, latency_tier, updated_at, updated_by}
```
**قانون انتخاب RAG (S7):** فقط بر اساس `semantic_profile` + capabilities + health + access — هرگز حدس زدن روی زبان/عنوان.

### 5.3 سه گزینه سرویس‌دهی RAG (مقایسه)

| معیار | 1) هر RAG = Docker service جدا | 2) engine مشترک + RAGهای منطقی (collection/alias جدا) | 3) هیبرید: سبک‌ها مشترک، سنگین جدا |
|---|---|---|---|
| RAM s52 (آزاد 9.7Gi) | هر service ≥ 1Gi → 5 RAG ≈ 5-10Gi ⚠️ | 1 engine ≈ 1-2Gi + ES مشترک | قابل کنترل |
| هزینه | بالا (image، restart، backup ×N) | کم | متوسط |
| انزوا | کامل (crash/upgrade جدا) | منطقی (فشل engine = همه) | نیمه |
| نگهداری | N بار | 1 بار | 1+N سنگین |
| مقیاس | مستقل | محدود به engine تکی | متعادل |
| پیچیدگی deploy | بالا | کم | متوسط |

**پیشنهاد:** گزینه **2** برای شروع (1 engine PCT + collection/alias جدا به ازای هر RAG)؛ ارتقا به گزینه 3 فقط برای RAGهای high-traffic/heavy (سنگینی = queries/day یا latency SLA). **با RAM/Disk فعلی s52، گزینه 1 رد می‌شود** مگر با ریزرسانی.

---

## S6 — یکپارچه‌سازی LiteLLM (gateway، نه engine)

### 6.1 وضعیت واقعی (AUDIT #18)
LiteLLM روی s52 **موجود و زنده** است (4000/4101؛ 4102 مرده) با کاتالوگ قوی: `bge-m3`، `Qwen3-Embedding-4B/0.6B`، `mxbai-embed-large`، `qwen38` (27B)، `gpt-4o`، `deepseek-chat`. `/model/info` 401 → auth لازم (API key از `.env` سرور — **در کد/Git/گزارش نمی‌آید**).
**قانون:** LiteLLM فقط **مصرف** می‌شود؛ config/مدل/کلیدها دست‌نخورده. RAG engine ما مستقل از LiteLLM است (اگر LiteLLM down شد، retrieval کار می‌کند، فقط generation/Enrichment degraded).

### 6.2 نقش دقیق LiteLLM در معماری
1. **Embedding** (stage Index Preparation + query vector): `POST /v1/embeddings` model=bge-m3 (یا تصمیم J4)
2. **Semantic Enrichment** (stage 9): `POST /v1/chat/completions` با Master Prompt
3. **Rerank-judge** (اختیاری، اگر cross-encoder نبود): LLM-judge
4. **Answer generation** (RAG API): retrieved chunks → answer با citations
5. (آینده) **SuperRAG planning** و **Research nightly** — با همان endpointها

### 6.3 قرارداد پاسخ RAG (تمام RAGها — PCT و خارجی)
```json
{
  "answer": "…",
  "citations": [
    {"work_id": "…", "edition_id": "…", "volume": 1,
     "chapter": "…", "page": 12, "quote": "…", "chunk_id": "…",
     "source_url": "…"}
  ],
  "retrieved_sources": [{"chunk_id": "…", "score": 0.87, "collection_id": "…"}],
  "collection_ids": ["c-…"],
  "confidence": 0.81,
  "evidence_sufficiency": "sufficient|partial|insufficient",
  "retrieval_trace": {"bm25_top": 10, "vector_top": 10, "fused": 20,
                      "reranked": 8, "filtered_out": 12, "took_ms": 340},
  "model_version": "qwen38@…", "index_version": "iv-1",
  "prompt_version": "mp-3", "litellm": {"model": "…", "tokens": 1234, "cost": 0.01},
  "rag_id": "pct-rag-1", "rag_profile_version": "sp-2"
}
```
`evidence_sufficiency = insufficient` → سوپراگ موظف است RAG دیگر جستجو کند (S7).

---

## S7 — SuperRAG (Research Orchestrator)

### 7.1 جریان ۱۰ مرحله
1. دریافت سؤال + user context
2. **تحلیل سؤال**: زیرسؤالات، حوزه‌های موضوعی (subject domains)
3. جستجوی **Knowledge Registry**: موضوع/کتاب/کلیپ مرتبط (نه حدس — فقط چیزی که در registry ثبت است)
4. جستجوی **RAG Registry**: RAGهایی که `subject_domains` ∩ سؤال ≠ ∅ و `health=ok` و `access_policy` pass
5. بررسی capabilities/limitها (بم25؟ vector؟ rerank؟ budget؟)
6. انتخاب 1..k RAG (ترتیب: coverage موضوعی ← health ← latency/cost ← freshness)
7. فراخوانی RAGها با قرارداد S6 (سؤال‌های تکی‌تکی، parallel با timeout)
8. **ترکیب و ارزیابی شواهد**: هم‌راستا/تعارض؛ هر ادعا → citation؛ تناقض صریح flag می‌شود
9. تولید پاسخ مستندشده: بخش‌بندی (پاسخ / شواهد / تناقض‌ها / **خلاءهای شواهد**)
10. ثبت run (سؤال، RAGها، versions، latency، cost) در SQLite + metrics

### 7.2 قواعد
- **نه حدس زدن وجود کتاب بر اساس زبان** — فقط registry.
- هر ادعا باید citation داشته؛ بدون آن → در بخش «خلاءهای شواهد».
- تناقض: هر دو طرف با citation + flag `contradiction` (خودِ سوپراگ نمی‌چیند؛ کاربر می‌بیند).
- budget/latency cap per request.

---

## S8 — Persistent Research Engine (شبانه)

### 8.1 State هر research (SQLite)
```
researches(
  research_id, user_id, main_question,
  subquestions_json,
  selected_collection_ids[],
  sources_searched_json,     -- {(source_id, query_hash, ts)}
  evidence_json,             -- ادعاهای مصوب + citations
  open_gaps_json,            -- خلاءهای باز
  last_search_at, next_run_at,
  findings_version,          -- بامهر تغییر معنادار +1
  delivery_status,           -- none|delivered|failed|suppressed
  delivery_channel,          -- email|bale|none
  consent {granted, ts, scope}, unsubscribe_at,
  created_at, updated_at, paused (bool)
)
research_runs( run_id, research_id, started_at, finished_at,
               new_sources, new_findings_count, changes_json, status )
```

### 8.2 جریان اجرای شبانه (هر research فعال)
1. بازیابی state
2. شناسایی منابع جدید/ناچک‌شده (کتاب‌های جدید در collectionها + زیرسؤال‌های باز)
3. جستجوی مکمل (فقط queryهای جدید — dedup با `sources_searched`)
4. مقایسه با findings قبلی: **فقط تغییرات معنادار** ثبت می‌شود (threshold: ادعای جدید با citation، یا رفع/تبدیل gap)
5. اگر `findings_version` عوض شد → `delivery_status=pending` وگرنه **no-delivery** (anti-duplicate: max 1 delivery/version)
6. delivery از طریق کانال مجاز (Email یا Bale) — **در PCM-12 هیچ پیامی ارسال نمی‌شود و هیچ job شبانه enable نمی‌شود** (V0.8)
7. ثبت run + metrics

### 8.3 الزامات
- **Consent صریح** user قبل از هر research (scope + channel)
- **unsubscribe** یک‌مرحله‌ای (حذف session + توقف delivery)
- **امنیت اطلاعات**: پاسخ/شواهد فقط به کانال همان user؛ log بدون محتوای حساس
- **anti-duplicate**: delivery با key `(research_id, findings_version)` UNIQUE

---

## S9 — Dashboard و Grafana

### 9.1 داشبورد موجود (دست‌نخورده) + ۴ بخش جدید (additive، پشت auth)

| بخش | محتوا | endpoint جدید (الگوی `dashboard_api.py`) |
|---|---|---|
| **Book Factory** | فهرست کتاب‌ها (work/edition/volume)، فایل‌های دانلودشده، دانلودهای ناموفق، صف پردازش (counts + top jobs)، خطاها، progress هر کتاب (11 stage) | `/api/dashboard/books*`, `/api/dashboard/factory/queue` |
| **Knowledge Collections** | کلکسیون‌ها، موضوعات، کتاب‌های هر کلکسیون، chunk counts، وضعیت ES (index versions + docs count)، رفرنس‌دهی index | `/api/dashboard/knowledge/*` |
| **RAG Registry** | فهرست RAGها، description، فهرست کتابها، لینک public/admin، users/requests counts، health، وضعیت اتصال LiteLLM | `/api/dashboard/rags` |
| **Research Jobs** | researchهای فعال، صف شبانه، findings جدید، researchهای متوقف، وضعیت delivery email/Bale | `/api/dashboard/research` |

UI: همان SPA تک‌فایلی `dashboard/index.html` — تب‌های جدید با الگوی موجود (fetch same-origin، 401→overlay، `escHtml` برای همه خروج‌های DOM — قانون §2.8).

### 9.2 Grafana (فقط stack موجود s52، بدون نصب جدید)
- **endpoint**: `GET /metrics` (Prometheus text) در backend PCT — counters/gauges: `pct_books_total{status=}`, `pct_queue_depth{stage=}`, `pct_worker_active`, `pct_download_failures_total`, `pct_processing_duration_seconds{stage=}` histogram, `pct_chunks_indexed{collection=}`, `pct_rag_queries_total{rag=}` + `pct_rag_error_total`, `pct_llm_tokens_total{model=,type=}`, `pct_research_runs_total{status=}`, `pct_research_deliveries_total{channel=,status=}`
- **Prometheus**: scrape job جدید در config موجود (فقط افزودن target — بدون تغییر targetهای دیگر)؛ Grafana: 4 dashboard JSON در `provisioning/dashboards` (همان الگوی stack موجود)
- **Loki**: لوگ ساختاریافته backend (JSON) → alert روی `status=failed` تکرارشونده

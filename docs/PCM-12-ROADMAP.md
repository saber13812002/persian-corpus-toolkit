# PCM-12-ROADMAP — نقشه‌راه نسخه‌ای (V0.1 → V1.0)

- تاریخ: 1405/08/03 (2026-10-24)
- قاعده طلایی: **مسیر عمودی تکی اول** — `یک Word → Parse → Validate → JSON → ES test index → Search → Citation`. تا این مسیر روی یک نمونه معتبر سبز نشود، bulk download / RAGهای متعدد شروع نمی‌شود.
- هر version: Scope · Dependencies · Classes/Interfaces · API Contracts · Data Schema · Acceptance · Tests · Security Risks · Rollback · Migration · Commit/Release
- الگوی deploy همه‌ی versionها: الگوی PCM-05 (backup DB + integrity → snapshot → build → `up -d backend` → health → smoke → regression نوشتاری → smoke crawl زنده).

---

## V0.1 — یک Word → JSON ساختاریافته (بسته‌بندی Factory بدون LLM/ES)

- **Scope**: stageهای 1-8 + 10 خط لوله (بدون LLM enrichment، بدون ES). یک کتاب واقعی (نمونه ≥ 30 صفحه) → raw + normalized + stage_state.
- **Dependencies**: یک فایل Word واقعی (از کاربر/اپراتور — **نه** دانلود از قائمیه؛ URL سایت هنوز NOT VERIFIED)؛ `python-docx` در requirements.
- **Classes/Interfaces**: `factory/parser.py` (blocks)، `factory/structure.py` (tree)، `factory/metadata.py` (biblio extract-only)، `factory/normalize.py` (norm v1: نیم‌فاصله، تکیه، اعداد، زیرمختصات)، `factory/quality.py`، `factory/chunking.py` (chunk v1: 500 token، 10% overlap)، `factory/run.py` (orchestrator stageها + checkpoint)
- **API Contracts**: `POST /api/factory/files` (ثبت فایل دستی/بازاری — multipart یا path سرور، auth) · `GET /api/factory/files/<id>/status` (11-stage progress) · `GET /api/factory/files/<id>/outputs` (raw/normalized/enriched refs) — همه پشت auth
- **Data Schema** (additive): `works`, `editions`, `volumes`, `files` (sha256, format, size, license_json, status)، `processing_runs` (file_id, run_id, stage, prompt/model versions nullable, tokens/cost nullable, status, error)
- **Acceptance**: یک docx واقعی → `outputs/` با raw+normalized JSONL + tree + quality report؛ file خرد → fail with reason؛ فایل تکراری (همان hash) → skip
- **Tests**: unit (parser/normalize/chunking روی 10 block synthetic)، integration (run factory روی فایل واقعی test fixture)، data quality (percent فارسی، no-null tree)، **بدون** test performance (حجم تکی)
- **Security Risks**: فایل آپلود (size cap، نوع MIME، بدون اجرای محتوا)؛ auth روی endpointهای نوشتاری جدید؛ secret ندارد
- **Rollback**: حذف endpointها (کد)؛ جداول additive دست‌نخورده می‌مانند (ممنوع DROP)
- **Migration**: `ensure_factory_schema()` افزایشی (همان الگوی `projects.py`) — بدون تغییر جدول موجود
- **Commit/Release**: commit `factory: V0.1 Word→JSON pipeline (stages 1-8,10)` → deploy الگوی PCM-05 → smoke: فایل تستی از سرور → status done → `git push` → گزارش

## V0.2 — یک کتاب → Elasticsearch test index + جستجوی معتبر

- **Dependencies**: V0.1 سبز؛ تصمیم J2 (ES host) + دیسک آزاد (AUDIT §6 ⛔)؛ embedding model از LiteLLM (J4)
- **Scope**: stage 11 (index prep) + bulk به `pct_test_v1` (alias `pct_test`) + retrieval endpoint (BM25 + kNN + fusion) + citation در خروجی
- **Classes/Interfaces**: `factory/indexer.py` (mapping + bulk idempotent)، `retrieval/search.py` (hybrid + RRF + metadata filter)، `retrieval/citations.py`
- **API Contracts**: `POST /api/factory/index` (book_id → bulk) · `GET /api/factory/search?q=&mode=hybrid&limit=8` → `{results:[{chunk_id, text, score, citation{work,edition,volume,chapter,page,quote}}]}`
- **Data Schema**: `index_versions` (iv_id, index_name, alias, mapping_version, embedding_model, chunk_count, created_at)؛ ES mapping مطابق ARCHITECTURE §4.3
- **Acceptance**: یک کتاب → ~N chunk در `pct_test` → search فارسی → top result با citation کامل (work/edition/volume/chapter)؛ دوباره‌ی bulk = 0 duplicate
- **Tests**: integration (bulk idempotency ×2 run)، data quality (هر chunk content_hash = hash(text) در ES)، unit (RRF fusion)، performance smoke (search p95 < 300ms روی 1 کتاب)
- **Security Risks**: ES بدون auth در شبکه داخلی s52 → firewall/iptables فقط از s52؛ mapping بدون فیلد حساس (فقط کتاب)
- **Rollback**: alias `pct_test` → index قبلی (blue/green)؛ حذف index جدید (فقط index خود PCT — هرگز index دیگر)
- **Migration**: ES index جدید فقط؛ DB additive `index_versions`
- **Commit/Release**: `factory: V0.2 ES test index + hybrid search with citations` → deploy → smoke search روی سرور

## V0.3 — 10 کتاب + صف پایدار + Collection

- **Dependencies**: V0.2 سبز؛ دیسک/ظرفیت برای 10 کتاب (تقریبی: 10 × ~50MB file + chunks)
- **Scope**: queue A (SQLite durable + lease + DLQ + priority + worker process مستقل از request)، resume از stage checkpoint (E2E)، `collections` + membership، dashboard تب **Book Factory** + **Knowledge Collections**
- **Classes/Interfaces**: `queue/manager.py` (push/claim/complete/fail/reclaim)، `queue/worker.py` (loop، lease renewal، max_concurrent)، `worker_supervisor` (thread در backend یا separate container — تصمیم در V0.3 design doc)
- **API Contracts**: `POST /api/factory/queue` (book(s) → jobs) · `GET /api/dashboard/factory/queue` · `GET/POST /api/registry/knowledge/collections*`
- **Data Schema**: `book_queue_jobs`, `book_stage_state`, `queue_dlq` (ARCHITECTURE §3.3)، `collections`, `collection_members`
- **Acceptance**: 10 کتاب → همه done بدون دخالت؛ **kill worker وسط کتاب 5** → restart → stages done skip + ادامه از stage ناقص (E2E الزامی)؛ duplicate job_key → skip؛ 1 collection با 3 کتاب → search filter `collection_id`
- **Tests**: E2E (10 کتاب + kill/resume)، unit (lease expiry، DLQ، priority ordering)، data quality (10/10 quality pass یا manual_review با دلیل)
- **Security Risks**: worker loop (OOM guard: RAM cap/book)، queue بدون auth در نوشتن (auth روی push)
- **Rollback**: worker stop (flag) — queue/state در DB می‌ماند؛ revert کد؛ جداول additive
- **Migration**: additive فقط
- **Commit/Release**: `queue: V0.3 durable queue + resume + collections + dashboard tabs` → deploy → smoke: queue 1 کتاب تست + kill/resume دستی

## V0.4 — RAG API با پاسخ مستندشده

- **Dependencies**: V0.3 سبز؛ LiteLLM API key مجاز (`.env` سرور)؛ embedding model انتخاب‌شده (J4)
- **Scope**: RAG service تکی `pct-rag-1` (گزینه 2 — engine مشترک + collection alias)؛ `POST /api/rag/<rag_id>/ask` با contract کامل S6 (answer, citations, evidence_sufficiency, retrieval_trace, versions)؛ LiteLLM circuit breaker (retrieval-only mode)
- **Classes/Interfaces**: `rag/service.py` (pipeline: retrieve→fuse→rerank→generate→package)، `rag/litellm_client.py` (embeddings + chat، token/cost log)، `rag/profile.py` (semantic_profile v1)
- **API Contracts**: `POST /api/rag/<rag_id>/ask` `{question, limit, filters}` → schema پاسخ S6 (DATA-CONTRACTS §6) · `GET /api/rag/<rag_id>/health`
- **Data Schema**: `llm_calls` (model, tokens_in/out, cost, latency_ms, status — بدون secret)
- **Acceptance**: 20 سؤال فارسی روی 10 کتاب → ≥ 80% با `evidence_sufficiency != insufficient` و citation موجود؛ kill LiteLLM → retrieval-only 200 + flag degraded؛ هر پاسخ شامل model/index/prompt versions
- **Tests**: integration (20 سؤال golden set، eval: citation-match + sufficiency)، unit (breaker، packaging)، performance (p95 < 15s شامل LLM)
- **Security Risks**: API key فقط در `.env` سرور (gitignored)؛ prompt injection از سؤال کاربر (system prompt extract-only + sanitize citation)؛ rate limit endpoint ask
- **Rollback**: RAG entry از registry حذف/غیرفعال (flag) — code revert؛ index دست‌نخورده
- **Migration**: additive (`llm_calls`)
- **Commit/Release**: `rag: V0.4 RAG API with documented answers (contract S6)` → deploy → smoke: 1 ask + 1 health + breaker test

## V0.5 — Knowledge Registry + RAG Registry

- **Dependencies**: V0.4 سبز
- **Scope**: registryها کامل (ARCHITECTURE §5) با API خواندنی + semantic_profile versioning + dashboard تب‌های **RAG Registry** (+ تکمیل Knowledge)؛ RAG entry `pct-rag-1` با profile v1
- **Classes/Interfaces**: `registry/knowledge.py`، `registry/rag.py`، `registry/profile.py` (version + diff)
- **API Contracts**: `GET /api/registry/knowledge/works|editions|collections|subjects` · `GET /api/registry/rags` · `GET /api/registry/rags/<id>/profile?version=` — pagination + sort whitelist + auth
- **Data Schema**: `rag_registrations`، `rag_semantic_profiles` (version, scope, exclusions, freshness, cost_tier, latency_tier, updated_by)، `registry_health` (last_check, p95, error_rate)
- **Acceptance**: هر کتاب/کلیپ/rag در API با همه فیلدها؛ profile v1→v2 با diff قابل‌نمایش؛ health check هر 5 دقیقه (background)؛ داشبورد RAG با health badge
- **Tests**: integration (API + versioning)، data quality (هیچ work بدون edition، هیچ rag بدون profile)
- **Security Risks**: profile با `updated_by` (audit)؛ API خواندنی — بدون write بدون auth
- **Rollback**: revert کد؛ جداول additive
- **Migration**: additive
- **Commit/Release**: `registry: V0.5 Knowledge + RAG registries with versioned profiles` → deploy → smoke

## V0.6 — LiteLLM Integration (عمیق‌تر + multi-model)

- **Dependencies**: V0.5 سبز؛ تأیید دسترسی/کلید برای مدل‌های embedding/LLM (J4)
- **Scope**: انتخاب و ثبت embedding model (bge-m3 vs Qwen3-Embedding-4B/0.6B — eval روی فارسی)، reindex با model جدید (iv جدید + alias cut)، rerank-judge (LLM)، cost tracking کامل per-rag/per-model، metrics llm_calls در dashboard
- **Acceptance**: eval embedding (100 query فارسی، recall@10 مقایسه 2 مدل)؛ reindex 10 کتاب بدون duplicate؛ cost/report: tokens/cost per RAG از DB واقعی (قانون §2.9)
- **Tests**: eval suite (recall@10، latency)، integration (alias cut)
- **Security Risks**: انتخاب model = هزینه → budget cap per-day در `rag_registrations`
- **Rollback**: alias cutback به iv قبلی (embedding model قبلی)
- **Commit/Release**: `litellm: V0.6 embedding eval + reindex + cost tracking` → deploy

## V0.7 — SuperRAG (Orchestrator)

- **Dependencies**: V0.6 سبز؛ ≥ 1 RAG ثبت‌شده (حداقل خودمان؛ RAGهای خارجی فقط اگر owner آن‌ها contract S6 را تأیید کند)
- **Scope**: سوپراگ 10-مرحله (ARCHITECTURE §7)؛ `POST /api/superrag/ask`؛ run log؛ budget cap
- **API Contracts**: `POST /api/superrag/ask` → `{answer, sections{answer,evidence,contradictions,gaps}, citations[], rag_runs[], trace}`
- **Acceptance**: سؤال 2-حوزه‌ای → citation از ≥ 2 RAG؛ سؤال خارج از registry → gaps صریح (نه حدس)؛ run log کامل در DB
- **Tests**: integration (3 scenario: single-domain، dual-domain، out-of-scope)
- **Security Risks**: cost amplification (cap 3 RAG/request)؛ prompt chaining injection
- **Rollback**: endpoint غیرفعال (flag)
- **Commit/Release**: `superrag: V0.7 research orchestrator` → deploy

## V0.8 — Persistent Research + delivery (dry-run اول)

- **Dependencies**: V0.7 سبز؛ کانال delivery (Email SMTP موجود s52 یا Bale API) + consent flow
- **Scope**: researches table + scheduler شبانه (dry-run: فقط log، ارسال واقعی بعد از تأیید جبهه‌ی delivery)؛ delivery anti-duplicate (UNIQUE research_id+findings_version)؛ dashboard تب **Research Jobs**
- **Acceptance**: 2 research تستی → شبیه‌سازی 2 run → run بدون تغییر = suppressed؛ با تغییر = 1 delivery (log)؛ unsubscribe → توقف فوری
- **Security Risks**: PII (email) — فقط scope user؛ log بدون محتوای حساس؛ consent صریح
- **Rollback**: pause all research (flag) — state دست‌نخورده
- **Commit/Release**: `research: V0.8 persistent research engine (dry-run delivery)` → deploy

## V1.0 — Stabilization عملیاتی + امنیت + monitoring + recovery

- **Dependencies**: V0.1..V0.8 سبز؛ دیسک s52 حل‌شده (⛔ AUDIT §6)
- **Scope**: `/metrics` Prometheus + 4 داشبورد Grafana (stack موجود s52) + Loki logs + alerts؛ DR: backup ES snapshot + JSONL export روزانه + restore runbook؛ security review (auth همه write endpoints، rate limit، audit log)؛ load test (20 کتاب همزمان)؛ runbook operations (reindex، reprocess، DLQ handling)
- **Acceptance**: 4 داشبورد با داده زنده؛ restore از بکاپ در محیط تست < 30 دقیقه؛ load test: 20 کتاب → همه done، بدون OOM (RAM ≤ 9.7Gi آزاد فعلی)
- **Tests**: E2E load، chaos (kill worker ×3، LiteLLM down، ES restart)، security (unauth write → 401/403، XSS scan dashboard)
- **Rollback**: runbook rollback برای هر component
- **Commit/Release**: `ops: V1.0 stabilization, monitoring, DR runbooks` → deploy → smoke کامل

---

## ترتیب وابستگی (شماره‌گذاری PCM پیشنهادی)

```
V0.1 → V0.2 → V0.3 → V0.4 → V0.5 → V0.6 → V0.7 → V0.8 → V1.0
  │        │        │        │
  │        │        │        └── (V0.6 می‌تواند با V0.5 موازی شود اگر model eval زودتر لازم باشد)
  │        └── ⛔ پیش‌نیازهای بیرونی: دیسک آزاد + تصمیم J2 (ES) + تصمیم J4 (embedding model)
  └── ⛔ پیش‌نیاز: یک فایل Word واقعی نمونه (از اپراتور — بدون وابستگی به سایت قائمیه)
```

## قواعد مشترک هر version
1. بدون بکاپ deploy نمی‌شود (`sqlite3 .backup` + `PRAGMA integrity_check`)
2. فقط `docker compose build backend && up -d backend` — هرگز `down -v`
3. APIهای نوشتاری اکستنشن (crawl) قبل/بعد از deploy smoke می‌شوند (regression)
4. 39+ تست موجود سبز + تست‌های جدید version
5. عدد آمار در گزارش/داشبورد فقط از شمارنده‌های واقعی DB
6. هر version: گزارش `گزارش-PCM-<N>.md` (11 بخش استاندارد)

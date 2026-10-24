# PCM-12-AGENT-HANDOFF — تسویق به اگنت/تیم بعدی

- تاریخ: 1405/08/03 (2026-10-24)
- هدف: هر توسعه‌دهنده/اگنت بعدی با خواندن این فایل + AGENTS.md بتواند بدون سؤال اضافی روی V0.1+ کار کند.

## ۰. خلاصه یک‌صفحه‌ای

- **این پروژه چیست (حالا):** ابزار crawl مرورگری (Chrome MV3) + Flask/SQLite (5055) + داشبورد pish-pak (پشت auth) روی s52. کراول زنده در production.
- **PCM-12 چه کرد:** فقط ممیزی + طراحی + contract + roadmap. **هیچ** کد عملیاتی، سرویس، schema یا index تغییری نکرده.
- **بعدی چیست:** V0.1 = یک Word واقعی → JSON (stages 1-8,10) بدون LLM/ES. بعد V0.2 (ES test index) و به ترتیب تا V1.0.
- **قاعده اول:** هرگز crawl زنده را قطع نکن؛ APIهای نوشتاری اکستنشن دست‌نخورده؛ همه تغییر additive + بکاپ.

## ۱. نقشه‌ی فایل‌ها (چه بخوانی، کجا کار کنی)

| وظیفه | فایل‌های مرجع |
|---|---|
| قواعد مطلق | `AGENTS.md` (نخستین مرجع — همیشه قبل از کار) |
| وضعیت واقعی موجود | `docs/PCM-12-AUDIT.md` |
| معماری هدف | `docs/PCM-12-ARCHITECTURE.md` (S2..S9) |
| الزامات محصول + acceptance | `docs/PCM-12-PRD.md` |
| schema/API/Prompt | `docs/PCM-12-DATA-CONTRACTS.md` |
| ترتیب اجرا | `docs/PCM-12-ROADMAP.md` |
| کد crawl/queue موجود | `backend/server.py` (phase1/2, `_run_elastic_harvest`) |
| الگو auth/dashboard | `backend/auth.py`, `backend/dashboard_api.py` |
| الگو schema افزایشی | `backend/projects.py` → `ensure_projects_schema()` |
| الگو deploy | `deploy/pcm05_deploy.sh` |
| الگو corpus/builder | `corpus/build_corpus.py` (برای factory V0.1) |

## ۲. ۱۰ تصمیم معماری (با شواهد محیطی — نه تصمیم نهایی بدون تأیید)

> قانون مأموریت: «بدون شواهد محیطی تصمیم نهایی تحمیل نمی‌شود». هر تصمیم: گزینه‌ها + شواهد s52 + پیشنهاد + سؤال باز.

### D1 — ES مشترک (کلانگر) یا per-collection
- شواهد: s52 فقط `taghrir-es` 8.13.4 (متوقف، 1.5GB volume)؛ دیسک 100% پر (819M آزاد).
- گزینه‌ها: (a) 1 ES کلانگر با index/alias جدا به ازای هر collection · (b) ES جدا به ازای هر collection
- پیشنهاد: **(a)** — RAM/disk s52 اجازه چند instance نمی‌دهد؛ انزوا با index+alias+ILM کافی است.
- سؤال: J2 (host ES: container جدید PCT یا سازمانی؟) + **دیسک آزاد پیش‌نیاز است**.

### D2 — engine RAG مشترک یا Docker به ازای هر RAG
- شواهد: 23Gi RAM (9.7Gi آزاد)؛ گزینه 1 (هر RAG یک service) در AUDIT §5.3 رد شد (RAM).
- پیشنهاد: **گزینه 2 (engine مشترک + RAGهای منطقی)** برای شروع؛ ارتقا به 3 (هیبرید) فقط برای RAG heavy با SLA.
- سؤال: هیچ (اجرا در V0.4/V0.5) — اما monitor RAM بعد از V0.4.

### D3 — نقش دقیق LiteLLM در فراخوانی RAG
- شواهد: LiteLLM 4000/4101 زنده با کاتالوگ LLM/Embedding قوی؛ `/model/info` 401 (auth).
- پاسخ: LiteLLM = **gateway LLM/Embedding فقط** (embedding، enrichment، rerank-judge، answer generation). **نه** RAG engine، **نه** retriever. RAG ما حتی بدون LiteLLM retrieval می‌دهد (circuit breaker).
- سؤال: J4 (model انتخابی: bge-m3 vs Qwen3-Embedding — eval در V0.6) + کلید مجاز.

### D4 — نگهداری فایل اصلی: filesystem یا object store
- شواهد: ساختار فعلی PCT = filesystem (bind-mount DB)؛ `corpus/` همین الگو؛ S3/minio روی s52 **وجود ندارد** (بررسی containerها: فقط gitlab-redis/loki).
- گزینه‌ها: (a) filesystem `corpus/books/<work>/<edition>/vol<N>/` با sha256 manifest · (b) object store
- پیشنهاد: **(a)** + manifest JSON (فهرست فایل‌ها + hash + size) در `files` table — ساده، با backup tar مطابق الگو موجود. ارتقا به object store فقط اگر فایل‌ها > 1TB یا multi-host.
- سؤال: J6 (مربوط به ظرفیت دیسک — با AUDIT §6 حل می‌شود).

### D5 — SQLite برای فاز اول یا DB متادیتای جدا
- شواهد: PCT فعلی = SQLite WAL و 39/39 تست سبز؛ load واقعی فاز اول = 10..100 کتاب (نه میلیون row)؛ WAL + `BEGIN IMMEDIATE` برای queue گزینه A کافی (ARCHITECTURE §3.2).
- پاسخ: **SQLite همان DB (`thesaurus.db`) با جداول additive** برای V0.1..V0.6. شرط جداسازی (مثلاً Postgres که روی s52 موجود است): اگر `book_queue_jobs` > 1M row یا writer contention سنجیده شود — در آن لحظه، interface queue ثابت است و swap کم‌هزینه است.
- سؤال: هیچ.

### D6 — ابزار queue مناسب برای حجم واقعی
- شواهد: حجم واقعی = کتاب‌های Word (هر job = یک stage یک کتاب، چند ثانیه..چند دقیقه) — **نه** job rate بالا. Celery/RabbitMQ برای PCT وجود ندارد (AUDIT #14).
- پاسخ: **گزینه A (SQLite durable queue)** — ARCHITECTURE §3.2، جدول‌ها در DATA-CONTRACTS §1.3. بدون نصب جدید.
- سؤال: هیچ (شرط ارتقا مکتوب در ARCHITECTURE §3.2).

### D7 — contract یکپارچه‌سازی با RAGهای دیگر (پروژه‌های مستقل)
- شواهد: `automated/export-sql-chromadb` (mesbahyazdi book_pages→Chroma)، `graph-rag`، moshat — همه خارج از محدوده AGENTS.md §1.
- پاسخ: **فقد contract** (DATA-CONTRACTS §7): RAG خارجی برای ثبت در registry باید contract ask (§6.5) را ارائه دهد؛ داده فقط از طریق JSONL/Parquet export یا alias خواندنی — **هیچ** کد/دپلوی تغییر در آن‌ها.
- سؤال: J7 (آیا owner هر RAG خارجی contract را می‌پذیرد؟ — اختیاری).

### D8 — چه چیزی در Knowledge Registry و چه چیزی در RAG Registry
- پاسخ (تفکیک مکتوب در ARCHITECTURE §5):
  - **Knowledge Registry** = حقیقت داده: work/edition/volume/file، collections، subjects، counts (doc/chunk)، index versions، quality، license، RAG-readiness.
  - **RAG Registry** = حقیقت سرویس: rag_id، capabilities، URLs، access، health، stats، semantic_profile (versioned).
  - قاعده: اگر یک فیلد «درباره داده» باشد → Knowledge؛ اگر «درباره سرویس» → RAG. `collection_ids` پل میان آن‌هاست (فقط در RAG Registry ارجاع می‌شود، تعریف در Knowledge).
- سؤال: هیچ.

### D9 — سیاست قانونی/لایسنس برای کتاب‌های قائمیه
- شواهد: شرایط سایت NOT VERIFIED (AUDIT §5)؛ الگوی سازمانی (mesbahyazdi) dump صفحه‌به‌صفحه دارد اما حقوق آن را روشن نمی‌کند.
- سیاست (تا تأیید): هر `file` بدون `license_json` (terms + rights_ok) **نمی‌تواند** وارد stage 8+ شود (PRD §3.4)؛ default = `rights_ok: null` → در registry با badge «لایسنس بررسی‌نشده»؛ RAG-readiness = false تا `rights_ok: true`.
- سؤال: **J9 — بلوک‌کننده**: شرایط استفاده سایت قائمیه (بازداشت/بازتوزین/نسخت‌برده) — فقط از owner سایت.

### D10 — چگونه همه چیز اضافه شود بدون قطع crawl فعلی
- پاسخ (قوانین اجرایی):
  1. همه migration = `ensure_*_schema()` افزایشی (الگوی `projects.py`) — بدون تغییر جدول موجود
  2. deploy = الگوی PCM-05: backup + integrity → build → `up -d backend` → smoke → **regression crawl زنده** (قبل/بعد: `/api/stats` + submit یک page تستی)
  3. APIهای نوشتاری اکستنشن بدون auth می‌مانند؛ فقط خواندنی‌های جدید + نوشتنی‌های factory/registry پشت auth
  4. Worker factory **جدا از request path** (loop با flag) — crash آن backend/crawl را نمی‌بازد
  5. هر deploy: smoke crawl زنده الزامی (الگوی PCM-05)
- سؤال: هیچ.

## ۳. مرزها (هرگز)

| موضوع | وضعیت |
|---|---|
| NotebookLM Orchestrator | ❌ دست نزن (AGENTS.md §1) |
| QA Bank | ❌ دست نزن |
| `automated/` (RAG indexer — subset دیگر) | ❌ تغییر کد/دپلوی ممنوع؛ فقط contract §7 |
| `graph-rag`, moshat, Flowise, Open WebUI, n8n | ❌ خارج از محدوده |
| LiteLLM config/کلیدها/مدل‌ها | ❌ بدون تغییر؛ فقط مصرف |
| `taghrir-es` و indexهای غیر-PCT | ❌ بدون تغییر (متعلق به taghrir) |
| `gitlab-redis` | ❌ متعلق به GitLab — استفاده برای PCT ممنوع |
| `backend/thesaurus.db` production | ⛔ فقط از طریق بکاپ‌برده‌شده؛ migration فقط additive |
| APIهای نوشتاری اکستنشن (crawl) | ⛔ بدون تغییر قرارداد؛ بدون auth می‌مانند |
| کراول زنده | ⛔ هر deploy با regression crawl |

## ۴. ریسک‌ها و وضعیت‌های فوری

| ریسک | شدت | وضعیت/اقدام |
|---|---|---|
| **دیسک s52 = 100% پر (819M آزاد)** | 🔴 بحرانی | قبل از V0.2 (ES) و قبل از هر بارگذاری فایل کتاب باید آزاد/گسترش شود. مستقل از PCM-13 — به saber گزارش شد. |
| URL سایت قائمیه ناشناخته (NOT VERIFIED) | 🟠 بلوک S1 | سؤال J1؛ طراحی Downloader بدون فرض (PRD §3) |
| لایسنس کتاب‌ها نامشخص | 🟠 بلوک قانونی | سؤال J9؛ gate `rights_ok` در pipeline (D9) |
| کیفیت استخراج Word (footnote/table/heading) | 🟠 کیفیت | quality gate (stage 8) + manual_review؛ eval V0.1 با 1 کتاب واقعی |
| داده تکراری (دانلود مجدد / reindex) | 🟡 کنترل‌شده | sha256 dedup + chunk_id deterministic + bulk idempotent |
| hardware s52 (RAM 9.7Gi آزاد) | 🟡 محدودکننده | worker RAM/CPU cap (PRD §12)؛ گزینه 1 (D2) رد شد |
| مداخله در production | 🟡 کنترل‌شده | قواعد D10 + الگو PCM-05 + smoke crawl |
| hallucination LLM در enrichment | 🟡 کنترل‌شده | Master Prompt extract-only + verbatim-quote check + confidence flags (DATA-CONTRACTS §4/§5) |
| `_HARVEST_JOB` in-memory (موجود) | 🟢 پذیرفته‌شده (فاز crawl) | جایگزینی در معماری جدید فقط برای factory — crawl فعلی دست‌نخورده |

## ۵. پرسش‌های تصمیم‌گیری (فقط موارد بلوک‌کننده — بخش J گزارش)

| # | پرسش | بلوک می‌کند |
|---|---|---|
| J1 | **URL دقیق سایت کتابخانه قائمیه** چیست؟ (همه دامنه‌های حدس‌زده‌شده از دو شبکه resolve نشدند) | S1/Downloader (V0.1 می‌تواند با فایل دستی شروع شود) |
| J2 | **host Elasticsearch** برای PCT: container جدید `pct-es` روی s52 (نیاز به دیسک آزاد) یا ES سازمانی؟ | V0.2 |
| J4 | **embedding model** اولیه: `bge-m3` (1024d) یا `Qwen3-Embedding`؟ (eval در V0.6) | V0.2 (موقتی) → V0.6 (نهایی) |
| J6 | **ظرفیت/محل ذخیره فایل‌های کتاب** بعد از آزادسازی دیسک (فایل سیستم فعلی یا volume جدا؟) | V0.3 (10 کتاب) |
| J7 | آیا **owner RAGهای خارجی** (مثلاً export-sql-chromadb) contract §7 را می‌پذیرد؟ | V0.5 (اختیاری) |
| J9 | **لایسنس/شرایط استفاده** کتاب‌های قائمیه چیست؟ | ورود هر کتاب به RAG-readiness |

سایر تصمیم‌ها (D1..D10) پیشنهاد با شواهد دارند و بلوک‌کننده نیستند — با شروع هر version تأیید می‌شوند.

## ۶. نقشه‌ی اجرا (به ترتیب، با gate‌ها)

```
[الان] V0.1: 1 Word واقعی → JSON            gate: acceptance PRD §4.5 + 1 کتاب ≥30 صفحه از اپراتور
       V0.2: → ES test index + search        gate: J2 + دیسک آزاد + smoke search
       V0.3: 10 کتاب + queue + collections   gate: E2E kill/resume + RAM cap
       V0.4: RAG API (contract S6)           gate: 20 سؤال golden + breaker
       V0.5: registries                      gate: API + profile versioning
       V0.6: LiteLLM deep (eval+reindex)     gate: recall@10 eval
       V0.7: SuperRAG                        gate: 3 scenario
       V0.8: persistent research (dry-run)   gate: consent + anti-dup
       V1.0: stabilization                   gate: load 20 کتاب + DR restore <30min
```
- هر گیت = deploy الگوی PCM-05 + 39+ تست سبز + smoke crawl زنده + گزارش `گزارش-PCM-<N>.md`
- **شروع bulk download / RAG متعدد قبل از سبز شدن V0.1+V0.2 ممنوع** (قاعده طلایی roadmap)

## ۷. دستورالعمل‌های عملی برای اولین ویرایش کد (V0.1)

1. `cd backend` و `python -m unittest test_api test_projects test_dashboard -v` → 39/39 (baseline)
2. `requirements.txt`: افزودن `python-docx` (سطح تکی — بازبینی نسخه در commit)
3. ماژول جدید `backend/factory/` (پاکر، نورمالایزر، کچونک، رن) — **فایل جدید**؛ `server.py` فقط wiring routeها + `ensure_factory_schema()` افزایشی
4. endpointهای نوشتاری factory **پشت `require_auth`** (الگوی `dashboard_api.py`)
5. فایل‌های کتاب: `corpus/books/...` (bind-mount جدید در docker-compose — additive؛ یا `PCT_BOOKS_DIR` env)
6. تست‌های جدید: `backend/test_factory.py` روی fixture docx کوچک (≤ 1MB، بدون داده واقعی کتاب تا V0.1 acceptance)
7. commit: `factory: V0.1 …` → push → deploy الگو → smoke (شامل regression crawl) → گزارش

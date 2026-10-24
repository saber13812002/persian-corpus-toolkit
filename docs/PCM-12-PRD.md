# PCM-12-PRD — Product Requirements: Book Factory → Knowledge → RAG

- تاریخ: 1405/08/03 (2026-10-24)
- محدوده: فقط `persian-corpus-toolkit` (backend/, dashboard/, corpus/, docs/). سرویس‌های RAG مستقل = **فقط contract یکپارچه‌سازی** (AGENTS.md §1).
- قاعده مطلق: بدون قطع کراول زنده؛ بدون تغییر سرویس/DB/skema عملیاتی؛ بدون bulk download؛ همه تغییرات آینده **additive** و با بکاپ.

## ۱. Product Vision

تبدیل `persian-corpus-toolkit` از «ابزار crawl مرورگری + داشبورد پایش» به **پایپلاین کتاب‌خانه‌ای**: دریافت Word → داده ساختاریافته قابل‌اتکا → پیکره نسخه‌شده → Knowledge Collections → RAG با پاسخ مستندشده → سوپراگ و researchهای پایدار — همه روی s52 با زیرساخت موجود، بدون تداخل با عملیات جاری.

## ۲. Actors

| Actor | نیاز |
|---|---|
| اپراتور کتابخانه (saber) | بارگذاری/پیگیری کتاب‌ها، مدیریت کلکسیون‌ها، بررسی خطاها |
| مصرف‌کننده RAG (انسان/سرویس) | سؤال → پاسخ با citation |
| سرویس‌های دیگر سازمان (Flowise، Open WebUI، n8n، پروژه‌های RAG مستقل) | مصرف RAG Registry + API RAG با contract ثابت |
| LiteLLM (gateway موجود) | مصرف‌کنده‌شدن برای embedding/LLM — بدون تغییر |

## ۳. S1 — دریافت کتاب Word (کتابخانه قائمیه)

### 3.1 وضعیت واقعی
- **URL سایت: NOT VERIFIED** — هیچ دامنه حدس‌زده‌شده از هیچ شبکه‌ای resolve نشد (AUDIT §5). egress s52 سالم است.
- بنابراین این بخش **طراحی بدون فرض** است؛ 8 سؤال زیر قبل از پیاده‌سازی Downloader باید با بررسی واقعی سایت (بعد از دریافت URL) جواب شوند.

### 3.2 سؤالات باز سایت (بلوک‌کننده — J1)
1. فرمت فایل: DOC یا DOCX (یا هر دو/بسته به کتاب)؟
2. URLهای دانلود چگونه استخراج می‌شوند (رابط کتاب‌خوانی؟ لینک مستقیم؟) — و آیا pattern پایدار دارند؟
3. ساختار بایوگرافیایی: چه فیلدهایی در صفحه کتاب موجودند (عنوان، نویسنده، ناشر، سال، موضوع، ISBN)؟
4. چندجلدی بودن: مدل صفحه‌بندی جلد (یک صفحه فهرست؟ جلد جدا؟)
5. ثبات URLها (مهم برای dedup و resume)
6. Resume: آیا دانلود قطعی‌شده قابل ادامه است (Range header)؟
7. شرایط استفاده/لایسنس: آیا بازداشت/بازتوزین مجاز است؟ (قانون J9)
8. API رسمی/export وجود دارد؟ rate limit غیررسمی چند است؟

### 3.3 مدل داده پیشنهادی (هر ۴ سطح، جدا — نمی‌ترکند)

```
work     : شناسه پایدار اثر (عنوان+نویسنده) — «این اثر چه چیزی است»
edition  : یک چاپ/ناشر/سال از work — «کدام چاپ»
volume   : جلد N از edition — «جلد چندم»
file     : فایل فیزیکی دریافت‌شده (با checksum) — «کدام فایل»
```
(یک work می‌تواند چند edition داشته باشد؛ یک edition چند volume؛ هر volume یک یا چند file — مثلاً اگر دانلود دوباره شد. file هرگز شناسه منطقی کتاب نیست.)

### 3.4 Downloader — طراحی (بدون پیاده‌سازی در PCM-12)
- **مبدأ**: لیست دستی اپراتور (URL/شناسه کتاب) یا فهرست سایت (بعد از تأیید S3.2)
- **حالت‌های مجاز**: تکی + batch کوچک با **rate limit صریح** (پیش‌فرض: 1 فایل/30 ثانیه، سقف روزانه قابل‌تنظیم) — **bulk ممنوع** تا قانون J9
- **Retry policy**: backoff نمایی (30s→2m→10m)، max 3 تلاش برای network error؛ 403/404 → `failed` + `reason` (بدون retry loop)
- **Dedup**: `sha256(file)` — اگر hash قبلاً در `files` بود → skip (بدون پردازش دوباره) + لینک به file قدیمی
- **Resume**: `Range: bytes=…` اگر سرور ساپورت کند؛ وگرنه دانلود مجدد از صفر + overwrite atomic (tmp → rename)
- **فایل ناقص/خرد**: هرگز به `files` با status=done ثبت نمی‌شود؛ `status=partial` + `bytes_downloaded/bytes_total`؛ stage 2 (format detection) فایل ناقص را رد می‌کند
- **نیمه‌نگه‌داری**: `downloads` table (download_id, url, file ref, status ∈ {pending,downloading,done,partial,failed}, attempts, bytes, error, started/finished)
- **چرخه حیات**: pending → downloading → (done | partial → resume) → failed(→ retry | dlq)
- **امنیت**: هر فایل دانلودشده `license_metadata` (source, terms_snapshot, downloaded_at) را با خود حمل می‌کند — بدون آن، stage 8 quality/8b license-check را رد نمی‌کند (قانون J9)

### 3.5 Acceptance (S1، وقتی URL تأیید شد)
- یک کتاب تکی با 1 retry طبیعی → `file` با sha256 در DB + فایل در `corpus/books/<work>/<edition>/vol<N>/`
- دانلود دوباره همان فایل → skip با دلیل `duplicate_hash`
- قطع عمدی شبکه وسط دانلود → `partial` → resume موفق (اگر سایت ساپورت کند)
- هیچ bulk/فشار روی سایت > rate limit صریح

## ۴. S2 — Document Processing Factory (PRD)

### 4.1 Inputs/Outputs
- Input: `file` (docx؛ doc → تبدیل به docx؛ odt اختیاری)
- Outputs (سه خروجی مستقل + state):
  1. `raw/` — متن دقیق‌الکلمه (JSONL: block_type, text, index, style, footnote_ref)
  2. `normalized/` — متن norm v-N (JSONL هم‌رسانده با raw با `block_index`)
  3. `enriched/` — metadata LLM (JSON مطابق `enrichment_schema_v1`) + processing_runs row
  4. `stage_state` checkpoints (برای resume)

### 4.2 استخراج ساختاری (stage 5/6)
- main text، chapters/sections با شماره‌بندی کتاب (فارسی/عربی/لاتین — parser همه را می‌فهمد)
- headings (از style docx + pattern عددی)
- footnotes/endnotes (جدا از main text، با ref)
- tables (به JSON rows، نه plain text)
- quotes (اگر style/bookmark موجود باشد؛ وگرنه **حدس نمی‌زند** — `quotes: []`)
- references (بخش ارجاع‌ها در انتهای کتاب/فصل — pattern)
- شماره جلد: **فقط از محتوای کتاب** (صفحه عنوان/جلد)، نه از نام فایل؛ اگر پیدا نشد → `volume: null, volume_source: "absent"`
- page numbers: **فقط اگر معتبر** (فیلد page در docx یا section break با page number)؛ وگرنه `page: null` (قانون: شماره صفحه ساختگی ثبت نمی‌شود)
- edition/source info: از front matter با `source_ref` + confidence

### 4.3 Master Prompt (PRD — متن کامل در DATA-CONTRACTS §5)
- extract-only؛ هیچ دانش عمومی؛ خروجی فقط JSON نسخه‌شده
- فیلدهای مبهم: `confidence < 0.7` → flag `uncertain` → در Knowledge Registry با badge «نیاز به بررسی»
- **ممنوعیت صریح**: اختراع عنوان/نویسنده/شماره صفحه/منبع
- قابل اجرا روی section‌های کوچک؛ هر فراخوانی ثبت می‌شود: prompt_version, model, tokens, cost, error
- در V0.1: enrichment **اختیاری** (بدون LLM مجاز — enriched=null) تا مسیر بدون وابستگی به LiteLLM سبز شود

### 4.4 Quality gate (stage 8)
- pass: percent فارسی ≥ 90، طول ≥ 1KB، بدون page خالی مکرر، بدون corrupt block
- fail → `manual_review` queue (کتاب در dashboard با دلیل) — **نه** auto-retry
- `quality_score` (0..1) به Knowledge Registry می‌رود (data quality — AUDIT §S5)

### 4.5 Acceptance (S2)
- یک docx واقعی (نمونه ≥ 30 صفحه، با چند فصل + پاورقی + جدول) → سه خروجی + stage_state کامل
- reprocess با norm_version جدید → فقط normalized+chunks بازنویسی می‌شوند، raw دست‌نخورده
- فایل خرد → stage 3 fail با reason `corrupt`
- doc واقعی (خودکار) → تبدیل یا رد صریح (نمی‌شکود ساillant)

## ۵. S3 — Queue (PRD)
- گزینه **A (SQLite durable queue)** برای V0.1..V0.6 (مقایسه کامل: ARCHITECTURE §3.2)
- Interface ثابت (`queue.push/claim/complete/fail`) — swap به broker در آینده بدون تغییر stageها
- الزام: worker توقف وسط کتاب → بعد از recovery، فقط stages واقعاً-completed skip می‌شوند (sha256 checkpoint) و کار از اولین stage ناقص ادامه می‌یابد (تست E2E الزامی در V0.3)
- Priority: کتاب‌های «ویژه» (priority=10) قبل از عادی (0)
- Concurrency: `max_concurrent_books` (پیش‌فرض 2) + `worker_count` (پیش‌فرض 1 روی s52 به‌خاطر RAM)
- Monitoring: queue_depth gauge + DLQ list در dashboard

## ۶. S4 — Data Store/ES (PRD)
- V0.2: **test index** `pct_test_v1` با alias `pct_test` — بدون ترافیک کاربر، بدون تماس با indexهای دیگر
- ES host: تصمیم J2 (container جدید `pct-es` یا سازمانی) — پیش‌نیاز: دیسک آزاد (AUDIT §6)
- bulk idempotent با chunk_id deterministic → reindex = بدون duplicate
- Index Version: هر تغییر mapping/انalyzer/انبار embedding → `iv-N` جدید + alias cut (blue/green ساده با alias)
- **Export**: JSONL logical export هر index version (برای تبادلم/ممیزی) — **dump هرگز پیش‌نیاز RAG نیست** (RAG با alias زنده سرویس می‌کند)
- Snapshot: repository ES (directory repo در volume جدا) — برای DR خود ES
- Acceptance (S4): 1000 chunk تست → bulk idempotent (دوباره‌run = 0 آیس) → BM25 + kNN هر دو جواب → metadata filter collection کار می‌کند

## ۷. S5 — Registries (PRD)
- Knowledge Registry: source of truth شناسه‌ها (work/edition/volume/file/collection/subject) + quality + license + RAG-readiness flags
- RAG Registry: identity + capabilities + semantic_profile (versioned) + health + stats
- API خواندنی هر دو با auth داشبورد + (بعدا) API key برای سرویس‌های سازمانی
- RAG جدید فقط با: entry کامل + semantic_profile v1 + collection با ≥ 1 کتاب index‌شده + health check pass
- **قانون:** بدون دانش hardware/usage، RAG زیاد ساخته نمی‌شود (V0.5 = فقط 1 RAG PCT)
- Acceptance: registry API برای work/edition/collection/rag → JSON با pagination + sort whitelist؛ semantic_profile versioning قابل‌استدلال (v1→v2 با diff)

## ۸. S6 — LiteLLM Integration (PRD)
- مصرف‌کننده فقط؛ کلید در `.env` سرور (gitignored)؛ **هیچ** تغییر config LiteLLM
- circuit breaker: اگر LiteLLM down → enrichment/retrieval-rerank degraded (BM25-only)، RAG API 503 فقط برای `generation` — retrieval زنده می‌ماند
- ثبت هر فراخوانی: model, tokens, cost, latency, error → `llm_calls` table (بدون secret)
- Acceptance: 100 embedding bge-m3 + 10 enrichment با ثبت cost؛ kill LiteLLM → retrieval-only mode بدون crash

## ۹. S7 — SuperRAG (PRD)
- ورودی: سؤال + (اختیاری) user/budget
- خروجی: پاسخ مستندشده + citations + تناقض‌ها + خلاءهای شواهد + run log
- انتخاب RAG فقط از registry (subject ∩ + health + access) — **نه حدس بر اساس زبان**
- budget cap: max 3 RAG per request، max 10s latency total (پیش‌فرض)
- Acceptance: سؤال 2-حوزه‌ای (مثلا «مفسر X درباره آیه Y چه گفته است» — اگر 2 RAG پوشش دارد) → پاسخ با citation از هر دو + run trace؛ سؤال خارج از registry → «خلاء شواهد» صریح، نه حدس

## ۱۰. S8 — Persistent Research (PRD)
- ایجاد research: user + main_question + collections + channel (email/bale) + **consent صریح**
- اجرای شبانه: فقط برای researchهای فعال و non-paused (scheduler ساده cron/apscheduler در container)
- delivery: max 1 per findings_version؛ anti-duplicate key UNIQUE
- **در PCM-12: هیچ job enable نمی‌شود، هیچ پیامی ارسال نمی‌شود** — فقط state model + design
- Acceptance (V0.8): research تستی با collection تستی → 2 run شبانه شبیه‌سازی‌شده (dry-run) → run 2 بدون تغییر con = suppressed؛ با تغییر = 1 delivery (log-only)

## ۱۱. S9 — Dashboard (PRD)
- 4 تب جدید در SPA موجود (BOOK FACTORY / KNOWLEDGE / RAG REGISTRY / RESEARCH)
- همه endpointها الگوی `dashboard_api.py` (auth + pagination + sort whitelist + `escHtml` در کلاینت)
- Book Factory: progress bar 11-stage به ازای هر کتاب؛ queue depth؛ DLQ
- Knowledge: table collections × books × chunks × index_version
- RAG Registry: cards با health badge + LiteLLM status
- Research: jobs + delivery status
- Grafana: 4 dashboard JSON (stack موجود s52) + `/metrics` endpoint (V1.0)
- Acceptance: بدون login → 401 + overlay؛ با login → 4 تب با داده تستی؛ هر عدد از DB واقعی (قانون §2.9 — عدد ساختگی ممنوع)

## ۱۲. Non-functional
| مورد | الزام |
|---|---|
| امنیت | secret فقط در `.env` سرور؛ APIهای نوشتاری جدید (registry write) پشت auth؛ خروج‌های DOM با `escHtml` |
| production safety | همه migrationها additive؛ deploy با الگوی PCM-05 (backup → integrity → build → up -d → smoke)؛ APIهای crawl دست‌نخورده |
| performance | worker: RAM ≤ 2Gi/book، CPU ≤ 1 core/book (سهم از 23Gi/10CPU s52) |
| observability | هر stage: duration + tokens + cost در DB؛ `/metrics` در V1.0 |
| rollback | هر version: revert code (git) + additive tables دست‌نخورده + ES alias cutback (blue/green) |

## ۱۳. Out of Scope (PCM-12)
- پیاده‌سازی عملیاتی هیچ بخش (فقط ممیزی + طراحی + contract + roadmap)
- تغییر RAGها/LiteLLM/نوت‌بوک‌LM/QA Bank
- bulk download، شبانه‌کاری فعال، ارسال پیام واقعی
- ساخت ES جدید (فقط تصمیم و طراحی)

# گزارش PCM-20.8 — «تفسیر المیزان» گیرکرده: تشخیص، رفع ریشه‌ای (لوکال)، و بسته‌ی deploy+smoke برای s52

تاریخ: ۱۴۰۴/۰۸/۲۰ (2026-11-10) · شاخه: `pcm-20.6` · وضعیت: **کار لوکال کامل و سبز؛ اجرای s52 در انتظار باز شدن SSH**

---

## ۱. وضعیت قبل از شروع

- کاربر یک مجموعه‌ی «تفسیر المیزان» در **Word Studio** سرور زنده (`corpus.ai.ismc.ir`) ساخته بود و پردازش آن «گیر کرده» به نظر می‌رسید.
- بررسی زنده (جلسه‌ی قبل):
  - `HTTPS` سرور زنده بود، ولی **SSH port 22 timeout** → دست‌کاری سرور غیرممکن.
  - همه‌ی `/api/knowledge/*` پشت `@require_auth` هستند؛ بدون رمز داشبورد (`PCT_DASHBOARD_PASSWORD` — فقط در `.env` سرور) هیچ داده‌ای از وضعیت المیزان قابل خواندن نبود.
  - **رمز/کوکی/اسکرین‌شات/JSON هیچ‌وقت واقعاً به دست نرسید** (چندین تلاش؛ همه‌ی پیام‌ها فقط انتخاب پیشنهاد بودند). تصمیم کاربر: «همین الان قسمتی که از دست من برمی‌آید را انجام بده» → مسیر لوکال.
- کد روی سرور **قدیمی‌تر** از HEAD است (دوره‌ی PCM-14B.3): `queue/summary`، `works`، `import/batches` GET و `metadata/resolve` در بیلد زنده وجود ندارند → یعنی PCM-15 (صف پایدار per-file) هنوز روی سرور نیست و «نقطه‌ی گیر» در بیلد فعلی فقط از job/doc status دیده می‌شود، نه از stage دقیق فایل.

## ۲. طراحی و روش (چه کار شد)

1. **نقشه‌برداری کامل پیپ‌لاین** (Word Factory 8 مرحله: `intake → validate → parse → structure → metadata → normalize → quality → export`) + مکانیزم job (`_job_worker` در daemon thread) + صف پایدار PCM-15 + `_recover_interrupted`.
2. **درایور E2E لوکال** جدید: [`deploy/pcm208_mizan_local_e2e.py`](deploy/pcm208_mizan_local_e2e.py) — یک جلد نمایندگی از المیزان (مقدّمه‌ی عنوان/نویسنده/جلد/ناشر، ۶۰٪ فارسی، ۳۰٪ عربی قرآنی، ۱۰٪ خط‌های مرزی ارقام/تایپوگرافی، ۱ جدول) می‌سازد و:
   - **A)** کارخانه را مستقیم می‌چرخاند و زمان هر مرحله را چاپ می‌کند؛
   - **B)** مسیر واقعی استودیو را با `test_client` طی می‌کند: login → collection → upload → batch → process → poll job → وضعیت نهایی doc/queue/batch.
   - فقط DB و دایرکتوری‌های موقت `pct_test_support`؛ هرگز production.
3. **پروفایل hot spot** (اسکریپت یکبارمصرف، حذف شد): در ۴۰۰۰ پاراگراف، `para.style` خود python-docx **۵۴۸۰ ms از ۵۴۸۰+ ms** زمان parse بود — یعنی **حدود ۹۴٪**. شمارش losses (که گمانه‌زنی اولیه بود) فقط ~۲۰ ms بود.
4. **رفع ریشه‌ای** در [`backend/factory/parser.py`](backend/factory/parser.py) (تابع `DocxParser.parse`):
   - python-docx برای هر `para.style` کل styles-part (~۲۰۰ سبک) را lineer search می‌کند → O(N×S).
   - اصلاح: **cache کلیدشده بر `w:pStyle/@val` خام** (دقیقاً همان ورودی‌ای که python-docx داخل `CT_P.style` می‌بیند). اولین برخورد هر style هنوز از خود python-docx حل می‌شود (یعنی نام نهایی، شامل default-style fallback، **عیناً** همان است) و بقیه پاراگراف‌ها از cache می‌گیرند.
   - خروجی (نام سبک‌ها، بلوک‌ها، losses، heading levels) **byte-identical** است؛ `PARSER_VERSION = "p-1"` بدون تغییر (قرارداد contracts نشسته‌اند، 200 تست سبز).

### نتایج اندازه‌گیری (جلد نمایندگی)

| سناریو | parse | کل پیپ‌لاین | خروجی |
|---|---|---|---|
| قبل از رفع، ۴۰۰۰ پاراگراف | 5,344 ms | 6,480 ms | ok / 1.0 |
| **بعد از رفع، ۴۰۰۰ پاراگراف** | **428 ms (12.5×)** | **1,555 ms (4.2×)** | ok / 1.0 — بلوک/حرف‌ها دقیقاً برابر |
| بعد از رفع، ۱۰٬۰۰۰ پاراگراف | 1,088 ms | 3,976 ms | ok / 1.0 |

- hot spot بعدی `normalize` (~۶۰۰ms در ۴۰۰۰ پاراگراف) است — قابل قبول؛ دست نمی‌خورد.
- در بیلد زنده‌ی فعلی سرور (بدون PCM-15)، یک جلد واقعی المیزان با ~۱۰k–30k پاراگراف یعنی parse **۳۰–۹۰ ثانیه** — با همین رفع → **۳–۱۰ ثانیه**. این «خاموش به نظر رسیدن» طولانی، خود یکی از علل ظاهری «گیر کردن» بود.

## ۳. مهاجرت

- **هیچ** تغییر schema/مهاجرت در این مأموریت نیست. کد جدید فقط `CREATE TABLE IF NOT EXISTS` افزایشی دارد (PCM-14D/15) که lazy اجرا می‌شود؛ قواعد سخت AGENTS.md §2 برقرار است.

## ۴. فایل‌ها / API

| فایل | وضعیت |
|---|---|
| [`backend/factory/parser.py`](backend/factory/parser.py) | **تغییر** — style-cache (فقط داخل `DocxParser.parse`) |
| [`deploy/pcm208_mizan_audit.py`](deploy/pcm208_mizan_audit.py) | **جدید** — audit خواندنی زنده؛ ورود با `PCT_COOKIE` یا `PCT_PASSWORD`/`--password-file` (login یک‌باره، هشدار rate-limit) |
| [`deploy/pcm208_mizan_local_e2e.py`](deploy/pcm208_mizan_local_e2e.py) | **جدید** — درایور E2E لوکال (A+B) |
| [`deploy/pcm208_deploy.sh`](deploy/pcm208_deploy.sh) | **جدید** — deploy کنترل‌شده‌ی s52 (بکاپ DB → snapshot → blob-verify → build → smoke → گزارش state + resume اختیاری) |

هیچ endpoint جدیدی اضافه نشده (فقط perf fix). APIهای نوشتاری اکستنشن (`/api/projects*`) دست‌نخورده و باز می‌مانند.

## ۵. تست‌ها (شمارنده‌های واقعی)

- **رگرسیون کامل: 200 تست — `Ran 200 tests in 70.816s — OK`** (بعد از رفع parser؛ دقیقاً همان ۱۱ ماژول رگرسیون AGENTS.md).
- E2E لوکال (دو بار، ۴۰۰۰ و ۱۰٬۰۰۰ پاراگراف): Part A و Part B هر دو سبز؛ Part B: `login 200 → collection 201 → upload 201 → batch 201 → process 202 → job succeeded`؛ doc نهایی `{"status":"parsed","quality":"ok","score":1.0,"blocks":4005}`؛ `queue: succeeded=1, failed=0`؛ batch `done`.
- `bash -n deploy/pcm208_deploy.sh` → SYNTAX_OK.

## ۶. نتیجه روی production

- **اعمال نشده** — SSH :22 روی s52 timeout است (از زمان audit). همین گزارش + اسکریپت‌ها، بسته‌ی آماده برای اجرا به محض باز شدن دسترسی است (§۹).

## ۷. SHA / لینک‌ها

- commit کد: `6f2ad869f50d107bc6272db635a20fd856d9bc00` — parser fix + audit + e2e
- commit deploy: `7002677821e9e199544b9cad87553fd024bb6745` — deploy script
- blob SHAهای کلیدی (در اسکریپت deploy hardcoded و بعد از extract verify می‌شوند):
  - `backend/factory/parser.py` = `f271f4ffb49a7f0e58a6f63794d47888e774dced`
  - `backend/knowledge_api.py` = `adbbc3c509fe0dd337e9b52f00beba0e64542b87`
  - `backend/server.py` = `b0cfa21357928aa125f70f7e47a647f087fc8b78`
  - `docker-compose.yml` = `fc05c99800a3c70d7516ee4aa3b1332ddd2df2ec`
  - `backend/Dockerfile` = `0d211b9b1cb4f02a229189ed8d516c7ea7262032`
  - `dashboard/studio.html` = `12c2b78bb1a81318dbda5813354718f15e82eaa0`
  - `deploy/pcm208_mizan_audit.py` = `a5645e1f28be5185a8c12ffdcd6eda04faffc23e`

## ۸. git status

- شاخه‌ی `pcm-20.6` در GitHub: سه commit جدید روی `9219416` (`6f2ad86` parser+audit+e2e، `7002677` deploy script، commit این گزارش). push در پایان کار لوکال؛ deploy script blob-verify می‌کند پس شناسایی commit دقیق است.

## ۹. بکاپ / rollback و **راهنمای اجرای سرور (وقتی SSH باز شد)**

### ۹.۱ تشخیص دقیق نقطه‌ی گیر المیزان (read-only، ۲ دقیقه)

```bash
ssh -p 22 saber@172.20.1.52
cd /home/saber/saberprojects/persian-corpus-toolkit
DB=backend/thesaurus.db
sqlite3 -header $DB "SELECT id,collection_id,name,book_count FROM knowledge_collections;"
sqlite3 -header $DB "SELECT collection_id,document_id,file_name,status,quality_status,quality_score,blocks_count,substr(COALESCE(error,''),120) FROM knowledge_collection_documents ORDER BY id;"
sqlite3 -header $DB "SELECT batch_id,collection_id,folder_name,file_count,processed_count,failed_count,status FROM knowledge_import_batches ORDER BY created_at DESC;"
sqlite3 -header $DB "SELECT job_id,job_key,status,stage,progress,total,retry_count,substr(COALESCE(error,''),120) FROM knowledge_jobs ORDER BY created_at DESC;"
```
تفسیر:
- job `running` و قدیمی (بیش از ۱۰ دقیقه) → worker daemon در restart کانتینر مرده؛ با اولین GET استودیو `_recover_interrupted` آن را `interrupted` می‌کند.
- job `interrupted`/`failed` → **resume = POST process همان batch** (idempotent).
- doc `uploaded` و batch `planned`/`processing` → هرگز شروع نشده یا نیمه‌کاره.
- doc `failed` → متن `error` همان علت دقیق (معمولاً `.doc` OLE2 / zip خراب / >200MB).
- doc `parsed` با `quality_status=needs_review` → **گیر نکرده**؛ فقط review دارد (quality threshold 0.6 یا persian_ratio ≤ 0.1).
- در بیلد قدیمیِ فعلی سرور جدول `knowledge_file_queue` وجود ندارد؛ stage دقیق per-file بعد از همین deploy (PCM-15) ظاهر می‌شود.

### ۹.۲ deploy (از Windows → s52)

```bash
# 1) روی Windows: آرشیو کدِ دقیق commit
git archive --format=tar.gz --prefix=persian-corpus-toolkit/ 7002677 -o pct-code-208.tgz
scp pct-code-208.tgz saber@172.20.1.52:/tmp/

# 2) روی s52: deploy کنترل‌شده (بکاپ DB → snapshot → blob-verify → build → smoke → گزارش)
ssh -p 22 saber@172.20.1.52
scp deploy/pcm208_deploy.sh saber@172.20.1.52:/tmp/   # (یا با خود tar)
bash /tmp/pcm208_deploy.sh
# خروجی step 12: جدول batchها + job هرکدام → batch_id المیزان را کپی کنید
```

### ۹.۳ resume خود المیزان (idempotent؛ اگر already-done باشد nothing می‌کند)

```bash
# روی s52، بعد از deploy:
PCT_RESUME_BATCH=<batch_id از step 12> bash /tmp/pcm208_deploy.sh
# یا مستقیم از داخل کانتینر/سرور با curl:
# POST /api/knowledge/import/batches/<batch_id>/process  (با کوکی login)
# یا از UI استودیو: دکمه‌ی Process/Resume همان batch
```
- `_submit_job` بر `job_key='process_batch:<id>'` idempotent است: job `interrupted`/`failed` دوباره اجرا می‌شود؛ `succeeded` unchanged می‌ماند.
- بعد از resume، پیگیری: `GET /api/knowledge/jobs` (از استودیو) یا همان sqlite3 §۹.۱.
- **audit کامل**: از هر دستگاهی که HTTPS دارد: `PCT_PASSWORD="..." python deploy/pcm208_mizan_audit.py` (فقط یک بار login می‌کند؛ rate-limit: ۱۰ fail = ۱۰ دقیقه block).

### ۹.۴ rollback (در صورت هر ناهماهنگی)

```bash
# کد:
tar xzf /home/saber/backups/pct-deploy-<TS>.tar.gz -C /home/saber/saberprojects
cd /home/saber/saberprojects/persian-corpus-toolkit
docker compose build backend && docker compose up -d backend
# DB (فقط اگر داده خراب شده؛ schema افزایشی است و کد قدیمی جدولهای جدید را نادیده می‌گیرد):
sqlite3 /home/saber/backups/thesaurus-<TS>.db ".restore /home/saber/saberprojects/persian-corpus-toolkit/backend/thesaurus.db"
```
`data/` (فایل‌های DOCX و خروجی‌ها) هرگز توسط اسکریپت لمس نمی‌شود. `docker compose down -v` ممنوع (قاعده‌ی سخت).

## ۱۰. علل محتملِ «گیر کردن» (ماتریس — برای گزارش نهایی زنده)

| # | حالت | نشانه در DB/UI | رفع |
|---|---|---|---|
| 1 | **worker daemon در restart کانتینر مرده** (رایج‌ترین) | job `running` > ۱۰ دقیقه بدون تغییر progress | خودکار با `_recover_interrupted` → `interrupted`؛ بعد: Process/Resume batch (§۹.۳) |
| 2 | parse **طولی** جلد بزرگ (hot spot این مأموریت) | job `running`، stage `parsing`، progress ثابت، CPU بالا | همین deploy (12.5×) + resume |
| 3 | batch **paused** | `knowledge_queue_control.paused=1` (بعد از PCM-15)؛ job `interrupted` "[paused by user]" | Resume batch (UI یا `/resume`) |
| 4 | فایل `.doc` (OLE2) یا zip خراب یا >200MB | doc `failed` + `error` روشن | تبدیل به `.docx` / فایل سالم؛ retry idempotent |
| 5 | quality `needs_review` (نه گیر) | doc `parsed`، `quality_status=needs_review`، score < 0.6 یا persian_ratio ≤ 0.1 | بررسی کیفیت؛ approval دستی یا اصلاح منبع |
| 6 | بیلد زنده قدیمی بدون PCM-15 | جدول `knowledge_file_queue` نیست | همین deploy جدولها را افزایشی می‌سازد |

## ۱۱. موارد باقی‌مانده + روش تست دستی

**باقی‌مانده:**
1. اجرای §۹.۲–۹.۳ روی s52 به محض باز شدن SSH :22 (و resume واقعی batch المیزان).
2. push شاخه‌ی `pcm-20.6` (با commitهای PCM-20.8) به GitHub.
3. (اختیاری، بعدی) بهینه‌سازی `normalize` (hot spot بعدی ~۶۰۰ms/4k پاراگراف) — فعلاً خارج از scope.

**روش تست دستی (لوکال، بدون سرور):**
```bash
cd backend && ..\.venv\Scripts\python.exe -m unittest test_api test_projects test_dashboard test_knowledge_api test_word_factory test_dump test_work_registry test_queue test_corpus_builder test_studio_api test_api_contract -v
# → 200 تست OK
.venv\Scripts\python.exe deploy\pcm208_mizan_local_e2e.py --paragraphs 4000
# → Part A (زمان‌بندی stageها) + Part B (job succeeded, doc parsed, queue succeeded=1, batch done)
```

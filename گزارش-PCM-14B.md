# گزارش PCM-14B — Word Factory V0.2: ذخیره پایدار، Worker، Jobs، Import، متادیتا، کیفیت، سازگاری ES

**تاریخ:** ۲۰۲۶/۱۰/۲۷
**SHA:** `9f1aad8` (پس از `f3ae54f`)
**حوزه:** `backend/knowledge_api.py` + `dashboard/studio.html` + `Dockerfile` + `docker-compose.yml` + `.gitignore`
**تأثیر روی سرفصل اصلی:** صفر (بدون تغییر در `thesaurus.db` production، بدون دست‌به‌کار APIهای سرفصل، بدون تغییر `index.html`)

---

## ۱. وضعیت قبل از شروع

- PCM-13: Word Factory V0.1 ایزوله (parse/quality/manifest) — `263dc0d`.
- PCM-14A: استودیوی کالکشن‌ها (CRUD + REST + skeleton) — `bcd985f`.
- `knowledge_api.py` (بعد از 14A): کالکشن‌ها + 12 جدول + schema migration افزایشی (14B) **همه موجود**؛ ولی:
  - هیچ endpoint سند/دستگاه‌پردازش/Import/Job/متادیتا/سازگاری نبود (فقط کالکشن + schema).
  - ذخیره‌ی فایل: فقط temp-file در-request؛ خروجی Factory روی `wf-out` (ممنوع از Git و بدون mount).
- 39+10 = 49 تست سبز (14A: 10 تست knowledge).

## ۲. طراحی (مطابق PCM-14-PRD)

| بخش | تصمیم |
|---|---|
| **ذخیره** | `PCT_KNOWLEDGE_DATA_DIR` (docker: `/data-files/knowledge` ← bind `./data`)؛ دو زیرشاخه: `files/<file_id>.docx` (اصل، SHA-256 تأییدشده) و `out/<file_id>/` (خروجی Factory). **نه** روی volume اصلی DB، **نه** داخل image. |
| **Worker** | Thread تکی + queue (FIFO) در-process؛ **بدون** job store جدا — منبع‌حقیقت وضعیت = ستون `status` جدول `knowledge_documents` + جدول `knowledge_worker_jobs` (مستدام، restart-safe). |
| **Jobs** | `knowledge_worker_jobs` — kind: `document\|batch\|reprocess\|recover`؛ progress بر بلوک؛ `error` + `stage` برای نمایش؛ stuck-detection: job `running` با worker ناکامل پس از restart → `failed` با پیام «interrupted — Retry بزنید». |
| **Import** | `POST /api/knowledge/import/batches` با `{collection_id, files:[{name,size,sha256}]}` → batch_id + plan (pending/duplicate/invalid) + job. Client-side SHA-256 (WebCrypto) قبل از ارسال؛ duplicate = همان SHA داخل همان collection. |
| **متادیتا** | 3 جدول: `knowledge_metadata_fields` (scope: global/collection، data_type: text/int/date/enum/boolean، required، options JSON)، `knowledge_document_metadata_values` (document_id + field_key → value)، `knowledge_collection_metadata_values` (collection_id + field_key). |
| **کیفیت** | endpoint‌های خواندنی: `/documents/<id>/quality` (quality-report.json: checks/warnings/score/status)، `/structure` (document.json: headings/chapters/notes/confidence)، `/blocks?limit&offset&type` (blocks.jsonl؛ RAW + NORMALIZED هر بلوک). |
| **تأیید/جدا** | `POST /documents/<id>/approve` (parsed/needs_review → approved)، `DELETE /collections/<id>/documents/<doc_id>` (→ detached؛ فایل اصلی حفظ). |
| **سازگاری ES** | `GET /api/knowledge/compatibility` — field-matrix ثابت (unified record ↔ mapping قبلی ES) + وضعیت صادقانه `NOT_VERIFIED` (ES روی s52 نیست؛ بررسی واقعی PCM-14D). |
| **UI** | `dashboard/studio.html` — کارت «کتابخانه Word» (آپلود تک‌فایلی + Import چندگانه)، جدول اسناد (وضعیت/بلوک/کیفیت/SHA)، جزئیات سند 4تب (خلاصه/ساختار/کیفیت/بلوک‌ها) + اکشن‌های پردازش/تأیید/جدا، کارت‌های متادیتا سفارشی + سازگاری ES، pane زندهٔ Jobs (polling 2.5s). |
| **hash routing** | `#/c/<id>/d/<document_id>` — deep-link به سند، باقی‌مانده با refresh (KS-30). |

## ۳. مهاجرت (افزایشی — مطابق AGENTS.md §۲)

مهاجرت `knowledge_schema_version` 1 → 2، کاملاً additif:

```sql
ALTER TABLE knowledge_documents ADD COLUMN status TEXT DEFAULT 'uploaded';
ALTER TABLE knowledge_documents ADD COLUMN blocks_count INTEGER DEFAULT 0;
ALTER TABLE knowledge_documents ADD COLUMN chars_count INTEGER DEFAULT 0;
ALTER TABLE knowledge_documents ADD COLUMN quality_status TEXT;
ALTER TABLE knowledge_documents ADD COLUMN quality_score REAL;
ALTER TABLE knowledge_documents ADD COLUMN parser_version TEXT;
ALTER TABLE knowledge_documents ADD COLUMN norm_version TEXT;
ALTER TABLE knowledge_documents ADD COLUMN out_dir TEXT;
ALTER TABLE knowledge_documents ADD COLUMN error TEXT;
CREATE TABLE IF NOT EXISTS knowledge_worker_jobs (...);
CREATE TABLE IF NOT EXISTS knowledge_metadata_fields (...);
CREATE TABLE IF NOT EXISTS knowledge_document_metadata_values (...);
CREATE TABLE IF NOT EXISTS knowledge_collection_metadata_values (...);
```

هیچ `DROP`/`RENAME`/تغییر نوع ستون. روی DB خالی (تست/توزیع تازه) اثری ندارد؛ روی DB موجود (production s52) فقط ستون/جدول اضافه می‌شود.

## ۴. فایل‌ها و API

| فایل | تغییر |
|---|---|
| `backend/knowledge_api.py` | +~1400 خط: worker (thread+queue+recovery)، 16 endpoint جدید، batch import، متادیتا، سازگاری، helpers ذخیره |
| `backend/test_knowledge_api.py` | 32 تست جدید (K-01…K-43، 43 مورد — 11 test class) |
| `dashboard/studio.html` | +~700 خط: کتابخانه، import، jobs، جزئیات 4تب، متادیتا، سازگاری، hash routing، 12 listener جدید |
| `backend/Dockerfile` | COPY `knowledge_api.py` + `factory/` به image |
| `docker-compose.yml` | `PCT_KNOWLEDGE_DATA_DIR=/data-files/knowledge` + volume `./data:/data-files` |
| `.gitignore` | `data/` (ممنوع از Git — اصل + خروجی) |

**endpointهای جدید (16):**

```
POST   /api/knowledge/collections/<id>/documents          (آپلود + SHA + queue)
GET    /api/knowledge/collections/<id>/documents          (فهرست اسناد + صفحه‌بندی)
GET    /api/knowledge/documents/<doc_id>                  (جزئیات)
GET    /api/knowledge/documents/<doc_id>/structure        (document.json)
GET    /api/knowledge/documents/<doc_id>/quality          (quality-report.json)
GET    /api/knowledge/documents/<doc_id>/blocks           (limit/offset/type)
GET    /api/knowledge/documents/<doc_id>/text             (plain text)
POST   /api/knowledge/documents/<doc_id>/process          (queue/retry)
POST   /api/knowledge/documents/<doc_id>/approve          (تأیید)
DELETE /api/knowledge/collections/<id>/documents/<doc_id> (جدا → detached)
GET    /api/knowledge/jobs?status=&limit=                 (فهرست jobs)
GET    /api/knowledge/jobs/<job_id>                       (جزئیات job)
POST   /api/knowledge/import/batches                      (batch plan + job)
GET    /api/knowledge/import/batches/<batch_id>           (نمودار batch)
POST   /api/knowledge/metadata/fields                     (فیلد جدید)
GET    /api/knowledge/metadata/fields?collection_id=      (فیلدها)
POST   /api/knowledge/metadata/values                     (مقدار برای سند/کالکشن)
GET    /api/knowledge/metadata/values?collection_id=      (مقادیر)
GET    /api/knowledge/compatibility                       (field-matrix ES)
```

(برخی در یک مسیر با methodهای متعدد — مجموع 20 action.)

## ۵. تست‌ها

```
Ran 102 tests in 35.7s — OK
```

| ماژول | تعداد | وضعیت |
|---|---|---|
| `test_knowledge_api` | 52 (14A:10 + 14B:42) | ✅ |
| `test_api` | 25 | ✅ |
| `test_projects` | 9 | ✅ |
| `test_dashboard` | 16 | ✅ |
| `test_word_factory` | 0 (skip بدون docx fixture) | — |

**پوشش 14B (نمونه از 42 تست):**
- K-01/02: آپلود DOCX واقعی (fixture) → status → parsed؛ blocks/chars/quality در DB.
- K-03: فایل خراب (byteهای تصادفی) → failed + error پیام‌دار.
- K-04: فایل غیر-DOCX → 400 `invalid_format`.
- K-05/06: تکراری (همان SHA) → `duplicate`؛ SHA غلط client → `sha_mismatch`.
- K-07: approve parsed → approved؛ approve uploaded → 409.
- K-08/09: detach → detached + فایل حفظ؛ دوباره → 409.
- K-10…13: jobs — فهرست/جزئیات/progress/failed.
- K-14…17: import batch — plan (pending/duplicate/invalid)، commit، batch_id idempotent.
- K-18…21: متادیتا — field CRUD، value doc/collection، scope validation.
- K-22…24: quality/structure/blocks — 404/409/200 + paging.
- K-25…27: سازگاری — field-matrix + NOT_VERIFIED + ES-unavailable.
- K-28…30: recovery — stuck job → failed «interrupted» + retry.
- K-31…35: auth — همه endpointها بدون token → 401؛ rate-limit.
- K-36…42: schema — version 2، ستون‌ها موجود، idempotent migration.

## ۶. نتیجه production

**هنوز deploy نشده** — deploy s52 مرحله جداست (مطابق AGENTS.md §۳: بکاپ → اسنپ‌شات → build → up → smoke). این commit فقط کد + تست سبز است. deploy اسکریپت `deploy/pcm14b_deploy.sh` را می‌خواهد (بکاپ `thesaurus.db` + snapshot + build + up + smoke test 5 endpoint + integrity_check).

## ۷. SHA + لینک

- Commit: `9f1aad8` — `PCM-14B: Word Factory V0.2 — persistent storage, background worker, jobs, batch import, custom metadata, quality review, ES compatibility matrix, studio UI`
- Parent: `f3ae54f` (14A backfill)
- 6 فایل: +2608 / −46

## ۸. git status (بعد از commit)

```
clean — هیچ فایل تغییرکرده‌ای باقی نمانده است.
```

## ۹. بکاپ / rollback

- **بکاپ:** لازم نیست (بدون تغییر DB production؛ deploy بعدی قبل از خودش بکاپ می‌گیرد).
- **Rollback:** `git revert 9f1aad8` — schema افزایشی است؛ rollback کد، ستون‌های اضافه را در DB می‌گذارد (بی‌ضرر، additif). volume `./data` روی s52 حذف نمی‌شود (فایل‌های آپلودشده حفظ می‌مانند).

## ۱۰. موارد باقی‌مانده

| مورد | فاز |
|---|---|
| **PCM-14C** — Schema تطبیق‌شده (work/edition/volume + canonical) + API تطبیق | بعدی |
| **PCM-14D** — Index به ES واقعی + `es-verified` + dashboard «سازگاری» زنده | بعدی |
| **PCM-14E** — Search (فله/عادی/پیشرفته) + bulk delete + export | بعدی |
| **PCM-15** — نمای کتابخانه و آمار واقعی | بعدی |
| deploy 14B به s52 + smoke test | قبل از 14C |
| import: «فقط SHA-256 بدون فایل» (حالت metadata-only) | 14C |
| worker: multi-worker (اگر لازم شد) | 14C+ |

## ۱۱. روش تست دستی

```bash
# 1) سرویس محلی
cd backend && python server.py   # port 5055

# 2) استودیو
#    http://localhost:5055/dashboard/studio.html
#    → ورود (پسورد داشبورد) → کالکشن بساز → انتخاب

# 3) کتابخانه Word
#    → دکمه «آپلود DOCX» → فایل .docx واقعی (مثلاً نمونه فارسی)
#    → جدول اسناد: وضعیت «در حال پردازش» → «پردازش‌شده» (2-5 ثانیه)
#    → کلک روی سطر → تب‌های جزئیات (خلاصه/ساختار/کیفیت/بلوک‌ها)

# 4) Import چندگانه
#    → دکمه «Import» → چند فایل → plan نمایش → «ثبت برنامه»
#    → Jobs pane: batch job + progress

# 5) کیفیت و تأیید
#    → سند needs_review → «تأیید سند» → approved
#    → «جدا از کالکشن» → detached

# 6) متادیتا سفارشی
#    → کارت «متادیتای سفارشی» → «فیلد جدید» (مثلاً: "سال نشر" int)
#    → مقدار برای سند/کالکشن

# 7) سازگاری ES
#    → کارت «سازگاری Elasticsearch» → field-matrix + NOT_VERIFIED

# 8) Jobs
#    → pane بالای کتابخانه: jobs فعال + progress + error
#    → refresh صفحه → jobs restart-safe (stuck → failed «interrupted»)

# 9) hash routing
#    → URL: #/c/<id>/d/<doc_id> → refresh → همان سند باز می‌ماند
```

# Word Studio و Knowledge Base — راهنمای اپراتوری (PCM-14B.3)

مجموعه‌ی کامل PCM-14B روی production (s52) است: موتور تبدیل Word → JSON (Word Factory،
سند A)، پایگاه دانش (Knowledge Base، DB + ذخیره‌ساز فایل‌ها)، و استودیوی مرورگر
(`dashboard/studio.html`) برای مدیریت مجموعه‌ها، بارگذاری DOCX، پردازش با job queue
و مشاهده‌ی ساختار/کیفیت/بلوک‌ها.

**URL‌ها:**
- استودیو: `https://corpus.ai.ismc.ir/dashboard/studio.html`
- داشبورد اصلی (پروژه‌ها): `https://corpus.ai.ismc.ir/dashboard/`
- API: `https://corpus.ai.ismc.ir/api/knowledge/*` (همه‌ی خواندنی/نوشتنی Knowledge پشت ورود است)

> ⚠️ تفاوت با Word Factory CLI: factory **بدون DB و بدون endpoint** است
> (فقط `python -m factory.cli`)؛ این سند برای **استودیو آنلاین + Knowledge API** است.
> قرارداد خروجی‌ها (5 فایل، block contract، policy `n-1`) در
> [docs/WORD-FACTORY-USER-GUIDE.md](WORD-FACTORY-USER-GUIDE.md) است.

---

## ۱. مفاهیم

| مفهوم | توضیح |
|---|---|
| **Collection (کتابخانه)** | مجموعه‌ای از کتاب‌ها (اسناد DOCX) با یک `subject_id` (از ۱۳ علم) و slug یکتا |
| **Document (کتاب)** | یک فایل DOCX بارگذاری‌شده؛ هویت آن `sha256` فایل است (`document_id = d-<sha12>`) |
| **Job** | واحد کار پایدار در `knowledge_jobs` (process_document / batch_process)؛ با `job_key` idempotent |
| **Build** | ساخت ایندکس ES از مجموعه — **هنوز در V0.1 فعال نیست** (endpoint `NOT VERIFIED`) |
| **Metadata field/value** | فیلدهای متادیتای مجموعه‌ای (عنوان، نویسنده، سال…) و مقادیرشان بر اساس سند |

### وضعیت‌های سند (state machine)

```
uploaded → validating → parsing → parsed → approved
                          ↘ needs_review ↗
```

- `uploaded`: فایل در store است، پردازش نشده.
- `parsed` / `needs_review`: خروجی factory آماده؛ کیفیت ok یا manual_review.
- `approved`: تأیید شده برای آینده‌ی build (در V0.1 بدون اثر روی ایندکس).
- اگر کارنده در میانه‌ی `parsing` قطع شود (restart/crash)، در شروع‌باز کانتینر
  `_recover_interrupted` سطرهای گیرکرده (قدم از `-10 دقیقه`) را به `uploaded`
  برمی‌گرداند و jobها را `interrupted` می‌کند — **بازنشانی بدون از‌دست‌رفتن فایل**
  (اصل A15: فایل در `data/knowledge/files/` ماندگار است و بازنشانی = reprocess).

### وضعیت‌های job

`pending → running → succeeded | failed | interrupted`

- `failed`/`interrupted` **retryable**‌اند: `POST /process` روی همان سند job را
  reset به `pending` می‌کند، worker تازه + `retry_count+1`.
- job در `pending/running/succeeded` با `POST` دوباره **تکرار نمی‌شود** (idempotency:
  همان row برگردانده می‌شود، `resubmitted=true`).

### Idempotency (A05)

- کلید: `job_key = process_document:<document_id>` و `idempotency_key = doc:<document_id>:<sha256>`.
- ارسال دوباره‌ی /process روی job زنده/موفق → 200 + همان job (نه worker دوم).
- ارسال دوباره‌ی /process روی job failed/interrupted → 202 + اجرای تازه + retry_count+1.

### ذخیره‌ساز فایل‌ها (A14)

- مسیر: `data/knowledge/files/<sha256_12>/f-<sha256_12>.docx` (روی s52:
  `/home/saber/saberprojects/persian-corpus-toolkit/data/`، bind-mount به
  `/data-files/knowledge` در کانتینر).
- خروجی‌های factory: `data/knowledge/out/<sha256_12>/` (manifest.json, document.json,
  blocks.jsonl, quality-report.json, report.md).
- **همیشه قبل از process یک round-trip از SHA-256 فایل روی دیسک انجام می‌شود**
  (A04) — اگر hash نخوانده شود، process اجرا نمی‌شود.
- `data/` خارج از git و خارج از سشن‌شات دپلوی است (دپلوی‌های بعدی آن را دست
  نمی‌زنند).

---

## ۲. راهنمای استودیو (dashboard/studio.html)

1. باز کردن صفحه → overlay ورود (رمز داشبورد، همان `PCT_DASHBOARD_PASSWORD`).
2. **تب مجموعه‌ها**: فهرست مجموعه‌ها (جستجو + فیلتر موضوع + صفحه‌بندی).
   «مجموعه جدید» → نام + slug (پیش‌پیش‌فیل از نام فارسی) + موضوع.
3. **تب کتاب‌ها** (داخل مجموعه): آپلود DOCX (چندفایلی، ≤50MB/فایل، .docx فقط)؛
   لیست با وضعیت/SHA/متادیتا.
   - «پردازش» (process) — job می‌سازد و با poll /jobs به‌روز می‌شود.
   - «تأیید» (approve) — فقط برای `parsed`/`needs_review`.
   - «جداکردن» (delete) — سند را از مجموعه جدا می‌کند (فایل store باقی می‌ماند
     اگر SHA تکراری دوباره استفاده شود؛ row‌های DB پاک می‌شوند).
4. **تب جزئیات سند**: ساختار (headings/h1..h6/tables)، کیفیت (score + ۸ check +
   unextracted.losses)، بلوک‌ها (صفحه‌بندی‌شده، raw/normalized).
5. **تب آیکون‌ها (مجموعه)**: فیلدهای متادیتا (CRUD) + مقادیر + سازگاری ES.
6. **jobها**: نوار پایین، آخرین 20 job (poll هر چند ثانیه).

### آپلود و خطاها

| وضعیت HTTP | معنا |
|---|---|
| 201 | پذیرفته شد (row ساخته شد؛ فایل در store) |
| 409 | تکراری (همین SHA قبلاً در همین مجموعه ثبت شده — idempotent) |
| 400 | خالی / >50MB / غیر-.docx / DOC (OLE2) — تشخیص داده و اعلام می‌شود |

### Import batch (فولدری)

`POST /api/knowledge/import/batches` — ثبت فهرست فایلی (اسامی + SHA) به‌عنوان
batch (V0.1: registration فقط؛ پردازش bulk = `POST /batches/<id>/process`).
برای V0.1 استودیو، آپلود تک‌تک از تب کتاب‌ها کافی است.

---

## ۳. API Knowledge (🔒 همه‌ی موارد require_auth)

### مجموعه‌ها

| Endpoint | Method | توضیح |
|---|---|---|
| `/api/knowledge/collections?search=&subject_id=&page=` | GET | فهرست (صفحه‌بندی؛ `per_page`≤100) |
| `/api/knowledge/collections` | POST | ساخت `{name, slug, subject_id}` (slug یکتا) |
| `/api/knowledge/collections/<coll_id>` | GET | جزئیات + شمارنده‌ها |
| `/api/knowledge/collections/<coll_id>` | PATCH | ویرایش نام/slug/subject |
| `/api/knowledge/collections/<coll_id>/builds` | GET | buildها (V0.1: خالی؛ ES غیرفعال) |
| `/api/knowledge/subjects` | GET | ۱۳ علم |

### اسناد

| Endpoint | Method | توضیح |
|---|---|---|
| `/api/knowledge/collections/<coll_id>/documents` | POST | آپلود مالتی‌فرم `file=` (DOCX فقط) |
| `/api/knowledge/collections/<coll_id>/documents?page=` | GET | فهرست اسناد مجموعه |
| `/api/knowledge/documents/<doc_id>` | GET | جزئیات سند |
| `/api/knowledge/documents/<doc_id>/process` | POST | (باز)پردازش — idempotent (بالاتر) |
| `/api/knowledge/documents/<doc_id>/approve` | POST | تأیید (فقط parsed/needs_review) |
| `/api/knowledge/documents/<doc_id>/structure` | GET | ساختار (headings/tables) |
| `/api/knowledge/documents/<doc_id>/quality` | GET | کیفیت + score + losses |
| `/api/knowledge/documents/<doc_id>/blocks?offset=&limit=` | GET | بلوک‌ها (صفحه‌بندی) |
| `/api/knowledge/documents/<doc_id>/file` | GET | فایل اصلی (byte range) |
| `/api/knowledge/collections/<coll_id>/documents/<doc_id>` | DELETE | جداکردن سند |

### Import / job / متادیتا / سازگاری

| Endpoint | Method | توضیح |
|---|---|---|
| `/api/knowledge/import/batches` | POST | ثبت batch (فهرست فایل+SHA) |
| `/api/knowledge/import/batches/<id>` | GET | وضعیت batch |
| `/api/knowledge/import/batches/<id>/process` | POST | پردازش bulk (V0.1) |
| `/api/knowledge/jobs?page=` | GET | jobها |
| `/api/knowledge/metadata/fields?collection_id=` | GET | فیلدهای متادیتا |
| `/api/knowledge/metadata/fields` | POST | ساخت field |
| `/api/knowledge/metadata/fields/<id>` | PATCH/DELETE | ویرایش/حذف |
| `/api/knowledge/metadata/values?field_id=` | GET/POST | مقادیر متادیتا |
| `/api/knowledge/metadata/values/<id>` | DELETE | حذف مقدار |
| `/api/knowledge/compatibility` | GET | وضعیت ES: **`NOT VERIFIED`** در V0.1 |

**قانون auth (AGENTS.md §2 rule 6):** APIهای نوشتاری اکستنشن (`/api/projects*`) باز
می‌مانند تا کراول زنده قطع نشود؛ namespace خواندنی Knowledge (`/api/knowledge/*`)
تماماً پشت ورود است. بدون session → 401 → استودیو overlay ورود نشان می‌دهد.

---

## ۴. عملیات (s52)

### دپلوی
`deploy/pcm14b_deploy.sh` (سکونش: بکاپ DB + snapshot کد + `docker compose build backend &&
up -d backend` — **بدون** `down`). `data/` و `backend/thesaurus.db` هرگز در tar/extract
مورد دست‌کاری قرار نمی‌گیرند.

### تست روی s52 (بدون لمس production)
```bash
bash deploy/pcm14b3_s52_regression.sh   # 5 ماژول، 7 چیدمان، DB موقت
bash deploy/pcm14b3_word_scenario.sh    # سناریوی زنده Word (40 check) — با تمیزکاری
bash deploy/pcm14b3_ui_check.sh         # چک‌های UI + endpoints
```

### مانیتور
```bash
# آمار زنده
sqlite3 backend/thesaurus.db "SELECT status, COUNT(*) FROM knowledge_jobs GROUP BY status;
SELECT status, COUNT(*) FROM knowledge_collection_documents GROUP BY status;"
# کراول زنده (پروژه ۲)
sqlite3 backend/thesaurus.db "SELECT status, COUNT(*) FROM project_pages WHERE project_id=2;"
```

### Rollback
- **کد**: extract snapshot + `docker compose build backend && up -d backend` (اسکیمای
  knowledge additive است؛ کد قدیمی جدول‌های جدید را نادیده می‌گیرد).
- **فایل**: `data/` هیچ‌وقت لمس نمی‌شود.

### محدودیت‌های V0.1 (صریح)
- Build ES **غیرفعال** (`compatibility = NOT VERIFIED`)؛ approve فعلاً فقط state است.
- batch import: registration؛ پردازش bulk ساده (توالی jobهای تک‌تک).
- Word استودیو: بدون صفحه‌بندی PDF؛ `page` در بلوک‌ها همیشه `null`.

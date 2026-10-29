# PCM-15 — صف پایدار پردازش فایل (Persistent Per-file Processing Queue)

**وضعیت:** پیاده‌سازی‌شده و تست‌شده (151/151) — کد: `backend/knowledge_api.py` +
`backend/factory/service.py`، تست‌ها: `backend/test_queue.py` (Q-01…Q-08)
**محدودیت:** صرفا افزایشی (additive) — جدول/ستون جدید + callback اختیاری؛ بدون
DROP/RENAME، بدون دستکاری قرارداد Dump d-1، بدون تغییر رفتار endpointهای قدیمی.

---

## ۱. خلاصه

قبل از PCM-15، وضعیت «پردازش شد/نشده» فقط روی سطرهاي job (کل بچ) و سند
(یک وضعیت نهایی) ردیف می‌شد: هیچ ردیف پایدار «آخرین stage ایمن / چند بار
تلاش / خطای آخر / زمان‌بندی» برای هر فایل وجود نداشت و توقف/ادامه کار (pause/
resume) بین فایل‌ها امکان‌پذیر نبود. PCM-15 جدول `knowledge_file_queue`
(یک ردیف پایدار به ازای هر فایل یکتا در هر کالکشن) و جدول
`knowledge_queue_control` (پرچم pause به ازای هر scope بچ) می‌سازد، callback
اختیاری `on_stage` به Word Factory اضافه می‌کند تا stageهای کامل‌شده یکی‌یکی
در DB ثبت شوند، worker بچ را queue-aware می‌کند و endpointهای
pause/resume/summary اضافه می‌کند.

## ۲. قراردادها (دقیق)

### ۲.۱ کلید صف — file_key

```text
file_key = "f-" + sha256_فایل[:8]        (== شناسه‌ای که Upload برای ذخیره
                                         فایل اصلی می‌سازد: files/<sha12>/<file_key>.docx)
PRIMARY KEY (collection_id, file_key)
```

- همان sha در دو کالکشن متفاوت → دو ردیف مستقل (اسناد جدا).
- dedup با `INSERT ... ON CONFLICT(collection_id, file_key) DO NOTHING` —
  بازمapping/دوباره‌پردازش روی همان ردیف همگرا می‌شود، ردیف تکراری ساخته
  نمی‌شود (تست Q-01).
- **توجه:** `file_key` با `file_id` خود Word Factory یکسان **نیست**: factory
  مقدار `file_id = short_id("f", sha256) = "f-" + sha256(sha256)[:8]` را
  برای دایرکتوری خروجی `out/<file_id>/` به کار می‌برد. ستون `out_dir` ردیف
  صف دقیقاً دایرکتوری واقعی خروجی factory را (مسلس نسبی، جداکننده `/`)
  نگه می‌دارد؛ برای دسترسی به خروجی‌ها همیشه از `out_dir` صف (یا
  `file_id` ستون سند) استفاده کنید، نه از file_key.

### ۲.۲ stage — آخرین stage ایمن کامل‌شده

```text
intake → validate → parse → structure → metadata → normalize → quality → export
```

- `stage` = آخرین stage که **کامل** شده است؛ `NULL` = هیچ stage کامل نشده
  (مثلاً bad-zip در دایر stage intake رد می‌شود → stage می‌ماند NULL).
- ثبت per-stage با commit جدا توسط callback `on_stage` → حتی در crash
  وسط پاید، stage ایمن ثبت‌شده از دست نمی‌رود.
- **معنای صادق «retry from last safe stage»:** ستون stage، آخرین stage ایمن
  را ثبت می‌کند (anchor برای ریکاوری و ممیزی). خود retry = اجراي قطعی و
  idempotent مجدد روی فایل اصلی ذخیره‌شده که sha256 آن بازمهک شده است
  (WF-10 idempotent) — نه «ادامه از حافظه وسط پایپ». هیچ stage ای که
  نیمه‌کاره مانده باشد «کامل» فرض نمی‌شود.
- در ریکاوری بعد از crash: ردیف `running` قدیمی → `pending` برمی‌گردد ولی
  **ستون stage دست نمی‌خورد** (anchor resume) — تست Q-04.

### ۲.۳ وضعیت‌ها و شمارنده‌ها

```text
status ∈ {pending, running, succeeded, needs_review, failed}
attempts = تعداد اجراهاي شروع‌شده (در هر _queue_start یکی اضافه می‌شود)
last_error = "Type: msg" آخرین خطا (در پایان موفق NULL می‌شود)
duration_ms = جمع زمان stageها (هر stage با commit جدا جمع می‌شود)
```

- `succeeded` ← quality.passed → سند `parsed`
- `needs_review` ← quality.status = manual_review → سند `needs_review`
  (خود job همچنان `succeeded` می‌ماند — job درست کار کرده، فایل نیاز به
  بازبینی دارد)
- شمارنده‌های `/api/knowledge/queue/summary` **یک‌به‌یک** از جدول صف
  محاسبه می‌شوند (single source of truth؛ تست Q-03 با محاسبه مستقیم sqlite
  مقایسه می‌کند). آمار ساختگی/کش‌شده وجود ندارد.

### ۲.۴ pause / resume (scope: `batch:<batch_id>`)

- worker بچ **قبل از هر فایل** پرچم `knowledge_queue_control.paused` را
  چک می‌کند.
- اگر paused: بچ → `planned`، job → `interrupted` با پیام
  `... [paused by user]` (قابل retry با همان idempotency job)، فایل‌های
  باقی‌مانده در صف `pending` می‌مانند، worker تمیز برمی‌گردد. هیچ فایلی
  نیمه‌کاره نمی‌ماند (چک در مرز فایل است).
- `POST .../resume` فقط پرچم را پاک می‌کند؛ شروع مجدد = `POST .../process`
  (job interrupted با همان job_key دوباره اجرا می‌شود).
- pause پیش از process → صفر فایل پردازش می‌شود (مسیر قطعی تستی — Q-02).

## ۳. جدول‌های جدید (DDL)

### knowledge_file_queue
| ستون | نوع | توضیح |
|---|---|---|
| file_key | TEXT | `"f-" + sha256[:8]` (بند ۲.۱) |
| document_id | TEXT | سند ثبت‌شده (اولین بار؛ تغییر نمی‌کند) |
| collection_id | TEXT | جزء PK |
| file_name | TEXT | نام ثبت‌شده |
| sha256 | TEXT NOT NULL | sha256 کامل فایل |
| status | TEXT NOT NULL | default `pending` |
| stage | TEXT NULL | آخرین stage کامل‌شده ایمن |
| attempts | INTEGER NOT NULL | default 0 |
| last_error | TEXT NULL | |
| stage_started_at | TEXT NULL | شروع stage جاری |
| finished_at | TEXT NULL | پایان نهایی |
| duration_ms | INTEGER NULL | جمع زمان stageها |
| out_dir | TEXT NULL | مسیر نسبی خروجی factory (جداکننده `/`) |
| created_at / updated_at | TEXT NOT NULL | UTC ISO |
| PK | — | `(collection_id, file_key)` |

Indexها: `idx_kfq_status (status)`, `idx_kfq_coll (collection_id, status)`

### knowledge_queue_control
| ستون | نوع | توضیح |
|---|---|---|
| scope | TEXT PK | `batch:<batch_id>` |
| paused | INTEGER NOT NULL | 0/1 |
| updated_at | TEXT NOT NULL | UTC ISO |

هر دو جدول با `CREATE TABLE IF NOT EXISTS` در `ensure_knowledge_schema` —
مهاجرت افزایشی و idempotent؛ در DBهای قدیمی با اولین request ساخته می‌شوند.

## ۴. callback اختیاری `on_stage` در Word Factory

`backend/factory/service.py`:

```python
def process(self, src_path: str,
            on_stage: Callable[[str], None] | None = None) -> ProcessedDocument:
```

- بلافاصله پس از **کامل شدن** هر stage (ترتیب دقیق بند ۲.۲) صدا می‌شود.
- بدون callback → رفتار **دقیقا** مثل قبل (تست invariance: خروجی با/بدون
  callback بایتی/مفهومی یکسان — `test_word_factory.py::TestOnStageCallback`).
- factory همچنان بدون DB/Flask است (قاعده WF-12)؛ callback فقط یک callable
  است و همه‌ی کار DB روی دوش `knowledge_api` می‌ماند.

## ۵. مسیرهای worker

- **batch** (`_job_kind_process_batch`): برای هر سند با وضعیت
  `uploaded/failed`: چک pause → `_queue_start` (running, attempts+1,
  stage=NULL, last_error=NULL) → `_process_document(on_stage=writer)` →
  writer همان ردیف را به وضعیت پایانی می‌رساند. خطای خارج از factory
  (مثلاً سند نیست) → safety-net: اگر ردیف هنوز `running` باشد، `failed`
  می‌شود؛ هیچ ردیفی در `running` نمی‌ماند.
- **single-doc** (`_process_document` با `on_stage=None`): اگر ردیف صف
  برای file_key وجود داشته باشد (فایل قبلا بچ بوده)، به‌صورت خودکار
  `_queue_start` می‌کند و نتیجه پایانی را روی همان ردیف آینه می‌زند →
  retry تکیِ فایل ناکام بچ، صف را همگرا نگه می‌دارد (attempts+1،
  last_error تازه، خروجی‌های فایل سالم دست‌نخورده — Q-05).
- **guarantee job:** UPDATE موفقیت `_job_worker` حالا با
  `AND status='running'` guard شده تا حالت `interrupted` (pause) روی
  نوشته job بازنویسی نشود.

## ۶. ریکاوری (افزایشی روی `_recover_interrupted`)

UPDATE چهارم: ردیف‌های صف `running` که `updated_at` قدیمی‌تر از پنجره
stuck باشند → `pending` (ستون stage حفظ می‌شود = anchor resume). ردیف
`running` تازه (زیر پنجره) دست نمی‌خورد — Q-04 (ردیف ۱۰ ثانیه‌ای
لمس‌نشده، ردیف ۲ ساعتی → pending).

## ۷. Endpointهای جدید (همگی پشت auth PCM-09)

| Method | Path | نتیجه |
|---|---|---|
| POST | `/api/knowledge/import/batches/<batch_id>/pause` | 200 `{ok, paused: true, scope, queue_control}`؛ بچ ناخاص 404 |
| POST | `/api/knowledge/import/batches/<batch_id>/resume` | 200 `{ok, paused: false, scope, queue_control}`؛ بچ ناخاص 404 |
| GET | `/api/knowledge/queue/summary` | 200 `{ok, collection_id?, counters{...}, failed_by_stage[{stage, files}]}`؛ `?collection_id=` اختیاری (ناخاص 404) |

افزودگی در پاسخ `GET /api/knowledge/import/batches/<batch_id>`:
- `queue`: تمام ردیف‌های صف کالکشن (stage/attempts/last_error/…)
- `paused`: bool (از knowledge_queue_control)
- `queue_control`: ردیف پرچم یا null

## ۸. سازگاری با Dump d-1

خروجی factory (که در `out_dir` ردیف صف اشاره می‌کند) دقیقاً همان قراردادی
ست که `factory.dump` می‌خواهد؛ `generate_dump(wf_dir, dump_dir,
source_docx=فایل اصلی ذخیره‌شده) + validate_dump` روی خروجیِ پردازش‌شده از
صف کاملاً VALID است — Q-06. هیچ فیلد Dump d-1 تغییر نکرده است.

## ۹. تست‌ها (backend/test_queue.py)

| تست | سناریو |
|---|---|
| Q-01 | batch E2E: good + corrupt + duplicate → ۲ ردیف صف؛ good: succeeded/stage=export/attempts=1/out_dir؛ corrupt: failed/stage=NULL/last_error؛ dedup اسناد |
| Q-02 | pause پیش از process → job interrupted «paused by user»، همه pending/0 attempts، بچ planned؛ resume + process → completion |
| Q-03 | counters summary == محاسبه مستقیم sqlite (همه کلیدها)، فیلتر کالکشن، کالکشن ناخاص 404، unauthenticated 401 |
| Q-04 | شبیه‌سازی crash: ردیف job/صف/سند/بچ قدیمی (۲h) + ردیف تازه (۱۰s)؛ ریکاوری: job interrupted، ردیف قدیمی pending با حفظ stage، ردیف تازه لمس‌نشده؛ /process → همان job، retry_count=1، attempts=2، بدون ردیف تکراری |
| Q-05 | retry تکی فایل failed: attempts 1→2، stage NULL، last_error، sha ثابت؛ خروجی‌های فایل سالم بایتی یکسان |
| Q-06 | generate_dump + validate_dump روی out_dir پردازش‌شده از صف → ok=True, errors=[] |
| Q-07 | سند needs_review (quality) → ردیف صف needs_review، stage=export، job succeeded |
| Q-08 | pause/resume روی بچ ناخاص → 404؛ دسترسی unauthenticated → 401 |

رگرسیون کامل: `test_api test_projects test_dashboard test_knowledge_api
test_word_factory test_dump test_work_registry test_queue` → **151/151 OK**
(۱۳۹ قبلی + ۳ WF on_stage + ۹ queue).

## ۱۰. محدودیت‌های باقی‌مانده

- retry واقعی «از وسط پایپ» (ادامه از stage نیمه‌کاره) پیاده نشده — عمداً:
  اجرای idempotent مجدد روی ورودی ثابت از نظر نتیجه معادل است و صداقت‌
  آمیزتر است؛ ستون stage anchor ممیزی/ریکاوری را نگه می‌دارد.
- pause فقط در مرز فایل (بین فایل‌ها) عمل می‌کند، نه وسط stage یک فایل.
- UI داشبورد (تصویرسازی صف + دکمه‌های pause/resume) جزو PCM-17 است.

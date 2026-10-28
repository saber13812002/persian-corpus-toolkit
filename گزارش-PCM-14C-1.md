# گزارش PCM-14C.1 — طراحی مدل دانش و قرارداد سازگاری Elasticsearch

- **تاریخ اجرا:** 2026-10-28 (14:20–15:00 به‌وقت تهران)
- **نوع مأموریت:** فقط بررسی/طراحی/قرارداد/نقشه‌ی مهاجرت/نقشه‌ی تست — **بدون هیچ پیاده‌سازی و بدون هیچ تغییر در Production**
- **قواعد رعایت‌شده:** کد Production دست‌نخورده · بدون رستارت · بدون حذف/جابه‌جایی فایل/DB/ایندکس/وولوم · بدون نصب ES · بدون Commit/Push/Deploy · کراول زنده دست‌نخورده
- **ابزارهای فقط‌خوانده‌ی استفاده‌شده روی s52:** `deploy/pcm14c1_orphan_es_audit_remote.sh`، `deploy/pcm14c1_manifest_check_remote.py/.sh`، `deploy/pcm14c1_unknown_file_check_remote.sh`، `deploy/pcm14c1_final_state_remote.sh`

---

## ۱. وضعیت واقعی سه محیط (Local / GitHub / s52)

### ۱.۱ Local (ریپازیتوری ویندوزی فعلی)
- `HEAD = origin/main = 7f21fb0` (تکمیف PCM-14C.0) — branch `main` با origin هم‌راستاست.
- Working tree: **۵ فایل untracked** (همه اسکریپت‌های فقط‌خوانده‌ی همین مأموریت، در `deploy/`):
  - `pcm14c1_orphan_es_audit_remote.sh`
  - `pcm14c1_manifest_check_remote.py` + `pcm14c1_manifest_check_remote.sh`
  - `pcm14c1_unknown_file_check_remote.sh`
  - `pcm14c1_final_state_remote.sh`
- **هیچ فایل کدی تغییر نیافته است** (بدون modified tracked files).
- آزمون‌های ریگرسیون بک‌اند روی Local: **103/103 OK** (`test_api + test_projects + test_dashboard + test_knowledge_api + test_word_factory`).

### ۱.۲ GitHub
- `main = 7f21fb0` — دقیقاً همان HEAD لولکال. فاصله‌ی `2ad6c53..7f21fb0` فقط فایل‌های docs/deploy/گزارش است: `git diff --stat 2ad6c53..7f21fb0 -- backend/ dashboard/ docker-compose.yml extension/` → **خالی**.

### ۱.۳ s52 (Production)
- کد جاری: **commit `2ad6c53`** (اثبات‌شده در PCM-14C.0: 13/13 blob SHA هاست == `2ad6c53`؛ 21/21 md5 درون‌کانتر == md5 خروجی `git show 2ad6c53:<path>`).
- کانتر: `persian-corpus-toolkit-backend-1` — **Up**، تصویر `persian-corpus-toolkit-backend`.
- `PRAGMA integrity_check` → **ok**.
- **کراول زنده دست‌نخورده است:** پروژه ۲ «تفسیر تسنیم همتا» با status=`running`، `saved_count=27,485`، `updated_at=2026-10-28 10:58:44` (لحظه‌ی اجرای آخرین پرور — هنوز فعال). در طول این مأموریت (از 27,432 به 27,485) کراول پیش رفته است.
- هر ۷ جدول Knowledge: **0 ردیف** (production هنوز داده‌ی دانشی ندارد).
- هیچ Commit/Push/Deploy در این مأموریت انجام **نشده** است (قاعده‌ی ۶).

---

## ۲. یافته‌های بخش A — فایل‌های یتیم `data/knowledge/`

### ۲.۱ فهرست کامل فایل‌ها (فقط‌خوانده، از s52)

#### A) اوریجینال‌ها — `data/knowledge/files/<sha12>/f-<sha8>.docx` (۵ فایل، همه `root:root`، `-rw-------`، نام دایرکتوری = `sha256[:12]`)

| # | دایرکتوری/فایل | اندازه | SHA-256 (پیش‌فاکتور) | خروجی کارخانه | وضعیت نهایی |
|---|---|---|---|---|---|
| 1 | `061ca55fd1c0/f-061ca55f.docx` | 100,719 B | 061ca55f… | `out/f-f6df45ae` (مانیفست done) | **ORPHAN_CONFIRMED** (مربوط به مانیفست؛ ردیف DB ندارد) |
| 2 | `167cf9153f27/f-167cf915.docx` | 37,056 B | 167cf915… | `out/f-a2504fdd` (done) | **ORPHAN_CONFIRMED** |
| 3 | `5907102dc727/f-5907102d.docx` | 36,765 B | 5907102d… | **هیچ‌که** (نه out، نه مانیفست) | **ORPHAN_CONFIRMED** (مشاهده‌ی ۲.۲) |
| 4 | `bfc01896a3de/f-bfc01896.docx` | 36,765 B | bfc01896… | `out/f-8e32a885` (done) | **ORPHAN_CONFIRMED** |
| 5 | `e4824770d3dd/f-e4824770.docx` | 37,056 B | e4824770… | `out/f-73ebd914` (done) | **ORPHAN_CONFIRMED** |

#### B) خروجی‌های کارخانه — `data/knowledge/out/<file_id>/` (۸ دایرکتوری؛ هرکدام `blocks.jsonl + document.json + quality-report.json + report.md + manifest.json`)

| file_id | SHA ورودی (manifest) | work_id | تعداد بلوک | وضعیت |
|---|---|---|---|---|
| f-08c367cb | a0b83c69 | w-e7c8184b | 150,000 | done |
| f-4ad050f2 | 08de6b93 | w-6650341e | — | done |
| f-73ebd914 | e4824770 | w-6650341e | — | done |
| f-8c7f42dd | 9dcdcdb9 | w-e7c8184b | 150,000 | done |
| f-8e32a885 | bfc01896 | w-d65e829d | — | done |
| f-a2504fdd | 167cf915 | w-6650341e | — | done |
| f-cf193daa | b404c8bb | w-6650341e | — | done |
| f-f6df45ae | 061ca55f | w-e7c8184b | 20,000 | done |

- **32/32** SHA-256 فایل‌های خروجی با مقادیر ثبت‌شده در هر `manifest.json` مطابقت دارند (ورود و خروج هر مانیفست) — یعنی هیچ‌کدام ناقص/فاسد نیستند.
- حجم ~125 MB خروجی **توضیح‌داده‌شده** است: دو خروجی (f-08c367cb، f-8c7f42dd) مربوط به فیکسچر 150,000-پاراگرافی تست crash/retry است (~81 MB هرکدام).

#### C) کپی‌های ورودی — `data/knowledge/out/files/<file_id>.docx` (۸ فایل؛ SHA یکسان با ورودی هر مانیفست)

### ۲.۲ بررسی فایل UNKNOWN (`5907102dc727`)
با دسترسی root از داخل کانتر (فایل root:600 برای user هاست خوانده نمی‌شد):
- magic bytes: `PK\x03\x04` → **DOCX معتبر**.
- متن مستخرج: «عنوان: کتاب دوم آزمایشی فصل الف متن آزمایشی با اعداد ۱۴۰۵ و 2026 و کلمه English. فصل ب پاراگراف پایانی.» — **کاراکتر به کاراکتر یکسان** با فیکسچر شناخته‌شده‌ی `bfc01896` (کتاب دوم آزمایشیِ همان سناریوی تست Word).
- توضیح: یک بار ذخیره‌ی مجدد همان سند (ZIP timestamp متفاوت) → SHA-256 متفاوت، متن یکسان.
- **نتیجه: ORPHAN_CONFIRMED** — بازمانده‌ی تست؛ نه در هیچ جدول DB، نه در هیچ مانیفست.

### ۲.۳ جمع‌بندی و ریشه‌ی یتیمی
- **13 آیتم یتیم** (5 اوریجینال + 8 out-dir + 8 کپی؛ در کل 21 فایل/دایرکتوری) — همه باقی‌مانده‌ی اجرای مکرر سناریوی PCM-14B.3 (۱۴۸/۱۸۲۲/۱۸۲۹–۱۹:۰۳ تاریخ 2026-10-27).
- **ریشه‌ی ساختاری:** گام ۱۲ پاک‌سازی سناریو (`pcm14b3_word_scenario.sh`) فقط `files/<sha12>` مربوط به 3 SHAی خود را پاک می‌کند و ردیف‌های DB را حذف می‌کند، **اما هیچ‌وقت `out/` را پاک نمی‌کند** و اوریجینال‌های تکراری با SHA جدید (re-save) را نمی‌شناسد.
- هیچ جدول Knowledge production ردیفی ندارد؛ بکاپ‌های DB (16:59 و 17:17) **پیش از** سناریو هستند و اصلاً جدول‌های Knowledge را ندارند. پس هیچ‌یک از این فایل‌ها Referenced به داده‌ی production نیستند.
- هیچ فایل REFERENCED (به DB production) و هیچ UNKNOWN باقی‌نمانده‌ای وجود ندارد.

### ۲.۴ پیشنهاد پاک‌سازی (جداگانه — در این مأموریت اجرا **نشده**)
فقط با تأیید کاربر، در یک مرحله‌ی مجزا:
1. **اول:** اضافه‌کردن گام پاک‌سازی `out/` به سناریوی تست (اصلاح ریشه‌ای، PCM-14C.2).
2. **بعد:** حذف 21 آیتم یتیم (همه باقی‌مانده‌ی اثبات‌شده‌ی تست؛ فهرست دقیق SHA در بالا) — از داخل کانتر با دسترسی root، با ثبت SHA-256 قبل/بعد و بکاپ اسنپ‌شات `data/knowledge` به `/home/saber/backups/` پیش از حذف.
3. **قاعده‌ی ایمنی:** هیچ فایلی که `REFERENCED` (ردیف DB فعال) باشد حذف نمی‌شود؛ این فهرست فقط از آیتم‌های ORPHAN_CONFIRMED ساخته شده است.

---

## ۳. بخش B و D — وضعیت واقعی Elasticsearch و قرارداد سازگاری

### ۳.۠ وضعیت کلی: **BLOCKED / NOT_VERIFIED**
کشف‌گری فقط‌خوانده‌ی کامل روی s52:
- هیچ کانتر/سرویس Elasticsearch روی s52 وجود ندارد (نه در `docker ps`، نه پورت 9200/9300، نه هیچ env var مرتبط).
- هیچ اندکس، alias یا mapping واقعی برای داده‌ی PCT وجود ندارد — پس «قالب قبلی»‌ای برای مقایسه وجود ندارد (بخش ۳.۳).
- تنها ES موجود: API برداشت دوردست `https://thesaurus.eiis.iki.ac.ir/fa/api/elastic/search` که **منبع کراول** است و خارج از محدوده‌ی این مأموریت است (لمس نمی‌شود).
- endpoint فعلی [`/api/knowledge/compatibility`](backend/knowledge_api.py:1727) واقع‌بینانه `NOT VERIFIED` برمی‌گرداند (رفتار صحیح، حفظ می‌شود).
- **نقطه‌ی ناسازگاری مستندات کشف‌شده:** کد به مسیر `backend/tests/fixtures/knowledge/golden-manifest.json` ارجاع می‌دهد ولی این دایرکتوری/فایل در ریپازیتوری وجود ندارد (باید در PCM-14C.2 ایجاد یا ارجاع حذف شود).

### ۳.۱ قرارداد پیشنهادی (فقط طراحی — وضعیت کلی: NOT_VERIFIED تا زمانی که mapping واقعی دیده شود)

#### ساختار اندکس و policy نسخه/alias
- نام اندکس فیزیکی: `pct-knowledge-v{n}` (n=1،2,…؛ هر Build = اندکس نسخه‌ی جدید).
- alias زنده: `pct-knowledge-live` — تمام خوانش‌ها (Word Studio، کلاینت‌های شخص ثالث) فقط از alias.
- **Build:** ساخت `pct-knowledge-v{n+1}` از DB → اعتبارسنجی (شمارش doc، نمونه doc) → **اسواپ اتمیک alias** (atomic alias actions با `must_exist` روی قدیم).
- **Rollback:** برگرداندن alias به `v{n-1}` (یک خط API؛ بدون rebuild).
- اندکس‌های قدیمی: حذف نمی‌شوند؛ نگه‌داشته می‌شوند تا زمانی که دو نسخه‌ی بعدی ساخته شوند (سیاست نگه‌داری = 2 نسخه‌ی غیرفعال).

#### mapping پیشنهادی (سند: Document؛ بلوک‌ها: nested)
```json
{
  "settings": {
    "number_of_shards": 1, "number_of_replicas": 1,
    "analysis": {
      "analyzer": { "fa_text": {
        "type": "custom", "tokenizer": "standard",
        "filter": ["lowercase", "fa_normalizer"] } } }
  },
  "mappings": {
    "properties": {
      "work_id":       { "type": "keyword" },
      "edition_id":    { "type": "keyword" },
      "volume_id":     { "type": "keyword" },
      "document_id":   { "type": "keyword" },
      "collection_id": { "type": "integer" },
      "title":         { "type": "text", "analyzer": "fa_text",
                          "fields": { "kw": { "type": "keyword" } } },
      "author":        { "type": "text", "analyzer": "fa_text",
                          "fields": { "kw": { "type": "keyword" } } },
      "sha256":        { "type": "keyword" },
      "status":        { "type": "keyword" },
      "block_count":   { "type": "integer" },
      "char_count":    { "type": "integer" },
      "schema_version":{ "type": "keyword" },
      "index_version": { "type": "integer" },
      "indexed_at":    { "type": "date" },
      "page":          { "type": "integer" },
      "blocks": {
        "type": "nested",
        "properties": {
          "block_id":     { "type": "keyword" },
          "seq":          { "type": "integer" },
          "type":         { "type": "keyword" },
          "raw_text":     { "type": "text", "index": false },
          "normalized_text":{ "type": "text", "analyzer": "fa_text" },
          "page":         { "type": "integer" },
          "metadata":     { "type": "object", "dynamic": "strict" }
        }
      }
    }
  }
}
```
- **`_id` دترمینیستیک:** `doc:{document_id}:{edition_id}` — بازنشرِ مجددِ همان سند باید idempotent باشد (PUT با همان `_id`).
- `page` همیشه **integer یا غایب** — هرگز حدس (null/missing اگر نامشخص).
- `raw_text` در ES فقط برای side-by-side ذخیره می‌شود (non-indexed)؛ منبع حقیقت RAW در `blocks.jsonl` است.

### ۳.۲ رابطه‌ی Work/Edition/Volume ↔ سند ایندکس‌شده
- هر سند (Document) در ES دقیقاً **یک** `work_id` + `edition_id` دارد و `volume_id` اختیاری است.
- Work/Edition/Volume **در ES ایندکس نمی‌شوند** — رجیستری آن‌ها در SQLite است (منبع حقیقت واحد)؛ ES فقط اسناد و بلوک‌ها را نگه می‌دارد و با کلیدهای stable به رجیستری وصل می‌شوند (join در لایه‌ی API).
- `collection` (کتاب در Word Studio) ↔ ES: ستون `es_alias` روی `knowledge_collections` نام alias را نگه می‌دارد؛ پیش‌فرض `pct-knowledge-live` ولی قابل تغییر.

### ۳.۳ مقایسه‌ی فیلدبه‌فیلد با «قالب قبلی»
| فیلد | قالب قبلی (واقعی) | وضعیت |
|---|---|---|
| همه‌ی فیلدها | **قالب قبلی وجود ندارد** (هیچ اندکس واقعی یافت نشد) | `NO_PREVIOUS_TEMPLATE` |
| `backend/tests/fixtures/knowledge/golden-manifest.json` (ارجاع در کد) | فایل در ریپازیتوری نیست | `UNKNOWN` — باید در C.2 ایجاد یا ارجاع حذف شود |

**وضعیت کلی سازگاری ES: `NOT_VERIFIED`** — طبق قاعده‌ی مأموریت، هیچ mapping فرضی به‌عنوان واقعی ارائه **نشده** است؛ جدول بالا نشان می‌دهد مقایسه‌ی واقعی نیازمند دسترسی به یک ES واقعی است.

### ۳.۴ مسیرهای رفع BLOCKED (برای تصمیم کاربر — بخش ۱۰)
1. **مسیر A (پیشنهادی):** ES جداگانه/محلی برای PCT (مثلاً یک کانتر `elasticsearch` در compose در staging پیش از production) — نیاز به تصمیم owner + منابع.
2. **مسیر B:** استفاده از همین سرویس دوردست thesaurus (غیرممکن برای نوشتن — فقط منبع کراول است).
3. **مسیر C:** تعویض موتور با SQLite-FTS5/سایر (تصمیم معماری بزرگ؛ خارج از این مأموریت).

---

## ۴. بخش C — مدل کانونیکال `Work → Edition → Volume → Document → Block` در مقابل جداول فعلی

### ۴.۱ جداول فعلی (7 جدول Knowledge + ستون‌های موجود)
از [`ensure_knowledge_schema`](backend/knowledge_api.py:126) و [`_ensure_document_columns`](backend/knowledge_api.py:268):

| جدول | ستون‌های کلیدی موجود |
|---|---|
| `knowledge_collections` | collection_id, name, slug, **es_alias UNIQUE**, **schema_version** ('s-1'), indexing_status, current_index_build |
| `knowledge_collection_documents` | document_id UNIQUE, **sha256**, file_id, **work_id/edition_id/volume_id TEXT**, status, UNIQUE(collection_id, sha256) |
| `knowledge_index_builds` | build_id, collection_id, index_name, status, doc_count, started/finished |
| `knowledge_jobs` | job_id, kind, **retry_count**, **idempotency_key**, progress, stage |
| `knowledge_import_batches` | batch_id, collection_id, status, counts |
| `knowledge_metadata_fields` | field_id, key, **data_type**, **validation_rules**, **scope**, collection_id |
| `knowledge_metadata_values` | value_id, field_id, scope, collection_id, batch_id, document_id, **version**, **source** |

### ۴.۲ تطبیق با 9 قاعده‌ی طراحی

| # | قاعده | وضعیت فعلی | فاصله |
|---|---|---|---|
| 1 | IDهای stable مستقل از نام نمایشی | **موجود (با ریسک):** `short_id = prefix- + sha256(key)[:8]` در [`factory/models.py`](backend/factory/models.py:39) — ولی `work_key` از **metadata استخراج‌شده** title/author ساخته می‌شود ([`factory/service.py:90`](backend/factory/service.py:90))؛ اگر استخراج title در دو فایل یکسان نباشد، `work_id` متفاوت می‌شود | رجیستری صریح Work لازم (مورد ۴.۳) |
| 2 | رابطه‌ی مستند نام کتاب ↔ نام مجموعه | **موجود:** collection = کتاب؛ `es_alias` = نام در ES | فقط مستندسازی + policy rename لازم |
| 3 | rename نباید IDها را بشکند | **داریم:** IDها hash از key هستند نه از نام | در practice: key فعلی روی نام تکیه دارد → با رجیستری صریح، rename بی‌اثر می‌شود |
| 4 | edition کتاب ≠ نسخه‌ی فنی ایندکس | **داریم (جداسازی درست):** `edition_id` (hash key+sha256 فایل) در مقابل `schema_version`/`index_version`/`es_alias` | مستندسازی تفاوت لازم |
| 5 | متادیتای سفارشی با نوع/اعتبارسنجی/scope | **موجود:** FIELD_TYPES 7 تا (string,number,boolean,date,url,enum,json) + validation_rules + scope | **scope فقط `collection/batch/document`** — scope های `work/edition/volume` **نبود** |
| 6 | RAW هرگز با normalized جایگزین نمی‌شود | **داریم:** هر Block هر دو `raw` و `normalized` دارد ([`models.py:79`](backend/factory/models.py:79)) و در `blocks.jsonl` هر دو نوشته می‌شود | — |
| 7 | بلوک‌ها با ترتیب قطعی + ID ثابت | **نیمه:** `seq` (index) قطعی است، اما `block_id = b{index:05d}:{type}` — چون **type در ID است**، اگر parser در run بعدی type را متفاوت طبقه‌بندی کند ID عوض می‌شود | پیشنهاد v2: `b{index:05d}` (بدون type) + column type جدا |
| 8 | حدس page ممنوع (null اگر نامشخص) | **داریم:** برای docx همیشه `page=None` | — |
| 9 | dedup با SHA-256 + idempotency | **داریم:** UNIQUE(collection_id, sha256) + `idempotency_key` روی jobs | — |

### ۴.۳ موارد موجود / موارد مفقود

**موجود (keep):** ستون‌های work/edition/volume_id روی documents · es_alias · index_builds · jobs با retry · batches · metadata fields/values · dedup · idempotency · RAW+normalized.

**مفقود (نیازمند مهاجرت افزایشی — بخش ۵):**
1. **جدول‌های رجیستری** `knowledge_works` (work_id PK, title, author, created_at) — فعلاً work فقط یک hash مبهم در ستون TEXT اسناد است.
2. **جدول `knowledge_editions`** (edition_id PK, work_id FK, file_sha256, edition_label, created_at).
3. **جدول `knowledge_volumes`** (volume_id PK, edition_id FK, **volume_no INTEGER**, label).
4. **`volume_no`** به‌عنوان داده‌ی قابل‌پرس‌وجو (امروز فقط داخل hash گم است).
5. **scope های متادیتای `work`/`edition`/`volume`** (محدودیت فعلی: `collection|batch|document`).
6. **ستون `block_count`/`char_count`** روی documents (برای نمایش آمار بدون خواندن JSONL).
7. **نشانگر نسخه‌ی schema پایدارشده** (امروز `schema_version='s-1'` فقط روی collection است).
8. **اصلاح ساختار block_id (v2)** — بدون type در ID (سازگاری با قاعده‌ی 7).
9. **سقف regex جلد:** `_vol_no` فقط جلدهای 1–6 را می‌شناسد ([`factory/metadata.py:38`](backend/factory/metadata.py:38)) — باید عمومی شود.

---

## ۵. بخش D (ادامه) — برنامه‌ی مهاجرت (فقط افزایشی، مطابق قاعده‌ی ۲ AGENTS.md)

**اصل:** هیچ `DROP`/`RENAME`/تغییر نوع ستون. فقط `CREATE TABLE` جدید + `ALTER TABLE ADD COLUMN` + backfill + index. هر مرحله: بکاپ → اجرا → `integrity_check` → تست → commit جدا.

| مرحله | عملیات | ریسک |
|---|---|---|
| M1 | `CREATE TABLE knowledge_works` + index روی (title, author) | بسیار کم |
| M2 | `CREATE TABLE knowledge_editions` + FK indexes | بسیار کم |
| M3 | `CREATE TABLE knowledge_volumes` + index (edition_id, volume_no) | بسیار کم |
| M4 | `ALTER TABLE knowledge_collection_documents ADD COLUMN block_count INTEGER, ADD COLUMN char_count INTEGER` + backfill از `manifest.json`های موجود در `out/` (فقط برای ردیف‌هایی که out دارند) | کم |
| M5 | گسترش `FIELD_SCOPES` به `+ work, edition, volume` (تغییر کد + validation؛ داده‌ای حذف نمی‌شود) | کم |
| M6 | backfill رجیستری: برای هر document فعلی، از `work_id/edition_id` ستون‌های موجود، ردیف‌های work/edition بسازد (title/author از metadata استخراج‌شده در `document.json` اگر موجود، در غیر این صورت NULL — **حدس ممنوع**) | کم |
| M7 | block_id v2: فقط برای **پردازش‌های جدید** فعال (reprocess)؛ اسناد قدیمی IDهای v1 را حفظ می‌کنند (میدان `id_scheme` روی documents: 'v1'/'v2') | کم |
| M8 | رفع BLOCKED ES (بسته به تصمیم کاربر — بخش ۱۰): ایجاد `pct-knowledge-v1` + alias در **staging** → validation → سپس production | متوسط |

هر مرحله به‌تنهایی قابل revert است (جدول/ستون‌های جدید unused باقی می‌مانند).

---

## ۶. بخش E — قرارداد OpenAPI (طراحی؛ یک API برای Word Studio و شخص ثالث)

### ۶.۱ فهرست endpointهای هدف (namespace خواندنی پشت auth؛ نوشتاری هم پشت auth — مطابق قاعده‌ی ۶ AGENTS.md که فقط `/api/projects*` باز می‌ماند)

| Method | Path | توضیح |
|---|---|---|
| POST | `/api/knowledge/works` | ساخت Work (رجیستری صریح) |
| GET | `/api/knowledge/works` | فهرست (page/limit) |
| GET | `/api/knowledge/works/{work_id}` | جزئیات + editionها |
| POST | `/api/knowledge/works/{work_id}/editions` | ثبت Edition (با فایل یا sha موجود) |
| GET | `/api/knowledge/editions/{edition_id}` | جزئیات + volumeها |
| POST | `/api/knowledge/editions/{edition_id}/volumes` | ثبت Volume |
| POST | `/api/knowledge/collections/{id}/documents` | (موجود) ثبت سند — از این‌جا work/edition/volume پذیرفته می‌شود |
| GET | `/api/knowledge/documents/{doc_id}` | (موجود) جزئیات |
| POST | `/api/knowledge/metadata/values` | (موجود) ثبت متادیتا — scope جدید: work/edition/volume |
| GET | `/api/knowledge/collections/{id}/builds` | (موجود) فهرست buildها |
| POST | `/api/knowledge/collections/{id}/builds` | **جدید** — اجرای Build ES (async job) |
| GET | `/api/knowledge/builds/{build_id}` | **جدید** — وضعیت Build + نسخه‌ی فعال |
| POST | `/api/knowledge/builds/{build_id}/rollback` | **جدید** — برگرداندن alias |
| POST | `/api/knowledge/jobs/{job_id}/retry` | **جدید** — retry عملیات ناکام |

### ۶.۲ نمونه‌ی JSON

**نمونه ۱ — ساخت کتاب (Work + Edition + Volume):**
```json
POST /api/knowledge/works
{ "title": "تفسیر تسنیم", "author": "مجموعه‌ی همتا" }
→ 201
{ "work_id": "w-3f9a2c1d", "title": "تفسیر تسنیم", "author": "مجموعه‌ی همتا",
  "created_at": "2026-10-28T12:00:00Z" }

POST /api/knowledge/works/w-3f9a2c1d/editions
{ "file_sha256": "061ca55f…", "edition_label": "نسخه‌ی ۱۴۰۵" }
→ 201
{ "edition_id": "e-8b2e4f60", "work_id": "w-3f9a2c1d", "file_sha256": "061ca55f…" }

POST /api/knowledge/editions/e-8b2e4f60/volumes
{ "volume_no": 1, "label": "جلد اول" }
→ 201
{ "volume_id": "v-1c4d7a92", "edition_id": "e-8b2e4f60", "volume_no": 1 }
```

**نمونه ۲ — ثبت متادیتا (scope جدید):**
```json
POST /api/knowledge/metadata/values
{ "field_id": 12, "scope": "edition", "edition_id": "e-8b2e4f60",
  "value": "1405", "source": "user" }
→ 201
{ "value_id": 78, "field_id": 12, "scope": "edition", "edition_id": "e-8b2e4f60",
  "version": 1, "source": "user" }
```

**نمونه ۳ — وضعیت Build:**
```json
GET /api/knowledge/builds/14
→ 200
{ "build_id": 14, "collection_id": 3, "status": "done",
  "index_name": "pct-knowledge-v2", "alias": "pct-knowledge-live",
  "doc_count": 128, "error": null,
  "started_at": "2026-10-28T12:04:11Z", "finished_at": "2026-10-28T12:06:40Z",
  "active_version": 2, "previous_version": 1,
  "rollback_available": true }
```

### ۶.۳ قواعد قرارداد
- **تک API:** Word Studio (frontend فعلی) و کلاینت‌های شخص ثالث هر دو همین endpointها را با همان auth (session) می‌خوانند.
- صفحه‌بندی اجباری: `?page=1&limit=50` (حداکثر 200) — کل‌جدول‌بارگذاری ممنوع (قاعده‌ی ۷ AGENTS.md).
- همه‌ی پاسخ‌های خطا: `{ "error": "<code>", "detail": "…" }` + status استاندارد (400/401/404/409/503).
- `409` برای تکرار: همان work (title+author) / همان sha256 در collection / build در حال اجرا.
- همه‌ی عملیات نوشتاری async-job-based با `idempotency_key` (replay امن).

---

## ۷. بخش F — ماتریس تست و معیارهای پذیرش

### ۷.۱ ماتریس

| لایه | کلاس تست | موارد | ابزار/محیط |
|---|---|---|---|
| **Unit** | model | `short_id` determinism · rename بدون تغییر ID · volume_no 0/1/2/7/99 · block_id v1/v2 · page=null · raw/normalized هر دو | pytest/unittest، بدون DB |
| **Unit** | validation | هر FIELD_TYPE × scope جدید (work/edition/volume) · validation_rules (min/max/enum/pattern) | بدون DB |
| **Integration** | SQLite | مهاجرت‌های M1–M7 روی DB تخته‌نویسی (با `pct_test_support.reset_db`) · idempotency مهاجرت (اجرای دوباره) · backfill | DB موقت |
| **Integration** | ES | mapping PUT · bulk index · **idempotent PUT با `_id` ثابت** · alias swap اتمیک · rollback · count بعد از build | **فقط روی اندکس تست جداسازده‌شده** `pct-knowledge-test-*` (هرگز `*-live`) |
| **Feature** | API | 14 endpoint جدول ۶.۱ × (200/400/401/404/409) · صفحه‌بندی · auth | Flask test client + DB موقت |
| **E2E** | جریان کامل | ثبت کتاب → فایل → process → approve → Build → query از alias → rollback → retry | staging |
| **Regression** | Word Factory | 103 تست فعلی سبز + سناریوی 40/40 PCM-14B.3 | Local + s52 |
| **Regression** | کراول | پروژه 2 `running` باقی بماند، `saved_count` رشد کند، API `/api/projects*` 200 | s52 (فقط‌خوانده) |
| **Idempotency/Retry** | job | replay همان request با `idempotency_key` → 1 effect · retry ناکام → resume · build دوباره روی همان collection → 409 تا تموم شدن قبلی | Flask client |
| **Versioning/Rollback** | ES | v1→v2 build → اسواپ → rollback → alias بازگشت به v1 بدون rebuild | اندکس تست |

### ۷.۲ معیارهای پذیرش (Acceptance Criteria)
1. **A1:** مهاجرت‌ها روی DB خالی و DB با داده (fixture) هر دو بدون خطا و idempotent.
2. **A2:** rename یک Work/Collation → هیچ `work_id`/`document_id`/`_id` ES تغییر نکند.
3. **A3:** یک Build کامل روی staging: `doc_count` ES == شمارنده‌ی واقعی DB (قاعده‌ی ۹ AGENTS.md — عدد ساختگی ممنوع).
4. **A4:** rollback alias در < 5 ثانیه و بدون rebuild.
5. **A5:** replay هر POST نوشتاری با همان idempotency_key → دقیقاً یک اثر.
6. **A6:** کراول s52 در تمام مدت تست‌ها `running` بماند و `saved_count` رشد کند.
7. **A7:** هیچ تستی مستقیماً روی `thesaurus.db` production یا alias `*-live` ننویسد.
8. **A8:** `integrity_check` + شمارش 7 جدول Knowledge بعد از هر مرحله == قبل (مگر مهاجرت backfill با عدد ثبت‌شده).

---

## ۸. بخش G.۸ — ریسک‌ها و گزینه‌های تصمیم

| # | ریسک/معضل | شدت | گزینه‌ها |
|---|---|---|---|
| R1 | ES در s52 وجود ندارد (BLOCKED) — بخش D نمی‌تواند VERIFIED شود | بالا | (الف) نصب ES در staging (تصمیم owner + منابع) (ب) تعویض به FTS5/سایر (ج) توقف خط ES و فقط sqlite-first |
| R2 | `work_key` فعلی روی metadata استخراج‌شده تکیه دارد → احتمال work_id متفاوت برای یک کتاب | بالا | رجیستری صریح Work (M1) + auto-derive فقط fallback |
| R3 | `block_id` فعلی type در ID دارد → instability بین runها | متوسط | v2 بدون type (M7) + میدان `id_scheme` |
| R4 | سقف جلد (regex 1–6) | کم | عمومی‌سازی `_vol_no` |
| R5 | 21 فایل یتیم (~125 MB) | کم | پاک‌سازی مرحله‌ی جدا با بکاپ (تصویب کاربر) |
| R6 | golden-fixture در کد refer شده ولی موجود نیست | کم | ایجاد فایل یا حذف ارجاع |
| R7 | افزودن scope های جدید متادیتا می‌تواند frontend فعلی را بی‌توجه بگذارد | کم | additive — frontend جدید scope ها را نشان می‌دهد، قدیم unchanged |

---

## ۹. ترتیب اجرای PCM-14C.2 و گام‌های بعد (پیشنهاد)

1. **C.2.1** — تصویب تصمیم‌های بخش ۱۰ (به‌ویژه R1: سرنوشت ES).
2. **C.2.2** — اصلاح سناریوی تست: گام پاک‌سازی `out/` (اصلاح ریشه‌ای یتیمی) + تصویب/اجرای پاک‌سازی 21 فایل یتیم (با بکاپ اسنپ‌شات).
3. **C.2.3** — مهاجرت‌های M1–M7 (هرکدام: بکاپ → migrate → integrity → تست → commit → deploy → smoke).
4. **C.2.4** — endpointهای رجیستری Work/Edition/Volume + scope های جدید متادیتا + JSON نمونه‌ها به OpenAPI.
5. **C.2.5** — (اگر R1(الف) تصویب شد) ES در staging → mapping/alias/Build/rollback + A3–A5.
6. **C.2.6** — e2e کامل + ریگرسیون Word Factory (40/40) + ریگرسیون کراول (A6) + گزارش پذیرش.
7. **C.3** — (اختیاری، بعد از C.2) reprocess اسناد قدیمی با block_id v2 + عمومی‌سازی regex جلد.

---

## ۱۰. فهرست دقیق موارد نیازمند تصمیم کاربر

| # | تصمیم | گزینه‌ها | پیشنهاد |
|---|---|---|---|
| D1 | **سرنوشت Elasticsearch** (R1 — BLOCKED) | (الف) نصب/استaging ES جدا برای PCT (ب) تعویض به SQLite FTS5 (ج) توقف خط ES | (الف) — ES در PRD هست و دوردست thesaurus فقط منبع کراول است |
| D2 | **owner/منابع ES** اگر (الف) | چه سروری، چه مقدار RAM/disk، image کدوم نسخه | s52 اگر منابع کفایت کند؛ وگرنه سرور staging جدا |
| D3 | **تأیید پاک‌سازی 21 فایل یتیم** (~125 MB) | بله/خیر (فهرست دقیق SHA در بخش ۲) | بله — همه ORPHAN_CONFIRMED، با بکاپ اسنپ‌شات قبل |
| D4 | **اصلاح سناریوی تست** (افزودن پاک‌سازی `out/`) | بله/خیر | بله — اصلاح ریشه‌ای |
| D5 | **block_id v2** (حذف type از ID) | بله (فقط runهای جدید) / خیر (v1 را نگه داریم) | بله — سازگاری با قاعده‌ی «ID ثابت» |
| D6 | **رجیستری صریح Work/Edition/Volume** (M1–M3, M6) | بله/خیر | بله — لازمه‌ی قاعده‌ی 1 و 3 |
| D7 | **گسترش scope های متادیتا** (work/edition/volume — M5) | بله/خیر | بله |
| D8 | **golden-manifest fixture** (R6) | ایجاد فایل در `backend/tests/fixtures/knowledge/` / حذف ارجاع از کد | ایجاد (برای golden-test سازگاری) |
| D9 | **تحویل این گزارش و اسکریپت‌ها به git** (در این مأموریت commit نشد) | commit+push کن / هنوز نگه دار | commit+push در مرحله‌ی بعد با تأیید شما |

---

## پیوست — وضعیت نهایی سه محیط (لحظه‌ی نگارش، بدون commit)

- **Local:** `HEAD=origin/main=7f21fb0`، clean به‌جز 5 اسکریپت untracked در `deploy/` + همین گزارش (untracked).
- **GitHub:** `main=7f21fb0`.
- **s52:** کد `2ad6c53` (اثبات‌شده)؛ کانتر Up؛ `integrity_check=ok`؛ 7 جدول Knowledge = 0 ردیف؛ کراول پروژه 2 `running` (27,485 ذخیره‌شده، `updated_at` لحظه‌ای)؛ هیچ تغییری در این مأموریت اعمال **نشده** است.

*پایان گزارش PCM-14C.1 — طراحی فقط، بدون پیاده‌سازی، بدون تغییر Production، بدون commit/push/deploy.*

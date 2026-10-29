# گزارش PCM-14D — Work Registry: سلسله‌مراتب اثر←نسخه←جلد

تاریخ: ۱۴۰۵/۰۸/۰۷ (2026-10-29) · شاخه: `main` · commit پایه: `855042f` (PCM-14C.4)

---

## A. خلاصه اجرایی

مأموریت «Work Registry: مدل اثر←نسخه←جلد←سند + scopeهای متادیتا» به‌طور
کامل انجام شد. مطابق دستور مأموریت، **ابتدا DB و مدل‌های موجود ممیزی شدند** —
هیچ فرضی از «ناقص بودن» مدل فعلی انجام نشد و نتیجه ممیزی (بخش B) نشان داد
که تنها چیزی که واقعاً وجود نداشت، **سلسله‌مراتب کتابی** بود: ستون‌های
denormalized روی `knowledge_collection_documents` (title/author/publisher/
publish_year/volume_no) بودند، ولی هیچ ساختاری برای **چند نسخه از یک اثر**،
**چند جلد از یک نسخه** و **متادیتا در سطح اثر/نسخه/جلد** نبود.

نتیجه‌ها:

1. **3 جدول جدید** `knowledge_works` / `knowledge_editions` /
   `knowledge_volumes` + **6 ستون additive** روی جدول اسناد + backfill از
   ستون‌های denormalized قدیمی (INSERT OR IGNORE — داده قدیمی هرگز بازنویسی
   نمی‌شود).
2. **شناسه‌های deterministic** دقیقاً مطابق `backend/factory/service.py:85-96`
   (`work_id = w-<sha8>`, `edition_id = e-<sha8>`, `volume_id = v-<sha8>`) —
   بنابراین registry API و خروجی Word Factory روی **همان** شناسه‌ها صحبت
   می‌کنند.
3. **scopeهای جدید متادیتا** `work`/`edition`/`volume` روی فیلدها و
   مقادیر + endpoint `/api/knowledge/metadata/resolve` با اولویت لایه‌ای
   `document > volume > edition > work > collection > field_default` و
   **anchor-gating** (id خالی → query بدون فیلتر صادر نمی‌شود).
4. **10 تست جدید** (RD-01..RD-07) + رگرسیون کامل **139/139 سبز**.
5. سند طراحی: `docs/PCM-14D-WORK-REGISTRY.md` (ERD، DDL، مهاجرت/rollback،
   قرارداد JSON، جدول سازگاری) + OpenAPI:
   `docs/openapi/pcm14d-knowledge-work-registry.openapi.yaml`.
6. **بدون deploy**: s52 فقط با چک خواندنی قابل‌استفاده است
   (`deploy/pcm14d_s52_readonly_check.sh`) — مطابق قاعده «بدون بکاپ و دستور
   صریح، deploy نمی‌شود».
7. قرارداد Dump `d-1` و Word Factory **کاملاً دست‌نخورده** (compat tests سبز).

## B. وضعیت قبل از تغییر و ممیزی

- git: clean روی `855042f` (= `origin/main`، PCM-14C.4)؛ 129 تست سبز.
- ممیزی اسکیمای موجود (PRAGMA table_info روی DB تستی):
  - `knowledge_collection_documents` ستون‌های `title/author/publisher/
    publish_year/volume_no` داشت (denormalized، تک‌مستوی) — مناسب برای
    نمایش، ولی **مدل داده کتابی نبود**.
  - `knowledge_metadata_fields.values` فقط scopeهای `collection/batch/
    document` داشت — متادیتای «سطح اثر/نسخه/جلد» جایی برای ثبت نداشت.
  - جدول `knowledge_works` و همتایان آن **وجود نداشتند** (تأیید با
    `SELECT name FROM sqlite_master`).
  - `backend/factory/service.py` (سطح 85-96) شناسه‌های `w-`/`e-`/`v-` را
    برای خروجی JSONL محاسبه می‌کند، ولی این شناسه‌ها در DB **هیچ مرجعی
    نداشتند** — یعنی یک اثر با دو نسخه (دو فایل DOCX) در DB دو «کتاب
    جدا» دیده می‌شدند، نه دو نسخه از یک اثر.
- نتیجه ممیزی: مهاجرت **افزایشی** (3 جدول جدید + 6 ستون ADD) کافی است؛
  هیچ DROP/RENAME/تغییر نوع ستونی لازم نیست.

## C. طراحی

**ERD (خلاصه — کامل در `docs/PCM-14D-WORK-REGISTRY.md`):**

```
knowledge_collections (1) ──< knowledge_collection_documents (N)
        │                              │  +6 ستون additive: work_id, edition_id,
        │                              │    volume_id (+3 ستون قدیمی بدون تغییر)
        │                              ▼
        │                     knowledge_works (1) ──< knowledge_editions (1) ──< knowledge_volumes (N)
        │                              │
        └──── knowledge_metadata_fields / _values
              (scope ∈ collection|batch|document|work|edition|volume؛
               سطر مقدار همیشه زنجیره کامل parent را حمل می‌کند)
```

- **شناسه‌ها (deterministic، قابل اثبات):** `work_key =
  title.lower()|author.lower()` (در صورت خالی بودن هر دو، sha256 فایل)؛
  `work_id = short_id("w", work_key)`؛ `edition_id = short_id("e",
  f"{work_key}|{sha256_file}")`؛ `volume_id = short_id("v",
  f"{edition_id}|{volume_no or 'main'}")` — تابع `short_id` دقیقاً همان
  `factory/models.py:231` است.
- **مهاجرت (افزایشی و idempotent):** `ensure_knowledge_schema` →
  `executescript(IF NOT EXISTS)` → `_ensure_registry_columns` (بررسی
  PRAGMA column + `ALTER TABLE ADD COLUMN` guarded ×6) →
  `_backfill_registry` (INSERT OR IGNORE از ستون‌های denormalized +
  biblio best-effort از `data/knowledge/out/<file_id>/document.json` فقط
  در صورت تنظیم `out_dir`).
- **rollback (فقط حذف داده/ساختار جدید، بدون دست‌زدن به داده قدیمی):**
  drop 3 جدول + `ALTER TABLE DROP COLUMN` ×6 (یا در SQLite قدیمی، بازسازی
  جدول با ستون‌های 6 تا جدید کمتر).
- **resolve لایه‌ای:** اولویت `document > volume > edition > work >
  collection > field_default`؛ هر scope با anchor خود gate شده (id خالی →
  `[]`، **نه** query بدون فیلتر — مانع نشت مقادیر collectionهای دیگر)؛
  پاسخ شامل `resolved`، `sources`، `raw` (تمام سطرهای هر scope) و
  `context` است.
- **همگامی زنده:** بعد از هر processing، `_upsert_registry_rows` از
  کتاب‌شناسی extract-only ثبت‌شده سطرهای registry را upsert می‌کند
  (INSERT OR IGNORE — ویرایش کاربر هرگز بازنویسی نمی‌شود) + به‌روزرسانی
  `document_count`.

## D. تغییرات کد و فایل

**جدید:**

| فایل | توضیح |
|-------|-------|
| `backend/test_work_registry.py` (596 خط) | 10 تست RD-01..RD-07 (ایزوله؛ `pct_test_support`) |
| `docs/PCM-14D-WORK-REGISTRY.md` (198 خط) | سند طراحی: ERD، DDL، id-derivation، مهاجرت/rollback، قرارداد JSON، جدول سازگاری، ماتریس RD |
| `docs/openapi/pcm14d-knowledge-work-registry.openapi.yaml` (736 خط) | OpenAPI 3.0.3: 11 path + schemas + examples + خطاها (cookieAuth `pct_session`) |
| `deploy/pcm14d_s52_readonly_check.sh` (67 خط) | چک خواندنی s52 (بدون deploy/نوشتن) — استفاده در مرحله deploy آینده |

**تغییرکرده (کد):**

| فایل | تغییر |
|-------|-------|
| `backend/knowledge_api.py` (+703 خط) | 3 جدول registry در DDL + `_ensure_registry_columns` + `_backfill_registry` + `_read_factory_biblio` + `_upsert_registry_rows` + 6 endpoint registry (works/editions/volumes: list/create/detail/patch) + scopeهای `work/edition/volume` در `create_field`/`set_value`/`list_values` + `/api/knowledge/metadata/resolve` + ستون‌های registry در response اسناد + 8-ستونی UNIQUE روی `knowledge_metadata_values` (افزایشی) |

**تغییرکرده (مستندات):** `readme.md` (ردیف قابلیت 8، 7 test files/139 تست،
درخت ساختار، endpointهای registry، جدول DB، تست‌ها، نقشه‌ی راه)،
`AGENTS.md` (بخش تست 139، ساختار فنی، نقشه‌ی راه).

**وابستگی جدید: صفر.** (فقط `hashlib` استاندارد)

## E. نتایج تست

| مجموعه | تعداد | نتیجه |
|---------|:-----:|:------:|
| هسته (api/projects/dashboard) | 39 | ✅ |
| knowledge_api (KB-01..KB-14) | 40 | ✅ |
| word_factory (WF-01..WF-13) | 24 | ✅ |
| dump (D01..D15) | 26 | ✅ |
| **work_registry (RD-01..RD-07)** | **10** | ✅ |
| **کل** | **139** | ✅ سبز (47.8s) |

پوشش RD:

- **RD-01** — idempotency اسکیمای knowledge (دو بار اجرا = همان جدول‌ها).
- **RD-02** — مهاجرت DB legacy: 6 ستون ADD شده، backfill از
  denormalized (هر سند قدیمی با `edition_id` متفاوت → سطر edition مجزا)،
  INSERT OR IGNORE (دو بار اجرا = بدون سطر تکراری).
- **RD-03** — processing واقعی کتاب نمونه → سطرهای work/edition ساخته
  می‌شوند با **همان شناسه‌هایی که Word Factory محاسبه می‌کند**
  (`work_id` از `work_key(title, author)` مستقیماً محاسبه و assert شد؛
  نویسنده = `python-docx` — مطابق extract-only: core properties اولویت
  دارد)؛ reprocess بدون سطر تکراری (idempotent).
- **RD-04** — سلسله‌مراتب: detail هر لایه + 404 برای idهای ساختگی +
  search/فیلتر/صفحه‌بندی روی فهرست works.
- **RD-05** — ساخت دستی work (idempotent: `created` فقط اولین بار) +
  اعتبارسنجی scopeهای entity در فیلدها (404/400).
- **RD-06** — زنجیره resolve: اولویت document>volume>edition>work>
  collection؛ حذف مقدار document → edition برنده می‌شود؛ resolve فقط
  در سطح work؛ raw = تمام سطرهای هر scope؛ layer `field_default`؛
  404 سند ناشناخته / 400 بدون context.
- **RD-07** — فیلترهای scope-strict `list_values` (value یک scope هرگز
  از فیلتر scope دیگر نمی‌نشیند).

اجرا:

```bash
cd backend
python -m unittest test_work_registry -v   # 10/10 (5.86s)
python -m unittest test_api test_projects test_dashboard \
  test_knowledge_api test_word_factory test_dump test_work_registry -v
  # 139/139 (47.8s)
```

تست‌ها ایزوله‌اند (`pct_test_support.reset_db()`)؛ ترتیب/ترکیب ماژول‌ها
مهم نیست. در مسیر توسعه، سه کاستی در خود تست/کد پیدا و **اصلاح** شد
(نه از بین بردن assertion):

1. DDL تازة `knowledge_metadata_values` ستون‌های entity را نداشت →
   UNIQUE 5-ستونی قدیمی روی DBهای تازه باقی می‌ماند (اصلاح: 8-ستونی).
2. `resolve` روی anchor خالی query بدون فیلتر می‌زد (نشت مقادیر
   collectionهای دیگر) → anchor-gating اعمال شد.
3. `raw` فقط سطرهای برنده را جمع می‌کرد → حالا تمام سطرهای هر scope.

## F. سازگاری (compat) — جدول خلاصه

| مورد | وضعیت |
|------|--------|
| ستون‌های denormalized قدیمی (`title/author/...`) | بدون تغییر، ادامه دارند |
| endpointهای قدیمی knowledge (collection/document/metadata) | بدون تغییر (تست‌های KB سبز) |
| scopeهای قدیمی متادیتا (collection/batch/document) | بدون تغییر |
| Dump `d-1` + Word Factory CLI | **کاملاً دست‌نخورده** (تست‌های D/WF سبز) |
| `knowledge_metadata_values` UNIQUE 5→8 ستون | افزایشی (ستون‌های جدید DEFAULT '' ) |
| DBهای قدیمی (بدون ستون‌های registry) | auto-migration additive هنگام startup |
| ES | `compatibility` = `NOT VERIFIED` (بدون تغییر، صادقانه) |

## G. Git: commit و push

- **commit کد:** `1535f455d7e5518eea151f9d1dfeee4663d63ed7`
  (8 فایل، 2567+ / 25−) — بعد از `855042f`، push بدون force.
- **GitHub:** `https://github.com/saber13812002/persian-corpus-toolkit` — SHA
  همان `1535f45` برای commit کد (تأیید با `git ls-remote`).
- این گزارش (با ثبت SHA نهایی) در **commit دوم بلافاصله بعدی** ثبت می‌شود
  (`git log --oneline -2` برای مشاهده هر دو) — همان رویه‌ی PCM-14C.3.

## H. وضعیت Local / GitHub / s52

| محیط | وضعیت |
|------|-------|
| Local | `main` = `1535f45`؛ working tree clean |
| GitHub | همگام با Local (`origin/main` = `1535f45`؛ تأیید با `git ls-remote`) |
| s52 | **pre-PCM-14D** — دست‌نخورده (چک خواندنی: `deploy/pcm14d_s52_readonly_check.sh`) |

## I. تأیید عدم اختلال در production

- هیچ deploy، restart یا نوشتن روی s52 انجام **نشده** است.
- اسکریپت چک خواندنی (`deploy/pcm14d_s52_readonly_check.sh`) آماده است:
  container status، probe endpointهای قدیمی (401/200/404 مطابق انتظار
  pre-14D)، نبود marker `knowledge_works` در کد s52، نبود جدول
  `knowledge_works` در DB، `PRAGMA integrity_check` + شمارنده‌ها، perms `.env`.
- کراول زنده (`/api/projects*`) دست‌نخورده است — هیچ endpoint نوشتاری
  اکستنشن تغییر نکرده است.

## J. محدودیت‌ها و ریسک‌ها

1. **هنوز deploy نشده** — مطابق قاعده مأموریت (بدون دستور صریح + بکاپ،
   deploy نمی‌شود). deploy آینده: بکاپ `thesaurus.db` + integrity_check →
   کپی کد → `docker compose build backend && up -d backend` → smoke test
   (چک خواندنی بالا + تست 139 روی کپی /tmp مطابق `pcm12_3_s52_test.sh`).
2. `publish_year`/`edition_label` در backfill فقط از ستون‌های قدیمی
   خوانده می‌شوند (best-effort)؛ در صورت غیاب، سطر edition با
   publisher خالی ساخته می‌شود (نمایش‌پذیر، قابل ویرایش با PATCH).
3. شناسه‌های registry از همان فرمول factory محاسبه می‌شوند؛ بنابراین اگر
   کاربر دستی work بسازد (`POST /api/knowledge/works`) و بعداً فایلی
   با همان title/author process شود، هر دو به همان `work_id` همگرا
   می‌شوند (معماری deterministic — مستند در سند).
4. ES بدون mapping واقعی — `compatibility` صادقانه `NOT VERIFIED` می‌ماند.

## K. روش تست دستی (اپراتور)

```bash
cd backend
# 1) رگرسیون کامل
python -m unittest test_api test_projects test_dashboard \
  test_knowledge_api test_word_factory test_dump test_work_registry -v
# 2) فقط Work Registry
python -m unittest test_work_registry -v

# 3) آزمایش دستی روی server محلی (بعد از docker compose up -d):
#    - POST /api/auth/login {"password": "..."}  → cookie pct_session
#    - GET  /api/knowledge/works                 → فهرست اثرها (search + صفحه‌بندی)
#    - POST /api/knowledge/works {"title":"...","author":"..."} → ساخت دستی (idempotent)
#    - POST /api/knowledge/works/w-XXXXXXXX/editions {"publisher":"..."}
#    - POST /api/knowledge/metadata/fields {"key":"ژانر","scope":"work"}
#    - POST /api/knowledge/metadata/values {"field_key":"ژانر","work_id":"w-...","value":"..."}
#    - GET  /api/knowledge/metadata/resolve?document_id=doc-...  → زنجیره اولویت
```

## L. فاز بعد

- **PCM-15** — صف پایدار پردازش: statusها (pending/running/succeeded/
  needs_review/failed)، retry از آخرین stage امن، pause/resume، E2E
  (folder سالم + خراب + تکراری + kill worker + restart) و سازگاری با
  Dump `d-1`.

---

*این گزارش بخشی از مأموریت «ادامه PCM-14C تا تحویل پیکره» است؛ مستندات
فنی کامل در `docs/PCM-14D-WORK-REGISTRY.md` و قرارداد OpenAPI در
`docs/openapi/pcm14d-knowledge-work-registry.openapi.yaml`.*

# PCM-17 — تکمیل UI استودیو: مدیریت صف + رجیستری اثر‌ها

**وضعیت:** پیاده‌سازی‌شده و تست‌شده (182/182) — کد:
`backend/knowledge_api.py` (endpoint جدید + شناسه‌های رجیستری در فهرست
اسناد)، `dashboard/studio.html` (کارت صف/بچ‌ها + کارت رجیستری +
به‌روزرسانی نقشه‌ی راه)؛ تست‌ها: `backend/test_studio_api.py`
(S-01..S-04، 7 تست)

**اصل:** evidence-based — همه‌ی اعداد UI از endpointهای REST واقعی
می‌آیند (سردبیر واحد: جدول‌های `knowledge_file_queue` /
`knowledge_queue_control` / `knowledge_import_batches`)؛ هیچ عدد تخمینی
یا ساختگی در UI نیست و هیچ endpoint ساختگی هم اضافه نشده.

---

## ۱. خلاصه

PCM-17 دو بخش استودیو را که در PCM-14D و PCM-15 به‌صورت API ساخته شده
بود ولی در UI نبودند، می‌سازد:

1. **کارت صف/بچ‌ها** (وسط صفحه‌ی کالکشن): نوار شمارنده‌های زنده‌ی
   صف (کل/در انتظار/در حال اجرا/موفق/نیاز به بررسی/ناموفق) + جدول
   بچ‌ها با وضعیت/توقف‌شده/عملیات (پردازش/توقف/ادامه).
2. **کارت رجیستری اثر‌ها** (ستون چپ): فهرست/جستجو/صفحه‌بندی
   `works`، ثبت اثر جدید، جزئیات اثر (ویرایش‌ها)، جزئیات ویرایش
   (جلدها + اسناد) و افزودن ویرایش/جلد.

به‌علاوه:

- **endpoint خواندنی جدید** `GET /api/knowledge/import/batches`
  (افزایشی؛ بدون تغییر هیچ endpoint موجود).
- **ستون «رجیستری» در جدول اسناد** (`work_id / edition_id /
  volume_id` — از ردیف سند خوانده می‌شود، نه حدس).
- **به‌روزرسانی نقشه‌ی راه استودیو** (PCM-14A..17 همه «انجام شد»).

## ۲. endpoint جدید (افزایشی)

```
GET /api/knowledge/import/batches?collection_id=&search=&page=&per_page=
```

| پارامتر | قواعد |
|---------|-------|
| `collection_id` | **الزامی**؛ شناسه‌ی متنی کالکشن (`c-...`؛ نه id عددی ردیف). غایب → 400 (`field=collection_id`)؛ ناشناخته → 404 |
| `search` | LIKE روی `batch_id` / `folder_name` |
| `page` | ≥1، پیش‌فرض 1 |
| `per_page` | 1..100 (سقف 100)، پیش‌فرض 50 |

پاسخ 200:

```json
{
  "batches": [ { ...ردیف knowledge_import_batches..., "paused": 0|1 } ],
  "total": 12, "page": 1, "per_page": 50, "total_pages": 1,
  "queue": {
    "counters": { "total": …, "pending": …, "running": …,
                  "succeeded": …, "needs_review": …, "failed": …,
                  "failed_with_safe_stage": …, "attempts_total": … },
    "failed_by_stage": [ { "stage": "parse", "files": 2 } ]
  }
}
```

- ردیف‌ها: `ORDER BY created_at DESC, batch_id` + `LIMIT/OFFSET`
  (قاعدهٔ AGENTS §2-7 — کل‌جدول‌بارگذاری در API ممنوع).
- `paused` از `knowledge_queue_control` (`scope = 'batch:<batch_id>'`)
  با یک `EXISTS` در همان SELECT — نه از job.
- `queue.counters` همان `queue_counters()` است که `queue/summary`
  می‌دهد (سردبیر واحد؛ آمار کش‌شده/ساختگی نیست).
- auth: مثل همه‌ی `/api/knowledge/*` — `require_auth` (401 بدون session).
- OpenAPI: `docs/openapi/pcm15-file-queue.openapi.yaml` (path جدید +
  schema `ImportBatch`).

## ۳. تغییرات `studio.html`

### ۳.۱ کارت صف/بچ‌ها (`#queueCard`)

- **نوار شمارنده‌ها** (`#qStrip`): 6 چیپ از `queue.counters`
  (هر چیپ فقط عدد واقعی endpoint؛ اگر کالکشن صف نداشته باشد همه ۰).
- **جدول بچ‌ها** (`#qBody`): بچ / پوشه / فایل / پردازش‌شده / ناموفق /
  وضعیت (planned/processing/done) / عملیات.
  - بچ `paused=1` → بج هشدار «توقف‌شده».
  - عملیات: «پردازش» (مخفی برای done)، «توقف» (وقتی active)،
    «ادامه» (وقتی paused) → `POST .../batches/<id>/process|pause|resume`.
- **polling**: فقط وقتی `counters.running > 0`، هر ۳ ثانیه؛ در غیر این
  صورت متوقف (بسته با `stopQueuePolling` هنگام تعویض/بستن کالکشن و
  خروج).
- toast بعد از هر عملیات با عدد واقعی پاسخ (مثلا `files_queued`).

### ۳.۲ کارت رجیستری (`#stWorksBody` در ستون چپ)

- «اثر جدید» → مودال (`#workModal`) → `POST /api/knowledge/works`
  (title الزامی).
- فهرست works (جستجو + صفحه‌بندی 8/صفحه) با `edition_count` /
  `document_count` (subquery واقعی endpoint).
- کلیک روی اثر → جزئیات: فیلدهای اثر + فهرست ویرایش‌ها (ناشر/سال +
  `volume_count`) + فرم افزودن ویرایش.
- کلیک روی ویرایش → جزئیات: `edition_label` + جلد‌ها (label/volume_id +
  `document_count`) + اسناد وابسته (با بج وضعیت سند) + فرم افزودن جلد
  (`volume_no` عدد صحیح یا null + label).
- همه‌ی idها با class `c-slug` (LTR) — قابل کپی.

### ۳.۳ جدول اسناد (`renderDocs`)

ستون «رجیستری» بعد از نام: `work_id / edition_id / volume_id`
(هرکدام که truthy باشد؛ از `knowledge_list_documents` که حالا این
سه ستون را SELECT می‌کند — سندِ پردازش‌نشده خالی می‌ماند).

### ۳.۴ نقشه‌ی راه (`#stRoadmap`)

شش ردیف همه‌ی `step done`: PCM-14A/B، PCM-14C.3 (Dump d-1 CLI)،
PCM-14D (رجیستری + resolve)، PCM-15 (صف ماندگار)، PCM-16 (پیکره‌ساز
CLI)، PCM-17 (این فاز). عبارت «این قابلیت در PCM-14D فعال می‌شود» از
کارت buildها حذف شد (ES هنوز `NOT VERIFIED` — همان‌طور صادقانه در
کارت سازگاری می‌ماند).

## ۴. سازگاری

| مورد | وضعیت |
|------|--------|
| endpointهای موجود | بدون تغییر (افزایشی فقط) |
| API نوشتاری اکستنشن (`/api/projects*`) | دست‌نخورده |
| قرارداد Dump d-1 / WF / pیکره‌ساز c-1 | دست‌نخورده |
| auth | endpoint جدید همان `require_auth` namespace |
| `dashboard/index.html` (داشبورد اصلی) | دست‌نخورده |

## ۵. ماتریس تست (`backend/test_studio_api.py` — 7 تست)

| # | پوشش |
|---|-------|
| S-01a | بدون auth → 401 (auth پیش از هر اعتبارسنجی پارامتر/کالکشن) |
| S-01b | `collection_id` غایب → 400 با `field=collection_id` |
| S-01c | کالکشن ناشناخته → 404 |
| S-01d | شکل ردیف‌ها + pagination (per_page پیش‌فرض 50 / سقف 100 / 2 صفحه با per_page=1) + search مثبت/منفی + کلیدهای 8 شمارنده |
| S-02 | `paused` در لیست: 0 → pause → 1 → resume → 0 |
| S-03 | `queue.counters` endpoint = بازمحاسبهٔ مستقیم از `knowledge_file_queue` (بعد از یک بچ واقعی good+corrupt) + `failed_by_stage` + شمارنده‌های خود ردیف batch |
| S-04 | شناسه‌های رجیستری در فهرست اسناد: پیش از پردازش falsy؛ پس از پردازش واقعی WF `work_id`+`edition_id` truthy، `volume_id` falsy (کتاب نمونه volume ندارد) + cross-check با `GET /works/<id>` |

اجرا:

```bash
cd backend
python -m unittest test_studio_api -v          # 7 tests
python -m unittest test_api test_projects test_dashboard \
  test_knowledge_api test_word_factory test_dump test_work_registry \
  test_queue test_corpus_builder test_studio_api -v
  # Ran 182 tests — OK
```

## ۶. محدودیت‌ها (صادقانه)

- کارت buildها (ES) هنوز «خالی» است — ES در V0.1 غیرفعال است و
  endpoint سازگاری صادقانه `NOT VERIFIED` می‌دهد (PCM-08/بعدی).
- پیکره‌های c-1 در استودیو نمایش داده **نمی‌شوند** — پیکره‌ساز offline
  CLI است (PCM-16) و خروجی‌اش در دایرکتوری‌های محلی/دیسک است، نه در
  DB؛ نمایش آن‌ها نیاز به قرارداد ذخیره‌سازی جدا دارد (خارج از PCM-17).
- retry فایل‌ناموفق از UI (فقط endpoint) در این فاز ساخته نشد.

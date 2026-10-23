# داشبورد پروژه‌ها (PCM-04)

داشبورد `/dashboard/` تب «📁 پروژه‌ها» را ارائه می‌دهد: فهرست همه‌ی پروژه‌های کراول با
صفحه‌بندی سمت سرور، جستجو، فیلتر وضعیت، مرتب‌سازی و نمای جزئیات هر پروژه.

## API

هر دو endpoint پشت احراز هویت هستند (PCM-09 — بدون کوکی session پاسخ `401`):

### `GET /api/dashboard/projects`

| پارامتر | پیش‌فرض | توضیح |
|---------|---------|-------|
| `search`  | — | LIKE روی `name` یا `host` |
| `status`  | — | فیلتر دقیق: `draft` / `tested` / `running` / `paused` |
| `sort`    | `updated_at` | فقط این ستون‌ها: `id, name, host, status, saved_count, updated_at, created_at` |
| `order`   | `DESC` | `ASC` / `DESC` |
| `page`    | `1` | شماره‌ی صفحه (از ۱) |
| `per_page`| `10` | ۱ تا ۱۰۰ |

پاسخ:

```json
{
  "projects": [
    {
      "id": 2, "name": "تفسیر تسنیم همتا", "host": "tasnim.hamtaa.org",
      "start_url": "https://...", "status": "running",
      "next_mode": "url_param", "next_param": "item_index", "next_step": 1,
      "saved_count": 197, "skipped_count": 0, "failed_count": 0,
      "cursor_url": "https://...item_index=39200",
      "last_message": "این دقیقه 4 ذخیره، 0 رد، 0 خطا.",
      "created_at": "2026-10-23 09:38:59", "updated_at": "2026-10-23 09:38:59",
      "fields_count": 5, "pages_count": 197
    }
  ],
  "total": 2, "page": 1, "per_page": 10, "total_pages": 1
}
```

- صفحه‌بندی: `COUNT(*)` برای `total` + `LIMIT ? OFFSET ?` — هیچ‌وقت کل جدول بارگذاری نمی‌شود.
- `fields_count` / `pages_count` با زیر‌پرس از `project_points` / `project_pages`.

### `GET /api/dashboard/projects/<id>/pages` (PCM-05)

فهرست صفحات ذخیره‌شده‌ی پروژه (فقط خواندنی):

| پارامتر | پیش‌فرض | توضیح |
|---------|---------|-------|
| `search`  | — | LIKE روی `url` **یا** `values_json` (متن هر فیلد) |
| `sort`    | `id` | فقط این‌ها: `id` / `captured_at` / `url` |
| `order`   | `DESC` | `ASC` / `DESC` |
| `page`    | `1` | از ۱ |
| `per_page`| `10` | ۱ تا ۱۰۰ |

پاسخ:

```json
{
  "pages": [
    {
      "id": 1,
      "url": "https://tasnim.hamtaa.org/payload?item_index=39004",
      "captured_at": "2026-10-23 08:50:16",
      "values": { "متن": "...", "برگ": "39004" },
      "prev_id": null,
      "next_id": 2
    }
  ],
  "total": 373, "page": 1, "per_page": 3, "total_pages": 125
}
```

- **`prev_id`/`next_id` با `LAG`/`LEAD`** محاسبه می‌شوند و **ترتیب خود لیست** را دنبال می‌کنند
  (همان `ORDER BY` + همان `WHERE`) — نه `id±1` خام؛ در هر sort/فیلتری درست‌اند.
- پروژه‌ی ناموجود → `404`.

### `GET /api/dashboard/projects/<id>/pages/<page_id>` (PCM-05)

جزئیات یک صفحه:

```json
{
  "id": 1,
  "url": "https://...",
  "captured_at": "2026-10-23 08:50:16",
  "content_hash": "9f2c...",
  "values": { "متن": "...", "برگ": "39004" },
  "raw_values_json": "{\"متن\": \"...\", \"برگ\": \"39004\"}",
  "position": { "index": 1, "total": 373 },
  "field_errors": []
}
```

- `position` بر اساس ترتیب ثبت (`id`) است؛ `field_errors` از PCM-07/08 شروع به پرشدن می‌کند
  (تا آن زمان خالی است — ساختگی نیست).
- صفحه‌ی ناموجود یا متعلق به پروژه‌ی دیگر → `404`.

### `GET /api/dashboard/projects/<id>`

آیتم کامل + موارد زیر:

```json
{
  "points": [ {"tag": "متن", "source": "css", "selector": "p.book-text", "transform": "text", "sample": "..."} ],
  "pages_summary": {
    "total": 197,
    "first_captured": "2026-10-23 08:50:16",
    "last_captured": "2026-10-23 09:39:33",
    "last_url": "https://...item_index=39200"
  },
  "values_sample": { "متن": "روحي انسان در بيداری ...", "برگ": "برگ 39200", "...": "..." }
}
```

`values_sample` = `values_json` آخرین صفحه‌ی ذخیره‌شده (پارس‌شده). پروژه‌ی ناموجود → `404`.

## UI

- تب «📁 پروژه‌ها»: کنترل‌های جستجو (نام/دامنه)، فیلتر وضعیت، مرتب‌سازی، تعداد در صفحه، جهت.
- دکمه‌ی «جزئیات» روی هر ردیف → کارت جزئیات: کارت‌های آمار (ذخیره/رد/خطا/صفحات/فیلدها)،
  جدول فیلدها (tag، source، selector، transform)، JSON آخرین صفحه با دکمه‌ی کپی،
  آدرس آخرین URL و دکمه‌ی بازگشت به فهرست.
- **کارت «📄 صفحات (N)» (PCM-05)**: مرور صفحه‌به‌صفحه — جستجو در URL یا متن فیلدها،
  sort (شماره/زمان ثبت/URL)، جهت، تعداد در صفحه، pager؛ هر ردیف URL (باز در تب جدید) +
  نمایه فیلدها + دکمه‌های «مشاهده» و «کپی».
- **نمای صفحه (PCM-05)**: Previous/Next بر اساس `prev_id`/`next_id` همان لیست (با همان
  فیلتر/sort)، موقعیت «X از Y»، جدول فیلدها با کل متن، JSON خام + کپی، hash محتوا.
  «بازگشت به فهرست» حالت (صفحه/جستجو/sort) را حفظ می‌کند؛ state در `pageBrowser` است تا
  رفرش خودکار ۱۰ ثانیه‌ای آن را بازنویسی نکند.
- صفحه‌بندی: دکمه‌های صفحه‌به‌صفحه + «صفحه X از Y».
- هر مقدار از API قبل از واردشدن در DOM از `escHtml` عبور می‌کند (XSS-safe).

## مهاجرت افزایشی

`ensure_dashboard_schema` (اجرا در `init_db` و در اولین request داشبورد):

1. اگر `projects.created_at` نیست: `ALTER TABLE projects ADD COLUMN created_at TEXT`
   + backfill: `UPDATE projects SET created_at = updated_at WHERE created_at IS NULL`.
   (SQLite در `ADD COLUMN` اجازه‌ی default غیرثابت مثل `datetime('now')` نمی‌دهد؛
   برای ردیف‌های جدید `create_project` مقدار را صریح ست می‌کند.)
2. ایندکس‌ها: `idx_projects_updated(projects.updated_at DESC)` و
   `idx_project_pages_captured(project_pages.project_id, captured_at)`.

هیچ داده‌ای حذف یا بازنویسی نمی‌شود؛ فقط ستون و ایندکس اضافه می‌شود.

## اصول

- **فقط خواندنی**: هیچ DELETE/UPDATE از این APIها انجام نمی‌شود.
- **پارامتری‌سازی کامل**: همه‌ی ورودی‌ها placeholder؛ `sort` از whitelist خارج → `updated_at`.
- **APIهای نوشتاری اکستنشن باز می‌مانند** (`/api/projects*`) تا کراول زنده قطع نشود.

تست‌ها: `backend/test_dashboard.py` → `D01..D07` (صفحه‌بندی، جستجو، فیلتر، sort،
جزئیات، 404، created_at) + `P01..P07` (PCM-05: صفحه‌بندی صفحات، جستجوی URL،
جستجوی متن فارسی فیلدها، Previous/Next هم‌راستای ترتیب لیست شامل فهرست فیلترشده،
جزئیات صفحه + position، 404ها و scope بین پروژه‌ها، sort DESC + url).

## دپلوی

`deploy/pcm05_deploy.sh`: بکاپ آنلاین DB + integrity + اسنپ‌شات کد → extract →
`docker compose build backend && up -d backend` (بدون `down`) → health-wait →
smoke (auth 401/200، dashboard 200، **pages list/detail با 401/404**، extension open) →
**regression نوشتاری** (ساخت پروژه + ذخیره صفحه، سپس پاک‌سازی) → مقایسه pre/post
شمارنده‌های پروژه ۲ + نمونه‌ی ۱۵ ثانیه‌ای برای تأیید ادامه‌ی کراول زنده.
بسته‌بندی کد: `deploy/pack_pcm05.py` (بدون .git/.env/DB).

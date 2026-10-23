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
جزئیات، 404، created_at).

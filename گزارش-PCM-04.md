# گزارش تحویل PCM-04 + PCM-09

**موضوع:** تب «پروژه‌ها» در داشبورد + احراز هویت رمز داشبورد
**تاریخ:** ۱۴۰۵/۰۸/۰۱ (2026-10-23) · **SHA:** `67cf03f` · **دپلوی:** s52

---

## ۱. وضعیت قبل از شروع

- داشبورد `/dashboard/` ۶ تب داشت (نمای کلی، اصطلاح‌نامه، بیانات، پیکره، صف، DB) — **بدون تب پروژه‌ها و بدون هیچ احراز هویتی**.
- کراول زنده فعال بود: پروژه «تفسیر تسنیم همتا» (id=2) با ۵ نقطه، ~۶۰ صفحه در ابتدای مأموریت و در حال رشد.
- `projects` ستون `created_at` نداشت (فقط `updated_at`).

## ۲. طراحی

**PCM-04 — نمای پروژه‌ها:**
- API خواندنی `GET /api/dashboard/projects` با جستجو (نام/دامنه)، فیلتر وضعیت، مرتب‌سازی از whitelist، و **صفحه‌بندی سمت سرور** (`COUNT(*)` + `LIMIT/OFFSET`).
- `GET /api/dashboard/projects/<id>` — جزئیات: فیلدها (نقاط)، خلاصه صفحات (تعداد/اولین/آخرین/آخرین URL)، و `values_sample` (مقادیر آخرین صفحه).
- UI: تب «📁 پروژه‌ها» با کنترل‌های جستجو/فیلتر/sort/صفحه‌بندی + کارت جزئیات (کارت‌های آمار، جدول فیلدها، JSON آخرین صفحه + کپی).

**PCM-09 — احراز هویت:**
- رمز فقط به‌صورت **scrypt-hash** (n=16384, r=8, p=1, salt ۱۶ بایتی) در `auth_meta`؛ plaintext فقط یک‌بار از `.env` سرور (`PCT_DASHBOARD_PASSWORD`) — gitignored، chmod 600.
- Session: توکن ۳۲ بایتی در `auth_sessions`، ۷ روز، قابل باطل‌کردن (logout)؛ cookie `pct_session` با `HttpOnly` + `Secure` (در HTTPS) + `SameSite=Lax`.
- Rate-limit: ۵ شکست در ۱۰ دقیقه از هر IP → 429 (DB-backed).
- **تصمیم کلیدی:** APIهای نوشتاری اکستنشن (`/api/projects*`) **باز می‌مانند** — کراول زنده هرگز با ورود داشبورد قطع نمی‌شود. فقط `/api/dashboard/*` و `/api/auth/*` پشت auth.

## ۳. مهاجرت‌ها (فقط افزایشی)

1. `projects.created_at TEXT` → `ALTER TABLE ... ADD COLUMN` + backfill از `updated_at`
   (SQLite در ADD COLUMN اجازه‌ی default غیرثابت نمی‌دهد؛ ردیف‌های جدید مقدار را در INSERT صریح می‌گیرند).
2. ایندکس‌ها: `idx_projects_updated(updated_at DESC)`، `idx_project_pages_captured(project_id, captured_at)`.
3. جداول `auth_meta`، `auth_sessions`، `auth_rate` (جدید، `CREATE TABLE IF NOT EXISTS`).

هیچ حذف/تغییر نوع ستونی نبود. اجرا: `deploy/pcm04_deploy.sh` (بکاپ → extract → rebuild).

## ۴. فایل‌ها و APIهای جدید/تغییرکرده

| فایل | نوع |
|---|---|
| `backend/auth.py` | **جدید** — scrypt، session، rate-limit، `make_require_auth`، روت‌های `/api/auth/*` |
| `backend/dashboard_api.py` | **جدید** — `ensure_dashboard_schema` + `GET /api/dashboard/projects[/<id>]` |
| `backend/server.py` | ProxyFix، wiring auth+dashboard در `init_db` و registration، بازگردانی `db.close()` |
| `backend/projects.py` | ستون `created_at` + ست کردن در INSERT |
| `dashboard/index.html` | تب پروژه‌ها + overlay ورود + `escHtml` + 401→login |
| `backend/Dockerfile` | COPY auth.py + dashboard_api.py |
| `docker-compose.yml` | `PCT_DASHBOARD_PASSWORD: ${PCT_DASHBOARD_PASSWORD:-}` (ارزش از .env سرور) |
| `backend/test_dashboard.py` | **جدید** — ۱۵ تست |
| `deploy/pcm04_deploy.sh` | **جدید** — دپلوی استاندارد با .env |

## ۵. نتایج تست (اجرای واقعی)

```text
cd backend && python -m unittest test_dashboard test_api test_projects
Ran 32 tests in 7.804s
OK
```

- `A01..A08`: status، 401، رمز اشتباه، ورود موفق، داده بعد از ورود، logout، rate-limit (۵ شکست→429 حتی با رمز درست)، **APIهای نوشتاری بدون auth باز** (کراول زنده امن).
- `D01..D07`: صفحه‌بندی (16 پروژه/2 صفحه)، جستجو، فیلتر وضعیت، sort `saved_count`، جزئیات (فیلدها + pages_summary + values_sample)، 404، `created_at`.

خطاهای پیدا و رفع‌شده در حین توسعه: (الف) `db.close()` جاافتاده در `init_db` که روی ویندوز DB موقت را lock می‌کرد؛ (ب) `DEFAULT (datetime('now'))` در `ALTER TABLE` نامعتبر بود → column ساده + backfill؛ (ج) bug در CASE منطق rate-limit (شمارنده هرگز جمع نمی‌شد) → مقایسه با `now - LOGIN_WINDOW`.

## ۶. نتیجه در production (smoke test واقعی)

| چک | نتیجه |
|---|---|
| health بعد از rebuild | ✅ healthy after 2s |
| `GET /api/auth/status` بدون cookie | ✅ `{"auth_enabled":true,"authenticated":false}` |
| `GET /api/dashboard/projects` بدون cookie | ✅ **401** `unauthorized` |
| `POST /api/auth/login` (رمز) | ✅ 200 + `{"ok":true}` + Set-Cookie |
| `GET /api/dashboard/projects` **با cookie** | ✅ 200 — پروژه id=2 «تفسیر تسنیم همتا» با 5 fields / **197 صفحه** |
| `GET /api/projects` (API اکستنشن) بدون cookie | ✅ 200 — **باز مانده** |
| `PRAGMA integrity_check` | ✅ ok |
| ستون `created_at` در `projects` | ✅ موجود (column 16) |
| جداول auth | ✅ ۳ جدول (`auth_meta`، `auth_sessions`، `auth_rate`) |
| **ادامه‌ی کراول زنده بعد از recreate** | ✅ 198 → **199** صفحه در ۱۲ ثانیه (status `running`) |

## ۷. SHA + لینک

- Commit: `67cf03fc163355f5c57e11ee8a780b6f45a39b42`
- لینک: https://github.com/saber13812002/persian-corpus-toolkit/commit/67cf03fc163355f5c57e11ee8a780b6f45a39b42
- Push: `2672c61..67cf03f main -> main` ✅

## ۸. git status (بعد از commit)

```text
git status --porcelain   → (خالی، همه‌چیز committed)
git log -1              → 67cf03f feat(pcm-04,pcm-09): dashboard projects view + password auth...
```

## ۹. بکاپ / Rollback

- **بکاپ DB:** `/home/saber/backups/thesaurus-<TS>.db` (`.backup` آنلاین + `integrity_check` = ok)
- **اسنپ‌شات کد:** `/home/saber/backups/pct-deploy-<TS>.tar.gz`
- **Rollback کد:** extract اسنپ‌شات روی `/home/saber/saberprojects/persian-corpus-toolkit` + `docker compose build backend && up -d backend`
- **Rollback DB:** `cp` بکاپ روی `backend/thesaurus.db`
- **تغییر رمز:** `UPDATE auth_meta SET value='<hash>' WHERE key='password_hash'` + `DELETE FROM auth_sessions;` (آموزش در `docs/dashboard-authentication.md`)

## ۱۰. موارد باقی‌مانده (برای فازهای بعد)

- **PCM-05:** مرور صفحه‌به‌صفحه / آیتم‌به‌آیتم صفحات ذخیره‌شده (prev/next بر اساس ترتیب فهرست، جستجو روی محتوای فیلد، کپی JSON هر صفحه)
- **PCM-06:** نمای آمار واقعی (شمارنده‌ها با تعریف مکتوب، بدون درصد ساختگی)
- **PCM-07:** ناوبری دوسویه + checkpoint/resume + کنترل Start/Pause/Resume/Retry Failed از داشبورد
- **PCM-08:** موتور transform (substring بعد از «برگ:»، حذف رشته، زنجیره‌ی قواعد) + reprocess کل پروژه
- **PCM-10:** health/metrics + ۴ داشبورد Grafana روی زیرساخت موجود s52

## ۱۱. روش تست دستی

1. مرورگر بدون ورود: `https://corpus.ai.ismc.ir/dashboard/` → overlay ورود نمایش داده می‌شود.
2. رمز را وارد کنید → تب «📁 پروژه‌ها»؛ پروژه «تفسیر تسنیم همتا» باید با ۵ فیلد و ~200 صفحه دیده شود.
3. «جزئیات» → جدول فیلدها + JSON آخرین صفحه (دکمه‌ی کپی کار می‌کند).
4. صفحه را در tab جدید باز کنید (بدون cookie) → `https://corpus.ai.ismc.ir/api/dashboard/projects` باید 401 بدهد.
5. اکستنشن کروم: کراول ادامه می‌یابد (شمارنده‌ی صفحات در داشبورد هر ۱۰ ثانیه رشد می‌کند) — ورود/خروج داشبورد روی آن اثر ندارد.
6. ۵ بار رمز اشتباه → 429 تا ۱۰ دقیقه بعد.

---
**نتیجه: PCM-04 + PCM-09 تحویل شد — 32/32 تست سبز، deploy سبز، کراول زنده بدون قطع‌شدن.**

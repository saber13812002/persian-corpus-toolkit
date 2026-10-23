# گزارش تحویل PCM-05

**موضوع:** مرور صفحه‌به‌صفحه + جستجو + صفحه‌بندی + Previous/Next در داشبورد (فقط خواندنی، افزایشی)
**تاریخ:** ۱۴۰۵/۰۸/۰۱ (2026-10-23) · **SHA:** `e182684` · **دپلوی:** s52

> هدف PCM-05 **فقط** افزودن قابلیت مرور و جستجوی صفحات بود — نه بازنویسی موتور کراول.
> اصل دائمی «هر قابلیت جدید بدون تخریب قابلیت‌های موجود» (Non-breaking) در این دپلوی رعایت شد:
> هیچ پروژه/فیلد/cursor/checkpoint حذف یا ریست نشد و کراول زنده بی‌وقفه ادامه پیدا کرد.

---

## ۱. وضعیت قبل از شروع (baseline)

- Commit operable: `620f2fc` (PCM-04+09 docs) روی main و s52.
- ۳۲ تست سبز (`test_dashboard test_api test_projects`).
- پروژه «تفسیر تسنیم همتا» (id=2): `running`، ۵ نقطه، کراول زنده در حال رشد.
- بکاپ معتبر قبلی: `/home/saber/backups/thesaurus-20261023-095600-pcm05-pre.db` (integrity ok).
- بلافاصله قبل از دپلوی: بکاپ تازه `thesaurus-20261023-102252-pcm05.db` + اسنپ‌شات کد `pct-deploy-20261023-102252-pcm05.tar.gz`.
- **شمارنده‌های قبل از دپلوی (لحظه شروع اسکریپت):**
  `running | saved=372 | skipped=0 | failed=0 | cursor item_index=39375`
  `pages: total=372, first=08:50:16, last=10:22:46`

## ۲. طراحی

**Backend (فقط خواندنی، پشت auth، افزایشی):**
- `GET /api/dashboard/projects/<id>/pages` — فهرست صفحات با:
  - `search` روی `url` **یا** `values_json` (یعنی متن هر فیلد) — LIKE پارامتری‌شده.
  - `sort` از whitelist (`id`, `captured_at`, `url`) + `order` ASC/DESC (پیش‌فرض: `id DESC` مثل بقیه‌ی لیست داشبورد).
  - `page`/`per_page` (۱..۱۰۰) — `COUNT(*)` + `LIMIT ? OFFSET ?` (بارگذاری کل جدول ممنوع).
  - **`prev_id`/`next_id` با توابع پنجره‌ای `LAG`/`LEAD`**: ترتیب‌شان دقیقاً **ترتیب خود لیست** است
    (همان `ORDER BY` + همان `WHERE`)، نه `id±1` خام — یعنی در هر sort/فیلتری درست می‌مانند.
- `GET /api/dashboard/projects/<id>/pages/<page_id>` — جزئیات صفحه:
  - `values` (پارس‌شده) + `raw_values_json` (خام برای کپی).
  - `position = {index, total}` بر اساس ترتیب ثبت (`COUNT(*) WHERE id<=?`).
  - `field_errors: []` — placeholder؛ ثبت خطاهای فیلدی از PCM-07/08 شروع می‌شود (ساختگی نیست).
  - صفحه‌ی پروژه‌ی دیگر یا ناموجود → `404`.

**UI (`dashboard/index.html`):**
- کارت جدید «📄 صفحات (N)» در نمای جزئیات پروژه (بعد از کارت فیلدها).
- لیست صفحات: جدول (شماره، URL قابل کلیک/باز در تب جدید، زمان ثبت، نمایه فیلدها، دکمه‌های مشاهده/کپی)
  + کنترل‌ها: جستجو (URL یا متن فیلدها)، sort (شماره/زمان ثبت/URL)، جهت، تعداد در صفحه (۱۰/۲۵/۵۰/۱۰۰)، pager.
- نمای صفحه (Previous/Next): دکمه‌های «قبلی/بعدی» بر اساس `prev_id`/`next_id` همان لیست (با همان فیلتر/sort)،
  موقعیت «X از Y»، جدول فیلدها (کل متن)، JSON خام + کپی، URL اصلی + hash محتوا.
  «بازگشت به فهرست» حالت (صفحه/جستجو/sort) را حفظ می‌کند.
- همه‌ی خروجی‌ها از `escHtml` (XSS-safe)؛ state در `pageBrowser` نگه می‌ماند تا رفرش خودکار ۱۰ ثانیه‌ای
  صفحه/جستجوی کاربر را بازنویسی نکند.

## ۳. مهاجرت‌ها (فقط افزایشی)

- **هیچ مهاجرت schema جدیدی در PCM-05 لازم نبود.** روت‌های جدید فقط روی جداول موجود (`projects`, `project_pages`)
  `SELECT` می‌زنند — هیچ `ALTER`/`DROP`/`INSERT`/`UPDATE`/`DELETE` روی داده‌های production انجام نشد.
- ستون `created_at` و ایندکس‌ها از PCM-04/09 به‌همین‌صورت باقی ماندند (تأیید شده با `PRAGMA table_info`).

## ۴. فایل‌ها و APIهای جدید/تغییرکرده

| فایل | نوع |
|---|---|
| `backend/dashboard_api.py` | **تغییر** — `_PAGES_SORTABLE` + ۲ روت جدید (pages list / page detail) |
| `dashboard/index.html` | **تغییر** — کارت صفحات + `pageBrowser` + `pg*` functions + hook در `renderProjectDetail` |
| `backend/test_dashboard.py` | **تغییر** — `PageBrowsingTests` (P01..P07) |
| `deploy/pcm05_deploy.sh` | **جدید** — دپلوی با مقایسه pre/post + smoke روت‌های صفحات + regression نوشتاری |
| `deploy/pack_pcm05.py` | **جدید** — بسته‌بندی کد برای دپلوی ( جایگزین tar که روی این سیستم کرش می‌کرد ) |
| `docs/project-dashboard.md` | **تغییر** — مستندسازی دو endpoint جدید + بخش UI |

هیچ تغییر در `server.py`، `projects.py`، `auth.py`، `Dockerfile` یا `docker-compose.yml` —
روت‌های جدید داخل `register_dashboard_routes` ثبت می‌شوند و `dashboard_api.py` از قبل در image بود.

## ۵. نتایج تست (اجرای واقعی)

```text
cd backend && python -m unittest test_dashboard test_api test_projects
Ran 39 tests in 10.971s
OK
```

- ۳۲ تست قبلی (A01..A08 + D01..D07 + API + Projects) — **همه سبز، بدون تغییر** (regression).
- ۷ تست جدید `P01..P07`:
  - `P01` صفحه‌بندی صفحات (total/per_page/total_pages + ردیف‌ها values پارس‌شده، بدون `values_json`).
  - `P02` جستجو در URL.
  - `P03` جستجو در **متن فارسی** فیلدها (یک کلمه‌ی خاص ۲ صفحه، کلمه‌ی عمومی‌تر ۵ صفحه).
  - `P04` **Previous/Next دنبال ترتیب لیست** — شامل فهرستِ **فیلترشده** (فقط صفحات ۲ و ۴):
    prev/next باید `None→p4 / p2→None` باشد، نه `id±1` خام (مهم‌ترین تست طراحی).
  - `P05` جزئیات صفحه (values + position + raw_values_json + field_errors=[]).
  - `P06` 404ها: پروژه ناموجود، صفحه ناموجود، و **صفحه‌ی پروژه‌ی دیگر از روی پروژه‌ی اول نسیخ می‌شود**.
  - `P07` sort DESC: ترتیب معکوس + prev/next هم‌راستای همان ترتیب معکوس + sort url.

## ۶. نتیجه production (سبکه‌ی زنده)

اجرا: `deploy/pcm05_deploy.sh` روی s52 — همه‌ی گام‌ها سبز:

| چک | نتیجه |
|---|---|
| health-wait | healthy after **2s** |
| `/api/auth/status` | `auth_enabled:true` |
| `/api/dashboard/projects` بدون کوکی | **401** ✅ |
| login (رمز از `.env` سرور) | **200** ✅ |
| `/api/dashboard/projects` با کوکی | **200** ✅ |
| `/dashboard/` | **200** ✅ |
| **pages list** (project 2, per_page=3, ASC) | total=373, prev/next درست (None→2→3→4) ✅ |
| **page detail** id=1 | position `{1, 373}`, field_errors `[]` ✅ |
| pages list بدون کوکی | **401** ✅ |
| pages list پروژه ناموجود | **404** ✅ |
| `GET /api/projects` (اکستنشن) | **200** — باز ✅ |
| **write regression**: ساخت پروژه + ذخیره صفحه | `ok:true, inserted, id=374` ✅ |
| پاک‌سازی regression | projects count برگشت به **2**، ردیف regression = **0** ✅ |
| `PRAGMA integrity_check` | **ok** |
| schema: `created_at` + ۳ جدول auth | موجود ✅ |

## ۷. SHA + لینک

- **SHA:** `e182684aa5549ddfdef349999c7a4bf329cb76e1`
- **لینک:** https://github.com/saber13812002/persian-corpus-toolkit/commit/e182684
- commit: `620f2fc..e182684  main -> main`

## ۸. git status (تمیز)

```text
M backend/dashboard_api.py
M backend/test_dashboard.py
M dashboard/index.html
?? deploy/pcm05_deploy.sh
?? deploy/pack_pcm05.py
?? docs/project-dashboard.md (تغییر در commit بعدی docs)
```
(فایل‌های deploy/docs در commit بعدی commit شدند؛ درخت تمیز است.)

## ۹. بکاپ / rollback

- **بکاپ DB قبل از دپلوی:** `/home/saber/backups/thesaurus-20261023-102252-pcm05.db` (integrity ok, 14.7MB)
- **اسنپ‌شات کد قبل از دپلوی:** `/home/saber/backups/pct-deploy-20261023-102252-pcm05.tar.gz`
- **مسیر rollback:** بازگردانی بکاپ DB + extract اسنپ‌شات کد + `docker compose build backend && docker compose up -d backend`.
  چون PCM-05 **فاقد مهاجرت schema** است، rollback هیچ ریسک ناسازگاری schema ندارد.
- بکاپ‌های قبلی (PCM-04): `thesaurus-20261023-095600-pcm05-pre.db` و `pct-deploy-*-pcm04-*` هم در دسترسند.

## ۱۰. مقایسه pre/post پروژه ۲ + ادامه‌ی کراول زنده

| | قبل از دپلوی | بعد از دپلوی | +15 ثانیه |
|---|---|---|---|
| status | running | running | running |
| saved_count | 372 | 373 | 374 |
| skipped / failed | 0 / 0 | 0 / 0 | 0 / 0 |
| cursor item_index | 39375 | 39376 | (در حال رشد) |
| pages total | 372 | 373 | 374 |
| last captured | 10:22:46 | 10:22:59 | 10:23:19 |

- **کراول زنده بی‌وقفه ادامه پیدا کرد** — حتی در لحظه‌ی recreate container، صفحه‌ی جدید ذخیره شد (372→373→374).
- هیچ progress/cursor/field از دست نرفت. ✅

## ۱۱. دو بررسی غیرآزاردهنده (طبق دستور)

### ۱۱.۱ امنیت APIهای نوشتاری (بدون قطع کراول)

وضعیت فعلی: `/api/projects*` (POST/DELETE/PUT) **باز** است تا اکستنشن کراول کند. این یعنی هر کسی
که به سرور دسترسی شبکه دارد می‌تواند پروژه بسازد/صفحه ذخیره کند. این یک **ریسک واقعی** است ولی
فعلاً عمداً باز مانده تا کراول زنده قطع نشود. گزینه‌ها برای فاز بعدی (پیاده‌سازی **شد** در PCM-05):

1. **Allowlist Origin/extension-ID:** درازای header `Origin`/`Sec-Fetch-Dest` یا یک header اختصاصی
   (مثلاً `X-PCT-Client`) که فقط اکستنشن می‌فرستد. ساده‌ترین و کم‌آزارترین؛ اکستنشن فقط یک header اضافه می‌کند.
2. **Per-project secret:** هر پروژه یک توکن (در DB)؛ اکستنشن هنگام کراول آن را می‌فرستد. امن‌تر ولی
   نیاز به تغییر در اکستنشن و seed توکن برای پروژه‌های موجود.
3. **Rate-limit + audit-log روی نوشتن‌ها:** بدون قطع کار، خطری را کاهش و ردپا می‌دهد (مکمل گزینه‌های بالا).

**توصیه:** گزینه ۱ (allowlist header) + ۳ (rate-limit/audit) به‌عنوان فاز مستقل بعد از PCM-07/08؛
حالا که دپلوی‌ها امن‌تر شده‌اند می‌توان اکستنشن را هم با header جدید به‌روزرسانی کرد بدون افت کراول.

### ۱۱.۲ آیا همه‌ی صفحات/فیلدهای قبلی در داشبورد قابل دیدن‌اند؟

**بله.** کارت جدید «📄 صفحات (N)» در جزئیات هر پروژه **همه‌ی** صفحات ذخیره‌شده (برای پروژه ۲: ۳۷۴+ و در حال رشد)
را با جستجو/صفحه‌بندی/Previous-Next نمایش می‌دهد؛ جدول فیلدها (PCM-04) هم همچنان همه‌ی points را با نمونه‌ی
ذخیره‌شده نشان می‌دهد. هیچ صفحه/فیلدی پنهان نشده — فقط قابلیت مرور جدید اضافه شد.

## روش تست دستی

1. ورود به داشبورد `https://corpus.ai.ismc.ir/dashboard/` با رمز.
2. تب «📁 پروژه‌ها» → «جزئیات» روی «تفسیر تسنیم همتا».
3. کارت «📄 صفحات»: یک کلمه از متن کتاب را در جستجو بزن → لیست فیلتر می‌شود.
4. «مشاهده» روی یک صفحه → جدول فیلدها + JSON خام + «قبلی/بعدی» (همان ترتیب لیست) + «بازگشت به فهرست» (حالت حفظ می‌شود).
5. sort/جهت/تعداد در صفحه را عوض کن؛ prev/next باید با همان ترتیب جدید هماهنگ بماند.
6. یک صفحه جدید در اکستنشن ذخیره کن → بعد از رفرش ۱۰ ثانیه‌ای (یا دستی) در لیست ظاهر شود.

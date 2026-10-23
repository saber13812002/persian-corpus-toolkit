# گزارش وضعیت PCM-02 — تکمیل Git، آماده‌سازی استقرار و تحویل عملیاتی

**تاریخ:** ۱۴۰۵/۰۸/۰۲ (2026-10-23)
**شعب:** `main`
**Repository:** https://github.com/saber13812002/persian-corpus-toolkit
**Production:** https://corpus.ai.ismc.ir (سرور s52 — `172.20.1.52:2222`، کاربر `saber`، ورود از طریق `jump53`)

---

## ۱. وضعیت فازهای PCM-02

| فاز | وضعیت | خلاصه |
|---|---|---|
| ۱ — بررسی کامل Git | ✅ | در مخزن صحیح، شعبه `main`، همگام با `origin/main` (آدرد عقب/پیش نیست) |
| ۲ — اجرای تست‌ها | ✅ | Backend **17/17** — UI **8/8** — syntax 6 JS — manifest معتبر |
| ۳ — Commit و Push | ✅ | HEAD روی remote: `b096e2d` — بدون force push |
| ۴ — آماده‌بودن Production | ⚠️ **BLOCKED** | `/api/projects` روی سرور **404** است (بکند قدیمی). SSH به s52 → `Permission denied (publickey)`؛ بررسی Docker/volume/DB روی سرور ممکن نبود |
| ۵ — استقرار | ⏸️ منتظر تأیید | برنامه در بخش ۳؛ طبق دستورالعمل بدون تأیید صریح کاربر اجرا نمی‌شود |
| ۶ — تست واقعی Chrome | ⏸️ **BLOCKED** | دسترسی به Chrome از این محیط نیست؛ چک‌لیست عملیاتی در بخش ۵ |
| ۷ — گزارش نهایی | ✅ | همین سند + پیام پایانی |

---

## ۲. نتیجه Git (تحقق‌شده روی remote)

| مورد | مقدار |
|---|---|
| Branch | `main` |
| Commit HEAD (روی remote) | `b096e2d6f4ed9bb045c147370907671465dea42c` |
| لینک مستقیم | https://github.com/saber13812002/persian-corpus-toolkit/commit/b096e2d6f4ed9bb045c147370907671465dea42c |
| Commit قبلی (کد PCM-01) | `e4a460014582dae992d1a5b6d14feb9bff00c2cc` — https://github.com/saber13812002/persian-corpus-toolkit/commit/e4a460014582dae992d1a5b6d14feb9bff00c2cc |
| Push | ✅ موفق، بعد از `git fetch` تأیید شد که `origin/main` دقیقاً روی HEAD است |
| توضیح | هنگام فاز ۳ مشخص شد کد PCM-01 از قبل به‌صورت commit `e4a4600` (پیام «کامیت») روی remote ثبت شده است. تغییرات باقی‌مانده (readme بازنویسی‌شده + این گزارش) با rebase تمیز روی آن سوار و push شدند — بدون force push، بدون overwrite. |

## ۳. شواهد تست (اجرا شده ۲۰۲۶-۱۰-۲۳)

### ۲.۱ Backend — `cd backend && python -m unittest test_api test_projects -v` (Python 3.14.7)

**Ran 17 tests — OK**

- `test_project_points_then_page_marks_tested` — دقیقاً همان مسیر `POST /api/projects` → `points` → `pages` که دکمه «ساختن از این صفحه» popup می‌زند
- `test_project_read_and_report_flow` — خواندن پروژه + گزارش اجرا (cursor/status)
- `test_projects.py` (T01–T12): ساخت، لیست، خواندن با ID واقعی، **باقی‌ماندن بعد از ریستارت بکند**، رد نام خالی، ردیابی endpoint ناشناخته 404، تکرار POST = ردیف‌های مجزا، سازگاری لیست بعد از ساخت، چند پروژه

### ۲.۲ UI — `cd extension && node test_popup.js`

**8 passed, 0 failed**

| تست | نتیجه |
|---|---|
| T03 انتخاب خودکار پروژه جدید در ComboBox | PASS |
| T04 بازگردانی انتخاب ذخیره‌شده بعد از بازکردن مجدد Popup | PASS |
| T05 بازسازی لیست بعد از Reload بدون گزینه تکراری | PASS |
| T07 رد نام خالی بدون POST + نمایش هشدار | PASS |
| T10 جلوگیری از کلیک دوتایی (فقط یک POST) | PASS |
| T08 بکند قطع → پیام روشن، بدون موفقیت کاذب | PASS |
| T11 POST موفق ولی فهرست نخوانده شد → پیام دوپهلو | PASS |
| 404 → پیام «سرور قدیمی است» | PASS |

### ۲.۳ sanity checks

- `node --check` روی `background.js`, `content_picker.js`, `content_thesaurus.js`, `content_khamenei.js`, `shared.js`, `popup.js` — همه OK
- `manifest.json` قابل‌تحلیل است (Manifest V3, v3.5, `content_picker.js` روی همه صفحات http/https ثبت است)
- ثبت routeها: [`register_site_routes` و `register_project_routes`](backend/server.py:1454) در ابتدای MAIN؛ `ensure_projects_schema` در `init_db`

### ۲.۴ امنیت commit

- `.gitignore` شامل `*.db`, `*.db-wal`, `*.db-shm`, `.env` است → هیچ دیتابیس عملیاتی یا رمزی stage نشده است
- فهرست stage: فقط ۱۴ فایل کد/اسناد مرتبط PCM-01/02 (در بخش ۴)

---

## ۴. وضعیت Production و برنامه استقرار

### ۴.۱ پرواز HTTP زنده (از شبکه کاربر، ۲۰۲۶-۱۰-۲۳)

| Endpoint | وضعیت | نتیجه |
|---|---|---|
| `GET /api/stats` | **200** | JSON معتبر — 1475 done / 1099 crawled |
| `GET /api/sites` | **200** | سایت تسنیم + 10 فیلد seed شده |
| `GET /api/projects` | **404** | ← **بکند سرور نسخه قدیمی است** |

**تشخیص قطعی:** بکند روی s52 بین نسخه‌های `4efe107` و `f40b0a6` کار می‌کند؛ ماژول‌های [`projects.py`](backend/projects.py:1) و `sites.py` و routeهایشان روی سرور نیستند. این همان خطای 404 گزارش‌شده PCM-01 است و **تنها** مانع عملیاتی ثبت پروژه است.

### ۴.۲ مانع دسترسی سرور

```
ssh s52  (HostName 172.20.1.52, Port 2222, User saber, از jump53)
→ Permission denied (publickey)
```

کلید SSH این دستگاه برای کاربر `saber` روی s52 ثبت نشده است. **تا رفع این مورد، فاز ۴ (بکاپ/شناسایی volume/rollback روی سرور) و فاز ۵ (استقرار) BLOCKED است.**

### ۴.۳ برنامه استقرار (برای اجرا فقط بعد از تأیید کاربر)

1. کد Commit جدید روی s52: `git pull` (یا clone تازه) — بدون تغییر دست‌نخورده روی داده‌ها.
2. شناسایی روش فعلی استقرار (compose/فولدر/volume واقعی) و ثبت در گزارش.
3. **بکاپ SQLite** (روش امن، نه copy فایل درحین‌نویس):
   ```bash
   sqlite3 /مسیر/thesaurus.db ".backup /root/backups/thesaurus-$(date +%Y%m%d).db"
   sqlite3 /root/backups/thesaurus-....db "PRAGMA integrity_check;"   # باید ok باشد
   ```
4. بازسازی تصویر: `docker compose build backend` (Dockerfile موجود [`backend/Dockerfile`](backend/Dockerfile:1) هر ۴ ماژول `server/projects/sites/sciences` را کپی می‌کند).
5. **به‌روزرسانی کم‌اختلال:** `docker compose up -d backend` — ⚠️ هرگز `docker-compose down`. Volume DB (فایل SQLite) دست‌نخورده می‌ماند.
6. Sanity: `curl -s http://127.0.0.1:5055/api/projects` → باید 200 با `{"projects":[...]}` باشد.
7. تأیید حفظ داده‌های قدیمی: مقایسه `crawled_total`/`queue_done` با خروجی `/api/stats` قبل از استقرار.
8. **Rollback:** تصویر قبلی باقی می‌ماند؛ `docker compose up -d backend` با تصویر قبلی. اسکیمای جدید **additive** است (فقط جدول‌های جدید `projects`, `project_points`, `project_pages`, `sites`, `site_fields`, `captures` — هیچ ستونی به جداول قدیمی اضافه/حذف نمی‌شود) → اجرای نسخه قدیمی روی DB جدید امن است.

### ۴.۴ تفاوت Local و Production (ثبت‌شده)

| مورد | Local | Production |
|---|---|---|
| کد | HEAD + تغییرات PCM-01 (این commit) | نسخه قبل از `projects.py` (404) |
| DB | `backend/thesaurus.db` (gitignored) | محل دقیق روی سرور باید در فاز ۴ شناسایی شود (محلی: volume `./backend/thesaurus.db`) |
| پورت | 127.0.0.1:5055 | پشت nginx → `corpus.ai.ismc.ir` |

---

## ۵. فهرست فایل‌های تغییرکرده در commitهای PCM-01/02

**کد Backend:**
- [`backend/projects.py`](backend/projects.py:1) — ★ سیستم پروژه (جدید): جدول‌ها + `GET/POST /api/projects`, `GET/POST /api/projects/<id>`, `points`, `pages`, `report`
- [`backend/sites.py`](backend/sites.py:1) — (جدید) سایت‌های نام‌دار + فیلدهای آماده (hamtaa seed شده)
- [`backend/server.py`](backend/server.py:1454) — ثبت routeهای projects/sites + `ensure_projects_schema`
- [`backend/test_projects.py`](backend/test_projects.py:1) — (جدید) 10 تست جریان پروژه
- [`backend/test_api.py`](backend/test_api.py:1) — 5 تست جدید پروژه/سایت
- [`backend/Dockerfile`](backend/Dockerfile:1) — (جدید) کپی هر ۴ ماژول

**اکستنشن:**
- [`extension/popup.js`](extension/popup.js:70) — ★ مدیریت خطا (`parseProjectResponse`), جلوگیری از کلیک دوتایی, بارگذاری مجدد/انتخاب خودکار/حفظ انتخاب ComboBox, پیام 404 «سرور قدیمی»
- [`extension/popup.html`](extension/popup.html:1) — بخش پروژه (نام، سرعت، ComboBox، دکمه‌ها)
- [`extension/background.js`](extension/background.js:1) — حلقه خواندن دقیقه‌ای با `chrome.alarms`، تست/شروع پروژه، resume
- [`extension/content_picker.js`](extension/content_picker.js:1) — (جدید) پنل روی صفحه: انتخاب المنت → نقطه، آزمایش، شروع خواندن
- [`extension/manifest.json`](extension/manifest.json:1) — v3.5، `content_picker.js` روی همه صفحات، `alarms`
- [`extension/test_popup.js`](extension/test_popup.js:1) — (جدید) 8 تست UI با DOM شبیه‌سازی‌شده

**زیرساخت/اسناد:**
- [`docker-compose.yml`](docker-compose.yml:1) — (جدید) backend محلی روی 127.0.0.1:5055
- [`readme.md`](readme.md:1) — بازنویسی کامل با استاندارد
- این سند + [`گزارش-وضعیت-پروژه.md`](گزارش-وضعیت-پروژه.md:1) (PCM-01)

---

## ۶. چک‌لیست تست واقعی Chrome (فاز ۶ — توسط کاربر/ایجنت با دسترسی Chrome)

بعد از استقرار فاز ۵ و تأیید:

1. اکستنشن را در `chrome://extensions` **Reload** کن.
2. صفحه‌ای از `tasnim.hamtaa.org` باز کن.
3. Popup را باز کن — نقطه وضعیت باید **سبز** («وصل به corpus.ai.ismc.ir») باشد.
4. نام یکتای آزمایشی بنویس (مثلاً `تست-PCM02-۱۴۰۵`) ← «ساختن از این صفحه».
5. popup باید «پروژه … ساخته شد» بگوید (نه «پروژه ساخته نشد»).
6. ComboBox همان پروژه را نشان می‌دهد و **خودکار انتخاب** است.
7. popup را ببند و باز کن — انتخاب حفظ شده باشد.
8. اکستنشن را Reload کن — انتخاب باز هم حفظ باشد.
9. `curl https://corpus.ai.ismc.ir/api/projects` → رکورد پروژه با ID واقعی موجود باشد.
10. (اختیاری، فقط با اجازه) حذف رکورد آزمایشی از SQLite بعد از آزمون.

**حداقل پذیرش PCM-01:** ثبت نام پروژه → ذخیره واقعی در Backend → نمایش در ComboBox → انتخاب خودکار → حفظ انتخاب بعد از بازکردن مجدد Popup.

---

## ۷. راهنمای تحویل به ایجنت‌های هوش مصنوعی (Handoff)

> این بخش برای ایجنت بعدی (یا توسعه‌دهنده) نوشته شده تا بدون مطالعه کامل کد، توسعه را ادامه دهد.

### ۷.۱ قوانین سخت
- فقط روی این repository کار کن؛ ارتباط با هیچ پروژه دیگری ندارد.
- **بدون تأیید صریح کاربر، هیچ تغییر روی Production** (s52 / `corpus.ai.ismc.ir`) — نه restart، نه rebuild، نه `docker-compose down`.
- `git add .` ممنوع؛ فقط فایل‌های مرتبط. بدون force push.
- دیتابیس (`*.db`)، `.env`، رمز و کلید هرگز در Git.
- آزمون خودکار سبز ≠ عملیاتی سبز؛ قبل از بستن هر PCM، آزمون واقعی Chrome الزامی است.

### ۷.۲ اجرای سریع
```bash
# Backend محلی (پورت 5055)
cd backend && pip install -r requirements.txt && python server.py

# یا با Docker
docker compose up -d --build

# تست‌ها (قبل از هر commit)
cd backend && python -m unittest test_api test_projects -v   # باید 17/17
cd extension && node test_popup.js                            # باید 8/8
node --check extension/popup.js extension/background.js extension/content_picker.js

# sanity API
curl http://127.0.0.1:5055/api/stats
curl http://127.0.0.1:5055/api/projects
```

### ۷.۳ معماری جریان پروژه (v3.5)
```
popup.js ──POST /api/projects {name,host,start_url,next_*}──► projects.py
   │                                                      │  جدول projects
   │ 200 {ok, project:{id}}                               │  جدول project_points
   ▼                                                      ▼
ComboBox (انتخاب خودکار + ذخیره در chrome.storage)     project_pages (dedup با SHA-256)
   │
content_picker.js (پنل روی صفحه): کلیک روی المنت → نقطه (tag/css/xpath/url/url_param + transform)
   │  POST /api/projects/<id>/points
   ▼
background.js: حلقه chrome.alarms — هر دقیقه N صفحه (N=1..12)
   │  هر صفحه: POST /api/projects/<id>/pages {url, values}
   │  بعد از هر نوبت: POST /api/projects/<id>/report {saved,skipped,failed,cursor_url,status}
   ▼
resume: `cursor_url` ستون پروژه است؛ بعد از هر صفحه ذخیره می‌شود.
        قطع شدن (باز کردن کروم، خالی ماندن 2 صفحه، refresh) → با restart/بازکردن،
        خواندن از `cursor_url` ادامه می‌یابد. شمارنده‌ها (saved/skipped/failed) تجمعی‌اند.
pause خودکار: بعد از 2 صفحه خالی پشت‌سرهم → status=paused (resume با شروع مجدد).
```

### ۷.۴ مراحل استفاده عملی (روند کاربر)
1. **دامنه:** صفحه سایت هدف در Chrome باز است (مثلاً `tasnim.hamtaa.org`).
2. **نام و دامنه:** در popup، نام پروژه را بنویس ← «ساختن از این صفحه» — `host` خودکار از URL تب خوانده می‌شود و پروژه سمت سرور ذخیره می‌شود.
3. **Inspect/نقطه‌ها:** «انتخاب و ویرایش» → پنل روی صفحه باز می‌شود؛ روی هر المنت کلیک → یک `tag` (مثل `verse_arabic`, `translation`, `page`) با selector و transform تعریف می‌شود (همان «اینسپکت المنت» به‌صورت امن بدون DevTools).
4. **آزمایش:** «آزمایش» یک صفحه را با همان نقاط استخراج و ذخیره می‌کند (اولین صفحه موفق → `status=tested`).
5. **کراول قطعه‌قطعه‌ی قابل‌ادامه:** «شروع خواندن» — هر دقیقه چند صفحه، شمارش saved/skipped در `/api/projects/<id>`؛ هر زمان قطع شد، از آخرین `cursor_url` ادامه می‌یابد.

### ۷.۵ افزودن دامنه/سایت جدید
1. اگر سایت «نام‌دار» است: در `sites.py` رکورد + فیلدهای پیش‌فرض (مثل seed تسنیم) اضافه کن و تست `test_api` بساز.
2. برای سایت دلخواهی: هیچ کدی لازم نیست — خودکار از popup ساخته می‌شود (host از URL). فقط نقطه‌ها در پنل تعریف می‌شوند.
3. transform جدید برای الگوهای خاص: در `content_picker.js` (سمت استخراج) و `projects.py` (معتبرسازی) — تست در `test_projects.py`.

### ۷.۶ عیب‌یابی سریع
| علامت | علت | اقدام |
|---|---|---|
| popup: «سرور نسخهٔ قدیمی است (404)» | بکند سرور بدون `projects.py` است | فاز ۵ این سند (بعد از تأیید) |
| `net::ERR_*` | پروکسی/HTTPS | `BACKEND` در `popup.js`/`background.js`/`content_picker.js` موقتاً `http://127.0.0.1:5055` |
| «این تب صفحه وب نیست.» | تب chrome:// یا about:blank | تب صفحه وب را فعال کن |
| 400 | نام/host خالی | نام را بنویس |
| 409 | تکرار | از لیست ComboBox انتخاب کن |
| `saved_count` بالا نمی‌رود | نقاط روی صفحه منطبق نیستند | پنل → «آزمایش» → نمونه‌ها را نگاه کن |

### ۷.۷ وضعیت‌های باز (backlog)
- B1 `background.js`: `sleep(2500)` ثابت بعد از `tabs.create` → تبدیل به polling `tabs.get` تا `status==='complete'`
- B2 `waitComplete` روی تب درحال-load گاهی فایر نمی‌شود → listener قبل از `tabs.update`
- `corpus/build_project_corpus.py`: خروجی `project_pages` به txt/jsonl
- RAG indexer
- CI: unittest + lint روی GitHub Actions
- یک `shared.js` واحد برای `BACKEND` (الان ثابت در 3 فایل اکستنشن)

---

## ۸. وضعیت نهایی PCM-01: **PARTIAL**

- کد و API: ✅ سالم و تست‌شده (17/17 + 8/8)
- Git: ✅ commit و push روی `origin/main` — HEAD `b096e2d`
- Backend Production: ⏸️ نسخه قدیمی (404 روی `/api/projects`) — استقرار منتظر تأیید کاربر + رفع دسترسی SSH
- Chrome E2E: ⏸️ انجام‌نشده — چک‌لیست بخش ۶

تا استقرار بکند و آزمون واقعی Chrome، PCM-01 بسته نمی‌شود و وارد توسعه عمیق Inspect Element/Crawler نمی‌شود.

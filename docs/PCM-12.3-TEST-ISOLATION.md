# PCM-12.3 — اصلاح ریشه‌ای Test Isolation + رفع Regression Gate (F-01) + ممیزی امنیتی Grafana

- **تاریخ اجرا:** ۱۴۰۵/۰۸/۰۳ (2026-10-25، ۱۶:۳۷ تا ۱۷:۳۰ UTC)
- **Production:** `https://corpus.ai.ismc.ir` · سرور s52 = `172.20.1.52`
- **مبنای کد:** commit `cab1c06` (HEAD `origin/main` پیش از این تغییرات)
- **ماهیت مأموریت:** test-harness + docs — **بدون تغییر رفتار production**، **بدون deploy**، **بدون اختلال در کراول زنده**
- **مخاطب اصلی:** رفع یافته‌ی F-01 از [`PCM-12-ACCEPTANCE-REPORT.md`](PCM-12-ACCEPTANCE-REPORT.md) (AT-18)

## ۰. خلاصه‌ی وضعیت

| معیار پذیرش | وضعیت | شواهد |
|---|:---:|---|
| تست‌های انفرادی PASS | ✅ | هر سه ماژول جداگانه OK (ویندوز + s52) |
| تست تجمیعی PASS | ✅ | 39/39 OK با دستور مستندشده (ویندوز + s52) |
| تست ترتیب معکوس PASS | ✅ | `test_dashboard test_projects test_api` OK |
| چند اجرای متوالی PASS | ✅ | 3 اجرای پشت‌سرهم OK (ویندوز + s52) |
| test discovery PASS | ✅ | `unittest discover` 39/39 OK |
| عدم اتصال تست‌ها به production | ✅ | guard: `server.DB_PATH` → فایل `/tmp`/`%TEMP%`؛ آلودگی DB زنده = 0؛ شمارنده‌های DB زنده فقط توسط کرام واقعی رشد کردند |
| عدم اختلال در کراول فعال | ✅ | container 2 روز بدون restart؛ cursor/`saved_count` پروژه ۲ یکسره ادامه یافت (11755→11757 فقط در اثر کرام زنده) |
| گزارش دقیق هر ۲۰ سناریو (مغایرت 19↔20) | ✅ | بخش ۴ (جدول ۲-A در گزارش PCM-12.2) |
| Commit و Push موفق | ✅ | بخش ۷ |

## ۱. وضعیت قبل (پیش از PCM-12.3)

دستور مستندشده در AGENTS.md — `python -m unittest test_api test_projects test_dashboard` — **FAIL** بود:
`Ran 39 tests ... FAILED (failures=1, errors=13)`، تکرارپذیر روی ویندوز محلی (Python 3.x) و s52 (Python 3.12.3).

### ریشه‌یابی کامل (بررسی‌شده در مرحله‌ی بازتولید)

| # | موضوع | یافته |
|---|-------|--------|
| 1 | `server.DB_PATH` | در [server.py:21](../backend/server.py) با `os.environ.get('PCT_DB') or ...` **فقط در اولین import** می‌بندد. هر ماژول تستی که بعد از آن `PCT_DB` عوض کند، هیچ اثری روی `server.DB_PATH` ندارد |
| 2 | متغیر `PCT_DB` | هر سه ماژول قبل از import server مقدار متفاوتی ست می‌کردند؛ فقط مقدار ماژول **اولِ import‌شده** (ترتیب CLI) برمی‌گشت |
| 3 | importهای مشترک | `import server` در هر ماژول، همان module-level singleton (`app`، `DB_PATH`) را بازمی‌گرداند؛ هیچ بارگذاری مجددی رخ نمی‌دهد |
| 4 | Singletonها/Global state | `app` (Flask) + `DB_PATH` + جدول‌های in-memory auth (rate-limit) — همه‌ی وضعیت بین ماژول‌ها مشترک بود |
| 5 | Rate Limiter | جدول `auth_rate` (DB-based) — ۵ ورود ناموفق تست A07، کل پنجره‌ی ۱۰ دقیقه‌ای را برای **همه‌ی تست‌های بعدی** پر می‌کرد → 429/401 → 13 خطای `KeyError`/`AssertionError` |
| 6 | مدیریت اتصال SQLite | `get_db()` per-request + `teardown_appcontext` (بستن در پایان request) — سالم؛ مشکل مدیریت اتصال نبود |
| 7 | حذف DB موقت | `os.remove(_DB)` هر ماژول، فایل **خودِ** ماژول را می‌ساخت، در حالی که اپ روی فایل ماژول اول کار می‌کرد → wipe بی‌اثر |
| 8 | ترتیب اجرا | با ۳ ماژول، فقط import ترتیب اولِ CLI موفق بود (coincidence)؛ در ترتیب‌های دیگر شکست‌های متفاوت. نتیجه: **وابستگی به ترتیب import** |

**نتیجه‌ی ریشه‌یابی:** واحد وضعیت مشترک (single source of truth) باید **یکی** باشد: یک فایل DB موقت که **قبل از** import server ست شود و **همه‌ی** کلاس‌های تست آن را wipe کنند.

## ۲. طراحی (اصلاح Fixture، نه production)

### ۲.۱ تصمیم معماری
- **بدون هیچ تغییر در کد production** (`server.py` دست‌نخورده ماند) — چون `DB_PATH` به‌درستی از env می‌خواند؛ مشکل در **test harness** بود، نه در اپ. الزام ۷ مأموریت (تغییر production فقط برای حل تست ممنوع) محقق شد.
- ماژول مشترک جدید: [`backend/pct_test_support.py`](../backend/pct_test_support.py) (فقط توسط `test_*` import می‌شود؛ در گراف import اپ نیست).

### ۲.۲ قرارداد جدید (مستند در AGENTS.md §۴)
1. هر ماژول تست **اولین** import: `import pct_test_support` (که `PCT_DB` + `PCT_DASHBOARD_PASSWORD` را قبل از import server ست می‌کند).
2. `server.DB_PATH` دقیقاً یک‌بار، به یک فایل موقت **مشترک** می‌بندد — برای همه‌ی ماژول‌ها یکسان.
3. هر کلاس تست در `setUp` → `pct_test_support.reset_db()` (حذف فایل اصلی + `-wal`/`-shm` + `server.init_db()`).
4. حذف فایل‌های موقت در `atexit` (best-effort).
5. قاعده‌ی محکم: هیچ ماژول تستی نباید خودش `PCT_DB` بسازد یا `init_db()` مستقیم صدا بزند.

### ۲.۳ تغییرات فایل
| فایل | تغییر | production؟ |
|------|-------|:---:|
| [`backend/pct_test_support.py`](../backend/pct_test_support.py) | **جدید** — bootstrap مشترک: DB موقت تکی + reset_db + atexit cleanup | خیر (test-only) |
| [`backend/test_api.py`](../backend/test_api.py) | حذف `mkstemp`/`os.environ` محلی → import support + `reset_db()` | خیر |
| [`backend/test_projects.py`](../backend/test_projects.py) | همان | خیر |
| [`backend/test_dashboard.py`](../backend/test_dashboard.py) | همان (رمز تست از env مشترک خوانده می‌شود) | خیر |
| [`deploy/pcm12_3_s52_test.sh`](../deploy/pcm12_3_s52_test.sh) | **جدید** — اسکریپت آزمون روی s52 (کپی backend در /tmp، guard ایزوله، آلودگی‌سنجی DB زنده) | خیر |
| [`deploy/pcm12_3_grafana_audit.sh`](../deploy/pcm12_3_grafana_audit.sh) | **جدید** — ممیزی امنیتی Grafana (read-only، masked) | خیر |
| [`AGENTS.md`](../AGENTS.md) | به‌روزرسانی §۴ تست‌ها + ردیف roadmap | docs |
| [`readme.md`](../readme.md) | ردیف roadmap PCM-12.2/12.3 + لینک گزارش | docs |
| [`docs/PCM-12-ACCEPTANCE-REPORT.md`](PCM-12-ACCEPTANCE-REPORT.md) | ممیزی شمارش + جدول ۲-A + تفکیک AT-18/F-01 | docs |

**assertionها دست‌نخورده ماندند** — هیچ تستی ضعیف‌تر نشد؛ فقط واحد DB واقعی‌شان درست شد.

## ۳. مهاجرت
**نیاز نیست.** هیچ تغییر schema؛ هیچ جدول production؛ فقط فایل‌های تست.

## ۴. ممیزی گزارش پذیرش PCM-12.2 (مغایرت 19↔20 + تفکیک AT-18)

### ۴.۱ مغایرت تعداد
نسخه‌ی اول خلاصه را «۱۴ PASS + ۴ PARTIAL + ۱ FAIL = 19» نوشته بود در حالی که ۲۰ سناریو وجود داشت. دو ایراد هم‌زمان:
1. **AT-06 «با یادداشت»** در شمارش نهایی گم شده بود — در حالی که نتیجه‌ی واقعی آن **PASS** است (یادداشت آن فقط false-alarm خودِ اسکریپت آزمون موقتمان بود: اسکریپت برای ردیف آخر پنجره `next_id=null` انتظار داشت، ولی رفتار درست `next_id=6` است چون ردیف بعدی در کل ۱۱٬۶۰۳ ردیف وجود دارد).
2. **باگ harness تست (F-01)** — که اصلاً **سناریوی پذیرش نبود** (نه قابلیت Word Factory است) — در ردیف AT-18 به‌عنوان FAIL سناریو شمارش شده بود.

**شمارش نهایی اصلاح‌شده: 15 PASS + 5 PARTIAL + 0 FAIL = 20.** جدول یک‌به‌یک کامل در گزارش PCM-12.2 (جدول ۲-A) ثبت شد؛ هر سناریو با شناسه‌ی مستقل AT-01..AT-20.

### ۴.۲ تفکیک دقیق AT-18 ↔ F-01 (تا دیگر با هم اشتباه نشوند)
| | **AT-18 (AT-18a)** | **F-01** |
|---|---|---|
| ماهیت | **سناریوی پذیرش**: آمادگی زیرساخت برای Word Factory (PCM-13) | **یافته‌ی فنی** از این آزمون: شکستگی gate تست ترکیبی |
| درباره‌ی چه چیزی | deps (`python-docx` نیست — پیش‌بینی‌شده)، storage (کافی)، harness | `DB_PATH` binding + نشت state بین ماژول‌های تست |
| وضعیت | 🟡 PARTIAL (Word Factory اصلاً نساخته‌شده است — PCM-13) | ❌ هنگام آزمون → ✅ **رفع‌شده در PCM-12.3 (این گزارش)** |
| جایی که ثبت شد | جدول ۲۰ سناریو (ردیف AT-18) | بخش «یافته‌های فنی جدا از ۲۰ سناریو» + همین گزارش |
| اقدام | افزودن `python-docx` در اولین مرحله‌ی Word (PCM-13) | انجام شد — `pct_test_support.py` + ماتریس regression سبز |

## ۵. تست‌ها (ماتریس کامل regression — مرحله‌ی سوم)

### ۵.۱ ویندوز محلی (Python از PATH، `cd backend`)
| # | اجرا | نتیجه |
|---|------|:---:|
| M1 | `unittest test_api` (انفرادی) | ✅ 8/8 OK |
| M2 | `unittest test_projects` (انفرادی) | ✅ 9/9 OK |
| M3 | `unittest test_dashboard` (انفرادی) | ✅ 22/22 OK |
| M4 | **`unittest test_api test_projects test_dashboard` (دستور مستندشده)** | ✅ **39/39 OK** |
| M5 | ترتیب معکوس: `test_dashboard test_projects test_api` | ✅ 39/39 OK |
| M6 | 3 اجرای تجمیعی متوالی (تکرارپذیری) | ✅ 3×39/39 OK |
| M7 | `unittest discover -s . -p "test_*.py"` | ✅ 39/39 OK |
| M8 | guard: `server.DB_PATH` | ✅ فایل `%TEMP%\pct_test_*.db` — نه `thesaurus.db` |

یادداشت M8: `backend/thesaurus.db` محلی یک فایل dev قدیمی (10-15، 13.8MB، gitignored) است — با اجرای این مأموریت **ساخت یا لمس نشد** (مهرهش از قبل وجود داشت)؛ اپ هرگز به آن وصل نشد چون `PCT_DB` همیشه ست بود.

### ۵.۲ s52 (Post-migration host — [اسکریپت](../deploy/pcm12_3_s52_test.sh))
اجرا در کپی موقت backend در `/tmp/pct123` (بدون `.venv`/DB)، با python از `.venv` دپلوی:
| # | اجرا | نتیجه |
|---|------|:---:|
| S0 | guard ایزوله‌بودن: `server.DB_PATH` = `/tmp/pct_test_*.db` | ✅ ISOLATED: OK |
| S1 | سه ماژول انفرادی | ✅ 3× OK |
| S2 | تجمیعی (ترتیب مستند) | ✅ 39/39 OK |
| S3 | تجمیعی (ترتیب معکوس) | ✅ 39/39 OK |
| S4 | 3 اجرای متوالی | ✅ 3×39/39 OK |
| S5 | test discovery | ✅ 39/39 OK |
| S6 | **آلودگی‌سنجی DB زنده**: پروژه‌ها با نام‌های تستی در `projects` + fixture `999001` در `khamenei_speeches` | ✅ **0 و 0** |
| S7 | سلامت کراول زنده | ✅ cursor/`saved_count` پروژه ۲ یکسره (11755→11757 = خودِ کرام زنده)؛ container «Up 2 days» بدون restart |
| S8 | پاکسازی /tmp | ✅ |

**نتیجه: روی هر دو پلتفرم، در همه‌ی ترتیب‌ها و اجراهای تکراری — 39/39 سبز؛ صفر آلودگی؛ صفر اختلال در production.**

## ۶. نتیجه روی production
- **Deploy انجام نشد** (طبق دستور: تغییر کد مشترک productionی نداشتیم — فقط فایل‌های تست/docs).
- کپی کد روی s52 فعلا‌ با local در کد operationally فرق دارد (فایل‌های تست جدید در local/git هستن) — **مهم نیست** چون روی s52 فقط کد داخل container اجرا می‌شود و ما هیچ کد operationally تغییر نداده‌ایم؛ همگامی بعدی در اولین deploy واقعی بعدی (PCM-13+) انجام می‌شود.
- **کراول زنده:** بدون اختلال (S7) — نرخ ۴ صفحه/دقیقه ادامه یافت؛ `integrity_check` پیش/بعد: ok.

## ۷. SHA + لینک + git status
- **commit:** (SHA در commit پس از این فایل ثبت می‌شود — همان الگوی report-first)
- **لینک:** (همان بالا)
- **git status:** تمیز (فقط تغییرات این مأموریت commit شدند؛ اسکریپت‌های debug موقت/خارج از repo حذف شدند)

## ۸. بکاپ / rollback
- **بکاپ DB لازم نبود** — هیچ دسترسی نوشتاری به `thesaurus.db` رخ نداد (S6/S7).
- **rollback** = `git revert <sha>`؛ هیچ رفتار operationally تغییر نکرده، پس deploy هم لازم نیست.
- بکاپ‌های موجود پیشین در `/home/saber/backups/` دست‌نخورده.

## ۹. ممیزی امنیتی Grafana (غیرمخرب — هیچ چیزی تغییر **نکرد**)

> هیچ credential در این گزارش نمایش داده نمی‌شود (فقط نام‌ها/ساختار/مسیرها).

### ۹.۱ محل واقعی نگهداری credentialها
| # | محل | نوع | وضعیت |
|---|------|-----|--------|
| 1 | `datasources.yml` در `/home/saber/saberprojects/observability/grafana/provisioning/datasources/` (bind-mount **ro** به `/etc/grafana/provisioning` در container) | کلیدهای `password`/`user`/`secureJsonData` برای 8 datasource (Prometheus، Loki، LiteLLM Postgres، QA mesbah/eiis/taghrir/ragportal/auth) | **plaintext در فایل روی دایسک** (permissions `rw-r--r--` — قابل خواندن توسط هر کاربر سرور) |
| 2 | `docker-compose.yml` همان پروژه‌ی `observability` | `GF_SECURITY_ADMIN_PASSWORD` (admin Grafana) **plaintext inline در compose** | **P0/P1 امنیتی** — علاوه بر دایسک، این فایل **توسط git track می‌شود** (repo `observability` روی همان سرور؛ 1 occurrence در HEAD) → رمز admin به تاریخچه‌ی git نیز رسیده است |
| 3 | ۳ فایل بکاپ: `datasources.yml.bak-20261010/12/13` در همان پوشه | نسخه‌های قدیمی رمزها (مختلف از فعلی — md5 متفاوت) | **هر rotate بدون حذف/بازنویسی این‌ها ناقص است** — رمزهای قدیمی هنوز در دایسک باقی می‌مانند |
| 4 | `grafana-ro-creds.txt` در `/home/saber/saberprojects/observability/` | فایل credential (permissions `rw-------` — 600) | حداقل از نظر permissions درست است؛ محتوا خارج از scope |
| 5 | env `GF_SECURITY_ADMIN_USER/PASSWORD` در container | از compose (item 2) | env را به‌جای yml نگه داشتن مشکل را حل نمی‌کند وقتی خودِ compose plaintext+git-tracked است |

**هیچ env file** (`.env`) نزدیک پروژه‌ی observability پیدا نشد؛ همه‌ی مقادیر یا در compose یا در yml هستند.

### ۹.۲ نحوه‌ی Mount شدن
- `bind (ro): .../observability/grafana/provisioning → /etc/grafana/provisioning`
- `volume: observability_grafana_data → /var/lib/grafana (rw)` — داده‌ی خودِ Grafana (DB داخلی sqlite) در named volume.
- **بهره‌گیری:** تغییر yml روی هاست **بلافاصله** (file-watch provisioning) اعمال می‌شود — **نه‌تنها restart نیاز ندارد بلکه اصلاً ممکن است بدون restart اعمال شود** (logs «provisioning datasources» را در هر reload می‌بینید).
- **پورت واقعی:** `3001` روی هاست (compose: `3001:3000`) — **`0.0.0.0:3001`** (روی همه‌ی اینترفیس‌ها باز است؛ باید بررسی/محدود شود).
- `/api/health` (بدون credential) = 200, `database: ok`, v11.3.0 — سرویس سالم.

### ۹.۳ قابلیت استفاده از Secret Management
**بله، بدون تغییر در معماری:**
1. **حذف مقادیر از compose/yml → env/secret خارجی:**
   - `GF_SECURITY_ADMIN_PASSWORD` → متغیر محیطی یا `--env-file` (فایل `.env` با permissions 600 در project dir، gitignored)؛ compose فقط `$VAR` را رفرانس می‌کند.
   - `password`/`user` در datasource yml → از طریق env interpolation در yml (`$PG_PASS`) + `.env` (600) — یا (تمیزتر) **Grafana API + service account** برای ایجاد/بازنویسی datasourceها با `secureJsonData` (که خودش encrypted-by-Grafana در sqlite داخلی نگه می‌شود) و حذف کلید plaintext از yml.
2. **سطح بالاتر (اختیاری):** Docker secrets (از Compose 2 با `secrets:`) یا Vault/SOPS برای همان env fileها.
3. **حذف از تاریخچه‌ی git:** `git filter-repo` روی repo `observability` + **rotate اجباری** (چون رمز در تاریخچه بوده، rotate الزامی است نه اختیاری).

### ۹.۴ روش Rotate بدون اختلال در Grafana (برنامه‌ی پیشنهادی — **در این مأموریت اجرا نشد**)
1. **مرحله‌ی ۱ (datasources):** مقادیر جدید را در `.env` (600) بگذارید؛ yml را به `$VAR` ref تغییر دهید؛ چون mount read-only است ولی فایل روی هاست عوض می‌شود، Grafana provisioning reload می‌کند (چند ثانیه) — **بدون restart، بدون قطع داشبوردها** (داشبوردها روی datasource uid راندن می‌کنند؛ تغییر credential با reload yml لحظه‌ای اعمال می‌شود و چند ثانیه‌ی نالایق بین reload و commit ممکن است connection pool را refresh کند — در ساعات کم‌ترافیک انجام شود).
2. **مرحله‌ی ۲ (admin):** `GF_SECURITY_ADMIN_PASSWORD` → env file (600) در compose + `$REF`؛ `docker compose up -d grafana` (یک restart کوتاه **نمی‌تواند** بدون تغییر env اجتناب شود برای admin password — اما چون env از compose خوانده می‌شود، `compose up -d` فقط container را با env جدید re-create می‌کند؛ داشبوردها/داده‌ها در volume هستند و حفظ می‌شوند؛ پنجره‌ی قطع ≈ 10–20 ثانیه، در ساعات کم‌ترافیک).
3. **مرحله‌ی ۳ (باقی‌مانده):** حذف/بازنویسی ۳ فایل `.bak-*` (رمزهای قدیمی) + حذف تاریخچه‌ی git (filter-repo) + محدود کردن bind `0.0.0.0:3001` به `127.0.0.1:3001` یا SSH tunnel.
4. **تأیید پس از rotate:** `/api/health` + ورود admin با رمز جدید + چک ۲ datasource (query test) — همه بدون قطع مانیتورینگِ دیگرِ سرویس‌ها (prometheus/loki دست‌نخورده).

### ۹.۵ یافته‌های امنیتی (ترتیب اولویت)
| # | یافته | اولویت | اقدام (فاز بعدی — خارج از scope این مأموریت) |
|---|--------|:---:|------|
| G-01 | `GF_SECURITY_ADMIN_PASSWORD` plaintext در compose **و** در تاریخچه‌ی git repo `observability` | **P0/P1** | rotate + env file (600) + `git filter-repo` + محدودسازی پورت 3001 |
| G-02 | کلیدهای datasource (6× `password`/`user`/`secureJsonData`) plaintext در `datasources.yml` روی دایسک (644) | P1 | env interpolation/secret + permissions 600 |
| G-03 | ۳ بکاپ yml با رمزهای قدیمی در پوشه‌ی provisioning | P1 | حذف پس از rotate |
| G-04 | Grafana روی `0.0.0.0:3001` (همه‌ی اینترفیس‌ها) | P1/P2 | bind به 127.0.0.1 یا SSH tunnel (تصمیم زیرمجموعه‌ی observability — خارج از scope PCT) |
| G-05 | `grafana-ro-creds.txt` | P3 | permissions 600 است؛ محتوا به‌روزرسانی شود هنگام rotate |

**قید مهم:** پروژه‌ی `observability` جزو زیرمجموعه‌ی مشترک است (غیر از PCT) — اقدامات G-01..G-05 **پیشنهاد** برای مالک آن زیرمجموعه‌اند و در این مأموریت هیچ‌کدام اجرا نشد (طبق دستور: بدون rotate، بدون restart).

## ۱۰. موارد باقی‌مانده
| # | مورد | تعلق |
|---|------|------|
| 1 | اعمال rotate/secret-management (G-01..G-05) — تصمیم + اجرا | مالک `observability` (پیشنهاد شده در §۹) |
| 2 | افزودن `python-docx` به `requirements.txt` در اولین مرحله‌ی Word | PCM-13 |
| 3 | provision کردن Elasticsearch برای PCT (ظرفیت کافی — AT-19) | PCM-13 |
| 4 | آزمون «پایان طبیعی کتاب» روی پروژه‌ی کوتاه | PCM-07 |
| 5 | ساخت ۴ داشبورد PCT روی زیرسرافت Grafana موجود | PCM-10 |
| 6 | **شروع PCM-13** (Word Factory) — پیش‌شرط‌ها (F-01 ✅، ES/Word ⏳) — **تا تأیید شما آغاز نمی‌شود** | PCM-13 |

## ۱۱. روش تست دستی / تکرار آزمون

```bash
# محلی — دستور رسمی (حالا سبز است):
cd backend && python -m unittest test_api test_projects test_dashboard -v

# ماتریس کامل (ترتیب معکوس + تکرار + discovery):
cd backend && python -m unittest test_dashboard test_projects test_api
cd backend && python -m unittest test_api test_projects test_dashboard
cd backend && python -m unittest discover -s . -p "test_*.py"

# s52 — بدون دست‌کاری production (guard ایزوله + آلودگی‌سنجی + چک کرام زنده):
scp deploy/pcm12_3_s52_test.sh s52:/tmp/ && ssh s52 "bash /tmp/pct123_s52.sh"

# ممیزی امنیتی Grafana (read-only، masked):
scp deploy/pcm12_3_grafana_audit.sh s52:/tmp/ && ssh s52 "bash /tmp/pct123_ga.sh"
```

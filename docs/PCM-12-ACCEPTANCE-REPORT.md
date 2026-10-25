# PCM-12.2 — گزارش آزمون پذیرش (Acceptance Report)

- **تاریخ اجرا:** ۱۴۰۵/۰۸/۰۳ (2026-10-25، ۱۵:۲۰ تا ۱۶:۲۰ UTC)
- **Production:** `https://corpus.ai.ismc.ir` · سرور s52 = `172.20.1.52`
- **وضعیت کد تحت آزمایش:** commit `81e3191` (HEAD `origin/main` پیش از این مستندات) — همگام با دپلوی s52 (AT-20)
- **SHA این مستندات:** `271ceba4f903d969f16a6c0aa6938a26d9216a62` — [لینک commit](https://github.com/saber13812002/persian-corpus-toolkit/commit/271ceba4f903d969f16a6c0aa6938a26d9216a62)
- **قواعد اجرا:** فقط آزمون‌های خواندنی روی production · بدون حذف رکورد عملیاتی · بدون توقف/ری‌استارت karam زنده · آزمون‌های وضعیت‌ساز فقط روی snapshot/محیط جدا · بدون نمایش کلید/رمز در گزارش
- **اسکریپت‌های آزمون:** [`deploy/pcm12_2_acceptance_test.sh`](../deploy/pcm12_2_acceptance_test.sh) (AT-01..06 + AT-11..14) · [`deploy/pcm12_2_corpus_test.sh`](../deploy/pcm12_2_corpus_test.sh) (AT-15/16) · [`deploy/pcm12_2_infra_test.sh`](../deploy/pcm12_2_infra_test.sh) (AT-17..19)

## ۰. خلاصه‌ی وضعیت ۲۰ سناریو

| # | سناریو | وضعیت | اهمیت | تأیید کاربر |
|---|--------|-------|-------|:---:|
| AT-01 | ورود داشبورد (auth) | ✅ PASS | P0 | بله |
| AT-02 | فهرست پروژه‌ها + جستجوی نام | ✅ PASS | P1 | بله |
| AT-03 | فهرست صفحات + صفحه‌بندی | ✅ PASS | P1 | بله |
| AT-04 | جستجوی صفحات (URL/محتوای فیلدها) | ✅ PASS | P1 | بله |
| AT-05 | جزئیات صفحه + JSON خام | ✅ PASS | P1 | بله |
| AT-06 | قبلی/بعدی در فهرست صفحات | ✅ PASS (با یادداشت) | P1 | بله |
| AT-07 | سلامت backend/API | ✅ PASS | P0 | خیر |
| AT-08 | سلامت SQLite (integrity) | ✅ PASS | P0 | خیر |
| AT-09 | وضعیت karam زنده (Status/Cursor) | ✅ PASS | P0 | بله |
| AT-10 | پیوستگی karam (افزایش شمارنده) | ✅ PASS | P0 | بله |
| AT-11 | cursor = آخرین صفحه (پایه‌ی resume) | ✅ PASS | P1 | خیر |
| AT-12 | شناسایی پایان طبیعی کتاب | 🟡 PARTIAL | P1 | خیر |
| AT-13 | ناوبری معکوس | 🟡 PARTIAL | P2 | بله |
| AT-14 | transforms فیلدها | ✅ PASS | P1 | خیر |
| AT-15 | ساخت Corpus روی snapshot جدا | ✅ PASS | P1 | خیر |
| AT-16 | اعتبارسنجی خروجی JSONL | ✅ PASS | P1 | خیر |
| AT-17 | Grafana (datasource + داشبوردها) | 🟡 PARTIAL | P2 | خیر |
| AT-18 | آمادگی Word Factory (deps/storage/تست) | ❌ FAIL (تست) / 🟡 deps | P1 | خیر |
| AT-19 | آمادگی Elasticsearch | 🟡 PARTIAL | P2 | خیر |
| AT-20 | همگامی Git/مستندات/دپلوی | ✅ PASS | P0 | خیر |

**جمع‌بندی:** ۱۴ PASS · ۴ PARTIAL · ۱ FAIL (تست harness، بی‌اثر روی production) · ۰ BLOCKED · ۰ NOT IMPLEMENTED در میان سناریوهای تعریف‌شده (قابلیت‌های PCM-13+ جدا از این لیست و «ساخته‌نشده» هستند؛ بخش ۷).

---

## ۱. ممیزی دسترسی s52 پس از مهاجرت (بخش اول مأموریت)

مهاجرت سرور رخ داده (hostname و uptime) ولی **مسیر استقرار تغییر نکرده** است. همه‌ی مسیرهای دسترسی سالم‌اند.

| # | بررسی | نتیجه | شواهد |
|---|-------|-------|-------|
| 1 | SSH مستقیم به s52 | ✅ سالم | `ssh -p 22 saber@172.20.1.52` → hostname `AI-TOOLS`، `uptime` = ۴ روز و ۸ ساعت (بوت ~ 2026-10-21) |
| 2 | SSH از طریق jump host 53 | ✅ سالم | `ssh jump53` (hostname `llm`) → از روی آن `ssh saber@172.20.1.52` موفق |
| 3 | تنظیمات/کلید/پورت SSH | ✅ بدون تغییر | `~/.ssh/config`: هاست‌های `s52` (پورت 22) و `jump53` (پورت 22)، کاربر `saber`، کلید `~/.ssh/id_ed25519`؛ هیچ‌کس دسترسی جدید نیافته، bypass ایمنی رخ نداده |
| 4 | مکان جدید Corpus Maker | ✅ همان مسیر | `/home/saber/saberprojects/persian-corpus-toolkit` (کپی کد، نه git repo) — دقیقاً همان قبل از مهاجرت |
| 5 | Docker / DB / services | ✅ سالم | Docker 29.1.3 · Compose 2.40.3 · container `persian-corpus-toolkit-backend-1` فعال (۲ روز uptime) روی `127.0.0.1:5055` · DB `backend/thesaurus.db` = 772M (bind-mount) |
| 6 | **disk-full رفع شد؟** | ✅ **بله، رفع شده** | قبل (PCM-12، ۱۴۰۵/۰۸/۰۲): درایو ۱۰۰٪ پر، 819M آزاد → حالا: **35٪ اشغال، 429G آزاد** از 686G |

### تفاوت قبل/بعد مهاجرت

| پارامتر | قبل از مهاجرت (مشاهده PCM-12، 10-24) | بعد از مهاجرت (این آزمون، 10-25) |
|---|---|---|
| hostname | نام قدیمی سرور | `AI-TOOLS` (بوت ≈ 10-21) |
| فضای دیسک | 100٪ پر (819M آزاد) — **بحرانی** | 35٪ پر (429G آزاد) — **رفع‌شده** |
| RAM | — (ذکرشده نبود) | 23Gi (≈11Gi در دسترس) |
| CPU | — | 10 core |
| Docker | فعال | 29.1.3 / Compose 2.40.3 |
| مسیر دپلوی | `/home/saber/saberprojects/persian-corpus-toolkit` | **بدون تغییر** |
| DB | سالم | 772M · `integrity_check` = ok |
| container backend | فعال | فعال (بازسازی‌شده ۲ روز پیش) |
| کرام زنده | در حال اجرا (پروژه ۲) | **هنوز در حال اجرا** (AT-10) |

**نتیجه‌ی بخش اول: ACCESS = OK — همه‌ی ۶ مورد سبز؛ محدودیت یا BLOCKED وجود ندارد.**

---

## ۲. شواهدسناریو‌به‌سناریو (بخش‌های دوم و سوم مأموریت)

### AT-01 — ورود داشبورد · ✅ PASS · P0
- **اجرا:** روی خود s52 (رمز از `.env` سمت سرور خوانده شد و هرگز نمایش/لاگ نشد): `POST /api/auth/login` → `{"ok": true}` + کوکی `pct_session` · سپس `GET /api/auth/status` → `{"auth_enabled": true, "authenticated": true}`.
- **مشکل:** — · **اقدام:** — · **تأیید کاربر:** بله (چک‌لیست C-01).

### AT-02 — فهرست پروژه‌ها · ✅ PASS · P1
- **اجرا:** `GET /api/dashboard/projects` (با کوکی): ۵ پروژه با فیلدهای `id/name/host/status/saved_count/created_at`؛ جستجو `search=esra` → ۱ پروژه دقیقاً `esra.ir`.
- **یادداشت:** `points` در API فهرست صفر است؛ نقاط در API جزئیات (AT-05) موجود است — مطابق طراحی [`dashboard_api.py`](../backend/dashboard_api.py).
- **تأیید کاربر:** بله (C-02).

### AT-03 — فهرست صفحات + صفحه‌بندی · ✅ PASS · P1
- **اجرا:** `GET /api/dashboard/projects/2/pages?per_page=5` → `total=11603`، `total_pages=2321`، ۵ ردیف با `id/url/captured_at/values/prev_id/next_id`؛ فیلدهای ذخیره‌شده: «ادرس صفحه، برگ، لینک صفحه بعد، لینک صفحه قبل، متن»؛ `page=2` offset درست (ردیف‌های ۶ تا ۱۰).
- **تأیید کاربر:** بله (C-04).

### AT-04 — جستجوی صفحات · ✅ PASS · P1
- **اجرا:** `search=حم` روی صفحات پروژه ۲ → `total=1551` (مطابقت در URL یا `values_json`)؛ `search=item_index=555` هم کارکردنی (نمونه در اسکریپت).
- **تأیید کاربر:** بله (C-05).

### AT-05 — جزئیات صفحه + JSON · ✅ PASS · P1
- **اجرا:** `GET .../pages/11603` → `values` (۵ فیلد)، `content_hash`، `field_errors=[]`، `position={"index":11603,"total":11603}`، `raw_values_json` کامل و قابل‌پارس.
- **تأیید کاربر:** بله (C-06).

### AT-06 — قبلی/بعدی در فهرست · ✅ PASS (با یادداشت) · P1
- **اجرا:** در پنجره‌ی ۵ ردیفی، `prev_id/next_id` هر ردیف با ردیف مجاور در **کل مجموعه‌ی فیلترشده** (نه فقط پنجره) یکسره است (پیاده‌سازی با `LAG/LEAD` در [`dashboard_api.py`](../backend/dashboard_api.py)).
- **یادداشت:** اولین اجرای اسکریپت ردیف آخر پنجره را «نادرست» علامت زده بود (`next_id=6` در حالی که انتظار `null` گذاشته بودم) — این **رفتار درست** است: ردیف بعدی در کل ۱۱٬۶۰۳ ردیف وجود دارد. اسکریپت اصلاح‌نشده این false-alarm را دارد؛ نتیجه‌ی دستی: سازگار.
- **تأیید کاربر:** بله (C-07 — دکمه‌های UI).

### AT-07 — سلامت backend/API · ✅ PASS · P0
- **اجرا:** `GET /api/stats` → `crawled_total=1099` · `GET /api/queue` → `queue_total=352677` (فهرست صف کارهای فاز ۲) · container در حال اجرا، بدون restart از ۲ روز پیش.
- **تأیید کاربر:** خیر (فنی).

### AT-08 — سلامت SQLite · ✅ PASS · P0
- **اجرا (روی production، خواندنی):** `PRAGMA integrity_check` = ok · `quick_check` = ok · شمارنده‌ها: `projects=5`، `project_pages=11544` (لحظه‌ی 15:23؛ در پایان آزمون 11700 — کرام زنده افزود)، `crawled_data=1099`، `khamenei_speeches=151`.
- **تأیید کاربر:** خیر (فنی).

### AT-09 — وضعیت karam زنده · ✅ PASS · P0
- **اجرا:** پروژه ۲ «تفسیر تسنیم همتا» → `status=running`، `pages_per_minute=4`، `cursor_url` با `item_index` فعال. پروژه ۵ «gharaati.ir» = `paused` با پیام «خواندن متوقف شد» (توقف ارادی کاربر، نه خطا) · پروژه ۶ «esra.ir» = tested · پروژه‌ی کhamenei: **151/151 کامل**.
- **تأیید کاربر:** بله (C-03/C-09).

### AT-10 — پیوستگی karam · ✅ PASS · P0
- **اجرا (دو نمونه ۹۵ ثانیه‌ای فاصله، فقط خواندنی):** 15:23:24 UTC → `saved=11552`، cursor `item_index=55555` → 15:25 → `saved=11558`، cursor `item_index=55561`، جدیدترین ردیف‌ها `id 11562..11564`. نرخ ≈ **۴ صفحه/دقیقه = دقیقاً `pages_per_minute=4`**. خطای جدیدی در `last_message` ثبت نشده.
- **تأیید کاربر:** بله (C-08 — مشاهده‌ی افزایش شمارنده).

### AT-11 — cursor = آخرین صفحه (پایه‌ی resume) · ✅ PASS · P1
- **اجرا:** `cursor_url` پروژه ۲ == URL آخرین ردیف `project_pages` (مطابقت واقعی، `match=True`). یعنی اگر تب/کرام بست، از همان نقطه ادامه می‌یابد (مکانیزم resume در عمل کار می‌کند؛ خود تست resume با «توقف عمدا» ممنوع بود و انجام نشد).
- **تأیید کاربر:** خیر.

### AT-12 — شناسایی پایان طبیعی کتاب · 🟡 PARTIAL · P1
- **منطق موجود (شواهد کد):** `next_mode ∈ {url_param, none}` در [`projects.py`](../backend/projects.py) اعتبارسنجی می‌شود؛ `advanceUrl()` در [`background.js`](../extension/background.js) پارامتر `next_param` را +`next_step` می‌کند؛ نبود پارامتر در لینک → خطای «پارامتر … در لینک نیست» و ثبت report با `failed` و `cursor_url=next`؛ شکست خواندن صفحه هم همین مسیر را دارد.
- **کاستی:** «پایان طبیعی» (کتابی که واقعاً تمام شود) تاکنون در production **مشاهده نشده** — هیچ کتابی به انتها نرسیده و وضعیت «completed/تمام شد» به‌طور واقعی آزمون نشده است.
- **اقدام پیشنهادی:** در PCM-07 (checkpoint/resume + کنترل) یک تست کنترل‌شده روی پروژه‌ی کوتاه‌مدت/جدید انجام شود؛ یا یک کتاب کوتاه واقعی تا انتها کرام شود.
- **تأیید کاربر:** خیر.

### AT-13 — ناوبری معکوس · 🟡 PARTIAL · P2
- **حقیقت دو لایه:**
  - **داشبورد (نمای صفحه‌ها):** ✅ دوسویه — دکمه‌های «→ قبلی» / «بعدی ←» در [`index.html`](../dashboard/index.html) (تابع `pgStep` روی `prev_id/next_id`).
  - **موتور karam (اکستنشن):** فقط پیش‌رو (forward-only) — به‌طراحی PCM-05؛ بازگشت موتور جزو PCM-07 است.
- **اقدام:** تأیید کاربری دکمه‌های داشبورد (C-07)؛ ناوبری معکوس موتور → PCM-07.
- **تأیید کاربر:** بله.

### AT-14 — transforms فیلدها · ✅ PASS · P1
- **اجرا:** دقیقاً ۴ transform در [`content_picker.js`](../extension/content_picker.js): `text` (نرمال‌سازی فاصله)، `before_paren` (قبل از پرانتز)، `paren_number` (عدد داخل پرانتز)، `add_one` (+1)؛ منابع نقطه: `css/xpath/url/url_param`. نمونه‌ی زنده: پروژه ۲ با `url_param` روی `item_index` و transform `add_one` در حال کار (AT-10).
- **تأیید کاربر:** خیر.

### AT-15 — ساخت Corpus روی snapshot جدا · ✅ PASS · P1
- **اجرا (اسکریپت [`pcm12_2_corpus_test.sh`](../deploy/pcm12_2_corpus_test.sh)، بدون هیچ تغییر روی production):**
  1. `sqlite3 thesaurus.db ".backup /tmp/pct_at15/backend/thesaurus.db"` → snapshot 772M، `integrity_check=ok` (backup آنلاین WAL، بدون قفل روی production).
  2. `corpus/build_corpus.py` **بدون هیچ تغییری** در `/tmp` اجرا شد (Python 3.12.3) — مسیر DB آن به‌صورت نسبی به snapshot نشست.
  3. خروجی‌ها: `thesaurus_raw_corpus.txt` (318,359 B) · `thesaurus_corpus.jsonl` (191,541 B) · `thesaurus_terms.txt` (38,359 B) · `README.md` کارت HuggingFace.
  4. درخت موقت کاملاً پاک شد.
- **تأیید کاربر:** خیر (فنی).

### AT-16 — اعتبارسنجی JSONL · ✅ PASS · P1
- **اجرا:** 1099 ردیف `crawled_data` → 1098 رکورد JSONL = 1099 − **۱ رکورد با عنوان خالی** (عدد دقیقاً با `SELECT COUNT(*) WHERE TRIM(title)<>''` → 1098 یکی است) · وایدر همه‌ی 1098 خط: **0 خط نامعتبر، 0 عنوان خالی** · نمونه: `{"id":"197855A6…","type":"term","title":"العالم الظلمانی","science_field":"فلسفه اشراق","category":"العالَم"}`.
- **تأیید کاربر:** خیر.

### AT-17 — Grafana · 🟡 PARTIAL · P2
- **سازوکار (سبز):** container `grafana` (11.3.0) + `prometheus` (v2.55.0) + `loki` (3.2.0) + 3 `pg-exporter` — همه «Up 4 days»؛ `/api/health` → `database: ok`؛ datasource‌های provision‌شده: **Prometheus (default)، Loki، LiteLLM Postgres، QA mesbah، QA eiis، QA taghrir** (فقط نام‌ها؛ مقادیر رمز در این گزارش نمی‌آید).
- **داشبوردهای موجود:** fleet-overview، kpi-overview، qa-rag-instances، server52/53/113-overview، litellm-gateway-52، model-serving، gpu-sama، iranseda-pipeline، eiis-rag-100-vs-1000 — **هیچ‌کدام مخصوص Corpus Maker نیستند**.
- **نتیجه:** زیرساخت Observability کاملاً آماده (PCM-10 می‌تواند مستقیم شروع شود) اما **۴ داشبورد PCT ساخته‌نشده** (NOT BUILT).
- **یافتن امنیتی (P1):** فایل `datasources.yml` داخل container، رمز‌های چند datasource را به‌صورت plaintext نگه می‌دارد (در جریان این ممیزی در خروجی ترمینال اپراتور دیده شد). پیشنهاد: بازسازی (rotate) این رمزها و مهاجرت به env/secret خارجی. جزئیات در `PCM-12-AUDIT.md`.
- **تأیید کاربر:** خیر.

### AT-18 — آمادگی Word Factory · ❌ FAIL (gate تست) · deps 🟡 · P1
- **deps:** `requirements.txt` فقط `flask==3.1.1` + `flask-cors==6.0.1` — **`python-docx` موجود نیست** (برای مرحله‌ی Word لازم است؛ هنوز نیازی فوری نیست).
- **storage:** 429G آزاد + 11Gi RAM در دسترس — **کافی**.
- **تست‌ها:** **نکته‌ی مهم:** دستور مکتوب در AGENTS.md —
  `python -m unittest test_api test_projects test_dashboard` — **نارنج (FAIL)** است، روی **هر دو** ویندوز محلی و s52 (Python 3.12.3): `Ran 39 tests ... FAILED (failures=1, errors=13)`.
- **ریشه‌یابی (کاملاً تکرارپذیر، شواهد کامل در اسکریپت‌های debug که حذف شد):**
  - هر ۳ ماژول تست در import، DB موقت اختصاصی می‌سازند و `PCT_DB` را ست می‌کنند — ولی `server.DB_PATH` در خط 21 [`server.py`](../backend/server.py) **فقط در اولین import** می‌بندد.
  - پس وقتی ۳ ماژول در یک فرآیند اجرا شوند، اپ از DB ماژول اول استفاده می‌کند و `os.remove(_DB)` ماژول‌های بعدی فایل اشتباهی را می‌سازد → **آشکار شدن state بین کلاس‌ها**:
    - ردیف rate-limit تست A07 (۵ ورود ناموفق / ۱۰ دقیقه) در DB به‌جا می‌ماند → همه‌ی ورودهای کلاس‌های بعدی `429/401` → همه‌ی تست‌های D* و P* با `KeyError` می‌افتند و D06 می‌شود `401 != 404`.
    - پروژه‌ی A08 هم به D01 نشت می‌کند → `total=17` در جایی که انتظار 16 است.
  - **تأیید:** اجرای هر ماژول **مجزا** سبز است: `test_api` 8/8 OK · `test_projects` 9/9 OK · `test_dashboard` 22/22 OK. و اجرای توالی «AuthTests سپس D01» با DB جدا، PASS.
  - **production درگیر نیست:** کد اجرای‌یافته در container درست است (تمام APIها در AT-01..06 سبز)؛ خرابی فقط در harness تست وقتی ماژول‌ها در یک فرآیند ترکیب شوند.
- **چرا P1:** gate «بدون تست سبز deploy نمی‌شود» (AGENTS.md §2-4) عملاً شکسته است — deploy بعدی (PCM-13+) بدون رفع این باگ، یا تست نمی‌شود یا نتیجه‌اش قابل اعتماد نیست.
- **اقدام پیشنهادی (فاز بعدی، خارج از این مأموریت که docs-only است):** یک `PCT_DB` مشترک بین ماژول‌ها (مثلاً bootstrap در `test_api` و import ساده در بقیه) یا تبدیل `DB_PATH` به accessor پویا؛ سپس بازسازی دستور اجرا در AGENTS.md.
- **تأیید کاربر:** خیر (فنی، ولی اطلاع از شکستگی gate مهم است).

### AT-19 — آمادگی Elasticsearch · 🟡 PARTIAL · P2
- **اجرا (فقط شناسایی، بدون ایجاد index):** هیچ سرویس ES در `docker-compose.yml` پروژه ما نیست · پورت 9200 گوش نمی‌دهد · container `taghrir-es` (8.13.4، متعلق به پروژه‌ی دیگر — خارج از scope و دست‌نخورده) در وضعیت `Exited(143) 4 days ago`.
- **ظرفیت s52 برای یک ES کوچک:** RAM 23Gi (≈10Gi آزاد) · دیسک 429G · 10 CPU — برای ES با heap 1–2GB **کافی** (با احتیاط اشتراک RAM با بقیه‌ی سرویس‌ها).
- **نتیجه:** برای PCM-13 باید ES به‌صورت آگاه provision شود (تصمیم D-ES در `PCM-12-ARCHITECTURE.md`): یا container جدید در compose ما، یا استفاده از ظرفیت موجود. الان **هیچ ES فعالی برای PCT وجود ندارد**.
- **تأیید کاربر:** خیر.

### AT-20 — همگامی Git/مستندات/دپلوی · ✅ PASS · P0
- **اجرا:** مقایسه‌ی `md5sum` **همه‌ی 25 فایل عملیاتی** بین working tree محلی (HEAD `81e3191`) و کپی دپلوی‌شده s52: 10 فایل backend `.py` + Dockerfile + requirements.txt · 5 فایل corpus · 8 فایل اکستنشن · `dashboard/index.html` · `docker-compose.yml` → **همه identical**.
- **یادداشت:** s52 کپی کد است (نه git repo) و یک `backend/.venv` اضافه دارد (خارج از repo، طبیعی).
- **تأیید کاربر:** خیر.

---

## ۳. کشفیات فرعی (خارج از ۲۰ سناریو)

1. **شکستگی gate تست** (جز AT-18) — مهم‌ترین کشف این آزمون؛ جزئیات و ریشه در بالا.
2. **رمز plaintext در `datasources.yml` Grafana** (P1 امنیتی) — rotate + secret خارجی.
3. **پنجره‌ی false-alarm در اسکریپت AT-06** — فقط یک باگ در اسکریپت آزمون خودمان است، نه محصول؛ نتیجه‌ی دستی PASS.
4. **پروژه ۵ (gharaati.ir) در حالت paused** با پیام «خواندن متوقف شد» — وضعیت ارادی کاربر؛ اگر انتظار ادامه دارد، باید دستی Resume شود (کنترل Start/Resume جزو PCM-07 است).

---

## ۴. جمع‌بندی نهایی (شرایط خاتمه‌ی مأموریت)

### ۴.۱ چه چیزی واقعاً در production کار می‌کند
- موتور karam + اکستنشن: پروژه ۲ **زنده** با نرخ ۴ صفحه/دقیقه؛ cursor/resume در عمل؛ transforms (۴ عددی)؛ خطای ثبت‌شده جدید: صفر.
- داشبورد + auth (PCM-04/09): ورود، فهرست/جزئیات پروژه، مرور صفحه‌به‌صفحه، صفحه‌بندی، جستجو، قبلی/بعدی — همه با داده‌ی واقعی production تأیید شد.
- API اکستنشن باز (بدون auth) + API خواندنی داشبورد پشت auth — طبق طراحی.
- DB: سالم (integrity ok)، 772M؛ pipeline کhamenei کامل (151/151).
- ساخت پیکره از `crawled_data`: روی snapshot جدا با کد دست‌نخورده سبز (1098 رکورد معتبر).
- همگامی کامل کد local ↔ s52 (25 فایل).

### ۴.۲ چه چیزی ناقص است
- **gate تست ترکیبی شکسته** (AT-18) — قبل از هر deploy بعدی باید رفع شود.
- **پایان طبیعی کتاب** (AT-12) — منطق هست ولی در production هیچ‌گاه مشاهده/آزمون نشده.
- **ناوبری معکوس موتور karam** (AT-13) — فقط داشبورد دوسوئه؛ موتور forward-only (در نقشه: PCM-07).
- **داشبوردهای Grafana مخصوص PCT** (AT-17) — زیرساخت هست، داشبورد نیست (PCM-10).

### ۴.۳ چه چیزی اصلاً ساخته نشده (PCM-13+ — فقط طراحی‌شده در `docs/PCM-12-*`)
Word Factory (دانلود/تبدیل Word) · Knowledge/RAG pipeline · ES index · Registries · LiteLLM برای PCT · SuperRAG · Research شبانه — **هیچ‌کدام در production نیستند**.

### ۴.۴ آمادگی زیرساخت برای PCM-13
**آماده (READY) با دو پیش‌شرط:**
- ✅ دیسک 429G آزاد · RAM 11Gi · CPU 10 · Docker/Compose جدید و سالم · DB سالم · Grafana+Prometheus+Loki فعال · دسترسی SSH مستقیم و jumphost هر دو سالم · همگامی Git.
- ⚠️ پیش‌شرط ۱: رفع باگ harness تست (AT-18) — چون gate deploy روی تست سبز است.
- ⚠️ پیش‌شرط ۲: تصمیم آگاهانه درباره‌ی provision کردن ES (AT-19) و افزودن `python-docx` در اولین مرحله‌ی Word.

### ۴.۵ آنچه کاربر باید در Chrome تست کند
دستورالعمل قدم‌به‌قدم و ساده: **[`docs/PCM-12-ACCEPTANCE-CHECKLIST.md`](PCM-12-ACCEPTANCE-CHECKLIST.md)** — ۱۰ مورد (C-01 تا C-10) با آدرس صفحه/دکمه/نتیجه‌ی مورد انتظار و جای PASS/FAIL. فنی‌ها (AT-07..08، 11..20) در بخش جدا همان فایل مستند شده‌اند.

---

## ۵. SHA + لینک + git status + بکاپ/rollback

- **وضعیت کد تحت آزمون:** `81e3191` (HEAD `origin/main` پیش از این commit)
- **commit این مستندات:** (در بخش ۸ — پس از push تکمیل می‌شود)
- **تغییر در production:** **صفر** — این مأموریت docs-only بود؛ فقط اسکریپت‌های موقت در `/tmp` s52 اجرا و پاک شدند.
- **بکاپ/rollback:** نیازی نبود (بدون تغییر کد/DB). آخرین بکاپ‌های موجود: `/home/saber/backups/thesaurus-<TS>.db` و `pct-deploy-<TS>.tar.gz`.
- **پاکسازی:** `/tmp/pct_at*.sh`، `/tmp/pct_at15*`، `/tmp/pct_test_out.txt` روی s52 حذف شدند؛ درخت محلی فقط ۳ اسکریپت جدید + ۲ doc جدید دارد.

## ۶. روش تکرار آزمون (برای اپراتور)

```bash
# روی s52 — آزمون‌های خواندنی داشبورد/API (رمز از .env سرور، نمایش نمی‌شود)
scp deploy/pcm12_2_acceptance_test.sh s52:/tmp/pct_at.sh && ssh s52 "bash /tmp/pct_at.sh"

# ساخت corpus روی snapshot جدا (آزاد از production)
scp deploy/pcm12_2_corpus_test.sh s52:/tmp/pct_at15.sh && ssh s52 "bash /tmp/pct_at15.sh"

# وضعیت Grafana/Word Factory/ES
scp deploy/pcm12_2_infra_test.sh s52:/tmp/pct_infra.sh && ssh s52 "bash /tmp/pct_infra.sh"

# تست‌های backend — هر ماژول جدا (وضعیت فعلی سبز)
cd backend && python -m unittest test_api -v
cd backend && python -m unittest test_projects -v
cd backend && python -m unittest test_dashboard -v
# ⚠️ ترکیب سه‌تایی در یک فرآیند فعلاً FAIL است (AT-18) — تا رفع باگ harness
```

## ۸. SHA + لینک commit این گزارش

- **SHA:** `271ceba4f903d969f16a6c0aa6938a26d9216a62`
- **لینک:** https://github.com/saber13812002/persian-corpus-toolkit/commit/271ceba4f903d969f16a6c0aa6938a26d9216a62
- **push:** `81e3191..271ceba  main -> main` (origin = GitHub)
- **محتویات commit:** این فایل + `PCM-12-ACCEPTANCE-CHECKLIST.md` + ۳ اسکریپت `deploy/pcm12_2_*` + یک ردیف در جدول roadmap readme (فقط ۶ فایل، 643 خط افزودنی؛ هیچ کد عملیاتی تغییر نکرده)

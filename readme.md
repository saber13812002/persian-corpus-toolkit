# 📚 Persian Corpus Toolkit (پیکره‌ساز فارسی)

ابزار کراول، دیتابیس و پیکره‌سازی برای سایت‌های علمی و محتوایی فارسی — با اکستنشن کروم (Manifest V3)، بکند Flask/SQLite و پایپلاین پیکره.

**Production:** https://corpus.ai.ismc.ir · **Repository:** https://github.com/saber13812002/persian-corpus-toolkit

---

## 🎯 امکانات

| # | قابلیت | وضعیت |
|---|--------|--------|
| 1 | اصطلاح‌نامه `thesaurus.eiis.iki.ac.ir` (فاز۱ لیست + فاز۲ تعاریف کامل) | ✅ فعال |
| 2 | بیانات `farsi.khamenei.ir/speech` (متن/عنوان/تاریخ جلالی/صوت/فیلم) | ✅ فعال |
| 3 | **سیستم پروژه** (v3.5): پروژه برای هر دامنه، نقطه‌های استخراج، کراول قطعه‌قطعه با resume | ✅ فعال (تست واقعی Chrome باقی‌مانده) |
| 4 | سایت‌های نام‌دار با فیلدهای آماده (`tasnim.hamtaa.org` seed شده) | ✅ فعال |
| 5 | داشبورد آنلاین `corpus.ai.ismc.ir/dashboard` (تب «پروژه‌ها» + صفحه‌بندی + جزئیات + احراز هویت رمز) | ✅ فعال (PCM-04/09) |
| 6 | پایپلاین پیکره + دیتaset + آپلود HuggingFace | ✅ در دسترس |
| 7 | ایندکسر RAG | 🚧 در دست توسعه |

### سیستم پروژه (هسته v3.5)

به‌جای «کراول یکسره»، یک **پروژه** (یک کتاب/سایت) تعریف می‌شود:

1. در Popup: نام پروژه + دامنه (خودکار از تب فعال) → «ساختن از این صفحه»
2. «انتخاب و ویرایش» → پنل روی صفحه → کلیک روی المنت‌ها = تعریف **نقطه** (tag + selector + transform)
3. «آزمایش و شروع» → حلقه خواندن: هر دقیقه N صفحه (N=1..12) با `chrome.alarms`
4. هر صفحه با **SHA-256** dedup می‌شود؛ شمارنده‌های saved/skipped/failed تجمعی‌اند
5. **Resume:** موقعیت خواندن در `cursor_url` ذخیره می‌شود — بعد از هر قطعی (بستن کروم، refresh، 2 صفحه خالی) از آخرین کراول ادامه می‌یابد
6. Pause خودکار بعد از 2 صفحه خالی پشت‌سرهم؛ resume با شروع مجدد

---

## 🏗 معماری

```
┌────────────────────────────────────────────────────────┐
│  Chrome Extension (Manifest V3)                        │
│  • popup.js/popup.html  — UI پروژه و آمار             │
│  • content_picker.js    — پنل روی صفحه: انتخاب نقطه   │
│  • background.js        — حلقه خواندن دقیقه‌ای (alarm)  │
│  • content_thesaurus.js / content_khamenei.js          │
├────────────────────────────────────────────────────────┤
│  Flask Backend (پورت ۵۰۵۵، SQLite WAL)                │
│  • server.py      — API اصلی + فاز۱/۲ + harvest      │
│  • projects.py    — پروژه/نقطه/صفحه/گزارش ★          │
│  • auth.py        — احراز هویت داشبورد (scrypt+cookie) │
│  • dashboard_api.py — API خواندنی داشبورد ★           │
│  • sites.py       — سایت‌های نام‌دار + فیلدها ★      │
│  • sciences.py    — ۱۳ علم اصطلاح‌نامه               │
│  • 3 test files (api/projects/dashboard) — 32 تست     │
├────────────────────────────────────────────────────────┤
│  Corpus Pipeline (corpus/)                             │
│  • build_corpus.py / build_dataset.py / pipeline.py    │
│  • upload_to_hf.py — آپلود به 🤗 HuggingFace          │
├────────────────────────────────────────────────────────┤
│  RAG Indexer (در دست توسعه)                           │
│  • Embedding با GPU، تخمین زمان، resume، anti-ban      │
└────────────────────────────────────────────────────────┘
```

### ساختار پروژه

```
persian-corpus-toolkit/
├── backend/
│   ├── server.py            # API اصلی (فاز۱/۲، harvest، khamenei)
│   ├── projects.py          # ★ سیستم پروژه (v3.5)
│   ├── auth.py              # ★ احراز هویت داشبورد (PCM-09)
│   ├── dashboard_api.py     # ★ API خواندنی داشبورد (PCM-04)
│   ├── sites.py             # ★ سایت‌ها و فیلدهای آماده
│   ├── sciences.py          # ۱۳ علم
│   ├── test_api.py          # ۸ تست
│   ├── test_projects.py     # ۹ تست جریان پروژه
│   ├── test_dashboard.py    # ۱۵ تست (auth A01-A08 + داشبورد D01-D07)
│   ├── requirements.txt
│   ├── Dockerfile
│   └── thesaurus.db         # (gitignored)
├── extension/
│   ├── manifest.json        # v3.5
│   ├── popup.html / popup.js
│   ├── background.js        # service worker + حلقه minute-loop
│   ├── content_picker.js    # ★ پنل انتخاب نقطه روی صفحه
│   ├── content_thesaurus.js / content_khamenei.js
│   ├── shared.js
│   ├── test_popup.js        # ۸ تست UI (node)
│   └── icons/
├── corpus/                  # پایپلاین پیکره و دیتاست
├── dashboard/               # داشبورد (تب‌های اصلی + «پروژه‌ها» + overlay ورود)
├── deploy/                  # nginx vhost + systemd + اسکریپت‌های دپلوی PCM
├── docs/                    # project-dashboard.md · dashboard-authentication.md
├── docker-compose.yml       # backend محلی روی 127.0.0.1:5055
├── AGENTS.md                # قواعد سخت دپلوی/مهاجرت/رمز
└── گزارش-وضعیت-پروژه.md / گزارش-PCM-0X.md
```

---

## 🚀 نصب و راه‌اندازی

### پیش‌نیازها
- Python 3.10+ (تست‌شده روی 3.12/3.14)
- Google Chrome (برای اکستنشن)
- Git

### 1. دریافت

```bash
git clone https://github.com/saber13812002/persian-corpus-toolkit.git
cd persian-corpus-toolkit
```

### 2. بکند (دو روش)

```bash
# روش A — مستقیم
cd backend
pip install -r requirements.txt
python server.py            # ← http://127.0.0.1:5055

# روش B — Docker (مطابق Production)
docker compose up -d --build
```

### 3. اکستنشن کروم

1. `chrome://extensions` ← **Developer mode** روشن
2. **Load unpacked** ← پوشه `extension/`
3. صفحه سایت هدف را باز کن و روی آیکون اکستنشن کلیک کن
4. برای سیستم پروژه: نام پروژه بنویس ← «ساختن از این صفحه» ← «انتخاب و ویرایش» (پنل روی صفحه) ← «آزمایش و شروع»

> برای تست محلی، ثابت `BACKEND` در `popup.js`، `background.js` و `content_picker.js` را به `http://127.0.0.1:5055` تغییر بده. در حالت Production همه‌جا `https://corpus.ai.ismc.ir` است.

### 4. ساخت پیکره

```bash
cd corpus
python pipeline.py          # خروجی در corpus/output/
python upload_to_hf.py --token hf_... --username ...
```

---

## 📊 API Endpoints (پورت 5055)

### سیستم پروژه (v3.5)

| Endpoint | Method | توضیح |
|---|---|---|
| `/api/projects?host=…` | GET | فهرست پروژه‌ها (فیلتر بر اساس دامنه) |
| `/api/projects` | POST | ساخت پروژه `{name, host, start_url, next_mode, next_param, next_step, pages_per_minute}` |
| `/api/projects/<id>` | GET/POST | مشاهده / ویرایش |
| `/api/projects/<id>/points` | POST/DELETE | تعریف/ویرایش/اعاده‌نام/حذف نقطه |
| `/api/projects/<id>/pages` | POST | ذخیره صفحه `{url, values}` — dedup با SHA-256 |
| `/api/projects/<id>/report` | POST | گزارش اجرا `{saved, skipped, failed, cursor_url, status}` |

### داشبورد (PCM-04/09 — 🔒 نیاز به ورود)

| Endpoint | Method | توضیح |
|---|---|---|
| `/api/auth/login` | POST | ورود `{password}` → cookie `pct_session` (HttpOnly/Secure/SameSite=Lax) |
| `/api/auth/logout` | POST | باطل‌کردن session |
| `/api/auth/status` | GET | `{auth_enabled, authenticated}` |
| `/api/dashboard/projects` | GET | فهرست پروژه‌ها — جستجو/فیلتر/status/مرتب‌سازی/صفحه‌بندی سمت سرور |
| `/api/dashboard/projects/<id>` | GET | جزئیات: فیلدها، pages_summary، values_sample آخرین صفحه |

سند کامل: [docs/project-dashboard.md](docs/project-dashboard.md) و [docs/dashboard-authentication.md](docs/dashboard-authentication.md)

### سایت‌ها

| Endpoint | Method | توضیح |
|---|---|---|
| `/api/sites` | GET | فهرست سایت‌های نام‌دار + فیلدها |
| `/api/sites/match?host=…` | GET | فیلدهای آماده یک سایت |
| `/api/captures` | POST | ذخیره و dedup صفحات عمومی |

### فازهای کلاسیک

| Endpoint | Method | توضیح |
|---|---|---|
| `/api/phase1/seed-batch`, `/api/phase2/next-batch`, `/api/phase2/complete` | POST | فاز۱/۲ اصطلاح‌نامه |
| `/api/thesaurus/elastic-harvest(+status)` | GET/POST | harvest سمت سرور (async + resume) |
| `/api/khamenei/*` | — | seed/submit/reset/stats/pending |
| `/api/stats`, `/api/pipeline/status`, `/api/queue` | GET | آمار |

---

## 🗄️ دیتابیس

`backend/thesaurus.db` (SQLite، WAL mode، gitignored)

| جدول | توضیح |
|---|---|
| `crawl_queue`, `crawled_data` | صف و داده‌های کلاسیک (content hash) |
| `projects` | ★ پروژه‌ها + `cursor_url` (نقطه resume) + شمارنده‌ها |
| `project_points` | ★ نقطه‌های استخراج (tag + source + selector + transform) |
| `project_pages` | ★ صفحات ذخیره‌شده (values_json + SHA-256) |
| `sites`, `site_fields` | سایت‌های نام‌دار و فیلدهای آماده |
| `captures` | captures عمومی |
| `auth_meta`, `auth_sessions`, `auth_rate` | ★ احراز هویت داشبورد (scrypt-hash، sessionهای ۷روزه، rate-limit) |

جدول‌های جدید **خودکار** و **additive** ساخته می‌شوند (migration امن برای DBهای قدیمی).

### بک‌آپ و بازیابی

```bash
sqlite3 backend/thesaurus.db ".backup backups/thesaurus_$(date +%Y%m%d_%H%M%S).db"
sqlite3 backups/thesaurus_xxx.db "PRAGMA integrity_check;"   # تأیید: ok
cp backups/thesaurus_20260802.db backend/thesaurus.db       # بازیابی
```

### Upsert هوشمند

با **content hash** (SHA-256): آیتم جدید → INSERT · تکراری با همین محتوا → SKIP · تکراری با محتوا تغییرکرده → UPDATE (version+1).

---

## 🧪 تست‌ها

```bash
cd backend && python -m unittest test_api test_projects test_dashboard -v   # 32/32
cd extension && node test_popup.js                            # 8/8
node --check extension/popup.js extension/background.js extension/content_picker.js
node -e "JSON.parse(require('fs').readFileSync('extension/manifest.json'))"
```

قبل از هر commit، هر دو مجموعه تست باید سبز باشند.

---

## 🏭 استقرار Production (corpus.ai.ismc.ir)

حقیقت‌های تأییدشده سرور (ممیزی PCM-03 — ۱۴۰۵/۰۸/۰۲):

| مورد | مقدار |
|---|---|
| سرور | `s52` (`172.20.1.52`) — SSH واقعی روی **پورت 22** (`ssh saber@172.20.1.52`) |
| ⚠️ پورت 2222 | **GitLab CE** است (کانتینر `gitlab` با map 2222→22)، **نه** SSH هاست — در `~/.ssh/config` برای SSH استفاده نشود |
| مسیر استقرار | `/home/saber/saberprojects/persian-corpus-toolkit` (کپی کد؛ **نه** git repo — کد از `origin/main` منتقل می‌شود) |
| Compose / کانتینر | سرویس `backend` فقط؛ کانتینر `persian-corpus-toolkit-backend-1`؛ image `persian-corpus-toolkit-backend` |
| پورت | `127.0.0.1:5055` (nginx `corpus.ai.ismc.ir` جلوی آن است) |
| DB | bind-mount: `./backend/thesaurus.db → /data/thesaurus.db` (SQLite WAL — فایل پایدار، نه volume نام‌دار) |

**داشبورد + احراز هویت (PCM-04/09 — از ۱۴۰۵/۰۸/۰۱):**
- داشبورد: `https://corpus.ai.ismc.ir/dashboard/` — tab «📁 پروژه‌ها» (فهرست + صفحه‌بندی + جزئیات)
- ورود: `POST /api/auth/login` با رمز؛ cookie `pct_session` (HttpOnly/Secure/SameSite=Lax)
- رمز: **فقط** در `.env` سرور (gitignored، chmod 600) — در DB به‌صورت scrypt-hash؛ هرگز در کد/Git/لاگ
- APIهای نوشتاری اکستنشن (`/api/projects*`) **باز می‌مانند** → کراول زنده هرگز با ورود داشبورد قطع نمی‌شود
- اگر رمزی seed نشده باشد (محیط توسعه)، APIهای داشبورد بدون ورود باز می‌مانند

**روند به‌روزرسانی (تأییدشده در PCM-03/04):**
1. بکاپ: `deploy/pcm04_deploy.sh` → `/home/saber/backups/thesaurus-<TS>.db` + `PRAGMA integrity_check`
2. سشن‌شات کد: tar کل پوشه استقرار (به‌جز DB) → `/home/saber/backups/pct-deploy-<TS>.tar.gz`
3. تضمین `.env` (رمز داشبورد، chmod 600) — فقط در سرور، هرگز در Git
4. انتقال کد `origin/main` به پوشه استقرار (DB در tar نباشد)
5. `docker compose build backend && docker compose up -d backend` — **فقط recreate backend؛ بدون `down`**
6. smoke test: health + auth (401 بدون cookie / 200 با cookie) + API اکستنشن باز + integrity_check

**قوانین:**
- ⛔ `docker-compose down` ممنوع — فقط `up -d backend` (recreate)
- ⛔ حذف هرگز: فایل `thesaurus.db`، volumeها، یا هر سرویس نامرتبط (سرور 40+ کانتینر دیگر دارد)
- همیشه **قبل** از هر استقرار: بکاپ SQLite + `integrity_check`
- Rollback: extract سشن‌شات کد + `docker compose build backend && up -d backend`؛ بازیابی DB از `/home/saber/backups/`
- اسکیمای `projects` **additive** است (جدول جدید، دست‌نخورده روی جداول قدیمی)

جزئیات کامل ممیزی، بکاپ‌ها و rollback: [گزارش-PCM-03.md](گزارش-PCM-03.md) بخش ۳–۴ · برنامه اولیه: [گزارش-PCM-02.md](گزارش-PCM-02.md) بخش ۳

---

## 🛠️ راهنمای توسعه‌دهنده

### افزودن سایت/دامنه جدید
- سایت «نام‌دار»: در `backend/sites.py` رکورد + فیلدهای پیش‌فرض + تست در `test_api.py`
- سایت دلخواهی: بدون کد — از popup ساخته می‌شود و نقطه‌ها در پنل تعریف می‌شوند
- transform جدید: در `content_picker.js` (استخراج) + `projects.py` (معتبرسازی) + تست

### رفع مشکل CORS
در `server.py` از `flask-cors` استفاده شده (origins باز برای `chrome-extension://*`).

### Debug
```bash
python server.py                          # لاگ بکند در stdout
# اکستنشن: F12 → Console → filter: [Crawler]
# کنسول popup: راست‌کلیک روی popup → Inspect → تب Network
sqlite3 backend/thesaurus.db "SELECT COUNT(*) FROM project_pages"
```

### وضعیت‌های باز (backlog)
- رفع `sleep` ثابت و `waitComplete` در `background.js` (B1/B2 گزارش PCM-01)
- `corpus/build_project_corpus.py` (خروجی پروژه به txt/jsonl)
- RAG indexer · CI (unittest + lint) · یکپارچه‌سازی ثابت `BACKEND` در `shared.js`

جزئیات بیشتر: [گزارش-وضعیت-پروژه.md](گزارش-وضعیت-پروژه.md) و [گزارش-PCM-02.md](گزارش-PCM-02.md)

---

## 📝 License

CC BY-NC-SA 4.0 — استفاده پژوهشی و آموزشی

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
| 5 | داشبورد آنلاین `corpus.ai.ismc.ir/dashboard` | ✅ فعال |
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
│  • sites.py       — سایت‌های نام‌دار + فیلدها ★      │
│  • sciences.py    — ۱۳ علم اصطلاح‌نامه               │
│  • test_api.py + test_projects.py — 17 تست            │
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
│   ├── sites.py             # ★ سایت‌ها و فیلدهای آماده
│   ├── sciences.py          # ۱۳ علم
│   ├── test_api.py          # ۷ تست
│   ├── test_projects.py     # ۱۰ تست جریان پروژه
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
├── dashboard/               # داشبورد استاتیک
├── deploy/                  # nginx vhost + systemd
├── docker-compose.yml       # backend محلی روی 127.0.0.1:5055
└── گزارش-وضعیت-پروژه.md / گزارش-PCM-02.md
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
cd backend && python -m unittest test_api test_projects -v   # 17/17
cd extension && node test_popup.js                            # 8/8
node --check extension/popup.js extension/background.js extension/content_picker.js
node -e "JSON.parse(require('fs').readFileSync('extension/manifest.json'))"
```

قبل از هر commit، هر دو مجموعه تست باید سبز باشند.

---

## 🏭 استقرار Production (corpus.ai.ismc.ir)

- سرور `s52` — Docker Compose؛ فقط سرویس `backend`؛ DB در volume (فایل SQLite پایدار)
- به‌روزرسانی: `git pull && docker compose build backend && docker compose up -d backend`
- **قوانین:**
  - ⛔ `docker-compose down` ممنوع
  - ⛔ بدون تأیید صریح کاربر، هیچ تغییر روی Production
  - همیشه **قبل** از هر استقرار: بکاپ SQLite با `sqlite3 .backup` + `PRAGMA integrity_check`
  - Rollback: تصویر قبلی باقی می‌ماند؛ اسکیمای جدید additive است
- برنامه کامل در [گزارش-PCM-02.md](گزارش-PCM-02.md) بخش ۳

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

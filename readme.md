# 📚 Persian Corpus Toolkit (پیکره‌ساز فارسی)

ابزار جامع کراول، دیتابیس و پیکره‌سازی برای سایت‌های علمی و محتوایی فارسی

## 🎯 پشتیبانی از سایت‌ها

| # | سایت | وضعیت | نوع محتوا |
|---|------|--------|-----------|
| 1 | `thesaurus.eiis.iki.ac.ir` | ✅ کامل | اصطلاح‌نامه علوم عقلی اسلامی |
| 2 | `farsi.khamenei.ir/speech` | 🚧 در حال توسعه | بیانات و سخنرانی‌ها |

## 🏗 معماری کلی

```
┌──────────────────────────────────────────────────┐
│  Chrome Extension (اکستنشن کروم)                  │
│  • کراول با سشن واقعی مرورگر                       │
│  • استخراج هوشمند DOM                             │
│  • پیمایش خودکار صفحات                            │
├──────────────────────────────────────────────────┤
│  Flask Backend (سرور محلی)                        │
│  • مدیریت صف کراول                                │
│  • Upsert هوشمند با content hash                  │
│  • SQLite Database                               │
├──────────────────────────────────────────────────┤
│  Corpus Pipeline (پایپلاین پیکره)                  │
│  • تبدیل دیتابیس به پیکره متنی خام                 │
│  • ساخت دیتاست Instruction-Tuning                 │
│  • آپلود خودکار به 🤗 HuggingFace                 │
├──────────────────────────────────────────────────┤
│  RAG Indexer (ایندکسر RAG - در دست توسعه)          │
│  • محاسبه Embedding با GPU                        │
│  • تخمین زمان با تست اولیه                        │
│  • سگمنت‌بندی و Resume                           │
└──────────────────────────────────────────────────┘
```

## 📁 ساختار پروژه

```
thesaurus-crawler/
├── backend/                    # سرور Flask + SQLite
│   ├── server.py              # API اصلی
│   └── requirements.txt
├── extension/                  # اکستنشن کروم (Manifest V3)
│   ├── manifest.json
│   ├── background.js           # Service Worker - صف و هماهنگی
│   ├── content.js              # Content Script - استخراج DOM
│   ├── popup.html              # UI پاپ‌آپ اکستنشن
│   ├── popup.js
│   └── icons/
├── corpus/                     # پایپلاین پیکره و دیتاست
│   ├── build_corpus.py         # ساخت پیکره متنی خام
│   ├── build_dataset.py        # ساخت دیتاست فاین‌تیون
│   ├── upload_to_hf.py         # آپلود به HuggingFace
│   ├── pipeline.py             # اجرای کامل پایپلاین
│   └── output/                 # خروجی‌ها (gitignored)
├── rag/                        # ایندکسر RAG (در دست توسعه)
├── README.md
└── .gitignore
```

## 🚀 نصب و راه‌اندازی - یک مرحله‌ای

### پیش‌نیازها
- Python 3.10+
- Google Chrome
- Git (برای همگام‌سازی با گیت‌هاب)

### 1. دریافت پروژه

```bash
git clone https://github.com/YOUR_USERNAME/persian-corpus-toolkit.git
cd persian-corpus-toolkit
```

### 2. نصب بکند

```bash
cd backend
pip install -r requirements.txt
python server.py
# ← روی http://127.0.0.1:5000 اجرا می‌شود
```

### 3. نصب اکستنشن کروم

1. آدرس `chrome://extensions` را در کروم باز کنید
2. **Developer mode** را روشن کنید (بالا-راست)
3. روی **Load unpacked** کلیک کنید
4. پوشه `extension/` را انتخاب کنید
5. یک تب از سایت هدف باز کنید (مثلاً `thesaurus.eiis.iki.ac.ir/fa/list/`)
6. روی آیکون اکستنشن کلیک کنید ← `🌱 Seed` ← `🚀 کراول کامل`

### 4. ساخت پیکره

```bash
cd corpus
python pipeline.py
# خروجی در پوشه corpus/output/
```

### 5. آپلود به HuggingFace

```bash
# از قبل یک توکن از https://huggingface.co/settings/tokens بسازید
python upload_to_hf.py --token hf_YOUR_TOKEN --username YOUR_USERNAME
```

## 🗄️ دیتابیس

### محل دیتابیس
`backend/thesaurus.db` (SQLite)

### ساختار جداول

| جدول | توضیح |
|------|-------|
| `crawl_queue` | صف کراول - URLها با وضعیت pending/done/crawling |
| `crawled_data` | داده‌های کراول‌شده با content hash برای تشخیص تغییرات |

### بک‌آپ و بازیابی

```bash
# بک‌آپ
cp backend/thesaurus.db backups/thesaurus_$(date +%Y%m%d_%H%M%S).db

# یا: (قبل از کراول مجدد)
sqlite3 backend/thesaurus.db ".backup 'backups/thesaurus_backup.db'"

# بازیابی
cp backups/thesaurus_20260729.db backend/thesaurus.db
```

## 🔄 Upsert هوشمند

بکند با **content hash** (SHA-256) کار می‌کند:

| وضعیت | اتفاق |
|--------|--------|
| آیتم جدید | INSERT |
| آیتم تکراری با محتوای یکسان | SKIP |
| آیتم تکراری با محتوای تغییر یافته | UPDATE (version+1) |

اگر کراول را مجدداً اجرا کنید، فقط آیتم‌های جدید یا تغییر یافته ذخیره می‌شوند.

## 📊 API Endpoints

| Endpoint | Method | توضیح |
|----------|--------|-------|
| `/api/next-job` | GET | کار بعدی در صف |
| `/api/submit-result` | POST | ارسال نتیجه کراول یک آیتم |
| `/api/page-content` | POST | ارسال لیست آیتم‌های یک صفحه |
| `/api/discover-links` | POST | اضافه کردن لینک‌های کشف‌شده به صف |
| `/api/seed-categories` | POST | پر کردن صف |
| `/api/stats` | GET | آمار کلی |
| `/api/reset-queue` | POST | ریست کارهای stuck |

## 🎯 سایت‌های پشتیبانی‌شده

### thesaurus.eiis.iki.ac.ir
- **نوع محتوا**: اصطلاحات فلسفه، منطق، کلام اسلامی
- **حجم**: ~۳۰۰,۰۰۰ آیتم
- **API**: ElasticSearch (`/fa/api/elastic/CategorySearch`)
- **کشف‌شده**: ۹ شاخه علمی، لیست full tree با CategorySearch

### farsi.khamenei.ir/speech (🚧)
- **نوع محتوا**: بیانات و سخنرانی‌ها
- **ساختار**:
  - `farsi.khamenei.ir/speech` → لیست بیانات
  - `farsi.khamenei.ir/speech-content?id=XXXXX` → صفحه هر بیان
- **داده‌های هدف**:
  - متن کامل سخنرانی
  - عنوان
  - تاریخ
  - لینک صوت
  - لینک فیلم
  - دسته‌بندی

## 🧠 RAG Indexer (در دست توسعه)

### قابلیت‌های برنامه‌ریزی‌شده:
1. **تست اولیه**: ایندکس ۱۰۰ آیتم برای تخمین سرعت
2. **تخمین زمان**: محاسبه زمان کل بر اساس GPU موجود
3. **سگمنت‌بندی**: تقسیم کار به تکه‌های قابل Resume
4. **Resume خودکار**: ادامه از آخرین نقطه توقف
5. **Anti-ban**: وقفه‌های تصادفی، exponential backoff
6. **پشتیبانی از GPU**: CUDA, MPS, CPU fallback

## 🛠️ راهنمای توسعه‌دهنده

### اضافه کردن سایت جدید

1. در `extension/content.js` یک `detectPageType()` جدید اضافه کنید
2. در `backend/server.py` یک endpoint `seed` جدید بسازید
3. در `corpus/` یک `build_corpus_SITENAME.py` جدید ایجاد کنید

### رفع مشکل CORS

در `server.py` از `flask-cors` استفاده شده. اگر مشکل دارید:
```python
CORS(app, origins=['chrome-extension://*', 'http://127.0.0.1:5000'])
```

### Debug

```bash
# لاگ بکند
python server.py  # لاگ‌ها در stdout

# لاگ اکستنشن
# در Chrome: F12 → Console → filter: [Crawler]

# چک دیتابیس
sqlite3 backend/thesaurus.db "SELECT COUNT(*) FROM crawled_data"
```

## 📝 License

CC BY-NC-SA 4.0 - استفاده پژوهشی و آموزشی

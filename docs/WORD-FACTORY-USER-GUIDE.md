# Word Factory V0.1 — راهنمای کاربر (سند B)

کارخانهٔ تبدیل فایل Word → پیکرهٔ ساختاریافته (block-based)، با خروجی‌های قابل اطمینان
و قابل بازتولید. **بدون اتصال به DB، بدون endpoint، بدون deploy** — فقط CLI.

## نصب (یک‌بار)

```bash
cd backend
pip install -r requirements.txt   # python-docx==1.2.0 افزوده شده
```

## اجرا

```bash
cd backend
python -m factory.cli "C:\path\to\book.docx" --out ../wf-out/run
```

> **Windows:** CLI به‌صورت خودکار stdout/stderr را UTF-8 می‌کند — در کنسول
> cp1252 خطای UnicodeEncodeError نمی‌دهد.

یا با گزینه‌ها:

```bash
python -m factory.cli book.docx --out ../wf-out/run \
    --threshold 0.6       # آستانهٔ score برای status ok (پیش‌فرض 0.6)
    --digits persian      # keep | persian | ascii (پیش‌فرض keep)
    --no-zwnj             # غیرفعال‌کردن قانون نیم‌فاصله
    --no-arabic           # غیرفعال‌کردن یکسان‌سازی عربی→فارسی
    --max-mb 200          # سقف حجم فایل مگابایت (پیش‌فرض 200)
    --quiet               # فقط مسیر خروجی را چاپ کند (کد خروجی: 0=ok، 1=manual_review)
```

## ورودی

- `.docx` (Office Open XML) — **پشتیبانی کامل**.
- `.doc` (OLE2/Word 97-2003) — **تشخیص می‌شود و صریحاً اعلام می‌کند پشتیبانی نمی‌شود**
  (خطای `UnsupportedFormatError`؛ هرگز parse کاذب یا خروجی ناقص بدون علامت).
- فایل خراب/خالی → خطای `ValidationFailedError`/`FormatDetectionError`؛ اگر intake رد کند،
  manifest با `processing.status: failed` نوشته می‌شود.

## خروجی (5 فایل در `out/f-<sha8>/`)

| فایل | توضیح |
|-------|-------|
| `manifest.json` | مانیفست v`m-2`: نسخه‌ها (parser/normalizer/normalizer_policy/factory)، SHA-256 ورودی، hash هر خروجی + `blocks_hash`، شمارنده‌ها، وضعیت |
| `document.json` | مدل کامل سند (پوشیده) — فایل/بلوک‌ها/ساختار/متادیتا/کیفیت |
| `blocks.jsonl` | **هر خط = یک block کامل**: `block_id`, `block_index`, `type`, `raw_text` (دست‌نخورده), `normalized_text`, `norm_version`, `content_hash`, `style`, `parent_block_id`, `position`, `page` (همیشه `null` — حدس صفحه ممنوع)، `warnings` |
| `quality-report.json` | ۸ check + score + `unextracted.losses` (image/drawing/...) + warnings |
| `report.md` | گزارش انسانی فارسی |

### قرارداد block

- `block_index` پیوسته از 0، مطابق ترتیب واقعی body (paragraph و table جابه‌جا).
- `type`: `paragraph` | `heading` | `table` | `pagebreak` | `empty`.
- `table`: `table_rows`/`table_cells` جدا — **تبدیل به متن inline ممنوع**.
- `raw_text` هیچ‌وقت تغییر نمی‌کند؛ `normalized_text` خروجی policy نسخه‌شده `n-1` است.

## سیاست نرمال‌سازی `n-1` (هر قانون قابل تنظیم + در manifest `m-2` ثبت می‌شود)

| قانون | پیش‌فرض | توضیح |
|-------|---------|-------|
| `nfkc` | خاموش | NFKC تکیه‌ها را تغییر می‌دهد (ّ→َ) — تغییر معنایی است؛ opt-in |
| `arabic_to_persian` | روشن | فقط دو جفت متغیر واقعی: `U+0649` (ى) → `U+06CC` (ی) و `U+0643` (ك) → `U+06A9` (ک)؛ ء/ة دست‌نخورده |
| `zwnj` | روشن | نیم‌فاصله فقط بین کلمهٔ کامل و پسوند (تر/ترین/مان/تان/های/ها/ای/ات/ان/ی) |
| `collapse_spaces` | روشن | فاصله‌های اضافی/تب (شامل NBSP) → یک space |
| `strip_zwsp` | روشن | حذف نویسه‌های پهنای صفر (U+200B/U+FEFF) |
| `strip_rlm` | روشن | حذف RLM/LRM (U+200E/U+200F) |
| `digits` | keep | تبدیل ارقام (اختیاری): `persian` (0-9→۰-۹) یا `ascii` (۰-۹→0-9) |
| **guard** | اجباری | هر rule که حرف/عدد عوض کند → warning + `manual_review` |

## کیفیت

- ۸ check: `file_openable`, `sha256_verified`, `non_empty_text`, `block_order_contiguous`,
  `tables_present`, `persian_content`, `headings_detected`, `no_fabricated_pages`.
- ۴ check سفت (hard-gate): شکستن هر کدام نتیجه را `manual_review` می‌کند (میانگین نمی‌تواند پنهان کند).
- `score` = میانگین checkها؛ `ok` وقتی score ≥ threshold **و** hard-gate شکسته نشده.
- `page` همیشه `null` است (docx صفحه ندارد) — ساخت/حدس صفحه ممنوع.
- استخراج ناقص (تصویر/نقشه/هایپرلینک/...) در `unextracted.losses` شمرده می‌شود؛
  **ادعای «استخراج کامل» بدون این بخش ممنوع است**.

## Idempotency

`file_id` (`f-<sha8>`) از SHA-256 ورودی است؛ اجرای دوباره روی همان فایل → همان
`f-...`، همان `blocks_hash`، **بدون خروجی تکراری** (خروجی روی همان پوشه بازنویسی
می‌شود). `blocks.jsonl` و `quality-report.json` **بایت‌به‌بایت یکسان**؛
`manifest.json`/`document.json`/`dump-manifest.json` **ساختاریا یکسان** (فقط
timestamps، مسیرها و hashهای پویای آنها تفاوت دارند — قرارداد §5).

## ایزولاسیون

- factory `server`/`flask`/`pct_test_support` import **نمی‌کند** (آزمون AST WF-12).
- فایل ورودی دست‌نخورده می‌ماند (در workspace کپی می‌شود).
- `wf-out/` در gitignore است؛ فایل Word هرگز commit نمی‌شود.

## تست

```bash
cd backend
python -m unittest test_word_factory -v                      # 24 تست WF-01..WF-13
python -m unittest test_dump -v                              # 26 تست D01..D15 (Dump d-1)
python -m unittest test_api test_projects test_dashboard test_knowledge_api test_word_factory test_dump
                                                             # 129 تست (کل)
```

## Dump (قرارداد `d-1` — PCM-14C.3)

**Dump** یک پاکت قابل حمل و خوداعتبارسنج برای یک اجرای WF است:
`dump-manifest.json` + رونویسی بایتی از 5 فایل WF — تابع خالص read-only از
دایرکتوری خروجی WF (بدون DB، بدون ES، بدون شبکه).

```bash
cd backend
# ساخت Dump (--input: همان docx اصلی برای راستی‌آزمایی SHA-256 ورودی)
python -m factory.cli make-dump ./wf-out/f-<sha8> --dump-dir ../wf-out/book-dump \
    --input "C:\path\to\book.docx"
# اعتبارسنجی — کد خروجی 0 = معتبر، 1 = نامعتبر
python -m factory.cli validate-dump ../wf-out/book-dump
# خلاصه — اعتبارسنجی + اطلاعات سند
python -m factory.cli dump-summary ../wf-out/book-dump        # یا با --json
```

- قاعده‌های اعتبارسنجی V1–V11: ساختار، فیلدهای اجباری، rehash همه‌ی SHA-256ها
  (ورودی + خروجی‌ها)، ترتیب بلوک‌ها، یکتایی `block_id`، سازگاری RAW/NORMALIZED
  با سیاست ثبت‌شده، وضعیت کیفیت.
- بدون `--input`، hash ورودی از مانیفست WF خوانده می‌شود (منبع اطمینان = مانیفست).
- سازگار با مانیفست‌های WF `m-1`/`m-2` (m-1 → سیاست ثبت‌شده null + warning).
- مسیر legacy (اجرای مستقیم .docx) بدون تغییر است.
- قرارداد کامل: [PCM-14C.3-DUMP-CONTRACT.md](PCM-14C.3-DUMP-CONTRACT.md).

## محدودیت‌های V0.1 (صریح)

- DOC (Word 97-2003): فقط تشخیص + اعلام عدم پشتیبانی.
- footnotes/endnotes: شمارش و placeholder؛ استخراج کامل v2.
- صفحه‌شماری: عمداً انجام نمی‌شود (بدون layout، حدس = ساخت).
- OCR/تصویر: خارج از scope (در losses شمرده می‌شود).

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

یا با گزینه‌ها:

```bash
python -m factory.cli book.docx --out ../wf-out/run \
    --threshold 0.85      # آستانهٔ score برای status ok (پیش‌فرض 0.85)
    --digits persian      # keep | persian | ascii (پیش‌فرض keep)
    --no-zwnj             # غیرفعال‌کردن قانون نیم‌فاصله
    --json                # خلاصهٔ JSON روی stdout
```

## ورودی

- `.docx` (Office Open XML) — **پشتیبانی کامل**.
- `.doc` (OLE2/Word 97-2003) — **تشخیص می‌شود و صریحاً اعلام می‌کند پشتیبانی نمی‌شود**
  (خطای `UnsupportedFormatError`؛ هرگز parse کاذب یا خروجی ناقص بدون علامت).
- فایل خراب/خالی → خطای `ValidationFailedError`/`FormatDetectionError`؛ اگر intake رد کند،
  manifest با `processing.status: failed` نوشته می‌شود.

## خروجی (5 فایل در `out/f-<sha256_12>/`)

| فایل | توضیح |
|-------|-------|
| `manifest.json` | نسخه‌ها (parser/normalizer)، SHA-256 ورودی، hash هر خروجی، شمارنده‌ها، وضعیت |
| `document.json` | مدل کامل سند (پوشیده) — فایل/بلوک‌ها/ساختار/متادیتا/کیفیت |
| `blocks.jsonl` | **هر خط = یک block کامل**: `block_id`, `block_index`, `type`, `raw_text` (دست‌نخورده), `normalized_text`, `norm_version`, `content_hash`, `style`, `parent_block_id`, `position`, `page` (همیشه `null` — حدس صفحه ممنوع)، `warnings` |
| `quality-report.json` | ۸ check + score + `unextracted.losses` (image/drawing/...) + warnings |
| `report.md` | گزارش انسانی فارسی |

### قرارداد block

- `block_index` پیوسته از 0، مطابق ترتیب واقعی body (paragraph و table جابه‌جا).
- `type`: `paragraph` | `heading` | `table` | `pagebreak` | `empty`.
- `table`: `table_rows`/`table_cells` جدا — **تبدیل به متن inline ممنوع**.
- `raw_text` هیچ‌وقت تغییر نمی‌کند؛ `normalized_text` خروجی policy نسخه‌شده `n-1` است.

## سیاست نرمال‌سازی `n-1` (هر قانون قابل تنظیم)

| قانون | پیش‌فرض | توضیح |
|-------|---------|-------|
| `nfkc` | خاموش | NFKC تکیه‌ها را تغییر می‌دهد (ّ→َ) — opt-in |
| `arabic_to_persian` | روشن | فقط `ى→ی` و `ک→ک` (جفت‌های متغیر واقعی) |
| `zwnj` | روشن | نیم‌فاصله فقط بین کلمهٔ کامل و پسوند (ها/تر/ترین/ای/مان/تان/ات/ان/ی) |
| `fullwidth` | خاموش | نیم‌پهن→ASCII |
| `nbsp` | روشن | NBSP→space |
| `digits` | keep | تبدیل ارقام (اختیاری) |
| `whitespace` | روشن | فاصله‌های اضافی/تب → space |
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

`file_id` از SHA-256 ورودی است؛ اجرای دوباره روی همان فایل → همان `f-...`، همان
`blocks_hash`، **بدون خروجی تکراری** (خروجی روی همان پوشه بازنویسی می‌شود).

## ایزولاسیون

- factory `server`/`flask`/`pct_test_support` import **نمی‌کند** (آزمون AST WF-12).
- فایل ورودی دست‌نخورده می‌ماند (در workspace کپی می‌شود).
- `wf-out/` در gitignore است؛ فایل Word هرگز commit نمی‌شود.

## تست

```bash
cd backend
python -m unittest test_word_factory -v                      # 24 تست WF-01..WF-13
python -m unittest test_api test_projects test_dashboard test_knowledge_api test_word_factory
                                                             # 103 تست (کل)
```

## محدودیت‌های V0.1 (صریح)

- DOC (Word 97-2003): فقط تشخیص + اعلام عدم پشتیبانی.
- footnotes/endnotes: شمارش و placeholder؛ استخراج کامل v2.
- صفحه‌شماری: عمداً انجام نمی‌شود (بدون layout، حدس = ساخت).
- OCR/تصویر: خارج از scope (در losses شمرده می‌شود).

# PCM-13 — گزارش پذیرش Word Factory V0.1 (سند A)

تاریخ: 2026-10-26 (تهران) · شاک: A (گزارش پذیرش) · وضعیت: **پایان مرحله‌ای — آماده merge (commit/push در ادامه همین جلسه)**
Scope: فقط `backend/factory/` + `backend/test_word_factory.py` + `requirements.txt` + `.gitignore` + این دایرکتوری.
بدون deploy، بدون تغییر DB، بدون تغییر API.

---

## ۱. وضعیت قبل از اجرا (baseline)

- HEAD قبل از شروع: `87e4137` — «PCM-12.3: test isolation root-cause fix (F-01) + Grafana security audit (GA-2)» (pushed).
- آزمون baseline: **39/39 سبز** در ۴ ماتریس (forward / reversed / ×2 تکرار).
- سند‌های مصوب خوانده‌شده: `docs/WORD-FACTORY-V0-1.md` (مأموریت)، `PCM-12-ACCEPTANCE-REPORT.md` (F-01/GA-2)، `PCM-12.3-TEST-ISOLATION.md` (قاعده isolation)، `PCM-05-ACCEPTANCE.md` (نمونه فرمت ۱۱ بخش)، `PCM-04-ACCEPTANCE.md` (نمونه فرمت)، `PCM-03-DEPLOY.md` (نمونه فرمت)، `docs/DEPLOYMENT-RUNBOOK.md` (قواعد deploy — این مرحله deploy ندارد).
- `python-docx` در محیط موجود بود (1.2.0) ولی در requirements نبود → در همین مرحله pin شد.

## ۲. طراحی

معماری ماژولار با **adapter pattern** برای فرمت‌های ورودی (`backend/factory/`، 13 فایل):

| ماژول | مسئولیت |
|-------|---------|
| `errors.py` | سلسله‌مراتب خطا: `FactoryError → {IntakeError→{FileMissing,UnsupportedFormat,FormatDetection}, ValidationFailed, Extraction, Normalization, Quality, Manifest, Service}` |
| `models.py` | `FileRecord`/`Block`/`DocumentModel`/`QualityResult`/`ProcessingReport` + `file_id_from_sha`/`work_id`/`edition_id`/`block_hash`/`blocks_hash`/`utc_now_iso` |
| `intake.py` | `DocumentIntakeService`: کپی به workspace ایزوله + SHA-256 + `detect_format` (magic OLE2 / zip+`[Content_Types].xml` + heuristic content-over-extension) |
| `validator.py` | `validate_docx` (موجود/خوانا/`[Content_Types].xml` قابل‌پارس) → `ValidationFailedError` |
| `parser.py` | `make_parser` + `DocParserAdapter` + `DocxParser` — قرارداد `parse(FileRecord) → (blocks, unextracted)`. **DOC: صریحاً `UnsupportedFormatError`**. `DocxParser`: استخراج **document-order** (paragraph + table interleaved)، heading style → level + parent (stack)، تکیه (hamza forms)، شمارش losses (image/drawing/shape/hyperlink) |
| `structure.py` | `DocumentStructure` — headings با parent، chapters/sections، stats |
| `metadata.py` | `build_metadata` — core properties (title/author/created/modified) + `metadata_confidence` واقعی |
| `normalize.py` | `NormalizationPolicy` (نسخه‌شده `n-1`) + `PersianNormalizer` + `verify_no_semantic_change` (guard اجباری) |
| `quality.py` | `QualityValidator` — ۸ check + hard-gates + `QualityResult` |
| `export.py` | ۵ خروجی: `manifest.json` (نسخه‌شده + hash خروجی‌ها) / `document.json` (پوشیده) / `blocks.jsonl` (هر خط یک block کامل) / `quality-report.json` / `report.md` (فارسی) |
| `service.py` | `DocumentProcessingService.process()` — pipeline کامل، **idempotent**، بدون DB/Flask |
| `cli.py` | `python -m factory.cli <input.docx> [--out DIR] [--threshold X] [--digits X] [--no-zwnj] [--json]` |

### قواعد نرمال‌سازی v1 (نسخه `n-1`) — هر قانون مستقل و قابل تنظیم است:

1. `nfkc`: **پیش‌فرض خاموش** (NFKC علامت‌های تکیه را تغییر می‌دهد: ّ→َ — تغییر محتوایی؛ opt-in فقط).
2. `arabic_to_persian`: فقط جفت‌های متغیر واقعی `ى(U+0649)→ی(U+06CC)` و `ک(U+0643)→ک(U+06A9)`؛ ء/ة دست‌نخورده.
3. `zwnj`: فقط بین کلمهٔ فارسی کامل و پسوند (lookahead پایان کلمه واقعی؛ «ش/م/ت/هست» حذف شد — join کاذب).
4. `fullwidth`→ASCII (opt-in)، `nbsp`→space (پیش‌فرض روشن).
5. `digits`: `keep`(پیش‌فرض)/`persian`/`ascii`.
6. `whitespace`: collapse + trim (پیش‌فرض روشن).
7. **guard**: `verify_no_semantic_change` — هر rule که حرف/عدد را عوض کند → warning در block + `manual_review`.

### تصمیمات مهم (با دلیل):

| تصمیم | دلیل |
|-------|-------|
| DOC (OLE2): تشخیص + اعلام عدم پشتیبانی | python-docx نمی‌خواند؛ `antiword/textract` سنگین و غیرقابل اطمینان‌سنجی بودند — اصل «ادعای استخراج کامل ممنوع» |
| `page` همیشه `null` + check `no_fabricated_pages` | docx ساختار صفحه ندارد (layout) — حدس صفحه = ساخت آمار |
| RAW هیچ‌وقت دست نمی‌خورد؛ `normalized_text` جداست | اصل مصوب «RAW دست‌نخورده» |
| `file_id` = SHA-256 ورودی؛ idempotency روی همان پوشه | WF-10 |
| quality score میانگین است اما **hard-gates** (file_openable/sha256/non_empty/block_order) شکستشان veto است | میانگین نمی‌تواند شکست سفت را پنهان کند (باگ واقعی در WF-11 پیدا شد) |
| `sectPr` انتهای body به‌عنوان بلوک ثبت نمی‌شود | خواص بخش است نه صفحه‌شکن محتوا (باگ واقعی WF-05) |
| factory `import server/flask` نمی‌کند (آزمون AST-based WF-12) | ایزولاسیون مطلق از زیرسیستم operationی |

## ۳. مهاجرت

**هیچ.** بدون DB، بدون schema، بدون endpoint.

## ۴. فایل‌ها / API

فایل‌های جدید (untracked → در commit بعدی):
```
backend/factory/__init__.py        backend/factory/models.py
backend/factory/errors.py          backend/factory/intake.py
backend/factory/validator.py       backend/factory/parser.py
backend/factory/structure.py       backend/factory/metadata.py
backend/factory/normalize.py       backend/factory/quality.py
backend/factory/export.py          backend/factory/service.py
backend/factory/cli.py
backend/factory/_smoke_fixtures.py (تابع‌های ساخت fixture برای تست)
backend/test_word_factory.py       (24 تست: WF-01..WF-13)
```
تغییرات: `backend/requirements.txt` (+`python-docx==1.2.0`)، `.gitignore` (+`wf-out/` `backend/wf-out/` `corpus/books/` `*.docx` `*.doc` — فایل‌های Word آزمایشی هرگز commit نمی‌شوند).
**API: بدون تغییر** — هیچ endpoint جدید/تغییری.

## ۵. تست‌ها

### 5.1 ماتریس رگرسیون (۴ ماتریس × ۶۳ تست) — همه **OK**:

| ماتریس | نتیجه |
|--------|-------|
| M1: `test_api test_projects test_dashboard test_word_factory` (forward) | `Ran 63 tests ... OK` |
| M2: `test_word_factory test_dashboard test_projects test_api` (reversed) | `Ran 63 tests ... OK` |
| M3: forward دوباره | `Ran 63 tests ... OK` |
| M4: `test_word_factory test_word_factory` (دوبار تکرار ماژول جدید) | `Ran 48 tests ... OK` |

### 5.2 شمارش دقیق (جدا):
`test_api`=8 · `test_projects`=9 · `test_dashboard`=22 · `test_word_factory`=24 → **63/63 سبز**.
(39 قبلی دست‌نخورده + 24 جدید.)

### 5.3 WF-01..WF-13 (24 تست):
- WF-01 دریافت سالم (3) · WF-02 فایل خراب (2) · WF-03 DOC قدیمی (4) · WF-04 متن فارسی (1)
- WF-05 ترتیب body + جدول (1) · WF-06 سلسله‌مراتب تیتر (1) · WF-07 نرمال‌سازی (4)
- WF-08 SHA-256 + manifest (1) · WF-09 JSONL (1) · WF-10 idempotency (1)
- WF-11 خطاهای استخراج ناقص (2) · WF-12 عدم اتصال DB (2) · WF-13 رگرسیون ایزولاسیون (1)

### 5.4 باگ‌های پیدا شده در تست و رفع‌شده (با شواهد):
1. **guard معکوس‌نما** (inverse map): `ه` را به `ة` و `ی` را به `ى` «برمی‌گرداند» و هر پاراگراف فارسی را manual_review می‌کرد → کاننیکال‌سازی یک‌طرفه روی هر دو طرف + معادلت NFKC در guard.
2. **NFKC پیش‌فرض**: تکیه ّ (U+0651) را به َ (U+064E) تبدیل می‌کرد (کتاب واقعی، 41 بلوک آلوده) → `nfkc=False` پیش‌فرض.
3. **ZWNJ join کاذب**: «و انگلیسی» → «و‌انگلیسی» (lookahead حرف بعدی را قبول داشت) + پسوند «ترین» وسط کلمه → lookahead محدود به پایان کلمه واقعی + لیست پسوند فقط کلیتیک کم‌خطر.
4. **score میانگین**: شکست `block_order_contiguous` با score 0.875 «ok» می‌شد → hard-gates veto.
5. **sectPr** انتهای body به‌عنوان بلوک `pagebreak` ثبت می‌شد → حذف از blocks.
6. **WF-12 order-dependent**: آزمون بر `sys.modules` global (بعد از import server در ماتریس ترکیبی) → آزمون AST-based استاتیک.

### 5.5 Secret scan:
`findstr /S /I /M password|token|secret|Bearer|API_KEY|s.tabatabaei` روی `factory/` + `requirements.txt` + `.gitignore` → **هیچ output** (پاک).

### 5.6 WF-14 — کتاب واقعی:
کتاب: `بانک جامع خاطرات مقام معظم رهبري.docx` (از `Downloads\Eitaa Desktop`؛ **کپی ایزوله** به `wf-out/bank-ehterafat.docx` — gitignored).
- file_id `f-c0167d25` · SHA-256 `27fcf603ab8f95a3479d3c2b7a0ca69249714d4e2cb2ffdb28d244f1bc4a1834`
- 941 بلوک، 213,326 کاراکتر، Persian ratio **0.9994**، ~71 صفحه (تقریب 3000 کاراکتر/صفحه)
- quality: **ok (score=1.0)**، 8/8 check سبز، بدون warning، بدون losses
- **WF-10 روی کتاب واقعی**: ۲ بار پردازش → `same file_id: True`، `same blocks_hash: True`، فقط یک پوشه `f-c0167d25`
- نمونه block (blocks.jsonl خط اول): `{"block_id":"b00000:paragraph","block_index":0,"type":"paragraph","raw_text":"بانک جامع خاطرات مقام معظم رهبري (دام ظله )",...,"normalized_text":"بانک جامع خاطرات مقام معظم رهبري (دام ظله )","norm_version":"n-1","content_hash":"sha256:49aac505baae65b8"}`
- نمونه quality-report: `{"passed":true,"score":1.0,"status":"ok","checks":[8×ok],"metrics":{"total_chars":213326,"persian_ratio":0.9994,...}}`
- کاندیدهای دیگر: `نامه‌ای به آینده.docx`/`نامه 1405.docx` در پوشه نبودند (MISSING)؛ `ناموس و بی‌ناموس.docx` اسکن 5 صفحه‌ای با 10 تصویر بود (خروجی ثبت شد ولی کاندید 30+ صفحه نیست).

## ۶. نتیجه production

**N/A — deploy ندارد** (طبق C3). هیچ تغییر روی s52؛ API/dashboard/DB production دست‌نخورده.

## ۷. SHA + لینک

- Base SHA: `87e4137`
- Commit SHA: `263dc0d`
- لینک commit: https://github.com/saber13812002/persian-corpus-toolkit/commit/263dc0d

## ۸. git status

```
 M .gitignore
 M backend/requirements.txt
?? backend/factory/
?? backend/test_word_factory.py
```
`wf-out/` و `backend/wf-out/` و `*.docx`/`*.doc` توسط `.gitignore` پوشیده‌اند (در git status ظاهر نمی‌شوند).

## ۹. بکاپ / rollback

- بکاپ: **نیازی نبود** (بدون DB/schema).
- Rollback: `git revert <commit>` + حذف `backend/factory/`؛ requirements یک خط `python-docx==1.2.0`؛ `.gitignore` هفت خط — همه قابل بازگشت.

## ۱۰. موارد باقی‌مانده

1. merge/commit/push (در ادامه همین جلسه).
2. استخراج footnotes/endnotes واقعی (v2 — فعلاً شمارش `0` و صریحاً در `unextracted`).
3. پشتیبانی DOC (antiword) — فقط تشخیص + اعلام عدم پشتیبانی.
4. صفحات واقعی PDF → خارج از scope V0.1 (docx صفحه ندارد؛ ساخت ممنوع).
5. pipeline‌بندی factory با `corpus/books/` و موتور transform (PCM-08) — طراحی بعدی.
6. `corpus/books/` در `.gitignore` گذاشته شد ولی محتوای واقعی هنوز آنجا نیست (کپی دستی در آینده).

## ۱۱. روش تست دستی (برای کاربر)

```bash
cd backend
python -m factory.cli "C:\path\to\book.docx" --out ../wf-out/run
# خروجی در wf-out/run/f-<sha12>/ :
#   manifest.json  document.json  blocks.jsonl  quality-report.json  report.md
```
- کتاب واقعی: `python -m factory.cli ..\wf-out\bank-ehterafat.docx --out ..\wf-out\run` → `quality: ok (score=1.0)`.
- تست‌ها: `cd backend && python -m unittest test_word_factory -v` (24 تست) یا کل ماتریس 63 تستی.
- خروجی `report.md` فارسی است و قابل خواندن انسانی (نمونه در `wf-out/run-bank*/f-c0167d25/report.md`).

---
*تمام آمار این گزارش از شمارنده‌های واقعی خروجی pipeline است؛ عدد ساختگی ثبت نشده.*

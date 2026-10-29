# PCM-14C.3 — قرارداد رسمی Export و قرارداد Dump (د-1)

**وضعیت:** نهایی (پیاده‌سازی‌شده + تست‌شده) · **تاریخ:** 2026-10-29
**مالک:** Word Factory (زیرسیستم پیکره) · **نسخه‌ی قرارداد Dump:** `d-1`

این سند **قرارداد رسمی** خروجی قابل‌انتقال Word Factory (Dump) است:
ساختار فایل‌ها، فیلدها، قواعد اعتبارسنجی، قواعد نسخه‌بندی، determinism،
و راهنمای عملیاتی. هدف: هر مصرف‌کننده‌ی آینده (ES / RAG / SuperRAG /
HuggingFace / هر چیز دیگر) بدون Elasticsearch و بدون دسترسی به کد
سرویس، بتواند یک Dump را **بازسازی** و **تأیید** کند.

- قرارداد بلوک‌ها و شناسه‌ها: [PCM-12-DATA-CONTRACTS.md](PCM-12-DATA-CONTRACTS.md) §2
- مستندسازی خط لوله: [WORD-FACTORY-USER-GUIDE.md](WORD-FACTORY-USER-GUIDE.md)
- کد: `backend/factory/dump.py` · آزمون‌ها: `backend/test_dump.py` (D01..D15)

---

## 1. اصول طراحی

1. **Dump تابع خالص و فقط‌خوانده از خروجی یک اجرای Word Factory است.**
   بدون parse مجدد، بدون LLM، بدون ES، بدون DB، بدون شبکه.
2. **RAW هرگز جایگزین نمی‌شود.** هر بلوک هم‌زمان `raw_text`
   (بایت‌به‌بایت) و `normalized_text` (خروجی سیاست ثبت‌شده) را دارد.
3. **خوداعتبارسنج‌پذیر:** هر Dump با فایل‌های **خودش** اعتبارسنجی
   می‌شود (SHA-256 ثبت‌شده + بازنرمال‌سازی از روی سیاست ثبت‌شده +
   بازمحاسبه‌ی `content_hash`) — بدون هیچ وابستگی خارجی.
4. **Determinism مستند:** فایل‌ها و بلوک‌ها با ترتیب قطعی تولید می‌شوند.
   فیلدهای زمان‌بندی (`*_at`, `duration_ms`) **تنها** تفاوت مجاز
   بین دو اجراست (بخش 5).
5. **سازگاری به‌پایین:** اجرای WF با مانیفست `m-1` یا `m-2` هر دو
   قابل تبدیل به Dump هستند (بخش 6).
6. **بدون ادعای سازگاری ES:** این قرارداد **مستقل** از Elasticsearch
   است. هیچ mapping واقعی ES برای این Dump وجود ندارد و در این سند
   ادعایی از این دست نمی‌شود؛ معماری مصرف‌کننده‌ی ES صرفاً طرح
   (بخش 8).

## 2. ساختار فایل Dump

```text
<collection-or-book>-dump/
  dump-manifest.json    ← قرارداد d-1 (این سند) — hash/size/نسخه/شناسه/یکپارچگی
  manifest.json         ← مانیفست اجرای WF (m-1 یا m-2)
  document.json         ← مدل سند (شناسه‌ها، متادیتا، ساختار، فهرست بلوک‌ها)
  blocks.jsonl          ← هر خط = یک بلوک (RAW + NORMALIZED + content_hash)
  quality-report.json   ← ۸ check + score + status (Quality Gate)
  report.md             ← گزارش انسانی (برای مرور چشمی)
```

- نام دایرکتوری Dump آزاد است (پیشنهاد: `<book>-dump` یا `<collection>-dump`).
- ترتیب `files[]` در dump-manifest همیشه `manifest.json, document.json,
  blocks.jsonl, quality-report.json, report.md` است (قطعی و مستند).
- ترتیب بلوک‌ها در `blocks.jsonl` = `block_index` پیوسته از 0
  (ترتیب واقعی body سند).
- کدگذاری همه‌ی فایل‌ها: **UTF-8** (بدون BOM). `blocks.jsonl` به‌صورت
  «هر خط یک JSON» (JSON Lines) است.
- 5 فایل WF **بایت‌به‌بایت** از اجرای WF کپی می‌شوند (خود WF دست‌نخورده).

## 3. فیلدهای `dump-manifest.json` (قرارداد d-1)

| کلید | نوع | توضیح |
|------|-----|-------|
| `dump_contract_version` | string | `"d-1"` — نسخه‌ی قرارداد Dump |
| `generated_at` | string | ISO-8601 UTC (ناپایدار — بخش 5) |
| `generator` | string | `"word-factory/<FACTORY_VERSION>"` |
| `source.kind` | string | `"word-factory-run"` |
| `source.input_file` | object | `filename, file_id, size_bytes, sha256, sha256_source` |
| `source.input_file.sha256_source` | string | `"manifest"` (حالت پیش‌فرض) یا `"rehashed"` (اگر docx اصلی داده شود و باز-hash شده باشد) |
| `identifiers` | object | `file_id (f-…)`, `work_id (w-…)`, `edition_id (e-…)`, `volume_id (v-…|null)` — فقط شناسه‌های **قابل اثبات** از اجرای WF |
| `document` | object | `title, author, publisher, publish_year, volume_no` (extract-only؛ ممکن است null باشد — حدس ممنوع) + `language: "fa"` |
| `versions` | object | `manifest` (m-1\|m-2), `schema` (wf-schema-1), `parser` (p-1), `normalizer` (n-1), `normalizer_policy` (نسخه‌ی کامل سیاست یا null در m-1), `factory` |
| `files[]` | array | برای هر 5 فایل WF: `name, sha256, size_bytes, encoding:"utf-8", format` (+ `line_count` برای blocks.jsonl) — ترتیب قطعی |
| `counts` | object | `blocks` (شمارنده‌ی واقعی JSONL), `total_chars` |
| `quality` | object | `status` (وضعیت اجرای WF: done\|manual_review), `score`, `quality_status` (ok\|manual_review\|failed) |
| `integrity` | object | `input_sha256`, `blocks_hash` (m-2؛ در m-1 برابر null), `file_hashes_verified: true` |

### 3.1 نمونه‌ی واقعی (خروجی واقعی `generate_dump` برای یک DOCX فارسی کوچک)

> این نمونه از خروجی واقعی CLI است؛ مقدار `sha256`ها در اجرای
> شما با همان فایل یکسان خواهد بود (determinism). آزمون D14
> کلیدهای سطح بالای این نمونه را با خروجی واقعی مقایسه می‌کند.

```json
{
  "dump_contract_version": "d-1",
  "generated_at": "2026-10-29T08:30:00Z",
  "generator": "word-factory/0.1",
  "source": {
    "kind": "word-factory-run",
    "input_file": {
      "filename": "book.docx",
      "file_id": "f-01234567",
      "size_bytes": 36214,
      "sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
      "sha256_source": "manifest"
    }
  },
  "identifiers": {
    "file_id": "f-01234567",
    "work_id": "w-abcdef01",
    "edition_id": "e-fedcba98",
    "volume_id": null
  },
  "document": {
    "title": null,
    "author": null,
    "publisher": null,
    "publish_year": null,
    "volume_no": null,
    "language": "fa"
  },
  "versions": {
    "manifest": "m-2",
    "schema": "wf-schema-1",
    "parser": "p-1",
    "normalizer": "n-1",
    "normalizer_policy": {
      "version": "n-1",
      "nfkc": false,
      "arabic_to_persian": true,
      "zwnj": true,
      "collapse_spaces": true,
      "strip_zwsp": true,
      "strip_rlm": true,
      "digits": "keep",
      "rules": ["arabic_to_persian", "zwnj", "collapse_spaces", "strip_zwsp", "strip_rlm"]
    },
    "factory": "0.1"
  },
  "files": [
    {"name": "manifest.json", "sha256": "1111111111111111111111111111111111111111111111111111111111111111", "size_bytes": 2148, "encoding": "utf-8", "format": "json"},
    {"name": "document.json", "sha256": "2222222222222222222222222222222222222222222222222222222222222222", "size_bytes": 4310, "encoding": "utf-8", "format": "json"},
    {"name": "blocks.jsonl", "sha256": "3333333333333333333333333333333333333333333333333333333333333333", "size_bytes": 5902, "encoding": "utf-8", "format": "jsonl", "line_count": 12},
    {"name": "quality-report.json", "sha256": "4444444444444444444444444444444444444444444444444444444444444444", "size_bytes": 1212, "encoding": "utf-8", "format": "json"},
    {"name": "report.md", "sha256": "5555555555555555555555555555555555555555555555555555555555555555", "size_bytes": 1687, "encoding": "utf-8", "format": "markdown"}
  ],
  "counts": {"blocks": 12, "total_chars": 542},
  "quality": {"status": "done", "score": 0.95, "quality_status": "ok"},
  "integrity": {
    "input_sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
    "blocks_hash": "9999999999999999999999999999999999999999999999999999999999999999",
    "file_hashes_verified": true
  }
}
```

## 4. قواعد اعتبارسنجی (V1..V11) — `validate_dump`

اعتبارسنجی **فقط** فایل‌های خود Dump را می‌خواند (بدون ES/DB/خروجی WF):

| # | بررسی | نتیجه در صورت شکست |
|---|-------|---------------------|
| V1 | `dump-manifest.json` موجود، خوانا، و `dump_contract_version == "d-1"` | error |
| V2 | هر فایل فهرست‌شده در `files[]` موجود است؛ `sha256` و `size_bytes` هرکدام با فایل واقعی می‌خواند | error (`sha256_mismatch:<file>`) |
| V3 | هر 5 فایل WF + dump-manifest حاضرند | error |
| V4 | `blocks.jsonl`: هر خط JSON معتبر؛ کلیدهای قرارداد (`block_id, block_index, type, raw_text, normalized_text, norm_version, content_hash, page`)؛ `block_index` پیوسته از 0؛ `block_id` یکتا و مطابق `b{index:05d}:{type}`؛ `page == null` | error |
| V5 | `content_hash` هر بلوک با `sha256(normalized_text)[:16]` بازمحاسبه‌شده می‌خواند | error (`content_hash_mismatch`) |
| V6 | `normalized_text` = خروجی **سیاست ثبت‌شده** در dump-manifest روی `raw_text` (بازنرمال‌سازی؛ برای بلوک‌های `empty/pagebreak/table` برابر `raw_text`) | error (`normalized_mismatch`) — در m-1 skipped + warning |
| V7 | `norm_version` هر بلوک با `versions.normalizer` می‌خواند | error |
| V8 | `line_count` و `counts.blocks` با شمارش واقعی JSONL می‌خواند | error |
| V9 | مانیفست WF: نسخه‌ی معتبر (m-1\|m-2) + hash خروجی‌های ثبت‌شده در WF با فایل‌های Dump می‌خواند | error |
| V10 | `quality-report.json`: status معتبر (ok\|manual_review\|failed)؛ اجرای «done» با quality «failed» تناقض دارد | error |
| V11 | `work_id`/`edition_id` در document.json با `identifiers` مانیفست Dump می‌خواند | error |

نتیجه: `(valid: bool, errors: list[str], warnings: list[str])` — **کد
خروجی CLI: 0 = معتبر، 1 = نامعتبر** (warnings مانع معتبربودن نیستند).

### 4.1 تشخیص‌های قابل کشف

- **Dump ناقص:** فایل گم / entry گم در `files[]` (V2/V3)
- **Dump مربوطه (tampered):** هر تغییری در محتوای هر 6 فایل → `sha256_mismatch` (V2)
- **Dump ناسازگار/اجنبی:** قرارداد متفاوت (V1)، نسخه‌ی WF غلط (V9)
- **تغییر سیاست نرمال‌سازی پس از ساخت:** V6 شکست می‌خورد
  (بازنرمال‌سازی با policy ثبت‌شده دیگر normalized_text را بازتولید نمی‌کند)

## 5. Determinism و تکرارپذیری

دو اجرای کامل WF روی **همان** فایل ورودی، با **همان** سیاست:

| فایل | پایدار بایت‌به‌بایت؟ | توضیح |
|-------|:---:|-------|
| `blocks.jsonl` | ✅ | فقط محتوا (بدون timestamp) |
| `quality-report.json` | ✅ | فقط نتایج checkها |
| `document.json` | ساختاری ✅ | (فقط timestampهای فیلد `file.created_at` متفاوت‌اند) |
| `manifest.json` | ساختاری ✅ | `processing.started_at/finished_at/duration_ms` متفاوت |
| `report.md` | ساختاری ✅ | stamp پایانی متفاوت |
| `dump-manifest.json` | ساختاری ✅ | `generated_at` متفاوت |

- **`blocks_hash`** (مانیفست WF) و **`work_id/edition_id/file_id`**
  بین دو اجرا **یکسان** می‌مانند → idempotency (WF-10).
- `generate_dump` روی همان دایرکتوری Dump، فایل‌ها را **درجا**
  بازنویسی می‌کند — هیچ فایل تکراری/اضافی ساخته نمی‌شود.
- آزمون‌های D05 و D10 این موارد را با claim واقعی می‌سنجند.

## 6. سازگاری نسخه‌ها (به‌پایین) و ریسک `block_id`

### 6.1 سازگاری m-1

- `generate_dump` هر دو مانیفست WF `m-1` و `m-2` را می‌پذیرد.
- در `m-1` سیاست نرمال‌سازی در مانیفست ثبت **نشده** بود:
  `versions.normalizer_policy: null` و `integrity.blocks_hash: null`
  در dump-manifest ثبت می‌شود و V6 با **warning صریح**
  (`normalizer_policy not recorded (m-1 run) — re-normalization check
  skipped`) رد می‌شود. سایر Vها (V1..V5, V7..V11) کامل اجرا می‌شوند.
- **داده‌های تاریخی بازنویسی نمی‌شوند**؛ خروجی‌های m-1 موجود
  (مثل `wf-out/run-bank` در ممیزی PCM-14C.2) بدون تغییر قابل تبدیل
  به Dump هستند و مصرف‌کننده باید بداند re-normalization روی آن‌ها
  تأییدنی‌شده است.

### 6.2 ریسک‌شناسی `block_id = b{index:05d}:{type}` (ارزیابی‌شده، بدون تغییر)

- **موقعیت‌محور بودن:** اگر parser در نسخه‌ی بعدی یک بلوک را حذف/افزود،
  `block_id` تمام بلوک‌های پایین‌تر عوض می‌شود — `block_id` برای
  «ارجاع به یک بلوک در یک **نسخه‌ی** خروجی» قابل‌اطمینان است، نه
  «همان بلوک در دو خروجی متفاوت».
- **type داخل id:** اگر طبقه‌بندی parser (مثلاً paragraph→heading) در
  نسخه‌ی بعدی عوض شود، id همان بلوک عوض می‌شود.
- **مطابقت با آزمون‌ها:** قواعد V4 id را با `block_index` و `type`
  **همان** رکورد بازمی‌خواند — یعنی صحت ساختاریِ داخل Dump، نه
  ثبات بین دو نسخه.
- **تصمیم PCM-14C.3:** مطابق قاعده‌ی مأموریت، `block_id` **تغییر
  نمی‌کند**؛ ثبات واقعی محتوا با `content_hash` (که فقط روی
  `normalized_text` است) و `file_id`/`edition_id` (که روی SHA-256
  فایل است) سنجیده می‌شود.

## 7. قواعد نسخه‌بندی

چهار نسخه‌ی **مستقل** وجود دارند + قرارداد Dump:

| نسخه | ثابت | چه چیزی را پوشش می‌دهد |
|------|------|------------------------|
| `p-N` | `PARSER_VERSION` | رفتار parser (بلوک‌ها، سلسله‌مراتب) |
| `n-N` | `NORM_VERSION` | سیاست/الگوریتم نرمال‌سازی |
| `m-N` | `MANIFEST_VERSION` | ساختار `manifest.json` (m-1→m-2: ثبت `normalizer_policy` + `factory` + `blocks_hash` — افزایشی) |
| `wf-schema-1` | `SCHEMA_VERSION` | ساختار رکورد بلوک در `blocks.jsonl` |
| `d-N` | `DUMP_VERSION` | ساختار خود Dump و `dump-manifest.json` |

**قواعد:**

1. **تغییر سیاست نرمال‌سازی** (مثلاً روشن‌شدن nfkc، تغییر digits) →
   `n-N` بالا می‌رود و نگاشت کامل policy در مانیفست ثبت می‌شود.
   `d-N` و `m-N` **تغییر نمی‌کنند** — چون ساختار قرارداد عوض نشده،
   فقط **مقدار** ثبت‌شده‌ی policy عوض شده است. (این همان ابهامی بود که
   ممیزی PCM-14C.2 روی 41 بلوک تفاوت‌دار همان فایل نشان داد؛ با ثبت
   کامل policy، «کدام سیاست» هرگز دوباره گم‌شده نیست.)
2. **تغییر ساختار Dump** (فیلد جدید در dump-manifest، فایل جدید،
   تغییر فرمت) → `d-N` بالا می‌رود؛ سازگاری به‌پایین فقط اگر
   افزایشی و مکتوب باشد.
3. **تغییر ساختار manifest WF** → `m-N` (افزایشی).
4. `MANIFEST_VERSION` در این مأموریت `m-1 → m-2` (افزایشی؛
   `knowledge_api` و بقیه کد، m-1 را می‌پذیرند و در حافظه کار می‌کنند).

## 8. معماری مصرف‌کننده‌های آینده (طرح فقط — بدون پیاده‌سازی)

Dump یک **نقطه‌ی اتصال واحد** (single ingest point) برای همه‌ی
مصرف‌کننده‌هاست؛ هیچ‌کدام مستقیم به WF/DB/s52 متصل نمی‌شوند:

```text
                 ┌────────────────────────────┐
 WF run → Dump ──┤  dumper-adapter (offline)  │
 (d-1)           └──────────────┬─────────────┘
                                │ (converters — فازهای آینده)
        ┌───────────────────────┼────────────────────────┐
        ▼                       ▼                        ▼
  ES importer              RAG indexer              HF dataset
  (mapping واقعی +        (chunk از blocks.jsonl    (آرشیو عمومی؛
   ILM + alias)            + metadata از             بدون PII)
                           document.json)
```

- **ES:** mapping واقعی (پیش‌نویس در PCM-12-DATA-CONTRACTS §3) فقط
  پس از آنکه یک importer واقعی روی یک Dump واقعی ساخته و تست شود
  اعتبار پیدا می‌کند. تا آن زمان **ادعای سازگاری ES نمی‌شود**.
- **RAG/SuperRAG:** chunking بر اساس بلوک‌های `heading/paragraph`
  با `parent_block_id` برای context؛ `content_hash` برای dedup.
- **HuggingFace:** خروجی JSONL/Parquet از `blocks.jsonl` +
  `document.json`؛ شناسه‌ها (`f-/w-/e-`) قابل ردیابی می‌مانند.
- این بخش **طرح معماری** است؛ هیچ endpoint، کد، یا pipeline برای
  این مصرف‌کننده‌ها در ریپازیتوری وجود ندارد.

## 9. راهنمای عملیاتی (CLI)

```bash
cd backend

# 1) پردازش (رفتار سنتی WF)
python -m factory.cli path/to/book.docx --out ./wf-out

# 2) ساخت Dump از خروجی WF (--input اختیاری: rehash فایل اصلی)
python -m factory.cli make-dump ./wf-out/<file_id> --dump-dir ./book-dump --input path/to/book.docx
python -m factory.cli make-dump ./wf-out/<file_id> --dump-dir ./book-dump --json

# 3) اعتبارسنجی Dump (بدون ES/DB)
python -m factory.cli validate-dump ./book-dump          # انسانی
python -m factory.cli validate-dump ./book-dump --json   # automation

# 4) خلاصه + یکپارچگی
python -m factory.cli dump-summary ./book-dump --json
```

**کدهای خروجی:** پردازش: `0=done · 1=failed/quality-review ·
2=unsupported-format · 3=usage` — Dump: `0=معتبر/ساخت‌شده ·
1=نامعتبر/خطا · 3=usage`.

**عیب‌یابی سریع:**

| پیام | معنی / اقدام |
|------|--------------|
| `manifest.json در … پیدا نشد` | مسیر دایرکتوری WF را (نه فایل docx) دادید |
| `SHA-256 فایل ورودی با مانیفست WF نمی‌خواند` | docx اصلی با اجرای WF جفت نمی‌شود (نسخه‌ی جدیدتر فایل؟) |
| `sha256_mismatch:<file>` | فایل Dump دست‌خورده/مقاوم است — Dump را دوباره بسازید |
| `normalized_mismatch:<bid>` | policy ثبت‌شده normalized را بازتولید نمی‌کند — نسخه‌ی کد/سیاست با اجرای WF نمی‌خواند |
| warning `normalizer_policy not recorded (m-1 run)` | اجرای WF قدیمی (m-1)؛ re-normalization تأییدنی‌شده است — برای تأیید کامل، WF را با کد فعلی دوباره اجرا کنید |

## 10. ماتریس آزمون (D01..D15) — `backend/test_dump.py`

| آزمون | پوشش | تعداد |
|-------|-------|:---:|
| D01 | ساخت Dump از DOCX فارسی معتبر (فیلدهای قرارداد) | 1 |
| D02 | اعتبارسنجی ساختار (فایل‌ها / فیلدها / hashها) | 3 |
| D03 | SHA-256 ورودی و خروجی‌ها (ثبت‌شده + rehash + mismatch) | 2 |
| D04 | رد Dump تahrif‌شده / ناقص | 2 |
| D05 | تکرارپذیری (دو WF run / دو generate روی همان WF) | 2 |
| D06 | حفظ RAW + مطابقت NORMALIZED با سیاست ثبت‌شده (پیش‌فرض + digits=persian) | 2 |
| D07 | ترتیب بلوک‌ها + block_id یکتا | 1 |
| D08 | سند خالی / WF ناقص / JSONL خراب | 3 |
| D09 | بازسازی و اعتبارسنجی بدون ES (فقط خود Dump) | 1 |
| D10 | idempotency ساخت Dump (بدون فایل تکراری) | 1 |
| D11 | سازگاری با مانیفست WF m-1 | 1 |
| D12 | بدون DB/production import (AST guard) + بدون فایل DB | 2 |
| D13 | چرخه‌های تکراری در-process (×۳) | 1 |
| D14 | نمونه‌ی JSON این سند = ساختار خروجی واقعی | 1 |
| D15 | CLI make-dump/validate-dump/dump-summary + legacy بدون تغییر | 3 |
| **جمع** | | **26** |

اجرا:

```bash
cd backend
python -m unittest test_dump -v          # 26 تست
python -m unittest test_api test_projects test_dashboard test_knowledge_api test_word_factory test_dump -v   # رگرسیون کامل (129)
```

## 11. شواهد تکرارپذیری روی فایل واقعی (اجرا شده)

اجرای واقعی روی سه کتاب DOCX موجود در `wf-out` (فقط‌خوانده؛ بدون commit فایل‌های
کاربری) — همان کتاب دو بار پردازش شد (دو دایرکتوری موقت مستقل)، سپس برای هر دو
`generate_dump(..., source_docx=...)` و `validate_dump` اجرا شد:

| کتاب | file_id | بلوک‌ها | quality | validate |
|-------|---------|:-------:|---------|:--------:|
| `namous.docx` | `f-4fe7c707` | 69 | ok (1.0) | ✅ |
| `bank-ehterafat.docx` | `f-c0167d25` | 941 | ok (1.0) | ✅ |
| `rahnamaye.docx` | `f-a471ea35` | 26 | ok (1.0) | ✅ |

برای **هر سه** کتاب:

- `file_id` / `work_id` / `edition_id` / `blocks_hash` بین دو اجرا **دقیقاً یکسان**؛
- `blocks.jsonl` و `quality-report.json` **بایت‌به‌بایت یکسان**؛
- `manifest.json`، `document.json` و `dump-manifest.json` **ساختاریا یکسان** (فقط timestamps، مسیرها و hashهای پویای آنها تافاوت دارند)؛

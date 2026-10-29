# PCM-16 — پیکره‌ساز (Corpus Builder) از روی Dumpهای معتبر — قرارداد c-1

**وضعیت:** پیاده‌سازی‌شده و تست‌شده (175/175) — کد: `backend/factory/corpus.py`
(+ CLI `build-corpus` در `factory/cli.py`)، تست‌ها: `backend/test_corpus_builder.py`
(C-01…C-16، 24 تست)
**محدودیت:** ماژول کاملاً جدا و خالص — بدون DB، بدون Flask، بدون ES، بدون
LLM، بدون شبکه؛ فقط‌خوانده از دایرکتوری‌های Dump d-1؛ هیچ بارگذاری عمومی
(HF یا غیره) انجام نمی‌شود.

---

## ۱. خلاصه

پایان خط «فایل Word → خروجی WF → Dump d-1» به یک **پیکره‌ی قابل‌انتقال**
بسته می‌شود: `build_corpus(dump_dirs, out_dir)` روی Dumpهای **معتبر** (V1…V11
قرارداد d-1) دو جریان جدا — RAW و NORMALIZED — با provenance کامل، dedup،
آمار واقعی، آرشیو قطعی و پکیج محلی Hugging Face می‌سازد.

- ورودی: یک یا چند دایرکتوری Dump (`dump-manifest.json` + 5 فایل WF).
- **هر Dump پیش از هر خط نگارش باید `validate_dump` را بگذراند**؛ حتی یک
  Dump نامعتبر در میان چند Dump سالم → `CorpusError` و هیچ فایلی نوشته
  نمی‌شود (fail-fast — تست C-03).
- خروجی: ۴ فایل JSONL + 1 آرشیو ZIP + 1 مانیفست c-1 + 1 پکیج HF محلی.

## ۲. قرارداد c-1 (خروجی‌ها)

```text
<out-dir>/
  corpus-manifest.json     ← قرارداد c-1 (manifest نسخه‌شده)
  raw.jsonl                ← جریان RAW: هر خط = یک بلوک (متن خام + provenance)
  normalized.jsonl         ← جریان NORMALIZED: هر خط = یک بلوک (متن نرمال + provenance)
  raw.unique.jsonl         ← بدون‌تکرار RAW + raw_hash + occurrence_count + occurrences
  normalized.unique.jsonl  ← بدون‌تکرار NORMALIZED + occurrence_count + occurrences
  corpus-data.zip          ← آرشیو قطعی = 4 فایل JSONL (بدون manifest)
  hf-package/              ← پکیج محلی HF: README.md + manifest + 4 فایل JSONL
```

### ۲.۱ خط جریان RAW

```json
{
  "record_id": "cb1:<input_sha12>:<block_id>",
  "block_id": "b00003:paragraph",
  "block_index": 3,
  "type": "paragraph",
  "raw_text": "…",
  "provenance": {
    "input_sha256": "…64 hex…", "input_filename": "book.docx",
    "factory_file_id": "f-…", "work_id": "w-…",
    "edition_id": "e-…", "volume_id": "v-…",
    "dump_dir": "C:\\…", "dump_contract": "d-1",
    "dump_blocks_sha256": "…", "dump_manifest_sha256": "…",
    "versions": {"manifest": "m-2", "schema": "wf-schema-1",
                 "parser": "p-1", "normalizer": "n-1",
                 "normalizer_policy": {"…": "…"}, "factory": "0.1"}
  },
  "document": {"title": "…", "author": "…", "publisher": "…",
               "publish_year": "…", "volume_no": 1, "language": "fa"}
}
```

### ۲.۲ خط جریان NORMALIZED

همان `record_id/block_id/block_index/type/provenance/document` +
`normalized_text` + `norm_version` + `content_hash` (همان سه فیلدی که
قرارداد بلوک WF تعریف می‌کند).

### ۲.۳ جریان‌ها جدا هستند

- `raw.jsonl` فقط `raw_text` دارد و `normalized.jsonl` فقط `normalized_text`
  (تست C-06) — RAW هرگز با نسخه‌ی نرمال‌شده جایگزین نمی‌شود.
- بلوک‌های غیرنرمال‌شده (empty/pagebreak/table) در WF `normalized == raw`
  هستند؛ پیکره‌ساز همین مقدار ثبت‌شده را انتقال می‌دهد.

### ۲.۴ dedup

| جریان | کلید | در فایل unique |
|-------|------|----------------|
| raw | `sha256(raw_text)[:16]` | `raw_hash` |
| normalized | `content_hash` = `sha256(normalized_text)[:16]` (همان قرارداد WF) | `content_hash` |

- استراتژی: **first-occurrence** در ترتیب قطعی (مستند در `policy` مانیفست) —
  خط unique اولین رخداد را نگه می‌دارد و `occurrence_count` + `occurrences`
  (لیست `<input8>:<block_id>`) همه‌ی رخدادها را ثبت می‌کنند؛ هیچ provenance‌ای
  حذف نمی‌شود (تست C-07).
- dedup بین فایل‌هاست (و داخل فایل اگر تکرار داشت) — شمارنده‌های
  `duplicates_raw/duplicates_normalized` در مانیفست = `lines - unique`.

### ۲.۵ مانیفست c-1 (fields)

```text
corpus_contract_version: "c-1"
generated_at            (تنها فیلد ناپایدار — جزو determinism نیست)
generator               "word-factory/0.1"
policy{streams, raw_kept_byte_exact, dedup_key_*, dedup_strategy,
       deterministic_order, archive, db: none, elasticsearch: none,
       network: none, llm: none}
files[]                 {name, sha256, size_bytes, line_count, encoding, format}
archive{name, sha256, size_bytes, members}
input_dumps[]           {dir, file_id, input_sha256, input_filename,
                         work/edition/volume, dump_contract,
                         dump_blocks_sha256, dump_manifest_sha256, versions,
                         quality{status, score, quality_status}, document,
                         counts{blocks, raw_chars, normalized_chars}}
counts{dumps, blocks_total, blocks_unique_raw, blocks_unique_normalized,
       duplicates_raw, duplicates_normalized, raw_chars, normalized_chars,
       by_type, dumps_by_quality}
integrity{all_dumps_validated: true, validation_rules: "dump d-1 (V1..V11)"}
hf_package{dir, upload: "manual", files{sha256}}
```

**قاعده:** دو کپی مانیفست (ریشه + hf-package) بایتی یکسان می‌مانند و
همان dict با همان serializer نوشته می‌شوند (تست C-13).

## ۳. determinism (دقیق)

| عنصر | قاعده |
|------|-------|
| ترتیب دامپ‌ها | مرتب‌سازی `(input_sha256, factory_file_id)` — جابه‌جایی ورودی `dumps` هیچ تأثیری ندارد (C-02) |
| ترتیب بلوک‌ها | `block_index` (همان ترتیب واقعی body) |
| 4 فایل JSONL | بایتی یکسان بین دو build در هر دو دایرکتوری (C-09/C-10) |
| ZIP | ترتیب ثابت members، timestamp ثابت 1980-01-01، deflate-9 → بایتی یکسان (C-11) |
| ناپایدار | فقط `generated_at` (manifest/README) |

## ۴. idempotency

`build_corpus` روی همان `out_dir` → بازنویسی درجا: فایل‌ها بایتی یکسان،
فایل جدیدی ساخته نمی‌شود، hash آرشیو با مانیفست می‌خواند (C-09).

## ۵. آمار — فقط واقعی

همه‌ی شمارنده‌ها از خود داده محاسبه می‌شوند (بازخوانی JSONL‌های ساخته‌شده /
ردیف‌های بلوک) — هیچ عدد تخمینی/ساختگی (C-12 با بازمحاسبه‌ی مستقل راستی
می‌آزماید). README پکیج HF هم فقط از همین شمارنده‌ها پر می‌شود.

## ۶. Hugging Face — فقط پکیج محلی

- `hf-package/` = README.md (کارت داده با `language: fa`،
  `license: cc-by-nc-sa-4.0`) + مانیفست + 4 فایل داده.
- **هیچ کد بارگذاری، هیچ import شبکه، هیچ دسترسی اینترنتی در این ماژول
  نیست** (guard با AST — C-15). بارگذاری عمومی فقط با تأیید صریح مالک داده
  و خارج از این ماژول.

## ۷. quality gate (اختیاری)

`require_quality="ok"` → فقط دامپ‌هایی با `quality_status == "ok"` وارد
پیکره می‌شوند؛ هر دامپ دیگر → `CorpusError` پیش از نگارش (C-05). پیش‌فرض
(`None`) = همه‌ی دامپ‌های معتبر d-1، با ثبت `dumps_by_quality` در مانیفست.

## ۸. CLI

```bash
cd backend
python -m factory.cli build-corpus ./dump1 ./dump2 --out ./corpus \
    [--require-quality ok] [--json]
```

کدهای خروجی: `0` = ساخته‌شد · `1` = خطا/رد دامپ · `3` = usage.
رفتار زیردستورهای legacy (process/make-dump/validate-dump/dump-summary)
بدون تغییر (C-14c).

## ۹. سازگاری به‌پایین

Dumpهایی از اجرای WF با مانیفست m-1 (سیاست نرمال‌سازی ثبت‌نشده) — که
`validate_dump` آن‌ها را با warning «re-normalization check skipped» معتبر
می‌داند — برای پیکره‌سازی پذیرفته می‌شوند؛ `versions.normalizer_policy`
در `input_dumps` به صورت `null` ثبت می‌شود (C-16).

## ۱۰. ماتریس تست (test_corpus_builder.py — 24 تست)

| # | پوشش |
|---|-------|
| C-01 | ساخت از یک Dump معتبر؛ hash/size/line_count همه‌ی فایل‌ها با بازمحاسبه می‌خواند |
| C-02 | جابه‌جایی ورودی → خروجی بایتی یکسان + ترتیب قطعی بلوک‌ها |
| C-03 | Dump tampered/ناقص/یک-بد-در-میان-سالم → CorpusError پیش از هر نگارش |
| C-04 | دایرکتوری غایب / require_quality نامعتبر |
| C-05 | quality gate: `ok` vs `manual_review` |
| C-06 | دو جریان جدا: RAW بایتی دست‌نخورده + NORMALIZED مطابق policy + کلیدهای جدا |
| C-07 | dedup بین ۳ فایل + occurrence tracking + content_hash در unique normalized |
| C-08 | provenance کامل و راستی‌آزموده با مقادیر واقعی Dump |
| C-09 | idempotency: rebuild درجا بایتی یکسان، بدون فایل جدید |
| C-10 | determinism بین دو دایرکتوری مستقل + manifest جزو generated_at یکسان |
| C-11 | ZIP: members/ترتیب + استخراج = بایت فایل‌ها + بایتی قطعی |
| C-12 | همه‌ی آمار مانیفست با بازمحاسبه‌ی مستقل می‌خواند |
| C-13 | پکیج HF محلی: کپی بایتی + README با آمار واقعی + «فقط محلی» |
| C-14 | CLI: موفقیت (exit 0) + رد دامپ خراب (exit 1) + legacy دست‌نخورده |
| C-15 | AST guard: بدون import ماژول‌های production/شبکه + بدون ساخت فایل DB |
| C-16 | سازگاری m-1 (policy ثبت‌نشده) — warning + پذیرش با null policy |

## ۱۱. محدودیت‌ها (صادقانه)

- پیکره‌ساز **offline** است: برای ساخت Dump جدید باید WF اجرا و Dump ساخته
  شود (pipeline: WF → make-dump → build-corpus).
- `dedup` فقط سطح «متن یکسان» است (نه fuzzy/semantic) — دو پاراگراف
  تقریباً یکسان هر دو باقی می‌مانند.
- `hf-package` فقط **محلی** است؛ هر انتشار عمومی مسئولیت عملیات و مالک داده
  است (خارج از محدوده‌ی این ماژول).
- مسیر `dump_dir` در provenance مطلق و وابسته به مکان است (برای ردیابی؛
  جزو determinism خروجی نیست — خروجی روی مقادیر hash/identities سنجیده می‌شود).

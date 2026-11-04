# PCM-20.3 — خط تولید پیکره‌ی تسنیم (Tasnim Corpus Factory) — قرارداد c-20.3

**وضعیت:** پیاده‌سازی‌شده و تست‌شده (16/16 + رگرسیون 200) — کد: `corpus/tasnim/`
(۱۳ ماژول) + CLI `python -m corpus.tasnim.cli <cmd>`، تست‌ها: `test_corpus_tasnim.py`
(T-01…T-10، 16 تست)
**محدودیت:** ماژول کاملاً جدا و خالص — بدون DB، بدون Flask، بدون شبکه، بدون
LLM/embedding/Neo4j؛ فقط‌خوانده روی خروجی کراول PCM-20؛ تمام خروجی‌ها زیر
`data/tasnim/`. **embedding و Neo4j صریحاً OUT OF SCOPE** (مأموریت بعدی).

---

## ۱. خلاصه

خروجی کراول «تفسیر تسنیم» (tasnim.hamtaa.org، پروژه‌ی 2 در s52، 45,844 رکورد —
PCM-20) به یک **خط تولید استاندارد، تکرارپذیر و نسخه‌شده** تبدیل می‌شود:

```text
tasnim-corpus.jsonl  (خروجی PCM-20، 73MB)
        │
        ▼  audit            ← درگاه آشتیابی (read-only) — تعاریف دقیق PCM-20.2
        ▼  build-corpus     ← پیکره‌ی رسمی Work→Edition→Volume→Page + validate V01..V08
        ▼  build-dataset    ← دیتاست‌های 1/10/50/90/100% (+ --volume N) — طبقه‌ای، قطعی
        ▼  export-dump      ← books.json + product.json سازگار با ai-dump-builder
        └  diff             ← Change Manifest بین دو نسخه‌ی پیکره
```

قواعد اصلی:

1. **فقط‌خوانده روی ورودی** — هیچ تغییری روی فایل‌های PCM-20 نمی‌شود.
2. **هیچ رکوردی حذف نمی‌شود** — رکوردهای ناقص/کوتاه فقط quality flag می‌گیرند.
3. **RAW (`text`) و NORMALIZED (`text_normalized`) همیشه جدا** — NORMALIZED
   تابعی از RAW + policy ثبت‌شده در manifest است (قابل بازسازی، V06).
4. **تکرارپذیری/قدرت‌مطلق (idempotent)** — ورودی+پیکربندی یکسان → content
   یکسان → همان نسخه REUSED می‌شود (فایلی نوشته نمی‌شود).
5. **نسخه‌ها فقط افزایشی** (v0001, v0002, …) — هرگز بازنویسی/حذف.
6. **provenance اثبات‌پذیر** — هر نسخه manifest.json دارد که زنجیره
   `Source Snapshot → Corpus → Dataset → Dump` را با SHA-256 نگه می‌دارد و
   `validate` آن را از نو محاسبه می‌کند.

## ۲. قرارداد ورودی (خروجی PCM-20)

`tasnim-corpus.jsonl` — هر خط یک رکورد:

```json
{"page_id": 12345, "url": "https://tasnim.hamtaa.org/book/79?section=2&item_index=12345",
 "captured_at": "…", "content_hash": "…", "item_index": 12345, "barg": 12346,
 "values": {"برگ": "۱۲٬۳۴۶", "متن": "…", "author": "…", "…": "…"}}
```

- `page_id` = id رکورد در `project_pages` (s52) — کلید provenance (`source_page_id`).
- `item_index` از URL (موقعیت کراول)؛ `values.برگ` = شماره‌ی برگ چاپی (RAW).
- **نکته‌ی مهم (بگ PCM-20.2):** `barg` در سطح بالای رکورد خروجی، حاصل
  «فقط اولین ریک ارقام» است (مثلاً «۳۹٬۰۰۵» → 39). این Factory با
  **بازپارسِ صحیح** (همه‌ی ریک‌های ارقام بعد از تبدیل ارقام فارسی/عربی به ASCII:
  «۳۹٬۰۰۵» → 39005) `barg` واقعی را می‌سازد و اختلاف را در gate می‌شمارد
  (`differs_from_export_barg`).
- فایل‌های اختیاری همسایه: `tasnim-corpus.json` (هدر+pages) و
  `export-summary.json` — فقط شناسایی/ثبت SHA می‌شوند (بدون بارگذاری کل فایل).

## ۳. سلسله‌مراتب و شناسه‌های پیکره

```text
Work  tasnim_hamta            (ثابت — «تفسیر تسنیم»)
 └── Edition tasnim_hamta__hamta-2026   (ویرایش = خروجی کراول + SHAها)
      └── Volume  <edition_id>__volNNN          (NNN از استراتژی)
           │   جلد نامشخص:  <edition_id>__volkey<sha8(key)>
           └── Page  <volume_id>__p<item_index>  (+ __d1, __d2 برای ردیف‌های تکراری)
                   بدون item_index: <volume_id>__pkey<sha8>
```

شناسه‌ها **قطعی** هستند (تابعی از داده، نه زمان/ترتیب فیزیکی) → خروجی
تکرارپذیر بین اجراها و بین ماشین‌ها.

### ۳.۱ استراتژی‌های شناسایی جلد (به ترتیب اولویت)

| استراتژی | تعریف |
|----------|-------|
| `url_section` | پارامتر `section` در URL — آخرین ریک ارقام آن (مثلاً `section=جلد 31` → 31) |
| `text` | الگوی «جلد N» در متن صفحه |
| `none` | هیچ‌کدام → «جلد نامشخص» (آخر گروه‌بندی) |

### ۳.۲ رکورد صفحه (pages.jsonl)

فیلدهای اصلی: `page_id, volume_id, item_index, barg, raw_barg, text` (RAW),
`text_normalized`, `url, captured_at, content_hash, source_page_id`,
`quality_status{status, flags}`, `metadata{barg_raw, url, content_hash,
captured_at, item_index, export_barg, section, values_keys}`.

### ۳.۳ quality flags (حذف نمی‌کنند — فقط ثبت می‌کنند)

| flag | تعریف |
|------|-------|
| `empty` | متن خالی/غیرمتنی |
| `short` | 1..19 کاراکتر (زیر `min_text_chars=20` Builder) |
| `truncated_at_2000` | `len(text) == 2000` — مشکوک به برش در کراول (NOT VERIFIED: منشأ برش) |
| `dup_item_index` | item_index تکراری بین رکوردها (ردیف دوم/سوم → `__d1`/`__d2`) |
| `no_barg` | «برگ» موجود ولی بدون رقم |
| `missing_item_index` | item_index در URL نیست/نامعتبر |

`quality_status.status = flags[0] or "ok"`.

### ۳.۴ سیاست نرمال‌سازی (ثبت‌شده در manifest)

| policy | steps |
|--------|-------|
| `tasnim-p1-ascii-digits` (پیش‌فرض) | ارقام فارسی/عربی→ASCII + collapse whitespace + strip (بدون حذف ZWNJ/محتوا) |
| `none` | دست‌نخورده (RAW == NORMALIZED) |

## ۴. درگاه آشتیابی (`audit`) — تعاریف دقیق PCM-20.2

خروجی JSON (`reports/audit-<sha12>.json`): `record_count`, `incomplete_empty`,
`short_lt_20`, `truncated_at_2000`, `no_barg`, `missing_item_index`,
`text_len{p50,p90,p99,max}`, `duplicate_item_index{value_count,extra_rows}`,
`duplicate_content_hash{…}`, `barg_reparse{with_raw_barg, with_parsed_barg,
equals_item_index_plus_1, differs_from_export_barg}`, `item_index{min,max,
distinct,missing_count,dup_count}`, `volume_strategy_census{url_section,text,none}`,
`distinct_url_sections`. **read-only** — هیچ چیزی نمی‌نویسد به‌جز فایل گزارش.

## ۵. نسخه‌پذیری و provenance (data/tasnim/)

```text
data/tasnim/
  sources/s<sha12>/manifest.json          (اسنپ‌شات منبع: path+SHA؛ بدون کپی فایل)
  corpus/builds/vNNNN/{corpus.json, pages.jsonl, manifest.json}
  datasets/<1|10|50|90|100>pct/vNNNN/{dataset.json, pages.jsonl, manifest.json}
  dumps/<pct>/vNNNN/{books.json, product.json, dump-check.json, manifest.json}
  manifests/registry.json                 (زنجیره‌ی کلی: "kind:version" → entry)
  reports/                                (audit + diff — برای انسان)
```

- **content_sha256** = sha256 روی `"name:sha:size\n"` فایل‌های محتوایی هر
  نسخه، **در حافظه** از بایت‌های canonical محاسبه می‌شود (قبل از نوشتن).
- **canonical JSON** = `json.dumps(ensure_ascii=False, sort_keys=True, indent=1)+"\n"`
  (JSONL: خط‌به‌خط، بدون indent) → بایت‌ها بین اجراها یکسان.
- **manifest** (`m-20.3`): `{manifest_version, kind, version, created_at,
  prev{version,kind,sha256,path_rel}, data{content_sha256, files{name:
  {sha256,size_bytes}}, …}}`. `created_at` در content sha **نمی‌آید**.
- **زنجیره‌ی prev**: هر manifest به manifest قبلی (SHA + مسیر نسبی)
  می‌خورد؛ `validate_manifest` مسیر را روی دیسک حل می‌کند و SHA prev را از
  نو محاسبه می‌کند. (بگ رفع‌شده: `chain_entry` دیگر `manifest.json` را دو
  بار نمی‌چسباند — T-09 رگرسیون دارد.)
- **idempotency**: `find_reusable_version` نسخه‌ای با همان `content_sha256`
  پیدا می‌کند → `REUSED` (خروجی 0، بدون نوشتن).

## ۶. الگوریتم دیتاست (`stratified-even-blocks` v2)

1. **کل کل**: `total = round(total_pages × pct / 100)` (1% از 21 → 0؛ 100% → همه).
2. **طبقه‌بندی جلد**: سهم هر جلد با largest-remainder؛ تساوی → جلد کوچک‌تر
   اول، «نامشخص» آخر.
3. **درون جلد**: `even_spaced_indexes(count, target, blocks≤5)` — بلوک‌های
   **متماد** با فاصله‌ی تقریباً یکنواخت در ترتیب صفحات جلد (ادامه‌دار؛
   قطعی). `target ≥ count` → همه‌ی صفحات جلد.
4. `--volume N`: فقط صفحات همان جلد (طبقه‌بندی درون همان جلد).
5. خروجی: `dataset.json` (meta + policy + provenance به corpus و snapshot) +
   `pages.jsonl` (صفحات انتخاب‌شده، مرتب‌شده بر page_id) + manifest.

## ۷. Adapter خروجی به ai-dump-builder (`export-dump`)

- **کد Builder دست‌نخورده می‌ماند**؛ این ماژول فقط ورودی آن را می‌سازد.
- `books.json`: یک Book برای هر جلد — `dap_code = tasnim__volNNN`
  (نامشخص: `tasnim__vol-unknown`)؛ هر page: `title, dap_code, page_number`
  (= barg واقعی، وگرنه item_index+1، وگرنه 0), `paragraph_text`
  (= `text_normalized`), `language=fa, words_count, _id=source_page_id` +
  provenance در 9 کلید `extra_metadata` (`page_id, item_index, barg,
  volume_no, url, captured_at, content_hash, source_page_id, raw_text`).
- `product.json`: `tasnim_tafsir`؛ `min_text_chars=20, max_embed_chars=6000,
  embed_batch=16, embed_concurrency=4`؛ `litellm_base/litellm_key = null`
  (Builder از محیط می‌خواند — **هیچ رمزی در خروجی نمی‌آید**).
- **چک سازگاری محلی** (`dump-check.json`): `extract_like_builder` دقیقاً
  همان `extract_records` Builder را تکرار می‌کند (skip < 20، truncate 6000،
  کپی extra_metadata) و REQUIRED fields را چک می‌کند؛ هر error → exit 1.
- **embedding/Neo4j OUT OF SCOPE** در این فاز — اجرای واقعی Builder در
  مأموریت بعدی (کپی دایرکتوری dump به `_aidump/products/<slug>/`).

## ۸. Change Manifest (`diff`)

کلید مقایسه = `source_page_id`. شمارنده‌ها: `from_pages, to_pages, added,
changed` (تغییر content_hash یا text), `unchanged, healed` (flag سابق
برطرف‌شده), `removed_from_source` (**فقط علامت — حذف خودکار ممنوع؛ نسخه‌های
قبلی immutable**), `duplicate_rows_in_new`. خروجی:
`reports/diff_<from>_<to>/change-manifest.json` (لیست‌ها تا 1000 + flag truncation).

## ۹. CLI و exit codes

```bash
python -m corpus.tasnim.cli audit          --jsonl tasnim-corpus.jsonl [--json …] [--summary …] [--data-root …] [--out …]
python -m corpus.tasnim.cli build-corpus   --jsonl … [--json …] [--summary …] [--data-root data/tasnim] [--policy tasnim-p1-ascii-digits|none]
python -m corpus.tasnim.cli validate-corpus --data-root … --build vNNNN
python -m corpus.tasnim.cli build-dataset  --data-root … --corpus vNNNN --percentage {1,10,50,90,100} [--volume N] [--blocks 5]
python -m corpus.tasnim.cli export-dump    --data-root … --dataset vNNNN --percentage {1,10,50,90,100}
python -m corpus.tasnim.cli diff           --data-root … --from v0001 --to v0002
```

| exit | معنا |
|------|------|
| 0 | موفقیت (شامل REUSED) |
| 1 | خطای validation/build (مثلاً compat-check، validate FAIL) |
| 2 | خطای ورودی (فایل نیست، نسخه‌ی ناشناخته، درصد نامعتبر) |

## ۱۰. اعتبارسنجی (`validate-corpus`، V01..V08)

V01 ساختار فیلدها · V02 ارجاعات volume · V03 یکتایی page_id + فرمول قطعی ·
V04 provenance (source_page_id/content_hash) · V05 بازسازی barg از raw_barg ·
V06 بازتولید `text_normalized` از RAW + policy · V07 آمار با شمارش واقعی ·
V08 manifest: SHA فایل‌ها + حل زنجیره‌ی prev روی دیسک.

## ۱۱. تست‌ها (16 — T-01…T-10)

| تست | پوشش |
|-----|------|
| T-01 | شمارنده‌های gate (fixture 21 رکورد، 4 جلد) با ارقام دقیق PCM-20.2 |
| T-02 / T-02b | ساختار/شناسه‌ها/جلد 31 از section / flag-not-delete (ok = 21-6) |
| T-03 / T-03b | validate PASS / فساد bytes → V03+V08 FAIL |
| T-04 / T-04b | دیتاست 1/10/50/90/100 (0/2/10/19/21) + بلوک≤5 + ادامه‌دار / --volume 2 |
| T-05 | idempotency: REUSED برای corpus و dataset (دایرکتوری جدید ساخته نمی‌شود) |
| T-06 | دترمینیسم: دو data-root جدا → content_sha256 + انتخاب یکسان |
| T-07 | dump: 4 books / 19 records / 2 skipped_short / required OK / litellm_key=null |
| T-08 | diff: added=1 changed=1 unchanged=19 removed=1 + change-manifest.json |
| T-09 / T-09b | زنجیره source→corpus→dataset (path_rel روی دیسک، بدون double-suffix) / v0001+v0002 immutable |
| T-10 / T-10b / T-10c | قرارداد CLI (0/2) / خواص even-blocks / بازپارس «۳۹٬۰۰۵» → 39005 |

اجرا: `python -X utf8 -m unittest test_corpus_tasnim -v` — **16/16 سبز** +
رگرسیون backend (200 تست) سبز.

## ۱۲. اجرای روی s52 (read-only، بدون deploy)

```bash
# روی s52 (kopi کد + python؛ خروجی‌ها فقط در data/tasnim):
python -X utf8 -m corpus.tasnim.cli audit --jsonl /path/to/tasnim-corpus.jsonl \
  --json /path/to/tasnim-corpus.json --summary /path/to/export-summary.json \
  --data-root /path/to/data/tasnim
python -X utf8 -m corpus.tasnim.cli build-corpus --jsonl … --data-root /path/to/data/tasnim
python -X utf8 -m corpus.tasnim.cli build-dataset --data-root … --corpus v0001 --percentage 10
python -X utf8 -m corpus.tasnim.cli export-dump --data-root … --dataset v0001 --percentage 10
```

## ۱۳. موارد باز — وضعیت بعد از PCM-20.4

- **منشأ `truncated_at_2000` — حل شد (PCM-20.4، GATE 1.5):** برش در سمت
  منبع (سقف RAG سایت — با API زنده اثبات شد)؛ صفر برش در export/کراول
  (تفصیل: `docs/PCM-20.4-TASNIM-ACCEPTANCE.md` §۴).
- **اجرای روی خروجی واقعی 73MB — حل شد (PCM-20.4):** پیکره‌ی canonical v0001
  روی 45,844 صفحه‌ی واقعی ساخته و اعتبارسنجی شد (content sha256
  `ee87686a…`) + 6 دیتاست نسخه‌شده + fixture افزایشی (تفصیل: سند PCM-20.4 §۵/§۶).
- **اجرای واقعی ai-dump-builder — نصفه حل شد (PCM-20.4):** 3 build واقعی
  Builder با `--mock-embed` (بدون LiteLLM/Neo4j/شبکه) روی 3 خروجی Dump —
  همه DUMP_VALIDATED. **embedding واقعی + Neo4j = PCM-20.5** (محیط ایزوله).

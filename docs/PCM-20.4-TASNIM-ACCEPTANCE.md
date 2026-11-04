# PCM-20.4 — پذیرش عملی و اجرای end-to-end زنجیره‌ی داده‌ی تسنیم

**وضعیت:** کامل‌شده و پذیرفته‌شده (QC A/B/C PASS + 216 تست سبز) — خروجی‌ها: `data/tasnim/pcm20_4/`
**هدف:** اثبات صحت زنجیره‌ی
`Real Snapshot → Canonical Corpus → Versioned Dataset → AI Dump Builder Input`
با provenance کامل (SHA-256 در هر گام، زنجیره‌ی `prev` در manifestها).
**مرجع:** قرارداد خط تولید = `docs/PCM-20.3-TASNIM-FORFACTORY.md` (c-20.3)؛ ممیزی منبع = PCM-20.2.

---

## ۱. خلاصه و ساختار مأموریت

| مرحله | کار | نتیجه |
|-------|-----|-------|
| Stage 1 | اعتبارسنجی اسنپ‌شات واقعی (SHA + JSON↔JSONL + آمار) | **ALL_MATCH** |
| GATE 1.5 | منشأ برش 2000 کاراکتر (read-only روی خروجی) | **PASS** — برش سمت منبع (RAG cap سایت) |
| 20.4-A | ساخت پیکره‌ی واقعی 45,844 صفحه + idempotency + cross-root + QC | **PASS** |
| 20.4-B | 6 دیتاست (1/10/50/90/100 + `--volume 56`) + QC + incremental fixture | **PASS** |
| 20.4-C | `export-dump` + اجرای **واقعی** ai-dump-builder (فقط `--mock-embed`) | **PASS** (3 build، DUMP_VALIDATED) |
| تست | رگرسیون 200 + تاست‌های T (16) — بدون هیچ skip | **216/216 سبز** |

## ۲. معماری کلی زنجیره (PCM-20)

```text
tasnim.hamtaa.org (سایت، RAG cap = 2000 کاراکتر)
        │  PCM-20: export read-only از s52 (thesaurus.db → JSON/JSONL)
        ▼
tasnim-corpus.json / .jsonl / export-summary      [Source Snapshot — immutable]
        │  audit  ← درگاه آشتیابی (read-only، تعاریف PCM-20.2)
        ▼  build-corpus (c-20.3)
corpus/builds/vNNNN   {corpus.json, pages.jsonl, manifest.json}   [Canonical Corpus]
        │  build-dataset (stratified-even-blocks v2)
        ▼
datasets/<pct>/vNNNN  {dataset.json, pages.jsonl, manifest.json}  [Versioned Dataset]
        │  export-dump (adapter — کد Builder دست‌نخورده)
        ▼
dumps/<pct>/vNNNN     {books.json, product.json, dump-check.json, manifest.json}
        │  کپی به دایرکتوری product جدا → python -m builder build --mock-embed
        ▼
builder-input/tasnim_tafsir_<case>/builds/<build_id> {chunks.jsonl, mapping.json, manifest.json}
        (ai-dump-builder — commit 1c500a64 — فقط embedding با MockEmbedder)
```

قواعد (از c-20.3، اینجا اجرا و اثبات شد): فقط‌خوانده روی ورودی؛ هیچ رکوردی حذف
نمی‌شود (فقط quality flag)؛ RAW و NORMALIZED جدا؛ idempotent (REUSED)؛ نسخه‌ها
فقط افزایشی و immutable؛ provenance با SHA-256.

## ۳. Stage 1 — اعتبارسنجی اسنپ‌شات واقعی

فایل‌ها از خروجی PCM-20 (read-only از `thesaurus.db` روی s52، پروژه‌ی 2
«تفسیر تسنیم همتا»، `exported_at_utc = 2026-11-03T16:03:13+00:00`) در
`data/tasnim/pcm20_4/source-snapshot/` ثبت شد.

| فایل | size (bytes) | SHA-256 (شروع) | با مرجع مأموریت |
|-------|-------------|----------------|------------------|
| `tasnim-corpus.json` | 72,959,214 | `cee2c08aae1862d0…` | ✅ |
| `tasnim-corpus.jsonl` | 72,906,133 | `fd927b663733fe05…` | ✅ |
| `pcm20_2_audit.json` | 63,188 | `db6c30f415372c6a…` | ✅ |

- **JSON↔JSONL:** هر دو 45,844 رکورد؛ ترتیب همه‌ی 7 فیلد کلیدی (page_id, url,
  item_index, barg, captured_at, content_hash, text) یکسان؛ **0 اختلاف**.
- **شمارنده‌های پروژه (از هدر خروجی):** saved 45,838 / skipped 20 / failed 52,025.
- آمار PCM-20.2 از نو محاسبه و تطبیق خورد (`validation/stage1_snapshot_audit.json`).

## ۴. GATE 1.5 — برش 2000 کاراکتر (منشأ: سمت منبع)

تحلیل read-only روی 45,844 متن (`validation/gate1_5_truncation_conclusion.json`):

- رکوردهای دقیقاً `len == 2000`: **28** (0.06%) — flag `truncated_at_2000`.
- histogram طول: `{0: 35, 1-19: 12366, 20-99: 10861, 100-499: 4688, 500-1999: 17866, 2000: 28, >2000: 0}`
  → هیچ رکوردی بیش از 2000 نیست و در بازه‌ی 1800–1999 **هیچ پیک مصنوعی** دیده
  نمی‌شود (هر باکته‌ی 100تایی: 124 تا 290 رکورد) — یعنی متن‌ها طبیعی‌اند و 28 رکورد
  دقیقاً در مرز تمام شده‌اند.
- دم (tail) این 28 رکورد: 10 تا با پانکچویشن، 18 تا در وسط متن (برخی در وسط
  آیه‌ی ﴿…﴾ یا پایان جدول رقم) — الگوی «برش ناگهانی» در مرز، نه پایان طبیعی جمله.
- کنترل: در 45,781 متن کوتاه‌تر از 2000 نسبت پانکچویشن دم 18,962/45,781 است —
  تفاوت باکته‌ها شلوغی طبیعی را نشان می‌دهد.
- **نتیجه:** برش از **سمت منبع** (لیمیت RAG سایت، تأییدشده با API زنده در
  PCM-20.2) است؛ **صفر** برش در لایه‌ی export/crawl. Flag فقط ثبت می‌شود (حذف ممنوع).

## ۵. مرحله‌ی 20.4-A — پیکره‌ی واقعی (`build-corpus`)

اجرا (روی `.venv` پروژه، Python 3.13.15):

```bash
python -X utf8 -m corpus.tasnim.cli audit --jsonl data/tasnim/pcm20_4/source-snapshot/tasnim-corpus.jsonl \
  --json  data/tasnim/pcm20_4/source-snapshot/tasnim-corpus.json \
  --summary data/tasnim/pcm20_4/source-snapshot/export-summary.json --data-root data/tasnim/pcm20_4
python -X utf8 -m corpus.tasnim.cli build-corpus --jsonl … --data-root data/tasnim/pcm20_4
python -X utf8 -m corpus.tasnim.cli validate-corpus --data-root data/tasnim/pcm20_4 --build v0001
```

**Corpus v0001** (canonical — از `corpus/builds/v0001/manifest.json`):

- 45,844 صفحه در **6 جلد**؛ policy `tasnim-p1-ascii-digits`
- `content_sha256 = ee87686ac49ce9c08a4a492f4f54c23ace571bb8f048aa8a0a863bece3d542d8`
- `manifest sha256 = e0b0c2cea4e52342f8a924e1c08a45e06d64aa236fcf586b6fc49782c39430fc`
- فایل‌ها: `pages.jsonl` 144,151,230 B (sha `0b31533a…`) · `corpus.json` 15,837 B (sha `97bc4d9a…`)
- `validate-corpus` → **PASS** (V01..V08)

| جلد | id | صفحات | برگ (span) | item_index (span) | empty | short |
|-----|----|--------|-----------|-------------------|-------|-------|
| 1 | `…__vol001` | 9 | 2–27 | 0–2 | 0 | 1 |
| 12 | `…__vol012` | 22 | 3650–11205 | 3649–11205 | 0 | 6 |
| 47 | `…__vol047` | 9,391 | … | 0–55698 | 5 | 2,449 |
| 56 | `…__vol056` | 29,689 | … | 59591–89279 | 26 | 8,102 |
| 80 | `…__vol080` | 767 | … | 90311–91077 | 0 | 216 |
| نامشخص | `…__volkeyd531f422` | 5,966 | — | — | 4 | 1,592 |

- استراتژی شناسایی جلد: `url_section` 39,878 / `text` 0 / `none` 5,966.
- **quality census کل:** `{ok: 33399, short: 12366, empty: 35, no_barg: 35,
  dup_item_index: 18, truncated_at_2000: 28, missing_item_index: 0}`
- `item_index`: count 45,844 / distinct 45,835 / 9 رکورد تکراری (ردیف دوم → `__d1`)؛
  `barg_reparse`: 45,809 با برگ قابل‌پارس؛ 45,800 برابر `item_index+1`؛
  44,801 با مقدار export متفاوت (بگ parse_barg PCM-20.2 در Factory اصلاح شد).
- `content_hash` تکراری: **0**.
- **QC A:** تمام بررسی‌های شمارشی (census/SHA/span/فرمول id/provenance) PASS.
- **Idempotency:** اجرای دوم → `REUSED` (فایلی نوشته نشد، همان v0001).
- **Cross-root determinism:** اجرا در data-root دوم → `content_sha256` و انتخاب
  صفحات **دقیقاً یکسان**.

## ۶. مرحله‌ی 20.4-B — دیتاست‌های نسخه‌شده (`build-dataset`)

الگوریتم `stratified-even-blocks` v2 (شرح کامل: PCM-20.3 §6): سهم هر جلد با
largest-remainder از کل `round(total × pct/100)`؛ داخل جلد بلوک‌های متما
(≤5 بلوک) با فاصله‌ی تقریباً یکنواخت در ترتیب صفحات.

```bash
python -X utf8 -m corpus.tasnim.cli build-dataset --data-root data/tasnim/pcm20_4 --corpus v0001 --percentage {1|10|50|90|100}
python -X utf8 -m corpus.tasnim.cli build-dataset … --percentage 10 --volume 56   # دیتاست تک‌جلد
```

| دیتاست | نسخه | صفحات | per-volume (1/12/47/56/80/نامشخص) | flags (ok/short/empty/dup/trunc) | content sha (شروع) |
|--------|------|-------|-----------------------------------|----------------------------------|--------------------|
| 1% | v0001 | 458 | 0/0/94/297/8/59 | 338/116/0/5/0 | `a407021e…` |
| 10% | v0001 | 4,584 | 1/2/939/2969/77/596 | 3402/1166/2/10/5 | `7de515a6…` |
| 10% (جلد 56) | v0002 | 2,969 | فقط vol056: 2,969 | 2193/770/2/0/4 | `11ab83ce…` |
| 50% | v0001 | 22,922 | 5/11/4,696/14,844/383/2,983 | 16858/6025/12/14/15 | `7c15be3f…` |
| 90% | v0001 | 41,260 | 8/20/8,452/26,720/690/5,370 | 29991/11193/33/17/28 | `8ef9aab8…` |
| 100% | v0001 | 45,844 | همه (100% هر جلد) | = census پیکره | `37673c3d…` |

- **پوشش درون‌جلد** (10%): جلد 1 → 11.11%، 12 → 9.09%، 47 → 10.00%، 56 →
  10.00%، 80 → 10.04%، نامشخص → 9.99% (پارامترهای جلد کوچک ریشه در
  largest-remainder + بلوک‌های صحیح است؛ انتظار می‌رود ≈ pct±1).
- `text_len` (p50/p90/max): 1% → 256/1806/1999 · 10% → 200/1763/2000 ·
  50% → 101/1740 · 90% → 60/1701 · 100% → 64/1710/2000.
- **QC B PASS:** شمارنده‌ها با بازتولید مستقل تطبیق؛ زنجیره‌ی manifest
  (dataset → corpus v0001 → snapshot `sfd927b663733`) روی دیسک حل شد؛
  اجرای تکراری → REUSED؛ `--volume 56` فقط 2,969 صفحه‌ی همان جلد (volume_scope
  در `dataset.json`).
- **Incremental fixture** (اثبات رفتار ارتقا، روی fixture 21 رکورد):
  - v0002 (21 صفحه): content `8a1cad10…` / manifest `14232e17…`
  - v0003 (22 صفحه): content `0d86db16…` / manifest `dbf35948…`
  - `diff v0002→v0003`: **added 1، changed 2، unchanged 18، healed 0،
    removed_from_source 1، duplicate_rows_in_new 0**
    (`reports/diff_v0002_v0003/change-manifest.json`، sha `7b302035…`)
  - صفحه‌ی «حذف‌شده» در change-manifest با یادداشت
    **«حذف خودکار ممنوع؛ نسخه‌ی قبلی immutable»** ثبت شد — هیچ نسخه‌ای دست‌نخورده
    باقی ماند؛ v0001 واقعی بعد از همه‌ی اجراها **بایت‌به‌بایت یکسان** بود.

## ۷. مرحله‌ی 20.4-C — `export-dump` + اجرای واقعی ai-dump-builder

### ۷.۱ Adapter (`export-dump`) — جدول تطبیق فیلدها

کد Builder **دست‌نخورده** است؛ `corpus/tasnim/dump.py` فقط ورودی آن را می‌سازد:

| books.json (adapter) | chunks.jsonl (خروجی Builder) |
|----------------------|-------------------------------|
| `book.title` | `book_name` |
| `page.dap_code` (`tasnim__volNNN` / `tasnim__vol-unknown`) | `book_id` |
| `page.page_number` (= barg واقعی ← item_index+1 ← 0) | `page_number` |
| `page.paragraph_text` (= `text_normalized`) | داخل `chunk_text` (قالب: `Metadata: book_name:…\nbook_id:…\npage_number:…\n-----\nContent: …`) |
| `page._id` | `source_id` |
| `page.language` / `words_count` | هم‌نام |
| 9 کلید `extra_metadata` (`page_id, item_index, barg, volume_no, url, captured_at, content_hash, source_page_id, raw_text`) | هم‌نام — فقط اگر مقدار `None` نباشد |
| — | `chunk_id` (0)، `link` (`book://<book_id>#p<page_number>`)، `_fp` (فingerprint)، `embedding` |

قواعد `extract_records` Builder که adapter محلی دقیقاً تکرار می‌کند
(`dump-check.json`): skip اگر `paragraph_text < min_text_chars(20)`؛ truncate
اگر `> max_embed_chars(6000)`؛ REQUIRED = `book_id, book_name, chunk_text,
chunk_id, page_number, embedding`.

### ۷.۲ سه خروجی dump ساخته‌شده

| dump | از dataset | کتاب‌ها | صفحات | records | skipped_short | content sha |
|------|-----------|--------|-------|---------|---------------|-------------|
| `dumps/10pct/v0001` | 10pct **v0002** (جلد 56) | 1 (`tasnim__vol056`) | 2,969 | 2,197 | 772 | `062ec699…` |
| `dumps/10pct/v0002` | 10pct v0001 | 6 | 4,584 | 3,416 | 1,168 | `3ef895e3…` |
| `dumps/100pct/v0001` | 100pct v0001 | 6 | 45,844 | 33,443 | 12,401 | `d5dc0098…` |

هر سه `dump-check.json` = required OK / 0 truncated.

### ۷.۳ اجرای واقعی Builder (mock-embed فقط)

- ریپو: `server52and53/_aidump` — commit `1c500a6411df5edca31be0616ca707cc55910417`
- **هر مرحله در دایرکتوری product جدا** زیر `data/tasnim/pcm20_4/builder-input/`
  (`tasnim_tafsir_<case>/books.json + product.json`) — کالکشن عملیاتی
  `falsafe_siasi` در `products/` Builder **هرگز لمس نشد**.
- دستور (cwd = ریشه‌ی `_aidump`):
  ```bash
  python -m builder build --product <dir> --mock-embed --no-embed-reuse
  python -m builder validate --product <dir> --build <build_id>
  ```
- **MockEmbedder** (داخل کد Builder، خط 186 `builder/core.py`): embedding قطعی
  از sha256 متن → بردار 1024-بعدی unit؛ کاملاً offline — **بدون LiteLLM،
  بدون شبکه، بدون Neo4j، بدون بارگذاری collection**.

| case | build_id | chunks sha256 | size | records/skipped | validation |
|------|----------|---------------|------|-----------------|------------|
| vol56 | `qwen3-embed-06b_20261104-041446` | `ab3bf5660b22c3fcef22aa43f99ecc6b83af998e74fd68ff6894d553e8fa81ff` | 57.5 MB | 2,197 / 772 | DUMP_VALIDATED (in-build + validate) |
| 10pct | `qwen3-embed-06b_20261104-041457` | `0b7f40b045766c24305b3c0c3eb2dfd6f8a585f27ba8081272491fc43be47e33` | 89.7 MB | 3,416 / 1,168 | DUMP_VALIDATED |
| 100pct | `qwen3-embed-06b_20261104-041514` | `f9debdd32142c78ab842cf5ece625a7721cfca47011d4ecc562cc9d1d8e02b79` | 872.2 MB | 33,443 / 12,401 | DUMP_VALIDATED |

- mapping.json در هر سه: sha `0bd9b8a73858306f5ef17da12bcc6758e80286fdef21f9ab820a7a7034d4002b`
- current pointer هر product به build جدید switch شد (`flip_current`).
- toolkit commit در لحظه‌ی اجرا: `8db3b60a2ce1a9a4dcead4a6f62dd7f61dff9151`.

> **صریح درباره‌ی «آیا dump نهایی واقعاً ساخته شد؟»:** بله — هر سه خروجی
> (از جمله 100% با **33,443 رکورد / 872.2 MB**) `chunks.jsonl` واقعی با
> manifest و mapping روی دیسک ساخته و اعتبارسنجی شدند (`backend=mock`).
> آنچه **نسخه‌ی آزمایشی** است، بردارهای embedding (MockEmbedder) هستند —
> embedding واقعی + Neo4j خارج از این مأموریت است (PCM-20.5).

### ۷.۴ QC C (22 بررسی) PASS

تطبیق records/skipped با `dump-check.json`؛ REQUIRED fields؛ dim=1024؛
`_fp` وجود دارد / `_embed_input` حذف شده؛ provenance 9 کلید در رکوردها؛
repo Builder بدون تغییر جدید (فقط 3 فایل WIP از قبل — mtime 2026-10-09 —
متعلق به اجراهای ما نیست).

## ۸. قرارداد نسخه‌پذیری (نمای کلی)

نسخه‌پذیری کامل در PCM-20.3 §5 تعریف شده؛ اینجا اثبات عملی شد:

- `manifests/registry.json` — زنجیره‌ی واحد: کلید `"kind:version"` (و
  `dataset:<pct>:version`، `dump:<pct>:version`) → `{content_sha256, sha256,
  prev refs}`. در پایان مأموریت **17 entry** (3 corpus، 6 dataset، 3 dump،
  3 source-snapshot).
- هر manifest → `prev{kind, version, sha256, path_rel}`؛ `validate_manifest`
  مسیر را روی دیسک حل و SHA prev را از نو محاسبه می‌کند.
- **REUSED:** ورودی+پیکربندی یکسان → همان `content_sha256` → خروجی `REUSED`
  بدون نوشتن (در همه‌ی 20.4-A/B اثبات شد).
- **Immutability:** هیچ نسخه‌ای بازنویسی/حذف نشد؛ v0001 واقعی بعد از همه‌ی
  اجراها بایت‌به‌بایت یکسان بود.

نمونه از registry:

```json
"dataset:10pct:v0001": {
  "content_sha256": "7de515a69eeeb47438edaae14ac26a4b57ff991fe461dcc102ef8137e132456a",
  "corpus": "v0001",
  "sha256": "cdf2868abc15681e1bc764e94284422444a2c6ac52c60706f458171fa73bdcc0"
},
"dump:100pct:v0001": {
  "content_sha256": "d5dc00980b8c95a0b878890d0a2e45dda85634f1d9c3af1a1a7ad74644a8a5e4",
  "dataset": "v0001",
  "sha256": "36787563fa0e0fdcfc7caf039eb1e0c625e04ce39498881b34716d5d027c301d"
}
```

## ۹. چیدمان داده‌ها (`data/tasnim/pcm20_4/`)

```text
source-snapshot/  tasnim-corpus.json(.jsonl), export-summary.json, pcm20_2_audit.json
sources/          sfd927b663733/ (اسنپ‌شات واقعی) + 2 اسنپ‌شات fixture
corpus/builds/    v0001 (واقعی) + v0002/v0003 (fixture incremental)
datasets/         1pct/ 10pct/(v0001,v0002) 50pct/ 90pct/ 100pct/
dumps/            10pct/(v0001,v0002) 100pct/v0001  → books.json + product.json + dump-check.json
builder-input/    tasnim_tafsir_{vol56,10pct,100pct}/  → builds/<build_id>/{chunks.jsonl,mapping.json,manifest.json,build.log}
manifests/        registry.json
reports/          audit-<sha12>.json + diff_v0002_v0003/change-manifest.json
validation/       stage1_snapshot_audit.json · gate1_5_truncation_conclusion.json
                  audit_gate.json · builder-run.json
```

هیچ داده‌ی واقعی در Git نمی‌رود (`data/` gitignored) — فقط SHAها در
registry/manifest و گزارش‌ها.

## ۱۰. نمونه‌ی رکوردها (verbatim از خروجی‌های واقعی)

### 10.1 رکورد صفحه — `corpus/builds/v0001/pages.jsonl` (اولین خط)

```json
{
 "barg": 2,
 "captured_at": "2026-10-25 16:50:40",
 "content_hash": "c5733f9083ca4b93139e0909bd1dbb268b275ffe9d289c8aa86044284eaffb38",
 "item_index": 2,
 "metadata": {
  "barg_raw": "برگ ۲",
  "export_barg": 2,
  "item_index": 2,
  "section": "تفسیر تسنیم جلد (1)",
  "url": "https://tasnim.hamtaa.org/payload?file_id=tasnim&item_index=2&section=…",
  "values_keys": ["ادرس صفحه", "برگ"]
 },
 "page_id": "tasnim_hamta__hamta-2026__vol001__p2",
 "position": 11700,
 "quality_status": { "flags": ["dup_item_index"], "status": "dup_item_index" },
 "raw_barg": "برگ ۲",
 "source_page_id": 11707,
 "text": "بسمه تعالی شأنه موقعیت قرآن …",
 "text_normalized": "بسمه تعالی شأنه موقعیت قرآن …",
 "url": "https://tasnim.hamtaa.org/payload?file_id=tasnim&item_index=2&…",
 "volume": { "volume_id": "tasnim_hamta__hamta-2026__vol001", "volume_no": 1, "volume_title": "جلد 1" },
 "volume_id": "tasnim_hamta__hamta-2026__vol001"
}
```

### 10.2 رکورد کتاب/صفحه — `dumps/10pct/v0001/books.json` (book 0، صفحه‌ی اول)

```json
{
 "dap_code": "tasnim__vol056",
 "language": "fa",
 "page_count": 2969,
 "title": "تفسیر تسنیم جلد 56",
 "pages": [
  {
   "_id": 11702,
   "barg": 55699,
   "dap_code": "tasnim__vol056",
   "item_index": 59591,
   "page_id": "tasnim_hamta__hamta-2026__vol056__p59591",
   "page_number": 55699,
   "paragraph_text": "جدال احسن بودن آیه",
   "raw_text": "جدال احسن بودن آیه",
   "source_page_id": 11702,
   "title": "تفسیر تسنیم جلد 56",
   "url": "https://tasnim.hamtaa.org/payload?file_id=tasnim&item_index=59591&…",
   "volume_no": 56,
   "words_count": 4
  }
 ]
}
```

### 10.3 رکورد نهایی — `chunks.jsonl` (اولین رکورد build واقعی vol56)

```json
{
 "book_id": "tasnim__vol001",
 "book_name": "تفسیر تسنیم جلد 1",
 "page_number": 2,
 "chunk_id": 0,
 "chunk_text": "Metadata: book_name:تفسیر تسنیم جلد 1\nbook_id:tasnim__vol001\npage_number:2\n-----\nContent: بسمه تعالی شأنه …",
 "link": "book://tasnim__vol001#p2",
 "source_id": 11707,
 "language": "fa",
 "words_count": 425,
 "page_id": "tasnim_hamta__hamta-2026__vol001__p2",
 "item_index": 2,
 "barg": 2,
 "volume_no": 1,
 "url": "https://tasnim.hamtaa.org/payload?file_id=tasnim&item_index=2&…",
 "captured_at": "2026-10-25 16:50:40",
 "content_hash": "c5733f9083ca4b93139e0909bd1dbb268b275ffe9d289c8aa86044284eaffb38",
 "source_page_id": 11707,
 "raw_text": "بسمه تعالی شأنه … (متن کامل RAW)",
 "_fp": "0247c9e41a98d1f3d860e6fa5e8fadb3037c8690",
 "embedding": [0.027596, -0.004492, 0.00107, 0.032302, "… 1024 dims (mock)"]
}
```

### 10.4 `product.json` (خروجی adapter — ثابت برای همه‌ی 3 case)

```json
{
 "builds_dir": "builds",
 "collection_name_pattern": "{product}__{model_slug}",
 "dump_filename": "chunks.jsonl",
 "embed_batch": 16,
 "embed_concurrency": 4,
 "export_file": "books.json",
 "extra_metadata": ["page_id","item_index","barg","volume_no","url","captured_at","content_hash","source_page_id","raw_text"],
 "litellm_base": null,
 "litellm_key": null,
 "max_embed_chars": 6000,
 "min_text_chars": 20,
 "models": { "available": ["Qwen3-Embedding-0.6B","Qwen3-Embedding-4B"], "default": "Qwen3-Embedding-0.6B" },
 "product": "tasnim_tafsir",
 "unattended": false
}
```

`litellm_base/litellm_key` عمداً `null` هستند (رمز در کد/خروجی نمی‌آید —
قاعده‌ی ۲.۵ AGENTS.md).

## ۱۱. نمونه‌ی manifest (ساختار `m-20.3`)

```json
{
 "created_at": "2026-11-04T03:34:20Z",
 "data": {
  "config": { "policy": { "id": "tasnim-p1-ascii-digits", "steps": ["ascii-digits", "collapse-whitespace", "strip"] } },
  "content_sha256": "ee87686a…",
  "files": { "corpus.json": {"sha256": "97bc4d9a…", "size_bytes": 15837},
             "pages.jsonl": {"sha256": "0b31533a…", "size_bytes": 144151230} },
  "source": { "jsonl": "…/tasnim-corpus.jsonl", "jsonl_sha256": "fd927b66…", "snapshot": "sfd927b663733" },
  "stats": { "page_count": 45844, "volume_count": 6, "quality_flag_counts": { "…": "…" }, "volumes": [ "…" ] }
 },
 "kind": "corpus",
 "manifest_version": "m-20.3",
 "prev": { "kind": "source-snapshot", "path_rel": "sources/sfd927b663733/manifest.json", "sha256": "7d19796a…", "version": "sfd927b663733" },
 "product": "corpus.tasnim",
 "version": "v0001"
}
```

`created_at` در `content_sha256` نمی‌آید → قدرت‌مطلق.

## ۱۲. تست‌ها

| مجموعه | اجرا | نتیجه |
|--------|------|-------|
| رگرسیون backend (11 ماژول) | `python -m unittest test_api test_projects … test_api_contract -v` (از `.venv`) | **Ran 200 tests — OK** (77.9s؛ 0 fail / 0 err / **0 skip**) |
| تاست‌های Factory (T-01…T-10c) | `python -X utf8 -m unittest test_corpus_tasnim -v` (ریشه‌ی ریپو) | **Ran 16 tests — OK** (3.6s) |

- 10 تست CT که قبلاً به‌دلیل نبود PyYAML skip می‌شدند، با نصب `pyyaml==6.0.3`
  در **venv پروژه** (`.venv` — 64-bit Python 3.13.15؛ نصب global انجام نشد)
  حالا اجرا و **PASS** می‌شوند (ct01a/b/c/d, ct02a, ct03a, ct04a/b, ct06a/b).
- هیچ skip به‌عنوان pass گزارش نشده است؛ خروجی `OK` ساده = صفر skip.

## ۱۳. موارد باز (NOT VERIFIED)

- **embedding واقعی + Neo4j** (بعد از Builder): خارج از این مأموریت —
  PCM-20.5 (در محیط ایزوله).
- مسیر کد دقیق `truncated_at_2000` داخل سایت (فقط رفتار API تأیید شد؛
  سورس سایت در دسترس نیست).
- اجرای مستقیم روی s52 (host از شبکه‌ی فعلی دسترس‌نیافتنی) — اسکریپت‌ها و
  دستورات آماده در §5/§12.
- Wiki.js: به‌روزرسانی ویکی بدون دسترسی/تأیید صریح انجام نشد.

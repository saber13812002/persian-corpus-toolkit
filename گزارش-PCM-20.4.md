# گزارش PCM-20.4 — پذیرش عملی و اجرای end-to-end زنجیره‌ی داده‌ی تسنیم

**تاریخ:** 2026-11-04 (UTC) · **دستورالعمل کامل:** `docs/PCM-20.4-TASNIM-ACCEPTANCE.md`
**هدف مأموریت:** اثبات صحت زنجیره‌ی `Real Snapshot → Canonical Corpus → Versioned Dataset →
AI Dump Builder Input` با provenance کامل (SHA-256 در هر گام) — بدون deploy،
بدون embedding واقعی، بدون LiteLLM، بدون Neo4j، بدون لمس کالکشن‌های عملیاتی.

**نتیجه‌ی نهایی: پذیرش کامل — همه‌ی 4 مرحله + Gate 1.5 پاس؛ 216/216 تست سبز؛
هیچ داده‌ی واقعی در Git نرفته (data/ gitignored).**

---

## A. اسنپ‌شات (Stage 1 — اعتبارسنجی ورودی واقعی)

فایل‌های PCM-20 (خروجی read-only از `thesaurus.db` روی s52؛ پروژه‌ی 2
«تفسیر تسنیم همتا»؛ `exported_at_utc = 2026-11-03T16:03:13+00:00`) در
`data/tasnim/pcm20_4/source-snapshot/` ثبت و تأیید شد:

| فایل | size (bytes) | SHA-256 (16 کاراکتر اول) | تطبیق با مرجع مأموریت |
|-------|-------------|--------------------------|------------------------|
| `tasnim-corpus.json` | 72,959,214 | `cee2c08aae1862d0` | ✅ |
| `tasnim-corpus.jsonl` | 72,906,133 | `fd927b663733fe05` | ✅ |
| `pcm20_2_audit.json` | 63,188 | `db6c30f415372c6a` | ✅ |

- **JSON↔JSONL:** 45,844 = 45,844 رکورد؛ ترتیب هر 7 فیلد کلیدی یکسان؛ **0 اختلاف**.
- شمارنده‌های پروژه (هدر خروجی): saved 45,838 / skipped 20 / failed 52,025.
- آمار PCM-20.2 از نو محاسبه و تطبیق (`validation/stage1_snapshot_audit.json`).
- **GATE 1.5 (برش 2000): PASS** — فقط 28 رکورد (0.06%) دقیقاً 2000 کاراکتر؛
  هیچ رکوردی >2000؛ پیک مصنوعی در 1800–1999 وجود ندارد؛ دم‌ها الگوی برش
  ناگهانی دارند (برخی در وسط ﴿آیه﴾). منشأ: **لیمیت RAG سمت سایت**
  (تأییدشده با API زنده در PCM-20.2) — صفر برش در export/crawl.
  (`validation/gate1_5_truncation_conclusion.json`)

## B. پیکره‌ی canonical (مرحله‌ی 20.4-A)

`build-corpus` روی خروجی واقعی 73MB → **Corpus v0001**
(`data/tasnim/pcm20_4/corpus/builds/v0001/`):

- **45,844 صفحه / 6 جلد**؛ policy `tasnim-p1-ascii-digits`؛ `validate-corpus` = **PASS** (V01..V08).
- `content_sha256 = ee87686ac49ce9c08a4a492f4f54c23ace571bb8f048aa8a0a863bece3d542d8`
- `manifest sha = e0b0c2cea4e52342f8a924e1c08a45e06d64aa236fcf586b6fc49782c39430fc`
- فایل‌ها: `pages.jsonl` 144,151,230 B (sha `0b31533a…`) · `corpus.json` 15,837 B (sha `97bc4d9a…`)

| جلد | id | صفحات | empty | short |
|-----|----|--------|-------|-------|
| 1 | `…__vol001` | 9 | 0 | 1 |
| 12 | `…__vol012` | 22 | 0 | 6 |
| 47 | `…__vol047` | 9,391 | 5 | 2,449 |
| 56 | `…__vol056` | 29,689 | 26 | 8,102 |
| 80 | `…__vol080` | 767 | 0 | 216 |
| نامشخص | `…__volkeyd531f422` | 5,966 | 4 | 1,592 |

- استراتژی جلد: url_section 39,878 / text 0 / none 5,966.
- **quality census:** ok 33,399 · short 12,366 · empty 35 · no_barg 35 ·
  dup_item_index 18 · truncated_at_2000 28 · missing_item_index 0.
- `item_index`: 45,844 / distinct 45,835 (9 ردیف تکراری → `__d1`)؛
  `barg_reparse`: 45,809 قابل‌پارس، 45,800 برابر ii+1، 44,801 با export متفاوت
  (بگ parse_barg رفع‌شده در Factory)؛ `content_hash` تکراری: **0**.
- **QC A: PASS** · **Idempotency:** اجرای دوم → REUSED (فایلی نوشته نشد) ·
  **Cross-root:** content_sha و انتخاب‌ها در data-root دوم دقیقاً یکسان.

## C. دیتاست‌های نسخه‌شده (مرحله‌ی 20.4-B)

`stratified-even-blocks` v2 — 5 درصد استاندارد + 1 دیتاست تک‌جلد:

| دیتاست | نسخه | صفحات | انتخاب درون‌جلد (1/12/47/56/80/نامشخص) | flags ok/short | content sha (16) |
|--------|------|-------|-----------------------------------------|----------------|------------------|
| 1% | v0001 | 458 | 0/0/94/297/8/59 | 338/116 | `a407021e95012824` |
| 10% | v0001 | 4,584 | 1/2/939/2969/77/596 | 3402/1166 | `7de515a69eeeb474` |
| 10% جلد 56 | v0002 | 2,969 | فقط vol056: 2,969 | 2193/770 | `11ab83ce8cef4d09` |
| 50% | v0001 | 22,922 | 5/11/4,696/14,844/383/2,983 | 16858/6025 | `7c15be3fb4191fef` |
| 90% | v0001 | 41,260 | 8/20/8,452/26,720/690/5,370 | 29991/11193 | `8ef9aab8eb7262d5` |
| 100% | v0001 | 45,844 | 100% هر جلد (= census پیکره) | 33399/12366 | `37673c3d4f377718` |

- پوشش درون‌جلد ≈ pct ± 1 (مثلاً 10%: 11.11 / 9.09 / 10.00 / 10.00 / 10.04 / 9.99%).
- **QC B: PASS** — شمارنده‌ها با بازتولید مستقل؛ زنجیره‌ی manifest روی دیسک
  حل شد (dataset → corpus v0001 → snapshot `sfd927b663733`)؛ اجرای تکراری → REUSED.
- **Incremental fixture** (21 رکورد؛ اثبات رفتار ارتقا):
  v0002 (21 صفحه، content `8a1cad10…`) → v0003 (22 صفحه، content `0d86db16…`)؛
  `diff v0002→v0003`: **added 1، changed 2، unchanged 18، healed 0،
  removed_from_source 1** (sha change-manifest `7b302035…`).
  صفحه‌ی «حذف‌شده» فقط با یادداشت *«حذف خودکار ممنوع؛ نسخه‌ی قبلی immutable»*
  علامت خورد — **هیچ نسخه‌ای حذف/بازنویسی نشد**؛ v0001 واقعی بعد از همه‌ی
  اجراها بایت‌به‌بایت یکسان بود.

## D. Builder — `export-dump` + اجرای واقعی ai-dump-builder (مرحله‌ی 20.4-C)

- ریپو Builder: `server52and53/_aidump` @ `1c500a6411df5edca31be0616ca707cc55910417`
  (کد **دست‌نخورده** — فقط اجرا شد؛ کالکشن عملیاتی `falsafe_siasi` هرگز لمس نشد).
- خروجی‌های dump (adapter `corpus/tasnim/dump.py`):

| dump | از dataset | کتاب‌ها | صفحات | records | skipped_short | content sha (16) |
|------|-----------|--------|-------|---------|---------------|------------------|
| `dumps/10pct/v0001` | 10pct v0002 (جلد 56) | 1 | 2,969 | 2,197 | 772 | `062ec699498a3920` |
| `dumps/10pct/v0002` | 10pct v0001 | 6 | 4,584 | 3,416 | 1,168 | `3ef895e32375764d` |
| `dumps/100pct/v0001` | 100pct v0001 | 6 | 45,844 | 33,443 | 12,401 | `d5dc00980b8c95a0` |

- **سه build واقعی** (هر کدام در دایرکتوری product جدا زیر
  `builder-input/`؛ دستور `python -m builder build --product <dir>
  --mock-embed --no-embed-reuse`) — همه‌ی 3 = **DUMP_VALIDATED**
  (اعتبارسنجی in-build + دستور مستقل `builder validate`):

| case | build_id | chunks sha256 (16) | size | rec/skip |
|------|----------|--------------------|------|----------|
| vol56 | `qwen3-embed-06b_20261104-041446` | `ab3bf5660b22c3fc` | 57.5 MB | 2,197/772 |
| 10pct | `qwen3-embed-06b_20261104-041457` | `0b7f40b045766c24` | 89.7 MB | 3,416/1,168 |
| 100pct | `qwen3-embed-06b_20261104-041514` | `f9debdd32142c78a` | 872.2 MB | 33,443/12,401 |

  dim = 1024 · backend = **mock** · `mapping.json` (sha `0bd9b8a73858306f5ef17da12bcc6758e80286fdef21f9ab820a7a7034d4002b`) · current pointerها switch شدند.
- **صریح: dump نهایی واقعاً ساخته شد** — هر 3 `chunks.jsonl` (از جمله 100% با
  33,443 رکورد / 872.2 MB) با manifest + mapping روی دیسک و اعتبارسنجی‌شده
  است. آنچه mock است **فقط بردارهای embedding** (MockEmbedder = sha256 → 1024d)
  است؛ **LiteLLM/شبکه/Neo4j/collection عملیاتی در هیچ مرحله‌ای درگیر نشدند**.
- **QC C (22 بررسی): PASS** — تطبیق counts با `dump-check.json`؛ REQUIRED
  fields؛ `_fp` موجود / `_embed_input` حذف؛ 9 کلید provenance در رکوردها؛
  repo Builder بدون تغییر جدید.
- toolkit commit در لحظه‌ی اجرا: `8db3b60a2ce1a9a4dcead4a6f62dd7f61dff9151`.

## E. تست‌ها (PASS/FAIL/SKIP)

| مجموعه | اجرا | PASS | FAIL | SKIP |
|--------|------|------|------|------|
| رگرسیون backend (11 ماژول) | `python -m unittest test_api … test_api_contract -v` از `.venv` | **200** | 0 | **0** |
| Factory T (T-01…T-10c) | `python -X utf8 -m unittest test_corpus_tasnim -v` (ریشه‌ی ریپو) | **16** | 0 | **0** |
| **مجموع** | | **216** | **0** | **0** |

- رگرسیون: `Ran 200 tests in 77.870s — OK` (خروجی `OK` ساده = صفر skip).
- 10 تست CT که قبلاً به‌خاطر نبود PyYAML skip می‌شدند، با نصب `pyyaml==6.0.3`
  در **venv پروژه** (`.venv` — Python 3.13.15 64-bit؛ **نصب global نشد**)
  حالا **اجرا و PASS** می‌شوند: ct01a/b/c/d، ct02a، ct03a، ct04a/b، ct06a/b.
- هیچ skip به‌عنوان pass گزارش نشده است.

## F. Git — سه محیط

| محیط | وضعیت | SHA |
|------|--------|-----|
| **Local** (این ویندوز) | commit + push به GitHub | `<شماره‌ی commit نهایی — در فاز Git تکمیل می‌شود>` |
| **GitHub** (origin: `saber13812002/persian-corpus-toolkit`) | push شده | `<SHA — بعد از push>` |
| **GitLab internal** (`s52:2222`) | **دسترس‌نیافتنی** — از شبکه‌ی فعلی `172.20.1.52:2222` unreachable (همان وضعیت PCM-18/20)؛ ریپو/ترانسفر تاریخچه انجام **نشد** و ادعایی درباره‌ی آن نیست | — |
| (مرجع) toolkit commit هنگام اجرای Builder | — | `8db3b60a2ce1a9a4dcead4a6f62dd7f61dff9151` |

- commit‌ها منطقی/سپارشی هستند؛ **هیچ داده‌ی واقعی** (data/، snapshot، dumps،
  builds) در Git نمی‌رود (data/ و فایل‌های `.tmp_*` gitignored) — فقط کد/اسناد/
  گزارش و SHAهای provenance.
- بدون force push.

## G. موارد NOT VERIFIED

1. **embedding واقعی + Neo4j load** — خارج از این مأموریت (PCM-20.5؛ محیط ایزوله).
   بردارهای موجود در `chunks.jsonl`‌ها mock هستند و نباید برای RAG واقعی استفاده شوند.
2. **مسیر کد دقیق `truncated_at_2000`** داخل سایت (سورس سایت در دسترس نیست —
   فقط رفتار API زنده تأیید شد).
3. **اجرای مستقیم روی s52** — host از شبکه‌ی فعلی دسترس‌نیافتنی؛ دستورات آماده
   در `docs/PCM-20.4-TASNIM-ACCEPTANCE.md` §5/§12 و پیوست.
4. **Wiki.js** — به‌روزرسانی ویکی بدون دسترسی/تأیید صریح انجام نشد.
5. GitLab internal — به‌دلیل item 3/F.

## H. پیشنهاد PCM-20.5 (مأموریت بعدی)

**embedding واقعی + بارگذاری Neo4j در محیط ایزوله** — روی خروجی‌های پذیرفته‌شده
این مأموریت (`dumps/` + `builder-input/`):

1. اجرای Builder واقعی (LiteLLM + مدل Qwen3-Embedding-0.6B) روی یکی از دیتاست‌ها
   (پیشنهاد: 10% — تعادل هزینه/دقت) در دایرکتوری product جدا؛ **کالکشن
   عملیاتی `falsafe_siasi` دست‌نخورده می‌ماند**.
2. بارگذاری `chunks.jsonl` + `mapping.json` به کالکشن جدید
   `tasnim_tafsir__<model_slug>` (consumer: `rag/graph-rag/app/load_collection.py`)
   در دیتابیس/کالکشن **جدید و ایزوله** (نه کالکشن‌های موجود).
3. آزمون کیفیت RAG: retrieval queryهای فارسی برحسب برگ/جلد/محتوا +
   verification provenance (page_id/barg از متادیتا رکورد به snapshot واقعی).
4. ثبت نتیجه در registry (زنجیره‌ی `dump → collection`) و گزارش با SHAها.

قواعد: بدون لمس کالکشن‌های عملیاتی؛ بدون رمز در کد/لاگ/گزارش؛ هر گام
تست→commit→push→گزارش.

---

## پیوست — مرجع‌های اثبات (همه در `data/tasnim/pcm20_4/`، gitignored)

- `validation/stage1_snapshot_audit.json` · `gate1_5_truncation_conclusion.json`
- `validation/audit_gate.json` · `validation/builder-run.json`
- `corpus/builds/v0001/manifest.json` (تمام آمار/SHAs) · `datasets/*/v*/manifest.json`
- `dumps/*/v*/{books.json, product.json, dump-check.json, manifest.json}`
- `builder-input/tasnim_tafsir_<case>/builds/<build_id>/` (chunks.jsonl + mapping + manifest + build.log)
- `manifests/registry.json` — **17 entry** (3 corpus، 6 dataset، 3 dump، 3 snapshot)
- `reports/audit-*.json` · `reports/diff_v0002_v0003/change-manifest.json`
- اسناد: `docs/PCM-20.4-TASNIM-ACCEPTANCE.md` (معماری + راهنمای اجرا + نمونه‌های JSON)
  · `docs/PCM-20.3-TASNIM-FORFACTORY.md` (قرارداد c-20.3)

# قرارداد داده — read model «تفسیر تسنیم» (PCM-20.6.4)

این سند قرارداد رسمی داده بین **پیکرهٔ canonical v0003** (ورودی)، **read model** (`tasnim_readmodel.db`) و **API/SSR** (خروجی) است. همهٔ اعداد از `build_meta.db` و پرسج‌های زندهٔ read model v0003 (ساخته‌شده 2026-11-07T04:01:31Z) گرفته‌اند.

مستندات مرتبط: [README.md](README.md) · [API-REFERENCE.md](API-REFERENCE.md) · [SECURITY.md](SECURITY.md) · [OPS-RUNBOOK.md](OPS-RUNBOOK.md)

---

## ۱. ورودی: پیکرهٔ canonical v0003

پیکرهٔ v0003 محصول خط لولهٔ `corpus/tasnim/` (PCM-20.3) است و شامل این فایل‌هاست:

| فایل | نقش | حجم (byte) | SHA-256 | وضعیت verify در build |
|------|-----|-----------|---------|------------------------|
| `pages.jsonl` | 45,844 صفحه | 170,629,785 | `8bec1bb8…9648755b` | ✅ verified |
| `heading-records.jsonl` | 10,739 هدر | 9,857,675 | `0a1e52a5…0b1aa` | ✅ verified |
| `corpus.json` | متادیتای اثر/نسخه | 19,846 | `8e71a395…f9f51b1` | ✅ verified |
| `manifest.json` | manifest رسمی (شمارنده‌ها، policy) | 6,938 | `0e50f52b…5cea60` | ⚠️ `verified: false` در build_meta (مطابقت شمارنده‌ها انجام شد؛ این flag به‌معنای ناسازگاری نیست — جزئیات: [TEST-REPORT.md](TEST-REPORT.md)) |
| `hidden-context-records.jsonl` | 10,728 رکورد **پنهان** | 17,895,082 | — | 🚫 **ممنوع — builder هرگز باز نمی‌کند** (HP-1) |
| `context-records.jsonl` | 10,728 رکورد (byte-identical با بالا، گیت S08) | 26,287,577 | — | 🚫 **ممنوع** (HP-1) |

- **شناسه‌ها:** work_id = `tasnim_hamta`، edition_id = `tasnim_hamta__hamta-2026` («خروجی کراول hamta-2026»).
- **حد truncation منبع:** صفحات در کراول با سقف **2,000 کاراکتر** ثبت شده‌اند (GATE 1.5 PCM-20.4: PASS). 28 صفحه دقیقاً `truncated_at_source=true` + `source_char_cap=2000` دارند.
- **hash صفحه:** `content_sha256` هر صفحه یک **hash سمت-کراولر** است (از متن صفحه بازتولید نمی‌شود — probe PCM-20.6.4) و به‌صورت verbatim ذخیره می‌شود. این نکته در `build_meta.page_content_hash_note` مکتوب است.
- **سند کامل پیکره:** `docs/PCM-20.6-CORPUS-V0003.md` (ریشهٔ ریپازیتوری).

## ۲. خروجی: محتویات دایرکتوری read model

مسیر قراردادی: `tasnim/data/readmodel/<version>/` (در V1 = `v0003`)

| فایل/دایرکتوری | حجم | توضیح |
|----------------|------|-------|
| `tasnim_readmodel.db` | **260,816,896 B** (~260 MB) | SQLite read model (WAL بسته هنگام build) |
| `build_meta.db` | 12,288 B | جدول `build_meta(key, value)` — meta build |
| `build.sha256` | 168 B | sidecar: SHA-256 دو فایل بالا (فرمت `sha  نام`) |
| `covers/*.svg` | 6 فایل (1,594–1,813 B) | جلد SVG مولد (بدون تصویر واقعی — سیاست «بدون cover ساختگی») |
| `tasnim_rate_limits.db` | 12,288 B | (اختیاری) DB rate-limit که سرویس کنار read model می‌سازد؛ **جزو هویت read model نیست** و حذف‌پذیر است |

محتوای `build.sha256` (صادقانه قابل‌بررسی):

```text
353f413b00467640fabfed267c9a2933a64495f3bfb3bab7e42cd43a54d9c0fd  tasnim_readmodel.db
ed0f3d525c4a3e24819b233646fb2f46f30c287bd6e924062f8f75b75eedbbc0  build_meta.db
```

> **محدودیت شناخته‌شده (صادقانه):** docstring builder، خروجی `build-report.json` را نام می‌برد؛ در build v0003 این فایل **تولید نشده** است (مجموعهٔ خروجی واقعی = ۴ ردیف بالا). هیچ رفتار روی این فایل شرطی نشده و همهٔ meta در `build_meta.db` موجود است. رفع = کار فنی کوچک (مورد باز برای فاز بعدی).

### ۲.۱ کلیدهای `build_meta` (کل — از build واقعی v0003)

| key | value |
|-----|-------|
| `corpus_version` | `v0003` |
| `content_sha256` | `40f45e0b2c393a65569846aeaac4d45dcee4bd58a7f158b1554adf3755ca78e4` |
| `db_sha256` | `353f413b00467640fabfed267c9a2933a64495f3bfb3bab7e42cd43a54d9c0fd` |
| `schema_version` | `tasnim-readmodel/1.0` |
| `topic_norm_version` | `tasnim-topic-norm/1.0` |
| `tokenizer_version` | `tokenize_fa/1.0` |
| `built_at` | `2026-11-07T04:01:31Z` |
| `page_count` | `45844` |
| `heading_count` | `10739` |
| `topic_count` | `1080` |
| `volume_count` | `6` |
| `rag_status` | `not_connected` |
| `surah_status` | `not_supported` |
| `hidden_context_included` | `false` |
| `policy` | `hidden summaries are system-only (embedding/retrieval) and must never be rendered publicly` |
| `page_content_hash_note` | hash سمت-کراولر، verbatim (بالات) |
| `fts_note` | standalone FTS5؛ پیش‌توکن `tokenize_fa/1.0`؛ unicode61؛ prefix AND؛ بدون stemming فارسی |
| `text_length_stats` | `{"p50": 64, "p90": 1710, "p99": 1985, "max": 2000}` |
| `source_files` | آرایهٔ 4 فایل با sha/size/verified (جدول §۱) |

## ۳. کلیدگذاری صفحات: `page_id`، `item_index`، `barg`

| مفهوم | تعریف | کاربرد |
|-------|-------|--------|
| **`item_index`** | کلید **ترتیب** صفحه در کل اثر (ردیف منطقى کراول). min=0، max=91,077. روی 45,844 سطر، 45,835 مقدار متمایز؛ 9 مقدار تکراری (2,3,4,9,14,19,24,25,26 = 18 سطر — همگی overlap vol001×vol047) | ناوبری prev/next، جستجو، URL `/page/<n>` |
| **`page_id`** | شناسهٔ یکتا: `<volume_id>__p<item_index>[__d<n>]` — مثلاً `tasnim_hamta__hamta-2026__vol047__p2__d1` | **کلید اصلی جدول `pages`** و هر اشاره در API |
| **`barg`** | شمارهٔ برگهٔ چاپی (printed leaf). 35 مقدار null (صفحات خالی) | **فقط نمایشی** — هرگز کلید یا URL نمی‌شود |
| **`dup_rank`** | 0 = نمایندهٔ اصلی یک `item_index`؛ 1+ = نسخهٔ تکراری (همه سمت vol047) | URL `/page/<n>?dup_rank=1` |

**قوانین (AGENTS.md §۲):**
- `page_id` کلید است؛ `item_index` ترتیب است؛ `barg` فقط نمایش.
- `next_page_id` **هرگز volume را رد نمی‌کند** (0 مورد در v0003) → prev/next داخل-volume امن است.
- تکرار `item_index` با suffix `__d1` در `page_id` متمایز می‌شود و `dup_of` به نمایندهٔ اصلی اشاره دارد.

## ۴. وضعیت‌های کیفیت (quality states)

هر صفحه یک `status` و تا 3 flag جداگانه دارد: **flags ممکن است بیشتر از status باشد** (یک صفحه هم `short` و هم `dup` باشد) — تعریف این نکته در خود API (`/statistics`) مکتوب است.

### ۴.۱ `pages.status` (GROUP BY زندهٔ v0003 — جمع = 45,844 ✅)

| status | شمار | معنی |
|--------|------|------|
| `ok` | 33,399 | متن کامل و سالم |
| `short` | 12,366 | متن کوتاه‌تر از انتظار (بدون truncation منبع) |
| `empty` | 35 | صفحه خالی |
| `truncated_at_2000` | 28 | در **منبع** 2,000 کاراکتر بریده شده (سیگنال رسمی = flag، نه صرفاً `len==2000`) |
| `dup_item_index` | 16 | نمایندهٔ تکراری یک `item_index` |

### ۴.۲ `pages.record_class` (GROUP BY زنده — جمع = 45,844 ✅)

| class | شمار |
|-------|------|
| `CONTENT_PAGE` | 33,443 |
| `SECTION_HEADING` | 10,739 |
| `SHORT_CONTENT` | 1,589 |
| `EMPTY_PAGE` | 35 |
| `UNKNOWN_STRUCTURE` | 38 |

### ۴.۳ کجا هر کدام دیده می‌شود؟

- **API:** فیلد `quality` در `/pages/{n}` (`{status, flags[], truncated_at_source, source_char_cap}`) و `/statistics` (تفکیک‌ها بالا + `definition` مکتوب برای هر بخش).
- **SSR:** نشان (badge) کوچک کنار شمارهٔ صفحه؛ صفحهٔ خالی = «این صفحه خالی است»؛ truncation = یادداشت «در منبع 2,000 کاراکتر».
- **search results:** `quality_status` برای هر hit.
- **about:** جدول «وضعیت کیفیت» با شمارنده‌های زنده.
- **پوشش (coverage):** شکاف‌های کل‌اثر (45,243 صفحه در 6 بازه) در جدول `coverage` + `GET /catalog` (`present_ratio=0.5033`) و صفحهٔ 404 (`in_missing_range` + نزدیک‌ترین صفحات موجود).

## ۵. schema کامل read model (`tasnim-readmodel/1.0`)

```sql
-- هویت
works(work_id TEXT PK, work_name TEXT);                 -- 1 سطر: tasnim_hamta
editions(edition_id TEXT PK, work_id TEXT FK,
        edition_name TEXT, source_version TEXT, exported_at TEXT);  -- 1 سطر
volumes(volume_id TEXT PK, edition_id TEXT FK, volume_no INT NULL,
        volume_title TEXT, volume_strategy TEXT,
        page_count INT, item_index_min INT, item_index_max INT,
        ambiguity_flag INT DEFAULT 0, overlap_note TEXT);           -- 6 سطر

-- صفحات (45,844 سطر)
pages(page_id TEXT PK,
      item_index INT, dup_rank INT DEFAULT 0,
      volume_id TEXT FK, barg INT NULL, section TEXT,
      content_sha256 TEXT, char_count INT,
      record_class TEXT, status TEXT,
      flag_short INT, flag_empty INT, flag_truncated_2000 INT,
      dup_of TEXT NULL,                    -- page_id هم-item_index با dup_rank کمتر
      seq_in_volume INT, seq_global INT,
      heading_record_id TEXT NULL,         -- «hctx:…» فقط شناسهٔ هدرِ همین صفحه
      context_record_id TEXT NULL,         -- «hcctx:…» فقط شناسه — محتوای رکورد هرگز
      next_page_id TEXT NULL, next_item_index INT NULL,
      captured_at TEXT, source_page_id INT, url TEXT,
      text TEXT, text_normalized TEXT,
      text_tokens TEXT);
CREATE INDEX idx_pages_ii  ON pages(item_index, dup_rank);
CREATE INDEX idx_pages_vol ON pages(volume_id, item_index);

-- هدرها (10,739 سطر)
headings(record_id TEXT PK,                -- «hctx:<page_id>»
         page_id TEXT FK, item_index INT, volume_id TEXT FK,
         heading_text TEXT, heading_hash TEXT,
         normalized_text TEXT,             -- normalize_topic (تفسیر §۷)
         topic_id TEXT FK,
         parent_heading_page_id TEXT NULL, -- 10,733 non-null، orphan 0
         next_page_id TEXT NULL,           -- association: صفحهٔ اول بخش بعدی
         children_count INT);
CREATE INDEX idx_headings_topic ON headings(topic_id);
CREATE INDEX idx_headings_vol   ON headings(volume_id, item_index);

-- موضوعات (1,080 سطر)
topics(topic_id TEXT PK,                   -- «t-» + sha1(normalized_text)[:12]
       normalized_text TEXT UNIQUE, display_text TEXT,
       page_count INT, volume_count INT,
       first_page_id TEXT, first_item_index INT);

-- سوره (در v0003 خالی — صادقانه not_supported)
surahs(surah_id TEXT PK, canonical_name TEXT, confidence REAL, page_count INT);

-- FTS5 — انحراف مکتوب از spec اولیه:
--   1) standalone table (spec اولیه external-content بود و bug column-mapping داشت)
--   2) range توکن فارسی [0600-06FF 0750-077F] نه [0621-064A] spec
--      (range spec گ، پ، چ، ژ را می‌ریخت — اصلاح شد و مکتوب شد)
CREATE VIRTUAL TABLE pages_fts USING fts5(
  page_id UNINDEXED, item_index UNINDEXED, tokens,
  tokenize='unicode61');
-- tokens با tokenize_fa/1.0 پیش‌محاسبه و در insert نوشته می‌شوند.

-- پوشش (11 سطر در v0003: 6 global + 5 volume)
coverage(scope TEXT,                        -- 'global' | volume_id
         missing_from INT, missing_to INT, missing_count INT,
         status TEXT DEFAULT 'backfill_pending',
         note TEXT);                        -- global rows: دلیل block (SPA-shell s52)
```

### ۵.۱ سطرهای `volumes` (6 — از DB زنده)

| volume_id | no | title | strategy | pages | item_index [min..max] | ambiguity |
|-----------|----|-------|----------|-------|----------------------|-----------|
| `…__vol001` | 1 | جلد 1 | url_section | 9 | 2..26 | ⚠️ overlap 9 صفحه با vol047 |
| `…__vol012` | 12 | جلد 12 | url_section | 22 | 11183..11204 | — |
| `…__vol047` | 47 | جلد 47 | url_section | 9,391 | 0..55698 | ⚠️ overlap 9 صفحه با vol001 |
| `…__vol056` | 56 | جلد 56 | url_section | 29,689 | 59591..89279 | — |
| `…__vol080` | 80 | جلد 80 | url_section | 767 | 90311..91077 | — |
| `…__volkeyd531f422` | null | نامشخص | none | 5,966 | 39004..55714 | — |

(پیشوند کامل هر volume_id: `tasnim_hamta__hamta-2026`.)

### ۵.۲ سطرهای `coverage` (11 — از DB زنده)

| scope | از | تا | count | status |
|-------|----|----|-------|--------|
| global | 3649 | 11182 | 7,534 | backfill_pending |
| global | 11205 | 39003 | 27,799 | backfill_pending |
| global | 44957 | 49956 | 5,000 | backfill_pending |
| global | 55699 | 55701 | 3 | backfill_pending |
| global | 55715 | 59590 | 3,876 | backfill_pending |
| global | 89280 | 90310 | 1,031 | backfill_pending |
| vol001 | 5–8 / 10–13 / 15–18 / 20–23 | | 16 | covered_by_other_volume (vol047) |
| vol047 | 3649 | 49956 | 46,308 | partial_other_volume (covered_by: vol012 [11183..11204] + volkey [39004..44956]) |
| volkeyd531f422 | 44957 | 55701 | 10,745 | partial_other_volume (covered_by: vol047 [49957..55698]) |

> **دو متریک جداگانه — صادقانه:**
> - **فهرست backfill کل‌اثر (مرجع):** 6 بازهٔ global، جمع **45,243** صفحه — این همان `missing_item_index` در `/catalog` و `/statistics` است.
> - **پوشش درون-volume:** مثل 46,308 برای vol047 (بازهٔ min..max خودِ جلد) — اعداد متفاوت است چون «کمبود در بازهٔ جلد» و «کمبود کل‌اثر» دو تعریف متفاوت‌اند (بعضی صفحات کمبود درون-جلد توسط جلد دیگر پوشش داده شده‌اند). API هر دو را جدا می‌دهد و تعریف هر کدام در پاسخ مکتوب است.
>
> همهٔ 6 بازهٔ global وضعیت `backfill_pending` دارند با note: *«no trusted source available offline: the live site /payload now returns an HTML SPA shell (PCM-20.5 GATE 0-D evidence); recovery requires a live re-crawl on s52 — BLOCKED until s52 is reachable»*. اجرای backfill بدون تأیید انسانی ممنوع (AGENTS.md §۲؛ طرح: `docs/PCM-20.6.3-BACKFILL-DESIGN.md`).

## ۶. ارتباط هدر ↔ صفحه ↔ hidden context (و HP-1)

- هر صفحهٔ SECTION_HEADING (10,739) یک رکورد در `headings` دارد؛ `heading_record_id` در `pages` به آن اشاره می‌کند.
- `headings` درختی است: `parent_heading_page_id` (10,733 non-null، 0 orphan؛ invariant «parent قبل از child در item_index»؛ عمق زنجیره max 7,213 / avg 2,695). UI درخت کامل نمی‌کشد — فقط نمایش صفحه + topic.
- **hidden context:** برای 10,728 هدر، «خلاصهٔ پنهان بخش» (hcctx) در پیکره وجود دارد. در read model **فقط شناسه** (`context_record_id = «hcctx:…»`) ذخیره می‌شود؛ **محتوا هرگز وارد read model/API/SSR نمی‌شود**.
- **HP-1 (Hard Policy 1) — ۴ لایهٔ ایزولهٔ hidden context:**
  1. **builder:** `ALLOWED_SOURCE_FILES = {pages.jsonl, heading-records.jsonl, corpus.json, manifest.json}`؛ `ReadModelBuilder._open` برای هر نام دیگر `BuildError("HP-1 violation: builder must never open %r")` می‌دهد. فایل‌های forbidden با canary داخل تست قرار می‌گیرند.
  2. **serializer:** `strict_pick` (deny-by-default) — هر endpoint فقط فیلدهای whitelist‌شده را از row برمی‌گزیند.
  3. **تست‌ها:** T-HC-1..4 (canary «HIDDEN-CANARY-DO-NOT-LEAK» در decoyها + اسکن همهٔ HTML bodies در smoke).
  4. **policy مکتوب:** `build_meta.policy` + `hidden_context_included=false`.
- جزئیات کامل + مدل تهدید: [SECURITY.md](SECURITY.md).

## ۷. نرمال‌سازی و توکن‌سازی (نسخه‌شده)

### ۷.۱ `normalize_topic` (tasnim-topic-norm/1.0)
trim → ارقام ۰-۹/٠-٩ به ASCII → حذف پیشوند عددی (دو بار) → HAMZA_MAP (ٔ→حذف، ٴ→حذف، ٲ→ا، ٵ→ئ، ە→ه، ۍ→ی) → حذف ` .:ـ-` از انتها. سپس `topic_id = "t-" + sha1(normalized)[:12]` (پایدار، deterministic). نتیجهٔ v0003: **1,080** متن متمایز؛ 62 موضوع روی ≥2 صفحه.

### ۷.۲ `tokenize_fa` (tokenize_fa/1.0)
ارقام→ASCII؛ حذف diacritics (064B-065F، 0670، 08D3-08FF)؛ ZWNJ→فاصله؛ حذف نشانه‌ها؛ توکن = `[0600-06FF 0750-077F]+ | ارقام | لاتین`. کوئری FTS = **prefix AND**: `"tok"*` روی هر توکن پرس‌ش.

**محدودیت‌های مکتوب (صادقانه):**
- **بدون stemming فارسی:** «قرآن» «قرآنی» را پیدا نمی‌کند (و بالعکس). ارزیابی stemming/ICU = ROADMAP V1.5.
- **مکمل‌های ZWNJ-جداشده** با فاصله جستجو می‌شوند (مثل «میزان معارف»).
- مثال زنده: «قرآن» → **6,760** صفحه (FTS5؛ همان عدد در `/search`، raw `COUNT` روی `pages_fts` و E2E step 8). (LIKE substring ساده = 6,922 — عدد متفاوت با تعریف متفاوت؛ عدد رسمی API/مستند = 6,760.)

## ۸. Invariants ساخت (build) + swap نسخه و rollback

### ۸.۱ CLI
```bash
python -X utf8 -m tasnim.web.build_cli build --corpus <dir-pickere> --out <dir-readmodel>
```

### ۸.۲ Invariants (همه test‌دار)
1. **Source read-only:** همهٔ فایل‌های ورودی read-only باز می‌شوند؛ builder هیچ‌چیز در درخت corpus نمی‌نویسد (تست mtime/size قبل/بعد).
2. **Determinism:** دو build یکسان = `db_sha256` یکسان (دو build v0003 با SHA برابر اثبات شد).
3. **Version dir:** خروجی همیشه در دایرکتوری نسخه (`v0003/`) — نسخه‌های قبلی دست‌نخورده می‌مانند.
4. **HP-1:** builder هرگز فایل‌های hidden/context را باز نمی‌کند (§۶).
5. **Validation vs manifest:** عدم‌مطابقت شمارنده‌ها با `manifest.json` = **فشل build** (نه warning).
6. **حافظهٔ محدود:** commit هر 5,000 سطر؛ کل‌فایل‌بارگذاری ممنوع.
7. **خروجی‌های قطعی:** `build_meta.db` + `build.sha256` + `covers/` کنار DB.

### ۸.۳ تعویض نسخه (مثلاً v0003 → v0004) — روش استاندارد
1. build نسخهٔ جدید: `--out tasnim/data/readmodel/v0004` (v0003 دست‌نخورده).
2. **تصدیه قبل از swap:** `sha256sum -c build.sha256` در دایرکتوری جدید + اجرای smoke.py روی پورت جدا با `--db v0004` + بررسی `GET /catalog` و `/health` (version + content_sha256 جدید).
3. **Swap:** فقط تغییر `--db`/`TASNIM_DB_PATH` + restart سرویس (در Docker: تغییر bind-mount در compose). read model **immutable** است — هیچ «مهاجرت درجا» روی DB زنده وجود ندارد.
4. **Rollback:** برگشت `--db` به دایرکتوری قبلی + restart (≤ چند دقیقه). rate-limit DB جداست و با swap معنی‌ای ندارد (بازنشانی‌اش امن است؛ OPS-RUNBOOK §۴).
5. smoke دوباره + گزارش. جزئیات کامل: [OPS-RUNBOOK.md](OPS-RUNBOOK.md) §۲ و [BACKUP-RESTORE.md](BACKUP-RESTORE.md).

## ۹. زنجیرهٔ SHA (provenance)

```text
pages.jsonl + heading-records.jsonl + corpus.json + manifest.json   (پیکره v0003 — immutable)
   │  (shaهای هر فایل در build_meta.source_files؛ content_sha256 کل‌محتوا)
   ▼
build_cli build  ──►  tasnim_readmodel.db  (db_sha256 در build_meta + sidecar build.sha256)
   │                          └──► build_meta.db  (sidecar build.sha256)
   ▼
API:  meta.readmodel = {version, content_sha256}  در هر پاسخ
      /health:  + db_sha256 + db_quick_check
      ETag:     «sha256(dbsha|key)[:32]» → خودبه‌خود با هر build جدید invalid می‌شود
SSR:   /about: نمایش content_sha256 + db_sha256 برای خواننده
```

**قوانین:** read model بعد از build **immutable** است؛ هیچ ابزار write روی آن نیست (سرویس با URI read-only باز می‌کند). بازیابی/برقابی یک نسخه فقط از طریق **بک‌آپ خارج از ریپازیتوری** + verify SHA — [BACKUP-RESTORE.md](BACKUP-RESTORE.md).

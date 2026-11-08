# PCM-20.7C — پایدارسازی پیکره (Corpus Stabilization)

**مأموریت:** PCM-20.7C (فاز C) — بخش‌های ۳.۱ تا ۳.۶ برنامه.
**برگ:** `pcm-20.6-tasnim-web-v1` · **تاریخ اجرا:** 2026-11-08 (UTC) · **حالت:** read-only روی داده + تولید فقط داخل `data/tasnim/pcm20_5/`
**قید:** هر عدد این گزارش از فایل/manifest واقعی خوانده شده؛ هیچ عدد ساختگی نیست.

---

## ۱. خلاصه‌ی نتیجه

| بخش | نتیجه |
|---|---|
| ۳.۱ تأیید baseline (v0003) | ✅ 46/46 چک سبز؛ 8/8 شمارنده‌ی گزارش‌شده = واقعی |
| ۳.۲ ممیزی ترتیب item_index | ✅ 0 نقض ترتیب؛ 9 تکراری **فلگ‌شده** (حذف نشد) |
| ۳.۳ شکاف‌ها + آماده‌سازی backfill | ✅ بازمحاسبه: 45,243 صفحه / 6 رنج / 91 ران؛ **Gate B: هیچ backfill زنده‌ای اجرا نشد** (جزئیات: `PCM-20.7C-GAP-REPORT.md`) |
| ۳.۴ Headings + Hidden Context | ✅ قرارداد cs-20.7 + پایپ‌لاین؛ پایلوت **PASS** (جزئیات: `PCM-20.7C-SEMANTIC-ENRICHMENT.md`) |
| ۳.۵ Topics | ✅ 1,080 موضوع canonical تأیید شد؛ 25 موضوع برتر با شمارش واقعی |
| ۳.۵ Surahs | ✅ رأی: **NOT_SUPPORTED** به‌عنوان نشانگر سازه‌ای (جزئیات: `PCM-20.7C-SURAH-ASSESSMENT.md`) |
| ۳.۶ تصاویر و متادیتا | ✅ رأی: **NOT_AVAILABLE** — منبع text-only است؛ فقط جلد SVG ساخته‌شده |

---

## ۲. بخش ۳.۱ — تأیید baseline (v0003)

**منبع:** `data/tasnim/pcm20_5/corpus/builds/v0003/manifest.json` + اسکن مستقیم فایل‌ها
(اسکریپت: `.tmp_pcm207c_verify.py`، خروجی: `.tmp_pcm207c_verify.json` — **46 چک، 0 FAIL**).

### 2.1 شناسه‌ی نسخه و زنجیره

| فیلد | مقدار |
|---|---|
| version | `v0003` (semantic contract `cs-20.6`) |
| created_at | `2026-11-06T12:35:21Z` |
| content_sha256 | `40f45e0b2c393a65569846aeaac4d45dcee4bd58a7f158b1554adf3755ca78e4` |
| base (previous) | `v0002` · content_sha `12a93e218bbc7a38d450749eca5ce25d0833b537cc13446048d430eade54f4a5` |
| policy | `tasnim-p1-ascii-digits` (digits→ASCII + collapse ws + strip) |
| built_by | `corpus.tasnim/1.0.0` |

### 2.2 SHA-256 فایل‌های v0003 (از manifest، بازتأیید‌شده با محاسبه‌ی مستقل)

| فایل | SHA-256 (سکوی) | سایز (بایت) |
|---|---|---|
| `pages.jsonl` | `8bec1bb8d2b66baa43a589a0ed29b63d1cf9f1527b80b2890b2081929648755b` | 170,629,785 |
| `corpus.json` | `8e71a3955df7a263eb10365bdecfca23c0b3b82d7ac271a6b8126807fd9f51b1` | 19,846 |
| `heading-records.jsonl` | `0a1e52a5fab2e412adbf8e7f3558b9041bae3798da72dacff4cd96dd1170b1aa` | 9,857,675 |
| `context-records.jsonl` | `a1ac04216c38243a26ca40e1857ec210965cfdecb464bc70f06afcb54805a949` | 26,287,577 |
| `hidden-context-records.jsonl` | `f5e07013a3a70b04ef41ac35edf31205f3ae846e29713f1e55737543fadd2329` | 17,895,082 |

زنجیره‌ی داده (Snapshot → Canonical → Semantic → Dataset → Dump) با SHAها در
`.tmp_pcm207c_v0003_immutability.json` ثبت شده و در طول فاز C **v0003 دست‌نخورده** ماند.

### 2.3 گزارش‌شده = واقعی (8/8)

| شمارنده | گزارش‌شده (PCM-20.6) | واقعی (محاسبه‌ی مستقل) |
|---|---:|---:|
| pages | 45,844 | 45,844 |
| volumes | 6 | 6 |
| topics (normalized) | 1,080 | 1,080 |
| headings | 10,739 | 10,739 |
| hidden context records | 10,728 | 10,728 |
| missing item_index | 45,243 | 45,243 |
| truncated_at_2000 | 28 | 28 |
| duplicate item_index | 9 | 9 |

---

## ۳. بخش ۳.۲ — ممیزی ترتیب item_index

- **0 نقض ترتیب** (ORDER violation): در هیچ جلدی صفحه‌ای با item_index کوچک‌تر
  بعد از صفحه‌ای با item_index بزرگ‌تر در ترتیب `position` قرار ندارد.
- **9 item_index تکراری**: **فلگ** شده‌اند و **حذف نشده‌اند** (قاعده‌ی flags-not-deletes؛
  page_id با `dup_rank` تمایز یافته است).
- item_index‌های موجود: 45,835 متمایز از 45,844 رکورد (45,844 − 45,835 = 9 تکراری).
- محدوده‌ی کامل: `0..91077` (span 91,078)؛ شکاف‌ها: 45,243 (بخش ۴).

### یافته‌های باز (F-1/F-2/F-3)

| ID | سختی | توضیح |
|---|---|---|
| **F-1** | gap مورد انتظار — در cs-20.7 بسته می‌شود | `next_page_item_index` در 0/10,739 رکورد heading وجود ندارد (در cs-20.6 روی رکوردهای hidden-context به‌عنوان `next_item_index` است). قرارداد ۳.۴ آن را در v0004 به رکوردهای heading اضافه می‌کند. |
| **F-2** | gap مورد انتظار — در cs-20.7 بسته می‌شود | `retrieval_context`/`retrieval_context_summary` در رکوردهای heading خالی است (rc=0, rcs=0)؛ خلاصه‌ی مخفی در `hidden-context-records.jsonl` نگهداری می‌شود. v0004 این دو فیلد را روی رکوردهای heading می‌گذارد. |
| **F-3** | ریزموضوع مستند (اقدام لازم نیست) | فایل‌های dataset بر اساس page_id (رشته) مرتب می‌شوند (قرارداد builder PCM-20.3/20.4)؛ در جلدی که عرض ارقام item_index یکنواخت نیست (vol047: ii 0..55698) ترتیب رشته ≠ ترتیب عددی. read-model در SQLite به‌صورت عددی مرتب می‌کند، پس **اثر کاربرپسند ندارد**. datasetهای pcm20_4 به‌هم‌خوردگی‌ناپذیر باقی می‌مانند؛ datasetهای جدید v0004 همان رفتار builder را برای یکدستی نگه می‌دارند. |

---

## ۴. بخش ۳.۳ — شکاف‌ها و آماده‌سازی backfill (Gate B)

**نتیجه: هیچ درخواست زنده‌ی bulkی اجرا نشد.** (قاعده‌ی Gate B مأموریت.)
جزئیات کامل در `PCM-20.7C-GAP-REPORT.md`. خلاصه با اعداد واقعی:

### 4.1 شکاف‌های بازمحاسبه‌شده (6 رنج = 45,243 صفحه)

| # | از | تا | تعداد |
|---|---:|---:|---:|
| 1 | 3,649 | 11,182 | 7,534 |
| 2 | 11,205 | 39,003 | 27,799 |
| 3 | 44,957 | 49,956 | 5,000 |
| 4 | 55,699 | 55,701 | 3 |
| 5 | 55,715 | 59,590 | 3,876 |
| 6 | 89,280 | 90,310 | 1,031 |
| **جمع** | | | **45,243** |

- gap-report `gap-report-2` (recomputed): content sha `501240608f2bac1a21fb827c8e1507b54f28cebb057e2c46ad2d9ce1f2586a24`
- fetch-plan `fetch-plan-1`: sha `b9b1c7e36a9b25edc072c94dbe59e5e909e5412ed5e9e5b159ce545b48f4902d`
  - 45,243 درخواست · 91 ران (budget 500/ران) · 188.5 ساعت روی 4 صفحه/دقیقه (~7.85 روز)
  - base_delay 15s ± jitter 0.3 · timeout 40s · retry backoff 30s×3 (حداکثر 3 تلاش)
  - User-Agent اعلام‌شده: `pct-tasnim-backfill/1.0 (read-only; corpus repair; contact: saber@ismc.ir)`
- **Probe زنده (بودجه‌ی ≤10):** 10/10 درخواست خواندنی → HTTP 200 (بودجه‌ی probe **به‌کاررفته**).

---

## ۵. بخش ۳.۴ — Headings و Hidden Context (گسترش معنایی)

**سند کامل:** `PCM-20.7C-SEMANTIC-ENRICHMENT.md`. خلاصه:

- قرارداد جدید `cs-20.7` (روی base `cs-20.6`)؛ فیلدهای جدید رکورد heading:
  `heading_id, item_index, volume_no, heading_text, next_page_id, next_page_item_index, retrieval_context, retrieval_context_summary, visibility, source_provenance`.
- سربرگ‌های کوتاه **حذف نمی‌شوند** (RETRIEEVABLE)؛ برای هر heading با صفحه‌ی بعد معتبر در همان جلد:
  خلاصه‌ی ≤3 خطی از **محتوای صفحه‌ی بعد** فقط به‌عنوان متادیتای retrieval/embedding (leakage-test شده؛ هرگز به کاربر نمایش داده نمی‌شود). متن صفحه‌ی اصلی دست‌نخورده.
- **Census واقعی (v0003):** 10,739 heading → واجدشرط **5,867** · skipped_next_too_short 4,861 · skipped_next_blank 8 · skipped_volume_end 3. طول متن صفحه‌ی بعد (واجدشرط): min 100 · p50 603 · p90 1,650 · p99 1,982 · max 2,000.
- **پایلوت طبقه‌بندی‌شده (همه‌ی 6 جلد): رأی PASS (8/8 معیار ثبت‌شده)** — 51/51 تول‌شده، 21 خطای معنایی minor ثبت‌شده، spot-check دستی 10/10، قاضی LLM مستقل.
- **اجرای کامل 5,867 رکورد:** در حال اجرا (checkpoint `data/tasnim/pcm20_5/full/summaries-full.jsonl`؛ 773/5,867 در لحظه‌ی نگارش این بخش). پس از اتمام → build `v0004` (سند: `PCM-20.7C-VERSIONING.md`).

---

## ۶. بخش ۳.۵ — Topics و Surahs

### 6.1 Topics — تأیید‌شده ✅

- **شمارش canonical: 1,080 موضوع** — با `normalize_topic` = **tasnim-topic-norm/1.0**
  (کد واقعی read-model: `web/readmodel.py`):
  strip → ارقام ۰-۹/٠-٩→ASCII → collapse whitespace → حذف پیشوند عددی (دوباره، مطابق fact-check) → یکدست‌سازی همزه → حذف ` .:ـ-` از انتها.
- `topic_id = "t-" + sha1(normalized)[:12]`.
- بازتأیید مستقل روی `heading-records.jsonl` واقعی v0003: **1,080** (مطابق گزارش — `.tmp_pcm207c_topics_canonical.json`).

| جلد | موضوعات متمایز |
|---|---:|
| vol001 | 1 |
| vol012 | 5 |
| vol047 | 293 |
| vol056 | 608 |
| vol080 | 44 |
| volkeyd531f422 | 203 |
| **جمع** | **1,154** (بیش از 1,080 چون موضوعات بین جلد مشترک‌اند — مورد انتظار) |

**25 موضوع برتر (شمارش canonical واقعی):**

| موضوع | n | موضوع | n |
|---|---:|---|---:|
| تفسیر | 1,678 | پیش گفتار | 79 |
| گزیده تفسیر | 1,677 | خطوط کلی معارف سوره | 77 |
| مفردات | 1,631 | زمان و مکان نزول | 76 |
| تناسب آیات | 1,514 | هدف سوره | 75 |
| بحث روایی | 1,302 | فضای نزول | 66 |
| اشارات و لطایف | 991 | نام ها و اوصاف سوره | 56 |
| شأن نزول | 182 | فهرست موضوعات | 33 |
| غرر آیات | 79 | فضیلت تلاوت | 20 |

نکته‌ی یکدست‌سازی: `گزیدهٔ تفسیر/گزیده تفسیر/گزیدهٴ تفسیر` → یک موضوع (1,677)؛
`1. شأن نزول` + `شأن نزول` → 182. (نمایش در UI: پرتکرارترین فرم raw، در تساوی: کوچک‌ترین lexicographic.)

### 6.2 Surahs — رأی: **NOT_SUPPORTED** (به‌عنوان نشانگر سازه‌ای/heading)

**سند کامل:** `PCM-20.7C-SURAH-ASSESSMENT.md`. خلاصه‌ی شواهد:

| مدرک | مقدار |
|---|---:|
| heading با عنوان صریح سوره (قاعده‌ی ثبت‌شده: متن heading = نام سوره / «سوره(ت) X» / «تفسیر(ر) سوره(ت) X»، NFKC) | **0** |
| اشاره‌ی «سوره X» در heading (regex) | 0 |
| نام سوره در خط اول محتوای صفحه‌ی heading | 0 |
| headingهای عمومی شامل «سور» (مثلاً «هدف سوره»، «خطوط کلی معارف سوره») | 274 — **مورد رد** (هم‌رویدادی کلمه، نه نام سوره) |

**پیراسته‌ی صادقانه:** کتاب در ساختار سوره‌ای است؛ 33 سربرگ «فهرست موضوعات» (vol047: 5/40، vol056: 21/216، volkey: 7/46) با 302 صفحه‌ی فرزند که 300 آنها نام سوره در **متن بدنه** دارند (116 نام متمایز) — این «محتوای بدنه» است، نه نشانگر سازه‌ای؛ استخراج surah←محدوده‌ی صفحه از صفحات فهرست **فرصت آینده** ثبت شد. Self-test matcher: 18/18. مسیر UI فعلی صادقانه است (`web/templates/surahs.html`: «هیچ دادهٔ سوره‌ای ساخته نمی‌شود…»). **فیلد surah در cs-20.7/v0004 اضافه نمی‌شود.**

---

## ۷. بخش ۳.۶ — تصاویر و متادیتا — رأی: **NOT_AVAILABLE**

**پرسش مأموریت:** آیا تصویر/اسکن صفحه یا متادیتای غنی‌تر از متن در دسترس است؟
**پاسخ صادقانه:** خیر — منبع text-only است.

### 7.1 شواهد (read-only، روی v0003)

1. **کلیدهای رکورد page** (16 کلید): `barg, captured_at, content_hash, item_index, metadata, page_id, position, quality_status, raw_barg, semantic, source_page_id, text, text_normalized, url, volume, volume_id` — **هیچ فیلد تصویر-مانندی** (image/scan/pdf/ocr-image/attachment).
2. **کلیدهای رکورد heading** (15 کلید): `children_page_ids, heading_hash, heading_text, item_index, next_page_id, page_id, parent_heading_page_id, provenance, record_id, record_kind, source_class, visibility, volume_id, volume_no, volume_title` — **هیچ فیلد تصویر-مانندی**.
3. **شکل `metadata` یکنواخت** — نمونه‌گیری 2,000 صفحه: 2,000/2,000 با کلیدهای
   `{barg_raw, captured_at, content_hash, export_barg, item_index, section, url, values_keys}`
   و `values_keys = [«ادرس صفحه», «برگ», «لینک صفحه بعد», «لینک صفحه قبل», «متن»]` — **فقط متن** (`.tmp_pcm207c_meta_sample.json`).
4. **جلدها:** `web/cover.py` SVG قطعی 600×800 (بدون raster، بدون شبکه) با برچسب اجباری
   **«نمایهٔ اختصاصی — جلد رسمی نیست»**؛ `cover_source` همیشه `"generated-svg"`.
   پس تنها «تصویر» موجود در کل سیستم، 6 جلد SVG **ساخته‌شده** است — نه تصویر منبع.

### 7.2 نتیجه

- **تصویر منبع: NOT_AVAILABLE** (API/اسنپ‌شات فقط payload متنی دارد).
- هیچ ادعای «OCR از تصویر» یا «بازیابی تصویر» در این فاز وجود ندارد و در v0004
  فیلد تصویری **ساخته نمی‌شود**. اگر در آینده تصویر منبع در دسترس شود، باید به‌عنوان
  نسخه‌ی جدا با provenance خودش اضافه شود.

---

## ۸. فهرست شواهد (فایل‌های واقعی)

| فایل | محتوا |
|---|---|
| `.tmp_pcm207c_verify.json` | 46 چک (0 FAIL) + findings + reported_vs_real |
| `.tmp_pcm207c_v0003_immutability.json` | SHAهای قفل‌شده‌ی v0003 |
| `.tmp_pcm207c_plan_facts.json` | رنج‌های شکاف + پارامترهای fetch-plan |
| `.tmp_pcm207c_probes.json` | 10/10 probe HTTP 200 |
| `.tmp_pcm207c_pilot_census.json` | census واقعی 10,739/5,867 + طول‌ها |
| `.tmp_pcm207c_surah_evidence.json` | شواهد surah + self-test 18/18 + findings + reported_vs_real |
| `.tmp_pcm207c_index_scan.json` | اسکن فهرست موضوعات (33/302/300/116) + field probe |
| `.tmp_pcm207c_topics_canonical.json` | 1,080 canonical + top-25 (tasnim-topic-norm/1.0) |
| `.tmp_pcm207c_meta_sample.json` | 2,000 نمونه‌ی metadata (text-only) |

## ۹. روش بازتولید

```bat
cd c:\Users\s.tabatabaei\Documents\saberprojects\persian-corpus-toolkit
.venv\Scripts\python.exe -X utf8 .tmp_pcm207c_verify.py
.venv\Scripts\python.exe -X utf8 .tmp_pcm207c_topics_canonical.py
.venv\Scripts\python.exe -X utf8 .tmp_pcm207c_meta_sample.py
.venv\Scripts\python.exe -X utf8 .tmp_pcm207c_index_scan.py
```

(همه read-only؛ هیچ‌کدام روی داده‌ی production یا v0003 نوشته نمی‌کنند.)

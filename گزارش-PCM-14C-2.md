# گزارش PCM-14C.2 — ممیزی قالب JSON و مسیر Export به Dump؛ فقط بررسی

- **تاریخ:** 2026-10-28 (14:15–14:45 به‌وقت تهران)
- **نوع:** فقط بررسی/مستندسازی/مقایسه/پیشنهاد — **بدون تغییر کد، بدون تغییر Production، بدون Commit/Push/Deploy**
- **مبتنی بر شواهد واقعی:** خروجی‌های واقعی Word Factory در `wf-out/` (Local) و `data/knowledge/out/` (s52)، کد فعلی `2ad6c53`/`7f21fb0`، و ممیزی‌های فقط‌خوانده

---

## ۱. خروجی واقعی Word Factory — Schema، فیلدها، شناسه‌ها، متادیتا، ساختار متن/بلوک‌ها

### ۱.۱ محل خروجی‌های واقعی
- **Local:** `wf-out/run/`، `wf-out/run-bank/`، `wf-out/run-bank2/`، `wf-out/run-bank3/` — ۴ اجرای واقعی روی ۲ فایل واقعی (`namous.docx` 6 MB، `bank-ehterafat.docx` 147 KB) — gitignored، فقط روی دسکتاپ.
- **s52:** `data/knowledge/out/<file_id>/` — ۸ دایرکتوری (بررسی‌شده در PCM-14C.1؛ 32/32 SHA خروجی‌ها با مانیفست‌ها مطابقت).
- **دسترسی API فعلی:** خروجی‌ها از طریق endpointهای موجود سرویس می‌شوند ( [`/api/knowledge/documents/<id>/blocks`](backend/knowledge_api.py:1060)، `/structure`، `/quality`، `/file`) — یعنی «dump» برای Word Studio حتی نیازی به دسترسی مستقیم به فایل ندارد.

### ۱.۲ هر اجرا ۵ فایل دارد (از [`factory/export.py`](backend/factory/export.py:76) + شواهد واقعی)

| فایل | محتوا (واقعی) |
|---|---|
| `manifest.json` | `manifest_version:"m-1"`، `schema_version:"wf-schema-1"`، بلوک `file` (file_id/filename/size_bytes/sha256/format/detected_by/created_at)، `work_id/edition_id/volume_id`، `versions:{parser:"p-1",normalizer:"n-1"}`، `processing:{status,error,started_at,finished_at,duration_ms}`، `outputs:{...: {path, sha256}}` برای هر ۴ خروجی دیگر، `counts:{blocks,total_chars}`، `quality:{score,status}` |
| `document.json` | `schema_version`، `file`، ۳ ID، `parser_version`/`norm_version`، `metadata`، `structure`، فهرست `blocks[]` (فیلدهای ساختاری: block_id/block_index/type/style/heading_level/parent_block_id/position/source_ref/page/processing_status/quality_status) |
| `blocks.jsonl` | **هر خط = یک بلوک کامل** (نمونه واقعی از `wf-out/run/f-4fe7c707/blocks.jsonl`): |
| `quality-report.json` | `passed/score/status/checks[8]/metrics/unextracted/warnings` |
| `report.md` | گزارش انسانی فارسی |

**نمونه واقعی بلوک** (از `wf-out/run-bank3/f-c0167d25/blocks.jsonl` خط ۳):
```json
{"block_id":"b00002:paragraph","block_index":2,"type":"paragraph",
 "raw_text":"سرشناسه:مرکز تحقیقات رایانه ای قائمیه اصفهان،1390 …",
 "style":"Normal","parent_block_id":null,"position":2,"source_ref":null,"page":null,
 "normalized_text":"سرشناسه:مرکز تحقیقات رایانه‌ای قائمیه اصفهان،1390 …",
 "norm_version":"n-1","content_hash":"sha256:069deabd0c6d341b"}
```
(در این نمونه، نیم‌فاصله در normalized اضافه شده — قانون `zwnj`؛ RAW دست‌نخورده.)

### ۱.۳ شناسه‌ها (همگی deterministic — از [`factory/models.py:229`](backend/factory/models.py:229))
| ID | الگو | نمونه واقعی |
|---|---|---|
| file_id | `f-` + sha256(sha256 فایل) [:8] | `f-c0167d25` |
| work_id | `w-` + sha256("title\|author" کوچک‌شده) [:8] — اگر title/author نبود: sha256 فایل | `w-37f8bb58` |
| edition_id | `e-` + sha256(work_key\|file_sha256) [:8] | `e-223c4083` |
| volume_id | `v-` + sha256(edition_id\|volume_no) [:8] — **null اگر volume استخراج نشد** (حدس ممنوع) | `null` در هر دو نمونه واقعی |
| block_id | `b{block_index:05d}:{type}` | `b00022:heading` |
| content_hash | `sha256:` + sha256(normalized_text) [:16] | `sha256:069deabd0c6d341b` |

### ۱.۴ متادیتا (extract-only — ۹ فیلد ثابت)
از [`factory/metadata.py`](backend/factory/metadata.py:51): هر فیلد `{value, source_ref: core-properties|frontmatter|absent, confidence: 0..1, flag: absent?}`. نمونه واقعی `bank-ehterafat.docx`: `author="Amoozesh" (0.9)` و بقیه `null/absent` — **حدس صفر**. `volume_no` فقط با regex جلد (محدودیت فعلی: ۱–۶).

### ۱.۵ ساختار و کیفیت
- `structure`: `headings[]` (block_id/level/text/parent_block_id)، `chapters[]` (H1)، `front_matter_blocks`، `confidence`، `notes[]` (مثال واقعی: "no headings found — document is flat").
- `quality-report`: **۸ check ثابت** (file_openable, sha256_verified, non_empty_text, block_order_contiguous, tables_present, persian_content, headings_detected, **no_fabricated_pages**) + `metrics` (persian_ratio واقعی: 0.9994 در نمونه) + `unextracted.losses` (نمونه واقعی `namous.docx`: `{"image":10,"drawing":10}` → warning).

### ۱.۶ ⚠️ یافته‌ی مهم ممیزی: پایداری نرمال‌سازی بین runهای توسعه
مقایسه‌ی فقط‌خوانده‌ی دو اجرای واقعی **همان فایل** (941 بلوک):
- `wf-out/run-bank` (13:46) در مقابل `wf-out/run-bank3` (13:50): **41 بلوک** در `normalized_text` و `content_hash` متفاوت‌اند (RAW در هر دو run عینا‌ً یکسان).
- **تحلیل دقیق** (با اجرای مجدد نرمال‌ساز فعلی روی هر 41 بلوک): 41/41 خروجی `run-bank` دقیقاً با سیاست `nfkc=True` و 41/41 خروجی `run-bank3` دقیقاً با **کد فعلی** (`nfkc=False` پیش‌فرض) مطابقت دارند.
- **تفسیر:** این دو run مربوط به **ایتریشن‌های توسعه‌ی قبل از commit نهایی PCM-13** (`263dc0d` — 13:32 همون روز) هستند؛ در آن زمان کد موقت NFKC روشن بوده و بعداً به «خاموش» (سیاست فعلی و مصوب) برگشته.
- **نتیجه برای قرارداد:** (1) کد فعلی deterministic است و خروجی‌های فعلی قابل اتکا‌اند؛ (2) **سیاست نرمال‌سازی باید در manifest ثبت صریح شود** (امروز فقط `normalizer:"n-1"` است و آرایه‌ی کامل policy نه) — پیشنهاد §۶؛ (3) `norm_version` باید با هر تغییر policy تغییر کند (قاعده‌ی موجود در مستندات، اما هنوز در manifest policy خود ثبت نمی‌شود).

---

## ۲. ممیزی همه‌ی اسکریپت‌ها و مستندات dump/export/ES/JSONL

### ۲.۱ اسکریپت‌های موجود (کد واقعی)
| فایل | وظیفه | ورودی → خروجی | وابستگی |
|---|---|---|---|
| [`corpus/build_corpus.py`](corpus/build_corpus.py:13) | ساخت پیکره‌ی **اصطلاح‌نامه** (نه کتاب‌های Word) | جدول `crawled_data` (DB) → `output/thesaurus_raw_corpus.txt` + `thesaurus_corpus.jsonl` + `thesaurus_terms.txt` + README HF | فقط sqlite3 |
| [`corpus/build_dataset.py`](corpus/build_dataset.py:1) | دیتاست فاین‌تیون | همان داده‌ها → `chatml/alpaca/completion.jsonl` | فقط stdlib |
| [`corpus/upload_to_hf.py`](corpus/upload_to_hf.py:1) | آپلود به HuggingFace | فایل‌های بالا | (اختیاری) |
| [`backend/factory/cli.py`](backend/factory/cli.py:47) | اجرای آفلاین Word Factory | یک `.docx` → ۵ فایل §۱.۲ | python-docx |
| [`backend/server.py`](backend/server.py:1326) | سرویس خروجی‌های corpus در داشبورد | فایل‌های output → فهرست + دانلود | — |
| [`deploy/pcm12_2_corpus_test.sh`](deploy/pcm12_2_corpus_test.sh:1) | تست آفلاین build روی snapshot DB | بکاپ آنلاین → build در /tmp → اعتبارسنجی JSONL → پاک‌سازی | فقط‌خوانده نسبت به production |

### ۲.۲ مستندات مرتبط
| سند | بخش مرتبط |
|---|---|
| [`docs/PCM-12-DATA-CONTRACTS.md`](docs/PCM-12-DATA-CONTRACTS.md:231) | **§2 قرارداد خروجی‌های Factory (JSONL)** — الگوری raw/normalized/chunks + `chunk_id` deterministic `kw_<work>_<edition>_<vol>_<seq6>`؛ **§3 ES Mapping (test index)**؛ **§7** تبادل داده فقط از طریق JSONL/Parquet export یا alias |
| [`docs/PCM-12-PRD.md`](docs/PCM-12-PRD.md:114) | **Export: JSONL logical export هر index version** + قانون صریح: **«dump هرگز پیش‌نیاز RAG نیست»** |
| [`docs/PCM-12-ARCHITECTURE.md`](docs/PCM-12-ARCHITECTURE.md:204) | جدول Backup/Export: ES snapshot (DR خود ES) در مقابل **JSONL/Parquet export (تبادلم/ممیزی/migration)** + تعریف «Corpus Version» = مجموعه JSONL با manifest hash |
| [`docs/PCM-13-ACCEPTANCE.md`](docs/PCM-13-ACCEPTANCE.md:115) | شواهد WF-08/09/10 (مانیفست، JSONL، idempotency) |
| [`docs/PCM-12-AUDIT.md`](docs/PCM-12-AUDIT.md:114) | الگوی سازمانی قبلی `automated/export-sql-chromadb` (mesbahyazdi `book_pages` → Chroma) — **خارج از scope، فقط الگو** |

---

## ۳. آیا قالب خروجی Elasticsearch در کد یا نمونه‌های واقعی تعریف شده؟

**پاسخ صریح:**
- ❌ **هیچ mapping واقعی/اجرای‌شده وجود ندارد.** هیچ ES روی s52 نیست (تأییدشده در PCM-14C.1: نه کانتر، نه 9200/9300). هیچ اندکس واقعی PCT وجود ندارد که mapping آن قابل خواندن باشد.
- ❌ **هیچ client ES در کد نیست:** [`backend/requirements.txt`](backend/requirements.txt:1) فقط `flask`، `flask-cors`، `python-docx` است.
- ⚠️ **یک «قالب» فقط به‌عنوان طراحی در مستندات وجود دارد:** [`docs/PCM-12-DATA-CONTRACTS.md`](docs/PCM-12-DATA-CONTRACTS.md:262) §3 — mapping **chunk-based** (نه block-based) با `dense_vector` 1024، analyzer `persian`، `index_version`/alias strategy `pct_test_v1 → pct_test`. این **طرح V0.2** است، نه واقعی؛ و فرض‌های تصمیم‌نشده در دل دارد (مدل embedding، ابعاد 1024/2560).
- ⚠️ الگوی سازمانی قبلی (mesbahyazdi → Chroma، صفحه‌به‌صفحه با HTML خام) خارج از scope است و **قالب PCT نیست** (طبق §7 DATA-CONTRACTS فقط یک «prior art»).

→ **نتیجه: برای «قالب قبلی» چیزی برای تطبیق وجود ندارد؛ قرارداد خروجی فعلی PCT = JSONL/Fایل‌های §۱ (مستند و با hash) است و ES-compatibility هنوز NOT_VERIFIED/طراحی است.** (همان وضعیت PCM-14C.1، بدون هیچ تقدم.)

---

## ۴. مقایسه‌ی دو مسیر

### مسیر A: `Word Factory → JSON/JSONL → Dump`
| معیار | وضعیت |
|---|---|
| پیاده‌سازی | ✅ **کاملاً موجود و تست‌شده** (5 خروجی، hash هر خروجی در manifest، 103/103 تست، سناریوی 40/40 روی production) |
| وابستگی | ✅ صفر (stdlib + python-docx؛ همین‌ها در requirements فعلی) |
| نیاز به ES | ❌ هیچ |
| تعیین‌پذیری | ✅ (به‌جز نکته‌ی §۱.۶ که با ثبت policy در manifest حل می‌شود) |
| قابلیت ممیزی/تبادلم | ✅ hash هر فایل + counts + versions در manifest = «Corpus Version» آماده (طبق ARCHITECTURE §S4) |
| مصرف‌کننده‌ها | Word Studio (API)، کراول‌کردن مجدد، migration، RAGهای خارجی (طبق §7 DATA-CONTRACTS: **تبادل فقط از طریق JSONL/Parquet**) |
| فاصله تا «dump آماده» | یک اسکریپت جمع‌کننده: `data/knowledge/out/*/blocks.jsonl + document.json + manifest.json` → یک آرشیو/JSONL تجمیعی با manifest سطح بالا |

### مسیر B: `Word Factory → قالب سازگار با ES → Dump`
| معیار | وضعیت |
|---|---|
| پیاده‌سازی | ❌ هیچ — نه ES، نه client، نه chunker، نه embedder، نه bulk writer |
| وابستگی جدید | ❌ ES container (+ volume، + RAM)، Python client ES، مدل embedding (تصمیم J4 هنوز باز است) |
| مراحل اضافی لازم | chunking policy `c-1` (500/50 token) + embedding + mapping PUT + bulk + alias |
| ریسک | حجم تغییر + سطح attack surface + تصمیم owner (D1/D2 از PCM-14C.1 هنوز باز) |
| مزیت | جستجوی semantic در آینده |

### جمع مقایسه
- مسیر A **همین حالا** قابل اجرا و قابل اعتماد است؛ مسیر B **۴ تصمیم باز + زیرساخت + کد جدید** دارد.
- نکته‌ی کلیدی معماری: در مسیر B هم، **منبع حقیقت همان JSONL مسیر A است** — لایه‌ی ES فقط یک **تبدیل‌کننده‌ی فرادستی** (JSONL → bulk payload) است و هرگز جایگزین آن نمی‌شود. پس انتخاب مسیر A هیچ راهی را قفل نمی‌کند.

---

## ۵. پیشنهاد

**مسیر A — `Word Factory → JSONL → Dump` به‌عنوان قرارداد رسمی خروجی (Canonical Export)**، با این ویژگی‌ها:
1. **بدون نصب Elasticsearch** و **بدون وابستگی جدید** (قید مأموریت).
2. **بدون قفل روی آینده:** لایه‌ی ES-compatible بعداً (PCM-14D) به‌صورت **converter** از همین JSONL ساخته می‌شود؛ contract JSONL سوپرست است (block-level → chunking c-1 روی آن قابل انجام است).
3. **اصلاح کوچک پیشنهادی (فقط در PCM-14C.3+، الان اجرا نمی‌شود):**
   - `norm_policy` کامل (آرایه‌ی rules فعال) در `manifest.json` ثبت شود → رفع ابهام §۱.۶؛
   - `block_count/char_count` روی ردیف DB (همان M4 در PCM-14C.1) تا dump بدون بازخوانی JSONL قابل شمارش باشد.

**تعریف «Dump» (مطابق مستندات موجود، نه اختراع):**
- **Dump logical** = مجموعه‌ی JSONL/JSON + manifest (hash + counts + versions) — برای تبادلم، ممیزی، migration، backup.
- **قانون موجود (PRD):** «dump هرگز پیش‌نیاز RAG نیست» — RAG با alias زنده سرویس می‌کند؛ dump فقط برای interchange/DR.
- فرمت پیشنهادی: **یک دایرکتوری/آرشیو با `dump-manifest.json`** (فهرست فایل‌ها + sha256 + counts + versions + timestamp) — نه یک فایل غول‌پیکر.

---

## ۶. قرارداد خروجی (پیشنهاد رسمی)

### ۶.۱ نمونه‌ی ورودی → خروجی
**ورودی:** یک فایل `.docx` (مثال واقعی: `bank-ehterafat.docx`، 147,180 B، sha256 `27fcf603…`).
**خروجی:** ۵ فایل §۱.۲ در `out/<file_id>/` + (در نسخه‌ی dump) `dump-manifest.json` جمع‌کننده.

### ۶.۲ نگاشت فیلدها (JSONL فعلی → مقصود)
| فیلد JSONL | نقش | مقصد ES (اگر روزی ساخته شود) |
|---|---|---|
| `block_id` | شناسه‌ی پایدار بلوک (با ریسک type-in-id — D5 از 14C.1) | `block_id` keyword |
| `block_index`/`position` | ترتیب قطعی | `seq` integer |
| `type` | نوع بلوک (9 نوع ثابت `BLOCK_TYPES`) | `type` keyword |
| `raw_text` | **RAW — منبع حقیقت** | `raw_text` (index:false) |
| `normalized_text` + `norm_version` | نسخه‌ی standard | `text` (analyzer فارسی) |
| `content_hash` | dedup/idempotency | `content_hash` keyword |
| `page` | همیشه `null` در docx (حدس ممنوع) | غایب/null |
| `source_ref` | مرجع داخلی (موجود: dict) | `source_ref` object |
| `work_id/edition_id/volume_id` (document.json) | شناسه‌های سلسله‌مراتب | keywordها |
| `metadata.fields` (9 فیلد + confidence) | کتاب‌شناسی extract-only | object با dynamic:strict |
| `manifest.outputs.*.sha256` | اعتبارسنجی هر فایل | — (سطح dump) |

### ۶.۳ سیاست نسخه‌بندی Schema
- ۴ نسخه‌ی مستقل: `wf-schema-N` (ساختار خروجی) · `p-N` (parser) · `n-N` (normalizer) · `m-N` (manifest) — امروز همه در نسخه‌ی 1.
- **قاعده:** هر تغییر رفتار → افزایش نسخه؛ خروجی‌های قدیمی با نسخه‌ی قدیم **حذف نمی‌شوند** (additive)؛ `manifest.json` تنها مرجع نسخه‌های هر اجرا است.
- **افزایش پیشنهادی:** `norm_policy: {rules: [...]}` در manifest (رفع §۱.۶) — به‌عنوان بخشی از `m-2`.

### ۶.۴ حفظ متن اصلی
- RAW در `raw_text` **دست‌نخورده** (تست `sha256_verified` + `no_fabricated_pages` در هر quality-report)؛ normalized فقط نسخه‌ی موازی؛ guard `verify_no_semantic_change` روی هر بلوک (در صورت شکست → `manual_review`).

### ۶.۵ شناسه‌های پایدار
- `f-/w-/e-/v-` deterministic (§۱.۳) → reprocess با همان sha256 = همان IDها (تست WF-10 واقعی: 2 run → `same file_id`, `same blocks_hash`).
- **باقی‌مانده (از 14C.1):** `block_id` v2 (بدون type) + رجیستری صریح Work/Edition/Volume — هر دو در نقشه‌ی M7/M1-M3، **اجرا نمی‌شود تا تصویب**.

### ۶.۶ معیارهای تست (برای مرحله‌ی پیاده‌سازی)
1. هر خط `blocks.jsonl` JSON معتبر با کلیدهای قرارداد (تست WF-09 موجود).
2. `sha256` هر خروجی با `manifest.outputs` مطابقت (تست WF-08 موجود) + **`dump-manifest.json`** هم همین قانون را دارد.
3. reprocess idempotent: 2 بار → همان `blocks_hash` (WF-10).
4. `page` در 100% بلوک‌های docx = null (check `no_fabricated_pages`).
5. RAW هر بلوک == محتوای استخراج‌شده از docx (round-trip با python-docx در محیط تست).
6. شمارش dump (blocks/chars) == مجموع شمارنده‌های واقعی (قاعده‌ی §2.9 AGENTS.md).
7. normalize determinism: اجرای دوباره‌ی کد فعلی روی 50 بلوک نمونه → 0 تفاوت (رفع §۱.۶ به‌صورت test).
8. هیچ تستی روی `thesaurus.db` production یا `data/knowledge` s52 ننویسد.

---

## ۷. وضعیت سه محیط (لحظه‌ی نگارش — بدون هیچ تغییر)

### Local (ویندوز)
- `HEAD = origin/main = 7f21fb0`؛ tracked files **بدون هیچ تغییر**.
- untracked: 5 اسکریپت `deploy/pcm14c1_*` + `گزارش-PCM-14C-1.md` + همین گزارش.
- `wf-out/` (gitignored): ۴ اجرای واقعی + ۵ اسکریپت/خروجی تحلیل فقط‌خوانده‌ی همین مأموریت (`pcm14c2_sample_dump.*`، `pcm14c2_diff_*.json`).
- آزمون‌ها: 103/103 OK (PCM-14C.1؛ کد دست‌نخورده).

### GitHub
- `main = 7f21fb0` (همان Local). `git diff --stat 2ad6c53..7f21fb0 -- backend/ dashboard/ docker-compose.yml extension/` = خالی.

### s52 (Production)
- کد: `2ad6c53` (اثبات‌شده PCM-14C.0)؛ کانتر `Up 20 hours`؛ `PRAGMA integrity_check = ok`.
- **کراول زنده دست‌نخورده:** پروژه ۲ «تفسیر تسنیم همتا» status=`running`، `saved_count=28,389`، `updated_at=2026-10-28 14:44:49` (در حال رشد — از 27,432 در صبح به 28,389 در این لحظه).
- 7 جدول Knowledge: 0 ردیف؛ `data/knowledge/` دست‌نخورده (21 فایل یتیم ممیزی‌شده در 14C.1، بدون هیچ تغییر).
- **هیچ** Commit/Push/Deploy/تغییری در این مأموریت انجام نشده است.

---

## ۸. برای قطعی‌کردن قرارداد خروجی، چه نمونه‌ای از کاربر نیاز داریم؟

| # | نمونه/تصمیم مورد نیاز | چرا |
|---|---|---|
| **N1** | اگر سازگاری با ES در اولویت است: **یک نمونه واقعی** از اندکس مقصد/قبلی — یعنی خروجی `GET /<index>/_mapping` + `GET /<index>/_settings` + ۲-۳ سند نمونه (`_source`) از همان اندکس | بدون این، هر قرارداد ES صرفاً طراحی مانده (وضعیت NOT_VERIFIED فعلی). همین نمونه، مقایسه‌ی فیلدبه‌فیلد `COMPATIBLE/MIGRATION_REQUIRED/UNKNOWN` (PCM-14C.1 §۳.۳) را ممکن می‌کند |
| **N2** | تأیید اینکه **مسیر A (JSONL = قرارداد رسمی خروجی)** با تعریف §۵ پذیرفته است | پایه‌ی PCM-14C.3 (اسکریپت dump + `dump-manifest.json` + `norm_policy` در manifest) |
| **N3** | انتخاب: dump = **آرشیو دایرکتوری با manifest** (پیشنهاد) یا **JSONL تجمیعی تک‌فایل** | فرمت فیزیکی interchange |
| **N4** | (اختیاری) یک `.docx` واقعی بزرگ/پیچیده (جدول + پاورقی + چند جلد) به‌عنوان **golden fixture** برای تست قرارداد — امروز فقط ۲ فایل واقعی کوچک + فیکسچرهای مصنوعی داریم | پوشش test matrix §۶.۶ روی ساختارهای نادر (table/footnote/multi-volume) |
| **N5** | تصمیم D1 از PCM-14C.1 (سرنوشت ES) — اگر (الف) انتخاب شد، N1 را هم بفرستید | مسیر B فقط بعد از این تصمیم معنا دارد |

---

*پایان گزارش PCM-14C.2 — فقط بررسی؛ بدون تغییر کد/Production؛ بدون Commit/Push/Deploy.*

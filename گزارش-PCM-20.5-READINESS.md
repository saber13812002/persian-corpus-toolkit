# گزارش ممیزی آمادگی PCM-20.5 (Readiness Audit)

- **تاریخ:** ۲۰۲۶-۱۱-۰۵ (UTC)
- **مأموریت مادر:** PCM-20.5 — ممیزی آمادگی، **سخت‌گیرانه READ-ONLY**؛ پاسخ به سؤال: *آیا پیکره/دیتاست/دامپ تسنیم آماده ورود به Neo4j با embedding واقعی و اتصال به RAG است؟*
- **دامنه:** زنجیره ۱۰ مرحله‌ای `Snapshot → Canonical Corpus → Semantic Corpus → Dataset → JSON/JSONL → AI Dump → Embedding → Neo4j → RAG → Chat`
- **روش:** ۴ زیرمأموریت — **S1** داده (SHA/شمارش، `.tmp_pcm205_readiness_s1.json`)، **S2** کد (builder/loader/RAG/adapter)، **S3** git + مستندات + زیرساخت embedding، **S4** ترکیب (این گزارش).
- **رعایت read-only:** هیچ تغییری در داده/کد/مستندات؛ هیچ عملیات git (این گزارش UNTRACKED می‌ماند)؛ هیچ رمزی در گزارش (فقط محل + نوع اعتبارنامه‌ها)؛ شبکه فقط پروب‌های ≤۵ثانیه در S3.
- **سازشده نداشتن:** هیچ یافته stop-condition خودترقیق‌شده نیست — همه در §2.11 مستند شده‌اند و منتظر تصمیم کاربر‌اند.

---

## جزء ۱ — سطح مدیریت (≤۲ صفحه)

### کجاییم
تا PCM-20.4 و PCM-20.5 GATE 0–1، زنجیره داده کامل و نسخه‌شده‌ی «تفسیر تسنیم» روی دیسک موجود است: snapshot واقعی ۴۵٬۸۴۴ صفحه (SHA-256 `fd927b66…`، ۷۲.۹MB)، پیکره‌ی canonical v0001 (SHA `ee87686a…`)، پیکره‌ی معنایی v0002 بر پایه قرارداد cs-20.5 (SHA `12a93e21…`، ۱۰٬۷۲۸ رکورد context پنهان)، ۶ دیتاست طبقه‌ای و ۳ AI Dump. هر ۷ build پیکره `content_sha_match: true` (صفر ناسازگاری در کل زنجیره)؛ تست‌ها سبز (۲۷/۲۷ tasnim+semantic در بازپیمایش S1؛ ۲۱۶ تست در PCM-20.4).

### چه چیزی واقعاً آماده است
- ✅ **Snapshot منبع** + زنجیره provenance (۴۵٬۸۴۴ صفحه؛ SHA تأییدشده، `record_count_verified`)
- ✅ **Canonical Corpus v0001** — واقعی، idempotent (REUSED)، قطعی cross-root (سه ریشه، یک content SHA)
- ✅ **Semantic Corpus v0002** — طبقه‌بندی ۶گانه + ۱۰٬۷۲۸ رکورد context پنهان (verbatim، بدون LLM)
- ✅ **۶ دیتاست** (1/10/50/90/100٪ + تک‌جلدی vol56) — همه از corpus v0001، سیاست `stratified-even-blocks`
- ✅ **AI Dump Builder به‌عنوان کامپوننت** — 3/3 DUMP_VALIDATED (با embedding **mock**)
- ✅ **اسکلت Neo4j loader + اپ RAG** — کلکشن‌سوییچ، references، admin

### چه چیزی ناقص/مسدود است
- ❌ **Embedding واقعی:** صفر بردار واقعی برای تسنیم؛ هر ۳ دامپ ۱۰۰٪ **mock** (backend=mock، dim 1024)
- ❌ **دیتاست/دامپ معنایی:** هیچ دیتاستی از v0002، هیچ دامپی semantic — هر ۳ دامپ stale (بر پایه v0001)
- ❌ **Neo4j Import:** هیچ host قابل‌دسترس (s52 همه‌پورت timeout؛ machine محلی بدون Docker/Neo4j)
- ❌ **Gap داده:** ۴۵٬۲۴۳ صفحه بدون `item_index` در ۶ بازه، وضعیت `unresolved` — بازیابی = re-crawl زنده، مسدود به s52
- ⚠️ **RAG برای تسنیم آماده نیست:** مسیر specific-book با `int(book_id)` شکسته، نمایش URL واقعی نه، hidden-context نه، جستجوی چندکلکشنی نه

### آیا تسنیم همین‌الان می‌تواند به Neo4j برود؟ → **خیر**
Embedding واقعی وجود ندارد؛ دامپ‌ها mock + stale‌اند؛ loader هنگام بارگذاری re-embed می‌کند و ۹ فیلد provenance را می‌ریزد؛ host Neo4j قابل‌دسترس نیست.

### آیا می‌تواند به RAG متصل شود؟ → **خیر، مشروط**
اسکلت موجود است ولی اتصال معتبر فقط پس از ۷ پیش‌شرط §۴ ممکن است (embedding واقعی، دامپ semantic، DB ایزوله، اصلاحات book_id/URL/hidden).

### ۵ ریسک بزرگ‌تر (هرکدام یک خط)
1. **Mock→real silent reuse:** reuse-map builder فقط `sha1(model+text)` است — build «واقعی» با همان برچسب model به‌صورت خاموش بردارهای mock را بازمی‌گذارد و از validate عبور می‌کند.
2. **SPOF روی s52:** همه configها به `172.20.1.52:4000/v1` اشاره دارند؛ s52 اکنون کاملاً down (همه پورت timeout).
3. **دامپ‌های mock + stale:** هیچ دامپ معتبری برای corpus معنایی وجود ندارد.
4. **اتلاف provenance در گراف:** loader هر ۹ فیلد provenance تسنیم را می‌ریزد؛ URL منبع در نتایج نیست.
5. **API key در تاریخ git:** `rag/graph-rag/app/config.json` (tracked) دارای ۳ فیلد `api_key` (len=25) و در تاریخ repo است.

### تصمیم بعدی
**پیش‌شرط‌های سخت (جزئیات §۴):** (۱) تصمیم دسترسی — بازگشت s52 یا راه‌اندازی LiteLLM روی s53؛ (۲) تصمیم model/dim — یک هویت واحد، تأییدشده در runtime؛ (۳) گارد reuse-map در builder؛ (۴) تصمیم loader — مصرف `embedding` دامپ یا پذیرش رسمی re-embed-at-load؛ (۵) دامپ semantic از v0002 (GATE 2)؛ (۶) DB مستقل Neo4j به‌ازای هر نسخه (GATE 3)؛ (۷) اصلاحات RAG — string book_id، نمایش URL، فیلتر hidden (GATE 4).
**پیشنهاد مأموریت بعدی:** `PCM-20.6: Real embedding + isolated Neo4j + RAG connection (GATE 2–4 execution)` — با ۷ پیش‌شرط بالا به‌عنوان entry checklist؛ **آغاز نشده** (جزئیات §۴).

---

## جزء ۲ — سطح فنی

### 2.1 جدول وضعیت مرحله‌به‌مرحله

| # | مرحله | وضعیت | مکان دقیق | آخرین نسخه | شمارش | SHA-256 (content) | تست‌شده؟ | real / fixture | آیا مرحله بعد از آن تولید می‌شود؟ | وابستگی / بلوک |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | Source Snapshot | ✅ READY | `data/tasnim/pcm20_4/source-snapshot/` | sfd927b663733 | ۴۵٬۸۴۴ صفحه / ۷۲٬۹۰۶٬۱۳۳ B | `fd927b66…` (jsonl) | بله (شمارش+SHA بازمحاسبه) | real | بله | ۴۵٬۲۴۳ صفحه بدون item_index (unresolved)؛ re-crawl زنده بلوک روی s52 |
| 2 | Canonical Corpus | ✅ READY | `data/tasnim/pcm20_4/corpus/builds/v0001/` | v0001 | ۴۵٬۸۴۴ | `ee87686a…` | بله (T04/T05/T09) | real | بله | هیچ (قطعی cross-root؛ idempotent REUSED) |
| 3 | Semantic Corpus | ✅ READY | `data/tasnim/pcm20_5/corpus/builds/v0002/` | v0002 (cs-20.5) | ۴۵٬۸۴۴ صفحه + ۱۰٬۷۲۸ ctx | `12a93e21…` | بله (GATE 1 + ۲۷ تست) | real | در اصل بله (هنوز دیتاست ندارد) | تصمیم طراحی «Embedding Context» تعریف‌نشده |
| 4 | Dataset | ⚠️ PARTIAL | `data/tasnim/pcm20_4/datasets/` | ۶ دیتاست، همه بر پایه v0001 | ۴۵۸ / ۴٬۵۸۴ / ۲٬۹۶۹ / ۲۲٬۹۲۲ / ۴۱٬۲۶۰ / ۴۵٬۸۴۴ | §2.4 | بله | real | برای v0001 بله؛ برای v0002 خیر | هیچ دیتاستی از semantic v0002 وجود ندارد |
| 5 | JSON/JSONL (adapter) | ⚠️ PARTIAL | `corpus/tasnim/dump.py` + `data/tasnim/pcm20_4/dumps/` | ۳ دامپ (بر پایه v0001) | ۲٬۱۹۷ / ۳٬۴۱۶ / ۳۳٬۴۴۳ | §2.5 | بله (template byte-identical) | داده real / embedding **mock** | برای v0001 بله؛ semantic خیر | هیچ دامپ semantic وجود ندارد |
| 6 | AI Dump Builder | ✅ READY (کامپوننت) | repo خارجی `_aidump` @ `1c500a64` | buildهای qwen3-embed-06b | ۳ build | mapping.json `0bd9b8a7…` (یکسان در ۳ build) | بله 3/3 DUMP_VALIDATED | mock (dim 1024) | بله | گارد mock در reuse-map نیست؛ commit خود builder در manifest ثبت نمی‌شود |
| 7 | Real Embedding | ⛔ BLOCKED | — (هیچ بردار واقعی) | — | ۰ بردار واقعی | — | خیر | — | خیر | s52 LiteLLM down؛ پورت‌های model s53 OPEN ولی service-level NOT VERIFIED؛ ابعاد واقعی NOT VERIFIED |
| 8 | Neo4j Loader | ⚠️ PARTIAL | `rag/graph-rag/app/load_collection.py` | repo @ `283ae504` (2026-09-29) | — | — | خیر (فقط کدخوانی؛ در این زنجیره اجرا نشده) | — | بله (با هشدارهای §2.6) | re-embed در load، ریزش ۹ فیلد provenance، CREATE بدون constraint، dim-lock |
| 9 | Neo4j Import | ⛔ BLOCKED | — (هیچ host) | — | — | — | خیر | — | خیر | s52 down + بدون Docker محلی؛ الگوی «DB جدا به‌ازای هر نسخه» لازم است |
| 10 | RAG Retrieval | ⚠️ PARTIAL | `rag/graph-rag/app/` | repo @ `283ae504` | تک‌کلکشن per process | — | خیر (هیچ تست retrieval) | — | جزئی | مسیر specific-book شکسته؛ multi-collection search پیاده نیست؛ URL در نتایج نیست |
| 11 | Chat Integration | ⚠️ PARTIAL | `rag/graph-rag/app/main.py` + UI | همان | — | — | خیر | — | جزئی | فرض `book_id:int`؛ کنترل نمایش hidden-content نه؛ references همیشگی |

### 2.2 Hidden context (cs-20.5)

- **موجودی:** ۱۰٬۷۲۸ رکورد در `data/tasnim/pcm20_5/corpus/builds/v0002/context-records.jsonl` (SHA `a1ac0421…`، ۲۶٬۲۸۷٬۵۷۷ B؛ duplicate `record_id` = 0).
- **اسکما (19 کلید):** `context_hash, context_item_index, context_page_id, heading_page_id, heading_text, internal_tags, next_item_index, next_page_id, next_page_summary, next_source_page_id, record_id, record_kind, retrieval_context, source_hash, summary_lines, summary_meta, visibility, volume_id, volume_title`.
- **هویت رکورد:** `record_id = "ctx:<page_id>"`، `visibility = "hidden"`، `record_kind = "context"`، `internal_tags = ["hidden","heading-context",<class>]`.
- **خلاصه verbatim:** `next_page_summary` = حداکثر ۳ خطِ اولِ صفحه‌ی بعد، کلمه‌به‌کلمه؛ `summary_meta = {max_lines: 3, method: "verbatim-extract/1.0", model: null, prompt_version: null}` — **بدون هیچ تولید/تفسیر LLM** (تمام رکوردها `method=verbatim-extract/1.0`، `model=null`).
- **سه لایه context:** (الف) **Visible** = متن صفحه (`text_normalized`) در `pages.jsonl`؛ (ب) **Hidden** = رکوردهای `context-records.jsonl` (منظور: نه برای نمایش مستقیم)؛ (ج) **Embedding context = تعریف‌نشده** — `make_chunk_text` فقط `text_normalized` صفحه را مصرف می‌کند و هیچ فیلد semantic در هیچ `chunk_text`/embedding context امروزه نیست.
- **اصلاح delta-11:** سراسر `SECTION_HEADING` = ۱۰٬۷۳۹؛ رکوردهای context = ۱۰٬۷۲۸؛ تفاوت = ۱۱. گزارش GATE 1 ادعا کرده بود هر ۱۱ «سرصفحه پایان جلد»‌اند — **نادرست**. واقعیت (مستند S1): **۳ پایان‌جلد** (بدون صفحه بعد: `vol012__p11204`, `vol056__p89279`, `vol080__p91077`) + **۸ مورد با صفحه بعد EMPTY_PAGE** (`vol047__p52332`, `vol047__p52504`, `vol056__p72306`, `vol056__p77649`, `vol056__p77843`, `vol056__p78503`, `vol056__p81845`, `vol056__p84772`) — چون متن صفحه بعد خالی است، خلاصه verbatim قابل استخراج نیست (طراحی: context record متنی غیرخالی در صفحه بعد را نیاز دارد).
- **Census کلاس (بازمحاسبه از pages.jsonl):** CONTENT_PAGE 33٬443 / SECTION_HEADING 10٬739 / SHORT_CONTENT 1٬589 / UNKNOWN_STRUCTURE 38 / EMPTY_PAGE 35 / **CHAPTER_HEADING 0** (یافته داده‌ای: هیچ عنوان سوره‌ای با الگوی `سور[هي]` دیده نشد). مبنا: definitive 33٬516 / guessed 12٬328 (مانیفست).
- **پیاده‌سازی‌نشده در هر ۳ لایه (grep S2: `hidden|visibility|record_kind|internal_tags|context_record|ctx:` → ۰ hit در کل `_aidump` + `rag/graph-rag`):** (a) فیلتر کردن از نمایش؛ (b) استفاده برای retrieval/augmentation؛ (c) یال گراف heading→next-page (فقط NEXT/PREV بین چانک‌ها + Token CONTAINS).
- **تصمیم طراحی لازم:** کدام فیلدها (مثلاً `retrieval_context`؟ `heading_text`؟) وارد ورودی embedding شوند — این تصمیم در GATE 2 باید ثبت شود.

### 2.3 یافته‌های داده Snapshot و پیکره

**Census جلدها (corpus v0001):**

| جلد | volume_no | صفحات | بازه item_index | بازه barg | strategy |
|---|---|---|---|---|---|
| vol001 | 1 | 9 | [2, 26] | [2, 27] | url_section |
| vol012 | 12 | 22 | [11183, 11204] | [3650, 11205] | url_section |
| vol047 | 47 | 9٬391 | [0, 55698] | [1, 55699] | url_section |
| vol056 | 56 | 29٬689 | [59591, 89279] | [55699, 89280] | url_section |
| vol080 | 80 | 767 | [90311, 91077] | [89281, 91078] | url_section |
| volkeyd531f422 (نامشخص) | null | 5٬966 | [39004, 55714] | [39005, 55715] | none |

جمع strategy: `url_section` 39٬878 / `none` 5٬966.

**Flagهای کیفیت:** ok 33٬399 / short 12٬366 / empty 35 / no_barg 35 / truncated_at_2000 28 / dup_item_index 18. آمار `item_index`: 45٬844 مقدار، 45٬835 متمایز، ۹ مقدار تکراری (۹ ردیف مازاد).

**Gap ledger:** 45٬243 صفحه بدون `item_index` در ۶ بازه: `[[3649,11182],[11205,39003],[44957,49956],[55699,55701],[55715,59590],[89280,90310]]` (جمع inclusive بازمحاسبه‌شده = 45٬243 ✓). وضعیت: **`unresolved`** — دلیل مانیفست: هیچ منبع معتبر آفلاینی نیست؛ `/payload` سایت زنده اکنون HTML-SPA برمی‌گرداند (شواهد GATE 0-D)؛ بازیابی = **live re-crawl روی s52 — مسدود تا دسترس‌پذیری s52**. علل گم‌شدن item_index در این 6 run صرفاً فرضیه‌اند (بدون شواهد آفلاین).

**مرجع ترتیب قطعی:** `item_index` (از URL، هرگز از barg). `page_number` در دامپ = barg یا item_index+1 (`corpus/tasnim/dump.py:47-52`)، بنابراین ترتیب زنجیره = ترتیب barg — پذیرفتنی ولی مرجع قطعی `item_index` در گراف نیست.

**جذب صفحات بازیابی‌شده در آینده:** `page_id_of(volume_id, item_index, dup_rank)` در `corpus/tasnim/schema.py` قطعی است → صفحات بازیابی‌شده در نسخه جدید (v0003+) با IDهای پایدار برای صفحات موجود می‌نشینند (versioning افزایشی اثبات‌شده). **Caveat طراحی (نه باگ):** `dup_rank` به ترتیب ورودی داده می‌شود (`corpus/tasnim/transform.py` خطوط 72–80)؛ اگر ردیف‌های بازیابی‌شده `item_index` تکراریِ موجود را اشتراک بگذارند، `dup_rank` ردیف‌های تکراری موجود می‌تواند جابه‌جا شود.

### 2.4 دیتاست‌ها

- ریشه: `data/tasnim/pcm20_4/datasets/`؛ سیاست: `stratified-even-blocks` (largest-remainder + حداکثر ۵ بلوک پیوسته ≤5 بر جلد)؛ ساختار جلدی حفظ می‌شود؛ همه `content_sha_recomputed_match: true` و `files_on_disk_match: true`.
- همه ۶ دیتاست از **corpus v0001** (content SHA `ee87686a…`، prev manifest `e0b0c2ce…`)؛ هیچ‌کدام semantic نیستند.

| دیتاست | درصد | volume_scope | انتخاب‌شده | manifest SHA | content SHA |
|---|---|---|---|---|---|
| 1pct/v0001 | 1 | — | 458 | `d7fd9f93…` | `a407021e…` |
| 10pct/v0001 | 10 | — | 4٬584 | `cdf2868a…` | `7de515a6…` |
| 10pct/v0002 | 10 | {volume_no: 56} | 2٬969 | `90177de2…` | `11ab83ce…` |
| 50pct/v0001 | 50 | — | 22٬922 | `bd511ae8…` | `7c15be3f…` |
| 90pct/v0001 | 90 | — | 41٬260 | `c7002f7b…` | `8ef9aab8…` |
| 100pct/v0001 | 100 | — | 45٬844 | `402bb01a…` | `37673c3d…` |

درصد‌ها دقیق: 458/45844=1.0٪، 4584/45844=10.0٪، 2969/29689(vol56)=10.0٪، 22922/45844=50.0٪، 41260/45844=90.0٪. **اصلاح S1:** `10pct/v0002` دیتاست **تک‌جلدی vol56** است (نه fixture آزمایش افزایشی؛ آزمایش افزایشی در سطح corpus بود — v0002/v0003).

- Idempotency: **REUSED** (نسخه موجود cover نمی‌شود)؛ versioning: کلید رجیستری `dataset:<pct>:<version>`؛ بازتولید قطعی از CLI `corpus/tasnim/cli.py build-dataset`؛ اثبات‌شده در تست‌ها T04/T05/T09.
- **ناقص:** هیچ دیتاستی از semantic v0002 (بلوک ورودی GATE 2).

### 2.5 JSON و Dump

- **مسیر A قرارداد رسمی است:** Canonical → JSON/JSONL (adapter) → builder. **Elasticsearch پیش‌شرط نیست** — در این زنجیره اصلاً ES وجود ندارد.
- **آدرپتار:** `corpus/tasnim/dump.py` (پیاده‌سازی محلی `extract_records`)؛ خروجی `dumps/<pct>/vNNNN/{books.json, product.json, dump-check.json, manifest.json}`؛ مانیفست صریح: «embedding/Neo4j OUT OF SCOPE در این فاز».
- **اسکمای رکورد (20 کلید):** ۹ فیلد دامپ پایه `book_id, book_name, page_number, chunk_id, chunk_text, link, source_id, language, words_count` + ۹ provenance تسنیم `page_id, item_index, barg, volume_no, url, captured_at, content_hash, source_page_id, raw_text` + `_fp` (فingerprint) + `embedding`.
- **template `chunk_text` (byte-identical آدرپتار↔builder):** `Metadata: book_name:…\nbook_id:…\npage_number:…\n-----\nContent: <text_normalized>` — `builder/core.py:114-122` = `corpus/tasnim/dump.py:136-144`. **هیچ فیلد semantic ندارد.**
- **validate_dump:** REQUIRED فقط ۶ فیلد؛ تکرار `(book_id, chunk_id)` فقط warning؛ **هیچ اعتبارسنجی provenance نیست**. `write_dump` فقط `_embed_input` را حذف می‌کند (`core.py:291-300`).
- **mapping.json:** SHA `0bd9b8a7…` یکسان در هر ۳ build.
- **یافته naming cross-wire:** دامپ `10pct/v0001` از دیتاست `10pct v0002` (تک‌جلدی vol56) ساخته شده (2٬197 رکورد، 772 skip-short) و دامپ `10pct/v0002` از دیتاست `10pct v0001` (۶ جلد) (3٬416 رکورد، 1٬168 skip-short) — نام دامپ برعکس نام دیتاست مبدأست.
- **Mock ≠ real:** هر ۳ build با `--mock-embed` (mock dim 1024، برچسب model «Qwen3-Embedding-0.6B»، backend=mock/endpoint=mock، `reused_embedding_count=0`). **هیچ دامپ معتبری برای corpus معنایی وجود ندارد** — هر ۳ دامپ بر پایه v0001 و پیش از semantic است.

### 2.6 یافته‌های کد Builder و Loader

**Loader re-embed می‌کند و `embedding` دامپ را هرگز مصرف نمی‌کند:**
- `rag/graph-rag/app/load_collection.py:179-185` — ساخت مدل + probe ابعاد هنگام load.
- `load_collection.py:216-217` — `emb.embed_query(text)` برای هر رکورد؛ `rec["embedding"]` هرگز خوانده نمی‌شود.
- در تضاد با ادعای طراحی builder در `builder/core.py:14-15` («so the consumer never re-embeds»). ⇒ الگوی GATE 3 در عمل = re-embed-at-load (هیچ قراردادی الزام معکوس ندارد؛ d-1 خانواده اسکمای جداگانه‌ای است و PCM-20.3/20.4 صریحاً embedding/Neo4j را به PCM-20.5 موکول کرده‌اند).

**آلوده‌سازی mock→real از مسیر reuse-map (سطح stop-condition):**
1. fingerprint = `sha1(model + text)` فقط (`core.py:215`) — backend/endpoint/dim در fingerprint نیست.
2. reuse به‌صورت پیش‌فرض از pointer `current` فعال است (`core.py:471`، `read_current` :387).
3. `load_reuse_map` فقط `embedding is not None` را چک می‌کند (`core.py:266-287`).
4. نتیجه: یک build «واقعی» با همان برچسب model به‌صورت خاموش بردارهای mock را بازمی‌گذارد و `validate_dump` (فقط non-null + dim check، `core.py:322-356`) آن را قبول می‌کند.
5. تنها محافظ = flag اپراتور `--no-embed-reuse` (در PCM-20.4 از طریق `.tmp_pcm204_builder_run.py:75` استفاده شده).

**Hollow provenance builder:** `git_commit` مانیفست = commit repo دایرکتوری PRODUCT (toolkit، `8db3b60`) که در `core.py:366-373` / `:525` ست می‌شود؛ commit خودِ repo builder (`1c500a64` — clean، `core.py` از `82d6361` بدون تغییر) در هیچ‌جا ثبت نمی‌شود.

**اتلاف metadata در Loader:** `CREATE_CHUNK` فقط `chunk_text, book_id, book_name, chunk_id, link, page_number, embedding, _row` را نگه می‌دارد (`load_collection.py:191-197`) — هر ۹ فیلد provenance + `language/words_count/source_id` ریخته می‌شوند؛ `link` ترکیبی `book://tasnim__vol001#p2` است، **نه** URL واقعی ⇒ URL منبع در نتایج در دسترس نیست.

**زنجیره‌ها:** `_build_chains` بر اساس `page_number` (از `order_by` mapping) مرتب می‌کند و tie-break با `_row` (ترتیب ردیف JSONL) (`load_collection.py:251-267`)؛ `item_index` هرگز به گراف نمی‌رسد. چون `page_number = barg یا item_index+1`، ترتیب زنجیره = ترتیب barg — پذیرفتنی، ولی مرجع قطعی در گراف نیست.

**ایمنی loader:** `--reset` پیش‌فرض خاموش و محدود به همان DB هدف (`:173-176`) — برای کلکشن‌های دیگر امن؛ **اما** `CREATE` (نه MERGE) بدون unique constraint ⇒ اجرای دوباره بدون `--reset` کل گراف را دوتایی می‌کند؛ index `IF NOT EXISTS` بدون dim صریح ⇒ قفل dim به بردار اول بین نسخه‌ها؛ بارگذاری دوفاصله/switch وجود ندارد؛ loader هیچ‌وقت `manifest.json` را نمی‌خواند ⇒ دامپ stale به‌صورت خاموش load می‌شود.

**الگوی امن مطابق کد فعلی:** Neo4j DB جدا به‌ازای هر نسخه (مثلاً `tasnim_v0002`) + `--reset` فقط در اولین load + اعتبارسنجی پس از load + switch با `set_collection.py` + restart کانتینر.

### 2.7 زیرساخت Embedding

**جدول ظرفیت (مستندات S3 C.2):**

| سرور | نقش | endpoint | مدل‌ها | dim | سخت‌افزار | پایداری | دسترسی |
|---|---|---|---|---|---|---|---|
| s52 (172.20.1.52) | LiteLLM gateway | :4000 `/v1` | 4B / 0.6B (برچسب) | 2560 / 1024 (برچسب) | 23Gi RAM / 10 CPU | disk 100٪ پر (2026-10-25، stale) | **down** — همه پورت (4000/4101/22/2222/81) timeout |
| s53 (172.20.1.53) | GPU model server | :4000 (4B)، :4001 (0.6B)، :11434 (ollama mxbai-embed-large)، :8000/:8001 (SGLang qwen38 27B-FP8) | Qwen3-Embedding-4B/0.6B، mxbai-embed-large، qwen3 27B-FP8 | 2560 / 1024 / 1024 | H800 (فقط ذکرشده در GATE0 §D2؛ تعداد GPU NOT VERIFIED) | پورت‌ها **OPEN** | قابل‌دسترس؛ service-level `/v1/embeddings` NOT VERIFIED |
| 172.30.0.117 | bge-m3 | :8001 | bge-m3 | 1024 | — | REFUSED | مسدود |
| 172.30.0.113 | — | — | — | — | — | timeout | مسدود |
| machine محلی (Windows) | — | — | — | — | بدون Docker/Neo4j | — | GATE 3 hostless |

- **SPOF = LiteLLM روی s52:** همه configها (RAG `config.json`، builder baseline) به `http://172.20.1.52:4000/v1` اشاره دارند. **تفاوت کلیدی با GATE 0:** model serverها روی s53 UP‌اند؛ تنها نقطه‌ی شکست، proxy LiteLLM روی s52 است.
- **گزینه‌ها:** (a) **بازگشت s52** — بدون تغییر معماری؛ (b) **LiteLLM روی s53** — نیازمند تأیید + راه‌اندازی (خارج از دامنه این ممیزی)؛ (c) **مستقیم s53:4001** — نقض مدل امنیتی builder («LiteLLM only, never direct to model server»).
- **تخمین ظرفیت (خارج‌삽ی ثابت، نه اندازه‌گیری):** baseline falsafe 32٬183 چانک ≈ ۳۰ دقیقه روی GPU شلوغ ⇒ تسنیم full 33٬443 چانک ≈ ۳۰–۴۰ دقیقه، 10٪ ≈ ۳–۴ دقیقه، حجم dump ≈ 870 MB.
- **جهت طراحی:** بار آتی نباید روی یک H100 متمرکز شود ⇒ pool چندسروره (backlog: `INFRA-EMBED-POOL`).

### 2.8 RAG

- **مدل کلکشن:** collection = **database Neo4j** (`config.py:164`؛ `list_collections` :175 = `SHOW DATABASES`)؛ تک‌کلکشن per process؛ سوییچ = تغییر config + restart (`main.py:499-505`)؛ تصویر `neo4j:2025.10.1-enterprise` (multi-DB OK) (`docker-compose.yml:3`).
- **کلکشن مستقل تسنیم:** DB جدید Neo4j از طریق loader `--collection tasnim` + `set_collection.py` + restart — **ممکن**.
- **جستجوی مستقل:** فقط active-collection (تکی per process) — **ممکن**. **جستجوی ترکیبی چندکلکشنی: NOT IMPLEMENTED** (نیازمند تغییر اپ).
- **فیلتر جلد:** از طریق property `book_id` (حاوی شماره جلد) **ممکن** ولی فیلتر اختصاصی نیست.
- **نمایش منبع/URL:** **در دسترس نیست** (URL در loader ریخته شده)؛ **شماره صفحه: بله**؛ **item_index: در گراف نیست**.
- **بازیابی hidden-context:** **NOT IMPLEMENTED**؛ **enable/disable منبع per-request:** **NOT IMPLEMENTED** (chat همواره references را stream می‌کند).
- **نتایج:** `document_text, score, book_id, book_name, chunk_id, link, page_number` (بدون URL واقعی)؛ references از طریق `###REFERENCES###` + `SourceReference {book_id: int, page_number: int}` (`structure_of_output_data_pydantic.py:39`).
- **مسیر specific-book برای تسنیم شکسته است:** `int(book_id)` در `nodes_langgraph.py:384` + book-matcher از CSV عددی mesbah (`nodes_langgraph.py:162-165`) در برابر string `tasnim__vol001`.
- **ناسازگاری config embedding:** `config.json` RAG مدل `Qwen3-Embedding-4B` را از طریق `http://172.20.1.52:4000/v1` قفل کرده؛ builder primary (baseline.md) = 0.6B/1024d؛ ابعاد واقعی runtime **NOT VERIFIED** — باید یک هویت واحد شود.
- **معتبرنامه‌ها (فقط محل + نوع):** `rag/graph-rag/app/config.json` (**git-TRACKED، در تاریخ repo**) دارای ۳ فیلد `api_key` (len=25) برای endpointهای LiteLLM-compatible (`llm_planner`/`llm_answerer`/`embedding`)؛ `.env` همان repo فقط template (placeholder) است؛ `_aidump` بدون `.env` روی دیسک (gitignored).
- **قابل‌استفاده:** اسکلت اپ، کلکشن‌سوییچ، تب admin، رندر references. **آماده نیست:** نمایش URL/provenance، hidden-context، string book_id، multi-collection.

### 2.9 ممیزی تست

- **Unit:** 27/27 `test_corpus_tasnim` + `test_corpus_semantic` (بازپیمایش S1، خروج 0، خط نتیجه: `Ran 27 tests in 6.119s / OK`) + 216 تست در PCM-20.4 (200 رگرسیون backend + 16 T؛ 0 skip).
- **Integration/feature:** پذیرش end-to-end PCM-20.4 (3 build واقعی builder با mock embed؛ snapshot واقعی 45٬844 صفحه با SHA verify + truncation gate).
- **Idempotency/versioning/determinism:** T05/T06/T09 + cross-root (سه ریشه، یک content SHA) + GATE 1 REUSED.
- **Dump validation:** 3/3 `DUMP_VALIDATED` (0 error/0 warning).
- **ناقص (صریحاً):** تست import Neo4j (**هیچ**)، تست retrieval RAG (**هیچ**، فارسی یا غیرفارسی)، تست pipeline e2e با embedding واقعی، تست رفتار hidden-context، تست reload-safety loader. در این ممیزی تست جدیدی نوشته **نشده** (ممنوع).

### 2.10 Git و مستندات

| محیط | وضعیت |
|---|---|
| **Local** | branch `main`، HEAD `11233e9` («GATE 1 (PCM-20.5) — PASS»، 2026-11-05، moazpor)؛ working tree پاک جز ۲ فایل S1 untracked؛ staging خالی؛ ۶۴ فایل `.tmp_pcm204_*` **داخل** commit `11233e9` هستند (88 فایل، +14٬418/−1) — ناسازگاری با متن §8 گزارش GATE 1؛ **۱ commit جلوتر از `origin/main`** (`f314de5`) — commit GATE 1 **push نشده**؛ remote فقط `origin = https://github.com/saber13812002/persian-corpus-toolkit.git` (بدون توکن)؛ stash خالی |
| **GitHub** | قابل‌دسترس (ls-remote موفق؛ upstream `f314de5` تأییدشده) |
| **Internal GitLab (s52:2222)** | **مسدود** — `ls-remote` از طریق `ssh -p 2222` → connection timed out (۲ تلاش)؛ s52:22 هم timeout؛ هیچ remote GitLabی در repo toolkit تنظیم نشده |
| **`rag/graph-rag`** | HEAD `283ae504` (2026-09-29)، tree پاک؛ origin = `http://172.20.1.52:81/rag/graph-rag.git` → **TIMEOUT** (host down) |
| **`_aidump`** | HEAD `1c500a64` (main، 2026-10-11)؛ ۳ فایل کثیف غیرموتوری (`README.md`, `scripts/build.sh`, `scripts/smoke_test.sh`؛ +24/−9، بدون تغییر engine)؛ **بدون remote** |

**مستندات موجود/ناقص:**

| مورد | وضعیت |
|---|---|
| `docs/PCM-20.5*.md` | **وجود ندارد** — قرارداد cs-20.5 فقط در گزارش GATE 1 است |
| `readme.md` roadmap | تا PCM-19 (stale نسبت به AGENTS.md که تا PCM-20.4 است) |
| `AGENTS.md` | ردیف PCM-20.5 ندارد |
| `docs/openapi/` | فقط APIهای knowledge (19 operation) — بدون corpus/Tasnim (زیرسیستم فقط-CLI؛ نیاز به reconcile در GATE1 §9) |
| Wiki.js | NOT VERIFIED |
| `.gitlab-ci.yml` | test-only تأییدشده (3 job: regression / openapi / client؛ بدون deploy) |

**فهرست مستندات مفقود:** سند قرارداد PCM-20.5، runbook embedding، سند عملیاتی loader Neo4j، برنامه GATE 2–4، ردیف‌های roadmap (readme/AGENTS).

### 2.11 Stop conditionهای فعال (مستند، خودترقیق‌نشده)

| # | Finding | اثر | تصمیم لازم کاربر |
|---|---|---|---|
| 1 | **دامپ‌های stale** — هر ۳ دامپ بر پایه v0001، پیش از semantic | embedding محتوای قدیمی (بدون لایه معنایی) | ساخت دامپ semantic (پیش‌شرط 5) |
| 2 | **Mock به‌جای embedding واقعی** — 100٪ بردارها mock | retrieval بی‌معنا | اجرای واقعی (پیش‌شرط 1+2) |
| 3 | **ابعاد بردار model واقعی نامشخص** (NOT VERIFIED) | dim-lock Neo4j به بردار اول | probe 1-رکوردی در runtime (پیش‌شرط 2) |
| 4 | **اتلاف metadata در گراف** — loader ۹ فیلد provenance را می‌ریزد | URL/برگه/provenance در نتایج نیست | پیش‌شرط 4 (اصلاح loader) یا پذیرش مکتوب |
| 5 | **Hidden context ناقص** — هیچ لایه‌ای آن را پیاده نمی‌کند | ارزش لایه معنایی در RAG محقق نمی‌شود | تعیین scope در GATE 4 |
| 6 | **رابطه heading↔صفحه‌بعد در گراف مدل‌نشده است** | ناوبری ساختاری/اختیارcontext ممکن نیست | تصمیم طراحی گراف |
| 7 | **تلاش کلکشن NOT VERIFIED** (DB زنده دست‌نیافتنی) — نام `tasnim` در شواهد ایستا دیده نشده | در صورت وجود، آلوده/overwrite خاموش | `SHOW DATABASES` روی s52/s53 (پیش‌شرط 6) |
| 8 | **Hollow provenance** — commit builder ثبت نمی‌شود | قابل‌استدال نبودن build | افزودن `builder_commit` (مأموریت جدا) |
| 9 | **مسیر آلوده‌سازی mock→real در reuse-map بدون محافظ** | بردار mock در dump «واقعی» به‌صورت خاموش | پیش‌شرط 3 (گارد backend+dim+endpoint) |
| 10 | **ترتیب item_index در گراف حفظ نمی‌شود** (page_number+_row به‌جای آن) | tie-break بر حسب ردیف JSONL در موارد تکرار/gap | اصلاح loader یا پذیرش مکتوب |
| 11 | **وضعیت مبهم gap** — در این ممیزی به‌عنوان `unresolved` با شواهد حل شد (stop نیست، مستند) | 45٬243 صفحه بی‌ترتیب قطعی | re-crawl زنده پس از بازگشت s52 |

### 2.12 اصلاحات و ناسازگاری‌ها

1. **delta-11:** گزارش GATE 1 همه ۱۱ عنوانِ بدون context record را «پایان‌جلد» می‌دانست؛ واقعیت = **3 پایان‌جلد + 8 با صفحه‌ی بعد EMPTY_PAGE** (فهرست در §2.2).
2. **`10pct/v0002` = دیتاست تک‌جلدی vol56** (`volume_scope: {volume_no: 56}`) — نه fixture افزایشی (اصلاح S1).
3. **«64 فایل staged دست‌نخورده» در §8 گزارش GATE 1** — در واقع داخل commit `11233e9` هستند (committed شده‌اند؛ staging خالی است).
4. **cross-wire نام دامپ:** `dumps/10pct/v0001` از دیتاست `10pct v0002` (vol56) و `dumps/10pct/v0002` از دیتاست `10pct v0001` ساخته شده (جزئیات §2.5).
5. **docstring در برابر کد:** `corpus/tasnim/schema.py:125` — docstring ادعای `sha8(values)` دارد اما کد از ثابت `_h8({"k":"noindex"})` برای page id fallback بدون-index استفاده می‌کند (caveat مستند، نه باگ).

### 2.13 فهرست NOT VERIFIED (وابسته به دسترسی)

| مورد | دسترسی دقیق لازم |
|---|---|
| ابعاد بردار Qwen3 واقعی (0.6B = 1024d؟) | endpoint LiteLLM زنده + یک `/v1/embeddings` |
| service-level embedding روی s53 (پورت‌ها OPEN، HTTP/auth بی‌بررسی) | probe HTTP با اعتبارنامه به s53:4000/4001 |
| وضعیت s52 و امکان recovery | دسترسی شبکه/ops به 172.20.1.52 |
| تعداد GPU روی s53 (H800 فقط ذکرشده در GATE0 §D2) | `nvidia-smi` از طریق s53:22 (پورت باز) |
| فهرست DBهای Neo4j زنده (بررسی تلاش کلکشن) | `SHOW DATABASES` روی instance s52 |
| Wiki.js | دسترسی خواندنی به سرویس Wiki |
| ظرفیت واقعی runtime (throughput/latency embedding) | اجرا واقعی روی GPU (اعداد فعلی خارج‌삽ی هستند) |
| علل گم‌شدن item_index در 6 run | live re-crawl روی s52 (فرضیه‌ها بدون شواهد) |
| وضعیت repo دوردست `rag/graph-rag` | دسترس‌پذیری `172.20.1.52:81` |

---

## جزء ۳ — جدول پذیرش نهایی

| مرحله | وضعیت | شواهد | بلوک‌ر |
|---|---|---|---|
| Source Snapshot | READY | 45٬844 صفحه؛ jsonl SHA `fd927b66…`؛ manifest `sfd927b663733` با 45٬844 page؛ شمارش بازمحاسبه‌شده | gap 45٬243 (unresolved) — re-crawl بلوک روی s52 |
| Canonical Corpus | READY | v0001؛ content SHA `ee87686a…` match؛ 45٬844 صفحه؛ cross-root deterministic؛ idempotent REUSED | — |
| Semantic Corpus | READY | v0002 (cs-20.5)؛ content SHA `12a93e21…` match؛ 10٬728 context record (schema 19 کلید، verbatim)؛ 0 duplicate | تصمیم طراحی Embedding Context تعریف‌نشده |
| Dataset | PARTIAL | ۶ دیتاست واقعی، همه بر پایه v0001؛ درصد‌های دقیق؛ `stratified-even-blocks`؛ T04/T05/T09 | هیچ دیتاست semantic-v0002 نیست |
| JSON-JSONL | PARTIAL | adapter byte-identical با builder؛ 3 دامپ (2٬197/3٬416/33٬443) — همگی MOCK + v0001-stale | هیچ دامپ semantic معتبر وجود ندارد |
| AI Dump Builder | READY (کامپوننت) | 3/3 DUMP_VALIDATED؛ mock dim 1024؛ mapping `0bd9b8a7…` یکسان | گارد mock در reuse-map نیست؛ commit builder ثبت نمی‌شود |
| Real Embedding | BLOCKED | 0 بردار واقعی در `data/`؛ ابعاد NOT VERIFIED | s52 LiteLLM down؛ s53 پورت‌ها OPEN ولی service NOT VERIFIED |
| Neo4j Loader | PARTIAL | کد کار می‌کند ولی re-embed در load (`:216-217`)، ریزش 9 provenance (`:191-197`)، CREATE بدون constraint | dim-lock؛ reload-duplicate؛ خواندن manifest |
| Neo4j Import | BLOCKED | هیچ host Neo4j قابل‌دسترس (s52 down؛ بدون Docker محلی) | الگوی DB جدا per-version لازم است |
| RAG Retrieval | PARTIAL | تک‌کلکشن per process؛ multi-DB image OK (`2025.10.1-enterprise`)؛ references/streaming موجود | specific-book path شکسته (int vs string)؛ multi-collection search نیست؛ URL نیست |
| Chat Integration | PARTIAL | chat + references (`###REFERENCES###`) + admin موجود | فرض `book_id:int`؛ کنترل نمایش hidden-content نیست |

**جمع‌بندی سطر:** 3 READY (مرحله 1–3)، 5 PARTIAL، 2 BLOCKED، 1 READY-کامپوننت — زنجیره در نقطه‌ی «Data ready / Serving not ready» ایستاده است.

---

## جزء ۴ — پاسخ نهایی

### «آیا تسنیم همین‌الان آماده ورود به Neo4j و اتصال به RAG است؟»

## → خیر — هنوز آماده نیست (NO)

### مسیر آمادگی مشروط (پیش‌شرط‌های سخت، مرتب‌شده)

1. **تصمیم دسترسی:** recovery s52 (liteLLM + host Neo4j) **یا** تأیید راه‌اندازی LiteLLM روی s53 (TCP-verified reachable، پورت‌های 4000/4001/11434/8000/8001/22 OPEN) — **تصمیم کاربر لازم است**.
2. **تصمیم model/dim:** 0.6B/1024d (primary builder) در برابر 4B/2560d (config RAG) — باید **یک هویت واحد** شود و با 1-رکوردی probe در runtime تأیید گردد.
3. **گارد builder:** `load_reuse_map` باید backend+dim+endpoint را هم match کند (یا برای backendهای واقعی `--no-embed-reuse` اجباری شود) — تغییر کد در `_aidump` (مأموریت جدا).
4. **تصمیم loader:** یا loader اصلاح شود تا `embedding` دامپ را مصرف کند (احترام به قرارداد builder) یا re-embed-at-load **رسمی** پذیرفته شود (مکتوب‌شده + پذیرش ~33k embed سریالی هنگام load + provenance همچنان ریخته می‌شود مگر loader اصلاح شود) — تغییر کد در `rag/graph-rag` (مأموریت جدا).
5. **دامپ semantic:** ساخت دیتاست(های) از semantic v0002 + dump با embedding واقعی (GATE 2).
6. **Neo4j:** DB ایزوله به‌ازای هر نسخه (`tasnim_v0002`) + `--reset` فقط در اولین load + اعتبارسنجی پس از load (GATE 3).
7. **اصلاحات RAG:** string book_id در مسیر specific-book + اسکمای references، نمایش URL/provenance، فیلتر hidden-context (scope GATE 4 یا follow-up).

### پیشنهاد مأموریت بعدی (خودکار آغاز **نمی‌شود**)

**PCM-20.6: Real embedding + isolated Neo4j + RAG connection (GATE 2–4 execution)** — اجرای عملی زنجیره با 7 پیش‌شرط بالا به‌عنوان entry checklist: ساخت دیتاست+دامپ semantic با embedding واقعی (گارد reuse-map اعمال‌شده)، import به Neo4j DB ایزوله `tasnim_v0002` با اعتبارسنجی پس از load، اتصال RAG با کلکشن مستقل و اصلاحات book_id/URL/hidden-context. خروجی مستندات: `docs/PCM-20.5*.md` (سند قرارداد cs-20.5)، runbook embedding، سند عملیاتی loader Neo4j، ردیف‌های roadmap (readme/AGENTS)، و مستندسازی backlog `INFRA-EMBED-POOL` (pool چندسروره برای بارهای آتی embedding).

**این مأموریت با این گزارش پایان می‌یابد؛ هیچ مأموریت بعدی خودکار آغاز نشده است.**

---

## پاورقی

- **SHA-256 این گزارش (خودارجاعی — محاسبه‌شده روی کل فایل به‌جز خط‌های حاوی این برچسب):** `916105bd61d913334aae64229dca7afcdb377b469dafd569408502d08e164b49`
   راستی‌آزمایی: `python -X utf8 -c "import hashlib;t=open('گزارش-PCM-20.5-READINESS.md',encoding='utf-8').read();x=''.join(l for l in t.splitlines(keepends=True) if 'SHA-256 این گزارش' not in l);print(hashlib.sha256(x.encode('utf-8')).hexdigest())"` — انتظار: `916105bd61d913334aae64229dca7afcdb377b469dafd569408502d08e164b49`
- **فایل‌های شواهد:**
  - `.tmp_pcm205_readiness_s1.json` — SHA-256 `351b908df79cbbc47dcd48f239c0fd8f0e5602a3cf15bf757c29f90cb51f2860` (کل شواهد S1)
  - `گزارش-PCM-20.5-GATE0.md` — SHA-256 `683567c6ed6a2bf1abd99304361cdd0717693e05ead852d82e9bbaec2eb0649b`
  - `گزارش-PCM-20.5-GATE1.md` — SHA-256 `6b6d4744864d69143407505d5e79a2d0d51a8465372208eff08314e0f7039e41`
- **بیانیه انطباق:** این ممیزی کاملاً read-only بود: بدون تغییر داده/کد/مستندات، بدون هیچ عملیات git (گزارش UNTRACKED)، بدون شبکه فراتر از پروب‌های ≤۵ثانیه در S3، بدون embedding، بدون deploy، بدون لمس production؛ هیچ رمز/توکنی در این گزارش نیست (فقط محل + نوع اعتبارنامه‌ها). هیچ یافته stop-condition خودترقیق‌نشده است.

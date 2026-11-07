# PCM-20.6.4 — Architecture: Tasnim Web V1

> **مأموریت:** PCM-20.6.4 Track B — معماری محصول + فنیِ «کتاب‌خانهٔ دیجیتال تسنیم» روی دامنه‌ی هدف `tasnim.ai.ismc.ir`.
> **وضعیت:** SPEC (فقط معماری؛ **هیچ** کد/دپلوی در این فاز). تاریخ: 2026-11-07 (Asia/Tehran).
> **پیش‌نیازهای شواهدی (بازبینی‌شده در این فاز):** داده‌ی v0003 (`content_sha256=40f45e0b…e4`) · fact-check (`.tmp_pcm2064_factcheck_report.md` — در دسترس نیست؛ نتایج آن در همین سند و یادداشت §۴.۲ تثبیت شده است) · design system [`PCM-20.6.4-DESIGN-SYSTEM.md`](PCM-20.6.4-DESIGN-SYSTEM.md) · شناخت سازمانی [`PCM-20.6.0-RECON.md`](PCM-20.6.0-RECON.md) + [`PCM-20.6-BASELINE.md`](PCM-20.6-BASELINE.md).
> **یادداشت اعداد (2026-11-07):** شمارش موضوع در این سند (1,082) از فاز طراحی است؛ در read model زندهٔ v0003 مقدار فعلی **1,080** است (ببینید §۴.۲، «به‌روزرسانی با شواهد زنده»). سایر اعداد شمارشی این سند نیز در همان یادداشت بازبینی شده‌اند.
> **زیرنویس:** اصطلاحات فنی لاتین می‌مانند؛ بقیه فارسی.

---

## ۱. تعریف محصول (Product Definition)

### ۱.۱ اهداف

| # | هدف | معیار موفق (قابل اندازه‌گیری از DB) |
|---|---|---|
| G1 | خواندن هر صفحهٔ موجود تفسیر تسنیم با URL پایدار و سریع | LCP < 2.5s روی اتصال داخلی؛ `GET /page/<item_index>` < 50ms (P95) |
| G2 | ناوبری واقعی بر اساس ترتیب `item_index` (نه برگ چاپی) | prev/next همیشه به صفحهٔ موجودِ بعدی/قبلی می‌رود؛ gapها شفاف |
| G3 | جستجوی فارسیِ کاربردی در 45,844 صفحه | FTS5 با توکن‌زاسیون فارسی‌شده؛ پاسخ < 200ms (P95) برای کلمه‌های پرتکرار |
| G4 | شفافیت کاملِ کیفیت داده | همهٔ ۵ وضعیت quality (ok/short/empty/truncated/dup) با badge؛ ۶ بازهٔ گم‌شده در `/coverage` |
| G5 | هویت «کتاب‌خانهٔ علوم اسلامی» — نه داشبورد، نه JSON viewer | design system §۱ + anti-patterns §۱۰ (سند طراحی) |
| G6 | آماده‌بودن برای RAG (بدون RAG جعلی) | بلاک `reference` در هر صفحه؛ `rag_status: not_connected` صریح |

### ۱.۲ Personas

1. **طالبه/تحقیقاتگر علوم دینی** — ورود از موضوع (بحث روایی، مفردات…) یا سوره (آینده)، خواندن صفحه‌به‌صفحه، نیاز به ارجاع‌دهی دقیق (جلد/برگ/SHA) برای استناد.
2. **خوانندهٔ عمومی/دانش‌آموز** — ورود از صفحهٔ اول، خواندن پیوسته با prev/next، جستجوی سادهٔ کلمه.
3. **پژوهشگر داده/فنی** (داخلی) — مصرف API + OpenAPI برای ساخت ابزار (RAG بعدی، تحلیل)؛ انتظار contract ثابت و honest.

### ۱.۳ دامنهٔ V1 (in-scope)

- خواندن (reader) + ناوبری (volume/heading/page prev-next) + فهرست موضوعات + جستجوی تمام‌متن + صفحهٔ پوشش/کیفیت + about/help.
- API read-only با OpenAPI 3.1 · read-model جدا از corpus (version-swappable) · SSR frontend · compose فایل.
- **بدون:** حساب کاربری، هرگونه نوشتن/نشان‌گذاری کاربری، پاسخ RAG، backfill، deploy production، DNS/cert/ingress change.

### ۱.۴ non-goals صریح

| رد شد | دلیل |
|---|---|
| نمایش پاسخ RAG/LLM به کاربر | مأموریت: `rag_status: not_connected`؛ هر نمایش = جعل |
| backfill صفحات گم‌شده | Track A جداست (Gate A)؛ V1 فقط gapها را نشان می‌دهد |
| Surah index | **verdict: SURAH_INDEX_NOT_SUPPORTED** (§۴.۴) — endpoint honest-unavailable |
| deploy روی ingress با گواهی | فقط PLAN (§۷)؛ اجرا = فاز جدا با تأیید مالک ingress (R10) |
| SPA / framework سمت کلاینت | §۳.۲ |
| رندر `hidden_context` | ممنوع مطلق — خصوصیت امنیتی HP-1 (§۵.۶) |

---

## ۲. Information Architecture / Sitemap

```mermaid
graph TD
  H[Home /<br/>معرفی اثر + گرید ۶ جلد + وضعیت پوشش + موضوعات برتر + جستجوی سریع + ادامهٔ خواندن]
  VL[/volumes — فهرست کامل جلد + coverage هرکدام]
  VD[/volume/:volume_id — کاور + متادیتا + فهرست هدرها + coverage + شروع خواندن]
  P[/page/:item_index — reader<br/>متن + heading + prev/next + drawer متادیتا + quality + مباحط مرتبط]
  TI[/topics — شاخص موضوع: 1082 موضوع + شمارنده]
  TD[/topic/:topic_id — رخدادها + صفحات + ارجاعات]
  SU[/surahs — «در حال تکمیل»<br/>API: status=unavailable]
  SE[/search?q= — نتایج با snippet + highlight + no-results fallback]
  CO[/coverage — ۶ بازهٔ گم‌شده + وضعیت backfill Track A]
  AB[/about — دربارهٔ داده + policyهای کیفیت + لینک runbook backfill]

  H --> VL
  H --> TI
  H --> SE
  VL --> VD
  VD --> P
  TI --> TD
  TD --> P
  P --> SE
  P --> VD
  P --> TI
  CO --> AB
```

### ۲.۱ قوانین کلیدی IA (مستقیماً از شواهد داده)

1. **کلید همه‌چیز `page_id` / `item_index` است، نه جلد.** volume فیلدِ توصیفی (attributed evidence) است؛ به‌خاطر ۳ جفت overlap (§۴.۲) و جلدِ `volume_no=null` (`volkeyd531f422`). URL صفحات هیچ‌گاه volume ندارد: `/page/<item_index>`.
2. **شماره‌شکنی ممنوع.** در 45,243 `item_index` گم‌شده (6 بازه: 3649–11182, 11205–39003, 44957–49956, 55699–55701, 55715–59590, 89280–90310)، prev/next می‌رود به نزدیک‌ترین موجود و chip هشدار می‌دهد «N صفحه در این بازه در دست بازیابی است» + link به `/coverage`.
3. **Surah section:** فقط «در حال تکمیل» (§۴.۴). نه کارتِ خالیِ تزیینی، نه دادهٔ ساختگی.
4. **جلد نامشخص** (`volkeyd531f422`, 5,966 صفحه) در گرید جلد با badge «شمارهٔ جلد در دست بازیابی» — نه حذف، نه حدس.
5. **Continue reading:** بدون account → `localStorage` کلاینت (آخرین item_index)؛ «آخرین صفحهٔ موجود پیکره» = item_index 91077 (vol080) — عدد واقعی DB.
6. **Breadcrumbs:** `خانه › جلد 47 › برگ 3037` — فقط وقتی جلد بدون‌ابهام است؛ در صفحاتی که volume آن در overlap قرار دارد، breadcrumb فقط `خانه › صفحه 3037` (بدون claim جلدی نادرست).

---

## ۳. معماری Frontend

### ۳.۱ تصمیم: **Flask server-rendered + Jinja + vanilla JS (progressive enhancement)**

| معیار | SSR Flask (انتخاب) | SPA (رد شد) |
|---|---|---|
| الگوی سازمان | مطابق (Flask + SQLite + بدون framework؛ داشبورد فعلی هم همین الگو) | خلاف الگو |
| LCP/بارگذاری | HTML کامل در request اول؛ JS اختیاری | آب‌بند bundle + XHR cascade |
| a11y/SEO | semantic HTML از سمت سرور | hydration + fallbacks |
| بدون-JS | سایت کامل قابل خواندن | سایت مرده |
| پیچیدگی build | صفر (compose 2 سرویس) | node build stage |
| دادهٔ سنگین | page ≤2KB متن — SSR کافی است | مزیت SPA اینجا بی‌معناست |

**رد شدن SPA دلیل‌دار:** محصول خواندنی با صفحه‌های کوچک است؛ هیچ interactivity سنگینی (جدول live، canvas، editing) وجود ندارد. مزیت SPA (state sharing، offline app) در V1 لازم نیست.

### ۳.۲ لایه‌ها

- **SSR:** همهٔ 10 صفحهٔ sitemap با Jinja (base layout یک‌تایی؛ `lang="fa" dir="rtl"`).
- **Progressive enhancement (vanilla JS, < 8KB):** history pushState برای prev/next، theme toggle، metadata drawer، text-size A+/A−، search debounce (اختیاری)، scroll-reveal (فقط با `prefers-reduced-motion: no-preference` + IntersectionObserver). بدون dependency.
- **Static assets:** CSS تک‌فایل `tasnim.css` (design tokens به‌صورت CSS variables)؛ فونت‌های **self-hosted woff2 subset** (§۳.۳ سند طراحی)؛ آیکون‌های SVG inline. **بدون CDN** (offline-first سازمان).
- **رابط کلاینت به API:** صفحات SSR داده را inline دارند؛ JS فقط برای prev/next خنک‌طلبانه `GET /pages/{n}/neighbors` می‌زند (cacheable) — یعنی کلاینت هیچ دادهٔ پنهانی را مستقیم نمی‌خواند و contract واحد می‌ماند.

### ۳.۳ چیدمان فایلی (برنامه‌ریزی‌شده برای فاز ۳)

```text
<worktree>/
  docker-compose.tasnim.yml        # standalone؛ کنار compose موجود
  tasnim-web/
    server.py                      # Flask app: SSR + wiring API (الگوی backend/server.py)
    readmodel.py                   # schema + query layer
    readmodel_builder.py           # CLI: corpus version dir → tasnim_readmodel.db
    search.py                      # tokenization + FTS5 query builder
    api_v1/                        # blueprints: catalog, volumes, pages, topics,
                                   #            surahs, search, statistics, health
    templates/                     # base/home/volumes/volume/page/topics/topic/
                                   # surahs/search/coverage/about/error
    static/css/tasnim.css
    static/js/tasnim.js
    static/fonts/*.woff2           # Vazirmatn, Noto Naskh Arabic, Amiri (subset)
    static/icons/*.svg
    openapi/tasnim-v1.openapi.yaml # 3.1؛ در runtime هم سرو می‌شود
  tests/
    tasnim_test_support.py         # temp readmodel + env (الگوی pct_test_support)
    test_readmodel.py              # unit builder
    test_tasnim_api.py             # unit+integration API
    test_tasnim_e2e.py             # 12-step scenario
  readmodel/v0003/                 # خروجی build (gitignored)
```

---

## ۴. معماری داده / Read Model

### ۴.۱ اصل: `tasnim_readmodel.db` — SQLite FTS5، جدا، فقط‌خوانده برای API

**چرا فایل‌های JSONL را هر-request نمی‌خوانیم:** حجم 5 فایل = **224,689,965 بایت** (pages.jsonl تنها = 170,629,785). بارگذاری کل‌فایل = ~200MB memory per request + تأخیر چند ثانیه. read-model = یک‌بار build → query millisecond.

### ۴.۲ شواهد داده‌ای پشت طراحی (fact-check این فاز، v0003)

| واقعیت | عدد | پیام معماری |
|---|---|---|
| `volume_id`ها | **6** (vol001, vol012, vol047, vol056, vol080, volkeyd531f422) | جدول `volumes` 6 سطر؛ volume_no یکی null |
| overlap بین جلد (item_index) | 3 جفت: vol001×vol047 [2..26] (34 صفحه) · vol012×vol047 [11183..11204] (22) · vol047×volkey [39004..55698] (11,695) | flag `ambiguity` در `volumes`؛ UI breadcrumb احتیاط (§۲.۱) |
| item_index تکراری | 9 مقدار (2,3,4,9,14,19,24,25,26) = 18 سطر، همه vol001×vol047، سمت vol047 با سuffix `__d1` + `dup_rank=1` | `pages` PK = `page_id` (منحصربه‌فرد)؛ `dup_of` اشاره به هم‌نوع |
| صفحات | 45,844 سطر؛ 45,835 مقدار متمایز item_index؛ `next_page_id` در 45,838 سطر (6 null = پایان زنجیره هر volume) | `next_page_id` **هرگز** volume را رد نمی‌کند (0 مورد) → prev/next intra-volume امن |
| barg | 35 سطر null (همان صفحات خالی) | barg فقط نمایشی (printed leaf) — **هرگز** key |
| quality | ok 33,399 · short 12,366 · dup 16 · empty 35 · truncated 28 | ستون‌های flag در `pages` |
| truncated | 28 صفحه؛ همه `truncated_at_source=true` + `source_char_cap=2000` + flag `truncated_at_2000` | سیگنال رسمی = flag (نه صرفاً `len==2000`) |
| headings | 10,739 رکورد؛ `parent` 10,733 non-null، orphan 0، invariant parent<child برقرار؛ عمق زنجیره max 7,213 / avg 2,695 | جدول `headings` با parent pointer؛ UI درخت کامل نمی‌کشد (R5) |
| topics (بعد از normalize) | **1,082** متن متمایز؛ 64 متن روی ≥2 صفحه؛ برترها: تفسیر ×1678، مفردات ×1631، گزیدهٔ تفسیر ×1531 | جدول `topics` 1,082 سطر — کوچک، ساده، سریع · **به‌روزرسانی با شواهد زندهٔ 2026-11-07 (read model v0003):** مقادیر فعلی `SELECT COUNT(*) FROM topics` = **1,080**، multi-page topics = **62**، و برترین‌ها: تفسیر ×1,678، گزیدهٔ تفسیر ×1,677، مفردات ×1,631 — اختلاف از normalize دقیق‌تر در builder نسخهٔ نهایی؛ مقادیر بالا (1,082/64/×1,531) از محاسبهٔ اولیهٔ طراحی هستند |
| surah | **0** فیلد surah در کل schema · **0** هدر با پیشوند سخت · **0/114** پوشش canonical · 265 هدر «شل» که همه sub-heading عمومی‌اند (هدف سوره، خطوط کلی معارف سوره…) · 0 صفحهٔ تعلق‌داده‌شده | **SURAH_INDEX_NOT_SUPPORTED** (§۴.۴) |
| hidden context | 10,728 رکورد hcctx + 10,739 hctx؛ همه `visibility=hidden_context`؛ policy مکتوب در corpus.json: «must never be rendered publicly» | HP-1 (§۵.۶)؛ builder اصلاً فایل‌های hc را باز نمی‌کند |

### ۴.۳ Schema (مجموعهٔ اجمالی)

```sql
-- هویت
works(work_id TEXT PK, work_name TEXT);
editions(edition_id TEXT PK, work_id TEXT FK, edition_name TEXT,
         source_version TEXT, exported_at TEXT);
volumes(volume_id TEXT PK, edition_id TEXT FK, volume_no INT NULL,
        volume_title TEXT, volume_strategy TEXT,
        page_count INT, item_index_min INT, item_index_max INT,
        ambiguity_flag INT DEFAULT 0,        -- 1 اگر overlap با جلد دیگر دارد
        overlap_note TEXT);                  -- جفت/بازه‌ی overlap (evidence)

-- صفحات (45,844 سطر)
pages(page_id TEXT PK,            -- <volume_id>__p<item_index>[__d<n>] — کلید یکتا
      item_index INT, dup_rank INT DEFAULT 0,
      volume_id TEXT FK, barg INT NULL, section TEXT,
      content_sha256 TEXT, char_count INT,
      record_class TEXT, status TEXT,       -- ok/short/empty/truncated_at_2000/dup_item_index
      flag_short INT, flag_empty INT, flag_truncated_2000 INT,
      dup_of TEXT NULL,                     -- page_id هم‌item_index با dup_rank کم‌تر
      seq_in_volume INT, seq_global INT,
      heading_record_id TEXT NULL,          -- hctx:... (فقط شناسه)
      context_record_id TEXT NULL,          -- hcctx:... (فقط شناسه — محتوای رکورد هرگز)
      next_page_id TEXT NULL, next_item_index INT NULL,
      captured_at TEXT, source_page_id INT, url TEXT,
      text TEXT, text_normalized TEXT,
      text_tokens TEXT);                    -- ستون FTS (§۴.۶)
CREATE INDEX idx_pages_ii ON pages(item_index, dup_rank);
CREATE INDEX idx_pages_vol ON pages(volume_id, item_index);

-- هدرها (10,739 سطر)
headings(record_id TEXT PK,        -- hctx:<page_id>
         page_id TEXT FK, item_index INT, volume_id TEXT FK,
         heading_text TEXT, heading_hash TEXT,
         normalized_text TEXT,     -- برای topic identity (§۴.۵)
         topic_id TEXT FK,
         parent_heading_page_id TEXT NULL,
         next_page_id TEXT NULL,   -- association B7: کوتاه‌های ابتدای بخش بعدی
         children_count INT);
CREATE INDEX idx_headings_topic ON headings(topic_id);
CREATE INDEX idx_headings_vol ON headings(volume_id, item_index);

-- موضوعات (1,082 سطر — در read model زندهٔ v0003: 1,080 سطر؛ ببینید §۴.۲، یادداشت به‌روزرسانی)
topics(topic_id TEXT PK,           -- 't-' + sha1(normalized_text)[:12] — پایدار
       normalized_text TEXT UNIQUE, display_text TEXT,
       page_count INT, volume_count INT, first_page_id TEXT,
       first_item_index INT);

-- سوره (شرطی — در v0003 خالی می‌ماند)
surahs(surah_id TEXT PK, canonical_name TEXT, confidence REAL, page_count INT);

-- FTS5 (ستون text_tokens)
CREATE VIRTUAL TABLE pages_fts USING fts5(
  page_id UNINDEXED, item_index UNINDEXED, tokens,
  content='pages', content_rowid='rowid', tokenize='unicode61');

-- پوشش (6 بازه + کل)
coverage(scope TEXT,               -- 'global' | volume_id
         missing_from INT, missing_to INT, missing_count INT,
         status TEXT DEFAULT 'backfill_pending',
         note TEXT);

-- build meta (build_meta.db داخل readmodel dir)
build_meta(key TEXT PK, value TEXT);  -- corpus_version, content_sha256, schema_ver,
                                       -- policy_versions, built_at, db_sha256, ...
```

**Invariants builder (اجباری، test‌دار):**
1. **Source read-only:** همهٔ فایل‌های corpus با mode `rb`/read-only باز می‌شوند؛ builder هیچ‌چیز در درخت corpus نمی‌نویسد (test: mtime/size قبل/بعد).
2. **Deterministic:** INSERT مرتب (page_id) + `PRAGMA` ثابت + بدون timestamp تصادفی در داده → `db_sha256` ثابت برای همان ورودی (test: دو build متوالی = SHA یکسان).
3. **Version directory:** خروجی در `readmodel/v0003/tasnim_readmodel.db` — هر نسخهٔ corpus یک دایرکتوری؛ **سوییچ نسخه = تغییر path/setting، نه تخریب نسخهٔ قبلی** (v0004 از backfill Track A همین مکانیزم را می‌گیرد).
4. **حافظهٔ bounded:** streaming خط‌به‌خط (pages.jsonl 170MB هرگز در memory نمی‌آید)؛ commit هر 5,000 سطر.
5. **No crawler-DB access:** builder تنها ورودی‌ها = `pages.jsonl`, `heading-records.jsonl`, `corpus.json`, `manifest.json`. **`hidden-context-records.jsonl` و `context-records.jsonl` هرگز باز نمی‌شوند** — محتوای ممنوعه اصلاً وارد process builder نمی‌شود (لایهٔ اول HP-1).
6. **Validation در build:** شمارنده‌ها با manifest آکورد (45,844 / 10,739 / 28 / 6 بازه)؛ عدم تطابق = build fail.

### ۴.۴ Verdict SURAHI (B6) — **SURAH_INDEX_NOT_SUPPORTED**

- شواهد (fact-check §۶): هیچ فیلدی با نام surah در schema؛ پیشوند سخت `تفسیر سوره/سوره/سورة…` در 10,739 هدر: **0 مورد**؛ canonical coverage **0/114**؛ 0 صفحهٔ تعلق‌داده‌شده.
- 265 هدر حاوی «سوره»/«سورة» همه sub-headingهای عمومی‌اند (هدف سوره ×75، خطوط کلی معارف سوره ×77، نام‌ها و اوصاف سوره ×56…) — **نام سوره نمی‌دهند**؛ استفاده از آن‌ها = ساخت داده.
- شواهد آینده (فقط یادداشت، نه در V1): 63/114 نام canonical در متن صفحات پیدا می‌شوند (probe روی 250 نویسهٔ اول) — نام‌های تک‌حرفی (ص/ق) پر فالتی‌پوزیتیف‌اند؛ این مسیر برای corpus نسخهٔ بعدی (v0005+) با معیار confidence جداست.
**نتیجهٔ عملی:** `/surahs` → `200 {status:"unavailable", reason, data:[]}`؛ UI → «در حال تکمیل»؛ `/surahs/{id}` → `404 code=SURAH_UNAVAILABLE`. جدول `surahs` در schema **می‌ماند** (شرطی) تا نسخهٔ بعدی بدون schema change پر شود.

### ۴.۵ Topic identity (B6)

- **Normalization rule (mکتوب، نسخهٔ `tasnim-topic-norm/1.0`):** (1) strip؛ (2) ارقام ۰-۹/٠-٩→ASCII؛ (3) collapse whitespace؛ (4) حذف شمارهٔ ابتدایی `^\(\d{1,3}\)|^\d{1,3}[\)\.\-\:]\s*` (یک‌بار)؛ (5) normalize همز/همزهٔ یوتیفیک: ٔ(0654)→e(06CC) حذف، ٲ→ا، ٵ→ئ، ە(06D5)→ه، ۍ→ی؛ (6) strip ` .:ـ-` از انتها. (مورد ۵ ضروری است: در داده `گزیدهٔ تفسیر` ×1531 / `گزیده تفسیر` ×108 / `گزیدهٴ تفسیر` ×38 — بدون hamza-norm سه topic جداست؛ با norm یکی می‌شوند.)
- **Identity:** `topic_id = 't-' + sha1(normalized_text)[:12]` — پایدار، بدون وابستگی به ترتیب build.
- **Display:** `display_text` = فرکانس‌برترین شکل خامِ همان normalized (از رکوردها، deterministic).
- **Hierarchy:** فقط `parent_heading_page_id` ذخیره می‌شود؛ درخت کامل در UI رندر نمی‌شود (عمق max 7,213 = زنجیرهٔ طولانی volume-wide)؛ topic detail = رخدادها + parent topic (اگر normalized-textِ parent خود یک topic باشد) + شمارندهٔ children.

### ۴.۶ برنامهٔ tokenization فارسی برای FTS5 (صادقانه)

**واقعیت:** `porter` استمرینگ **انگلیسی** است و برای فارسی بی‌اثر/مضر؛ tokenizer پیش‌فرض `unicode61` مرزهای کلمهٔ عربی/فارسی را بر اساس Unicode categories می‌بُرد — کار می‌کند ولی (a) ZWNJ (U+200C, category Cf) رفتار پیش‌بینی‌ناپذیر دارد و (b) هیچ stem فارسی نمی‌دهد. ماژویین tokenizer سفارشی (ICU/custom module) در build استاندارد sqlite پایتون سازمان قابل اتکا نیست (offline-first؛ بدون dependency باینری جدید).

**طرح V1 — pre-tokenization deterministic (بدون dependency):**
1. **Tokenizer سمت builder** (`tokenize_fa/1.0`): روی `text_normalized` (policy `tasnim-p1` corpus: ascii_digits + collapse_ws + strip): (a) ارقام عربی/extended→ASCII؛ (b) **ZWNJ→space** (کلمه‌ها جدا می‌شوند — trade-off: توکن بیشتر، ولی بدون missed-match برای جستجوی کلمه‌وار)؛ (c) جدا کردن `<` `>` ﴿ ﴾ « » «…» و نشانه‌ها؛ (d) خروجی: رشتهٔ space-separated از توکن‌های `[\u0621-\u064A]+|[\u0660-\u0669→0-9]+|[A-Za-z0-9]+` (توکن خالی حذف).
2. **FTS5** روی `text_tokens` با `tokenize='unicode61'` (توکن‌ها از‌قبل جداست؛ unicode61 عملاً identity می‌ماند).
3. **Query pipeline:** همان tokenizer روی query → هر توکن با prefix `توکن*` → `AND` بین توکن‌ها → `bm25()` rank.
4. **محدودیت‌های مکتوب (در UI/راهنما + OpenAPI):** (a) **بدون stem فارسی** — فرم‌های ریشه‌تغییر‌یافته (مثلا «گشود» ≠ «گشودن» در ریشه) نمی‌خورند؛ (b) prefix matching فرم‌های **پسوندی** را پوشش می‌دهد («تفسیر*» می‌خورد به «تفسیری/تفسیرها») — اصلی‌ترین مورفولوژی فارسی؛ (c) ZWNJ-split ممکن است کلمه‌های مرکب را به دو توکن بشکند («می‌گردد»→«می»+«گردد») — جستجوی «می گردد» (با space) می‌خورد.
5. **Snippets:** `snippet()` روی `text` اصلی (خوانایی فارسی)؛ highlight با `<mark>`.
6. **حجم:** pages_fts ≈ +30–40% روی متن (حدود 60–80MB) — کل DB تخمین ≈ 450–550MB. قابل‌قبول (فایل واحد، WAL).

---

## ۵. قرارداد API (B9)

### ۵.۱ کلیات

- **Base path:** `/api/v1/tasnim/` — هم‌بند با SSR (یک Flask app).
- **Format:** JSON فقط (UTF-8). **OpenAPI 3.1** در `/api/v1/tasnim/openapi.json` + Swagger UI استاتیک در `/api/v1/tasnim/docs` (خودسرو، بدون CDN).
- **Envelope موفق:**
```json
{ "data": { ... },
  "meta": { "request_id": "req_01J...", "readmodel": { "version": "v0003",
    "content_sha256": "40f45e0b…" }, "generated_at": "2026-11-07T00:00:00Z" } }
```
- **Envelope خطا (RFC-7807-style):**
```json
{ "type": "https://tasnim.ai.ismc.ir/errors/page-not-found",
  "title": "Page not found", "status": 404,
  "code": "PAGE_NOT_FOUND",
  "message": "صفحه‌ای با item_index 99999 در پیکره وجود ندارد.",
  "details": { "item_index": 99999,
    "in_missing_range": [3649, 11182],
    "suggestion": "نزدیک‌ترین صفحات موجود: 11183" },
  "request_id": "req_01J..." }
```
- **قانون صمیمت (honesty):** endpoint بدون دادهٔ واقعی **هرگز** دادهٔ ساختگی نمی‌دهد: یا `404` با `code` توصیفی یا `200` با `"status":"unavailable"` + `reason` مکتوب (surahs).
- **Rate limiting (الگوی DB-backed سازمان، مطابق `backend/auth.py`):** جدول `tasnim_rate_limits` (ip, endpoint_class, window_start, count)؛ سقف‌ها: `search` = 30/min/IP، `read` (bقیه) = 120/min/IP؛ `429` + `Retry-After` + `code=RATE_LIMITED`. (V1 عمومی است؛ auth کاربری ندارد — محدودیت بر اساس IP.)
- **Cache policy (بر پایهٔ ETag):**
| کلاس endpoint | ETag | Cache-Control |
|---|---|---|
| `/catalog`, `/statistics` | hash(build_meta sha + endpoint) | `public, max-age=60, stale-while-revalidate=300` |
| `/volumes`, `/topics` | hash(build sha + canonicalized params) | `public, max-age=300` |
| `/pages/{n}`, `/volumes/{id}`, `/topics/{id}`, `/surahs*` | strong = content_sha256 رکورد (immutable در هر build) | `public, max-age=3600` |
| `/search` | weak `W/"q+params+build"` | `no-store` |
- **Pagination:** `limit` (default 50، max 200) + `offset` **و** `page_token` (opaque؛ `next_page_token` در `meta`) — cursor روی ترتیب `item_index`. `ORDER BY` فقط از whitelist سخت‌کدشده (قاعدهٔ سازمان ۷)؛ `LIMIT/OFFSET` واقعی در SQL — کل‌جدول‌بارگذاری ممنوع.

### ۵.۲ دوازده endpoint

**1) `GET /catalog`** — هویت + آمار کل.
```json
"data": { "work": { "work_id": "tasnim_hamta", "name": "تفسیر تسنیم" },
 "edition": { "edition_id": "tasnim_hamta__hamta-2026", "name": "خروجی کراول hamta-2026" },
 "counts": { "pages": 45844, "volumes": 6, "topics": 1082, "headings": 10739,
   "missing_item_index": 45243 },
 "coverage": { "present_ratio": 0.4998, "definition": "45844/(45844+45243)" },
 "rag_status": "not_connected",
 "readmodel": { "version": "v0003", "content_sha256": "40f45e0b…" } }
```

**2) `GET /volumes?limit&offset&sort=volume_no|page_count`** — فهرست 6 جلد. هر عنصر: `volume_id, volume_no (null مجاز), title, page_count, item_index_min/max, coverage{missing_count,ranges}, ambiguity{flag, overlap_note}, first_page_item_index, last_page_item_index`.

**3) `GET /volumes/{volume_id}`** — جزئیات: همهٔ فیلدهای 2 + `top_headings` (10 هدر پرتکرار در جلد، از `headings`) + `missing_ranges` (از `coverage`) + `dup_item_index_with` (جفت‌های 9گانه برای vol001/vol047) + `first_page`/`last_page` ref.

**4) `GET /surahs`** — **honest unavailable:**
```json
{ "data": { "status": "unavailable",
 "reason": "در پیکرهٔ v0003 هیچ مارکر مطمئن سوره وجود ندارد: 0/114 پوشش canonical از هدرها؛ فیلد surah در schema نیست.",
 "data": [],
 "next_planned": "surah index text-level برای نسخهٔ بعدی پیکره (خارج از V1)" },
 "meta": { ... } }
```

**5) `GET /surahs/{surah_id}`** — `404` با `code=SURAH_UNAVAILABLE` + همان reason.

**6) `GET /topics?limit&offset&page_token&q&min_pages&sort=page_count|name`** — فهرست از 1,082 موضوع. هر عنصر: `topic_id, display_text, page_count, volume_count, first_page_id, first_item_index`. `q` = prefix روی `normalized_text` (ترتیب: LIKE prefix + فیلتر؛ جدول 1,082 سطر است).

**7) `GET /topics/{topic_id}`** — جزئیات: identity + counts + `parent_topic` (nullable) + `occurrences` paginated (هر سطر: `item_index, page_id, volume_ref{volume_id,volume_no}, heading_text, is_heading_page`) + `sample_pages` (3).

**8) `GET /pages/{item_index}?dup_rank=0`** — **قلب contract.** (9 مقدار item_index دو سطر دارند؛ default `dup_rank=0`؛ list در `duplicates`.)
```json
"data": {
  "page_id": "tasnim_hamta__hamta-2026__vol047__p3036",
  "item_index": 3036, "dup_rank": 0,
  "volume": { "volume_id": "…vol047", "volume_no": 47, "title": "جلد 47",
              "attribution": "recorded", "ambiguity": false },
  "barg": 3037,
  "heading": null,
  "visible_content": { "text": "…", "char_count": 2000,
                       "record_class": "CONTENT_PAGE" },
  "next_page_reference": { "item_index": 3037, "page_id": "…p3037",
                           "exists": true, "gap_before": 0 },
  "previous_page_reference": { "item_index": 3035, "exists": true, "gap_before": 0 },
  "metadata": { "page_id": "…", "content_sha256": "76d61f13…",
                "captured_at": "2026-10-26 05:38:15", "source_page_id": 14764,
                "section": "تفسیر تسنیم جلد (47)",
                "source_url": "https://tasnim.hamtaa.org/payload?…" },
  "quality": { "status": "truncated_at_2000", "flags": ["truncated_at_2000"],
               "truncated_at_source": true, "source_char_cap": 2000 },
  "duplicates": [ { "dup_rank": 1, "page_id": "…vol047__p3036__d1" } ],
  "reference": { "work_id": "tasnim_hamta", "edition_id": "tasnim_hamta__hamta-2026",
                 "volume_id": "…vol047", "volume_no": 47,
                 "item_index": 3036, "barg": 3037,
                 "page_id": "tasnim_hamta__hamta-2026__vol047__p3036",
                 "content_sha256": "76d61f13…",
                 "source_url": "https://tasnim.hamtaa.org/payload?…",
                 "canonical_url": "https://tasnim.ai.ismc.ir/page/3036" },
  "rag_status": "not_connected"
}
```
- `heading` (وقتی `heading_record_id` پر است — 10,739 صفحه): `{ "record_id": "hctx:…", "text": "…", "next_page_id": "…" }` — association B7 (هدرهای کوتاهِ ابتدای بخش بعدی `next_page_id` دارند).
- `volume.attribution`: `"recorded"` (از `semantic.order`) یا `"ambiguous"` (وقتی item_index در overlap دو volume است) — بدون حدس.
- **جداسازی اجباری پاسخ:** `visible_content` / `heading` / `next_page_reference` / `metadata` / `quality` / `reference` — هر بخش مستقل (قالب مأموریت).

**9) `GET /pages/{item_index}/neighbors`** — برای prev/next خنک‌طلبانه:
```json
"data": { "current": 3036,
 "prev": { "item_index": 3035, "page_id": "…", "exists": true, "gap_before": 0 },
 "next": { "item_index": 3037, "page_id": "…", "exists": true, "gap_before": 0 },
 "missing_nearby": { "prev_range": null, "next_range": null } }
```
وقتی `exists:false`: `{ "item_index": 3650, "exists": false, "gap_before": 1,
"in_missing_range": [3649, 11182], "next_available_item_index": 11183 }` — UI chip «در دست بازیابی» را از همین field می‌سازد.

**10) `GET /search?q=&limit=20&offset|page_token&volume_id=&sort=relevance|item_index`**
- `q` اجباری، 2–64 کاراکتر. Response:
```json
"data": { "query": { "raw": "زبان قرآن", "tokens": ["زبان","قرآن"] },
 "total": 1234,
 "results": [ { "item_index": 19, "page_id": "…",
   "volume_ref": { "volume_id": "…", "volume_no": 1, "ambiguous": false },
   "snippet": "…زبانِ « فطرت » است که فرهنگ عمومی…",
   "heading": { "text": "پیشگفتار مفسر" },
   "quality_status": "ok" } ] },
"meta": { "next_page_token": "…" }
```
- `total` واقعی از `COUNT(*)` query هم‌شکل (برای queryهای سبک)؛ برای queryهای سنگین (≥3 توکن) `total` = `-1` + `estimated: true` (شمارش‌ساز ساختگی ممنوع).
- no-results: `200` با `total: 0` + `suggestions` (2–3 کلمهٔ پرتکرار از `topics` — واقعی از DB).

**11) `GET /statistics`** — همهٔ شمارنده‌های واقعی + **`definition` مکتوب برای هرکدام** (قاعدهٔ سازمان ۹):
```json
"data": { "pages_by_class": { "CONTENT_PAGE": 33443, "SECTION_HEADING": 10739,
   "SHORT_CONTENT": 1589, "EMPTY_PAGE": 35, "UNKNOWN_STRUCTURE": 38,
   "definition": "semantic.class_counts از manifest v0003" },
 "quality_status": { "ok": 33399, "short": 12366, "dup_item_index": 16,
   "empty": 35, "truncated_at_2000": 28,
   "definition": "quality_status.status در pages.jsonl" },
 "item_index": { "distinct": 45835, "rows": 45844, "duplicates": 9,
   "min": 0, "max": 91077,
   "missing": { "count": 45243, "ranges": [[3649,11182],[11205,39003],
     [44957,49956],[55699,55701],[55715,59590],[89280,90310]],
     "definition": "item_indexهای بدون صفحه، از gaps manifest" } },
 "text_length": { "p50": 64, "p90": 1710, "p99": 1985, "max": 2000,
   "definition": "histogram manifest v0003" },
 "topics": { "distinct_normalized": 1082, "multi_page": 64,
   "definition": "normalize tasnim-topic-norm/1.0 روی 10739 هدر" },
 "surah": { "status": "not_supported", "coverage": "0/114",
   "definition": "fact-check PCM-20.6.4: 0 هدر با پیشوند سخت" } }
```

**12) `GET /health`** — liveness + `readmodel{version, content_sha256, db_sha256}` + `db_quick_check: ok` + `uptime_s`. بدون PII. (برای healthcheck compose.)

### ۵.۳ Swagger / چک contract

- `openapi/tasnim-v1.openapi.yaml` (3.1) با همهٔ 12 operation + error components + sample responses واقعی (از v0003).
- چک خودکار (الگوی `deploy/pcm19_openapi_check.py`): spec ↔ app زنده (signature routeها + fieldهای پاسخ) — در CI.

### ۵.۶ خصوصیت امنیتی HP-1 (انزواي hidden-context) — **mکتوب و test‌دار**

> **HP-1:** هیچ مقدار از `hidden_summary`, `retrieval_context`, `next_page_summary` (رکوردهای `hcctx:*`/`ctx:*`)، در (الف) read-model، (ب) هر پاسخ API، (ج) هر صفحهٔ SSR، (د) هر asset استاتیک، **نمی‌آید**.
- لایهٔ 1 (builder): builder اصلاً `hidden-context-records.jsonl` / `context-records.jsonl` را باز **نمی‌کند** (§۴.۳ invariant 5) — ستونی هم برای محتوای آن‌ها وجود ندارد؛ فقط `heading_record_id`/`context_record_id` (شناسه‌های امن) از `pages.jsonl` کپی می‌شوند.
- لایهٔ 2 (serializer): whitelist fields (§۵.۲) — serializer فقط کلیدهای مکتوب را serialize می‌کند (deny-by-default).
- لایهٔ 3 (tests): T-HC-1..4 (§۹) — scan زیررشتهٔ کلیدهای ممنوعه در body همهٔ پاسخ‌ها + DOM scan در E2E.
- لایهٔ 4 (policy): policy مکتوب corpus («must never be rendered publicly») در `build_meta.policy_versions` ثبت می‌شود.

### ۵.۷ RAG-ready properties (B11)

1. **Canonical URL پایدار:** `https://tasnim.ai.ismc.ir/page/<item_index>` (+ `?dup_rank=` فقط برای 9 مورد تکراری) — پایدار بین نسخه‌های readmodel (item_index identity است).
2. **بلاک `reference`** در `/pages/{n}` (§۵.2-8): work/edition/volume/item_index/barg/page_id/content_sha256/source_url/canonical_url — مستقیم قابل استفاده برای citation در RAG.
3. **Hidden-context exclusion** = HP-1 (§۵.۶) — ورودی RAGِ بعدی هم فقط همین fields public.
4. **`rag_status: "not_connected"`** صریح در `/catalog` و `/pages/{n}` — **هیچ** fake RAG، هیچ endpoint پاسخ، هیچ `ai:` field در V1.

---

## ۶. (جای شمارهٔ ۶ — در ۵.۲/۵.۷ پوشیده شد؛ این بخش خالی نماند: «نسخه‌بندی»)

**Versioning:** API = `v1` در path؛ readmodel version در `meta` همهٔ پاسخ‌ها؛ تغییر شکست‌دهنده contract → `v2` (V1 freeze پس از acceptance). Read-model **version-swappable**: بعد از backfill (v0004) → `readmodel/v0004/` build → setting path سوییچ → v0003 دست‌نخورده می‌ماند (rollback = برگشت setting).

---

## ۷. طرح دپلوی (فقط PLAN — در این فاز صفر تغییر)

### ۷.۱ `docker-compose.tasnim.yml` (در ریشهٔ worktree؛ spec)

```yaml
services:
  tasnim-api:
    build: { context: tasnim-web, dockerfile: Dockerfile }   # python:3.12-slim
    image: tasnim-api:1
    container_name: tasnim-api
    command: ["python", "-X", "utf8", "server.py"]
    ports: ["127.0.0.1:5071:5071"]        # فقط loopback روی s53؛ public = nginx
    volumes:
      - tasnim_readmodel:/data/tasnim_readmodel:ro   # readmodel/v0003/…
    environment:
      - TASNIM_DB_PATH=/data/tasnim_readmodel/v0003/tasnim_readmodel.db
      - TASNIM_LOG_LEVEL=INFO
      - TASNIM_RATE_SEARCH=30
      - TASNIM_RATE_READ=120
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:5071/api/v1/tasnim/health',timeout=3).status==200 else 1)"]
      interval: 30s
      timeout: 5s
      retries: 3
    restart: unless-stopped
    depends_on: []

  tasnim-web:
    image: nginx:1.27-alpine
    container_name: tasnim-web
    ports: ["5070:80"]                     # تنها پورت public روی s53
    volumes:
      - ./deploy/nginx/tasnim-web.conf:/etc/nginx/conf.d/default.conf:ro
    healthcheck:
      test: ["CMD", "wget", "-qO-", "http://127.0.0.1/healthz"]
      interval: 30s
      timeout: 5s
      retries: 3
    restart: unless-stopped
    depends_on:
      tasnim-api: { condition: service_healthy }

volumes:
  tasnim_readmodel:
```

نکات: (a) **secret در image نیست** — V1 اصلاً secret ندارد (سایت عمومی read-only؛ اگر بعداً لازم شد، الگوی PCM-09 سازمان: env + scrypt در DB). (b) read-model `:ro` mount — container هرگز نمی‌نویسد. (c) nginx: سرو static assets (`/static/`) + proxy `/` و `/api/` به `tasnim-api:5071` + `X-Forwarded-Proto`/`X-Real-IP` + `/healthz` استاتیک. (d) `restart: unless-stopped` هر دو.

### ۷.۲ انتخاب پورت — توجیه در برابر inventory s53

مهمانی‌های s53 (از RECON؛ **همه باید اجتناب شوند**): 4000, 4001, 11434, 8000, 8001, 7474, 7687, 6333, 9001, 8033, 8034, **8003–8054**, **5436–5477**, 8290. (همچنین 5055 = backend محلی dev روی Windows.)

| پورت | استفاده | تداخل؟ |
|---|---|---|
| **5070** (public، nginx) | ingress → s53:5070 | ❌ در هیچ بازه نیست (54xx/80xx/40xx/9001/7474/7687/6333/8290/11434) — **آزاد** |
| **5071** (internal، loopback-only) | tasnim-api | ❌ در هیچ بازه — **آزاد**؛ چون فقط 127.0.0.1 است حتی رقابت فرضی هم risk ندارد |
| 5055 | backend داشبورد (dev) | untouched |

### ۷.۳ طرح اتصال `tasnim.ai.ismc.ir` (فقط PLAN — نیازمند تأیید مالک ingress؛ R10)

وضعیت فعلی (BASELINE/RECON): DNS ✅ → 172.30.0.133؛ TLS ❌ (default cert `CN=admin.ai.ismc.ir` → `SEC_E_WRONG_PRINCIPAL`); ingress = **Kong + Tyk + cloudflared** (نه nginx per-host؛ الگوی nginx vhost فقط برای s52 است).

مراحل اجرا (فاز بعدی، بعد از تأیید):
1. صدور گواهی Let's Encrypt برای **`tasnim.ai.ismc.ir`** با همان mechanism که `rag.`/`docs.` را دارد (YE2 chain؛ precedents: `rag.ai.ismc.ir` انقضا 2027-11-01، `admin.ai.ismc.ir` انقضا 2027-01-01).
2. افزودن route در Kong: `host = tasnim.ai.ismc.ir` → upstream `s53:5070` (IP دقیق s53 از inventory سرورها در RECON هنگام اجرا) + header `X-Forwarded-Proto: https` + SNI termination با گواهی جدید.
3. (اختیاری) route `*.tasnim.ai.ismc.ir` — نه در V1.
4. Smoke test: `curl -vI https://tasnim.ai.ismc.ir/api/v1/tasnim/health` + verify cert CN + verify 200.
5. Rollback: حذف route (2 دقیقه) — هیچ state‌ای در ingress نمی‌ماند.

**در این مأموریت: صفر تغییر DNS/TLS/proxy.**

### ۷.۴ runbook محلی (dev، Windows)

`python readmodel_builder.py --corpus <path-to-builds/v0003> --out readmodel/v0003` → `python server.py` (port 5071، بدون 5070) — compose فقط برای s53 است.

---

## ۸. (جای شمارهٔ ۸ — پوشیده شد در ۹؛ این بخش: «معماری تست» به‌عنوان ۹ باقی می‌ماند؛ برای نگه‌داشتن شماره‌گذاری مأموریت، §۸ = «چک‌لیست build invariants + observability»)

**Observability V1 (حداقل):** structured log JSON (request_id, endpoint, status, ms, db_ms)؛ `/health` با `uptime_s` + `db_quick_check`؛ metric سادهٔ `tasnim_requests_total` در `/statistics` (اختیاری). **بدون** dependency خارجی (پوشش کامل‌تر observability = مأموریت PCM-10 الگو، خارج از V1).

---

## ۹. استراتژی تست (B14)

### ۹.۱ Unit (read-model builder + API)

| گروه | موارد (هرکدام ≥1 test) |
|---|---|
| parser/mapping | page_id round-trip؛ `__d1` → `dup_of` + `dup_rank`؛ mapping 6 volume؛ volume_no null حفظ شود |
| item_index | 45,835 distinct؛ 9 duplicate → 18 سطر با `dup_of` صحیح؛ gap ranges دقیقاً 6 بازهٔ manifest |
| flags | `capped_2000` فقط با `truncated_at_source=true` (نه صرفاً len)؛ `empty`+`no_barg` (35)؛ `short` (12,366) |
| heading mapping | 10,739 رکورد؛ parent pointer همه resolve (orphan=0)؛ `next_page_id` preserved برای هدرهای کوتاه (B7 sample test روی hctx:…p14) |
| topics | normalization rule (hamza/ZWNJ/digit/leading-number cases)؛ 1,082 distinct؛ `topic_id` پایدار (دو build = id یکسان)؛ گزیده‌تفسیر 3شکل → 1 topic |
| **hidden-context isolation** | T-HC-1: builder files opened = exact set (mock/monkeypatch open)؛ T-HC-2: schema به `hidden_summary`/`retrieval_context` هیچ column/table ندارد (introspection)؛ T-HC-3: serializer whitelist — هر field غیر-whitelist raise می‌کند |
| FTS tokenization | ZWNJ split؛ digit map؛ prefix match «تفسیر*» می‌خورد به «تفسیری»؛ query pipeline end-to-end روی 3 صفحهٔ fixture |
| pagination | limit/offset + page_token؛ boundary (offset=0، offset=max، limit>200 clamp) |
| error contract | هر `code` حداقل یک test؛ format RFC-7807 fields کامل + `request_id` |
| rate limit | 30/min search → 429 + Retry-After (clock mock) |
| ETag | 304 روی repeat request؛ تغییر build sha → ETag جدید |

### ۹.۲ Integration (corpus → read model → API → frontend)

- I-1: build واقعی روی v0003 (در test: روی snapshot کوچک + fixture) → `db_sha256` deterministic (دو build = یکسان).
- I-2: همهٔ 12 endpoint × {200 shape, 404 honest, 429, 304} با test client Flask.
- I-3: `/pages/3036` → shape کامل §۵.۲-8 (ترuncated page واقعی) + `/pages/2` → `duplicates` populated + `/pages/99999` → 404 با `in_missing_range`.
- I-4: `/search?q=زبان قرآن` → total>0 + snippet؛ `/search?q=xyzxyz` → total 0 + suggestions.
- I-5: SSR render هر 10 صفحه (test client) + assert `dir="rtl"` + `lang="fa"` + breadcrumb.
- I-6: source read-only — mtime/size کل درخت corpus قبل/بعد build = یکسان.
- I-7: version swap — readmodel/v0003 + v0003-b (copy) هر دو سالم؛ سوییچ path → `/catalog` version جدید.

### ۹.۳ E2E — سناریوی ۱۲ قدم (desktop + viewport 375px موبایل؛ هر قدم با assert DOM)

1. Home بار شود: گرید 6 جلد (کاور SVG + badge جلد نامشخص) + پوشش کل + جستجوی سریع + continue-reading (localStorage خالی → default).
2. `/volumes` — 6 سطر + sort.
3. `/volume/…vol047` — کاور + coverage (2 بازهٔ گم‌شده) + top headings + ambiguity note (overlap با volkey).
4. اولین صفحهٔ خواندنی جلد (item_index 0) باز شود؛ reader: متن + breadcrumb + controls.
5. metadata drawer: SHA کپی‌شود + **assert: هیچ substring «hidden_summary»/«retrieval_context» در DOM** (T-HC-4).
6. prev/next: از 3036 → 3037 (gap 0)؛ از 11182 (آخرِ قبلِ gap) → next = 11183 + chip «7,534 صفحه در بازه در دست بازیابی».
7. صفحهٔ truncated (3036): banner «متن در منبع قطع است» + badge `truncated_at_2000`.
8. `/topics` — 1,082 موضوع paginated؛ جستجوی prefix «بحث» → بحث روایی.
9. `/topic/<بحث روایی>` — 1,302 رخداد + pagination + parent/child.
10. `/search?q=زبان قرآن` — نتایج + `<mark>` highlight + no-results path با `q=zzzz` (suggestions).
11. `/surahs` — «در حال تکمیل» + API response `status=unavailable` (honest).
12. Pass نهایی: keyboard-only (تمام قدم‌ها بدون ماوس) + `prefers-reduced-motion` on + viewport 375px (بدون horizontal scroll) + dark mode toggle کنتراست.

### ۹.۴ Regression و قواعد

- **رگرسیون کامل سازمان:** 200-test backend suite (`test_api test_projects test_dashboard test_knowledge_api test_word_factory test_dump test_work_registry test_queue test_corpus_builder test_studio_api test_api_contract`) + corpus suites (`test_corpus_tasnim test_corpus_semantic test_corpus_semantic_v3 test_corpus_gap_report test_corpus_truncation_report test_corpus_backfill`) — **بدون تغییر**؛ اضافه‌شدن suites جدید: `test_readmodel`، `test_tasnim_api`، `test_tasnim_e2e`.
- **قاعدهٔ skip:** هیچ skip بی‌دلیل؛ هر `@unittest.skip` باید reason مکتوب + شمارهٔ مأموریت داشته باشد (الگوی سازمان: 0 skip در acceptance PCM-20.4).
- **Windows caveats:** همهٔ SQLite connectionها در teardown بسته می‌شوند (open handle مانع replace می‌شود)؛ `python -X utf8` برای کنسول؛ test support ماژول جدید `tasnim_test_support.py` (الگوی `pct_test_support`): readmodel موقت **مشترک** + `reset()` قبل از هر کلاس؛ ترتیب ماژول‌ها مهم نباشد.
- CI: test-only (الگوی `.gitlab-ci.yml` موجود) — بدون job deploy.

---

## ۱۰. Risk Register (Track B) + Stop Conditions

| # | ریسک | شواهد | مدیریت در V1 | **Stop condition / وظیفهٔ فاز ۳** |
|---|---|---|---|---|
| R1 | ابهام volume (3 جفت overlap؛ volume_no null) | fact-check §۳ | کلید = page_id/item_index؛ flag `ambiguity`؛ breadcrumb احتیاط | اگر در build v0004 (post-backfill) mapping volume تغییر کند → فقط read-model rebuild (کد ثابت). اگر cross-volume `next_page_id` (اکنون 0) ظاهر شود → prev/next به global item_index order تغییر می‌کند — **stop و بازبینی contract** |
| R2 | **Surah NOT_SUPPORTED** | 0/114؛ 0 هدر سخت؛ 265 هدر شل = sub-heading عمومی | `/surahs` = honest unavailable + UI «در حال تکمیل» | **فاز ۳ نباید** با 265 هدرِ شل surah index بسازد (فالتی). text-level evidence (63/114 در متن) فقط برای نسخهٔ بعدی corpus با معیار confidence — خارج از V1 |
| R3 | صفحات 2000-نویسه‌ای (28) | همه `truncated_at_source=true` | banner TRUNCATED اجباری + flag رسمی | رندر خام بدون banner = **stop** (acceptance fail) |
| R4 | ingress مشترک (Kong/Tyk) — owner coordination | R10 RECON؛ default cert | V1 روی s53:5070 (http داخلی) قابل تست است؛ TLS/ingress = فاز جدا | **deploy به `tasnim.ai.ismc.ir` بدون تأیید مالک ingress = ممنوع** (stop) |
| R5 | عمق hierarchy (max 7,213) | fact-check §۷.۲ | UI درخت نمی‌کشد؛ فقط parent pointer + occurrence list | اگه خواستیم TOC volume کامل → الگوریتم lazy-loading لازم است (خارج از V1) |
| R6 | 45,243 صفحهٔ گم‌شده (≈50% فضای item_index) | 6 بازه؛ Track A در Gate A | `/coverage` + chipها + statistics | بعد از backfill (v0004) → rebuild readmodel + **مقایسهٔ شمارنده‌ها** (rollback = path swap) |
| R7 | محدودیت FTS فارسی (بدون stem) | §۴.۶ | prefix matching + کشفیات مکتوب در راهنما/UI | انتظار stem = scope creep V2 |
| R8 | Windows harness (handles/UTF-8) | قواعد AGENTS §۴ | `tasnim_test_support` + `-X utf8` + teardown close | flake در تست = stop تا root-cause |
| R9 | نقض hidden-context (R11 RECON) | 10,728 رکورد system-only | HP-1 چهارلایه‌ای (§۵.۶) | هر leak = **release-blocking** |
| R10 | حجم build (170MB streaming) | §۴.۱ | bounded memory + commit 5k | build > 30min روی dev → به s53 (خارج از scope V1 test) |

---

## ۱۱. خلاصهٔ تصمیمات کلیدی (قرار دادن در یک نگاه)

| تصمیم | انتخاب | یک‌خط دلیل |
|---|---|---|
| کلید ناوبری | `page_id`/`item_index` | volume مبهم است (§۴.۲)؛ item_index identity اصلی است |
| frontend | Flask SSR + Jinja + vanilla JS | الگوی سازمان، LCP، a11y، بدون-JS؛ SPA هیچ مزیت واقعی ندارد |
| read model | SQLite FTS5 جدا، versioned dir | 224MB JSONL قابل streaming-query نیست؛ v0004 بدون تخریب v0003 |
| FTS فارسی | pre-tokenization deterministic + unicode61 + prefix | بدون dependency باینری؛ صادقانه محدود (بدون stem) |
| surah | honest unavailable | 0/114 شواهد — ساخت = نقض قاعدهٔ ۹ |
| topics | 1,082 normalized + stable id | شواهد قوی (10,739 هدر؛ 64 تکراریِ چندصفحه) |
| کاور | SVG تایپوگرافی deterministic + لیبل «جلد رسمی نیست» | no fake covers (B3) |
| فونت | Vazirmatn + Noto Naskh Arabic (+Amiri display)، self-hosted OFL | MASTER.md فونت‌ها فارسی نمی‌دانند؛ offline-first |
| پورت | 5070 public / 5071 loopback | در برابر inventory s53 آزاد (§۷.۲) |
| ingress | فقط PLAN، owner-approved | R10؛ صفر تغییر در این مأموریت |
| RAG | `rag_status: not_connected` + `reference` block | آماده بدون جعل (B11) |
| hidden context | HP-1 چهارلایه‌ای + test scan | policy مکتوب corpus (B10) |

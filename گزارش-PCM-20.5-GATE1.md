# گزارش PCM-20.5 — GATE 1: پیکره‌ی معنایی نسخه‌شده (v0002)

- **امضا/تاریخ:** ۲۰۲۶-۱۱-۰۵ (UTC)
- **مأموریت:** PCM-20.5 — زنجیره‌ی واقعی Snapshot → Canonical Corpus → **Semantic Enrichment** → Dataset → Dump → Embedding → Neo4j → RAG
- **حیثیت این مرحله:** GATE 1 از ۴ — تکمیل‌شده (PASS) — کاملاً offline
- **قید:** بدون deploy، بدون لمس production، بدون git commit؛ `data/tasnim/pcm20_4/` دست‌نخورده

---

## ۱. وضعیت قبل از مرحله

- GATE 0 کامل و گزارش‌شده (`گزارش-PCM-20.5-GATE0.md`): ۸ ناسازگاری آماری توضیح داده شد؛
  gapهای `item_index` (۴۵٬۲۴۳ عدد در ۶ بازه) در منبع آفلاین قابل بازیابی نیستند
  (`/payload` سایت زنده HTML-SPA برمی‌گرداند — شواهد GATE 0-D).
- تصمیم کاربر: **GATE 1 همین حالا offline**؛ GATE 2–4 مسدود تا برگشت s52؛
  ۶۴ فایل staged `.tmp_pcm204_*` دست‌نخورده تا تصمیم جداگانه.
- زنجیره‌ی پذیرفته‌ی PCM-20.4 در `data/tasnim/pcm20_4/`: corpus v0001 (واقعی) +
  v0002/v0003 (fixture) + datasetها + dumpها.

## ۲. طراحی

**قرارداد معنایی `cs-20.5` (ruleset `semantic-rules/1.0`):**

1. **مرجع ترتیب قطعی** = `item_index`؛ کلید مرتب‌سازی:
   `volume_no → volume_id → item_index → dup_rank → source_position`.
2. **طبقه‌بندی ۶گانه** با مبنای مشخص (definitive = اندازه‌گیری‌شده / guessed = الگو/واژگان):

| کلاس | مبنا | قاعده |
|---|---|---|
| `EMPTY_PAGE` | definitive | `len(text) == 0` |
| `UNKNOWN_STRUCTURE` | definitive | هیچ حرف عربی/لاتین ندارد |
| `CONTENT_PAGE` | definitive | `len(text) >= 20` |
| `CHAPTER_HEADING` | guessed | الگوی عنوان سوره `^\s*سور[هي]` |
| `SECTION_HEADING` | guessed | شماره‌گذاری `^\s*\d+[\.،,]\s` یا ۲۹ واژگان کلیدی بخش |
| `SHORT_CONTENT` | guessed | پیش‌فرض (متن ۱–۱۹ کاراکتر بدون تطبیق) |

3. **رکوردهای Contextual پنهان** برای هر صفحه‌ی عنوان (CHAPTER/SECTION) که صفحه‌ی
   بعدِ هم‌جلدِ آن متن داشته باشد: `record_id = "ctx:<page_id>"`، `visibility=hidden`،
   `record_kind=context`، `heading_text` (کلمه‌به‌کلمه از صفحه)،
   `next_page_summary` = حداکثر ۳ خطِ اولِ verbatim صفحه‌ی بعد،
   `retrieval_context = "<heading> — <volume_title> — <summary>"`،
   `internal_tags=["hidden","heading-context",<class>]`، `source_hash` = content_hash
   صفحه‌ی عنوان، `context_hash` = sha256 canonical-JSON رکورد (بدون خودِ فیلد hash).
   **بدون هیچ تولید/تفسیر LLM:** `model=null`, `method="verbatim-extract/1.0"`،
   `prompt_version=null` — هر سه در بلوک `semantic.context_records` مانیفست.
4. **بازیابی gap فقط از منبع معتبر**؛ در غیاب آن ثبت در ledger:
   `gaps.missing_item_index.status = "unresolved"` با ۶ بازه‌ی دقیق و دلیل.
5. پیکره‌ی جدید **v0002** (kind=`corpus`) در ریشه‌ی **جدید** `data/tasnim/pcm20_5/`
   — ۳ فایل محتوایی: `corpus.json` (base + بلوک `semantic` + `stats.semantic`)،
   `pages.jsonl` (هر صفحه + بلوک `semantic`: کلاس/مبنا/قاعده/بلوک order/next_*)،
   `context-records.jsonl` (رکوردهای پنهان). محتوا فاقد هر فیلد زمان‌بسته است →
   SHA قطعی و REUSED-idempotent.

**تطبیق با GATE 1 مأموریت:** همه‌ی ۶ کلاس ✓؛ مشخص definitive/guessed ✓؛
رکوردهای پنهان با همه‌ی فیلدهای خواسته‌شده ✓؛ بدون fabrication ✓؛
نسخه‌نشینی خلاصه (method/model/prompt) در مانیفست ✓؛ gap → ledger unresolved ✓؛
پیکره‌ی immutable جدید + diff + validate + audit + idempotency + cross-root ✓.

## ۳. مهاجرت

ندارد — هیچ تغییر schema/production؛ کل مرحله read-source + write-to-new-roots.
`data/tasnim/pcm20_4/` و production s52 هرگز لمس نشدند.

## ۴. فایل/API

| فایل | عمل | توضیح |
|---|---|---|
| [`corpus/tasnim/semantic.py`](corpus/tasnim/semantic.py) | **جدید** | طبقه‌بندی، context-records، ledger، `validate_semantic` (S01–S07)، `semantic_diff` |
| [`corpus/tasnim/cli.py`](corpus/tasnim/cli.py) | تغییر | زیرمأمور `build-semantic` و `semantic-diff` + auto-detect semantic در `validate-corpus` |
| [`test_corpus_semantic.py`](test_corpus_semantic.py) | **جدید** | ۱۱ تست S-01..S-11 (fixture ۱۰ رکورد) |
| `corpus/tasnim/diff.py` | **دست‌نخورده** | `semantic-diff` خروجی مجزای `semantic-change.json` می‌سازد |

API جدیدی وجود ندارد (CLI-only؛ تغییر OpenAPI برای GATE 1 لازم نیست — سطح REST
این زیرسیستم ندارد؛ OpenAPI در گزارش نهایی با PCM-19 reconcile می‌شود).

## ۵. تست‌ها

- رگرسیون کامل: `python -X utf8 -m unittest test_corpus_tasnim test_corpus_semantic -v`
  → **Ran 27 tests — OK** (16 تست T بدون تغییر + 11 تست S جدید؛ 0 skip، 0 failure).
- پوشش S: ساختار/سنسوس (S-01)، بلوک order (S-02)، validate دوجهته V+S (S-03)،
  idempotency/REUSED (S-04)، cross-root determinism (S-05)، semantic-diff (S-06)،
  verbatim بودن context + context_hash (S-07)، عدم تغییر base (S-08)،
  زنجیره‌ی مانیفست + ledger gap (S-09)، فساد → FAIL (S-10)، قرارداد CLI (S-11).
- خطای اجرای ۱ در توسعه (ویرایشی، پیش از باز بودن این مرحله): import تایپ‌شده
  `unicodedada` → `unicodedata` (S-01..S-11 بعد از اصلاح سبز).

## ۶. نتیجه (جدول PASS/FAIL/BLOCKED/NOT VERIFIED)

| ردیف | مورد | وضعیت |
|---|---|---|
| 1 | بازسازی v0001 در ریشه‌ی جدید با SHA یکسان PCM-20.4 | **PASS** |
| 2 | ساخت v0002 معنایی (45٬844 صفحه + 10٬728 context پنهان) | **PASS** |
| 3 | validate (V01–V08 + S01–S07) روی v0002 | **PASS** |
| 4 | semantic-diff v0001→v0002 (ثبوت صفر تغییر محتوا) | **PASS** |
| 5 | idempotency (دوباره build → REUSED v0002، نسخه‌ی جدید نساخت) | **PASS** |
| 6 | cross-root determinism (ریشه‌ی دوم، SHA یکسان v0001 و v0002) | **PASS** |
| 7 | رگرسیون ۲۷ تست | **PASS** |
| 8 | عدم تغییر `data/tasnim/pcm20_4/` | **PASS** (SHAهای ۳ مانیفست ثابت — §7) |
| 9 | بازیابی ۴۵٬۲۴۳ عددِ گم‌شده‌ی item_index | **BLOCKED** — منبع آفلاین معتبر نیست (GATE 0-D)؛ ledger `unresolved` در مانیفست v0002 ثبت شد |
| 10 | تأیید A3 GitLab (GATE 0) | **NOT VERIFIED** (دسترسی خارج از محدوده‌ی offline) |

## ۷. شواهد و SHA-256

**Builds (ریشه‌ی اصلی `data/tasnim/pcm20_5/`):**

| نسخه | content_sha256 | manifest_sha256 |
|---|---|---|
| v0001 | `ee87686ac49ce9c08a4a492f4f54c23ace571bb8f048aa8a0a863bece3d542d8` | `72a3cb9354f9d78901623d2fd56191e4b93088f266ce60fff7ae33784690c6bc` |
| v0002 | `12a93e218bbc7a38d450749eca5ce25d0833b537cc13446048d430eade54f4a5` | `dfbbad3da6372a0663a30fe7b2efae31c9c8e4cd54c33341b6d1973b2601bff8` |

- content_sha v0001 **دقیقاً** مساوی v0001 پذیرفته‌ی PCM-20.4
  (`data/tasnim/pcm20_4/corpus/builds/v0001` — همان `ee87686a…`،
  manifest آنجا: `e0b0c2cea4e52342f8a924e1c08a45e06d64aa236fcf586b6fc49782c39430fc`).
- زنجیره‌ی v0002: `prev = {kind: corpus, version: v0001, path_rel: corpus/builds/v0001/manifest.json,
  sha256: 72a3cb93…}` — با SHA روی دیسک یکسان.
- فایل‌های v0002: `corpus.json` `6c9b1003…`، `pages.jsonl` `9e00bf62…`،
  `context-records.jsonl` `a1ac0421…` (هر سه در manifest با size).

**Cross-root (`data/tasnim/pcm20_5_crossroot/`):** v0001 و v0002 هر دو
content_sha با ریشه‌ی اصلی **یکسان** (v0002: `12a93e21…`) — determinism اثبات‌شده.
manifestهای crossroot متفاوت‌اند (فقط `prev.sha` source-snapshot که در هر ریشه
جدا ثبت شده) — این مورد انتظاری است؛ **محتوا** (معیض قرارداد) یکسان است.

**semantic-diff v0001→v0002** (`reports/diff_v0001_v0002/semantic-change.json`,
sha `61f92caeedb9172f18efcea4c17847a0d8812deed05d708f47e069a0fd393f47`):
pages_from=45844, pages_to=45844, added=0, recovered=0, changed=0,
unchanged=**45844**, missing=0, duplicate_rows=18, unresolved_gaps=**45243**,
context_records_added=**10728**. → طبقه‌بندی/حاشیه فقط *افزوده* شده؛
هیچ کاراکتری از base تغییر نکرده (تطبیق با S05).

**سنسوس طبقه‌بندی (واقعی، 45٬844 صفحه):**

| کلاس | شمار | مبنایی |
|---|---|---|
| CONTENT_PAGE | 33٬443 | definitive |
| SECTION_HEADING | 10٬739 | guessed |
| SHORT_CONTENT | 1٬589 | guessed |
| UNKNOWN_STRUCTURE | 38 | definitive |
| EMPTY_PAGE | 35 | definitive |
| CHAPTER_HEADING | 0 | — |

- مبنا: definitive **33٬516** / guessed **12٬328** (جمع 45٬844 ✓).
- **یافته:** هیچ عنوان سوره‌ی «خالص» (`سوره بقره`-مانند) در متن کوتاه‌های پیکره
  وجود ندارد (ممیزی واژگان: ۲۷۴ رکورد حاوی «سور» — همه در عناوین فرعی مثل
  «نام ها و اوصاف سوره»/«هدف سوره»/«تناسب سوره» که به‌درستی SECTION شدند).
  پس CHAPTER_HEADING=0 یک **یافته‌ی داده** است، نه باگ؛ قاعده در تست‌های fixture
  فعال و سبز است.
- Context records: 10٬728 از 10٬739 عنوان (بافت = 11 عنوان در انتهای جلد،
  بدون صفحه‌ی بعدِ هم‌جلد → بومی، نه حذف)؛ هر ۱۰٬728 دارای summary
  (`context_with_summary=10728`).

**Ledger gap در مانیفست v0002:** `status="unresolved"`, count=45٬243،
`missing_runs=[[3649,11182],[11205,39003],[44957,49956],[55699,55701],[55715,59590],[89280,90310]]`،
دلیل: «no trusted source available offline … recovery requires a live re-crawl on s52».

**SHA پروب‌های خواندنی:** v0001-probe `cf90547a6bf4d6e5bcba2347077cda4548dc71a07b2f6ba0f24eed5923df0510`،
vocab-probe `e9009992ead785a4f4a57c9beb894648ff421186a307fc683902c1f249847c81`،
classify-probe `7b14431c9faf00f56daa72767b7aa05075e9bfd8060315e0c7af48bdc0b4e592`.
جمع شواهد: [`.tmp_pcm205_gate1_evidence.json`](.tmp_pcm205_gate1_evidence.json).

**عدم تغییر pcm20_4 (SHAهای مانیفست قبل/بعد از مرحله — یکسان):**
v0001 `e0b0c2ce…`، v0002 `14232e17…`، v0003 `dbf35948…`.

## ۸. git status / بکاپ / rollback

- **هیچ commitی انجام نشد** (طبق قاعده و تصمیم کاربر).
- ۶۴ فایل staged `.tmp_pcm204_*` دست‌نخورده ماندند.
- بکاپ لازم نبود: فقط **ساخت** در دو ریشه‌ی جدید (`pcm20_5`, `pcm20_5_crossroot`)؛
  rollback = حذف این دو دایرکتوری. `pcm20_4` و production هرگز نویز نشدند.

## ۹. موارد باقی‌مانده / خط‌کشی‌ها

1. ۴۵٬۲۴۳ عددِ گم‌شده‌ی `item_index` باقی‌مانده‌ی **unresolved** — نیازمند
   re-crawl زنده روی s52 (GATE 2). تا آن زمان ترتیب درونِ گپ‌ها بر پایه‌ی
   `source_position` است و ledger آن را ثبت می‌کند.
2. `SEMANTIC_SCHEMA_VERSION=cs-20.5` — اگر قواعد (واژگان/آستانه‌ها) تغییر کند،
   نسخه‌ی قواعد بزرگ و نسخه‌ی جدید پیکره می‌سازد؛ v0002 ثابت می‌ماند.
3. خلاصه‌سازی هنوز **verbatim/بدون LLM** است؛ اگر در گپ‌های بعدی خواسته شد
   خلاصه‌ی LLM زبانی‌شده، باید `model`/`prompt_version` پر و نسخه‌ی جدید ساخته شود
   (قاعده‌ی ۸: بدون fabrication).
4. مستندسازی قرارداد معنایی در `docs/` و reconcile OpenAPI — در **گزارش نهایی**
   (پس از GATE 4) یکجا انجام می‌شود.
5. GATE 2–4 همچنان **BLOCKED** (s52 / Neo4j محلی).

## ۱۰. روش تست دستی (تکرارپذیر)

```bash
# از ریشه‌ی ریپازیتوری، با پیکره‌ی واقعی PCM-20.4 (فقط خواندن):
python -X utf8 -m corpus.tasnim.cli build-corpus \
  --jsonl data/tasnim/pcm20_4/source-snapshot/tasnim-corpus.jsonl \
  --json  data/tasnim/pcm20_4/source-snapshot/tasnim-corpus.json \
  --summary data/tasnim/pcm20_4/source-snapshot/export-summary.json \
  --data-root data/tasnim/pcm20_5
# انتظار: v0001، 45844 صفحه، content sha ee87686a…، validate PASS

python -X utf8 -m corpus.tasnim.cli build-semantic \
  --data-root data/tasnim/pcm20_5 --base v0001
# انتظار: v0002، 10728 context، census §7، content sha 12a93e21…، validate PASS

python -X utf8 -m corpus.tasnim.cli validate-corpus \
  --data-root data/tasnim/pcm20_5 --build v0002        # انتظار: PASS
python -X utf8 -m corpus.tasnim.cli semantic-diff \
  --data-root data/tasnim/pcm20_5 --from v0001 --to v0002
# انتظار: unchanged=45844, context_records_added=10728, unresolved_gaps=45243
python -X utf8 -m corpus.tasnim.cli build-semantic \
  --data-root data/tasnim/pcm20_5 --base v0001
# انتظار: "REUSED v0002 — semantic content identical (same base + rules). No new version."
python -X utf8 -m unittest test_corpus_tasnim test_corpus_semantic -v   # انتظار: 27 OK
```

## ۱۱. نتیجه‌ی نهایی

**GATE 1: PASS.** پیکره‌ی معنایی v0002 در `data/tasnim/pcm20_5/corpus/builds/v0002`
با content SHA `12a93e21…` ساخته و اثبات شد که: (الف) بر پایه‌ی v0001ِ بایته‌به‌بایت
PCM-20.4 است؛ (ب) هیچ محتوایی تغییر/حذف/افزوده‌ی بی‌مجاز نکرده
(semantic-diff: unchanged 45844/45844، S05)؛ (ج) deterministic و idempotent است
(REUSED + cross-root SHA یکسان)؛ (د) قابل بازتأیید کامل است (V01–V08 + S01–S07)؛
(هـ) gapها با ledger صادقانه `unresolved` ثبت‌اند. پیش‌شرط GATE 2
(دیتاست ۱۰٪ از v0002 + embedding واقعی) از نظر داده **آماده** است؛ اجرای آن
فقط منتظر s52 (LiteLLM `172.20.1.52:4000`) می‌ماند.

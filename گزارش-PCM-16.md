# گزارش PCM-16 — پیکره‌ساز از Dumpهای معتبر (Corpus Builder، قرارداد c-1)

تاریخ: ۱۴۰۵/۰۸/۰۷ (2026-10-29) · شاخه: `main` · commit پایه: `aa174c7` (PCM-15 report)

---

## A. خلاصه اجرایی

مأموریت «PCM-16 — پیکره‌ساز (Corpus Builder)» به‌طور کامل انجام شد: ماژول
مستقل `backend/factory/corpus.py` (قرارداد `c-1`) فقط از **Dumpهای معتبر
`d-1`** (اعتبارسنجی کامل V1..V11 پیش از هر نوشتن) پیکره می‌سازد — دو جریان
جدا **RAW** (دست‌نخورده بایتی) و **NORMALIZED** (مطابق سیاست ثبت‌شده)،
dedup با ردیابی کامل رخدادها، provenance خط‌به‌خط، خروجی نسخه‌دار
JSONL + ZIP قطعی + بسته HuggingFace **فقط محلی**، idempotent و قطعی، بدون
DB/Elasticsearch/شبکه/LLM.

نتیجه‌ها:

1. **ماژول جدید `factory/corpus.py`** (481 خط) — `build_corpus(dump_dirs,
   out_dir, require_quality=None)` + قرارداد `c-1` + خروجی
   `corpus-manifest.json` با policy/counts/integrity کامل.
2. **اعتبارسنجی fail-fast:** اگر هر Dump از میان چند Dump نامعتبر باشد،
   کل build رد می‌شود (`CorpusError`) و هیچ فایلی نوشته **نمی‌شود**
   (حتی دایرکتوری خروجی ساخته نمی‌شود — تست C-03c).
3. **جریان‌های جدا:** `raw.jsonl` فقط `raw_text` دارد و
   `normalized.jsonl` فقط `normalized_text` + `norm_version` +
   `content_hash` — هیچ‌کدام فیلد دیگری را تحمل نمی‌کند (تست C-06).
4. **dedup با صداقت:** کلید raw = `sha256:+sha256(raw_text)[:16]`، کلید
   normalized = `content_hash` (همان قرارداد WF)؛ خط‌های یکتا
   `occurrence_count` و فهرست کامل رخدادها را دارند — هیچ provenance‌ای
   حذف نمی‌شود (تست C-07).
5. **قطعی و idempotent:** ترتیب ورودی‌ها بر `(input_sha256, file_id)`
   مرتب می‌شود؛ 4 فایل JSONL و ZIP در دو اجرای متوالی و در دو دایرکتوری
   مختلف **بایتی یکسان** (C-02/C-09/C-10)؛ ZIP با timestamp ثابت
   1980-01-01 و ترتیب ثابت اعضا.
6. **آمار واقعی:** همه شمارنده‌های manifest از دادهٔ واقعی بازمحاسبه
   می‌شوند و تست C-12 آن‌ها را مستقل از فایل‌های نوشته‌شده بازبینی
   می‌کند — عدد ساختگی وجود ندارد.
7. **بسته HF فقط محلی:** `hf-package/` با README (فرانت‌ماتر YAML:
   `language: fa`، آمار واقعی، عبارت صریح «فقط محلی — انتشار خودکار
   نیست») + کپی بایتی 4 JSONL + کپی بایتی manifest. انتشار عمومی فقط
   با تأیید صریح مالک.
8. **24 تست جدید** (C-01..C-16 در `backend/test_corpus_builder.py`،
   626 خط) + زیردستور CLI `build-corpus` + رگرسیون کامل **175/175 سبز**.
9. سند طراحی: `docs/PCM-16-CORPUS-BUILDER.md` (199 خط) + به‌روزرسانی
   `readme.md`/`AGENTS.md`.
10. **بدون deploy:** چک خواندنی s52 اجرا شد و production را
    دست‌نخورده/سالم تأیید کرد (بخش H و I).

## B. وضعیت قبل از تغییر و ممیزی

- git: clean روی `aa174c7` (= `origin/main`، commit گزارش PCM-15)؛
  رگرسیون 151 تست سبز.
- ممیزی موجود:
  - `corpus/` در ریشهٔ ریپازیتوری متعلق به **زیرپروژهٔ قدیمی
    thesaurus** است (build_corpus.py / build_dataset.py /
    upload_to_hf.py / pipeline.py / scrape_khamenei.py) — خارج از محدوده
    و دست‌نخورده باقی ماند.
  - قرارداد Dump `d-1` (PCM-14C.3) کامل و پایدار است: 6 فایل
    کانونیکال، `validate_dump` (V1..V11)، `dump_summary` — ورودی ایده‌آل
    برای پیکره‌ساز.
  - هیچ سازنده‌ی پیکره‌ای از روی Dump وجود نداشت؛ خروجی‌های WF/Dump فقط
    قابل مصرف توسط API/Studio بودند.
  - `factory/cli.py` سه زیردستور dump داشت (`make-dump` /
    `validate-dump` / `dump-summary`)؛ جای `build-corpus` خالی بود.
- نتیجه ممیزی: پیکره‌ساز باید **مستقل** (بدون DB/Flask/شبکه — هم‌سایهٔ
  بقیهٔ factory) و **فقط-خوانده** روی Dumpها باشد؛ هیچ تغییر schema یا
  API در server لازم نیست → این فاز **بدون مهاجرت** است.
- **نکته مهم (ممیزی s52):** اجرای
  `deploy/pcm16_s52_readonly_check.sh` وضعیت s52 را **pre-PCM-14D**
  تأیید کرد (endpoint `/api/knowledge/works` → 404، جدول
  `knowledge_works` غایب، `backend/factory/dump.py` MISSING — یعنی حتی
  PCM-14C.3 هم روی s52 نیست؛ `cli.py` روی s52 فقط 106 خط) — مطابق
  گزارش‌های PCM-14D و PCM-15.

## C. طراحی (خلاصه — کامل در `docs/PCM-16-CORPUS-BUILDER.md`)

```
دایرکتوری خروجی c-1:
  corpus-manifest.json     (قرارداد c-1: policy/files/counts/integrity)
  raw.jsonl                (جریان RAW — فقط raw_text)
  normalized.jsonl         (جریان NORMALIZED — normalized_text + norm_version + content_hash)
  raw.unique.jsonl         (dedup RAW + occurrence_count + occurrences)
  normalized.unique.jsonl  (dedup NORMALIZED + occurrence_count + occurrences)
  corpus-data.zip          (ZIP قطعی از 4 JSONL؛ manifest داخل archive نیست)
  hf-package/              (README.md + کپی بایتی 4 JSONL + کپی بایتی manifest)
```

- **fail-fast:** مرحلهٔ ۱ = اعتبارسنجی **تمام** Dumpها (`validate_dump`
  V1..V11) + درِ اختیاری کیفیت (`require_quality="ok"`). هر خطا →
  `CorpusError` پیش از اولین نوشتن.
- **ترتیب قطعی:** Dumpها بر `(input_sha256, factory_file_id)` مرتب؛
  بلوک‌ها بر `block_index` → خروجی به ترتیب لیست ورودی وابسته **نیست**.
- **record:** `record_id = "cb1:{input_sha256[:12]}:{block_id}"` +
  `provenance{input_sha256, input_filename, factory_file_id,
  work/edition/volume_id, dump_dir, dump_contract, dump_blocks_sha256,
  dump_manifest_sha256, versions}` + `document{title, author, ...}`.
- **dedup:** first-occurrence در ترتیب قطعی؛ کلیدها و رخدادها در
  manifest ثبت می‌شوند (استراتژی در `policy.dedup_strategy`).
- **manifest c-1:** `corpus_contract_version:"c-1"` + `policy`
  (streams/dedup/deterministic_order + `db:"none"`/`elasticsearch:"none"`/
  `network:"none"`/`llm:"none"`) + `files[]` (hash/size/line_count هر
  فایل) + `archive` (sha256 archive — خود manifest در archive نیست، پس
  self-consistent است) + `input_dumps[]` + `counts` + `integrity` +
  `hf_package`. کپی manifest در ریشه و در `hf-package` **بایتی یکسان**
  (نویسندگی دوتایی از همان dict با همان serializer).
- **ZIP قطعی:** `ZipInfo(date_time=(1980,1,1,0,0,0))`،
  `external_attr=0o644<<16`، deflate-9، اعضا به ترتیب ثابت
  `CORPUS_DATA_FILES`.
- **rollback:** بدون schema/بدون endpoint/بدون deploy — حذف ماژول =
  rollback کامل؛ کد قدیمی دست‌نخورده است.

## D. تغییرات کد و فایل

**جدید:**

| فایل | توضیح |
|-------|-------|
| `backend/factory/corpus.py` (481 خط) | قرارداد c-1: `build_corpus` + اعتبارسنجی fail-fast + دو جریان + dedup + ZIP قطعی + manifest + بسته HF محلی |
| `backend/test_corpus_builder.py` (626 خط) | 24 تست C-01..C-16 (ایزوله؛ بدون `pct_test_support` — fixtures docx + WF + Dump واقعی) |
| `docs/PCM-16-CORPUS-BUILDER.md` (199 خط) | سند طراحی: قرارداد c-1، determinism، idempotency، آمار واقعی، HF محلی، quality gate، CLI، سازگاری m-1، ماتریس C، محدودیت‌ها |
| `deploy/pcm16_s52_readonly_check.sh` (95 خط) | چک خواندنی s52 (بدون deploy/نوشتن) — اجرا شده (بخش H) |

**تغییرکرده (کد):**

| فایل | تغییر |
|-------|-------|
| `backend/factory/cli.py` (+41/−10) | زیردستور `build-corpus` (dumps... + `--out` + `--require-quality ok` + `--json`) + dispatch + `except (DumpError, CorpusError)` + docstring |
| `backend/factory/__init__.py` (+2) | export `CORPUS_VERSION`, `CorpusError`, `build_corpus` در `__all__` |

**تغییرکرده (مستندات):** `readme.md` (ردیف قابلیت پیکره‌ساز c-1،
9 test files/175 تست، دستور رگرسیون 175، نقشه‌ی راه)، `AGENTS.md`
(دستور رگرسیون 175، `test_corpus_builder.py` (24، C-01..C-16)،
نقشه‌ی راه).

**وابستگی جدید: صفر.** (فقط کتابخانه‌های استاندارد `hashlib`/`os`/`json`/
`zipfile`/`datetime`)

## E. نتایج تست

| مجموعه | تعداد | نتیجه |
|---------|:-----:|:------:|
| هسته (api/projects/dashboard) | 39 | ✅ |
| knowledge_api (KB-01..KB-14) | 40 | ✅ |
| word_factory (WF-01..WF-13 + on_stage) | 27 | ✅ |
| dump (D01..D15) | 26 | ✅ |
| work_registry (RD-01..RD-07) | 10 | ✅ |
| queue (Q-01..Q-08) | 9 | ✅ |
| **corpus_builder (C-01..C-16)** | **24** | ✅ |
| **کل** | **175** | ✅ سبز (76.250s) |

پوشش C (همه E2E با pipeline واقعی Word Factory + `generate_dump` روی
fixtures docx):

- **C-01** — یک Dump معتبر → همه خروجی‌ها؛ hash/size/line_count
  manifest بازمحاسبه می‌شود و درست است.
- **C-02** — `[A,B]` و `[B,A]` → داده‌های **بایتی یکسان** (4 JSONL +
  ZIP)؛ `input_dumps` مرتب؛ داخل هر فایل، بلوک‌ها به ترتیب `block_index`.
- **C-03** — (a) `blocks.jsonl` دستکاری‌شده (tamper بازنویسی‌پذیر) →
  `CorpusError`؛ (b) `quality-report.json` حذف‌شده → `CorpusError`؛
  (c) یک Dump نامعتبر در میان چند Dump سالم → **کل build** رد؛ در هر
  سه حالت `out_dir` اصلاً ساخته نمی‌شود.
- **C-04** — دایرکتوری Dump وجود ندارد → `CorpusError`؛ مقدار نامعتبر
  `require_quality` → `CorpusError`.
- **C-05** — `require_quality="ok"`: Dump ضعیف (متن فارسی < 50 کاراکتر
  → hard gate `non_empty_text` → `manual_review`) **رد** می‌شود؛ بدون
  در، همان Dump پذیرفته و در `dumps_by_quality` ثبت می‌شود.
- **C-06** — جریان‌ها جدا: خط `raw.jsonl` فاقد `normalized_text` و خط
  `normalized.jsonl` فاقد `raw_text` است؛ `raw_text` **بایتی** با متن
  Dump برابر است؛ `raw_hash` بازمحاسبه می‌شود.
- **C-07** — پاراگراف مشترک در 3 کتاب → `occurrence_count=3` + فهرست
  رخدادها؛ dedup normalized با `content_hash` (ارقام نگه‌داشته‌شده
  ۱۴۰۵/1405 را جدا نگه می‌دارد — مطابق سیاست WF).
- **C-08** — provenance هر خط کامل است و مقادیر آن (input_sha256،
  factory_file_id، work/edition/volume، hashهای Dump) با مانیفست Dump
  واقعی یکی‌یکی برابر است.
- **C-09** — build دوباره روی همان `out_dir` → همه فایل‌ها **بایتی
  یکسان**، فهرست فایل‌ها بدون اضافه/کم.
- **C-10** — build در دو دایرکتوری مستقل → داده‌ها بایتی یکسان؛
  manifest‌ها برابر (به‌جز `generated_at`).
- **C-11** — ZIP = 4 JSONL به ترتیب قطعی؛ استخراج = بایت فایل‌ها؛
  بایت‌بایت قطعی بین دو build.
- **C-12** — **همه** آمارهای `counts` با بازمحاسبهٔ مستقل از فایل‌های
  نوشته‌شده راستی‌آزمایی می‌شوند (dumps/blocks/unique/duplicates/chars/
  by_type/dumps_by_quality).
- **C-13** — بسته HF: 4 کپی JSONL بایتی یکسان با ریشه؛ کپی manifest
  بایتی یکسان با manifest ریشه؛ README فرانت‌ماتر (`language: fa`،
  `license`) + آمار واقعی + عبارت «فقط محلی» دارد؛ hashهای
  `hf_package` درست محاسبه می‌شوند.
- **C-14** — CLI `python -m factory.cli build-corpus ... --json` →
  exit 0 + manifest خوانا؛ روی Dump خراب → exit 1 + خطا در stderr +
  خروجی نوشته نمی‌شود؛ زیردستور legacy `validate-dump` بدون تغییر
  عمل می‌کند.
- **C-15** — AST guard: `corpus.py` هیچ import از ماژول‌های production
  (server/flask/knowledge_api/...) یا شبکه (urllib/requests/socket/...)
  ندارد؛ build هیچ فایل `.db` نمی‌سازد.
- **C-16** — سازگاری m-1: Dump با `normalizer_policy: null` (مانیفست
  m-1 شبیه‌سازی‌شده) با warning «re-normalization check skipped»
  پذیرفته می‌شود و `versions.normalizer_policy: null` ثبت می‌شود.

اجرا (برای این گزارش دوباره اجرا شد — 2026-10-29):

```bash
cd backend
python -m unittest test_corpus_builder -v
  # Ran 24 tests in 8.405s — OK
python -m unittest test_api test_projects test_dashboard \
  test_knowledge_api test_word_factory test_dump test_work_registry \
  test_queue test_corpus_builder -v
  # Ran 175 tests in 76.250s — OK
```

در مسیر توسعه، 2 کاستی در خود **کد** پیدا و **اصلاح** شد (نه از بین
بردن assertion): (1) کپی manifest در `hf-package` پیش از افزودن کلید
`hf_package` نوشته می‌شد → ریشه و HF تفاوت می‌افتادند؛ چیدمان مرحلهٔ ۴
جدا شد (کپی داده‌ها → README → افزودن `hf_package` → نوشتن **دو**
manifest بایتی یکسان). (2) ساخت ZIP از `open().read()` خام استفاده می‌کرد
→ helper `_read_bytes` (with-block) جایگزین شد. به‌علاوه دو
ResourceWarning بستن فایل در تست‌ها با `with` برطرف شد.

## F. سازگاری (compat) — جدول خلاصه

| مورد | وضعیت |
|------|--------|
| endpointهای server (همه) | بدون تغییر (هیچ route جدیدی؛ تست‌های api/dashboard سبز) |
| قرارداد Dump `d-1` | **کاملا دست‌نخورده** (D01..D15 سبز)؛ پیکره‌ساز فقط مصرف‌کنندهٔ خواندنی است |
| سازگاری m-1 (سیاست ثبت‌نشده) | پذیرفته با warning + ثبت `null` (C-16) — مطابق قرارداد D11 |
| زیردستورات legacy CLI (`validate-dump` و...) | بدون تغییر (C-14c) |
| Word Factory (pipeline، خروجی‌ها) | دست‌نخورده (WF-01..WF-13 سبز) |
| صف PCM-15 / Registry PCM-14D | دست‌نخورده (Q/RD سبز) |
| اکستنشن (`/api/projects*`) | دست‌نخورده (probe 200 روی s52) |
| DB / ES / شبکه | پیکره‌ساز هیچ‌کدام را لمس نمی‌کند (C-15 AST guard + policy `none`) |
| `corpus/` قدیمی (thesaurus) | دست‌نخورده — خارج از محدوده |

## G. Git: commit و push

- **commit کد:** `cd3d377596aec7eb75e1b9fff2b61a0f3cbd6755` (8 فایل،
  1456+ / 10−) — بعد از `aa174c7`، push بدون force.
- **GitHub:** `https://github.com/saber13812002/persian-corpus-toolkit` —
  SHA commit کد با `git ls-remote` تأیید می‌شود (بخش H).
- این گزارش (با ثبت SHA نهایی) در **commit دوم بلافاصله بعدی** ثبت
  می‌شود — همان رویه‌ی PCM-14C.3 / PCM-14D / PCM-15.
- قبل از commit: `git diff --check` → بدون whitespace error (فقط
  هشدارهای CRLF→LF پیشین)؛ secret scan روی 8 فایل → **0 hit**؛
  `git status` → دقیقاً 8 فایل PCM-16، بدون فایل اضافی.

## H. وضعیت Local / GitHub / s52

| محیط | وضعیت |
|------|-------|
| Local | `main` = `cd3d377` (commit کد PCM-16)؛ working tree clean (بعد از commit گزارش) |
| GitHub | همگام با Local (`origin/main` = `cd3d377`؛ تأیید با `git ls-remote`) |
| s52 | **pre-PCM-14D** — دست‌نخورده (هم 14D، هم 15، هم 16 روی s52 نیستند) |

نتیجهٔ چک خواندنی s52 (اجرا شد 2026-10-29،
`ssh -p 22 saber@172.20.1.52 'bash -s' < deploy/pcm16_s52_readonly_check.sh`):

- container `persian-corpus-toolkit-backend-1` — **Up 2 days**
  (image `sha256:147e985ddade2ed6f2078383720189852e66e697dec58516dbdd1bfed290f9ec`)؛
  بدون restart.
- probes: `/api/stats` 200، `/api/projects` 200 (کراول زنده دست‌نخورده)،
  `/api/knowledge/collections` 401، `/api/knowledge/works` **404**
  (pre-14D)، `/api/knowledge/queue/summary` 404 (pre-15)،
  `/api/dashboard/projects` 401، `/dashboard/studio.html` 200،
  `/api/auth/status` → `{"auth_enabled":true,"authenticated":false}`.
- کد s52: `backend/factory/corpus.py` **غایب**، marker `build-corpus`
  در `factory/cli.py` غایب، `knowledge_file_queue` غایب (pre-15)،
  `knowledge_works` غایب (pre-14D)؛ `knowledge_api.py` = 1781 خط،
  `factory/cli.py` = 106 خط، `factory/dump.py` **MISSING** (روی s52 حتی
  PCM-14C.3 نیست — مطابق گزارش PCM-14C.3 که deploy نداشت).
- DB production: `PRAGMA integrity_check` = **ok**؛ projects=6،
  auth_sessions=17، knowledge_collections=0،
  knowledge_collection_documents=0؛ جدول `knowledge_works` و
  `knowledge_file_queue` هر دو غایب (مطابق pre-14D).
- `.env` perms = 600 (محتوا هرگز چاپ نشده).

## I. تأیید عدم اختلال در production

- هیچ deploy، restart یا نوشتن روی s52 انجام **نشده** است (چک کاملاً
  read-only — خود اسکریپت در انتها این را اعلام می‌کند).
- کراول زنده (`/api/projects*`) دست‌نخورده — 200 در چک بالا.
- PCM-16 ماهیتاً **بدون مهاجرت** است (هیچ schema/endpoint جدید)؛ حتی
  هنگام deploy آینده، خطری برای endpointهای نوشتاری اکستنشن ندارد.
- deploy آینده (فقط با دستور صریح + بکاپ): بکاپ `thesaurus.db` +
  integrity_check → اسنپ‌شات deploy dir → کپی کد →
  `docker compose build backend && docker compose up -d backend` →
  health-wait + smoke. **توجه:** چون s52 هنوز pre-14D است، deploy بعدی
  عملاً 14C.3 + 14D + 15 + 16 را یکجا می‌رساند — همهٔ مهاجرت‌ها
  افزایشی و idempotent هستند و باید جداگانه smoke test شوند.

## J. محدودیت‌ها و ریسک‌ها

1. **هنوز deploy نشده** — مطابق قاعدهٔ مأموریت (بدون دستور صریح +
   بکاپ، deploy نمی‌شود).
2. **dedup فقط متن دقیق** (exact-text) است — dedup مبهم/فازی (fuzzy)
   عمداً در این فاز پیاده **نمی‌شود** (ریسک حذف متن واقعی).
3. **بسته HF فقط محلی** است — انتشار عمومی در هاجینگ‌فیس فقط با تأیید
   صریح مالک و به‌صورت دستی (در README و manifest ثبت شده).
4. `dump_dir` در provenance مسیر **محلی** همان ماشین ساخت پیکره است —
   برای تکرارپذیری بین ماشین‌ها، شناسه‌های hash (input_sha256/
   blocks_sha256/manifest_sha256) منبع اعتماد‌پذیر هستند، نه مسیر.
5. `generated_at` تنها فیلد ناپایدار در manifest است (باقیِ خروجی
   بایتی قطعی) — برای مقایسهٔ بایتهای manifest بین دو build، این فیلد
   باید کنار گذاشته شود (C-10 همین کار را می‌کند).
6. پیکره‌ساز Dumpها را **فقط می‌خواند**؛ هیچ‌گاه تغییرش نمی‌دهد؛ اگر
   Dump در دایرکتوری‌ای باشد که دسترسی نوشتن ندارد، باز هم کار می‌کند.
7. UI پیکره‌ساز (تصویرسازی آمار/پیکره در استودیو) جزو PCM-17 است.

## K. روش تست دستی (اپراتور)

```bash
cd backend
# 1) رگرسیون کامل (175 تست)
python -m unittest test_api test_projects test_dashboard \
  test_knowledge_api test_word_factory test_dump test_work_registry \
  test_queue test_corpus_builder -v
# 2) فقط پیکره‌ساز (24 تست)
python -m unittest test_corpus_builder -v

# 3) آزمایش دستی با CLI (بدون server/DB):
#    a) دو کتاب docx ساخت و از WF/Dump عبور داد:
python -m factory.cli make-dump <wf_dir> -o dump-a
#    b) پیکره ساخت:
python -m factory.cli build-corpus dump-a dump-b --out corpus-out --json
#       → exit 0 + خلاصهٔ counts + corpus-manifest.json
#    c) درِ کیفیت:
python -m factory.cli build-corpus dump-a dump-b --out corpus-out \
  --require-quality ok
#       → Dumpهای manual_review رد می‌شوند (خطای واضح)
#    d) بررسی: 4 JSONL + zip + hf-package/ ساخته شده؛ hashهای manifest
#       با `sha256sum` (یا Python hashlib) قابل راستی‌آزمایی‌اند؛
#       build دوباره روی همان out_dir → خروجی بایتی یکسان.
```

## L. فاز بعد

- **PCM-17** — تکمیل UI استودیو: نمایش واقعی Dumpها/پیکره‌ها و
  آمارهای موجود (evidence-based، فقط REST، بدون دادهٔ ساختگی) +
  تصویرسازی صف PCM-15 و پیکره‌های c-1 در داشبورد.

---

*این گزارش بخشی از مأموریت «ادامه PCM-14C تا تحویل پیکره» است؛ مستندات
فنی کامل در `docs/PCM-16-CORPUS-BUILDER.md`.*

# گزارش PCM-14C.3 — قرارداد رسمی Export و آماده‌سازی Dump (d-1)

تاریخ: ۱۴۰۵/۰۸/۰۷ (2026-10-29) · شاخه: `main` · commit کد: `e367bc7`

---

## A. خلاصه اجرایی

مأموریت «تثبیت قرارداد رسمی Export و آماده‌سازی Dump در Persian Corpus Toolkit»
به‌طور کامل انجام شد. خروجی اصلی: **قرارداد Dump `d-1`** — یک قرارداد رسمی،
نسخه‌پذیر، قابل‌تست و **مستقل از Elasticsearch** برای بسته‌بندی و انتقال خروجی
Word Factory.

نتیجه‌ها:

1. ماژول `backend/factory/dump.py` — `generate_dump` / `validate_dump` (V1–V11) /
   `dump_summary` — بدون DB، بدون ES، بدون شبکه.
2. مانیفست WF ارتقا به **`m-2`**: ثبت کامل `normalizer_policy` + `factory` +
   `blocks_hash` (سازگاری معکوس با `m-1` حفظ شده).
3. CLI با سه زیردستور جدید: `make-dump` / `validate-dump` / `dump-summary`
   (مسیر legacy بدون تغییر؛ کدهای خروجی 0/1/2/3).
4. **26 تست جدید** (D01–D15) + رگرسیون کامل **129/129 سبز**.
5. سند قرارداد کامل: `docs/PCM-14C.3-DUMP-CONTRACT.md` (۱۱ بخش).
6. شواهد تکرارپذیری روی **۳ کتاب واقعی** (فقط‌خوانده) — همگی پایدار.
7. commit `e367bc7` روی `origin/main` push شد (بدون force).
8. s52 فقط **چک خواندنی** شد؛ **هیچ deploy و تغییر** انجام نشد (طبق مأموریت).

## B. وضعیت قبل از تغییر و ممیزی

- git: clean (بعد از commit `708d689`)؛ 103 تست سبز.
- خط لوله Word Factory (V0.1) موجود بود؛ ولی:
  - مانیفست `m-1` سیاست کامل نرمال‌سازی را **ثبت نمی‌کرد** (فقط `n-1`) — یعنی
    بازسازی دقیق نرمال‌سازی یک اجرای قدیمی بدون دسترسی به کد ممکن نبود.
  - هیچ قرارداد رسمی Export/بسته‌بندی وجود نداشت؛ 5 فایل خروجی WF بدون
    بسته خوداعتبارسنج قابل انتقال نبودند (دریافت‌کننده نمی‌توانست بدون دسترسی
    به دایرکتوری WF، صحت و تکمیلی را اثبات کند).
  - سازگاری ES: **هیچ mapping واقعی وجود ندارد** (`compatibility` = NOT
    VERIFIED در V0.1) — بنابراین این مأموریت هیچ ادعای ES-compat انجام نداد.
- ساختار کد: `backend/factory/{intake,validator,parser,structure,metadata,
  normalize,quality,export,service,cli}.py` — همه ایزوله (بدون DB/Flask/LLM).

## C. قرارداد Dump نهایی (d-1)

**تعریف:** Dump یک دایرکتوری است: `dump-manifest.json` + **رونویسی بایتی** 5
فایل WF (`manifest.json`, `document.json`, `blocks.jsonl`, `quality-report.json`,
`report.md`). ساخت Dump یک تابع خالص **read-only** از دایرکتوری خروجی WF است.

- **شناسه‌ها (provable):** `file_id` (`f-<sha8>`)، `work_id`، `edition_id` —
  همه از SHA-256 ورودی مشتق می‌شوند و بین اجراها ثابت‌اند.
- **integrity:** SHA-256 فایل ورودی + SHA-256 هر 5 فایل خروجی + `blocks_hash`
  (hash کانونیکال کل بلوک‌ها) در dump-manifest ثبت می‌شود.
- **اعتبارسنجی V1–V11 بدون ES/DB/شبکه:** وجود فایل‌ها، فیلدهای اجباری، rehash
  همه‌ی hashهای ثبت‌شده، ترتیب قطعی بلوک‌ها، یکتایی `block_id`، سازگاری
  RAW/NORMALIZED با سیاست ثبت‌شده، وضعیت کیفیت، سازگاری نسخه‌ها.
  → هر تغییر (tamper) یا ناکامی فایل، Dump را **INVALID** می‌کند (کد خروجی 1).
- **RAW + NORMALIZED:** `raw_text` دست‌نخورده و کنار `normalized_text` ثبت
  می‌شود؛ هر دو در `blocks.jsonl` هستند.
- **سیاست نرمال‌سازی ثبت‌شده:** کل policy نسخه‌شده `n-1` (7 پارامتر + فهرست
  ruleهای فعال) در مانیفست WF (`m-2`) و به‌دنبال آن در dump-manifest ثبت
  می‌شود.
- **ترتیب قطعی:** بلوک‌ها مطابق ترتیب واقعی body؛ `block_id = b<index:05d>:<type>`.
- **قواعد نسخه‌بندی:** تغییر policy نرمال‌سازی → نسخه جدید `n-N`؛ تغییر خود
  قرارداد Dump → نسخه جدید `d-N` (هر دو فقط افزایشی؛ بدون بازنویسی داده).
- **سازگاری:** Dump با مانیفست‌های WF `m-1` و `m-2` کار می‌کند؛ روی `m-1`
  سیاست ثبت‌شده `null` است و یک warning صادر می‌شود (قاعده V6 skip).
- **مصرف‌کننده‌های آینده (ES/RAG/HF):** فقط طراحی در بخش 8 سند قرارداد — مصرف‌
  کننده باید روی **Dump اعتبارسنجی‌شده** build کند؛ هیچ endpoint ساختگی اضافه
  نشده است.

سند کامل: [`docs/PCM-14C.3-DUMP-CONTRACT.md`](docs/PCM-14C.3-DUMP-CONTRACT.md)

## D. تغییرات کد و فایل (13 فایل، +1645/−38)

**جدید:**

| فایل | توضیح |
|-------|-------|
| `backend/factory/dump.py` (459 خط) | `DUMP_VERSION="d-1"`، `generate_dump`، `validate_dump` (V1–V11)، `dump_summary`، `DumpError` |
| `backend/test_dump.py` | 26 تست D01–D15 (ایزوله؛ tempfile؛ AST guard) |
| `docs/PCM-14C.3-DUMP-CONTRACT.md` (360 خط) | سند قرارداد رسمی (۱۱ بخش) |

**تغییرکرده (کد):**

| فایل | تغییر |
|-------|-------|
| `backend/factory/models.py` | `FACTORY_VERSION` + `blocks_hash()` روی ProcessedDocument |
| `backend/factory/normalize.py` | `NormalizationPolicy.policy_dict()` (ثبت کامل policy) |
| `backend/factory/export.py` | مانیفست **m-2**: `versions.normalizer_policy` + `versions.factory` + `blocks_hash` |
| `backend/factory/service.py` | عبور factory version به مانیفست |
| `backend/factory/cli.py` | reconfigure خروجی UTF-8 (Windows cp1252)؛ dispatch زیردستورهای dump؛ legacy بدون تغییر |
| `backend/factory/__init__.py` | export APIهای dump |

**تغییرکرده (مستندات):**

- `docs/WORD-FACTORY-USER-GUIDE.md` — بخش Dump + رفع driftها (threshold پیش‌فرض
  0.6 نه 0.85؛ `file_id` = `f-<sha8>`؛ جدول policy واقعی بدون ruleهای
  خیالی `fullwidth`/`nbsp`؛ CLI واقعی (`--quiet/--no-arabic/--max-mb`)؛ 129 تست).
- `docs/PCM-12-DATA-CONTRACTS.md` — بخش 2.5: اشاره به قرارداد Dump (مصرف‌
  کننده‌های بعد باید از Dump معتبر build کنند).
- `readme.md` — ردیف قابلیت 7 (Word Factory + Dump d-1)، 129 تست، درخت ساختار،
  نقشه‌ی راه.
- `AGENTS.md` — بخش تست (129)، ساختار فنی (factory + dump.py)، نقشه‌ی راه.

**وابستگی جدید: صفر.**

## E. نتایج تست

| مجموعه | تعداد | نتیجه |
|---------|:-----:|:------:|
| هسته (api/projects/dashboard) | 39 | ✅ |
| knowledge_api (KB-01..KB-14) | 40 | ✅ |
| word_factory (WF-01..WF-13) | 24 | ✅ |
| **dump (D01..D15)** | **26** | ✅ |
| **کل** | **129** | ✅ سبز |

پوشش D01–D15: ساخت Dump؛ ساختار V1–V11؛ SHA-256 ورودی/خروجی + rehash +
mismatch؛ رد Dump تahrif‌شده/ناقص؛ تکرارپذیری (دو WF run + دو dump روی همان
run)؛ حفظ RAW + مطابقت NORMALIZED با سیاست ثبت‌شده (پیش‌فرض و `digits=persian`)؛
ترتیب بلوک‌ها + یکتایی block_id؛ حالت‌های نازل (سند خالی / WF ناقص / JSONL
خراب)؛ بازسازی offline فقط از خود Dump؛ idempotency؛ سازگاری m-1؛ ایزولاسیون
(AST guard + بدون ساخت فایل DB)؛ چرخه‌های تکراری در-process؛ تطابق نمونه JSON
سند با خروجی واقعی (D14)؛ CLI (ساخت/اعتبارسنجی/exit code/legacy).

اجرا:

```bash
cd backend
python -m unittest test_dump -v                       # 26/26
python -m unittest test_api test_projects test_dashboard \
  test_knowledge_api test_word_factory test_dump -v   # 129/129
```

تست‌ها ایزوله‌اند: دایرکتوری موقت، بدون import ماژول‌های production (AST guard)،
بدون ساخت فایل DB؛ ترتیب/ترکیب ماژول‌ها بر نتیجه اثر نمی‌گذارد.
فایل‌های واقعی کاربر (wf-out) در تست استفاده **نمی‌شوند**.

## F. ثبات نرمال‌سازی و شناسه‌ها — شواهد تکرارپذیری روی فایل واقعی

اجرا روی 3 کتاب DOCX واقعی در `wf-out` (فقط‌خوانده؛ بدون commit فایل کاربری) —
هر کتاب دو بار پردازش شد (دو دایرکتوری موقت مستقل) و برای هر دو اجرا
`generate_dump(..., source_docx=...)` + `validate_dump` انجام شد:

| کتاب | input sha256 (16) | file_id | بلوک‌ها | blocks_hash (16) |
|-------|-------------------|---------|:-------:|------------------|
| `namous.docx` | `de021889780e0124` | `f-4fe7c707` | 69 | `daefe16931a84b70` |
| `bank-ehterafat.docx` | `27fcf603ab8f95a3` | `f-c0167d25` | 941 | `3323e8d66a50fe5c` |
| `rahnamaye.docx` | `3d62d435a8c294ed` | `f-a471ea35` | 26 | `f6c6b448e3b96066` |

برای **هر سه** کتاب:

- `file_id` / `work_id` / `edition_id` / `blocks_hash` بین دو اجرا **دقیقاً یکسان**؛
- `blocks.jsonl` و `quality-report.json` **بایت‌به‌بایت یکسان**؛
- `manifest.json`، `document.json` و `dump-manifest.json` **ساختاریا یکسان**
  (فقط timestamps، مسیرها و hashهای پویای آنها تفاوت دارند)؛
- `validate_dump` برای هر دو Dump هر کتاب: **VALID** (0 error, 0 warning)؛
- policy ثبت‌شده: `n-1` با `nfkc=false, arabic_to_persian=true, zwnj=true,
  collapse_spaces=true, strip_zwsp=true, strip_rlm=true, digits=keep`؛
- quality هر سه: `status=done`, `score=1.0`, `quality_status=ok`.

**ریسک `block_id = b<index>:<type>` (ارزیابی شد، بدون تغییر مطابق مأموریت):**
شناسه بر اساس موقعیت است؛ به‌شرط ثابت ماندن ورودی، پایدار است. اگر در آینده
parser به‌گونه‌ای تغییر کند که تعداد/ترتیب بلوک‌ها عوض شود، `blocks_hash` عوض
می‌شود و نسخه parser باید تغییر کند (`p-N`) — در بخش 6 و 7 سند قرارداد
مستند شده است. **هیچ داده تاریخی بازنویسی نشد.**

## G. Git: commit و push

- **commit کد:** `e367bc756da6977c7aa7a544c79afa0ca27e6c68`
  (13 فایل، 1645+ / 38−)
- **push:** `origin main` — `708d689..e367bc7` (بدون force)
- **GitHub:** `https://github.com/saber13812002/persian-corpus-toolkit` — SHA
  همان `e367bc7` (تأیید با `git rev-parse origin/main`).
- این گزارش + اسکریپت چک s52 در commit دوم بلافاصله بعدی ثبت شده‌اند
  (`git log --oneline -2` برای مشاهده هر دو).

## H. وضعیت Local / GitHub / s52

| محیط | وضعیت |
|------|-------|
| Local | `main` = `e367bc7` + commit گزارش؛ working tree clean |
| GitHub | همگام با Local (`origin/main` = `e367bc7`؛ + commit گزارش) |
| s52 | **pre-PCM-14C.3** — `dump.py` روی s52 نیست (انتظار می‌رود؛ deploy نشده) |

## I. تأیید عدم اختلال در production

چک خواندنی s52 (`deploy/pcm14c3_s52_readonly_check.sh`) — هیچ چیزی روی s52
تغییر نکرد:

- کانتینر `persian-corpus-toolkit-backend-1`: **Up 39 hours** (restart نشده).
- پروب‌ها: `/api/stats` 200 · `/api/projects` 200 (اکستنشن باز) ·
  `/api/knowledge/collections` 401 · `/api/dashboard/projects` 401 ·
  `/dashboard/studio.html` 200 · `auth_enabled: true`.
- DB: `PRAGMA integrity_check` = **ok**؛ شمارنده‌ها: `project_pages=33142`،
  `projects=6`، `auth_sessions=17`.
- `.env`: موجود با perms **600** (محتوا چاپ نشد).
- schema/DB/کانتینر: **بدون هیچ تغییری**.

## J. محدودیت‌ها و ریسک‌ها

1. **بدون mapping ES واقعی** — هیچ ادعای ES-compat وجود ندارد (V0.1:
   `NOT VERIFIED`؛ مطابق دستور مأموریت).
2. `block_id` موقعیت‌محور است (بخش F؛ مستند، بدون تغییر).
3. بدون `--input` در `make-dump`، منبع SHA-256 ورودی، مانیفست WF است (منبع
   اطمینان = مانیفست؛ `sha256_source=manifest`)؛ با `--input` rehash واقعی
   انجام می‌شود (`rehashed`).
4. GitLab (پورت 2222 s52) هنگام چک از روی خود s52 جواب نداد (HTTP 000) —
   best-effort ثبت شد؛ مانعی برای این مأموریت نبود (مأموریت docs-only است).
5. محدودیت‌های V0.1 Word Factory (DOC قدیمی، صفحه‌شماری، OCR) بدون تغییر
   هستند (مستند در راهنمای کاربر).

## K. روش تست دستی (اپراتور)

```bash
cd backend
# 1) پردازش یک کتاب
python -m factory.cli "C:\path\to\book.docx" --out ../wf-out/run

# 2) ساخت Dump (file_id از خروجی مرحله 1)
python -m factory.cli make-dump "../wf-out/run/f-<sha8>" \
    --dump-dir "../wf-out/run-dump" --input "C:\path\to\book.docx"

# 3) اعتبارسنجی (کد خروجی 0 = VALID)
python -m factory.cli validate-dump "../wf-out/run-dump"

# 4) خلاصه
python -m factory.cli dump-summary "../wf-out/run-dump" --json

# 5) تست تخربه‌کاری (باید INVALID + کد خروجی 1 شود)
#    یک خط از blocks.jsonl داخل Dump را عوض کنید و دوباره validate کنید

# 6) تکرارپذیری: همان docx را دوبار پردازش کنید → file_id و blocks_hash
#    باید دقیقاً یکسان باشند
```

## L. پیشنهاد برای فاز بعد

- **PCM-14C.4 (پیشنهادی):** سازنده index ES / دیتاست HuggingFace که ورودی‌اش
  **Dump اعتبارسنجی‌شده** باشد — فقط بعد از اینکه mapping واقعی ES موجود و
  مستند شود (مطابق بخش 8 سند قرارداد).
- یا: اتوماسیون Dump برای کل کتابخانه `wf-out` (batch) + ثبت فهرست Dumpها
  در `data/knowledge` (فقط خواندنی برای consumption بعدی).

---

*این گزارش بخشی از مأموریت PCM-14C.3 است؛ مستندات فنی کامل در
`docs/PCM-14C.3-DUMP-CONTRACT.md` و راهنمای کاربر در
`docs/WORD-FACTORY-USER-GUIDE.md`.*

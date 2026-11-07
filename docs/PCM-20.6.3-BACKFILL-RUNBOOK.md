# PCM-20.6.3 — Runbook اجرای Backfill پیکره

| فیلد | مقدار |
|-----|-------|
| مأموریت | PCM-20.6.3 — اجرای واقعی Backfill (فقط پس از Gate B) |
| سند طراحی | `docs/PCM-20.6.3-BACKFILL-DESIGN.md` (سیاست `bf-2`) |
| برآورد زمان کل | ≈ 45,243 × 15s ≈ **188.5 ساعت ≈ 7.9 روز** در نرخ هدف 4 صفحه/دقیقه |
| تعداد اجراها | ≈ 91 اجرا با budget 500 (هر اجرا یک دستور `run`) |

> ⚠️ **این Runbook فقط پس از عبور Gate B قابل اجراست:**
> 1. تأیید دسترس‌پذیری زنده‌ی سایت (پروب ≤10 GET)
> 2. تأیید نرخ و عدم خطای 5xx مکرر
> 3. تأیید صریح اپراتور (دستور زنده فقط با `--allow-live` +
>    `BACKFILL_APPROVED=approved`)

---

## ۱. پیش‌نیازها

| # | پیش‌نیاز | چک |
|---|---------|-----|
| 1 | ماشین با دسترسی شبکه به `tasnim.hamtaa.org` (اتصال از s52 یا هر host با اینترنت) | `curl -sI https://tasnim.hamtaa.org` → 200/301 |
| 2 | درجه‌ی پایدار `v0003` در `data/tasnim/pcm20_5/corpus/builds/v0003/` (pages.jsonl + manifest.json) | `python -m corpus.tasnim.cli validate-corpus --build <v0003 dir>` |
| 3 | Python 3.8+ با stdlib فقط (بدون pip install) — یا همان `.venv` خط تولید | `python --version` |
| 4 | دایرکتوری کاری خالی برای خروجی run (مثلاً `data/tasnim/backfill/v0004-run/`) | — |
| 5 | دایرکتوری data root برای ثبت (جایی که `corpus/builds` و `manifests` دارد) | — |

مسیر‌های این Runbook (مثال — با `cd` به ریشه‌ی repository):

```text
PAGES=data/tasnim/pcm20_5/corpus/builds/v0003/pages.jsonl
BASE =data/tasnim/pcm20_5/corpus/builds/v0003
ROOT =data/tasnim/pcm20_5
WORK =data/tasnim/backfill/v0004-run
```

---

## ۲. مراحل اجرا (دستورهای دقیق)

همه‌ی دستورها از **ریشه‌ی repository** اجرا می‌شوند (بررسی‌شده:
`python -X utf8 -m corpus.tasnim.backfill.cli --help` روی این مسیر سبز است).
کدخروجی: `0` موفق · `1` validation fail · `2` input/guard error.

### ۲.۱ گزارش شکاف (dry، بدون شبکه)

```bash
python -X utf8 -m corpus.tasnim.backfill.cli gap-report \
  --pages "%PAGES%" --out "%WORK%/gap-report.json"
```

**انتظار (داده‌ی واقعی v0003):**
`45,243` مفقود در `6` بازه (دقیقاً همان اعداد Phase-0) + `content sha`.
اگر اعداد متفاوت بود → **متوقف شو** و baseline را بازخوانی کن.

### ۲.۲ برنامه‌ی Fetch (dry، بدون شبکه)

```bash
python -X utf8 -m corpus.tasnim.backfill.cli plan \
  --gap-report "%WORK%/gap-report.json" --out "%WORK%/fetch-plan.json"
```

**انتظار:** 45,243 آیتم صاعد؛ `estimated_hours_at_target ≈ 188.5`؛
`estimated_runs_at_budget ≈ 91` (budget 500)؛ `plan sha` چاپ می‌شود.
**`plan sha` را یادداشت کن** — checkpoint با آن قفل است.

### ۲.۳ dry-run (بدون هیچ درخواست)

```bash
python -X utf8 -m corpus.tasnim.backfill.cli run \
  --plan "%WORK%/fetch-plan.json" --base-pages "%PAGES%" \
  --out-dir "%WORK%/run" --dry-run
```

**انتظار:** `budget used: 500`، `fetched: 0`، `pending left: 44,743`،
فایل `backfill-records.jsonl` ساخته **نمی‌شود**. guard لازم نیست.

### ۲.۴ تأیید (Gate B) — قبل از اولین اجرای زنده

- پروب ≤10 GET دستی با curl (نمونه):
  ```bash
  curl -s -o /dev/null -w "%%{http_code}" "https://tasnim.hamtaa.org/api/v1/files/tasnim/chunk-detail?item_index=5000"
  ```
  (5000 درون بازه‌ی مفقود [3649–11182] است)
- تأیید: 200 با JSON معتبر / 404 (مجاز، permanent) — نه 5xx مکرر.
- ثبت صریح تأیید در گزارش مأموریت + ست env در همان shell:
  ```bat
  set BACKFILL_APPROVED=approved
  ```

### ۲.۵ اجرای زنده با resume (≈91 تکرار)

هر اجرا حداکثر 500 آیتم فعال (budget)؛ checkpoint بین اجراها باقی می‌ماند:

```bat
for /L %%i in (1,1,91) do (
  python -X utf8 -m corpus.tasnim.backfill.cli run ^
    --plan "%WORK%/fetch-plan.json" --base-pages "%PAGES%" ^
    --out-dir "%WORK%/run" --budget 500 --allow-live || (
    echo RUN %%i FAILED — متوقف شد
    exit /b 1
  )
)
```

**نکات عملی:**
- هر اجرا تقریباً 500 × ~15s ≈ **2.1 ساعت** طول می‌کشد → کل ≈ 7.9 روز.
- اگر اجرای بین‌البهره قطع شود، کافی است همان دستور `run` را دوباره
  اجرا کنی — checkpoint stageها را حفظ می‌کند (exact-once).
- 404ها `permanent` می‌شوند و در `run/backfill-records.jsonl`/
  `run-report.json` (`permanent_failures`) ثبت می‌شوند — **بدون retry**.
- در هر اجرا خروجی `pending left` باید دقیقاً 500 واحد کم شود
  (مگر اینکه permanent/404 رخ دهد).
- اگر 5xx مکرر دیدی: متوقف شو، `BACKFILL_APPROVED` را unset کن و
  Gate B را دوباره ارزیابی (کاهش budget/نرخ).

### ۲.۶ verify (اجباری پیش از register)

```bat
python -X utf8 -m corpus.tasnim.backfill.cli verify ^
  --plan "%WORK%/fetch-plan.json" --out-dir "%WORK%/run" ^
  --base-pages "%PAGES%"
```

**انتظار:** `verify: PASS`؛ `records ≈ 45,243 − permanent`؛
`checkpoint` همه‌ی آیتم‌ها terminal؛ `base sha` = SHA فعلی `pages.jsonl`
v0003 (اثبات عدم تغییر base). در صورت FAIL → register نمی‌شود (کد 1).

### ۲.۷ register — ساخت v0004

```bat
python -X utf8 -m corpus.tasnim.backfill.cli register ^
  --plan "%WORK%/fetch-plan.json" --base "%BASE%" --base-pages "%PAGES%" ^
  --out-dir "%WORK%/run" --data-root "%ROOT%" --version 4
```

**اثرها (append-only):**
- کپی `backfill-records.jsonl` → `%ROOT%/corpus/builds/v0004/backfill/`
- `%ROOT%/corpus/builds/v0004/backfill/manifest.json`
  (`backfill-manifest-1`، `prev → v0003/corpus`)
- entry جدید `backfill:v0004` در `%ROOT%/manifests/registry.json`
- چاپ diff پنج‌حالته: `new / duplicate / unchanged / changed / absent`

**انتظار منطقی:** `new` بزرگ‌ترین دسته؛ `unchanged` ممکن است صفر باشد
(چون base اصلاً این indexها را ندارد)؛ `changed` فقط اگر base رکوردی با
همان index ولی متن متفاوت داشته (dupهای vol1×vol47)؛ `absent` = تعداد
permanent/budget-ناکار.

### ۲.۸ گزارش نهایی (Gate C)

در گزارش مأموریت: شمارنده‌های verify + diff + شمارنده‌های
`permanent_failures` + SHA base قبل/بعد + registry diff.

---

## ۳. Abort / Rollback

| وضعیت | عمل |
|------|-----|
| قطع بین اجراها (kill/خاموشی) | هیچ چیزی از دست نمی‌رود؛ همان `run` را دوباره بزن (checkpoint) |
| توقف کامل پیش از register | `run/` را نگه دار؛ base دست‌نخورده است؛ هیچ اثری در registry |
| register شد ولی diff نادرست است | **rollback** = base (v0003) همان است — `v0004/backfill` استفاده نشود + entry registry با `status: "rolled_back"` و `active_base_unchanged: true` (تابع `backfill.manifest.rollback_entry`) |
| plan اشتباه ساخته شد (مثلاً budget/نرخ عوض) | `fetch-plan.json` را از step ۲.۲ بساز؛ اگر `run/` قدیمی باشد، دایرکتوری جدید `--out-dir` بده — checkpoint با `plan_sha` قفل است و resume اشتباه **مسدود** می‌شود |
| اشتباه در `--version` | register را با شماره‌ی صحیح تکرار کن (registry append-only است؛ entry غلط با `rolled_back` علامت می‌خورد) |

**قاعده‌ی طلایی:** هیچ فایلی از `v0003` در هیچ مرحله نوشته نمی‌شود →
rollback هیچ‌وقت «بازگرداندن فایل» نیست، فقط «عدم استفاده از لایه‌ی جدید».

---

## ۴. شکست‌های دائمی (permanent)

- `404` → `permanent_failures` با `reason: "not_found (404)"`
- parse error (JSON نامعتبر / `original_text` ندارد / mismatch URL↔payload)
  → `reason: "parse: ..."`
- 3 attempt شکست خورد (5xx/شبکه) → `reason: "5xx/network exhausted"`
- همه در `run/run-report.json` و manifest ثبت می‌شوند.
- **اصلاح بعدی:** list را در مأموریت جدا با `plan` مجدد و فقط همان
  indexها fetch کن (فرآیند تکرارپذیر است چون همه‌چیز از
  `gap-report-2` شروع می‌شود).

---

## ۵. چک‌لیست ایمنی (هر اجرا)

- [ ] `v0003` در filesystem read-only بررسی شد (SHA قبل/بعد run)
- [ ] هیچ دستور `git reset --hard` / `git clean -fd` / force-push در بازی نیست
- [ ] `run` زنده فقط با `--allow-live` **و** `BACKFILL_APPROVED=approved`
- [ ] `dry-run` قبل از اولین اجرای زنده سبز بود
- [ ] `plan sha` بین plan و checkpoint یکی است
- [ ] نرخ ≤ 4 صفحه/دقیقه (delay 15s) — تغییر `--delay` فقط با مستندسازی
- [ ] بعد از هر اجرا: `pending left` منطقی است (≤ budget کم شده)
- [ ] بعد از تمام اجراها: `verify: PASS` **قبل** از register
- [ ] هیچ secret در لاگ/گزارش/manifest نیست (فقط UA عمومی)

---

## ۶. عیب‌یابی سریع

| علامت | علت محتمل | اقدام |
|------|----------|------|
| خروج 2 + `LIVE GUARD` | `--allow-live` یا env ناقص | هر دو را ست کن و دوباره |
| خروج 2 + `checkpoint: ... plan sha mismatch` | plan عوض شده و `run/` قدیمی است | `--out-dir` جدید بده یا plan قبلی را بازسازی کن |
| `fetched` زیاد ولی `pending left` کم نمی‌شود | permanent در حال جمع شدن است (404/parse) | `run-report.json` را ببین — ممکن است بازه‌ی واقعی 404 بدهد |
| 5xx مکرر | server شلوغ/مسدودکننده | متوقف شو؛ Gate B را بازنشانی کن |
| `verify: FAIL` | records ناقص یا base تغییر کرده (نباید شود) | run را با budget کوچک‌تر ادامه بده؛ base را ممیزی کن |

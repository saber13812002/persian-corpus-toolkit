# PCM-20.6.3 — طرح Backfill پیکره (طراحی)

| فیلد | مقدار |
|-----|-------|
| مأموریت | PCM-20.6.3 — آماده‌سازی Backfill پیکره‌ی «تفسیر تسنیم» (Track A — طرح + اسکلت جدا) |
| نسخه‌ی سند | 1.0 (۱۴۰۵/08/15) |
| جایگزینی | طرح `bf-1` (بخش `backfill_design` در `corpus/tasnim/gap_report.py` — «design-only (not executed)») |
| سیاست نسخه | `bf-2` (`old_wins=True`, `volume_guessing=False`) |
| وضعیت | **READY_FOR_APPROVAL** (طرح + اسکلت + تست آفلاین؛ بدون هیچ درخواست زنده) |

> **قاعده‌ی مهم:** این سند و اسکلت کد، **مجاز به هیچ درخواست شبکه‌ای نیستند**.
> اجرای زنده فقط در مأموریت بعدی و پس از Gate B (تأیید دسترسی + نرخ) و
> تأیید صریح اپراتور (`--allow-live` + `BACKFILL_APPROVED=approved`) مجاز است.

---

## ۱. هدف و محدوده

**هدف:** بازیابی ۴۵٬۲۴۳ صفحه‌ی مفقود از پیکره‌ی رسمی `v0003` (تفسیر تسنیم) از
سرور اصلی `tasnim.hamtaa.org`، به‌صورت یک لایه‌ی جدا و قابل‌برگشت که نسخه‌ی
`v0004 = v0003 + backfill` را می‌سازد — بدون دست‌زدن به هیچ فایل `v0003`.

**محدوده‌ی این مأموریت (Track A):**
- تحلیل منبع و طراحی خط لوله (این سند)
- اسکلت کامل کد در `corpus/tasnim/backfill/` (۸ ماژول + CLI)
- ۲۸ تست آفلاین (بدون شبکه) + رگرسیون ۵ سوئیت موجود
- Runbook و سند پذیرش

**خارج از محدوده:**
- هیچ درخواست زنده به سایت (حتی یک GET)
- تغییر schema / DB / اکستنشن / Crawler
- تغییر هیچ رکورد یا فایل `v0003` (immutable)
- Embedding / Neo4j / Elasticsearch
- شروع Track B (وب)

---

## ۲. پیش‌فرض‌های اثبات‌شده (از PCM-20.6 Phase-0)

این اعداد در Phase-0 روی snapshot واقعی محاسبه و در **BF01b** (این مأموریت)
دوباره تکرار شدند (۲۸/۲۸ تست روی داده‌ی واقعی، read-only):

| فیلد | مقدار |
|-----|-------|
| صفحات `v0003` | 45,844 |
| بازه‌ی item_index | [0 .. 91077] → 91,078 موقعیت |
| item_indexهای متمایز | 45,835 |
| item_index تکراری (dup) | 9 (همه برخورد vol1×vol47) |
| صفحات مفقود | **45,243** در **6 بازه** |
| بازه‌های مفقود | [3649–11182] (7,534) · [11205–39003] (27,799) · [44957–49956] (5,000) · [55699–55701] (3) · [55715–59590] (3,876) · [89280–90310] (1,031) |
| صفحات 2000-کاراکتری | 28 (سقف خود منبع برای RAG — **بازیافتنی نیست**، GATE 1.5 PASS) |
| صفحات خالی | 35 |
| SHA محتوای `v0003` | `40f45e0b...` |

**منبع:** `docs/PCM-20.6-BASELINE.md` §10.5 (حساب مجدد gap، verbatim) و §1.6
(برش 2000). نقطه‌ی پایانی `chunk-detail` در GATE 1.5 E4 زنده تأیید شده است؛
اما **خزش کامل ۴۵٬۲۴۳ صفحه هنوز هرگز اجرا نشده** — این دقیقاً چیزی است که
PCM-20.6.3 آماده می‌کند.

---

## ۳. تحلیل منبع

### ۳.۱ ساختار URL و شناسه‌ها

- نقطه‌ی پایانی:
  `GET https://tasnim.hamtaa.org/api/v1/files/tasnim/chunk-detail?item_index=N`
- پاسخ JSON: `{original_text, section, values?, item_index?}`
- URL **هیچ پارامتر section ندارد** → فیلد `section`ِ **payload** قوی‌ترین
  شواهد برای تطبیق جلد است (نه URL).
- `item_index` = هویت مرتب‌سازی **متناثر (sparse)** — کلید اصلی fetch.
- `barg` = شماره‌ی چاپی برگ (مثل `۳۹٬۰۰۵`) — **کلید نیست**؛ فقط داده‌ی
  نمایشی. پارسر اصلاح‌شده: `common.parse_barg_all_runs` (اصلاح PCM-20.2؛
  رگرسیون T10c + BF10).
- `/payload` (SPA-shell) **مصرف‌پذیر نیست** — فقط `chunk-detail`.

### ۳.۲ تطبیق جلد (volume) — هرگز حدس نمی‌زنیم

`parse.volume_candidates` شواهد را به ترتیب قوت جمع می‌کند:

| اولویت | شواهد | منبع |
|------|------|------|
| ۱ (قوی‌ترین) | `payload_section` | فیلد `section`ِ JSON پاسخ |
| ۲ | `url_section` | (legacy — در این endpoint وجود ندارد) |
| ۳ | متن خود صفحه | الگوی «جلد N» در `original_text` |
| — (فناوی) | همسایه‌ها | صفحات قبلی/بعدی در base — **فقط راهنما، جزو candidates نیست** |

وضعیت‌ها (whitelist، فقط این سه):

| وضعیت | شرط | رفتار |
|------|-----|------|
| `resolved` | دقیقاً ۱ کاندیدای متمایز | `volume_no` ست می‌شود |
| `ambiguous` | >۱ کاندیدای متمایز | `volume_no=None` + `ambiguous=true` — **هرگز حدس** |
| `unresolved` | ۰ کاندیدا | `volume_no=None` + راهنمای همسایه در گزارش |

### ۳.۳ کیفیت صفحات (order ثابت flags)

`parse.quality_flags` — order ثابت (مهم برای ممیزی):

1. `empty` (متن خالی)
2. `short` (< 20 کاراکتر — `reconcile.MIN_TEXT_CHARS`)
3. `truncated_at_2000` (== `SOURCE_CHAR_CAP` = 2000)
4. `no_barg`
5. `missing_item_index`
6. `dup_item_index`

---

## ۴. قوانین ثابت (invariants)

| # | قاعده |
|---|-------|
| I1 | `page_id` = `<volume_id>__p<item_index>[__d<n>]` — کلید یکتا؛ `item_index` کلید fetch؛ `barg` هرگز کلید نیست |
| I2 | **v0003 immutable**: هیچ فایلی از base نوشته/پاک/بازنام‌گذاری نمی‌شود؛ فقط خوانده می‌شود |
| I3 | **هرگز حدس volume**: شواهد + flag فقط |
| I4 | **زنجیره‌ی provenance**: هر رکورد backfill: `url + fetched_at + http_status + attempts + payload_sha256 + text_sha256 + base_state` |
| I5 | **Old-wins (R15)**: اگر متن base با fetch متفاوت باشد، رکورد base برتر است؛ رکورد backfill فقط **ثبت** می‌شود (flag `changed`) |
| I6 | append-only: رکوردها فقط اضافه می‌شوند؛ registry فقط entry جدید می‌گیرد |
| I7 | بدون تأیید دوگانه هیچ درخواست زنده: `--allow-live` **و** env `BACKFILL_APPROVED=approved` |
| I8 | rate ≤ 4 صفحه/دقیقه + jitter ±30٪ + UA شناسا + timeout 40s |
| I9 | هر رکورد فقط یک‌بار fetch می‌شود (exact-once با checkpoint terminal) |
| I10 | 404 = شکست دائمی (بدون retry)؛ 5xx/شبکه = retryable (exponential backoff) |

---

## ۵. معماری خط لوله

### ۵.۱ ماژول‌ها (در `corpus/tasnim/backfill/`)

| ماژول | قرارداد | وظیفه |
|------|--------|------|
| `gap.py` | `gap-report-2` | محاسبه‌ی شکاف از `pages.jsonl` base (شمارنده‌ها + بازه‌ها + `summary_fa` + `content_sha256` قبل از `generated_at`) |
| `fetch_plan.py` | `fetch-plan-1` | برنامه‌ی Fetch مرتب‌شده‌ی صاعد + delay قطعی (jitter SHA-seeded) + برآورد زمان/باجت |
| `parse.py` | `backfill-parse/1` | پارس `chunk-detail` + cross-check URL↔payload + volume + flags + change + رکورد کامل |
| `checkpoint.py` | `checkpoint-1` | وضعیت per-item (`pending→fetched→parsed→written→done` / `retry` / `permanent`)؛ نوشتن اتمیک؛ قفل `plan_sha` |
| `runner.py` | `backfill-run-report-1` | اجرای pipeline با budget + retry/backoff + verify خروجی |
| `manifest.py` | `backfill-manifest-1` | diff پنج‌حالته + manifest v0004 + ثبت registry + entry rollback |
| `transport.py` | — | `FakeTransport` (تست) / `LiveTransport` (urllib، پشت guard) / `live_guard` |
| `cli.py` | — | 5 subcommand: `gap-report` · `plan` · `run` · `verify` · `register` (کدخروجی 0/1/2) |

فقط stdlib، Python 3.8+ — مطابق قرارداد خط تولید.

### ۵.۲ جریان (pipeline)

```
pages.jsonl (v0003, read-only)
      │
      ▼
[1] gap-report-2          محاسبه‌ی 45,243 مفقود در 6 بازه
      │
      ▼
[2] fetch-plan-1          45,243 آیتم صاعد + delay قطعی + برآورد
      │
      ▼
[3] run (budget 500)      ┌──────────────────────────────────────────┐
                          │ per item:                                │
                          │  terminal? ──skip──► pending/continue    │
                          │  HTTP GET (guard!)                       │
                          │  404 ──────────────► permanent (no retry)│
                          │  5xx/net ──────────► backoff 30/90/270   │
                          │  parse ──error──────► permanent          │
                          │  OK ─► record ─► write line              │
                          │  checkpoint mark (atomic) per stage      │
                          └──────────────────────────────────────────┘
      │  (≈91 اجرا × 500؛ resume از checkpoint)
      ▼
[4] verify                بازخوانی records + checkpoint + plan_sha
                          + SHA فایل base (اثبات عدم تغییر)
      │
      ▼
[5] register v0004        manifest backfill (prev→v0003) + registry
                          (append-only) + کپی records به
                          corpus/builds/v0004/backfill/
```

### ۵.۳ کنترل نرخ و خطا

| پارامتر | مقدار | توضیح |
|--------|------|------|
| نرخ هدف | 4 صفحه/دقیقه | delay پایه = 15s |
| jitter | ±30٪ قطعی (SHA-seeded) | delay ∈ [10.5, 19.5] — تکرارپذیر |
| timeout | 40s | per request |
| max attempts | 3 | فقط برای 5xx/خطای شبکه |
| backoff | 30 → 90 → 270s | `base × 3^(attempt-1)` |
| budget هر اجرا | 500 | `run` هر بار حداکثر 500 آیتم فعال |
| 404 | **permanent، بدون retry** | در `permanent_failures` ثبت می‌شود |
| parse error | **permanent** | با reason `"parse: ..."` |
| UA | `pct-tasnim-backfill/1.0 (read-only; corpus repair; contact: saber@ismc.ir)` | شفاف و قابل ردیابی |

**برآورد زمان:** 45,243 × 15s ≈ **188.5 ساعت ≈ 7.9 روز** در نرخ هدف؛
≈ 91 اجرا با budget 500 (بدون احتساب backoff خطاها).

### ۵.۴ checkpoint و resume

- `checkpoint.json` با `plan_sha` قفل است: اگر plan عوض شود، resume
  مسدود می‌شود (`CheckpointError`) — جلوگیری از تفسیر غلط وضعیت.
- stageها: `pending → fetched → parsed → written → done` (terminal)؛
  `retry`؛ `permanent` (terminal).
- نوشتن اتمیک: tmp در همان دایرکتوری + `os.replace`.
- `done` نهایی است (idempotent) → exact-once حتی با kill در هر لحظه.

### ۵.۵ guard زنده (دفاع در عمق)

`transport.live_guard(allow_live, approved_token)`:
1. flag `--allow-live` **و**
2. env `BACKFILL_APPROVED` == `"approved"` (دقیق)

کمتر از هر دو → `TransportGuardError` → خروج 2 **قبل از هر درخواست**.
`run --dry-run` (بدون `--fake-bodies`) اصلاً transport نمی‌سازد.
`--fake-bodies` (JSON `{item_index: body}`) همیشه مجاز — آفلاین.

---

## ۶. مدل نسخه‌بندی و rollback

- `v0004 = v0003 + backfill` — یک **لایه‌ی جدید** در
  `corpus/builds/v0004/backfill/` (records کپی می‌شوند، append-only).
- **هیچ رکورد base بازنویسی نمی‌شود**؛ سیاست `bf-2/old-wins`:
  - `new` — item_index در base نبود → رکورد کاملاً جدید
  - `unchanged` — SHA متن دقیقاً برابر base
  - `changed` — متن متفاوت → **رکورد base برتر**؛ backfill فقط ثبت (R15)
  - `duplicate` — base خودش dup index دارد
  - `absent` — آیتم plan که fetch نشد (budget ناتمام / 404)
- **manifest:** قرارداد `backfill-manifest-1` بر بستر `m-20.3`:
  زنجیره‌ی `prev → v0003/corpus`، SHA-256 فایل‌ها، `policy`،
  `rollback{strategy: "keep-base"}`، ثبت در registry (append-only).
- **rollback:** = **نگه‌داشتن base** (v0003 دست‌نخورده) + entry registry
  با `status: "rolled_back"` و `active_base_unchanged: true`.
  هیچ فایل base هیچ‌وقت دست نمی‌خورد → rollback ارزان و بدون ریسک است.
- **بازیافت نادرست صفحات برش‌خورده:** 28 صفحه‌ی 2000-کاراکتری سقف خود
  منبع است و در backfill **بازیافتنی نیست** (خروجی همان 2000 کاراکتر
  را برمی‌گردد) — فقط flag می‌خورند.

---

## ۷. قرارداد داده

| فایل | فرمت | قرارداد |
|------|------|--------|
| `gap-report.json` | JSON | `gap-report-2` |
| `fetch-plan.json` | JSON | `fetch-plan-1` |
| `run/backfill-records.jsonl` | JSONL (append) | رکورد کامل §7.1 |
| `run/checkpoint.json` | JSON | `checkpoint-1` |
| `run/run-report.json` | JSON | `backfill-run-report-1` |
| `corpus/builds/v0004/backfill/manifest.json` | JSON | `backfill-manifest-1` |
| `manifests/registry.json` | JSON | append-only entry جدید |

### ۷.۱ رکورد backfill (حداقل فیلدها)

`item_index, url, fetched_at, http_status, attempts, text, text_sha256,
text_len, section, raw_barg, barg, barg_parse, payload_item_index,
payload_sha256, volume{status, volume_no, candidates, neighbors, ambiguous},
quality_flags[], base_state{present_in_base, dup_in_base, base_page_ids,
base_content_hash}, change, parser_version, policy_version`

SHAها بر مبنای `common.canonical_json` (sort_keys, indent=1) — سازگار با
قراردادهای `m-2`/`d-1`.

---

## ۸. چیزهایی که **فرض نمی‌کنیم** + درهای تصمیم

| # | عدم‌فرض | در (gate) |
|---|--------|-----------|
| A1 | دسترس‌پذیری سایت در لحظه‌ی اجرا تضمین شده نیست (s52 آفلاین است؛ خود سایت در GATE 1.5 زنده بود ولی خزش کامل نشکافته) | **Gate B**: پروب ≤10 GET + تأیید نرخ قبل از هر اجرای زنده |
| A2 | ممکن است server 404 بدهد (صفحه حذف شده) → در `permanent_failures` ثبت می‌شود، **ساکت حذف نمی‌شود** | گزارش در run-report + manifest |
| A3 | volume ممکن است ambiguous بماند → flag؛ حدس ممنوع | ممیزی دستی قبل از هر استفاده‌ی volume-based |
| A4 | نرخ تحمل سایت ناشناخته → سقف 4 pg/min + jitter | Gate B: مشاهده‌ی خطا → کاهش budget/نرخ |
| A5 | `/payload` ممکن است بازگردد؟ خیر — SPA-shell، مصرف نمی‌شود | فقط `chunk-detail` |
| A6 | 28 صفحه‌ی برش‌خورده ممکن است «داده کامل» برگردند؟ خیر — سقف منبع | خارج از scope |
| A7 | داده‌های `v0003` ممکن است عوض شده باشند؟ — verify، SHA base را بازخوانی می‌کند | verify قبل از register (اجباری) |

**Gate A (این مأموریت):** طرح + اسکلت + تست آفلاین → **READY_FOR_APPROVAL** (این سند).
**Gate B (مأموریت بعدی):** تأیید دسترسی زنده + نرخ + تأیید صریح اپراتور.
**Gate C:** verify سبز + register v0004 + ثبت گزارش.

---

## ۹. جایگزینی طرح قبلی (`bf-1`)

`corpus/tasnim/gap_report.py` هنوز تابع `backfill_design` با
`BACKFILL_ID = "bf-1"` / `BACKFILL_STATUS = "design-only (not executed)"`
دارد (گزارش شکاف v1). این طرح جدید (`bf-2`) آن را **جایگزین** می‌کند:

| وجه | bf-1 (قدیم) | bf-2 (این طرح) |
|-----|------------|---------------|
| خروجی | snapshot خام (JSONL) | لایه‌ی نسخه‌شده backfill روی پیکره‌ی canonical |
| نسخه | snapshot جدید خام | `v0004 = v0003 + backfill` با manifest `backfill-manifest-1` |
| checkpoint | ندارد | `checkpoint-1` + resume exact-once |
| volume | attribute تقریبی | شواهد + flag، هرگز حدس |
| guard | ندارد | guard دوگانه زنده |
| rollback | — | keep-base + entry registry |

تابع `bf-1` **جا می‌ماند** (فقط گزارش v1 است و تغییری در آن نمی‌شود —
حذف کد خارج از scope است).

---

## ۱۰. صحت‌سنجی

- ۲۸ تست آفلاین (BF01–BF22b) — بدون شبکه؛ جزئیات:
  `docs/PCM-20.6.3-BACKFILL-ACCEPTANCE.md`.
- تکرار اعداد Phase-0 روی `v0003` واقعی (BF01b): 6 بازه / 45,243 /
  45,844 / 45,835 / 9 dup — **دقیقاً مطابق §10.5 baseline**.
- رگرسیون ۵ سوئیت خط تولید: 52 تست سبز.
- `v0003` در تمام اجراها read-only بود (SHA verify در verify_output).
- هیچ commit نشده؛ اسکلت در worktree جدا (branch `pcm-20.6-tasnim-web-v1`
  روی base `20911d7`).

# گزارش PCM-15 — صف پایدار پردازش فایل (Persistent Per-file Processing Queue)

تاریخ: ۱۴۰۵/۰۸/۰۷ (2026-10-29) · شاخه: `main` · commit پایه: `519f98f` (PCM-14D report)

---

## A. خلاصه اجرایی

مأموریت «PCM-15 — صف پایدار پردازش فایل» به‌طور کامل انجام شد: هر فایل
یادداشت‌شده در یک کالکشن حالا یک **ردیف پایدار** با آخرین stage ایمن،
تعداد تلاش، خطای آخر، زمان‌بندی، SHA-256 و مسیر خروجی دارد؛ pause/resume
بین فایل‌ها ممکن است؛ ریکاوری بعد از crash/kill ردیف‌های مانده را با حفظ
stage به `pending` برمی‌گرداند؛ و خروجی صف با قرارداد Dump `d-1` سازگار
مانده است.

نتیجه‌ها:

1. **2 جدول جدید** `knowledge_file_queue` (PK: `collection_id, file_key`)
   و `knowledge_queue_control` (پرچم pause به ازای هر بچ) — کاملاً
   افزایشی و idempotent (`CREATE TABLE IF NOT EXISTS` در
   `ensure_knowledge_schema`)؛ هیچ DROP/RENAME/تغییر نوع ستونی.
2. **callback اختیاری `on_stage`** در Word Factory
   (`backend/factory/service.py`) — بلافاصله پس از کامل شدن هر stage از
   ۸ stage صدا می‌شود؛ factory همچنان بدون DB/Flask است (WF-12 سبز).
3. **worker بچ queue-aware**: برای هر فایل چک pause → `_queue_start`
   (running, attempts+1) → `_process_document(on_stage=writer)` → وضعیت
   پایانی. safety-net: هیچ ردیفی در `running` نمی‌ماند.
4. **retry تکی آینه‌دار**: `POST /documents/<id>/process` اگر ردیف صف
   وجود داشته باشد، همان ردیف را به‌روز می‌کند (attempts+1، last_error
   تازه) — صف و اسناد هرگز واگرا نمی‌شوند.
5. **3 endpoint جدید** (همگی پشت auth PCM-09): `POST .../pause`،
   `POST .../resume`، `GET /api/knowledge/queue/summary` (شمارنده‌ها
   یک‌به‌یک از جدول صف؛ آمار ساختگی/کش‌شده وجود ندارد) + افزودگی
   `queue`/`paused`/`queue_control` در پاسخ detail بچ.
6. **9 تست جدید** (Q-01..Q-08 در `backend/test_queue.py`، 582 خط) +
   **3 تست on_stage** در `test_word_factory.py` + رگرسیون کامل
   **151/151 سبز**.
7. سند طراحی: `docs/PCM-15-FILE-QUEUE.md` (قراردادهای دقیق، DDL،
   worker، ریکاوری، endpointها، سازگاری d-1، ماتریس تست، محدودیت‌ها) +
   OpenAPI: `docs/openapi/pcm15-file-queue.openapi.yaml`.
8. **بدون deploy**: چک خواندنی s52 اجرا شد و production را
   دست‌نخورده/سالم تأیید کرد (بخش H و I).

## B. وضعیت قبل از تغییر و ممیزی

- git: clean روی `519f98f` (= `origin/main`، commit گزارش PCM-14D)؛
  رگرسیون 139 تست سبز.
- ممیزی موجود (PRAGMA + خواندن کد):
  - وضعیت پردازش فقط در سطوح job (کل بچ) و سند (یک وضعیت نهایی) بود؛
    هیچ ردیف پایدار per-file از `stage`/`attempts`/`last_error`/
    `duration_ms` وجود نداشت.
  - `_recover_interrupted` فقط job/بچ/سند را بازیابی می‌کرد؛ فایلی که
    worker وسط پردازشش crash کرده بود قابل ردیابی نبود.
  - pause/resume هیچ مکانیزمی نداشت (نه endpoint، نه چک در worker).
  - `factory/service.py` `process()` بدون hook stage بود — ثبت stageهای
    کامل‌شده در DB فقط با تغییر factory ممکن بود.
- نتیجه ممیزی: مهاجرت **افزایشی** (2 جدول جدید + callback اختیاری)
  کافی است؛ رفتار همه endpointهای قدیمی و قرارداد Dump `d-1` دست‌نخورده
  می‌ماند.
- **نکته مهم (ممیزی s52):** با اولین اجرای
  `deploy/pcm15_s52_readonly_check.sh` معلوم شد s52 در وضعیت
  **pre-PCM-14D** است (endpoint `/api/knowledge/works` → 404، جدول
  `knowledge_works` غایب، `knowledge_api.py` 1781 خط) — مطابق گزارش
  PCM-14D که ثبت کرده بود 14D روی s52 استقرار **نشده** است. انتظارهای
  اسکریپت بر همین اساس اصلاح و چک دوباره اجرا شد (نتیجه بخش H).

## C. طراحی

**مدل (خلاصه — کامل در `docs/PCM-15-FILE-QUEUE.md`):**

```
knowledge_collections (1) ──< knowledge_collection_documents (N)
        │                              │  (file_id = "f-"+sha256[:8])
        ▼                              ▼
knowledge_file_queue                knowledge_queue_control
  PK (collection_id, file_key)        PK scope = "batch:<batch_id>"
  status/stage/attempts/last_error/   paused 0/1 + updated_at
  duration_ms/out_dir/sha256
```

- **file_key** = `"f-" + sha256[:8]` — همان شناسه‌ای که Upload برای
  فایل اصلی می‌سازد (`files/<sha12>/<file_key>.docx`). dedup با
  `ON CONFLICT DO NOTHING`.
- **تفکیک هویتی (مستند):** `file_key` با `file_id` خود factory
  یکسان **نیست** (factory `short_id("f", sha)` = hash دوبرابر می‌سازد
  و خروجی را در `out/<file_id>/` می‌نویسد). ستون `out_dir` ردیف صف
  مسیر واقعی خروجی factory را (نسبی، جداکننده `/`) نگه می‌دارد —
  single source of truth برای مکان خروجی.
- **stage** = آخرین stage **کامل** شده ایمن (`NULL` = هیچ)؛ ثبت per-stage
  با commit جدا توسط `on_stage`. «retry از آخرین stage امن» صادقانه:
  retry = اجرای قطعی و idempotent مجدد روی فایل اصلی ذخیره‌شده (sha
  بازمهک شده — WF-10)، نه ادامه از حافظه وسط پایپ.
- **وضعیت‌ها:** `pending → running → succeeded | needs_review | failed`
  (quality.passed → succeeded/سند `parsed`؛ quality manual_review →
  needs_review/سند `needs_review`، خود job موفق می‌ماند).
- **pause:** worker قبل از هر فایل پرچم را چک می‌کند → بچ `planned` +
  job `interrupted` («[paused by user]»)؛ resume فقط پرچم را پاک می‌کند
  و `/process` با idempotency job ادامه می‌دهد.
- **ریکاوری:** UPDATE چهارم در `_recover_interrupted` — ردیف صف
  `running` قدیمی‌تر از پنجره stuck → `pending` **با حفظ stage**؛
  ردیف تازه لمس نمی‌شود.
- **rollback:** drop دو جدول جدید؛ ستون/رفتار قدیمی دست‌نخورده است.

## D. تغییرات کد و فایل

**جدید:**

| فایل | توضیح |
|-------|-------|
| `backend/test_queue.py` (582 خط) | 9 تست Q-01..Q-08 (ایزوله؛ `pct_test_support`) |
| `docs/PCM-15-FILE-QUEUE.md` (205 خط) | سند طراحی: قراردادها، DDL، callback، worker، ریکاوری، endpointها، سازگاری d-1، ماتریس Q، محدودیت‌ها |
| `docs/openapi/pcm15-file-queue.openapi.yaml` (238 خط) | OpenAPI 3.0.3: pause/resume/queue-summary + افزودگی batch detail + schemas QueueRow/QueueControl/QueueCounters + مستندسازی تفاوت file_key/file_id |
| `deploy/pcm15_s52_readonly_check.sh` (87 خط) | چک خواندنی s52 (بدون deploy/نوشتن) — اجرا شده (بخش H) |

**تغییرکرده (کد):**

| فایل | تغییر |
|-------|-------|
| `backend/knowledge_api.py` (+~390) | 2 جدول در DDL + ثابت‌های status/stage + 9 helper صف (pause flag، `_queue_row/_stage_writer/_start/_finish/_ensure_rows`، `queue_counters`) + on_stage در batch/single-doc + safety-net + UPDATE چهارم ریکاوری + guard `AND status='running'` در job + 3 endpoint جدید (pause/resume/queue-summary) + `queue/paused/queue_control` در batch detail + normalize `out_dir` به `/` (Windows) |
| `backend/factory/service.py` (+23/−~3) | پارامتر اختیاری `on_stage` در `process()` + `_notify` پس از کامل شدن هر 8 stage (ترتیب قطعی)؛ بدون callback = رفتار دقیقاً مثل قبل |
| `backend/test_word_factory.py` (+42) | کلاس `TestOnStageCallback` (3 تست): ترتیب قطعی stageها، last-safe روی failure، invariance خروجی با/بدون callback |

**تغییرکرده (مستندات):** `readme.md` (ردیف قابلیت 8b، 8 test files/151
تست، endpointهای queue، جدول DB، نقشه‌ی راه)، `AGENTS.md` (دستور رگرسیون
151، فهرست تست‌ها، نقشه‌ی راه).

**وابستگی جدید: صفر.** (فقط کتابخانه‌های استاندارد `hashlib`/`os`/`time`)

## E. نتایج تست

| مجموعه | تعداد | نتیجه |
|---------|:-----:|:------:|
| هسته (api/projects/dashboard) | 39 | ✅ |
| knowledge_api (KB-01..KB-14) | 40 | ✅ |
| word_factory (WF-01..WF-13 + on_stage) | 27 | ✅ |
| dump (D01..D15) | 26 | ✅ |
| work_registry (RD-01..RD-07) | 10 | ✅ |
| **queue (Q-01..Q-08)** | **9** | ✅ |
| **کل** | **151** | ✅ سبز (55.4s) |

پوشش Q (همه E2E با pipeline واقعی Word Factory روی fixtures docx):

- **Q-01** — batch با good + corrupt + duplicate: 2 ردیف صف (dedup)،
  good → succeeded/stage=export/attempts=1/`out_dir` دقیق؛ corrupt →
  failed/stage=NULL/last_error؛ semantic plan (duplicate=sha ثبت‌شده).
- **Q-02** — pause پیش از process: 0 فایل پردازش می‌شود، job
  interrupted «[paused by user]»، بچ planned، همه ردیف‌ها pending/0
  attempts؛ resume + process → completion کامل.
- **Q-03** — شمارنده‌های `queue/summary` **یک‌به‌یک** با محاسبه مستقیم
  sqlite (همه کلیدها + failed_by_stage)؛ فیلتر کالکشن؛ 404 کالکشن
  ناخاص؛ 401 بدون auth.
- **Q-04** — شبیه‌سازی crash: ردیف job/صف/سند/بچ قدیمی (2h) + ردیف صف
  تازه (10s). ریکاوری: job interrupted، ردیف قدیمی pending **با حفظ
  stage**، ردیف تازه لمس‌نشده؛ `/process` → همان job، retry_count=1،
  attempts=2، بدون ردیف تکراری.
- **Q-05** — retry تکی فایل failed: attempts 1→2، stage NULL (bad-zip:
  هیچ stage ایمن کامل نشده)، last_error، sha ثابت؛ خروجی‌های فایل سالم
  **بایتی یکسان** (hash همه 5 فایل خروجی).
- **Q-06** — `generate_dump` + `validate_dump` روی `out_dir`
  پردازش‌شده از صف → ok=True، errors=[] (سازگاری کامل d-1).
- **Q-07** — سند needs_review (quality: متن کوتاه انگلیسی): ردیف صف
  needs_review + stage=export + job succeeded (تمایز صادقانه).
- **Q-08** — pause/resume روی بچ ناخاص → 404؛ کل endpointهای جدید
  بدون auth → 401.

اجرا (دوباره اجرا شد در 2026-10-29 برای این گزارش):

```bash
cd backend
python -m unittest test_queue -v
  # Ran 9 tests in 7.492s — OK
python -m unittest test_api test_projects test_dashboard \
  test_knowledge_api test_word_factory test_dump test_work_registry \
  test_queue -v
  # Ran 151 tests in 55.367s — OK
```

در مسیر توسعه، 5 کاستی در خود **تست/کد** پیدا و **اصلاح** شد (نه از
بین بردن assertion): (1) semantic plan — ورودی‌های از قبل ثبت‌شده
`duplicate` می‌شوند نه `pending`؛ (2) INSERT تستی با دو string-literal
جانب‌به‌جانب برای sha (SQLite آن‌ها را نمی‌چسباند) → پارامتری شد؛
(3) و (4) مسیر خروجی باید از ستون `out_dir` صف خوانده شود، نه محاسبه از
file_key (تفکیک هویت file_key vs factory file_id)؛ (5) client تستی
log-in‌شده برای چک 401 با client تازه جایگزین شد. به‌علاوه یک اصلاح
production کوچک: `out_dir` در ویندوز با backslash ذخیره می‌شد →
`.replace(os.sep, "/")` (ستون جدید، بدون تأثیر بر داده قدیمی).

## F. سازگاری (compat) — جدول خلاصه

| مورد | وضعیت |
|------|--------|
| endpointهای قدیمی knowledge (collection/document/batch/metadata/works) | بدون تغییر (تست‌های KB/RD سبز) |
| Word Factory CLI + خروجی‌ها (بدون callback) | **بایتی یکسان** (تست invariance) |
| قرارداد Dump `d-1` | **کاملا دست‌نخورده** (D01..D15 سبز + Q-06) |
| اکستنشن (`/api/projects*`) | دست‌نخورده (probe 200 روی s52) |
| auth PCM-09 | بدون تغییر؛ endpointهای جدید پشت auth (401 بدون cookie) |
| DBهای قدیمی | auto-migration افزایشی هنگام اولین request (IF NOT EXISTS) |
| ES | بدون تغییر (`compatibility` صادقانه `NOT VERIFIED`) |

## G. Git: commit و push

- **commit کد:** `dd0a800231177ceee61d3a46853def56f05948c9` (9 فایل،
  1577+ / 31−) — بعد از `519f98f`، push بدون force.
- **GitHub:** `https://github.com/saber13812002/persian-corpus-toolkit` —
  SHA commit کد با `git ls-remote` تأیید شده (بخش H).
- این گزارش (با ثبت SHA نهایی) در **commit دوم بلافاصله بعدی** ثبت
  می‌شود — همان رویه‌ی PCM-14C.3 / PCM-14D.
- قبل از commit: `git diff --check` → بدون whitespace error (فقط
  هشدارهای CRLF→LF پیشین)؛ secret scan روی 9 فایل → **0 hit**.

## H. وضعیت Local / GitHub / s52

| محیط | وضعیت |
|------|-------|
| Local | `main` = `dd0a800` (commit کد PCM-15)؛ working tree clean (بعد از commit گزارش) |
| GitHub | همگام با Local (`origin/main` = `dd0a800`؛ تأیید با `git ls-remote` — commit بعدی) |
| s52 | **pre-PCM-14D** — دست‌نخورده (هم PCM-14D هم PCM-15 روی s52 نیستند) |

نتیجه چک خواندنی s52 (اجرا شده 2026-10-29،
`ssh -p 22 saber@172.20.1.52 'bash -s' < deploy/pcm15_s52_readonly_check.sh`):

- container `persian-corpus-toolkit-backend-1` — **Up 46 hours**
  (image `147e985d…290f9ec`)؛ بدون restart.
- probes: `/api/stats` 200، `/api/projects` 200 (کراول زنده
  دست‌نخورده)، `/api/knowledge/collections` 401،
  `/api/knowledge/works` 404 (pre-14D)، `/api/knowledge/queue/summary`
  404 (pre-15، مطابق انتظار)، `POST .../batches/b-nope/pause` 404
  (pre-15)، `/api/dashboard/projects` 401، `/dashboard/studio.html` 200،
  `/api/auth/status` → `{"auth_enabled":true,"authenticated":false}`.
- کد s52: marker `knowledge_file_queue` غایب، `on_stage` غایب،
  `knowledge_works` غایب (pre-14D، مطابق گزارش PCM-14D)؛
  `knowledge_api.py` = 1781 خط، `service.py` = 149 خط،
  `test_queue.py` MISSING.
- DB production: `PRAGMA integrity_check` = **ok**؛ projects=6،
  auth_sessions=17، knowledge_collections=0،
  knowledge_collection_documents=0؛ جدول `knowledge_works` و
  `knowledge_file_queue` هر دو غایب (مطابق pre-14D).
- `.env` perms = 600 (محتوا هرگز چاپ نشده).

## I. تأیید عدم اختلال در production

- هیچ deploy، restart یا نوشتن روی s52 انجام **نشده** است (چک کاملاً
  read-only — خود اسکریپت در انتها این را اعلام می‌کند).
- کراول زنده (`/api/projects*`) دست‌نخورده — 200 در چک بالا.
- هیچ endpoint نوشتاری اکستنشن تغییر نکرده است (تست‌های api سبز).
- deploy آینده (فقط با دستور صریح + بکاپ): بکاپ `thesaurus.db` +
  integrity_check → اسنپ‌شات deploy dir → کپی کد →
  `docker compose build backend && docker compose up -d backend` →
  health-wait + smoke (چک خواندنی + 151 تست روی کپی /tmp).
  **توجه:** چون s52 هنوز pre-14D است، deploy PCM-15 واقعاً باید شامل
  PCM-14D هم باشد (کد 14D بخشی از همین main است) — مهاجرت 14D + 15
  هر دو افزایشی و idempotent هستند.

## J. محدودیت‌ها و ریسک‌ها

1. **هنوز deploy نشده** — مطابق قاعده مأموریت (بدون دستور صریح +
   بکاپ، deploy نمی‌شود).
2. s52 در pre-14D مانده است؛ پس deploy بعدی دو مهاجرت (14D + 15) را
   یکجا اعمال می‌کند (هر دو additive — ریسک کم، ولی در گزارش بعدی باید
   جداگانه smoke test شود).
3. retry «از وسط پایپ» (ادامه از stage نیمه‌کاره) عمداً پیاده نشده —
   اجرای idempotent مجدد روی ورودی ثابت از نظر نتیجه معادل است و
   صداقت‌آمیزتر است؛ ستون stage anchor ممیزی/ریکاوری را نگه می‌دارد.
4. pause فقط در مرز فایل (بین فایل‌ها) عمل می‌کند، نه وسط stage یک
   فایل.
5. `attempts`/`duration_ms` در reprocess‌های تکراری **جمع** می‌شوند
   (history، نه count آخرین اجرا) — در سند طراحی مستند است.
6. UI داشبورد (تصویرسازی صف + دکمه‌های pause/resume) جزو PCM-17 است.

## K. روش تست دستی (اپراتور)

```bash
cd backend
# 1) رگرسیون کامل
python -m unittest test_api test_projects test_dashboard \
  test_knowledge_api test_word_factory test_dump test_work_registry \
  test_queue -v
# 2) فقط صف
python -m unittest test_queue -v

# 3) آزمایش دستی روی server محلی (بعد از docker compose up -d):
#    - POST /api/auth/login {"password": "..."}  → cookie pct_session
#    - POST /api/knowledge/import/batches  (batch با چند فایل)
#    - POST /api/knowledge/import/batches/<b>/process
#    - GET  /api/knowledge/import/batches/<b>      → queue + paused + queue_control
#    - GET  /api/knowledge/queue/summary           → counters زنده
#    - POST /api/knowledge/import/batches/<b>/pause  → بعد از process در بچ بزرگ
#    - POST /api/knowledge/import/batches/<b>/resume
#    - POST /api/knowledge/documents/<d>/process   → retry تکی (attempts+1)
#    - kill -9 worker و restart → ریکاوری (running قدیمی → pending با حفظ stage)
```

## L. فاز بعد

- **PCM-16** — Corpus Builder: سازنده پیکره **فقط** از Dumpهای
  معتبر `d-1` (dedup، provenance، RAW/NORMALIZED جدا، خروجی نسخه‌دار
  JSONL+archive، idempotent، آمار واقعی، بسته‌بندی local HuggingFace —
  بدون انتشار عمومی بدون تأیید صریح مالک).

---

*این گزارش بخشی از مأموریت «ادامه PCM-14C تا تحویل پیکره» است؛ مستندات
فنی کامل در `docs/PCM-15-FILE-QUEUE.md` و قرارداد OpenAPI در
`docs/openapi/pcm15-file-queue.openapi.yaml`.*

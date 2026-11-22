# AGENTS.md — راهنمای کار روی persian-corpus-toolkit

این فایل قواعد دائمی برای هر کسی/هوش مصنوعی که روی این ریپازیتوری کار می‌کند.
قواعد زیر **مطلق** هستند و جزئیات مأموریت‌های تکی (PCM-01…PCM-10) به آن‌ها اضافه می‌شوند.

## ۱. محدوده‌ی مجاز (scope)

- **فقط** زیرسیستم پیکره: `backend/`, `dashboard/`, `extension/`, `corpus/`, `deploy/`, `docs/`.
- **هرگز** روی NotebookLM، RAG indexer (جزء زیرمجموعه‌ی دیگر)، یا QA Bank دست نزنید.
- هرگز DB production (`backend/thesaurus.db` روی s52) را خارج از بکاپ‌برده‌شده لمس نکنید.

## ۲. قواعد سخت (hard rules)

1. **بدون بکاپ، مهاجرت نمی‌شود** — قبل از هر تغییر schema:
   `sqlite3 thesaurus.db ".backup /home/saber/backups/thesaurus-<TS>.db"` + `PRAGMA integrity_check`.
2. **مهاجرت‌ها فقط افزایشی** (additive): `ALTER TABLE ... ADD COLUMN` + backfill + index.
   هیچ `DROP`/`RENAME`/تغییر نوع ستون در production.
3. **`docker compose down -v` ممنوع** — فقط `docker compose build backend && docker compose up -d backend`.
4. **هر مرحله: تست → commit → push → deploy → smoke test → گزارش.** بدون تست سبز، deploy نمی‌شود.
5. **رمز/توکن در کد، Git، لاگ، metric یا گزارش نمی‌آید.** رمز داشبورد فقط در
   `.env` سرور (gitignored، chmod 600) و در DB به‌صورت scrypt-hash.
6. **APIهای نوشتاری اکستنشن باز می‌مانند** (`/api/projects*`) — کراول زنده نباید با
   تغییرات داشبورد قطع شود. فقط namespace‌های خواندنی داشبورد (`/api/dashboard/*`) پشت auth.
7. SQL پارامتری‌شده (placeholder)؛ `ORDER BY` فقط از whitelist؛ `LIMIT/OFFSET` برای صفحه‌بندی —
   کل‌جدول‌بارگذاری در APIها ممنوع.
8. خروج‌های DOM در کلاینت از `escHtml` (XSS)؛ هیچ HTML خام بدون sanitize.
9. عدد آمار/درصد ساختگی ندهید — فقط شمارنده‌های واقعی DB، با تعریف مکتوب.

## ۳. دپلوی (s52 = 172.30.0.133 — IP جدید vCenter؛ 172.20.1.52 دیگر وجود ندارد)

```text
SSH:     ssh -p 22 saber@172.30.0.133          # 2222 = GitLab، نه SSH
DIR:     /home/saber/saberprojects/persian-corpus-toolkit   # کپی کد (نه git repo)
DB:      backend/thesaurus.db  (bind-mount به /data/thesaurus.db در container)
NGINX:   443 ssl → 127.0.0.1:5055 با X-Forwarded-Proto
BACKUP:  /home/saber/backups/  (thesaurus-<TS>.db + pct-deploy-<TS>.tar.gz)
```

مراحل استاندارد (نمونه: `deploy/pcm04_deploy.sh`):
1. بکاپ آنلاین DB + integrity_check
2. اسنپ‌شات deploy dir (بدون DB)
3. `.env` را تضمین کن (chmod 600)
4. کد جدید را extract کن
5. `docker compose build backend && docker compose up -d backend`
6. health-wait + smoke test (endpointهای کلیدی + چک auth)
7. integrity_check مجدد + شمارش‌ها (مقایسه با قبل)

## ۴. تست‌ها

```bash
cd backend && python -m unittest test_api test_projects test_dashboard \
  test_knowledge_api test_word_factory test_dump test_work_registry test_queue \
  test_corpus_builder test_studio_api test_api_contract -v \
  # 200 تست (رگرسیون کامل)
```

- **200 تست**: `test_api.py` (8، فاز۱/۲ + پروژه)، `test_projects.py` (9، جریان CRUD)،
  `test_dashboard.py` (22، auth A01-A08 + داشبورد D01-D07)، `test_knowledge_api.py`
  (40، KB-01..KB-14 — PCM-14B)، `test_word_factory.py` (27، WF-01..WF-13 + on_stage
  PCM-15)، `test_dump.py` (26، D01..D15 — قرارداد Dump `d-1`، PCM-14C.3)،
  `test_work_registry.py` (10، RD-01..RD-07 — Work Registry، PCM-14D)،
  `test_queue.py` (9، Q-01..Q-08 — صف پایدار فایل، PCM-15)،
  `test_corpus_builder.py` (24، C-01..C-16 — پیکره‌ساز `c-1`، PCM-16)،
  `test_studio_api.py` (7، S-01..S-04 — استودیو: فهرست بچ‌ها + paused +
  counters + رجیستری اسناد، PCM-17)، `test_api_contract.py` (18،
  CT-01..CT-06 — قرارداد OpenAPI spec ↔ app زنده، PCM-19).
- **PCM-12.3 (رفع F-01):** هر سه ماژول اول `import pct_test_support` می‌کنند که
  یک DB موقت **مشترک** می‌سازد و `PCT_DB`/`PCT_DASHBOARD_PASSWORD` را **قبل از**
  `import server` ست می‌کند؛ سپس هر کلاس در `setUp` با
  `pct_test_support.reset_db()` دیتابیس را از نو می‌سازد. این باعث می‌شود:
  - `server.DB_PATH` فقط به فایل موقت اشاره کند (هرگز `thesaurus.db` production)؛
  - rate-limit/session/state بین ماژول‌ها **نشت نکند**؛
  - ترتیب و ترکیب ماژول‌ها (انفرادی/ترکیبی/معکوس/تکراری/discovery) مهم نباشد.
- **قاعده:** هیچ ماژول تستی نباید خودش `PCT_DB` بسازد یا `server.init_db()`
  را مستقیم صدا بزند؛ همه از `pct_test_support.reset_db()` استفاده کنند.
- روی Windows: هر connection باید بسته شود (open handle مانع `os.remove` می‌شود) —
  `teardown_appcontext` این کار را برای درخواسته‌های داخل `with client:` انجام می‌دهد.
- اجرای آزمون روی s52 (بدون دست‌کاری production): `deploy/pcm12_3_s52_test.sh`
  (کپی backend در /tmp + python از .venv، با guard عدم اتصال به DB زنده).

## ۵. ساختار فنی

- Flask + SQLite (WAL) روی ۵۰۵۵؛ Docker Compose؛ اکستنشن Chrome MV3.
- `backend/server.py` — API اصلی + wiring · `projects.py` — پروژه/نقطه/صفحه ·
  `auth.py` — احراز هویت (PCM-09) · `dashboard_api.py` — API خواندنی داشبورد (PCM-04) ·
  `sites.py` — سایت‌های seed.
- `backend/factory/` — Word Factory (DOCX→JSONL، CLI، بدون DB/ES) + `dump.py`
  قرارداد رسمی Dump `d-1` (PCM-14C.3، سند: `docs/PCM-14C.3-DUMP-CONTRACT.md`).
- `knowledge_api.py` — Work Registry (PCM-14D): جدول‌های `knowledge_works`/
  `knowledge_editions`/`knowledge_volumes` + scopeهای `work/edition/volume` متادیتا
  + `/api/knowledge/metadata/resolve` (سند: `docs/PCM-14D-WORK-REGISTRY.md`).
- `docs/openapi/` — مشخصه‌های OpenAPI (PCM-14D + PCM-15؛ 19 operation) + راهنمای
  اپراتور (PCM-19) · `.gitlab-ci.yml` — CI فقط تست (رگرسیون 200 + چک OpenAPI +
  نمونه کلاینت؛ **بدون job deploy**؛ `deploy/pcm19_openapi_check.py`).
- داشبورد: HTML+JS تک‌صفحه‌ای بدون framework در `dashboard/index.html`؛ همه‌ی
  fetchها `credentials: same-origin` و 401 → overlay ورود.

## ۶. نقشه‌ی راه (ترتیب اجرا)

| فاز | وضعیت |
|-----|-------|
| PCM-01 رفع «پروژه ساخته نمی‌شود» | ✅ |
| PCM-02 برنامه و ممیزی | ✅ |
| PCM-03 deploy + ممیزی production | ✅ |
| **PCM-04** تب پروژه‌ها (فهرست/جزئیات/صفحه‌بندی) + **PCM-09** auth | ✅ (این دپلوی) |
| **PCM-05** مرور صفحه‌به‌صفحه / آیتم‌به‌آیتم | ⏳ |
| **PCM-06** نمای آمار واقعی | ⏳ |
| **PCM-07** ناوبری دوسویه + checkpoint/resume + کنترل Start/Pause/Resume/Retry | ⏳ |
| **PCM-08** موتور transform + reprocess | ⏳ |
| **PCM-10** health/metrics + ۴ داشبورد Grafana (زیرساخت موجود s52) | ⏳ |
| **PCM-12.2** آزمون پذیرش ۲۰ سناریو + ممیزی دسترسی s52 | ✅ (docs-only) |
| **PCM-12.3** اصلاح ریشه‌ای test isolation (F-01) + آزمون امنیتی Grafana | ✅ (test-harness + docs؛ بدون deploy) |
| **PCM-14B.3** Word Studio + پایگاه دانش + Word Factory (CLI) | ✅ (روی s52؛ 40+24 تست) |
| **PCM-14C.3** قرارداد رسمی Dump `d-1` + manifest `m-2` (ثبت policy نرمال‌سازی) + CLI dump | ✅ (26 تست D + 129 کامل؛ بدون deploy) |
| **PCM-14C.4** پذیرش عملی قرارداد Dump روی CLI واقعی (`deploy/pcm14c4_dump_acceptance.py`) | ✅ (ACCEPTANCE PASS؛ بدون deploy) |
| **PCM-14D** Work Registry: اثر←نسخه←جلد + scopeهای work/edition/volume + resolve + OpenAPI | ✅ (10 تست RD + 139 کامل؛ بدون deploy) |
| **PCM-15** صف پایدار پردازش فایل: `knowledge_file_queue`/`knowledge_queue_control` + `on_stage` factory + pause/resume/summary + ریکاوری با حفظ stage + سازگاری Dump d-1 | ✅ (9 تست Q + 151 کامل؛ بدون deploy) |
| **PCM-16** پیکره‌ساز از Dumpهای معتبر d-1: قرارداد `c-1` — جریان‌های جدا RAW/NORMALIZED + provenance + dedup + آرشیو قطعی + پکیج محلی HF + CLI `build-corpus` (بدون DB/ES/شبکه) | ✅ (24 تست C + 175 کامل؛ بدون deploy؛ سند: docs/PCM-16-CORPUS-BUILDER.md) |
| **PCM-17** تکمیل UI استودیو: کارت صف/بچ‌ها (شمارنده‌های زنده + process/pause/resume) + کارت رجیستری اثر‌ها + `GET /api/knowledge/import/batches` (افزایشی) + ستون رجیستری اسناد | ✅ (7 تست S + 182 کامل؛ بدون deploy؛ سند: docs/PCM-17-STUDIO-UI.md) |
| **PCM-18** ممیزی observability روی s52: اسکریپت خواندنی + گزارش (اجرای s52 مسدود — host unreachable) | ✅ (اسکریپت + گزارش؛ بدون deploy؛ اجرای s52 در انتظار دسترسی) |
| **PCM-19** قرارداد API: تست‌های CT-01..CT-06 (200 کامل) + به‌روزرسانی README/AGENTS/OpenAPI + GitLab CI test-only + نمونه کلاینت REST + چک‌کن OpenAPI | ✅ (18 تست CT؛ بدون deploy؛ سند: docs/openapi/README.md) |
| **PCM-20** خروجی کامل JSON پیکره‌ی «تفسیر تسنیم» + ممیزی شماره صفحه (`deploy/pcm20_tasnim_export.py`) | ✅ (read-only روی سرور: 45,844 سند / 73MB؛ بدون deploy) |
| **PCM-20.2** ممیزی عمیق خروجی واقعی + تطبیق با AI Dump Builder (`deploy/pcm20_2_tasnim_audit.py`) | ✅ (باگ parse_barg اثبات شد؛ adapter بدون تغییر کد Builder ممکن است؛ بدون deploy) |
| **PCM-20.3** Tasnim Corpus Factory: `corpus/tasnim/` (13 ماژول) + 16 تست T — audit gate + پیکره‌ی canonical (RAW/NORMALIZED جدا) + V01–V08 + dataset‌های 1/10/50/90/100 + adapter Dump سازگار با builder + diff + زنجیره‌ی manifest/provenance (immutable، append-only) | ✅ (16 تست + رگرسیون کامل 200؛ بدون deploy؛ سند: docs/PCM-20.3-TASNIM-FORFACTORY.md؛ embedding/Neo4j = مأموریت بعدی) |
| **PCM-20.4** پذیرش واقعی end-to-end تسنیم: snapshot واقعی 45,844 صفحه (SHA verify + GATE 1.5 truncation) → پیکره‌ی canonical v0001 → 6 دیتاست نسخه‌شده (شامل 1 جلد + fixture افزایشی با diff/immutable) → 3 خروجی Dump + **3 build واقعی ai-dump-builder** (mock embedding؛ بدون LiteLLM/Neo4j/collection عملیاتی) + زنجیره‌ی registry 17-entry + 216 تست سبز (200 رگرسیون + 16 T؛ 0 skip) | ✅ (acceptance PASS؛ بدون deploy؛ سند: docs/PCM-20.4-TASNIM-ACCEPTANCE.md؛ embedding/Neo4j واقعی = PCM-20.5) |
| **PCM-20.10** حد عددی توقف کراول + ممیزی کامل‌بودن: `stop_number` در projects (مهاجرت افزایشی + UI «حد عددی توقف» + چک قبل از هر صفحه در crawl loop — توقف تمیز با `paused` + release قفل) + اسکریپت read-only ممیزی gap/کیفیت/تکرار روی API زنده `deploy/pcm2010_crawl_gap_audit.py` (گپ‌ها به‌صورت بازه، صفحات ناقص/کوچک، payloadهای تکراری، وضعیت قفل run، اثبات کامل با `--expect-max N`) | ✅ (18 تست جدید SN-01..06 + 12 stop-rule؛ رگرسیون 206 سبز؛ **deploy شد 2026-11-20** روی s52 جدید 172.30.0.133) |
| **PCM-EXT-03** قفل cross-browser اجرای تکی: lease روی backend (claim/heartbeat/release + TTL 180s) + panel «در حال خواندن (دستگاه دیگر)» + 404-fallback v3.7 | ✅ (14 تست RL + اکستنشن v3.8؛ **deploy شد 2026-11-20**؛ سند: گزارش-PCM-EXT-03.md) |
| **PCM-EXT-04** توقف بر مبنای تکرار محتوا: ۱۰ صفحهٔ یکسان → stop + فیلد مبنای محتوا `stop_field` (خودکار=کل محتوا یا یک فیلد) + select در پنل + اکستنشن v3.9 | ✅ (14 تست extension + 8 تست SF + رگرسیون 228 سبز؛ **deploy شد 2026-11-20**؛ سند: docs/گزارش-PCM-EXT-04.md) |
| **PCM-EXT-05** Ghaemiyeh Book Collector: اکستنشن MV3 جدا `extension-ghaemiyeh/` (trace دسته‌بندی + دانلود گروهی DOCX + آپلود به کالکشن؛ auth از طریق کوکی `pct_session`) + 8 تست G (pipeline خالص با deps تزریقی) | ✅ (8 تست G + رگرسیون 226 سبز؛ بدون deploy — نصب load-unpacked؛ سند: docs/گزارش-PCM-EXT-05.md) |
| **PCM-EXT-06** کراول سال‌به‌سال بیانات (farsi.khamenei.ir): ریشه‌ی مشکل = سایت `?page=N` را نادیده می‌گیرد و هر سال جلالی = یک صفحهٔ کامل لیست (`/speech?nt=2&year=Y`، ۱۳۷۹–۱۴۰۴)؛ اسکریپت `corpus/scrape_khamenei.py` با discovery تک‌درخواستی سال‌به‌سال + auto year-walk (بدون hijack صف pending برای run سال‌محور) + اکستنشن فاز۱ با state machine `nextKhameneiYear` (مستقل از `?page=`) + content-script کشف فقط anchorهای دارای تاریخ + `maxYear` | ✅ (13 تست Python + 8 تست node سال‌walk + 61+8 رگرسیون اکستنشن + 226 رگرسیون backend سبز؛ e2e واقعی: ۱۴۰۰(35) + ۱۴۰۲(56) = 91 بیان با متن کامل + تاریخ در DB؛ بدون deploy) |
| **PCM-EXT-08** «آیه بعد» در SPAهای hash-based (تفسیر نور/گرااتی): روش پنجم «صفحه بعد» با مقدار `next_param='hash'` — content script دکمهٔ `<input onclick="viewer(S,A)" value="آیه بعد">` را پیدا و آدرس `#numsooreh=S&numayeh=A` می‌سازد + **حفظ hash در آدرس** (backend دیگر `#` را از start_url/صفحه/cursor نمی‌تراشد؛ هر آیّه = صفحهٔ جدا با dedup درست) + `hashNumber` (سوره×10000+entry) برای حد عددی توقف + منبع نقطهٔ `hash_param` (خواندن numsooreh/numayeh از hash) + تبدیل `src_attr` (آدرس مطلق src — برای mp3 `archive/tafsir/{S}/{A}.mp3` که A = شمارهٔ آیّهٔ نمایشی، نه numayeh) + صبر AJAX بعد از `complete` | ✅ (10 تست hash در test_next.js + 9 تست DOM در test_hash_next.js + 6 تست HU در test_projects.py + رگرسیون سبز؛ بدون deploy — نصب load-unpacked؛ سند: docs/EXT-NEXT-PAGE-METHODS.md) |
| **PCM-STUDIO-BATCH** عملیات گروهی کتابخانهٔ Word استودیو: `POST .../documents/process-all` (job `process_collection` روی همهٔ uploaded/failed — mirror worker بچ‌ها + idempotency + resume با force_retry) + `POST .../documents/pause` (scope `collection:<id>`، توقف تمیز بعد از سند جاری) + `POST .../documents/approve-all` (UPDATE اتمیک parsed/needs_review→approved + audit `approved_all`) + کلید افزایشی `status_counts` در لیست اسناد + ۳ دکمهٔ toolbar با شمارندهٔ زندهٔ سمت‌سرور + OpenAPI (3 operation جدید، spec pcm15 = 8 op) | ✅ (11 تست S-05..S-11 + رگرسیون 243 سبز؛ بدون deploy — سوار درِ M7؛ سند: docs/PCM-STUDIO-BATCH-REPORT.md) |

گزارش‌ها: `گزارش-PCM-0X.md` (۱۱ بخش: وضعیت قبل، طراحی، مهاجرت، فایل/API، تست،
نتیجه production، SHA+لینک، git status، بکاپ/rollback، موارد باقی‌مانده، روش تست دستی).

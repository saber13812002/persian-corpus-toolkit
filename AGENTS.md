# AGENTS.md — راهنمای کار روی persian-corpus-toolkit

این فایل قواعد دائمی برای هر کسی/هوش مصنوعی که روی این ریپازیتوری کار می‌کند.
قواعد زیر **مطلق** هستند و جزئیات مأموریت‌های تکی (PCM-01…PCM-10) به آن‌ها اضافه می‌شوند.

## ۱. محدوده‌ی مجاز (scope)

- **فقط** زیرسیستم پیکره: `backend/`, `dashboard/`, `extension/`, `corpus/`, `deploy/`, `docs/`, `tasnim/`.
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
10. **read model‌های Tasnim اشیای immutable/نسخه‌شده‌اند** — هر نسخه یک دایرکتوری
    مستقل (`tasnim/data/readmodel/vNNNN/`) است؛ بعد از انتشار، هیچ تغییری در `v0003`
    و بعدش نمی‌شود؛ نسخهٔ جدید = دایرکتوری جدید + `build.sha256` جدید. دایرکتوری‌های
    `tasnim/data/` و `data/` gitignored‌اند (بکاپ/بازیابی: `docs/tasnim/BACKUP-RESTORE.md`).
11. **context پنهان هرگز خارج نمی‌شود (HP-1):** `hidden-context-records.jsonl` و
    `context-records.jsonl` در read model/API/UI ممنوع‌اند — 4 لایهٔ محافظ: builder
    guard + `strict_pick` (whitelist در serializer) + تست‌های T-HC-1..4 + canary در
    چک 15 smoke؛ فیلد تازه باید به whitelist اضافه شود.
12. **کلیدهای دادهٔ Tasnim ثابت‌اند:** `page_id` کلید منحصربه‌فرد صفحه و `item_index`
    کلید ترتیب است (barg فقط نمایشی و ممکن است null باشد)؛ coverها SVG placeholder
    با شمارهٔ واقعی جلد‌اند — عکس/کاور جعلی بارگذاری نمی‌شود.
13. **پورت‌ها و نام‌های رزرو:** 5070 (nginx) و 5071 (API) + نام containerهای
    `tasnim-*` فقط برای زیرسیستم تسنیم (مطابق `docs/tasnim/DEPLOYMENT.md`).
14. **بازیابی صفحات گمشده (Gate B) فقط با تأیید صریح انسان:** `BACKFILL_APPROVED=approved`
    + runbook (`docs/tasnim/OPS-RUNBOOK.md`)؛ policy bf-2 (PCM-20.6.3)؛ اجرای زنده فقط روی s52.

## ۳. دپلوی (s52 = 172.20.1.52)

```text
SSH:     ssh -p 22 saber@172.20.1.52          # 2222 = GitLab، نه SSH
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
- **Tasnim Web V1 (PCM-20.6.4):** `tasnim/web/` — اپ Flask+Jinja (SSR، RTL) روی
  read model نسخه‌شده: 12 endpoint خواندنی `/api/v1/tasnim/...` + FTS5 (`tokenize_fa/1.0`)
  + OpenAPI 3.1 · `tasnim/web/build_cli.py` — builder read model (HP-1؛ بدون DB/ES/شبکه) ·
  `tasnim/e2e/` — smoke 15-item + E2E · `tasnim/sdk/{python,javascript}` — SDKهای بدون
  وابستگی · `tasnim/{Dockerfile,docker-compose.tasnim.yml,nginx/tasnim.conf}` ·
  مستندات: `docs/tasnim/INDEX.md` (15 سند) + `docs/PCM-20.6.4-ARCHITECTURE.md`.

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
| **PCM-20.6.3** backfill صفحات گمشده: policy bf-2 + `corpus/tasnim/backfill/` (gap-report/plan/run) + 28 تست BF01–BF22b (audit gate؛ بدون اجرای زنده) | ✅ طراحی/READY_FOR_APPROVAL (اجرا در انتظار تأیید صریح انسان؛ s52 آفلاین؛ 45,243 صفحه ≈ 188.5 ساعت) |
| **PCM-20.6.4** Tasnim Web V1 — کتابخانه‌ی دیجیتال: read model v0003 (immutable/نسخه‌شده) + SSR/RTL + 12 endpoint خواندنی + FTS5 فارسی + OpenAPI 3.1 + SDK Python/JS + استک nginx/Docker + smoke 15-item + 15 سند `docs/tasnim/` | ✅ V1 تحویل‌شده (296 تست: 293 سبز + 3 skip داده‌ای؛ اجرای مستقیم تأیید شده؛ provision دامنه/اجرای Docker/GitLab در انتظار) |

گزارش‌ها: `گزارش-PCM-0X.md` (۱۱ بخش: وضعیت قبل، طراحی، مهاجرت، فایل/API، تست،
نتیجه production، SHA+لینک، git status، بکاپ/rollback، موارد باقی‌مانده، روش تست دستی).

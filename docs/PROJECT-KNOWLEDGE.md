# PROJECT-KNOWLEDGE — دانش‌نامه‌ی ماندگار پروژه (برای سشن‌های بعدی)

> **هدف این سند:** در هر سشن جدید، خواندن همین فایل کافی است تا بدون دوباره‌خواندن کل
> ریپازیتوری، به کل نقشه‌ی سورس، اهداف، تاریخچه‌ی مأموریت‌ها، اعداد رسمی، سرورها،
> تست‌ها، deploy و موارد باز دسترسی داشته باشید.
> **تاریخ تدوین:** ۲۰۲۶-۱۱-۱۰ (بررسی کامل repo؛ snapshot وضعیت: `pcm-20.6` @ `20911d7` +
> worktree `pcm-20.6-tasnim-web-v1` @ `d03fb51`).
> **تکمیل‌شده با:** readme.md، AGENTS.md، docker-compose.yml، docs/PCM-20.6-BASELINE.md،
> docs/PCM-20.6-CORPUS-V0003.md، گزارش‌های PCM-20.6.4/20.7C/20.7D (از branch web-v1)،
> اسکن کامل backend/ + corpus/ + extension/ + deploy/ + .gitlab-ci.yml + data/tasnim.

---

## ۱. پروژه چیست (یک‌نفس)

**Persian Corpus Toolkit (پیکره‌ساز فارسی)** — زنجیره‌ی کامل:
`کراول وب‌سایت‌های فارسی (اکستنشن Chrome MV3) → SQLite (Flask، port 5055) → پیکره‌سازی
نسخه‌ای (corpus/tasnim) → Dump سازگار با ai-dump-builder → RAG (Neo4j + vLLM)`.

- production پلتفرم: `https://corpus.ai.ismc.ir` (سرور s52 — فعلاً OFFLINE)
- production RAG تسنیم: روی s53 (زنجیره‌ی ۵۳ زنده، ingress 172.30.0.133 → `rag.ai.ismc.ir`)
- GitHub (origin, primary): `saber13812002/persian-corpus-toolkit`
- لایسنس: CC BY-NC-SA 4.0
- دامنه‌های مرتبط: `tasnim.hamtaa.org` (منبع پیکره‌ی «تفسیر تسنیم» — target کراول/بک‌فیل)،
  `tasnim.ai.ismc.ir` (برای Web V1 — هنوز vhost ندارد)، `rag.ai.ismc.ir` (زنده)،
  `docs.ai.ismc.ir` (Wiki.js؛ REST v2 غیرفعال)

### ارکیتکچر کلی

```text
[Chrome Extension MV3 v3.5]        [Flask backend :5055]              [Pipeline آفلاین]
 background.js (chrome.alarms,      server.py (API اصلی + wiring)      corpus/tasnim/ (CLI)
 SHA-256 dedup, cursor resume)      projects.py, sites.py              audit → build-corpus
 content_thesaurus/khamenei.js      auth.py (scrypt + cookie)          → build-semantic
 content_picker.js (نقطه‌چین‌کن)     dashboard_api.py (خواندنی, auth)  → build-dataset
 popup.html/js                      knowledge_api.py (Word Studio/KB/  → export-dump
       │                             Work Registry/Queue)               → diff / semantic-diff
       ▼                              │                                 │
 [SQLite WAL: thesaurus.db]           ▼                                 ▼
                                      dashboard/index.html          data/tasnim/<root>/
                                      dashboard/studio.html         (corpus/datasets/dumps/
                                      extension/ (MV3)              manifests/reports/...)
```

---

## ۲. نقشه‌ی دقیق درخت‌فایل‌ها (چه کجاست)

### ریشه‌ی repo
| مسیر | توضیح |
|---|---|
| `readme.md` | مستند اصلی (۴۰۸ سطر): امکانات، APIها، جدول‌های DB، roadmap |
| `AGENTS.md` | **قواعد مطلق** (scope، hard rules، deploy، تست‌ها، roadmap) — حتماً بخوان |
| `docker-compose.yml` | backend: `127.0.0.1:5055:5055`، `PCT_DB=/data/thesaurus.db` (bind `./backend/thesaurus.db`)، `PCT_DASHBOARD_PASSWORD` از `.env` (gitignored) |
| `.gitlab-ci.yml` | CI **فقط تست** (test-only): regression + openapi + client — بدون job deploy (قاعده‌ی AGENTS) |
| `گزارش-PCM-0X.md` (ریشه) | گزارش‌های فارسی هر مأموریت (۱۱ بخش استاندارد) |

### `backend/` (Flask + SQLite، ~۶۰KB server.py + ۱۳۴KB knowledge_api.py)
| فایل | نقش |
|---|---|
| `server.py` | API اصلی: phase1/seed-batch، phase2/next-batch·complete·complete-batch، next-job، submit-result، discover-links، page-content، thesaurus/* (sciences, elastic-harvest, elastic-status, recent)، khamenei/* (stats, reset, crawl-status, pending, mark-done, recent, submit, seed)، stats، queue، db/info، corpus/list، reset-queue، seed-categories، `GET /` و `/dashboard` |
| `projects.py` | پروژه v3.5: `/api/projects` CRUD + points + pages + report — **APIهای نوشتاری باز می‌مانند** (قاعده ۶) |
| `sites.py` | سایت‌های seed + `/api/sites`، `/match`، `/fields`، `/api/captures` |
| `auth.py` | PCM-09: `/api/auth/login` (scrypt) + `logout` + `status`؛ cookie HttpOnly `pct_session`؛ decorator `@require_auth` |
| `dashboard_api.py` | `/api/dashboard/projects[/<id>[/pages[/<page_id>]]]` — فقط خواندنی، همه `@require_auth` |
| `knowledge_api.py` | Word Studio + KB: collections، subjects، documents (structure/quality/blocks/file/process/approve)، import/batches (process/pause/resume)، queue/summary، metadata/fields·values·resolve، jobs، **Work Registry** (works/editions/volumes + resolve + compatibility) — همه `@require_auth` |
| `sciences.py` | داده‌های کمکی (علوم) |
| `factory/` | **Word Factory** (DOCX→JSONL، CLI، بدون DB/ES): cli, intake, parser, normalize, structure, quality, metadata, models, service, export, dump (قرارداد `d-1`), corpus (قرارداد `c-1`), validator, errors, _smoke_fixtures |
| `pct_test_support.py` | **Bootstrap تست**: DB موقت مشترک + `PCT_DB`/`PCT_DASHBOARD_PASSWORD` قبل از import server + `reset_db()` — قاعده: هیچ تستی خودش DB نسازد |
| `test_*.py` (۱۰ ماژول) | رگرسیون ۲۰۰ — جدول شمارش‌ها در §۶ |
| `Dockerfile`, `requirements.txt` | بیلد backend |

### `corpus/` (لایه‌ی پیکره‌سازی — آفلاین، بدون DB/ES/شبکه)
| فایل/پوشه | نقش |
|---|---|
| `pipeline.py`, `build_corpus.py`, `build_dataset.py`, `upload_to_hf.py`, `scrape_khamenei.py` | legacy: خط کهن‌تر (خامنیه/thesaurus) |
| `tasnim/__init__.py` | package |
| `tasnim/cli.py` (575 سطر) | CLI با ۸ زیردستور: `audit`، `build-corpus`، `build-semantic`، `validate-corpus`، `build-dataset`، `export-dump`، `diff`، `semantic-diff`. exit code: 0=mokhalef/REUSED, 1=خطای اجرا/validate, 2=خطای ورودی. ورودی‌ها read-only؛ خروجی زیر `data/tasnim` |
| `tasnim/common.py` | مسیرهای root، ثابت‌ها |
| `tasnim/reconcile.py` | load_source + `gate_report` (GATE 1/1.5) |
| `tasnim/transform.py`, `normalize.py` | RAW + NORMALIZED flows (جدا) |
| `tasnim/schema.py` | قرارداد رکورد |
| `tasnim/validate.py` | V01–V09 (corpus) + S01–S10 (semantic) |
| `tasnim/versioning.py` | registry + chain (immutable، append-only) |
| `tasnim/manifest.py` | manifest `m-2` (policy نرمال‌سازی ثبت می‌شود) |
| `tasnim/dataset.py` | دیتاست‌های ۱/۱۰/۵۰/۹۰/۱۰۰٪ — stratified-even-blocks، قطعی + `--volume N` |
| `tasnim/dump.py` | قرارداد رسمی Dump `d-1` (سند: [PCM-14C.3-DUMP-CONTRACT.md](docs/PCM-14C.3-DUMP-CONTRACT.md)) |
| `tasnim/diff.py` | Change Manifest بین دو نسخه |
| `tasnim/semantic.py` (59KB) | لایه‌ی معنایی: cs-20.5 (v0002) → cs-20.6 (v0003: HeadingRecord + hidden context + metadata truncation 2000) → cs-20.7 (v0004: LLM next-page summaries، leakage-gated) |
| `tasnim/gap_report.py` | D2/PCM-20.6: گپ صفحه‌های موجود در سایت ولی غایب از snapshot (45,243 صفحه در 6 range) — 8 تست G01–G05 |
| `tasnim/truncation_report.py` | D3/PCM-20.6: ۲۸ صفحه‌ی cap-2000 (0.06٪)؛ سقف سمت‌منبع — 5 تست TR01–TR04 |
| `tasnim/semantic.py` (web-v1) | + enrichment cs-20.7 (v0004) |
| `tasnim/backfill/` (فقط branch web-v1، ۹ ماژول، ۱۵ مرحله) | خط بک‌فیل 45,243 صفحه — dual guard: env `BACKFILL_APPROVED=approved` + flag `--allow-live` (**Gate B = تأیید صریح انسانی**) |
| `tasnim/enrich.py` (فقط web-v1، 601 سطر) | غنی‌سازی LLM: 5,867 رکورد (5,816 تولیدی، 0 failure، ~3.54h) با `/models/Qwen3.8-27B-FP8`، prompt `hc-prompt/1.0` |

### `tasnim/` (فقط branch `pcm-20.6-tasnim-web-v1` — پلتفرم وب V1)
- `web/api.py` (1198) — Flask `/api/v1/tasnim` (12 endpoint GET، RFC-7807، ETag/304، صفحه‌بندی cursor، rate-limiter in-process)
- `web/readmodel.py` (934) — SQLite FTS5: 12 جدول، `tasnim_readmodel.db` = 260,816,896 B (SHA `353f413b…`)
- `web/pages.py` (804) + `web/ssr.py` — SSR پلتفرم خواندن RTL (9 route)
- `web/openapi.py` (428) + 12 template + فونت Vazirmatn/Noto
- `sdk/python` + `sdk/javascript` — SDKهای رسمی (23/23 + 22/22 تست)
- `e2e/` — E2E (12/12)
- ایزوله‌سازی hidden context: **HP-1 چهارلایه + canary**
- `design-system/tasnim-web/MASTER.md`

### `dashboard/`
- `index.html` — داشبورد تک‌صفحه‌ای (فهرست/جزئیات/صفحات پروژه‌ها + آمار + استودیو؛ همه fetch با `credentials: same-origin`، 401→overlay ورود)
- `studio.html` — Word Studio (PCM-14B.3/17): کارت صف/بچ‌ها (شمارنده‌های زنده + process/pause/resume) + کارت رجیستری اثر‌ها + رجیستری اسناد

### `extension/` (Chrome MV3 v3.5 «Persian Corpus Crawler»)
- `manifest.json`: permissions `activeTab, storage, scripting, tabs, alarms`؛ host: thesaurus.eiis.iki.ac.ir، farsi.khamenei.ir، corpus.ai.ismc.ir، tasnim.hamtaa.org، `<all_urls>`
- `background.js` — minute-loop با `chrome.alarms`، dedup SHA-256، resume با cursor
- `content_thesaurus.js` / `content_khamenei.js` — استخراج‌گر‌های per-site
- `content_picker.js` — انتخاب نقاط روی صفحه (all urls)
- `popup.html/js`, `shared.js`, `test_popup.js`

### `deploy/` (اسکریپت‌های s52/ممیزی — همه read-only یا deploy دستی)
- deploy استاندارد: `pcm03_deploy.sh`, `pcm04_deploy.sh`, `pcm05_deploy.sh`, `pcm14a_deploy.sh`, `pcm14b_deploy.sh`
- acceptance/audit: `pcm12_2_*.sh`, `pcm12_3_*.sh`, `pcm14b3_*.sh`, `pcm14c*_remote.sh`, `pcm14d/15/16/17_s52_readonly_check.sh`, `pcm18_s52_observability_audit.sh`
- OpenAPI/کلاینت: `pcm19_openapi_check.py`, `pcm19_rest_client_sample.py` (stdlib-only)
- تسنیم: `pcm20_tasnim_export.py` (خروجی 45,844 صفحه), `pcm20_2_tasnim_audit.py`, `pcm206_hc_pilot.py` (پایلوت D4)
- nginx: `nginx-corpus.vhost.conf`, `nginx-corpus.http.conf`؛ systemd: `persian-corpus.service`

### `docs/`
- `PCM-12-*` (PRD، ARCHITECTURE، AUDIT، DATA-CONTRACTS، ROADMAP، ACCEPTANCE، HANDOFF، CHECKLIST)
- `PCM-12.3-TEST-ISOLATION.md` (رفع F-01)، `PCM-13-ACCEPTANCE.md`
- `PCM-14C.3-DUMP-CONTRACT.md`، `PCM-14D-WORK-REGISTRY.md`، `PCM-15-FILE-QUEUE.md`، `PCM-16-CORPUS-BUILDER.md`، `PCM-17-STUDIO-UI.md`
- `PCM-20.3-TASNIM-FORFACTORY.md`، `PCM-20.4-TASNIM-ACCEPTANCE.md`، `PCM-20.6-BASELINE.md`، `PCM-20.6-CORPUS-V0003.md`، `PCM-20.6.0-RECON.md`
- `dashboard-authentication.md`، `project-dashboard.md`، `WORD-FACTORY-USER-GUIDE.md`، `WORD-STUDIO-KNOWLEDGE-GUIDE.md`
- `openapi/`: README + 2 spec (PCM-14D work registry، PCM-15 file queue؛ 19 operation)
- **فقط روی branch web-v1:** 15 سند `PCM-20.7*.md` + 14 سند `docs/tasnim/*.md` (گزارش Web V1، architecture Phase D، EMBEDDING/NEO4J-LOADER/RAG-INTEGRATION)

### `data/tasnim/` (خروجی‌های محلی — gitignored)
| ریشه | محتوا |
|---|---|
| `pcm20_4/` | source-snapshot/، corpus/ (v0001)، datasets/، dumps/، manifests/، reports/، sources/，validation/،builder-input/ |
| `pcm20_5/` | corpus/، datasets/، full/، manifests/، pilot/، reports/، sources/ |
| `pcm20_5_crossroot/` | آزمایش cross-root |
| `pcm20_6/` | `pilot/hc-pilot.json` (پایلوت D4) |
| `pcm20_7d/` | `tasnim-v0004-export.json` + report (خروجی Phase D) |

---

## ۳. وضعیت Git (snapshot ۲۰۲۶-۱۱-۱۰)

| ref | commit | وضعیت |
|---|---|---|
| `pcm-20.6` (این workspace) | `20911d7` | HEAD فعلی؛ آخرین: D1–D4 + گزارش‌ها |
| `main` | `11233e9` | ۱ commit **پیش از** `origin/main` (`f314de5`) — commit «GATE 1 PCM-20.5 PASS» **push نشده** |
| `pcm-20.6-tasnim-web-v1` | `d03fb51` | worktree: `C:/Users/s.tabatabaei/Documents/saberprojects/pcm-20.6-tasnim-web-v1`؛ با origin هم‌سنجیده (push شده) |
| origin (GitHub) | — | primary remote؛ GitLab s52:2222 **unreachable** (s52 offline) |

**نکته‌ی حیاتی:** جدیدترین کارها (PCM-20.6.3 backfill-readiness، **20.6.4 Web V1**، 20.7A deploy،
20.7B TLS، **20.7C enrichment v0004**، **20.7D RAG production**) روی `pcm-20.6-tasnim-web-v1`
(109 فایل، +25,753 سطر نسبت به این شاخه) هستند و در این workspace **نمی‌بینید**. برای
دسترسی: `git show pcm-20.6-tasnim-web-v1:<path>` یا رفتن به worktree.

**Hygiene (باز):** در index شاخه‌ی `pcm-20.6` حدود **183 فایل `.tmp_*` staged** هستند (از
اجراهای PCM-20.4/20.5/20.6/20.7A-C در ریشه) + 4 فایل tmp untracked. قبل از هر commit جدی،
`git restore --staged .tmp_*` یا حذف فیزیکی لازم است. `.gitignore` پوشش نمی‌دهد.

**repoهای خارجی مرتبط (خارج از GitHub):**
- `graph-rag` (زنجیره‌ی RAG): branch `pcm-20.7d-tasnim-loader` (`e094483`+`498e0b0`) push به `git.ai.ismc.ir` از طریق relay روی 53
- `_aidump` (ai-dump-builder): branch `pcm-20.7d-embed-identity` (`9617707`+`f2a6404`) — بدون remote

---

## ۴. تاریخچه‌ی مأموریت‌ها (PCM-01 → PCM-20.7D)

| مأموریت | خلاصه | وضعیت |
|---|---|---|
| PCM-01..03 | رفع «پروژه ساخته نمی‌شود»، برنامه/ممیزی، deploy+ممیزی production | ✅ |
| **PCM-04 + PCM-09** | تب پروژه‌ها (فهرست/جزئیات/صفحه‌بندی) + auth داشبورد | ✅ (production) |
| PCM-05..08 | مرور صفحه‌به‌صفحه، آمار واقعی، ناوبری دوسویه+checkpoint، موتور transform | ⏳ (roadmap) |
| PCM-10 | health/metrics + 4 داشبورد Grafana | ⏳ |
| PCM-12.2/12.3 | 20 سناریوی پذیرش + test isolation (F-01) | ✅ |
| **PCM-14B.3** | Word Studio + پایگاه دانش + Word Factory | ✅ (s52؛ 40+24 تست) |
| **PCM-14C.3** | قرارداد Dump `d-1` + manifest `m-2` + CLI | ✅ (26 تست D) |
| **PCM-14C.4** | پذیرش Dump روی CLI واقعی | ✅ (ACCEPTANCE PASS) |
| **PCM-14D** | Work Registry (اثر←نسخه←جلد) + resolve + OpenAPI | ✅ (10 تست RD) |
| **PCM-15** | صف پایدار `knowledge_file_queue` + pause/resume | ✅ (9 تست Q) |
| **PCM-16** | پیکره‌ساز از Dumpهای معتبر (قرارداد `c-1`) | ✅ (24 تست C) |
| **PCM-17** | تکمیل UI استودیو + `GET import/batches` | ✅ (7 تست S) |
| PCM-18 | ممیزی observability s52 | ✅ (اسکریپت+گزارش؛ اجرای s52 مسدود) |
| **PCM-19** | قرارداد API: CT-01..CT-06 + CI test-only + sample client | ✅ (18 تست CT) |
| **PCM-20** | خروجی JSON کامل «تفسیر تسنیم» 45,844 سند/73MB | ✅ (read-only روی سرور) |
| **PCM-20.2** | ممیزی عمیق خروجی + تطبیق با AI Dump Builder (باگ parse_barg اثبات شد) | ✅ |
| **PCM-20.3** | Tasnim Corpus Factory: 13 ماژول + 16 تست T + canonical + datasets + adapter | ✅ |
| **PCM-20.4** | پذیرش E2E: snapshot واقعی → v0001 → 6 دیتaset → 3 Dump → 3 build واقعی ai-dump-builder (mock embedding) | ✅ (216 تست سبز) |
| **PCM-20.5** | semantic v0002 (cs-20.5: context records) + GATE 1 (offline) | ✅ (commit `11233e9` روی main — push نشده) |
| **PCM-20.6** | baseline 2026-11-06 + v0003 (cs-20.6) + gap/truncation reports + pilot D4 | ✅ روی `pcm-20.6` |
| **PCM-20.6.3** | backfill readiness (9 ماژول، design + dual guard) | ✅ (فقط web-v1) |
| **PCM-20.6.4** | **Tasnim Web V1**: read model FTS5 + API + SSR + SDK + 296 تست + 6 commit | ✅ (فقط web-v1؛ deploy/Docker BLOCKED در این host) |
| **PCM-20.7A** | deploy prep Web (compose/nginx/53) | ✅ (فقط web-v1) |
| **PCM-20.7B** | TLS/portbind (partial — s52 offline) | ⚠️ |
| **PCM-20.7C** | Enrichment cs-20.7 → **v0004** (5,816 LLM summaries، leakage PASS، 11 datasets) + 323 تست | ✅ (فقط web-v1) |
| **PCM-20.7D** | **RAG Phase D production**: Neo4j loader + instance `tasnim` + portal E2E | ✅ **PASS — production روی 53** |

---

## ۵. اعداد رسمی پیکره‌ی تسنیم (فقط از شمارنده‌های واقعی)

### زنجیره‌ی نسخه‌ها (lineage)
| نسخه | قرارداد | محتوای کلیدی | SHA (مختصر) |
|---|---|---|---|
| snapshot | — | 45,844 صفحه از tasnim.hamtaa.org (jsonl `fd927b66…`، json `cee2c08a…`) | — |
| **v0001** | c-1 / d-1 | canonical RAW+NORMALIZED، provenance، dedup، آرشیو قطعی | content `ee87686a…` |
| **v0002** | cs-20.5 | context records (semantic) | semantic `12a93e21…` |
| **v0003** | cs-20.6 | + 10,739 HeadingRecord + 10,728 hidden-context-records + metadata truncation (validators S01–S10/V01–V09) | روی `pcm-20.6` |
| **v0004** | cs-20.7 | + LLM next-page summaries (leakage-gated، retrieval-metadata-only) | content `d7ebaeb3…`، 11 datasets |

### ساختار دانش
- **6 جلد** (جلد 47 و 56 کامل؛ بقیه جزئی)، 1 Work، 1 Edition
- **گپ**: 45,243 صفحه موجود در سایت ولی غایب از snapshot — **6 range** (gap_report؛ live sampling 8/8 OK) → بک‌فیل ≈ **188.5 ساعت** در 4 صفحه/دقیقه؛ fetch-plan-1 = 91 run × 500
- **truncation**: 28 صفحه (0.06٪) در سقف 2000 کاراکتر — سقف سمت‌منبع (live re-check 3/3 تأیید) → GATE 1.5 PASS
- **hidden context pilot (D4)**: policy v1 = **STOP** (17/37 = 45.95٪ < 0.80؛ همه‌ی FAILها فقط word_overlap؛ 0 هالوسیناسیون در چک دستی؛ توصیه: LLM-judge + min-length filter) — اما در 20.7C با prompt `hc-prompt/1.0` و Qwen3.8-27B-FP8، غنی‌سازی کامل انجام شد (0 failure)

### Phase D production (روی s53 — زنده)
| مورد | مقدار |
|---|---|
| Neo4j DB | `tasnim-qwen3-embed-06b` |
| Chunk (embedded واقعی) | **45,808** (1024-dim، Qwen3-Embedding-0.6B، unit-norm) |
| HiddenContext / Heading / Volume / Work / Edition | 21,467 / 10,739 / 6 / 1 / 1 |
| NEXT/PREV edges | 45,802 (حفظ شکاف‌های item_index) |
| vector index | ONLINE، cosine، 1024 |
| صحت | dump↔DB exact vector equality = True |
| instance | `tasnim`: API 8063 / FE 8064 / PG 5440، image `mrbaqeri/qa_lang_neo4j_mesbah:1.0.0` |
| rag-portal | corpus row `tasnim` (min_points=0)؛ 11 corpus |
| مسیر serving | V2F direct streaming؛ loader بدون re-embed |
| Dump Phase D | SHA `0e028eff…46a51` (1,268,536,648 B) |

### Web V1 (فقط branch web-v1)
- read model: `tasnim_readmodel.db` = 260,816,896 B، SHA `353f413b…` (FTS5، 12 جدول)
- API: 12 endpoint GET زیر `/api/v1/tasnim` (RFC-7807، ETag/304، cursor pagination)
- تست‌ها: 296 (293/3skip/0fail) + smoke 15/15 + E2E 12/12 + SDK 23/23 و 22/22
- 4 باگ رفع‌شده: ETag، thread-safety rate-limiter، SVG autoescape، ETag در SDK
- commitهای شاخه (6): `b11390d → 2aa11f1 → 592aca9 → adb846c → 3f4225e → report`

---

## ۶. تست‌ها — اعداد دقیق و دستورات اجرا

### Backend (رگرسیون رسمی: **200 تست**)
```bash
cd backend && python -m unittest test_api test_projects test_dashboard \
  test_knowledge_api test_word_factory test_dump test_work_registry test_queue \
  test_corpus_builder test_studio_api test_api_contract -v
```
| ماژول | شمارش | حوزه |
|---|---|---|
| test_api.py | 8 | فاز 1/2 + پروژه |
| test_projects.py | 9 | جریان CRUD |
| test_dashboard.py | 22 | auth A01–A08 + داشبورد D01–D07 |
| test_knowledge_api.py | 40 | KB-01..KB-14 (PCM-14B) |
| test_word_factory.py | 27 | WF-01..WF-13 + on_stage |
| test_dump.py | 26 | D01..D15 (Dump d-1) |
| test_work_registry.py | 10 | RD-01..RD-07 |
| test_queue.py | 9 | Q-01..Q-08 |
| test_corpus_builder.py | 24 | C-01..C-16 (c-1) |
| test_studio_api.py | 7 | S-01..S-04 |
| test_api_contract.py | 18 | CT-01..CT-06 (OpenAPI↔app) |

**قاعده‌ی ایزوله‌سازی (PCM-12.3):** همه‌ی ماژول‌ها `pct_test_support` را import می‌کنند که
**قبل از** `import server`، `PCT_DB`/`PCT_DASHBOARD_PASSWORD` را ست می‌کند؛ هر کلاس در `setUp`
با `pct_test_support.reset_db()` شروع می‌کند. هیچ تستی خودش DB نسازد. روی Windows:
`with client:` connection را می‌بندد (open handle مانع os.remove می‌شود).

### Corpus/Tasnim (روی `pcm-20.6`: **52 تست** سبز — T16 + G + TR + دیگر)
```bash
cd corpus && python -m unittest tasnim test discovery (دستور دقیق در docs/PCM-20.6-BASELINE.md)
```
(روی web-v1: 52 + 27 تست enrichment = 79؛ رگرسیون کامل web-v1 = **323**.)

### Web (فقط web-v1): 296 تست (test_tasnim_api 941 سطر، test_tasnim_frontend 855،
test_tasnim_readmodel 566، test_tasnim_sdk 672، test_corpus_backfill 690، test_corpus_pcm207c 794)

### CI (`.gitlab-ci.yml`)
- image `python:3.12-slim`؛ jobs: `regression`، `openapi`، `client` — **test-only**
- `PCT_DB=/tmp/pct-ci-$CI_JOB_ID.db`؛ **هیچ CI variable `PCT_DASHBOARD_PASSWORD` نسازید** (setdefault می‌بازد و 401 می‌شود)
- ⚠️ ناسازگاری مستند: کامنت CI «188 tests» قدیمی است (AGENTS.md = 200) — در فرصت بعدی اصلاح کنید
- GitLab executor روی s52 (2222) — فعلاً غیرقابل‌وصول

---

## ۷. سرورها و دسترسی (از PCM-20.6-BASELINE + 20.7D)

| سرور | IP | نقش | وضعیت (2026-11) |
|---|---|---|---|
| **s52** | 172.20.1.52 | PCT production (`/home/saber/saberprojects/persian-corpus-toolkit` = کپی کد، نه git)، GitLab CE (port **2222**، نه SSH)، backups `/home/saber/backups/` | ❌ **OFFLINE** — deploy/بک‌فیل/TLS/GitLab-sync همه مسدود تا بازگشت |
| **s53** | 172.20.1.53 («llm») | 2×H100؛ vLLM embeddings (4000/4001)؛ LLM Qwen3.8-27B-FP8 (8000/8001)؛ Neo4j enterprise (14 DB)؛ rag-portal + instances | ✅ **LIVE** — RAG تسنیم production اینجاست |
| ingress | 172.30.0.133 | `*.ai.ismc.ir` | ✅ زنده؛ `tasnim.ai.ismc.ir` **بدون vhost** (default cert CN=admin) |

### Runbook deploy s52 (عند بازگشت آنلاینی — از AGENTS.md + `deploy/pcm04_deploy.sh`)
1. بکاپ آنلاین: `sqlite3 thesaurus.db ".backup /home/saber/backups/thesaurus-<TS>.db"` + `PRAGMA integrity_check`
2. اسنپ‌شات deploy dir (بدون DB) → `pct-deploy-<TS>.tar.gz`
3. تضمین `.env` (chmod 600)
4. extract کد جدید
5. `docker compose build backend && docker compose up -d backend` (**هرگز** `down -v`)
6. health-wait + smoke test (endpointهای کلیدی + چک auth)
7. integrity_check مجدد + مقایسه شمارش‌ها
- SSH: `ssh -p 22 saber@172.20.1.52`

### Runbook RAG Phase D (از 20.7D — rollback موجود)
- rollback کامل: instance `tasnim` (8063/8064/5440) + corpus row `tasnim` در portal + Neo4j DB `tasnim-qwen3-embed-06b`
- 7-step manual test guide در `PCM-20.7D-PHASE-D-REPORT.md` (web-v1)

---

## ۸. قواعد سخت (خلاصه‌ی Mطلق از AGENTS.md)

1. **بدون بکاپ، مهاجرت نمی‌شود** (backup + integrity_check قبل از هر schema change)
2. **مهاجرت فقط افزایشی** (ADD COLUMN + backfill + index؛ هیچ DROP/RENAME/تغییر نوع در production)
3. **`docker compose down -v` ممنوع**
4. **هر مرحله: تست → commit → push → deploy → smoke → گزارش**
5. **رمز/توکن در کد/Git/لاگ/metric/گزارش نمی‌آید** (رمز داشبورد فقط `.env` سرور + scrypt در DB)
6. **APIهای نوشتاری اکستنشن باز می‌مانند** (`/api/projects*`)؛ فقط `/api/dashboard/*` و `/api/knowledge/*` پشت auth
7. SQL پارامتری‌شده؛ ORDER BY فقط whitelist؛ LIMIT/OFFSET اجباری (کل‌جدول‌بارگذاری ممنوع)
8. خروج DOM: `escHtml` (XSS)
9. **عدد ساختگی ندهید** — فقط شمارنده‌های واقعی DB
10. Scope: فقط `backend/ dashboard/ extension/ corpus/ deploy/ docs/`؛ **هرگز** NotebookLM / RAG indexer (به‌جز خط تسنیم که مستند شده) / QA Bank

---

## ۹. موارد باز (open items — به‌روز 2026-11-10)

| # | مورد | بلاک‌کننده | اولویت |
|---|---|---|---|
| 1 | **بک‌فیل 45,243 صفحه (Gate B)** — کد آماده (web-v1)؛ نیاز به تأیید صریح انسانی + s53/شبکه | تصمیم انسانی | بالا |
| 2 | **s52 OFFLINE** — deploy هر تغییری، TLS، GitLab mirror/sync، production PCT | بازگشت سرور | بالا |
| 3 | LiteLLM alias `rag-tasnim` (POST /model/new hang) — follow-up اپراتور روی 53 | اپراتور | متوسط (غیربلاک‌کننده؛ RAG مستقیم کار می‌کند) |
| 4 | push commit `11233e9` روی `main` (GATE 1) به origin | — | پایین |
| 5 | **183 فایل `.tmp_*` staged در index** `pcm-20.6` — `git restore --staged .tmp_*` + حذف | — | پایین (hygiene) |
| 6 | ناسازگاری `188 vs 200` در کامنت `.gitlab-ci.yml` | — | پایین |
| 7 | vhost `tasnim.ai.ismc.ir` (Web V1 deployment) — Docker در host فعلی نیست | s52/سرور میزبان | متوسط |
| 8 | surah-aware processing = NOT_SUPPORTED (ارزیابی 20.7C) | نیاز به تصمیم | پایین |

---

## ۱۰. چک‌لیست شروع هر سشن جدید

```text
1) git branch --show-current  → کدام شاخه؟ (کار جدید تسنیم/وب/RAG = web-v1)
2) git log --oneline -5       → آخرین وضعیت
3) این فایل (docs/PROJECT-KNOWLEDGE.md) را بخوان
4) AGENTS.md → قواعد سخت (حتی اگر قبلاً خوانده‌اید)
5) گزارش آخرین مأموریت (گزارش-PCM-*.md در ریشه یا docs/)
6) برای اعداد: فقط به §۵ ارجاع دهید؛ عدد جدید = شمارش واقعی
7) هر کار: تست → commit → (اگر s52 زنده بود) deploy → smoke → گزارش
```

**مسیرهای کلیدی سریع:**
- قواعد: [AGENTS.md](AGENTS.md)
- baseline سرورها/داده: [docs/PCM-20.6-BASELINE.md](docs/PCM-20.6-BASELINE.md)
- قرارداد Dump: [docs/PCM-14C.3-DUMP-CONTRACT.md](docs/PCM-14C.3-DUMP-CONTRACT.md)
- Work Registry: [docs/PCM-14D-WORK-REGISTRY.md](docs/PCM-14D-WORK-REGISTRY.md)
- Corpus Builder: [docs/PCM-16-CORPUS-BUILDER.md](docs/PCM-16-CORPUS-BUILDER.md)
- OpenAPI: [docs/openapi/README.md](docs/openapi/README.md)
- CLI تسنیم: [corpus/tasnim/cli.py](corpus/tasnim/cli.py)
- CI: [.gitlab-ci.yml](.gitlab-ci.yml)

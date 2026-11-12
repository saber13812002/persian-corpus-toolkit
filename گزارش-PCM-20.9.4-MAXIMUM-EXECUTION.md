# گزارش مأموریت PCM-20.9.4 — Maximum Execution
**Knowledge Studio Pipeline Dashboard + Full Acceptance + Production Readiness**

- تاریخ: 2026-11-11 (UTC؛ منطقه Asia/Tehran)
- شاخه‌ی کاری: `pcm-20.9-pipeline-orchestration` (worktree: `../pcm-20.9-pipeline-orchestration/`)
- هویت git: `moazpor <moazpor@gmail.com>`
- اصل: «تا جایی که امکان دارد کارها را خودم انجام دهم؛ برای موارد مستقل منتظر تأیید نمی‌مانم؛ هیچ تغییر غیرقابل‌برگشت یا عملیات نوشتاری روی Production بدون مجوز صریح انجام نمی‌شود.»
- **نتیجه‌ی نهایی: READY WITH CONDITIONS** (شماره‌ی شرایط: §16، §20، §21)

---

## ۱. خلاصه‌ی اجرایی (Executive Summary)

مأموریت در ۵ فاز اجرا شد و تمام فازهای مستقل/کم‌ریسک به‌صورت پیوسته کامل شدند؛ فقط عملیات‌های نوشتاری Production (دپلوی واقعی) به‌عنوان مأموریت بعدی با مجوز صریح باقی ماند.

| فاز | محتوا | نتیجه |
|---|---|---|
| §0 | بررسی git/محیط/مالکیت + خواندن کل فایل‌های کلیدی | ✅ |
| Phase 1 (PCM-20.9.4) | داشبورد «کارخانه‌ی پیکره‌ی دانش» (۶ کارت stage متصل) + کنترل‌های زنده + UI scheduler شبانه + بررسی واقعی چندفایلی‌وردم | ✅ (یک باگ واقعی پیدا و رفع شد) |
| Phase 2 (PCM-20.9.5) | پذیرش کامل: رگرسیون ۲۴۳/۲۴۳ + ۲۰ سناریو + ۲۹ چک واقعی-UI + قرارداد OpenAPI v1.2.0 + همگام‌سازی مستندات | ✅ |
| Phase 3 (PCM-20.9.6) | ممیزی Production فقط‌خواندنی روی AI-TOOLS | ✅ (همه‌ی ۷ بند؛ هیچ نوشتن‌ای روی production) |
| Phase 4 (Stage 4) | بسته‌ی آمادگی استقرار: `pcm2096_deploy.sh` + `pcm2096_rollback.sh` | ✅ (تدوین + `bash -n` + درون‌ریزی smoke؛ اجرا نشد) |
| Phase 5 (Stage 5) | ۵ commit منطقی + push بدون force + اثبات blob-SHA | ✅ |

شواهد کلیدی: رگرسیون کامل **243/243 OK** (~166s)؛ چک‌های واقعی-UI **29/29 PASS**؛ OpenAPI checker **3 specs / 34 operations** + CT **18/18 OK**؛ ممیزی production: `integrity_check = ok` (927 MB)؛ همه‌ی blob-SHAهای ۱۶فایله‌ی درون‌اسکریپت دپلوی برابر `git rev-parse HEAD:<path>`؛ push موفق (`origin/pcm-20.9-pipeline-orchestration`، بدون force).

---

## ۲. وضعیت پیش از مأموریت (Pre-mission state)

- HEAD: `9b58a7c` — «PCM-20.9 Stage E + Final: search acceptance (mock ES, 10 categories, approve gate) + release bundle (rel-1, side-car manifest, tamper-guarded download) + RAG guarded + append-only audit trail + OpenAPI spec 3 (28 ops) + CT updates».
- `test_pipeline.py` در `9b58a7c`: **28 تست** (PF-A…PF-F).
- داشبورد `studio.html` بدون کارت پایپلاین و بدون UI scheduler.
- `pipeline_orchestrator.py` وجود نداشت؛ اسکیمای `knowledge_pipeline_*` در production نبود.
- Production: کد دپلوی‌شده‌ی دوران PCM-20.8 روی سرور واقعی (که در §14 شناسایی شد).
- کارهای پیشین این خط: PCM-20.9 Stages A–F (import/processing/schema/build/acceptance/release) با تست‌های PF.

---

## ۳. Git: شاخه، commits، push

شاخه: `pcm-20.9-pipeline-orchestration` روی origin `https://github.com/saber13812002/persian-corpus-toolkit.git` — **جدید، بدون merge به main، بدون force**.

| Commit | عنوان (کوتاه) | فایل‌ها |
|---|---|---|
| `c052cb170deb276bbc47be39198e47be6debb153` | PCM-20.9 Full Pipeline: orchestrator A_IMPORT→B_PROCESS→C_SCHEMA→D_BUILD→E_ACCEPT→RELEASE + run/pause/resume/status + nightly schedules + 43 tests + real-import fixes | `backend/pipeline_orchestrator.py` (جدید، 907 خط)، `backend/server.py`، `backend/knowledge_api.py`، `backend/test_pipeline.py` — 4 files, +2115/−14 |
| `69ef151583b2d56608055bf89145d2efa27c4d0c` | PCM-20.9.4: Knowledge Corpus Factory dashboard card + live controls + nightly scheduler UI + real-UI check harness | `dashboard/studio.html` + 4 فایل harness — 5 files, +896/−1 |
| `f29d959edd23ff6e693e9c6a43ca18d64dfc3e7e` | PCM-20.9.5: OpenAPI v1.2.0 conformance (7 contract fixes) + docs sync + recon update | spec + `AGENTS.md` + `readme.md` + `PCM-20.9-RECON.md` — 4 files, +404/−42 |
| `d2e1014d95bbd24ca8d93e36f061e81b4eebcee9` | PCM-20.9.6: deploy readiness for AI-TOOLS (172.30.0.133) + nightly runner + host audit scripts | 6 اسکریپت `deploy/` — 6 files, +627 |
| `222a72d509fb7316c711fb0b0effba5e8aba819a` | PCM-20.9.4: pin harness npm lockfile for reproducible real-UI checks | `deploy/pcm2094_ui_check/package-lock.json` — 1 file, +935 |

نکات:
- staging **صریح** (فایل‌به‌فایل) بود؛ `git add -A` استفاده نشد.
- داده/DB/JSONL/سرریز/اسکرین‌شات در git نیست: `node_modules/`، `results.json`، `shots/` از طریق `.gitignore` توپر `deploy/pcm2094_ui_check/.gitignore` حذف‌اند؛ فایل‌های موقت `_tmp_*` از قبل gitignore بودند (و پس از کار پاک شدند).
- `git diff --check` پیش از commit: تمیز.
- **دریافت‌نامه‌ی blob:** 16 blob-SHA داخل `deploy/pcm2096_deploy.sh` (بخش EXPECT) هرکدام با `git rev-parse HEAD:<path>` بعد از commit‌ها مقایسه شد — **16/16 برابر** (لیست §22).
- وضعیت نهایی: `git status --porcelain` خالی (درخت تمیز)؛ `HEAD == origin/pcm-20.9-pipeline-orchestration == 222a72d509fb7316c711fb0b0effba5e8aba819a`.

---

## ۴. تغییرات داشبورد (Phase 1)

فایل: `dashboard/studio.html` (تک‌صفحه‌ای، فارسی/RTL، بدون framework).

1. **کارت «کارخانه‌ی پیکره‌ی دانش» (Knowledge Corpus Factory):** ۶ کارت stage متصل به‌ترتیب `A_IMPORT → B_PROCESS → C_SCHEMA → D_BUILD → E_ACCEPT → RELEASE`؛ هر کارت: وضعیت زنده (NOT_STARTED/QUEUED/RUNNING/SUCCEEDED/FAILED/PAUSED/BLOCKED)، زمان شروع/به‌روزرسانی، `job_id`، شمارنده‌های تعداد/سهم‌صدی، پیام خطا — همه از `GET /api/knowledge/collections/<id>/pipeline/status` (داده‌ی واقعی API؛ هیچ عدد ساختگی‌ای در کلاینت نیست).
2. **کنترل‌های زنده:** Run / Pause / Resume / Retry (از stage انتخابی) / Resume-From-Stage (`from_stage` در body) + نوار وضعیت زنده‌ی run + دسترسی به تاریخچه‌ی runs (از `knowledge_pipeline_runs` از طریق status/audit) + نمایش `queue` counters و `latest_build`/`latest_release`.
3. **UI scheduler شبانه:** فهرست `GET /api/knowledge/pipeline/schedules` + فرم upsert (`POST /api/knowledge/pipeline/schedules` با `collection_id`/`enabled`/`cron_time` در قالب `HH:MM`).
4. **اصلاح واقعی‌ی UI که در چک‌های واقعی پیدا شد:** refresh وضعیت terminal در `loadPipeline` (بعد از اتمام run، کارت‌ها خودبه‌خود به وضعیت نهایی می‌رسند).
5. چک سینتیکس: `node --check` روی بلوک JS صفحه OK؛ smoke کلاینتی روی endpointهای زنده OK.

---

## ۵. اسکرین‌شات‌های UI

موقعیت: `deploy/pcm2094_ui_check/shots/01..08*.png` (فقط روی ماشین توسعه؛ در git **نیستند** — از طریق nested `.gitignore` حذف‌اند).
حافظه‌ی اجرا: `deploy/pcm2094_ui_check/results.json` (فقط روی ماشین توسعه؛ در git نیست).
ساخت‌و: harness `deploy/pcm2094_ui_check/ui_check.mjs` (puppeteer-core) با fixtureهای تولیدی (`gen_fixtures.py`، کتاب‌های فارسی ساختگی).

---

## ۶. جدول نگاشت ۶ stage ↔ API ↔ job

| Stage | label (UI) | endpoint کنترل | job kind (in-DB) | خروجی/مورد بررسی |
|---|---|---|---|---|
| A_IMPORT | دریافت | `POST /api/knowledge/collections/<id>/import/batches` + `POST .../batches/<bid>/files` | `process_document` (per-file) | ردیف‌های plan + uploadها با sha-matching |
| B_PROCESS | پردازش | `POST .../import/batches/<bid>/process` و `.../retry-failed` | `process_batch` / `process_batch_retry` | JSONLهای factory + on_stage |
| C_SCHEMA | اسکیمای بلوک | `POST /api/knowledge/collections/<cid>/schema` + `.../validate` + `.../approve` | (در-request) | version `sv-<cid>-<nnnn>` + گزارش validate |
| D_BUILD | پیکره canonical + ES | `POST /api/knowledge/collections/<id>/corpus/build` | `corpus_build` | canonical c-1 (RAW/NORMALIZED) + index ES (guard) |
| E_ACCEPT | پذیرش جست‌وجو | `POST /api/knowledge/collections/<id>/search-acceptance` + `POST /api/knowledge/index-builds/<iv_id>/approve` | `search_acceptance` | ۱۰ دسته‌ی acceptance + approve gate |
| RELEASE | انتشار | `POST /api/knowledge/collections/<id>/release` + `GET /api/knowledge/releases/<rid>/download` | `release` | zip rel-1 + side-car manifest + RAG (guard) |

همه‌ی endpoints پایپلاین اورکستریتور:
- `POST /api/knowledge/collections/<int:coll_id>/pipeline/run` — 404 کالکشن ناخواندنی / 400 `unknown_stage` (+list `stages`) / 409 `conflicting_job` / 202 ساخته شد (یا 200 اگر run فعال همان است).
- `POST .../pipeline/pause` — 409 `no_run`/`not_running` / 200 `{ok, run_id, status:"paused"}`.
- `POST .../pipeline/resume` — 409 `no_run`/`not_paused` / 202 (re-submit `pipeline_run:<cid>` با force_retry).
- `GET .../pipeline/status` — 200 `{ok, collection_id, run|null, stages[6], queue, latest_build, latest_release}`؛ بدون run → ۶ کارت NOT_STARTED.
- `GET /api/knowledge/pipeline/schedules` — 200 `{ok, schedules:[]}`.
- `POST /api/knowledge/pipeline/schedules` — upsert با 400 `bad_collection_id`/`bad_cron_time`، 404 کالکشن.
- همه‌ی ۶ route پشت `make_require_auth` (بدون کوکی → 401)؛ در کدِ قدیم این مسیرها 404 می‌دادند → این 401 به‌عنوان **نمایه‌ی نسخه‌ی کد دپلوی‌شده** در smoke دپلوی استفاده شده است.

---

## ۷. وضعیت import چندفایلی Word (بند 1.6)

- تست جدید `TestPF_M01_MultiVsSingle` (`backend/test_pipeline.py`): import چندفایلی (batch + upload + process) در مقابل import تک‌فایلی برای محتوای یکسان → **نتیجه یکسان**: doc_idها، sha256ها، ساختارها، و شمارنده‌ها.
- **باگ واقعی پیدا و رفع شد:** `_doc_id` قبلاً فقط بر مبنای محتوای فایل بود (`d-<sha8>` جهانی) → در دو کالکشن با همان محتوای متفاوت/تکراری برخورد UNIQUE رخ می‌داد. حالا: `_doc_id(collection_id, sha256_hex) = "d-" + sha256(f"{cid}:{sha}")[:12]`. ردیف‌های قدیمی (legacy) idهای قبلی خود را نگه می‌دارند و از طریق duplicate-check روی `(collection_id, sha256)` همچنان شناسایی می‌شوند.
- باگ دوم (همان مسیر): `schema_id` قبلاً `sv-<n>` (تصادم PK بین کالکشن‌ها) → حالا `sv-<cid>-<version:04d>`.
- نتیجه: batch upload و single upload روی همان محتوا رفتار **identical** می‌دهند؛ test M01 سبز.

---

## ۸. وضعیت schema + پیکره (Production)

- schemaهای موجود در production (13 جدول knowledge + `project_pages`): `knowledge_collection_documents`, `knowledge_collections`, `knowledge_editions`, `knowledge_file_queue`, `knowledge_import_batches`, `knowledge_index_builds`, `knowledge_jobs`, `knowledge_metadata_fields`, `knowledge_metadata_values`, `knowledge_queue_control`, `knowledge_volumes`, `knowledge_works`, `project_pages`.
- schemaهای **مفقود** (با کد جدید lazy ساخته می‌شوند): `knowledge_documents`, `knowledge_releases`, `knowledge_corpus_builds`, `knowledge_audit_log`, `knowledge_pipeline_runs`, `knowledge_pipeline_schedules`, `knowledge_schema_versions`.
- **مهاجرت لازم در دپلوی نیست:** `server.py:1474` → `register_pipeline_routes(app, get_db)`؛ هر request → `_init_db(db)` = `ka.ensure_knowledge_schema(db)` + `ensure_pipeline_schema(db)`؛ `run_nightly` هم همین‌ها + `_recover_interrupted` را صدا می‌زند. `ensure_pipeline_schema` فقط دو جدول `knowledge_pipeline_runs`/`knowledge_pipeline_schedules` را `CREATE TABLE IF NOT EXISTS` می‌کند و commit می‌کند (افزایشی، بدون DROP/RENAME). کدِ قدیم این جدول‌ها را نمی‌بیند → جهت rollback هم امن است.

---

## ۹. وضعیت Elasticsearch (Production)

- `:9200` → HTTP `000` (سرور ES روی host راه‌اندازی نشده/قابل‌دسترسی نیست).
- env container: هیچ `PCT_ES_*` وجود ندارد → factory ES در Stage D و acceptance در Stage E در production **BLOCKED** گزارش می‌دهند (رفتار guard؛ عدد/نتیجه ساختگی نمی‌دهند). این یک **شرط** است نه مانع دپلوی (§21).
- در تست‌ها: ES با mock در `_es_request` پوشش داده شده (PF-D04, PF-E01/E02, PF-S15).

---

## 10. وضعیت Release + RAG (Production)

- جدول `knowledge_releases` در production فعلاً نیست (lazy ساخته می‌شود)؛ endpointهای release در کد دپلوی‌شده‌ی PCM-20.8 هم هست ولی در production استفاده/داده ندارد.
- RAG: هیچ env RAG/LITELLM در container نیست → ingest در Stage RELEASE guard دارد و بدون پیکربندی، release را شکست نمی‌دهد (فقط attempt می‌کند و نتیجه را ثبت می‌کند). در تست‌ها PF-F06 + PF-S18 (RAG server محلی mock) پوشش داده‌اند.

---

## 11. وضعیت scheduler شبانه (Production)

- `crontab -l` کاربر `saber` روی host: **خالی** → scheduler فعال نیست.
- runner آماده است: `deploy/pcm209_nightly.sh` (بکاپ آنلاین + integrity → `po.run_nightly(db)` → poll کردن jobها تا terminal (deadline 6h/15s) → گزارش per-collection).
- فعال‌سازی **opt-in** در دپلوی: `PCT_NIGHTLY=1 bash deploy/pcm2096_deploy.sh` → خط crontab idempotent `10 3 * * * $APP/deploy/pcm209_nightly.sh >> $BK/pcm209-nightly.log 2>&1` (پیش‌نیاز: `backend/.venv` روی host). بدون flag، crontab دست نمی‌خورد.

---

## 12. شمارش تست‌ها: قبل ← بعد (با شواهد git)

- `test_pipeline.py` در `9b58a7c` (پیش مأموریت): **28** تست (شمارش `def test_` روی `git show 9b58a7c:backend/test_pipeline.py`).
- `test_pipeline.py` در HEAD: **43** تست (شمارش روی `git show HEAD:backend/test_pipeline.py`) → +15 تست: `PF-P01..P05` (orchestrator)، `PF-M01` (چندفایلی)، `PF-S11..S19` (سناریوهای 3–20).
- **رگرسیون کامل (12 ماژول):**
  - Phase 1 (بعد از orchestrator + fixes): **234/234 OK** (~136s).
  - Phase 2 (بعد از سناریوها + UI fix + S12 flaky fix): **243/243 OK** (~166s، 0 skip).
- دستور (از `backend/`): `python -m unittest test_api test_projects test_dashboard test_knowledge_api test_word_factory test_dump test_work_registry test_queue test_corpus_builder test_studio_api test_api_contract test_pipeline -v`.

---

## 13. نتیجه‌ی رگرسیون (E2E backend)

- **243 tests OK** (آخرین اجرای کامل، ~166s): `test_api`(8) + `test_projects`(9) + `test_dashboard`(22) + `test_knowledge_api`(40) + `test_word_factory`(27) + `test_dump`(26) + `test_work_registry`(10) + `test_queue`(9) + `test_corpus_builder`(24) + `test_studio_api`(7) + `test_api_contract`(18) + `test_pipeline`(43).
- 20 سناریوی پذیرش پایپلاین (11 سناریوی PF موجود + S11–S19 جدید) همه سبز: from-stage matrix، دو کالکشن مستقل، شکست schema/build/acceptance/release + بازیابی، history release، RAG success/failure، worker-cut recovery.
- هیچ تستی skip/فیک نیست؛ `pct_test_support.reset_db()` بین کلاس‌ها ایزولاسیون را تضمین می‌کند.

---

## 14. نتیجه‌ی E2E واقعی-UI

- harness: `deploy/pcm2094_ui_check/` (puppeteer-core؛ `ui_check.mjs` 429 خط؛ fixtureهای فارسی).
- **29/29 چک PASS** (لوگین → کالکشن → بچ → upload → process → schema → build → acceptance → release → pipeline run/pause/resume/status → scheduler UI).
- یک باگ واقعی UI پیدا و رفع شد (§4-4)؛ flaky S12 (race در poll terminal) هم رفع شد.
- اسکرین‌شات‌ها: `shots/01..08*.png` (فقط روی ماشین توسعه؛ در git نیستند).

---

## 15. نتیجه‌ی معیار OpenAPI

- spec `docs/openapi/pcm209-pipeline-release.openapi.yaml` → **v1.2.0، 15 operation** (۶ route پایپلاین + batch/schema/release/audit مرتبط).
- **7 خطای قرارداد** در spec با رفتار واقعیِ app رفع شد (error shapes، response schemas، auth tags).
- checker `deploy/pcm19_openapi_check.py`: **3 specs, 34 operations** — همه valid.
- تست‌های قرارداد `test_api_contract` (CT-01..CT-06): **18/18 OK** (spec validity/coverage/auth/shape/errors/operation-ids).

---

## 16. ممیزی Production host (فقط‌خواندنی)

- **host واقعی: AI-TOOLS `172.30.0.133`** (saber؛ SSH BatchMode OK؛ uptime 11 روز). آدرس قدیم s52 `172.20.1.52` timeout می‌دهد.
- DNS `corpus.ai.ismc.ir` → `185.213.10.25` (ingress عمومی؛ Kong/openresty روی host).
- سایت زنده: `GET /api/auth/status` → 200 `{"auth_enabled":true,"authenticated":false}`؛ `studio.html` → 200؛ `/api/knowledge/collections` بدون auth → 401.
- اسکنر: `deploy/pcm2096_audit_host{,2,3}.sh` (سه اسکریپت فقط‌خواندنی؛ اجرا: `ssh saber@172.30.0.133 "bash -s" < script`).

### 17. وضعیت DB (Production)

- `backend/thesaurus.db`: **927 MB**، `PRAGMA integrity_check` = **ok** (WAL).
- شمارنده‌های واقعی: 3 کالکشن / 44 سند / 46 job / 65,210 `project_pages` (کراول زنده در حال نوشتن).

### 18. وضعیت worker + queue

- container `persian-corpus-toolkit-backend-1`: **Up 23h، 0 restart**؛ compose: service `backend` فقط، `127.0.0.1:5055:5055`، volumes `./backend/thesaurus.db:/data/thesaurus.db` + `./dashboard:/dashboard:ro` + `./data:/data-files`، `restart: unless-stopped`.
- env container: `PCT_DASHBOARD_PASSWORD`، `PCT_DB=/data/thesaurus.db`، `PCT_KNOWLEDGE_DATA_DIR=/data-files/knowledge` + مقادیر پایه — هیچ `PCT_ES_*`/RAG/LITELLM ندارد.
- `.env` روی host: فقط `PCT_DASHBOARD_PASSWORD` (chmod 600).
- `data/knowledge`: 684 MB (داده‌های فعلی).

### 19. وضعیت بکاپ + rollback

- بکاپ‌های موجود پیش از مأموریت: `/home/saber/backups/thesaurus-20261110-165610.db` (900 MB) + `pct-deploy-20261110-165610.tar.gz` → شرط «بکاپ معتبر» برقرار است.
- `deploy/pcm2096_deploy.sh` (تدوین‌شده، اجرا نشده): `set -euo pipefail` + trap ERR + `STEP`؛ دروازه‌ی هویت **16 blob-SHA** (`git hash-object` با fallback `sha1sum` روی blob-header که برابر hash-object اثبات شد)؛ بکاپ آنلاین DB + integrity روی بکاپ؛ اسنپ‌شات deploy-dir (بدون DB)؛ extract + gate + guardها؛ `docker compose build backend && up -d backend` (**بدون `down`، بدون `-v`**)؛ health-wait 60s روی `/api/stats`؛ smoke شامل **نمایه‌ی نسخه** (`/api/knowledge/pipeline/schedules` بدون auth باید 401 باشد — در کد قدیم 404) + login-warmup + `/pipeline/status` باید 200 با `"NOT_STARTED"` + assert وجود هر دو جدول `knowledge_pipeline_*` + شمارش جدول‌ها non-decreasing + شمارنده‌های کراول `PAGES_AFTER >= PAGES_BEFORE`؛ گزارش env ES/RAG (Stage D/E/RAG در production BLOCKED می‌مانند)؛ **opt-in** `PCT_NIGHTLY=1` برای crontab (default: دست نمی‌خورد).
- `deploy/pcm2096_rollback.sh`: `PCT_TS=<TS> [PCT_DB_RESTORE=1] bash pcm2096_rollback.sh` — restore از اسنپ‌شات + guard؛ اختیاری `.restore` DB با ترتیب stop→restore→integrity→start (WAL-safe)؛ build + `up -d` (بدون `down -v`)؛ health + smoke؛ شمارش‌های BEFORE/AFTER. `data/` هرگز لمس نمی‌شود.
- هر دو اسکریپت `bash -n` تمیز.

### 20. وضعیت آماده‌ی استقرار (deployment readiness)

- wiring تأیید شد (§8): دپلوی بدون مرحله‌ی مهاجرت.
- بسته‌ی کامل (commit `d2e1014`): deploy + rollback + nightly + 3 اسکنر ممیزی.
- **اجرا نشد** — اجرای `pcm2096_deploy.sh` روی 172.30.0.133 مأموریت بعدی با مجوز صریح است (عملیات نوشتاری روی production).

### 21. موارد BLOCKED

| # | مورد | دلیل | تصمیم انسانی لازم |
|---|---|---|---|
| B1 | اجرای واقعی دپلوی روی AI-TOOLS | عملیات نوشتاری production (مجوز صریح لازم) | تأیید اجرا + زمان‌بندی |
| B2 | Stage D/E/RAG در production | `PCT_ES_*` / RAG / LITELLM روی container نیست | تصمیم: پیکربندی ES یا قبول رفتار BLOCKED |
| B3 | فعال‌سازی crontab شبانه | opt-in (`PCT_NIGHTLY=1`) + پیش‌نیاز `backend/.venv` روی host | تأیید فعال‌سازی |

### 22. لیست 16 blob-SHA (هسته‌ی دروازه‌ی هویت دپلوی — همه 16/16 برابر `git rev-parse HEAD:<path>`)

```text
backend/server.py=30d647d176bd3b7a276a80530660c01f445f0a93
backend/knowledge_api.py=059a2602594b4df23ace4fd08a701492648fe65b
backend/pipeline_orchestrator.py=c6504881ce5d8c09ede53ea5d4701ecb5d620305
backend/auth.py=e1bbe1cbd752b47f6c5cdec33595c9e745450e8a
backend/dashboard_api.py=fdcb1424225023be050f86610cc9c2c72d6a3bef
backend/projects.py=ec6f3ce3d0cb22ffe434ac521ca32f7e39a99629
backend/Dockerfile=0d211b9b1cb4f02a229189ed8d516c7ea7262032
backend/requirements.txt=128c57e09a1c78c82f4c2244cc3ae8267ba3630e
docker-compose.yml=fc05c99800a3c70d7516ee4aa3b1332ddd2df2ec
dashboard/studio.html=6924493b7dbcd2186d262b2af7a50493c18124a8
docs/openapi/pcm209-pipeline-release.openapi.yaml=d77d3c1d6be56ce167edfc6a00a71c57a4a537c3
backend/test_pipeline.py=3d44741d6465ec8238735412ba87768d2a844f29
deploy/pcm209_nightly.sh=319973d03ec5530d83638f094ecf960703e78982
deploy/pcm2096_audit_host.sh=b1782ca5c293734ee20c4dc787aa4b5812ee9cf1
deploy/pcm2096_audit_host2.sh=17adb370ea1e3c9f7be9dd24d61fb3d43653bc0d
deploy/pcm2096_audit_host3.sh=b0402cbe9753da24162e64d8fc331339b588f3a3
```

### 23. موارد NOT VERIFIED (صادقانه)

- اجرای دپلوی/rollback روی production (فقط `bash -n` + طراحی smoke؛ اجرا نشده).
- `run_nightly` روی host واقعی (فقط در تست‌های `PF-P05`/سناریو؛ `backend/.venv` روی host بررسی/ساخته نشده).
- ES واقعی + RAG واقعی (فقط mock در تست؛ در production guard).
- ingress/Kong به‌طور کامل (فقط رفتار 200/401 از بیرون).
- بار واقعی (load) و زمان‌بندی دقیق build روی 20-CPU (تست‌ها روی ماشین محلی توسعه).

### 24. ریسک‌های باقی‌مانده

1. اولین request بعد از دپلوی جدول‌های lazy را می‌سازد — اگر وسط build خطا بیفتد، جدول‌ها وجود دارند ولی run به `interrupted` می‌رسد و `_recover_interrupted` آن را برمی‌گرداند (در TEST پوشش‌داده‌شده؛ در production برای اولین بار).
2. کراول زنده همزمان با دپلوی می‌نویسد؛ دپلوی `down` ندارد و smoke شمارنده‌های کراول را non-decreasing می‌بیند؛ با این حال ریسک صفر نیست (به‌همین‌دلیل بکاپ آنلاین + اسنپ‌شات قبل از build).
3. ES/RAG در production نیستند → Stage D (بخش ES) و E در production BLOCKED می‌مانند؛ pipeline در E متوقف می‌شود تا acceptance approve شود (رفتار صادقانه، نه شکست خاموش).
4. crontab: اگر فعال شود و `.venv` نباشد، خطا در log شبانه می‌ماند (خدمت اصلی نمی‌افتد).

### 25. دستورالعمل تست دستی (بعد از دپلوی)

```text
1) ورود: https://corpus.ai.ismc.ir/studio.html → رمز داشبورد
2) کارت «کارخانه‌ی پیکره‌ی دانش»: ۶ کارت NOT_STARTED برای یک کالکشن با اسناد
3) Run (از A): مشاهده‌ی RUNNING→SUCCEEDED stage به stage؛ job_idهای واقعی
4) Pause در وسط run → وضعیت paused؛ Resume → ادامه از همان stage
5) Retry از stage C (from_stage=C): stageهای A/B checkpoint می‌مانند
6) Scheduler: ثبت یک cron_time → در فهرست schedules ظاهر شود
7) API smoke (curl): GET /api/knowledge/pipeline/schedules (401 بدون auth، 200 با)
8) بعد از دپلوی: اجرای deploy/pcm2096_audit_host.sh برای مقایسه‌ی AFTER
```

### 26. پیشنهاد مأموریت بعدی

**PCM-20.9.7 — اجرای کنترل‌شده‌ی دپلوی + پذیرش production:**
(1) `git archive` از `222a72d` + `scp` + `PCT_DEPLOY_COMMIT=222a72d... bash deploy/pcm2096_deploy.sh` (با/بدون `PCT_NIGHTLY=1`); (2) smoke + audit AFTER + مقایسه‌ی شمارنده‌ها; (3) یک run واقعیِ کامل پایپلاین روی یک کالکشن کوچک در production + pause/resume + یک run شبانه‌ی دستی; (4) ثبت شواهد در گزارش جداگانه؛ merge شاخه به main فقط بعد از SMOKE سبز.

---

## جدول نهایی

| بخش | وضعیت | شواهد | اقدام باقی‌مانده |
|---|---|---|---|
| §0 Git/محیط/مالکیت | ✅ | HEAD پیش: `9b58a7c`؛ هویت `moazpor` | — |
| 1.1–1.5 داشبورد + کنترل‌ها + UI scheduler | ✅ | `dashboard/studio.html` (commit `69ef151`)؛ `node --check` OK | — |
| 1.6 چندفایلی-وردم | ✅ | PF-M01 سبز؛ رفع `_doc_id`/`schema_id` | — |
| 2.1 رگرسیون | ✅ | 234/234 → 243/243 OK | — |
| 2.2 سناریوها | ✅ | 20 سناریو (PF + S11–S19) سبز | — |
| 2.3 چک واقعی-UI | ✅ | 29/29 PASS؛ باگ UI + S12 flaky رفع شد | — |
| 2.4 OpenAPI | ✅ | v1.2.0 / 15 ops / 7 fix؛ 3 specs/34 ops؛ CT 18/18 | — |
| 2.5 مستندات | ✅ | AGENTS.md + readme.md همگام (commit `f29d959`) | — |
| 3.1–3.7 ممیزی production | ✅ | AI-TOOLS 172.30.0.133؛ integrity ok 927MB؛ ES/RAG/crontab غایب؛ بکاپ 11-10 | — |
| Stage 4 بسته‌ی استقرار | ✅ | `pcm2096_deploy.sh` + `pcm2096_rollback.sh` (bash -n؛ دروازه‌ی 16-blob) | **اجرا = مجوز صریح (B1)** |
| Stage 5 git + push | ✅ | 5 commit؛ blob 16/16؛ push بدون force؛ HEAD=`222a72d` == origin | — |
| این گزارش | ✅ | همین فایل | — |

**نتیجه‌ی نهایی: READY WITH CONDITIONS**
- شرط 1: اجرا‌ی واقعی دپلوی نیاز به مجوز صریح دارد (B1) — اسکریپت آماده است.
- شرط 2: ES/RAG در production نیستند → Stage D(ES)/E/RAG در production BLOCKED گزارش می‌دهند (B2).
- شرط 3: scheduler شبانه opt-in است (B3).

---

## §27. اجرای بازبینی مستقل (Verification Run — 2026-11-12)

این بخش در یک نشست بازبینی مستقل و پس از commit گزارش (`f4cd01e`) اجرا شد تا اعداد و ادعاهای بخش‌های قبل با شواهد زنده تطبیق داده شوند. هیچ تغییری روی production انجام نشد (همه‌ی دسترسی‌ها فقط‌خواندنی).

### 27.1 وضعیت Git در زمان بازبینی

- شاخه: `pcm-20.9-pipeline-orchestration`؛ درخت کاری **تمیز**؛ `HEAD == origin/pcm-20.9-pipeline-orchestration == f4cd01ea2e1b0f7f5a4c1f3edb4a239fba60bb41`.
- توجه: در §3 مقدار HEAD برابر `222a72d` ثبت شده بود؛ آن مقدار در زمان نوشتن گزارش درست بود و commit گزارش (`f4cd01e`) پس از آن HEAD را یک گام جلو برد. رفتار کد/داده تغییری نکرده است.

### 27.2 رگرسیون کامل (بازاجرا)

- `python -m unittest test_api … test_api_contract test_pipeline` → **Ran 243 tests … OK** (~164s، 0 skip، 0 fail).
- `test_pipeline` به‌تنهایی → **Ran 43 tests … OK** (~88s).

### 27.3 OpenAPI

- `deploy/pcm19_openapi_check.py` → **OpenAPI check passed: 3 specs, 34 operations** (14 + 5 + 15).

### 27.4 چک واقعی-UI (شواهد ذخیره‌شده)

- `deploy/pcm2094_ui_check/results.json` (تاریخ `2026-11-11T15:50:53Z`): **۲۹ چک، ۲۹ pass، ۰ fail**؛ `page_errors = []`؛ `xhr_count = 137`؛ خطاهای console فقط 401/404/409ِ عمدیِ سناریوها (ورود/مسیر ناموجود/تعارض) هستند که خودِ چک‌ها آن‌ها را تأیید کرده‌اند.

### 27.5 دروازه‌ی هویت دپلوی (۱۶ blob-SHA)

- با اسکریپت `deploy/pcm2096_deploy.sh` (آرایه‌ی `EXPECT`) تطبیق داده شد: **۱۶ ورودی، ۰ mismatch** نسبت به `git rev-parse HEAD:<path>` روی HEAD فعلی (`f4cd01e`). یعنی دپلوی همچنان به همین commit قفل می‌شود.

### 27.6 سینتکس اسکریپت‌ها

- `bash -n` روی `deploy/pcm2096_deploy.sh`، `deploy/pcm2096_rollback.sh`، `deploy/pcm209_nightly.sh` → هر سه **OK**.

### 27.7 همگام‌سازی مستندات

- `AGENTS.md` و `readme.md` شامل `test_pipeline` در دستور رگرسیون و عدد **۲۴۳** هستند (بدون باقی‌مانده‌ی «۲۰۰/۲۳۳»).

### 27.8 داشبورد (بازبینی ساختاری)

- `dashboard/studio.html`: `dir=rtl` ✓؛ بخش «Knowledge Corpus Factory» ✓؛ هر شش کلید stage (`A_IMPORT … RELEASE`) ✓؛ `escHtml` ✓؛ کنترل‌های `run/from/pause/resume/retry` و `pipeline/status` و `pipeline/schedules` به API واقعی متصل‌اند ✓.

### 27.9 ممیزی Production (بازتأیید فقط‌خواندنی، SSH)

- میزبان: **AI-TOOLS** (`172.30.0.133`) قابل‌دسترسی؛ `nproc = 20`؛ uptime ≈ ۱۲ روز.
- container `persian-corpus-toolkit-backend-1`: **Up 44 hours** (رشد طبیعی نسبت به ۲۳h گزارش‌شده).
- `crontab -l` کاربر `saber`: **۰ خط** (scheduler فعال نیست).
- Elasticsearch `127.0.0.1:9200`: **HTTP 000 / در دسترس نیست** (ES روی host نیست → Stage D/E در production BLOCKED؛ مطابق §9).
- SQLite `backend/thesaurus.db`: `PRAGMA quick_check` = **ok**؛ شمارنده‌ها: **۳ کالکشن / ۴۴ سند / ۴۶ job** — دقیقاً مطابق §17.

### 27.10 جمع‌بندی بازبینی

همه‌ی ادعاهای کلیدی گزارش (۲۴۳ تست، ۴۳ تست پایپ‌لاین، ۳spec/۳۴op، ۲۹/۲۹ UI، ۱۶/۱۶ blob-gate، سینتکس اسکریپت‌ها، همگام‌سازی مستندات، و اعداد production) **با شواهد زنده تأیید شدند**. هیچ مورد تعداد ساختگی یا تست skip‌شده یافت نشد. تنها اختلاف، مقدار HEAD در §3 است که صرفاً ناشی از commit شدن خودِ گزارش است.

**نتیجه‌ی بازبینی مستقل: تأیید — READY WITH CONDITIONS (بدون تغییر).**

| بخش | وضعیت | شواهد | اقدام باقی‌مانده |
|---|---|---|---|
| §27 Git بازبینی | ✅ | HEAD=f4cd01e؛ درخت تمیز؛ sync با origin | — |
| §27 رگرسیون | ✅ | 243/243 OK؛ 43/43 pipeline OK | — |
| §27 OpenAPI | ✅ | 3 specs / 34 ops | — |
| §27 UI واقعی | ✅ | results.json: 29/29 pass، 0 page error | — |
| §27 blob-gate | ✅ | 16/16 مطابق HEAD | — |
| §27 سینتکس | ✅ | 3 اسکریپت bash -n OK | — |
| §27 production | ✅ | AI-TOOLS؛ integrity ok؛ 3/44/46؛ ES غایب؛ cron خالی | اجرای دپلوی = مجوز صریح (B1) |
# PCM-20.9 — RECON (مرحله صفر): Knowledge Studio → Knowledge Corpus Factory

تاریخ: 2026-11-10 · شاخه: `pcm-20.9-knowledge-studio-factory` (از `pcm-20.6`)
هدف: تبدیل Word Studio موجود به «کارخانه پیکره دانش» با ۵ مرحله (A–E) + Full Pipeline + Nightly + داشبورد فارسی — **فقط با پیاده‌سازی واقعی و تست‌شده**، بدون دکمه‌ی نمایشی.

---

## ۱. خلاصه‌ی وضعیت کل‌کلانه

| # | کامپوننت | وضعیت | دلیل/اثبات |
|---|---------|-------|------------|
| 1 | آپلود تک‌فایل DOCX → رجیستری | ✅ IMPLEMENTED | `knowledge_add_document` (knowledge_api.py:1366-1447)؛ تست KB-01..KB-04 |
| 2 | **ایمپورت چندفایلی (multi-import)** | ❌ **BROKEN (plan-only)** | ریشه‌ای دقیق در §۳ — هیچ بایت فایلی منتقل/ذخیره نمی‌شود |
| 3 | موتور Jobs پایدار (PCM-12) | ✅ IMPLEMENTED | `knowledge_jobs` + `_submit_job`/`_job_worker` + recover |
| 4 | صف پایدار فایل PCM-15 | ✅ IMPLEMENTED | `knowledge_file_queue` + stages + pause/resume؛ 9 تست Q |
| 5 | Work Registry (PCM-14D) | ✅ IMPLEMENTED | works/editions/volumes + resolve؛ 10 تست RD |
| 6 | متادیتا (fields/values/resolve) | ✅ IMPLEMENTED | 6 scope + merge precedence |
| 7 | Word Factory (8 stage) | ✅ IMPLEMENTED | `factory/service.py`؛ نسخه‌های p-1/n-1/m-2 |
| 8 | Dump d-1 | ✅ IMPLEMENTED (فقط CLI/offline) | `factory/dump.py`؛ 26 تست D؛ **اتصال به API ندارد** |
| 9 | Corpus c-1 | ✅ IMPLEMENTED (فقط CLI/offline) | `factory/corpus.py`؛ 24 تست C؛ **اتصال به API ندارد** |
| 10 | Dataset builder | ✅ IMPLEMENTED (offline) | `corpus/build_dataset.py` + `corpus/tasnim/dataset.py` |
| 11 | **Stage C — Schema Design & Mapping** | ✅ IMPLEMENTED | versions اتمیک + immutable + validate dry-run + approve (PF-C01..C03) |
| 12 | **Stage D — Corpus build + ES index factory** | ✅ IMPLEMENTED | corpus/build (c-1) + ES guarded (blocked بدون `PCT_ES_URL`) (PF-D01..D04) |
| 13 | **Stage E — Search validation** | ✅ IMPLEMENTED | search-acceptance (mock ES) + approve gate (PF-E01..E03) |
| 14 | **RAG publish** | 🟡 GUARDED | قرارداد ingest شناخته‌شده نیست → `rag_status=blocked` (بدون URL) / `failed` (با URL) (PF-F06) |
| 15 | **Full Pipeline runner** | ⬜ NOT_IMPLEMENTED | — |
| 16 | **Nightly scheduler** | ⬜ NOT_IMPLEMENTED | — |
| 17 | **Pipeline dashboard (stage cards)** | ⬜ NOT_IMPLEMENTED | studio.html بدون نمای pipeline است |
| 18 | Audit trail | ✅ IMPLEMENTED | `knowledge_audit_log` (append-only) + `GET /audit` + کارت audit در UI (PF-F07) |
| 19 | OpenAPI | ✅ IMPLEMENTED | 3 spec / 28 operation (PCM-14D/15/20.9) + `pcm19_openapi_check` + CT-01..06 (3 spec) |
| 20 | UI multi-import (frontend) | ✅ IMPLEMENTED | `confirmImport()` → plan + آپلود واقعی تدریجی + retry-failed (Stage A/B، PF-A/B) |

**نتیجه‌ی کلیدی (به‌روز بعد از Stages A..F + OpenAPI):** «ورود» (multi-import) و «خروج» (corpus/dump/release) حالا به API متصل‌اند؛ Stage D/E/F با guard صادقانه (ES/RAG) پیاده و تست‌شده‌اند. باقی‌مانده: pipeline runner/nightly/UI pipeline dashboard + deploy + گزارش.

---

## ۲. روش recon

- خواندن کامل: `backend/knowledge_api.py` (2879 خط)، `dashboard/studio.html` (1678 خط)،
  `backend/factory/{service,models,dump,corpus,export,intake}.py`،
  `backend/pct_test_support.py` + الگوی `backend/test_knowledge_api.py`،
  `corpus/tasnim/versioning.py` (قوانین نسخه‌پذیری v0001 + idempotency content_sha256)،
  `docs/{PCM-15-FILE-QUEUE,PCM-16-CORPUS-BUILDER,PCM-14C.3-DUMP-CONTRACT,PCM-17-STUDIO-UI}.md`،
  `deploy/pcm208_deploy.sh`، `گزارش-PCM-20.8.1-MIZAN-PRODUCTION-ACCEPTANCE.md`.
- پروب زنده (از workstation، 2026-11-10):
  - `http://172.30.0.133:9200/` → **000 (unreachable)** — ES روی هاست production نیست.
  - `https://rag.ai.ismc.ir/` → **200** (پورتال عمومی «رگ»؛ `/health` 200، `/docs` 200، `/api` 301) — API ingest عمومی/مستند **نیافت شد**.
  - `https://corpus.ai.ismc.ir/api/knowledge/collections` → **401** — اپ production زنده و auth درست کار می‌کند.

---

## ۳. ریشه‌یابی Stage A — چرا multi-import «نامعتبر» است

زنجیره‌ی شکست، با شواهد کد:

1. **فرانت‌اند فقط plan می‌فرستد، نه فایل.**
   [`confirmImport()`](dashboard/studio.html) در studio.html:
   ```js
   const j = await fetchAPI('/api/knowledge/import/batches', {
     method: 'POST',
     headers: { 'Content-Type': 'application/json' },
     body: JSON.stringify({
       collection_id: state.collection.collection_id,
       files: importPlan.map((r) => ({ name: r.name, size: r.size, sha256: r.sha256 })),
     }),
   });
   ```
   SHA-256 در کلاینت با `crypto.subtle` محاسبه می‌شود ولی **هیچ‌گاه بایت فایلی POST نمی‌شود** (نه multipart، نه chunked).

2. **سرور plan را در هیچ جدولی ذخیره نمی‌کند.**
   [`knowledge_create_batch`](backend/knowledge_api.py:1705) (خط 1705–1782): فقط یک ردیف در
   `knowledge_import_batches` (PK `batch_id = b-<sha8>`, status `'planned'`, `file_count`)
   INSERT می‌کند. جدولی برای `batch_files`/plan وجود ندارد و هیچ ردیف
   `knowledge_collection_documents` ساخته نمی‌شود.

3. **Process روی مجموعه‌ای خالی اجرا می‌شود.**
   [`_job_kind_process_batch`](backend/knowledge_api.py:1035) (خط 1035–1111):
   ```sql
   SELECT ... FROM knowledge_collection_documents
   WHERE collection_id=? AND status IN ('uploaded','failed')
   ```
   برای بچِ تازه‌ی multi-import این مجموعه **صفر** ردیف است → job با 0 فایل «موفق» تمام می‌شود.
   کاربر ناخودآگاه مجبور است هر فایل را جدا `uploadOne` (تک‌آپلود واقعی) کند — دقیقاً همان
   «نااطمینانی» گزارش‌شده.

4. **batch detail هم scope اشتباه دارد.**
   [`knowledge_batch_detail`](backend/knowledge_api.py:1843) (خط 1843–1879): documents =
   **تمام** اسناد collection و queue rows = **تمام** صف collection — چون
   `knowledge_collection_documents` و `knowledge_file_queue` ستون `batch_id` ندارند
   (grep `batch_id` روی کل فایل: 42 hit، هیچ‌کدام در این دو جدول).

### طراحی رفع (Stage A)
- **جدول افزایشی** `knowledge_batch_files`:
  `(batch_id, seq, file_name, sha256, size_bytes, status, document_id, error, updated_at)`
  — `status ∈ {planned, uploaded, duplicate, size_mismatch, rejected, processed}`.
- **کاملاً idempotent:** `knowledge_create_batch` هر entry plan را در `knowledge_batch_files` ذخیره می‌کند (رفتار فعلی batch row حفظ می‌شود).
- **endpoint جدید** `POST /api/knowledge/import/batches/<batch_id>/files` (multipart،
  پشت auth): فایل را مثل single-upload ذخیره می‌کند (stream 1MB + cap 50MB + SHA-256)،
  سپس **با sha256 با plan match** می‌کند:
  - sha مطابقت دارد → ردیف plan → `uploaded` + document row با `batch_id`؛
  - sha با یک plan entry دیگر یا doc موجود در collection یکسان → `duplicate` (با `existing_document_id`)؛
  - sha در plan نیست → 400 `not_in_plan`؛
  - size نامتفاوت → `size_mismatch`.
- **ستون افزایشی** `batch_id` روی `knowledge_collection_documents` (ALTER TABLE ADD COLUMN + backfill NULL؛ سازگار با تک‌آپلودها = NULL).
- **resume/بازآزمایی:** هر entry `planned` تا آپلود، قابل تکرار است؛ `GET batch` شمارنده‌ی
  `uploaded/file_count` واقعی برمی‌گرداند.
- **رفع scope:** `_queue_ensure_rows` + `_job_kind_process_batch` + batch detail فقط روی
  اسناد همان batch (وقتی batch_id موجود باشد) کار می‌کنند؛ تک‌آپلودها (batch_id NULL)
  همان رفتار قبلی را نگه می‌دارند.

---

## ۴. Stage B — کنترل پردازش بچ

وضعیت: **PARTIAL** — pause/resume (scope `batch:<id>` در `knowledge_queue_control`) و
checkpoint (ستون `stage` = آخرین stage ایمن) موجود است.
رفع‌های لازم:
- `POST /batches/<id>/retry-failed` — فقط queue rows با status `failed` را بازنشانی می‌کند
  (attempt count +1) و job فرآیند را با همان idempotency pattern `_submit_job` می‌سازد.
- scope کردن پردازش به batch (§۳).
- شمارنده‌های زنده از `queue_counters` (بدون عدد ساختگی).

---

## ۵. وضعیت production (اصلاح‌شده)

**هاست واقعی production = `172.30.0.133` (AI-TOOLS)** — **نه** `172.20.1.52`
(طبق `گزارش-PCM-20.8.1`: s52 = "No route to host"؛ DNS `corpus.ai.ismc.ir` روی
172.30.0.133 است). SSH `saber@172.30.0.133`؛ اپ در
`/home/saber/saberprojects/persian-corpus-toolkit`؛ کانتینر
`persian-corpus-toolkit-backend-1` (5055)؛ DB `backend/thesaurus.db`؛ بکاپ
`/home/saber/backups/`.

بانک‌های دانش کاربر در production (هدف اجرای نهایی):

| collection | نام | اسناد | وضعیت |
|---|---|---|---|
| `c-29a205c5` | تفسیر المیزان | 20 (همه parsed؛ 70,251 بلوک / 14,269,034 کاراکتر / quality 1.0) | ✅ آماده‌ی Stage D |
| `c-77bdcbe8` | من لایحضر | 24 | آماده |
| `c-86347897` | کتب امام خامنه ای | 0 | خالی |

Jobs: 44 مورد، همه succeeded. صف خالی. **ES: نه روی 9200/9300، نه کانتینر** (مستند در PCM-20.8.1 + پروب امروز).

### ۵.۲ قرارداد RAG
`rag.ai.ismc.ir` = پورتال عمومی پاسخ‌گویی (سؤال/جواب + think-tank + leaderboard).
هیچ endpoint ingest/corpus عمومی در HTML یا مسیرهای معمول (`/api`, `/docs`) مشاهده
نشد. ⇒ **Publish-to-RAG = UNKNOWN contract → BLOCKED** طبق stop-rules؛ مسیر مستقل
(standalone release) پیاده می‌شود و publish با `PCT_RAG_INGEST_URL`/token قابل فعال‌سازی
می‌ماند (guard: اگر تنظیم نبود → وضعیت `BLOCKED` با دلیل صادقانه در UI/audit).

---

## ۶. قراردادهای موجود قابل‌ری‌استفاده (بازتعریف نمی‌شوند)

| قرارداد | ماژول | نکته |
|---|---|---|
| **d-1** (Dump) | `backend/factory/dump.py` | `generate_dump(wf_dir, dump_dir, source_docx)` — read-only، idempotent، byte-deterministic؛ `validate_dump` V1..V11 |
| **c-1** (Corpus) | `backend/factory/corpus.py` | `build_corpus(dump_dirs, out_dir, require_quality)` — fail-fast اعتبارسنجی همه dumpها قبل از هر نوشتن؛ ZIP قطعی (1980-01-01)؛ hf-package فقط محلی |
| **PCM-15** (Queue) | `knowledge_api.py` | stages `intake→validate→parse→structure→metadata→normalize→quality→export`؛ `stage` = آخرین stage ایمن (نقطه‌ی resume) |
| **Factory** | `backend/factory/service.py` | `DocumentProcessingService(out_dir).process(src, on_stage)`؛ idها قطعی `w-/e-/v-/f-/d-<sha8>` |
| **نسخه‌پذیری** | `corpus/tasnim/versioning.py` | الگوی `v0001` افزایشی + `find_reusable_version` (idempotency با content_sha256) — الگوبرداری برای index-builds و corpus-builds |
| **تست** | `pct_test_support.py` | DB مشترک موقت + `reset_db()` در setUp + `PCT_KNOWLEDGE_DATA_DIR` موقت؛ fixture DOCX فارسی با `factory/_smoke_fixtures.make_docx(path, [(style, text), ...])` |
| **Deploy** | `deploy/pcm208_deploy.sh` | backup+integrity → اسنپ‌شات → `git archive` commit → extract → blob verify → `build backend && up -d backend` (هرگز نه `down -v`) → smoke |

---

## ۷. نگاشت stop-rules → تصمیم طراحی

| Stop rule | تصمیم |
|---|---|
| تغییر مخرب DB | فقط `CREATE TABLE IF NOT EXISTS` + `ALTER TABLE ... ADD COLUMN` (بدون DROP/RENAME/تغییر نوع) |
| بازنویسی operational index | ES اصلاً وجود ندارد؛ factory با guard env (`PCT_ES_URL`) — اگر unset → `BLOCKED`، هیچ تلاش اتصال/ساخت سرویس |
| اختلال در RAG collection | publish فقط با endpoint جدا و guard؛ در نبود قرارداد → `BLOCKED` |
| تغییر alias زنده بدون acceptance | alias switch فقط بعد از `Approve Index Version` (Stage E) |
| نصب سرویس جدید | **هیچ**؛ nightly = cron روی هاست s52 که اسکریپت python موجود (venv همان کانتینر/هاست) را صدا می‌زند — نه thread اپ، نه سرویس تازه |
| قرارداد RAG ناشناخته | `BLOCKED` + ثبت در audit + راهنمای اپراتور |
| بکاپ گم‌شده | deploy استاندارد (backup + integrity قبل/بعد) |
| job متضاد | `_submit_job` با `job_key` یکتا + per-collection lock (ردیف lock در جدول pipeline) |

---

## ۸. طراحی کلی Stage C–E + Pipeline

### Stage C — Schema Design & Mapping
- جدول `knowledge_schema_versions` (افزایشی):
  `schema_id` PK (`sv-<sha8>`), `collection_id`, `version` (1,2,...), `name`,
  `definition` (JSON: `{fields:[{key, type, required, source, mapping}], mapping:{...}}`),
  `status ∈ {draft, valid, approved, superseded}`, `validated_at`, `approved_at`,
  `created_at` — **immutable پس از validate** (تغییر = نسخه‌ی جدید).
- `POST /api/knowledge/collections/<id>/schemas` (draft) →
  `POST /schemas/<id>/validate` (`Design & Validate`: schema را روی N سند واقعی
  collection dry-run می‌کند: پوشش فیلدها، نوع، نمونه‌های خالی → گزارش) →
  `POST /schemas/<id>/approve` (`Approve Schema Version` → status `approved` +
  `collection.schema_version` به `sv-...` اشاره می‌کند؛ نسخه‌ی قبلی `superseded`).
- `GET /schemas` / `GET /schemas/<id>` (با dry-run report).

### Stage D — Corpus export + ES index factory
- `POST /collections/<id>/corpus/build` (job):
  1. برای هر doc `parsed` → `factory.dump.generate_dump(out_dir, dump_dir, source_docx)` (d-1)؛
  2. `factory.corpus.build_corpus(dump_dirs, corpus_dir)` (c-1) → `corpus-data.zip` + raw/normalized + hf-package؛
  3. ثبت در `knowledge_index_builds` (جدول موجود: `iv-<sha8>`) با `content_sha256` و مسیر خروجی + idempotency (همان content → REUSED).
- **ES (guarded):** اگر `PCT_ES_URL` تنظیم نبود → build `corpus-only` تمام می‌شود و
  بخش ES با وضعیت `BLOCKED (no PCT_ES_URL)` ثبت می‌شود. اگر تنظیم بود:
  - index نام `knowledge_<collection_slug>_v0001` (الگوی `versioning.py`؛ افزایشی)؛
  - bulk-index بلوک‌های normalized + متادیتای resolve + mapping از schema approved؛
  - **atomic alias switch** روی `es_alias` (`pct-col-<slug>`) فقط پس از صفر بودن خطا +
    شمارش‌های مطابقت؛ **rollback** = برگرداندن alias به index قبلی (هر دو index زنده می‌مانند).
- `GET /collections/<id>/corpus/builds` + `GET /builds/<iv_id>` (manifest + hashes).

### Stage E — Search validation + acceptance
- `POST /collections/<id>/search-acceptance` (job) — **guard:** بدون ES → `BLOCKED`.
  با ES: 10 دسته‌ی تست (فارسی: exact-match بلوک، partial، تیتر/فصل، work/edition/volume
  filter، متادیتای scope، pagination/consistency، determinism دو اجرای یکسان،
  absence (سند حذف‌شده نباشد)، cross-collection isolation، latency smoke).
  هر test: query + انتظار + نتیجه (pass/fail + شواهد).
- `Approve Index Version` = `POST /index-builds/<iv_id>/approve` →
  `collection.current_index_build` + `validation_status='accepted'` + alias نهایی.
  بدون pass کامل → `NEEDS_REVIEW`.

### Final — Release
- **Standalone (همیشه قابل اجرا):** `POST /collections/<id>/release` → بسته‌ی
  `release-<ts>.zip`: corpus-data.zip (c-1) + dumps (d-1) + manifest زنجیره‌ای
  (hash هر لایه) + dataset (pct قابل‌انتخاب) + README provenance. دانلود از
  `GET /releases/<id>/download` (پشت auth).
- **RAG (guarded):** `PCT_RAG_INGEST_URL` + token؛ در نبود → `BLOCKED (unknown RAG contract)`.
- **Audit trail:** جدول `knowledge_audit_log` (append-only):
  `(ts, actor_session, collection_id, stage, action, status, detail_json)` —
  هر اقدام pipeline/acceptance/approve ثبت می‌شود.

### Full Pipeline
- جدول `knowledge_pipeline_runs`:
  `(run_id, collection_id, trigger ∈ {manual, nightly}, status ∈ {running, paused, done, failed}, stage_states (JSON), created_at, finished_at)` +
  ردیف lock per-collection (`pipeline_lock`): اگر run فعال هست → 409 `conflicting_job`.
- Machine وضعیت stage: `A_IMPORT → B_PROCESS → C_SCHEMA → D_BUILD → E_ACCEPT → RELEASE`
  هر stage مستقل قابل اجراست؛ **checkpoint:** `stage_states` بعد از هر stage پایدار می‌شود؛
  `Run Full Pipeline` از اولین stage **غیر-SUCCESS** شروع می‌شود (idempotent — شکست
  Stage E، Stage A/B را از نو اجرا نمی‌کند).
- وضعیت‌های UI: `NOT_STARTED/READY/RUNNING/PAUSED/SUCCESS/FAILED/NEEDS_REVIEW/BLOCKED/STALE`
  (STALE = job روی job_row بیش از threshold بدون progress).
- `POST /collections/<id>/pipeline/run` (از stage انتخابی) + `pause`/`resume` +
  `GET /pipeline/status` (یک endpoint برای همه‌ی stage cards).

### Nightly
- **cron روی هاست s52** (نه thread اپ، نه سرویس جدید):
  `*/0 3 * * * /home/saber/saberprojects/persian-corpus-toolkit/deploy/pcm209_nightly.sh`
  — اسکریپت: بکاپ سریع → venv python → تابع `run_nightly()` در
  `knowledge_api.py` (فقط collectionهایی که در جدول `knowledge_pipeline_schedules`
  با `enabled=1` ثبت شده‌اند؛ default OFF) → هر run با per-collection lock.
- `GET/POST /api/knowledge/pipeline/schedules` (enable/disable/cron-time per collection) —
  همه در DB؛ UI یک سوییچ ساده.

### UI (studio.html)
- تب/کارت جدید «خط لوله پیکره» در pane workspace: 6 کارت stage (A–E + Release) با
  وضعیت + شمارنده‌های واقعی (از `GET /pipeline/status`) + دکمه‌های
  `Run Stage` / `Run Full Pipeline` / `Pause` / `Resume` / `Approve`؛
  بخش multi-import بازسازی می‌شود: plan → آپلود تدریجی فایل‌ها با progress per-file
  (fetch multipart تکی + retry) → شمارنده‌ی `uploaded/file_count` زنده.
- همه‌ی fetchها `credentials:'same-origin'` + `escHtml` برای خروج DOM (قاعده ۸).

---

## ۹. برنامه‌ی تست

- ماژول جدید `backend/test_pipeline.py` (نام test: **PF-xx**) — با الگوی
  `pct_test_support` + `_smoke_fixtures.make_docx` (DOCX فارسی واقعی) + 1 فایل خراب
  (OLE2/.doc جعلی یا zip خراب):
  - Stage A: plan persist؛ آپلود 5 فایل فارسی (match/دوباره/خارج از plan/size-mismatch/duplicate)؛ resume بعد از قطعی؛ process batch = فقط فایل‌های batch (scope).
  - Stage B: pause در میانه، resume، retry-failed فقط failedها.
  - Stage C: draft→validate (dry-run روی اسناد واقعی)→approve→supersede؛ immutability.
  - Stage D: corpus build واقعی از dumpهای d-1 (content_sha256 + REUSED)؛ ES guard → BLOCKED بدون `PCT_ES_URL`؛ (با mock ES client: index naming + alias switch + rollback).
  - Stage E: guard BLOCKED بدون ES؛ با mock: 10 دسته + approve → `current_index_build` + `validation_status`.
  - Pipeline: run full روی 2 فایل (1 خراب) → A/B SUCCESS با NEEDS_REVIEW؟ (فایل خراب → doc `failed` + batch نهایی `NEEDS_REVIEW`، pipeline ادامه می‌دهد تا D/E روی parsedها)؛ checkpoint: شکست مصنوعی در E → re-run فقط E؛ lock: run دوم هم‌زمان → 409.
  - Release: zip شامل corpus+dumps+manifest با hash معتبر (validate d-1 روی خروجی).
  - Audit: هر اقدام در `knowledge_audit_log`.
  - Nightly: تابع `run_nightly` با schedule غیرفعال = no-op؛ فعال = run ثبت‌شده.
- رگرسیون کامل: 216 تست موجود (200 رگرسیون + 16 T) + تست‌های جدید باید سبز بماند.

---

## ۱۰. ریسک‌ها و ناشناخته‌ها

1. **ES وجود ندارد** — Stage D/E عملاً `BLOCKED` تا زمانی که `PCT_ES_URL` روی هاست
   production فراهم شود (خارج از scope این مأموریت؛ stop-rule: نصب سرویس ممنوع).
   تمام منطق ES با **mock** تست می‌شود و guard صادقانه گزارش می‌دهد.
2. **قرارداد RAG نامشخص** — publish با guard؛ مستندسازی در راهنما.
3. **حجم production:** Mizan = 70K بلوک — dump/corpus build باید job باشد (خودکار
   خواهد بود) و نه در-request.
4. **Windows dev:** handle باز SQLite → `pct_test_support` حل شده است؛ test‌های جدید
   همان الگو را رعایت می‌کنند.
5. **تنوع داده‌ی 24 doc «من لایحضر»** — dry-run schema (Stage C) دقیقاً برای همین است؛
   approval فقط بعد از مشاهده‌ی گزارش واقعی.

---

## ۱۱. ترتیب اجرای commit (feature branch)

1. `[recon]` این سند ✅
2. Stage A: جدول `knowledge_batch_files` + endpoint آپلود batch + `batch_id` روی documents + scope process/detail
3. Stage B: retry-failed + شمارنده‌ها + UI آپلود تدریجی multi-import
4. Stage C: schema versions + validate/dry-run + approve
5. Stage D: corpus/dump build job (c-1/d-1) + ES guarded factory + alias/rollback
6. Stage E: search acceptance (guarded + mock) + approve index
7. Final: release standalone + RAG guarded + audit log
8. Pipeline runner + schedule (nightly hook) + UI pipeline dashboard
9. OpenAPI operations + `deploy/pcm209_openapi_check.py`
10. تست‌های PF + رگرسیون کامل سبز
11. deploy/pcm209_deploy.sh (الگوی pcm208) + اجرای واقعی روی c-29a205c5 / c-77bdcbe8
12. `گزارش-PCM-20.9-KNOWLEDGE-STUDIO-FACTORY.md` (24 بخش) + راهنمای اپراتور فارسی

---

## ۱۲. لاگ اجرای واقعی (به‌روزرسانی زنده)

### Stage A — ✅ (تست‌های PF-A01..A05 سبز)
- جدول `knowledge_batch_files` + `batch_id` روی `knowledge_collection_documents` (additive).
- `POST /collections/<id>/import/plan` + `POST /import/upload` (مطابقت plan + size + duplicate → 409/400/409) + `POST /batches/<id>/process` (فقط scope batch).
- شمارنده‌های زنده: `uploaded/file_count` روی batch + `GET /batches/<id>`.

### Stage B — ✅ (تست‌های PF-B01..B03 سبز)
- `POST /batches/<id>/retry-failed` (فقط failedها؛ بدون failed → 409) + delete/restore فایل موقت + retry.
- resume تدریجی multi-import در UI (upQueue + progress per-file).

### Stage C — ✅ (تست‌های PF-C01..C03 سبز)
- `knowledge_collection_schemas` + `knowledge_schema_fields` (versions اتمیک، immutable پس از approve)
  + `validation_status` روی collection (`pending→validating→ready_for_approval→approved|needs_review`).
- validate = dry-run واقعی روی بلوک‌های parse‌شده (missing/frequency per field)؛ approve فقط با
  `report.overall=pass` و پوشش کامل فیلدهای required.

### Stage D — ✅ (تست‌های PF-D01..D04 سبز)
- `POST /collections/<id>/corpus-build` (job؛ idempotent) → پیکره canonical `c-1` از
  `knowledge_blocks` (RAW + NORMALIZED جدا + provenance + dedup) + `GET /corpus-builds`.
- کارخانه‌ی ایندکس ES guarded: بدون `PCT_ES_URL` → `es_index_status='blocked'` صادقانه؛
  با ES: `PUT <name>_vNNNN` (mapping واقعی) → bulk (idهای idempotent) → `_refresh` →
  count verification → `/_aliases` atomic (remove+add) → rollback alias اگر count mismatch.
- reuse: اگر alias به همان index اشاره کند و count برابر باشد → بدون rebuild.

### Stage E — ✅ (تست‌های PF-E01..E03 سبز)
- `POST /collections/<id>/search-acceptance` (job؛ guarded: بدون ES یا بدون Stage D build → 409/BLOCKED).
- ۱۰ دسته: count / exact_block (match_phrase + exact-source) / partial_text / heading_filter
  / work_filter (keyword) / metadata_filter (`.keyword`) / pagination (sort `_id`، stable) /
  determinism / absence / latency (budget 30s). خروجی: `search_status` +
  `search_detail` (report `sa-1` JSON: overall/pass/fail/skipped + failed[]) روی build row.
- guard صادقانه: شکست هر دسته → `search_status='fail'` + `validation_status='needs_review'`
  + `POST /index-builds/<iv_id>/approve` → 409 `acceptance_not_passed`.
- approve: فقط با `search_status='pass'` و `es_index_status='success'` →
  `validation_status='accepted'` + `current_index_build=<iv_id>` (تأیید هر دو آدرس
  `current_index_build` و `current_schema` روی collection).
- تست با mock ES در سطح `_es_request` (build + acceptance روی یک fake cluster با alias map).

### Final (Release) — ✅ (تست‌های PF-F01..F07 سبز)
- `POST /collections/<id>/release` (job؛ guarded: بدون Stage D build → 409 `no_corpus_build`)
  → باز-verify sha آرشیو corpus روی دایسک + باز-اعتبارسنجی کامل هر dump (d-1، V1..V11)
  + zip قطعی (fixed timestamp 1980-01-01، deflate، مرتب‌شده) + **release-manifest کنار
  zip (side-car، نه داخل zip — چون container نمی‌تواند خودش را hash کند، مثل c-1)** +
  README + زنجیره‌ی hash (corpus archive → dumps root → data zip).
- RAG guarded و صادقانه: بدون `PCT_RAG_INGEST_URL` → `rag_status='blocked'`؛
  با URL → POST واقعی (payload: kind/contract/release_id/zip_sha256/manifest_sha256 +
  `Authorization: Bearer`)؛ خطا → `failed` (release خراب نمی‌شود).
- `GET /collections/<id>/releases` + `GET /releases/<release_id>/download`:
  download **مجدداً hash می‌گیرد**؛ mismatch → 409 `hash_mismatch` + ثبت audit.
- idempotent: هم‌محتوا → همان `release_id` + reuse zip (سطر تکراری نمی‌سازد).
- stale corpus: آپلود جدید بعد از build → release job `failed` (stale) تا Stage D دوباره.
- **audit trail**: جدول `knowledge_audit_log` (append-only؛ actor = `sess-<sha8>` برای
  اکشن‌های request یا `worker` برای job) + `GET /collections/<id>/audit` (limit/offset) +
  کارت «ردیابی اقدامات» در UI (فیلتر stage/action).
- `test_pipeline`: 28/28 سبز (A5+B3+C3+D4+E3+F7+T0... A..F).

### OpenAPI — ✅ (spec سوم + CT به‌روز)
- `docs/openapi/pcm209-pipeline-release.openapi.yaml` — ۹ operation جدید
  (corpus/build، corpus/builds، index-builds/<iv_id>، search-acceptance،
  index-builds/<iv_id>/approve، release، releases، download، audit) + schemas
  (JobObject/JobResult/IndexBuild/Release/AuditEntry/Error).
- `test_api_contract`: `SPECS` به ۳ spec؛ `len(specs)==3`؛ `_path_url` مقدار عددی
  برای `coll_id` (converter `<int:...>`).
- `deploy/pcm19_openapi_check.py`: **3 specs, 28 operations** — OK.

### وضعیت رگرسیون (آخرین اجرا)
- `test_pipeline`: 28/28 سبز (A5+B3+C3+D4+E3+F7 = ۲۵ کلاس، ۲۸ تست).
- رگرسیون کامل روی **Python 3.13** (با PyYAML، هم‌شکل CI): **228 تست → OK، 0 skip**
  (200 موجود + 28 pipeline؛ CT-01..06 با ۳ spec سبز).
- روی Python 3.14 (32-bit، بدون PyYAML): 228 تست → OK (10 skip CT، پیشین).
- UI: کارت «ریلیز پیکره» (Build + releases + RAG badge) + کارت «ردیابی اقدامات»
  (audit log با فیلتر) + JS syntax OK (node).

### باقی‌مانده
- Pipeline runner + schedule (nightly hook) + UI pipeline dashboard (چند stage زنجیره‌ای).
- deploy/pcm209_deploy.sh + اجرای واقعی روی s52 (host در دسترس نبود).
- `گزارش-PCM-20.9-KNOWLEDGE-STUDIO-FACTORY.md` (24 بخش) + راهنمای اپراتور فارسی.

---

*بخش ۱۲ به‌روزرسانی زنده است؛ بقیه‌ی مراحل (Pipeline runner، Nightly، UI pipeline
dashboard، deploy، گزارش) در همین سند ثبت می‌شوند.*

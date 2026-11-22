# PCM-STUDIO-BATCH — عملیات گروهی کتابخانهٔ Word (پردازش همه / توقف / تأیید همه)

**تاریخ:** ۲۰۲۶-11-22 · **شاخه:** `pcm-20.9-knowledge-studio-factory` · **وضعیت:** ✅ کامل — بدون deploy (سوار درِ M7)

## ۱. مسئله (قبل)

در استودیو (کتابخانهٔ Word)، کاربر برای هر سند باید جداگانه روی «پردازش» و سپس
«تأیید» کلیک می‌کرد. درخواست:

> «یا یک دکمه پردازش همه فایل‌های پردازش‌نشده — یا یک دکمه‌ی تایید همه تاییدنشده‌ها»

روش انتخابی (تأییدشده توسط owner): **روش B** — دو (سه) endpoint بک‌اند + دکمه‌های
toolbar با شمارندهٔ زندهٔ سمت‌سرور.

- طرح: `docs/superpowers/specs/2026-11-22-word-studio-batch-ops-design.md`
- پلن اجرایی: `docs/superpowers/plans/2026-11-22-word-studio-batch-ops.md` (۷ task، TDD)

## ۲. آنچه ساخته شد

### APIهای جدید (همه `POST`، پشت auth PCM-09، مسیر `coll_id` = کالکشن)

| Endpoint | رفتار | پاسخ‌ها |
|---|---|---|
| `/api/knowledge/collections/<id>/documents/process-all` | یک job `process_collection` روی **کل** اسناد `uploaded`/`failed` کالکشن (mirror worker بچ‌ها: صف پایدار، pause-check بین هر سند، safety-net قفل queue)؛ `idempotency_key=collection:<id>`؛ `force_retry=True` (دوبار زدن = resume همان job)؛ قبل از submit پرچم pause کلیر می‌شود | `202 {ok, job, files_queued, resubmitted:false}` · `200 resubmitted:true` · `404` · `409 code:no_files_to_process` |
| `/api/knowledge/collections/<id>/documents/pause` | set پرچم pause روی scope `collection:<id>`؛ worker بعد از پایان سند جاری تمیز می‌ایستد (job → `interrupted`، stage=`paused`) | `200 {ok, paused:true, scope, queue_control}` · `404` |
| `/api/knowledge/collections/<id>/documents/approve-all` | UPDATE اتمیکِ همهٔ `parsed`/`needs_review` → `approved` + `_refresh_book_count` + یک خط audit `approved_all` با `detail_json={"count": n}` | `200 {ok, approved:n}` · `404` · `409 code:no_docs_to_approve` |

### تغییر افزایشی خواندنی

- `GET /api/knowledge/collections/<id>/documents` کلید **`status_counts`** جدید
  (GROUP BY status روی کل کالکشن — مستقل از صفحه/جستجو؛ عدد ساختگی نیست، شمارندهٔ واقعی DB).

### UI (`dashboard/studio.html` — کتابخانهٔ Word)

- سه دکمه در `.doc-toolbar` بعد از `importBtn`:
  - `#procAllBtn` «پردازش همه (n)» — n = uploaded+failed (زنده)؛
  - `#pauseAllBtn` «توقف پردازش» — فعال فقط وقتی job `process_collection` همین کالکشن active است؛
  - `#apprAllBtn` «تأیید همه (n)» — n = parsed+needs_review (زنده).
- `state.docStatusCounts` از `status_counts` پر می‌شود؛ `state.collJobActive` از لیست jobs؛
  `updateDocsToolbar()` هر دو را sync می‌کند.
- در حین job فعال، تایمر خودکار (2.5s) علاوه بر `refreshJobs()`، `renderDocs()` هم می‌زند تا
  وضعیت/شمارنده‌ها زنده به‌روز شوند.

### OpenAPI (PCM-19)

- `docs/openapi/pcm15-file-queue.openapi.yaml`: سه operation جدید
  (`processAllDocuments`, `pauseCollectionDocuments`, `approveAllDocuments`) — spec حالا **8 operation**؛
  چک‌کن CI: `deploy/pcm19_openapi_check.py` → OK 3 specs, 31 operations.

## ۳. مهاجرت

**هیچ** — بدون تغییر schema. فقط کلید افزایشی در JSON (`status_counts`) + routeها.
`knowledge_jobs`/`knowledge_queue_control` از قبل ستون `stage`/scope را داشتند.

## ۴. تست (TDD — هر task: تستِ FAIL → پیاده‌سازی → PASS → commit)

| تست | آنچه ثابت می‌کند | نتیجه |
|---|---|---|
| S-05a/b/c | 401 / 404 / 409 `no_files_to_process` | ✅ |
| S-06 | ۲ سند (کتاب سالم + docx خراب) → ۱ job، `files_queued=2`، job succeeded progress=2، وضعیت‌های پایانی `["failed","parsed"]`، صف بدون سطر open | ✅ |
| S-07 | POST دوم حین اجرا → 200 `resubmitted`، همان job_id، دقیقاً ۱ سطر job (worker دوم نیست) | ✅ |
| S-08 | pause → `queue_control` در DB؛ run با pause active → job `interrupted` + همه اسناد دست‌نخورده؛ POST دوباره → succeeded + پرچم پاک | ✅ |
| S-09a/b/c | 401 / 404 / 409 `no_docs_to_approve` | ✅ |
| S-10 | حالت مخلوط: فقط `parsed` تأیید می‌شود (`approved=1`)، سند `uploaded` دست‌نخورده؛ دقیقاً ۱ خط audit با count=1؛ فراخوانی دوم → 409 | ✅ |
| S-11 | `status_counts` == محاسبهٔ مستقیم از DB و در `per_page=1` هم یکسان (مستقل از صفحه‌بندی) | ✅ |

نکتهٔ determinism: دو docx با محتوای ثابت (`make_sample_book`) در همان ثانیهٔ DOS timestamp
byte-identical و هم‌SHA می‌شوند → dedup؛ deshalb تست‌های چندسندی از `make_broken_docx`
به‌عنوان فایل دوم استفاده می‌کنند (الگوی موجود S-03).

## ۵. رگرسیون کامل

```
cd backend && python -m unittest test_api test_projects test_dashboard \
  test_knowledge_api test_word_factory test_dump test_work_registry test_queue \
  test_corpus_builder test_studio_api test_api_contract -v
```

**243 تست · OK · 0 failure · 0 error · 0 skip** (232 baseline + 11 تست S جدید؛
اجرا با python `.venv` — PyYAML موجود، همهٔ 18 تست CT فعال و سبز).

## ۶. Commits (روی `92439ee`)

| SHA | موضوع |
|---|---|
| `38c5cf2` | feat(knowledge): status_counts in documents list (additive) |
| `6a14dbb` | feat(knowledge): process-all documents (job kind process_collection) |
| `d5d1a5b` | feat(knowledge): pause-all documents endpoint |
| `574b990` | feat(knowledge): approve-all documents endpoint |
| `a724d00` | docs(openapi): declare process-all / pause / approve-all operations |
| `3caa5f7` | feat(studio-ui): toolbar buttons پردازش همه / توقف پردازش / تأیید همه |
| `eceb2fb` | docs: این گزارش + خط roadmap در AGENTS.md |

## ۷. git status

درخت بعد از commit این گزارش **پاک** است (`git status --short` خالی).

## ۸. دپلوی / بکاپ

- **بدون deploy** — دیتابیس production لمس نشده (همهٔ تست‌ها روی DB موقت مشترک
  `pct_test_support`)؛ DB bind-mount شده نیازی به rebuild کد ندارد تا دپلوی.
- سوار **درِ M7** (PCM-EXT-07 — deploy کد روی s52 جدید `172.30.0.133`)؛
  پیش‌نهاد: ابتدا staging، سپس smoke test روی UI استودیو توسط owner، بعد production.
- Rollback = rollback همان دپلوی (هیچ تغییر schema/دادهٔ ماندگار در این مأموریت نیست).

## ۹. موارد باقی‌مانده

- UI زنده در مرورگر (staging) — پس از دپلوی M7.
- درِ M7: تأیید صریح owner برای deploy کد روی s52 (هنوز باز).

## ۱۰. روش تست دستی (بعد از دپلوی)

1. وارد استودیو → یک کالکشن با چند سند `uploaded` باز کن.
2. دکمه «پردازش همه (n)» → job در پنل jobs زنده پیش می‌رود؛ وضعیت‌ها صفحه‌به‌صفحه عوض می‌شوند.
3. حین اجرا «توقف پردازش» → job بعد از سند جاری می‌ایستد (`interrupted`/paused).
4. «پردازش همه» دوباره → همان job ادامه می‌دهد تا پایان.
5. «تأیید همه (m)» → فقط اسناد parsed/needs_review approve می‌شوند؛ audit یک خط می‌گیرد.
6. دکمه‌ها وقتی کارندار نباشند disabled هستند و شمارنده‌ها عدد واقعی DB را نشان می‌دهند.

## ۱۱. نتیجه production

کاربردی (بدون deploy) — نتیجه production = همان رفتار فعلی s52؛ تغییرات با اولین
دپلوی بعدی (M7) فعال می‌شوند.

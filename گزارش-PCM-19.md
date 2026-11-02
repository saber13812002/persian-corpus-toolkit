# گزارش PCM-19 — قرارداد API: تست‌های CT-01..CT-06 + GitLab CI + نمونه کلاینت REST + چک‌کن OpenAPI + به‌روزرسانی اسناد

- **تاریخ:** 2026-11-02 (Asia/Tehran)
- **base:** `c30c49f` (گزارش PCM-18)
- **commit کد + اسناد:** `0340caa` (`0340caaba3028efeb301ac8146e02cc7428186df`)
- **deploy:** **خیر** — هیچ deploy/restart/تغییری روی s52 انجام نشد.

---

## A. خلاصهٔ نتایج

| # | نتیجه | مدرک |
|---|-------|------|
| 1 | **رگرسیون کامل 200/200 روی Python 3.13** (11 ماژول از جمله `test_api_contract`) | `Ran 200 tests in 81.241s — OK` (بخش E.1) |
| 2 | **رگرسیون کامل 200 تست روی Python 3.14** — `OK (skipped=10)`؛ هر ۱۰ skip صادقانه «PyYAML not installed» است (تنها این interpreter ندارد) | `Ran 200 tests in 77.362s — OK (skipped=10)` (بخش E.2) |
| 3 | 18 تست قرارداد جدید CT-01..CT-06: دو spec OpenAPI (19 operation) حالا **به‌صورت ماشینی** در مقابل app زنده نگه‌داری می‌شوند | [`backend/test_api_contract.py`](backend/test_api_contract.py) (جدید، 18 تست) |
| 4 | 3 نقص مشخصه PCM-14D رفع شد (quote نداشتن title، دو description بدون quote)؛ هر دو spec با `openapi: 3.0.3` parse می‌شوند و `deploy/pcm19_openapi_check.py` خروجی «OpenAPI check passed: 2 specs, 19 operations» (exit 0) می‌دهد | [`docs/openapi/pcm14d-knowledge-work-registry.openapi.yaml`](docs/openapi/pcm14d-knowledge-work-registry.openapi.yaml) (اصلاح) + [`deploy/pcm19_openapi_check.py`](deploy/pcm19_openapi_check.py) |
| 5 | **CI فقط-تست** ([`.gitlab-ci.yml`](.gitlab-ci.yml)) — 3 job: `regression` (200 تست) / `openapi` (چک‌کن spec) / `client` (py_compile + `--help` کلاینت)؛ **هیچ job deploy ندارد** (قاعدهٔ AGENTS §2: استقرار فقط دستی) | YAML validated + هر سه اسکریپت job جداگانه اجرا و سبز (بخش E.4) |
| 6 | **نمونه کلاینت REST** برای مصرف‌کنندهٔ خارجی — فقط stdlib (بدون pip)، فقط خواندنی، رمز از env/فایل (هرگز hardcode)؛ e2e روی server واقعی throwaway: login → collections → works+editions → batches + queue counters → قرارداد 404 → **exit 0** | [`deploy/pcm19_rest_client_sample.py`](deploy/pcm19_rest_client_sample.py) (جدید، ~320 خط) |
| 7 | راهنمای اپراتور OpenAPI: [`docs/openapi/README.md`](docs/openapi/README.md) — فهرست specها/contract، ماتریس CT، راهنمای چک‌کن و کلاینت، چرایی CI | جدید |
| 8 | به‌روزرسانی اسناد: `readme.md` (جدول امکانات سطر 8e، معماری 11 فایل/200 تست، درخت پروژه، بخش تست، backlog «CI فعال شد»، roadmap + PCM-18/19) و `AGENTS.md` (دستور رگرسیون + 200 تست + ماژول 18تستی، ساختار فنی، roadmap) | diff: `readme.md` 16+/-، `AGENTS.md` 14+/- (بخش D) |
| 9 | gates سبز: `git diff --check` تمیز؛ secret scan (patterns PAT/AWS/private-key/`password=`/`Bearer`) → 0 hit واقعی؛ `git status` = دقیقاً 8 ورودی PCM-19 (3 modified + 5 جدید)؛ فایل throwaway seed حذف شده | بخش E.5 |
| 10 | push بدون force + SHA با `git ls-remote` تأیید: GitHub `main` = Local `0340caa` | بخش G/H |

## B. وضعیت قبل از PCM-19 (baseline)

1. **دو مشخصه OpenAPI** موجود بودند اما **هیچ test/CI** آن‌ها را نگه‌داشت: `pcm14d-knowledge-work-registry.openapi.yaml` (14 operation) و `pcm15-file-queue.openapi.yaml` (5 operation). spec PCM-14D سه نقص YAML داشت (سطر 3 بدون quote + دو description) که parse را در بعضی parserها شکننده می‌کرد.
2. **182 تست** در 10 ماژول (آخرین: `test_studio_api.py` — PCM-17).
3. **CI نبود** — backlog `readme.md` صریحاً «CI (unittest + lint)» را باز داشت. GitLab CE روی s52:2222 mirror است ولی pipeline تعریف نشده بود.
4. **نمونه کلاینت برای مصرف‌کنندهٔ خارجی نبود** — تنها کلاینت‌ها dashboard/studio.html (JS درون‌خطی) و اکستنشن Chrome بودند.
5. roadmap: PCM-17 آخرین ✅؛ PCM-18 (ممیزی s52) انجام شده بود ولی s52 در زمان آن ردیاب نبود (5× timeout) و دو اسکریپت `pcm17_s52_readonly_check.sh` / `pcm18_s52_observability_audit.sh` در انتظار اجرا.

## C. طراحی / رویه

### C.1 تست‌های قرارداد — [`backend/test_api_contract.py`](backend/test_api_contract.py) (18 تست)

| ماتریس | تست | چه چیزی ثابت می‌کند |
|---|---|---|
| CT-01 (4) | صحت spec | parse YAML + `openapi: 3.x` + `info.title/version/paths/schemas` غیرخالی؛ هر operation دارای `operationId` با الگوی `[A-Za-z][A-Za-z0-9]*`؛ هر `$ref` محلی حل شود (با unescape `~0`/`~1` JSON Pointer)؛ پارامترهای `in: path` = `{param}`های template |
| CT-02 (1) | پوشش spec⊆app | هر (path, method) هر دو spec در url_map app زنده وجود دارد؛ normalize `<converter:name>`→`{name}`؛ مجموع ≥ 19 operation؛ لیست missing خالی |
| CT-03 (1) | قرارداد auth | هر 19 operation **بدون session → 401**، با method دقیق اعلان‌شده (جدول method→sender شامل PATCH/PUT — چون 405 در routing Flask **زودتر** از decorator auth می‌آید) |
| CT-04 (2) | shape زنده ↔ schema | ردیف بچ (201 ساخته‌شده) ⊇ `ImportBatch` + `queue.counters` ⊇ `QueueCounters`؛ work/edition/volume ساخته‌شده ⊇ schemaهای `Work`/`Edition`/`Volume` + idempotent re-create (`created:false`) |
| CT-05 (8) | قرارداد خطاها | 400+`field` (collection_id / key / volume_no) · 404 (collection/work/batch نامشخص) · cap `per_page` روی 100 · فیلدهای صفحه‌بندی int + `total_pages` |
| CT-06 (2) | یکتایی | operationId در کل دو spec یکتا؛ هیچ (path, method) تکراری بین specها |

نکات پیاده‌سازی (درس‌های این مرحله):
- `pct_test_support` **اول** import می‌شود (پیش از `server`) — همان قاعدهٔ PCM-12.3؛ `reset_db()` در هر `setUp`.
- `assertEqual` ناموفق داخل `subTest` جریان را می‌شکند؛ شمارنده‌ها (مثل `checked += 1`) باید در مقابل این مقاوم باشند — در CT-03 شمارنده قبل از assert نیست و assert در subTest می‌ماند تا همه 19 مورد سنجیده شوند.
- تست‌های CT-01/CT-02 (6 تست yaml + 4 وابسته) با `@unittest.skipUnless(yaml is not None)` — در interpreter بدون PyYAML **صادقانه skip** می‌شوند، نه silent-pass.

### C.2 CI — [`.gitlab-ci.yml`](.gitlab-ci.yml)

- **image:** `python:3.12-slim` (همان image production در [`backend/Dockerfile`](backend/Dockerfile)) + `pip install -r backend/requirements.txt pyyaml`.
- **فقط 1 stage `test` با 3 job** — آگاهانه **بدون job deploy** (AGENTS §2 قاعدهٔ «بدون تست سبز deploy نمی‌شود» + استقرار همیشه دستی با `deploy/pcm04_deploy.sh`).
- **`PCT_DASHBOARD_PASSWORD` عمداً تعریف نمی‌شود** — `pct_test_support` آن را با `os.environ.setdefault` روی `test-secret-123` می‌گذارد و همه ماژول‌های تست همین fixture را hardcode کرده‌اند؛ تعریف خارجی `setdefault` را باطل می‌کرد و **همهٔ تست‌های login را 401 می‌کرد** (نقصی که در پیش‌نویس اول CI بود و قبل از commit اصلاح شد).
- `PCT_DB` به فایل موقت job-point می‌زند (`/tmp/pct-ci-$CI_JOB_ID.db`) — هر job DB تازه، بدون نشت state.
- job `client` با `python -m py_compile` هر دو اسکریپت pcm19 + اجرای `--help` کلاینت (نه `python -c` چندخطی که در cmd/YAML شکننده است).
- rules: merge_request_event یا default branch.

### C.3 نمونه کلاینت — [`deploy/pcm19_rest_client_sample.py`](deploy/pcm19_rest_client_sample.py)

- **فقط stdlib** (urllib/json/argparse) — مصرف‌کنندهٔ خارجی نیازی به pip ندارد.
- احراز هویت PCM-09: `POST /api/auth/login` → کوکیز `pct_session` از Set-Cookie گرفته و replay می‌شود.
- رمز: `--password` / `--password-file` / `PCT_PASSWORD` / getpass — **هرگز در کد/Git/لاگ** (AGENTS §2.5).
- envelope: روی `ok:false` یا non-2xx استثنای `PctError(code, body)` — قرارداد خطاها قابل‌تست است.
- **فقط خواندنی** (فقط GET): collections → works + جزئیات اولین work (editions) → batches اولین collection + `queue.counters` + `queue/summary` → نشان از قرارداد 404 (`w-ffffffff` باید 404 بدهد).
- `_force_utf8_stdio()`: reconfigure خروجی به UTF-8 — چون چاپ فارسی روی کنسول Windows (cp1252) `UnicodeEncodeError` می‌دهد (نقص واقعی که در e2e اول پیدا شد و اصلاح شد).
- خروجی صادقانه: بچِ ساخته‌نشده/پردازش‌نشده‌ای که صف نداشته باشد counters همه‌صفر گزارش می‌کند — همان رفتار درست `queue_counters()` که مستقیم از `knowledge_file_queue` حساب می‌کند (آمار ساختگی نمی‌دهد، AGENTS §2.9).

### C.4 چک‌کن OpenAPI — [`deploy/pcm19_openapi_check.py`](deploy/pcm19_openapi_check.py)

آینهٔ سبک CT-01 برای CI/اپراتور: glob `docs/openapi/*.yaml` → parse + openapi 3.x + info/schemas + هر operationId یکتا + حل همهٔ `$ref` + تطبیق path-params با template + ≥1 operation. exit 0/1. بدون وابستگی به app/DB.

### C.5 به‌روزرسانی اسناد

- `readme.md`: سطر 8e جدول امکانات (PCM-19)؛ جعبهٔ معماری «11 test files — 200 تست»؛ درخت پروژه + `test_api_contract.py` (و اصلاح عدد test_word_factory به 27)؛ بخش تست + دستور `test_api_contract` و «200/200 (کل)»؛ backlog: «CI (unittest) فعال شد — PCM-19»؛ roadmap: سطرهای PCM-18 و PCM-19.
- `AGENTS.md`: دستور رگرسیون + `test_api_contract` و «200 تست (رگرسیون کامل)»؛ شمارش ماژول‌ها + «(18، CT-01..CT-06 — قرارداد OpenAPI spec ↔ app زنده، PCM-19)»؛ ساختار فنی + `docs/openapi/` و `.gitlab-ci.yml`؛ roadmap: سطرهای PCM-18 و PCM-19.
- `docs/openapi/README.md` (جدید): راهنمای اپراتور — فهرست specها و 19 operation، قواعد مشترک (envelope/صفحه‌بندی/خطاها/شناسه‌های قطعی)، دستور چک‌کن، ماتریس CT، راهنمای کلاینت، چرایی بدون-deploy بودن CI و ممنوعیت `PCT_DASHBOARD_PASSWORD` در CI، قواعد نگه‌داری.

## D. فایل‌های این مرحله

| فایل | نوع | توضیح |
|------|-----|-------|
| [`backend/test_api_contract.py`](backend/test_api_contract.py) | جدید | 18 تست CT-01..CT-06 — قرارداد OpenAPI↔app زنده |
| [`.gitlab-ci.yml`](.gitlab-ci.yml) | جدید | CI فقط-تست (3 job؛ بدون deploy) |
| [`deploy/pcm19_openapi_check.py`](deploy/pcm19_openapi_check.py) | جدید | چک‌کن specها برای CI/اپراتور (exit 0/1) |
| [`deploy/pcm19_rest_client_sample.py`](deploy/pcm19_rest_client_sample.py) | جدید | نمونه کلاینت REST، فقط stdlib، فقط خواندنی |
| [`docs/openapi/README.md`](docs/openapi/README.md) | جدید | راهنمای اپراتور OpenAPI/CI/کلاینت |
| [`docs/openapi/pcm14d-knowledge-work-registry.openapi.yaml`](docs/openapi/pcm14d-knowledge-work-registry.openapi.yaml) | اصلاح | 3 نقص quote (سطر 3 + 710 + 730-732) |
| [`readme.md`](readme.md) | اصلاح | 8e/معماری/درخت/تست/backlog/roadmap |
| [`AGENTS.md`](AGENTS.md) | اصلاح | رگرسیون 200 + ماژول جدید + ساختار + roadmap |

هیچ endpoint/رفتار production تغییر نکرده (فقط اسناد/تست/CI/اسکریپت).

## E. تست‌ها (اجرا شده — با مدرک)

### E.1 Python 3.13 (محیط کامل: flask 3.1.3 + flask-cors 6.0.1 + docx + pyyaml 6.0.3)

```
cd backend && python -m unittest test_api test_projects test_dashboard \
  test_knowledge_api test_word_factory test_dump test_work_registry test_queue \
  test_corpus_builder test_studio_api test_api_contract -v
Ran 200 tests in 81.241s
OK
```

### E.2 Python 3.14 (interpreter پیش‌فرض 32-bit — بدون PyYAML)

```
Ran 200 tests in 77.362s
OK (skipped=10)
```

هر 10 skip همان 10 تست yaml-gate هستند (CT-01×4 + CT-02 + 5 مورد دیگر وابسته به spec) — پیام skip: «PyYAML not installed». **هیچ assertion حذف یا تضعیف نشده**؛ در CI (python:3.12 + pyyaml) همه 200 تست اجرا می‌شوند.

### E.3 e2e نمونه کلاینت

سرور throwaway (DB موقت، پورت 5055) + seed یک‌باره (collection + batch + work + edition):

```
logged in (session cookie stored, HttpOnly, 7 days)
=== collections (total=1) ===
  c-1277c57f  ...  [contract-e2e]
=== works (total=1) ===  →  work detail w-...: 1 edition(s)
=== batches of c-... (total=1) ===  status=planned paused=0
queue counters: {"total":0,...}   ← بچ پردازش‌نشده = صف خالی = counters صفر (درست)
queue summary : {...}
error contract: unknown work -> HTTP 404 (expected 404)
DONE — read-only; nothing was written.   (exit 0)
```

نقص واقعی پیدا شده و اصلاح شد: `UnicodeEncodeError: 'charmap'` روی چاپ فارسی → `_force_utf8_stdio()`. بعد از e2e: سرور kill، DB/داده‌های موقت و اسکریپت seed throwaway **حذف** شدند (در بخش E.5 تأیید).

### E.4 CI

- YAML parse: سبز (parser پایدار).
- `python deploy/pcm19_openapi_check.py` → «OpenAPI check passed: 2 specs, 19 operations» (exit 0).
- `python -m py_compile deploy/pcm19_openapi_check.py deploy/pcm19_rest_client_sample.py` → exit 0.
- `python deploy/pcm19_rest_client_sample.py --help` → exit 0.
- محدودیت صادقانه: CI **فعلاً فقط روی mirror GitLab CE (s52:2222) فعال می‌شود** — remote اصلی GitHub است و GitLab CI در GitHub اجرا نمی‌شود؛ تا mirror همگام نشود، jobها در GitLab اجرا نخواهند شد (بدون ادعای اجرای CI).

### E.5 gates

- `git diff --check` → تمیز (فقط هشدارهای CRLF↔LF سبک موجود repo).
- secret scan روی 8 فایل جدید/تغییرکرده: patterns `ghp_/gho_/sk-/hf_/Bearer/private.key` و `password=` → **0 hit واقعی** (هیت‌ها فقط نام گزینهٔ `--password-file` در کلاینت/README و fixture تست `test-secret-123` که از PCM-12.3 در کل suite موجود است و رمز production نیست).
- `git status --porcelain` بعد از commit: clean. فایل throwaway seed (`pcm19_seed_tmp.py`) حذف شده.
- working tree قبل از commit = دقیقاً 8 ورودی PCM-19 (3 modified + 5 untracked) — مطابق `8 files changed` در commit.

## F. وضعیت s52 (محدودیت — صادقانه)

- s52 در زمان این مرحله (2026-11-02) **همچنان ردیاب نیست** — ادامهٔ وضعیت PCM-17/18 (تاکنون 5× timeout ثبت‌شده). در PCM-19 دوباره attempt نشده چون هدف PCM-19 ذاتا‌ً offline (تست/CI/اسناد) است و هیچ ادعایی از s52 نشده است.
- بنابراین **هیچ** بخشی از `pcm17_s52_readonly_check.sh` / `pcm18_s52_observability_audit.sh` اجرا نشده و در این گزارش عدد/وضعیتی از s52 ادعا **نمی‌شود**.
- آخرین وضعیت s52 **با مدرک** = چک PCM-16 (2026-10-29): production healthy، pre-PCM-14D، DB integrity ok.
- **برنامهٔ اقدام به‌محض دسترسی:** (1) `pcm17_s52_readonly_check.sh` (2) `pcm18_s52_observability_audit.sh` (3) ثبت خروجی هر دو در گزارش پیوسته.

## G. Git: commit و push

- **commit کد + اسناد:** `0340caa` = `0340caaba3028efeb301ac8146e02cc7428186df` — 8 files changed, 1090 insertions(+), 14 deletions(-)؛ push بدون force.
- **GitHub:** `git ls-remote origin main` → `0340caaba3028efeb301ac8146e02cc7428186df refs/heads/main` — **مطابق Local HEAD** (تأیید شده).
- این گزارش در **commit دوم بلافاصله بعدی** ثبت می‌شود (رویهٔ PCM-14C.3/14D/15/16/17/18).
- پیام commit: «PCM-19: contract tests CT-01..CT-06 (OpenAPI spec vs live app) + GitLab CI (test-only) + REST client sample + OpenAPI checker + docs refresh; 200/200 regression; no deploy».

## H. وضعیت Local / GitHub / s52

| محیط | وضعیت |
|------|-------|
| Local | `main` = `0340caa` (+ commit گزارش در ادامه)؛ working tree clean |
| GitHub | `main` = `0340caa` — با `git ls-remote` تأیید شده (بخش G) |
| s52 | **ردیاب** (از 2026-11-02، 5× timeout). آخرین وضعیت مدرک‌شده = چک PCM-16. اسکرپت‌های PCM-17/18 آماده؛ اجرا — به‌محض دسترسی |

## I. production

- هیچ deploy/restart/تغییری روی s52 انجام **نشد**.
- PCM-19 ذاتا‌ً بدون تغییر رفتار است: فقط تست/CI/اسکریپت/اسناد — endpoint جدیدی ساخته نشد (CT-02 برعکس تضمین می‌کند specها فراتر از app نرفته‌اند).
- deploy آینده (با تأیید مالک) بچ PCM-14C.3+14D+15+16+17(+19) را یکجا حمل می‌کند — همه additive/بدون مهاجرت (مستند در گزارش‌های مرحله‌ای).

## J. ریسک‌ها و محدودیت‌ها

| # | ریسک/محدودیت | اثر | وضعیت |
|---|--------------|-----|-------|
| 1 | s52 ردیاب | چک‌های PCM-17/18 + deploy بچ آماده‌شده‌ها انجام نشده | اسکرپت‌ها آماده؛ به‌محض دسترسی |
| 2 | CI تا mirror همگام نشود، اجرا نمی‌شود | pipeline فعلاً بدون اجراست | صادقانه ثبت شد (E.4)؛ هر سه job محلی verify شده |
| 3 | 10 تست yaml-gate در Py3.14 skip می‌شوند | در interpreter بدون PyYAML، CT-01/02 اجرا نمی‌شوند | skip صادقانه + CI با pyyaml همه 200 را اجرا می‌کند |
| 4 | `docs/openapi/` هنوز namespace کامل `/api/knowledge/*` را پوشش نمی‌دهد (فقط 19 operation از PCM-14D/15/17) | specهای collections/documents/subjects ناقص‌اند | قاعدهٔ نگه‌داری در `docs/openapi/README.md` ثبت شد — با endpoint جدید، CT-02/CT-03 فشار می‌آورند |
| 5 | ES index «NOT VERIFIED» (از PCM-14C) | — | بدون تغییر؛ با دسترسی s52 بررسی |

## K. راهنمای اپراتور

```bash
# 1) رگرسیون کامل (Python 3.10+ با flask + pyyaml؛ image production = 3.12):
cd backend && python -m unittest test_api test_projects test_dashboard \
  test_knowledge_api test_word_factory test_dump test_work_registry test_queue \
  test_corpus_builder test_studio_api test_api_contract -v     # 200/200

# 2) چک OpenAPI فقط (بدون app/DB):
python deploy/pcm19_openapi_check.py        # «2 specs, 19 operations — OK»

# 3) نمونه کلاینت (فقط خواندنی؛ رمز هرگز در کد/لاگ):
PCT_PASSWORD=... python deploy/pcm19_rest_client_sample.py --base https://corpus.ai.ismc.ir
# یا محلی: --base http://127.0.0.1:5055 --password-file .\pct-pw.txt

# 4) CI: mirror repo در GitLab CE (s52:2222) → هر MR/commit روی main سه job test اجرا می‌کند.
```

جزئیات کامل: [`docs/openapi/README.md`](docs/openapi/README.md).

## L. موارد باقی‌مانده / گام بعدی

1. **به‌محض دسترسی s52:** اجرای `deploy/pcm17_s52_readonly_check.sh` + `deploy/pcm18_s52_observability_audit.sh` + ثبت خروجی‌ها (بخش F).
2. **mirror GitLab:** همگام‌سازی repo در GitLab CE تا CI واقعاً اجرا شود (jobهای deploy عمداً وجود ندارند).
3. **roadmap باز:** PCM-06 (نمای آمار) · PCM-07 (ناوبری/کنترل) · PCM-08 (transform) · PCM-10 (metrics + 4 داشبورد Grafana) — ترتیب در `AGENTS.md` §6.
4. **deploy بچ** (فقط با تأیید مالک، مطابق `deploy/pcm04_deploy.sh`): PCM-14C.3 + 14D + 15 + 16 + 17 (+ اسناد/تست PCM-19) — همه additive، بدون مهاجرت schema.

# مشخصه‌های OpenAPI — Knowledge Studio (PCM-19)

این پوشه مشخصه‌های رسمی OpenAPI 3.0 برای namespace خواندنی/نویسندنی
`/api/knowledge/*` است. مشخصه‌ها **بخشی از قرارداد API** هستند:
تست‌های `backend/test_api_contract.py` (CT-01..CT-06) و چک‌کن
`deploy/pcm19_openapi_check.py` صحت آن‌ها را به‌طور خودکار می‌سنجند و
`.gitlab-ci.yml` در هر merge request/commit روی main اجرا می‌شود.

> قاعده: مشخصه **واقعی** می‌ماند — هر operation باید موجودی در app زنده
> باشد (CT-02)، و هر 401/400/404/shape باید با رفتار واقعی app مطابقت
> کند (CT-03/CT-04/CT-05). تغییر endpoint در کد بدون به‌روزرسانی
> مشخصه (یا بالعکس) رگرسیون را می‌شکند.

## فهرست مشخصه‌ها

| فایل | عنوان | Operationها |
|---|---|---|
| [pcm14d-knowledge-work-registry.openapi.yaml](pcm14d-knowledge-work-registry.openapi.yaml) | Work/Edition/Volume Registry (PCM-14D) | 14 — works/editions/volumes CRUD + متادیتا (fields/values) + `metadata/resolve` |
| [pcm15-file-queue.openapi.yaml](pcm15-file-queue.openapi.yaml) | Per-file Processing Queue (PCM-15) | 5 — pause/resume بچ + `queue/summary` + list/detail بچ‌ها (سطح PCM-17) |

مجموع: **19 operation** (9 GET). همه endpointها با احراز هویت session
PCM-09 (`cookieAuth` = cookie `pct_session`) محافظت می‌شوند.

نکات قرارداد مشترک (در هر دو spec):

- پاسخ‌ها: `{"ok": true, ...}` / `{"ok": false, "message": ..., "field"?: ...}`.
- صفحه‌بندی: `page` (≥1) + `per_page` (1..100، cap سمت سرور) + خروجی
  `total` / `page` / `per_page` / `total_pages`.
- خطاها: `401` بدون session · `400` + `field` برای ورودی نامعتبر ·
  `404` برای شناسه نامشخص.
- شناسه‌ها قطعی‌اند: `w-/e-/v-<sha8>` (spec 14D) و `b-/f-<sha8>` (spec 15).

## اعتبارسنجی (دستور محلی)

```bash
# نیازمند PyYAML (pip install pyyaml) — image production/CI هم همین را دارد
python deploy/pcm19_openapi_check.py
# خروجی موفق: «2 specs, 19 operations — OK»
```

چه چیزی را می‌سنجد (آینه‌ی CT-01):
1. parse شدن YAML + `openapi: 3.x` + `info.title`/`info.version`/`paths`/`components.schemas` غیرخالی؛
2. هر operation دارای `operationId` یکتا و با الگوی `[A-Za-z][A-Za-z0-9]*`؛
3. هر `$ref` محلی (`#/...`) در spec حل شود (با unescape `~0`/`~1` از JSON Pointer)؛
4. پارامترهای `in: path` اعلان‌شده دقیقاً برابر `{param}`های template مسیر باشند.

برای اعتبارسنجی کامل‌تر (شامل تطبیق با app زنده) از رگرسیون استفاده کنید:

```bash
cd backend && python -m unittest test_api_contract -v    # 18/18
```

ماتریس CT (در `backend/test_api_contract.py`):

| تست | محتوا |
|---|---|
| CT-01 | صحت ساختار spec (parse + operationId + `$ref` + path params) |
| CT-02 | پوشش: هر (path, method) spec در url_map app موجود است + ≥19 operation |
| CT-03 | قرارداد auth: هر 19 operation بدون session → **401** (با method دقیق — 405 در routing زودتر از decorator می‌آید) |
| CT-04 | تطبیق shape زنده با schemaهای spec (ImportBatch/QueueCounters/Work/Edition/Volume) |
| CT-05 | قرارداد خطاها: 400+field / 404 / cap `per_page` روی 100 / فیلدهای صفحه‌بندی |
| CT-06 | یکتایی operationId + عدم تکرار (path, method) بین دو spec |

## نمونه کلاینت REST برای مصرف‌کننده‌های خارجی

`deploy/pcm19_rest_client_sample.py` — کلاینت **فقط-stdlib** (بدون pip)
که قرارداد HTTP را دقیق نشان می‌دهد: ورود با `POST /api/auth/login` +
replay کوکیز `pct_session`، envelope `ok:false`، صفحه‌بندی، و قرارداد
خطا (404 برای شناسه نامشخص). فقط خواندنی است (فقط GET) و هیچ چیزی
نمی‌نویسد.

```bash
# رمز هرگز در کد/Git/لاگ (AGENTS §2.5) — از environment یا فایل:
PCT_PASSWORD=... python deploy/pcm19_rest_client_sample.py --base https://corpus.ai.ismc.ir
python deploy/pcm19_rest_client_sample.py --base http://127.0.0.1:5055 --password-file .\pct-pw.txt
# گزینه‌ها: --collection <id> · --search <term> · --insecure (فقط تست محلی)
```

خروجی: collections (صفحه اول) → فهرست works + جزئیات اولین work
(editions) → batches اولین collection + `queue.counters` + `queue/summary`
→ نشان از قرارداد خطا (work نامشخص باید 404 بدهد) → exit 0.

## CI (GitLab CE روی s52:2222)

`.gitlab-ci.yml` در ریشه repo — **فقط تست، بدون هیچ job deploy**
(قاعده AGENTS: استقرار فقط دستی، طبق `deploy/pcm04_deploy.sh`):

| Job | محتوا |
|---|---|
| `regression` | رگرسیون کامل `cd backend && python -m unittest <10 ماژول> test_api_contract -v` (200 تست) |
| `openapi` | `python deploy/pcm19_openapi_check.py` |
| `client` | `py_compile` دو اسکریپت pcm19 + `--help` کلاینت |

- image: `python:3.12-slim` (همان image production) + `pip install -r backend/requirements.txt` + `pyyaml`.
- `PCT_DB` به فایل موقت job-point می‌زند؛ `PCT_DASHBOARD_PASSWORD` **عمداً تعریف نمی‌شود**
  چون `pct_test_support` آن را با `setdefault` روی `test-secret-123` می‌گذارد و
  همه ماژول‌های تست همین رمز را hardcode کرده‌اند (تعریف خارجی همه‌ی تست‌های login را 401 می‌کند).
- GitLab CE فقط mirror است؛ remote اصلی GitHub (`origin`) است.

## نگه‌داری

- endpoint جدید در `/api/knowledge/*` → operation جدید در spec مربوط +
  coverage خودکار CT-02/CT-03 آن را می‌فشارند.
- تغییر shape پاسخ → schema spec + CT-04 به‌روز شود.
- نسخه spec با `info.version` افزایش یابد (حالا هر دو `1.0.0`).

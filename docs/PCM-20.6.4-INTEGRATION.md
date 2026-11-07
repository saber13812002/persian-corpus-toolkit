# راهنمای یکپارچه‌سازی — Tasnim Web V1 (PCM-20.6.4)

> سند رسمی برای **استفاده‌کنندگان خارجی** از API خواندنی پیکرهٔ «تفسیر تسنیم».
> همه‌ی نمونه‌های این سند روی سرور واقعی V1 (پیکرهٔ `v0003`، ۴۵٬۸۴۴ صفحه) یا
> روی فلکسچر آزمون (`test_tasnim_sdk.py`، ۵۱/۵۱ سبز) اعتبارسنجی شده‌اند.

---

## ۱. خلاصه

- **API خواندنی فقط (read-only)** — هیچ endpoint نوشتاری وجود ندارد.
- **بدون احراز هویت در V1** — نه توکن، نه کلید API. تنها محدودکننده، rate limit
  به‌ازای هر IP است (بخش ۵).
- **JSON + UTF-8** — همه‌ی پاسخ‌ها `Content-Type: application/json` با `ensure_ascii=False`
  (متن فارسی خوانا، نه `\u0627`).
- **۱۲ endpoint** + دو مرجع developer (`/openapi.json` و `/docs`).
- **SDK رسمی** برای Python و JavaScript/TypeScript (بخش ۸).
- **پیکرهٔ واقعی:** ۴۵٬۸۴۴ صفحه / ۶ جلد / ۱٬۰۸۰ موضوع؛ بازه‌های گم‌شدهٔ
  `item_index` صریح گزارش می‌شوند (بخش ۷، gap-awareness).

## ۲. Base URL و نسخه‌بندی

| مورد | مقدار |
|---|---|
| سرور عمومی V1 | `https://tasnim.ai.ismc.ir` |
| پیشوند API | `/api/v1/tasnim` |
| نمونهٔ کامل | `https://tasnim.ai.ismc.ir/api/v1/tasnim/catalog` |
| اینستانس محلی (dev) | `http://127.0.0.1:5071` (پورت داخلی dev؛ ۵۰۷۰ = public) |

- نسخه‌بندی در **مسیر** است (`/api/v1/`). در V1 فقط تغییرات **افزایشی** می‌شود
  (فیلد/endpoint جدید). تغییر شکست‌دهنده → `/api/v2`؛ V1 تا اعلام رسمی باقی می‌ماند.
- `CANONICAL_BASE` (بدون پیشوند API: `https://tasnim.ai.ismc.ir`) در payloadها
  برای URLهای ارجاعی/استناد (`reference.canonical_url`) استفاده می‌شود.
- Swagger UI آفلاین: `GET /api/v1/tasnim/docs` (و machine-readable
  `GET /api/v1/tasnim/openapi.json`) — هر دو از rate-limit **معاف**.

## ۳. شکل پاسخ (envelope)

هر پاسخ موفق:

```json
{
  "data": { "...": "payload endpoint" },
  "meta": {
    "request_id": "req_9f3a2b1c4d5e6f70",
    "readmodel": { "version": "v0003", "content_sha256": "…" },
    "generated_at": "2026-11-07T12:00:00Z",
    "next_page_token": "…"
  }
}
```

- `meta.request_id` (شکل `req_` + ۱۶ hex) را در هر گزارش خطا بفرستید.
- `meta.next_page_token` فقط وقتی صفحهٔ بعدی وجود دارد (بخش ۶).
- پاسخ‌های خطا **RFC-7807** هستند (بخس ۵).

## ۴. فهرست endpointها (۱۲)

| Method | Path | کاربرد | کلاس rate | ETag |
|---|---|---|---|---|
| GET | `/catalog` | هویت work/edition + شمارنده‌ها + coverage | read | strong |
| GET | `/volumes` | فهرست جلد‌ها (sort: `volume_no`, `page_count`) | read | strong |
| GET | `/volumes/{volume_id}` | جزئیات جلد: coverage، ranges گم‌شده، ambiguity، top headings | read | strong |
| GET | `/surahs` | **503 صادقانه** — index سوره در V1 پشتیبانی نمی‌شود | read | — |
| GET | `/surahs/{surah_id}` | **503 صادقانه** (همان `details` + `surah_id`) | read | — |
| GET | `/topics` | فهرست موضوعات (sort: `page_count`, `name`؛ فیلتر `q`, `min_pages`) | read | strong |
| GET | `/topics/{topic_id}` | جزئیات موضوع: occurrences، parent، sample pages | read | strong |
| GET | `/pages/{item_index}` | **صفحه** (قلب قرارداد؛ `?dup_rank=N`) | read | strong |
| GET | `/pages/{item_index}/neighbors` | prev/next با آگاهی از gap + `missing_nearby` | read | strong |
| GET | `/search` | جستجوی پرتای (stem فارسی؛ AND بین توکن‌ها) | **search** | no-store |
| GET | `/statistics` | آمار زندهٔ DB با تعاریف مکتوب | read | strong |
| GET | `/health` | health + هویت readmodel + uptime — **معاف از rate limit** | exempt | — |

پارامترهای عمومی فهرست‌ها: `limit` (پیش‌فرض ۵۰؛ جستجو ۲۰؛ سقف ۲۰۰)، `offset` **یا**
`page_token`، `sort` (فقط مقدارهای whitelisted؛ غیرمجاز → `INVALID_SORT`).

## ۵. Rate limit و خطاها

### ۵.۱ محدودیت درخواست

| کلاس | سقف | شامل |
|---|---|---|
| `search` | **۳۰/دقیقه/IP** | `/search` |
| `read` | **۱۲۰/دقیقه/IP** | بقیهٔ endpointهای جدول بالا |
| exempt | بدون محدودیت | `/health`, `/openapi.json`, `/docs` |

- پنجرهٔ شمارش **دقیقهٔ تقویمی** است (نه ۶۰ ثانیهٔ متحرک).
- IP = اولین مقدار `X-Forwarded-For` اگر باشد، وگرنه `remote_addr`
  (پشت proxy/nginx صحیح کار می‌کند).
- در ۴۲۹ هدر `Retry-After` (ثانیه تا پایان پنجره، حداقل ۱) ارسال می‌شود.

### ۵.۲ جدول خطاها (RFC-7807)

```json
{
  "type": "https://tasnim.ai.ismc.ir/errors/page-not-found",
  "title": "صفحهٔ موردنظر در پیکره نیست",
  "status": 404,
  "code": "PAGE_NOT_FOUND",
  "message": "…",
  "details": { "item_index": 5, "in_missing_range": [4, 9],
               "suggestion": "نزدیک‌ترین صفحات موجود: 3، 10" },
  "request_id": "req_…"
}
```

| code | HTTP | `details` (کلیدهای مهم) |
|---|---|---|
| `VOLUME_NOT_FOUND` | 404 | `volume_id` |
| `TOPIC_NOT_FOUND` | 404 | `topic_id` |
| `PAGE_NOT_FOUND` | 404 | `item_index`, `in_missing_range` (یا null), `suggestion` |
| `SURAH_INDEX_NOT_SUPPORTED` | 503 | `status: "not_supported"`, `coverage: "0/114"`, `reason`, `next_planned`, `evidence[4]`, (+`surah_id` برای endpoint دوم) |
| `RATE_LIMITED` | 429 | `limit`, `window: "60s"`, `endpoint_class` + هدر `Retry-After` |
| `INVALID_QUERY` | 400 | `q` باید ۲..۶۴ کاراکتر و قابل-کلمه‌بندی باشد |
| `INVALID_PARAMETER` | 400 | نام/مقدار پارامتر نامعتبر |
| `INVALID_SORT` | 400 | مقدار `sort` خارج از whitelist |
| `INVALID_PAGE_TOKEN` | 400 | `page_token` قابل-رمزگشایی نیست |

`type` همیشه `https://tasnim.ai.ismc.ir/errors/<slug از code>` است (یعنی از
**code** می‌آید، نه از id منبع).

## ۶. صفحه‌بندی (pagination)

- `limit` + `offset` **یا** `page_token` (opaque؛ base64 — تفسیر نکنید، فقط بفرستید).
- تا وقتی ردیف بعدی هست، `meta.next_page_token` در پاسخ می‌آید؛ در آخرین صفحه
  غیاب دارد.
- ترتیب‌بندی‌ها پایدارند؛ برای پیمایش کامل generatorهای SDK (`iter_volumes`,
  `iter_topics`, `iter_pages`) را ترجیح بدهید — زنجیرهٔ token را خودکار می‌پیوندند.
- `iter_pages(min, max)` روی بازه‌های گم‌شده یا **skip** می‌کند
  (`on_missing="skip"`، پیش‌فرض) یا با `PAGE_NOT_FOUND` می‌اندازد (`"raise"`).
- نکتهٔ عملی: `iter_topics()` روی کل corpus یعنی ~۲۲ درخواست (۱٬۰۸۰ موضوع ÷ ۵۰).
  برای «چند موضوع اول» فقط `list_topics(limit=5)` بزنید.

## ۷. قرارداد صفحه (heart of the contract)

`item_index` شمارهٔ **سطح corpus** است (شمارهٔ فیزیکی کتاب نیست) و ممکن است
**گپ** داشته باشد. مثال واقعی: بازهٔ `3649..11182` غایب است و
`GET /pages/3650` با ۴۰۴ + `in_missing_range: [3649, 11182]` + پیشنهاد
نزدیک‌ترین صفحات موجود پاسخ می‌دهد.

فیلدهای کلیدی payload صفحه:

- `item_index`, `dup_rank` (اگر همان `item_index` در چند رکورد باشد؛ پیش‌فرض ۰).
- `volume` → `volume_id`, `volume_no`, `title`, `attribution`, `ambiguity`
  (اگر `item_index` در دو جلد آمده باشد: `ambiguity: true`,
  `attribution: "ambiguous"`).
- `heading` → `text` (سرفصل بخش جاری) یا null.
- `visible_content` → `text`, `char_count`, `record_class`
  (`CONTENT_PAGE` | `SHORT_CONTENT` | `EMPTY_PAGE`).
- `quality` → `status` (`ok` | `short` | `empty` | `truncated_at_2000` |
  `dup_item_index`), `flags` (لیست: `short`, `empty`, `truncated_at_2000`,
  و `dup_item_index` فقط وقتی dup **بین-جلد** است), `truncated_at_source`,
  `source_char_cap`.
- `next_page_reference` / `previous_page_reference` — **gap-aware**:
  `{item_index, page_id, exists, gap_before}` + در صورت گپ
  `in_missing_range: [lo, hi]`، `next/prev_available_item_index` و رفرنس
  تودرتوی `gap`. در ابتدا/پایان corpus → `null`.
- `metadata` → `page_id`, `content_sha256`, `captured_at`, `source_page_id`,
  `source_url` (provenance).
- `reference` → `work_id`, `edition_id`, `volume_id`, `item_index`, `barg`,
  `page_id`, `content_sha256`, `source_url`, **`canonical_url`** —
  شکل `https://tasnim.ai.ismc.ir/page/{item_index}[?dup_rank=N]`.
- `duplicates` → اگر رکورد هم-`item_index` دیگری داشته باشد:
  `[{dup_rank, page_id, volume_id}, …]`.

### الگوی استناد RAG (citation pattern)

برای هر سند RAG که از این پیکره می‌سازید:

1. متن را از `visible_content.text` بگیرید (نه از snippet جستجو).
2. ارجاع = `reference.canonical_url` (+ `barg` و `volume.title` برای خوانا بودن).
3. برای تازگی/یکپارچگی، `page_id` + `reference.content_sha256` را هم ذخیره کنید؛
   `meta.readmodel.version` (مثلاً `v0003`) نسل پیکره را مشخص می‌کند.
4. برای پیمایش یک بخش، `iter_pages` را با `on_missing="skip"` بزنید — گپ‌ها
   خودکار رد می‌شوند و خروجی فقط صفحات **موجود** است.
5. اگر `quality.status != "ok"`، در ارجاع بگویید (مثلاً `truncated_at_2000`
   یعنی متن در منبع در ۲۰۰۰ نویسه بریده شده) — هرگز متن ناقص را کامل فرض نکنید.

## ۸. SDKهای رسمی

### ۸.۱ Python — `tasnim/sdk/python/tasnim_client/`

- فقط کتابخانهٔ استاندارد (`urllib`)؛ Python 3.9+. بدون publish — از
  `PYTHONPATH` استفاده کنید:

  ```bash
  set PYTHONPATH=tasnim\sdk\python;%PYTHONPATH%   # Windows
  export PYTHONPATH=tasnim/sdk/python:$PYTHONPATH # bash
  ```

- نمونه:

  ```python
  from tasnim_client import TasnimClient, TasnimAPIError, Page

  c = TasnimClient("https://tasnim.ai.ismc.ir")          # dev: http://127.0.0.1:5071

  p = c.get_page(2)                                        # -> Page (dict + properties)
  print(p.item_index, p.barg, p.text[:100], p.quality_status)
  print(p.next_item_index, p.canonical_url)

  for page in c.iter_pages(0, 100, on_missing="skip"):     # gap-aware
      print(page.item_index, page.barg)

  s = c.search("قرآن", limit=10)
  print(s.data["total"], [h["item_index"] for h in s.data["results"]])

  try:
      c.get_page(3650)
  except TasnimAPIError as e:
      print(e.code, e.details["in_missing_range"])         # PAGE_NOT_FOUND [3649, 11182]
  ```

- رفتارهای کلاینت: 429 → sleep روی `Retry-After` + retry (تا `max_retries=3`،
  سقف هر خواب `max_backoff_s=65` ثانیه) — با `rate_limit_backoff=False` حذف
  می‌شود؛ کش ETag in-memory (`etag_cache=True`، 304 → `from_cache=True`،
  `clear_etag_cache()` برای reset)؛ خطای transport → `TasnimClientError`
  (تفکیک از `TasnimAPIError` که یعنی envelope رسمی دریافت شده).
- CLI دمو: `python -m tasnim_client --base http://127.0.0.1:5071 --page 2`
  (و `--search "تفسیر"` / `--topic t-…`).
- آزمون: `test_tasnim_sdk.py` (ریشهٔ repo) — ۵۱ تست end-to-end روی HTTP واقعی.

### ۸.۲ JavaScript/TypeScript — `tasnim/sdk/javascript/`

- ES Module، zero-dep، `fetch` — Node 18+ و مرورگر. `tasnim.sdk.d.ts`
  تایپ‌های کامل دارد.

  ```js
  import TasnimClient, { TasnimAPIError } from "./tasnim-client.mjs";

  const c = new TasnimClient({ baseUrl: "https://tasnim.ai.ismc.ir" });

  const p = await c.getPage(2);          // camelCase + snake_case هر دو موجود
  console.log(p.itemIndex, p.qualityStatus, p.text.slice(0, 100));

  for await (const pg of c.iterPages(1, 20, { onMissing: "skip" })) {
      console.log(pg.itemIndex, pg.barg);
  }

  const s = await c.search("قرآن", { limit: 5 });
  console.log(s.data.total);              // 3+ توکن: total === -1 && estimated
  try {
      await c.getPage(3650);
  } catch (e) {
      if (e instanceof TasnimAPIError) console.log(e.code, e.details.in_missing_range);
  }
  ```

- همان قرارداد 1:1 با پایتون: backoff 429 (`sleep` injectable برای تست)،
  کش ETag (`fromCache` روی پاسخ‌های خام)، pagination با `pageToken`.

## ۹. سیاست کش و ETag

- Endpointهای «پایدار» (catalog، volumes list/detail، topics list/detail،
  page، neighbors، statistics) **ETag قوی** دارند:
  `"sha256(DBSHA|key)[:32]"` — چون به sha256 خود دیتابیس گره خورده، با هر
  **build جدید** پیکره، همهٔ ETag‌ها عوض می‌شوند (invalidation خودکار).
- 304 Not Modified: **بدون بدنه**؛ فقط ETag + `Cache-Control` می‌آیند.
  کلاینت‌های SDK خودکار `If-None-Match` می‌فرستند.
- `/search` با `Cache-Control: no-store` پاسخ می‌دهد (ETag ضعیف صرفاً
  referential است) — SDKها آن را conditional نمی‌کنند.
- `Cache-Control` روی پایدارها `public, max-age=60` است؛ برای cache مشترک
  (CDN) هم بی‌ضرر است چون ETag قوی است.
- `generated_at` + `meta.readmodel.version` را برای تصمیم «داده هنوز تازه‌ست؟»
  استفاده کنید.

## ۱۰. cheatsheet curl

```bash
B="https://tasnim.ai.ismc.ir/api/v1/tasnim"

# سلامت (rate-exempt)
curl -s "$B/health" | python -m json.tool

# هویت + شمارنده‌ها
curl -s "$B/catalog" | python -m json.tool

# یک صفحه (قلب قرارداد)
curl -s "$B/pages/2" | python -m json.tool
curl -s "$B/pages/2?dup_rank=1"          # رکورد دوم همان item_index

# gap-aware: 3650 غایب است
curl -si "$B/pages/3650" | head -20      # 404 + in_missing_range + suggestion

# جستجو
curl -s "$B/search?q=%D9%82%D8%B1%D8%A2%D9%86&limit=5" | python -m json.tool

# فهرست + صفحه‌بندی با token
curl -s "$B/volumes?limit=2" | python -m json.tool
#   -> meta.next_page_token
curl -s "$B/volumes?limit=2&page_token=<token>" | python -m json.tool

# ETag / 304
ET=$(curl -sI "$B/catalog" | tr -d "\r" | awk -F': ' '/^ETag:/{print $2}')
curl -si -H "If-None-Match: $ET" "$B/catalog" | head -5   # 304 Not Modified

# آمار زنده
curl -s "$B/statistics" | python -m json.tool

# سوره — 503 صادقانه
curl -si "$B/surahs" | head -20
```

## ۱۱. محدودیت‌های V1 (صادقانه)

- **Index سوره نیست:** `/surahs*` عمداً 503 است؛ دلیل، coverage `0/114` و
  شواهد را در `details` می‌دهد. (مأموریت بعدی.)
- **embedding/Neo4j نیست:** API فقط خوانش ساختاری/متنی است؛ برداری‌سازی و
  گراف دانش مأموریت بعدی‌اند.
- **بدون auth:** برای V1 عمومی پذیرفته شده (محتوای عمومی + rate limit).
- **تغییر پیکره build-to-build:** `meta.readmodel.version` عوض می‌شود؛ ETag‌ها
  باطل می‌شوند؛ `content_sha256` صفحات ثابت می‌ماند (محتوای صفحه تغییر نکرده،
  نسل build عوض شده است).

## ۱۲. پشتیبانی و پیگیری

- در گزارش هر مشکل: `request_id` پاسخ، `item_index`/endpoint، و مقدار
  `meta.readmodel.version`.
- قرارداد رسمی machine-readable: `GET $B/openapi.json` (OpenAPI 3.1).
- آزمون‌های قرارداد سمت ما: `test_tasnim_api.py` (12 endpoint + contract +
  rate + hidden-context) و `test_tasnim_sdk.py` (SDK e2e) — خروجی‌های هر دو
  در گزارش PCM-20.6.4 ثبت شده است.

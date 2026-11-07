# مرجع API — `tasnim.ai.ismc.ir` (V1)

API **خواندنی** (read-only) روی read model SQLite/FTS5. پیشوند: `/api/v1/tasnim/`. همهٔ نمونه‌های این سند از **درخواست‌های واقعی** به سرویس زندهٔ محلی (read model v0003، 2026-11-07) گرفته‌اند — فقط `request_id`/`generated_at` در برخی نمونه‌ها برای خوانایی کوتاه شده‌اند.

مستندات مرتبط: [DATA-CONTRACT.md](DATA-CONTRACT.md) · [SECURITY.md](SECURITY.md) · OpenAPI: [`tasnim/web/openapi.py`](../../tasnim/web/openapi.py)

---

## ۱. اصول مشترک

### ۱.۱ Envelope پاسخ

هر پاسخ موفق 200:

```json
{
  "data": { "...": "..." },
  "meta": {
    "generated_at": "2026-11-07T13:11:22Z",
    "readmodel": {
      "content_sha256": "40f45e0b2c393a65569846aeaac4d45dcee4bd58a7f158b1554adf3755ca78e4",
      "version": "v0003"
    },
    "request_id": "req_e9fd8c6bab0d400c",
    "next_page_token": "Mg=="
  }
}
```

- `request_id`: `req_` + 16 hex — برای گزارش incident.
- `meta.readmodel` در **هر** پاسخ → کلاینت همیشه می‌داند روی کدام نسخه/محتوا جواب گرفته.
- `next_page_token` فقط در پاسخ‌های paginated.
- JSON با `ensure_ascii=False` (فارسی خوانا).

### ۱.۲ قرارداد خطا

هر خطا JSON با این فیلدهاست (status + `code` ثابت، `type` URI پایدار):

```json
{
  "type": "https://tasnim.ai.ismc.ir/errors/page-not-found",
  "title": "Page not found",
  "status": 404,
  "message": "صفحه‌ای با item_index 5000 در پیکره وجود ندارد.",
  "code": "PAGE_NOT_FOUND",
  "request_id": "req_f52f6ecc87e54482",
  "details": {
    "item_index": 5000,
    "in_missing_range": [3649, 11182],
    "suggestion": "نزدیک‌ترین صفحات موجود: 3648، 11183"
  }
}
```

| HTTP | `code` | `type` slug | چه‌وقت | `details` |
|------|--------|-------------|--------|-----------|
| 404 | `PAGE_NOT_FOUND` | `page-not-found` | `/pages/{n}` موجود نیست | `item_index`، `in_missing_range` (اگر در شکاف)، `suggestion` |
| 404 | `VOLUME_NOT_FOUND` | `volume-not-found` | `/volumes/{id}` نامعتبر | `volume_id` |
| 404 | `TOPIC_NOT_FOUND` | `topic-not-found` | `/topics/{id}` نامعتبر | `topic_id` |
| 404 | `NOT_FOUND` | `not-found` | مسیر API ناشناخته | `path` (request_id در این حالت `req_unknown` است — قبل از middleware) |
| 503 | `SURAH_INDEX_NOT_SUPPORTED` | `surah-index-not-supported` | `/surahs` و `/surahs/{id}` — **صادقانه، نه خطا** | `status: not_supported`، `coverage: "0/114"`، `reason`، `evidence[4]`، `next_planned` (+ `surah_id` در detail) |
| 429 | `RATE_LIMITED` | `rate-limited` | limit هر-IP فراتر رفته | `limit`، `window: "60s"`، `endpoint_class`؛ header `Retry-After` |
| 400 | `INVALID_QUERY` | `invalid-query` | `q` زیر 2 یا بالای 64 کاراکتر | `param: "q"` |
| 400 | `INVALID_PARAMETER` | `invalid-parameter` | مثلاً `limit` عدد نیست | `param` |
| 400 | `INVALID_SORT` | `invalid-sort` | `sort` خارج از whitelist | `allowed: ["volume_no", "page_count"]` |
| 400 | `INVALID_PAGE_TOKEN` | `invalid-page-token` | `page_token` corrupt | — |

`message` همیشه فارسی است؛ `title`/`code`/`type` ثابت انگلیسی/URI برای ماشین‌خوانی. **هیچ خطایی stack trace یا مسیر داخلی لو نمی‌دهد** (handler 500 عمومی فارسی).

### ۱.۳ صفحه‌بندی (pagination)

- پارامترها: `limit` (پیش‌فرض 50؛ جستجو 20؛ **حداکثر 200** — مقدار بیشتر clamp می‌شود) و **یا** `offset` **یا** `page_token` (base64 opaque).
- `page_token`ها در نمونه‌های واقعی: `"MQ=="` = 1، `"Mg=="` = 2، `"Mw=="` = 3. توکن از `meta.next_page_token` پاسخ قبلی گرفته شود (ساخت توکن دستی ممکن نیست).
- پاسخ paginated: `data.items[]` + `data.total`.

### ۱.۴ Caching / ETag

- **ETag قوی** `"sha256(DBSHA|key)[:32]"` برای `/catalog`، `/volumes`، `/volumes/{id}`، `/pages/{n}`، `/topics`، `/topics/{id}`، `/statistics` — چون در SHA خود db گنجانده‌اند، با هر build جدید خودبه‌خود invalid می‌شوند. `If-None-Match` → **304 با بدنهٔ خالی** + همان ETag.
- **ETag ضعیف** `W/"…"` فقط برای `/search` + `Cache-Control: no-store` (نقشهٔ نتایج باید تازه بماند؛ با این حال 304 با If-None-Match ضعیف کار می‌کند — تست `test_weak_etag_no_store_304`).
- `Cache-Control` نمونه‌ها: `/catalog` = `public, max-age=60, stale-while-revalidate=300`؛ `/volumes/{id}` = `max-age=3600`.
- 304 واقعی نمونه (درخواست دوم `/catalog` با `If-None-Match`): **بدنه خالی** — فقط هدرها.

### ۱.۵ Rate limiting

- bucket **هر-IP، هر-دقیقهٔ تقویمی**، ذخیره‌شده در SQLite (`tasnim_rate_limits.db`) با `threading.Lock` (thread-safe؛ تست `test_rate_limiter_thread`).
- limitها: **search 30/min** · **read 120/min** (بقیهٔ endpointها کلاس read).
- IP کلاینت = اولین ورودی هدر `X-Forwarded-For` اگر موجود بود، وگرنه `remote_addr`. (nginx `X-Forwarded-For` را append-only می‌سازد → XFF ساختگی از بیرون نمی‌تواند bucket key شود — [SECURITY.md](SECURITY.md) §۴.)
- **معاف (EXEMPT):** `/health`، `/openapi.json`، `/docs` — برای monitoring و dev.

### ۱.۶ OpenAPI و docs

- `GET /api/v1/tasnim/openapi.json` — spec **3.1.0**، `title: "Tasnim Web V1 API (read model)"`، `version: 1.0.0`، **14 path**، schemas: `Error`، `Meta`، `PageRef`. `servers`: canonical + `http://127.0.0.1:5071`. توضیحات spec صادقانه: rag `not_connected`، surahs 503.
- `GET /api/v1/tasnim/docs` — پوستهٔ HTML **آفلاین** (بدون CDN) که spec را از `openapi.json` می‌کشد. انحراف مکتوب از Swagger UI کامل.

---

## ۲. Endpointها (12 + 2 dev)

### 2.1 `GET /health` — بدون rate limit

```bash
curl http://127.0.0.1:5071/api/v1/tasnim/health
```

```json
{
  "data": {
    "db_quick_check": "ok",
    "readmodel": {
      "content_sha256": "40f45e0b2c393a65569846aeaac4d45dcee4bd58a7f158b1554adf3755ca78e4",
      "db_sha256": "353f413b00467640fabfed267c9a2933a64495f3bfb3bab7e42cd43a54d9c0fd",
      "version": "v0003"
    },
    "status": "ok",
    "uptime_s": 150.7
  },
  "meta": { "generated_at": "2026-11-07T13:11:22Z", "readmodel": { "content_sha256": "40f4…", "version": "v0003" }, "request_id": "req_c233bef816af441f" }
}
```

`db_quick_check` یک `PRAGMA integrity_check` سبک نیست — یک query سبک روی read model است (سرعت بالا برای healthcheck).

### 2.2 `GET /catalog` — ETag قوی، `Cache-Control: public, max-age=60, stale-while-revalidate=300`

```json
{
  "data": {
    "counts": {
      "headings": 10739,
      "missing_item_index": 45243,
      "pages": 45844,
      "topics": 1080,
      "volumes": 6
    },
    "coverage": {
      "definition": "pages/(pages+missing_item_index) — شمارنده‌های زندهٔ read model",
      "present_ratio": 0.5033
    },
    "edition": { "edition_id": "tasnim_hamta__hamta-2026", "name": "خروجی کراول hamta-2026" },
    "rag_status": "not_connected",
    "readmodel": { "content_sha256": "40f45e0b…", "version": "v0003" },
    "work": { "name": "تفسیر تسنیم", "work_id": "tasnim_hamta" }
  },
  "meta": { "generated_at": "…", "readmodel": { "…": "…" }, "request_id": "req_e9fd8c6bab0d400c" }
}
```

### 2.3 `GET /volumes` — paginated (`limit` default 50، max 200؛ `sort` ∈ {`volume_no`,`page_count`}؛ `offset`/`page_token`)

نمونهٔ واقعی `?limit=2` (دو جلد اول):

```json
{
  "data": {
    "items": [
      {
        "ambiguity": {
          "flag": true,
          "overlap_note": [
            { "item_index_count": 9,
              "ranges": [[2,4],[9,9],[14,14],[19,19],[24,26]],
              "volume_id": "tasnim_hamta__hamta-2026__vol047" }
          ]
        },
        "coverage": {
          "missing_count": 16,
          "ranges": [[5,8],[10,13],[15,18],[20,23]],
          "statuses": ["covered_by_other_volume","covered_by_other_volume","covered_by_other_volume","covered_by_other_volume"]
        },
        "first_page_item_index": 2,
        "item_index_max": 26, "item_index_min": 2, "last_page_item_index": 26,
        "page_count": 9,
        "title": "جلد 1",
        "volume_id": "tasnim_hamta__hamta-2026__vol001",
        "volume_no": 1
      },
      {
        "ambiguity": { "flag": false, "overlap_note": null },
        "coverage": { "missing_count": 0, "ranges": [], "statuses": [] },
        "first_page_item_index": 11183,
        "item_index_max": 11204, "item_index_min": 11183, "last_page_item_index": 11204,
        "page_count": 22,
        "title": "جلد 12",
        "volume_id": "tasnim_hamta__hamta-2026__vol012",
        "volume_no": 12
      }
    ],
    "total": 6
  },
  "meta": { "generated_at": "…", "next_page_token": "Mg==", "readmodel": { "…": "…" }, "request_id": "req_185222269b1f45bc" }
}
```

جلد‌های 6 تا (زنده): vol001 (9 صفحه، ii 2..26) · vol012 (22، 11183..11204) · vol047 (9,391، 0..55698) · vol056 (29,689، 59591..89279) · vol080 (767، 90311..91077) · volkeyd531f422 (5,966، 39004..55714، `volume_no: null`، `title: "نامشخص"`).

خطا نمونه (`/volumes/does_not_exist`):

```json
{ "code": "VOLUME_NOT_FOUND", "details": { "volume_id": "does_not_exist" },
  "message": "جلدی با volume_id «does_not_exist» در read model نیست.",
  "request_id": "req_04634ea9ba27416d", "status": 404, "title": "Volume not found",
  "type": "https://tasnim.ai.ismc.ir/errors/volume-not-found" }
```

### 2.4 `GET /volumes/{volume_id}` — ETag قوی، `Cache-Control: max-age=3600`

نمونهٔ واقعی `vol047` (ترuncated برای خوانایی؛ فیلدها کامل در `data`):

```json
{
  "data": {
    "ambiguity": { "flag": true, "overlap_note": [ { "item_index_count": 9,
      "ranges": [[2,4],[9,9],[14,14],[19,19],[24,26]],
      "volume_id": "tasnim_hamta__hamta-2026__vol001" } ] },
    "coverage": { "missing_count": 46308, "ranges": [[3649,49956]],
                  "statuses": ["partial_other_volume"] },
    "dup_item_index_with": [ { "item_index_count": 9,
      "ranges": [[2,4],[9,9],[14,14],[19,19],[24,26]],
      "volume_id": "tasnim_hamta__hamta-2026__vol001" } ],
    "first_page": { "item_index": 0, "page_id": "tasnim_hamta__hamta-2026__vol047__p0" },
    "first_page_item_index": 0,
    "item_index_max": 55698, "item_index_min": 0,
    "last_page": { "item_index": 55698, "page_id": "tasnim_hamta__hamta-2026__vol047__p55698" },
    "last_page_item_index": 55698,
    "missing_ranges": [ { "from": 3649, "missing_count": 46308,
                          "status": "partial_other_volume", "to": 49956 } ],
    "page_count": 9391,
    "strategy": "url_section",
    "title": "جلد 47",
    "top_headings": [
      { "count": 317, "text": "تفسیر" }, { "count": 301, "text": "مفردات" },
      { "count": 273, "text": "تناسب آیات" }, { "count": 245, "text": "گزیدهٔ تفسیر" },
      { "count": 243, "text": "بحث روایی" }, { "count": 201, "text": "اشارات و لطایف" },
      { "count": 65, "text": "گزیده تفسیر" }, { "count": 24, "text": "1. شأن نزول" },
      { "count": 7, "text": "لطایف و اشارات" }, { "count": 7, "text": "گزیدهٴ تفسیر" }
    ],
    "volume_id": "tasnim_hamta__hamta-2026__vol047",
    "volume_no": 47
  },
  "meta": { "…": "…" }
}
```

جلد «نامشخص» (`volkeyd531f422`): `volume_no: null`، `strategy: "none"`، `top_headings` خودش (تفسیر 206، مفردات 206، گزیدهٔ تفسیر 205، تناسب آیات 184، بحث روایی 161، …) — UI بج «در حال بازیابی شمارهٔ جلد» می‌زند.

### 2.5 `GET /surahs` و `GET /surahs/{surah_id}` — **503 صادقانه**

```json
{
  "code": "SURAH_INDEX_NOT_SUPPORTED",
  "details": {
    "coverage": "0/114",
    "evidence": [
      "0 فیلد surah در schema پیکره",
      "0 هدر با پیشوند سخت «تفسیر سوره/سوره/سورة» از 10,739 هدر",
      "0 صفحهٔ تعلق‌داده‌شده به سوره",
      "265 هدرِ شلِ حاوی «سوره» همه sub-heading عمومی‌اند"
    ],
    "next_planned": "surah index text-level برای نسخهٔ بعدی پیکره (خارج از V1)",
    "reason": "در پیکرهٔ v0003 هیچ مارکر مطمئن سوره وجود ندارد: فیلد surah در schema نیست؛ 0 هدر با پیشوند سخت سوره؛ پوشش canonical 0/114",
    "status": "not_supported"
  },
  "message": "در پیکرهٔ v0003 هیچ مارکر مطمئن سوره وجود ندارد: …",
  "request_id": "req_a76f1f6785d049f3",
  "status": 503,
  "title": "Surah index not supported",
  "type": "https://tasnim.ai.ismc.ir/errors/surah-index-not-supported"
}
```

(`surahs/{surah_id}` دقیقاً همین را برمی‌گرداند + `details.surah_id`.) **هیچ نام سوره‌ای ساختگی سرو نمی‌شود.**

### 2.6 `GET /topics` — paginated (default limit 50)

```json
{
  "data": {
    "items": [
      { "display_text": "تفسیر", "first_item_index": 273,
        "first_page_id": "tasnim_hamta__hamta-2026__vol047__p273",
        "page_count": 1678, "topic_id": "t-bd4e94070cce", "volume_count": 5 },
      { "display_text": "گزیدهٔ تفسیر", "first_item_index": 271,
        "first_page_id": "tasnim_hamta__hamta-2026__vol047__p271",
        "page_count": 1677, "topic_id": "t-683d792bac44", "volume_count": 5 },
      { "display_text": "مفردات", "first_item_index": 662,
        "first_page_id": "tasnim_hamta__hamta-2026__vol047__p662",
        "page_count": 1631, "topic_id": "t-80649ebf018a", "volume_count": 4 }
    ],
    "total": 1080
  },
  "meta": { "generated_at": "…", "next_page_token": "Mw==", "readmodel": { "…": "…" }, "request_id": "req_d60fb977dfca4872" }
}
```

### 2.7 `GET /topics/{topic_id}` — paginated occurrences

نمونهٔ واقعی `t-bd4e94070cce` (تفسیر):

```json
{
  "data": {
    "display_text": "تفسیر",
    "first_item_index": 273,
    "first_page_id": "tasnim_hamta__hamta-2026__vol047__p273",
    "normalized_text": "تفسیر",
    "occurrences": [
      { "heading_text": "تفسیر", "is_heading_page": true, "item_index": 273,
        "page_id": "tasnim_hamta__hamta-2026__vol047__p273",
        "volume_ref": { "volume_id": "tasnim_hamta__hamta-2026__vol047", "volume_no": 47 } },
      { "heading_text": "تفسیر", "is_heading_page": true, "item_index": 333, "page_id": "…p333", "volume_ref": { "…": 47 } },
      { "heading_text": "تفسیر", "is_heading_page": true, "item_index": 402, "page_id": "…p402", "volume_ref": { "…": 47 } }
    ],
    "occurrences_total": 1678,
    "page_count": 1678,
    "parent_topic": { "count": 1676, "display_text": "گزیدهٔ تفسیر", "topic_id": "t-683d792bac44" },
    "sample_pages": [ { "item_index": 273, "page_id": "…p273" }, { "item_index": 333, "page_id": "…p333" }, { "item_index": 402, "page_id": "…p402" } ],
    "topic_id": "t-bd4e94070cce",
    "volume_count": 5
  },
  "meta": { "…": "…" }
}
```

### 2.8 `GET /pages/{item_index}` — ETag قوی؛ `?dup_rank=N` برای نسخه‌های تکراری

نمونهٔ واقعی `/pages/2` (متن کامل 1,861 کاراکتر؛ اینجا 2 جملهٔ اول به‌عنوان نمونه):

```json
{
  "data": {
    "barg": 2,
    "dup_rank": 0,
    "duplicates": [
      { "dup_rank": 1, "page_id": "tasnim_hamta__hamta-2026__vol047__p2__d1",
        "volume_id": "tasnim_hamta__hamta-2026__vol047" }
    ],
    "heading": null,
    "item_index": 2,
    "metadata": {
      "captured_at": "2026-10-25 16:50:40",
      "content_sha256": "c5733f9083ca4b93139e0909bd1dbb268b275ffe9d289c8aa86044284eaffb38",
      "page_id": "tasnim_hamta__hamta-2026__vol001__p2",
      "section": "تفسیر تسنیم جلد (1)",
      "source_page_id": 11707,
      "source_url": "https://tasnim.hamtaa.org/payload?file_id=tasnim&item_index=2&section=…"
    },
    "next_page_reference": { "exists": true, "gap_before": 1, "item_index": 3,
                             "page_id": "tasnim_hamta__hamta-2026__vol001__p3" },
    "page_id": "tasnim_hamta__hamta-2026__vol001__p2",
    "previous_page_reference": { "exists": true, "gap_before": 1, "item_index": 1,
                                  "page_id": "tasnim_hamta__hamta-2026__vol047__p1" },
    "quality": { "flags": ["dup_item_index"], "source_char_cap": null,
                 "status": "dup_item_index", "truncated_at_source": false },
    "rag_status": "not_connected",
    "reference": {
      "barg": 2, "canonical_url": "https://tasnim.ai.ismc.ir/page/2",
      "content_sha256": "c5733f90…", "edition_id": "tasnim_hamta__hamta-2026",
      "item_index": 2, "page_id": "tasnim_hamta__hamta-2026__vol001__p2",
      "source_url": "…", "volume_id": "tasnim_hamta__hamta-2026__vol001",
      "volume_no": 1, "work_id": "tasnim_hamta"
    },
    "visible_content": {
      "char_count": 1861,
      "record_class": "CONTENT_PAGE",
      "text": "بسمه تعالی شأنه موقعیت قرآن قرآن که کلید باب کنز مخفی است … (متن کامل صفحه در پاسخ واقعی)"
    },
    "volume": { "ambiguity": true, "attribution": "ambiguous", "title": "جلد 1",
                "volume_id": "tasnim_hamta__hamta-2026__vol001", "volume_no": 1 }
  },
  "meta": { "generated_at": "2026-11-07T13:11:22Z",
            "readmodel": { "content_sha256": "40f45e0b…", "version": "v0003" },
            "request_id": "req_269074ff29a24f8b" }
}
```

نکات:
- `dup_rank=1` (درخواست `/pages/2?dup_rank=1`): همان page ولی `page_id …vol047__p2__d1`، `barg: 3`، `char_count: 1749`، `content_sha256: 43efadea…`، `canonical_url: /page/2?dup_rank=1` — یعنی **هر نسخهٔ تکراری هویت و canonical جدا دارد**.
- `previous_page_reference` برای ii=2 به vol047 اشاره می‌کند چون ii=1 فقط در vol047 وجود دارد (ناوبری روی زنجیرهٔ `next_page_id` است).
- برای ii که در شکاف است: 404 با `details.in_missing_range` + `suggestion` (نمونه §۱.۲).

### 2.9 `GET /pages/{item_index}/neighbors` — فقط prev/next + شکاف نزدیک (سبک؛ برای prefetch)

نمونهٔ واقعی `/pages/3648/neighbors` (آخرین صفحه قبل از بزرگ‌ترین شکاف):

```json
{
  "data": {
    "current": 3648,
    "missing_nearby": { "next_range": [3649, 11182], "prev_range": null },
    "next": {
      "exists": true,
      "gap": { "exists": false, "gap_before": 1, "in_missing_range": [3649, 11182],
               "item_index": 3649, "next_available_item_index": 11183 },
      "gap_before": 7535,
      "in_missing_range": [3649, 11182],
      "item_index": 11183,
      "next_available_item_index": 11183,
      "page_id": "tasnim_hamta__hamta-2026__vol012__p11183"
    },
    "prev": { "exists": true, "gap_before": 1, "item_index": 3647,
              "page_id": "tasnim_hamta__hamta-2026__vol047__p3647" }
  },
  "meta": { "…": "…" }
}
```

یعنی «بعد از 3648، 7,534 صفحهٔ بعدی (3649..11182) مفقودند؛ اولین صفحهٔ موجود 11183 است» — UI دقیقاً همین را نمایش می‌دهد.

### 2.10 `GET /search?q=…` — `q` بین 2 تا 64 کاراکتر؛ `volume_id` اختیاری؛ limit default 20؛ **ETag ضعیف + no-store**

نمونهٔ واقعی `q=قرآن` (20 نتیجه از `total: 6760`؛ 3 اولین نتیجه):

```json
{
  "data": {
    "query": { "raw": "قرآن", "tokens": ["قرآن"] },
    "results": [
      {
        "heading": null,
        "item_index": 91,
        "page_id": "tasnim_hamta__hamta-2026__vol047__p91",
        "quality_status": "ok",
        "snippet": "…ند اهل بیت عصمت و طهارت ( علیهم السلام ) دیگران را از تفسیر <mark>قرآن</mark> به قرآن منع کرده اند …",
        "volume_ref": { "ambiguous": false, "volume_id": "tasnim_hamta__hamta-2026__vol047", "volume_no": 47 }
      },
      {
        "heading": null, "item_index": 63, "page_id": "…vol047__p63", "quality_status": "ok",
        "snippet": "اکنون که مدعا ( استقلال <mark>قرآن</mark> در حجیت و دلالت بر معارف دین ) روشن شد …",
        "volume_ref": { "ambiguous": false, "volume_id": "tasnim_hamta__hamta-2026__vol047", "volume_no": 47 }
      },
      {
        "heading": null, "item_index": 59645, "page_id": "…vol056__p59645", "quality_status": "ok",
        "snippet": "در مباحث اصول فقه و تفسیر <mark>قرآن</mark> کریم این پرسش مطرح شده است …",
        "volume_ref": { "ambiguous": false, "volume_id": "tasnim_hamta__hamta-2026__vol056", "volume_no": 56 }
      }
    ],
    "total": 6760
  },
  "meta": { "…": "…" }
}
```

- `snippet` = HTML sanitize‌شده با `<mark>` دور hit — کلاینت باید آن را به‌عنوان **safe HTML** از همین endpoint بپذیرد (ساخت‌شده در سرور با esc) یا strip کند.
- محدودیت‌های توکن‌سازی (بدون stemming فارسی؛ ZWNJ) — [DATA-CONTRACT.md](DATA-CONTRACT.md) §۷.۲.
- `volume_id` filter نمونه: `q=قرآن&volume_id=…vol047` → `total: 1568`.
- خطا نمونه: `q=a` (1 کاراکتر) → `INVALID_QUERY` / «q باید بین 2 تا 64 کاراکتر باشد».

### 2.11 `GET /statistics` — ETag قوی

```json
{
  "data": {
    "item_index": {
      "distinct": 45835, "duplicates": 9, "max": 91077, "min": 0,
      "missing": {
        "count": 45243,
        "definition": "item_indexهای بدون صفحه، از coverage (global) — با gaps manifest build شده",
        "ranges": [[3649,11182],[11205,39003],[44957,49956],[55699,55701],[55715,59590],[89280,90310]]
      },
      "rows": 45844
    },
    "pages_by_class": {
      "CONTENT_PAGE": 33443, "EMPTY_PAGE": 35, "SECTION_HEADING": 10739,
      "SHORT_CONTENT": 1589, "UNKNOWN_STRUCTURE": 38,
      "definition": "GROUP BY pages.record_class (زنده، read model)"
    },
    "quality_status": {
      "definition": "GROUP BY pages.status (زنده، read model); flags ممکن است بیشتر از status باشد (یک صفحه هم short و هم dup باشد)",
      "dup_item_index": 16, "empty": 35, "ok": 33399, "short": 12366, "truncated_at_2000": 28
    },
    "surah": { "coverage": "0/114",
               "definition": "fact-check PCM-20.6.4: 0 هدر با پیشوند سخت سوره؛ جدول surahs خالی",
               "status": "not_supported" },
    "text_length": { "definition": "histogram manifest (طول متن صفحات) — از build_meta، تعریف مکتوب",
                     "max": 2000, "p50": 64, "p90": 1710, "p99": 1985 },
    "topics": { "definition": "normalize tasnim-topic-norm/1.0 روی 100% هدرها؛ stable id t-+sha1[:12]",
                "distinct_normalized": 1080, "multi_page": 62 }
  },
  "meta": { "…": "…" }
}
```

هر بخش `definition` دارد — **آمار بدون تعریف مکتوب ممنوع** (AGENTS.md §۲.۹).

### 2.12 مسیرهای dev

| مسیر | توضیح |
|------|-------|
| `GET /openapi.json` | spec 3.1.0 کامل (14 path) — بدون rate limit |
| `GET /docs` | پوستهٔ HTML آفلاین (بدون CDN) که spec را می‌کشد — بدون rate limit |

### 2.13 SSR (frontend) — صفحات HTML (خارج از این API contract)

`/` · `/volumes` · `/volumes/{id}` · `/page/{n}` · `/page/{n}/neighbors` (JSON) · `/topics` · `/topics/{id}` · `/surahs` · `/search` · `/about` · 404. صفحات SSR داده را inline دارند و JS خنک‌طلبانه فقط `/pages/{n}/neighbors` می‌کشد. جزئیات رفتار: [USER-GUIDE-FA.md](USER-GUIDE-FA.md).

---

## ۳. خلاصهٔ rate limit و cache به‌صورت جدول

| endpoint | rate class | ETag | Cache-Control نمونه |
|----------|-----------|------|----------------------|
| /health | معاف | — | no-store |
| /catalog | read | قوی | public, max-age=60, stale-while-revalidate=300 |
| /volumes، /volumes/{id} | read | قوی | max-age=3600 (detail) |
| /pages/{n}، /pages/{n}/neighbors | read | قوی (page) | — |
| /topics، /topics/{id} | read | قوی | — |
| /surahs، /surahs/{id} | read | — | no-store (503) |
| /search | **search (30/min)** | ضعیف `W/…` | no-store |
| /statistics | read | قوی | — |
| /openapi.json، /docs | معاف | — | — |

## ۴. نمونه‌های کلاینت (زندهٔ احراز‌شده)

- **Python (stdlib فقط):** `tasnim/sdk/python/` — `TasnimClient` + CLI (`python -m tasnim_client --base http://127.0.0.1:5071 --page 2`)؛ ETag cache در حافظه؛ retry با backoff برای 429 (max_retries=3، max_backoff_s=65)؛ 23/23 تست + اجرای زنده.
- **JavaScript (ESM، بدون dependency):** `tasnim/sdk/javascript/` — `tasnim-client.mjs` + `tasnim.sdk.d.ts`؛ 22/22 تست + `node --check`.
- جزئیات کامل + نمونه‌های کد: [../PCM-20.6.4-INTEGRATION.md](../PCM-20.6.4-INTEGRATION.md) و [INDEX.md](INDEX.md) قلم ۹.

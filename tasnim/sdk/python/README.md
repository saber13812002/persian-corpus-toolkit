# tasnim_client — Python SDK برای API پیکرهٔ تسنیم (V1)

**PCM-20.6.4 · scope C.** یک کلاینت خواندنی (read-only) برای API رسمی
`/api/v1/tasnim` — ۱۲ endpoint، JSON، UTF-8. **فقط کتابخانهٔ استاندارد
Python** (`urllib`)؛ هیچ وابستگی سومی ندارد. Python 3.9+.

راهنمای کامل یکپارچه‌سازی (محدودیت‌ها، صفحه‌بندی، ETag، جدول خطا، الگوی
استناد RAG) در `docs/PCM-20.6.4-INTEGRATION.md` است.

## نصب / راه‌اندازی

بسته درون این مخزن است (publish جداگانه در V1 پیش‌بینی نشده). برای
استفاده، مسیر `tasnim/sdk/python` را به `PYTHONPATH` اضافه کنید:

```bash
export PYTHONPATH=tasnim/sdk/python:$PYTHONPATH   # bash
set PYTHONPATH=tasnim\sdk\python;%PYTHONPATH%     # Windows cmd
```

بعد:

```python
from tasnim_client import TasnimClient
c = TasnimClient("https://tasnim.ai.ismc.ir")
```

سرور عمومی V1: `https://tasnim.ai.ismc.ir` — هر اینستانس V1 دیگری هم
کار می‌کند (مثلاً `http://127.0.0.1:5071` برای test-local).

## نمونه‌های اصلی

```python
from tasnim_client import TasnimClient, TasnimAPIError

c = TasnimClient("https://tasnim.ai.ismc.ir")

# ۱) سلامت و هویت
print(c.get_health().data["readmodel"])
print(c.get_catalog().data["counts"])

# ۲) یک صفحه (heart of the contract)
p = c.get_page(2)
print(p.item_index, p.barg, p.volume_no)
print(p.text[:120])                    # visible_content.text
print(p.quality_status, p.flags)
print(p.next_item_index, p.previous_item_index)
print(p.canonical_url)                 # برای استناد

# ۳) حرکت gap-aware — اگر ii 3649..11182 نباشد، next می‌پرد:
for i in (3648, 3649, 11183):
    try:
        p = c.get_page(i)
        print(i, "->", p.next_item_index)
    except TasnimAPIError as e:
        print(i, e.code, e.details["in_missing_range"], e.details["suggestion"])

# ۴) همهٔ صفحات موجود در یک بازه (گاپ‌ها skip می‌شوند)
for page in c.iter_pages(0, 100, on_missing="skip"):
    ...

# ۵) جستجو
s = c.search("قرآن", limit=10)
print(s.data["total"], s.data["results"][0]["item_index"])

# ۶) موضوعات (پیمایش کامل صفحه‌به‌صفحه)
for t in c.iter_topics(limit=100):
    print(t["display_text"], t["page_count"])
detail = c.get_topic("t-bd4e94070cce")
print(detail.display_text, detail.occurrences_total)

# ۷) جلد‌ها
for v in c.iter_volumes(limit=20):
    print(v["volume_no"], v["title"], v["page_count"])
vol = c.get_volume("tasnim_hamta__hamta-2026__vol047")

# ۸) آمار زنده
print(c.get_statistics().data["item_index"])

# ۹) سوره‌ها — در V1 صادقانه 503 است
try:
    c.get_surahs()
except TasnimAPIError as e:
    print(e.status, e.code, e.details["coverage"])   # 503 SURAH_INDEX_NOT_SUPPORTED
```

## خطاها

* `TasnimAPIError(status, code, title, message, details, request_id,
  type, retry_after)` — برای هر پاسخ 4xx/5xx با envelope رسمی
  (RFC-7807). کدهای ثابت: `VOLUME_NOT_FOUND`, `TOPIC_NOT_FOUND`,
  `PAGE_NOT_FOUND`, `SURAH_INDEX_NOT_SUPPORTED`, `RATE_LIMITED`,
  `INVALID_QUERY`, `INVALID_PARAMETER`, `INVALID_SORT`,
  `INVALID_PAGE_TOKEN`.
* `TasnimClientError` — خطای transport (DNS، timeout، بدنهٔ غیر-JSON).

`request_id` (شکل `req_…`) را برای پیگیری در گزارش خطا بفرستید.

## Rate limit (۴۲۹)

سرویس‌دهنده ۳۰ درخواست جستجو/دقیقه و ۱۲۰ خوانش/دقیقه **به‌ازای هر IP**
دارد. در ۴۲۹ هدر `Retry-After` می‌آید. با `rate_limit_backoff=True`
(پیش‌فرض) کلاینت به‌صورت خودکار تا `max_retries` بار sleep+retry
می‌کند (سقف هر خواب = `max_backoff_s` ثانیه). با `False`، خطای
`RATE_LIMITED` بلافاصله بالا می‌آید تا تصمیم با شما باشد.

```python
c = TasnimClient(base, rate_limit_backoff=False)   # 429 -> throw
```

## صفحه‌بندی

`limit` (پیش‌فرض ۵۰؛ جستجو ۲۰؛ سقف ۲۰۰) + `offset` **یا** `page_token`.
تا جایی که صفحهٔ بعدی هست، `meta.next_page_token` در پاسخ می‌آید.
ژنراتورهای `iter_volumes()` / `iter_topics()` زنجیرهٔ token را
خودکار می‌پیوندند؛ برای `search` هم می‌توانید دستی `page_token`
بدهید.

## کش ETag (اختیاری)

پایه‌های پایدار (catalog/volumes/volume-detail/topic-detail/page/
neighbors/statistics) ETag قوی دارند. کلاینت یک کش in-memory
می‌گیرد (`etag_cache=True` پیش‌فرض): درخواست بعدی `If-None-Match`
می‌فرستد و در ۳۰۴ همان پاسخ قبلی با `from_cache=True` برمی‌گردد.
جستجو `no-store` است و هرگز کش نمی‌شود. برای بیرون‌اندازن کش:
`c.clear_etag_cache()`.

## CLI دمو

```bash
python -m tasnim_client --base http://127.0.0.1:5071 --page 2
python -m tasnim_client --search "تفسیر" --topic t-xxxxxxxx
```

خروجی JSON خلاصه‌شدهٔ همهٔ endpointهاست (فقط خواندنی).

## آزمون

تست end-to-end کلاینت: `test_tasnim_sdk.py` در ریشهٔ worktree
(روی فلکسچر offline، بدون شبکه):

```bash
python -X utf8 -m unittest test_tasnim_sdk -v
```

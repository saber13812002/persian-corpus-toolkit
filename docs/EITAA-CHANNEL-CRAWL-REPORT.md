# گزارش کراول کانال ایتا (PCM-EITAA)

تاریخ: 2026-11-25 — شاخه `pcm-20.9-knowledge-studio-factory` — **بدون deploy** (فقط کد محلی + تست)

## ۱. وضعیت قبل

- هیچ مسیر کراول برای کانال‌های ایتا وجود نداشت. تنها الگوی «اسکریپت + endpoint اختصاصی» کراول
  بیانات (farsi.khamenei.ir) بود: `corpus/scrape_khamenei.py` + endpointهای `/api/khamenei/*`.
- هدف: کانال `sharabebeheshti` یک‌بار در DB ثبت شود و کراولر **پست‌به‌پست** از تازه‌ترین
  تا قدیمی‌ترین جلو برود تا بعداً پیکره (JSONL → Dump → corpus → registry) از روی DB ساخته شود.

## ۲. طراحی

سند طراحی: [`docs/superpowers/specs/2026-11-25-eitaa-channel-crawl-design.md`](superpowers/specs/2026-11-25-eitaa-channel-crawl-design.md)
برنامه‌ی اجرا: [`docs/superpowers/plans/2026-11-25-eitaa-channel-crawl.md`](superpowers/plans/2026-11-25-eitaa-channel-crawl.md)

- محدوده: **متن پست + کاتالوگ رسانه** (عنوان/مدت/حجم — بدون دانلود فایل رسانه).
- روش: اسکریپت مستقل پایتون + endpointهای اختصاصی backend (الگوی khamenei).
- واقعیت صفحه‌بندی ایتا (زنده تأیید شده 2026-11-25):
  - صفحهٔ ۱ = ۱۲ پست تازه‌ترین (`/1303` … `/1314`) به ترتیب DOM.
  - قدم‌به‌قدم به عقب با `<a class="eme_messages_more" data-before="N">` → `?before=N`
    (بدون `<link rel="next">`؛ پراپ `q=` آخر آدرس باید حذف شود).
  - صفحهٔ پایانی (مثلاً `?before=13`) anchor ندارد و پست ۱ (سنگ‌شده/`service_message`)
    در آن است.

## ۳. فایل‌ها و endpointها

### backend (`backend/server.py` — سکشن EITAA، افزایشی)
- جدول‌ها (`ensure_eitaa_schema`): `eitaa_channels` (username PK + ۷ ستون + created/updated)
  و `eitaa_posts` (post_id PK + ۱۱ ستون قرارداد + content_hash/char_count/crawled_at +
  ایندکس `idx_eitaa_posts_channel`).
- endpointها (۸ عدد):
  | endpoint | کار |
  |---|---|
  | `POST /api/eitaa/channel` | ثبت/به‌روزرسانی کانال (idempotent upsert) |
  | `POST /api/eitaa/submit` | ذخیرهٔ یک پست + ترفیع صفحهٔ جاری به `done` + ثبت صفحهٔ بعد در `crawl_queue` (`page_type='eitaa_page'`, `site='eitaa'`) |
  | `POST /api/eitaa/seed` | صف‌کردن صفحهٔ اول کانال (idempotent) |
  | `GET /api/eitaa/pending` | فهرست صفحات pending |
  | `GET /api/eitaa/crawl-status?channel=` | وضعیت کراول (ثبت کانال، پست‌ها، max_post_number، pending) |
  | `GET /api/eitaa/stats` | شمارش کانال/پست/کاراکتر + by_type |
  | `GET /api/eitaa/posts?channel=&limit=&offset=` | لیست صفحه‌بندی‌شده (limit clamp 1..200) |
  | `POST /api/eitaa/reset` | پاک‌سازی کامل دو جدول + سطرهای `eitaa_page` صف |
- dedup پست: `content_hash` روی ۱۱ فیلد منهای `views` (تغییر «مشاهده» پست را دوباره نمی‌کند).

### اسکریپت (`corpus/scrape_eitaa.py`)
- `channel_url` / `extract_username` / `parse_channel` / `parse_posts` (قرارداد ۱۱ فیلدی) /
  `next_page_url` / `strip_tags` — خالص و تست‌شده با fixture واقعی.
- `submit_channel` / `submit_post` / `seed` / `_get` (retry + backoff `2*(n+1)`، 404→"") /
  `_session` (همان الگوی robust khamenei: `trust_env=False`، هدرهای مرورگری، `verify=False`).
- `crawl_channel(username, backend, session, max_pages, max_posts, delay, retries, sleep)`:
  GET صفحهٔ ۱ (خاموشی نهایی → `errors=1`) → `submit_channel` + `seed` → در هر صفحه:
  parse + `next_page_url` + submit همهٔ پست‌ها با `page_url`/`next_url` (frontier).
  توقف: بدون next URL، ۲ صفحهٔ خالی پیاپی، `max_pages`، یا `max_posts`.
- CLI: `--channel` (username یا URL)، `--backend`، `--max-pages`، `--max-posts`،
  `--delay 2.0`، `--parse-only` (فقط fetch صفحهٔ ۱ + JSON خروجی، بدون backend).

### fixtureهای زنده (در repo، برای تست آفلاین)
- `corpus/fixtures/eitaa_sharabebeheshti_page1.html` (86,895 کاراکتر؛ ۱۲ پست تازه‌ترین 1303..1314)
- `corpus/fixtures/eitaa_sharabebeheshti_oldest.html` (75,500 کاراکتر؛ پست‌های 1..12، بدون
  anchor ادامه، پست ۱ سنگ‌شده)

## ۴. نتایج تست (اعداد واقعی، اجرا 2026-11-25)

- `corpus`: `.venv\Scripts\python.exe -m unittest corpus.test_scrape_eitaa -v`
  → **10 تست OK** (T-01..T-05, T-03b: parsing واقعی صفحهٔ زنده + variantهای ویدیو/عکس/سنگ‌شده
  + terminal page؛ T-07..T-10: walk دو صفحّه با frontier، توقف روی خطای شبکه، توقف روی ۲ صفحهٔ
  خالی، `max_pages`).
- `backend`: رگرسیون کامل (12 ماژول شامل `test_eitaa`) → **Ran 256 tests — OK** (248
  رگرسیون قبلی + 8 EA). 18 red شناخته‌شدهٔ baseline (race S-07 استودیو) در اجراهای امروز
  بازتولید نشد (همانند اجراهای PCM-20.10/EXT-04).
- ruling ثبت‌شده در ledger: T-02 برنامه، پست 1303 را audio فرض کرده بود؛ fixture واقعی
  نشان می‌دهد 1303 **متنی** است (کپشن لینک کانال دیگر) و پست audio/`mp3` همان 1309 است
  (index 6). تست و برنامه هر دو اصلاح شدند.

## ۵. نحوهٔ اجرای واقعی

```bat
:: از ریشهٔ repo (backend روی 5055)
.venv\Scripts\python.exe corpus\scrape_eitaa.py --channel sharabebeheshti
:: یا فقط صفحهٔ اول برای بررسی (بدون backend)
.venv\Scripts\python.exe corpus\scrape_eitaa.py --channel sharabebeheshti --parse-only
:: محدودکننده‌ها
.venv\Scripts\python.exe corpus\scrape_eitaa.py --channel sharabebeheshti --max-pages 3 --max-posts 30
```

چک بعد از کراول:

```
curl http://127.0.0.1:5055/api/eitaa/crawl-status?channel=sharabebeheshti
curl http://127.0.0.1:5055/api/eitaa/stats
```

## ۶. موارد باقی‌مانده (خارج از محدودهٔ این مأموریت)

- دانلود خود فایل رسانه (mp4/mp3/عکس) — فعلاً فقط کاتالوگ.
- deploy روی s52 (برنامه‌ای برای این مأموریت نیست؛ بعد از سوار شدن درِ بعدی).
- کارت داشبورد ایتا (نمای خواندنی در `dashboard/`) — بعداً، از روی همین endpointها.
- اجرای زندهٔ کامل کانال + ساخت JSONL/Dump/پیکره از `eitaa_posts` (مصرف‌کنندهٔ بعدی).
- OpenAPI spec برای ۸ endpoint (الگوی PCM-19) — در صورت ورود به قرارداد رسمی.

## ۷. git / rollback

- commitهای مأموریت (بر `pcm-20.9-knowledge-studio-factory`):
  `f782a4a` (Task 1: schema + channel + submit)، `d50e886` (Task 2: seed/pending/status/stats/posts/reset)،
  `e20144f` (Task 3: scraper parsing + fixtureهای زنده)، + commit این مأموریت (Task 4:
  crawl walk + CLI + report + AGENTS).
- rollback = revert چهار commit؛ schema افزایشی است و `/api/eitaa/reset` داده‌ها را پاک می‌کند.
- بکاپ DB: لازم نبود (مهاجرت فقط جدول‌های جدید؛ بدون لمس production s52).

## ۸. روش تست دستی (سرور محلی)

1. `cd backend && ..\.venv\Scripts\python.exe server.py`
2. `curl -X POST http://127.0.0.1:5055/api/eitaa/seed -H "Content-Type: application/json" -d "{\"channel\":\"sharabebeheshti\"}"`
3. `.venv\Scripts\python.exe corpus\scrape_eitaa.py --channel sharabebeheshti --max-pages 2`
4. `curl http://127.0.0.1:5055/api/eitaa/crawl-status?channel=sharabebeheshti` → posts/max_post_number باید پر باشند.
5. `curl -X POST http://127.0.0.1:5055/api/eitaa/reset` → شمارنده‌ها صفر.

# گزارش تست — Tasnim Web V1

> PCM-20.6.4 · سند B15 · 2026-11-07
> نقشهٔ مادر: [INDEX.md](INDEX.md) · راهنمای توسعه: [DEVELOPER.md](DEVELOPER.md)

این سند **کل شواهد** تست V1 را با اعداد واقعی جمع می‌کند. هر عدد از یک اجرای واقعی در 2026-11-07 روی host BAKHTIARI-VM (Windows) می‌آید — عدد تخمینی در این سند نیست.

---

## ۱. خلاصه

| لایه | نتیجه |
|---|---|
| رگرسیون unit/integration (10 سوت) | **296 تست → 293 گذشت / 3 skip / 0 fail** (`Ran 296 tests in 53.016s`، exit 0) |
| smoke HTTP (15 چک) | **15 PASS / 0 FAIL** |
| E2E سناریو (12 مرحله) | **12/12 PASS** (e2e-evidence.json) |
| SDK Python (live) | **23/23** + CLI |
| SDK JavaScript (live) | **22/22** + `node --check` |
| curl واقعی روی دادهٔ v0003 | ✅ (بخش ۵) |

---

## ۲. جدول سوت‌ها (296 تست)

| سوت | تست‌ها | حوزه |
|---|---|---|
| `test_corpus_backfill.py` | 28 | backfill design (Track A، BF01–BF22b) |
| `test_corpus_gap_report.py` | 8 | gap report |
| `test_corpus_semantic.py` | 11 | semantic analysis |
| `test_corpus_semantic_v3.py` | 12 | semantic v3 |
| `test_corpus_tasnim.py` | 16 | corpus factory (T-01..T-16) |
| `test_corpus_truncation_report.py` | 5 | truncation report |
| `test_tasnim_api.py` | 66 | API + envelope + errors + rate-limit + ETag + HP-1 |
| `test_tasnim_frontend.py` | 53 | SSR pages + canary + dark mode + mobile |
| `test_tasnim_readmodel.py` | 46 | build + schema + HP-1 + cover + normalize/tokenize |
| `test_tasnim_sdk.py` | 51 | SDK Python + JS + CLI |
| **جمع** | **296** | |

### 3 skip (داده‌ای، نه شکست)

| skip | پیام واقعی | دلیل |
|---|---|---|
| `test_corpus_backfill.py:142` | «real v0003 data absent (worktree)» | canonical corpus در این worktree نیست (gitignored؛ روی s52). روی s52 اجرا می‌شود و آنجا skip نمی‌شود. |
| `test_corpus_gap_report.py:279` | «real snapshot not present» | همان دلیل — snapshot واقعی در worktree نیست |
| `test_corpus_truncation_report.py:198` | «real v0001 pages not present» | همان دلیل — صفحات v0001 واقعی در worktree نیست |

این 3 skip **تطبیق با واقعیت** هستند: داده‌های چندگیگی canonical corpus عمداً gitignored است و در این worktree کپی نشده. هیچ تست دیگری skip نشده (293/293 اجرای‌شده سبز).

### 4 bug که تست‌ها پیدا کردند (و fix شدند در همین مأموریت)

| # | bug | test anchor | fix |
|---|---|---|---|
| 1 | weak ETag برای `/search` باعث 304 **نادرست** می‌شد (search cache-less است) | `test_tasnim_api.py:585 test_weak_etag_no_store_304` (همچنین `:107 test_catalog_strong_etag_and_304`، `:454 test_page_304`، `:803 test_etag`) | search: `W/"…"` + `Cache-Control: no-store` (304 فقط برای strong ETag‌ها) |
| 2 | rate-limiter **thread-unsafe** بود (race در counterها — دو thread روی یک bucket) | `test_tasnim_api.py:775 test_rate_limiter_thread` | `threading.Lock` + `check_same_thread=False` روی connection |
| 3 | cover SVG **escape نمی‌شد** (عنوان جلد با `<`/`&` XSS داخل SVG) | `test_tasnim_readmodel.py:283 test_cover` (+ `test_tasnim_api.py:523 test_prefix_cover`، `test_tasnim_sdk.py:123 test_catalog_cover`) | `Markup`-wrapped escape در `cover.py` |
| 4 | SDK، ETag پاسخ را **نمی‌رساند** (کلاینت نمی‌تواند 304 بفرستد) | `test_tasnim_sdk.py:127 test_catalog_etag_304`، `:340 test_page_etag_304`، `:527 test_search_not_etag`، `:560 test_statistics_etag_304` (+ `test_tasnim_api.py:273 test_q_metachars_escap`) | ETag cache درون‌حافظه‌ای در هر دو SDK (Python + JS) |

هر 4 مورد: ابتدا test **fail** شد → fix → test سبز شد → رگرسیون کامل سبز شد.

---

## ۳. smoke 15/15 (ترتیب دقیق `run_suite`)

اجرا: `python -X utf8 -m tasnim.e2e.smoke --base http://127.0.0.1:5071` (سرور واقعی روی read model v0003)

| # | چک | چه چیزی را ثابت می‌کند |
|---|---|---|
| 1 | `health` | API زنده + version + content_sha256 (اگر مرده باشد، بقیه short-circuit) |
| 2 | `home` | صفحهٔ خانه 200 + RTL + شمارندهها |
| 3 | `volumes` | فهرست 6 جلد |
| 4 | `volume` (vol047) | جزئیات بزرگ‌ترین جلد (9,391 صفحه) |
| 5 | `page` (صفحه 2) | خواندن صفحهٔ واقعی با متن فارسی |
| 6 | `gap_recovery` (صفحه 5000 — داخل شکاف) | 404 + `in_missing_range` + پیشنهاد «نزدیک‌ترین صفحات موجود: 3648، 11183» |
| 7 | `topics` | فهرست موضوعات (1,080 normalized) |
| 8 | `surahs` | 503 صادقانه `SURAH_INDEX_NOT_SUPPORTED` |
| 9 | `search` | «قرآن» → total 6,760 + نتایج |
| 10 | `about` | صفحهٔ درباره 200 |
| 11 | `catalog_and_etag` | catalog + strong ETag → **304** با If-None-Match |
| 12 | `openapi` | spec 3.1.0 سرو می‌شود |
| 13 | `not_found` | 404 envelope استاندارد (path + request_id) |
| 14 | `font` | `/static/fonts/noto-naskh-arabic.ttf` → 200، content-type font/ttf، >10,000 B |
| 15 | `canary scan` | **HIDDEN-CANARY-DO-NOT-LEAK در هیچ HTML body‌ای نیست** (HP-1 در خروجی واقعی) |

خروجی: `RESULT [label]: N PASS / M FAIL / T total` → exit 0.

⚠️ **یادداشت Phase 7**: کامنت خط 44 `smoke.py` هنوز «6455 FTS matches in v0003» را ذکر می‌کند — عدد فعلی مصدق **6,760** است (3-way verified: live sample + raw FTS5 COUNT + E2E step 8). کامنت قدیمی است؛ کد درست است.

---

## ۴. E2E 12/12 (سناریوی کاربر واقعی)

اجرا: `python -X utf8 -m tasnim.e2e.e2e_scenario --base http://127.0.0.1:5071` → `e2e-evidence.json` (2026-11-07T10:54:33Z)

| # | مرحله | شواهد کلیدی |
|---|---|---|
| 1 | home | 200، 21,186 B؛ markerها: `missing_counter_45243`، `pages_counter_45844`، `present_ratio_50_3`، `rtl_fa` |
| 2 | فهرست جلد | 6 کارت + «نامشخص» (volkey) |
| 3 | ورود به vol047 | 31,041 B، محدودهٔ ii «0 – 55698» |
| 4 | صفحه 2 | prev=1، next=3 |
| 5 | متن واقعی فارسی | `text_len` 1,861 (تفسیر واقعی، نه placeholder) |
| 6 | next از 3648 | → 11,183 با یادداشت شکاف «3649..11182 (7534 pages)» |
| 7 | prev از 11183 | → 3,648 (معکوس) |
| 8 | search «قرآن» | total 6,760؛ marks 20؛ 20 نتیجه |
| 9 | topic «تفسیر» | `occurrences_shown` 25 |
| 10 | صفحهٔ سوره | پیام صادقانه؛ **هیچ نام سوره ساختگی** |
| 11 | پنجرهٔ متادیتا | 11 فیلد (page_id / sha256 / source_url / captured_at / rag …) |
| 12 | mobile viewport 375px | `captures/09-mobile-home.png` 33,041 B + `10-mobile-reader.png` 68,139 B |

---

## ۵. شواهد curl روی دادهٔ واقعی (v0003)

همه از سرور واقعی روی `tasnim/data/readmodel/v0003/` (نمونه‌های کامل در [API-REFERENCE.md](API-REFERENCE.md)):

```bash
$ curl -sS http://127.0.0.1:5071/api/v1/tasnim/health
# 200 — status ok، readmodel v0003، content_sha256 40f45e0b…

$ curl -sS "http://127.0.0.1:5071/api/v1/tasnim/pages/2"
# 200 — متن فارسی واقعی (1,861 کاراکتر)، page_id vol001__p2، prev/next

$ curl -sS "http://127.0.0.1:5071/api/v1/tasnim/pages/5000"
# 404 PAGE_NOT_FOUND، in_missing_range=true،
# suggestion: «نزدیک‌ترین صفحات موجود: 3648، 11183»

$ curl -sS "http://127.0.0.1:5071/api/v1/tasnim/search?q=%DA%98%D8%B1%D8%A2%D9%86"
# 200 — total 6760 (3-way verified)

$ curl -sS "http://127.0.0.1:5071/api/v1/tasnim/search?q=%DA%98%D8%B1%D8%A2%D9%82&volume=vol047"
# 200 — total 1568 (فقط vol047)

$ curl -sS "http://127.0.0.1:5071/api/v1/tasnim/statistics"
# 200 — status: ok 33399 / short 12366 / empty 35 / truncated_at_2000 28 / dup_item_index 16
#          record_class: CONTENT_PAGE 33443 / SECTION_HEADING 10739 / SHORT_CONTENT 1589 / EMPTY_PAGE 35 / UNKNOWN_STRUCTURE 38

$ curl -sS http://127.0.0.1:5071/api/v1/tasnim/surahs
# 503 SURAH_INDEX_NOT_SUPPORTED — coverage «0/114»، reason صادقانه
```

**cross-check عدد 6,760** (3 روش مستقل، نتیجهٔ یکسان):
1. `total` پاسخ live `/search?q=قرآن`
2. `SELECT COUNT(*) FROM pages_fts WHERE pages_fts MATCH '"قرآن"*'` (raw FTS5 روی همان DB)
3. step 8 از E2E (بخش ۴)

---

## ۶. SDK — live verification

### Python (`tasnim/sdk/python/tasnim_client/`)

- **23/23** تست live (کلاینت واقعی vs سرور واقعی: همهٔ endpoints + 429 backoff + ETag/304 + error handling)
- CLI: `python -X utf8 -m tasnim_client --base http://127.0.0.1:5071 --page 2` → متن صفحه 2 چاپ شد
- ویژگی‌های live-test شده: backoff روی 429 (`max_retries=3`، `max_backoff_s=65`)، in-memory ETag cache (304 دومین بار)، `TasnimAPIError` با code فارسی/انگلیسی

### JavaScript (`tasnim/sdk/javascript/`)

- **22/22** تست live (fetch واقعی vs سرور واقعی)
- `node --check tasnim-client.mjs` → syntax OK
- Node 18+، zero-dependency، ESM

---

## ۷. بازتولید همهٔ چیز (دستورهای دقیق)

```bash
# از ریشهٔ repo (worktree pcm-20.6-tasnim-web-v1):

# 0) سرور:
python -X utf8 -m tasnim.web.app \
  --db tasnim/data/readmodel/v0003/tasnim_readmodel.db \
  --port 5071 --rate-db .tmp_phase6/ratelimit.db

# 1) رگرسیون کامل (10 سوت، ~53s):
python -X utf8 -m unittest \
  test_corpus_backfill test_corpus_gap_report test_corpus_semantic \
  test_corpus_semantic_v3 test_corpus_tasnim test_corpus_truncation_report \
  test_tasnim_api test_tasnim_frontend test_tasnim_readmodel test_tasnim_sdk \
  -v
# → Ran 296 tests in ~53s / OK (skipped=3)

# 2) smoke (15 چک):
python -X utf8 -m tasnim.e2e.smoke --base http://127.0.0.1:5071
# → 15 PASS / 0 FAIL

# 3) E2E (12 مرحله + evidence json):
python -X utf8 -m tasnim.e2e.e2e_scenario --base http://127.0.0.1:5071

# 4) SDK Python (live):
cd tasnim/sdk/python && python -X utf8 -m unittest discover -v && cd ../..
#    + CLI: python -X utf8 -m tasnim_client --base http://127.0.0.1:5071 --page 2

# 5) SDK JS (live):
node tasnim/sdk/javascript/test/run.mjs    # 22/22
node --check tasnim/sdk/javascript/tasnim-client.mjs

# 6) verify read model identity:
sha256sum tasnim/data/readmodel/v0003/tasnim_readmodel.db
# → 353f413b00467640fabfed267c9a2933a64495f3bfb3bab7e42cd43a54d9c0fd
```

---

## ۸. محدودیت‌های مصدق تست (صادقانه)

| محدودیت | وضعیت |
|---|---|
| Docker build/run واقعی | ⛔ اجرا نشده (این host Docker ندارد — [DOCKER.md](DOCKER.md) §0). پوشش: اجرای مستقیم همان پروسه (smoke 15/15) |
| smoke روی ingress/https | ⛔ هنوز (domain provision نشده — [DEPLOYMENT.md](DEPLOYMENT.md) §6) |
| 3 تست داده‌محور | skip (corpus source در worktree نیست — روی s52 اجرا می‌شوند) |
| load/stress test | خارج از V1 (rate-limit + ETag طراحی شده‌اند ولی stress نشده) |
| cross-browser (IE/سازگاری‌های قدیمی) | خارج از V1 (Chrome/Edge/Firefox مدرن؛ RTL + mobile 375px evidence شده) |

---

## ۹. شواهد خام (کجا ببینم)

- `tasnim/e2e/e2e-evidence.json` — خروجی E2E 12/12
- `tasnim/e2e/screenshots/09-mobile-home.png`، `10-mobile-reader.png` — سکرین‌شات mobile
- `.tmp_phase6/` (این worktree، موقت) — نمونه‌های JSON API (24 فایل)، خروجی probeها، log سرور
- خروجی `unittest` — 296 سطر verbose (در ترمینال مأموریت؛ بازتولید: بخش ۷)

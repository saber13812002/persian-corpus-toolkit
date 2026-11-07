# راهنمای توسعه — Tasnim Web V1

> PCM-20.6.4 · سند B15 · 2026-11-07
> نقشهٔ مادر: [INDEX.md](INDEX.md) · قرارداد داده: [DATA-CONTRACT.md](DATA-CONTRACT.md) · API: [API-REFERENCE.md](API-REFERENCE.md)

---

## ۱. چیدمان repo (بخش‌های مربوط به V1)

```text
tasnim/                        ← کل زیرسیستم V1
├── Dockerfile                 ← image API (python:3.12-slim، فقط Flask)
├── docker-compose.tasnim.yml  ← stack: tasnim-api + tasnim-web(nginx)
├── .dockerignore
├── nginx/tasnim.conf          ← reverse proxy + security headers
├── e2e/
│   ├── smoke.py               ← smoke 15-check (HTTP-only، بدون درون‌مایهٔ app)
│   ├── e2e_scenario.py        ← سناریوی 12 مرحله‌ای عکاسی/ادعا
│   ├── screenshot.py          ← سکرین‌شات (اختیاری)
│   └── screenshots/           ← 09-mobile-home.png، 10-mobile-reader.png (evidence)
├── web/
│   ├── app.py                 ← main(): --db/--port/--host/--rate-db
│   ├── api.py                 ← 12 endpoint + envelope + error + rate-limit + ETag
│   ├── readmodel.py           ← build CLI + SCHEMA_SQL + normalize_topic + tokenize_fa + HP-1 guard
│   ├── build_cli.py           ← `python -m tasnim.web.build_cli build …`
│   ├── ssr.py                 ← render صفحات SSR (Jinja)
│   ├── pages.py               ← routeهای HTML (home/volumes/page/search/…)
│   ├── cover.py               ← تولید SVG جلد (escape-safe)
│   ├── openapi.py             ← spec 3.1.0 (14 path) — سرو می‌شود روی /openapi.json + /docs
│   ├── templates/             ← base, home, volumes, volume_detail, page, page_missing,
│   │                            search, topics, topic_detail, surahs, about, error, macros
│   └── static/
│       ├── css/tasnim.css     ← design system (توکن‌ها در بالا)
│       ├── js/tasnim.js       ← vanilla JS (بدون framework): nav، search، drawer، dark mode
│       └── fonts/             ← Noto Naskh Arabic + Vazirmatn (OFL) + OFL.txt
├── sdk/
│   ├── python/tasnim_client/  ← client استاندارد (urllib، Py3.9+) + CLI `python -m tasnim_client`
│   └── javascript/            ← ESM fetch zero-dep (Node 18+) + tasnim.sdk.d.ts
└── data/readmodel/v0003/      ← read model فعلی (260 MB) — gitignored

tasnim_test_support.py         ← test harness (ریشهٔ repo): fixture + reset + make_app
test_tasnim_api.py             ← 66 تست (API + envelope + errors + rate + ETag + HP-1 canary)
test_tasnim_frontend.py        ← 53 تست (SSR pages + canary + dark mode + mobile)
test_tasnim_readmodel.py       ← 46 تست (build + schema + HP-1 + cover + normalize/tokenize)
test_tasnim_sdk.py             ← 51 تست (SDK Python + JS + CLI)
test_corpus_*.py               ← 80 تست (corpus/backfill/semantic/truncation — Track A، جزئیات در docs)

design-system/tasnim-web/      ← MASTER.md + pages/ (منبع design، css پیاده‌سازی‌شده است)
docs/tasnim/                   ← همین بستهٔ اسناد (B15)
```

---

## ۲. شروع سریع (dev)

```bash
# 1) سرور:
python -X utf8 -m tasnim.web.app --db tasnim/data/readmodel/v0003/tasnim_readmodel.db --port 5071

# 2) smoke (در ترمینال دیگر):
python -X utf8 -m tasnim.e2e.smoke --base http://127.0.0.1:5071
# انتظار: 15 PASS / 0 FAIL

# 3) رگرسیون کامل (10 سوت؛ ~53 ثانیه):
python -X utf8 -m unittest \
  test_corpus_backfill test_corpus_gap_report test_corpus_semantic \
  test_corpus_semantic_v3 test_corpus_tasnim test_corpus_truncation_report \
  test_tasnim_api test_tasnim_frontend test_tasnim_readmodel test_tasnim_sdk \
  -v
# انتظار: Ran 296 tests … OK (skipped=3)
```

⚠️ **`-X utf8` روی Windows الزامی است** (stdout با emoji/فارسی؛ بدون آن `UnicodeEncodeError` در `cp1252`/`cp874`). روی Linux/macOS بی‌ضرر است.

### چرا `-X utf8` و نه `set PYTHONUTF8=1`؟
- `python -X utf8` در هر shell (cmd/PowerShell/bash) یکسان است و در CI هم قابل‌کپی است.
- خروجی‌های تست و smoke همگی فارسی/emoji دارند؛ بدون UTF-8 mode، حتی `print("✓")` روی Windows می‌شکند.

---

## ۳. test harness: `tasnim_test_support.py`

هر ماژول `test_tasnim_*.py` **باید** با `import tasnim_test_support as t` شروع کند. harness:

1. **یک DB موقت مشترک** می‌سازد (temp dir، حذف در teardown) و متغیرهای `PCT_DB`/`PCT_DASHBOARD_PASSWORD` را **قبل از** `import tasnim.web.api` ست می‌کند.
2. **`t.reset_db()`** (در `setUp` هر کلاس): DB را از نو می‌سازد — یعنی rate-limit/session بین تست‌ها نشت نمی‌کند و ترتیب اجرا مهم نیست.
3. **`t.make_app(rate_search=30, rate_read=120)`**: Flask app با همان `api.py` ولی rate-limit قابل‌تنظیم (در تست‌های 429، `rate_search=2` و …).
4. **`t.build_fixture_corpus(tmpdir)`**: یک corpus fixture معتبر 10-صفحه‌ای + **۲ فایل forbidden با canary** (`hidden-context-records.jsonl`، `context-records.jsonl` — محتوا: «HIDDEN-CANARY-DO-NOT-LEAK»). اگر builder فایل‌های forbidden را باز کند، build fail می‌شود و canary در هیچ output‌ای دیده نمی‌شود (تست‌های HP-1).

**قاعدهٔ طلایی** (هم‌سان PCM-12.3 مادر): هیچ ماژول تستی خودش `PCT_DB` نمی‌سازد یا `init_db` را مستقیم نمی‌خواند؛ همه از harness استفاده می‌کنند.

### 3 skip موجود (داده‌ای، نه شکست)

| skip | دلیل (assert/skipmessage واقعی) |
|---|---|
| `test_corpus_backfill.py:142` | «real v0003 data absent (worktree)» — corpus source در این worktree نیست (gitignored) |
| `test_corpus_gap_report.py:279` | «real snapshot not present» |
| `test_corpus_truncation_report.py:198` | «real v0001 pages not present» |

این سه تست روی s52 (که corpus source آنجا است) اجرا می‌شوند و آنجا skip نمی‌شوند.

---

## ۴. افزودن endpoint جدید (checklist)

1. **در `api.py`**: handler با همان الگو:
   - query parsing با همان اعتبارسنجی‌ها (limit clamp، sort whitelist، page_token base64)
   - response با `envelope(data, meta)` — `meta.request_id` را از `req_id()` بسازید
   - errorها از `err_payload(code, status, title, message, details)` — **code باید در جدول [API-REFERENCE.md](API-REFERENCE.md) §errors باشد**؛ کد جدید = آپدیت سند + OpenAPI
   - cache/ETag: strong ETag برای داده‌های read-model (`sha256(DBSHA|key)[:32]`)؛ weak `W/"…"` + `Cache-Control: no-store` برای `/search`
2. **در `openapi.py`**: path جدید (operationId snake_case، responses با `Error`/`Meta`/`PageRef` موجود)
3. **در `test_tasnim_api.py`**: تست happy + تست error + (اگر ETag) تست 304
4. **در `tasnim/e2e/smoke.py`**: چک اختیاری (فقط اگر مسیر کلیدی کاربر است)
5. **در اسناد**: [API-REFERENCE.md](API-REFERENCE.md) (نمونهٔ واقعی curl + پاسخ واقعی) + [INDEX.md](INDEX.md) اگر ساختار کلی عوض شد
6. **HP-1 (قانون سفید‌سازی سریالایزر)**: هر فیلدی که از DB به JSON می‌رود باید از whitelist صریح رد شود (`strict_pick`). **هرگز** `row → dict` خام. این قانون ۴ لایه دارد؛ جزئیات در [SECURITY.md](SECURITY.md).

### افزودن صفحهٔ SSR جدید

1. template در `tasnim/web/templates/` (از `base.html` ارث ببرد؛ `dir="rtl"` در base است)
2. route در `pages.py`
3. تست در `test_tasnim_frontend.py` (200 + markerهای کلیدی + canary scan خودکار روی همهٔ HTML)
4. اگر در nav است: `macros.html` / `base.html`

---

## ۵. FTS5 + توکنایزیشن فارسی (طرح + محدودیت‌های صادقانه)

`tokenize_fa/1.0` (در `readmodel.py`):

1. اعداد فارسی/عربی → ASCII
2. حذف diacritics (064B–065F، 0670، 08D3–08FF)
3. `ZWNJ` (06DC) → فاصله
4. حذف نشانه‌ها
5. token = `[0600-06FF 0750-077F]+` (یا اعداد/لاتین)

FTS: `pages_fts` **مستقل** (standalone FTS5)، columnها `page_id UNINDEXED, item_index UNINDEXED, tokens`؛ content = `tokenize_fa(text)`؛ query = prefix-AND: `"tok1"* AND "tok2"*` روی `tokens`.

**محدودیت‌های مصدّق (در build_meta ثبت است):**

- ❌ **ستمال‌یابی فارسی ندارد** — «خوانده/خواندن/خوانده‌ام» فقط با prefix مشترک پیدا می‌شوند؛ «می‌خواند» ≠ «خواندن».
- ❌ **کلمه‌های مرکب با ZWNJ**: چون ZWNJ→فاصله، «کتاب‌خانه» به‌صورت «کتاب خانه» توکن می‌شود؛ جستجوی «کتابخانه» (یک‌واژه) **پیدا نمی‌شود** — کاربر باید «کتاب خانه» بزند.
- ⚠️ **انحراف مصدق از spec**: FTS مستقل است (spec DDL با external-content column-mapping bug داشت) و محدودهٔ توکن `[0600-06FF]` است نه `[0621-064A]` (آن محدوده گ/پ/چ/ژ را بیرون می‌انداخت). هر دو در `build_meta.fts_note` ثبت‌اند.
- ⚠️ `unicode61` به‌عنوان tokenizer FTS5 برای columnهای UNINDEXED است؛ matching واقعی روی column `tokens` با query prefix است.

**برنامهٔ آینده (V1.5+)**: ارزیابی stemming فارسی (Persica/ICU) + index دوطرفه — در [ROADMAP.md](ROADMAP.md).

---

## ۶. بازسازی read model (build)

```bash
python -X utf8 -m tasnim.web.build_cli build \
  --corpus <dir-v0003> \
  --out tasnim/data/readmodel
```

- `<dir-v0003>`: دایرکتوری canonical corpus (pages.jsonl + heading-records.jsonl + corpus.json + manifest.json). **در این worktree موجود نیست** (gitignored؛ canonical روی s52) — برای dev از fixture harness (`t.build_fixture_corpus`) استفاده کنید.
- خروجی: `tasnim/data/readmodel/vNNNN/` (نسخه‌ی خودکار؛ v0003 فعلی).
- **زمان/حجم مورد انتظار** (v0003 واقعی): build ≈ چند دقیقه روی host متوسط؛ خروجی ≈ 260 MB DB + 6 SVG + sidecar.
- **deterministic**: دو build از همان corpus = SHA256 یکسان (تست شده در test_tasnim_readmodel).
- commit هر 5,000 صفحه؛ HP-1 guard در `_open` (هر open فایل forbidden → `BuildError`).
- validation vs `manifest.json` = build fail (نه warn).

**چک بعد از build**:
1. `sha256sum tasnim_readmodel.db` → مقایسه با `build.sha256` sidecar
2. `python -X utf8 -m tasnim.e2e.smoke --base http://127.0.0.1:5071` (با `--db` جدید)
3. `/api/v1/tasnim/statistics` — شمارندهها باید با `build_meta` تطبیق داشته باشند

**سواپ نسخه**: هرگز v0003 را جابجا/ویرایش نکنید (immutable). v0004 → دایرکتوری جدید → تغییر `--db`/mount → smoke → (rollback = برگشت mount). جزئیات: [DATA-CONTRACT.md](DATA-CONTRACT.md) §version-swap.

---

## ۷. طراحی بصری (design system)

- منبع: [`design-system/tasnim-web/MASTER.md`](../../design-system/tasnim-web/MASTER.md) + `pages/`
- پیاده‌سازی: `tasnim/web/static/css/tasnim.css` (توکن‌های CSS variable در ابتدای فایل) + `templates/`
- فونت‌ها: Noto Naskh Arabic (متن) + Vazirmatn (رابط) — هر دو **SIL Open Font License** (OFL.txt در کنار فونت‌ها؛ فونت‌ها در filesystem/container هستند، نه pypi)
- RTL: `dir="rtl"` در `<html>`؛ CSS logical properties
- dark reading mode: class `dark` روی `<html>` + prefers-color-scheme + toggle در nav (تست‌شده)
- mobile: viewport ≤375px evidence در [TEST-REPORT.md](TEST-REPORT.md) (سکرین‌شات‌ها در `tasnim/e2e/screenshots/`)

---

## ۸. نکات ویندوزی (این host = Windows)

- همیشه `python -X utf8` (بخش ۲)
- اسکریپت‌های پروب: **inline `python -c "…"` در cmd/PowerShell شکست می‌خورد** (quoting) — همیشه فایل `.py` جدا بنویسید (الگو: `.tmp_phase6/*.py`)
- `list_files` گاهی فایل‌های `.db` را نشان نمی‌دهد (attrib) — برای لیست دقیق از PowerShell `Get-ChildItem` استفاده کنید
- open SQLite handle روی Windows `os.remove` را خفه می‌کند — harness در teardown همهٔ connectionها را می‌بندد؛ اگر تست خودتان connection باز می‌گذارید، `tearDown` بنویسید
- مسیریابی: repo در `c:/Users/s.tabatabaei/Documents/saberprojects/pcm-20.6-tasnim-web-v1` — همهٔ commandها را از ریشهٔ repo بزنید

---

## ۹. وابستگی‌ها

| dependency | نسخهٔ پین | کجا |
|---|---|---|
| Python | 3.9+ (SDK) / 3.12 (Docker) | runtime |
| Flask | **3.1.3** (پین سخت در Dockerfile) | web + tests |
| Jinja2 | 3.1.6 (ترانزیت Flask) | templates |
| Werkzeug | 3.1.9 (ترانزیت Flask) | test client |
| SQLite (FTS5) | درون‌build CPython | read model |
| Node.js | 18+ (فقط SDK JS) | sdk/javascript |

**هیچ dependency دیگری نیست.** (هیچ DB driver، هیچ template engine خارجی، هیچ http library — همه stdlib + Flask.)

---

## ۱۰. قواعد سخت توسعه (خلاصهٔ AGENTS.md §2 + قوانین V1)

1. **بدون بکاپ، مهاجرت نمی‌شود**؛ مهاجرت‌ها فقط افزایشی.
2. **read model immutable** — هرگز داخل `v0003/` (یا هر نسخه) نوشته نمی‌شود؛ فقط با build جدید.
3. **HP-1**: hidden context هرگز عمومی نمی‌شود (4 لایه؛ canary test: T-HC-1..4).
4. **صفحات را با `page_id` کلید بزنید**؛ ترتیب = `item_index`؛ `barg` فقط display.
5. **کاور/تصویر ساختگی نداریم** — فقط SVG برنامه‌ای (escape-safe) یا badge.
6. **آمار ساختگی نداریم** — فقط شمارندهٔ واقعی DB.
7. **پورت‌ها**: 5070/5071 رزرو؛ container nameها با `tasnim-*`.
8. **backfill فقط با تأیید صریح انسانی** (Gate B؛ [../PCM-20.6.3-BACKFILL-DESIGN.md](../PCM-20.6.3-BACKFILL-DESIGN.md)).
9. `tasnim/data/` و `data/` gitignored — هرگز commit نشود.

# گزارش PCM-14A — لایه‌ی DB و REST API «استودیوی دانش» (Collections)

فاز 1A از PCM-14 (نسخه‌ی 2026-10): ساخت لایه‌ی پایتختی کالکشن‌های کتابخانه‌ی
دانش — جدول‌های SQLite، REST API پشت auth، و اسکلت رابط «استودیوی دانش».
**بدون** ES/ingest/chunking (آن‌ها PCM-14D/E) — مطابق تصمیم 2026-10-25
که از ES در فاز 1 استفاده نمی‌شود.

---

## ۱. وضعیت قبل (pre-state)

- هیچ جدول/جدول‌سازی یا API برای «دانش» وجود نداشت؛ کل دامنه‌ی Knowledge خالی بود.
- `backend/knowledge_api.py`، `backend/test_knowledge_api.py` و
  `dashboard/studio.html` موجود نبودند.
- 63 تست سبز (`test_api` 8 + `test_projects` 9 + `test_dashboard` 22 +
  `test_word_factory` 24)؛ هیچ تغییری در آن‌ها.
- `dashboard/index.html` بدون ورودی به استودیو.

## ۲. طراحی و تصمیمات (design)

### 2.1 مدل داده (فقط additive — AGENTS.md rule 2)

سه جدول جدید، هرکدام با `IF NOT EXISTS`؛ هیچ `DROP`/`RENAME`/تغییر نوع ستون:

| جدول | نقش | کلیدها/ایندها |
|---|---|---|
| `knowledge_collections` | کالکشن (یک کتاب/مجموعه منابع) | `id` PK، `UNIQUE(collection_id)`، `UNIQUE(slug)`، `UNIQUE(es_alias)`، `idx_kcol_updated` |
| `knowledge_collection_documents` | اسناد/فایل‌های داخل کالکشن (فاز D populate می‌کند) | `id` PK، `UNIQUE(file_id)`، `UNIQUE(document_id)`، `UNIQUE(collection_id,file_id)`، `idx_kcol_documents(collection_id,status)` |
| `knowledge_index_builds` | buildهای ES (فاز E populate) | `id` PK، `UNIQUE(iv_id)`، `idx_kbuilds_collection(collection_id,created_at DESC)` |

- `init_db()` از `knowledge_api.init_knowledge_db()` invoke می‌کند (خط ۳۵۰ در
  `server.py`) — در هر `reset_db()` تست هم اجرا می‌شود.

### 2.2 شناسه‌ها (deterministic, content-bound)

- `collection_id` = `'c-' + sha256(slug)[:8]` → **پایدار**؛ rename
  (تغییر `name`) آن را عوض **نمی‌کند**.
- `es_alias` = `'pct-col-' + slug` → ثابت برای هر کالکشن؛ `es_index`
  (مخصوص هر build) در فاز E با pattern `pct-col-{slug}-v{NNNN}` ساخته می‌شود.
- `slug` canonical: `^[a-z0-9]+(?:-[a-z0-9]+)*$`، طول ۲ تا ۶۴؛ ورودی حروف بزرگ
  **نرمال** می‌شود (نه reject): `'OloomAqli'` → `'oloomaqli'` و باید با
  slug کوچک‌نویس موجود collision بدهد (409) — وگرنه دو twin برای یک slug
  ساخته می‌شد.
- slug از نام فارسی: mapping صوتی `آاأإ→a, ب→b, پ→p, چ→ch, ...` فقط
  **پیش‌پر** comfort در UI است؛ server source of truth برای اعتبار slug است.

### 2.3 API (همه پشت `@require_auth` از `auth.py`، یعنی PCM-09)

| Method | Path | پاسخ | خطاها |
|---|---|---|---|
| POST | `/api/knowledge/collections` | `201 {ok, collection}` | 400 name/slug، 409 duplicate |
| GET | `/api/knowledge/collections` | `{ok,total,page,per_page,total_pages,collections}` | — |
| GET | `/api/knowledge/collections/<id>` | `{ok,collection}` | 404 |
| PATCH | `/api/knowledge/collections/<id>` | `200 {ok,collection}` (فقط display fields) | 400/404 |
| GET | `/api/knowledge/collections/<id>/builds` | `{ok,collection,builds}` | 404 |
| GET | `/api/knowledge/subjects` | `{ok,subjects:[{subject,n}]}` | — |

- list: `search` (LIKE روی name/slug)، `subject` (exact)، `sort` whitelist
  (`name|slug|updated_at|created_at`)، `order` ASC/DESC، `per_page` (1..100)
  + `page` → **LIMIT/OFFSET** — AGENTS.md rule 7 (کل‌جدول‌بارگذاری ممنوع).
- `ORDER BY` فقط از whitelist؛ همه query‌ها placeholder (`?`) — rule 7.
- PATCH فقط `name`/`description`/`subject` می‌گیرد و `collection_id/slug/
  es_alias/collection_version` را **نقصد** تغییر می‌دهد (تست ثابت‌کننده دارد).
- extension write APIها (`/api/projects*`) دست‌نخورده و باز ماندند (rule 6) —
  تست `test_existing_endpoints_still_open` این را ثابت می‌کند.

### 2.4 رابط «استودیوی دانش» (اسکلت، data-driven)

`dashboard/studio.html` — SPA یک‌صفحه‌ای، RTL، بدون framework، همان سبک
`dashboard/index.html`:
- **auth overlay** مثل index (POST `/api/auth/login`، 401 → overlay)؛ صفحه
  خودِ static بدون login سرو می‌شود (data پشت auth است) — test دارد.
- ۵ ستون (ساختار کتاب / اسناد / پردازش / کالکشن‌ها / جستجو)؛ در PCM-14A فقط
  **کالکشن‌ها** فعال است؛ بقیه grey-out با «در فاز بعد».
- ستون کالکشن‌ها: create form (نام فارسی + slug پیش‌پر از نام + موضوع +
  توضیح)، list با search/subject filter/صفحه‌بندی، detail (JSON ساختار کالکشن
  + نسخه‌های schema/norm/chunk + builds)، rename (PATCH).
- همه خروج‌های DOM از `escHtml()`؛ همه fetch `credentials:'same-origin'` —
  AGENTS.md rule 8.
- ورودی در `dashboard/index.html`: یک `<a class="nav-item">📚 استودیوی دانش</a>`
  (additive، target=_blank).

### 2.5 تست‌ها (KS-01..KS-05 + auth + prefill)

`backend/test_knowledge_api.py` — 19 تست، طبق rule PCM-12.3 اول
`import pct_test_support` سپس `import server`:

| کد | تست |
|---|---|
| KS-01 | create Persian collection؛ همه fieldها + مقادیر اولیه (counts 0، status `none`/`pending`، versions s-1/n-1/c-1) |
| KS-02 | `collection_id`/`slug`/`es_alias` deterministic و معتبر |
| KS-03 | duplicate slug → 409؛ slug نامعتبر (فاصله، فارسی، 1 کاراکتر، leading/trailing dash، >64) → 400 `field:slug`؛ uppercase → نرمال + collision |
| KS-04 | detail بعد از create + 404 |
| KS-05 | search (فارسی/لاتین)، subject filter، صفحه‌بندی (per_page/page/total_pages)، sort |
| + | PATCH rename هویت را ثابت نگه می‌دارد؛ PATCH خالی 400؛ subjects گروه‌بندی‌شده؛ builds endpoint + record؛ 401 بدون/با رمز غلط؛ studio page بدون login سرو می‌شود؛ `/api/stats` همچنان باز است |

## ۳. مهاجرت (migration)

- **فقط additive** (rule 2): `CREATE TABLE IF NOT EXISTS` × 3 + 4 index.
- **بدون** `ALTER` روی جدول موجود، **بدون** `DROP`/`RENAME`.
- در production: `init_knowledge_db()` با اولین start container اجرا می‌شود؛
  چون همه `IF NOT EXISTS` است، idempotent و بدون lock طولانی.
- **بکاپ** (rule 1): قبل از deploy، `.backup` + `PRAGMA integrity_check` (در
  `deploy/pcm14a_deploy.sh`).

## ۴. فایل‌ها و API

| فایل | تغییر |
|---|---|
| `backend/knowledge_api.py` | **جدید** — schema + 6 endpoint + `_slug_from_name` |
| `backend/server.py` | import + `init_knowledge_db()` در `init_db()` + blueprints registration |
| `backend/test_knowledge_api.py` | **جدید** — 19 تست |
| `dashboard/studio.html` | **جدید** — اسکلت استودیو (فقط کالکشن‌ها فعال) |
| `dashboard/index.html` | +1 خط: ورودی «📚 استودیوی دانش» |
| `deploy/pcm14a_deploy.sh` | **جدید** — بکاپ+integrity+build+up+smoke+rollback |

## ۵. نتیجه‌ی تست (local)

```
python -m unittest test_knowledge_api -v   →  Ran 19 tests ... OK
python -m unittest test_api test_projects test_dashboard test_word_factory test_knowledge_api
                                             →  Ran 82 tests ... OK   (forward)
(reverse order)                             →  Ran 82 tests ... OK
(repeat)                                    →  Ran 82 tests ... OK
```

82 تست (63 قبلی + 19 جدید) در هر ۳ ترتیب (forward/reverse/repeat) سبز —
isolation طبق PCM-12.3 (F-01) حفظ شده.

> Note: `ResourceWarning`ها از `open()` بدون `close()` در
> `test_word_factory.py` و یک `send_from_directory` در تست studio-page هستند؛
> روی Linux/s52 بی‌اثر و فقط cosmetic (Python 3.14-32bit روی Windows).

## ۶. نتیجه‌ی production (s52)

**هنوز deploy نشده.** این فاز local است و 82 تست سبز است؛ deploy + smoke test
با `bash deploy/pcm14a_deploy.sh` روی s52 انجام می‌شود (بکاپ + integrity +
`build` + `up -d backend` + smoke 401/200 + مقایسه‌ی شمارش‌ها). نتیجه‌ی
production پس از deploy در همین بخش ثبت می‌شود.
## ۷. SHA + لینک (commit)

- commit: `bcd985f` — [PCM-14A: Knowledge Studio collections layer
  (DB+REST+studio skeleton)](https://github.com/saber13812002/persian-corpus-toolkit/commit/bcd985f)
- pushed به `origin/main` (GitHub): `b3d9014..bcd985f`

## ۸. git status (آخرین)

```
## main...origin/main          (in sync)
```

فایل‌های commit `bcd985f` (7 files, +1760):
- `backend/knowledge_api.py` (جدید)
- `backend/test_knowledge_api.py` (جدید)
- `dashboard/studio.html` (جدید)
- `deploy/pcm14a_deploy.sh` (جدید)
- `backend/server.py` (ویرایش)
- `dashboard/index.html` (ویرایش)
- `گزارش-PCM-14A.md` (جدید)

## ۹. بکاپ / rollback

- بکاپ DB + snapshot deploy dir قبل از هر deploy (داخل `pcm14a_deploy.sh`).
- **Rollback**: چون همه‌ی چیز additive است، rollback = برگشتن کد به SHA قبلی
  (`docker compose build backend && up -d backend`). جداول جدید تا وقتی populate
  نشده‌اند، خالی و بی‌ضررند؛ `DROP TABLE knowledge_*` برای حذف کامل در صورت
  نیاز (فقط بعد از بکاپ).

## ۱۰. موارد باقی‌مانده (خارج از PCM-14A)

- **PCM-14B** — اسناد: upload/parse/normalize/quality + `knowledge_collection_documents`.
- **PCM-14C** — chunks + `documents/<id>/chunks` viewer + `chunk_id`.
- **PCM-14D** — ingest ES: build + `es_index` `pct-col-{slug}-v{NNNN}` + `knowledge_index_builds` + alias swap.
- **PCM-14E** — retrieval hybrid (dense `paraphrase-multilingual-MiniLM-L12-v2` + sparse SPLADE) + `knowledge_search` + RRF + filters.
- **PCM-14F/G** — semantic layers (terms/relations/graph/embedding) + dashboard retrieval tab.
- تکمیل ستون‌های grey-out استودیو (پردازش/جستجو/ساختار) در فازهای فوق.

## ۱۱. روش تست دستی (manual QA)

1. **بیلد/استارت**: `docker compose build backend && docker compose up -d backend`.
2. **ورود**: `https://<host>/dashboard/` → ورود → روی «📚 استودیوی دانش» کلیک (تب جدید).
3. **ایجاد**: در «کالکشن‌ها» → «کالکشن جدید»:
   - نام «کتابخانه علوم عقلی» → slug خودکار پر می‌شود (`oloom-e-om-e-aql`…؛ می‌توانید ویرایش کنید به `oloom-aqli`).
   - موضوع «فلسفه» → ثبت → 201، در list ظاهر می‌شود، counters `0/0`، status `none`/`pending`.
4. **تعیینی بودن**: بازخوانی — `collection_id` همان است؛ rename فقط `name` را عوض می‌کند، `collection_id/slug/es_alias` ثابت می‌مانند.
5. **تکرار**: همین slug → 409 «کالکشن با همین slug وجود دارد».
6. **نامعتبر**: slug با فاصله/فارسی/حرف بزرگ → حرف بزرگ نرمال می‌شود؛ بقیه 400 با پیام `slug`.
7. **جستجو/فیلتر/صفحه‌بندی**: چند کالکشن بسازید → search فارسی و لاتین، filter موضوع، صفحه‌بندی ۲ تایی.
8. **API خام** (با session): `curl -b cookie.jar -H 'Content-Type: application/json' -d '{"name":"X","slug":"x-y"}' .../api/knowledge/collections` → 201؛ بدون cookie → 401.
9. **extension دست‌نخورده**: یک crawl کوچک → `/api/projects*` همچنان کار می‌کند.
10. **smoke**: `curl -s .../api/stats` (200، بدون auth) + `integrity_check` بعد از deploy.

# PCM-14D — Work / Edition / Volume Registry (مدل سلسله‌مراتب اثر)

**وضعیت:** پیاده‌سازی‌شده و تست‌شده (139/139) — کد: `backend/knowledge_api.py`، تست‌ها:
`backend/test_work_registry.py` (RD-01…RD-07)
**محدودیت:** صرفاً افزایشی (additive) — بدون حذف/تغییر ستون، بدون دستکاری Dump d-1.

---

## ۱. خلاصه

قبل از PCM-14D، شناسه‌های `work_id`/`edition_id`/`volume_id` فقط به‌صورت
ستون‌های غیرنرمال‌شده (denormalized) روی جدول اسناد و در خروجی Word Factory
ذخیره می‌شدند؛ جدول «اثربار» مستقلی وجود نداشت و متادیتا فقط در سه scope
کالکشن/بچ/سند قابل تعریف بود. PCM-14D سه جدول ثبت (registry) برای
Work → Edition → Volume می‌سازد، ستون‌های entity را به جدول‌های متادیتا
افزوده و یک endpoint حل تعارض (resolve) با precedence مشخص اضافه می‌کند.

## ۲. ERD (نمای متنی)

```text
knowledge_collections (1)
        │  collection_id (int row id = کلید مسیری API)
        ▼
knowledge_collection_documents (N)          ── اسناد بارگذاری/پردازش‌شده
        │  work_id ─────────────┐
        │  edition_id ──┐       │
        │  volume_id ┐  │       │   (ستون‌های denormalized — از قبل موجود)
        ▼              ▼       ▼
knowledge_works (1) ◄── knowledge_editions (N) ◄── knowledge_volumes (N)
   (PK: work_id)        (PK: edition_id,      (PK: volume_id,
                          FK→work_id)           FK→edition_id, work_id)

knowledge_metadata_fields (m-1)      + work_id/edition_id/volume_id (sentinel '')
knowledge_metadata_values            + work_id/edition_id/volume_id (sentinel '')
        scope ∈ {collection, batch, document, work, edition, volume}
```

## ۳. جدول‌های جدید (DDL)

### knowledge_works
| ستون | نوع | توضیح |
|---|---|---|
| work_id | TEXT PK | `w-<sha8>` — کلید طبیعی قطعی |
| title / author / subject | TEXT | extract-only یا ویرایش کاربر |
| language | TEXT | |
| document_count | INTEGER | به‌روزرسانی می‌شود با هر process/upsert |
| source | TEXT | `factory` (پردازش خودکار) یا `user` (ثبت دستی) |
| created_at / updated_at | TEXT | UTC ISO |

### knowledge_editions
| ستون | نوع | توضیح |
|---|---|---|
| edition_id | TEXT PK | `e-<sha8>` |
| work_id | TEXT NOT NULL | FK منطقی به knowledge_works (index idx_ked_work) |
| publisher / publish_year / edition_label | TEXT | |
| language / document_count / source / created_at / updated_at | — | مانند works |

### knowledge_volumes
| ستون | نوع | توضیح |
|---|---|---|
| volume_id | TEXT PK | `v-<sha8>` |
| edition_id | TEXT NOT NULL | FK منطقی (index idx_kvol_edition) |
| work_id | TEXT NOT NULL | برای کوئری مستقیم (index idx_kvol_work) |
| volume_no | INTEGER | |
| label | TEXT | |
| document_count / source / created_at / updated_at | — | مانند works |

### ستون‌های اضافه‌شده به جدول‌های متادیتا (ALTER TABLE ADD COLUMN)
- `knowledge_metadata_fields` += `work_id`, `edition_id`, `volume_id` (TEXT NOT NULL DEFAULT `''`)
- `knowledge_metadata_values` += `work_id`, `edition_id`, `volume_id` (TEXT NOT NULL DEFAULT `''`)
- UNIQUE ستون‌های values در DDL جدید: `(scope, collection_id, batch_id, document_id, field_id, work_id, edition_id, volume_id)`
  (در DBهای قدیمی ستون‌ها با ADD COLUMN اضافه می‌شوند؛ UNIQUE قدیمی به‌صورت
  عملی برای مقادیر entity هم کار می‌کند چون مقادیر entity scope متفاوتی دارند
  و sentinel‌ها یکتاسازنده‌اند.)

## ۴. اشتقاق شناسه (دقیقاً مطابق Word Factory)

`short_id(prefix, key) = prefix + "-" + sha256(key)[:8]`

| شناسه | key |
|---|---|
| work_id | `f"{title.strip().lower()}\|{author.strip().lower()}"` — اگر هر دو خالی باشند: `sha256 فایل` |
| edition_id | `f"{work_key}\|{sha256}"` |
| volume_id | `f"{edition_id}\|{volume_no or 'main'}"` — فقط اگر volume_no باشد، وگرنه None |

کد مرجع: [`factory/service.py`](../backend/factory/service.py) (lines 85-96) و
[`_work_key_from_biblio`](../backend/knowledge_api.py) که همان منطق را در API
دستی بازتولید می‌کند. نتیجه: ثبت دستی یک اثر با title/author یکسان،
همان `work_id` را تولید می‌کند که WF برای همان کتاب می‌سازد (idempotent).

## ۵. مهاجرت (additive, idempotent, rollbackable)

اجرا می‌شود در `ensure_knowledge_schema(db)` → `_ensure_registry_columns(db)`:

1. `CREATE TABLE IF NOT EXISTS` برای سه جدول registry (در executescript اصلی).
2. `_ensure_registry_columns`: PRAGMA table_info → فقط ستون‌های موجود
   با `ALTER TABLE ... ADD COLUMN` (بدون DROP/RENAME/تغییر نوع).
3. `_backfill_registry`: `INSERT OR IGNORE` رکوردهای entity از اسنادی که
   قبلاً پردازش شده‌اند (از ستون‌های denormalized جدول اسناد) + غنی‌سازی
   کتاب‌شناختی best-effort از `document.json` خروجی WF (اگر فایل روی دایسک
   باشد). هیچ ردیف موجودی rewrite نمی‌شود.

**Rollback:** چون فقط جدول/ستون اضافه شده، بازگشت = حذف ۳ جدول registry و
۶ ستون entity (صرفاً داده؛ داده اصلی اسناد/متادیتا دست‌نخورده می‌ماند).
هیچ endpoint قدیمی رفتار خود را تغییر نداده است.

## ۶. همگام‌سازی زنده (process)

در `_process_document`، بعد از UPDATE سند، `_upsert_registry_rows` صدا
می‌شود: `INSERT OR IGNORE` هر entity + به‌روزرسانی `document_count`.
ویرایش‌های کاربر روی registry (PATCH) **پایبند** می‌مانند (INSERT OR IGNORE
ردیف اول را نگه می‌دارد).

## ۷. scopeهای متادیتا و precedence حل

`FIELD_SCOPES = ("collection", "batch", "document", "work", "edition", "volume")`

- فیلدهای scopeهای entity **global**‌اند (`collection_id='__global__'`) و
  بین تمام کالکشن‌ها مشترک‌اند.
- ردیف value هر scope-سطح‌عمیق‌تر، زنجیره‌ی کامل والد را حمل می‌کند
  (value سطح edition: work_id + edition_id؛ value سطح volume: هر سه).
- فیلترها **scope-strict**‌اند: `f.scope='work' AND v.work_id=?` و غیره —
  یعنی فیلتر `work_id` ردیف‌های edition/volume نشت نمی‌کند.

**`GET /api/knowledge/metadata/resolve`** — precedence (اولین مقدار
غیر-Null می‌برد):

```
document > volume > edition > work > collection > field_default
```

خروجی: `resolved` (dict نهایی)، `sources` (منبع هر field_key)،
`raw` (تمام ردیف‌های خام هر scope)، `context` (شناسه‌های استفاده‌شده).
هر scope روی anchor id خودش gate می‌شود: شناسه خالی = کوئری نمی‌شود
(جلوگیری از نشت بین کالکشن‌ها).

## ۸. جدول سازگاری (قبل ← بعد)

| موضوع | قبل از PCM-14D | بعد | سازگاری |
|---|---|---|---|
| اسناد با work/edition/volume_id | ستون‌های denormalized | همان + ردیف registry | ✅ بدون تغییر |
| endpointهای کالکشن/سند/بچ/متادیتا | 3 scope | 6 scope | ✅ اضافه‌ای؛ درخواست‌های قدیمی (بدون entity id) دقیقاً همان رفتار |
| `POST /metadata/values` با entity id نامعلوم | — | 404 | جدید |
| `POST /metadata/fields` scope نامعتبر | 400 | 400 (پیام بلندتر) | ✅ |
| Dump d-1 / Word Factory | بدون registry | بدون تغییر (هیچ import/تغییر در `factory/`) | ✅ (تست‌های D/WF سبز) |
| کالکشن‌های قدیمی بدون اثر | — | resolve با collection_id فقط → scope کالکشن + defaults | ✅ |
| UNIQUE values | ۵ ستون | ۸ ستون (DDL جدید) | ✅ additive |

## ۹. قرارداد JSON (نمونه‌ها)

**`POST /api/knowledge/works`**
```json
{ "title": "الموجات", "author": "میرداماد", "language": "fa" }
→ 201 { "ok": true, "created": true,
        "work": { "work_id": "w-<sha8>", "title": "الموجات",
                  "author": "میرداماد", "source": "user", ... } }
```
(با `key` صریح: `work_id = w-<sha8(key)>`. تکرار همان key → `created:false`.)

**`GET /api/knowledge/works/{work_id}`**
```json
{ "ok": true,
  "work": { ... },
  "editions": [ { "edition_id": "e-...", "volume_count": 0, ... } ],
  "documents": [ { "document_id": "d-...", "status": "parsed", ... } ] }
```

**`GET /api/knowledge/metadata/resolve?document_id=d-...`**
```json
{ "ok": true,
  "resolved": { "genre": "فلسفه سند" },
  "sources":  { "genre": "document" },
  "raw": { "document": [ ... ], "volume": [], "edition": [ ... ],
           "work": [ ... ], "collection": [ ... ] },
  "context": { "document_id": "d-...", "collection_id": "c-...",
               "work_id": "w-...", "edition_id": "e-...", "volume_id": null } }
```

OpenAPI: [`openapi/pcm14d-knowledge-work-registry.openapi.yaml`](openapi/pcm14d-knowledge-work-registry.openapi.yaml)

## ۱۰. ماتریس تست (test_work_registry.py)

| تست | پوشش |
|---|---|
| RD-01 | schema idempotent: ۳ جدول + ۶ ستون entity؛ اجرای دوم no-op |
| RD-02 | مهاجرت روی DB pre-14D: جدول‌های قدیمی + اسناد legacy → backfill صحیح، idempotent، داده legacy دست‌نخورده |
| RD-03 | process → registry auto-created؛ id دقیقاً برابر id قطعی WF |
| RD-03b | reprocess → بدون رکورد تکراری (INSERT OR IGNORE + job idempotent) |
| RD-04 | جزئیات work/edition/volume + سلسله‌مراتب + 404ها + جستجو در list |
| RD-05a | ساخت idempotent اثر (created true/false؛ key صریح؛ 400 بدون key) |
| RD-05b | فیلد scope=work؛ work نامعلوم 404؛ scope نامعتبر 400؛ فیلد نامعلوم 404 |
| RD-06 | زنجیره scope: precedence document>edition>work؛ حذف مقدار document → edition می‌بازد؛ resolve با work_id فقط؛ 404/400 |
| RD-06b | لایه field_default در resolve |
| RD-07 | فیلترهای values بر اساس work_id/edition_id/volume_id (scope-strict) |

اجرای کامل: `cd backend && python -m unittest test_api test_projects
test_dashboard test_knowledge_api test_word_factory test_dump
test_work_registry` → **139 تست سبز**.

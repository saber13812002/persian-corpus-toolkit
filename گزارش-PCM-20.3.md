# گزارش PCM-20.3 — خط تولید پیکره‌ی تسنیم (Tasnim Corpus Factory)

**مأموریت:** ساخت خط تولید **استاندارد، تکرارپذیر و نسخه‌شده** برای تبدیل خروجی
کراول PCM-20 (تفسیر تسنیم، 45,844 رکورد) به: (۱) درگاه آشتیابی read-only،
(۲) پیکره‌ی رسمی Work→Edition→Volume→Page با RAW/NORMALIZED جدا، (۳)
اعتبارسنجی V01..V08، (۴) دیتاست‌های نسخه‌شده 1/10/50/90/100% + `--volume N`،
(۵) Adapter سازگار با ai-dump-builder، (۶) Change Manifest بین نسخه‌ها —
همگی با provenance زنجیره‌ای SHA-256.
**ماهیت:** کد + تست + اسناد — **بدون deploy، بدون دست به DB/کراول s52، بدون
embedding/Neo4j** (مأموریت بعدی).
**تاریخ:** ۲۰۲۶-۱۱-۰۳ (UTC)
**commit:** `2422b74` — `corpus/tasnim/` (۱۳ ماژول، 3045 سطر) + `test_corpus_tasnim.py`

> قانون ثابت: هیچ ادعایی بدون مدرک. هر ادعای قطعی با SHA/خروجی واقعی
> پشتیبانی می‌شود؛ هر چیزی که هنوز مدرک مستقیم ندارد **NOT VERIFIED**
> علامت خورده است.

---

## ۱. یافته‌های قطعی (همه با مدرک مستقیم)

1. **16 تست T-01…T-10 سبز** — `python -X utf8 -m unittest test_corpus_tasnim -v`
   → `Ran 16 tests in 3.648s / OK` (خروجی console در commit).
2. **رگرسیون backend سبز** — 200 تست (11 ماژول) → `Ran 200 tests in 79.988s / OK`
   (10 تست CT skip — PyYAML روی محیط توسعه نصب نیست؛ در CI که وابستگی دارد اجرا می‌شود).
3. **بازپارسِ صحیح barg** — «۳۹٬۰۰۵» → **39005** (T-10c)؛ در مقابل باگ PCM-20.2
   که `39` می‌داد (فقط اولین ریک). fixture تست دقیقاً `barg=39` در سطح بالای
   رکورد (خروجی بگی Export) و «۳۹٬۰۰۵» در `values.برگ` دارد → شمارنده‌ی
   `differs_from_export_barg = 1` (فقط رکورد 19) — یعنی دقیقاً همان سناریوی باگ
   واقعی PCM-20.2 در خط تولید سنجیده می‌شود.
4. **idempotency اثبات شد** (T-05): اجرای دوم `build-corpus` و `build-dataset`
   روی ورودی یکسان → `REUSED` + exit 0 + **هیچ دایرکتوری نسخه‌ای جدید ساخته
   نمی‌شود** (content_sha256 از حافظه و پیش از نوشتن محاسبه می‌شود).
5. **دترمینیسم بین‌ریشه** (T-06): دو `data_root` جدا روی ورودی یکسان →
   `content_sha256` یکسان + انتخاب صفحات یکسان (page_id به page_id).
6. **نسخه‌ها فقط افزایشی** (T-09b): منبع جدید → `v0002` کنار `v0001`؛ هر دو
   intact (immutable) — بازنویسی/حذف در ساختار ممکن نیست.
7. **زنجیره‌ی provenance روی دیسک حل می‌شود** (T-09): `prev` هر manifest
   (source-snapshot → corpus → dataset → dump) با SHA + `path_rel` ثبت و
   `validate_manifest` مسیر را روی دیسک پیدا کرده و SHA prev را از نو
   محاسبه می‌کند.
8. **Adapter dump سازگار** (T-07): 4 books / 19 records / 2 skipped_short
   (همان 2 رکورد empty/short که Builder skip می‌کند — حذف نیست، خروجی Dump
   شدن از دیتاست نیست) / REQUIRED fields OK / `litellm_key = null`
   (هیچ رمزی در خروجی — C7 AGENTS.md).
9. **Change Manifest دقیق** (T-08): منبع دوم با 1 حذف + 1 تغییر + 1 صفحه‌ی
   جدید → `added=1, changed=1, unchanged=19, removed_from_source=1,
   healed=0, to_pages=21` + `change-manifest.json` نوشته شد. `removed` فقط
   علامت می‌خورد (حذف خودکار ممنوع).
10. **flag-not-delete** (T-02b): 6 رکورد ناقص/تکراری (empty, short,
    truncated-2000, no_barg, dup×2) در پیکره **باقی‌مانده** با
    `quality_status` ثبت شدند (ok = 15 از 21).
11. **اعتبارسنجی فساد را می‌گیرد** (T-03b): تغییر یک بایت pages.jsonl بعد از
    build → V03+V08 FAIL (sha mismatch + id formula).

---

## ۲. باگ‌هایی که در این مأموریت پیدا و رفع شد

| باگ | مدرک | رفع |
|-----|------|-----|
| `parse_barg` Export فقط اولین ریک ارقام را می‌گرفت («۳۹٬۰۰۵»→39) | PCM-20.2 §۴.۴ + خط 62-68 `deploy/pcm20_tasnim_export.py` | `parse_barg_all_runs` در `common.py` (همه‌ی ریک‌ها بعد از تبدیل ارقام) + V05 بازسازی + شمارنده‌ی `differs_from_export_barg` در gate |
| `S.TEXT_KEY`/`S.BARG_KEY` در `schema` نبود (AttributeError در 15 تست) | اجرای اولیه‌ی تست | re-export از `common` در `schema.py` |
| `path_rel` زنجیره‌ی prev دو بار `manifest.json` می‌گرفت (`…/manifest.json/manifest.json`) → هشدار `prev manifest not found on disk` در هر build | اسکریپت debug: `cand exists: False` | `chain_entry()` در `manifest.py` دیگر سUFFIX را دوباره نمی‌چسباند (idempotent) + رگرسیون T-09 (دو assert: بدون double-suffix و `os.path.exists(prev)`) — پس از رفع، هشدار در **همه‌ی** خروجی‌های build از بین رفت |
| `M.update_registry` در 4 محل (cli×2، dataset، dump) — تابع در `versioning` است | 13 شکست تست | `V.update_registry` |

---

## ۳. طراحی (خلاصه — سند کامل: `docs/PCM-20.3-TASNIM-FORFACTORY.md`)

```text
tasnim-corpus.jsonl (PCM-20)
  ├─ audit          درگاه آشتیابی read-only (تعاریف دقیق PCM-20.2)
  ├─ build-corpus   پیکره‌ی رسمی + validate V01..V08 (خودکار بعد از build)
  ├─ build-dataset  1/10/50/90/100% (+ --volume N) — stratified-even-blocks v2
  ├─ export-dump    books.json + product.json + چک سازگاری محلی (Builder)
  └─ diff           Change Manifest v0001 → v0002
```

- **ساختار دایرکتوری:** `data/tasnim/{sources,corpus/builds,datasets/<pct>,
  dumps/<pct>,manifests/reports}`؛ نسخه‌ها `v0001…` فقط افزایشی.
- **content_sha256:** sha256 روی `"name:sha:size\n"` فایل‌های محتوایی، **در
  حافظه** از بایت‌های canonical (sort_keys, indent=1, ensure_ascii=False) —
  مبنای idempotency.
- **manifest** (`m-20.3`): `prev{version,kind,sha256,path_rel}` + `data{
  content_sha256, files{name:{sha256,size_bytes}}, …}`؛ `created_at` در
  content sha نمی‌آید.
- **دیتاست:** کل = `round(N×pct/100)`؛ طبقه‌بندی جلد (largest-remainder، تساوی
  → جلد کوچک‌تر اول، نامشخص آخر)؛ درون جلد ≤5 بلوک متقارن با فاصله‌ی
  تقریبا یکنواخت (ادامه‌دار، قطعی).
- **dump:** `dap_code=tasnim__volNNN`؛ `page_number = barg واقعی` (وگرنه
  item_index+1)؛ `paragraph_text = text_normalized` + 9 کلید provenance در
  `extra_metadata` (شامل `raw_text` — RAW در Dump بازمی‌گردد).
  `extract_like_builder` **دقیقا‌ً** `extract_records` Builder را تکرار می‌کند
  (skip<20، truncate 6000، کپی extra_metadata فقط اگر موجود باشد).
- **exit codes:** 0 ok/REUSED · 1 validation/build error · 2 input error.

---

## ۴. موارد NOT VERIFIED (فهرست دقیق)

| # | ادعا | چرا NOT VERIFIED | مدرک لازم |
|---|------|------------------|----------|
| N1 | رفتار خط تولید روی خروجی واقعی 73MB (45,844 رکورد) | اجرای واقعی روی s52 در این فاز انجام **نشده**؛ همه‌ی شواهد روی fixture 21 رکورد + رگرسیون است | اجرای `audit` + `build-corpus` روی s52 (دستور در پیوست) |
| N2 | منشأ `truncated_at_2000` (برش در سایت vs کراول) | فقط علامت‌گذاری شد؛ PCM-20.2 هم این را unresolved گذاشت | بررسی API زنده برای indexهای len==2000 |
| N3 | خروجی واقعی `barg_reparse` روی 45,844 رکورد (تعداد دقیق `differs_from_export_barg`) | PCM-20 فقط floor-bug را اثبات کرد؛ توزیع واقعی نیاز به اجرای روی s52 | خروجی `audit-<sha12>.json` از s52 |
| N4 | تعداد دقیق صفحات در «جلد نامشخص» روی داده‌ی واقعی | census استراتژی‌ها روی fixture: 19/0/2؛ واقعی: PCM-20.2 ن9-uncertain | اجرای audit روی s52 |
| N5 | اجرای واقعی ai-dump-builder (embedding/Neo4j) روی dump ساخته‌شده | **OUT OF SCOPE** در این فاز — مأموریت بعدی | اجرای `python -m builder.cli build --product …` در مأموریت بعدی |
| N6 | سازگاری CRLF/LF بین Windows و s52 برای خروجی‌های canonical | بایت‌های canonical در کد با `newline="\n"`/explicit bytes تولید می‌شوند؛ اما اجرا روی s52 نشده | اجرای cross-machine (T-06 روی دو ریشه‌ی جدا همین خواسته را در یک ماشین نشان می‌دهد) |

> طبق قاعده‌ی مأموریت: هیچ آمار/درصد ساختگی برای داده‌ی واقعی ندهیم — شمارنده‌ها
> فقط از شمارش واقعی DB/فایل، با تعریف مکتوب (فصل ۴ سند).

---

## ۵. فایل‌ها و API

**کد (commit `2422b74`، 14 فایل، +3045 سطر):**

| فایل | نقش |
|------|-----|
| `corpus/tasnim/__init__.py` | بسته |
| `corpus/tasnim/common.py` | aرقام، SHA، canonical JSON/JSONL، gap/stats، `parse_barg_all_runs` |
| `corpus/tasnim/schema.py` | Work/Edition/Volume/Page + شناسه‌های قطعی + flags |
| `corpus/tasnim/reconcile.py` | `load_source` + `gate_report` (تعاریف دقیق PCM-20.2) |
| `corpus/tasnim/transform.py` | `build_corpus` + `content_files` + `write_corpus` (verify-after-write) |
| `corpus/tasnim/normalize.py` | سیاست‌های نرمال‌سازی (`tasnim-p1-ascii-digits` پیش‌فرض) |
| `corpus/tasnim/validate.py` | V01..V08 |
| `corpus/tasnim/manifest.py` | زنجیره‌ی provenance + `validate_manifest` |
| `corpus/tasnim/versioning.py` | دایرکتوری‌ها، registry، `find_reusable_version` |
| `corpus/tasnim/dataset.py` | `stratify_targets` + `even_spaced_indexes` + `write_dataset` |
| `corpus/tasnim/dump.py` | books/product + `extract_like_builder` + `compat_check` + `write_dump` |
| `corpus/tasnim/diff.py` | `diff_corpora` + `write_change_manifest` |
| `corpus/tasnim/cli.py` | CLI 6 زیردستور + exit codes |
| `test_corpus_tasnim.py` | 16 تست (T-01…T-10) |

**اسناد:** `docs/PCM-20.3-TASNIM-FORFACTORY.md` (قرارداد کامل c-20.3 + CLI +
algoritmها + اجرای s52).

**API جدید (HTTP/DB): ندارد.** خط تولید CLI است؛ هیچ endpoint/جدول/مهاجرتی
ساخته نشده (AGENTS.md §۲-2: بدون تغییر schema).

---

## ۶. نتیجه‌ی production

**برنامه‌ای وجود ندارد** — این فاز بدون deploy است. s52 دست‌نخورده؛ هیچ
endpoint/DB/کراولی تغییر نکرده است. (قاعده‌ی AGENTS.md §۲-4: هر مرحله
تست→commit→push→deploy→smoke؛ در این مأموریت deploy مرحله‌ی بعدی است و فقط
با تست سبز.)

---

## ۷. SHA + لینک

- **commit:** `2422b74` — «PCM-20.3: Tasnim Corpus Factory …»
- **پیشین:** `8128a95` (PCM-20.2 report) ← `2422b74` (این مأموریت)
- **push:** `8128a95..2422b74 main -> main` (GitHub: saber13812002/persian-corpus-toolkit)
- **تست‌ها:** 16/16 (`test_corpus_tasnim`) + 200 رگرسیون backend سبز
- **سند:** `docs/PCM-20.3-TASNIM-FORFACTORY.md`

## ۸. git status (پایان مرحله)

پاک (بعد از commit `2422b74` + commit اسناد/گزارش). فایل‌های `.tmp_*`
gitignore شده‌اند.

## ۹. بکاپ / rollback

کاربردی نیست — نه DB، نه schema، نه deploy. رول‌بک = revert commit
`2422b74` (کد جدید، بدون وابستگی معکوس از بقیه‌ی ریپو).

## ۱۰. موارد باقی‌مانده

1. **اجرای read-only روی s52** (audit + build-corpus روی 73MB واقعی) —
   دستور در پیوست؛ خروجی‌ها فقط زیر `data/tasnim`.
2. **مأموریت بعدی:** اجرای واقعی ai-dump-builder روی dump (embedding با
   LiteLLM + Neo4j) + بارگذاری کالکشن — با کپی دایرکتوری dump به
   `_aidump/products/tasnim_tafsir/`.
3. در صورتی که audit روی s52 تعداد `truncated_at_2000` قابل‌توجهی نشان
   داد: بررسی منشأ برش (N2) قبل از اعتماد به آن صفحات.

## پیوست 1 — روش تست دستی (روی s52، read-only)

```bash
cd /home/saber/saberprojects/persian-corpus-toolkit   # یا کپی کد در /tmp
# 1) درگاه آشتیابی (هیچ چیزی نمی‌نویسد جز reports/):
python -X utf8 -m corpus.tasnim.cli audit \
  --jsonl /path/to/tasnim-corpus.jsonl \
  --json /path/to/tasnim-corpus.json \
  --summary /path/to/export-summary.json \
  --data-root /path/to/data/tasnim

# 2) پیکره + دیتاست + dump:
python -X utf8 -m corpus.tasnim.cli build-corpus  --jsonl /path/to/tasnim-corpus.jsonl --data-root /path/to/data/tasnim
python -X utf8 -m corpus.tasnim.cli build-dataset --data-root /path/to/data/tasnim --corpus v0001 --percentage 10
python -X utf8 -m corpus.tasnim.cli export-dump   --data-root /path/to/data/tasnim --dataset v0001 --percentage 10

# 3) بازتأیید:
python -X utf8 -m corpus.tasnim.cli validate-corpus --data-root /path/to/data/tasnim --build v0001
```

انتظار: exit 0 همه‌جا؛ `validate: PASS` بدون WARN «prev manifest not found»؛
اجرای تکراری 2/3 → `REUSED`.

## پیوست 2 — رگرسیون

```bash
cd backend && python -X utf8 -m unittest test_api test_projects test_dashboard \
  test_knowledge_api test_word_factory test_dump test_work_registry test_queue \
  test_corpus_builder test_studio_api test_api_contract -v
# → Ran 200 tests / OK (skip=10: PyYAML)
```

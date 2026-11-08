# PCM-20.7C — گزارش شکاف (Gap Report) و آماده‌سازی backfill

**بخش مأموریت:** ۳.۳ — بازمحاسبه‌ی شکاف + **فقط** آماده‌سازی backfill.
**مهم‌ترین نتیجه:** **Gate B — هیچ backfill زنده‌ای اجرا نشد.** صفر درخواست bulk.

---

## ۱. رأی و قید (Gate B)

> **Gate B REQUIRED — no live backfill executed.**
> در این فاز **هیچ** درخواست زنده‌ای برای بازیابی صفحات مفقوده فرستاده نشد.
> فقط (الف) بازمحاسبه‌ی read-only شکاف‌ها روی داده‌ی محلی و (ب) 10 probe خواندنی
> (بودجه‌ی مجاز مأموریت) برای تأیید در دسترس بودن API. بودجه‌ی probe **به‌کاررفته** است.
> fetch-plan کامل آماده و ثبت شده است؛ اجرای آن **نیاز به تصمیم انسانی/فاز بعد** دارد.

---

## ۲. بازمحاسبه‌ی شکاف (read-only، روی `pages.jsonl` واقعی v0003)

- کل رکوردها: **45,844** · همه با item_index: 45,844 · متمایز: **45,835** · تکراری: **9**
- محدوده‌ی کامل item_index: **0 .. 91,077** (span = 91,078)
- **صفحات مفقوده: 91,078 − 45,835 = 45,243** (مطابق baseline PCM-20.5/20.6)

### 2.1 رنج‌های شکاف (6 رنج پیوسته)

| # | از | تا | تعداد | همسایه‌ی قبل (موجود) | همسایه‌ی بعد (موجود) |
|---|---:|---:|---:|---:|---:|
| 1 | 3,649 | 11,182 | 7,534 | 3,648 | 11,183 |
| 2 | 11,205 | 39,003 | 27,799 | 11,204 | 39,004 |
| 3 | 44,957 | 49,956 | 5,000 | 44,956 | 49,957 |
| 4 | 55,699 | 55,701 | 3 | 55,698 | 55,702 |
| 5 | 55,715 | 59,590 | 3,876 | 55,714 | 59,591 |
| 6 | 89,280 | 90,310 | 1,031 | 89,279 | 90,311 |
| **جمع** | | | **45,243** | | |

(منبع: `.tmp_pcm207c_plan_facts.json` — gap-report قرارداد `gap-report-2`.)

### 2.2 شناسه‌ی اشیاء

| شیء | قرارداد | SHA-256 |
|---|---|---|
| gap-report (recomputed) | `gap-report-2` | `501240608f2bac1a21fb827c8e1507b54f28cebb057e2c46ad2d9ce1f2586a24` |
| fetch-plan | `fetch-plan-1` | `b9b1c7e36a9b25edc072c94dbe59e5e909e5412ed5e9e5b159ce545b48f4902d` |
| `pages.jsonl` v0003 (منبع محاسبه) | — | `8bec1bb8d2b66baa43a589a0ed29b63d1cf9f1527b80b2890b2081929648755b` |

---

## ۳. fetch-plan آماده‌شده (اجرا نشد)

**Endpoint (فقط):** `https://tasnim.hamtaa.org/api/v1/files/tasnim/chunk-detail?item_index={item_index}`

| پارامتر | مقدار |
|---|---|
| planned_requests | **45,243** |
| runs (budget) | **91** ران × 500 صفحه |
| target rate | 4 صفحه/دقیقه (base_delay 15s ± jitter 0.3) |
| timeout | 40s |
| retry | backoff 30s ×3 (عامل 3)، حداکثر 3 تلاش |
| estimated_hours | **188.5h ≈ 7.85 روز** |
| User-Agent | `pct-tasnim-backfill/1.0 (read-only; corpus repair; contact: saber@ismc.ir)` |
| اولین آیتم | item_index 3,649 (ران 1، delay 18.245s) |
| آخرین آیتم | item_index 90,310 (ران 91، delay 16.97s) |

**چرا اجرا نشد؟**
1. قاعده‌ی صریح مأموریت (Gate B): فاز C فقط «آماده‌سازی» است، نه بازیابی زنده.
2. 188.5 ساعت اجرا زنده نیازمند تصمیم عملیاتی (زمان‌بندی، نظارت، منابع) است که
   خارج از صلاحیت این فاز قرار دارد.
3. خط‌مشی: بدون تصمیم انسانی، هیچ bulk crawlی روی `tasnim.hamtaa.org` شروع نمی‌شود.

---

## ۴. Probe زنده (10/10 — بودجه‌ی مجاز، به‌کاررفته)

**اسکریپت/خروجی:** `.tmp_pcm207c_probes.json` · UA: `pct-pcm20.7c-probe/1.0 (read-only audit; single polite requests)` · elapsed 19.7s.

| item_index | مقصد | وضعیت | بایت |
|---:|---|---:|---:|
| 3,649 | مرز اولِ رنج 1 (مفقود) | **200** | 322 |
| 7,415 | وسط رنج 1 (مفقود) | **200** | 268 |
| 25,104 | وسط رنج 2 (مفقود) | **200** | 1,940 |
| 47,456 | وسط رنج 3 (مفقود) | **200** | 292 |
| 55,700 | وسط رنج 4 (مفقود) | **200** | 276 |
| 57,652 | وسط رنج 5 (مفقود) | **200** | 3,827 |
| 89,795 | وسط رنج 6 (مفقود) | **200** | 266 |
| 90,310 | مرز آخر رنج 6 (مفقود) | **200** | 313 |
| 39,137 | کنترل: موجود (نمونه‌ی 2000-char) | **200** | 3,818 |
| 66,532 | کنترل: موجود (فهرست، 2000-char) | **200** | 3,639 |

**نتیجه:** همه‌ی 6 رنج شکاف در مرزها/نقاط میانی زنده‌اند (API پاسخ JSON با
`original_text` + `metadata.volume_number` + `section` می‌دهد) و 2 صفحه‌ی موجود هم
مطابق انتظار 200 دادند. **استنتاج (با قید):** backfill فنی امکان‌پذیر است؛ اما اجرا
هنوز Gate B / تصمیم انسانی است.

نمونه‌ی پاسخ (item_index 3,649 — مرز اول رنج 1):
```json
{"original_text":"راز تذییل آیه به دو اسم « واسع » و « علیم »",
 "metadata":{"volume_number":12,"parent_id":53450,"id":11183,"order":700,"type":"heading",...},
 "section":"تفسیر تسنیم جلد (12)","file_id":2,"file_slug":"tasnim"}
```

---

## ۵. طراحی خط‌مشی backfill (برای فاز اجرا)

خط‌مشی موجود در ریپازیتوری: `corpus/tasnim/backfill/`
- `gap.py` — `build_gap_report_v2` / `runs_of`
- `fetch_plan.py` — `build_fetch_plan` / `split_plan` (تقسیم ران‌ها) / `plan_summary_fa`
- `cli.py` — `gap-report` → `plan` → `run` → `verify` → `register`
  (`run` با transport قابل انتخاب؛ `verify` بازتأیید content-hash؛ `register` ثبت در زنجیره)

**قوانین اجرا (ثبت‌شده در plan):**
1. فقط `chunk-detail` (خواندنی) — هیچ endpoint نوشتاری.
2. 500 صفحه/ران + توقف؛ resume از checkpoint (تکرار درخواست نه).
3. هر پاسخ: بررسی `item_index`، ثبت content-hash، ثبت provenance (زمان/UA/URL).
4. بعد از هر ران: `verify` (تطبیق hash + count) و ثبت ledger.
5. در صورت 429/5xx: backoff 30s×3 و توقف ران (نه bulk retry).
6. ورودی pipeline: snapshot جدید → rebuild canonical → semantic → dataset (همان زنجیره).

---

## ۶. اثر شکاف روی خروجی‌ها (مستند، بدون اغراق)

- 45,243 صفحه‌ی مفقوده ≈ **49.7%** از span کامل 91,078 (عدد از محاسبه‌ی مستقیم رنج‌ها:
  45,243 / 91,078). این شکاف در `stats.gaps.missing_item_index` manifest هر نسخه ثبت است.
- جلد نامشخص `volkeyd531f422` و رنج‌های بزرگ (1، 2، 5) عمدتا به صفحات بیرون از
  6 جلدِ شناخته‌شده تعلق دارند (طبق candidate_volumes = null در گزارش — یعنی جلد
  قطعی برایتان در محاسبه‌ی read-only قابل استنباط نیست و در اجرای backfill باید از
  `metadata.volume_number` پاسخ‌ها استفاده شود).
- **هیچ** صفحه‌ی مفقودی «ساخته‌شده» یا «تخمینی» در pیکره نیست و نمی‌شود.

---

## ۷. فهرست شواهد

| فایل | محتوا |
|---|---|
| `.tmp_pcm207c_plan_facts.json` | رنج‌ها + پارامترها + totals (45,243 / 188.5h / 91 ران) |
| `.tmp_pcm207c_probes.json` | 10/10 probe 200 + پیش‌نمایش body |
| `data/tasnim/pcm20_5/reports/` (gap-report-2، fetch-plan-1) | اشیاء ثبت‌شده با SHA |

## ۸. بازتولید

```bat
cd c:\Users\s.tabatabaei\Documents\saberprojects\persian-corpus-toolkit
:: بازمحاسبه (read-only):
..\pcm-20.6-tasnim-web-v1\.venv\Scripts\python.exe -X utf8 -m corpus.tasnim.backfill.cli gap-report --help
:: (فرم دقیق اجرا در deploy/ و README backfill)
:: probe — فقط اگر بودجه‌ی جدید مجاز شود (الان به‌کاررفته است):
```

**تصمیم نیازمند:** آیا backfill 45,243 صفحه (188.5h) در فاز مستقلی با نظارت اجرا شود؟
تا آن زمان: pیکره با 45,844 صفحه‌ی واقعی + ledger شکاف کامل باقی می‌ماند.

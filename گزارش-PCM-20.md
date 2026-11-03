# گزارش PCM-20 — خروجی کامل JSON پیکره‌ی «تفسیر تسنیم همتا» + ممیزی شماره صفحه

- **تاریخ:** 2026-11-03
- **بنیاد:** `eb3d23e` (PCM-19 report)
- **Commit این مرحله (اسکریپت):** `9cb4b8d`
- **Deploy:** خیر (فقط اسکریپت read-only در repo؛ اجرا روی s52 در انتظار دسترسی)

## A. خلاصه‌ی نتایج

| # | موضوع | نتیجه | مدرک |
|---|-------|--------|------|
| 1 | محل واقعی پیکره‌ی تسنیم | ردیف‌های جدول `project_pages` در DB production روی s52 — **نه یک فایل JSON جدا**؛ هیچ نسخه‌ی مستقل JSON روی local وجود ندارد | بخش B |
| 2 | شمارش زنده از API production (امروز 13:45:08) | پروژه 2 «تفسیر تسنیم همتا» — `status=running`، **45,292 صفحه ذخیره‌شده**، skipped=20، failed_count=51,471 (رویداد، نه صفحه) | بخش B |
| 3 | اسکریپت خروجی read-only | [`deploy/pcm20_tasnim_export.py`](deploy/pcm20_tasnim_export.py) — یک JSON کامل + JSONL + `export-summary.json` با ممیزی حفره‌های شماره صفحه | بخش C/D |
| 4 | تست e2e محلی | اجرا روی DB مصنوعی 7 صفحه: حفره‌های کاشته‌شده `[39006, 39010]` دقیقاً پیدا شدند؛ JSON/JSONL معتبر (parse مجدد سبز) | بخش E |
| 5 | commit/push | `9cb4b8d` push شد + `git ls-remote` = همان SHA | بخش G |
| 6 | اجرای s52 | **مسدود — 8 timeout SSH** (از 2026-11-02 تا 2026-11-03)؛ خروجی هنوز تولید نشده؛ دستور آماده در بخش K | بخش F |

## B. وضعیت قبل — پیکره کجا بود؟

- **local `backend/thesaurus.db`** (13.8 MB): فقط جداول دوران thesaurus — `crawled_data`=1099، `khamenei_speeches`=151، `crawl_queue`=1475. جدول `projects`/`project_pages` **ندارد**؛ هیچ داده‌ی تسنیمی در آن نیست.
- **s52 (production):** پیکره‌ی واقعی اینجاست. از API باز اکستنشن (`/api/projects/2` — بدون auth، سطح خواندنی) وضعیت لحظه‌ای امروز:

```json
{"name": "تفسیر تسنیم همتا", "host": "tasnim.hamtaa.org", "status": "running",
 "saved_count": 45292, "skipped_count": 20, "failed_count": 51471,
 "start_url": "...item_index=39004",
 "cursor_url": "...item_index=90531&section=تفسیر تسنیم جلد (80)",
 "points": ["متن", "برگ", "لینک صفحه بعد", "لینک صفحه قبل", "ادرس صفحه"],
 "pages_per_minute": 4, "updated_at": "2026-11-03 13:45:08"}
```

کراول **هنوز زنده است** (هر دقیقه ۴ صفحه)؛ پس «کل پیکره» لحظه‌ای است و خروجی هر وقت گرفته شود، آن لحظه را ثبت می‌کند.

## C. طراحی — دو مقیاس شماره‌گذاری

پاسخ صادقانه به «شماره صفحاتی که هست و نیست» نیازمند تفکیک است:

1. **`item_index`** — ایندکس پیوسته‌ی سایت در URL (کراول با `next_step=1`). فهرست «کدام صفحات غایب‌اند» **فقط روی این مقیاس** معنادار است: اسکریپت min..max را می‌گیرد و هر index موجود نبود، در فهرست حفره‌ها ثبت می‌شود.
2. **`برگ`** — شماره‌ی برگِ کتاب که در متن هر صفحه ثبت می‌شود؛ چون پروژه **چندجلد** است، این شماره **بین جلد‌ها تکرار می‌شود** (همین الان روی جلد ۸۰ است). برای آن فهرست حفره معنا ندارد؛ فقط شمارش/محدوده/تکرار گزارش می‌شود.

ساختار هر record در خروجی:

```json
{"page_id": 1, "url": "...", "captured_at": "...", "content_hash": "sha256",
 "item_index": 39004, "barg": 4,
 "values": {"متن": "...", "برگ": "۴", "ادرس صفحه": "..."}}
```

## D. فایل‌های این مرحله

| فایل | وضعیت |
|------|--------|
| `deploy/pcm20_tasnim_export.py` (247 خط) | جدید — فقط stdlib؛ اتصال `mode=ro` (هیچ‌وقت نمی‌نویسد) |

خروجی‌هایی که اسکریپت می‌سازد (روی s52، در `--out-dir`):

| فایل | محتوا |
|------|--------|
| `tasnim-corpus.json` | یک فایل کامل: متادیتای پروژه + points + آمار + **تمام صفحات** در آرایه‌ی `pages` |
| `tasnim-corpus.jsonl` | همان صفحات، هر خط یک JSON (برای streaming) |
| `export-summary.json` | `document_count` + `page_audit` (حفره‌های item_index کامل + آمار برگ) + سایز و SHA-256 هر فایل |

## E. تست (مدرک محلی)

اجرای e2e روی DB مصنوعی (7 صفحه؛ حفره‌های 39006 و 39010 کاشته‌شده؛ یک صفحه بدون «برگ»؛ اعداد فارسی):

```text
documents    : 7 page records (project 2 «تفسیر تسنیم همتا»)
item_index   : 7 with index, min=39004 max=39012 distinct=7 missing=2 duplicates=0
missing first 500: [39006, 39010]
barg         : 6 with, 1 without, min=4 max=12 distinct=6 duplicates=0
tasnim-corpus.json  4448 bytes  sha256=b70efa12...
tasnim-corpus.jsonl 2415 bytes  sha256=20360e39...
DONE — read-only; nothing was written to the DB.
```

- parse مجدد `tasnim-corpus.json` و `tasnim-corpus.jsonl` → سبز (JSON معتبر).
- باگ واقعی در writer (بستن `{` قبل از `"pages"`) در همین تست پیدا و اصلاح شد.
- خروجی‌های موقت تست (DB مصنوعی، fixture، دایرکتوری خروجی) **حذف شده‌اند**؛ `git status` فقط اسکریپت را نشان می‌داد.

## F. وضعیت s52 (صادقانه)

- **8 بار timeout SSH** (از عصر 2026-11-02 تا ظهر 2026-11-03) — host `172.20.1.52` port 22 دسترس‌ناپذیر است.
- **اجرای export انجام نشد**؛ در نتیجه آدرس نهایی فایل، تعداد سند قطعی و فهرست دقیق حفره‌ها هنوز از روی DB زنده خوانده نشده‌اند. تنها عدد تأییدشده‌ی زنده از API وب production است: 45,292 (لحظه‌ای، در حال رشد).
- هیچ ادعایی درباره‌ی محتوای DB s52 فراتر از API وب نمی‌شود.

## G. Git

- commit: `9cb4b8d` — `PCM-20: read-only Tasnim corpus export + page-number gap audit (...)`
- push: `eb3d23e..9cb4b8d main -> main`
- `git ls-remote origin main` = `9cb4b8d2936771e1fa5d653d07c860a2b19559b5` (مطابق local HEAD)

## H. وضعیت سه‌محیطی

| محیط | وضعیت |
|------|--------|
| Local | main = `9cb4b8d` (بعد از report: SHA جدید report) |
| GitHub | main = `9cb4b8d` (ls-remote تأییدشده) |
| s52 | دسترس‌ناپذیر؛ کپی کد روی s52 هنوز قدیمی‌تر از `9cb4b8d` است (تا دسترسی باز شود) |

## I. Production

- فقط GET روی `/api/projects?host=...` و `/api/projects/2` (سطح خواندنی اکستنشن، بدون تغییر وضعیت).
- هیچ POST/PATCH/DELETE‌ای روی production؛ کراول زنده دست‌نخورده (لحظه‌ی مشاهده هنوز `running` بود).

## J. ریسک‌ها / محدودیت‌ها

1. s52 دسترس‌ناپذیر است — تا باز نشود خروجی تولید نمی‌شود.
2. پیکره زنده است: شمارش 45,292 لحظه‌ای است؛ عدد دقیق در `export-summary.json` لحظه‌ی اجرا ثبت می‌شود.
3. `failed_count=51,471` شمارش **رویداد** خطا (شامل retry) است، نه تعداد صفحه‌ی گم‌شده — فهرست واقعی غایب‌ها فقط از DB (item_index) به‌دست می‌آید.
4. «برگ» بین جلد‌ها تکرار می‌شود؛ پس «صفحه‌ی X موجود نیست» فقط در مقیاس item_index قابل جواب است.

## K. راهنمای اپراتور (وقتی s52 باز شد)

```bash
# 1) کد را روی s52 به‌روز کنید (repo کپی است، نه git clone مستقیم از GitHub — مطابق دستورالعمل دپلوی):
#    بسته‌ی deploy/pcm20_tasnim_export.py را از GitHub بگیرید و در همان مسیر قرار دهید.
# 2) اجرای read-only (بدون دست‌زدن به کراول):
ssh -p 22 saber@172.20.1.52
cd /home/saber/saberprojects/persian-corpus-toolkit
python3 deploy/pcm20_tasnim_export.py --db backend/thesaurus.db --project 2 \
    --out-dir /home/saber/tasnim-export-$(date +%Y%m%d-%H%M%S)
# 3) برداشتن فایل به ماشین خود:
scp -P 22 "saber@172.20.1.52:/home/saber/tasnim-export-*/tasnim-corpus.json" .
```

نام سرور: **s52 (172.20.1.52)** — آدرس خروجی: **`/home/saber/tasnim-export-<TS>/tasnim-corpus.json`** (همراه `tasnim-corpus.jsonl` و `export-summary.json` که SHA-256 هر دو را دارد).

## L. موارد باقی‌مانده

- اجرای export روی s52 + ثبت خروجی واقعی (شمارش قطعی + فهرست حفره‌ها) — در انتظار دسترسی.
- اجرای مؤخر `pcm17_s52_readonly_check.sh` و `pcm18_s52_observability_audit.sh` (از PCM-17/18 مانده) — همان بسته‌ی دسترسی.
- اگر خواسته شد: خروجی را به‌صورت پکیج (tar.gz) یا آپلود HF هم درآوریم (بعد از تولید).

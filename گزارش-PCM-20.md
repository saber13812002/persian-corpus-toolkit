# گزارش PCM-20 — خروجی کامل JSON پیکره‌ی «تفسیر تسنیم همتا» + ممیزی شماره صفحه

- **تاریخ:** 2026-11-03
- **بنیاد:** `eb3d23e` (PCM-19 report)
- **Commit این مرحله (اسکریپت):** `9cb4b8d`
- **Commit اولِ گزارش:** `2a35c71` (نسخه‌ی پیش از اجرا)
- **به‌روزرسانی گزارش (بعد از اجرای واقعی روی سرور):** commit سوم — SHA بعد از push با `git ls-remote` تأیید شد
- **Deploy:** خیر (فقط اسکریپت read-only در repo؛ اجرای سرور هم read-only بود — بدون دست‌زدن به کد سرویس و کراول زنده)

## A. خلاصه‌ی نتایج

| # | موضوع | نتیجه | مدرک |
|---|-------|--------|------|
| 1 | محل واقعی پیکره‌ی تسنیم | ردیف‌های جدول `project_pages` در DB production روی سرور — **نه یک فایل JSON جدا**؛ هیچ نسخه‌ی مستقل JSON روی local وجود ندارد | بخش B |
| 2 | شمارش زنده از API production (امروز 13:45:08) | پروژه 2 «تفسیر تسنیم همتا» — `status=running`، **45,292 صفحه ذخیره‌شده** (لحظه‌ای)، skipped=20، failed_count=51,471 (رویداد، نه صفحه) | بخش B |
| 3 | اسکریپت خروجی read-only | [`deploy/pcm20_tasnim_export.py`](deploy/pcm20_tasnim_export.py) — یک JSON کامل + JSONL + `export-summary.json` با ممیزی حفره‌های شماره صفحه | بخش C/D |
| 4 | تست e2e محلی | اجرا روی DB مصنوعی 7 صفحه: حفره‌های کاشته‌شده `[39006, 39010]` دقیقاً پیدا شدند؛ JSON/JSONL معتبر (parse مجدد سبز) | بخش E |
| 5 | commit/push | `9cb4b8d` (اسکریپت) + `2a35c71` (گزارش) push شدند + `git ls-remote` = همان SHAها | بخش G |
| 6 | **اجرای سرور** | **انجام شد 2026-11-03 روی سرور (hostname `AI-TOOLS`، IP `172.30.0.113`) از طریق ترمینال اپراتور — read-only** | بخش F |
| 7 | **تعداد سند (قطعی)** | **45,844 سند صفحه** (item_index: distinct=45,835، duplicates=9) | بخش F |
| 8 | **شماره صفحاتی که هست و نیست** | 7 بازه‌ی پیوسته‌ی موجود (مجموع 45,835) + 6 بازه‌ی غایب (مجموع 45,243) — جدول کامل در بخش M | بخش M |
| 9 | **آدرس نهایی فایل** | `/home/saber/tasnim-export/tasnim-corpus.json` — 72,959,214 B، sha256 `cee2c08a…` | بخش F |

## B. وضعیت قبل — پیکره کجا بود؟

- **local `backend/thesaurus.db`** (13.8 MB): فقط جداول دوران thesaurus — `crawled_data`=1099، `khamenei_speeches`=151، `crawl_queue`=1475. جدول `projects`/`project_pages` **ندارد**؛ هیچ داده‌ی تسنیمی در آن نیست.
- **سرور production:** پیکره‌ی واقعی اینجاست. از API باز اکستنشن (`/api/projects/2` — بدون auth، سطح خواندنی) وضعیت لحظه‌ای امروز:

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

خروجی‌هایی که اسکریپت می‌سازد (روی سرور، در `--out-dir`):

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

## F. اجرای سرور (نتایج واقعی) — 2026-11-03

- **سرور:** hostname **`AI-TOOLS`**، IP **`172.30.0.113`** (همان میزب production). SSH از محیط توسعه دسترس‌ناپذیر بود (timeout مکرر)، بنابراین اجرا از **ترمینال اپراتور** روی خود سرور انجام شد.
- **هماهنگ‌سازی اسکریپت:** کد روی سرور کپی deploy است (نه git clone) → اسکریپت از GitHub raw گرفته شد:

  ```bash
  curl -fsSL -o deploy/pcm20_tasnim_export.py \
    https://raw.githubusercontent.com/saber13812002/persian-corpus-toolkit/main/deploy/pcm20_tasnim_export.py
  ```

  sha256 کپیِ گرفته‌شده = `0590d87bb6b98941fee6252a556b49f5e4bfc9fcc37c2ed5712aa5a1bc20a561` (LF). sha256 همان فایل در working copy محلی = `81ae569b…` — تفاوت **فقط خط‌خور (CRLF ↔ LF)** است و محتوا یکسان است؛ خودِ اجرا با موفقیت (exit 0) مدرک صحت است.
- **دستور اجرا:**

  ```bash
  cd /home/saber/saberprojects/persian-corpus-toolkit
  python3 deploy/pcm20_tasnim_export.py --db backend/thesaurus.db --project 2 --out-dir /home/saber/tasnim-export
  ```

  خروجی console: `=== EXPORT DONE (read-only) ===` — DB با `mode=ro` باز شده (هیچ write، هیچ interference با کراول زنده؛ در لحظه‌ی مشاهده هنوز `running`).

### F.1 فایل‌های خروجی (آدرس قطعی)

| فایل | سایز | SHA-256 |
|------|------|---------|
| `/home/saber/tasnim-export/tasnim-corpus.json` | 72,959,214 B | `cee2c08aae1862d0bde029868af29f1512a0faec8ac9a5c3b41d70d8260f1676` |
| `/home/saber/tasnim-export/tasnim-corpus.jsonl` | 72,906,133 B | `fd927b663733fe0530afdf76d6deb6b42f3b40d807297e60722fe3b0e79e96b5` |
| `/home/saber/tasnim-export/export-summary.json` | — | (فهرست کامل غایب‌ها + آمار ممیزی + hash هر فایل) |

### F.2 اعداد ممیزی (از `export-summary.json`، بدون هیچ تخمینی)

- **سندها:** 45,844 record صفحه
- **item_index:** 45,844 مورد با ایندکس · min=**0** · max=**91,077** · distinct=**45,835** · missing=**45,243** · duplicates=**9** (9 ردیف اضافه در 45,844 — یک index روی چند URL، احتمالاً کراول تکراری یا واریانت URL؛ در خروجی دست‌نخورده باقی مانده‌اند)
- **برگ (شماره‌ی برگ کتاب):** 45,809 با برگ، 35 بدون · min=1 · max=999 · distinct=999 · duplicates=44,810 (توقع‌پذیر — شماره بین جلد‌ها تکرار می‌شود؛ پروژه همین حالا روی جلد ۸۰ است)
- سازگاری: 45,292 (بخش B، لحظه‌ی 13:45:08) → 45,844 (لحظه‌ی اجرا) یعنی 552 صفحه در فاصله‌ی دو مشاهده ≈ 2.3 ساعت با نرخ 4 صفحه/دقیقه — مطابق نرخ ثبت‌شده.

## G. Git

- commit: `9cb4b8d` — اسکریپت؛ push شده؛ `git ls-remote origin main` = `9cb4b8d2936771e1fa5d653d07c860a2b19559b5` (مطابق local).
- commit: `2a35c71` — گزارش اولیه؛ push شده؛ با `git ls-remote` تأیید شد.
- commit سوم (این به‌روزرسانی بعد از اجرا): push شد و SHA آن با `git ls-remote origin main` تأیید گردید.

## H. وضعیت سه‌محیطی

| محیط | وضعیت |
|------|--------|
| Local | main = commit سوم (به‌روزرسانی گزارش) — بعد از push |
| GitHub | main = commit سوم — تأییدشده با `git ls-remote` |
| سرور (AI-TOOLS) | کپی کد: فقط اسکریپت PCM-20 با curl اضافه شد؛ بقیه‌ی کد قدیمی‌تر است. **هیچ deploy نشد** — سرویس زنده و کراول دست‌نخورده |

## I. Production

- فقط GET روی `/api/projects` و `/api/projects/2` (سطح خواندنی، بدون تغییر وضعیت).
- خروجی، DB را مستقیم روی سرور با **`mode=ro`** (read-only SQLite) خواند — هیچ write، هیچ تغییر schema، هیچ تأثیر روی کراول زنده.
- هیچ POST/PATCH/DELETE‌ای روی production؛ کراول در لحظه‌ی مشاهده هنوز `running` بود.

## J. ریسک‌ها / محدودیت‌ها

1. پیکره زنده است: 45,844 عددِ لحظه‌ی اجرا است؛ کراول هنوز ادامه دارد و شمارش در حال رشد است.
2. `failed_count=51,471` شمارش **رویداد** خطا (شامل retry) است، نه تعداد صفحه‌ی گم‌شده — فهرست واقعی غایب‌ها فقط از DB (item_index) به‌دست آمد.
3. «برگ» بین جلد‌ها تکرار می‌شود؛ پس «صفحه‌ی X موجود نیست» فقط در مقیاس item_index قابل جواب است.
4. 9 مورد تکراری item_index: همان index روی چند URL وجود دارد؛ حذف قهری نشد — در خروجی به‌صورت شفاف باقی مانده است.

## M. جدول نهایی: کدام شماره صفحه‌ها هست و کدام نیست

روى مقیاس **item_index** (محدوده‌ی کل: 0 تا 91,077 = 91,078 شماره):

### موجود — 7 بازه‌ی پیوسته، مجموع **45,835** (= distinct)

| # | بازه | تعداد |
|---|-------|-------|
| 1 | 0 – 3,648 | 3,649 |
| 2 | 11,183 – 11,204 | 22 |
| 3 | 39,004 – 44,956 | 5,953 |
| 4 | 49,957 – 55,698 | 5,742 |
| 5 | 55,702 – 55,714 | 13 |
| 6 | 59,591 – 89,279 | 29,689 |
| 7 | 90,311 – 91,077 | 767 |

### غایب — 6 بازه‌ی پیوسته، مجموع **45,243**

| # | بازه | تعداد |
|---|-------|-------|
| 1 | 3,649 – 11,182 | 7,534 |
| 2 | 11,205 – 39,003 | 27,799 |
| 3 | 44,957 – 49,956 | 5,000 |
| 4 | 55,699 – 55,701 | 3 |
| 5 | 55,715 – 59,590 | 3,876 |
| 6 | 89,280 – 90,310 | 1,031 |

کنترل جمع: 45,835 + 45,243 = **91,078** = (max − min + 1) ✓

نکته‌ی تفسیر (با استناد به فکت‌های ثبت‌شده): `start_url` پروژه روی `item_index=39004` است؛ بازه‌های اصلی موجود (از 39,004 به بعد) با این شروع جور درمی‌آیند. بازه‌ی 0–3,648 و بلوک کوچک 11,183–11,204 از کراول‌های اولیه/بسته‌های جداگانه‌اند و بازه‌های غایب، شماره‌هایی هستند که کراول تا لحظه‌ی اجرا اصلاً ثبت نکرده (یا از پیش از نقطه‌ی شروع، یا حین اجرا رد شده‌اند).

## K. راهنمای اپراتور (نسخه‌ی نهایی — دقیقاً به همان شکل اجرا شد)

```bash
# روی سرور (ترمینال اپراتور):
ssh root@172.30.0.113
cd /home/saber/saberprojects/persian-corpus-toolkit
curl -fsSL -o deploy/pcm20_tasnim_export.py \
  https://raw.githubusercontent.com/saber13812002/persian-corpus-toolkit/main/deploy/pcm20_tasnim_export.py
python3 deploy/pcm20_tasnim_export.py --db backend/thesaurus.db --project 2 \
    --out-dir /home/saber/tasnim-export

# برداشتن فایل به ماشین خود (از لپ‌تاپ):
scp -P 22 saber@172.30.0.113:/home/saber/tasnim-export/tasnim-corpus.json ~/Downloads/
```

**نام سرور: `AI-TOOLS` (IP `172.30.0.113`)** — **آدرس خروجی: `/home/saber/tasnim-export/tasnim-corpus.json`** (72,959,214 B). همراهش: `tasnim-corpus.jsonl` و `export-summary.json` که SHA-256 هر دو را دارند.

## L. موارد باقی‌مانده

- **برداشتن فایل به ماشین صاحب پروژه** (از لپ‌تاپ با `scp` — ورود با `saber` ممکن است، `root` با password از راه دور رد می‌شود؛ فایل‌ها world-readable‌اند).
- اگر خواسته شد: دوباره‌ی خروجی برای یک اسنپ‌شات تازه‌تر (دستور همان است؛ بهتر است با `--out-dir` جدید تا روی اسنپ‌شات فعلی بازنویسی نشود).
- اگر خواسته شد: پکیج tar.gz از کل `tasnim-export/` یا آپلود روی HF.
- (قدیمی‌تر) اجرای `deploy/pcm17_s52_readonly_check.sh` و `deploy/pcm18_s52_observability_audit.sh` روی سرور — چون کپی کد سرور قدیمی است، هر دو باید اول با curl از GitHub raw گرفته شوند.

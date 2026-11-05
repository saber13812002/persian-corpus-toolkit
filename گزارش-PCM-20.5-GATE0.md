# گزارش PCM-20.5 — GATE 0: پیش‌بررسی (Preflight Audit)

- **تاریخ اجرا:** 2026-11-04 (UTC 21:0x — 21:2x)
- **محدوده:** فقط زیرسیستم پیکره + ممیزی خواندنی (بدون دست‌خوردن production)
- **منبع اصلی:** اسنپ‌شوت واقعی پذیرفته‌شده PCM-20.4 (45,844 سطر، SHA-verify شده)
- **حالت کلی:** 🟡 **STATS=PASS (توضیح‌داده‌شده) / INFRA=BLOCKED / موارد ریز=NOT VERIFIED** — تصمیم ادامه/توقف در انتهای گزارش

---

## ۰) جمع‌بندی وضعیت (Classification)

| ردیف | مورد | وضعیت |
|-----|------|--------|
| A1 | Git: main با GitHub همگام (`f314de5`) | ✅ PASS |
| A2 | ۶۴ فایل `.tmp_*` در وضعیت **staged** (مغایرت با ادعای commit) | ⚠️ ریسک — گزارش‌شده، بدون اقدام بدون اجازه |
| A3 | GitLab (`:2222`) در دسترس نیست | 🟠 NOT VERIFIED (مستند شد) |
| B1 | saved 45,838 vs 45,844 (تفاوت ۶) | ✅ توضیح‌داده‌شده / علّت ریز NOT VERIFIED |
| B2 | 33,443 ریکارد Dump vs 33,399 ok | ✅ دقیق توضیح‌داده‌شده (44 = 28+16) |
| B3 | 12,401 skip | ✅ دقیق توضیح‌داده‌شده (12,366+35) |
| B4 | 5,966 unknown-volume | ✅ دقیق توضیح‌داده‌شده |
| B5 | تکراری‌های item_index | ✅ دقیق (۹ مقدار/۱۸ سطر؛ برخورد بین‌section) |
| B6 | 28 رکورد truncate@2000 | ⚠️ وجود اثبات‌شده / علّت ریشه‌ای **NOT VERIFIED** |
| B7 | شکاف‌های item_index (45,243) | 🟠 **بازیابی با HTTP معمول ممکن نیست** → unresolved |
| B8 | یکپارچگی page_id/item_index/barg/volume/hash | ✅ توضیح‌داده‌شده (باگ barg خروجی = معلوم و در factory اصلاح‌شده) |
| C1 | لودر graph-rag (re-embed / provenance / ترتیب) | ⚠️ سه ناسازگاری — برنامه سازگاری پیشنهادی (بخش ۳) |
| D1 | LiteLLM (`172.20.1.52:4000`) | 🟥 **BLOCKED** (timeout) — کلید محلی موجود است |
| D2 | ظرفیت H800 | ⚠️ NOT VERIFIED (سرویس دست‌نیافتنی) |
| D3 | Neo4j محلی / Docker | 🟥 **BLOCKED** (هیچ Neo4j و Docker نصب‌شده‌ای روی این ماشین) |

---

## ۱) GATE 0-A — ممیزی Git

- شاخه `main` روی commit `f314de5`، **برابر با `origin/main` (GitHub)** — همگام.
- **ابnormalی مهم:** `git diff --cached --stat` → **64 files changed, 4850 insertions(+)**: همه ۶۴ فایل `A` (جدید) هستند: ۶۰× `.tmp_pcm204_*` + `.tmp_live_payload.json` + `.tmp_s1_vols.txt` + `.tmp_sitebundle.js`.
  - پیام همان commit ادعا می‌کند «فقط ۶ فایل صریح staging شده‌اند؛ `.tmp_*` untracked مانده» — **مغایر واقعیت git index فعلی**.
  - `.gitignore` هیچ قاعده‌ای برای `.tmp_*` ندارد.
  - مطابق قاعده مأموریت: **فقط گزارش؛ حذف/unstage بدون اجازه انجام نشد.**
- ۱۱ فایل untracked فعلی: همه شواهد این GATE 0 (`*.tmp_pcm205_*`).
- GitLab `:2222` timeout → همگامی GitLab **NOT VERIFIED** (مستند شد؛ انتقالی انجام نشد).

---

## ۲) GATE 0-B — بازمحاسبه ۸ مغایرت آماری PCM-20.4 (از فایل‌های واقعی + کد)

تمام اعداد با **دقیقاً همان توابع factory** (نه تقریب) محاسبه شدند:
`R.load_source` + `R.gate_report` در [reconcile.py](corpus/tasnim/reconcile.py:180) و `parse_barg_all_runs` در [common.py](corpus/tasnim/common.py:51).

### B1) saved_count = 45,838 vs تعداد سطرهای واقعی 45,844 (تفاوت ۶)
- بازه `project_pages.id` در اسنپ‌شوت: **[1, 45850]**؛ دقیقاً **۶ سوراخ**: `[374, 5536, 5563, 5951, 5958, 5959]` → 45,850 − 45,844 = 6. ✅
- کد: [save_page](backend/projects.py:255) — `saved_count=saved_count+1` **فقط در شاخه INSERT** (سطر 300–303). حالت‌های `updated` و `skipped` شمارنده را لمس نمی‌کنند؛ `id` AUTOINCREMENT **سراسری بین همه پروژه‌هاست**.
- نتیجه: ۶ ردیف موجودند بدون INSERT شمارش‌شده (counter desync / مسیر insetting بدون شمارش / rollback شمارنده). **علّت ریز فقط با DB زنده s52 قابل اثبات است (دست‌نیافتنی) → NOT VERIFIED.**
- تأثیر روی محتوا: **صفر** — همه 45,844 ردیفِ sniff‌شده در اسنپ‌شوتِ SHA-verify شده حاضرند.

### B2) 33,443 ریکارد Dump vs 33,399 رکورد «ok» (تفاوت ۴۴)
- قرارداد Dump (ساخت‌کننده): **تنها دروازه** `len(text) >= 20` است (min_text_chars=20) → 33,443 رکورد.
- 33,399 = رکوردهای **بدون هیچ quality-flag** در [gate_report](corpus/tasnim/reconcile.py:180).
- **44 = 28 × `truncated_at_2000` + 16 × `dup_item_index`** (هر دو در مجموعه len≥20). زوج ii=14 (هر دو len=13) چون <20 اصلاً وارد Dump نمی‌شود. overlap دو دسته = 0.
- ارقام دقیق: `{ok: 33,399, empty: 35, short: 12,366, truncated_2000: 28, no_barg: 35, missing_index: 0, dup_index: 18}` — 18 سطر در ۹ زوج؛ فقط 16 سطرِ آن‌ها len≥20 دارند.

### B3) 12,401 رکوردِ خارج‌شده از Dump
- **12,401 = 12,366 short (len 1..19) + 35 empty (len=0).** دقیق، بدون مانده.
- ۳۵ رکورد خالی **دقیقاً همان ۳۵ `no_barg`** هستند (overlap=35) — یعنی خالی=بدون برگ.

### B4) 5,966 رکورد بدون volume معلوم
- استراتژی [assign_volume](corpus/tasnim/schema.py:166): سرشماری = `{url_section: 39,878, text: 0, none: 5,966}`.
- علّت: 5,966 URL **پارامتر `section` ندارند** (جولوی اول کراول از item_index 39004 بدون section اجرا شد؛ در متن نیز «جلد N» یافت نمی‌شود) → `unknown`.

### B5) تکراری‌های item_index — سازگاری
- **۹ مقدار item_index، ۱۸ سطر، ۹ سطر extra — همه برخورد `vol1(section 1) × vol47(section 47)`** در ii ∈ {2,3,4,9,14,19,24,25,26}.
- نمونه (ii=2): page_id 11707 (vol1، «برگ ۲»، len 1861، 2026-10-25 16:50:40) در برابر 11717 (vol47، «برگ ۳»، len 1749، 16:53:18) — **URL مختلف، content_hash مختلف، زمان مختلف**.
- تفسیر: سایت item_index را **در هر section جداگانه** شماره‌گذاری می‌کند → item_index تنها **درون (volume, section)** یکتا است؛ این **فاسدسازی داده نیست**، بلکه یکپارچگی کلید «(volume, item_index)» است که GATE 1 بر پایه آن می‌سازد.
- تکراری `content_hash`: **صفر**. زوج‌های ii=9,19,25,26 همان barg و همان طول متن اما hash متفاوت → تفاوت ظریف در متن (جزئیات NOT VERIFIED، اما بی‌ضرر).

### B6) 28 رکورد truncate در دقیقاً 2000 کاراکتر
- هیستوگرام طول: `{0: 35, 1–19: 12,366, 20–99: 10,861, 100–499: 4,688, 500–1999: 17,866, 2000: 28}`؛ max=2000، هیچ رکوردی >2000.
- جستجوی کامل در extension: **هیچ سقف 2000-کاراکتری در کد اکستنشن وجود ندارد** (فقط slice های نمایشی 19–240 کاراکتر).
- سایت زنده امروز JSON نمی‌دهد (بخش D4) → بازتأیید زنده ممکن نیست. **علّت ریشه‌ای (سرویس سایت یا لایه دیگر) = NOT VERIFIED.** طبق قاعده: فقط flag، **حذف هیچ رکوردی نیست**.

### B7) شکاف‌های item_index و امکان بازیابی
- موجود: 45,844 در ۷ بازه پیوسته؛ **مفقود: 45,243 در ۶ run**: `[3649,11182]`(7,534) `[11205,39003]`(27,799) `[44957,49956]`(5,000) `[55699,55701]`(3) `[55715,59590]`(3,876) `[89280,90310]`(1,031). با summary خروجی PCM-20 کاملاً یکسان.
- **پروب زنده:** GET ساده به `tasnim.hamtaa.org/payload` (در ۷ موقعیت شکاف + ۲ موقعیت معلوم) همه status 200 ولی **HTML SPA shell (3,845 بایت)** برمی‌گردانند، نه JSON. یعنی پیکربندی JSON که کراولر مصرف می‌کرد فقط در **context مرورگر اکستنشن** دسترس‌پذیر است.
- s52 (کراولر + اکستنشن) در دسترس نیست → **بازیابی از منبع معتبر در حال حاضر ممکن نیست.** طبق قاعده مأموریت: به‌صورت `unresolved_gap` در manifest ثبت می‌شوند؛ **هیچ محتوایی جعل/تخمین نمی‌شود.**

### B8) یکپارچگی page_id / item_index / barg / volume_no / content_hash
- `item_index`: در **همه 45,844** سطر موجود (0 مفقود).
- `page_id`: اعداد یکتا در [1,45850] (۶ سوراخ = B1).
- `barg`: 45,809 قابل‌پارس (بازپارس factory). **45,800 مورد با بازپارس == ii+1.** 35 بدون barg = دقیقاً 35 خالی.
- **44,801 اختلاف barg «خروجی PCM-20» با بازپارس factory** — همان باگ `parse_barg` شناخته‌شده PCM-20.2 (پارس فقط اولین run ارقام؛ اصلاح: join همه runs برای جداکننده هزارگان) — در [parse_barg_all_runs](corpus/tasnim/common.py:51) اصلاح است.
- `content_hash`: همه سطرها، 0 تکراری.
- `captured_at`: 1 کاهش واقعی in monotonicity (page_id 11705: 2026-10-26 08:28:27 در برابر قبلی 11704) = **بازکراول/به‌روزرسانی** یک صفحه vol1 — سازگار با منطق UPDATE در `save_page`. بازه کل: 2026-10-23 08:50:16 → 2026-11-03 16:03:08.
- cursor زنده سایت (item_index 91285) > max اسنپ‌شوت → سایت هنوز در حال رشد است؛ اسنپ‌شوت ما یک لحظه‌ی منسجم است.

---

## ۳) GATE 0-C — ممیزی لودر graph-rag + برنامه سازگاری

ممیزی [load_collection.py](../rag/graph-rag/app/load_collection.py) (repo جدا `rag/` — خارج از scope این ریپازیتوری، بدون تغییر):

1. **Re-embed می‌کند:** بردارهای از پیش‌محاسبه‌شده در Dump **راسته نادیده گرفته** می‌شوند و متن دوباره embed می‌شود.
2. **Provenance را حذف می‌کند:** هر ۹ کلید provenance (page_id, item_index, barg, volume_no, url, captured_at, content_hash, source_page_id, raw_text) در گره‌ها ماندگار نیستند.
3. **ترتیب نادرست:** زنجیره NEXT/PREV در [_build_chains](../rag/graph-rag/app/_build_chains) بر پایه `page_number` (= barg) ساخته می‌شود، در حالی‌که ترتیب قطعی = **(volume, item_index)** (B5).

**برنامه سازگاری (پیشنهادی، اجرا در GATE 3):**
- لودر اختصاصی داخل toolkit: `corpus/tasnim/neo4j_loader.py`
  - بردارهای **همان Dump را مصرف** کند (بدون re-embed؛ dim+model+version از manifest dump خوانده می‌شود)؛
  - **همه کلیدهای provenance** را روی گره نگه دارد؛
  - زنجیره NEXT/PREV بر پایه **(volume_no, item_index)** با flag روی شکاف‌ها (gap → رله `NEXT` داده نمی‌شود، به‌جایش گره `Page.gap_after=true`)؛
  - هدف: **فقط یک Neo4j database جدید و صریح‌نام** (پیشنهاد: `tasnim_tafsir__qwen3_embed_06b__10pct__v0002`)؛ هیچ collection عملیاتی (بالاخص `falsafe_siasi`) لمس نمی‌شود.
- `rag/` دست‌نخورده می‌ماند (repo جدا، scope آژانس‌های دیگری).

---

## ۴) GATE 0-D — سرویس Embedding و زیرساخت (پروب‌ها)

- `LITELLM_API_KEY` در env محلی **موجود است** (مقدار هرگز چاپ نشد — قاعده ۵).
- پروب‌های شبکه (از این ماشین):
  | هدف | وضعیت |
  |-----|--------|
  | `172.20.1.52:4000` (LiteLLM) | 🟥 timeout |
  | `172.20.1.52:22` (SSH) | 🟥 timeout |
  | `172.20.1.52:2222` (GitLab) | 🟥 timeout |
  | `localhost:7474/7687` (Neo4j) | 🟥 timeout (Neo4j محلی نیست) |
  | Docker CLI | 🟥 نصب نیست |
  | `tasnim.hamtaa.org` (HTTPS) | ✅ 200 (اما SPA shell — D/B7) |
- **نتیجه:** GATE 2 (embedding واقعی با LiteLLM) = **BLOCKED**؛ ظرفیت H800 = **NOT VERIFIED** (طبق قاعده مأموریت: توقف، **هیچ سرویس جدیدی روی H800 اضافه نمی‌شود**). GATE 3 (Neo4j) = **BLOCKED** (نیاز به s52 یا Docker+Neo4j محلی — هیچ‌کدام موجود نیست).
- این بلوک‌ها **ممانعت از GATE 1 نیستند**: GATE 1 کاملاً offline است (فقط اسنپ‌شوت + کد factory).

---

## ۵) شواهد (Artifacts) و SHA-256

| فایل | SHA-256 |
|-----|---------|
| `.tmp_pcm205_gate0b_extract.json` | `7A1F13FA3CCAD6FA20CC966598E6CEDABEB6A238F11D313671CE2B5A49EADFD6` |
| `.tmp_pcm205_gate0b_recompute.json` | `4AD7B8D5197819E7E4BE4FA44C34741B9383C488DF8C902D3D99E5B1B037A8A7` |
| `.tmp_pcm205_gate0b_exact.json` | `231D01376928198408F6FE4C4CE6F77F104EB11E9329AC6845555FC99C43C45F` |
| `.tmp_pcm205_gate0d_probe.json` | `6F5BBFE754F5086C9C416FE3CE92FCC627C0C70D7A4240E5D97B8675C4791A69` |
| `.tmp_pcm205_gate0b_final.json` | `239C0443BC88071CA914BA2371607A6FD3B5D272BC9EB1584F34E060D03CC39A` |
| `.tmp_pcm205_gitstatus.txt` | (خروجی `git status`/`diff --cached --stat` لحظه GATE 0-A) |

اسکریپت‌های تولیدکننده: `.tmp_pcm205_gate0b_extract.py`, `.tmp_pcm205_gate0b_recompute.py`, `.tmp_pcm205_gate0b_exact.py`, `.tmp_pcm205_gate0d_probe.py`, `.tmp_pcm205_gate0b_final.py` — همه دترمنستیک و فقط-خواندنی روی اسنپ‌شوت.

---

## ۶) ریسک‌ها و ابهام‌های باقی‌مانده (طبق Stop-Policy)

1. ⚠️ **64 فایل `.tmp_pcm204_*` staged در git index** — مغایرت با ادعای commit؛ نیاز به تصمیم کاربر (unstage / commit / delete — بدون اجازه اقدام نمی‌شود).
2. ⚠️ **علّت ۶ سوراخِ شمارنده** و **علّت truncation@2000**: هر دو **NOT VERIFIED** و برای اثبات نیاز به s52 (در دسترس نیست). اثر روی محتوا/پیکره: ندارد (فقط flag).
3. 🟥 **s52 کامل down/unreachable** → GATE 2/3/4 و همگامی GitLab مسدود.
4. 🟠 **45,243 صفحه مفقود** (۶۰٪ کل بازه) در حال حاضر **unrecoverable** → در GATE 1 فقط `unresolved_gap` ثبت می‌شوند. کیفیت RAG آینده روی بازه‌های شکاف‌دار محدود خواهد بود (اثرپذیری: پوشش volume 47/56 ناقص).
5. ⚠️ **لودر فعلی graph-rag سه ناسازگاری دارد** (B/C) — تا GATE 3 استفاده از آن برای این پیکره **ممنوع** است (خطرات: re-embed با مدل متفاوت، از دست رفتن provenance، ترتیب غلط زنجیره).

---

## ۷) نتیجه‌گیری GATE 0 و پیشنهاد

- **احصائیه‌ها: PASS** — هر ۸ مغایرت با عدد دقیق + علّت + نمونه + شواهد توضیح داده شد؛ هیچ عددی ساختگی نیست.
- **زیرساخت: BLOCKED** — GATE 2 (LiteLLM) و GATE 3 (Neo4j) بدون s52/Docker محلی انجام‌پذیر نیستند؛ طبق سیاست توقف، **بدون سرویس جدید و بدون fallback خاموش**.
- **GATE 1 انجام‌پذیر است** (کاملاً offline): پیکره‌ی canonical v0002 با ترتیب قطعی (volume, item_index)، طبقه‌بندی سبک‌ها، context مخفی هِدینگ‌ها، ثبت شکاف‌ها به‌صورت unresolved، diff/validate/idempotency/cross-root.
- **تصمیم خواسته می‌شود:** (الف) ادامه فوری به GATE 1 و انتظار برای s52 در GATE 2–4؛ یا (ب) توقف کامل تا بازگشت زیرساخت. به‌علاوه تصمیم درباره ۶۴ فایل staged.

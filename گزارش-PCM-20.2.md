# گزارش PCM-20.2 — ممیزی عمیق خروجی واقعی تسنیم و تطبیق با AI Dump Builder

**مأموریت:** پیش از اجرای Pipeline تسنیم و Dataset Versioning، اطلاعات واقعی استخراج‌شده از
Production را بررسی کنم و سازگاری آن را با ai-dump-builder اثبات کنم.
**ماهیت:** صرفاً ممیزی و طراحی — هیچ تغییر در DB عملیاتی، crawl، رکورد، فایل اصلی،
embedding، Neo4j یا ES انجام نشد.
**تاریخ:** ۲۰۲۶-۱۱-۰۳ (UTC)
**commit اسکریپت ممیزی:** `671cbf9` (lokal) — `deploy/pcm20_2_tasnim_audit.py`

> قانون ثابت: هیچ ادعایی بدون مدرک. هر ادعای قطعی با SHA/خط-کد/خروجی واقعی پشتیبانی
> می‌شود؛ هر چیزی که هنوز مدرک مستقیم ندارد **NOT_VERIFIED** علامت خورده است.

---

## ۱. یافته‌های قطعی

این‌ها همه با مدرک مستقیم اثبات شده‌اند (SHA / خط کد / خروجی console / پاسخ زنده API):

1. **مغایرت SHA اسکریپت Export کاملاً تبیین شد** (فصل ۳): تفاوت فقط CRLF↔LF است؛
   محتوای بایتی یکسان است. نسخه‌ی اجراشده روی s52 **اثبات‌پذیر** است (LF = `0590d87b…`).
2. **حجم/هش پیکره‌ی واقعی:** `tasnim-corpus.json` = 72,959,214 B / sha256
   `cee2c08a…`؛ `tasnim-corpus.jsonl` = 72,906,133 B / sha256 `fd927b66…`؛
   **45,844 رکورد** (از PCM-20).
3. **ساختار حفره‌های item_index دقیقاً ثبت شد** (فصل ۴): 7 بازه‌ی present / 6 بازه‌ی
   missing، جمع 45,243 index مفقود در بازه‌ی 0..91,077.
4. **«برگ» سایت یک شماره‌ی صفحه‌ی پیوسته‌ی سراسری است** (= `item_index + 1`)، اثبات‌شده
   با نمونه‌ی زنده‌ی API: در `item_index=39004` مقدار برگ «برگ ۳۹٬۰۰۵» = 39,005.
5. **باگ parse_barg در Export اثبات شد** (فصل ۴.۴): `parse_barg` فقط **اولین ریک ارقام** را
   می‌گیرد → برای «۳۹٬۰۰۵» نتیجه `39` (= floor(N/1000)). این دقیقاً آمار PCM-20 را
   توضیح می‌دهد (distinct=999، 44,810 تکراری = 45,809−999). مقدار واقعی برگ از رشته‌ی
   خام `values.برگ` قابل بازیابی است (اسکریپت PCM-20.2 همین را بازپارس می‌کند).
6. **ai-dump-builder ممیزی شد** (فصل ۷) با ارجاع به خط دقیق کد.
7. **Adapter برای تسنیم بدون هیچ تغییر در کد اصلی ممکن است** (فصل ۷.۱۰): کافی است خروجی
   تسنیم به قالب ورودی Builder (آرایه‌ی کتاب‌ها با pages) تبدیل شود و provenance از طریق
   `extra_metadata` در `product.json` عبور کند.
8. **Loader Neo4j متن‌ها را دوباره embed می‌کند** و **فیلدهای extra_metadata را در Neo4j
   می‌ریزد** (فصل ۷.۷/۷.۸) — provenance در **فایل Dump** (منبع رسمی) محفوظ می‌ماند.

---

## ۲. یافته‌های نیازمند تأیید (NOT VERIFIED)

این‌ها هنوز **مدرک مستقیم** ندارند و در انتظار اجرای read-only اسکریپت ممیزی روی s52
(دستور در پیوست) یا داده‌ای هستند که در DB عملیاتی ذخیره نشده‌اند:

| # | ادعا | چرا NOT VERIFIED | مدرک لازم |
|---|------|------------------|----------|
| N1 | تعداد دقیق صفحات/محدوده‌ی item_index/بازتگِ **هر جلد** | اسکریپت PCM-20.2 هنوز روی فایل واقعی اجرا نشده | خروجی `pcm20_2_audit.json` از s52 |
| N2 | نمونه‌های ≥20 رکورد واقعی از ابتدا/وسط/انتها و از جلدهای مختلف | همان | همان |
| N3 | تعداد دقیق رکوردهای ناقص / متن‌های خالی / زیر-20 نویسه | همان | همان |
| N4 | رکوردهای کاملِ متناظر با 9 index تکراری (URL/hash/barg) | PCM-20 فقط شمارش داد | همان |
| N5 | 9 تکراری `content_hash` (کدام صفحات، چه رابطه‌ای) | PCM-20 فقط شمارش داد | همان |
| N6 | نگاشت `failed_count=52,233` → indexهای مفقودِ خاص | DB عملیاتی **فقط شمارنده‌ی تجمیعی** دارد؛ رکورد per-index از خطا نگه‌داری نمی‌شود | نیاز به تغییر design crawler (خارج از این مأموریت) |
| N7 | provenance دو جزیره‌ی قبل از start_url (0–3,648 و 11,183–11,204) | نمی‌دانیم از چه اجرای قبلی/seed باشند | لاگ اجرای قبلی (موجود نیست) |
| N8 | علت بازه‌ی دقیقاً 5,000-صفحه‌ای 44,957–49,956 | حدس‌ها (پنجره‌ی شکست crawler) بدون مدرک | لاگ/رکوردهای خطا |
| N9 | آیا پایان واقعی سایت بالاتر از 91,285 است | بازه در بالا **باز** است (cursor 91,285 > max موجود 91,077) | اتمام کامل crawl |

> طبق قاعده‌ی مأموریت: **هیچ index مفقودی را بدون مدرک به‌عنوان «صفحه‌ی حذف‌شده» یا
> «صفحه‌ی از دست‌رفته‌ی قطعی» معرفی نکرده‌ام.** فقط الگوهای محاسباتی ثبت شده‌اند.

---

## ۳. مغایرت SHA اسکریپت Export (بخش ۱ مأموریت)

**سؤال:** SHA مرجع `81ae569b…` در مقابل SHA واقعی `0590d87…` — کدام فایل اجرا شد؟
GitHub یا Local یا s52؟

### ۳.۱ شواهد بایتی
| کپی | SHA-256 | خط‌خور | مدرک |
|------|---------|--------|------|
| working copy محلی (Windows, `core.autocrlf=true`) | `81ae569bddf2…` | **CRLF** | محاسبه روی فایل محلی |
| blob Git `deploy/pcm20_tasnim_export.py` | `0590d87b…` (نسخه‌ی LF) | **LF** | `git cat-file blob 102ddc9e…` |
| GitHub raw @`75f8846` | `0590d87b…` (10,989 B) | **LF** | fetch + hash مستقیم |
| کپی اجراشده روی s52 (curl از raw) | `0590d87b…` | **LF** | ثبت‌شده در `گزارش-PCM-20.md` بخش F |

- blob Git برای این مسیر = `102ddc9e3dc16e456e3cdd4a56ac94c05f8e1e09` — **یکسان در
  سه commit** `9cb4b8d`، `2a35c71` و `75f8846` (تحقق با `git rev-parse <sha>:path`).
- `.gitattributes`: `* text=auto eol=lf` (ضبط خط‌خور از PCM-14B.3).

### ۳.۲ تعیین نقش commitها
- `9cb4b8d` — اسکریپت Export **در اینجا وارد شد** و از آن پس دست نخورده مانده.
- `2a35c71` — commit **گزارش** PCM-20 است (فقط `گزارش-PCM-20.md`، +134 خط)؛ اسکریپت
  را **تغییر نداده** (blob یکسان).
- `75f8846` — آپدیت گزارش PCM-20 (اجرا روی s52 ثبت شد).

### ۳.۳ نتیجه (اثبات‌پذیر — NOT_VERIFIED نیست)
- **دلیل مغایرت = فقط خط‌خور** (CRLF در کپی محلی مقابل LF در Git/raw/s52). محتوا
  بایتی یکسان است.
- **نسخه‌ی اجراشده روی s52 = کپیِ curl-شده از GitHub raw = blob `102ddc9e…` (LF) =
  `0590d87b…`.** پس `0590d87…` همان «SHA واقعی/درست» است و `81ae569b…` فقط نمایش
  خط‌خور CRLF کپی محلی ویندوز.
- چون blob در سه commit یکسان است و کپی s52 مستقیماً از raw گرفته شد، **نسخه‌ی اجراشده
  اثبات‌پذیر است** و نیاز به اعلام NOT_VERIFIED نیست.

---

## ۴. تحلیل دقیق حفره‌های Crawl (بخش ۳ مأموریت)

### ۴.۱ اعداد (از PCM-20، ثبت‌شده روی خروجی واقعی 45,844 رکورد)
- بازه‌ی کل: **0 .. 91,077** (اندازه 91,078).
- **Present (7 بازه):**
  - 0–3,648 (3,649)
  - 11,183–11,204 (22)
  - 39,004–44,956 (5,953)
  - 49,957–55,698 (5,742)
  - 55,702–55,714 (13)
  - 59,591–89,279 (29,689)
  - 90,311–91,077 (767)
  - جمع distinct = **45,835**
- **Missing (6 بازه):**
  - 3,649–11,182 (7,534)
  - 11,205–39,003 (27,799)
  - **44,957–49,956 (دقیقاً 5,000)**
  - 55,699–55,701 (3)
  - 55,715–59,590 (3,876)
  - 89,280–90,310 (1,031)
  - جمع = **45,243**

### ۴.۲ شواهد زنده (GET `/api/projects/2` — 2026-11-03 16:55 UTC)
`status: running` · `saved_count: 46,046` · `failed_count: 52,233` · `skipped_count: 20` ·
`pages: 46,052` · `start_url: …item_index=39004` (بدون section) ·
`cursor_url: …item_index=91285&section=تفسیر تسنیم جلد (80)` · `created_at: 2026-10-23 09:38:59`.

### ۴.۳ تفسیرِ مبتنی بر مدرک
- **`39,004` دقیقاً `start_url` است** → این اجرا از 39,004 شروع/ری‌استارت شد.
- **0–3,648 و 11,183–11,204** **قبل** از `start_url` هستند. provenance‌شان در
  این اجرا توضیح‌داده‌نشده است (N7) — فقط الگو ثبت می‌شود، ادعای قطعی نمی‌شود.
- **44,957–49,956 دقیقاً 5,000** → بلوک ساختارمند؛ علت **NOT_VERIFIED** (N8).
- **`failed_count=52,233 ≠ 45,243`**: DB فقط شمارنده‌ی تجمیعی نگه می‌دارد، رکورد
  per-index از خطا ندارد → نگاشت دقیق **NOT_VERIFIED** (N6).
- **بازه در بالا باز است**: `cursor 91,285 > max موجود 91,077` → `91,077` پایان سایت
  **نیست**؛ crawl هنوز در حال پیشروی است (N9).
- **9 index تکراری**: رکوردهای کاملِ متناظر (URL/hash/barg) در انتظار اجرای
  PCM-20.2 (N4).

### ۴.۴ ریشه‌ی مشکل barg و ارتباط با آمار (اثبات محاسباتی)
`parse_barg` در `deploy/pcm20_tasnim_export.py` فقط `DIGITS_RE.search(...)` (اولین ریک
ارقام) را برمی‌گرداند. چون جداکننده‌ی هزارگان ٬ فقط برای N≥1000 وجود دارد:
- N<1000 → barg = N (مثلاً 55)
- N≥1000 → barg = floor(N/1000) (مثلاً «۳۹٬۰۰۵»→39)

با داده‌ی فعلی، همه‌ی bargهای کات‌شده در بازه‌ی 1..999 می‌افتند → **distinct=999** و
**تکراری = 45,809 − 999 = 44,810**. این **دقیقاً** آمار PCM-20 است → باگ تأیید شد.
**مقدار واقعی برگ** از `values.برگ` با بازپارسِ همه‌ی ریک‌های ارقام بازیابی می‌شود
(تابع `reparsed_barg` در اسکریپت PCM-20.2) و قرار است `== item_index+1` تأیید شود.

---

## ۵. ساختار واقعی جلدها (بخش ۴ مأموریت)

- **جلد از پارامتر `section` در URL قابل شناسایی است**، مثلاً
  `…&section=تفسیر تسنیم جلد (80)`. شماره‌ی جلد = عدد آخرِ section.
- **ساختار داده‌ی مناسب: Work → Edition → Volume → Page.**
  - Work = «تفسیر تسنیم» (کل اثر)
  - Edition = این نسخه/چاپ خاص (hamtaa)
  - Volume = هر `جلد (n)` (یک section)
  - Page = هر رکورد (یک item_index / یک برگ)
- **برگِ واقعی پیوسته‌ی سراسری است** (فصل ۴.۴) → «تکرار barg بین جلد» در واقع
  تکرارِ کات‌شده‌ی floor(N/1000) است، نه شماره‌ی صفحه‌ی واقعیِ درون‌جلد.
- اعداد دقیق هر جلد (تعداد صفحات، بازه‌ی item_index، بازه‌ی barg، جلدهای ناقص) =
  **NOT_VERIFIED** (N1) تا اجرای اسکریپت روی s52.

---

## ۶. Schema نهایی پیشنهادی (بخش ۶ مأموریت)

هر رکورد صفحه باید این فیلدها را حفظ کند (طبق مأموریت، provenance نمی‌تواند در
تبدیل حذف شود):

| فیلد | منبع (تسنیم) | معنی |
|------|--------------|------|
| `page_id` | `r["id"]` | شناسه‌ی یکتای صفحه در DB crawler |
| `item_index` | query `item_index` | شماره‌ی صفحه در crawl (نطاق 0..91,077) |
| `barg` | بازپارسِ `values.برگ` | شماره‌ی برگِ **واقعی** (= item_index+1) |
| `volume_no` | `section` (عدد آخر) | شماره‌ی جلد |
| `url` | `url` | URL دقیق صفحه (provenance کامل) |
| `captured_at` | `captured_at` | زمان گرفتن صفحه |
| `content_hash` | `content_hash` | اثر محتوای صفحه |
| `raw_text` | `values.متن` | متن خام صفحه |

> نکته: در Export فعلی، `barg` (فیلد عددی) **مقدار کات‌شده** است؛ `values.برگ`
> (رشته‌ی خام) **مقدار واقعی** را دارد. Adapter باید از `values.برگ` بازپارس کند.

---

## ۷. مقایسه/ممیزی ai-dump-builder (بخش ۵ و ۷ مأموریت)

موقعیت: `server52and53/_aidump`، tag `v1-baseline`، بدون remote. (v0 = `es2dump.py` و
`_wip_es2dump.py` که بایتی یکسانند؛ v2 = `build_scale50_dump.py`.)

| # | مورد | مدرک (خط کد) |
|---|------|---------------|
| ۷.۱ | **Schema ورودی** | آرایه‌ی کتاب‌ها: `{dap_code, page_count, pages:[{title, dap_code, page_number, paragraph_text, language, subjects, author, publisher, ...}]}` — ثابت‌شده با fixture در `tests/smoke_test.py` |
| ۷.۲ | **Chunking** | `make_chunk_text` (core.py:114-122): `"Metadata: book_name:{title}\nbook_id:{dap_code}\npage_number:{n}\n-----\nContent: {paragraph_text}"` (با `norm()`) |
| ۷.۳ | **extract_records** | core.py:125-162 — skip اگر `min_text_chars=20`، truncation در `max_embed_chars=6000`، `extra_metadata` فقط کلیدهای لیست‌شده را می‌کوبد (155-157) |
| ۷.۴ | **فیلدهای رکورد** | `book_id=dap_code, book_name, page_number, chunk_id=index صفحه, chunk_text, link=book://{dap}#p{n}, source_id=page._id, language, words_count, _embed_input` |
| ۷.۵ | **write_dump** | core.py:291-300 — **فقط** `_embed_input` را حذف می‌کند → فیلدهای `extra_metadata` در Dump **مانده** |
| ۷.۶ | **Embedding + fingerprint/reuse** | `fingerprint=sha1(model+\x00+embed_input)` (core.py:215-216)؛ `load_reuse_map` (266-287)؛ `embed_all` (219-263) وکتور قبلی را هنگام تطبیق fingerprint **بازمی‌کوبد** |
| ۷.۷ | **validate_dump** | core.py:322-356؛ `REQUIRED=[book_id,book_name,chunk_text,chunk_id,page_number,embedding]` (319) → وضعیت `DUMP_VALIDATED / READY_WITH_WARNINGS / FAILED` |
| ۷.۸ | **manifest + versioning** | `DUMP_SCHEMA_VERSION="1"` (42)؛ `write_manifest` (360-363)؛ builds در `builds/<model_slug>_<ts>/`؛ `flip_current` (376-384) با `os.replace` اتمیک، پوینتر **per-model** `current-<slug>.txt` |
| ۷.۹ | **رابط با Neo4j** | `load_collection.py` — `load()` (163-248)؛ **یک DATABASE به ازای هر collection** |
| ۷.۱۰ | **Loader روی embedding موجود** | خط 215-229: متنِ هر رکورد (`chunk_text`) **دوباره** با `emb.embed_query(text)` embed می‌شود و **فیلد `embedding` خودِ رکورد Dump نادیده گرفته می‌شود** |
| ۷.۱۱ | **فیلدهای ماندگار در Neo4j** | `CREATE_CHUNK` (191-197) فقط ۷ فیلد mapping + `_row` را ست می‌کند → **فیلدهای `extra_metadata` (page_id, item_index, barg, url, captured_at, content_hash) در Neo4j ریخته می‌شوند** |
| ۷.۱۲ | **زنجیره** | NEXT/PREV درون هر کتاب (237-238) با `order_by` سپس `_row` |

### ۷.۱۲.۱ نتیجه‌ی کلیدی برای Adapter
- **provenance در فایل Dump (منبع رسمی/کانونیکال) 100% محفوظ است** (7.5) اما
  **در Neo4j ذخیره نمی‌شود** (7.11). یعنی:
  - برای **RAG/جستجو** کافی است (chunk_text + book_id + book_name + page_number + link).
  - برای **پرس‌وجوی provenance صفحه در Neo4j** نیاز است یا (a) `mapping_file`
    override + تغییر Loader (کد consumer — خارج از «بدون تغییر کد»)، یا (b) provenance
    فقط از فایل Dump خوانده شود (پیشنهاد فعلی).
- **Loader همیشه دوباره embed می‌کند** (7.10) → embedding داخل Dump بیشتر «portability/
  provenance» است؛ Neo4j با مدلِ `config.json` خودش embed می‌کند. fingerprint-reuse
  صرفاً هزینه‌ی LiteLLM هنگام **build** را کم می‌کند.

### ۷.۱۳ امکان Adapter برای تسنیم **بدون تغییر کد**
**بله، ممکن است.** نقشه‌ی تبدیل (هر **جلد** = یک **book**):
- `book.dap_code` ← شناسه‌ی جلد (مثلاً `tasnim__vol{volume_no}`)
- `book.pages[]` ← صفحات همان جلد
- `page.page_number` ← `barg` (واقعی، بازپارس‌شده)
- `page.title` ← نام جلد / اثر
- `page.paragraph_text` ← `raw_text` (متن)
- `page.language` ← `fa`
- `extra_metadata` در `product.json` ← `["page_id","item_index","barg","volume_no","url","captured_at","content_hash"]`
- هیچ خطی از `core.py` تغییر نمی‌کند؛ فقط `product.json` (conf) + یک **Adapter** کوچک
  جداگانه (Tasnim JSONL → قالب ورودی Builder) نوشته می‌شود.

---

## ۸. مقایسه‌ی معماری Corpus/Dataset/Dump (بخش ۷ مأموریت)

| معیار | A: یک کتاب بزرگ برای همه‌ی تسنیم | **B: یک collection مادر + جلد‌های مستقل** | C: یک dataset مادر + dataset مستقل هر جلد |
|-------|----------------------------------|-------------------------------------------|-------------------------------------------|
| ساختار book_id | یک book_id برای 45k صفحه | **هر جلد یک book_id** | هر جلد یک database/collection جدا |
| جستجو | ✓ | ✓ | ✓ (با query بین‌database سخت‌تر) |
| بازیابی | ✓ | ✓ | ✓ |
| RAG چندمنبع | ✓ | ✓ (فیلتر بر book_id) | ⚠ (چند endpoint) |
| زنجیره‌ی NEXT/PREV | یک زنجیره‌ی 45k-صفحه‌ای (بد) | **تمیز، درون هر جلد** | تمیز |
| versioning | ✓ | ✓ (یک Dump canonical + provenance per-volume) | ⚠ (80+ build جدا) |
| توسعه‌ی آتی | ⚠ | ✓ (C بعداً از همین Adapter) | ✓ ولی هزینه‌ی عملیاتی بالا |
| هزینه‌ی عملیاتی | کم | **کم-متوسط** | بالا (80+ DB) |

**پیشنهاد: گزینه‌ی B** — یک collection مادر با جلد‌های مستقل (هر جلد = book_id).
دلایل فنی:
1. با Semantics Builder **بدون تغییر** هم‌خوان است (یک کتاب = یک جلد، طبیعی).
2. در Neo4j **قابل پرس بر اساس جلد** است (`book_id`) و زنجیره‌ی NEXT/PREV تمیز است.
3. یک **Dump canonical** واحد با provenance هر جلد از طریق `extra_metadata`.
4. **گزینه‌ی C بعداً** از همین Adapter قابل‌رسیدنی است (فصل‌بندی/جداسازی) بدون بازگشت.

---

## ۹. ریسک‌ها

| ریسک | توضیح | کاهش |
|------|-------|------|
| R1 | اجرای Pipeline قبل از اجرای ممیزی s52 → تصمیم بر داده‌ی ناقص | اول `pcm20_2_tasnim_audit.py` روی s52 (read-only) |
| R2 | استفاده از `barg` کات‌شده‌ی Export به‌جای `values.برگ` | Adapter **باید** از `values.برگ` بازپارس کند (فصل ۶) |
| R3 | فرض‌کردن `91,077` پایان سایت | بازه باز است (N9)؛ versioning را «در حال crawl» علامت بزنید |
| R4 | انتظار provenance در Neo4j | provenance در **Dump** است نه Neo4j (7.11)؛ query provenance از Dump |
| R5 | دوباره‌embed شدن در Loader → هزینه/تفاوت برداری | Loader همیشه re-embed می‌کند (7.10)؛ برای ثبات، مدل `config.json` را قفل کنید |
| R6 | `failed_count` و حفره‌ها قابل‌نمایه‌گیری per-index نیستند (N6) | برای ریشه‌یابی، لاگ per-index به crawler اضافه شود (فاز آینده) |

---

## ۱۰. برنامه‌ی اجرایی مرحله‌ی بعد

1. **[اپراتور]** اجرای read-only `deploy/pcm20_2_tasnim_audit.py` روی s52 (دستور در
   پیوست) → دریافت `pcm20_2_audit.json` و تکمیل N1..N5.
2. **[design]** تأیید نهایی نقشه‌ی Adapter (جلد→book، provenance از `values.برگ`) بر
   اساس داده‌ی واقعی.
3. **[impl, خارج از این مأموریت]** نوشتن Adapter (Tasnim JSONL → قالب Builder) +
   `product.json` برای تسنیم با `extra_metadata` کامل.
4. **[impl]** ساخت Dump اول با `--mock-embed` (آفلاین) + `validate` → سپس embed واقعی.
5. **[impl]** `load_collection.py` روی یک collection جدید (بدون دست به production).
6. **[gate]** smoke: 20 پرس‌وجوی نمونه + چک provenance از Dump + چک NEXT/PREV.
7. **[decision]** اگر نیاز به provenance در Neo4j شد → تغییر `mapping_file`/Loader
   (با طراحی جدا، چون کد consumer است).

> **محدودیت‌های رعایت‌شده در این مأموریت:** بدون تغییر DB اصلی، بدون restart/
> crawl، بدون حذف رکورد، بدون بازنویسی JSON اصلی، بدون embedding جدید، بدون ساخت
> Neo4j/ES جدید، فقط اطلاعات واقعی و اثبات‌پذیر.

---

## پیوست ۱ — وضعیت سه محیط (جداگانه)

| محیط | آخرین commit / وضعیت | مدرک |
|------|----------------------|------|
| **Local** | بعد از commit این گزارش: `HEAD` = commit این گزارش (parent = `671cbf9` که اسکریپت ممیزی است) | `git log` محلی |
| **GitHub** (`origin/main`) | قبل از push = `75f8846d29c99e3de6a1a2ff7b4c7d3b3a5faf3c`؛ پس از push = همین commit گزارش (یکسان با Local) | `git ls-remote origin main` |
| **s52** (AI-TOOLS, 172.30.0.113) | کپی کد در `/home/saber/saberprojects/persian-corpus-toolkit` (نه git repo). اسکریپت **PCM-20** اجرا شده (خروجی‌ها موجود). **اسکریپت PCM-20.2 هنوز کپی/اجرا نشده** — در انتظار اپراتور. از سمت من host unreachable است. | `گزارش-PCM-20.md` بخش F |

## پیوست ۲ — دستور اجرای ممیزی روی s52 (read-only، برای اپراتور)

```bash
cd /home/saber/saberprojects/persian-corpus-toolkit
curl -fsSL -o deploy/pcm20_2_tasnim_audit.py \
  https://raw.githubusercontent.com/saber13812002/persian-corpus-toolkit/main/deploy/pcm20_2_tasnim_audit.py
sha256sum deploy/pcm20_2_tasnim_audit.py
python3 deploy/pcm20_2_tasnim_audit.py \
  --jsonl /home/saber/tasnim-export/tasnim-corpus.jsonl \
  --json  /home/saber/tasnim-export/tasnim-corpus.json
```
خروجی: `pcm20_2_audit.json` + خلاصه‌ی console. هیچ فایلی تغییر نمی‌کند.

## پیوست ۳ — smoke test محلی اسکریپت ممیزی
اجرا روی JSONL مصنوعی (113 رکورد، باگ barg شبیه‌سازی‌شده):
```
documents : 113 ; incomplete : 1 ; empty text : 1
dup item_index : 1 values / 1 extra ; dup content_hash : 1
barg reparse  : 113 with raw ; 1 differ from export barg ; 112 == item_index+1
item_index    : 0..119 ; present 113 ; missing 8 (3 runs)
volumes       : 3 distinct ; vol_nos 1..3
```
→ همه‌ی شمارنده‌ها درست؛ `sample_mismatches` باگ کات‌شده را درست شناسایی کرد
(`raw=۱٬۰۰۶, export_barg=1, reparsed=1006`).

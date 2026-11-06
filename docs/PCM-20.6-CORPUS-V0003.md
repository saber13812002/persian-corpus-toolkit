# PCM-20.6 SUBTASK 02 — تثبیت پیکره‌ی تسنیم (قرارداد معنایی v0003 / cs-20.6)

**وضعیت:** کامل‌شده؛ ۴ commit روی branch `pcm-20.6` (از `main` = `11233e9`)؛ بدون push؛ بدون deploy؛ s52 فقط‌خوانده؛ s53 فقط inference.
**هدف:** (۱) قرارداد معنایی v0003 با hidden-context + truncation، (۲) تحلیل شکاف 45,243 `item_index` مفقود، (۳) رسمی‌سازی برش 2000 کاراکتر، (۴) پایلوت hidden-context با مدل داخلی، (۵) رگرسیون کامل + این سند.
**مرجع‌ها:** زنجیره‌ی داده = `docs/PCM-20.3-TASNIM-FORFACTORY.md` (c-20.3) و `docs/PCM-20.4-TASNIM-ACCEPTANCE.md` (GATE 1.5)؛ قرارداد cs-20.5 از PCM-20.5.

---

## ۱. خلاصه و وضعیت گیت‌ها

| مرحله | کار | نتیجه |
|-------|-----|-------|
| D1 | قرارداد معنایی v0003 (cs-20.6): HeadingRecord + hidden context + truncation | **GO** — بیلد واقعی v0003 + 12 تست V30x |
| D2 | تحلیل شکاف `item_index` (gap_report) + نمونه‌گیری زنده ≤10 | **GO** — 45,243 مفقود در 6 بازه؛ زنده 8/8 `present` |
| D3 | رسمی‌سازی برش 2000 کاراکتر + recheck زنده | **GO** — 28 صفحه at-cap (0.06%)؛ recheck 3/3 زنده `live_len=2000` |
| D4 | پایلوت hidden-context با Qwen3.8-27B-FP8 (s53) | **STOP** — 17/37 = 45.95% < 80% (سیاست مکتوب v1)؛ تحلیل ریشه‌ای: همه‌ی FAILها فقط gate overlap — جزئیات §5 |
| D5 | رگرسیون + این سند | **سبز** — 52/52 پیکره + 200/200 backend |

| commit | محتوا |
|--------|-------|
| `390ab25` | (a) D1: semantic v0003 (cs-20.6) — `corpus/tasnim/semantic.py` + `test_corpus_semantic_v3.py` |
| `52cd94b` | (b) D2: `corpus/tasnim/gap_report.py` + `test_corpus_gap_report.py` |
| `35e3fc9` | (c) D3: `corpus/tasnim/truncation_report.py` + `test_corpus_truncation_report.py` |
| HEAD branch (این commit) | (d) D4: `deploy/pcm206_hc_pilot.py` + این سند |

سه فایل PCM-20.5 که از قبل staged بودند (`.tmp_pcm205_readiness_s1.json`،
`.tmp_pcm205_readiness_s1_probe.py`، `گزارش-PCM-20.5-READINESS.md`) دست‌نخورده
staged باقی مانده‌اند. هیچ داده‌ای (`.tmp_*`، `data/`) commit نشده است.

---

## ۲. D1 — قرارداد معنایی v0003 (cs-20.6)

### ۲.۱ ساختار

`build-semantic` با opt-in `--contract cs-20.6` بیلد جدید `v0003` می‌سازد
(base = `v0002`، لایه‌ی معنایی cs-20.5 از PCM-20.5). همه‌ی تغییرات **افزایشی**
هستند: فایل‌ها و رکوردهای cs-20.5 دست‌نخورده می‌مانند (تست V304 اثبات می‌کند).

فایل‌های بیلد واقعی `data/tasnim/pcm20_5/corpus/builds/v0003/`:

| فایل | رکورد | توضیح |
|-------|-------|-------|
| `pages.jsonl` | 45,844 | همان صفحات base |
| `heading-records.jsonl` | **10,739** | رکوردهای عنوان — جدید در cs-20.6 |
| `hidden-context-records.jsonl` | **10,728** | بافت پنهان هر عنوان — جدید در cs-20.6 |
| `context-records.jsonl` | 10,728 | بخش cs-20.5 (دست‌نخورده) |
| `corpus.json` / `manifest.json` | — | `content_sha256 = 40f45e0b…e4`؛ `prev → v0002` (manifest sha `dfbbad3d…`) |

### ۲.۲ شکل رکورد عنوان (HeadingRecord)

```json
{
  "record_id": "hctx:tasnim_hamta__hamta-2026__vol001__p14",
  "record_kind": "heading",
  "heading_text": "…", "heading_hash": "…",
  "page_id": "…", "next_page_id": "…",
  "parent_heading_page_id": "…", "children_page_ids": ["…"],
  "source_class": "SECTION_HEADING",
  "visibility": "hidden_context",
  "volume_id": "…", "volume_no": 1, "volume_title": "جلد 1",
  "item_index": 14,
  "provenance": {"captured_at": "…", "content_hash": "…", "source_page_id": "…"}
}
```

- `visibility: "hidden_context"` — این بافت **هرگز** عمومی رندر نمی‌شود
  (سیستمی/داخلی است؛ قرارداد، نه توصیه).
- روابط parent/child از زنجیره‌ی عناوین روی صفحات استخراج می‌شود؛
  `next_page_id` ارجاع به صفحه‌ی بعدی برای ساخت بافت «پیام بعدی چه می‌گوید».
- از 10,739 رکورد عنوان، **10,736** دارای `next_page_id` هستند (مخزن انتخاب
  پایلوت D4).

### ۲.۳ بافت پنهان و truncation

- هر عنوان یک ContextRecord با `hidden_summary` = استخراج **کلمه‌به‌کلمه**
  (verbatim) از ابتدای صفحه‌ی بعدی دارد — اعتبارسنجی S09:
  `hidden_summary == recomputed verbatim extract`. (تولید LLMی **در این
  قرارداد نیست**؛ فقط اسکلت داده + پایلوت جدا — §5.)
- `semantic.truncation` — متادیتای truncation برای هر صفحه؛ اعتبارسنجی **V09**:
  flag ⟺ `len(text) == 2000`.
- اعتبارسنجی‌های لایه‌ی معنایی: S01–S10؛ اعتبارسنجی پیکره: V01–V09.
- قطعی: `content_sha256` روی canonical JSON (sort_keys, indent=1)؛ بیلد مجدد
  روی ریشه‌ی دیگر → همان SHA (تست V309).

---

## ۳. D2 — تحلیل شکاف `item_index` (45,243)

ابزار: [`corpus/tasnim/gap_report.py`](corpus/tasnim/gap_report.py)
(قطعی، بدون شبکه مگر `--live`؛ قرارداد `gap-report-1`) + 8 تست G01–G05.
خروجی واقعی: `data/tasnim/pcm20_5/reports/gap_report/gap-report.json`
(`content_sha256 = e24bd09a…85da`، `generated_at 2026-11-06T13:19:06Z`).

### ۳.۱ شمارنده‌های واقعی

| شاخص | مقدار |
|------|-------|
| رکوردهای snapshot | 45,844 (همه با `item_index`) |
| `item_index` متمایز | 45,835 (تکراری: 9) |
| بازه | 0 … 91,077 (گستره 91,078) |
| **مفقودی** | **45,243 صفحه در 6 بازه‌ی پیوسته** |

### ۳.۲ بازه‌های مفقود

| بازه | تعداد | تعلق (از گزارش) |
|------|-------|------------------|
| 3,649 … 11,182 | 7,534 | مرز جلد 47 ← 12 |
| 11,205 … 39,003 | 27,799 | جلد 12 |
| 44,957 … 49,956 | 5,000 | جلد نامشخص |
| 55,699 … 55,701 | 3 | جلد 47 |
| 55,715 … 59,590 | 3,876 | جلد نامشخص |
| 89,280 … 90,310 | 1,031 | مرز جلد 56 ← 80 |

### ۳.۳ نمونه‌گیری زنده (≤10 درخواست، فقط‌خوانده)

**8 درخواست — همه HTTP 200، همه `present`، 0 blocked.** نتیجه: صفحات «مفقود»
در سایت زنده **موجود**‌اند و در crawl اصلی ثبت نشده‌اند (شکاف سمت crawl، نه
سایت). 2 درخواست کنترل (آخرین موجود قبل از بزرگ‌ترین بازه = 11,204 و اولین
موجود بعد از آن = 39,004) هم `present` بودند. نکته: 3 از 8 پاسخ با متن بسیار
کوتاه (5/11/16/25 کاراکتر) برگشت — مطابق جمعیت صفحات کوتاه (بسمله/عنوان).

### ۳.۴ طرح Backfill `bf-1` — فقط طرح، **اجرا نشده**

بازکراول 45,243 `item_index` مفقود با همان مکانیزم اصلی (payload URL)،
append-only (سَنپ‌شات جدید؛ هیچ رکورد موجودی بازنویسی/حذف نمی‌شود)، rate-limited
به نرخ مشاهده‌شده (~4 صفحه/دقیقه → ~188.5 ساعت ≈ 7.9 روز). اجرای واقعی فقط در
مأموریت بعدی و با تأیید دسترسی زنده. (قاعده: هرگز بدون تأیید زنده.)

---

## ۴. D3 — رسمی‌سازی محدودیت 2000 کاراکتر

ابزار: [`corpus/tasnim/truncation_report.py`](corpus/tasnim/truncation_report.py)
(قرارداد `truncation-report-1`) + 5 تست TR01–TR04.
خروجی واقعی: `data/tasnim/pcm20_5/reports/truncation/truncation-report.json`
(`content_sha256 = e241bc08…af6`).

### ۴.۱ شواهد (غیرمستقیم + مستقیم)

1. **GATE 1.5 (PCM-20.4، PASS):** برش از **سمت منبع** — اندِکس RAG سایت
   `chunk_text` را در 2000 کاراکتر می‌بُرد؛ هیچ رکوردی >2000 نیست و در
   1800–1999 پیک مصنوعی دیده نمی‌شود. مدرک: `pcm20_4/validation/gate1_5_truncation_conclusion.json`
   (SHA `b0f45e93…d5158d`).
2. **سرشماری این مأموریت روی 45,844 صفحه‌ی بیلد v0003:**
   `at_cap = 28` (0.06%)، `over_cap = 0`.
   توزیع جلدی: جلد 47 → 5، جلد 56 → 20، نامشخص → 3.
   فهرست کامل 28 صفحه در `affected_pages` همان گزارش.
3. **recheck زنده (این مأموریت، فقط‌خوانده):** 3 صفحه از 28 صفحه‌ی at-cap —
   **مختلف** از 2 صفحه‌ای که PCM-20.4 چک کرده بود (39,137 / 66,532):

| item_index | HTTP | live_len | status | section |
|------------|------|----------|--------|---------|
| 3,036 | 200 | 2000 | at_cap | تفسیر تسنیم جلد (12) |
| 50,503 | 200 | 2000 | at_cap | تفسیر تسنیم جلد (51) |
| 50,614 | 200 | 2000 | at_cap | تفسیر تسنیم جلد (52) |

   → **3/3 در سایت زنده هم 2000 کاراکتر** — برش سمت منبع مجدداً تأیید شد.

### ۴.۲ رسمی‌سازی

- هر صفحه در v0003 متادیتای `semantic.truncation` دارد
  (`truncated_at_2000: true/false` + طول).
- **V09:** flag ⟺ `len(text) == 2000` (اعتبارسنجی اجباری در validate).
- قرارداد قطعی‌بودن: `content_sha256` روی «هسته‌ی قطعی» گزارش — بدون
  `live_recheck` و بدون `summary_fa` (این دو وابسته به شبکه/زمان هستند) —
  بنابراین SHA گزارش، با یا بدون `--live`، یکسان است (تست TR03b).

---

## ۵. D4 — پایلوت Hidden Context (مدل داخلی s53)

اسکریپت: [`deploy/pcm206_hc_pilot.py`](deploy/pcm206_hc_pilot.py) (در همین commit).
خروجی واقعی: `data/tasnim/pcm20_6/pilot/hc-pilot.json` (خارج از git).

### ۵.۱ طراحی و اجرا

- **انتخاب قطعی:** 40 مورد درخواستی، سقف 8 به‌ازای هر جلد، ترتیب
  (volume_no, item_index) → **37 مورد انتخاب شد** (جلد 1 فقط 1 و جلد 12 فقط
  4 داوطلب داشت): جلد 1:1، 12:4، 47:8، 56:8، 80:8، نامشخص:8 — داخل بازه‌ی
  مأموریت (30–50).
- **مدل:** `/models/Qwen3.8-27B-FP8` (دقیقاً همان id که API بازگرداند؛
  vLLM، `owned_by: vllm`).
- **پارامترها:** `temperature=0.3`، `max_tokens=300`،
  `chat_template_kwargs: {enable_thinking: false}`.
- **چالش API (مستند در گزارش):** این مدل reasoning است؛ بدون خاموش‌کردن
  thinking، کل بودجه‌ی 300 توکن صرف `reasoning_content` می‌شد و `content`
  **خالی** باقی می‌ماند (اجرای #2: 37/37 خروجی خالی → FAIL). پس از
  `enable_thinking=false`: `reasoning_tokens=0` و خروجی واقعی 3خطی (پروبتشده).
  `/models` هم envelope دارد (`{"object":"list","data":[...]}`) — اسکریپت هر دو
  شکل را می‌خواند.
- **prompt:** system (دستیار داخلی کتابخانه‌ای، ابداع ممنوع، فقط متن داده‌شده) +
  user (عنوان فعلی + متن صفحه‌ی بعدی + قالب 3خطی: خط ۱ موضوع، خط ۲ نکته‌ی
  محوری، خط ۳ ارتباط با عنوان). prompt کامل هر آیتم در گزارش ذخیره است.
- **اجرا:** 37/37 موفق (HTTP 200)، 0 blocked، 0 skipped؛ تأخیر:
  min 889ms / median 3195ms / max 7183ms.

### ۵.۲ سیاست نمره‌دهی (مکتوب، نسخه‌ی 1)

| gate | تعریف |
|------|-------|
| `lines_ok` | دقیقاً 3 خط غیرخالی |
| `persian_ok` | نسبت کاراکتر فارسی/عربی از کل حروف ≥ 0.70 |
| `overlap_ok` | کلمات بی‌تکرار خروجی (len≥3، نرمال‌شده ی/ک) که در صفحه‌ی بعدی یافت می‌شوند ≥ 0.40 |
| PASS | هر سه | NEAR | 2–4 خط + دو gate دیگر |
| GO | evaluated ≥ 10 و good/evaluated ≥ 0.80 |

### ۵.۳ نتیجه‌ی رسمی

**counts: PASS 17 / NEAR 0 / FAIL 20 (از 37) → good_rate 0.4595 →
سیاست v1: `STOP` («good 17/37 < 0.80»).** مطابق مأموریت («if poor → stop and
report»): **توسعه‌ی hidden-context با LLM متوقف می‌شود و گزارش داده می‌شود.**

### ۵.۴ تحلیل ریشه‌ای (چرا 20 FAIL؟)

- **همه‌ی 20 FAIL** دارند: `n_lines=3` (100%) و `persian_ratio=1.00` (100%) —
  یعنی **تنها** gate شکست‌خورده `word_overlap` است (بازه‌ی مشاهده‌شده 0.000–0.391).
- توزیع FAILها بر اساس طول صفحه‌ی بعدی: **<100 کاراکتر: 11**؛ 100–499: 2؛ ≥500: 7.
  برای صفحه‌های بسیار کوتاه، threshold 0.40 روی کلمات خروجی عملاً دست‌نیافتنی است
  (خلاصه‌ی 3خطی حتماً کلماتی می‌سازد که در متن 5–30 کاراکتری نیست).
- **بررسی دستی همه‌ی 20 FAIL** (متن صفحه‌ی بعدی در برابر خروجی):
  **0 ابداع/هاهلوسینیشن.** نمونه‌ها: صفحه‌ی بعدی فقط «بسم الله الرحمن الرحیم»
  → خروجی درست می‌گوید صفحه فقط بسمله دارد؛ صفحه‌ی بعدی فقط «* * *» → خروجی
  درست می‌گوید صفحه فاقد محتوای خواندنی است؛ صفحات بلند (احصان کنیز، نسخ در
  تکوین، سوره‌ی کوثر: مفردات/معنا/تفسیر) → پارافرایز وفادار از متن واقعی.
- **rescore جایگزین (v2، بدون شبکه):** معیار معکوس (کلمات صفحه‌ی بعدی که در
  خروجی یافت می‌شوند) هم لکسیکال است و باز هم پایین: میانگین‌نوبت کل 37 مورد
  0.208؛ حتی موردی که v1 آن را PASS داده میانگین‌نوبتش 0.185 است. هیچ آستانه‌ای
  وجود ندارد که v2 را از FAIL جدا کند (پارافرایزِ 3خطی لزوماً واژگان متن
  1000–2000 کاراکتری را تکرار نمی‌کند). **نتیجه: هم v1 و هم v2 برای این
  وظیفه‌ی خلاصه‌سازی، متریک نامناسب‌اند؛ مشکل «کیفیت مدل» نیست.**

### ۵.۵ شواهد کیفی

- نمونه‌ی PASS (جلد 80، p90314، عنوان «غرر آیات»):
  «تأکید بر اهمیت موضوع سوره و بیان یکی از اصول اخلاق اجتماعی |
  برشمردن آیات این سوره از آیات برجسته قرآن به دلیل جایگاه اخلاقی آن |
  توضیح جایگاه قرآنی و اخلاقیِ سوره‌ای که در عنوان فعلی به نام غرر آیات
  اشاره شده است»
- نمونه‌ی FAIL ولی وفادار (جلد 80، p90318، صفحه‌ی بعدی = «* * *»):
  «صفحه‌ی بعدی فاقد هرگونه محتوای متنی قابل‌خواندن است و تنها شامل
  جداکننده‌ی ستاره‌ای می‌باشد. | هیچ نکته‌ی محوری یا اطلاعات جدیدی در این
  صفحه برای خواننده وجود ندارد. | این صفحه هیچ ارتباط محتوایی با عنوان فعلی
  «مفردات» ندارد و صرفاً یک فاصله‌ی بصری است.»

### ۵.۶ توصیه برای re-pilot (مأموریت بعدی)

1. **داوری وفاداری با LLM-judge** (سنجش ورودی/خروجی، به‌جای overlap لکسیکال).
2. **فلتر حداقل طول صفحه‌ی بعدی** (≥100 کاراکتر) برای حذف موارد ساختاریاً
   نامعتبر از نمره‌دهی.
3. ثبت `reasoning_tokens` در meta برای هر پاسخ (پایش رفتاری مدل).

---

## ۶. D5 — رگرسیون و قطعی

| مجموعه | نتیجه |
|--------|-------|
| پیکره: `test_corpus_tasnim` (16) + `test_corpus_semantic` (11) + `test_corpus_semantic_v3` (12) + `test_corpus_gap_report` (8) + `test_corpus_truncation_report` (5) | **52/52 سبز** |
| backend: 11 ماژول (test_api, test_projects, test_dashboard, test_knowledge_api, test_word_factory, test_dump, test_work_registry, test_queue, test_corpus_builder, test_studio_api, test_api_contract) | **200/200 سبز** |

- 27 تستِ پیشین (PCM-20.5) در این 52 گنجیده‌اند و دست‌نخورده سبز‌اند.
- v0002 (cs-20.5) immutable: `content_sha256 = 12a93e21…f4a5`؛ تست V304
  (بخش‌های cs-20.5 در v0003 unchanged) سبز.
- قطعی: بیلد v0003 روی ریشه‌ی دیگر → همان SHA (V309)؛ گزارش‌های gap/truncation
  روی هسته‌ی قطعی → SHA ثابت با/بدون شبکه (G03, TR02, TR03b).

---

## ۷. چیزهایی که **عمداً انجام نشد**

- **Backfill اجرا نشد** (bf-1 فقط طرح — §3.4).
- **خلاصه‌ی LLMی در قرارداد v0003 نیست** — بافت پنهان فعلی verbatim است؛
  پایلوت جدا اجرا شد و به STOP رسید (§5). هیچ لایه‌ی LLMی به زنجیره‌ی
  canonical اضافه نشده است.
- **بدون deploy، بدون push، بدون لمس s52** (سایت فقط 3 درخواست فقط‌خوانده در
  D3 + 8 درخواست فقط‌خوانده در D2).
- **هیچ داده‌ای commit نشد** (`data/` gitignored؛ `.tmp_*` untracked مانده‌اند).
- سرویس/dependency جدیدی ساخته نشد (پایلوت از یک endpoint OpenAI-compatible
  موجود s53 استفاده کرد).

---

## ۸. وضعیت نهایی گیت‌ها

| درگاه | وضعیت |
|-------|-------|
| D1 قرارداد v0003 | **GO** |
| D2 گزارش شکاف | **GO** |
| D3 برش 2000 | **GO** |
| D4 hidden-context LLM | **STOP** (17/37 < 0.80؛ کیفیت مدل قابل‌دفاع، متریک نمره‌دهی معیوب — §5.4) |
| D5 رگرسیون + سند | **GO** |

## ۹. روش تست دستی

```bash
# رگرسیون پیکره (52)
.venv\Scripts\python.exe -X utf8 -m unittest test_corpus_tasnim \
  test_corpus_semantic test_corpus_semantic_v3 test_corpus_gap_report \
  test_corpus_truncation_report -v
# رگرسیون backend (200)
cd backend && ..\.venv\Scripts\python.exe -X utf8 -m unittest test_api \
  test_projects test_dashboard test_knowledge_api test_word_factory \
  test_dump test_work_registry test_queue test_corpus_builder \
  test_studio_api test_api_contract -v
# بیلد v0003 (قطعی، بدون شبکه؛ base = بیلد معنایی cs-20.5 یعنی v0002)
.venv\Scripts\python.exe -X utf8 -m corpus.tasnim.cli build-semantic \
  --data-root data/tasnim/pcm20_5 --base v0002 --contract cs-20.6
# گزارش‌ها (بدون شبکه)
.venv\Scripts\python.exe -X utf8 -m corpus.tasnim.gap_report --jsonl data/tasnim/pcm20_4/source-snapshot/tasnim-corpus.jsonl --pages data/tasnim/pcm20_5/corpus/builds/v0003/pages.jsonl --out /tmp/gap.json
.venv\Scripts\python.exe -X utf8 -m corpus.tasnim.truncation_report --pages data/tasnim/pcm20_5/corpus/builds/v0003/pages.jsonl --out /tmp/trunc.json
# پایلوت (نیاز به s53) / dry-run بدون شبکه
.venv\Scripts\python.exe -X utf8 deploy/pcm206_hc_pilot.py --dry-run
```

# PCM-20.7C — گسترش معنایی (Semantic Enrichment): خلاصه‌ی صفحه‌ی بعد

**بخش مأموریت:** ۳.۴ — قرارداد Headings/Hidden Context + پایپ‌لاین تولید خلاصه + پایلوت طبقه‌بندی‌شده + اجرای کامل.
**رأی پایلوت:** **PASS (8/8)** — مجوز اجرای کامل و ساخت `v0004` صادر شد.

---

## ۱. هدف و قرارداد جدید (cs-20.7)

برای هر heading با **صفحه‌ی بعد معتبر در همان جلد**: تولید خلاصه‌ی ≤3 خطی از
**محتوای صفحه‌ی بعد** در فیلد `retrieval_context_summary` — صرفاً متادیتای
embedding/retrieval؛ **هرگز نمایش‌داده‌نشده به کاربر**.

### 1.1 فیلدهای قرارداد رکورد heading در v0004

| فیلد | توضیح |
|---|---|
| `heading_id` / `record_id` | شناسه (`hctx:<page_id>`) |
| `item_index` / `volume_no` | موقعیت جلد/برگ |
| `heading_text` | متن heading (اصالح‌نشده) |
| `next_page_id` | page_id صفحه‌ی بعد (همان جلد) |
| `next_page_item_index` | item_index صفحه‌ی بعد (**بستن F-1**) |
| `retrieval_context` | متن کامل صفحه‌ی بعد، verbatim (**بستن F-2**) |
| `retrieval_context_summary` | خلاصه‌ی ≤3 خطی تولیدشده |
| `visibility` | `RETRIEVABLE` — حتی headings کوتاه **حذف نمی‌شوند** |
| `source_provenance` | model/prompt/params + provenance page |

قوانین سفت:
- متن صفحه‌ی اصلی **دست‌نخورده** می‌ماند.
- صفحه‌ی بعد خالی/بسیار کوتاه/پایان جلد → **بافتِ context نمی‌سازیم** (skip ثبت‌شده).
- خلاصه فقط از متن واقعی صفحه‌ی بعد؛ بدون شماره‌گذاری؛ بدون ابداع.

### 1.2 کد (افزوده‌شده در این فاز)

| فایل | نقش |
|---|---|
| `corpus/tasnim/enrich.py` (جدید) | `generate_summaries` (checkpoint/resume)، `enriched_content`، `write_enriched`، `validate_enriched` |
| `corpus/tasnim/semantic.py` | branch S11: اعتبارسنجی cs-20.7 (prev_contract باید cs-20.6 باشد) + S01–S07 |
| `corpus/tasnim/cli.py` | `build-enriched --data-root --base v0003 --summaries <ckpt>` |
| `test_corpus_semantic.py` | S01–S11 (+ smoke 57/57 در `.tmp_pcm207c_enrich_smoke.py`) |

**Smoke test:** 57/57 PASS (build روی fixture + اعتبارسنجی + idempotency + corruption).
**رگرسیون:** 52 تست semantic/T-suite سبز در لحظه‌ی ادغام.

---

## ۲. پارامترهای ثبت‌شده (پیش از اجرا — تغییر نیافته‌اند)

| پارامتر | مقدار |
|---|---|
| Endpoint | `http://172.20.1.53:8000/v1` (vLLM؛ سرویس مجاز مأموریت) |
| Model | `/models/Qwen3.8-27B-FP8` |
| Model version | `vllm-listing/created-1794094268` (از listing API) |
| Prompt version | `hc-prompt/1.0` (سیستم: «تو یک خلاصه‌نویس دقیق و کوتاه فارسی هستی.» + کاربر: ۳ خط: ۱ موضوع صفحه‌ی بعد، ۲ نکته‌ی محوری، ۳ ارتباط با عنوان؛ «بدون شماره‌گذاری، بدون ابداع») |
| max_tokens / temperature | 300 / 0.3 |
| tries / backoff | 3 (2s/5s) |
| timeout | 120s |
| pace | 1.0s بین درخواست‌ها |
| `chat_template_kwargs` | `{"enable_thinking": false}` (الزامی برای این vLLM) |
| قاضی (judge) | همان endpoint؛ temperature 0.0، max_tokens 200، tries 2، **پرامپت قاضی مستقل** |

---

## ۳. Census واقعی (v0003، read-only)

| وضعیت | تعداد |
|---|---:|
| کل headings | 10,739 |
| **واجدشرط (ok)** | **5,867** |
| skipped_next_too_short (متن صفحه‌ی بعد <100) | 4,861 |
| skipped_next_blank | 8 |
| skipped_volume_end | 3 |

طول متن صفحه‌ی بعد (واجدشرط): min 100 · p50 603 · p90 1,650 · p99 1,982 · max 2,000.
(منبع: `.tmp_pcm207c_pilot_census.json`.)

---

## ۴. پایلوت طبقه‌بندی‌شده — رأی: **PASS**

**نمونه:** 51 رکورد، طبقه‌بندی‌شده روی **همه‌ی 6 جلد** (short/medium/long buckets + جلد‌های کوچک).
**سند معیارها:** `docs/PCM-20.7C-PILOT-PLAN.md` (ثبت **پیش از** اجرا؛ بعد از اجرا تغییر نکردند).

### 4.1 معیارها در برابر نتایج (همه از `pilot-eval.json`)

| معیار | تعریف ثبت‌شده | نتیجه | آمار |
|---|---|---|---|
| A1 | 1..3 خط غیرخالی، ≥60% فارسی/خط، بدون شماره‌گذاری | ✅ | 51/51 (100%) |
| A2 | judge: ≥90% grounded-or-minor AND 0% hallucinated AND 0 judge error | ✅ | 51/51 grounded-or-minor · 0 hallucinated · 0 judge_errors |
| A3 | 0 fabrication (judge + spot-check دستی) | ✅ | 0 |
| A4 | ≥90% relevant (ارتباط با عنوان فعلی) | ✅ | 51/51 (100%) |
| A5 | 0 refusal/reflex-model boilerplate | ✅ | 51/51 |
| A6 | 0 verbatim (کپی متن صفحه‌ی بعد) | ✅ | 51/51 |
| A7 | failure checkpoint <5% | ✅ | 0/51 (0%) |
| A8 | meta fields غیرnull (model/prompt/params) | ✅ | 51/51 |

**قاعده‌ی تصمیم ثبت‌شده:** PASS = همه سبز · PARTIAL فقط در حالت A2/A4 بین 70–89% با بقیه سبز · FAIL = A2/A4<70% یا شکست A1/A5/A6 یا A3.
→ **Verdict: PASS (8/8)** · elapsed 53.6s (judge phase) · generation 97.25s.

### 4.2 فهرست صریح خطاهای معنایی (21 مورد — ثبت‌شده، نه پنهان‌شده)

فایل: `data/tasnim/pcm20_5/pilot/semantic-errors.json` (count 21).
**همه‌ی 21 مورد از نوع `minor_extrapolation`** با برچسب‌های `boilerplate` (خط سوم کلیشه‌ای
«این مبحث با عنوان X هم‌خوانی دارد…») و/یا `heading_echo` (تکرار عنوان در خط سوم).
**هیچ hallucination و هیچ fabrication در 51 مورد نیست.** نمونه:

- `hctx:...vol001__p14` (پیشگفتار مفسر): خط سوم boilerplate.
- `hctx:...vol047__p50672` (گزیدهٔ تفسیر): heading_echo.
- `hctx:...vol047__p51376/p51581/p53934` (تناسب آیات): boilerplate.
- `hctx:...volkeyd531f422__p41878` (فهرست موضوعات): boilerplate («نقشه راه…»).

(لیست کامل 21 رکورد در فایل؛ همه با summary کامل و bucket/volume.)

### 4.3 Spot-check دستی (مستقل از judge)

`spotcheck-10.txt`: 10 رکورد منتخب (هر 6 جلد) → **بازبینی دستی: 10/10 grounded، 0 fabrication، 0 verbatim**
(`reviewed_at 2026-11-08T00:01:00Z`).

### 4.4 افشا (disclosure) — اصلاح false-positive در A5

نسخه‌ی اول regex A5 عبارت‌هایی بی‌ربط هم می‌زد؛ بعد از اجرا، **فقط خودِ regex** اصلاح شد
(مجموعه‌ی الگوهای refusal واقعی: «نمی‌توانم|نمی‌شود خلاصه|متأسفم|…|به عنوان یک مدل»…) —
**قصد معیار و آستانه‌ها تغییر نکردند** و نتیجه‌ی A5 (51/51) با regex اصلاح‌شده دوباره محاسبه شد.
این اصلاح در §9 برنامه‌ی پایلوت ثبت شده است (قاعده‌ی «بعد از اجرا تغییر نمی‌کنند» برای
**معیارها** است، نه برای باگ‌های خودِ کد ابزار؛ با افشای صریح).

### 4.5 درس‌های PCM-20.5/20.6 اعمال‌شده

- **word-overlap به‌عنوان معیار faithfulness استفاده نشد** (فقط judge مستقل + spot-check دستی).
- خطاهای معنایی **صریح فهرست** شدند (21 مورد).
- معیارهای پذیرش **پیش از اجرا** ثبت شدند.

---

## ۵. Leakage — خلاصه هرگز به کاربر نمایش داده نمی‌شود

- `retrieval_context_summary` (و `retrieval_context`) **فقط** در build semantic cs-20.7 نگهداری می‌شود.
- read-model web (`web/readmodel.py`، `_headings_pass`) این فیلدها را **خوانده و به DB/UI نمی‌آورد** — خروجی DOM فقط از فیلدهای عمومی heading است (XSS: `escHtml`).
- test leakage در Task 17/18: بررسی می‌کند summary در payload عمومی/UI/API **نباشد**.

---

## ۶. اجرای کامل 5,867 رکورد (در حال اجرا)

- **checkpoint:** `data/tasnim/pcm20_5/full/summaries-full.jsonl` (resume-safe؛ seed از 51 رکورد پایلوت — **بدون تکرار درخواست**).
- **در لحظه‌ی نگارش این بخش:** ~800/5,867 (00:37 UTC)؛ نرخ واقعی ~30–34/دقیقه → ETA ~03:05 UTC.
- پس از اتمام: `full-stats.json` (stats.failed باید 0 یا بسیار کم باشد؛ هر failure قابل retry با resume=True).
- سپس: `build-enriched --base v0003 --summaries full/summaries-full.jsonl` → **v0004** (سند: `PCM-20.7C-VERSIONING.md`).

### 6.1 حسابداری درخواست‌های LLM (واقعی، از فایل‌ها)

| فاز | درخواست | منبع |
|---|---:|---|
| probe endpoint (models + chat smoke) | 1 GET + 1 chat | `.tmp_pcm207c_llm_probe.json` |
| pilot generation | **51** (51 ok، 0 error) | `pilot/gen-stats.json` |
| pilot judge | 1 درخواست/رکورد (≥51؛ 0 judge_error) | `pilot/pilot-eval.json` (A2) |
| full run | ≤5,816 (باقی‌مانده بعد از seed پایلوت) | `full/full-stats.json` (بعد از اتمام) |

(سرویس LLM در s53 سرویس مجاز مأموریت است؛ مستقل از بودجه‌ی probe روی `tasnim.hamtaa.org` که جداگانه 10/10 و به‌کاررفته است.)

---

## ۷. درگاه‌های خروجی (فایل‌های واقعی)

| فایل | محتوا |
|---|---|
| `docs/PCM-20.7C-PILOT-PLAN.md` | معیارها ثبت‌شده + افشا + نتیجه (§9) |
| `data/tasnim/pcm20_5/pilot/summaries-pilot.jsonl` | 51 خلاصه + meta |
| `data/tasnim/pcm20_5/pilot/pilot-eval.json` | 8/8 + verdict PASS + spot-check |
| `data/tasnim/pcm20_5/pilot/semantic-errors.json` | 21 خطا (صریح) |
| `data/tasnim/pcm20_5/pilot/judge-cache.json` | پاسخ‌های قاضی (cache) |
| `data/tasnim/pcm20_5/full/summaries-full.jsonl` | checkpoint اجرای کامل (در حال رشد) |

## ۸. بازتولید (سمک بدون LLM)

```bat
cd ..\pcm-20.6-tasnim-web-v1
.venv\Scripts\python.exe -X utf8 .tmp_pcm207c_enrich_smoke.py   :: 57/57 (fake chat)
.venv\Scripts\python.exe -X utf8 -m unittest test_corpus_semantic test_corpus_semantic_v3 -v
```

(اجرای واقعی LLM فقط با endpoint مجاز و pace 1s؛ resume از checkpoint.)

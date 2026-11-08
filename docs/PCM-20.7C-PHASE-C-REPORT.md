# PCM-20.7C — گزارش نهایی فاز C (Corpus Stabilization & Semantic Enrichment)

**تاریخ:** 2026-11-08 (UTC) · **شخه:** `pcm-20.6-tasnim-web-v1` ·
**وضعیت:** **Acceptance PASS** (با ۲ blocker شناخته‌شده که نیاز به تصمیم انسانی دارند — §۸)

فاز A (web v1 + deploy) قبلاً PASS (`8b8c5bc`)؛ فاز B (TLS/observability) PARTIAL
(TLS در سطح operator مسدود — در این فاز **لمس نشد**).

---

## ۱. Scope (۹ بخش ۳.۱–۳.۹) — وضعیت

| بخش | موضوع | وضعیت | سند |
|---|---|---|---|
| 3.1 | ممیزی baseline (۴۶ چک) | ✅ 46/46 PASS (0 FAIL) | `PCM-20.7C-CORPUS-STABILIZATION.md` |
| 3.2 | ممیزی ترتیب item_index | ✅ 0 ORDER violation؛ 9 تکراری flag شد (حذف نشد) | همان + `PCM-20.7C-GAP-REPORT.md` |
| 3.3 | recompute gap + آماده‌سازی backfill (GATE B) | ✅ 45,243/6 run؛ **صفر** درخواست زنده؛ 10/10 probe 200 | `PCM-20.7C-GAP-REPORT.md` |
| 3.4 | Headings/Hidden Context (enrichment) | ✅ پایلوت PASS 8/8 + اجرای کامل 5,867 رکورد (0 failure) + v0004 | `PCM-20.7C-SEMANTIC-ENRICHMENT.md` + `PCM-20.7C-PILOT-PLAN.md` |
| 3.5 | Topics & Surahs | ✅ topics 1,080 canonical · surah **NOT_SUPPORTED** | `PCM-20.7C-SURAH-ASSESSMENT.md` |
| 3.6 | Images & metadata | ✅ NOT_AVAILABLE (منبع text-only) | `PCM-20.7C-CORPUS-STABILIZATION.md` |
| 3.7 | Versioning + datasetها | ✅ v0004 ساخته شد + 11 dataset بازسازی | `PCM-20.7C-VERSIONING.md` |
| 3.8 | تست‌ها | ✅ 27 تست جدید + رگرسیون 323 | این سند §۴ |
| 3.9 | Deliverables | ✅ 6 سند + کد + تست (git: §۶) | این سند §۵ |

## ۲. Baseline (3.1) — 46 چک، 0 FAIL (شمارنده‌های واقعی از v0003)

| معیار | مقدار واقعی |
|---|---|
| Pages | 45,844 |
| Volumes | 6 (vol001 9 · vol012 22 · vol047 9,391 · vol056 29,689 · vol080 767 · نامشخص 5,966) |
| Topics canonical | 1,080 (`t-<sha1[:12]>`) |
| Headings (SECTION_HEADING) | 10,739 |
| Hidden Context records | 10,728 |
| Missing item_index | 45,243 (6 run) |
| 2,000-char truncation | 28 |
| Duplicate item_index | 9 (18 row) |

زنجیره‌ی provenance (Snapshot → Canonical → Semantic → Dataset → Dump) با SHA verify شده.

## ۳. نتایج کلیدی

### 3.1 Gap recompute + GATE B (3.3)

- 45,844 رکورد · 45,835 متمایز · 9 تکراری · بازه 0..91,077 (span 91,078) · **45,243 مفقود (49.7%)**.
- 6 run مفقود: [3649–11182: 7,534] · [11205–39003: 27,799] · [44957–49956: 5,000] ·
  [55699–55701: 3] · [55715–59590: 3,876] · [89280–90310: 1,031].
- آرتیفکت‌ها (real): `gap-report-2` content sha `501240608f2bac1a21fb827c8e1507b54f28cebb057e2c46ad2d9ce1f2586a24` ·
  `fetch-plan-1` sha `b9b1c7e36a9b25edc072c94dbe59e5e909e5412ed5e9e5b159ce545b48f4902d`
  (45,243 درخواست · 91 ران × 500 · 188.5 ساعت @ 4 صفحه/دقیقه ≈ 7.85 روز).
- **GATE B رعایت شد:** صفر درخواست bulk زنده به s52؛ فقط 10 probe خواندنی (budget
  مأموریت؛ هر 10 تا HTTP 200) — budget **تمام** شد.

### 3.2 Enrichment (3.4) — پایلوت + اجرای کامل

**پایلوت (51 رکورد): رأی PASS (8/8)** — `data/tasnim/pcm20_5/pilot/pilot-eval.json`:

| معیار | نتیجه |
|---|---|
| A1–A4، A5، A8 | 51/51 هرکدام |
| A6 (verbatim/leak) | 0 از 51 |
| A7 (judge errors) | 0 از 51 |
| Hallucinated (طبقه‌بندی قاضی) | 0 |
| semantic_errors | 21 (همه `minor_extrapolation` با flag `boilerplate`/`heading_echo` — ثبت‌شده در `pilot/semantic-errors.json`) |
| قاضی | همان endpoint vLLM؛ temp 0.0 · max_tokens 200 · tries 2 · پرامپت مستقل |
| Spot-check دستی | 10/10 (reviewed_at 2026-11-08T00:01:00Z) |

افشای A5: regex تشخیص «رد درخواست» **بعد از** اجرا اصلاح شد (patternهای واقعی)؛
مقصد معیار تغییر نکرد؛ در §9 سند پایلوت ثبت شد.

**اجرای کامل (5,867 رکورد واجدشرط): 0 شکست:**

- stats: eligible 5,867 · generated 5,816 · resumed 51 (پایلوت) · failed 0 · skipped 4,872 · filtered 0
- requests: 5,816 ok / 0 errors · elapsed 12,734.19s (~3.54h)
- checkpoint نهایی: 5,867 خط · 5,867 record_id متمایز · 0 تکرار · 0 normalize نامعتبر ·
  0 کلید نامعتبر · 1 model (`/models/Qwen3.8-27B-FP8`) · 1 prompt-version (`hc-prompt/1.0`) ·
  51/51 seed پایلوت · remaining 0
- `summaries-full.jsonl` sha `78f22436f0069c5d2d612d5210415876b1bc953988d31bfbd72b48433ea4d68c`
- statusهای ثبت‌شده: ok 5,867 · failed 0 · skipped_next_too_short 4,861 · skipped_next_blank 8 · skipped_volume_end 3 · skipped_no_next 0

### 3.3 v0004 (3.7)

- **ساخت شد و validate PASS:** content `d7ebaeb361aec453ab629af0c7f6890dc73292dbd3f9f71845074720a23e50df` ·
  manifest sha `73c7b3e13244ded42030982eccec476d4a924eb6696c8fd8dbd28fd3f650f635` ·
  created 2026-11-08T03:39:11Z · schema cs-20.7 · prev = v0003
  (`0e50f52b…cea60` — برابر SHA محاسبه‌شده از دیسک).
- **immutability v0003** بعد از build بازتأیید شد (6/6 SHA، از جمله manifest).
- **semantic-diff v0003→v0004 (real):** pages 45,844 بدون تغییر · added 0 · recovered 0 ·
  changed 0 · missing 0 · duplicate_rows 18 · unresolved_gaps 45,243 ·
  `semantic-change.json` sha `ed0bdf65ba3c61704660a9249034cbfbbaa7a3b4b0d8783384741871f875abc8`.
- **Leakage verdict: PASS** — (a) تست V405: خلاصه در هیچ خروجی عمومی (pages/
  context/hidden-context/dump) نیست؛ (b) پایلوت A6: 0 verbatim از 51؛
  (c) `validate_enriched` (بخش S11) چک sample-wise leakage در build v0004 PASS.

### 3.4 Datasetها (3.7)

۱۱ dataset روی base v0004 ساخته شد (5 سراسری @1/10/50/90/100 + 6 تک‌جلدی @10
شامل جلد «نامشخص» از طریق افزودنی `--volume-id`). همه‌ی content/manifest SHAها و
`volume_scope`ها در `PCM-20.7C-VERSIONING.md` §۵ ثبت‌اند (11 entry در registry).

### 3.5 Surah (3.5) — رأی **NOT_SUPPORTED**

روی 10,739 heading واقعی v0003: explicit surah 0 · mention 0 · first-line 0؛
274 heading عمومی «سور…» به‌درستی رد شدند؛ self-test 18/18؛ صفحه‌ی web
(`surahs.html`) صادقانه «پشتیبانی نمی‌شود» را با شواهد نشان می‌دهد؛ هیچ فیلد
surah به cs-20.7 اضافه **نشد** (قاعده: بدون داده، فیلد ساختگی نمی‌سازیم).

## ۴. Tests

| مجموعه | نتیجه |
|---|---|
| `test_corpus_pcm207c.py` (جدید، 27 تست: G01×3 gap recompute · SU×6 surah matcher · E01×2 enrich units · V401–V408×10 build v0004/immutable/validation/cs-20.7/leakage/idempotency/negatives/tamper · DS01–05×5 volume-id) | **27/27 GREEN** |
| رگرسیون کامل tasnim (corpus + web/sdk) | **323 OK** (107 corpus + 216 web/sdk؛ 3 skip مشروط موجود از قبل) |
| Smoke enrichment pipeline | 57/57 PASS |

## ۵. Evidence (فایل‌های آرتیفکت روی دیسک)

| آرتیفکت | مسیر |
|---|---|
| manifests زنجیره (v0001–v0004) + registry | `data/tasnim/pcm20_5/corpus/builds/vNNNN/manifest.json` · `data/tasnim/pcm20_5/manifests/registry.json` |
| checkpoint خلاصه‌ها (5,867) | `data/tasnim/pcm20_5/full/summaries-full.jsonl` (+ `full-stats.json`) |
| ارزیابی پایلوت + خطاهای semantic | `data/tasnim/pcm20_5/pilot/pilot-eval.json` · `pilot/semantic-errors.json` |
| gap report + fetch plan | `data/tasnim/pcm20_5/reports/gap_report/` (gap-report-2، fetch-plan-1) |
| semantic diff | `data/tasnim/pcm20_5/reports/diff_v0003_v0004/semantic-change.json` |
| datasetها | `data/tasnim/pcm20_5/datasets/<pct>/vNNNN/manifest.json` (11) |

هیچ آمار/درصد ساختگی در سندها نیست؛ همه‌ی اعداد از این فایل‌ها/manifestها خوانده شده‌اند.

## ۶. Git

- شخه: `pcm-20.6-tasnim-web-v1` (worktree `pcm-20.6-tasnim-web-v1`)
- Commits این فاز (بعد از این سند):
  1. enrichment pipeline (`corpus/tasnim/enrich.py` + تغییرات `cli.py`/`dataset.py`/`semantic.py`)
  2. تست مأموریت (`test_corpus_pcm207c.py`)
  3. سندهای PCM-20.7C-*.md (۶) + plan
- push: معمولی (بدون force) — SHA نهایی: **(بعد از commit در `attempt_completion` ثبت)**

## ۷. Production

- **بدون deploy:** کل کار فاز C آفلاین روی data-root محلی (`pcm20_5`) بود؛ هیچ
  تغییر DB/API/nginx/extension ندارد؛ سرویس‌های production دست‌نخورده ماندند.
- TLS (فاز B) همچنان در سطح operator مسدود است — طبق دستور مأموریت، در این فاز
  لمس نشد.

## ۸. Acceptance

**PASS** — همه‌ی ۹ بخش scope بسته شدند؛ همه‌ی دروازه‌های کیفیت (validate corpus +
semantic S11 + leakage + immutability) سبز؛ رگرسیون 323 سبز.

**Blockers نیازمند تصمیم انسانی (هر دو شناخته‌شده و مستند):**

1. **Backfill 45,243 صفحه مفقود** (~188.5h crawl زنده روی s52): طبق GATE B در این
   فاز فقط **آماده‌سازی** شد (fetch-plan-1)؛ اجرا به‌عنوان مأموریت بعدی نیاز به
   تأیید operator دارد.
2. **TLS/HTTPS s52**: از فاز B باقی‌مانده؛ مسدود در سطح operator (certbot/ACME)؛
   خارج از scope کد.

## ۹. فهرست Deliverables (سند + کد، در git)

| فایل | نوع |
|---|---|
| `docs/PCM-20.7C-CORPUS-STABILIZATION.md` | سند (baseline + findings + images/metadata) |
| `docs/PCM-20.7C-GAP-REPORT.md` | سند (gap recompute + GATE B + probes) |
| `docs/PCM-20.7C-SEMANTIC-ENRICHMENT.md` | سند (قرارداد cs-20.7 + پارامترها + اجرا) |
| `docs/PCM-20.7C-PILOT-PLAN.md` | سند (طرح پایلوت + معیارها A1–A8 + افشا A5) |
| `docs/PCM-20.7C-SURAH-ASSESSMENT.md` | سند (رأی NOT_SUPPORTED + شواهد) |
| `docs/PCM-20.7C-VERSIONING.md` | سند (زنجیره + v0004 + datasetها) |
| `docs/PCM-20.7C-PHASE-C-REPORT.md` | این سند |
| `corpus/tasnim/enrich.py` | کد (جدید) |
| `corpus/tasnim/cli.py` / `dataset.py` / `semantic.py` | کد (تغییر: build-enriched، --volume-id، S11) |
| `test_corpus_pcm207c.py` | تست (27) |
| `docs/superpowers/plans/2026-11-07-pcm-20.7c-corpus-stabilization.md` | plan مأموریت |

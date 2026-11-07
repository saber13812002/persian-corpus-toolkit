# PCM-20.6.3 — سند پذیرش Backfill پیکره

| فیلد | مقدار |
|-----|-------|
| مأموریت | PCM-20.6.3 — Track A: طرح + اسکلت جدا + تست آفلاین |
| سند طراحی | `docs/PCM-20.6.3-BACKFILL-DESIGN.md` |
| Runbook | `docs/PCM-20.6.3-BACKFILL-RUNBOOK.md` |
| کد | `corpus/tasnim/backfill/` (9 فایل) + `test_corpus_backfill.py` |
| وضعیت | **READY_FOR_APPROVAL** — Gate A عبور کرد |

---

## ۱. معیارهای پذیرش

| # | معیار | وضعیت |
|---|-------|-------|
| AC1 | طراحی کامل با invariants (item_index، page_id، volume هرگز-حدس، provenance، immutability v0003) | ✅ DESIGN §4 |
| AC2 | جایگزینی صریح طرح `bf-1` (سیاست `bf-2`) | ✅ DESIGN §9 |
| AC3 | اسکلت کامل: gap → plan → fetch+retry → checkpoint/resume → parse → volume → diff → manifest/registry → CLI | ✅ 8 ماژول + cli |
| AC4 | ≥20 تست آفلاین بدون هیچ درخواست شبکه | ✅ 28 تست (BF01–BF22b) |
| AC5 | رگرسیون ۵ سوئیت خط تولید سبز | ✅ 52 تست OK |
| AC6 | تکرار اعداد Phase-0 روی `v0003` واقعی | ✅ BF01b (28/28، read-only) |
| AC7 | بدون commit؛ فقط فایل‌های جدید در worktree | ✅ `git status` تمیز (فقط `??`) |
| AC8 | guard دوگانه زنده + dry-run بدون transport + fake-bodies آفلاین | ✅ BF19/BF20/BF20b |
| AC9 | rate model: ≤4 pg/min + jitter قطعی + backoff 30/90/270 + budget 500 | ✅ BF04/BF16 |
| AC10 | exact-once resume با checkpoint + قفل plan_sha | ✅ BF14/BF15/BF18 |
| AC11 | rollback = keep-base + entry registry (بدون دست‌زدن به base) | ✅ BF21b/BF22 |

---

## ۲. ماتریس تست (Requirement → تست)

| Requirement | تست | توضیح |
|------------|-----|-------|
| محاسبه‌ی دقیق شکاف (6 بازه / 45,243) | BF01 | فیکستور کوچک با 8 بازه‌ی قطعی |
| **تکرار اعداد Phase-0 روی v0003 واقعی** | BF01b | 6 بازه / 45,243 / 45,844 / 45,835 / 9 dup — دقیق |
| قطعی گزارش شکاف (SHA یکسان) | BF02 | اجرای دوم → همان `content_sha256` + `summary_fa` |
| ساخت/پارس URL `chunk-detail` + cross-check | BF03 | roundtrip + ParseError روی mismatch |
| ریاضیات plan: ترتیب، jitter∈[10.5,19.5]، split، برآورد | BF04 | `estimated_runs_at_budget=2` (فیکستور) + determinism |
| پارس `chunk-detail` + SHA payload | BF05 | `payload_sha256` روی canonical JSON قابل بازتأیید |
| ورودی نامعتبر (non-JSON / بدون `original_text`) | BF05b | ParseError |
| mismatch `item_index` payload↔URL | BF06 | ParseError (دفاع در عمق) |
| volume: resolved از `payload_section` | BF07 | قوی‌ترین شواهد |
| volume: resolved از `url_section` (legacy) | BF07b | شواهد دوم |
| volume: **ambiguous هرگز حدس نمی‌زند** | BF08 | `volume_no=None` + `ambiguous=true` + candidates [5,12] |
| volume: unresolved + راهنمای همسایه | BF09 | همسایه‌ها فقط guidance، در candidates نیست |
| **رگرسیون باگ barg** (PCM-20.2) | BF10 | `parse_barg_all_runs("۳۹٬۰۰۵") == 39005` |
| order ثابت quality flags | BF11 | empty/short/no_barg/missing (+truncated/dup) |
| change detection: new/unchanged/changed | BF12 | ماتریس کامل SHA |
| رکورد کامل backfill (provenance) | BF13 | همه فیلدها + `change` + `base_state` + versions |
| checkpoint: stageها + idempotent + reload | BF14 | `done` نهایی؛ `permanent_failures` مرتب |
| checkpoint: قفل plan_sha | BF15 | plan متفاوت → `CheckpointError` |
| retry با exponential backoff 30/90 | BF16 | `FlakyTransport` (2 بار 500 بعد 200)؛ sleeps دقیق |
| 404 = permanent بدون retry | BF17 | attempts=1، reason `"not_found (404)"` |
| 5xx/شبکه با تمام شدن attempts → permanent | BF17b | attempts=3 |
| **exact-once resume** در 3 اجرای budget-chunked | BF18 | records [3,4,8,9]؛ verify OK؛ تکرار اجرا = بدون دوباره‌fetch |
| CLI dry-run end-to-end (بدون transport) | BF19 | budget 4؛ بدون `backfill-records.jsonl`؛ verify exit 0 |
| **guard زنده**: 3 ترکیب ناقص → exit 2 | BF20 | بدون flag / بدون env / هر دو — هیچ فایل run-report |
| `--fake-bodies` بدون guard (آفلاین) | BF20b | exit 0، 2 رکورد، permanent 0 |
| diff پنج‌حالته + absent | BF21 | new/duplicate/unchanged/changed/absent + `absent[10]` |
| rollback: entry registry append-only | BF21b | `rolled_back` + `active_base_unchanged` + registry هر دو entry |
| manifest v0004: prev/immutable/rollback/policy | BF22 | `backfill-manifest-1`؛ `prev → v0003/corpus`؛ `old_wins=true` |

---

## ۳. نتایج واقعی اجرا (verbatim)

### ۳.۱ سوئیت جدید — `test_corpus_backfill.py` (worktree، بدون داده‌ی واقعی)

دستور (از ریشه‌ی worktree `pcm-20.6-tasnim-web-v1`):

```bat
c:\Users\s.tabatabaei\Documents\saberprojects\persian-corpus-toolkit\.venv\Scripts\python.exe -X utf8 -m unittest test_corpus_backfill -v
```

نتیجه:

```text
Ran 28 tests in ~7s
OK (skipped=1)
```

- **27 تست PASS**؛ 1 skip = **BF01b** (داده‌ی واقعی `v0003` در worktree نیست —
  به‌صورت خودکار skip می‌شود تا آفلاین بماند).

### ۳.۲ همان سوئیت — روی `v0003` واقعی (read-only از main worktree)

```bat
set TASNIM_V0003_DIR=c:\Users\s.tabatabaei\Documents\saberprojects\persian-corpus-toolkit\data\tasnim\pcm20_5\corpus\builds\v0003
python -X utf8 -m unittest test_corpus_backfill -v
```

نتیجه:

```text
Ran 28 tests in 6.8s
OK (0 skipped)
```

- **28/28 PASS** — BF01b **اعداد Phase-0 را دقیق تکرار کرد**:
  6 بازه · 45,243 مفقود · 45,844 کل · 45,835 متمایز · 9 dup.
- `v0003` فقط خوانده شد (`build_gap_report_v2` = read + `sha256_file`).

### ۳.۳ رگرسیون ۵ سوئیت خط تولید (worktree root)

```bat
python -X utf8 -m unittest test_corpus_tasnim test_corpus_semantic test_corpus_semantic_v3 test_corpus_gap_report test_corpus_truncation_report -v
```

نتیجه:

```text
Ran 52 tests in 35.677s
OK (skipped=2)
```

| سوئیت | تعداد | وضعیت |
|------|------|------|
| `test_corpus_tasnim` | 16 | OK |
| `test_corpus_semantic` | 11 | OK |
| `test_corpus_semantic_v3` | 12 | OK |
| `test_corpus_gap_report` | 8 | OK (1 skip: **G05** — snapshot واقعی در worktree نیست) |
| `test_corpus_truncation_report` | 5 | OK (1 skip: **TR04** — v0001 واقعی در worktree نیست) |

> Skipها (نه fail) هستند و صرفاً به‌خاطر نبود داده‌ی واقعی در worktree جدا
> است؛ همان تست‌ها روی main worktree (که داده دارد) در Phase-0/PCM-20.5 سبز بوده‌اند.

### ۳.۴ smoke test CLI

```text
python -X utf8 -m corpus.tasnim.backfill.cli --help   → exit 0
```

(5 subcommand: `gap-report · plan · run · verify · register`)

---

## ۴. شواهد عینیت (evidence)

| # | شواهد |
|---|-------|
| E1 | `git status` worktree: فقط `?? corpus/tasnim/backfill/` و `?? test_corpus_backfill.py` (+ 3 سند)؛ هیچ commit؛ base `20911d7` |
| E2 | 0 درخواست شبکه در تمام اجراها (FakeTransport / transport=None) |
| E3 | `v0003` read-only: SHA base قبل/بعد در `verify_output` بازخوانی می‌شود |
| E4 | BF01b: تکرار دقیق اعداد Phase-0 (§3.2) |
| E5 | CLI `--help` exit 0 (§3.4) |

---

## ۵. درگاه تصمیم (Gate A)

**وضعیت: `READY_FOR_APPROVAL`**

- طرح + اسکلت + 28 تست آفلاین + رگرسیون 52 تست: **همه سبز**.
- اعداد واقعی Phase-0 روی `v0003` واقعی تکرار شدند (BF01b).
- هیچ درگاه باز فنی برای **این مأموریت** نیست؛ درهای باز (B: دسترسی زنده/نرخ؛
  C: register) به مأموریت اجرای واقعی تعلق دارند (Runbook).

**محدودیت‌های صادقانه (نه بازدارنده):**
- `run` زنده هرگز در این مأموریت اجرا نشده (به‌صورت طراحی ممنوع) — مسیر آن
  فقط با fake-bodies و dry-run پوشش داده شده است.
- برآورد 188.5h بر اساس نرخ هدف است؛ نرخ واقعی فقط در Gate B مشخص می‌شود.
- `v0004` هنوز ساخته **نشده** — خروجی، لایه‌ی آماده‌ی ساخت با manifest/registry است.

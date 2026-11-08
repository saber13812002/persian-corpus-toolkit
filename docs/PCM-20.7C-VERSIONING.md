# PCM-20.7C — Versioning: زنجیره‌ی v0004 + بازسازی datasetها

**بخش مأموریت:** ۳.۷ — ساخت نسخه‌ی جدید از پیکره (additive)، immutable ماندن نسخه‌های
قبلی، ثبت زنجیره‌ی provenance و بازسازی همه‌ی datasetها روی نسخه‌ی جدید.

**نتیجه:** `v0004` (cs-20.7) ساخته و اعتبارسنجی‌شده (PASS)؛ `v0003` immutable
تأییدشده؛ ۱۱ dataset (۵ سراسری + ۶ تک‌جلدی @10%) روی v0004 بازسازی‌شده.

---

## ۱. زنجیره‌ی نسخه‌های پیکره (real — از manifests روی دیسک)

| version | created_at | schema | content_sha256 | manifest sha256 | prev |
|---|---|---|---|---|---|
| sfd927b663733 (source-snapshot) | — | — | — | `239f38df211c30f19058c1bde3a1aa981d64ea04655bbbe468dd0716888bfe5a` | — |
| v0001 | 2026-11-04T23:33:08Z | c-20.3 | `ee87686ac49ce9c08a4a492f4f54c23ace571bb8f048aa8a0a863bece3d542d8` | `72a3cb9354f9d78901623d2fd56191e4b93088f266ce60fff7ae33784690c6bc` | source-snapshot sfd927b663733 |
| v0002 | 2026-11-04T23:40:16Z | cs-20.5 | `12a93e218bbc7a38d450749eca5ce25d0833b537cc13446048d430eade54f4a5` | `dfbbad3da6372a0663a30fe7b2efae31c9c8e4cd54c33341b6d1973b2601bff8` | v0001 |
| v0003 | 2026-11-06T12:35:21Z | cs-20.6 | `40f45e0b2c393a65569846aeaac4d45dcee4bd58a7f158b1554adf3755ca78e4` | `0e50f52b7fb5eb8df81e15464014a35ad3797ead2641fc2965f29edf125cea60` | v0002 |
| **v0004** | **2026-11-08T03:39:11Z** | **cs-20.7** | **`d7ebaeb361aec453ab629af0c7f6890dc73292dbd3f9f71845074720a23e50df`** | **`73c7b3e13244ded42030982eccec476d4a924eb6696c8fd8dbd28fd3f650f635`** | v0003 |

- prev v0004 = `{kind: corpus, path_rel: corpus/builds/v0003/manifest.json,
  sha256: 0e50f52b…cea60}` — دقیقاً برابر SHA محاسبه‌شده از فایل manifest.json
  v0003 روی دیسک (زنجیره verify شده).
- registry (`data/tasnim/pcm20_5/manifests/registry.json`) ۱۵ entry دارد:
  ۴ corpus + ۱۱ dataset + ۱ source-snapshot؛ content/manifest SHAهای همه‌ی
  entryها با manifests روی دیسک یک‌به‌یک مطابقت دارند (چک‌شده در
  `.tmp_pcm207c_chain.json`).
- قواعد زنجیره: **افزایشی و immutable** — هیچ نسخه‌ی قبلی بازنویسی/پوشیده
  نمی‌شود؛ هر build جدید `vNNNN+1` می‌سازد؛ `previous_version` + `prev` در
  manifest جدید به نسخه‌ی پایه اشاره می‌کند؛ idempotency: اگر content sha
  یکسان باشد `REUSED` چاپ می‌شود و نسخه‌ی جدید ساخته **نمی‌شود**
  (تست‌شده: V406 / T05 / V307).

## ۲. فایل‌های v0004 (از manifest v0004 — real)

| فایل | SHA-256 | اندازه | نسبت به v0003 |
|---|---|---|---|
| `pages.jsonl` | `8bec1bb8d2b66baa43a589a0ed29b63d1cf9f1527b80b2890b2081929648755b` | 170,629,785 B | **byte-identical** (متن صفحات دست‌نخورده) |
| `corpus.json` | `16c4179667bbf9db5c8d3e95137992b8c083369ba12a0e8b89f1f1d00bac0618` | 20,829 B | **جدید** (cs-20.7 + بلوک enrichment) |
| `heading-records.jsonl` | `ad7200f397afa155c1e7745ab7d5c39255638d80eeb52f2877ed7f3c0e85d08f` | 21,488,568 B | **جدید** (فیلدهای cs-20.7: summary + next_page_item_index + retrieval_context) |
| `context-records.jsonl` | `a1ac04216c38243a26ca40e1857ec210965cfdecb464bc70f06afcb54805a949` | 26,287,577 B | byte-identical |
| `hidden-context-records.jsonl` | `f5e07013a3a70b04ef41ac35edf31205f3ae846e29713f1e55737543fadd2329` | 17,895,082 B | byte-identical |

بلوک `enrichment` در corpus.json (cs-20.7) — real:

| کلید | مقدار |
|---|---|
| schema_version / prev_contract | cs-20.7 / cs-20.6 |
| status_counts | ok 5,867 · failed 0 · skipped_next_too_short 4,861 · skipped_next_blank 8 · skipped_volume_end 3 · skipped_no_next 0 |
| method / prompt / model | llm-summary/1.0 · hc-prompt/1.0 · `/models/Qwen3.8-27B-FP8` |
| model_version / temp / max_tokens | vllm-listing/created-1794094268 · 0.3 · 300 |
| min_next_page_chars / max_summary_lines | 100 / 3 |
| summaries_source | count 5,867 · file `full/summaries-full.jsonl` · sha256 `78f22436f0069c5d2d612d5210415876b1bc953988d31bfbd72b48433ea4d68c` |
| hidden_context.heading_records | count 10,739 · record_version v2 |

### ۲.۱ اجرای کامل (5,867 رکورد)

- stats: eligible 5,867 · generated 5,816 · resumed 51 (پایلوت) · failed 0 ·
  skipped 4,872 · filtered 0.
- requests: 5,816 · ok 5,816 · errors 0؛ elapsed 12,734.19s (~3.54h؛
  2026-11-08 ~00:14Z تا 03:38Z).
- آدیت نهایی checkpoint: 5,867 خط، 5,867 record_id متمایز، 0 تکرار، 0 normalize
  نامعتبر، 0 کلید نامعتبر، یک model، یک prompt-version، 51/51 seed پایلوت،
  remaining 0.

## ۳. Immutability v0003 (بازتأیید **بعد** از build v0004 — real disk SHAs)

| فایل v0003 | SHA روی دیسک بعد از build | برابر manifest v0003؟ |
|---|---|---|
| pages.jsonl | `8bec1bb8…9648755b` | ✅ |
| corpus.json | `8e71a3955df7a263eb10365bdecfca23c0b3b82d7ac271a6b8126807fd9f51b1` | ✅ |
| heading-records.jsonl | `0a1e52a5fab2e412adbf8e7f3558b9041bae3798da72dacff4cd96dd1170b1aa` | ✅ |
| context-records.jsonl | `a1ac0421…fcb54805a949` | ✅ |
| hidden-context-records.jsonl | `f5e07013…add2329` | ✅ |
| manifest.json | `0e50f52b7fb5eb8df81e15464014a35ad3797ead2641fc2965f29edf125cea60` | ✅ (== prev.sha256 در manifest v0004) |

## ۴. Semantic diff v0003 → v0004 (real)

`reports/diff_v0003_v0004/semantic-change.json`
(sha `ed0bdf65ba3c61704660a9249034cbfbbaa7a3b4b0d8783384741871f875abc8`):

| معیار | مقدار |
|---|---|
| pages total / unchanged | 45,844 / 45,844 |
| added / recovered / changed / missing | 0 / 0 / 0 / 0 |
| duplicate_rows | 18 (9 item_index تکراری؛ همان ledger قبلی — حذف نشدند) |
| unresolved_gaps (missing item_index) | 45,243 (6 run؛ وضعیت unresolved حفظ شده در manifest v0004) |
| context_records_added | 0 |

یعنی v0004 **هیچ** تغییر محتوایی صفحه‌ای نسبت به v0003 ندارد؛ فقط بلوک‌های
semantic cs-20.7 (heading-records + corpus.json) تغییر کرده‌اند.

## ۵. بازسازی datasetها روی v0004 (real — 11 خروجی)

`pcm20_5/datasets/` پیش از این فاز خالی بود؛ همه‌ی ۱۱ dataset زیر برای اولین
بار روی base v0004 ساخته شدند (`build-dataset`):

| dataset | pct | scope | pages | content_sha256 | manifest sha256 |
|---|---|---|---|---|---|
| 1pct/v0001 | 1 | global | 458 | `b1bfbd96f1e92b5ecc6b59c77ffb53ce9fb3dd08b16191676182fd7e829a04c6` | `dc69db34b76d51214fc92d6d30ece40acae226177cf9666b5587fc080bdbeb5e` |
| 10pct/v0001 | 10 | global | 4,584 | `9f8722e00213fff85097d1ab1c64ed6cafb5ad068572df4f6c8c9d19f07267ff` | `85b4d09dfb01fd841e0dd07072d0f3b072e000d042716c2f74d71f2559745ade` |
| 50pct/v0001 | 50 | global | 22,922 | `4d7621e96472d283bdbe0d937e5a167c7863babf23aca99552ed895d9114037a` | `ea5694b4b9ebeeb49cc546602ea5318b4efc672ce502604bf2373dcc5c372ff8` |
| 90pct/v0001 | 90 | global | 41,260 | `b9234306b1ab24f7f71d947e2af86a893b4f351f3ae12752750af9afba75f675` | `75aa4f779c730d8eff5dde999ad016db511598f1364f99668f7586c25c660f29` |
| 100pct/v0001 | 100 | global | 45,844 | `9c01947167437b4a95bdac5083863beb7772e32a54242a62ca2c9e306eb71d38` | `f6dfcd22fe4c5817e401ce7f4716f9e204e37c6959c91ec1abc204ad56dd4e8f` |
| 10pct/v0002 | 10 | volume_no 1 | 1 | `cea8e598b94ae38dd011502b2b687661bb554ccdaf016dae5e9f70a5202f61d8` | `eae891633378f6f0e33e29c3dbf51e551f7419a4b6cf1d13a9838109cb240cf4` |
| 10pct/v0003 | 10 | volume_no 12 | 2 | `87df21d129306960a8bf2e7d8522c2694b1f378b3027dbe034b80e155abc3033` | `48f5ef7696f09cf530658add766855d90391fff9d7a4787a9d20991d7fb12603` |
| 10pct/v0004 | 10 | volume_no 47 | 939 | `8d8933c947755b827e11c64d2900a1ce319c9a1f2fdb52828e66a3b6afbca4ed` | `a7f33fc2bad09d72e2cb192da4995b2f2d603629db2a87d9f2f19f107c7dbca8` |
| 10pct/v0005 | 10 | volume_no 56 | 2,969 | `55dd36517acd52ac7d43dd94a140973bfe29e4f1dc7f7bf9e0be5f8ba347c02f` | `44a386ce3c3adbc05611863aa72145ad1bfd62d0185c19a9c5fd780d8a2a8979` |
| 10pct/v0006 | 10 | volume_no 80 | 77 | `24ba9c666419afba650b47654fe277c5af1e303347a93c1d0705d38b6786bd74` | `13824f4c3520eabf6ef4fadae08523dcfbcf797a460567f5648eb3b8eebeca98` |
| 10pct/v0007 | 10 | volume_id `tasnim_hamta__hamta-2026__volkeyd531f422` | 597 | `57ff381e4ebc2706668368d78f212782c810c4dda9634e90675c81b485cc41ab` | `ae0f5c13b199b73f02a6c0ffe78f919ec67817453edfacba70c9fe4001890bb8` |

- همه‌ی ۱۱ manifest دارای `dataset_meta.corpus = {version: v0004,
  content_sha256: d7ebaeb3…, source_snapshot_sha256}` و `_prev` زنجیره‌ای به
  manifest v0004.
- `volume_scope` روی دیسک verify شده: جلد‌های نام‌دار → `{"volume_no": N}`؛
  جلد «نامشخص» (بدون volume_no) → `{"volume_id": "…"}`؛ global → null.
- پوشش @10% per-volume: vol1 1/9 (11.11%) · vol12 2/22 (9.09%) · vol47 939/9,391
  (10.0%) · vol56 2,969/29,689 (10.0%) · vol80 77/767 (10.04%) ·
  nameless 597/5,966 (10.01%). (انحراف‌های جزئی جلد‌های کوچک به‌سبب
  round-to-integer در `stratify_targets`.)

### ۵.۱ افزودنی CLI این فاز

`build-dataset` اکنون `--volume-id <vid>` می‌پذیرد (برای جلد «نامشخص» که
volume_no ندارد)؛ `--volume N` برای جلد‌های نام‌دار (compat)؛ هر دو با هم →
rc=2؛ volume-id ناشناخته → rc=2. (تست‌ها: DS01–DS05 در
`test_corpus_pcm207c.py`.)

## ۶. قواعد rollback و حفظ‌قدهی

- **rollback = pointer**: چون همه‌ی نسخه‌ها روی دیسک موجود و registry
  append-only است، بازگشت به v0003 صرفاً مصرف registry entry
  `corpus:v0003` (content `40f45e0b…`) است — هیچ داده‌ای از بین نرفته است.
- اگر quality gate build جدید FAIL شود، CLI با rc=1 خارج می‌شود و نسخه‌ی
  قبلی دست‌نخورده می‌ماند (ساختار `build-enriched`: اعتبارسنجی بعد از
  نوشتن temp، ثبت در registry فقط بعد از PASS).
- datasetها **به‌صورت مستقل** versioning دارند (هر `pct_dir` زنجیره‌ی
  vNNNN خودش را دارد) و base خود را در `dataset_meta.corpus` ثبت می‌کنند؛
  پس هر dataset همیشه به‌طور دقیق مشخص است که از کدام content_sha پیکره
  ساخته شده است.

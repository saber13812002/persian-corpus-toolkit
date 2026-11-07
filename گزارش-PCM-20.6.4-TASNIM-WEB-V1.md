# گزارش PCM-20.6.4 — Tasnim Web V1 (تحویل نهایی PCM-20.6.3 + PCM-20.6.4)

- **تاریخ:** 2026-11-07 (UTC)
- **شاخه:** `pcm-20.6-tasnim-web-v1` در worktree `c:/Users/s.tabatabaei/Documents/saberprojects/pcm-20.6-tasnim-web-v1`
- **بنیاد (base):** `20911d77108e8322ae8451ff292a53e38ce49d21` (HEAD محلی `pcm-20.6`)
- **دامنه‌ی کار:** PCM-20.6.3 (آماده‌سازی backfill) + PCM-20.6.4 (پلتفرم خواندن Tasnim Web V1: لایه داده + API + فرانت‌اند + تست + SDK + Docker + مستندات)
- **حکم کلی:** تحویل کامل در ۶ commit منطقی؛ رگرسیون کامل 296 تست سبز (293 موفق / 3 skip / 0 ناکام)؛ محصول روی نسخه‌ی واقعی v0003 به‌صورت زنده تأیید شده (smoke 15/15، E2E 12/12، SDKهای زنده). هیچ merge، هیچ force-push، و هیچ تغییری روی `main` انجام نشده است.

---

## A. خلاصه‌ی مدیریتی

۱. **دو مأموریت در یک شاخه تحویل شد:**
   - PCM-20.6.3: «آماده‌سازی backfill» — ReCon فاز ۰ + طراحی ۱۵ مرحله‌ای + runbook + معیار پذیرش + اسکافالد پایپ‌لاین (۹ ماژول + ۲۸ تست) در `corpus/tasnim/backfill/`. اجرای زنده **در انتظار Gate B** (تصریح انسانی صریح) و بازگشت s52 است.
   - PCM-20.6.4: «Tasnim Web V1» — ریدمُدل FTS5 دوازده‌جدولی از pike v0003، API عمومی ۱۲ اندپوینتی با OpenAPI، پلتفرم خواندن SSR راست‌به‌چپ با ۹ روت، دو SDK بدون وابستگی (Python/JS)، compose مستقل Docker، و مجموعه‌ی ۱۴ فایلی مستندات مشتری.

۲. **نتایج کلیدی (همه از شواهد ثبت‌شده):**
   - رگرسیون آفلاین ۱۰ مجموعه: **296 تست = 293 موفق + 3 skip + 0 ناکام** (52.336s).
   - Smoke زنده 15/15، سناریوی E2E 12/12 روی نسخه‌ی واقعی v0003.
   - SDK Python: 23/23 زنده؛ SDK JavaScript (Node v24.14.0): 22/22 زنده.
   - اسکن راز (secret) روی ۸۶ فایلِ در حال commit: 300 برخورد، **همه طبقه‌بندی‌شده و مشروع، صفر راز واقعی**.
   - ۴ باگ واقعی در حین تست کشف و اصلاح شد (ETag ضعیف، thread-safety ریت‌لیمیت، autoescape SVG جلد، نمایش ETag در SDK).

۳. **موارد BLOCKED (مستند، نه ناتمام‌کاری پنهان):**
   - Docker: این میزپس بدون binary Docker است (بررسی 2026-11-07) → build/stack روی این میز اجرا نشد؛ محصول مستقیم روی 127.0.0.1:5071 تأیید شد.
   - GitLab داخلی (s52:2222): s52 آفلاین است (بازپیمایش 2026-11-07 16:29 UTC، هر ۶ پورت TIMEOUT).
   - انتشار Wiki (docs.ai.ismc.ir): REST v2 پاسخ 404 + نبود گذرنامه.
   - دامنه `tasnim.ai.ismc.ir`: DNS آماده، provisioning انجام نشد (فقط برنامه‌ریزی).
   - اجرای زنده backfill: در انتظار Gate B.

۴. **سالم بودن محیط‌ها:** worktree اصلی دست‌نخورده (HEAD `20911d7` روی `pcm-20.6` بدون تغییر)؛ `main` GitHub بدون تغییر (`f314de5…` تا پیش از push).

---

## B. وضعیت Corpus (v0003)

پیکره‌ی رسمی «تفسیر تسنیم» نسخه‌ی **v0003** (immutable، versioned، SHA-verify):

| کمیت | مقدار (شواهد ثبت‌شده) |
|---|---|
| صفحه‌ی موجود | **45,844** |
| جلد | **6** |
| موضوع | **1,080** |
| سرفصل | **10,739** |
| سوره | **0** — وضعیت `NOT_SUPPORTED` (شواهد: 265 زیرنویس عمومیِ غیرمحتوایی؛ روت `/surahs` به‌صورت صادقانه stub است) |
| صفحه‌ی مفقود (مورد backfill) | **45,243** در 6 اجرای fetch |
| صفحه‌ی truncated-2000 | **28** |
| item_index تکراری | **9** |
| ابهام volkey | `volkeyd531f422` |

**ریدمُدل (read model):** دیتابیس SQLite FTS5 با **12 جدول**؛ `tasnim_readmodel.db` حجم **260,816,896 B** با SHA256 `353f413b00467640fabfed267c9a2933a64495f3bfb3bab7e42cd43a54d9c0fd`؛ SHA محتوای v0003 = `40f45e0b2c393a65569846aeaac4d45dcee4bd58a7f158b1554adf3755ca78e4`. هر build از روی دیتای خواندنی‌فقط v0003 و با ثبت SHA در meta است؛ تغییر محتوا بدون تغییر نسخه مجاز نیست.

---

## C. Backfill (PCM-20.6.3)

- **Gate A = READY_FOR_APPROVAL** (دستاورد این فاز). اجرا فقط با **Gate B** (تصریح انسانی صریح) رخ می‌دهد.
- پایپ‌لاین **۱۵ مرحله‌ای** (بازمحاسبه‌ی gap → برنامه‌ی fetch → parse → پرچم‌های کیفیت → checkpoint/resume → versioning نسخه‌ی v0004 با diff/rollback-registry/provenance) به‌صورت **۹ ماژول** در `corpus/tasnim/backfill/`.
- **۲۸ تست** (1 skip = BF01b که نیاز به transport زنده دارد).
- **نگهبانی دوگانه برای محیط زنده:** متغیر محیطی `BACKFILL_APPROVED=approved` **و** پرچم `--allow-live` هر دو لازم‌اند؛ تا پیش از هر دو، transport زنده غیرفعال است.
- تخمین: 45,243 صفحه با سرعت محافظه‌کارانه 4 صفحه/دقیقه ≈ **188.5 ساعت** (≈ 7.9 روز پیوسته) — یعنی backfill قرار است در اجراهای checkpoint/resume چندمرحله‌ای انجام شود، نه یک‌جا.
- ReCon فاز ۰ (`docs/PCM-20.6.0-RECON.md`، 30,481 B، SHA256 `2777acc76724ac6a4f96b85d34b9a04d84bc72f664d5018c2face8f1711c96e3` — از worktree اصلی کپی و SHA یکسان تأیید شد) در commit ۱ وارد شد.

---

## D. معماری

```
 v0003 (read-only, SHA-verified)
      │ build (deterministic)
      ▼
 tasnim_readmodel.db  (SQLite FTS5, 12 جدول)
      │  tokenیزه‌شده از پیش: tokenize_fa/1.0 (تفکیک ZWNJ، نگاشت ارقام، حذف تشدید)
      │  unicode61 + prefix-AND + bm25
      ▼
 Flask /api/v1/tasnim  (12 GET + /openapi.json + /docs)
   RFC-7807 · ETag/304 · صفحه‌بندی cursor (page_token مبهم base64) · rate-limiter درون‌فرآیند
      ▲
      │ read-only
 9 روت SSR (Flask + Jinja، بدون framework کلاینت) ← HTML + design system محلی
```

- **لایه داده:** builder یک‌بار از v0003 خواندنی ریدمُدل را می‌سازد؛ همه‌ی کلیدهای پایدار `page_id` / `item_index` هستند.
- **HP-1 (عزل context پنهان) — ۴ لایه:** (1) guard در builder، (2) whitelist در `strict_pick`، (3) تست‌های T-HC-1..4، (4) canary `HIDDEN-CANARY-DO-NOT-LEAK` در check 15 smoke که هر HTML خروجی را اسکن می‌کند. **10,728 رکورد context پنهان** از خروجی‌های عمومی خارج‌اند.
- **فرانت‌اند:** SSR خالص (بدون JS-framework)؛ صفحات SSR از rate-limit معاف‌اند (مستند در کد).
- **اصل کلید پایدار + جلد placeholder:** جلد کتاب‌ها SVG قطعی (deterministic) و صریحاً «رسمی‌نبودن» برچسب‌خورده‌اند؛ بدون تصویر واقعیِ ناشر.

---

## E. صفحات محصول (9 روت SSR)

| روت | توضیح |
|---|---|
| `/` | خانه: معرفی، آمار واقعیِ DB، دسترسی سریع |
| `/volumes` | فهرست ۶ جلد با شمارنده‌های واقعی |
| `/volumes/<id>` | جزئیات جلد: فهرست موضوع/سرفصل + جلد SVG |
| `/page/<item_index>` | **خواننده‌ی صفحه** با ناوبری gap-aware: صفحات مفقود را نمی‌سازد؛ حالت **gap-recovery** می‌گوید چه چیزی در دسترس است و چرا |
| `/topics` / `/topics/<id>` | فهرست موضوع (1,080) + جزئیات با صفحات وابسته |
| `/surahs` | stub صادقانه: `NOT_SUPPORTED` با توضیح شواهد (265 زیرنویس عمومی) |
| `/search` | جستجوی FTS فارسی (سروان‌شده)؛ نمونه ثبت‌شده: 6,760 hit برای «قرآن» در v0003 |
| `/about` | درباره‌ی پیکره، provenance، حدود و شرایط |

به‌علاوه 404/500 سفارشی. طراحی: **warm-paper editorial**، RTL، scale فاصله‌ی 8pt، تم تیره، فونت‌های self-hosted.

---

## F. API (`/api/v1/tasnim`)

**12 اندپوینت GET** (+ `/openapi.json` و `/docs`):

`/catalog` · `/volumes` · `/volumes/{volume_id}` · `/surahs` · `/surahs/{surah_id}` · `/topics` · `/topics/{topic_id}` · `/pages/{item_index}` · `/pages/{item_index}/neighbors` · `/search` · `/statistics` · `/health`

- خطاها به‌سبک **RFC-7807** (`application/problem+json`).
- **ETag/304** قوی (weak-ETag bug در حین تست پیدا و اصلاح شد).
- صفحه‌بندی **cursor** با `page_token` مبهم base64 (بدون اعداد توالی عمومی).
- **rate-limiter** درون‌فرآیند (thread-safety آن هم در حین تست اصلاح شد).
- OpenAPI 3.1 در `tasnim/web/openapi.py` — منبع واقعیِ spec از app (تست CT-style در CI).

---

## G. تصاویر و Metadata

- **جلد کتاب‌ها:** SVG قطعی از متادیتای v0003؛ صریحاً با برچسب «غیررسمی / تولیدشده برای نمایش». هیچ تصویر واقعیِ ناشر استفاده نشده است.
- **فونت‌ها (self-hosted، OFL 1.1):** Vazirmatn — regular / medium / bold (هر TTF ≈ 122–123 KB) + Noto Naskh Arabic (307,592 B).
- **Metadata:** همه‌ی شمارنده‌ها (صفحه/موضوع/سرفصل/جلد) مستقیم از DB خوانده می‌شوند؛ عدد ساختگی وجود ندارد (قاعده‌ی ۹ AGENTS). provenance هر رکورد به v0003 + SHAهای ثبت‌شده بازمی‌گردد.

---

## H. تست

**رگرسیون آفلاین (10 مجموعه، از ریشه‌ی worktree، venv python، `-X utf8`):**

| مجموعه | تست | skip |
|---|---|---|
| test_corpus_backfill | 28 | 1 (BF01b — نیاز به transport زنده) |
| test_corpus_gap_report | 8 | 1 (G05 — نیاز به داده‌ی زنده) |
| test_corpus_semantic | 11 | — |
| test_corpus_semantic_v3 | 12 | — |
| test_corpus_tasnim | 16 | — |
| test_corpus_truncation_report | 5 | 1 (TR04 — نیاز به داده‌ی زنده) |
| test_tasnim_readmodel | 46 | — |
| test_tasnim_api | 66 | — |
| test_tasnim_frontend | 53 | — |
| test_tasnim_sdk | 51 | — |
| **جمع** | **296** | **3 skip / 0 fail / 293 pass — 52.336s** |

**تست‌های زنده (روی v0003 واقعی، localhost):**
- Smoke (`tasnim/e2e/smoke.py`): **15/15** (شامل canary-scan HP-1 روی هر HTML).
- سناریوی E2E: **12/12**.
- SDK Python: **23/23** زنده؛ SDK JS/ESM: **22/22** زنده (Node v24.14.0 + `node --check`).
- 6,760 hit FTS برای «قرآن» به‌صورت زنده verify شد (comment مربوط در smoke.py با این مقدار به‌روزرسانی — تنها تغییر کدِ مصوب این فاز).

**باگ‌های کشف‌شده و اصلاح‌شده (۴):** ETag ضعیف/304 · thread-safety ریت‌لیمیت · autoescape در جلد SVG · نمایش ETag در SDK.

**اسکن راز:** 86 فایلِ در حال commit، 300 برخورد با الگوهای (password/passwd/secret/api_key/token/Bearer/PEM/AKIA/ghp_/xox) — هر برخورد به‌صورت دستی طبقه‌بندی شد (page_token صفحه‌بندی، token در tokenize_fa، design tokens، `BACKFILL_APPROVED=approved` نگهبانی، fixture «secret text» تستی، اشاره به `/etc/passwd` در مدل تهدید و …). **صفر راز واقعی؛ صفر فایل data/.tmp/screenshot در commit؛ بزرگ‌ترین فایل < 2MB.**

**check-ignore:** 3 مسیر حساس (داده‌ی read model `tasnim/data/`، اسکرین‌شات‌های E2E، `.tmp_*`) همه با `git check-ignore -v` تأییدِ ignore شدند. `git diff --check` پس از هر ۵ commit اول تمیز بود.

---

## I. Docker

`tasnim/docker-compose.tasnim.yml` (project name `tasnim-web-v1`):

- `tasnim-web`: nginx:1.27-alpine، پورت عمومی **5070** (تنها پورت هاستی)، healthcheck با wget از پشت proxy.
- `tasnim-api`: image ساخته‌شده از `./tasnim`، **فقط داخلی** (5071، بدون پورت هاستی)، read model با bind خواندنی‌فقط از `v0003`، volume نام‌دار `tasnim_runtime` فقط برای DB rate-limit، healthcheck روی `/api/v1/tasnim/health`.
- شبکه‌ی اختصاصی `tasnim-net`؛ **هیچ رازی در compose**.

**وضعیت اجرا: BLOCKED روی این میز** — binary Docker در دسترس نبود (بررسی 2026-11-07). به‌جای آن، کل محصول به‌صورت مستقیم (Flask + SSR) روی `127.0.0.1:5071` اجرا و با smoke 15/15 و E2E 12/12 تأیید شد. دستورهای `docker compose` در `docs/tasnim/DOCKER.md` برای میز مجهز آماده‌اند.

---

## J. دامنه

- `tasnim.ai.ismc.ir` → `172.30.0.133` (DNS آماده).
- گواهی فعلی هاست: default با `CN=admin.ai.ismc.ir` (نه گواهی این محصول)؛ پاسخ HTTP: `000` (سرویس هنوز provision نشده).
- **حکم:** فقط برنامه‌ریزی (PLAN ONLY) — هیچ provisioning در این فاز انجام نشد. مسیر پیشنهادی: 5070 هاست ← proxy سرور با X-Forwarded-Proto + TLS اختصاصی، مطابق `docs/tasnim/DEPLOYMENT.md`.

---

## K. مستندات

- **مجموعه‌ی ۱۴ فایلی `docs/tasnim/`:** INDEX, README, USER-GUIDE-FA, API-REFERENCE, DATA-CONTRACT, DEPLOYMENT, DOCKER, OPS-RUNBOOK, SECURITY, BACKUP-RESTORE, TEST-REPORT, DEVELOPER, ROADMAP, WIKI-IMPORT.
- **WIKI-IMPORT:** برنامه‌ی انتقال به Wiki.js (docs.ai.ismc.ir) نوشته شد؛ **انتخاب BLOCKED** (REST v2 → 404 + نبود گذرنامه).
- `readme.md`: بخش جدید با quickstart سه‌خطی + جدول وضعیت.
- `AGENTS.md`: قواعد ۱۰ تا ۱۴ (ریدمُدل‌های immutable + `tasnim/data/` خارج از git؛ HP-1 چهارلایه؛ کلیدهای پایدار + جلد SVG؛ رزرو پورت‌های 5070/5071 و نام‌های `tasnim-*`؛ Gate B فقط با تصریح انسانی صریح) + سطرهای نقشه‌ی راه PCM-20.6.3 و PCM-20.6.4.

---

## L. Git — جدول چهارمحیط با SHAهای دقیق

| محیط | مسیر/میزبانی | شاخه/رف | SHA | وضعیت |
|---|---|---|---|---|
| worktree محلی (مأموریت) | `c:/Users/s.tabatabaei/Documents/saberprojects/pcm-20.6-tasnim-web-v1` | `pcm-20.6-tasnim-web-v1` | **SHA همین commit ۶** (نکته‌ی پایین) | 6 commit روی بنیاد؛ status تمیز |
| worktree اصلی | `c:/Users/s.tabatabaei/Documents/saberprojects/persian-corpus-toolkit` | `pcm-20.6` | `20911d77108e8322ae8451ff292a53e38ce49d21` | **دست‌نخورده** (تأیید پس از همه‌ی کارها) |
| GitHub (origin) | `https://github.com/saber13812002/persian-corpus-toolkit.git` | `main` | `f314de544601fb0d7753e6199c9bd748cb25ef1a` | **بدون تغییر** (تأیید با `git ls-remote origin`) |
| GitHub (origin) | همان | `pcm-20.6-tasnim-web-v1` | **= SHA همین commit ۶** (پس از push) | push جدیدِ بدون-force؛ remote tip دقیقاً برابر HEAD محلی |
| GitLab داخلی | s52:2222 (172.20.1.52) | — | — | **BLOCKED** — بازپیمایش 2026-11-07 16:29 UTC: هر ۶ پورت (22/2222/443/80/4000/5055) TIMEOUT؛ remote GitLab در `.git/config` هم تعریف نیست |
| سرور s52 | 172.20.1.52 | — | — | **BLOCKED** — آفلاین 6/6 (همان بازپیمایش) |

**۶ commit (از قدیمی به جدید):**

| # | SHA | عنوان | فایل |
|---|---|---|---|
| 1 | `b11390d13ea572e05bfcfbeea00970cf0252b6ea` | PCM-20.6.3: backfill readiness — recon, design, runbook, acceptance, pipeline scaffold | 14 (+3367) |
| 2 | `2aa11f1831914b74a33c8a41aab96bd34b2bf38a` | PCM-20.6.4: Tasnim API and data layer — read model builder + /api/v1/tasnim + OpenAPI | 10 (+4538) |
| 3 | `592aca94c01cacfeaa07c7fb317e2422a7a70b12` | PCM-20.6.4: frontend and design system — RTL SSR reading platform | 29 (+6087) |
| 4 | `adb846c7116b55e3387602c9c65717951f547327` | PCM-20.6.4: tests, E2E scenario, third-party SDKs (Python/JS), integration guide | 12 (+3942) |
| 5 | `3f4225e8fa6395d54d82eb3e01486c3164256fca` | PCM-20.6.4: Docker, deployment plan, and documentation set | 21 (+2971, −1) |
| 6 | همین commit | PCM-20.6.4: final mission report (گزارش-PCM-20.6.4-TASNIM-WEB-V1) | 1 (همین فایل) |

> **چرا SHA commit ۶ در همین متن نیست:** این گزارش خودِ commit ۶ است و طبق دستور مأموریت **پیش از** push نوشته و commit می‌شود؛ بنابراین SHA خودش در لحظه‌ی نگارش وجود ندارد (self-reference). از آنجا که push یک **push جدیدِ شاخه بدون-force** است، remote tip بعد از push دقیقاً برابر `git rev-parse HEAD` این worktree خواهد بود — قابل استناد با `git ls-remote origin pcm-20.6-tasnim-web-v1` و مقدار تأییدشده در گزارش تکمیلی (attempt_completion) ثبت می‌شود.

> **حاشیه‌ی انحراف از اسنپ‌شات فاز ۰ (worktree اصلی):** در فاز ۰ سه فایل `.tmp_pcm205_readiness_s1.json` / `.tmp_pcm205_readiness_s1_probe.py` / `گزارش-PCM-20.5-READINESS.md` به‌عنوان «staged» ثبت شده بودند؛ حالت واقعی: index خالی است و این سه فایل **در HEAD track شده‌اند** (در تاریخچه‌ی `pcm-20.6` commit شده‌اند) و روی دیسک بدون تغییر موجود‌اند. HEAD اصلی (`20911d7`) و محتوای این سه فایل در پایان کار **دقیقاً همان** حالت اولیه بود؛ هیچ عملی در این فاز آن‌ها را تغییر نداد. تنها آرتفکت این فاز در worktree اصلی یک فایل موقت status بود که بلافاصله حذف شد؛ وضعیت نهایی worktree اصلی فقط `?? docs/PCM-20.6.0-RECON.md` (بازگشت انتظار — در worktree مأموریت commit شده).

---

## M. ریسک‌ها

| ریسک | وضعیت/مهار |
|---|---|
| backfill زنده روی منبع اصلی بدون تصریح | مهارشده: نگهبانی دوگانه (`BACKFILL_APPROVED=approved` + `--allow-live`)؛ اجرا فقط با Gate B |
| نشت context پنهان (HP-1) به خروجی عمومی | چهار لایه: guard builder + whitelist strict_pick + T-HC-1..4 + canary در smoke (15/15) |
| فرسودگی read model نسبت به محتوا | immutable + SHA در meta؛ هر تغییر محتوا ⇒ نسخه‌ی جدید (v0004) |
| rate-limiter درون‌فرآیند (single-instance) | برای V1 کافی است؛ compose تک‌نسخه‌ای است؛ در مقیاس‌دهی بعدی به Redis/edge منتقل می‌شود |
| بدون Docker روی این میز | مستند BLOCKED؛ دستورهای کامل در DOCKER.md؛ تأیید محصول مستقیم انجام شد |
| s52 آفلاین (GitLab/سرور) | بازپیمایش 2026-11-07 ثبت شد؛ پس از بازگشت: sync GitLab + deploy + smoke |
| ۹ item_index تکراری + 1 volkey مبهم | در gap/quality report‌ها علامت‌گذاری‌شده؛ در ریدمُدل به‌صورت صریح مدیریت شده‌اند؛ حل نهایی با backfill |
| ۲۸ صفحه‌ی truncated-2000 | گزارش‌شده (TR)؛ تکمیل در backfill |
| جلد‌های SVG | صریحاً «غیررسمی» — ریسک حقوقی تصویر واقعی حذف شد |

---

## N. تصاویر محصول

۱۰ اسکرین‌شات E2E (gitignored؛ خارج از commit؛ در `tasnim/e2e/screenshots/`):

| فایل | بایت |
|---|---|
| 01-home.png | 166,963 |
| 02-volumes.png | 73,869 |
| 03-volume-detail.png | 368,955 |
| 04-reader.png | 272,683 |
| 05-gap-recovery.png | 91,506 |
| 06-topics.png | 180,616 |
| 07-search.png | 137,410 |
| 08-about.png | 336,890 |
| 09-mobile-home.png | 33,041 |
| 10-mobile-reader.png | 68,139 |
| **جمع** | **1,730,072** |

---

## O. پیشنهاد گام بعدی

۱. **Gate B:** تصریح انسانی صریح برای اجرای backfill روی s52 (پس از بازگشت s52) — ابتدا 100 صفحه‌ی آزمایشی با diff کامل، سپس اجراهای checkpoint/resume با نرخ 4 صفحه/دقیقه (~188.5 ساعت) و تولید v0004.
۲. **Docker deploy** روی میز مجهز: `docker compose -f tasnim/docker-compose.tasnim.yml up -d` + smoke از خارج.
۳. **provisioning دامنه:** TLS اختصاصی برای `tasnim.ai.ismc.ir` روی 5070 (برنامه در DEPLOYMENT.md).
۴. **انتشار Wiki** پس از دسترسی/گذرنامه به docs.ai.ismc.ir (WIKI-IMPORT.md).
۵. **sync GitLab** پس از بازگشت s52 (push شاخه + MR اختیاری).
۶. **مأموریت بعدی داده:** embedding/Neo4j روی ریدمُدل (خارج از این فاز).

---

## روش تست دستی

از ریشه‌ی worktree (`pcm-20.6-tasnim-web-v1`):

```bat
:: ۱) رگرسیون آفلاین کامل — انتظار: 296 تست، OK، 3 skip (G05, BF01b, TR04)، 0 fail (~52s)
..\persian-corpus-toolkit\.venv\Scripts\python.exe -X utf8 -m unittest ^
  test_corpus_backfill test_corpus_gap_report test_corpus_semantic ^
  test_corpus_semantic_v3 test_corpus_tasnim test_corpus_truncation_report ^
  test_tasnim_readmodel test_tasnim_api test_tasnim_frontend test_tasnim_sdk -v

:: ۲) smoke زنده (نیاز: سرویس روی 127.0.0.1:5071 با read model v0003) — انتظار: 15/15 PASS
..\persian-corpus-toolkit\.venv\Scripts\python.exe -X utf8 tasnim\e2e\smoke.py --base http://127.0.0.1:5071

:: ۳) سناریوی E2E — انتظار: 12/12 PASS
..\persian-corpus-toolkit\.venv\Scripts\python.exe -X utf8 tasnim\e2e\e2e_scenario.py

:: ۴) SDKهای زنده — انتظار: 23/23 (Python) و 22/22 (JS؛ Node v24.14.0)
node tasnim\sdk\js\tasnim-client.live-test.mjs

:: ۵) چک دستی UI: http://127.0.0.1:5071/ و /volumes و /search?q=قرآن
::    انتظار: 6,760 نتایج (v0003) و حالت gap-recovery برای صفحات مفقود
```

---

## کارهای صریحاً انجام‌نشده (NOT done)

- ❌ اجرای زنده‌ی backfill (در انتظار Gate B + بازگشت s52).
- ❌ build/run Docker (این میز بدون binary Docker).
- ❌ sync با GitLab (s52 آفلاین؛ بازپیمایش 2026-11-07 16:29 UTC ثبت شد).
- ❌ انتشار Wiki.js (404 + نبود گذرنامه).
- ❌ provisioning دامنه/TLS (فقط برنامه).
- ❌ merge به `main` / بازکردن PR (طبق دستور: فقط push شاخه‌ی ویژگی).
- ❌ deploy روی s52 (آفلاین).
- ❌ پشتیبانی سوره (صادقانه `NOT_SUPPORTED`).
- ❌ embedding/Neo4j (مأموریت بعدی).
- ❌ هرگونه تغییر کدِ غیرمؤید: تنها تغییر کد، یک خط کامنت در `tasnim/e2e/smoke.py` (6455 → 6,760 FTS matches, live-verified) بود.

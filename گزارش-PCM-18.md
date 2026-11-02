# گزارش PCM-18 — ممیزی read-only مانیتورینگ/مشاهده‌پذیری s52 + آماده‌سازی چک PCM-17

- **تاریخ:** 2026-11-02 (Asia/Tehran)
- **base:** `cd14220` (گزارش PCM-17)
- **commit کد + اسکرپت:** `f770aff`
- **deploy:** **خیر** — هیچ deploy/restart/تغییری روی s52 انجام نشد.

---

## A. خلاصهٔ نتایج

| # | نتیجه | مدرک |
|---|-------|------|
| 1 | ممیزی secret/credential **کل repo** (git tracked): **0 hit** | `git grep` — patterns: `-----BEGIN`, `PRIVATE KEY`, `sk-…`, `AKIA…`, `ghp_…`, `xox…`, `AIza…` + اسکن `password=/token=` روی `deploy/`, `docker-compose.yml`, `dashboard/`, `extension/` |
| 2 | `docker-compose.yml`: **بدون رمز** — `PCT_DASHBOARD_PASSWORD: ${PCT_DASHBOARD_PASSWORD:-}` (فقط env-var reference) + کامنت «Never hardcode» | [`docker-compose.yml`](docker-compose.yml:15) |
| 3 | `.gitignore` کامل: `.env`, `backend/thesaurus.db`, `data/`, `wf-out/`, `*.docx` پوشش داده‌شده | [`.gitignore`](.gitignore:9) |
| 4 | اسکرپت‌های deploy: رمز داشبورد **فقط در runtime** از `.env` محلی سرور خوانده می‌شود (pattern `grep … \| cut -d= -f2-`)؛ هیچ literal در کد | 12 occurrence — همگی `PW=$(grep … .env …)` یا `printf 'PCT_DASHBOARD_PASSWORD=%s' "$PW"` (تولید `.env` روی سرور) |
| 5 | endpoint `/api/metrics` در backend **وجود ندارد** — درست مطابق نقشه‌ی راه (PCM-10)؛ PCM-18 آن را نمی‌سازد، فقط ثبت وضعیت | جستجوی `metrics|/health|prometheus` در `backend/*.py` — هیچ route‌ای |
| 6 | **اسکرپت ممیزی مشاهده‌پذیری s52 آماده:** [`deploy/pcm18_s52_observability_audit.sh`](deploy/pcm18_s52_observability_audit.sh) — read-only، masked، 8 بخش (stack containerها، health endpointها، `/api/metrics` probe، scrape-job Prometheus، داشبوردهای Grafana، credential audit masked، production PCT + DB integrity، منابع host) | فایل جدید در commit |
| 7 | **s52 در زمان این گزارش ردیاب نبود** — 5× `ssh: connect to host 172.20.1.52 port 22: Connection timed out` (2026-11-02). **هیچ بخشی از ممیزی s52 اجرا نشد** و هیچ ادعایی از آن نشده است | لاگ ssh (پس از 3 timeout PCM-17، 2 تایم‌اوت دیگر در PCM-18) |
| 8 | آخرین وضعیت s52 با مدرک: چک PCM-16 (2026-10-29) — production سالم، pre-PCM-14D، DB integrity ok | [`گزارش-PCM-16.md`](گزارش-PCM-16.md) |
| 9 | اسکرپت چک PCM-17 ([`deploy/pcm17_s52_readonly_check.sh`](deploy/pcm17_s52_readonly_check.sh)) **همچنان اجرا نشده** — با همان محدودیت s52 | — |
| 10 | working tree تمیز، push بدون force، SHA با `git ls-remote` تأیید شده | بخش G |

## B. ممیزی موجود (baseline audit)

1. **هدف PCM-18:** «ممیزی read-only مانیتورینگ s52 (بدون credential plaintext) + اجرای چک PCM-17 به‌محض دسترسی».
2. **وضعیت پیش از PCM-18:**
   - PCM-17 کامل و push شده (`4b3a84c` + `cd14220`).
   - s52 از 2026-11-02 ساعت 14:19 (3 تایم‌اوت) تا پایان این گزارش (2 تایم‌اوت دیگر) **ردیاب نبود**.
   - زیرساخت مشاهده‌پذیری s52 از PCM-12.3 مستند است (خارج از repo PCT): Prometheus 2.55.0 `:9090`، Grafana 11.3.0 `:3001` (dashboards PCT **خالی** — PCM-10)، Loki 3.2.0 `:3100`، node-exporter `:9100`. یافته‌های امنیتی G-01..G-05 در `docs/PCM-12.3-TEST-ISOLATION.md` §۹ ثبت شده‌اند (رمز plaintext در `datasources.yml` + `GF_SECURITY_ADMIN_PASSWORD` در compose) — این‌ها متعلق به زیرمجموعه‌ی مشترک `observability` هستند و در scope PCT **اصلاح نمی‌شوند**؛ فقط در اسکرپت PCM-18 **بازممیزی masked** می‌شوند تا وضعیت (تغییر/ثابت) ثبت گردد.
   - در repo PCT: هیچ dashboard JSON یا scrape-job برای PCT وجود ندارد (درست — متعلق به PCM-10 روی stack s52).

## C. طراحی / رویه

### C.1 اسکرپت `deploy/pcm18_s52_observability_audit.sh` (جدید)

read-only، masked، بدون login/rotate/restart. 8 بخش:

| # | بخش | خروجی مورد انتظار (pre-PCM-10/17) |
|---|------|-----------------------------------|
| 1 | `docker ps` stack مانیتورینگ (prometheus/grafana/loki/node-exporter/pg-exporter) | همه Up |
| 2 | health endpointهای عمومی بدون credential: prometheus `/-/healthy`+`/-/ready`، grafana `/api/health`، loki `/ready`، node-exporter `/metrics` | 200 |
| 3 | probe `GET /api/metrics` روی backend PCT | **404** (PCM-10 هنوز) |
| 4 | config Prometheus — نام jobها + چک target PCT (masked URL) + `/api/v1/targets` زنده | بدون job PCT |
| 5 | داشبوردهای Grafana — فقط نام‌های فایل‌های JSON + provisioning (paths masked) + `/api/search` بدون auth | بدون داشبورد PCT |
| 6 | **credential audit masked** — همان الگوی PCM-12.3: کلیدها/permissions/نام datasourceها فقط؛ مقدار هیچ رازی چاپ نمی‌شود؛ flag `INLINE-CREDS-ROTATE` اگر URL credential داشته باشد | وضعیت G-01..G-05: ثابت یا rotate شده |
| 7 | production PCT: container + `/dashboard/studio.html` + `PRAGMA integrity_check` + mtime DB + permissions `.env` | سالم |
| 8 | منابع host: disk/RAM/uptime | ثبت |

### C.2 ممیزی محلی (در این گزارش انجام شد — مدرک در بخش D/E)

- اسکن secret روی **تمام فایل‌های tracked** با 8 pattern (private key، AWS، GitHub PAT، Slack، Google API key).
- اسکن `password=/token=` محدود به `deploy/`، `docker-compose.yml`، `dashboard/`، `extension/` — هر hit یکی‌یکی بازبینی شد.
- بررسی `docker-compose.yml` و `.gitignore`.

## D. فایل‌های این مرحله

| فایل | نوع | توضیح |
|------|-----|-------|
| [`deploy/pcm18_s52_observability_audit.sh`](deploy/pcm18_s52_observability_audit.sh) | جدید | ممیزی مشاهده‌پذیری s52 — read-only/masked، 8 بخش، قابل اجرا به‌محض دستیابی |
| [`گزارش-PCM-18.md`](گزارش-PCM-18.md) | جدید | همین گزارش (commit دوم، با SHA نهایی) |

هیچ فایل production/کد دست‌نخورده است (PCM-18 = ممیزی + اسکرپت، بدون تغییر رفتار).

## E. نتایج ممیزی محلی (اجرا شده — با مدرک)

1. **اسکن secret کل repo:** `git grep -nE -e "-----BEGIN" -e "PRIVATE KEY"` و 5 pattern token → **0 hit**.
2. **اسکن `password=/token=`:** 12 hit — همگی الگوی مجاز:
   - `PW=$(grep '^PCT_DASHBOARD_PASSWORD=' … | cut -d= -f2-)` (6 اسکرپت تست/بررسی) — خواندن از `.env` سرور در runtime؛
   - `printf 'PCT_DASHBOARD_PASSWORD=%s\n' "$PW"` / `"$PCT_DASH_PW"` (3 اسکرپت deploy) — **ساختن** `.env` روی سرور از متغیر؛
   - `ENV_PW=$(grep …)` در pcm05 — فقط برای مقایسهٔ قبل/بعد.
   - **هیچ literal credential در هیچ فایل tracked نیست.**
3. **`docker-compose.yml`:** خط 15 = `PCT_DASHBOARD_PASSWORD: ${PCT_DASHBOARD_PASSWORD:-}` — env-var با default خالی + کامنت صریح «Never hardcode the password in this file or the repo». بقیهٔ envها بدون حساسیت (`HOST`, `PORT`, `PCT_DB`, `STATIC_DIR`, `PCT_KNOWLEDGE_DATA_DIR`).
4. **`.gitignore`:** `.env` (خط 9)، `backend/thesaurus.db` + `*.db*` (27–28)، `data/` (34)، `wf-out/` (31, 35) — هیچ داده/رمز از مسیر commit رد نمی‌شود.
5. **`dashboard/` و `extension/`:** بدون هیچ pattern `password=`/`token=` (خروجی اسکن: فقط `deploy/`).
6. **endpoint مانیتورینگ در backend:** `grep metrics|/health|prometheus` در `backend/*.py` — هیچ route `/metrics` یا `/api/health`؛ «metrics» فقط در `factory/models.py`/`quality.py` به‌معنای `QualityReport.metrics` (آمار کیفیت سند — بی‌ربط Prometheus). **نتیجه: PCM-10 هنوز کارِ پیشِ‌رو است و PCM-18 آن را نمی‌سازد** (scope PCM-18 فقط ممیزی read-only + اسکرپت).

## F. وضعیت s52 (محدودیت — صادقانه)

- **5 تایم‌اوت متوالی** `ssh -p 22 saber@172.20.1.52` (3 در PCM-17 ساعت 14:19–14:21 + 2 در PCM-18 ساعت 14:31–14:37، Asia/Tehran): `Connection timed out`.
- بنابراین **بخش‌های 1–8 اسکرپت PCM-18 و چک PCM-17 اجرا نشدند** و در این گزارش هیچ عدد/وضعیتی از s52 ادعا **نمی‌شود**.
- آخرین وضعیت s52 **با مدرک** از چک PCM-16 (2026-10-29): production healthy، pre-PCM-14D (registry/queue endpoints 404)، DB integrity ok، کد s52 قدیمی‌تر از PCM-14C.3/14D/15/16/17.
- **برنامهٔ اقدام به‌محض دسترسی:**
  1. `ssh -p 22 saber@172.20.1.52 "bash -s" < deploy/pcm18_s52_observability_audit.sh`
  2. `ssh -p 22 saber@172.20.1.52 "bash -s" < deploy/pcm17_s52_readonly_check.sh`
  3. ثبت خروجی هر دو در بخش H و به‌روزرسانی این گزارش (commit پیوسته).

## G. Git: commit و push

- **commit کد + اسکرپت:** `f770aff` — بعد از `cd14220`، push بدون force.
- **GitHub:** `https://github.com/saber13812002/persian-corpus-toolkit` — SHA با `git ls-remote` تأیید می‌شود (بخش H).
- این گزارش در **commit دوم بلافاصله بعدی** ثبت می‌شود (رویهٔ PCM-14C.3/14D/15/16/17).
- قبل از commit: `git diff --check` تمیز؛ secret scan (بخش E) → 0 hit واقعی؛ `git status` → فقط فایل‌های PCM-18.

## H. وضعیت Local / GitHub / s52

| محیط | وضعیت |
|------|-------|
| Local | `main` = `f770aff` (commit PCM-18)؛ working tree clean (بعد از commit گزارش) |
| GitHub | همگام با Local (تأیید با `git ls-remote`) |
| s52 | **ردیاب نبود** (5× Connection timed out، 2026-11-02). آخرین وضعیت مدرک‌شده = چک PCM-16 (2026-10-29): pre-14D، سالم. اسکرپت‌های PCM-18 + PCM-17 آماده؛ اجرا — به‌محض دسترسی |

## I. production

- هیچ deploy/restart/تغییری روی s52 انجام **نشد** (s52 حتی ردیاب نبود).
- PCM-18 ذاتاً بدون تغییر است: فقط یک اسکرپت read-only + گزارش.
- deploy آینده (با تأیید مالک) بچ PCM-14C.3+14D+15+16+17 را یکجا حمل می‌کند — همه additive/بدون مهاجرت (مستند در گزارش‌های مرحله‌ای).

## J. ریسک‌ها و محدودیت‌ها

| # | ریسک/محدودیت | اثر | وضعیت |
|---|--------------|-----|-------|
| 1 | s52 ردیاب نیست (شبکه/host) | ممیزی مشاهده‌پذیری + چک PCM-17 انجام نشده | اسکرپت‌ها آماده؛ در PCM-19 یا هر فرصت بعدی اجرا |
| 2 | یافته‌های امنیتی G-01..G-05 (observability — خارج از scope PCT) | تا rotate شدن، رمزها در `datasources.yml`/compose باقی‌اند | **فقط ثبت** — اقدام متعلق به مالک زیرمجموعه‌ی observability (دستور §1: لمس ممنوع) |
| 3 | `/api/metrics` + 4 داشبورد PCT هنوز نیستند | مانیتورینگ PCT در Grafana فعلاً غیرفعال | PCM-10 (پیش‌رو در نقشه‌ی راه) |
| 4 | ES index still «NOT VERIFIED» (از PCM-14C) | — | بدون تغییر؛ در PCM-19 با رسیدن s52 بررسی می‌شود |

## K. راهنمای اپراتور (اجرا به‌محض دستیابی s52)

```bash
# 1) ممیزی مشاهده‌پذیری (read-only، masked):
ssh -p 22 saber@172.20.1.52 "bash -s" < deploy/pcm18_s52_observability_audit.sh

# 2) چک PCM-17 (read-only):
ssh -p 22 saber@172.20.1.52 "bash -s" < deploy/pcm17_s52_readonly_check.sh
```

خروجی هر دو را در بخش H این گزارش ثبت کنید. هیچ‌کدام تغییر ایجاد نمی‌کنند.

رگرسیون (روی هر محیطی با Python 3.10+):

```bash
cd backend && python -m unittest test_api test_projects test_dashboard \
  test_knowledge_api test_word_factory test_dump test_work_registry \
  test_queue test_corpus_builder test_studio_api -v   # 182/182
```

## L. گام بعدی

- **PCM-19:** به‌روزرسانی README/AGENTS/OpenAPI + نمونهٔ REST client سومی + تست قرارداد API + راهنمای اپراتور + GitLab/CI + گزارش نهایی A–I.
- به‌محض دستیابی s52: اجرای هر دو اسکرپت (بخش K) + ثبت خروجی + (در صورت تمایل مالک) برنامه‌ی deploy بچ 14C.3→17 با بکاپ/rollback.

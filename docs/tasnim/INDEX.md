# مستندات «تفسیر تسنیم — کتابخانهٔ دیجیتال» (V1) — نقشهٔ سندها

این فهرست، مجموعهٔ کامل مدارک محصول **تفسیر تسنیم — کتابخانهٔ دیجیتال** (PCM-20.6.4، فاز B15) را به‌همراه سندهای مأموریتی مرتبط می‌آورد. همهٔ اعداد و نمونه‌های این مجموعه از **شواهد واقعی** (build v0003 + سرویس زندهٔ محلی) گرفته‌شده‌اند؛ هیچ عددی ساختگی نیست.

- **نسخهٔ پیکره:** v0003 — `content_sha256 = 40f45e0b2c393a65…`
- **سرویس محلی اثبات‌شده:** 296 تست (293 گذر / 3 skip) + smoke 15/15 + E2E 12/12
- **نقش‌ها:** خوانندهٔ کتاب · توسعه‌دهنده · اپراتور/DevOps · یکپارچه‌ساز (SDK/API)

## ۱. شروع سریع (برای همه)

اگر فقط می‌خواهید کتاب را **بخوانید**، مستقیماً سایت را باز کنید (پس از استقرار). اگر می‌خواهید آن را **روی دستگاه خود اجرا کنید**، سه دستور کافی است:

```bash
# ۱) ساخت read model (فقط اگر قبلاً build نشده باشد)
python -X utf8 -m tasnim.web.build_cli build --corpus <دایرکتوری-پیکره-v0003> --out tasnim/data/readmodel/v0003

# ۲) اجرای سرویس (SSR + API روی 127.0.0.1:5071)
python -X utf8 -m tasnim.web.app --db tasnim/data/readmodel/v0003/tasnim_readmodel.db --port 5071

# ۳) مرور در مرورگر
#    http://127.0.0.1:5071
```

جزئیات: [README.md](README.md) · اجرا با Docker: [DOCKER.md](DOCKER.md)

## ۲. نقشهٔ سندها (۱۵ قلم B15)

| # | قلم (B15) | سند | خلاصهٔ یک‌خطی |
|---|-----------|-----|----------------|
| ۱ | README محصول | [README.md](README.md) | «این چیست؟» + quickstart + چیدمان ریپازیتوری + وضعیت‌ها |
| ۲ | معماری | [../PCM-20.6.4-ARCHITECTURE.md](../PCM-20.6.4-ARCHITECTURE.md) | معماری لایه‌ها، read model، API، خط‌مشی طراحی (سند مأموریتی، موجود از قبل) |
| ۳ | قرارداد داده | [DATA-CONTRACT.md](DATA-CONTRACT.md) | حقایق پیکرهٔ v0003، کلید `page_id`، `item_index` در برابر `barg`، وضعیت‌های کیفیت، HP-1، schema کامل، invariants build، زنجیرهٔ SHA |
| ۴ | مرجع API | [API-REFERENCE.md](API-REFERENCE.md) | هر ۱۲ endpoint با نمونهٔ **واقعی** request/response، قرارداد خطا، صفحه‌بندی، ETag/Cache، rate limit |
| ۵ | OpenAPI/Swagger | [tasnim/web/openapi.py](../../tasnim/web/openapi.py) (منبع) | spec 3.1.0 سروشده در `/api/v1/tasnim/openapi.json` + پوستهٔ آفلاین `/docs` (14 path، 3 schema) |
| ۶ | استقرار | [DEPLOYMENT.md](DEPLOYMENT.md) | دامنهٔ هدف `tasnim.ai.ismc.ir` (DNS-ready، unprovisioned — با شواهد)، طرح shared-ingress، اجرای محلی/production، rollback |
| ۷ | Docker | [DOCKER.md](DOCKER.md) | چیدمان compose، دستورات build/run/stop، **وضعیت صادقانه: اجرای Docker روی این هاست BLOCKED** (binary ندارد)، troubleshooting |
| ۸ | راهنمای توسعه‌دهنده | [DEVELOPER.md](DEVELOPER.md) | چیدمان ریپازیتوری، دستور دقیق ۱۰ سویت تست، harness، افزودن endpoint/صفحه، FTS5 فارسی، نکات Windows، rebuild |
| ۹ | یکپارچه‌سازی سومی | [../PCM-20.6.4-INTEGRATION.md](../PCM-20.6.4-INTEGRATION.md) | SDKهای Python/JS + نمونه‌ها + احراز زنده (سند مأموریتی، موجود از قبل) |
| ۱۰ | راهنمای کاربر (فارسی) | [USER-GUIDE-FA.md](USER-GUIDE-FA.md) | خواندن صفحه، prev/next، شکاف‌های «در دست بازیابی»، جستجو، موضوعات، جلد‌ها، بج‌های کیفیت، چاپ، حالت تاریک |
| ۱۱ | Runbook عملیات | [OPS-RUNBOOK.md](OPS-RUNBOOK.md) | کارهای روزانه/هفتگی، تعویض نسخهٔ read model (v0004)، ریست rate-limit، فضای دیسک، مانیتورینگ، پاسخ به حادثه |
| ۱۲ | بک‌آپ و بازیابی | [BACKUP-RESTORE.md](BACKUP-RESTORE.md) | چه چیزی بک‌آپ شود، دستورات، **تصدیهٔ بازیابی با SHA + smoke**، سناریوهای rollback |
| ۱۳ | گزارش تست | [TEST-REPORT.md](TEST-REPORT.md) | جداول کامل: ۱۰ سویت / 296 تست، smoke 15/15، E2E 12/12، شواهد curl، ۴ باگ پیداشده + فکس، روش بازتولید |
| ۱۴ | امنیت | [SECURITY.md](SECURITY.md) | مدل تهدید، HP-1 (۴ لایه + تست‌ها)، rate limiting، CORS، نشت‌ناپذیری خطاها، SVG cover، فونت OFL، محدودیت‌های شناخته‌شده |
| ۱۵ | نقشهٔ راه | [ROADMAP.md](ROADMAP.md) | V1 تحویل‌شده · V1.5 (دامنه، Docker-host، surah index، stemming/ICU) · V2 (backfill→v0004، RAG با citation، cover واقعی) |

## ۳. سندهای مکمل

| سند | توضیح |
|-----|-------|
| [WIKI-IMPORT.md](WIKI-IMPORT.md) | نقشهٔ انتقال این ۱۵ سند به Wiki.js (دستاور `docs.ai.ismc.ir`) + **نتیجهٔ بررسی دسترسی: BLOCKED** (API v2 غیرفعال، بدون creds) + چک‌لیست |
| [../PCM-20.6.3-BACKFILL-DESIGN.md](../PCM-20.6.3-BACKFILL-DESIGN.md) | طراحی backfill (Track A) برای 45,243 صفحهٔ مفقوده — وضعیت READY_FOR_APPROVAL |
| [../PCM-20.6-CORPUS-V0003.md](../PCM-20.6-CORPUS-V0003.md) | سند پیکرهٔ canonical v0003 (ساختار، SHAها، گیت‌ها) |
| [../PCM-20.6.0-RECON.md](../PCM-20.6.0-RECON.md) | شناخت (RECON) زیرساخت: ingress، دامنه‌ها، پرت‌ها (فایل روی main است؛ لینک بعد از merge با main اعتبار دارد) |

## ۴. چیدمان فایل‌های کلیدی

```text
tasnim/
  web/            # SSR + API + build CLI (Flask؛ dependency: فقط Flask 3.1.3)
  e2e/            # smoke.py (15 check) + e2e_scenario.py (12 step) + screenshots/
  sdk/python/     # کلاینت Python (stdlib فقط؛ 23/23)
  sdk/javascript/ # کلاینت JS ESM (بدون dependency؛ 22/22)
  Dockerfile      # python:3.12-slim + Flask==3.1.3، user non-root، healthcheck
  docker-compose.tasnim.yml   # tasnim-api (5071) + tasnim-web (nginx, 5070)
  nginx/tasnim.conf           # reverse proxy 5070 → 5071
  data/readmodel/v0003/       # read model ساخته‌شده (gitignored؛ 260 MB)
docs/tasnim/      # ← این مجموعهٔ مستندات
```

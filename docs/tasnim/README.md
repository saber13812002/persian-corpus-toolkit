# تفسیر تسنیم — کتابخانهٔ دیجیتال (V1)

**تفسیر تسنیم** (مؤلف: آیت‌الله مصطفی همتی شاهرودی) به‌صورت یک **کتابخانهٔ دیجیتال فارسی** با کیفیت خوانندگی بالا ارائه می‌شود: 45,844 صفحه از پیکرهٔ canonical **v0003**، در 6 جلد شناسایی‌شده، با جستجوی تمام‌متن فارسی، ناوبری صفحه‌به‌صفحه (Previous/Next) با نمایش صادقانهٔ شکاف‌ها، فهرست موضوعات استخراج‌شده و نشان‌های کیفیت.

سایت **SSR** است (صفحه‌های کوچک، بدون dependency جانبی، offline-first) و یک **API خواندنی** REST با قرارداد خطای یکدست و OpenAPI 3.1 دارد.

> **امید مهم:** همهٔ اعداد این مستند از read model واقعی v0003 و سرویس محلی زنده گرفته‌اند؛ هیچ آمار ساختگی نیست (قاعدهٔ AGENTS.md §۲.۹).

## کل ارقام v0003 (از `build_meta` + read model زنده)

| کمیت | مقدار | منبع |
|------|-------|------|
| صفحات | **45,844** | `build_meta.page_count` |
| جلد (volume) شناسایی‌شده | **6** (شامل ۱ «نامشخص») | جدول `volumes` |
| هدر (heading) | **10,739** | `build_meta.heading_count` |
| موضوعات متمایز (بعد از normalize) | **1,080** | `build_meta.topic_count` |
| پوشش موجود (present_ratio) | **0.5033** = 45,844 / (45,844 + 45,243) | `GET /catalog` — 45,243 صفحهٔ مفقود = 6 بازهٔ `backfill_pending` |
| وضعیت RAG | `not_connected` (صريح) | همهٔ پاسخ‌ها |

## شروع سریع (۳ دستور)

```bash
# ۱) ساخت read model — فقط اگر هنوز build نشده باشد (خروجی: ~260 MB)
python -X utf8 -m tasnim.web.build_cli build \
  --corpus <دایرکتوری-پیکره-v0003> \
  --out tasnim/data/readmodel/v0003

# ۲) اجرای سرویس: SSR + API روی 127.0.0.1:5071
python -X utf8 -m tasnim.web.app \
  --db tasnim/data/readmodel/v0003/tasnim_readmodel.db \
  --port 5071

# ۳) باز کردن در مرورگر
#    http://127.0.0.1:5071
```

> **نکتهٔ شفافیت:** درخت منبع پیکرهٔ v0003 (فایل‌های `pages.jsonl`، `heading-records.jsonl`، `corpus.json`، `manifest.json`) در **worktree فعلی نیست** (کپی canonical روی s52/خط لولهٔ PCM-20.3 قرار دارد)؛ به همین دلیل دستور ۱ فقط در محیطی که آن درخت در دسترس است اجرا می‌شود. خود read model ساخته‌شده (v0003) در `tasnim/data/readmodel/v0003/` موجود است و دستور ۲ همین‌جا قابل اجراست. برای جایگزینی/بازیابی: [BACKUP-RESTORE.md](BACKUP-RESTORE.md) و [OPS-RUNBOOK.md](OPS-RUNBOOK.md).

اجرا با Docker (برای میزبان دارای Docker): [DOCKER.md](DOCKER.md) — توجه: روی workstation توسعهٔ فعلی **binary Docker نصب نیست** (شواهد در همان سند).

## چه چیزی برای خواننده هست؟

- **خواندن صفحه:** متن کامل صفحه با فونت Noto Naskh، شمارهٔ `item_index`، برگهٔ چاپی (`barg`)، جلد و section؛ دکمه‌های Previous/Next.
- **شکاف‌ها به‌صورت صادقانه:** برای 6 بازهٔ صفحهٔ موجودنیست (مثل `3649–11182`) سایت صفحهٔ «این صفحه در دست بازیابی است» می‌نویسد و نزدیک‌ترین صفحات موجود را پیشنهاد می‌دهد؛ هیچ متن ساختگی نمی‌گذارد.
- **جستجوی فارسی:** جستجوی پیشوندی روی 45,844 صفحه (مثال واقعی: «قرآن» → **6,760** صفحه).
- **موضوعات:** 1,080 موضوع استخراج‌شده از 10,739 هدر (مثل «تفسیر» 1,678 صفحه) با صفحهٔ جزئیات.
- **جلد‌ها:** 6 کارت جلد با بازهٔ `item_index` و شمارهٔ صفحات؛ جلد «نامشخص» با بج «در حال بازیابی شمارهٔ جلد».
- **سوره‌ها:** صادقانه `not_supported` (0/114 در v0003) — صفحهٔ /surahs دلیل فنی را توضیح می‌دهد؛ ساخت دادهٔ ساختگی ممنوع است.
- **کیفیت:** نشان‌های `short` / `empty` / `truncated_at_2000` / `dup_item_index` کنار هر صفحه (تعریف: [DATA-CONTRACT.md](DATA-CONTRACT.md)).
- **حالت تاریک + چاپ:** theme toggle و CSS print.
- **دربارهٔ داده (provenance):** صفحهٔ /about SHA256 پیکره و read model و وضعیت کیفیت را نمایش می‌دهد.

## چیدمان ریپازیتوری (بخش‌های مرتبط)

```text
tasnim/
  web/            # Flask app: SSR (templates/ + static/) + API (api.py) +
                  #   read model (readmodel.py) + build CLI (build_cli.py) +
                  #   OpenAPI 3.1 (openapi.py) + cover SVG (cover.py)
  e2e/            # smoke.py (15 check) + e2e_scenario.py (12 step) + screenshots/
  sdk/python/     # کلاینت Python (stdlib؛ 23/23 تست)
  sdk/javascript/ # کلاینت JS ESM (بدون dependency؛ 22/22 تست)
  Dockerfile + docker-compose.tasnim.yml + nginx/tasnim.conf
  data/readmodel/v0003/   # read model ساخته‌شده (gitignored؛ 260.8 MB)
docs/tasnim/      # ← این مجموعهٔ مستندات (15 قلم؛ نقشه: INDEX.md)
corpus/tasnim/    # خط لولهٔ ساخت پیکره (PCM-20.3) + backfill (PCM-20.6.3)
test_tasnim_*.py  # 10 سویت تست در ریشهٔ ریپازیتوری (296 تست)
```

## وضعیت‌ها (صادقانه، تاریخ 2026-11-07)

| قلم | وضعیت | یادداشت |
|-----|--------|---------|
| اجرای محلی (SSR+API) | ✅ آماده | `tasnim/data/readmodel/v0003` موجود؛ smoke 15/15 روی 5070/5071 |
| تست‌های رگرسیون | ✅ 296 تست (293 گذر، 3 skip) | skipها به‌دلیل نبود دادهٔ واقعی v0003 در worktree — جزئیات: [TEST-REPORT.md](TEST-REPORT.md) |
| OpenAPI + Swagger آفلاین | ✅ `/api/v1/tasnim/openapi.json` + `/docs` | spec 3.1.0، 14 path |
| دامنهٔ `tasnim.ai.ismc.ir` | ⛔ BLOCKED | DNS-ready (A=185.213.10.25) اما vhost/cert ندارد — **طرح بدون اجرا** در [DEPLOYMENT.md](DEPLOYMENT.md) |
| اجرای Docker | ⛔ BLOCKED (این هاست) | binary Docker روی workstation نیست — دستورات و طرح کامل در [DOCKER.md](DOCKER.md) |
| GitLab (2222) | ⏳ UNKNOWN | از workstation TIME OUT؛ deploy/commit جزو فاز ۷ |
| backfill 45,243 صفحهٔ مفقوده | ⏳ READY_FOR_APPROVAL | PCM-20.6.3 — اجرا بدون تأیید انسانی ممنوع (AGENTS.md §۲) |

## مستندات

نقشهٔ کامل 15 قلم: [INDEX.md](INDEX.md). مهم‌ترین‌ها:

- [USER-GUIDE-FA.md](USER-GUIDE-FA.md) — راهنمای خواننده (فارسی، بدون اصطلاحات)
- [API-REFERENCE.md](API-REFERENCE.md) — مرجع کامل API با نمونه‌های واقعی
- [DATA-CONTRACT.md](DATA-CONTRACT.md) — قرارداد داده و read model
- [DEPLOYMENT.md](DEPLOYMENT.md) · [DOCKER.md](DOCKER.md) — استقرار
- [OPS-RUNBOOK.md](OPS-RUNBOOK.md) · [BACKUP-RESTORE.md](BACKUP-RESTORE.md) — عملیات
- [SECURITY.md](SECURITY.md) — مدل تهدید و کنترل‌ها
- [TEST-REPORT.md](TEST-REPORT.md) — گزارش کامل شواهد تست
- [ROADMAP.md](ROADMAP.md) — V1.5 / V2

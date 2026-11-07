# نقشهٔ راه — Tasnim Web

> PCM-20.6.4 · سند B15 · 2026-11-07
> نقشهٔ مادر: [INDEX.md](INDEX.md)

---

## V1 — تحویل‌شده (2026-11-07)

همهٔ موارد زیر **ساخته و تست‌شده** هستند (شواهد: [TEST-REPORT.md](TEST-REPORT.md)):

| مورد | وضعیت |
|---|---|
| read model v0003 (45,844 صفحه، 6 جلد، 10,739 هدر، 1,080 موضوع) | ✅ |
| 12 endpoint JSON (`/api/v1/tasnim/*`) + OpenAPI 3.1.0 + `/docs` | ✅ |
| 10 صفحهٔ SSR فارسی RTL (خانه، جلد‌ها، صفحه، جستجو، موضوعات، سوره‌ها، درباره، خطا) | ✅ |
| جستجوی فارسی FTS5 (6,760 نتیجه برای «قرآن») + صفحه‌بندی + فیلتر جلد | ✅ |
| rate-limit + ETag/304 + envelope خطا (فارسی) | ✅ |
| HP-1 (جداسازی hidden context، 4 لایه + canary test) | ✅ |
| smoke 15/15 + E2E 12/12 + 296 تست (293 سبز / 3 skip داده‌ای) | ✅ |
| SDK Python (23/23 live + CLI) + SDK JS (22/22 live) | ✅ |
| Docker stack (Dockerfile + compose + nginx) — **طراحی + بازبینی** | ✅ code / ⛔ اجرا (این host Docker ندارد) |
| استقرار `tasnim.ai.ismc.ir` | ⛔ **در انتظار تأیید مالک ingress** ([DEPLOYMENT.md](DEPLOYMENT.md)) |

---

## V1.5 — نزدیک (بستگی به تأییدها/دسترسی‌ها)

### 1. Provisioning دامنه‌ی `tasnim.ai.ismc.ir`
- **توضیح**: گواهی Let's Encrypt برای hostname دقیق + route در Kong → `127.0.0.1:5070`
- **اولویت**: بالا (مهم‌ترین مانع go-live)
- **وابستگی**: تأیید صریح مالک ingress + دسترسی کنسول Kong
- **مورد قبولی**: `curl https://tasnim.ai.ismc.ir/api/v1/tasnim/health` → 200 + smoke 15/15 از خارج
- **rollback**: حذف route (≈ ۲ دقیقه)

### 2. اجرای واقعی Docker روی host دارای Docker
- **توضیح**: `docker compose -f tasnim/docker-compose.tasnim.yml up -d --build` + smoke 15/15 روی `:5070`
- **اولویت**: بالا (قبل از go-live، برای اطمینان از هم‌خوانی stack)
- **وابستگی**: host با Docker ≥ 24 (مثلاً s53 یا host میزبان)
- **مورد قبولی**: خروجی `docker compose ps` + hash image + smoke سبز، ثبت در [TEST-REPORT.md](TEST-REPORT.md)
- **سند**: [DOCKER.md](DOCKER.md) §7

### 3. ارزیابی stemming/ICU برای جستجوی فارسی
- **توضیح**: ارزیابی Persica/ICU stemming + index دوطرفه؛ تصمیم: آیا ارزش rebuild read model دارد؟
- **اولویت**: متوسط (تأثیر مستقیم بر کیفیت جستجو — محدودیت فعلی در [USER-GUIDE-FA.md](USER-GUIDE-FA.md) §3)
- **وابستگی**: وقت dev + fixture تطبیق‌یابی (نمونهٔ query واقعی + انتظار)
- **مورد قبولی**: گزارش A/B: precision/recall پیش/پس در یک set query نمونه؛ اگر مثبت → item V2 «rebuild با tokenizer جدید»
- **تأثیر**: اگر مثبت، `tokenizer_version` در build_meta تغییر می‌کند و یک build جدید (v0005+) لازم است

### 4. (اختیاری) index سوره‌ها در سطح text
- **توضیح**: شناسایی مارکرهای سوره روی متن (در v0003: 0 فیلد surah، 0 هدر سخت از 10,739، 265 هدر شل — شواهد در [API-REFERENCE.md](API-REFERENCE.md) `/surahs`)
- **اولویت**: متوسط (امروز 503 صادقانه برمی‌گردانیم)
- **وابستگی**: یا یک pass جدید روی متن (اگر مارکر قابل‌اعتماد پیدا شود) یا backfill (item V2)
- **مورد قبولی**: ≥ 114 سوره با حداقل یک صفحهٔ مطمئن + تست؛ `/surahs` → 200

### 5. (اختیاری) CSP header + HSTS روی nginx
- **توضیح**: `Content-Security-Policy` (خروجی ما third-party script ندارد؛ CSP سخت ساده است) + HSTS روی ingress
- **اولویت**: پایین (افزایش دفاع، نه رفع حفره)
- **مورد قبولی**: headerها در پاسخ واقعی + smoke سبز

---

## V2 — بعد از تأیید backfill

### 1. Backfill صفحات در دست بازیابی (PCM-20.6.3) → v0004 → سواپ
- **توضیح**: 45,243 صفحهٔ شکاف‌دار با re-crawl زنده از منبع (برنامهٔ کامل: [../PCM-20.6.3-BACKFILL-DESIGN.md](../PCM-20.6.3-BACKFILL-DESIGN.md) — policy bf-2، 28 تست BF01–BF22b، READY_FOR_APPROVAL)
- **اولویت**: بالا‌ترین item V2 (تکمیل 50٪ کتاب)
- **وابستگی‌های سخت (Gate B)**:
  - ⛔ s52 online (اکنون آفلاین)
  - ⛔ **تأیید صریح انسانی** (`BACKFILL_APPROVED=approved` + `--allow-live`)
  - ≤ 10 live probe قبل از run کامل؛ توقف خودکار با هر 5xx
- **برآورد** (از سند طراحی): 45,243 صفحه @ 4 pg/min ≈ **188.5 ساعت ≈ 7.9 روز ≈ 91 run** با budget 500/run
- **مورد قبولی**:
  - v0004 build شده + SHA + smoke سبز روی v0004
  - سواپ طبق [OPS-RUNBOOK.md](OPS-RUNBOOK.md) §7 + rollback test
  - `statistics` جدید (page_count ↑، missing ↓) + آپدیت [DATA-CONTRACT.md](DATA-CONTRACT.md)
- **تأکید**: تا تأیید صریح انسانی، **هیچ** probe زنده‌ای اجرا نمی‌شود (قاعدهٔ سخت AGENTS.md)

### 2. RAG با citation (اتصال به زیرسیستم RAG)
- **توضیح**: امروز `rag_status: not_connected` (در build_meta + API). اتصال read model به RAG indexer با **citation به page_id + source_url**
- **اولویت**: بالا (ارزش اصلی «کتابخانه + پاسخ با منبع»)
- **وابستگی**: زیرسیستم RAG (زیرمجموعهٔ دیگر — خارج از scope این repo؛ هماهنگی لازم)
- **مورد قبولی**: پاسخ RAG با حداقل یک citation قابل‌پیمایش (page_id → صفحهٔ واقعی) + تست

### 3. (اختیاری) حساب کاربری (bookmarks/annot)
- **توضیح**: افزودن state کاربری — **معماری فعلی stateless است**؛ این یک تغییر بزرگ است (auth، DB نوشتاری، scope جدید)
- **اولویت**: پایین (فقط اگر demand واقعی باشد)
- **وابستگی**: تصمیم محصول + auth pattern (احتمالاً هم‌الگو با auth داشبورد (PCM-09))
- **تأکید امنیتی**: اگر اضافه شد، rate-limit/ETag/HP-1 باید بازمعماری شوند (state ≠ read-only)

### 4. (اختیاری) کاورهای واقعی
- **توضیح**: جایگزینی SVG برنامه‌ای با تصویر واقعی جلد (اگر منبع معتبر پیدا شود)
- **اولویت**: پایین
- **قاعدهٔ سخت**: تا آن زمان، **کاور/تصویر ساختگی نداریم** (AGENTS.md §2) — SVG + badge می‌ماند

---

## ترتیب پیشنهادی اجرا

```text
V1.5.1  Docker روی host واقعی        (فنی، بدون تأیید خارجی)
V1.5.2  Provisioning دامنه + go-live  (تأیید مالک ingress)
V1.5.3  ارزیابی stemming              (تصمیم‌ساز برای V2)
─────────────────────────────────────────────
V2.1    Backfill (Gate B: تأیید انسان + s52 online) → v0004 → سواپ
V2.2    RAG با citation
V2.3+   (اختیاری) index سوره / حساب / کاور واقعی
```

**قاعدهٔ طلایی**: هر item با «تست → commit → deploy → smoke → گزارش» (AGENTS.md §2-4) و بدون آمار ساختگی.

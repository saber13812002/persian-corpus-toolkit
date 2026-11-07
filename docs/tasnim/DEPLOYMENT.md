# استقرار و دپلوی — Tasnim Web V1

> PCM-20.6.4 · سند B15 · 2026-11-07
> نقشهٔ مادر: [INDEX.md](INDEX.md) · معماری کامل: [../PCM-20.6.4-ARCHITECTURE.md](../PCM-20.6.4-ARCHITECTURE.md)

این سند **برنامهٔ** استقرار است. وضعیت فعلی: **طراحی کامل، اجرا در انتظار تأیید مالک ingress** — هیچ DNS، گواهی یا پروکسی‌ای تاکنون تغییر نیافته است.

---

## ۱. وضعیت فعلی (با شواهد)

| مورد | وضعیت | مدرک |
|---|---|---|
| دامنهٔ هدف `tasnim.ai.ismc.ir` | **DNS-ready، provision نشده** | 2026-11-07: DNS A = `185.213.10.25` (همان edge IP شبکهٔ ismc.ir؛ همان IP که `docs.ai.ismc.ir` را سرو می‌کند). TLS با verify → `SSLCertVerificationError(1, "[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: Hostname mismatch, certificate is not valid for 'tasnim.ai.ismc.ir'. (_ssl.c:1082)")` — یعنی ترافیک به edge می‌رسد ولی vhost این دامنه وجود ندارد و گواهی پیش‌فرض (CN=`admin.ai.ismc.ir`) برمی‌گردد. |
| ingress مشترک | Kong + Tyk + cloudflared (مستندات در [../PCM-20.6.0-RECON.md](../PCM-20.6.0-RECON.md) §6 — فایل روی main است، در این branch نیست) | گواهی پیش‌فرض Let's Encrypt برای CN=admin.ai.ismc.ir؛ route اختصاصی برای تسنیم **وجود ندارد** |
| اجرای محلی / توسعه | ✅ کار می‌کند | سرور Flask مستقیم روی `127.0.0.1:5071` با smoke 15/15 (سند: [TEST-REPORT.md](TEST-REPORT.md)) |
| Docker | ⛔ در این host قابل اجرا نیست (این host Docker ندارد) | [DOCKER.md](DOCKER.md) |
| s52 (سرور corpus) | ⛔ آفلاین در زمان این مأموریت | فقط برای backfill بعدی؛ **نیاز برای V1 نیست** |

**نتیجه:** V1 به‌طور کامل آماده است و تنها مانع، **تأیید و اجرای گام‌های ingress توسط مالک ingress** است (سطح سازمانی، خارج از این repo).

---

## ۲. برنامهٔ ingress مشترک (فقط برنامه — اجرای آن نیازمند تأیید مالک ingress است)

هدف: `https://tasnim.ai.ismc.ir` → سرور داخلی `:5070` روی host میزبان.

### ۲.۱ گام‌ها (مطابق بخش 7.3 [ARCHITECTURE](../PCM-20.6.4-ARCHITECTURE.md))

1. **گواهی Let's Encrypt برای hostname دقیق** `tasnim.ai.ismc.ir`
   - wildcard در V1 لازم نیست (نام دامنهٔ بعدی در صحنه نیست).
   - به‌محض ایجاد route، LE برای این hostname صادر می‌شود (پنجرهٔ برتری: اگر ingress از DNS-01/challenge برتر استفاده می‌کند، owner آن را تنظیم می‌کند).
2. **Route در Kong**: host `tasnim.ai.ismc.ir` → upstream `127.0.0.1:5070`
   - headerها: `X-Forwarded-Proto https` (الزامی — API برای request_id/ETag به آن اعتماد می‌کند)
   - `X-Forwarded-For` به‌صورت append-only (nginx ما همین کار را برای upstream داخلی انجام می‌دهد)
3. **Smoke test پس از route**:
   ```bash
   curl -sS https://tasnim.ai.ismc.ir/api/v1/tasnim/health
   # انتظار: HTTP 200 + "status":"ok" + readmodel.version="v0003"
   curl -sS https://tasnim.ai.ismc.ir/ | head -c 200
   # انتظار: HTML صفحهٔ خانه با `dir="rtl"` و `<html lang="fa">`
   ```
4. **بازگشت به عقب (rollback)**: حذف route از Kong (≈ ۲ دقیقه). گواهی LE می‌ماند (ضرر ندارد). هیچ‌چیز دیگر تغییر نمی‌کند.
5. **پس از بالا آمدن**: اجرای smoke کامل از خارج (همان ۱۵ چک [smoke.py](../../tasnim/e2e/smoke.py) با `--base https://tasnim.ai.ismc.ir`) و ثبت نتیجه در [TEST-REPORT.md](TEST-REPORT.md).

### ۲.۲ چه چیزی در V1 انجام **نمی‌شود** (صریح)

- ❌ هیچ تغییر DNS (record A وجود دارد و دست نمی‌خورد)
- ❌ هیچ گواهی‌ای صادر یا جایگزین نمی‌شود
- ❌ هیچ proxy/firewall در این repo یا این host تغییر نمی‌کند
- ❌ wildcard certificate یا route دوم

### ۲.۳ شرایط پیش‌نیاز مالک ingress

- دسترسی کنسول Kong (route + upstream)
- تأیید صریح برای صدور LE برای `tasnim.ai.ismc.ir`
- تأیید که upstream `127.0.0.1:5070` روی host میزبان سرو می‌شود

---

## ۳. اجرای محلی / توسعه (الان، بدون تأیید هیچ‌کس)

### ۳.۱ سرور مستقیم (ساده‌ترین)

```bash
# از ریشهٔ repo:
python -X utf8 -m tasnim.web.app \
  --db tasnim/data/readmodel/v0003/tasnim_readmodel.db \
  --port 5071
# سپس:
#   web   → http://127.0.0.1:5071/
#   API   → http://127.0.0.1:5071/api/v1/tasnim/health
```

گزینه‌های [app.py](../../tasnim/web/app.py): `--db` (الزامی؛ پیش‌فرض `$TASNIM_DB_PATH`)، `--port` (پیش‌فرض 5071)، `--host` (پیش‌فرض 127.0.0.1)، `--rate-db` (پیش‌فرض `tasnim_rate_limits.db` در کنار read model؛ برای تست جدا پیشنهاد می‌شود: `--rate-db .tmp_phase6/ratelimit.db`).

### ۳.۲ smoke test

```bash
python -X utf8 -m tasnim.e2e.smoke --base http://127.0.0.1:5071
# انتظار: 15 PASS / 0 FAIL
```

جزئیات هر ۱۵ چک: [TEST-REPORT.md](TEST-REPORT.md) §3.

### ۳.۳ با Docker (روی host دارای Docker)

```bash
docker compose -f tasnim/docker-compose.tasnim.yml up -d --build
# web → http://127.0.0.1:5070/   (nginx)
# api → http://127.0.0.1:5071/   (فقط از داخل network)
```

⚠️ در این host (BAKHTIARI-VM) Docker موجود نیست — اجرای واقعی Docker روی host دیگر لازم است. جزئیات: [DOCKER.md](DOCKER.md).

---

## ۴. برنامهٔ پورت‌ها

| پورت | جهت | سرویس | توضیح |
|---|---|---|---|
| **5070** | عمومی (از طریق ingress) | nginx `tasnim-web` | تنها پورتی که ingress می‌بیند؛ در compose فقط publish روی `5070:5070` |
| **5071** | داخلی | Flask `tasnim-api` | بدون publish؛ فقط در network `tasnim-net` |
| 5079 | موقت/تست | — | فقط برای تست‌های این مأموریت رزرو شد؛ **بخش inventory پورت‌های s53 را ببینید** و هرگز به‌طور دائمی استفاده نشود |

پورت‌های اشغال‌شدهٔ شناخته‌شده که باید اجتناب شود (مستندسازی در [../PCM-20.6-BASELINE.md](../PCM-20.6-BASELINE.md)): 4000/4001, 11434, 8000/8001, 7474/7687, 6333, 9001, 8033/8034, 8003–8054, 5436–5477, 8290؛ 5055 = backend اصلی.

---

## ۵. مأموریت production (وقتی تأیید شد)

معماری production = **compose stack روی host میزبان** + ingress سازمانی. الگوی بک‌آپ/verify مطابق AGENTS.md §3 سازمان:

### ۵.۱ پیش از deploy

1. **بک‌آپ**: کپی `tasnim/data/readmodel/v0003/` (DB + sidecar + covers) + `tar` stack.
2. **verify**: `sha256sum` فایل‌های بک‌آپ را با [build.sha256](../../tasnim/data/readmodel/v0003/build.sha256) مقایسه.
3. **تست سبز**: رگرسیون 296 + smoke 15/15 روی کد جدید (قانون: بدون تست سبز، deploy نمی‌شود).

### ۵.۲ deploy

```bash
# روی host میزبان:
docker compose -f tasnim/docker-compose.tasnim.yml build tasnim-api
docker compose -f tasnim/docker-compose.tasnim.yml up -d tasnim-api
# ⛔ docker compose down -v ممنوع (حذف volume = حذف state rate-limit)
```

### ۵.۳ پس از deploy

1. health-wait تا `service_healthy` (healthcheck: 30s start_period / 10s interval / 20s timeout / 3 retries).
2. smoke: ۱۵ چک `smoke.py --base http://127.0.0.1:5070` و بعد `--base https://tasnim.ai.ismc.ir`.
3. ثبت نتیجه در گزارش مأموریت + آپدیت جدول وضعیت [README.md](README.md).

### ۵.۴ rollback

- **rollback کد**: `docker compose ... up -d tasnim-api` با image قبلی (image tag تاریخ‌دار نگه دارید).
- **rollback ingress**: حذف route (≈ ۲ دقیقه).
- **rollback read model**: هیچ‌وقت DB فعلی را جابجا نکنید؛ همیشه نسخهٔ جدید در دایرکتوری جدید (v0004, ...) ساخته شود و با تغییر `TASNIM_DB_PATH` سواپ شود. جزئیات: [DATA-CONTRACT.md](DATA-CONTRACT.md) §swap + [BACKUP-RESTORE.md](BACKUP-RESTORE.md).

---

## ۶. چک‌لیست پیش از go-live

- [ ] smoke 15/15 روی `http://127.0.0.1:5070` (nginx)
- [ ] smoke 15/15 روی `https://tasnim.ai.ismc.ir` (از خارج)
- [ ] rate-limit از IP واقعی (خارجی) تست شده (429 با `Retry-After`)
- [ ] صفحهٔ 404 / 429 / 503 در مرورگر واقعی دیده شده (فارسی، بدون نشت stack trace)
- [ ] ETag 304 از خارج (با `If-None-Match`)
- [ ] font بارگذاری می‌شود (`/static/fonts/noto-naskh-arabic.ttf`, >10KB)
- [ ] بک‌آپ قبل از deploy گرفته و verify شده
- [ ] route ingress + گواهی LE فعال و قابل rollback

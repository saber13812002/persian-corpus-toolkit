# Docker — Tasnim Web V1

> PCM-20.6.4 · سند B15 · 2026-11-07
> نقشهٔ مادر: [INDEX.md](INDEX.md) · استقرار: [DEPLOYMENT.md](DEPLOYMENT.md)

---

## ۰. وضعیت صادقانهٔ اجرا (مهم)

**این stack در host جاری (BAKHTIARI-VM) اجرا نشده است، چون این host اصلاً Docker ندارد.** مدرک (اجرا شده 2026-11-07 روی همان host که روی آن V1 توسعه یافته):

```text
$ docker --version
'docker' is not recognized as an internal or external command, operable program or batch file.
$ docker-compose --version
'docker-compose' is not recognized as an internal or external command, operable program or batch file.
```

بنابراین:

- ✅ **کدهای Docker** (Dockerfile + compose + nginx conf) در repo هستند و بازبینی‌شده‌اند.
- ✅ **سازگاری کامل** با اجرای مستقیم محلی اثبات شده است: همان `app.py` روی `127.0.0.1:5071` اجرا شد و smoke 15/15 سبز شد (سند: [TEST-REPORT.md](TEST-REPORT.md)).
- ⛔ **build/run واقعی image** روی host دارای Docker لازم است (گام صریح V1.5 در [ROADMAP.md](ROADMAP.md)).

یعنی هیچ «test سبز Docker» ادعا **نمی‌شود**؛ آنچه سبز است، اجرای مستقیم همان پروسه‌ای است که Docker آن را wrap می‌کند.

---

## ۱. چیدمان stack

فایل: [tasnim/docker-compose.tasnim.yml](../../tasnim/docker-compose.tasnim.yml) (`name: tasnim-web-v1`)

| سرویس | image | پورت | نقش |
|---|---|---|---|
| `tasnim-api` | build از `./tasnim` → tag `tasnim-api:pcm2064` | **بدون publish** (فقط در network `tasnim-net` روی 5071) | Flask read-model server |
| `tasnim-web` | `nginx:1.27-alpine` | `5070:5070` (تنها پورت عمومی) | reverse proxy + SSR static + security headers |

اتصال: `tasnim-web` روی `depends_on: tasnim-api (condition: service_healthy)` — nginx تا healthy شدن API بالا نمی‌آید.

### volumes

| volume | mount | توضیح |
|---|---|---|
| bind: `./tasnim/data/readmodel/v0003` → `/data/readmodel` | **read-only** | read model v0003 — container هرگز نمی‌تواند آن را لمس کند |
| named: `tasnim_runtime` → `/var/tasnim` | read/write | DB rate-limit (`ratelimit.db`) + هر state اجرایی |

### healthcheckها

| سرویس | دستور | start_period / interval / timeout / retries |
|---|---|---|
| `tasnim-api` | `python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:5071/health'...)"` (urllib → `/health` از داخل) | 30s / 10s / 20s / 3 |
| `tasnim-web` | `wget -q --spider http://127.0.0.1:5070/api/v1/tasnim/health` | 30s / 10s / **15s** / 3 |

### network

- `tasnim-net` — bridge اختصاصی stack؛ هیچ‌کس از بیرون نمی‌تواند مستقیم به `tasnim-api:5071` برسد.

### قوانین سخت

- ⛔ **`docker compose down -v` ممنوع** — volume `tasnim_runtime` حاوی state rate-limit است و حذف آن با `down` (بدون `-v`) اتفاق نمی‌افتد، اما `-v` هرگز اجرا نمی‌شود (حرفه‌ای‌تر: `down` معمولی volume را نگه می‌دارد).
- `restart: unless-stopped` برای هر دو سرویس.

---

## ۲. Dockerfile

فایل: [tasnim/Dockerfile](../../tasnim/Dockerfile)

```dockerfile
FROM python:3.12-slim
ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TASNIM_DB_PATH=/data/readmodel/tasnim_readmodel.db
WORKDIR /app
COPY . /app/tasnim/
RUN pip install --no-cache-dir "Flask==3.1.3"
RUN useradd --create-home --uid 10001 tasnim
USER tasnim
EXPOSE 5071
HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:5071/api/v1/tasnim/health', timeout=5)"
ENTRYPOINT ["python","-X","utf8","-m","tasnim.web.app"]
CMD ["--db","/data/readmodel/tasnim_readmodel.db","--host","0.0.0.0","--port","5071","--rate-db","/var/tasnim/ratelimit.db"]
```

نکات:

- **تک وابستگی**: فقط `Flask==3.1.3` پین‌شده (سطح‌های واقعی: Flask 3.1.3 / Jinja2 3.1.6 / Werkzeug 3.1.9). فونت OFL داخل `/app/tasnim/web/static/fonts/` است و از filesystem سرو می‌شود (هیچ بستهٔ Python دیگر لازم نیست).
- **non-root**: user `tasnim` با uid ثابت 10001.
- `COPY . /app/tasnim/` — یعنی build context ریشهٔ repo است و فقط درخت `tasnim/` وارد image می‌شود؛ **هیچ data در image نیست** (read model از bind mount می‌آید).

---

## ۳. nginx (tasnim-web)

فایل: [tasnim/nginx/tasnim.conf](../../tasnim/nginx/tasnim.conf)

- `upstream tasnim_api { server tasnim-api:5071; keepalive 32; }`
- `listen 5070` + `[::]:5070`
- gzip: min_length 1024، level 5
- `client_max_body_size 64k` (API فقط GET دارد؛ حد محافظتی)
- `location /api/` → proxy به upstream با:
  - `X-Real-IP $remote_addr`
  - `X-Forwarded-For $proxy_add_x_forwarded_for` (append-only — API برای rate-limit اولین entry XFF را می‌خواند؛ جزئیات در [SECURITY.md](SECURITY.md))
  - timeouts: connect 5s / read 60s / send 60s
- security headers (هر دو location): `X-Content-Type-Options: nosniff` + `Referrer-Policy: strict-origin-when-cross-origin`
- `X-Frame-Options: SAMEORIGIN` فقط روی `/api/` (صفحات SSR frame نمی‌شوند؛ API هم نمی‌تواند داخل iframe بیگانه بخورد)

---

## ۴. دستورات (روی host دارای Docker)

از ریشهٔ repo:

```bash
# build + start (هر دو سرویس):
docker compose -f tasnim/docker-compose.tasnim.yml up -d --build

# وضعیت + health:
docker compose -f tasnim/docker-compose.tasnim.yml ps
docker inspect --format '{{.State.Health.Status}}' tasnim-api
docker inspect --format '{{.State.Health.Status}}' tasnim-web

# لاگ‌ها:
docker compose -f tasnim/docker-compose.tasnim.yml logs -f tasnim-api

# smoke روی nginx:
python -X utf8 -m tasnim.e2e.smoke --base http://127.0.0.1:5070

# توقف (volume حفظ می‌شود):
docker compose -f tasnim/docker-compose.tasnim.yml stop

# ⛔ هرگز: docker compose down -v
```

### اجرای تک‌سرویس (فقط API، بدون nginx)

```bash
docker build -t tasnim-api:pcm2064 -f tasnim/Dockerfile .
docker run --rm --name tasnim-api \
  -v "$PWD/tasnim/data/readmodel/v0003:/data/readmodel:ro" \
  -v tasnim_runtime:/var/tasnim \
  -p 127.0.0.1:5071:5071 \
  tasnim-api:pcm2064
# → http://127.0.0.1:5071/api/v1/tasnim/health
```

---

## ۵. تغییر نسخهٔ read model (v0003 → v0004)

1. read model جدید را در `tasnim/data/readmodel/v0004/` بسازید (سند: [DATA-CONTRACT.md](DATA-CONTRACT.md)).
2. در compose، bind mount `./tasnim/data/readmodel/v0003` → `v0004` (یا با env `TASNIM_DB_PATH` مسیر دقیق‌تر را بدهید).
3. `docker compose ... up -d tasnim-api` (image عوض نشده؛ فقط mount).
4. smoke → اگر سبز: `tasnim-web` را هم restart کنید تا `depends_on` دوباره healthy را ببیند.
5. rollback = برگرداندن mount به v0003 + restart. v0003 دست‌نخورده باقی می‌ماند (immutable).

---

## ۶. troubleshooting

| علائم | احتمال | راه‌حل |
|---|---|---|
| `tasnim-web` بالا نمی‌آید، status = `unhealthy` / `starting` | API هنوز healthy نیست | `docker compose ... logs tasnim-api` — معمولاً مسیر `--db` اشتباه است |
| `sqlite3.OperationalError: unable to open database file` | read model در مسیر mount نیست یا bind ro خطا دارد | `docker compose ... exec tasnim-api ls -l /data/readmodel` — باید ۴ فایل (db + meta + sidecar + covers/) دیده شود |
| همهٔ درخواستها 429 | rate-limit volume از قبل پر است (test‌های پیاپی) | `docker compose ... exec tasnim-api rm -f /var/tasnim/ratelimit.db` و restart (جزئیات: [OPS-RUNBOOK.md](OPS-RUNBOOK.md)) |
| `port is already allocated` روی 5070 | پورت اشغال (inventory را ببینید: [DEPLOYMENT.md](DEPLOYMENT.md) §4) | سرویس اشغال‌کننده را پیدا کنید یا پورت publish را تغییر دهید |
| build شکست: `pip` network error | mirror/proxy | روی host میزبان `--build-arg` mirror پیکربندی کنید؛ تنها بسته Flask است |
| image pull `nginx:1.27-alpine` شکست | registry access | cache registry داخلی سازمان را استفاده کنید |
| Persian text در خروجی container garbled | env (نادر) | `PYTHONUNBUFFERED=1` و `-X utf8` در ENTRYPOINT هستند؛ locale container لازم نیست — همه‌چیز در سطح text/JSON است |

---

## ۷. چه چیزی برای «اثبات واقعی Docker» لازم است (V1.5)

- [ ] host دارای Docker ≥ 24 + compose plugin
- [ ] `docker compose -f tasnim/docker-compose.tasnim.yml up -d --build` سبز
- [ ] smoke 15/15 با `--base http://127.0.0.1:5070`
- [ ] ثبت خروجی `docker compose ps` + hash image در [TEST-REPORT.md](TEST-REPORT.md)

تا آن زمان، وضعیت صادقانه این است: **stack طراحی‌شده + بازبینی‌شده + اجرای مستقیم اثبات‌شده؛ اجرای image هنوز نشده.**

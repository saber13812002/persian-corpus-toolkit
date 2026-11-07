# Runbook عملیاتی — Tasnim Web V1

> PCM-20.6.4 · سند B15 · 2026-11-07
> نقشهٔ مادر: [INDEX.md](INDEX.md) · استقرار: [DEPLOYMENT.md](DEPLOYMENT.md) · بک‌آپ: [BACKUP-RESTORE.md](BACKUP-RESTORE.md)

---

## ۱. چک روزانه (≈ ۲ دقیقه)

```bash
# 1) health — انتظار status=ok + readmodel.version:
curl -sS http://127.0.0.1:5070/api/v1/tasnim/health

# 2) smoke کوتاه (فقط health + home + page + search):
python -X utf8 -m tasnim.e2e.smoke --base http://127.0.0.1:5070
# انتظار: 15 PASS / 0 FAIL

# 3) لاگ‌های خطا (compose):
docker compose -f tasnim/docker-compose.tasnim.yml logs --since 24h tasnim-api | grep -Ei "error|traceback"
```

اگر smoke شکست خورد → بخش ۶ (incident).

## ۲. چک هفتگی (≈ ۱۰ دقیقه)

- [ ] smoke کامل 15/15 (همان دستور بالا)
- [ ] **disk**: `du -sh tasnim/data/readmodel/` (خط پایه: ≈ 261 MB برای v0003) — رشد غیرمنتظره یعنی مشکل
- [ ] **rate-limit DB**: اندازهٔ `tasnim_rate_limits.db` (یا `ratelimit.db` در volume) — باید کوچک بماند (≤ چند MB؛ جدول به‌طور خودکار purge می‌شود اما اگر بزرگ شد، reset در بخش ۴)
- [ ] **429 rate**: در لاگ‌ها یا ingress، فراوانی پاسخ‌های 429 را نگاه کنید؛ اگر کاربران واقعی 429 می‌گیرند، یا load واقعی بالاست (طبیعی) یا bot (→ بخش ۵)
- [ ] **ETag/304**: یک `curl -H "If-None-Match: …"` دستی — 304 باید بیاید (اگر 200 آمد، cache شکسته است)
- [ ] **درون‌بررسی read model**: `sqlite3 tasnim_readmodel.db "PRAGMA integrity_check;"` → `ok` (read-only؛ DB read-only mount است، خرابی = مشکل filesystem)
- [ ] بک‌آپ (بخش ۳)

---

## ۳. بک‌آپ دوره‌ای

**چه چیزی بک‌آپ می‌شود** (فقط این‌ها):

| آیتم | مسیر | اندازهٔ خط پایه |
|---|---|---|
| read model | `tasnim/data/readmodel/v0003/` (db + build_meta + sidecar + covers) | ≈ 261 MB |
| rate-limit (اختیاری) | `tasnim_rate_limits.db` / volume `tasnim_runtime` | ≤ MBها — **حیاتی نیست** (دادهٔ قابل‌تولید) |
| corpus source | canonical corpus (روی s52) | GBها — **جدا بک‌آپ می‌شود** (immutable؛ سند: [BACKUP-RESTORE.md](BACKUP-RESTORE.md)) |

دستور (الگوی بک‌آپ سازمانی — AGENTS.md §3):

```bash
TS=$(date +%Y%m%d-%H%M%S)
mkdir -p /home/saber/backups
# 1) snapshot read model:
cp -a tasnim/data/readmodel/v0003 /home/saber/backups/tasnim-readmodel-v0003-$TS
# 2) verify:
( cd /home/saber/backups/tasnim-readmodel-v0003-$TS && sha256sum tasnim_readmodel.db )
# مقایسه با:
sha256sum tasnim/data/readmodel/v0003/tasnim_readmodel.db
# (یا مقایسه با build.sha256 sidecar)
```

**restore** را در [BACKUP-RESTORE.md](BACKUP-RESTORE.md) ببینید.

---

## ۴. reset rate-limit (وقتی همه 429 می‌گیرند)

```bash
# اجرای مستقیم (dev):
rm tasnim_rate_limits.db          # یا مسیر --rate-db
# و restart سرور

# compose:
docker compose -f tasnim/docker-compose.tasnim.yml exec tasnim-api \
  sh -c "rm -f /var/tasnim/ratelimit.db"
docker compose -f tasnim/docker-compose.tasnim.yml restart tasnim-api
```

- rate-limit **per-IP per-calendar-minute** است (search 30/min، read 120/min) — reset فقط وقتی لازم است که state خراب/آلوده شده باشد (مثلا‌ بعد از تست‌های سنگین روی یک IP واحد).
- reset **دادهٔ کاربری نمی‌ازاید** — rate-limit state قابل‌تولید است.
- اگر 429 فقط روی یک IP خاص است و بقیه سالم‌اند: مشکل bot/scraper است، نه خرابی (بخش ۵).

---

## ۵. پایش و هشدارهای پیشنهادی

| سیگنال | چطور دیدن | آستانهٔ پیشنهادی |
|---|---|---|
| health | `GET /api/v1/tasnim/health` (exempt از rate-limit) | 1 fail متوالی = page |
| 5xx در ingress | لاگ ingress | هر 5xx (باید تقریبا‌ صفر باشد — API فقط 4xx/503-سوره می‌دهد) |
| 429 rate | ingress status codes | > 1% درخواستها در 5 دقیقه = بررسی |
| disk usage | `df -h` روی host | > 80% = هشدار |
| container health | `docker inspect --format '{{.State.Health.Status}}' tasnim-api tasnim-web` | هر `unhealthy` = page |
| restart‌های مکرر | `docker inspect --format '{{.RestartCount}}' tasnim-api` | > 2 در 24h = بررسی |

**چیزی که نباید رخ دهد**: stack trace در خروجی عمومی. هرگز (error pages سفارشی فارسی؛ سند: [SECURITY.md](SECURITY.md)).

---

## ۶. incident response

### سناریو 1: «سایت پایین است» (ingress 502/504)

1. `docker compose -f tasnim/docker-compose.tasnim.yml ps` — کدام container؟
2. `docker compose ... logs --since 1h tasnim-api` / `tasnim-web`
3. اگر `tasnim-api` restarting: `--db` path را چک کنید (`ls -l tasnim/data/readmodel/v0003/`)
4. `docker compose ... up -d tasnim-api` (image عوض نشده؛ فقط restart)
5. smoke 15/15 → ثبت در گزارش

### سناریو 2: «صفحات خالی/غلط می‌آید» (200 ولی محتوا بد)

1. `curl -sS .../api/v1/tasnim/catalog | head` — `readmodel.version` و `content_sha256` را با `build_meta.db` مقایسه کنید
2. اگر mismatch: mount اشتباه شده است (دو نسخه؟) — compose را چک کنید
3. `PRAGMA integrity_check` روی DB (read-only)
4. rollback به snapshot قبلی: [BACKUP-RESTORE.md](BACKUP-RESTORE.md) §restore

### سناریو 3: «کاربر می‌گوید جستجو جواب نمی‌دهد»

1. از سرور تست کنید: `curl -sS ".../api/v1/tasnim/search?q=قرآن&limit=1"` — 6,760 انتظار
2. اگر 429: بخش ۴
3. اگر 200 ولی total=0: query user را دقیق بگیرید — محدودیت‌های توکنایزیشن (نیم‌فاصله، stemming) در [USER-GUIDE-FA.md](USER-GUIDE-FA.md) §3 — احتمالاً انتظار کاربر با طراحی فعلی خوانده نمی‌شود (bug نیست؛ roadmap item)
4. اگر bug واقعی: `test_tasnim_api.py` را بچینید + issue

### سناریو 4: «سخت‌افزار/دیسک پر شد»

1. `df -h` — بزرگ‌ترین consumer؟
2. rate-limit DB (reset در بخش ۴ — ایمن است)
3. لاگ‌های قدیمی container: `docker compose ... logs` را truncate کنید (state نمی‌پرد)
4. هرگز read model را برای جا باز نکنید — restore از بک‌آپ: [BACKUP-RESTORE.md](BACKUP-RESTORE.md)

---

## ۷. تغییر نسخهٔ read model (v0003 → v0004) — procedure کامل

**پیش‌نیاز**: v0004 با build CLI ساخته شده + verify شده (SHA + smoke روی v0004 به‌طور محلی سبز). سند build: [DATA-CONTRACT.md](DATA-CONTRACT.md).

```text
1. بک‌آپ فعلی (بخش ۳) — قبل از هر چیزی.
2. v0004 را کنار v0003 کپی کنید (هرگز جابجا/حذف):
     tasnim/data/readmodel/v0004/
3. verify SHA:
     sha256sum tasnim/data/readmodel/v0004/tasnim_readmodel.db
     # باید با build.sha256 در v0004/ یکی باشد
4. در compose: bind mount v0003 → v0004 (یا env TASNIM_DB_PATH)
5. docker compose ... up -d tasnim-api   (image بدون تغییر)
6. health-wait (30s start_period)
7. smoke 15/15 با --db v0004 → اگر سبز:
     docker compose ... restart tasnim-web
8. ثبت: report + آپدیت README (نسخهٔ فعال)
```

**rollback** (هر لحظه، ≈ ۲ دقیقه):
```text
1. compose: bind mount → v0003
2. docker compose ... up -d tasnim-api && restart tasnim-web
3. smoke 15/15 → ثبت
```
v0003 دست‌نخورده باقی مانده است (immutable) — rollback واقعی است، نه restore.

---

## ۸. قوانین طلایی عملیاتی

1. **هرگز `docker compose down -v`** — volume runtime (rate-limit state) می‌پرد؛ `stop`/`restart`/`up -d` کافی است.
2. **هرگز داخل `tasnim/data/readmodel/vNNNN/` ننویسید** — read-only.
3. **بدون بک‌آپ، مهاجرت نمی‌شود** — قبل از هر سواپ، snapshot + SHA verify.
4. **هر تغییر: تست → (commit — مرحلهٔ 7) → deploy → smoke → گزارش.**
5. **آمار به مدیران فقط از `/api/v1/tasnim/statistics`** — شمارندهٔ واقعی DB؛ هرگز تخمین.

# گزارش PCM-03 — رفع مانع SSH، ممیزی و استقرار (تکمیل‌شده)

**تاریخ:** ۱۴۰۵/۰۸/۰۲ (2026-10-23)
**HEAD Git:** `dd0911b` · **Production:** `https://corpus.ai.ismc.ir` · **سرور:** `s52` (`172.20.1.52`)

---

## ۱. نتیجه نهایی: **استقرار موفق — API ساخت پروژه در Production فعال است**

| مرحله | وضعیت |
|---|---|
| رفع دسترسی SSH | ✅ کلید ایجنت روی s52 (پورت 22) فعال شد — پورت 2222 در واقع **GitLab** است، نه SSH |
| ممیزی استقرار | ✅ مسیر/کانتینر/Volume/DB/نسخه فعلی شناسایی شد |
| بکاپ | ✅ `~/backups/thesaurus-20261023-081649.db` — `integrity_check: ok` |
| Build و Deploy | ✅ تصویر ساخته شد؛ فقط کانتینر backend recreate شد (سایر 40+ سرویس دست‌نخورده) |
| `/api/projects` | ✅ **HTTP 200 + JSON معتبر** (قبلا 404) |
| `/api/sites` و `/api/stats` | ✅ دست‌نخورده، 200 |
| داده‌های قدیمی | ✅ 1099 crawled / 1475 queue — **قبل و بعد دقیقا یکسان** |
| پروژه آزمایشی واقعی | ✅ `PCM03-E2E-14050802` (id=1) از API عمومی ساخته شد |
| ثبت پایدار در SQLite | ✅ رکورد مستقیما در جدول `projects` دیده شد |
| ماندگاری بعد از restart کنترل‌شده | ✅ بعد از `docker restart` هم از API برگردانده شد |
| تست واقعی Chrome | ⏸️ **برای کاربر** — چک‌لیست ۶ مرحله‌ای (بخش ۷) |

**شرط پایان PCM-03 برآورده شد:** ساخت پروژه در Backend واقعی ✅ · ثبت پایدار ✅ · دریافت از API ✅ · آماده‌بودن برای آزمون Chrome ✅

---

## ۲. یافته‌های دسترسی SSH (مرحله ۱)

- کلید ایجنت (`zcode-agent`, fingerprint `SHA256:97MEQ0f1L/bHr49fXQf1leXELZmzkczmgCsv5d5qvOQ`) در `~saber/.ssh/authorized_keys` روی s52 **ثبت شده بود** (پس از هماهنگی کاربر)
- **کشف مهم:** `172.20.1.52:2222` که در `~/.ssh/config` وای‌سیده بود، در واقع **GitLab CE** است (`gitlab/gitlab-ce:16.3.9`, کانتینر `gitlab` با map `2222->22`) — نه سرویس SSH. SSH واقعی s52 روی **پورت 22** است.
- entry `s52` در config کاربر با `Port 2222` برای SSH اشتباه است (فقط برای دسترسی git به GitLab کاربرد دارد).

## ۳. ممیزی استقرار (مرحله ۲ — قبل از تغییر)

| مورد | مقدار |
|---|---|
| مسیر استقرار | `/home/saber/saberprojects/persian-corpus-toolkit` (کپی کد، **نه** git repo) |
| Compose | `docker-compose.yml` — فقط سرویس `backend` |
| کانتینر | `persian-corpus-toolkit-backend-1`، image `persian-corpus-toolkit-backend`، پورت `127.0.0.1:5055` |
| Volume/DB | bind-mount: `./backend/thesaurus.db → /data/thesaurus.db` (فایل SQLite 13.8MB، WAL) |
| نسخه قبل از استقرار | کد 2026-10-14 — تصویر فقط `server.py + sites.py + sciences.py` داشت (**بدون `projects.py` → ریشه 404**) |
| رکوردها (baseline) | `crawled_data=1099`, `crawl_queue=1475`؛ جداول: captures, crawl_progress, crawl_queue, crawled_data, khamenei_speeches, site_fields, sites |
| سرویس‌های نامرتبط سرور | 40+ کانتینر (llmhub, kong, cms, gitlab, …) — **هیچ‌کدام لمس نشدند** |
| سازگاری migration | اسکیمای جدید **additive** (جدول‌های `projects`, `project_points`, `project_pages` خودکار ساخته می‌شوند؛ هیچ تغییری روی جداول قدیمی) ✅ |

## ۴. عملیات استقرار (مرحله ۴ — با مجوز صریح کاربر)

دستورالعمل اجراشده (اسکریپت‌ها در [`deploy/pcm03_backup.sh`](deploy/pcm03_backup.sh:1) و [`deploy/pcm03_deploy.sh`](deploy/pcm03_deploy.sh:1) — این‌ها هم به Git اضافه شدند):

1. **بکاپ SQLite** با `sqlite3 .backup` → `/home/saber/backups/thesaurus-20261023-081649.db` → `PRAGMA integrity_check: ok`
2. **سشن‌شات کل پوشه استقرار** (به‌جز DB) → `/home/saber/backups/pct-deploy-20261023-081828.tar.gz` (rollback کد)
3. انتقال کد `origin/main` (`dd0911b`) با tar؛ DB در tar **نبود** و دست‌نخورده ماند
4. `docker compose build backend` + `docker compose up -d backend` — **بدون down**، فقط recreate کانتینر backend؛ healthy بعد از ۲ ثانیه
5. بررسی endpointها روی سرور و از خارج: همه 200
6. تأیید `integrity_check: ok` و تساوی شمارنده‌ها (1099/1475)

**Rollback در صورت نیاز (آماده و تست‌پذیر):**
```bash
# بازگردانی کد:
tar xzf /home/saber/backups/pct-deploy-20261023-081828.tar.gz -C /home/saber/saberprojects/
cd /home/saber/saberprojects/persian-corpus-toolkit && docker compose build backend && docker compose up -d backend
# بازیابی DB (اگر لازم شد):
cp /home/saber/backups/thesaurus-20261023-081649.db /home/saber/saberprojects/persian-corpus-toolkit/backend/thesaurus.db
```

## ۵. نتایج API (بعد از استقرار)

| Endpoint | قبل | بعد |
|---|---|---|
| `GET https://corpus.ai.ismc.ir/api/projects` | **404** | **200** `{"projects":[...]}` |
| `GET /api/sites` | 200 | 200 (بدون تغییر) |
| `GET /api/stats` | 200 | 200 (1099/1475 بدون تغییر) |
| `GET /dashboard` | 200 | 200 |

## ۶. پروژه آزمایشی (مستقیما از Production — با مجوز کاربر)

```
POST https://corpus.ai.ismc.ir/api/projects
{"name":"PCM03-E2E-14050802","host":"tasnim.hamtaa.org","start_url":"https://tasnim.hamtaa.org/?item_index=1","next_mode":"url_param","next_param":"item_index","next_step":1,"pages_per_minute":2}
→ 200 {"ok":true,"project":{"id":1,...,"status":"draft"}}
```

- ✅ رکورد در SQLite: `sqlite3 ... 'SELECT id,name,host,status,cursor_url FROM projects'` → `1|PCM03-E2E-14050802|tasnim.hamtaa.org|draft|...`
- ✅ `docker restart persian-corpus-toolkit-backend-1` → `GET /api/projects` باز هم `id=1` را با 200 برمی‌گرداند
- ⚠️ این رکورد آزمایشی فعلا در Production باقی است؛ حذف آن فقط در صورت درخواست کاربر انجام می‌شود (endpoint حذف پروژه فعلا وجود ندارد)

## ۷. چک‌لیست تست Chrome (PCM-04 — توسط کاربر)

endpoint اکنون آماده است:

0 از 6
- اکستنشن را در `chrome://extensions` با Reload به‌روزرسانی کردم
- یک صفحه معمولی از `tasnim.hamtaa.org` باز کردم
- در Popup نام پروژه «تست تسنیم» را وارد و ثبت کردم
- پروژه در ComboBox ظاهر شد و انتخاب شد
- Popup را بستم و دوباره باز کردم؛ پروژه باقی مانده بود
- اکستنشن را Reload کردم؛ پروژه همچنان قابل انتخاب بود

> نکته: ComboBox روی تب `tasnim.hamtaa.org` دو پروژه را نشان خواهد داد: «تست تسنیم» شما + `PCM03-E2E-14050802` (آزمایش من).

## ۸. وضعیت Git

- Commitهای این مأموریت: `dd0911b` (گزارش اولیه) + commit پیوسته با اسکرپت‌های deploy و نتایج نهایی
- بدون هیچ secret/دیتابیس عملیاتی

## ۹. وضعیت PCM-01: **PASS (سمت Backend/Git) — در انتظار تأیید Chrome**

- ثبت نام پروژه: ✅ (از API واقعی Production)
- ذخیره واقعی در Backend: ✅ (SQLite مستقیما تأیید شد)
- نمایش در ComboBox + انتخاب خودکار + حفظ انتخاب: ⏸️ چک‌لیست بخش ۷ (نیازمند Chrome)

**قدم بعد:** اجرای چک‌لیست بخش ۷ توسط کاربر → سپس PCM-05 (Inspect Element) و PCM-06 (Crawling).

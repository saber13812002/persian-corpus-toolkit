# گزارش PCM-14B.3 — استقرار API Knowledge + Word Studio روی production (s52)

تاریخ: ۱۴۰۵/08/06 (2026-10-27، ۲۳:۲۷ تهران — مرجع: PCM-03: `2026-10-23=۱۴۰۵/08/02`) · کد پایه: commit `2ad6c53` (origin/main) · commit این فاز: `725f6bb`

---

## ۱. وضعیت قبل

- production s52: کد PCM-14B.2 (بدون `knowledge_api.py`، بدون `studio.html`)، کانتینر
  `persian-corpus-toolkit-backend-1`، DB `backend/thesaurus.db` (اسکیمای knowledge v2
  در PCM-14B.2 ساخته شده بود).
- کراول زنده: پروژه ۲ با ۲۳٬۷۵۳ صفحه (لحظه شروع فاز ۴) — باید هرگز قطع/پاک نشود.
- GitHub `origin/main` = `2ad6c53` (شامل همه‌ی کد PCM-14B.3: knowledge_api.py،
  studio.html، factory/، ۵ ماژول تست).

## ۲. طراحی (خلاصه)

- `backend/knowledge_api.py` — API خواندنی/نوشتنی Knowledge؛ همه‌ی endpoints با
  `@require_auth` (cookie `pct_session`). `data/` خارج از کد: store پایدار
  `data/knowledge/{files,out}` bind-mount به `/data-files/knowledge`.
- `dashboard/studio.html` — استودیو فارسی RTL (مجموعه‌ها/کتاب‌ها/جزئیات/jobها/مجموعه).
- `deploy/pcm14b_deploy.sh` — دپلوی کنترل‌شده: بکاپ DB → snapshot کد → `docker compose
  build backend && up -d backend` (بدون `down`)؛ `data/` و DB هرگز در tar نیستند.

## ۳. مهاجرت

- additive-only: `knowledge_schema_version` 1→2؛ `ALTER TABLE ADD COLUMN` +
  `CREATE TABLE IF NOT EXISTS`؛ در تک‌فرایند کانتینر اجرا شد (بدون نبرد همزمان).
- `PRAGMA integrity_check` پیش/پس: **ok**.

## ۴. فایل/API

| فایل | نقش |
|---|---|
| `backend/knowledge_api.py` | 28 endpoint Knowledge (🔒 require_auth) |
| `dashboard/studio.html` | Word Studio (فارسی/RTL) |
| `deploy/pcm14b_deploy.sh` | دپلوی کنترل‌شده + blob-hash verification |
| `deploy/pcm14b3_*.sh` | ۱۱ اسکریپت ممیزی/تست/سناریو (این فاز) |
| `docs/WORD-STUDIO-KNOWLEDGE-GUIDE.md` | راهنمای اپراتوری استودیو + Knowledge |
| `readme.md` | به‌روزرسانی (امکانات/معماری/API/DB/تست/نقشه‌ی راه) |
| `.gitattributes` | انضباط LF در export (رفع ریشه‌ای drift CRLF) |

## ۵. تست (زیرساخت + production)

| مجموعه | نتیجه |
|---|---|
| `test_api` / `test_projects` / `test_dashboard` / `test_knowledge_api` / `test_word_factory` | 8+9+22+40+24 = **103/103 سبز** (lokal + s52) |
| regression s52 (5 ماژول × 7 چیدمان: solo×5، مستند، معکوس، تکراری×2، discovery) | **7/7 OK**؛ guard ایزوله: `server.DB_PATH=/tmp/pct_test_*.db` |
| سناریوی زنده Word روی s52 (`pcm14b3_word_scenario.sh`) | **40/40 SARE PASSED** (2 DOCX، SHA، process، artifacts، metadata، approve، refresh، restart، interrupted-retry) |
| UI check (`pcm14b3_ui_check.sh`) | **18/18 PASS** (studio.html=200، sha سرو‌شده == sha repo، lang=fa dir=rtl، 401/200 auth) |
| extension | 8/8 (node) + `node --check` + manifest JSON |

> یادداشت: در regression اولیه s52 یک FAIL داشتیم — `dashboard/` در کپی /tmp نبود
> (STATIC_DIR به `../dashboard` نیاز دارد). با افزودن `cp -r dashboard` به harness
> رفع شد؛ production هرگز دست‌نخورده ماند.

## ۶. نتیجه production (smoke بعد از deploy)

| چک | نتیجه |
|---|---|
| `GET /dashboard/studio.html` | 200 (70٬977 بایت؛ sha سرو‌شده == sha repo) |
| `GET /api/auth/status` | 200 `{"auth_enabled":true,"authenticated":false}` |
| Knowledge بدون cookie | 401 · با cookie | 200 |
| `GET /api/knowledge/compatibility` | 200 `NOT VERIFIED` (ES در V0.1 غیرفعال) |
| API اکستنشن (`/api/projects*`) | باز (قانون AGENTS.md §2-6) |
| خارجی | `https://corpus.ai.ismc.ir/dashboard/studio.html` → 200 · `/api/auth/status` → 200 |
| کانتینر | `persian-corpus-toolkit-backend-1: Up` (recreate فقط) |

## ۷. SHA + لینک

- commit این فاز: `725f6bb` → https://github.com/saber13812002/persian-corpus-toolkit/commit/725f6bb
- هویت blob روی s52 (مطابق `git rev-parse 725f6bb:<path>`):
  `docs/WORD-STUDIO-KNOWLEDGE-GUIDE.md=9c93791a` · `readme.md=33f9c4fc` ·
  `deploy/pcm14b_deploy.sh=3370750a` · `.gitattributes=273f441c` — **4/4 تطبیق**.
- کد backend روی s52 = `2ad6c53` (مطابق blob-hashes در `pcm14b_deploy.sh`).

## ۸. git status

```
[main 725f6bb] PCM-14B.3: deploy+verify scripts, studio docs, .gitattributes LF discipline
18 files changed, 1200 insertions(+), 10 deletions(-)
push: 2ad6c53..725f6bb  main -> main (GitHub)
```

## ۹. بکاپ/rollback

- بکاپ‌های این روز: `/home/saber/backups/thesaurus-20261027-165923.db` +
  `thesaurus-20261027-171702.db` (هر دو `integrity_check=ok`) +
  `pct-deploy-<TS>.tar.gz` (snapshot کد، بدون DB).
- **Rollback کد**: extract snapshot + `docker compose build backend && up -d backend`
  (اسکیمای knowledge additive است؛ کد قدیمی جدول‌های جدید را نادیده می‌گیرد).
- **Rollback DB**: `.restore` از بکاپ — فقط در صورت فساد knowledge_* (احتمال خیلی کم).
- `data/` (فایل‌های Knowledge) در هیچ rollbackی لمس نمی‌شود.

## ۱۰. شمارنده‌های پایانی (تأیید صاف‌سازی)

| مورد | مقدار |
|---|---|
| `knowledge_collections` / `knowledge_collection_documents` / `knowledge_jobs` | **0 / 0 / 0** (داده‌های سناریو تمیز شدند) |
| `data/knowledge/files` | خالی (تمیزکاری) |
| پروژه ۲ (کراول زنده) | 23٬873 صفحه — **در حال رشد** (۲۳٬۷۵۳ → ۲۳٬۸۷۳ در طول فاز؛ هیچ قطعی) |
| `project_pages` کل | 23٬878 |
| `PRAGMA integrity_check` | ok |

## ۱۱. موارد باقی‌مانده + روش تست دستی

**باقی‌مانده (V0.1 → بعد):**
1. **Wiki.js**: ویکی موجود = `مستندات هوش مصنوعی` روی `docs.ai.ismc.ir` (پورت 8888،
   کانتینر `wikijs` + `wikijs-postgres`)؛ صفحه‌ای برای Word Factory/Studio **وجود ندارد**
   و API ویکی بدون ورود مدیری قابل‌نویسندگی نیست → سند در
   `docs/WORD-STUDIO-KNOWLEDGE-GUIDE.md` گذاشته شد؛ import به ویکی با حساب مدیری
   `docs.ai.ismc.ir` انجام می‌شود (خارج از scope این فاز — فقط چک شد).
2. Build ES (`/builds`) و `compatibility=NOT VERIFIED` — فعال‌سازی ES در فاز بعد.
3. batch import: فعلاً registration؛ پردازش bulk = توالی jobهای تک‌تک.
4. PDF/صفحه‌بندی خارج از scope؛ `page` همیشه `null`.

**روش تست دستی:**
1. مرورگر → `https://corpus.ai.ismc.ir/dashboard/studio.html` → overlay ورود (رمز داشبورد).
2. «مجموعه جدید» (نام + موضوع) → تب کتاب‌ها → آپلود یک `.docx` (≤50MB).
3. «پردازش» → poll jobها → وضعیت `parsed`/`needs_review`.
4. جزئیات: ساختار / کیفیت (score + ۸ check + losses) / بلوک‌ها.
5. «تأیید» → `approved`. «جداکردن» → حذف row (فایل store باقی می‌ماند).
6. بدون cookie: هر `/api/knowledge/*` → 401؛ `/api/projects*` باز.

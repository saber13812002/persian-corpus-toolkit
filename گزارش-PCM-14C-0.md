# گزارش PCM-14C.0 — ممیزی تطبیق سه‌محیطی (لوکال / GitHub / s52) پیش از PCM-14C

تاریخ: ۱۴۰۵/08/07 (2026-10-28، ۰۶:۳۰ تهران) · فاز: ممیزی فقط-خواندنی (بدون تغییر production)
· اسکریپت: `deploy/pcm14c_env_audit_remote.sh` (جدید)

## ۱. وضعیت قبل

- سؤال باز از گزارش PCM-14B.3: «SHA کد Backend روی سرور (`2ad6c53`) با Commit مستندات
  (`725f6bb`) متفاوت است؛ آیا خطا است؟ کدام نسخه از هر فایل در حال اجراست؟»
- این فاز **هیچ** تغییر production انجام نداد؛ فقط خواند (git، hash، probe HTTP،
  sqlite خواندنی) در حالی که کراول زنده در حال اجرا بود.

## ۲. نتیجه کلیدی (پاسخ سؤال SHA)

**تفاوت `2ad6c53` و `725f6bb` خطا نیست؛ طراحی است.**

| Commit | محتوا | اجرا روی s52؟ |
|---|---|---|
| `2ad6c53` | کل کد PCM-14B.3 (backend، factory/، studio.html) | ✅ بله — کانتینر دقیقاً این blobها را اجرا می‌کند |
| `725f6bb` | + ۱۱ اسکریپت deploy/pcm14b3_* + راهنمای استودیو + readme + .gitattributes | ❌ خیر — هیچ‌کدام در Docker image نیست (Dockerfile فقط `backend/*` و `factory/` را COPY می‌کند؛ اسکریپت‌های deploy فقط روی host اجرا می‌شوند) |
| `a855b9a` (= HEAD = origin/main) | + همین فایل گزارش PCM-14B.3 فقط | ❌ docs-only |

اثبات: `git diff --stat 2ad6c53..a855b9a -- backend/ dashboard/ docker-compose.yml extension/`
**خالی** است → مخزن HEAD همه‌ی کد مستقر را **بدون هیچ تغییر** دارد. هیچ کدی در
GitHub/لوکال قدیمی‌تر یا متفاوت از s52 نیست.

## ۳. مهاجرت

نیازی نبود (فقط-خواندنی؛ بدون تغییر schema).

## ۴. فایل/API

| فایل | نقش |
|---|---|
| `deploy/pcm14c_env_audit_remote.sh` | ممیزی فقط-خواندنی سه‌لایه: blob SHA روی disk host + md5 کد داخل image + bind-mount dashboard + probe + DB خواندنی |

## ۵. تست / ممیزی (نتایج واقعی این اجرا، ۲۰۲۶-۱۰-۲۸ ۰۶:۲۵ تهران)

**الف) disk host s52 — ۱۳/۱۳ blob SHA == blob commit `2ad6c53`:**

```
b0cfa213  backend/server.py          21eb85ef  backend/sciences.py
e1bbe1cb  backend/auth.py            ec6f3ce3  backend/projects.py
fdcb1424  backend/dashboard_api.py   ee5a449a  backend/sites.py
b9c42b29  backend/knowledge_api.py   23190460  backend/pct_test_support.py
0d211b9b  backend/Dockerfile         bf5bef10  backend/requirements.txt
fc05c998  docker-compose.yml         4c7c2a54  dashboard/studio.html
e548c3ac  dashboard/index.html
```

**ب) کد داخل کانتینر در حال اجرا — ۲۱/۲۱ md5 == md5(`git show 2ad6c53:<path>`):**
`/app/server.py`، `/app/knowledge_api.py`، `/app/auth.py`، `/app/dashboard_api.py`،
`/app/projects.py`، `/app/sciences.py`، `/app/sites.py`، `/app/requirements.txt` +
`/app/factory/*` (۱۴ فایل) — **همه برابری دقیق بایت‌به‌بایت با commit `2ad6c53`.**
کانتینر: `persian-corpus-toolkit-backend-1` · image `sha256:147e985d…` ·
ساخت image `2026-10-27T17:17:12Z` (هم‌زمان با TS دپلوی PCM-14B.3) · Up ۸ ساعت.

> توضیح CRLF: checkout ویندوز `core.autocrlf=true` دارد (فایل‌ها CRLF روی disk لوکال،
> blob در git = LF). بنابراین md5 فایل‌های لوکال با md5 کانتینر متفاوت است — این
> drift نیست؛ blob SHA (بخش الف) مرجع هویت است و ۱۳/۱۳ تطبیق دارد.

**ج) dashboard از bind-mount (نه از image) سرو می‌شود:**
`./dashboard` → `/dashboard:ro`؛ blob `studio.html` روی disk = `4c7c2a54` = همون
blob `2ad6c53` → سروِ ۲۰۰ تأیید شد.

**د) probe سرویس (127.0.0.1:5055):**

| endpoint | نتیجه |
|---|---|
| `GET /dashboard/studio.html` | 200 |
| `GET /api/auth/status` | 200 `{"auth_enabled":true,"authenticated":false}` |
| `GET /api/knowledge/collections` بدون cookie | 401 (auth فعال) |
| `GET /api/dashboard/projects` بدون cookie | 401 (auth فعال) |
| `GET /api/projects` (اکستنشن) | **200 — باز** (قانون AGENTS.md §2-6) |

**ه) DB خواندنی:** `PRAGMA integrity_check = ok` · ۷ جدول `knowledge_*` ·
ستون‌های v2 موجود (`knowledge_jobs.retry_count`، `knowledge_collection_documents.status`) ·
collections/documents/jobs = 0/0/0.

## ۶. نتیجه production

کد در حال اجرا روی s52 = **دقیقاً commit `2ad6c53`** (ساخته‌شده از `git archive`).
هیچ فایل کدی بین s52، GitHub و لوکال تفاوت ندارد. کراول زنده (پروژهٔ ۲) در حال
اجرا و **رشد** است (مشاهدهٔ مستقیم در ۲ لحظه: ۲۵٬۵۶۰ → ۲۵٬۵۷۷ صفحه؛ `updated_at`
هر چند ثانیه به‌روز می‌شود) — هیچ تأثیری از این ممیزی بر آن نشده.

## ۷. شمارنده‌های واقعی (لحظهٔ ممیزی)

| مورد | مقدار |
|---|---|
| `project_pages` پروژهٔ ۲ | **25,577** (در گزارش 14B.3: 23,873 — رشد مداوم، بدون قطعی) |
| `project_pages` کل | 25,582 |
| `crawl_queue` | 352,785 |
| `knowledge_collections / documents / jobs` | 0 / 0 / 0 |
| `PRAGMA integrity_check` | ok |

## ۸. ⚠️ ابهام‌های باقی‌مانده (کشف‌شده در این ممیزی)

1. **`data/knowledge/` ۲۶۷ مگابایت دادهٔ یتیم سناریو دارد** — گزارش PCM-14B.3 §10
   نوشت «`data/knowledge/files` خالی (تمیزکاری)» ولی در واقع ۵ دایرکتوری فایل
   (168K) + ۹ دایرکتوری out (≈267M) با مالک **root** (نوشتۀ کانتینر) باقی مانده‌اند؛
   تمیزکاری DB انجام شده ولی فایل‌های disk پاک نشده‌اند (احتمالاً `Permission
   denied` — دایرکتوری‌ها root-owned و کاربر `saber` دسترسی حذف ندارد).
   - همه‌ی این IDها متناظر با سطرهای پاک‌شده‌ی سناریوی ۴۰/۴۰ هستند (جدول‌های
     knowledge خالی‌اند) → **کاملاً یتیم و قابل حذف امن**.
   - پیشنهاد (اجرا نشد — طبق دستور «Production را فعلاً تغییر نده»):
     `sudo docker exec persian-corpus-toolkit-backend-1 rm -rf /data-files/knowledge/files /data-files/knowledge/out`
     + `mkdir -p` مجدد + chmod 775 (یا تغییر USER کانتینر در PCM-14C تا root نباشد).
   - نکتهٔ امنیت: دو دایرکتوری ۱۲۵M در `out/` برای ۲ فایل تستی DOCX بزرگ‌تر از
     انتظار است — هنگام PCM-14C/audit بعدی باید بررسی شود چه چیزی آن‌قدر جا
     برده (احتمال تکرار چندگانهٔ chunks در output).
2. `compatibility=NOT VERIFIED` — ES هنوز غیرفعال (در V0.1 مورد انتظار؛ PCM-14C).
3. import راهنما به Wiki.js با حساب مدیری `docs.ai.ismc.ir` (خارج از scope فنی).
4. batch import = توالی jobهای تکی (مورد انتظار V0.1).

## ۹. SHA + لینک

- HEAD لوکال = origin/main = `a855b9a` (این گزارش در commit بعدی پیوست می‌شود)
- هویت کد s52: ۱۳/۱۳ blob (host) + ۲۱/۲۱ md5 (container) == `2ad6c53`
- image s52: `sha256:147e985ddade2ed6f2078383720189852e66e697dec58516dbdd1bfed290f9ec`

## ۱۰. بکاپ/rollback

- تغییر production: **صفر** (فقط خواند) → rollback لازم نیست.
- بکاپ‌های موجود از PCM-14B.3 عیناً معتبرند: `thesaurus-20261027-165923.db`،
  `thesaurus-20261027-171702.db` + `pct-deploy-<TS>.tar.gz`.

## ۱۱. نتیجه و قدم بعد

**تطبیق سه محیط تأیید شد:** لوکال ویندوز = GitHub = `a855b9a` (docs-only روی
کدِ `2ad6c53`)؛ s52 = دقیقاً `2ad6c53` در حال اجرا. سؤال SHA کاملاً روشن شد.

**پیش‌نیازهای پیشنهادی برای شروع PCM-14C** (بدون تأخیر در فاز):
1. پاک‌سازی ۲۶۷M دادهٔ یتیم `data/knowledge/` (یک دستور `sudo docker exec`؛ §8-1) —
   پیش از پر شدن بیشتر در PCM-14C.
2. بررسی سبب حجم ۱۲۵M دو دایرکتوری out.
3. سپس PCM-14C: مدل استاندارد کتاب (نسخه/جلد/تعداد)، ثبات متادیتا، و
   سازگاری/فعال‌سازی Elasticsearch — بدون هیچ دست‌کاری در کراول فعلی.

**روش تکرار ممیزی:**
```bash
scp deploy/pcm14c_env_audit_remote.sh saber@172.20.1.52:/tmp/
ssh -p 22 saber@172.20.1.52 'bash /tmp/pcm14c_env_audit_remote.sh'
```

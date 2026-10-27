# گزارش PCM-14B.2 — ممیزی و پذیرش ایزوله: رفع نقص قرارداد retry job + ممیزی انحراف‌های گزارش 14B

**تاریخ:** ۲۰۲۶/۱۰/۲۷
**SHA:** `fc8d60e` (پس از `430bfc7`)
**حوزه:** `backend/knowledge_api.py`، `backend/test_knowledge_api.py`، `deploy/pcm14b_acceptance_local.py`
**تأثیر روی سرفصل اصلی:** صفر (بدون لمس `thesaurus.db` production، بدون تغییر API سرفصل، بدون تغییر `index.html`)

---

## ۱. وضعیت قبل از شروع

- PCM-14B (`9f1aad8`): Word Factory V0.2 پیاده‌شده؛ تست‌های ماژولی سبز.
- ممیزی اولیه (این مأموریت) دو یافته داشت:
  - **F-A (مهم):** قرارداد retry job شکسته بود. `_submit_job` برای هر `job_key` موجود (از جمله `failed`/`interrupted`) همان ردیف قدیمی را برمی‌گرداند و worker جدیدی **نمی‌گشود**. یعنی سندِ job شکسته/قطع‌شده هرگز دوباره اجرا نمی‌شد — در حالی که §۱۳ اسپک و گزارش 14B هر دو «retryable» را وعده می‌دادند. ستون `retry_count` هم در کل کد دست‌نخورده بود.
  - **F-B (فنی):** سطر ۸۱ گزارش 14B اندپوینت `GET /api/knowledge/jobs/<job_id>` را مستند کرده بود؛ چنین روتی در کد وجود ندارد (فقط `GET /api/knowledge/jobs` فهرست).
- s52: بک‌اند دپلوی‌شده از ۲۰۲۵-10-23 است و اصلاً `knowledge_api.py` ندارد → هیچ‌چیز از 14B روی production نیست.

## ۲. طراحی (رفع F-A)

تغییر در [`_submit_job`](backend/knowledge_api.py:454):

| وضعیت job موجود با همان `job_key` | رفتار قبل | رفتار بعد |
|---|---|---|
| `pending` / `running` | برگرداندن ردیف، worker دوم نمی‌گشود (idempotent) | **بدون تغییر** — همان |
| `succeeded` | برگرداندن ردیف (idempotent) | **بدون تغییر** — همان |
| `failed` / `interrupted` | برگرداندن ردیفِ مرده ❌ | **بازاجرا:** ردیف به `pending` بازمی‌گردد (`progress=0, error=NULL, completed_at=NULL`)، `retry_count+1`، worker تازه می‌گشود؛ پاسخ `202` + `resubmitted=false` |

Worker spawn در helper مشترک [`_start_worker`](backend/knowledge_api.py:497) (import lazy از `server` — همان قرارداد قبلی، بدون تغییر رفتار).

## ۳. مهاجرت

هیچ. (ستون `retry_count` از نسخه 2 schema 14B وجود داشت — فقط مصرفش تکمیل شد.)

## ۴. فایل‌ها و API

| فایل | تغییر |
|---|---|
| `backend/knowledge_api.py` | `_submit_job`: شاخه retry برای `failed`/`interrupted` + helper `_start_worker` |
| `backend/test_knowledge_api.py` | تست regresion `test_kb12b_retry_reexecutes_interrupted_job` (40 تست در ماژول؛ قبل 39) |
| `deploy/pcm14b_acceptance_local.py` | اسکریپت پذیرش ایزوله: server واقعی روی DB+دادهٔ موقت، ۲ فاز با restart واقعی (kill/relaunch) |

API: بدون تغییر امضا. فقط **رفتار** `POST /documents/<id>/process` (و `POST /import/batches/<id>/process`) برای jobهای شکسته درست شد.

## ۵. تست‌ها

```
Ran 103 tests in 34.1s — OK
```

| ماژول | تعداد | وضعیت |
|---|---|---|
| `test_api` | 8 | ✅ |
| `test_projects` | 9 | ✅ |
| `test_dashboard` | 22 | ✅ |
| `test_word_factory` | 24 | ✅ |
| `test_knowledge_api` | 40 | ✅ |

(گزارش 14B اعداد 25/9/16/0/52 را ذکر کرده بود؛ آن اعداد با واقعیت ماژول‌ها در آن لحظه تطبیق ندارد — ارقام بالا شمارش واقعی اجرای امروز است.)

**تست regresion جدید (KB-12B):** job را مستقیم `interrupted` می‌کند (۲ ساعت قدیمی) + سند را `uploaded`؛ سپس `/process` → `202`، همان `job_id`، `succeeded`، `retry_count=1`، سند `parsed`؛ و بار دوم `/process` روی job موفق → `200` + `resubmitted=true` + بدون تغییر `retry_count` (idempotency حفظ است).

## ۶. نتیجه production

**بدون deploy** (مطابق AGENTS.md §۳: deploy مرحله جداست). نکته مهم: چون s52 اصلاً 14B را ندارد، deploy بعدی کل 14B + این رفع را یکجا می‌گیرد؛ هیچ نگران backward-compat با production فعلی نیست.

## ۷. پذیرش ایزوله (۲۷ گام، سرور واقعی)

`deploy/pcm14b_acceptance_local.py` — سرور واقعی (`python server.py`) روی `PCT_DB`+`PCT_KNOWLEDGE_DATA_DIR` موقت:

| فاز | گام‌ها | نتیجه |
|---|---|---|
| A (اجرا ۱) | login؛ کالکشن؛ آپلود ۲ DOCX فارسی با تأیید SHA-256؛ store پایدار `data/files`؛ process → job `succeeded`؛ ساختار/کیفیت/بلوک‌ها (raw+normalized)؛ فیلد متادیتا (document scope) + مقدار؛ approve | 14/14 ✅ |
| B (kill سخت → اجرا ۲) | re-login؛ اسناد+وضعیت (approved/uploaded) **بقا پس از restart**؛ artifacts قابل‌خواند؛ متادیتا **بقا**؛ process سند دوم **بعد از restart** → succeeded (worker زنده)؛ job کهنه ۲ ساعت → `interrupted` در درخواست بعدی (recovery §13)؛ **retry قرارداد:** `/process` روی سندِ job-interrupted → بازاجرا → parsed (F-A رفع شد)؛ endpoint سازگاری ES → صادقانه `NOT_VERIFIED` | 13/13 ✅ |

**جمع: 27/27.**

## ۸. SHA + لینک

- این commit: (پس از `430bfc7`)
- Parent: `430bfc7` (گزارش 14B)

## ۹. بکاپ / rollback

- **بکاپ:** لازم نیست (بدون تغییر DB production).
- **Rollback:** `git revert <این-commit>` — تغییر فقط در منطق `_submit_job` است؛ rollback آن، رفتار قبلی (stale row) برمی‌گرداند.

## ۱۰. موارد باقی‌مانده

| مورد | فاز |
|---|---|
| **رفع F-B:** اصلاح سطر ۸۱ گزارش 14B (حذف ادعای `GET /jobs/<job_id>`) — یا افزودن همان روت در 14C | 14C (docs) |
| deploy 14B + 14B.2 به s52 (اسکریپت `deploy/pcm14b_deploy.sh` هنوز نوشته نشده است) | قبل از 14C |
| PCM-14C — schema تطبیق‌شده + API تطبیق | بعدی |
| PCM-14D — index به ES واقعی + `es-verified` | بعدی |
| PCM-14E — Search + bulk delete + export | بعدی |
| PCM-15 — نمای کتابخانه و آمار واقعی | بعدی |

## ۱۱. روش تست دستی (lokal)

```bash
# 1) تمام تست‌ها (103):
cd backend && python -m unittest test_api test_projects test_dashboard test_word_factory test_knowledge_api -v

# 2) پذیرش ایزوله با restart واقعی (27 گام):
python deploy/pcm14b_acceptance_local.py

# 3) دستی: سرور را بچینید وسط پردازش (Ctrl+C وسط job)؛
#    دوباره start کنید → job در /api/knowledge/jobs باید 'interrupted' باشد
#    → روی سند «پردازش دوباره» بزنید → باید بازاجرا شود (202) و parsed شود.
```

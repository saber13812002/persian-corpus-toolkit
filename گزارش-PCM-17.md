# گزارش PCM-17 — تکمیل UI استودیو: مدیریت صف + رجیستری اثر‌ها

تاریخ: ۱۴۰۵/۰۸/۱۱ (2026-11-02) · شاخه: `main` · commit پایه: `80fef97` (PCM-16 report)

---

## A. خلاصه اجرایی

مأموریت «PCM-17 — تکمیل UI استودیو» انجام شد: دو بخش استودیو که در
PCM-14D و PCM-15 به‌صورت API ساخته شده بودند ولی در UI نبودند، ساخته
شدند — **کارت صف/بچ‌ها** (شمارنده‌های زنده + process/pause/resume +
polling هوشمند) و **کارت رجیستری اثر‌ها** (work/edition/volume +
اسناد) — به‌علاوه endpoint خواندنی افزایشی
`GET /api/knowledge/import/batches`، ستون «رجیستری» در جدول اسناد و
به‌روزرسانی نقشه‌ی راه استودیو. همه‌ی اعداد UI evidence-based و فقط از
REST واقعی می‌آیند؛ هیچ endpoint ساختگی، هیچ عدد تخمینی، و بدون deploy.

نتیجه‌ها:

1. **endpoint خواندنی جدید** (افزایشی): `GET /api/knowledge/import/batches?
   collection_id=&search=&page=&per_page≤100` — ردیف‌های بچ + پرچم
   `paused` هر بچ (از `knowledge_queue_control` با `EXISTS`) + شمارنده‌های
   زنده‌ی `queue` (همان `queue_counters` — سردبیر واحد با
   `queue/summary`). `LIMIT/OFFSET` + `ORDER BY created_at DESC, batch_id`.
2. **ستون رجیستری در فهرست اسناد:** `work_id/edition_id/volume_id` از
   `knowledge_list_documents` — سندِ پردازش‌نشده خالی می‌ماند (نه حدس).
3. **کارت صف/بچ‌ها** در `studio.html`: نوار ۶ شمارنده + جدول بچ‌ها با
   بج وضعیت/توقف‌شده + دکمه‌های پردازش/توقف/ادامه؛ polling هر ۳ ثانیه
   **فقط** وقتی `running > 0`؛ توقف polling هنگام تعویض/خروج کالکشن.
4. **کارت رجیستری** (ستون چپ): اثر جدید (مودال، title الزامی) →
   `POST /works`؛ فهرست/جستجو/صفحه‌بندی works با `edition_count`/
   `document_count`؛ جزئیات اثر + فرم ویرایش جدید؛ جزئیات ویرایش +
   جلد‌ها + اسناد وابسته + فرم جلد جدید (volume_no عدد یا null).
5. **نقشه‌ی راه استودیو:** شش ردیف همه «انجام شد» (PCM-14A..17).
6. **7 تست جدید** (S-01..S-04 در `backend/test_studio_api.py`) +
   رگرسیون کامل **182/182 سبز**.
7. **OpenAPI** (`docs/openapi/pcm15-file-queue.openapi.yaml`): path جدید
   + schema `ImportBatch`؛ در همین مرحله دو نقص YAML پیشین فایل
   (title بدون quote + indentation schema) هم پیدا و اصلاح شد و حالا
   کل فایل با PyYAML معتبر می‌شود (`YAML_VALID`).
8. سند طراحی: `docs/PCM-17-STUDIO-UI.md` + به‌روزرسانی
   `docs/WORD-STUDIO-KNOWLEDGE-GUIDE.md` / `readme.md` / `AGENTS.md`.
9. **بدون deploy:** اسکریپت چک خواندنی `deploy/pcm17_s52_readonly_check.sh`
   آماده شد ولی s52 در زمان این گزارش **ردیاب نبود** (بخش H/I) —
   هیچ ادعایی درباره‌ی وضعیت لحظه‌ای s52 نمی‌شود.

## B. وضعیت قبل از تغییر و ممیزی

- git: clean روی `80fef97` (= `origin/main`، commit گزارش PCM-16)؛
  رگرسیون 175 تست سبز.
- ممیزی موجود:
  - APIهای PCM-14D/15 (works/editions/volumes، process/pause/resume،
    queue/summary) کامل بودند ولی **هیچ UI** نداشتند: استودیو فقط
    کارت بیلدها با عبارت «این قابلیت در PCM-14D فعال می‌شود» داشت.
  - جدول اسناد (`knowledge_list_documents`) شناسه‌های رجیستری را
    SELECT نمی‌کرد؛ UI نمی‌توانست بدون فراخوانی تک‌تک جزئیات اسناد
    آن‌ها را نشان دهد.
  - هیچ endpointی برای **فهرست** بچ‌های یک کالکشن نبود (فقط ساخت/
    جزئیات/کنترل بچ) — کارت صف نیاز به `GET /import/batches` داشت.
- نتیجه ممیزی: فقط یک endpoint خواندنی افزایشی + تغییر SELECT فهرست
  اسناد + UI لازم است؛ **هیچ مهاجرت schema** و تغییر endpoint موجودی
  نیست.

## C. طراحی (خلاصه — کامل در `docs/PCM-17-STUDIO-UI.md`)

- `GET /import/batches`: `collection_id` الزامی (400/404)، `search` LIKE
  روی `batch_id`/`folder_name`، صفحه‌بندی با سقف `per_page=100`؛
  `paused` در همان SELECT با `CASE WHEN EXISTS(knowledge_queue_control
  WHERE scope='batch:'||batch_id AND paused=1)`؛ `queue.counters` =
  `queue_counters(db, cid)`؛ `failed_by_stage` از همان جدول صف.
- UI: همه‌ی fetchها همان الگوی `credentials: same-origin` + `escHtml`
  برای خروج‌های DOM (XSS — AGENTS §2-8)؛ اعداد فقط از پاسخ‌ها؛
  polling با timer قابل قطع (`state.queueTimer`) و `stopQueuePolling()`
  در `openCollection`/`backToTop`.
- rollback: حذف endpoint = rollback کامل (کد قدیمی route جدید را
  نمی‌شناسد؛ UI جدید فقط با کالکشن باز می‌شود و 404 را به‌عنوان
  پیام خطا نشان می‌دهد) — بدون schema/بدون داده.

## D. تغییرات کد و فایل

**جدید:**

| فایل | توضیح |
|-------|-------|
| `backend/test_studio_api.py` (373 خط) | 7 تست S-01..S-04 (شکل endpoint + 401/400/404 + pagination/search + paused + counters=DB + رجیستری اسناد با WF واقعی) |
| `docs/PCM-17-STUDIO-UI.md` | سند طراحی: endpoint، UI، سازگاری، ماتریس تست، محدودیت‌ها |
| `deploy/pcm17_s52_readonly_check.sh` | چک خواندنی s52 (بدون deploy/نوشتن) — آماده؛ اجرا نشد (s52 ردیاب نبود — بخش H) |

**تغییرکرده (کد):**

| فایل | تغییر |
|-------|-------|
| `backend/knowledge_api.py` (+64/−5) | `knowledge_list_batches` (GET /import/batches) + افزودن `work_id, edition_id, volume_id` به SELECT `knowledge_list_documents` |
| `dashboard/studio.html` (+374/−2) | کارت صف/بچ‌ها + کارت رجیستری + مودال اثر جدید + ستون رجیستری اسناد + نقشه‌ی راه + JS (loadQueue/batchAction/loadRegistry/renderWorkDetail/renderEditionDetail/addEdition/addVolume + polling) |
| `docs/openapi/pcm15-file-queue.openapi.yaml` | path `GET /api/knowledge/import/batches` + schema `ImportBatch` + توضیح PCM-17 در info + **اصلاح نقص YAML پیشین** (quote برای title با `:` و indentation بخش ImportBatch) |

**تغییرکرده (مستندات):** `readme.md` (ردیف قابلیت PCM-17، 10 test
files/182 تست، دستور رگرسیون، نقشه‌ی راه)، `AGENTS.md` (دستور رگرسیون
182، `test_studio_api.py` (7، S-01..S-04)، نقشه‌ی راه)،
`docs/WORD-STUDIO-KNOWLEDGE-GUIDE.md` (مراحل ۷ و ۸ راهنمای استودیو،
جدول‌های Import/صف + رجیستری اثر‌ها).

**وابستگی جدید: صفر.** (فقط HTML/JS/SQL موجود).

## E. نتایج تست

| مجموعه | تعداد | نتیجه |
|---------|:-----:|:------:|
| هسته (api/projects/dashboard) | 39 | ✅ |
| knowledge_api (KB-01..KB-14) | 40 | ✅ |
| word_factory (WF-01..WF-13 + on_stage) | 27 | ✅ |
| dump (D01..D15) | 26 | ✅ |
| work_registry (RD-01..RD-07) | 10 | ✅ |
| queue (Q-01..Q-08) | 9 | ✅ |
| corpus_builder (C-01..C-16) | 24 | ✅ |
| **studio_api (S-01..S-04)** | **7** | ✅ |
| **کل** | **182** | ✅ سبز (78.590s) |

پوشش S (همه E2E با pipeline واقعی Word Factory):

- **S-01a** — بدون auth → 401 (auth پیش از هر اعتبارسنجی پارامتر/کالکشن).
- **S-01b** — `collection_id` غایب → 400 با `field=collection_id`.
- **S-01c** — کالکشن ناشناخته → 404.
- **S-01d** — شکل ردیف‌ها (کلیدها + `paused=0` + `status=planned`) +
  pagination (پیش‌فرض 50، per_page=1 → 2 صفحه، سقف 100) + search
  مثبت/منفی + کلیدهای ۸ شمارنده‌ی `queue.counters`.
- **S-02** — `paused` در لیست: 0 → `POST /pause` → 1 → `POST /resume` → 0.
- **S-03** — بچ واقعی (good + corrupt) پردازش شد؛ `queue.counters`
  endpoint با **بازمحاسبه‌ی مستقیم از `knowledge_file_queue`** (فیلتر
  کالکشن) یکی‌یکی برابر + `failed_by_stage` + `processed_count`/
  `failed_count`/`status=done` خود ردیف batch.
- **S-04** — پیش از پردازش: `work_id/edition_id/volume_id` در فهرست
  اسناد موجود اما falsy؛ پس از پردازش واقعی WF: `work_id`+`edition_id`
  truthy و `volume_id` falsy (کتاب نمونه `volume_no` ندارد)؛
  cross-check با `GET /works/<work_id>` (همان work + همان edition در
  فهرست ویرایش‌ها).

اجرا (برای این گزارش اجرا شد — 2026-11-02):

```bash
cd backend
python -m unittest test_studio_api -v
  # Ran 7 tests in 4.756s — OK
python -m unittest test_api test_projects test_dashboard \
  test_knowledge_api test_word_factory test_dump test_work_registry \
  test_queue test_corpus_builder test_studio_api -v
  # Ran 182 tests in 78.590s — OK
```

در مسیر توسعه 1 کاستی در خود **تست** پیدا و اصلاح شد (نه از بین
بردن assertion): S-01a اولیه POST /collections را بدون auth می‌زد و
401 برمی‌گشت؛ شکل تست تغییر کرد به GET مستقیم endpoint جدید بدون
auth (assert 401) — assertion قوی‌تر و وابسته به endpoint تحت تست.

## F. سازگاری (compat) — جدول خلاصه

| مورد | وضعیت |
|------|--------|
| endpointهای موجود | بدون تغییر (فقط افزودن route GET؛ تست‌های همه ماژول‌ها سبز) |
| API نوشتاری اکستنشن (`/api/projects*`) | دست‌نخورده |
| قرارداد Dump d-1 / WF / پیکره‌ساز c-1 | دست‌نخورده (D/WF/C سبز) |
| صف PCM-15 / Registry PCM-14D | دست‌نخورده (Q/RD سبز)؛ endpoint جدید فقط **مصرف‌کنندهٔ خواندنی** همین جدول‌هاست |
| auth | endpoint جدید همان `require_auth` namespace knowledge |
| `dashboard/index.html` (داشبورد اصلی) | دست‌نخورده |
| schema DB | **بدون مهاجرت** (هیچ جدول/ستون جدید) |

## G. Git: commit و push

- **commit کد + مستندات:** `4b3a84c` (9 فایل، 1225+ / 25−) — بعد از
  `80fef97`، push بدون force.
- **GitHub:** `https://github.com/saber13812002/persian-corpus-toolkit` —
  SHA commit با `git ls-remote` تأیید می‌شود (بخش H).
- این گزارش (با ثبت SHA نهایی) در **commit دوم بلافاصله بعدی** ثبت
  می‌شود — همان رویه‌ی PCM-14C.3 / PCM-14D / PCM-15 / PCM-16.
- قبل از commit: `git diff --check` → بدون whitespace error (فقط
  هشدارهای CRLF→LF پیشین)؛ secret scan روی 9 فایل → **0 hit**
  (تنها «test-secret-123» — رمز آزمون در-memory، نه credentials
  واقعی)؛ `git status` → دقیقا‌اً 9 فایل PCM-17، بدون فایل اضافی.

## H. وضعیت Local / GitHub / s52

| محیط | وضعیت |
|------|-------|
| Local | `main` = `4b3a84c` (commit کد PCM-17)؛ working tree clean (بعد از commit گزارش) |
| GitHub | همگام با Local (تأیید با `git ls-remote`) |
| s52 | **در زمان این گزارش ردیاب نبود** — `ssh -p 22 saber@172.20.1.52` سه‌بار «Connection timed out» (2026-11-02، Asia/Tehran). آخرین وضعیت **مدرک‌شده** s52 از چک PCM-16 (2026-10-29): pre-PCM-14D، دست‌نخورده، DB سالم |

`deploy/pcm17_s52_readonly_check.sh` آماده است (همان الگوی PCM-16 +
markerهای PCM-17: `knowledge_list_batches` در `knowledge_api.py`،
`queueCard` در `studio.html`، و probe
`GET /api/knowledge/import/batches` — پیش از deploy باید 404 بدهد).
اجرای آن — به‌محض دستیابی به s52 — با:

```bash
ssh -p 22 saber@172.20.1.52 "bash -s" < deploy/pcm17_s52_readonly_check.sh
```

## I. تأیید عدم اختلال در production

- هیچ deploy، restart یا نوشتن روی s52 انجام **نشده** است (و در زمان
  گزارش اصلا‌اً قابل اتصال نبود).
- PCM-17 ماهیّتا‌اً **افزایشی و بدون مهاجرت** است: یک route GET خواندنی
  + ستون‌های موجود در SELECT + UI؛ حتی هنگام deploy آینده، خطری برای
  endpointهای نوشتاری اکستنشن و کراول زنده ندارد.
- deploy آینده (فقط با دستور صریح + بکاپ): بکاپ `thesaurus.db` +
  integrity_check → اسنپ‌شات deploy dir → کپی کد →
  `docker compose build backend && docker compose up -d backend` →
  health-wait + smoke. **توجه:** چون s52 آخرین بار pre-14D تأیید شده،
  deploy بعدی عملا‌اً 14C.3 + 14D + 15 + 16 + 17 را یکجا می‌رساند —
  همه‌ی مهاجرت‌ها افزایشی و idempotent و باید جداگانه smoke test شوند.

## J. محدودیت‌ها و ریسک‌ها

1. **هنوز deploy نشده** — مطابق قاعده‌ی مأموریت (بدون دستور صریح +
   بکاپ، deploy نمی‌شود).
2. **چک s52 در این فاز اجرا نشد** — server در زمان گزارش ردیاب بود؛
   اسکریپت آماده است و اجرای آن قبل از هر deploy الزامی است.
3. کارت buildها (ES) هنوز «خالی» است — ES در V0.1 غیرفعال است و
   endpoint سازگاری صادقانه‌‌ `NOT VERIFIED` می‌دهد.
4. پیکره‌های c-1 در استودیو نمایش داده **نمی‌شوند** — پیکره‌ساز
   offline CLI است و خروجی‌اش در دایرکتوری‌های محلی است، نه در DB؛
   نمایش آن‌ها نیاز به قرارداد ذخیره‌سازی جدا دارد (خارج از PCM-17).
5. retry فایل‌ناموفق فقط از endpoint (`/process` دوباره) در دسترس است؛
   دکمه‌ی مستقل retry در UI این فاز ساخته نشد.
6. polling هر ۳ ثانیه فقط با `running>0` فعال است — اگر browser tab
   در background باشد browser interval را کند می‌کند (رفتار استاندارد
  ؛ counterها در هر refresh بعدی واقعی‌اند).

## K. روش تست دستی (اپراتور)

```bash
cd backend
# 1) رگرسیون کامل (182 تست)
python -m unittest test_api test_projects test_dashboard \
  test_knowledge_api test_word_factory test_dump test_work_registry \
  test_queue test_corpus_builder test_studio_api -v
# 2) فقط استودیو (7 تست)
python -m unittest test_studio_api -v

# 3) آزمایش دستی در استودیو (بعد از deploy آینده، روی kالکشن نمونه):
#    a) چند DOCX آپلود و یک batch بسازید (یا آپلودها را process کنید)
#    b) کارت «صف/بچ‌ها»: شمارنده‌ها باید با خروجی
#       GET /api/knowledge/queue/summary?collection_id=... یکی باشند
#    c) «توقف» → بج «توقف‌شده» + در list paused=1؛ «ادامه» → پاک
#    d) کارت «رجیستری اثر‌ها»: «اثر جدید» + ویرایش + جلد؛ سپس یک
#       سند را process کنید → در جدول اسناد ستون «رجیستری» پر شود
#    e) endpoint جدید:
#       curl -H "Cookie: pct_session=..." \
#         'https://corpus.ai.ismc.ir/api/knowledge/import/batches?collection_id=c-...'
```

## L. فاز بعد

- **PCM-18** — ممیزی observability روی s52 (فقط-خوانده؛ بدون چاپ
  credential) + اجرای چک خواندنی PCM-17 به‌محض دسترسی به s52.
- **PCM-19** — به‌روزرسانی README/AGENTS/OpenAPI نهایی + نمونه client
  REST + تست قرارداد API + راهنمای اپراتوری + GitLab/CI + گزارش نهایی.

---

*این گزارش بخشی از مأموریت «ادامه PCM-14C تا تحویل پیکره» است؛
مستندات فنی کامل در `docs/PCM-17-STUDIO-UI.md`.*

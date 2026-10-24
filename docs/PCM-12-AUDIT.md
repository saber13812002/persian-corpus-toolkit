# PCM-12-AUDIT — ممیزی واقعی Persian Corpus Toolkit

- تاریخ: 1405/08/03 (2026-10-24)
- نوع: ممیزی **غیرمخرب** (بدون تغییر سرویس، DB، schema، crawl یا کوانت)
- شعب: `main` · آخرین Commit: `e804756` (هم‌راستا با `origin/main`) · Working tree: تمیز قبل از این مأموریت
- Production: `https://corpus.ai.ismc.ir` (nginx 443 → `127.0.0.1:5055` روی s52 = `172.20.1.52`)
- داشبورد: `/dashboard/`

## ۱. وضعیت Git واقعی (S0)

| مورد | مقدار (مشاهده‌شده) |
|---|---|
| Branch | `main` |
| HEAD | `e804756` |
| Working tree | پاک (بدون تغییر) |
| origin | `https://github.com/saber13812002/persian-corpus-toolkit` |
| آخرین report در مخزن | `گزارش-PCM-05.md` (SHA `e182684`) |
| مسیر production | `/home/saber/saberprojects/persian-corpus-toolkit` (کپی کد — **نه** git repo) |
| DB production | `backend/thesaurus.db` (bind-mount به `/data/thesaurus.db`) |
| بکاپ‌ها | `/home/saber/backups/` (`thesaurus-<TS>.db` + `pct-deploy-<TS>.tar.gz`) |

سوابق PCM: PCM-01..05 ✅ (گزارش PCM-03/04/05 در مخزن)، PCM-06..10 ⏳ (طراحی‌شده در `AGENTS.md` roadmap).

## ۲. ساختار واقعی کد (چه چیزی واقعاً موجود است)

### 2.1 Backend (Flask 3.1.1 + SQLite WAL، port 5055)

| فایل | نقش واقعی | شواهد کلیدی |
|---|---|---|
| `backend/server.py` (1494 خط) | API اصلی + schema + harvesting | `init_db()`: جداول `crawl_queue`، `crawled_data`، `crawl_progress` + migration افزایشی؛ `ensure_khamenei_schema()`: `khamenei_speeches`؛ `content_hash()` SHA-256؛ `upsert_page_items()` (dedup روی content_hash: inserted/updated/skipped)؛ `_HARVEST_JOB` + `_run_elastic_harvest()` (harvest سمت سرور از `thesaurus.eiis.iki.ac.ir/fa/api/elastic/search` با cursor `elastic://thesaurus/<science>` و resume) |
| `backend/projects.py` (332) | سیستم پروژه‌های crawl v3.5 | `projects` / `project_points` / `project_pages`؛ resume با `cursor_url`؛ `pages_per_minute` (1..12)؛ نقاط با منبع css/xpath/url/url_param + transforms |
| `backend/auth.py` (237) | احراز هویت داشبورد (PCM-09) | `auth_meta` (scrypt hash)، `auth_sessions` (توکن 32 بایتی، 7 روز)، `auth_rate` (5 شکست/10 دقیقه/IP)؛ کوکی `pct_session` HttpOnly/Secure/SameSite=Lax؛ بدون seed رمز = dev mode open |
| `backend/dashboard_api.py` (246) | API خواندنی داشبورد (PCM-04/05) | `@require_auth`؛ سفیدفهرست sort؛ LAG/LEAD برای prev/next هم‌راستا با مرتب‌سازی |
| `backend/sites.py` (227) | سایت‌های seed + تگ‌های صفحه | `sites`/`site_fields`/`captures`؛ seed سایت «تفسیر تسنیم همتا» (surah/ayah/arabic/translation/content/volume/page/url) |
| `backend/sciences.py` | علوم/دسته‌های thesaurus | seed علوم برای harvest |
| `backend/Dockerfile` | python:3.12-slim، 6 فایل py | فقط `flask==3.1.1` + `flask-cors==6.0.1` |
| `docker-compose.yml` | فقط یک سرویس `backend` | `PCT_DB=/data/thesaurus.db`؛ `PCT_DASHBOARD_PASSWORD` از `.env` (gitignored) |

### 2.2 Chrome Extension (MV3 v3.5)

- `extension/manifest.json`: permissions `activeTab, storage, scripting, tabs, alarms`؛ `host_permissions: <all_urls>`
- content scripts: thesaurus (2 فاز)، khamenei، picker
- `background.js`: orchestration crawl + submit به APIها
- **APIهای نوشتاری اکستنشن (`/api/projects*`، `/api/phase2/*`، `/api/submit-result`...) باز و بدون auth می‌مانند** (قانون §2.6 AGENTS.md — کراول زنده نباید قطع شود).

### 2.3 Corpus pipeline (batch، سمت سرور/محلی)

| فایل | نقش |
|---|---|
| `corpus/pipeline.py` | ارجاع به build_corpus → build_dataset → (اختیاری) HF upload |
| `corpus/build_corpus.py` | خواندن `crawled_data` → `thesaurus_raw_corpus.txt` / `thesaurus_corpus.jsonl` / `thesaurus_terms.txt` + README HF |
| `corpus/build_dataset.py` | ساخت dataset |
| `corpus/upload_to_hf.py` | آپلود HuggingFace |
| `corpus/scrape_khamenei.py` | اسکرپر مستقل سخنرانی‌ها (discover از list pages → استخراج regex شامل تاریخ جلالی → submit به backend؛ resume از pending queue) |

### 2.4 Dashboard

- `dashboard/index.html`: تک‌صفحه‌ای بدون framework؛ fetch با `credentials: same-origin`؛ 401 → overlay ورود
- تب‌های موجود: وضعیت پ이프لاین، پروژه‌ها (فهرست/جزئیات/صفحه‌بندی PCM-05)، صفحات پروژه (prev/next)

### 2.5 Deploy

- الگوی استاندارد (نمونه `deploy/pcm05_deploy.sh`): pre-state → `sqlite3 .backup` + `PRAGMA integrity_check` → snapshot tar (بدون DB) → extract → `docker compose build backend && up -d backend` → health-wait → smoke auth (401 بدون کوکی / 200 با کوکی) → smoke endpointهای جدید → regression نوشتاری + cleanup
- nginx conf: `deploy/nginx-corpus.vhost.conf` (443 ssl → 127.0.0.1:5055)
- `deploy/persian-corpus.service` (systemd، جایگزین داکر)

## ۳. جدول قابلیت‌ها (حقیقت در مقابل طراحی)

وضعیت: ✅ IMPLEMENTED · 🟡 PARTIAL · 📋 PLANNED · ❌ MISSING · ⛔ BLOCKED · ❓ NOT VERIFIED

| # | قابلیت | وضعیت | شواهد واقعی | فعال در production؟ | قابل‌استفاده برای معماری جدید؟ | تغییر لازم |
|---|---|---|---|---|---|---|
| 1 | Crawl مرورگری 2 فاز (thesaurus) | ✅ | `server.py: phase1/phase2` + extension content_thesaurus | بله (baseline PCM-03: 1099 crawled) | بله، الگوی dedup (SHA-256) | الگو را به factory Word تعمیم بده |
| 2 | سیستم پروژه‌های crawl v3.5 | ✅ | `projects.py`؛ جداول projects/project_points/project_pages | بله (پروژه 2 «تفسیر تسنیم همتا» در زمان PCM-05 در حال crawl، 372→374) | بله، ساختار نقطه/صفحه | افزودن additive: نوع «کتاب» به‌عنوان پروژه |
| 3 | Dedup با content hash | ✅ | `content_hash()` + `upsert_page_items()` | بله | کاملاً | تعمیم به فایل‌های Word (file-level hash) |
| 4 | Resume با cursor | ✅ | `cursor_url` در projects؛ cursor `elastic://` در harvest | بله | کاملاً | الگو را برای download resume بکار بگیر |
| 5 | Auth داشبورد (scrypt + session + rate limit) | ✅ | `auth.py`؛ PCM-09 | بله | کاملاً (برای بخش‌های جدید داشبورد) | گسترش role (فقط additive) در صورت نیاز |
| 6 | API خواندنی داشبورد + صفحه‌بندی + sort whitelist | ✅ | `dashboard_api.py` | بله | کاملاً | افزودن endpointهای جدید با همان الگو |
| 7 | Harvest سمت سرور (thesaurus elastic) با resume | ✅ | `_run_elastic_harvest()` + job thread + status | بله (سرویس زنده) | الگوی worker تکی + status | الگو → worker مستقل factory |
| 8 | Corpus builder (JSONL/tx) از crawled_data | ✅ | `corpus/build_corpus.py` | خیر (batch دستی) | بله (خروجی JSONL) | ورودی را به فایل Word/JSON ساختاریافته تعمیم بده |
| 9 | اسکرپر مستقل کhamenei با rate limit + resume | ✅ | `scrape_khamenei.py` | خیر (batch) | الگو | — |
| 10 | **Elasticsearch عملیاتی برای PCT** | ❌ MISSING | s52: تنها `taghrir-es` (8.13.4) = **Exited (143) سه روز پیش**، listener 9200 ندارد، volume `taghrir-es-data` = 1.508GB | خیر | volume/تصویر قابل بازسازی | **ایجاد ES جدید (یا اطمینان از مجوز استفاده از ES موجود سازمانی)** — سؤال J |
| 11 | **دریافت فایل Word از کتابخانه قائمیه** | ❓ NOT VERIFIED | دامنه‌های حدس‌زده‌شده (kitoobqaemeya.com، qaemiyeh.ir، qaimiyyah.ir و ...) از **هر دو شبکه** (Windows محلی و s52) resolve نمی‌شوند؛ در رپازیتوری/سرور هیچ ارجاعی به سایت پیدا نشد | خیر | — | **URL دقیق سایت لازم است** — سؤال J؛ تا آن زمان طراحی بدون فرض درباره فرمت |
| 12 | DOC/DOCX parser در toolkit | ❌ MISSING | هیچ کد docx در repo (فقط dashboard doc به‌عنوان ارجاع) | خیر | — | V0.1: افزودن `python-docx` (DOCX) / برای `.doc` تبدیل به DOCX لازم |
| 13 | Queue پایدار / Worker مستقل / Scheduler | ❌ MISSING (فقط الگو) | تنها «کوانت» واقعی: `crawl_queue` (فاز1) + thread تکی `_HARVEST_JOB` در memory (با restart از بین می‌رود) | خیر (فاز1 queue = crawl مرورگری) | جدول crawl_queue به‌عنوان نمونه الگو | طراحی S3: DB-based durable queue (گزینه A) |
| 14 | Celery/RabbitMQ/Redis برای PCT | ❌ MISSING | s52: فقط `gitlab-redis` (redis:7، متعلق به GitLab) — **متعلق به PCT نیست**؛ Celery/RabbitMQ برای PCT وجود ندارد | خیر | — | بدون نصب جدید: گزینه A (SQLite queue) |
| 15 | Knowledge Registry (کتاب/نسخه/کلیپ) | ❌ MISSING | — | خیر | — | طراحی S5، پیاده در V0.5 |
| 16 | RAG Registry | ❌ MISSING | — | خیر | — | طراحی S5، پیاده در V0.5 |
| 17 | RAG engine متعلق به PCT | ❌ MISSING (محدوده) | RAGها موجود s52 متعلق به پروژه‌های **مستقل** دیگرند (AGENTS.md §1): `automated/export-sql-chromadb` (mesbahyazdi→Chroma)، `graph-rag`، moshat، Flowise، Open WebUI | خیر | **فقط contract یکپارچه‌سازی** — تغییر ممنوع | قرارداد S6/S7 |
| 18 | LiteLLM (موجود s52) | 🟡 موجود/متعلق به زیرساخت سازمانی | 3 اینسانس: 4000 (زنده)، 4101 (زنده)، 4102 (مرده)؛ `/model/info` فقط با auth (401)؛ مدل‌ها: whisper-persian-v4، bge-m3 (172.30.0.117:8001)، mxbai-embed-large (ollama .53:11434)، Qwen3-Embedding-4B/0.6B (.53:4000/4001)، qwen38 (Qwen3.8-27B-FP8 SGLang .53:8000/8001)، gpt-4o، deepseek-chat؛ `drop_params: true` | بله (برای مصرف‌کننده‌های دیگر) | بله به‌عنوان **LLM/Embedding gateway** (نه RAG engine) | فقط مصرف با مجوز؛ تغییر config ممنوع |
| 19 | Observability (Prometheus/Grafana/Loki) | 🟡 موجود، خالی برای PCT | Prometheus 2.55.0 (9090)، Grafana 11.3.0 (3001، **دایرکتوری dashboards خالی**، provisioning موجود)، Loki 3.2.0 (3100)، node-exporter 9100 | بله (زیرساخت) | کاملاً — **باید از همین‌ها استفاده شود** (قانون S9: بدون infra موازی) | افزودن Prometheus endpoint در backend (V1.0) + 4 داشبورد |
| 20 | Backup/rollback | ✅ | الگوی PCM-03..05 + `/home/saber/backups/` | بله (با هر deploy) | کاملاً | تعمیم: بکاپ فایل‌های کتاب + snapshot ES |
| 21 | **فضای دیسک s52** | ⛔ BLOCKED (ریسک عملیاتی) | root disk: 686G کل، 657G مصرف‌شده، **819M آزاد (100% full)** | — | — | **پیش‌نیاز آزادسازی/گسترش دیسک** قبل از هر بارگذاری فایل کتاب — سؤال J |
| 22 | RAM/CPU s52 | ✅ کافی‌به‌نظر | 23Gi RAM (9.7Gi آزاد)، 10 CPU | بله | بله | ظرفیت‌سنجی workerها روی همین اعداد |
| 23 | APIهای نوشتاری باز (اکستنشن) | ✅ | `/api/projects*`، `/api/phase2/*`، `/api/submit-result` بدون auth | بله (کراول زنده) | باید دست‌نخورده بماند | — |
| 24 | Test suite | ✅ | 39/39 سبز (PCM-05): `test_api.py` + `test_projects.py` + `test_dashboard.py` | بله | کاملاً | افزودن تست factory/queue در V0.1..0.3 |

## ۴. زیرساخت s52 — وضعیت واقعی (مشاهده 1405/08/03، غیرمخرب)

### 4.1 Containers مرتبط با PCT
| container | وضعیت |
|---|---|
| `persian-corpus-backend` (compose) | زنده، 5055، کراول زنده |
| `taghrir-es` (elasticsearch:8.13.4) | **Exited (143)** — متعلق به پروژه دیگر (taghrir)؛ volume 1.508GB؛ listener 9200 فعال ندارد |

### 4.2 اینسانس‌های LiteLLM و مدل‌ها (فقط شناسایی، بدون تغییر)
- 4000: زنده · 4101: زنده · 4102: مرده
- مدل‌های ثبت‌شده در config: `whisper-persian-v4`، `bge-m3` (ریموت 172.30.0.117:8001)، `mxbai-embed-large` (ollama 172.20.1.53:11434)، `Qwen3-Embedding-4B` (.53:4000)، `Qwen3-Embedding-0.6B` (.53:4001)، `qwen38` (Qwen3.8-27B-FP8، SGLang روی GPU server 172.20.1.53:8000/8001)، `gpt-4o`، `deepseek-chat`؛ `drop_params: true`
- نتیجه: **gateway LLM/Embedding قوی موجود است** — PCT می‌تواند فقط به‌عنوان مصرف‌کننده (با API key مجاز) متصل شود.

### 4.3 پروژه‌های RAG/ML مستقل (محدوده — دست‌نخورده، AGENTS.md §1)
| پروژه | ماهیت | نکته برای contract |
|---|---|---|
| `automated/export-sql-chromadb` | dump MySQL `book_pages` از mesbahyazdi.ir (ستون‌ها: `id, book_id, book_title, section_id, section_title, page_id, page_text (HTML), link, error`) + اسکریپت‌های خروج ChromaDB + web_service | **همین الگو، الگوی قبلی سازمانی «کتاب صفحه‌به‌صفحه» است** — برای آشنایی با مدل داده؛ PCT نباید روی این dump تکیه کند، اما می‌تواند با contract استاندارد (chunk JSON) ادغام شود |
| `graph-rag` | Neo4j | خارج از محدوده |
| `mesbah-meshkat-...` (moshat) | FastAPI 8601 + Streamlit 8602 + SQLite، word-search | خارج از محدوده |
| Flowise 3.0.5 (3004)، Open WebUI (3005)، n8n (5678) | ابزارهای عمومی سازمان | خارج از محدوده؛ ممکن است بعداً مصرف‌کننده RAG Registry باشند |
| `ai_ismc_ir` (Shahrbano CMS) | Laravel/Next.js | خارج از محدوده |

### 4.4 Observability
- Prometheus 2.55.0 :9090 (rules/ موجود) · Grafana 11.3.0 :3001 (dashboards **خالی**، provisioning dashboards+datasources موجود) · Loki 3.2.0 :3100 · node-exporter :9100
- نتیجه: **زیرساخت کامل است، فقط داشبورد/endpoint کم دارد** → V1.0 بدون نصب چیز جدید.

## ۵. خلاصه S1 — دریافت کتاب Word از کتابخانه قائمیه

- **URL سایت: ❓ NOT VERIFIED** — هیچ دامنه حدس‌زده‌شده از هیچ شبکه‌ای resolve نشد؛ در کل رپازیتوری و دایرکتوری‌های s52 هیچ ارجاعی به سایت قائمیه نبود.
- egress سرور s52 **سالم است** (example.com و mesbahyazdi.ir → 200) → مشکل از شبکه نیست، URL واقعاً ناشناخته است.
- نتیجه: طراحی Downloader (بخش S1 در PRD) **بدون فرض از سایت** نوشته شده و با 8 سؤال صریح (فرمت DOC/DOCX، ساختار بایوگرافیایی، چندجلدی بودن، ثبات URL، resume، لایسنس، API رسمی، rate limit) شروع می‌شود که بعد از دریافت URL باید تکمیل شوند.
- الگوی قبلی موجود در سازمان (mesbahyazdi `book_pages`) نشان می‌دهد مدل داده «کتاب/بخش/صفحه» در سازمان ریشه دارد — مدل پیشنهادی PCM-12 آن را تعمیم‌دهی می‌کند (Work/Edition/Volume/File).

## ۶. ریسک‌های عملیاتی فوری (مستقل از PCM-13)

1. ⛔ **دیسک s52 = 100% پر (819M آزاد)** — خطر قطع هر سرویسی شامل PCT. هر بارگذاری فایل کتاب یا ES جدید **پیش‌نیاز آزادسازی دیسک دارد**.
2. ⛔ ES عملیاتی برای PCT وجود ندارد؛ شروع V0.2 (تست ES روی یک کتاب) نیاز به تصمیم (J): ES جدید مستقل PCT (container کوچک، volume جدا) در مقابل استفاده از ES سازمانی.
3. ⛔ URL سایت قائمیه ناشناخته → S1/Q1.
4. 🟡 `_HARVEST_JOB` تکی in-memory: با restart backend، job از بین می‌رود (resume فقط از cursor DB) — برای معماری جدید باید با worker پایدار جایگزین شود (S3).

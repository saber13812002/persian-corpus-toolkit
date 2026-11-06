# PCM-20.6 — SUBTASK 01: BASELINE تازه‌نفس (read-only)

> **مأموریت:** وضعیت‌سنجی کاملِ read-only از ریپازیتوری محلی + ۴ سرور (s52/s53/s113/s117) + ۳ دامنه‌ی `*.ai.ismc.ir` + داده‌های محلی پیکره‌ی تسنیم، پیش از توسعه‌ی (الف) وبسایت `tasnim.ai.ismc.ir` و (ب) کلکشن RAG در `rag.ai.ismc.ir`.
>
> **زمان بررسی:** 2026-11-06 11:20 تا 12:05 (Asia/Tehran, +03:30) / `2026-11-06T07:20Z–08:35Z`
> **حالت:** صرفاً read-only — هیچ نوشتاری روی هیچ سرور، هیچ deploy، هیچ توقف container، هیچ push/commit/branch.
> **محیط اجرا:** Windows 10, cmd.exe, `c:/Users/s.tabatabaei/Documents/saberprojects/persian-corpus-toolkit`, Python از `.venv`
> **اسکریپت‌های probe (برای پاکسازی پس از تأیید گزارش):**
> `.tmp_pcm206_baseline_s53_probe.sh` · `.tmp_pcm206_baseline_s53_probe2.sh` · `.tmp_pcm206_baseline_s53_probe3.sh` · `.tmp_pcm206_baseline_domains.ps1` · `.tmp_pcm206_baseline_s52tcp.ps1` · `.tmp_pcm206_baseline_regkeys.ps1` · `.tmp_pcm206_baseline_dataverify.py` (+ خروجی‌های `*_out.txt`/`*_out.json`)
>
> **منابع زمینه‌ای خوانده‌شده (گام اجباری اول):** `AGENTS.md`، `readme.md`، `گزارش-PCM-20.md`، `گزارش-PCM-20.2.md`، `docs/PCM-20.3-TASNIM-FORFACTORY.md`، `docs/PCM-20.4-TASNIM-ACCEPTANCE.md`، `گزارش-PCM-20.5-GATE0.md`، `گزارش-PCM-20.5-GATE1.md`، `گزارش-PCM-20.5-READINESS.md`، `گزارش-PCM-18.md`، `.tmp_pcm205_readiness_s1.json`، `deploy/pcm20_tasnim_export.py`، `deploy/nginx-corpus.vhost.conf`

---

## ۱. وضعیت محلی (local)

### 1.1 Git محلی

دستور: `git status --short` / `git log --oneline -3` / `git remote -v`

```text
A  .tmp_pcm205_readiness_s1.json
A  .tmp_pcm205_readiness_s1_probe.py
A  "گزارش-PCM-20.5-READINESS.md"
?? .tmp_pcm206_baseline_*  (9 فایل جدید این مأموریت)

11233e9 GATE 1 (PCM-20.5) — **PASS**، کامل شد؛ کاملاً offline، بدون deploy و بدون git commit.
f314de5 PCM-20.4: report section F backfill ...
1b79f9a PCM-20.4: real-world acceptance of the Tasnim end-to-end chain ...
```

| فیلد | مقدار |
|---|---|
| شاخه | `main` |
| HEAD | **`11233e984fcb7ac5f1b7b68b5e6f81e3acfce54d`** («GATE 1 (PCM-20.5) — PASS»، 2026-11-05 18:52:26 +0330) |
| commit‌های staging | ۳ فایل staged (افزوده به index، **commit نشده**): خروجی/اسکریپت/گزارش PCM-20.5 READINESS |
| untracked | ۹ اسکریپت/خروجی `.tmp_pcm206_baseline_*` این مأموریت |
| remote | فقط `origin` (GitHub) — **هیچ remote‌ای برای GitLab داخلی تعریف نشده** |

### 1.2 ساختار کد محلی

- ماژول‌های `corpus/tasnim/` (۱۳ ماژول + `__init__`): `cli.py`, `common.py`, `dataset.py`, `diff.py`, `dump.py`, `manifest.py`, `normalize.py`, `reconcile.py`, `schema.py`, `semantic.py`, `transform.py`, `validate.py`, `versioning.py` — موجود و دست‌نخورده.
- `backend/` — ۱۱ ماژول تستی (بک‌اند Flask + SQLite).
- داده: `data/tasnim/{pcm20_4, pcm20_5, pcm20_5_crossroot}` — جزئیات در بخش ۱۰.
- `.venv/` موجود (تست‌ها با `.venv\Scripts\python.exe` اجرا شد).

### 1.3 رگرسیون ۲۰۰ تست بک‌اند (baseline تست)

دستور: `cd backend && ..\.venv\Scripts\python.exe -X utf8 -m unittest test_api test_projects test_dashboard test_knowledge_api test_word_factory test_dump test_work_registry test_queue test_corpus_builder test_studio_api test_api_contract`

```text
----------------------------------------------------------------------
Ran 200 tests in 80.265s

OK
```

**نتیجه: 200/200 PASS, 0 FAIL, 0 SKIP** — فقط ResourceWarningهای بی‌ضرر (فایل‌های بسته‌نشده در تست‌ها).

همچنین رگرسیون پیکره:

```text
.venv\Scripts\python.exe -X utf8 -m unittest test_corpus_tasnim test_corpus_semantic
Ran 27 tests in 6.000s
OK
```

**جمع کل سبز: 227 تست** (200 بک‌اند + 27 پیکره/سمانتیک) — مطابق انتظار PCM-20.5 READINESS.

### 1.4 تأیید SHA-256 همه‌ی اشیاء داده (مقایسه با ممیزی S1)

اسکریپت: `.tmp_pcm206_baseline_dataverify.py` (read-only) — هر SHA ثبت‌شده در `.tmp_pcm205_readiness_s1.json` را از نو محاسبه کرد:

```text
RESULT=ALL_MATCH  CHECKS=33
```

۳۳ چک = اسنپ‌شات (۴ فایل) + ۷ corpus build (۱۶ فایل) + ۶ dataset manifest + ۱۲ فایل dump + ۳ registry — **همه مطابقت کامل**. خروجی کامل: `.tmp_pcm206_baseline_dataverify_out.json`.

### 1.5 parse_barg — وضعیت باگ PCM-20.2

- **کد اصلاح‌شده (مرجع رسمی):** [`corpus/tasnim/common.py`](../corpus/tasnim/common.py) تابع `parse_barg_all_runs` (خط ۵۱): همه‌ی ریک‌های ارقام را پس از نرمال‌سازی فارسی/عربی→ASCII می‌چسباند؛ جداکننده‌های هزارگان (٬ ، -) بی‌اثر می‌شوند.
- **تست رگرسیونی:** [`test_corpus_tasnim.py`](../test_corpus_tasnim.py) `test_t10c_barg_reparse_fixed` (خط ۵۵۰): `parse_barg_all_runs("۳۹٬۰۰۵") == 39005`، `"1,024" == 1024` — **سبز** (در ۲۷ تست بالا).
- **تست صحنه‌ای:** همان فایل، خط ۲۳۲: برای رکورد `item_index=19` (برگ «۳۹٬۰۰۵») مقدار `p19["barg"] == 39005` — **سبز**.
- نسخه‌ی باگ‌دار قدیمی (`parse_barg` در `deploy/pcm20_tasnim_export.py` خط ۶۲ — فقط اولین ریک) باقی مانده چون اسکریپت خروجی PCM-20 تاریخی است و در خط تولید فعلی (factory) به‌کار نمی‌رود.

### 1.6 شواهد ۲۸ صفحه‌ی مرز ۲۰۰۰ (truncated_at_2000)

فایل: [`data/tasnim/pcm20_4/validation/gate1_5_truncation_conclusion.json`](../data/tasnim/pcm20_4/validation/gate1_5_truncation_conclusion.json) (SHA-256 محلی: `b0f45e9381db78da8a16b8e577038e2de8a8897f0c59c38b01cf1dc192d5158d`)

- **نتیجه درسی: PASS** — هیچ حلقه‌ای از Export/Crawl/Factory متن را قطع نمی‌کند؛ مرز ۲۰۰۰ **ویژگی خود منبع** است (سقف chunk شاخص RAG سایت `tasnim.hamtaa.org`).
- ۴ شاهد (E1–E4): نبود truncation در کد مسیر داده؛ نبود pile-up آماری در مرز (28 رکورد در دقیقاً 2000 در مقابل 288 در 1990–1999)؛ هم‌توزیع بودن پایان‌ها؛ **مقایسه زنده با API سایت** (`GET /api/v1/files/tasnim/chunk-detail?item_index=N`): item 39137 و 66532 هر دو در زنده هم 2000 کاراکترند.
- **برای نمونه‌برداری زنده‌ی بعدی (PCM-20.6):** endpoint = `https://tasnim.hamtaa.org/api/v1/files/tasnim/chunk-detail?item_index={N}`؛ نمونه‌های مرزی ثبت‌شده: `39137, 66532` (دقیقاً ۲۰۰۰) + کنترل‌ها `41, 67125, 91028`.

---

## ۲. GitHub (origin)

دستور: `git ls-remote origin main` / `git remote -v`

```text
f314de544601fb0d7753e6199c9bd748cb25ef1a    refs/heads/main
origin  https://github.com/saber13812002/persian-corpus-toolkit.git
```

| فیلد | مقدار |
|---|---|
| remote | `origin` → `https://github.com/saber13812002/persian-corpus-toolkit.git` |
| HEAD `main` روی GitHub | **`f314de544601fb0d7753e6199c9bd748cb25ef1a`** («PCM-20.4: report section F backfill …») |
| انحراف | **محلی ۱ commit جلوتر از origin** (`11233e9` commit نشده‌ی GATE 1 است؛ push نشده) |

⚠️ این انحراف **منتظر اراده‌ی کاربر است** (PCM-20.5 عمداً بدون commit/push تمام شد). هیچ عملی در این مأموریت انجام نشد.

---

## ۳. GitLab داخلی (s52:2222)

**BLOCKED** — با دو دلیل مستقل:

1. **هیچ remote‌ای** برای GitLab روی git محلی تعریف نشده (خروجی `git remote -v` فقط `origin` است).
2. **هست خود s52 در دسترس نیست** — پروب TCP تازه‌گرفته‌شده در همین مأموریت (`.tmp_pcm206_baseline_s52tcp.ps1`، 2026-11-06 11:53 +0330، timeout 5s هر پورت):

```text
s52 172.20.1.52:2222 = TIMEOUT/CLOSED
s52 172.20.1.52:22   = TIMEOUT/CLOSED
```

مطابق تاریخچه: PCM-20.4 (خط ۲ commit `f314de5`) «GitLab internal s52:2222 re-confirmed unreachable (no transfer, no claims)».
**نتیجه:** SHA/وضعیت مخزن GitLab داخلی **UNKNOWN** — قابل ادعا نیست.

---

## ۴. سرور s52 (172.20.1.52)

**BLOCKED — کل هاست بی‌دسترس.**

دستور: `ssh -o ConnectTimeout=10 -o BatchMode=yes -p 22 saber@172.20.1.52 "echo REACHABLE"`

```text
ssh: connect to host 172.20.1.52 port 22: Connection timed out
```

پرواب TCP همه‌ی پورت‌های کلیدی (timeout 5s):

```text
s52 172.20.1.52:22    = TIMEOUT/CLOSED   (SSH)
s52 172.20.1.52:2222  = TIMEOUT/CLOSED   (GitLab)
s52 172.20.1.52:443   = TIMEOUT/CLOSED   (nginx/HTTPS)
s52 172.20.1.52:80    = TIMEOUT/CLOSED   (nginx/HTTP)
s52 172.20.1.52:4000  = TIMEOUT/CLOSED   (سابقاً LiteLLM)
s52 172.20.1.52:5055  = TIMEOUT/CLOSED   (بک‌اند PCT)
```

تاریخچه‌ی یکسان در `گزارش-PCM-18.md` (۵× Connection timed out) و `گزارش-PCM-20.5-READINESS.md` (همه‌ی پورت‌ها down).

**پیامدها (هر چه روی s52 است، در این baseline قابل مشاهده نیست):**
- deploy production PCT (`/home/saber/saberprojects/persian-corpus-toolkit` روی s52) — UNKNOWN
- `thesaurus.db` production — UNKNOWN
- **باز-crawl زنده‌ی 45,243 صفحه‌ی گمشده‌ی `item_index`** — BLOCKED (نیازمند s52؛ جزئیات بخش ۱۰.۵)
- وضعیت مخزن GitLab s52:2222 — UNKNOWN (بخش ۳)

---

## ۵. زیرساخت سرورها (نمای کلی)

| هاست | IP | دسترسی SSH | CPU | RAM | دیسک | load | وضعیت |
|---|---|---|---|---|---|---|---|
| **s52** | 172.20.1.52 | ❌ timeout | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | **BLOCKED / offline** |
| **s53** (hostname `llm`) | 172.20.1.53 (+ tailscale 100.72.7.26) | ✅ `ssh -p 22 saber@` | 40× Intel Xeon Gold 6458Q | 117 GiB (39Gi used / 78Gi available) | 1.5 TB (1.1T used, **295G free**, 80%) | 4.26 (uptime 9 روز) | **آزنده و باردار** |
| **s113** | 172.20.1.113 | ❌ timeout | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | **BLOCKED / offline** |
| **s117** | 172.20.1.117 | ❌ timeout | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | **BLOCKED / offline** |

> s113/s117: هر ۶ پورت (22/2222/443/80/4000/5055) `TIMEOUT/CLOSED` — همان جدول `.tmp_pcm206_baseline_s52tcp.ps1`.
>
> یادداشت PCM-20: s113 زمانی با نام «AI-TOOLS» و IP `172.30.0.113` برای export زنده استفاده می‌شد؛ اکنون در هیچ‌یک از دو فضای IP قابل دسترس نیست.

### 5.1 s53 — GPU (H100)

دستور: `nvidia-smi --query-gpu=...`

```text
0, NVIDIA H100 80GB HBM3, 81559 MiB, 74991 MiB, 6091 MiB, 100 %
1, NVIDIA H100 80GB HBM3, 81559 MiB, 66878 MiB, 14203 MiB, 100 %
```

**s53 = هاست H100.** هر دو GPU تقریباً پر (GPU0: 92% VRAM؛ GPU1: 82%) — مدل‌های vLLM همیشه‌روشن.

### 5.2 s53 — containerهای Docker (از `docker compose ls` / `docker ps`، probe 1 و 2)

| container/stack | پورت‌ها | وضعیت |
|---|---|---|
| `vllm-embedding` (compose `embedding-deployment`) | 4000 | Up (HTTP 200) |
| `vllm-embedding-06b` | 4001 | Up (HTTP 200) |
| `ollama` | 11434 | Up |
| vLLM LLM (Qwen3.8-27B-FP8) | 8000 / 8001 | Up (HTTP 200) |
| `neo4j` (neo4j:2025.10.1-enterprise) | 7474 / 7687 | **Up 5 روز, healthy** |
| `qdrant` (v1.19.1) | 6333 | Up (healthz passed؛ `/collections` API-key می‌خواهد) |
| `mock-litellm` | 9001 | Up |
| `ragportal` api / frontend | 8033 / 8034 | Up |
| QA stacks: mesbah / eiis / taghrir / sources / radio | 8003/8004 · 8013/8014 · 8023/8024 · 8053/8054 · 8043/8044 | Up |
| feedback Postgres | 5436/5446/5456/5466/5477 | Up |
| `kong-gw-oss` (Kong) + Tyk self-managed | gateway | موجود (API admin بدون اعتبارسنجی پاسخ نداد) |
| `h200-public-tunnel` (cloudflared) | — | Up (تونل عمومی) |

**nginx روی host s53 وجود ندارد** — مسیریابی عمومی با Kong/Tyk + cloudflared انجام می‌شود (در مقابل الگوی `deploy/nginx-corpus.vhost.conf` که nginx-host + Let's Encrypt است).
**هیچ کپی‌ای از ریپازیتوری PCT روی s53 نیست** (`/home/saber/saberprojects/persian-corpus-toolkit` → NOT FOUND) — PCT production (اگر روزی روی s52 بوده) در s53 نیست.

---

## ۶. سرویس‌های مدل (embedding / LLM)

پروب‌های `curl` واقعی روی s53 (read-only؛ فقط GET و یک درخواست embedding تک‌واژه‌ای برای اندازه‌گیری بُعد):

| پورت | سرویس | مدل | بُعد (dimension) | health واقعی | یادداشت |
|---|---|---|---|---|---|
| 4000 | vllm-embedding | **Qwen3-Embedding-4B** | **2560** (اندازه‌گیری زنده از پاسخ `/v1/embeddings`) | HTTP 200 + embedding واقعی برگشت | `max_model_len=32768` |
| 4001 | vllm-embedding-06b | **Qwen3-Embedding-0.6B** | **1024** (اندازه‌گیری زنده) | HTTP 200 + embedding واقعی برگشت | `max_model_len=8192` |
| 11434 | ollama | mxbai-embed-large | **UNKNOWN** (پروب بُعد انجام نشد) | پورت باز | در دسترس |
| 8000 / 8001 | vLLM (LLM) | **Qwen3.8-27B-FP8** | — (چت، نه embedding) | HTTP 200 | `max_model_len=200,000` |
| 9001 | mock-litellm | — | — | Up | mock |

خروجی مستقیم اندازه‌گیری (probe 3):

```text
port=4000 model=Qwen3-Embedding-4B   server_model=Qwen3-Embedding-4B   dim=2560
port=4001 model=Qwen3-Embedding-0.6B server_model=Qwen3-Embedding-0.6B dim=1024
```

> ✅ **این سطر، «NOT VERIFIED» قدیمی PCM-20.5 را رفع می‌کند:** بُعد واقعی Qwen3-Embedding-0.6B = **1024** و 4B = **2560**. (dimension mock در buildهای PCM-20.4 هم 1024 بود → با 0.6B سازگار؛ 4B نیاز به طراحی تازه دارد.)
>
> `LITELLM_BASE` پورتال RAG = `http://172.30.0.133:4000/v1` (فضای IP عمومی 172.30.0.x) — **UNTESTED** از این شبکه (به‌سبب قوانین مأموریت فقط از داخل s53 probe شده؛ از خارج به آن IP/پورت درخواستی ارسال نشد).

---

## ۷. Neo4j

همه‌ی مشاهدات روی **s53** (هیچ Neo4j روی هاست دیگر قابل مشاهده نیست — بقیه offline):

| فیلد | مقدار | شواهد |
|---|---|---|
| ایمیج | `neo4j:2025.10.1-enterprise` | `docker ps` |
| پورت‌ها | bolt **7687** / http **7474** | `ss -tlnp` + `docker ps` |
| وضعیت | Up 5 روز، healthy | `docker ps` |
| http بدون اعتبار | `GET :7474/db/neo4j` → **401** (سرور پاسخ می‌دهد، auth لازم است) | `curl` |
| `GET :7474/` | JSON dbms: `"bolt_routing":"neo4j://127.0.0.1:7687"` | `curl` |
| فهرست databaseها / شمارش نودها | **UNKNOWN** — نیازمند اعتبار؛ هیچ نوشتاری/خوندنی با auth انجام نشد | — |

**مصرف‌کننده‌های Neo4j (از configها، کلیدهای حساس masked):**

| مصرف‌کننده | URI | database |
|---|---|---|
| graph-rag (repo RAG) | `NEO4J_DATABASE=neo4j` (default) | `neo4j` |
| rag-portal (QA corpus) | `QA_CORPUS_NEO4J_URI=bolt://172.20.1.53:7687` | **`taghrir`** |

> الگوی «کلکشن RAG» در این زیرساخت = **یک database Neo4j** (منطق `config.py:164`: `ACTIVE_COLLECTION = COLLECTION["active"] or os.environ.get("NEO4J_DATABASE", "neo4j")`).

---

## ۸. وضعیت RAG (graph-rag + rag-portal)

### 8.1 ریپازیتوری graph-rag روی s53

```text
/home/saber/saberprojects/graph-rag
git log --oneline -1  →  633be2c merge: combine Dump baseline 428e7d3 with main 283ae50  keep-both-lines
```

| فیلد | مقدار |
|---|---|
| HEAD | **`633be2cf428f2404d72dc76868d4d397dd9798bb`** (2026-10-09) |
| سابقه | PCM-20.5 READINESS HEAD را `283ae504` (2026-09-29) ثبت کرده بود → **ریپازیتوری از آن تاریخ ۲ هفته جلوتر رفته** |
| dirty | `M docker-compose.yml` + ۹ فایل untracked (اسکریپت‌های کمکی `_verify*.py`, `_link_audit*.py`, `load_collection.py.bak.*`, `import_neo4j_dump.sh`, `logs/`) |

`config.json` (کلیدهای حساس masked):

```text
embedding.model          = Qwen3-Embedding-0.6B
embedding.endpoint       = <masked-url :4001>
collection.active        = falsafe-siasi-qwen3-embed-06b
llm.planner/answerer     = qwen38
NEO4J_DATABASE           = neo4j
```

### 8.2 rag-portal (= rag.ai.ismc.ir)

- containerهای `ragportal` api:8033 / frontend:8034 روی s53؛ nginx داخلی پورتال: `/api/` → `ragportal_api:8000`، SPA با `try_files`.
- شواهد مالکیت دامنه: `GOOGLE_REDIRECT_URI=https://rag.ai.ismc.ir/api/auth/google/redirect` در compose پورتال.
- `LITELLM_BASE=http://172.30.0.133:4000/v1`؛ `QA_CORPUS_NEO4J_DB=taghrir`.
- از بیرون: `https://rag.ai.ismc.ir/` → **HTTP 200**، عنوان «رگ | پورتال هوشمند پاسخ‌گویی»، `/api/health` → 200.

### 8.3 کلکشن تسنیم — وضعیت

| سؤال | پاسخ | شواهد |
|---|---|---|
| آیا کلکشن RAG تسنیمی ثبت/بارگذاری شده؟ | **خیر — هیچ نشانی از آن نیست** | `collection.active=falsafe-siasi-qwen3-embed-06b`؛ database پورتال `taghrir`؛ هیچ build واقعی embedding تسنیم وجود ندارد (تمام buildهای PCM-20.4 mock بودند) |
| embedding واقعی تسنیم تولید شده؟ | **خیر** | `.tmp_pcm205_readiness_s1.json` → `mock_not_rag_ready: true`, `zero real embeddings in data/` |
| dataset/dump برای semantic v0002 ساخته شده؟ | **خیر** | بخش ۱۰.۴ (stale dumps: همه از v0001 پیش از semantic) |
| gateway routing (Kong/Tyk) | **UNKNOWN** — APIهای admin بدون credentials پاسخ ندادند (خروجی خالی) | probe 2 |

---

## ۹. DNS / TLS (دامنه‌های `*.ai.ismc.ir`)

پروب‌ها: `nslookup` + `curl -w` + بررسی TLS با PowerShell (`.tmp_pcm206_baseline_domains.ps1`)؛ همه از شبکه‌ی کاربر (DNS resolver 172.22.6.1).

| دامنه | DNS (A) | TLS (443) | HTTP | vhost |
|---|---|---|---|---|
| `tasnim.ai.ismc.ir` | ✅ → **172.30.0.133** | ⚠️ گواهی پیش‌فرض: **`CN=admin.ai.ismc.ir`** (Let's Encrypt YE2, انقضا 2027-01-01, thumb `76D433EF…`) → `SEC_E_WRONG_PRINCIPAL` | 000 (fail TLS) | **هنوز vhost/گواهی اختصاصی ندارد** — SNI روی default vhost می‌افتد |
| `rag.ai.ismc.ir` | ✅ → 172.30.0.133 | ✅ `CN=rag.ai.ismc.ir` (Let's Encrypt YE2, انقضا **2027-11-01**, thumb `187BEBD9…`) | **200** | ✅ فعال — پورتال «رگ»؛ `/api/health`=200 |
| `docs.ai.ismc.ir` | ✅ → 172.30.0.133 | ✅ `CN=docs.ai.ismc.ir` (Let's Encrypt, انقضا 2027-03-01, thumb `12D073EF…`) | **200** | ✅ فعال — Wiki.js «مستندات هوش مصنوعی» |

> هر چهار نام (شامل parent `ai.ismc.ir`) به همان IP `172.30.0.133` resolve می‌شوند (Non-authoritative answer).

**بررسی Wiki.js بدون اعتبار (docs.ai.ismc.ir):**

| endpoint | نتیجه |
|---|---|
| `GET /` | 200 — HTML Wiki.js (عنوان: «مستندات هوش مصنوعی | Wiki.js»، `lang=fa, rtl`) |
| `GET /api/v2` | **404** |
| `GET /api/v2/meta` | **404** |
| `GET /api/v2/ping` | **404** |
| `POST /api/graphql` | صفحه‌ی خطای Wiki.js (404) — GraphQL بدون token در دسترس نیست |

نتیجه: Wiki.js زنده است اما **REST API v2 غیرفعال/دست‌نیافتنی است** — اتوماسیون محتوای docs از بیرون بدون دسترسی مدیریتی ممکن نیست.

**نکته‌ی کلیدی برای وبسایت تسنیم:** دامنه resolve می‌شود و TLS از لایه‌ی ingress (172.30.0.133) مدیریت می‌شود؛ برای راه‌اندازی باید vhost جدید + گواهی `tasnim.ai.ismc.ir` در ingress ساخته شود (الگوی مرجع این ریپازیتوری: [`deploy/nginx-corpus.vhost.conf`](../deploy/nginx-corpus.vhost.conf) — 80→301→443، Let's Encrypt، `proxy_pass 127.0.0.1:…`، `X-Forwarded-Proto`).

---

## ۱۰. داده تسنیم (local, `data/tasnim/`)

### 10.1 زنجیره‌ی داده (همه SHAها در این baseline از نو محاسبه و مطابقت یافت — بخش 1.4)

```text
اسنپ‌شات (45,844 صفحه)
  └→ corpus v0001 (canonical، RAW+NORMALIZED جدا)
       ├→ 6 dataset (stratified-even-blocks: 1/10/10-vol56/50/90/100٪)
       │    └→ 3 dump (d-1) ─→ 3 build خارجی ai-dump-builder (همه --mock-embed)
       └→ corpus v0002 (semantic، قرارداد cs-20.5: 45,844 صفحه + 10,728 context-record)
```

### 10.2 اسنپ‌شات (root: `data/tasnim/pcm20_4/source-snapshot/`)

| فایل | حجم (B) | SHA-256 |
|---|---:|---|
| `tasnim-corpus.jsonl` | 72,906,133 | `fd927b663733fe0530afdf76d6deb6b42f3b40d807297e60722fe3b0e79e96b5` |
| `tasnim-corpus.json` | 72,959,214 | `cee2c08aae1862d0bde029868af29f1512a0faec8ac9a5c3b41d70d8260f1676` |
| `export-summary.json` | 408,016 | `1b96b1b07c1acca11ebfcd75e3cd8f5f706c76955e6023e30923f6dc7a2fc733` |
| `pcm20_2_audit.json` | 63,188 | `db6c30f415372c6ae7cb9709286e0d4f0ac42db78c5b7aa38de2e7996c7260d7` |

ثبت‌شده به‌عنوان `sfd927b663733` (manifest SHA `7d19796a9df622b4afbf5c25d0f280273e104c9cff2874dc46d057c08736c7f3` — هر سه root pcm20_4/pcm20_5/crossroot همین اسنپ‌شات را با manifest‌های متفاوتِ `created_at` ثبت کرده‌اند).

### 10.3 corpusها

| build | نقش | pages | content SHA-256 |
|---|---|---:|---|
| `pcm20_4/v0001` | REAL canonical | 45,844 | `ee87686ac49ce9c08a4a492f4f54c23ace571bb8f048aa8a0a863bece3d542d8` |
| `pcm20_4/v0002` | FIXTURE (21 رکورد) | 21 | `8a1cad109266f76be8d1827a1fcd53fe0d3c70e373cbda3cc134bf5c78ab883b` |
| `pcm20_4/v0003` | FIXTURE (22 رکورد) | 22 | `0d86db167cd3bbf803a958c4660b8ea887f134438c77fe499c8b0b78250c7f36` |
| `pcm20_5/v0001` | REAL cross-root (همان محتوا) | 45,844 | `ee87686a…` (همان v0001) |
| `pcm20_5/v0002` | **SEMANTIC (cs-20.5)** | 45,844 + **10,728** context-record | `12a93e218bbc7a38d450749eca5ce25d0833b537cc13446048d430eade54f4a5` |
| `crossroot/v0001` | REAL cross-root | 45,844 | `ee87686a…` |
| `crossroot/v0002` | SEMANTIC cross-root | 45,844 + 10,728 | `12a93e21…` |

شمارش خط‌های از-نو (این baseline): `pcm20_5/v0002/pages.jsonl` = **45,844** خط؛ `context-records.jsonl` = **10,728** خط.

شماریابی semantic v0002 (از GATE 1، دوباره در S1 تایید شد):

| class | تعداد |
|---|---:|
| CONTENT_PAGE | 33,443 |
| SECTION_HEADING | 10,739 |
| SHORT_CONTENT | 1,589 |
| UNKNOWN_STRUCTURE | 38 |
| EMPTY_PAGE | 35 |
| CHAPTER_HEADING | 0 |

### 10.4 datasets و dumps (root: `data/tasnim/pcm20_4/`)

| dataset | انتخاب | content SHA-256 (8) |
|---|---:|---|
| 1pct/v0001 | 458 | `a407021e…` |
| 10pct/v0001 | 4,584 | `7de515a6…` |
| 10pct/v0002 (vol56) | 2,969 | `11ab83ce…` |
| 50pct/v0001 | 22,922 | `7c15be3f…` |
| 90pct/v0001 | 41,260 | `8ef9aab8…` |
| 100pct/v0001 | 45,844 | `37673c3d…` |

3 dump (d-1): `10pct/v0001` (از vol56: 2,197 رکورد / 772 skip)، `10pct/v0002` (6 جلد: 3,416 / 1,168)، `100pct/v0001` (45,844 صفحه: **33,443 رکورد** / 12,401 skip) — 3 build خارجی builder (mock-embed، 1024-dim، `DUMP_VALIDATED 0 errors`).

**registryها (read-only):** `pcm20_4/manifests/registry.json` (SHA `83abe05c…`، 15 entry در `chain`: 3 corpus + 6 dataset + 3 dump + 3 source-snapshot)؛ `pcm20_5/…` (SHA `e8474e4b…`، 3 entry: v0001, v0002 semantic, snapshot)؛ `pcm20_5_crossroot/…` (SHA `df056d01…`، 3 entry). همه در این baseline دوباره SHA شد و مطابق بود.

### 10.5 فاصله‌ی 45,243 (گشوده — BLOCKED برای بازیابی)

بازمحاسبه‌ی مستقل در این baseline (`.tmp_pcm206_baseline_dataverify.py`، فقط خواندن jsonl اسنپ‌شات):

```text
total_lines=45844  distinct=45835  min=0  max=91077  span=91078
coverage_gap = 91078 - 45835 = 45243   →  match=True
6 runs: [3649–11182] [11205–39003] [44957–49956] [55699–55701] [55715–59590] [89280–90310]  (sum=45243, دقیقاً مطابق ثبت)
dup item_index: 9 مقادیر تکراری (همه برخورد vol1×vol47)
```

**تفسیر:** هر 45,844 رکورد اسنپ‌شات `item_index` دارد؛ 45,243 = **مقادیری در بازه‌ی [0..91077] که اصلاً در اسنپ‌شات نیستند** (سوراخ‌های پوشش از منبع). دلایل احتمالی در GATE 0 ثبت شده‌اند ولی **HYPOTHESIS** هستند؛ بازیابی واقعی نیازمند re-crawl زنده از سایت است و:
- مسیر قدیمی (s52/172.30.0.113) — s52 و s113 هر دو offline (بخش‌های ۴ و ۵)؛
- endpoint زنده‌ی کشف‌شده در PCM-20.5: `GET https://tasnim.hamtaa.org/api/v1/files/tasnim/chunk-detail?item_index=N` (read-only) — در GATE 0-D ثابت شد `/payload` سایت اکنون HTML SPA shell می‌دهد؛ همین endpoint chunk-detail هنوز در PCM-20.4 برای 5 آیتم جواب زنده داده بود، ولی **در این baseline عمداً دوباره probe نشد** (خارج از scope؛ در PCM-20.6 قابل انجام است).

### 10.6 یافته‌های باز (از S1، در این baseline تأیید شدند)

| یافته | وضعیت |
|---|---|
| 28 صفحه (0.06%) توسط **خود منبع** در 2000 کاراکتر بسته شده‌اند | ثابت (GATE 1.5 PASS، بخش 1.6) — قابل بازیابی نیست؛ factory پرچم `truncated_at_2000` می‌زند و حذف نمی‌کند |
| هیچ dataset/dump برای semantic v0002 وجود ندارد | ✅ تأیید — همه 6 dataset و 3 dump از v0001 (پیش از semantic) |
| همه‌ی embeddingها mock | ✅ تأیید — zero real embedding در `data/` |
| delta-11 (10,739 سرتیتر − 10,728 context-record) | ✅ تأیید — 3 سرتیترِ پایان‌جلد (بدون صفحه‌ی بعد) + 8 سرتیتر که صفحه‌ی بعدشان EMPTY_PAGE است |

---

## ۱۱. BLOCKED / MISSING (با شواهد)

| # | مورد | دلیل BLOCKED | شواهد (دستور + خروجی) | اثر بر PCM-20.6 |
|---|---|---|---|---|
| B1 | **s52 (172.20.1.52) کاملاً بی‌دسترس** | `ssh: connect to host 172.20.1.52 port 22: Connection timed out` + 6/6 پورت TCP `TIMEOUT/CLOSED` (11:53 +0330) | بخش ۴ | deploy production PCT و `thesaurus.db` و re-crawl زنده‌ی 45,243 → UNKNOWN/BLOCKED |
| B2 | **s113 / s117 بی‌دسترس** | 6/6 پورت هر دو `TIMEOUT/CLOSED` | بخش ۵ | نقش سابقه‌ای s113 («AI-TOOLS») دیگر قابل تأیید نیست |
| B3 | **GitLab داخلی s52:2222** | remote تعریف نشده + `s52:2222 = TIMEOUT/CLOSED` | بخش ۳ | وضعیت/SHA مخزن داخلی UNKNOWN |
| B4 | **فهرست collectionهای Qdrant (s53:6333)** | `curl /collections` → `Must provide an API key or an Authorization bearer token` | بخش ۶ | وجود/عدم کلکشن در Qdrant UNKNOWN (احتمالاً نامرتبط؛ RAG اینجایی Neo4j است) |
| B5 | **فهرست databaseهای Neo4j + شمارش نود** | `GET :7474/db/neo4j` → 401 (بدون auth) | بخش ۷ | فقط «سرور بالا + endpoint bolt فعال» تایید شد؛ `taghrir`/`neo4j` از configها خوانده شد، نه از سرور |
| B6 | **routing عمومی Kong/Tyk** | APIهای admin (Kong :8001, Tyk :8290) بدون credentials پاسخ ندادند | بخش ۸.3 | نقشه‌ی دقیق دامنه→بک‌اند از بیرون قابل رسم نیست؛ اما 3 دامنه با curl مستقیم رفتارشان اندازه‌گیری شد |
| B7 | **bُعد embedding ollama (mxbai-embed-large)** | probe بُعد انجام نشد (خارج از ضرورت) | بخش ۶ | UNKNOWN — اگر لازم شد در PCM-20.6 اندازه‌گیری می‌شود |
| B8 | **`LITELLM_BASE=http://172.30.0.133:4000/v1` از شبکه‌ی ما** | UNTESTED (قوانین: فقط probe read-only از داخل s53؛ از خارج درخواست ارسال نشد) | بخش ۶ | سلامت litellm عمومی از دید portal → در PCM-20.6 با یک GET ساده قابل بررسی است |
| B9 | **REST API v2 Wiki.js (docs.ai.ismc.ir)** | `/api/v2`, `/api/v2/meta`, `/api/v2/ping`, `/api/graphql` → همه 404 | بخش ۹ | اتوماسیون محتوای docs بدون دسترسی admin ممکن نیست |
| B10 | **بازیابی 45,243 صفحه‌ی گمشده** | نیازمند re-crawl زنده؛ مسیرهای قدیمی (s52/s113) offline؛ endpoint سایت در حالت فعلی (SPA shell برای /payload) | بخش ۱۰.۵ | داده‌ی کامل 91,078-item فقط با re-crawl زنده از `tasnim.hamtaa.org` |

---

## ۱۲. جمع‌بندی: go / no-go + فازهای gated

### 12.1 وضعیت کلی

| ستون | وضعیت | دلیل |
|---|---|---|
| **داده محلی تسنیم** | ✅ **GO** | 33/33 SHA مطابق، 227 تست سبز، زنجیره‌ی provenance کامل و deterministic، gap دقیقاً کمّی‌سازی شد |
| **وبسایت `tasnim.ai.ismc.ir`** | ✅ **GO (با کار راه‌اندازی)** | DNS فعال؛ فقط vhost + گواهی Let's Encrypt در ingress (الگو: `deploy/nginx-corpus.vhost.conf`) و اپ بک‌اند لازم است؛ گواهی فعلی default (CN=admin) است |
| **RAG روی `rag.ai.ismc.ir`** | ⚠️ **GO مشروط (infrastructure آماده، داده‌ی تسنیم هنوز نه)** | پورتال زنده + embedding واقعی (0.6B=1024 / 4B=2560) + Neo4j enterprise بالا؛ **ولی** embedding واقعی تسنیم وجود ندارد، dump برای semantic v0002 ساخته نشده، و کلکشن فعال فعلی `falsafe-siasi` است |
| **کامل‌کردن پیکره (45,243)** | ❌ **BLOCKED** | B1/B10 — s52/s113 offline؛ نیازمند تصمیم: re-crawl مستقیم از سایت یا بازگشت s52 |

### 12.2 فازهای پیشنهادی برای PCM-20.6 (gated)

| فاز | gate ورودی | وابستگی |
|---|---|---|
| **P1 — vhost تسنیم** (DNS/ TLS/ ingress + اسکلت اپ) | بدون پیش‌شرط: DNS و IP ingress ثابت (172.30.0.133) | — |
| **P2 — dataset + dump برای semantic v0002** | نیازمند تصمیم طراحی: context-records در chunk_text/embedding context آید یا نه (GATE 2 design decision باز است) | محلی، offline، قابل انجام الان |
| **P3 — embedding واقعی + بارگذاری Neo4j (کلکشن `tasnim_tafsir`)** | P2 + انتخاب مدل (0.6B/1024-dim پیشنهادی: سازگار با mock و با GPU1 که 14 GB آزاد دارد) + تعریف database/collection تازه در Neo4j + اعتبار (B5) | s53 (آزنده) |
| **P4 — اتصال رگ‌پورتال به کلکشن تسنیم** | P3 + تعریف routing در gateway (B6) + تصمیم auth | s53 |
| **P5 — بازیابی 45,243 صفحه‌ی گمشده** | **B1/B10** — یا بازگشت s52/s113، یا re-crawl زنده مستقیم از `tasnim.hamtaa.org` (read-only، با endpoint `chunk-detail`) | BLOCKED تا رفع |
| **P6 — docs: محتوا در Wiki.js** | B9 — یا فعال‌سازی API v2 یا ویرایش دستی با حساب admin | docs.ai.ismc.ir |

### 12.3 موارد باقی‌مانده‌ی مهم برای تصمیم‌گیری کاربر

1. **commit/push محلی** (1 commit + 3 فایل staged) — اراده‌ی کاربر (این مأموریت عمداً دست نخورد).
2. **مدل embedding برای کلکشن تسنیم**: 0.6B (1024-dim، سبک، سازگار با buildهای mock) یا 4B (2560-dim، کیفی‌تر، نیازمند طراحی تازه + VRAM بیشتر).
3. **سرنوشت 45,243 صفحه**: re-crawl زنده‌ی مستقیم از سایت (مسیر جدید، بدون s52) در مقابل انتظار بازگشت s52.
4. **semantic fields در chunk**: `embedding_context_defined=false` هنوز باز است — قرار نیست context-records (10,728 رکورد hidden) وارد embedding شوند یا نه.
5. **پاکسازی probeها**: 10 فایل/خروجی `.tmp_pcm206_baseline_*` برای حذف/ثبت پس از تأیید این گزارش.

### 12.4 صحت‌سنجی این گزارش

- هر SHA در این گزارش از دو منبع مستقل: (الف) محاسبه‌ی از-نو در 2026-11-06 با `.tmp_pcm206_baseline_dataverify.py` (33/33 مطابق) و (ب) مقایسه با `.tmp_pcm205_readiness_s1.json` (2026-11-05).
- هر claim سروری با دستور و خروجی مستقیم در متن (بخش‌های ۴–۸)؛ هیچ عددی ساختگی نیست.
- حالت read-only: هیچ نوشتاری روی s53، هیچ push، هیچ commit، هیچ deploy، هیچ توقف container.

---

*پایان گزارش — PCM-20.6 SUBTASK 01 (FRESH BASELINE)*

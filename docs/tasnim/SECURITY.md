# امنیت — Tasnim Web V1

> PCM-20.6.4 · سند B15 · 2026-11-07
> نقشهٔ مادر: [INDEX.md](INDEX.md) · API: [API-REFERENCE.md](API-REFERENCE.md)

---

## ۱. مدل تهدید (scope صریح)

V1 یک **کتابخانهٔ دیجیتال read-only** است:

- ❌ بدون user account، بدون session، بدون state کاربری
- ❌ بدون ورودی نوشتاری (همهٔ endpoints فقط `GET`)
- ❌ بدون upload، بدون file handling کاربر
- ✅ خروجی: HTML (SSR) + JSON (API) + SVG (کاور) + فونت

بنابراین سطح حمله محدود به این‌هاست: **XSS (inject دادهٔ corpus به HTML/SVG)، SQL injection، path traversal، information disclosure، abuse/rate، cache poisoning.**

| تهدید | وضعیت | کنترل |
|---|---|---|
| SQL injection | ✅ بسته | همهٔ queries **پارامتری** (placeholder)؛ `ORDER BY` فقط از whitelist؛ هیچ string-interpolation در SQL نیست |
| XSS (reflected/stored) | ✅ بسته | همهٔ خروجی‌های DOM از `escHtml`؛ Jinja autoescape؛ serializer `strict_pick` (deny-by-default)؛ **canary test** (بخش ۲) |
| SVG injection (کاور) | ✅ بسته | `Markup`-wrapped escape در `cover.py`؛ test: `test_tasnim_readmodel.py:283 test_cover` |
| Information disclosure | ✅ بسته | error pages فارسی/سفارشی؛ **هیچ stack trace در خروجی عمومی**؛ 404/429/503 همه envelope استاندارد |
| Abuse / scraping | ✅ کنترل | rate-limit per-IP (بخش ۳) |
| Cache poisoning | ✅ کنترل | ETag strong (content-addressed به SHA read model)؛ `no-store` برای search |
| CORS | ✅ لازم نیست | V1 same-origin است (SSR + API یک origin)؛ **هیچ `Access-Control-Allow-Origin`** صادر نمی‌شود |
| Dependency | ✅ حداقل | فقط Flask (پین 3.1.3) + stdlib (بخش ۷) |

---

## ۲. HP-1: جداسازی hidden context (مهم‌ترین کنترل)

**سیاست** (در `build_meta.db` ثبت شده):
> «hidden summaries are system-only (embedding/retrieval) and must never be rendered publicly»

**4 لایهٔ دفاع:**

1. **لایهٔ builder (سخت‌گیرانه‌ترین)**: `ReadModelBuilder._open` در `readmodel.py` هر open فایل را با whitelist بررسی می‌کند:
   - `ALLOWED_SOURCE_FILES` = `{pages.jsonl, heading-records.jsonl, corpus.json, manifest.json}`
   - `FORBIDDEN` = `{hidden-context-records.jsonl (17,895,082 B / 10,728 رکورد), context-records.jsonl (26,287,577 B / 10,728 رکورد)}`
   - هر open یک forbidden → `BuildError("HP-1 violation: builder must never open %r" % name)` → **build fail**
2. **لایهٔ schema**: جدول `pages` فقط `context_record_id` (فقط ID، **هرگز محتوا**) دارد؛ هیچ column hidden-text در read model نیست.
3. **لایهٔ serializer**: `strict_pick` — deny-by-default؛ هر فیلدی که به JSON/HTML می‌رود باید صریح whitelist شده باشد.
4. **لایهٔ test**: **T-HC-1..4** + **canary**: `tasnim_test_support.build_fixture_corpus` دو فایل forbidden با محتوای `HIDDEN-CANARY-DO-NOT-LEAK` می‌سازد؛ اگر هر لایه‌ای شکست بخورد:
   - build fail می‌شود (لایهٔ 1) یا
   - canary در خروجی ظاهر می‌شود → **smoke check #15** (canary scan روی همهٔ HTML body‌ها) fail می‌شود

**شواهد**: `hidden_context_included=false` در `build_meta.db`؛ smoke check 15 (بخش [TEST-REPORT.md](TEST-REPORT.md) §3) روی دادهٔ واقعی v0003 سبز.

---

## ۳. Rate limiting

| class | حد | window |
|---|---|---|
| `search` | 30 / دقیقه / IP | calendar minute |
| `read` (بقیّهٔ endpoints عمومی) | 120 / دقیقه / IP | calendar minute |

**Exempt** (بدون شمارش): `/api/v1/tasnim/health`، `/openapi.json`، `/docs`.

### شناسایی IP (صادقانه)

در `api.py:236-238`:
```python
ip = (xf.split(",")[0].strip() if xf else (request.remote_addr or "local"))
# xf = X-Forwarded-For header
```
یعنی **اولین entry از XFF** — این فقط امن است اگر reverse proxy خلیفهٔ خنثی باشد (nginx ما XFF را **append-only** می‌کند، نه replace؛ ingress سازمانی هم باید همین کار را کند — [DEPLOYMENT.md](DEPLOYMENT.md) §2.1). اگر از بیرون ingress مستقیم به 5071 وصل شوید، XFF قابل‌تقلب است — **پس 5071 هرگز public نمی‌شود** (فقط از طریق ingress روی 5070).

### state

- SQLite table `tasnim_rate_limits` در `--rate-db` (default: کنار read model؛ در compose: volume `tasnim_runtime` روی `/var/tasnim/ratelimit.db`)
- `threading.Lock` + `check_same_thread=False` (bug #2 در [TEST-REPORT.md](TEST-REPORT.md) §2 — fix شده)
- **429 response**: `Retry-After` + envelope استاندارد (`code: RATE_LIMITED`، `limit`، `window: "60s"`، `endpoint_class`)
- reset: [OPS-RUNBOOK.md](OPS-RUNBOOK.md) §4

---

## ۴. Error pages و information disclosure

| status | code | چه چیزی می‌آید (و چه چیزی نمی‌آید) |
|---|---|---|
| 404 صفحه | `PAGE_NOT_FOUND` | item_index + `in_missing_range` + suggestion — **نه** stack، **نه** SQL، **نه** path داخلی |
| 404 volume/topic | `VOLUME_NOT_FOUND` / `TOPIC_NOT_FOUND` | فقط id خواسته‌شده |
| 404 مسیر | `NOT_FOUND` | فقط path + `request_id: "req_unknown"` |
| 400 | `INVALID_QUERY` / `INVALID_PARAMETER` / `INVALID_SORT` / `INVALID_PAGE_TOKEN` | param + allowed values — **نه** internals |
| 429 | `RATE_LIMITED` | limit + window + Retry-After |
| 503 | `SURAH_INDEX_NOT_SUPPORTED` | reason صادقانه (data gap، نه fault) |
| 500 (theoretical) | — | page سفارشی `error.html` — **هیچ stack trace عمومی** |

همهٔ errorها: `type` (URI ممتد `https://tasnim.ai.ismc.ir/errors/<slug>`)، `title`، `status`، `message` **فارسی**، `code`، `request_id`.

**test anchor**: `test_tasnim_api.py` (تمام error contract) + smoke check 13.

---

## ۵. SVG cover generation

- `cover.py` SVG را **programmatic** می‌سازد (هیچ binary image، هیچ fetch از بیرون)
- تمام مقادیر text (عنوان جلد، شماره) از `markupsafe.escape` رد می‌شوند → `Markup`
- **bug #3** (fix شده): قبل از fix، عنوان با `<`/`&` باعث SVG injection می‌شد؛ test: `test_tasnim_readmodel.py:283 test_cover`
- `Content-Type: image/svg+xml` + `X-Content-Type-Options: nosniff` (nginx)
- **کاور/تصویر واقعی نداریم** — فقط SVG برنامه‌ای + badge (قاعدهٔ سخت: «no fake covers» — AGENTS.md §2)

---

## ۶. فونت‌ها

- Noto Naskh Arabic + Vazirmatn (3 weight) — هر دو **SIL Open Font License 1.1**
- `OFL.txt` در کنار فونت‌ها (در repo + در container)
- `Content-Type: font/ttf` + `Cache-Control: max-age=86400`
- فونت‌ها static asset هستند (نه upload) — سطح حمله صفر
- smoke check 14: فونت سرو می‌شود، >10,000 B

---

## ۷. Dependency minimization

| dependency | نسخه | دلیل |
|---|---|---|
| Flask | **3.1.3** (پین سخت) | فقط web framework |
| Jinja2 | 3.1.6 (ترانزیت) | SSR |
| Werkzeug | 3.1.9 (ترانزیت) | test client + WSGI |
| Python stdlib | 3.9+ / 3.12 | sqlite3، json، urllib (SDK)، markupsafe (ترانزیت Flask) |
| Node.js | 18+ (فقط SDK JS) | zero-dependency ESM fetch |

**هیچ dependency دیگری نیست** — نه DB driver خارجی، نه http library، نه template engine، نه image library. سطح حملهٔ supply-chain = 3 پکیج (Flask + 2 ترانزیت).

---

## ۸. TLS و transport

- **در container/host**: HTTP plain (127.0.0.1 / docker network) — trust boundary = docker network + host
- **در ingress**: TLS terminates در Kong (گواهی Let's Encrypt برای `tasnim.ai.ismc.ir`) — [DEPLOYMENT.md](DEPLOYMENT.md) §2
- `X-Forwarded-Proto: https` از ingress (الزامی — API برای `type` URI در errorها به آن اعتماد می‌کند)
- HSTS: در V1 روی ingress تنظیم می‌شود (مالک ingress) — در nginx ما نیست (چون TLS آنجا نیست)

---

## ۹. محدودیت‌های معروف (صادقانه)

| محدودیت | ریسک | مهار |
|---|---|---|
| XFF trust model | اگر 5071 public شود، IP spoofing | **5071 هرگز public نیست** (compose: بدون publish؛ فقط docker network) |
| rate-limit = per-IP (نه per-fingerprint) | bot با IP pool | ingress-level (مالک ingress) + rate-limit حداقل abuse را محدود می‌کند |
| FTS5 query injection | `"`/`*` در query | query در `api.py` sanitize می‌شود (escape `"`) — test: `test_tasnim_api.py:273 test_q_metachars_escap`؛ query نهایی فقط `"tok"* AND …` |
| path traversal در `--db` | اپراتور با `--db /etc/passwd` | فقط اپراتور با دسترسی host می‌تواند سرور را start کند؛ DB باز می‌شود با `sqlite3` که روی فایل غیر-DB خطا می‌دهد (نه read) |
| `manifest.json` verify=false در v0003 | build validation ضعیف‌تر | build meta ثبت کرده؛ **build fail** اگر manifest ناقص باشد (فقط verify SHA نیست) |
| Docker: non-root ولی `COPY .` | اگر build context آلوده شود | `.dockerignore` + code review (سطح supply-chain) |
| بدون CSP header | (خروجی خود ما، third-party script ندارد) | `nosniff` + `Referrer-Policy` + `X-Frame-Options SAMEORIGIN` (API)؛ CSP = V1.5 candidate |

---

## ۱۰. چک‌لیست امنیتی (قبل از هر release)

- [ ] canary scan سبز (smoke #15)
- [ ] `hidden_context_included=false` در build_meta
- [ ] هیچ `Access-Control-Allow-Origin` در headerها نیست
- [ ] error page‌ها (404/429/503/500) در مرورگر — هیچ stack trace
- [ ] cover SVG با عنوان شامل `<script>` → escape شده (test)
- [ ] FTS query با `"`, `*`, `'` → safe (test)
- [ ] 429 با `Retry-After` (test)
- [ ] dependency audit: فقط Flask pinned
- [ ] TLS در ingress + `X-Forwarded-Proto` (وقتی provision شد)

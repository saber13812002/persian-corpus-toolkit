# Tasnim Web V1 — SDK JavaScript/TypeScript

README-first: این SDK نسخهٔ JS/TS مشتری‌کیت رسمی API خواندنی «تفسیر تسنیم»
Web V1 است و 1:1 با SDK پایتون (`tasnim/sdk/python`) مطابقت دارد — همان ۱۲
endpoint، همان envelope، همان خطاها، همان backoff برای 429 و همان کش ETag.

- **بدون وابستگی (zero deps):** ES Module + `fetch` global — Node 18+ و
  همهٔ مرورگرهای مدرن.
- `tasnim-client.mjs` — کد کلاینت (ESM).
- `tasnim.sdk.d.ts` — تایپ‌های TypeScript.

مستند کامل قرارداد (base URL، rate limitها، جدول خطاها، pagination، cache):
`docs/PCM-20.6.4-INTEGRATION.md` (repo). نمونه‌های واقعی curl هم در همان سند.

## استفاده

```js
// Node (ESM) یا مرورگر
import TasnimClient from "./tasnim-client.mjs";
import { TasnimAPIError } from "./tasnim-client.mjs";

const c = new TasnimClient(); // baseUrl پیش‌فرض: https://tasnim.ai.ismc.ir
// یا instance محلی: new TasnimClient({ baseUrl: "http://127.0.0.1:5071" });

const health = await c.getHealth();
console.log(health.data.status);            // "ok"
console.log(health.requestId);              // "req_..."

const catalog = await c.getCatalog();
console.log(catalog.data.counts);           // { pages, volumes, topics, headings, missing_item_index }
const again = await c.getCatalog();         // 304 → cached
console.log(again.fromCache);               // true
```

### خواندن یک صفحه (قلب قرارداد — gap-aware)

```js
const p = await c.getPage(2);
console.log(p.itemIndex);       // 2 (کاملاً snake_case هم هست: p.item_index)
console.log(p.text);            // متن صفحه
console.log(p.qualityStatus);   // "ok" | "short" | "dup_item_index" | ...
console.log(p.nextItemIndex);   // 3  |  null در پایان corpus
// رفرنس کامل (با in_missing_range / gap_before):
console.log(p.next_page_reference);

// 404 در بازهٔ گم‌شده — جزئیاتِ بازسازی:
try {
  await c.getPage(3650);
} catch (e) {
  if (e instanceof TasnimAPIError && e.code === "PAGE_NOT_FOUND") {
    console.log(e.details.in_missing_range); // [3649, 11182]
    console.log(e.details.suggestion);       // نزدیک‌ترین صفحات موجود
  }
}
```

### pagination + generators

```js
// یک صفحه (۵۰ تا) + token شفافِ server:
const page1 = await c.listVolumes({ limit: 50 });
const page2 = await c.listVolumes({ limit: 50, pageToken: page1.nextPageToken });

// یا کل زنجیرهٔ token (تمام جلد‌ها):
for await (const v of c.iterVolumes()) {
  console.log(v.volume_no, v.title, v.page_count);
}

// خوانش صفحه‌به‌صفحه با جهش روی gaps (به‌صورت پیش‌فرض skip):
for await (const pg of c.iterPages(1, 20, { onMissing: "skip" })) {
  console.log(pg.itemIndex, pg.barg);
}
```

> ⚠️ `iterTopics()` روی corpus کامل 1080 موضوع یعنی ~22 request (limit 50).
> اگر فقط چند موضوع اول می‌خواهید، از `c.listTopics({ limit: 5 })` استفاده
> کنید — نه generator. هر request در کلاسِ read است (120/دقیقه به‌ازای IP).

### جستجو

```js
const s = await c.search("قرآن", { limit: 20 });
console.log(s.data.total, s.data.results.length);
// 3+ توکن → نتیجهٔ برآوردی: s.data.total === -1 && s.data.estimated === true
// صفر نتیجه (حالت دقیق) → s.data.suggestions = موضوعات پرتکرار
```

### خطاها

```js
import { TasnimAPIError, TasnimClientError } from "./tasnim-client.mjs";

try {
  await c.getVolume("nope");
} catch (e) {
  if (e instanceof TasnimAPIError) {
    console.log(e.status);     // 404
    console.log(e.code);       // "VOLUME_NOT_FOUND"
    console.log(e.message);    // پیام فارسیِ دقیق
    console.log(e.requestId);  // برای پشتیبانی
  } else if (e instanceof TasnimClientError) {
    // خطای ترنسپورت (DNS/timeout/conn refused) — یا envelopeِ غیرمنتظره
    console.log(String(e));
  }
}
```

### rate limit (429)

کلاسیک read: 120 request/دقیقه، کلاس search: 30/دقیقه (به‌ازای هر IP).
کلاینت به‌صورت پیش‌فرض روی 429 مقدار `Retry-After` سرور را sleep می‌کند
(cap: `maxBackoffS` ثانیه، پیش‌فرض 65) تا `maxRetries` بار. برای تست‌ها:

```js
const c = new TasnimClient({
  baseUrl: "http://127.0.0.1:PORT",
  sleep: (s) => { /* injectable — در تست واقعی نمی‌خوابید */ },
});
// یا برای حذف backoff: new TasnimClient({ rateLimitBackoff: false })
```

### TypeScript

```ts
import TasnimClient from "./tasnim-client.mjs";
import type { Page, TopicDetail, TasnimAPIError } from "./tasnim.sdk.d.ts";

const c = new TasnimClient({ baseUrl: "https://tasnim.ai.ismc.ir" });
const p: Page = await c.getPage(2);
const t: TopicDetail = await c.getTopic("t-bd4e94070cce");
console.log(t.displayText, t.occurrencesTotal);
```

## ساختار پاسخ (envelope)

هر پاسخ موفق:

```json
{
  "data": { "…": "payload" },
  "meta": {
    "request_id": "req_031351974c5c4970",
    "readmodel": { "version": "v0003", "content_sha256": "40f45e…" },
    "generated_at": "2026-11-07T…",
    "next_page_token": "…(فقط تا پایان نتایج)…"
  }
}
```

## test

```bash
cd <worktree>
node --check tasnim/sdk/javascript/tasnim-client.mjs   # syntax (ESM)
```

آزمون‌های کاملِ Python-client (با سرور واقعی fixture) در
`test_tasnim_sdk.py` (ریشهٔ worktree) — همان contract برای هر دو SDK.

// Background — orchestrate two-phase crawls for thesaurus + khamenei
const BACKEND = 'https://corpus.ai.ismc.ir';
const KHAMENEI_HOST = 'farsi.khamenei.ir';
const THESAURUS_HOST = 'thesaurus.eiis.iki.ac.ir';

let crawlState = {
  mode: 'idle', // idle | phase1 | phase2 | both
  site: null,
  currentTabId: null,
  khamenei: { nextYear: null, emptyStreak: 0, MIN_YEAR: 1370, ids: [], idx: 0, delayMs: 2000, errors: 0 },
};

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  handle(msg, sender).then(sendResponse).catch((e) => sendResponse({ ok: false, message: String(e) }));
  return true;
});

async function handle(msg, sender) {
  switch (msg.action) {
    case 'runPhase1':
      return runPhase1(msg.site || 'thesaurus');
    case 'runPhase2':
      return runPhase2(msg.site || 'thesaurus');
    case 'runBothPhases':
      return runBoth(msg.site || 'thesaurus');
    case 'startSingle':
      return startSingle();
    case 'stop':
      crawlState.mode = 'idle';
      await chrome.storage.local.set({ crawlStop: true });
      return { ok: true };
    case 'reset':
      await fetch(`${BACKEND}/api/reset-queue`, { method: 'POST' });
      crawlState.mode = 'idle';
      return { ok: true };
    case 'resetKhameneiPhase2': {
      const r = await fetch(`${BACKEND}/api/khamenei/reset`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mode: 'phase2' }),
      });
      const data = await r.json();
      crawlState.mode = 'idle';
      return { ok: !!data.ok, ...data };
    }
    case 'getStats':
      return getStats(msg.site || 'thesaurus');
    case 'openProject':
      return controlPicker('openProject', { projectId: msg.projectId });
    case 'testProject':
      return controlPicker('testProject', { projectId: msg.projectId });
    case 'startReading':
      return startReading(msg, sender);
    case 'stopReading':
      return stopReading();
    case 'phaseProgress':
    case 'phaseDone':
      // relay to popup if open
      return { ok: true };
    case 'khameneiListScanned':
      if (crawlState.mode === 'phase1' && crawlState.site === 'khamenei') {
        await continueKhameneiPhase1(msg);
      }
      return { ok: true };
    case 'khameneiExtractResult':
      if (crawlState.mode === 'phase2' && crawlState.site === 'khamenei') {
        await onKhameneiPhase2Result(msg);
      }
      return { ok: true };
    default:
      return { error: 'unknown' };
  }
}

async function runBoth(site) {
  const p1 = await runPhase1(site);
  if (p1?.ok === false) return p1;
  // wait until phase1 finishes (thesaurus content script is long-running)
  if (site === 'thesaurus') {
    await waitUntilIdle();
  }
  return runPhase2(site);
}

async function waitUntilIdle() {
  for (let i = 0; i < 200000; i++) {
    if (crawlState.mode === 'idle') return;
    await sleep(1000);
  }
}

async function runPhase1(site) {
  await chrome.storage.local.set({ crawlStop: false });
  crawlState.mode = 'phase1';
  crawlState.site = site;

  if (site === 'thesaurus') {
    const tabId = await ensureSiteTab('thesaurus');
    await ensureContentScript(tabId, 'thesaurus');
    // fire and forget long harvest — progress via messages
    chrome.tabs.sendMessage(tabId, { action: 'phase1List', delayMs: 350 }, (resp) => {
      crawlState.mode = 'idle';
      chrome.runtime.sendMessage({ action: 'phaseDone', phase: 1, site: 'thesaurus', summary: resp?.summary });
    });
    return { ok: true, message: 'فاز۱ اصطلاح‌نامه شروع شد (Elastic ۱۰۰تایی × ۱۳ علم)' };
  }

  // Khamenei phase 1 — walk YEARS, not pages. The site ignores ?page=N
  // entirely; each Jalali year is ONE complete list page
  // (/speech?nt=2&year=YYYY, 28-79 items). Unfiltered /speech shows only the
  // latest year, so: open it, then walk backwards year by year until
  // 2 consecutive empty years (or MIN_YEAR floor).
  crawlState.khamenei = { nextYear: null, emptyStreak: 0, MIN_YEAR: 1370, ids: [], idx: 0, delayMs: 2000, errors: 0 };
  await navigateToUrl(`https://${KHAMENEI_HOST}/speech`, 'khamenei');
  return { ok: true, message: 'فاز۱ بیانات: در حال کشف سال‌به‌سال (هر سال = یک صفحه کامل)...' };
}

// Pure year-walk decision (unit-tested in test_khamenei_years.js).
// s: { nextYear, emptyStreak, MIN_YEAR } — mutated in place.
// msg: khameneiListScanned { total, maxYear } from the page just scanned.
// Returns { url } to navigate next, or { done: true, reason: 'empty'|'floor' }.
function nextKhameneiYear(s, msg) {
  s.emptyStreak = s.emptyStreak || 0;
  if (s.nextYear == null) {
    // First page (unfiltered /speech) already seeded the latest year.
    s.nextYear = (msg && msg.maxYear) || 1404;
  } else if (msg && msg.total === 0) {
    s.emptyStreak += 1;
  } else {
    s.emptyStreak = 0;
  }
  s.nextYear -= 1;
  if (s.emptyStreak >= 2) return { done: true, reason: 'empty' };
  if (s.nextYear < s.MIN_YEAR) return { done: true, reason: 'floor' };
  return { url: `https://${KHAMENEI_HOST}/speech?nt=2&year=${s.nextYear}` };
}

async function continueKhameneiPhase1(msg) {
  if (crawlState.mode !== 'phase1') return;
  const stop = await chrome.storage.local.get(['crawlStop']);
  if (stop.crawlStop) {
    crawlState.mode = 'idle';
    return;
  }
  const s = crawlState.khamenei;
  const next = nextKhameneiYear(s, msg);
  if (next.done) {
    crawlState.mode = 'idle';
    chrome.runtime.sendMessage({ action: 'phaseDone', phase: 1, site: 'khamenei' });
    return;
  }
  await sleep(s.delayMs);
  await navigateToUrl(next.url, 'khamenei');
}

async function runPhase2(site) {
  await chrome.storage.local.set({ crawlStop: false });
  crawlState.mode = 'phase2';
  crawlState.site = site;

  if (site === 'thesaurus') {
    const tabId = await ensureSiteTab('thesaurus');
    await ensureContentScript(tabId, 'thesaurus');
    chrome.tabs.sendMessage(tabId, { action: 'phase2Save', batchSize: 50 }, (resp) => {
      crawlState.mode = 'idle';
      chrome.runtime.sendMessage({ action: 'phaseDone', phase: 2, site: 'thesaurus', summary: resp?.summary });
    });
    return { ok: true, message: 'فاز۲ اصطلاح‌نامه: ذخیره کامل از صف...' };
  }

  // Khamenei: pull pending speech IDs and visit pages
  const ids = await fetchPendingKhameneiIds();
  if (!ids.length) {
    crawlState.mode = 'idle';
    const st = await fetch(`${BACKEND}/api/pipeline/status?site=khamenei`).then((r) => r.json());
    if (st.complete) {
      return {
        ok: true,
        alreadyComplete: true,
        message: `همه بیانات ذخیره شده‌اند. آخرین: ${st.phase2?.khamenei_last_crawled_at || '-'}`,
      };
    }
    return { ok: false, message: 'صف بیانات خالی است — اول فاز ۱ را بزنید' };
  }
  crawlState.khamenei.ids = ids;
  crawlState.khamenei.idx = 0;
  crawlState.khamenei.errors = 0;
  await navigateKhameneiDetail();
  return { ok: true, message: `فاز۲: ${ids.length} بیان در صف` };
}

async function fetchPendingKhameneiIds(limit = 500) {
  try {
    const r = await fetch(`${BACKEND}/api/phase2/next-batch?site=khamenei&limit=${limit}`);
    const data = await r.json();
    return (data.items || [])
      .map((j) => {
        const m = (j.url || '').match(/id=(\d+)/);
        return m ? { id: m[1], queue_id: j.id, url: j.url } : null;
      })
      .filter(Boolean);
  } catch (_) {
    return [];
  }
}

async function navigateKhameneiDetail() {
  const s = crawlState.khamenei;
  if (crawlState.mode !== 'phase2') return;
  if (s.idx >= s.ids.length) {
    // try refresh more pending
    const more = await fetchPendingKhameneiIds();
    if (more.length) {
      s.ids = more;
      s.idx = 0;
    } else {
      crawlState.mode = 'idle';
      chrome.runtime.sendMessage({ action: 'phaseDone', phase: 2, site: 'khamenei' });
      return;
    }
  }
  const item = s.ids[s.idx];
  await sleep(s.delayMs);
  await navigateToUrl(item.url || `https://${KHAMENEI_HOST}/speech-content?id=${item.id}`, 'khamenei');
}

async function onKhameneiPhase2Result(msg) {
  const s = crawlState.khamenei;
  if (msg.status === 'inserted' || msg.status === 'updated' || msg.status === 'skipped') {
    s.errors = 0;
    s.delayMs = Math.max(1500, Math.floor(s.delayMs * 0.95));
  } else {
    s.errors += 1;
    s.delayMs = Math.min(20000, Math.floor(s.delayMs * 1.5) + 500);
    if (s.errors >= 5) {
      crawlState.mode = 'idle';
      return;
    }
  }
  s.idx += 1;
  await navigateKhameneiDetail();
}

async function controlPicker(action, extra) {
  const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
  const tab = tabs[0];
  if (!tab?.id || !/^https?:/i.test(tab.url || '')) {
    return { ok: false, message: 'یک صفحه وب باز کن' };
  }
  try {
    await chrome.scripting.executeScript({ target: { tabId: tab.id }, files: ['content_picker.js'] });
  } catch (_) {}
  try {
    return await chrome.tabs.sendMessage(tab.id, { action, ...(extra || {}) });
  } catch (e) {
    return { ok: false, message: e.message };
  }
}

async function startSingle() {
  const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tabs[0]) return { ok: false, message: 'تب فعالی نیست' };
  const url = tabs[0].url || '';
  const site = /khamenei\.ir/i.test(url) ? 'khamenei' : 'thesaurus';
  await ensureContentScript(tabs[0].id, site);
  try {
    return await chrome.tabs.sendMessage(tabs[0].id, { action: 'extractCurrentPage' });
  } catch (e) {
    return { ok: false, message: e.message };
  }
}

async function getStats(site) {
  try {
    const [pipe, stats, kh] = await Promise.all([
      fetch(`${BACKEND}/api/pipeline/status?site=${site}`).then((r) => r.json()),
      fetch(`${BACKEND}/api/stats`).then((r) => r.json()).catch(() => ({})),
      fetch(`${BACKEND}/api/khamenei/stats`).then((r) => r.json()).catch(() => ({})),
    ]);
    return {
      pipeline: pipe,
      stats,
      khStats: kh,
      mode: crawlState.mode,
      site: crawlState.site,
    };
  } catch (e) {
    return { error: e.message };
  }
}

async function ensureSiteTab(site) {
  const host = site === 'khamenei' ? KHAMENEI_HOST : THESAURUS_HOST;
  const start =
    site === 'khamenei'
      ? `https://${host}/speech`
      : `https://${host}/fa/list/`;
  const tabs = await chrome.tabs.query({ url: `https://${host}/*` });
  if (tabs.length) {
    crawlState.currentTabId = tabs[0].id;
    return tabs[0].id;
  }
  const t = await chrome.tabs.create({ url: start, active: false });
  crawlState.currentTabId = t.id;
  await sleep(2500);
  return t.id;
}

async function navigateToUrl(url, site) {
  const host = site === 'khamenei' ? KHAMENEI_HOST : THESAURUS_HOST;
  const tabs = await chrome.tabs.query({ url: `https://${host}/*` });
  if (tabs.length) {
    crawlState.currentTabId = tabs[0].id;
    await chrome.tabs.update(tabs[0].id, { url, active: false });
  } else {
    const t = await chrome.tabs.create({ url, active: false });
    crawlState.currentTabId = t.id;
  }
}

async function ensureContentScript(tabId, site) {
  try {
    await chrome.tabs.sendMessage(tabId, { action: 'ping' });
  } catch (_) {
    const files =
      site === 'khamenei' ? ['shared.js', 'content_khamenei.js'] : ['shared.js', 'content_thesaurus.js'];
    await chrome.scripting.executeScript({ target: { tabId }, files });
  }
}

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

// Auto-trigger extract/discover when khamenei tab finishes loading during crawl
chrome.tabs.onUpdated.addListener(async (tabId, info, tab) => {
  if (info.status !== 'complete') return;
  if (tabId !== crawlState.currentTabId) return;
  if (!tab.url || !tab.url.includes(KHAMENEI_HOST)) return;
  if (crawlState.site !== 'khamenei') return;
  if (crawlState.mode !== 'phase1' && crawlState.mode !== 'phase2') return;

  try {
    await ensureContentScript(tabId, 'khamenei');
    if (crawlState.mode === 'phase1' && /\/speech(\?|$)/.test(tab.url)) {
      await chrome.tabs.sendMessage(tabId, { action: 'discoverSpeechIds' });
    } else if (crawlState.mode === 'phase2' && tab.url.includes('speech-content')) {
      await chrome.tabs.sendMessage(tabId, { action: 'extractCurrentPage' });
    }
  } catch (e) {
    console.error(e);
    crawlState.khamenei.errors += 1;
    if (crawlState.mode === 'phase2') {
      crawlState.khamenei.idx += 1;
      await navigateKhameneiDetail();
    }
  }
});

let reading = false;

// --- Next-page strategies ----------------------------------------------------
// next_param holds a spec string (next_mode stays 'url_param' for backend compat):
//   ''                              → none
//   '<param>'                       → legacy: increment ?<param>=N query param
//   'next-link' | 'next-link:<css>' → follow the next-page link found on the page
//   'url-number'                    → last number in the path, +step, zero-pad kept
//   'path-number'                   → PCM-EXT-09: first FULLY numeric path
//                                     segment, +step, zero-pad kept; the
//                                     site-written slug stays untouched
//                                     (/questions/4/<slug> → /questions/5/<slug>)
//   'regex:<pattern>'               → exactly one digit capture group, +step
//   'hash'                          → PCM-EXT-08: hash-based SPA; the page's own
//                                     «آیه بعد» button (viewer(S,A)) is the
//                                     next page; next URL comes from the DOM.

function parseNextSpec(project) {
  const spec = String((project && project.next_param) || '').trim();
  if (!spec) return { kind: 'none' };
  if (spec === 'next-link' || spec.indexOf('next-link:') === 0) {
    return { kind: 'nextLink', selector: spec === 'next-link' ? '' : spec.slice('next-link:'.length).trim() };
  }
  if (spec === 'hash') return { kind: 'hash' };
  if (spec === 'url-number') return { kind: 'number' };
  if (spec === 'path-number') return { kind: 'pathNumber' };
  if (spec.indexOf('regex:') === 0) return { kind: 'regex', pattern: spec.slice('regex:'.length).trim() };
  return { kind: 'param', param: spec };
}

function bumpNumber(numStr, step) {
  const n = parseInt(numStr, 10) + step;
  if (!Number.isFinite(n) || n < 0) throw new Error('عدد ' + numStr + ' جلو نمی‌رود');
  return (numStr.length > 1 && numStr[0] === '0') ? String(n).padStart(numStr.length, '0') : String(n);
}

// ── PCM-20.10: حد عددی توقف (stop rule) ────────────────────────────────
// «تا کجا بروی» روی همان مقیاسی که advanceUrl جلو می‌رود (شماره‌ی صفحه).
// stopNumber خالی/۰ = بدون حد. با stop-token (دکمه‌ی توقف) مستقل است:
// هر دو باید برقرار باشند تا run زنده بماند.
function parseStopSpec(project) {
  const raw = String((project && (project.stop_number != null ? project.stop_number : project.stopNumber)) || '').trim();
  if (!raw) return null;
  const n = parseInt(raw, 10);
  return Number.isFinite(n) && n > 0 ? n : null;
}

// شماره‌ی عددی صفحه‌ای که آدرسش `url` است — با همان روشی که advanceUrl
// جلو می‌رود. null اگر قابل استخراج نبود (در آن صورت حد اعمال نمی‌شود).
// PCM-EXT-08: شمارهٔ صفحه در آدرس‌های hash-based (تفسیر گرااتی):
//   #numsooreh=S&numayeh=A → S*10000+A — همان مقیاسی که دکمهٔ «آیه بعد»
//   جلو می‌رود، پس حد عددی (stop_number) روی آن معنا دارد (مثلا حد 20008 =
//   سورهٔ ۲ آیّهٔ ۸؛ 1142716 = آخر قرآن). آدرس بدون numayeh → null.
function hashNumber(hash) {
  if (!hash) return null;
  const parts = String(hash).split('&');
  let s = null; let a = null;
  for (let i = 0; i < parts.length; i += 1) {
    const kv = parts[i].split('=');
    const k = String(kv[0] || '').toLowerCase();
    const v = String(kv[1] || '').trim();
    if (k === 'numsooreh' && /^\d+$/.test(v)) s = parseInt(v, 10);
    if (k === 'numayeh' && /^\d+$/.test(v)) a = parseInt(v, 10);
  }
  if (s === null || a === null) return null;
  return s * 10000 + a;
}

function pageNumberOf(url, project) {
  let u;
  try { u = new URL(url); } catch (_) { return null; }
  const spec = parseNextSpec(project);
  if (spec.kind === 'hash') {
    return hashNumber(u.hash.replace(/^#/, ''));
  }
  if (spec.kind === 'pathNumber') {
    // PCM-EXT-09: اولین بخشِ کاملاً عددی مسیر (/questions/4/<slug> → 4)
    const segs = u.pathname.split('/');
    for (let i = 0; i < segs.length; i += 1) {
      if (/^\d+$/.test(segs[i])) return parseInt(segs[i], 10);
    }
    return null;
  }
  if (spec.kind === 'param') {
    const v = u.searchParams.get(spec.param);
    return v !== null && /^\d+$/.test(v) ? parseInt(v, 10) : null;
  }
  if (spec.kind === 'regex') {
    const m = spec.pattern ? new RegExp(spec.pattern).exec(u.pathname) : null;
    if (m) {
      const g = m.slice(1).find((x) => x !== undefined);
      if (g && /^\d+$/.test(g)) return parseInt(g, 10);
    }
    return null;
  }
  // number / nextLink / none: آخرین عدد مسیر
  const runs = u.pathname.match(/\d+/g);
  return runs ? parseInt(runs[runs.length - 1], 10) : null;
}

// { done, why } — done=true یعنی run باید پایان یابد (حد عددی رسید/عبور کرد).
// PCM-EXT-10.1: `baseline` = شمارهٔ صفحهٔ «نقطهٔ شروع خواندن» (لنگر حد نسبی).
// اگر موجود باشد، حد یعنی «stopAt صفحهٔ دیگر بعد از baseline» — نه عدد مطلق در
// مقیاس سایت (رفتار قدیمی که کاربر با اعداد خام 20000/30000/… روش hash مواجه
// می‌شد و نمی‌دانست از کجا می‌آیند).
function checkStopUrl(targetUrl, project, baseline) {
  const stopAt = parseStopSpec(project);
  if (!stopAt) return { done: false };
  const n = pageNumberOf(targetUrl, project);
  if (n === null) return { done: false }; // حد اعمال‌پذیر نیست
  if (baseline != null && Number.isFinite(baseline)) {
    const limit = baseline + stopAt;
    if (n > limit) {
      return { done: true, why: `به حد نسبی رسید: ${stopAt} صفحهٔ دیگر بعد از ${baseline} خوانده شد (حالا روی عدد ${n})` };
    }
    return { done: false };
  }
  // رفتار قدیمی (baseline نامعلوم): حد مطلق در مقیاس سایت.
  if (n > stopAt) return { done: true, why: 'حد عددی ' + stopAt + ' از عدد ' + n + ' عبور کرد' };
  if (n === stopAt) return { done: true, why: 'به حد عددی ' + stopAt + ' رسید (صفحهٔ ' + n + ' آخرین صفحه است)' };
  return { done: false };
}

// ── PCM-EXT-04: توقف بر مبنای تکرار محتوا (content stop) ──────────────
// اگر محتوای مبنایی N صفحهٔ پشت‌سرهم یکسان باشد (یا صفحات خالی باشند)،
// سایت گیر/تکراری است و run تمام می‌شود. مبنای محتوا = فیلدی که کاربر
// انتخاب کرده (project.stop_field)؛ اگر انتخاب نشده باشد، کل محتوای
// استخراج‌شده (ترکیب همه‌ی values).
const SAME_PAGE_LIMIT = 10;

// امضای محتوای یک صفحه: مقدار فیلد مبنایی؛ اگر فیلد انتخاب نشده باشد یا
// در values این صفحه نباشد، ترکیب مرتب‌شده‌ی همه‌ی مقادیر.
function contentSignature(project, values) {
  const v = values || {};
  const field = String((project && (project.stop_field != null ? project.stop_field : project.stopField)) || '').trim();
  if (field && Object.prototype.hasOwnProperty.call(v, field)) {
    return String(v[field] == null ? '' : v[field]);
  }
  return Object.keys(v).sort().map((k) => String(v[k] == null ? '' : v[k])).join('\u0001');
}

// PCM-EXT-10.1: امضای «فقط محتوای متنی» (نقاط css/xpath). برای تشخیص این‌که
// یک SPAی hash-based به صفحهٔ جدید re-render شده یا نه استفاده می‌شود: نقاط
// url/hash_param با ناوبری فوراً تغییر می‌کنند و سیگنال «محتوا رندر شد» نیستند،
// بنابراین اینجا شمرده نمی‌شوند.
function textValuesSig(values, points) {
  const tags = (points || [])
    .filter((p) => p.source === 'css' || p.source === 'xpath')
    .map((p) => String(p.tag || ''))
    .filter(Boolean)
    .sort();
  return tags.map((t) => String((values || {})[t] == null ? '' : (values || {})[t])).join('\u0001');
}

// هش djb2 32-بیت از امضا — مقدار کوچک برای ذخیره در pctRun.
function sigHash(s) {
  let h = 5381;
  for (let i = 0; i < s.length; i += 1) h = ((h << 5) + h + s.charCodeAt(i)) | 0;
  return String(h);
}

// { streak, stop } — streak = تعداد صفحات یکسانِ پشت‌سرهم تا این صفحه (شامل
// آن). stop=true یعنی حد SAME_PAGE_LIMIT رسید و run باید تمام شود.
function updateSameStreak(sameStreak, lastSig, sig) {
  const streak = sig === lastSig ? sameStreak + 1 : 1;
  return { streak, stop: streak >= SAME_PAGE_LIMIT };
}

function advanceUrl(url, project) {
  const spec = parseNextSpec(project);
  if (spec.kind === 'none') throw new Error('قانون صفحه بعد ذخیره نشده');
  if (spec.kind === 'nextLink') throw new Error('روش «لینک صفحه بعد» نیاز به باز شدن صفحه دارد');
  // PCM-EXT-08: آدرس بعدی از DOM (دکمهٔ «آیه بعد») می‌آید، نه از همین آدرس.
  if (spec.kind === 'hash') throw new Error('روش «آیه بعد» نیاز به باز شدن صفحه دارد');
  const step = Number((project && project.next_step) || 1) || 1;
  const next = new URL(url);
  if (spec.kind === 'param') {
    const param = spec.param;
    if (!next.searchParams.has(param)) throw new Error('پارامتر ' + param + ' در لینک نیست');
    const n = parseInt(next.searchParams.get(param), 10);
    if (!Number.isFinite(n)) throw new Error('پارامتر صفحه عدد نیست');
    next.searchParams.set(param, String(n + step));
    return next.toString();
  }
  if (spec.kind === 'number') {
    const runs = next.pathname.match(/\d+/g);
    if (!runs) throw new Error('عدد در مسیر آدرس نیست — از روش رجکس استفاده کن');
    const run = runs[runs.length - 1];
    const idx = next.pathname.lastIndexOf(run);
    next.pathname = next.pathname.slice(0, idx) + bumpNumber(run, step) + next.pathname.slice(idx + run.length);
    return next.toString();
  }
  if (spec.kind === 'pathNumber') {
    // PCM-EXT-09: فقط «بخش»ی که کاملاً عدد باشد جلو می‌رود (مثل
    // /questions/4/<slug> → /questions/5/<slug>) و بقیهٔ مسیر — یعنی slug
    // متنی که خود سایت نوشته — دست نمی‌خورد. تفاوت با 'number': آن یکی
    // آخرین توالی عدد مسیر را می‌گیرد (هرجا بود)، این یکی اولین بخشِ
    // تمام‌عددی را.
    const segs = next.pathname.split('/');
    let found = -1;
    for (let i = 0; i < segs.length; i += 1) {
      if (/^\d+$/.test(segs[i])) { found = i; break; }
    }
    if (found < 0) throw new Error('بخشِ کاملاً عددی در مسیر نیست — از رجکس استفاده کن');
    segs[found] = bumpNumber(segs[found], step);
    next.pathname = segs.join('/');
    return next.toString();
  }
  if (spec.kind === 'regex') {
    let re;
    try {
      re = new RegExp(spec.pattern);
    } catch (e) {
      throw new Error('رجکس نامعتبر: ' + e.message);
    }
    const m = re.exec(next.pathname);
    if (!m) throw new Error('رجکس با این آدرس همخوانی ندارد');
    const groups = m.slice(1).filter((g) => g !== undefined);
    if (groups.length !== 1) throw new Error('رجکس باید دقیقا‌ یک گروه ( ) داشته باشد');
    const g = groups[0];
    if (!/^\d+$/.test(g)) throw new Error('گروهِ رجکس عدد نیست');
    const idx = m.index + m[0].indexOf(g);
    next.pathname = next.pathname.slice(0, idx) + bumpNumber(g, step) + next.pathname.slice(idx + g.length);
    return next.toString();
  }
  throw new Error('قانون صفحه بعد نامعتبر است');
}

async function postReport(projectId, body) {
  const r = await fetch(`${BACKEND}/api/projects/${projectId}/report`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  return r.json();
}

function newToken() {
  return 'r' + Date.now().toString(36) + '-' + Math.random().toString(36).slice(2, 10);
}

// PCM-EXT-03: هویت پایدارِ این مرورگر (برای قفل بین‌مرورگری run).
// یک‌بار ساخته می‌شود و تا همیشه در storage.local همین پروفایل می‌ماند.
async function getOwnerId() {
  const stored = await chrome.storage.local.get('pctOwner');
  if (stored.pctOwner) return stored.pctOwner;
  const owner = 'b' + Date.now().toString(36) + '-' + Math.random().toString(36).slice(2, 10);
  await chrome.storage.local.set({ pctOwner: owner });
  return owner;
}

// ── PCM-EXT-03: قفل run بین‌مرورگری — حقیقت در backend است ─────────────
// claim: گرفتن قفل (اتمی در سرور). 409 = نشست دیگر دارد می‌خواند.
async function claimRun(projectId, owner, token) {
  const resp = await fetch(`${BACKEND}/api/projects/${projectId}/run`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ owner, token }),
  });
  const body = await resp.json().catch(() => ({}));
  return { code: resp.status, body };
}

// heartbeat: تمدید قفل. 409 = دیگر مالک قفل نیستیم → run باید خود را متوقف کند.
// خطای شبکهٔ گذرا run را نمی‌کشد (heartbeat بعدی حقیقت را می‌گوید).
async function heartbeatRun(projectId, owner, token) {
  try {
    const resp = await fetch(`${BACKEND}/api/projects/${projectId}/run/heartbeat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ owner, token }),
    });
    if (resp.status === 409) return { ok: false, body: await resp.json().catch(() => ({})) };
    return { ok: true, body: {} };
  } catch (_) {
    return { ok: true, body: {} };
  }
}

// release: آزادسازی قفل (توقف/پایان run/بسته‌شدن تب). best-effort: اگر نشود،
// TTL سرور قفل را خودکار منقضی می‌کند.
async function releaseRun(projectId, owner, token) {
  if (!owner || !token) return;
  try {
    await fetch(`${BACKEND}/api/projects/${projectId}/run/release`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ owner, token }),
    });
  } catch (_) { /* TTL سرور قفل را منقضی می‌کند */ }
}

async function startReading(msg, sender) {
  const stored = await chrome.storage.local.get('pctRun');
  if (stored.pctRun?.active) {
    return { ok: false, message: 'یک پروژهٔ دیگر در حال خواندن است — اول «توقف» را بزن.' };
  }
  const projectId = msg.projectId;
  const info = await fetch(`${BACKEND}/api/projects/${projectId}`).then((r) => r.json());
  if (!info.id) return { ok: false, message: 'پروژه پیدا نشد' };
  if (info.status === 'draft' || !info.tested_at) {
    return { ok: false, message: 'اول آزمایش این صفحه باید موفق شود' };
  }
  if (info.next_mode !== 'url_param' || !info.next_param) {
    return { ok: false, message: 'قانون صفحه بعد ذخیره نشده' };
  }
  const pages = Math.max(1, Math.min(12, Number(msg.pagesPerMinute || info.pages_per_minute || 4)));
  // PCM-EXT-10.1: baselineِ حد نسبی = شمارهٔ «صفحهٔ فعلی» (آخرین صفحهٔ خوانده‌شده)
  // هنگام شروع. stop_number از این‌جای پس یعنی «N صفحهٔ دیگر». اگر عدد قابل
  // استخراج نباشد baseline خالی می‌ماند و حد مطلق (legacy) اعمال می‌شود.
  let stopBaseline = null;
  let stopAnchor = '';
  {
    const baseU = String(info.cursor_url || info.start_url || '');
    stopBaseline = pageNumberOf(baseU, info);
    const sv = String(info.stop_number || '').trim();
    if (stopBaseline != null && sv) stopAnchor = sv;
  }
  // PCM-EXT-10.1: امضای متنی «صفحهٔ فعلی» (صفحهٔ آزمایش‌شده) — «محتوای قبلی»
  // اولیه برای تشخیص re-render در SPAهای hash-based.
  const lastTextSig = String(msg.prevTextSig || '');
  // PCM-EXT-03: قفل run بین‌مرورگری — backend «حقیقت»ِ یک-run-در-هر-زمان است.
  // اگر مرورگر/دستگاه دیگری همین پروژه را می‌خواند، اینجا 409 می‌گیریم.
  const owner = await getOwnerId();
  const token = newToken();
  let claim;
  try {
    claim = await claimRun(projectId, owner, token);
  } catch (e) {
    return { ok: false, message: 'اتصال به سرور برای شروع ممکن نشد: ' + e.message };
  }
  if (claim.code === 409) {
    return { ok: false, message: claim.body?.message || 'این پروژه همین حالا در حال خواندن است (نشست دیگر) — صبر کن یا آن را متوقف کن.' };
  }
  if (claim.code === 404) {
    // backend قدیمی بدون route قفل: رفتار v3.7 (فقط محلی) ادامه می‌یابد.
    console.warn('PCM-EXT-03: run-lock route missing — backend outdated');
  } else if (claim.code !== 200) {
    return { ok: false, message: 'ثبت run در سرور ممکن نشد (کد ' + claim.code + ')' };
  }
  // تب اختصاصی در background: تب کاربر (و پنلش) دست‌نخورده می‌ماند و می‌تواند
  // در همان meanwhile پروژهٔ دیگر را ویرایش کند.
  const tab = await chrome.tabs.create({ url: 'about:blank', active: false });
  const tabId = tab.id;
  await postReport(projectId, { status: 'running', message: `خواندن شروع شد، ${pages} صفحه در دقیقه` });
  await chrome.storage.local.set({
    pctRun: { active: true, token, owner, projectId, tabId, pagesPerMinute: pages, emptyStreak: 0, sameStreak: 0, lastSig: '', nextUrl: String(msg.nextUrl || ''), stopBaseline, stopAnchor, lastTextSig },
  });
  chrome.alarms.create('pctRead', { delayInMinutes: 1, periodInMinutes: 1 });
  runMinute();
  return { ok: true, message: `خواندن شروع شد، ${pages} صفحه در دقیقه` };
}

async function stopReading() {
  const stored = await chrome.storage.local.get('pctRun');
  const run = stored.pctRun;
  await chrome.alarms.clear('pctRead');
  if (run?.active && run?.projectId) {
    await postReport(run.projectId, { status: 'paused', message: 'خواندن متوقف شد' });
    await releaseRun(run.projectId, run.owner, run.token); // PCM-EXT-03
  }
  // تغییر token: حلقه‌ای که در حال اجراست ناهمخوانی را می‌بیند و می‌ایستد؛
  // هیچ snapshot قدیمی دیگر نمی‌تواند active:true را برگرداند.
  await chrome.storage.local.set({
    pctRun: { ...(run || {}), active: false, token: newToken() },
  });
  return { ok: true, message: 'خواندن متوقف شد' };
}

function waitComplete(tabId, timeout, hashOnly) {
  // PCM-EXT-08: برای hash-based SPA (تفسیر گرااتی) تغییر hash = بارگذاری AJAX
  // محتواست و load event جدید نمی‌دهد. در حالت hashOnly (آدرس‌های قبلی و جدید
  // یکی‌شان hash دارند) صبر به 'complete' وصل نمی‌شود؛ بعد از یک load کوتاه،
  // تا زمان‌بندیِ AJAX (محدود به timeout) امتداد می‌یابد.
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      chrome.tabs.onUpdated.removeListener(onUp);
      reject(new Error('صفحه دیر باز شد'));
    }, timeout);
    function settle() {
      clearTimeout(timer);
      chrome.tabs.onUpdated.removeListener(onUp);
      if (hashOnly) {
        const extra = new Promise((r) => setTimeout(r, Math.min(4000, Math.max(0, timeout - 4000))));
        extra.then(resolve, resolve);
      } else {
        resolve();
      }
    }
    function onUp(id, info) {
      if (id === tabId && info.status === 'complete') settle();
    }
    chrome.tabs.onUpdated.addListener(onUp);
  });
}

async function extractWhenReady(tabId, payload) {
  let last = 'اسکریپت صفحه جواب نداد';
  for (let i = 0; i < 8; i += 1) {
    try {
      await chrome.scripting.executeScript({ target: { tabId }, files: ['content_picker.js'] });
    } catch (_) {}
    try {
      return await chrome.tabs.sendMessage(tabId, payload);
    } catch (e) {
      last = e.message;
      await sleep(400);
    }
  }
  return { ok: false, message: last };
}

// توقفی که token هنوز هم‌خوانی دارد: گزارش paused + غیرفعال‌سازی. اگر کاربر
// از قبل «توقف» زده باشد (token عوض شده)، دست به storage نمی‌زند.
async function endRun(projectId, message, token) {
  await postReport(projectId, { status: 'paused', message });
  const stored = await chrome.storage.local.get('pctRun');
  const cur = stored.pctRun;
  if (cur?.active && cur.token === token) {
    await releaseRun(projectId, cur.owner, token); // PCM-EXT-03: فقط run زنده قفل را رها می‌کند
    await chrome.storage.local.set({ pctRun: { ...cur, active: false } });
  }
  await chrome.alarms.clear('pctRead');
}

// خفتی که به توقف واکنش نشان می‌دهد: هر یک ثانیه یک‌بار چک می‌کند.
async function sleepLive(ms, isLive) {
  const end = Date.now() + ms;
  while (Date.now() < end) {
    await sleep(Math.min(1000, end - Date.now()));
    if (!(await isLive())) return false;
  }
  return true;
}

async function runMinute() {
  if (reading) return;
  const stored = await chrome.storage.local.get('pctRun');
  const run0 = stored.pctRun;
  if (!run0?.active) return;
  // خواندنی قدیمی (بدون token، قبل از v3.7): پایان می‌دهد و شروع دوباره می‌خواهد.
  if (!run0.token) {
    await postReport(run0.projectId, { status: 'paused', message: 'خواندن نسخهٔ قدیمی قطع شد — دوباره «آزمایش و شروع» بزن.' });
    await chrome.storage.local.set({ pctRun: { ...run0, active: false } });
    await chrome.alarms.clear('pctRead');
    return;
  }
  const token = run0.token;
  const owner = run0.owner || ''; // PCM-EXT-03: run‌های legacy بدون owner، heartbeat نمی‌فرستند
  // هویت این اجرا: تا tokenِ storage با token ما یکی باشد و active باشد، زنده‌ایم؛
  // «توقف» فقط token را عوض می‌کند.
  const isLive = async () => {
    const fresh = await chrome.storage.local.get('pctRun');
    return !!(fresh.pctRun && fresh.pctRun.active && fresh.pctRun.token === token);
  };
  reading = true;
  let saved = 0;
  let skipped = 0;
  let failed = 0;
  let emptyStreak = run0.emptyStreak || 0;
  let sameStreak = run0.sameStreak || 0;
  let lastSig = String(run0.lastSig || '');
  let nextUrl = run0.nextUrl || '';
  // PCM-EXT-10.1: وضعیت حد نسبی + «محتوای قبلی» برای re-renderِ hash-based.
  let stopBaseline = run0.stopBaseline != null ? run0.stopBaseline : null;
  let stopAnchor = String(run0.stopAnchor || '');
  let lastTextSig = String(run0.lastTextSig || '');
  const run = { projectId: run0.projectId, tabId: run0.tabId, pagesPerMinute: run0.pagesPerMinute };
  try {
    const project = await fetch(`${BACKEND}/api/projects/${run.projectId}`).then((r) => r.json());
    if (!project?.id || project.status === 'paused') {
      await endRun(run.projectId, 'پروژه متوقف یا پیدا نشد.', token);
      return;
    }
    const spec = parseNextSpec(project);
    let cursor = project.cursor_url || project.start_url;
    // PCM-EXT-10.1: اگر عدد توقف از آخرین لنگر تغییر کرده، baseline را به
    // «موقعیت فعلی» (آخرین صفحهٔ خوانده‌شده) باز-لنگر بزن تا حد تازه یعنی
    // «N صفحهٔ دیگر از همین‌جا».
    {
      const curStopRaw = String(project.stop_number || '').trim();
      if (curStopRaw && curStopRaw !== stopAnchor) {
        const base = pageNumberOf(String(cursor || ''), project);
        if (base != null) stopBaseline = base;
        stopAnchor = curStopRaw;
      }
    }
    const pages = Math.max(1, Math.min(12, Number(run.pagesPerMinute || project.pages_per_minute || 4)));
    const gap = Math.max(2000, Math.floor(60000 / pages) - 4000);
    let target = '';
    if (spec.kind === 'nextLink' || spec.kind === 'hash') {
      // PCM-EXT-08: در روش hash هم مثل next-link، صفحه بعد از خود صفحه
      // (دکمهٔ «آیه بعد» → viewer(S,A)) کشف می‌شود؛ در آزمایش اولین‌اش ذخیره شد.
      target = String(nextUrl || '');
      if (!target) target = cursor; // لینک ذخیره‌شده نیست: اول صفحه فعلی را بخوان تا کشف شود
    } else {
      try {
        target = advanceUrl(cursor, project);
      } catch (e) {
        await endRun(run.projectId, 'نمی‌توان به صفحه بعد رفت: ' + e.message, token);
        return;
      }
    }
    for (let i = 0; i < pages; i += 1) {
      if (!(await isLive())) return; // «توقف» زده شد
      // PCM-EXT-03: heartbeat هر صفحه؛ 409 = قفل حالا با نشست دیگری است.
      if (owner) {
        const hb = await heartbeatRun(run.projectId, owner, token);
        if (!hb.ok) {
          await endRun(run.projectId, 'قفل این run دیگر متعلق به نشست دیگری است — خواندن متوقف شد.', token);
          return;
        }
      }
      if (!target) {
        await endRun(run.projectId, 'لینک صفحه بعد پیدا نشد — خواندن تمام شد.', token);
        return;
      }
      try { await chrome.tabs.get(run.tabId); } catch (_) {
        await endRun(run.projectId, 'تب خواندن بسته شد.', token);
        return;
      }
      // PCM-20.10: حد عددی — قبل از باز کردن صفحه بررسی می‌شود تا از
      // عبور از حد جلوگیری کند (مثلا حد 495: sh495 خوانده می‌شود، sh496 نه).
      const stopCheck = checkStopUrl(target, project, stopBaseline);
      if (stopCheck.done) {
        await endRun(run.projectId, 'خواندن به حد مشخص‌شده رسید: ' + stopCheck.why + '.', token);
        return;
      }
      try {
        await chrome.tabs.update(run.tabId, { url: target });
        // PCM-EXT-08: اگر قبلاً روی همین document بودیم (فقط hash عوض شد) صبر
        // به 'complete' اضافه می‌شود؛ وگرنه load عادی.
        const prevHash = String(cursor || '').indexOf('#') >= 0;
        const nextHash = String(target || '').indexOf('#') >= 0;
        await waitComplete(run.tabId, 20000, prevHash && nextHash);
        if (!(await isLive())) return;
        await sleep(600);
        const result = await extractWhenReady(run.tabId, {
          action: 'extractProject',
          projectId: project.id,
          points: project.points,
          nextSpec: project.next_param || '',
          // PCM-EXT-10.1: برای SPAهای hash-based، تا وقتی متن DOM از «صفحهٔ قبلی»
          // تغییر نکند صبر می‌شود (وگرنه محتوای یک‌صفحه‌قبلی ذخیره می‌شد).
          prevSig: lastTextSig,
          waitHash: spec.kind === 'hash',
        });
        if (!(await isLive())) return;
        // PCM-EXT-03: heartbeat دوم (بعد از extract) تا فاصلهٔ بین‌heartbeat‌ها
        // با سرعت پایین صفحه/دقیقه از TTL سرور عبور نکند.
        if (owner) {
          const hb2 = await heartbeatRun(run.projectId, owner, token);
          if (!hb2.ok) {
            await endRun(run.projectId, 'قفل این run دیگر متعلق به نشست دیگری است — خواندن متوقف شد.', token);
            return;
          }
        }
        // مقصد بعدی: در روش لینک/hash، از خود صفحه؛ در بقیه، از آدرس.
        let nextTarget = '';
        if (spec.kind === 'nextLink' || spec.kind === 'hash') {
          nextTarget = String((result && result.nextUrl) || '');
        } else {
          try {
            nextTarget = advanceUrl(target, project);
          } catch (e) {
            nextTarget = 'ERR:' + e.message;
          }
        }
        const domNext = spec.kind === 'nextLink' || spec.kind === 'hash';
        const advanceFailed = !domNext && nextTarget.indexOf('ERR:') === 0;
        if (!result?.ok) {
          emptyStreak += 1;
          failed += 1;
          await postReport(run.projectId, { failed: 1, cursor_url: target, message: result?.message || 'صفحه خوانده نشد' });
          if (advanceFailed) {
            await endRun(run.projectId, 'نمی‌توان به صفحه بعد رفت: ' + nextTarget.slice(4), token);
            return;
          }
          if (domNext && !nextTarget) {
            await endRun(run.projectId, 'صفحه بعد پیدا نشد. خواندن ایستاد.', token);
            return;
          }
          if (emptyStreak >= 2) {
            await endRun(run.projectId, 'دو صفحه پشت‌سرهم متن نداشت. خواندن ایستاد.', token);
            return;
          }
        } else {
          emptyStreak = 0;
          if (result.status === 'skipped') skipped += 1;
          else saved += 1;
          // PCM-EXT-10.1: متن صفحهٔ ذخیره‌شده را به‌عنوان «محتوای قبلی» برای
          // تشخیص re-renderِ hash بعدی نگه می‌داریم.
          lastTextSig = textValuesSig(result.values, project.points);
          // PCM-EXT-04: توقف بر مبنای تکرار محتوا — ۱۰ صفحهٔ پشت‌سرهم با
          // امضای یکسان (مبنای انتخابی یا کل محتوا) = سایت گیر کرده.
          const st = updateSameStreak(sameStreak, lastSig, sigHash(contentSignature(project, result.values)));
          sameStreak = st.streak;
          lastSig = sigHash(contentSignature(project, result.values));
          if (st.stop) {
            const basis = String(project.stop_field || '').trim();
            await endRun(run.projectId, 'ده صفحهٔ پشت‌سرهم محتوای یکسان (' + (basis ? 'فیلد «' + basis + '»' : 'کل محتوا') + ') داشت — خواندن ایستاد.', token);
            return;
          }
          const label = Object.entries(result.values || {}).map(([k, v]) => `${k}=${String(v || '').slice(0, 24)}`).join(' ');
          const tail = domNext && nextTarget ? ' → ' + nextTarget : '';
          await postReport(run.projectId, {
            cursor_url: target,
            message: `${result.status}: ${label || target}${tail}`,
          });
          if (advanceFailed) {
            await endRun(run.projectId, 'نمی‌توان به صفحه بعد رفت: ' + nextTarget.slice(4), token);
            return;
          }
          if (domNext && !nextTarget) {
            await endRun(run.projectId, 'صفحه ذخیره شد ولی صفحه بعد نداشت — خواندن تمام شد.', token);
            return;
          }
        }
        cursor = target;
        if (nextTarget) {
          if (domNext) nextUrl = nextTarget;
          target = nextTarget;
        }
        if (!(await isLive())) return;
        // ذخیره پیشرفت با همان token — snapshot قدیمی دیگر نمی‌تواند run را
        // بعد از توقف زنده کند.
        await chrome.storage.local.set({
          pctRun: { active: true, token, projectId: run.projectId, tabId: run.tabId, pagesPerMinute: run.pagesPerMinute, emptyStreak, sameStreak, lastSig, nextUrl, stopBaseline, stopAnchor, lastTextSig },
        });
      } catch (e) {
        if (!(await isLive())) return;
        failed += 1;
        await postReport(run.projectId, { failed: 1, message: e.message });
      }
      if (i < pages - 1) {
        if (!(await sleepLive(gap, isLive))) return;
      }
    }
    if (!(await isLive())) return;
    const summary = await fetch(`${BACKEND}/api/projects/${run.projectId}`).then((r) => r.json());
    // آخرین چک: اگر وسط fetch توقف زده شد، «running» قدیمی را بعد از «paused» نپوشانیم.
    if (!(await isLive())) return;
    await postReport(run.projectId, {
      status: 'running',
      message: `این دقیقه ${saved} ذخیره، ${skipped} رد، ${failed} خطا. مجموع ${summary.saved_count || 0}.`,
    });
  } finally {
    reading = false;
  }
}

chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === 'pctRead') runMinute();
});

// اگر تب خواندن بسته شود، run پایان می‌یابد و گزارش می‌دهد.
chrome.tabs.onRemoved.addListener(async (tabId) => {
  const stored = await chrome.storage.local.get('pctRun');
  const run = stored.pctRun;
  if (run?.active && run.tabId === tabId) {
    await chrome.alarms.clear('pctRead');
    await postReport(run.projectId, { status: 'paused', message: 'خواندن متوقف شد — تب خواندن بسته شد.' });
    await releaseRun(run.projectId, run.owner, run.token); // PCM-EXT-03
    await chrome.storage.local.set({ pctRun: { ...run, active: false, token: newToken() } });
  }
});

async function resumeReadingAlarm() {
  const stored = await chrome.storage.local.get('pctRun');
  if (stored.pctRun?.active) {
    chrome.alarms.create('pctRead', { delayInMinutes: 1, periodInMinutes: 1 });
  }
}
chrome.runtime.onStartup.addListener(resumeReadingAlarm);
chrome.runtime.onInstalled.addListener(resumeReadingAlarm);

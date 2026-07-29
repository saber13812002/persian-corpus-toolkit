// Background — orchestrate two-phase crawls for thesaurus + khamenei
const BACKEND = 'http://127.0.0.1:5000';
const KHAMENEI_HOST = 'farsi.khamenei.ir';
const THESAURUS_HOST = 'thesaurus.eiis.iki.ac.ir';

let crawlState = {
  mode: 'idle', // idle | phase1 | phase2 | both
  site: null,
  currentTabId: null,
  khamenei: { listPage: 1, ids: [], idx: 0, delayMs: 2000, errors: 0 },
};

chrome.runtime.onMessage.addListener((msg, _s, sendResponse) => {
  handle(msg).then(sendResponse).catch((e) => sendResponse({ ok: false, message: String(e) }));
  return true;
});

async function handle(msg) {
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
    case 'getStats':
      return getStats(msg.site || 'thesaurus');
    case 'phaseProgress':
    case 'phaseDone':
      // relay to popup if open
      return { ok: true };
    case 'khameneiListScanned':
      if (crawlState.mode === 'phase1' && crawlState.site === 'khamenei') {
        if ((msg.seeded || 0) === 0) crawlState.khamenei.emptyPages = (crawlState.khamenei.emptyPages || 0) + 1;
        else crawlState.khamenei.emptyPages = 0;
        await continueKhameneiPhase1();
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

  // Khamenei: walk list pages and seed IDs
  crawlState.khamenei = { listPage: 1, ids: [], idx: 0, delayMs: 2000, errors: 0 };
  await navigateToUrl(`https://${KHAMENEI_HOST}/speech?page=1`, 'khamenei');
  return { ok: true, message: 'فاز۱ بیانات: در حال کشف لیست...' };
}

async function continueKhameneiPhase1() {
  if (crawlState.mode !== 'phase1') return;
  const stop = await chrome.storage.local.get(['crawlStop']);
  if (stop.crawlStop) {
    crawlState.mode = 'idle';
    return;
  }
  const s = crawlState.khamenei;
  s.emptyPages = (s.emptyPages || 0);
  // caller should set lastSeeded via message — check storage
  s.listPage += 1;
  if (s.listPage > 800 || s.emptyPages >= 3) {
    crawlState.mode = 'idle';
    chrome.runtime.sendMessage({ action: 'phaseDone', phase: 1, site: 'khamenei' });
    return;
  }
  await sleep(s.delayMs);
  await navigateToUrl(`https://${KHAMENEI_HOST}/speech?page=${s.listPage}`, 'khamenei');
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

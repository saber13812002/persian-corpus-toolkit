// Background Service Worker v2 - Multi-site support
const BACKEND = 'http://127.0.0.1:5000';

let crawlState = {
  mode: 'idle',         // 'idle', 'single', 'thesaurus_full', 'khamenei_full'
  site: null,           // 'thesaurus', 'khamenei'
  currentTabId: null,
  stats: { crawled: 0, skipped: 0, errors: 0 },
  thesaurusFull: {
    scienceIds: ['040','050','060','070','080','090','100','110','120'],
    currentScienceIdx: 0,
    currentPage: 1,
    maxPages: 50,
  },
  khameneiFull: {
    ids: [],
    currentIdx: 0,
  }
};

// ═══ Message handling ═══
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  handleMessage(msg, sender, sendResponse);
  return true;
});

async function handleMessage(msg, sender, sendResponse) {
  switch (msg.action) {
    case 'getState': sendResponse({ state: crawlState }); break;
    case 'startSingle': await startSingle(); sendResponse({ ok: true }); break;
    case 'startThesaurusFull': await startThesaurusFull(); sendResponse({ ok: true }); break;
    case 'startKhameneiFull': await startKhameneiFull(); sendResponse({ ok: true }); break;
    case 'stop': crawlState.mode = 'idle'; sendResponse({ ok: true }); break;
    case 'seedThesaurus': await seedThesaurus(); sendResponse({ ok: true }); break;
    case 'seedKhamenei': await seedKhameneiFromActive(); sendResponse({ ok: true }); break;
    case 'reset': await reset(); sendResponse({ ok: true }); break;
    case 'getStats': sendResponse(await getStats()); break;
    case 'khameneiListScanned': await onKhameneiListScanned(); sendResponse({ ok: true }); break;
    case 'continueFull': await continueFull(); sendResponse({ ok: true }); break;
    default: sendResponse({ error: 'unknown action' }); break;
  }
}

// ═══ Single page crawl ═══
async function startSingle() {
  const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tabs[0]) return;
  crawlState.mode = 'single';
  crawlState.currentTabId = tabs[0].id;
  crawlState.site = tabs[0].url?.includes('khamenei') ? 'khamenei' : 'thesaurus';
  chrome.tabs.sendMessage(tabs[0].id, { action: 'extractCurrentPage' });
}

// ═══ Thesaurus full crawl ═══
async function startThesaurusFull() {
  crawlState.mode = 'thesaurus_full';
  crawlState.site = 'thesaurus';
  crawlState.stats = { crawled: 0, skipped: 0, errors: 0 };
  crawlState.thesaurusFull = {
    scienceIds: ['040','050','060','070','080','090','100','110','120'],
    currentScienceIdx: 0,
    currentPage: 1,
    maxPages: 50
  };
  await navigateThesaurusPage();
}

async function navigateThesaurusPage() {
  const s = crawlState.thesaurusFull;
  if (s.currentScienceIdx >= s.scienceIds.length) {
    crawlState.mode = 'idle';
    console.log('🎉 Thesaurus full crawl complete!');
    return;
  }
  const sid = s.scienceIds[s.currentScienceIdx];
  const url = `https://thesaurus.eiis.iki.ac.ir/fa/list?type=type01&ScienceId=${sid}&page=${s.currentPage}`;
  
  await navigateToUrl(url, 'thesaurus');
}

// ═══ Khamenei full crawl ═══
async function startKhameneiFull() {
  crawlState.mode = 'khamenei_full';
  crawlState.site = 'khamenei';
  crawlState.stats = { crawled: 0, skipped: 0, errors: 0 };

  // First, get all queued IDs from backend
  try {
    const r = await fetch(`${BACKEND}/api/queue?filter=pending&limit=200`);
    const jobs = await r.json();
    crawlState.khameneiFull.ids = jobs
      .filter(j => j.url?.includes('speech-content'))
      .map(j => {
        const m = j.url.match(/id=(\d+)/);
        return m ? m[1] : null;
      })
      .filter(Boolean);
    console.log(`[Khamenei] ${crawlState.khameneiFull.ids.length} speech IDs in queue`);
  } catch (e) {
    console.error('[Khamenei] Failed to get IDs:', e);
  }

  if (crawlState.khameneiFull.ids.length === 0) {
    // No IDs in queue yet - navigate to list page first
    await navigateToUrl('https://farsi.khamenei.ir/speech', 'khamenei');
    return;
  }
  await navigateKhameneiPage();
}

async function navigateKhameneiPage() {
  const s = crawlState.khameneiFull;
  if (s.currentIdx >= s.ids.length) {
    crawlState.mode = 'idle';
    console.log('🎉 Khamenei full crawl complete!');
    return;
  }
  const sid = s.ids[s.currentIdx];
  const url = `https://farsi.khamenei.ir/speech-content?id=${sid}`;
  await navigateToUrl(url, 'khamenei');
}

async function onKhameneiListScanned() {
  if (crawlState.mode !== 'khamenei_full') return;
  // Refresh the ID list from backend
  try {
    const r = await fetch(`${BACKEND}/api/queue?filter=pending&limit=200`);
    const jobs = await r.json();
    crawlState.khameneiFull.ids = jobs
      .filter(j => j.url?.includes('speech-content'))
      .map(j => {
        const m = j.url.match(/id=(\d+)/);
        return m ? m[1] : null;
      })
      .filter(Boolean);
    crawlState.khameneiFull.currentIdx = 0;
    console.log(`[Khamenei] Refreshed: ${crawlState.khameneiFull.ids.length} IDs`);
    await navigateKhameneiPage();
  } catch (e) { console.error(e); }
}

async function continueFull() {
  if (crawlState.mode === 'thesaurus_full') {
    crawlState.thesaurusFull.currentPage++;
    await navigateThesaurusPage();
  } else if (crawlState.mode === 'khamenei_full') {
    crawlState.khameneiFull.currentIdx++;
    await navigateKhameneiPage();
  }
}

// ═══ Helpers ═══
async function navigateToUrl(url, site) {
  const tabs = await chrome.tabs.query({ url: `https://${site === 'khamenei' ? 'farsi.khamenei.ir' : 'thesaurus.eiis.iki.ac.ir'}/*` });
  if (tabs.length > 0) {
    crawlState.currentTabId = tabs[0].id;
    chrome.tabs.update(tabs[0].id, { url: url, active: false });
  } else {
    const t = await chrome.tabs.create({ url: url, active: false });
    crawlState.currentTabId = t.id;
  }
}

async function seedThesaurus() {
  try {
    const r = await fetch(`${BACKEND}/api/seed-categories`, { method: 'POST' });
    console.log('Thesaurus seeded:', await r.json());
  } catch (e) { console.error(e); }
}

async function seedKhameneiFromActive() {
  const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
  if (tabs[0] && tabs[0].url?.includes('khamenei')) {
    chrome.tabs.sendMessage(tabs[0].id, { action: 'discoverSpeechIds' });
  }
}

async function reset() {
  await fetch(`${BACKEND}/api/reset-queue`, { method: 'POST' });
  crawlState = { ...crawlState, mode: 'idle', stats: { crawled: 0, skipped: 0, errors: 0 } };
}

async function getStats() {
  try {
    const [r1, r2] = await Promise.all([
      fetch(`${BACKEND}/api/stats`),
      fetch(`${BACKEND}/api/khamenei/stats`),
    ]);
    const stats = await r1.json();
    const khStats = await r2.json();
    return {
      stats,
      khStats,
      mode: crawlState.mode,
      site: crawlState.site,
      local: crawlState.stats
    };
  } catch (e) {
    return { error: e.message };
  }
}

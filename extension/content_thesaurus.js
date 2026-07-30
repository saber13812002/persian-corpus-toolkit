// Thesaurus content script — two-phase crawl via Elastic API (session cookies)
// Phase 1: list pages (100/page) → /api/phase1/seed-batch (dedupe)
 // Phase 2: promote payloads → /api/phase2/complete-batch (full DB save)

const BACKEND = (window.PCT && PCT.BACKEND) || 'http://127.0.0.1:5055';
const ELASTIC = (window.PCT && PCT.ELASTIC_URL) || 'https://thesaurus.eiis.iki.ac.ir/fa/api/elastic/search';
const BASE = (window.PCT && PCT.THESAURUS_BASE) || 'https://thesaurus.eiis.iki.ac.ir';
const PAGE_SIZE = (window.PCT && PCT.PAGE_SIZE) || 100;
const SCIENCE_IDS = (window.PCT && PCT.THESAURUS_SCIENCE_IDS) || [
  '040','050','060','070','080','090','100','110','120','140','150','170','180'
];

let busy = false;

chrome.runtime.onMessage.addListener((msg, _s, sendResponse) => {
  if (msg.action === 'ping') {
    sendResponse({ ok: true, url: location.href });
    return true;
  }
  if (msg.action === 'phase1List' || msg.action === 'harvestElastic') {
    runPhase1(msg).then(sendResponse);
    return true;
  }
  if (msg.action === 'phase2Save' || msg.action === 'promotePending') {
    runPhase2(msg).then(sendResponse);
    return true;
  }
  if (msg.action === 'extractCurrentPage') {
    // Single-page helper: if ScienceId in URL, list that page only
    const sid = detectScienceIdFromUrl();
    if (sid) {
      phase1OnePage({ scienceId: sid, pageNumber: detectPageFromUrl() || 1 }).then(sendResponse);
      return true;
    }
    sendResponse({ ok: false, message: 'ScienceId در URL نیست' });
    return true;
  }
  return false;
});

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

function elasticBody({ pageNumber, pageSize, scienceId }) {
  return {
    PageNumber: pageNumber,
    PageSize: pageSize,
    SortItem: 'Rank',
    SortType: 'ASC',
    SearchPhrase: '',
    MainTypeList: [],
    ScienceList: scienceId ? [String(scienceId)] : [],
    TermCategoryList: [],
    TermTypeList: [],
    CategoryTypeList: [],
    CategorySubjectList: [],
    CategoryKeywordList: [],
    SearchIn: 'Both',
    Lang: 'fa',
    call_num: Date.now(),
  };
}

async function fetchElasticPage({ pageNumber, pageSize = PAGE_SIZE, scienceId }) {
  const r = await fetch(ELASTIC, {
    method: 'POST',
    credentials: 'include',
    headers: {
      accept: 'application/json, text/javascript, */*; q=0.01',
      'content-type': 'application/json; charset=UTF-8',
      'x-requested-with': 'XMLHttpRequest',
    },
    body: JSON.stringify(elasticBody({ pageNumber, pageSize, scienceId })),
  });
  if (!r.ok) throw new Error(`elastic HTTP ${r.status}`);
  return r.json();
}

function unwrapElastic(payload) {
  const outer = payload?.Data || payload || {};
  const inner = outer.Data || outer;
  return {
    list: inner.ResultList || [],
    count: inner.Count ?? payload?.TotalCount ?? 0,
  };
}

function mapListItem(row, scienceId, sourcePage) {
  const id = row.Id || '';
  if (!id) return null;
  let mainType = (row.MainType && row.MainType.Id) || 'term';
  if (mainType === 'grammer') mainType = 'grammar';
  const pathType = ['term', 'keyword', 'index', 'grammar', 'category'].includes(mainType)
    ? mainType
    : 'term';
  return {
    url: `${BASE}/fa/${pathType}/${id}`,
    item_id: id,
    item_type: pathType,
    page_type: pathType,
    title: row.Title || '',
    science_id: (row.ScienceField && row.ScienceField.Id) || scienceId || '',
    source_page: sourcePage,
    // keep full elastic row for phase 2 (definitions etc.)
    payload: row,
  };
}

async function phase1OnePage({ scienceId, pageNumber, pageSize = PAGE_SIZE }) {
  const sourcePage = `${BASE}/fa/list/#!?type=type01&ScienceId=${scienceId}&page=${pageNumber}`;
  const payload = await fetchElasticPage({ pageNumber, pageSize, scienceId });
  const { list, count } = unwrapElastic(payload);
  const items = list.map((row) => mapListItem(row, scienceId, sourcePage)).filter(Boolean);
  const totalPages = Math.max(1, Math.ceil((count || 0) / pageSize));

  const r = await fetch(`${BACKEND}/api/phase1/seed-batch`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      site: 'thesaurus',
      items,
      cursor: {
        key: `thesaurus:list:${scienceId}`,
        scienceId,
        page: pageNumber,
        totalPages,
        count,
      },
    }),
  });
  const result = await r.json();
  console.log(`[Phase1] sci=${scienceId} p=${pageNumber}/${totalPages}`, result);
  return {
    ok: true,
    scienceId,
    pageNumber,
    totalPages,
    count,
    items: items.length,
    ...result,
  };
}

async function runPhase1(opts = {}) {
  if (busy) return { ok: false, message: 'busy' };
  busy = true;
  const sciences = opts.scienceIds || SCIENCE_IDS;
  const delayMs = opts.delayMs || 350;
  const summary = { added: 0, duplicates: 0, pages: 0, sciences: {}, errors: 0 };

  try {
    await chrome.storage.local.set({ crawlStop: false });
    for (const scienceId of sciences) {
      let page = 1;
      let totalPages = 1;
      const sci = { added: 0, duplicates: 0, pages: 0, count: 0 };

      // Resume from progress cursor if present
      try {
        const st = await fetch(`${BACKEND}/api/pipeline/status?site=thesaurus`).then((x) => x.json());
        const cur = (st.cursors || []).find((c) => c.key === `thesaurus:list:${scienceId}`);
        if (cur && cur.value) {
          const v = JSON.parse(cur.value);
          if (v.page && v.totalPages && v.page < v.totalPages) {
            page = Number(v.page) + 1;
          } else if (v.page && v.totalPages && v.page >= v.totalPages) {
            summary.sciences[scienceId] = { ...sci, skipped_complete: true };
            continue;
          }
        }
      } catch (_) {}

      while (page <= totalPages) {
        const stop = await chrome.storage.local.get(['crawlStop']);
        if (stop.crawlStop) {
          summary.stopped = true;
          break;
        }
        try {
          const r = await phase1OnePage({ scienceId, pageNumber: page });
          totalPages = r.totalPages || totalPages;
          sci.count = r.count || sci.count;
          sci.added += r.added || 0;
          sci.duplicates += r.duplicates || 0;
          sci.pages += 1;
          summary.added += r.added || 0;
          summary.duplicates += r.duplicates || 0;
          summary.pages += 1;
          chrome.runtime.sendMessage({
            action: 'phaseProgress',
            phase: 1,
            site: 'thesaurus',
            scienceId,
            page,
            totalPages,
            result: r,
          });
          if (!r.items) break;
          page += 1;
          await sleep(delayMs);
        } catch (e) {
          console.error('[Phase1]', scienceId, page, e);
          summary.errors += 1;
          await sleep(delayMs * 3);
          page += 1;
          if (summary.errors >= 10) break;
        }
      }
      summary.sciences[scienceId] = sci;
      if (summary.stopped) break;
    }
    chrome.runtime.sendMessage({ action: 'phaseDone', phase: 1, site: 'thesaurus', summary });
    return { ok: true, phase: 1, summary };
  } finally {
    busy = false;
  }
}

async function runPhase2(opts = {}) {
  if (busy) return { ok: false, message: 'busy' };
  busy = true;
  const batchSize = opts.batchSize || 50;
  const summary = { inserted: 0, updated: 0, skipped: 0, errors: 0, empty: 0, batches: 0 };

  try {
    await chrome.storage.local.set({ crawlStop: false });
    for (;;) {
      const stop = await chrome.storage.local.get(['crawlStop']);
      if (stop.crawlStop) {
        summary.stopped = true;
        break;
      }
      const next = await fetch(
        `${BACKEND}/api/phase2/next-batch?site=thesaurus&limit=${batchSize}`
      ).then((r) => r.json());
      const items = next.items || [];
      if (!items.length) break;

      const payload = {
        site: 'thesaurus',
        items: items.map((row) => ({
          id: row.id,
          queue_id: row.id,
          url: row.url,
          science_id: row.science_id,
          source_page: row.source_page,
          payload: row.payload,
        })),
      };
      const res = await fetch(`${BACKEND}/api/phase2/complete-batch`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      }).then((r) => r.json());

      summary.inserted += res.inserted || 0;
      summary.updated += res.updated || 0;
      summary.skipped += res.skipped || 0;
      summary.errors += res.errors || 0;
      summary.empty += res.empty || 0;
      summary.batches += 1;

      chrome.runtime.sendMessage({
        action: 'phaseProgress',
        phase: 2,
        site: 'thesaurus',
        batch: summary.batches,
        result: res,
      });
      await sleep(opts.delayMs || 200);
    }
    chrome.runtime.sendMessage({ action: 'phaseDone', phase: 2, site: 'thesaurus', summary });
    return { ok: true, phase: 2, summary };
  } finally {
    busy = false;
  }
}

function detectScienceIdFromUrl() {
  const m = location.href.match(/ScienceId=(\d+)/i);
  return m ? m[1] : null;
}
function detectPageFromUrl() {
  const m = location.href.match(/[?&#]page=(\d+)/i);
  return m ? parseInt(m[1], 10) : 1;
}

console.log('[Thesaurus Phase1/2] Ready on', location.href);

// Content Script v2 - Runs on thesaurus.eiis.iki.ac.ir
// Fixed: proper Persian text extraction, debug logging

const BACKEND = 'http://127.0.0.1:5000';
let lastUrl = '';
let extracting = false;

// ═══ Listen for messages ═══
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.action === 'extractCurrentPage') {
    extractAndSubmit();
    sendResponse({ ok: true });
  }
  return true;
});

// ═══ Watch for URL changes (SPA navigation) ═══
setInterval(() => {
  if (window.location.href !== lastUrl && !extracting) {
    lastUrl = window.location.href;
    setTimeout(() => extractAndSubmit(), 1500);
  }
}, 1000);

// ═══ Main extraction ═══
async function extractAndSubmit() {
  if (extracting) return;
  extracting = true;
  
  try {
    const url = window.location.href;
    const items = [];
    
    // The site uses AngularJS with ng-repeat. Wait for it to render.
    await sleep(500);
    
    // Strategy 1: Look for .data-row elements (Angular templates)
    const rows = document.querySelectorAll('.data-row');
    console.log(`[Crawler] Found ${rows.length} .data-row elements`);
    
    if (rows.length > 0) {
      for (const row of rows) {
        const item = extractFromDataRow(row, url);
        if (item) items.push(item);
      }
    }
    
    // Strategy 2: Look for links in the main content area
    if (items.length === 0) {
      const links = document.querySelectorAll('a.main-title, a[href*="/fa/term/"], a[href*="/fa/keyword/"], a[href*="/fa/index/"], a[href*="/fa/grammar/"]');
      console.log(`[Crawler] Found ${links.length} direct links`);
      
      for (const link of links) {
        const item = extractFromLink(link, url);
        if (item) items.push(item);
      }
    }
    
    // Strategy 3: Try to access Angular scope data
    const ngData = tryExtractAngularData();
    
    // Strategy 4: Look for any ng-repeat generated content
    if (items.length === 0) {
      const ngRows = document.querySelectorAll('[ng-repeat="item in result.itemList"] > *, .search-item, [data-ng-repeat]');
      console.log(`[Crawler] Found ${ngRows.length} ng-repeat elements`);
      
      for (const row of ngRows) {
        // Find the link inside
        const link = row.querySelector('a[href]');
        if (link) {
          const item = extractFromLink(link, url);
          if (item) items.push(item);
        }
      }
    }
    
    // Pagination
    const pagination = extractPagination();
    
    // Submit
    if (items.length > 0) {
      const body = {
        url: url,
        page_type: detectPageType(),
        items: items,
        pagination: pagination,
        angular_data: ngData
      };
      
      console.log(`[Crawler] Submitting ${items.length} items...`, body);
      
      const r = await fetch(`${BACKEND}/api/page-content`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
      });
      const result = await r.json();
      console.log(`[Crawler] ✅ Done: inserted=${result.inserted}, updated=${result.updated}, skipped=${result.skipped}`);
      
      // Notify background to continue full crawl
      chrome.runtime.sendMessage({ action: 'continueFull' });
    } else {
      console.warn('[Crawler] ⚠️ No items found. DOM:', document.body.innerHTML.substring(0, 2000));
    }
  } catch (e) {
    console.error('[Crawler] ❌ Error:', e);
  } finally {
    extracting = false;
  }
}

// ═══ Extract from .data-row ═══
function extractFromDataRow(row, sourceUrl) {
  // Find the main link
  const link = row.querySelector('a.main-title, a[href*="/fa/term/"], a[href*="/fa/keyword/"], a[href*="/fa/index/"]');
  if (!link) return null;
  
  const href = link.getAttribute('href') || '';
  const title = (link.textContent || '').trim();
  
  if (!href || !title) return null;
  
  // Build full URL
  const itemUrl = href.startsWith('http') ? href : `https://thesaurus.eiis.iki.ac.ir${href}`;
  
  // Determine type from the filter labels (.fld spans)
  let itemType = 'term';
  const fldSpans = row.querySelectorAll('.fld');
  for (const span of fldSpans) {
    const t = (span.textContent || '').trim();
    if (t.includes('کلیدواژه') || t.includes('keyword')) itemType = 'keyword';
    else if (t.includes('نمایه') || t.includes('index')) itemType = 'index';
    else if (t.includes('اصطلاح') || t.includes('term')) itemType = 'term';
    else if (t.includes('اصول') || t.includes('grammar') || t.includes('قواعد')) itemType = 'grammar';
  }
  
  // Science field (2nd .fld)
  const scienceField = fldSpans.length > 1 ? (fldSpans[1].textContent || '').trim().replace(/\s*\/\s*/g, '').trim() : '';
  
  // Category (3rd .fld) 
  const category = fldSpans.length > 2 ? (fldSpans[2].textContent || '').trim().replace(/\s*\/\s*/g, '').trim() : '';
  
  // Extract ID from href: /fa/term/ABC123.../title
  const idMatch = href.match(/\/([A-F0-9]{32,})(?:\/|$)/i);
  const itemId = idMatch ? idMatch[1] : '';
  
  // Row number
  const rowNum = (row.querySelector('.rowNum')?.textContent || '').trim();
  
  return {
    url: itemUrl,
    item_id: itemId,
    item_type: itemType,
    title: title,
    science_field: scienceField,
    category: category,
    row_num: rowNum || '',
    source_page: sourceUrl
  };
}

// ═══ Extract from direct link ═══
function extractFromLink(link, sourceUrl) {
  const href = link.getAttribute('href') || '';
  const title = (link.textContent || '').trim();
  
  if (!href || !title) return null;
  
  const itemUrl = href.startsWith('http') ? href : `https://thesaurus.eiis.iki.ac.ir${href}`;
  
  // Determine type from URL
  let itemType = 'term';
  if (href.includes('/fa/keyword/')) itemType = 'keyword';
  else if (href.includes('/fa/index/')) itemType = 'index';
  else if (href.includes('/fa/grammar/')) itemType = 'grammar';
  else if (href.includes('/fa/category/')) itemType = 'category';
  
  // Extract ID
  const idMatch = href.match(/\/([A-F0-9]{32,})(?:\/|$)/i);
  const itemId = idMatch ? idMatch[1] : '';
  
  return {
    url: itemUrl,
    item_id: itemId,
    item_type: itemType,
    title: title,
    science_field: '',
    category: '',
    row_num: '',
    source_page: sourceUrl
  };
}

// ═══ Try to access AngularJS data ═══
function tryExtractAngularData() {
  try {
    // Access AngularJS scope via angular.element
    const el = document.querySelector('[ng-controller="ngSearchController"]');
    if (el && window.angular) {
      const scope = window.angular.element(el).scope();
      if (scope && scope.result) {
        return {
          totalCount: scope.result.count || 0,
          itemCount: (scope.result.itemList || []).length,
          facetCounts: {
            cnt: (scope.result.cntList || []).length,
            sci: (scope.result.sciList || []).length,
            typ: (scope.result.typList || []).length
          }
        };
      }
    }
  } catch (e) {
    console.log('[Crawler] Angular access failed:', e.message);
  }
  
  // Check if Angular is available as a global
  if (typeof window.angular === 'undefined') {
    console.log('[Crawler] AngularJS not exposed globally');
  }
  
  return { angularAvailable: typeof window.angular !== 'undefined' };
}

// ═══ Pagination ═══
function extractPagination() {
  const result = { current: 1, total: 1, totalResults: 0 };
  
  // Try to get total count from the banner text
  const body = document.body.textContent || '';
  const match = body.match(/(\d[\d,]+)\s*مورد/);
  if (match) {
    result.totalResults = parseInt(match[1].replace(/,/g, ''), 10);
  }
  
  // Active page
  const active = document.querySelector('.page-item.active, .pagination .active, .page-link.active');
  if (active) {
    const n = parseInt((active.textContent || '').trim(), 10);
    if (!isNaN(n)) result.current = n;
  }
  
  // Total pages from pagination links
  const pageLinks = document.querySelectorAll('.page-item:not(.active) .page-link, .pagination a');
  pageLinks.forEach(link => {
    const n = parseInt((link.textContent || '').trim(), 10);
    if (!isNaN(n) && n > result.total) result.total = n;
  });
  
  // Estimate total pages
  if (result.totalResults > 0 && result.total === 1) {
    result.total = Math.ceil(result.totalResults / 100);
  }
  
  return result;
}

// ═══ Page type detection ═══
function detectPageType() {
  const u = window.location.href;
  if (u.includes('/fa/term/')) return 'term';
  if (u.includes('/fa/keyword/')) return 'keyword';
  if (u.includes('/fa/index/')) return 'index';
  if (u.includes('/fa/grammar/')) return 'grammar';
  if (u.includes('/fa/category/')) return 'category';
  if (u.includes('/fa/list')) return 'list';
  return 'unknown';
}

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

console.log('[Crawler v2] Ready on', window.location.href);

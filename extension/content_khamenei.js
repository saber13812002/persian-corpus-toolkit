// Content Script for farsi.khamenei.ir
// Extracts speech content from detail pages and discovers IDs from list pages

const BACKEND = 'http://127.0.0.1:5000';
let lastUrl = '';
let extracting = false;

// ═══ Listen for messages ═══
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.action === 'extractCurrentPage') {
    extractAndSubmit();
    sendResponse({ ok: true });
  }
  if (msg.action === 'discoverSpeechIds') {
    discoverIds();
    sendResponse({ ok: true });
  }
  return true;
});

// ═══ Watch for URL changes ═══
setInterval(() => {
  if (window.location.href !== lastUrl && !extracting) {
    lastUrl = window.location.href;
    setTimeout(() => extractAndSubmit(), 1000);
  }
}, 1500);

// ═══ Discover speech IDs from list page ═══
async function discoverIds() {
  console.log('[Khamenei] Discovering speech IDs...');
  const links = document.querySelectorAll('a[href*="speech-content?id="]');
  const ids = [];
  links.forEach(link => {
    const href = link.getAttribute('href') || '';
    const match = href.match(/speech-content\?id=(\d+)/);
    if (match) ids.push(match[1]);
  });

  if (ids.length > 0) {
    console.log(`[Khamenei] Found ${ids.length} IDs: ${ids.slice(0,5).join(',')}...`);
    try {
      const r = await fetch(`${BACKEND}/api/khamenei/seed`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ids: ids })
      });
      const result = await r.json();
      console.log(`[Khamenei] Seeded ${result.seeded} new IDs`);
    } catch (e) {
      console.error('[Khamenei] Seed error:', e);
    }
  }
}

// ═══ Extract speech content ═══
async function extractAndSubmit() {
  if (extracting) return;
  extracting = true;

  try {
    const url = window.location.href;

    // Detect page type
    if (url.includes('speech-content')) {
      // Detail page - extract full speech
      const speech = extractSpeechDetail();
      if (speech) {
        console.log(`[Khamenei] Extracted speech #${speech.speech_id}: ${speech.title} (${speech.char_count} chars)`);
        const r = await fetch(`${BACKEND}/api/khamenei/submit`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(speech)
        });
        const result = await r.json();
        console.log(`[Khamenei] ✅ ${result.status}: ${speech.title}`);
      }
    } else if (url.match(/\/speech(\?|$)/)) {
      // List page - discover IDs
      await discoverIds();
      
      // Also try to find pagination "more" button or next page link
      chrome.runtime.sendMessage({ action: 'khameneiListScanned' });
    }
  } catch (e) {
    console.error('[Khamenei] Error:', e);
  } finally {
    extracting = false;
  }
}

// ═══ Extract from speech-content detail page ═══
function extractSpeechDetail() {
  // Speech ID from URL
  const idMatch = window.location.href.match(/[?&]id=(\d+)/);
  if (!idMatch) return null;
  const speechId = idMatch[1];

  // Title - from <title> tag or h1
  let title = '';
  const titleTag = document.querySelector('title');
  if (titleTag) {
    title = titleTag.textContent.trim();
    // Remove site name suffix
    title = title.replace(/\s*[-–|]\s*KHAMENEI\.IR.*$/i, '').trim();
    title = title.replace(/\s*[-–|]\s*پایگاه.*$/i, '').trim();
    title = title.replace(/\s*[-–|]\s*farsi\.khamenei\.ir.*$/i, '').trim();
  }
  if (!title) {
    const h1 = document.querySelector('h1, .title, .speech-title');
    if (h1) title = h1.textContent.trim();
  }

  // Date - from .Content div or meta
  let date = '';
  const contentDiv = document.querySelector('.Content, #newsContentInnerSide, [class*="Content"]');
  if (contentDiv) {
    const text = contentDiv.textContent || '';
    const dateMatch = text.match(/(\d{4}\/\d{2}\/\d{2})/);
    if (dateMatch) date = dateMatch[1];
  }

  // Main content text
  let content = '';
  // Strategy 1: div.Content
  const divContent = document.querySelector('div.Content');
  if (divContent) {
    content = divContent.textContent.trim();
  }
  // Strategy 2: newsContentInnerSide
  if (!content) {
    const newsDiv = document.getElementById('newsContentInnerSide');
    if (newsDiv) content = newsDiv.textContent.trim();
  }
  // Strategy 3: any visible text in the main area
  if (!content) {
    const mainArea = document.querySelector('#newsContentInnerSide, .Content, [id*="Content"], [class*="speech-body"]');
    if (mainArea) content = mainArea.textContent.trim();
  }

  // Clean content - remove date prefix if it appears at the start
  if (date && content.startsWith(date)) {
    content = content.substring(date.length).trim();
  }

  // Audio URL
  let audioUrl = '';
  const audioLink = document.querySelector('a[href*="audio-content"]');
  if (audioLink) {
    const href = audioLink.getAttribute('href') || '';
    audioUrl = href.startsWith('http') ? href : `https://farsi.khamenei.ir${href}`;
  }

  // Tags
  const tags = [];
  document.querySelectorAll('.topmenu-tag, a[title]').forEach(el => {
    const t = el.getAttribute('title');
    if (t && t !== 'کلیدواژه' && t.length > 2) tags.push(t);
  });

  return {
    speech_id: speechId,
    title: title,
    date: date,
    content: content,
    audio_url: audioUrl,
    tags: tags,
    char_count: content.length,
  };
}

console.log('[Khamenei Content] Ready on', window.location.href);

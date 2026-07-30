// Popup — two-phase crawler UI
let currentSite = 'thesaurus';
let refreshInterval = null;

document.addEventListener('DOMContentLoaded', async () => {
  bindEvents();
  await detectActiveSite();
  updateHint();
  refreshStats();
  refreshInterval = setInterval(refreshStats, 3000);
});

document.addEventListener('visibilitychange', () => {
  if (document.hidden) clearInterval(refreshInterval);
  else {
    refreshStats();
    refreshInterval = setInterval(refreshStats, 3000);
  }
});

function bindEvents() {
  document.getElementById('siteThesaurus').addEventListener('click', () => selectSite('thesaurus'));
  document.getElementById('siteKhamenei').addEventListener('click', () => selectSite('khamenei'));
  document.getElementById('btnPhase1').addEventListener('click', runPhase1);
  document.getElementById('btnPhase2').addEventListener('click', runPhase2);
  document.getElementById('btnFull').addEventListener('click', runBoth);
  document.getElementById('btnSingle').addEventListener('click', startSingle);
  document.getElementById('btnStop').addEventListener('click', stop);
  document.getElementById('btnReset').addEventListener('click', reset);
  document.getElementById('btnDashboard').addEventListener('click', () => {
    chrome.tabs.create({ url: 'http://127.0.0.1:5055/dashboard' });
  });
}

async function detectActiveSite() {
  try {
    const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
    const url = tabs[0]?.url || '';
    if (/khamenei\.ir/i.test(url)) selectSite('khamenei');
    else if (/thesaurus\.eiis\.iki\.ac\.ir/i.test(url)) selectSite('thesaurus');
  } catch (_) {}
}

function selectSite(site) {
  currentSite = site;
  document.getElementById('siteThesaurus').classList.toggle('active', site === 'thesaurus');
  document.getElementById('siteKhamenei').classList.toggle('active', site === 'khamenei');
  document.getElementById('siteTag').textContent = site === 'khamenei' ? '🎤 khamenei.ir' : '📖 thesaurus';
  updateHint();
  refreshStats();
}

function updateHint() {
  const hint = document.getElementById('hintBox');
  if (currentSite === 'khamenei') {
    hint.textContent =
      'بیانات: فاز۱ کشف ID از لیست /speech — فاز۲ باز کردن هر speech-content و ذخیره div.Content. دامنه: farsi.khamenei.ir';
  } else {
    hint.textContent =
      'اصطلاح‌نامه: فاز۱ Elastic صدتا‌صدتا در ۱۳ علم — فاز۲ ذخیره کامل تعاریف در DB. تب سایت باز باشد تا سشن استفاده شود.';
  }
}

function setRunning(on, label) {
  document.getElementById('btnPhase1').disabled = on;
  document.getElementById('btnPhase2').disabled = on;
  document.getElementById('btnFull').disabled = on;
  document.getElementById('btnStop').disabled = !on;
  document.getElementById('statusDot').className = 'dot ' + (on ? 'running' : 'idle');
  document.getElementById('statusText').textContent = on ? (label || 'در حال اجرا') : 'آماده';
}

function runPhase1() {
  setRunning(true, 'فاز ۱');
  log(currentSite === 'khamenei' ? '🌱 فاز۱: کشف لیست بیانات...' : '🌱 فاز۱: لیست Elastic (۱۳ علم، ۱۰۰تایی)...', 'info');
  chrome.runtime.sendMessage({ action: 'runPhase1', site: currentSite }, (resp) => {
    if (chrome.runtime.lastError) {
      log('❌ ' + chrome.runtime.lastError.message, 'err');
      setRunning(false);
      return;
    }
    if (resp?.message) log(resp.message, resp.ok === false ? 'err' : 'ok');
    // keep running until phaseDone; poll handles UI
    refreshStats();
  });
}

function runPhase2() {
  setRunning(true, 'فاز ۲');
  log(currentSite === 'khamenei' ? '💾 فاز۲: ذخیره متن بیانات...' : '💾 فاز۲: ذخیره کامل اصطلاحات...', 'info');
  chrome.runtime.sendMessage({ action: 'runPhase2', site: currentSite }, (resp) => {
    if (chrome.runtime.lastError) {
      log('❌ ' + chrome.runtime.lastError.message, 'err');
      setRunning(false);
      return;
    }
    if (resp?.message) log(resp.message, resp.ok === false ? 'err' : 'ok');
    refreshStats();
  });
}

function runBoth() {
  setRunning(true, 'فاز ۱+۲');
  log('🚀 اجرای هر دو فاز پشت‌سرهم...', 'info');
  chrome.runtime.sendMessage({ action: 'runBothPhases', site: currentSite }, (resp) => {
    if (chrome.runtime.lastError) {
      log('❌ ' + chrome.runtime.lastError.message, 'err');
      setRunning(false);
      return;
    }
    if (resp?.message) log(resp.message, resp.ok === false ? 'err' : 'info');
  });
}

function startSingle() {
  log('📄 کراول صفحه فعلی...', 'info');
  chrome.runtime.sendMessage({ action: 'startSingle' }, (resp) => {
    if (resp?.ok === false) log('❌ ' + (resp.message || 'خطا'), 'err');
    else log('✅ ارسال شد', 'ok');
  });
}

function stop() {
  chrome.runtime.sendMessage({ action: 'stop' }, () => {
    setRunning(false);
    log('⏹ توقف درخواست شد', 'warn');
  });
}

function reset() {
  chrome.runtime.sendMessage({ action: 'reset' }, () => {
    log('🔄 صف ریست شد', 'info');
    refreshStats();
  });
}

function refreshStats() {
  chrome.runtime.sendMessage({ action: 'getStats', site: currentSite }, (resp) => {
    if (!resp || resp.error) return;
    const pipe = resp.pipeline || {};
    const p1 = pipe.phase1 || {};
    const p2 = pipe.phase2 || {};
    document.getElementById('statListed').textContent = (p1.listed_unique || 0).toLocaleString('fa-IR');
    document.getElementById('statPending').textContent = (p1.pending_detail || 0).toLocaleString('fa-IR');
    const saved =
      currentSite === 'khamenei' ? p2.khamenei_saved || 0 : p2.thesaurus_saved || 0;
    document.getElementById('statSaved').textContent = Number(saved).toLocaleString('fa-IR');
    const last =
      currentSite === 'khamenei' ? p2.khamenei_last_crawled_at || '-' : '-';
    document.getElementById('statLast').textContent = last
      ? String(last).replace('T', ' ').slice(0, 19)
      : '-';

    if (resp.mode && resp.mode !== 'idle') {
      setRunning(true, resp.mode);
    } else if (!document.getElementById('btnStop').disabled && resp.mode === 'idle') {
      setRunning(false);
    }
  });
}

function log(msg, level = 'info') {
  const box = document.getElementById('logBox');
  const entry = document.createElement('div');
  entry.className = 'entry ' + level;
  const time = new Date().toLocaleTimeString('fa-IR', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  entry.textContent = `[${time}] ${msg}`;
  box.prepend(entry);
  while (box.children.length > 40) box.removeChild(box.lastChild);
}

chrome.runtime.onMessage.addListener((msg) => {
  if (msg.action === 'phaseProgress') {
    if (msg.phase === 1) {
      log(`فاز۱ ${msg.scienceId || ''} ص${msg.page}/${msg.totalPages} +${msg.result?.added || 0}`, 'info');
    } else {
      log(`فاز۲ دسته ${msg.batch}: +${msg.result?.inserted || 0} / skip ${msg.result?.skipped || 0}`, 'info');
    }
    refreshStats();
  }
  if (msg.action === 'phaseDone') {
    log(`✅ فاز ${msg.phase} تمام شد`, 'ok');
    setRunning(false);
    refreshStats();
  }
});

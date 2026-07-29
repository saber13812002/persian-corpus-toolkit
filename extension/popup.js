// Popup Logic v2 - Multi-site support
let currentSite = 'thesaurus';
let refreshInterval = null;

document.addEventListener('DOMContentLoaded', () => {
  refreshStats();
  refreshInterval = setInterval(refreshStats, 3000);
});

document.addEventListener('visibilitychange', () => {
  if (document.hidden) clearInterval(refreshInterval);
  else { refreshStats(); refreshInterval = setInterval(refreshStats, 3000); }
});

function selectSite(site) {
  currentSite = site;
  document.getElementById('siteThesaurus').classList.toggle('active', site === 'thesaurus');
  document.getElementById('siteKhamenei').classList.toggle('active', site === 'khamenei');
  document.getElementById('siteTag').textContent = site === 'khamenei' ? '🎤 khamenei.ir' : '📖 thesaurus';
  updateButtons();
}

function updateButtons() {
  const fullBtn = document.getElementById('btnFull');
  const seedBtn = document.getElementById('btnSeed');
  if (currentSite === 'khamenei') {
    fullBtn.textContent = '🚀 کراول بیانات';
    seedBtn.textContent = '🌱 کشف بیانات';
  } else {
    fullBtn.textContent = '🚀 کراول کامل';
    seedBtn.textContent = '🌱 Seed Categories';
  }
}

function seed() {
  log('🌱 Seeding...', 'info');
  if (currentSite === 'khamenei') {
    chrome.runtime.sendMessage({ action: 'seedKhamenei' }, () => {
      log('✅ لینک‌های صفحه به صف اضافه شد', 'ok');
      refreshStats();
    });
  } else {
    chrome.runtime.sendMessage({ action: 'seedThesaurus' }, () => {
      log('✅ دسته‌بندی‌های علمی به صف اضافه شد', 'ok');
      refreshStats();
    });
  }
}

function reset() {
  chrome.runtime.sendMessage({ action: 'reset' }, () => {
    log('🔄 صف ریست شد', 'info');
    refreshStats();
  });
}

function startSingle() {
  log('📄 کراول صفحه فعلی...', 'info');
  chrome.runtime.sendMessage({ action: 'startSingle' });
}

function startFull() {
  const action = currentSite === 'khamenei' ? 'startKhameneiFull' : 'startThesaurusFull';
  const label = currentSite === 'khamenei' ? '🎤 کراول بیانات شروع شد' : '📖 کراول کامل اصطلاح‌نامه شروع شد';
  log(label, 'info');
  document.getElementById('btnFull').disabled = true;
  document.getElementById('btnStop').disabled = false;
  updateStatus('running');
  chrome.runtime.sendMessage({ action: action });
}

function stop() {
  log('⏹ توقف...', 'info');
  chrome.runtime.sendMessage({ action: 'stop' }, () => {
    document.getElementById('btnFull').disabled = false;
    document.getElementById('btnStop').disabled = true;
    updateStatus('idle');
  });
}

function openDashboard() {
  chrome.tabs.create({ url: 'http://127.0.0.1:5000/dashboard' });
}

async function refreshStats() {
  chrome.runtime.sendMessage({ action: 'getStats' }, (resp) => {
    if (!resp || resp.error) return;

    const stats = resp.stats || {};
    const khStats = resp.khStats || {};
    
    document.getElementById('statThesaurus').textContent = (stats.by_type?.term || 0).toLocaleString('fa-IR');
    document.getElementById('statKhamenei').textContent = (khStats.total || 0).toLocaleString('fa-IR');
    document.getElementById('statQueue').textContent = (stats.queue_pending || 0).toLocaleString('fa-IR');

    if (resp.mode && resp.mode !== 'idle') {
      document.getElementById('btnFull').disabled = true;
      document.getElementById('btnStop').disabled = false;
      updateStatus('running');
      document.getElementById('statusText').textContent = 
        resp.site === 'khamenei' ? '🎤 کراول بیانات' : '📖 کراول اصطلاح‌نامه';
    }
  });
}

function updateStatus(state) {
  document.getElementById('statusDot').className = 'dot ' + state;
}

function log(msg, level = 'info') {
  const box = document.getElementById('logBox');
  const entry = document.createElement('div');
  entry.className = 'entry ' + level;
  const time = new Date().toLocaleTimeString('fa-IR', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  entry.textContent = `[${time}] ${msg}`;
  box.prepend(entry);
  while (box.children.length > 50) box.removeChild(box.lastChild);
}

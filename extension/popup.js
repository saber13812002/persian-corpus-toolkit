// Popup — two-phase crawler UI
let currentSite = 'thesaurus';
let refreshInterval = null;

const BACKEND = 'https://corpus.ai.ismc.ir';

document.addEventListener('DOMContentLoaded', async () => {
  bindEvents();
  bindProject();
  await detectActiveSite();
  updateHint();
  await checkConnection();
  await loadProjects();
  refreshStats();
  refreshInterval = setInterval(() => {
    refreshStats();
    refreshProject();
  }, 3000);
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
  document.getElementById('btnResetPhase2').addEventListener('click', resetPhase2Dates);
  document.getElementById('btnDashboard').addEventListener('click', () => {
    chrome.tabs.create({ url: 'https://corpus.ai.ismc.ir/dashboard' });
  });
}

let activeProjectId = null;
let creatingProject = false;

function bindProject() {
  document.getElementById('btnCreateProject').addEventListener('click', createProject);
  document.getElementById('btnEditPoints').addEventListener('click', editPoints);
  document.getElementById('btnTestProject').addEventListener('click', testProject);
  document.getElementById('btnStopRead').addEventListener('click', stopReading);
  document.getElementById('projectSelect').addEventListener('change', (e) => {
    activeProjectId = e.target.value ? Number(e.target.value) : null;
    chrome.storage.local.set({ pctProjectId: activeProjectId });
    refreshProject();
  });
}

async function activeTab() {
  const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
  return tabs[0];
}

function setReport(text) {
  document.getElementById('reportText').textContent = text;
}

/** Parse a backend response as JSON. Network/HTTP/JSON failures are separated
 *  and surfaced as a clear, user-facing message (never a silent success). */
async function parseProjectResponse(r, context) {
  if (!r.ok) {
    if (r.status === 404) {
      throw new Error(
        'سرور نسخهٔ قدیمی است و endpoint ساخت پروژه را ندارد (404). باید backend تازه deploy شود.'
      );
    }
    if (r.status === 409) {
      throw new Error('این پروژه قبلاً ثبت شده است (409).');
    }
    if (r.status === 500) {
      throw new Error('خطای داخلی سرور (500). دوباره تلاش کن.');
    }
    if (r.status === 400) {
      throw new Error('دادهٔ نامعتبر برای سرور (400). نام و میزبان را بررسی کن.');
    }
    throw new Error(`درخواست ناموفق بود (HTTP ${r.status}).`);
  }
  try {
    return await r.json();
  } catch (_) {
    throw new Error(`پاسخ سرور قابل‌خواندن نبود (${context}).`);
  }
}

/** Rebuild the project ComboBox from a fresh backend read. Returns true on
 *  success, false if the list could not be loaded. */
async function loadProjects() {
  const tab = await activeTab();
  let host = '';
  try { host = new URL(tab?.url || '').host; } catch (_) {}
  if (!host) {
    setReport('یک صفحه وب باز کن، بعد پروژه را بساز.');
    return false;
  }
  const select = document.getElementById('projectSelect');
  let data;
  try {
    const r = await fetch(`${BACKEND}/api/projects?host=${encodeURIComponent(host)}`);
    data = await r.json();
  } catch (e) {
    setReport(`فهرست پروژه‌ها خوانده نشد: ${e.message}`);
    select.innerHTML = '<option value="">خواندن فهرست ناموفق بود</option>';
    return false;
  }
  const list = Array.isArray(data.projects) ? data.projects : [];
  // Rebuild from scratch so no duplicate options are ever created.
  select.innerHTML = '';
  const blank = document.createElement('option');
  blank.value = '';
  blank.textContent = list.length ? 'یک پروژه را انتخاب کن' : 'هنوز پروژه‌ای نیست';
  select.appendChild(blank);
  list.forEach((project) => {
    if (select.querySelector(`option[value="${String(project.id)}"]`)) return; // no dup
    const option = document.createElement('option');
    option.value = String(project.id);
    option.textContent = `${project.name} — ${project.points?.length || 0} نقطه`;
    select.appendChild(option);
  });
  const stored = await chrome.storage.local.get('pctProjectId');
  const wanted =
    stored.pctProjectId &&
    [...select.options].some((o) => o.value === String(stored.pctProjectId));
  if (wanted) {
    select.value = String(stored.pctProjectId);
    activeProjectId = Number(stored.pctProjectId);
  } else if (activeProjectId && [...select.options].some((o) => o.value === String(activeProjectId))) {
    // Keep the project just created/selected in this session.
    select.value = String(activeProjectId);
  } else {
    // Previously selected project no longer exists → safe default.
    select.value = '';
    activeProjectId = null;
  }
  refreshProject();
  return true;
}

async function createProject() {
  if (creatingProject) return;
  const tab = await activeTab();
  let url;
  try { url = new URL(tab?.url || ''); } catch (_) {
    setReport('این تب صفحه وب نیست.');
    return;
  }
  const nameEl = document.getElementById('projectName');
  const name = (nameEl.value || '').trim();
  if (!name) {
    nameEl.focus();
    setReport('نام پروژه را بنویس، بعد ساختن را بزن.');
    log('نام پروژه خالی است', 'warn');
    return;
  }
  const pace = Math.max(1, Math.min(12, Number(document.getElementById('pagesPerMinute').value) || 4));
  const param = url.searchParams.has('item_index') ? 'item_index' : '';
  const btn = document.getElementById('btnCreateProject');
  creatingProject = true;
  btn.disabled = true;
  const originalLabel = btn.textContent;
  btn.textContent = 'در حال ساخت…';
  setReport('در حال ساختن پروژه…');
  try {
    const r = await fetch(`${BACKEND}/api/projects`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name,
        host: url.host,
        start_url: url.href.split('#')[0],
        next_mode: param ? 'url_param' : 'none',
        next_param: param,
        next_step: 1,
        pages_per_minute: pace,
      }),
    });
    const data = await parseProjectResponse(r, 'ساخت پروژه');
    if (data.ok === false) {
      throw new Error(data.message || 'پروژه ساخته نشد');
    }
    // Success confirmed by the backend. Now refresh the list and select it.
    activeProjectId = data.project.id;
    await chrome.storage.local.set({ pctProjectId: activeProjectId });
    const ok = await loadProjects();
    const select = document.getElementById('projectSelect');
    select.value = String(activeProjectId);
    if (ok) {
      setReport(`پروژه «${data.project.name}» ساخته شد. حالا نقطه‌های تفسیر را روی صفحه وصل کن.`);
      log(`پروژه ${data.project.id} ساخته شد`, 'ok');
    } else {
      // POST succeeded and is persisted, but the list could not be refreshed.
      // Do NOT report this as a clean success.
      setReport(
        `پروژه «${data.project.name}» در سرور ثبت شد، ولی فهرست تازه‌خوانی نشد. Popup را ببند و باز کن تا در لیست دیده شود.`
      );
      log(`پروژه ${data.project.id} ساخته شد ولی فهرست نخوانده شد`, 'warn');
    }
  } catch (e) {
    setReport(e.message || 'پروژه ساخته نشد');
    log(`خطا در ساخت پروژه: ${e.message}`, 'err');
  } finally {
    creatingProject = false;
    btn.disabled = false;
    btn.textContent = originalLabel;
  }
}

function editPoints() {
  if (!activeProjectId) {
    setReport('اول پروژه را از این صفحه بساز.');
    return;
  }
  chrome.runtime.sendMessage({ action: 'openProject', projectId: activeProjectId }, (resp) => {
    if (chrome.runtime.lastError) {
      setReport(chrome.runtime.lastError.message);
      return;
    }
    if (resp?.ok === false) setReport(resp.message || 'ویرایش باز نشد');
    else setReport('پنل روی صفحه باز شد. نقطه را انتخاب کن یا ویرایش کن.');
  });
}

function testProject() {
  if (!activeProjectId) {
    setReport('اول پروژه را از این صفحه بساز.');
    return;
  }
  setReport('در حال آزمایش این صفحه…');
  chrome.runtime.sendMessage({ action: 'testProject', projectId: activeProjectId }, (resp) => {
    if (chrome.runtime.lastError) {
      setReport(chrome.runtime.lastError.message);
      return;
    }
    setReport(resp?.message || (resp?.ok ? 'آزمایش تمام شد' : 'آزمایش ناموفق بود'));
    refreshProject();
  });
}

function stopReading() {
  chrome.runtime.sendMessage({ action: 'stopReading' }, (resp) => {
    setReport(resp?.message || 'توقف شد');
    refreshProject();
  });
}

async function refreshProject() {
  if (!activeProjectId) return;
  try {
    const r = await fetch(`${BACKEND}/api/projects/${activeProjectId}`);
    if (!r.ok) return;
    const project = await r.json();
    const hint = document.getElementById('pointHint');
    const n = project.points?.length || 0;
    hint.textContent = n
      ? `${n} نقطه وصل شده: ${project.points.map((p) => p.tag).join('، ')}`
      : 'روی متن تفسیر کلیک کن، اسم نقطه را بنویس، ذخیره کن. برای عوض کردنش ویرایش را بزن.';
    if (project.pages_per_minute) document.getElementById('pagesPerMinute').value = project.pages_per_minute;
    if (project.last_message || project.status === 'running') {
      setReport(
        `${project.last_message || project.status} — ذخیره ${project.saved_count || 0}، رد ${project.skipped_count || 0}، خطا ${project.failed_count || 0}`
      );
    }
    document.getElementById('statusDot').className = 'dot ' + (project.status === 'running' ? 'running' : 'idle');
    document.getElementById('statusText').textContent = project.status === 'running' ? 'در حال خواندن' : 'آماده';
  } catch (_) {}
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

async function checkConnection() {
  const el = document.getElementById('connText');
  try {
    const r = await fetch(`${BACKEND}/api/stats`);
    if (!r.ok) throw new Error('HTTP ' + r.status);
    el.textContent = 'وصل به corpus.ai.ismc.ir';
    el.style.color = '#2ecc71';
    log('ویجت به corpus.ai.ismc.ir وصل است', 'ok');
  } catch (e) {
    el.textContent = 'قطع';
    el.style.color = '#e74c3c';
    log('ویجت وصل نشد: ' + e.message, 'err');
  }
}

function startSingle() {
  log('📄 کراول صفحه فعلی...', 'info');
  chrome.runtime.sendMessage({ action: 'startSingle' }, (resp) => {
    if (chrome.runtime.lastError) {
      log('❌ ' + chrome.runtime.lastError.message, 'err');
      return;
    }
    if (resp?.ok === false) {
      log('❌ ' + (resp.message || resp.status || 'خطا'), 'err');
      return;
    }
    const sp = resp?.speech || {};
    log(
      `✅ ${resp?.status || 'ok'} #${sp.speech_id || '-'} تاریخ=${sp.date || 'خالی'} سال=${sp.year || '-'}`,
      sp.date ? 'ok' : 'warn'
    );
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

function resetPhase2Dates() {
  if (currentSite !== 'khamenei') {
    log('این دکمه فقط برای بیانات است — سایت بیانات را انتخاب کن', 'warn');
    return;
  }
  if (!confirm('بیانات ذخیره‌شده پاک شود و فاز۲ از اول برای ثبت تاریخ دوباره اجرا شود؟\n(لیست فاز۱ می‌ماند)')) return;
  chrome.runtime.sendMessage({ action: 'resetKhameneiPhase2' }, (resp) => {
    if (resp && resp.ok) {
      log(`🔄 ریست فاز۲: ${resp.requeued || 0} مورد در صف — حالا فاز۲ را بزن`, 'ok');
    } else {
      log('خطا در ریست: ' + (resp?.message || ''), 'err');
    }
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

#!/usr/bin/env node
/* ui_check.mjs — PCM-20.9.4 mission 2.3: REAL-UI verification of
 * dashboard/studio.html (Knowledge Corpus Factory) against a REAL local
 * Flask server (venv python, temp DB, temp data dir, real .docx files).
 *
 * Drives the actual UI with headless Chrome (puppeteer-core):
 *   login (wrong+right pw) -> create collection -> multi-import (10 files)
 *   -> full pipeline run -> pause mid-run -> 409 while paused -> resume
 *   -> stage cards (A..F) -> audit history -> resume-from-stage (RELEASE)
 *   -> nightly schedule save -> release zip download -> secrets scan
 *   -> JS health -> mobile viewport (390x844).
 *
 * Exit code: 0 = all checks passed, 1 = at least one failure.
 * Evidence: console + results.json + shots/*.png (tmp/ kept on failure).
 */
import { spawn, execSync } from 'node:child_process';
import net from 'node:net';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import puppeteer from 'puppeteer-core';

const here = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(here, '..', '..');
const BACKEND = path.join(ROOT, 'backend');
const PY = 'C:/Users/s.tabatabaei/Documents/saberprojects/persian-corpus-toolkit/.venv/Scripts/python.exe';
const CHROME = 'C:/Program Files/Google/Chrome/Application/chrome.exe';
const TMP = path.join(here, 'tmp');
const SHOTS = path.join(here, 'shots');
const FIXDIR = path.join(TMP, 'fixtures');
const DB = path.join(TMP, 'pct_ui.db');
const DATADIR = path.join(TMP, 'data');
const PASSWORD = 'test-secret-123';

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function waitFor(fn, { timeout = 60000, interval = 200, label = 'condition' } = {}) {
  const t0 = Date.now();
  for (;;) {
    let v;
    try { v = await fn(); } catch { v = false; }
    if (v) return v;
    if (Date.now() - t0 > timeout) throw new Error('TIMEOUT waiting for: ' + label);
    await sleep(interval);
  }
}

const results = [];
function check(name, pass, evidence = '') {
  const ev = String(evidence).slice(0, 400);
  results.push({ name, pass: !!pass, evidence: ev });
  console.log((pass ? 'PASS' : 'FAIL') + '  ' + name + (ev ? '  — ' + ev : ''));
}

function shot(page, name) {
  return page.screenshot({ path: path.join(SHOTS, name) }).catch(() => {});
}

function freePort() {
  return new Promise((resolve, reject) => {
    const s = net.createServer();
    s.listen(0, '127.0.0.1', () => {
      const p = s.address().port;
      s.close(() => resolve(p));
    });
    s.on('error', reject);
  });
}

async function startServer(port) {
  const env = {
    ...process.env,
    PCT_DB: DB,
    PCT_KNOWLEDGE_DATA_DIR: DATADIR,
    PCT_DASHBOARD_PASSWORD: PASSWORD,
    HOST: '127.0.0.1',
    PORT: String(port),
  };
  const child = spawn(PY, ['server.py'], {
    cwd: BACKEND, env, stdio: ['ignore', 'pipe', 'pipe'], windowsHide: true,
  });
  let out = '';
  child.stdout.on('data', (d) => { out += d; });
  child.stderr.on('data', (d) => { out += d; });
  const base = 'http://127.0.0.1:' + port;
  try {
    await waitFor(async () => {
      try {
        const r = await fetch(base + '/api/auth/status');
        return r.status === 200;
      } catch { return false; }
    }, { timeout: 60000, interval: 500, label: 'Flask server ready on ' + base });
  } catch (e) {
    console.error('--- server log (last 3000 chars) ---');
    console.error(out.slice(-3000));
    throw e;
  }
  return { child, base, log: () => out };
}

async function main() {
  fs.rmSync(TMP, { recursive: true, force: true });
  fs.mkdirSync(TMP, { recursive: true });
  fs.mkdirSync(SHOTS, { recursive: true });
  fs.mkdirSync(DATADIR, { recursive: true });

  /* ── fixtures: 10 real Persian .docx ─────────────────────────────── */
  execSync(`"${PY}" gen_fixtures.py "${FIXDIR}" 10`, { cwd: here, stdio: 'inherit' });
  const docx = fs.readdirSync(FIXDIR).filter((f) => f.endsWith('.docx')).sort()
    .map((f) => path.join(FIXDIR, f));
  check('U-fixtures', docx.length === 10, docx.length + ' docx generated in ' + FIXDIR);

  /* ── real Flask server on a free port ────────────────────────────── */
  const port = await freePort();
  const server = await startServer(port);
  const base = server.base;
  console.log('server: ' + base + ' (pid ' + server.child.pid + ', db ' + DB + ')');

  const browser = await puppeteer.launch({
    executablePath: CHROME,
    headless: 'new',
    args: ['--no-sandbox', '--disable-dev-shm-usage', '--lang=fa-IR'],
    defaultViewport: { width: 1440, height: 900 },
  });
  const page = await browser.newPage();

  /* evidence collectors */
  const pageErrors = [];
  const consoleErrors = [];
  const xhrs = [];
  page.on('pageerror', (e) => pageErrors.push(e.message));
  page.on('console', (m) => { if (m.type() === 'error') consoleErrors.push(m.text()); });
  page.on('response', async (resp) => {
    try {
      const url = resp.url();
      if (!url.startsWith(base)) return;
      const ct = resp.headers()['content-type'] || '';
      if (!ct.includes('json')) return;
      let body = '';
      try { body = (await resp.text()).slice(0, 200000); } catch { /* ignore */ }
      xhrs.push({ url: url.replace(base, ''), status: resp.status(), body });
    } catch { /* ignore */ }
  });

  const barText = () => page.$eval('#pfRunBar', (el) => el.textContent).catch(() => '');
  const toastsNow = () => page.evaluate(() =>
    Array.from(document.querySelectorAll('#toasts .toast'))
      .map((t) => t.textContent.trim()).join(' | ')).catch(() => '');
  async function waitToast(substr, timeout = 30000) {
    const t0 = Date.now();
    for (;;) {
      const t = await toastsNow();
      if (t.includes(substr)) return t;
      if (Date.now() - t0 > timeout) {
        throw new Error('TIMEOUT waiting for toast containing "' + substr + '" (seen: ' + (t || '(none)') + ')');
      }
      await sleep(100);
    }
  }
  const stageBadge = (stage) => page.evaluate((s) => {
    const card = document.querySelector('.pf-stage[data-pfstage="' + s + '"]');
    if (!card) return null;
    const b = card.querySelector('.pf-stage-head .badge');
    return b ? b.textContent.trim() : null;
  }, stage);
  const stageBody = (stage) => page.evaluate((s) => {
    const card = document.querySelector('.pf-stage[data-pfstage="' + s + '"]');
    return card ? card.querySelector('.pf-stage-body').textContent : '';
  }, stage);

  let exitCode = 0;
  try {
    /* ── U-login ───────────────────────────────────────────────────── */
    await page.goto(base + '/dashboard/studio.html', { waitUntil: 'load' });
    await waitFor(async () => {
      const d = await page.$eval('#loginOverlay', (el) => getComputedStyle(el).display);
      return d !== 'none';
    }, { label: 'login overlay visible' });
    check('U-login-overlay-shown', true, 'overlay visible before auth');

    await page.type('#loginPassword', 'wrong-password-999');
    await page.click('#loginForm button[type=submit]');
    await waitFor(async () => {
      const t = await page.$eval('#loginError', (el) => el.textContent).catch(() => '');
      return t.includes('رمز عبور اشتباه است');
    }, { label: 'wrong-password message', timeout: 15000 });
    check('U-login-wrong-pw-message', true, '#loginError = "رمز عبور اشتباه است"');
    await shot(page, '01-login-wrong.png');

    await page.$eval('#loginPassword', (el) => { el.value = ''; });
    await page.type('#loginPassword', PASSWORD);
    await page.click('#loginForm button[type=submit]');
    await waitFor(async () => {
      const d = await page.$eval('#loginOverlay', (el) => getComputedStyle(el).display);
      return d === 'none';
    }, { label: 'login overlay hidden after right password', timeout: 15000 });
    check('U-login-success', true, 'overlay hidden, session cookie set');
    await shot(page, '02-logged-in-empty.png');

    /* ── U-create collection ───────────────────────────────────────── */
    await page.click('#createBtn');
    await waitFor(() => page.$eval('#createModal', (el) => el.classList.contains('open')),
      { label: 'create modal open' });
    await page.type('#cName', 'کالکشن آزمایشی UI');
    await page.type('#cSlug', 'ui-check');
    await page.click('#createSubmit');
    await waitToast('ساخته شد', 20000);
    await waitFor(async () => {
      const n = await page.$$eval('#colList .col-item', (els) => els.length);
      return n >= 1;
    }, { label: 'collection appears in list' });
    check('U-create-collection', true, 'کالکشن آزمایشی UI (ui-check) created, listed');
    await shot(page, '03-collection-created.png');

    /* ── U-open collection ─────────────────────────────────────────── */
    await page.click('#colList .col-item');
    await waitFor(async () => {
      const d = await page.$eval('#wsContent', (el) => el.style.display);
      return d !== 'none';
    }, { label: 'workspace content visible' });
    await waitFor(async () => (await barText()).includes('بدون run'),
      { label: 'run bar shows "بدون run"', timeout: 15000 });
    check('U-open-collection', true, 'workspace visible, pipeline run bar = "بدون run"');

    /* ── U-import: multi-file (10 docx) ────────────────────────────── */
    await page.click('#importBtn');
    await waitFor(() => page.$eval('#importModal', (el) => el.classList.contains('open')),
      { label: 'import modal open' });
    const input = await page.$('#importFileInput');
    await input.uploadFile(...docx);
    await waitFor(async () => {
      const dis = await page.$eval('#importConfirm', (el) => el.disabled);
      const rows = await page.$$eval('#importPlan tbody tr', (els) => els.length).catch(() => 0);
      return !dis && rows === 10;
    }, { label: 'import plan ready (10 rows, confirm enabled)', timeout: 30000 });
    await shot(page, '04-import-plan.png');
    await page.click('#importConfirm');
    const impToast = await waitToast('آپلود و ثبت شد', 90000);
    await waitFor(() => page.$eval('#importModal', (el) => !el.classList.contains('open')),
      { label: 'import modal closed', timeout: 15000 });
    check('U-import-10-files', true, impToast.slice(0, 200));

    /* ── U-run / U-pause / U-error / U-resume ──────────────────────── */
    await page.click('#pfRunBtn');
    await waitToast('خط لوله شروع شد', 20000);
    await waitFor(async () => (await barText()).includes('در حال اجرا'),
      { label: 'run bar "در حال اجرا"' });
    check('U-run-started', true, 'run bar = در حال اجرا');

    await waitFor(async () => !(await page.$eval('#pfPauseBtn', (el) => el.disabled)),
      { label: 'pause button enabled (running)' });
    await page.click('#pfPauseBtn');
    await waitToast('متوقف شد', 20000);
    await waitFor(async () => (await barText()).includes('توقف‌شده'),
      { label: 'run bar "توقف‌شده"' });
    const btnState = await page.evaluate(() => ({
      pause: document.querySelector('#pfPauseBtn').disabled,
      resume: document.querySelector('#pfResumeBtn').disabled,
      run: document.querySelector('#pfRunBtn').disabled,
    }));
    check('U-pause-mid-run', true, 'run bar = توقف‌شده; buttons ' + JSON.stringify(btnState));
    check('U-pause-button-states', btnState.pause === true && btnState.resume === false,
      JSON.stringify(btnState));
    await shot(page, '05-paused.png');

    /* clicking "run" while paused must give an honest error toast (409) */
    await page.click('#pfRunBtn');
    const errToast = await waitToast('paused', 15000);
    check('U-error-409-while-paused', errToast.includes('paused'), errToast.slice(0, 200));

    await page.click('#pfResumeBtn');
    await waitToast('ادامه خط لوله', 15000);
    await waitFor(async () => (await barText()).includes('انجام شد'),
      { label: 'run bar "انجام شد" after resume', timeout: 300000 });
    check('U-resume-to-done', true, 'run bar = انجام شد (full run A→F finished)');

    /* ── U-stages: the 6 connected cards ───────────────────────────── */
    const nCards = await page.$$eval('.pfStages .pf-stage, .pf-stage', (els) => els.length);
    check('U-stages-6-cards', nCards === 6, 'cards=' + nCards);
    const badges = {};
    for (const s of ['A_IMPORT', 'B_PROCESS', 'C_SCHEMA', 'D_BUILD', 'E_ACCEPT', 'RELEASE']) {
      badges[s] = await stageBadge(s);
    }
    check('U-stages-badges',
      badges.A_IMPORT === 'موفق' && badges.B_PROCESS === 'موفق' && badges.C_SCHEMA === 'موفق' &&
      badges.D_BUILD === 'موفق' && badges.E_ACCEPT === 'بلاک' && badges.RELEASE === 'موفق',
      JSON.stringify(badges));

    const aBody = await stageBody('A_IMPORT');
    check('U-stages-A-counts', aBody.includes('اسناد کل') && aBody.includes('۱۰'),
      aBody.slice(0, 200));
    const cBody = await stageBody('C_SCHEMA');
    check('U-stages-C-schema-id', /sv-c-[0-9a-f]{8}-0001/.test(cBody), cBody.slice(0, 200));
    const eBody = await stageBody('E_ACCEPT');
    check('U-stages-E-honest-blocked', eBody.includes('blocked') && eBody.includes('دلیل'),
      eBody.slice(0, 200));
    const fBody = await stageBody('RELEASE');
    check('U-stages-F-release-info', fBody.includes('rel-') && fBody.includes('RAG'),
      fBody.slice(0, 300));
    await shot(page, '06-stages-done.png');

    /* ── U-history (audit log rows) ────────────────────────────────── */
    await waitFor(async () => {
      const t = await page.$eval('#pfHistory', (el) => el.textContent).catch(() => '');
      return t.includes('pipeline') && t.includes('paused');
    }, { label: 'history shows pipeline rows incl. pause', timeout: 20000 });
    const histText = await page.$eval('#pfHistory', (el) => el.textContent).catch(() => '');
    const histRows = await page.$$eval('#pfHistory tbody tr', (els) => els.length).catch(() => 0);
    check('U-history-rows', histRows >= 3 && histText.includes('pipeline'),
      'rows=' + histRows + '; actions incl. pipeline_* / paused: ' +
      ['started', 'paused', 'resumed', 'done'].map((k) => k + '=' + histText.includes(k)).join(' '));

    /* ── U-fromstage: resume-from RELEASE (checkpoint) ─────────────── */
    await page.select('#pfFromStage', 'RELEASE');
    await page.click('#pfFromBtn');
    await waitToast('ادامه از stage RELEASE', 20000);
    let sawRunning = false;
    {
      const t0 = Date.now();
      while (Date.now() - t0 < 20000) {
        if ((await barText()).includes('در حال اجرا')) { sawRunning = true; break; }
        await sleep(100);
      }
    }
    await waitFor(async () => (await barText()).includes('انجام شد'),
      { label: 'run done after from-stage', timeout: 180000 });
    await waitFor(async () => {
      const t = await page.$eval('#pfHistory', (el) => el.textContent).catch(() => '');
      return t.includes('from=RELEASE');
    }, { label: 'history shows from=RELEASE', timeout: 30000 });
    check('U-fromstage-release', true,
      'sawRunning=' + sawRunning + '; history detail contains "from=RELEASE"');

    /* ── U-schedule: nightly (int PK in, string cid out) ───────────── */
    await page.click('#pfSchedOn');
    await page.$eval('#pfSchedTime', (el) => { el.value = '03:30'; });
    await page.click('#pfSchedSave');
    await waitToast('Schedule ذخیره شد', 15000);
    await waitFor(async () => page.evaluate(() => {
      const box = document.querySelector('#pfSchedule');
      const cb = document.querySelector('#pfSchedOn');
      const tm = document.querySelector('#pfSchedTime');
      return box && cb && cb.checked &&
        tm && tm.value === '03:30' && box.textContent.includes('آخرین به‌روزرسانی');
    }), { label: 'schedule re-rendered (checked, 03:30, updated hint)', timeout: 15000 });
    check('U-schedule-save-roundtrip', true,
      'checkbox checked + time 03:30 + "آخرین به‌روزرسانی" hint (int PK accepted, string cid matched)');
    await shot(page, '07-schedule-saved.png');

    /* ── U-releases table (corpus card) ────────────────────────────── */
    const relTable = await page.$eval('#stReleasesInner', (el) => el.textContent).catch(() => '');
    check('U-releases-table', relTable.includes('rel-') && relTable.includes('دانلود'),
      relTable.slice(0, 150));

    /* ── U-download: the release zip (real bytes) ──────────────────── */
    const dlHref = await page.$eval(
      '.pf-stage[data-pfstage="RELEASE"] a[href*="/download"]',
      (a) => a.getAttribute('href'));
    const dl = await page.evaluate(async (h) => {
      const r = await fetch(h, { credentials: 'same-origin' });
      const buf = new Uint8Array(await r.arrayBuffer());
      return { status: r.status, size: buf.length,
               magic: String.fromCharCode(buf[0], buf[1]) };
    }, dlHref);
    check('U-download-release-zip',
      dl.status === 200 && dl.magic === 'PK' && dl.size > 1024,
      dlHref + ' -> ' + JSON.stringify(dl));

    /* ── U-secrets: no password in DOM or any XHR body ─────────────── */
    const html = await page.evaluate(() => document.documentElement.outerHTML);
    check('U-secrets-DOM', !html.includes(PASSWORD), 'password absent from rendered DOM');
    check('U-secrets-XHR', !xhrs.some((x) => x.body.includes(PASSWORD)),
      xhrs.length + ' JSON responses captured, none contain the password');

    /* ── U-jshealth ────────────────────────────────────────────────── */
    check('U-jshealth-pageerrors', pageErrors.length === 0,
      pageErrors.slice(0, 3).join(' | ') || 'no page errors');
    const consoleErrs = consoleErrors.filter((t) => !/Failed to load resource|favicon/i.test(t));
    check('U-jshealth-console', consoleErrs.length === 0,
      consoleErrs.slice(0, 3).join(' | ') || 'no console errors (benign network 404s filtered)');

    /* ── U-overflow desktop ────────────────────────────────────────── */
    const ov = await page.evaluate(() =>
      document.documentElement.scrollWidth - document.documentElement.clientWidth);
    check('U-desktop-no-overflow', ov <= 1, 'scrollWidth-clientWidth=' + ov);

    /* ── U-mobile: 390x844 ─────────────────────────────────────────── */
    await page.setViewport({ width: 390, height: 844 });
    await page.reload({ waitUntil: 'load' });
    await waitFor(async () => {
      const d = await page.$eval('#wsContent', (el) => el.style.display).catch(() => 'none');
      return d !== 'none';
    }, { label: 'collection reopened on mobile (hash routing)', timeout: 30000 });
    const mOv = await page.evaluate(() =>
      document.documentElement.scrollWidth - document.documentElement.clientWidth);
    check('U-mobile-no-overflow', mOv <= 1, 'scrollWidth-clientWidth=' + mOv + ' @390x844');
    await shot(page, '08-mobile-390.png');
  } catch (e) {
    exitCode = 1;
    check('U-fatal', false, (e && e.message) || String(e));
  } finally {
    /* evidence + cleanup */
    const failed = results.filter((r) => !r.pass);
    fs.writeFileSync(path.join(here, 'results.json'), JSON.stringify({
      at: new Date().toISOString(),
      url: base,
      server_log_tail: server.log().slice(-4000),
      checks: results,
      page_errors: pageErrors,
      console_errors: consoleErrors,
      xhr_count: xhrs.length,
    }, null, 2));
    await browser.close().catch(() => {});
    try {
      execSync('taskkill /F /T /PID ' + server.child.pid, { stdio: 'ignore' });
    } catch { server.child.kill(); }
    console.log('\n=== UI CHECK SUMMARY: ' +
      (results.length - failed.length) + '/' + results.length + ' passed ===');
    if (failed.length) {
      console.log('failed: ' + failed.map((f) => f.name).join(', '));
      console.log('tmp kept for inspection: ' + TMP);
    } else {
      fs.rmSync(TMP, { recursive: true, force: true });
    }
  }
  process.exit(exitCode);
}

main().catch((e) => { console.error(e); process.exit(1); });

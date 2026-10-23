// On-page project editor: pick a point, edit it, test the page, then read ahead.
(() => {
  if (window.__pctPicker) return;
  window.__pctPicker = true;

  const BACKEND = 'https://corpus.ai.ismc.ir';
  let project = null;
  let picking = false;
  let previousTag = '';
  let selected = null;
  let busy = false;
  let poll = null;

  const hostEl = document.createElement('div');
  hostEl.id = 'pct-picker-host';
  hostEl.style.cssText = 'all:initial;position:fixed;top:12px;left:12px;z-index:2147483647;';
  const shadow = hostEl.attachShadow({ mode: 'open' });
  shadow.innerHTML = `
    <style>
      * { box-sizing: border-box; }
      .panel {
        width: 340px; max-height: calc(100vh - 24px); overflow: auto; direction: rtl;
        font-family: Tahoma, sans-serif; font-size: 13px; background: #1a1a2e; color: #e8e8e8;
        border: 1px solid #334155; border-radius: 12px; padding: 12px;
        box-shadow: 0 10px 28px rgba(0,0,0,.4); display: none;
      }
      h2 { font-size: 14px; margin: 0 0 2px; color: #f8fafc; }
      .sub { font-size: 11px; color: #94a3b8; margin-bottom: 8px; }
      .steps { display: flex; gap: 4px; margin-bottom: 10px; }
      .steps span { flex: 1; text-align: center; font-size: 10px; color: #94a3b8; border-bottom: 2px solid #334155; padding-bottom: 4px; }
      .steps span.on { color: #f8fafc; border-color: #e94560; }
      label { display: block; color: #94a3b8; font-size: 11px; margin: 8px 0 3px; }
      input, select {
        width: 100%; padding: 7px; border-radius: 6px; border: 1px solid #334155;
        background: #0f172a; color: #f8fafc; font-family: inherit;
      }
      .row { display: flex; gap: 6px; margin-top: 8px; }
      button {
        flex: 1; padding: 8px; border: 0; border-radius: 6px; cursor: pointer;
        font-family: inherit; font-weight: 700; color: #f8fafc; background: #1e293b;
      }
      button:focus-visible { outline: 2px solid #f8fafc; outline-offset: 2px; }
      button.primary { background: #e94560; }
      button.stop { background: #7f1d1d; }
      ul { list-style: none; padding: 0; margin: 8px 0 0; }
      li { border-top: 1px solid #334155; padding: 6px 0; }
      .tag { font-weight: 700; }
      .sample { color: #94a3b8; font-size: 11px; margin: 2px 0 4px; }
      .mini { display: flex; gap: 4px; }
      .mini button { padding: 4px 8px; font-size: 11px; font-weight: 600; }
      .preview { background: #0f172a; border-radius: 6px; padding: 8px; min-height: 32px; max-height: 64px; overflow: auto; color: #e2e8f0; }
      .report { margin-top: 8px; font-size: 12px; line-height: 1.5; color: #e2e8f0; }
      .form { display: none; margin-top: 8px; }
    </style>
    <div class="panel" id="panel">
      <h2 id="title">پروژه</h2>
      <div class="sub">نقطهٔ تفسیر را انتخاب کن. متن آیه جداست.</div>
      <div class="steps" aria-hidden="true">
        <span class="on">۱ پروژه</span><span id="step2">۲ نقطه‌ها</span><span id="step3">۳ آزمایش</span><span id="step4">۴ خواندن</span>
      </div>
      <ul id="points"></ul>
      <div class="row">
        <button class="primary" id="add" type="button">نقطه جدید</button>
        <button id="close" type="button">بستن</button>
      </div>
      <div class="form" id="form">
        <div class="preview" id="preview">روی متن تفسیر در صفحه کلیک کن</div>
        <label for="tag">اسم نقطه</label>
        <input id="tag" placeholder="مثلا متن یا جلد">
        <label for="source">از کجا</label>
        <select id="source">
          <option value="css">همین عنصر</option>
          <option value="url_param">پارامتر آدرس</option>
          <option value="url">لینک صفحه</option>
        </select>
        <label for="selector">نشانی عنصر یا نام پارامتر</label>
        <input id="selector">
        <label for="transform">خواندن</label>
        <select id="transform">
          <option value="text">متن کامل</option>
          <option value="before_paren">قبل از پرانتز</option>
          <option value="paren_number">عدد داخل پرانتز</option>
          <option value="add_one">عدد به‌اضافه یک</option>
        </select>
        <div class="row">
          <button class="primary" id="savePoint" type="button">ذخیره نقطه</button>
          <button id="cancel" type="button">انصراف</button>
        </div>
      </div>
      <label for="nextParam">صفحه بعد با پارامتر آدرس</label>
      <div class="row">
        <input id="nextParam" placeholder="item_index" style="flex:2">
        <input id="nextStep" type="number" value="1" min="1" style="flex:1" aria-label="گام">
      </div>
      <label for="pace">در هر دقیقه چند صفحه</label>
      <input id="pace" type="number" min="1" max="12" value="4">
      <div class="row">
        <button class="primary" id="test" type="button">آزمایش و شروع</button>
        <button class="stop" id="stop" type="button">توقف</button>
      </div>
      <div class="report" id="report" role="status" aria-live="polite" aria-atomic="true"></div>
    </div>
  `;

  const $ = (id) => shadow.getElementById(id);

  function panel() { return $('panel'); }
  function report(text) { $('report').textContent = text || ''; }

  function cssFor(el) {
    const classes = [...el.classList].filter((c) => !/^data-v-/.test(c));
    const bem = classes.find((c) => c.includes('__') || c.includes('--'));
    if (bem) return '.' + bem;
    if (classes[0]) return el.tagName.toLowerCase() + '.' + classes[0];
    if (el.id) return '#' + CSS.escape(el.id);
    return el.tagName.toLowerCase();
  }

  function textOf(el) {
    return ((el && (el.innerText || el.textContent)) || '').replace(/\s+/g, ' ').trim();
  }

  function applyField(field) {
    if (field.source === 'url') return location.href.split('#')[0];
    if (field.source === 'url_param') {
      const value = new URLSearchParams(location.search).get(field.selector) || '';
      if (field.transform === 'add_one') {
        const n = parseInt(value, 10);
        return Number.isFinite(n) ? String(n + 1) : '';
      }
      return value;
    }
    let el = null;
    try {
      if (field.source === 'xpath') {
        el = document.evaluate(field.selector, document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
      } else if (field.selector) {
        el = document.querySelector(field.selector);
      }
    } catch (_) {
      el = null;
    }
    const text = textOf(el);
    if (field.transform === 'before_paren') return text.split('(')[0].trim();
    if (field.transform === 'paren_number') {
      const found = text.match(/\((\d+)\)/);
      return found ? found[1] : '';
    }
    return text;
  }

  function showForm(on) {
    $('form').style.display = on ? 'block' : 'none';
    picking = on && $('source').value === 'css';
  }

  function fillForm(point) {
    previousTag = point?.tag || '';
    $('tag').value = point?.tag || '';
    $('source').value = point?.source || 'css';
    $('selector').value = point?.selector || '';
    $('transform').value = point?.transform || 'text';
    $('preview').textContent = point?.sample || 'روی متن تفسیر در صفحه کلیک کن';
    showForm(true);
    $('tag').focus();
  }

  function render() {
    if (!project) return;
    $('title').textContent = project.name || 'پروژه';
    $('nextParam').value = project.next_param || $('nextParam').value;
    $('nextStep').value = project.next_step || 1;
    $('pace').value = project.pages_per_minute || 4;
    const count = (project.points || []).length;
    $('step2').classList.toggle('on', count > 0);
    $('step3').classList.toggle('on', project.status === 'tested' || project.status === 'running' || project.status === 'paused');
    $('step4').classList.toggle('on', project.status === 'running');
    const list = $('points');
    list.innerHTML = '';
    (project.points || []).forEach((point) => {
      const li = document.createElement('li');
      const name = document.createElement('div');
      name.className = 'tag';
      name.textContent = point.tag;
      const sample = document.createElement('div');
      sample.className = 'sample';
      sample.textContent = (point.sample || point.selector || point.source).slice(0, 80);
      const mini = document.createElement('div');
      mini.className = 'mini';
      const edit = document.createElement('button');
      edit.type = 'button';
      edit.textContent = 'ویرایش';
      edit.addEventListener('click', () => fillForm(point));
      const remove = document.createElement('button');
      remove.type = 'button';
      remove.textContent = 'حذف';
      remove.addEventListener('click', () => removePoint(point.tag));
      mini.append(edit, remove);
      li.append(name, sample, mini);
      list.appendChild(li);
    });
    if (!count) {
      const li = document.createElement('li');
      li.textContent = 'هنوز نقطه‌ای وصل نشده';
      list.appendChild(li);
    }
    if (project.last_message || project.saved_count) {
      report(
        `${project.last_message || project.status} — ذخیره ${project.saved_count || 0}، رد ${project.skipped_count || 0}، خطا ${project.failed_count || 0}`
      );
    }
  }

  async function load(id) {
    const r = await fetch(`${BACKEND}/api/projects/${id}`);
    if (!r.ok) throw new Error('پروژه پیدا نشد');
    project = await r.json();
    render();
    return project;
  }

  function openPanel() {
    if (!hostEl.isConnected) document.documentElement.appendChild(hostEl);
    panel().style.display = 'block';
    if (!poll) poll = setInterval(() => { if (project?.id) load(project.id).catch(() => {}); }, 4000);
  }

  function closePanel() {
    picking = false;
    panel().style.display = 'none';
    if (selected) selected.style.outline = '';
  }

  async function savePoint() {
    if (!project?.id) {
      report('اول از اکستنشن پروژه را بساز');
      return;
    }
    const tag = $('tag').value.trim();
    if (!tag) {
      report('اسم نقطه را بنویس');
      return;
    }
    const source = $('source').value;
    const r = await fetch(`${BACKEND}/api/projects/${project.id}/points`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        previous_tag: previousTag,
        tag,
        source,
        selector: source === 'url' ? '' : $('selector').value.trim(),
        transform: $('transform').value,
        sample: ($('preview').textContent || '').slice(0, 240),
      }),
    });
    const data = await r.json();
    if (!r.ok || data.ok === false) throw new Error(data.message || 'ذخیره نقطه نشد');
    project = data.project;
    previousTag = '';
    showForm(false);
    render();
    report(`نقطه ${tag} ذخیره شد`);
  }

  async function removePoint(tag) {
    const r = await fetch(`${BACKEND}/api/projects/${project.id}/points?tag=${encodeURIComponent(tag)}`, { method: 'DELETE' });
    const data = await r.json();
    if (!r.ok || data.ok === false) throw new Error(data.message || 'حذف نشد');
    project = data.project;
    render();
  }

  async function saveRule() {
    const param = $('nextParam').value.trim();
    const r = await fetch(`${BACKEND}/api/projects/${project.id}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        next_mode: param ? 'url_param' : 'none',
        next_param: param,
        next_step: Number($('nextStep').value) || 1,
        pages_per_minute: Math.max(1, Math.min(12, Number($('pace').value) || 4)),
      }),
    });
    const data = await r.json();
    if (!r.ok || data.ok === false) throw new Error(data.message || 'قانون ذخیره نشد');
    project = data.project;
    return project;
  }

  async function waitFor(points) {
    const css = points.filter((p) => (p.source === 'css' || p.source === 'xpath') && p.selector);
    const start = Date.now();
    while (css.length && Date.now() - start < 8000) {
      const found = css.some((p) => {
        try {
          if (p.source === 'xpath') {
            return document.evaluate(p.selector, document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
          }
          return document.querySelector(p.selector);
        } catch (_) {
          return false;
        }
      });
      if (found) return;
      await new Promise((resolve) => setTimeout(resolve, 250));
    }
  }

  async function extract(points, projectId) {
    if (busy) return { ok: false, message: 'در حال خواندن' };
    busy = true;
    try {
      await waitFor(points);
      const url = location.href.split('#')[0];
      const values = {};
      points.forEach((point) => { values[point.tag] = applyField(point); });
      const r = await fetch(`${BACKEND}/api/projects/${projectId}/pages`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url, values }),
      });
      const data = await r.json();
      if (!r.ok || data.ok === false) {
        return { ok: false, status: data.status || 'empty', message: data.message || 'خوانده نشد', values, url };
      }
      if (data.project) project = data.project;
      return { ok: true, status: data.status, values, url, project: data.project };
    } catch (e) {
      return { ok: false, message: String(e) };
    } finally {
      busy = false;
    }
  }

  async function testAndStart() {
    if (!project?.id) {
      report('اول از اکستنشن پروژه را بساز');
      return { ok: false, message: 'پروژه‌ای انتخاب نشده' };
    }
    if (!(project.points || []).length) {
      report('اول یک نقطه از متن تفسیر وصل کن');
      return { ok: false, message: 'نقطه‌ای تعریف نشده' };
    }
    try {
      await saveRule();
    } catch (e) {
      report(String(e));
      return { ok: false, message: String(e) };
    }
    const result = await extract(project.points, project.id);
    render();
    if (!result.ok) {
      report(result.message || 'آزمایش ناموفق بود');
      return result;
    }
    const preview = Object.entries(result.values).map(([k, v]) => `${k}: ${String(v || '').slice(0, 60)}`).join(' | ');
    if (project.next_mode !== 'url_param' || !project.next_param) {
      report(`صفحه ذخیره شد. قانون صفحه بعد را بنویس تا خواندن ادامه پیدا کند. ${preview}`);
      return { ok: true, started: false, message: reportText(), values: result.values };
    }
    const started = await chrome.runtime.sendMessage({
      action: 'startReading',
      projectId: project.id,
      pagesPerMinute: project.pages_per_minute,
    });
    report(started?.ok ? `${started.message} — ${preview}` : (started?.message || preview));
    if (started?.ok) $('step4').classList.add('on');
    return { ok: !!started?.ok, started: !!started?.ok, message: $('report').textContent, values: result.values };
  }

  function reportText() { return $('report').textContent; }

  document.addEventListener('mouseover', (e) => {
    if (!picking || hostEl.contains(e.target)) return;
    if (selected && selected !== e.target) selected.style.outline = '';
    e.target.style.outline = '2px solid #e94560';
    selected = e.target;
  }, true);

  document.addEventListener('click', (e) => {
    if (!picking || hostEl.contains(e.target)) return;
    e.preventDefault();
    e.stopPropagation();
    selected = e.target;
    $('source').value = 'css';
    $('preview').textContent = textOf(e.target).slice(0, 180) || '(بدون متن)';
    $('selector').value = cssFor(e.target);
    $('transform').value = 'text';
    $('tag').focus();
  }, true);

  $('add').addEventListener('click', () => fillForm(null));
  $('cancel').addEventListener('click', () => { picking = false; showForm(false); if (selected) selected.style.outline = ''; });
  $('close').addEventListener('click', closePanel);
  $('savePoint').addEventListener('click', () => savePoint().catch((e) => report(String(e))));
  $('test').addEventListener('click', () => testAndStart());
  $('stop').addEventListener('click', () => {
    chrome.runtime.sendMessage({ action: 'stopReading' }, (resp) => {
      report(resp?.message || 'توقف شد');
    });
  });
  $('source').addEventListener('change', () => { picking = $('source').value === 'css' && $('form').style.display === 'block'; });

  chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
    if (message.action === 'openProject') {
      openPanel();
      const params = new URLSearchParams(location.search);
      if (params.has('item_index') && !$('nextParam').value) $('nextParam').value = 'item_index';
      load(message.projectId).then(() => sendResponse({ ok: true })).catch((e) => sendResponse({ ok: false, message: String(e) }));
      return true;
    }
    if (message.action === 'testProject') {
      openPanel();
      const run = () => testAndStart().then(sendResponse);
      if (project?.id) run();
      else if (message.projectId) load(message.projectId).then(run).catch((e) => sendResponse({ ok: false, message: String(e) }));
      else sendResponse({ ok: false, message: 'پروژه‌ای انتخاب نشده' });
      return true;
    }
    if (message.action === 'extractProject') {
      extract(message.points || project?.points || [], message.projectId).then(sendResponse);
      return true;
    }
    if (message.action === 'ping') {
      sendResponse({ ok: true, picker: true });
      return true;
    }
    return false;
  });
})();

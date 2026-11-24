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
  let runState = null;
  // PCM-EXT-10 (v3.13): snapshot of «آخرین تنظیمات همگام‌شده» از سرور — پل ۴ ثانیه‌ای
  // فقط فیلدی را بازنویسی می‌کند که کاربر دست نخورده باشد (عبارت هنوز با اسنپ‌شات یکی
  // است)؛ وگرنه ویرایش در حال کاربر حفظ می‌شود.
  let syncedSettings = null;
  // PCM-EXT-03: باید با RUN_LOCK_TTL بک‌اند یکی باشد (ثانیه).
  const RUN_LOCK_TTL_SEC = 180;
  // قفل بین‌مرورگری: آیا همین پروژه را نشست/مرورگر دیگری همین حالا می‌خواند؟
  // (مبنای قضاوت: GET پروژه که run_owner/run_heartbeat را از بک‌اند می‌آورد.)
  const lockLiveByOther = () => !!(
    project?.run_owner && project?.run_heartbeat &&
    (Date.now() / 1000 - Number(project.run_heartbeat)) < RUN_LOCK_TTL_SEC
  );

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
          <option value="hash_param">پارامتر hash (سوره/آیه)</option>
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
          <option value="src_attr">مدرک src (مثل آدرس mp3)</option>
        </select>
        <div class="row">
          <button class="primary" id="savePoint" type="button">ذخیره نقطه</button>
          <button id="cancel" type="button">انصراف</button>
        </div>
      </div>
      <label for="nextMode">روش صفحه بعد</label>
      <div class="row">
        <select id="nextMode" style="flex:3">
          <option value="param">پارامتر آدرس (item_index=5)</option>
          <option value="nextlink">لینک صفحه بعد در صفحه</option>
          <option value="hash">دکمهٔ «آیه بعد» (hash سوره/آیه)</option>
          <option value="number">عدد در آدرس (ساده)</option>
          <option value="pathnumber">عددِ بالای مسیر (slug دست‌نخورده)</option>
          <option value="regex">رجکس (دقیق)</option>
          <option value="none">بدون قانون</option>
        </select>
        <input id="nextStep" type="number" value="1" min="1" style="flex:1" aria-label="گام">
      </div>
      <div id="nextDetail" class="row" style="display:none">
        <input id="nextDetailInput" dir="ltr" style="flex:3">
      </div>
      <div class="sub" id="nextHint"></div>
      <label for="pace">در هر دقیقه چند صفحه</label>
      <input id="pace" type="number" min="1" max="12" value="4">
      <label for="stopNum">حد عددی توقف (صفحهٔ آخر؛ خالی = بدون حد)</label>
      <input id="stopNum" type="number" min="1" step="1" placeholder="مثلا 495 — تا همین عدد بخواند">
      <label for="stopField">مبنای تشخیص تکرار محتوا (۱۰ صفحهٔ یکسان → توقف)</label>
      <select id="stopField" title="اگر ۱۰ صفحهٔ پشت‌سرهم محتوای یکسان دید، خواندن ایست می‌کند. «خودکار» یعنی کل محتوا">
        <option value="">خودکار (کل محتوا)</option>
      </select>
      <div class="row">
        <button class="primary" id="test" type="button">آزمایش و شروع</button>
        <button class="stop" id="stop" type="button">توقف</button>
      </div>
      <div class="row" id="restartRow" style="display:none">
        <button id="restart" type="button">شروع از نو (از همین صفحه)</button>
      </div>
      <div class="row">
        <button id="saveSettings" type="button" title="حتی حین خواندن ذخیره می‌شود و حلقهٔ خواندن از دقیقهٔ بعد از آن‌ها استفاده می‌کند">ذخیره تنظیمات</button>
      </div>
      <div class="sub" id="runNote" style="display:none"></div>
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
    // PCM-EXT-08: hash_param — پارامترها از hash آدرس خوانده می‌شود
    // (SPAهای hash-based مثل تفسیر نور: #numsooreh=1&numayeh=1).
    if (field.source === 'hash_param') {
      const hashQuery = String(location.hash || '').replace(/^#/, '');
      const value = new URLSearchParams(hashQuery).get(field.selector) || '';
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
    // PCM-EXT-08: src_attr — مدرک src را (آدرس mp3 از <audio><source>) لینک مطلق برمی‌گرداند.
    if (field.transform === 'src_attr') {
      const raw = el ? String(el.getAttribute('src') || el.getAttribute('href') || '') : '';
      if (!raw) return '';
      try { return new URL(raw, location.href).href; } catch (_) { return raw; }
    }
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
    syncSettingsFromServer();
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

  // PCM-EXT-10 (v3.13): همگام‌سازی تنظیمات بدون بازنویسی ویرایشِ کاربر.
  // اگر مقدار فعلی فورم با اسنپ‌شات (آخرین همگام) فرق دارد، یعنی کاربر آن فیلد
  // را عوض کرده → حفظ کن؛ وگرنه با وضعیت سرور همگام شود.
  const SETTINGS_FIELDS = ['mode', 'detail', 'step', 'pace', 'stopNum', 'stopField'];
  function serverSettings() {
    const parsed = parseSpecField(project.next_param);
    return {
      mode: parsed.mode,
      detail: parsed.detail,
      step: String(project.next_step || 1),
      pace: String(project.pages_per_minute || 4),
      stopNum: String(project.stop_number || ''),
      stopField: String(project.stop_field || ''),
    };
  }
  function readFormSettings() {
    return {
      mode: $('nextMode').value,
      detail: $('nextDetailInput').value,
      step: $('nextStep').value,
      pace: $('pace').value,
      stopNum: $('stopNum').value,
      stopField: $('stopField').value,
    };
  }
  function applySettings(s) {
    $('nextMode').value = s.mode;
    $('nextDetailInput').value = s.detail;
    $('nextStep').value = s.step;
    $('pace').value = s.pace;
    $('stopNum').value = s.stopNum;
    rebuildStopField(s.stopField);
    updateNextDetail();
  }
  function syncSettingsFromServer() {
    const server = serverSettings();
    if (!syncedSettings) {
      applySettings(server);
      syncedSettings = server;
      return;
    }
    const cur = readFormSettings();
    const next = {};
    for (const k of SETTINGS_FIELDS) {
      next[k] = (cur[k] !== syncedSettings[k]) ? cur[k] : server[k];
    }
    applySettings(next);
    syncedSettings = next;
  }

  // PCM-EXT-04: گزینه‌های «مبنای تشخیص تکرار محتوا» از نقاط پروژه ساخته می‌شود
  function rebuildStopField(preferred) {
    const sel = $('stopField');
    const current = preferred != null ? String(preferred) : String(project?.stop_field || '');
    const tags = (project?.points || []).map((p) => String(p.tag || '').trim()).filter(Boolean);
    sel.innerHTML = '';
    const opt0 = document.createElement('option');
    opt0.value = '';
    opt0.textContent = 'خودکار (کل محتوا)';
    sel.appendChild(opt0);
    tags.forEach((tag) => {
      const opt = document.createElement('option');
      opt.value = tag;
      opt.textContent = tag;
      sel.appendChild(opt);
    });
    sel.value = (current && tags.includes(current)) ? current : '';
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
    if (!poll) poll = setInterval(async () => { if (project?.id) { await load(project.id).catch(() => {}); refreshRunState(); } }, 4000);
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

  function parseSpecField(raw) {
    const spec = String(raw || '').trim();
    if (spec === 'next-link' || spec.indexOf('next-link:') === 0) {
      return { mode: 'nextlink', detail: spec === 'next-link' ? '' : spec.slice('next-link:'.length).trim() };
    }
    if (spec === 'hash') return { mode: 'hash', detail: '' };
    if (spec === 'url-number') return { mode: 'number', detail: '' };
    if (spec === 'path-number') return { mode: 'pathnumber', detail: '' };
    if (spec.indexOf('regex:') === 0) return { mode: 'regex', detail: spec.slice('regex:'.length).trim() };
    if (spec) return { mode: 'param', detail: spec };
    return { mode: 'none', detail: '' };
  }

  function specFromForm() {
    const mode = $('nextMode').value;
    const detail = $('nextDetailInput').value.trim();
    if (mode === 'param') return detail;
    if (mode === 'nextlink') return detail ? 'next-link:' + detail : 'next-link';
    if (mode === 'hash') return 'hash';
    if (mode === 'number') return 'url-number';
    if (mode === 'pathnumber') return 'path-number';
    if (mode === 'regex') return detail ? 'regex:' + detail : '';
    return '';
  }

  // PCM-EXT-09: پیش‌نمایش آدرس بعدی برای روش‌های عددیِ «از آدرس» (بدون DOM).
  // همان منطق advanceUrl در background.js: اولین بخشِ کاملاً عددی مسیر + گام.
  function advancePreview(specStr, url, step) {
    const u = new URL(url);
    const segs = u.pathname.split('/');
    let found = -1;
    for (let i = 0; i < segs.length; i += 1) {
      if (/^\d+$/.test(segs[i])) { found = i; break; }
    }
    if (found < 0) throw new Error('عددِ کاملی در مسیر آدرس نیست');
    const n = parseInt(segs[found], 10) + (Number(step) || 1);
    if (!Number.isFinite(n)) throw new Error('گام نامعتبر است');
    segs[found] = (segs[found].length > 1 && segs[found][0] === '0')
      ? String(n).padStart(segs[found].length, '0')
      : String(n);
    u.pathname = segs.join('/');
    return u.href;
  }

  const NEXT_DETAIL = {
    param: { show: true, ph: 'item_index', hint: 'نام پارامتر در آدرس، مثلا ?item_index=5 — در هر خواندن به عددش گام اضافه می‌شود.' },
    nextlink: { show: true, ph: 'مثلا: a[rel=next] — خالی = خودکار', hint: 'اگر CSS لینک «بعدی» را می‌دانی بنویس؛ وگرنه خالی بگذار تا خودکار از rel=next، متن «بعدی/ادامه/Next» و عدد آدرس کشف شود.' },
    hash: { show: false, ph: '', hint: 'برای صفحات hash-based مثل تفسیر گرااتی: دکمهٔ «آیه بعد» (viewer(S,A)) پیدا شده و آدرس بعدی ساخته می‌شود ...#numsooreh=S&numayeh=A. اگر دکمه نباشد (ته سوره)، خودکار numsooreh+1 و numayeh=1 می‌شود؛ در سورهٔ ۱۱۴ (ته قرآن) خواندن تمام می‌شود. حد عددی توقف = سوره×10000+شمارهٔ hash (مثلا 2:8 → 20008). آدرس mp3 را با نقطهٔ css روی عنصر source + «مدرک src» بردار.' },
    number: { show: false, ph: '', hint: 'آخرین عدد مسیر + گام؛ صفرهای پیشین حفظ می‌شوند: 001→002 و 1→2 (هم p_ghazal-495.html و هم sh495 را پوشش می‌دهد).' },
    pathnumber: { show: false, ph: '', hint: 'فقط اولین «بخشِ کاملاً عددی» مسیر جلو می‌رود و بقیهٔ آدرس (slug متن‌دار که خود سایت نوشته) دست نمی‌خورد: /questions/4/<slug> → /questions/5/<slug>. صفرهای پیشین حفظ می‌شوند. حد عددی توقف = همان عدد.' },
    regex: { show: true, ph: 'مثلا: p_ghazal-(\\d+)\\.html یا sh(\\d+)', hint: 'الگو روی مسیر آدرس خوانده می‌شود و باید دقیقا یک گروه ( ) با محتوای عددی داشته باشد؛ بعد از +گام، عرض صفرها حفظ می‌شود.' },
    none: { show: false, ph: '', hint: 'فقط همین صفحه خوانده می‌شود؛ خواندن خودکار ادامه پیدا نمی‌کند.' },
  };

  function updateNextDetail() {
    const mode = $('nextMode').value;
    const cfg = NEXT_DETAIL[mode] || NEXT_DETAIL.none;
    $('nextDetail').style.display = cfg.show ? 'flex' : 'none';
    $('nextDetailInput').placeholder = cfg.ph;
    $('nextHint').textContent = cfg.hint || '';
  }

  async function saveRule() {
    const mode = $('nextMode').value;
    const detail = $('nextDetailInput').value.trim();
    if (mode === 'regex' && !detail) {
      report('برای روش رجکس، الگو را بنویس');
      return null;
    }
    if (mode === 'regex' && detail) {
      try { new RegExp(detail); } catch (e) {
        report('رجکس نامعتبر است: ' + e.message);
        return null;
      }
    }
    const spec = specFromForm();
    const r = await fetch(`${BACKEND}/api/projects/${project.id}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        next_mode: spec ? 'url_param' : 'none',
        next_param: spec,
        next_step: Number($('nextStep').value) || 1,
        pages_per_minute: Math.max(1, Math.min(12, Number($('pace').value) || 4)),
        stop_number: $('stopNum').value.trim(),
        stop_field: $('stopField').value,
      }),
    });
    const data = await r.json();
    if (!r.ok || data.ok === false) throw new Error(data.message || 'قانون ذخیره نشد');
    project = data.project;
    syncedSettings = serverSettings(); // ویرایشِ کاربر حالا همان وضعیت سرور شد
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

  async function extract(points, projectId, nextSpec) {
    if (busy) return { ok: false, message: 'در حال خواندن' };
    busy = true;
    try {
      await waitFor(points);
      const specNow = String(nextSpec != null ? nextSpec : (project ? project.next_param : '') || '');
      // PCM-EXT-08: در SPAهای hash-based، hash بخشی از «هویت» صفحه است (هر آیه = یک hash جدا)،
      // پس در حالت hash آن حفظ می‌شود؛ در حالت‌های دیگر، برای تغییر نرفت رفتار dedup
      // سایت‌های موجود، hash مثل قبل حذف می‌شود.
      const url = specNow === 'hash' ? location.href : location.href.split('#')[0];
      const values = {};
      points.forEach((point) => { values[point.tag] = applyField(point); });
      const r = await fetch(`${BACKEND}/api/projects/${projectId}/pages`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url, values }),
      });
      const data = await r.json();
      const spec = specNow;
      let nextUrl = '';
      if (spec === 'next-link' || spec.indexOf('next-link:') === 0) {
        nextUrl = findNextUrl(spec, url);
      } else if (spec === 'hash') {
        nextUrl = hashNextUrl();
      }
      if (!r.ok || data.ok === false) {
        return { ok: false, status: data.status || 'empty', message: data.message || 'خوانده نشد', values, url, nextUrl };
      }
      if (data.project) project = data.project;
      return { ok: true, status: data.status, values, url, nextUrl, project: data.project };
    } catch (e) {
      return { ok: false, message: String(e) };
    } finally {
      busy = false;
    }
  }

  // Find the next page's link on this page. Order: explicit CSS (if given in
  // the spec) → rel=next → anchor text «بعدی/ادامه/Next» → anchor whose path
  // equals "last number in the path +1" (covers numbered sites).
  function findNextUrl(spec, currentUrl) {
    const explicit = spec === 'next-link' ? '' : spec.slice('next-link:'.length).trim();
    const clean = (h) => String(h || '').split('#')[0];
    let here;
    try { here = new URL(currentUrl); } catch (_) { return ''; }
    const abs = (a) => {
      try {
        const u = new URL(a.href, currentUrl);
        if (u.origin !== here.origin) return '';
        const c = clean(u.href);
        return c === clean(currentUrl) ? '' : c;
      } catch (_) {
        return '';
      }
    };
    let anchors = [];
    try { anchors = Array.from(document.querySelectorAll('a[href]')); } catch (_) { return ''; }
    if (explicit) {
      let el = null;
      try { el = document.querySelector(explicit); } catch (_) { el = null; }
      if (el && el.tagName === 'A') {
        const u = abs(el);
        if (u) return u;
      }
    }
    const byRel = anchors.find((a) => /\bnext\b/i.test(a.getAttribute('rel') || ''));
    if (byRel) { const u = abs(byRel); if (u) return u; }
    const exact = /^(بعدی|بعد|ادامه|ادامه مطلب|صفحه بعد|next|»|›|>>|→)$/i;
    const loose = /(بعدی|ادامه|next page)/i;
    const byText = anchors.find((a) => {
      const t = ((a.innerText || a.textContent) || '').replace(/\s+/g, ' ').trim();
      return !!t && t.length <= 40 && (exact.test(t) || loose.test(t));
    });
    if (byText) { const u = abs(byText); if (u) return u; }
    const runs = here.pathname.match(/\d+/g);
    if (runs && runs.length) {
      const run = runs[runs.length - 1];
      const idx = here.pathname.lastIndexOf(run);
      const n = parseInt(run, 10);
      if (Number.isFinite(n)) {
        const bumped = (run.length > 1 && run[0] === '0') ? String(n + 1).padStart(run.length, '0') : String(n + 1);
        const expected = here.pathname.slice(0, idx) + bumped + here.pathname.slice(idx + run.length);
        const byHref = anchors.find((a) => {
          const u = abs(a);
          if (!u) return false;
          try { return new URL(u).pathname === expected; } catch (_) { return false; }
        });
        if (byHref) return abs(byHref);
      }
    }
    return '';
  }

  // PCM-EXT-08: دکمهٔ «آیه بعد» (onclick=viewer(S,A)) را در DOM پیدا کن و آدرس hash بعدی را بساز.
  // مخصوص SPAهای hash-based مثل تفسیر نور (gharaati.ir): «بعد» لینک نیست بلکه <input> با
  // viewer(S,A) است؛ آدرس بعدی = پایهٔ فعلی + #numsooreh=S&numayeh=A.
  // PCM-EXT-08.1: اگر دکمهٔ «آیه بعد» نباشد (ته سوره — فقط «آیه قبل» هست)، از خود آدرس
  // جلو می‌رود: numsooreh از hash فعلی +۱ و numayeh=1 — مگر سورهٔ ۱۱۴ باشد (ته قرآن)
  // که در آن صورت '' برمی‌گرداند و خواندن تمیز تمام می‌شود.
  function hashNextUrl() {
    let btns = [];
    try { btns = Array.from(document.querySelectorAll('input,button,a')); } catch (_) { btns = []; }
    for (let i = 0; i < btns.length; i += 1) {
      const el = btns[i];
      const oc = String(el.getAttribute('onclick') || '');
      const m = oc.match(/viewer\(\s*(\d+)\s*,\s*(\d+)\s*\)/);
      if (!m) continue;
      const label = String(el.value != null ? el.value : (el.innerText || el.textContent) || '').replace(/\s+/g, ' ').trim();
      if (label && label.indexOf('آیه بعد') === -1) continue;
      const base = String(location.href).split('#')[0];
      return base + '#numsooreh=' + m[1] + '&numayeh=' + m[2];
    }
    // ته سوره: «آیه بعد» نیست → سورهٔ بعد از خود آدرس: numsooreh+1, numayeh=1.
    try {
      const hash = String(location.hash || '').replace(/^#/, '');
      const s = hash.match(/(?:^|&|\?)numsooreh=(\d+)/);
      if (s) {
        const cur = parseInt(s[1], 10);
        if (cur >= 1 && cur < 114) {
          return String(location.href).split('#')[0] + '#numsooreh=' + (cur + 1) + '&numayeh=1';
        }
      }
    } catch (_) {}
    return '';
  }

  // PCM-EXT-10 (v3.13): اگر اجرای این پروژه «توقف» شده باشد و موقعیت ذخیره‌شده
  // (nextUrl) در pctRun مانده باشد، می‌توان از همان‌جا ادامه داد.
  const isResumableRun = () => !!(runState && !runState.active && project &&
    runState.projectId === project.id && runState.nextUrl && project.status === 'paused');

  async function refreshRunState() {
    const st = await chrome.storage.local.get('pctRun');
    runState = st.pctRun || null;
    if (!project) return;
    const btn = $('test');
    const note = $('runNote');
    $('restartRow').style.display = 'none';
    if (runState?.active && runState.projectId === project.id) {
      btn.disabled = true;
      btn.textContent = 'در حال خواندن…';
      note.style.display = 'none';
    } else if (runState?.active) {
      btn.disabled = false;
      btn.textContent = 'آزمایش و شروع';
      note.textContent = `پروژهٔ ${runState.projectId} در حال خواندن است — برای شروع این پروژه اول «توقف» را بزن.`;
      note.style.display = 'block';
    } else if (lockLiveByOther()) {
      // PCM-EXT-03: lock زنده در بک‌اند از یک مرورگر/دستگاه دیگر.
      btn.disabled = true;
      btn.textContent = 'در حال خواندن (دستگاه دیگر)';
      note.textContent = 'این پروژه همین حالا توسط نشست دیگری (مرورگر/دستگاه دیگر) در حال خواندن است — شروع ممکن نیست.';
      note.style.display = 'block';
    } else if (isResumableRun()) {
      btn.disabled = false;
      btn.textContent = 'ادامه (از جای ذخیره‌شده)';
      $('restartRow').style.display = 'flex';
      note.textContent = `آخرین خواندن این پروژه متوقف شد — «ادامه» از ${runState.nextUrl} ادامه می‌دهد. برای شروع از همین صفحه، «شروع از نو» را بزن.`;
      note.style.display = 'block';
    } else {
      btn.disabled = false;
      btn.textContent = 'آزمایش و شروع';
      note.style.display = 'none';
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
    const st = await chrome.storage.local.get('pctRun');
    if (st.pctRun?.active) {
      if (st.pctRun.projectId === project.id) {
        report('این پروژه همین حالا در حال خواندن است — برای ایستادن «توقف» را بزن.');
        return { ok: false, message: 'already running' };
      }
      report(`پروژهٔ ${st.pctRun.projectId} در حال خواندن است — اول «توقف» را بزن.`);
      return { ok: false, message: 'another project running' };
    }
    // PCM-EXT-03: قفل بین‌مرورگری (claim در startReading مرجع نهایی است؛
    // این چک فقط پیام سریع به کاربر می‌دهد).
    if (lockLiveByOther()) {
      report('این پروژه همین حالا توسط نشست دیگری در حال خواندن است — صبر کن یا آن را متوقف کن.');
      return { ok: false, message: 'locked by another session' };
    }
    try {
      await saveRule();
    } catch (e) {
      report(String(e));
      return { ok: false, message: String(e) };
    }
    const result = await extract(project.points, project.id, project.next_param || '');
    render();
    if (!result.ok) {
      report(result.message || 'آزمایش ناموفق بود');
      return result;
    }
    const preview = Object.entries(result.values).map(([k, v]) => `${k}: ${String(v || '').slice(0, 60)}`).join(' | ');
    if (!project.next_param) {
      report(`صفحه ذخیره شد. قانون صفحه بعد را بنویس تا خواندن ادامه پیدا کند. ${preview}`);
      return { ok: true, started: false, message: reportText(), values: result.values };
    }
    const spec = String(project.next_param || '');
    let nextNote = '';
    if (spec === 'next-link' || spec.indexOf('next-link:') === 0) {
      nextNote = result.nextUrl
        ? ` — لینک بعدی: ${result.nextUrl}`
        : ' — هشدار: لینک صفحه بعد روی این صفحه پیدا نشد؛ برای کشفش صفحه اول دوباره خوانده می‌شود.';
    } else if (spec === 'hash') {
      nextNote = result.nextUrl
        ? ` — آیهٔ بعد: ${result.nextUrl}`
        : ' — هشدار: دکمهٔ «آیه بعد» روی این صفحه پیدا نشد (شاید آخر سوره باشد).';
    } else if (spec === 'path-number') {
      // PCM-EXT-09: پیشروی از خود آدرس می‌آید (نه DOM)؛ بعدی را همین‌جا
      // محاسبه کن تا کاربر در آزمایش ببیند.
      try {
        nextNote = ` — صفحهٔ بعد: ${advancePreview('path-number', result.url, project.next_step)}`;
      } catch (e) {
        nextNote = ' — هشدار: ' + e.message;
      }
    }
    const started = await chrome.runtime.sendMessage({
      action: 'startReading',
      projectId: project.id,
      pagesPerMinute: project.pages_per_minute,
      nextUrl: result.nextUrl || '',
    });
    report(started?.ok ? `${started.message}${nextNote} — ${preview}` : (started?.message || preview));
    if (started?.ok) $('step4').classList.add('on');
    refreshRunState();
    return { ok: !!started?.ok, started: !!started?.ok, message: $('report').textContent, values: result.values };
  }

  // PCM-EXT-10 (v3.13): ادامهٔ اجرای متوقف‌شده از nextUrl ذخیره‌شده (stopReading آن را
  // در pctRun نگه می‌دارد). اول تنظیمات فعلی فورم را ذخیره می‌کند (پس ویرایش‌های
  // کاربر اعمال می‌شوند)، بعد خواندن را از همان موقعیت ادامه می‌دهد.
  async function resumeRun() {
    if (!project?.id) {
      report('اول از اکستنشن پروژه را بساز');
      return { ok: false, message: 'پروژه‌ای انتخاب نشده' };
    }
    const st = await chrome.storage.local.get('pctRun');
    const run = st.pctRun;
    if (!run?.nextUrl || run.projectId !== project.id) {
      report('موقعیت ذخیره‌شده‌ای برای ادامه پیدا نشد — «شروع از نو» را بزن.');
      return testAndStart();
    }
    if (run.active) {
      report('این پروژه همین حالا در حال خواندن است.');
      return { ok: false, message: 'already running' };
    }
    if (lockLiveByOther()) {
      report('این پروژه همین حالا توسط نشست دیگری در حال خواندن است — صبر کن یا آن را متوقف کن.');
      return { ok: false, message: 'locked by another session' };
    }
    try {
      await saveRule();
    } catch (e) {
      report(String(e));
      return { ok: false, message: String(e) };
    }
    const started = await chrome.runtime.sendMessage({
      action: 'startReading',
      projectId: project.id,
      pagesPerMinute: project.pages_per_minute,
      nextUrl: run.nextUrl,
    });
    report(started?.ok ? `ادامه از: ${run.nextUrl} — ${started.message}` : (started?.message || 'ادامه ممکن نشد'));
    if (started?.ok) $('step4').classList.add('on');
    refreshRunState();
    return { ok: !!started?.ok, started: !!started?.ok, message: started?.message || '' };
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
  // PCM-EXT-10 (v3.13): وقتی اجرای متوقف‌شده‌ای با موقعیت ذخیره‌شده هست، دکمهٔ اصلی
  // «ادامه» می‌شود؛ «شروع از نو» همیشه از همین صفحه آزمایش می‌کند.
  $('test').addEventListener('click', () => (isResumableRun() ? resumeRun() : testAndStart()));
  $('restart').addEventListener('click', () => testAndStart());
  // ذخیرهٔ تنظیمات حتی حین خواندن: حلقهٔ run هر دقیقه پروژه را دوباره می‌خواند،
  // پس شرط توقف/روش صفحه بعدِ تازه از دقیقهٔ بعد اعمال می‌شود.
  $('saveSettings').addEventListener('click', async () => {
    if (!project?.id) { report('اول پروژه را انتخاب کن'); return; }
    try {
      const saved = await saveRule();
      report(saved ? 'تنظیمات ذخیره شد — حلقهٔ خواندن از دقیقهٔ بعد از آن‌ها استفاده می‌کند.' : 'ذخیره نشد');
    } catch (e) { report(String(e)); }
  });
  $('stop').addEventListener('click', async () => {
    const resp = await chrome.runtime.sendMessage({ action: 'stopReading' });
    report(resp?.message || 'توقف شد');
    if (project?.id) await load(project.id).catch(() => {});
    refreshRunState();
  });
  $('source').addEventListener('change', () => { picking = $('source').value === 'css' && $('form').style.display === 'block'; });
  $('nextMode').addEventListener('change', updateNextDetail);

  // PCM-EXT-08: export فقط برای تست (extension/test_hash_next.js).
  window.__pctHashNext = hashNextUrl;

  chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
    if (message.action === 'openProject') {
      openPanel();
      load(message.projectId).then(() => {
        if (!project.next_param) {
          const keys = [...new URLSearchParams(location.search).keys()];
          if (keys.length) {
            $('nextMode').value = 'param';
            $('nextDetailInput').value = keys[0];
            updateNextDetail();
          }
        }
        refreshRunState();
        sendResponse({ ok: true });
      }).catch((e) => sendResponse({ ok: false, message: String(e) }));
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
      extract(message.points || project?.points || [], message.projectId, message.nextSpec).then(sendResponse);
      return true;
    }
    if (message.action === 'ping') {
      sendResponse({ ok: true, picker: true });
      return true;
    }
    return false;
  });
})();

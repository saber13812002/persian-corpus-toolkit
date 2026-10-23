// UI-side tests for the create-project / ComboBox logic in popup.js (PCM-01).
// Runs the real popup.js in a sandbox with stubbed chrome.* + minimal DOM and
// a controllable fetch. Covers T03 (auto-select), T04 (reopen), T05 (reload),
// T07 (empty name), T08 (backend down), T10 (double-click guard), T11
// (POST ok but list refresh fails).
//
// Run: node test_popup.js
"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const assert = require("assert");

const BACKEND = "https://corpus.ai.ismc.ir";

// ---- minimal DOM stub -----------------------------------------------------
function makeElement(id) {
  const children = [];
  const el = {
    id,
    value: "",
    textContent: "",
    className: "",
    style: {},
    disabled: false,
    innerHTML: "",
    _options: [],
    focus() {},
    addEventListener() {},
    appendChild(o) { children.push(o); return o; },
    prepend(o) { children.unshift(o); return o; },
    removeChild(o) { const i = children.indexOf(o); if (i >= 0) children.splice(i, 1); },
    querySelector() { return null; },
  };
  Object.defineProperty(el, "children", { get: () => children });
  Object.defineProperty(el, "lastChild", { get: () => (children.length ? children[children.length - 1] : null) });
  // classList used by selectSite
  el.classList = {
    toggle() {},
    add() {},
    remove() {},
    contains: () => false,
  };
  return el;
}
function makeSelect(id) {
  const el = makeElement(id);
  // el._options is the live options array (makeElement already set it to [])
  Object.defineProperty(el, "options", {
    get() { return el._options; },
  });
  // innerHTML = '' must clear options
  let _html = "";
  Object.defineProperty(el, "innerHTML", {
    get() { return _html; },
    set(v) {
      _html = v;
      if (v === "") el._options.length = 0;
    },
  });
  el.appendChild = function (o) { this._options.push(o); return o; };
  el.querySelector = function (sel) {
    const m = sel.match(/value="(.+)"/);
    if (!m) return null;
    return this._options.find((o) => o.value === m[1]) || null;
  };
  return el;
}

function makeDocument(els) {
  return {
    addEventListener() {},
    hidden: false,
    getElementById(id) {
      if (!els[id]) els[id] = id === "projectSelect" ? makeSelect(id) : makeElement(id);
      return els[id];
    },
    createElement(tag) {
      const o = makeElement("option");
      o.tagName = tag;
      return o;
    },
  };
}

// ---- chrome stub ----------------------------------------------------------
function makeChrome({ activeTabUrl = "https://tasnim.hamtaa.org/payload?item_index=5" } = {}) {
  const storage = {};
  return {
    _storage: storage,
    tabs: {
      query: async () => [{ id: 1, url: activeTabUrl }],
      create: async () => ({}),
    },
    storage: {
      local: {
        get: async (key) => {
          if (typeof key === "string") return { [key]: storage[key] };
          const out = {};
          (Array.isArray(key) ? key : [key]).forEach((k) => { if (k in storage) out[k] = storage[k]; });
          return out;
        },
        set: async (obj) => Object.assign(storage, obj),
      },
    },
    runtime: {
      sendMessage: () => {},
      lastError: null,
      onMessage: { addListener() {} },
      onStartup: { addListener() {} },
      onInstalled: { addListener() {} },
    },
    alarms: { create() {}, clear() {}, onAlarm: { addListener() {} } },
  };
}

// ---- load popup.js into a sandbox with stubs -----------------------------
function loadPopup({ fetchImpl, activeTabUrl } = {}) {
  const els = {};
  const document = makeDocument(els);
  const chrome = makeChrome({ activeTabUrl });
  const sandbox = {
    document,
    chrome,
    fetch: fetchImpl,
    URL,
    console,
    setTimeout,
    clearTimeout,
    setInterval: () => 0,
    clearInterval: () => {},
    confirm: () => false,
    Number,
    Array,
    Object,
    String,
    Date,
  };
  // make (0).toLocaleString('fa-IR') work inside the sandbox
  sandbox.Number.prototype.toLocaleString = () => "0";
  sandbox.Date.prototype.toLocaleTimeString = () => "12:00:00";
  sandbox.window = sandbox;
  vm.createContext(sandbox);
  const code = fs.readFileSync(path.join(__dirname, "popup.js"), "utf8");
  vm.runInContext(code, sandbox);
  return { sandbox, document, chrome, els };
}

function jsonOk(obj) {
  return { ok: true, status: 200, json: async () => obj };
}
function jsonErr(status, body) {
  return { ok: false, status, json: async () => body };
}

async function run() {
  let passed = 0, failed = 0;
  const t = async (name, fn) => {
    try { await fn(); passed++; console.log("PASS", name); }
    catch (e) { failed++; console.log("FAIL", name, "-", e.message); }
  };

  // T07 — empty name: no POST, report shows the warning
  await t("T07 empty name rejected (no POST, warn shown)", async () => {
    let posts = 0;
    const { els, sandbox } = loadPopup({
      fetchImpl: async () => { posts++; return jsonOk({ projects: [] }); },
    });
    els.projectName = makeElement("projectName");
    els.projectName.value = "   ";
    els.projectSelect = makeSelect("projectSelect");
    await sandbox.createProject();
    assert.strictEqual(posts, 0, "must not POST with empty name");
    assert.ok(/نام پروژه/.test(els.reportText.textContent), "warn shown: " + els.reportText.textContent);
  });

  // T10 — double-click guard: second click while first in-flight is ignored
  await t("T10 double-click guard (only one POST)", async () => {
    let posts = 0;
    let release;
    const gate = new Promise((r) => (release = r));
    const { els, sandbox } = loadPopup({
      fetchImpl: async (url) => {
        if (String(url).includes("api/projects?")) return jsonOk({ projects: [] });
        posts++;
        await gate; // hold the POST in-flight
        return jsonOk({ ok: true, project: { id: 7, name: "X", host: "h" } });
      },
    });
    els.projectName = makeElement("projectName");
    els.projectName.value = "Dup";
    els.projectSelect = makeSelect("projectSelect");
    const p1 = sandbox.createProject();
    await new Promise((r) => setTimeout(r, 5)); // let first click start
    await sandbox.createProject(); // second click while in-flight
    await sandbox.createProject(); // third
    release();
    await p1;
    assert.strictEqual(posts, 1, "exactly one POST despite 3 clicks");
  });

  // T03 — auto-select: after create, the new id is the selected option
  await t("T03 new project auto-selected in ComboBox", async () => {
    const { els, sandbox } = loadPopup({
      fetchImpl: async (url) => {
        const u = String(url);
        if (u.includes("api/projects?")) return jsonOk({ projects: [{ id: 11, name: "N", points: [] }] });
        if (u.includes("api/projects") && u.endsWith("api/projects")) return jsonOk({ ok: true, project: { id: 11, name: "N" } });
        return jsonOk({ projects: [] });
      },
    });
    els.projectName = makeElement("projectName");
    els.projectName.value = "N";
    els.projectSelect = makeSelect("projectSelect");
    await sandbox.createProject();
    assert.strictEqual(els.projectSelect.value, "11", "selected value must be new id");
  });

  // T04 — reopen: stored pctProjectId restored into selection
  await t("T04 reopen restores stored selection", async () => {
    const { els, sandbox, chrome } = loadPopup({
      fetchImpl: async (url) => {
        if (String(url).includes("api/projects?"))
          return jsonOk({ projects: [{ id: 11, name: "N", points: [] }, { id: 12, name: "M", points: [] }] });
        return jsonOk({ projects: [] });
      },
    });
    // pre-seed stored selection (simulates a previous create)
    await chrome.storage.local.set({ pctProjectId: 12 });
    els.projectSelect = makeSelect("projectSelect");
    await sandbox.loadProjects();
    assert.strictEqual(els.projectSelect.value, "12", "stored selection restored");
  });

  // T05 — reload extension: list rebuilt from backend, stored selection kept
  await t("T05 reload rebuilds list and keeps selection (no dup options)", async () => {
    const { els, sandbox, chrome } = loadPopup({
      fetchImpl: async (url) => {
        if (String(url).includes("api/projects?"))
          return jsonOk({ projects: [{ id: 5, name: "A", points: [] }, { id: 6, name: "B", points: [] }] });
        return jsonOk({ projects: [] });
      },
    });
    await chrome.storage.local.set({ pctProjectId: 5 });
    const sel = makeSelect("projectSelect");
    els.projectSelect = sel;
    await sandbox.loadProjects();
    // no duplicate options
    const vals = sel._options.map((o) => o.value);
    assert.strictEqual(new Set(vals).size, vals.length, "no duplicate options");
    assert.strictEqual(sel.value, "5", "selection restored after reload");
    // second load (e.g. visibility refresh) must not create dups
    await sandbox.loadProjects();
    const vals2 = sel._options.map((o) => o.value);
    assert.strictEqual(new Set(vals2).size, vals2.length, "still no dups after 2nd load");
  });

  // T08 — backend down: fetch throws, no fake success, clear message
  await t("T08 backend down -> clear error, no fake success", async () => {
    const { els, sandbox } = loadPopup({
      fetchImpl: async () => { throw new Error("Failed to fetch"); },
    });
    els.projectName = makeElement("projectName");
    els.projectName.value = "X";
    els.projectSelect = makeSelect("projectSelect");
    await sandbox.createProject();
    const msg = els.reportText.textContent;
    assert.ok(/خوانده نشد|Failed to fetch|خطا/.test(msg), "clear error shown: " + msg);
    assert.ok(!/ساخته شد/.test(msg), "no fake success");
  });

  // T11 — POST ok but list refresh fails: must NOT report clean success
  await t("T11 POST ok but list refresh fails -> ambiguous message, not clean success", async () => {
    let listCalls = 0;
    const { els, sandbox } = loadPopup({
      fetchImpl: async (url) => {
        const u = String(url);
        if (u.includes("api/projects?")) { listCalls++; throw new Error("refresh failed"); }
        if (u.endsWith("api/projects")) return jsonOk({ ok: true, project: { id: 21, name: "Z" } });
        return jsonOk({ projects: [] });
      },
    });
    els.projectName = makeElement("projectName");
    els.projectName.value = "Z";
    els.projectSelect = makeSelect("projectSelect");
    await sandbox.createProject();
    const msg = els.reportText.textContent;
    assert.ok(/ثبت شد/.test(msg), "says it was registered: " + msg);
    assert.ok(/نخوانده|باز کن/.test(msg), "says list not refreshed: " + msg);
    assert.ok(!/هالا نقطه/.test(msg), "not the clean success message");
  });

  // parseProjectResponse: 404 -> outdated message
  await t("404 maps to 'backend outdated' message", async () => {
    const { sandbox } = loadPopup({ fetchImpl: async () => jsonOk({ projects: [] }) });
    let caught = "";
    try { await sandbox.parseProjectResponse(jsonErr(404, {}), "x"); } catch (e) { caught = e.message; }
    assert.ok(/قدیمی|404|deploy/.test(caught), "404 -> outdated msg: " + caught);
  });

  console.log(`\n${passed} passed, ${failed} failed`);
  process.exit(failed ? 1 : 0);
}

run().catch((e) => { console.error(e); process.exit(1); });

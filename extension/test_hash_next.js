// Node tests for hashNextUrl() in content_picker.js (PCM-EXT-08).
// The "next page" of hash-based SPAs (tafsir gharaati) is not an <a> link but
// an <input onClick="viewer(S,A)" value="آیه بعد"> button; the next address is
// base + #numsooreh=S&numayeh=A.
"use strict";
const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

function makeElement() {
  return {
    id: "",
    value: "",
    textContent: "",
    innerText: "",
    style: {},
    children: [],
    classList: { add() {}, remove() {}, toggle() {}, contains() { return false; } },
    appendChild(c) { this.children.push(c); return c; },
    append(...c) { this.children.push(...c); },
    addEventListener() {},
    focus() {},
    contains() { return false; },
    querySelector() { return null; },
    getAttribute() { return null; },
    setAttribute() {},
    remove() {},
  };
}

// A fake input/button carrying the onClick attribute from the real site.
function btn(onclick, value) {
  const el = makeElement();
  el._oc = onclick;
  el.value = value == null ? "" : String(value);
  el.innerText = el.value;
  el.textContent = el.value;
  el.getAttribute = (n) => (n === "onclick" ? el._oc : null);
  return el;
}

// Load content_picker.js in a vm with a minimal DOM + location stub.
function loadPicker({ href, buttons = [] } = {}) {
  const els = new Map();
  const shadow = {
    _html: "",
    set innerHTML(v) { this._html = v; },
    get innerHTML() { return this._html; },
    getElementById(id) {
      if (!els.has(id)) els.set(id, makeElement());
      return els.get(id);
    },
  };
  const document = {
    createElement: () => {
      const el = makeElement();
      el.attachShadow = () => shadow;
      return el;
    },
    querySelectorAll: (sel) => (sel === "input,button,a" ? buttons.slice() : []),
    addEventListener() {},
    documentElement: makeElement(),
  };
  const chrome = {
    runtime: { onMessage: { addListener() {} }, sendMessage: async () => ({ ok: true }) },
    storage: { local: { get: async () => ({}), set: async () => {} } },
  };
  const location = {
    href,
    search: "",
    hash: href.includes("#") ? href.split("#").slice(1).join("#") : "",
  };
  const sandbox = {
    window: {},
    document,
    chrome,
    location,
    console,
    setTimeout,
    clearTimeout,
    setInterval: () => 0,
    clearInterval: () => {},
    URL,
    URLSearchParams,
    CSS: { escape: (s) => s },
    fetch: async () => { throw new Error("no network in test"); },
  };
  vm.createContext(sandbox);
  vm.runInContext(fs.readFileSync(path.join(__dirname, "content_picker.js"), "utf8"), sandbox, {
    filename: "content_picker.js",
  });
  return sandbox;
}

let passed = 0;
let failed = 0;
const t = async (name, fn) => {
  try {
    await fn();
    passed++;
    console.log("PASS", name);
  } catch (e) {
    failed++;
    console.log("FAIL", name, "-", e.message);
  }
};

const BASE = "https://gharaati.ir/تفسیر-نور/";

(async () => {
  await t("content page: آیه بعد button -> next hash url", () => {
    const s = loadPicker({
      href: BASE + "#numsooreh=2&numayeh=8",
      buttons: [btn("viewer(2,7)", "آیه قبل"), btn("viewer(2,9)", "آیه بعد")],
    });
    assert.strictEqual(s.window.__pctHashNext(), BASE + "#numsooreh=2&numayeh=9");
  });

  await t("prefers آیه بعد over آیه قبل when both present (2:8 -> 2:9)", () => {
    const s = loadPicker({
      href: BASE + "#numsooreh=2&numayeh=8",
      buttons: [btn("viewer(2,7)", "آیه قبل"), btn("viewer(2,9)", "آیه بعد")],
    });
    assert.strictEqual(s.window.__pctHashNext(), BASE + "#numsooreh=2&numayeh=9");
  });

  await t("first content page: 1:1 -> آیه بعد viewer(1,2)", () => {
    const s = loadPicker({
      href: BASE + "#numsooreh=1&numayeh=1",
      buttons: [btn("viewer(1,2)", "آیه بعد")],
    });
    assert.strictEqual(s.window.__pctHashNext(), BASE + "#numsooreh=1&numayeh=2");
  });

  await t("surah end (only آیه قبل) -> next surah, numayeh=1 (1:7 -> 2:1)", () => {
    const s = loadPicker({
      href: BASE + "#numsooreh=1&numayeh=7",
      buttons: [btn("viewer(1,6)", "آیه قبل")],
    });
    assert.strictEqual(s.window.__pctHashNext(), BASE + "#numsooreh=2&numayeh=1");
  });

  await t("final surah 114 end (no آیه بعد, no numsooreh=115) -> empty (run ends)", () => {
    const s = loadPicker({
      href: BASE + "#numsooreh=114&numayeh=6",
      buttons: [btn("viewer(114,5)", "آیه قبل")],
    });
    assert.strictEqual(s.window.__pctHashNext(), "");
  });

  await t("no hash params at all and no button -> empty", () => {
    const s = loadPicker({ href: BASE, buttons: [] });
    assert.strictEqual(s.window.__pctHashNext(), "");
  });

  await t("آیه بعد button wins over the surah-end fallback", () => {
    const s = loadPicker({
      href: BASE + "#numsooreh=2&numayeh=8",
      buttons: [btn("viewer(2,7)", "آیه قبل"), btn("viewer(2,9)", "آیه بعد")],
    });
    assert.strictEqual(s.window.__pctHashNext(), BASE + "#numsooreh=2&numayeh=9");
  });

  await t("viewer() button with a different label is skipped", () => {
    const s = loadPicker({
      href: BASE + "#numsooreh=2&numayeh=8",
      buttons: [btn("viewer(2,99)", "مشاهده"), btn("viewer(2,9)", "آیه بعد")],
    });
    assert.strictEqual(s.window.__pctHashNext(), BASE + "#numsooreh=2&numayeh=9");
  });

  await t("viewer() with spaces around args still matches", () => {
    const s = loadPicker({
      href: BASE + "#numsooreh=114&numayeh=2715",
      buttons: [btn("viewer( 114 , 2716 )", "آیه بعد")],
    });
    assert.strictEqual(s.window.__pctHashNext(), BASE + "#numsooreh=114&numayeh=2716");
  });

  await t("no buttons at all -> surah-end fallback (3:1 -> 4:1)", () => {
    const s = loadPicker({ href: BASE + "#numsooreh=3&numayeh=1", buttons: [] });
    assert.strictEqual(s.window.__pctHashNext(), BASE + "#numsooreh=4&numayeh=1");
  });

  await t("placeholder page (2:1): only button is آیه بعد -> viewer(2,8)", () => {
    const s = loadPicker({
      href: BASE + "#numsooreh=2&numayeh=1",
      buttons: [btn("viewer(2,8)", "آیه بعد")],
    });
    assert.strictEqual(s.window.__pctHashNext(), BASE + "#numsooreh=2&numayeh=8");
  });

  await t("base keeps persian path, old hash is replaced", () => {
    const s = loadPicker({
      href: BASE + "#numsooreh=3&numayeh=5",
      buttons: [btn("viewer(3,6)", "آیه بعد")],
    });
    assert.strictEqual(s.window.__pctHashNext(), BASE + "#numsooreh=3&numayeh=6");
  });

  console.log(`\n${passed} passed, ${failed} failed`);
  process.exit(failed ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(1); });

// Node tests for the next-page strategies in background.js (no chrome needed).
// Load background.js in a vm sandbox with a stubbed chrome.* and exercise the
// pure URL logic: parseNextSpec / bumpNumber / advanceUrl for all four modes.
//
// Run: node extension/test_next.js
"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const assert = require("assert");

function makeChrome() {
  const noop = () => {};
  return {
    runtime: {
      onMessage: { addListener: noop },
      onStartup: { addListener: noop },
      onInstalled: { addListener: noop },
      sendMessage: noop,
      lastError: null,
    },
    tabs: {
      onUpdated: { addListener: noop },
      onRemoved: { addListener: noop },
      query: async () => [],
      create: async () => ({}),
      update: async () => {},
      sendMessage: noop,
    },
    storage: { local: { get: async () => ({}), set: async () => {} } },
    alarms: { onAlarm: { addListener: noop }, create: noop, clear: noop },
    scripting: { executeScript: async () => {} },
  };
}

const sandbox = {
  chrome: makeChrome(),
  console,
  setTimeout,
  clearTimeout,
  URL,
  fetch: async () => { throw new Error("no network in test"); },
};
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(path.join(__dirname, "background.js"), "utf8"), sandbox, {
  filename: "background.js",
});

const advanceUrl = sandbox.advanceUrl;
const parseNextSpec = sandbox.parseNextSpec;
const bumpNumber = sandbox.bumpNumber;
// PCM-20.10
const parseStopSpec = sandbox.parseStopSpec;
const pageNumberOf = sandbox.pageNumberOf;
const checkStopUrl = sandbox.checkStopUrl;
// PCM-EXT-04
const contentSignature = sandbox.contentSignature;
const sigHash = sandbox.sigHash;
const updateSameStreak = sandbox.updateSameStreak;
// PCM-EXT-08
const hashNumber = sandbox.hashNumber;

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
const throws = (fn, re) => {
  try {
    fn();
  } catch (e) {
    if (re && !re.test(e.message)) throw new Error("wrong error: " + e.message);
    return;
  }
  throw new Error("expected throw");
};
// Objects returned from the vm sandbox carry a different-realm prototype,
// which makes deepStrictEqual fail even when structure is identical.
// JSON round-trip normalizes them before comparing.
const specEq = (actual, expected) =>
  assert.deepStrictEqual(JSON.parse(JSON.stringify(actual)), expected);

(async () => {
  // ---- parseNextSpec -------------------------------------------------------
  await t("spec: empty -> none", () =>
    specEq(parseNextSpec({ next_param: "" }), { kind: "none" }));
  await t("spec: legacy param name", () =>
    specEq(parseNextSpec({ next_param: "item_index" }), { kind: "param", param: "item_index" }));
  await t("spec: next-link plain", () =>
    specEq(parseNextSpec({ next_param: "next-link" }), { kind: "nextLink", selector: "" }));
  await t("spec: next-link:selector", () =>
    specEq(parseNextSpec({ next_param: "next-link:a[rel=next]" }), { kind: "nextLink", selector: "a[rel=next]" }));
  await t("spec: hash", () =>
    specEq(parseNextSpec({ next_param: "hash" }), { kind: "hash" }));
  await t("spec: url-number", () =>
    specEq(parseNextSpec({ next_param: "url-number" }), { kind: "number" }));
  await t("spec: regex:pattern", () =>
    specEq(parseNextSpec({ next_param: "regex:sh(\\d+)" }), { kind: "regex", pattern: "sh(\\d+)" }));

  // ---- mode: url_param (legacy) --------------------------------------------
  await t("param: ?item_index=5 -> 6", () =>
    assert.strictEqual(
      advanceUrl("https://tasnim.hamtaa.org/payload?item_index=5", { next_param: "item_index", next_step: 1 }),
      "https://tasnim.hamtaa.org/payload?item_index=6"));
  await t("param: step 2 -> 7", () =>
    assert.strictEqual(
      advanceUrl("https://x.test/a?item_index=5", { next_param: "item_index", next_step: 2 }),
      "https://x.test/a?item_index=7"));
  await t("param: missing param -> throw", () =>
    throws(() => advanceUrl("https://x.test/a", { next_param: "item_index", next_step: 1 }), /پارامتر/));
  await t("param: non-numeric -> throw", () =>
    throws(() => advanceUrl("https://x.test/a?item_index=ab", { next_param: "item_index", next_step: 1 }), /عدد/));

  // ---- mode: url-number -----------------------------------------------------
  const num = (url, step = 1) => advanceUrl(url, { next_param: "url-number", next_step: step });
  await t("number: p_ghazal-495.html -> 496", () =>
    assert.strictEqual(num("https://www.hafizonlove.com/divan/p_ghazal-495.html"),
      "https://www.hafizonlove.com/divan/p_ghazal-496.html"));
  await t("number: p_ghazal-001.html -> 002 (zero-pad kept)", () =>
    assert.strictEqual(num("https://www.hafizonlove.com/divan/p_ghazal-001.html"),
      "https://www.hafizonlove.com/divan/p_ghazal-002.html"));
  await t("number: p_ghazal-1.html -> 2 (no zero added)", () =>
    assert.strictEqual(num("https://www.hafizonlove.com/divan/p_ghazal-1.html"),
      "https://www.hafizonlove.com/divan/p_ghazal-2.html"));
  await t("number: ganjoor sh1 -> sh2", () =>
    assert.strictEqual(num("https://ganjoor.net/hafez/ghazal/sh1"), "https://ganjoor.net/hafez/ghazal/sh2"));
  await t("number: ganjoor sh495 -> sh496", () =>
    assert.strictEqual(num("https://ganjoor.net/hafez/ghazal/sh495"), "https://ganjoor.net/hafez/ghazal/sh496"));
  await t("number: sh099 -> sh100 (width kept)", () =>
    assert.strictEqual(num("https://ganjoor.net/hafez/ghazal/sh099"), "https://ganjoor.net/hafez/ghazal/sh100"));
  await t("number: sh999 -> sh1000 (width grows)", () =>
    assert.strictEqual(num("https://ganjoor.net/hafez/ghazal/sh999"), "https://ganjoor.net/hafez/ghazal/sh1000"));
  await t("number: last number wins (/book/2/page-15.html -> 16)", () =>
    assert.strictEqual(num("https://x.test/book/2/page-15.html"), "https://x.test/book/2/page-16.html"));
  await t("number: step 2 (sh3 -> sh5)", () =>
    assert.strictEqual(num("https://ganjoor.net/hafez/ghazal/sh3", 2), "https://ganjoor.net/hafez/ghazal/sh5"));
  await t("number: query string preserved", () =>
    assert.strictEqual(num("https://www.hafizonlove.com/divan/p_ghazal-1.html?print=1"),
      "https://www.hafizonlove.com/divan/p_ghazal-2.html?print=1"));
  await t("number: no digits in path -> throw", () =>
    throws(() => num("https://x.test/about"), /عدد/));

  // ---- mode: regex ----------------------------------------------------------
  const rex = (pattern, url, step = 1) =>
    advanceUrl(url, { next_param: "regex:" + pattern, next_step: step });
  await t("regex: p_ghazal-(\\d+)\\.html (495 -> 496)", () =>
    assert.strictEqual(rex("p_ghazal-(\\d+)\\.html", "https://www.hafizonlove.com/divan/p_ghazal-495.html"),
      "https://www.hafizonlove.com/divan/p_ghazal-496.html"));
  await t("regex: sh(\\d+) on sh1 -> sh2", () =>
    assert.strictEqual(rex("sh(\\d+)", "https://ganjoor.net/hafez/ghazal/sh1"), "https://ganjoor.net/hafez/ghazal/sh2"));
  await t("regex: zero-padded capture 001 -> 002", () =>
    assert.strictEqual(rex("p_ghazal-(\\d+)\\.html", "https://www.hafizonlove.com/divan/p_ghazal-001.html"),
      "https://www.hafizonlove.com/divan/p_ghazal-002.html"));
  await t("regex: no match -> throw", () =>
    throws(() => rex("sh(\\d+)", "https://ganjoor.net/hafez/madigh/1"), /همخوانی ندارد/));
  await t("regex: two groups -> throw", () =>
    throws(() => rex("(\\d+)/(\\d+)", "https://x.test/a/1/2"), /یک گروه/));
  await t("regex: non-numeric group -> throw", () =>
    throws(() => rex("([a-z]+)-495\\.html", "https://www.hafizonlove.com/divan/p_ghazal-495.html"), /عدد نیست/));
  await t("regex: invalid pattern -> throw", () =>
    throws(() => rex("(", "https://x.test/a"), /نامعتبر/));
  await t("regex: step 2", () =>
    assert.strictEqual(rex("sh(\\d+)", "https://ganjoor.net/hafez/ghazal/sh3", 2), "https://ganjoor.net/hafez/ghazal/sh5"));

  // ---- bumpNumber ------------------------------------------------------------
  await t("bump: 001 -> 002", () => assert.strictEqual(bumpNumber("001", 1), "002"));
  await t("bump: 1 -> 2", () => assert.strictEqual(bumpNumber("1", 1), "2"));
  await t("bump: 099 -> 100", () => assert.strictEqual(bumpNumber("099", 1), "100"));
  await t("bump: underflow -> throw", () => throws(() => bumpNumber("1", -5), /جلو نمی‌رود/));

  // ---- guards -----------------------------------------------------------------
  await t("next-link: advanceUrl refuses (needs DOM)", () =>
    throws(() => advanceUrl("https://x.test/a", { next_param: "next-link" }), /لینک/));
  await t("hash: advanceUrl refuses (needs DOM)", () =>
    throws(() => advanceUrl("https://gharaati.ir/تفسیر-نور/#numsooreh=1&numayeh=1", { next_param: "hash" }), /باز شدن صفحه/));
  await t("none: advanceUrl refuses", () =>
    throws(() => advanceUrl("https://x.test/a", { next_param: "" }), /ذخیره نشده/));

  // ---- PCM-20.10: stop rule -----------------------------------------------------
  await t("stop: empty stop_number -> null", () => {
    assert.strictEqual(parseStopSpec({ stop_number: "" }), null);
    assert.strictEqual(parseStopSpec({}), null);
    assert.strictEqual(parseStopSpec({ stop_number: "0" }), null);
    assert.strictEqual(parseStopSpec({ stop_number: "  " }), null);
  });
  await t("stop: numeric stop_number parsed", () => {
    assert.strictEqual(parseStopSpec({ stop_number: "495" }), 495);
    assert.strictEqual(parseStopSpec({ stop_number: " 7 " }), 7);
  });
  await t("stop: param mode page number from query", () => {
    const p = { next_param: "item_index", next_step: 1 };
    assert.strictEqual(pageNumberOf("https://tasnim.hamtaa.org/payload?file_id=10&item_index=69677", p), 69677);
    assert.strictEqual(pageNumberOf("https://x.test/a", p), null);
    assert.strictEqual(pageNumberOf("https://x.test/a?item_index=ab", p), null);
  });
  await t("stop: number mode page number from path", () => {
    const p = { next_param: "url-number", next_step: 1 };
    assert.strictEqual(pageNumberOf("https://ganjoor.net/hafez/ghazal/sh495", p), 495);
    assert.strictEqual(pageNumberOf("https://www.hafizonlove.com/divan/p_ghazal-001.html", p), 1);
    assert.strictEqual(pageNumberOf("https://x.test/about", p), null);
  });
  await t("stop: regex mode page number from capture", () => {
    const p = { next_param: "regex:sh(\\d+)", next_step: 1 };
    assert.strictEqual(pageNumberOf("https://ganjoor.net/hafez/ghazal/sh150", p), 150);
    assert.strictEqual(pageNumberOf("https://ganjoor.net/hafez/madigh/1", p), null);
  });
  await t("stop: no limit -> never done", () => {
    const p = { next_param: "url-number", stop_number: "" };
    specEq(checkStopUrl("https://ganjoor.net/hafez/ghazal/sh99999", p), { done: false });
  });
  await t("stop: below limit -> not done", () => {
    const p = { next_param: "url-number", stop_number: "495" };
    specEq(checkStopUrl("https://ganjoor.net/hafez/ghazal/sh494", p), { done: false });
  });
  await t("stop: at limit -> done (last page read)", () => {
    const p = { next_param: "url-number", stop_number: "495" };
    const r = checkStopUrl("https://ganjoor.net/hafez/ghazal/sh495", p);
    assert.strictEqual(r.done, true);
    assert.match(r.why, /رسید/);
  });
  await t("stop: over limit -> done (overshoot blocked)", () => {
    const p = { next_param: "url-number", stop_number: "495" };
    const r = checkStopUrl("https://ganjoor.net/hafez/ghazal/sh496", p);
    assert.strictEqual(r.done, true);
    assert.match(r.why, /عبور/);
  });
  await t("stop: param mode at limit (tasnim item_index)", () => {
    const p = { next_param: "item_index", stop_number: "70000" };
    assert.strictEqual(checkStopUrl("https://tasnim.hamtaa.org/payload?item_index=69999", p).done, false);
    assert.strictEqual(checkStopUrl("https://tasnim.hamtaa.org/payload?item_index=70000", p).done, true);
    assert.strictEqual(checkStopUrl("https://tasnim.hamtaa.org/payload?item_index=70001", p).done, true);
  });
  await t("stop: step 2 can overshoot -> still stops", () => {
    // step 2: sh494 -> sh496 crosses the 495 limit without landing on it
    const p = { next_param: "url-number", next_step: 2, stop_number: "495" };
    const r = checkStopUrl("https://ganjoor.net/hafez/ghazal/sh496", p);
    assert.strictEqual(r.done, true);
  });
  await t("stop: limit not applicable (no number) -> not done", () => {
    const p = { next_param: "url-number", stop_number: "495" };
    specEq(checkStopUrl("https://x.test/about", p), { done: false });
  });

  // ── PCM-EXT-08: hash-based pages (tafsir gharaati, #numsooreh=S&numayeh=A) ──
  await t("hashNumber: S*10000+A (2:8 -> 20008)", () => {
    assert.strictEqual(hashNumber("numsooreh=2&numayeh=8"), 20008);
    assert.strictEqual(hashNumber("numsooreh=1&numayeh=7"), 10007);
    assert.strictEqual(hashNumber("numsooreh=114&numayeh=2716"), 1142716);
  });
  await t("hashNumber: missing part -> null", () => {
    assert.strictEqual(hashNumber("numsooreh=2"), null);
    assert.strictEqual(hashNumber("numayeh=8"), null);
    assert.strictEqual(hashNumber(""), null);
    assert.strictEqual(hashNumber(null), null);
  });
  await t("hashNumber: extra params ignored", () => {
    assert.strictEqual(hashNumber("numsooreh=1&numayeh=7&keyword=خدا"), 10007);
  });
  await t("hashNumber: keys case-insensitive, non-numeric rejected", () => {
    assert.strictEqual(hashNumber("NUMSOOREH=2&NUMAYEH=8"), 20008);
    assert.strictEqual(hashNumber("numsooreh=a&numayeh=7"), null);
  });
  await t("stop: hash mode page number from URL hash", () => {
    const p = { next_param: "hash", next_step: 1 };
    assert.strictEqual(pageNumberOf("https://gharaati.ir/تفسیر-نور/#numsooreh=2&numayeh=8", p), 20008);
    assert.strictEqual(pageNumberOf("https://gharaati.ir/تفسیر-نور/#numsooreh=1&numayeh=1", p), 10001);
    assert.strictEqual(pageNumberOf("https://gharaati.ir/تفسیر-نور/", p), null);
  });
  await t("stop: hash at limit -> done", () => {
    const p = { next_param: "hash", stop_number: "20008" };
    const r = checkStopUrl("https://gharaati.ir/تفسیر-نور/#numsooreh=2&numayeh=8", p);
    assert.strictEqual(r.done, true);
    assert.match(r.why, /رسید/);
  });
  await t("stop: hash below limit -> not done", () => {
    const p = { next_param: "hash", stop_number: "20008" };
    assert.strictEqual(checkStopUrl("https://gharaati.ir/تفسیر-نور/#numsooreh=2&numayeh=7", p).done, false);
  });
  await t("stop: hash over limit -> done (overshoot blocked)", () => {
    const p = { next_param: "hash", stop_number: "20008" };
    const r = checkStopUrl("https://gharaati.ir/تفسیر-نور/#numsooreh=2&numayeh=9", p);
    assert.strictEqual(r.done, true);
    assert.match(r.why, /عبور/);
  });

  // ── PCM-EXT-09: path-number — only the numeric PATH SEGMENT advances ──
  const pnum = (url, step = 1) => advanceUrl(url, { next_param: "path-number", next_step: step });
  await t("spec: path-number", () =>
    specEq(parseNextSpec({ next_param: "path-number" }), { kind: "pathNumber" }));
  await t("pathnum: islam.se /questions/4/<slug> -> 5 (slug untouched)", () =>
    assert.strictEqual(
      pnum("https://islam.stackexchange.com/questions/4/what-is-the-purpose-of-having-the-concept-of-fasting-in-islam"),
      "https://islam.stackexchange.com/questions/5/what-is-the-purpose-of-having-the-concept-of-fasting-in-islam"));
  await t("pathnum: digits inside the slug are NOT touched", () =>
    assert.strictEqual(
      pnum("https://x.test/questions/4/what-is-page-9-of-vol-2"),
      "https://x.test/questions/5/what-is-page-9-of-vol-2"));
  await t("pathnum: zero-padded segment kept padded (04 -> 05)", () =>
    assert.strictEqual(pnum("https://x.test/qa/04/slug-a"), "https://x.test/qa/05/slug-a"));
  await t("pathnum: width grows when needed (09 -> 10)", () =>
    assert.strictEqual(pnum("https://x.test/qa/09/slug-a"), "https://x.test/qa/10/slug-a"));
  await t("pathnum: step 2 (4 -> 6)", () =>
    assert.strictEqual(pnum("https://islam.stackexchange.com/questions/4/abc", 2),
      "https://islam.stackexchange.com/questions/6/abc"));
  await t("pathnum: first numeric segment wins (/users/7/2024/notes)", () =>
    assert.strictEqual(pnum("https://x.test/users/7/2024/notes"), "https://x.test/users/8/2024/notes"));
  await t("pathnum: query string preserved", () =>
    assert.strictEqual(
      pnum("https://islam.stackexchange.com/questions/4/abc?tab=votes"),
      "https://islam.stackexchange.com/questions/5/abc?tab=votes"));
  await t("pathnum: hash fragment preserved", () =>
    assert.strictEqual(
      pnum("https://islam.stackexchange.com/questions/4/abc#comment-9"),
      "https://islam.stackexchange.com/questions/5/abc#comment-9"));
  await t("pathnum: no fully-numeric segment -> throw", () =>
    throws(() => pnum("https://x.test/questions/what-is-fast/"), /رجکس/));
  await t("pathnum: contrast with url-number (last number wins)", () =>
    assert.strictEqual(
      advanceUrl("https://x.test/book/2/page-15.html", { next_param: "url-number", next_step: 1 }),
      "https://x.test/book/2/page-16.html"));
  await t("pathnum: pageNumberOf from the numeric segment", () => {
    const p = { next_param: "path-number", next_step: 1 };
    assert.strictEqual(
      pageNumberOf("https://islam.stackexchange.com/questions/4/what-is-fasting", p), 4);
    assert.strictEqual(pageNumberOf("https://x.test/qa/04/slug-a", p), 4);
    assert.strictEqual(pageNumberOf("https://x.test/about", p), null);
  });
  await t("pathnum: stop rule at limit (5 -> stop before 6)", () => {
    const p = { next_param: "path-number", stop_number: "5" };
    const at = checkStopUrl("https://islam.stackexchange.com/questions/5/abc", p);
    assert.strictEqual(at.done, true);
    assert.match(at.why, /رسید/);
    assert.strictEqual(
      checkStopUrl("https://islam.stackexchange.com/questions/4/abc", p).done, false);
    const r = checkStopUrl("https://islam.stackexchange.com/questions/6/abc", p);
    assert.strictEqual(r.done, true);
    assert.match(r.why, /عبور/);
  });

  // ── PCM-EXT-04: توقف بر مبنای تکرار محتوا ─────────────────────────────
  await t("content: auto mode joins ALL values, sorted by key", () => {
    const p = { stop_field: "" };
    const s = contentSignature(p, { b: "۲", a: "۱", c: "۳" });
    assert.strictEqual(s, "۱\u0001۲\u0001۳");
  });
  await t("content: auto mode ignores stop_field when empty", () => {
    const p = {};
    assert.strictEqual(contentSignature(p, { x: "only" }), "only");
  });
  await t("content: selected field used when present in values", () => {
    const p = { stop_field: "body" };
    assert.strictEqual(contentSignature(p, { body: "متن اصلی", title: "عنوان" }), "متن اصلی");
  });
  await t("content: selected field missing from values -> fallback to auto", () => {
    const p = { stop_field: "body" };
    assert.strictEqual(contentSignature(p, { title: "عنوان" }), "عنوان");
  });
  await t("content: null/undefined values become empty string", () => {
    const p = { stop_field: "" };
    assert.strictEqual(contentSignature(p, { a: null, b: undefined, c: "x" }), "\u0001\u0001x");
  });
  await t("content: different field selection -> different signature", () => {
    const vals = { body: "متن", title: "عنوان" };
    assert.notStrictEqual(
      contentSignature({ stop_field: "body" }, vals),
      contentSignature({ stop_field: "title" }, vals)
    );
  });
  await t("hash: deterministic", () => {
    assert.strictEqual(sigHash("متن یکسان"), sigHash("متن یکسان"));
  });
  await t("hash: distinct for different strings", () => {
    assert.notStrictEqual(sigHash("aaa"), sigHash("aab"));
    assert.notStrictEqual(sigHash(""), sigHash("x"));
  });
  await t("hash: returns string form", () => {
    assert.strictEqual(typeof sigHash("abc"), "string");
  });
  await t("streak: equal sig increments", () => {
    assert.strictEqual(updateSameStreak(0, "h", "h").streak, 1);
    assert.strictEqual(updateSameStreak(1, "h", "h").streak, 2);
    assert.strictEqual(updateSameStreak(9, "h", "h").streak, 10);
  });
  await t("streak: different sig resets to 1", () => {
    assert.strictEqual(updateSameStreak(9, "h1", "h2").streak, 1);
    assert.strictEqual(updateSameStreak(0, "", "first").streak, 1);
  });
  await t("streak: stop=true exactly at 10 (not at 9)", () => {
    assert.strictEqual(updateSameStreak(8, "h", "h").stop, false); // ->9
    assert.strictEqual(updateSameStreak(9, "h", "h").stop, true); // ->10
  });
  await t("streak: full 10-identical-page simulation", () => {
    let streak = 0;
    let last = "";
    let stopped = null;
    for (let i = 1; i <= 12 && stopped === null; i += 1) {
      const sig = sigHash(contentSignature({ stop_field: "body" }, { body: "همین متن" }));
      const r = updateSameStreak(streak, last, sig);
      last = sig;
      streak = r.streak;
      if (r.stop) stopped = i;
    }
    assert.strictEqual(stopped, 10); // دهمین صفحهٔ یکسان → توقف
  });
  await t("streak: change after 9 identical -> restart, no stop", () => {
    let streak = 0;
    let last = "";
    let stopped = false;
    for (let i = 0; i < 12; i += 1) {
      // ۹ صفحهٔ یکسان، بعد یه صفحهٔ متفاوت (reset)، بعد ادامه
      const sig = sigHash("page-" + (i === 9 ? "new" : "same"));
      const r = updateSameStreak(streak, last, sig);
      last = sig;
      streak = r.streak;
      if (r.stop) stopped = true;
    }
    assert.strictEqual(stopped, false);
  });

  console.log(`\n${passed} passed, ${failed} failed`);
  process.exit(failed ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(1); });

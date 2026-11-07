/* Tasnim Web V1 — minimal progressive enhancement (design system §6, §9)
 *
 * The site works fully with JavaScript disabled:
 *   - the pre-paint theme script in <head> applies the saved theme;
 *   - the metadata drawer is a native <details>;
 *   - all navigation is plain anchors (SSR);
 *   - search forms submit with method=get.
 *
 * This file only enhances, never replaces:
 *   - #theme-toggle  → persist theme choice (localStorage "tasnim-theme");
 *   - #font-minus/-plus/-reset → reader font size 16–24px
 *     (localStorage "tasnim-font-size", overrides --text-reading);
 *   - #meta-toggle   → aria-expanded sync with the native drawer.
 */
(function () {
  "use strict";

  function store(key, value) {
    try {
      if (value === undefined) return localStorage.getItem(key);
      localStorage.setItem(key, value);
      return value;
    } catch (e) {
      return value === undefined ? null : value;
    }
  }

  var root = document.documentElement;

  /* ---------- theme toggle ---------- */
  var toggle = document.getElementById("theme-toggle");

  function currentTheme() {
    return root.getAttribute("data-theme") === "dark" ? "dark" : "light";
  }

  function syncToggle() {
    if (!toggle) return;
    toggle.setAttribute("aria-pressed", currentTheme() === "dark" ? "true" : "false");
  }

  if (toggle) {
    toggle.addEventListener("click", function () {
      var next = currentTheme() === "dark" ? "light" : "dark";
      root.setAttribute("data-theme", next);
      store("tasnim-theme", next);
      syncToggle();
    });
    syncToggle();
  }

  /* ---------- reader font size (16–24px) ---------- */
  var MIN = 16;
  var MAX = 24;
  var reader = document.querySelector(".reader__text");
  var minus = document.getElementById("font-minus");
  var plus = document.getElementById("font-plus");
  var reset = document.getElementById("font-reset");

  function clamp(v) {
    return Math.min(MAX, Math.max(MIN, v));
  }

  function storedSize() {
    var v = parseInt(store("tasnim-font-size") || "", 10);
    return isFinite(v) ? clamp(v) : null;
  }

  function applySize(px) {
    if (px === null) {
      root.style.removeProperty("--text-reading");
    } else {
      root.style.setProperty("--text-reading", px + "px");
    }
  }

  function adjust(delta) {
    var cur = storedSize();
    if (cur === null) {
      // First adjustment: derive from the rendered default
      // (17px mobile / 19px desktop per the type scale).
      var cs = getComputedStyle(reader || document.body).fontSize;
      cur = parseInt(cs, 10);
      if (!isFinite(cur)) cur = 19;
      cur = clamp(cur);
    }
    var next = clamp(cur + delta);
    store("tasnim-font-size", String(next));
    applySize(next);
  }

  if (reader) {
    var s0 = storedSize();
    if (s0 !== null) applySize(s0);
  }
  if (minus) minus.addEventListener("click", function () { adjust(-1); });
  if (plus) plus.addEventListener("click", function () { adjust(1); });
  if (reset) reset.addEventListener("click", function () {
    store("tasnim-font-size", "");
    applySize(null);
  });

  /* ---------- metadata drawer: aria-expanded sync ---------- */
  var drawer = document.getElementById("metadata-drawer");
  var metaBtn = document.getElementById("meta-toggle");

  if (drawer && metaBtn) {
    function syncMeta() {
      metaBtn.setAttribute("aria-expanded", drawer.open ? "true" : "false");
    }
    metaBtn.addEventListener("click", function () {
      drawer.open = !drawer.open;
      syncMeta();
    });
    drawer.addEventListener("toggle", syncMeta);
    syncMeta();
  }
})();

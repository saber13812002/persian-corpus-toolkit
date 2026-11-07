# -*- coding: utf-8 -*-
"""Tasnim Web V1 — 12-step user-journey E2E (PCM-20.6.4, scope B14).

Walks the real v0003 product over plain HTTP like a user would: home →
volumes → volume detail → reader → real text → gap-aware next/prev →
Persian search → topic detail → honest surah page → metadata drawer →
mobile viewport checks. Stdlib only (plus a re-use of ``screenshot.py``
for the optional 375px browser captures).

Every step records PASS/FAIL with concrete evidence (status, bytes, the
exact markers matched). The full evidence is written to the gitignored
``tasnim/e2e/e2e-evidence.json``.

Usage (worktree root, server already running on :5071):
    python -X utf8 tasnim/e2e/e2e_scenario.py [--base http://127.0.0.1:5071]

Exit codes: 0 = all 12 steps PASS, 1 = one or more FAIL.

Known v0003 facts the assertions lean on (probed, real counters only):
  * work «تفسیر تسنیم», edition «خروجی کراول hamta-2026», 6 volumes
  * pages=45844, missing_item_index=45243, present_ratio≈50.3٪
  * vol047: 9391 pages, item_index 0..55698, own coverage row
    [3649..49956] 46308 (partial_other_volume); first page ii=0
  * global gap [3649..11182]: last-existing before = 3648, first-existing
    after = 11183 (both status ok)
  * topic «تفسیر» = t-bd4e94070cce, 1678 pages, 5 volumes, first ii=273
  * search «قرآن» → exact single-token FTS count
  * page ii=2: dup (vol001 rank0 / vol047 rank1), 1861 chars,
    captured_at 2026-10-25 16:50:40, source_page_id 11707
"""
import argparse
import datetime
import html
import json
import os
import re
import subprocess
import sys
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)  # allow re-using screenshot.py helpers

DEFAULT_BASE = "http://127.0.0.1:5071"
EVIDENCE_PATH = os.path.join(HERE, "e2e-evidence.json")

VOLUME_VOL047 = "tasnim_hamta__hamta-2026__vol047"
VOLUME_UNKNOWN = "tasnim_hamta__hamta-2026__volkeyd531f422"
TOPIC_TAFSIR = "t-bd4e94070cce"
SEARCH_Q = "قرآن"
PERSIAN = re.compile(u"[\u0600-\u06FF]")

# Surah names that must NOT appear on the honest "in progress" page.
NO_FABRICATED_SURAHS = ["فاتحه", "بقره", "آل عمران", "کهف", "واقعه", "ملك"]


# ---------------------------------------------------------------------------
# tiny http helper (same contract as smoke.py)
# ---------------------------------------------------------------------------

def http(base, path, headers=None, timeout=25):
    url = base.rstrip("/") + path
    req = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, {k: v for k, v in r.headers.items()}, r.read()
    except urllib.error.HTTPError as e:  # noqa: F821
        body = e.read() if e.fp else b""
        return e.code, {k: v for k, v in e.headers.items()}, body
    except Exception as e:  # noqa: BLE001
        return None, {}, str(e).encode("utf-8")


def text_of(body):
    return body.decode("utf-8", "replace")


def nav_href(text, direction):
    """Extract /page/<n> from the prev/next nav-link (or None)."""
    m = re.search(
        r'class="nav-page nav-page--%s"[^>]*?href="(/page/(\d+))"'
        % direction, text)
    return m.group(2) if m else None


def reader_text_of(text):
    m = re.search(r'<div class="reader__text" lang="fa">(.*?)</div>',
                  text, re.S)
    if not m:
        return None
    return html.unescape(re.sub(r"<[^>]+>", "", m.group(1))).strip()


def drawer_of(text):
    i = text.find('id="metadata-drawer"')
    if i < 0:
        return None
    j = text.find("</details>", i)
    return text[i:j] if j > i else text[i:]


class Step:
    def __init__(self, n, name):
        self.n, self.name = n, name
        self.ok = False
        self.evidence = {}

    def fail(self, **ev):
        self.evidence.update(ev)
        return self

    def pass_(self, **ev):
        self.ok = True
        self.evidence.update(ev)
        return self


# ---------------------------------------------------------------------------
# the 12 steps — each: (base, timeout) -> Step
# ---------------------------------------------------------------------------

def step_01_home(base, timeout):
    s = Step(1, "home: intro, volume grid, coverage numbers, search box")
    st, hd, body = http(base, "/", timeout=timeout)
    t = text_of(body)
    if st != 200:
        return s.fail(status=st)
    checks = {
        "rtl_fa": 'lang="fa"' in t and 'dir="rtl"' in t,
        "intro_kicker": "کتابخانهٔ دیجیتال" in t,
        "work_title": "hero__title" in t and "تفسیر تسنیم" in t,
        "coverage_grid": "coverage-grid" in t,
        "pages_counter_45844": "45844" in t,
        "missing_counter_45243": "45243" in t,
        "present_ratio_50_3": "50.3" in t,
        "volume_grid": "volume-grid" in t,
        "hero_search_box": 'id="hero-q"' in t,
        "rag_footer_off": "متصل نیست" in t,
    }
    missing = [k for k, v in checks.items() if not v]
    return (s.pass_(status=200, bytes=len(body), markers=sorted(checks),
                    missing=[]) if not missing
            else s.fail(status=200, missing=missing))


def step_02_volume_list(base, timeout):
    s = Step(2, "volume list: all 6 volumes + unknown-volume badge")
    st, hd, body = http(base, "/volumes", timeout=timeout)
    t = text_of(body)
    if st != 200:
        return s.fail(status=st)
    n_cards = t.count("volume-card\"")
    cards_ok = n_cards >= 6
    unknown_badge = "در حال بازیابی شمارهٔ جلد" in t
    unknown_card = ("/volumes/" + VOLUME_UNKNOWN) in t
    registered = "جلد ثبت‌شده" in t
    ok = cards_ok and unknown_badge and unknown_card and registered
    return (s.pass_(status=200, volume_cards=n_cards,
                    unknown_volume_card=VOLUME_UNKNOWN)
            if ok else s.fail(status=200, volume_cards=n_cards,
                              unknown_badge=unknown_badge,
                              unknown_card=unknown_card,
                              registered=registered))


def step_03_volume_detail(base, timeout):
    s = Step(3, "enter volume vol047: cover, count, range, headings, start")
    st, hd, body = http(base, "/volumes/" + VOLUME_VOL047, timeout=timeout)
    t = text_of(body)
    if st != 200:
        return s.fail(status=st)
    checks = {
        "cover_plate": "volume-detail__cover" in t,
        "cover_svg": "<svg" in t,
        "page_count_9391": "9391" in t,
        # template renders "0 –\n          55698" (multi-line span)
        "ii_range_0_55698": re.search(r"0\s*–\s*55698", t) is not None,
        "missing_ranges_section": "بازه‌های در دست بازیابی" in t,
        "missing_count_46308": "46308" in t,
        "top_headings": "هدرهای پرتکرار" in t,
        "start_button": "شروع مطالعه" in t,
        "start_target_page0": 'href="/page/0"' in t,
        "page_index": "فهرست صفحات" in t,
    }
    missing = [k for k, v in checks.items() if not v]
    return (s.pass_(status=200, bytes=len(body),
                    ii_range="0 – 55698", missing=[]) if not missing
            else s.fail(status=200, missing=missing))


def step_04_select_page(base, timeout):
    s = Step(4, "select page 2: Naskh text block, heading, vol/barg/ii, "
                "prev/next")
    st, hd, body = http(base, "/page/2", timeout=timeout)
    t = text_of(body)
    if st != 200:
        return s.fail(status=st)
    prev_to, next_to = nav_href(t, "prev"), nav_href(t, "next")
    checks = {
        "article_flag": 'data-item-index="2"' in t,
        "naskh_text_block": "reader__text" in t,
        "item_index_code": "item_index: <code>2</code>" in t,
        "volume_label_1": "جلد 1" in t,
        "heading_h1": "reader__heading" in t,
        "prev_to_1": prev_to == "1",
        "next_to_3": next_to == "3",
    }
    missing = [k for k, v in checks.items() if not v]
    return (s.pass_(status=200, prev=prev_to, next=next_to, missing=[])
            if not missing else s.fail(status=200, prev=prev_to,
                                       next=next_to, missing=missing))


def step_05_read_text(base, timeout):
    s = Step(5, "read real Persian text (non-empty, Persian script)")
    st, hd, body = http(base, "/page/2", timeout=timeout)
    t = text_of(body)
    if st != 200:
        return s.fail(status=st)
    txt = reader_text_of(t)
    if txt is None or not txt:
        return s.fail(status=200, text_len=0, detail="no reader text")
    has_fa = bool(PERSIAN.search(txt))
    return (s.pass_(status=200, text_len=len(txt), persian_script=has_fa,
                    snippet=txt[:80])
            if has_fa else s.fail(status=200, text_len=len(txt),
                                  persian_script=False))


def step_06_next_gap_aware(base, timeout):
    s = Step(6, "next page from 3648 (last before gap) lands on 11183 "
                "with honest gap note")
    st, hd, body = http(base, "/page/3648", timeout=timeout)
    t = text_of(body)
    if st != 200:
        return s.fail(status=st)
    next_to = nav_href(t, "next")
    gap_note = "nav-gap" in t and "در دست بازیابی" in t
    ok = next_to == "11183" and gap_note
    return (s.pass_(status=200, next=next_to, gap_note=True,
                    gap="3649..11182 (7534 pages)")
            if ok else s.fail(status=200, next=next_to, gap_note=gap_note))


def step_07_prev_gap_aware(base, timeout):
    s = Step(7, "prev page from 11183 (first after gap) lands on 3648")
    st, hd, body = http(base, "/page/11183", timeout=timeout)
    t = text_of(body)
    if st != 200:
        return s.fail(status=st)
    prev_to = nav_href(t, "prev")
    ok = prev_to == "3648"
    return (s.pass_(status=200, prev=prev_to)
            if ok else s.fail(status=200, prev=prev_to))


def step_08_search(base, timeout):
    s = Step(8, "Persian search «قرآن»: marks, links, honest total")
    path = "/search?q=" + urllib.parse.quote(SEARCH_Q)
    st, hd, body = http(base, path, timeout=timeout)
    t = text_of(body)
    if st != 200:
        return s.fail(status=st)
    m = re.search(r"(\d+) نتیجه برای «قرآن»", t)
    total = int(m.group(1)) if m else None
    n_mark = t.count("<mark>")
    n_hits = t.count("search-hit\"")
    ok = (total is not None and total >= 100 and n_mark >= 2
          and n_hits >= 5 and "/page/" in t and "مشاهدهٔ صفحه" in t)
    ev = dict(status=200, total=total, marks=n_mark, hits=n_hits)
    return s.pass_(**ev) if ok else s.fail(**ev)


def step_09_topic_detail(base, timeout):
    s = Step(9, "open top topic «تفسیر»: occurrences, page links, "
                "auto-extract label")
    st, hd, body = http(base, "/topics/" + TOPIC_TAFSIR, timeout=timeout)
    t = text_of(body)
    if st != 200:
        return s.fail(status=st)
    checks = {
        "title": "<h1" in t and "تفسیر" in t,
        "counts": "1678 صفحه" in t and "5 جلد" in t,
        "first_page": "اولین: صفحه 273" in t,
        "occ_list": "occ-list" in t,
        "occ_page_links": t.count('class="occ-item"') >= 5,
        "auto_extract_label": "استخراج خودکار" in t,
    }
    missing = [k for k, v in checks.items() if not v]
    n_occ = t.count('class="occ-item"')
    return (s.pass_(status=200, occurrences_shown=n_occ, missing=[])
            if not missing else s.fail(status=200, occurrences_shown=n_occ,
                                       missing=missing))


def step_10_surahs_honest(base, timeout):
    s = Step(10, "surah page: honest «در حال تکمیل», no fabricated names")
    st, hd, body = http(base, "/surahs", timeout=timeout)
    t = text_of(body)
    if st != 200:
        return s.fail(status=st)
    checks = {
        "in_progress": "در حال تکمیل" in t,
        "coverage_0_114": "0/114" in t,
        "reason": "چرا هنوز؟" in t,
        "no_fabrication_note": "هیچ دادهٔ سوره‌ای ساخته نمی‌شود" in t,
    }
    leaked = [n for n in NO_FABRICATED_SURAHS if n in t]
    ok = all(checks.values()) and not leaked
    return (s.pass_(status=200, fabricated_names=[])
            if ok else s.fail(status=200, fabricated_names=leaked,
                              missing=[k for k, v in checks.items()
                                       if not v]))


def step_11_metadata_drawer(base, timeout):
    s = Step(11, "metadata drawer in HTML: page_id, sha256, source_url, "
                 "captured_at, rag_status")
    st, hd, body = http(base, "/page/2", timeout=timeout)
    t = text_of(body)
    if st != 200:
        return s.fail(status=st)
    d = drawer_of(t)
    if d is None:
        return s.fail(status=200, detail="no metadata drawer in HTML")
    checks = {
        "dt_page_id": "<dt>page_id</dt>" in d,
        "dt_sha256": "<dt>content_sha256</dt>" in d,
        "dt_source_url": "<dt>source_url</dt>" in d,
        "dt_captured_at": "<dt>captured_at</dt>" in d,
        "dt_source_page_id": "<dt>source_page_id</dt>" in d,
        "page_id_value": re.search(
            r"tasnim_hamta__hamta-2026__vol\d{3}__p2", d) is not None,
        "sha256_hex64": re.search(
            r"<code dir=\"ltr\">[0-9a-f]{64}</code>", d) is not None,
        "source_url_link": re.search(
            r"<a href=\"https?://[^\"]+\" rel=\"nofollow noopener\">",
            d) is not None,
        "captured_at_value": "2026-10-25 16:50:40" in d,
        "source_page_id_value": "11707" in d,
        "rag_not_connected_footer": "not_connected" in t,
    }
    missing = [k for k, v in checks.items() if not v]
    return (s.pass_(status=200, drawer_fields=sorted(checks), missing=[])
            if not missing else s.fail(status=200, missing=missing))


def step_12_mobile(base, timeout):
    s = Step(12, "mobile: viewport meta, 375px CSS, 375px re-captures")
    st, hd, body = http(base, "/", timeout=timeout)
    t = text_of(body)
    if st != 200:
        return s.fail(status=st)
    viewport = 'name="viewport"' in t
    cst, chd, css = http(base, "/static/css/tasnim.css", timeout=timeout)
    css_text = text_of(css) if cst == 200 else ""
    mobile_first = "375/768/1024/1280" in css_text
    has_minwidth = "@media (min-width:" in css_text
    static_ok = viewport and cst == 200 and mobile_first and has_minwidth

    shots = []
    browser_ok = True
    try:
        import screenshot  # noqa: WPS433 (sibling module, stdlib only)
        browser = screenshot.find_browser()
        if browser:
            views = [
                ("09-mobile-home", "/", 375, 812),
                ("10-mobile-reader", "/page/2", 375, 812),
            ]
            import shutil
            import tempfile
            profile = tempfile.mkdtemp(prefix="pct_e2e_mobile_")
            try:
                for slug, path, w, h in views:
                    out = os.path.join(HERE, "screenshots", slug + ".png")
                    os.makedirs(os.path.dirname(out), exist_ok=True)
                    screenshot.shoot(browser, base.rstrip("/") + path, out,
                                     w, h, profile, timeout=120)
                    size = os.path.getsize(out) if os.path.exists(out) else 0
                    sig_ok = False
                    if size > 8:
                        with open(out, "rb") as f:
                            sig_ok = (f.read(8) == b"\x89PNG\r\n\x1a\n")
                    good = size > 8000 and sig_ok
                    shots.append({"file": slug + ".png", "url": path,
                                  "width": w, "height": h, "bytes": size,
                                  "png_signature": sig_ok, "ok": good})
            finally:
                shutil.rmtree(profile, ignore_errors=True)
        else:
            browser_ok = False
            shots.append({"file": None,
                          "note": "BLOCKED: no Chromium-family browser"})
    except Exception as e:  # noqa: BLE001
        browser_ok = False
        shots.append({"file": None, "error": repr(e)})

    ok = static_ok and all(x.get("ok", False) for x in shots
                           if x.get("file")) and (
        browser_ok or all(x.get("file") is None for x in shots))
    return (s.pass_(status=200, viewport_meta=viewport,
                    css_mobile_first_comment=mobile_first,
                    css_minwidth_media=has_minwidth,
                    captures=shots)
            if ok else s.fail(status=200, viewport_meta=viewport,
                              css_mobile_first_comment=mobile_first,
                              css_minwidth_media=has_minwidth,
                              captures=shots))


STEPS = [step_01_home, step_02_volume_list, step_03_volume_detail,
         step_04_select_page, step_05_read_text, step_06_next_gap_aware,
         step_07_prev_gap_aware, step_08_search, step_09_topic_detail,
         step_10_surahs_honest, step_11_metadata_drawer, step_12_mobile]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--base", default=DEFAULT_BASE)
    ap.add_argument("--timeout", type=int, default=25)
    args = ap.parse_args(argv)

    # read-model identity for the evidence file (health is rate-exempt)
    rm = {}
    st, hd, body = http(args.base, "/api/v1/tasnim/health", timeout=args.timeout)
    if st == 200:
        try:
            doc = json.loads(body.decode("utf-8"))
            rm = doc.get("data", {}).get("readmodel", {})
        except ValueError:
            pass

    print("=" * 78)
    print("Tasnim Web V1 — 12-step user-journey E2E  [target: %s]"
          % args.base)
    print("readmodel: %s" % (rm or "unknown (server not healthy)"))
    print("=" * 78)

    results = []
    for fn in STEPS:
        step = fn(args.base, args.timeout)
        results.append(step)
        flag = "PASS" if step.ok else "FAIL"
        ev = json.dumps(step.evidence, ensure_ascii=False)
        print("%2d  [%s]  %s" % (step.n, flag, step.name))
        if len(ev) > 160:
            ev = ev[:157] + "..."
        print("     " + ev)

    n_pass = sum(1 for r in results if r.ok)
    n_fail = len(results) - n_pass
    evidence = {
        "mission": "PCM-20.6.4 Phase 5 — Track B (E2E B14)",
        "base": args.base,
        "generated_at": datetime.datetime.now(datetime.timezone.utc)
                        .strftime("%Y-%m-%dT%H:%M:%SZ"),
        "readmodel": rm,
        "steps": [{"n": r.n, "name": r.name, "status": "PASS" if r.ok
                   else "FAIL", "evidence": r.evidence} for r in results],
        "summary": {"total": len(results), "pass": n_pass, "fail": n_fail},
    }
    with open(EVIDENCE_PATH, "w", encoding="utf-8") as f:
        json.dump(evidence, f, ensure_ascii=False, indent=2)
    print("-" * 78)
    print("RESULT: %d PASS / %d FAIL / %d total" % (n_pass, n_fail,
                                                     len(results)))
    print("evidence -> %s" % EVIDENCE_PATH)
    return 0 if n_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

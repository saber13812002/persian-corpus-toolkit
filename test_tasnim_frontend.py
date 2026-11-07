# -*- coding: utf-8 -*-
"""Tasnim Web V1 — SSR frontend tests (PCM-20.6.4, Track B, spec §9.4).

Offline, fixture-based (tasnim_test_support.reset()), exact counts — no
fabricated data, no network. Covers:

* every route renders 200 with the shared RTL layout + a11y markers
* / (hero, live counters, present_ratio definition, volume cards,
  latest pages)
* /volumes + /volumes/<id> (stats, backfill ranges, top headings,
  paginated page index with gap chips, heading list)
* /page/<ii> reader (heading, quality badges, truncated banner, dup
  notice + dup_rank, in-volume position, metadata drawer, related
  topics, gap-aware prev/next with rel=prev/next)
* missing item_index -> honest 200 recovery (never 404/500)
* /topics + /topics/<topic_id> (filter, parent topic, occurrences)
* /surahs («در حال تکمیل», no fabrication, no surah data)
* /search?q= SSR FTS5 with <mark>; invalid q -> 400 page (not 500)
* /about (provenance SHAs, quality table, backfill table — DB only)
* styled 404/405; font/CSS/JS static assets (content types, cache)
* HP-1 canary: forbidden substrings absent from every rendered page
* unknown-volume badge (temp-fixture mutation: volume_no -> NULL)
* _pager unit regression (pagination URLs must use '?')
* SSR routes are exempt from the API rate limiter

Windows-safe: fresh fixture per class, all apps closed via
tasnim_shutdown before rmtree (guarded so the last class's teardown
never runs twice on a stale state).
"""
import hashlib
import os
import re
import shutil
import sqlite3
import unittest

import tasnim_test_support as fx
from tasnim.web import api, pages

# HP-1 forbidden substrings (same set as test_tasnim_api.py)
FORBIDDEN_SUBSTRINGS = (
    "hidden_summary",
    "retrieval_context",
    fx.CANARY,
    "secret text",
)

BIG = 10 ** 6  # rate-limit ceiling: SSR tests must never see 429


# --- byte-exact Persian literals (extracted from rendered fixture
#     HTML during the PCM-20.6.4 repair - do not retype by hand) ---
_T_PAGE12 = "\u0635\u0641\u062D\u0647 12"
_T_PAGE10 = "\u0635\u0641\u062D\u0647 10"
_T_INVOL3 = "\u0635\u0641\u062D\u0647 3 \u0627\u0632 7 \u062F\u0631"
_T_INVOL4 = "\u0635\u0641\u062D\u0647 4 \u0627\u0632 7 \u062F\u0631"
_T_INVOL6 = "\u0635\u0641\u062D\u0647 6 \u0627\u0632 7 \u062F\u0631"
_T_CHIP6_4_9 = "6 \u0635\u0641\u062D\u0647 \u062F\u0631 \u0628\u0627\u0632\u0647\u0654 4 \u062A\u0627 9 \u062F\u0631 \u062F\u0633\u062A \u0628\u0627\u0632\u06CC\u0627\u0628\u06CC \u0627\u0633\u062A"
_T_CHIP1_4_4 = "1 \u0635\u0641\u062D\u0647 \u062F\u0631 \u0628\u0627\u0632\u0647\u0654 4 \u062A\u0627 4 \u062F\u0631 \u062F\u0633\u062A \u0628\u0627\u0632\u06CC\u0627\u0628\u06CC \u0627\u0633\u062A"
_T_CHIP4_6_9 = "4 \u0635\u0641\u062D\u0647 \u062F\u0631 \u0628\u0627\u0632\u0647\u0654 6 \u062A\u0627 9 \u062F\u0631 \u062F\u0633\u062A \u0628\u0627\u0632\u06CC\u0627\u0628\u06CC \u0627\u0633\u062A"
_T_CHIP986_13_998 = "986 \u0635\u0641\u062D\u0647 \u062F\u0631 \u0628\u0627\u0632\u0647\u0654 13 \u062A\u0627 998 \u062F\u0631 \u062F\u0633\u062A \u0628\u0627\u0632\u06CC\u0627\u0628\u06CC \u0627\u0633\u062A"
_T_VOLRANGE = "6 \u0635\u0641\u062D\u0647 \u062F\u0631 \u0628\u0627\u0632\u0647\u0654 4 \u062A\u0627 9"
_T_RECRANGE = "6 \u0635\u0641\u062D\u0647 \u062F\u0631 \u0628\u0627\u0632\u0647\u0654"
_T_RECCODES = "<code>4</code> \u062A\u0627 <code>9</code>"
_T_DUPLINK0 = "\u0646\u0633\u062E\u0647\u0654 0 (\u062C\u0644\u062F 1)"
_T_DUPLINK1 = "\u0646\u0633\u062E\u0647\u0654 1 (\u062C\u0644\u062F 1)"
_T_START = "\u0634\u0631\u0648\u0639 \u0645\u0637\u0627\u0644\u0639\u0647"
_T_AB_SHORT = "<tr><td><code>short</code></td><td>\u0635\u0641\u062D\u0647\u0654 \u06A9\u0648\u062A\u0627\u0647 (\u06A9\u0645\u062A\u0631 \u0627\u0632 \u0622\u0633\u062A\u0627\u0646\u0647)</td><td>1</td></tr>"
_T_AB_EMPTY = "<tr><td><code>empty</code></td><td>\u0628\u062F\u0648\u0646 \u0645\u062A\u0646 (\u062F\u0631 \u062F\u0633\u062A \u0628\u0627\u0632\u06CC\u0627\u0628\u06CC)</td><td>1</td></tr>"
_T_AB_TRUNC = "<tr><td><code>truncated_at_2000</code></td><td>\u0645\u062A\u0646 \u062F\u0631 \u0645\u0646\u0628\u0639 \u0642\u0637\u0639 \u0627\u0633\u062A (\u06F2\u06F0\u06F0\u06F0 \u0646\u0648\u06CC\u0633\u0647)</td><td>1</td></tr>"
_T_AB_DUP = "<tr><td><code>dup_item_index</code></td><td>\u062A\u06A9\u0631\u0627\u0631 \u0634\u0645\u0627\u0631\u0647 (\u0686\u0646\u062F \u0646\u0633\u062E\u0647 \u0628\u0631\u0627\u06CC \u06CC\u06A9 \u0634\u0645\u0627\u0631\u0647)</td><td>2</td></tr>"


def _teardown_state(state):
    for app in list(state.get("apps", [])):
        try:
            app.tasnim_shutdown()
        except Exception:
            pass
    shutil.rmtree(state.get("tmp", ""), ignore_errors=True)


class SsrBase(unittest.TestCase):
    """Fresh fixture + SSR app per class (spec §9.4)."""

    @classmethod
    def setUpClass(cls):
        cls.state = fx.reset()
        cls.app = fx.make_app(cls.state, rate_search=BIG, rate_read=BIG)
        cls.client = cls.app.test_client()

    @classmethod
    def tearDownClass(cls):
        if fx._STATE.get("tmp") == cls.state["tmp"]:
            fx._STATE.clear()
            _teardown_state(cls.state)

    def get(self, path):
        return self.client.get(path)

    def assert_layout(self, r):
        """Shared RTL layout + a11y markers on every rendered page."""
        b = r.get_data(as_text=True)
        for needle in (
            '<html lang="fa" dir="rtl"',
            '<meta name="viewport" content="width=device-width,'
            ' initial-scale=1">',
            'href="/static/css/tasnim.css"',
            'src="/static/js/tasnim.js"',
            '<a class="skip-link" href="#main">',
            '<main id="main" class="site-main">',
            'site-footer__id',
            'not_connected',
        ):
            self.assertIn(needle, b)
        return b

    def assert_no_leak(self, b):
        for s in FORBIDDEN_SUBSTRINGS:
            self.assertNotIn(s, b)


class TestAbout(SsrBase):
    def test_provenance(self):
        r = self.get("/about")
        self.assertEqual(r.status_code, 200)
        b = self.assert_layout(r)
        self.assertIn("<h1 class=\"page-head__title\">دربارهٔ پیکره</h1>", b)
        for needle in (
            "<code>%s</code>" % fx.WORK_ID,
            "پیکره آزمایشی",
            "<code>%s</code>" % fx.EDITION_ID,
            "خروجی آزمایشی",
            "<code>v0099</code>",
            "<code>%s</code>" % ("f" * 64),
            "<code>%s</code>" % self.state["report"]["db_sha256"],
            "<code>tasnim-readmodel/1.0</code>",
            "<code>tasnim-topic-norm/1.0</code>",
            "<code>tokenize_fa/1.0</code>",
            "not_connected",
            "not_supported",
            'href="/static/fonts/README.md"',
            "مستندات و SHA-256 فونت‌ها",
        ):
            self.assertIn(needle, b)
        # built_at: wallclock UTC, ISO 'Z' (never asserted byte-exact)
        self.assertRegex(b, r"<code>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z</code>")

    def test_counts_quality_backfill_db_only(self):
        r = self.get("/about")
        self.assertEqual(r.status_code, 200)
        b = self.assert_layout(r)
        for num in (">10<", ">2<", ">4<", ">6<"):
            self.assertIn(
                'class="stat-card__num"%s' % num, b)
        self.assertIn(
            "<tr><td><code>ok</code></td><td>متن کامل</td><td>5</td></tr>", b)
        self.assertIn(_T_AB_SHORT, b)
        self.assertIn(_T_AB_EMPTY, b)
        self.assertIn(_T_AB_TRUNC, b)
        self.assertIn(_T_AB_DUP, b)
        for needle in ("p50 = 100", "p90 = 150", "p99 = 190",
                       "max = 2000"):
            self.assertIn(needle, b)
        # backfill table row: global gap [4,9] (6 pages), status, note
        self.assertIn("<td><code>4</code></td>", b)
        self.assertIn("<td><code>9</code></td>", b)
        self.assertIn("<td>6</td>", b)
        self.assertIn("<td>backfill_pending</td>", b)
        self.assertIn("test fixture: backfill pending", b)


class TestStaticAssets(SsrBase):
    def test_css_design_tokens(self):
        r = self.get("/static/css/tasnim.css")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(
            r.headers.get("Content-Type", "").startswith("text/"))
        b = r.get_data(as_text=True)
        for needle in (
            "@media (min-width: 768px)",
            "@media (min-width: 1024px)",
            "@media (min-width: 1280px)",
            "@media (prefers-reduced-motion:",
            "@media print",
            '[data-theme="dark"]',
            "@font-face",
            ":focus-visible",
            "font-display: swap",
        ):
            self.assertIn(needle, b)

    def test_js_served(self):
        r = self.get("/static/js/tasnim.js")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(
            r.headers.get("Content-Type", "").startswith("text/"))

    def test_fonts_200_ttf_cached(self):
        d = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "tasnim", "web", "static", "fonts")
        for name in ("vazirmatn-regular.ttf", "vazirmatn-medium.ttf",
                     "vazirmatn-bold.ttf", "noto-naskh-arabic.ttf"):
            r = self.get("/static/fonts/" + name)
            self.assertEqual(r.status_code, 200, name)
            self.assertEqual(r.headers.get("Content-Type"), "font/ttf", name)
            self.assertEqual(r.headers.get("Cache-Control"),
                             "public, max-age=86400", name)
            self.assertEqual(len(r.data), os.path.getsize(
                os.path.join(d, name)), name)

    def test_font_404_no_font_headers(self):
        r = self.get("/static/fonts/nope.ttf")
        self.assertEqual(r.status_code, 404)
        self.assertNotEqual(r.headers.get("Content-Type", ""), "font/ttf")
        self.assertNotIn("Cache-Control", r.headers)

    def test_font_docs(self):
        r = self.get("/static/fonts/OFL.txt")
        self.assertEqual(r.status_code, 200)
        r = self.get("/static/fonts/README.md")
        self.assertEqual(r.status_code, 200)
        self.assertIn("SHA-256", r.get_data(as_text=True))


class TestErrorPages(SsrBase):
    def test_404_styled(self):
        r = self.get("/nope")
        self.assertEqual(r.status_code, 404)
        b = self.assert_layout(r)
        self.assertRegex(b, r'<p class="error-card__code" dir="ltr">404</p>')
        self.assertIn(
            "<h1 class=\"error-card__title\">صفحه پیدا نشد</h1>", b)
        self.assertIn(
            "مسیری که درخواست دادید («/nope») وجود ندارد.", b)
        self.assertIn('href="/">بازگشت به خانه</a>', b)

    def test_405_json(self):
        r = self.client.post("/")
        self.assertEqual(r.status_code, 405)
        self.assertEqual(r.content_type, "application/json")
        body = r.get_json()
        self.assertEqual(body["code"], "METHOD_NOT_ALLOWED")
        self.assertTrue(body["request_id"])


class TestLayoutAndA11y(SsrBase):
    ROUTES = (
        "/", "/volumes", "/volumes/%s" % fx.V1, "/volumes/%s" % fx.V2,
        "/page/0", "/page/3", "/page/12", "/page/5", "/page/999",
        "/topics", "/surahs", "/search?q=تفسیر", "/about",
    )

    def test_all_routes_layout(self):
        for path in self.ROUTES:
            r = self.get(path)
            self.assertEqual(r.status_code, 200, path)
            self.assert_layout(r)

    def test_nav_active_and_search_form(self):
        tids = re.findall(
            r'href="/topics/(t-[0-9a-f]{12})"',
            self.get("/topics").get_data(as_text=True))
        self.assertEqual(len(tids), 2)
        r = self.get("/")
        b = self.assert_layout(r)
        self.assertIn('<a href="/" class="is-active">خانه</a>', b)
        self.assertNotIn('<a href="/volumes" class="is-active">', b)
        r = self.get("/volumes")
        b = self.assert_layout(r)
        self.assertIn('<a href="/volumes" class="is-active">جلدها</a>', b)
        r = self.get("/topics")
        b = self.assert_layout(r)
        self.assertIn('<a href="/topics" class="is-active">موضوعات</a>', b)
        b = self.get("/").get_data(as_text=True)
        for needle in (
            '<form class="site-search" action="/search" method="get"'
            ' role="search">',
            'name="q" dir="auto" minlength="2" maxlength="64"',
            'aria-label="جستجو در متن"',
            'id="theme-toggle"',
        ):
            self.assertIn(needle, b)

    def test_reader_tools_and_nav_rel(self):
        b = self.assert_layout(self.get("/page/3"))
        for needle in (
            'id="font-minus"',
            'id="font-reset"',
            'id="font-plus"',
            'aria-controls="metadata-drawer"',
            'id="meta-toggle"',
            '<div class="reader__text" lang="fa">',
        ):
            self.assertIn(needle, b)
        self.assertRegex(b, r'rel="prev"\s+href="/page/2"')
        self.assertRegex(b, r'rel="next"\s+href="/page/10"')


class TestHp1Canary(SsrBase):
    ROUTES = (
        "/", "/volumes", "/volumes/%s" % fx.V1, "/volumes/%s" % fx.V2,
        "/page/0", "/page/1", "/page/2", "/page/2?dup_rank=1", "/page/3",
        "/page/5", "/page/10", "/page/11", "/page/12", "/page/999",
        "/topics", "/search?q=تفسیر", "/search?q=زرافه", "/about",
    )

    def test_no_canary_any_page(self):
        tids = re.findall(
            r'href="/topics/(t-[0-9a-f]{12})"',
            self.get("/topics").get_data(as_text=True))
        routes = list(self.ROUTES) + ["/topics/" + t for t in tids]
        for path in routes:
            r = self.get(path)
            self.assertEqual(r.status_code, 200, path)
            self.assert_no_leak(r.get_data(as_text=True))

    def test_drawer_shows_record_id_only(self):
        b = self.get("/page/0").get_data(as_text=True)
        self.assertIn("hctx:%s" % fx._P["p0"], b)
        self.assertNotIn("hcctx:", b)
        self.assertIn("محتوای رکورد نمایش داده نمی‌شود", b)


class TestPager(unittest.TestCase):
    """Unit regression: pagination URLs must be real query strings."""

    def test_pager_urls(self):
        p = pages._pager("/topics", 2, 100, 25, "q=بحث&sort=page_count")
        self.assertEqual(p["total_pages"], 4)
        self.assertEqual(p["prev_url"],
                         "/topics?q=بحث&sort=page_count&p=1")
        self.assertEqual(p["next_url"],
                         "/topics?q=بحث&sort=page_count&p=3")
        p = pages._pager("/volumes/%s" % fx.V1, 1, 120, 50, "view=headings")
        self.assertIsNone(p["prev_url"])
        self.assertEqual(p["next_url"],
                         "/volumes/%s?view=headings&p=2" % fx.V1)
        p = pages._pager("/volumes/%s" % fx.V1, 1, 3, 50)
        self.assertIsNone(p["next_url"])
        self.assertIsNone(p["prev_url"])
        self.assertEqual(p["total_pages"], 1)


class TestSsrNotRateLimited(unittest.TestCase):
    """SSR routes are exempt from the API rate limiter (documented)."""

    @classmethod
    def setUpClass(cls):
        cls.state = fx.reset()
        cls.app = fx.make_app(cls.state)  # default rates: search=30
        cls.client = cls.app.test_client()

    @classmethod
    def tearDownClass(cls):
        if fx._STATE.get("tmp") == cls.state["tmp"]:
            fx._STATE.clear()
            _teardown_state(cls.state)

    def test_search_not_limited(self):
        for _ in range(40):  # > default search limit (30)
            r = self.client.get("/search?q=تفسیر")
            self.assertEqual(r.status_code, 200)


class TestHome(SsrBase):
    def test_hero_and_counters(self):
        r = self.get("/")
        self.assertEqual(r.status_code, 200)
        b = self.assert_layout(r)
        self.assertRegex(
            b, r"کتابخانهٔ دیجیتال · پیکرهٔ v0099")
        self.assertIn(
            "<h1 id=\"hero-title\" class=\"hero__title\">پیکره آزمایشی</h1>",
            b)
        self.assertIn("خروجی آزمایشی", b)
        # exact fixture counters (DB-only, no fabricated numbers)
        for num in (">10<", ">2<", ">4<", ">6<"):
            self.assertIn('class="stat-card__num"%s' % num, b)
        self.assertIn('class="stat-card__num">62.5٪</span>', b)
        self.assertIn(
            "pages/(pages+missing_item_index)", b)

    def test_latest_pages(self):
        b = self.get("/").get_data(as_text=True)
        self.assertEqual(b.count('class="latest-item"'), 8)
        i12 = b.find('href="/page/12"')
        i11 = b.find('href="/page/11"')
        i10 = b.find('href="/page/10"')
        i0 = b.find('href="/page/0"')
        self.assertNotEqual(i12, -1)
        self.assertNotEqual(i11, -1)
        self.assertNotEqual(i10, -1)
        self.assertTrue(i12 < i11 < i10)
        self.assertEqual(i0, -1)  # latest = DESC, 8 rows from 12 down to 2
        # dup status has no QUALITY_LABELS entry -> raw status shown
        self.assertIn(
            'class="latest-item__quality">dup_item_index</span>', b)
        self.assertIn(
            'class="latest-item__quality">%s</span>'
            % pages.QUALITY_LABELS["truncated_at_2000"][1], b)

    def test_topic_strip(self):
        b = self.get("/").get_data(as_text=True)
        self.assertIn("بحث روایی", b)
        self.assertIn("3 صفحه", b)
        self.assertIn("پیشگفتار مفسر", b)
        self.assertIn("1 صفحه", b)
        self.assertIn(pages.TOPIC_DISCLAIMER, b)

    def test_volume_cards(self):
        b = self.get("/").get_data(as_text=True)
        self.assertEqual(b.count('class="volume-card"'), 2)
        self.assertIn("7 صفحه", b)
        self.assertRegex(b, r"7 صفحه\s*· 6 در دست بازیابی")
        self.assertIn("3 صفحه", b)
        self.assertEqual(
            b.count("badge--info\">تعلق‌دهی ابهام‌دار</span>"), 2)


class TestVolumes(SsrBase):
    def test_list(self):
        r = self.get("/volumes")
        self.assertEqual(r.status_code, 200)
        b = self.assert_layout(r)
        self.assertIn("<h1 class=\"page-head__title\">جلدها</h1>", b)
        self.assertRegex(b, r"· 2 جلد ثبت‌شده")
        self.assertIn("در حال بازیابی شمارهٔ جلد» نشان داده می‌شود", b)
        self.assertIn('href="/volumes/%s"' % fx.V1, b)
        self.assertIn('href="/volumes/%s"' % fx.V2, b)
        # sort=volume_no is default: V1 (no 1) before V2 (no 2)
        self.assertTrue(b.find("/volumes/%s" % fx.V1)
                        < b.find("/volumes/%s" % fx.V2))

    def test_sort_page_count(self):
        b = self.get("/volumes?sort=page_count").get_data(as_text=True)
        # 7 > 3 -> V1 first
        self.assertTrue(b.find("/volumes/%s" % fx.V1)
                        < b.find("/volumes/%s" % fx.V2))

    def test_bad_sort_falls_back(self):
        r = self.get("/volumes?sort=bogus")
        self.assertEqual(r.status_code, 200)
        self.assertIn("<h1 class=\"page-head__title\">جلدها</h1>",
                      r.get_data(as_text=True))

    def test_detail_vol001(self):
        r = self.get("/volumes/%s" % fx.V1)
        self.assertEqual(r.status_code, 200)
        b = self.assert_layout(r)
        self.assertIn("<h1 class=\"page-head__title\">جلد 1</h1>", b)
        self.assertIn("استراتژی: url_section", b)
        self.assertIn("نمایهٔ اختصاصی — جلد رسمی نیست", b)
        # stat cards: 7 pages, span 0–11, 6 missing
        self.assertRegex(b, r"<span class=\"stat-card__num\">7</span>")
        self.assertRegex(b, r"<span class=\"stat-card__num\">\s*0 –\s*11</span>")
        self.assertRegex(
            b, r"<span class=\"stat-card__num\">6</span>")
        self.assertIn('href="/page/0">' + _T_START + '</a>', b)
        # backfill range (per-volume coverage row, gap [4,9])
        self.assertIn("بازه‌های در دست بازیابی", b)
        self.assertIn(_T_VOLRANGE, b)
        self.assertIn("badge--muted\">backfill_pending</span>", b)
        # top headings: «بحث روایی» x2 (p2, p3)
        self.assertRegex(b, r"بحث روایی\s*</span>\s*<span"
                           r" class=\"topic-chip__count\">2 بار")
        # page index: 7 rows + one gap entry
        self.assertEqual(b.count('class="page-index__item"'), 7)
        self.assertEqual(b.count('class="page-index__gap"'), 1)
        self.assertRegex(
            b, r"6 صفحه در باز.*? 4 تا 9 در دست بازیابی است")
        self.assertIn(
            'class="page-index__item" href="/page/0">', b)
        self.assertIn("برگ 1", b)
        self.assertRegex(
            b, r"<span class=\"page-index__quality\">%s</span>"
            % re.escape(pages.QUALITY_LABELS["ok"][1]))
        self.assertRegex(
            b, r"<span class=\"page-index__quality\">%s</span>"
            % re.escape(pages.QUALITY_LABELS["empty"][1]))
        # heading list: 3 rows
        self.assertRegex(b, r"هدرهای این جلد\s*<span"
                           r" class=\"volume-section__count\">3 هدر</span>")
        self.assertRegex(b, r"هدرهای این جلد\s*\n?\s*<span"
                           r" class=\"volume-section__count\">3 هدر</span>"
                           if False else r">3 هدر<", b)
        self.assertEqual(b.count("class=\"heading-list__item\""), 3)
        self.assertRegex(b, r"بحث روایی\s*</span>\s*<span"
                           r" class=\"heading-list__num\">صفحه 2</span>")
        self.assertNotIn("badge--warning\">در حال بازیابی شمارهٔ جلد", b)

    def test_detail_vol002(self):
        r = self.get("/volumes/%s" % fx.V2)
        self.assertEqual(r.status_code, 200)
        b = self.assert_layout(r)
        self.assertIn("<h1 class=\"page-head__title\">جلد 2</h1>", b)
        self.assertRegex(b, r"<span class=\"stat-card__num\">3</span>")
        self.assertRegex(b, r"<span class=\"stat-card__num\">\s*10 –\s*12</span>")
        self.assertIn("شروع مطالعه</a>", b)
        self.assertIn('href="/page/10"', b)
        self.assertNotIn("بازه‌های در دست بازیابی", b)
        self.assertIn("12) بحث روایی", b)
        self.assertNotIn("page-index__gap", b)
        self.assertIn("badge--info\">تعلق‌دهی ابهام‌دار</span>", b)
        self.assertIn("badge--muted\">هم‌پوشانی با جلد دیگر</span>", b)

    def test_detail_404(self):
        r = self.get("/volumes/nope")
        self.assertEqual(r.status_code, 404)
        b = self.assert_layout(r)
        self.assertIn("مورد پیدا نشد", b)
        self.assertIn("جلدی با volume_id «nope» در read model نیست.", b)


class TestReader(SsrBase):
    def test_page0_full(self):
        r = self.get("/page/0")
        self.assertEqual(r.status_code, 200)
        b = self.assert_layout(r)
        self.assertIn(
            '<article class="reader" data-item-index="0"', b)
        self.assertIn('<h1 class="reader__heading">پیشگفتار مفسر</h1>', b)
        self.assertIn(
            '<a href="/volumes/%s">جلد 1</a> · برگ 1' % fx.V1, b)
        self.assertIn("item_index: <code>0</code>", b)
        self.assertRegex(b, r'<span class="badge badge--%s">%s</span>'
                         % tuple(pages.QUALITY_LABELS["ok"]))
        self.assertIn("تفسیر قرآن کریم از روایات", b)
        self.assertIn("25 characters", b)
        self.assertIn("صفحه 1 از 7 در", b)
        self.assertIn("فهرست صفحات جلد", b)
        # metadata drawer (whitelist only)
        self.assertIn("fx__vol001__p0", b)
        self.assertIn("hctx:fx__vol001__p0", b)
        self.assertIn("محتوای رکورد نمایش داده نمی‌شود", b)
        self.assertIn("https://example.org/payload?item_index=0", b)
        self.assertIn('rel="nofollow noopener"', b)
        # related topics: volume's top topic
        self.assertIn("موضوعات مرتبط", b)
        self.assertIn("بحث روایی", b)
        # gap-aware nav: corpus start / adjacent next
        self.assertIn("nav-page--end", b)
        self.assertIn("ابتدای پیکره", b)
        self.assertRegex(b, r'rel="next"\s+href="/page/1"')
        self.assertNotIn("gap-chip", b)

    def test_page3_gap_next(self):
        b = self.assert_layout(self.get("/page/3"))
        self.assertIn('<h1 class="reader__heading">بحث روایی</h1>', b)
        self.assertRegex(b, r'<span class="badge badge--warning">%s</span>'
                         % re.escape(pages.QUALITY_LABELS["short"][1]))
        self.assertIn("متن کوتاه", b)
        self.assertRegex(b, r'rel="prev"\s+href="/page/2"')
        self.assertRegex(b, r'rel="next"\s+href="/page/10"')
        self.assertIn(_T_CHIP6_4_9, b)

    def test_page12_truncated(self):
        b = self.assert_layout(self.get("/page/12"))
        self.assertIn('<div class="banner banner--danger" role="alert"'
                      ' id="truncated-banner">', b)
        self.assertIn(pages.TRUNCATED_BANNER, b)
        self.assertIn(_T_PAGE12, b)
        self.assertRegex(b, r'<span class="badge badge--danger">%s</span>'
                         % re.escape(
                             pages.QUALITY_LABELS["truncated_at_2000"][1]))
        self.assertIn("زبان قرآن و بیان آن", b)
        self.assertRegex(b, r'rel="prev"\s+href="/page/11"')
        self.assertIn("انتهای پیکره", b)
        # breadcrumb: volume known & unambiguous
        self.assertIn(
            '<a href="/volumes/%s">جلد 2</a>' % fx.V2, b)

    def test_page10_ambiguous(self):
        b = self.assert_layout(self.get("/page/10"))
        self.assertIn("متن دهم", b)
        self.assertIn(_T_PAGE10, b)
        self.assertIn("تعلق جلدی ثبت‌شده نیست", b)
        self.assertIn(
            "badge--info\">شماره در چند جلد ثبت شده — تعلق ابهام‌دار</span>",
            b)
        self.assertIn("attributed evidence", b)
        self.assertIn(_T_INVOL6, b)
        self.assertRegex(b, r'rel="prev"\s+href="/page/3"')
        self.assertIn(_T_CHIP6_4_9, b)
        self.assertRegex(b, r'rel="next"\s+href="/page/11"')

    def test_page11_empty(self):
        b = self.assert_layout(self.get("/page/11"))
        self.assertIn(
            "این صفحه در کراول بدون متن ثبت شده است (در دست بازیابی).", b)
        self.assertRegex(b, r'<span class="badge badge--muted">%s</span>'
                         % re.escape(pages.QUALITY_LABELS["empty"][1]))
        self.assertIn("صفحه 7 از 7 در", b)
        self.assertIn("تعلق جلدی ثبت‌شده نیست", b)
        self.assertNotIn("متن یازدهم", b)
        self.assertRegex(b, r'rel="prev"\s+href="/page/10"')
        self.assertRegex(b, r'rel="next"\s+href="/page/12"')

    def test_page2_dup_notice(self):
        b = self.assert_layout(self.get("/page/2"))
        self.assertIn('<h1 class="reader__heading">بحث روایی</h1>', b)
        self.assertIn("id=\"dup-notice\"", b)
        self.assertRegex(b, r"<strong>تکر\w+ شماره:</strong>")
        self.assertIn("<code>dup_rank=0</code>", b)
        self.assertIn('href="/page/2?dup_rank=1"', b)
        self.assertIn(_T_DUPLINK1, b)
        self.assertIn("متن سوم", b)
        self.assertIn(_T_INVOL3, b)
        self.assertRegex(b, r'rel="prev"\s+href="/page/1"')
        self.assertRegex(b, r'rel="next"\s+href="/page/3"')

    def test_page2_dup_rank1(self):
        b = self.assert_layout(self.get("/page/2?dup_rank=1"))
        self.assertIn("کوتاه", b)
        self.assertIn("<code>dup_rank=1</code>", b)
        # extra flag badge (short) distinct from the dup label
        self.assertRegex(b, r'<span class="badge badge--warning">%s</span>'
                         % re.escape(pages.QUALITY_LABELS["short"][1]))
        self.assertIn('href="/page/2?dup_rank=0"', b)
        self.assertIn(_T_DUPLINK0, b)
        self.assertIn(_T_INVOL4, b)

    def test_page_bad_dup_rank(self):
        for q in ("abc", "-1"):
            b = self.assert_layout(self.get("/page/2?dup_rank=" + q))
            self.assertIn("متن سوم", b)
            self.assertIn('data-dup-rank="0"', b)


class TestRecovery(SsrBase):
    def test_missing_in_gap(self):
        r = self.get("/page/5")
        self.assertEqual(r.status_code, 200)  # honest 200, not 404/500
        b = self.assert_layout(r)
        self.assertIn(
            '<article class="reader recovery" data-missing="true">', b)
        self.assertIn(
            "<h1 class=\"reader__heading\">این صفحه در دست بازیابی است</h1>",
            b)
        self.assertIn("<strong>وضعیت:</strong>", b)
        self.assertIn("item_index: <code>5</code>", b)
        self.assertIn("recovery__range", b)
        self.assertIn(_T_RECRANGE, b)
        self.assertIn(_T_RECCODES, b)
        # gap-aware nav from inside the gap
        self.assertRegex(b, r'rel="prev"\s+href="/page/3"')
        self.assertIn(_T_CHIP1_4_4, b)
        self.assertRegex(b, r'rel="next"\s+href="/page/10"')
        self.assertIn(_T_CHIP4_6_9, b)
        self.assertIn("به‌جای حدس زدن", b)

    def test_missing_beyond_max(self):
        r = self.get("/page/999")
        self.assertEqual(r.status_code, 200)
        b = self.assert_layout(r)
        self.assertIn('data-missing="true"', b)
        self.assertNotIn("recovery__range", b)  # no coverage row for 999
        self.assertRegex(b, r'rel="prev"\s+href="/page/12"')
        self.assertIn(_T_CHIP986_13_998, b)
        self.assertIn("انتهای پیکره", b)


class TestTopics(SsrBase):
    def _tids(self):
        b = self.get("/topics").get_data(as_text=True)
        tids = re.findall(r'href="/topics/(t-[0-9a-f]{12})"', b)
        self.assertEqual(len(tids), 2)
        # sort=page_count: بحث روایی (3) before پیشگفتار مفسر (1)
        order = [b.find('href="/topics/%s"' % t) for t in tids]
        self.assertTrue(order[0] < order[1])
        return tids

    def test_list(self):
        b = self.get("/topics").get_data(as_text=True)
        self.assertIn("<h1 class=\"page-head__title\">موضوعات</h1>", b)
        self.assertIn("2 موضوع ثبت‌شده.", b)
        self.assertIn(pages.TOPIC_DISCLAIMER, b)
        self.assertIn("بحث روایی", b)
        self.assertIn("3 صفحه · 2 جلد", b)
        self.assertIn("اولین: صفحه 2", b)
        self.assertIn("پیشگفتار مفسر", b)
        self.assertIn("1 صفحه · 1 جلد", b)
        self.assertIn("اولین: صفحه 0", b)

    def test_filter(self):
        b = self.get("/topics?q=بحث").get_data(as_text=True)
        self.assertIn("1 موضوع ثبت‌شده.", b)
        self.assertIn("value=\"بحث\"", b)
        self.assertIn("بحث روایی", b)
        self.assertNotIn("پیشگفتار مفسر", b)
        self.assertIn("پاک‌کردن فیلتر", b)

    def test_filter_empty(self):
        b = self.get("/topics?q=زرافه").get_data(as_text=True)
        self.assertIn("0 موضوع ثبت‌شده.", b)
        self.assertIn("موضوعی با این فیلتر پیدا نشد.", b)

    def test_detail_main(self):
        tid = self._tids()[0]
        b = self.assert_layout(self.get("/topics/" + tid))
        self.assertIn(
            "<h1 class=\"page-head__title\">بحث روایی</h1>", b)
        self.assertRegex(b, r"3 صفحه · 2 جلد\s*· اولین: صفحه 2")
        self.assertIn(pages.TOPIC_DISCLAIMER, b)
        self.assertIn("موضوع والد (بیشتر هدرها زیر):", b)
        self.assertIn("پیشگفتار مفسر", b)
        self.assertRegex(b, r"\(1 هدر\)")
        self.assertRegex(b, r"وقوع‌ها \(3\)")
        self.assertIn('href="/page/2#heading"', b)
        self.assertIn('href="/page/3#heading"', b)
        self.assertIn('href="/page/10#heading"', b)
        self.assertEqual(b.count("badge--ok\">هدر</span>"), 3)
        self.assertIn("برای اطمینان، هدرها را در صفحه‌ها ببینید", b)

    def test_detail_secondary(self):
        tid = self._tids()[1]
        b = self.assert_layout(self.get("/topics/" + tid))
        self.assertIn(
            "<h1 class=\"page-head__title\">پیشگفتار مفسر</h1>", b)
        self.assertRegex(b, r"1 صفحه · 1 جلد\s*· اولین: صفحه 0")
        self.assertNotIn("موضوع والد", b)
        self.assertRegex(b, r"وقوع‌ها \(1\)")
        self.assertIn('href="/page/0#heading"', b)
        self.assertEqual(b.count("badge--ok\">هدر</span>"), 1)

    def test_detail_404(self):
        r = self.get("/topics/nope")
        self.assertEqual(r.status_code, 404)
        b = self.assert_layout(r)
        self.assertIn("مورد پیدا نشد", b)
        self.assertIn("موضوعی با topic_id «nope» وجود ندارد.", b)


class TestSurahs(SsrBase):
    def test_surahs_honest(self):
        r = self.get("/surahs")
        self.assertEqual(r.status_code, 200)
        b = self.assert_layout(r)
        self.assertIn("<h1 class=\"page-head__title\">سوره‌ها</h1>", b)
        self.assertIn("در حال تکمیل", b)
        self.assertIn("پوشش canonical: 0/114", b)
        self.assertIn("چرا هنوز؟", b)
        self.assertIn(api.SURAH_REASON, b)
        self.assertIn(api.SURAH_PLANNED, b)
        self.assertIn("شواهد از read model", b)
        self.assertRegex(
            b, r"265 هدر.*? حاوی «سوره» همه sub-heading عمومی‌اند")
        self.assertIn("هیچ دادهٔ سوره‌ای ساخته نمی‌شود", b)
        # no fabricated surah data
        self.assertNotIn("الفاتحة", b)
        self.assertNotIn("بقره", b)


class TestSearchSsr(SsrBase):
    def test_search_hits_with_mark(self):
        r = self.get("/search?q=تفسیر")
        self.assertEqual(r.status_code, 200)
        b = self.assert_layout(r)
        self.assertIn(
            'aria-label="نتایج جستجو"', b)
        self.assertRegex(b, r"2 نتیجه برای «تفسیر»")
        self.assertEqual(b.count("<mark>تفسیر</mark>"), 2)
        self.assertIn('href="/page/0"', b)
        self.assertIn('href="/page/10"', b)
        self.assertIn("تعلق‌دهی ابهام‌دار", b)
        self.assertRegex(b, r'<a href="/page/0">پیشگفتار مفسر</a>')
        self.assertRegex(b, r'<a href="/page/10">12\) بحث روایی</a>')
        self.assertRegex(b, r"جلد 1\s*</span>")
        self.assertIn("no stemming", b)
        self.assertIn("مشاهدهٔ صفحه", b)

    def test_search_no_results(self):
        b = self.assert_layout(self.get("/search?q=زرافه"))
        self.assertRegex(b, r"نتیجه‌ای یافت نشد برای «زرافه»")
        self.assertIn("empty-state__title", b)
        self.assertIn("نتیجه‌ای یافت نشد", b)
        self.assertIn("موضوعات پرکاربرد:", b)
        self.assertIn('href="/topics?q=', b)
        self.assertNotIn("aria-label=\"نتایج جستجو\"", b)

    def test_search_short_q_400(self):
        r = self.get("/search?q=x")
        self.assertEqual(r.status_code, 400)
        b = self.assert_layout(r)
        self.assertRegex(b, r'error-card__code" dir="ltr">400')
        self.assertIn("جستجو نامعتبر", b)
        self.assertIn(
            "q باید بین ۲ تا ۶۴ کاراکتر باشد. عبارت جستجو را بررسی کنید.", b)

    def test_search_missing_q_400(self):
        r = self.get("/search")
        self.assertEqual(r.status_code, 400)
        self.assertIn("جستجو نامعتبر", r.get_data(as_text=True))

    def test_search_long_q_400(self):
        r = self.get("/search?q=" + "ز" * 65)
        self.assertEqual(r.status_code, 400)
        self.assertIn("جستجو نامعتبر", r.get_data(as_text=True))

    def test_search_no_tokens_400(self):
        r = self.get("/search?q=!!")
        self.assertEqual(r.status_code, 400)
        b = r.get_data(as_text=True)
        self.assertIn("جستجو نامعتبر", b)
        self.assertIn("هیچ توکن فارسی/عدد", b)

    def test_search_estimated_3_tokens(self):
        b = self.assert_layout(
            self.get("/search?q=قرآن روایات امامان"))
        self.assertRegex(b, r"تعداد دقیق شمارش نشده \(بیش از ۳ توکن\)")
        self.assertEqual(b.count('class="search-hit"'), 1)
        self.assertIn('href="/page/12"', b)


class TestUnknownVolume(SsrBase):
    """Unknown volume_no (NULL) -> «جلد نامشخص» + badge, everywhere."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        conn = sqlite3.connect(cls.state["db_path"])
        try:
            conn.execute("UPDATE volumes SET volume_no=NULL"
                         " WHERE volume_id=?", (fx.V2,))
            conn.commit()
        finally:
            conn.close()

    def test_detail_unknown(self):
        r = self.get("/volumes/%s" % fx.V2)
        self.assertEqual(r.status_code, 200)
        b = self.assert_layout(r)
        self.assertIn("<h1 class=\"page-head__title\">جلد 2</h1>", b)
        self.assertIn(pages.UNKNOWN_VOLUME_LABEL, b)
        self.assertRegex(b, r"شمار.* جلد در پیکره ثبت نشده است")
        self.assertIn("badge--warning\">%s</span>"
                      % pages.UNKNOWN_VOLUME_BADGE, b)
        self.assertIn("badge--info\">تعلق‌دهی ابهام‌دار</span>", b)
        self.assertIn("استراتژی: url_section", b)

    def test_grid_badge(self):
        b = self.get("/volumes").get_data(as_text=True)
        self.assertEqual(b.count("badge--warning\">%s</span>"
                                 % pages.UNKNOWN_VOLUME_BADGE), 1)

    def test_reader_label_and_crumbs(self):
        b = self.assert_layout(self.get("/page/12"))
        self.assertIn("جلد نامشخص", b)
        # the ONLY link to /volumes/fx__vol002 is the reader__vol label;
        # the breadcrumb omits the volume when it is unknown
        self.assertEqual(b.count('<a href="/volumes/%s">' % fx.V2), 1)


if __name__ == "__main__":
    unittest.main()

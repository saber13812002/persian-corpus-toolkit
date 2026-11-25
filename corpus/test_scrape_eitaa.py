"""Tests for corpus/scrape_eitaa.py — pure parsing, no network."""
import os
import unittest

import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import scrape_eitaa as es

FIXTURE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "fixtures", "eitaa_sharabebeheshti_page1.html")
with open(FIXTURE, encoding="utf-8") as _f:
    PAGE1_HTML = _f.read()
OLDEST = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                      "fixtures", "eitaa_sharabebeheshti_oldest.html")
with open(OLDEST, encoding="utf-8") as _f:
    OLDEST_HTML = _f.read()

# synthetic building blocks for variant tests (T-03)
def msg_block(post_id, classes, inner):
    return f'<div class="etme_widget_message {classes} js-widget_message" data-post="{post_id}">{inner}</div>'

DOC = (
    '<a class="etme_widget_message_document_wrap" href="/chan/{n}">'
    '<div class="etme_widget_message_document_icon accent_bg {kind}"></div>'
    '<div class="etme_widget_message_document">'
    '<div class="etme_widget_message_document_title accent_color" dir="auto">{title}</div>'
    '<div class="etme_widget_message_document_extra" dir="auto"> زمان: <time>{dur}</time>'
    '<span style="padding: 0 0 0 5px">حجم: {size}</span></div></div></a>'
)
TEXT = '<div class="etme_widget_message_text js-message_text" dir="auto">{body}</div>'
FOOTER = '<div class="etme_widget_message_footer compact js-message_footer"><div class="etme_widget_message_info short js-message_info"><span class="etme_widget_message_views" data-count="{views}">1</span><span class="etme_widget_message_meta"><a class="etme_widget_message_date" href="/chan/{n}"><time datetime="{date}" class="time">05:33</time></a></span></div></div>'


class ParseChannelTests(unittest.TestCase):
    def test_t01_parse_channel_real_page(self):
        ch = es.parse_channel(PAGE1_HTML)
        self.assertEqual(ch["username"], "sharabebeheshti")
        self.assertEqual(ch["display_name"], "موسسه شراب بهشتی")
        self.assertEqual((ch["followers_count"], ch["photos_count"],
                          ch["videos_count"], ch["files_count"]), (683, 332, 40, 4))
        self.assertIn("سایت رسمی", ch["description"])
        self.assertTrue(ch["photo_url"].startswith("/download_"))

    def test_t04_channel_url(self):
        self.assertEqual(es.channel_url("sharabebeheshti"), "https://eitaa.com/sharabebeheshti")
        self.assertEqual(es.channel_url("sharabebeheshti", 1303), "https://eitaa.com/sharabebeheshti?before=1303")
        self.assertEqual(es.extract_username("https://eitaa.com/sharabebeheshti"), "sharabebeheshti")
        self.assertEqual(es.extract_username("sharabebeheshti"), "sharabebeheshti")


class ParsePostsTests(unittest.TestCase):
    def test_t02_parse_posts_real_page(self):
        # fixture = the 12 NEWEST posts of the live channel (1303..1314, DOM order)
        posts = es.parse_posts(PAGE1_HTML)
        self.assertEqual(len(posts), 12)
        self.assertEqual(posts[0]["post_id"], "sharabebeheshti/1303")
        self.assertEqual(posts[-1]["post_id"], "sharabebeheshti/1314")
        # post 1303 (index 0): plain text post, caption links another channel
        t0 = posts[0]
        self.assertEqual(t0["post_type"], "text")
        self.assertEqual(t0["media_title"], "")
        self.assertEqual(t0["views"], 1)
        self.assertEqual(t0["url"], "https://eitaa.com/sharabebeheshti/1303")
        self.assertTrue(t0["post_date"].startswith("2026-"))
        self.assertEqual(t0["channel"], "sharabebeheshti")
        self.assertEqual(t0["post_number"], 1303)
        # post 1309 (index 6): audio with .mp3 document; caption references the channel
        a = posts[6]
        self.assertEqual(a["post_id"], "sharabebeheshti/1309")
        self.assertEqual(a["post_type"], "audio")
        self.assertTrue(a["media_title"].endswith(".mp3"))
        self.assertRegex(a["media_duration"], r"^\d+:\d{2}$")
        self.assertRegex(a["media_size"], r"^\d+(?:\.\d+)?[MKG]$")
        self.assertIn("https://eitaa.com/sharabebeheshti", a["text"])

    def test_t03_parse_posts_media_variants(self):
        video = msg_block("chan/10", "text_not_supported_wrap",
                          DOC.format(n=10, kind="video", title="x.mp4", dur="1:00", size="5M")
                          + TEXT.format(body="کپشن ویدیو")
                          + FOOTER.format(n=10, views=7, date="2023-06-01T10:00:00+00:00"))
        photo = msg_block("chan/11", "text_not_supported_wrap",
                          DOC.format(n=11, kind="image", title="photo.jpg", dur="", size="")
                          + TEXT.format(body="عکس")
                          + FOOTER.format(n=11, views=3, date="2023-06-02T10:00:00+00:00"))
        # photo document: <time> tag omitted entirely must yield "" not crash
        photo = photo.replace("<time></time>", "")
        # pinned/service post (live markup of post 1: service_message class + "سنجاق پیغام")
        pinned = msg_block("chan/1", "text_not_supported_wrap service_message",
                           TEXT.format(body="سنجاق پیغام\nآگهی")
                           + FOOTER.format(n=1, views=0, date="2023-05-05T06:34:41+00:00"))
        plain = msg_block("chan/12", "text_not_supported_wrap",
                          TEXT.format(body="A & B<br>خط دوم")
                          + FOOTER.format(n=12, views=0, date="2023-06-03T10:00:00+00:00"))
        html = "<html><body>" + video + photo + pinned + plain + "</body></html>"
        posts = es.parse_posts(html)
        self.assertEqual([p["post_type"] for p in posts], ["video", "image", "pinned", "text"])
        self.assertEqual(posts[0]["media_title"], "x.mp4")
        self.assertEqual(posts[0]["views"], 7)
        self.assertEqual(posts[1]["media_title"], "photo.jpg")
        self.assertEqual(posts[1]["media_duration"], "")
        self.assertEqual(posts[1]["media_size"], "")
        self.assertEqual(posts[2]["post_number"], 1)
        self.assertEqual(posts[2]["post_date"], "2023-05-05T06:34:41+00:00")
        self.assertEqual(posts[3]["text"], "A & B\nخط دوم")

    def test_t05_parse_posts_empty_page(self):
        self.assertEqual(es.parse_posts("<html><body><h1>404</h1></body></html>"), [])
        self.assertEqual(es.parse_posts(""), [])

    def test_t03b_next_page_url_and_terminal(self):
        self.assertEqual(es.next_page_url(PAGE1_HTML), "https://eitaa.com/sharabebeheshti?before=1303")
        # oldest page: no more anchor → "" (terminal stop); it holds the pinned post 1
        self.assertEqual(es.next_page_url(OLDEST_HTML), "")
        posts = es.parse_posts(OLDEST_HTML)
        self.assertEqual([p["post_id"] for p in posts][:3],
                         ["sharabebeheshti/1", "sharabebeheshti/2", "sharabebeheshti/3"])
        self.assertEqual(posts[0]["post_type"], "pinned")
        self.assertEqual(es.next_page_url("<html><body></body></html>"), "")


class FakeResponse:
    def __init__(self, text="", status_code=200):
        self.text = text
        self.status_code = status_code

    def json(self):
        import json as json_mod
        return json_mod.loads(self.text) if self.text else {}


class FakeSession:
    def __init__(self, pages=None):
        self.pages = dict(pages or {})
        self.calls = []

    def get(self, url, timeout=None):
        self.calls.append(("GET", url))
        return FakeResponse(self.pages.get(url, ""), 200)

    def post(self, url, json=None, timeout=None):
        self.calls.append(("POST", url, json))
        import json as json_mod
        return FakeResponse(json_mod.dumps({"status": "inserted"}), 200)


class ErrorSession:
    def get(self, url, timeout=None):
        raise RuntimeError("boom")


def synth_page(user, ids, before=None):
    # latest-first page: ids in DOM order (oldest of the page first, like the live site)
    parts = [msg_block(f"{user}/{n}", "text_not_supported_wrap",
                       TEXT.format(body=f"کپشن {n}")
                       + FOOTER.format(n=n, views=1, date="2023-05-14T05:33:00+00:00"))
             for n in ids]
    parts.append('<div class="etme_widget_message_centered js-messages_more_wrap" dir="auto">'
                 + (f'<a href="/{user}?before={before}&q=" class="eme_messages_more js-messages_more" data-before="{before}"><span>مطالب قبلی</span></a>' if before else "")
                 + "</div>")
    return f'<main class="etme_main" data-url="/{user}"><section>' + "".join(parts) + "</section></main>"


class CrawlChannelTests(unittest.TestCase):
    def _two_page_session(self):
        return FakeSession({
            "https://eitaa.com/chan": synth_page("chan", [1303, 1304, 1305], before=1303),
            "https://eitaa.com/chan?before=1303": synth_page("chan", [1291, 1292]),
        })

    def test_t07_crawl_two_pages_frontier(self):
        sess = self._two_page_session()
        res = es.crawl_channel("chan", session=sess, delay=0, sleep=lambda s: None)
        self.assertEqual((res["pages"], res["posts"], res["inserted"]), (2, 5, 5))
        subs = [c for c in sess.calls if c[0] == "POST" and c[1].endswith("/api/eitaa/submit")]
        self.assertEqual(len(subs), 5)
        self.assertEqual(subs[2][2]["page_url"], "https://eitaa.com/chan")
        self.assertEqual(subs[2][2]["next_url"], "https://eitaa.com/chan?before=1303")
        self.assertEqual(subs[-1][2]["page_url"], "https://eitaa.com/chan?before=1303")
        self.assertEqual(subs[-1][2]["next_url"], "")
        api_calls = [c for c in sess.calls if c[0] == "POST"]
        self.assertTrue(any(c[1].endswith("/api/eitaa/channel") for c in api_calls))
        self.assertTrue(any(c[1].endswith("/api/eitaa/seed") for c in api_calls))

    def test_t08_crawl_stops_on_network_error(self):
        res = es.crawl_channel("chan", session=ErrorSession(), delay=0,
                               sleep=lambda s: None, retries=2)
        self.assertEqual(res["errors"], 1)
        self.assertEqual(res["posts"], 0)

    def test_t09_crawl_stops_on_two_empty_pages(self):
        sess = FakeSession({
            "https://eitaa.com/chan": synth_page("chan", [], before=12),
            "https://eitaa.com/chan?before=12": synth_page("chan", [], before=24),
            "https://eitaa.com/chan?before=24": synth_page("chan", [1]),
        })
        res = es.crawl_channel("chan", session=sess, delay=0, sleep=lambda s: None)
        self.assertEqual(res["pages"], 2)
        self.assertEqual(res["posts"], 0)
        self.assertEqual([c[1] for c in sess.calls if c[0] == "GET"],
                         ["https://eitaa.com/chan", "https://eitaa.com/chan?before=12"])

    def test_t10_max_pages(self):
        res = es.crawl_channel("chan", session=self._two_page_session(),
                               delay=0, sleep=lambda s: None, max_pages=1)
        self.assertEqual(res["pages"], 1)
        self.assertEqual(res["posts"], 3)

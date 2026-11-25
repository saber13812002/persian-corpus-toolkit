"""API tests for Eitaa channel registration + post submission (EA-01..EA-08)."""
import sqlite3
import unittest

import pct_test_support  # noqa: F401  (MUST precede `import server`)
import server  # noqa: E402

CHANNEL = {
    "username": "sharabebeheshti",
    "display_name": "موسسه شراب بهشتی",
    "description": "ادمین\n@sabertaba",
    "followers_count": 683,
    "photos_count": 332,
    "videos_count": 40,
    "files_count": 4,
    "photo_url": "/download_b591189e?token=abc",
}

POST = {
    "post_id": "sharabebeheshti/2",
    "channel": "sharabebeheshti",
    "post_number": 2,
    "post_type": "audio",
    "media_title": "Sharab-e-Beheshti01 - Vaghee.mp3",
    "media_duration": "17:50",
    "media_size": "17.2M",
    "text": "دانلود کامل 5 فصل:\n1-نهج البلاغه",
    "post_date": "2023-05-14T05:33:18+00:00",
    "views": 1,
    "url": "https://eitaa.com/sharabebeheshti/2",
}

PAGE1 = "https://eitaa.com/sharabebeheshti"
PAGE2 = "https://eitaa.com/sharabebeheshti?before=1303"


class EitaaApiTests(unittest.TestCase):
    def setUp(self):
        pct_test_support.reset_db()
        db = sqlite3.connect(server.DB_PATH)
        server.ensure_eitaa_schema(db)
        db.close()
        self.client = server.app.test_client()

    def test_ea01_channel_upsert(self):
        self.assertEqual(self.client.post("/api/eitaa/channel", json=CHANNEL).get_json()["status"], "inserted")
        self.assertEqual(self.client.post("/api/eitaa/channel", json=CHANNEL).get_json()["status"], "skipped")
        self.assertEqual(self.client.post("/api/eitaa/channel", json=dict(CHANNEL, followers_count=700)).get_json()["status"], "updated")
        self.assertEqual(self.client.post("/api/eitaa/channel", json={}).status_code, 400)

    def test_ea02_post_insert(self):
        self.assertEqual(self.client.post("/api/eitaa/submit", json=POST).get_json()["status"], "inserted")
        db = sqlite3.connect(server.DB_PATH)
        db.row_factory = sqlite3.Row
        row = db.execute("SELECT * FROM eitaa_posts WHERE post_id=?", (POST["post_id"],)).fetchone()
        db.close()
        self.assertEqual(row["media_title"], "Sharab-e-Beheshti01 - Vaghee.mp3")
        self.assertEqual(row["media_duration"], "17:50")
        self.assertEqual(row["media_size"], "17.2M")
        self.assertEqual(row["post_date"], "2023-05-14T05:33:18+00:00")
        self.assertEqual(row["char_count"], len(POST["text"]))
        self.assertIn("Sharab-e-Beheshti01", row["full_data"])

    def test_ea03_resubmit_same_skipped_views_ignored(self):
        self.client.post("/api/eitaa/submit", json=POST)
        self.assertEqual(self.client.post("/api/eitaa/submit", json=POST).get_json()["status"], "skipped")
        # views is volatile — a change in views alone must NOT trigger an update
        self.assertEqual(self.client.post("/api/eitaa/submit", json=dict(POST, views=5)).get_json()["status"], "skipped")

    def test_ea04_changed_post_updated(self):
        self.client.post("/api/eitaa/submit", json=POST)
        self.assertEqual(self.client.post("/api/eitaa/submit", json=dict(POST, text="متن جدید")).get_json()["status"], "updated")

    def test_ea05_empty_post_not_stored(self):
        body = dict(POST, text="", media_title="", media_duration="", media_size="", post_type="text")
        self.assertEqual(self.client.post("/api/eitaa/submit", json=body).get_json()["status"], "empty")
        db = sqlite3.connect(server.DB_PATH)
        n = db.execute("SELECT COUNT(*) FROM eitaa_posts").fetchone()[0]
        db.close()
        self.assertEqual(n, 0)

    def _post(self, i, text="تست"):
        return self.client.post("/api/eitaa/submit", json=dict(
            POST, post_id=f"c/{i}", channel="c", post_number=i,
            url=f"https://eitaa.com/c/{i}", post_type="text",
            media_title="", media_duration="", media_size="", text=text))

    def test_ea06_stats(self):
        self.client.post("/api/eitaa/channel", json=CHANNEL)
        self.client.post("/api/eitaa/submit", json=POST)
        self._post(3, "متن ساده")
        s = self.client.get("/api/eitaa/stats").get_json()
        self.assertEqual(s["channels"], 1)
        self.assertEqual(s["posts"], 2)
        self.assertEqual(s["by_type"], {"audio": 1, "text": 1})
        self.assertGreater(s["chars"], 0)

    def test_ea07_posts_listing_pagination(self):
        for i in range(1, 16):
            self._post(i, f"t{i}")
        p1 = self.client.get("/api/eitaa/posts?channel=c&limit=10&offset=0").get_json()
        self.assertEqual(p1["total"], 15)
        self.assertEqual([p["post_number"] for p in p1["posts"]], list(range(1, 11)))
        p2 = self.client.get("/api/eitaa/posts?channel=c&limit=10&offset=10").get_json()
        self.assertEqual([p["post_number"] for p in p2["posts"]], list(range(11, 16)))

    def test_ea08_frontier_and_reset(self):
        self.client.post("/api/eitaa/channel", json=CHANNEL)
        self.assertEqual(self.client.post("/api/eitaa/seed", json={"channel": "sharabebeheshti"}).get_json()["added"], 1)
        self.assertEqual(self.client.post("/api/eitaa/seed", json={"channel": "sharabebeheshti"}).get_json()["added"], 0)
        self.assertEqual(self.client.get("/api/eitaa/pending").get_json()["urls"], [PAGE1])
        # a post submitted from PAGE1 carries the frontier to PAGE2
        self.client.post("/api/eitaa/submit", json=dict(POST, page_url=PAGE1, next_url=PAGE2))
        self.assertEqual(self.client.get("/api/eitaa/pending").get_json()["urls"], [PAGE2])
        st = self.client.get("/api/eitaa/crawl-status?channel=sharabebeheshti").get_json()
        self.assertTrue(st["channel_registered"])
        self.assertEqual(st["posts"], 1)
        self.assertEqual(st["max_post_number"], 2)
        self.assertEqual(st["pending"], 1)
        r = self.client.post("/api/eitaa/reset").get_json()
        self.assertEqual(r["deleted_posts"], 1)
        self.assertEqual(r["deleted_channels"], 1)
        self.assertEqual(self.client.get("/api/eitaa/pending").get_json()["count"], 0)
        self.assertEqual(self.client.get("/api/eitaa/posts").get_json()["total"], 0)

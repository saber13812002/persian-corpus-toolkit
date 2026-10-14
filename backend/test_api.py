"""API tests for date normalization and one khamenei save."""
import os
import sqlite3
import tempfile
import unittest

_fd, _DB = tempfile.mkstemp(suffix=".db")
os.close(_fd)
os.environ["PCT_DB"] = _DB

import server  # noqa: E402


class ApiTests(unittest.TestCase):
    def setUp(self):
        if os.path.exists(_DB):
            os.remove(_DB)
        server.init_db()
        db = sqlite3.connect(server.DB_PATH)
        server.ensure_khamenei_schema(db)
        db.close()
        self.client = server.app.test_client()

    def test_jalali_digits(self):
        self.assertEqual(server.normalize_jalali_date("۱۴۰۴/۰۱/۱۵"), "1404/01/15")
        self.assertEqual(server.jalali_year("۱۴۰۴/۰۱/۱۵"), "1404")

    def test_khamenei_submit_stores_date(self):
        resp = self.client.post(
            "/api/khamenei/submit",
            json={
                "speech_id": "999001",
                "title": "تست",
                "date": "۱۴۰۴/۰۱/۱۵",
                "content": "متن آزمایشی بیان",
                "url": "https://farsi.khamenei.ir/speech-content?id=999001",
            },
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.get_json()
        self.assertEqual(body["status"], "inserted")
        self.assertEqual(body["date"], "1404/01/15")
        self.assertEqual(body["year"], "1404")

        stats = self.client.get("/api/khamenei/stats").get_json()
        self.assertEqual(stats["total"], 1)
        self.assertEqual(stats["with_date"], 1)
        self.assertEqual(stats["by_year"]["1404"], 1)

    def test_stats_ok(self):
        body = self.client.get("/api/stats").get_json()
        self.assertIn("crawled_total", body)
        self.assertEqual(body["crawled_total"], 0)


if __name__ == "__main__":
    unittest.main()

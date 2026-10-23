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

    def test_hamtaa_fields_and_capture(self):
        match = self.client.get("/api/sites/match?host=tasnim.hamtaa.org").get_json()
        tags = {f["tag"]: f for f in match["fields"]}
        self.assertEqual(tags["page"]["transform"], "add_one")
        self.assertEqual(tags["page"]["selector"], "item_index")
        self.assertEqual(tags["surah"]["transform"], "before_paren")
        url = "https://tasnim.hamtaa.org/payload?file_id=10&item_index=358"
        values = {
            "surah": "آلِ عِمْرَان",
            "ayah": "66",
            "volume": "10",
            "page": "359",
            "arabic": "هَا أَنْتُمْ",
            "url": url,
        }
        saved = self.client.post(
            "/api/captures", json={"host": "tasnim.hamtaa.org", "url": url, "values": values}
        ).get_json()
        self.assertEqual(saved["status"], "inserted")
        again = self.client.post(
            "/api/captures", json={"host": "tasnim.hamtaa.org", "url": url, "values": values}
        ).get_json()
        self.assertEqual(again["status"], "skipped")
        listed = self.client.get("/api/captures?host=tasnim.hamtaa.org").get_json()
        self.assertEqual(listed["items"][0]["values"]["page"], "359")
        self.assertEqual(listed["items"][0]["values"]["ayah"], "66")

    def test_project_points_then_page_marks_tested(self):
        created = self.client.post(
            "/api/projects",
            json={
                "name": "تفسیر تسنیم",
                "host": "tasnim.hamtaa.org",
                "start_url": "https://tasnim.hamtaa.org/payload?file_id=10&item_index=400",
                "next_mode": "url_param",
                "next_param": "item_index",
                "next_step": 1,
                "pages_per_minute": 4,
            },
        ).get_json()
        self.assertTrue(created["ok"])
        project = created["project"]
        self.assertEqual(project["status"], "draft")
        self.assertEqual(project["points"], [])
        pid = project["id"]

        saved = self.client.post(
            f"/api/projects/{pid}/points",
            json={
                "tag": "tafsir",
                "source": "css",
                "selector": "main article",
                "transform": "text",
                "sample": "متن تفسیر",
            },
        ).get_json()
        self.assertEqual(saved["project"]["points"][0]["tag"], "tafsir")

        renamed = self.client.post(
            f"/api/projects/{pid}/points",
            json={
                "previous_tag": "tafsir",
                "tag": "متن",
                "source": "css",
                "selector": ".book-tafsir",
                "transform": "text",
                "sample": "تفسیر آیه",
            },
        ).get_json()
        tags = [p["tag"] for p in renamed["project"]["points"]]
        self.assertEqual(tags, ["متن"])

        empty = self.client.post(
            f"/api/projects/{pid}/pages",
            json={"url": "https://tasnim.hamtaa.org/payload?file_id=10&item_index=400", "values": {"متن": ""}},
        )
        self.assertEqual(empty.status_code, 422)

        page = self.client.post(
            f"/api/projects/{pid}/pages",
            json={
                "url": "https://tasnim.hamtaa.org/payload?file_id=10&item_index=400",
                "values": {"متن": "این متن تفسیر است"},
            },
        ).get_json()
        self.assertEqual(page["status"], "inserted")
        self.assertEqual(page["project"]["status"], "tested")
        self.assertEqual(page["project"]["saved_count"], 1)
        self.assertIsNotNone(page["project"]["tested_at"])

        report = self.client.post(
            f"/api/projects/{pid}/report",
            json={"saved": 1, "status": "running", "message": "۱ صفحه ذخیره شد", "cursor_url": "https://tasnim.hamtaa.org/payload?file_id=10&item_index=401"},
        ).get_json()
        self.assertEqual(report["project"]["saved_count"], 2)
        self.assertEqual(report["project"]["status"], "running")
        self.assertIn("item_index=401", report["project"]["cursor_url"])

    def test_create_project_validation_errors(self):
        missing = self.client.post("/api/projects", json={"name": "تست"})
        self.assertEqual(missing.status_code, 400)
        bad_mode = self.client.post(
            "/api/projects",
            json={"name": "تست", "host": "example.org", "next_mode": "bogus"},
        )
        self.assertEqual(bad_mode.status_code, 400)
        ok = self.client.post(
            "/api/projects",
            json={"name": "تست", "host": "Example.ORG", "start_url": "https://example.org/p?item_index=5#frag"},
        ).get_json()
        self.assertTrue(ok["ok"])
        self.assertEqual(ok["project"]["host"], "example.org")
        self.assertEqual(ok["project"]["start_url"], "https://example.org/p?item_index=5")
        self.assertEqual(ok["project"]["status"], "draft")

    def test_project_read_and_report_flow(self):
        created = self.client.post(
            "/api/projects",
            json={"name": "آزمایش", "host": "tasnim.hamtaa.org"},
        ).get_json()
        pid = created["project"]["id"]
        loaded = self.client.get(f"/api/projects/{pid}").get_json()
        self.assertEqual(loaded["name"], "آزمایش")
        self.assertEqual(loaded["points"], [])
        report = self.client.post(
            f"/api/projects/{pid}/report",
            json={"failed": 1, "message": "صفحه خالی بود", "status": "paused"},
        ).get_json()
        self.assertEqual(report["project"]["failed_count"], 1)
        self.assertEqual(report["project"]["status"], "paused")
        self.assertEqual(report["project"]["last_message"], "صفحه خالی بود")
        listed = self.client.get("/api/projects?host=tasnim.hamtaa.org").get_json()
        self.assertGreaterEqual(len(listed["projects"]), 1)
        missing = self.client.get("/api/projects/99999")
        self.assertEqual(missing.status_code, 404)

    def test_define_new_site_tag(self):
        saved = self.client.post(
            "/api/sites/fields",
            json={
                "host": "example.org",
                "name": "نمونه",
                "tag": "title",
                "source": "css",
                "selector": "h1",
                "transform": "text",
                "sample": "سلام",
            },
        ).get_json()
        self.assertTrue(saved["ok"])
        self.assertEqual(saved["fields"][0]["tag"], "title")


if __name__ == "__main__":
    unittest.main()

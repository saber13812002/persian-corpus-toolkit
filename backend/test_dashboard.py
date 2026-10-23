"""Dashboard read-APIs (PCM-04) + dashboard authentication (PCM-09) tests.

Covers:
  A01 auth status, A02 401 before login, A03 wrong password, A04 login ok,
  A05 data visible after login, A06 logout invalidates session,
  A07 rate limit on repeated failures, A08 extension write APIs stay open
  (live crawl is never interrupted by the dashboard login),
  D01 pagination, D02 search, D03 status filter, D04 sorting,
  D05 detail (fields + pages summary + values sample), D06 detail 404,
  D07 additive created_at migration.

Note: every request goes through `with self.client:` so Flask's
teardown_appcontext closes the per-request SQLite connection — required
on Windows, where an open handle blocks os.remove() of the test DB.
"""
import os
import tempfile
import unittest

_fd, _DB = tempfile.mkstemp(suffix=".db")
os.close(_fd)
os.environ["PCT_DB"] = _DB
# Set BEFORE server.init_db() so the password gets hashed + seeded.
os.environ["PCT_DASHBOARD_PASSWORD"] = "test-secret-123"

import server  # noqa: E402

PW = "test-secret-123"
N_PROJ = 15


class Base(unittest.TestCase):
    def setUp(self):
        if os.path.exists(_DB):
            os.remove(_DB)
        server.init_db()
        self.client = server.app.test_client()

    def req(self, method, path, **kw):
        with self.client as c:
            return getattr(c, method)(path, **kw)

    def get(self, path, **kw):
        return self.req("get", path, **kw)

    def post(self, path, **kw):
        return self.req("post", path, **kw)

    def login(self, password=PW):
        return self.post("/api/auth/login", json={"password": password})

    def make_project(self, name, host="tasnim.hamtaa.org", **kw):
        r = self.post("/api/projects", json={"name": name, "host": host, **kw})
        return r.get_json()["project"]["id"]


# ── PCM-09: authentication ──────────────────────────────────────

class AuthTests(Base):
    # A01 — status endpoint reports auth enabled, not yet authenticated
    def test_A01_status(self):
        d = self.get("/api/auth/status").get_json()
        self.assertTrue(d["auth_enabled"])
        self.assertFalse(d["authenticated"])

    # A02 — protected dashboard API returns 401 before login
    def test_A02_dashboard_401(self):
        self.assertEqual(self.get("/api/dashboard/projects").status_code, 401)

    # A03 — wrong password is rejected (and counted)
    def test_A03_wrong_password(self):
        self.assertEqual(self.login("nope").status_code, 401)
        self.assertFalse(self.get("/api/auth/status").get_json()["authenticated"])
        self.assertEqual(self.get("/api/dashboard/projects").status_code, 401)

    # A04 — correct password logs in (session cookie set)
    def test_A04_login_ok(self):
        r = self.login()
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["ok"])
        self.assertTrue(self.get("/api/auth/status").get_json()["authenticated"])

    # A05 — after login the dashboard data APIs answer
    def test_A05_data_after_login(self):
        self.login()
        r = self.get("/api/dashboard/projects")
        self.assertEqual(r.status_code, 200)
        self.assertIn("projects", r.get_json())

    # A06 — logout revokes the session
    def test_A06_logout(self):
        self.login()
        self.post("/api/auth/logout")
        self.assertFalse(self.get("/api/auth/status").get_json()["authenticated"])
        self.assertEqual(self.get("/api/dashboard/projects").status_code, 401)

    # A07 — 5 failures in a row -> rate limited (429), even correct password
    def test_A07_rate_limit(self):
        for _ in range(5):
            self.assertEqual(self.login("bad").status_code, 401)
        self.assertEqual(self.login(PW).status_code, 429)

    # A08 — extension write APIs stay open: a live crawl never breaks
    def test_A08_write_apis_open(self):
        pid = self.make_project("no-auth-write", next_mode="url_param", next_param="item_index")
        r = self.post(f"/api/projects/{pid}/pages", json={
            "url": "https://tasnim.hamtaa.org/payload?item_index=1",
            "values": {"متن": "hello"},
        })
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["ok"])


# ── PCM-04: dashboard read APIs (logged in) ─────────────────────

class DashboardApiTests(Base):
    def setUp(self):
        super().setUp()
        self.login()
        for i in range(N_PROJ):
            self.make_project(f"Proj-{i:02d}")
        # one project with data: fields + 3 pages
        self.pid = self.make_project("DataProj")
        self.post(f"/api/projects/{self.pid}/points", json={
            "tag": "متن", "source": "css", "selector": "p.book-text", "transform": "text",
        })
        for i in range(3):
            self.post(f"/api/projects/{self.pid}/pages", json={
                "url": f"https://tasnim.hamtaa.org/payload?item_index={i}",
                "values": {"متن": f"متن صفحه {i}"},
            })
        self.post(f"/api/projects/{self.pid}", json={"status": "running"})

    # D01 — pagination math
    def test_D01_pagination(self):
        # setUp creates N_PROJ + DataProj = N_PROJ + 1 projects total
        total = N_PROJ + 1
        d = self.get("/api/dashboard/projects?per_page=10").get_json()
        self.assertEqual(d["total"], total)
        self.assertEqual(len(d["projects"]), 10)
        self.assertEqual(d["total_pages"], 2)
        d2 = self.get("/api/dashboard/projects?per_page=10&page=2").get_json()
        self.assertEqual(len(d2["projects"]), total - 10)

    # D02 — search by name or host
    def test_D02_search(self):
        d = self.get("/api/dashboard/projects?search=Proj-07").get_json()
        self.assertEqual(d["total"], 1)
        self.assertEqual(d["projects"][0]["name"], "Proj-07")
        d2 = self.get("/api/dashboard/projects?search=tasnim").get_json()
        self.assertGreater(d2["total"], 5)

    # D03 — status filter
    def test_D03_status_filter(self):
        d = self.get("/api/dashboard/projects?status=running").get_json()
        self.assertEqual(d["total"], 1)
        self.assertEqual(d["projects"][0]["name"], "DataProj")
        d2 = self.get("/api/dashboard/projects?status=draft").get_json()
        self.assertEqual(d2["total"], N_PROJ)

    # D04 — sorting by saved_count DESC puts the data project first
    def test_D04_sort(self):
        d = self.get(
            "/api/dashboard/projects?sort=saved_count&order=DESC&per_page=10"
        ).get_json()
        self.assertEqual(d["projects"][0]["name"], "DataProj")
        self.assertGreaterEqual(d["projects"][0]["saved_count"], 3)

    # D05 — detail: fields, pages summary, last values sample
    def test_D05_detail(self):
        d = self.get(f"/api/dashboard/projects/{self.pid}").get_json()
        self.assertEqual(d["id"], self.pid)
        self.assertEqual(d["status"], "running")
        self.assertEqual(len(d["points"]), 1)
        self.assertEqual(d["points"][0]["tag"], "متن")
        self.assertEqual(d["pages_summary"]["total"], 3)
        self.assertIn("item_index=2", d["pages_summary"]["last_url"])
        self.assertEqual(d["values_sample"]["متن"], "متن صفحه 2")
        # list view exposes the same counts
        lst = self.get("/api/dashboard/projects?search=DataProj").get_json()
        self.assertEqual(lst["projects"][0]["fields_count"], 1)
        self.assertEqual(lst["projects"][0]["pages_count"], 3)

    # D06 — unknown project -> 404
    def test_D06_detail_404(self):
        self.assertEqual(self.get("/api/dashboard/projects/9999").status_code, 404)

    # D07 — created_at column exists and is populated (additive migration)
    def test_D07_created_at(self):
        d = self.get("/api/dashboard/projects?search=DataProj").get_json()
        self.assertIn("created_at", d["projects"][0])
        self.assertTrue(d["projects"][0]["created_at"])


if __name__ == "__main__":
    unittest.main()

# -*- coding: utf-8 -*-
"""test_studio_api — PCM-17: Studio UI backend surface (batches list + registry ids).

Coverage (S-01..S-04):
  S-01 GET /api/knowledge/import/batches — list shape + auth/validation:
       unauthenticated 401; missing collection_id 400 (field=collection_id);
       unknown collection 404; a created batch appears with the full row
       shape (batch_id/folder_name/file_count/processed_count/failed_count/
       status + paused flag); pagination fields + per_page cap; search
       filters by batch_id/folder_name.
  S-02 pause/resume are reflected in the LIST as paused=1 / paused=0
       (the UI's «توقف‌شده» badge is driven by this field).
  S-03 the list's queue.counters must equal a direct DB recompute of
       knowledge_file_queue (single source of truth, AGENTS §2.9).
  S-04 GET /api/knowledge/collections/<id>/documents carries work_id /
       edition_id / volume_id after a real WF run (the UI's رجیستری
       column is driven by these fields); they are NULL/None before the
       document is processed.

Follows the PCM-12.3 rule: import pct_test_support FIRST, then server.
"""
import hashlib
import io
import json
import os
import shutil
import sqlite3
import tempfile
import time
import unittest
from unittest import mock

import pct_test_support  # noqa: F401  (must precede `import server`)

import server

PW = "test-secret-123"


class Base(unittest.TestCase):
    def setUp(self):
        pct_test_support.reset_db()
        self._datadir = tempfile.mkdtemp(prefix="pct-studio-")
        self._old_dd = os.environ.get("PCT_KNOWLEDGE_DATA_DIR")
        os.environ["PCT_KNOWLEDGE_DATA_DIR"] = self._datadir
        self.client = server.app.test_client()

    def tearDown(self):
        if self._old_dd is None:
            os.environ.pop("PCT_KNOWLEDGE_DATA_DIR", None)
        else:
            os.environ["PCT_KNOWLEDGE_DATA_DIR"] = self._old_dd
        shutil.rmtree(self._datadir, ignore_errors=True)

    def login(self, password=PW):
        return self.client.post(
            "/api/auth/login", json={"password": password}
        )

    def make_collection(self, name="کتابخانه آزمون", slug="studio-test"):
        r = self.client.post(
            "/api/knowledge/collections",
            json={"name": name, "slug": slug},
        )
        self.assertEqual(r.status_code, 201, r.get_data(as_text=True))
        return r.get_json()["collection"]

    @staticmethod
    def sha256_file(path):
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        return h.hexdigest()

    def upload(self, coll_id, path, name=None):
        with open(path, "rb") as f:
            data = {"file": (io.BytesIO(f.read()), name or os.path.basename(path))}
        return self.client.post(
            f"/api/knowledge/collections/{coll_id}/documents",
            data=data, content_type="multipart/form-data",
        )

    def wait_job(self, job_id, timeout=30.0):
        deadline = time.time() + timeout
        while time.time() < deadline:
            j = self.client.get("/api/knowledge/jobs").get_json()
            row = next((x for x in j["jobs"] if x["job_id"] == job_id), None)
            if row and row["status"] in ("succeeded", "failed", "interrupted"):
                return row
            time.sleep(0.2)
        self.fail(f"job {job_id} did not finish within {timeout}s")

    def _db(self):
        conn = sqlite3.connect(server.DB_PATH, timeout=60)
        conn.row_factory = sqlite3.Row
        return conn

    def _make_book(self, name="book.docx"):
        from factory._smoke_fixtures import make_sample_book
        tmp = tempfile.mkdtemp(prefix="pct-studio-src-")
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        return make_sample_book(os.path.join(tmp, name))

    def _make_batch(self, coll_id, files, folder_name=None):
        r = self.client.post("/api/knowledge/import/batches", json={
            "collection_id": coll_id,
            "folder_name": folder_name or "pct17 folder",
            "files": files,
        })
        self.assertEqual(r.status_code, 201, r.get_data(as_text=True))
        return r.get_json()

    def _file_entry(self, path, name=None):
        return {"name": name or os.path.basename(path),
                "size": os.path.getsize(path),
                "sha256": self.sha256_file(path)}

    def _process_batch(self, batch_id):
        r = self.client.post(f"/api/knowledge/import/batches/{batch_id}/process")
        self.assertIn(r.status_code, (200, 202), r.get_data(as_text=True))
        return r.get_json()

    def _docs(self, coll_id):
        return self.client.get(
            f"/api/knowledge/collections/{coll_id}/documents"
        ).get_json()["documents"]

    def _list_batches(self, cid, **params):
        q = {"collection_id": cid}
        q.update(params)
        return self.client.get(
            "/api/knowledge/import/batches?" + "&".join(
                f"{k}={v}" for k, v in q.items())
        )


class TestS01_ListShape(Base):
    """S-01: GET /import/batches — auth, validation, row shape, search."""

    def test_s01a_unauthenticated_401(self):
        # auth is checked before any parameter/collection validation,
        # so any (even unknown) collection_id must 401 while logged out
        r = self.client.get(
            "/api/knowledge/import/batches?collection_id=c-any")
        self.assertEqual(r.status_code, 401)

    def test_s01b_missing_collection_id_400(self):
        self.login()
        r = self.client.get("/api/knowledge/import/batches")
        self.assertEqual(r.status_code, 400)
        j = r.get_json()
        self.assertEqual(j["field"], "collection_id")

    def test_s01c_unknown_collection_404(self):
        self.login()
        r = self._list_batches("c-doesnotexist")
        self.assertEqual(r.status_code, 404)

    def test_s01d_row_shape_and_pagination(self):
        self.login()
        coll = self.make_collection(slug="s01")
        good1 = self._make_book("one.docx")
        good2 = self._make_book("two.docx")
        self.upload(coll["id"], good1)
        self.upload(coll["id"], good2)
        p1 = self._make_batch(coll["collection_id"],
                              [self._file_entry(good1)], "alpha folder")
        p2 = self._make_batch(coll["collection_id"],
                              [self._file_entry(good2)], "beta folder")
        b1 = p1["batch"]["batch_id"]
        b2 = p2["batch"]["batch_id"]

        r = self._list_batches(coll["collection_id"])
        self.assertEqual(r.status_code, 200, r.get_data(as_text=True))
        j = r.get_json()
        for key in ("batches", "total", "page", "per_page", "total_pages",
                    "queue"):
            self.assertIn(key, j)
        self.assertEqual(j["total"], 2)
        self.assertEqual(j["page"], 1)
        self.assertEqual(j["per_page"], 50)
        self.assertEqual(j["total_pages"], 1)
        # counters are present with the full PCM-15 key set
        for k in ("total", "pending", "running", "succeeded",
                  "needs_review", "failed", "failed_with_safe_stage",
                  "attempts_total"):
            self.assertIn(k, j["queue"]["counters"])
        self.assertIsInstance(j["queue"]["failed_by_stage"], list)

        by_id = {b["batch_id"]: b for b in j["batches"]}
        self.assertEqual(set(by_id), {b1, b2})
        row = by_id[b1]
        for k in ("batch_id", "collection_id", "folder_name", "file_count",
                  "processed_count", "failed_count", "status", "created_at",
                  "updated_at", "paused"):
            self.assertIn(k, row)
        self.assertEqual(row["folder_name"], "alpha folder")
        self.assertEqual(row["file_count"], 1)
        self.assertEqual(row["processed_count"], 0)
        self.assertEqual(row["failed_count"], 0)
        self.assertEqual(row["status"], "planned")
        self.assertEqual(row["paused"], 0)

        # search: matches folder_name only of the first batch
        j2 = self._list_batches(coll["collection_id"],
                                search="alpha folder").get_json()
        self.assertEqual(j2["total"], 1)
        self.assertEqual(j2["batches"][0]["batch_id"], b1)
        # search: no match -> empty, total 0
        j3 = self._list_batches(coll["collection_id"],
                                search="nope-not-here").get_json()
        self.assertEqual(j3["total"], 0)
        self.assertEqual(j3["batches"], [])

        # pagination: per_page=1 -> two pages, first row is the newest
        j4 = self._list_batches(coll["collection_id"], per_page=1).get_json()
        self.assertEqual(j4["total"], 2)
        self.assertEqual(j4["total_pages"], 2)
        self.assertEqual(len(j4["batches"]), 1)
        j5 = self._list_batches(coll["collection_id"],
                                per_page=1, page=2).get_json()
        self.assertEqual(len(j5["batches"]), 1)
        self.assertNotEqual(j4["batches"][0]["batch_id"],
                            j5["batches"][0]["batch_id"])
        # per_page is capped at 100
        j6 = self._list_batches(coll["collection_id"], per_page=500).get_json()
        self.assertEqual(j6["per_page"], 100)


class TestS02_PausedFlag(Base):
    """S-02: pause/resume must be visible in the list as paused=1/0."""

    def test_s02_pause_reflected_in_list(self):
        self.login()
        coll = self.make_collection(slug="s02")
        good = self._make_book("good.docx")
        self.upload(coll["id"], good)
        plan = self._make_batch(coll["collection_id"],
                                [self._file_entry(good)])
        bid = plan["batch"]["batch_id"]

        r = self._list_batches(coll["collection_id"]).get_json()
        self.assertEqual(r["batches"][0]["paused"], 0)

        r = self.client.post(f"/api/knowledge/import/batches/{bid}/pause")
        self.assertEqual(r.status_code, 200, r.get_data(as_text=True))
        r = self._list_batches(coll["collection_id"]).get_json()
        self.assertEqual(r["batches"][0]["paused"], 1)

        r = self.client.post(f"/api/knowledge/import/batches/{bid}/resume")
        self.assertEqual(r.status_code, 200)
        r = self._list_batches(coll["collection_id"]).get_json()
        self.assertEqual(r["batches"][0]["paused"], 0)


class TestS03_CountersMatch(Base):
    """S-03: list queue.counters == direct DB recompute."""

    def test_s03_counters_match_db(self):
        self.login()
        coll = self.make_collection(slug="s03")
        good = self._make_book("good.docx")
        from factory._smoke_fixtures import make_broken_docx
        tmp = tempfile.mkdtemp(prefix="pct-studio-corrupt-")
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        corrupt = make_broken_docx(os.path.join(tmp, "corrupt.docx"))
        self.upload(coll["id"], good)
        self.upload(coll["id"], corrupt)
        plan = self._make_batch(coll["collection_id"], [
            self._file_entry(good), self._file_entry(corrupt)])
        job = self._process_batch(plan["batch"]["batch_id"])
        row = self.wait_job(job["job"]["job_id"])
        self.assertEqual(row["status"], "succeeded", row)

        conn = self._db()
        try:
            expected = {
                "total": conn.execute(
                    "SELECT COUNT(*) n FROM knowledge_file_queue "
                    "WHERE collection_id=?",
                    (coll["collection_id"],)).fetchone()["n"],
                "pending": conn.execute(
                    "SELECT COUNT(*) n FROM knowledge_file_queue "
                    "WHERE collection_id=? AND status='pending'",
                    (coll["collection_id"],)).fetchone()["n"],
                "running": conn.execute(
                    "SELECT COUNT(*) n FROM knowledge_file_queue "
                    "WHERE collection_id=? AND status='running'",
                    (coll["collection_id"],)).fetchone()["n"],
                "succeeded": conn.execute(
                    "SELECT COUNT(*) n FROM knowledge_file_queue "
                    "WHERE collection_id=? AND status='succeeded'",
                    (coll["collection_id"],)).fetchone()["n"],
                "needs_review": conn.execute(
                    "SELECT COUNT(*) n FROM knowledge_file_queue "
                    "WHERE collection_id=? AND status='needs_review'",
                    (coll["collection_id"],)).fetchone()["n"],
                "failed": conn.execute(
                    "SELECT COUNT(*) n FROM knowledge_file_queue "
                    "WHERE collection_id=? AND status='failed'",
                    (coll["collection_id"],)).fetchone()["n"],
                "attempts_total": conn.execute(
                    "SELECT COALESCE(SUM(attempts),0) n FROM "
                    "knowledge_file_queue WHERE collection_id=?",
                    (coll["collection_id"],)).fetchone()["n"],
            }
            stages = [dict(r) for r in conn.execute(
                "SELECT stage, COUNT(*) AS files FROM knowledge_file_queue "
                "WHERE stage IS NOT NULL AND status='failed' "
                "AND collection_id=? "
                "GROUP BY stage", (coll["collection_id"],))]
        finally:
            conn.close()

        j = self._list_batches(coll["collection_id"]).get_json()
        for k, v in expected.items():
            self.assertEqual(j["queue"]["counters"][k], v, k)
        # the state must be non-trivial (1 good + 1 corrupt)
        self.assertEqual(j["queue"]["counters"]["total"], 2)
        self.assertEqual(j["queue"]["counters"]["succeeded"], 1)
        self.assertEqual(j["queue"]["counters"]["failed"], 1)
        self.assertEqual(j["queue"]["counters"]["attempts_total"], 2)
        self.assertEqual(j["queue"]["failed_by_stage"], stages)

        # batch row processed/failed counts mirror the queue outcome
        b = j["batches"][0]
        self.assertEqual(b["processed_count"], 1)
        self.assertEqual(b["failed_count"], 1)
        self.assertEqual(b["status"], "done")


class TestS04_DocRegistryIds(Base):
    """S-04: documents list carries work/edition/volume ids after a WF run."""

    def test_s04_registry_ids_in_docs_list(self):
        self.login()
        coll = self.make_collection(slug="s04")
        good = self._make_book("good.docx")
        self.upload(coll["id"], good)
        plan = self._make_batch(coll["collection_id"],
                                [self._file_entry(good)])
        doc_id = self._docs(coll["id"])[0]["document_id"]

        # before processing: the fields are present but empty
        d0 = self._docs(coll["id"])[0]
        self.assertIn("work_id", d0)
        self.assertIn("edition_id", d0)
        self.assertIn("volume_id", d0)
        self.assertFalse(d0["work_id"])
        self.assertFalse(d0["edition_id"])
        self.assertFalse(d0["volume_id"])

        job = self._process_batch(plan["batch"]["batch_id"])
        row = self.wait_job(job["job"]["job_id"])
        self.assertEqual(row["status"], "succeeded", row)

        d1 = next(d for d in self._docs(coll["id"])
                  if d["document_id"] == doc_id)
        self.assertTrue(d1["work_id"], d1)
        self.assertTrue(d1["edition_id"], d1)
        # the sample book has no volume_no -> volume_id stays empty
        self.assertFalse(d1["volume_id"], d1)

        # cross-check: the work exists in the registry and its id matches
        w = self.client.get(
            f"/api/knowledge/works/{d1['work_id']}").get_json()
        self.assertTrue(w["ok"])
        self.assertEqual(w["work"]["work_id"], d1["work_id"])
        self.assertTrue(w["editions"])
        self.assertTrue(any(e["edition_id"] == d1["edition_id"]
                            for e in w["editions"]), w["editions"])


class TestS11_StatusCounts(Base):
    """S-11: list documents carries server-side status_counts (page-independent)."""

    def test_s11_status_counts_match_db(self):
        self.login()
        coll = self.make_collection(slug="s11")
        self.upload(coll["id"], self._make_book("good.docx"))

        j = self.client.get(
            f"/api/knowledge/collections/{coll['id']}/documents"
        ).get_json()
        self.assertIn("status_counts", j)
        self.assertEqual(j["status_counts"].get("uploaded"), 1)

        conn = self._db()
        try:
            rows = conn.execute(
                "SELECT status, COUNT(*) n FROM knowledge_collection_documents"
                " WHERE collection_id=? GROUP BY status",
                (coll["collection_id"],)).fetchall()
            expected = {r["status"]: r["n"] for r in rows}
        finally:
            conn.close()
        self.assertEqual(j["status_counts"], expected)

        # page independence: identical map at per_page=1
        j2 = self.client.get(
            f"/api/knowledge/collections/{coll['id']}/documents?per_page=1"
        ).get_json()
        self.assertEqual(j2["status_counts"], expected)


class TestS05_ProcessAllValidation(Base):
    """S-05: process-all auth / 404 / 409."""

    def test_s05a_unauthenticated_401(self):
        r = self.client.post(
            "/api/knowledge/collections/1/documents/process-all")
        self.assertEqual(r.status_code, 401)

    def test_s05b_unknown_collection_404(self):
        self.login()
        r = self.client.post(
            "/api/knowledge/collections/999999/documents/process-all")
        self.assertEqual(r.status_code, 404)
        self.assertFalse(r.get_json()["ok"])

    def test_s05c_no_files_409(self):
        self.login()
        coll = self.make_collection(slug="s05c")
        r = self.client.post(
            f"/api/knowledge/collections/{coll['id']}/documents/process-all")
        self.assertEqual(r.status_code, 409, r.get_data(as_text=True))
        self.assertEqual(r.get_json()["code"], "no_files_to_process")


class TestS06_ProcessAllHappy(Base):
    """S-06: one job over all uploaded/failed docs, queue rows terminal."""

    def test_s06_two_books_processed(self):
        self.login()
        coll = self.make_collection(slug="s06")
        good = self._make_book("one.docx")
        from factory._smoke_fixtures import make_broken_docx
        tmp = tempfile.mkdtemp(prefix="pct-studio-corrupt-")
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        corrupt = make_broken_docx(os.path.join(tmp, "two.docx"))
        self.upload(coll["id"], good)
        self.upload(coll["id"], corrupt)
        r = self.client.post(
            f"/api/knowledge/collections/{coll['id']}/documents/process-all")
        self.assertEqual(r.status_code, 202, r.get_data(as_text=True))
        j = r.get_json()
        self.assertTrue(j["ok"])
        self.assertEqual(j["files_queued"], 2)
        self.assertFalse(j["resubmitted"])
        row = self.wait_job(j["job"]["job_id"])
        self.assertEqual(row["status"], "succeeded", row)
        self.assertEqual(row["total"], 2)
        self.assertEqual(row["progress"], 2)
        docs = self._docs(coll["id"])
        self.assertEqual(len(docs), 2)
        statuses = sorted(d["status"] for d in docs)
        self.assertEqual(statuses, ["failed", "parsed"])
        conn = self._db()
        try:
            n_open = conn.execute(
                "SELECT COUNT(*) n FROM knowledge_file_queue"
                " WHERE collection_id=? AND status IN ('pending','running')",
                (coll["collection_id"],)).fetchone()["n"]
        finally:
            conn.close()
        self.assertEqual(n_open, 0)


class TestS07_ProcessAllIdempotency(Base):
    """S-07: second POST while running -> same job, no second worker."""

    def test_s07_second_post_no_second_worker(self):
        self.login()
        coll = self.make_collection(slug="s07")
        self.upload(coll["id"], self._make_book("one.docx"))
        url = f"/api/knowledge/collections/{coll['id']}/documents/process-all"
        r1 = self.client.post(url)
        self.assertEqual(r1.status_code, 202, r1.get_data(as_text=True))
        r2 = self.client.post(url)
        self.assertEqual(r2.status_code, 200, r2.get_data(as_text=True))
        j2 = r2.get_json()
        self.assertTrue(j2["resubmitted"])
        self.assertEqual(j2["job"]["job_id"],
                         r1.get_json()["job"]["job_id"])
        row = self.wait_job(j2["job"]["job_id"])
        self.assertEqual(row["status"], "succeeded", row)
        jobs = self.client.get("/api/knowledge/jobs").get_json()["jobs"]
        mine = [x for x in jobs if x["kind"] == "process_collection"
                and x["collection_id"] == coll["collection_id"]]
        self.assertEqual(len(mine), 1)


class TestS08_PauseResume(Base):
    """S-08: pause endpoint sets the scope; paused run stops clean; resume finishes."""

    def test_s08_pause_stops_cleanly_and_resume_finishes(self):
        self.login()
        coll = self.make_collection(slug="s08")
        good = self._make_book("one.docx")
        from factory._smoke_fixtures import make_broken_docx
        tmp = tempfile.mkdtemp(prefix="pct-studio-corrupt-")
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        corrupt = make_broken_docx(os.path.join(tmp, "two.docx"))
        self.upload(coll["id"], good)
        self.upload(coll["id"], corrupt)
        url = f"/api/knowledge/collections/{coll['id']}/documents"

        r = self.client.post(f"{url}/pause")
        self.assertEqual(r.status_code, 200, r.get_data(as_text=True))
        j = r.get_json()
        self.assertTrue(j["paused"])
        scope = f"collection:{coll['collection_id']}"
        self.assertEqual(j["scope"], scope)
        conn = self._db()
        try:
            row = conn.execute(
                "SELECT paused FROM knowledge_queue_control WHERE scope=?",
                (scope,)).fetchone()
        finally:
            conn.close()
        self.assertTrue(row and row["paused"])

        # paused run: the worker stops before the first file (deterministic)
        with mock.patch("knowledge_api.queue_is_paused",
                        return_value=True):
            r = self.client.post(f"{url}/process-all")
            self.assertEqual(r.status_code, 202, r.get_data(as_text=True))
            row = self.wait_job(r.get_json()["job"]["job_id"])
        self.assertEqual(row["status"], "interrupted", row)
        self.assertIn("paused", row["error"] or "")
        for d in self._docs(coll["id"]):
            self.assertEqual(d["status"], "uploaded")

        # resume: same endpoint clears the flag and re-executes the job
        r2 = self.client.post(f"{url}/process-all")
        self.assertEqual(r2.status_code, 202, r2.get_data(as_text=True))
        row2 = self.wait_job(r2.get_json()["job"]["job_id"])
        self.assertEqual(row2["status"], "succeeded", row2)
        statuses = sorted(d["status"] for d in self._docs(coll["id"]))
        self.assertEqual(statuses, ["failed", "parsed"])
        conn = self._db()
        try:
            p = conn.execute(
                "SELECT paused FROM knowledge_queue_control WHERE scope=?",
                (scope,)).fetchone()
        finally:
            conn.close()
        self.assertFalse(p["paused"])


class TestS09_ApproveAllValidation(Base):
    """S-09: approve-all auth / 404 / 409."""

    def test_s09a_unauthenticated_401(self):
        r = self.client.post(
            "/api/knowledge/collections/1/documents/approve-all")
        self.assertEqual(r.status_code, 401)

    def test_s09b_unknown_collection_404(self):
        self.login()
        r = self.client.post(
            "/api/knowledge/collections/999999/documents/approve-all")
        self.assertEqual(r.status_code, 404)
        self.assertFalse(r.get_json()["ok"])

    def test_s09c_no_candidates_409(self):
        self.login()
        coll = self.make_collection(slug="s09c")
        r = self.client.post(
            f"/api/knowledge/collections/{coll['id']}/documents/approve-all")
        self.assertEqual(r.status_code, 409, r.get_data(as_text=True))
        self.assertEqual(r.get_json()["code"], "no_docs_to_approve")


class TestS10_ApproveAllHappy(Base):
    """S-10: only parsed/needs_review flip; uploaded untouched; one audit row."""

    def test_s10_approves_only_parsed_and_needs_review(self):
        self.login()
        coll = self.make_collection(slug="s10")
        self.upload(coll["id"], self._make_book("one.docx"))
        r = self.client.post(
            f"/api/knowledge/collections/{coll['id']}/documents/process-all")
        self.assertEqual(r.status_code, 202, r.get_data(as_text=True))
        self.wait_job(r.get_json()["job"]["job_id"])
        # second doc stays 'uploaded' — not a candidate (distinct bytes)
        from factory._smoke_fixtures import make_broken_docx
        tmp = tempfile.mkdtemp(prefix="pct-studio-corrupt-")
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        self.upload(coll["id"], make_broken_docx(os.path.join(tmp, "two.docx")))

        r = self.client.post(
            f"/api/knowledge/collections/{coll['id']}/documents/approve-all")
        self.assertEqual(r.status_code, 200, r.get_data(as_text=True))
        self.assertEqual(r.get_json()["approved"], 1)
        statuses = sorted(d["status"] for d in self._docs(coll["id"]))
        self.assertEqual(statuses, ["approved", "uploaded"])

        conn = self._db()
        try:
            rows = conn.execute(
                "SELECT detail_json FROM knowledge_audit_log"
                " WHERE collection_id=? AND action='approved_all'",
                (coll["collection_id"],)).fetchall()
        finally:
            conn.close()
        self.assertEqual(len(rows), 1)
        self.assertEqual(json.loads(rows[0]["detail_json"])["count"], 1)

        r2 = self.client.post(
            f"/api/knowledge/collections/{coll['id']}/documents/approve-all")
        self.assertEqual(r2.status_code, 409)


if __name__ == "__main__":
    unittest.main()

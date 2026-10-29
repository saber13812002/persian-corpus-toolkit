# -*- coding: utf-8 -*-
"""test_queue — PCM-15: persistent per-file processing queue.

Coverage (Q-01..Q-07):
  Q-01 batch E2E: good + corrupt + duplicate file
       - good  -> queue row succeeded, stage=export, attempts=1, duration_ms,
         out_dir, sha256
       - corrupt -> queue row failed, stage=NULL (no completed safe stage),
         last_error, attempts=1
       - duplicate -> ONE queue row / ONE document row per file_key (dedup)
  Q-02 pause before process -> 0 files processed, job interrupted
       '[paused by user]', rows stay pending; resume -> completes
  Q-03 /api/knowledge/queue/summary counters == direct DB recompute
       (single source of truth), collection filter, unknown collection 404,
       unauthenticated 401
  Q-04 worker kill + restart: stale running job/queue/doc/batch rows are
       recovered (queue -> pending keeping the last safe stage), fresh
       (10s-old) running row is NOT touched; /process re-executes the job
       and completes; no duplicate queue rows; attempts bumped
  Q-05 retry a failed file (single-doc endpoint): attempts 1 -> 2, same
       (last safe) stage, last_error present; the good file's artifacts are
       byte-identical (deterministic idempotent re-run over sha-verified
       unchanged input)
  Q-06 Dump contract d-1: generate_dump + validate_dump on a queue-processed
       out_dir -> VALID (source DOCX rehashed)
  Q-07 quality needs_review path -> queue row status needs_review,
       stage=export

Follows the PCM-12.3 rule: import pct_test_support FIRST, then server.
"""
import hashlib
import io
import os
import shutil
import sqlite3
import tempfile
import time
import unittest

import pct_test_support  # noqa: F401  (must precede `import server`)

import server

PW = "test-secret-123"


class Base(unittest.TestCase):
    def setUp(self):
        pct_test_support.reset_db()
        self._datadir = tempfile.mkdtemp(prefix="pct-queue-")
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

    def make_collection(self, name="کتابخانه آزمون", slug="queue-test"):
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

    def _queue_rows(self, collection_id=None):
        conn = self._db()
        try:
            if collection_id:
                rows = conn.execute(
                    "SELECT * FROM knowledge_file_queue WHERE collection_id=?",
                    (collection_id,)).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM knowledge_file_queue").fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def _make_book(self, name="book.docx"):
        from factory._smoke_fixtures import make_sample_book
        tmp = tempfile.mkdtemp(prefix="pct-queue-src-")
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        return make_sample_book(os.path.join(tmp, name))

    def _make_batch(self, coll_id, files):
        r = self.client.post("/api/knowledge/import/batches", json={
            "collection_id": coll_id,
            "folder_name": "pct15 folder",
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


class TestQ01_BatchE2E(Base):
    """Q-01: batch with good + corrupt + duplicate files."""

    def test_q01_good_corrupt_duplicate(self):
        self.login()
        coll = self.make_collection(slug="q01")
        good = self._make_book("good.docx")
        from factory._smoke_fixtures import make_broken_docx
        tmp = tempfile.mkdtemp(prefix="pct-queue-corrupt-")
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        corrupt = make_broken_docx(os.path.join(tmp, "corrupt.docx"))

        r = self.upload(coll["id"], good)
        self.assertEqual(r.status_code, 201)
        good_doc_id = r.get_json()["document"]["document_id"]
        r = self.upload(coll["id"], corrupt)
        self.assertEqual(r.status_code, 201)
        corrupt_doc_id = r.get_json()["document"]["document_id"]

        # Both files are already registered (uploaded above), so the plan
        # flags every entry as a duplicate of a known sha — the batch then
        # processes the registered documents (deduped by queue file_key).
        plan = self._make_batch(coll["collection_id"], [
            self._file_entry(good, "good.docx"),
            self._file_entry(corrupt, "corrupt.docx"),
            # duplicate: same sha as the good file, different name
            self._file_entry(good, "good-copy.docx"),
        ])
        self.assertEqual(plan["summary"]["total"], 3)
        self.assertEqual(plan["summary"]["pending"], 0)
        self.assertEqual(plan["summary"]["duplicate"], 3)
        batch_id = plan["batch"]["batch_id"]

        job = self._process_batch(batch_id)
        row = self.wait_job(job["job"]["job_id"])
        self.assertEqual(row["status"], "succeeded", row)

        good_key = "f-" + self.sha256_file(good)[:8]
        corrupt_key = "f-" + self.sha256_file(corrupt)[:8]
        q = {r["file_key"]: r for r in self._queue_rows(coll["collection_id"])}
        self.assertEqual(len(q), 2, "exactly one queue row per unique file")
        self.assertIn(good_key, q)
        self.assertIn(corrupt_key, q)

        g = q[good_key]
        self.assertEqual(g["status"], "succeeded")
        self.assertEqual(g["stage"], "export")
        self.assertEqual(g["attempts"], 1)
        self.assertEqual(g["last_error"], None)
        self.assertGreaterEqual(g["duration_ms"], 0)
        self.assertIsNotNone(g["finished_at"])
        # out_dir is the factory's own output dir (its file_id =
        # short_id("f", sha)), stored as a posix relative path
        from factory.models import short_id
        self.assertEqual(
            g["out_dir"], "out/" + short_id("f", self.sha256_file(good)))
        self.assertEqual(g["sha256"], self.sha256_file(good))
        self.assertEqual(g["document_id"], good_doc_id)

        c = q[corrupt_key]
        self.assertEqual(c["status"], "failed")
        # bad-zip is rejected inside stage 1 (intake) -> no completed
        # safe stage exists
        self.assertIsNone(c["stage"])
        self.assertEqual(c["attempts"], 1)
        self.assertTrue(c["last_error"])
        self.assertIsNotNone(c["finished_at"])

        # document rows: parsed/needs_review vs failed; dedup intact
        docs = {d["document_id"]: d for d in self._docs(coll["id"])}
        self.assertIn(docs[good_doc_id]["status"], ("parsed", "needs_review"))
        self.assertEqual(docs[corrupt_doc_id]["status"], "failed")
        self.assertTrue(docs[corrupt_doc_id]["error"])
        self.assertEqual(len(docs), 2, "duplicate upload registered once")

        # batch tally + detail endpoint exposes the queue + pause state
        det = self.client.get(
            f"/api/knowledge/import/batches/{batch_id}").get_json()
        self.assertEqual(det["batch"]["status"], "done")
        self.assertEqual(det["batch"]["processed_count"], 1)
        self.assertEqual(det["batch"]["failed_count"], 1)
        self.assertFalse(det["paused"])
        self.assertEqual(len(det["queue"]), 2)


class TestQ02_PauseResume(Base):
    """Q-02: deterministic pause before process -> 0 processed, then resume."""

    def test_q02_pause_then_resume(self):
        self.login()
        coll = self.make_collection(slug="q02")
        good = self._make_book("good.docx")
        from factory._smoke_fixtures import make_broken_docx
        tmp = tempfile.mkdtemp(prefix="pct-queue-corrupt-")
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        corrupt = make_broken_docx(os.path.join(tmp, "corrupt.docx"))
        self.upload(coll["id"], good)
        self.upload(coll["id"], corrupt)
        plan = self._make_batch(coll["collection_id"], [
            self._file_entry(good), self._file_entry(corrupt)])
        batch_id = plan["batch"]["batch_id"]

        # pause BEFORE processing starts
        r = self.client.post(f"/api/knowledge/import/batches/{batch_id}/pause")
        self.assertEqual(r.status_code, 200, r.get_data(as_text=True))
        self.assertTrue(r.get_json()["paused"])

        job = self._process_batch(batch_id)
        row = self.wait_job(job["job"]["job_id"])
        self.assertEqual(row["status"], "interrupted", row)
        self.assertIn("paused by user", row["error"])

        # NOTHING was processed; both queue rows still pending, 0 attempts
        docs = {d["document_id"]: d for d in self._docs(coll["id"])}
        self.assertTrue(all(d["status"] == "uploaded" for d in docs.values()))
        q = self._queue_rows(coll["collection_id"])
        self.assertEqual(len(q), 2)
        self.assertTrue(all(r["status"] == "pending" for r in q))
        self.assertTrue(all(r["attempts"] == 0 for r in q))
        # batch rolled back to planned while paused
        det = self.client.get(
            f"/api/knowledge/import/batches/{batch_id}").get_json()
        self.assertEqual(det["batch"]["status"], "planned")
        self.assertTrue(det["paused"])

        # resume (clears the flag; processing must be (re)started)
        r = self.client.post(f"/api/knowledge/import/batches/{batch_id}/resume")
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.get_json()["paused"])
        job = self._process_batch(batch_id)
        row = self.wait_job(job["job"]["job_id"])
        self.assertEqual(row["status"], "succeeded", row)
        q = {r["file_key"]: r for r in self._queue_rows(coll["collection_id"])}
        self.assertEqual({r["status"] for r in q.values()},
                         {"succeeded", "failed"})
        self.assertTrue(all(r["attempts"] == 1 for r in q.values()))


class TestQ03_Summary(Base):
    """Q-03: summary counters must equal a direct DB recompute."""

    def test_q03_counters_match_db(self):
        self.login()
        coll = self.make_collection(slug="q03")
        good = self._make_book("good.docx")
        from factory._smoke_fixtures import make_broken_docx
        tmp = tempfile.mkdtemp(prefix="pct-queue-corrupt-")
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        corrupt = make_broken_docx(os.path.join(tmp, "corrupt.docx"))
        self.upload(coll["id"], good)
        self.upload(coll["id"], corrupt)
        plan = self._make_batch(coll["collection_id"], [
            self._file_entry(good), self._file_entry(corrupt)])
        job = self._process_batch(plan["batch"]["batch_id"])
        self.wait_job(job["job"]["job_id"])

        # recompute the same counters straight from the DB
        conn = self._db()
        try:
            expected = {
                "total": conn.execute(
                    "SELECT COUNT(*) n FROM knowledge_file_queue").fetchone()["n"],
                "pending": conn.execute(
                    "SELECT COUNT(*) n FROM knowledge_file_queue "
                    "WHERE status='pending'").fetchone()["n"],
                "running": conn.execute(
                    "SELECT COUNT(*) n FROM knowledge_file_queue "
                    "WHERE status='running'").fetchone()["n"],
                "succeeded": conn.execute(
                    "SELECT COUNT(*) n FROM knowledge_file_queue "
                    "WHERE status='succeeded'").fetchone()["n"],
                "needs_review": conn.execute(
                    "SELECT COUNT(*) n FROM knowledge_file_queue "
                    "WHERE status='needs_review'").fetchone()["n"],
                "failed": conn.execute(
                    "SELECT COUNT(*) n FROM knowledge_file_queue "
                    "WHERE status='failed'").fetchone()["n"],
                "attempts_total": conn.execute(
                    "SELECT COALESCE(SUM(attempts),0) n FROM "
                    "knowledge_file_queue").fetchone()["n"],
            }
        finally:
            conn.close()

        j = self.client.get("/api/knowledge/queue/summary").get_json()
        self.assertTrue(j["ok"])
        for k, v in expected.items():
            self.assertEqual(j["counters"][k], v, k)
        # a non-trivial state actually produced
        self.assertEqual(j["counters"]["succeeded"], 1)
        self.assertEqual(j["counters"]["failed"], 1)
        self.assertEqual(j["counters"]["attempts_total"], 2)

        # collection filter
        j = self.client.get(
            f"/api/knowledge/queue/summary?collection_id="
            f"{coll['collection_id']}").get_json()
        self.assertEqual(j["counters"]["total"], 2)
        # unknown collection -> 404
        r = self.client.get(
            "/api/knowledge/queue/summary?collection_id=c-doesnotexist")
        self.assertEqual(r.status_code, 404)

    def test_q03_unauthenticated_401(self):
        r = self.client.get("/api/knowledge/queue/summary")
        self.assertEqual(r.status_code, 401)


class TestQ04_KillRestart(Base):
    """Q-04: simulate a worker crash (stale rows) -> recovery -> re-run."""

    def test_q04_crash_recovery_and_rerun(self):
        self.login()
        coll = self.make_collection(slug="q04")
        good = self._make_book("good.docx")
        sha = self.sha256_file(good)
        self.upload(coll["id"], good)
        plan = self._make_batch(coll["collection_id"], [self._file_entry(good)])
        batch_id = plan["batch"]["batch_id"]
        job = self._process_batch(batch_id)
        first = self.wait_job(job["job"]["job_id"])
        self.assertEqual(first["status"], "succeeded", first)

        file_key = "f-" + sha[:8]
        conn = self._db()
        try:
            now2h = "datetime('now','-2 hours')"
            # --- force the "crashed 2 hours ago" snapshot ---------------
            conn.execute(
                "UPDATE knowledge_jobs SET status='interrupted', "
                "error='boom [worker interrupted]', updated_at=" + now2h +
                " WHERE job_id=?", (first["job_id"],))
            conn.execute(
                "UPDATE knowledge_file_queue SET status='running', "
                "stage='structure', updated_at=" + now2h +
                " WHERE collection_id=? AND file_key=?",
                (coll["collection_id"], file_key))
            conn.execute(
                "UPDATE knowledge_collection_documents SET status='parsing', "
                "updated_at=" + now2h + " WHERE sha256=?", (sha,))
            conn.execute(
                "UPDATE knowledge_import_batches SET status='processing', "
                "updated_at=" + now2h + " WHERE batch_id=?", (batch_id,))
            # a FRESH (10s-old) running row — must NOT be recovered
            conn.execute(
                """INSERT INTO knowledge_file_queue
                   (file_key, document_id, collection_id, sha256, status,
                    stage, attempts, created_at, updated_at)
                   VALUES (?, ?, ?, ?, 'running', 'parse', 1,
                           datetime('now','-10 seconds'),
                           datetime('now','-10 seconds'))""",
                ("f-fresh999", "d-fresh999", coll["collection_id"], "0" * 64))
            conn.commit()
        finally:
            conn.close()

        # any authenticated knowledge call runs recovery first
        det = self.client.get(
            f"/api/knowledge/import/batches/{batch_id}").get_json()
        job_row = next(j for j in det["jobs"] if j["job_id"] == first["job_id"])
        self.assertEqual(job_row["status"], "interrupted")
        q = {r["file_key"]: r for r in self._queue_rows(coll["collection_id"])}
        # stale running row -> pending, last safe stage KEPT as resume anchor
        self.assertEqual(q[file_key]["status"], "pending")
        self.assertEqual(q[file_key]["stage"], "structure")
        self.assertEqual(q[file_key]["attempts"], 1)
        # fresh row untouched
        self.assertEqual(q["f-fresh999"]["status"], "running")
        # document back to uploaded, batch back to planned
        docs = {d["document_id"]: d for d in self._docs(coll["id"])}
        self.assertTrue(all(d["status"] == "uploaded" for d in docs.values()))
        self.assertEqual(det["batch"]["status"], "planned")

        # /process re-executes the interrupted job (same row, retry bumped)
        job = self._process_batch(batch_id)
        self.assertEqual(job["job"]["job_id"], first["job_id"])
        row = self.wait_job(first["job_id"])
        self.assertEqual(row["status"], "succeeded", row)
        self.assertEqual(row["retry_count"], 1)

        q = {r["file_key"]: r for r in self._queue_rows(coll["collection_id"])}
        self.assertEqual(q[file_key]["status"], "succeeded")
        self.assertEqual(q[file_key]["stage"], "export")
        self.assertEqual(q[file_key]["attempts"], 2)  # crash + re-run
        # no duplicate rows: only our file + the fake fresh row
        self.assertEqual(set(q.keys()), {file_key, "f-fresh999"})
        docs = {d["document_id"]: d for d in self._docs(coll["id"])}
        self.assertTrue(
            all(d["status"] in ("parsed", "needs_review") for d in docs.values()))


class TestQ05_RetryFailed(Base):
    """Q-05: retry a failed file — attempts bump, same safe stage, the good
    file's artifacts stay byte-identical (deterministic re-run)."""

    def test_q05_retry_failed_file(self):
        self.login()
        coll = self.make_collection(slug="q05")
        good = self._make_book("good.docx")
        from factory._smoke_fixtures import make_broken_docx
        tmp = tempfile.mkdtemp(prefix="pct-queue-corrupt-")
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        corrupt = make_broken_docx(os.path.join(tmp, "corrupt.docx"))
        self.upload(coll["id"], good)
        r = self.upload(coll["id"], corrupt)
        corrupt_doc_id = r.get_json()["document"]["document_id"]
        plan = self._make_batch(coll["collection_id"], [
            self._file_entry(good), self._file_entry(corrupt)])
        job = self._process_batch(plan["batch"]["batch_id"])
        self.wait_job(job["job"]["job_id"])

        good_key = "f-" + self.sha256_file(good)[:8]
        corrupt_key = "f-" + self.sha256_file(corrupt)[:8]
        q = {r["file_key"]: r for r in self._queue_rows(coll["collection_id"])}
        # the queue row stores the factory's real output dir (its file_id
        # is short_id("f", sha), NOT f-<sha[:8]>) — single source of truth
        good_out = os.path.join(
            self._datadir, q[good_key]["out_dir"].replace("/", os.sep))
        artifact_hashes = {
            fn: self.sha256_file(os.path.join(good_out, fn))
            for fn in ("blocks.jsonl", "document.json", "manifest.json",
                       "quality-report.json", "report.md")
        }
        self.assertEqual(q[corrupt_key]["status"], "failed")
        first_error = q[corrupt_key]["last_error"]
        self.assertTrue(first_error)
        corrupt_sha = q[corrupt_key]["sha256"]

        # single-doc retry of the failed file (job key process_document)
        r = self.client.post(
            f"/api/knowledge/documents/{corrupt_doc_id}/process")
        self.assertEqual(r.status_code, 202, r.get_data(as_text=True))
        row = self.wait_job(r.get_json()["job"]["job_id"])
        self.assertEqual(row["status"], "failed", row)

        q = {r["file_key"]: r for r in self._queue_rows(coll["collection_id"])}
        c = q[corrupt_key]
        self.assertEqual(c["status"], "failed")
        self.assertEqual(c["attempts"], 2)
        # still no completed safe stage (bad-zip fails inside intake)
        self.assertIsNone(c["stage"])
        self.assertTrue(c["last_error"])
        self.assertEqual(c["sha256"], corrupt_sha, "input verified unchanged")

        # the good file is untouched: same artifacts, same queue row state
        for fn, h in artifact_hashes.items():
            self.assertEqual(self.sha256_file(os.path.join(good_out, fn)), h,
                             fn)
        self.assertEqual(q[good_key]["status"], "succeeded")
        self.assertEqual(q[good_key]["attempts"], 1)


class TestQ06_DumpCompat(Base):
    """Q-06: a queue-processed output must satisfy the Dump contract d-1."""

    def test_q06_dump_generate_validate(self):
        self.login()
        coll = self.make_collection(slug="q06")
        good = self._make_book("good.docx")
        self.upload(coll["id"], good)
        plan = self._make_batch(coll["collection_id"], [self._file_entry(good)])
        job = self._process_batch(plan["batch"]["batch_id"])
        row = self.wait_job(job["job"]["job_id"])
        self.assertEqual(row["status"], "succeeded", row)

        q = self._queue_rows(coll["collection_id"])
        self.assertEqual(len(q), 1)
        # the queue row stores the factory's real output dir — use it
        out_dir = os.path.join(
            self._datadir, q[0]["out_dir"].replace("/", os.sep))
        self.assertTrue(os.path.isdir(out_dir), out_dir)

        from factory.dump import generate_dump, validate_dump
        dump_dir = tempfile.mkdtemp(prefix="pct-queue-dump-")
        self.addCleanup(shutil.rmtree, dump_dir, ignore_errors=True)
        # the stored original is named by the QUEUE file_key (f-<sha8>)
        stored = os.path.join(
            self._datadir, "files", q[0]["sha256"][:12],
            q[0]["file_key"] + ".docx")
        self.assertTrue(os.path.isfile(stored))
        manifest = generate_dump(out_dir, dump_dir, source_docx=stored)
        self.assertTrue(manifest)
        ok, errors, _warnings = validate_dump(dump_dir)
        self.assertTrue(ok, errors)
        self.assertEqual(errors, [])


class TestQ07_NeedsReview(Base):
    """Q-07: a document that fails quality (manual_review) lands in the
    queue as needs_review (not failed, not succeeded)."""

    def test_q07_needs_review_status(self):
        self.login()
        coll = self.make_collection(slug="q07")
        from factory._smoke_fixtures import make_docx
        tmp = tempfile.mkdtemp(prefix="pct-queue-src-")
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        # short English text: hard-gate non_empty_text fails -> manual_review
        short = make_docx(os.path.join(tmp, "short.docx"),
                          [("Normal", "tiny")])
        self.upload(coll["id"], short)
        plan = self._make_batch(coll["collection_id"], [self._file_entry(short)])
        job = self._process_batch(plan["batch"]["batch_id"])
        row = self.wait_job(job["job"]["job_id"])
        self.assertEqual(row["status"], "succeeded", row)  # job ok, file NR

        q = self._queue_rows(coll["collection_id"])
        self.assertEqual(len(q), 1)
        self.assertEqual(q[0]["status"], "needs_review")
        self.assertEqual(q[0]["stage"], "export")
        self.assertEqual(q[0]["attempts"], 1)
        docs = self._docs(coll["id"])
        self.assertEqual(docs[0]["status"], "needs_review")


class TestQ08_QueueControlErrors(Base):
    """Q-08: control endpoints — unknown batch 404, resume on unknown 404."""

    def test_q08_unknown_batch_404(self):
        self.login()
        r = self.client.post("/api/knowledge/import/batches/b-nope0000/pause")
        self.assertEqual(r.status_code, 404)
        r = self.client.post("/api/knowledge/import/batches/b-nope0000/resume")
        self.assertEqual(r.status_code, 404)
        # unauthenticated control access — a fresh (NOT logged in) client
        r2 = server.app.test_client()
        r = r2.post("/api/knowledge/import/batches/b-nope0000/pause")
        self.assertEqual(r.status_code, 401)


if __name__ == "__main__":
    unittest.main(verbosity=2)

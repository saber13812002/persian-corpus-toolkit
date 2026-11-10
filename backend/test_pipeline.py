# -*- coding: utf-8 -*-
"""test_pipeline — PCM-20.9 Knowledge Corpus Factory: Stage A tests (PF-Axx).

Stage A = «آپلود قابل‌اعتماد چندفایلی»:
  - the plan is PERSISTED (knowledge_batch_files, one row per file);
  - the REAL bytes are uploaded per file to
    POST /api/knowledge/import/batches/<batch_id>/files (sha-matched,
    idempotent retryable, per-file outcomes);
  - processing is scoped to the batch (documents.batch_id or plan-referenced
    docs); a brand-new batch with nothing uploaded -> 409 no_files_uploaded;
  - the legacy PCM-15 flow (single uploads BEFORE the batch plan) keeps
    working — plan rows flag duplicates and the batch processes them.

Fixture requirement (task spec): 5 Persian-named DOCX + 1 corrupt file,
all generated locally via factory._smoke_fixtures.

Follows the PCM-12.3 rule: import pct_test_support FIRST, then server.
"""
import hashlib
import io
import json
import os
import re
import shutil
import sqlite3
import tempfile
import time
import unittest

import pct_test_support  # noqa: F401  (must precede `import server`)

import server
import knowledge_api

PW = "test-secret-123"

# 5 Persian-named books + 1 corrupt file (task spec)
PERSIAN_FILES = [
    "کتاب-اول-ادبیات.docx",
    "کتاب-دوم-تاریخ.docx",
    "کتاب-سوم-فلسفه.docx",
    "کتاب-چهارم-حقوق.docx",
    "کتاب-پنجم-پزشکی.docx",
]
CORRUPT_FILE = "فایل-خراب.docx"


class Base(unittest.TestCase):
    def setUp(self):
        pct_test_support.reset_db()
        self._cur_coll = None
        self._datadir = tempfile.mkdtemp(prefix="pct-pipeline-")
        self._old_dd = os.environ.get("PCT_KNOWLEDGE_DATA_DIR")
        os.environ["PCT_KNOWLEDGE_DATA_DIR"] = self._datadir
        self.client = server.app.test_client()
        self.login()

    def tearDown(self):
        if self._old_dd is None:
            os.environ.pop("PCT_KNOWLEDGE_DATA_DIR", None)
        else:
            os.environ["PCT_KNOWLEDGE_DATA_DIR"] = self._old_dd
        shutil.rmtree(self._datadir, ignore_errors=True)

    def login(self, password=PW):
        r = self.client.post("/api/auth/login", json={"password": password})
        self.assertEqual(r.status_code, 200, r.get_data(as_text=True))

    def make_collection(self, name="پیکره آزمایشی", slug="pipeline-test"):
        r = self.client.post(
            "/api/knowledge/collections",
            json={"name": name, "slug": slug},
        )
        self.assertEqual(r.status_code, 201, r.get_data(as_text=True))
        coll = r.get_json()["collection"]
        self._cur_coll = coll
        return coll

    @staticmethod
    def sha256_file(path):
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        return h.hexdigest()

    def _make_src(self, name, kind="book"):
        from factory._smoke_fixtures import (make_broken_docx, make_docx,
                                              make_sample_book)
        p = os.path.join(tempfile.gettempdir(), f"pct-pf-{name}")
        if kind == "book":
            make_sample_book(p)
        elif kind == "broken":
            make_broken_docx(p)
        else:
            make_docx(p, [("Normal", "متن کوتاه " + name)])
        return p

    def make_persian_set(self):
        """5 Persian-named books + 1 corrupt file. -> list of paths."""
        from factory._smoke_fixtures import make_broken_docx
        tmp = tempfile.mkdtemp(prefix="pct-pf-src-")
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        paths = []
        for i, name in enumerate(PERSIAN_FILES):
            from factory._smoke_fixtures import make_docx
            p = os.path.join(tmp, name)
            make_docx(p, [
                ("Normal", f"عنوان: {name}"),
                ("Normal", "نویسنده: نویسنده نمونه"),
                ("Heading 1", "فصل اول"),
                ("Normal", f"متن فارسی کتاب شماره {i + 1}."),
                ("Heading 1", "فصل دوم"),
                ("Normal", "پایان کتاب."),
            ])
            paths.append(p)
        broken = os.path.join(tmp, CORRUPT_FILE)
        make_broken_docx(broken)
        paths.append(broken)
        return paths  # [5 books..., corrupt]

    def _file_entry(self, path, size=None):
        return {"name": os.path.basename(path),
                "size": size if size is not None else os.path.getsize(path),
                "sha256": self.sha256_file(path)}

    def make_batch(self, coll_id, files, folder_name="پوشه آزمایشی"):
        r = self.client.post("/api/knowledge/import/batches", json={
            "collection_id": coll_id,
            "folder_name": folder_name,
            "files": files,
        })
        self.assertEqual(r.status_code, 201, r.get_data(as_text=True))
        return r.get_json()

    def batch_upload(self, batch_id, path, name=None):
        with open(path, "rb") as f:
            data = {"file": (io.BytesIO(f.read()),
                             name or os.path.basename(path))}
        return self.client.post(
            f"/api/knowledge/import/batches/{batch_id}/files",
            data=data, content_type="multipart/form-data",
        )

    def process_batch(self, batch_id):
        r = self.client.post(f"/api/knowledge/import/batches/{batch_id}/process")
        self.assertIn(r.status_code, (200, 202), r.get_data(as_text=True))
        return r.get_json()

    def wait_job(self, job_id, timeout=60.0):
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

    def _batch_detail(self, batch_id):
        r = self.client.get(f"/api/knowledge/import/batches/{batch_id}")
        self.assertEqual(r.status_code, 200, r.get_data(as_text=True))
        return r.get_json()

    def retry_failed(self, batch_id):
        return self.client.post(
            f"/api/knowledge/import/batches/{batch_id}/retry-failed")

    def _queue_rows(self, coll_id):
        conn = self._db()
        try:
            return [dict(x) for x in conn.execute(
                "SELECT * FROM knowledge_file_queue WHERE collection_id=?",
                (coll_id,)).fetchall()]
        finally:
            conn.close()

    # ── PCM-20.9 Stage D helpers ────────────────────────────────────────
    def upload_and_process(self, path, name=None):
        """Single DOCX upload + process (waits for the job). Returns the
        final document row (dict) from GET documents."""
        with open(path, "rb") as fh:
            raw = fh.read()
        r = self.client.post(
            f"/api/knowledge/collections/"
            f"{self._cur_coll_id()}/documents",
            data={"file": (io.BytesIO(raw), name or os.path.basename(path))},
            content_type="multipart/form-data")
        self.assertEqual(r.status_code, 201, r.get_data(as_text=True))
        doc_id = r.get_json()["document"]["document_id"]
        r = self.client.post(f"/api/knowledge/documents/{doc_id}/process")
        self.assertIn(r.status_code, (200, 202), r.get_data(as_text=True))
        job = self.wait_job(r.get_json()["job"]["job_id"])
        self.assertEqual(job["status"], "succeeded", job)
        docs = self.client.get(
            f"/api/knowledge/collections/{self._cur_coll_id()}/documents"
        ).get_json()["documents"]
        row = next(d for d in docs if d["document_id"] == doc_id)
        self.assertIn(row["status"], ("parsed", "needs_review"), row)
        return row

    def _cur_coll_id(self):
        # the last collection created in this test
        assert self._cur_coll is not None, "make_collection() first"
        return self._cur_coll["id"]


class TestPF_A01_PlanPersistence(Base):
    """PF-A01 — the plan is persisted, one row per file, with per-file state."""

    def test_plan_rows_persisted_and_invalid_flagged(self):
        coll = self.make_collection()
        paths = self.make_persian_set()
        good = paths[:5]
        corrupt = paths[5]
        # a bad entry (wrong extension) + the 5 books + the corrupt file
        bad_txt = os.path.join(self._datadir, "notes.txt")
        with open(bad_txt, "w", encoding="utf-8") as f:
            f.write("نه docx نیست")

        r = self.client.post("/api/knowledge/import/batches", json={
            "collection_id": coll["collection_id"],
            "folder_name": "folder-A",
            "files": ([self._file_entry(p) for p in good + [corrupt]]
                      + [{"name": "notes.txt",
                          "size": os.path.getsize(bad_txt),
                          "sha256": self.sha256_file(bad_txt)}]),
        })
        self.assertEqual(r.status_code, 201, r.get_data(as_text=True))
        body = r.get_json()
        self.assertEqual(body["summary"]["total"], 7)
        self.assertEqual(body["summary"]["pending"], 6)
        self.assertEqual(body["summary"]["invalid"], 1)
        batch_id = body["batch"]["batch_id"]

        conn = self._db()
        try:
            rows = [dict(x) for x in conn.execute(
                "SELECT seq, file_name, sha256, size_bytes, status, error, "
                "document_id FROM knowledge_batch_files "
                "WHERE batch_id=? ORDER BY seq", (batch_id,)).fetchall()]
        finally:
            conn.close()
        self.assertEqual(len(rows), 7)
        self.assertEqual(rows[0]["file_name"], PERSIAN_FILES[0])
        self.assertEqual(rows[0]["status"], "pending")
        self.assertEqual(rows[0]["sha256"], self.sha256_file(good[0]))
        self.assertEqual(rows[0]["size_bytes"], os.path.getsize(good[0]))
        self.assertIsNone(rows[0]["document_id"])
        self.assertEqual(rows[6]["status"], "invalid_extension")
        self.assertEqual(rows[6]["error"], "invalid extension (only .docx)")

        # batch detail exposes the persisted plan + upload summary
        det = self._batch_detail(batch_id)
        self.assertEqual(len(det["plan_files"]), 7)
        self.assertEqual(det["upload_summary"]["total"], 7)
        self.assertEqual(det["upload_summary"]["pending"], 6)
        self.assertEqual(det["upload_summary"]["invalid"], 1)
        self.assertEqual(det["upload_summary"]["uploaded"], 0)


class TestPF_A02_UploadFlow(Base):
    """PF-A02 — the REAL per-file upload: sha-matched, per-file outcomes."""

    def test_upload_all_outcomes(self):
        coll = self.make_collection()
        paths = self.make_persian_set()
        good, corrupt = paths[:5], paths[5]
        plan = self.make_batch(
            coll["collection_id"],
            [self._file_entry(p) for p in good + [corrupt]])
        batch_id = plan["batch"]["batch_id"]

        # 1) upload the first good book -> 201 + document linked to batch
        r = self.batch_upload(batch_id, good[0])
        self.assertEqual(r.status_code, 201, r.get_data(as_text=True))
        body = r.get_json()
        self.assertEqual(body["status"], "uploaded")
        self.assertEqual(body["sha256"], self.sha256_file(good[0]))
        doc = body["document"]
        self.assertEqual(doc["document_id"], "d-" +
                         self.sha256_file(good[0])[:8])
        self.assertEqual(doc["batch_id"], batch_id)
        self.assertTrue(doc["file_name"].endswith(".docx"))

        conn = self._db()
        try:
            row = conn.execute(
                "SELECT status, document_id FROM knowledge_batch_files "
                "WHERE batch_id=? AND file_name=?",
                (batch_id, PERSIAN_FILES[0])).fetchone()
        finally:
            conn.close()
        self.assertEqual(row["status"], "uploaded")
        self.assertEqual(row["document_id"], doc["document_id"])

        # the original bytes are stored on disk (same layout as single upload)
        data_dir = knowledge_api.knowledge_data_dir()
        sha = self.sha256_file(good[0])
        stored = os.path.join(
            data_dir, "files", sha[:12], f"f-{sha[:8]}.docx")
        self.assertTrue(os.path.exists(stored), stored)
        self.assertEqual(self.sha256_file(stored), sha)

        # 2) idempotent retry of the SAME file -> 200 duplicate_upload,
        #    same document, no second document row
        r = self.batch_upload(batch_id, good[0])
        self.assertEqual(r.status_code, 200, r.get_data(as_text=True))
        body = r.get_json()
        self.assertTrue(body["duplicate_upload"])
        self.assertEqual(body["document"]["document_id"], doc["document_id"])
        conn = self._db()
        try:
            n = conn.execute(
                "SELECT COUNT(*) AS n FROM knowledge_collection_documents "
                "WHERE sha256=?", (sha,)).fetchone()["n"]
        finally:
            conn.close()
        self.assertEqual(n, 1)

        # 3) a file that is NOT in the plan -> 400 not_in_plan
        other = self._make_src("other.docx", kind="mini")
        r = self.batch_upload(batch_id, other, name=PERSIAN_FILES[1])
        self.assertEqual(r.status_code, 400, r.get_data(as_text=True))
        self.assertEqual(r.get_json()["code"], "not_in_plan")

        # 4) size mismatch (planned size differs from the real file) ->
        #    400 + plan row flagged size_mismatch
        plan2 = self.make_batch(
            coll["collection_id"],
            [self._file_entry(good[1], size=12345)])
        bid2 = plan2["batch"]["batch_id"]
        r = self.batch_upload(bid2, good[1])
        self.assertEqual(r.status_code, 400, r.get_data(as_text=True))
        body = r.get_json()
        self.assertEqual(body["code"], "size_mismatch")
        self.assertEqual(body["planned_size"], 12345)
        self.assertEqual(body["actual_size"], os.path.getsize(good[1]))
        conn = self._db()
        try:
            row = conn.execute(
                "SELECT status FROM knowledge_batch_files "
                "WHERE batch_id=? AND file_name=?",
                (bid2, PERSIAN_FILES[1])).fetchone()
        finally:
            conn.close()
        self.assertEqual(row["status"], "size_mismatch")

        # 5) collection-level duplicate (same sha single-uploaded before) ->
        #    409 + plan row flagged duplicate with the existing document
        with open(good[2], "rb") as fh:
            raw = fh.read()
        r = self.client.post(
            f"/api/knowledge/collections/{coll['id']}/documents",
            data={"file": (io.BytesIO(raw), os.path.basename(good[2]))},
            content_type="multipart/form-data")
        self.assertEqual(r.status_code, 201, r.get_data(as_text=True))
        existing = r.get_json()["document"]["document_id"]
        plan3 = self.make_batch(
            coll["collection_id"], [self._file_entry(good[2])])
        bid3 = plan3["batch"]["batch_id"]
        r = self.batch_upload(bid3, good[2])
        self.assertEqual(r.status_code, 409, r.get_data(as_text=True))
        body = r.get_json()
        self.assertEqual(body["code"], "duplicate")
        self.assertEqual(body["existing_document_id"], existing)
        conn = self._db()
        try:
            row = conn.execute(
                "SELECT status, document_id FROM knowledge_batch_files "
                "WHERE batch_id=? AND file_name=?",
                (bid3, PERSIAN_FILES[2])).fetchone()
        finally:
            conn.close()
        self.assertEqual(row["status"], "duplicate")
        self.assertEqual(row["document_id"], existing)

        # 6) not a docx / missing file / unknown batch
        txt = os.path.join(self._datadir, "x.txt")
        with open(txt, "w", encoding="utf-8") as f:
            f.write("txt")
        r = self.batch_upload(batch_id, txt)
        self.assertEqual(r.status_code, 400)
        r = self.client.post(
            f"/api/knowledge/import/batches/{batch_id}/files",
            data={}, content_type="multipart/form-data")
        self.assertEqual(r.status_code, 400)
        r = self.batch_upload("b-00000000", good[3])
        self.assertEqual(r.status_code, 404)

        # 7) upload_summary reflects the first batch's state
        det = self._batch_detail(batch_id)
        s = det["upload_summary"]
        self.assertEqual(s["total"], 6)
        self.assertEqual(s["uploaded"], 1)
        self.assertEqual(s["pending"], 5)


class TestPF_A03_BatchProcessE2E(Base):
    """PF-A03 — full Stage A flow: plan -> upload 5 good + 1 corrupt ->
    process -> batch-scoped queue results."""

    def test_stage_a_end_to_end(self):
        coll = self.make_collection()
        paths = self.make_persian_set()
        good, corrupt = paths[:5], paths[5]

        plan = self.make_batch(
            coll["collection_id"],
            [self._file_entry(p) for p in good + [corrupt]])
        batch_id = plan["batch"]["batch_id"]
        for p in good + [corrupt]:
            r = self.batch_upload(batch_id, p)
            self.assertEqual(r.status_code, 201, r.get_data(as_text=True))

        # a document from OUTSIDE the batch (single upload) must NOT be
        # processed by the batch job
        outsider = self._make_src("خارجی.docx", kind="mini")
        with open(outsider, "rb") as fh:
            raw = fh.read()
        r = self.client.post(
            f"/api/knowledge/collections/{coll['id']}/documents",
            data={"file": (io.BytesIO(raw), os.path.basename(outsider))},
            content_type="multipart/form-data")
        self.assertEqual(r.status_code, 201, r.get_data(as_text=True))
        outsider_doc = r.get_json()["document"]["document_id"]

        body = self.process_batch(batch_id)
        self.assertEqual(body["files_queued"], 6)
        job = self.wait_job(body["job"]["job_id"])
        self.assertEqual(job["status"], "succeeded", job)

        conn = self._db()
        try:
            q = [dict(x) for x in conn.execute(
                "SELECT * FROM knowledge_file_queue WHERE collection_id=?",
                (coll["collection_id"],)).fetchall()]
            outsider = conn.execute(
                "SELECT status FROM knowledge_collection_documents "
                "WHERE document_id=?", (outsider_doc,)).fetchone()
        finally:
            conn.close()
        # exactly the batch's 6 files are queued — the outsider is not
        self.assertEqual(len(q), 6)
        self.assertEqual(
            sorted(x["status"] for x in q),
            ["failed"] + ["succeeded"] * 5)
        self.assertEqual(outsider["status"], "uploaded")  # untouched

        det = self._batch_detail(batch_id)
        self.assertEqual(det["batch"]["status"], "done")
        self.assertEqual(det["batch"]["processed_count"], 5)
        self.assertEqual(det["batch"]["failed_count"], 1)
        self.assertEqual(len(det["documents"]), 6)
        self.assertEqual(len(det["queue"]), 6)
        # per-file plan state after processing
        by_name = {p["file_name"]: p for p in det["plan_files"]}
        self.assertEqual(by_name[PERSIAN_FILES[0]]["status"], "uploaded")
        self.assertIsNotNone(by_name[PERSIAN_FILES[0]]["document_id"])
        self.assertEqual(by_name[CORRUPT_FILE]["status"], "uploaded")
        # the corrupt file's queue row failed with an error
        cq = [x for x in det["queue"] if x["status"] == "failed"]
        self.assertEqual(len(cq), 1)
        self.assertTrue(cq[0]["last_error"])


class TestPF_A04_EmptyBatchGuard(Base):
    """PF-A04 — a NEW batch with plan rows but no uploads -> 409."""

    def test_process_without_uploads_409(self):
        coll = self.make_collection()
        paths = self.make_persian_set()
        plan = self.make_batch(
            coll["collection_id"],
            [self._file_entry(p) for p in paths[:5]])
        batch_id = plan["batch"]["batch_id"]

        r = self.client.post(
            f"/api/knowledge/import/batches/{batch_id}/process")
        self.assertEqual(r.status_code, 409, r.get_data(as_text=True))
        body = r.get_json()
        self.assertEqual(body["code"], "no_files_uploaded")
        self.assertEqual(body["planned"], 5)
        self.assertEqual(body["uploaded"], 0)

        # the batch must not have been marked processing
        conn = self._db()
        try:
            st = conn.execute(
                "SELECT status FROM knowledge_import_batches "
                "WHERE batch_id=?", (batch_id,)).fetchone()["status"]
        finally:
            conn.close()
        self.assertEqual(st, "planned")


class TestPF_A05_LegacyFlow(Base):
    """PF-A05 — legacy PCM-15 flow: single uploads BEFORE the plan.

    The plan flags every entry 'duplicate' (sha already known); processing
    must still process exactly the registered documents (scoping via the
    plan rows' document references), and pre-20.9 batches (no plan rows at
    all) keep whole-collection semantics.
    """

    def test_single_upload_then_plan_then_process(self):
        coll = self.make_collection()
        paths = self.make_persian_set()
        good, corrupt = paths[:5], paths[5]

        # single uploads FIRST (pre-20.9 UI flow)
        doc_ids = []
        for p in good[:2] + [corrupt]:
            with open(p, "rb") as fh:
                raw = fh.read()
            r = self.client.post(
                f"/api/knowledge/collections/{coll['id']}/documents",
                data={"file": (io.BytesIO(raw), os.path.basename(p))},
                content_type="multipart/form-data")
            self.assertEqual(r.status_code, 201, r.get_data(as_text=True))
            doc_ids.append(r.get_json()["document"]["document_id"])

        plan = self.make_batch(
            coll["collection_id"],
            [self._file_entry(p) for p in good[:2] + [corrupt]])
        batch_id = plan["batch"]["batch_id"]
        # all entries already known -> duplicates
        self.assertEqual(plan["summary"]["pending"], 0)
        self.assertEqual(plan["summary"]["duplicate"], 3)

        body = self.process_batch(batch_id)
        self.assertEqual(body["files_queued"], 3)
        job = self.wait_job(body["job"]["job_id"])
        self.assertEqual(job["status"], "succeeded", job)

        det = self._batch_detail(batch_id)
        self.assertEqual(det["batch"]["status"], "done")
        self.assertEqual(det["batch"]["processed_count"], 2)
        self.assertEqual(det["batch"]["failed_count"], 1)
        self.assertEqual(len(det["queue"]), 3)
        # the 2 un-uploaded remaining books are NOT in this batch's scope
        self.assertEqual(len(det["documents"]), 3)
        conn = self._db()
        try:
            n = conn.execute(
                "SELECT COUNT(*) AS n FROM knowledge_file_queue "
                "WHERE collection_id=?",
                (coll["collection_id"],)).fetchone()["n"]
        finally:
            conn.close()
        self.assertEqual(n, 3)


class TestPF_B01_RetryOnlyFailed(Base):
    """PF-B01 — Stage B: retry-failed re-runs ONLY the failed files.

    Succeeded files must stay untouched (checkpoint/resume): same attempts,
    same status, no error. The failed file is re-executed (attempts 1 -> 2).
    Batch counters are re-applied from the real document states.
    """

    def test_retry_touches_failed_only(self):
        coll = self.make_collection()
        paths = self.make_persian_set()
        good, corrupt = paths[:5], paths[5]

        plan = self.make_batch(
            coll["collection_id"],
            [self._file_entry(p) for p in good + [corrupt]])
        batch_id = plan["batch"]["batch_id"]
        for p in good + [corrupt]:
            r = self.batch_upload(batch_id, p)
            self.assertEqual(r.status_code, 201, r.get_data(as_text=True))

        body = self.process_batch(batch_id)
        self.wait_job(body["job"]["job_id"])

        before = self._queue_rows(coll["collection_id"])
        failed = [q for q in before if q["status"] == "failed"]
        ok = [q for q in before if q["status"] == "succeeded"]
        self.assertEqual(len(failed), 1)
        self.assertEqual(len(ok), 5)
        snap_ok = {q["file_key"]: (q["attempts"], q["status"],
                                   q["last_error"]) for q in ok}

        r = self.retry_failed(batch_id)
        self.assertEqual(r.status_code, 202, r.get_data(as_text=True))
        jbody = r.get_json()
        self.assertEqual(jbody["files_queued"], 1)
        self.assertFalse(jbody["resubmitted"])
        job = self.wait_job(jbody["job"]["job_id"])
        self.assertEqual(job["status"], "succeeded", job)

        after = self._queue_rows(coll["collection_id"])
        # the 5 succeeded files are bit-for-bit untouched
        for q in after:
            if q["file_key"] in snap_ok:
                self.assertEqual(
                    (q["attempts"], q["status"], q["last_error"]),
                    snap_ok[q["file_key"]],
                    f"succeeded file {q['file_key']} was touched")
        # the corrupt file was re-executed: attempts 1 -> 2, still failing
        f = [q for q in after if q["file_key"] == failed[0]["file_key"]]
        self.assertEqual(len(f), 1)
        self.assertEqual(f[0]["attempts"], 2)
        self.assertEqual(f[0]["status"], "failed")
        self.assertTrue(f[0]["last_error"])

        det = self._batch_detail(batch_id)
        self.assertEqual(det["batch"]["status"], "done")
        self.assertEqual(det["batch"]["processed_count"], 5)
        self.assertEqual(det["batch"]["failed_count"], 1)


class TestPF_B02_RetryErrors(Base):
    """PF-B02 — Stage B: retry-failed error paths.

    409 no_failed_files when the batch has nothing to retry; 404 for an
    unknown batch id.
    """

    def test_no_failed_files_409(self):
        coll = self.make_collection()
        from factory._smoke_fixtures import make_docx
        tmp = tempfile.mkdtemp(prefix="pct-pf-b2-")
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        paths = []
        for i in range(2):
            p = os.path.join(tmp, f"کتاب-{i}.docx")
            make_docx(p, [
                ("Normal", f"عنوان: کتاب {i}"),
                ("Heading 1", "فصل اول"),
                ("Normal", f"متن فارسی کتاب شماره {i + 1}."),
                ("Heading 1", "فصل دوم"),
                ("Normal", "پایان کتاب."),
            ])
            paths.append(p)

        plan = self.make_batch(
            coll["collection_id"], [self._file_entry(p) for p in paths])
        batch_id = plan["batch"]["batch_id"]
        for p in paths:
            r = self.batch_upload(batch_id, p)
            self.assertEqual(r.status_code, 201, r.get_data(as_text=True))

        body = self.process_batch(batch_id)
        self.wait_job(body["job"]["job_id"])
        self.assertEqual(
            sorted(q["status"] for q in self._queue_rows(
                coll["collection_id"])), ["succeeded", "succeeded"])

        r = self.retry_failed(batch_id)
        self.assertEqual(r.status_code, 409, r.get_data(as_text=True))
        j = r.get_json()
        self.assertEqual(j["code"], "no_failed_files")
        self.assertEqual(j["failed"], 0)

    def test_unknown_batch_404(self):
        r = self.retry_failed("b-00000000")
        self.assertEqual(r.status_code, 404, r.get_data(as_text=True))


class TestPF_B03_TransientRecovery(Base):
    """PF-B03 — Stage B: a transient failure (missing stored original)
    recovers via retry-failed after the file is restored.

    Also exercises force_retry: the retry job key was already used by a
    SUCCEEDED retry run, so a later retry must re-execute the same job
    row instead of being blocked by idempotency.
    """

    def test_delete_restore_then_retry(self):
        from factory._smoke_fixtures import make_docx
        coll = self.make_collection()
        tmp = tempfile.mkdtemp(prefix="pct-pf-b3-")
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        book = os.path.join(tmp, "کتاب-موقتی.docx")
        make_docx(book, [
            ("Normal", "عنوان: کتاب موقتی"),
            ("Normal", "نویسنده: نویسنده نمونه"),
            ("Heading 1", "فصل اول"),
            ("Normal", "متن فارسی کتاب موقتی."),
            ("Heading 1", "فصل دوم"),
            ("Normal", "پایان کتاب."),
        ])

        plan = self.make_batch(
            coll["collection_id"], [self._file_entry(book)])
        batch_id = plan["batch"]["batch_id"]
        r = self.batch_upload(batch_id, book)
        self.assertEqual(r.status_code, 201, r.get_data(as_text=True))
        sha = r.get_json()["sha256"]
        doc_id = r.get_json()["document"]["document_id"]
        file_id = "f-" + sha[:8]
        stored = knowledge_api._stored_file_path(sha, file_id, ".docx")
        self.assertTrue(os.path.isfile(stored))

        # break the store: move the original away -> processing must fail
        backup = os.path.join(tmp, "backup.docx")
        shutil.move(stored, backup)

        body = self.process_batch(batch_id)
        self.wait_job(body["job"]["job_id"])
        q = self._queue_rows(coll["collection_id"])
        self.assertEqual(len(q), 1)
        self.assertEqual(q[0]["status"], "failed")
        self.assertEqual(q[0]["attempts"], 1)

        # retry while still broken -> honest second failure (attempts 2)
        r = self.retry_failed(batch_id)
        self.assertEqual(r.status_code, 202, r.get_data(as_text=True))
        self.wait_job(r.get_json()["job"]["job_id"])
        q = self._queue_rows(coll["collection_id"])
        self.assertEqual(q[0]["status"], "failed")
        self.assertEqual(q[0]["attempts"], 2)

        # restore the original -> the retry succeeds. This re-submits the
        # SAME job_key whose previous run already SUCCEEDED (force_retry).
        shutil.copyfile(backup, stored)
        r = self.retry_failed(batch_id)
        self.assertEqual(r.status_code, 202, r.get_data(as_text=True))
        job = self.wait_job(r.get_json()["job"]["job_id"])
        self.assertEqual(job["status"], "succeeded", job)
        q = self._queue_rows(coll["collection_id"])
        self.assertEqual(q[0]["status"], "succeeded")
        self.assertEqual(q[0]["attempts"], 3)
        self.assertEqual(q[0]["last_error"], None)

        d = self.client.get(
            f"/api/knowledge/documents/{doc_id}").get_json()
        self.assertEqual(d["document"]["status"], "parsed")

        # nothing left to retry
        r = self.retry_failed(batch_id)
        self.assertEqual(r.status_code, 409, r.get_data(as_text=True))
        self.assertEqual(r.get_json()["code"], "no_failed_files")


class TestPF_C01_SchemaLifecycle(Base):
    """PF-C01 — Stage C: schema version lifecycle.

    Draft creation (default template) -> validate against REAL blocks
    (honest counts from the collection's processed documents) -> approve
    -> collection.schema_version points at it -> draft edits immutable
    after approval; a second version is created as a new draft.
    """

    def test_lifecycle(self):
        from factory._smoke_fixtures import make_docx
        coll = self.make_collection()
        tmp = tempfile.mkdtemp(prefix="pct-pf-c1-")
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        paths = []
        for i in range(2):
            p = os.path.join(tmp, f"کتاب-{i}.docx")
            make_docx(p, [
                ("Normal", f"عنوان: کتاب {i}"),
                ("Normal", "نویسنده: نویسنده نمونه"),
                ("Heading 1", "فصل اول"),
                ("Normal", f"متن فارسی کتاب شماره {i + 1}."),
                ("Heading 1", "فصل دوم"),
                ("Normal", "پایان کتاب."),
            ])
            paths.append(p)
        for p in paths:
            with open(p, "rb") as fh:
                raw = fh.read()
            r = self.client.post(
                f"/api/knowledge/collections/{coll['id']}/documents",
                data={"file": (io.BytesIO(raw), os.path.basename(p))},
                content_type="multipart/form-data")
            self.assertEqual(r.status_code, 201, r.get_data(as_text=True))
        # process both documents so real blocks.jsonl exist
        docs = self.client.get(
            f"/api/knowledge/collections/{coll['id']}/documents").get_json()
        for d in docs["documents"]:
            r = self.client.post(
                f"/api/knowledge/documents/{d['document_id']}/process")
            self.assertIn(r.status_code, (200, 202), r.get_data(as_text=True))
            job = self.wait_job(r.get_json()["job"]["job_id"])
            self.assertEqual(job["status"], "succeeded", job)

        cid = coll["collection_id"]

        # empty schema list + approved null
        r = self.client.get(f"/api/knowledge/collections/{cid}/schema")
        self.assertEqual(r.status_code, 200, r.get_data(as_text=True))
        j = r.get_json()
        self.assertEqual(j["versions"], [])
        self.assertIsNone(j["approved"])
        self.assertTrue(j["default_fields"])

        # create a draft (default template)
        r = self.client.post(
            f"/api/knowledge/collections/{cid}/schema",
            json={"description": "اسکیم بلوک‌های پیکره"})
        self.assertEqual(r.status_code, 201, r.get_data(as_text=True))
        sv1 = r.get_json()["schema"]
        self.assertEqual(sv1["version"], 1)
        self.assertEqual(sv1["status"], "draft")
        self.assertTrue(sv1["fields"])
        names = [f["name"] for f in sv1["fields"]]
        self.assertIn("block_id", names)
        self.assertIn("normalized_text", names)

        # validate BEFORE approve -> ok, honest block counts
        r = self.client.post(
            f"/api/knowledge/collections/{cid}/schema/{sv1['schema_id']}/validate")
        self.assertEqual(r.status_code, 200, r.get_data(as_text=True))
        rep = r.get_json()["report"]
        self.assertTrue(rep["ok"], rep)
        self.assertGreater(rep["documents_scanned"], 0)
        self.assertGreater(rep["blocks_scanned"], 0)
        self.assertTrue(rep["observed_block_types"])
        # block_id is required -> coverage 1.0
        bid = next(f for f in rep["fields"] if f["name"] == "block_id")
        self.assertEqual(bid["coverage"], 1.0)

        # approve
        r = self.client.post(
            f"/api/knowledge/collections/{cid}/schema/{sv1['schema_id']}/approve")
        self.assertEqual(r.status_code, 200, r.get_data(as_text=True))
        self.assertTrue(r.get_json()["ok"])

        # collection now points at the approved schema
        det = self.client.get(
            f"/api/knowledge/collections/{coll['id']}").get_json()["collection"]
        self.assertEqual(det["schema_version"], sv1["schema_id"])
        self.assertIsNotNone(det["schema"])
        self.assertEqual(det["schema"]["schema_id"], sv1["schema_id"])

        # approved version is immutable
        r = self.client.patch(
            f"/api/knowledge/collections/{cid}/schema/{sv1['schema_id']}",
            json={"description": "تغییر بعد از تأیید"})
        self.assertEqual(r.status_code, 409, r.get_data(as_text=True))
        self.assertEqual(r.get_json()["code"], "immutable")

        # a second version is a new draft (version 2)
        r = self.client.post(
            f"/api/knowledge/collections/{cid}/schema", json={})
        self.assertEqual(r.status_code, 201, r.get_data(as_text=True))
        sv2 = r.get_json()["schema"]
        self.assertEqual(sv2["version"], 2)
        self.assertEqual(sv2["status"], "draft")

        # list shows both, approved = sv1
        r = self.client.get(f"/api/knowledge/collections/{cid}/schema")
        j = r.get_json()
        self.assertEqual(len(j["versions"]), 2)
        self.assertEqual(j["versions"][0]["version"], 2)  # newest first
        self.assertEqual(j["approved"]["schema_id"], sv1["schema_id"])


class TestPF_C02_SchemaValidation(Base):
    """PF-C02 — Stage C: field validation & honest failure reporting.

    - invalid field definitions are rejected (bad name / bad type /
      duplicate name / duplicate es_field / empty list);
    - a required field that does NOT exist in any real block produces a
      FAILING validation report, which blocks approval (409 not_validated);
    - an unknown collection / unknown schema_id -> 404.
    """

    def test_field_validation_errors(self):
        coll = self.make_collection()
        cid = coll["collection_id"]
        bad_sets = [
            {"fields": []},
            {"fields": [{"name": "Bad Name", "type": "string"}]},
            {"fields": [{"name": "x", "type": "not-a-type"}]},
            {"fields": [{"name": "x", "type": "string"},
                        {"name": "x", "type": "integer"}]},
            {"fields": [{"name": "x", "type": "string", "es_field": "e"},
                        {"name": "y", "type": "string", "es_field": "e"}]},
        ]
        for body in bad_sets:
            r = self.client.post(
                f"/api/knowledge/collections/{cid}/schema", json=body)
            self.assertEqual(r.status_code, 400, r.get_data(as_text=True))
            self.assertTrue(r.get_json()["errors"])

    def test_required_field_missing_blocks_approve(self):
        from factory._smoke_fixtures import make_docx
        coll = self.make_collection()
        tmp = tempfile.mkdtemp(prefix="pct-pf-c2-")
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        p = os.path.join(tmp, "کتاب-تک.docx")
        make_docx(p, [
            ("Normal", "عنوان: کتاب تک"),
            ("Heading 1", "فصل اول"),
            ("Normal", "متن فارسی کتاب."),
        ])
        with open(p, "rb") as fh:
            raw = fh.read()
        r = self.client.post(
            f"/api/knowledge/collections/{coll['id']}/documents",
            data={"file": (io.BytesIO(raw), os.path.basename(p))},
            content_type="multipart/form-data")
        self.assertEqual(r.status_code, 201, r.get_data(as_text=True))
        doc_id = r.get_json()["document"]["document_id"]
        r = self.client.post(
            f"/api/knowledge/documents/{doc_id}/process")
        self.assertIn(r.status_code, (200, 202), r.get_data(as_text=True))
        self.wait_job(r.get_json()["job"]["job_id"])

        cid = coll["collection_id"]
        # a custom schema where a REQUIRED field does not exist in blocks
        fields = [
            {"name": "block_id", "type": "string", "required": True,
             "es_field": "block_id"},
            {"name": "page", "type": "integer", "required": True,
             "es_field": "page"},
        ]
        r = self.client.post(
            f"/api/knowledge/collections/{cid}/schema",
            json={"fields": fields, "description": "اسکیم با فیلد غلط"})
        self.assertEqual(r.status_code, 201, r.get_data(as_text=True))
        sv = r.get_json()["schema"]

        # validation must FAIL: page is always null in docx -> required missing
        r = self.client.post(
            f"/api/knowledge/collections/{cid}/schema/{sv['schema_id']}/validate")
        self.assertEqual(r.status_code, 200, r.get_data(as_text=True))
        rep = r.get_json()["report"]
        self.assertFalse(rep["ok"], rep)
        self.assertTrue(any("page" in e for e in rep["errors"]))
        page = next(f for f in rep["fields"] if f["name"] == "page")
        self.assertEqual(page["present"], 0)

        # approval is blocked by the failing report
        r = self.client.post(
            f"/api/knowledge/collections/{cid}/schema/{sv['schema_id']}/approve")
        self.assertEqual(r.status_code, 409, r.get_data(as_text=True))
        self.assertEqual(r.get_json()["code"], "not_validated")

    def test_unknown_collection_and_schema_404(self):
        r = self.client.get("/api/knowledge/collections/c-00000000/schema")
        self.assertEqual(r.status_code, 404, r.get_data(as_text=True))
        coll = self.make_collection()
        r = self.client.get(
            f"/api/knowledge/collections/{coll['collection_id']}"
            "/schema/sv-0000")
        self.assertEqual(r.status_code, 404, r.get_data(as_text=True))


class TestPF_C03_SchemaDraftEdit(Base):
    """PF-C03 — Stage C: a DRAFT version can be edited (description and
    fields are re-validated); an invalid edit is rejected and leaves the
    draft unchanged."""

    def test_draft_edit_and_reject(self):
        coll = self.make_collection()
        cid = coll["collection_id"]
        r = self.client.post(
            f"/api/knowledge/collections/{cid}/schema",
            json={"description": "پیش‌نویس"})
        sv = r.get_json()["schema"]

        # edit description + fields (valid)
        new_fields = [
            {"name": "block_id", "type": "string", "required": True,
             "es_field": "block_id"},
            {"name": "raw_text", "type": "text", "required": True},
        ]
        r = self.client.patch(
            f"/api/knowledge/collections/{cid}/schema/{sv['schema_id']}",
            json={"description": "ویرایش‌شده", "fields": new_fields})
        self.assertEqual(r.status_code, 200, r.get_data(as_text=True))
        upd = r.get_json()["schema"]
        self.assertEqual(upd["description"], "ویرایش‌شده")
        self.assertEqual(len(upd["fields"]), 2)
        self.assertEqual(upd["status"], "draft")

        # invalid edit rejected (400) and the draft keeps the prior fields
        r = self.client.patch(
            f"/api/knowledge/collections/{cid}/schema/{sv['schema_id']}",
            json={"fields": [{"name": "bad name", "type": "string"}]})
        self.assertEqual(r.status_code, 400, r.get_data(as_text=True))
        r = self.client.get(
            f"/api/knowledge/collections/{cid}/schema/{sv['schema_id']}")
        kept = r.get_json()["schema"]
        self.assertEqual(len(kept["fields"]), 2)
        self.assertEqual(kept["description"], "ویرایش‌شده")


# ---------------------------------------------------------------------------
# PCM-20.9 Stage D — canonical corpus (c-1) + guarded ES index factory
# ---------------------------------------------------------------------------


def _corpus_build_paths(coll_pk, cid):
    import knowledge_api
    root = os.path.join(knowledge_api.knowledge_data_dir(),
                        "corpus_builds", cid)
    return root, os.path.join(root, "dumps"), os.path.join(root, "corpus")


class _StageDPrep(Base):
    """Shared setup: 2 processed Persian books in one collection."""

    def _prep(self, n=2):
        from factory._smoke_fixtures import make_docx
        coll = self.make_collection()
        tmp = tempfile.mkdtemp(prefix="pct-pf-d-")
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        rows = []
        for i in range(n):
            p = os.path.join(tmp, f"کتاب-{i}.docx")
            make_docx(p, [
                ("Normal", f"عنوان: کتاب {i}"),
                ("Normal", "نویسنده: نویسنده نمونه"),
                ("Heading 1", "فصل اول"),
                ("Normal", f"متن فارسی کتاب شماره {i + 1}."),
                ("Heading 1", "فصل دوم"),
                ("Normal", "پایان کتاب."),
            ])
            rows.append(self.upload_and_process(p))
        return coll, rows

    def corpus_build(self, coll_pk):
        r = self.client.post(
            f"/api/knowledge/collections/{coll_pk}/corpus/build")
        self.assertIn(r.status_code, (200, 202), r.get_data(as_text=True))
        j = r.get_json()
        self.assertTrue(j["ok"])
        job = self.wait_job(j["job"]["job_id"])
        return r.status_code, j, job

    def corpus_builds(self, coll_pk):
        r = self.client.get(
            f"/api/knowledge/collections/{coll_pk}/corpus/builds")
        self.assertEqual(r.status_code, 200, r.get_data(as_text=True))
        return r.get_json()["builds"]


class TestPF_D01_CorpusBuildReal(_StageDPrep):
    """PF-D01 — Stage D: the REAL build.

    2 processed books -> POST corpus/build -> d-1 dump per document
    (validated) -> c-1 canonical corpus on disk (4 JSONL + deterministic
    zip + manifest) -> build row with content_sha256 (archive sha),
    status 'succeeded', ES part honestly 'blocked' (no PCT_ES_URL).
    GET /corpus/builds + GET /index-builds/<iv_id> (with manifest).
    """

    def test_corpus_build_end_to_end(self):
        os.environ.pop("PCT_ES_URL", None)
        from factory.dump import validate_dump
        import knowledge_api
        coll, rows = self._prep(2)
        cid = coll["collection_id"]
        blocks_total = sum(r["blocks_count"] for r in rows)
        self.assertGreater(blocks_total, 0)

        code, j, job = self.corpus_build(coll["id"])
        self.assertEqual(code, 202)
        self.assertEqual(j["documents"], 2)
        self.assertTrue(j["queued"])
        self.assertEqual(job["status"], "succeeded", job)

        builds = self.corpus_builds(coll["id"])
        self.assertEqual(len(builds), 1)
        b = builds[0]
        self.assertEqual(b["status"], "succeeded")
        self.assertEqual(b["es_index_status"], "blocked")
        self.assertEqual(b["es_index"], "none")
        self.assertTrue(re.fullmatch(r"[0-9a-f]{64}", b["content_sha256"]))
        self.assertEqual(b["chunk_count"], blocks_total)
        iv_id = b["iv_id"]
        self.assertTrue(iv_id.startswith("iv-"))

        # on-disk: one validated d-1 dump per document + the c-1 corpus
        root, dumps, corpus_dir = _corpus_build_paths(coll["id"], cid)
        self.assertTrue(os.path.isdir(corpus_dir))
        expected_files = [
            "raw.jsonl", "normalized.jsonl",
            "raw.unique.jsonl", "normalized.unique.jsonl",
            "corpus-data.zip", "corpus-manifest.json",
        ]
        for name in expected_files:
            self.assertTrue(
                os.path.isfile(os.path.join(corpus_dir, name)), name)
        dump_count = 0
        for d in rows:
            dd = os.path.join(dumps, d["file_id"])
            self.assertTrue(os.path.isdir(dd), dd)
            ok, errors, _ = validate_dump(dd)
            self.assertTrue(ok, errors)
            dump_count += 1
        self.assertEqual(dump_count, 2)

        # normalized stream = exactly the sum of the real blocks counts
        with open(os.path.join(corpus_dir, "normalized.jsonl"),
                  encoding="utf-8") as fh:
            nlines = sum(1 for l in fh if l.strip())
        self.assertEqual(nlines, blocks_total)

        # manifest is self-consistent: archive sha == content_sha256
        with open(os.path.join(corpus_dir, "corpus-manifest.json"),
                  encoding="utf-8") as fh:
            man = json.load(fh)
        self.assertEqual(man["archive"]["sha256"], b["content_sha256"])
        self.assertEqual(man["counts"]["blocks_total"], blocks_total)
        self.assertEqual(man["counts"]["dumps"], 2)
        self.assertEqual(man["corpus_contract_version"], "c-1")
        # the archive sha matches the real zip on disk
        h = hashlib.sha256()
        with open(os.path.join(corpus_dir, "corpus-data.zip"), "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        self.assertEqual(h.hexdigest(), man["archive"]["sha256"])

        # GET /index-builds/<iv_id> returns the row + the manifest
        r = self.client.get(f"/api/knowledge/index-builds/{iv_id}")
        self.assertEqual(r.status_code, 200, r.get_data(as_text=True))
        item = r.get_json()["build"]
        self.assertEqual(item["iv_id"], iv_id)
        self.assertEqual(item["manifest"]["archive"]["sha256"],
                         b["content_sha256"])

        # blocked detail is honest Persian
        detail = json.loads(b["es_detail"])
        self.assertEqual(detail["status"], "blocked")
        self.assertIn("PCT_ES_URL", detail["reason"])

        # collection detail exposes the new columns too
        det = self.client.get(
            f"/api/knowledge/collections/{coll['id']}"
        ).get_json()["collection"]
        self.assertEqual(len(det["index_builds"]), 1)
        self.assertEqual(det["index_builds"][0]["es_index_status"],
                         "blocked")


class TestPF_D02_CorpusBuildIdempotent(_StageDPrep):
    """PF-D02 — Stage D: content idempotency (REUSED) + new content.

    - rebuild with the SAME content -> job 'reused <iv_id>', still ONE
      build row (no rewrite);
    - add a 3rd book and rebuild -> NEW row, different content_sha256
      (archive is deterministic per content).
    """

    def test_reused_then_new_content(self):
        os.environ.pop("PCT_ES_URL", None)
        coll, rows = self._prep(2)
        _, _, job1 = self.corpus_build(coll["id"])
        self.assertEqual(job1["status"], "succeeded", job1)
        iv1 = self.corpus_builds(coll["id"])[0]["iv_id"]

        # same content again -> REUSED (job re-runs in place; the worker
        # short-circuits on the identical corpus archive sha), still 1 row
        _, j2, job2 = self.corpus_build(coll["id"])
        self.assertTrue(j2["queued"])
        self.assertEqual(job2["status"], "succeeded", job2)
        self.assertIn(iv1, job2.get("stage") or "", job2)
        self.assertEqual(len(self.corpus_builds(coll["id"])), 1)

        # a 3rd book changes the content -> a second, different row
        from factory._smoke_fixtures import make_docx
        tmp = tempfile.mkdtemp(prefix="pct-pf-d2-")
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        p = os.path.join(tmp, "کتاب-سوم.docx")
        make_docx(p, [
            ("Normal", "عنوان: کتاب سوم"),
            ("Heading 1", "فصل اول"),
            ("Normal", "متن فارسی کتاب سوم."),
        ])
        self.upload_and_process(p)
        _, _, job3 = self.corpus_build(coll["id"])
        self.assertEqual(job3["status"], "succeeded", job3)
        builds = self.corpus_builds(coll["id"])
        self.assertEqual(len(builds), 2)
        # two distinct content hashes, two distinct build rows
        shas = {b["content_sha256"] for b in builds}
        self.assertEqual(len(shas), 2)
        self.assertEqual(len({b["iv_id"] for b in builds}), 2)
        # newest first: the 3-doc build is on top, the 2-doc (iv1) row kept
        self.assertEqual(builds[1]["iv_id"], iv1)
        self.assertGreater(builds[0]["chunk_count"], builds[1]["chunk_count"])


class TestPF_D03_CorpusBuildErrors(_StageDPrep):
    """PF-D03 — Stage D: error paths.

    empty collection -> 409 no_processed_documents; uploaded-but-unprocessed
    document -> 409; unknown collection -> 404; unknown iv_id -> 404.
    """

    def test_error_paths(self):
        os.environ.pop("PCT_ES_URL", None)
        # empty collection
        coll = self.make_collection()
        r = self.client.post(
            f"/api/knowledge/collections/{coll['id']}/corpus/build")
        self.assertEqual(r.status_code, 409, r.get_data(as_text=True))
        self.assertEqual(r.get_json()["code"], "no_processed_documents")

        # uploaded but NOT processed -> still 409
        from factory._smoke_fixtures import make_docx
        tmp = tempfile.mkdtemp(prefix="pct-pf-d3-")
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        p = os.path.join(tmp, "کتاب-بدون-پردازش.docx")
        make_docx(p, [("Normal", "متن")])
        with open(p, "rb") as fh:
            raw = fh.read()
        r = self.client.post(
            f"/api/knowledge/collections/{coll['id']}/documents",
            data={"file": (io.BytesIO(raw), "کتاب-بدون-پردازش.docx")},
            content_type="multipart/form-data")
        self.assertEqual(r.status_code, 201, r.get_data(as_text=True))
        r = self.client.post(
            f"/api/knowledge/collections/{coll['id']}/corpus/build")
        self.assertEqual(r.status_code, 409, r.get_data(as_text=True))
        self.assertEqual(r.get_json()["code"], "no_processed_documents")

        # unknown collection -> 404
        r = self.client.post(
            "/api/knowledge/collections/999999/corpus/build")
        self.assertEqual(r.status_code, 404, r.get_data(as_text=True))
        r = self.client.get(
            "/api/knowledge/collections/999999/corpus/builds")
        self.assertEqual(r.status_code, 404, r.get_data(as_text=True))
        # unknown build -> 404
        r = self.client.get("/api/knowledge/index-builds/iv-00000000")
        self.assertEqual(r.status_code, 404, r.get_data(as_text=True))


class TestPF_D04_ESFactoryMocked(_StageDPrep):
    """PF-D04 — Stage D: the ES index factory, mocked at _es_request.

    With PCT_ES_URL set and an approved schema:
    - success: versioned index knowledge_<slug>_v0001, mapping built from
      the approved schema (es_field keys, index:false when not
      searchable), one ATOMIC /_aliases call, alias holder == the new
      index, docs == sum of blocks;
    - rebuild with same content -> REUSED, no v0002;
    - count mismatch -> job failed, es_index_status 'failed', NO alias
      switch (rollback: the alias never moved).
    """

    def setUp(self):
        super().setUp()
        os.environ["PCT_ES_URL"] = "http://es.fake:9200"
        self.addCleanup(lambda: os.environ.pop("PCT_ES_URL", None))

    def _approve_default_schema(self, cid):
        r = self.client.post(
            f"/api/knowledge/collections/{cid}/schema", json={})
        self.assertEqual(r.status_code, 201, r.get_data(as_text=True))
        sv = r.get_json()["schema"]
        r = self.client.post(
            f"/api/knowledge/collections/{cid}/schema/{sv['schema_id']}"
            "/validate")
        self.assertEqual(r.status_code, 200, r.get_data(as_text=True))
        r = self.client.post(
            f"/api/knowledge/collections/{cid}/schema/{sv['schema_id']}"
            "/approve")
        self.assertEqual(r.status_code, 200, r.get_data(as_text=True))

    class _FakeES:
        def __init__(self, count_override=None, bulk_errors=False):
            self.indices = {}       # name -> mapping props (PUT'd)
            self.bulk_docs = 0
            self.bulk_errors = bulk_errors
            self.count_override = count_override
            self.alias_holders = {}
            self.alias_calls = []   # each /_aliases actions list
            self.refreshes = 0

        def __call__(self, es_url, method, path, body=None, ndjson=False):
            # body arrives as a list of objects: alternating
            # {"index": {...}} action lines and payload dicts (the real
            # _es_request serializes; the seam is patched above it).
            if method == "PUT":  # PUT /<new_index> {mappings}
                name = path[1:]
                self.indices[name] = (body or {}).get("mappings", {}).get(
                    "properties", {})
                return {}
            if method == "POST" and path == "/_bulk":
                n = 0
                for line in body:
                    if isinstance(line, dict) and "index" in line:
                        n += 1
                self.bulk_docs += n
                if self.bulk_errors:
                    return {"errors": True, "items": [
                        {"index": {"error": {"type": "boom"}}}]}
                return {"errors": False}
            if method == "POST" and path.endswith("/_refresh"):
                self.refreshes += 1
                return {}
            if method == "GET" and path.endswith("/_count"):
                c = (self.count_override if self.count_override is not None
                     else self.bulk_docs)
                return {"count": c}
            if method == "GET":  # /<index>/_count handled above; /<alias>
                name = path[1:]
                if name in self.indices:
                    return {name: {}}
                return self.alias_holders.get(name, {})
            if method == "POST" and path == "/_aliases":
                self.alias_calls.append(body["actions"])
                for a in body["actions"]:
                    if "remove" in a:
                        nm = a["remove"]["index"]
                        al = a["remove"]["alias"]
                        if al in self.alias_holders:
                            del self.alias_holders[al]
                    if "add" in a:
                        self.alias_holders[a["add"]["alias"]] = \
                            a["add"]["index"]
                return {}
            raise AssertionError(f"unexpected ES call {method} {path}")

    def test_es_success_reuse_and_rollback(self):
        import unittest.mock
        import knowledge_api
        coll, rows = self._prep(2)
        cid = coll["collection_id"]
        blocks_total = sum(r["blocks_count"] for r in rows)
        self._approve_default_schema(cid)

        fake = self._FakeES()
        with unittest.mock.patch.object(
                knowledge_api, "_es_request", side_effect=fake):
            _, _, job = self.corpus_build(coll["id"])
        self.assertEqual(job["status"], "succeeded", job)
        builds = self.corpus_builds(coll["id"])
        self.assertEqual(len(builds), 1)
        b = builds[0]
        self.assertEqual(b["status"], "succeeded")
        self.assertEqual(b["es_index_status"], "success")
        self.assertEqual(b["es_index"],
                         f"knowledge_{coll['slug']}_v0001")
        self.assertEqual(b["chunk_count"], blocks_total)
        # mapping came from the approved schema
        props = fake.indices[b["es_index"]]
        self.assertEqual(props["normalized_text"], {"type": "text"})
        self.assertEqual(props["block_id"], {"type": "keyword"})
        self.assertEqual(props["type"], {"type": "keyword"})
        self.assertEqual(props["norm_version"],
                         {"type": "keyword", "index": False})
        # one ATOMIC alias call; alias now holds exactly the new index
        self.assertEqual(len(fake.alias_calls), 1)
        self.assertEqual(fake.alias_holders.get(coll["es_alias"]),
                         b["es_index"])
        self.assertEqual(fake.bulk_docs, blocks_total)
        self.assertGreaterEqual(fake.refreshes, 1)
        # collection flagged ready with this build
        det = self.client.get(
            f"/api/knowledge/collections/{coll['id']}"
        ).get_json()["collection"]
        self.assertEqual(det["indexing_status"], "ready")
        self.assertEqual(det["current_index_build"], b["iv_id"])
        # detail carries the ES info
        detail = json.loads(b["es_detail"])
        self.assertEqual(detail["docs"], blocks_total)
        self.assertEqual(detail["alias"], coll["es_alias"])

        # same content again -> REUSED: no v0002, no second alias switch
        with unittest.mock.patch.object(
                knowledge_api, "_es_request", side_effect=fake):
            _, _, job2 = self.corpus_build(coll["id"])
        self.assertEqual(job2["status"], "succeeded", job2)
        self.assertEqual(len(self.corpus_builds(coll["id"])), 1)
        self.assertEqual(len(fake.indices), 1)
        self.assertEqual(len(fake.alias_calls), 1)

        # --- rollback: count mismatch -> job failed, alias NOT touched ---
        from factory._smoke_fixtures import make_docx
        tmp = tempfile.mkdtemp(prefix="pct-pf-d4-")
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        p = os.path.join(tmp, "کتاب-چهارم.docx")
        make_docx(p, [
            ("Normal", "عنوان: کتاب چهارم"),
            ("Normal", "متن فارسی کتاب چهارم."),
        ])
        self.upload_and_process(p)
        fake2 = self._FakeES(count_override=-1)
        with unittest.mock.patch.object(
                knowledge_api, "_es_request", side_effect=fake2):
            _, _, job3 = self.corpus_build(coll["id"])
        self.assertEqual(job3["status"], "failed", job3)
        builds = self.corpus_builds(coll["id"])
        self.assertEqual(len(builds), 2)
        b3 = builds[0]  # newest = the failed ES attempt
        self.assertEqual(b3["es_index_status"], "failed")
        self.assertIn("count mismatch", json.loads(b3["es_detail"])["error"])
        # the alias never moved (rollback); es_index never assigned
        self.assertEqual(fake2.alias_calls, [])
        self.assertEqual(b3["es_index"], "none")
        # retrying the SAME job kind re-runs the ES part on the same row
        with unittest.mock.patch.object(
                knowledge_api, "_es_request", side_effect=self._FakeES()):
            _, _, job4 = self.corpus_build(coll["id"])
        self.assertEqual(job4["status"], "succeeded", job4)
        builds = self.corpus_builds(coll["id"])
        # still 2 rows total (failed->retried row updated in place)
        self.assertEqual(len(builds), 2)
        top = builds[0]
        self.assertEqual(top["es_index_status"], "success")
        self.assertRegex(top["es_index"],
                         r"^knowledge_" + coll["slug"] + r"_v\d{4}$")


# ---------------------------------------------------------------------------
# PCM-20.9 Stage E — search acceptance + approval (PF-Exx)
# ---------------------------------------------------------------------------

class _FakeSearchES:
    """A minimal in-memory cluster for acceptance runs.

    Docs are recorded per PHYSICAL index by the bulk hook
    (`_make_fake_bulk`), and the /_aliases call maintains
    alias -> index, so the acceptance sees exactly the docs that were
    switched in under the alias. The search endpoint answers the
    acceptance's real requests with a faithful mini-matcher:
      - match_phrase  normalized_text : exact substring in the text
      - match         normalized_text : exact word in the text (the
                                        Persian analyzer's token set)
      - term          keywords.work_id: exact keyword equality
      - term          metadata.<key>  : exact value equality
      - bool.filter term type=heading : exact field equality
      - match_all: everything
    Pagination: sort by _id asc (only when a sort is given), then
    from/size — mirroring real ES stable paging.
    """

    def __init__(self):
        self.indices = {}          # name -> mapping props
        self.alias_to_index = {}   # alias -> physical index
        self.bulk_docs = {}        # physical index -> [(doc_id, source)]
        self.search_calls = []     # (path, body)

    def __call__(self, es_url, method, path, body=None, ndjson=False):
        if method == "PUT":  # PUT /<new_index> {mappings}
            self.indices[path[1:]] = (body or {}).get(
                "mappings", {}).get("properties", {})
            return {}
        if method == "POST" and path == "/_bulk":
            # (never reached in tests: the bulk hook wraps us)
            return {"errors": False}
        if method == "POST" and path.endswith("/_refresh"):
            return {}
        if method == "GET" and path.endswith("/_count"):
            name = path[1:-len("/_count")]
            return {"count": len(self._docs_for(name))}
        if method == "GET" and path == "/_aliases":
            return {}
        if method == "POST" and path == "/_aliases":
            for a in body["actions"]:
                al = a.get("add", {}).get("alias")
                if "remove" in a:
                    al = a["remove"]["alias"]
                    self.alias_to_index.pop(al, None)
                if "add" in a:
                    self.alias_to_index[a["add"]["alias"]] = \
                        a["add"]["index"]
            return {}
        if method == "GET" and "/" not in path[1:]:
            # GET /<name> — alias holder listing
            name = path[1:]
            if name in self.indices:
                return {name: {}}
            if name in self.alias_to_index:
                return {self.alias_to_index[name]: {}}
            return {}
        if method == "POST" and path.endswith("/_search"):
            self.search_calls.append((path, body))
            alias = path[1:-len("/_search")]
            docs = self._docs_for(alias)
            hits = [(d, s) for d, s in docs if self._match(body, s)]
            if (body or {}).get("sort"):
                hits = sorted(hits, key=lambda h: h[0])
            size = body.get("size", 10)
            frm = body.get("from", 0)
            page = hits[frm:frm + size]
            return {"hits": {
                "total": {"value": len(hits), "relation": "eq"},
                "hits": [{"_id": d, "_source": s} for d, s in page],
            }}
        raise AssertionError(f"unexpected ES call {method} {path}")

    # -- internals -------------------------------------------------------
    def _docs_for(self, name):
        """Docs for a physical index name OR an alias (the build counts
        the physical index before the alias exists; the acceptance
        searches the live alias)."""
        if name in self.bulk_docs:
            return sorted(self.bulk_docs[name])
        idx = self.alias_to_index.get(name)
        if idx is None:
            return []
        return sorted(self.bulk_docs.get(idx, []))

    def _match(self, body, src):
        query = (body or {}).get("query") or {}
        if "match_all" in query:
            return True
        if "bool" in query:
            for f in (query["bool"].get("filter") or []):
                for field, spec in f.items():
                    if field == "term":
                        k, v = next(iter(spec.items()))
                        if src.get(k) != v:
                            return False
            return True
        if "match_phrase" in query:
            (k, v), = query["match_phrase"].items()
            return v in (src.get(k) or "")
        if "match" in query:
            (k, v), = query["match"].items()
            return (str(v) in str(src.get(k) or "").split())
        if "term" in query:
            (k, v), = query["term"].items()
            if k == "keywords.work_id":
                return (src.get("keywords") or {}).get("work_id") == v
            if k.startswith("metadata."):
                # real ES: dynamic strings are text + .keyword subfield;
                # the query targets the .keyword side
                fk = k.split(".", 1)[1]
                if fk.endswith(".keyword"):
                    fk = fk[:-len(".keyword")]
                return (src.get("metadata") or {}).get(fk) == v
        return False


def _make_fake_bulk(es):
    """Wrap the fake so /_bulk records docs per physical index
    (the seam sits above the fake's own bulk handling)."""
    orig = es.__call__

    def wrapped(es_url, method, path, body=None, ndjson=False):
        if method == "POST" and path == "/_bulk":
            per_index = {}
            for i in range(0, len(body), 2):
                act = body[i].get("index", {})
                per_index.setdefault(act.get("_index"), []).append(
                    (act.get("_id"), body[i + 1]))
            for idx, docs in per_index.items():
                es.bulk_docs.setdefault(idx, []).extend(docs)
            return {"errors": False}
        return orig(es_url, method, path, body=body, ndjson=ndjson)
    return wrapped


class TestPF_E01_SearchAcceptanceMocked(_StageDPrep):
    """PF-E01 — Stage E: the 10-category acceptance, mocked at
    _es_request (real build + real corpus; ES simulated).

    - the build switches the alias to the new index (Stage D);
    - the acceptance then runs 10 REAL categories against the LIVE
      alias: count, exact phrase, partial word, heading filter,
      work_id keyword filter, custom metadata filter, pagination,
      determinism, absence, latency;
    - every category passes with real evidence;
    - search_status='pass' on the build row;
    - collection validation_status='accepted';
    - the approve endpoint then returns ok (the gate is open) and
      current_index_build points at the build.
    """

    def setUp(self):
        super().setUp()
        os.environ["PCT_ES_URL"] = "http://es.fake:9200"
        self.addCleanup(lambda: os.environ.pop("PCT_ES_URL", None))

    def _approve_default_schema(self, cid):
        r = self.client.post(
            f"/api/knowledge/collections/{cid}/schema", json={})
        self.assertEqual(r.status_code, 201, r.get_data(as_text=True))
        sv = r.get_json()["schema"]
        r = self.client.post(
            f"/api/knowledge/collections/{cid}/schema/{sv['schema_id']}"
            "/validate")
        self.assertEqual(r.status_code, 200, r.get_data(as_text=True))
        r = self.client.post(
            f"/api/knowledge/collections/{cid}/schema/{sv['schema_id']}"
            "/approve")
        self.assertEqual(r.status_code, 200, r.get_data(as_text=True))

    def _collection_meta_value(self, cid, key, value):
        r = self.client.post("/api/knowledge/metadata/fields", json={
            "scope": "collection", "collection_id": cid,
            "field_key": key, "display_name": "دسته آزمایشی",
            "data_type": "string"})
        self.assertEqual(r.status_code, 201, r.get_data(as_text=True))
        r = self.client.post("/api/knowledge/metadata/values", json={
            "field_key": key, "value": value, "scope": "collection",
            "collection_id": cid})
        self.assertEqual(r.status_code, 200, r.get_data(as_text=True))

    def test_acceptance_pass_and_approve(self):
        import unittest.mock
        import knowledge_api
        coll, rows = self._prep(2)
        cid = coll["collection_id"]
        blocks_total = sum(r["blocks_count"] for r in rows)
        self._approve_default_schema(cid)
        # a collection-scope metadata value (exercises category 06)
        self._collection_meta_value(cid, "category", "آزمایشی")
        # capture the work_id of the first document (category 05)
        docs = self.client.get(
            f"/api/knowledge/collections/{coll['id']}/documents"
        ).get_json()["documents"]
        work_id = docs[0]["work_id"]
        self.assertTrue(work_id)

        fake = _FakeSearchES()
        with unittest.mock.patch.object(
                knowledge_api, "_es_request",
                side_effect=_make_fake_bulk(fake)):
            _, _, job = self.corpus_build(coll["id"])
        self.assertEqual(job["status"], "succeeded", job)
        builds = self.corpus_builds(coll["id"])
        b = builds[0]
        self.assertEqual(b["es_index_status"], "success")
        alias = coll["es_alias"]
        self.assertEqual(fake.alias_to_index.get(alias), b["es_index"])

        # --- run the acceptance against the same fake cluster (it holds
        # the bulk docs; the alias was switched in by the Stage D build).
        # wait_job stays INSIDE the patch: the worker runs in a thread
        # and must observe the mocked seam while it works.
        fake.search_calls.clear()
        with unittest.mock.patch.object(
                knowledge_api, "_es_request", side_effect=fake):
            r = self.client.post(
                f"/api/knowledge/collections/{coll['id']}"
                "/search-acceptance")
            self.assertIn(r.status_code, (200, 202),
                          r.get_data(as_text=True))
            job = self.wait_job(r.get_json()["job"]["job_id"])
        self.assertEqual(job["status"], "succeeded", job)

        builds = self.corpus_builds(coll["id"])
        b = builds[0]
        self.assertEqual(b["search_status"], "pass")
        report = json.loads(b["search_detail"])
        self.assertEqual(report["overall"], "pass")
        self.assertEqual(report["failed"], [])
        self.assertEqual(report["alias"], alias)
        self.assertEqual(report["index"], b["es_index"])
        self.assertEqual(report["expected_count"], blocks_total)
        self.assertEqual(set(report["categories"]), set([
            "count", "exact_block", "partial_text", "heading_filter",
            "work_filter", "metadata_filter", "pagination",
            "determinism", "absence", "latency"]))
        for code, c in report["categories"].items():
            self.assertEqual(c["status"], "pass",
                             f"{code}: {c['detail']}")
        # the acceptance only ever READ from the alias (search/count),
        # never moved it
        self.assertEqual(fake.alias_to_index.get(alias), b["es_index"])

        # collection flags
        det = self.client.get(
            f"/api/knowledge/collections/{coll['id']}"
        ).get_json()["collection"]
        self.assertEqual(det["validation_status"], "accepted")

        # the approve gate is open now
        r = self.client.post(
            f"/api/knowledge/index-builds/{b['iv_id']}/approve")
        self.assertEqual(r.status_code, 200, r.get_data(as_text=True))
        j = r.get_json()
        self.assertTrue(j["ok"])
        self.assertEqual(j["validation_status"], "accepted")
        det = self.client.get(
            f"/api/knowledge/collections/{coll['id']}"
        ).get_json()["collection"]
        self.assertEqual(det["current_index_build"], b["iv_id"])


class TestPF_E02_SearchAcceptanceGuarded(_StageDPrep):
    """PF-E02 — Stage E guards: honest BLOCKED, no fabricated results.

    - no PCT_ES_URL and no Stage D build -> 409 no_corpus_build;
    - ES configured, Stage D build done (ES success via the fake),
      but a failing acceptance (forced count mismatch) ->
      search_status='fail', validation_status='needs_review', and the
      approve endpoint refuses with 409 acceptance_not_passed.
    """

    def setUp(self):
        super().setUp()
        os.environ["PCT_ES_URL"] = "http://es.fake:9200"
        self.addCleanup(lambda: os.environ.pop("PCT_ES_URL", None))

    def test_guards_and_failed_acceptance(self):
        import unittest.mock
        import knowledge_api
        from factory._smoke_fixtures import make_docx
        coll = self.make_collection()
        tmp = tempfile.mkdtemp(prefix="pct-pf-e2-")
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        p = os.path.join(tmp, "کتاب-ع2.docx")
        make_docx(p, [
            ("Normal", "عنوان: کتاب تست"),
            ("Heading 1", "فصل اول"),
            ("Normal", "متن فارسی تستی."),
        ])
        self.upload_and_process(p)

        # guard 1: no Stage D build at all -> 409
        r = self.client.post(
            f"/api/knowledge/collections/{coll['id']}/search-acceptance")
        self.assertEqual(r.status_code, 409, r.get_data(as_text=True))
        self.assertEqual(r.get_json()["code"], "no_corpus_build")

        # build Stage D against a fake cluster (alias switches in)
        fake = _FakeSearchES()
        with unittest.mock.patch.object(
                knowledge_api, "_es_request",
                side_effect=_make_fake_bulk(fake)):
            code, j, job = self.corpus_build(coll["id"])
        self.assertEqual(job["status"], "succeeded", job)

        # now force a FAILED acceptance: the fake's count is wrong
        # (simulates a stale/unflushed index) -> categories fail,
        # overall 'fail', needs_review, approve refused.
        real_count = fake.__call__

        def broken(es_url, method, path, body=None, ndjson=False):
            if method == "GET" and path.endswith("/_count"):
                return {"count": 999999}
            return real_count(es_url, method, path, body=body,
                              ndjson=ndjson)

        with unittest.mock.patch.object(
                knowledge_api, "_es_request", side_effect=broken):
            r = self.client.post(
                f"/api/knowledge/collections/{coll['id']}"
                "/search-acceptance")
            self.assertIn(r.status_code, (200, 202),
                          r.get_data(as_text=True))
            job = self.wait_job(r.get_json()["job"]["job_id"])
        self.assertEqual(job["status"], "succeeded", job)
        b = self.corpus_builds(coll["id"])[0]
        self.assertEqual(b["search_status"], "fail")
        report = json.loads(b["search_detail"])
        self.assertEqual(report["overall"], "fail")
        self.assertIn("count", report["failed"])
        det = self.client.get(
            f"/api/knowledge/collections/{coll['id']}"
        ).get_json()["collection"]
        self.assertEqual(det["validation_status"], "needs_review")
        # the approve gate must stay shut
        r = self.client.post(
            f"/api/knowledge/index-builds/{b['iv_id']}/approve")
        self.assertEqual(r.status_code, 409, r.get_data(as_text=True))
        self.assertEqual(r.get_json()["code"], "acceptance_not_passed")
        # and the alias never moved (acceptance is read-only)
        self.assertEqual(fake.alias_to_index.get(coll["es_alias"]),
                         b["es_index"])

        # unknown iv_id approve -> 404
        r = self.client.post("/api/knowledge/index-builds/iv-nosuch/approve")
        self.assertEqual(r.status_code, 404)


class TestPF_E03_SearchAcceptanceBlockedNoES(_StageDPrep):
    """PF-E03 — Stage E with NO PCT_ES_URL at all: the job runs,
    records an honest BLOCKED on the build row (Persian reason),
    fails with a clear error, and the collection stays pending."""

    def test_blocked_without_es(self):
        import knowledge_api
        os.environ.pop("PCT_ES_URL", None)
        from factory._smoke_fixtures import make_docx
        coll = self.make_collection()
        tmp = tempfile.mkdtemp(prefix="pct-pf-e3-")
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        p = os.path.join(tmp, "کتاب-ع3.docx")
        make_docx(p, [
            ("Normal", "عنوان: کتاب بلاک"),
            ("Normal", "متن بلاک."),
        ])
        self.upload_and_process(p)
        # Stage D corpus-only (ES part blocked)
        code, j, job = self.corpus_build(coll["id"])
        self.assertEqual(job["status"], "succeeded", job)
        b = self.corpus_builds(coll["id"])[0]
        self.assertEqual(b["es_index_status"], "blocked")

        r = self.client.post(
            f"/api/knowledge/collections/{coll['id']}/search-acceptance")
        self.assertIn(r.status_code, (200, 202), r.get_data(as_text=True))
        job = self.wait_job(r.get_json()["job"]["job_id"])
        self.assertEqual(job["status"], "failed", job)
        self.assertIn("BLOCKED", job["error"])
        b = self.corpus_builds(coll["id"])[0]
        self.assertEqual(b["search_status"], "blocked")
        detail = json.loads(b["search_detail"])
        self.assertEqual(detail["status"], "blocked")
        self.assertIn("PCT_ES_URL", detail["reason"])
        det = self.client.get(
            f"/api/knowledge/collections/{coll['id']}"
        ).get_json()["collection"]
        self.assertEqual(det["validation_status"], "pending")


# ---------------------------------------------------------------------------
# PCM-20.9 Final — Stage F: release bundle + audit trail (PF-Fxx)
# ---------------------------------------------------------------------------

def _release_paths(cid):
    import knowledge_api
    return os.path.join(knowledge_api.knowledge_data_dir(), "releases")


class _StageFPrep(_StageDPrep):
    """Shared setup: 2 processed books + a REAL Stage D corpus build
    (ES blocked — no PCT_ES_URL), ready for the release stage."""

    def setUp(self):
        super().setUp()
        os.environ.pop("PCT_ES_URL", None)

    def _prep_with_corpus(self, n=2):
        coll, rows = self._prep(n)
        _, _j, job = self.corpus_build(coll["id"])
        self.assertEqual(job["status"], "succeeded", job)
        return coll, rows

    def start_release(self, coll_pk):
        r = self.client.post(
            f"/api/knowledge/collections/{coll_pk}/release")
        self.assertIn(r.status_code, (200, 202), r.get_data(as_text=True))
        j = r.get_json()
        self.assertTrue(j["ok"], j)
        job = self.wait_job(j["job"]["job_id"])
        return r, j, job

    def releases(self, coll_pk):
        r = self.client.get(
            f"/api/knowledge/collections/{coll_pk}/releases")
        self.assertEqual(r.status_code, 200, r.get_data(as_text=True))
        return r.get_json()["releases"]


class TestPF_F01_ReleaseBundleEndToEnd(_StageFPrep):
    """PF-F01 — Stage F end-to-end (the REAL bundle).

    2 books -> Stage D corpus -> POST /release:
    - the corpus archive sha is re-verified on disk;
    - the dumps layer = EXACTLY the corpus manifest's input_dumps, each
      re-validated (d-1 V1..V11) with every file hash recomputed;
    - a deterministic release zip (corpus + dumps + release-manifest +
      README) is written;
    - the release-manifest is a CHAINED hash: corpus archive sha,
      dumps-root sha, pre-zip chain, zip sha — all recomputable;
    - RAG is honestly BLOCKED (no PCT_RAG_INGEST_URL — nothing called);
    - the download endpoint re-hashes the zip and serves it;
    - the bundle unzips and every member matches the manifest.
    """

    def test_release_bundle(self):
        import zipfile
        coll, rows = self._prep_with_corpus(2)
        cid = coll["collection_id"]
        blocks_total = sum(r["blocks_count"] for r in rows)

        r, j, job = self.start_release(coll["id"])
        self.assertEqual(job["status"], "succeeded", job)
        self.assertEqual(j["documents"], 2)

        rels = self.releases(coll["id"])
        self.assertEqual(len(rels), 1)
        rel = rels[0]
        self.assertTrue(rel["release_id"].startswith("rel-"))
        self.assertEqual(rel["rag_status"], "blocked")
        b = self.corpus_builds(coll["id"])[0]
        self.assertEqual(rel["build_iv_id"], b["iv_id"])
        self.assertEqual(rel["content_sha256"], b["content_sha256"])

        # on disk: data zip + side-car manifest + readme
        rel_dir = os.path.join(_release_paths(cid), rel["release_id"])
        zip_path = rel["zip_path"]
        self.assertTrue(os.path.isfile(zip_path))
        self.assertEqual(self.sha256_file(zip_path), rel["zip_sha256"])
        self.assertEqual(os.path.getsize(zip_path), rel["size_bytes"])
        m_path = os.path.join(rel_dir, "release-manifest.json")
        self.assertTrue(os.path.isfile(m_path))
        self.assertTrue(os.path.isfile(os.path.join(rel_dir, "README.md")))

        # side-car manifest (NOT inside the zip — the container cannot
        # hash itself, exactly like corpus c-1)
        with open(m_path, encoding="utf-8") as fh:
            m = json.load(fh)
        self.assertEqual(m["release_contract"], "rel-1")
        self.assertEqual(m["release_id"], rel["release_id"])
        self.assertEqual(m["collection_id"], cid)
        self.assertEqual(m["data_zip"]["sha256"], rel["zip_sha256"])
        self.assertEqual(m["data_zip"]["size_bytes"], rel["size_bytes"])

        # the data zip itself (independent of the stored manifest)
        with zipfile.ZipFile(zip_path) as z:
            names = sorted(z.namelist())
            bad = z.testzip()
            self.assertIsNone(bad)
            self.assertTrue(any(n.startswith("corpus/") for n in names))
            self.assertTrue(any(n.startswith("dumps/") for n in names))
            self.assertNotIn("release-manifest.json", names)
            self.assertNotIn("README.md", names)
            # every member's hash must match the manifest
            for name, ent in m["corpus"]["files"].items():
                self.assertEqual(self.sha256_file_from_bytes(
                    z.read("corpus/" + name)), ent["sha256"], name)
            for de in m["dumps"]["entries"]:
                for fe in de["files"]:
                    self.assertEqual(
                        self.sha256_file_from_bytes(
                            z.read(f"dumps/{de['file_id']}/{fe['name']}")),
                        fe["sha256"], de["file_id"] + "/" + fe["name"])
            # corpus archive inside the zip matches the recorded sha,
            # and IS the Stage D content itself
            self.assertEqual(self.sha256_file_from_bytes(
                z.read("corpus/corpus-data.zip")),
                m["corpus"]["archive"]["sha256"])
            self.assertEqual(m["corpus"]["archive"]["sha256"],
                             b["content_sha256"])
            self.assertEqual(m["corpus"]["blocks_total"], blocks_total)
            self.assertEqual(m["dumps"]["count"], 2)

        # chained hashes: corpus archive -> dumps root -> data zip
        ch = m["chained"]
        self.assertEqual(ch["corpus_archive_sha256"],
                         rel["content_sha256"])
        expect_root = hashlib.sha256(
            "|".join(sorted(e["dump_manifest_sha256"]
                            for e in m["dumps"]["entries"])).encode()
        ).hexdigest()
        self.assertEqual(ch["dumps_root_sha256"], expect_root)
        self.assertEqual(ch["data_zip_sha256"], rel["zip_sha256"])

        # download: re-hashed and served
        d = self.client.get(f"/api/knowledge/releases/{rel['release_id']}"
                            "/download")
        self.assertEqual(d.status_code, 200)
        body = d.data
        self.assertEqual(self.sha256_file_from_bytes(body),
                         rel["zip_sha256"])
        self.assertEqual(len(body), rel["size_bytes"])

    @staticmethod
    def sha256_file_from_bytes(data):
        return hashlib.sha256(data).hexdigest()


class TestPF_F02_ReleaseIdempotent(_StageFPrep):
    """PF-F02 — same corpus content -> SAME release_id, zip reused
    (no rewrite), exactly ONE release row."""

    def test_release_idempotent(self):
        coll, rows = self._prep_with_corpus(2)
        _r, _j, job = self.start_release(coll["id"])
        self.assertEqual(job["status"], "succeeded", job)
        rels = self.releases(coll["id"])
        self.assertEqual(len(rels), 1)
        rel1 = rels[0]

        # second release for the SAME content: new job run, but the bundle
        # is reused (row count stays 1, same id, same zip hash)
        _r, _j, job2 = self.start_release(coll["id"])
        self.assertEqual(job2["status"], "succeeded", job2)
        rels2 = self.releases(coll["id"])
        self.assertEqual(len(rels2), 1)
        self.assertEqual(rels2[0]["release_id"], rel1["release_id"])
        self.assertEqual(rels2[0]["zip_sha256"], rel1["zip_sha256"])


class TestPF_F03_ReleaseNoBuild(_StageFPrep):
    """PF-F03 — release requires a Stage D corpus build: no build yet ->
    409 no_corpus_build (honest, no fabricated bundle)."""

    def test_release_blocked_without_corpus_build(self):
        coll, rows = self._prep(2)
        r = self.client.post(f"/api/knowledge/collections/{coll['id']}"
                             "/release")
        self.assertEqual(r.status_code, 409)
        j = r.get_json()
        self.assertFalse(j["ok"])
        self.assertEqual(j["code"], "no_corpus_build")
        self.assertEqual(self.releases(coll["id"]), [])


class TestPF_F04_ReleaseStaleCorpus(_StageFPrep):
    """PF-F04 — the corpus must match the CURRENT documents: a new upload
    after the corpus build -> the release FAILS (stale corpus), forcing a
    Stage D rebuild before a trustworthy release."""

    def test_release_stale_corpus_fails(self):
        coll, rows = self._prep_with_corpus(2)
        # a brand-new document the corpus was NOT built from
        from factory._smoke_fixtures import make_docx
        tmp = tempfile.mkdtemp(prefix="pct-pf-f4-")
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        p = os.path.join(tmp, "کتاب-جدید.docx")
        make_docx(p, [("Normal", "متن کتاب جدید برای تست stale.")])
        self.upload_and_process(p)

        _r, _j, job = self.start_release(coll["id"])
        self.assertEqual(job["status"], "failed", job)
        self.assertIn("stale", (job["error"] or "").lower())
        self.assertEqual(self.releases(coll["id"]), [])


class TestPF_F05_ReleaseTamperDetection(_StageFPrep):
    """PF-F05 — the download endpoint re-hashes the zip on disk: a
    tampered bundle is REFUSED (409 hash_mismatch) and the tamper is
    recorded in the audit trail."""

    def test_download_refuses_tampered_zip(self):
        coll, rows = self._prep_with_corpus(2)
        _r, _j, _job = self.start_release(coll["id"])
        rel = self.releases(coll["id"])[0]
        # tamper with the zip on disk
        with open(rel["zip_path"], "ab") as fh:
            fh.write(b"tamper")
        d = self.client.get(f"/api/knowledge/releases/{rel['release_id']}"
                            "/download")
        self.assertEqual(d.status_code, 409)
        j = d.get_json()
        self.assertFalse(j["ok"])
        self.assertEqual(j["code"], "hash_mismatch")
        # audit trail records the refusal
        a = self.client.get(
            f"/api/knowledge/collections/{coll['id']}/audit").get_json()
        actions = [e["action"] for e in a["entries"]]
        self.assertIn("download_hash_mismatch", actions)


class TestPF_F06_ReleaseRagGuarded(_StageFPrep):
    """PF-F06 — RAG is config-guarded (unknown RAG contract):
    - with a fake PCT_RAG_INGEST_URL the release SUCCEEDS and the ingest
      is attempted (here refused by the fake server -> rag_status='failed'
      with the recorded error — the bundle is still produced);
    - the ingest payload carries the real hashes (verifiable provenance).
    """

    def test_release_rag_attempted_when_configured(self):
        import http.server
        import threading
        captured = {}

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length)
                captured["payload"] = json.loads(body.decode("utf-8"))
                captured["auth"] = self.headers.get("Authorization", "")
                self.send_response(503)
                self.end_headers()
                self.wfile.write(b"rag down")

            def log_message(self, *a):
                pass

        srv = http.server.HTTPServer(("127.0.0.1", 0), Handler)
        port = srv.server_address[1]
        t = threading.Thread(target=srv.serve_forever, daemon=True)
        t.start()
        self.addCleanup(srv.shutdown)
        os.environ["PCT_RAG_INGEST_URL"] = f"http://127.0.0.1:{port}/ingest"
        os.environ["PCT_RAG_INGEST_TOKEN"] = "rag-test-token"
        self.addCleanup(lambda: os.environ.pop("PCT_RAG_INGEST_URL", None))
        self.addCleanup(lambda: os.environ.pop("PCT_RAG_INGEST_TOKEN", None))

        coll, rows = self._prep_with_corpus(2)
        _r, _j, job = self.start_release(coll["id"])
        self.assertEqual(job["status"], "succeeded", job)  # bundle is fine
        rel = self.releases(coll["id"])[0]
        self.assertEqual(rel["rag_status"], "failed")
        # the payload carried the real, verifiable provenance
        pl = captured["payload"]
        self.assertEqual(pl["kind"], "pct-release")
        self.assertEqual(pl["contract"], "rel-1")
        self.assertEqual(pl["release_id"], rel["release_id"])
        self.assertEqual(pl["zip_sha256"], rel["zip_sha256"])
        self.assertEqual(pl["collection_id"], coll["collection_id"])
        self.assertEqual(captured["auth"], "Bearer rag-test-token")


class TestPF_F07_AuditTrail(_StageFPrep):
    """PF-F07 — the append-only audit trail: every pipeline/acceptance/
    release action lands in knowledge_audit_log with a real actor
    (sess-<sha8> for request actions, 'worker' for job actions)."""

    def test_audit_trail_records_actions(self):
        coll, rows = self._prep_with_corpus(2)
        _r, _j, _job = self.start_release(coll["id"])

        a = self.client.get(
            f"/api/knowledge/collections/{coll['id']}/audit").get_json()
        self.assertTrue(a["ok"])
        self.assertGreater(a["count"], 0)
        actions = {e["action"] for e in a["entries"]}
        # corpus build (worker) + release (worker) are recorded
        self.assertIn("corpus_built", actions)
        self.assertIn("release_built", actions)
        actors = {e["actor"] for e in a["entries"]}
        self.assertIn("worker", actors)
        for e in a["entries"]:
            self.assertIn(e["status"], ("ok", "fail", "blocked"))
            self.assertTrue(e["ts"])

        # the same collection only — another collection's audit is clean
        other = self.make_collection(name="دیگر", slug="pipeline-other")
        a2 = self.client.get(
            f"/api/knowledge/collections/{other['id']}/audit").get_json()
        self.assertEqual(a2["count"], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)

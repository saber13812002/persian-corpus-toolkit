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
import os
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
        return r.get_json()["collection"]

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


if __name__ == "__main__":
    unittest.main(verbosity=2)

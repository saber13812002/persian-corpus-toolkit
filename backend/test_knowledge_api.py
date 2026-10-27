"""PCM-14A/B — Corpus Knowledge Studio (collections + Word Library) tests.

PCM-14A (collections):
  KS-01 create Persian collection
  KS-02 valid slug / collection_id / alias (deterministic)
  KS-03 duplicate + invalid slug/name rejection
  KS-04 list/detail after creation
  KS-05 search, subject filter, pagination
  Plus: PATCH rename (id/slug/alias stable), auth (401), subjects,
  index-builds endpoint, studio page serving, slug prefill helper.

PCM-14B (Word Library + Metadata + Jobs):
  KB-01 DOCX upload → stored under data/knowledge/files/<sha12>/ + registry row
  KB-02 duplicate upload (same SHA-256) → 409
  KB-03 invalid uploads: wrong extension / empty file / over size cap
  KB-04 .docx that is really OLE2 → process → failed (real factory pipeline)
  KB-05 process valid book → parsed + counts + deterministic factory ids
  KB-06 idempotent reprocess (same job_key → resubmitted, no 2nd worker)
  KB-07 structure / quality / blocks / raw-vs-normalized endpoints
  KB-08 approve parsed/needs_review; reject non-parseable states
  KB-09 detach: registry row removed, stored file kept
  KB-10 import batch plan (pending/duplicate/invalid) + summary
  KB-11 metadata fields (create/list/validate/dup/soft-disable) +
        values (set/get/version bump/invalid value)
  KB-12 jobs endpoint + stuck-recovery (old pending → interrupted)
  KB-13 ES compatibility endpoint → NOT VERIFIED

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
import unittest.mock

import pct_test_support  # noqa: F401  (must precede `import server`)

import server

PW = "test-secret-123"
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class Base(unittest.TestCase):
    def setUp(self):
        pct_test_support.reset_db()
        # Isolated file store per test (never the repo ./data on CI machines):
        # knowledge_data_dir() reads PCT_KNOWLEDGE_DATA_DIR on every call.
        self._datadir = tempfile.mkdtemp(prefix="pct-knowledge-")
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

    def make_collection(self, name="کتاب اول", slug="book-one", **kw):
        r = self.client.post(
            "/api/knowledge/collections",
            json={"name": name, "slug": slug, **kw},
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
        """Poll the job until terminal; return its final row."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            j = self.client.get(f"/api/knowledge/jobs").get_json()
            row = next((x for x in j["jobs"] if x["job_id"] == job_id), None)
            if row and row["status"] in ("succeeded", "failed", "interrupted"):
                return row
            time.sleep(0.2)
        self.fail(f"job {job_id} did not finish within {timeout}s")


# ────────────────────────────────────────────────────────────────────────────
# PCM-14A — collections (unchanged contract)
# ────────────────────────────────────────────────────────────────────────────

class CollectionCreateTests(Base):
    """KS-01 / KS-02 / KS-03"""

    def test_ks01_create_persian_collection(self):
        self.login()
        r = self.client.post(
            "/api/knowledge/collections",
            json={
                "name": "کتابخانه علوم عقلی",
                "slug": "oloom-aqli",
                "description": "منابع علوم عقلی",
                "subject": "فلسفه",
            },
        )
        self.assertEqual(r.status_code, 201, r.get_data(as_text=True))
        j = r.get_json()
        self.assertTrue(j["ok"])
        c = j["collection"]
        self.assertEqual(c["name"], "کتابخانه علوم عقلی")
        self.assertEqual(c["slug"], "oloom-aqli")
        # c-51911bd0 == 'c-' + sha256(b'oloom-aqli')[:8]
        self.assertEqual(c["collection_id"], "c-51911bd0")
        self.assertEqual(c["es_alias"], "pct-col-oloom-aqli")
        self.assertEqual(c["book_count"], 0)
        self.assertEqual(c["chunk_count"], 0)
        self.assertEqual(c["indexing_status"], "none")
        self.assertEqual(c["validation_status"], "pending")
        self.assertEqual(c["collection_version"], 1)
        self.assertEqual(c["schema_version"], "s-1")
        self.assertEqual(c["normalization_version"], "n-1")
        self.assertEqual(c["chunking_version"], "c-1")

    def test_ks02_deterministic_ids_and_alias(self):
        self.login()
        r = self.client.post(
            "/api/knowledge/collections",
            json={"name": "تفاسیر قرآن", "slug": "tafasir-quran"},
        )
        self.assertEqual(r.status_code, 201)
        c = r.get_json()["collection"]
        expected_id = "c-" + hashlib.sha256(b"tafasir-quran").hexdigest()[:8]
        self.assertEqual(c["collection_id"], expected_id)
        self.assertTrue(SLUG_RE.match(c["slug"]))
        self.assertTrue(c["es_alias"].startswith("pct-col-"))
        self.assertEqual(len(c["es_alias"]), len("pct-col-") + len(c["slug"]))

    def test_ks03_duplicate_slug_rejected(self):
        self.login()
        self.client.post(
            "/api/knowledge/collections",
            json={"name": "اول", "slug": "dup-slug"},
        )
        r = self.client.post(
            "/api/knowledge/collections",
            json={"name": "دوم", "slug": "dup-slug"},
        )
        self.assertEqual(r.status_code, 409)
        self.assertFalse(r.get_json()["ok"])

    def test_ks03_invalid_slug(self):
        self.login()
        for bad in ("has space", "fa-کتاب", "a", "-lead", "trail-", "a" * 65):
            r = self.client.post(
                "/api/knowledge/collections",
                json={"name": "نام", "slug": bad},
            )
            self.assertEqual(
                r.status_code, 400, f"slug {bad!r} should be rejected"
            )
            self.assertEqual(r.get_json().get("field"), "slug")

    def test_ks03_uppercase_normalized_then_collides(self):
        self.login()
        r = self.client.post(
            "/api/knowledge/collections",
            json={"name": "بزرگ", "slug": "OloomAqli"},
        )
        self.assertEqual(r.status_code, 201, r.get_data(as_text=True))
        self.assertEqual(r.get_json()["collection"]["slug"], "oloomaqli")
        # a differently-cased duplicate must collide, not create a twin
        r2 = self.client.post(
            "/api/knowledge/collections",
            json={"name": "بزرگ‌تر", "slug": "OLOOMAQLI"},
        )
        self.assertEqual(r2.status_code, 409)

    def test_ks03_missing_name(self):
        self.login()
        r = self.client.post(
            "/api/knowledge/collections", json={"slug": "good-slug"}
        )
        self.assertEqual(r.status_code, 400)
        r2 = self.client.post(
            "/api/knowledge/collections", json={"name": "   ", "slug": "good-slug"}
        )
        self.assertEqual(r2.status_code, 400)

    def test_same_name_different_slug_allowed(self):
        self.login()
        self.assertEqual(
            self.client.post(
                "/api/knowledge/collections",
                json={"name": "تک", "slug": "single-1"},
            ).status_code,
            201,
        )
        self.assertEqual(
            self.client.post(
                "/api/knowledge/collections",
                json={"name": "تک", "slug": "single-2"},
            ).status_code,
            201,
        )


class CollectionListDetailTests(Base):
    """KS-04 / KS-05 + PATCH + subjects + builds"""

    def _make(self, name, slug, subject=None):
        r = self.client.post(
            "/api/knowledge/collections",
            json={"name": name, "slug": slug, "subject": subject},
        )
        self.assertEqual(r.status_code, 201, r.get_data(as_text=True))
        return r.get_json()["collection"]

    def test_ks04_detail_after_create(self):
        self.login()
        c = self._make("کتاب اول", "book-one", "فلسفه")
        r = self.client.get(
            f"/api/knowledge/collections/{c['id']}"
        )
        self.assertEqual(r.status_code, 200)
        j = r.get_json()["collection"]
        self.assertEqual(j["collection_id"], c["collection_id"])
        self.assertEqual(j["documents"], [])
        self.assertEqual(j["index_builds"], [])
        r404 = self.client.get("/api/knowledge/collections/9999")
        self.assertEqual(r404.status_code, 404)

    def test_ks05_search_subject_filter_pagination(self):
        self.login()
        self._make("کتابخانه فلسفه", "falsafeh", "فلسفه")
        self._make("تفاسیر قرآن", "tafasir", "قرآن")
        self._make("منطق رواقی", "mantegh", "فلسفه")

        # no filter: 3
        r = self.client.get("/api/knowledge/collections")
        self.assertEqual(r.get_json()["total"], 3)

        # search by name (Persian)
        r = self.client.get("/api/knowledge/collections?search=فلسفه")
        self.assertEqual(r.get_json()["total"], 1)
        self.assertEqual(
            r.get_json()["collections"][0]["slug"], "falsafeh"
        )

        # search by slug (Latin)
        r = self.client.get("/api/knowledge/collections?search=tafasir")
        self.assertEqual(r.get_json()["total"], 1)

        # subject filter
        r = self.client.get("/api/knowledge/collections?subject=فلسفه")
        self.assertEqual(r.get_json()["total"], 2)

        # pagination
        r = self.client.get("/api/knowledge/collections?per_page=2&page=1")
        j = r.get_json()
        self.assertEqual(len(j["collections"]), 2)
        self.assertEqual(j["total_pages"], 2)
        r = self.client.get("/api/knowledge/collections?per_page=2&page=2")
        j = r.get_json()
        self.assertEqual(len(j["collections"]), 1)

        # sort by name ASC
        r = self.client.get("/api/knowledge/collections?sort=name&order=ASC&per_page=10")
        slugs = [c["slug"] for c in r.get_json()["collections"]]
        self.assertEqual(len(slugs), 3)

    def test_patch_rename_keeps_identity_stable(self):
        self.login()
        c = self._make("نام قدیمی", "stable-slug")
        r = self.client.patch(
            f"/api/knowledge/collections/{c['id']}",
            json={
                "name": "نام جدید",
                "description": "توضیح تازه",
                "subject": "تاریخ",
            },
        )
        self.assertEqual(r.status_code, 200, r.get_data(as_text=True))
        c2 = r.get_json()["collection"]
        self.assertEqual(c2["name"], "نام جدید")
        self.assertEqual(c2["description"], "توضیح تازه")
        self.assertEqual(c2["subject"], "تاریخ")
        # identity must NOT move when only display fields change
        self.assertEqual(c2["collection_id"], c["collection_id"])
        self.assertEqual(c2["slug"], c["slug"])
        self.assertEqual(c2["es_alias"], c["es_alias"])
        self.assertEqual(c2["collection_version"], c["collection_version"])

    def test_patch_requires_content(self):
        self.login()
        c = self._make("نام", "patch-empty")
        r = self.client.patch(
            f"/api/knowledge/collections/{c['id']}", json={"bogus": 1}
        )
        self.assertEqual(r.status_code, 400)

    def test_subjects_grouped(self):
        self.login()
        self._make("الف", "subj-a", "فلسفه")
        self._make("ب", "subj-b", "فلسفه")
        self._make("ج", "subj-c", "قرآن")
        r = self.client.get("/api/knowledge/subjects")
        self.assertEqual(r.status_code, 200)
        subj = {s["subject"]: s["n"] for s in r.get_json()["subjects"]}
        self.assertEqual(subj, {"فلسفه": 2, "قرآن": 1})

    def test_index_builds_endpoint_and_record(self):
        self.login()
        c = self._make("با build", "with-build")
        # insert a build row directly (PCM-14D will own the API)
        import sqlite3
        conn = sqlite3.connect(server.DB_PATH)
        conn.row_factory = sqlite3.Row
        conn.execute(
            """INSERT INTO knowledge_index_builds
               (iv_id, collection_id, es_index, es_alias, schema_version,
                norm_version, chunking_version, chunk_count, status, created_at, completed_at)
               VALUES (?, ?, ?, ?, 's-1', 'n-1', 'c-1', 120, 'active',
                       '2026-10-26T10:00:00Z', '2026-10-26T10:05:00Z')""",
            (
                "iv-1", c["collection_id"],
                "pct-col-with-build-v0001", "pct-col-with-build",
            ),
        )
        conn.commit()
        conn.close()
        r = self.client.get(
            f"/api/knowledge/collections/{c['id']}/builds"
        )
        self.assertEqual(r.status_code, 200)
        j = r.get_json()
        self.assertEqual(len(j["builds"]), 1)
        self.assertEqual(j["builds"][0]["iv_id"], "iv-1")
        self.assertEqual(j["builds"][0]["es_index"], "pct-col-with-build-v0001")


class AuthSecurityTests(Base):
    """KS-22 (partial): /api/knowledge/* behind PCM-09 auth"""

    def test_unauthenticated_401(self):
        # GET on list/subjects/detail, POST on create — all must be 401
        # before login. (PATCH on detail is verified via the authenticated
        # path in CollectionListDetailTests.)
        for path, method in [
            ("/api/knowledge/collections", "GET"),
            ("/api/knowledge/collections", "POST"),
            ("/api/knowledge/subjects", "GET"),
            ("/api/knowledge/collections/1", "GET"),
        ]:
            r = (
                self.client.get(path)
                if method == "GET"
                else self.client.post(path, json={})
            )
            self.assertEqual(
                r.status_code, 401, f"{method} {path} should be 401"
            )

    def test_wrong_password_401(self):
        r = self.client.post(
            "/api/auth/login", json={"password": "wrong-password"}
        )
        self.assertEqual(r.status_code, 401)
        r = self.client.get("/api/knowledge/collections")
        self.assertEqual(r.status_code, 401)

    def test_studio_page_served_without_login(self):
        # Like /dashboard/ itself: the page is public, the data is protected.
        r = self.client.get("/dashboard/studio.html")
        self.assertEqual(r.status_code, 200)
        self.assertIn("استودیوی دانش", r.get_data(as_text=True))

    def test_existing_endpoints_still_open(self):
        # Extension write APIs must stay OPEN (AGENTS.md rule 6).
        r = self.client.get("/api/stats")
        self.assertEqual(r.status_code, 200)


class SlugPrefillTests(Base):
    """_slug_from_name: valid slug output for Persian names"""

    def test_persian_name_produces_valid_slug(self):
        from knowledge_api import _slug_from_name
        for name in (
            "کتابخانه علوم عقلی",
            "تفاسیر قرآن",
            "کتاب اول ۱۴۰۵",
            "منطق و فلسفه",
        ):
            slug = _slug_from_name(name)
            self.assertTrue(slug, f"empty slug for {name!r}")
            self.assertLessEqual(len(slug), 64)
            self.assertTrue(SLUG_RE.match(slug), f"invalid slug {slug!r} from {name!r}")

    def test_latin_name_passthrough(self):
        from knowledge_api import _slug_from_name
        self.assertEqual(_slug_from_name("Book One"), "book-one")


# ────────────────────────────────────────────────────────────────────────────
# PCM-14B — Word Library (documents)
# ────────────────────────────────────────────────────────────────────────────

class UploadTests(Base):
    """KB-01 / KB-02 / KB-03 — DOCX registration + file store"""

    def setUp(self):
        super().setUp()
        self.login()
        self.coll = self.make_collection("کتابخانه علوم عقلی", "oloom-aqli")
        self._tmp = tempfile.mkdtemp(prefix="pct-kb-src-")

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)
        super().tearDown()

    def test_kb01_valid_docx_stored_and_registered(self):
        from factory._smoke_fixtures import make_sample_book
        src = make_sample_book(os.path.join(self._tmp, "sample.docx"))
        r = self.upload(self.coll["id"], src)
        self.assertEqual(r.status_code, 201, r.get_data(as_text=True))
        d = r.get_json()["document"]
        self.assertEqual(d["status"], "uploaded")
        self.assertEqual(d["file_name"], "sample.docx")
        expected_sha = self.sha256_file(src)
        self.assertEqual(d["sha256"], expected_sha)
        self.assertEqual(d["file_size"], os.path.getsize(src))
        self.assertTrue(d["document_id"].startswith("d-"))
        # the original must be stored under files/<sha12>/
        stored = os.path.join(
            self._datadir, "files", expected_sha[:12],
            d["file_id"] + ".docx")
        self.assertTrue(os.path.isfile(stored), f"missing {stored}")
        self.assertEqual(self.sha256_file(stored), expected_sha)
        # registry visible on the collection detail
        det = self.client.get(
            f"/api/knowledge/collections/{self.coll['id']}").get_json()
        self.assertEqual(len(det["collection"]["documents"]), 1)
        self.assertEqual(det["collection"]["documents"][0]["document_id"],
                         d["document_id"])

    def test_kb02_duplicate_upload_409(self):
        from factory._smoke_fixtures import make_sample_book
        src = make_sample_book(os.path.join(self._tmp, "sample.docx"))
        r1 = self.upload(self.coll["id"], src)
        self.assertEqual(r1.status_code, 201)
        first_id = r1.get_json()["document"]["document_id"]
        # same bytes, different filename — must still be detected as dup
        r2 = self.upload(self.coll["id"], src, name="copy-of-sample.docx")
        self.assertEqual(r2.status_code, 409)
        self.assertEqual(r2.get_json().get("code"), "duplicate")
        self.assertEqual(r2.get_json().get("existing_document_id"), first_id)

    def test_kb03_wrong_extension_rejected(self):
        p = os.path.join(self._tmp, "notes.txt")
        with open(p, "wb") as f:
            f.write(b"hello world")
        r = self.upload(self.coll["id"], p)
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.get_json().get("field"), "file")

    def test_kb03_empty_file_rejected(self):
        p = os.path.join(self._tmp, "empty.docx")
        with open(p, "wb") as f:
            f.write(b"")
        r = self.upload(self.coll["id"], p)
        self.assertEqual(r.status_code, 400)

    def test_kb03_over_size_cap_rejected(self):
        import knowledge_api
        big = io.BytesIO(b"\x00" * 2048)
        data = {"file": (big, "big.docx")}
        with unittest.mock.patch.object(knowledge_api,
                                        "MAX_UPLOAD_BYTES", 1024):
            r = self.client.post(
                f"/api/knowledge/collections/{self.coll['id']}/documents",
                data=data, content_type="multipart/form-data")
        self.assertEqual(r.status_code, 400)

    def test_upload_requires_file(self):
        r = self.client.post(
            f"/api/knowledge/collections/{self.coll['id']}/documents",
            data={}, content_type="multipart/form-data")
        self.assertEqual(r.status_code, 400)


class ProcessTests(Base):
    """KB-04 / KB-05 / KB-06 / KB-07 / KB-08 — real Word Factory pipeline"""

    def setUp(self):
        super().setUp()
        self.login()
        self.coll = self.make_collection("کتابخانه علوم عقلی", "oloom-aqli")
        self._tmp = tempfile.mkdtemp(prefix="pct-kb-src-")
        from factory._smoke_fixtures import make_sample_book
        self.good_src = make_sample_book(os.path.join(self._tmp, "good.docx"))
        self.upload(self.coll["id"], self.good_src)
        self.doc = self.client.get(
            f"/api/knowledge/collections/{self.coll['id']}/documents"
        ).get_json()["documents"][0]

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)
        super().tearDown()

    def _doc_after(self, doc_id):
        return self.client.get(
            f"/api/knowledge/documents/{doc_id}").get_json()["document"]

    def test_kb05_process_valid_book(self):
        r = self.client.post(f"/api/knowledge/documents/{self.doc['document_id']}/process")
        self.assertEqual(r.status_code, 202, r.get_data(as_text=True))
        job = self.wait_job(r.get_json()["job"]["job_id"])
        self.assertEqual(job["status"], "succeeded", job)
        d = self._doc_after(self.doc["document_id"])
        self.assertIn(d["status"], ("parsed", "needs_review"))
        self.assertGreater(d["blocks_count"], 0)
        self.assertGreater(d["chars_count"], 0)
        self.assertTrue(d["file_id"].startswith("f-"))
        self.assertTrue(d["work_id"])
        self.assertTrue(d["edition_id"])
        # factory quality vocabulary (quality.py): "ok" | "manual_review"
        self.assertIn(d["quality_status"], ("ok", "manual_review"))
        # factory output must exist on disk
        out = os.path.join(self._datadir, "out", d["file_id"])
        for fn in ("blocks.jsonl", "document.json", "quality-report.json",
                   "manifest.json"):
            self.assertTrue(os.path.isfile(os.path.join(out, fn)), fn)
        # collection book_count reflects the parsed doc
        det = self.client.get(
            f"/api/knowledge/collections/{self.coll['id']}").get_json()
        self.assertEqual(det["collection"]["book_count"], 1)

    def test_kb04_ole2_masquerading_docx_fails_cleanly(self):
        from factory._smoke_fixtures import make_ole2_doc
        src = make_ole2_doc(os.path.join(self._tmp, "legacy.docx"))
        r = self.upload(self.coll["id"], src)
        self.assertEqual(r.status_code, 201, r.get_data(as_text=True))
        doc_id = r.get_json()["document"]["document_id"]
        r = self.client.post(f"/api/knowledge/documents/{doc_id}/process")
        self.assertEqual(r.status_code, 202)
        job = self.wait_job(r.get_json()["job"]["job_id"])
        # the factory refused the OLE2 bytes → job failed with a clean error
        self.assertEqual(job["status"], "failed", job)
        self.assertTrue(job["error"])
        d = self._doc_after(doc_id)
        # the document must be marked failed (reprocessable), not lost
        self.assertEqual(d["status"], "failed")
        self.assertTrue(d["error"])

    def test_kb06_idempotent_reprocess(self):
        doc_id = self.doc["document_id"]
        r1 = self.client.post(f"/api/knowledge/documents/{doc_id}/process")
        self.assertEqual(r1.status_code, 202)
        job1 = r1.get_json()["job"]
        self.wait_job(job1["job_id"])
        # same job_key → same job, no second worker
        r2 = self.client.post(f"/api/knowledge/documents/{doc_id}/process")
        self.assertEqual(r2.status_code, 200)
        j2 = r2.get_json()
        self.assertTrue(j2["resubmitted"])
        self.assertEqual(j2["job"]["job_id"], job1["job_id"])
        # exactly ONE job row for this document
        jobs = [j for j in self.client.get("/api/knowledge/jobs").get_json()["jobs"]
                if j["kind"] == "process_document"
                and j["job_key"].endswith(doc_id)]
        self.assertEqual(len(jobs), 1)

    def test_kb07_structure_quality_blocks_raw_vs_normalized(self):
        doc_id = self.doc["document_id"]
        r = self.client.post(f"/api/knowledge/documents/{doc_id}/process")
        self.wait_job(r.get_json()["job"]["job_id"])
        d = self._doc_after(doc_id)
        self.assertEqual(d["status"], d["status"])  # parsed/needs_review
        # structure
        r = self.client.get(f"/api/knowledge/documents/{doc_id}/structure")
        self.assertEqual(r.status_code, 200)
        j = r.get_json()
        self.assertIn("structure", j)
        # quality report
        r = self.client.get(f"/api/knowledge/documents/{doc_id}/quality")
        self.assertEqual(r.status_code, 200)
        self.assertIn("quality", r.get_json())
        # blocks
        r = self.client.get(f"/api/knowledge/documents/{doc_id}/blocks")
        j = r.get_json()
        self.assertGreater(j["total"], 0)
        self.assertLessEqual(len(j["blocks"]), j["limit"])
        first = j["blocks"][0]
        for key in ("block_id", "type", "raw_text", "normalized_text"):
            self.assertIn(key, first)
        # raw vs normalized: the sample book has Arabic Yā + extra spaces,
        # so the two views MUST differ (RAW never mutated).
        r = self.client.get(f"/api/knowledge/documents/{doc_id}/file?view=raw")
        raw = r.get_json()["text"]
        r = self.client.get(
            f"/api/knowledge/documents/{doc_id}/file?view=normalized")
        norm = r.get_json()["text"]
        self.assertTrue(raw)
        self.assertNotEqual(raw, norm)
        self.assertIn("ی", norm)          # ي → ی
        self.assertNotIn("   ", norm)      # collapsed spaces

    def test_kb07_unprocessed_document_409_on_artifacts(self):
        # upload but do NOT process
        from factory._smoke_fixtures import make_docx
        src = make_docx(os.path.join(self._tmp, "raw.docx"),
                        [("Normal", "متن آزمایشی")])
        doc_id = self.upload(self.coll["id"], src).get_json()["document"]["document_id"]
        for ep in ("structure", "quality"):
            r = self.client.get(f"/api/knowledge/documents/{doc_id}/{ep}")
            self.assertEqual(r.status_code, 409, ep)

    def test_kb08_approve_rules(self):
        doc_id = self.doc["document_id"]
        # not parsed yet → 409
        r = self.client.post(f"/api/knowledge/documents/{doc_id}/approve")
        self.assertEqual(r.status_code, 409)
        r = self.client.post(f"/api/knowledge/documents/{doc_id}/process")
        self.wait_job(r.get_json()["job"]["job_id"])
        r = self.client.post(f"/api/knowledge/documents/{doc_id}/approve")
        self.assertEqual(r.status_code, 200, r.get_data(as_text=True))
        self.assertEqual(r.get_json()["document"]["status"], "approved")
        # approving again (already approved) → 409
        r = self.client.post(f"/api/knowledge/documents/{doc_id}/approve")
        self.assertEqual(r.status_code, 409)


class DetachTests(Base):
    """KB-09 — detach removes registry link but keeps the file"""

    def test_kb09_detach(self):
        self.login()
        c = self.make_collection("کتابخانه", "detach-col")
        from factory._smoke_fixtures import make_docx
        tmp = tempfile.mkdtemp(prefix="pct-kb-src-")
        try:
            src = make_docx(os.path.join(tmp, "a.docx"),
                            [("Normal", "متنی کوتاه")])
            d = self.upload(c["id"], src).get_json()["document"]
            stored = os.path.join(
                self._datadir, "files", d["sha256"][:12],
                d["file_id"] + ".docx")
            r = self.client.delete(
                f"/api/knowledge/collections/{c['id']}/documents/{d['document_id']}")
            self.assertEqual(r.status_code, 200, r.get_data(as_text=True))
            # registry row gone
            docs = self.client.get(
                f"/api/knowledge/collections/{c['id']}/documents").get_json()
            self.assertEqual(docs["total"], 0)
            self.assertEqual(
                self.client.get(f"/api/knowledge/documents/{d['document_id']}")
                .status_code, 404)
            # but the original file is KEPT (may be shared / re-registered)
            self.assertTrue(os.path.isfile(stored))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class BatchTests(Base):
    """KB-10 — folder-based import planning"""

    def test_kb10_batch_plan_with_mixed_entries(self):
        self.login()
        c = self.make_collection("کتابخانه", "batch-col")
        from factory._smoke_fixtures import make_docx
        tmp = tempfile.mkdtemp(prefix="pct-kb-src-")
        try:
            s1 = make_docx(os.path.join(tmp, "one.docx"),
                           [("Normal", "کتاب یک")])
            s2 = make_docx(os.path.join(tmp, "two.docx"),
                           [("Normal", "کتاب دو")])
            plan_files = [
                {"name": "one.docx", "size": os.path.getsize(s1),
                 "sha256": self.sha256_file(s1)},
                {"name": "two.docx", "size": os.path.getsize(s2),
                 "sha256": self.sha256_file(s2)},
                {"name": "readme.txt", "size": 10,
                 "sha256": "a" * 64},
            ]
            r = self.client.post("/api/knowledge/import/batches", json={
                "collection_id": c["collection_id"],
                "folder_name": "فایل‌های جدید",
                "files": plan_files,
            })
            self.assertEqual(r.status_code, 201, r.get_data(as_text=True))
            j = r.get_json()
            self.assertEqual(j["summary"]["total"], 3)
            self.assertEqual(j["summary"]["pending"], 2)
            self.assertEqual(j["summary"]["invalid"], 1)
            statuses = {e["status"] for e in j["plan"]}
            self.assertIn("pending", statuses)
            self.assertIn("invalid_extension", statuses)
            batch_id = j["batch"]["batch_id"]
            self.assertTrue(batch_id.startswith("b-"))
            # batch detail lists the planned state
            b = self.client.get(
                f"/api/knowledge/import/batches/{batch_id}").get_json()
            self.assertEqual(b["batch"]["status"], "planned")
            self.assertEqual(b["batch"]["file_count"], 3)

            # one file's sha missing/invalid → flagged, not crashing
            r = self.client.post("/api/knowledge/import/batches", json={
                "collection_id": c["collection_id"],
                "files": [{"name": "x.docx", "size": 5, "sha256": "zz"}],
            })
            self.assertEqual(r.status_code, 201)
            self.assertEqual(
                r.get_json()["plan"][0]["status"], "invalid_sha")

            # unknown collection → 404
            r = self.client.post("/api/knowledge/import/batches", json={
                "collection_id": "c-doesnotexist",
                "files": plan_files,
            })
            self.assertEqual(r.status_code, 404)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class MetadataTests(Base):
    """KB-11 — custom versioned metadata, three scopes"""

    def setUp(self):
        super().setUp()
        self.login()
        self.coll = self.make_collection("کتابخانه", "meta-col")

    def test_kb11_field_crud_and_validation(self):
        # create a collection-scoped field
        r = self.client.post("/api/knowledge/metadata/fields", json={
            "scope": "collection",
            "collection_id": self.coll["collection_id"],
            "field_key": "publisher",
            "display_name": "ناشر",
            "data_type": "string",
        })
        self.assertEqual(r.status_code, 201, r.get_data(as_text=True))
        f = r.get_json()["field"]
        self.assertEqual(f["field_key"], "publisher")
        self.assertEqual(f["scope"], "collection")
        self.assertTrue(f["field_id"].startswith("mf-"))

        # duplicate (same scope+collection+key) → 409
        r = self.client.post("/api/knowledge/metadata/fields", json={
            "scope": "collection",
            "collection_id": self.coll["collection_id"],
            "field_key": "publisher",
            "display_name": "ناشر ۲",
        })
        self.assertEqual(r.status_code, 409)

        # invalid data_type → 400
        r = self.client.post("/api/knowledge/metadata/fields", json={
            "scope": "collection",
            "collection_id": self.coll["collection_id"],
            "field_key": "x1", "display_name": "نمو",
            "data_type": "nonsense",
        })
        self.assertEqual(r.status_code, 400)

        # document-scoped field
        r = self.client.post("/api/knowledge/metadata/fields", json={
            "scope": "document",
            "field_key": "page_count",
            "display_name": "تعداد صفحات",
            "data_type": "number",
            "required": True,
        })
        self.assertEqual(r.status_code, 201, r.get_data(as_text=True))
        pf = r.get_json()["field"]

        # list: both visible for this collection
        r = self.client.get(
            f"/api/knowledge/metadata/fields?collection_id={self.coll['collection_id']}")
        keys = {f["field_key"] for f in r.get_json()["fields"]}
        self.assertIn("publisher", keys)
        self.assertIn("page_count", keys)

        # update display_name
        r = self.client.patch(
            f"/api/knowledge/metadata/fields/{f['field_id']}",
            json={"display_name": "ناشر (ویرایش‌شده)"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["field"]["display_name"],
                         "ناشر (ویرایش‌شده)")

        # soft-disable: field no longer listed, values kept
        r = self.client.delete(f"/api/knowledge/metadata/fields/{f['field_id']}")
        self.assertEqual(r.status_code, 200)
        keys = {f_["field_key"] for f_ in self.client.get(
            f"/api/knowledge/metadata/fields?collection_id={self.coll['collection_id']}"
        ).get_json()["fields"]}
        self.assertNotIn("publisher", keys)
        self.assertIn("page_count", keys)

        # invalid default value for a typed field → 400
        r = self.client.post("/api/knowledge/metadata/fields", json={
            "scope": "document",
            "field_key": "pub_year", "display_name": "سال",
            "data_type": "number", "default_value": "نه-عدد",
        })
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.get_json().get("field"), "default_value")

        _ = pf  # used for scope assertion below
        self.assertEqual(pf["scope"], "document")

    def test_kb11_value_set_get_version_and_invalid(self):
        self.client.post("/api/knowledge/metadata/fields", json={
            "scope": "collection",
            "collection_id": self.coll["collection_id"],
            "field_key": "lang", "display_name": "زبان",
            "data_type": "string",
        })
        cid = self.coll["collection_id"]
        r = self.client.post("/api/knowledge/metadata/values", json={
            "field_key": "lang", "collection_id": cid, "value": "فارسی"})
        self.assertEqual(r.status_code, 200, r.get_data(as_text=True))
        self.assertEqual(r.get_json()["version"], 1)
        r = self.client.post("/api/knowledge/metadata/values", json={
            "field_key": "lang", "collection_id": cid, "value": "فارسی/عربی"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["version"], 2)
        vals = self.client.get(
            f"/api/knowledge/metadata/values?collection_id={cid}").get_json()
        self.assertEqual(len(vals["values"]), 1)
        self.assertEqual(vals["values"][0]["value"], "فارسی/عربی")
        # deleting the value works
        r = self.client.delete(
            f"/api/knowledge/metadata/values/{vals['values'][0]['value_id']}")
        self.assertEqual(r.status_code, 200)

    def test_kb11_invalid_value_rejected(self):
        self.client.post("/api/knowledge/metadata/fields", json={
            "scope": "collection",
            "collection_id": self.coll["collection_id"],
            "field_key": "year", "display_name": "سال",
            "data_type": "number",
        })
        r = self.client.post("/api/knowledge/metadata/values", json={
            "field_key": "year",
            "collection_id": self.coll["collection_id"],
            "value": "نه-عدد",
        })
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.get_json().get("field"), "field_key")

    def test_kb11_unknown_field_rejected(self):
        r = self.client.post("/api/knowledge/metadata/values", json={
            "field_key": "ghost",
            "collection_id": self.coll["collection_id"],
            "value": "x",
        })
        self.assertEqual(r.status_code, 404)


class JobAndCompatibilityTests(Base):
    """KB-12 / KB-13 — persistent jobs, stuck recovery, honest ES status"""

    def test_kb12_jobs_listed_and_stuck_recovery(self):
        self.login()
        conn = sqlite3.connect(server.DB_PATH)
        conn.row_factory = sqlite3.Row
        conn.execute(
            "CREATE TABLE IF NOT EXISTS knowledge_jobs ("
            "job_id TEXT PRIMARY KEY, job_key TEXT NOT NULL UNIQUE, "
            "kind TEXT NOT NULL, collection_id TEXT, batch_id TEXT, "
            "status TEXT NOT NULL DEFAULT 'pending', stage TEXT, "
            "progress INTEGER NOT NULL DEFAULT 0, total INTEGER NOT NULL DEFAULT 0, "
            "retry_count INTEGER NOT NULL DEFAULT 0, error TEXT, "
            "idempotency_key TEXT, created_at TEXT NOT NULL, "
            "updated_at TEXT NOT NULL, completed_at TEXT)")
        # a job stuck since 2 hours ago (restart happened)
        conn.execute(
            "INSERT INTO knowledge_jobs "
            "(job_id, job_key, kind, status, created_at, updated_at) "
            "VALUES ('j-stuck001', 'process_document:d-stuck01', "
            "'process_document', 'pending', "
            "datetime('now','-2 hours'), datetime('now','-2 hours'))")
        # a FRESH pending job (10s old) — must NOT be marked interrupted
        conn.execute(
            "INSERT INTO knowledge_jobs "
            "(job_id, job_key, kind, status, created_at, updated_at) "
            "VALUES ('j-fresh001', 'process_document:d-fresh01', "
            "'process_document', 'pending', "
            "datetime('now','-10 seconds'), datetime('now','-10 seconds'))")
        conn.commit()
        conn.close()

        jobs = {j["job_id"]: j for j in
                self.client.get("/api/knowledge/jobs").get_json()["jobs"]}
        self.assertEqual(jobs["j-stuck001"]["status"], "interrupted")
        self.assertIn("worker interrupted", jobs["j-stuck001"]["error"])
        self.assertEqual(jobs["j-fresh001"]["status"], "pending")

    def test_kb12b_retry_reexecutes_interrupted_job(self):
        """PCM-14B acceptance B10 (root fix): /process on a document whose job
        is 'interrupted' MUST re-execute it (reset to pending + fresh worker
        + retry_count bump), not return the stale row."""
        self.login()
        from factory._smoke_fixtures import make_sample_book
        self.coll = self.make_collection("کتابخانه", "retry-col")
        tmp = tempfile.mkdtemp(prefix="pct-kb-retry-")
        src = make_sample_book(os.path.join(tmp, "retry.docx"))
        self.upload(self.coll["id"], src)
        doc = self.client.get(
            f"/api/knowledge/collections/{self.coll['id']}/documents"
        ).get_json()["documents"][0]
        doc_id = doc["document_id"]

        # simulate a crash: the document's job is interrupted (2h old),
        # document left 'uploaded'
        conn = sqlite3.connect(server.DB_PATH)
        conn.row_factory = sqlite3.Row
        conn.execute(
            """INSERT INTO knowledge_jobs
               (job_id, job_key, kind, collection_id, status,
                created_at, updated_at)
               VALUES ('j-retry001', 'process_document:%s', 'process_document',
                       ?, 'interrupted',
                       datetime('now','-2 hours'), datetime('now','-2 hours'))"""
            % doc_id, (self.coll["collection_id"],))
        conn.execute(
            "UPDATE knowledge_collection_documents SET status='uploaded' "
            "WHERE document_id=?", (doc_id,))
        conn.commit()
        conn.close()

        # /process must RE-RUN (202 + resubmitted=false) and finish succeeded
        r = self.client.post(f"/api/knowledge/documents/{doc_id}/process")
        self.assertEqual(r.status_code, 202, r.get_data(as_text=True))
        self.assertFalse(r.get_json()["resubmitted"])
        job_id = r.get_json()["job"]["job_id"]
        self.assertEqual(job_id, "j-retry001")  # same row reused, re-executed

        job = self.wait_job(job_id)
        self.assertEqual(job["status"], "succeeded", dict(job))
        self.assertEqual(job["retry_count"], 1)
        d = self.client.get(
            f"/api/knowledge/documents/{doc_id}").get_json()["document"]
        self.assertIn(d["status"], ("parsed", "needs_review"))

        # a SUCCEEDED job with the same key is NOT re-run (idempotency holds)
        r = self.client.post(f"/api/knowledge/documents/{doc_id}/process")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["resubmitted"])
        self.assertEqual(r.get_json()["job"]["status"], "succeeded")
        jobs = {j["job_id"]: j for j in
                self.client.get("/api/knowledge/jobs").get_json()["jobs"]}
        self.assertEqual(jobs[job_id]["retry_count"], 1)

    def test_kb13_compatibility_not_verified(self):
        self.login()
        r = self.client.get("/api/knowledge/compatibility")
        self.assertEqual(r.status_code, 200)
        j = r.get_json()
        self.assertFalse(j["es_available"])
        self.assertEqual(j["previous_mapping"], "NOT_VERIFIED")
        self.assertTrue(all(f["compatibility"] == "NOT_VERIFIED"
                            for f in j["field_matrix"]))


if __name__ == "__main__":
    unittest.main(verbosity=2)

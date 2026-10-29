# -*- coding: utf-8 -*-
"""PCM-14D — Work/Edition/Volume registry + entity metadata scopes tests.

RD-01 schema idempotent: registry tables + entity metadata columns exist,
     ensure_knowledge_schema is a no-op on second run
RD-02 additive migration on a pre-14D DB: legacy schema + denormalized doc
     rows -> registry tables created, entity columns added, backfill done,
     legacy data untouched (rollbackable by data only)
RD-03 process -> registry rows auto-created (ids identical to factory)
RD-04 work/edition/volume detail + hierarchy counts
RD-05 work create idempotent (same key -> same id, created=false 2nd time),
     unknown edition/volume in metadata -> 404, invalid scope -> 400
RD-06 metadata scope chain: set values at work/edition/volume/document,
     /metadata/resolve precedence document > volume > edition > work >
     collection, sources reported, unknown document 404, no context 400
RD-07 metadata list values filterable by work_id/edition_id/volume_id

Follows the PCM-12.3 rule: import pct_test_support FIRST, then server.
All tests use the shared temp DB (pct_test_support.reset_db) and an
isolated PCT_KNOWLEDGE_DATA_DIR — the production DB is never touched.
"""
import hashlib
import io
import os
import sqlite3
import tempfile
import unittest
import unittest.mock

import pct_test_support  # noqa: F401  (must precede `import server`)

import server
from factory._smoke_fixtures import make_sample_book
from factory.models import short_id
from knowledge_api import ensure_knowledge_schema, _work_key_from_biblio

PW = "test-secret-123"


class Base(unittest.TestCase):
    def setUp(self):
        pct_test_support.reset_db()
        self._datadir = tempfile.mkdtemp(prefix="pct-reg-")
        self._old_dd = os.environ.get("PCT_KNOWLEDGE_DATA_DIR")
        os.environ["PCT_KNOWLEDGE_DATA_DIR"] = self._datadir
        self.client = server.app.test_client()

    def tearDown(self):
        if self._old_dd is None:
            os.environ.pop("PCT_KNOWLEDGE_DATA_DIR", None)
        else:
            os.environ["PCT_KNOWLEDGE_DATA_DIR"] = self._old_dd
        import shutil
        shutil.rmtree(self._datadir, ignore_errors=True)

    def login(self):
        return self.client.post("/api/auth/login", json={"password": PW})

    def make_collection(self, name="کتابخانه آزمون", slug="reg-test"):
        r = self.client.post(
            "/api/knowledge/collections",
            json={"name": name, "slug": slug})
        self.assertEqual(r.status_code, 201, r.get_data(as_text=True))
        return r.get_json()["collection"]

    def make_book(self, name="book.docx"):
        p = os.path.join(self._datadir, name)
        return make_sample_book(p)

    def upload(self, coll_id, path):
        # NOTE: document routes take the INTEGER collection row id (coll["id"]),
        # not the collection_id string (coll["collection_id"]).
        if isinstance(coll_id, dict):
            coll_id = coll_id["id"]
        with open(path, "rb") as f:
            data = {"file": (io.BytesIO(f.read()), os.path.basename(path))}
        return self.client.post(
            f"/api/knowledge/collections/{coll_id}/documents",
            data=data, content_type="multipart/form-data")

    def wait_job(self, job_id, timeout=30.0):
        import time
        deadline = time.time() + timeout
        while time.time() < deadline:
            j = self.client.get("/api/knowledge/jobs").get_json()
            row = next((x for x in j["jobs"] if x["job_id"] == job_id), None)
            if row and row["status"] in ("succeeded", "failed", "interrupted"):
                return row
            time.sleep(0.2)
        self.fail(f"job {job_id} did not finish within {timeout}s")

    def process_doc(self, doc_id):
        r = self.client.post(f"/api/knowledge/documents/{doc_id}/process")
        self.assertIn(r.status_code, (200, 202), r.get_data(as_text=True))
        job = r.get_json()["job"]
        j = self.wait_job(job["job_id"])
        self.assertEqual(j["status"], "succeeded", j)
        return j

    @staticmethod
    def db_path():
        return server.DB_PATH


# ────────────────────────────────────────────────────────────────────────────
# RD-01 — schema idempotent
# ────────────────────────────────────────────────────────────────────────────

class TestRD01_Schema(Base):
    def test_rd01_idempotent(self):
        self.login()  # auth required before the view can build the schema
        self.client.get("/api/knowledge/collections")  # triggers schema
        db = sqlite3.connect(self.db_path())
        db.row_factory = sqlite3.Row
        try:
            self._rd01_checks(db)
        finally:
            db.close()

    def _rd01_checks(self, db):
        tables = {r[0] for r in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        for t in ("knowledge_works", "knowledge_editions",
                  "knowledge_volumes"):
            self.assertIn(t, tables)
        fcols = {r[1] for r in db.execute(
            "PRAGMA table_info(knowledge_metadata_fields)")}
        vcols = {r[1] for r in db.execute(
            "PRAGMA table_info(knowledge_metadata_values)")}
        for col in ("work_id", "edition_id", "volume_id"):
            self.assertIn(col, fcols)
            self.assertIn(col, vcols)
        # second run must be a no-op (no error, no column dup)
        ensure_knowledge_schema(db)
        fcols2 = {r[1] for r in db.execute(
            "PRAGMA table_info(knowledge_metadata_fields)")}
        self.assertEqual(fcols, fcols2)
        db.close()


# ────────────────────────────────────────────────────────────────────────────
# RD-02 — additive migration on a pre-14D DB (legacy schema simulation)
# ────────────────────────────────────────────────────────────────────────────

class TestRD02_LegacyMigration(Base):
    def test_rd02_backfill(self):
        legacy = os.path.join(self._datadir, "legacy.db")
        con = sqlite3.connect(legacy)
        con.row_factory = sqlite3.Row
        try:
            self._rd02_checks(con)
        finally:
            con.close()

    def _rd02_checks(self, con):
        # Minimal PRE-14D state: the studio tables exist (as they do after
        # PCM-14B) but WITHOUT the registry tables and WITHOUT the
        # work/edition/volume columns on the metadata tables.
        con.executescript("""
        CREATE TABLE knowledge_collections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            collection_id TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL, slug TEXT NOT NULL UNIQUE,
            language TEXT NOT NULL DEFAULT 'fa',
            collection_version INTEGER NOT NULL DEFAULT 1,
            schema_version TEXT NOT NULL DEFAULT 's-1',
            normalization_version TEXT NOT NULL DEFAULT 'n-1',
            chunking_version TEXT NOT NULL DEFAULT 'c-1',
            es_alias TEXT NOT NULL UNIQUE,
            current_index_build TEXT,
            book_count INTEGER NOT NULL DEFAULT 0,
            chunk_count INTEGER NOT NULL DEFAULT 0,
            indexing_status TEXT NOT NULL DEFAULT 'none',
            validation_status TEXT NOT NULL DEFAULT 'pending',
            access_policy TEXT NOT NULL DEFAULT 'auth',
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
        CREATE TABLE knowledge_collection_documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            collection_id TEXT NOT NULL,
            document_id TEXT NOT NULL UNIQUE,
            file_name TEXT, relative_path TEXT,
            sha256 TEXT NOT NULL,
            file_size INTEGER NOT NULL DEFAULT 0,
            file_id TEXT, work_id TEXT, edition_id TEXT, volume_id TEXT,
            status TEXT NOT NULL DEFAULT 'uploaded',
            blocks_count INTEGER NOT NULL DEFAULT 0,
            chars_count INTEGER NOT NULL DEFAULT 0,
            quality_status TEXT, quality_score REAL,
            parser_version TEXT, norm_version TEXT, out_dir TEXT,
            error TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
            UNIQUE (collection_id, sha256));
        CREATE TABLE knowledge_index_builds (
            iv_id TEXT PRIMARY KEY, collection_id TEXT NOT NULL,
            es_index TEXT NOT NULL, es_alias TEXT NOT NULL,
            schema_version TEXT NOT NULL, norm_version TEXT,
            chunking_version TEXT, chunk_count INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'building',
            created_at TEXT NOT NULL, completed_at TEXT);
        CREATE TABLE knowledge_jobs (
            job_id TEXT PRIMARY KEY, job_key TEXT NOT NULL UNIQUE,
            kind TEXT NOT NULL, collection_id TEXT, batch_id TEXT,
            status TEXT NOT NULL DEFAULT 'pending', stage TEXT,
            progress INTEGER NOT NULL DEFAULT 0, total INTEGER NOT NULL DEFAULT 0,
            retry_count INTEGER NOT NULL DEFAULT 0, error TEXT,
            idempotency_key TEXT, created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL, completed_at TEXT);
        CREATE TABLE knowledge_import_batches (
            batch_id TEXT PRIMARY KEY, collection_id TEXT NOT NULL,
            folder_name TEXT, file_count INTEGER NOT NULL DEFAULT 0,
            processed_count INTEGER NOT NULL DEFAULT 0,
            failed_count INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'planned',
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
        CREATE TABLE knowledge_metadata_fields (
            field_id TEXT PRIMARY KEY, scope TEXT NOT NULL,
            collection_id TEXT NOT NULL DEFAULT '__global__',
            field_key TEXT NOT NULL, display_name TEXT NOT NULL,
            data_type TEXT NOT NULL DEFAULT 'string',
            required INTEGER NOT NULL DEFAULT 0, default_value TEXT,
            validation_rules TEXT, searchable INTEGER NOT NULL DEFAULT 1,
            schema_version TEXT NOT NULL DEFAULT 'm-1',
            enabled INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
            UNIQUE (scope, collection_id, field_key));
        CREATE TABLE knowledge_metadata_values (
            value_id INTEGER PRIMARY KEY AUTOINCREMENT,
            field_id TEXT NOT NULL, scope TEXT NOT NULL,
            collection_id TEXT NOT NULL DEFAULT '',
            batch_id TEXT NOT NULL DEFAULT '',
            document_id TEXT NOT NULL DEFAULT '',
            value TEXT, source TEXT NOT NULL DEFAULT 'user',
            version INTEGER NOT NULL DEFAULT 1,
            edited_at TEXT NOT NULL, edited_by TEXT,
            UNIQUE (scope, collection_id, batch_id, document_id, field_id));
        """)
        con.execute(
            "INSERT INTO knowledge_collections (collection_id, name, slug, "
            "es_alias, created_at, updated_at) VALUES "
            "('c-legacy', 'کالکشن قدیمی', 'legacy', 'pct-col-legacy', "
            "'2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')")
        # Legacy processed documents with denormalized entity ids —
        # exactly what PCM-14B left in the production DB.
        for i, (wid, eid, vid) in enumerate((("w-a", "e-a", "v-a"),
                                             ("w-b", "e-b", None))):
            con.execute(
                "INSERT INTO knowledge_collection_documents "
                "(collection_id, document_id, file_name, sha256, file_size, "
                " file_id, work_id, edition_id, volume_id, status, "
                " blocks_count, chars_count, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'parsed', 10, 100, "
                "'2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')",
                ("c-legacy", f"d-leg{i:04d}", f"old{i}.docx",
                 f"{i:02x}" * 32, 1024, f"f-old{i:04d}", wid, eid, vid))
        # A legacy collection-scoped metadata value (must survive as-is).
        con.execute(
            "INSERT INTO knowledge_metadata_fields (field_id, scope, "
            "collection_id, field_key, display_name, created_at, updated_at)"
            " VALUES ('mf-leg', 'collection', 'c-legacy', 'genre', 'ژانر', "
            "'2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')")
        con.execute(
            "INSERT INTO knowledge_metadata_values (field_id, scope, "
            "collection_id, value, edited_at) VALUES "
            "('mf-leg', 'collection', 'c-legacy', 'فلسفه', "
            "'2026-01-01T00:00:00Z')")
        con.commit()

        # Run the NEW schema function against the legacy DB.
        ensure_knowledge_schema(con)

        tables = {r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        for t in ("knowledge_works", "knowledge_editions",
                  "knowledge_volumes"):
            self.assertIn(t, tables)
        vcols = {r[1] for r in con.execute(
            "PRAGMA table_info(knowledge_metadata_values)")}
        for col in ("work_id", "edition_id", "volume_id"):
            self.assertIn(col, vcols)
        # Backfill: both works created, one with an edition+volume row.
        works = {r[0] for r in con.execute("SELECT work_id FROM knowledge_works")}
        self.assertEqual(works, {"w-a", "w-b"})
        editions = {r[0] for r in con.execute(
            "SELECT edition_id FROM knowledge_editions")}
        # every legacy doc carrying an edition_id gets its own row
        self.assertEqual(editions, {"e-a", "e-b"})
        vols = {r[0] for r in con.execute(
            "SELECT volume_id FROM knowledge_volumes")}
        self.assertEqual(vols, {"v-a"})
        cnt = con.execute(
            "SELECT document_count FROM knowledge_works WHERE work_id='w-a'"
        ).fetchone()[0]
        self.assertEqual(cnt, 1)
        # Idempotent: a second run must not duplicate or alter.
        ensure_knowledge_schema(con)
        self.assertEqual(con.execute(
            "SELECT COUNT(*) FROM knowledge_works").fetchone()[0], 2)
        # Legacy metadata value untouched (sentinel default on new cols).
        row = con.execute(
            "SELECT value, work_id FROM knowledge_metadata_values "
            "WHERE field_id='mf-leg'").fetchone()
        self.assertEqual(row["value"], "فلسفه")
        self.assertEqual(row["work_id"], "")
        # Legacy documents untouched.


# ────────────────────────────────────────────────────────────────────────────
# RD-03/04 — process -> registry sync + hierarchy detail
# ────────────────────────────────────────────────────────────────────────────

class TestRD03_ProcessSync(Base):
    def _setup_book(self):
        self.login()
        coll = self.make_collection()
        r = self.upload(coll, self.make_book())
        self.assertEqual(r.status_code, 201, r.get_data(as_text=True))
        doc = r.get_json()["document"]
        self.process_doc(doc["document_id"])
        d = self.client.get(
            f"/api/knowledge/documents/{doc['document_id']}").get_json()["document"]
        self.assertEqual(d["status"], "parsed")
        return coll, d

    def test_rd03_registry_created(self):
        coll, d = self._setup_book()
        self.assertTrue(d["work_id"].startswith("w-"))
        self.assertTrue(d["edition_id"].startswith("e-"))
        self.assertIsNone(d["volume_id"])  # fixture has no «جلد» line
        # The registry mirrors the factory's extract-only result. python-docx
        # core properties win over front matter, and the default template's
        # core author is "python-docx" (title core is empty -> front matter).
        expected_author = "python-docx"
        db = sqlite3.connect(self.db_path())
        db.row_factory = sqlite3.Row
        try:
            w = db.execute("SELECT * FROM knowledge_works WHERE work_id=?",
                           (d["work_id"],)).fetchone()
            self.assertIsNotNone(w)
            self.assertEqual(w["source"], "factory")
            self.assertEqual(w["title"], "نمونه کتاب آزمون")
            self.assertEqual(w["author"], expected_author)
            e = db.execute("SELECT * FROM knowledge_editions WHERE edition_id=?",
                           (d["edition_id"],)).fetchone()
            self.assertIsNotNone(e)
            self.assertEqual(e["publisher"], "انتشارات نمونه")
            self.assertEqual(db.execute(
                "SELECT COUNT(*) FROM knowledge_volumes").fetchone()[0], 0)
        finally:
            db.close()
        # The id the registry used must equal the deterministic factory id.
        key = _work_key_from_biblio("نمونه کتاب آزمون", expected_author, "")
        self.assertEqual(d["work_id"], short_id("w", key))

    def test_rd03_reprocess_no_dup(self):
        coll, d = self._setup_book()
        r = self.client.post(
            f"/api/knowledge/documents/{d['document_id']}/process")
        self.assertEqual(r.status_code, 200)  # resubmitted (idempotent)
        j = self.wait_job(r.get_json()["job"]["job_id"])
        self.assertEqual(j["status"], "succeeded")
        db = sqlite3.connect(self.db_path())
        try:
            self.assertEqual(db.execute(
                "SELECT COUNT(*) FROM knowledge_works").fetchone()[0], 1)
            self.assertEqual(db.execute(
                "SELECT COUNT(*) FROM knowledge_editions").fetchone()[0], 1)
        finally:
            db.close()

    def test_rd04_hierarchy_detail(self):
        coll, d = self._setup_book()
        r = self.client.get(f"/api/knowledge/works/{d['work_id']}")
        self.assertEqual(r.status_code, 200)
        j = r.get_json()
        self.assertEqual(j["work"]["work_id"], d["work_id"])
        self.assertEqual(len(j["editions"]), 1)
        self.assertEqual(j["editions"][0]["edition_id"], d["edition_id"])
        self.assertEqual(len(j["documents"]), 1)
        self.assertEqual(j["documents"][0]["document_id"], d["document_id"])
        # edition detail: documents + empty volumes
        r2 = self.client.get(f"/api/knowledge/editions/{d['edition_id']}")
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(len(r2.get_json()["documents"]), 1)
        self.assertEqual(r2.get_json()["volumes"], [])
        # unknown ids -> 404
        self.assertEqual(
            self.client.get("/api/knowledge/works/w-nosuch").status_code, 404)
        self.assertEqual(
            self.client.get("/api/knowledge/editions/e-nosuch").status_code, 404)
        self.assertEqual(
            self.client.get("/api/knowledge/volumes/v-nosuch").status_code, 404)
        # list works: search by title
        r3 = self.client.get("/api/knowledge/works", query_string={"search": "آزمون"})
        self.assertEqual(r3.get_json()["total"], 1)
        r4 = self.client.get("/api/knowledge/works", query_string={"search": "zzz"})
        self.assertEqual(r4.get_json()["total"], 0)


# ────────────────────────────────────────────────────────────────────────────
# RD-05 — registry create (idempotent) + entity metadata validation
# ────────────────────────────────────────────────────────────────────────────

class TestRD05_CreateAndValidate(Base):
    def setUp(self):
        super().setUp()
        self.login()

    def test_rd05a_work_idempotent(self):
        payload = {"title": "الموجات", "author": "میرداماد", "language": "fa"}
        r1 = self.client.post("/api/knowledge/works", json=payload)
        self.assertEqual(r1.status_code, 201, r1.get_data(as_text=True))
        w1 = r1.get_json()
        self.assertTrue(w1["created"])
        expected = short_id("w", "الموجات|میرداماد")
        self.assertEqual(w1["work"]["work_id"], expected)
        r2 = self.client.post("/api/knowledge/works", json=payload)
        w2 = r2.get_json()
        self.assertFalse(w2["created"])
        self.assertEqual(w2["work"]["work_id"], expected)
        # explicit key wins over biblio
        r3 = self.client.post("/api/knowledge/works",
                              json={"key": "custom-key"})
        self.assertEqual(r3.get_json()["work"]["work_id"],
                         short_id("w", "custom-key"))
        # missing everything -> 400
        self.assertEqual(self.client.post(
            "/api/knowledge/works", json={}).status_code, 400)

    def test_rd05b_entity_metadata_validation(self):
        r = self.client.post("/api/knowledge/metadata/fields", json={
            "scope": "work", "field_key": "work_genre",
            "display_name": "ژانر اثر"})
        self.assertEqual(r.status_code, 201, r.get_data(as_text=True))
        field_id = r.get_json()["field"]["field_id"]
        # unknown work -> 404
        r = self.client.post("/api/knowledge/metadata/values", json={
            "field_key": "work_genre", "value": "فلسفه",
            "work_id": "w-nosuch"})
        self.assertEqual(r.status_code, 404)
        # invalid scope -> 400
        r = self.client.post("/api/knowledge/metadata/fields", json={
            "scope": "chapter", "field_key": "x", "display_name": "x"})
        self.assertEqual(r.status_code, 400)
        # unknown field with work_id -> 404
        r = self.client.post("/api/knowledge/metadata/values", json={
            "field_key": "nope", "value": "x", "work_id": "w-12345678"})
        self.assertEqual(r.status_code, 404)
        self.assertTrue(field_id)


# ────────────────────────────────────────────────────────────────────────────
# RD-06 — metadata scope chain + resolve precedence
# ────────────────────────────────────────────────────────────────────────────

class TestRD06_Resolve(Base):
    def setUp(self):
        super().setUp()
        self.login()

    def _def_field(self, key, scope, cid=None):
        r = self.client.post("/api/knowledge/metadata/fields", json={
            "scope": scope, "field_key": key,
            "display_name": f"فیلد {key}",
            **({"collection_id": cid} if cid else {})})
        self.assertEqual(r.status_code, 201, r.get_data(as_text=True))
        return r.get_json()["field"]["field_id"]

    def _set(self, key, value, **ctx):
        r = self.client.post("/api/knowledge/metadata/values", json={
            "field_key": key, "value": value, **ctx})
        self.assertEqual(r.status_code, 200, r.get_data(as_text=True))
        return r.get_json()

    def test_rd06_chain(self):
        coll = self.make_collection()
        cid = coll["collection_id"]
        # processed book (fixture: no volume in front matter)
        r = self.upload(coll, self.make_book())
        doc_id = r.get_json()["document"]["document_id"]
        self.process_doc(doc_id)
        d = self.client.get(
            f"/api/knowledge/documents/{doc_id}").get_json()["document"]
        wid, eid = d["work_id"], d["edition_id"]

        self._def_field("genre", "collection", cid)
        self._def_field("genre", "work")
        self._def_field("genre", "edition")
        self._def_field("genre", "document")
        self._set("genre", "فلسفه کالکشن", collection_id=cid)
        self._set("genre", "فلسفه اثر", work_id=wid)
        self._set("genre", "فلسفه ویرایش", edition_id=eid, work_id=wid)
        self._set("genre", "فلسفه سند", document_id=doc_id)

        # resolve by document_id: document wins for genre
        r = self.client.get("/api/knowledge/metadata/resolve",
                            query_string={"document_id": doc_id})
        self.assertEqual(r.status_code, 200, r.get_data(as_text=True))
        j = r.get_json()
        self.assertEqual(j["resolved"]["genre"], "فلسفه سند")
        self.assertEqual(j["sources"]["genre"], "document")
        self.assertEqual(j["context"]["work_id"], wid)
        # raw rows carried per scope
        self.assertTrue(any(v["value"] == "فلسفه ویرایش"
                            for v in j["raw"]["edition"]))
        self.assertTrue(any(v["value"] == "فلسفه اثر"
                            for v in j["raw"]["work"]))

        # remove the document value -> edition wins (via API delete)
        vals = self.client.get("/api/knowledge/metadata/values",
                               query_string={"document_id": doc_id}).get_json()
        vid = next(v["value_id"] for v in vals["values"]
                   if v["value"] == "فلسفه سند")
        self.assertEqual(self.client.delete(
            f"/api/knowledge/metadata/values/{vid}").status_code, 200)
        j2 = self.client.get("/api/knowledge/metadata/resolve",
                             query_string={"document_id": doc_id}).get_json()
        self.assertEqual(j2["resolved"]["genre"], "فلسفه ویرایش")
        self.assertEqual(j2["sources"]["genre"], "edition")

        # resolve by work_id only (no document) -> work value
        j3 = self.client.get("/api/knowledge/metadata/resolve",
                             query_string={"work_id": wid}).get_json()
        self.assertEqual(j3["resolved"]["genre"], "فلسفه اثر")
        self.assertEqual(j3["sources"]["genre"], "work")

        # unknown document -> 404 ; no context at all -> 400
        self.assertEqual(self.client.get(
            "/api/knowledge/metadata/resolve",
            query_string={"document_id": "d-nosuch"}).status_code, 404)
        self.assertEqual(self.client.get(
            "/api/knowledge/metadata/resolve").status_code, 400)

    def test_rd06_field_default_layer(self):
        coll = self.make_collection()
        cid = coll["collection_id"]
        r = self.client.post("/api/knowledge/metadata/fields", json={
            "scope": "collection", "field_key": "license",
            "display_name": "لایسنس", "collection_id": cid,
            "default_value": "CC-BY-4.0"})
        self.assertEqual(r.status_code, 201, r.get_data(as_text=True))
        j = self.client.get("/api/knowledge/metadata/resolve",
                            query_string={"collection_id": cid}).get_json()
        self.assertEqual(j["resolved"]["license"], "CC-BY-4.0")
        self.assertEqual(j["sources"]["license"], "field_default")


# ────────────────────────────────────────────────────────────────────────────
# RD-07 — values list filters by entity ids
# ────────────────────────────────────────────────────────────────────────────

class TestRD07_ValueFilters(Base):
    def setUp(self):
        super().setUp()
        self.login()

    def test_rd07_entity_filters(self):
        r = self.client.post("/api/knowledge/works",
                             json={"title": "منطق", "author": "خواجه نظام‌الحکمه"})
        wid = r.get_json()["work"]["work_id"]
        re_ = self.client.post(
            f"/api/knowledge/works/{wid}/editions",
            json={"publisher": "انتشارات قلم"})
        eid = re_.get_json()["edition"]["edition_id"]
        self._def("work_note", "work")
        self._def("edition_note", "edition")
        self._set("work_note", "یادداشت اثر", work_id=wid)
        self._set("edition_note", "یادداشت ویرایش", edition_id=eid, work_id=wid)

        jw = self.client.get("/api/knowledge/metadata/values",
                             query_string={"work_id": wid}).get_json()
        self.assertTrue(any(v["value"] == "یادداشت اثر" for v in jw["values"]))
        self.assertFalse(any(v["value"] == "یادداشت ویرایش"
                             for v in jw["values"]))
        je = self.client.get("/api/knowledge/metadata/values",
                             query_string={"edition_id": eid}).get_json()
        self.assertTrue(any(v["value"] == "یادداشت ویرایش"
                            for v in je["values"]))
        self.assertFalse(any(v["value"] == "یادداشت اثر"
                             for v in je["values"]))
        # volume filter: empty for a volume with no values
        jv = self.client.get("/api/knowledge/metadata/values",
                             query_string={"volume_id": "v-nosuch"}).get_json()
        self.assertEqual(jv["values"], [])

    def _def(self, key, scope):
        r = self.client.post("/api/knowledge/metadata/fields", json={
            "scope": scope, "field_key": key, "display_name": key})
        self.assertEqual(r.status_code, 201, r.get_data(as_text=True))

    def _set(self, key, value, **ctx):
        r = self.client.post("/api/knowledge/metadata/values", json={
            "field_key": key, "value": value, **ctx})
        self.assertEqual(r.status_code, 200, r.get_data(as_text=True))


if __name__ == "__main__":
    unittest.main(verbosity=2)

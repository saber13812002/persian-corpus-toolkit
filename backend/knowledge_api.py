"""Corpus Knowledge Studio — Collections, Word Library, Metadata & Work
Registry (PCM-14A/B/D).

The «استودیوی دانش» backend. Everything here is ADDITIVE (AGENTS.md rule 2):

  - new tables only (knowledge_collections, knowledge_collection_documents,
    knowledge_index_builds, knowledge_jobs, knowledge_metadata_fields,
    knowledge_metadata_values, knowledge_import_batches);
    column additions via guarded ALTER TABLE ADD COLUMN + backfill, never
    DROP/RENAME/type change;
  - read+write APIs under /api/knowledge/*, all behind the PCM-09 auth
    (same session model as /api/dashboard/*);
  - the extension write APIs and all existing endpoints are untouched.

Word Factory (PCM-13) is REUSED, never re-implemented:
  factory.service.DocumentProcessingService  (DOCX -> blocks/quality/manifest)
The studio stores:
  - the original DOCX (data/knowledge/files/<sha12>/<file_id>.docx)
  - the factory output (data/knowledge/out/<file_id>/...)
  - the registry + metadata in SQLite (source of truth)
Elasticsearch indexing is a LATER phase (PCM-14D); compatibility with the
previous book index is reported as NOT VERIFIED (no local PCT ES exists —
audit 2026-10-26, s52: no 9200/9300 listeners, no ES container).

Naming contract (PCM-14 §4):
  display name (Persian)  : کتابخانه علوم عقلی   (independent, may change)
  collection slug         : oloom-aqli           (technical, stable, unique)
  collection id           : c-<sha256(slug)[:8]> (deterministic)
  index alias             : pct-col-oloom-aqli
  physical index          : pct-col-oloom-aqli-v0001 (PCM-14D)

Renaming the display name never touches id/slug/alias.
"""
import hashlib
import json
import os
import re
import shutil
import threading
import time
import unicodedata

from flask import Response, jsonify, request

from auth import make_require_auth

from factory.models import short_id  # deterministic w-/e-/v- ids (PCM-14D)

SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
SLUG_MAX = 64
NAME_MAX = 200
DESC_MAX = 2000

INDEXING_STATUSES = ("none", "building", "ready", "error")
VALIDATION_STATUSES = ("pending", "valid", "invalid")
ACCESS_POLICIES = ("open", "auth", "keys")

# PCM-14B — document lifecycle (spec §6: no ambiguous 'success')
DOC_STATUSES = (
    "uploaded", "validating", "parsing", "parsed", "needs_review",
    "approved", "indexing", "indexed", "failed",
)
FIELD_TYPES = ("string", "number", "boolean", "date", "url", "enum", "json")
# PCM-14D — metadata can also be scoped to the Work/Edition/Volume entities.
FIELD_SCOPES = ("collection", "batch", "document", "work", "edition", "volume")

MAX_UPLOAD_BYTES = 50 * (1 << 20)      # 50 MB per DOCX
MAX_FILES_PER_BATCH = 100
BLOCKS_PAGE = 200

# PCM-12 job contract (spec §13): persistent, recoverable, idempotent.
JOB_STATUSES = ("pending", "running", "succeeded", "failed", "interrupted")


def _now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _collection_id(slug):
    """Deterministic collection id from the stable technical slug."""
    return "c-" + hashlib.sha256(slug.encode("utf-8")).hexdigest()[:8]


def _index_alias(slug):
    return "pct-col-" + slug


def _doc_id(collection_id, sha256_hex):
    """Deterministic per-(collection, content) document id:
    d-<sha256("<cid>:<filesha>")[:12]>.

    PCM-20.9 mission 1.6 — `document_id` is UNIQUE globally, so a
    content-only id (the old d-<sha8>) turned "the same file in a second
    collection" into a hard constraint violation (500 on the batch
    upload). The id is now a pure function of (collection_id, sha256):
    retries are idempotent, and the per-collection business key
    (collection_id, sha256) is unchanged. Legacy rows keep their old
    ids (backfill is untouched); they are still found by the
    (collection_id, sha256) duplicate check.
    """
    return "d-" + hashlib.sha256(
        f"{collection_id}:{sha256_hex}".encode("utf-8")).hexdigest()[:12]


# ---------------------------------------------------------------------------
# Data dir (uploaded originals + factory outputs)
# ---------------------------------------------------------------------------

def knowledge_data_dir():
    """Writable store for DOCX originals + Word Factory outputs.

    Production (docker): /data-files/knowledge (bind-mounted ./data,
    gitignored). Local dev: <repo>/data/knowledge (gitignored). Never on the
    DB bind-mount path, so a DB backup never needs to carry files.
    """
    d = os.environ.get("PCT_KNOWLEDGE_DATA_DIR", "").strip()
    if not d:
        d = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "..", "data", "knowledge")
    d = os.path.abspath(d)
    for sub in ("files", "out"):
        os.makedirs(os.path.join(d, sub), exist_ok=True)
    return d


def _stored_file_path(sha256_hex: str, file_id: str, ext: str):
    return os.path.join(knowledge_data_dir(), "files", sha256_hex[:12],
                        f"{file_id}{ext or '.docx'}")


def factory_out_dir(file_id: str):
    return os.path.join(knowledge_data_dir(), "out", file_id)


# ---------------------------------------------------------------------------
# Schema (additive migration)
# ---------------------------------------------------------------------------

def ensure_knowledge_schema(db):
    """Create the studio tables if absent (idempotent, additive only)."""
    db.executescript("""
    CREATE TABLE IF NOT EXISTS knowledge_collections (
        id                  INTEGER PRIMARY KEY AUTOINCREMENT,
        collection_id       TEXT NOT NULL UNIQUE,
        name                TEXT NOT NULL,
        slug                TEXT NOT NULL UNIQUE,
        description         TEXT,
        subject             TEXT,
        language            TEXT NOT NULL DEFAULT 'fa',
        collection_version  INTEGER NOT NULL DEFAULT 1,
        schema_version      TEXT NOT NULL DEFAULT 's-1',
        normalization_version TEXT NOT NULL DEFAULT 'n-1',
        chunking_version    TEXT NOT NULL DEFAULT 'c-1',
        es_alias            TEXT NOT NULL UNIQUE,
        current_index_build TEXT,
        book_count          INTEGER NOT NULL DEFAULT 0,
        chunk_count         INTEGER NOT NULL DEFAULT 0,
        indexing_status     TEXT NOT NULL DEFAULT 'none',
        validation_status   TEXT NOT NULL DEFAULT 'pending',
        access_policy       TEXT NOT NULL DEFAULT 'auth',
        created_at          TEXT NOT NULL,
        updated_at          TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS knowledge_collection_documents (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        collection_id TEXT NOT NULL,
        document_id   TEXT NOT NULL UNIQUE,
        file_name     TEXT,
        relative_path TEXT,
        sha256        TEXT NOT NULL,
        file_size     INTEGER NOT NULL DEFAULT 0,
        file_id       TEXT,
        work_id       TEXT,
        edition_id    TEXT,
        volume_id     TEXT,
        status        TEXT NOT NULL DEFAULT 'uploaded',
        blocks_count  INTEGER NOT NULL DEFAULT 0,
        chars_count   INTEGER NOT NULL DEFAULT 0,
        quality_status TEXT,
        quality_score REAL,
        parser_version TEXT,
        norm_version  TEXT,
        out_dir       TEXT,
        error         TEXT,
        created_at    TEXT NOT NULL,
        updated_at    TEXT NOT NULL,
        UNIQUE (collection_id, sha256)
    );
    CREATE TABLE IF NOT EXISTS knowledge_index_builds (
        iv_id          TEXT PRIMARY KEY,
        collection_id  TEXT NOT NULL,
        es_index       TEXT NOT NULL,
        es_alias       TEXT NOT NULL,
        schema_version TEXT NOT NULL,
        norm_version   TEXT,
        chunking_version TEXT,
        chunk_count    INTEGER NOT NULL DEFAULT 0,
        status         TEXT NOT NULL DEFAULT 'building',
        created_at     TEXT NOT NULL,
        completed_at   TEXT
    );
    CREATE TABLE IF NOT EXISTS knowledge_jobs (
        job_id         TEXT PRIMARY KEY,
        job_key        TEXT NOT NULL UNIQUE,
        kind           TEXT NOT NULL,
        collection_id  TEXT,
        batch_id       TEXT,
        status         TEXT NOT NULL DEFAULT 'pending',
        stage          TEXT,
        progress       INTEGER NOT NULL DEFAULT 0,
        total          INTEGER NOT NULL DEFAULT 0,
        retry_count    INTEGER NOT NULL DEFAULT 0,
        error          TEXT,
        idempotency_key TEXT,
        created_at     TEXT NOT NULL,
        updated_at     TEXT NOT NULL,
        completed_at   TEXT
    );
    CREATE TABLE IF NOT EXISTS knowledge_import_batches (
        batch_id       TEXT PRIMARY KEY,
        collection_id  TEXT NOT NULL,
        folder_name    TEXT,
        file_count     INTEGER NOT NULL DEFAULT 0,
        processed_count INTEGER NOT NULL DEFAULT 0,
        failed_count   INTEGER NOT NULL DEFAULT 0,
        status         TEXT NOT NULL DEFAULT 'planned',
        created_at     TEXT NOT NULL,
        updated_at     TEXT NOT NULL
    );
    -- PCM-20.9 Stage A — persisted batch import plan (one row per planned
    -- file). This is what makes multi-import reliable: the plan survives
    -- the HTTP response, and the per-file upload endpoint
    -- (POST /import/batches/<id>/files) matches real uploads against it by
    -- SHA-256. Statuses: pending / uploaded / duplicate / invalid_* /
    -- size_mismatch.
    CREATE TABLE IF NOT EXISTS knowledge_batch_files (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        batch_id      TEXT NOT NULL,
        seq           INTEGER NOT NULL,
        file_name     TEXT NOT NULL,
        sha256        TEXT,
        size_bytes    INTEGER NOT NULL DEFAULT 0,
        status        TEXT NOT NULL DEFAULT 'pending',
        document_id   TEXT,
        error         TEXT,
        created_at    TEXT NOT NULL,
        updated_at    TEXT NOT NULL,
        UNIQUE (batch_id, seq)
    );
    CREATE INDEX IF NOT EXISTS idx_kbf_batch
        ON knowledge_batch_files(batch_id);
    CREATE INDEX IF NOT EXISTS idx_kbf_sha
        ON knowledge_batch_files(batch_id, sha256);
    -- NOTE: idx on knowledge_collection_documents(batch_id) is created in
    -- _ensure_document_columns, AFTER the batch_id column itself exists.
    -- NOTE: scope columns use NOT NULL sentinels ('__global__' / '') because
    -- SQLite UNIQUE constraints disallow expressions and treat NULLs as
    -- distinct — sentinels make dedup exact and queryable.
    CREATE TABLE IF NOT EXISTS knowledge_metadata_fields (
        field_id       TEXT PRIMARY KEY,
        scope          TEXT NOT NULL,
        collection_id  TEXT NOT NULL DEFAULT '__global__',
        field_key      TEXT NOT NULL,
        display_name   TEXT NOT NULL,
        data_type      TEXT NOT NULL DEFAULT 'string',
        required       INTEGER NOT NULL DEFAULT 0,
        default_value  TEXT,
        validation_rules TEXT,
        searchable     INTEGER NOT NULL DEFAULT 1,
        schema_version TEXT NOT NULL DEFAULT 'm-1',
        enabled        INTEGER NOT NULL DEFAULT 1,
        created_at     TEXT NOT NULL,
        updated_at     TEXT NOT NULL,
        UNIQUE (scope, collection_id, field_key)
    );
    CREATE TABLE IF NOT EXISTS knowledge_metadata_values (
        value_id      INTEGER PRIMARY KEY AUTOINCREMENT,
        field_id      TEXT NOT NULL,
        scope         TEXT NOT NULL,
        collection_id TEXT NOT NULL DEFAULT '',
        batch_id      TEXT NOT NULL DEFAULT '',
        document_id   TEXT NOT NULL DEFAULT '',
        work_id       TEXT NOT NULL DEFAULT '',
        edition_id    TEXT NOT NULL DEFAULT '',
        volume_id     TEXT NOT NULL DEFAULT '',
        value         TEXT,
        source        TEXT NOT NULL DEFAULT 'user',
        version       INTEGER NOT NULL DEFAULT 1,
        edited_at     TEXT NOT NULL,
        edited_by     TEXT,
        UNIQUE (scope, collection_id, batch_id, document_id, field_id,
                work_id, edition_id, volume_id)
    );
    CREATE INDEX IF NOT EXISTS idx_kcol_updated
        ON knowledge_collections(updated_at DESC);
    CREATE INDEX IF NOT EXISTS idx_kcol_documents
        ON knowledge_collection_documents(collection_id, status);
    CREATE INDEX IF NOT EXISTS idx_kbuilds_collection
        ON knowledge_index_builds(collection_id, created_at DESC);
    CREATE INDEX IF NOT EXISTS idx_kjobs_status
        ON knowledge_jobs(status, created_at);
    CREATE INDEX IF NOT EXISTS idx_kmeta_scope
        ON knowledge_metadata_fields(scope, collection_id, enabled);
    CREATE INDEX IF NOT EXISTS idx_kmv_doc
        ON knowledge_metadata_values(document_id, field_id);
    -- PCM-14D — Work/Edition/Volume entity registry (see ERD in
    -- docs/PCM-14D-WORK-REGISTRY.md). Ids reuse the deterministic
    -- short_id scheme of the Word Factory (w-/e-/v-<sha8>).
    CREATE TABLE IF NOT EXISTS knowledge_works (
        work_id          TEXT PRIMARY KEY,
        title            TEXT,
        author           TEXT,
        subject          TEXT,
        language         TEXT,
        document_count   INTEGER NOT NULL DEFAULT 0,
        source           TEXT NOT NULL DEFAULT 'factory',
        created_at       TEXT NOT NULL,
        updated_at       TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS knowledge_editions (
        edition_id       TEXT PRIMARY KEY,
        work_id          TEXT NOT NULL,
        publisher        TEXT,
        publish_year     TEXT,
        edition_label    TEXT,
        language         TEXT,
        document_count   INTEGER NOT NULL DEFAULT 0,
        source           TEXT NOT NULL DEFAULT 'factory',
        created_at       TEXT NOT NULL,
        updated_at       TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS knowledge_volumes (
        volume_id        TEXT PRIMARY KEY,
        edition_id       TEXT NOT NULL,
        work_id          TEXT NOT NULL,
        volume_no        INTEGER,
        label            TEXT,
        document_count   INTEGER NOT NULL DEFAULT 0,
        source           TEXT NOT NULL DEFAULT 'factory',
        created_at       TEXT NOT NULL,
        updated_at       TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_ked_work ON knowledge_editions(work_id);
    CREATE INDEX IF NOT EXISTS idx_kvol_edition ON knowledge_volumes(edition_id);
    CREATE INDEX IF NOT EXISTS idx_kvol_work ON knowledge_volumes(work_id);
    -- PCM-15 — persistent per-file processing queue (single source of truth
    -- for file-level stage/attempts/timings/last-error/artifact path).
    -- One row per (collection, file_key); file_key == the deterministic
    -- Word Factory file_id (f-<sha8>). Statuses: pending / running /
    -- succeeded / needs_review / failed. `stage` is the last COMPLETED
    -- (safe) stage — on failure it is the resume anchor (retry = idempotent
    -- re-run over the sha-verified unchanged input, see docs).
    CREATE TABLE IF NOT EXISTS knowledge_file_queue (
        file_key         TEXT NOT NULL,
        document_id      TEXT NOT NULL,
        collection_id    TEXT NOT NULL,
        file_name        TEXT,
        sha256           TEXT NOT NULL,
        status           TEXT NOT NULL DEFAULT 'pending',
        stage            TEXT,
        attempts         INTEGER NOT NULL DEFAULT 0,
        last_error       TEXT,
        stage_started_at TEXT,
        finished_at      TEXT,
        duration_ms      INTEGER,
        out_dir          TEXT,
        created_at       TEXT NOT NULL,
        updated_at       TEXT NOT NULL,
        PRIMARY KEY (collection_id, file_key)
    );
    CREATE INDEX IF NOT EXISTS idx_kfq_status ON knowledge_file_queue(status);
    CREATE INDEX IF NOT EXISTS idx_kfq_coll ON knowledge_file_queue(collection_id, status);
    -- PCM-15 — pause/resume control (scope = 'batch:<batch_id>').
    CREATE TABLE IF NOT EXISTS knowledge_queue_control (
        scope        TEXT PRIMARY KEY,
        paused       INTEGER NOT NULL DEFAULT 0,
        updated_at   TEXT NOT NULL
    );
    -- PCM-20.9 Stage C — corpus schema versions (immutable design & mapping
    -- of the per-block document schema). A version is created as a draft
    -- (status='draft'), validated against the REAL blocks.jsonl of the
    -- collection's processed documents, and then approved (status='approved',
    -- approved_at set). Once approved a version's fields JSON is never
    -- modified — fixes mean a NEW version (immutable versioning).
    CREATE TABLE IF NOT EXISTS knowledge_schema_versions (
        schema_id    TEXT PRIMARY KEY,        -- sv-<cid>-<n>: global PK,
                                              -- <n> is the per-collection
                                              -- version (1, 2, 3, ...)
        collection_id TEXT NOT NULL,
        version      INTEGER NOT NULL,        -- 1, 2, 3, ... per collection
        status       TEXT NOT NULL DEFAULT 'draft',  -- draft/approved
        description  TEXT,
        fields       TEXT NOT NULL,           -- JSON: list of field definitions
        validation   TEXT,                    -- JSON: last validation report
        approved_at  TEXT,
        created_at   TEXT NOT NULL,
        updated_at   TEXT NOT NULL,
        UNIQUE (collection_id, version)
    );
    CREATE INDEX IF NOT EXISTS idx_ksv_coll
        ON knowledge_schema_versions(collection_id, version DESC);
    -- PCM-20.9 Final — release bundle registry. One row per built release:
    -- a content-addressed zip (corpus c-1 + per-doc dumps d-1 + chained
    -- manifest + README) stored under <data>/releases/<release_id>/.
    -- release_id = rel-<sha256(collection_id:content_sha256)[:8]> (deterministic).
    -- rag_status: blocked (PCT_RAG_INGEST_URL absent -> honest, no call) /
    -- success (ingest confirmed) / failed (ingest attempted, error recorded).
    CREATE TABLE IF NOT EXISTS knowledge_releases (
        release_id     TEXT PRIMARY KEY,      -- rel-<sha8>
        collection_id  TEXT NOT NULL,
        build_iv_id    TEXT,                  -- the Stage D build it came from
        content_sha256 TEXT NOT NULL,         -- corpus archive sha (identity)
        zip_path       TEXT NOT NULL,         -- absolute, under data dir
        zip_sha256     TEXT NOT NULL,
        size_bytes     INTEGER NOT NULL DEFAULT 0,
        manifest       TEXT NOT NULL,         -- JSON: release-manifest.json
        rag_status     TEXT NOT NULL DEFAULT 'blocked',
        created_at     TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_krel_coll
        ON knowledge_releases(collection_id, created_at DESC);
    -- PCM-20.9 Final — append-only audit trail. Every pipeline/acceptance/
    -- approve/release action is recorded (never updated, never deleted).
    CREATE TABLE IF NOT EXISTS knowledge_audit_log (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        ts            TEXT NOT NULL,
        actor         TEXT NOT NULL,          -- sess-<sha8> | worker | system
        collection_id TEXT,
        stage         TEXT NOT NULL,          -- import/build/acceptance/release/...
        action        TEXT NOT NULL,
        status        TEXT NOT NULL,          -- ok / fail / blocked
        detail_json   TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_kaudit_coll
        ON knowledge_audit_log(collection_id, ts);
    """)
    db.commit()
    _ensure_document_columns(db)
    _ensure_registry_columns(db)
    _ensure_build_columns(db)


def _ensure_registry_columns(db):
    """PCM-14D — additive upgrades for pre-existing DBs (PCM-14B -> PCM-14D).

    Same guarded pattern as _ensure_document_columns: probe
    PRAGMA table_info, ALTER TABLE ADD COLUMN only what is missing,
    backfill only where data is absent. Never alters an existing column.

    - knowledge_metadata_fields  += work_id/edition_id/volume_id ('' sentinel)
    - knowledge_metadata_values  += work_id/edition_id/volume_id ('' sentinel)
    - knowledge_works/editions/volumes backfilled from the denormalized
      ids already stored on knowledge_collection_documents (plus the
      biblio extracted by the factory into document.json, when present).
    """
    existing = {r[1] for r in db.execute(
        "PRAGMA table_info(knowledge_metadata_fields)").fetchall()}
    for col, decl in (("work_id", "TEXT NOT NULL DEFAULT ''"),
                      ("edition_id", "TEXT NOT NULL DEFAULT ''"),
                      ("volume_id", "TEXT NOT NULL DEFAULT ''")):
        if col not in existing:
            db.execute(f"ALTER TABLE knowledge_metadata_fields "
                       f"ADD COLUMN {col} {decl}")
    existing_v = {r[1] for r in db.execute(
        "PRAGMA table_info(knowledge_metadata_values)").fetchall()}
    for col, decl in (("work_id", "TEXT NOT NULL DEFAULT ''"),
                      ("edition_id", "TEXT NOT NULL DEFAULT ''"),
                      ("volume_id", "TEXT NOT NULL DEFAULT ''")):
        if col not in existing_v:
            db.execute(f"ALTER TABLE knowledge_metadata_values "
                       f"ADD COLUMN {col} {decl}")

    # Backfill the entity registry from documents that were already
    # processed (status in parsed/needs_review/approved/indexed carry ids).
    _backfill_registry(db)
    db.commit()


def _backfill_registry(db):
    """Idempotent registry backfill (no-op when rows already exist).

    The denormalized work_id/edition_id/volume_id columns on
    knowledge_collection_documents are the source of truth; biblio text
    is enriched best-effort from the factory's document.json when the
    file is still on disk. Never overwrites existing registry rows.
    """
    rows = db.execute(
        """SELECT d.work_id, d.edition_id, d.volume_id, d.out_dir,
                  d.file_id, COUNT(*) AS n
           FROM knowledge_collection_documents d
           WHERE d.work_id IS NOT NULL AND d.work_id != ''
           GROUP BY d.work_id, d.edition_id, d.volume_id, d.out_dir,
                    d.file_id""").fetchall()
    for r in rows:
        biblio = _read_factory_biblio(r["file_id"]) if r["out_dir"] else {}
        w = (biblio.get("title"), biblio.get("author"))
        e = (biblio.get("publisher"), biblio.get("publish_year"))
        db.execute(
            """INSERT OR IGNORE INTO knowledge_works
               (work_id, title, author, document_count, source,
                created_at, updated_at)
               VALUES (?, ?, ?, ?, 'factory', ?, ?)""",
            (r["work_id"], w[0], w[1], r["n"], _now(), _now()))
        if r["edition_id"]:
            db.execute(
                """INSERT OR IGNORE INTO knowledge_editions
                   (edition_id, work_id, publisher, publish_year,
                    document_count, source, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, 'factory', ?, ?)""",
                (r["edition_id"], r["work_id"], e[0], e[1], r["n"],
                 _now(), _now()))
        if r["volume_id"]:
            db.execute(
                """INSERT OR IGNORE INTO knowledge_volumes
                   (volume_id, edition_id, work_id, volume_no,
                    document_count, source, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, 'factory', ?, ?)""",
                (r["volume_id"], r["edition_id"] or "", r["work_id"],
                 biblio.get("volume"), r["n"], _now(), _now()))


def _read_factory_biblio(file_id):
    """Best-effort biblio read from the factory's document.json (absent -> {})."""
    if not file_id:
        return {}
    try:
        p = os.path.join(factory_out_dir(file_id), "document.json")
        with open(p, encoding="utf-8") as fh:
            d = json.load(fh)
    except (OSError, ValueError):
        return {}
    meta = d.get("metadata") or {}
    fields = meta.get("fields") or {}

    def _val(key):
        v = (fields.get(key) or {}).get("value")
        return str(v).strip() if v is not None else None

    vol = meta.get("volume")
    return {
        "title": _val("title"),
        "author": _val("author"),
        "publisher": _val("publisher"),
        "publish_year": _val("publish_year"),
        "volume": vol if isinstance(vol, int) else None,
    }


def _upsert_registry_rows(conn, doc):
    """PCM-14D — sync the entity registry after a successful WF run.

    Purely additive: INSERT OR IGNORE on entity ids (the id is the
    natural key), then a count refresh. Existing rows are never
    rewritten here — user edits to biblio fields win over re-runs.
    """
    biblio = doc.metadata
    title = (biblio.fields.get("title") or None)
    author = (biblio.fields.get("author") or None)
    publisher = (biblio.fields.get("publisher") or None)
    year = (biblio.fields.get("publish_year") or None)

    def _s(fv):
        return fv.value.strip() if (fv and fv.value) else None

    conn.execute(
        """INSERT OR IGNORE INTO knowledge_works
           (work_id, title, author, document_count, source,
            created_at, updated_at)
           VALUES (?, ?, ?, 1, 'factory', ?, ?)""",
        (doc.work_id, _s(title), _s(author), _now(), _now()))
    conn.execute(
        """UPDATE knowledge_works SET document_count =
               (SELECT COUNT(*) FROM knowledge_collection_documents
                 WHERE work_id = ?),
             updated_at = ?
           WHERE work_id = ?""",
        (doc.work_id, _now(), doc.work_id))
    if doc.edition_id:
        conn.execute(
            """INSERT OR IGNORE INTO knowledge_editions
               (edition_id, work_id, publisher, publish_year,
                document_count, source, created_at, updated_at)
               VALUES (?, ?, ?, ?, 1, 'factory', ?, ?)""",
            (doc.edition_id, doc.work_id, _s(publisher), _s(year),
             _now(), _now()))
        conn.execute(
            """UPDATE knowledge_editions SET document_count =
                   (SELECT COUNT(*) FROM knowledge_collection_documents
                     WHERE edition_id = ?),
                 updated_at = ?
               WHERE edition_id = ?""",
            (doc.edition_id, _now(), doc.edition_id))
    if doc.volume_id:
        conn.execute(
            """INSERT OR IGNORE INTO knowledge_volumes
               (volume_id, edition_id, work_id, volume_no,
                document_count, source, created_at, updated_at)
               VALUES (?, ?, ?, ?, 1, 'factory', ?, ?)""",
            (doc.volume_id, doc.edition_id or "", doc.work_id,
             biblio.volume_no, _now(), _now()))
        conn.execute(
            """UPDATE knowledge_volumes SET document_count =
                   (SELECT COUNT(*) FROM knowledge_collection_documents
                     WHERE volume_id = ?),
                 updated_at = ?
               WHERE volume_id = ?""",
            (doc.volume_id, _now(), doc.volume_id))


def _ensure_document_columns(db):
    """Additive column upgrades for pre-existing DBs (PCM-14A -> PCM-14B).

    Guarded: SQLite has no ADD COLUMN IF NOT EXISTS, so we probe
    PRAGMA table_info and add only what is missing. Never alters an
    existing column (AGENTS.md rule 2).
    """
    existing = {r[1] for r in db.execute(
        "PRAGMA table_info(knowledge_collection_documents)").fetchall()}
    wanted = [
        ("relative_path", "TEXT"),
        ("file_size", "INTEGER NOT NULL DEFAULT 0"),
        ("file_id", "TEXT"),
        ("work_id", "TEXT"),
        ("edition_id", "TEXT"),
        ("volume_id", "TEXT"),
        ("quality_score", "REAL"),
        ("parser_version", "TEXT"),
        ("norm_version", "TEXT"),
        ("out_dir", "TEXT"),
        # PCM-20.9 Stage A — which import batch created this document
        # (NULL = single upload). Additive: pre-existing rows stay NULL.
        ("batch_id", "TEXT"),
    ]
    for col, decl in wanted:
        if col not in existing:
            db.execute(
                f"ALTER TABLE knowledge_collection_documents ADD COLUMN {col} {decl}"
            )
    # PCM-20.9 Stage A — index for batch-scoped queries (only valid once the
    # batch_id column exists, hence here and not in the CREATE script).
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_kcol_documents_batch "
        "ON knowledge_collection_documents(batch_id)")
    # Backfill document_id for pre-14B rows that may have had null/dup ids.
    for r in db.execute(
            "SELECT id, document_id, sha256 FROM knowledge_collection_documents "
            "WHERE document_id IS NULL OR document_id = ''").fetchall():
        db.execute(
            "UPDATE knowledge_collection_documents SET document_id=? WHERE id=?",
            ("d-" + (r[2] or hex(r[0]))[:8], r[0]),
        )
    db.commit()


STUCK_AFTER_MOD = "-10 minutes"  # a live worker always updates within 10 min


def _ensure_build_columns(db):
    """PCM-20.9 Stage D — additive columns for knowledge_index_builds.

    Pre-20.9 rows keep NULL (legacy builds had no canonical corpus / ES
    factory outcome). Guarded PRAGMA-probe + ALTER, never alters an
    existing column (AGENTS.md rule 2).
    """
    existing = {r[1] for r in db.execute(
        "PRAGMA table_info(knowledge_index_builds)").fetchall()}
    wanted = [
        # SHA-256 of the canonical corpus archive (c-1) — the content
        # idempotency key (same content -> REUSED, no second build).
        ("content_sha256", "TEXT"),
        # corpus dir, relative to the knowledge data dir
        ("out_dir", "TEXT"),
        # ES factory outcome: pending / blocked / success / failed
        ("es_index_status", "TEXT"),
        # JSON detail of the ES factory outcome (reason / error / info)
        ("es_detail", "TEXT"),
        # PCM-20.9 Stage E — search-acceptance outcome on the live alias:
        # pass / fail (NULL = never validated)
        ("search_status", "TEXT"),
        # JSON report of the 10-category search acceptance run
        ("search_detail", "TEXT"),
    ]
    for col, decl in wanted:
        if col not in existing:
            db.execute(
                f"ALTER TABLE knowledge_index_builds ADD COLUMN {col} {decl}")
    db.commit()


def _recover_interrupted(db):
    """PCM-13/14 §13 (+PCM-15): after a restart, make stuck state resumable.

    Only rows whose updated_at is OLDER than STUCK_AFTER_MOD are considered
    stuck — a live worker updates its row (job stage/progress, document
    status, queue row) well within that window, so in-flight work is never
    touched.

    - jobs stuck in pending/running   -> interrupted (retryable)
    - documents stuck in parsing      -> uploaded (reprocessable, file intact)
    - batches stuck in 'processing'   -> planned (re-runnable)
    - queue rows stuck in 'running'   -> pending (re-queued; the recorded
      `stage` = last completed safe stage is kept as the resume anchor)
    Idempotent and cheap (no-op UPDATEs when nothing is stuck).
    """
    db.execute(
        """UPDATE knowledge_jobs SET status='interrupted',
             error=COALESCE(error,'') || ' [worker interrupted]'
           WHERE status IN ('pending','running')
             AND updated_at < datetime('now', ?)""", (STUCK_AFTER_MOD,))
    db.execute(
        """UPDATE knowledge_collection_documents SET status='uploaded', updated_at=?
           WHERE status IN ('validating','parsing')
             AND updated_at < datetime('now', ?)""", (_now(), STUCK_AFTER_MOD))
    db.execute(
        """UPDATE knowledge_import_batches SET status='planned', updated_at=?
           WHERE status='processing' AND updated_at < datetime('now', ?)""",
        (_now(), STUCK_AFTER_MOD))
    db.execute(
        """UPDATE knowledge_file_queue SET status='pending', updated_at=?
           WHERE status='running' AND updated_at < datetime('now', ?)""",
        (_now(), STUCK_AFTER_MOD))
    db.commit()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _slug_from_name(name):
    """Best-effort Persian→Latin slug seed from the display name.

    The user ALWAYS confirms/edits the slug in the form before submit;
    the server is the source of truth for validity (SLUG_RE). This is a
    convenience prefill, not a commitment.
    """
    t = {
        "آ": "a", "ا": "a", "أ": "a", "إ": "a", "ب": "b", "پ": "p",
        "ت": "t", "ث": "s", "ج": "j", "چ": "ch", "ح": "h", "خ": "kh",
        "د": "d", "ذ": "z", "ر": "r", "ز": "z", "س": "s", "ش": "sh",
        "ص": "s", "ط": "t", "ع": "a", "غ": "gh", "ف": "f", "ق": "q",
        "ک": "k", "گ": "g", "ل": "l", "م": "m", "ن": "n", "و": "v",
        "ه": "h", "ی": "y", "ئ": "y", "ء": "e",
    }
    out = []
    for ch in unicodedata.normalize("NFC", name):
        if ch in t:
            out.append(t[ch])
        elif ch.isascii() and ch.isalnum():
            out.append(ch.lower())
        else:
            out.append("-")
    slug = "".join(out).strip("-")
    slug = re.sub(r"-{2,}", "-", slug)
    return slug[:SLUG_MAX].strip("-")


def _clean_name(value):
    if value is None:
        return None
    value = str(value).strip()
    return value[:NAME_MAX] or None


def _work_key_from_biblio(title, author, sha256):
    """Mirror factory.service work-key derivation so registry-created ids
    match the ids the Word Factory would assign to the same book."""
    t = (str(title or "").strip().lower())
    a = (str(author or "").strip().lower())
    key = f"{t}|{a}"
    if not (t or a):
        key = sha256 or ""
    return key


def _collection_row(db, coll_id):
    return db.execute(
        """SELECT c.*,
                  (SELECT COUNT(*) FROM knowledge_collection_documents d
                    WHERE d.collection_id = c.collection_id
                      AND d.status IN ('parsed','needs_review','approved',
                                       'indexing','indexed')) AS book_count,
                  (SELECT COUNT(*) FROM knowledge_index_builds b
                    WHERE b.collection_id = c.collection_id) AS build_count
           FROM knowledge_collections c WHERE c.id = ?""",
        (coll_id,),
    ).fetchone()


def _refresh_book_count(db, collection_id):
    db.execute(
        """UPDATE knowledge_collections SET
             book_count = (SELECT COUNT(*) FROM knowledge_collection_documents d
                           WHERE d.collection_id = ?
                             AND d.status IN ('parsed','needs_review','approved',
                                              'indexing','indexed')),
             updated_at = ?
           WHERE collection_id = ?""",
        (collection_id, _now(), collection_id))


def _doc_row(db, doc_id):
    return db.execute(
        """SELECT id, document_id, collection_id, file_name, relative_path,
                  sha256, file_size, file_id, work_id, edition_id, volume_id,
                  status, batch_id, blocks_count, chars_count,
                  quality_status, quality_score, parser_version, norm_version,
                  out_dir, error, created_at, updated_at
           FROM knowledge_collection_documents WHERE document_id = ?""",
        (doc_id,),
    ).fetchone()


def _coll_by_id_or_404(db, coll_id):
    row = _collection_row(db, coll_id)
    if not row:
        return None
    return row


# ---------------------------------------------------------------------------
# Job runner (persistent, resumable — spec §13)
# ---------------------------------------------------------------------------

def _job_worker(db_path, job_id):
    """Runs in a background thread; own SQLite connection (WAL)."""
    import sqlite3
    conn = sqlite3.connect(db_path, timeout=60)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("UPDATE knowledge_jobs SET status='running', stage='start', "
                     "updated_at=? WHERE job_id=?", (_now(), job_id))
        conn.commit()
        kind_row = conn.execute(
            "SELECT job_key FROM knowledge_jobs WHERE job_id=?", (job_id,)
        ).fetchone()
        key = kind_row["job_key"]
        fn = _JOB_KINDS.get(key.split(":")[0])
        if fn is None:
            raise RuntimeError(f"unknown job kind {key!r}")
        fn(conn, job_id)
        # PCM-15: a batch job that stops early (user pause) sets its own
        # 'interrupted' state — never overwrite a terminal state set by the
        # kind fn itself.
        # Keep the kind fn's final stage ('reused <iv>', 'es <index>', ...);
        # 'done' only when the kind fn never set one.
        conn.execute(
            "UPDATE knowledge_jobs SET status='succeeded', "
            "stage=COALESCE(stage, 'done'), "
            "updated_at=?, completed_at=? WHERE job_id=? AND status='running'",
            (_now(), _now(), job_id))
        conn.commit()
    except Exception as e:  # noqa: BLE001 — job errors are DATA, not crashes
        conn.execute("UPDATE knowledge_jobs SET status='failed', error=?, "
                     "updated_at=?, completed_at=? WHERE job_id=?",
                     (f"{type(e).__name__}: {e}", _now(), _now(), job_id))
        conn.commit()
    finally:
        conn.close()


def _submit_job(db, job_key, kind, collection_id, batch_id, total=0,
                idempotency_key=None, force_retry=False):
    """Insert a persistent job row and start its worker thread.

    Idempotency: re-submitting the same job_key while the job is still
    pending/running/succeeded returns the existing row and does NOT start
    a second worker. A job in a terminal-but-retryable state (failed,
    interrupted — spec §13 "retryable") is RE-EXECUTED: the row is reset
    to pending and a fresh worker starts; retry_count is bumped.

    PCM-20.9 Stage B: `force_retry=True` also treats a COMPLETED job
    (status='succeeded') as retryable — used by the batch retry-failed
    endpoint, where a successful retry run must not block a later retry.
    """
    now = _now()
    existing = db.execute(
        "SELECT job_id, status, retry_count FROM knowledge_jobs WHERE job_key=?",
        (job_key,)).fetchone()
    if existing:
        states = ("failed", "interrupted")
        if force_retry:
            states = states + ("succeeded",)
        if existing["status"] in states:
            ph = ",".join("?" for _ in states)
            db.execute(
                f"""UPDATE knowledge_jobs
                      SET status='pending', progress=0, stage=NULL, error=NULL,
                          retry_count=retry_count+1, updated_at=?,
                          completed_at=NULL
                    WHERE job_id=? AND status IN ({ph})""",
                (now, existing["job_id"], *states))
            db.commit()
            _start_worker(existing["job_id"])
            return {"job_id": existing["job_id"], "job_key": job_key,
                    "status": "pending"}, True
        db.commit()
        return dict(existing), False
    job_id = "j-" + hashlib.sha256(
        (job_key + now).encode("utf-8")).hexdigest()[:8]
    db.execute(
        """INSERT INTO knowledge_jobs
           (job_id, job_key, kind, collection_id, batch_id, status, progress,
            total, idempotency_key, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, 'pending', 0, ?, ?, ?, ?)""",
        (job_id, job_key, kind, collection_id, batch_id, total,
         idempotency_key, now, now))
    db.commit()
    _start_worker(job_id)
    return {"job_id": job_id, "job_key": job_key, "status": "pending"}, True


def _start_worker(job_id):
    """Spawn the daemon worker thread for a persisted job row."""
    import server  # lazy: server imports this module at startup
    t = threading.Thread(
        target=_job_worker, args=(server.DB_PATH, job_id), daemon=True)
    t.start()


_JOB_KINDS = {}  # kind -> worker fn(conn, job_id); registered below


def _job_progress(conn, job_id, progress, total=None, stage=None):
    conn.execute(
        "UPDATE knowledge_jobs SET progress=?, total=COALESCE(?, total), "
        "stage=?, updated_at=? WHERE job_id=?",
        (progress, total, stage, _now(), job_id))
    conn.commit()


# ---------------------------------------------------------------------------
# PCM-20.9 Final — audit trail (append-only) + guarded RAG ingest
# ---------------------------------------------------------------------------

def _audit_actor():
    """Who is acting, from the CURRENT context (never fabricated).

    - inside a request: 'sess-<sha8>' from the live session cookie;
    - inside a worker thread (no request context): 'worker';
    - otherwise: 'system'.
    """
    try:
        import flask
        if flask.has_request_context():
            tok = request.cookies.get("pct_session", "")
            if tok:
                return "sess-" + hashlib.sha256(
                    tok.encode("utf-8")).hexdigest()[:8]
    except Exception:  # noqa: BLE001 — actor best-effort, never blocks
        pass
    try:
        import threading
        if threading.current_thread() is not threading.main_thread():
            return "worker"
    except Exception:  # noqa: BLE001
        pass
    return "system"


def _audit_log(db, collection_id, stage, action, status, detail=None):
    """Append one row to knowledge_audit_log (append-only, never updated).

    Best-effort: a failed audit write must never break the action it
    records (logged, not raised).
    """
    try:
        db.execute(
            "INSERT INTO knowledge_audit_log "
            "(ts, actor, collection_id, stage, action, status, detail_json) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (_now(), _audit_actor(), collection_id, stage, action, status,
             json.dumps(detail, ensure_ascii=False) if detail is not None
             else None))
        db.commit()
    except Exception:  # noqa: BLE001
        import traceback
        traceback.print_exc()


def _rag_ingest(conn, coll_id, build, release, manifest):
    """Guarded RAG ingest of a release bundle.

    Honest: without PCT_RAG_INGEST_URL (and a token) the result is
    'blocked' (unknown RAG contract — nothing is called, nothing claimed).
    When configured, the release zip is ingested over HTTP and the outcome
    (success / failed + detail) is recorded. Returns (status, detail).
    """
    url = os.environ.get("PCT_RAG_INGEST_URL", "").strip()
    token = os.environ.get("PCT_RAG_INGEST_TOKEN", "").strip()
    if not url:
        return "blocked", ("PCT_RAG_INGEST_URL تنظیم نیست — RAG ingest "
                           "غیرفعال (unknown RAG contract); خروجی release "
                           "لوکال قابل استفاده است")
    try:
        import urllib.request
        payload = json.dumps({
            "kind": "pct-release",
            "contract": manifest["release_contract"],
            "collection_id": coll_id,
            "build_iv_id": build["iv_id"],
            "content_sha256": build["content_sha256"],
            "release_id": release["release_id"],
            "zip_sha256": release["zip_sha256"],
            "path": release["zip_path"],
            "manifest_path": os.path.join(
                os.path.dirname(release["zip_path"]),
                "release-manifest.json"),
            "manifest_sha256": _sha256_file(os.path.join(
                os.path.dirname(release["zip_path"]),
                "release-manifest.json")),
        }).encode("utf-8")
        req = urllib.request.Request(url, data=payload,
                                     method="POST")
        req.add_header("Content-Type", "application/json")
        if token:
            req.add_header("Authorization", "Bearer " + token)
        with urllib.request.urlopen(req, timeout=60) as resp:
            if resp.status >= 300:
                raise RuntimeError(f"HTTP {resp.status}")
        return "success", "ingest request accepted"
    except Exception as e:  # noqa: BLE001 — record, don't crash the release
        return "failed", f"{type(e).__name__}: {e}"


# ---------------------------------------------------------------------------
# PCM-15 — persistent per-file queue (stage/attempts/last-error/timings)
# ---------------------------------------------------------------------------

QUEUE_STATUSES = ("pending", "running", "succeeded", "needs_review", "failed")
STAGE_NAMES = ("intake", "validate", "parse", "structure", "metadata",
               "normalize", "quality", "export")
STAGE_SAFE_ORDER = {name: i for i, name in enumerate(STAGE_NAMES)}


def queue_scope(batch_id):
    """PCM-15 pause/resume control scope for a batch (None = no scope)."""
    return f"batch:{batch_id}" if batch_id else None


def queue_is_paused(conn, scope):
    """True when the given scope exists and is paused."""
    if not scope:
        return False
    r = conn.execute("SELECT paused FROM knowledge_queue_control WHERE scope=?",
                     (scope,)).fetchone()
    return bool(r and r["paused"])


def queue_set_paused(conn, scope, paused, now=None):
    now = now or _now()
    conn.execute(
        """INSERT INTO knowledge_queue_control (scope, paused, updated_at)
           VALUES (?, ?, ?)
           ON CONFLICT(scope) DO UPDATE SET paused=excluded.paused,
               updated_at=excluded.updated_at""",
        (scope, 1 if paused else 0, now))
    conn.commit()


def _queue_row(conn, collection_id, file_key):
    return conn.execute(
        "SELECT * FROM knowledge_file_queue WHERE collection_id=? AND file_key=?",
        (collection_id, file_key)).fetchone()


def _queue_stage_writer(conn, collection_id, file_key, t0):
    """Build the on_stage callback for one queued file.

    The callback records each COMPLETED (safe) stage in the queue row
    immediately (own commit — survives a later mid-pipeline crash). It also
    measures the current stage's duration into the row at each transition,
    so `duration_ms` on failure is the time up to the last safe stage.
    """
    state = {"stage": None, "t": t0}

    def on_stage(stage_name):
        if stage_name not in STAGE_SAFE_ORDER:
            return
        now = _now()
        cur = state["stage"]
        # duration of the stage that just finished (intake t0 baseline)
        dur = int((time.time() - state["t"]) * 1000)
        if cur is None:
            conn.execute(
                """UPDATE knowledge_file_queue
                    SET stage=?, stage_started_at=?, duration_ms=?, updated_at=?
                  WHERE collection_id=? AND file_key=?""",
                (stage_name, now, dur, now, collection_id, file_key))
        else:
            conn.execute(
                """UPDATE knowledge_file_queue
                    SET stage=?, stage_started_at=?,
                        duration_ms=COALESCE(duration_ms,0)+?, updated_at=?
                  WHERE collection_id=? AND file_key=?""",
                (stage_name, now, dur, now, collection_id, file_key))
        conn.commit()
        state["stage"] = stage_name
        state["t"] = time.time()

    return on_stage


def _queue_start(conn, collection_id, file_key, t0):
    """Mark a queue row running for attempt n (first run or retry)."""
    now = _now()
    conn.execute(
        """UPDATE knowledge_file_queue
            SET status='running', stage=NULL, last_error=NULL,
                stage_started_at=?, finished_at=NULL, duration_ms=NULL,
                attempts=attempts+1, updated_at=?
          WHERE collection_id=? AND file_key=?""",
        (now, now, collection_id, file_key))
    conn.commit()
    return _queue_stage_writer(conn, collection_id, file_key, t0)


def _queue_finish(conn, collection_id, file_key, status, error=None,
                  out_dir=None):
    """Terminal state for a queue row (succeeded/needs_review/failed)."""
    now = _now()
    conn.execute(
        """UPDATE knowledge_file_queue
            SET status=?, last_error=?, out_dir=COALESCE(?, out_dir),
                finished_at=?, updated_at=?
          WHERE collection_id=? AND file_key=?""",
        (status, error, out_dir, now, now, collection_id, file_key))
    conn.commit()


SCHEMA_FIELD_TYPES = ("string", "text", "integer", "float", "boolean", "keyword")


def _default_schema_fields():
    """The corpus block schema shipped as the default draft (PCM-20.9 Stage C).

    Mirrors the Word Factory unified block record (blocks.jsonl):
    block_id, block_index, type, raw_text, normalized_text, norm_version,
    style, parent_block_id, position, source_ref, page, content_hash,
    table_rows, ref_id, warnings.
    """
    def f(name, ftype, desc="", es_field=None, required=False, searchable=True):
        d = {"name": name, "type": ftype, "description": desc,
             "required": required, "searchable": searchable}
        if es_field:
            d["es_field"] = es_field
        return d
    return [
        f("block_id", "string", "شناسهٔ قطعی بلوک (b<index>:<type>)",
          "block_id", True, True),
        f("block_index", "integer", "شمارهٔ ترتیبی بلوک در سند",
          "block_index", True, True),
        f("type", "keyword", "نوع بلوک: heading/paragraph/table/footnote/endnote",
          "type", True, True),
        f("raw_text", "text", "متن خام بلوک", "raw_text", True, True),
        f("normalized_text", "text", "متن نرمال‌شده (نسخهٔ norm)",
          "normalized_text", True, True),
        f("norm_version", "string", "نسخهٔ سیاست نرمال‌سازی", None, False, False),
        f("content_hash", "string", "هش محتوای نرمال‌شده (dedup)",
          "content_hash", False, False),
        f("style", "string", "استایل docx (Heading1, Normal, ...)", "style",
          False, True),
        f("heading_level", "integer", "سطح تیتر (فقط برای بلوک‌های تیتر)",
          "heading_level", False, True),
        f("parent_block_id", "string", "بلوک والد در سلسله‌مراتب تیترها",
          "parent_block_id", False, False),
        f("position", "integer", "موقعیت بلوک در سند", "position", False, False),
        f("page", "integer", "شمارهٔ صفحه (در docx همیشه null — حدس ممنوع)",
          "page", False, True),
        f("source_ref", "string", "ارجاع منبع (JSON به‌صورت رشته)",
          "source_ref", False, False),
        f("table_rows", "text", "ردیف‌های جدول (فقط بلوک‌های جدول)",
          "table_rows", False, False),
        f("ref_id", "string", "شناسهٔ پانوشت/پایان‌نوشت (fn-/en-)",
          "ref_id", False, False),
        f("warnings", "text", "هشدارهای پردازش (JSON به‌صورت رشته)",
          "warnings", False, False),
    ]


def _schema_version_row(conn, collection_id, schema_id):
    r = conn.execute(
        """SELECT * FROM knowledge_schema_versions
           WHERE collection_id=? AND schema_id=?""",
        (collection_id, schema_id)).fetchone()
    return dict(r) if r else None


def _collection_schema_list(conn, collection_id):
    return [dict(r) for r in conn.execute(
        """SELECT * FROM knowledge_schema_versions
           WHERE collection_id=? ORDER BY version DESC""",
        (collection_id,)).fetchall()]


def _collection_approved_schema(conn, collection_id):
    r = conn.execute(
        """SELECT * FROM knowledge_schema_versions
           WHERE collection_id=? AND status='approved'
           ORDER BY version DESC LIMIT 1""", (collection_id,)).fetchone()
    return dict(r) if r else None


def _validate_schema_fields(fields):
    """Validate the schema field list itself. -> (normalized_fields, errors).

    A field: name (non-empty, unique, [a-z0-9_]), type in SCHEMA_FIELD_TYPES,
    optional description (str), optional es_field (str, unique when present),
    required (bool, default False), searchable (bool, default True).
    """
    if not isinstance(fields, list) or not fields:
        return None, ["fields باید یک لیست غیرخالی از تعریف فیلدها باشد"]
    errors, names, es_names = [], set(), set()
    normalized = []
    for i, fld in enumerate(fields):
        where = f"فیلد {i + 1}"
        if not isinstance(fld, dict):
            errors.append(f"{where}: باید یک شیٔ JSON باشد")
            continue
        name = str(fld.get("name") or "").strip()
        if not name or not re.fullmatch(r"[a-z0-9_]{1,64}", name):
            errors.append(f"{where}: نام معتبر ندارد ([a-z0-9_]، ۱ تا ۶۴ حرف)")
            continue
        if name in names:
            errors.append(f"{where}: نام تکراری: {name}")
            continue
        ftype = str(fld.get("type") or "").strip()
        if ftype not in SCHEMA_FIELD_TYPES:
            errors.append(f"{where} ({name}): نوع «{ftype}» معتبر نیست "
                          f"(مجاز: {', '.join(SCHEMA_FIELD_TYPES)})")
            continue
        es_field = str(fld.get("es_field") or "").strip() or None
        if es_field and not re.fullmatch(r"[a-z0-9_.]{1,64}", es_field):
            errors.append(f"{where} ({name}): es_field نامعتبر است")
            continue
        if es_field and es_field in es_names:
            errors.append(f"{where} ({name}): es_field تکراری: {es_field}")
            continue
        desc = str(fld.get("description") or "")
        norm = {
            "name": name,
            "type": ftype,
            "description": desc,
            "required": bool(fld.get("required", False)),
            "searchable": bool(fld.get("searchable", True)),
        }
        if es_field:
            norm["es_field"] = es_field
        names.add(name)
        if es_field:
            es_names.add(es_field)
        normalized.append(norm)
    if errors:
        return None, errors
    return normalized, []


def _schema_validate_report(conn, collection_id, fields, limit=200000):
    """Dry-run a schema against the collection's REAL processed blocks.

    Reads blocks.jsonl from the out_dirs of parsed/approved documents (up to
    `limit` blocks total), checks every required field for presence and every
    declared type for a sane runtime type, and reports per-field coverage plus
    observed values of `type`/`style`. Honest counts only.
    """
    docs = conn.execute(
        """SELECT document_id, out_dir FROM knowledge_collection_documents
           WHERE collection_id=? AND out_dir IS NOT NULL
             AND status IN ('parsed','needs_review','approved','indexed')""",
        (collection_id,)).fetchall()
    data_root = knowledge_data_dir()
    fields_by_name = {f["name"]: f for f in fields}
    seen = {}
    for f in fields:
        seen[f["name"]] = {"present": 0, "type_ok": 0, "type_bad": 0, "seen": 0}
    type_values = {}
    style_values = {}
    total_blocks = 0
    docs_scanned = 0
    for d in docs:
        if total_blocks >= limit:
            break
        blocks_p = os.path.join(data_root, d["out_dir"], "blocks.jsonl")
        if not os.path.isfile(blocks_p):
            continue
        docs_scanned += 1
        try:
            with open(blocks_p, encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    total_blocks += 1
                    if total_blocks > limit:
                        break
                    try:
                        rec = json.loads(line)
                    except Exception:
                        continue
                    for f in fields:
                        s = seen[f["name"]]
                        if f["name"] not in rec or rec[f["name"]] is None:
                            continue
                        s["present"] += 1
                        v = rec[f["name"]]
                        t = f["type"]
                        ok = (
                            (t in ("string", "text", "keyword")
                             and isinstance(v, str))
                            or (t == "integer" and isinstance(v, int)
                                and not isinstance(v, bool))
                            or (t == "float" and isinstance(v, (int, float))
                                and not isinstance(v, bool))
                            or (t == "boolean" and isinstance(v, bool))
                        )
                        s["seen"] += 1
                        s["type_ok" if ok else "type_bad"] += 1
                    if "type" in rec and isinstance(rec["type"], str):
                        type_values[rec["type"]] = \
                            type_values.get(rec["type"], 0) + 1
                    if "style" in rec and isinstance(rec["style"], str):
                        style_values[rec["style"]] = \
                            style_values.get(rec["style"], 0) + 1
        except OSError:
            continue
    errors, warnings = [], []
    for f in fields:
        s = seen[f["name"]]
        if total_blocks and f["required"] and s["present"] == 0:
            errors.append(f"فیلد الزامی «{f['name']}» در هیچ بلوکی یافت نشد")
        if s["type_bad"]:
            warnings.append(
                f"فیلد «{f['name']}» در {s['type_bad']} بلوک نوع نامطلوب دارد")
    report = {
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "documents_scanned": docs_scanned,
        "blocks_scanned": total_blocks,
        "truncated": total_blocks > limit,
        "fields": [
            {
                "name": f["name"],
                "required": f["required"],
                "seen": seen[f["name"]]["seen"],
                "present": seen[f["name"]]["present"],
                "type_ok": seen[f["name"]]["type_ok"],
                "type_bad": seen[f["name"]]["type_bad"],
                "coverage": (round(seen[f["name"]]["present"] / total_blocks, 4)
                              if total_blocks else None),
            } for f in fields
        ],
        "observed_block_types": dict(sorted(type_values.items(),
                                            key=lambda kv: -kv[1])),
        "observed_styles": dict(sorted(style_values.items(),
                                        key=lambda kv: -kv[1])),
        "at": _now(),
    }
    return report


# ---------------------------------------------------------------------------
# PCM-20.9 Stage D — canonical corpus build + guarded ES index factory
# ---------------------------------------------------------------------------

# corpus schema field type -> Elasticsearch mapping type
_ES_TYPE_MAP = {
    "string": "keyword", "text": "text", "integer": "long",
    "float": "float", "boolean": "boolean", "keyword": "keyword",
}


def _es_url():
    """ES base URL for the index factory (empty = ES factory disabled).

    CONFIG-GUARDED: without PCT_ES_URL the corpus build completes
    corpus-only and the ES part is recorded as 'blocked' — the server
    never touches a cluster it was not configured for (stop rule: no
    operational index rewrite from unconfigured code).
    """
    return os.environ.get("PCT_ES_URL", "").strip()


def _es_request(es_url, method, path, body=None, ndjson=False):
    """The single ES HTTP seam (stdlib urllib — no new dependency).

    `path` is absolute ('/_bulk', '/<idx>/_refresh', '/_aliases', ...).
    `body` is a JSON-serializable dict, or a list of objects serialized as
    NDJSON when ndjson=True. Returns the parsed JSON response ({} when the
    response body is empty). Tests patch THIS ONE function to simulate a
    whole cluster.
    """
    import urllib.request
    url = es_url.rstrip("/") + path
    headers = {"Accept": "application/json"}
    data = None
    if body is not None:
        if ndjson:
            data = ("\n".join(json.dumps(x, ensure_ascii=False)
                              for x in body) + "\n").encode("utf-8")
            headers["Content-Type"] = "application/x-ndjson"
        else:
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers,
                                 method=method)
    with urllib.request.urlopen(req, timeout=60) as resp:
        raw = resp.read()
    if not raw:
        return {}
    return json.loads(raw.decode("utf-8"))


def _es_next_index_name(conn, collection_id, slug):
    """Versioned physical index name: knowledge_<slug>_vNNNN.

    NNNN = (max existing version of this collection) + 1, zero-padded to
    4. Old indexes are never overwritten or deleted — each build gets a
    fresh name (rollback = the alias simply stays on the previous one).
    """
    prefix = "knowledge_" + slug + "_"
    pat = re.compile(re.escape(prefix) + r"v(\d{4})$")
    n = 0
    for r in conn.execute(
            "SELECT es_index FROM knowledge_index_builds "
            "WHERE collection_id=? AND es_index IS NOT NULL "
            "AND es_index != 'none'", (collection_id,)).fetchall():
        m = pat.match(r["es_index"] or "")
        if m:
            n = max(n, int(m.group(1)))
    return prefix + f"v{n + 1:04d}"


def _document_metadata(conn, collection_id, doc_row):
    """Merged custom metadata {field_key: value} for one document.

    Scope priority: document > work > edition > volume > collection
    (first value per field_key wins); only enabled fields. The merged
    metadata is embedded in every ES doc so search can filter on it.
    """
    rows = conn.execute(
        """SELECT m.field_key, v.value,
                  CASE m.scope
                    WHEN 'document' THEN 0
                    WHEN 'work' THEN 1
                    WHEN 'edition' THEN 2
                    WHEN 'volume' THEN 3
                    ELSE 4 END AS prio,
                  v.edited_at
             FROM knowledge_metadata_values v
             JOIN knowledge_metadata_fields m ON m.field_id = v.field_id
            WHERE m.enabled = 1
              AND (
                    (m.scope='collection' AND v.collection_id=?)
                 OR (m.scope='document' AND v.document_id=?)
                 OR (m.scope='work'     AND v.work_id=?)
                 OR (m.scope='edition'  AND v.edition_id=?)
                 OR (m.scope='volume'   AND v.volume_id=?)
              )
            ORDER BY prio, v.edited_at DESC""",
        (collection_id, doc_row["document_id"],
         doc_row["work_id"] or "", doc_row["edition_id"] or "",
         doc_row["volume_id"] or "")).fetchall()
    meta = {}
    for r in rows:
        if r["field_key"] not in meta:
            meta[r["field_key"]] = r["value"]
    return meta


def _es_build_index(conn, coll, fields, corpus_dir):
    """Build the versioned ES index for a corpus + ATOMIC alias switch.

    Safe-rollback flow (the alias only moves when everything verified):
      1. PUT the new index knowledge_<slug>_vNNNN with the schema mapping
      2. bulk-index the NORMALIZED stream (one ES doc per block, plus the
         merged custom metadata)
      3. refresh, then GET /_count — must equal the number of docs sent,
         otherwise raise (the alias is NOT touched => rollback)
      4. ONE atomic /_aliases call: remove previous holder(s) + add the
         new index.
    Any failure before step 4 leaves the alias on the previous index; the
    (possibly partial) new index is kept for audit and never aliased.
    """
    es_url = _es_url()
    if not es_url:
        raise RuntimeError("PCT_ES_URL is not set")
    slug = coll["slug"]
    es_index = _es_next_index_name(conn, coll["collection_id"], slug)
    alias = coll["es_alias"]

    # --- 1. new index, mapping from the (approved or default) schema -----
    props = {}
    for f in fields:
        key = f.get("es_field") or f["name"]
        p = {"type": _ES_TYPE_MAP.get(f.get("type"), "keyword")}
        if not f.get("searchable", True):
            p["index"] = False
        props[key] = p
    # Stage E filter fields (work/edition/volume scope) — always present
    # in the mapping so term filters on keywords.* are deterministic.
    props["keywords"] = {"properties": {
        "work_id": {"type": "keyword"},
        "edition_id": {"type": "keyword"},
        "volume_id": {"type": "keyword"},
    }}
    _es_request(es_url, "PUT", "/" + es_index,
                {"mappings": {"properties": props}})

    # --- 2. bulk the normalized stream -----------------------------------
    docs_by_file = {
        d["file_id"]: d for d in conn.execute(
            "SELECT * FROM knowledge_collection_documents "
            "WHERE collection_id=? AND file_id IS NOT NULL",
            (coll["collection_id"],)).fetchall()}
    lines = []
    with open(os.path.join(corpus_dir, "normalized.jsonl"),
              encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            fid = (rec.get("provenance") or {}).get("factory_file_id")
            payload = dict(rec)
            # Stage E: promote the provenance entity ids to top-level
            # keyword fields so work/edition/volume filters are term
            # queries (no painless, no dynamic sub-guessing).
            prov = rec.get("provenance") or {}
            kw = {}
            if prov.get("work_id"):
                kw["work_id"] = prov["work_id"]
            if prov.get("edition_id"):
                kw["edition_id"] = prov["edition_id"]
            if prov.get("volume_id"):
                kw["volume_id"] = prov["volume_id"]
            if kw:
                payload["keywords"] = kw
            doc_row = docs_by_file.get(fid)
            if doc_row is not None:
                payload["metadata"] = _document_metadata(
                    conn, coll["collection_id"], doc_row)
            lines.append({"index": {"_index": es_index,
                                    "_id": rec.get("record_id") or
                                    rec.get("block_id")}})
            lines.append(payload)
    sent = len(lines) // 2
    for i in range(0, len(lines), 1000):  # 500 docs per bulk round-trip
        resp = _es_request(es_url, "POST", "/_bulk", lines[i:i + 1000],
                           ndjson=True)
        if resp.get("errors"):
            bad = [a for a in (resp.get("items") or [])
                   if (a.get("index") or {}).get("error")]
            raise RuntimeError("bulk indexing errors: "
                               + json.dumps(bad[:3], ensure_ascii=False))

    # --- 3. verify the count BEFORE touching the alias (rollback) --------
    _es_request(es_url, "POST", "/" + es_index + "/_refresh")
    cnt = _es_request(es_url, "GET", "/" + es_index + "/_count")
    got = cnt.get("count")
    if got != sent:
        raise RuntimeError(
            f"ES count mismatch after bulk: sent {sent}, counted {got} — "
            f"index {es_index} kept, alias NOT switched (rollback)")

    # --- 4. ONE atomic alias switch --------------------------------------
    prev = []
    try:
        holders = _es_request(es_url, "GET", "/" + alias)
        prev = [ix for ix in (holders or {}) if ix != es_index]
    except Exception:  # noqa: BLE001 — first build: alias does not exist yet
        prev = []
    actions = [{"remove": {"index": ix, "alias": alias}} for ix in prev]
    actions.append({"add": {"index": es_index, "alias": alias}})
    _es_request(es_url, "POST", "/_aliases", {"actions": actions})
    return {"es_index": es_index, "docs": sent, "alias": alias,
            "previous_index": prev[-1] if prev else None}


def _batch_scope_clause(conn, batch_id, alias=None):
    """PCM-20.9 Stage A — scoping clause for document/queue queries.

    Returns (extra_where_sql, params) to append to a
    knowledge_collection_documents query (optionally under `alias`):

    - Batch WITH plan rows (knowledge_batch_files): scope to documents
      belonging to this batch (documents.batch_id = batch_id, set by the
      per-file upload endpoint) OR documents referenced by a plan row
      (pre-20.9 flow: files single-uploaded before the batch was planned,
      plan flags them 'duplicate' with existing_document_id).
    - Batch WITHOUT plan rows (pre-20.9 legacy batch, plan not persisted):
      returns ("", []) -> whole-collection semantics, as the original
      PCM-15 flow relied on.
    """
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM knowledge_batch_files WHERE batch_id=?",
        (batch_id,)).fetchone()
    if not (row and row["n"]):
        return "", []
    col = f"{alias}." if alias else ""
    return (f" AND ({col}batch_id = ? OR {col}document_id IN "
            f"(SELECT document_id FROM knowledge_batch_files "
            f" WHERE batch_id = ? AND document_id IS NOT NULL))",
            [batch_id, batch_id])


def _queue_ensure_rows(conn, collection_id, batch_id):
    """Ensure one pending queue row per planned file of the batch.

    The queue is keyed by the deterministic Word Factory file_id
    (f-<sha8> == f-<sha256[:8]>), so re-planning / re-runs converge on the
    same row (no duplicates).

    PCM-20.9 Stage A: rows are scoped to the batch's own documents when the
    batch has plan rows (see _batch_scope_clause). Legacy batches (pre-20.9,
    plan not persisted) keep the historical whole-collection behaviour —
    this is what the pre-20.9 PCM-15 flow relied on.
    """
    clause, params = _batch_scope_clause(conn, batch_id)
    docs = conn.execute(
        f"""SELECT document_id, file_name, sha256 FROM
             knowledge_collection_documents
           WHERE collection_id=? AND status IN ('uploaded','failed'){clause}
           ORDER BY id""", (collection_id, *params)).fetchall()
    for d in docs:
        file_key = "f-" + d["sha256"][:8]
        now = _now()
        conn.execute(
            """INSERT INTO knowledge_file_queue
               (file_key, document_id, collection_id, file_name, sha256,
                status, attempts, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, 'pending', 0, ?, ?)
               ON CONFLICT(collection_id, file_key) DO NOTHING""",
            (file_key, d["document_id"], collection_id, d["file_name"],
             d["sha256"], now, now))
    conn.commit()


def queue_counters(conn, collection_id=None):
    """Counters computed straight from the queue table (single truth)."""
    where = "WHERE collection_id=?" if collection_id else ""
    args = (collection_id,) if collection_id else ()
    row = conn.execute(
        f"""SELECT
              COUNT(*) AS total,
              SUM(CASE WHEN status='pending' THEN 1 ELSE 0 END) AS pending,
              SUM(CASE WHEN status='running' THEN 1 ELSE 0 END) AS running,
              SUM(CASE WHEN status='succeeded' THEN 1 ELSE 0 END) AS succeeded,
              SUM(CASE WHEN status='needs_review' THEN 1 ELSE 0 END)
                  AS needs_review,
              SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END) AS failed,
              SUM(CASE WHEN stage IS NOT NULL AND status='failed'
                  THEN 1 ELSE 0 END) AS failed_with_safe_stage,
              SUM(COALESCE(attempts,0)) AS attempts_total
            FROM knowledge_file_queue {where}""", args).fetchone()
    out = dict(row)
    out["total"] = out["total"] or 0
    for k in ("pending", "running", "succeeded", "needs_review", "failed",
              "failed_with_safe_stage", "attempts_total"):
        out[k] = out[k] or 0
    return out


# ---------------------------------------------------------------------------
# Word Factory integration (PCM-13, reused)
# ---------------------------------------------------------------------------

def _process_document(conn, collection_id, doc_id, on_stage=None):
    """Run the Word Factory on one registered document (in-place update).

    PCM-15: `on_stage` (optional) is forwarded to the factory — it is called
    with the name of each stage right after that stage completes (intake ..
    export). The caller uses it to persist per-stage progress (safe-stage
    tracking for the queue).
    """
    row = conn.execute(
        """SELECT * FROM knowledge_collection_documents
           WHERE document_id = ? AND collection_id = ?""",
        (doc_id, collection_id)).fetchone()
    if not row:
        raise RuntimeError(f"document {doc_id} not found")
    sha = row["sha256"]
    file_key = "f-" + sha[:8]
    file_name = row["file_name"] or "book.docx"
    ext = os.path.splitext(file_name)[1]
    stored = _stored_file_path(sha, file_key, ext)
    if not os.path.isfile(stored):
        raise RuntimeError("stored original file missing (corrupt store)")

    # PCM-15 — single-document path: when no explicit on_stage is given
    # (i.e. not the queue-aware batch worker), mirror the outcome into the
    # per-file queue row IF one exists (the file was part of a batch). This
    # keeps single-doc retry of a failed queue file consistent: attempts
    # bump, last safe stage re-recorded, last_error refreshed.
    if on_stage is None:
        qrow = _queue_row(conn, collection_id, file_key)
        if qrow is not None:
            on_stage = _queue_start(conn, collection_id, file_key, time.time())

    conn.execute("UPDATE knowledge_collection_documents SET status='parsing', "
                 "updated_at=? WHERE id=?", (_now(), row["id"]))
    conn.commit()

    from factory.service import DocumentProcessingService
    out_root = os.path.join(knowledge_data_dir(), "out")
    os.makedirs(out_root, exist_ok=True)
    svc = DocumentProcessingService(out_root)
    try:
        doc = svc.process(stored, on_stage=on_stage)  # raises on failure
    except Exception as e:  # noqa: BLE001 — record per-doc failure, keep going
        err = f"{type(e).__name__}: {e}"
        conn.execute("UPDATE knowledge_collection_documents SET status='failed', "
                     "error=?, updated_at=? WHERE id=?",
                     (err, _now(), row["id"]))
        _refresh_book_count(conn, collection_id)
        conn.commit()
        if on_stage is not None:
            _queue_finish(conn, collection_id, file_key, "failed", error=err)
        raise

    file_id = doc.file.file_id
    out_dir = factory_out_dir(file_id)
    status = "parsed" if doc.quality.passed else "needs_review"
    conn.execute(
        """UPDATE knowledge_collection_documents SET
             file_id=?, work_id=?, edition_id=?, volume_id=?, status=?,
             blocks_count=?, chars_count=?, quality_status=?, quality_score=?,
             parser_version=?, norm_version=?, out_dir=?, error=NULL,
             updated_at=?
           WHERE id=?""",
        (file_id, doc.work_id, doc.edition_id, doc.volume_id, status,
         len(doc.blocks), doc.total_chars, doc.quality.status,
         doc.quality.score, doc.parser_version, doc.norm_version,
         os.path.relpath(out_dir, knowledge_data_dir()), _now(), row["id"]))
    # PCM-14D — keep the entity registry in sync (idempotent upsert; the
    # ids/keys mirror factory.service exactly, so the registry row is the
    # same one _backfill_registry would create from this document).
    _upsert_registry_rows(conn, doc)
    _refresh_book_count(conn, collection_id)
    conn.commit()
    if on_stage is not None:
        _queue_finish(conn, collection_id, file_key,
                      "succeeded" if status == "parsed" else "needs_review",
                      out_dir=os.path.relpath(out_dir, knowledge_data_dir())
                                   .replace(os.sep, "/"))
    return status


def _job_kind_process_document(conn, job_id):
    r = conn.execute("SELECT job_key, collection_id FROM knowledge_jobs "
                     "WHERE job_id=?", (job_id,)).fetchone()
    kind, doc_id = r["job_key"].split(":", 1)
    _process_document(conn, r["collection_id"], doc_id)


def _job_kind_process_batch(conn, job_id):
    """PCM-15 queue-aware batch worker.

    Per file: ensure its queue row -> mark running (attempts+1) -> run the
    factory with an on_stage callback persisting the last safe stage ->
    terminal state (succeeded / needs_review / failed with last_error).
    Honours the batch pause scope: when paused, the job stops cleanly,
    leaves the remaining files pending, and marks itself interrupted
    (retryable — POST /process resumes).
    """
    r = conn.execute("SELECT job_key, collection_id FROM knowledge_jobs "
                     "WHERE job_id=?", (job_id,)).fetchone()
    _, batch_id = r["job_key"].split(":", 1)
    coll = r["collection_id"]
    scope = queue_scope(batch_id)

    _queue_ensure_rows(conn, coll, batch_id)
    # PCM-20.9 Stage A: batch-scoped processing (see _batch_scope_clause);
    # legacy pre-20.9 batches keep whole-collection semantics.
    clause, params = _batch_scope_clause(conn, batch_id)
    docs = conn.execute(
        f"""SELECT document_id, file_name, sha256 FROM
             knowledge_collection_documents
            WHERE collection_id = ? AND status IN ('uploaded','failed'){clause}
            ORDER BY id""", (coll, *params)).fetchall()
    total = len(docs)
    done = 0
    paused_now = _now()
    for d in docs:
        if queue_is_paused(conn, scope):
            # clean stop: remaining files stay pending in the queue
            conn.execute(
                "UPDATE knowledge_import_batches SET status='planned', "
                "updated_at=? WHERE batch_id=?", (paused_now, batch_id))
            conn.commit()
            _job_progress(conn, job_id, done, total, "paused")
            conn.execute(
                """UPDATE knowledge_jobs
                     SET status='interrupted',
                         error=COALESCE(error,'') || ' [paused by user]',
                         updated_at=? WHERE job_id=?""",
                (paused_now, job_id))
            conn.commit()
            return
        file_key = "f-" + d["sha256"][:8]
        t0 = time.time()
        on_stage = _queue_start(conn, coll, file_key, t0)
        try:
            # _process_document finishes the queue row itself in every case
            # (succeeded / needs_review / failed) via the on_stage lifecycle.
            _process_document(conn, coll, d["document_id"],
                              on_stage=on_stage)
        except Exception as e:  # noqa: BLE001 — keep going, record per file
            err = f"{type(e).__name__}: {e}"
            conn.execute(
                "UPDATE knowledge_collection_documents SET status='failed', "
                "error=?, updated_at=? WHERE document_id=?",
                (err, _now(), d["document_id"]))
            conn.commit()
            # safety net: if the failure happened before the factory ran
            # (e.g. registry row gone) the queue row is still 'running' —
            # finalize it so no row is ever left dangling.
            q = _queue_row(conn, coll, file_key)
            if q and q["status"] == "running":
                _queue_finish(conn, coll, file_key, "failed", error=err)
        done += 1
        _job_progress(conn, job_id, done, total,
                      f"document {d['document_id']}")
    # batch tally (PCM-20.9 Stage A: same scope as the docs processed above)
    clause, params = _batch_scope_clause(conn, batch_id)
    t = conn.execute(
        f"""SELECT
             SUM(CASE WHEN status IN ('parsed','needs_review','approved','indexed')
                 THEN 1 ELSE 0 END) AS ok,
             SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END) AS bad
            FROM knowledge_collection_documents
            WHERE collection_id=?{clause}""", (coll, *params)).fetchone()
    conn.execute(
        "UPDATE knowledge_import_batches SET processed_count=?, failed_count=?, "
        "status='done', updated_at=? WHERE batch_id=?",
        (t["ok"] or 0, t["bad"] or 0, _now(), batch_id))
    conn.commit()


def _job_kind_process_batch_retry(conn, job_id):
    """PCM-20.9 Stage B — retry only the FAILED files of a batch.

    Succeeded / needs_review files are left untouched (checkpoint/resume:
    a failed run never forces re-processing the whole batch). Each failed
    queue row is re-executed through the normal Word Factory path with the
    per-file queue lifecycle (attempts+1, safe-stage tracking, last_error).
    Honours the batch pause scope like the main batch job (clean stop,
    job interrupted, remaining failed files stay failed for a later retry).
    """
    r = conn.execute("SELECT job_key, collection_id FROM knowledge_jobs "
                     "WHERE job_id=?", (job_id,)).fetchone()
    _, batch_id = r["job_key"].split(":", 1)
    coll = r["collection_id"]
    scope = queue_scope(batch_id)
    dclause, dparams = _batch_scope_clause(conn, batch_id, alias="d")
    rows = conn.execute(
        f"""SELECT q.file_key, q.document_id FROM knowledge_file_queue q
             JOIN knowledge_collection_documents d
               ON d.document_id = q.document_id
              AND d.collection_id = q.collection_id
            WHERE q.collection_id = ? AND q.status = 'failed'{dclause}
            ORDER BY q.created_at""", (coll, *dparams)).fetchall()
    total = len(rows)
    done = 0
    for q in rows:
        if queue_is_paused(conn, scope):
            # clean stop: the remaining failed files stay failed
            paused_now = _now()
            _job_progress(conn, job_id, done, total, "paused")
            conn.execute(
                """UPDATE knowledge_jobs
                     SET status='interrupted',
                         error=COALESCE(error,'') || ' [paused by user]',
                         updated_at=? WHERE job_id=?""",
                (paused_now, job_id))
            conn.commit()
            return
        t0 = time.time()
        on_stage = _queue_start(conn, coll, q["file_key"], t0)
        try:
            # _process_document finishes the queue row itself in every case
            _process_document(conn, coll, q["document_id"], on_stage=on_stage)
        except Exception as e:  # noqa: BLE001 — keep going, record per file
            err = f"{type(e).__name__}: {e}"
            conn.execute(
                "UPDATE knowledge_collection_documents SET status='failed', "
                "error=?, updated_at=? WHERE document_id=?",
                (err, _now(), q["document_id"]))
            conn.commit()
            qrow = _queue_row(conn, coll, q["file_key"])
            if qrow and qrow["status"] == "running":
                _queue_finish(conn, coll, q["file_key"], "failed", error=err)
        done += 1
        _job_progress(conn, job_id, done, total, f"document {q['document_id']}")
    # batch tally (same scope as the main batch job)
    tclause, tparams = _batch_scope_clause(conn, batch_id)
    t = conn.execute(
        f"""SELECT
             SUM(CASE WHEN status IN ('parsed','needs_review','approved','indexed')
                 THEN 1 ELSE 0 END) AS ok,
             SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END) AS bad
            FROM knowledge_collection_documents
            WHERE collection_id=?{tclause}""", (coll, *tparams)).fetchone()
    conn.execute(
        "UPDATE knowledge_import_batches SET processed_count=?, failed_count=?, "
        "status='done', updated_at=? WHERE batch_id=?",
        (t["ok"] or 0, t["bad"] or 0, _now(), batch_id))
    conn.commit()


def _job_kind_corpus_build(conn, job_id):
    """PCM-20.9 Stage D — canonical corpus (c-1) + guarded ES factory.

    Per processed document: factory.dump.generate_dump (d-1; the stored
    original is re-hashed when present, else the WF manifest sha is
    trusted). Then factory.corpus.build_corpus (c-1, fail-fast: no file
    is written unless every dump validates). The build row is keyed by
    the CORPUS ARCHIVE sha256: same content -> REUSED (no rewrite, no
    second row). The ES part is config-guarded (PCT_ES_URL): absent ->
    es_index_status='blocked'; present -> versioned index + atomic alias
    switch (see _es_build_index); ES failure keeps the alias untouched.
    """
    r = conn.execute(
        "SELECT job_key, collection_id FROM knowledge_jobs WHERE job_id=?",
        (job_id,)).fetchone()
    _, coll_id = r["job_key"].split(":", 1)
    coll = conn.execute(
        "SELECT * FROM knowledge_collections WHERE collection_id=?",
        (coll_id,)).fetchone()
    if not coll:
        raise RuntimeError(f"collection {coll_id} not found")
    coll = dict(coll)

    docs = conn.execute(
        """SELECT * FROM knowledge_collection_documents
           WHERE collection_id=? AND out_dir IS NOT NULL
             AND status IN ('parsed','needs_review','approved','indexed')
           ORDER BY id""", (coll_id,)).fetchall()
    total = len(docs)
    if not total:
        raise RuntimeError("no processed documents in the collection "
                           "(need status parsed/needs_review/approved/"
                           "indexed with factory output)")

    root = os.path.join(knowledge_data_dir(), "corpus_builds", coll_id)
    dumps_root = os.path.join(root, "dumps")
    corpus_dir = os.path.join(root, "corpus")
    os.makedirs(dumps_root, exist_ok=True)

    from factory.dump import generate_dump, validate_dump
    from factory.corpus import build_corpus

    # --- 1. one canonical d-1 dump per processed document ----------------
    # Reuse an existing, valid dump when the input + factory versions still
    # match the current WF output: generate_dump rewrites
    # dump-manifest.json with a fresh generated_at, which would change the
    # archive sha on every rebuild and break content idempotency (REUSED).
    def _dump_is_reusable(wf_dir, dump_dir, sha):
        try:
            with open(os.path.join(wf_dir, "manifest.json"),
                      encoding="utf-8") as fh:
                m = json.load(fh)
        except Exception:  # noqa: BLE001 — missing/corrupt WF output
            return False
        if not isinstance(m, dict):
            return False
        if (m.get("file") or {}).get("sha256") != sha:
            return False
        ok, _e, _w = validate_dump(dump_dir)
        if not ok:
            return False
        try:
            with open(os.path.join(dump_dir, "dump-manifest.json"),
                      encoding="utf-8") as fh:
                dm = json.load(fh)
        except Exception:  # noqa: BLE001
            return False
        if not isinstance(dm, dict):
            return False
        v2 = dm.get("versions") or {}
        # dump.py derives versions from: manifest_version + schema_version +
        # m["versions"]{parser, normalizer, normalizer_policy, factory}
        if v2.get("manifest") != m.get("manifest_version"):
            return False
        if v2.get("schema") != m.get("schema_version"):
            return False
        v1 = m.get("versions") or {}
        return all(v2.get(k) == v1.get(k) for k in
                   ("parser", "normalizer", "normalizer_policy", "factory"))

    dump_dirs = []
    for i, d in enumerate(docs, 1):
        d_out = os.path.join(knowledge_data_dir(), d["out_dir"])
        dump_dir = os.path.join(dumps_root, d["file_id"])
        stored = _stored_file_path(
            d["sha256"], "f-" + d["sha256"][:8],
            os.path.splitext(d["file_name"] or "book.docx")[1])
        if not _dump_is_reusable(d_out, dump_dir, d["sha256"]):
            generate_dump(wf_dir=d_out, dump_dir=dump_dir,
                          source_docx=stored if os.path.isfile(stored)
                          else None)
        dump_dirs.append(dump_dir)
        _job_progress(conn, job_id, i, total, f"dump {d['file_id']}")

    # --- 2. canonical corpus c-1 (fail-fast, deterministic archive) ------
    _job_progress(conn, job_id, total, total, "corpus build (c-1)")
    manifest = build_corpus(dump_dirs, corpus_dir)
    content_sha = manifest["archive"]["sha256"]

    # --- 3. build row, content-idempotent (REUSED on same archive sha) ---
    reuse = conn.execute(
        """SELECT iv_id, es_index_status FROM knowledge_index_builds
           WHERE collection_id=? AND content_sha256=?""",
        (coll_id, content_sha)).fetchone()
    if reuse and (reuse["es_index_status"] or "pending") != "failed":
        # same corpus content, ES part already settled (success or
        # blocked) -> nothing to do (no rewrite, no second row)
        iv_id = reuse["iv_id"]
        conn.execute(
            "UPDATE knowledge_index_builds SET status='succeeded', "
            "completed_at=? WHERE iv_id=?", (_now(), iv_id))
        conn.commit()
        _audit_log(conn, coll_id, "build", "corpus_reused", "ok",
                   {"iv_id": iv_id, "content_sha256": content_sha})
        _job_progress(conn, job_id, total, total, f"reused {iv_id}")
        return

    iv_id = "iv-" + hashlib.sha256(
        (coll_id + content_sha).encode("utf-8")).hexdigest()[:8]
    now = _now()
    rel_out = os.path.relpath(corpus_dir, knowledge_data_dir())
    rel_out = rel_out.replace(os.sep, "/")
    if reuse:
        # same content but the previous ES attempt FAILED: the corpus on
        # disk is unchanged — keep the same row and re-run the ES part
        # below (never a second row for the same content).
        conn.execute(
            """UPDATE knowledge_index_builds
               SET status='succeeded', completed_at=?, content_sha256=?,
                   out_dir=?, es_index='none', es_index_status='pending',
                   es_detail=NULL, schema_version=?, chunk_count=?
               WHERE iv_id=?""",
            (now, content_sha, rel_out, coll["schema_version"],
             manifest["counts"]["blocks_total"], iv_id))
    else:
        conn.execute(
            """INSERT INTO knowledge_index_builds
               (iv_id, collection_id, es_index, es_alias, schema_version,
                norm_version, chunking_version, chunk_count, status,
                created_at, completed_at, content_sha256, out_dir,
                es_index_status)
               VALUES (?, ?, 'none', ?, ?, ?, ?, ?, 'succeeded',
                       ?, ?, ?, ?, 'pending')""",
            (iv_id, coll_id, coll["es_alias"], coll["schema_version"],
             coll["normalization_version"], coll["chunking_version"],
             manifest["counts"]["blocks_total"], now, now, content_sha,
             rel_out))
    conn.commit()
    _job_progress(conn, job_id, total, total, "corpus built (c-1)")

    # --- 4. ES index factory (config-guarded; rollback-safe) -------------
    if not _es_url():
        conn.execute(
            "UPDATE knowledge_index_builds "
            "SET es_index_status=?, es_detail=? WHERE iv_id=?",
            ("blocked", json.dumps(
                {"status": "blocked",
                 "reason": "PCT_ES_URL تنظیم نیست — ES factory غیرفعال "
                            "(build corpus-only)"},
                ensure_ascii=False), iv_id))
        conn.commit()
        _audit_log(conn, coll_id, "build", "corpus_built", "blocked",
                   {"iv_id": iv_id, "content_sha256": content_sha,
                    "es": "blocked: PCT_ES_URL not set"})
        return

    schema_row = _collection_approved_schema(conn, coll_id)
    fields = (json.loads(schema_row["fields"]) if schema_row
              else _default_schema_fields())
    try:
        info = _es_build_index(conn, coll, fields, corpus_dir)
    except Exception as e:  # noqa: BLE001 — alias stays on the prev index
        conn.execute(
            "UPDATE knowledge_index_builds "
            "SET es_index_status=?, es_detail=? WHERE iv_id=?",
            ("failed", json.dumps(
                {"status": "failed",
                 "error": f"{type(e).__name__}: {e}"},
                ensure_ascii=False), iv_id))
        conn.commit()
        _audit_log(conn, coll_id, "build", "es_index_failed", "fail",
                   {"iv_id": iv_id, "error": f"{type(e).__name__}: {e}"})
        raise
    conn.execute(
        "UPDATE knowledge_index_builds SET es_index=?, es_index_status=?, "
        "es_detail=? WHERE iv_id=?",
        (info["es_index"], "success", json.dumps(info, ensure_ascii=False),
         iv_id))
    # the alias now serves this index: mark the collection accordingly
    conn.execute(
        "UPDATE knowledge_collections SET current_index_build=?, "
        "indexing_status='ready', updated_at=? WHERE collection_id=?",
        (iv_id, _now(), coll_id))
    conn.commit()
    _audit_log(conn, coll_id, "build", "es_index_success", "ok",
               {"iv_id": iv_id, "es_index": info["es_index"],
                "es_alias": info.get("es_alias")})
    _job_progress(conn, job_id, total, total, f"es {info['es_index']}")


# ---------------------------------------------------------------------------
# PCM-20.9 Stage E — search validation & acceptance
# ---------------------------------------------------------------------------

# The 10 acceptance categories (RECON §8 Stage E). The order is the
# reported order; each one is a REAL query against the LIVE alias.
_SEARCH_CATEGORIES = [
    "count",            # 01 — alias /_count == corpus blocks_total
    "exact_block",      # 02 — phrase match on a full normalized block
    "partial_text",     # 03 — single-word match (Persian analyzer works)
    "heading_filter",   # 04 — type=heading filter returns only headings
    "work_filter",      # 05 — keywords.work_id term filter, exact scope
    "metadata_filter",  # 06 — custom metadata term filter, exact scope
    "pagination",       # 07 — from/size pages: stable total, unique ids
    "determinism",      # 08 — same query twice -> identical id set
    "absence",          # 09 — a nonsense phrase matches 0 docs
    "latency",          # 10 — a search query returns well under 30 s
]


def _search_acceptance_run(conn, build, coll_id):
    """Run the 10-category acceptance against the LIVE alias (read-only).

    Safe by construction: it only issues search/count requests — the
    alias is never touched, so a failing acceptance cannot move any
    pointer. Every category is honest: missing data yields 'skipped'
    (vacuous), a wrong result yields 'fail' with the evidence.

    Returns the report dict stored in search_detail (JSON).
    """
    alias = build["es_alias"]
    index = build["es_index"]
    expected = build["chunk_count"]
    es = _es_url()

    def q(query, size=3, from_=None, sort=None):
        body = {"query": query}
        if size is not None:
            body["size"] = size
        if from_ is not None:
            body["from"] = from_
        if sort is not None:
            body["sort"] = sort
        return _es_request(es, "POST", "/" + alias + "/_search", body)

    def total_of(resp):
        return (resp.get("hits") or {}).get("total", {}).get("value")

    def hits_of(resp):
        return (resp.get("hits") or {}).get("hits") or []

    def _normalized_records(limit=20000):
        p = os.path.join(knowledge_data_dir(), build["out_dir"],
                         "normalized.jsonl")
        recs = []
        with open(p, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    recs.append(json.loads(line))
                if len(recs) >= limit:
                    break
        return recs

    # --- 01 count ---------------------------------------------------------
    def _do_count():
        got = _es_request(es, "GET", "/" + alias + "/_count").get("count")
        ok = (got == expected)
        return ("pass" if ok else "fail"), \
            f"count={got} vs corpus blocks_total={expected}"

    # --- 02 exact block (phrase on a full normalized text) ----------------
    def _do_exact():
        recs = _normalized_records(1)
        if not recs:
            return "skipped", "corpus normalized.jsonl is empty"
        text = (recs[0].get("normalized_text") or "").strip()
        if not text:
            return "skipped", "first block has empty normalized_text"
        n = total_of(q({"match_phrase": {"normalized_text": text}}))
        exact = any((h.get("_source") or {}).get("normalized_text") == text
                    for h in hits_of(q(
                        {"match_phrase": {"normalized_text": text}})))
        ok = bool(n and n >= 1) and exact
        return ("pass" if ok else "fail"), \
            f"phrase {text[:50]!r}: hits={n}, exact-source-present={exact}"

    # --- 03 partial text (one word, analyzer) -----------------------------
    def _do_partial():
        recs = _normalized_records(1)
        text = ""
        for r in recs:
            text = (r.get("normalized_text") or "").strip()
            if text:
                break
        if not text:
            return "skipped", "no non-empty normalized_text found"
        word = text.split()[0]
        n = total_of(q({"match": {"normalized_text": word}}))
        ok = bool(n and n >= 1)
        return ("pass" if ok else "fail"), \
            f"word {word!r}: hits={n} (expected >=1)"

    # --- 04 heading filter --------------------------------------------------
    def _do_heading():
        resp = q({"bool": {"filter": [{"term": {"type": "heading"}}]}},
                 size=20)
        n = total_of(resp)
        if not n:
            return "skipped", "corpus has no heading blocks"
        all_h = all((h.get("_source") or {}).get("type") == "heading"
                    for h in hits_of(resp))
        return ("pass" if all_h else "fail"), \
            f"type=heading: hits={n}, all-headings={all_h}"

    # --- 05 work filter (keyword term on provenance work_id) ---------------
    def _do_work():
        r = conn.execute(
            """SELECT work_id FROM knowledge_collection_documents
               WHERE collection_id=? AND work_id IS NOT NULL
                 AND work_id != '' ORDER BY id LIMIT 1""",
            (coll_id,)).fetchone()
        if not r or not r["work_id"]:
            return "skipped", "no work_id on any document (category vacuous)"
        wid = r["work_id"]
        exp = conn.execute(
            """SELECT COALESCE(SUM(blocks_count), 0) AS n
               FROM knowledge_collection_documents
              WHERE collection_id=? AND work_id=?""",
            (coll_id, wid)).fetchone()["n"]
        resp = q({"term": {"keywords.work_id": wid}}, size=20)
        n = total_of(resp)
        all_w = all((h.get("_source") or {}).get("keywords", {})
                    .get("work_id") == wid for h in hits_of(resp))
        ok = (n == exp) and all_w
        return ("pass" if ok else "fail"), \
            f"keywords.work_id={wid}: hits={n}, expected={exp}, " \
            f"all-same-work={all_w}"

    # --- 06 custom metadata filter -----------------------------------------
    def _do_metadata():
        row = conn.execute(
            """SELECT f.field_key, v.value
               FROM knowledge_metadata_values v
               JOIN knowledge_metadata_fields f ON f.field_id = v.field_id
              WHERE f.enabled = 1 AND f.scope = 'collection'
                AND v.collection_id = ?
              ORDER BY v.value_id LIMIT 1""",
            (coll_id,)).fetchone()
        if not row or row["value"] is None:
            return "skipped", \
                "no collection-scope metadata value (category vacuous)"
        key, value = row["field_key"], row["value"]
        # expected = blocks of docs whose MERGED metadata keeps the value
        exp = 0
        for d in conn.execute(
                "SELECT * FROM knowledge_collection_documents "
                "WHERE collection_id=?", (coll_id,)):
            if _document_metadata(conn, coll_id, d).get(key) == value:
                exp += d["blocks_count"] or 0
        # real ES: a dynamic string field is text + .keyword subfield —
        # the term query must hit the exact .keyword side
        resp = q({"term": {"metadata." + key + ".keyword": value}},
                 size=20)
        n = total_of(resp)
        all_m = all((h.get("_source") or {}).get("metadata", {})
                    .get(key) == value for h in hits_of(resp))
        ok = (n == exp) and all_m
        return ("pass" if ok else "fail"), \
            f"metadata.{key}={value!r}: hits={n}, expected={exp}, " \
            f"all-carry-value={all_m}"

    # --- 07 pagination -------------------------------------------------------
    def _do_pagination():
        sort = [{"_id": {"order": "asc"}}]  # stable paging on real ES too
        pages = []
        totals = set()
        for f in (0, 2, 4):
            resp = q({"match_all": {}}, size=2, from_=f, sort=sort)
            totals.add(total_of(resp))
            pages.append([h["_id"] for h in hits_of(resp)])
        all_ids = [i for pg in pages for i in pg]
        stable = len(totals) == 1
        unique = len(all_ids) == len(set(all_ids))
        ok = stable and unique and all_ids
        return ("pass" if ok else "fail"), \
            f"pages(from=0/2/4, size=2): totals={sorted(totals, key=str)}, " \
            f"ids={len(all_ids)}, unique={unique}"

    # --- 08 determinism ------------------------------------------------------
    def _do_determinism():
        sort = [{"_id": {"order": "asc"}}]
        a = [h["_id"] for h in hits_of(
            q({"match_all": {}}, size=20, sort=sort))]
        b = [h["_id"] for h in hits_of(
            q({"match_all": {}}, size=20, sort=sort))]
        ok = bool(a) and a == b
        return ("pass" if ok else "fail"), \
            f"two identical sorted queries: {len(a)} vs {len(b)} ids, " \
            f"equal={a == b}"

    # --- 09 absence -----------------------------------------------------------
    def _do_absence():
        nonsense = "زبرجدی‌فوق‌العادة‌۹۸۷۶۵"
        n = total_of(q({"match_phrase": {"normalized_text": nonsense}}))
        ok = n == 0
        return ("pass" if ok else "fail"), \
            f"nonsense phrase: hits={n} (expected 0)"

    # --- 10 latency smoke -------------------------------------------------------
    def _do_latency():
        t0 = time.time()
        _es_request(es, "GET", "/" + alias + "/_count")
        dt = time.time() - t0
        ok = dt < 30.0
        return ("pass" if ok else "fail"), \
            f"count query took {dt:.3f}s (budget 30s)"

    runners = {
        "count": _do_count,
        "exact_block": _do_exact,
        "partial_text": _do_partial,
        "heading_filter": _do_heading,
        "work_filter": _do_work,
        "metadata_filter": _do_metadata,
        "pagination": _do_pagination,
        "determinism": _do_determinism,
        "absence": _do_absence,
        "latency": _do_latency,
    }
    categories = {}
    failed = []
    for code in _SEARCH_CATEGORIES:
        fn = runners[code]
        try:
            status, detail = fn()
        except Exception as e:  # noqa: BLE001 — a failed query IS evidence
            status, detail = "fail", f"{type(e).__name__}: {e}"
        categories[code] = {"status": status, "detail": detail}
        if status == "fail":
            failed.append(code)
    return {
        "version": "sa-1",
        "alias": alias,
        "index": index,
        "build_iv_id": build["iv_id"],
        "expected_count": expected,
        "categories": categories,
        "overall": "pass" if not failed else "fail",
        "failed": failed,
        "ran_at": _now(),
    }


def _job_kind_search_acceptance(conn, job_id):
    """PCM-20.9 Stage E — the guarded search acceptance (job).

    Guards (honest, no fabricated results):
      - a Stage D build (content_sha256 NOT NULL) must exist;
      - PCT_ES_URL must be configured, else the job fails BLOCKED;
      - the build's es_index_status must be 'success' (a live alias),
        else BLOCKED — acceptance against a non-live index is meaningless.
    Outcome is written to the build row (search_status pass/fail/blocked
    + search_detail report) and to the collection (validation_status
    accepted / needs_review). The alias is never touched here.
    """
    r = conn.execute(
        "SELECT job_key FROM knowledge_jobs WHERE job_id=?",
        (job_id,)).fetchone()
    _, coll_id = r["job_key"].split(":", 1)
    coll = conn.execute(
        "SELECT * FROM knowledge_collections WHERE collection_id=?",
        (coll_id,)).fetchone()
    if not coll:
        raise RuntimeError(f"collection {coll_id} not found")
    build = conn.execute(
        """SELECT * FROM knowledge_index_builds
           WHERE collection_id=? AND content_sha256 IS NOT NULL
           ORDER BY created_at DESC, iv_id DESC""",
        (coll_id,)).fetchone()
    if not build:
        raise RuntimeError("no Stage D corpus build found — run the "
                           "corpus build (Stage D) first")
    build = dict(build)

    def _mark_blocked(reason):
        conn.execute(
            "UPDATE knowledge_index_builds SET search_status=?, "
            "search_detail=? WHERE iv_id=?",
            ("blocked", json.dumps(
                {"status": "blocked", "reason": reason},
                ensure_ascii=False), build["iv_id"]))
        conn.commit()
        _audit_log(conn, coll_id, "acceptance", "search_acceptance_blocked",
                   "blocked", {"iv_id": build["iv_id"], "reason": reason})

    if not _es_url():
        _mark_blocked("PCT_ES_URL تنظیم نیست — search acceptance "
                      "غیرفعال (Stage D ES factory هم blocked است)")
        raise RuntimeError("search acceptance BLOCKED: PCT_ES_URL is "
                           "not set (no cluster configured)")
    if (build["es_index_status"] or "pending") != "success":
        _mark_blocked(f"es_index_status={build['es_index_status']!r} — "
                      "ابتدا Stage D تا es success (alias زنده) بماند")
        raise RuntimeError("search acceptance BLOCKED: the Stage D ES "
                           "factory has no successful index yet")

    _job_progress(conn, job_id, 1, len(_SEARCH_CATEGORIES),
                  "acceptance start")
    report = _search_acceptance_run(conn, build, coll_id)
    overall = report["overall"]
    conn.execute(
        "UPDATE knowledge_index_builds SET search_status=?, "
        "search_detail=? WHERE iv_id=?",
        (overall, json.dumps(report, ensure_ascii=False), build["iv_id"]))
    vs = "accepted" if overall == "pass" else "needs_review"
    conn.execute(
        "UPDATE knowledge_collections SET validation_status=?, "
        "updated_at=? WHERE collection_id=?",
        (vs, _now(), coll_id))
    conn.commit()
    _job_progress(conn, job_id, len(_SEARCH_CATEGORIES),
                  len(_SEARCH_CATEGORIES), f"acceptance {overall}")
    _audit_log(conn, coll_id, "acceptance", "search_acceptance",
               "ok" if overall == "pass" else "fail",
               {"iv_id": build["iv_id"], "overall": overall,
                "failed": report.get("failed", [])})


def _job_kind_release(conn, job_id):
    """PCM-20.9 Final — the release bundle (standalone, always runnable).

    Produces a content-addressed zip:
      corpus/corpus-data.zip + corpus-manifest.json   (c-1)
      dumps/<file_id>/{canonical files + dump-manifest.json}  (d-1, one per doc)
      release-manifest.json  — chained hashes of EVERY layer + provenance
      README.md              — human provenance
    All layers are re-verified BEFORE packaging (hashes recomputed from the
    bytes on disk; a mismatch fails the job). The release row is keyed by
    (collection_id, content_sha256): the same corpus content produces the
    SAME release_id and the zip is reused (no rewrite).

    RAG is config-guarded: PCT_RAG_INGEST_URL absent -> rag_status='blocked'
    (honest, nothing called); present -> ingest attempt recorded.
    """
    from factory.dump import validate_dump
    from factory.corpus import ARCHIVE_NAME, CORPUS_DATA_FILES

    r = conn.execute(
        "SELECT job_key FROM knowledge_jobs WHERE job_id=?",
        (job_id,)).fetchone()
    _, coll_id = r["job_key"].split(":", 1)
    coll = conn.execute(
        "SELECT * FROM knowledge_collections WHERE collection_id=?",
        (coll_id,)).fetchone()
    if not coll:
        raise RuntimeError(f"collection {coll_id} not found")
    coll = dict(coll)
    build = conn.execute(
        """SELECT * FROM knowledge_index_builds
           WHERE collection_id=? AND content_sha256 IS NOT NULL
           ORDER BY created_at DESC, iv_id DESC""",
        (coll_id,)).fetchone()
    if not build:
        raise RuntimeError("no Stage D corpus build found — run the "
                           "corpus build (Stage D) first")
    build = dict(build)
    corpus_dir = os.path.join(knowledge_data_dir(), build["out_dir"])
    content_sha = build["content_sha256"]
    total = 4  # corpus / dumps / manifest / rag

    # ---- 1. corpus layer (c-1): re-verify the archive + manifest ---------
    _job_progress(conn, job_id, 1, total, "verify corpus (c-1)")
    archive = os.path.join(corpus_dir, ARCHIVE_NAME)
    if not os.path.isfile(archive):
        raise RuntimeError(f"corpus archive missing on disk: {archive}")
    real_archive = _sha256_file(archive)
    if real_archive != content_sha:
        raise RuntimeError(
            "corpus archive sha mismatch — on-disk archive does not match "
            "the recorded build content_sha256")
    with open(os.path.join(corpus_dir, "corpus-manifest.json"),
              encoding="utf-8") as fh:
        cman = json.load(fh)
    cman_sha = _sha256_file(os.path.join(corpus_dir,
                                         "corpus-manifest.json"))
    corpus_files = {}
    for f in cman.get("files") or []:
        p = os.path.join(corpus_dir, f["name"])
        corpus_files[f["name"]] = {
            "sha256": _sha256_file(p),
            "size_bytes": os.path.getsize(p),
        }

    # ---- 2. dumps layer (d-1): exactly the dumps the corpus was built ----
    # from (the corpus manifest's input_dumps is the authoritative layer
    # list — the release must mirror the corpus, not the current DB).
    _job_progress(conn, job_id, 2, total, "verify dumps (d-1)")
    dumps_root = os.path.join(os.path.dirname(corpus_dir), "dumps")
    input_dumps = cman.get("input_dumps") or []
    if not input_dumps:
        raise RuntimeError("corpus manifest has no input_dumps — cannot "
                           "build a release from it")
    corpus_fids = sorted((i.get("file_id") or "" for i in input_dumps))
    docs = conn.execute(
        """SELECT file_id, file_name FROM knowledge_collection_documents
           WHERE collection_id=? AND out_dir IS NOT NULL
             AND status IN ('parsed','needs_review','approved','indexed')""",
        (coll_id,)).fetchall()
    doc_by_fid = {d["file_id"]: (d["file_name"] or "") for d in docs
                  if d["file_id"]}
    db_fids = sorted(doc_by_fid)
    if corpus_fids != db_fids:
        stale = sorted(set(db_fids) - set(corpus_fids))
        gone = sorted(set(corpus_fids) - set(db_fids))
        raise RuntimeError(
            "corpus is stale relative to the collection's documents — "
            "run the corpus build (Stage D) again before release "
            f"(new in DB: {stale}; not in DB: {gone})")
    dumps_entries = []
    for i, entry in enumerate(input_dumps, 1):
        fid = entry.get("file_id")
        dump_dir = os.path.join(dumps_root, fid)
        dm_path = os.path.join(dump_dir, "dump-manifest.json")
        if not os.path.isfile(dm_path):
            raise RuntimeError(f"dump missing on disk: {fid}")
        ok, errs, _w = validate_dump(dump_dir)
        if not ok:
            raise RuntimeError(f"dump invalid ({fid}): "
                               + "; ".join(errs[:3]))
        with open(dm_path, encoding="utf-8") as fh:
            dm = json.load(fh)
        fentries = []
        for e in dm.get("files") or []:
            p = os.path.join(dump_dir, e["name"])
            real = _sha256_file(p)
            if real != e.get("sha256"):
                raise RuntimeError(
                    f"dump file hash mismatch {fid}/{e['name']}")
            fentries.append({"name": e["name"], "sha256": real,
                             "size_bytes": os.path.getsize(p)})
        dumps_entries.append({
            "file_id": fid,
            "input_filename": doc_by_fid.get(fid, ""),
            "input_sha256": (dm.get("integrity") or {}).get("input_sha256"),
            "work_id": (dm.get("identifiers") or {}).get("work_id"),
            "edition_id": (dm.get("identifiers") or {}).get("edition_id"),
            "volume_id": (dm.get("identifiers") or {}).get("volume_id"),
            "dump_contract": dm.get("dump_contract_version"),
            "dump_manifest_sha256": _sha256_file(dm_path),
            "blocks": (dm.get("counts") or {}).get("blocks"),
            "files": fentries,
        })
    _job_progress(conn, job_id, 2, total,
                  f"dumps verified ({len(dumps_entries)})")

    # ---- 3. build the deterministic release zip --------------------------
    release_id = "rel-" + hashlib.sha256(
        (coll_id + content_sha).encode("utf-8")).hexdigest()[:8]
    release_dir = os.path.join(knowledge_data_dir(), "releases", release_id)
    os.makedirs(release_dir, exist_ok=True)
    zip_path = os.path.join(release_dir, f"release-{release_id}.zip")

    # Idempotent: a row with this (collection, content) + zip on disk -> reuse
    existing = conn.execute(
        "SELECT release_id, zip_path, zip_sha256 FROM knowledge_releases "
        "WHERE collection_id=? AND content_sha256=?",
        (coll_id, content_sha)).fetchone()
    if existing and os.path.isfile(existing["zip_path"]):
        _audit_log(conn, coll_id, "release", "release_reused", "ok",
                   {"release_id": existing["release_id"],
                    "content_sha256": content_sha})
        _job_progress(conn, job_id, total, total,
                      f"reused {existing['release_id']}")
        return

    members = []  # (arcname, abs_path)
    # corpus layer
    members.append(("corpus/" + ARCHIVE_NAME, archive))
    members.append(("corpus/corpus-manifest.json",
                    os.path.join(corpus_dir, "corpus-manifest.json")))
    for name in CORPUS_DATA_FILES:
        members.append(("corpus/" + name, os.path.join(corpus_dir, name)))
    # dumps layer
    for de in dumps_entries:
        for fe in de["files"]:
            members.append(
                (f"dumps/{de['file_id']}/{fe['name']}",
                 os.path.join(dumps_root, de["file_id"], fe["name"])))

    _job_progress(conn, job_id, 3, total, "pack release data zip")
    _write_release_zip(zip_path, members)
    zip_sha = _sha256_file(zip_path)
    zip_size = os.path.getsize(zip_path)

    # ---- 4. release manifest (chained hashes) + README -------------------
    # The manifest is a SIDE-CAR (NOT inside the zip) — exactly like corpus
    # c-1: the container cannot hash itself, so the manifest sits alongside
    # and carries the hash of the data zip it describes.
    dumps_chain = hashlib.sha256(
        "|".join(sorted(e["dump_manifest_sha256"]
                        for e in dumps_entries)).encode("utf-8")).hexdigest()
    manifest = {
        "release_contract": "rel-1",
        "release_id": release_id,
        "collection_id": coll_id,
        "collection_name": coll["name"],
        "collection_slug": coll["slug"],
        "build_iv_id": build["iv_id"],
        "generated_at": _now(),
        "generator": "knowledge-studio/release",
        "data_zip": {"name": os.path.basename(zip_path), "sha256": zip_sha,
                     "size_bytes": zip_size,
                     "members": [m[0] for m in sorted(members,
                                                       key=lambda x: x[0])]},
        "corpus": {
            "contract": "c-1",
            "archive": {"name": ARCHIVE_NAME, "sha256": real_archive,
                        "size_bytes": os.path.getsize(archive)},
            "manifest_sha256": cman_sha,
            "files": corpus_files,
            "blocks_total": (cman.get("counts") or {}).get("blocks_total"),
        },
        "dumps": {
            "contract": "d-1",
            "count": len(dumps_entries),
            "entries": dumps_entries,
        },
        "chained": {
            "corpus_archive_sha256": real_archive,
            "dumps_root_sha256": dumps_chain,
            "data_zip_sha256": zip_sha,
        },
        "provenance": {
            "es_alias": coll["es_alias"],
            "es_index_status": build["es_index_status"],
            "search_status": build["search_status"],
            "schema_version": build["schema_version"],
            "normalization_version": build["norm_version"],
            "chunking_version": build["chunking_version"],
        },
    }
    m_bytes = json.dumps(manifest, ensure_ascii=False,
                         indent=2).encode("utf-8")
    with open(os.path.join(release_dir, "release-manifest.json"),
              "wb") as fh:
        fh.write(m_bytes)

    readme = _release_readme(coll, build, manifest, dumps_entries)
    with open(os.path.join(release_dir, "README.md"), "w",
              encoding="utf-8") as fh:
        fh.write(readme)

    # ---- 5. RAG (guarded) ------------------------------------------------
    _job_progress(conn, job_id, 4, total, "rag ingest (guarded)")
    rag_status, rag_detail = _rag_ingest(conn, coll_id, build,
                                         {"release_id": release_id,
                                          "zip_sha256": zip_sha,
                                          "zip_path": zip_path},
                                         manifest)

    # ---- 6. persist release row (upsert by content) ----------------------
    now = _now()
    conn.execute(
        """INSERT INTO knowledge_releases
           (release_id, collection_id, build_iv_id, content_sha256,
            zip_path, zip_sha256, size_bytes, manifest, rag_status,
            created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(release_id) DO UPDATE SET
             build_iv_id=excluded.build_iv_id,
             zip_path=excluded.zip_path,
             zip_sha256=excluded.zip_sha256,
             size_bytes=excluded.size_bytes,
             manifest=excluded.manifest,
             rag_status=excluded.rag_status""",
        (release_id, coll_id, build["iv_id"], content_sha, zip_path,
         zip_sha, zip_size,
         json.dumps(manifest, ensure_ascii=False), rag_status, now))
    conn.commit()
    _audit_log(conn, coll_id, "release", "release_built", "ok",
               {"release_id": release_id, "content_sha256": content_sha,
                "zip_sha256": zip_sha, "size_bytes": zip_size,
                "dumps": len(dumps_entries), "rag_status": rag_status})
    _job_progress(conn, job_id, total, total, f"release {release_id}")


def _sha256_file(path, chunk=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for c in iter(lambda: f.read(chunk), b""):
            h.update(c)
    return h.hexdigest()


def _write_release_zip(path, members):
    """Deterministic release zip: fixed member order (sorted by arcname),
    fixed date 1980-01-01, deflate. No self-hash member (like corpus c-1)."""
    import zipfile
    ordered = sorted(members, key=lambda m: m[0])
    fixed_date = (1980, 1, 1, 0, 0, 0)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for arcname, abspath in ordered:
            zi = zipfile.ZipInfo(arcname, date_time=fixed_date)
            zi.compress_type = zipfile.ZIP_DEFLATED
            zi.external_attr = 0o644 << 16
            with open(abspath, "rb") as f:
                data = f.read()
            z.writestr(zi, data)


def _release_readme(coll, build, manifest, dumps_entries):
    c = manifest["corpus"]
    lines = [
        "# Persian Corpus Toolkit — Release " + manifest["release_id"],
        "",
        "This release is a **self-contained, verifiable** package of the "
        "canonical corpus and its source dumps.",
        "",
        "## On-disk layout",
        f"- `release-{manifest['release_id']}.zip` — DATA ONLY (corpus + "
        f"dumps); sha256 `{manifest['data_zip']['sha256']}`",
        "- `release-manifest.json` — side-car: chained hash of every layer "
        "(NOT inside the zip, so the zip can be hashed)",
        "- `README.md` — this file",
        "",
        "## Provenance",
        f"- Collection: {coll['name']} (`{coll['slug']}`, "
        f"`{coll['collection_id']}`)",
        f"- Build: `{build['iv_id']}` (content sha "
        f"`{build['content_sha256']}`)",
        f"- Schema version: {build['schema_version']} · "
        f"normalization: {build['norm_version']} · "
        f"chunking: {build['chunking_version']}",
        f"- ES: {build['es_index_status']} · search acceptance: "
        f"{build['search_status']}",
        f"- Generated at: {manifest['generated_at']}",
        "",
        "## Contents (layered + chained hashes)",
        f"- `corpus/corpus-data.zip` — canonical c-1 archive "
        f"(sha256 `{c['archive']['sha256']}`, "
        f"{c['blocks_total']} blocks)",
        f"- `corpus/corpus-manifest.json` — sha256 "
        f"`{manifest['corpus']['manifest_sha256']}`",
        f"- `corpus/*.jsonl` — the 4 c-1 streams (raw/normalized × full/unique)",
        f"- `dumps/<file_id>/` — {len(dumps_entries)} source dumps (d-1), "
        "each re-validated (V1..V11)",
        "",
        "## Verification (run in any environment)",
        "1. Recompute `sha256` of the data zip and compare with "
        "`data_zip.sha256` in `release-manifest.json`.",
        "2. Inside the zip: recompute `sha256(corpus/corpus-data.zip)` and "
        "compare with `corpus.archive.sha256` (must also equal the build's "
        "content sha).",
        "3. For each `dumps/<file_id>/`, re-run the d-1 validator "
        "(`factory.dump.validate_dump`) — all V1..V11 checks must pass.",
        "The release is trustworthy if and only if all three match.",
        "",
    ]
    return "\n".join(lines)


_JOB_KINDS["process_document"] = _job_kind_process_document
_JOB_KINDS["process_batch"] = _job_kind_process_batch
_JOB_KINDS["process_batch_retry"] = _job_kind_process_batch_retry
_JOB_KINDS["corpus_build"] = _job_kind_corpus_build
_JOB_KINDS["search_acceptance"] = _job_kind_search_acceptance
_JOB_KINDS["release"] = _job_kind_release


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

def register_knowledge_routes(app, get_db):
    require_auth = make_require_auth(get_db)

    # ── Collections (PCM-14A, unchanged contract) ──────────────────────

    @app.route("/api/knowledge/collections", methods=["GET"])
    @require_auth
    def knowledge_collections():
        db = get_db()
        ensure_knowledge_schema(db)
        _recover_interrupted(db)

        search = (request.args.get("search") or "").strip()
        subject = (request.args.get("subject") or "").strip()
        sort = request.args.get("sort") or "updated_at"
        order = "ASC" if (request.args.get("order") or "").upper() == "ASC" else "DESC"
        page = max(1, int(request.args.get("page") or 1))
        per_page = min(100, max(1, int(request.args.get("per_page") or 20)))

        where, params = [], []
        if search:
            where.append("(name LIKE ? OR slug LIKE ?)")
            like = f"%{search}%"
            params.extend([like, like])
        if subject:
            where.append("subject = ?")
            params.append(subject)
        where_sql = ("WHERE " + " AND ".join(where)) if where else ""

        sortable = {
            "name": "c.name", "slug": "c.slug", "updated_at": "c.updated_at",
            "created_at": "c.created_at", "book_count": "c.book_count",
            "subject": "c.subject",
        }
        sort_col = sortable.get(sort, "c.updated_at")
        total = db.execute(
            f"SELECT COUNT(*) AS n FROM knowledge_collections c {where_sql}", params
        ).fetchone()["n"]
        rows = db.execute(
            f"""SELECT c.id, c.collection_id, c.name, c.slug, c.description,
                       c.subject, c.language, c.collection_version,
                       c.schema_version, c.normalization_version,
                       c.chunking_version, c.es_alias, c.current_index_build,
                       c.book_count, c.chunk_count, c.indexing_status,
                       c.validation_status, c.access_policy,
                       c.created_at, c.updated_at
               FROM knowledge_collections c
               {where_sql}
               ORDER BY {sort_col} {order}, c.id DESC
               LIMIT ? OFFSET ?""",
            (*params, per_page, (page - 1) * per_page),
        ).fetchall()
        return jsonify({
            "collections": [dict(r) for r in rows],
            "total": total,
            "page": page,
            "per_page": per_page,
            "total_pages": (total + per_page - 1) // per_page,
        })

    @app.route("/api/knowledge/collections", methods=["POST"])
    @require_auth
    def knowledge_create_collection():
        db = get_db()
        ensure_knowledge_schema(db)
        data = request.get_json(silent=True) or {}

        name = _clean_name(data.get("name"))
        if not name:
            return jsonify({"ok": False, "message": "نام کالکشن الزامی است"}), 400
        # Uppercase input is normalized, not rejected: 'OloomAqli' ->
        # 'oloomaqli' and must collide with an existing lowercase slug.
        slug = str(data.get("slug") or "").strip().lower()
        if not SLUG_RE.match(slug) or len(slug) < 2 or len(slug) > SLUG_MAX:
            return jsonify({
                "ok": False,
                "message": "نام فنی (slug) باید ۲ تا ۶۴ کاراکتر، فقط حروف کوچک انگلیسی، اعداد و خط تیره باشد",
                "field": "slug",
            }), 400
        description = _clean_name(data.get("description"))
        subject = _clean_name(data.get("subject"))
        language = str(data.get("language") or "fa").strip()[:8] or "fa"

        dup = db.execute("SELECT 1 FROM knowledge_collections WHERE slug=?",
                         (slug,)).fetchone()
        if dup:
            return jsonify({
                "ok": False,
                "message": f"کالکشنی با نام فنی «{slug}» از قبل وجود دارد",
                "field": "slug",
            }), 409
        dup_alias = db.execute(
            "SELECT 1 FROM knowledge_collections WHERE es_alias=?",
            (_index_alias(slug),)).fetchone()
        if dup_alias:
            return jsonify({"ok": False,
                            "message": "این alias Elasticsearch درگیر است"}), 409

        now = _now()
        row = db.execute(
            """INSERT INTO knowledge_collections
               (collection_id, name, slug, description, subject, language,
                es_alias, indexing_status, validation_status, access_policy,
                created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, 'none', 'pending', 'auth', ?, ?)""",
            (_collection_id(slug), name, slug, description, subject, language,
             _index_alias(slug), now, now),
        )
        db.commit()
        row = _collection_row(db, row.lastrowid)
        return jsonify({"ok": True, "collection": dict(row)}), 201

    @app.route("/api/knowledge/collections/<int:coll_id>", methods=["GET"])
    @require_auth
    def knowledge_collection_detail(coll_id):
        db = get_db()
        ensure_knowledge_schema(db)
        _recover_interrupted(db)
        row = _collection_row(db, coll_id)
        if not row:
            return jsonify({"ok": False, "message": "کالکشن پیدا نشد"}), 404
        item = dict(row)
        item["documents"] = [
            dict(r) for r in db.execute(
                """SELECT id, document_id, file_name, relative_path, sha256,
                          file_size, file_id, status, blocks_count,
                          chars_count, quality_status, quality_score, error,
                          created_at, updated_at
                   FROM knowledge_collection_documents
                   WHERE collection_id = ?
                   ORDER BY id DESC""",
                (row["collection_id"],))
        ]
        item["index_builds"] = [
            dict(r) for r in db.execute(
                """SELECT iv_id, es_index, es_alias, schema_version,
                          norm_version, chunking_version, chunk_count,
                          status, created_at, completed_at,
                          content_sha256, out_dir, es_index_status, es_detail
                   FROM knowledge_index_builds
                   WHERE collection_id = ?
                   ORDER BY created_at DESC, iv_id DESC""",
                 (row["collection_id"],))
        ]
        item["metadata_fields"] = _meta_fields(db, row["collection_id"])
        # PCM-20.9 Stage C — approved corpus schema (null until approved)
        item["schema"] = _collection_approved_schema(
            db, row["collection_id"])
        return jsonify({"ok": True, "collection": item})

    @app.route("/api/knowledge/collections/<int:coll_id>", methods=["PATCH"])
    @require_auth
    def knowledge_update_collection(coll_id):
        db = get_db()
        ensure_knowledge_schema(db)
        row = _collection_row(db, coll_id)
        if not row:
            return jsonify({"ok": False, "message": "کالکشن پیدا نشد"}), 404
        data = request.get_json(silent=True) or {}

        name = _clean_name(data.get("name"))
        if name is not None and not name:
            return jsonify({"ok": False, "field": "name",
                            "message": "نام نمی‌تواند خالی باشد"}), 400
        description = _clean_name(data.get("description"))
        subject = _clean_name(data.get("subject"))

        sets, params = [], []
        if name is not None:
            sets.append("name = ?")
            params.append(name)
        if description is not None:
            sets.append("description = ?")
            params.append(description)
        if subject is not None:
            sets.append("subject = ?")
            params.append(subject)
        if not sets:
            return jsonify({"ok": False,
                            "message": "مقداری برای ویرایش فرستاده نشده"}), 400
        # Display-name edit never touches id/slug/alias/versions (PCM-14 §4);
        # collection_version bumps only on content changes (PCM-14B+).
        sets.append("updated_at = ?")
        params.append(_now())
        params.append(coll_id)
        db.execute(
            f"UPDATE knowledge_collections SET {', '.join(sets)} WHERE id = ?",
            params,
        )
        db.commit()
        return jsonify({"ok": True,
                        "collection": dict(_collection_row(db, coll_id))})

    @app.route("/api/knowledge/collections/<int:coll_id>/builds", methods=["GET"])
    @require_auth
    def knowledge_collection_builds(coll_id):
        db = get_db()
        ensure_knowledge_schema(db)
        row = _collection_row(db, coll_id)
        if not row:
            return jsonify({"ok": False, "message": "کالکشن پیدا نشد"}), 404
        builds = [
            dict(r) for r in db.execute(
                """SELECT iv_id, es_index, es_alias, schema_version,
                          norm_version, chunking_version, chunk_count,
                          status, created_at, completed_at,
                          content_sha256, out_dir, es_index_status,
                          es_detail, search_status, search_detail
                   FROM knowledge_index_builds
                   WHERE collection_id = ?
                   ORDER BY created_at DESC, iv_id DESC""",
                  (row["collection_id"],))
        ]
        return jsonify({"ok": True,
                        "collection_id": row["collection_id"],
                        "current": row["current_index_build"],
                        "builds": builds})

    @app.route("/api/knowledge/subjects", methods=["GET"])
    @require_auth
    def knowledge_subjects():
        db = get_db()
        ensure_knowledge_schema(db)
        rows = db.execute(
            "SELECT subject, COUNT(*) AS n FROM knowledge_collections "
            "WHERE subject IS NOT NULL AND subject != '' "
            "GROUP BY subject ORDER BY n DESC, subject"
        ).fetchall()
        return jsonify({"subjects": [dict(r) for r in rows]})

    # ── Documents / Word Library (PCM-14B) ─────────────────────────────

    def _validate_upload_file(f):
        """Return (file_name, size) or raise ValueError.

        Security: basename only (path traversal impossible), size cap,
        .docx extension required (magic-byte validation happens in the
        factory intake, which also rejects non-zip / OLE2 / empty).
        """
        raw = f.filename or ""
        name = os.path.basename(str(raw).replace("\\", "/"))
        if not name or name.startswith("."):
            raise ValueError("نام فایل معتبر نیست")
        if len(name) > 255:
            raise ValueError("نام فایل بیش از حد بلند است")
        ext = os.path.splitext(name)[1].lower()
        if ext != ".docx":
            raise ValueError("فقط فایل DOCX مجاز است")
        return name, ext

    @app.route("/api/knowledge/collections/<int:coll_id>/documents",
               methods=["POST"])
    @require_auth
    def knowledge_add_document(coll_id):
        db = get_db()
        ensure_knowledge_schema(db)
        _recover_interrupted(db)
        row = _collection_row(db, coll_id)
        if not row:
            return jsonify({"ok": False, "message": "کالکشن پیدا نشد"}), 404
        f = request.files.get("file")
        if f is None:
            return jsonify({"ok": False, "message": "فایلی آپلود نشده است",
                            "field": "file"}), 400
        try:
            name, ext = _validate_upload_file(f)
        except ValueError as e:
            return jsonify({"ok": False, "message": str(e),
                            "field": "file"}), 400

        # Stream to temp, enforcing the size cap as we go.
        tmp = None
        size = 0
        h = hashlib.sha256()
        try:
            import tempfile
            fd, tmp = tempfile.mkstemp(suffix=ext, prefix="kdoc_")
            with os.fdopen(fd, "wb") as out:
                while True:
                    chunk = f.stream.read(1 << 20)
                    if not chunk:
                        break
                    size += len(chunk)
                    if size > MAX_UPLOAD_BYTES:
                        raise ValueError(
                            f"فایل بزرگ‌تر از ۵۰ مگابایت است ({size} بایت)")
                    out.write(chunk)
                    h.update(chunk)
            if size == 0:
                raise ValueError("فایل خالی (0 بایت) است")
            sha = h.hexdigest()
        except ValueError as e:
            if tmp and os.path.exists(tmp):
                os.remove(tmp)
            return jsonify({"ok": False, "message": str(e),
                            "field": "file"}), 400
        except Exception as e:  # noqa: BLE001
            if tmp and os.path.exists(tmp):
                os.remove(tmp)
            return jsonify({"ok": False, "message": f"خواندن فایل ناموفق بود: {e}",
                            "field": "file"}), 400

        cid = row["collection_id"]
        dup = db.execute(
            "SELECT document_id FROM knowledge_collection_documents "
            "WHERE collection_id=? AND sha256=?", (cid, sha)).fetchone()
        if dup:
            os.remove(tmp)
            return jsonify({"ok": False,
                            "message": "این فایل (همان SHA-256) قبلا‌ در این کالکشن ثبت شده",
                            "code": "duplicate",
                            "existing_document_id": dup["document_id"]}), 409

        file_id = "f-" + sha[:8]
        dst = _stored_file_path(sha, file_id, ext)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.move(tmp, dst)

        relative_path = (request.form.get("relative_path") or "").strip()[:512]
        now = _now()
        db.execute(
            """INSERT INTO knowledge_collection_documents
               (collection_id, document_id, file_name, relative_path, sha256,
                file_size, file_id, status, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, 'uploaded', ?, ?)""",
            (cid, _doc_id(cid, sha), name, relative_path or None, sha, size,
              file_id, now, now))
        db.commit()
        doc = _doc_row(db, _doc_id(cid, sha))
        return jsonify({"ok": True, "document": dict(doc),
                        "stored_path": "files/" + sha[:12] + "/" +
                                       os.path.basename(dst)}), 201

    @app.route("/api/knowledge/collections/<int:coll_id>/documents",
               methods=["GET"])
    @require_auth
    def knowledge_list_documents(coll_id):
        db = get_db()
        ensure_knowledge_schema(db)
        _recover_interrupted(db)
        row = _collection_row(db, coll_id)
        if not row:
            return jsonify({"ok": False, "message": "کالکشن پیدا نشد"}), 404

        search = (request.args.get("search") or "").strip()
        status = (request.args.get("status") or "").strip()
        page = max(1, int(request.args.get("page") or 1))
        per_page = min(100, max(1, int(request.args.get("per_page") or 50)))

        where, params = ["collection_id = ?"], [row["collection_id"]]
        if search:
            where.append("(file_name LIKE ? OR document_id LIKE ?)")
            like = f"%{search}%"
            params.extend([like, like])
        if status:
            if status not in DOC_STATUSES:
                return jsonify({"ok": False, "field": "status",
                                "message": "وضعیت نامعتبر"}), 400
            where.append("status = ?")
            params.append(status)
        where_sql = "WHERE " + " AND ".join(where)
        total = db.execute(
            f"SELECT COUNT(*) AS n FROM knowledge_collection_documents {where_sql}",
            params).fetchone()["n"]
        rows = db.execute(
            f"""SELECT id, document_id, file_name, relative_path, sha256,
                       file_size, file_id, work_id, edition_id, volume_id,
                       status, blocks_count, chars_count,
                       quality_status, quality_score, error, created_at, updated_at
                FROM knowledge_collection_documents
               {where_sql}
               ORDER BY id DESC LIMIT ? OFFSET ?""",
            (*params, per_page, (page - 1) * per_page)).fetchall()
        return jsonify({"documents": [dict(r) for r in rows],
                        "total": total, "page": page, "per_page": per_page,
                        "total_pages": (total + per_page - 1) // per_page})

    @app.route("/api/knowledge/documents/<doc_id>", methods=["GET"])
    @require_auth
    def knowledge_document_detail(doc_id):
        db = get_db()
        ensure_knowledge_schema(db)
        _recover_interrupted(db)
        d = _doc_row(db, doc_id)
        if not d:
            return jsonify({"ok": False, "message": "سند پیدا نشد"}), 404
        item = dict(d)
        item["metadata"] = _meta_values(db, document_id=doc_id)
        # extracted biblio fields (extract-only, never invented)
        extracted = {}
        if d["out_dir"] and os.path.isdir(factory_out_dir(d["file_id"] or "")):
            p = os.path.join(factory_out_dir(d["file_id"]), "document.json")
            if os.path.isfile(p):
                try:
                    with open(p, encoding="utf-8") as fh:
                        extracted = (json.load(fh).get("metadata") or {})
                except (OSError, ValueError):
                    extracted = {}
        item["extracted"] = extracted
        return jsonify({"ok": True, "document": item})

    @app.route("/api/knowledge/documents/<doc_id>/structure", methods=["GET"])
    @require_auth
    def knowledge_document_structure(doc_id):
        db = get_db()
        ensure_knowledge_schema(db)
        d = _doc_row(db, doc_id)
        if not d:
            return jsonify({"ok": False, "message": "سند پیدا نشد"}), 404
        if not d["out_dir"] or not d["file_id"]:
            return jsonify({"ok": False,
                            "message": "سند هنوز پردازش نشده است"}), 409
        p = os.path.join(factory_out_dir(d["file_id"]), "document.json")
        if not os.path.isfile(p):
            return jsonify({"ok": False,
                            "message": "خروجی پردازش روی دیسک پیدا نشد"}), 409
        with open(p, encoding="utf-8") as fh:
            data = json.load(fh)
        return jsonify({"ok": True,
                        "structure": data.get("structure") or {},
                        "work_id": data.get("work_id"),
                        "edition_id": data.get("edition_id"),
                        "volume_id": data.get("volume_id")})

    @app.route("/api/knowledge/documents/<doc_id>/quality", methods=["GET"])
    @require_auth
    def knowledge_document_quality(doc_id):
        db = get_db()
        ensure_knowledge_schema(db)
        d = _doc_row(db, doc_id)
        if not d:
            return jsonify({"ok": False, "message": "سند پیدا نشد"}), 404
        if not d["out_dir"] or not d["file_id"]:
            return jsonify({"ok": False,
                            "message": "سند هنوز پردازش نشده است"}), 409
        p = os.path.join(factory_out_dir(d["file_id"]), "quality-report.json")
        if not os.path.isfile(p):
            return jsonify({"ok": False,
                            "message": "گزارش کیفیت روی دیسک پیدا نشد"}), 409
        with open(p, encoding="utf-8") as fh:
            data = json.load(fh)
        return jsonify({"ok": True, "quality": data})

    @app.route("/api/knowledge/documents/<doc_id>/blocks", methods=["GET"])
    @require_auth
    def knowledge_document_blocks(doc_id):
        db = get_db()
        ensure_knowledge_schema(db)
        d = _doc_row(db, doc_id)
        if not d:
            return jsonify({"ok": False, "message": "سند پیدا نشد"}), 404
        if not d["out_dir"] or not d["file_id"]:
            return jsonify({"ok": False,
                            "message": "سند هنوز پردازش نشده است"}), 409
        p = os.path.join(factory_out_dir(d["file_id"]), "blocks.jsonl")
        if not os.path.isfile(p):
            return jsonify({"ok": False,
                            "message": "خروجی بلوک‌ها روی دیسک پیدا نشد"}), 409
        btype = (request.args.get("type") or "").strip()
        limit = min(BLOCKS_PAGE, max(1, int(request.args.get("limit") or 100)))
        offset = max(0, int(request.args.get("offset") or 0))
        records = []
        with open(p, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                if btype and rec.get("type") != btype:
                    continue
                records.append(rec)
        total = len(records)
        page = records[offset:offset + limit]
        return jsonify({"ok": True, "blocks": page, "total": total,
                        "offset": offset, "limit": limit})

    @app.route("/api/knowledge/documents/<doc_id>/file", methods=["GET"])
    @require_auth
    def knowledge_document_file(doc_id):
        """Raw / normalized text for side-by-side comparison (spec §6)."""
        db = get_db()
        ensure_knowledge_schema(db)
        d = _doc_row(db, doc_id)
        if not d:
            return jsonify({"ok": False, "message": "سند پیدا نشد"}), 404
        view = (request.args.get("view") or "raw").strip().lower()
        if view not in ("raw", "normalized"):
            return jsonify({"ok": False, "field": "view",
                            "message": "view باید raw یا normalized باشد"}), 400
        if not d["out_dir"] or not d["file_id"]:
            return jsonify({"ok": False,
                            "message": "سند هنوز پردازش نشده است"}), 409
        p = os.path.join(factory_out_dir(d["file_id"]), "blocks.jsonl")
        if not os.path.isfile(p):
            return jsonify({"ok": False,
                            "message": "خروجی بلوک‌ها روی دیسک پیدا نشد"}), 409
        limit = min(BLOCKS_PAGE, max(1, int(request.args.get("limit") or 100)))
        offset = max(0, int(request.args.get("offset") or 0))
        texts, total = [], 0
        with open(p, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                total += 1
                if total - 1 < offset:
                    continue
                if len(texts) >= limit:
                    break
                if view == "raw":
                    texts.append(rec.get("raw_text") or "")
                else:
                    texts.append(rec.get("normalized_text") or "")
        return jsonify({"ok": True, "view": view,
                        "text": "\n".join(texts),
                        "total_blocks": total,
                        "offset": offset, "limit": limit})

    @app.route("/api/knowledge/collections/<int:coll_id>/documents/<doc_id>",
               methods=["DELETE"])
    @require_auth
    def knowledge_detach_document(coll_id, doc_id):
        """Detach a book from the collection.

        The stored original file is NOT deleted (it may be shared /
        re-registered); only the registry link + metadata values go.
        """
        db = get_db()
        ensure_knowledge_schema(db)
        row = _collection_row(db, coll_id)
        if not row:
            return jsonify({"ok": False, "message": "کالکشن پیدا نشد"}), 404
        cid = row["collection_id"]
        d = db.execute(
            "SELECT id FROM knowledge_collection_documents "
            "WHERE document_id=? AND collection_id=?", (doc_id, cid)).fetchone()
        if not d:
            return jsonify({"ok": False, "message": "سند در این کالکشن نیست"}), 404
        db.execute(
            "DELETE FROM knowledge_metadata_values WHERE document_id=?", (doc_id,))
        db.execute(
            "DELETE FROM knowledge_collection_documents WHERE id=?", (d["id"],))
        _refresh_book_count(db, cid)
        db.commit()
        return jsonify({"ok": True, "detached": doc_id})

    @app.route("/api/knowledge/documents/<doc_id>/process", methods=["POST"])
    @require_auth
    def knowledge_process_document(doc_id):
        """(Re)process with the Word Factory. Idempotent via job_key."""
        db = get_db()
        ensure_knowledge_schema(db)
        _recover_interrupted(db)
        d = _doc_row(db, doc_id)
        if not d:
            return jsonify({"ok": False, "message": "سند پیدا نشد"}), 404
        job, created = _submit_job(
            db, f"process_document:{doc_id}", "process_document",
            d["collection_id"], None, total=1,
            idempotency_key=f"doc:{doc_id}:{d['sha256']}")
        code = 202 if created else 200
        return jsonify({"ok": True, "job": job, "resubmitted": not created}), code

    @app.route("/api/knowledge/documents/<doc_id>/approve", methods=["POST"])
    @require_auth
    def knowledge_approve_document(doc_id):
        db = get_db()
        ensure_knowledge_schema(db)
        d = _doc_row(db, doc_id)
        if not d:
            return jsonify({"ok": False, "message": "سند پیدا نشد"}), 404
        if d["status"] not in ("parsed", "needs_review"):
            return jsonify({"ok": False,
                            "message": "فقط اسناد parsed/needs_review قابل تأییدند"}), 409
        db.execute("UPDATE knowledge_collection_documents SET status='approved', "
                   "updated_at=? WHERE id=?", (_now(), d["id"]))
        _refresh_book_count(db, d["collection_id"])
        db.commit()
        return jsonify({"ok": True, "document": dict(_doc_row(db, doc_id))})

    # ── Import batches (folder-based registration, PCM-14B §2) ─────────

    @app.route("/api/knowledge/import/batches", methods=["POST"])
    @require_auth
    def knowledge_create_batch():
        db = get_db()
        ensure_knowledge_schema(db)
        _recover_interrupted(db)
        data = request.get_json(silent=True) or {}
        cid = str(data.get("collection_id") or "").strip()
        coll = db.execute(
            "SELECT collection_id FROM knowledge_collections WHERE collection_id=?",
            (cid,)).fetchone()
        if not coll:
            return jsonify({"ok": False, "field": "collection_id",
                            "message": "کالکشن پیدا نشد"}), 404
        files = data.get("files") or []
        if not files:
            return jsonify({"ok": False, "field": "files",
                            "message": "فهرست فایل پوشه خالی است"}), 400
        if len(files) > MAX_FILES_PER_BATCH:
            return jsonify({"ok": False, "field": "files",
                            "message": f"حداکثر {MAX_FILES_PER_BATCH} فایل در هر ثبت"}), 400

        now = _now()
        batch_id = "b-" + hashlib.sha256(
            (cid + now + json.dumps(files, sort_keys=True)).encode("utf-8")
        ).hexdigest()[:8]
        plan = []
        plan_rows = []  # PCM-20.9 Stage A — persisted plan (knowledge_batch_files)
        for i, f in enumerate(files):
            if not isinstance(f, dict):
                plan.append({"index": i, "status": "invalid",
                             "reason": "entry not an object"})
                plan_rows.append((i, f"entry-{i}", None, 0, "invalid",
                                  None, "entry not an object"))
                continue
            name = os.path.basename(str(f.get("name") or "").replace("\\", "/"))
            sha = str(f.get("sha256") or "").strip().lower()
            size = int(f.get("size") or 0)
            entry = {"index": i, "name": name, "sha256": sha or None,
                     "size": size}
            row_doc, row_err = None, None
            if not name or os.path.splitext(name)[1].lower() != ".docx":
                entry["status"] = "invalid_extension"
                row_err = "invalid extension (only .docx)"
            elif not re.match(r"^[0-9a-f]{64}$", sha):
                entry["status"] = "invalid_sha"
                row_err = "invalid SHA-256"
            elif size == 0 or size > MAX_UPLOAD_BYTES:
                entry["status"] = "invalid_size"
                row_err = f"invalid size ({size})"
            else:
                known = db.execute(
                    "SELECT document_id FROM knowledge_collection_documents "
                    "WHERE collection_id=? AND sha256=?",
                    (cid, sha)).fetchone()
                if known:
                    entry["status"] = "duplicate"
                    entry["existing_document_id"] = known["document_id"]
                    row_doc = known["document_id"]
                else:
                    entry["status"] = "pending"
            plan.append(entry)
            plan_rows.append((i, name or f"entry-{i}", sha or None, size,
                              entry["status"], row_doc, row_err))

        pending = sum(1 for e in plan if e["status"] == "pending")
        db.execute(
            """INSERT INTO knowledge_import_batches
               (batch_id, collection_id, folder_name, file_count, status,
                created_at, updated_at)
               VALUES (?, ?, ?, ?, 'planned', ?, ?)""",
            (batch_id, cid,
             _clean_name(data.get("folder_name")) or None,
             len(plan), now, now))
        # PCM-20.9 Stage A — persist the plan so the per-file upload
        # endpoint can match real uploads against it (reliability).
        for (seq, nm, sha, sz, st, doc, err) in plan_rows:
            db.execute(
                """INSERT INTO knowledge_batch_files
                   (batch_id, seq, file_name, sha256, size_bytes, status,
                    document_id, error, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (batch_id, seq, nm, sha, sz, st, doc, err, now, now))
        db.commit()
        return jsonify({
            "ok": True,
            "batch": {"batch_id": batch_id, "collection_id": cid,
                      "file_count": len(plan), "status": "planned"},
            "plan": plan,
            "summary": {
                "total": len(plan),
                "pending": pending,
                "duplicate": sum(1 for e in plan if e["status"] == "duplicate"),
                "invalid": sum(1 for e in plan
                               if e["status"].startswith("invalid")),
            },
        }), 201

    @app.route("/api/knowledge/import/batches/<batch_id>/files",
               methods=["POST"])
    @require_auth
    def knowledge_batch_upload_file(batch_id):
        """PCM-20.9 Stage A — the REAL file upload for a planned batch.

        Multipart upload of one DOCX. The server computes SHA-256, matches
        it against the persisted plan (knowledge_batch_files), stores the
        original (same layout as the single upload) and creates the
        document row linked to this batch.

        Per-file outcomes (idempotent, retryable):
          uploaded        → new document row (status 'uploaded'), 201
          200 duplicate_upload → already uploaded, same document returned
          duplicate       → 409, same SHA already in the collection
          size_mismatch   → 400, SHA in plan but size differs
          not_in_plan     → 400, SHA is not part of this batch's plan
        """
        db = get_db()
        ensure_knowledge_schema(db)
        _recover_interrupted(db)
        b = db.execute(
            "SELECT * FROM knowledge_import_batches WHERE batch_id=?",
            (batch_id,)).fetchone()
        if not b:
            return jsonify({"ok": False, "message": "بچ پیدا نشد"}), 404
        f = request.files.get("file")
        if f is None:
            return jsonify({"ok": False, "field": "file",
                            "message": "فایلی آپلود نشده است"}), 400
        try:
            name, ext = _validate_upload_file(f)
        except ValueError as e:
            return jsonify({"ok": False, "message": str(e),
                            "field": "file"}), 400

        import tempfile
        tmp = None
        size = 0
        h = hashlib.sha256()
        try:
            fd, tmp = tempfile.mkstemp(suffix=ext, prefix="kbatch_")
            with os.fdopen(fd, "wb") as out:
                while True:
                    chunk = f.stream.read(1 << 20)
                    if not chunk:
                        break
                    size += len(chunk)
                    if size > MAX_UPLOAD_BYTES:
                        raise ValueError(
                            f"فایل بزرگ‌تر از ۵۰ مگابایت است ({size} بایت)")
                    out.write(chunk)
                    h.update(chunk)
            if size == 0:
                raise ValueError("فایل خالی (0 بایت) است")
            sha = h.hexdigest()
        except ValueError as e:
            if tmp and os.path.exists(tmp):
                os.remove(tmp)
            return jsonify({"ok": False, "message": str(e),
                            "field": "file"}), 400
        except Exception as e:  # noqa: BLE001
            if tmp and os.path.exists(tmp):
                os.remove(tmp)
            return jsonify({"ok": False,
                            "message": f"خواندن فایل ناموفق بود: {e}",
                            "field": "file"}), 400

        cid = b["collection_id"]
        now = _now()
        planned = db.execute(
            "SELECT id, file_name, sha256, size_bytes, status, document_id "
            "FROM knowledge_batch_files WHERE batch_id=? ORDER BY seq",
            (batch_id,)).fetchall()
        match = next((p for p in planned if p["sha256"] == sha), None)
        if match is None:
            os.remove(tmp)
            return jsonify({"ok": False, "field": "file",
                            "code": "not_in_plan",
                            "message": "این فایل (SHA-256) در پلن ثبت‌شده این بچ نیست",
                            "sha256": sha}), 400
        if match["size_bytes"] != size:
            os.remove(tmp)
            db.execute(
                "UPDATE knowledge_batch_files SET status='size_mismatch', "
                "error=?, updated_at=? WHERE id=?",
                (f"size mismatch: planned {match['size_bytes']} got {size}",
                 now, match["id"]))
            db.commit()
            return jsonify({"ok": False, "field": "file",
                            "code": "size_mismatch",
                            "message": "حجم فایل با پلن مطابقت ندارد",
                            "planned_size": match["size_bytes"],
                            "actual_size": size, "sha256": sha}), 400
        if match["status"] == "uploaded" and match["document_id"]:
            # idempotent retry of an already-uploaded entry
            os.remove(tmp)
            doc = _doc_row(db, match["document_id"])
            return jsonify({"ok": True, "status": "uploaded",
                            "duplicate_upload": True,
                            "document": dict(doc) if doc else None,
                            "sha256": sha})
        dup = db.execute(
            "SELECT document_id FROM knowledge_collection_documents "
            "WHERE collection_id=? AND sha256=?", (cid, sha)).fetchone()
        if dup:
            os.remove(tmp)
            db.execute(
                "UPDATE knowledge_batch_files SET status='duplicate', "
                "document_id=?, error=NULL, updated_at=? WHERE id=?",
                (dup["document_id"], now, match["id"]))
            db.commit()
            return jsonify({"ok": False, "code": "duplicate",
                            "message": "این فایل (همان SHA-256) قبلا‌ در این کالکشن ثبت شده",
                            "existing_document_id": dup["document_id"],
                            "sha256": sha}), 409
        file_id = "f-" + sha[:8]
        dst = _stored_file_path(sha, file_id, ext)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        if os.path.exists(dst):
            os.remove(tmp)  # content already stored (same sha) — reuse
        else:
            shutil.move(tmp, dst)
        doc_id = _doc_id(cid, sha)
        db.execute(
            """INSERT INTO knowledge_collection_documents
               (collection_id, document_id, file_name, relative_path, sha256,
                file_size, file_id, status, batch_id, created_at, updated_at)
               VALUES (?, ?, ?, NULL, ?, ?, ?, 'uploaded', ?, ?, ?)""",
            (cid, doc_id, match["file_name"] or name, sha, size, file_id,
             batch_id, now, now))
        db.execute(
            "UPDATE knowledge_batch_files SET status='uploaded', "
            "document_id=?, error=NULL, updated_at=? WHERE id=?",
            (doc_id, now, match["id"]))
        db.commit()
        doc = _doc_row(db, doc_id)
        return jsonify({"ok": True, "status": "uploaded",
                        "document": dict(doc) if doc else None,
                        "sha256": sha}), 201

    @app.route("/api/knowledge/import/batches", methods=["GET"])
    @require_auth
    def knowledge_list_batches():
        """PCM-17: list the import batches of a collection (paginated).

        Read-only surface for the Studio queue UI: batch rows + per-batch
        pause flag + live queue counters for the collection. All numbers
        come straight from the queue table (single source of truth).
        """
        db = get_db()
        ensure_knowledge_schema(db)
        _recover_interrupted(db)
        cid = (request.args.get("collection_id") or "").strip()
        if not cid:
            return jsonify({"ok": False, "field": "collection_id",
                            "message": "collection_id لازم است"}), 400
        coll = db.execute(
            "SELECT collection_id FROM knowledge_collections WHERE collection_id=?",
            (cid,)).fetchone()
        if not coll:
            return jsonify({"ok": False, "field": "collection_id",
                            "message": "کالکشن پیدا نشد"}), 404
        search = (request.args.get("search") or "").strip()
        page = max(1, int(request.args.get("page") or 1))
        per_page = min(100, max(1, int(request.args.get("per_page") or 50)))

        where, params = ["collection_id = ?"], [cid]
        if search:
            where.append("(batch_id LIKE ? OR folder_name LIKE ?)")
            like = f"%{search}%"
            params.extend([like, like])
        where_sql = "WHERE " + " AND ".join(where)
        total = db.execute(
            f"SELECT COUNT(*) AS n FROM knowledge_import_batches {where_sql}",
            params).fetchone()["n"]
        rows = db.execute(
            f"""SELECT b.*,
                        CASE WHEN EXISTS(
                            SELECT 1 FROM knowledge_queue_control q
                             WHERE q.scope = 'batch:' || b.batch_id
                               AND q.paused = 1)
                         THEN 1 ELSE 0 END AS paused
                FROM knowledge_import_batches b
                {where_sql}
                ORDER BY b.created_at DESC, b.batch_id
                LIMIT ? OFFSET ?""",
            (*params, per_page, (page - 1) * per_page)).fetchall()
        counters = queue_counters(db, cid)
        stages = [
            dict(r) for r in db.execute(
                """SELECT stage, COUNT(*) AS files FROM knowledge_file_queue
                   WHERE stage IS NOT NULL AND collection_id=?
                   GROUP BY stage""", (cid,))]
        return jsonify({"batches": [dict(r) for r in rows],
                        "total": total, "page": page, "per_page": per_page,
                        "total_pages": (total + per_page - 1) // per_page,
                        "queue": {"counters": counters,
                                  "failed_by_stage": stages}})

    @app.route("/api/knowledge/import/batches/<batch_id>", methods=["GET"])
    @require_auth
    def knowledge_batch_detail(batch_id):
        db = get_db()
        ensure_knowledge_schema(db)
        _recover_interrupted(db)
        b = db.execute(
            "SELECT * FROM knowledge_import_batches WHERE batch_id=?",
            (batch_id,)).fetchone()
        if not b:
            return jsonify({"ok": False, "message": "بچ پیدا نشد"}), 404
        # PCM-20.9 Stage A — the persisted plan (per-file status).
        plan_files = [
            dict(r) for r in db.execute(
                "SELECT id, seq, file_name, sha256, size_bytes, status, "
                "document_id, error, updated_at FROM knowledge_batch_files "
                "WHERE batch_id=? ORDER BY seq", (batch_id,))]
        uploaded = sum(1 for p in plan_files if p["status"] == "uploaded")
        # PCM-20.9 Stage A — documents/queue scoped to THIS batch (legacy
        # batches without plan rows fall back to the whole collection).
        clause, params = _batch_scope_clause(db, batch_id)
        qclause, qparams = _batch_scope_clause(db, batch_id, alias="d")
        if clause:
            docs = [
                dict(r) for r in db.execute(
                    f"SELECT id, document_id, file_name, relative_path, "
                    f"sha256, file_size, status, blocks_count, chars_count, "
                    f"quality_status, quality_score, error, created_at, "
                    f"updated_at FROM knowledge_collection_documents "
                    f"WHERE collection_id=?{clause} ORDER BY id",
                    (b["collection_id"], *params))]
            queue = [dict(r) for r in db.execute(
                f"SELECT q.file_key, q.document_id, q.file_name, q.sha256, "
                f"q.status, q.stage, q.attempts, q.last_error, "
                f"q.stage_started_at, q.finished_at, q.duration_ms, "
                f"q.out_dir, q.created_at, q.updated_at "
                f"FROM knowledge_file_queue q JOIN "
                f"knowledge_collection_documents d ON "
                f"d.document_id = q.document_id AND "
                f"d.collection_id = q.collection_id "
                f"WHERE q.collection_id=?{qclause} ORDER BY q.created_at",
                (b["collection_id"], *qparams))]
        else:
            docs = [
                dict(r) for r in db.execute(
                    "SELECT id, document_id, file_name, relative_path, "
                    "sha256, file_size, status, blocks_count, chars_count, "
                    "quality_status, quality_score, error, created_at, "
                    "updated_at FROM knowledge_collection_documents "
                    "WHERE collection_id=? ORDER BY id",
                    (b["collection_id"],))]
            queue = [dict(r) for r in db.execute(
                "SELECT file_key, document_id, file_name, sha256, status, "
                "stage, attempts, last_error, stage_started_at, finished_at, "
                "duration_ms, out_dir, created_at, updated_at "
                "FROM knowledge_file_queue WHERE collection_id=? "
                "ORDER BY created_at", (b["collection_id"],))]
        jobs = [dict(r) for r in db.execute(
            "SELECT job_id, kind, status, stage, progress, total, error, "
            "created_at, updated_at, completed_at FROM knowledge_jobs "
            "WHERE batch_id=? ORDER BY created_at DESC", (batch_id,))]
        ctrl = db.execute(
            "SELECT paused, updated_at FROM knowledge_queue_control WHERE scope=?",
            (queue_scope(batch_id),)).fetchone()
        return jsonify({"ok": True, "batch": dict(b),
                        "plan_files": plan_files,
                        "upload_summary": {
                            "total": len(plan_files),
                            "uploaded": uploaded,
                            "pending": sum(1 for p in plan_files
                                           if p["status"] == "pending"),
                            "duplicate": sum(1 for p in plan_files
                                             if p["status"] == "duplicate"),
                            "invalid": sum(1 for p in plan_files
                                           if p["status"].startswith("invalid")),
                        },
                        "documents": docs, "jobs": jobs,
                        "queue": queue,
                        "paused": bool(ctrl and ctrl["paused"]),
                        "queue_control": dict(ctrl) if ctrl else None})

    @app.route("/api/knowledge/import/batches/<batch_id>/process",
               methods=["POST"])
    @require_auth
    def knowledge_process_batch(batch_id):
        db = get_db()
        ensure_knowledge_schema(db)
        _recover_interrupted(db)
        b = db.execute(
            "SELECT * FROM knowledge_import_batches WHERE batch_id=?",
            (batch_id,)).fetchone()
        if not b:
            return jsonify({"ok": False, "message": "بچ پیدا نشد"}), 404
        # PCM-20.9 Stage A — batch-scoped count (see _batch_scope_clause);
        # legacy pre-20.9 batches keep the collection-wide count.
        clause, params = _batch_scope_clause(db, batch_id)
        n = db.execute(
            f"SELECT COUNT(*) AS n FROM knowledge_collection_documents "
            f"WHERE collection_id=? AND status IN ('uploaded','failed'){clause}",
            (b["collection_id"], *params)).fetchone()["n"]
        planned = db.execute(
            "SELECT COUNT(*) AS n FROM knowledge_batch_files "
            "WHERE batch_id=?", (batch_id,)).fetchone()["n"]
        if planned and n == 0:
            up = db.execute(
                "SELECT COUNT(*) AS n FROM knowledge_batch_files "
                "WHERE batch_id=? AND status='uploaded'",
                (batch_id,)).fetchone()["n"]
            if up == 0:
                return jsonify({"ok": False, "code": "no_files_uploaded",
                                "message": "هنوز هیچ فایلی برای این بچ آپلود نشده؛ ابتدا فایل‌ها را آپلود کنید",
                                "uploaded": 0, "planned": planned}), 409
        db.execute("UPDATE knowledge_import_batches SET status='processing', "
                   "updated_at=? WHERE batch_id=?", (_now(), batch_id))
        db.commit()
        job, created = _submit_job(
            db, f"process_batch:{batch_id}", "process_batch",
            b["collection_id"], batch_id, total=n,
            idempotency_key=f"batch:{batch_id}")
        return jsonify({"ok": True, "job": job, "files_queued": n,
                        "resubmitted": not created}), (202 if created else 200)

    # ── PCM-15 — queue pause/resume + summary ──────────────────────────

    def _batch_or_404(db, batch_id):
        b = db.execute(
            "SELECT * FROM knowledge_import_batches WHERE batch_id=?",
            (batch_id,)).fetchone()
        if not b:
            return None
        return b

    @app.route("/api/knowledge/import/batches/<batch_id>/pause",
               methods=["POST"])
    @require_auth
    def knowledge_pause_batch(batch_id):
        """PCM-15: pause a batch queue. The running worker checks the flag
        before every file and stops cleanly (remaining files stay pending)."""
        db = get_db()
        ensure_knowledge_schema(db)
        _recover_interrupted(db)
        b = _batch_or_404(db, batch_id)
        if not b:
            return jsonify({"ok": False, "message": "بچ پیدا نشد"}), 404
        queue_set_paused(db, queue_scope(batch_id), True)
        ctrl = db.execute(
            "SELECT paused, updated_at FROM knowledge_queue_control WHERE scope=?",
            (queue_scope(batch_id),)).fetchone()
        return jsonify({"ok": True, "paused": True,
                        "scope": queue_scope(batch_id),
                        "queue_control": dict(ctrl)})

    @app.route("/api/knowledge/import/batches/<batch_id>/resume",
               methods=["POST"])
    @require_auth
    def knowledge_resume_batch(batch_id):
        """PCM-15: clear the pause flag (does NOT auto-start a worker —
        resume processing by POSTing /process again; an interrupted/paused
        job is re-executed by the existing job idempotency)."""
        db = get_db()
        ensure_knowledge_schema(db)
        _recover_interrupted(db)
        b = _batch_or_404(db, batch_id)
        if not b:
            return jsonify({"ok": False, "message": "بچ پیدا نشد"}), 404
        queue_set_paused(db, queue_scope(batch_id), False)
        ctrl = db.execute(
            "SELECT paused, updated_at FROM knowledge_queue_control WHERE scope=?",
            (queue_scope(batch_id),)).fetchone()
        return jsonify({"ok": True, "paused": False,
                        "scope": queue_scope(batch_id),
                        "queue_control": dict(ctrl)})

    @app.route("/api/knowledge/import/batches/<batch_id>/retry-failed",
               methods=["POST"])
    @require_auth
    def knowledge_retry_failed_batch(batch_id):
        """PCM-20.9 Stage B — retry ONLY the failed files of a batch.

        Succeeded / needs_review files are untouched (checkpoint/resume):
        a failed run never forces re-processing the whole batch. Each
        failed queue row is re-executed with attempts+1 and safe-stage
        tracking. Idempotent while a retry is pending/running; a completed
        retry can be re-triggered (force_retry). 409 when there is
        nothing to retry.
        """
        db = get_db()
        ensure_knowledge_schema(db)
        _recover_interrupted(db)
        b = db.execute(
            "SELECT * FROM knowledge_import_batches WHERE batch_id=?",
            (batch_id,)).fetchone()
        if not b:
            return jsonify({"ok": False, "message": "بچ پیدا نشد"}), 404
        dclause, dparams = _batch_scope_clause(db, batch_id, alias="d")
        n = db.execute(
            f"""SELECT COUNT(*) AS n FROM knowledge_file_queue q
                 JOIN knowledge_collection_documents d
                   ON d.document_id = q.document_id
                  AND d.collection_id = q.collection_id
                WHERE q.collection_id = ? AND q.status = 'failed'{dclause}""",
            (b["collection_id"], *dparams)).fetchone()["n"]
        if n == 0:
            return jsonify({"ok": False, "code": "no_failed_files",
                            "message": "فایلی با وضعیت ناموفق برای این بچ وجود ندارد",
                            "failed": 0}), 409
        job, created = _submit_job(
            db, f"process_batch_retry:{batch_id}", "process_batch_retry",
            b["collection_id"], batch_id, total=n,
            idempotency_key=f"batch_retry:{batch_id}", force_retry=True)
        return jsonify({"ok": True, "job": job, "files_queued": n,
                        "resubmitted": not created}), (202 if created else 200)

    # ── PCM-20.9 Stage C — corpus schema design & mapping ───────────────
    def _coll_or_404_schema(db, collection_id):
        return db.execute(
            "SELECT * FROM knowledge_collections WHERE collection_id=?",
            (collection_id,)).fetchone()

    def _schema_payload(db, collection_id, schema_id=None):
        versions = _collection_schema_list(db, collection_id)
        approved = _collection_approved_schema(db, collection_id)
        out = {
            "versions": [
                {**v, "fields": json.loads(v["fields"]),
                 "validation": json.loads(v["validation"])
                 if v["validation"] else None}
                for v in versions
            ],
            "approved": (
                {**approved, "fields": json.loads(approved["fields"]),
                 "validation": json.loads(approved["validation"])
                 if approved["validation"] else None}
                if approved else None),
            "default_fields": _default_schema_fields(),
        }
        return out

    @app.route("/api/knowledge/collections/<cid>/schema", methods=["GET"])
    @require_auth
    def knowledge_schema_list(cid):
        """List the corpus schema versions of a collection (newest first),
        plus the approved version and the default field template."""
        db = get_db()
        ensure_knowledge_schema(db)
        c = _coll_or_404_schema(db, cid)
        if not c:
            return jsonify({"ok": False, "message": "کالکشن پیدا نشد"}), 404
        return jsonify({"ok": True, "collection_id": cid,
                        **_schema_payload(db, cid)})

    @app.route("/api/knowledge/collections/<cid>/schema", methods=["POST"])
    @require_auth
    def knowledge_schema_create(cid):
        """Create a NEW schema version draft for the collection.

        Body: {description?, fields?}. fields defaults to the built-in
        block-schema template. Versions are immutable once approved; this
        endpoint always creates a fresh version (version = max+1).
        """
        db = get_db()
        ensure_knowledge_schema(db)
        c = _coll_or_404_schema(db, cid)
        if not c:
            return jsonify({"ok": False, "message": "کالکشن پیدا نشد"}), 404
        data = request.get_json(silent=True) or {}
        description = str(data.get("description") or "").strip()[:500] or None
        fields_in = data.get("fields")
        if fields_in is None:
            normalized, _ = _validate_schema_fields(_default_schema_fields())
        else:
            normalized, errors = _validate_schema_fields(fields_in)
            if errors:
                return jsonify({"ok": False, "field": "fields", "errors": errors,
                                "message": "تعریف فیلدها نامعتبر است"}), 400
        row = db.execute(
            "SELECT COALESCE(MAX(version), 0) AS v "
            "FROM knowledge_schema_versions WHERE collection_id=?",
            (cid,)).fetchone()
        version = row["v"] + 1
        # schema_id is the GLOBAL primary key, but version is per-collection:
        # embed the collection id so two collections can both hold a
        # version-1 schema without a PK collision.
        schema_id = f"sv-{cid}-{version:04d}"
        now = _now()
        db.execute(
            """INSERT INTO knowledge_schema_versions
               (schema_id, collection_id, version, status, description,
                fields, created_at, updated_at)
               VALUES (?, ?, ?, 'draft', ?, ?, ?, ?)""",
            (schema_id, cid, version, description,
             json.dumps(normalized, ensure_ascii=False), now, now))
        db.commit()
        sv = _schema_version_row(db, cid, schema_id)
        return jsonify({"ok": True, "schema": {
            **sv, "fields": json.loads(sv["fields"]), "validation": None}}), 201

    @app.route("/api/knowledge/collections/<cid>/schema/<schema_id>",
               methods=["GET"])
    @require_auth
    def knowledge_schema_detail(cid, schema_id):
        db = get_db()
        ensure_knowledge_schema(db)
        sv = _schema_version_row(db, cid, schema_id)
        if not sv:
            return jsonify({"ok": False, "message": "نسخهٔ اسکیم پیدا نشد"}), 404
        return jsonify({"ok": True, "schema": {
            **sv, "fields": json.loads(sv["fields"]),
            "validation": json.loads(sv["validation"])
            if sv["validation"] else None}})

    @app.route("/api/knowledge/collections/<cid>/schema/<schema_id>",
               methods=["PATCH"])
    @require_auth
    def knowledge_schema_update(cid, schema_id):
        """Update a DRAFT version (description and/or fields).

        Approved versions are immutable — 409. fields are re-validated.
        """
        db = get_db()
        ensure_knowledge_schema(db)
        sv = _schema_version_row(db, cid, schema_id)
        if not sv:
            return jsonify({"ok": False, "message": "نسخهٔ اسکیم پیدا نشد"}), 404
        if sv["status"] == "approved":
            return jsonify({"ok": False, "code": "immutable",
                            "message": "نسخهٔ تأییدشده تغییرناپذیر است — "
                                       "یک نسخهٔ جدید بسازید"}), 409
        data = request.get_json(silent=True) or {}
        sets, params = [], []
        if "description" in data:
            d = str(data.get("description") or "").strip()[:500] or None
            sets.append("description=?"); params.append(d)
        if "fields" in data:
            normalized, errors = _validate_schema_fields(data["fields"])
            if errors:
                return jsonify({"ok": False, "field": "fields",
                                "errors": errors,
                                "message": "تعریف فیلدها نامعتبر است"}), 400
            sets.append("fields=?")
            params.append(json.dumps(normalized, ensure_ascii=False))
        if not sets:
            return jsonify({"ok": False, "message": "مقداری برای ویرایش نیست"}), 400
        sets.append("updated_at=?"); params.append(_now())
        params += [schema_id, cid]
        db.execute(f"""UPDATE knowledge_schema_versions
                        SET {', '.join(sets)}
                        WHERE schema_id=? AND collection_id=?""", params)
        db.commit()
        sv = _schema_version_row(db, cid, schema_id)
        return jsonify({"ok": True, "schema": {
            **sv, "fields": json.loads(sv["fields"]),
            "validation": json.loads(sv["validation"])
            if sv["validation"] else None}})

    @app.route("/api/knowledge/collections/<cid>/schema/<schema_id>/validate",
               methods=["POST"])
    @require_auth
    def knowledge_schema_validate(cid, schema_id):
        """'Design & Validate Schema' — dry-run a version's fields against
        the collection's REAL blocks.jsonl (honest counts, truncated at a
        200k-block cap). Works for draft AND approved versions (read-only:
        does not change the version, only stores the latest report)."""
        db = get_db()
        ensure_knowledge_schema(db)
        sv = _schema_version_row(db, cid, schema_id)
        if not sv:
            return jsonify({"ok": False, "message": "نسخهٔ اسکیم پیدا نشد"}), 404
        fields = json.loads(sv["fields"])
        report = _schema_validate_report(db, cid, fields)
        db.execute("""UPDATE knowledge_schema_versions
                      SET validation=?, updated_at=?
                      WHERE schema_id=? AND collection_id=?""",
                   (json.dumps(report, ensure_ascii=False), _now(),
                    schema_id, cid))
        db.commit()
        return jsonify({"ok": True, "schema_id": schema_id, "report": report})

    @app.route("/api/knowledge/collections/<cid>/schema/<schema_id>/approve",
               methods=["POST"])
    @require_auth
    def knowledge_schema_approve(cid, schema_id):
        """'Approve Schema Version' — the version must be a draft with a
        PASSING validation report (ok=true, at least 1 block scanned).
        Approval is immutable: the version's fields JSON is never touched
        again, and the collection's schema_version is pointed at it."""
        db = get_db()
        ensure_knowledge_schema(db)
        c = _coll_or_404_schema(db, cid)
        if not c:
            return jsonify({"ok": False, "message": "کالکشن پیدا نشد"}), 404
        sv = _schema_version_row(db, cid, schema_id)
        if not sv:
            return jsonify({"ok": False, "message": "نسخهٔ اسکیم پیدا نشد"}), 404
        if sv["status"] == "approved":
            return jsonify({"ok": True, "already": True,
                            "schema_id": schema_id}), 200
        val = json.loads(sv["validation"]) if sv["validation"] else None
        if not val or not val.get("ok") or not val.get("blocks_scanned"):
            return jsonify({"ok": False, "code": "not_validated",
                            "message": "پیش از تأیید باید «اعتبارسنجی» با "
                                       "نتیجهٔ موفق اجرا شود (حداقل یک بلوک)"}), 409
        now = _now()
        db.execute("""UPDATE knowledge_schema_versions
                      SET status='approved', approved_at=?, updated_at=?
                      WHERE schema_id=? AND collection_id=?""",
                   (now, now, schema_id, cid))
        db.execute("""UPDATE knowledge_collections
                      SET schema_version=?, updated_at=?
                      WHERE collection_id=?""", (schema_id, now, cid))
        db.commit()
        _audit_log(db, cid, "schema", "schema_approved", "ok",
                   {"schema_id": schema_id, "version": sv["version"]})
        return jsonify({"ok": True, "schema_id": schema_id,
                        "version": sv["version"], "approved_at": now})

    # ── PCM-20.9 Stage D — canonical corpus build + ES index factory ────

    @app.route("/api/knowledge/collections/<int:coll_id>/corpus/build",
               methods=["POST"])
    @require_auth
    def knowledge_corpus_build(coll_id):
        """Start the Stage D build: per-doc d-1 dumps -> c-1 corpus ->
        guarded ES factory. Idempotent: job keyed corpus_build:<cid>
        (force_retry) and the build row keyed by the corpus archive
        SHA-256 (same content -> REUSED, no rewrite)."""
        db = get_db()
        ensure_knowledge_schema(db)
        row = _collection_row(db, coll_id)
        if not row:
            return jsonify({"ok": False, "message": "کالکشن پیدا نشد"}), 404
        cid = row["collection_id"]
        n = db.execute(
            """SELECT COUNT(*) AS n FROM knowledge_collection_documents
               WHERE collection_id=? AND out_dir IS NOT NULL
                 AND status IN ('parsed','needs_review','approved',
                                'indexed')""",
            (cid,)).fetchone()["n"]
        if not n:
            return jsonify({"ok": False, "code": "no_processed_documents",
                            "message": "هیچ سند پردازش‌شده‌ای برای ساخت "
                                       "پیکره در این کالکشن نیست"}), 409
        job, started = _submit_job(
            db, job_key=f"corpus_build:{cid}", kind="corpus_build",
            collection_id=cid, batch_id=None, total=n,
            idempotency_key=f"corpus_build:{cid}", force_retry=True)
        return jsonify({"ok": True, "queued": started, "job": job,
                        "documents": n}), (202 if started else 200)

    @app.route("/api/knowledge/collections/<int:coll_id>/corpus/builds",
               methods=["GET"])
    @require_auth
    def knowledge_corpus_builds(coll_id):
        """List the canonical corpus builds of a collection (newest
        first). Only builds produced by the Stage D factory (they carry
        a content_sha256); legacy index-build rows are not mixed in."""
        db = get_db()
        ensure_knowledge_schema(db)
        row = _collection_row(db, coll_id)
        if not row:
            return jsonify({"ok": False, "message": "کالکشن پیدا نشد"}), 404
        builds = [
            dict(r) for r in db.execute(
                """SELECT iv_id, es_index, es_alias, schema_version,
                          norm_version, chunking_version, chunk_count,
                          status, created_at, completed_at,
                          content_sha256, out_dir, es_index_status,
                          es_detail, search_status, search_detail
                   FROM knowledge_index_builds
                   WHERE collection_id = ?
                     AND content_sha256 IS NOT NULL
                   ORDER BY created_at DESC, iv_id DESC""",
                  (row["collection_id"],))
        ]
        return jsonify({"ok": True,
                        "collection_id": row["collection_id"],
                        "builds": builds})

    @app.route("/api/knowledge/index-builds/<iv_id>", methods=["GET"])
    @require_auth
    def knowledge_index_build_detail(iv_id):
        """One build row + its canonical corpus manifest (read from the
        on-disk out_dir, when present)."""
        db = get_db()
        ensure_knowledge_schema(db)
        r = db.execute(
            "SELECT * FROM knowledge_index_builds WHERE iv_id=?",
            (iv_id,)).fetchone()
        if not r:
            return jsonify({"ok": False, "message": "بیلد پیدا نشد"}), 404
        item = dict(r)
        manifest = None
        if item.get("out_dir"):
            mp = os.path.join(knowledge_data_dir(), item["out_dir"],
                              "corpus-manifest.json")
            if os.path.isfile(mp):
                try:
                    with open(mp, encoding="utf-8") as fh:
                        manifest = json.load(fh)
                except (OSError, json.JSONDecodeError):
                    manifest = None
        item["manifest"] = manifest
        return jsonify({"ok": True, "build": item})

    # ── PCM-20.9 Stage E — search acceptance + index approval ───────────

    @app.route("/api/knowledge/collections/<int:coll_id>/search-acceptance",
               methods=["POST"])
    @require_auth
    def knowledge_search_acceptance(coll_id):
        """Start the Stage E search acceptance (job, guarded).

        Validates the 10 categories against the LIVE alias of the
        collection's newest Stage D build. Guards: no Stage D build ->
        409; no PCT_ES_URL or no successful ES index -> the job fails
        honestly as BLOCKED (no fabricated results). Idempotency key
        search_acceptance:<cid> (force_retry: re-runnable).
        """
        db = get_db()
        ensure_knowledge_schema(db)
        row = _collection_row(db, coll_id)
        if not row:
            return jsonify({"ok": False, "message": "کالکشن پیدا نشد"}), 404
        cid = row["collection_id"]
        has_build = db.execute(
            """SELECT 1 FROM knowledge_index_builds
               WHERE collection_id=? AND content_sha256 IS NOT NULL
               LIMIT 1""", (cid,)).fetchone()
        if not has_build:
            return jsonify({"ok": False, "code": "no_corpus_build",
                            "message": "هنوز پیکره canonical (Stage D) "
                                       "ساخته نشده — ابتدا «ساخت پیکره»"}), 409
        job, started = _submit_job(
            db, job_key=f"search_acceptance:{cid}",
            kind="search_acceptance", collection_id=cid, batch_id=None,
            total=len(_SEARCH_CATEGORIES),
            idempotency_key=f"search_acceptance:{cid}", force_retry=True)
        return jsonify({"ok": True, "queued": started, "job": job}), \
            (202 if started else 200)

    @app.route("/api/knowledge/index-builds/<iv_id>/approve",
               methods=["POST"])
    @require_auth
    def knowledge_approve_index_build(iv_id):
        """Approve an index version (Stage E gate, RECON §8).

        Hard gate: the build must have a FULL acceptance pass
        (search_status='pass'). Without it -> 409 (no approval on a
        non-validated alias — stop rule «no live alias change without
        acceptance»). On approval: collection.current_index_build +
        validation_status='accepted' + indexing_status='ready'.
        """
        db = get_db()
        ensure_knowledge_schema(db)
        r = db.execute(
            "SELECT * FROM knowledge_index_builds WHERE iv_id=?",
            (iv_id,)).fetchone()
        if not r:
            return jsonify({"ok": False, "message": "بیلد پیدا نشد"}), 404
        if (r["search_status"] or "") != "pass":
            return jsonify(
                {"ok": False, "code": "acceptance_not_passed",
                 "search_status": r["search_status"],
                 "message": "تأیید نسخه‌ی ایندکس فقط بعد از گذر کامل "
                            "اعتبارسنجی جستجو (Stage E) امکان دارد"}), 409
        if (r["es_index_status"] or "") != "success":
            return jsonify(
                {"ok": False, "code": "es_not_success",
                 "es_index_status": r["es_index_status"],
                 "message": "این بیلد ایندکس ES زنده ندارد (es success "
                            "نیست) — قابل تأیید نیست"}), 409
        db.execute(
            """UPDATE knowledge_collections
               SET current_index_build=?, validation_status='accepted',
                   indexing_status='ready', updated_at=?
              WHERE collection_id=?""",
            (iv_id, _now(), r["collection_id"]))
        db.commit()
        _audit_log(db, r["collection_id"], "acceptance", "index_approved",
                   "ok", {"iv_id": iv_id,
                          "search_status": r["search_status"],
                          "es_index_status": r["es_index_status"]})
        return jsonify({"ok": True, "iv_id": iv_id,
                        "collection_id": r["collection_id"],
                        "validation_status": "accepted"})

    # ── PCM-20.9 Final — release bundle + audit trail ─────────────────────

    @app.route("/api/knowledge/collections/<int:coll_id>/release",
               methods=["POST"])
    @require_auth
    def knowledge_release(coll_id):
        """Start the release build (job). Standalone: it never needs ES or
        RAG — the bundle is always produced; RAG ingest is config-guarded
        (absent URL -> rag_status='blocked', nothing called). Idempotent by
        corpus content (same content -> same release_id, zip reused)."""
        db = get_db()
        ensure_knowledge_schema(db)
        row = _collection_row(db, coll_id)
        if not row:
            return jsonify({"ok": False, "message": "کالکشن پیدا نشد"}), 404
        cid = row["collection_id"]
        build = db.execute(
            """SELECT iv_id FROM knowledge_index_builds
               WHERE collection_id=? AND content_sha256 IS NOT NULL
               ORDER BY created_at DESC, iv_id DESC LIMIT 1""",
            (cid,)).fetchone()
        if not build:
            return jsonify(
                {"ok": False, "code": "no_corpus_build",
                 "message": "برای ساخت release باید پیکره canonical "
                             "(Stage D) وجود داشت — ابتدا «ساخت پیکره»"}
            ), 409
        n = db.execute(
            """SELECT COUNT(*) AS n FROM knowledge_collection_documents
               WHERE collection_id=? AND out_dir IS NOT NULL
                 AND status IN ('parsed','needs_review','approved',
                                'indexed')""",
            (cid,)).fetchone()["n"]
        job, started = _submit_job(
            db, job_key=f"release:{cid}", kind="release",
            collection_id=cid, batch_id=None, total=4,
            idempotency_key=f"release:{cid}", force_retry=True)
        return jsonify({"ok": True, "queued": started, "job": job,
                        "documents": n}), (202 if started else 200)

    @app.route("/api/knowledge/collections/<int:coll_id>/releases",
               methods=["GET"])
    @require_auth
    def knowledge_releases(coll_id):
        """List the release bundles of a collection (newest first)."""
        db = get_db()
        ensure_knowledge_schema(db)
        row = _collection_row(db, coll_id)
        if not row:
            return jsonify({"ok": False, "message": "کالکشن پیدا نشد"}), 404
        rels = [dict(r) for r in db.execute(
            """SELECT release_id, collection_id, build_iv_id,
                      content_sha256, zip_path, zip_sha256, size_bytes,
                      rag_status, created_at
               FROM knowledge_releases
               WHERE collection_id=?
               ORDER BY created_at DESC, release_id DESC""",
            (row["collection_id"],))]
        return jsonify({"ok": True,
                        "collection_id": row["collection_id"],
                        "releases": rels})

    @app.route("/api/knowledge/releases/<release_id>/download",
               methods=["GET"])
    @require_auth
    def knowledge_release_download(release_id):
        """Download a release bundle zip (behind PCM-09 auth).

        The on-disk zip is re-hashed against the recorded zip_sha256 before
        it is served — a tampered/missing file never goes out the door."""
        db = get_db()
        ensure_knowledge_schema(db)
        r = db.execute(
            "SELECT * FROM knowledge_releases WHERE release_id=?",
            (release_id,)).fetchone()
        if not r:
            return jsonify({"ok": False, "message": "release پیدا نشد"}), 404
        p = r["zip_path"]
        if not os.path.isfile(p):
            return jsonify(
                {"ok": False, "code": "zip_missing",
                 "message": "فایل zip روی دیسک پیدا نشد (release روی DB "
                             "ثبت است ولی فایل غایب است)"}), 410
        real = _sha256_file(p)
        if real != r["zip_sha256"]:
            _audit_log(db, r["collection_id"], "release",
                       "download_hash_mismatch", "fail",
                       {"release_id": release_id,
                        "expected": r["zip_sha256"], "actual": real})
            return jsonify(
                {"ok": False, "code": "hash_mismatch",
                 "message": "SHA-256 فایل zip با مقدار ثبت‌شده نمی‌خواند "
                             "— دانلود برای امنیت متوقف شد"}), 409
        # serve the VERIFIED bytes in memory (no open handle left behind —
        # on Windows an open handle would block the data-dir cleanup)
        with open(p, "rb") as fh:
            data = fh.read()
        resp = Response(data, mimetype="application/zip")
        resp.headers[
            "Content-Disposition"] = (
            "attachment; filename=" + os.path.basename(p))
        return resp

    @app.route("/api/knowledge/collections/<int:coll_id>/audit",
               methods=["GET"])
    @require_auth
    def knowledge_audit(coll_id):
        """Read the append-only audit trail of a collection
        (newest first, ?limit= capped)."""
        db = get_db()
        ensure_knowledge_schema(db)
        row = _collection_row(db, coll_id)
        if not row:
            return jsonify({"ok": False, "message": "کالکشن پیدا نشد"}), 404
        try:
            limit = max(1, min(int(request.args.get("limit", 100)), 500))
        except (TypeError, ValueError):
            limit = 100
        entries = [dict(r) for r in db.execute(
            """SELECT ts, actor, stage, action, status, detail_json
               FROM knowledge_audit_log
               WHERE collection_id=?
               ORDER BY id DESC LIMIT ?""",
            (row["collection_id"], limit))]
        return jsonify({"ok": True,
                        "collection_id": row["collection_id"],
                        "count": len(entries),
                        "entries": entries})

    @app.route("/api/knowledge/queue/summary", methods=["GET"])
    @require_auth
    def knowledge_queue_summary():
        """PCM-15: live counters for the per-file queue.

        All numbers are computed directly from knowledge_file_queue — the
        single source of truth (no cached/fabricated statistics, AGENTS §2).
        Optional ?collection_id= filter.
        """
        db = get_db()
        ensure_knowledge_schema(db)
        _recover_interrupted(db)
        coll_id = (request.args.get("collection_id") or "").strip() or None
        if coll_id:
            known = db.execute(
                "SELECT collection_id FROM knowledge_collections "
                "WHERE collection_id=?", (coll_id,)).fetchone()
            if not known:
                return jsonify({"ok": False, "field": "collection_id",
                                "message": "کالکشن پیدا نشد"}), 404
        counters = queue_counters(db, coll_id)
        stages = [
            dict(r) for r in db.execute(
                f"""SELECT stage, COUNT(*) AS files FROM knowledge_file_queue
                   WHERE stage IS NOT NULL
                     {'AND collection_id=?' if coll_id else ''}
                   GROUP BY stage""",
                (coll_id,) if coll_id else ())]
        return jsonify({"ok": True,
                        "collection_id": coll_id,
                        "counters": counters,
                        "failed_by_stage": stages})

    # ── Metadata (custom, versioned, three scopes — PCM-14B §3) ────────

    def _meta_fields(db, collection_id=None):
        rows = db.execute(
            """SELECT * FROM knowledge_metadata_fields
               WHERE enabled=1
                 AND (scope != 'collection'
                      OR collection_id = '__global__'
                      OR collection_id = ?)
               ORDER BY scope, field_key""", (collection_id or "",)).fetchall()
        return [dict(r) for r in rows]

    def _meta_values(db, collection_id=None, document_id=None, batch_id=None,
                     work_id=None, edition_id=None, volume_id=None,
                     scope=None):
        q = ("SELECT v.*, f.field_key, f.display_name, f.data_type "
             "FROM knowledge_metadata_values v "
             "JOIN knowledge_metadata_fields f ON f.field_id = v.field_id")
        where, params = ["f.enabled=1"], []
        if collection_id:
            where.append("v.collection_id = ?")
            params.append(collection_id)
        # Entity filters are scope-strict: a work/edition/volume id must not
        # leak into more-specific rows (an edition value row carries its
        # parent work_id, so matching on work_id alone would over-select).
        if document_id:
            where.append("f.scope='document' AND v.document_id = ?")
            params.append(document_id)
        if batch_id:
            where.append("v.batch_id = ?")
            params.append(batch_id)
        if work_id:
            where.append("f.scope='work' AND v.work_id = ?")
            params.append(work_id)
        if edition_id:
            where.append("f.scope='edition' AND v.edition_id = ?")
            params.append(edition_id)
        if volume_id:
            where.append("f.scope='volume' AND v.volume_id = ?")
            params.append(volume_id)
        if scope:
            where.append("f.scope = ?")
            params.append(scope)
        rows = db.execute(
            q + " WHERE " + " AND ".join(where) + " ORDER BY v.value_id",
            params).fetchall()
        return [dict(r) for r in rows]

    def _validate_meta_value(data_type, value):
        """Return (normalized_value, error). None value is always allowed
        (absent); empty string for non-boolean types normalizes to None."""
        if value is None:
            return None, None
        s = str(value).strip()
        if not s and data_type != "boolean":
            return None, None
        try:
            if data_type == "number":
                return str(float(s)), None
            if data_type == "boolean":
                if s.lower() in ("1", "true", "yes", "بلی", "بله"):
                    return "true", None
                if s.lower() in ("0", "false", "no", "نه"):
                    return "false", None
                return None, "مقدار بولی نامعتبر است"
            if data_type == "date":
                if not re.match(r"^\d{4}/\d{1,2}/\d{1,2}$", s):
                    return None, "تاریخ باید به شکل 1404/1/1 باشد"
                return s, None
            if data_type == "url":
                if not re.match(r"^https?://\S+$", s):
                    return None, "آدرس باید با http:// یا https:// شروع شود"
                return s, None
            if data_type == "json":
                json.loads(s)
                return s, None
            if data_type == "enum":
                return s, None
            return s, None  # string
        except (ValueError, json.JSONDecodeError):
            return None, f"مقدار معتبر از نوع {data_type} نیست"

    @app.route("/api/knowledge/metadata/fields", methods=["GET"])
    @require_auth
    def knowledge_list_fields():
        db = get_db()
        ensure_knowledge_schema(db)
        cid = request.args.get("collection_id")
        scope = (request.args.get("scope") or "").strip()
        if scope and scope not in FIELD_SCOPES:
            return jsonify({"ok": False, "field": "scope",
                            "message": "scope نامعتبر"}), 400
        rows = db.execute(
            """SELECT * FROM knowledge_metadata_fields
               WHERE enabled=1
                 AND (scope != 'collection'
                      OR collection_id = '__global__'
                      OR collection_id = ?)
               ORDER BY scope, field_key""", (cid or "",)).fetchall()
        fields = [dict(r) for r in rows]
        if scope:
            fields = [f for f in fields if f["scope"] == scope]
        return jsonify({"ok": True, "fields": fields})

    @app.route("/api/knowledge/metadata/fields", methods=["POST"])
    @require_auth
    def knowledge_create_field():
        db = get_db()
        ensure_knowledge_schema(db)
        data = request.get_json(silent=True) or {}
        scope = str(data.get("scope") or "collection").strip()
        if scope not in FIELD_SCOPES:
            return jsonify({"ok": False, "field": "scope",
                            "message": ("scope باید collection/batch/document/"
                                        "work/edition/volume باشد")}), 400
        cid = str(data.get("collection_id") or "").strip() or None
        if scope in ("work", "edition", "volume"):
            cid = None  # entity-scoped fields are global (all collections)
        coll = None
        if scope == "collection" and cid:
            coll = db.execute(
                "SELECT 1 FROM knowledge_collections WHERE collection_id=?",
                (cid,)).fetchone()
            if not coll:
                return jsonify({"ok": False, "field": "collection_id",
                                "message": "کالکشن پیدا نشد"}), 404
        key = re.sub(r"\W+", "_", str(data.get("field_key") or "").strip())[:64]
        if not key or not re.match(r"^[a-z0-9_]+$", key):
            return jsonify({"ok": False, "field": "field_key",
                            "message": "field_key باید a-z 0-9 _ باشد"}), 400
        display = _clean_name(data.get("display_name"))
        if not display:
            return jsonify({"ok": False, "field": "display_name",
                            "message": "display_name الزامی است"}), 400
        dtype = str(data.get("data_type") or "string").strip()
        if dtype not in FIELD_TYPES:
            return jsonify({"ok": False, "field": "data_type",
                            "message": "data_type نامعتبر"}), 400
        default_value = data.get("default_value")
        default_value = None if default_value is None else str(default_value)[:1000]
        if dtype != "boolean" and default_value is not None:
            _, err = _validate_meta_value(dtype, default_value)
            if err:
                return jsonify({"ok": False, "field": "default_value",
                                "message": err}), 400
        validation_rules = data.get("validation_rules")
        if validation_rules is not None:
            try:
                json.dumps(validation_rules)
            except (TypeError, ValueError):
                return jsonify({"ok": False, "field": "validation_rules",
                                "message": "validation_rules باید JSON معتبر باشد"}), 400
            validation_rules = json.dumps(validation_rules, ensure_ascii=False)
        else:
            validation_rules = None
        now = _now()
        field_id = "mf-" + hashlib.sha256(
            f"{scope}|{cid or ''}|{key}".encode("utf-8")).hexdigest()[:8]
        try:
            db.execute(
                """INSERT INTO knowledge_metadata_fields
                   (field_id, scope, collection_id, field_key, display_name,
                    data_type, required, default_value, validation_rules,
                    searchable, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (field_id, scope, cid or "__global__",
                 key, display, dtype, 1 if data.get("required") else 0,
                 default_value, validation_rules,
                 0 if data.get("searchable") is False else 1, now, now))
            db.commit()
        except Exception:  # UNIQUE violation
            db.rollback()
            return jsonify({"ok": False, "field": "field_key",
                            "message": "این فیلد از قبل تعریف شده"}), 409
        row = db.execute("SELECT * FROM knowledge_metadata_fields "
                         "WHERE field_id=?", (field_id,)).fetchone()
        return jsonify({"ok": True, "field": dict(row)}), 201

    @app.route("/api/knowledge/metadata/fields/<field_id>", methods=["PATCH"])
    @require_auth
    def knowledge_update_field(field_id):
        db = get_db()
        ensure_knowledge_schema(db)
        row = db.execute(
            "SELECT * FROM knowledge_metadata_fields WHERE field_id=?",
            (field_id,)).fetchone()
        if not row:
            return jsonify({"ok": False, "message": "فیلد پیدا نشد"}), 404
        data = request.get_json(silent=True) or {}
        sets, params = [], []
        if "display_name" in data:
            display = _clean_name(data["display_name"])
            if not display:
                return jsonify({"ok": False, "field": "display_name",
                                "message": "display_name نمی‌تواند خالی باشد"}), 400
            sets.append("display_name=?")
            params.append(display)
        if "required" in data:
            sets.append("required=?")
            params.append(1 if data["required"] else 0)
        if "default_value" in data:
            dv = data["default_value"]
            dv = None if dv is None else str(dv)[:1000]
            if dv is not None:
                _, err = _validate_meta_value(row["data_type"], dv)
                if err:
                    return jsonify({"ok": False, "field": "default_value",
                                    "message": err}), 400
            sets.append("default_value=?")
            params.append(dv)
        if "searchable" in data:
            sets.append("searchable=?")
            params.append(0 if data["searchable"] is False else 1)
        if "enabled" in data:
            sets.append("enabled=?")
            params.append(1 if data["enabled"] else 0)
        if not sets:
            return jsonify({"ok": False, "message": "مقداری برای ویرایش فرستاده نشده"}), 400
        # A schema change to the field definition bumps its schema_version
        # (display-only tweaks do NOT touch stored values).
        sets.append("updated_at=?")
        params.append(_now())
        params.append(field_id)
        db.execute(f"UPDATE knowledge_metadata_fields SET {', '.join(sets)} "
                   "WHERE field_id=?", params)
        db.commit()
        row = db.execute("SELECT * FROM knowledge_metadata_fields "
                         "WHERE field_id=?", (field_id,)).fetchone()
        return jsonify({"ok": True, "field": dict(row)})

    @app.route("/api/knowledge/metadata/fields/<field_id>", methods=["DELETE"])
    @require_auth
    def knowledge_delete_field(field_id):
        """Soft-disable a field (values kept for audit) or hard-remove it."""
        db = get_db()
        ensure_knowledge_schema(db)
        row = db.execute(
            "SELECT * FROM knowledge_metadata_fields WHERE field_id=?",
            (field_id,)).fetchone()
        if not row:
            return jsonify({"ok": False, "message": "فیلد پیدا نشد"}), 404
        if request.args.get("purge") == "1":
            db.execute("DELETE FROM knowledge_metadata_values WHERE field_id=?",
                       (field_id,))
            db.execute("DELETE FROM knowledge_metadata_fields WHERE field_id=?",
                       (field_id,))
        else:
            db.execute("UPDATE knowledge_metadata_fields SET enabled=0, "
                       "updated_at=? WHERE field_id=?", (_now(), field_id))
        db.commit()
        return jsonify({"ok": True, "purged": request.args.get("purge") == "1"})

    @app.route("/api/knowledge/metadata/values", methods=["GET"])
    @require_auth
    def knowledge_list_values():
        db = get_db()
        ensure_knowledge_schema(db)
        cid = request.args.get("collection_id")
        doc_id = request.args.get("document_id")
        batch_id = request.args.get("batch_id")
        work_id = request.args.get("work_id")
        edition_id = request.args.get("edition_id")
        volume_id = request.args.get("volume_id")
        if not (cid or doc_id or batch_id or work_id or edition_id or volume_id):
            return jsonify({"ok": False,
                            "message": ("یکی از collection_id/document_id/"
                                        "batch_id/work_id/edition_id/volume_id "
                                        "لازم است")}), 400
        return jsonify({"ok": True,
                        "values": _meta_values(db, cid, doc_id, batch_id,
                                                work_id, edition_id, volume_id)})

    @app.route("/api/knowledge/metadata/values", methods=["POST"])
    @require_auth
    def knowledge_set_value():
        db = get_db()
        ensure_knowledge_schema(db)
        data = request.get_json(silent=True) or {}
        field_key = str(data.get("field_key") or "").strip()
        value = data.get("value")
        doc_id = str(data.get("document_id") or "").strip()
        batch_id = str(data.get("batch_id") or "").strip()
        cid = str(data.get("collection_id") or "").strip()
        work_id = str(data.get("work_id") or "").strip()
        edition_id = str(data.get("edition_id") or "").strip()
        volume_id = str(data.get("volume_id") or "").strip()
        want_scope = str(data.get("scope") or "").strip()

        q = ("SELECT * FROM knowledge_metadata_fields "
             "WHERE field_key=? AND enabled=1")
        qp = [field_key]
        if want_scope in FIELD_SCOPES:
            q += " AND scope=?"
            qp.append(want_scope)
        candidates = db.execute(q + " ORDER BY scope, field_id", qp).fetchall()
        f = None
        for c in candidates:
            if c["scope"] == "document" and not doc_id:
                continue
            if c["scope"] == "batch" and not batch_id:
                continue
            if c["scope"] == "collection" and not cid:
                continue
            if c["scope"] == "work" and not work_id:
                continue
            if c["scope"] == "edition" and not edition_id:
                continue
            if c["scope"] == "volume" and not volume_id:
                continue
            f = c
            break
        if not f:
            return jsonify({"ok": False, "field": "field_key",
                            "message": "فیلد تعریف نشده یا غیرفعال است"}), 404
        scope = f["scope"]
        if scope == "document":
            if not doc_id:
                return jsonify({"ok": False, "field": "document_id",
                                "message": "برای فیلد سند، document_id لازم است"}), 400
            d = db.execute(
                "SELECT 1 FROM knowledge_collection_documents WHERE document_id=?",
                (doc_id,)).fetchone()
            if not d:
                return jsonify({"ok": False, "field": "document_id",
                                "message": "سند پیدا نشد"}), 404
            cid = db.execute(
                "SELECT collection_id FROM knowledge_collection_documents "
                "WHERE document_id=?", (doc_id,)).fetchone()["collection_id"]
        elif scope == "batch":
            if not batch_id:
                return jsonify({"ok": False, "field": "batch_id",
                                "message": "برای فیلد بچ، batch_id لازم است"}), 400
            if not cid:
                b = db.execute(
                    "SELECT collection_id FROM knowledge_import_batches "
                    "WHERE batch_id=?", (batch_id,)).fetchone()
                if not b:
                    return jsonify({"ok": False, "field": "batch_id",
                                    "message": "بچ پیدا نشد"}), 404
                cid = b["collection_id"]
        elif scope == "work":
            if not work_id:
                return jsonify({"ok": False, "field": "work_id",
                                "message": "برای فیلد اثر، work_id لازم است"}), 400
            if not db.execute("SELECT 1 FROM knowledge_works WHERE work_id=?",
                              (work_id,)).fetchone():
                return jsonify({"ok": False, "field": "work_id",
                                "message": "اثر پیدا نشد"}), 404
        elif scope == "edition":
            if not edition_id:
                return jsonify({"ok": False, "field": "edition_id",
                                "message": "برای فیلد ویرایش، edition_id لازم است"}), 400
            er = db.execute("SELECT work_id FROM knowledge_editions "
                            "WHERE edition_id=?", (edition_id,)).fetchone()
            if not er:
                return jsonify({"ok": False, "field": "edition_id",
                                "message": "ویرایش پیدا نشد"}), 404
            work_id = work_id or er["work_id"]
        elif scope == "volume":
            if not volume_id:
                return jsonify({"ok": False, "field": "volume_id",
                                "message": "برای فیلد جلد، volume_id لازم است"}), 400
            vr = db.execute("SELECT work_id, edition_id FROM knowledge_volumes "
                            "WHERE volume_id=?", (volume_id,)).fetchone()
            if not vr:
                return jsonify({"ok": False, "field": "volume_id",
                                "message": "جلد پیدا نشد"}), 404
            work_id = work_id or vr["work_id"]
            edition_id = edition_id or (vr["edition_id"] or "")
        else:  # collection
            if not cid:
                return jsonify({"ok": False, "field": "collection_id",
                                "message": "برای فیلد کالکشن، collection_id لازم است"}), 400

        norm, err = _validate_meta_value(f["data_type"], value)
        if err:
            return jsonify({"ok": False, "field": "field_key", "message": err}), 400

        now = _now()
        existing = db.execute(
            """SELECT value_id, version FROM knowledge_metadata_values
               WHERE field_id=? AND scope=? AND collection_id=?
                 AND batch_id=? AND document_id=? AND work_id=?
                 AND edition_id=? AND volume_id=?""",
            (f["field_id"], scope, cid, batch_id, doc_id,
             work_id, edition_id, volume_id)).fetchone()
        if existing:
            db.execute(
                """UPDATE knowledge_metadata_values
                   SET value=?, source='user', version=version+1, edited_at=?
                   WHERE value_id=?""",
                (norm, now, existing["value_id"]))
            new_version = existing["version"] + 1
        else:
            db.execute(
                """INSERT INTO knowledge_metadata_values
                   (field_id, scope, collection_id, batch_id, document_id,
                    work_id, edition_id, volume_id,
                    value, source, version, edited_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'user', 1, ?)""",
                (f["field_id"], scope, cid or "", batch_id or "",
                 doc_id or "", work_id, edition_id, volume_id, norm, now))
            new_version = 1
        # Metadata edits NEVER re-upload/re-parse the Word file (spec §3);
        # they are flagged index-affecting for later selective reindex.
        if doc_id:
            db.execute("UPDATE knowledge_collection_documents SET updated_at=? "
                       "WHERE document_id=?", (now, doc_id))
        if cid:
            db.execute("UPDATE knowledge_collections SET updated_at=? "
                       "WHERE collection_id=?", (now, cid))
        for ent_table, ent_col, ent_id in (("knowledge_works", "work_id", work_id),
                                           ("knowledge_editions", "edition_id", edition_id),
                                           ("knowledge_volumes", "volume_id", volume_id)):
            if ent_id:
                db.execute(f"UPDATE {ent_table} SET updated_at=? WHERE {ent_col}=?",
                           (now, ent_id))
        db.commit()
        row = db.execute(
            """SELECT v.*, f.field_key, f.display_name, f.data_type
               FROM knowledge_metadata_values v
               JOIN knowledge_metadata_fields f ON f.field_id=v.field_id
               WHERE v.field_id=? AND v.scope=? AND v.collection_id=?
                 AND v.batch_id=? AND v.document_id=? AND v.work_id=?
                 AND v.edition_id=? AND v.volume_id=?""",
            (f["field_id"], scope, cid or "", batch_id or "",
             doc_id or "", work_id, edition_id, volume_id)).fetchone()
        return jsonify({"ok": True, "value": dict(row),
                        "version": new_version,
                        "affects_index": True})

    @app.route("/api/knowledge/metadata/values/<int:value_id>", methods=["DELETE"])
    @require_auth
    def knowledge_delete_value(value_id):
        db = get_db()
        ensure_knowledge_schema(db)
        r = db.execute("DELETE FROM knowledge_metadata_values WHERE value_id=?",
                       (value_id,))
        db.commit()
        if not r.rowcount:
            return jsonify({"ok": False, "message": "مقدار پیدا نشد"}), 404
        return jsonify({"ok": True})

    # ── Jobs ───────────────────────────────────────────────────────────

    @app.route("/api/knowledge/jobs", methods=["GET"])
    @require_auth
    def knowledge_jobs():
        db = get_db()
        ensure_knowledge_schema(db)
        _recover_interrupted(db)
        cid = request.args.get("collection_id")
        rows = db.execute(
            """SELECT job_id, job_key, kind, collection_id, batch_id, status,
                      stage, progress, total, retry_count, error,
                      idempotency_key, created_at, updated_at, completed_at
               FROM knowledge_jobs
               WHERE 1=1 {}
               ORDER BY created_at DESC LIMIT 100""".format(
                "AND collection_id = ?" if cid else ""),
            (cid,) if cid else ()).fetchall()
        return jsonify({"ok": True, "jobs": [dict(r) for r in rows]})

    # ── PCM-14D — Work / Edition / Volume registry ─────────────────────

    def _ent_count(table, col, ent_id):
        return db.execute(
            f"SELECT COUNT(*) AS n FROM knowledge_collection_documents "
            f"WHERE {col} = ?", (ent_id,)).fetchone()["n"]

    @app.route("/api/knowledge/works", methods=["GET"])
    @require_auth
    def knowledge_list_works():
        db = get_db()
        ensure_knowledge_schema(db)
        search = (request.args.get("search") or "").strip()
        page = max(1, int(request.args.get("page") or 1))
        per_page = min(100, max(1, int(request.args.get("per_page") or 50)))
        where, params = [], []
        if search:
            where.append("(title LIKE ? OR author LIKE ? OR work_id LIKE ?)")
            like = f"%{search}%"
            params.extend([like, like, like])
        where_sql = (" WHERE " + " AND ".join(where)) if where else ""
        total = db.execute(
            f"SELECT COUNT(*) AS n FROM knowledge_works{where_sql}",
            params).fetchone()["n"]
        rows = db.execute(
            f"""SELECT w.*,
                  (SELECT COUNT(*) FROM knowledge_editions e
                    WHERE e.work_id = w.work_id) AS edition_count,
                  (SELECT COUNT(*) FROM knowledge_collection_documents d
                    WHERE d.work_id = w.work_id) AS document_count
               FROM knowledge_works w
               {where_sql}
               ORDER BY w.updated_at DESC
               LIMIT ? OFFSET ?""",
            (*params, per_page, (page - 1) * per_page)).fetchall()
        return jsonify({"works": [dict(r) for r in rows], "total": total,
                        "page": page, "per_page": per_page,
                        "total_pages": (total + per_page - 1) // per_page})

    @app.route("/api/knowledge/works", methods=["POST"])
    @require_auth
    def knowledge_create_work():
        db = get_db()
        ensure_knowledge_schema(db)
        data = request.get_json(silent=True) or {}
        key = str(data.get("key") or "").strip()
        if not key:
            key = _work_key_from_biblio(
                data.get("title"), data.get("author"),
                str(data.get("sha256") or "").strip())
        if not key:
            return jsonify({"ok": False, "field": "key",
                            "message": "key (یا title/author/sha256) لازم است"}), 400
        work_id = short_id("w", key)
        now = _now()
        existed = db.execute("SELECT 1 FROM knowledge_works WHERE work_id=?",
                             (work_id,)).fetchone()
        db.execute(
            """INSERT OR IGNORE INTO knowledge_works
               (work_id, title, author, subject, language, document_count,
                source, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, 0, 'user', ?, ?)""",
            (work_id, _clean_name(data.get("title")),
             _clean_name(data.get("author")), _clean_name(data.get("subject")),
             (str(data.get("language") or "").strip() or None), now, now))
        db.commit()
        row = db.execute("SELECT * FROM knowledge_works WHERE work_id=?",
                         (work_id,)).fetchone()
        return jsonify({"ok": True, "work": dict(row),
                        "created": existed is None}), 201

    @app.route("/api/knowledge/works/<work_id>", methods=["GET"])
    @require_auth
    def knowledge_work_detail(work_id):
        db = get_db()
        ensure_knowledge_schema(db)
        w = db.execute("SELECT * FROM knowledge_works WHERE work_id=?",
                       (work_id,)).fetchone()
        if not w:
            return jsonify({"ok": False, "message": "اثر پیدا نشد"}), 404
        editions = [dict(r) for r in db.execute(
            """SELECT e.*,
                 (SELECT COUNT(*) FROM knowledge_volumes v
                   WHERE v.edition_id = e.edition_id) AS volume_count
                FROM knowledge_editions e WHERE e.work_id=?
                ORDER BY e.edition_id""", (work_id,))]
        documents = [dict(r) for r in db.execute(
            """SELECT document_id, collection_id, file_name, sha256, status,
                      blocks_count, chars_count, quality_status, out_dir
               FROM knowledge_collection_documents WHERE work_id=?
               ORDER BY id""", (work_id,))]
        return jsonify({"ok": True, "work": dict(w),
                        "editions": editions, "documents": documents})

    @app.route("/api/knowledge/works/<work_id>", methods=["PATCH"])
    @require_auth
    def knowledge_update_work(work_id):
        db = get_db()
        ensure_knowledge_schema(db)
        if not db.execute("SELECT 1 FROM knowledge_works WHERE work_id=?",
                          (work_id,)).fetchone():
            return jsonify({"ok": False, "message": "اثر پیدا نشد"}), 404
        data = request.get_json(silent=True) or {}
        sets, params = [], []
        for col, key in (("title", "title"), ("author", "author"),
                         ("subject", "subject"), ("language", "language")):
            if key in data:
                sets.append(f"{col}=?")
                params.append(_clean_name(data[key]))
        if not sets:
            return jsonify({"ok": False,
                            "message": "مقداری برای ویرایش فرستاده نشده"}), 400
        sets.append("updated_at=?")
        params.extend([_now(), work_id])
        db.execute(f"UPDATE knowledge_works SET {', '.join(sets)} "
                   f"WHERE work_id=?", params)
        db.commit()
        row = db.execute("SELECT * FROM knowledge_works WHERE work_id=?",
                         (work_id,)).fetchone()
        return jsonify({"ok": True, "work": dict(row)})

    @app.route("/api/knowledge/works/<work_id>/editions", methods=["POST"])
    @require_auth
    def knowledge_create_edition(work_id):
        db = get_db()
        ensure_knowledge_schema(db)
        if not db.execute("SELECT 1 FROM knowledge_works WHERE work_id=?",
                          (work_id,)).fetchone():
            return jsonify({"ok": False, "message": "اثر پیدا نشد"}), 404
        data = request.get_json(silent=True) or {}
        key = str(data.get("key") or "").strip()
        if not key:
            key = f"{work_id}|{str(data.get('publisher') or '').strip()}|" \
                  f"{str(data.get('publish_year') or '').strip()}"
        edition_id = short_id("e", f"{work_id}|{key}")
        now = _now()
        db.execute(
            """INSERT OR IGNORE INTO knowledge_editions
               (edition_id, work_id, publisher, publish_year, edition_label,
                language, document_count, source, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, 0, 'user', ?, ?)""",
            (edition_id, work_id, _clean_name(data.get("publisher")),
             _clean_name(data.get("publish_year")),
             _clean_name(data.get("edition_label")),
             (str(data.get("language") or "").strip() or None), now, now))
        db.commit()
        row = db.execute("SELECT * FROM knowledge_editions WHERE edition_id=?",
                         (edition_id,)).fetchone()
        return jsonify({"ok": True, "edition": dict(row)}), 201

    @app.route("/api/knowledge/editions/<edition_id>", methods=["GET"])
    @require_auth
    def knowledge_edition_detail(edition_id):
        db = get_db()
        ensure_knowledge_schema(db)
        e = db.execute("SELECT * FROM knowledge_editions WHERE edition_id=?",
                       (edition_id,)).fetchone()
        if not e:
            return jsonify({"ok": False, "message": "ویرایش پیدا نشد"}), 404
        volumes = [dict(r) for r in db.execute(
            """SELECT v.*,
                 (SELECT COUNT(*) FROM knowledge_collection_documents d
                   WHERE d.volume_id = v.volume_id) AS document_count
                FROM knowledge_volumes v WHERE v.edition_id=?
                ORDER BY v.volume_no, v.volume_id""", (edition_id,))]
        documents = [dict(r) for r in db.execute(
            """SELECT document_id, collection_id, file_name, sha256, status,
                      blocks_count, chars_count, quality_status, out_dir
               FROM knowledge_collection_documents WHERE edition_id=?
               ORDER BY id""", (edition_id,))]
        return jsonify({"ok": True, "edition": dict(e),
                        "volumes": volumes, "documents": documents})

    @app.route("/api/knowledge/editions/<edition_id>", methods=["PATCH"])
    @require_auth
    def knowledge_update_edition(edition_id):
        db = get_db()
        ensure_knowledge_schema(db)
        if not db.execute("SELECT 1 FROM knowledge_editions "
                          "WHERE edition_id=?", (edition_id,)).fetchone():
            return jsonify({"ok": False, "message": "ویرایش پیدا نشد"}), 404
        data = request.get_json(silent=True) or {}
        sets, params = [], []
        for col, key in (("publisher", "publisher"),
                         ("publish_year", "publish_year"),
                         ("edition_label", "edition_label"),
                         ("language", "language")):
            if key in data:
                sets.append(f"{col}=?")
                params.append(_clean_name(data[key]))
        if not sets:
            return jsonify({"ok": False,
                            "message": "مقداری برای ویرایش فرستاده نشده"}), 400
        sets.append("updated_at=?")
        params.extend([_now(), edition_id])
        db.execute(f"UPDATE knowledge_editions SET {', '.join(sets)} "
                   f"WHERE edition_id=?", params)
        db.commit()
        row = db.execute("SELECT * FROM knowledge_editions "
                         "WHERE edition_id=?", (edition_id,)).fetchone()
        return jsonify({"ok": True, "edition": dict(row)})

    @app.route("/api/knowledge/editions/<edition_id>/volumes", methods=["POST"])
    @require_auth
    def knowledge_create_volume(edition_id):
        db = get_db()
        ensure_knowledge_schema(db)
        e = db.execute("SELECT work_id FROM knowledge_editions "
                       "WHERE edition_id=?", (edition_id,)).fetchone()
        if not e:
            return jsonify({"ok": False, "message": "ویرایش پیدا نشد"}), 404
        data = request.get_json(silent=True) or {}
        key = str(data.get("key") or "").strip()
        if not key:
            key = f"{edition_id}|{data.get('volume_no') or 'main'}"
        volume_id = short_id("v", f"{edition_id}|{key}")
        now = _now()
        vno = data.get("volume_no")
        try:
            vno = int(vno) if vno is not None and str(vno).strip() != "" else None
        except (TypeError, ValueError):
            return jsonify({"ok": False, "field": "volume_no",
                            "message": "volume_no باید عدد باشد"}), 400
        db.execute(
            """INSERT OR IGNORE INTO knowledge_volumes
               (volume_id, edition_id, work_id, volume_no, label,
                document_count, source, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, 0, 'user', ?, ?)""",
            (volume_id, edition_id, e["work_id"], vno,
             _clean_name(data.get("label")), now, now))
        db.commit()
        row = db.execute("SELECT * FROM knowledge_volumes WHERE volume_id=?",
                         (volume_id,)).fetchone()
        return jsonify({"ok": True, "volume": dict(row)}), 201

    @app.route("/api/knowledge/volumes/<volume_id>", methods=["GET"])
    @require_auth
    def knowledge_volume_detail(volume_id):
        db = get_db()
        ensure_knowledge_schema(db)
        v = db.execute("SELECT * FROM knowledge_volumes WHERE volume_id=?",
                       (volume_id,)).fetchone()
        if not v:
            return jsonify({"ok": False, "message": "جلد پیدا نشد"}), 404
        documents = [dict(r) for r in db.execute(
            """SELECT document_id, collection_id, file_name, sha256, status,
                      blocks_count, chars_count, quality_status, out_dir
               FROM knowledge_collection_documents WHERE volume_id=?
               ORDER BY id""", (volume_id,))]
        return jsonify({"ok": True, "volume": dict(v), "documents": documents})

    @app.route("/api/knowledge/volumes/<volume_id>", methods=["PATCH"])
    @require_auth
    def knowledge_update_volume(volume_id):
        db = get_db()
        ensure_knowledge_schema(db)
        if not db.execute("SELECT 1 FROM knowledge_volumes "
                          "WHERE volume_id=?", (volume_id,)).fetchone():
            return jsonify({"ok": False, "message": "جلد پیدا نشد"}), 404
        data = request.get_json(silent=True) or {}
        sets, params = [], []
        if "volume_no" in data:
            vno = data["volume_no"]
            try:
                vno = int(vno) if vno is not None and str(vno).strip() != "" else None
            except (TypeError, ValueError):
                return jsonify({"ok": False, "field": "volume_no",
                                "message": "volume_no باید عدد باشد"}), 400
            sets.append("volume_no=?")
            params.append(vno)
        if "label" in data:
            sets.append("label=?")
            params.append(_clean_name(data["label"]))
        if not sets:
            return jsonify({"ok": False,
                            "message": "مقداری برای ویرایش فرستاده نشده"}), 400
        sets.append("updated_at=?")
        params.extend([_now(), volume_id])
        db.execute(f"UPDATE knowledge_volumes SET {', '.join(sets)} "
                   f"WHERE volume_id=?", params)
        db.commit()
        row = db.execute("SELECT * FROM knowledge_volumes WHERE volume_id=?",
                         (volume_id,)).fetchone()
        return jsonify({"ok": True, "volume": dict(row)})

    # ── PCM-14D — metadata resolution (merged scope chain) ─────────────

    @app.route("/api/knowledge/metadata/resolve", methods=["GET"])
    @require_auth
    def knowledge_metadata_resolve():
        """Merge effective metadata for a document across scopes.

        Precedence (highest wins): document > volume > edition > work >
        collection > global field defaults. Returns the resolved dict,
        the source of each value, and the raw per-scope value rows.
        """
        db = get_db()
        ensure_knowledge_schema(db)
        doc_id = request.args.get("document_id")
        work_id = request.args.get("work_id")
        edition_id = request.args.get("edition_id")
        volume_id = request.args.get("volume_id")
        cid = request.args.get("collection_id")
        d = None
        if doc_id:
            d = db.execute(
                """SELECT collection_id, work_id, edition_id, volume_id
                   FROM knowledge_collection_documents WHERE document_id=?""",
                (doc_id,)).fetchone()
            if not d:
                return jsonify({"ok": False, "message": "سند پیدا نشد"}), 404
            cid = cid or d["collection_id"]
            work_id = work_id or d["work_id"]
            edition_id = edition_id or d["edition_id"]
            volume_id = volume_id or d["volume_id"]
        if not (cid or work_id or edition_id or volume_id):
            return jsonify({"ok": False,
                            "message": ("document_id یا collection_id لازم است")}), 400

        fields = [f for f in _meta_fields(db, cid) if f["enabled"]]
        scopes = (("document", doc_id), ("volume", volume_id),
                  ("edition", edition_id), ("work", work_id),
                  ("collection", None))

        def _rows(scope):
            # Each scope is gated on its anchor id: an empty ('' sentinel)
            # id must NOT produce an unfiltered query (that would leak
            # value rows from every other collection).
            if scope == "document":
                return _meta_values(db, document_id=doc_id) if doc_id else []
            if scope == "volume":
                return _meta_values(db, volume_id=volume_id) if volume_id else []
            if scope == "edition":
                return _meta_values(db, edition_id=edition_id) if edition_id else []
            if scope == "work":
                return _meta_values(db, work_id=work_id) if work_id else []
            if not cid:
                return []
            return _meta_values(db, collection_id=cid, scope="collection")

        resolved = {}
        sources = {}
        raw = {}
        # Merge most-specific-first (document > volume > edition > work >
        # collection): the first non-null value written wins. raw carries
        # ALL value rows of every scope, not only the winners.
        for scope, _anchor in scopes:
            rows = _rows(scope)
            raw[scope] = rows
            for v in rows:
                fk = v["field_key"]
                if fk in resolved:
                    continue
                if v["value"] is not None:
                    resolved[fk] = v["value"]
                    sources[fk] = scope
        # field defaults (global layer)
        for f in fields:
            if f["field_key"] not in resolved and f["default_value"] is not None:
                resolved[f["field_key"]] = f["default_value"]
                sources[f["field_key"]] = "field_default"
        return jsonify({"ok": True, "resolved": resolved, "sources": sources,
                        "raw": {k: [dict(v) for v in vs]
                                for k, vs in raw.items()},
                        "context": {"document_id": doc_id, "collection_id": cid,
                                    "work_id": work_id, "edition_id": edition_id,
                                    "volume_id": volume_id}})

    # ── ES compatibility (PCM-14B §5 — honest NOT VERIFIED) ────────────

    @app.route("/api/knowledge/compatibility", methods=["GET"])
    @require_auth
    def knowledge_compatibility():
        db = get_db()
        ensure_knowledge_schema(db)
        # The ONLY ES in this project is the REMOTE thesaurus harvest API
        # (thesaurus.eiis.iki.ac.ir) — a crawl source for the thesaurus,
        # NOT a book/collection index. No local PCT Elasticsearch exists
        # (audit 2026-10-26 on s52: no 9200/9300, no ES container).
        return jsonify({
            "ok": True,
            "es_available": False,
            "previous_mapping": "NOT_VERIFIED",
            "reason": (
                "مAPPING کتاب‌های قبلی در دسترس نیست: هیچ Elasticsearch محلی "
                "متعلق به PCT وجود ندارد (ممیزی s52 در 1405/08/04 — پورت "
                "9200/9300 گوش نمی‌دهند و کانتینر ES نیست). تنها ES پروژه "
                "API دوردست hasaurus است که منبع کراول thesaurus می‌باشد، "
                "نه ایندکس کتاب. ساختار جدید روی قرارداد Word Factory V0.1 "
                "اساس دارد و Golden Fixture در تست‌ها نگهداری می‌شود."
            ),
            "field_matrix": [
                {"existing_field": None, "new_field": "collection_id",
                 "type": "keyword", "compatibility": "NOT_VERIFIED",
                 "action": "await ES bootstrap (PCM-14D)"},
                {"existing_field": None, "new_field": "document_id",
                 "type": "keyword", "compatibility": "NOT_VERIFIED",
                 "action": "await ES bootstrap (PCM-14D)"},
                {"existing_field": None, "new_field": "work_id/edition_id",
                 "type": "keyword", "compatibility": "NOT_VERIFIED",
                 "action": "deterministic ids from PCM-13 (title|author|sha)"},
                {"existing_field": None, "new_field": "block_id",
                 "type": "keyword", "compatibility": "NOT_VERIFIED",
                 "action": "bNNNNN:type — deterministic (PCM-13)"},
                {"existing_field": None, "new_field": "raw_text",
                 "type": "text (persian analyzer)", "compatibility": "NOT_VERIFIED",
                 "action": "analyzer to be defined in PCM-14D"},
                {"existing_field": None, "new_field": "normalized_text",
                 "type": "text (persian analyzer)", "compatibility": "NOT_VERIFIED",
                 "action": "norm_version n-1 (PCM-13)"},
                {"existing_field": None, "new_field": "metadata.*",
                 "type": "object", "compatibility": "NOT_VERIFIED",
                 "action": "custom fields via knowledge_metadata_*"},
                {"existing_field": None, "new_field": "source_ref",
                 "type": "object", "compatibility": "NOT_VERIFIED",
                 "action": "structural citation (no invented page numbers)"},
            ],
            "golden_fixture": (
                "backend/tests/fixtures/knowledge/golden-manifest.json "
                "(deterministic manifest of the canonical sample book; "
                "regenerated in test suite)"
            ),
        })

    return app

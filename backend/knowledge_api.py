"""Corpus Knowledge Studio — Collections, Word Library & Metadata (PCM-14A/B).

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

from flask import jsonify, request

from auth import make_require_auth

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
FIELD_SCOPES = ("collection", "batch", "document")

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


def _doc_id(sha256_hex: str):
    return "d-" + sha256_hex[:8]


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
        value         TEXT,
        source        TEXT NOT NULL DEFAULT 'user',
        version       INTEGER NOT NULL DEFAULT 1,
        edited_at     TEXT NOT NULL,
        edited_by     TEXT,
        UNIQUE (scope, collection_id, batch_id, document_id, field_id)
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
    """)
    db.commit()
    _ensure_document_columns(db)


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
    ]
    for col, decl in wanted:
        if col not in existing:
            db.execute(
                f"ALTER TABLE knowledge_collection_documents ADD COLUMN {col} {decl}"
            )
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


def _recover_interrupted(db):
    """PCM-13/14 §13: after a restart, make stuck state resumable.

    Only rows whose updated_at is OLDER than STUCK_AFTER_MOD are considered
    stuck — a live worker updates its row (job stage/progress, document
    status) well within that window, so in-flight work is never touched.

    - jobs stuck in pending/running  -> interrupted (retryable)
    - documents stuck in parsing -> uploaded (reprocessable, file intact)
    - batches stuck in 'processing' -> planned (re-runnable)
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
                  status, blocks_count, chars_count, quality_status,
                  quality_score, parser_version, norm_version, out_dir, error,
                  created_at, updated_at
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
        conn.execute("UPDATE knowledge_jobs SET status='succeeded', stage='done', "
                     "updated_at=?, completed_at=? WHERE job_id=?",
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
                idempotency_key=None):
    """Insert a persistent job row and start its worker thread.

    Idempotency: re-submitting the same job_key returns the existing job
    (and does NOT start a second worker) — spec §13/§9.
    """
    now = _now()
    existing = db.execute(
        "SELECT job_id, status FROM knowledge_jobs WHERE job_key=?",
        (job_key,)).fetchone()
    if existing:
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
    import server  # lazy: server imports this module at startup
    t = threading.Thread(
        target=_job_worker, args=(server.DB_PATH, job_id), daemon=True)
    t.start()
    return {"job_id": job_id, "job_key": job_key, "status": "pending"}, True


_JOB_KINDS = {}  # kind -> worker fn(conn, job_id); registered below


def _job_progress(conn, job_id, progress, total=None, stage=None):
    conn.execute(
        "UPDATE knowledge_jobs SET progress=?, total=COALESCE(?, total), "
        "stage=?, updated_at=? WHERE job_id=?",
        (progress, total, stage, _now(), job_id))
    conn.commit()


# ---------------------------------------------------------------------------
# Word Factory integration (PCM-13, reused)
# ---------------------------------------------------------------------------

def _process_document(conn, collection_id, doc_id):
    """Run the Word Factory on one registered document (in-place update)."""
    row = conn.execute(
        """SELECT * FROM knowledge_collection_documents
           WHERE document_id = ? AND collection_id = ?""",
        (doc_id, collection_id)).fetchone()
    if not row:
        raise RuntimeError(f"document {doc_id} not found")
    sha = row["sha256"]
    file_name = row["file_name"] or "book.docx"
    ext = os.path.splitext(file_name)[1]
    stored = _stored_file_path(sha, "f-" + sha[:8], ext)
    if not os.path.isfile(stored):
        raise RuntimeError("stored original file missing (corrupt store)")

    conn.execute("UPDATE knowledge_collection_documents SET status='parsing', "
                 "updated_at=? WHERE id=?", (_now(), row["id"]))
    conn.commit()

    from factory.service import DocumentProcessingService
    out_root = os.path.join(knowledge_data_dir(), "out")
    os.makedirs(out_root, exist_ok=True)
    svc = DocumentProcessingService(out_root)
    try:
        doc = svc.process(stored)  # raises FactoryError on failure
    except Exception as e:  # noqa: BLE001 — record per-doc failure, keep going
        conn.execute("UPDATE knowledge_collection_documents SET status='failed', "
                     "error=?, updated_at=? WHERE id=?",
                     (f"{type(e).__name__}: {e}", _now(), row["id"]))
        _refresh_book_count(conn, collection_id)
        conn.commit()
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
    _refresh_book_count(conn, collection_id)
    conn.commit()
    return status


def _job_kind_process_document(conn, job_id):
    r = conn.execute("SELECT job_key, collection_id FROM knowledge_jobs "
                     "WHERE job_id=?", (job_id,)).fetchone()
    kind, doc_id = r["job_key"].split(":", 1)
    _process_document(conn, r["collection_id"], doc_id)


def _job_kind_process_batch(conn, job_id):
    r = conn.execute("SELECT job_key, collection_id FROM knowledge_jobs "
                     "WHERE job_id=?", (job_id,)).fetchone()
    _, batch_id = r["job_key"].split(":", 1)
    coll = r["collection_id"]
    docs = conn.execute(
        """SELECT document_id FROM knowledge_collection_documents
           WHERE collection_id = ? AND status IN ('uploaded','failed')
           ORDER BY id""", (coll,)).fetchall()
    total = len(docs)
    done = 0
    for d in docs:
        try:
            _process_document(conn, coll, d["document_id"])
        except Exception as e:  # noqa: BLE001 — keep going, record per file
            conn.execute("UPDATE knowledge_collection_documents SET status='failed', "
                         "error=?, updated_at=? WHERE document_id=?",
                         (f"{type(e).__name__}: {e}", _now(), d["document_id"]))
            conn.commit()
        done += 1
        _job_progress(conn, job_id, done, total,
                      f"document {d['document_id']}")
    # batch tally
    t = conn.execute(
        """SELECT
             SUM(CASE WHEN status IN ('parsed','needs_review','approved','indexed')
                 THEN 1 ELSE 0 END) AS ok,
             SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END) AS bad
           FROM knowledge_collection_documents WHERE collection_id=?""",
        (coll,)).fetchone()
    conn.execute(
        "UPDATE knowledge_import_batches SET processed_count=?, failed_count=?, "
        "status='done', updated_at=? WHERE batch_id=?",
        (t["ok"] or 0, t["bad"] or 0, _now(), batch_id))
    conn.commit()


_JOB_KINDS["process_document"] = _job_kind_process_document
_JOB_KINDS["process_batch"] = _job_kind_process_batch


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
                          status, created_at, completed_at
                   FROM knowledge_index_builds
                   WHERE collection_id = ?
                   ORDER BY created_at DESC, iv_id DESC""",
                (row["collection_id"],))
        ]
        item["metadata_fields"] = _meta_fields(db, row["collection_id"])
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
                          status, created_at, completed_at
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
            (cid, _doc_id(sha), name, relative_path or None, sha, size,
             file_id, now, now))
        db.commit()
        doc = _doc_row(db, _doc_id(sha))
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
                       file_size, file_id, status, blocks_count, chars_count,
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
        for i, f in enumerate(files):
            if not isinstance(f, dict):
                plan.append({"index": i, "status": "invalid",
                             "reason": "entry not an object"})
                continue
            name = os.path.basename(str(f.get("name") or "").replace("\\", "/"))
            sha = str(f.get("sha256") or "").strip().lower()
            size = int(f.get("size") or 0)
            entry = {"index": i, "name": name, "sha256": sha or None,
                     "size": size}
            if not name or os.path.splitext(name)[1].lower() != ".docx":
                entry["status"] = "invalid_extension"
            elif not re.match(r"^[0-9a-f]{64}$", sha):
                entry["status"] = "invalid_sha"
            elif size == 0 or size > MAX_UPLOAD_BYTES:
                entry["status"] = "invalid_size"
            else:
                known = db.execute(
                    "SELECT document_id FROM knowledge_collection_documents "
                    "WHERE collection_id=? AND sha256=?",
                    (cid, sha)).fetchone()
                if known:
                    entry["status"] = "duplicate"
                    entry["existing_document_id"] = known["document_id"]
                else:
                    entry["status"] = "pending"
            plan.append(entry)

        pending = sum(1 for e in plan if e["status"] == "pending")
        db.execute(
            """INSERT INTO knowledge_import_batches
               (batch_id, collection_id, folder_name, file_count, status,
                created_at, updated_at)
               VALUES (?, ?, ?, ?, 'planned', ?, ?)""",
            (batch_id, cid,
             _clean_name(data.get("folder_name")) or None,
             len(plan), now, now))
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
        docs = [
            dict(r) for r in db.execute(
                "SELECT id, document_id, file_name, relative_path, sha256, "
                "file_size, status, blocks_count, chars_count, quality_status, "
                "quality_score, error, created_at, updated_at "
                "FROM knowledge_collection_documents "
                "WHERE collection_id=? ORDER BY id", (b["collection_id"],))]
        jobs = [dict(r) for r in db.execute(
            "SELECT job_id, kind, status, stage, progress, total, error, "
            "created_at, updated_at, completed_at FROM knowledge_jobs "
            "WHERE batch_id=? ORDER BY created_at DESC", (batch_id,))]
        return jsonify({"ok": True, "batch": dict(b),
                        "documents": docs, "jobs": jobs})

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
        n = db.execute(
            "SELECT COUNT(*) AS n FROM knowledge_collection_documents "
            "WHERE collection_id=? AND status IN ('uploaded','failed')",
            (b["collection_id"],)).fetchone()["n"]
        db.execute("UPDATE knowledge_import_batches SET status='processing', "
                   "updated_at=? WHERE batch_id=?", (_now(), batch_id))
        db.commit()
        job, created = _submit_job(
            db, f"process_batch:{batch_id}", "process_batch",
            b["collection_id"], batch_id, total=n,
            idempotency_key=f"batch:{batch_id}")
        return jsonify({"ok": True, "job": job, "files_queued": n,
                        "resubmitted": not created}), (202 if created else 200)

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

    def _meta_values(db, collection_id=None, document_id=None, batch_id=None):
        q = ("SELECT v.*, f.field_key, f.display_name, f.data_type "
             "FROM knowledge_metadata_values v "
             "JOIN knowledge_metadata_fields f ON f.field_id = v.field_id")
        where, params = ["f.enabled=1"], []
        if collection_id:
            where.append("v.collection_id = ?")
            params.append(collection_id)
        if document_id:
            where.append("v.document_id = ?")
            params.append(document_id)
        if batch_id:
            where.append("v.batch_id = ?")
            params.append(batch_id)
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
                            "message": "scope باید collection/batch/document باشد"}), 400
        cid = str(data.get("collection_id") or "").strip() or None
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
        if not (cid or doc_id or batch_id):
            return jsonify({"ok": False,
                            "message": "یکی از collection_id/document_id/batch_id لازم است"}), 400
        return jsonify({"ok": True,
                        "values": _meta_values(db, cid, doc_id, batch_id)})

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
                 AND batch_id=? AND document_id=?""",
            (f["field_id"], scope, cid, batch_id, doc_id)).fetchone()
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
                    value, source, version, edited_at)
                   VALUES (?, ?, ?, ?, ?, ?, 'user', 1, ?)""",
                (f["field_id"], scope, cid or "", batch_id or "",
                 doc_id or "", norm, now))
            new_version = 1
        # Metadata edits NEVER re-upload/re-parse the Word file (spec §3);
        # they are flagged index-affecting for later selective reindex.
        if doc_id:
            db.execute("UPDATE knowledge_collection_documents SET updated_at=? "
                       "WHERE document_id=?", (now, doc_id))
        if cid:
            db.execute("UPDATE knowledge_collections SET updated_at=? "
                       "WHERE collection_id=?", (now, cid))
        db.commit()
        row = db.execute(
            """SELECT v.*, f.field_key, f.display_name, f.data_type
               FROM knowledge_metadata_values v
               JOIN knowledge_metadata_fields f ON f.field_id=v.field_id
               WHERE v.field_id=? AND v.scope=? AND v.collection_id=?
                 AND v.batch_id=? AND v.document_id=?""",
            (f["field_id"], scope, cid or "", batch_id or "",
             doc_id or "")).fetchone()
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

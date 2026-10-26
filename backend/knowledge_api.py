"""Corpus Knowledge Studio — Collection Management APIs (PCM-14A).

The «استودیوی دانش» backend: collections of Word books that will later be
indexed into Elasticsearch (PCM-14C/D). Everything here is ADDITIVE:

  - new tables only (knowledge_collections, knowledge_collection_documents,
    knowledge_index_builds, knowledge_jobs); no ALTER/RENAME/DROP;
  - read+write APIs under /api/knowledge/*, all behind the PCM-09 auth
    (same session model as /api/dashboard/*);
  - the extension write APIs and all existing endpoints are untouched.

Naming contract (PCM-14, section 4):
  display name (Persian)  : کتابخانه علوم عقلی   (independent, may change)
  collection slug         : oloom-aqli           (technical, stable, unique)
  collection id           : c-<sha256(slug)[:8]> (deterministic)
  index alias             : pct-col-oloom-aqli
  physical index          : pct-col-oloom-aqli-v0001 (PCM-14D)

Renaming the display name never touches id/slug/alias.
"""
import hashlib
import re
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


def _now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _collection_id(slug):
    """Deterministic collection id from the stable technical slug."""
    return "c-" + hashlib.sha256(slug.encode("utf-8")).hexdigest()[:8]


def _index_alias(slug):
    return "pct-col-" + slug


def ensure_knowledge_schema(db):
    """Additive migration: create the studio tables if absent.

    Column additions in later sub-phases (PCM-14B/C/D) must follow the
    AGENTS.md rule: ALTER TABLE ADD COLUMN + backfill + index, never
    DROP/RENAME.
    """
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
        es_alias            TEXT NOT NULL,
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
        document_id   TEXT NOT NULL,
        file_name     TEXT,
        sha256        TEXT NOT NULL,
        status        TEXT NOT NULL DEFAULT 'uploaded',
        blocks_count  INTEGER NOT NULL DEFAULT 0,
        chars_count   INTEGER NOT NULL DEFAULT 0,
        quality_status TEXT,
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
        norm_version   TEXT NOT NULL,
        chunking_version TEXT NOT NULL,
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
        status         TEXT NOT NULL DEFAULT 'pending',
        stage          TEXT,
        progress       INTEGER NOT NULL DEFAULT 0,
        retry_count    INTEGER NOT NULL DEFAULT 0,
        error          TEXT,
        idempotency_key TEXT,
        created_at     TEXT NOT NULL,
        updated_at     TEXT NOT NULL,
        completed_at   TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_kcol_updated
        ON knowledge_collections(updated_at DESC);
    CREATE INDEX IF NOT EXISTS idx_kcol_documents
        ON knowledge_collection_documents(collection_id, status);
    CREATE INDEX IF NOT EXISTS idx_kbuilds_collection
        ON knowledge_index_builds(collection_id, created_at DESC);
    """)
    db.commit()


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
                    WHERE d.collection_id = c.collection_id) AS doc_count,
                  (SELECT COUNT(*) FROM knowledge_index_builds b
                    WHERE b.collection_id = c.collection_id) AS build_count
           FROM knowledge_collections c WHERE c.id = ?""",
        (coll_id,),
    ).fetchone()


def register_knowledge_routes(app, get_db):
    require_auth = make_require_auth(get_db)

    @app.route("/api/knowledge/collections", methods=["GET"])
    @require_auth
    def knowledge_collections():
        db = get_db()
        ensure_knowledge_schema(db)

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
        row = _collection_row(db, coll_id)
        if not row:
            return jsonify({"ok": False, "message": "کالکشن پیدا نشد"}), 404
        item = dict(row)
        item["documents"] = [
            dict(r) for r in db.execute(
                """SELECT id, document_id, file_name, sha256, status,
                          blocks_count, chars_count, quality_status, error,
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
        description = data.get("description")
        description = _clean_name(description)
        subject = data.get("subject")
        subject = _clean_name(subject)

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
        return jsonify({"ok": True, "collection": dict(_collection_row(db, coll_id))})

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

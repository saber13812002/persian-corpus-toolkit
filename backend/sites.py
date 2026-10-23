"""Named sites and the tags picked from the page."""
import hashlib
import json

from flask import jsonify, request


HAMTAA_FIELDS = [
    ("surah", "css", ".reader-appbar__book", "before_paren"),
    ("ayah", "css", ".reader-appbar__book", "paren_number"),
    ("arabic", "css", "p.book-text", "text"),
    ("translation", "css", ".book-note--translation .book-note__body", "text"),
    ("content", "css", "main article", "text"),
    ("volume", "url_param", "file_id", "text"),
    ("page", "url_param", "item_index", "add_one"),
    ("url", "url", "", "text"),
]


def ensure_sites_schema(db):
    db.executescript("""
    CREATE TABLE IF NOT EXISTS sites (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        host        TEXT NOT NULL UNIQUE,
        name        TEXT,
        created_at  TEXT DEFAULT (datetime('now'))
    );
    CREATE TABLE IF NOT EXISTS site_fields (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        site_id     INTEGER NOT NULL,
        tag         TEXT NOT NULL,
        source      TEXT NOT NULL,
        selector    TEXT DEFAULT '',
        transform   TEXT DEFAULT 'text',
        sample      TEXT DEFAULT '',
        created_at  TEXT DEFAULT (datetime('now')),
        UNIQUE(site_id, tag)
    );
    CREATE TABLE IF NOT EXISTS captures (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        host         TEXT NOT NULL,
        url          TEXT NOT NULL,
        values_json  TEXT NOT NULL,
        content_hash TEXT NOT NULL,
        captured_at  TEXT DEFAULT (datetime('now')),
        UNIQUE(host, url)
    );
    CREATE INDEX IF NOT EXISTS idx_captures_host ON captures(host, id DESC);
    CREATE INDEX IF NOT EXISTS idx_fields_site ON site_fields(site_id);
    """)
    db.commit()


def seed_default_sites(db):
    ensure_sites_schema(db)
    db.execute(
        "INSERT OR IGNORE INTO sites (host, name) VALUES (?, ?)",
        ("tasnim.hamtaa.org", "همتا"),
    )
    row = db.execute("SELECT id FROM sites WHERE host=?", ("tasnim.hamtaa.org",)).fetchone()
    site_id = row[0] if not isinstance(row, dict) and not hasattr(row, "keys") else row["id"]
    have = {
        r[0]
        for r in db.execute("SELECT tag FROM site_fields WHERE site_id=?", (site_id,))
    }
    for tag, source, selector, transform in HAMTAA_FIELDS:
        if tag in have:
            continue
        db.execute(
            """INSERT INTO site_fields (site_id, tag, source, selector, transform)
               VALUES (?, ?, ?, ?, ?)""",
            (site_id, tag, source, selector, transform),
        )
    db.commit()


def _site_by_host(db, host):
    return db.execute("SELECT * FROM sites WHERE host=?", (host,)).fetchone()


def _fields(db, site_id):
    rows = db.execute(
        """SELECT tag, source, selector, transform, sample
           FROM site_fields WHERE site_id=? ORDER BY id""",
        (site_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def register_site_routes(app, get_db):
    @app.route("/api/sites")
    def list_sites():
        db = get_db()
        ensure_sites_schema(db)
        seed_default_sites(db)
        rows = db.execute(
            """SELECT s.host, s.name,
                      (SELECT COUNT(*) FROM site_fields f WHERE f.site_id=s.id) AS fields,
                      (SELECT COUNT(*) FROM captures c WHERE c.host=s.host) AS captures
               FROM sites s ORDER BY s.host"""
        ).fetchall()
        return jsonify({"sites": [dict(r) for r in rows]})

    @app.route("/api/sites/match")
    def match_site():
        db = get_db()
        ensure_sites_schema(db)
        seed_default_sites(db)
        host = (request.args.get("host") or "").lower().strip()
        site = _site_by_host(db, host)
        if not site:
            return jsonify({"host": host, "name": "", "fields": []})
        return jsonify({"host": site["host"], "name": site["name"], "fields": _fields(db, site["id"])})

    @app.route("/api/sites/fields", methods=["POST"])
    def save_field():
        db = get_db()
        ensure_sites_schema(db)
        data = request.get_json(silent=True) or {}
        host = (data.get("host") or "").lower().strip()
        tag = (data.get("tag") or "").strip()
        source = (data.get("source") or "css").strip()
        if not host or not tag:
            return jsonify({"ok": False, "message": "host و tag لازم است"}), 400
        if source not in ("css", "xpath", "url", "url_param"):
            return jsonify({"ok": False, "message": "source نامعتبر است"}), 400
        name = (data.get("name") or host).strip()
        db.execute(
            """INSERT INTO sites (host, name) VALUES (?, ?)
               ON CONFLICT(host) DO UPDATE SET name=excluded.name""",
            (host, name),
        )
        site = _site_by_host(db, host)
        db.execute(
            """INSERT INTO site_fields (site_id, tag, source, selector, transform, sample)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(site_id, tag) DO UPDATE SET
                 source=excluded.source,
                 selector=excluded.selector,
                 transform=excluded.transform,
                 sample=excluded.sample""",
            (
                site["id"],
                tag,
                source,
                data.get("selector") or "",
                data.get("transform") or "text",
                (data.get("sample") or "")[:240],
            ),
        )
        db.commit()
        return jsonify({"ok": True, "host": host, "fields": _fields(db, site["id"])})

    @app.route("/api/sites/fields", methods=["DELETE"])
    def delete_field():
        db = get_db()
        ensure_sites_schema(db)
        host = (request.args.get("host") or "").lower().strip()
        tag = (request.args.get("tag") or "").strip()
        site = _site_by_host(db, host)
        if site and tag:
            db.execute("DELETE FROM site_fields WHERE site_id=? AND tag=?", (site["id"], tag))
            db.commit()
        return jsonify({"ok": True, "fields": _fields(db, site["id"]) if site else []})

    @app.route("/api/captures", methods=["POST"])
    def save_capture():
        db = get_db()
        ensure_sites_schema(db)
        data = request.get_json(silent=True) or {}
        host = (data.get("host") or "").lower().strip()
        url = (data.get("url") or "").split("#")[0].strip()
        values = data.get("values") or {}
        if not host or not url or not isinstance(values, dict):
            return jsonify({"ok": False, "message": "host و url و values لازم است"}), 400
        payload = json.dumps(values, ensure_ascii=False, sort_keys=True)
        digest = hashlib.sha256(payload.encode()).hexdigest()
        existing = db.execute(
            "SELECT id, content_hash FROM captures WHERE host=? AND url=?",
            (host, url),
        ).fetchone()
        if existing and existing["content_hash"] == digest:
            return jsonify({"ok": True, "status": "skipped", "id": existing["id"]})
        if existing:
            db.execute(
                """UPDATE captures SET values_json=?, content_hash=?, captured_at=datetime('now')
                   WHERE id=?""",
                (payload, digest, existing["id"]),
            )
            db.commit()
            return jsonify({"ok": True, "status": "updated", "id": existing["id"]})
        cur = db.execute(
            """INSERT INTO captures (host, url, values_json, content_hash)
               VALUES (?, ?, ?, ?)""",
            (host, url, payload, digest),
        )
        db.commit()
        return jsonify({"ok": True, "status": "inserted", "id": cur.lastrowid})

    @app.route("/api/captures")
    def list_captures():
        db = get_db()
        ensure_sites_schema(db)
        host = (request.args.get("host") or "").lower().strip()
        limit = request.args.get("limit", 20, type=int)
        if host:
            rows = db.execute(
                """SELECT id, host, url, values_json, captured_at FROM captures
                   WHERE host=? ORDER BY id DESC LIMIT ?""",
                (host, limit),
            ).fetchall()
        else:
            rows = db.execute(
                """SELECT id, host, url, values_json, captured_at FROM captures
                   ORDER BY id DESC LIMIT ?""",
                (limit,),
            ).fetchall()
        items = []
        for r in rows:
            item = dict(r)
            try:
                item["values"] = json.loads(item.pop("values_json") or "{}")
            except Exception:
                item["values"] = {}
                item.pop("values_json", None)
            items.append(item)
        return jsonify({"items": items, "count": len(items)})

"""Crawl projects: named page-points, a next-page rule, and a run report.

A project is one book or site the extension is reading. Points are chosen
on the page. Quran verse tags are not seeded here.
"""
import hashlib
import json

from flask import jsonify, request


def ensure_projects_schema(db):
    db.executescript("""
    CREATE TABLE IF NOT EXISTS projects (
        id                INTEGER PRIMARY KEY AUTOINCREMENT,
        name              TEXT NOT NULL,
        host              TEXT NOT NULL,
        start_url         TEXT DEFAULT '',
        next_mode         TEXT DEFAULT 'url_param',
        next_param        TEXT DEFAULT '',
        next_step         INTEGER DEFAULT 1,
        pages_per_minute  INTEGER DEFAULT 4,
        cursor_url        TEXT DEFAULT '',
        status            TEXT DEFAULT 'draft',
        saved_count       INTEGER DEFAULT 0,
        skipped_count     INTEGER DEFAULT 0,
        failed_count      INTEGER DEFAULT 0,
        last_message      TEXT DEFAULT '',
        tested_at         TEXT,
        created_at        TEXT,
        updated_at        TEXT DEFAULT (datetime('now'))
    );
    CREATE TABLE IF NOT EXISTS project_points (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id  INTEGER NOT NULL,
        tag         TEXT NOT NULL,
        source      TEXT NOT NULL,
        selector    TEXT DEFAULT '',
        transform   TEXT DEFAULT 'text',
        sample      TEXT DEFAULT '',
        UNIQUE(project_id, tag)
    );
    CREATE TABLE IF NOT EXISTS project_pages (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id   INTEGER NOT NULL,
        url          TEXT NOT NULL,
        values_json  TEXT NOT NULL,
        content_hash TEXT NOT NULL,
        captured_at  TEXT DEFAULT (datetime('now')),
        UNIQUE(project_id, url)
    );
    CREATE INDEX IF NOT EXISTS idx_projects_host ON projects(host, id DESC);
    CREATE INDEX IF NOT EXISTS idx_project_pages ON project_pages(project_id, id DESC);
    """)
    db.commit()


def _points(db, project_id):
    rows = db.execute(
        """SELECT tag, source, selector, transform, sample
           FROM project_points WHERE project_id=? ORDER BY id""",
        (project_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def _project(db, project_id):
    row = db.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
    if not row:
        return None
    item = dict(row)
    item["points"] = _points(db, project_id)
    item["pages"] = db.execute(
        "SELECT COUNT(*) AS n FROM project_pages WHERE project_id=?",
        (project_id,),
    ).fetchone()["n"]
    return item


def _touch(db, project_id, **fields):
    if not fields:
        db.execute("UPDATE projects SET updated_at=datetime('now') WHERE id=?", (project_id,))
        return
    fields = dict(fields)
    fields["updated_at"] = None
    cols = []
    vals = []
    for key, value in fields.items():
        if key == "updated_at":
            cols.append("updated_at=datetime('now')")
            continue
        cols.append(f"{key}=?")
        vals.append(value)
    vals.append(project_id)
    db.execute(f"UPDATE projects SET {', '.join(cols)} WHERE id=?", vals)


def register_project_routes(app, get_db):
    @app.route("/api/projects", methods=["GET"])
    def list_projects():
        db = get_db()
        ensure_projects_schema(db)
        host = (request.args.get("host") or "").lower().strip()
        if host:
            rows = db.execute(
                "SELECT * FROM projects WHERE host=? ORDER BY id DESC",
                (host,),
            ).fetchall()
        else:
            rows = db.execute("SELECT * FROM projects ORDER BY id DESC LIMIT 50").fetchall()
        items = []
        for row in rows:
            item = dict(row)
            item["points"] = _points(db, item["id"])
            items.append(item)
        return jsonify({"projects": items})

    @app.route("/api/projects", methods=["POST"])
    def create_project():
        db = get_db()
        ensure_projects_schema(db)
        from dashboard_api import ensure_dashboard_schema  # created_at column
        ensure_dashboard_schema(db)
        data = request.get_json(silent=True) or {}
        name = (data.get("name") or "").strip()
        host = (data.get("host") or "").lower().strip()
        if not name or not host:
            return jsonify({"ok": False, "message": "نام پروژه و میزبان لازم است"}), 400
        next_mode = data.get("next_mode") or "url_param"
        if next_mode not in ("url_param", "none"):
            return jsonify({"ok": False, "message": "next_mode نامعتبر است"}), 400
        pace = int(data.get("pages_per_minute") or 4)
        pace = max(1, min(12, pace))
        step = int(data.get("next_step") or 1) or 1
        start_url = (data.get("start_url") or "").split("#")[0].strip()
        cur = db.execute(
            """INSERT INTO projects
               (name, host, start_url, next_mode, next_param, next_step, pages_per_minute, cursor_url, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'draft', datetime('now'))""",
            (
                name,
                host,
                start_url,
                next_mode,
                (data.get("next_param") or "").strip(),
                step,
                pace,
                start_url,
            ),
        )
        db.commit()
        return jsonify({"ok": True, "project": _project(db, cur.lastrowid)})

    @app.route("/api/projects/<int:project_id>", methods=["GET"])
    def get_project(project_id):
        db = get_db()
        ensure_projects_schema(db)
        item = _project(db, project_id)
        if not item:
            return jsonify({"ok": False, "message": "پروژه پیدا نشد"}), 404
        return jsonify(item)

    @app.route("/api/projects/<int:project_id>", methods=["POST"])
    def update_project(project_id):
        db = get_db()
        ensure_projects_schema(db)
        item = _project(db, project_id)
        if not item:
            return jsonify({"ok": False, "message": "پروژه پیدا نشد"}), 404
        data = request.get_json(silent=True) or {}
        fields = {}
        if "name" in data and str(data["name"]).strip():
            fields["name"] = str(data["name"]).strip()
        if "start_url" in data:
            fields["start_url"] = str(data["start_url"] or "").split("#")[0].strip()
        if "next_mode" in data:
            if data["next_mode"] not in ("url_param", "none"):
                return jsonify({"ok": False, "message": "next_mode نامعتبر است"}), 400
            fields["next_mode"] = data["next_mode"]
        if "next_param" in data:
            fields["next_param"] = str(data["next_param"] or "").strip()
        if "next_step" in data:
            fields["next_step"] = int(data["next_step"] or 1) or 1
        if "pages_per_minute" in data:
            fields["pages_per_minute"] = max(1, min(12, int(data["pages_per_minute"] or 4)))
        if "cursor_url" in data:
            fields["cursor_url"] = str(data["cursor_url"] or "").split("#")[0].strip()
        if "status" in data:
            if data["status"] not in ("draft", "tested", "running", "paused"):
                return jsonify({"ok": False, "message": "status نامعتبر است"}), 400
            fields["status"] = data["status"]
        if "last_message" in data:
            fields["last_message"] = str(data["last_message"] or "")[:500]
        _touch(db, project_id, **fields)
        db.commit()
        return jsonify({"ok": True, "project": _project(db, project_id)})

    @app.route("/api/projects/<int:project_id>/points", methods=["POST"])
    def save_point(project_id):
        db = get_db()
        ensure_projects_schema(db)
        if not _project(db, project_id):
            return jsonify({"ok": False, "message": "پروژه پیدا نشد"}), 404
        data = request.get_json(silent=True) or {}
        tag = (data.get("tag") or "").strip()
        source = (data.get("source") or "css").strip()
        if not tag:
            return jsonify({"ok": False, "message": "اسم نقطه لازم است"}), 400
        if source not in ("css", "xpath", "url", "url_param"):
            return jsonify({"ok": False, "message": "source نامعتبر است"}), 400
        previous = (data.get("previous_tag") or "").strip()
        if previous and previous != tag:
            db.execute(
                "DELETE FROM project_points WHERE project_id=? AND tag=?",
                (project_id, previous),
            )
        db.execute(
            """INSERT INTO project_points (project_id, tag, source, selector, transform, sample)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(project_id, tag) DO UPDATE SET
                 source=excluded.source,
                 selector=excluded.selector,
                 transform=excluded.transform,
                 sample=excluded.sample""",
            (
                project_id,
                tag,
                source,
                data.get("selector") or "",
                data.get("transform") or "text",
                (data.get("sample") or "")[:240],
            ),
        )
        _touch(db, project_id)
        db.commit()
        return jsonify({"ok": True, "project": _project(db, project_id)})

    @app.route("/api/projects/<int:project_id>/points", methods=["DELETE"])
    def delete_point(project_id):
        db = get_db()
        ensure_projects_schema(db)
        tag = (request.args.get("tag") or "").strip()
        if _project(db, project_id) and tag:
            db.execute(
                "DELETE FROM project_points WHERE project_id=? AND tag=?",
                (project_id, tag),
            )
            _touch(db, project_id)
            db.commit()
        item = _project(db, project_id)
        if not item:
            return jsonify({"ok": False, "message": "پروژه پیدا نشد"}), 404
        return jsonify({"ok": True, "project": item})

    @app.route("/api/projects/<int:project_id>/pages", methods=["POST"])
    def save_page(project_id):
        db = get_db()
        ensure_projects_schema(db)
        item = _project(db, project_id)
        if not item:
            return jsonify({"ok": False, "message": "پروژه پیدا نشد"}), 404
        data = request.get_json(silent=True) or {}
        url = (data.get("url") or "").split("#")[0].strip()
        values = data.get("values") or {}
        if not url or not isinstance(values, dict):
            return jsonify({"ok": False, "message": "url و values لازم است"}), 400
        if not any(str(v or "").strip() for v in values.values()):
            return jsonify({"ok": False, "status": "empty", "message": "هیچ متنی خوانده نشد"}), 422
        payload = json.dumps(values, ensure_ascii=False, sort_keys=True)
        digest = hashlib.sha256(payload.encode()).hexdigest()
        existing = db.execute(
            "SELECT id, content_hash FROM project_pages WHERE project_id=? AND url=?",
            (project_id, url),
        ).fetchone()
        if existing and existing["content_hash"] == digest:
            status = "skipped"
            page_id = existing["id"]
        elif existing:
            db.execute(
                """UPDATE project_pages
                   SET values_json=?, content_hash=?, captured_at=datetime('now')
                   WHERE id=?""",
                (payload, digest, existing["id"]),
            )
            status = "updated"
            page_id = existing["id"]
        else:
            cur = db.execute(
                """INSERT INTO project_pages (project_id, url, values_json, content_hash)
                   VALUES (?, ?, ?, ?)""",
                (project_id, url, payload, digest),
            )
            status = "inserted"
            page_id = cur.lastrowid
        sets = ["cursor_url=?", "updated_at=datetime('now')"]
        vals = [url]
        if item["status"] == "draft":
            sets.append("status='tested'")
            sets.append("tested_at=datetime('now')")
        if status == "inserted":
            sets.append("saved_count=saved_count+1")
        elif status == "skipped":
            sets.append("skipped_count=skipped_count+1")
        db.execute(f"UPDATE projects SET {', '.join(sets)} WHERE id=?", (*vals, project_id))
        db.commit()
        return jsonify({"ok": True, "status": status, "id": page_id, "project": _project(db, project_id)})

    @app.route("/api/projects/<int:project_id>/report", methods=["POST"])
    def report_project(project_id):
        db = get_db()
        ensure_projects_schema(db)
        item = _project(db, project_id)
        if not item:
            return jsonify({"ok": False, "message": "پروژه پیدا نشد"}), 404
        data = request.get_json(silent=True) or {}
        saved = item["saved_count"] + int(data.get("saved") or 0)
        skipped = item["skipped_count"] + int(data.get("skipped") or 0)
        failed = item["failed_count"] + int(data.get("failed") or 0)
        fields = {
            "saved_count": saved,
            "skipped_count": skipped,
            "failed_count": failed,
        }
        if data.get("cursor_url"):
            fields["cursor_url"] = str(data["cursor_url"]).split("#")[0]
        if "message" in data:
            fields["last_message"] = str(data.get("message") or "")[:500]
        if data.get("status") in ("draft", "tested", "running", "paused"):
            fields["status"] = data["status"]
        _touch(db, project_id, **fields)
        db.commit()
        return jsonify({"ok": True, "project": _project(db, project_id)})

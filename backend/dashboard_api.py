"""Dashboard read APIs for projects (PCM-04) — behind auth (PCM-09).

Serves the new «پروژه‌ها» tab of /dashboard/:
  GET /api/dashboard/projects            — paginated list, search, filter, sort
  GET /api/dashboard/projects/<id>       — project details (fields, cursor, stats)

Read-only: no mutation, no deletes. All queries parameterized with
LIMIT/OFFSET pagination so the whole table is never loaded into memory.
"""
import json

from flask import jsonify, request

from auth import make_require_auth

_SORTABLE = {
    "id": "p.id",
    "name": "p.name",
    "host": "p.host",
    "status": "p.status",
    "saved_count": "p.saved_count",
    "updated_at": "p.updated_at",
    "created_at": "p.created_at",
}


def ensure_dashboard_schema(db):
    """Additive migration: add created_at to projects (backfilled once)."""
    cols = {r[1] for r in db.execute("PRAGMA table_info(projects)").fetchall()}
    if "created_at" not in cols:
        # SQLite forbids non-constant defaults in ADD COLUMN, so the column
        # is added plain and backfilled explicitly below. New rows get
        # created_at set by the INSERT in projects.create_project.
        db.execute("ALTER TABLE projects ADD COLUMN created_at TEXT")
        db.execute(
            "UPDATE projects SET created_at = updated_at WHERE created_at IS NULL"
        )
        db.commit()
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_projects_updated ON projects(updated_at DESC)"
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_project_pages_captured "
        "ON project_pages(project_id, captured_at)"
    )


def register_dashboard_routes(app, get_db):
    require_auth = make_require_auth(get_db)

    @app.route("/api/dashboard/projects", methods=["GET"])
    @require_auth
    def dash_projects():
        db = get_db()
        ensure_dashboard_schema(db)

        search = (request.args.get("search") or "").strip()
        status = (request.args.get("status") or "").strip()
        sort = request.args.get("sort") or "updated_at"
        order = "ASC" if (request.args.get("order") or "").upper() == "ASC" else "DESC"
        page = max(1, int(request.args.get("page") or 1))
        per_page = min(100, max(1, int(request.args.get("per_page") or 10)))

        where = []
        params = []
        if search:
            where.append("(p.name LIKE ? OR p.host LIKE ?)")
            like = f"%{search}%"
            params.extend([like, like.lower()])
        if status:
            where.append("p.status = ?")
            params.append(status)
        where_sql = ("WHERE " + " AND ".join(where)) if where else ""

        sort_col = _SORTABLE.get(sort, "p.updated_at")
        total = db.execute(
            f"SELECT COUNT(*) AS n FROM projects p {where_sql}", params
        ).fetchone()["n"]
        rows = db.execute(
            f"""SELECT p.id, p.name, p.host, p.start_url, p.status,
                       p.next_mode, p.next_param, p.next_step, p.pages_per_minute,
                       p.saved_count, p.skipped_count, p.failed_count,
                       p.cursor_url, p.last_message, p.created_at, p.updated_at,
                       (SELECT COUNT(*) FROM project_points pp WHERE pp.project_id = p.id) AS fields_count,
                       (SELECT COUNT(*) FROM project_pages pg WHERE pg.project_id = p.id) AS pages_count
                FROM projects p
                {where_sql}
                ORDER BY {sort_col} {order}, p.id DESC
                LIMIT ? OFFSET ?""",
            (*params, per_page, (page - 1) * per_page),
        ).fetchall()

        return jsonify({
            "projects": [dict(r) for r in rows],
            "total": total,
            "page": page,
            "per_page": per_page,
            "total_pages": (total + per_page - 1) // per_page,
        })

    @app.route("/api/dashboard/projects/<int:project_id>", methods=["GET"])
    @require_auth
    def dash_project_detail(project_id):
        db = get_db()
        ensure_dashboard_schema(db)
        row = db.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
        if not row:
            return jsonify({"ok": False, "message": "پروژه پیدا نشد"}), 404
        item = dict(row)
        item["points"] = [
            dict(r)
            for r in db.execute(
                "SELECT tag, source, selector, transform, sample "
                "FROM project_points WHERE project_id=? ORDER BY id",
                (project_id,),
            ).fetchall()
        ]
        pages = db.execute(
            """SELECT COUNT(*) AS n,
                      MIN(captured_at) AS first_captured,
                      MAX(captured_at) AS last_captured
               FROM project_pages WHERE project_id=?""",
            (project_id,),
        ).fetchone()
        last_page = db.execute(
            "SELECT url, captured_at FROM project_pages WHERE project_id=? "
            "ORDER BY id DESC LIMIT 1",
            (project_id,),
        ).fetchone()
        item["pages_summary"] = {
            "total": pages["n"],
            "first_captured": pages["first_captured"],
            "last_captured": pages["last_captured"],
            "last_url": last_page["url"] if last_page else "",
        }
        try:
            item["values_sample"] = json.loads(
                db.execute(
                    "SELECT values_json FROM project_pages WHERE project_id=? "
                    "ORDER BY id DESC LIMIT 1",
                    (project_id,),
                ).fetchone()[0]
            ) if last_page else {}
        except Exception:
            item["values_sample"] = {}
        return jsonify(item)

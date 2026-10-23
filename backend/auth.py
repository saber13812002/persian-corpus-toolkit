"""Dashboard authentication (PCM-09).

Single-password login protecting:
  - the /dashboard/ UI data
  - the /api/dashboard/* read APIs (projects list/detail/stats)

The extension write APIs (/api/projects/..., points, pages, report)
stay OPEN so a live crawl is never interrupted by the dashboard login.

Security model:
- The password is stored ONLY as a scrypt hash (table `auth_meta`).
  Plaintext arrives once via the PCT_DASHBOARD_PASSWORD env var (seeded
  into the hash at first start) or PCT_DASHBOARD_PASSWORD_HASH. The
  plaintext is never persisted to the DB or committed to Git.
- Sessions: 32-byte random tokens in `auth_sessions`, 7-day expiry,
  revocable (logout / manual delete), delivered as an
  HttpOnly + Secure (behind HTTPS) + SameSite=Lax cookie.
- Login rate limit: 5 failures per 10 minutes per client IP.
- No password/token in URLs, logs, metrics or reports.
"""
import hashlib
import hmac
import os
import secrets
import time
from functools import wraps

from flask import jsonify, request

COOKIE = "pct_session"
SESSION_DAYS = 7
LOGIN_MAX_FAILS = 5
LOGIN_WINDOW = 600  # seconds


# ── password hashing (stdlib scrypt, per-hash salt) ─────────────

def hash_password(password, salt=None, iterations=16384):
    if salt is None:
        salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(
        password.encode("utf-8"), salt=salt, n=iterations, r=8, p=1, dklen=32
    )
    return "scrypt$%d$%s$%s" % (iterations, salt.hex(), digest.hex())


def verify_password(password, stored):
    try:
        algo, it, salt, expect = stored.split("$")
        if algo != "scrypt":
            return False
        digest = hashlib.scrypt(
            password.encode("utf-8"), salt=bytes.fromhex(salt),
            n=int(it), r=8, p=1, dklen=32,
        )
        return hmac.compare_digest(digest.hex(), expect)
    except Exception:
        return False


# ── schema / seeding ────────────────────────────────────────────

def ensure_auth_schema(db):
    db.executescript("""
    CREATE TABLE IF NOT EXISTS auth_meta (
        key   TEXT PRIMARY KEY,
        value TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS auth_sessions (
        token      TEXT PRIMARY KEY,
        created_at REAL NOT NULL,
        expires_at REAL NOT NULL
    );
    CREATE TABLE IF NOT EXISTS auth_rate (
        ip      TEXT PRIMARY KEY,
        fails   INTEGER NOT NULL DEFAULT 0,
        window  REAL NOT NULL
    );
    """)
    db.commit()


def seed_password(db):
    """Store the password hash once. Plaintext is never persisted."""
    ensure_auth_schema(db)
    row = db.execute("SELECT value FROM auth_meta WHERE key='password_hash'").fetchone()
    if row:
        return
    stored = (os.environ.get("PCT_DASHBOARD_PASSWORD_HASH") or "").strip()
    if not stored:
        pw = os.environ.get("PCT_DASHBOARD_PASSWORD") or ""
        if pw:
            stored = hash_password(pw)
    if stored:
        db.execute(
            "INSERT OR IGNORE INTO auth_meta (key, value) VALUES ('password_hash', ?)",
            (stored,),
        )
        db.commit()


def _stored_hash(db):
    row = db.execute("SELECT value FROM auth_meta WHERE key='password_hash'").fetchone()
    return row[0] if row else None


# ── sessions ────────────────────────────────────────────────────

def _current_session(db):
    token = request.cookies.get(COOKIE)
    if not token:
        return None
    row = db.execute(
        "SELECT token, expires_at FROM auth_sessions WHERE token=?", (token,)
    ).fetchone()
    if not row:
        return None
    if row["expires_at"] < time.time():
        db.execute("DELETE FROM auth_sessions WHERE token=?", (token,))
        db.commit()
        return None
    return row


def make_require_auth(get_db):
    """Decorator factory: 401 unless a live session cookie is present."""

    def require_auth(f):
        @wraps(f)
        def wrapper(*a, **kw):
            db = get_db()
            ensure_auth_schema(db)
            if not _stored_hash(db):
                # Dev mode: no password configured -> endpoints stay open.
                return f(*a, **kw)
            if not _current_session(db):
                return jsonify({"ok": False, "message": "unauthorized"}), 401
            return f(*a, **kw)

        return wrapper

    return require_auth


# ── login rate limit (DB-backed, survives restarts) ─────────────

def _client_ip():
    xff = (request.headers.get("X-Forwarded-For") or "").split(",")[0].strip()
    return xff or request.remote_addr or "unknown"


def _rate_blocked(db, ip):
    row = db.execute("SELECT fails, window FROM auth_rate WHERE ip=?", (ip,)).fetchone()
    if not row:
        return False
    if time.time() - row["window"] >= LOGIN_WINDOW:
        db.execute("DELETE FROM auth_rate WHERE ip=?", (ip,))
        return False
    return row["fails"] >= LOGIN_MAX_FAILS


def _rate_fail(db, ip):
    """Record a failed login. `window` is the start of the current burst;
    if it is older than LOGIN_WINDOW the counter restarts at 1."""
    now = time.time()
    cutoff = now - LOGIN_WINDOW
    db.execute(
        """INSERT INTO auth_rate (ip, fails, window) VALUES (?, 1, ?)
           ON CONFLICT(ip) DO UPDATE SET
             fails = CASE WHEN window < ? THEN 1 ELSE fails + 1 END,
             window = CASE WHEN window < ? THEN ? ELSE window END""",
        (ip, now, cutoff, cutoff, now),
    )
    db.commit()


def _rate_ok(db, ip):
    db.execute("DELETE FROM auth_rate WHERE ip=?", (ip,))
    db.commit()


# ── routes ──────────────────────────────────────────────────────

def register_auth_routes(app, get_db):
    @app.route("/api/auth/login", methods=["POST"])
    def auth_login():
        db = get_db()
        ensure_auth_schema(db)
        ip = _client_ip()
        if _rate_blocked(db, ip):
            return jsonify({"ok": False, "message": "تلاش‌های ناموفق زیاد است؛ ۱۰ دقیقه صبر کنید"}), 429
        data = request.get_json(silent=True) or {}
        pw = data.get("password") or ""
        stored = _stored_hash(db)
        if not stored or not pw or not verify_password(pw, stored):
            _rate_fail(db, ip)
            return jsonify({"ok": False, "message": "رمز عبور اشتباه است"}), 401
        _rate_ok(db, ip)
        token = secrets.token_urlsafe(32)
        now = time.time()
        db.execute(
            "INSERT INTO auth_sessions (token, created_at, expires_at) VALUES (?, ?, ?)",
            (token, now, now + SESSION_DAYS * 86400),
        )
        db.execute("DELETE FROM auth_sessions WHERE expires_at < ?", (now,))
        db.commit()
        resp = jsonify({"ok": True})
        secure = (
            request.is_secure
            or (request.headers.get("X-Forwarded-Proto") or "").lower() == "https"
        )
        resp.set_cookie(
            COOKIE, token,
            max_age=SESSION_DAYS * 86400,
            httponly=True, secure=secure, samesite="Lax", path="/",
        )
        return resp

    @app.route("/api/auth/logout", methods=["POST"])
    def auth_logout():
        db = get_db()
        token = request.cookies.get(COOKIE)
        if token:
            db.execute("DELETE FROM auth_sessions WHERE token=?", (token,))
            db.commit()
        resp = jsonify({"ok": True})
        resp.delete_cookie(COOKIE, path="/")
        return resp

    @app.route("/api/auth/status", methods=["GET"])
    def auth_status():
        db = get_db()
        ensure_auth_schema(db)
        return jsonify({
            "auth_enabled": bool(_stored_hash(db)),
            "authenticated": bool(_current_session(db)),
        })

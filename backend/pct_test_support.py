"""Shared bootstrap for the backend test suite (PCM-12.3).

WHY THIS MODULE EXISTS
----------------------
``server.DB_PATH`` (``server.py:21``) is bound ONCE, at first import:

    DB_PATH = os.environ.get('PCT_DB') or <deployed thesaurus.db>

The old pattern -- every test module created its own ``tempfile.mkstemp()``
DB and set ``PCT_DB`` before importing ``server`` -- worked for a single
module but broke as soon as two or more modules were imported in one
process (the documented command
``python -m unittest test_api test_projects test_dashboard``): the app
kept talking to module #1's temp file while modules #2/#3 wiped their own,
unrelated files. Consequences observed (PCM-12.2, AT-18):

* the auth rate-limit rows from test A07 (5 failed logins / 10 min)
  survived into every later test class -> 429/401 on every login ->
  all D*/P* tests failed with ``KeyError`` and ``401 != 404``;
* A08's project leaked into D01 -> ``total=17 != 16``.

This module establishes ONE shared test database BEFORE ``server`` is
imported. Import it FIRST in every test module:

    import pct_test_support  # noqa: F401  (must precede `import server`)
    import server

Guarantees
----------
* every test class starts from a freshly re-initialised DB (call
  :func:`reset_db` from ``setUp``);
* rate-limit / session / project state can never leak across classes;
* test order and module combination are irrelevant: any subset, any
  order, repeated runs, all behave the same;
* the production database is NEVER opened: ``PCT_DB`` is always set,
  so ``server.DB_PATH`` can never fall back to ``backend/thesaurus.db``.

No production behaviour is affected -- this file is imported only by the
``test_*`` modules and is not part of the deployed application import
graph (``server.py`` never imports it).
"""
import atexit
import os
import tempfile

_fd, DB_PATH = tempfile.mkstemp(prefix="pct_test_", suffix=".db")
os.close(_fd)
os.environ["PCT_DB"] = DB_PATH


def _cleanup():
    """Best-effort removal of the temp DB at interpreter exit (WAL/SHM too)."""
    for suffix in ("", "-wal", "-shm"):
        try:
            os.remove(DB_PATH + suffix)
        except OSError:
            pass


atexit.register(_cleanup)
# Seed the dashboard password hash before the first server.init_db() so the
# auth tests can log in (PCM-09). Test-only value, never a production secret.
os.environ.setdefault("PCT_DASHBOARD_PASSWORD", "test-secret-123")


def reset_db():
    """Drop and re-create the shared test DB (main file + WAL/SHM sidecars).

    Call from each test class's ``setUp`` -- the same wipe the old
    per-module ``os.remove(_DB)`` attempted, but on the file the app
    actually uses. All per-request SQLite connections are closed by Flask's
    ``teardown_appcontext`` (tests run requests inside ``with client:``),
    so the file is safe to delete even on Windows.
    """
    import server  # resolved lazily: pct_test_support must be imported first

    for suffix in ("", "-wal", "-shm"):
        try:
            os.remove(DB_PATH + suffix)
        except FileNotFoundError:
            pass
    server.init_db()

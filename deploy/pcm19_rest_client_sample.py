#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PCM-19 — Third-party REST client sample (stdlib only, no pip installs).

A minimal, dependency-free client for the Knowledge Studio read API,
written for external consumers who cannot use the dashboard's
JavaScript bundle. It demonstrates the exact HTTP contract the two
additive OpenAPI specs declare (docs/openapi/*.yaml) and the API
contract tests enforce (backend/test_api_contract.py):

  * PCM-09 session auth: POST /api/auth/login sets an HttpOnly
    ``pct_session`` cookie that must be replayed on every request.
  * Response envelopes: {"ok": true, ...} /
    {"ok": false, "field"?: ..., "message": ...}.
  * Pagination: page / per_page (clamped to 100) / total / total_pages.
  * Error shapes: 400 (field), 401 (no session), 404 (unknown id).

Usage (the password is read from the environment or the command line —
never hardcode it, AGENTS §2.5):

    python deploy/pcm19_rest_client_sample.py --base https://corpus.ai.ismc.ir
    python deploy/pcm19_rest_client_sample.py --base https://corpus.ai.ismc.ir \
        --password-file ./pct-password.txt
    PCT_PASSWORD=... python deploy/pcm19_rest_client_sample.py --base ...

Run it with the same Python it is written for (3.8+, stdlib only).
Read-only by construction: it only calls GET endpoints.
"""
import argparse
import getpass
import json
import os
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request

DEFAULT_BASE = "https://corpus.ai.ismc.ir"
# Local dev (docker compose) example: --base http://127.0.0.1:5055
USER_AGENT = "pct-third-party-sample/1.0 (stdlib-only; PCM-19)"

STAGES = ("intake", "validate", "parse", "structure", "metadata",
          "normalize", "quality", "export")


def _force_utf8_stdio():
    """Persian text must survive any console (e.g. cp1252 on Windows)."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError, OSError):
            pass


class PctError(Exception):
    """Non-2xx HTTP answer or an {"ok": false} envelope."""

    def __init__(self, code, body):
        super().__init__("HTTP %s: %s" % (code, body))
        self.code = code
        self.body = body


class PctClient:
    """Tiny session-cookie client for the /api/knowledge read surface."""

    def __init__(self, base_url, timeout=30.0, insecure=False):
        self.base = base_url.rstrip("/")
        self.timeout = timeout
        self._ctx = ssl._create_unverified_context() if insecure else None
        self._cookie = None  # raw "pct_session=<token>" header value

    # ── transport ────────────────────────────────────────────────

    def _request(self, method, path, params=None, body=None):
        url = self.base + path
        if params:
            url += "?" + urllib.parse.urlencode(params)
        data = None
        headers = {"User-Agent": USER_AGENT}
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if self._cookie:
            headers["Cookie"] = self._cookie
        req = urllib.request.Request(url, data=data, headers=headers,
                                     method=method)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout,
                                        context=self._ctx) as resp:
                raw = resp.read().decode("utf-8")
                set_cookie = resp.headers.get("Set-Cookie", "")
                if set_cookie:
                    # keep only the token pair; drop Path/HttpOnly/...
                    self._cookie = set_cookie.split(";", 1)[0]
                return json.loads(raw)
        except urllib.error.HTTPError as e:
            raw = e.read().decode("utf-8", "replace")
            try:
                parsed = json.loads(raw)
            except ValueError:
                parsed = raw
            raise PctError(e.code, parsed)

    # ── auth (PCM-09) ────────────────────────────────────────────

    def login(self, password):
        """POST /api/auth/login — stores the session cookie.

        Rate limit: 5 failed logins / 10 min / client IP (see auth.py).
        """
        body = self._request("POST", "/api/auth/login",
                             body={"password": password})
        if not body.get("ok"):
            raise PctError(401, body)
        return body

    # ── collections (read) ───────────────────────────────────────

    def list_collections(self, page=1, per_page=50):
        body = self._request("GET", "/api/knowledge/collections",
                             {"page": page, "per_page": per_page})
        if not body.get("ok", True):
            raise PctError(200, body)
        return body

    def collection(self, coll_id):
        body = self._request("GET",
                             "/api/knowledge/collections/%s" % coll_id)
        if not body.get("ok", True):
            raise PctError(200, body)
        return body

    # ── PCM-14D work registry (read) ─────────────────────────────

    def list_works(self, search=None, page=1, per_page=50):
        params = {"page": page, "per_page": per_page}
        if search:
            params["search"] = search
        return self._get_checked("/api/knowledge/works", params)

    def work(self, work_id):
        return self._get_checked("/api/knowledge/works/%s" % work_id)

    def edition(self, edition_id):
        return self._get_checked("/api/knowledge/editions/%s" % edition_id)

    def volume(self, volume_id):
        return self._get_checked("/api/knowledge/volumes/%s" % volume_id)

    def resolve(self, document_id):
        """GET /api/knowledge/metadata/resolve?document_id=...

        Merges effective metadata across all scopes for one document.
        """
        return self._get_checked("/api/knowledge/metadata/resolve",
                                 {"document_id": document_id})

    # ── PCM-15/17 queue (read) ───────────────────────────────────

    def batches(self, collection_id, search=None, page=1, per_page=50):
        """GET /api/knowledge/import/batches — collection_id is REQUIRED
        (400 with field=collection_id when missing, 404 when unknown)."""
        params = {"collection_id": collection_id,
                  "page": page, "per_page": per_page}
        if search:
            params["search"] = search
        return self._get_checked("/api/knowledge/import/batches", params)

    def batch(self, batch_id):
        return self._get_checked(
            "/api/knowledge/import/batches/%s" % batch_id)

    def queue_summary(self, collection_id=None):
        params = {}
        if collection_id:
            params["collection_id"] = collection_id
        return self._get_checked("/api/knowledge/queue/summary", params)

    # ── helper ───────────────────────────────────────────────────

    def _get_checked(self, path, params=None):
        body = self._request("GET", path, params)
        if isinstance(body, dict) and body.get("ok") is False:
            raise PctError(200, body)
        return body


def _load_password(args):
    if args.password:
        return args.password
    if args.password_file:
        with open(args.password_file, encoding="utf-8") as fh:
            return fh.read().strip()
    if "PCT_PASSWORD" in os.environ:
        return os.environ["PCT_PASSWORD"]
    # last resort: ask interactively (never echoed)
    return getpass.getpass("Knowledge Studio dashboard password: ")


def _print_paged(title, rows, total, page, per_page, total_pages,
                 id_field="work_id", pretty_keys=()):
    print("\n=== %s (total=%d, page=%d/%d) ===" %
          (title, total, page, max(total_pages, 1)))
    for row in rows:
        bits = [row.get(id_field)]
        bits += ["%s=%s" % (k, row[k]) for k in pretty_keys
                 if row.get(k) not in (None, "")]
        print("  " + "  ".join(str(b) for b in bits if b))


def main(argv=None):
    _force_utf8_stdio()
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", default=DEFAULT_BASE,
                    help="API base URL (default: %(default)s)")
    ap.add_argument("--password", default=None,
                    help="dashboard password (prefer PCT_PASSWORD or "
                         "--password-file; never hardcode)")
    ap.add_argument("--password-file", default=None,
                    help="file containing the password (one line, chmod 600)")
    ap.add_argument("--collection", default=None,
                    help="collection_id for the batches/queue demo")
    ap.add_argument("--search", default=None,
                    help="optional search term for the works list")
    ap.add_argument("--insecure", action="store_true",
                    help="disable TLS certificate verification (LOCAL "
                         "testing only — never for production)")
    args = ap.parse_args(argv)

    client = PctClient(args.base, insecure=args.insecure)

    # 1) auth (PCM-09)
    try:
        client.login(_load_password(args))
    except PctError as e:
        print("LOGIN FAILED (%s): %s" % (e.code, e.body), file=sys.stderr)
        return 2
    print("logged in (session cookie stored, HttpOnly, 7 days)")

    # 2) collections (first page)
    try:
        colls = client.list_collections(per_page=10)
    except PctError as e:
        print("COLLECTIONS FAILED (%s): %s" % (e.code, e.body),
              file=sys.stderr)
        return 1
    rows = colls.get("collections", [])
    print("\n=== collections (total=%s) ===" % colls.get("total"))
    for c in rows:
        print("  %s  %s  [%s]" % (c.get("collection_id"), c.get("name"),
                                  c.get("slug")))

    # 3) PCM-14D: works + hierarchy
    try:
        works = client.list_works(search=args.search, per_page=20)
    except PctError as e:
        print("WORKS FAILED (%s): %s" % (e.code, e.body), file=sys.stderr)
        return 1
    _print_paged("works", works["works"], works["total"], works["page"],
                 works["per_page"], works["total_pages"],
                 pretty_keys=("title", "author", "document_count"))
    if works["works"]:
        w = works["works"][0]
        detail = client.work(w["work_id"])
        print("\nwork detail %s: %d edition(s), %d document(s)" % (
            w["work_id"], len(detail.get("editions", [])),
            len(detail.get("documents", []))))
        for e in detail.get("editions", [])[:5]:
            print("  edition %s  %s / %s" % (
                e.get("edition_id"), e.get("publisher"),
                e.get("publish_year")))

    # 4) PCM-15/17: batches + live queue counters
    cid = args.collection
    if not cid and rows:
        cid = rows[0].get("collection_id")
    if cid:
        try:
            b = client.batches(cid, per_page=10)
        except PctError as e:
            # expected contract: 400 (missing) / 404 (unknown collection)
            print("BATCHES FAILED (%s): %s" % (e.code, e.body),
                  file=sys.stderr)
            return 1
        counters = b["queue"]["counters"]
        print("\n=== batches of %s (total=%d) ===" % (cid, b["total"]))
        for row in b["batches"]:
            print("  %s  %s  files=%d processed=%d failed=%d "
                  "status=%s paused=%s" % (
                      row["batch_id"], row.get("folder_name"),
                      row["file_count"], row["processed_count"],
                      row["failed_count"], row["status"], row["paused"]))
        print("queue counters: " + json.dumps(counters))
        s = client.queue_summary(cid)
        print("queue summary : " + json.dumps(s["counters"]))
    else:
        print("\n(no collection found — skipping the queue demo)")

    # 5) error-contract demo: unknown id must be a clean 404
    try:
        client.work("w-ffffffff")
        print("\nERROR-CONTRACT: unexpected success for unknown work",
              file=sys.stderr)
        return 1
    except PctError as e:
        print("\nerror contract: unknown work -> HTTP %s (expected 404)"
              % e.code)
        if e.code != 404:
            return 1

    print("\nDONE — read-only; nothing was written.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

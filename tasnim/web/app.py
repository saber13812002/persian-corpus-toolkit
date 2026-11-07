# -*- coding: utf-8 -*-
"""Tasnim Web V1 — app factory + standalone server entry (PCM-20.6.4 §7.4).

Usage (local runbook):
    python -X utf8 -m tasnim.web.app --db tasnim/data/readmodel/v0003/tasnim_readmodel.db
serves 127.0.0.1:5071 (SSR site + API). ``--db`` may be omitted when the
``TASNIM_DB_PATH`` environment variable points at tasnim_readmodel.db.

The API blueprint (12 endpoints + /openapi.json + /docs) is mounted at
/api/v1/tasnim/. The SSR frontend (V1 RTL reading experience) is mounted
at the root: /, /volumes, /page/<n>, /topics, /surahs, /search, /about.

Offline docs: a minimal local HTML shell that fetches the OpenAPI 3.1
spec from /openapi.json — no CDN, no network (documented deviation from
full Swagger UI).
"""
import os

from tasnim.web.api import (ApiError, SerializerError, create_app)

__all__ = ["create_app", "main", "ApiError", "SerializerError"]


def main(argv=None):
    import argparse
    p = argparse.ArgumentParser(prog="tasnim.web.app")
    p.add_argument("--db", default=os.environ.get("TASNIM_DB_PATH"),
                   help="tasnim_readmodel.db path "
                        "(default: $TASNIM_DB_PATH)")
    p.add_argument("--port", type=int, default=5071)
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--rate-db", default=None,
                   help="rate-limit sqlite path (default: beside read model)")
    args = p.parse_args(argv)
    if not args.db:
        p.error("--db is required (or set TASNIM_DB_PATH)")
    rate_db = args.rate_db or os.path.join(
        os.path.dirname(os.path.abspath(args.db)), "tasnim_rate_limits.db")
    app = create_app(args.db, rate_db_path=rate_db)
    app.run(host=args.host, port=args.port, debug=False)


if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
"""Tasnim Web V1 — read-only API blueprint (PCM-20.6.4, §5).

Base path: /api/v1/tasnim/  (12 endpoints, JSON only, UTF-8).

HP-1 layer 2: every serializer is DENY-BY-DEFAULT — response dicts are
built from full DB row dicts (SELECT *) and pass through
``strict_pick`` whitelists; any non-whitelisted key (e.g. a future
``hidden_summary`` column) raises SerializerError (test T-HC-3).

Documented deviation: /surahs and /surahs/{id} return **503
SURAH_INDEX_NOT_SUPPORTED** (mission contract) instead of the spec's
200-unavailable / 404-SURAH_UNAVAILABLE.
"""
import base64
import hashlib
import html
import json
import os
import sqlite3
import threading
import time
import uuid
from urllib.parse import quote

from flask import Blueprint, Response, g, jsonify, request

from tasnim.web.readmodel import (RAG_STATUS, TOPIC_NORM_VERSION,
                                  build_fts_match, make_snippet,
                                  tokenize_fa)

CANONICAL_BASE = "https://tasnim.ai.ismc.ir"
ERROR_BASE = CANONICAL_BASE + "/errors"
DEFAULT_LIMIT = 50
SEARCH_DEFAULT_LIMIT = 20
MAX_LIMIT = 200

SURAH_REASON = ("در پیکرهٔ v0003 هیچ مارکر مطمئن سوره وجود ندارد: فیلد surah در "
                "schema نیست؛ 0 هدر با پیشوند سخت سوره؛ پوشش canonical 0/114")
SURAH_PLANNED = "surah index text-level برای نسخهٔ بعدی پیکره (خارج از V1)"

EXEMPT_PATHS = ("/health", "/openapi.json", "/docs")

# --------------------------------------------------------------------------
# errors
# --------------------------------------------------------------------------


class SerializerError(Exception):
    """HP-1 layer 2: non-whitelisted key reached the serializer."""


class ApiError(Exception):
    def __init__(self, status, code, title, message, details=None,
                 type_name=None, headers=None):
        super().__init__(message)
        self.status = status
        self.code = code
        self.title = title
        self.message = message
        self.details = details
        self.type_name = type_name or code.lower().replace("_", "-")
        self.headers = headers or {}

    def to_dict(self, request_id):
        return {
            "type": ERROR_BASE + "/" + self.type_name,
            "title": self.title,
            "status": self.status,
            "code": self.code,
            "message": self.message,
            "details": self.details,
            "request_id": request_id,
        }


# --------------------------------------------------------------------------
# HP-1 layer 2: strict whitelist serializer (deny-by-default)
# --------------------------------------------------------------------------


def strict_pick(source, allowed, path=""):
    """Copy only whitelisted keys from `source`. Any key outside the
    whitelist RAISES — deny-by-default, per spec §5.6 layer 2."""
    allowed = set(allowed)
    out = {}
    for k in source:
        if k not in allowed:
            raise SerializerError(
                "non-whitelisted key %r reached serializer (%s)"
                % (k, path or k))
        out[k] = source[k]
    return out


# --------------------------------------------------------------------------
# rate limiting (DB-backed, separate store file)
# --------------------------------------------------------------------------


class RateLimiter:
    def __init__(self, db_path, search=30, read=120, clock=None):
        self.clock = clock or time.time
        self.limits = {"search": int(search), "read": int(read)}
        self._conn = None
        self._db_path = db_path
        # One shared connection, guarded: the Flask dev server is threaded,
        # and SQLite objects are not usable across threads by default
        # (ProgrammingError on worker threads). check_same_thread=False +
        # a lock serializes the tiny read-modify-write.
        self._lock = threading.Lock()
        if db_path:
            self._conn = sqlite3.connect(db_path, check_same_thread=False)
            self._conn.execute(
                "CREATE TABLE IF NOT EXISTS tasnim_rate_limits("
                " ip TEXT NOT NULL, endpoint_class TEXT NOT NULL,"
                " window_start INTEGER NOT NULL, count INTEGER NOT NULL,"
                " PRIMARY KEY(ip, endpoint_class, window_start))")
            self._conn.commit()

    def check(self, ip, endpoint_class):
        if self._conn is None:
            return
        limit = self.limits.get(endpoint_class)
        if limit is None:
            return
        now = int(self.clock())
        window = now - (now % 60)
        with self._lock:
            conn = self._conn
            row = conn.execute(
                "SELECT count FROM tasnim_rate_limits WHERE ip=? AND"
                " endpoint_class=? AND window_start=?",
                (ip, endpoint_class, window)).fetchone()
            if row:
                n = row[0] + 1
                conn.execute(
                    "UPDATE tasnim_rate_limits SET count=? WHERE ip=? AND"
                    " endpoint_class=? AND window_start=?",
                    (n, ip, endpoint_class, window))
            else:
                n = 1
                conn.execute(
                    "INSERT INTO tasnim_rate_limits(ip, endpoint_class,"
                    " window_start, count) VALUES(?,?,?,?)",
                    (ip, endpoint_class, window, n))
            conn.commit()
        if n > limit:
            raise ApiError(
                429, "RATE_LIMITED", "Rate limit exceeded",
                "سقف %d درخواست در هر دقیقه برای %s رد شد."
                % (limit, endpoint_class),
                details={"limit": limit, "window": "60s",
                         "endpoint_class": endpoint_class},
                headers={"Retry-After": str(max(1, window + 60 - now))})

    def close(self):
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------


def _utcnow():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _like_prefix(q):
    return (q.replace("\\", "\\\\").replace("%", "\\%")
            .replace("_", "\\_")) + "%"


def parse_pagination(default_limit=DEFAULT_LIMIT):
    """limit (default, max 200) + offset OR opaque page_token (base64)."""
    try:
        limit = int(request.args.get("limit", default_limit))
    except (TypeError, ValueError):
        raise ApiError(400, "INVALID_PARAMETER", "Invalid limit",
                       "limit باید عدد باشد", details={"param": "limit"})
    limit = max(1, min(MAX_LIMIT, limit))
    token = request.args.get("page_token")
    if token:
        try:
            offset = int(base64.urlsafe_b64decode(
                token.encode("ascii")).decode("ascii"))
        except Exception:
            raise ApiError(400, "INVALID_PAGE_TOKEN", "Invalid page_token",
                           "page_token نامعتبر است",
                           details={"param": "page_token"})
    else:
        try:
            offset = int(request.args.get("offset", 0))
        except (TypeError, ValueError):
            raise ApiError(400, "INVALID_PARAMETER", "Invalid offset",
                           "offset باید عدد باشد", details={"param": "offset"})
    if offset < 0:
        raise ApiError(400, "INVALID_PARAMETER", "Invalid offset",
                       "offset نمی‌تواند منفی باشد",
                       details={"param": "offset"})
    return limit, offset


def make_token(offset):
    return base64.urlsafe_b64encode(str(offset).encode("ascii")).decode()


# --------------------------------------------------------------------------
# blueprint
# --------------------------------------------------------------------------


def make_blueprint(state):
    meta = state["meta"]
    V = meta.get("corpus_version", "unknown")
    C = meta.get("content_sha256", "")
    DBSHA = meta.get("db_sha256", "")

    bp = Blueprint("tasnim", __name__)

    # -- request plumbing ---------------------------------------------------
    @bp.before_request
    def _before_request():
        g.request_id = "req_" + uuid.uuid4().hex[:16]
        g._t0 = time.time()
        path = request.path
        for ex in EXEMPT_PATHS:
            if path.endswith(ex):
                return None
        cls = "search" if path.endswith("/search") else "read"
        xf = request.headers.get("X-Forwarded-For")
        ip = (xf.split(",")[0].strip() if xf
              else (request.remote_addr or "local"))
        state["rate"].check(ip, cls)
        return None

    @bp.after_request
    def _after_request(resp):
        t = getattr(g, "_t0", None)
        ms = round((time.time() - t) * 1000, 1) if t else None
        g._t0 = time.time()
        try:
            state["log"] and state["log"].info(json.dumps({
                "request_id": getattr(g, "request_id", "-"),
                "path": request.path,
                "status": resp.status_code,
                "ms": ms,
            }, ensure_ascii=False))
        except Exception:
            pass
        return resp

    # -- envelope -----------------------------------------------------------
    def etag_for(key, weak=False):
        h = hashlib.sha256(
            ("%s|%s" % (DBSHA, key)).encode("utf-8")).hexdigest()[:32]
        return ('W/"%s"' % h) if weak else ('"%s"' % h)

    def _etag_matches(etag):
        inm = request.headers.get("If-None-Match")
        if not inm or not etag:
            return False
        want = etag.strip('"')
        if want.startswith("W/"):
            want = want[2:].strip('"')
        for cand in inm.split(","):
            c = cand.strip()
            if c.startswith("W/"):
                c = c[2:]
            if c.strip('"') == want:
                return True
        return False

    def respond(data, etag=None, cache=None, token=None, extra_meta=None):
        if _etag_matches(etag):
            r = Response(status=304)
            if etag:
                r.headers["ETag"] = etag
            if cache:
                r.headers["Cache-Control"] = cache
            return r
        m = {
            "request_id": g.request_id,
            "readmodel": {"version": V, "content_sha256": C},
            "generated_at": _utcnow(),
        }
        if token:
            m["next_page_token"] = token
        if extra_meta:
            m.update(extra_meta)
        body = jsonify({"data": data, "meta": m})
        if etag:
            body.headers["ETag"] = etag
        if cache:
            body.headers["Cache-Control"] = cache
        return body

    def get_db():
        if "tasnim_db" not in g:
            p = quote(os.path.abspath(state["readmodel_path"]), safe="/:")
            conn = sqlite3.connect("file:%s?mode=ro" % p, uri=True)
            conn.row_factory = sqlite3.Row
            g.tasnim_db = conn
        return g.tasnim_db

    # ======================================================================
    # 1) /catalog
    # ======================================================================
    @bp.get("/catalog")
    def catalog():
        db = get_db()
        w = db.execute("SELECT * FROM works LIMIT 1").fetchone()
        e = db.execute("SELECT * FROM editions LIMIT 1").fetchone()
        pages = db.execute("SELECT COUNT(*) c FROM pages").fetchone()["c"]
        vols = db.execute("SELECT COUNT(*) c FROM volumes").fetchone()["c"]
        topics = db.execute("SELECT COUNT(*) c FROM topics").fetchone()["c"]
        heads = db.execute("SELECT COUNT(*) c FROM headings").fetchone()["c"]
        missing = db.execute(
            "SELECT COALESCE(SUM(missing_count),0) c FROM coverage"
            " WHERE scope='global'").fetchone()["c"]
        data = {
            "work": {"work_id": w["work_id"], "name": w["work_name"]},
            "edition": {"edition_id": e["edition_id"],
                        "name": e["edition_name"]},
            "counts": {"pages": pages, "volumes": vols, "topics": topics,
                       "headings": heads, "missing_item_index": missing},
            "coverage": {
                "present_ratio": round(pages / (pages + missing), 4)
                if (pages + missing) else None,
                "definition": "pages/(pages+missing_item_index) — "
                              "شمارنده‌های زندهٔ read model",
            },
            "rag_status": RAG_STATUS,
            "readmodel": {"version": V, "content_sha256": C},
        }
        return respond(data, etag=etag_for("/catalog"),
                       cache="public, max-age=60, stale-while-revalidate=300")

    # ======================================================================
    # 2) /volumes
    # ======================================================================
    def _volume_coverage(db, vid):
        rows = db.execute(
            "SELECT missing_from, missing_to, missing_count, status FROM"
            " coverage WHERE scope=? ORDER BY missing_from", (vid,)).fetchall()
        return {
            "missing_count": sum(r["missing_count"] for r in rows),
            "ranges": [[r["missing_from"], r["missing_to"]] for r in rows],
            "statuses": [r["status"] for r in rows],
        }

    @bp.get("/volumes")
    def volumes_list():
        db = get_db()
        limit, offset = parse_pagination()
        sort = request.args.get("sort", "volume_no")
        if sort == "volume_no":
            order = ("ORDER BY (volume_no IS NULL), volume_no ASC,"
                     " volume_id ASC")
        elif sort == "page_count":
            order = "ORDER BY page_count DESC, volume_id ASC"
        else:
            raise ApiError(400, "INVALID_SORT", "Invalid sort",
                           "sort باید volume_no یا page_count باشد",
                           details={"allowed": ["volume_no", "page_count"]})
        total = db.execute("SELECT COUNT(*) c FROM volumes").fetchone()["c"]
        rows = db.execute(
            "SELECT * FROM volumes %s LIMIT ? OFFSET ?" % order,
            (limit, offset)).fetchall()
        items = []
        for r in rows:
            ov = r["overlap_note"]
            items.append({
                "volume_id": r["volume_id"],
                "volume_no": r["volume_no"],
                "title": r["volume_title"],
                "page_count": r["page_count"],
                "item_index_min": r["item_index_min"],
                "item_index_max": r["item_index_max"],
                "coverage": _volume_coverage(db, r["volume_id"]),
                "ambiguity": {"flag": bool(r["ambiguity_flag"]),
                              "overlap_note": json.loads(ov) if ov else None},
                "first_page_item_index": r["item_index_min"],
                "last_page_item_index": r["item_index_max"],
            })
        token = make_token(offset + limit) if offset + limit < total else None
        return respond({"items": items, "total": total},
                       etag=etag_for("/volumes|%s|%s|%s"
                                     % (sort, limit, offset)),
                       cache="public, max-age=300", token=token)

    # ======================================================================
    # 3) /volumes/{id}
    # ======================================================================
    @bp.get("/volumes/<volume_id>")
    def volume_detail(volume_id):
        db = get_db()
        r = db.execute("SELECT * FROM volumes WHERE volume_id=?",
                       (volume_id,)).fetchone()
        if r is None:
            raise ApiError(404, "VOLUME_NOT_FOUND", "Volume not found",
                           "جلدی با volume_id «%s» در read model نیست."
                           % volume_id,
                           details={"volume_id": volume_id})
        ov = r["overlap_note"]
        top = db.execute(
            "SELECT heading_text AS text, COUNT(*) c FROM headings"
            " WHERE volume_id=? GROUP BY heading_text"
            " ORDER BY c DESC, heading_text ASC LIMIT 10",
            (volume_id,)).fetchall()
        mr = db.execute(
            "SELECT missing_from, missing_to, missing_count, status FROM"
            " coverage WHERE scope=? ORDER BY missing_from",
            (volume_id,)).fetchall()
        first = db.execute(
            "SELECT page_id, item_index FROM pages WHERE volume_id=?"
            " ORDER BY item_index ASC LIMIT 1", (volume_id,)).fetchone()
        last = db.execute(
            "SELECT page_id, item_index FROM pages WHERE volume_id=?"
            " ORDER BY item_index DESC LIMIT 1", (volume_id,)).fetchone()
        data = {
            "volume_id": r["volume_id"],
            "volume_no": r["volume_no"],
            "title": r["volume_title"],
            "strategy": r["volume_strategy"],
            "page_count": r["page_count"],
            "item_index_min": r["item_index_min"],
            "item_index_max": r["item_index_max"],
            "coverage": _volume_coverage(db, volume_id),
            "ambiguity": {"flag": bool(r["ambiguity_flag"]),
                          "overlap_note": json.loads(ov) if ov else None},
            "top_headings": [{"text": t["text"], "count": t["c"]}
                             for t in top],
            "missing_ranges": [
                {"from": m["missing_from"], "to": m["missing_to"],
                 "missing_count": m["missing_count"], "status": m["status"]}
                for m in mr],
            "dup_item_index_with": json.loads(ov) if ov else [],
            "first_page": ({"page_id": first["page_id"],
                            "item_index": first["item_index"]}
                           if first else None),
            "last_page": ({"page_id": last["page_id"],
                           "item_index": last["item_index"]}
                          if last else None),
            "first_page_item_index": r["item_index_min"],
            "last_page_item_index": r["item_index_max"],
        }
        return respond(data, etag=etag_for("/volumes/" + volume_id),
                       cache="public, max-age=3600")

    # ======================================================================
    # 4-5) /surahs — honest unavailable (503, mission contract)
    # ======================================================================
    def _surah_503(surah_id=None):
        details = {
            "status": "not_supported",
            "coverage": "0/114",
            "reason": SURAH_REASON,
            "next_planned": SURAH_PLANNED,
            "evidence": [
                "0 فیلد surah در schema پیکره",
                "0 هدر با پیشوند سخت «تفسیر سوره/سوره/سورة» از 10,739 هدر",
                "0 صفحهٔ تعلق‌داده‌شده به سوره",
                "265 هدرِ شلِ حاوی «سوره» همه sub-heading عمومی‌اند",
            ],
        }
        if surah_id is not None:
            details["surah_id"] = surah_id
        raise ApiError(503, "SURAH_INDEX_NOT_SUPPORTED",
                       "Surah index not supported",
                       SURAH_REASON, details=details)

    @bp.get("/surahs")
    def surahs():
        _surah_503()

    @bp.get("/surahs/<surah_id>")
    def surah_detail(surah_id):
        _surah_503(surah_id)

    # ======================================================================
    # 6) /topics
    # ======================================================================
    @bp.get("/topics")
    def topics_list():
        db = get_db()
        limit, offset = parse_pagination()
        q = (request.args.get("q") or "").strip()
        min_pages = request.args.get("min_pages")
        sort = request.args.get("sort", "page_count")
        where, params = [], []
        if q:
            where.append("normalized_text LIKE ? ESCAPE '\\'")
            params.append(_like_prefix(q))
        if min_pages is not None:
            try:
                min_pages_i = int(min_pages)
            except (TypeError, ValueError):
                raise ApiError(400, "INVALID_PARAMETER", "Invalid min_pages",
                               "min_pages باید عدد باشد",
                               details={"param": "min_pages"})
            where.append("page_count >= ?")
            params.append(min_pages_i)
        if sort == "page_count":
            order = "ORDER BY page_count DESC, topic_id ASC"
        elif sort == "name":
            order = "ORDER BY normalized_text ASC, topic_id ASC"
        else:
            raise ApiError(400, "INVALID_SORT", "Invalid sort",
                           "sort باید page_count یا name باشد",
                           details={"allowed": ["page_count", "name"]})
        sql = "SELECT * FROM topics"
        if where:
            sql += " WHERE " + " AND ".join(where)
        total = db.execute(
            "SELECT COUNT(*) c FROM topics"
            + (" WHERE " + " AND ".join(where) if where else ""),
            params).fetchone()["c"]
        rows = db.execute(sql + " " + order + " LIMIT ? OFFSET ?",
                          params + [limit, offset]).fetchall()
        items = [{
            "topic_id": r["topic_id"],
            "display_text": r["display_text"],
            "page_count": r["page_count"],
            "volume_count": r["volume_count"],
            "first_page_id": r["first_page_id"],
            "first_item_index": r["first_item_index"],
        } for r in rows]
        token = make_token(offset + limit) if offset + limit < total else None
        return respond({"items": items, "total": total},
                       etag=etag_for("/topics|%s|%s|%s|%s"
                                     % (q, min_pages, sort, offset)),
                       cache="public, max-age=300", token=token)

    # ======================================================================
    # 7) /topics/{id}
    # ======================================================================
    @bp.get("/topics/<topic_id>")
    def topic_detail(topic_id):
        db = get_db()
        r = db.execute("SELECT * FROM topics WHERE topic_id=?",
                       (topic_id,)).fetchone()
        if r is None:
            raise ApiError(404, "TOPIC_NOT_FOUND", "Topic not found",
                           "موضوعی با topic_id «%s» وجود ندارد." % topic_id,
                           details={"topic_id": topic_id})
        # parent topic: majority normalized text of parent headings
        pr = db.execute(
            "SELECT h2.normalized_text norm, COUNT(*) c FROM headings h1"
            " JOIN headings h2 ON h2.page_id = h1.parent_heading_page_id"
            " WHERE h1.topic_id=? GROUP BY h2.normalized_text"
            " ORDER BY c DESC, h2.normalized_text ASC LIMIT 1",
            (topic_id,)).fetchone()
        parent = None
        if pr:
            pt = db.execute(
                "SELECT topic_id, display_text FROM topics"
                " WHERE normalized_text=?", (pr["norm"],)).fetchone()
            if pt:
                parent = {"topic_id": pt["topic_id"],
                          "display_text": pt["display_text"],
                          "count": pr["c"]}
        limit, offset = parse_pagination()
        where = "h.topic_id=?"
        params = [topic_id]
        total = db.execute(
            "SELECT COUNT(*) c FROM headings h WHERE " + where,
            params).fetchone()["c"]
        rows = db.execute(
            "SELECT p.item_index, p.page_id, p.volume_id, v.volume_no,"
            " h.heading_text, h.record_id,"
            " (p.heading_record_id = h.record_id) is_heading_page"
            " FROM headings h JOIN pages p ON p.page_id = h.page_id"
            " LEFT JOIN volumes v ON v.volume_id = p.volume_id"
            " WHERE " + where +
            " ORDER BY p.item_index ASC, p.page_id ASC LIMIT ? OFFSET ?",
            params + [limit, offset]).fetchall()
        occ = [{
            "item_index": o["item_index"],
            "page_id": o["page_id"],
            "volume_ref": {"volume_id": o["volume_id"],
                           "volume_no": o["volume_no"]},
            "heading_text": o["heading_text"],
            "is_heading_page": bool(o["is_heading_page"]),
        } for o in rows]
        first3 = db.execute(
            "SELECT p.page_id, p.item_index FROM headings h"
            " JOIN pages p ON p.page_id = h.page_id WHERE h.topic_id=?"
            " ORDER BY p.item_index ASC, p.page_id ASC LIMIT 3",
            (topic_id,)).fetchall()
        data = {
            "topic_id": r["topic_id"],
            "normalized_text": r["normalized_text"],
            "display_text": r["display_text"],
            "page_count": r["page_count"],
            "volume_count": r["volume_count"],
            "first_page_id": r["first_page_id"],
            "first_item_index": r["first_item_index"],
            "parent_topic": parent,
            "occurrences_total": total,
            "occurrences": occ,
            "sample_pages": [{"page_id": s["page_id"],
                              "item_index": s["item_index"]}
                             for s in first3],
        }
        token = make_token(offset + limit) if offset + limit < total else None
        return respond(data, etag=etag_for("/topics/" + topic_id +
                                           "|%s" % offset),
                       cache="public, max-age=3600", token=token)

    # ======================================================================
    # 8) /pages/{n}   — the heart of the contract
    # ======================================================================
    def _missing_range_for(db, ii):
        r = db.execute(
            "SELECT missing_from, missing_to FROM coverage WHERE"
            " scope='global' AND missing_from<=? AND ?<=missing_to LIMIT 1",
            (ii, ii)).fetchone()
        return [r["missing_from"], r["missing_to"]] if r else None

    def _nearest(db, ii, direction):
        if direction == "prev":
            r = db.execute(
                "SELECT item_index, page_id FROM pages WHERE item_index<?"
                " AND dup_rank=0 ORDER BY item_index DESC LIMIT 1",
                (ii,)).fetchone()
        else:
            r = db.execute(
                "SELECT item_index, page_id FROM pages WHERE item_index>?"
                " AND dup_rank=0 ORDER BY item_index ASC LIMIT 1",
                (ii,)).fetchone()
        return None if r is None else (r["item_index"], r["page_id"])

    def _page_reference(db, ii, neighbor, direction):
        """neighbor: (nn, page_id) | None. Gap-aware reference object."""
        if neighbor is None:
            return {"item_index": None, "page_id": None, "exists": False,
                    "gap_before": 0,
                    "reason": ("beginning_of_corpus" if direction == "prev"
                               else "end_of_corpus")}
        nn, pid = neighbor
        gap = nn - ii if direction == "next" else ii - nn
        ref = {"item_index": nn, "page_id": pid, "exists": True,
               "gap_before": gap}
        if gap > 1:
            mr = _missing_range_for(
                db, ii + 1 if direction == "next" else ii - 1)
            if mr:
                ref["in_missing_range"] = mr
                if direction == "next":
                    ref["next_available_item_index"] = nn
                    ref["gap"] = {"item_index": ii + 1, "exists": False,
                                  "gap_before": 1, "in_missing_range": mr,
                                  "next_available_item_index": nn}
                else:
                    ref["prev_available_item_index"] = nn
                    ref["gap"] = {"item_index": ii - 1, "exists": False,
                                  "gap_before": 1, "in_missing_range": mr,
                                  "prev_available_item_index": nn}
        return ref

    @bp.get("/pages/<int:item_index>")
    def page(item_index):
        db = get_db()
        try:
            dup_rank = int(request.args.get("dup_rank", 0))
        except (TypeError, ValueError):
            raise ApiError(400, "INVALID_PARAMETER", "Invalid dup_rank",
                           "dup_rank باید عدد باشد", details={"param": "dup_rank"})
        if dup_rank < 0:
            raise ApiError(400, "INVALID_PARAMETER", "Invalid dup_rank",
                           "dup_rank نمی‌تواند منفی باشد",
                           details={"param": "dup_rank"})
        row = db.execute(
            "SELECT * FROM pages WHERE item_index=? AND dup_rank=? LIMIT 1",
            (item_index, dup_rank)).fetchone()
        if row is None:
            mr = _missing_range_for(db, item_index)
            prev = _nearest(db, item_index, "prev")
            nxt = _nearest(db, item_index, "next")
            near = [x for x in (prev and prev[0], nxt and nxt[0]) if x]
            sug = "، ".join(str(x) for x in near) or "—"
            raise ApiError(
                404, "PAGE_NOT_FOUND", "Page not found",
                "صفحه‌ای با item_index %d در پیکره وجود ندارد." % item_index,
                details={"item_index": item_index,
                         "in_missing_range": mr,
                         "suggestion": "نزدیک‌ترین صفحات موجود: %s" % sug})
        vol = db.execute("SELECT * FROM volumes WHERE volume_id=?",
                         (row["volume_id"],)).fetchone()
        vols_here = db.execute(
            "SELECT COUNT(DISTINCT volume_id) c FROM pages"
            " WHERE item_index=?", (item_index,)).fetchone()["c"]
        ambiguous = vols_here > 1
        heading = None
        if row["heading_record_id"]:
            h = db.execute(
                "SELECT record_id, heading_text, next_page_id FROM headings"
                " WHERE record_id=?", (row["heading_record_id"],)).fetchone()
            if h:
                heading = {"record_id": h["record_id"],
                           "text": h["heading_text"],
                           "next_page_id": h["next_page_id"]}
        flags = []
        if row["flag_short"]:
            flags.append("short")
        if row["flag_empty"]:
            flags.append("empty")
        if row["flag_truncated_2000"]:
            flags.append("truncated_at_2000")
        if vols_here > 1:
            flags.append("dup_item_index")
        dups = db.execute(
            "SELECT dup_rank, page_id, volume_id FROM pages WHERE"
            " item_index=? AND page_id<>? ORDER BY dup_rank, page_id",
            (item_index, row["page_id"])).fetchall()
        prev = _nearest(db, item_index, "prev")
        nxt = _nearest(db, item_index, "next")
        canon = CANONICAL_BASE + "/page/%d" % item_index
        if dup_rank > 0:
            canon += "?dup_rank=%d" % dup_rank
        # HP-1 layer 2: every block is built from an explicit whitelist and
        # then guarded by strict_pick — any non-whitelisted key (e.g. a
        # future hidden_summary column or a serializer bug) raises 500.
        visible = strict_pick({"text": row["text"],
                               "char_count": row["char_count"],
                               "record_class": row["record_class"]},
                              {"text", "char_count", "record_class"},
                              "visible_content")
        metadata = strict_pick({"page_id": row["page_id"],
                                "content_sha256": row["content_sha256"],
                                "captured_at": row["captured_at"],
                                "source_page_id": row["source_page_id"],
                                "section": row["section"],
                                "source_url": row["url"]},
                               {"page_id", "content_sha256", "captured_at",
                                "source_page_id", "section", "source_url"},
                               "metadata")
        quality = strict_pick({"status": row["status"], "flags": flags,
                               "truncated_at_source":
                                   bool(row["flag_truncated_2000"]),
                               "source_char_cap": (2000
                                                   if row["flag_truncated_2000"]
                                                   else None)},
                              {"status", "flags", "truncated_at_source",
                               "source_char_cap"}, "quality")
        if heading is not None:
            heading = strict_pick(heading, {"record_id", "text",
                                            "next_page_id"}, "heading")
        dups = strict_pick({"items": [
            {"dup_rank": d["dup_rank"], "page_id": d["page_id"],
             "volume_id": d["volume_id"]} for d in dups]},
            {"items"}, "duplicates")
        wk = db.execute("SELECT work_id FROM works LIMIT 1").fetchone()
        ed = db.execute("SELECT edition_id FROM editions LIMIT 1").fetchone()
        reference = strict_pick({
            "work_id": wk["work_id"] if wk else None,
            "edition_id": ed["edition_id"] if ed else None,
            "volume_id": row["volume_id"],
            "volume_no": vol["volume_no"],
            "item_index": item_index, "barg": row["barg"],
            "page_id": row["page_id"],
            "content_sha256": row["content_sha256"],
            "source_url": row["url"],
            "canonical_url": canon},
            {"work_id", "edition_id", "volume_id", "volume_no",
             "item_index", "barg", "page_id", "content_sha256",
             "source_url", "canonical_url"}, "reference")
        volume = strict_pick({
            "volume_id": vol["volume_id"],
            "volume_no": vol["volume_no"],
            "title": vol["volume_title"],
            "attribution": "ambiguous" if ambiguous else "recorded",
            "ambiguity": ambiguous},
            {"volume_id", "volume_no", "title", "attribution", "ambiguity"},
            "volume")
        data = strict_pick({
            "page_id": row["page_id"], "item_index": item_index,
            "dup_rank": dup_rank, "barg": row["barg"],
            "volume": volume, "heading": heading,
            "visible_content": visible,
            "next_page_reference": _page_reference(db, item_index, nxt,
                                                   "next"),
            "previous_page_reference": _page_reference(db, item_index, prev,
                                                       "prev"),
            "metadata": metadata, "quality": quality,
            "duplicates": dups["items"], "reference": reference,
            "rag_status": RAG_STATUS,
        }, {
            "page_id", "item_index", "dup_rank", "barg", "volume",
            "heading", "visible_content", "next_page_reference",
            "previous_page_reference", "metadata", "quality", "duplicates",
            "reference", "rag_status",
        }, "page")
        return respond(data, etag=etag_for("/pages/" + row["page_id"]),
                       cache="public, max-age=3600")

    # ======================================================================
    # 9) /pages/{n}/neighbors
    # ======================================================================
    @bp.get("/pages/<int:item_index>/neighbors")
    def page_neighbors(item_index):
        db = get_db()
        row = db.execute(
            "SELECT page_id FROM pages WHERE item_index=? AND dup_rank=0"
            " LIMIT 1", (item_index,)).fetchone()
        if row is None:
            mr = _missing_range_for(db, item_index)
            raise ApiError(
                404, "PAGE_NOT_FOUND", "Page not found",
                "صفحه‌ای با item_index %d در پیکره وجود ندارد." % item_index,
                details={"item_index": item_index,
                         "in_missing_range": mr})
        prev = _nearest(db, item_index, "prev")
        nxt = _nearest(db, item_index, "next")
        prev_range = _missing_range_for(db, item_index - 1) \
            if item_index - 1 >= 0 else None
        next_range = _missing_range_for(db, item_index + 1)
        data = {
            "current": item_index,
            "prev": _page_reference(db, item_index, prev, "prev"),
            "next": _page_reference(db, item_index, nxt, "next"),
            "missing_nearby": {"prev_range": prev_range,
                               "next_range": next_range},
        }
        return respond(data, etag=etag_for("/pages/%d/neighbors" % item_index),
                       cache="public, max-age=3600")

    # ======================================================================
    # 10) /search
    # ======================================================================
    def _snippet_html(text, tokens):
        for t in tokens:
            if not t:
                continue
            segs = make_snippet(text, t)
            if any(mk for _s, mk in segs):
                parts = []
                for seg, marked in segs:
                    parts.append("<mark>%s</mark>" % html.escape(seg)
                                 if marked else html.escape(seg))
                return "".join(parts)
        return html.escape((text or "")[:220])

    @bp.get("/search")
    def search():
        db = get_db()
        q = request.args.get("q")
        if q is None or len(q) < 2 or len(q) > 64:
            raise ApiError(
                400, "INVALID_QUERY", "Invalid query",
                "q باید بین 2 تا 64 کاراکتر باشد",
                details={"param": "q"})
        tokens = tokenize_fa(q)
        if not tokens:
            raise ApiError(
                400, "INVALID_QUERY", "Invalid query",
                "هیچ توکن فارسی/عدد در query یافت نشد",
                details={"param": "q", "raw": q})
        vol_id = request.args.get("volume_id")
        sort = request.args.get("sort", "relevance")
        if sort not in ("relevance", "item_index"):
            raise ApiError(400, "INVALID_SORT", "Invalid sort",
                           "sort باید relevance یا item_index باشد",
                           details={"allowed": ["relevance", "item_index"]})
        limit, offset = parse_pagination(SEARCH_DEFAULT_LIMIT)
        match = build_fts_match(tokens)
        where = "f.tokens MATCH ?"
        params = [match]
        if vol_id:
            where += " AND p.volume_id=?"
            params.append(vol_id)
        estimated = len(tokens) >= 3
        if not estimated:
            total = db.execute(
                "SELECT COUNT(*) c FROM pages_fts f JOIN pages p"
                " ON p.page_id=f.page_id WHERE " + where,
                params).fetchone()["c"]
        else:
            total = -1
        if sort == "relevance":
            order = "ORDER BY bm25(pages_fts), p.item_index ASC"
        else:
            order = "ORDER BY p.item_index ASC, p.page_id ASC"
        rows = db.execute(
            "SELECT p.item_index, p.page_id, p.volume_id, p.status,"
            " p.text, h.heading_text FROM pages_fts f JOIN pages p"
            " ON p.page_id=f.page_id LEFT JOIN headings h"
            " ON h.page_id=p.page_id WHERE " + where + " " + order +
            " LIMIT ? OFFSET ?", params + [limit, offset]).fetchall()
        results = []
        for r in rows:
            vno = db.execute("SELECT volume_no FROM volumes WHERE volume_id=?",
                             (r["volume_id"],)).fetchone()
            amb = db.execute(
                "SELECT COUNT(DISTINCT volume_id) c FROM pages"
                " WHERE item_index=?", (r["item_index"],)).fetchone()["c"] > 1
            results.append({
                "item_index": r["item_index"],
                "page_id": r["page_id"],
                "volume_ref": {"volume_id": r["volume_id"],
                               "volume_no": vno["volume_no"] if vno else None,
                               "ambiguous": amb},
                "snippet": _snippet_html(r["text"], tokens),
                "heading": {"text": r["heading_text"]}
                if r["heading_text"] else None,
                "quality_status": r["status"],
            })
        data = {
            "query": {"raw": q, "tokens": tokens},
            "total": total,
            "results": results,
        }
        if estimated:
            data["estimated"] = True
        if total == 0 and not estimated:
            top = db.execute(
                "SELECT display_text FROM topics ORDER BY page_count DESC,"
                " display_text ASC LIMIT 3").fetchall()
            data["suggestions"] = [t["display_text"] for t in top]
        return respond(data, etag=etag_for("/search|%s|%s|%s|%s"
                                           % (q, vol_id, sort, offset),
                                           weak=True),
                       cache="no-store")

    # ======================================================================
    # 11) /statistics
    # ======================================================================
    @bp.get("/statistics")
    def statistics():
        db = get_db()
        pbc = db.execute(
            "SELECT record_class, COUNT(*) c FROM pages GROUP BY"
            " record_class ORDER BY record_class").fetchall()
        qs = db.execute("SELECT status, COUNT(*) c FROM pages GROUP BY"
                        " status ORDER BY status").fetchall()
        ii = db.execute(
            "SELECT COUNT(*) n_rows, COUNT(DISTINCT item_index) n_distinct,"
            " MIN(item_index) min_ii, MAX(item_index) max_ii FROM pages"
        ).fetchone()
        mr = db.execute(
            "SELECT missing_from, missing_to, missing_count FROM coverage"
            " WHERE scope='global' ORDER BY missing_from").fetchall()
        tl = json.loads(meta.get("text_length_stats") or "{}")
        topics = db.execute(
            "SELECT COUNT(*) d, SUM(CASE WHEN page_count>=2 THEN 1 ELSE 0"
            " END) m FROM topics").fetchone()
        data = {
            "pages_by_class": dict([tuple(x) for x in pbc]) | {
                "definition": "GROUP BY pages.record_class (زنده، read model)"},
            "quality_status": {r["status"]: r["c"] for r in qs} | {
                "definition": "GROUP BY pages.status (زنده، read model);"
                               " flags ممکن است بیشتر از status باشد (یک"
                               " صفحه هم short و هم dup باشد)"},
            "item_index": {
                "distinct": ii["n_distinct"],
                "rows": ii["n_rows"],
                "duplicates": ii["n_rows"] - ii["n_distinct"],
                "min": ii["min_ii"],
                "max": ii["max_ii"],
                "missing": {
                    "count": sum(r["missing_count"] for r in mr),
                    "ranges": [[r["missing_from"], r["missing_to"]]
                               for r in mr],
                    "definition": "item_indexهای بدون صفحه، از coverage"
                                  " (global) — با gaps manifest build شده",
                },
            },
            "text_length": {
                "p50": tl.get("p50"), "p90": tl.get("p90"),
                "p99": tl.get("p99"), "max": tl.get("max"),
                "definition": "histogram manifest (طول متن صفحات) — از"
                               " build_meta، تعریف مکتوب",
            },
            "topics": {
                "distinct_normalized": topics["d"],
                "multi_page": int(topics["m"] or 0),
                "definition": "normalize %s روی 100%% هدرها؛ stable id"
                               " t-+sha1[:12]" % TOPIC_NORM_VERSION,
            },
            "surah": {
                "status": "not_supported",
                "coverage": "0/114",
                "definition": "fact-check PCM-20.6.4: 0 هدر با پیشوند"
                               " سخت سوره؛ جدول surahs خالی",
            },
        }
        return respond(data, etag=etag_for("/statistics"),
                       cache="public, max-age=60, stale-while-revalidate=300")

    # ======================================================================
    # 12) /health
    # ======================================================================
    @bp.get("/health")
    def health():
        db = get_db()
        quick = "ok"
        try:
            db.execute("SELECT 1").fetchone()
        except sqlite3.Error:
            quick = "error"
        data = {
            "status": "ok" if quick == "ok" else "degraded",
            "readmodel": {"version": V, "content_sha256": C,
                          "db_sha256": DBSHA},
            "db_quick_check": quick,
            "uptime_s": round(state["clock"]() - state["started_at"], 1),
        }
        return respond(data)

    # ------------------------------------------------------------------
    # OpenAPI + offline docs
    # ------------------------------------------------------------------
    @bp.get("/openapi.json")
    def openapi_json():
        from tasnim.web.openapi import spec
        return jsonify(spec(V, C))

    @bp.get("/docs")
    def docs():
        from tasnim.web.openapi import DOCS_HTML
        return Response(DOCS_HTML, mimetype="text/html; charset=utf-8")

    return bp


# --------------------------------------------------------------------------
# app factory
# --------------------------------------------------------------------------


_WEB_DIR = os.path.dirname(os.path.abspath(__file__))


def _load_build_meta(readmodel_path):
    meta_path = os.path.join(os.path.dirname(os.path.abspath(readmodel_path)),
                             "build_meta.db")
    conn = sqlite3.connect("file:%s?mode=ro" % quote(meta_path, safe="/:"),
                           uri=True)
    try:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT key, value FROM build_meta").fetchall()
        meta = {r["key"]: r["value"] for r in rows}
    finally:
        conn.close()
    if "db_sha256" not in meta:
        raise RuntimeError("build_meta.db incomplete: %s" % meta_path)
    return meta


def create_app(readmodel_path, rate_search=30, rate_read=120,
               rate_db_path=None, clock=None, with_ssr=True):
    from flask import Flask
    state_clock = clock or time.time
    rm_dir = os.path.dirname(os.path.abspath(readmodel_path))
    state = {
        "readmodel_path": readmodel_path,
        "meta": _load_build_meta(readmodel_path),
        "covers_dir": os.path.join(rm_dir, "covers"),
        "started_at": state_clock(),
        "clock": state_clock,
        "rate": RateLimiter(rate_db_path, rate_search, rate_read, clock),
        "log": None,
    }
    if with_ssr:
        app = Flask("tasnim-web",
                    template_folder=os.path.join(_WEB_DIR, "templates"),
                    static_folder=os.path.join(_WEB_DIR, "static"))
    else:
        app = Flask("tasnim-web")
    app.json.ensure_ascii = False
    app.extensions["tasnim"] = state
    app.register_blueprint(make_blueprint(state),
                           url_prefix="/api/v1/tasnim")
    if with_ssr:
        from tasnim.web import pages, ssr
        app.register_blueprint(ssr.make_ssr_blueprint(state))

        @app.errorhandler(pages.SsrError)
        def _ssr_error(e):
            from flask import render_template
            return render_template("error.html", status=e.status,
                                   title=e.title, message=e.message,
                                   error=e), e.status

    @app.after_request
    def _font_types(resp):
        # deterministic font content types (mimetypes varies by platform);
        # only for successful serves, so 404s keep their error semantics.
        path = request.path
        if resp.status_code == 200 and path.startswith("/static/fonts/"):
            ct = resp.headers.get("Content-Type", "")
            if not ct.startswith("font/"):
                if path.endswith(".ttf"):
                    resp.headers["Content-Type"] = "font/ttf"
                elif path.endswith(".woff2"):
                    resp.headers["Content-Type"] = "font/woff2"
            # Override Werkzeug's default "no-cache": fonts are immutable per
            # build and must be cached client-side for one day (design §5).
            resp.headers["Cache-Control"] = "public, max-age=86400"
        return resp

    @app.errorhandler(ApiError)
    def _api_error(e):
        rid = getattr(g, "request_id", None) or "req_unknown"
        body = jsonify(e.to_dict(rid))
        body.status_code = e.status
        for k, v in e.headers.items():
            body.headers[k] = v
        return body

    @app.errorhandler(404)
    def _nf(e):
        rid = getattr(g, "request_id", None) or "req_unknown"
        if request.path.startswith("/api/"):
            err = ApiError(404, "NOT_FOUND", "Not found",
                           "مسیر «%s» پیدا نشد." % request.path,
                           details={"path": request.path})
            body = jsonify(err.to_dict(rid))
            body.status_code = 404
            return body
        from flask import render_template
        return render_template(
            "error.html", status=404, title="صفحه پیدا نشد",
            message="مسیری که درخواست دادید («%s») وجود ندارد."
                    % request.path,
            error=None), 404

    @app.errorhandler(405)
    def _na(e):
        rid = getattr(g, "request_id", None) or "req_unknown"
        err = ApiError(405, "METHOD_NOT_ALLOWED", "Method not allowed",
                       "روش %s برای «%s» مجاز نیست."
                       % (request.method, request.path),
                       details={"path": request.path,
                                "allowed": sorted(e.valid_methods)
                       if e.valid_methods else []})
        body = jsonify(err.to_dict(rid))
        body.status_code = 405
        return body

    @app.errorhandler(500)
    def _err500(e):
        rid = getattr(g, "request_id", None) or "req_unknown"
        if request.path.startswith("/api/"):
            err = ApiError(500, "INTERNAL", "Internal server error",
                           "خطای داخلی؛ request_id را به عملگر بدهید.",
                           details={})
            body = jsonify(err.to_dict(rid))
            body.status_code = 500
            return body
        from flask import render_template
        return render_template(
            "error.html", status=500, title="خطای داخلی",
            message="خطای داخلی پیش آمد؛ اگر ادامه یافت، request_id "
                    "(%s) را به عملگر بدهید." % rid,
            error=None), 500

    @app.teardown_appcontext
    def _teardown(exc):
        db = g.pop("tasnim_db", None)
        if db is not None:
            db.close()

    @app.teardown_appcontext
    def _teardown_rate(exc):
        # close on full app shutdown only (no requests in flight check needed:
        # Flask calls teardown per request; use explicit close from run())
        pass

    def shutdown():
        state["rate"].close()

    app.tasnim_shutdown = shutdown
    return app


def main(argv=None):
    import argparse
    p = argparse.ArgumentParser(prog="tasnim.web.app")
    p.add_argument("--db", required=True, help="tasnim_readmodel.db path")
    p.add_argument("--port", type=int, default=5071)
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--rate-db", default=None,
                   help="rate-limit sqlite path (default: beside read model)")
    args = p.parse_args(argv)
    rate_db = args.rate_db or os.path.join(
        os.path.dirname(os.path.abspath(args.db)), "tasnim_rate_limits.db")
    app = create_app(args.db, rate_db_path=rate_db)
    app.run(host=args.host, port=args.port, debug=False)


if __name__ == "__main__":
    main()

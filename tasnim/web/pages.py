# -*- coding: utf-8 -*-
"""Tasnim Web V1 — SSR page-model service layer (PCM-20.6.4, §6).

Binding rule: **templates never query SQLite.** Every route renders a
model dict built here (or by the API service layer). All queries are
LIMIT/OFFSET-bounded — no full-table loads per request.

HP-1 (architecture §5.6): metadata blocks pass through ``strict_pick``
(deny-by-default), the same guard as the API serializers. Heading
*text* is public per the API contract (page + search render
``heading.text``); only ``hctx:``/``hcctx:`` record *ids* may be shown
(metadata drawer) — never record content.

Digits: UI numbers are ASCII (``font-variant-numeric: tabular-nums``);
Persian digits appear only in fixed label strings and corpus text.
"""
import json
import math
import os
import re
import sqlite3
from urllib.parse import quote

from flask import g
from markupsafe import Markup

from tasnim.web.api import SURAH_PLANNED, SURAH_REASON, strict_pick
from tasnim.web.readmodel import (RAG_STATUS, build_fts_match,
                                  make_snippet, tokenize_fa)

# ---------------------------------------------------------------------------
# fixed labels (design system §7.5 — exact strings)
# ---------------------------------------------------------------------------

QUALITY_LABELS = {
    "ok": ("ok", "کامل"),
    "short": ("warning", "صفحهٔ کوتاه"),
    "empty": ("muted", "بدون متن (در دست بازیابی)"),
    "truncated_at_2000": ("danger", "متن در منبع قطع است (۲۰۰۰ نویسه)"),
}

TRUNCATED_BANNER = ("این صفحه در منبعِ اصلی حداکثر ۲۰۰۰ نویسه ثبت شده است؛"
                    " ادامهٔ متن موجود نیست.")

UNKNOWN_VOLUME_LABEL = "جلد نامشخص"
UNKNOWN_VOLUME_BADGE = "در حال بازیابی شمارهٔ جلد"
TOPIC_DISCLAIMER = "تأیید انسانی نشده — استخراج خودکار"

TOPICS_PER_PAGE = 25
VOLUME_PAGES_PER_PAGE = 50
VOLUME_HEADINGS_PER_PAGE = 25
HOMEPAGE_VOLUMES = 50
HOMEPAGE_LATEST = 8
HOMEPAGE_TOP_TOPICS = 6


class SsrError(Exception):
    """Renderable HTML error state (e.g. invalid search q) — 400, not 500."""

    def __init__(self, status, title, message):
        super().__init__(message)
        self.status = status
        self.title = title
        self.message = message


class Ssr404(SsrError):
    """Unknown volume_id / topic_id on an SSR route — styled 404 page."""

    def __init__(self, message):
        super().__init__(404, "مورد پیدا نشد", message)


# ---------------------------------------------------------------------------
# db access (shared with the API blueprint: same g-key, one connection)
# ---------------------------------------------------------------------------

def get_db(state):
    """Read-only connection on the app context (g-key 'tasnim_db', closed
    by the app teardown). Same key the API blueprint uses, so an SSR
    request that also hits /api reuses one connection."""
    if "tasnim_db" not in g:
        p = quote(os.path.abspath(state["readmodel_path"]), safe="/:")
        conn = sqlite3.connect("file:%s?mode=ro" % p, uri=True)
        conn.row_factory = sqlite3.Row
        g.tasnim_db = conn
    return g.tasnim_db


def _page_no(raw, default=1):
    try:
        p = int(raw)
    except (TypeError, ValueError):
        return default
    return p if p >= 1 else default


def _pager(base_path, page, total, per_page, extra=""):
    total_pages = max(1, int(math.ceil(total / float(per_page))))
    page = min(page, total_pages)
    def url(p):
        q = (extra + "&") if extra else ""
        return "%s?%sp=%%d" % (base_path, q) % p
    return {
        "page": page,
        "total": total,
        "total_pages": total_pages,
        "prev_url": url(page - 1) if page > 1 else None,
        "next_url": url(page + 1) if page < total_pages else None,
    }


def _volume_label(volume_no):
    return UNKNOWN_VOLUME_LABEL if volume_no is None else "جلد %d" % volume_no


# ---------------------------------------------------------------------------
# gap-aware navigation (mirrors api.py §5.2-8 semantics exactly)
# ---------------------------------------------------------------------------

def _missing_range_for(db, ii):
    r = db.execute(
        "SELECT missing_from, missing_to FROM coverage WHERE"
        " scope='global' AND missing_from<=? AND ?<=missing_to LIMIT 1",
        (ii, ii)).fetchone()
    return [r["missing_from"], r["missing_to"]] if r else None


def _nearest(db, ii, direction):
    """Nearest PRESENT page (dup_rank=0 anchor) on the given side."""
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


def _nav_ref(db, ii, neighbor, direction):
    """Gap-aware nav model for the templates.

    ``gap`` is present when the neighbour is not adjacent: the real
    missing count between the two pages plus the (lo, hi) span of the
    absent item_indexes. Numbering is never collapsed.
    """
    if neighbor is None:
        return {"exists": False, "item_index": None, "gap": None,
                "reason": "beginning_of_corpus" if direction == "prev"
                          else "end_of_corpus"}
    nn = neighbor[0]
    gap = nn - ii if direction == "next" else ii - nn
    g = None
    if gap > 1:
        lo = ii + 1 if direction == "next" else nn + 1
        hi = nn - 1 if direction == "next" else ii - 1
        g = {"lo": lo, "hi": hi, "count": hi - lo + 1}
    return {"exists": True, "item_index": nn, "gap": g, "reason": None}


# ---------------------------------------------------------------------------
# quality
# ---------------------------------------------------------------------------

def _quality(row, dup_rank):
    status = row["status"]
    if status == "dup_item_index":
        cls, label = "warning", "تکرار شماره (نسخهٔ %d)" % dup_rank
    else:
        cls, label = QUALITY_LABELS.get(status, ("muted", status))
    flags = []
    if row["flag_short"]:
        flags.append(("warning", "صفحهٔ کوتاه"))
    if row["flag_empty"]:
        flags.append(("muted", "بدون متن (در دست بازیابی)"))
    if row["flag_truncated_2000"]:
        flags.append(("danger", "متن در منبع قطع است (۲۰۰۰ نویسه)"))
    if status == "dup_item_index":
        flags.append(("warning", "تکرار شماره (نسخهٔ %d)" % dup_rank))
    return {
        "status": status,
        "cls": cls,
        "label": label,
        "flags": flags,
        "truncated_at_source": bool(row["flag_truncated_2000"]),
    }


# ---------------------------------------------------------------------------
# cover plates (builder-written SVG file, deterministic fallback)
# ---------------------------------------------------------------------------

def cover_svg(state, volume_id, volume_no, work_name, edition_name):
    """Return the inline SVG text for a volume cover plate.

    The builder writes ``<readmodel_dir>/covers/<volume_id>.svg``; we read
    it verbatim (it is our own deterministic output — safe to inline).
    Missing file (or unsafe id) falls back to the generator.
    """
    from tasnim.web.cover import generate_cover
    if volume_id and re.fullmatch(r"[A-Za-z0-9_\-]+", volume_id):
        path = os.path.join(state["covers_dir"], volume_id + ".svg")
        try:
            with open(path, "r", encoding="utf-8") as f:
                # Markup: our own deterministic SVG, must render inline
                # (Jinja autoescape would otherwise show it as text).
                return Markup(f.read())
        except OSError:
            pass
    return Markup(generate_cover(volume_id, volume_no,
                                 work_name or "", edition_name or ""))


# ---------------------------------------------------------------------------
# site context (context processor)
# ---------------------------------------------------------------------------

def site_context(db, state):
    w = db.execute("SELECT work_id, work_name FROM works LIMIT 1").fetchone()
    e = db.execute("SELECT edition_id, edition_name FROM editions LIMIT 1"
                   ).fetchone()
    meta = state["meta"]
    return {
        "work_id": w["work_id"] if w else None,
        "work_name": w["work_name"] if w else "پیکرهٔ تسنیم",
        "edition_id": e["edition_id"] if e else None,
        "edition_name": e["edition_name"] if e else None,
        "corpus_version": meta.get("corpus_version", "unknown"),
        "rag_status": RAG_STATUS,
    }


# ---------------------------------------------------------------------------
# models
# ---------------------------------------------------------------------------

def home_model(db, state):
    w = db.execute("SELECT work_id, work_name FROM works LIMIT 1").fetchone()
    e = db.execute("SELECT edition_id, edition_name FROM editions LIMIT 1"
                   ).fetchone()
    pages_n = db.execute("SELECT COUNT(*) c FROM pages").fetchone()["c"]
    vols_n = db.execute("SELECT COUNT(*) c FROM volumes").fetchone()["c"]
    topics_n = db.execute("SELECT COUNT(*) c FROM topics").fetchone()["c"]
    heads_n = db.execute("SELECT COUNT(*) c FROM headings").fetchone()["c"]
    missing = db.execute(
        "SELECT COALESCE(SUM(missing_count),0) c FROM coverage"
        " WHERE scope='global'").fetchone()["c"]
    top_topics = db.execute(
        "SELECT topic_id, display_text, page_count, volume_count"
        " FROM topics ORDER BY page_count DESC, topic_id ASC"
        " LIMIT %d" % HOMEPAGE_TOP_TOPICS).fetchall()
    vol_rows = db.execute(
        "SELECT * FROM volumes ORDER BY (volume_no IS NULL), volume_no"
        " ASC, volume_id ASC LIMIT %d" % HOMEPAGE_VOLUMES).fetchall()
    volumes = _volume_cards(db, state, vol_rows,
                            w["work_name"] if w else "",
                            e["edition_name"] if e else "")
    latest = db.execute(
        "SELECT p.item_index, p.page_id, p.volume_id, p.status,"
        " v.volume_no FROM pages p LEFT JOIN volumes v"
        " ON v.volume_id=p.volume_id WHERE p.dup_rank=0"
        " ORDER BY p.item_index DESC LIMIT %d" % HOMEPAGE_LATEST).fetchall()
    meta = state["meta"]
    return {
        "work": {"work_id": w["work_id"], "name": w["work_name"]} if w else {},
        "edition": ({"edition_id": e["edition_id"],
                     "name": e["edition_name"]} if e else {}),
        "counts": {
            "pages": pages_n,
            "volumes": vols_n,
            "topics": topics_n,
            "headings": heads_n,
            "missing_item_index": missing,
            "present_ratio": round(pages_n / (pages_n + missing), 4)
            if (pages_n + missing) else None,
            "present_ratio_definition":
                "pages/(pages+missing_item_index) — شمارنده‌های زندهٔ "
                "read model",
        },
        "top_topics": [dict(t) for t in top_topics],
        "volumes": volumes,
        "latest_pages": [
            {"item_index": r["item_index"],
             "volume_label": _volume_label(r["volume_no"]),
             "quality": QUALITY_LABELS.get(r["status"],
                                           ("muted", r["status"]))[1]}
            for r in latest],
        "meta": {
            "corpus_version": meta.get("corpus_version"),
            "content_sha256": meta.get("content_sha256"),
            "db_sha256": meta.get("db_sha256"),
            "built_at": meta.get("built_at"),
        },
    }


def _volume_cards(db, state, rows, work_name, edition_name):
    items = []
    for r in rows:
        cov = db.execute(
            "SELECT missing_from, missing_to, missing_count, status"
            " FROM coverage WHERE scope=? ORDER BY missing_from",
            (r["volume_id"],)).fetchall()
        ov = r["overlap_note"]
        items.append({
            "volume_id": r["volume_id"],
            "volume_no": r["volume_no"],
            "label": _volume_label(r["volume_no"]),
            "unknown": r["volume_no"] is None,
            "title": r["volume_title"],
            "page_count": r["page_count"],
            "ii_min": r["item_index_min"],
            "ii_max": r["item_index_max"],
            "missing_count": sum(c["missing_count"] for c in cov),
            "missing_ranges": [[c["missing_from"], c["missing_to"]]
                               for c in cov],
            "ambiguity_flag": bool(r["ambiguity_flag"]),
            "overlap_note": json.loads(ov) if ov else None,
            "cover_svg": cover_svg(state, r["volume_id"], r["volume_no"],
                                   work_name, edition_name),
        })
    return items


def volumes_model(db, state, sort="volume_no"):
    w = db.execute("SELECT work_name FROM works LIMIT 1").fetchone()
    e = db.execute("SELECT edition_name FROM editions LIMIT 1").fetchone()
    work_name = w["work_name"] if w else ""
    edition_name = e["edition_name"] if e else ""
    if sort == "page_count":
        order = "ORDER BY page_count DESC, volume_id ASC"
    else:
        order = "ORDER BY (volume_no IS NULL), volume_no ASC, volume_id ASC"
    rows = db.execute(
        "SELECT * FROM volumes %s LIMIT %d" % (order, 200)).fetchall()
    items = _volume_cards(db, state, rows, work_name, edition_name)
    return {"items": items, "total": len(items),
            "work_name": work_name, "edition_name": edition_name}


def volume_detail_model(db, state, volume_id, page=1):
    r = db.execute("SELECT * FROM volumes WHERE volume_id=? LIMIT 1",
                   (volume_id,)).fetchone()
    if r is None:
        return None
    w = db.execute("SELECT work_name FROM works LIMIT 1").fetchone()
    e = db.execute("SELECT edition_name FROM editions LIMIT 1").fetchone()
    work_name = w["work_name"] if w else ""
    edition_name = e["edition_name"] if e else ""
    mr = db.execute(
        "SELECT missing_from, missing_to, missing_count, status, note"
        " FROM coverage WHERE scope=? ORDER BY missing_from",
        (volume_id,)).fetchall()
    top_headings = db.execute(
        "SELECT heading_text AS text, COUNT(*) c FROM headings"
        " WHERE volume_id=? GROUP BY heading_text"
        " ORDER BY c DESC, heading_text ASC LIMIT 10",
        (volume_id,)).fetchall()
    top_topics = db.execute(
        "SELECT t.topic_id, t.display_text, COUNT(*) c FROM headings h"
        " JOIN topics t ON t.topic_id=h.topic_id WHERE h.volume_id=?"
        " AND h.topic_id IS NOT NULL GROUP BY t.topic_id"
        " ORDER BY c DESC, t.display_text ASC LIMIT 8",
        (volume_id,)).fetchall()
    first = db.execute(
        "SELECT page_id, item_index, status FROM pages WHERE volume_id=?"
        " ORDER BY item_index ASC, page_id ASC LIMIT 1",
        (volume_id,)).fetchone()
    last = db.execute(
        "SELECT page_id, item_index, status FROM pages WHERE volume_id=?"
        " ORDER BY item_index DESC, page_id DESC LIMIT 1",
        (volume_id,)).fetchone()
    # headings (paginated)
    h_total = db.execute(
        "SELECT COUNT(*) c FROM headings WHERE volume_id=?",
        (volume_id,)).fetchone()["c"]
    h_page = _page_no(page)
    h_rows = db.execute(
        "SELECT record_id, heading_text, item_index, page_id FROM headings"
        " WHERE volume_id=? ORDER BY item_index ASC, record_id ASC"
        " LIMIT ? OFFSET ?",
        (volume_id, VOLUME_HEADINGS_PER_PAGE,
         (h_page - 1) * VOLUME_HEADINGS_PER_PAGE)).fetchall()
    h_pager = _pager("/volumes/%s" % volume_id, h_page, h_total,
                     VOLUME_HEADINGS_PER_PAGE, "view=headings")
    # page index (paginated, gap-aware between consecutive rows)
    p_total = r["page_count"] or db.execute(
        "SELECT COUNT(*) c FROM pages WHERE volume_id=?",
        (volume_id,)).fetchone()["c"]
    p_page = _page_no(page)
    p_rows = db.execute(
        "SELECT page_id, item_index, status, barg FROM pages"
        " WHERE volume_id=? ORDER BY item_index ASC, page_id ASC"
        " LIMIT ? OFFSET ?",
        (volume_id, VOLUME_PAGES_PER_PAGE,
         (p_page - 1) * VOLUME_PAGES_PER_PAGE)).fetchall()
    prev_ii = r["item_index_min"] - 1 if r["item_index_min"] is not None \
        else None
    items = []
    for row in p_rows:
        if prev_ii is not None and row["item_index"] - prev_ii > 1:
            lo, hi = prev_ii + 1, row["item_index"] - 1
            items.append({"gap": {"lo": lo, "hi": hi,
                                  "count": hi - lo + 1}})
        items.append({
            "item_index": row["item_index"],
            "page_id": row["page_id"],
            "status": row["status"],
            "barg": row["barg"],
            "quality": QUALITY_LABELS.get(row["status"],
                                          ("muted", row["status"]))[1],
        })
        prev_ii = row["item_index"]
        nxt = row["item_index"]
    p_pager = _pager("/volumes/%s" % volume_id, p_page, p_total,
                     VOLUME_PAGES_PER_PAGE)
    # trailing gap (only on the last page of the index)
    if p_pager["page"] == p_pager["total_pages"] and r["item_index_max"] \
            is not None and p_rows and nxt < r["item_index_max"]:
        lo, hi = nxt + 1, r["item_index_max"]
        items.append({"gap": {"lo": lo, "hi": hi, "count": hi - lo + 1}})
    ov = r["overlap_note"]
    return {
        "volume_id": volume_id,
        "volume_no": r["volume_no"],
        "label": _volume_label(r["volume_no"]),
        "unknown": r["volume_no"] is None,
        "title": r["volume_title"],
        "strategy": r["volume_strategy"],
        "page_count": r["page_count"],
        "ii_min": r["item_index_min"],
        "ii_max": r["item_index_max"],
        "work_name": work_name,
        "edition_name": edition_name,
        "cover_svg": cover_svg(state, volume_id, r["volume_no"],
                               work_name, edition_name),
        "ambiguity_flag": bool(r["ambiguity_flag"]),
        "overlap_note": json.loads(ov) if ov else None,
        "missing_ranges": [
            {"lo": c["missing_from"], "hi": c["missing_to"],
             "count": c["missing_count"], "status": c["status"],
             "note": c["note"]} for c in mr],
        "missing_count": sum(c["missing_count"] for c in mr),
        "top_headings": [dict(t) for t in top_headings],
        "top_topics": [dict(t) for t in top_topics],
        "first_page": ({"item_index": first["item_index"],
                        "status": first["status"]} if first else None),
        "last_page": ({"item_index": last["item_index"],
                       "status": last["status"]} if last else None),
        "headings": {
            "items": [dict(h) for h in h_rows],
            "pager": h_pager,
        },
        "page_index": {
            "items": items,
            "pager": p_pager,
        },
    }


def page_model(db, state, item_index, dup_rank=0):
    row = db.execute(
        "SELECT * FROM pages WHERE item_index=? AND dup_rank=? LIMIT 1",
        (item_index, dup_rank)).fetchone()
    if row is None:
        # Honest recovery state (HTTP 200), not 404/500.
        return {
            "missing": True,
            "item_index": item_index,
            "range": _missing_range_for(db, item_index),
            "prev": _nav_ref(db, item_index, _nearest(db, item_index, "prev"),
                             "prev"),
            "next": _nav_ref(db, item_index, _nearest(db, item_index, "next"),
                             "next"),
        }
    vol = db.execute("SELECT * FROM volumes WHERE volume_id=? LIMIT 1",
                     (row["volume_id"],)).fetchone()
    vols_here = db.execute(
        "SELECT COUNT(DISTINCT volume_id) c FROM pages WHERE item_index=?"
        , (item_index,)).fetchone()["c"]
    ambiguous = vols_here > 1
    heading = None
    if row["heading_record_id"]:
        h = db.execute(
            "SELECT record_id, heading_text, topic_id FROM headings"
            " WHERE record_id=? LIMIT 1",
            (row["heading_record_id"],)).fetchone()
        if h:
            heading = {"record_id": h["record_id"],
                       "text": h["heading_text"],
                       "topic_id": h["topic_id"]}
    quality = _quality(row, dup_rank)
    dups = []
    for d in db.execute(
            "SELECT p.dup_rank, p.page_id, p.volume_id, v.volume_no"
            " FROM pages p LEFT JOIN volumes v ON v.volume_id=p.volume_id"
            " WHERE p.item_index=? AND p.page_id<>?"
            " ORDER BY p.dup_rank, p.page_id LIMIT 10",
            (item_index, row["page_id"])):
        dups.append({
            "dup_rank": d["dup_rank"],
            "page_id": d["page_id"],
            "volume_id": d["volume_id"],
            "volume_label": _volume_label(d["volume_no"]),
        })
    # related topics: the heading's topic + the volume's top topics
    related = []
    if heading and heading["topic_id"]:
        t = db.execute(
            "SELECT topic_id, display_text, page_count FROM topics"
            " WHERE topic_id=? LIMIT 1", (heading["topic_id"],)).fetchone()
        if t:
            related.append({"topic_id": t["topic_id"],
                            "display_text": t["display_text"],
                            "page_count": t["page_count"],
                            "via": "heading"})
    seen = {x["topic_id"] for x in related}
    for t in db.execute(
            "SELECT t.topic_id, t.display_text, t.page_count,"
            " COUNT(*) c FROM headings h"
            " JOIN topics t ON t.topic_id=h.topic_id"
            " WHERE h.volume_id=? AND h.topic_id IS NOT NULL"
            " GROUP BY t.topic_id ORDER BY c DESC, t.display_text ASC"
            " LIMIT 5", (row["volume_id"],)):
        if t["topic_id"] not in seen:
            related.append({"topic_id": t["topic_id"],
                            "display_text": t["display_text"],
                            "page_count": t["page_count"],
                            "via": "volume"})
    seq = row["seq_in_volume"]
    vol_pages = vol["page_count"] if vol else None
    metadata = strict_pick({
        "page_id": row["page_id"],
        "content_sha256": row["content_sha256"],
        "captured_at": row["captured_at"],
        "source_page_id": row["source_page_id"],
        "section": row["section"],
        "source_url": row["url"],
        "heading_record_id": row["heading_record_id"],
    }, {"page_id", "content_sha256", "captured_at", "source_page_id",
        "section", "source_url", "heading_record_id"}, "metadata")
    return {
        "missing": False,
        "page_id": row["page_id"],
        "item_index": item_index,
        "dup_rank": dup_rank,
        "barg": row["barg"],
        "text": row["text"],
        "char_count": row["char_count"],
        "record_class": row["record_class"],
        "volume": {
            "volume_id": vol["volume_id"] if vol else row["volume_id"],
            "volume_no": vol["volume_no"] if vol else None,
            "title": vol["volume_title"] if vol else None,
            "label": _volume_label(vol["volume_no"]) if vol else "—",
            "unknown": vol["volume_no"] is None if vol else False,
            "attribution": "ambiguous" if ambiguous else "recorded",
            "ambiguous": ambiguous,
        },
        "heading": heading,
        "quality": quality,
        "truncated_banner": bool(row["flag_truncated_2000"]),
        "duplicates": dups,
        "related_topics": related,
        "metadata": metadata,
        "prev": _nav_ref(db, item_index, _nearest(db, item_index, "prev"),
                         "prev"),
        "next": _nav_ref(db, item_index, _nearest(db, item_index, "next"),
                         "next"),
        "in_volume": ({"seq": seq, "total": vol_pages}
                      if seq is not None and vol_pages else None),
        "rag_status": RAG_STATUS,
    }


def topics_model(db, q=None, sort="page_count", page=1):
    q = (q or "").strip()
    where, params = [], []
    if q:
        like = "%" + q.replace("\\", "\\\\").replace("%", "\\%") \
            .replace("_", "\\_") + "%"
        where.append("display_text LIKE ? ESCAPE '\\'")
        params.append(like)
    order = ("ORDER BY page_count DESC, topic_id ASC"
             if sort == "page_count" else
             "ORDER BY display_text ASC, topic_id ASC")
    where_sql = (" WHERE " + " AND ".join(where)) if where else ""
    total = db.execute(
        "SELECT COUNT(*) c FROM topics" + where_sql, params).fetchone()["c"]
    p = _page_no(page)
    rows = db.execute(
        "SELECT topic_id, display_text, page_count, volume_count,"
        " first_item_index FROM topics" + where_sql + " " + order +
        " LIMIT ? OFFSET ?",
        params + [TOPICS_PER_PAGE, (p - 1) * TOPICS_PER_PAGE]).fetchall()
    return {
        "q": q,
        "sort": sort,
        "items": [dict(t) for t in rows],
        "pager": _pager("/topics", p, total, TOPICS_PER_PAGE,
                        ("q=%s&sort=%s" % (q, sort)) if q else
                        ("sort=%s" % sort) if sort != "page_count" else ""),
        "total": total,
    }


def topic_detail_model(db, topic_id, page=1):
    r = db.execute("SELECT * FROM topics WHERE topic_id=? LIMIT 1",
                   (topic_id,)).fetchone()
    if r is None:
        return None
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
            " WHERE normalized_text=? LIMIT 1", (pr["norm"],)).fetchone()
        if pt:
            parent = {"topic_id": pt["topic_id"],
                      "display_text": pt["display_text"],
                      "count": pr["c"]}
    total = db.execute(
        "SELECT COUNT(*) c FROM headings WHERE topic_id=?",
        (topic_id,)).fetchone()["c"]
    p = _page_no(page)
    rows = db.execute(
        "SELECT p.item_index, p.page_id, p.volume_id, v.volume_no,"
        " h.heading_text, h.record_id,"
        " (p.heading_record_id = h.record_id) is_heading_page"
        " FROM headings h JOIN pages p ON p.page_id=h.page_id"
        " LEFT JOIN volumes v ON v.volume_id=p.volume_id"
        " WHERE h.topic_id=?"
        " ORDER BY p.item_index ASC, p.page_id ASC LIMIT ? OFFSET ?",
        (topic_id, TOPICS_PER_PAGE, (p - 1) * TOPICS_PER_PAGE)).fetchall()
    occ = [{
        "item_index": o["item_index"],
        "page_id": o["page_id"],
        "volume_id": o["volume_id"],
        "volume_label": _volume_label(o["volume_no"]),
        "heading_text": o["heading_text"],
        "is_heading_page": bool(o["is_heading_page"]),
    } for o in rows]
    return {
        "topic_id": r["topic_id"],
        "display_text": r["display_text"],
        "normalized_text": r["normalized_text"],
        "page_count": r["page_count"],
        "volume_count": r["volume_count"],
        "first_item_index": r["first_item_index"],
        "disclaimer": TOPIC_DISCLAIMER,
        "parent_topic": parent,
        "occurrences_total": total,
        "occurrences": occ,
        "pager": _pager("/topics/%s" % topic_id, p, total, TOPICS_PER_PAGE),
    }


def surahs_model():
    """Honest state — no surah data is fabricated (mission rule)."""
    return {
        "status": "not_supported",
        "banner": "در حال تکمیل",
        "coverage": "0/114",
        "reason": SURAH_REASON,
        "planned": SURAH_PLANNED,
        "evidence": [
            "0 فیلد surah در schema پیکره",
            "0 هدر با پیشوند سخت «تفسیر سوره/سوره/سورة» از 10,739 هدر",
            "0 صفحهٔ تعلق‌داده‌شده به سوره",
            "265 هدرِ شلِ حاوی «سوره» همه sub-heading عمومی‌اند",
        ],
    }


def search_model(db, q):
    """SSR search over the same FTS5 index as the API.

    Returns the model dict; raises SsrError(400) on an invalid query
    (empty / too short / too long / no tokens) — never 500.
    """
    if q is None or len(q) < 2 or len(q) > 64:
        raise SsrError(
            400, "جستجو نامعتبر",
            "q باید بین ۲ تا ۶۴ کاراکتر باشد. عبارت جستجو را بررسی کنید.")
    tokens = tokenize_fa(q)
    if not tokens:
        raise SsrError(
            400, "جستجو نامعتبر",
            "هیچ توکن فارسی/عدد در query یافت نشد؛ حداقل یک کلمهٔ فارسی "
            "بنویسید.")
    match = build_fts_match(tokens)
    estimated = len(tokens) >= 3
    if not estimated:
        total = db.execute(
            "SELECT COUNT(*) c FROM pages_fts f JOIN pages p"
            " ON p.page_id=f.page_id WHERE f.tokens MATCH ?",
            (match,)).fetchone()["c"]
    else:
        total = -1
    rows = db.execute(
        "SELECT p.item_index, p.page_id, p.volume_id, p.status,"
        " p.text, h.heading_text FROM pages_fts f JOIN pages p"
        " ON p.page_id=f.page_id LEFT JOIN headings h"
        " ON h.page_id=p.page_id WHERE f.tokens MATCH ?"
        " ORDER BY bm25(pages_fts), p.item_index ASC LIMIT 20",
        (match,)).fetchall()
    results = []
    for r in rows:
        vno = db.execute(
            "SELECT volume_no FROM volumes WHERE volume_id=? LIMIT 1",
            (r["volume_id"],)).fetchone()
        amb = db.execute(
            "SELECT COUNT(DISTINCT volume_id) c FROM pages"
            " WHERE item_index=?", (r["item_index"],)).fetchone()["c"] > 1
        snippet = []
        for t in tokens:
            if not t:
                continue
            segs = make_snippet(r["text"], t)
            if any(mk for _s, mk in segs):
                snippet = [(s, bool(m)) for s, m in segs]
                break
        if not snippet:
            snippet = [((r["text"] or "")[:220], False)]
        results.append({
            "item_index": r["item_index"],
            "page_id": r["page_id"],
            "volume_label": _volume_label(
                vno["volume_no"] if vno else None),
            "ambiguous": amb,
            "snippet": snippet,
            "heading": r["heading_text"],
            "quality": QUALITY_LABELS.get(r["status"],
                                          ("muted", r["status"]))[1],
        })
    suggestions = []
    if total == 0 and not estimated:
        suggestions = [t["display_text"] for t in db.execute(
            "SELECT display_text FROM topics ORDER BY page_count DESC,"
            " display_text ASC LIMIT 3")]
    return {
        "q": q,
        "tokens": tokens,
        "total": total,
        "estimated": estimated,
        "results": results,
        "suggestions": suggestions,
    }


def about_model(db, state):
    meta = state["meta"]
    w = db.execute("SELECT * FROM works LIMIT 1").fetchone()
    e = db.execute("SELECT * FROM editions LIMIT 1").fetchone()
    counts = {}
    for table in ("pages", "volumes", "topics", "headings"):
        counts[table] = db.execute(
            "SELECT COUNT(*) c FROM " + table).fetchone()["c"]
    missing = db.execute(
        "SELECT COALESCE(SUM(missing_count),0) c FROM coverage"
        " WHERE scope='global'").fetchone()["c"]
    quality = {r["status"]: r["c"] for r in db.execute(
        "SELECT status, COUNT(*) c FROM pages GROUP BY status")}
    backfill = [
        {"lo": c["missing_from"], "hi": c["missing_to"],
         "count": c["missing_count"], "status": c["status"],
         "note": c["note"]}
        for c in db.execute(
            "SELECT missing_from, missing_to, missing_count, status, note"
            " FROM coverage WHERE scope='global' ORDER BY missing_from"
            " LIMIT 50")]
    try:
        tlen = json.loads(meta.get("text_length_stats") or "{}")
    except ValueError:
        tlen = {}
    return {
        "meta": {
            "corpus_version": meta.get("corpus_version"),
            "content_sha256": meta.get("content_sha256"),
            "db_sha256": meta.get("db_sha256"),
            "built_at": meta.get("built_at"),
            "schema_version": meta.get("schema_version"),
            "topic_norm_version": meta.get("topic_norm_version"),
            "tokenizer_version": meta.get("tokenizer_version"),
            "rag_status": meta.get("rag_status"),
            "surah_status": meta.get("surah_status"),
            "fts_note": meta.get("fts_note"),
            "text_length_stats": tlen,
        },
        "work": dict(w) if w else {},
        "edition": dict(e) if e else {},
        "counts": dict(counts, missing_item_index=missing),
        "quality": quality,
        "backfill_ranges": backfill,
    }

"""
Thesaurus Crawler Backend
Flask API + SQLite - Crawl queue manager & data store
"""

import sqlite3, json, hashlib, time, os, re
from datetime import datetime, timezone
from flask import Flask, request, jsonify, g, send_from_directory, redirect, abort
from werkzeug.middleware.proxy_fix import ProxyFix
from flask_cors import CORS

STATIC_DIR = os.environ.get('STATIC_DIR') or os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..', 'dashboard')
)
app = Flask(__name__, static_folder=STATIC_DIR, static_url_path='/dashboard')
# Production runs behind nginx (X-Forwarded-*); trust one proxy hop so
# request.is_secure / remote_addr are correct for cookie + rate limiting.
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
CORS(app)

DB_PATH = os.environ.get('PCT_DB') or os.path.join(os.path.dirname(__file__), 'thesaurus.db')

_PERSIAN_DIGIT_TRANS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def to_ascii_digits(s):
    return (s or "").translate(_PERSIAN_DIGIT_TRANS)


def normalize_jalali_date(s):
    """Normalize ۱۴۰۴/۰۱/۰۱ or 1404/01/01 → 1404/01/01; return '' if invalid."""
    ascii_s = to_ascii_digits(s).strip()
    m = re.search(r'(\d{4}/\d{2}/\d{2})', ascii_s)
    return m.group(1) if m else ''


def jalali_year(date_str):
    d = normalize_jalali_date(date_str)
    return d[:4] if d else ''


@app.route('/')
def root():
    return redirect('/dashboard/')


@app.route('/dashboard')
@app.route('/dashboard/')
def dashboard_index():
    # PCM-09: the page itself is public; all project data lives behind
    # /api/auth/* + /api/dashboard/* (401 without a session cookie).
    # The UI shows the login overlay client-side when auth is enabled.
    return send_from_directory(app.static_folder, 'index.html')


# ═══════════════════════════════════════
# DATABASE
# ═══════════════════════════════════════

def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DB_PATH)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA foreign_keys=ON")
    return db


def init_db():
    db = sqlite3.connect(DB_PATH)
    db.executescript("""
    CREATE TABLE IF NOT EXISTS crawl_queue (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        url         TEXT NOT NULL UNIQUE,
        page_type   TEXT NOT NULL DEFAULT 'term',
        science_id  TEXT,
        category_id TEXT,
        title       TEXT,
        status      TEXT NOT NULL DEFAULT 'pending',
        priority    INTEGER DEFAULT 0,
        depth       INTEGER DEFAULT 0,
        content_hash TEXT,
        created_at  TEXT DEFAULT (datetime('now')),
        started_at  TEXT,
        finished_at TEXT,
        error_msg   TEXT,
        retry_count INTEGER DEFAULT 0,
        source_page TEXT,
        page_num    INTEGER,
        site        TEXT DEFAULT 'thesaurus',
        payload     TEXT,
        list_only   INTEGER DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS crawled_data (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        url         TEXT NOT NULL UNIQUE,
        item_id     TEXT,
        item_type   TEXT,
        title       TEXT,
        title_en    TEXT,
        full_data   TEXT,
        content_hash TEXT NOT NULL,
        science_field TEXT,
        category_tree TEXT,
        parent_id   TEXT,
        definitions TEXT,
        related_terms TEXT,
        source_text  TEXT,
        crawled_at  TEXT DEFAULT (datetime('now')),
        version     INTEGER DEFAULT 1
    );

    CREATE TABLE IF NOT EXISTS crawl_progress (
        key         TEXT PRIMARY KEY,
        value       TEXT,
        updated_at  TEXT DEFAULT (datetime('now'))
    );

    CREATE INDEX IF NOT EXISTS idx_queue_status ON crawl_queue(status, priority);
    CREATE INDEX IF NOT EXISTS idx_queue_url ON crawl_queue(url);
    CREATE INDEX IF NOT EXISTS idx_crawled_url ON crawled_data(url);
    CREATE INDEX IF NOT EXISTS idx_crawled_hash ON crawled_data(content_hash);
    CREATE INDEX IF NOT EXISTS idx_crawled_type ON crawled_data(item_type);
    """)
    db.commit()
    # Migrations for older DBs
    cols = {r[1] for r in db.execute("PRAGMA table_info(crawl_queue)").fetchall()}
    for col, typedef in [
        ('site', "TEXT DEFAULT 'thesaurus'"),
        ('payload', 'TEXT'),
        ('list_only', 'INTEGER DEFAULT 0'),
        ('item_id', 'TEXT'),
    ]:
        if col not in cols:
            try:
                db.execute(f"ALTER TABLE crawl_queue ADD COLUMN {col} {typedef}")
            except Exception:
                pass
    db.commit()
    # Create site index after migration
    try:
        db.execute("CREATE INDEX IF NOT EXISTS idx_queue_site_status ON crawl_queue(site, status)")
    except Exception:
        pass
    from sites import ensure_sites_schema, seed_default_sites
    from projects import ensure_projects_schema
    from dashboard_api import ensure_dashboard_schema
    ensure_sites_schema(db)
    seed_default_sites(db)
    ensure_projects_schema(db)
    ensure_dashboard_schema(db)
    _init_auth(db)
    db.close()


@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()


# ═══════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════

def content_hash(data):
    if isinstance(data, dict) or isinstance(data, list):
        data = json.dumps(data, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(data.encode()).hexdigest()


import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sciences import THESAURUS_SCIENCES, THESAURUS_SCIENCE_IDS, THESAURUS_MAIN_TYPES


# ═══════════════════════════════════════
# TWO-PHASE PIPELINE
# Phase 1: list discovery → crawl_queue (deduped, no crawled_data)
# Phase 2: full save → crawled_data / khamenei_speeches
# ═══════════════════════════════════════

@app.route('/api/phase1/seed-batch', methods=['POST'])
def phase1_seed_batch():
    """
    Insert discovered list items into crawl_queue.
    Duplicates (same url) are skipped — never re-listed.
    Body: { site, items: [{url, item_id, title, page_type, science_id, source_page, payload?}] }
    """
    db = get_db()
    data = request.get_json(silent=True) or {}
    site = data.get('site') or 'thesaurus'
    items = data.get('items') or []
    added, duplicates = 0, 0

    for item in items:
        url = (item.get('url') or '').strip()
        if not url:
            continue
        existing = db.execute("SELECT id, status FROM crawl_queue WHERE url=?", (url,)).fetchone()
        if existing:
            duplicates += 1
            continue
        payload = item.get('payload')
        if payload is not None and not isinstance(payload, str):
            payload = json.dumps(payload, ensure_ascii=False)
        db.execute(
            """INSERT INTO crawl_queue
               (url, page_type, science_id, title, status, priority, source_page, site, payload, list_only, item_id)
               VALUES (?, ?, ?, ?, 'pending', ?, ?, ?, ?, 1, ?)""",
            (
                url,
                item.get('page_type') or item.get('item_type') or 'term',
                item.get('science_id') or '',
                item.get('title') or '',
                int(item.get('priority') or 5),
                item.get('source_page') or '',
                site,
                payload,
                item.get('item_id') or '',
            )
        )
        added += 1

    # cursor progress optional
    cursor = data.get('cursor') or {}
    if cursor.get('key'):
        db.execute(
            """INSERT INTO crawl_progress (key, value, updated_at) VALUES (?, ?, datetime('now'))
               ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=datetime('now')""",
            (cursor['key'], json.dumps(cursor, ensure_ascii=False))
        )

    db.commit()
    return jsonify({
        "added": added,
        "duplicates": duplicates,
        "requested": len(items),
        "site": site,
    })


@app.route('/api/phase2/next-batch', methods=['GET'])
def phase2_next_batch():
    """Return pending queue rows for full save (marks them crawling)."""
    db = get_db()
    site = request.args.get('site', 'thesaurus')
    limit = request.args.get('limit', 20, type=int)
    rows = db.execute(
        """SELECT id, url, page_type, science_id, title, payload, item_id, source_page, site
           FROM crawl_queue
           WHERE status='pending' AND site=? AND page_type NOT IN ('khamenei_speech', 'list')
           ORDER BY priority DESC, id ASC LIMIT ?""",
        (site, limit)
    ).fetchall()
    ids = [r['id'] for r in rows]
    if ids:
        db.execute(
            f"UPDATE crawl_queue SET status='crawling', started_at=datetime('now') WHERE id IN ({','.join('?'*len(ids))})",
            ids
        )
        db.commit()
    return jsonify({"items": [dict(r) for r in rows], "count": len(rows)})


@app.route('/api/phase2/complete', methods=['POST'])
def phase2_complete():
    """
    Save full page content and mark queue item done.
    Thesaurus → crawled_data; Khamenei → khamenei_speeches (via existing submit helpers).
    """
    db = get_db()
    data = request.get_json(silent=True) or {}
    site = data.get('site') or 'thesaurus'
    queue_id = data.get('queue_id')
    url = data.get('url') or ''

    if site == 'khamenei':
        speech = {
            'speech_id': data.get('speech_id') or data.get('item_id'),
            'title': data.get('title', ''),
            'date': data.get('date', '') or data.get('speech_date', ''),
            'year': data.get('year', ''),
            'content': data.get('content', ''),
            'audio_url': data.get('audio_url', ''),
            'video_url': data.get('video_url', ''),
            'url': url,
            'meta_text': data.get('meta_text', ''),
            'tags': data.get('tags', []),
            'related_links': data.get('related_links', []),
            'extra_links': data.get('extra_links', []),
        }
        ensure_khamenei_schema(db)
        result = _phase2_save_khamenei(db, speech)
    else:
        item = data.get('item') or data
        # If payload-only promote
        if not item.get('full_elastic') and data.get('payload'):
            try:
                item = json.loads(data['payload']) if isinstance(data['payload'], str) else data['payload']
            except Exception:
                pass
        result = _phase2_save_thesaurus(db, item, url=url)

    if queue_id:
        db.execute(
            "UPDATE crawl_queue SET status='done', finished_at=datetime('now'), list_only=0 WHERE id=?",
            (queue_id,)
        )
    elif url:
        db.execute(
            "UPDATE crawl_queue SET status='done', finished_at=datetime('now'), list_only=0 WHERE url=?",
            (url,)
        )
    db.commit()
    return jsonify(result)


@app.route('/api/phase2/complete-batch', methods=['POST'])
def phase2_complete_batch():
    """Promote many thesaurus/khamenei queue items into final tables."""
    db = get_db()
    data = request.get_json(silent=True) or {}
    site = data.get('site') or 'thesaurus'
    rows = data.get('items') or []
    results = {'inserted': 0, 'updated': 0, 'skipped': 0, 'errors': 0, 'empty': 0}

    for row in rows:
        try:
            url = row.get('url') or ''
            queue_id = row.get('queue_id') or row.get('id')
            if site == 'khamenei':
                r = _phase2_save_khamenei(db, row)
            else:
                payload = row.get('payload')
                item = row.get('item')
                if not item and payload:
                    item = json.loads(payload) if isinstance(payload, str) else payload
                if not item:
                    results['errors'] += 1
                    continue
                if item.get('Id') and not item.get('item_id'):
                    item = _map_elastic_to_item(item, row.get('science_id') or '', row.get('source_page') or '')
                r = _phase2_save_thesaurus(db, item, url=url or item.get('url'))

            st = r.get('status')
            if st in results:
                results[st] += 1
            else:
                results['errors'] += 1

            if st in ('inserted', 'updated', 'skipped'):
                if queue_id:
                    db.execute(
                        "UPDATE crawl_queue SET status='done', finished_at=datetime('now'), list_only=0 WHERE id=?",
                        (queue_id,)
                    )
                elif url:
                    db.execute(
                        "UPDATE crawl_queue SET status='done', finished_at=datetime('now'), list_only=0 WHERE url=?",
                        (url,)
                    )
        except Exception:
            results['errors'] += 1

    db.commit()
    return jsonify(results)


def _map_elastic_to_item(row, science_id, source_page):
    item_id = row.get('Id') or row.get('item_id') or ''
    main = (row.get('MainType') or {}).get('Id') or row.get('item_type') or 'term'
    # API uses grammer spelling
    path_type = main if main in ('term', 'keyword', 'index', 'grammar', 'category', 'grammer') else 'term'
    if path_type == 'grammer':
        path_type = 'grammar'
    title = row.get('Title') or row.get('title') or ''
    sci = row.get('ScienceField') or {}
    cats = [c.get('Title') for c in (row.get('CategoryList') or []) if isinstance(c, dict) and c.get('Title')]
    defs = row.get('DefinitionList') or row.get('definitions') or []
    parts = []
    for d in defs:
        if not isinstance(d, dict):
            continue
        fa = None
        for t in d.get('Translate') or []:
            if str(t.get('Language', '')).lower() in ('persian', 'fa', 'farsi'):
                fa = t.get('Title')
                break
        parts.append(fa or d.get('Text') or '')
    return {
        'url': row.get('url') or f"https://thesaurus.eiis.iki.ac.ir/fa/{'grammar' if path_type=='grammar' else path_type}/{item_id}",
        'item_id': item_id,
        'item_type': path_type,
        'title': title,
        'science_field': sci.get('Title') or row.get('science_field') or '',
        'science_id': sci.get('Id') or science_id,
        'category': row.get('category') or ' / '.join(cats),
        'source_page': source_page,
        'definitions': defs,
        'related_terms': row.get('RelatedList') or row.get('related_terms') or [],
        'source_text': row.get('source_text') or '\n\n'.join([p for p in parts if p]),
        'full_elastic': row,
    }


def _phase2_save_thesaurus(db, item, url=''):
    if not item:
        return {'status': 'error', 'reason': 'empty item'}
    if item.get('Id') and not item.get('item_id'):
        item = _map_elastic_to_item(item, item.get('science_id') or '', item.get('source_page') or '')
    item_url = url or item.get('url') or ''
    item_id = item.get('item_id') or ''
    item_type = item.get('item_type') or 'term'
    title = item.get('title') or ''
    science_field = item.get('science_field') or ''
    category_tree = item.get('category') or ''
    definitions = item.get('definitions') or []
    related_terms = item.get('related_terms') or []
    source_text = item.get('source_text') or ''
    full_data = json.dumps(item, ensure_ascii=False)
    chash = content_hash(full_data)

    existing = db.execute(
        "SELECT id, content_hash FROM crawled_data WHERE url=? OR (item_id=? AND item_id != '')",
        (item_url, item_id)
    ).fetchone()
    if existing:
        if existing['content_hash'] == chash:
            return {'status': 'skipped'}
        db.execute(
            """UPDATE crawled_data SET title=?, full_data=?, content_hash=?, crawled_at=datetime('now'),
               version=version+1, science_field=?, category_tree=?, definitions=?, related_terms=?,
               source_text=?, item_type=? WHERE id=?""",
            (title, full_data, chash, science_field, category_tree,
             json.dumps(definitions, ensure_ascii=False),
             json.dumps(related_terms, ensure_ascii=False),
             source_text, item_type, existing['id'])
        )
        return {'status': 'updated'}
    db.execute(
        """INSERT INTO crawled_data
           (url, item_id, item_type, title, full_data, content_hash, crawled_at,
            science_field, category_tree, definitions, related_terms, source_text)
           VALUES (?, ?, ?, ?, ?, ?, datetime('now'), ?, ?, ?, ?, ?)""",
        (item_url, item_id, item_type, title, full_data, chash,
         science_field, category_tree,
         json.dumps(definitions, ensure_ascii=False),
         json.dumps(related_terms, ensure_ascii=False),
         source_text)
    )
    return {'status': 'inserted'}


def _phase2_save_khamenei(db, speech):
    ensure_khamenei_schema(db)
    speech_id = str(speech.get('speech_id') or '')
    content = speech.get('content') or ''
    if not speech_id:
        return {'status': 'error', 'reason': 'missing speech_id'}
    if not content:
        return {'status': 'empty'}
    title = speech.get('title') or ''
    speech_date = normalize_jalali_date(speech.get('date') or speech.get('speech_date') or '')
    speech_year = jalali_year(speech_date) or jalali_year(speech.get('year') or '')
    audio_url = speech.get('audio_url') or ''
    image_url = speech.get('image_url') or ''
    video_url = speech.get('video_url') or ''
    page_url = speech.get('url') or f"https://farsi.khamenei.ir/speech-content?id={speech_id}"
    meta_text = speech.get('meta_text') or ''
    tags = json.dumps(speech.get('tags') or [], ensure_ascii=False)
    related_links = json.dumps(speech.get('related_links') or [], ensure_ascii=False)
    extra_links = json.dumps(speech.get('extra_links') or [], ensure_ascii=False)
    char_count = len(content)
    # Include date in hash so date-only fixes trigger update on re-crawl
    chash = content_hash(f"{content}|{speech_date}")
    existing = db.execute(
        "SELECT content_hash, speech_date FROM khamenei_speeches WHERE speech_id=?", (speech_id,)
    ).fetchone()
    if existing:
        old_date = (existing['speech_date'] or '').strip()
        if existing['content_hash'] == chash and old_date:
            return {'status': 'skipped', 'date': speech_date, 'year': speech_year}
        db.execute(
            """UPDATE khamenei_speeches SET title=?, speech_date=?, speech_year=?, content=?, content_hash=?,
               char_count=?, audio_url=?, image_url=?, video_url=?, url=?, meta_text=?,
               tags=?, related_links=?, extra_links=?, crawled_at=datetime('now')
               WHERE speech_id=?""",
            (title, speech_date, speech_year, content, chash, char_count, audio_url, image_url,
             video_url, page_url, meta_text, tags, related_links, extra_links, speech_id)
        )
        return {'status': 'updated', 'date': speech_date, 'year': speech_year}
    db.execute(
        """INSERT INTO khamenei_speeches
           (speech_id, title, speech_date, speech_year, content, content_hash, char_count,
            audio_url, image_url, video_url, url, meta_text, tags, related_links, extra_links)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (speech_id, title, speech_date, speech_year, content, chash, char_count,
         audio_url, image_url, video_url, page_url, meta_text, tags, related_links, extra_links)
    )
    return {'status': 'inserted', 'date': speech_date, 'year': speech_year}


@app.route('/api/pipeline/status')
def pipeline_status():
    db = get_db()
    site = request.args.get('site', 'all')

    def q(sql, args=()):
        return db.execute(sql, args).fetchone()['c']

    where = '' if site == 'all' else " AND site=?"
    args = () if site == 'all' else (site,)
    pending = q(f"SELECT COUNT(*) as c FROM crawl_queue WHERE status='pending'{where}", args)
    crawling = q(f"SELECT COUNT(*) as c FROM crawl_queue WHERE status='crawling'{where}", args)
    done = q(f"SELECT COUNT(*) as c FROM crawl_queue WHERE status='done'{where}", args)
    listed = q(f"SELECT COUNT(*) as c FROM crawl_queue WHERE 1=1{where}", args)

    thesaurus_saved = q("SELECT COUNT(*) as c FROM crawled_data")
    try:
        kh_saved = q("SELECT COUNT(*) as c FROM khamenei_speeches")
        kh_last = db.execute("SELECT MAX(crawled_at) as d FROM khamenei_speeches").fetchone()['d']
    except Exception:
        kh_saved, kh_last = 0, None

    cursors = db.execute("SELECT key, value, updated_at FROM crawl_progress ORDER BY key").fetchall()
    return jsonify({
        "site": site,
        "phase1": {"listed_unique": listed, "pending_detail": pending, "crawling": crawling, "done": done},
        "phase2": {
            "thesaurus_saved": thesaurus_saved,
            "khamenei_saved": kh_saved,
            "khamenei_last_crawled_at": kh_last,
        },
        "sciences": [{"id": a, "title": b} for a, b in THESAURUS_SCIENCES],
        "cursors": [dict(r) for r in cursors],
        "complete": pending == 0 and crawling == 0 and listed > 0,
    })


@app.route('/api/thesaurus/sciences')
def thesaurus_sciences():
    return jsonify({"sciences": [{"id": a, "title": b} for a, b in THESAURUS_SCIENCES]})


# ═══════════════════════════════════════
# API - Queue Management (for Chrome ext)
# ═══════════════════════════════════════

@app.route('/api/next-job', methods=['GET'])
def next_job():
    """
    Extension asks: "what should I crawl next?"
    Returns the highest-priority pending job, or null.
    """
    db = get_db()
    row = db.execute(
        "SELECT * FROM crawl_queue WHERE status='pending' AND page_type NOT IN ('khamenei_speech', 'list') ORDER BY priority DESC, id ASC LIMIT 1"
    ).fetchone()
    if row is None:
        return jsonify(None)
    # Mark as crawling
    db.execute(
        "UPDATE crawl_queue SET status='crawling', started_at=datetime('now') WHERE id=?",
        (row['id'],)
    )
    db.commit()
    return jsonify(dict(row))


@app.route('/api/submit-result', methods=['POST'])
def submit_result():
    """
    Extension submits crawled data.
    Checks content_hash to avoid duplicates (upsert).
    """
    db = get_db()
    data = request.get_json()
    url = data.get('url', '')
    item_id = data.get('item_id', '')
    item_type = data.get('item_type', 'term')
    title = data.get('title', '')
    full_data = json.dumps(data.get('full_data', {}), ensure_ascii=False)
    chash = content_hash(full_data)

    # Check if already crawled with same hash
    existing = db.execute(
        "SELECT id, content_hash FROM crawled_data WHERE url=? OR (item_id=? AND item_id != '')",
        (url, item_id)
    ).fetchone()

    if existing:
        if existing['content_hash'] == chash:
            # Unchanged - just update queue status
            db.execute(
                "UPDATE crawl_queue SET status='done', finished_at=datetime('now'), content_hash=? WHERE url=?",
                (chash, url)
            )
            db.commit()
            return jsonify({"status": "skipped", "reason": "unchanged", "id": existing['id']})
        else:
            # Changed - update data
            db.execute("""
                UPDATE crawled_data SET 
                    title=?, full_data=?, content_hash=?, crawled_at=datetime('now'), version=version+1,
                    science_field=?, category_tree=?, definitions=?, related_terms=?, source_text=?
                WHERE id=?
            """, (
                title, full_data, chash,
                data.get('science_field', ''),
                data.get('category_tree', ''),
                json.dumps(data.get('definitions', []), ensure_ascii=False),
                json.dumps(data.get('related_terms', []), ensure_ascii=False),
                data.get('source_text', ''),
                existing['id']
            ))
            db.execute(
                "UPDATE crawl_queue SET status='done', finished_at=datetime('now'), content_hash=? WHERE url=?",
                (chash, url)
            )
            db.commit()
            return jsonify({"status": "updated", "id": existing['id']})
    else:
        # New item
        cur = db.execute("""
            INSERT INTO crawled_data 
                (url, item_id, item_type, title, full_data, content_hash, 
                 science_field, category_tree, parent_id, definitions, related_terms, source_text)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            url, item_id, item_type, title, full_data, chash,
            data.get('science_field', ''),
            data.get('category_tree', ''),
            data.get('parent_id', ''),
            json.dumps(data.get('definitions', []), ensure_ascii=False),
            json.dumps(data.get('related_terms', []), ensure_ascii=False),
            data.get('source_text', ''),
        ))
        db.execute(
            "UPDATE crawl_queue SET status='done', finished_at=datetime('now'), content_hash=? WHERE url=?",
            (chash, url)
        )
        db.commit()
        return jsonify({"status": "inserted", "id": cur.lastrowid})


@app.route('/api/discover-links', methods=['POST'])
def discover_links():
    """
    Extension sends discovered links (e.g., from a list page).
    Adds them to the queue if not already present.
    """
    db = get_db()
    data = request.get_json()
    links = data.get('links', [])
    source_page = data.get('source_page', '')
    added, skipped = 0, 0
    
    for link in links:
        url = link.get('url', '')
        if not url:
            continue
        page_type = link.get('type', 'term')
        title = link.get('title', '')
        item_id = link.get('item_id', '')
        science_id = link.get('science_id', '')
        
        existing = db.execute("SELECT id FROM crawl_queue WHERE url=?", (url,)).fetchone()
        if not existing:
            db.execute("""
                INSERT INTO crawl_queue (url, page_type, title, item_id, science_id, source_page, status, priority)
                VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)
            """, (url, page_type, title, item_id, science_id, source_page, data.get('priority', 0)))
            added += 1
        else:
            skipped += 1
    db.commit()
    return jsonify({"added": added, "skipped": skipped})


@app.route('/api/page-content', methods=['POST'])
def page_content():
    """
    Extension submits raw content extracted from a page or Elastic API.
    Checks hash before storing.
    """
    db = get_db()
    data = request.get_json() or {}
    return jsonify(upsert_page_items(db, data))


def upsert_page_items(db, data):
    items = data.get('items', [])
    page_url = data.get('url', '')
    results = {'inserted': 0, 'updated': 0, 'skipped': 0}

    for item in items:
        item_url = item.get('url', f"{page_url}#{item.get('item_id', '')}")
        item_id = item.get('item_id', '')
        item_type = item.get('item_type', 'term')
        title = item.get('title', '')
        science_field = item.get('science_field', '')
        category_tree = item.get('category', '')
        definitions = item.get('definitions', [])
        related_terms = item.get('related_terms', [])
        source_text = item.get('source_text', '')
        if not source_text and isinstance(definitions, list):
            parts = []
            for d in definitions:
                if not isinstance(d, dict):
                    continue
                fa = None
                for t in d.get('Translate') or []:
                    if str(t.get('Language', '')).lower() in ('persian', 'fa', 'farsi'):
                        fa = t.get('Title')
                        break
                parts.append(fa or d.get('Text') or '')
            source_text = '\n\n'.join([p for p in parts if p])

        full_data = json.dumps(item, ensure_ascii=False)
        chash = content_hash(full_data)

        existing = db.execute(
            "SELECT id, content_hash FROM crawled_data WHERE url=? OR (item_id=? AND item_id != '')",
            (item_url, item_id if item_id else '')
        ).fetchone()

        if existing:
            if existing['content_hash'] == chash:
                results['skipped'] += 1
                continue
            db.execute("""
                UPDATE crawled_data SET title=?, full_data=?, content_hash=?, crawled_at=datetime('now'),
                    version=version+1, science_field=?, category_tree=?, definitions=?, related_terms=?,
                    source_text=?, item_type=?
                WHERE id=?
            """, (
                title, full_data, chash, science_field, category_tree,
                json.dumps(definitions, ensure_ascii=False),
                json.dumps(related_terms, ensure_ascii=False),
                source_text, item_type, existing['id']
            ))
            results['updated'] += 1
        else:
            db.execute("""
                INSERT INTO crawled_data
                    (url, item_id, item_type, title, full_data, content_hash, crawled_at,
                     science_field, category_tree, definitions, related_terms, source_text)
                VALUES (?, ?, ?, ?, ?, ?, datetime('now'), ?, ?, ?, ?, ?)
            """, (
                item_url, item_id, item_type, title, full_data, chash,
                science_field, category_tree,
                json.dumps(definitions, ensure_ascii=False),
                json.dumps(related_terms, ensure_ascii=False),
                source_text
            ))
            results['inserted'] += 1

        db.execute(
            "INSERT OR IGNORE INTO crawl_queue (url, page_type, title, status, finished_at) VALUES (?, ?, ?, 'done', datetime('now'))",
            (item_url, item_type, title)
        )

    pagination = data.get('pagination') or {}
    meta = data.get('angular_data') or {}
    science_id = meta.get('scienceId') or ''
    if science_id and pagination:
        cursor_url = f"elastic://thesaurus/{science_id}"
        existing_c = db.execute("SELECT id FROM crawl_queue WHERE url=?", (cursor_url,)).fetchone()
        title = f"Elastic cursor {science_id} page {pagination.get('current')}/{pagination.get('total')}"
        page_num = int(pagination.get('current') or 1)
        if existing_c:
            db.execute(
                "UPDATE crawl_queue SET page_num=?, title=?, status='done', finished_at=datetime('now') WHERE url=?",
                (page_num, title, cursor_url)
            )
        else:
            db.execute(
                """INSERT INTO crawl_queue (url, page_type, science_id, title, status, priority, page_num, finished_at)
                   VALUES (?, 'elastic_cursor', ?, ?, 'done', 0, ?, datetime('now'))""",
                (cursor_url, science_id, title, page_num)
            )

    db.commit()
    return results


# In-memory harvest job state (single worker)
_HARVEST_JOB = {
    "running": False,
    "summary": None,
    "error": None,
    "started_at": None,
    "finished_at": None,
}


@app.route('/api/thesaurus/elastic-harvest', methods=['POST'])
def thesaurus_elastic_harvest():
    """
    Start or run Elastic harvest.
    Body: { science_ids?, page_size?, max_pages?, resume?, delay_ms?, async?: true }
    If async=true (default), returns immediately and runs in background thread.
    """
    data = request.get_json(silent=True) or {}
    async_mode = data.get('async', True)

    if _HARVEST_JOB["running"]:
        return jsonify({"ok": False, "message": "harvest already running", "job": _HARVEST_JOB}), 409

    if async_mode:
        import threading
        _HARVEST_JOB.update({
            "running": True,
            "summary": None,
            "error": None,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "finished_at": None,
        })

        def worker():
            try:
                with app.app_context():
                    summary = _run_elastic_harvest(data)
                _HARVEST_JOB["summary"] = summary
            except Exception as e:
                _HARVEST_JOB["error"] = str(e)
            finally:
                _HARVEST_JOB["running"] = False
                _HARVEST_JOB["finished_at"] = datetime.now(timezone.utc).isoformat()

        threading.Thread(target=worker, daemon=True).start()
        return jsonify({"ok": True, "async": True, "message": "harvest started"})

    summary = _run_elastic_harvest(data)
    return jsonify({"ok": True, "async": False, "summary": summary})


@app.route('/api/thesaurus/elastic-harvest/status')
def thesaurus_elastic_harvest_status():
    return jsonify({
        "running": _HARVEST_JOB["running"],
        "summary": _HARVEST_JOB["summary"],
        "error": _HARVEST_JOB["error"],
        "started_at": _HARVEST_JOB["started_at"],
        "finished_at": _HARVEST_JOB["finished_at"],
    })


def _run_elastic_harvest(data):
    import urllib.request
    # PCM-25 DC#2: default to ALL known sciences (the old hard-coded list
    # stopped at 120, which is why کلام/140 + 150/170/180 were never
    # list-scanned by the server and the button could never "finish" them).
    science_ids = data.get('science_ids') or list(THESAURUS_SCIENCE_IDS)
    page_size = int(data.get('page_size') or 100)
    max_pages = data.get('max_pages')
    resume = data.get('resume', True)
    delay_ms = float(data.get('delay_ms') or 200) / 1000.0
    only_science = data.get('science_id')
    if only_science:
        science_ids = [str(only_science)]

    # Dedicated connection for background thread
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")

    summary = {"sciences": {}, "inserted": 0, "updated": 0, "skipped": 0, "pages": 0, "errors": 0}

    elastic_url = "https://thesaurus.eiis.iki.ac.ir/fa/api/elastic/search"
    headers = {
        "accept": "application/json, text/javascript, */*; q=0.01",
        "content-type": "application/json; charset=UTF-8",
        "origin": "https://thesaurus.eiis.iki.ac.ir",
        "referer": "https://thesaurus.eiis.iki.ac.ir/fa/list/",
        "x-requested-with": "XMLHttpRequest",
        "user-agent": "Mozilla/5.0 (compatible; PersianCorpusToolkit/2.3)",
    }

    def fetch_page(science_id, page_number):
        body = json.dumps({
            "PageNumber": page_number,
            "PageSize": page_size,
            "SortItem": "Rank",
            "SortType": "ASC",
            "SearchPhrase": "",
            "MainTypeList": [],
            "ScienceList": [str(science_id)],
            "TermCategoryList": [],
            "TermTypeList": [],
            "CategoryTypeList": [],
            "CategorySubjectList": [],
            "CategoryKeywordList": [],
            "SearchIn": "Both",
            "Lang": "fa",
            "call_num": int(time.time() * 1000),
        }).encode("utf-8")
        req = urllib.request.Request(elastic_url, data=body, headers=headers, method="POST")
        # Avoid system HTTP(S)_PROXY breaking thesaurus access
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(req, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def map_item(row, science_id, source_page):
        item_id = row.get("Id") or ""
        if not item_id:
            return None
        main = (row.get("MainType") or {}).get("Id") or "term"
        path_type = main if main in ("term", "keyword", "index", "grammar", "category") else "term"
        title = row.get("Title") or ""
        sci = row.get("ScienceField") or {}
        cats = [c.get("Title") for c in (row.get("CategoryList") or []) if c.get("Title")]
        defs = row.get("DefinitionList") or []
        parts = []
        for d in defs:
            fa = None
            for t in d.get("Translate") or []:
                if str(t.get("Language", "")).lower() in ("persian", "fa", "farsi"):
                    fa = t.get("Title")
                    break
            parts.append(fa or d.get("Text") or "")
        return {
            "url": f"https://thesaurus.eiis.iki.ac.ir/fa/{path_type}/{item_id}",
            "item_id": item_id,
            "item_type": path_type,
            "title": title,
            "science_field": sci.get("Title") or "",
            "science_id": sci.get("Id") or science_id,
            "category": " / ".join(cats),
            "row_num": "",
            "source_page": source_page,
            "definitions": defs,
            "related_terms": row.get("RelatedList") or [],
            "source_text": "\n\n".join([p for p in parts if p]),
            "full_elastic": row,
        }

    try:
        for science_id in science_ids:
            start_page = 1
            if resume:
                row = db.execute(
                    "SELECT page_num FROM crawl_queue WHERE url=?",
                    (f"elastic://thesaurus/{science_id}",)
                ).fetchone()
                if row and row["page_num"]:
                    start_page = int(row["page_num"]) + 1

            page = start_page
            total_pages = start_page
            sci = {"inserted": 0, "updated": 0, "skipped": 0, "pages": 0, "count": 0, "start_page": start_page}

            while True:
                if max_pages is not None and sci["pages"] >= int(max_pages):
                    break
                try:
                    payload = fetch_page(science_id, page)
                except Exception as e:
                    summary["errors"] += 1
                    sci["error"] = str(e)
                    break

                outer = payload.get("Data") or {}
                inner = outer.get("Data") or outer
                result_list = inner.get("ResultList") or []
                count = inner.get("Count") or 0
                sci["count"] = count
                total_pages = max(1, (count + page_size - 1) // page_size) if count else page
                source_page = f"https://thesaurus.eiis.iki.ac.ir/fa/list/#!?type=type01&ScienceId={science_id}&page={page}"
                items = [x for x in (map_item(r, science_id, source_page) for r in result_list) if x]

                res = upsert_page_items(db, {
                    "url": source_page,
                    "page_type": "list",
                    "items": items,
                    "pagination": {"current": page, "total": total_pages, "totalResults": count},
                    "angular_data": {"source": "elastic-backend", "scienceId": science_id, "pageNumber": page},
                })

                sci["inserted"] += res.get("inserted", 0)
                sci["updated"] += res.get("updated", 0)
                sci["skipped"] += res.get("skipped", 0)
                sci["pages"] += 1
                summary["inserted"] += res.get("inserted", 0)
                summary["updated"] += res.get("updated", 0)
                summary["skipped"] += res.get("skipped", 0)
                summary["pages"] += 1
                summary["current"] = {"science_id": science_id, "page": page, "total_pages": total_pages}
                _HARVEST_JOB["summary"] = dict(summary)

                if not result_list or page >= total_pages:
                    break
                page += 1
                time.sleep(delay_ms)

            summary["sciences"][science_id] = sci
    finally:
        db.close()

    return summary


@app.route('/api/thesaurus/elastic-status')
def thesaurus_elastic_status():
    db = get_db()
    rows = db.execute(
        "SELECT science_id, page_num, title, finished_at FROM crawl_queue WHERE page_type='elastic_cursor' ORDER BY science_id"
    ).fetchall()
    crawled = db.execute("SELECT COUNT(*) as c FROM crawled_data").fetchone()["c"]
    by_type = db.execute(
        "SELECT item_type, COUNT(*) as c FROM crawled_data GROUP BY item_type"
    ).fetchall()
    return jsonify({
        "crawled_total": crawled,
        "by_type": {r["item_type"]: r["c"] for r in by_type},
        "cursors": [dict(r) for r in rows],
        "job": {
            "running": _HARVEST_JOB["running"],
            "summary": _HARVEST_JOB["summary"],
            "error": _HARVEST_JOB["error"],
            "started_at": _HARVEST_JOB["started_at"],
            "finished_at": _HARVEST_JOB["finished_at"],
        },
    })


@app.route('/api/thesaurus/progress')
def thesaurus_progress():
    """PCM-21: per-science progress — how far we are and what remains.
    Real counters only: list scan from crawl_progress cursors
    (thesaurus:list:<sid>), content queue from crawl_queue, saved
    content from crawled_data.
    """
    db = get_db()

    cursor_map = {}
    for key, value in db.execute("SELECT key, value FROM crawl_progress").fetchall():
        if not key.startswith('thesaurus:list:'):
            continue
        try:
            v = json.loads(value)
        except (ValueError, TypeError):
            v = {}
        cursor_map[key[len('thesaurus:list:'):]] = v

    queue_map = {}
    for r in db.execute(
        "SELECT COALESCE(NULLIF(science_id, ''), '_') AS sid, "
        "COUNT(*) AS total, "
        "SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) AS pending, "
        "SUM(CASE WHEN status = 'done' THEN 1 ELSE 0 END) AS done "
        "FROM crawl_queue WHERE site = 'thesaurus' "
        "GROUP BY COALESCE(NULLIF(science_id, ''), '_')"
    ).fetchall():
        queue_map[r['sid']] = r

    # Per-science saved items. Production rows carry the science id in
    # full_data.science_id (the science_field column holds the *title*, not the
    # id, so grouping on it would never match the id-keyed table below). We
    # therefore attribute by the real id, falling back to science_field for
    # legacy rows that stored the id there. This is why the per-science
    # "آیتم‌های ذخیره" column previously rendered all zeros while the total
    # items_saved was 146k+.
    content_map = {}
    for r in db.execute(
        "SELECT sci, COUNT(*) AS c FROM ("
        "  SELECT COALESCE("
        "    NULLIF(json_extract(full_data, '$.science_id'), ''), "
        "    COALESCE(NULLIF(science_field, ''), '_')"
        "  ) AS sci FROM crawled_data"
        ") GROUP BY sci"
    ).fetchall():
        content_map[r['sci']] = r['c']

    main_types = {}
    for r in db.execute(
        "SELECT item_type, COUNT(*) AS c FROM crawled_data "
        "WHERE item_type IN ('term', 'category', 'grammer') GROUP BY item_type"
    ).fetchall():
        main_types[r['item_type']] = r['c']

    sciences = []
    expected_pages = 0
    scanned_pages = 0
    for sid, sname in THESAURUS_SCIENCES:
        cur = cursor_map.get(sid) or {}
        total_pages = cur.get('totalPages')
        scanned = cur.get('page')
        try:
            total_pages = int(total_pages) if total_pages is not None else None
        except (TypeError, ValueError):
            total_pages = None
        try:
            scanned = int(scanned) if scanned is not None else None
        except (TypeError, ValueError):
            scanned = None
        q = queue_map.get(sid)
        if total_pages is not None:
            expected_pages += total_pages
            if scanned is not None:
                scanned_pages += scanned
        sciences.append({
            'id': sid,
            'name': sname,
            'list_scan': {
                'page': scanned,
                'total_pages': total_pages,
                'complete': (total_pages is not None and scanned is not None
                             and scanned >= total_pages),
            },
            'queue': {
                'total': q['total'] if q else 0,
                'pending': (q['pending'] or 0) if q else 0,
                'done': (q['done'] or 0) if q else 0,
            },
            'content_items': content_map.get(sid, 0),
        })

    pending_all = db.execute(
        "SELECT COUNT(*) AS c FROM crawl_queue "
        "WHERE site = 'thesaurus' AND status = 'pending'"
    ).fetchone()['c']
    done_all = db.execute(
        "SELECT COUNT(*) AS c FROM crawl_queue "
        "WHERE site = 'thesaurus' AND status = 'done'"
    ).fetchone()['c']
    items_saved = db.execute("SELECT COUNT(*) AS c FROM crawled_data").fetchone()['c']

    return jsonify({
        'sciences': sciences,
        'list_scan': {
            'expected_pages': expected_pages,
            'scanned_pages': scanned_pages,
            'complete': expected_pages > 0 and scanned_pages >= expected_pages,
        },
        'content': {
            'pending': pending_all,
            'done': done_all,
            'items_saved': items_saved,
            'by_main_type': {
                label: main_types.get(key, 0) for key, label in THESAURUS_MAIN_TYPES
            },
        },
        'harvest_job': {
            'running': _HARVEST_JOB['running'],
            'summary': _HARVEST_JOB['summary'],
            'error': _HARVEST_JOB['error'],
            'started_at': _HARVEST_JOB['started_at'],
            'finished_at': _HARVEST_JOB['finished_at'],
        },
    })


# ═══════════════════════════════════════
# API - Stats & Status
# ═══════════════════════════════════════

@app.route('/api/stats', methods=['GET'])
def stats():
    db = get_db()
    total_queue = db.execute("SELECT COUNT(*) as c FROM crawl_queue").fetchone()['c']
    pending = db.execute("SELECT COUNT(*) as c FROM crawl_queue WHERE status='pending'").fetchone()['c']
    crawling = db.execute("SELECT COUNT(*) as c FROM crawl_queue WHERE status='crawling'").fetchone()['c']
    done = db.execute("SELECT COUNT(*) as c FROM crawl_queue WHERE status='done'").fetchone()['c']
    crawled = db.execute("SELECT COUNT(*) as c FROM crawled_data").fetchone()['c']
    by_type = db.execute("SELECT item_type, COUNT(*) as c FROM crawled_data GROUP BY item_type").fetchall()
    by_site_rows = db.execute(
        "SELECT COALESCE(site, 'thesaurus') AS site, COUNT(*) AS total, "
        "SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) AS pending, "
        "SUM(CASE WHEN status = 'done' THEN 1 ELSE 0 END) AS done "
        "FROM crawl_queue GROUP BY COALESCE(site, 'thesaurus')"
    ).fetchall()

    return jsonify({
        "queue_total": total_queue,
        "queue_pending": pending,
        "queue_crawling": crawling,
        "queue_done": done,
        "queue_by_site": {
            r["site"]: {"total": r["total"], "pending": r["pending"], "done": r["done"]}
            for r in by_site_rows
        },
        "crawled_total": crawled,
        "by_type": {row['item_type']: row['c'] for row in by_type}
    })


@app.route('/api/reset-queue', methods=['POST'])
def reset_queue():
    """Reset all 'crawling' jobs back to 'pending' (PCM-25: report count)."""
    db = get_db()
    cur = db.execute(
        "UPDATE crawl_queue SET status='pending', started_at=NULL "
        "WHERE status='crawling'")
    db.commit()
    return jsonify({"status": "ok", "reset": cur.rowcount})


# ═══════════════════════════════════════
# API - Seed the queue
# ═══════════════════════════════════════

@app.route('/api/seed-categories', methods=['POST'])
def seed_categories():
    """
    Seed the queue with science category list pages.
    Uses the known API: /fa/api/elastic/CategorySearch?ScienceId=X
    and the list page: /fa/list?type=type01&ScienceId=X
    """
    db = get_db()
    base = "https://thesaurus.eiis.iki.ac.ir"
    
    # Science IDs from the API data
    sciences = [
        ("040", "معرفت‌شناسی"),
        ("050", "منطق"),
        ("060", "منطق رواقی"),
        ("070", "فلسفه اسلامی"),
        ("080", "فلسفه اشراق"),
        ("090", "فلسفه دین"),
        ("100", "فلسفه اخلاق"),
        ("110", "فلسفه حقوق"),
        ("120", "فلسفه سیاسی"),
        ("140", "کلام"),
        ("150", "معرفت‌شناسی عرفانی"),
        ("170", "عرفان نظری"),
        ("180", "عرفان عملی"),
    ]
    
    type_ids = [
        ("type01", "list"),
        ("type02", "category"),
    ]
    
    added = 0
    for sid, sname in sciences:
        for tid, tname in type_ids:
            url = f"{base}/fa/list?type={tid}&ScienceId={sid}&page=1"
            existing = db.execute("SELECT id FROM crawl_queue WHERE url=?", (url,)).fetchone()
            if not existing:
                db.execute("""
                    INSERT INTO crawl_queue (url, page_type, science_id, title, status, priority, page_num)
                    VALUES (?, 'list', ?, ?, 'pending', 10, 1)
                """, (url, sid, f"{sname} - {tname}"))
                added += 1
    
    db.commit()
    return jsonify({"seeded": added})


# ═══════════════════════════════════════
# Dashboard API
# ═══════════════════════════════════════

@app.route('/dashboard')
def dashboard():
    return app.send_static_file('index.html')

@app.route('/api/thesaurus/recent')
def thesaurus_recent():
    db = get_db()
    limit = request.args.get('limit', 20, type=int)
    rows = db.execute(
        "SELECT id, item_id, item_type, title, science_field, crawled_at FROM crawled_data WHERE item_type='term' ORDER BY id DESC LIMIT ?",
        (limit,)
    ).fetchall()
    return jsonify([dict(r) for r in rows])

def ensure_khamenei_schema(db):
    db.execute("""
    CREATE TABLE IF NOT EXISTS khamenei_speeches (
        speech_id TEXT PRIMARY KEY,
        title TEXT,
        speech_date TEXT,
        speech_year TEXT,
        content TEXT,
        content_hash TEXT,
        char_count INTEGER,
        audio_url TEXT,
        image_url TEXT,
        video_url TEXT,
        url TEXT,
        meta_text TEXT,
        tags TEXT,
        related_links TEXT,
        extra_links TEXT,
        crawled_at TEXT DEFAULT (datetime('now'))
    )
    """)
    # Lightweight migrations for older DBs
    cols = {r[1] for r in db.execute("PRAGMA table_info(khamenei_speeches)").fetchall()}
    for col, typedef in [
        ('url', 'TEXT'),
        ('meta_text', 'TEXT'),
        ('video_url', 'TEXT'),
        ('related_links', 'TEXT'),
        ('extra_links', 'TEXT'),
        ('speech_year', 'TEXT'),
    ]:
        if col not in cols:
            db.execute(f"ALTER TABLE khamenei_speeches ADD COLUMN {col} {typedef}")
    # Backfill year from speech_date when possible
    db.execute("""
        UPDATE khamenei_speeches
        SET speech_year = substr(speech_date, 1, 4)
        WHERE (speech_year IS NULL OR speech_year = '')
          AND speech_date IS NOT NULL AND length(speech_date) >= 4
    """)
    db.commit()


@app.route('/api/khamenei/stats')
def khamenei_stats():
    db = get_db()
    ensure_khamenei_schema(db)
    total = db.execute("SELECT COUNT(*) as c FROM khamenei_speeches").fetchone()['c']
    total_chars = db.execute("SELECT COALESCE(SUM(char_count),0) as c FROM khamenei_speeches").fetchone()['c']
    pages = db.execute("SELECT COUNT(*) as c FROM crawl_queue WHERE page_type='khamenei_speech'").fetchone()['c']
    pending = db.execute(
        "SELECT COUNT(*) as c FROM crawl_queue WHERE page_type='khamenei_speech' AND status='pending'"
    ).fetchone()['c']
    last = db.execute("SELECT MAX(crawled_at) as d FROM khamenei_speeches").fetchone()['d']
    with_date = db.execute(
        "SELECT COUNT(*) as c FROM khamenei_speeches WHERE speech_date IS NOT NULL AND speech_date != ''"
    ).fetchone()['c']
    without_date = total - with_date
    by_year_rows = db.execute("""
        SELECT COALESCE(NULLIF(speech_year,''), substr(speech_date,1,4), 'نامشخص') AS year,
               COUNT(*) AS c
        FROM khamenei_speeches
        GROUP BY year
        ORDER BY year DESC
    """).fetchall()
    by_year = {r['year']: r['c'] for r in by_year_rows}
    return jsonify({
        "total": total,
        "total_chars": total_chars,
        "pages": pages,
        "pending": pending,
        "last_crawled_at": last,
        "with_date": with_date,
        "without_date": without_date,
        "by_year": by_year,
    })


@app.route('/api/khamenei/reset', methods=['POST'])
def khamenei_reset():
    """
    Reset Khamenei crawl for re-test (e.g. after date extraction fix).
    mode=phase2 (default): keep Phase1 URL list, wipe saved speeches, re-queue Phase2.
    mode=full: also delete khamenei queue + progress (start Phase1 from scratch).
    """
    db = get_db()
    ensure_khamenei_schema(db)
    data = request.get_json(silent=True) or {}
    mode = (data.get('mode') or 'phase2').lower()

    deleted_speeches = db.execute("SELECT COUNT(*) as c FROM khamenei_speeches").fetchone()['c']
    db.execute("DELETE FROM khamenei_speeches")

    if mode == 'full':
        deleted_queue = db.execute(
            "SELECT COUNT(*) as c FROM crawl_queue WHERE site='khamenei' OR page_type='khamenei_speech'"
        ).fetchone()['c']
        db.execute("DELETE FROM crawl_queue WHERE site='khamenei' OR page_type='khamenei_speech'")
        db.execute("DELETE FROM crawl_progress WHERE key LIKE 'khamenei%'")
        requeued = 0
    else:
        deleted_queue = 0
        cur = db.execute(
            """UPDATE crawl_queue
               SET status='pending', started_at=NULL, finished_at=NULL, content_hash=NULL
               WHERE site='khamenei' OR page_type='khamenei_speech'"""
        )
        requeued = cur.rowcount

    db.commit()
    return jsonify({
        "ok": True,
        "mode": mode,
        "deleted_speeches": deleted_speeches,
        "deleted_queue": deleted_queue,
        "requeued": requeued,
        "message": "فاز۲ ریست شد — دوباره فاز۲ را بزن" if mode != 'full'
                   else "کامل ریست شد — دوباره از فاز۱ شروع کن",
    })


@app.route('/api/khamenei/crawl-status')
def khamenei_crawl_status():
    """Resume helper: pending left + last crawl date + complete flag."""
    db = get_db()
    ensure_khamenei_schema(db)
    total = db.execute("SELECT COUNT(*) as c FROM khamenei_speeches").fetchone()['c']
    pending = db.execute(
        "SELECT COUNT(*) as c FROM crawl_queue WHERE page_type='khamenei_speech' AND status='pending'"
    ).fetchone()['c']
    queued = db.execute(
        "SELECT COUNT(*) as c FROM crawl_queue WHERE page_type='khamenei_speech'"
    ).fetchone()['c']
    last = db.execute("SELECT MAX(crawled_at) as d FROM khamenei_speeches").fetchone()['d']
    complete = queued > 0 and pending == 0
    # PCM-21: which past years are still waiting (parsed from the list
    # page source_page = .../speech?nt=2&year=YYYY). Real data only.
    pending_by_year = {}
    for r in db.execute(
        "SELECT source_page FROM crawl_queue "
        "WHERE page_type = 'khamenei_speech' AND status = 'pending'"
    ).fetchall():
        m = re.search(r"year=(\d{4})", r['source_page'] or '')
        y = m.group(1) if m else '?'
        pending_by_year[y] = pending_by_year.get(y, 0) + 1
    return jsonify({
        "total": total,
        "pending": pending,
        "queued": queued,
        "last_crawled_at": last,
        "complete": complete,
        "pending_by_year": pending_by_year,
    })


@app.route('/api/khamenei/pending')
def khamenei_pending():
    db = get_db()
    limit = request.args.get('limit', 500, type=int)
    rows = db.execute(
        """SELECT url FROM crawl_queue
           WHERE page_type='khamenei_speech' AND status='pending'
           ORDER BY priority DESC, id ASC LIMIT ?""",
        (limit,)
    ).fetchall()
    ids = []
    for r in rows:
        mm = re.search(r'id=(\d+)', r['url'] or '')
        if mm:
            ids.append(mm.group(1))
    return jsonify({"ids": ids, "count": len(ids)})


@app.route('/api/khamenei/mark-done', methods=['POST'])
def khamenei_mark_done():
    db = get_db()
    data = request.get_json() or {}
    speech_id = str(data.get('speech_id', ''))
    if not speech_id:
        return jsonify({"error": "speech_id required"}), 400
    url = f"https://farsi.khamenei.ir/speech-content?id={speech_id}"
    db.execute(
        "UPDATE crawl_queue SET status='done', finished_at=datetime('now') WHERE url=? OR url LIKE ?",
        (url, f"%speech-content?id={speech_id}%")
    )
    db.commit()
    return jsonify({"ok": True})

@app.route('/api/khamenei/recent')
def khamenei_recent():
    db = get_db()
    limit = request.args.get('limit', 20, type=int)
    rows = db.execute(
        "SELECT speech_id, title, speech_date, char_count, crawled_at FROM khamenei_speeches ORDER BY speech_id DESC LIMIT ?",
        (limit,)
    ).fetchall()
    return jsonify([dict(r) for r in rows])

_TASNIM_LINE_CACHE = {}
_TASNIM_DATA_DIRS = (
    os.path.join(os.path.dirname(__file__), '..', 'data', 'tasnim'),
    os.path.join(os.path.dirname(__file__), '..', 'data-files', 'tasnim'),
    '/data-files/tasnim',
    '/data/tasnim',
)


def _jsonl_line_count(path):
    """Cached line count for large .jsonl artifacts — the dashboard polls
    /api/corpus/list every 10 s and corpus files are tens of MB."""
    try:
        st = os.stat(path)
    except OSError:
        return 0
    cached = _TASNIM_LINE_CACHE.get(path)
    if cached and cached[0] == st.st_mtime and cached[1] == st.st_size:
        return cached[2]
    n = 0
    try:
        with open(path, 'r', encoding='utf-8') as fh:
            for _ in fh:
                n += 1
    except OSError:
        return 0
    _TASNIM_LINE_CACHE[path] = (st.st_mtime, st.st_size, n)
    return n


def _tasnim_corpus_artifacts():
    """PCM-21: list built, versioned outputs of corpus/tasnim
    (data/tasnim/<root>/{corpus,datasets,dumps}/...). Returns an empty
    list when the data dir is absent (fresh hosts) — never an error."""
    items = []
    base = next((d for d in _TASNIM_DATA_DIRS if os.path.isdir(d)), None)
    if base is None:
        return items
    kind_desc = {
        'corpus': 'پیکره canonical (جریان RAW/NORMALIZED جدا)',
        'dataset': 'دیتاست نسخه‌شده (HF)',
        'dump': 'دامپ رسمی (d-1)',
    }
    for root in sorted(os.listdir(base)):
        root_dir = os.path.join(base, root)
        if not os.path.isdir(root_dir):
            continue
        specs = []
        builds = os.path.join(root_dir, 'corpus', 'builds')
        if os.path.isdir(builds):
            for v in sorted(os.listdir(builds)):
                if os.path.isdir(os.path.join(builds, v)):
                    specs.append(('corpus', v, os.path.join(builds, v)))
        for pct in ('1pct', '10pct', '50pct', '90pct', '100pct'):
            for kind, sub in (('dataset', 'datasets'), ('dump', 'dumps')):
                d = os.path.join(root_dir, sub, pct)
                if os.path.isdir(d):
                    for v in sorted(os.listdir(d)):
                        if os.path.isdir(os.path.join(d, v)):
                            specs.append((kind, pct + ' ' + v, os.path.join(d, v)))
        for kind, ver, path in specs:
            total_size = 0
            entries = 0
            try:
                for fn in sorted(os.listdir(path)):
                    fp = os.path.join(path, fn)
                    if not os.path.isfile(fp):
                        continue
                    total_size += os.path.getsize(fp)
                    if fn.endswith('.jsonl'):
                        entries += _jsonl_line_count(fp)
            except OSError:
                continue
            if total_size == 0:
                continue
            size_str = (f"{total_size/1024:.1f} KB" if total_size < 1024 * 1024
                        else f"{total_size/1024/1024:.1f} MB")
            items.append({
                "name": f"tasnim/{root} — {kind} {ver}",
                "root": root,
                "kind": kind,
                "version": ver,
                "size": size_str,
                "entries": entries,
                "description": kind_desc[kind],
                "detail": "",
            })
    return items


@app.route('/api/corpus/list')
def corpus_list():
    import glob
    corpus_dir = os.path.join(os.path.dirname(__file__), '..', 'corpus', 'output')
    files = []
    descriptions = {
        'thesaurus_raw_corpus.txt': ('پیکره خام کامل', 'متن کامل با هدرهای YAML'),
        'thesaurus_corpus.jsonl': ('فرمت JSONL', 'یک JSON در هر خط'),
        'thesaurus_terms.txt': ('لیست ساده', 'هر خط یک اصطلاح'),
        'thesaurus_dataset_chatml.jsonl': ('ChatML (OpenAI)', 'دیتاست فاین‌تیون فرمت OpenAI'),
        'thesaurus_dataset_alpaca.jsonl': ('Alpaca (Llama)', 'دیتاست فاین‌تیون فرمت Alpaca'),
        'thesaurus_dataset_completion.jsonl': ('Completion', 'دیتاست تکمیل'),
    }
    for f in sorted(glob.glob(os.path.join(corpus_dir, '*'))):
        name = os.path.basename(f)
        if name == 'README.md':
            continue
        size = os.path.getsize(f)
        entries = 0
        if name.endswith('.jsonl'):
            with open(f, 'r', encoding='utf-8') as fh:
                entries = sum(1 for _ in fh)
        size_str = f"{size/1024:.1f} KB" if size < 1024*1024 else f"{size/1024/1024:.1f} MB"
        desc, detail = descriptions.get(name, ('', ''))
        files.append({"name": name, "size": size_str, "entries": entries, "description": desc, "detail": detail})
    # PCM-21: also list built, versioned tasnim corpora/datasets/dumps
    # (empty when data/tasnim is absent on this host).
    files.extend(_tasnim_corpus_artifacts())
    return jsonify({"files": files})

@app.route('/api/queue')
def queue_list():
    db = get_db()
    filter_status = request.args.get('filter', 'all')
    limit = request.args.get('limit', 50, type=int)
    if filter_status != 'all':
        rows = db.execute("SELECT * FROM crawl_queue WHERE status=? ORDER BY priority DESC, id ASC LIMIT ?", (filter_status, limit)).fetchall()
    else:
        rows = db.execute("SELECT * FROM crawl_queue ORDER BY priority DESC, id ASC LIMIT ?", (limit,)).fetchall()
    return jsonify([dict(r) for r in rows])

@app.route('/api/db/info')
def db_info():
    db = get_db()
    tables = []
    for name in ['crawl_queue', 'crawled_data', 'khamenei_speeches']:
        try:
            count = db.execute(f"SELECT COUNT(*) as c FROM {name}").fetchone()['c']
        except:
            count = 0
        desc = {
            'crawl_queue': 'صف کراول - URLهای در انتظار پردازش',
            'crawled_data': 'داده‌های کراول‌شده اصطلاح‌نامه',
            'khamenei_speeches': 'بیانات khamenei.ir',
        }.get(name, '')
        tables.append({"name": name, "rows": count, "size": "-", "description": desc})
    return jsonify({"tables": tables})


# ═══════════════════════════════════════
# Khamenei.ir Speech API
# ═══════════════════════════════════════

@app.route('/api/khamenei/submit', methods=['POST'])
def khamenei_submit():
    """Submit a scraped khamenei speech (text + URL + metadata)."""
    db = get_db()
    ensure_khamenei_schema(db)
    data = request.get_json() or {}
    speech_id = str(data.get('speech_id', ''))
    result = _phase2_save_khamenei(db, {
        'speech_id': speech_id,
        'title': data.get('title', ''),
        'date': data.get('date', ''),
        'year': data.get('year', ''),
        'content': data.get('content', ''),
        'audio_url': data.get('audio_url', ''),
        'image_url': data.get('image_url', ''),
        'video_url': data.get('video_url', ''),
        'url': data.get('url') or f"https://farsi.khamenei.ir/speech-content?id={speech_id}",
        'meta_text': data.get('meta_text', ''),
        'tags': data.get('tags', []),
        'related_links': data.get('related_links', []),
        'extra_links': data.get('extra_links', []),
    })
    if result.get('status') in ('inserted', 'updated', 'skipped'):
        db.execute(
            "UPDATE crawl_queue SET status='done', finished_at=datetime('now') WHERE page_type='khamenei_speech' AND url LIKE ?",
            (f"%id={speech_id}%",)
        )
        db.commit()
    return jsonify(result)


@app.route('/api/khamenei/seed', methods=['POST'])
def khamenei_seed():
    """Seed the queue with khamenei speech IDs (skip already crawled)."""
    db = get_db()
    ensure_khamenei_schema(db)
    data = request.get_json() or {}
    ids = [str(x) for x in data.get('ids', [])]
    links = data.get('links') or []
    source_url = data.get('source_url', '')
    # Also accept link objects
    for link in links:
        sid = str(link.get('id') or link.get('speech_id') or '')
        if sid:
            ids.append(sid)
    ids = list(dict.fromkeys(ids))
    added = 0
    skipped_done = 0
    base = "https://farsi.khamenei.ir"
    for sid in ids:
        url = f"{base}/speech-content?id={sid}"
        already = db.execute(
            "SELECT speech_id FROM khamenei_speeches WHERE speech_id=?", (sid,)
        ).fetchone()
        if already:
            skipped_done += 1
            # ensure queue marked done
            db.execute(
                "UPDATE crawl_queue SET status='done', finished_at=datetime('now') WHERE url=?",
                (url,)
            )
            continue
        existing = db.execute("SELECT id, status FROM crawl_queue WHERE url=?", (url,)).fetchone()
        if not existing:
            title = f"Speech #{sid}"
            for link in links:
                if str(link.get('id') or '') == sid and link.get('title'):
                    title = link['title']
                    break
            db.execute(
                """INSERT INTO crawl_queue
                   (url, page_type, title, status, priority, source_page)
                   VALUES (?, 'khamenei_speech', ?, 'pending', 5, ?)""",
                (url, title, source_url)
            )
            added += 1
        elif existing['status'] in ('done', 'failed'):
            # Re-queue only if not in speeches table (handled above)
            pass
    db.commit()
    return jsonify({"seeded": added, "already_crawled": skipped_done, "requested": len(ids)})


# ═══════════════════════════════════════
# EITAA CHANNEL CRAWL (additive; same family as /api/khamenei/*)
# ═══════════════════════════════════════

EITAA_CHANNEL_FIELDS = (
    "username", "display_name", "description",
    "followers_count", "photos_count", "videos_count", "files_count",
    "photo_url",
)
EITAA_POST_FIELDS = (
    "post_id", "channel", "post_number", "post_type",
    "media_title", "media_duration", "media_size",
    "text", "post_date", "views", "url",
)


def ensure_eitaa_schema(db):
    db.execute("""
    CREATE TABLE IF NOT EXISTS eitaa_channels (
        username TEXT PRIMARY KEY,
        display_name TEXT,
        description TEXT,
        followers_count INTEGER,
        photos_count INTEGER,
        videos_count INTEGER,
        files_count INTEGER,
        photo_url TEXT,
        created_at TEXT DEFAULT (datetime('now')),
        updated_at TEXT DEFAULT (datetime('now'))
    )
    """)
    db.execute("""
    CREATE TABLE IF NOT EXISTS eitaa_posts (
        post_id TEXT PRIMARY KEY,
        channel TEXT NOT NULL,
        post_number INTEGER,
        post_type TEXT,
        media_title TEXT,
        media_duration TEXT,
        media_size TEXT,
        text TEXT,
        post_date TEXT,
        views INTEGER,
        url TEXT,
        full_data TEXT,
        content_hash TEXT,
        char_count INTEGER,
        crawled_at TEXT DEFAULT (datetime('now'))
    )
    """)
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_eitaa_posts_channel "
        "ON eitaa_posts(channel, post_number)"
    )
    db.commit()


def _eitaa_canonical_channel(data):
    """Filter to the 8 known channel keys; counts → int, others → str."""
    canon = {}
    for k in EITAA_CHANNEL_FIELDS:
        v = data.get(k)
        if k.endswith("_count"):
            try:
                canon[k] = int(v or 0)
            except (TypeError, ValueError):
                canon[k] = 0
        else:
            canon[k] = str(v or "")
    return canon


def _eitaa_save_channel(db, data):
    username = str(data.get("username") or "").strip()
    if not username:
        return None
    canon = _eitaa_canonical_channel(data)
    existing = db.execute(
        "SELECT * FROM eitaa_channels WHERE username=?", (username,)
    ).fetchone()
    if existing is None:
        db.execute(
            """INSERT INTO eitaa_channels
               (username, display_name, description, followers_count,
                photos_count, videos_count, files_count, photo_url)
               VALUES (?,?,?,?,?,?,?,?)""",
            (canon["username"], canon["display_name"], canon["description"],
             canon["followers_count"], canon["photos_count"],
             canon["videos_count"], canon["files_count"], canon["photo_url"]),
        )
        return {"status": "inserted", "username": username}
    prev = json.dumps(
        {k: existing[k] for k in EITAA_CHANNEL_FIELDS},
        sort_keys=True, ensure_ascii=False)
    cur = json.dumps(canon, sort_keys=True, ensure_ascii=False)
    if prev == cur:
        return {"status": "skipped", "username": username}
    db.execute(
        """UPDATE eitaa_channels
           SET display_name=?, description=?, followers_count=?, photos_count=?,
               videos_count=?, files_count=?, photo_url=?,
               updated_at=datetime('now')
           WHERE username=?""",
        (canon["display_name"], canon["description"], canon["followers_count"],
         canon["photos_count"], canon["videos_count"], canon["files_count"],
         canon["photo_url"], username),
    )
    return {"status": "updated", "username": username}


def _eitaa_canonical_post(data):
    """Filter to the 11 known post keys; ints for post_number/views, str for the rest."""
    canon = {}
    for k in EITAA_POST_FIELDS:
        v = data.get(k)
        if k in ("post_number", "views"):
            try:
                canon[k] = int(v or 0)
            except (TypeError, ValueError):
                canon[k] = 0
        else:
            canon[k] = str(v or "")
    return canon


def _eitaa_save_post(db, data):
    post_id = str(data.get("post_id") or "").strip()
    if not post_id:
        return None
    canon = _eitaa_canonical_post(data)
    if not canon["text"] and not canon["media_title"]:
        return {"status": "empty", "post_id": post_id}
    # views is volatile (changes between crawls) — excluded from the hash.
    chash = content_hash({k: v for k, v in canon.items() if k != "views"})
    full_data = json.dumps(canon, ensure_ascii=False)
    char_count = len(canon["text"])
    existing = db.execute(
        "SELECT content_hash FROM eitaa_posts WHERE post_id=?", (post_id,)
    ).fetchone()
    if existing is not None:
        if existing["content_hash"] == chash:
            return {"status": "skipped", "post_id": post_id}
        db.execute(
            """UPDATE eitaa_posts
               SET channel=?, post_number=?, post_type=?, media_title=?,
                   media_duration=?, media_size=?, text=?, post_date=?,
                   views=?, url=?, full_data=?, content_hash=?, char_count=?,
                   crawled_at=datetime('now')
               WHERE post_id=?""",
            (canon["channel"], canon["post_number"], canon["post_type"],
             canon["media_title"], canon["media_duration"], canon["media_size"],
             canon["text"], canon["post_date"], canon["views"], canon["url"],
             full_data, chash, char_count, post_id),
        )
        return {"status": "updated", "post_id": post_id}
    db.execute(
        """INSERT INTO eitaa_posts
           (post_id, channel, post_number, post_type, media_title, media_duration,
            media_size, text, post_date, views, url, full_data, content_hash, char_count)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (canon["post_id"], canon["channel"], canon["post_number"], canon["post_type"],
         canon["media_title"], canon["media_duration"], canon["media_size"],
         canon["text"], canon["post_date"], canon["views"], canon["url"],
         full_data, chash, char_count),
    )
    return {"status": "inserted", "post_id": post_id}


@app.route('/api/eitaa/channel', methods=['POST'])
def eitaa_channel():
    """Register/update a channel once (idempotent upsert)."""
    db = get_db()
    ensure_eitaa_schema(db)
    data = request.get_json(silent=True) or {}
    result = _eitaa_save_channel(db, data)
    if result is None:
        return jsonify({"error": "username required"}), 400
    db.commit()
    return jsonify(result)


@app.route('/api/eitaa/submit', methods=['POST'])
def eitaa_submit():
    """Store one post; promote the page row to done and enqueue the next page."""
    db = get_db()
    ensure_eitaa_schema(db)
    data = request.get_json(silent=True) or {}
    post_id = str(data.get("post_id") or "").strip()
    if not post_id:
        return jsonify({"error": "post_id required"}), 400
    result = _eitaa_save_post(db, data)
    page_url = data.get("page_url")
    next_url = data.get("next_url")
    if page_url:
        db.execute(
            """INSERT INTO crawl_queue
               (url, page_type, site, title, status, finished_at)
               VALUES (?, 'eitaa_page', 'eitaa', ?, 'done', datetime('now'))
               ON CONFLICT(url) DO UPDATE
               SET status='done', finished_at=datetime('now')""",
            (str(page_url), str(page_url)),
        )
    if next_url:
        db.execute(
            """INSERT OR IGNORE INTO crawl_queue
               (url, page_type, site, title, status)
               VALUES (?, 'eitaa_page', 'eitaa', ?, 'pending')""",
            (str(next_url), str(next_url)),
        )
    db.commit()
    return jsonify(result)


from sites import register_site_routes
from projects import register_project_routes
from auth import ensure_auth_schema, seed_password, register_auth_routes
from dashboard_api import register_dashboard_routes
from knowledge_api import ensure_knowledge_schema, register_knowledge_routes
register_site_routes(app, get_db)
register_project_routes(app, get_db)
register_auth_routes(app, get_db)
register_dashboard_routes(app, get_db)
register_knowledge_routes(app, get_db)


def _init_auth(db):
    ensure_auth_schema(db)
    seed_password(db)


# ═══════════════════════════════════════
# MAIN
# ═══════════════════════════════════════

if __name__ == '__main__':
    init_db()
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    ensure_khamenei_schema(db)
    ensure_eitaa_schema(db)
    db.close()
    host = os.environ.get('HOST', '0.0.0.0')
    port = int(os.environ.get('PORT', '5055'))
    print("Persian Corpus Toolkit Backend")
    print(f"   API:    http://{host}:{port}")
    print(f"   Dashboard: http://{host}:{port}/dashboard")
    app.run(host=host, port=port, debug=False, use_reloader=False)

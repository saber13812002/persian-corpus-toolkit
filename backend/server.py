"""
Thesaurus Crawler Backend
Flask API + SQLite - Crawl queue manager & data store
"""

import sqlite3, json, hashlib, time, os
from datetime import datetime, timezone
from flask import Flask, request, jsonify, g
from flask_cors import CORS

app = Flask(__name__, static_folder='../dashboard', static_url_path='/dashboard')
CORS(app)

DB_PATH = os.path.join(os.path.dirname(__file__), 'thesaurus.db')


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
        page_type   TEXT NOT NULL DEFAULT 'term',   -- 'category', 'list', 'term', 'grammar', 'keyword', 'index'
        science_id  TEXT,      -- e.g., '040', '050'
        category_id TEXT,      -- category tree id
        title       TEXT,
        status      TEXT NOT NULL DEFAULT 'pending',  -- 'pending', 'queued', 'crawling', 'done', 'failed'
        priority    INTEGER DEFAULT 0,
        depth       INTEGER DEFAULT 0,
        content_hash TEXT,
        created_at  TEXT DEFAULT (datetime('now')),
        started_at  TEXT,
        finished_at TEXT,
        error_msg   TEXT,
        retry_count INTEGER DEFAULT 0,
        source_page TEXT,      -- which page this URL was discovered from
        page_num    INTEGER    -- pagination: which page number in a list
    );

    CREATE TABLE IF NOT EXISTS crawled_data (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        url         TEXT NOT NULL UNIQUE,
        item_id     TEXT,       -- internal item ID (hash)
        item_type   TEXT,       -- 'term', 'keyword', 'index', 'grammar', 'category'
        title       TEXT,
        title_en    TEXT,
        full_data   TEXT,       -- full JSON blob of the crawled data
        content_hash TEXT NOT NULL,
        science_field TEXT,
        category_tree TEXT,     -- TreePath from API
        parent_id   TEXT,
        definitions TEXT,       -- JSON array of definitions
        related_terms TEXT,     -- JSON array of related term IDs
        source_text  TEXT,      -- plain text for NLP corpus
        crawled_at  TEXT DEFAULT (datetime('now')),
        version     INTEGER DEFAULT 1
    );

    CREATE INDEX IF NOT EXISTS idx_queue_status ON crawl_queue(status, priority);
    CREATE INDEX IF NOT EXISTS idx_queue_url ON crawl_queue(url);
    CREATE INDEX IF NOT EXISTS idx_crawled_url ON crawled_data(url);
    CREATE INDEX IF NOT EXISTS idx_crawled_hash ON crawled_data(content_hash);
    CREATE INDEX IF NOT EXISTS idx_crawled_type ON crawled_data(item_type);
    """)
    db.commit()
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
        "SELECT * FROM crawl_queue WHERE status='pending' ORDER BY priority DESC, id ASC LIMIT 1"
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
    Extension submits raw content extracted from a page.
    Used when the extension reads terms/lists directly from page and sends them.
    Checks hash before storing.
    """
    db = get_db()
    data = request.get_json()
    items = data.get('items', [])
    page_url = data.get('url', '')
    page_type = data.get('page_type', 'list')
    
    results = {'inserted': 0, 'updated': 0, 'skipped': 0}
    
    for item in items:
        item_url = item.get('url', f"{page_url}#{item.get('item_id', '')}")
        item_id = item.get('item_id', '')
        item_type = item.get('item_type', 'term')
        title = item.get('title', '')
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
            else:
                db.execute("""
                    UPDATE crawled_data SET title=?, full_data=?, content_hash=?, crawled_at=datetime('now'), version=version+1
                    WHERE id=?
                """, (title, full_data, chash, existing['id']))
                results['updated'] += 1
        else:
            db.execute("""
                INSERT INTO crawled_data (url, item_id, item_type, title, full_data, content_hash, crawled_at)
                VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
            """, (item_url, item_id, item_type, title, full_data, chash))
            results['inserted'] += 1
            
        # Also mark queue entry
        db.execute(
            "INSERT OR IGNORE INTO crawl_queue (url, page_type, title, status, finished_at) VALUES (?, ?, ?, 'done', datetime('now'))",
            (item_url, item_type, title)
        )
    
    db.commit()
    return jsonify(results)


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
    
    return jsonify({
        "queue_total": total_queue,
        "queue_pending": pending,
        "queue_crawling": crawling,
        "queue_done": done,
        "crawled_total": crawled,
        "by_type": {row['item_type']: row['c'] for row in by_type}
    })


@app.route('/api/reset-queue', methods=['POST'])
def reset_queue():
    """Reset all 'crawling' jobs back to 'pending'"""
    db = get_db()
    db.execute("UPDATE crawl_queue SET status='pending', started_at=NULL WHERE status='crawling'")
    db.commit()
    return jsonify({"status": "ok"})


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

@app.route('/api/khamenei/stats')
def khamenei_stats():
    db = get_db()
    total = db.execute("SELECT COUNT(*) as c FROM khamenei_speeches").fetchone()['c']
    total_chars = db.execute("SELECT COALESCE(SUM(char_count),0) as c FROM khamenei_speeches").fetchone()['c']
    pages = db.execute("SELECT COUNT(*) as c FROM crawl_queue WHERE page_type='khamenei_speech'").fetchone()['c']
    return jsonify({"total": total, "total_chars": total_chars, "pages": pages})

@app.route('/api/khamenei/recent')
def khamenei_recent():
    db = get_db()
    limit = request.args.get('limit', 20, type=int)
    rows = db.execute(
        "SELECT speech_id, title, speech_date, char_count, crawled_at FROM khamenei_speeches ORDER BY speech_id DESC LIMIT ?",
        (limit,)
    ).fetchall()
    return jsonify([dict(r) for r in rows])

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
    """Submit a scraped khamenei speech"""
    db = get_db()
    data = request.get_json()
    speech_id = data.get('speech_id', '')
    title = data.get('title', '')
    speech_date = data.get('date', '')
    content = data.get('content', '')
    audio_url = data.get('audio_url', '')
    image_url = data.get('image_url', '')
    tags = json.dumps(data.get('tags', []), ensure_ascii=False)
    char_count = len(content)
    chash = content_hash(content)
    
    db.execute("CREATE TABLE IF NOT EXISTS khamenei_speeches (speech_id TEXT PRIMARY KEY, title TEXT, speech_date TEXT, content TEXT, content_hash TEXT, char_count INTEGER, audio_url TEXT, image_url TEXT, tags TEXT, crawled_at TEXT DEFAULT (datetime('now')))")
    
    existing = db.execute("SELECT content_hash FROM khamenei_speeches WHERE speech_id=?", (speech_id,)).fetchone()
    if existing:
        if existing['content_hash'] == chash:
            return jsonify({"status": "skipped", "reason": "unchanged"})
        else:
            db.execute("UPDATE khamenei_speeches SET title=?, speech_date=?, content=?, content_hash=?, char_count=?, audio_url=?, image_url=?, tags=?, crawled_at=datetime('now') WHERE speech_id=?", 
                       (title, speech_date, content, chash, char_count, audio_url, image_url, tags, speech_id))
            db.commit()
            return jsonify({"status": "updated"})
    else:
        db.execute("INSERT INTO khamenei_speeches (speech_id, title, speech_date, content, content_hash, char_count, audio_url, image_url, tags) VALUES (?,?,?,?,?,?,?,?,?)",
                   (speech_id, title, speech_date, content, chash, char_count, audio_url, image_url, tags))
        db.commit()
        return jsonify({"status": "inserted"})


@app.route('/api/khamenei/seed', methods=['POST'])
def khamenei_seed():
    """Seed the queue with khamenei speech IDs"""
    db = get_db()
    data = request.get_json()
    ids = data.get('ids', [])
    added = 0
    base = "https://farsi.khamenei.ir"
    for sid in ids:
        url = f"{base}/speech-content?id={sid}"
        existing = db.execute("SELECT id FROM crawl_queue WHERE url=?", (url,)).fetchone()
        if not existing:
            db.execute("INSERT INTO crawl_queue (url, page_type, title, status, priority) VALUES (?, 'khamenei_speech', ?, 'pending', 5)", (url, f"Speech #{sid}"))
            added += 1
    db.commit()
    return jsonify({"seeded": added})


# ═══════════════════════════════════════
# MAIN
# ═══════════════════════════════════════

if __name__ == '__main__':
    init_db()
    # Ensure khamenei_speeches table exists
    db = sqlite3.connect(DB_PATH)
    db.execute("CREATE TABLE IF NOT EXISTS khamenei_speeches (speech_id TEXT PRIMARY KEY, title TEXT, speech_date TEXT, content TEXT, content_hash TEXT, char_count INTEGER, audio_url TEXT, image_url TEXT, tags TEXT, crawled_at TEXT DEFAULT (datetime('now')))")
    db.commit()
    db.close()
    print(f"🚀 Persian Corpus Toolkit Backend")
    print(f"   API:    http://127.0.0.1:5000")
    print(f"   Dashboard: http://127.0.0.1:5000/dashboard")
    app.run(host='127.0.0.1', port=5000, debug=False, use_reloader=False)

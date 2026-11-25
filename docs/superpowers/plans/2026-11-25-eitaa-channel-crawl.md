# Eitaa Channel Crawl Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Register an Eitaa channel once and crawl its posts post-by-post into the backend DB, so the existing JSONL → Dump `d-1` → corpus/registry pipeline can later be built from the stored data.

**Architecture:** Two additive SQLite tables (`eitaa_channels`, `eitaa_posts`) + 8 unauthenticated endpoints in `backend/server.py` (same family/pattern as the existing `/api/khamenei/*`), plus a standalone `corpus/scrape_eitaa.py` that walks the site's server-rendered pagination backwards (`?before=N`, terminal when a page has no "مطالب قبلی" anchor) and submits each post. Resume is a single-page frontier in `crawl_queue` (≤1 pending row).

**Tech Stack:** Python 3, Flask, sqlite3 (WAL), `requests`, unittest. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-11-25-eitaa-channel-crawl-design.md`

## Global Constraints

- Scope: `backend/`, `corpus/`, `docs/` only (AGENTS.md §1).
- SQL: parameterized placeholders; `ORDER BY` only from a whitelist; `LIMIT/OFFSET` for pagination; no whole-table loads in API responses (AGENTS.md §2.7).
- Schema changes additive only: `CREATE TABLE IF NOT EXISTS` / `ALTER ... ADD COLUMN`; no DROP/RENAME (AGENTS.md §2.2).
- Test modules: `import pct_test_support` MUST precede `import server`; every test class calls `pct_test_support.reset_db()` in `setUp`; never set `PCT_DB` or call `server.init_db()` directly (AGENTS.md §4).
- No deploy to s52 in this mission; production `thesaurus.db` is never opened by tests.
- No secrets in code/logs/metrics (AGENTS.md §2.5).
- Stats endpoints return real DB counters only, no invented numbers (AGENTS.md §2.9).
- Windows dev box: interpreter `.venv\Scripts\python.exe`; backend tests run from `backend/`, corpus tests from the repo root.
- Eitaa page facts (verified live 2026-11-25 on `sharabebeheshti`, server-rendered — no JS):
  - page 1 = `https://eitaa.com/<chan>` (the 12 **newest** posts); walk backwards via the bottom anchor `<a href="/<chan>?before=N&q=" class="eme_messages_more js-messages_more" data-before="N">` ("مطالب قبلی") — **there is no `<link rel="next">`** and the older direction is `?before=N`, not `?after=N`. The **oldest page carries no more anchor** → that is the terminal stop. ~12 posts/page; this channel currently has 1314 posts.
  - post block: `<div class="etme_widget_message <classes> js-widget_message" data-post="<chan>/<N>" [data-view="..."]>` (wrap divs are `etme_widget_message_wrap` — no `data-post`, must not match); oldest/pinned posts carry class `service_message`; pinned banner text "سنجاق پیغام".
  - media block: `<a class="etme_widget_message_document_wrap" href="/<chan>/<N>">` containing `<div class="etme_widget_message_document_icon accent_bg audio|video|image|file"></div>`, `.etme_widget_message_document_title` (may wrap the filename in nothing — plain text node), `<time>11:59</time>` (duration; photos may omit `<time>` entirely), span "حجم:\n 5.1M" (newline inside the span is possible).
  - caption: `<div class="etme_widget_message_text js-message_text" ...>` (white-space pre-wrap → newlines meaningful); date: `<time datetime="2026-11-22T12:29:14+00:00" class="time">12:29</time>`; views: `span.etme_widget_message_views[data-count]` (followed by `<span class="copyonly"> مشاهده</span>`).
  - channel header: `<div class="etme_channel_info_header_title"><span dir="auto">موسسه شراب بهشتی</span></div>` (nested span!), `<div class="etme_channel_info_header_username"><a href="/<chan>">@<chan></a></div>`, `<img src="/download_...?token=...">` inside `.etme_page_photo_image`, `.etme_channel_info_description` (pre-wrap), counters: `<div class="etme_channel_info_counter"><span class="counter_value" data-count="683">683</span> <span class="counter_type">دنبال‌کننده</span></div>` — **value span first, label span second**; labels دنبال‌کننده/عکس/ویدیو/فایل.

## Review Focus

1. Page with zero posts (404/error HTML, deleted channel) → `parse_posts` returns `[]`, crawl stops cleanly without crash. — pinned to Task 3 (T-05) and Task 4 (T-09).
2. Media-block variants (video/image/file icons; document with no duration/size, e.g. photos; no media at all) → optional fields come back `""`/`0`, never `KeyError`. — pinned to Task 3 (T-03).
3. HTML entities and multi-line Persian captions (`&`, `<br>`, `white-space: pre-wrap`) → unescaped, newline-preserving text. — pinned to Task 3 (T-03).
4. Re-crawl / resume of a channel with new posts → old posts `skipped` by content hash, new ones `inserted`, no duplicate rows. — pinned to Task 1 (EA-03) for the hash rule; Task 4 (T-07) for the frontier walk.
5. Network failure mid-walk (requests exception / non-200) → retries with backoff, then counted in `errors` and the run stops without a traceback. — pinned to Task 4 (T-08).

---

### Task 1: Backend — schema + `/api/eitaa/channel` + `/api/eitaa/submit`

**Files:**
- Modify: `backend/server.py` (new `# EITAA` section inserted immediately before the `from sites import register_site_routes` line, ~line 1707; also add `ensure_eitaa_schema(db)` in the `if __name__ == '__main__':` block right after `ensure_khamenei_schema(db)`, ~line 1732)
- Test: `backend/test_eitaa.py` (new)

**Interfaces:**
- Consumes: `content_hash()` (`server.py:169`), `get_db()`, `crawl_queue` table (already exists), `pct_test_support`.
- Produces:
  - `server.ensure_eitaa_schema(db)` — idempotent; creates:
    ```sql
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
    );
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
    );
    CREATE INDEX IF NOT EXISTS idx_eitaa_posts_channel ON eitaa_posts(channel, post_number);
    ```
  - `POST /api/eitaa/channel` — body: channel dict (keys as table columns minus timestamps) → `{"status": "inserted"|"updated"|"skipped", "username": str}`; 400 `{"error": "username required"}` when username missing/empty. Upsert rule: same canonical JSON → `skipped`; different → `UPDATE` + `updated_at=datetime('now')` → `updated`.
  - `POST /api/eitaa/submit` — body: post dict `{"post_id", "channel", "post_number", "post_type", "media_title", "media_duration", "media_size", "text", "post_date", "views", "url"}` + optional `"page_url"`, `"next_url"` → `{"status": "inserted"|"updated"|"skipped"|"empty"|"error", "post_id": str}`.
    - `empty` (409 body status, HTTP 200): `text` empty **and** `media_title` empty → nothing stored.
    - `content_hash` computed over the canonical dict of the 11 post fields **excluding `views`** (view counts change between crawls; spec §4.1).
    - `full_data` = `json.dumps(canonical 11-field dict, ensure_ascii=False)`; `char_count = len(text)`.
    - Front-side bookkeeping: if `page_url` present → `INSERT INTO crawl_queue (url, page_type, site, title, status, finished_at) VALUES (?, 'eitaa_page', 'eitaa', ?, 'done', datetime('now')) ON CONFLICT(url) DO UPDATE SET status='done', finished_at=datetime('now')` (seed created the row as `pending`, this promotes it). If `next_url` present → `INSERT OR IGNORE ... status='pending'` row for it.
    - 400 when `post_id` missing.
  - Every handler calls `ensure_eitaa_schema(db)` first (same defensive pattern as khamenei handlers).

- [ ] **Step 1: Write the failing tests** — create `backend/test_eitaa.py`:

```python
"""API tests for Eitaa channel registration + post submission (EA-01..EA-08)."""
import sqlite3
import unittest

import pct_test_support  # noqa: F401  (MUST precede `import server`)
import server  # noqa: E402

CHANNEL = {
    "username": "sharabebeheshti",
    "display_name": "موسسه شراب بهشتی",
    "description": "ادمین\n@sabertaba",
    "followers_count": 683,
    "photos_count": 332,
    "videos_count": 40,
    "files_count": 4,
    "photo_url": "/download_b591189e?token=abc",
}

POST = {
    "post_id": "sharabebeheshti/2",
    "channel": "sharabebeheshti",
    "post_number": 2,
    "post_type": "audio",
    "media_title": "Sharab-e-Beheshti01 - Vaghee.mp3",
    "media_duration": "17:50",
    "media_size": "17.2M",
    "text": "دانلود کامل 5 فصل:\n1-نهج البلاغه",
    "post_date": "2023-05-14T05:33:18+00:00",
    "views": 1,
    "url": "https://eitaa.com/sharabebeheshti/2",
}

PAGE1 = "https://eitaa.com/sharabebeheshti"
PAGE2 = "https://eitaa.com/sharabebeheshti?before=1303"


class EitaaApiTests(unittest.TestCase):
    def setUp(self):
        pct_test_support.reset_db()
        db = sqlite3.connect(server.DB_PATH)
        server.ensure_eitaa_schema(db)
        db.close()
        self.client = server.app.test_client()

    def test_ea01_channel_upsert(self):
        self.assertEqual(self.client.post("/api/eitaa/channel", json=CHANNEL).get_json()["status"], "inserted")
        self.assertEqual(self.client.post("/api/eitaa/channel", json=CHANNEL).get_json()["status"], "skipped")
        self.assertEqual(self.client.post("/api/eitaa/channel", json=dict(CHANNEL, followers_count=700)).get_json()["status"], "updated")
        self.assertEqual(self.client.post("/api/eitaa/channel", json={}).status_code, 400)

    def test_ea02_post_insert(self):
        self.assertEqual(self.client.post("/api/eitaa/submit", json=POST).get_json()["status"], "inserted")
        db = sqlite3.connect(server.DB_PATH)
        db.row_factory = sqlite3.Row
        row = db.execute("SELECT * FROM eitaa_posts WHERE post_id=?", (POST["post_id"],)).fetchone()
        db.close()
        self.assertEqual(row["media_title"], "Sharab-e-Beheshti01 - Vaghee.mp3")
        self.assertEqual(row["media_duration"], "17:50")
        self.assertEqual(row["media_size"], "17.2M")
        self.assertEqual(row["post_date"], "2023-05-14T05:33:18+00:00")
        self.assertEqual(row["char_count"], len(POST["text"]))
        self.assertIn("Sharab-e-Beheshti01", row["full_data"])

    def test_ea03_resubmit_same_skipped_views_ignored(self):
        self.client.post("/api/eitaa/submit", json=POST)
        self.assertEqual(self.client.post("/api/eitaa/submit", json=POST).get_json()["status"], "skipped")
        # views is volatile — a change in views alone must NOT trigger an update
        self.assertEqual(self.client.post("/api/eitaa/submit", json=dict(POST, views=5)).get_json()["status"], "skipped")

    def test_ea04_changed_post_updated(self):
        self.client.post("/api/eitaa/submit", json=POST)
        self.assertEqual(self.client.post("/api/eitaa/submit", json=dict(POST, text="متن جدید")).get_json()["status"], "updated")

    def test_ea05_empty_post_not_stored(self):
        body = dict(POST, text="", media_title="", media_duration="", media_size="", post_type="text")
        self.assertEqual(self.client.post("/api/eitaa/submit", json=body).get_json()["status"], "empty")
        db = sqlite3.connect(server.DB_PATH)
        n = db.execute("SELECT COUNT(*) FROM eitaa_posts").fetchone()[0]
        db.close()
        self.assertEqual(n, 0)
```

- [ ] **Step 2: Run tests to verify they fail**

Run (from `backend/`): `..\.venv\Scripts\python.exe -m unittest test_eitaa -v`
Expected: FAIL/ERROR — `AttributeError: module 'server' has no attribute 'ensure_eitaa_schema'` (and 404s).

- [ ] **Step 3: Implement in `backend/server.py`**

Insert a new section before `from sites import register_site_routes`:

```
# ═══════════════════════════════════════
# EITAA CHANNEL CRAWL (additive; same family as /api/khamenei/*)
# ═══════════════════════════════════════
```

- `ensure_eitaa_schema(db)`: the three statements from Interfaces (no migrations needed — brand-new tables).
- `EITAA_CHANNEL_FIELDS` / `EITAA_POST_FIELDS`: tuple constants listing the 8 channel keys and 11 post keys — used to build canonical dicts (filter incoming JSON to these keys so unknown keys never leak into hashes).
- `_eitaa_save_channel(db, data) -> dict`: build canonical channel dict (counts as `int(v or 0)`, strings `str(v or "")`); compare against `json.dumps(existing_row_as_dict, sort_keys=True, ensure_ascii=False)`; insert / update / skip.
- `_eitaa_save_post(db, post) -> dict`:
  - empty check first → `{"status": "empty", ...}`.
  - canonical 11-field dict (views coerced `int(v or 0)`, others `str(v or "")` except `post_number`/`views` ints); `chash = content_hash({k: v for k, v in canon.items() if k != "views"})`.
  - existing row by `post_id`: same hash → `skipped`; else UPDATE all columns + `crawled_at=datetime('now')` → `updated`; else INSERT → `inserted`.
- Routes (each: `db = get_db(); ensure_eitaa_schema(db); ...; db.commit(); jsonify(...)`):
  - `POST /api/eitaa/channel` → `_eitaa_save_channel`.
  - `POST /api/eitaa/submit` → `_eitaa_save_post`, then frontier bookkeeping for `page_url` / `next_url` exactly as in Interfaces.
- Add `ensure_eitaa_schema(db)` in `__main__` after `ensure_khamenei_schema(db)`.

- [ ] **Step 4: Run tests to verify they pass**

Run (from `backend/`): `..\.venv\Scripts\python.exe -m unittest test_eitaa -v`
Expected: 5 tests PASS (EA-01..EA-05).

- [ ] **Step 5: Commit**

```bash
git add backend/server.py backend/test_eitaa.py
git commit -m "feat(eitaa): additive schema + channel/post submit endpoints (EA-01..05)"
```

---

### Task 2: Backend — seed / pending / crawl-status / stats / posts / reset

**Files:**
- Modify: `backend/server.py` (extend the EITAA section from Task 1)
- Test: `backend/test_eitaa.py` (extend same class)

**Interfaces:**
- Consumes: Task 1 (schema, `PAGE1`/`PAGE2`/`CHANNEL`/`POST` fixtures in the test file).
- Produces:
  - `POST /api/eitaa/seed` — body `{"channel": str}`; 400 without channel; inserts first page `https://eitaa.com/<channel>` as `crawl_queue` row `page_type='eitaa_page'`, `site='eitaa'`, `status='pending'` if not already present → `{"added": 0|1, "url": str}`.
  - `GET /api/eitaa/pending` → `{"urls": [str], "count": int}` — all `eitaa_page` pending rows, `ORDER BY id ASC`.
  - `GET /api/eitaa/crawl-status?channel=<chan>` → `{"channel_registered": bool, "posts": int, "max_post_number": int, "pending": int, "last_crawled_at": str|null}`; `posts`/`max_post_number` filtered by `channel` when the param is present.
  - `GET /api/eitaa/stats` → `{"channels": int, "posts": int, "chars": int, "last_crawled_at": str|null, "by_type": {post_type: int}}` — all real counters.
  - `GET /api/eitaa/posts?channel=&limit=&offset=` → `{"total": int, "posts": [row dicts], "limit": int, "offset": int}`; `ORDER BY post_number ASC` (whitelist), `LIMIT ? OFFSET ?` (default limit 50, max 200); `channel` filter optional.
  - `POST /api/eitaa/reset` → deletes `eitaa_posts`, `eitaa_channels`, and `crawl_queue` rows with `page_type='eitaa_page'` → `{"deleted_posts": int, "deleted_channels": int, "deleted_queue": int}`.

- [ ] **Step 1: Write the failing tests** — append to `EitaaApiTests`:

```python
    def _post(self, i, text="تست"):
        return self.client.post("/api/eitaa/submit", json=dict(
            POST, post_id=f"c/{i}", channel="c", post_number=i,
            url=f"https://eitaa.com/c/{i}", post_type="text",
            media_title="", media_duration="", media_size="", text=text))

    def test_ea06_stats(self):
        self.client.post("/api/eitaa/channel", json=CHANNEL)
        self.client.post("/api/eitaa/submit", json=POST)
        self._post(3, "متن ساده")
        s = self.client.get("/api/eitaa/stats").get_json()
        self.assertEqual(s["channels"], 1)
        self.assertEqual(s["posts"], 2)
        self.assertEqual(s["by_type"], {"audio": 1, "text": 1})
        self.assertGreater(s["chars"], 0)

    def test_ea07_posts_listing_pagination(self):
        for i in range(1, 16):
            self._post(i, f"t{i}")
        p1 = self.client.get("/api/eitaa/posts?channel=c&limit=10&offset=0").get_json()
        self.assertEqual(p1["total"], 15)
        self.assertEqual([p["post_number"] for p in p1["posts"]], list(range(1, 11)))
        p2 = self.client.get("/api/eitaa/posts?channel=c&limit=10&offset=10").get_json()
        self.assertEqual([p["post_number"] for p in p2["posts"]], list(range(11, 16)))

    def test_ea08_frontier_and_reset(self):
        self.client.post("/api/eitaa/channel", json=CHANNEL)
        self.assertEqual(self.client.post("/api/eitaa/seed", json={"channel": "sharabebeheshti"}).get_json()["added"], 1)
        self.assertEqual(self.client.post("/api/eitaa/seed", json={"channel": "sharabebeheshti"}).get_json()["added"], 0)
        self.assertEqual(self.client.get("/api/eitaa/pending").get_json()["urls"], [PAGE1])
        # a post submitted from PAGE1 carries the frontier to PAGE2
        self.client.post("/api/eitaa/submit", json=dict(POST, page_url=PAGE1, next_url=PAGE2))
        self.assertEqual(self.client.get("/api/eitaa/pending").get_json()["urls"], [PAGE2])
        st = self.client.get("/api/eitaa/crawl-status?channel=sharabebeheshti").get_json()
        self.assertTrue(st["channel_registered"])
        self.assertEqual(st["posts"], 1)
        self.assertEqual(st["max_post_number"], 2)
        self.assertEqual(st["pending"], 1)
        r = self.client.post("/api/eitaa/reset").get_json()
        self.assertEqual(r["deleted_posts"], 1)
        self.assertEqual(r["deleted_channels"], 1)
        self.assertEqual(self.client.get("/api/eitaa/pending").get_json()["count"], 0)
        self.assertEqual(self.client.get("/api/eitaa/posts").get_json()["total"], 0)
```

- [ ] **Step 2: Run tests to verify they fail**

Run (from `backend/`): `..\.venv\Scripts\python.exe -m unittest test_eitaa -v`
Expected: EA-01..05 PASS; EA-06..08 FAIL with 404.

- [ ] **Step 3: Implement the six routes in `backend/server.py`**

Follow the khamenei handlers' shape exactly (`db = get_db(); ensure_eitaa_schema(db); ...`). `posts` listing: clamp `limit` to `[1, 200]`, `offset >= 0`; `SELECT * FROM eitaa_posts` + optional `WHERE channel=?`; return `[dict(r) for r in rows]`.

- [ ] **Step 4: Run tests to verify they pass**

Run (from `backend/`): `..\.venv\Scripts\python.exe -m unittest test_eitaa -v`
Expected: 8 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/server.py backend/test_eitaa.py
git commit -m "feat(eitaa): frontier queue + status/stats/listing/reset endpoints (EA-06..08)"
```

---

### Task 3: Scraper — parsing (`corpus/scrape_eitaa.py`) + real-page fixture

**Files:**
- Create: `corpus/scrape_eitaa.py`
- Create: `corpus/fixtures/eitaa_sharabebeheshti_page1.html` (ALREADY fetched) + `corpus/fixtures/eitaa_sharabebeheshti_oldest.html` (fetch `?before=13` — the terminal page with the pinned post 1)
- Test: `corpus/test_scrape_eitaa.py`

**Interfaces:**
- Produces (module-level, all pure except where noted):
  - `BASE = "https://eitaa.com"`
  - `channel_url(username, before=None) -> str` — `https://eitaa.com/<u>` or `...?before=N`.
  - `extract_username(arg) -> str` — accepts bare username or any `eitaa.com/<user>` URL.
  - `parse_channel(html) -> dict` — keys `username, display_name, description, followers_count, photos_count, videos_count, files_count, photo_url`; missing → `""` / `0`. `display_name` from the header_title div (strip inner tags); `username` from the header_username `<a href="/<chan>">`; counters by `counter_value` `data-count` + label substring in the sibling `counter_type`.
  - `parse_posts(html) -> list[dict]` — post dicts in DOM order with the exact 11-field contract of `POST /api/eitaa/submit` (Task 1 Interfaces); `views` `0` when absent; `media_*` `""` when absent; `post_type` ∈ `text|audio|video|image|file|pinned|service`.
  - `next_page_url(html) -> str` — absolute URL or `""`; from `a.eme_messages_more` (`data-before="N"` attr, else `before=N` in its href); drop the trailing `q=` param. (No `<link rel="next">` exists in current markup.)
  - `strip_tags(html) -> str` — `<br>`/`</p>`/`</div>` → `\n`, tags removed, `html.unescape`, per-line strip, empty lines dropped, joined with `\n`.
  - `submit_channel(session, channel, backend_url="http://127.0.0.1:5055") -> dict`
  - `submit_post(session, post, backend_url="http://127.0.0.1:5055") -> dict`
  - `seed(session, channel, backend_url="http://127.0.0.1:5055") -> dict`
  - `_get(session, url, retries=3, sleep=time.sleep) -> str | None` — 200 → text; 404 → `""`; other status/exception retried with `2*(attempt+1)s` backoff; final failure → `None`.
  - `_session` — same robust pattern as `scrape_khamenei.py` (`trust_env=False`, browser UA/Accept-Language headers, `verify=False`).
- Fixture: `corpus/fixtures/eitaa_sharabebeheshti_page1.html` = the **live page captured 2026-11-25** from `https://eitaa.com/sharabebeheshti` (86,895 chars): the 12 **newest** posts `sharabebeheshti/1303` … `/1314` (audio posts), header with counters 683/332/40/4, more anchor `data-before="1303"` ("مطالب قبلی"). The pinned/`service_message` post 1 lives on the oldest page (reached via `?before=13`, no more anchor) — covered by a synthetic block in T-03, not the fixture.

Parser decisions (fixed here, tests pin them):
- Post block boundary: opening tag regex `<div class="(etme_widget_message [^"]*)" data-post="([^"]+)"[^>]*>`; block runs from the tag start to the next such tag (or the `etme_widget_message_centered` div, or end of string).
- `post_type`: `service_message` in the block's class list → `"pinned"` if the block contains "سنجاق" else `"service"`; else document icon class `audio|video|image|file` when a `etme_widget_message_document_wrap` block exists; else `"text"`.
- Media fields from inside the document wrap: icon `document_icon accent_bg (\w+)`; title `.etme_widget_message_document_title` first non-empty text; duration `<time>([^<]+)</time>`; size from the span following "حجم:" (`حجم:\s*([^<]+?)\s*</span>`).
- `post_date`: first `<time datetime="([^"]+)"` in the block (the duration `<time>` has no `datetime` attr, so it never matches).
- `url` = `f"{BASE}/{post_id}"`.
- Counter labels matched by substring (ZWNJ-safe): "دنبال"→followers, "عکس"→photos, "ویدیو"→videos, "فایل"→files.

- [ ] **Step 1: Create the fixture file**

ALREADY DONE (fetched live 2026-11-25, 86,895 chars, UTF-8): `corpus/fixtures/eitaa_sharabebeheshti_page1.html` (sanity: `data-post="sharabebeheshti/1303"` … `/1314`, `data-before="1303"`, `counter_value" data-count="683"`). THEN fetch `https://eitaa.com/sharabebeheshti?before=13` to `corpus/fixtures/eitaa_sharabebeheshti_oldest.html` (UTF-8; sanity: `data-post="sharabebeheshti/1"` … `/12`, **no** `eme_messages_more` anchor, post 1 has class `service_message`).

- [ ] **Step 2: Write the failing tests** — create `corpus/test_scrape_eitaa.py` (pattern: `corpus/test_scrape_khamenei.py`, repo-root run):

```python
"""Tests for corpus/scrape_eitaa.py — pure parsing, no network."""
import os
import unittest

import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import scrape_eitaa as es

FIXTURE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "fixtures", "eitaa_sharabebeheshti_page1.html")
with open(FIXTURE, encoding="utf-8") as _f:
    PAGE1_HTML = _f.read()
OLDEST = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                      "fixtures", "eitaa_sharabebeheshti_oldest.html")
with open(OLDEST, encoding="utf-8") as _f:
    OLDEST_HTML = _f.read()

# synthetic building blocks for variant tests (T-03)
def msg_block(post_id, classes, inner):
    return f'<div class="etme_widget_message {classes} js-widget_message" data-post="{post_id}">{inner}</div>'

DOC = (
    '<a class="etme_widget_message_document_wrap" href="/chan/{n}">'
    '<div class="etme_widget_message_document_icon accent_bg {kind}"></div>'
    '<div class="etme_widget_message_document">'
    '<div class="etme_widget_message_document_title accent_color" dir="auto">{title}</div>'
    '<div class="etme_widget_message_document_extra" dir="auto"> زمان: <time>{dur}</time>'
    '<span style="padding: 0 0 0 5px">حجم: {size}</span></div></div></a>'
)
TEXT = '<div class="etme_widget_message_text js-message_text" dir="auto">{body}</div>'
FOOTER = '<div class="etme_widget_message_footer compact js-message_footer"><div class="etme_widget_message_info short js-message_info"><span class="etme_widget_message_views" data-count="{views}">1</span><span class="etme_widget_message_meta"><a class="etme_widget_message_date" href="/chan/{n}"><time datetime="{date}" class="time">05:33</time></a></span></div></div>'


class ParseChannelTests(unittest.TestCase):
    def test_t01_parse_channel_real_page(self):
        ch = es.parse_channel(PAGE1_HTML)
        self.assertEqual(ch["username"], "sharabebeheshti")
        self.assertEqual(ch["display_name"], "موسسه شراب بهشتی")
        self.assertEqual((ch["followers_count"], ch["photos_count"],
                          ch["videos_count"], ch["files_count"]), (683, 332, 40, 4))
        self.assertIn("سایت رسمی", ch["description"])
        self.assertTrue(ch["photo_url"].startswith("/download_"))

    def test_t04_channel_url(self):
        self.assertEqual(es.channel_url("sharabebeheshti"), "https://eitaa.com/sharabebeheshti")
        self.assertEqual(es.channel_url("sharabebeheshti", 1303), "https://eitaa.com/sharabebeheshti?before=1303")
        self.assertEqual(es.extract_username("https://eitaa.com/sharabebeheshti"), "sharabebeheshti")
        self.assertEqual(es.extract_username("sharabebeheshti"), "sharabebeheshti")


class ParsePostsTests(unittest.TestCase):
    def test_t02_parse_posts_real_page(self):
        # fixture = the 12 NEWEST posts of the live channel (1303..1314, DOM order)
        posts = es.parse_posts(PAGE1_HTML)
        self.assertEqual(len(posts), 12)
        self.assertEqual(posts[0]["post_id"], "sharabebeheshti/1303")
        self.assertEqual(posts[-1]["post_id"], "sharabebeheshti/1314")
        t0 = posts[0]  # post 1303: plain text (caption links another channel)
        self.assertEqual(t0["post_type"], "text")
        self.assertEqual(t0["media_title"], "")
        self.assertEqual(t0["views"], 1)
        self.assertEqual(t0["url"], "https://eitaa.com/sharabebeheshti/1303")
        self.assertTrue(t0["post_date"].startswith("2026-"))
        self.assertEqual(t0["channel"], "sharabebeheshti")
        self.assertEqual(t0["post_number"], 1303)
        a = posts[6]  # post 1309: audio .mp3; caption references the channel
        self.assertEqual(a["post_id"], "sharabebeheshti/1309")
        self.assertEqual(a["post_type"], "audio")
        self.assertTrue(a["media_title"].endswith(".mp3"))
        self.assertRegex(a["media_duration"], r"^\d+:\d{2}$")
        self.assertRegex(a["media_size"], r"^\d+(?:\.\d+)?[MKG]$")
        self.assertIn("https://eitaa.com/sharabebeheshti", a["text"])

    def test_t03_parse_posts_media_variants(self):
        video = msg_block("chan/10", "text_not_supported_wrap",
                          DOC.format(n=10, kind="video", title="x.mp4", dur="1:00", size="5M")
                          + TEXT.format(body="کپشن ویدیو")
                          + FOOTER.format(n=10, views=7, date="2023-06-01T10:00:00+00:00"))
        photo = msg_block("chan/11", "text_not_supported_wrap",
                          DOC.format(n=11, kind="image", title="photo.jpg", dur="", size="")
                          + TEXT.format(body="عکس")
                          + FOOTER.format(n=11, views=3, date="2023-06-02T10:00:00+00:00"))
        # photo document: <time> tag omitted entirely must yield "" not crash
        photo = photo.replace("<time></time>", "")
        # pinned/service post (live markup of post 1: service_message class + "سنجاق پیغام")
        pinned = msg_block("chan/1", "text_not_supported_wrap service_message",
                           TEXT.format(body="سنجاق پیغام\nآگهی")
                           + FOOTER.format(n=1, views=0, date="2023-05-05T06:34:41+00:00"))
        plain = msg_block("chan/12", "text_not_supported_wrap",
                          TEXT.format(body="A & B<br>خط دوم")
                          + FOOTER.format(n=12, views=0, date="2023-06-03T10:00:00+00:00"))
        html = "<html><body>" + video + photo + pinned + plain + "</body></html>"
        posts = es.parse_posts(html)
        self.assertEqual([p["post_type"] for p in posts], ["video", "image", "pinned", "text"])
        self.assertEqual(posts[0]["media_title"], "x.mp4")
        self.assertEqual(posts[0]["views"], 7)
        self.assertEqual(posts[1]["media_title"], "photo.jpg")
        self.assertEqual(posts[1]["media_duration"], "")
        self.assertEqual(posts[1]["media_size"], "")
        self.assertEqual(posts[2]["post_number"], 1)
        self.assertEqual(posts[2]["post_date"], "2023-05-05T06:34:41+00:00")
        self.assertEqual(posts[3]["text"], "A & B\nخط دوم")

    def test_t05_parse_posts_empty_page(self):
        self.assertEqual(es.parse_posts("<html><body><h1>404</h1></body></html>"), [])
        self.assertEqual(es.parse_posts(""), [])

    def test_t03b_next_page_url_and_terminal(self):
        self.assertEqual(es.next_page_url(PAGE1_HTML), "https://eitaa.com/sharabebeheshti?before=1303")
        # oldest page: no more anchor → "" (terminal stop); it holds the pinned post 1
        self.assertEqual(es.next_page_url(OLDEST_HTML), "")
        posts = es.parse_posts(OLDEST_HTML)
        self.assertEqual([p["post_id"] for p in posts][:3],
                         ["sharabebeheshti/1", "sharabebeheshti/2", "sharabebeheshti/3"])
        self.assertEqual(posts[0]["post_type"], "pinned")
        self.assertEqual(es.next_page_url("<html><body></body></html>"), "")
```

Note on T-03: when `dur`/`size` are empty strings the synthetic `DOC` produces `<time></time>` and an empty size span; the photo case then has `<time></time>` removed entirely — the parser must treat a missing duration `<time>` as `""`.

- [ ] **Step 3: Run tests to verify they fail**

Run (from repo root): `.venv\Scripts\python.exe -m unittest corpus.test_scrape_eitaa -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scrape_eitaa'`.

- [ ] **Step 4: Implement the parsing half of `corpus/scrape_eitaa.py`**

Module header docstring (site facts + run instructions, khamenei style), then the functions per Interfaces. `_post_json(session, url, payload) -> dict` helper: `session.post(url, json=payload, timeout=30).json()` wrapped in try/except → `{"status": "error", "error": str(e)}`.

- [ ] **Step 5: Run tests to verify they pass**

Run (from repo root): `.venv\Scripts\python.exe -m unittest corpus.test_scrape_eitaa -v`
Expected: 6 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add corpus/scrape_eitaa.py corpus/fixtures/eitaa_sharabebeheshti_page1.html corpus/fixtures/eitaa_sharabebeheshti_oldest.html corpus/test_scrape_eitaa.py
git commit -m "feat(eitaa): scraper parsing (channel/posts/next-page) + live-page fixture (T-01..T-05)"
```

---

### Task 4: Scraper — crawl walk + CLI, then full regression + report

**Files:**
- Modify: `corpus/scrape_eitaa.py` (append crawler + CLI)
- Modify: `corpus/test_scrape_eitaa.py` (append crawler tests)
- Create: `docs/EITAA-CHANNEL-CRAWL-REPORT.md`
- Modify: `AGENTS.md` (roadmap table: add one row)

**Interfaces:**
- Consumes: Task 1–2 endpoints (`/api/eitaa/channel|submit|seed`), Task 3 parsing.
- Produces:
  - `crawl_channel(username, backend="http://127.0.0.1:5055", session=None, max_pages=0, max_posts=0, delay=0.0, retries=3, sleep=None) -> dict` with keys `username, pages, posts, inserted, updated, skipped, empty, errors`. Walk: GET page 1 (fail → `errors=1`, stop) → `submit_channel` + `seed` → per page: `parse_posts`, `next_page_url`, submit every post with `page_url=<this page>` and `next_url=<next page or "">`; stop when no next URL, or 2 consecutive empty pages, or `max_pages` reached (checked after a page), or `max_posts` reached (checked after a page); `sleep(delay)` between pages.
  - CLI (`if __name__ == "__main__":`): `--channel` (required; username or URL), `--backend` (default `http://127.0.0.1:5055`), `--max-pages 0`, `--max-posts 0`, `--delay 2.0`, `--parse-only` (fetch page 1, print `{"channel": ..., "posts": [...]}` JSON, no backend).
  - Test doubles: `FakeResponse(text, status_code=200)` with `.json()`; `FakeSession(pages)` recording `("GET", url)` / `("POST", url, payload)` and answering POSTs with `{"status": "inserted"}`; `ErrorSession` whose `get` always raises `RuntimeError`.

- [ ] **Step 1: Write the failing tests** — append to `corpus/test_scrape_eitaa.py`:

```python
class FakeResponse:
    def __init__(self, text="", status_code=200):
        self.text = text
        self.status_code = status_code

    def json(self):
        import json as json_mod
        return json_mod.loads(self.text) if self.text else {}


class FakeSession:
    def __init__(self, pages=None):
        self.pages = dict(pages or {})
        self.calls = []

    def get(self, url, timeout=None):
        self.calls.append(("GET", url))
        return FakeResponse(self.pages.get(url, ""), 200)

    def post(self, url, json=None, timeout=None):
        self.calls.append(("POST", url, json))
        import json as json_mod
        return FakeResponse(json_mod.dumps({"status": "inserted"}), 200)


class ErrorSession:
    def get(self, url, timeout=None):
        raise RuntimeError("boom")


def synth_page(user, ids, before=None):
    # latest-first page: ids in DOM order (oldest of the page first, like the live site)
    parts = [msg_block(f"{user}/{n}", "text_not_supported_wrap",
                       TEXT.format(body=f"کپشن {n}")
                       + FOOTER.format(n=n, views=1, date="2023-05-14T05:33:00+00:00"))
              for n in ids]
    parts.append('<div class="etme_widget_message_centered js-messages_more_wrap" dir="auto">'
                 + (f'<a href="/{user}?before={before}&q=" class="eme_messages_more js-messages_more" data-before="{before}"><span>مطالب قبلی</span></a>' if before else "")
                 + "</div>")
    return f'<main class="etme_main" data-url="/{user}"><section>' + "".join(parts) + "</section></main>"


class CrawlChannelTests(unittest.TestCase):
    def _two_page_session(self):
        return FakeSession({
            "https://eitaa.com/chan": synth_page("chan", [1303, 1304, 1305], before=1303),
            "https://eitaa.com/chan?before=1303": synth_page("chan", [1291, 1292]),
        })

    def test_t07_crawl_two_pages_frontier(self):
        sess = self._two_page_session()
        res = es.crawl_channel("chan", session=sess, delay=0, sleep=lambda s: None)
        self.assertEqual((res["pages"], res["posts"], res["inserted"]), (2, 5, 5))
        subs = [c for c in sess.calls if c[0] == "POST" and c[1].endswith("/api/eitaa/submit")]
        self.assertEqual(len(subs), 5)
        self.assertEqual(subs[2][2]["page_url"], "https://eitaa.com/chan")
        self.assertEqual(subs[2][2]["next_url"], "https://eitaa.com/chan?before=1303")
        self.assertEqual(subs[-1][2]["page_url"], "https://eitaa.com/chan?before=1303")
        self.assertEqual(subs[-1][2]["next_url"], "")
        api_calls = [c for c in sess.calls if c[0] == "POST"]
        self.assertTrue(any(c[1].endswith("/api/eitaa/channel") for c in api_calls))
        self.assertTrue(any(c[1].endswith("/api/eitaa/seed") for c in api_calls))

    def test_t08_crawl_stops_on_network_error(self):
        res = es.crawl_channel("chan", session=ErrorSession(), delay=0,
                               sleep=lambda s: None, retries=2)
        self.assertEqual(res["errors"], 1)
        self.assertEqual(res["posts"], 0)

    def test_t09_crawl_stops_on_two_empty_pages(self):
        sess = FakeSession({
            "https://eitaa.com/chan": synth_page("chan", [], before=12),
            "https://eitaa.com/chan?before=12": synth_page("chan", [], before=24),
            "https://eitaa.com/chan?before=24": synth_page("chan", [1]),
        })
        res = es.crawl_channel("chan", session=sess, delay=0, sleep=lambda s: None)
        self.assertEqual(res["pages"], 2)
        self.assertEqual(res["posts"], 0)
        self.assertEqual([c[1] for c in sess.calls if c[0] == "GET"],
                         ["https://eitaa.com/chan", "https://eitaa.com/chan?before=12"])

    def test_t10_max_pages(self):
        res = es.crawl_channel("chan", session=self._two_page_session(),
                               delay=0, sleep=lambda s: None, max_pages=1)
        self.assertEqual(res["pages"], 1)
        self.assertEqual(res["posts"], 3)
```

- [ ] **Step 2: Run tests to verify they fail**

Run (from repo root): `.venv\Scripts\python.exe -m unittest corpus.test_scrape_eitaa -v`
Expected: T-07..T-10 FAIL with `AttributeError: ... has no attribute 'crawl_channel'`.

- [ ] **Step 3: Implement `crawl_channel` + `_get` + CLI in `corpus/scrape_eitaa.py`**

Per Interfaces. Progress prints like `scrape_khamenei.py` (one line per page: `Page N: X posts (next=... )`), final summary `print(json.dumps(res, ensure_ascii=False))`.

- [ ] **Step 4: Run scraper tests to verify they pass**

Run (from repo root): `.venv\Scripts\python.exe -m unittest corpus.test_scrape_eitaa -v`
Expected: 10 tests PASS.

- [ ] **Step 5: Run the full backend regression**

Run (from `backend/`):
```
..\.venv\Scripts\python.exe -m unittest test_api test_projects test_dashboard test_knowledge_api test_word_factory test_dump test_work_registry test_queue test_corpus_builder test_studio_api test_api_contract test_eitaa -v
```
Baseline (measured 2026-11-25 on clean HEAD `f150254`): 248 tests, **18 pre-existing red** — `test_studio_api.test_s07` is a race (worker finishes the 1-doc job before the 2nd POST → 409 `no_files_to_process` instead of resubmit-200) and its leaked worker connection makes every later `reset_db()` hit `PermissionError [WinError 32]` (Windows file lock), cascading into 17 errors across `test_studio_api` (S-08..S-11) and `test_api_contract` (CT-03..CT-05). These are unrelated to Eitaa and are NOT fixed in this mission — just called out in the report.

Expected: 248 pre-existing (230 green / 18 known-red) + 8 new EA + 10 new T green, 0 new failures.

- [ ] **Step 6: Write the report** — create `docs/EITAA-CHANNEL-CRAWL-REPORT.md`:
  وضعیت قبل / طراحی (link to spec) / فایل‌ها و endpointها / نتایج تست (real numbers) / نحوه اجرای واقعی (`python corpus\scrape_eitaa.py --channel sharabebeheshti`) / موارد باقی‌مانده (media download, deploy, dashboard card) / بدون deploy.

- [ ] **Step 7: Update `AGENTS.md`** — add one roadmap row (next to PCM-EXT-09):
  `PCM-EITAA` کراول کانال ایتا: `corpus/scrape_eitaa.py` + جدول‌های `eitaa_channels`/`eitaa_posts` + ۸ endpoint `/api/eitaa/*` + ۱۸ تست (8 EA + 10 T) — ✅ (بدون deploy؛ سند: docs/EITAA-CHANNEL-CRAWL-REPORT.md). Also add `test_eitaa` to the test-suite list in §4 with its count.

- [ ] **Step 8: Commit**

```bash
git add corpus/scrape_eitaa.py corpus/test_scrape_eitaa.py docs/EITAA-CHANNEL-CRAWL-REPORT.md AGENTS.md
git commit -m "feat(eitaa): crawl walk + CLI, full regression green, report (T-07..T-10)"
```

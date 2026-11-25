# Eitaa Channel Crawl — post-by-post registration (design)

Date: 2026-11-25 · Scope: `corpus/` + `backend/` · Status: DRAFT (awaiting owner approval)

## 1. Intent / why

Eitaa channel pages (e.g. `https://eitaa.com/sharabebeheshti`) are a new crawl
target. The owner wants the **channel registered once** (name, username,
description, counters) and then **crawled post-by-post** through the site's
pagination, with every post stored in the backend database — so the existing
JSONL → Dump `d-1` → corpus / registry pipeline can later be built from the same
data ("بعدا طبق همون جیسون و کورپوس و رگ ساخته بشه").

Chosen scope (owner decision, 2026-11-25): **text + media catalog** — each post
stores its caption/text plus media metadata (type, file title, duration, size).
Actual media file download is **not** in scope (Eitaa download links are
tokenized per-session; that is a separate future mission).

## 2. What exists today (recon)

- `corpus/scrape_khamenei.py` — proven pattern: standalone Python scraper,
  browser-like `requests` session (`trust_env=False`, verify off), per-item
  extraction via regex on server-rendered HTML, submission to a dedicated
  backend endpoint, `content_hash` dedup server-side, resume via pending queue
  + `mark-done`, `--max`/`--delay` limits, argparse CLI, small unittest file.
- `backend/server.py` — `khamenei_speeches` table + `ensure_khamenei_schema(db)`
  (`CREATE TABLE IF NOT EXISTS` + additive `ALTER TABLE ... ADD COLUMN`
  migrations + backfill), `content_hash()` helper (`server.py:169`),
  `crawl_queue` table used as the resume queue (`page_type='khamenei_speech'`),
  endpoint family: `/api/khamenei/{submit,seed,pending,mark-done,crawl-status,
  stats,recent,reset}`.
- Eitaa page facts (from the provided live sample, server-rendered — no JS
  needed):
  - Pagination (verified live 2026-11-25, latest-first): page 1 = `/chan` (no
    param, 12 newest posts); next (older) page via the bottom anchor
    `a.eme_messages_more[data-before="N"]` (`?before=N&q=`, "مطالب قبلی") —
    **no `<link rel="next">` exists**. The oldest page has no such anchor →
    terminal stop. ~12 posts per page (channel currently at 1314 posts).
  - Post identity: `div.js-widget_message[data-post="chan/N"]` — unique
    per-post key `N` (stable, monotonic).
  - Per post: `div.js-message_text` (caption, `dir` rtl/lt), media block
    `a.etme_widget_message_document_wrap` with icon class
    `audio|video|image|file`, `.etme_widget_message_document_title` (file
    name), `time` (duration), size span; pinned posts are
    `service_message`/class `text_not_supported_wrap` with "سنجاق پیغام";
    date: `<time datetime="2023-05-14T05:33:18+00:00">`; views:
    `span.etme_widget_message_views[data-count]`.
  - Channel header: `.etme_channel_info_header_title`,
    `.etme_channel_info_header_username`, `.etme_channel_info_description`,
    `.etme_channel_info_counter[data-count]` (followers/photos/videos/files),
    photo `img` in `.etme_page_photo_image`.
  - Media file URL is **not** in the list page (the document anchor points to
    the post detail page). Catalog stores metadata only; download-URL
    resolution = future mission.

## 3. Approaches considered

| # | Approach | Trade-off | Verdict |
|---|----------|-----------|---------|
| A | Standalone Python scraper + dedicated backend endpoints (khamenei pattern) | New table + ~6 small endpoints; but zero new infra, reuses proven resume/dedup code, server-rendered pages need no browser | **Chosen** (owner-approved) |
| B | Chrome extension crawl (existing project/point machinery) | Reuses UI, but the extension pipeline is thesaurus-shaped (items/definitions), lease/heartbeat is fragile for multi-page channel walks, needs a human-driven browser | Rejected |
| C | JSONL only, no DB | Cheapest, but owner explicitly wants posts in the DB so corpus/registry can be built later | Rejected |

## 4. Design (Method A)

### 4.1 Backend — schema (additive; local `thesaurus.db`, never a production
ALTER on s52)

New tables created by `ensure_eitaa_schema(db)` (same idempotent style as
`ensure_khamenei_schema`):

```sql
CREATE TABLE IF NOT EXISTS eitaa_channels (
    username TEXT PRIMARY KEY,          -- e.g. 'sharabebeheshti'
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
    post_id TEXT PRIMARY KEY,           -- 'sharabebeheshti/12'
    channel TEXT NOT NULL,
    post_number INTEGER,
    post_type TEXT,                     -- 'text'|'audio'|'video'|'image'|'file'|'pinned'|'service'
    media_title TEXT,                   -- file name, e.g. 'Sharab-e-Beheshti01 - Vaghee.mp3'
    media_duration TEXT,                -- '17:50'
    media_size TEXT,                    -- '17.2M'
    text TEXT,                          -- caption (raw, no HTML)
    post_date TEXT,                     -- ISO 8601 from <time datetime>
    views INTEGER,
    url TEXT,                           -- https://eitaa.com/<channel>/<N>
    full_data TEXT,                     -- full post JSON (for JSONL/Dump later)
    content_hash TEXT,
    char_count INTEGER,
    crawled_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_eitaa_posts_channel ON eitaa_posts(channel, post_number);
```

Dedup/update rule (mirrors `_phase2_save_khamenei`): key = `post_id`;
`content_hash` over canonical post JSON **excluding the volatile `views`
counter** (view counts change between crawls; including them would make every
re-crawl an "update" storm); same hash → `skipped`, different hash → `UPDATE`
(re-setting fields, `crawled_at=now`), new → `INSERT`. Empty text **and** no
media metadata → status `empty` (not stored).

### 4.2 Backend — endpoints (extension write APIs stay open, AGENTS rule 6;
no auth, same family as `/api/khamenei/*`)

| Endpoint | Purpose |
|----------|---------|
| `POST /api/eitaa/channel` | Upsert `eitaa_channels` (channel registered once; updates `updated_at` + counters on re-crawl) |
| `POST /api/eitaa/submit` | Upsert one post (JSON body = parsed post); marks its `crawl_queue` row done |
| `POST /api/eitaa/seed` | Initialize the crawl frontier for a channel: insert the first page URL `https://eitaa.com/<chan>` as `page_type='eitaa_page'` pending (skip if already in queue) |
| `GET /api/eitaa/pending?limit=` | Pending page queue (resume helper, like `/api/khamenei/pending`) |
| `GET /api/eitaa/crawl-status` | counts (channel registered? posts saved? pending pages? complete flag) |
| `GET /api/eitaa/stats` | totals, char sum, last crawled_at, by-type counts |
| `GET /api/eitaa/posts?channel=&limit=&offset=` | paginated post listing (whitelisted `ORDER BY post_number`, `LIMIT/OFFSET` per AGENTS rule 7) — the future JSONL/Dump export source |
| `POST /api/eitaa/reset` | wipe `eitaa_posts`/`eitaa_channels` + queue (for re-crawls) |

All SQL parameterized; `ORDER BY` only from a fixed whitelist.

### 4.3 Scraper — `corpus/scrape_eitaa.py` (standalone, khamenei style)

- Session: same robust pattern (`trust_env=False`, browser headers,
  `verify=False`, 30s timeout, retries with backoff).
- `parse_channel(html)` → channel dict (regex on the header classes).
- `parse_posts(html, username)` → list of post dicts in DOM order; each:
  `post_id` from `data-post`, type from icon class / `service_message`,
  `media_title/duration/size` from the document block, `text` = tag-stripped
  `.js-message_text` (whitespace-normalized, links' text kept), `post_date`
  from `datetime` attr, `views` from `data-count`, `url` absolute, `full_data`
- `crawl_channel(username, backend, max_pages, max_posts, delay)`:
  1. `POST /api/eitaa/channel` (register once).
  2. Loop pages: fetch → parse → submit each post → follow next URL.
  3. Stop when: no next link, or `max_pages`/`max_posts` reached, or two
     consecutive empty pages (safety against server quirks).
  4. `sleep(delay)` (default 2s) between page requests; 2× on error.
  5. Print progress like `scrape_khamenei.py`; final JSON summary
     `{inserted, updated, skipped, empty, errors}`.
- CLI: `--channel sharabebeheshti` (or full URL), `--backend`
  (default `http://127.0.0.1:5055`), `--max-pages`, `--max-posts`,
  `--delay`, `--parse-only` (print parsed JSON of page 1, no backend —
  for offline testing against the saved sample).

### 4.4 Tests

- `backend/test_eitaa.py` (new module, `import pct_test_support` first,
  `reset_db()` in `setUp`; **no** direct `PCT_DB` handling — AGENTS rule 4):
  - EA-01 channel upsert insert/refresh
  - EA-02 post submit → inserted
  - EA-03 same post again → skipped (same hash)
  - EA-04 changed post → updated
  - EA-05 empty post (no text, no media) → empty, not stored
  - EA-06 stats counts + by_type
  - EA-07 posts listing pagination (limit/offset, channel filter)
  - EA-08 crawl-status complete flag + reset
- `corpus/test_scrape_eitaa.py` (pure parser tests, no network): fixture =
  trimmed copy of the provided live page (2–3 posts incl. one pinned + one
  audio) → assert `parse_posts`/`parse_channel`/`next_page_url` output;
  Persian-digit tolerance not needed (dates already ISO ASCII) but size like
  `17.2M` must pass through.
- Full regression: the documented `python -m unittest ...` module list, now
  including the two new modules — everything green before commit.

### 4.5 Non-goals / constraints

- No media file download, no audio transcription.
- No Chrome-extension involvement; no Grafana/dashboard UI (a dashboard card
  can follow later).
- No deploy to s52 in this mission (local work, like PCM-EXT-05/06/08);
  deploy decision comes after a real end-to-end run on `sharabebeheshti`.
- Production DB untouched; all new SQL is `CREATE TABLE IF NOT EXISTS` /
  additive.
- No invented stats: every number in stats endpoints is a real DB counter.

## 5. What's left to the builder

- Exact regexes for the media block and pinned/service variants (sample has
  pinned + audio; handle absent-optional-blocks gracefully → `None` fields).
- Canonical JSON key order for `full_data`/hash stability (sorted keys).
- Whether `seed` enqueues up-front (all page URLs are unknown in advance —
  pages are discovered by walking; so the pending queue holds *visited* page
  URLs marked done + the *current frontier* URL pending). Implementation
  choice: on each page submit, mark that page done and insert the next URL as
  pending (frontier pattern), so `pending` always has ≤1 row for resume.
- `post_date` stays raw ISO (no Jalali conversion — khamenei normalization is
  site-specific).

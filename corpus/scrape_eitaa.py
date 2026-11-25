"""
Eitaa Channel Scraper - Standalone Python Script
Walks an Eitaa channel post-by-post (newest -> oldest) and submits each post
to the toolkit backend (/api/eitaa/*), so the existing JSONL -> Dump -> corpus
-> registry pipeline can be built afterwards.

PAGINATION REALITY (verified live 2026-11-25, sharabebeheshti):
- Page 1 = https://eitaa.com/<channel> -> the 12 NEWEST posts, DOM order
  (oldest of the page first).
- Walk backwards with <a class="eme_messages_more" data-before="N">
  (inside <div class="etme_widget_message_centered js-messages_more_wrap">)
  -> next page = https://eitaa.com/<channel>?before=N (href also carries
  a trailing "q=" param that must be dropped). No <link rel="next">.
- Terminal page (e.g. ?before=13) has NO more anchor and holds the oldest
  posts (post 1 is a pinned/service_message post).
- Posts: <div class="etme_widget_message ... js-widget_message"
  data-post="<channel>/<number>" ...>. Media posts carry an
  etme_widget_message_document_wrap block (icon accent_bg audio|video|
  image|file, title, زمان <time>, حجم span).
- Channel header: etme_channel_info_header_title / _username /
  etme_channel_info_description + counter_value/counter_type spans
  (followers/photo/video/file counts) + etme_page_photo_image img.
"""
import html as html_mod
import json
import os
import re
import sys
import time
import urllib3

import requests

urllib3.disable_warnings()
try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

BASE = "https://eitaa.com"
BACKEND_DEFAULT = "http://127.0.0.1:5055"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,*/*",
    "Accept-Language": "fa,en-US;q=0.9,en;q=0.8",
}

# Robust session: ignore Windows registry/system proxy (broken VPN leftover),
# use browser-like headers so eitaa.com doesn't 403. Same pattern as
# scrape_khamenei.py.
_session = requests.Session()
_session.trust_env = False
_session.headers.update(HEADERS)
_session.verify = False


# ── URL helpers ────────────────────────────────────────────────

def channel_url(username, before=None):
    """https://eitaa.com/<u> or https://eitaa.com/<u>?before=N."""
    u = str(username or "").strip().lstrip("/")
    if before is None:
        return f"{BASE}/{u}"
    return f"{BASE}/{u}?before={before}"


def extract_username(arg):
    """Bare username or any https://eitaa.com/<user>[/...] URL -> username."""
    s = str(arg or "").strip()
    if "eitaa.com/" in s:
        s = s.split("eitaa.com/", 1)[1]
    s = s.split("?", 1)[0].split("#", 1)[0]
    return s.split("/", 1)[0].lstrip("/")


# ── HTML parsing (pure) ────────────────────────────────────────

def strip_tags(html):
    """HTML fragment -> plain text: <br>/</p>/</div> become newlines, all
    other tags removed, entities unescaped, lines stripped, empty lines
    dropped, joined with \\n."""
    s = re.sub(r'<br\s*/?>', '\n', html or '', flags=re.I)
    s = re.sub(r'</p>', '\n', s, flags=re.I)
    s = re.sub(r'</div>', '\n', s, flags=re.I)
    s = re.sub(r'<[^>]+>', '', s)
    s = html_mod.unescape(s)
    lines = [ln.strip() for ln in s.splitlines()]
    return "\n".join(ln for ln in lines if ln)


POST_OPEN_RE = re.compile(
    r'<div class="(etme_widget_message [^"]*)" data-post="([^"]+)"[^>]*>')
CENTERED_RE = re.compile(r'<div class="etme_widget_message_centered[^"]*"')


def _parse_post_block(block, classes, post_id):
    if "service_message" in classes:
        post_type = "pinned" if "سنجاق" in block else "service"
    else:
        icon = re.search(r'etme_widget_message_document_icon accent_bg (\w+)', block)
        post_type = icon.group(1) if icon else "text"

    media_title = media_duration = media_size = ""
    if post_type in ("audio", "video", "image", "file"):
        title = re.search(r'etme_widget_message_document_title[^>]*>([^<]+)<', block)
        if title:
            media_title = title.group(1).strip()
        dur = re.search(r'<time>([^<]+)</time>', block)
        if dur:
            media_duration = dur.group(1).strip()
        size = re.search(r'حجم:\s*([^<]+?)\s*</span>', block)
        if size:
            media_size = size.group(1).strip()

    text = ""
    t = re.search(r'<div class="etme_widget_message_text[^"]*"[^>]*>(.*?)</div>',
                  block, flags=re.S)
    if t:
        text = strip_tags(t.group(1))

    d = re.search(r'<time datetime="([^"]+)"', block)
    post_date = d.group(1) if d else ""
    v = re.search(r'etme_widget_message_views" data-count="(\d+)"', block)
    views = int(v.group(1)) if v else 0

    channel, post_number = "", 0
    if "/" in post_id:
        channel, num = post_id.split("/", 1)
        try:
            post_number = int(num)
        except ValueError:
            post_number = 0

    return {
        "post_id": post_id,
        "channel": channel,
        "post_number": post_number,
        "post_type": post_type,
        "media_title": media_title,
        "media_duration": media_duration,
        "media_size": media_size,
        "text": text,
        "post_date": post_date,
        "views": views,
        "url": f"{BASE}/{post_id}",
    }


def parse_posts(html):
    """All posts of a channel page, DOM order, 11-field submit contract."""
    if not html:
        return []
    matches = list(POST_OPEN_RE.finditer(html))
    if not matches:
        return []
    centered = CENTERED_RE.search(html)
    posts = []
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(html)
        if centered and start < centered.start() < end:
            end = centered.start()
        posts.append(_parse_post_block(html[start:end], m.group(1), m.group(2)))
    return posts


def next_page_url(html):
    """Absolute URL of the older page, or "" on the terminal page."""
    if not html:
        return ""
    m = re.search(r'<a\b[^>]*?\bclass="[^"]*eme_messages_more[^"]*"[^>]*>', html)
    if not m:
        return ""
    tag = m.group(0)
    before = None
    db = re.search(r'data-before="(\d+)"', tag)
    href = re.search(r'href="([^"]+)"', tag)
    if db:
        before = db.group(1)
    elif href and "before=" in href.group(1):
        bm = re.search(r'before=(\d+)', href.group(1))
        if bm:
            before = bm.group(1)
    if before is None:
        return ""
    path = href.group(1).split("?", 1)[0] if href else ""
    if not path:
        mu = re.search(r'data-url="/([^"/]+)"', html)
        if not mu:
            return ""
        path = f"/{mu.group(1)}"
    return f"{BASE}{path}?before={before}"


def parse_channel(html):
    """Channel header -> 8-field registration contract (missing -> ""/0)."""
    ch = {
        "username": "",
        "display_name": "",
        "description": "",
        "followers_count": 0,
        "photos_count": 0,
        "videos_count": 0,
        "files_count": 0,
        "photo_url": "",
    }
    if not html:
        return ch

    u = re.search(r'etme_channel_info_header_username[^>]*>(.*?)</div>', html, flags=re.S)
    if u:
        a = re.search(r'href="/([^"/?]+)"', u.group(1))
        if a:
            ch["username"] = a.group(1)

    t = re.search(r'etme_channel_info_header_title[^>]*>(.*?)</div>', html, flags=re.S)
    if t:
        ch["display_name"] = strip_tags(t.group(1))

    d = re.search(r'etme_channel_info_description[^>]*>(.*?)</div>', html, flags=re.S)
    if d:
        ch["description"] = strip_tags(d.group(1))

    for value, label in re.findall(
            r'<span class="counter_value" data-count="(\d+)"[^>]*>.*?'
            r'<span class="counter_type">([^<]+)</span>', html, flags=re.S):
        if "دنبال" in label:
            ch["followers_count"] = int(value)
        elif "عکس" in label:
            ch["photos_count"] = int(value)
        elif "ویدیو" in label:
            ch["videos_count"] = int(value)
        elif "فایل" in label:
            ch["files_count"] = int(value)

    p = re.search(r'etme_page_photo_image[^>]*>\s*<img src="([^"]+)"', html)
    if p:
        ch["photo_url"] = p.group(1)
    return ch


# ── Backend submission ─────────────────────────────────────────

def _post_json(session, url, payload):
    sess = session or _session
    try:
        r = sess.post(url, json=payload, timeout=30)
        return r.json()
    except Exception as e:
        return {"error": str(e)}


def submit_channel(session, channel, backend_url=BACKEND_DEFAULT):
    """Register/update the channel once (idempotent upsert)."""
    return _post_json(session, f"{backend_url}/api/eitaa/channel", channel)


def submit_post(session, post, backend_url=BACKEND_DEFAULT):
    """Store one post; backend advances the page frontier."""
    return _post_json(session, f"{backend_url}/api/eitaa/submit", post)


def seed(session, channel, backend_url=BACKEND_DEFAULT):
    """Queue the channel's first page (idempotent)."""
    return _post_json(session, f"{backend_url}/api/eitaa/seed",
                      {"channel": channel})


def _get(session, url, retries=3, sleep=time.sleep):
    """GET -> page text. 200 -> text; 404 -> ""; other status/exception
    retried with 2*(attempt+1)s backoff; final failure -> None."""
    sess = session or _session
    for attempt in range(retries + 1):
        try:
            r = sess.get(url, timeout=30)
            if r.status_code == 200:
                return r.text
            if r.status_code == 404:
                return ""
        except Exception:
            pass
        if attempt < retries:
            sleep(2 * (attempt + 1))
    return None

# -*- coding: utf-8 -*-
"""Tasnim Web V1 — HTTP smoke suite (PCM-20.6.4, scope A5).

Stops at the public edge (default http://127.0.0.1:5070) and exercises the
real product over plain HTTP: SSR pages + the 12-endpoint API + static assets.
Stdlib only. Exits 0 when every check passes, 1 otherwise.

Design goals
------------
* No dependency on the tasnim package or on a local read model — the smoke
  talks to a *running* server (the Docker stack on 5070, or the direct Flask
  module on 5071 during local development). The same script, different --base.
* Every check records a status code, byte size, and the markers it matched,
  so the printed table is self-evidencing (no "trust me, it passed").
* A global hidden-context canary scan runs over every HTML body collected:
  the HP-1 isolation invariant ("no hidden summary ever rendered") must hold
  on the live product, not just in the fixture.

Usage
-----
    python -X utf8 tasnim/e2e/smoke.py [--base http://127.0.0.1:5070]
                                       [--label docker-stack]
                                       [--timeout 20]

Exit codes: 0 = all checks PASS, 1 = one or more FAIL (or server unreachable).
"""
import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request

DEFAULT_BASE = "http://127.0.0.1:5070"
API = "/api/v1/tasnim"

# HP-1 invariant: this canary string must NEVER appear in any rendered HTML.
# It is only ever planted in the offline *fixture* (decoy files); the real
# read model does not contain it, so its absence here is a real guarantee.
CANARY = "HIDDEN-CANARY-DO-NOT-LEAK"

# Real v0003 read-model facts the assertions lean on (see Phase 5 probes).
VOLUME_ID = "tasnim_hamta__hamta-2026__vol047"   # 9391 pages, ii 0..55698
SEARCH_Q = "قرآن"                                # 6,760 FTS matches in v0003 (live-verified)
FONT_PATH = "/static/fonts/noto-naskh-arabic.ttf"
CONTENT_SHA = "40f45e0b2c393a65569846aeaac4d45dcee4bd58a7f158b1554adf3755ca78e4"
DB_SHA = "353f413b00467640fabfed267c9a2933a64495f3bfb3bab7e42cd43a54d9c0fd"


def http(base, path, headers=None, timeout=20):
    """Return (status|None, headers-dict, body-bytes). status is None on
    transport failure (connection refused, etc.)."""
    url = base.rstrip("/") + path
    req = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, {k: v for k, v in r.headers.items()}, r.read()
    except urllib.error.HTTPError as e:
        body = e.read() if e.fp else b""
        return e.code, {k: v for k, v in e.headers.items()}, body
    except Exception as e:  # noqa: BLE001
        return None, {}, str(e).encode("utf-8")


class Recorder:
    """Collects check rows + every HTML body for the canary scan."""

    def __init__(self):
        self.rows = []
        self.html_bodies = []

    def add(self, name, ok, status, size, evidence):
        self.rows.append({
            "name": name, "ok": bool(ok), "status": status,
            "size": size, "evidence": evidence,
        })

    def note_html(self, body):
        if body:
            self.html_bodies.append(body)

    def canary_leak(self):
        hits = []
        for i, b in enumerate(self.html_bodies):
            try:
                text = b.decode("utf-8", "replace")
            except Exception:  # noqa: BLE001
                text = ""
            if CANARY in text:
                hits.append(i)
        return hits


# ---------------------------------------------------------------------------
# Individual checks. Each takes (base, rec, timeout) and records one row.
# ---------------------------------------------------------------------------

def check_home(base, rec, timeout):
    st, hd, body = http(base, "/", timeout=timeout)
    rec.note_html(body)
    text = body.decode("utf-8", "replace")
    markers = {
        "lang=fa dir=rtl": 'dir="rtl"' in text and 'lang="fa"' in text,
        "hero title": "hero__title" in text,
        "work name": "تفسیر تسنیم" in text,
        "coverage grid": "coverage-grid" in text,
        "volume grid": "volume-grid" in text,
        "hero search": "hero__search" in text,
        "footer RAG off": "متصل نیست" in text,
    }
    ok = st == 200 and all(markers.values())
    missing = [k for k, v in markers.items() if not v]
    rec.add("GET / (home)", ok, st, len(body),
            "200" if st == 200 else "status=%s" % st
            + ("; missing: " + ",".join(missing) if missing else
               "; markers: rtl,hero,work,coverage,volumes,search,rag-off"))
    return st is not None


def check_volumes(base, rec, timeout):
    st, hd, body = http(base, "/volumes", timeout=timeout)
    rec.note_html(body)
    text = body.decode("utf-8", "replace")
    n_cards = text.count("volume-card\"")
    markers = {
        "volume grid": "volume-grid" in text,
        "6+ volume cards": n_cards >= 6,
        "unknown-volume badge": "در حال بازیابی شمارهٔ جلد" in text,
        "registered total": "جلد ثبت‌شده" in text,
    }
    ok = st == 200 and all(markers.values())
    missing = [k for k, v in markers.items() if not v]
    rec.add("GET /volumes", ok, st, len(body),
            "200; %d volume cards" % n_cards
            + ("" if ok else "; missing: " + ",".join(missing)))


def check_volume(base, rec, timeout):
    st, hd, body = http(base, "/volumes/" + VOLUME_ID, timeout=timeout)
    rec.note_html(body)
    text = body.decode("utf-8", "replace")
    markers = {
        "volume-detail": "volume-detail" in text,
        "cover plate": "volume-detail__cover" in text,
        "page count 9391": "9391" in text,
        "item_index range": "بازهٔ item_index" in text,
        "start reading btn": "شروع مطالعه" in text,
        "top headings": "هدرهای پرتکرار" in text,
    }
    ok = st == 200 and all(markers.values())
    missing = [k for k, v in markers.items() if not v]
    rec.add("GET /volumes/<vol047>", ok, st, len(body),
            "200; cover+count+range+start+headings"
            + ("" if ok else "; missing: " + ",".join(missing)))


def check_page(base, rec, timeout):
    st, hd, body = http(base, "/page/2", timeout=timeout)
    rec.note_html(body)
    text = body.decode("utf-8", "replace")
    markers = {
        "article reader": 'data-item-index="2"' in text,
        "naskh text block": "reader__text" in text,
        "item_index code": "item_index: <code>2</code>" in text,
        "prev nav": "nav-page--prev" in text,
        "next nav": "nav-page--next" in text,
        "dup banner": "dup-notice" in text,
        "metadata drawer": "metadata-drawer" in text,
    }
    ok = st == 200 and all(markers.values())
    missing = [k for k, v in markers.items() if not v]
    rec.add("GET /page/2 (reader)", ok, st, len(body),
            "200; naskh+prev/next+dup+drawer"
            + ("" if ok else "; missing: " + ",".join(missing)))


def check_gap_recovery(base, rec, timeout):
    st, hd, body = http(base, "/page/5000", timeout=timeout)
    rec.note_html(body)
    text = body.decode("utf-8", "replace")
    markers = {
        "missing flag": 'data-missing="true"' in text,
        "recovery heading": "این صفحه در دست بازیابی است" in text,
        "backfill text": "در دست بازیابی" in text,
        "next nav present": "nav-page--next" in text,
        "no text block": "reader__text" not in text,
    }
    ok = st == 200 and all(markers.values())
    missing = [k for k, v in markers.items() if not v]
    rec.add("GET /page/5000 (gap)", ok, st, len(body),
            "200; honest backfill page, no reader text"
            + ("" if ok else "; missing: " + ",".join(missing)))


def check_topics(base, rec, timeout):
    st, hd, body = http(base, "/topics", timeout=timeout)
    rec.note_html(body)
    text = body.decode("utf-8", "replace")
    markers = {
        "topic list": "topic-list" in text,
        "top topic تفسیر": "تفسیر" in text,
        "auto-extract note": "استخراج خودکار" in text,
        "registered total": "موضوع ثبت‌شده" in text,
    }
    ok = st == 200 and all(markers.values())
    missing = [k for k, v in markers.items() if not v]
    rec.add("GET /topics", ok, st, len(body),
            "200; list+top topic+auto note"
            + ("" if ok else "; missing: " + ",".join(missing)))


def check_surahs(base, rec, timeout):
    st, hd, body = http(base, "/surahs", timeout=timeout)
    rec.note_html(body)
    text = body.decode("utf-8", "replace")
    markers = {
        "honest banner": "در حال تکمیل" in text,
        "coverage 0/114": "0/114" in text,
        "reason section": "چرا هنوز؟" in text,
        "no-fabrication note": "هیچ دادهٔ سوره‌ای ساخته نمی‌شود" in text,
        "no surah names": "آیة" not in text,
    }
    ok = st == 200 and all(markers.values())
    missing = [k for k, v in markers.items() if not v]
    rec.add("GET /surahs (honest)", ok, st, len(body),
            "200; not_supported banner + 0/114 + no data"
            + ("" if ok else "; missing: " + ",".join(missing)))


def check_search(base, rec, timeout):
    path = "/search?q=" + urllib.parse.quote(SEARCH_Q)
    st, hd, body = http(base, path, timeout=timeout)
    rec.note_html(body)
    text = body.decode("utf-8", "replace")
    markers = {
        "result hits": "search-hit" in text,
        "mark highlight": "<mark>" in text,
        "total count line": "نتیجه" in text,
        "result links": "/page/" in text,
    }
    ok = st == 200 and all(markers.values())
    missing = [k for k, v in markers.items() if not v]
    rec.add("GET /search?q=قرآن", ok, st, len(body),
            "200; hits+<mark>+count+links"
            + ("" if ok else "; missing: " + ",".join(missing)))


def check_about(base, rec, timeout):
    st, hd, body = http(base, "/about", timeout=timeout)
    rec.note_html(body)
    text = body.decode("utf-8", "replace")
    markers = {
        "about title": "دربارهٔ پیکره" in text,
        "content sha": CONTENT_SHA in text,
        "db sha": DB_SHA in text,
        "provenance table": "منبع‌شناسی" in text,
        "quality table": "وضعیت کیفیت" in text,
    }
    ok = st == 200 and all(markers.values())
    missing = [k for k, v in markers.items() if not v]
    rec.add("GET /about", ok, st, len(body),
            "200; provenance shas + quality table"
            + ("" if ok else "; missing: " + ",".join(missing)))


def check_health(base, rec, timeout):
    st, hd, body = http(base, API + "/health", timeout=timeout)
    ok = False
    evidence = "status=%s" % st
    if st == 200:
        try:
            doc = json.loads(body.decode("utf-8"))
            d = doc.get("data", {})
            rm = d.get("readmodel", {})
            mrm = doc.get("meta", {}).get("readmodel", {})
            ok = (d.get("status") == "ok"
                  and rm.get("version")
                  and rm.get("content_sha256") == CONTENT_SHA
                  and rm.get("db_sha256") == DB_SHA
                  and d.get("db_quick_check") == "ok"
                  and mrm.get("version") == rm.get("version"))
            evidence = ("200; version=%s content_sha=%s db_quick=%s"
                        % (rm.get("version"),
                           (rm.get("content_sha256") or "")[:12],
                           d.get("db_quick_check")))
        except Exception as e:  # noqa: BLE001
            evidence = "200; JSON parse error: %r" % e
    rec.add("GET %s/health" % API, ok, st, len(body), evidence)
    return st == 200


def check_catalog_and_etag(base, rec, timeout):
    st1, hd1, body1 = http(base, API + "/catalog", timeout=timeout)
    ok = False
    evidence = "first status=%s" % st1
    etag = (hd1 or {}).get("ETag")
    if st1 == 200 and etag:
        try:
            doc = json.loads(body1.decode("utf-8"))
            d = doc.get("data", {})
            meta = doc.get("meta", {})
            base_ok = (d.get("work", {}).get("name") == "تفسیر تسنیم"
                       and "counts" in d and "readmodel" in meta)
            st2, hd2, body2 = http(
                base, API + "/catalog",
                headers={"If-None-Match": etag}, timeout=timeout)
            if base_ok and st2 == 304:
                ok = True
                evidence = ("200; work=تفسیر تسنیم; ETag=%s -> "
                            "304 on If-None-Match" % etag)
            else:
                evidence = ("200; ETag=%s but recheck=%s (want 304)"
                            % (etag, st2))
        except Exception as e:  # noqa: BLE001
            evidence = "200; JSON parse error: %r" % e
    elif st1 == 200:
        evidence = "200; no ETag header"
    rec.add("GET %s/catalog (+ETag/304)" % API, ok, st1, len(body1), evidence)


def check_openapi(base, rec, timeout):
    st, hd, body = http(base, API + "/openapi.json", timeout=timeout)
    ok = False
    evidence = "status=%s" % st
    if st == 200:
        try:
            doc = json.loads(body.decode("utf-8"))
            paths = doc.get("paths", {})
            ok = bool(paths)
            evidence = "200; openapi=%s paths=%d" % (
                doc.get("openapi", "?"), len(paths))
        except Exception as e:  # noqa: BLE001
            evidence = "200; JSON parse error: %r" % e
    rec.add("GET %s/openapi.json" % API, ok, st, len(body), evidence)


def check_not_found(base, rec, timeout):
    st, hd, body = http(base, "/definitely-not-a-page-404", timeout=timeout)
    rec.note_html(body)
    text = body.decode("utf-8", "replace")
    ok = st == 404 and "404" in text and "reader__text" not in text
    rec.add("GET /definitely-not-a-page-404", ok, st, len(body),
            "404; HTML error page" if ok else "status=%s" % st)


def check_font(base, rec, timeout):
    st, hd, body = http(base, FONT_PATH, timeout=timeout)
    ct = (hd or {}).get("Content-Type", "")
    cc = (hd or {}).get("Cache-Control", "")
    ok = st == 200 and "font/ttf" in ct and "max-age=86400" in cc \
        and len(body) > 10000
    rec.add("GET %s" % FONT_PATH, ok, st, len(body),
            "200; %s; Cache-Control=%s; %d bytes"
            % (ct, cc, len(body)) if ok else
            "status=%s ct=%s cc=%s" % (st, ct, cc))


def run_suite(base, timeout):
    rec = Recorder()
    up = True
    # health first: a dead server should short-circuit with a clear signal
    if not check_health(base, rec, timeout):
        up = False
    if up:
        check_home(base, rec, timeout)
        check_volumes(base, rec, timeout)
        check_volume(base, rec, timeout)
        check_page(base, rec, timeout)
        check_gap_recovery(base, rec, timeout)
        check_topics(base, rec, timeout)
        check_surahs(base, rec, timeout)
        check_search(base, rec, timeout)
        check_about(base, rec, timeout)
        check_catalog_and_etag(base, rec, timeout)
        check_openapi(base, rec, timeout)
        check_not_found(base, rec, timeout)
        check_font(base, rec, timeout)

    # global HP-1 canary scan over every HTML body collected
    leaks = rec.canary_leak()
    rec.add("canary scan (no hidden context)",
            not leaks, 200 if not leaks else 500, len(rec.html_bodies),
            "no %r in %d HTML bodies" % (CANARY, len(rec.html_bodies))
            if not leaks else
            "LEAK in bodies: %s" % leaks)
    return rec


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--base", default=DEFAULT_BASE)
    ap.add_argument("--label", default="")
    ap.add_argument("--timeout", type=int, default=20)
    args = ap.parse_args(argv)

    label = args.label or args.base
    print("=" * 78)
    print("Tasnim Web V1 — smoke suite  [target: %s]" % label)
    print("=" * 78)
    rec = run_suite(args.base, args.timeout)

    print("%-34s %-6s %9s  %s" % ("check", "status", "bytes", "evidence"))
    print("-" * 78)
    for r in rec.rows:
        flag = "PASS" if r["ok"] else "FAIL"
        print("%-34s %-6s %9d  [%s] %s"
              % (r["name"], r["status"], r["size"], flag, r["evidence"]))
    print("-" * 78)
    n_pass = sum(1 for r in rec.rows if r["ok"])
    n_fail = len(rec.rows) - n_pass
    print("RESULT [%s]: %d PASS / %d FAIL / %d total"
          % (label, n_pass, n_fail, len(rec.rows)))
    print("=" * 78)
    return 0 if n_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

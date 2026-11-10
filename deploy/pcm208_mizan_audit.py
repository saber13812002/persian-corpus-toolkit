#!/usr/bin/env python3
"""PCM-20.8 — Read-only audit of the live Tasnim/Mizan Word Studio state.

Finds the «تفسیر المیزان» work (collection/document/job) on the live
backend, reports its current stage, counts and last error, and prints a
diagnosis of where the pipeline is stuck.

STRICTLY READ-ONLY: only GET requests to /api/auth/status and
/api/knowledge/*. No mutations, no deploy, no DB access.

Usage (credentials are never written to a file and never printed):
    set PCT_COOKIE=<pct_session value>
    python deploy\\pcm208_mizan_audit.py [base_url]

    or:  python deploy\\pcm208_mizan_audit.py --cookie-file %TEMP%\\pct_ck.txt
         (file contains the raw cookie value, one line)

    or (dashboard password — the script logs in itself):
    set PCT_PASSWORD=<dashboard password>
    python deploy\\pcm208_mizan_audit.py
         (login is one-shot; the returned cookie is held in memory only)
"""

import json
import os
import sys
import urllib.error
import urllib.request

DEFAULT_BASE = "https://corpus.ai.ismc.ir"
UA = "pcm208-mizan-audit/1.0 (read-only)"


def get_cookie():
    env = os.environ.get("PCT_COOKIE", "").strip()
    if env:
        return env
    if "--cookie-file" in sys.argv:
        i = sys.argv.index("--cookie-file")
        path = sys.argv[i + 1]
        with open(path, "r", encoding="utf-8") as f:
            v = f.read().strip()
        if v:
            return v
    pw = get_password()
    if pw:
        base = DEFAULT_BASE
        for a in sys.argv[1:]:
            if not a.startswith("--") and "://" in a:
                base = a
        ck = login(base, pw)
        if ck:
            return ck
    print("FATAL: no cookie. Set PCT_COOKIE or pass --cookie-file "
          "(or PCT_PASSWORD / --password-file to log in).", file=sys.stderr)
    sys.exit(2)


def get_password():
    env = os.environ.get("PCT_PASSWORD", "").strip()
    if env:
        return env
    if "--password-file" in sys.argv:
        i = sys.argv.index("--password-file")
        path = sys.argv[i + 1]
        with open(path, "r", encoding="utf-8") as f:
            v = f.read().strip()
        if v:
            return v
    return ""


def login(base, password, timeout=25):
    """One-shot POST /api/auth/login. Returns session cookie value or None.
    Password is sent once over TLS and never printed (length only)."""
    body = json.dumps({"password": password}).encode("utf-8")
    req = urllib.request.Request(
        base + "/api/auth/login", data=body, method="POST",
        headers={
            "User-Agent": UA,
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            r.read()
            setc = r.headers.get("Set-Cookie", "")
    except urllib.error.HTTPError as e:
        e.read()
        print("login failed: HTTP %d — wrong password? (rate-limit: "
              "do NOT retry blindly; 10 failed attempts lock the IP 10 min)"
              % e.code, file=sys.stderr)
        return None
    except Exception as e:  # noqa: BLE001
        print("login failed: %s" % e, file=sys.stderr)
        return None
    for part in setc.split(","):
        part = part.strip()
        if part.startswith("pct_session="):
            val = part.split(";", 1)[0].split("=", 1)[1]
            print("login OK (cookie len=%d, held in memory only)" % len(val))
            return val
    print("login returned 200 but no pct_session cookie", file=sys.stderr)
    return None


def get(base, path, cookie, timeout=25):
    req = urllib.request.Request(
        base + path,
        headers={
            "User-Agent": UA,
            "Cookie": "pct_session=" + cookie,
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read().decode("utf-8", "replace")
            try:
                return r.status, json.loads(body)
            except json.JSONDecodeError:
                return r.status, {"_raw": body[:400]}
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        try:
            return e.code, json.loads(body)
        except json.JSONDecodeError:
            return e.code, {"_raw": body[:200]}
    except Exception as e:  # noqa: BLE001
        return -1, {"error": str(e)}


def name_of(obj):
    if not isinstance(obj, dict):
        return ""
    for k in ("name", "title", "work_name", "book"):
        v = obj.get(k)
        if isinstance(v, str) and v:
            return v
    return ""


def is_mizan(text):
    t = (text or "").lower()
    return ("میزان" in (text or "")) or "mizan" in t or "المیزان" in (text or "")


def main():
    cookie = get_cookie()
    base = DEFAULT_BASE
    for a in sys.argv[1:]:
        if not a.startswith("--") and "://" in a:
            base = a
    print("# PCM-20.8 Mizan audit — read-only")
    print("base:", base)

    st, d = get(base, "/api/auth/status", cookie)
    print("auth/status:", st, json.dumps(d, ensure_ascii=False))
    if st != 200 or not d.get("authenticated"):
        print("FATAL: cookie not authenticated — aborting (read-only guard).")
        return 1

    # 1) collections
    st, d = get(base, "/api/knowledge/collections", cookie)
    print("\n== collections:", st)
    cols = d.get("collections", d if isinstance(d, list) else [])
    if st != 200:
        print(json.dumps(d, ensure_ascii=False)[:500])
        cols = []
    for c in cols:
        if not isinstance(c, dict):
            continue
        flag = " <<<< MIZAN" if is_mizan(name_of(c)) else ""
        print("  coll id=%s name=%r docs=%s status=%s%s" % (
            c.get("id"), name_of(c),
            c.get("documents_count", c.get("doc_count", "?")),
            c.get("status", "?"), flag))

    # 2) documents per collection (cap 200 each, defensive)
    docs_all = []
    for c in cols:
        if not isinstance(c, dict) or "id" not in c:
            continue
        cid = c["id"]
        st, d = get(base, "/api/knowledge/collections/%s/documents" % cid, cookie)
        if st != 200:
            print("  docs for coll %s: HTTP %s" % (cid, st))
            continue
        ds = d.get("documents", d if isinstance(d, list) else [])
        for doc in ds[:200]:
            if isinstance(doc, dict):
                doc["_coll"] = c
                docs_all.append(doc)
        print("  coll %s: %d documents" % (cid, len(ds)))

    print("\n== all documents (stage/status):")
    mizan_docs = []
    for doc in docs_all:
        nm = name_of(doc)
        status = doc.get("status", doc.get("state", "?"))
        stage = doc.get("stage", doc.get("on_stage", ""))
        err = doc.get("last_error", doc.get("error", ""))
        flag = " <<<< MIZAN" if is_mizan(nm) else ""
        print("  doc id=%s coll=%s name=%r status=%s stage=%s err=%r%s" % (
            doc.get("id"), doc.get("collection_id", doc.get("_coll", {}).get("id")),
            nm[:60], status, stage, (err or "")[:120], flag))
        if is_mizan(nm):
            mizan_docs.append(doc)

    # 3) detailed dive into mizan docs
    for doc in mizan_docs[:5]:
        did = doc.get("id")
        print("\n== DIVE doc %s ==" % did)
        for path in (
            "/api/knowledge/documents/%s" % did,
            "/api/knowledge/documents/%s/structure" % did,
            "/api/knowledge/documents/%s/quality" % did,
        ):
            st, d = get(base, path, cookie)
            print("  GET %s -> %s" % (path, st))
            print("   ", json.dumps(d, ensure_ascii=False)[:1500])

    # 4) jobs (older builds expose /api/knowledge/jobs)
    st, d = get(base, "/api/knowledge/jobs", cookie)
    print("\n== jobs:", st)
    jobs = d.get("jobs", d if isinstance(d, list) else [])
    if st != 200:
        print(json.dumps(d, ensure_ascii=False)[:300])
    for j in jobs[:50]:
        if not isinstance(j, dict):
            continue
        flag = " <<<< MIZAN" if is_mizan(json.dumps(j, ensure_ascii=False)) else ""
        keep = {k: j.get(k) for k in (
            "id", "document_id", "collection_id", "stage", "status",
            "state", "created_at", "updated_at", "last_error", "message",
            "progress", "total", "done") if k in j}
        print("  ", json.dumps(keep, ensure_ascii=False)[:300], flag)

    # 5) queue summary (newer builds; may 404)
    st, d = get(base, "/api/knowledge/queue/summary", cookie)
    print("\n== queue/summary:", st)
    if st == 200:
        print(json.dumps(d, ensure_ascii=False)[:1200])

    if not mizan_docs and not cols:
        print("\nRESULT: nothing found — cookie valid but no collections; "
              "the work may live under a different namespace or the build "
              "predates collections.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

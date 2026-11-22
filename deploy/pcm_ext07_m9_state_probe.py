"""M9: read-only state probe of the staging khamenei queue (run on s52)."""
import json
import sqlite3
import ssl
import urllib.request

B = "https://pct-staging.ai.ismc.ir"
DB = "/home/saber/saberprojects/pct-staging/backend/thesaurus.db"
CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE


def get(path):
    r = urllib.request.urlopen(B + path, context=CTX, timeout=30)
    return json.loads(r.read().decode())


def main():
    db = sqlite3.connect(DB)
    db.row_factory = sqlite3.Row
    total = db.execute("SELECT COUNT(*) c FROM khamenei_speeches").fetchone()["c"]
    with_date = db.execute(
        "SELECT COUNT(*) c FROM khamenei_speeches WHERE speech_date != ''"
    ).fetchone()["c"]
    by_year = {
        r["y"]: r["c"]
        for r in db.execute(
            "SELECT substr(speech_date,1,4) y, COUNT(*) c FROM khamenei_speeches "
            "GROUP BY y ORDER BY y"
        )
    }
    q = db.execute(
        "SELECT status, COUNT(*) c FROM crawl_queue "
        "WHERE page_type='khamenei_speech' GROUP BY status"
    ).fetchall()
    qby = {
        r["y"]: r["c"]
        for r in db.execute(
            "SELECT COALESCE((SELECT regexp_extract(src, 'year=(\\\\d{4})', 1)), '?') y, "
            "COUNT(*) c FROM (SELECT source_page src FROM crawl_queue "
            "WHERE page_type='khamenei_speech' AND status='pending') GROUP BY y"
        )
    } if False else {}
    # regexp_extract needs the sqlite FTS5/JSON1 regex? Not always compiled in — do it in python
    pend_rows = db.execute(
        "SELECT source_page FROM crawl_queue "
        "WHERE page_type='khamenei_speech' AND status='pending'"
    ).fetchall()
    import re

    qby = {}
    for r in pend_rows:
        m = re.search(r"year=(\d{4})", r["source_page"] or "")
        y = m.group(1) if m else "?"
        qby[y] = qby.get(y, 0) + 1
    dups = db.execute(
        "SELECT COUNT(*) c FROM (SELECT speech_id FROM khamenei_speeches "
        "GROUP BY speech_id HAVING COUNT(*)>1)"
    ).fetchone()["c"]
    integ = db.execute("PRAGMA integrity_check").fetchone()[0]
    db.close()

    print("DB: total=%d with_date=%d dups=%d integrity=%s" % (total, with_date, dups, integ))
    print("DB by_year:", json.dumps(by_year, sort_keys=True))
    print("QUEUE status:", json.dumps({r["status"]: r["c"] for r in q}))
    print("QUEUE pending_by_year:", json.dumps(qby, sort_keys=True))
    try:
        cs = get("/api/khamenei/crawl-status")
        print("API crawl-status:", json.dumps(cs, sort_keys=True))
    except Exception as e:  # noqa
        print("API crawl-status ERROR:", e)
    try:
        st = get("/api/khamenei/stats")
        print("API stats:", json.dumps({k: st[k] for k in ("total", "with_date", "without_date") if k in st}))
    except Exception as e:  # noqa
        print("API stats ERROR:", e)


if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
"""PCM-14B isolated acceptance (audit-only; NO production touched).

Runs the REAL backend (python server.py) against temp DB + temp data dir.
Phase A: create collection, upload 2 DOCX, verify SHA-256, process doc1,
         metadata field+value, approve doc1.
         -> hard-kill server (simulates crash/restart)
Phase B: restart server (same temp DB + data)
         -> verify everything survived (docs, artifacts, metadata)
         -> process doc2 (worker alive after restart)
         -> simulate interrupted job (backdate running job 2h) -> recovery
         -> retry contract probe: /process on the interrupted job's document
         -> ES compatibility endpoint (expect honest NOT_VERIFIED)

Exit code 0 = all hard checks passed; soft findings printed as WARN.
"""
import hashlib
import io
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:5155"
PW = "acceptance-pw-14b"
RESULTS = []


def record(step, ok, detail=""):
    RESULTS.append((step, ok, detail))
    try:
        print(("PASS " if ok else "FAIL ") + step + ((" | " + detail) if detail else ""))
    except UnicodeEncodeError:
        print(("PASS " if ok else "FAIL ") + step
              + ((" | " + detail.encode("ascii", "replace").decode()) if detail else ""))


def http(method, path, headers=None, data=None, timeout=30):
    req = urllib.request.Request(BASE + path, data=data, method=method,
                                 headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read()


def jbody(b):
    try:
        return json.loads(b.decode("utf-8"))
    except Exception:
        return {}


def multipart(fields, files):
    """files: list of (formname, filename, bytes)"""
    boundary = "----acc14b"
    out = io.BytesIO()
    for k, v in fields.items():
        out.write(("--%s\r\nContent-Disposition: form-data; name=\"%s\"\r\n\r\n%s\r\n"
                   % (boundary, k, v)).encode())
    for name, fname, content in files:
        out.write(("--%s\r\nContent-Disposition: form-data; name=\"%s\"; "
                   "filename=\"%s\"\r\nContent-Type: application/octet-stream\r\n\r\n"
                   % (boundary, name, fname)).encode())
        out.write(content)
        out.write(b"\r\n")
    out.write(("--%s--\r\n" % boundary).encode())
    return out.getvalue(), "multipart/form-data; boundary=" + boundary


def make_docx(path, title, body_paras):
    from docx import Document
    d = Document()
    d.add_heading(title, level=1)
    for p in body_paras:
        d.add_paragraph(p)
    d.save(path)
    return open(path, "rb").read()


def start_server(env):
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return subprocess.Popen(
        [sys.executable, "server.py"], cwd=os.path.join(root, "backend"),
        env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def wait_ready(proc, tries=40):
    for _ in range(tries):
        if proc.poll() is not None:
            return False
        try:
            urllib.request.urlopen(BASE + "/api/auth/status", timeout=2)
            return True
        except Exception:
            time.sleep(0.5)
    return False


def poll_job(cookie, jid, tries=60):
    """Poll the jobs LIST endpoint (no per-job GET exists) until terminal."""
    row = None
    for _ in range(tries):
        time.sleep(0.5)
        try:
            _, _, b = http("GET", "/api/knowledge/jobs?limit=50", {"Cookie": cookie})
            row = next((x for x in jbody(b)["jobs"] if x["job_id"] == jid), None)
            if row and row["status"] in ("succeeded", "failed", "interrupted"):
                return row
        except Exception:
            pass
    return row


def main():
    work = tempfile.mkdtemp(prefix="pct-acc14b-")
    db_path = os.path.join(work, "acc.db")
    data_dir = os.path.join(work, "data")
    os.makedirs(data_dir, exist_ok=True)

    # fixtures: two Persian books
    f1 = make_docx(os.path.join(work, "b1.docx"), "کتاب اول — تاریخ",
                   ["این فصل به بررسی تاریخ ایران می‌پردازد.", "متن دومین پاراگراف کتاب اول."])
    f2 = make_docx(os.path.join(work, "b2.docx"), "کتاب دوم — ادبیات",
                   ["ادبیات فارسی ریشه در حافظ و سعدی دارد.", "پاراگراف دوم کتاب دوم."])
    sha1 = hashlib.sha256(f1).hexdigest()
    sha2 = hashlib.sha256(f2).hexdigest()

    env = dict(os.environ)
    env.update({"PCT_DB": db_path, "PCT_KNOWLEDGE_DATA_DIR": data_dir,
                "PCT_DASHBOARD_PASSWORD": PW, "HOST": "127.0.0.1", "PORT": "5155"})

    # ─────────────────────────── PHASE A ───────────────────────────
    print("\n=== PHASE A: server run 1 ===")
    srv = start_server(env)
    try:
        if not wait_ready(srv):
            record("A0 server starts", False, "never became ready")
            return
        record("A0 server starts", True)

        # login
        body = json.dumps({"password": PW}).encode()
        st, hd, b = http("POST", "/api/auth/login",
                         {"Content-Type": "application/json"}, body)
        cookie = ""
        for v in hd.get("Set-Cookie", "").split(","):
            if "pct_session" in v or "session" in v:
                cookie = v.split(";")[0]
        record("A1 login", st == 200, "cookie set" if cookie else "no cookie")
        AH = {"Cookie": cookie}

        # create collection
        st, hd, b = http("POST", "/api/knowledge/collections",
                         {**AH, "Content-Type": "application/json"},
                         json.dumps({"name": "کالکشن آزمایشی پذیرش",
                                     "slug": "acc-14b", "subject": "تاریخ"}).encode())
        coll = jbody(b)["collection"]
        cid_num, cid = coll["id"], coll["collection_id"]
        record("A2 create collection", st in (200, 201), cid)

        # upload both
        def upload(fname, content):
            body, ct = multipart({"relative_path": ""}, [("file", fname, content)])
            return http("POST", f"/api/knowledge/collections/{cid_num}/documents",
                        {**AH, "Content-Type": ct}, body)

        st, hd, b = upload("b1.docx", f1)
        d1 = jbody(b)["document"]
        record("A3 upload doc1", st == 201 and d1["sha256"] == sha1,
               "sha match: %s" % (d1["sha256"] == sha1))
        st, hd, b = upload("b2.docx", f2)
        d2 = jbody(b)["document"]
        record("A4 upload doc2", st == 201 and d2["sha256"] == sha2)

        # stored file on disk (persistent store)
        stored = os.path.exists(os.path.join(data_dir, "files"))
        record("A5 persistent store (data/files)", stored)

        # process doc1
        st, hd, b = http("POST", f"/api/knowledge/documents/{d1['document_id']}/process", AH)
        job1 = jbody(b)["job"]
        record("A6 process doc1 queued", st in (200, 202), job1["job_id"])
        # poll (list endpoint — no per-job GET exists)
        final = poll_job(cookie, job1["job_id"])
        record("A7 job1 finished", final and final["status"] == "succeeded",
               str(final["status"] if final else "?"))
        _, _, b = http("GET", "/api/knowledge/documents/" + d1["document_id"], AH)
        doc1 = jbody(b)["document"]
        record("A8 doc1 parsed", doc1["status"] in ("parsed", "needs_review"),
               "blocks=%s quality=%s" % (doc1["blocks_count"], doc1["quality_status"]))

        # artifacts
        st, hd, b = http("GET", f"/api/knowledge/documents/{d1['document_id']}/structure", AH)
        s = jbody(b)["structure"]
        record("A9 structure artifact", st == 200 and len(s.get("headings", [])) >= 1,
               "headings=%d" % len(s.get("headings", [])))
        st, hd, b = http("GET", f"/api/knowledge/documents/{d1['document_id']}/quality", AH)
        q = jbody(b)["quality"]
        record("A10 quality artifact", st == 200 and "score" in q)
        st, hd, b = http("GET", f"/api/knowledge/documents/{d1['document_id']}/blocks?limit=10", AH)
        blk = jbody(b)["blocks"]
        raw_ok = all(("raw_text" in x and "normalized_text" in x) for x in blk)
        record("A11 blocks raw+normalized", st == 200 and raw_ok and len(blk) >= 1)

        # metadata: document-scope field + value
        st, hd, b = http("POST", "/api/knowledge/metadata/fields",
                         {**AH, "Content-Type": "application/json"},
                         json.dumps({"scope": "document", "field_key": "year",
                                     "display_name": "سال", "data_type": "number"}).encode())
        fb = jbody(b)
        record("A12 metadata field created", st in (200, 201),
               "field_key=%s err=%s" % ((fb.get("field") or {}).get("field_key"),
                                        fb.get("message", "")))
        st, hd, b = http("POST", "/api/knowledge/metadata/values",
                         {**AH, "Content-Type": "application/json"},
                         json.dumps({"field_key": "year", "document_id": d1["document_id"],
                                     "value": 1398}).encode())
        record("A13 metadata value set", st in (200, 201), str(jbody(b)))

        # approve
        st, hd, b = http("POST", f"/api/knowledge/documents/{d1['document_id']}/approve", AH)
        record("A14 approve doc1", st == 200 and jbody(b)["document"]["status"] == "approved")

    finally:
        srv.kill()
        srv.wait()
    print("=== PHASE A end: server killed (hard) ===")

    # ─────────────────────────── PHASE B ───────────────────────────
    print("\n=== PHASE B: server run 2 (restart, same temp DB+data) ===")
    srv = start_server(env)
    try:
        if not wait_ready(srv):
            record("B0 server restarts", False)
            return
        record("B0 server restarts", True)
        st, hd, b = http("POST", "/api/auth/login",
                         {"Content-Type": "application/json"},
                         json.dumps({"password": PW}).encode())
        cookie = ""
        for v in hd.get("Set-Cookie", "").split(","):
            if "session" in v:
                cookie = v.split(";")[0]
        AH = {"Cookie": cookie}
        record("B1 re-login after restart", st == 200, "cookie=%s" % ("yes" if cookie else "no"))

        # everything survived
        _, _, b = http("GET", f"/api/knowledge/collections/{cid_num}", AH)
        coll = jbody(b)["collection"]
        docs = {x["document_id"]: x for x in coll["documents"]}
        record("B2 documents survived restart",
               d1["document_id"] in docs and d2["document_id"] in docs)
        record("B3 doc1 state survived", docs.get(d1["document_id"], {}).get("status") == "approved",
               str(docs.get(d1["document_id"], {}).get("status")))
        record("B4 doc2 still uploaded", docs.get(d2["document_id"], {}).get("status") == "uploaded")

        st, hd, b = http("GET", f"/api/knowledge/documents/{d1['document_id']}/blocks?limit=5", AH)
        record("B5 artifacts retrievable after restart",
               st == 200 and len(jbody(b)["blocks"]) >= 1)
        st, hd, b = http("GET", "/api/knowledge/metadata/values?document_id=" + d1["document_id"], AH)
        vals = jbody(b).get("values") or []
        md_ok = any(str(v.get("field_key")) == "year"
                    and str(v.get("value")) in ("1398", "1398.0")
                    for v in vals)
        record("B6 metadata survived restart", md_ok,
               "values=%s" % json.dumps(vals, ensure_ascii=False)[:120])

        # worker alive after restart: process doc2
        st, hd, b = http("POST", f"/api/knowledge/documents/{d2['document_id']}/process", AH)
        job2 = jbody(b)["job"]
        record("B7 process doc2 after restart", st in (200, 202))
        final = poll_job(cookie, job2["job_id"])
        record("B8 job2 succeeded after restart",
               final and final["status"] == "succeeded",
               str(final["status"] if final else "?"))

        # ── interrupted-job recovery contract ──
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        # simulate crash mid-run: job2's twin for doc1's key -> running, 2h old
        conn.execute(
            "UPDATE knowledge_jobs SET status='running', progress=0, "
            "updated_at=datetime('now','-2 hours'), completed_at=NULL "
            "WHERE job_id=?", (job1["job_id"],))
        conn.commit()
        conn.close()
        _, _, b = http("GET", "/api/knowledge/jobs", AH)
        rows = {j["job_id"]: j for j in jbody(b)["jobs"]}
        j1 = rows.get(job1["job_id"], {})
        record("B9 stuck job -> interrupted on next request",
               j1.get("status") == "interrupted" and "worker interrupted" in (j1.get("error") or ""),
               str(j1.get("status")))

        # retry contract probe: doc1 back to 'uploaded' (as recovery would leave a
        # crashed doc), then /process again. job_key already exists -> does it re-run?
        conn = sqlite3.connect(db_path)
        conn.execute("UPDATE knowledge_collection_documents SET status='uploaded' "
                     "WHERE document_id=?", (d1["document_id"],))
        conn.commit()
        conn.close()
        st, hd, b = http("POST", f"/api/knowledge/documents/{d1['document_id']}/process", AH)
        rj = jbody(b)
        time.sleep(4)
        _, _, b = http("GET", f"/api/knowledge/documents/{d1['document_id']}", AH)
        doc1b = jbody(b)["document"]
        rj_job = rj.get("job", {})
        record("B10 RETRY-CONTRACT: /process re-runs interrupted job",
               doc1b["status"] in ("parsed", "needs_review", "approved"),
               "http=%s job.status=%s doc.status=%s resubmitted=%s" % (
                   st, rj_job.get("status"), doc1b["status"], rj.get("resubmitted")))
        if doc1b["status"] not in ("parsed", "needs_review", "approved"):
            print("  >> FINDING: interrupted job is NOT re-executed by /process "
                  "(existing job_key returns the stale row; worker never started).")

        # ── ES compatibility (honest status) ──
        st, hd, b = http("GET", "/api/knowledge/compatibility", AH)
        cj = jbody(b)
        flags = [f.get("compatibility") for f in cj.get("field_matrix", [])]
        record("B11 ES compatibility endpoint", st == 200,
               "es_available=%s prev=%s flags=%s" % (
                   cj.get("es_available"), cj.get("previous_mapping"),
                   sorted(set(flags)) if flags else []))

    finally:
        srv.kill()
        srv.wait()

    # ── summary ──
    print("\n=== SUMMARY ===")
    fails = [r for r in RESULTS if not r[1]]
    for step, ok, detail in RESULTS:
        print(("PASS " if ok else "FAIL ") + step)
    print("\n%d/%d passed" % (len(RESULTS) - len(fails), len(RESULTS)))
    print("workdir (temp, will remain until OS cleanup):", work)
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()

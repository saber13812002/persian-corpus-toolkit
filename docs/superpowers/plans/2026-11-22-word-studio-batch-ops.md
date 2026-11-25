# Word Studio Bulk Ops (process-all / pause / approve-all) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One-click batch «process all unprocessed» and «approve all unapproved» in the Word Studio Word Library, driven by two new backend endpoints + a pause control, with server-side live counters.

**Architecture:** Reuse the existing PCM-15 job/queue machinery verbatim: a new job kind `process_collection` (worker fn mirroring `_job_kind_process_batch`, whole-collection scope, pause scope `collection:<cid>` in the existing `knowledge_queue_control` table — no schema migration), one synchronous atomic approve-all UPDATE + audit row, and an additive `status_counts` map on the documents list so the UI counters never depend on the 50-row page cap.

**Tech Stack:** Python 3 / Flask / SQLite (WAL) in `backend/knowledge_api.py`; vanilla JS single-file UI in `dashboard/studio.html`; unittest with `pct_test_support` (PCM-12.3 rule); OpenAPI 3.0.3 YAML contract.

**Spec:** `docs/superpowers/specs/2026-11-22-word-studio-batch-ops-design.md` (approved by owner 2026-11-22, Method B)

## Global Constraints

- AGENTS §2.7: parameterized SQL (placeholders); no string interpolation of values.
- AGENTS §2.8: client DOM output through `escHtml` (Persian labels are static, counts via `faNum`).
- AGENTS §2.9: all counters come from real DB queries server-side — no client-computed/fabricated statistics.
- Additive only: no schema migration, no data migration, no change to existing endpoint response shapes (new keys only).
- Every new route is `@require_auth` (PCM-09).
- Tests: `import pct_test_support` FIRST, then `import server`; `pct_test_support.reset_db()` in `setUp` (PCM-12.3).
- `job_key` format is `kind:identifier` — the worker dispatches on `job_key.split(":")[0]` into `_JOB_KINDS` (knowledge_api.py:835).
- Persian UI copy; numerals via existing `faNum()`.
- Test run command (workspace `.venv` python, from `backend/`):
  `python -m unittest test_api test_projects test_dashboard test_knowledge_api test_word_factory test_dump test_work_registry test_queue test_corpus_builder test_studio_api test_api_contract -v`
  Baseline before this feature: 232 tests.

## Review Focus

1. **Collection with >50 docs:** process-all/approve-all/status_counts must cover ALL docs, not just the first UI page → pinned by S-11 (same `status_counts` with `per_page=1` and default page) and S-06 (job `total` = real count).
2. **Re-pressing «process all» while a job is running:** exactly one worker may exist (idempotency) → pinned by S-07 (single job row, same `job_id`, 200 `resubmitted`).
3. **Pause mid-run:** clean stop (job `interrupted`, `[paused by user]`), no dangling `running` queue rows, resume re-runs only the remaining docs → pinned by S-08 (mocked pause check, deterministic).
4. **Approve-all while some docs are still `uploaded`:** only `parsed`/`needs_review` flip; `uploaded` docs are never retro-approved → pinned by S-10 (mixed-state assert + 409 on second call).
5. **Unknown collection id on any new endpoint:** 404 with `ok:false` (not 500) → pinned by S-05b + S-09b.

---

### Task 1: `status_counts` on the documents list

**Files:**
- Modify: `backend/knowledge_api.py` — `knowledge_list_documents` (lines 3363–3405)
- Test: `backend/test_studio_api.py` (new class at end, before `if __name__`)

**Interfaces:**
- Produces: documents-list response gains a top-level key `status_counts: dict[str, int]` — collection-wide per-status map from a single `GROUP BY status` query, independent of page/per_page/search/status filters. All later UI tasks read `state.docStatusCounts` populated from this key.

- [ ] **Step 1: Write the failing test** — append to `backend/test_studio_api.py`:

```python
class TestS11_StatusCounts(Base):
    """S-11: list documents carries server-side status_counts (page-independent)."""

    def test_s11_status_counts_match_db(self):
        self.login()
        coll = self.make_collection(slug="s11")
        self.upload(coll["id"], self._make_book("good.docx"))

        j = self.client.get(
            f"/api/knowledge/collections/{coll['id']}/documents"
        ).get_json()
        self.assertIn("status_counts", j)
        self.assertEqual(j["status_counts"].get("uploaded"), 1)

        conn = self._db()
        try:
            rows = conn.execute(
                "SELECT status, COUNT(*) n FROM knowledge_collection_documents"
                " WHERE collection_id=? GROUP BY status",
                (coll["collection_id"],)).fetchall()
            expected = {r["status"]: r["n"] for r in rows}
        finally:
            conn.close()
        self.assertEqual(j["status_counts"], expected)

        # page independence: identical map at per_page=1
        j2 = self.client.get(
            f"/api/knowledge/collections/{coll['id']}/documents?per_page=1"
        ).get_json()
        self.assertEqual(j2["status_counts"], expected)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m unittest test_studio_api.TestS11_StatusCounts -v`
Expected: FAIL — `AssertionError: 'status_counts' not found` (key absent).

- [ ] **Step 3: Implement in `knowledge_list_documents`**

After the `total` query (line ~3393), add a third query:

```python
        counts = db.execute(
            "SELECT status, COUNT(*) AS n FROM knowledge_collection_documents"
            " WHERE collection_id = ? GROUP BY status",
            (row["collection_id"],)).fetchall()
        status_counts = {c["status"]: c["n"] for c in counts}
```

and add `"status_counts": status_counts` to the final `jsonify(...)` (purely additive).

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m unittest test_studio_api.TestS11_StatusCounts -v`
Expected: PASS (1 test).

- [ ] **Step 5: Commit**

```bash
git add backend/knowledge_api.py backend/test_studio_api.py
git commit -m "feat(studio): S-11 server-side status_counts on documents list (page-independent, AGENTS §2.9)"
```

---

### Task 2: `process-all` endpoint + `process_collection` job kind

**Files:**
- Modify: `backend/knowledge_api.py` —
  - new helper `collection_scope()` next to `queue_scope()` (line 1033)
  - new worker `_job_kind_process_collection()` right after `_job_kind_process_batch` (ends line 2033)
  - registration in `_JOB_KINDS` (line 3021)
  - new route after `knowledge_approve_document` (line 3615)
- Test: `backend/test_studio_api.py` (new classes)

**Interfaces:**
- Produces:
  - `collection_scope(collection_id: str) -> str` — returns `f"collection:{collection_id}"`.
  - `_JOB_KINDS["process_collection"]` registered; job_key format `process_collection:<coll_id>`.
  - `POST /api/knowledge/collections/<int:coll_id>/documents/process-all` → 202 `{ok, job, files_queued, resubmitted:false}` / 200 `{ok, job, files_queued, resubmitted:true}` / 409 `{ok:false, code:"no_files_to_process", message}` / 404 / 401.
  - Task 3 (pause) and Task 6 (UI) rely on this job kind name and the 200-vs-202 contract.

- [ ] **Step 1: Write the failing tests** — append to `backend/test_studio_api.py`:

```python
class TestS05_ProcessAllValidation(Base):
    """S-05: process-all auth / 404 / 409."""

    def test_s05a_unauthenticated_401(self):
        r = self.client.post(
            "/api/knowledge/collections/1/documents/process-all")
        self.assertEqual(r.status_code, 401)

    def test_s05b_unknown_collection_404(self):
        self.login()
        r = self.client.post(
            "/api/knowledge/collections/999999/documents/process-all")
        self.assertEqual(r.status_code, 404)
        self.assertFalse(r.get_json()["ok"])

    def test_s05c_no_files_409(self):
        self.login()
        coll = self.make_collection(slug="s05c")
        r = self.client.post(
            f"/api/knowledge/collections/{coll['id']}/documents/process-all")
        self.assertEqual(r.status_code, 409, r.get_data(as_text=True))
        self.assertEqual(r.get_json()["code"], "no_files_to_process")


class TestS06_ProcessAllHappy(Base):
    """S-06: one job over all uploaded/failed docs, queue rows terminal."""

    def test_s06_two_books_processed(self):
        self.login()
        coll = self.make_collection(slug="s06")
        self.upload(coll["id"], self._make_book("one.docx"))
        self.upload(coll["id"], self._make_book("two.docx"))
        r = self.client.post(
            f"/api/knowledge/collections/{coll['id']}/documents/process-all")
        self.assertEqual(r.status_code, 202, r.get_data(as_text=True))
        j = r.get_json()
        self.assertTrue(j["ok"])
        self.assertEqual(j["files_queued"], 2)
        self.assertFalse(j["resubmitted"])
        row = self.wait_job(j["job"]["job_id"])
        self.assertEqual(row["status"], "succeeded", row)
        self.assertEqual(row["total"], 2)
        self.assertEqual(row["progress"], 2)
        docs = self._docs(coll["id"])
        self.assertEqual(len(docs), 2)
        for d in docs:
            self.assertIn(d["status"], ("parsed", "needs_review"), d)
        conn = self._db()
        try:
            n_open = conn.execute(
                "SELECT COUNT(*) n FROM knowledge_file_queue"
                " WHERE collection_id=? AND status IN ('pending','running')",
                (coll["collection_id"],)).fetchone()["n"]
        finally:
            conn.close()
        self.assertEqual(n_open, 0)


class TestS07_ProcessAllIdempotency(Base):
    """S-07: second POST while running -> same job, no second worker."""

    def test_s07_second_post_no_second_worker(self):
        self.login()
        coll = self.make_collection(slug="s07")
        self.upload(coll["id"], self._make_book("one.docx"))
        url = f"/api/knowledge/collections/{coll['id']}/documents/process-all"
        r1 = self.client.post(url)
        self.assertEqual(r1.status_code, 202, r1.get_data(as_text=True))
        r2 = self.client.post(url)
        self.assertEqual(r2.status_code, 200, r2.get_data(as_text=True))
        j2 = r2.get_json()
        self.assertTrue(j2["resubmitted"])
        self.assertEqual(j2["job"]["job_id"],
                         r1.get_json()["job"]["job_id"])
        row = self.wait_job(j2["job"]["job_id"])
        self.assertEqual(row["status"], "succeeded", row)
        jobs = self.client.get("/api/knowledge/jobs").get_json()["jobs"]
        mine = [x for x in jobs if x["kind"] == "process_collection"
                and x["collection_id"] == coll["collection_id"]]
        self.assertEqual(len(mine), 1)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m unittest test_studio_api.TestS05_ProcessAllValidation test_studio_api.TestS06_ProcessAllHappy test_studio_api.TestS07_ProcessAllIdempotency -v`
Expected: FAIL — 404s (route not registered) / `unknown job kind`.

- [ ] **Step 3: Implement**

(a) Helper after `queue_scope` (line ~1036):

```python
def collection_scope(collection_id):
    """PCM-STUDIO-BATCH — pause scope for a whole-collection job."""
    return f"collection:{collection_id}"
```

(b) Worker after `_job_kind_process_batch` (line 2033). Mirror that fn with the batch-specific parts removed — parse `coll = job_key.split(":", 1)[1]`, `scope = collection_scope(coll)`, then:

```python
    _queue_ensure_rows(conn, coll, None)
    docs = conn.execute(
        """SELECT document_id, file_name, sha256 FROM
             knowledge_collection_documents
            WHERE collection_id = ? AND status IN ('uploaded','failed')
            ORDER BY id""", (coll,)).fetchall()
    total = len(docs)
    paused_now = _now()
    for d in docs:
        if queue_is_paused(conn, scope):
            conn.execute(
                "UPDATE knowledge_jobs SET status='interrupted',"
                " error=COALESCE(error,'') || ' [paused by user]',"
                " stage='paused', updated_at=? WHERE job_id=?",
                (paused_now, job_id))
            conn.commit()
            return
        file_key = "f-" + d["sha256"][:8]
        on_stage = _queue_start(conn, coll, file_key, time.time())
        try:
            _process_document(conn, coll, d["document_id"],
                              on_stage=on_stage)
        except Exception as e:  # noqa: BLE001 — keep going, record per doc
            err = f"{type(e).__name__}: {e}"
            conn.execute(
                "UPDATE knowledge_collection_documents SET status='failed',"
                " error=?, updated_at=? WHERE document_id=?",
                (err, _now(), d["document_id"]))
            conn.commit()
            q = _queue_row(conn, coll, file_key)
            if q and q["status"] == "running":
                _queue_finish(conn, coll, file_key, "failed", error=err)
        done += 1
        _job_progress(conn, job_id, done, total,
                      f"document {d['document_id']}")
```

(`done = 0` before the loop; no batch tally — there is no `knowledge_import_batches` row.)

(c) Registration at line 3021:

```python
_JOB_KINDS["process_collection"] = _job_kind_process_collection
```

(d) Route after `knowledge_approve_document` (line 3615):

```python
    @app.route("/api/knowledge/collections/<int:coll_id>/documents/process-all",
               methods=["POST"])
    @require_auth
    def knowledge_process_all_documents(coll_id):
        """PCM-STUDIO-BATCH: one idempotent job over ALL uploaded/failed docs."""
        db = get_db()
        ensure_knowledge_schema(db)
        _recover_interrupted(db)
        row = _collection_row(db, coll_id)
        if not row:
            return jsonify({"ok": False, "message": "کالکشن پیدا نشد"}), 404
        n = db.execute(
            "SELECT COUNT(*) AS n FROM knowledge_collection_documents"
            " WHERE collection_id=? AND status IN ('uploaded','failed')",
            (row["collection_id"],)).fetchone()["n"]
        if n == 0:
            return jsonify({"ok": False, "code": "no_files_to_process",
                            "message": "هیچ سند پردازش‌نشده‌ای وجود ندارد"}), 409
        # re-pressing the button after a pause = resume
        queue_set_paused(db, collection_scope(row["collection_id"]), False)
        job, created = _submit_job(
            db, f"process_collection:{row['collection_id']}",
            "process_collection", row["collection_id"], None, total=n,
            idempotency_key=f"collection:{row['collection_id']}",
            force_retry=True)
        return jsonify({"ok": True, "job": job, "files_queued": n,
                        "resubmitted": not created}), (202 if created else 200)
```

`force_retry=True` (deliberate improvement over the batch endpoint): a previously `succeeded` job re-runs when new files exist (`n > 0` already guaranteed), while a `pending`/`running` job still returns the same row with no second worker.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m unittest test_studio_api.TestS05_ProcessAllValidation test_studio_api.TestS06_ProcessAllHappy test_studio_api.TestS07_ProcessAllIdempotency -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/knowledge_api.py backend/test_studio_api.py
git commit -m "feat(studio): process-all endpoint + process_collection job (S-05..S-07) — idempotent whole-collection processing with PCM-15 queue"
```

---

### Task 3: collection pause endpoint + deterministic pause/resume

**Files:**
- Modify: `backend/knowledge_api.py` — new route after the Task-2 process-all route
- Test: `backend/test_studio_api.py` (add `from unittest import mock` to imports)

**Interfaces:**
- Consumes: `collection_scope` (Task 2), the worker's per-file `queue_is_paused` check (Task 2).
- Produces: `POST /api/knowledge/collections/<int:coll_id>/documents/pause` → 200 `{ok:true, paused:true, scope, queue_control}` / 404 / 401. UI Task 6 binds `pauseAllBtn` to it.

- [ ] **Step 1: Write the failing test**

```python
class TestS08_PauseResume(Base):
    """S-08: pause endpoint sets the scope; paused run stops clean; resume finishes."""

    def test_s08_pause_stops_cleanly_and_resume_finishes(self):
        self.login()
        coll = self.make_collection(slug="s08")
        self.upload(coll["id"], self._make_book("one.docx"))
        self.upload(coll["id"], self._make_book("two.docx"))
        url = f"/api/knowledge/collections/{coll['id']}/documents"

        r = self.client.post(f"{url}/pause")
        self.assertEqual(r.status_code, 200, r.get_data(as_text=True))
        j = r.get_json()
        self.assertTrue(j["paused"])
        scope = f"collection:{coll['collection_id']}"
        self.assertEqual(j["scope"], scope)
        conn = self._db()
        try:
            row = conn.execute(
                "SELECT paused FROM knowledge_queue_control WHERE scope=?",
                (scope,)).fetchone()
        finally:
            conn.close()
        self.assertTrue(row and row["paused"])

        # paused run: the worker stops before the first file (deterministic)
        with mock.patch("knowledge_api.queue_is_paused",
                        return_value=True):
            r = self.client.post(f"{url}/process-all")
            self.assertEqual(r.status_code, 202, r.get_data(as_text=True))
            row = self.wait_job(r.get_json()["job"]["job_id"])
        self.assertEqual(row["status"], "interrupted", row)
        self.assertIn("paused", row["error"] or "")
        for d in self._docs(coll["id"]):
            self.assertEqual(d["status"], "uploaded")

        # resume: same endpoint clears the flag and re-executes the job
        r2 = self.client.post(f"{url}/process-all")
        self.assertEqual(r2.status_code, 202, r2.get_data(as_text=True))
        row2 = self.wait_job(r2.get_json()["job"]["job_id"])
        self.assertEqual(row2["status"], "succeeded", row2)
        for d in self._docs(coll["id"]):
            self.assertIn(d["status"], ("parsed", "needs_review"), d)
        conn = self._db()
        try:
            p = conn.execute(
                "SELECT paused FROM knowledge_queue_control WHERE scope=?",
                (scope,)).fetchone()
        finally:
            conn.close()
        self.assertFalse(p["paused"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m unittest test_studio_api.TestS08_PauseResume -v`
Expected: FAIL — 404 on `.../documents/pause` (route missing).

- [ ] **Step 3: Implement the route** (mirrors `knowledge_pause_batch`, line 4050):

```python
    @app.route("/api/knowledge/collections/<int:coll_id>/documents/pause",
               methods=["POST"])
    @require_auth
    def knowledge_pause_all_documents(coll_id):
        """PCM-STUDIO-BATCH: pause the whole-collection processing job."""
        db = get_db()
        ensure_knowledge_schema(db)
        _recover_interrupted(db)
        row = _collection_row(db, coll_id)
        if not row:
            return jsonify({"ok": False, "message": "کالکشن پیدا نشد"}), 404
        scope = collection_scope(row["collection_id"])
        queue_set_paused(db, scope, True)
        ctrl = db.execute(
            "SELECT paused, updated_at FROM knowledge_queue_control"
            " WHERE scope=?", (scope,)).fetchone()
        return jsonify({"ok": True, "paused": True, "scope": scope,
                        "queue_control": dict(ctrl)})
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m unittest test_studio_api.TestS08_PauseResume -v`
Expected: PASS (1 test).

- [ ] **Step 5: Commit**

```bash
git add backend/knowledge_api.py backend/test_studio_api.py
git commit -m "feat(studio): S-08 collection pause endpoint + clean stop/resume of process_collection job"
```

---

### Task 4: `approve-all` endpoint (atomic + audit)

**Files:**
- Modify: `backend/knowledge_api.py` — new route after the Task-3 pause route
- Test: `backend/test_studio_api.py` (add `import json` to imports)

**Interfaces:**
- Consumes: `_collection_row`, `_refresh_book_count`, `_audit_log(db, collection_id, stage, action, status, detail)` (line 958).
- Produces: `POST /api/knowledge/collections/<int:coll_id>/documents/approve-all` → 200 `{ok:true, approved:n}` / 409 `{ok:false, code:"no_docs_to_approve", message}` / 404 / 401. UI Task 6 binds `apprAllBtn` to it and shows `j.approved`.

- [ ] **Step 1: Write the failing tests**

```python
class TestS09_ApproveAllValidation(Base):
    """S-09: approve-all auth / 404 / 409."""

    def test_s09a_unauthenticated_401(self):
        r = self.client.post(
            "/api/knowledge/collections/1/documents/approve-all")
        self.assertEqual(r.status_code, 401)

    def test_s09b_unknown_collection_404(self):
        self.login()
        r = self.client.post(
            "/api/knowledge/collections/999999/documents/approve-all")
        self.assertEqual(r.status_code, 404)
        self.assertFalse(r.get_json()["ok"])

    def test_s09c_no_candidates_409(self):
        self.login()
        coll = self.make_collection(slug="s09c")
        r = self.client.post(
            f"/api/knowledge/collections/{coll['id']}/documents/approve-all")
        self.assertEqual(r.status_code, 409, r.get_data(as_text=True))
        self.assertEqual(r.get_json()["code"], "no_docs_to_approve")


class TestS10_ApproveAllHappy(Base):
    """S-10: only parsed/needs_review flip; uploaded untouched; one audit row."""

    def test_s10_approves_only_parsed_and_needs_review(self):
        self.login()
        coll = self.make_collection(slug="s10")
        self.upload(coll["id"], self._make_book("one.docx"))
        r = self.client.post(
            f"/api/knowledge/collections/{coll['id']}/documents/process-all")
        self.assertEqual(r.status_code, 202, r.get_data(as_text=True))
        self.wait_job(r.get_json()["job"]["job_id"])
        # second doc stays 'uploaded' — not a candidate
        self.upload(coll["id"], self._make_book("two.docx"))

        r = self.client.post(
            f"/api/knowledge/collections/{coll['id']}/documents/approve-all")
        self.assertEqual(r.status_code, 200, r.get_data(as_text=True))
        self.assertEqual(r.get_json()["approved"], 1)
        statuses = sorted(d["status"] for d in self._docs(coll["id"]))
        self.assertEqual(statuses, ["approved", "uploaded"])

        conn = self._db()
        try:
            rows = conn.execute(
                "SELECT detail_json FROM knowledge_audit_log"
                " WHERE collection_id=? AND action='approved_all'",
                (coll["collection_id"],)).fetchall()
        finally:
            conn.close()
        self.assertEqual(len(rows), 1)
        self.assertEqual(json.loads(rows[0]["detail_json"])["count"], 1)

        r2 = self.client.post(
            f"/api/knowledge/collections/{coll['id']}/documents/approve-all")
        self.assertEqual(r2.status_code, 409)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m unittest test_studio_api.TestS09_ApproveAllValidation test_studio_api.TestS10_ApproveAllHappy -v`
Expected: FAIL — 404s (route missing).

- [ ] **Step 3: Implement the route**

```python
    @app.route("/api/knowledge/collections/<int:coll_id>/documents/approve-all",
               methods=["POST"])
    @require_auth
    def knowledge_approve_all_documents(coll_id):
        """PCM-STUDIO-BATCH: atomically approve every parsed/needs_review doc."""
        db = get_db()
        ensure_knowledge_schema(db)
        row = _collection_row(db, coll_id)
        if not row:
            return jsonify({"ok": False, "message": "کالکشن پیدا نشد"}), 404
        n = db.execute(
            "SELECT COUNT(*) AS n FROM knowledge_collection_documents"
            " WHERE collection_id=? AND status IN ('parsed','needs_review')",
            (row["collection_id"],)).fetchone()["n"]
        if n == 0:
            return jsonify({"ok": False, "code": "no_docs_to_approve",
                            "message": "هیچ سند parsed/needs_review "
                                       "برای تأیید وجود ندارد"}), 409
        db.execute(
            "UPDATE knowledge_collection_documents"
            " SET status='approved', updated_at=?"
            " WHERE collection_id=? AND status IN ('parsed','needs_review')",
            (_now(), row["collection_id"]))
        _refresh_book_count(db, row["collection_id"])
        _audit_log(db, row["collection_id"], "documents", "approved_all",
                   "ok", {"count": n})
        db.commit()
        return jsonify({"ok": True, "approved": n})
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m unittest test_studio_api.TestS09_ApproveAllValidation test_studio_api.TestS10_ApproveAllHappy -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/knowledge_api.py backend/test_studio_api.py
git commit -m "feat(studio): approve-all endpoint (S-09/S-10) — atomic parsed/needs_review flip + audit row approved_all"
```

---

### Task 5: OpenAPI contract for the three new operations

**Files:**
- Modify: `docs/openapi/pcm15-file-queue.openapi.yaml` (queue/pause-control spec — already declares `QueueControl`, `Unauthorized`, `NotFound`)

**Interfaces:**
- Consumes: the three routes from Tasks 2–4 (exact paths/statuses as specified there).
- Produces: machine-enforced contract — `test_api_contract.py` (CT-01..CT-06) and `deploy/pcm19_openapi_check.py` pass with the new operations.

- [ ] **Step 1: Add the three operations** — new paths block (insert before `components:`):

```yaml
  /api/knowledge/collections/{coll_id}/documents/process-all:
    post:
      tags: [queue]
      operationId: processAllDocuments
      summary: Process ALL uploaded/failed documents of a collection (one idempotent job)
      parameters:
        - { name: coll_id, in: path, required: true, schema: { type: integer } }
      responses:
        "200":
          description: Job already pending/running — same job returned (resubmitted)
          content:
            application/json:
              schema:
                type: object
                properties:
                  ok: { type: boolean, example: true }
                  job: { type: object }
                  files_queued: { type: integer, example: 2 }
                  resubmitted: { type: boolean, example: true }
        "202":
          description: Job created and worker started
          content:
            application/json:
              schema:
                type: object
                properties:
                  ok: { type: boolean, example: true }
                  job: { type: object }
                  files_queued: { type: integer, example: 2 }
                  resubmitted: { type: boolean, example: false }
        "401": { $ref: "#/components/responses/Unauthorized" }
        "404": { $ref: "#/components/responses/NotFound" }
        "409":
          description: Nothing to process
          content:
            application/json:
              schema:
                type: object
                properties:
                  ok: { type: boolean, example: false }
                  code: { type: string, example: no_files_to_process }
                  message: { type: string }
  /api/knowledge/collections/{coll_id}/documents/pause:
    post:
      tags: [queue]
      operationId: pauseCollectionDocuments
      summary: Pause the whole-collection processing job (clean stop at next file boundary)
      parameters:
        - { name: coll_id, in: path, required: true, schema: { type: integer } }
      responses:
        "200":
          description: Pause flag set (scope = collection:<coll_id>)
          content:
            application/json:
              schema:
                type: object
                properties:
                  ok: { type: boolean, example: true }
                  paused: { type: boolean, example: true }
                  scope: { type: string, example: "collection:c-01234567" }
                  queue_control: { $ref: "#/components/schemas/QueueControl" }
        "401": { $ref: "#/components/responses/Unauthorized" }
        "404": { $ref: "#/components/responses/NotFound" }
  /api/knowledge/collections/{coll_id}/documents/approve-all:
    post:
      tags: [queue]
      operationId: approveAllDocuments
      summary: Atomically approve every parsed/needs_review document (audit-logged)
      parameters:
        - { name: coll_id, in: path, required: true, schema: { type: integer } }
      responses:
        "200":
          description: All candidate documents approved
          content:
            application/json:
              schema:
                type: object
                properties:
                  ok: { type: boolean, example: true }
                  approved: { type: integer, example: 5 }
        "401": { $ref: "#/components/responses/Unauthorized" }
        "404": { $ref: "#/components/responses/NotFound" }
        "409":
          description: No parsed/needs_review documents to approve
          content:
            application/json:
              schema:
                type: object
                properties:
                  ok: { type: boolean, example: false }
                  code: { type: string, example: no_docs_to_approve }
                  message: { type: string }
```

- [ ] **Step 2: Run the contract tests**

Run: `cd backend && python -m unittest test_api_contract -v`
Expected: PASS (18 tests — CT-02 sees the new routes, CT-03 sees 401s, CT-06 sees unique operationIds).

- [ ] **Step 3: Run the CI OpenAPI checker**

Run: `python deploy/pcm19_openapi_check.py`
Expected: PASS (prints ok for all specs).

- [ ] **Step 4: Commit**

```bash
git add docs/openapi/pcm15-file-queue.openapi.yaml
git commit -m "docs(openapi): declare process-all / pause / approve-all operations (CT-01..CT-06 enforced)"
```

---

### Task 6: UI toolbar buttons + live counters (dashboard/studio.html)

**Files:**
- Modify: `dashboard/studio.html` — `.doc-toolbar` (lines 333–345), `renderDocs()` (1376), `refreshJobs()` (1593), trigger section (1620)

**Interfaces:**
- Consumes: `status_counts` (Task 1), process-all/pause/approve-all endpoints (Tasks 2–4), job list with `kind`/`collection_id` fields (existing `GET /api/knowledge/jobs`).
- Produces: three toolbar buttons `#procAllBtn` (label `#procAllLabel`), `#pauseAllBtn`, `#apprAllBtn` (label `#apprAllLabel`); `state.docStatusCounts`; `state.collJobActive`; functions `updateDocsToolbar()`, `triggerProcessAll()`, `triggerPauseAll()`, `triggerApproveAll()`.

- [ ] **Step 1: Add the toolbar buttons** — inside `.doc-toolbar` (line 333), after the `importBtn` button (line 342), before the spacer:

```html
          <button type="button" class="btn" id="procAllBtn" disabled>
            <svg class="icon" viewBox="0 0 24 24" aria-hidden="true"><path d="m5 3 14 9-14 9V3Z"/></svg>
            <span id="procAllLabel">پردازش همه (۰)</span>
          </button>
          <button type="button" class="btn" id="pauseAllBtn" disabled>
            <svg class="icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M8 5v14M16 5v14"/></svg>
            توقف پردازش
          </button>
          <button type="button" class="btn" id="apprAllBtn" disabled>
            <svg class="icon" viewBox="0 0 24 24" aria-hidden="true"><path d="m4 12 5 5L20 6"/></svg>
            <span id="apprAllLabel">تأیید همه (۰)</span>
          </button>
```

- [ ] **Step 2: Add the JS** — in `renderDocs()` (after `state.docsTotal = ...`, line 1384) store `state.docStatusCounts = j.status_counts || {};` and call `updateDocsToolbar();` at the end of the try block (after row bindings). In `refreshJobs()` compute, before the existing timer logic:

```js
    state.collJobActive = active.some((x) =>
      x.kind === 'process_collection' && x.collection_id === state.activeId);
    updateDocsToolbar();
```

and extend the self-rescheduling timer so that while `state.collJobActive` is true it ALSO re-renders the docs (so statuses/counters update live):

```js
    if (active.length) {
      if (!state._jobTimer) state._jobTimer = setTimeout(() => {
        state._jobTimer = null;
        refreshJobs();
        if (state.collJobActive) renderDocs();
      }, 2500);
    }
```

New functions (next to `triggerProcess`, line 1620):

```js
function updateDocsToolbar() {
  const sc = state.docStatusCounts || {};
  const np = (sc.uploaded || 0) + (sc.failed || 0);
  const na = (sc.parsed || 0) + (sc.needs_review || 0);
  const pb = $('procAllBtn'), ab = $('apprAllBtn'), pab = $('pauseAllBtn');
  if (!pb) return;
  pb.disabled = np <= 0;
  $('procAllLabel').textContent = 'پردازش همه (' + faNum(np) + ')';
  ab.disabled = na <= 0;
  $('apprAllLabel').textContent = 'تأیید همه (' + faNum(na) + ')';
  pab.disabled = !state.collJobActive;
}
async function triggerProcessAll() {
  try {
    const j = await fetchAPI('/api/knowledge/collections/' + state.activeId +
      '/documents/process-all', { method: 'POST' });
    toast('پردازش ' + faNum(j.files_queued) + ' سند آغاز شد');
    refreshJobs();
  } catch (e) { toast(e.message, 'err'); }
}
async function triggerPauseAll() {
  try {
    await fetchAPI('/api/knowledge/collections/' + state.activeId +
      '/documents/pause', { method: 'POST' });
    toast('توقف پس از پایان سند جاری ثبت شد');
    refreshJobs();
  } catch (e) { toast(e.message, 'err'); }
}
async function triggerApproveAll() {
  try {
    const j = await fetchAPI('/api/knowledge/collections/' + state.activeId +
      '/documents/approve-all', { method: 'POST' });
    toast(faNum(j.approved) + ' سند تأیید شد');
    await renderDocs();
  } catch (e) { toast(e.message, 'err'); }
}
```

- [ ] **Step 3: Bind the handlers** — wherever `importBtn` gets its click listener (search `importBtn` in the script block), add beside it:

```js
$('procAllBtn').addEventListener('click', () => triggerProcessAll());
$('pauseAllBtn').addEventListener('click', () => triggerPauseAll());
$('apprAllBtn').addEventListener('click', () => triggerApproveAll());
```

- [ ] **Step 4: Syntax-verify the inline script** (no browser in this step; live UI check happens at staging deploy):

Run:
```
node -e "const fs=require('fs');const h=fs.readFileSync('dashboard/studio.html','utf8');const m=h.match(/<script>([\s\S]*?)<\/script>/g);const code=m[m.length-1].replace(/<\/?script>/g,'');new Function(code);console.log('studio.html script OK')"
```
Expected: `studio.html script OK`.

- [ ] **Step 5: Commit**

```bash
git add dashboard/studio.html
git commit -m "feat(studio-ui): toolbar buttons پردازش همه / توقف پردازش / تأیید همه with server-side live counters"
```

---

### Task 7: Full regression + report + push

**Files:**
- Modify: `docs/PCM-STUDIO-BATCH-REPORT.md` (new — 11-section AGENTS report style, short: scope, design ref, API table, test results, SHA, git status, no-deploy note)
- Modify: `AGENTS.md` §6 roadmap — new row: `PCM-STUDIO-BATCH | ✅ (N تست S + 232 رگرسیون سبز؛ بدون deploy — سوار درِ M7)`

**Interfaces:**
- Consumes: all of Tasks 1–6.
- Produces: green regression evidence + pushed commits.

- [ ] **Step 1: Run the FULL regression**

Run:
```
cd backend && python -m unittest test_api test_projects test_dashboard test_knowledge_api test_word_factory test_dump test_work_registry test_queue test_corpus_builder test_studio_api test_api_contract -v
```
Expected: **243 tests, 0 failures, 0 errors, 0 skips** (232 baseline + 11 new S-tests).

- [ ] **Step 2: Write the report** — `docs/PCM-STUDIO-BATCH-REPORT.md`: what/why, the 3 endpoints + job kind, test table (S-05..S-11 with pass counts), regression 243 result, commit SHAs, `git status --short` (clean), deployment note (rides the open M7 s52 gate; staging-first recommended for owner UI verification).

- [ ] **Step 3: Commit + push**

```bash
git add docs/PCM-STUDIO-BATCH-REPORT.md AGENTS.md
git commit -m "docs: PCM-STUDIO-BATCH report (11 new S tests + 243 regression green) + AGENTS roadmap row — no deploy (M7 gate)"
git push origin pcm-20.9-knowledge-studio-factory
```

- [ ] **Step 4: Verify clean tree**

Run: `git status --short && git log --oneline -8`
Expected: empty status; the 7 feature commits visible on top of `92439ee`.

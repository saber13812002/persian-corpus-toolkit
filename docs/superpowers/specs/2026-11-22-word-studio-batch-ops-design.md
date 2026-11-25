# Word Studio — Bulk «Process All» / «Approve All» (design)

Date: 2026-11-22 · Branch: `pcm-20.9-knowledge-studio-factory` · Status: DRAFT (awaiting owner approval)

## 1. Problem

In the Word Library (کتابخانهٔ Word, `dashboard/studio.html`) every uploaded
document requires three manual steps: click the row → press «پردازش» → later
press «تأیید سند». With dozens of files this is tedious. The owner wants
one-click batch operations:

- a «process all unprocessed files» action
- an «approve all unapproved» action

Owner decision (brainstorming, 2026-11-22): **Method B — two backend
endpoints + toolbar buttons** (server-side counts, because the UI document
list is capped at 50 rows per page and a client-only batch would silently
skip documents beyond page 1).

## 2. What exists today (recon findings)

- Doc statuses (`knowledge_api.py:60`): `uploaded, validating, parsing,
  parsed, needs_review, approved, indexing, indexed, failed`.
- Per-doc: `POST /api/knowledge/documents/<id>/process` (idempotent job) and
  `POST /api/knowledge/documents/<id>/approve` (single-row UPDATE).
- Job machinery (PCM-15): `knowledge_jobs` rows + daemon worker thread
  (`_job_worker`, `_submit_job` with idempotency/retry, `_start_worker`,
  `_job_progress`). Kind dispatch by `job_key.split(":")[0]` into
  `_JOB_KINDS`.
- Per-file queue `knowledge_file_queue` (keyed `collection_id, file_key=
  f-<sha8>`) with stage tracking; `_queue_ensure_rows(conn, coll, batch_id)`
  with `batch_id=None` already yields whole-collection semantics (the
  `_batch_scope_clause` returns no clause for an unknown batch).
- Pause control `knowledge_queue_control` (`scope TEXT PRIMARY KEY`,
  currently only `'batch:<id>'`); `queue_is_paused` / `queue_set_paused` /
  `queue_scope` helpers.
- `GET /api/knowledge/collections/<id>/documents` returns a page of ≤100
  rows + `total`; **no per-status counts** — the UI only ever fetches 50.
- UI: `#docsCard` toolbar (`.doc-toolbar`, `studio.html:333`) currently has
  only upload / multi-import / total badge. Active jobs render in `#jobsPane`
  with a 2.5 s self-rescheduling poll (`refreshJobs`).

## 3. Design (Method B)

### 3.1 API — three new endpoints (all `@require_auth`, inside
`register_knowledge_routes`, placed right after the single-doc
process/approve routes)

1. `POST /api/knowledge/collections/<int:coll_id>/documents/process-all`
   - Counts docs `status IN ('uploaded','failed')` of the collection.
   - 409 `{ok:false, code:"no_files_to_process"}` when 0.
   - Clears the collection pause flag (`queue_set_paused(scope, False)`) so
     that **re-pressing the button after a pause = resume**.
   - Submits ONE job: `_submit_job(db, f"process_collection:{coll_id}",
     "process_collection", coll_id, None, total=n,
     idempotency_key=f"collection:{coll_id}")`.
   - 202 on first submit, 200 when resubmitted (existing row returned),
     same contract as `knowledge_process_batch`.

2. `POST /api/knowledge/collections/<int:coll_id>/documents/pause`
   - Sets the pause flag for scope `collection:<coll_id>`. The worker stops
     cleanly after the current file (remaining files stay `uploaded`),
     marks the job `interrupted` (retryable). Response: `{ok, paused:true,
     scope}` — mirrors the batch pause endpoint.

3. `POST /api/knowledge/collections/<int:coll_id>/documents/approve-all`
   - Synchronous (no job): one atomic
     `UPDATE ... SET status='approved' WHERE collection_id=? AND status IN
     ('parsed','needs_review')`.
   - 409 `{ok:false, code:"no_docs_to_approve"}` when 0 candidates.
   - `_refresh_book_count` once after the update + one append-only
     `knowledge_audit_log` row (`stage="documents"`,
     `action="approved_all"`, detail `{"count": n}`) — approvals are a
     human decision and belong in the trail.
   - Response: `{ok:true, approved:n}`.

### 3.2 New job kind `process_collection`

New worker fn `_job_kind_process_collection(conn, job_id)` in
`knowledge_api.py`, registered in `_JOB_KINDS` (alongside the existing
kinds). Structure mirrors `_job_kind_process_batch` with the batch-specific
parts removed:

- Read `job_key` → coll_id (format `process_collection:<coll_id>`),
  `scope = f"collection:{coll_id}"`.
- `_queue_ensure_rows(conn, coll, None)` → one pending queue row per
  `uploaded`/`failed` doc (idempotent ON CONFLICT).
- Select the work list: `WHERE collection_id=? AND status IN
  ('uploaded','failed') ORDER BY id` (re-evaluated at job start → a resumed
  job naturally sees only the remaining docs).
- Loop per doc: pause check first (paused → set job `interrupted`,
  `stage='paused'`, error note, return); else `_queue_start` +
  `_process_document(conn, coll, doc_id, on_stage=...)` with the same
  safety-net finalization as the batch worker; per-doc failure does NOT stop
  the job (recorded on the doc + queue row).
- `_job_progress` after each doc (the existing `#jobsPane` progress bar
  works unchanged).
- No `knowledge_import_batches` row exists → no batch tally.

### 3.3 Additive list field `status_counts`

`knowledge_list_documents` additionally returns `status_counts`: a
collection-wide per-status map (single `GROUP BY status` query, always
computed, independent of the 50/100-row page cap). Example:
`{"uploaded":3,"failed":1,"parsed":5,"needs_review":2,"approved":40,...}`.
Purely additive — existing consumers unaffected; CT-04 (spec⊆live) still
passes.

### 3.4 UI (`dashboard/studio.html`, `#docsCard` toolbar)

Three buttons in `.doc-toolbar` (before the spacer/badge), Persian labels:

| id | label | enabled when |
|----|-------|--------------|
| `procAllBtn` | `پردازش همه (N)` | `status_counts.uploaded + failed > 0` |
| `pauseAllBtn` | `توقف پردازش` | a `process_collection` job for the active collection is `pending`/`running` |
| `apprAllBtn` | `تأیید همه (M)` | `status_counts.parsed + needs_review > 0` |

- Counts are Persian numerals (`faNum`) from the **server-side**
  `status_counts`; buttons disabled at 0 (single source of truth, AGENTS
  §2.9 — no fabricated stats).
- `renderDocs()` stores `state.docStatusCounts` and calls a small
  `updateDocsToolbar()`.
- `triggerProcessAll()` → POST process-all → toast + `refreshJobs()`; the
  existing 2.5 s job poll is extended: while a `process_collection` job of
  the active collection is active it also re-runs `renderDocs()` so
  statuses (and the approve-all counter) update live.
- `triggerPauseAll()` → POST pause → toast «توقف پس از پایان سند جاری
  ثبت شد».
- `triggerApproveAll()` → POST approve-all → toast «N سند تأیید شد» (409 →
  message toast) → re-render.

## 4. Non-goals / out of scope

- No changes to the per-document flow (detail-panel buttons stay).
- No indexing/build changes; approve-all does NOT trigger corpus build or
  ES index (those remain explicit pipeline steps).
- No new DB schema: `knowledge_queue_control` already exists; the
  `collection:<cid>` scope is just a new row value (additive, no migration).
- No retry-failed-for-collection endpoint (the batch one stays batch-scoped;
  a failed doc can be re-processed via process-all or the per-doc button —
  the job re-selects `failed` docs).
- No changes to `extension/` (studio is a dashboard feature).

## 5. Tests (extend `backend/test_studio_api.py`, IDs continue S-05…)

- **S-05** process-all: 401 unauthenticated; 409 `no_files_to_process` on an
  empty/fully-processed collection.
- **S-06** process-all happy path: upload 2 real sample books (distinct
  SHAs), POST → 202, wait job `succeeded`, both docs `parsed`/
  `needs_review`, queue rows terminal, job progress/total correct.
- **S-07** idempotency: second POST while running (or after success with no
  new files) → 200 `resubmitted:true`, no second worker, no doc re-run
  (progress/attempts unchanged for already-parsed docs).
- **S-08** pause/resume: pause mid-run (or before start) → job
  `interrupted`; re-POST process-all → job resumes and finishes the
  remaining docs (remaining count = expected).
- **S-09** approve-all: 409 `no_docs_to_approve` when nothing is
  parsed/needs_review.
- **S-10** approve-all happy path: after S-06-style processing, POST →
  `approved == expected count`; DB shows all `approved`; audit log gained
  exactly one `approved_all` row with the right count; re-POST → 409.
- **S-11** `status_counts` in the documents list matches a direct DB
  `GROUP BY` recompute (page-cap independence: >50 docs if feasible, else
  assert exact map on the test set).
- **S-12** new endpoints 404 for an unknown collection id.

Regression: full suite green (baseline 232 + new tests) via the AGENTS §4
command (with the new file already included in `test_studio_api.py`).

## 6. OpenAPI (PCM-19 contract)

Add the 3 operations to the spec that already declares the collection
documents surface (verify at impl: `docs/openapi/pcm209-pipeline-release.
openapi.yaml` vs `pcm15-file-queue.openapi.yaml`) with operationIds,
request/response schemas (`ProcessAllResult`, `ApproveAllResult`,
`PauseResult`), 409 error models, and `201/202/200/404/401` responses.
CT-01..CT-06 then automatically cover the new ops (401 contract, spec⊆app,
operationId uniqueness).

## 7. Deployment

Code-only, additive. No schema migration, no data migration. Rides the
still-open **M7 s52 production code-deploy gate** (owner approval
required); deploy follows the AGENTS §3 standard sequence (DB backup,
image build, `up -d backend`, smoke, integrity check). Staging deploy first
for owner verification is recommended.

## 8. Risks / mitigations

- **Long job, no progress feedback** → the existing `#jobsPane` bar +
  live `renderDocs` refresh cover it; pause gives a clean stop.
- **Two workers at once** → `_submit_job` idempotency on
  `process_collection:<cid>` guarantees a single live worker.
- **Crash mid-run** → PCM-15 recovery (`_recover_interrupted`) + queue rows
  persist; restart re-runs the job, already-parsed docs are skipped by
  status, in-flight file resumes from its last safe stage.
- **approve-all while a job is still parsing** → only `parsed`/
  `needs_review` are approved; later-parsed docs are not retro-approved
  (documented behaviour; user presses approve-all again — the button
  re-enables as the counters update live).

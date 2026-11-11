# -*- coding: utf-8 -*-
"""PCM-20.9 — pipeline orchestration (Full Pipeline runner + Nightly).

This module does NOT reimplement any stage: it orchestrates the existing
knowledge_api primitives (the job engine, the per-file queue, the schema
lifecycle, the Stage D corpus build, the Stage E search acceptance, the
release bundle) into one checkpointed, resumable, pausable run per
collection.

Stage machine (in order):
    A_IMPORT -> B_PROCESS -> C_SCHEMA -> D_BUILD -> E_ACCEPT -> RELEASE

Rules (see PCM-20.9-RECON.md §8):
- Per-collection singleton: one run at a time. The run row itself is the
  lock; a second start while a run is active -> 409 conflicting_job.
- Checkpoints: each stage's terminal state is persisted in the run row's
  `stage_states` JSON. A re-run (or a resume after a pause) skips stages
  that already reached SUCCESS; `from_stage` additionally resets the
  stages at/after the given stage.
- Pause/resume: `pause` flips the run to 'paused'; the running worker
  notices on its next poll and interrupts its own job (retryable).
  `resume` re-submits the same job key (force_retry) — checkpointed
  (SUCCESS) stages are not re-executed.
- Honest outcomes: a stage ends SUCCESS / FAILED / BLOCKED / NEEDS_REVIEW.
  BLOCKED and NEEDS_REVIEW are recorded and the run CONTINUES (e.g. Stage E
  is blocked without PCT_ES_URL, but the release can still be built);
  only FAILED stops the run.
- No ES/RAG URLs are fabricated: every guarded outcome is recorded as
  'blocked' in the underlying build/release rows.

All pipeline tables are additive (CREATE TABLE IF NOT EXISTS only) and are
keyed by the STRING collection_id (c-...), like every other knowledge_*
child table.
"""
import hashlib
import json
import re
import time

import knowledge_api as ka
from auth import make_require_auth
from flask import jsonify, request

# (key, human label) — the tuple order IS the stage order
STAGES = (
    ("A_IMPORT", "import"),
    ("B_PROCESS", "process"),
    ("C_SCHEMA", "schema"),
    ("D_BUILD", "corpus build"),
    ("E_ACCEPT", "search acceptance"),
    ("RELEASE", "release"),
)
STAGE_KEYS = tuple(k for k, _ in STAGES)

# cron_time validation: HH:MM wall-clock time, 24h
CRON_RE = re.compile(r"([01]\d|2[0-3]):[0-5]\d")

# a sub-stage (job) that takes 30+ minutes is stuck
_STAGE_TIMEOUT = 1800.0


# ---------------------------------------------------------------------------
# schema (additive, AGENTS rule 2: CREATE TABLE IF NOT EXISTS only)
# ---------------------------------------------------------------------------

def ensure_pipeline_schema(db):
    """Additive DDL for the orchestration tables."""
    db.execute(
        """CREATE TABLE IF NOT EXISTS knowledge_pipeline_runs (
             run_id TEXT PRIMARY KEY,
             collection_id TEXT NOT NULL UNIQUE,
             trigger_type TEXT NOT NULL DEFAULT 'manual',
             status TEXT NOT NULL DEFAULT 'running',
             stage_states TEXT NOT NULL DEFAULT '{}',
             started_stage TEXT,
             error TEXT,
             job_id TEXT,
             created_at TEXT,
             updated_at TEXT,
             finished_at TEXT
           )""")
    db.execute(
        """CREATE TABLE IF NOT EXISTS knowledge_pipeline_schedules (
             collection_id TEXT PRIMARY KEY,
             enabled INTEGER NOT NULL DEFAULT 0,
             cron_time TEXT NOT NULL DEFAULT '03:00',
             updated_at TEXT,
             last_run_at TEXT,
             last_status TEXT
           )""")
    db.commit()


# ---------------------------------------------------------------------------
# run-row helpers
# ---------------------------------------------------------------------------

def _run_id(cid):
    """Deterministic run id: one run row per collection (the lock)."""
    return "pr-" + hashlib.sha256(cid.encode("utf-8")).hexdigest()[:8]


def _run_row(conn, cid):
    r = conn.execute(
        "SELECT * FROM knowledge_pipeline_runs WHERE collection_id=?",
        (cid,)).fetchone()
    return dict(r) if r else None


def _run_status(conn, cid):
    r = conn.execute(
        "SELECT status FROM knowledge_pipeline_runs WHERE collection_id=?",
        (cid,)).fetchone()
    return r["status"] if r else None


def _new_state():
    return {"status": "NOT_STARTED", "detail": None, "error": None,
            "job_id": None, "started_at": None, "updated_at": None}


def _load_states(run):
    """Parse stage_states JSON; every stage key is always present."""
    states = {}
    try:
        states = json.loads(run["stage_states"] or "{}")
    except (TypeError, ValueError):
        states = {}
    if not isinstance(states, dict):
        states = {}
    for skey, _label in STAGES:
        if not isinstance(states.get(skey), dict):
            states[skey] = _new_state()
    return states


def _persist_states(conn, run_id, states):
    conn.execute(
        "UPDATE knowledge_pipeline_runs SET stage_states=?, updated_at=? "
        "WHERE run_id=?",
        (json.dumps(states, ensure_ascii=False), ka._now(), run_id))
    conn.commit()


def _finish_run(conn, run_id, status, error=None):
    """Terminal run update. Conditional on status='running': if a pause
    won the race in the last moment, the run stays 'paused' and a resume
    will re-derive the outcome from the checkpointed stage states."""
    conn.execute(
        "UPDATE knowledge_pipeline_runs SET status=?, error=?, updated_at=?, "
        "finished_at=? WHERE run_id=? AND status='running'",
        (status, error, ka._now(), ka._now(), run_id))
    conn.commit()


def _interrupt_pipeline_job(conn, job_id):
    """Self-interrupt the pipeline job (clean pause; retryable)."""
    conn.execute(
        "UPDATE knowledge_jobs SET status='interrupted', "
        "error=COALESCE(error,'') || ' [pipeline paused]', updated_at=? "
        "WHERE job_id=? AND status IN ('pending','running')",
        (ka._now(), job_id))
    conn.commit()


def _job_dead_or_stale(conn, job_id):
    """True when the job no longer has a live worker: missing, in a
    terminal state, or not updated within STUCK_AFTER_MOD (SQL-side
    comparison — immune to client clock skew)."""
    if not job_id:
        return True
    r = conn.execute(
        "SELECT status FROM knowledge_jobs WHERE job_id=?",
        (job_id,)).fetchone()
    if not r:
        return True
    if r["status"] in ("succeeded", "failed", "interrupted"):
        return True
    stale = conn.execute(
        "SELECT 1 AS x FROM knowledge_jobs WHERE job_id=? "
        "AND updated_at < datetime('now', ?)",
        (job_id, ka.STUCK_AFTER_MOD)).fetchone()
    return bool(stale)


def _wait_subjob(conn, subjob_id, cid, timeout=_STAGE_TIMEOUT, interval=0.3):
    """Poll a sub-job to a terminal state.

    Returns the job row (dict) when terminal; None when the RUN was paused
    in the meantime (the caller then self-interrupts the pipeline job).
    Raises TimeoutError when the sub-job is stuck beyond `timeout`.
    """
    deadline = time.time() + timeout
    while True:
        if _run_status(conn, cid) == "paused":
            return None
        row = conn.execute(
            "SELECT * FROM knowledge_jobs WHERE job_id=?",
            (subjob_id,)).fetchone()
        if row is None:
            return None
        if row["status"] in ("succeeded", "failed", "interrupted"):
            return dict(row)
        if time.time() >= deadline:
            raise TimeoutError("sub-job " + str(subjob_id) + " did not finish")
        # release any read transaction before sleeping (WAL hygiene)
        conn.commit()
        time.sleep(interval)


def _newest_build(conn, cid):
    r = conn.execute(
        """SELECT * FROM knowledge_index_builds
           WHERE collection_id=? AND content_sha256 IS NOT NULL
           ORDER BY created_at DESC, iv_id DESC LIMIT 1""", (cid,)).fetchone()
    return dict(r) if r else None


def _newest_release(conn, cid):
    r = conn.execute(
        "SELECT * FROM knowledge_releases WHERE collection_id=? "
        "ORDER BY created_at DESC, release_id DESC LIMIT 1",
        (cid,)).fetchone()
    return dict(r) if r else None


def _pipeline_batch_id(cid):
    """The deterministic plan-row-less batch the pipeline uses for Stage B.

    No knowledge_batch_files rows -> _batch_scope_clause returns ("", [])
    -> whole-collection semantics: every uploaded/failed document is
    processed, exactly like the legacy PCM-15 flow.
    """
    return "b-" + hashlib.sha256(
        (cid + ":pipeline").encode("utf-8")).hexdigest()[:8]


# ---------------------------------------------------------------------------
# stage handlers — each returns (status, detail, subjob_id, error)
#   status in: SUCCESS / FAILED / BLOCKED / NEEDS_REVIEW / PAUSED
# ---------------------------------------------------------------------------

def _stage_a_import(conn, cid, state):
    row = conn.execute(
        """SELECT COUNT(*) AS n,
                  SUM(CASE WHEN status IN ('uploaded','failed')
                      THEN 1 ELSE 0 END) AS up
           FROM knowledge_collection_documents WHERE collection_id=?""",
        (cid,)).fetchone()
    n = row["n"] or 0
    if n == 0:
        return ("FAILED", None, None,
                "no documents imported — upload at least one file (Stage A) "
                "before running the pipeline")
    return "SUCCESS", {"documents": n, "uploaded": row["up"] or 0}, None, None


def _stage_b_process(conn, cid, state):
    n = conn.execute(
        """SELECT COUNT(*) AS n FROM knowledge_collection_documents
           WHERE collection_id=? AND status IN ('uploaded','failed')""",
        (cid,)).fetchone()["n"]
    bid = _pipeline_batch_id(cid)
    if n == 0:
        # nothing left to process: report the honest queue counters
        c = ka.queue_counters(conn, cid)
        if c["failed"] or c["needs_review"]:
            return "NEEDS_REVIEW", dict(c), None, None
        return "SUCCESS", dict(c), None, None
    now = ka._now()
    conn.execute(
        """INSERT INTO knowledge_import_batches
           (batch_id, collection_id, status, created_at, updated_at)
           VALUES (?, ?, 'planned', ?, ?)
           ON CONFLICT(batch_id) DO NOTHING""",
        (bid, cid, now, now))
    conn.execute(
        "UPDATE knowledge_import_batches SET status='processing', "
        "updated_at=? WHERE batch_id=?", (now, bid))
    conn.commit()
    job, _created = ka._submit_job(
        conn, "process_batch:" + bid, "process_batch", cid, bid,
        total=n, idempotency_key="batch:" + bid, force_retry=True)
    row = _wait_subjob(conn, job["job_id"], cid)
    if row is None or row["status"] == "interrupted":
        return "PAUSED", {"subjob": job["job_id"]}, job["job_id"], None
    if row["status"] == "failed":
        return "FAILED", {"subjob": job["job_id"]}, job["job_id"], row["error"]
    c = ka.queue_counters(conn, cid)
    if c["failed"] or c["needs_review"]:
        return "NEEDS_REVIEW", dict(c), job["job_id"], None
    return "SUCCESS", dict(c), job["job_id"], None


def _stage_c_schema(conn, cid, state):
    approved = ka._collection_approved_schema(conn, cid)
    if approved:
        return ("SUCCESS",
                {"schema_id": approved["schema_id"], "already": True},
                None, None)
    row = conn.execute(
        "SELECT COALESCE(MAX(version), 0) AS v "
        "FROM knowledge_schema_versions WHERE collection_id=?",
        (cid,)).fetchone()
    version = row["v"] + 1
    # schema_id is the GLOBAL primary key, but version is per-collection:
    # embed the collection id so two collections can both hold a version-1
    # schema without a PK collision (exposed by the two-collection scenario).
    schema_id = "sv-%s-%04d" % (cid, version)
    normalized, errors = ka._validate_schema_fields(
        ka._default_schema_fields())
    if errors:
        return ("FAILED", None, None,
                "default schema fields invalid: " + "; ".join(errors))
    now = ka._now()
    conn.execute(
        """INSERT INTO knowledge_schema_versions
           (schema_id, collection_id, version, status, description, fields,
            created_at, updated_at)
           VALUES (?, ?, ?, 'draft', ?, ?, ?, ?)""",
        (schema_id, cid, version,
         "PCM-20.9 pipeline default schema (auto-created)",
         json.dumps(normalized, ensure_ascii=False), now, now))
    conn.commit()
    report = ka._schema_validate_report(conn, cid, normalized)
    conn.execute(
        "UPDATE knowledge_schema_versions SET validation=?, updated_at=? "
        "WHERE schema_id=? AND collection_id=?",
        (json.dumps(report, ensure_ascii=False), ka._now(),
         schema_id, cid))
    conn.commit()
    if not report.get("blocks_scanned"):
        return ("BLOCKED", dict(report), None,
                "no processed blocks found to validate against — run "
                "Stage B with at least one successful document first")
    if not report.get("ok"):
        return ("NEEDS_REVIEW", dict(report), None,
                "schema validation failed: "
                + "; ".join(report.get("errors") or []))
    # identical to POST /schema/<schema_id>/approve
    conn.execute(
        "UPDATE knowledge_schema_versions SET status='approved', "
        "approved_at=?, updated_at=? WHERE schema_id=? AND collection_id=?",
        (now, now, schema_id, cid))
    conn.execute(
        "UPDATE knowledge_collections SET schema_version=?, updated_at=? "
        "WHERE collection_id=?", (schema_id, now, cid))
    conn.commit()
    ka._audit_log(conn, cid, "schema", "schema_approved", "ok",
                  {"schema_id": schema_id, "version": version,
                   "by": "pipeline"})
    return ("SUCCESS",
            {"schema_id": schema_id, "version": version,
             "blocks_scanned": report.get("blocks_scanned")},
            None, None)


def _stage_d_build(conn, cid, state):
    n = conn.execute(
        """SELECT COUNT(*) AS n FROM knowledge_collection_documents
           WHERE collection_id=? AND out_dir IS NOT NULL
             AND status IN ('parsed','needs_review','approved','indexed')""",
        (cid,)).fetchone()["n"]
    if n == 0:
        return ("FAILED", None, None,
                "no processed documents to build a corpus from — Stage B "
                "did not produce any successful documents")
    job, _created = ka._submit_job(
        conn, "corpus_build:" + cid, "corpus_build", cid, None,
        total=n, idempotency_key="corpus_build:" + cid, force_retry=True)
    row = _wait_subjob(conn, job["job_id"], cid)
    if row is None or row["status"] == "interrupted":
        return "PAUSED", {"subjob": job["job_id"]}, job["job_id"], None
    if row["status"] == "failed":
        return "FAILED", {"subjob": job["job_id"]}, job["job_id"], row["error"]
    b = _newest_build(conn, cid)
    if not b:
        return ("FAILED", {"subjob": job["job_id"]}, job["job_id"],
                "corpus build succeeded but no build row found")
    return ("SUCCESS",
            {"iv_id": b["iv_id"], "es_index_status": b["es_index_status"],
             "content_sha256": b["content_sha256"]},
            job["job_id"], None)


def _stage_e_accept(conn, cid, state):
    build = _newest_build(conn, cid)
    if not build:
        return ("FAILED", None, None,
                "no Stage D corpus build found — run the corpus build "
                "(Stage D) first")
    job, _created = ka._submit_job(
        conn, "search_acceptance:" + cid, "search_acceptance", cid, None,
        total=len(ka._SEARCH_CATEGORIES),
        idempotency_key="search_acceptance:" + cid, force_retry=True)
    row = _wait_subjob(conn, job["job_id"], cid)
    if row is None or row["status"] == "interrupted":
        return "PAUSED", {"subjob": job["job_id"]}, job["job_id"], None
    build = _newest_build(conn, cid)
    if row["status"] == "failed":
        if build and build["search_status"] == "blocked":
            reason = None
            try:
                reason = json.loads(build["search_detail"] or "{}").get("reason")
            except (TypeError, ValueError):
                reason = None
            return ("BLOCKED",
                    {"iv_id": build["iv_id"], "reason": reason},
                    job["job_id"], reason)
        return "FAILED", {"subjob": job["job_id"]}, job["job_id"], row["error"]
    if build and build["search_status"] == "pass":
        # identical to POST /index-builds/<iv_id>/approve
        now = ka._now()
        conn.execute(
            """UPDATE knowledge_collections SET current_index_build=?,
               validation_status='accepted', indexing_status='ready',
               updated_at=? WHERE collection_id=?""",
            (build["iv_id"], now, cid))
        conn.commit()
        ka._audit_log(conn, cid, "acceptance", "index_approved", "ok",
                      {"iv_id": build["iv_id"], "search_status": "pass",
                       "es_index_status": build["es_index_status"],
                       "by": "pipeline"})
        return ("SUCCESS",
                {"iv_id": build["iv_id"], "search_status": "pass"},
                job["job_id"], None)
    return ("FAILED",
            {"iv_id": build["iv_id"] if build else None,
             "search_status": build["search_status"] if build else None},
            job["job_id"], "search acceptance did not pass")


def _stage_release(conn, cid, state):
    job, _created = ka._submit_job(
        conn, "release:" + cid, "release", cid, None,
        total=4, idempotency_key="release:" + cid, force_retry=True)
    row = _wait_subjob(conn, job["job_id"], cid)
    if row is None or row["status"] == "interrupted":
        return "PAUSED", {"subjob": job["job_id"]}, job["job_id"], None
    if row["status"] == "failed":
        return "FAILED", {"subjob": job["job_id"]}, job["job_id"], row["error"]
    rel = _newest_release(conn, cid)
    return ("SUCCESS",
            {"release_id": rel.get("release_id") if rel else None,
             "rag_status": rel.get("rag_status") if rel else None,
             "zip_sha256": rel.get("zip_sha256") if rel else None},
            job["job_id"], None)


_STAGE_HANDLERS = {
    "A_IMPORT": _stage_a_import,
    "B_PROCESS": _stage_b_process,
    "C_SCHEMA": _stage_c_schema,
    "D_BUILD": _stage_d_build,
    "E_ACCEPT": _stage_e_accept,
    "RELEASE": _stage_release,
}


# ---------------------------------------------------------------------------
# the pipeline job kind (runs in a background thread, own connection)
# ---------------------------------------------------------------------------

def _job_kind_pipeline_run(conn, job_id):
    """The checkpointed stage machine.

    SUCCESS stages are skipped (checkpoint); BLOCKED / NEEDS_REVIEW are
    recorded and the run continues; FAILED stops the run (the job itself
    fails, so GET /api/knowledge/jobs reflects it); a pause self-interrupts
    the job (retryable via resume).
    """
    r = conn.execute(
        "SELECT job_key, collection_id FROM knowledge_jobs WHERE job_id=?",
        (job_id,)).fetchone()
    _, cid = r["job_key"].split(":", 1)
    run = _run_row(conn, cid)
    if not run:
        raise RuntimeError("pipeline run row missing for " + cid)
    run_id = run["run_id"]
    total = len(STAGES)
    states = _load_states(run)
    for i, (skey, label) in enumerate(STAGES):
        if _run_status(conn, cid) == "paused":
            _interrupt_pipeline_job(conn, job_id)
            return
        st = states[skey]
        if st["status"] == "SUCCESS":
            _job_progress = ka._job_progress
            _job_progress(conn, job_id, i, total, skey + " (checkpoint)")
            continue
        now = ka._now()
        st["status"] = "RUNNING"
        st["error"] = None
        if not st.get("started_at"):
            st["started_at"] = now
        st["updated_at"] = now
        _persist_states(conn, run_id, states)
        ka._job_progress(conn, job_id, i, total, label)
        status, detail, subjob_id, error = \
            _STAGE_HANDLERS[skey](conn, cid, st)
        st["status"] = status
        st["detail"] = detail
        st["error"] = error
        st["job_id"] = subjob_id
        st["updated_at"] = ka._now()
        _persist_states(conn, run_id, states)
        ka._audit_log(
            conn, cid, "pipeline", "stage_completed",
            "fail" if status == "FAILED"
            else ("blocked" if status == "BLOCKED" else "ok"),
            {"stage": skey, "status": status, "job_id": subjob_id,
             "error": error})
        if status == "PAUSED":
            _interrupt_pipeline_job(conn, job_id)
            return
        if status == "FAILED":
            msg = "stage " + skey + " failed: " + (error or "unknown")
            _finish_run(conn, run_id, "failed", msg)
            ka._audit_log(conn, cid, "pipeline", "pipeline_failed", "fail",
                          {"stage": skey, "error": error})
            raise RuntimeError(msg)
        # SUCCESS / BLOCKED / NEEDS_REVIEW -> checkpoint and continue
    _finish_run(conn, run_id, "done")
    ka._audit_log(conn, cid, "pipeline", "pipeline_done", "ok",
                  {"stages": list(STAGE_KEYS)})


# ---------------------------------------------------------------------------
# run control (called from request context and from run_nightly)
# ---------------------------------------------------------------------------

def _start_run(db, cid, trigger="manual", from_stage=None):
    """Start (or restart) the pipeline run for one collection.

    Returns (run, job, created, err). err is None on success, else
    (code, message): 'unknown_stage' (400) / 'conflicting_job' (409).
    """
    if from_stage is not None and from_stage not in STAGE_KEYS:
        return None, None, False, (
            "unknown_stage",
            "unknown stage (expected one of: " + ", ".join(STAGE_KEYS) + ")")
    ka._recover_interrupted(db)
    run = _run_row(db, cid)
    if run:
        if run["status"] == "paused":
            return run, None, False, (
                "conflicting_job",
                "the pipeline is paused — resume it, or wait for it")
        if run["status"] == "running":
            jr = None
            if run["job_id"]:
                jr = db.execute(
                    "SELECT status FROM knowledge_jobs WHERE job_id=?",
                    (run["job_id"],)).fetchone()
            if jr and jr["status"] in ("pending", "running"):
                return run, None, False, (
                    "conflicting_job",
                    "a pipeline run is already active for this collection")
            # stale: the worker died while the run row said 'running'
            _finish_run(db, run["run_id"], "failed",
                        "[stale run: worker lost — auto-recovered]")
    now = ka._now()
    run_id = _run_id(cid)
    if from_stage is not None:
        old = _load_states(run) if run else {}
        from_idx = STAGE_KEYS.index(from_stage)
        states = {}
        for idx, (skey, _label) in enumerate(STAGES):
            if idx < from_idx:
                states[skey] = dict(old.get(skey) or _new_state())
            else:
                states[skey] = _new_state()
    else:
        states = {skey: _new_state() for skey, _l in STAGES}
    states_json = json.dumps(states, ensure_ascii=False)
    db.execute(
        """INSERT INTO knowledge_pipeline_runs
           (run_id, collection_id, trigger_type, status, stage_states,
            started_stage, created_at, updated_at)
           VALUES (?, ?, ?, 'running', ?, ?, ?, ?)
           ON CONFLICT(run_id) DO UPDATE SET
             trigger_type=excluded.trigger_type,
             status='running',
             stage_states=excluded.stage_states,
             started_stage=excluded.started_stage,
             error=NULL,
             job_id=NULL,
             updated_at=excluded.updated_at,
             finished_at=NULL""",
        (run_id, cid, trigger, states_json,
         from_stage or "A_IMPORT", now, now))
    db.commit()
    job_key = "pipeline_run:" + cid
    # a previous job row may still be pending/running for a few ms after
    # the run finished (worker settles its own terminal state last) — wait
    # for it to settle so the re-submit actually (re)starts a worker
    deadline = time.time() + 15
    while time.time() < deadline:
        jr = db.execute(
            "SELECT status FROM knowledge_jobs WHERE job_key=?",
            (job_key,)).fetchone()
        if not jr or jr["status"] not in ("pending", "running"):
            break
        time.sleep(0.2)
    job, created = ka._submit_job(
        db, job_key, "pipeline_run", cid, None,
        total=len(STAGES), idempotency_key=job_key, force_retry=True)
    db.execute(
        "UPDATE knowledge_pipeline_runs SET job_id=? WHERE run_id=?",
        (job["job_id"], run_id))
    db.commit()
    ka._audit_log(db, cid, "pipeline", "pipeline_started", "ok",
                  {"trigger": trigger, "from_stage": from_stage,
                   "run_id": run_id, "job_id": job["job_id"]})
    run = _run_row(db, cid)
    return run, job, created, None


# ---------------------------------------------------------------------------
# nightly driver (deploy/pcm209_nightly.sh)
# ---------------------------------------------------------------------------

def run_nightly(db):
    """Start one pipeline run per ENABLED schedule.

    Returns a list of {collection_id, status, detail} where status is one
    of: started / skipped / error. One bad schedule never stops the rest.
    """
    ensure_pipeline_schema(db)
    ka.ensure_knowledge_schema(db)
    ka._recover_interrupted(db)
    results = []
    rows = db.execute(
        "SELECT collection_id FROM knowledge_pipeline_schedules "
        "WHERE enabled=1 ORDER BY collection_id").fetchall()
    for r in rows:
        cid = r["collection_id"]
        col = db.execute(
            "SELECT collection_id FROM knowledge_collections "
            "WHERE collection_id=?", (cid,)).fetchone()
        if not col:
            st, detail = "skipped", "collection no longer exists"
        else:
            try:
                run, _job, _created, err = _start_run(db, cid,
                                                      trigger="nightly")
            except Exception as e:  # noqa: BLE001 — keep going, record it
                st, detail = "error", f"{type(e).__name__}: {e}"
            else:
                if err is None:
                    st, detail = "started", run["run_id"]
                elif err[0] == "conflicting_job":
                    st, detail = "skipped", "conflicting_job"
                else:
                    st, detail = "error", err[0]
        db.execute(
            "UPDATE knowledge_pipeline_schedules SET last_run_at=?, "
            "last_status=? WHERE collection_id=?",
            (ka._now(), st, cid))
        db.commit()
        results.append({"collection_id": cid, "status": st,
                        "detail": detail})
    return results


# ---------------------------------------------------------------------------
# routes
# ---------------------------------------------------------------------------

def register_pipeline_routes(app, get_db):
    require_auth = make_require_auth(get_db)

    def _init_db(db):
        ka.ensure_knowledge_schema(db)
        ensure_pipeline_schema(db)

    def _cid_or_none(db, coll_id):
        row = ka._collection_row(db, coll_id)
        return row["collection_id"] if row else None

    @app.route("/api/knowledge/collections/<int:coll_id>/pipeline/run",
               methods=["POST"])
    @require_auth
    def pipeline_run(coll_id):
        """Start the full pipeline run (per-collection singleton).

        Body (optional): {"from_stage": "D_BUILD"} — re-enter from a stage;
        stages at/after it are reset, earlier SUCCESS checkpoints are kept.
        """
        db = get_db()
        _init_db(db)
        cid = _cid_or_none(db, coll_id)
        if not cid:
            return jsonify({"ok": False, "message": "کالکشن پیدا نشد"}), 404
        data = request.get_json(silent=True) or {}
        run, job, created, err = _start_run(db, cid, trigger="manual",
                                            from_stage=data.get("from_stage"))
        if err:
            code, message = err
            body = {"ok": False, "code": code, "message": message}
            if code == "unknown_stage":
                body["stages"] = list(STAGE_KEYS)
                return jsonify(body), 400
            return jsonify(body), 409
        return jsonify({"ok": True, "queued": created,
                        "run_id": run["run_id"], "job": job}), \
            (202 if created else 200)

    @app.route("/api/knowledge/collections/<int:coll_id>/pipeline/pause",
               methods=["POST"])
    @require_auth
    def pipeline_pause(coll_id):
        """Pause the active run; the worker self-interrupts on its next poll."""
        db = get_db()
        _init_db(db)
        cid = _cid_or_none(db, coll_id)
        if not cid:
            return jsonify({"ok": False, "message": "کالکشن پیدا نشد"}), 404
        run = _run_row(db, cid)
        if not run:
            return jsonify({"ok": False, "code": "no_run",
                            "message": "no pipeline run for this collection"}
                           ), 409
        if run["status"] != "running":
            return jsonify({"ok": False, "code": "not_running",
                            "message": "the pipeline is not running "
                                       "(status: " + run["status"] + ")"}
                           ), 409
        r = db.execute(
            "UPDATE knowledge_pipeline_runs SET status='paused', "
            "updated_at=? WHERE collection_id=? AND status='running'",
            (ka._now(), cid))
        db.commit()
        if r.rowcount == 0:
            return jsonify({"ok": False, "code": "not_running",
                            "message": "the pipeline is not running"}), 409
        ka._audit_log(db, cid, "pipeline", "pipeline_paused", "ok",
                      {"run_id": run["run_id"]})
        return jsonify({"ok": True, "run_id": run["run_id"],
                        "status": "paused"})

    @app.route("/api/knowledge/collections/<int:coll_id>/pipeline/resume",
               methods=["POST"])
    @require_auth
    def pipeline_resume(coll_id):
        """Resume a paused run: re-submit the same job key (force_retry);
        SUCCESS checkpoints are skipped, the in-flight stage re-enters."""
        db = get_db()
        _init_db(db)
        cid = _cid_or_none(db, coll_id)
        if not cid:
            return jsonify({"ok": False, "message": "کالکشن پیدا نشد"}), 404
        run = _run_row(db, cid)
        if not run:
            return jsonify({"ok": False, "code": "no_run",
                            "message": "no pipeline run for this collection"}
                           ), 409
        if run["status"] != "paused":
            return jsonify({"ok": False, "code": "not_paused",
                            "message": "the pipeline is not paused "
                                       "(status: " + run["status"] + ")"}
                           ), 409
        r = db.execute(
            "UPDATE knowledge_pipeline_runs SET status='running', error=NULL, "
            "updated_at=? WHERE collection_id=? AND status='paused'",
            (ka._now(), cid))
        db.commit()
        if r.rowcount == 0:
            return jsonify({"ok": False, "code": "not_paused",
                            "message": "the pipeline is not paused"}), 409
        job, _created = ka._submit_job(
            db, "pipeline_run:" + cid, "pipeline_run", cid, None,
            total=len(STAGES), idempotency_key="pipeline_run:" + cid,
            force_retry=True)
        db.execute(
            "UPDATE knowledge_pipeline_runs SET job_id=? WHERE run_id=?",
            (job["job_id"], run["run_id"]))
        db.commit()
        ka._audit_log(db, cid, "pipeline", "pipeline_resumed", "ok",
                      {"run_id": run["run_id"], "job_id": job["job_id"]})
        return jsonify({"ok": True, "queued": True,
                        "run_id": run["run_id"], "job": job}), 202

    @app.route("/api/knowledge/collections/<int:coll_id>/pipeline/status",
               methods=["GET"])
    @require_auth
    def pipeline_run_status(coll_id):
        """Live stage cards for the UI: NOT_STARTED / READY / RUNNING /
        PAUSED / STALE / SUCCESS / FAILED / NEEDS_REVIEW / BLOCKED."""
        db = get_db()
        _init_db(db)
        cid = _cid_or_none(db, coll_id)
        if not cid:
            return jsonify({"ok": False, "message": "کالکشن پیدا نشد"}), 404
        ka._recover_interrupted(db)
        run = _run_row(db, cid)
        run_status = run["status"] if run else None
        if run:
            states = _load_states(run)
        else:
            states = {k: _new_state() for k, _l in STAGES}
        job_dead = bool(run and run_status in ("running", "paused")
                        and _job_dead_or_stale(db, run["job_id"]))
        cards = []
        prev_success = True
        for skey, label in STAGES:
            st = states.get(skey) or _new_state()
            stored = st.get("status") or "NOT_STARTED"
            if stored in ("SUCCESS", "FAILED", "BLOCKED", "NEEDS_REVIEW",
                          "PAUSED"):
                card_status = stored
            elif stored == "RUNNING":
                if run_status == "paused":
                    card_status = "PAUSED"
                elif job_dead:
                    card_status = "STALE"
                else:
                    card_status = "RUNNING"
            else:  # NOT_STARTED
                if prev_success and run_status in ("running", "paused"):
                    card_status = "READY"
                else:
                    card_status = "NOT_STARTED"
            cards.append({
                "stage": skey,
                "label": label,
                "status": card_status,
                "detail": st.get("detail"),
                "error": st.get("error"),
                "job_id": st.get("job_id"),
                "started_at": st.get("started_at"),
                "updated_at": st.get("updated_at"),
            })
            prev_success = (card_status == "SUCCESS")
        return jsonify({
            "ok": True,
            "collection_id": cid,
            "run": None if not run else {
                "run_id": run["run_id"],
                "status": run["status"],
                "trigger_type": run["trigger_type"],
                "error": run["error"],
                "started_at": run["created_at"],
                "finished_at": run["finished_at"],
            },
            "stages": cards,
            "queue": ka.queue_counters(db, cid),
            "latest_build": _newest_build(db, cid),
            "latest_release": _newest_release(db, cid),
        })

    @app.route("/api/knowledge/pipeline/schedules", methods=["GET"])
    @require_auth
    def pipeline_schedules_list():
        """List the nightly schedules (one per collection)."""
        db = get_db()
        _init_db(db)
        rows = [dict(r) for r in db.execute(
            "SELECT * FROM knowledge_pipeline_schedules "
            "ORDER BY collection_id").fetchall()]
        return jsonify({"ok": True, "schedules": rows})

    @app.route("/api/knowledge/pipeline/schedules", methods=["POST"])
    @require_auth
    def pipeline_schedule_upsert():
        """Create/update a nightly schedule.

        Body: {collection_id: int PK, enabled: bool, cron_time?: "HH:MM"}.
        """
        db = get_db()
        _init_db(db)
        data = request.get_json(silent=True) or {}
        cid_in = data.get("collection_id")
        if isinstance(cid_in, bool) or not isinstance(cid_in, int) \
                or cid_in <= 0:
            return jsonify({"ok": False, "code": "bad_collection_id",
                            "field": "collection_id",
                            "message": "collection_id must be a positive "
                                       "integer"}), 400
        cron_time = str(data.get("cron_time") or "03:00").strip()
        if not CRON_RE.fullmatch(cron_time):
            return jsonify({"ok": False, "code": "bad_cron_time",
                            "field": "cron_time",
                            "message": "cron_time must be HH:MM (24h)"}), 400
        row = ka._collection_row(db, cid_in)
        if not row:
            return jsonify({"ok": False, "message": "کالکشن پیدا نشد"}), 404
        cid = row["collection_id"]
        enabled = 1 if data.get("enabled") else 0
        now = ka._now()
        db.execute(
            """INSERT INTO knowledge_pipeline_schedules
               (collection_id, enabled, cron_time, updated_at)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(collection_id) DO UPDATE SET
                 enabled=excluded.enabled,
                 cron_time=excluded.cron_time,
                 updated_at=excluded.updated_at""",
            (cid, enabled, cron_time, now))
        db.commit()
        sched = db.execute(
            "SELECT * FROM knowledge_pipeline_schedules "
            "WHERE collection_id=?", (cid,)).fetchone()
        return jsonify({"ok": True, "schedule": dict(sched)})


ka._JOB_KINDS["pipeline_run"] = _job_kind_pipeline_run

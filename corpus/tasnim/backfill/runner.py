# -*- coding: utf-8 -*-
"""tasnim.backfill.runner — اجرای pipeline Backfill (PCM-20.6.3).

جریان هر item_index (از plan، ترتیب صعودی):
    1. checkpoint: اگر terminal (done/permanent) است → skip (idempotent resume).
    2. fetch با retry/backoff:
         200            → ادامه
         404            → permanent (بدون retry — صفحه در منبع نیست)
         5xx / network  → retry (max_attempts، backoff 30s×3^k) → permanent
    3. parse (parse_chunk_detail + build_backfill_record) — خطای parse →
       permanent (بدون retry؛ محتوا ثابت است).
    4. نوشتن رکورد به backfill-records.jsonl (append-only).
    5. checkpoint: written → done + save (اتمیکی).

قواعد:
    * transport تزریق‌شونده است (FakeTransport در تست/dry-run).
    * budget: هر اجرا حداکثر `budget` آیتم **فعال** (غیر-terminal) می‌کشد؛
      بقیه در اجرا بعد (resume) — خروجی resume-safe است.
    * `sleep_fn` تزریق‌شونده است → تست‌ها بدون خواب واقعی اجرا می‌شوند.
    * هیچ تغییر روی دایرکتوری base (v0003) — فقط خواندن.
"""
from __future__ import annotations

import json
import os
import time

from .. import common as C
from . import checkpoint as CK
from . import fetch_plan as FP
from . import parse as P
from . import transport as TR

RUN_REPORT_CONTRACT = "backfill-run-report-1"


def plan_sha_of(plan: dict) -> str:
    """SHA قطعیِ plan (مبنای قفل checkpoint)."""
    core = {"items": plan["items"], "endpoint": plan.get("endpoint")}
    return C.sha256_text(C.canonical_json(core).decode("utf-8"))


def backoff_seconds(attempt: int, base: float, factor: float = 3.0) -> float:
    """backoff قبل از تلاشِ attempt (1-based): base * factor^(attempt-1)."""
    return base * (factor ** (attempt - 1))


def fetch_with_retry(transport, url: str, user_agent: str, timeout: float,
                     max_attempts: int, retry_base: float,
                     sleep_fn=time.sleep) -> dict:
    """fetch با retry/backoff. برگشت:
       {"ok": True, "status": 200, "body_text": ..., "attempts": n}
       {"ok": False, "status": int|None, "reason": str, "attempts": n}
    """
    last_reason = "unknown"
    last_status = None
    for attempt in range(1, max(max_attempts, 1) + 1):
        try:
            resp = transport.get(url, user_agent=user_agent, timeout=timeout)
        except TR.TransportError as e:
            last_status, last_reason = None, "network: %s" % e
        else:
            last_status = resp["status"]
            if resp["status"] == 200:
                return {"ok": True, "status": 200,
                        "body_text": resp.get("body_text", ""),
                        "attempts": attempt}
            if resp["status"] == 404:
                return {"ok": False, "status": 404,
                        "reason": "not_found (404)", "attempts": attempt}
            last_reason = "http_%d" % resp["status"]
        if attempt < max_attempts:
            sleep_fn(backoff_seconds(attempt, retry_base))
    return {"ok": False, "status": last_status,
            "reason": last_reason, "attempts": attempt}


# --------------------------------------------------------------------------- base index
def base_index_entry(base_index: dict, item_index: int) -> dict:
    """ورودی base_index برای parse.build_backfill_record."""
    e = base_index["by_index"].get(item_index)
    if e is None:
        return {"present": False, "dup_in_base": False,
                "base_text_sha": None, "base_page_ids": [],
                "base_content_hash": None}
    return {"present": True,
            "dup_in_base": bool(e["dup"]),
            "base_text_sha": (e["texts_sha"][0] if e["texts_sha"] else None),
            "base_page_ids": list(e["page_ids"]),
            "base_content_hash": e["content_hash"]}


# --------------------------------------------------------------------------- pipeline
def run_pipeline(plan: dict, base_index: dict, vol_map: dict,
                 present_sorted: list, transport,
                 out_dir: str, checkpoint_path: str = None,
                 budget: int = None, dry_run: bool = False,
                 sleep_fn=time.sleep,
                 fetched_at_fn=lambda: C.now_utc()) -> dict:
    """اجرای pipeline روی یک «جعبه‌ی» plan (budget آیتم فعال).

    خروجی‌ها در out_dir:
        backfill-records.jsonl   (append-only — رکوردهای fetched/parsed)
        checkpoint.json          (resume-safe)
        run-report.json          (آخرین اجرا)
    """
    os.makedirs(out_dir, exist_ok=True)
    psha = plan_sha_of(plan)
    ck_path = checkpoint_path or os.path.join(out_dir, "checkpoint.json")
    ck = CK.CheckpointStore(ck_path, psha).load()

    rate = plan["rate"]
    items = plan["items"]
    pending = ck.pending_items(items)
    if budget is None:
        budget = rate.get("budget_per_run", len(items))
    todo = pending[:budget]

    records_path = os.path.join(out_dir, "backfill-records.jsonl")
    counts = {"skipped_done": 0, "fetched": 0, "parse_errors": 0,
              "permanent": 0, "budget_used": 0}
    changes = {"new": 0, "unchanged": 0, "changed": 0}

    out_f = None
    try:
        if not dry_run:
            out_f = open(records_path, "ab")
        for it in todo:
            idx = it["item_index"]
            if ck.is_terminal(idx):
                counts["skipped_done"] += 1
                continue
            counts["budget_used"] += 1
            url = it["url"]
            if dry_run:
                # فقط شمارش؛ درخواستی نمی‌رود
                continue
            res = fetch_with_retry(
                transport, url, rate.get("user_agent"),
                rate.get("timeout_seconds", FP.DEFAULT_TIMEOUT_SECONDS),
                rate.get("retry", {}).get("max_attempts",
                                          FP.DEFAULT_MAX_ATTEMPTS),
                rate.get("retry", {}).get("backoff_base_seconds",
                                          FP.DEFAULT_RETRY_BASE_SECONDS),
                sleep_fn=sleep_fn)
            if not res["ok"]:
                ck.mark(idx, CK.STAGE_PERMANENT, reason=res["reason"],
                        http_status=res.get("status"),
                        attempts=res.get("attempts", 0))
                counts["permanent"] += 1
                ck.save()
                continue
            ck.mark(idx, CK.STAGE_FETCHED,
                    http_status=200, attempts=res["attempts"])
            try:
                parsed = P.parse_chunk_detail(res["body_text"], url)
                rec = P.build_backfill_record(
                    idx, url, 200, parsed, fetched_at_fn(),
                    res["attempts"],
                    base_index_entry(base_index, idx),
                    vol_map, present_sorted)
            except P.ParseError as e:
                ck.mark(idx, CK.STAGE_PERMANENT,
                        reason="parse: %s" % e,
                        http_status=200, attempts=res["attempts"])
                counts["parse_errors"] += 1
                ck.save()
                continue
            ck.mark(idx, CK.STAGE_PARSED, text_sha256=rec["text_sha256"])
            out_f.write(C.canonical_json_line(rec))
            changes[rec["change"]] = changes.get(rec["change"], 0) + 1
            ck.mark(idx, CK.STAGE_WRITTEN)
            ck.mark(idx, CK.STAGE_DONE)
            counts["fetched"] += 1
            ck.save()
    finally:
        if out_f is not None:
            out_f.close()

    report = {
        "contract": RUN_REPORT_CONTRACT,
        "plan_sha": psha,
        "dry_run": dry_run,
        "budget": budget,
        "counts": counts,
        "changes": changes,
        "checkpoint_counts": ck.counts(),
        "permanent_failures": ck.permanent_failures(),
        "pending_remaining": len(ck.pending_items(items)),
        "run_at": fetched_at_fn(),
    }
    report_path = os.path.join(out_dir, "run-report.json")
    C.write_json(report_path, report)
    return report


# --------------------------------------------------------------------------- verify
REQUIRED_RECORD_FIELDS = (
    "item_index", "url", "text", "text_sha256", "text_len",
    "quality_flags", "base_state", "change",
    "parser_version", "policy_version",
)


def verify_output(out_dir: str, plan: dict,
                  base_pages_jsonl: str = None) -> dict:
    """verify پس از اجرا (برای `cli verify`).

    چک‌ها:
      * run-report.json وجود دارد و plan_sha با plan جاری یکی است.
      * backfill-records.jsonl: همه‌ی رکوردها فیلدهای لازم دارند،
        text_sha256 درست محاسبه می‌شود، change ∈ {new,unchanged,changed}.
      * checkpoint با plan_sha یکی است و همه‌ی آیتم‌های plan terminal
        یا در بودجه‌ی بعدی‌اند.
      * (اختیاری) base pages.jsonl: SHA فایل دست‌نخورده (immutable).
    """
    errors = []
    warnings = []

    report_p = os.path.join(out_dir, "run-report.json")
    if not os.path.exists(report_p):
        errors.append("run-report.json missing")
        report = None
    else:
        report = C.read_json(report_p)
        if report.get("plan_sha") != plan_sha_of(plan):
            errors.append("plan_sha mismatch in run-report")

    records = []
    rec_p = os.path.join(out_dir, "backfill-records.jsonl")
    if os.path.exists(rec_p):
        for r in C.read_jsonl(rec_p):
            for f in REQUIRED_RECORD_FIELDS:
                if f not in r:
                    errors.append("record missing field %s (idx=%s)"
                                  % (f, r.get("item_index")))
            if r.get("text_sha256") != C.sha256_text(r.get("text", "")):
                errors.append("text_sha256 mismatch (idx=%s)"
                              % r.get("item_index"))
            if r.get("change") not in ("new", "unchanged", "changed"):
                errors.append("bad change flag (idx=%s)" % r.get("item_index"))
            records.append(r)
    else:
        warnings.append("backfill-records.jsonl missing (dry-run?)")

    ck_p = os.path.join(out_dir, "checkpoint.json")
    ck_counts = None
    if os.path.exists(ck_p):
        ck_raw = C.read_json(ck_p)
        if ck_raw.get("plan_sha") != plan_sha_of(plan):
            errors.append("plan_sha mismatch in checkpoint")
        ck_counts = ck_raw.get("counts")
        # همه‌ی آیتم‌های plan یا terminal یا در pending (budget بعدی)
        pending = ck_raw.get("items", {})
        non_terminal = sum(1 for st in pending.values()
                           if st.get("stage") not in
                           (CK.STAGE_DONE, CK.STAGE_PERMANENT))
        if non_terminal:
            warnings.append("%d آیتم non-terminal (ادامه در run بعدی)"
                            % non_terminal)
    else:
        warnings.append("checkpoint.json missing (dry-run?)")

    base_sha = None
    if base_pages_jsonl and os.path.exists(base_pages_jsonl):
        base_sha = C.sha256_file(base_pages_jsonl)

    return {
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "records": len(records),
        "checkpoint_counts": ck_counts,
        "base_pages_sha256": base_sha,
        "report": report,
    }

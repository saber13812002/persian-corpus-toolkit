# -*- coding: utf-8 -*-
"""tasnim.backfill.checkpoint — store checkpoint/resume (PCM-20.6.3).

store فایل‌محور JSON (بدون وابستگی به SQLite)، با نوشتن اتمیک
(tmp + os.replace) و ردیابی idempotent مرحله‌ای برای هر item_index.

مراحل (stages):
    pending (ضمنی) → fetched → parsed → written → done
    + retry      (شکست موقتی — با attempts و backoff)
    + permanent  (شکست غیرقابل‌بازگشت: 404 / تمام تلاش‌ها / خطای parse)

قواعد:
    * resume: اگر `plan_sha` در store با plan جاری متفاوت باشد →
      CheckpointError (resume روی plan اشتباه ممنوع).
    * `done` نهایی است: آیتم done دیگر به مرحله‌ی دیگری برنمی‌گردد.
    * store همیشه JSON معتبر است (نوشتن اتمیک؛ هرگز فایل نصفه نمی‌ماند).

محدودیت شناخته‌شده (برای اجرای واقعی 45k آیتم): هر `save()` کل فایل را
بازنویسی می‌کند (O(n²) در کل اجرا). برای اجرای واقعی روی s52، runner باید
بین اجراهای budget (هر ~500 آیتم) save کند — نه حتماً بعد از هر آیتم.
"""
from __future__ import annotations

import json
import os
import tempfile

from .. import common as C

CONTRACT = "checkpoint-1"

STAGE_FETCHED = "fetched"
STAGE_PARSED = "parsed"
STAGE_WRITTEN = "written"
STAGE_DONE = "done"
STAGE_RETRY = "retry"
STAGE_PERMANENT = "permanent"

STAGES_ALL = (STAGE_FETCHED, STAGE_PARSED, STAGE_WRITTEN,
              STAGE_DONE, STAGE_RETRY, STAGE_PERMANENT)
DONE_STAGES = (STAGE_DONE,)
TERMINAL_STAGES = (STAGE_DONE, STAGE_PERMANENT)


class CheckpointError(ValueError):
    """خطای store checkpoint (plan_sha نامعتبر/ناسازگار، stage نامعتبر)."""


class CheckpointStore:
    """store checkpoint یک plan Fetch (کلید: item_index)."""

    def __init__(self, path: str, plan_sha: str):
        if not plan_sha:
            raise CheckpointError("plan_sha is required")
        self.path = path
        self.plan_sha = plan_sha
        self.items = {}

    # ---------------------------------------------------------------- load/save
    def load(self) -> "CheckpointStore":
        """بارگذاری (اگر store وجود نداشته باشد → store خالی)."""
        if not os.path.exists(self.path):
            return self
        with open(self.path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        if raw.get("contract") not in (None, CONTRACT):
            raise CheckpointError("not a checkpoint file: %s" % self.path)
        if raw.get("plan_sha") != self.plan_sha:
            raise CheckpointError(
                "plan_sha mismatch — store=%s plan=%s (resume ممنوع)"
                % (raw.get("plan_sha"), self.plan_sha))
        self.items = raw.get("items") or {}
        return self

    def save(self) -> str:
        """نوشتن اتمیک (tmp در همان دایرکتوری + os.replace)."""
        d = os.path.dirname(os.path.abspath(self.path))
        os.makedirs(d, exist_ok=True)
        doc = {
            "contract": CONTRACT,
            "plan_sha": self.plan_sha,
            "updated_at": C.now_utc(),
            "counts": self.counts(),
            "items": self.items,
        }
        fd, tmp = tempfile.mkstemp(prefix=".ckpt-", dir=d)
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(C.canonical_json(doc))
            os.replace(tmp, self.path)
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)
        return self.path

    # ---------------------------------------------------------------- state
    def state(self, item_index: int) -> dict:
        """وضعیت فعلی یک آیتم (default: pending)."""
        st = self.items.get(str(item_index))
        if st is None:
            return {"stage": "pending", "attempts": 0}
        return st

    def is_done(self, item_index: int) -> bool:
        st = self.items.get(str(item_index))
        return bool(st) and st.get("stage") in DONE_STAGES

    def is_terminal(self, item_index: int) -> bool:
        """done یا permanent — هر دو برای resume «تکمیل‌شده» به‌حساب می‌آیند."""
        st = self.items.get(str(item_index))
        return bool(st) and st.get("stage") in TERMINAL_STAGES

    def mark(self, item_index: int, stage: str, **meta) -> dict:
        """ثبت یک stage (idempotent: done نهایی است و تغییر نمی‌کند)."""
        if stage not in STAGES_ALL:
            raise CheckpointError("bad stage: %r" % (stage,))
        key = str(item_index)
        cur = self.items.get(key)
        if cur is not None and cur.get("stage") in DONE_STAGES:
            return cur  # done نهایی (idempotent)
        cur = cur or {"stage": "pending", "attempts": 0}
        cur["stage"] = stage
        cur["updated_at"] = C.now_utc()
        for k, v in meta.items():
            cur[k] = v
        self.items[key] = cur
        return cur

    def pending_items(self, plan_items: list) -> list:
        """آیتم‌های plan که هنوز terminal نشده‌اند (برای resume)."""
        return [it for it in plan_items
                if not self.is_terminal(it["item_index"])]

    def permanent_failures(self) -> list:
        """فهرست شکست‌های دائمی (برای گزارش و run بعدی)."""
        out = []
        for key, st in sorted(self.items.items(), key=lambda kv: int(kv[0])):
            if st.get("stage") == STAGE_PERMANENT:
                out.append({
                    "item_index": int(key),
                    "reason": st.get("reason"),
                    "http_status": st.get("http_status"),
                    "attempts": st.get("attempts", 0),
                })
        return out

    def counts(self) -> dict:
        """شمارنده‌ی مراحل (آیتم‌های ثبت‌نشده pending ضمنی‌اند و اینجا
        فقط آیتم‌های ثبت‌شده را می‌شمارد)."""
        c = {s: 0 for s in STAGES_ALL}
        c["pending"] = 0
        for st in self.items.values():
            s = st.get("stage", "pending")
            c[s] = c.get(s, 0) + 1
        return c

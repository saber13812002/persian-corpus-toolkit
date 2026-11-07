# -*- coding: utf-8 -*-
"""tasnim.backfill.manifest — manifest نسخه‌ی v0004 + diff نسبت به base (PCM-20.6.3).

وظیفه:
    * ساخت manifest `backfill` برای خروجی Backfill (قرارداد `backfill-manifest-1`)
      بر بستر همان قرارداد manifest خط تولید (`m-20.3`): زنجیره‌ی prev،
      SHA-256 فایل‌ها، ثبت در registry (append-only).
    * diff نسبت به base (v0003): هر رکورد Backfill یک flag وضعیت دارد:
        new       — item_index در base نبود (رکورد کاملاً جدید).
        duplicate — item_index در base هست و base خودش dup_index دارد.
        unchanged — متن دقیقاً همان است (SHA برابر).
        changed   — متن متفاوت است (سیاست **old-wins**: رکورد base برتر؛
                    رکورد backfill فقط ثبت می‌شود — R15).
        absent    — فقط در verify: آیتمی از plan که fetch نکرده (budget
                    نامتکمل) یا 404 شده است.
    * rollback metadata: rollback = نگه‌داشتن base (v0003) + یک entry
      registry با kind `backfill` و `status: rollback-ready`؛ هیچ فایل base
      دست‌نخورده می‌ماند (immutable).

قواعد:
    * هیچ چیزی روی base نمی‌نویسد — فقط خواندن base + نوشتن در دایرکتوری
      جدا (build جدید).
    * registry append-only: `V.update_registry` فقط entry اضافه/به‌روز می‌کند
      و هیچ entry قبلی را حذف نمی‌کند.
"""
from __future__ import annotations

import os

from .. import common as C
from .. import manifest as M
from .. import versioning as V

CONTRACT = "backfill-manifest-1"

# وضعیت‌های diff (فقط همین 5 مقدار — whitelist)
STATUS_NEW = "new"
STATUS_DUPLICATE = "duplicate"
STATUS_UNCHANGED = "unchanged"
STATUS_CHANGED = "changed"
STATUS_ABSENT = "absent"
STATUS_ALL = (STATUS_NEW, STATUS_DUPLICATE, STATUS_UNCHANGED,
              STATUS_CHANGED, STATUS_ABSENT)


# --------------------------------------------------------------------------- diff
def base_index_from_pages(pages_jsonl: str) -> dict:
    """فهرست base از pages.jsonl برای cross-reference diff.

    برگشت: {
      "by_index": {item_index: {"dup": bool, "texts_sha": [sha...],
                                 "page_ids": [...], "content_hash": str|None}},
      "present_sorted": [item_index...],
    }
    """
    by_index = {}
    for p in C.read_jsonl(pages_jsonl):
        idx = p.get("item_index")
        if idx is None:
            continue
        vol = p.get("volume") or {}
        entry = by_index.setdefault(idx, {
            "count": 0,
            "texts_sha": set(),
            "page_ids": [],
            "content_hash": None,
        })
        entry["count"] += 1
        text = p.get("text")
        if isinstance(text, str):
            entry["texts_sha"].add(C.sha256_text(text))
        entry["page_ids"].append(p.get("page_id"))
        if entry["content_hash"] is None:
            entry["content_hash"] = p.get("content_hash")
    out_by_index = {}
    for idx, e in by_index.items():
        out_by_index[idx] = {
            "dup": e["count"] > 1,
            "texts_sha": sorted(e["texts_sha"]),
            "page_ids": e["page_ids"],
            "content_hash": e["content_hash"],
        }
    return {"by_index": out_by_index,
            "present_sorted": sorted(by_index.keys())}


def diff_status(record: dict) -> str:
    """flag وضعیت diff برای یک رکورد Backfill (بر اساس base_state رکورد).

    * base_state.present_in_base=False → "new"
    * base_state.dup_in_base=True       → "duplicate"
    * record.change == "unchanged"      → "unchanged"
    * record.change == "changed"        → "changed"
    """
    bs = record.get("base_state") or {}
    if not bs.get("present_in_base"):
        return STATUS_NEW
    if bs.get("dup_in_base"):
        return STATUS_DUPLICATE
    if record.get("change") == "unchanged":
        return STATUS_UNCHANGED
    return STATUS_CHANGED


def build_diff(base: dict, backfill_records: list,
               plan_items: list = None) -> dict:
    """diff کامل v0004 نسبت به base.

    base:             خروجی base_index_from_pages (یا هم‌شکل)
    backfill_records: رکوردهای ساخته‌شده توسط parse.build_backfill_record
    plan_items:       (اختیاری) فهرست آیتم‌های plan — اگر دادی، آیتم‌هایی
                      که رکورد backfill ندارند → "absent" (budget/404).
    """
    counts = {s: 0 for s in STATUS_ALL}
    detail = []
    seen_idx = set()
    for r in sorted(backfill_records, key=lambda x: x["item_index"]):
        st = diff_status(r)
        counts[st] += 1
        seen_idx.add(r["item_index"])
        detail.append({
            "item_index": r["item_index"],
            "status": st,
            "text_sha256": r.get("text_sha256"),
            "change": r.get("change"),
            "base_page_ids": (r.get("base_state") or {}).get("base_page_ids"),
        })
    absent = []
    if plan_items is not None:
        for it in plan_items:
            idx = it["item_index"]
            if idx in seen_idx:
                continue
            counts[STATUS_ABSENT] += 1
            absent.append({"item_index": idx, "url": it.get("url")})
    return {
        "contract": CONTRACT,
        "counts": counts,
        "total": len(backfill_records) + counts[STATUS_ABSENT],
        "detail": detail,
        "absent": absent,
    }


# --------------------------------------------------------------------------- manifest
def backfill_manifest_data(base_manifest: dict, base_dir: str, data_root: str,
                           out_dir: str, backfill_files: dict,
                           diff: dict, plan: dict,
                           permanent_failures: list,
                           rollback_ready: bool = True) -> dict:
    """بدنه‌ی data برای manifest backfill (بدون created_at).

    data_root: ریشه‌ی دیتا (برای محاسبه‌ی path_rel زنجیره).
    """
    base_version = base_manifest.get("version")
    base_rel = os.path.relpath(os.path.abspath(base_dir),
                               os.path.abspath(data_root)).replace(os.sep, "/")
    prev_entry = M.chain_entry(base_manifest, base_rel)
    return {
        "contract": CONTRACT,
        "base": {
            "version": base_version,
            "content_sha256": (base_manifest.get("data") or {}).get("content_sha256"),
            "manifest_sha256": prev_entry.get("sha256"),
            "path_rel": prev_entry.get("path_rel"),
            "immutable": True,
        },
        "_prev": prev_entry,  # build_manifest آن را به prev سطح‌بالا تبدیل می‌کند
        "plan": {
            "contract": plan.get("contract"),
            "endpoint": plan.get("endpoint"),
            "planned_requests": (plan.get("totals") or {}).get("planned_requests"),
            "rate": plan.get("rate"),
        },
        "files": backfill_files,
        "diff": diff,
        "permanent_failures": list(permanent_failures),
        "policy": {
            "policy_version": "bf-2",
            "old_wins": True,
            "volume_guessing": False,
        },
        "rollback": {
            "ready": rollback_ready,
            "strategy": "keep-base",
            "base_version": base_version,
            "note": ("rollback = نگه‌داشتن base (immutable) + entry registry "
                     "این نسخه با status=rollback-ready؛ هیچ تغییر روی base."),
        },
    }


def write_backfill_manifest(out_dir: str, version: str, data: dict) -> dict:
    """manifest backfill در دایرکتوری خروجی (kind: backfill)."""
    manifest = M.build_manifest("backfill", version, data)
    M.write_manifest(out_dir, manifest)
    return manifest


def register(data_root: str, kind: str, version: str, entry: dict) -> dict:
    """ثبت append-only در registry زنجیره (manifests/registry.json)."""
    paths = V.root_paths(data_root)
    return V.update_registry(paths["manifests"], kind, version, entry)


def rollback_entry(version: str, reason: str) -> dict:
    """entry registry برای rollback (بدون هیچ تغییر روی داده‌ی base).

    rollback عملیاتی = عدم‌تأیید نسخه‌ی backfill: registry entry جدیدی
    با `status: "rolled_back"` اضافه می‌شود و base (v0003) که immutable
    است، همچنان آخرین نسخه‌ی معتبر corpus باقی می‌ماند.
    """
    return {
        "status": "rolled_back",
        "reason": reason,
        "rolled_back_version": version,
        "active_base_unchanged": True,
    }

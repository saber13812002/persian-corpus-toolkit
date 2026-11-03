# -*- coding: utf-8 -*-
"""tasnim.diff — به‌روزرسانی افزایشی + Change Manifest (PCM-20.3 §5).

تعیین وضعیت هر رکوردِ منبعِ جدید (v_new) نسبت به پیکره‌ی قبلی (v_old):
  * added                : page_id جدید (item_index/position جدید در منبع).
  * changed              : همان page_id، ولی content_hash (یا متن) عوض شده.
  * duplicate            : item_index تکراری که در v_old هم تکراری بود (بدون تغییر).
  * removed_from_source  : page_id در v_old هست ولی در منبعِ جدید نیست.
                           — فقط FLAG می‌شود؛ پیکره‌ی جدید هنوز همه‌ی رکوردهای
                           قبلی را نگه می‌دارد؟ خیر: پیکره‌ی جدید از منبعِ جدید
                           ساخته می‌شود؛ رکوردهای removed در Change Manifest
                           ثبت می‌شوند و در پیکره‌ی جدید (که از منبعِ جدید است)
                           نیستند — اما هیچ‌گاه به‌صورت خودکار از آرشیو/
                           نسخه‌های قبلی حذف نمی‌شوند (نسخه‌های قبلی immutable).
  * healed               : رکوردی که در v_old flag داشت (empty/short/...) و
                           در v_new بدون آن flag است.

خروجی: reports/diff_<from>_<to>/change-manifest.json + خلاصه console.
"""
from __future__ import annotations

import os

from . import common as C
from . import versioning as V


def _load_corpus_pages(builds_root: str, tag: str) -> tuple:
    d = os.path.join(builds_root, tag)
    if not os.path.isdir(d):
        raise ValueError("corpus build not found: %s" % tag)
    corpus = C.read_json(os.path.join(d, "corpus.json"))
    pages = C.read_jsonl(os.path.join(d, "pages.jsonl"))
    return d, corpus, pages


def _key(p):
    """کلید تطبیق بین نسخه‌ها: source_page_id (ثابت از production DB)."""
    return p.get("source_page_id")


def diff_corpora(data_root: str, from_tag: str, to_tag: str) -> dict:
    paths = V.root_paths(data_root)
    builds = paths["corpus_builds"]
    d_from, c_from, pages_from = _load_corpus_pages(builds, from_tag)
    d_to, c_to, pages_to = _load_corpus_pages(builds, to_tag)

    by_from = {_key(p): p for p in pages_from}
    by_to = {_key(p): p for p in pages_to}

    added, changed, healed, unchanged = [], [], [], 0
    dup_new = 0

    for k, p in by_to.items():
        flags_to = p["quality_status"]["flags"]
        if k not in by_from:
            added.append({"source_page_id": k, "page_id": p["page_id"],
                          "item_index": p.get("item_index"),
                          "volume_id": p.get("volume_id"),
                          "flags": flags_to})
            if "dup_item_index" in flags_to:
                dup_new += 1
            continue
        old = by_from[k]
        if old.get("content_hash") != p.get("content_hash") or \
           (old.get("text") or "") != (p.get("text") or ""):
            changed.append({"source_page_id": k, "page_id": p["page_id"],
                            "item_index": p.get("item_index"),
                            "old_content_hash": old.get("content_hash"),
                            "new_content_hash": p.get("content_hash"),
                            "flags": flags_to})
        else:
            unchanged += 1
            # healed: flag سابق از بین رفته
            old_flags = set(old["quality_status"]["flags"])
            if old_flags - set(flags_to):
                healed.append({"source_page_id": k, "page_id": p["page_id"],
                               "fixed_flags": sorted(old_flags - set(flags_to)),
                               "remaining_flags": flags_to})

    removed = [{"source_page_id": k, "page_id": by_from[k]["page_id"],
                "item_index": by_from[k].get("item_index"),
                "volume_id": by_from[k].get("volume_id"),
                "note": "removed_from_source — در پیکره‌ی قبلی بود، در منبع جدید نیست (حذف خودکار ممنوع؛ نسخه‌ی قبلی immutable)"}
               for k in by_from if k not in by_to]

    change = {
        "kind": "tasnim-change-manifest",
        "from": from_tag,
        "to": to_tag,
        "from_content_sha256": _manifest_sha(d_from),
        "to_content_sha256": _manifest_sha(d_to),
        "counts": {
            "from_pages": len(pages_from),
            "to_pages": len(pages_to),
            "added": len(added),
            "changed": len(changed),
            "unchanged": unchanged,
            "healed": len(healed),
            "removed_from_source": len(removed),
            "duplicate_rows_in_new": dup_new,
        },
        "added": added[:1000],
        "changed": changed[:1000],
        "healed": healed[:1000],
        "removed_from_source": removed[:1000],
        "truncated": {"added": len(added) > 1000, "changed": len(changed) > 1000,
                      "healed": len(healed) > 1000,
                      "removed_from_source": len(removed) > 1000},
    }
    return change


def _manifest_sha(build_dir: str) -> str:
    mp = os.path.join(build_dir, "manifest.json")
    if os.path.exists(mp):
        m = C.read_json(mp)
        return (m.get("data") or {}).get("content_sha256")
    return None


def write_change_manifest(data_root: str, from_tag: str, to_tag: str) -> dict:
    paths = V.root_paths(data_root)
    d = os.path.join(paths["reports"], "diff_%s_%s" % (from_tag, to_tag))
    os.makedirs(d, exist_ok=True)
    change = diff_corpora(data_root, from_tag, to_tag)
    p = os.path.join(d, "change-manifest.json")
    C.write_json(p, change)
    return {"dir": d, "path": p, "sha256": C.sha256_file(p), "change": change}

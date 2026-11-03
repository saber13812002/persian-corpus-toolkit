# -*- coding: utf-8 -*-
"""tasnim.versioning — ساختار دایرکتوری و قوانین نسخه‌پذیری (PCM-20.3 §7).

ساختار زیر data/tasnim:

    sources/                          (اسنپ‌شات‌های ورودی — فقط‌خواندن بعد از ثبت)
      <TS>-<sha8>/  (فایل‌های PCM-20 + manifest.json)
    corpus/builds/
      v0001/  (corpus.json + pages.jsonl + manifest.json)
      v0002/  ...
    datasets/
      <pct>/
        v0001/  (dataset.json + pages.jsonl + manifest.json)
        v0002/  ...
    dumps/
      <pct>/
        v0001/  (books.json + product.json + manifest.json)
    manifests/
      v0001/manifest.json             (registry: زنجیره‌ی کلی + فهرست نسخه‌ها)
    reports/                          (خروجی audit/diff — برای انسان)

قوانین:
  * نسخه‌ها فقط افزایشی: هرگز بازنویسی/حذف.
  * idempotent: اگر content_sha256 ورودی+پیکربندی با آخرین نسخه برابر بود →
    همان نسخه REUSED می‌شود (خروجی جدید ساخته نمی‌شود).
"""
from __future__ import annotations

import os

from . import common as C

MANIFEST_VERSION = "m-20.3"

DATASET_PCTS = (1, 10, 50, 90, 100)


def root_paths(data_root: str) -> dict:
    return {
        "root": os.path.abspath(data_root),
        "sources": os.path.join(data_root, "sources"),
        "corpus_builds": os.path.join(data_root, "corpus", "builds"),
        "datasets": os.path.join(data_root, "datasets"),
        "dumps": os.path.join(data_root, "dumps"),
        "manifests": os.path.join(data_root, "manifests"),
        "reports": os.path.join(data_root, "reports"),
    }


def pct_dirname(pct: int) -> str:
    if pct == 100:
        return "100pct"
    return "%dpct" % pct


# --------------------------------------------------------------------------- versions
def next_version_number(builds_root: str, subdir: str = None) -> int:
    """بعد از بزرگ‌ترین vNNNN موجود → +1 (اولین نسخه = 1)."""
    d = os.path.join(builds_root, subdir) if subdir else builds_root
    if not os.path.isdir(d):
        return 1
    best = 0
    for name in os.listdir(d):
        if name.startswith("v") and name[1:].isdigit():
            best = max(best, int(name[1:]))
    return best + 1


def version_tag(number: int) -> str:
    return "v%04d" % number


def version_dir(builds_root: str, tag: str, subdir: str = None) -> str:
    d = os.path.join(builds_root, subdir) if subdir else builds_root
    return os.path.join(d, tag)


def read_registry(registry_dir: str) -> dict:
    """registry زنجیره‌ی کلی (manifests/registry.json) — اگر نبود → خالی."""
    p = os.path.join(registry_dir, "registry.json")
    if not os.path.exists(p):
        return {"chain": {}, "updated_at": None}
    return C.read_json(p)


def update_registry(registry_dir: str, kind: str, version: str,
                    entry: dict) -> dict:
    """ثبت یک نسخه در registry + برگشت registry به‌روز. (idempotent)"""
    reg = read_registry(registry_dir)
    chain = reg.setdefault("chain", {})
    chain[kind + ":" + version] = entry
    reg["updated_at"] = C.now_utc()
    C.write_json(os.path.join(registry_dir, "registry.json"), reg)
    return reg


# --------------------------------------------------------------------------- idempotency
def find_reusable_version(builds_root: str, subdir: str,
                          content_sha256: str) -> str:
    """اگر نسخه‌ای با همین content_sha256 دارد → tag آن، وگرنه None."""
    d = os.path.join(builds_root, subdir) if subdir else builds_root
    if not os.path.isdir(d):
        return None
    for name in sorted(os.listdir(d)):
        mp = os.path.join(d, name, "manifest.json")
        if not (name.startswith("v") and os.path.exists(mp)):
            continue
        try:
            m = C.read_json(mp)
        except Exception:
            continue
        if (m.get("data") or {}).get("content_sha256") == content_sha256:
            return name
    return None

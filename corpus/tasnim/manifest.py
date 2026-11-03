# -*- coding: utf-8 -*-
"""tasnim.manifest — زنجیره‌ی manifest و provenance (PCM-20.3 §7).

هر نسخه (source / corpus / dataset / dump) یک manifest.json دارد که:
  * به نسخه‌ی قبلی زنجیره می‌خورد (prev: version + sha256 + path_rel)؛
  * SHA-256 ورودی و خروجی‌های خود را ثبت می‌کند؛
  * قابل بازتأیید است: validate_manifest همه‌ی SHAها را از نو محاسبه می‌کند.

زنجیره:  source snapshot → corpus vX → dataset (pct) → dump
قاعده: «هیچ نسخه‌ای بدون provenance اثبات‌پذیر پذیرفته نمی‌شود».
"""
from __future__ import annotations

import os

from . import common as C
from . import versioning as V


def build_manifest(kind: str, version: str, data: dict) -> dict:
    """manifest یک نسخه.

    kind ∈ {source-snapshot, corpus, dataset, dump}
    data: دیکتاریوم آزادِ جزئیات (files, config, stats, ...) — field وابسته
          به زمان در content نیست؛ created_at جدا ثبت می‌شود (خارج از content sha).
    """
    manifest = {
        "manifest_version": V.MANIFEST_VERSION,
        "kind": kind,
        "version": version,
        "created_at": C.now_utc(),
        "product": "corpus.tasnim",
    }
    prev = data.pop("_prev", None)
    if prev:
        manifest["prev"] = prev
    manifest["data"] = data
    return manifest


def write_manifest(dir_path: str, manifest: dict) -> dict:
    """نوشتن manifest.json در dir_path + برگشت {path, sha256}."""
    path = os.path.join(dir_path, "manifest.json")
    C.write_json(path, manifest)
    return {"path": path, "sha256": C.sha256_file(path)}


def load_manifest(dir_path: str) -> dict:
    return C.read_json(os.path.join(dir_path, "manifest.json"))


def chain_entry(manifest: dict, dir_rel: str = None) -> dict:
    """ورودی زنجیره برای نسخه‌ی بعدی.

    dir_rel: مسیر نسبی دایرکتوری نسخه به data_root (با "/" — برای path_rel).
             اگر dir_rel خودش با manifest.json تمام شود، دوباره اضافه نمی‌شود.
    """
    entry = {
        "version": manifest.get("version"),
        "kind": manifest.get("kind"),
        "sha256": C.sha256_text(C.canonical_json(manifest).decode("utf-8")),
    }
    if dir_rel:
        rel = dir_rel.replace(os.sep, "/").strip("/")
        if not rel.endswith("manifest.json"):
            rel = rel + "/manifest.json"
        entry["path_rel"] = rel
    return entry


# --------------------------------------------------------------------------- validation
def _find_data_root(dir_path: str) -> str:
    """data_root را از دایرکتوری نسخه کشف می‌کند (والدِ «manifests»/«sources»/«corpus»)."""
    d = os.path.abspath(dir_path)
    for _ in range(8):
        if os.path.isdir(os.path.join(d, "manifests")) or os.path.isdir(os.path.join(d, "sources")) \
           or os.path.isdir(os.path.join(d, "corpus")):
            return d
        parent = os.path.dirname(d)
        if parent == d:
            break
        d = parent
    return None


def _check_files(data: dict, base_dir: str, errors: list) -> None:
    files = data.get("files") or {}
    for name, meta in files.items():
        p = os.path.join(base_dir, name)
        if not os.path.exists(p):
            errors.append("file missing: %s" % name)
            continue
        if C.sha256_file(p) != meta.get("sha256"):
            errors.append("sha mismatch: %s" % name)
        if meta.get("size_bytes") is not None and C.file_size(p) != meta["size_bytes"]:
            errors.append("size mismatch: %s" % name)


def validate_manifest(dir_path: str, data_root: str = None) -> tuple:
    """بازتأیید کامل: برگشت (ok, errors, warnings).

    data_root: ریشه‌ی data/tasnim (اگر نبود، خودکار کشف می‌شود).
    """
    errors, warnings = [], []
    try:
        m = load_manifest(dir_path)
    except Exception as e:
        return False, ["manifest unreadable: %s" % e], []

    if m.get("manifest_version") != V.MANIFEST_VERSION:
        warnings.append("manifest_version mismatch: %r" % m.get("manifest_version"))
    if not m.get("kind"):
        errors.append("kind missing")
    if not m.get("version"):
        errors.append("version missing")

    # chain: prev باید موجود باشد و SHAاش با manifest ثبت‌شده یکی
    prev = m.get("prev")
    if prev:
        prev_path = None
        if prev.get("path_rel"):
            root = data_root or _find_data_root(dir_path)
            if root:
                cand = os.path.join(root, prev["path_rel"].replace("/", os.sep))
                if os.path.exists(cand):
                    prev_path = cand
        if prev_path is None:
            warnings.append("prev manifest not found on disk: %s" % prev.get("version"))
        else:
            try:
                prev_m = load_manifest(os.path.dirname(prev_path))
                if C.sha256_text(C.canonical_json(prev_m).decode("utf-8")) != prev.get("sha256"):
                    errors.append("prev sha mismatch: %s" % prev.get("version"))
            except Exception as e:
                errors.append("prev manifest unreadable: %s" % e)

    _check_files(m.get("data") or {}, dir_path, errors)
    return (not errors), errors, warnings

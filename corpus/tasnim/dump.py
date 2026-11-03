# -*- coding: utf-8 -*-
"""tasnim.dump — Adapter خروجی به ai-dump-builder (PCM-20.3 §6).

قواعد:
  * کد Builder دست‌نخورده می‌ماند؛ این ماژول فقط «ورودی» Builder را می‌سازد
    و در کنارش یک «چک سازگاری محلی» دارد که دقیقاً همان منطق استخراج
    Builder (extract_records) را روی همان داده اجرا می‌کند.
  * یک Book برای هر جلد:  dap_code = "tasnim__vol<N>"  (جلد نامشخص: "tasnim__vol-unknown").
  * page_number = barg واقعی (اگر نبود item_index+1؛ اگر آن هم نبود 0).
  * paragraph_text = text_normalized (RAW در extra_metadata بازمی‌گردد).
  * provenance در همه‌ی رکوردها: page_id, item_index, barg, volume_no, url,
    captured_at, content_hash, source_page_id.

خروجی: dumps/<pct>/vNNNN/{books.json, product.json, dump-check.json, manifest.json}
کد Builder:  python -m builder.cli build --product <dir>  (بعدی: فاز embedding)
"""
from __future__ import annotations

import os

from . import common as C
from . import manifest as M
from . import versioning as V
from .transform import content_sha256_of_files

PRODUCT_NAME = "tasnim_tafsir"
DEFAULT_MODEL = "Qwen3-Embedding-0.6B"
AVAILABLE_MODELS = ["Qwen3-Embedding-0.6B", "Qwen3-Embedding-4B"]

EXTRA_METADATA = [
    "page_id", "item_index", "barg", "volume_no",
    "url", "captured_at", "content_hash", "source_page_id", "raw_text",
]


def dap_code_of(volume_no) -> str:
    return "tasnim__vol%03d" % volume_no if volume_no is not None else "tasnim__vol-unknown"


def volume_title_of(recs: list) -> str:
    v = recs[0].get("volume") or {}
    if v.get("volume_no") is None:
        return "تفسیر تسنیم — جلد نامشخص"
    return "تفسیر تسنیم جلد %d" % v["volume_no"]


def page_number_of(p: dict) -> int:
    if p.get("barg") is not None:
        return int(p["barg"])
    if p.get("item_index") is not None:
        return int(p["item_index"]) + 1
    return 0


# --------------------------------------------------------------------------- books.json
def build_books(pages: list) -> list:
    """pages → لیست کتاب‌ها (ساختار ورودی Builder)."""
    by_vol = {}
    for p in pages:
        vid = p["volume_id"]
        by_vol.setdefault(vid, []).append(p)

    vols = sorted(by_vol.items(),
                  key=lambda kv: (0 if (kv[1][0].get("volume") or {}).get("volume_no") is not None else 1,
                                  (kv[1][0].get("volume") or {}).get("volume_no") or 0, kv[0]))
    books = []
    for vid, recs in vols:
        recs = sorted(recs, key=lambda r: (r.get("item_index") is None,
                                            r.get("item_index") if r.get("item_index") is not None else 0,
                                            r.get("position", 0)))
        vno = (recs[0].get("volume") or {}).get("volume_no")
        dap = dap_code_of(vno)
        title = volume_title_of(recs)
        book = {
            "dap_code": dap,
            "title": title,
            "language": "fa",
            "page_count": len(recs),
            "pages": [],
        }
        for p in recs:
            text_norm = p.get("text_normalized") or ""
            book["pages"].append({
                "title": title,
                "dap_code": dap,
                "page_number": page_number_of(p),
                "paragraph_text": text_norm,
                "language": "fa",
                "words_count": C.words_count(text_norm),
                "_id": p["source_page_id"],
                # --- provenance (از طریق extra_metadata به Dump منتقل می‌شود) ---
                "page_id": p["page_id"],
                "item_index": p.get("item_index"),
                "barg": p.get("barg"),
                "volume_no": vno,
                "url": p.get("url"),
                "captured_at": p.get("captured_at"),
                "content_hash": p.get("content_hash"),
                "source_page_id": p.get("source_page_id"),
                "raw_text": p.get("text"),
            })
        books.append(book)
    return books


def make_product(export_file: str = "books.json") -> dict:
    """product.json برای kد Builder — بدون هیچ رمزی (litellm_key=null)."""
    return {
        "product": PRODUCT_NAME,
        "export_file": export_file,
        "builds_dir": "builds",
        "dump_filename": "chunks.jsonl",
        "collection_name_pattern": "{product}__{model_slug}",
        "litellm_base": None,
        "litellm_key": None,
        "_docs": ("litellm_base/litellm_key عمداً خالی‌اند: Builder از محیط "
                  "(LITELLM_API_KEY / LITELLM_BASE_URL) می‌خواند. "
                  "برای ساخت واقعی، product را در دایرکتوری product Builder کپی "
                  "و مسیرها را تنظیم کنید."),
        "models": {"default": DEFAULT_MODEL, "available": list(AVAILABLE_MODELS)},
        "min_text_chars": 20,
        "max_embed_chars": 6000,
        "embed_batch": 16,
        "embed_concurrency": 4,
        "extra_metadata": list(EXTRA_METADATA),
        "unattended": False,
    }


# --------------------------------------------------------------------------- compat check
def _norm(s):
    """همان norm Builder (core.py:77-78)."""
    return "" if s is None else str(s).strip()


def _make_chunk_text(page):
    """همان make_chunk_text Builder (core.py:114-122)."""
    meta = "Metadata: " + "\n".join([
        "book_name:" + _norm(page.get("title")),
        "book_id:" + _norm(page.get("dap_code")),
        "page_number:%d" % (page.get("page_number") or 0),
    ])
    content = _norm(page.get("paragraph_text"))
    return "%s\n-----\nContent: %s" % (meta, content)


def extract_like_builder(books: list, cfg: dict):
    """تکرارِ دقیق extract_records Builder (core.py:125-162) — بدون embedding.

    برگشت: (records, stats) — مطابق منطق Builder: skip زیر min_text_chars،
    truncate روی max_embed_chars، کپی extra_metadata فقط اگر موجود باشد.
    """
    min_chars = int(cfg.get("min_text_chars", 20))
    max_embed = int(cfg.get("max_embed_chars", 6000))
    extra = cfg.get("extra_metadata") or []
    records, skipped, truncated = [], 0, 0
    for book in books:
        dap = _norm(book.get("dap_code"))
        for idx, page in enumerate(book.get("pages") or []):
            text = _norm(page.get("paragraph_text"))
            if len(text) < min_chars:
                skipped += 1
                continue
            chunk_text = _make_chunk_text(page)
            embed_input = chunk_text if len(chunk_text) <= max_embed else chunk_text[:max_embed]
            if len(chunk_text) > max_embed:
                truncated += 1
            rec = {
                "book_id": dap,
                "book_name": _norm(page.get("title")),
                "page_number": page.get("page_number") or 0,
                "chunk_id": idx,
                "chunk_text": chunk_text,
                "link": "book://%s#p%s" % (dap, page.get("page_number")),
                "source_id": page.get("_id"),
                "language": _norm(page.get("language")),
                "words_count": page.get("words_count") or 0,
            }
            for k in extra:
                if k in page and page.get(k) is not None:
                    rec[k] = page[k]
            records.append(rec)
    stats = {"total": len(records), "skipped_short": skipped, "truncated": truncated}
    return records, stats


REQUIRED_DUMP_FIELDS = ["book_id", "book_name", "chunk_text", "chunk_id", "page_number"]


def compat_check(books: list, cfg: dict) -> dict:
    """چک سازگاری محلی: records استخراج‌شده + اعتبار فیلدهای REQUIRED + provenance."""
    records, stats = extract_like_builder(books, cfg)
    errors, warnings = [], []
    missing_prov = 0
    seen_ids = set()
    for r in records:
        for f in REQUIRED_DUMP_FIELDS:
            if r.get(f) in (None, ""):
                errors.append("record %s: required field %r missing" % (r.get("source_id"), f))
        if r.get("content_hash") is None:
            missing_prov += 1
        sid = r.get("source_id")
        if sid in seen_ids:
            warnings.append("duplicate source_id in export: %r" % sid)
        seen_ids.add(sid)
    if missing_prov:
        warnings.append("%d records without content_hash provenance" % missing_prov)
    # صفحه‌های کوتاه که Builder skip می‌کند (حذف نیست — فقط از Dump خارج می‌شوند)
    total_pages = sum(len(b.get("pages") or []) for b in books)
    return {
        "books": len(books),
        "pages_total": total_pages,
        "records_extracted": stats["total"],
        "skipped_short_lt_min_text_chars": stats["skipped_short"],
        "truncated_at_max_embed_chars": stats["truncated"],
        "min_text_chars": int(cfg.get("min_text_chars", 20)),
        "max_embed_chars": int(cfg.get("max_embed_chars", 6000)),
        "required_fields_ok": not errors,
        "errors": errors,
        "warnings": warnings,
    }


# --------------------------------------------------------------------------- write
def write_dump(data_root: str, pct: int, dataset_manifest: dict,
               pages: list) -> dict:
    """نوشتن (فقط افزایشی) یک نسخه‌ی dump: books.json + product.json + check."""
    paths = V.root_paths(data_root)
    pdir = V.pct_dirname(pct)
    builds_root = os.path.join(paths["dumps"], pdir)
    tag = V.version_tag(V.next_version_number(builds_root))
    out_dir = V.version_dir(builds_root, tag)
    os.makedirs(out_dir, exist_ok=True)

    books = build_books(pages)
    cfg = make_product()
    check = compat_check(books, cfg)
    if check["errors"]:
        raise RuntimeError("compat check failed: %s" % check["errors"][:5])

    books_path = os.path.join(out_dir, "books.json")
    product_path = os.path.join(out_dir, "product.json")
    check_path = os.path.join(out_dir, "dump-check.json")
    C.write_json(books_path, books)
    C.write_json(product_path, cfg)
    C.write_json(check_path, check)
    files = {name: {"sha256": C.sha256_file(os.path.join(out_dir, name)),
                    "size_bytes": C.file_size(os.path.join(out_dir, name))}
             for name in ("books.json", "product.json", "dump-check.json")}
    content_sha256 = content_sha256_of_files(files)

    ds_ver = str(dataset_manifest.get("version") or "")
    prev_rel = os.path.relpath(
        os.path.join(paths["datasets"], V.pct_dirname(pct), ds_ver),
        paths["root"]).replace(os.sep, "/") + "/manifest.json"
    manifest = M.build_manifest("dump", tag, {
        "percentage": pct,
        "content_sha256": content_sha256,
        "files": files,
        "builder": {
            "product": PRODUCT_NAME,
            "adapter": "corpus.tasnim.dump (local reimplementation of extract_records)",
            "note": ("embedding/Neo4j OUT OF SCOPE در این فاز؛ اجرای واقعی Builder "
                     "در مأموریت بعدی."),
        },
        "compat_check": check,
        "_prev": M.chain_entry(dataset_manifest, prev_rel),
    })
    M.write_manifest(out_dir, manifest)
    V.update_registry(paths["manifests"], "dump:%s" % pdir, tag,
                      {"dataset": dataset_manifest.get("version"),
                       "content_sha256": content_sha256,
                       "sha256": C.sha256_file(os.path.join(out_dir, "manifest.json"))})
    return {"version": tag, "dir": out_dir, "files": files,
            "content_sha256": content_sha256, "check": check, "reused": False}

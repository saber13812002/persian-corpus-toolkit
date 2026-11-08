# -*- coding: utf-8 -*-
"""tasnim.cli — رابط خط فرمان خط تولید تسنیم (PCM-20.3 §8).

زیردستورها:
    audit            درگاه آشتیابی روی خروجی PCM-20 (فقط‌خواندن)
    build-corpus     ساخت پیکره‌ی رسمی (نسخه‌ای + manifest + validate)
    build-semantic   لایه‌ی معنایی روی یک build (PCM-20.5 GATE 1) — نسخه‌ی جدید
    build-enriched   retrieval-context عنوان‌ها (cs-20.7؛ PCM-20.7C؛ base cs-20.6)
    validate-corpus  اعتبارسنجی یک build موجود (به‌صورت خودکار S01..S07 برای semantic)
    build-dataset    ساخت دیتاست pct٪ (لایه‌بندی‌شده، قطعی) [+ --volume N]
    export-dump      ساخت خروجی سازگار با ai-dump-builder (بدون embedding)
    diff             Change Manifest بین دو نسخه‌ی پیکره
    semantic-diff    semantic-diff 7 دسته‌ای بین دو build (PCM-20.5 GATE 1)

کد خروجی: 0 = موفق/REUSED · 1 = خطای اجرا/اعتبارسنجی · 2 = خطای ورودی.
همه‌ی زیردستورها فقط‌خواندن روی ورودی‌ها هستند؛ خروجی زیر data/tasnim می‌نویسد.
"""
from __future__ import annotations

import argparse
import os
import sys

from . import common as C
from . import dataset as D
from . import diff as DFF
from . import dump as DP
from . import enrich as ENR
from . import manifest as M
from . import normalize as N
from . import reconcile as R
from . import schema as S
from . import semantic as SEM
from . import transform as T
from . import validate as VAL
from . import versioning as V


def _emit(msg: str) -> None:
    print(msg, flush=True)


def _fail(msg: str, code: int = 1) -> int:
    _emit("ERROR: %s" % msg)
    return code


def _last_corpus_entry(data_root: str):
    """آخرین نسخه‌ی ثبت‌شده‌ی corpus در registry (برای زنجیره‌ی prev)."""
    reg = V.read_registry(V.root_paths(data_root)["manifests"])
    chain = reg.get("chain") or {}
    for key in sorted(chain):
        if key.startswith("corpus:"):
            v = key.split(":", 1)[1]
            d = os.path.join(V.root_paths(data_root)["corpus_builds"], v)
            if os.path.exists(os.path.join(d, "manifest.json")):
                try:
                    m = M.load_manifest(d)
                    return M.chain_entry(
                        m, os.path.relpath(d, V.root_paths(data_root)["root"]).replace(os.sep, "/") + "/manifest.json")
                except Exception:
                    continue
    return None


# --------------------------------------------------------------------------- audit
def cmd_audit(args) -> int:
    if not os.path.exists(args.jsonl):
        return _fail("jsonl not found: %s" % args.jsonl, 2)
    source = R.load_source(args.jsonl, args.json, args.summary)
    gate = R.gate_report(source)
    _emit("=== TASNIM AUDIT (read-only) ===")
    _emit("source jsonl : %s" % source["jsonl_path"])
    _emit("jsonl sha256 : %s  (%d bytes, %d records)"
          % (source["jsonl_sha256"], source["jsonl_size_bytes"], source["record_count"]))
    if source.get("summary"):
        _emit("summary sha256: %s" % source["summary_sha256"])
    _emit("-- integrity --")
    for k in ("incomplete_empty", "short_lt_%d" % R.MIN_TEXT_CHARS, "truncated_at_2000",
              "no_barg", "missing_item_index"):
        _emit("  %-22s %d" % (k, gate[k]))
    tl = gate["text_len"]
    _emit("  text_len           p50=%s p90=%s p99=%s max=%s"
          % (tl["p50"], tl["p90"], tl["p99"], tl["max"]))
    _emit("-- duplicates --")
    _emit("  dup item_index     %d values / %d extra rows"
          % (gate["duplicate_item_index"]["value_count"], gate["duplicate_item_index"]["extra_rows"]))
    _emit("  dup content_hash   %d values / %d extra rows"
          % (gate["duplicate_content_hash"]["value_count"], gate["duplicate_content_hash"]["extra_rows"]))
    _emit("-- barg reparse (fixed parser) --")
    b = gate["barg_reparse"]
    _emit("  with raw barg      %d" % b["with_raw_barg"])
    _emit("  with parsed barg   %d" % b["with_parsed_barg"])
    _emit("  == item_index+1    %d" % b["equals_item_index_plus_1"])
    _emit("  != export barg     %d" % b["differs_from_export_barg"])
    _emit("-- item_index gap --")
    gi = gate["item_index"]
    _emit("  min=%s max=%s distinct=%d missing=%d dup=%d"
          % (gi["min"], gi["max"], gi["distinct"], gi["missing_count"], gi["dup_count"]))
    _emit("-- volumes --")
    _emit("  strategy census    %s" % gate["volume_strategy_census"])
    _emit("  distinct url sections: %d" % gate["distinct_url_sections"])

    out_path = args.out
    if out_path is None:
        if args.data_root:
            out_path = os.path.join(V.root_paths(args.data_root)["reports"],
                                    "audit-%s.json" % source["jsonl_sha256"][:12])
        else:
            out_path = os.path.join(os.path.dirname(os.path.abspath(args.jsonl)),
                                    "tasnim_audit.json")
    audit = {
        "kind": "tasnim-audit",
        "source": {"jsonl_path": source["jsonl_path"], "jsonl_sha256": source["jsonl_sha256"],
                   "summary_sha256": source.get("summary_sha256")},
        "gate": gate,
    }
    C.write_json(out_path, audit)
    _emit("audit written  : %s  sha256=%s" % (out_path, C.sha256_file(out_path)))
    _emit("DONE — read-only; nothing was modified.")
    return 0


# --------------------------------------------------------------------------- build-corpus
def _register_source_snapshot(data_root: str, source: dict) -> dict:
    """ثبت اسنپ‌شات منبع (path+sha؛ بدون کپی فایل) + manifest زنجیره‌ی ریشه."""
    paths = V.root_paths(data_root)
    tag = "s%s" % source["jsonl_sha256"][:12]
    snap_dir = os.path.join(paths["sources"], tag)
    if os.path.exists(os.path.join(snap_dir, "manifest.json")):
        return M.load_manifest(snap_dir)
    files = {"jsonl": {"sha256": source["jsonl_sha256"], "size_bytes": source["jsonl_size_bytes"]}}
    manifest = M.build_manifest("source-snapshot", tag, {
        "files": files,
        "paths": {"jsonl": source["jsonl_path"], "json": source.get("json_path"),
                  "summary": source.get("summary_path")},
        "page_count": source["record_count"],
        "exported_at_utc": (source.get("json_meta") or {}).get("exported_at_utc"),
        "project_id": ((source.get("json_meta") or {}).get("project") or {}).get("id"),
        "content_sha256": source["jsonl_sha256"],
    })
    os.makedirs(snap_dir, exist_ok=True)
    M.write_manifest(snap_dir, manifest)
    V.update_registry(paths["manifests"], "source-snapshot", tag,
                      {"sha256": C.sha256_file(os.path.join(snap_dir, "manifest.json"))})
    return manifest


def cmd_build_corpus(args) -> int:
    if not os.path.exists(args.jsonl):
        return _fail("jsonl not found: %s" % args.jsonl, 2)
    C.force_utf8_stdio()
    source = R.load_source(args.jsonl, args.json, args.summary)
    try:
        result = T.build_corpus(source, policy_id=args.policy)
    except ValueError as e:
        return _fail(str(e), 2)
    corpus, pages = result["corpus"], result["pages"]

    # idempotency: content از حافظه (بدون نوشتن)
    files = T.content_files(corpus, pages)
    csha = T.content_sha256_of_files(files)
    paths = V.root_paths(args.data_root)
    builds = paths["corpus_builds"]
    reuse = V.find_reusable_version(builds, None, csha)
    if reuse:
        _emit("REUSED %s — content identical (same input + config). No new version." % reuse)
        return 0

    src_manifest = _register_source_snapshot(args.data_root, source)
    snap_rel = os.path.relpath(os.path.join(paths["sources"], src_manifest["version"]),
                               paths["root"]).replace(os.sep, "/") + "/manifest.json"
    prev_entry = _last_corpus_entry(args.data_root)
    if prev_entry is None:
        prev_entry = M.chain_entry(src_manifest, snap_rel)

    tag = V.version_tag(V.next_version_number(builds))
    out_dir = V.version_dir(builds, tag)
    written = T.write_corpus(out_dir, corpus, pages)
    if written["files"] != files:
        return _fail("write verification failed (sha mismatch after write)")

    manifest = M.build_manifest("corpus", tag, {
        "content_sha256": csha,
        "files": written["files"],
        "source": {"jsonl_path": source["jsonl_path"], "jsonl_sha256": source["jsonl_sha256"],
                   "json_path": source.get("json_path"),
                   "summary_sha256": source.get("summary_sha256"),
                   "snapshot": src_manifest["version"]},
        "config": corpus.get("config") or {},
        "stats": corpus.get("stats") or {},
        "_prev": prev_entry,
    })
    M.write_manifest(out_dir, manifest)
    V.update_registry(paths["manifests"], "corpus", tag,
                      {"content_sha256": csha,
                       "sha256": C.sha256_file(os.path.join(out_dir, "manifest.json"))})

    _emit("=== BUILD CORPUS ===")
    _emit("version        : %s" % tag)
    _emit("pages          : %d" % len(pages))
    _emit("volumes        : %d" % len(corpus["volumes"]))
    _emit("content sha256 : %s" % csha)
    _emit("build dir      : %s" % out_dir)

    ok, errors, warnings = VAL.validate_corpus(out_dir)
    _emit("validate       : %s" % ("PASS" if ok else "FAIL"))
    for e in errors[:10]:
        _emit("  ERROR: %s" % e)
    for w in warnings[:10]:
        _emit("  WARN: %s" % w)
    if not ok:
        return 1
    _emit("DONE.")
    return 0


# --------------------------------------------------------------------------- validate-corpus
def cmd_validate_corpus(args) -> int:
    build_dir = args.build
    if not os.path.isdir(build_dir):
        cand = os.path.join(V.root_paths(args.data_root)["corpus_builds"], build_dir)
        if os.path.isdir(cand):
            build_dir = cand
    if not os.path.isdir(build_dir):
        return _fail("corpus build dir not found: %s" % args.build, 2)
    ok, errors, warnings = VAL.validate_corpus(build_dir)
    # PCM-20.5 GATE 1: اگر build لایه‌ی معنایی دارد، S01..S07 هم اجرا می‌شود
    root_hint = args.data_root if os.path.isdir(args.data_root) else None
    try:
        corpus = C.read_json(os.path.join(build_dir, "corpus.json"))
        if "semantic" in corpus:
            ok2, s_errors, s_warnings = SEM.validate_semantic(build_dir, root_hint)
            errors = list(errors) + ["S: %s" % e for e in s_errors]
            warnings = list(warnings) + list(s_warnings)
            ok = ok and ok2
    except Exception:
        pass
    _emit("=== VALIDATE CORPUS: %s ===" % build_dir)
    for e in errors:
        _emit("  ERROR: %s" % e)
    for w in warnings:
        _emit("  WARN: %s" % w)
    _emit("RESULT: %s" % ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


# --------------------------------------------------------------------------- build-semantic (PCM-20.5 GATE 1)
def cmd_build_semantic(args) -> int:
    C.force_utf8_stdio()
    paths = V.root_paths(args.data_root)
    builds = paths["corpus_builds"]
    base_dir = os.path.join(builds, args.base)
    if not os.path.isdir(base_dir):
        return _fail("base corpus build not found: %s" % args.base, 2)
    contract = args.contract
    if contract == SEM.SEMANTIC_SCHEMA_VERSION_ENRICHED:
        return _fail("contract %s is produced by 'build-enriched' "
                     "(needs a summaries checkpoint)" % contract, 2)
    try:
        if contract == SEM.SEMANTIC_SCHEMA_VERSION_V3:
            result = SEM.build_semantic_v3(base_dir)
        else:
            result = SEM.build_semantic(base_dir)
    except ValueError as e:
        return _fail(str(e), 2)
    corpus2, pages2, context = result["corpus"], result["pages"], result["context"]
    heading_records = result.get("heading_records")
    hidden_context = result.get("hidden_context")
    base_manifest, base_rel = result["base_manifest"], result["base_rel"]

    files = SEM.content_files_semantic(corpus2, pages2, context,
                                       heading_records, hidden_context)
    csha = T.content_sha256_of_files(files)
    reuse = V.find_reusable_version(builds, None, csha)
    if reuse:
        _emit("REUSED %s — semantic content identical (same base + rules). No new version."
              % reuse)
        return 0

    bdata = base_manifest.get("data") or {}
    prev_entry = M.chain_entry(base_manifest, base_rel)
    tag = V.version_tag(V.next_version_number(builds))
    out_dir = V.version_dir(builds, tag)
    written = SEM.write_semantic(out_dir, corpus2, pages2, context,
                                 heading_records, hidden_context)
    if written["files"] != files:
        return _fail("write verification failed (sha mismatch after write)")

    manifest = M.build_manifest("corpus", tag, {
        "content_sha256": csha,
        "files": written["files"],
        "source": bdata.get("source") or {},
        "base": {"version": base_manifest.get("version"),
                 "content_sha256": bdata.get("content_sha256"),
                 "path_rel": base_rel},
        "config": corpus2.get("config") or {},
        "stats": corpus2.get("stats") or {},
        "gaps": SEM.gaps_ledger(corpus2),
        "_prev": prev_entry,
    })
    M.write_manifest(out_dir, manifest)
    V.update_registry(paths["manifests"], "corpus", tag,
                      {"content_sha256": csha,
                       "sha256": C.sha256_file(os.path.join(out_dir, "manifest.json"))})

    cc = result["class_counts"]
    _emit("=== BUILD SEMANTIC (contract=%s) ===" % contract)
    _emit("version        : %s" % tag)
    _emit("base           : %s (%s)" % (args.base, bdata.get("content_sha256")))
    _emit("contract       : %s" % contract)
    if hidden_context is not None:
        _emit("heading records: %d (hidden_context)" % len(heading_records))
        _emit("hidden context : %d (hidden_context, %s)"
              % (len(hidden_context), SEM.SUMMARY_METHOD))
        _emit("truncated@%d  : %d pages (GATE 1.5)"
              % (S.SOURCE_CHAR_CAP, len(result.get("truncation_pages") or [])))
    _emit("pages          : %d" % len(pages2))
    _emit("context records: %d (hidden, verbatim)" % len(context))
    _emit("class census   : %s" % cc)
    _emit("basis census   : %s" % result["basis_counts"])
    _emit("content sha256 : %s" % csha)
    _emit("build dir      : %s" % out_dir)

    ok, errors, warnings = VAL.validate_corpus(out_dir)
    ok2, s_errors, s_warnings = SEM.validate_semantic(out_dir, args.data_root)
    errors = list(errors) + ["S: %s" % e for e in s_errors]
    warnings = list(warnings) + list(s_warnings)
    ok = ok and ok2
    _emit("validate       : %s" % ("PASS" if ok else "FAIL"))
    for e in errors[:10]:
        _emit("  ERROR: %s" % e)
    for w in warnings[:10]:
        _emit("  WARN: %s" % w)
    if not ok:
        return 1
    _emit("DONE.")
    return 0


def cmd_build_enriched(args) -> int:
    C.force_utf8_stdio()
    paths = V.root_paths(args.data_root)
    builds = paths["corpus_builds"]
    base_dir = os.path.join(builds, args.base)
    if not os.path.isdir(base_dir):
        return _fail("base corpus build not found: %s" % args.base, 2)
    try:
        prepared = ENR.enriched_content(base_dir, args.summaries)
    except ValueError as e:
        return _fail(str(e), 2)
    corpus2 = prepared["corpus"]
    files = prepared["files"]
    csha = prepared["content_sha256"]
    reuse = V.find_reusable_version(builds, None, csha)
    if reuse:
        _emit("REUSED %s — enriched content identical (same base + summaries). "
              "No new version." % reuse)
        return 0
    base_manifest, base_rel = prepared["base_manifest"], prepared["base_rel"]
    bdata = base_manifest.get("data") or {}
    prev_entry = M.chain_entry(base_manifest, base_rel)
    tag = V.version_tag(V.next_version_number(builds))
    out_dir = V.version_dir(builds, tag)
    written = ENR.write_enriched(out_dir, prepared)
    if written["files"] != files:
        return _fail("write verification failed (sha mismatch after write)")
    manifest = M.build_manifest("corpus", tag, {
        "content_sha256": csha,
        "files": written["files"],
        "source": bdata.get("source") or {},
        "base": {"version": base_manifest.get("version"),
                 "content_sha256": bdata.get("content_sha256"),
                 "path_rel": base_rel},
        "previous_version": base_manifest.get("version"),
        "summaries_source": prepared["summaries_source"],
        "config": corpus2.get("config") or {},
        "stats": corpus2.get("stats") or {},
        "gaps": SEM.gaps_ledger(corpus2),
        "_prev": prev_entry,
    })
    M.write_manifest(out_dir, manifest)
    V.update_registry(paths["manifests"], "corpus", tag,
                      {"content_sha256": csha,
                       "sha256": C.sha256_file(os.path.join(out_dir, "manifest.json"))})
    ss = prepared["summaries_source"]
    _emit("=== BUILD ENRICHED (contract=%s) ===" % ENR.ENRICH_SCHEMA_VERSION)
    _emit("version        : %s" % tag)
    _emit("base           : %s (%s)" % (args.base, bdata.get("content_sha256")))
    _emit("summaries      : %s (%d entries, sha %s)"
          % (ss.get("file"), ss.get("count"), ss.get("sha256")))
    _emit("status census  : %s" % prepared["status_counts"])
    _emit("pages          : %d (byte-identical to base)" % len(prepared["pages"]))
    _emit("content sha256 : %s" % csha)
    _emit("build dir      : %s" % out_dir)
    ok, errors, warnings = VAL.validate_corpus(out_dir)
    ok2, s_errors, s_warnings = SEM.validate_semantic(out_dir, args.data_root)
    errors = list(errors) + ["S: %s" % e for e in s_errors]
    warnings = list(warnings) + list(s_warnings)
    ok = ok and ok2
    _emit("validate       : %s" % ("PASS" if ok else "FAIL"))
    for e in errors[:10]:
        _emit("  ERROR: %s" % e)
    for w in warnings[:10]:
        _emit("  WARN: %s" % w)
    if not ok:
        return 1
    _emit("DONE.")
    return 0


# --------------------------------------------------------------------------- build-dataset
def _load_corpus_build(data_root: str, tag: str) -> tuple:
    paths = V.root_paths(data_root)
    d = os.path.join(paths["corpus_builds"], tag)
    if not os.path.isdir(d):
        raise ValueError("corpus build not found: %s" % tag)
    return d, M.load_manifest(d), C.read_jsonl(os.path.join(d, "pages.jsonl"))


def _dataset_content(cmeta: dict, pages: list):
    c1 = C.canonical_json(cmeta)
    c2 = b"".join(C.canonical_json_line(p) for p in pages)
    return T.content_sha256_of_files({
        "dataset.json": {"sha256": C.sha256_bytes(c1), "size_bytes": len(c1)},
        "pages.jsonl": {"sha256": C.sha256_bytes(c2), "size_bytes": len(c2)},
    })


def cmd_build_dataset(args) -> int:
    if args.percentage not in V.DATASET_PCTS:
        return _fail("percentage must be one of %s" % (V.DATASET_PCTS,), 2)
    try:
        _d, corpus_manifest, pages = _load_corpus_build(args.data_root, args.corpus)
    except ValueError as e:
        return _fail(str(e), 2)
    try:
        result = D.select_dataset(pages, args.percentage, args.volume,
                                  args.volume_id, args.blocks)
    except ValueError as e:
        return _fail(str(e), 2)

    cmeta = D.dataset_meta(corpus_manifest, result, args.percentage)
    csha = _dataset_content(cmeta, result["pages"])
    paths = V.root_paths(args.data_root)
    builds = os.path.join(paths["datasets"], V.pct_dirname(args.percentage))
    reuse = V.find_reusable_version(builds, None, csha)
    if reuse:
        _emit("REUSED datasets/%s/%s — identical selection. No new version."
              % (V.pct_dirname(args.percentage), reuse))
        return 0

    written = D.write_dataset(args.data_root, args.percentage, corpus_manifest,
                              result, args.volume, args.volume_id)
    _emit("=== BUILD DATASET ===")
    _emit("pct            : %d%%" % args.percentage)
    _emit("version        : %s" % written["version"])
    _emit("selected pages : %d" % result["stats"]["selected_page_count"])
    _emit("corpus         : %s" % args.corpus)
    _emit("content sha256 : %s" % written["content_sha256"])
    _emit("out dir        : %s" % written["dir"])
    for drow in result["stats"]["volume_distribution"]:
        _emit("  vol %-6s pages=%-5d selected=%-5d coverage=%s%%"
              % (drow["volume_no"], drow["pages_in_volume"], drow["selected"],
                 drow["coverage_pct"]))
    _emit("DONE.")
    return 0


# --------------------------------------------------------------------------- export-dump
def _dump_content(books: list, cfg: dict, check: dict):
    c1 = C.canonical_json(books)
    c2 = C.canonical_json(cfg)
    c3 = C.canonical_json(check)
    return T.content_sha256_of_files({
        "books.json": {"sha256": C.sha256_bytes(c1), "size_bytes": len(c1)},
        "product.json": {"sha256": C.sha256_bytes(c2), "size_bytes": len(c2)},
        "dump-check.json": {"sha256": C.sha256_bytes(c3), "size_bytes": len(c3)},
    })


def cmd_export_dump(args) -> int:
    if args.percentage not in V.DATASET_PCTS:
        return _fail("percentage must be one of %s" % (V.DATASET_PCTS,), 2)
    if not args.dataset:
        return _fail("--dataset (vNNNN) is required", 2)
    paths = V.root_paths(args.data_root)
    ddir = os.path.join(paths["datasets"], V.pct_dirname(args.percentage), args.dataset)
    if not os.path.isdir(ddir):
        return _fail("dataset dir not found: %s" % ddir, 2)
    dataset_manifest = M.load_manifest(ddir)
    pages = C.read_jsonl(os.path.join(ddir, "pages.jsonl"))

    books = DP.build_books(pages)
    cfg = DP.make_product()
    check = DP.compat_check(books, cfg)
    if check["errors"]:
        return _fail("compat check failed: %s" % check["errors"][:5])
    csha = _dump_content(books, cfg, check)
    builds = os.path.join(paths["dumps"], V.pct_dirname(args.percentage))
    reuse = V.find_reusable_version(builds, None, csha)
    if reuse:
        _emit("REUSED dumps/%s/%s — identical export. No new version."
              % (V.pct_dirname(args.percentage), reuse))
        return 0

    written = DP.write_dump(args.data_root, args.percentage, dataset_manifest, pages)
    _emit("=== EXPORT DUMP (adapter for ai-dump-builder) ===")
    _emit("dataset        : %s" % args.dataset)
    _emit("version        : %s" % written["version"])
    _emit("books          : %d" % written["check"]["books"])
    _emit("records        : %d (skipped_short=%d, truncated=%d)"
          % (written["check"]["records_extracted"],
             written["check"]["skipped_short_lt_min_text_chars"],
             written["check"]["truncated_at_max_embed_chars"]))
    _emit("required fields: %s" % ("OK" if written["check"]["required_fields_ok"] else "FAIL"))
    for w in written["check"]["warnings"][:5]:
        _emit("  WARN: %s" % w)
    _emit("content sha256 : %s" % written["content_sha256"])
    _emit("out dir        : %s" % written["dir"])
    _emit("NOTE: embedding/Neo4j OUT OF SCOPE در این فاز (مأموریت بعدی).")
    _emit("DONE.")
    return 0


# --------------------------------------------------------------------------- diff
def cmd_diff(args) -> int:
    try:
        written = DFF.write_change_manifest(args.data_root, args.from_version, args.to_version)
    except ValueError as e:
        return _fail(str(e), 2)
    ch = written["change"]
    _emit("=== DIFF %s -> %s ===" % (args.from_version, args.to_version))
    for k, v in ch["counts"].items():
        _emit("  %-22s %s" % (k, v))
    _emit("change manifest: %s" % written["path"])
    _emit("sha256         : %s" % written["sha256"])
    _emit("DONE.")
    return 0


# --------------------------------------------------------------------------- semantic-diff (PCM-20.5 GATE 1)
def cmd_semantic_diff(args) -> int:
    try:
        written = SEM.write_semantic_change_manifest(args.data_root,
                                                     args.from_version, args.to_version)
    except ValueError as e:
        return _fail(str(e), 2)
    ch = written["diff"]
    _emit("=== SEMANTIC DIFF %s -> %s ===" % (args.from_version, args.to_version))
    for k, v in ch["counts"].items():
        _emit("  %-24s %s" % (k, v))
    for key in ("added_pages", "missing_pages", "recovered", "changed"):
        if ch.get(key + "_truncated"):
            _emit("  (list %s truncated to %d rows)" % (key, SEM._MAX_LIST))
    _emit("semantic change: %s" % written["path"])
    _emit("sha256         : %s" % written["sha256"])
    _emit("DONE.")
    return 0


# --------------------------------------------------------------------------- parser
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m corpus.tasnim.cli",
        description="خط تولید پیکره‌ی تسنیم (PCM-20.3) — فقط‌خواندن روی ورودی، خروجی زیر data/tasnim.")
    sub = p.add_subparsers(dest="cmd")

    sp = sub.add_parser("audit", help="درگاه آشتیابی (read-only)")
    sp.add_argument("--jsonl", required=True, help="tasnim-corpus.jsonl")
    sp.add_argument("--json", default=None, help="(اختیاری) tasnim-corpus.json")
    sp.add_argument("--summary", default=None, help="(اختیاری) export-summary.json")
    sp.add_argument("--data-root", default=None, help="برای مسیر پیش‌فرض خروجی audit")
    sp.add_argument("--out", default=None, help="مسیر خروجی audit JSON")
    sp.set_defaults(func=cmd_audit)

    sp = sub.add_parser("build-corpus", help="ساخت پیکره‌ی رسمی (نسخه‌ای)")
    sp.add_argument("--jsonl", required=True, help="tasnim-corpus.jsonl")
    sp.add_argument("--json", default=None, help="(اختیاری) tasnim-corpus.json")
    sp.add_argument("--summary", default=None, help="(اختیاری) export-summary.json")
    sp.add_argument("--data-root", default="data/tasnim")
    sp.add_argument("--policy", default=N.POLICY_DEFAULT,
                    choices=sorted(N.POLICIES), help="سیاست نرمال‌سازی")
    sp.set_defaults(func=cmd_build_corpus)

    sp = sub.add_parser("validate-corpus", help="اعتبارسنجی یک build")
    sp.add_argument("--data-root", default="data/tasnim")
    sp.add_argument("--build", required=True, help="vNNNN یا مسیر build")
    sp.set_defaults(func=cmd_validate_corpus)

    sp = sub.add_parser("build-dataset", help="ساخت دیتاست pct٪")
    sp.add_argument("--data-root", default="data/tasnim")
    sp.add_argument("--corpus", required=True, help="نسخه‌ی پیکره (vNNNN)")
    sp.add_argument("--percentage", type=int, required=True, choices=list(V.DATASET_PCTS))
    sp.add_argument("--volume", type=int, default=None, help="فقط یک جلد (number)")
    sp.add_argument("--volume-id", default=None,
                    help="فقط یک جلد به‌صورت volume_id (برای جلد بی‌شماره؛ PCM-20.7C) — "
                         "تعارض با --volume")
    sp.add_argument("--blocks", type=int, default=D.DEFAULT_BLOCKS,
                    help="تعداد بلوک‌های انتخاب درون هر جلد (پیش‌فرض 5)")
    sp.set_defaults(func=cmd_build_dataset)

    sp = sub.add_parser("export-dump", help="خروجی سازگار با ai-dump-builder")
    sp.add_argument("--data-root", default="data/tasnim")
    sp.add_argument("--dataset", default=None, help="نسخه‌ی دیتاست (vNNNN)")
    sp.add_argument("--percentage", type=int, required=True, choices=list(V.DATASET_PCTS))
    sp.set_defaults(func=cmd_export_dump)

    sp = sub.add_parser("diff", help="Change Manifest بین دو نسخه")
    sp.add_argument("--data-root", default="data/tasnim")
    sp.add_argument("--from", dest="from_version", required=True, help="vNNNN قبلی")
    sp.add_argument("--to", dest="to_version", required=True, help="vNNNN جدید")
    sp.set_defaults(func=cmd_diff)

    sp = sub.add_parser("build-semantic",
                        help="لایه‌ی معنایی روی یک build (PCM-20.5 GATE 1; cs-20.6 = v0003)")
    sp.add_argument("--data-root", default="data/tasnim")
    sp.add_argument("--base", required=True,
                    help="نسخه‌ی base (vNNNN؛ برای cs-20.6: build معنایی cs-20.5)")
    sp.add_argument("--contract", default=SEM.SEMANTIC_SCHEMA_VERSION,
                    choices=list(SEM.CONTRACTS),
                    help="قرارداد معنایی (پیش‌فرض cs-20.5؛ cs-20.6 = Semantic v0003 "
                         "hidden-context، نیاز به base معنایی cs-20.5)")
    sp.set_defaults(func=cmd_build_semantic)

    sp = sub.add_parser("semantic-diff", help="semantic-diff 7 دسته‌ای بین دو build")
    sp.add_argument("--data-root", default="data/tasnim")
    sp.add_argument("--from", dest="from_version", required=True, help="vNNNN قبلی")
    sp.add_argument("--to", dest="to_version", required=True, help="vNNNN جدید")
    sp.set_defaults(func=cmd_semantic_diff)

    sp = sub.add_parser("build-enriched",
                        help="cs-20.7: retrieval-context عنوان‌ها "
                             "(PCM-20.7C؛ base cs-20.6 + checkpoint)")
    sp.add_argument("--data-root", default="data/tasnim")
    sp.add_argument("--base", required=True,
                    help="نسخه‌ی base cs-20.6 (vNNNN؛ Semantic v0003)")
    sp.add_argument("--summaries", required=True,
                    help="checkpoint JSONL خلاصه‌ها (generate_summaries)")
    sp.set_defaults(func=cmd_build_enriched)
    return p


def main(argv=None) -> int:
    C.force_utf8_stdio()
    p = build_parser()
    try:
        args = p.parse_args(argv)
    except SystemExit as e:  # argparse: خطای ورودی (2) یا --help (0)
        return int(e.code) if isinstance(e.code, int) else 2
    if not getattr(args, "func", None):
        p.print_help()
        return 2
    try:
        return args.func(args)
    except FileNotFoundError as e:
        return _fail("file not found: %s" % e, 2)
    except Exception as e:
        _fail("%s: %s" % (type(e).__name__, e))
        return 1


if __name__ == "__main__":
    sys.exit(main())

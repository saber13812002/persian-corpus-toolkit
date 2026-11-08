# -*- coding: utf-8 -*-
"""tasnim.enrich — قرارداد cs-20.7: retrieval-contextِ عنوان‌ها (PCM-20.7C Phase C).

افزوده‌ی افزایشی روی cs-20.6 (Semantic v0003) — هیچ فیلد/فایلِ موجود حذف یا
تغییر نمی‌کند:

  * رکوردهای heading از v1 به v2 ارتقا می‌یابند (همان فیلدها + ۷ فیلد جدید):
      next_page_item_index        item_index صفحه‌ی بعد (None اگر صفحه‌ی بعد نیست)
      retrieval_context           رشته‌ی قطعی: عنوان + جلد + summary (اگر هست)
      retrieval_context_summary   خلاصه‌ی ≤۳ خطِ متن واقعی صفحه‌ی بعد (یا None)
      summary_status              ok | skipped_volume_end | skipped_no_next |
                                  skipped_next_blank | skipped_next_too_short | failed
      summary_meta                {method, model, model_version, prompt_version,
                                   temperature, max_tokens, max_lines}
      summary_sha256              SHA-256 متن summary (None اگر summary نیست)
      retrieval_context_sha256    SHA-256 رشته‌ی retrieval_context
  * summary فقط از checkpoint JSONL (خروجی generate_summaries، ساخته‌شده روی
    متن واقعی صفحه‌ی بعد) گرفته می‌شود؛ هیچ تفسیر/ابداع داخل builder نیست.
  * headingهای غیرواجدشرط (آخر جلد / صفحه‌ی بعد خالی / زیر ۱۰۰ کاراکتر /
    گم‌شده) summary نمی‌گیرند — status مشخص و summary=null (بدون ابداع).
  * pages.jsonl و context-records.jsonl و hidden-context-records.jsonl
    byte-identical با base می‌مانند؛ تنها فایل تغییریافته heading-records.jsonl
    است (+ بلوک‌های semantic/enrichment در corpus.json).
  * summary در payload عمومی (corpus.json / رکورد صفحه‌ی عنوان در pages.jsonl)
    قرار نمی‌گیرد — validate_enriched (S11) آن را با آزمون leakage کنترل می‌کند.

build قطعی است: با base + checkpoint یکسان، خروجی byte-identical است.
"""
from __future__ import annotations

import copy
import os
import time

from . import common as C
from . import manifest as M
from . import schema as S
from . import transform as T


ENRICH_SCHEMA_VERSION = "cs-20.7"
PREV_CONTRACT = "cs-20.6"       # base باید Semantic v0003 (cs-20.6) باشد
BASE_PREV_CONTRACT = "cs-20.5"  # و base خودش prev_contract = cs-20.5 داشته باشد
MISSION = "PCM-20.7C PHASE C"
SUMMARY_METHOD = "llm-summary/1.0"
PROMPT_VERSION = "hc-prompt/1.0"
MIN_NEXT_PAGE_CHARS = 100
MAX_SUMMARY_LINES = 3

STATUS_OK = "ok"
STATUS_VOLUME_END = "skipped_volume_end"
STATUS_NO_NEXT = "skipped_no_next"
STATUS_NEXT_BLANK = "skipped_next_blank"
STATUS_NEXT_SHORT = "skipped_next_too_short"
STATUS_FAILED = "failed"
STATUSES = (STATUS_OK, STATUS_VOLUME_END, STATUS_NO_NEXT, STATUS_NEXT_BLANK,
            STATUS_NEXT_SHORT, STATUS_FAILED)
SKIP_STATUSES = (STATUS_VOLUME_END, STATUS_NO_NEXT, STATUS_NEXT_BLANK,
                 STATUS_NEXT_SHORT)

NEW_FIELDS = ("next_page_item_index", "retrieval_context",
              "retrieval_context_summary", "summary_status", "summary_meta",
              "summary_sha256", "retrieval_context_sha256")

# فایل‌هایی که در build cs-20.7 byte-identical با base می‌مانند
UNTOUCHED_FILES = ("pages.jsonl", "context-records.jsonl", S.HC_FILE_CONTEXT)


# --------------------------------------------------------------------------- normalization
def normalize_summary(text):
    """خلاصه را canonical می‌کند: ۱ تا ۳ خط غیرخالی (با strip)؛ وگرنه None."""
    if not isinstance(text, str):
        return None
    lines = [ln.strip() for ln in text.splitlines()]
    lines = [ln for ln in lines if ln]
    if not lines or len(lines) > MAX_SUMMARY_LINES:
        return None
    return "\n".join(lines)


# --------------------------------------------------------------------------- eligibility
def eligibility_of(heading, by_pid):
    """صلاحیتِ گرفتن summary برای یک رکورد heading.

    heading: رکورد v1/v2 از heading-records.jsonl (next_page_id + volume_id).
    by_pid:  {page_id: page} از pages.jsonl.
    برگشت: (status, next_page|None)
    """
    npi = heading.get("next_page_id")
    if not npi:
        return STATUS_VOLUME_END, None   # آخر جلد (صفحه‌ی بعد در همان جلد نیست)
    np_ = by_pid.get(npi)
    if np_ is None:
        return STATUS_NO_NEXT, None      # دفاعی: صفحه‌ی بعد گم (نباید پیش بیاید)
    if (np_.get("volume") or {}).get("volume_id") != heading.get("volume_id"):
        return STATUS_VOLUME_END, np_    # دفاعی: S02 تضمین می‌کند پیش نیاید
    text = (np_.get("text") or "").strip()
    if not text:
        return STATUS_NEXT_BLANK, np_
    if len(text) < MIN_NEXT_PAGE_CHARS:
        return STATUS_NEXT_SHORT, np_
    return STATUS_OK, np_


def retrieval_context_of(heading, summary):
    """رشته‌ی قطعی retrieval_context: عنوان + جلد + summary (فقط اگر موجود)."""
    parts = [x for x in (heading.get("heading_text"), heading.get("volume_title"),
                         summary) if x]
    return " — ".join(parts)


def summary_meta_of(entry):
    return {
        "method": SUMMARY_METHOD,
        "model": entry.get("model"),
        "model_version": entry.get("model_version"),
        "prompt_version": entry.get("prompt_version") or PROMPT_VERSION,
        "temperature": entry.get("temperature"),
        "max_tokens": entry.get("max_tokens"),
        "max_lines": MAX_SUMMARY_LINES,
    }


def enriched_heading_record(base_rec, status, summary, meta, next_page):
    """رکورد heading v2 = همه‌ی فیلدهای v1 + فیلدهای جدید + heading_hash دوباره."""
    rec = dict(base_rec)
    rec["next_page_item_index"] = next_page.get("item_index") if next_page else None
    rec["retrieval_context"] = retrieval_context_of(rec, summary)
    rec["retrieval_context_summary"] = summary
    rec["summary_status"] = status
    rec["summary_meta"] = meta
    rec["summary_sha256"] = C.sha256_text(summary) if summary else None
    rec["retrieval_context_sha256"] = C.sha256_text(rec["retrieval_context"])
    rec["heading_hash"] = C.sha256_text(
        C.canonical_json({k: v for k, v in rec.items() if k != "heading_hash"}).decode("utf-8"))
    return rec


# --------------------------------------------------------------------------- checkpoint
def load_checkpoint(path):
    """checkpoint JSONL → {record_id: entry}. رکوردهای بدون record_id رد می‌شوند."""
    out = {}
    for line in C.read_jsonl(path):
        rid = line.get("record_id")
        if rid:
            out[rid] = line
    return out


def generate_summaries(base_dir, out_path, chat_fn, only_record_ids=None,
                       limit=None, resume=True, pace_seconds=1.0):
    """تولید checkpoint خلاصه‌ها برای headingهای واجدشرط از base cs-20.6.

    chat_fn(heading_rec, next_page) → dict با کلید "summary" (و model/
    model_version/prompt_version/temperature/max_tokens) یا None؛ خطا = failed.
    خلاصه‌ی ناکاننیکال (نه ۱..۳ خط) → failed و در checkpoint نوشته نمی‌شود
    (در اجرای بعدی دوباره تلاش می‌شود). pace: حداکثر ~۱ درخواست در ثانیه.
    """
    pages = C.read_jsonl(os.path.join(base_dir, "pages.jsonl"))
    by_pid = {p.get("page_id"): p for p in pages}
    headings = C.read_jsonl(os.path.join(base_dir, S.HC_FILE_HEADING))
    done = load_checkpoint(out_path) if (resume and os.path.exists(out_path)) else {}
    only = set(only_record_ids or ())

    stats = {"eligible": 0, "generated": 0, "resumed": 0, "failed": 0,
             "skipped": 0, "filtered": 0}
    count = 0
    mode = "ab" if resume else "wb"
    with open(out_path, mode) as f:
        for h in headings:
            status, np_ = eligibility_of(h, by_pid)
            if status != STATUS_OK:
                stats["skipped"] += 1
                continue
            stats["eligible"] += 1
            rid = h.get("record_id")
            if (only and rid not in only) or (limit is not None and count >= limit):
                stats["filtered"] += 1
                continue
            if rid in done:
                stats["resumed"] += 1
                continue
            t0 = time.time()
            try:
                res = chat_fn(h, np_)
            except Exception:
                res = None
            if not isinstance(res, dict):
                res = None
            summary = normalize_summary((res or {}).get("summary"))
            if summary is None:
                stats["failed"] += 1
                continue
            entry = {
                "record_id": rid,
                "page_id": h.get("page_id"),
                "item_index": h.get("item_index"),
                "volume_id": h.get("volume_id"),
                "volume_no": h.get("volume_no"),
                "heading_text": h.get("heading_text"),
                "next_page_id": h.get("next_page_id"),
                "summary": summary,
                "model": res.get("model"),
                "model_version": res.get("model_version"),
                "prompt_version": res.get("prompt_version") or PROMPT_VERSION,
                "temperature": res.get("temperature"),
                "max_tokens": res.get("max_tokens"),
                "generated_at": C.now_utc(),
            }
            f.write(C.canonical_json_line(entry))
            f.flush()
            done[rid] = entry
            stats["generated"] += 1
            count += 1
            if pace_seconds > 0:
                time.sleep(max(0.0, pace_seconds - (time.time() - t0)))
    return {"stats": stats, "checkpoint": done, "checkpoint_count": len(done),
            "out_path": out_path}


# --------------------------------------------------------------------------- build (two-stage)
def _base_check(ab):
    corpus = C.read_json(os.path.join(ab, "corpus.json"))
    sem = corpus.get("semantic") or {}
    if sem.get("schema_version") != PREV_CONTRACT:
        raise ValueError("cs-20.7 requires a cs-20.6 (Semantic v0003) base; got %r"
                         % sem.get("schema_version"))
    if sem.get("prev_contract") != BASE_PREV_CONTRACT:
        raise ValueError("the cs-20.6 base must have prev_contract %r; got %r"
                         % (BASE_PREV_CONTRACT, sem.get("prev_contract")))
    base_manifest = M.load_manifest(ab)
    if not (base_manifest.get("data") or {}).get("content_sha256"):
        raise ValueError("base manifest lacks data.content_sha256")
    return corpus, sem, base_manifest


def _consensus(entries, key):
    vals = {e.get(key) for e in entries}
    vals.discard(None)
    return vals.pop() if len(vals) == 1 else None


def enriched_content(base_dir, summaries_path):
    """آماده‌سازی کامل محتوای build cs-20.7 در حافظه (بدون نوشتن روی دیسک).

    برگشت: {corpus, pages, headings, files, content_sha256, status_counts,
             enrichment, summaries_source, base_manifest, base_rel, base_dir}
    """
    ab = os.path.abspath(base_dir)
    parent = os.path.dirname(ab)
    if os.path.basename(parent) != "builds":
        raise ValueError("base_dir must be <data_root>/corpus/builds/vNNNN: %s" % base_dir)
    base_rel = "corpus/builds/%s" % os.path.basename(ab)
    if not os.path.exists(summaries_path):
        raise ValueError("summaries checkpoint not found: %s" % summaries_path)

    corpus, sem, base_manifest = _base_check(ab)
    pages = C.read_jsonl(os.path.join(ab, "pages.jsonl"))
    headings = C.read_jsonl(os.path.join(ab, S.HC_FILE_HEADING))
    by_pid = {p.get("page_id"): p for p in pages}
    entries = load_checkpoint(summaries_path)
    for e in entries.values():
        for k in ("record_id", "summary"):
            if k not in e:
                raise ValueError("checkpoint entry lacks %r (record_id=%r)"
                                 % (k, e.get("record_id")))
    known = {h.get("record_id") for h in headings}
    extra = sorted(set(entries) - known, key=str)
    if extra:
        raise ValueError("checkpoint has %d record_id(s) not in base heading records: %s"
                         % (len(extra), extra[:5]))

    bdata = base_manifest.get("data") or {}
    bfiles = bdata.get("files") or {}
    ok_entries = []
    census = {s: 0 for s in STATUSES}
    new_headings = []
    for h in headings:
        status, np_ = eligibility_of(h, by_pid)
        rid = h.get("record_id")
        entry = entries.get(rid)
        summary = meta = None
        if status == STATUS_OK:
            if entry is None:
                status = STATUS_FAILED   # واجدشرط اما بدون summary معتبر
            else:
                summary = normalize_summary(entry.get("summary"))
                if summary is None:
                    raise ValueError("invalid summary in checkpoint (need 1..3 "
                                     "non-empty lines): record_id=%s" % rid)
                meta = summary_meta_of(entry)
                ok_entries.append(entry)
        elif entry is not None:
            raise ValueError("summary provided for ineligible heading (status=%s): "
                             "record_id=%s" % (status, rid))
        census[status] += 1
        new_headings.append(enriched_heading_record(h, status, summary, meta, np_))

    # --- corpus.semantic: cs-20.7 (بلوک‌های cs-20.6 دست‌نخورده)
    corpus2 = copy.deepcopy(corpus)
    sem7 = corpus2["semantic"]
    sem7["schema_version"] = ENRICH_SCHEMA_VERSION
    sem7["mission"] = MISSION
    sem7["prev_contract"] = PREV_CONTRACT
    sem7["base_corpus"] = {
        "version": base_manifest.get("version"),
        "content_sha256": bdata.get("content_sha256"),
        "kind": "corpus",
        "path_rel": base_rel,
    }
    summaries_source = {
        "file": os.path.basename(os.path.abspath(summaries_path)),
        "sha256": C.sha256_file(summaries_path),
        "count": len(entries),
    }
    sem7["enrichment"] = {
        "method": SUMMARY_METHOD,
        "prompt_version": PROMPT_VERSION,
        "min_next_page_chars": MIN_NEXT_PAGE_CHARS,
        "max_summary_lines": MAX_SUMMARY_LINES,
        "model": _consensus(ok_entries, "model"),
        "model_version": _consensus(ok_entries, "model_version"),
        "temperature": _consensus(ok_entries, "temperature"),
        "max_tokens": _consensus(ok_entries, "max_tokens"),
        "status_counts": dict(census),
        "summaries_source": summaries_source,
    }
    hr7 = (sem7.get("hidden_context") or {}).get("heading_records") or {}
    hr7["record_version"] = "v2"
    stats_sem = corpus2.setdefault("stats", {}).setdefault("semantic", {})
    stats_sem.setdefault("hidden_context", {})["enrichment"] = {
        "summary_ok_count": census[STATUS_OK],
        "summary_failed_count": census[STATUS_FAILED],
        "summary_skipped_count": sum(census[s] for s in SKIP_STATUSES),
        "status_counts": dict(census),
    }

    # --- files: ۳ فایل دست‌نخورده (meta از manifest base) + ۲ فایل تولیدی
    files = {}
    for name in UNTOUCHED_FILES:
        meta = bfiles.get(name)
        if meta is None:
            raise ValueError("base manifest lacks file meta: %s" % name)
        files[name] = dict(meta)
    hb = b"".join(C.canonical_json_line(r) for r in new_headings)
    files[S.HC_FILE_HEADING] = {"sha256": C.sha256_bytes(hb), "size_bytes": len(hb)}
    cb = C.canonical_json(corpus2)
    files["corpus.json"] = {"sha256": C.sha256_bytes(cb), "size_bytes": len(cb)}

    return {
        "corpus": corpus2,
        "pages": pages,
        "headings": new_headings,
        "files": files,
        "content_sha256": T.content_sha256_of_files(files),
        "status_counts": dict(census),
        "enrichment": sem7["enrichment"],
        "summaries_source": summaries_source,
        "base_manifest": base_manifest,
        "base_rel": base_rel,
        "base_dir": ab,
    }


def write_enriched(out_dir, prepared):
    """نوشتن build cs-20.7 + بازتأیید SHA همه‌ی ۵ فایل پس از نوشتن."""
    ab = prepared["base_dir"]
    os.makedirs(out_dir, exist_ok=True)
    for name in UNTOUCHED_FILES:
        src = os.path.join(ab, name)
        if C.sha256_file(src) != prepared["files"][name]["sha256"]:
            raise RuntimeError("base file differs from base manifest: %s" % name)
        with open(src, "rb") as f:
            data = f.read()
        C.write_bytes(os.path.join(out_dir, name), data)
        if C.sha256_file(os.path.join(out_dir, name)) != prepared["files"][name]["sha256"]:
            raise RuntimeError("byte-copy verification failed: %s" % name)
    C.write_bytes(os.path.join(out_dir, S.HC_FILE_HEADING),
                  b"".join(C.canonical_json_line(r) for r in prepared["headings"]))
    C.write_json(os.path.join(out_dir, "corpus.json"), prepared["corpus"])
    for name in (S.HC_FILE_HEADING, "corpus.json"):
        if C.sha256_file(os.path.join(out_dir, name)) != prepared["files"][name]["sha256"]:
            raise RuntimeError("write verification failed: %s" % name)
    return {
        "files": {k: dict(v) for k, v in prepared["files"].items()},
        "content_sha256": prepared["content_sha256"],
        "paths": {name: os.path.join(out_dir, name) for name in prepared["files"]},
        "build_dir": out_dir,
    }


# --------------------------------------------------------------------------- validation (S11)
def validate_enriched(out_dir, base_dir):
    """اعتبارسنجی build cs-20.7 روی base cs-20.6 (بخش S11 از validate_semantic).

    برگشت (ok, errors, warnings). پیام‌ها پیشوند ندارند؛ صداکننده (S11)
    پیشوند «S11: » اضافه می‌کند.
    """
    errors, warnings = [], []
    try:
        corpus = C.read_json(os.path.join(out_dir, "corpus.json"))
        pages = C.read_jsonl(os.path.join(out_dir, "pages.jsonl"))
        headings = C.read_jsonl(os.path.join(out_dir, S.HC_FILE_HEADING))
        manifest = M.load_manifest(out_dir)
        b_corpus = C.read_json(os.path.join(base_dir, "corpus.json"))
        b_headings = C.read_jsonl(os.path.join(base_dir, S.HC_FILE_HEADING))
        b_manifest = M.load_manifest(base_dir)
    except Exception as e:
        return False, ["build unreadable: %s" % e], []
    sem = corpus.get("semantic") or {}
    b_sem = b_corpus.get("semantic") or {}
    mdata = manifest.get("data") or {}
    bdata = b_manifest.get("data") or {}

    if sem.get("schema_version") != ENRICH_SCHEMA_VERSION:
        errors.append("schema_version must be %r: got %r"
                      % (ENRICH_SCHEMA_VERSION, sem.get("schema_version")))
    if sem.get("prev_contract") != PREV_CONTRACT:
        errors.append("prev_contract must be %r: got %r"
                      % (PREV_CONTRACT, sem.get("prev_contract")))
    base_corpus = sem.get("base_corpus") or {}
    if base_corpus.get("content_sha256") != bdata.get("content_sha256"):
        errors.append("base_corpus.content_sha256 != base manifest content_sha256")
    prev = manifest.get("prev") or {}
    exp_prev_sha = C.sha256_text(C.canonical_json(b_manifest).decode("utf-8"))
    if (prev.get("version") != b_manifest.get("version")
            or prev.get("sha256") != exp_prev_sha):
        errors.append("manifest.prev does not chain to the cs-20.6 base")

    # ۳ فایل عمومی: byte-identity با base
    for name in UNTOUCHED_FILES:
        if (C.sha256_file(os.path.join(out_dir, name))
                != C.sha256_file(os.path.join(base_dir, name))):
            errors.append("public file differs from base (sha): %s" % name)

    # manifest data.files vs دیسک
    for name, meta in (mdata.get("files") or {}).items():
        p = os.path.join(out_dir, name)
        if not os.path.exists(p) or C.sha256_file(p) != meta.get("sha256"):
            errors.append("manifest file sha mismatch: %s" % name)

    by_pid = {p.get("page_id"): p for p in pages}
    if [r.get("record_id") for r in headings] != [r.get("record_id") for r in b_headings]:
        errors.append("heading record order/ids differ from base")
    b_by_rid = {r.get("record_id"): r for r in b_headings}

    census = {s: 0 for s in STATUSES}
    leak_samples = []   # (summary, rid, heading_page_jsonl_line_bytes)
    for r in headings:
        rid = r.get("record_id")
        b = b_by_rid.get(rid)
        if b is None:
            errors.append("heading record not in base: %s" % rid)
            continue
        for f, v in b.items():
            if f == "heading_hash":
                continue  # در v2 روی fieldset بزرگ‌تر دوباره حساب می‌شود (قطعی)
            if r.get(f) != v:
                errors.append("base field changed: %s (record_id=%s)" % (f, rid))
                break
        for f in NEW_FIELDS:
            if f not in r:
                errors.append("new field missing: %s (record_id=%s)" % (f, rid))
        status = r.get("summary_status")
        if status not in STATUSES:
            errors.append("unknown summary_status %r (record_id=%s)" % (status, rid))
            continue
        census[status] = census.get(status, 0) + 1
        exp_status, _ = eligibility_of(r, by_pid)
        s = r.get("retrieval_context_summary")
        if status == STATUS_OK:
            if not s or normalize_summary(s) != s:
                errors.append("ok summary not canonical 1..3 non-empty lines: %s" % rid)
            if r.get("summary_sha256") != (C.sha256_text(s) if s else None):
                errors.append("summary_sha256 mismatch: %s" % rid)
            meta = r.get("summary_meta") or {}
            if meta.get("method") != SUMMARY_METHOD:
                errors.append("summary_meta.method must be %s: %s" % (SUMMARY_METHOD, rid))
            if meta.get("max_lines") != MAX_SUMMARY_LINES:
                errors.append("summary_meta.max_lines must be %d: %s"
                              % (MAX_SUMMARY_LINES, rid))
            if exp_status != STATUS_OK:
                errors.append("ok status but eligibility is %s: %s" % (exp_status, rid))
            hp_ = by_pid.get(r.get("page_id"))
            if hp_ is not None:
                leak_samples.append((s, rid, C.canonical_json_line(hp_)))
        elif status == STATUS_FAILED:
            if exp_status != STATUS_OK:
                errors.append("failed status but eligibility is %s: %s"
                              % (exp_status, rid))
        else:  # skipped_*
            if (s is not None or r.get("summary_meta") is not None
                    or r.get("summary_sha256") is not None):
                errors.append("skipped record must have null summary/meta/sha: %s" % rid)
            if exp_status != status:
                errors.append("skipped status %r != recomputed %r: %s"
                              % (status, exp_status, rid))
        npi = r.get("next_page_id")
        npg = by_pid.get(npi) if npi else None
        if r.get("next_page_item_index") != (npg.get("item_index") if npg else None):
            errors.append("next_page_item_index mismatch: %s" % rid)
        if r.get("retrieval_context") != retrieval_context_of(r, s):
            errors.append("retrieval_context != recomputed: %s" % rid)
        if r.get("retrieval_context_sha256") != C.sha256_text(r.get("retrieval_context") or ""):
            errors.append("retrieval_context_sha256 mismatch: %s" % rid)
        meta2 = {k: v for k, v in r.items() if k != "heading_hash"}
        if r.get("heading_hash") != C.sha256_text(C.canonical_json(meta2).decode("utf-8")):
            errors.append("heading_hash mismatch: %s" % rid)

    # --- بلوک enrichment + سرشماری
    enr = sem.get("enrichment") or {}
    for key in ("method", "prompt_version", "min_next_page_chars", "max_summary_lines",
                "status_counts", "summaries_source"):
        if key not in enr:
            errors.append("enrichment.%s missing" % key)
    if enr.get("method") != SUMMARY_METHOD:
        errors.append("enrichment.method must be %s" % SUMMARY_METHOD)
    if enr.get("prompt_version") != PROMPT_VERSION:
        errors.append("enrichment.prompt_version must be %s" % PROMPT_VERSION)
    if enr.get("min_next_page_chars") != MIN_NEXT_PAGE_CHARS:
        errors.append("enrichment.min_next_page_chars mismatch")
    if enr.get("max_summary_lines") != MAX_SUMMARY_LINES:
        errors.append("enrichment.max_summary_lines mismatch")
    if enr.get("status_counts") != census:
        errors.append("enrichment.status_counts != recomputed census")
    ss = enr.get("summaries_source") or {}
    if not (isinstance(ss.get("sha256"), str) and len(ss.get("sha256")) == 64):
        errors.append("enrichment.summaries_source.sha256 missing/invalid")
    if not isinstance(ss.get("count"), int):
        errors.append("enrichment.summaries_source.count missing/invalid")

    # --- stats: بخش‌های دست‌نخورده + enrichment
    st7 = (corpus.get("stats") or {}).get("semantic") or {}
    stb = (b_corpus.get("stats") or {}).get("semantic") or {}
    for key in ("class_counts", "basis_counts", "context_record_count"):
        if st7.get(key) != stb.get(key):
            errors.append("stats.semantic.%s differs from base" % key)
    h7 = st7.get("hidden_context") or {}
    hb = stb.get("hidden_context") or {}
    for key in ("heading_record_count", "context_record_count",
                "truncated_at_source_count"):
        if h7.get(key) != hb.get(key):
            errors.append("stats.semantic.hidden_context.%s differs from base" % key)
    en7 = h7.get("enrichment") or {}
    if en7.get("status_counts") != census:
        errors.append("stats enrichment.status_counts mismatch")
    if en7.get("summary_ok_count") != census.get(STATUS_OK, 0):
        errors.append("stats summary_ok_count mismatch")
    if en7.get("summary_failed_count") != census.get(STATUS_FAILED, 0):
        errors.append("stats summary_failed_count mismatch")
    if en7.get("summary_skipped_count") != sum(census.get(s, 0) for s in SKIP_STATUSES):
        errors.append("stats summary_skipped_count mismatch")

    # --- بلوک‌های semantic دست‌نخورده (cs-20.6)
    for key in ("classification", "order_key", "truncation", "context_records"):
        if sem.get(key) != b_sem.get(key):
            errors.append("semantic.%s differs from cs-20.6 base" % key)
    hc7 = sem.get("hidden_context") or {}
    bhc = b_sem.get("hidden_context") or {}
    for key in ("policy", "visibility", "relations", "context_records"):
        if hc7.get(key) != bhc.get(key):
            errors.append("hidden_context.%s differs from base" % key)
    hr7 = hc7.get("heading_records") or {}
    bhr = bhc.get("heading_records") or {}
    for key in ("count", "file", "record_id_prefix"):
        if hr7.get(key) != bhr.get(key):
            errors.append("hidden_context.heading_records.%s differs from base" % key)

    # --- آزمون leakage: summary نباید در payload عمومی باشد
    if leak_samples:
        try:
            with open(os.path.join(out_dir, "corpus.json"), "rb") as f:
                pub_corpus = f.read()
        except Exception:
            pub_corpus = b""
        try:
            with open(os.path.join(out_dir, "pages.jsonl"), "rb") as f:
                semi_pages = f.read()
            with open(os.path.join(out_dir, "context-records.jsonl"), "rb") as f:
                semi_ctx = f.read()
            with open(os.path.join(out_dir, S.HC_FILE_CONTEXT), "rb") as f:
                semi_hidden = f.read()
        except Exception:
            semi_pages = semi_ctx = semi_hidden = b""
        for s, rid, hline in leak_samples[:50]:
            blob = (s or "").encode("utf-8")
            if not blob:
                continue
            if blob in pub_corpus:
                errors.append("LEAK — summary present in public corpus.json: %s" % rid)
            if hline is not None and blob in hline:
                errors.append("LEAK — summary embedded in the heading page's "
                              "public record: %s" % rid)
            if blob in semi_pages:
                warnings.append("summary text appears verbatim in pages.jsonl "
                                "(verbatim collision with next-page text): %s" % rid)
            if blob in semi_ctx or blob in semi_hidden:
                warnings.append("summary text appears in hidden-tier records "
                                "(verbatim collision with cs-20.5 extract): %s" % rid)

    return (not errors), errors, warnings

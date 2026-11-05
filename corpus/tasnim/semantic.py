# -*- coding: utf-8 -*-
"""tasnim.semantic — PCM-20.5 GATE 1: لایه‌ی معنایی روی پیکره‌ی رسمی.

این ماژول یک نسخه‌ی معنایی (semantic) از یک build پیکره‌ی موجود (base) می‌سازد:

  * مرجع ترتیب قطعی: item_index (به‌علاوه‌ی جلد و dup_rank و موقعیت منبع) —
    بدون حدس شماره‌ی صفحه؛ هر صفحه یک بلوک `semantic.order` می‌گیرد.
  * طبقه‌بندی 6گانه‌ی رکوردهای کوتاه:
    CONTENT_PAGE / CHAPTER_HEADING / SECTION_HEADING / SHORT_CONTENT /
    EMPTY_PAGE / UNKNOWN_STRUCTURE — با علامت‌گذاری مبنای طبقه‌بندی:
    definitive (اندازه‌گیری‌شده: خالی/بدون‌حرف/len>=20) یا guessed
    (الگو/واژگان: عنوان سوره، شماره‌گذاری، کلمات کلیدی بخش).
  * رکوردهای Contextual پنهان (hidden) برای صفحات عنوان: متن عنوان +
    خلاصه‌ی verbatim استخراجی از صفحه‌ی بعد (حداکثر 3 خط، بدون LLM،
    model=null، روش "verbatim-extract/1.0") + متادیتای جلد + شناسه‌ها و
    هش منبع + context_hash. هیچ محتوایی ساختگی نیست.
  * دفترک شکاف‌ها (gaps ledger): شکاف item_index که منبع معتبر آفلاینی
    برای بازیابی ندارد (سایت زنده /payload دیگر JSON برنمی‌گرداند —
    شواهد PCM-20.5 GATE 0-D) → در manifest به‌عنوان unresolved ثبت می‌شود.
  * semantic-diff: 7 دسته (added/recovered/changed/unchanged/missing/
    duplicate/unresolved) + افزایش رکوردهای context — خروجی
    reports/diff_<from>_<to>/semantic-change.json (متفاوت از change-manifest).

قواعد قطعیت: هیچ فیلد وابسته‌به‌زمان در content نیست؛ base_rel مستقل از
ریشه‌ی data است (cross-root determinism)؛ class_counts همیشه هر 6 کلاس را
شامل می‌شود (حتی صفر)؛ ترتیب context = ترتیب فایل.

قواعد عدم‌تغییری: base دست‌نخورده می‌ماند؛ نسخه‌ی جدید فقط اضافه می‌شود.
"""
from __future__ import annotations

import copy
import os
import re
import unicodedata
from collections import Counter

from . import common as C
from . import manifest as M
from . import reconcile as R
from . import transform as T
from . import versioning as V


SEMANTIC_SCHEMA_VERSION = "cs-20.5"
RULE_SET = "semantic-rules/1.0"
SUMMARY_METHOD = "verbatim-extract/1.0"
MAX_SUMMARY_LINES = 3
VISIBILITY_HIDDEN = "hidden"

CLS_CONTENT = "CONTENT_PAGE"
CLS_CHAPTER = "CHAPTER_HEADING"
CLS_SECTION = "SECTION_HEADING"
CLS_SHORT = "SHORT_CONTENT"
CLS_EMPTY = "EMPTY_PAGE"
CLS_UNKNOWN = "UNKNOWN_STRUCTURE"
CLASSES = (CLS_CONTENT, CLS_CHAPTER, CLS_SECTION, CLS_SHORT, CLS_EMPTY, CLS_UNKNOWN)

BASIS_DEFINITIVE = "definitive"
BASIS_GUESSED = "guessed"
BASES = (BASIS_DEFINITIVE, BASIS_GUESSED)

ORDER_KEY = ["volume_no", "volume_id", "item_index", "dup_rank", "source_position"]

LETTER_RE = re.compile(r"[\u0600-\u06FF\u0750-\u077Fa-zA-Z]")
NUMBERED_RE = re.compile(r"^\s*\d+[\.\u066b\u060c,\u202f\u00a0 ]+\s*\S")
CHAPTER_RE = re.compile(r"^\s*سور[هي]")

# واژگان بخش‌های کوتاهِ تفسیر تسنیم (از ممیزی واژگان PCM-20.5 GATE 1).
# این فهرست مبنای guessed است — هر تطبیق در class_rule ثبت می‌شود.
SECTION_KEYWORDS = (
    "گزیده", "بحث روایی", "اشارات و لطایف", "لطایف و اشارات",
    "نام ها و اوصاف سوره", "نام های سوره", "نام و اوصاف سوره", "نام و وصف سوره",
    "نام سوره", "تطبیق", "مفردات", "تناسب", "غرر", "شبهه",
    "مراد از", "منظور از", "معنای", "مخاطب",
    "پیش گفتار", "پیشگفتار", "مقدمه", "فهرست", "فضیلت",
    "خطوط کلی", "هدف", "تفسیر", "نزول", "پاسخ",
)

_DUP_RANK_RE = re.compile(r"__d(\d+)$")
_MAX_LIST = 1000


def _dup_rank_of(page_id: str) -> int:
    m = _DUP_RANK_RE.search(page_id or "")
    return int(m.group(1)) if m else 0


def _volume_title(vol: dict) -> str:
    return (vol or {}).get("volume_title") or ""


# --------------------------------------------------------------------------- classification
def classify_page(text: str) -> tuple:
    """طبقه‌بندی یک متن صفحه.

    برگشت: (record_class, basis, rule).
    definite rules (اندازه‌گیری‌شده): خالی، بدون‌حرف، len>=20.
    guessed rules (الگو/واژگان): عنوان سوره، شماره‌گذاری، کلمه‌ی کلیدی.
    """
    if text is None:
        text = ""
    if text == "":
        return CLS_EMPTY, BASIS_DEFINITIVE, "empty: len==0"
    if not LETTER_RE.search(text):
        return CLS_UNKNOWN, BASIS_DEFINITIVE, "no-letters"
    if len(text) >= R.MIN_TEXT_CHARS:
        return CLS_CONTENT, BASIS_DEFINITIVE, "content: len>=20"
    nfkc = unicodedata.normalize("NFKC", text)
    if CHAPTER_RE.match(nfkc):
        return CLS_CHAPTER, BASIS_GUESSED, "chapter: sura-title-pattern"
    if NUMBERED_RE.match(C.to_ascii_digits(text)):
        return CLS_SECTION, BASIS_GUESSED, "section: numbered"
    for kw in SECTION_KEYWORDS:
        if kw in nfkc:
            return CLS_SECTION, BASIS_GUESSED, "section: keyword:%s" % kw
    return CLS_SHORT, BASIS_GUESSED, "short: default"


def extract_summary(text: str, max_lines: int = MAX_SUMMARY_LINES) -> tuple:
    """خلاصه‌ی verbatim استخراجی: حداکثر max_lines خط غیرخالیِ اول متن.

    برگشت: (summary|None, line_count). هیچ تفسیر/تولیدی در آن نیست.
    """
    lines = [ln.strip() for ln in (text or "").splitlines()]
    lines = [ln for ln in lines if ln]
    if not lines:
        return None, 0
    take = lines[:max_lines]
    return "\n".join(take), len(take)


# --------------------------------------------------------------------------- context records
def _make_context_record(p: dict, nxt: dict, cls: str, summary: str, n_lines: int) -> dict:
    """رکورد Contextual پنهان برای یک صفحه‌ی عنوان (بدون هیچ محتوای ساختگی)."""
    vt = _volume_title(p.get("volume"))
    rec = {
        "record_id": "ctx:%s" % p["page_id"],
        "visibility": VISIBILITY_HIDDEN,
        "record_kind": "context",
        "heading_page_id": p["page_id"],
        "context_page_id": p["page_id"],
        "context_item_index": p.get("item_index"),
        "heading_text": p.get("text") or "",
        "next_page_id": nxt["page_id"],
        "next_item_index": nxt.get("item_index"),
        "next_source_page_id": nxt.get("source_page_id"),
        "next_page_summary": summary,
        "summary_lines": n_lines,
        "retrieval_context": "%s — %s — %s" % (p.get("text") or "", vt, summary),
        "internal_tags": ["hidden", "heading-context", cls],
        "volume_id": (p.get("volume") or {}).get("volume_id"),
        "volume_title": vt,
        "source_hash": p.get("content_hash"),
        "summary_meta": {"method": SUMMARY_METHOD, "model": None,
                         "prompt_version": None, "max_lines": MAX_SUMMARY_LINES},
    }
    rec["context_hash"] = C.sha256_text(
        C.canonical_json({k: v for k, v in rec.items() if k != "context_hash"}).decode("utf-8"))
    return rec


# --------------------------------------------------------------------------- build
def build_semantic(base_dir: str) -> dict:
    """لایه‌ی معنایی را از فایل‌های build پیکره‌ی base می‌سازد (بدون تغییر base)."""
    ab = os.path.abspath(base_dir)
    parent = os.path.dirname(ab)
    if os.path.basename(parent) != "builds":
        raise ValueError("base_dir must be <data_root>/corpus/builds/vNNNN: %s" % base_dir)
    base_rel = "corpus/builds/%s" % os.path.basename(ab)

    corpus = C.read_json(os.path.join(ab, "corpus.json"))
    pages = C.read_jsonl(os.path.join(ab, "pages.jsonl"))
    base_manifest = M.load_manifest(ab)
    if "semantic" in corpus:
        raise ValueError("base corpus already has a semantic layer (not a valid base): %s"
                         % base_rel)
    bdata = base_manifest.get("data") or {}
    if not bdata.get("content_sha256"):
        raise ValueError("base manifest lacks data.content_sha256: %s" % base_rel)

    corpus2 = copy.deepcopy(corpus)
    pages2 = []
    context = []
    vol_seq = {}
    class_counts = {k: 0 for k in CLASSES}
    basis_counts = {b: 0 for b in BASES}

    for i, p in enumerate(pages):  # ترتیب فایل = ترتیب رسمی (جلد، item_index, ...)
        cls, basis, rule = classify_page(p.get("text") or "")
        class_counts[cls] += 1
        basis_counts[basis] += 1
        vol = p.get("volume") or {}
        vid = vol.get("volume_id")
        vol_seq[vid] = vol_seq.get(vid, 0) + 1
        nxt = (pages[i + 1] if (i + 1 < len(pages)
                                and (pages[i + 1].get("volume") or {}).get("volume_id") == vid)
               else None)
        page2 = dict(p)
        page2["semantic"] = {
            "record_class": cls,
            "class_basis": basis,
            "class_rule": rule,
            "order": {
                "volume_no": vol.get("volume_no"),
                "volume_id": vid,
                "item_index": p.get("item_index"),
                "dup_rank": _dup_rank_of(p.get("page_id")),
                "source_position": p.get("position"),
                "seq_in_volume": vol_seq[vid],
                "seq_global": i,
            },
            "next_page_id": nxt["page_id"] if nxt else None,
            "next_item_index": nxt.get("item_index") if nxt else None,
        }
        pages2.append(page2)
        if cls in (CLS_CHAPTER, CLS_SECTION) and nxt is not None:
            summary, n_lines = extract_summary(nxt.get("text") or "")
            if summary is not None:
                context.append(_make_context_record(p, nxt, cls, summary, n_lines))

    corpus2["semantic"] = {
        "schema_version": SEMANTIC_SCHEMA_VERSION,
        "mission": "PCM-20.5 GATE 1",
        "base_corpus": {
            "version": base_manifest.get("version"),
            "content_sha256": bdata.get("content_sha256"),
            "kind": "corpus",
            "path_rel": base_rel,
        },
        "order_key": ORDER_KEY,
        "classification": {
            "rule_set": RULE_SET,
            "min_text_chars": R.MIN_TEXT_CHARS,
            "class_counts": class_counts,
            "basis_counts": basis_counts,
        },
        "context_records": {
            "count": len(context),
            "method": SUMMARY_METHOD,
            "model": None,
            "prompt_version": None,
            "max_summary_lines": MAX_SUMMARY_LINES,
        },
    }
    corpus2.setdefault("stats", {})["semantic"] = {
        "class_counts": class_counts,
        "basis_counts": basis_counts,
        "context_record_count": len(context),
        "context_with_summary": len(context),
        "headings_total": class_counts[CLS_CHAPTER] + class_counts[CLS_SECTION],
    }
    return {"corpus": corpus2, "pages": pages2, "context": context,
            "class_counts": class_counts, "basis_counts": basis_counts,
            "base_manifest": base_manifest, "base_rel": base_rel, "base_dir": ab}


def content_files_semantic(corpus: dict, pages: list, context: list) -> dict:
    cbytes = C.canonical_json(corpus)
    pbytes = b"".join(C.canonical_json_line(p) for p in pages)
    xbytes = b"".join(C.canonical_json_line(r) for r in context)
    return {
        "corpus.json": {"sha256": C.sha256_bytes(cbytes), "size_bytes": len(cbytes)},
        "pages.jsonl": {"sha256": C.sha256_bytes(pbytes), "size_bytes": len(pbytes)},
        "context-records.jsonl": {"sha256": C.sha256_bytes(xbytes), "size_bytes": len(xbytes)},
    }


def write_semantic(build_dir: str, corpus: dict, pages: list, context: list) -> dict:
    os.makedirs(build_dir, exist_ok=True)
    paths = {
        "corpus.json": os.path.join(build_dir, "corpus.json"),
        "pages.jsonl": os.path.join(build_dir, "pages.jsonl"),
        "context-records.jsonl": os.path.join(build_dir, "context-records.jsonl"),
    }
    C.write_json(paths["corpus.json"], corpus)
    C.write_jsonl(paths["pages.jsonl"], pages)
    C.write_bytes(paths["context-records.jsonl"],
                  b"".join(C.canonical_json_line(r) for r in context))
    expected = content_files_semantic(corpus, pages, context)
    files = {}
    for name, meta in expected.items():
        p = paths[name]
        sha = C.sha256_file(p)
        size = C.file_size(p)
        if sha != meta["sha256"] or size != meta["size_bytes"]:
            raise RuntimeError("write verification failed: %s sha %s != %s"
                               % (name, sha, meta["sha256"]))
        files[name] = {"sha256": sha, "size_bytes": size}
    return {"files": files, "content_sha256": T.content_sha256_of_files(files),
            "paths": paths, "build_dir": build_dir}


# --------------------------------------------------------------------------- gaps ledger
def gaps_ledger(corpus: dict) -> dict:
    """دفترک شکاف‌های item_index (منبع معتبر آفلاینی برای بازیابی وجود ندارد)."""
    gi = (corpus.get("stats") or {}).get("item_index") or {}
    count = gi.get("missing_count", 0)
    return {"missing_item_index": {
        "count": count,
        "missing_runs": gi.get("missing_runs") or [],
        "status": "unresolved" if count > 0 else "none",
        "reason": ("no trusted source available offline: the live site /payload now "
                   "returns an HTML SPA shell (PCM-20.5 GATE 0-D evidence); recovery "
                   "requires a live re-crawl on s52 — BLOCKED until s52 is reachable"),
        "discovered": "PCM-20.5 GATE 0",
    }}


# --------------------------------------------------------------------------- validation
def validate_semantic(build_dir: str, data_root: str = None) -> tuple:
    """اعتبارسنجی لایه‌ی معنایی (S01..S07). برگشت (ok, errors, warnings)."""
    errors, warnings = [], []
    try:
        corpus = C.read_json(os.path.join(build_dir, "corpus.json"))
        pages = C.read_jsonl(os.path.join(build_dir, "pages.jsonl"))
        manifest = M.load_manifest(build_dir)
    except Exception as e:
        return False, ["S01: build unreadable: %s" % e], []
    mdata = manifest.get("data") or {}
    sem = corpus.get("semantic")

    # S01 — ساختار
    if not isinstance(sem, dict):
        return False, ["S01: corpus.semantic missing"], []
    for key in ("base_corpus", "order_key", "classification", "context_records"):
        if key not in sem:
            errors.append("S01: semantic.%s missing" % key)
    ctx_path = os.path.join(build_dir, "context-records.jsonl")
    ctx_recs = []
    if not os.path.exists(ctx_path):
        errors.append("S01: context-records.jsonl missing")
    else:
        ctx_recs = C.read_jsonl(ctx_path)
    bad_pages = 0
    for i, p in enumerate(pages):
        s = p.get("semantic")
        missing = "semantic block"
        if isinstance(s, dict):
            missing = None
            for f in ("record_class", "class_basis", "class_rule", "order", "next_page_id"):
                if f not in s:
                    missing = f
                    break
        if missing:
            bad_pages += 1
            if bad_pages <= 5:
                errors.append("S01: page %d (page_id=%s) lacks %s"
                              % (i, p.get("page_id"), missing))
    if bad_pages > 5:
        errors.append("S01: %d more pages with missing semantic fields" % (bad_pages - 5))

    # S02 — ترتیب
    s02 = Counter()
    vol_seq = {}
    for i, p in enumerate(pages):
        s = p.get("semantic") or {}
        o = s.get("order") or {}
        vol = p.get("volume") or {}
        vid = vol.get("volume_id")
        vol_seq[vid] = vol_seq.get(vid, 0) + 1
        nxt = (pages[i + 1] if (i + 1 < len(pages)
                                and (pages[i + 1].get("volume") or {}).get("volume_id") == vid)
               else None)
        exp_next = nxt["page_id"] if nxt else None
        exp_nii = nxt.get("item_index") if nxt else None
        desc = "page %d (page_id=%s)" % (i, p.get("page_id"))
        checks = [
            ("order.seq_global != %d" % i, o.get("seq_global") != i),
            ("order.seq_in_volume != %d" % vol_seq[vid], o.get("seq_in_volume") != vol_seq[vid]),
            ("order.volume_id != page.volume", o.get("volume_id") != vid),
            ("order.item_index != page.item_index", o.get("item_index") != p.get("item_index")),
            ("order.dup_rank != dup_rank(page_id)",
             o.get("dup_rank") != _dup_rank_of(p.get("page_id"))),
            ("order.source_position != page.position",
             o.get("source_position") != p.get("position")),
            ("next_page_id mismatch", s.get("next_page_id") != exp_next),
            ("next_item_index mismatch", s.get("next_item_index") != exp_nii),
        ]
        for msg, bad in checks:
            if bad:
                s02[msg] += 1
                if s02[msg] <= 5:
                    errors.append("S02: %s: %s" % (desc, msg))
    for msg, n in s02.items():
        if n > 5:
            errors.append("S02: %s: %d more" % (msg, n - 5))

    # S03 — سرشماری
    cc, bc = Counter(), Counter()
    for p in pages:
        s = p.get("semantic") or {}
        cc[s.get("record_class")] += 1
        bc[s.get("class_basis")] += 1
    exp_cc = {k: cc.get(k, 0) for k in CLASSES}
    exp_bc = {k: bc.get(k, 0) for k in BASES}
    cls_block = sem.get("classification") or {}
    if cls_block.get("class_counts") != exp_cc:
        errors.append("S03: semantic.classification.class_counts %s != recomputed %s"
                      % (cls_block.get("class_counts"), exp_cc))
    if cls_block.get("basis_counts") != exp_bc:
        errors.append("S03: semantic.classification.basis_counts %s != recomputed %s"
                      % (cls_block.get("basis_counts"), exp_bc))
    if (sem.get("context_records") or {}).get("count") != len(ctx_recs):
        errors.append("S03: context_records.count %s != %d file rows"
                      % ((sem.get("context_records") or {}).get("count"), len(ctx_recs)))
    stats_sem = (corpus.get("stats") or {}).get("semantic") or {}
    if stats_sem.get("class_counts") != exp_cc:
        errors.append("S03: stats.semantic.class_counts mismatch")
    if stats_sem.get("context_record_count") != len(ctx_recs):
        errors.append("S03: stats.semantic.context_record_count %s != %d"
                      % (stats_sem.get("context_record_count"), len(ctx_recs)))
    ids = [r.get("record_id") for r in ctx_recs]
    if len(set(ids)) != len(ids):
        errors.append("S03: duplicate context record_id")

    # S04 — verbatim بودن رکوردهای context
    by_pid = {}
    for p in pages:
        by_pid.setdefault(p.get("page_id"), p)
    if len(by_pid) != len(pages):
        errors.append("S04: page_id not unique in build — context records unverifiable")
    s04 = 0

    def _s04(msg, rid):
        nonlocal s04
        s04 += 1
        if s04 <= 5:
            errors.append("S04: %s (record_id=%s)" % (msg, rid))

    for r in ctx_recs:
        rid = r.get("record_id")
        hp = by_pid.get(r.get("heading_page_id"))
        if hp is None:
            _s04("heading page missing: %s" % r.get("heading_page_id"), rid)
            continue
        hsem = hp.get("semantic") or {}
        if hsem.get("record_class") not in (CLS_CHAPTER, CLS_SECTION):
            _s04("heading page is not a heading class: %s" % hsem.get("record_class"), rid)
        if r.get("heading_text") != hp.get("text"):
            _s04("heading_text != page.text", rid)
        if r.get("visibility") != VISIBILITY_HIDDEN:
            _s04("visibility != hidden", rid)
        if r.get("record_kind") != "context":
            _s04("record_kind != context", rid)
        if r.get("source_hash") != hp.get("content_hash"):
            _s04("source_hash != page.content_hash", rid)
        if r.get("context_page_id") != hp.get("page_id"):
            _s04("context_page_id != heading page_id", rid)
        if r.get("next_page_id") != hsem.get("next_page_id"):
            _s04("next_page_id != page.semantic.next_page_id", rid)
        np_ = by_pid.get(r.get("next_page_id"))
        if np_ is None:
            _s04("next page missing: %s" % r.get("next_page_id"), rid)
            continue
        if r.get("next_source_page_id") != np_.get("source_page_id"):
            _s04("next_source_page_id mismatch", rid)
        summary, n_lines = extract_summary(np_.get("text") or "")
        if r.get("next_page_summary") != summary:
            _s04("next_page_summary != recomputed verbatim extract", rid)
        if r.get("summary_lines") != n_lines:
            _s04("summary_lines != recomputed", rid)
        if r.get("volume_id") != (hp.get("volume") or {}).get("volume_id"):
            _s04("volume_id mismatch", rid)
        meta = {k: v for k, v in r.items() if k != "context_hash"}
        if r.get("context_hash") != C.sha256_text(C.canonical_json(meta).decode("utf-8")):
            _s04("context_hash mismatch", rid)
    if s04 > 5:
        errors.append("S04: %d more context record errors" % (s04 - 5))

    # S05 — عدم‌تغییری base
    root = data_root or M._find_data_root(build_dir)
    base_rel = (sem.get("base_corpus") or {}).get("path_rel")
    if not root or not base_rel:
        errors.append("S05: cannot resolve base corpus (root=%r base_rel=%r)"
                      % (root, base_rel))
    else:
        base_dir2 = os.path.join(root, base_rel.replace("/", os.sep))
        if not os.path.isdir(base_dir2):
            errors.append("S05: base build not found: %s" % base_rel)
        else:
            try:
                base_corpus = C.read_json(os.path.join(base_dir2, "corpus.json"))
                base_pages = C.read_jsonl(os.path.join(base_dir2, "pages.jsonl"))
            except Exception as e:
                errors.append("S05: base build unreadable: %s" % e)
            else:
                if len(base_pages) != len(pages):
                    errors.append("S05: page count differs from base: %d vs %d"
                                  % (len(pages), len(base_pages)))
                by_src = {}
                for b in base_pages:
                    by_src.setdefault(b.get("source_page_id"), b)
                if len(by_src) != len(base_pages):
                    errors.append("S05: base source_page_id not unique — cannot verify")
                s05 = Counter()

                def _s05(desc, what):
                    s05[what] += 1
                    if s05[what] <= 5:
                        errors.append("S05: %s: %s" % (desc, what))

                for p in pages:
                    b = by_src.get(p.get("source_page_id"))
                    desc = "source_page_id=%s" % p.get("source_page_id")
                    if b is None:
                        _s05(desc, "missing in base")
                        continue
                    for f in ("text", "text_normalized", "content_hash", "url", "barg",
                              "raw_barg", "item_index", "quality_status", "page_id",
                              "position"):
                        if p.get(f) != b.get(f):
                            _s05(desc, "field %s differs from base" % f)
                for what, n in s05.items():
                    if n > 5:
                        errors.append("S05: %s: %d more" % (what, n - 5))
                if (((corpus.get("stats") or {}).get("page_count") or 0)
                        != ((base_corpus.get("stats") or {}).get("page_count") or 0)):
                    errors.append("S05: stats.page_count differs from base")

    # S06 — دفترک شکاف‌ها
    gaps = (mdata.get("gaps") or {}).get("missing_item_index") or {}
    gi = (corpus.get("stats") or {}).get("item_index") or {}
    exp_count = gi.get("missing_count", 0)
    if gaps.get("count") != exp_count:
        errors.append("S06: gaps.missing_item_index.count %r != stats.item_index.missing_count %r"
                      % (gaps.get("count"), exp_count))
    if gaps.get("missing_runs") != (gi.get("missing_runs") or []):
        errors.append("S06: gaps.missing_item_index.missing_runs mismatch")
    exp_status = "unresolved" if exp_count > 0 else "none"
    if gaps.get("status") != exp_status:
        errors.append("S06: gaps status must be %r (no trusted offline source): got %r"
                      % (exp_status, gaps.get("status")))

    # S07 — manifest (files شامل context-records.jsonl + زنجیره‌ی prev)
    ok_m, merr, mwarn = M.validate_manifest(build_dir, data_root)
    for e in merr:
        errors.append("S07: %s" % e)
    warnings.extend(mwarn)
    return (not errors), errors, warnings


# --------------------------------------------------------------------------- semantic diff
def _manifest_sha(build_dir: str) -> str:
    return C.sha256_file(os.path.join(build_dir, "manifest.json"))


def _load_build_for_diff(data_root: str, tag: str) -> tuple:
    d = os.path.join(V.root_paths(data_root)["corpus_builds"], tag)
    if not os.path.isdir(d):
        raise ValueError("corpus build not found: %s" % tag)
    return (d, C.read_json(os.path.join(d, "corpus.json")),
            C.read_jsonl(os.path.join(d, "pages.jsonl")))


def _trim(items: list) -> tuple:
    return items[:_MAX_LIST], len(items) > _MAX_LIST


def semantic_diff(data_root: str, from_tag: str, to_tag: str) -> dict:
    """7 دسته‌ی semantic diff: added/recovered/changed/unchanged/missing/duplicate/unresolved."""
    from_dir, from_corpus, from_pages = _load_build_for_diff(data_root, from_tag)
    to_dir, to_corpus, to_pages = _load_build_for_diff(data_root, to_tag)
    by_from = {p.get("source_page_id"): p for p in from_pages}
    by_to = {p.get("source_page_id"): p for p in to_pages}

    added, missing, recovered, changed = [], [], [], []
    unchanged = 0
    for k, tp in by_to.items():
        if k not in by_from:
            added.append({"source_page_id": k, "page_id": tp.get("page_id"),
                          "volume_id": (tp.get("volume") or {}).get("volume_id")})
    for k, fp in by_from.items():
        if k not in by_to:
            missing.append({"source_page_id": k, "page_id": fp.get("page_id")})
    for k, fp in by_from.items():
        tp = by_to.get(k)
        if tp is None:
            continue
        fflags = ((fp.get("quality_status") or {}).get("flags")) or []
        if "missing_item_index" in fflags and tp.get("item_index") is not None:
            recovered.append({"source_page_id": k, "item_index": tp.get("item_index")})
        diff_fields = [f for f in ("text", "text_normalized", "content_hash", "barg",
                                   "item_index") if fp.get(f) != tp.get(f)]
        if diff_fields:
            changed.append({"source_page_id": k, "fields": diff_fields})
        else:
            unchanged += 1
    dup_rows = sum(1 for p in to_pages
                   if "dup_item_index" in (((p.get("quality_status") or {}).get("flags")) or []))
    to_gi = ((to_corpus.get("stats") or {}).get("item_index")) or {}
    from_sem = (from_corpus.get("semantic") or {}).get("context_records") or {}
    to_sem = (to_corpus.get("semantic") or {}).get("context_records") or {}
    ctx_added = (to_sem.get("count") or 0) - (from_sem.get("count") or 0)

    added_l, added_trunc = _trim(added)
    missing_l, missing_trunc = _trim(missing)
    rec_l, rec_trunc = _trim(recovered)
    ch_l, ch_trunc = _trim(changed)
    return {
        "kind": "semantic-change",
        "mission": "PCM-20.5 GATE 1",
        "from": {"tag": from_tag, "manifest_sha256": _manifest_sha(from_dir)},
        "to": {"tag": to_tag, "manifest_sha256": _manifest_sha(to_dir)},
        "counts": {
            "pages_from": len(by_from),
            "pages_to": len(by_to),
            "added_pages": len(added_l),
            "recovered": len(rec_l),
            "changed": len(ch_l),
            "unchanged": unchanged,
            "missing_pages": len(missing_l),
            "duplicate_rows": dup_rows,
            "unresolved_gaps": to_gi.get("missing_count", 0),
            "context_records_added": ctx_added,
        },
        "added_pages": added_l,
        "added_pages_truncated": added_trunc,
        "missing_pages": missing_l,
        "missing_pages_truncated": missing_trunc,
        "recovered": rec_l,
        "recovered_truncated": rec_trunc,
        "changed": ch_l,
        "changed_truncated": ch_trunc,
    }


def write_semantic_change_manifest(data_root: str, from_tag: str, to_tag: str) -> dict:
    diff = semantic_diff(data_root, from_tag, to_tag)
    out_dir = os.path.join(V.root_paths(data_root)["reports"],
                           "diff_%s_%s" % (from_tag, to_tag))
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "semantic-change.json")
    C.write_json(path, diff)
    return {"path": path, "sha256": C.sha256_file(path), "diff": diff}

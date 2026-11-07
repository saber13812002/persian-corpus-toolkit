# -*- coding: utf-8 -*-
"""tasnim_test_support — shared fixture read model (PCM-20.6.4, spec §9.4).

Modeled on ``backend/pct_test_support.py``: module-level shared state, and
every test class calls :func:`reset` in ``setUpClass`` so module order,
combination and repetition never leak state.

The fixture corpus is tiny (10 pages / 4 headings / 2 volumes, one overlap
pair, one dup, one gap, one truncated page, one empty page) and builds in
milliseconds, so ``reset()`` rebuilds everything from scratch in a fresh
tempdir — no stale files, no shared rate-limit db, Windows-safe
(explicit shutdown before rmtree).

Fixture layout (deterministic; no wall-clock in the main db):

  vol001  span [0,11]  pages at ii 0,1,2,3,10,11   (7 rows, ii=2 has a dup)
  vol002  span [10,12] pages at ii 10,11,12         (3 rows)

  * ii 10,11 exist in BOTH volumes  -> ambiguity + overlap [10,11]
  * ii 2: anchor p2 (rank 0) + p2b (rank 1) -> dup_of, status dup_item_index
  * global gap [4,9] (6 missing)      -> coverage rows + gap-aware refs
  * ii 12 (vol002) truncated_at_2000 with truncated_at_source=true
  * ii 11 (vol001) empty, flags empty+no_barg, barg None
  * topics: «بحث روایی» (3 pages, 2 volumes; one form «12) بحث روایی»
    normalizes to the same topic) + «پیشگفتار مفسر» (1 page, parent of
    the «بحث روایی» heading on p2)

Two DECOY forbidden files (hidden-context-records.jsonl, context-records.
jsonl) are written with a canary string, for T-HC-1/T-HC-2 proofs.
"""
import hashlib
import json
import os
import shutil
import tempfile

_ROOT = os.path.dirname(os.path.abspath(__file__))

CANARY = "HIDDEN-CANARY-DO-NOT-LEAK"
WORK_ID = "fx_work"
EDITION_ID = "fx_work__fx-2026"
V1 = "fx__vol001"
V2 = "fx__vol002"

EXPECTED = {
    "pages": 10,
    "headings": 4,
    "topics": 2,
    "volumes": 2,
    "missing": 6,
    "missing_runs": [[4, 9]],
    "dup_values": 3,
    "dup_extra_rows": 3,
    "distinct_ii": 7,
    "min_ii": 0,
    "max_ii": 12,
    "quality_status": {"ok": 5, "dup_item_index": 2, "short": 1,
                       "empty": 1, "truncated_at_2000": 1},
    "flag_counts": {"ok": 5, "dup_item_index": 2, "short": 2, "empty": 1,
                    "no_barg": 1, "truncated_at_2000": 1},
    "class_counts": {"CONTENT_PAGE": 7, "SHORT_CONTENT": 2,
                     "EMPTY_PAGE": 1},
}

_P = {}  # page ids, filled in _pages()


def _pages():
    """The 10 fixture page records, in file order."""
    from tasnim.web.readmodel import sha256_file  # noqa: F401  (parity only)

    def rec(pid, vol, ii, rank, status, flags, text, rclass, barg,
            seq_v, seq_g, next_pid, hrid=None, truncated=False,
            section="بخش 1"):
        vol_no = 1 if vol == V1 else 2
        return {
            "barg": barg,
            "captured_at": "2026-01-01 00:00:00",
            "content_hash": hashlib.sha256(
                text.encode("utf-8")).hexdigest(),
            "item_index": ii,
            "metadata": {"section": section, "item_index": ii},
            "page_id": pid,
            "position": 1000 + seq_g,
            "quality_status": {"flags": flags, "status": status},
            "raw_barg": ("برگ %d" % barg) if barg is not None else None,
            "semantic": {
                "record_class": rclass,
                "order": {"dup_rank": rank, "item_index": ii,
                          "seq_global": seq_g, "seq_in_volume": seq_v,
                          "volume_id": vol, "volume_no": vol_no},
                "hidden_context": {"heading_record_id": hrid,
                                   "context_record_id": None},
                "next_item_index": None,
                "next_page_id": next_pid,
                "truncation": {"source_char_cap": 2000,
                               "truncated_at_source": truncated},
            },
            "source_page_id": 1000 + seq_g,
            "text": text,
            "url": "https://example.org/payload?item_index=%d" % ii,
            "volume_id": vol,
        }

    P = _P
    P["p0"] = "fx__vol001__p0"
    P["p1"] = "fx__vol001__p1"
    P["p2"] = "fx__vol001__p2"
    P["p2b"] = "fx__vol001__p2b"
    P["p3"] = "fx__vol001__p3"
    P["p10a"] = "fx__vol001__p10"
    P["p11a"] = "fx__vol001__p11"
    P["p10b"] = "fx__vol002__p10"
    P["p11b"] = "fx__vol002__p11"
    P["p12"] = "fx__vol002__p12"

    rows = [
        rec(P["p0"], V1, 0, 0, "ok", [],
            "تفسیر قرآن کریم از روایات", "CONTENT_PAGE", 1, 1, 0,
            P["p1"], hrid="hctx:" + P["p0"]),
        rec(P["p1"], V1, 1, 0, "ok", [],
            "متن دوم و ادامه", "CONTENT_PAGE", 2, 2, 1, P["p2"]),
        rec(P["p2"], V1, 2, 0, "dup_item_index", ["dup_item_index"],
            "متن سوم", "CONTENT_PAGE", 3, 3, 2, P["p2b"],
            hrid="hctx:" + P["p2"]),
        rec(P["p2b"], V1, 2, 1, "dup_item_index",
            ["dup_item_index", "short"], "کوتاه", "SHORT_CONTENT", 4, 4, 3,
            P["p3"]),
        rec(P["p3"], V1, 3, 0, "short", ["short"],
            "متن کوتاه", "SHORT_CONTENT", 5, 5, 4, P["p10a"],
            hrid="hctx:" + P["p3"]),
        rec(P["p10a"], V1, 10, 0, "ok", [],
            "متن دهم", "CONTENT_PAGE", 6, 6, 5, P["p11a"]),
        rec(P["p11a"], V1, 11, 0, "empty", ["empty", "no_barg"],
            "", "EMPTY_PAGE", None, 7, 6, None),
        rec(P["p10b"], V2, 10, 0, "ok", [],
            "تفسیری بر قرآن و معنا", "CONTENT_PAGE", 1, 1, 7,
            P["p11b"], hrid="hctx:" + P["p10b"], section="بخش 2"),
        rec(P["p11b"], V2, 11, 0, "ok", [],
            "متن یازدهم", "CONTENT_PAGE", 2, 2, 8, P["p12"],
            section="بخش 2"),
        rec(P["p12"], V2, 12, 0, "truncated_at_2000", ["truncated_at_2000"],
            "زبان قرآن و بیان آن در روایات امامان علیهم‌السلام",
            "CONTENT_PAGE", 3, 3, 9, None, truncated=True,
            section="بخش 2"),
    ]
    return rows


def _headings():
    P = _P
    def rec(rid, pid, ii, vol, text, parent, next_pid, children):
        return {
            "children_page_ids": children,
            "heading_hash": hashlib.sha256(
                text.encode("utf-8")).hexdigest(),
            "heading_text": text,
            "item_index": ii,
            "next_page_id": next_pid,
            "page_id": pid,
            "parent_heading_page_id": parent,
            "provenance": {"content_hash": "0" * 64},
            "record_id": rid,
            "record_kind": "heading",
            "source_class": "SECTION_HEADING",
            "visibility": "hidden_context",
            "volume_id": vol,
            "volume_no": 1 if vol == V1 else 2,
        }
    return [
        rec("hctx:" + P["p0"], P["p0"], 0, V1, "پیشگفتار مفسر", None,
            P["p1"], [P["p2"]]),
        rec("hctx:" + P["p2"], P["p2"], 2, V1, "بحث روایی", P["p0"],
            P["p2b"], [P["p3"]]),
        rec("hctx:" + P["p3"], P["p3"], 3, V1, "بحث روایی", None,
            P["p10a"], []),
        rec("hctx:" + P["p10b"], P["p10b"], 10, V2, "12) بحث روایی", None,
            P["p11b"], []),
    ]


def _corpus_json():
    return {
        "kind": "corpus",
        "schema_version": "tasnim-corpus/1.0",
        "work": {"work_id": WORK_ID, "work_name": "پیکره آزمایشی",
                 "source": "test fixture", "description": "PCM-20.6.4 fixture"},
        "edition": {"edition_id": EDITION_ID,
                    "edition_name": "خروجی آزمایشی",
                    "source_version": "fixture",
                    "exported_at": "2026-01-01T00:00:00Z"},
        "volumes": [
            {"volume_id": V1, "edition_id": EDITION_ID, "volume_no": 1,
             "volume_title": "جلد 1", "volume_strategy": "url_section",
             "source_section": "بخش 1", "page_count": 7,
             "item_index_span": [0, 11], "barg_span": [1, 7]},
            {"volume_id": V2, "edition_id": EDITION_ID, "volume_no": 2,
             "volume_title": "جلد 2", "volume_strategy": "url_section",
             "source_section": "بخش 2", "page_count": 3,
             "item_index_span": [10, 12], "barg_span": [1, 3]},
        ],
        "semantic": {
            "schema_version": "tasnim-semantic/1.0",
            "hidden_context": {
                "policy": "must never be rendered publicly (fixture)",
                "heading_records": {"count": EXPECTED["headings"],
                                    "file": "heading-records.jsonl",
                                    "record_id_prefix": "hctx:"},
                "context_records": {"count": 0,
                                    "file": "context-records.jsonl"},
                "visibility": "hidden_context",
                "relations": {},
            },
            "truncation": {"affected_count": 1,
                           "affected_pages": [_P["p12"]],
                           "source_char_cap": 2000},
        },
    }


def build_fixture_corpus(corpus_dir):
    """Write the 4 allowed files + 2 forbidden DECOY files. Returns the
    manifest dict (for direct assertions in tests)."""
    _pages()  # populate _P
    os.makedirs(corpus_dir, exist_ok=True)

    def wjsonl(name, rows):
        with open(os.path.join(corpus_dir, name), "w",
                  encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

    wjsonl("pages.jsonl", _pages())
    wjsonl("heading-records.jsonl", _headings())
    with open(os.path.join(corpus_dir, "corpus.json"), "w",
              encoding="utf-8") as f:
        json.dump(_corpus_json(), f, ensure_ascii=False, indent=1)

    # decoy forbidden files (T-HC-1: must never be opened)
    for name in ("hidden-context-records.jsonl", "context-records.jsonl"):
        with open(os.path.join(corpus_dir, name), "w",
                  encoding="utf-8") as f:
            f.write(json.dumps(
                {"canary": CANARY, "hidden_summary": "secret text",
                 "retrieval_context": "secret text"},
                ensure_ascii=False) + "\n")

    from tasnim.web.readmodel import sha256_file
    files = {}
    for name in ("pages.jsonl", "heading-records.jsonl", "corpus.json"):
        files[name] = {"sha256": sha256_file(
            os.path.join(corpus_dir, name)),
            "size_bytes": os.path.getsize(os.path.join(corpus_dir, name))}
    # manifest also lists the forbidden files, exactly like the real one
    for name in ("hidden-context-records.jsonl", "context-records.jsonl"):
        files[name] = {"sha256": sha256_file(
            os.path.join(corpus_dir, name)),
            "size_bytes": os.path.getsize(os.path.join(corpus_dir, name))}

    manifest = {
        "kind": "manifest",
        "manifest_version": "m-2",
        "version": "fixture",
        "data": {
            "content_sha256": "f" * 64,
            "files": files,
            "stats": {
                "page_count": EXPECTED["pages"],
                "volume_count": EXPECTED["volumes"],
                "quality_flag_counts": EXPECTED["flag_counts"],
                "semantic": {"class_counts": EXPECTED["class_counts"]},
                "duplicates": {"item_index_values": EXPECTED["dup_values"],
                               "item_index_extra_rows":
                               EXPECTED["dup_extra_rows"]},
                "item_index": {
                    "count": EXPECTED["pages"],
                    "distinct": EXPECTED["distinct_ii"],
                    "min": EXPECTED["min_ii"],
                    "max": EXPECTED["max_ii"],
                    "missing_count": EXPECTED["missing"],
                    "missing_runs": EXPECTED["missing_runs"],
                },
                "text_len": {"p50": 100, "p90": 150, "p99": 190,
                             "max": 2000},
            },
            "gaps": {"missing_item_index": {
                "count": EXPECTED["missing"],
                "missing_runs": EXPECTED["missing_runs"],
                "reason": "test fixture: backfill pending",
                "status": "unresolved"}},
        },
    }
    with open(os.path.join(corpus_dir, "manifest.json"), "w",
              encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=1)
    return manifest


def read_json(name_or_path):
    with open(name_or_path, encoding="utf-8") as f:
        return json.load(f)


def write_json(name_or_path, obj):
    with open(name_or_path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)


def rehash_file(corpus_dir, name):
    """Refresh manifest.json's sha for a mutated source file.

    The builder verifies every manifest-listed file's sha (invariant:
    source integrity), so any test that mutates a source file MUST call
    this before building — otherwise the build fails with
    "sha256 mismatch" instead of reaching the intended failure point.
    """
    from tasnim.web.readmodel import sha256_file
    p = os.path.join(corpus_dir, "manifest.json")
    mj = read_json(p)
    mj["data"]["files"][name]["sha256"] = sha256_file(
        os.path.join(corpus_dir, name))
    mj["data"]["files"][name]["size_bytes"] = os.path.getsize(
        os.path.join(corpus_dir, name))
    write_json(p, mj)


# ---------------------------------------------------------------------------
# shared state (pct_test_support pattern)
# ---------------------------------------------------------------------------

_STATE = {}


def _shutdown_state(state):
    for app in list(state.get("apps", [])):
        try:
            app.tasnim_shutdown()
        except Exception:
            pass
    shutil.rmtree(state.get("tmp", ""), ignore_errors=True)


def reset():
    """Tear down any previous fixture and build a fresh one. Returns the
    state dict. Call from setUpClass of every test class."""
    if _STATE:
        _shutdown_state(_STATE)
    from tasnim.web.readmodel import ReadModelBuilder
    tmp = tempfile.mkdtemp(prefix="pct_tasnim_fx_")
    corpus_dir = os.path.join(tmp, "v0099")   # basename -> corpus_version
    out_dir = os.path.join(tmp, "readmodel", "v0099")
    build_fixture_corpus(corpus_dir)
    report = ReadModelBuilder(corpus_dir, out_dir).build()
    state = {
        "tmp": tmp,
        "corpus_dir": corpus_dir,
        "out_dir": out_dir,
        "db_path": os.path.join(out_dir, "tasnim_readmodel.db"),
        "report": report,
        "apps": [],
    }
    _STATE.clear()
    _STATE.update(state)
    return state


def get():
    return _STATE if _STATE else reset()


def make_app(state=None, rate_search=30, rate_read=120, clock=None,
             rate_db_path=None, with_ssr=True):
    """Create a Flask app over the fixture read model. The app is tracked
    in the shared state so tearDownClass can close its rate-limit db
    (Windows: open handle would block rmtree). ``with_ssr`` mounts the
    V1 SSR frontend (default on; the API-only suites pass False)."""
    from tasnim.web.api import create_app
    state = state if state is not None else get()
    if rate_db_path is None:
        rate_db_path = os.path.join(state["tmp"],
                                    "rate_%d.db" % len(state["apps"]))
    app = create_app(state["db_path"], rate_search=rate_search,
                     rate_read=rate_read, rate_db_path=rate_db_path,
                     clock=clock, with_ssr=with_ssr)
    state["apps"].append(app)
    return app

# -*- coding: utf-8 -*-
"""Tasnim Web V1 — read model builder tests (PCM-20.6.4, spec §9.1 group
"parser/mapping", "item_index", "flags", "heading mapping", "topics",
"hidden-context isolation" T-HC-1/2, plus the determinism invariant §4.3).

All tests are OFFLINE and run on the tiny deterministic fixture corpus
from ``tasnim_test_support`` (no production corpus, no network).

Run (worktree root):
    python -X utf8 -m unittest test_tasnim_readmodel -v
"""
import json
import os
import shutil
import sqlite3
import tempfile
import unittest

import tasnim_test_support as fx
from tasnim.web import readmodel as rm
from tasnim.web.readmodel import (BuildError, ReadModelBuilder,
                                  _dig, _gaps_reason, _runs_of,
                                  _runs_of_missing, _vol_part_of_page_id,
                                  build_fts_match, make_snippet,
                                  normalize_topic, sha256_file,
                                  topic_id_of, tokenize_fa)


def _fresh_build(mutate=None):
    """Build the fixture corpus in a fresh tmpdir. `mutate(corpus_dir)`
    may be called after the corpus is written (for failure tests)."""
    tmp = tempfile.mkdtemp(prefix="pct_rm_")
    corpus_dir = os.path.join(tmp, "v0099")
    out_dir = os.path.join(tmp, "out")
    try:
        fx.build_fixture_corpus(corpus_dir)
        if mutate:
            mutate(corpus_dir)
        report = ReadModelBuilder(corpus_dir, out_dir).build()
        return tmp, corpus_dir, out_dir, report
    except Exception:
        shutil.rmtree(tmp, ignore_errors=True)
        raise


class TestRunHelpers(unittest.TestCase):
    def test_runs_of_missing(self):
        present = {0, 1, 2, 3, 10, 11, 12}
        self.assertEqual(_runs_of_missing(present, 0, 12), [(4, 9)])
        self.assertEqual(_runs_of_missing({0}, 0, 5), [(1, 5)])
        self.assertEqual(_runs_of_missing({0, 1, 2}, 0, 2), [])

    def test_runs_of(self):
        self.assertEqual(_runs_of([1, 2, 3, 7, 8]), [[1, 3], [7, 8]])
        self.assertEqual(_runs_of([5]), [[5, 5]])

    def test_vol_part_of_page_id(self):
        self.assertEqual(
            _vol_part_of_page_id("fx__vol001__p10"), "fx__vol001")
        self.assertEqual(_vol_part_of_page_id("plain"), "plain")

    def test_gaps_reason(self):
        self.assertEqual(_gaps_reason({"gaps": {"missing_item_index": {
            "reason": "r"}}}), "r")
        self.assertTrue(_gaps_reason(None).startswith("backfill pending"))

    def test_dig(self):
        d = {"a": {"b": {"c": 1}}}
        self.assertEqual(_dig(d, "a", "b", "c"), 1)
        self.assertIsNone(_dig(d, "a", "x"))
        self.assertIsNone(_dig("no", "a"))


class TestTokenization(unittest.TestCase):
    """spec §9.1 "FTS tokenization": ZWNJ split, digit map, prefix."""

    def test_zwnj_split(self):
        self.assertEqual(tokenize_fa("نیم‌نوشته"), ["نیم", "نوشته"])

    def test_digit_map(self):
        self.assertEqual(tokenize_fa("۱۲۳ و 45"), ["123", "و", "45"])
        self.assertEqual(tokenize_fa("٢٠"), ["20"])

    def test_diacritics_deleted(self):
        # fully-voweled Arabic: diacritics DELETED (not spaced)
        self.assertEqual(tokenize_fa("مَكتوب"), ["مكتوب"])
        self.assertEqual(tokenize_fa("عَ"), ["ع"])

    def test_latin_and_mixed(self):
        self.assertEqual(tokenize_fa("abc 123 فارسی"),
                         ["abc", "123", "فارسی"])
        self.assertEqual(tokenize_fa(""), [])

    def test_build_fts_match_prefix_and(self):
        self.assertEqual(build_fts_match(["تفسیر"]), '"تفسیر"*')
        self.assertEqual(build_fts_match(["زبان", "قرآن"]),
                         '"زبان"* AND "قرآن"*')

    def test_prefix_matches_suffix_morphology(self):
        # «تفسیر*» must hit «تفسیری» — prefix over pre-computed tokens
        stored = tokenize_fa("تفسیری بر قرآن")
        self.assertIn("تفسیری", stored)
        self.assertTrue(stored[0].startswith("تفسیر"))

    def test_make_snippet_hit(self):
        segs = make_snippet("این متن دربارهٔ قرآن کریم است", "قرآن")
        marked = [s for s, m in segs if m]
        self.assertEqual(len(marked), 1)
        self.assertIn("قرآن", marked[0])

    def test_make_snippet_miss_fallback(self):
        segs = make_snippet("متن کوتاه بدون عبارت", "غایب")
        self.assertFalse(any(m for _s, m in segs))
        self.assertEqual("".join(s for s, _m in segs), "متن کوتاه بدون عبارت")


class TestTopicNormalization(unittest.TestCase):
    """spec §9.1 "topics": hamza/ZWNJ/digit/leading-number cases +
    stable topic_id across raw forms."""

    def test_leading_number_stripped(self):
        self.assertEqual(normalize_topic("12) بحث روایی"), "بحث روایی")
        self.assertEqual(normalize_topic("(3) بحث روایی"), "بحث روایی")
        self.assertEqual(normalize_topic("[5] بحث روایی"), "بحث روایی")

    def test_unicode_digits(self):
        self.assertEqual(normalize_topic("۱۲) بحث روایی"), "بحث روایی")

    def test_hamza_unification(self):
        self.assertEqual(normalize_topic("گزیدهٔ"), "گزیده")
        self.assertEqual(normalize_topic("گزیدهٴ"), "گزیده")

    def test_trailing_punct(self):
        self.assertEqual(normalize_topic("بحث روایی ."), "بحث روایی")
        self.assertEqual(normalize_topic("بحث روایی:"), "بحث روایی")

    def test_whitespace_collapsed(self):
        self.assertEqual(normalize_topic("بحث   روایی\nمتن"),
                         "بحث روایی متن")

    def test_stable_id_across_forms(self):
        # «بحث روایی» and «12) بحث روایی» → ONE topic (spec: گزیده 3شکل → 1)
        a = topic_id_of(normalize_topic("بحث روایی"))
        b = topic_id_of(normalize_topic("12) بحث روایی"))
        self.assertEqual(a, b)
        self.assertTrue(a.startswith("t-"))
        self.assertEqual(len(a), 2 + 12)


class TestFixtureBuild(unittest.TestCase):
    """The shared fixture build: report, outputs, invariants, row-level
    mapping checks (parser/mapping, item_index, flags, heading, topics)."""

    @classmethod
    def setUpClass(cls):
        cls.state = fx.reset()

    def test_report_counts(self):
        c = self.state["report"]["counts"]
        self.assertEqual(c["pages"], fx.EXPECTED["pages"])
        self.assertEqual(c["headings"], fx.EXPECTED["headings"])
        self.assertEqual(c["topics"], fx.EXPECTED["topics"])
        self.assertEqual(c["volumes"], fx.EXPECTED["volumes"])
        self.assertEqual(c["missing_item_index"], fx.EXPECTED["missing"])
        self.assertEqual(c["missing_runs"], fx.EXPECTED["missing_runs"])
        self.assertEqual(c["dup_item_index_values"], fx.EXPECTED["dup_values"])

    def test_version_from_dirname(self):
        self.assertEqual(self.state["report"]["corpus_version"], "v0099")

    def test_opened_files_exact_allowed(self):
        self.assertEqual(self.state["report"]["opened_files"],
                         sorted(rm.ALLOWED_SOURCE_FILES))

    def test_invariants(self):
        inv = self.state["report"]["invariants"]
        self.assertTrue(inv["source_read_only"])
        self.assertEqual(inv["forbidden_files_opened"], [])
        self.assertFalse(inv["hidden_context_included"])

    def test_outputs_exist(self):
        out = self.state["out_dir"]
        for name in ("tasnim_readmodel.db", "build_meta.db",
                     "build.sha256", "covers"):
            self.assertTrue(os.path.exists(os.path.join(out, name)), name)
        for vid in (fx.V1, fx.V2):
            self.assertTrue(os.path.exists(
                os.path.join(out, "covers", vid + ".svg")))

    def test_sidecar_sha_matches(self):
        with open(os.path.join(self.state["out_dir"], "build.sha256"),
                  encoding="utf-8") as f:
            lines = f.read().splitlines()
        self.assertEqual(
            [l.split()[-1] for l in lines],
            ["tasnim_readmodel.db", "build_meta.db"])
        self.assertEqual(lines[0].split()[0], self.state["report"]["db_sha256"])

    def test_build_meta_rows(self):
        conn = sqlite3.connect(self.state["out_dir"] + os.sep
                               + "build_meta.db")
        try:
            meta = dict(conn.execute(
                "SELECT key, value FROM build_meta").fetchall())
        finally:
            conn.close()
        self.assertEqual(meta["corpus_version"], "v0099")
        self.assertEqual(meta["rag_status"], "not_connected")
        self.assertEqual(meta["surah_status"], "not_supported")
        self.assertEqual(meta["hidden_context_included"], "false")
        self.assertEqual(meta["schema_version"],
                         rm.SCHEMA_VERSION)
        self.assertEqual(meta["tokenizer_version"],
                         rm.TOKENIZER_VERSION)
        self.assertEqual(meta["page_count"], "10")
        self.assertEqual(meta["heading_count"], "4")
        self.assertEqual(meta["topic_count"], "2")
        self.assertEqual(meta["volume_count"], "2")
        self.assertEqual(meta["db_sha256"],
                         self.state["report"]["db_sha256"])
        self.assertIn("must never be rendered publicly", meta["policy"])
        tl = json.loads(meta["text_length_stats"])
        self.assertEqual(tl, {"p50": 100, "p90": 150, "p99": 190,
                              "max": 2000})

    def _pages(self):
        conn = sqlite3.connect(self.state["db_path"])
        conn.row_factory = sqlite3.Row
        try:
            rows = {r["page_id"]: r for r in conn.execute(
                "SELECT * FROM pages")}
        finally:
            conn.close()
        return rows

    def test_dup_of_mapping(self):
        rows = self._pages()
        # ii=2: anchor p2 (rank 0) + p2b (rank 1) → dup_of → anchor
        self.assertEqual(rows[fx._P["p2"]]["dup_rank"], 0)
        self.assertIsNone(rows[fx._P["p2"]]["dup_of"])
        self.assertEqual(rows[fx._P["p2b"]]["dup_rank"], 1)
        self.assertEqual(rows[fx._P["p2b"]]["dup_of"],
                         fx._P["p2"])
        # overlap ii=10/11: both rank 0 → NO dup_of (ambiguity, not dup)
        self.assertIsNone(rows[fx._P["p10b"]]["dup_of"])
        self.assertIsNone(rows[fx._P["p11b"]]["dup_of"])

    def test_flags_and_status(self):
        rows = self._pages()
        P = fx._P
        self.assertEqual(rows[P["p12"]]["flag_truncated_2000"], 1)
        self.assertEqual(rows[P["p11a"]]["flag_empty"], 1)
        self.assertEqual(rows[P["p3"]]["flag_short"], 1)
        self.assertEqual(rows[P["p2b"]]["flag_short"], 1)
        self.assertEqual(rows[P["p2b"]]["status"], "dup_item_index")
        self.assertEqual(rows[P["p0"]]["status"], "ok")

    def test_truncation_only_with_source_flag(self):
        rows = self._pages()
        for r in rows.values():
            if r["flag_truncated_2000"]:
                self.assertEqual(r["page_id"], fx._P["p12"])

    def test_volume_rows_and_overlaps(self):
        conn = sqlite3.connect(self.state["db_path"])
        conn.row_factory = sqlite3.Row
        try:
            vols = {r["volume_id"]: r for r in
                    conn.execute("SELECT * FROM volumes")}
        finally:
            conn.close()
        self.assertEqual(vols[fx.V1]["page_count"], 7)
        self.assertEqual(vols[fx.V1]["item_index_min"], 0)
        self.assertEqual(vols[fx.V1]["item_index_max"], 11)
        self.assertEqual(vols[fx.V2]["page_count"], 3)
        self.assertTrue(vols[fx.V1]["ambiguity_flag"])
        self.assertTrue(vols[fx.V2]["ambiguity_flag"])
        note = json.loads(vols[fx.V1]["overlap_note"])
        self.assertEqual(note[0]["volume_id"], fx.V2)
        self.assertEqual(note[0]["ranges"], [[10, 11]])
        self.assertEqual(note[0]["item_index_count"], 2)

    def test_coverage_rows(self):
        conn = sqlite3.connect(self.state["db_path"])
        conn.row_factory = sqlite3.Row
        try:
            cov = list(conn.execute(
                "SELECT * FROM coverage ORDER BY scope, missing_from"))
        finally:
            conn.close()
        g = [r for r in cov if r["scope"] == "global"]
        self.assertEqual([(r["missing_from"], r["missing_to"],
                            r["missing_count"]) for r in g],
                         [(4, 9, 6)])
        self.assertEqual(g[0]["status"], "backfill_pending")
        v1 = [r for r in cov if r["scope"] == fx.V1]
        self.assertEqual([(r["missing_from"], r["missing_to"])
                          for r in v1], [(4, 9)])
        self.assertEqual(v1[0]["status"], "backfill_pending")
        self.assertEqual([r for r in cov if r["scope"] == fx.V2], [])

    def test_heading_rows_and_parents(self):
        conn = sqlite3.connect(self.state["db_path"])
        conn.row_factory = sqlite3.Row
        try:
            hs = list(conn.execute("SELECT * FROM headings"))
        finally:
            conn.close()
        self.assertEqual(len(hs), 4)
        by_page = {h["page_id"]: h for h in hs}
        self.assertEqual(by_page[fx._P["p2"]]["parent_heading_page_id"],
                         fx._P["p0"])
        self.assertEqual(by_page[fx._P["p2"]]["children_count"], 1)
        self.assertEqual(by_page[fx._P["p0"]]["next_page_id"],
                         fx._P["p1"])
        # all parents resolve (orphan = 0, enforced by builder): parent
        # page must exist and itself carry a heading record
        for h in hs:
            if h["parent_heading_page_id"]:
                self.assertIn(h["parent_heading_page_id"], by_page,
                              "parent page %s has no heading"
                              % h["parent_heading_page_id"])

    def test_topics_rows(self):
        conn = sqlite3.connect(self.state["db_path"])
        conn.row_factory = sqlite3.Row
        try:
            ts = {r["normalized_text"]: r
                  for r in conn.execute("SELECT * FROM topics")}
        finally:
            conn.close()
        self.assertEqual(set(ts), {"بحث روایی", "پیشگفتار مفسر"})
        b = ts["بحث روایی"]
        self.assertEqual(b["page_count"], 3)
        self.assertEqual(b["volume_count"], 2)
        self.assertEqual(b["display_text"], "بحث روایی")
        self.assertEqual(b["first_item_index"], 2)
        self.assertEqual(b["first_page_id"], fx._P["p2"])
        self.assertEqual(b["topic_id"], topic_id_of("بحث روایی"))


class TestDeterminism(unittest.TestCase):
    """spec §4.3 invariant 2: two builds of identical input → identical
    db bytes (no wall-clock timestamps in the main db)."""

    def test_two_builds_same_sha(self):
        tmp = tempfile.mkdtemp(prefix="pct_det_")
        corpus_dir = os.path.join(tmp, "v0099")
        try:
            fx.build_fixture_corpus(corpus_dir)
            a = os.path.join(tmp, "a")
            b = os.path.join(tmp, "b")
            ReadModelBuilder(corpus_dir, a).build()
            ReadModelBuilder(corpus_dir, b).build()
            self.assertEqual(sha256_file(os.path.join(a,
                               "tasnim_readmodel.db")),
                             sha256_file(os.path.join(b,
                               "tasnim_readmodel.db")))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_volume_no_null_preserved(self):
        # spec §9.1: «volume_no null حفظ شود»
        tmp, _c, out, _r = _fresh_build(mutate=lambda d: self._null_vol2(d))
        try:
            conn = sqlite3.connect(os.path.join(out, "tasnim_readmodel.db"))
            try:
                row = conn.execute(
                    "SELECT volume_no FROM volumes WHERE volume_id=?",
                    (fx.V2,)).fetchone()
            finally:
                conn.close()
            self.assertIsNone(row[0])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    @staticmethod
    def _null_vol2(corpus_dir):
        path = os.path.join(corpus_dir, "corpus.json")
        cj = fx.read_json(path)
        cj["volumes"][1]["volume_no"] = None
        fx.write_json(path, cj)
        fx.rehash_file(corpus_dir, "corpus.json")


class TestValidationFailures(unittest.TestCase):
    """spec §9.1/§4.3 invariant 6: validation vs manifest = build fail."""

    def _expect_build_error(self, mutate, needle):
        with self.assertRaises(BuildError) as ctx:
            _fresh_build(mutate=mutate)
        self.assertIn(needle, str(ctx.exception))

    @staticmethod
    def _mutate_jsonl(d, name, fn):
        p = os.path.join(d, name)
        with open(p, encoding="utf-8") as f:
            lines = f.read().splitlines()
        fn(lines)
        with open(p, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        fx.rehash_file(d, name)

    def test_page_count_mismatch(self):
        def m(d):
            p = os.path.join(d, "manifest.json")
            mj = fx.read_json(p)
            mj["data"]["stats"]["page_count"] = 99
            fx.write_json(p, mj)
        self._expect_build_error(m, "page count")

    def test_class_count_mismatch(self):
        def m(d):
            p = os.path.join(d, "manifest.json")
            mj = fx.read_json(p)
            mj["data"]["stats"]["semantic"]["class_counts"][
                "CONTENT_PAGE"] = 1
            fx.write_json(p, mj)
        self._expect_build_error(m, "class CONTENT_PAGE")

    def test_cross_volume_next_page_id(self):
        def m(d):
            def f(lines):
                rec = json.loads(lines[4])   # p3 (5th row, vol001)
                # the builder's R1 guard reads the TOP-level next_page_id
                rec["next_page_id"] = "fx__vol002__p10"
                lines[4] = json.dumps(rec, ensure_ascii=False)
            self._mutate_jsonl(d, "pages.jsonl", f)
        self._expect_build_error(m, "R1")

    def test_orphan_heading_parent(self):
        def m(d):
            def f(lines):
                rec = json.loads(lines[1])   # hctx:p2
                rec["parent_heading_page_id"] = "fx__vol001__pX"
                lines[1] = json.dumps(rec, ensure_ascii=False)
            self._mutate_jsonl(d, "heading-records.jsonl", f)
        self._expect_build_error(m, "orphan")

    def test_truncation_flag_without_source(self):
        def m(d):
            def f(lines):
                rec = json.loads(lines[9])   # p12 (10th row)
                rec["semantic"]["truncation"]["truncated_at_source"] = False
                lines[9] = json.dumps(rec, ensure_ascii=False)
            self._mutate_jsonl(d, "pages.jsonl", f)
        self._expect_build_error(m, "truncated_at_2000 without")

    def test_duplicate_page_id(self):
        def m(d):
            def f(lines):
                lines.append(lines[1])       # duplicate p1
            self._mutate_jsonl(d, "pages.jsonl", f)
        self._expect_build_error(m, "duplicate page_id")

    def test_source_sha_mismatch(self):
        def m(d):
            p = os.path.join(d, "pages.jsonl")
            with open(p, "a", encoding="utf-8") as f:
                f.write("{}\n")
        self._expect_build_error(m, "sha256 mismatch")


class TestHiddenContextIsolation(unittest.TestCase):
    """HP-1 layer 1+2 tests (T-HC-1, T-HC-2), spec §9.1.

    T-HC-1: builder files opened = EXACT allowed set (OS-level open spy);
            forbidden decoy content never reaches the db bytes.
    T-HC-2: schema has NO column/table for hidden_summary /
            retrieval_context (introspection over sqlite_master).
    """

    FORBIDDEN_SUBSTRINGS = (b"hidden_summary", b"retrieval_context",
                            fx.CANARY.encode("utf-8"),
                            b"secret text")

    @classmethod
    def setUpClass(cls):
        cls.state = fx.reset()

    def test_hc1_opened_files_os_spy(self):
        # T-HC-1 (spec §9.1): the builder's files opened = EXACT allowed
        # set. Two complementary proofs:
        #  (a) builder.opened_files — every corpus read goes through
        #      _open(), which raises on forbidden names and records all
        #      others;
        #  (b) OS-level open() spy on the readmodel module: the two
        #      forbidden decoys (written by the fixture with a canary)
        #      are never opened at all.
        tmp = tempfile.mkdtemp(prefix="pct_hc1_")
        corpus_dir = os.path.join(tmp, "v0099")
        out = os.path.join(tmp, "out")
        real_open = open
        opened_any = []
        b = None
        try:
            fx.build_fixture_corpus(corpus_dir)
            # decoys exist on disk (so "never opened" is meaningful)
            self.assertTrue(os.path.exists(os.path.join(
                corpus_dir, "hidden-context-records.jsonl")))
            self.assertTrue(os.path.exists(os.path.join(
                corpus_dir, "context-records.jsonl")))

            def spy_open(path, *a, **k):
                if isinstance(path, str) and path.startswith(corpus_dir):
                    opened_any.append(os.path.basename(path))
                return real_open(path, *a, **k)

            rm.open = spy_open
            try:
                b = ReadModelBuilder(corpus_dir, out)
                b.build()
            finally:
                rm.open = real_open
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        self.assertEqual(sorted(set(b.opened_files)),
                         sorted(rm.ALLOWED_SOURCE_FILES))
        for name in rm.FORBIDDEN_SOURCE_FILES:
            self.assertNotIn(name, opened_any)

    def test_hc1_forbidden_open_raises(self):
        b = ReadModelBuilder("/nonexistent-corpus", "/nonexistent-out")
        with self.assertRaises(BuildError) as ctx:
            b._open("hidden-context-records.jsonl")
        self.assertIn("HP-1", str(ctx.exception))

    def test_hc2_no_forbidden_substrings_in_db_bytes(self):
        for name in ("tasnim_readmodel.db", "build_meta.db"):
            with open(os.path.join(self.state["out_dir"], name), "rb") as f:
                data = f.read()
            for bad in self.FORBIDDEN_SUBSTRINGS:
                self.assertNotIn(bad, data,
                                 "%r in %s" % (bad, name))

    def test_hc2_schema_introspection(self):
        conn = sqlite3.connect(self.state["db_path"])
        try:
            objs = [r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master"
                " WHERE type IN ('table','view','index')")]
            names = list(objs)
            for obj in objs:
                if obj.startswith("sqlite_"):
                    continue
                names.extend(r[1] for r in conn.execute(
                    'PRAGMA table_info("%s")' % obj))
        finally:
            conn.close()
        for n in names:
            low = n.lower()
            self.assertNotIn("hidden", low, "table/column %r" % n)
            self.assertNotIn("hidden_summary", low, n)
            self.assertNotIn("retrieval_context", low, n)
        # the surahs table exists but is EMPTY (honest 503)
        conn = sqlite3.connect(self.state["db_path"])
        try:
            self.assertEqual(
                conn.execute("SELECT COUNT(*) FROM surahs").fetchone()[0],
                0)
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)

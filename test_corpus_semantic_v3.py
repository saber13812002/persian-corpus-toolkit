# -*- coding: utf-8 -*-
"""test_corpus_semantic_v3.py — PCM-20.6 SUBTASK 02: قرارداد Semantic v0003 (cs-20.6).

اجرا:  python -X utf8 -m unittest test_corpus_semantic_v3 -v

فیکستور اصلی: همان 10 رکورد test_corpus_semantic (2 جلد) —
    idx 1  CONTENT_PAGE            (جلد 1)
    idx 2  CHAPTER_HEADING «سوره بقره»
    idx 3  SECTION_HEADING «1. شأن نزول»
    idx 4  SECTION_HEADING «تفسیر»
    idx 5  UNKNOWN_STRUCTURE «* * *»
    idx 6  EMPTY_PAGE «»
    idx 7  CONTENT_PAGE
    idx 8  SHORT_CONTENT (19 کاراکتر)
    idx 9  CONTENT_PAGE            (جلد 2)
    idx 10 SECTION_HEADING «مفردات» (پایان جلد 2)

انتظار v0003 (cs-20.6):
    * 4 رکورد HeadingRecord (hctx: برای idx 2، 3، 4، 10) با روابط parent/children:
        - idx2: parent=None, children=[]            (بعدش تا idx3 صفحه‌ای نیست)
        - idx3: parent=idx2,  children=[]
        - idx4: parent=idx3,  children=[idx5, idx6, idx7, idx8]
        - idx10: parent=None (جلد 2 عنوان قبلی ندارد), children=[] (پایان جلد)
    * 3 رکورد ContextRecord (hcctx: برای idx 2، 3، 4 — همان انتخاب cs-20.5):
        idx10 context ندارد (آخرِ جلد). hidden_summary = استخراج verbatim 3 خط؛
        summary_sha256 + provenance + next_volume_no = 1 (همه جلد 1).
    * truncation: در این فیکستور هیچ صفحه‌ی 2000 کاراکتری نیست → affected_count=0
      (آزمون جدا روی فیکستور 21 رکوردی test_corpus_tasnim که idx 11 = "خ"*2000 است).
    * همه‌ی فیلدها/فایل‌های cs-20.5 دست‌نخورده (context-records.jsonl بایت‌به‌بایت).
    * opt-in: `build-semantic --base v0002` (پیش‌فرض cs-20.5) باید rc=2 بماند (S11).
"""
import contextlib
import io
import os
import shutil
import tempfile
import unittest

from corpus.tasnim import cli as CL
from corpus.tasnim import common as C
from corpus.tasnim import manifest as M
from corpus.tasnim import schema as S
from corpus.tasnim import semantic as SEM
from corpus.tasnim import validate as VAL
from corpus.tasnim import versioning as V

from test_corpus_semantic import make_semantic_fixture
from test_corpus_tasnim import make_fixture as make_full_fixture


ED = "%s__%s" % (S.WORK, S.EDITION)          # edition_id
P = lambda i: "%s__vol001__p%d" % (ED, i)    # page_id جلد 1
P2 = lambda i: "%s__vol002__p%d" % (ED, i)   # page_id جلد 2


class V3Base(unittest.TestCase):
    def setUp(self):
        C.force_utf8_stdio()
        self.tmp = tempfile.mkdtemp(prefix="pct-semv3-test-")
        self.data_root = os.path.join(self.tmp, "data", "tasnim")
        self.fix = os.path.join(self.tmp, "src")
        os.makedirs(self.fix, exist_ok=True)
        self.jsonl = os.path.join(self.fix, "tasnim-corpus.jsonl")
        make_semantic_fixture(self.jsonl)

    def tearDown(self):
        try:
            shutil.rmtree(self.tmp)
        except Exception:
            pass

    def builds_dir(self, data_root=None):
        return os.path.join(data_root or self.data_root, "corpus", "builds")

    def build_corpus(self):
        rc = CL.main(["build-corpus", "--jsonl", self.jsonl,
                      "--data-root", self.data_root])
        self.assertEqual(rc, 0, "build-corpus failed")
        return os.path.join(self.builds_dir(), "v0001")

    def build_semantic(self):
        rc = CL.main(["build-semantic", "--data-root", self.data_root,
                      "--base", "v0001"])
        self.assertEqual(rc, 0, "build-semantic failed")
        return os.path.join(self.builds_dir(), "v0002")

    def build_v3(self, expect_tag="v0003"):
        rc = CL.main(["build-semantic", "--data-root", self.data_root,
                      "--base", "v0002", "--contract",
                      SEM.SEMANTIC_SCHEMA_VERSION_V3])
        self.assertEqual(rc, 0, "build-semantic --contract cs-20.6 failed")
        tags = sorted(t for t in os.listdir(self.builds_dir()) if t.startswith("v"))
        self.assertIn(expect_tag, tags)
        return os.path.join(self.builds_dir(), expect_tag)

    def read(self, build_dir, name):
        return C.read_jsonl(os.path.join(build_dir, name)) if name.endswith(".jsonl") \
            else C.read_json(os.path.join(build_dir, name))


class TestV301BuildBasics(V3Base):
    def test_v301_version_contract_files(self):
        self.build_corpus()
        v2 = self.build_semantic()
        v3 = self.build_v3()

        corpus3 = self.read(v3, "corpus.json")
        sem = corpus3["semantic"]
        self.assertEqual(sem["schema_version"], "cs-20.6")
        self.assertEqual(sem["mission"], "PCM-20.6 SUBTASK 02")
        self.assertEqual(sem["prev_contract"], "cs-20.5")
        self.assertEqual(sem["base_corpus"]["version"], "v0002")
        self.assertEqual(sem["base_corpus"]["kind"], "corpus")
        self.assertEqual(sem["base_corpus"]["path_rel"], "corpus/builds/v0002")

        man = M.load_manifest(v3)
        names = sorted((man["data"]["files"] or {}).keys())
        self.assertEqual(names, ["context-records.jsonl", "corpus.json",
                                 "heading-records.jsonl",
                                 "hidden-context-records.jsonl", "pages.jsonl"])
        # زنجیره‌ی prev به build معنایی cs-20.5
        prev = man.get("prev") or {}
        self.assertEqual(prev.get("version"), "v0002")
        self.assertEqual(prev.get("kind"), "corpus")
        self.assertEqual(prev.get("path_rel"), "corpus/builds/v0002/manifest.json")

        st = (corpus3.get("stats") or {}).get("semantic") or {}
        self.assertEqual((st.get("hidden_context") or {}).get("heading_record_count"), 4)
        self.assertEqual((st.get("hidden_context") or {}).get("context_record_count"), 3)
        self.assertEqual((st.get("hidden_context") or {}).get("truncated_at_source_count"), 0)

        # بلوک‌های cs-20.5 دست‌نخورده
        self.assertEqual(sem["classification"]["class_counts"].get("SECTION_HEADING"), 3)
        self.assertEqual(sem["context_records"]["count"], 3)
        self.assertEqual(sem["order_key"], SEM.ORDER_KEY)


class TestV302HeadingRecords(V3Base):
    def test_v302_heading_records_and_relations(self):
        self.build_corpus()
        v2 = self.build_semantic()
        v3 = self.build_v3()
        hr = self.read(v3, "heading-records.jsonl")
        pages = self.read(v3, "pages.jsonl")
        by_pid = {p["page_id"]: p for p in pages}

        self.assertEqual(len(hr), 4)
        self.assertEqual([r["page_id"] for r in hr],
                         [P(2), P(3), P(4), P2(10)])

        by_rid = {r["record_id"]: r for r in hr}
        r2 = by_rid["hctx:%s" % P(2)]
        r3 = by_rid["hctx:%s" % P(3)]
        r4 = by_rid["hctx:%s" % P(4)]
        r10 = by_rid["hctx:%s" % P2(10)]

        # idx2 — CHAPTER، اولین عنوان جلد
        self.assertEqual(r2["visibility"], "hidden_context")
        self.assertEqual(r2["record_kind"], "heading")
        self.assertEqual(r2["heading_text"], "سوره بقره")
        self.assertEqual(r2["item_index"], 2)
        self.assertEqual(r2["volume_no"], 1)
        self.assertEqual(r2["volume_id"], "%s__vol001" % ED)
        self.assertEqual(r2["source_class"], "CHAPTER_HEADING")
        self.assertIsNone(r2["parent_heading_page_id"])
        self.assertEqual(r2["children_page_ids"], [])
        self.assertEqual(r2["next_page_id"], P(3))
        p2 = by_pid[P(2)]
        self.assertEqual(r2["provenance"]["source_page_id"], p2["source_page_id"])
        self.assertEqual(r2["provenance"]["content_hash"], p2["content_hash"])
        self.assertEqual(r2["provenance"]["captured_at"], p2["captured_at"])

        # idx4 — parent = idx3، children = idx5..idx8 (تا عنوان بعدی — عنوان بعدی نیست)
        self.assertEqual(r4["parent_heading_page_id"], P(3))
        self.assertEqual(r4["children_page_ids"], [P(5), P(6), P(7), P(8)])
        self.assertEqual(r4["next_page_id"], P(5))

        # idx10 — جلد 2: عنوان قبلی ندارد، پایان جلد
        self.assertEqual(r10["volume_no"], 2)
        self.assertIsNone(r10["parent_heading_page_id"])
        self.assertEqual(r10["children_page_ids"], [])
        self.assertIsNone(r10["next_page_id"])

        # heading_hash قابل بازتولید است
        for r in hr:
            meta = {k: v for k, v in r.items() if k != "heading_hash"}
            self.assertEqual(r["heading_hash"],
                             C.sha256_text(C.canonical_json(meta).decode("utf-8")))

        # لینک از صفحه به رکورد
        self.assertEqual(by_pid[P(4)]["semantic"]["hidden_context"]["heading_record_id"],
                         "hctx:%s" % P(4))
        self.assertIsNone(by_pid[P(5)]["semantic"]["hidden_context"]["heading_record_id"])


class TestV303ContextRecords(V3Base):
    def test_v303_hidden_context_records(self):
        self.build_corpus()
        v2 = self.build_semantic()
        v3 = self.build_v3()
        hc = self.read(v3, "hidden-context-records.jsonl")
        pages = self.read(v3, "pages.jsonl")
        by_pid = {p["page_id"]: p for p in pages}
        ctx5 = self.read(v2, "context-records.jsonl")

        # همان انتخاب/ترتیب cs-20.5 (idx 2، 3، 4 — idx10 آخرِ جلد است)
        self.assertEqual([r["page_id"] for r in hc], [P(2), P(3), P(4)])
        self.assertEqual([r["record_id"] for r in hc],
                         ["hcctx:%s" % p for p in (P(2), P(3), P(4))])
        self.assertEqual([r["page_id"] for r in hc],
                         [r["heading_page_id"] for r in ctx5])

        r = hc[0]
        nxt = by_pid[P(3)]
        self.assertEqual(r["visibility"], "hidden_context")
        self.assertEqual(r["record_kind"], "context")
        self.assertEqual(r["heading_text"], "سوره بقره")
        self.assertEqual(r["item_index"], 2)
        self.assertEqual(r["volume_no"], 1)
        self.assertEqual(r["next_page_id"], P(3))
        self.assertEqual(r["next_item_index"], 3)
        self.assertEqual(r["next_volume_no"], 1)
        # hidden_summary = استخراج verbatim 3 خط از صفحه‌ی بعد
        self.assertEqual(r["hidden_summary"], "1. شأن نزول")
        self.assertEqual(r["summary_lines"], 1)
        self.assertEqual(r["summary_sha256"], C.sha256_text("1. شأن نزول"))
        self.assertEqual(r["summary_meta"], {
            "method": "verbatim-extract/1.0", "model": None,
            "model_version": None, "prompt_version": None, "max_lines": 3})
        # provenance از صفحه‌ی «بعد» (مبدأ خلاصه)
        self.assertEqual(r["provenance"]["source_page_id"], nxt["source_page_id"])
        self.assertEqual(r["provenance"]["content_hash"], nxt["content_hash"])
        self.assertEqual(r["provenance"]["captured_at"], nxt["captured_at"])
        meta = {k: v for k, v in r.items() if k != "context_hash"}
        self.assertEqual(r["context_hash"],
                         C.sha256_text(C.canonical_json(meta).decode("utf-8")))

        # لینک از صفحه‌ی عنوان به رکورد context
        self.assertEqual(by_pid[P(3)]["semantic"]["hidden_context"]["context_record_id"],
                         "hcctx:%s" % P(3))
        self.assertIsNone(by_pid[P2(10)]["semantic"]["hidden_context"]["context_record_id"])

        # سیاست نمایش در corpus
        sem = self.read(v3, "corpus.json")["semantic"]
        self.assertEqual(sem["hidden_context"]["policy"], S.HC_POLICY_TEXT)
        self.assertEqual(sem["hidden_context"]["visibility"], "hidden_context")


class TestV304Immutability(V3Base):
    def test_v304_cs205_parts_untouched(self):
        self.build_corpus()
        v2 = self.build_semantic()
        v3 = self.build_v3()
        pages2 = self.read(v2, "pages.jsonl")
        pages3 = self.read(v3, "pages.jsonl")
        corpus2 = self.read(v2, "corpus.json")
        corpus3 = self.read(v3, "corpus.json")

        self.assertEqual(len(pages2), len(pages3))
        for a, b in zip(pages2, pages3):
            self.assertEqual(a["text"], b["text"])
            self.assertEqual(a["text_normalized"], b["text_normalized"])
            self.assertEqual(a["content_hash"], b["content_hash"])
            self.assertEqual(a["quality_status"], b["quality_status"])
            for f in ("record_class", "class_basis", "class_rule", "order",
                      "next_page_id", "next_item_index"):
                self.assertEqual(a["semantic"].get(f), b["semantic"].get(f),
                                 "cs-20.5 semantic field %r changed" % f)

        sem2 = corpus2["semantic"]
        sem3 = corpus3["semantic"]
        self.assertEqual(sem3["classification"], sem2["classification"])
        self.assertEqual(sem3["order_key"], sem2["order_key"])
        self.assertEqual(sem3["context_records"], sem2["context_records"])

        # context-records.jsonl بایت‌به‌بایت یکسان
        self.assertEqual(C.sha256_file(os.path.join(v2, "context-records.jsonl")),
                         C.sha256_file(os.path.join(v3, "context-records.jsonl")))
        # buildِ v0002 خود دست‌نخورده مانده (فقط‌خواندن)
        man2 = M.load_manifest(v2)
        self.assertEqual(man2["version"], "v0002")
        ok, errors, _ = VAL.validate_corpus(v2)
        self.assertTrue(ok, errors)


class TestV305Truncation(V3Base):
    def _full_chain(self, data_root):
        fx = os.path.join(self.tmp, "full_src")
        os.makedirs(fx, exist_ok=True)
        jl = os.path.join(fx, "tasnim-corpus.jsonl")
        jp = os.path.join(fx, "tasnim-corpus.json")
        sm = os.path.join(fx, "export-summary.json")
        make_full_fixture(jl, jp, sm)
        self.assertEqual(CL.main(["build-corpus", "--jsonl", jl,
                                  "--data-root", data_root]), 0)
        self.assertEqual(CL.main(["build-semantic", "--data-root", data_root,
                                  "--base", "v0001"]), 0)
        self.assertEqual(CL.main(["build-semantic", "--data-root", data_root,
                                  "--base", "v0002", "--contract", "cs-20.6"]), 0)
        return os.path.join(data_root, "corpus", "builds")

    def test_v305_truncation_block_and_v09(self):
        root2 = os.path.join(self.tmp, "root2")
        builds = self._full_chain(root2)
        v1 = os.path.join(builds, "v0001")
        v3 = os.path.join(builds, "v0003")
        pages = C.read_jsonl(os.path.join(v3, "pages.jsonl"))
        corpus3 = C.read_json(os.path.join(v3, "corpus.json"))

        p11 = [p for p in pages if p["item_index"] == 11][0]
        self.assertEqual(len(p11["text"]), 2000)
        self.assertIn(S.F_TRUNCATED_2000, p11["quality_status"]["flags"])
        t = p11["semantic"]["truncation"]
        self.assertTrue(t["truncated_at_source"])
        self.assertEqual(t["source_char_cap"], 2000)
        self.assertEqual(t["gate"], "PCM-20.5 GATE 1.5")
        # سایر صفحات
        for p in pages:
            if p is not p11:
                self.assertFalse(p["semantic"]["truncation"]["truncated_at_source"])

        tb = corpus3["semantic"]["truncation"]
        self.assertEqual(tb["source_char_cap"], 2000)
        self.assertEqual(tb["affected_count"], 1)
        self.assertEqual(tb["affected_pages"], [p11["page_id"]])
        self.assertEqual(tb["evidence"]["sha256"], S.GATE_1_5_EVIDENCE_SHA)
        self.assertEqual(tb["evidence"]["path_rel"], S.GATE_1_5_EVIDENCE_REL)

        # validate: V09 + S10 سبز
        ok, errors, _ = VAL.validate_corpus(v3)
        self.assertTrue(ok, errors)
        ok, serr, _ = SEM.validate_semantic(v3, root2)
        self.assertTrue(ok, serr)

        # V09: خرابی flag → خطا
        recs = C.read_jsonl(os.path.join(v1, "pages.jsonl"))
        q11 = [p for p in recs if p["item_index"] == 11][0]
        q11["quality_status"]["flags"] = []
        with open(os.path.join(v1, "pages.jsonl"), "w", encoding="utf-8",
                  newline="\n") as f:
            for r in recs:
                f.write(C.canonical_json_line(r).decode("utf-8"))
        ok, errors, _ = VAL.validate_corpus(v1)
        self.assertFalse(ok)
        self.assertTrue(any(e.startswith("V09") for e in errors), errors)

    def test_v305b_cap_pileup_warning(self):
        # متن بلندتر از cap → هشدار (نه خطا)
        root3 = os.path.join(self.tmp, "root3")
        builds = self._full_chain(root3)
        v1 = os.path.join(builds, "v0001")
        recs = C.read_jsonl(os.path.join(v1, "pages.jsonl"))
        q11 = [p for p in recs if p["item_index"] == 11][0]
        q11["text"] = "خ" * 2001
        q11["quality_status"]["flags"] = []
        with open(os.path.join(v1, "pages.jsonl"), "w", encoding="utf-8",
                  newline="\n") as f:
            for r in recs:
                f.write(C.canonical_json_line(r).decode("utf-8"))
        ok, errors, warnings = VAL.validate_corpus(v1)
        self.assertTrue(any(w.startswith("V09") and "longer than source cap" in w
                            for w in warnings), (ok, errors, warnings))


class TestV306Corruption(V3Base):
    def test_v306_tampered_summary_fails(self):
        self.build_corpus()
        v2 = self.build_semantic()
        v3 = self.build_v3()
        path = os.path.join(v3, "hidden-context-records.jsonl")
        recs = C.read_jsonl(path)
        recs[0]["hidden_summary"] = "خلاصه‌ی ساختگی و بی‌مورد"
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            for r in recs:
                f.write(C.canonical_json_line(r).decode("utf-8"))
        ok, errors, _ = SEM.validate_semantic(v3, self.data_root)
        self.assertFalse(ok)
        self.assertTrue(any(e.startswith("S09") for e in errors), errors)
        rc = CL.main(["validate-corpus", "--data-root", self.data_root,
                      "--build", "v0003"])
        self.assertEqual(rc, 1)

    def test_v306b_tampered_heading_children_fails(self):
        self.build_corpus()
        v2 = self.build_semantic()
        v3 = self.build_v3()
        path = os.path.join(v3, "heading-records.jsonl")
        recs = C.read_jsonl(path)
        r4 = [r for r in recs if r["page_id"] == P(4)][0]
        r4["children_page_ids"].append(P(9))   # صفحه‌ی جلد 2 — خارج از حوزه
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            for r in recs:
                f.write(C.canonical_json_line(r).decode("utf-8"))
        ok, errors, _ = SEM.validate_semantic(v3, self.data_root)
        self.assertFalse(ok)
        self.assertTrue(any(e.startswith("S09") and "children" in e
                            for e in errors), errors)


class TestV307Idempotency(V3Base):
    def test_v307_reused_no_new_version(self):
        self.build_corpus()
        v2 = self.build_semantic()
        v3 = self.build_v3()
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = CL.main(["build-semantic", "--data-root", self.data_root,
                          "--base", "v0002", "--contract", "cs-20.6"])
        self.assertEqual(rc, 0)
        self.assertIn("REUSED v0003", out.getvalue())
        tags = sorted(t for t in os.listdir(self.builds_dir()) if t.startswith("v"))
        self.assertEqual(tags, ["v0001", "v0002", "v0003"])


class TestV308CLIContract(V3Base):
    def test_v308_optin_errors(self):
        self.build_corpus()
        v2 = self.build_semantic()
        # پیش‌فرض (cs-20.5) روی base معنایی → rc 2 (سازگاری با S11)
        rc = CL.main(["build-semantic", "--data-root", self.data_root,
                      "--base", "v0002"])
        self.assertEqual(rc, 2, "default contract must refuse a semantic base")
        # cs-20.6 روی base غیرمعنایی → rc 2
        rc = CL.main(["build-semantic", "--data-root", self.data_root,
                      "--base", "v0001", "--contract", "cs-20.6"])
        self.assertEqual(rc, 2, "cs-20.6 requires a cs-20.5 semantic base")
        # قرارداد نامعتبر → rc 2 (argparse)
        rc = CL.main(["build-semantic", "--data-root", self.data_root,
                      "--base", "v0002", "--contract", "nope"])
        self.assertEqual(rc, 2)


class TestV309Determinism(V3Base):
    def test_v309_cross_root_same_sha(self):
        # قرارداد قطعی بودن (همان S05/T06): همان فایل ورودی (مسیر یکسان)
        # در دو data_rootِ متفاوت → content_sha256 یکسان.
        self.build_corpus()
        self.build_semantic()
        v3a = self.build_v3()
        man_a = M.load_manifest(v3a)

        root_b = os.path.join(self.tmp, "rootb", "data", "tasnim")
        self.assertEqual(CL.main(["build-corpus", "--jsonl", self.jsonl,
                                  "--data-root", root_b]), 0)
        self.assertEqual(CL.main(["build-semantic", "--data-root", root_b,
                                  "--base", "v0001"]), 0)
        self.assertEqual(CL.main(["build-semantic", "--data-root", root_b,
                                  "--base", "v0002", "--contract", "cs-20.6"]), 0)
        v3b = os.path.join(root_b, "corpus", "builds", "v0003")
        man_b = M.load_manifest(v3b)
        self.assertEqual(man_a["data"]["content_sha256"],
                         man_b["data"]["content_sha256"])

    def test_v309b_ordering_invariant(self):
        # ترتیب فایل باید با مرتب‌سازی (volume_no, item_index, dup_rank, position) یکسان باشد
        self.build_corpus()
        self.build_semantic()
        v3 = self.build_v3()
        pages = self.read(v3, "pages.jsonl")
        keys = []
        for p in pages:
            o = p["semantic"]["order"]
            keys.append((o["volume_no"],
                         o["item_index"] if o["item_index"] is not None else 10**9,
                         o["dup_rank"], o["source_position"]))
        self.assertEqual(keys, sorted(keys))
        for i, p in enumerate(pages):
            self.assertEqual(p["semantic"]["order"]["seq_global"], i)


if __name__ == "__main__":
    unittest.main()

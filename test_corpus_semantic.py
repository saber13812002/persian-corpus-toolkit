# -*- coding: utf-8 -*-
"""test_corpus_semantic.py — PCM-20.5 GATE 1: لایه‌ی معنایی پیکره (S-01..S-11).

اجرا:  python -X utf8 -m unittest test_corpus_semantic -v

فیکستور: 10 رکورد در 2 جلد (section=1 → جلد 1، section=2 → جلد 2) با
صحنه‌های 6 طبقه‌ی معنایی:
    idx 1  متن کامل                  → CONTENT_PAGE   (definitive)
    idx 2  «سوره بقره»               → CHAPTER_HEADING (guessed)
    idx 3  «1. شأن نزول»             → SECTION_HEADING (guessed, numbered)
    idx 4  «تفسیر»                   → SECTION_HEADING (guessed, keyword)
    idx 5  «* * *»                   → UNKNOWN_STRUCTURE (definitive)
    idx 6  «»                        → EMPTY_PAGE     (definitive)
    idx 7  متن کامل                  → CONTENT_PAGE   (definitive)
    idx 8  «این صفحه کوتاه است.» (19)  → SHORT_CONTENT (guessed)
    idx 9  متن کامل (جلد 2)          → CONTENT_PAGE   (definitive)
    idx 10 «مفردات» (پایان جلد)      → SECTION_HEADING (guessed, keyword)

رکوردهای context پنهان: فقط idx 2، 3، 4 (عنوان‌ها با صفحه‌ی بعد در همان
جلد و متن غیرخالی)؛ idx 10 آخر جلد است → context ندارد.
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
from corpus.tasnim import semantic as SEM
from corpus.tasnim import validate as VAL
from corpus.tasnim import versioning as V

from test_corpus_tasnim import fa, page_rec


def make_semantic_fixture(jsonl_path):
    """10 رکورد (2 جلد) — فقط jsonl (بدون json/summary)."""
    texts = {
        1: "متن کامل صفحه‌ی اول با تفسیر و روایت کافی برای آزمون.",
        2: "سوره بقره",
        3: "1. شأن نزول",
        4: "تفسیر",
        5: "* * *",
        6: "",
        7: "متن صفحه‌ی هفت با محتوای کافی برای پیکره‌سازی و آزمون.",
        8: "این صفحه کوتاه است.",
        9: "متن کامل صفحه‌ی اول جلد دوم با روایات متعدد و نقل‌های کافی.",
        10: "مفردات",
    }
    recs = []
    for i in range(1, 11):
        section = 1 if i <= 8 else 2
        recs.append(page_rec(
            i,
            "https://tasnim.hamtaa.org/book/79?section=%d&item_index=%d" % (section, i),
            i, texts[i], fa(i), barg_export=i))
    with open(jsonl_path, "w", encoding="utf-8", newline="\n") as f:
        import json as _json
        for r in recs:
            f.write(_json.dumps(r, ensure_ascii=False) + "\n")
    return len(recs)


class SemanticBase(unittest.TestCase):
    def setUp(self):
        C.force_utf8_stdio()
        self.tmp = tempfile.mkdtemp(prefix="pct-sem-test-")
        self.data_root = os.path.join(self.tmp, "data", "tasnim")
        self.fix = os.path.join(self.tmp, "src")
        os.makedirs(self.fix, exist_ok=True)
        self.jsonl = os.path.join(self.fix, "tasnim-corpus.jsonl")
        self.n_rec = make_semantic_fixture(self.jsonl)

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
        self.assertEqual(sorted(os.listdir(self.builds_dir())), ["v0001"])
        return os.path.join(self.builds_dir(), "v0001")

    def build_semantic(self, expect_tag="v0002"):
        rc = CL.main(["build-semantic", "--data-root", self.data_root,
                      "--base", "v0001"])
        self.assertEqual(rc, 0, "build-semantic failed")
        tags = sorted(t for t in os.listdir(self.builds_dir()) if t.startswith("v"))
        self.assertIn(expect_tag, tags)
        return os.path.join(self.builds_dir(), expect_tag)

    def pages_of(self, build_dir):
        return C.read_jsonl(os.path.join(build_dir, "pages.jsonl"))


class TestS01Classification(SemanticBase):
    def test_s01_classes_and_rules(self):
        self.build_corpus()
        build = self.build_semantic()
        pages = self.pages_of(build)
        by_idx = {p["item_index"]: p for p in pages}
        exp = {
            1: ("CONTENT_PAGE", "definitive", "content: len>=20"),
            2: ("CHAPTER_HEADING", "guessed", "chapter: sura-title-pattern"),
            3: ("SECTION_HEADING", "guessed", "section: numbered"),
            4: ("SECTION_HEADING", "guessed", "section: keyword:تفسیر"),
            5: ("UNKNOWN_STRUCTURE", "definitive", "no-letters"),
            6: ("EMPTY_PAGE", "definitive", "empty: len==0"),
            7: ("CONTENT_PAGE", "definitive", "content: len>=20"),
            8: ("SHORT_CONTENT", "guessed", "short: default"),
            9: ("CONTENT_PAGE", "definitive", "content: len>=20"),
            10: ("SECTION_HEADING", "guessed", "section: keyword:مفردات"),
        }
        for idx, (cls, basis, rule) in exp.items():
            s = by_idx[idx]["semantic"]
            self.assertEqual(s["record_class"], cls, "idx %d class" % idx)
            self.assertEqual(s["class_basis"], basis, "idx %d basis" % idx)
            self.assertEqual(s["class_rule"], rule, "idx %d rule" % idx)
        corpus = C.read_json(os.path.join(build, "corpus.json"))
        cc = corpus["semantic"]["classification"]["class_counts"]
        self.assertEqual(cc, {"CONTENT_PAGE": 3, "CHAPTER_HEADING": 1,
                              "SECTION_HEADING": 3, "SHORT_CONTENT": 1,
                              "EMPTY_PAGE": 1, "UNKNOWN_STRUCTURE": 1})
        self.assertEqual(corpus["semantic"]["classification"]["basis_counts"],
                         {"definitive": 5, "guessed": 5})
        self.assertEqual(corpus["semantic"]["classification"]["rule_set"],
                         "semantic-rules/1.0")
        self.assertEqual(corpus["semantic"]["schema_version"], "cs-20.5")
        self.assertEqual(corpus["semantic"]["base_corpus"]["version"], "v0001")


class TestS02Order(SemanticBase):
    def test_s02_order_block(self):
        self.build_corpus()
        build = self.build_semantic()
        pages = self.pages_of(build)
        self.assertEqual(len(pages), 10)
        by_idx = {p["item_index"]: p for p in pages}
        for i, p in enumerate(pages):
            self.assertEqual(p["semantic"]["order"]["seq_global"], i)
        self.assertEqual(by_idx[1]["semantic"]["order"]["seq_in_volume"], 1)
        self.assertEqual(by_idx[8]["semantic"]["order"]["seq_in_volume"], 8)
        self.assertEqual(by_idx[9]["semantic"]["order"]["seq_in_volume"], 1)
        self.assertEqual(by_idx[10]["semantic"]["order"]["seq_in_volume"], 2)
        self.assertEqual(by_idx[1]["volume"]["volume_no"], 1)
        self.assertEqual(by_idx[9]["volume"]["volume_no"], 2)
        self.assertEqual(by_idx[1]["semantic"]["order"]["source_position"], 0)
        self.assertEqual(by_idx[9]["semantic"]["order"]["source_position"], 8)
        for idx in (8, 10):
            self.assertIsNone(by_idx[idx]["semantic"]["next_page_id"])
            self.assertIsNone(by_idx[idx]["semantic"]["next_item_index"])
        self.assertEqual(by_idx[1]["semantic"]["next_page_id"], by_idx[2]["page_id"])
        self.assertEqual(by_idx[1]["semantic"]["next_item_index"], 2)
        for p in pages:
            o = p["semantic"]["order"]
            self.assertEqual(o["volume_id"], p["volume"]["volume_id"])
            self.assertEqual(o["volume_no"], p["volume"]["volume_no"])
            self.assertEqual(o["item_index"], p["item_index"])
            self.assertEqual(o["dup_rank"], 0)


class TestS03Validation(SemanticBase):
    def test_s03_validate_pass(self):
        self.build_corpus()
        build = self.build_semantic()
        ok, errors, warnings = VAL.validate_corpus(build)
        self.assertTrue(ok, "validate_corpus: %s" % errors)
        ok2, s_errors, s_warnings = SEM.validate_semantic(build, self.data_root)
        self.assertTrue(ok2, "validate_semantic: %s" % s_errors)
        rc = CL.main(["validate-corpus", "--data-root", self.data_root,
                      "--build", "v0002"])
        self.assertEqual(rc, 0)


class TestS04Idempotency(SemanticBase):
    def test_s04_reused_no_new_version(self):
        self.build_corpus()
        self.build_semantic()
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = CL.main(["build-semantic", "--data-root", self.data_root,
                          "--base", "v0001"])
        self.assertEqual(rc, 0)
        self.assertIn("REUSED v0002", out.getvalue())
        self.assertEqual(sorted(os.listdir(self.builds_dir())), ["v0001", "v0002"])


class TestS05CrossRoot(SemanticBase):
    def test_s05_cross_root_same_sha(self):
        self.build_corpus()
        build1 = self.build_semantic()
        m1 = M.load_manifest(build1)
        root2 = os.path.join(self.tmp, "data2", "tasnim")
        rc = CL.main(["build-corpus", "--jsonl", self.jsonl, "--data-root", root2])
        self.assertEqual(rc, 0)
        rc = CL.main(["build-semantic", "--data-root", root2, "--base", "v0001"])
        self.assertEqual(rc, 0)
        m2 = M.load_manifest(os.path.join(root2, "corpus", "builds", "v0002"))
        self.assertEqual(m1["data"]["content_sha256"], m2["data"]["content_sha256"])
        self.assertEqual(
            M.load_manifest(self.builds_dir() + os.sep + "v0001")["data"]["content_sha256"],
            M.load_manifest(os.path.join(root2, "corpus", "builds", "v0001"))
            ["data"]["content_sha256"])


class TestS06SemanticDiff(SemanticBase):
    def test_s06_semantic_diff_counts(self):
        self.build_corpus()
        self.build_semantic()
        rc = CL.main(["semantic-diff", "--data-root", self.data_root,
                      "--from", "v0001", "--to", "v0002"])
        self.assertEqual(rc, 0)
        rep = C.read_json(os.path.join(self.data_root, "reports",
                                       "diff_v0001_v0002", "semantic-change.json"))
        self.assertEqual(rep["kind"], "semantic-change")
        c = rep["counts"]
        self.assertEqual(c["added_pages"], 0)
        self.assertEqual(c["recovered"], 0)
        self.assertEqual(c["changed"], 0)
        self.assertEqual(c["unchanged"], 10)
        self.assertEqual(c["missing_pages"], 0)
        self.assertEqual(c["duplicate_rows"], 0)
        self.assertEqual(c["unresolved_gaps"], 0)
        self.assertEqual(c["context_records_added"], 3)
        self.assertEqual(c["pages_from"], 10)
        self.assertEqual(c["pages_to"], 10)
        self.assertEqual(rep["from"]["tag"], "v0001")
        self.assertEqual(rep["to"]["tag"], "v0002")
        self.assertTrue(rep["from"]["manifest_sha256"])
        self.assertTrue(rep["to"]["manifest_sha256"])


class TestS07ContextRecords(SemanticBase):
    def test_s07_context_verbatim(self):
        self.build_corpus()
        build = self.build_semantic()
        pages = self.pages_of(build)
        ctx = C.read_jsonl(os.path.join(build, "context-records.jsonl"))
        self.assertEqual(len(ctx), 3)
        by_idx = {p["item_index"]: p for p in pages}
        pid2idx = {p["page_id"]: p["item_index"] for p in pages}
        self.assertEqual([pid2idx[r["heading_page_id"]] for r in ctx], [2, 3, 4])
        for r in ctx:
            hp = by_idx[pid2idx[r["heading_page_id"]]]
            self.assertEqual(r["visibility"], "hidden")
            self.assertEqual(r["record_kind"], "context")
            self.assertEqual(r["record_id"], "ctx:%s" % hp["page_id"])
            self.assertEqual(r["heading_text"], hp["text"])
            self.assertEqual(r["context_page_id"], hp["page_id"])
            self.assertEqual(r["context_item_index"], hp["item_index"])
            self.assertEqual(r["source_hash"], hp["content_hash"])
            self.assertEqual(r["next_page_id"], hp["semantic"]["next_page_id"])
            self.assertEqual(r["next_item_index"], hp["semantic"]["next_item_index"])
            np_ = by_idx[r["next_item_index"]]
            self.assertEqual(r["next_source_page_id"], np_["source_page_id"])
            exp_sum, n = SEM.extract_summary(np_["text"])
            self.assertEqual(r["next_page_summary"], exp_sum)
            self.assertEqual(r["summary_lines"], n)
            self.assertEqual(
                r["retrieval_context"],
                "%s — %s — %s" % (hp["text"], hp["volume"]["volume_title"], exp_sum))
            self.assertIn("hidden", r["internal_tags"])
            self.assertIn("heading-context", r["internal_tags"])
            self.assertIn(hp["semantic"]["record_class"], r["internal_tags"])
            self.assertEqual(r["volume_id"], hp["volume"]["volume_id"])
            self.assertEqual(r["volume_title"], hp["volume"]["volume_title"])
            sm = r["summary_meta"]
            self.assertEqual(sm["method"], "verbatim-extract/1.0")
            self.assertIsNone(sm["model"])
            self.assertIsNone(sm["prompt_version"])
            self.assertEqual(sm["max_lines"], 3)
            meta = {k: v for k, v in r.items() if k != "context_hash"}
            self.assertEqual(r["context_hash"],
                             C.sha256_text(C.canonical_json(meta).decode("utf-8")))
        # idx 10 (پایان جلد) عنوان است اما context ندارد
        self.assertNotIn(by_idx[10]["page_id"], [r["heading_page_id"] for r in ctx])


class TestS08BaseImmutability(SemanticBase):
    def test_s08_base_untouched(self):
        base = self.build_corpus()
        base_sha_before = C.sha256_file(os.path.join(base, "manifest.json"))
        self.build_semantic()
        base_pages = self.pages_of(base)
        new_pages = self.pages_of(self.builds_dir() + os.sep + "v0002")
        self.assertEqual(len(base_pages), len(new_pages))
        for b, p in zip(base_pages, new_pages):
            for k, v in b.items():
                self.assertEqual(p.get(k), v, "base field %r changed" % k)
        self.assertEqual(C.sha256_file(os.path.join(base, "manifest.json")), base_sha_before)
        reg = V.read_registry(os.path.join(self.data_root, "manifests"))
        self.assertEqual(reg["chain"]["corpus:v0001"]["sha256"], base_sha_before)


class TestS09ManifestChain(SemanticBase):
    def test_s09_chain_and_gaps(self):
        self.build_corpus()
        build = self.build_semantic()
        m = M.load_manifest(build)
        self.assertEqual(m["kind"], "corpus")
        self.assertEqual(m["version"], "v0002")
        prev = m["prev"]
        self.assertEqual(prev["kind"], "corpus")
        self.assertEqual(prev["version"], "v0001")
        self.assertEqual(prev["path_rel"], "corpus/builds/v0001/manifest.json")
        base_manifest = M.load_manifest(os.path.join(self.builds_dir(), "v0001"))
        self.assertEqual(prev["sha256"],
                         C.sha256_text(C.canonical_json(base_manifest).decode("utf-8")))
        ok, errors, warnings = M.validate_manifest(build, self.data_root)
        self.assertTrue(ok, errors)
        d = m["data"]
        self.assertEqual(d["base"]["version"], "v0001")
        self.assertEqual(d["base"]["path_rel"], "corpus/builds/v0001")
        self.assertEqual(d["base"]["content_sha256"],
                         M.load_manifest(os.path.join(self.builds_dir(), "v0001"))
                         ["data"]["content_sha256"])
        self.assertEqual(sorted(d["files"]),
                         ["context-records.jsonl", "corpus.json", "pages.jsonl"])
        g = d["gaps"]["missing_item_index"]
        self.assertEqual(g["count"], 0)
        self.assertEqual(g["status"], "none")
        self.assertEqual(g["missing_runs"], [])
        reg = V.read_registry(os.path.join(self.data_root, "manifests"))
        self.assertEqual(reg["chain"]["corpus:v0002"]["content_sha256"],
                         d["content_sha256"])
        self.assertEqual(reg["chain"]["corpus:v0002"]["sha256"],
                         C.sha256_file(os.path.join(build, "manifest.json")))


class TestS10Corruption(SemanticBase):
    def test_s10_corrupt_context_fails(self):
        self.build_corpus()
        build = self.build_semantic()
        ctx_path = os.path.join(build, "context-records.jsonl")
        ctx = C.read_jsonl(ctx_path)
        ctx[0]["heading_text"] = "تغییر شده"
        C.write_jsonl(ctx_path, ctx)
        ok, errors, warnings = SEM.validate_semantic(build, self.data_root)
        self.assertFalse(ok)
        self.assertTrue(any(e.startswith("S04") for e in errors), errors)
        rc = CL.main(["validate-corpus", "--data-root", self.data_root,
                      "--build", "v0002"])
        self.assertEqual(rc, 1)


class TestS11CLIContract(SemanticBase):
    def test_s11_cli_errors(self):
        self.build_corpus()
        self.build_semantic()
        rc = CL.main(["build-semantic", "--data-root", self.data_root,
                      "--base", "v0099"])
        self.assertEqual(rc, 2)
        rc = CL.main(["build-semantic", "--data-root", self.data_root,
                      "--base", "v0002"])
        self.assertEqual(rc, 2, "semantic build must not be used as base")
        rc = CL.main(["semantic-diff", "--data-root", self.data_root,
                      "--from", "v0099", "--to", "v0002"])
        self.assertEqual(rc, 2)
        rc = CL.main(["validate-corpus", "--data-root", self.data_root,
                      "--build", "v0002"])
        self.assertEqual(rc, 0)
        rc = CL.main(["validate-corpus", "--data-root", self.data_root,
                      "--build", "v0001"])
        self.assertEqual(rc, 0, "plain corpus build still validates")


if __name__ == "__main__":
    unittest.main()

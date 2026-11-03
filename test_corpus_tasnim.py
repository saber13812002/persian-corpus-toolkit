# -*- coding: utf-8 -*-
"""test_corpus_tasnim.py — PCM-20.3: خط تولید پیکره‌ی تسنیم (T-01..T-10).

اجرا:  python -m unittest test_corpus_tasnim -v

فیکستور: خروجیِ مصنوعیِ کوچکِ PCM-20 (tasnim-corpus.jsonl) با همه‌ی
صحنه‌های واقعی ممیزی PCM-20.2: صفحات کامل/خالی/کوتاه/2000، barg با
فاصله‌های هزارگان (۳۹٬۰۰۵)، جلد از section در URL + از متن + نامشخص،
item_index تکراری، section بدون رقم (جلد 31)، برگِ بدون رقم.

نکته‌ی وفاداری: `barg` سطح‌بالای هر رکورد = خروجی parser باگ‌دار PCM-20
(فقط اولین ریک ارقام). برای رکورد 19 (برگ «۳۹٬۰۰۵») parser باگ‌دار 39
بازمی‌گرداند؛ parser اصلاح‌شده‌ی این خط تولید 39005. این تفاوت دقیقاً
سناریوی «differs_from_export_barg» است.
"""
import json
import os
import shutil
import tempfile
import unittest

from corpus.tasnim import cli as CL
from corpus.tasnim import common as C
from corpus.tasnim import dataset as DS
from corpus.tasnim import dump as DP
from corpus.tasnim import manifest as M
from corpus.tasnim import normalize as N
from corpus.tasnim import reconcile as R
from corpus.tasnim import versioning as V

BARG = "\u0628\u0631\u06af"      # «برگ»
TEXT = "\u0645\u062A\u0646"      # «متن»

FA_DIGITS = {str(i): chr(0x06F0 + i) for i in range(10)}
THOUSANDS_SEP = "\u066c"         # ٬


def fa(n):
    return "".join(FA_DIGITS[c] for c in str(n))


def fa_str(s):
    """حرف‌به‌حرف به رقم فارسی (برای رشته‌های با صفر مثل '005')."""
    return "".join(FA_DIGITS[c] for c in s)


def page_rec(page_id, url, idx, text, barg, content_hash=None, barg_export=None):
    """یک رکورد خروجی PCM-20.

    barg        = مقدار خام values[«برگ»] (string فارسی)
    barg_export = مقدار سطح‌بالای `barg` — خروجی parser باگ‌دار PCM-20
                  (None اگر parser هیچ رقمی پیدا نکرده باشد).
    """
    return {
        "page_id": page_id,
        "url": url,
        "captured_at": "2026-01-01T00:00:00Z",
        "content_hash": content_hash or ("h%04d" % page_id),
        "item_index": idx,
        "barg": barg_export,
        "values": {BARG: barg, TEXT: text, "author": "همتا"},
    }


def make_fixture(jsonl_path, json_path, summary_path):
    """3 جلد (1، 2، 31) + 2 صفحه‌ی نامشخص + رکوردهای ناقص/تکراری (21 رکورد)."""
    recs = []

    # جلد 1 — section در URL (رقم 1) + 6 صفحه
    for i in range(1, 7):
        recs.append(page_rec(
            i,
            "https://tasnim.hamtaa.org/book/79?section=%s&item_index=%d" % (fa(1), i),
            i, "متن صفحه‌ی %s از جلد 1. تفسیر آیه‌ای با ذکر حدیث و نقل." % fa(i),
            fa(i), barg_export=i))

    # جلد 2 — section در URL (رقم 2) + 6 صفحه؛ یکی خالی، یکی کوتاه، یکی 2000
    for i in range(7, 13):
        if i == 9:
            text = ""                       # empty
        elif i == 10:
            text = "کوتاه"                   # short (<20)
        elif i == 11:
            text = "خ" * 2000               # truncated-at-2000 (NOT VERIFIED)
        else:
            text = "متن صفحه‌ی %s از جلد 2. تفسیر با نقل‌ها و روایات متعدد." % fa(i)
        recs.append(page_rec(
            i,
            "https://tasnim.hamtaa.org/book/79?section=%s&item_index=%d" % (fa(2), i),
            i, text, fa(i), barg_export=i))

    # جلد 31 — section بدون رقم («جلد 31» در متن) + 4 صفحه
    for i in range(13, 17):
        recs.append(page_rec(
            i,
            "https://tasnim.hamtaa.org/book/79?section=%s&item_index=%d" % ("\u062C\u0644\u062F%2031", i),
            i, "تفسیر تسنیم جلد 31 — متن صفحه‌ی %s با مصادیق و احکام." % fa(i),
            fa(i), barg_export=i))

    # جلد نامشخص — section بدون رقم (مقدمه) + بدون برچسب جلد در متن (2 صفحه)
    recs.append(page_rec(
        17, "https://tasnim.hamtaa.org/book/79?section=%s&item_index=17" % "\u0645\u0642\u062F\u0645\u0647",
        17, "متن مقدمه‌ای کلی برای نمونه‌برداری اولیه؛ بدون شماره جلد.", fa(17),
        barg_export=17))
    recs.append(page_rec(
        18, "https://tasnim.hamtaa.org/book/79?section=%s&item_index=18" % "\u0645\u0642\u062F\u0645\u0647",
        18, "توضیح تکمیلی مقدمه؛ این رکورد نیز بدون شماره جلد است.", fa(18),
        barg_export=18))

    # barg با فاصله‌ی هزارگان: «۳۹٬۰۰۵» → parser اصلاح‌شده 39005،
    # parser باگ‌دار (سطح‌بالا) 39. (اصلاح PCM-20.2)
    recs.append(page_rec(
        19, "https://tasnim.hamtaa.org/book/79?section=%s&item_index=19" % fa(2),
        19, "متن صفحه‌ی 19 از جلد 2؛ برگ با فاصله‌ی هزارگان در رقم آن.",
        fa(39) + THOUSANDS_SEP + fa_str("005"), barg_export=39))

    # item_index تکراری (دو رکورد با index 5؛ ردیف دوم در واقع از جلد 2 است)
    recs.append(page_rec(
        20, "https://tasnim.hamtaa.org/book/79?section=%s&item_index=5" % fa(2),
        5, "رکوردر تکراریِ item_index=5؛ در واقع یک صفحه‌ی دیگر از جلد 2.",
        fa(5), barg_export=5))

    # برگ بدون رقم (parser هیچ رقمی پیدا نمی‌کند → barg_export None)
    recs.append(page_rec(
        21, "https://tasnim.hamtaa.org/book/79?section=%s&item_index=21" % fa(2),
        21, "متن صفحه‌ی 21 از جلد 2؛ بدون رقمِ برگ در داده‌ی منبع.",
        "\u0648", barg_export=None))

    with open(jsonl_path, "w", encoding="utf-8", newline="\n") as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    with open(json_path, "w", encoding="utf-8", newline="\n") as f:
        f.write('{\n  "corpus": "tasnim fixture",\n  "exported_at_utc": '
                '"2026-01-01T00:00:00Z",\n  "page_count": %d,\n  "project": '
                '{"id": 2, "name": "tasnim-fixture"},\n  "pages": []\n}\n' % len(recs))

    with open(summary_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps({"document_count": len(recs),
                            "files": {jsonl_path.split(os.sep)[-1]: {
                                "sha256": C.sha256_file(jsonl_path),
                                "size_bytes": C.file_size(jsonl_path)}}},
                           ensure_ascii=False, indent=1))
    return len(recs)


class TasnimBase(unittest.TestCase):
    def setUp(self):
        C.force_utf8_stdio()
        self.tmp = tempfile.mkdtemp(prefix="pct-tasnim-test-")
        self.data_root = os.path.join(self.tmp, "data", "tasnim")
        self.fix = os.path.join(self.tmp, "src")
        os.makedirs(self.fix, exist_ok=True)
        self.jsonl = os.path.join(self.fix, "tasnim-corpus.jsonl")
        self.jsone = os.path.join(self.fix, "tasnim-corpus.json")
        self.summary = os.path.join(self.fix, "export-summary.json")
        self.n_rec = make_fixture(self.jsonl, self.jsone, self.summary)

    def tearDown(self):
        # Windows: ensure no open handles
        try:
            shutil.rmtree(self.tmp)
        except Exception:
            pass

    def build_corpus(self):
        rc = CL.main(["build-corpus", "--jsonl", self.jsonl, "--json", self.jsone,
                      "--summary", self.summary, "--data-root", self.data_root])
        self.assertEqual(rc, 0, "build-corpus failed")
        builds = os.path.join(self.data_root, "corpus", "builds")
        tags = [t for t in os.listdir(builds) if t.startswith("v")]
        self.assertEqual(len(tags), 1)
        return os.path.join(builds, tags[0])


class TestT01AuditGate(TasnimBase):
    def test_t01_audit_gate_counters(self):
        rc = CL.main(["audit", "--jsonl", self.jsonl, "--json", self.jsone,
                      "--summary", self.summary, "--data-root", self.data_root])
        self.assertEqual(rc, 0)
        reports = os.path.join(self.data_root, "reports")
        outs = [f for f in os.listdir(reports) if f.startswith("audit-")]
        self.assertEqual(len(outs), 1)
        audit = C.read_json(os.path.join(reports, outs[0]))
        g = audit["gate"]
        # تعاریف PCM-20.2 روی فیکستور 21 رکوردی
        self.assertEqual(g["record_count"], 21)
        self.assertEqual(g["incomplete_empty"], 1)
        self.assertEqual(g["short_lt_20"], 1)
        self.assertEqual(g["truncated_at_2000"], 1)
        self.assertEqual(g["no_barg"], 1)
        self.assertEqual(g["missing_item_index"], 0)
        # barg reparse: 39005 درست پارس شده (1 رکورد بدون رقم → 20 با barg)
        self.assertEqual(g["barg_reparse"]["with_parsed_barg"], 20)
        # فقط رکورد 19 (باگ هزارگان) parse اصلاح‌شده‌اش با خروجی باگ‌دار فرق دارد
        self.assertEqual(g["barg_reparse"]["differs_from_export_barg"], 1)
        # item_index: 5 تکراری (2 رکورد با 5) — min=1 max=21
        self.assertEqual(g["item_index"]["min"], 1)
        self.assertEqual(g["item_index"]["max"], 21)
        self.assertEqual(g["duplicate_item_index"]["value_count"], 1)
        self.assertEqual(g["duplicate_item_index"]["extra_rows"], 1)
        # volumes: 2 رکورد نامشخص (مقدمه)
        self.assertEqual(g["volume_strategy_census"]["none"], 2)


class TestT02CanonicalCorpus(TasnimBase):
    def test_t02_structure_and_ids(self):
        build = self.build_corpus()
        corpus = C.read_json(os.path.join(build, "corpus.json"))
        pages = C.read_jsonl(os.path.join(build, "pages.jsonl"))
        self.assertEqual(corpus["stats"]["page_count"], 21)
        self.assertEqual(len(pages), 21)
        # 4 جلد: 1، 2، 31، نامشخص
        vnos = sorted([v["volume_no"] for v in corpus["volumes"] if v["volume_no"] is not None])
        self.assertEqual(vnos, [1, 2, 31])
        unknown = [v for v in corpus["volumes"] if v["volume_no"] is None]
        self.assertEqual(len(unknown), 1)
        self.assertEqual(unknown[0]["page_count"], 2)
        # page_id قطعی: <volume>__p<idx> و تکراری __d1
        pids = {p["page_id"] for p in pages}
        self.assertEqual(len(pids), 21)
        dup = [p for p in pages if p["item_index"] == 5]
        self.assertEqual(len(dup), 2)
        self.assertTrue(any("__d1" in p["page_id"] for p in dup))
        # provenance: source_page_id برای همه
        self.assertTrue(all(p["source_page_id"] for p in pages))
        # RAW/NORMALIZED جدا: یک رکورد empty دارد
        empty = [p for p in pages if p["quality_status"]["flags"]]
        self.assertTrue(any("empty" == f for p in empty for f in p["quality_status"]["flags"]))
        # barg 39005 (parse اصلاح‌شده)
        p19 = [p for p in pages if p["item_index"] == 19][0]
        self.assertEqual(p19["barg"], 39005)

    def test_t02b_flags_not_deletes(self):
        build = self.build_corpus()
        pages = C.read_jsonl(os.path.join(build, "pages.jsonl"))
        self.assertEqual(len(pages), self.n_rec)  # هیچ رکوردی حذف نشده
        corpus = C.read_json(os.path.join(build, "corpus.json"))
        qf = corpus["stats"]["quality_flag_counts"]
        # 6 رکورد flag دارد: 5&20 (dup)، 9 (empty)، 10 (short)، 11 (2000)، 21 (no_barg)
        self.assertEqual(qf["empty"], 1)
        self.assertEqual(qf["short"], 1)
        self.assertEqual(qf["truncated_at_2000"], 1)
        self.assertEqual(qf["no_barg"], 1)
        self.assertEqual(qf["dup_item_index"], 2)
        self.assertEqual(qf["ok"], 21 - 6)


class TestT03Validation(TasnimBase):
    def test_t03_validate_pass(self):
        build = self.build_corpus()
        from corpus.tasnim import validate as VAL
        ok, errors, warnings = VAL.validate_corpus(build)
        self.assertTrue(ok, errors)
        self.assertEqual(errors, [])

    def test_t03b_validate_catches_corruption(self):
        build = self.build_corpus()
        # تخریب pages.jsonl: تغییر text بدون به‌روزرسانی norm
        pp = os.path.join(build, "pages.jsonl")
        lines = open(pp, encoding="utf-8").read().splitlines()
        rec = json.loads(lines[0])
        rec["text_normalized"] = "تخریب‌شده"
        lines[0] = json.dumps(rec, ensure_ascii=False)
        open(pp, "w", encoding="utf-8").write("\n".join(lines) + "\n")
        from corpus.tasnim import validate as VAL
        ok, errors, _ = VAL.validate_corpus(build)
        self.assertFalse(ok)
        self.assertTrue(any(e.startswith("V06") for e in errors))


class TestT04Datasets(TasnimBase):
    def _build_all(self):
        self.build_corpus()
        builds = os.path.join(self.data_root, "corpus", "builds")
        tag = [t for t in os.listdir(builds) if t.startswith("v")][0]
        for pct in (1, 10, 50, 90, 100):
            rc = CL.main(["build-dataset", "--data-root", self.data_root,
                          "--corpus", tag, "--percentage", str(pct)])
            self.assertEqual(rc, 0, "dataset %d%% failed" % pct)
        return tag

    def test_t04_counts_and_continuity(self):
        tag = self._build_all()
        corpus_pages = C.read_jsonl(os.path.join(
            self.data_root, "corpus", "builds", tag, "pages.jsonl"))
        for pct in (1, 10, 50, 90, 100):
            ddir = os.path.join(self.data_root, "datasets", V.pct_dirname(pct))
            dtag = [t for t in os.listdir(ddir) if t.startswith("v")][0]
            ds_pages = C.read_jsonl(os.path.join(ddir, dtag, "pages.jsonl"))
            meta = C.read_json(os.path.join(ddir, dtag, "dataset.json"))
            expected = int(round(len(corpus_pages) * pct / 100.0))
            if pct >= 100:
                self.assertEqual(len(ds_pages), len(corpus_pages))
            else:
                self.assertEqual(len(ds_pages), expected)
            # پیوستگی: درون هر جلد، صفحات انتخابی باید بلوک‌های متوالی باشند
            by_vol = {}
            for p in ds_pages:
                by_vol.setdefault(p["volume_id"], []).append(p)
            for vid, recs in by_vol.items():
                order = {p["page_id"]: i for i, p in
                         enumerate([x for x in corpus_pages if x["volume_id"] == vid])}
                idxs = sorted(order[p["page_id"]] for p in recs)
                runs = []
                prev = None
                for i in idxs:
                    if prev is None or i != prev + 1:
                        runs.append([i, i])
                    else:
                        runs[-1][1] = i
                    prev = i
                self.assertLessEqual(len(runs), 5, "volume %s has >5 fragments" % vid)
            # subset check
            corpus_ids = {p["page_id"] for p in corpus_pages}
            self.assertTrue(all(p["page_id"] in corpus_ids for p in ds_pages))
            self.assertEqual(meta["stats"]["selected_page_count"], len(ds_pages))

    def test_t04b_single_volume(self):
        tag = self._build_all()
        rc = CL.main(["build-dataset", "--data-root", self.data_root,
                      "--corpus", tag, "--percentage", "50", "--volume", "2"])
        self.assertEqual(rc, 0)
        ddir = os.path.join(self.data_root, "datasets", "50pct")
        tags = sorted([t for t in os.listdir(ddir) if t.startswith("v")])
        v2 = C.read_jsonl(os.path.join(ddir, tags[-1], "pages.jsonl"))
        self.assertTrue(all(p["volume"]["volume_no"] == 2 for p in v2))


class TestT05Idempotency(TasnimBase):
    def test_t05_reused_no_new_version(self):
        self.build_corpus()
        rc2 = CL.main(["build-corpus", "--jsonl", self.jsonl, "--json", self.jsone,
                       "--summary", self.summary, "--data-root", self.data_root])
        self.assertEqual(rc2, 0)
        builds = os.path.join(self.data_root, "corpus", "builds")
        self.assertEqual(len([t for t in os.listdir(builds) if t.startswith("v")]), 1)
        out2 = __import__("io").StringIO()
        import contextlib
        with contextlib.redirect_stdout(out2):
            rc3 = CL.main(["build-corpus", "--jsonl", self.jsonl, "--json", self.jsone,
                           "--summary", self.summary, "--data-root", self.data_root])
        self.assertEqual(rc3, 0)
        self.assertIn("REUSED", out2.getvalue())
        self.assertEqual(len([t for t in os.listdir(builds) if t.startswith("v")]), 1)
        # dataset idempotent
        builds = os.path.join(self.data_root, "corpus", "builds")
        tag = [t for t in os.listdir(builds) if t.startswith("v")][0]
        with contextlib.redirect_stdout(out2):
            CL.main(["build-dataset", "--data-root", self.data_root, "--corpus", tag,
                     "--percentage", "10"])
            out_first = out2.getvalue()
            out2.truncate(0); out2.seek(0)
            CL.main(["build-dataset", "--data-root", self.data_root, "--corpus", tag,
                     "--percentage", "10"])
        self.assertIn("REUSED", out2.getvalue())


class TestT06Determinism(TasnimBase):
    def test_t06_same_input_same_sha(self):
        b1 = self.build_corpus()
        sha1 = C.read_json(os.path.join(b1, "manifest.json"))["data"]["content_sha256"]
        # data_root دوم → همان خروجی
        root2 = os.path.join(self.tmp, "data2", "tasnim")
        rc = CL.main(["build-corpus", "--jsonl", self.jsonl, "--json", self.jsone,
                      "--summary", self.summary, "--data-root", root2])
        self.assertEqual(rc, 0)
        b2 = os.path.join(root2, "corpus", "builds", "v0001")
        sha2 = C.read_json(os.path.join(b2, "manifest.json"))["data"]["content_sha256"]
        self.assertEqual(sha1, sha2)
        # انتخاب دیتاست هم قطعی
        for root, tag in ((self.data_root, "v0001"), (root2, "v0001")):
            CL.main(["build-dataset", "--data-root", root, "--corpus", tag, "--percentage", "50"])
        d1 = C.read_jsonl(os.path.join(self.data_root, "datasets", "50pct", "v0001", "pages.jsonl"))
        d2 = C.read_jsonl(os.path.join(root2, "datasets", "50pct", "v0001", "pages.jsonl"))
        self.assertEqual([p["page_id"] for p in d1], [p["page_id"] for p in d2])


class TestT07DumpAdapter(TasnimBase):
    def test_t07_books_and_compat(self):
        self.build_corpus()
        builds = os.path.join(self.data_root, "corpus", "builds")
        tag = [t for t in os.listdir(builds) if t.startswith("v")][0]
        CL.main(["build-dataset", "--data-root", self.data_root, "--corpus", tag,
                 "--percentage", "100"])
        rc = CL.main(["export-dump", "--data-root", self.data_root,
                      "--dataset", "v0001", "--percentage", "100"])
        self.assertEqual(rc, 0)
        ddir = os.path.join(self.data_root, "dumps", "100pct", "v0001")
        books = C.read_json(os.path.join(ddir, "books.json"))
        cfg = C.read_json(os.path.join(ddir, "product.json"))
        check = C.read_json(os.path.join(ddir, "dump-check.json"))
        # 4 کتاب (جلد 1، 2، 31، نامشخص)
        self.assertEqual(len(books), 4)
        self.assertTrue(all(b["dap_code"].startswith("tasnim__vol") for b in books))
        # provenance در همه‌ی صفحات
        for b in books:
            for pg in b["pages"]:
                self.assertIn("page_id", pg)
                self.assertIn("content_hash", pg)
                self.assertIn("source_page_id", pg)
        # compat: فیلدهای REQUIRED OK، بدون error
        self.assertTrue(check["required_fields_ok"], check["errors"])
        self.assertEqual(check["errors"], [])
        self.assertEqual(check["pages_total"], 21)
        # skipped: empty + short (2 رکورد زیر min_text_chars)
        self.assertEqual(check["skipped_short_lt_min_text_chars"], 2)
        # product بدون رمز
        self.assertIsNone(cfg["litellm_key"])


class TestT08Diff(TasnimBase):
    def _two_sources(self):
        """منبعِ دوم: یک صفحه حذف، یک صفحه تغییر، یک صفحه جدید."""
        recs = R.load_source(self.jsonl)["pages"]
        new = os.path.join(self.fix, "v2.jsonl")
        with open(new, "w", encoding="utf-8", newline="\n") as f:
            for p in recs:
                if p["page_id"] == 6:
                    continue  # removed_from_source
                if p["page_id"] == 8:
                    p = dict(p)
                    p["values"] = dict(p["values"])
                    p["values"][TEXT] = "متن تغییریافته‌ی صفحه‌ی 8 با محتوای جدید."
                    p["content_hash"] = "hXXXX"
                f.write(json.dumps(p, ensure_ascii=False) + "\n")
            f.write(json.dumps(page_rec(
                99, "https://tasnim.hamtaa.org/book/79?section=%s&item_index=99" % fa(2),
                99, "صفحه‌ی کاملاً جدید از جلد 2 با متن تازه.", fa(99),
                barg_export=99),
                ensure_ascii=False) + "\n")
        return new

    def test_t08_change_manifest(self):
        self.build_corpus()
        v2 = self._two_sources()
        # v2 را در همان data_root بسازیم (content متفاوت → نسخه‌ی دوم)
        rc = CL.main(["build-corpus", "--jsonl", v2, "--data-root", self.data_root])
        self.assertEqual(rc, 0)
        builds = os.path.join(self.data_root, "corpus", "builds")
        tags = sorted(t for t in os.listdir(builds) if t.startswith("v"))
        self.assertEqual(tags, ["v0001", "v0002"])
        rc = CL.main(["diff", "--data-root", self.data_root, "--from", "v0001", "--to", "v0002"])
        self.assertEqual(rc, 0)
        ch = C.read_json(os.path.join(self.data_root, "reports",
                                      "diff_v0001_v0002", "change-manifest.json"))
        c = ch["counts"]
        self.assertEqual(c["removed_from_source"], 1)
        self.assertEqual(c["changed"], 1)
        self.assertEqual(c["added"], 1)
        self.assertEqual(c["to_pages"], self.n_rec - 1 + 1)  # 21-1+1=21


class TestT09Versioning(TasnimBase):
    def test_t09_chain_and_registry(self):
        self.build_corpus()
        builds = os.path.join(self.data_root, "corpus", "builds")
        tag = [t for t in os.listdir(builds) if t.startswith("v")][0]
        m = M.load_manifest(os.path.join(builds, tag))
        # prev باید source-snapshot باشد و موجود باشد
        self.assertIn("prev", m)
        self.assertEqual(m["prev"]["kind"], "source-snapshot")
        # رگرسیون: path_rel نباید دو بار manifest.json بگیرد و باید روی دیسک باشد
        self.assertFalse(m["prev"]["path_rel"].endswith("manifest.json/manifest.json"))
        prev_path = os.path.join(self.data_root,
                                 m["prev"]["path_rel"].replace("/", os.sep))
        self.assertTrue(os.path.exists(prev_path))
        # زنجیره: dataset → corpus
        CL.main(["build-dataset", "--data-root", self.data_root, "--corpus", tag,
                 "--percentage", "10"])
        ddir = os.path.join(self.data_root, "datasets", "10pct", "v0001")
        dm = M.load_manifest(ddir)
        self.assertEqual(dm["prev"]["kind"], "corpus")
        self.assertFalse(dm["prev"]["path_rel"].endswith("manifest.json/manifest.json"))
        self.assertTrue(os.path.exists(
            os.path.join(self.data_root, dm["prev"]["path_rel"].replace("/", os.sep))))
        # validate: همه‌ی زنجیره بازتأیید می‌شود
        ok, errors, _ = M.validate_manifest(ddir, self.data_root)
        self.assertTrue(ok, errors)
        # registry دارد زنجیره را نگه می‌دارد
        reg = V.read_registry(os.path.join(self.data_root, "manifests"))
        self.assertIn("corpus:%s" % tag, reg["chain"])
        self.assertIn("source-snapshot:%s" % m["prev"]["version"], reg["chain"])

    def test_t09b_versions_never_overwritten(self):
        self.build_corpus()
        # source جدید → نسخه‌ی دوم پیکره (همیشه افزایشی)
        new = os.path.join(self.fix, "v3.jsonl")
        recs = R.load_source(self.jsonl)["pages"]
        with open(new, "w", encoding="utf-8", newline="\n") as f:
            for p in recs:
                f.write(json.dumps(p, ensure_ascii=False) + "\n")
            f.write(json.dumps(page_rec(
                100, "https://tasnim.hamtaa.org/book/79?section=%s&item_index=100" % fa(1),
                100, "یک صفحه‌ی تازه برای نسخه‌ی دوم.", fa(100),
                barg_export=100), ensure_ascii=False) + "\n")
        rc = CL.main(["build-corpus", "--jsonl", new, "--data-root", self.data_root])
        self.assertEqual(rc, 0)
        builds = os.path.join(self.data_root, "corpus", "builds")
        tags = sorted(t for t in os.listdir(builds) if t.startswith("v"))
        self.assertEqual(tags, ["v0001", "v0002"])
        # هر دو هنوز موجود (immutable)
        self.assertTrue(os.path.exists(os.path.join(builds, "v0001", "pages.jsonl")))
        self.assertTrue(os.path.exists(os.path.join(builds, "v0002", "pages.jsonl")))


class TestT10CLIContract(TasnimBase):
    def test_t10_help_and_errors(self):
        import io as _io, contextlib
        out = _io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = CL.main(["--help"])
        self.assertEqual(rc, 0)
        self.assertIn("build-corpus", out.getvalue())
        rc = CL.main(["build-corpus", "--jsonl", os.path.join(self.tmp, "nope.jsonl"),
                      "--data-root", self.data_root])
        self.assertEqual(rc, 2)
        rc = CL.main(["build-dataset", "--data-root", self.data_root, "--corpus", "v9999",
                      "--percentage", "10"])
        self.assertEqual(rc, 2)
        rc = CL.main(["audit", "--jsonl", os.path.join(self.tmp, "nope.jsonl")])
        self.assertEqual(rc, 2)
        # percentage نامعتبر
        self.build_corpus()
        builds = os.path.join(self.data_root, "corpus", "builds")
        tag = [t for t in os.listdir(builds) if t.startswith("v")][0]
        rc = CL.main(["build-dataset", "--data-root", self.data_root, "--corpus", tag,
                      "--percentage", "33"])
        self.assertEqual(rc, 2)

    def test_t10b_even_blocks_properties(self):
        for count, target, blocks in [(1000, 100, 5), (333, 33, 5), (100, 10, 5),
                                      (500, 250, 5), (500, 499, 5), (100, 50, 5),
                                      (20, 2, 5), (100, 99, 5), (10, 3, 5)]:
            s = DS.even_spaced_indexes(count, target, blocks)
            self.assertEqual(len(s), target, (count, target))
            self.assertTrue(all(0 <= i < count for i in s))
            # continuity: بلوک‌های متوالی (حداکثر `blocks` بلوک، یا کمتر)
            runs = 0
            prev = None
            for i in sorted(s):
                if prev is None or i != prev + 1:
                    runs += 1
                prev = i
            self.assertLessEqual(runs, max(1, blocks), (count, target, runs))
        # exact counts
        self.assertEqual(len(DS.even_spaced_indexes(1000, 100, 5)), 100)
        self.assertEqual(len(DS.even_spaced_indexes(100, 99, 5)), 99)

    def test_t10c_barg_reparse_fixed(self):
        # «۳۹٬۰۰۵» (با فاصله‌ی هزارگان + صفر) → 39005 — اصلاح PCM-20.2
        self.assertEqual(C.parse_barg_all_runs(fa(39) + THOUSANDS_SEP + fa_str("005")), 39005)
        self.assertEqual(C.parse_barg_all_runs("1,024"), 1024)
        self.assertEqual(C.parse_barg_all_runs("1000"), 1000)
        self.assertIsNone(C.parse_barg_all_runs("\u0648"))
        self.assertIsNone(C.parse_barg_all_runs(None))
        self.assertEqual(C.parse_barg_all_runs(fa(12)), 12)


if __name__ == "__main__":
    unittest.main(verbosity=2)

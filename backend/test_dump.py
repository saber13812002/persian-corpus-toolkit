# -*- coding: utf-8 -*-
"""test_dump — آزمون‌های پذیرش قرارداد Dump (PCM-14C.3، D01..D15).

مستقل از pct_test_support: dump تابع خالص و فقط‌خوانده از خروجی Word
Factory است (filesystem موقت + python-docx؛ بدون DB/Flask/ES/شبکه).

D01 ساخت Dump از DOCX فارسی معتبر
D02 اعتبارسنجی ساختار Dump (فایل‌ها + فیلدهای قرارداد)
D03 SHA-256 ورودی و خروجی‌ها (ثبت‌شده + بازمحاسبه)
D04 رد Dump ناقص/مربوطه (تغییر hash / حذف فایل)
D05 تکرارپذیری: همان ورودی دوبار → خروجی ساختاری/بایتی پایدار
D06 حفظ RAW + مطابقی NORMALIZED با سیاست ثبت‌شده (پیش‌فرض + سفارشی)
D07 ترتیب قطعی بلوک‌ها + block_id یکتا
D08 سند خالی / خروجی WF ناقص / blocks.jsonl خراب
D09 بازسازی و اعتبارسنجی بدون ES (فقط فایل‌های خود Dump)
D10 idempotency: ساخت دوباره Dump → بدون خروجی تکراری
D11 سازگاری با خروجی WF با مانیفست m-1 (سیاست ثبت‌نشده)
D12 عدم اتصال به DB عملیاتی / import ماژول‌های production (AST guard)
D13 چرخه‌های تکراری در-process (process→dump→validate ×۳)
D14 نمونه JSON سند قرارداد = همان ساختار خروجی واقعی
D15 CLI: make-dump / validate-dump / رفتار legacy بدون تغییر
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from factory import (DocumentProcessingService, NormalizationPolicy,
                     PersianNormalizer, sha256_file, content_hash,
                     generate_dump, validate_dump, dump_summary, DumpError)
from factory.dump import CANONICAL_FILES, DUMP_VERSION
from factory._smoke_fixtures import (make_broken_docx, make_docx,
                                     make_sample_book)

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS_CONTRACT = os.path.join(REPO_ROOT, "docs", "PCM-14C.3-DUMP-CONTRACT.md")
BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))

#: فیلدهای ناپایدار زمان‌بندی (مستند در قرارداد — جزو determinism نیستند)
_VOLATILE = ("started_at", "finished_at", "duration_ms", "created_at",
             "generated_at")


def _sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _read(p: str) -> bytes:
    with open(p, "rb") as f:
        return f.read()


#: فایل‌هایی که محتوایشان بین دو اجرا timestamp دارد (قرارداد §5)
_VOLATILE_CONTENT = {"manifest.json", "document.json", "report.md"}


def _strip_dump_volatile(obj):
    """مثل _strip_volatile + hash/size فایل‌های دارای timestamp."""
    obj = _strip_volatile(obj)
    if isinstance(obj, dict) and isinstance(obj.get("files"), list):
        for e in obj["files"]:
            if e.get("name") in _VOLATILE_CONTENT:
                e.pop("sha256", None)
                e.pop("size_bytes", None)
    return obj


def _strip_wf_manifest(m):
    """مانیفست WF: hash دو فایل ناپایدار (document=created_at،
    report_md=footer) هم ناپایدارند؛ برای مقایسه‌ی ساختاری حذف می‌شوند."""
    m = _strip_volatile(m)
    outs = m.get("outputs")
    if isinstance(outs, dict):
        for k in ("document", "report_md"):
            if isinstance(outs.get(k), dict):
                outs[k].pop("sha256", None)
    return m


def _read_jsonl(p: str) -> list[dict]:
    with open(p, encoding="utf-8") as f:
        return [json.loads(l) for l in f.read().splitlines() if l.strip()]


#: فیلدهای مسیری (وابسته به محل اجرای WF — جزو determinism نیستند)
_PATH_KEYS = ("path",)


def _strip_volatile(obj):
    """حذف فیلدهای زمان‌بندی/مسیری برای مقایسه‌ی ساختاری."""
    if isinstance(obj, dict):
        return {k: _strip_volatile(v) for k, v in obj.items()
                if k not in _VOLATILE and k not in _PATH_KEYS}
    if isinstance(obj, list):
        return [_strip_volatile(x) for x in obj]
    return obj


class DumpBase(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="dump_test_")
        self.out = os.path.join(self.dir, "out")

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def run_wf(self, src: str, **kw) -> str:
        """پردازش src با WF → برگشت دایرکتوری خروجی WF."""
        doc = DocumentProcessingService(out_dir=self.out, **kw).process(src)
        return os.path.join(self.out, doc.file.file_id)

    def dump(self, wf_dir: str, name="dump", **kw) -> str:
        d = os.path.join(self.dir, name)
        generate_dump(wf_dir, d, **kw)
        return d

    @staticmethod
    def load(p: str):
        with open(p, encoding="utf-8") as f:
            return json.load(f)


class TestD01_Generate(DumpBase):
    """D01: ساخت Dump از خروجی WF برای یک DOCX فارسی معتبر."""

    def test_d01_generate(self):
        src = make_sample_book(os.path.join(self.dir, "book.docx"))
        wf = self.run_wf(src)
        d = self.dump(wf)
        dm = self.load(os.path.join(d, "dump-manifest.json"))
        self.assertEqual(dm["dump_contract_version"], DUMP_VERSION)
        self.assertEqual(dm["generator"], "word-factory/0.1")
        self.assertEqual(dm["source"]["kind"], "word-factory-run")
        self.assertEqual(dm["source"]["input_file"]["sha256_source"], "manifest")
        for name in CANONICAL_FILES:
            self.assertTrue(os.path.isfile(os.path.join(d, name)), name)
        self.assertEqual(len(dm["files"]), len(CANONICAL_FILES))
        self.assertTrue(dm["counts"]["blocks"] > 0)
        self.assertTrue(dm["identifiers"]["file_id"].startswith("f-"))
        self.assertTrue(dm["identifiers"]["work_id"].startswith("w-"))
        self.assertTrue(dm["identifiers"]["edition_id"].startswith("e-"))
        self.assertEqual(dm["document"]["language"], "fa")
        # نسخه‌ها: m-2 + norm_policy ثبت‌شده
        self.assertEqual(dm["versions"]["manifest"], "m-2")
        self.assertIsInstance(dm["versions"]["normalizer_policy"], dict)
        self.assertEqual(dm["versions"]["normalizer_policy"]["version"], "n-1")
        self.assertEqual(dm["integrity"]["file_hashes_verified"], True)


class TestD02_Structure(DumpBase):
    """D02: اعتبارسنجی ساختار Dump (V1..V11)."""

    def _setup(self):
        src = make_sample_book(os.path.join(self.dir, "b.docx"))
        return self.dump(self.run_wf(src))

    def test_d02a_all_files_present(self):
        d = self._setup()
        ok, errors, warnings = validate_dump(d)
        self.assertTrue(ok, errors)
        self.assertEqual(sorted(os.listdir(d)),
                         sorted(list(CANONICAL_FILES) + ["dump-manifest.json"]))

    def test_d02b_contract_fields(self):
        dm = self.load(os.path.join(self._setup(), "dump-manifest.json"))
        for top in ("dump_contract_version", "generated_at", "generator",
                    "source", "identifiers", "document", "versions",
                    "files", "counts", "quality", "integrity"):
            self.assertIn(top, dm, f"فیلد بالای قرارداد: {top}")
        for e in dm["files"]:
            for k in ("name", "sha256", "size_bytes", "encoding", "format"):
                self.assertIn(k, e, f"فیلد files[]: {k}")
            self.assertEqual(e["encoding"], "utf-8")
        lc = next(e for e in dm["files"] if e["name"] == "blocks.jsonl")
        self.assertEqual(lc["format"], "jsonl")
        self.assertEqual(lc["line_count"], dm["counts"]["blocks"])
        for fmt, name in (("json", "manifest.json"), ("markdown", "report.md")):
            self.assertEqual(next(e for e in dm["files"]
                                   if e["name"] == name)["format"], fmt)

    def test_d02c_recorded_hashes_recompute(self):
        d = self._setup()
        dm = self.load(os.path.join(d, "dump-manifest.json"))
        for e in dm["files"]:
            p = os.path.join(d, e["name"])
            self.assertEqual(_sha256_bytes(_read(p)), e["sha256"], e["name"])
            self.assertEqual(os.path.getsize(p), e["size_bytes"], e["name"])


class TestD03_Hashes(DumpBase):
    """D03: SHA-256 ورودی و خروجی‌ها."""

    def test_d03a_output_hashes(self):
        src = make_sample_book(os.path.join(self.dir, "h.docx"))
        wf = self.run_wf(src)
        d = self.dump(wf)
        dm = self.load(os.path.join(d, "dump-manifest.json"))
        # hash ثبت‌شده هر خروجی WF با hash واقعی فایل در Dump می‌خواند
        m = self.load(os.path.join(d, "manifest.json"))
        for out_name, info in m["outputs"].items():
            self.assertTrue(info["sha256"])
            self.assertEqual(len(info["sha256"]), 64)
        self.assertEqual(dm["integrity"]["input_sha256"],
                         m["file"]["sha256"])

    def test_d03b_input_rehash(self):
        src = make_sample_book(os.path.join(self.dir, "r.docx"))
        wf = self.run_wf(src)
        d = self.dump(wf, source_docx=src)
        dm = self.load(os.path.join(d, "dump-manifest.json"))
        self.assertEqual(dm["source"]["input_file"]["sha256_source"], "rehashed")
        self.assertEqual(dm["integrity"]["input_sha256"], sha256_file(src))
        # فایل اصلی دست‌نخورده باقی مانده
        self.assertEqual(dm["source"]["input_file"]["sha256"], sha256_file(src))
        # docx دیگری → جفت‌شدگی غلط → DumpError
        other = make_docx(os.path.join(self.dir, "other.docx"),
                          [("Normal", "متن دیگری به‌کلی.")])
        with self.assertRaises(DumpError):
            generate_dump(wf, os.path.join(self.dir, "bad"),
                          source_docx=other)


class TestD04_Reject(DumpBase):
    """D04: رد Dump ناقص / تahrif‌شده (hash غلط / فایل گم)."""

    def _setup(self):
        src = make_sample_book(os.path.join(self.dir, "t.docx"))
        return self.dump(self.run_wf(src))

    def test_d04a_tampered_blocks(self):
        d = self._setup()
        p = os.path.join(d, "blocks.jsonl")
        data = _read(p).decode("utf-8")
        with open(p, "w", encoding="utf-8") as f:
            f.write(data + "تغییر")  # hash ثبت‌شده دیگر نمی‌خواند
        ok, errors, _ = validate_dump(d)
        self.assertFalse(ok)
        self.assertIn("sha256_mismatch:blocks.jsonl", errors)
        self.assertIn("size_mismatch:blocks.jsonl", errors)

    def test_d04b_missing_file(self):
        d = self._setup()
        os.remove(os.path.join(d, "quality-report.json"))
        ok, errors, _ = validate_dump(d)
        self.assertFalse(ok)
        self.assertIn("file_missing:quality-report.json", errors)


class TestD05_Repeatability(DumpBase):
    """D05: همان ورودی دوبار → خروجی پایدار (ساختاری + بایتی)."""

    def test_d05a_two_wf_runs(self):
        src = make_sample_book(os.path.join(self.dir, "p.docx"))
        out1 = os.path.join(self.out, "f1")
        doc1 = DocumentProcessingService(out_dir=out1).process(src)
        out2 = os.path.join(self.out, "f2")
        doc2 = DocumentProcessingService(out_dir=out2).process(src)
        d1 = self.dump(os.path.join(out1, doc1.file.file_id), "d1")
        d2 = self.dump(os.path.join(out2, doc2.file.file_id), "d2")
        # فایل‌های بایتی‌پایدار (مستند در قرارداد)
        for name in ("blocks.jsonl", "quality-report.json"):
            self.assertEqual(_read(os.path.join(d1, name)),
                             _read(os.path.join(d2, name)), name)
        # سایر فایل‌ها ساختاری‌اً یکسان (به‌جز فیلدهای زمان‌بندی)
        m1 = _strip_wf_manifest(self.load(os.path.join(d1, "manifest.json")))
        m2 = _strip_wf_manifest(self.load(os.path.join(d2, "manifest.json")))
        self.assertEqual(m1, m2, "manifest.json")
        d1j = _strip_volatile(self.load(os.path.join(d1, "document.json")))
        d2j = _strip_volatile(self.load(os.path.join(d2, "document.json")))
        self.assertEqual(d1j, d2j, "document.json")
        self.assertEqual(doc1.blocks_hash(), doc2.blocks_hash())
        # dump-manifest هم ساختاری‌اً یکسان
        # (به‌جز hash/size report.md — footer-timestamp؛ قرارداد §5)
        x1 = _strip_dump_volatile(self.load(os.path.join(d1, "dump-manifest.json")))
        x2 = _strip_dump_volatile(self.load(os.path.join(d2, "dump-manifest.json")))
        self.assertEqual(x1, x2)

    def test_d05b_dump_twice_same_wf(self):
        src = make_docx(os.path.join(self.dir, "d.docx"),
                        [("Heading1", "فصل"), ("Normal", "متن تست تکرار.")])
        wf = self.run_wf(src)
        d = os.path.join(self.dir, "dup")
        generate_dump(wf, d)
        snap = {n: _read(os.path.join(d, n)) for n in CANONICAL_FILES}
        dm1 = self.load(os.path.join(d, "dump-manifest.json"))
        generate_dump(wf, d)  # دوم — همان دایرکتوری
        for n in CANONICAL_FILES:
            self.assertEqual(_read(os.path.join(d, n)), snap[n], n)
        dm2 = self.load(os.path.join(d, "dump-manifest.json"))
        self.assertEqual(_strip_volatile(dm1), _strip_volatile(dm2))


class TestD06_RawNormalized(DumpBase):
    """D06: RAW دست‌نخورده + NORMALIZED مطابق سیاست ثبت‌شده."""

    def test_d06a_raw_preserved_default_policy(self):
        raws = [
            "متن زیربخش با فاصلهٔ   اضافی و\tتب.",
            "دومین پاراگراف با عدد ۱۴۰۵ و عدد 2026 در یک خط.",
        ]
        src = make_docx(os.path.join(self.dir, "rn.docx"),
                        [("Normal", raws[0]), ("Normal", raws[1])])
        wf = self.run_wf(src)
        d = self.dump(wf)
        recs = _read_jsonl(os.path.join(d, "blocks.jsonl"))
        norm = PersianNormalizer()
        for rec, raw in zip(recs, raws):
            self.assertEqual(rec["raw_text"], raw, "RAW باید بایت‌به‌بایت باشد")
            expected, _ = norm.normalize(raw)
            self.assertEqual(rec["normalized_text"], expected)
            self.assertEqual(rec["norm_version"], "n-1")
            self.assertEqual(rec["content_hash"],
                             content_hash(rec["normalized_text"]))
        # سیاست ثبت‌شده در dump-manifest = همان سیاست پیش‌فرض n-1
        dm = self.load(os.path.join(d, "dump-manifest.json"))
        self.assertEqual(dm["versions"]["normalizer_policy"],
                         NormalizationPolicy().policy_dict())
        ok, errors, _ = validate_dump(d)
        self.assertTrue(ok, errors)

    def test_d06b_custom_policy_digits_persian(self):
        src = make_docx(os.path.join(self.dir, "dp.docx"),
                        [("Normal", "سال 2026 در متن.")])
        wf = self.run_wf(src, norm_policy=NormalizationPolicy(digits="persian"))
        d = self.dump(wf)
        recs = _read_jsonl(os.path.join(d, "blocks.jsonl"))
        self.assertEqual(recs[0]["raw_text"], "سال 2026 در متن.")
        self.assertEqual(recs[0]["normalized_text"], "سال ۲۰۲۶ در متن.")
        dm = self.load(os.path.join(d, "dump-manifest.json"))
        self.assertEqual(dm["versions"]["normalizer_policy"]["digits"],
                         "persian")
        # بازنرمال‌سازی از روی policy ثبت‌شده در dump باید برقرار باشد
        ok, errors, warnings = validate_dump(d)
        self.assertTrue(ok, errors)
        self.assertEqual(warnings, [])


class TestD07_OrderIds(DumpBase):
    """D07: ترتیب قطعی بلوک‌ها + block_id یکتا و مطابق قرارداد."""

    def test_d07_order_and_ids(self):
        src = make_sample_book(os.path.join(self.dir, "o.docx"))
        d = self.dump(self.run_wf(src))
        recs = _read_jsonl(os.path.join(d, "blocks.jsonl"))
        ids = [r["block_id"] for r in recs]
        self.assertEqual(len(ids), len(set(ids)), "block_id باید یکتا باشد")
        for i, r in enumerate(recs):
            self.assertEqual(r["block_index"], i)
            self.assertEqual(r["block_id"], f"b{i:05d}:{r['type']}")
            self.assertIsNone(r["page"])


class TestD08_Degraded(DumpBase):
    """D08: سند خالی / خروجی WF ناقص / blocks.jsonl خراب."""

    def test_d08a_empty_document(self):
        src = make_docx(os.path.join(self.dir, "e.docx"), [("Normal", "")])
        wf = self.run_wf(src)
        d = self.dump(wf)
        dm = self.load(os.path.join(d, "dump-manifest.json"))
        # کیفیت: manual_review (نه crash، نه claim سبز کاذب)
        self.assertEqual(dm["quality"]["quality_status"], "manual_review")
        ok, errors, _ = validate_dump(d)
        self.assertTrue(ok, errors)
        recs = _read_jsonl(os.path.join(d, "blocks.jsonl"))
        self.assertEqual(recs[0]["type"], "empty")
        self.assertEqual(recs[0]["raw_text"], "")
        self.assertEqual(recs[0]["normalized_text"], "")

    def test_d08b_incomplete_wf_output(self):
        src = make_sample_book(os.path.join(self.dir, "i.docx"))
        wf = self.run_wf(src)
        os.remove(os.path.join(wf, "quality-report.json"))  # خروجی ناقص
        with self.assertRaises(DumpError) as ctx:
            generate_dump(wf, os.path.join(self.dir, "nx"))
        self.assertIn("quality-report.json", str(ctx.exception.message))

    def test_d08c_corrupt_jsonl_in_dump(self):
        src = make_docx(os.path.join(self.dir, "c.docx"),
                        [("Normal", "متن سالم."), ("Normal", "متن دوم.")])
        d = self.dump(self.run_wf(src))
        p = os.path.join(d, "blocks.jsonl")
        lines = _read(p).decode("utf-8").splitlines()
        with open(p, "w", encoding="utf-8") as f:
            f.write(lines[0] + "\n" + "{json خراب" + "\n" + lines[1] + "\n")
        ok, errors, _ = validate_dump(d)
        self.assertFalse(ok)
        self.assertIn("invalid_jsonl_line:2", errors)
        # خط سالم هم باید هنوز قابل‌بازسازی باشد
        rec = json.loads(lines[0])
        self.assertEqual(rec["content_hash"],
                         content_hash(rec["normalized_text"]))


class TestD09_OfflineReconstruction(DumpBase):
    """D09: بازسازی/اعتبارسنجی فقط از روی خود Dump (بدون ES/DB/خروجی WF)."""

    def test_d09_offline(self):
        src = make_sample_book(os.path.join(self.dir, "of.docx"))
        wf = self.run_wf(src)
        d = self.dump(wf)
        # Dump را به دایرکتوری دیگری منتقل کن — اعتبارسنجی نباید به
        # مسیر WF یا فایل اصلی وابسته باشد
        moved = os.path.join(self.dir, "moved-dump")
        shutil.copytree(d, moved)
        shutil.rmtree(self.out)  # خروجی WF را کلاً حذف کن
        ok, errors, _ = validate_dump(moved)
        self.assertTrue(ok, errors)
        # بازسازی ساختاری: content_hash هر بلوک از normalized_text
        recs = _read_jsonl(os.path.join(moved, "blocks.jsonl"))
        for r in recs:
            self.assertEqual(r["content_hash"],
                             content_hash(r["normalized_text"]))
        s = dump_summary(moved)
        self.assertTrue(s["valid"])
        self.assertEqual(s["contract"], DUMP_VERSION)
        self.assertEqual(s["counts"]["blocks"], len(recs))


class TestD10_Idempotent(DumpBase):
    """D10: ساخت دوباره Dump روی همان دایرکتوری — بدون خروجی تکراری."""

    def test_d10_regenerate(self):
        src = make_docx(os.path.join(self.dir, "id.docx"),
                        [("Normal", "متن idempotency.")])
        wf = self.run_wf(src)
        d = os.path.join(self.dir, "dump")
        generate_dump(wf, d)
        first = sorted(os.listdir(d))
        snap = {n: _read(os.path.join(d, n)) for n in first}
        generate_dump(wf, d)
        second = sorted(os.listdir(d))
        self.assertEqual(first, second, "باید دقیقاً همان 6 فایل باشد")
        self.assertEqual(len(second), len(CANONICAL_FILES) + 1)
        for n in CANONICAL_FILES:
            self.assertEqual(snap[n], _read(os.path.join(d, n)), n)
        ok, errors, _ = validate_dump(d)
        self.assertTrue(ok, errors)


class TestD11_M1Compat(DumpBase):
    """D11: سازگاری با اجرای WF با مانیفست m-1 (سیاست ثبت‌نشده)."""

    def test_d11_m1_run(self):
        src = make_docx(os.path.join(self.dir, "m1.docx"),
                        [("Normal", "متن اجرای m-1.")])
        wf = self.run_wf(src)
        # شبیه‌سازی خروجی WF قدیمی: manifest.json را به m-1 بازمی‌گردانیم
        mp = os.path.join(wf, "manifest.json")
        m = self.load(mp)
        m["manifest_version"] = "m-1"
        m["versions"].pop("normalizer_policy", None)
        m["versions"].pop("factory", None)
        m.pop("blocks_hash", None)
        with open(mp, "w", encoding="utf-8") as f:
            json.dump(m, f, ensure_ascii=False, indent=2)
        d = self.dump(wf)
        dm = self.load(os.path.join(d, "dump-manifest.json"))
        self.assertEqual(dm["versions"]["manifest"], "m-1")
        self.assertIsNone(dm["versions"]["normalizer_policy"])
        self.assertIsNone(dm["integrity"]["blocks_hash"])
        ok, errors, warnings = validate_dump(d)
        self.assertTrue(ok, errors)
        self.assertTrue(any("normalizer_policy not recorded" in w
                            for w in warnings))


class TestD12_Isolation(DumpBase):
    """D12: بدون DB عملیاتی / بدون import ماژول‌های production."""

    def test_d12_no_production_imports(self):
        import ast
        import pathlib
        pkg = pathlib.Path(__file__).resolve().parent / "factory"
        banned = {"server", "flask", "pct_test_support", "dashboard_api",
                  "auth", "projects", "sqlite3"}
        for py in sorted(pkg.glob("*.py")):
            tree = ast.parse(py.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    mods = {a.name.split(".")[0] for a in node.names}
                elif isinstance(node, ast.ImportFrom) and node.module:
                    mods = {node.module.split(".")[0]}
                else:
                    continue
                hit = mods & banned
                self.assertFalse(hit, f"{py.name} imports {hit}")

    def test_d12_no_db_file(self):
        src = make_sample_book(os.path.join(self.dir, "db.docx"))
        wf = self.run_wf(src)
        d = self.dump(wf)
        for base in (self.dir, self.out, wf, d):
            self.assertFalse(any(f.endswith((".db", "-wal", "-shm"))
                                 for f in os.listdir(base)), base)


class TestD13_RepeatedCycles(DumpBase):
    """D13: چرخه‌های تکراری در-process (state نشت نکند)."""

    def test_d13_cycles(self):
        src = make_sample_book(os.path.join(self.dir, "cyc.docx"))
        for i in range(3):
            wf = self.run_wf(src)
            d = self.dump(wf, f"cyc{i}")
            ok, errors, _ = validate_dump(d)
            self.assertTrue(ok, errors)
            recs = _read_jsonl(os.path.join(d, "blocks.jsonl"))
            self.assertEqual(len(recs), self.load(
                os.path.join(d, "manifest.json"))["counts"]["blocks"])


class TestD14_DocContract(DumpBase):
    """D14: نمونه JSON سند قرارداد با خروجی واقعی یکسان است (کلیدهای top)."""

    def test_d14_doc_sample_matches_real(self):
        self.assertTrue(os.path.isfile(DOCS_CONTRACT),
                        "سند قرارداد باید وجود داشته باشد")
        with open(DOCS_CONTRACT, encoding="utf-8") as f:
            text = f.read()
        samples = [b for b in re.findall(r"```json\s*\n(.*?)\n```", text,
                                         re.DOTALL)
                   if "dump_contract_version" in b]
        self.assertTrue(samples, "نمونه json با dump_contract_version در سند")
        sample = json.loads(samples[0])
        self.assertEqual(sample["dump_contract_version"], DUMP_VERSION)
        src = make_docx(os.path.join(self.dir, "dc.docx"),
                        [("Normal", "متن آزمون سند.")])
        dm = self.load(os.path.join(
            self.dump(self.run_wf(src)), "dump-manifest.json"))
        self.assertEqual(sorted(sample.keys()), sorted(dm.keys()),
                         "کلیدهای top نمونه سند باید با خروجی واقعی یکی باشد")


class TestD15_Cli(DumpBase):
    """D15: CLI — زیردستورات dump + رفتار legacy بدون تغییر."""

    def _cli(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, "-m", "factory.cli", *args],
            cwd=BACKEND_DIR, capture_output=True, text=True,
            encoding="utf-8", timeout=120)

    def _setup(self):
        src = make_sample_book(os.path.join(self.dir, "cli.docx"))
        return src, self.run_wf(src)

    def test_d15_make_and_validate(self):
        src, wf = self._setup()
        d = os.path.join(self.dir, "clidump")
        r = self._cli("make-dump", wf, "--dump-dir", d, "--input", src,
                      "--json")
        self.assertEqual(r.returncode, 0, r.stderr)
        dm = json.loads(r.stdout)
        self.assertEqual(dm["dump_contract_version"], DUMP_VERSION)
        self.assertEqual(dm["source"]["input_file"]["sha256_source"],
                         "rehashed")
        r = self._cli("validate-dump", d, "--json")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(json.loads(r.stdout)["valid"])
        r = self._cli("dump-summary", d, "--json")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout)["contract"], DUMP_VERSION)

    def test_d15_tamper_exit_code(self):
        src, wf = self._setup()
        d = os.path.join(self.dir, "clidump2")
        self.assertEqual(self._cli("make-dump", wf, "--dump-dir", d,
                                   "--json").returncode, 0)
        p = os.path.join(d, "blocks.jsonl")
        with open(p, "a", encoding="utf-8") as f:
            f.write("x")
        r = self._cli("validate-dump", d, "--json")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertFalse(json.loads(r.stdout)["valid"])

    def test_d15_legacy_unchanged(self):
        src, _ = self._setup()
        out = os.path.join(self.dir, "legacy-out")
        r = self._cli(src, "--out", out, "--quiet")
        self.assertEqual(r.returncode, 0, r.stderr)
        fid = [f for f in os.listdir(out) if f.startswith("f-")][0]
        self.assertEqual(r.stdout.strip(), os.path.join(out, fid))


if __name__ == "__main__":
    unittest.main(verbosity=2)

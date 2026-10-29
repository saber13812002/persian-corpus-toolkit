# -*- coding: utf-8 -*-
"""test_corpus_builder — آزمون‌های پذیرش پیکره‌ساز (PCM-16، C-01..C-15).

مستقل از pct_test_support: پیکره‌ساز تابع خالص و فقط‌خوانده از Dumpهای
d-1 است (filesystem موقت + python-docx؛ بدون DB/Flask/ES/شبکه).

C-01 ساخت پیکره از یک Dump معتبر (تمام خروجی‌ها + hash/line_count درست)
C-02 ترتیب قطعی چند دامپ (جابه‌جایی ورودی → همان خروجی)
C-03 رد Dump نامعتبر/tampered — پیش از هر نگارش (fail-fast)
C-04 ورودی‌های نامعتبر (دایرکتوری غایب / require_quality غلط)
C-05 quality gate: require_quality="ok"
C-06 دو جریان جدا: RAW دست‌نخورده + NORMALIZED مطابق policy
C-07 dedup بین فایل‌ها + occurrence tracking + شمارش تکرار
C-08 provenance کامل هر بلوک (بازخوانی و راستی‌آزمایی مقادیر)
C-09 idempotency: build دوباره روی همان out_dir (بایتی + بدون تکرار)
C-10 determinism: build در دایرکتوری جدید (داده‌ها بایتی یکسان)
C-11 آرشیو ZIP قطعی (members + hash + استخراج = فایل‌های اصلی)
C-12 آمار فقط واقعی (بازمحاسبه مستقل از خود جریان‌ها)
C-13 پکیج محلی HF (ساختار + README + بدون کد بارگذاری/شبکه)
C-14 CLI build-corpus (موفقیت + خطای رد دامپ + dispatch legacy دست‌نخورده)
C-15 انزوا: بدون import ماژول‌های production/شبکه + بدون فایل DB
C-16 سازگاری به‌پایین: Dump شبیه m-1 (policy ثبت‌نشده)
"""
import ast
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from factory import (DocumentProcessingService, NormalizationPolicy,
                     build_corpus, content_hash, generate_dump,
                     validate_dump, CorpusError, CORPUS_VERSION)
from factory._smoke_fixtures import make_docx, make_sample_book
from factory.corpus import ARCHIVE_NAME, CORPUS_DATA_FILES, HF_DIR

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
PRODUCTION_MODULES = {"server", "flask", "knowledge_api", "dashboard_api",
                      "projects", "auth", "pct_test_support"}
NETWORK_MODULES = {"urllib", "urllib.request", "requests", "http.client",
                   "socket", "smtplib", "huggingface_hub"}


def _sha256_file(p: str) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def _sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _read_bytes(p: str) -> bytes:
    with open(p, "rb") as f:
        return f.read()


def _read_jsonl(p: str) -> list[dict]:
    with open(p, encoding="utf-8") as f:
        return [json.loads(l) for l in f.read().splitlines() if l.strip()]


def _load_json(p: str):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def _book_paras(marker: str, extra: list[tuple[str, str]] = None):
    """پاراگراف‌های یک کتاب متمایز (با خط متمایز marker — SHA یکتا)."""
    paras = [
        ("Normal", f"خط متمایز: {marker}"),
        ("Heading 1", "فصل اول"),
        ("Normal", "این اولین پاراگراف است. فارسی و انگلیسی English در کنار هم."),
        ("Normal", "متن با فاصلهٔ   اضافی و\tتب برای تفاوت raw/norm."),
    ]
    if extra:
        paras.extend(extra)
    return paras


class CorpusBase(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="corpus_test_")
        self.out = os.path.join(self.dir, "wf-out")

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def book(self, name: str, paras=None) -> str:
        """ساخت یک docx متمایز در دایرکتوری موقت."""
        p = os.path.join(self.dir, name)
        if paras is None:
            make_sample_book(p)
        else:
            make_docx(p, paras)
        return p

    def make_dump(self, name: str, paras=None,
                  norm_policy: NormalizationPolicy = None) -> str:
        """book → WF → Dump معتبر d-1 — برگشت دایرکتوری Dump."""
        src = self.book(f"{name}.docx", paras)
        kw = {}
        if norm_policy is not None:
            kw["norm_policy"] = norm_policy
        doc = DocumentProcessingService(out_dir=self.out, **kw).process(src)
        d = os.path.join(self.dir, f"dump-{name}")
        generate_dump(os.path.join(self.out, doc.file.file_id), d)
        return d

    def out1(self, name="corpus") -> str:
        return os.path.join(self.dir, name)

    def load_manifest(self, out_dir: str) -> dict:
        return _load_json(os.path.join(out_dir, "corpus-manifest.json"))


class TestC01_SingleDump(CorpusBase):
    def test_c01_outputs_and_hashes(self):
        """C-01: یک Dump معتبر → همه‌ی خروجی‌ها؛ hash/size/line_count می‌خواند."""
        d = self.make_dump("a", _book_paras("کتاب A"))
        out = self.out1()
        m = build_corpus([d], out)

        self.assertEqual(m["corpus_contract_version"], CORPUS_VERSION)
        for name in CORPUS_DATA_FILES + (ARCHIVE_NAME, "corpus-manifest.json"):
            self.assertTrue(os.path.isfile(os.path.join(out, name)), name)
        for fname in ("README.md", "corpus-manifest.json") + CORPUS_DATA_FILES:
            self.assertTrue(os.path.isfile(os.path.join(out, HF_DIR, fname)),
                            f"hf/{fname}")

        # hash/size/line_count هر فایل با بازمحاسبه می‌خواند
        for e in m["files"]:
            p = os.path.join(out, e["name"])
            self.assertEqual(_sha256_file(p), e["sha256"], e["name"])
            self.assertEqual(os.path.getsize(p), e["size_bytes"], e["name"])
            self.assertEqual(len(_read_jsonl(p)), e["line_count"], e["name"])
        ap = os.path.join(out, ARCHIVE_NAME)
        self.assertEqual(_sha256_file(ap), m["archive"]["sha256"])
        self.assertEqual(m["archive"]["members"], list(CORPUS_DATA_FILES))

        # همه‌ی بلوک‌های Dump در هر دو جریان (1:1)
        src_blocks = _read_jsonl(os.path.join(d, "blocks.jsonl"))
        for name in CORPUS_DATA_FILES[:2]:
            self.assertEqual(len(_read_jsonl(os.path.join(out, name))),
                             len(src_blocks), name)
        self.assertEqual(m["counts"]["blocks_total"], len(src_blocks))
        self.assertEqual(m["counts"]["dumps"], 1)


class TestC02_DeterministicOrder(CorpusBase):
    def test_c02_order_independent(self):
        """C-02: [A,B] و [B,A] → داده‌های بایتی یکسان؛ input_dumps مرتب."""
        da = self.make_dump("a", _book_paras("کتاب A"))
        db = self.make_dump("b", _book_paras("کتاب B"))
        out_ab = self.out1("c-ab")
        out_ba = self.out1("c-ba")
        m_ab = build_corpus([da, db], out_ab)
        m_ba = build_corpus([db, da], out_ba)

        for name in CORPUS_DATA_FILES + (ARCHIVE_NAME,):
            self.assertEqual(_read_bytes(os.path.join(out_ab, name)),
                             _read_bytes(os.path.join(out_ba, name)),
                             f"byte-diff: {name}")

        ids_ab = [(e["input_sha256"], e["file_id"])
                  for e in m_ab["input_dumps"]]
        ids_ba = [(e["input_sha256"], e["file_id"])
                  for e in m_ba["input_dumps"]]
        self.assertEqual(ids_ab, ids_ba)
        self.assertEqual(ids_ab, sorted(ids_ab))
        self.assertEqual(len(ids_ab), 2)
        self.assertEqual(len({i[1] for i in ids_ab}), 2)  # دو فایل متمایز

    def test_c02_block_order_within_file(self):
        """C-02b: داخل هر فایل، بلوک‌ها به ترتیب block_index."""
        d = self.make_dump("a", _book_paras("کتاب A"))
        out = self.out1()
        build_corpus([d], out)
        for name in CORPUS_DATA_FILES[:2]:
            lines = _read_jsonl(os.path.join(out, name))
            idx = [r["block_index"] for r in lines]
            self.assertEqual(idx, list(range(len(idx))), name)


class TestC03_InvalidRejected(CorpusBase):
    def test_c03_tampered_dump_rejected_before_write(self):
        """C-03: Dump tampered → CorpusError؛ هیچ فایلی نوشته نشود."""
        d = self.make_dump("a", _book_paras("کتاب A"))
        bp = os.path.join(d, "blocks.jsonl")
        data = _read_bytes(bp)
        self.assertIn(b'"paragraph"', data)
        with open(bp, "wb") as f:
            f.write(data.replace(b'"paragraph"', b'"Paragraph"', 1))
        out = self.out1()
        with self.assertRaises(CorpusError):
            build_corpus([d], out)
        self.assertFalse(os.path.exists(out))

    def test_c03_missing_file_rejected(self):
        """C-03b: Dump ناقص (فایل حذف‌شده) → CorpusError."""
        d = self.make_dump("a", _book_paras("کتاب A"))
        os.remove(os.path.join(d, "quality-report.json"))
        out = self.out1()
        with self.assertRaises(CorpusError):
            build_corpus([d], out)
        self.assertFalse(os.path.exists(out))

    def test_c03_one_bad_of_many_rejected(self):
        """C-03c: یک دامپ نامعتبر در میان چند دامپ سالم → کل build رد شود."""
        good = self.make_dump("a", _book_paras("کتاب A"))
        bad = self.make_dump("b", _book_paras("کتاب B"))
        os.remove(os.path.join(bad, "blocks.jsonl"))
        out = self.out1()
        with self.assertRaises(CorpusError):
            build_corpus([good, bad], out)
        self.assertFalse(os.path.exists(out))


class TestC04_InvalidArgs(CorpusBase):
    def test_c04_missing_dir(self):
        out = self.out1()
        with self.assertRaises(CorpusError):
            build_corpus([os.path.join(self.dir, "nope")], out)
        self.assertFalse(os.path.exists(out))

    def test_c04_bad_require_quality(self):
        d = self.make_dump("a", _book_paras("کتاب A"))
        out = self.out1()
        with self.assertRaises(CorpusError):
            build_corpus([d], out, require_quality="high")
        self.assertFalse(os.path.exists(out))


class TestC05_QualityGate(CorpusBase):
    def test_c05_require_ok_gate(self):
        """C-05: require_quality='ok' دامپ manual_review را رد می‌کند؛
        بدون gate هر دو وارد پیکره می‌شوند."""
        ok = self.make_dump("a", _book_paras("کتاب A"))
        weak = self.make_dump(
            "weak", [("Normal", "متن خیلی کوتاه.")] +
                    _book_paras("کتاب ضعیف")[:1])
        dm_w = _load_json(os.path.join(weak, "dump-manifest.json"))
        self.assertNotEqual(dm_w["quality"]["quality_status"], "ok")

        out = self.out1()
        with self.assertRaises(CorpusError):
            build_corpus([ok, weak], out, require_quality="ok")
        self.assertFalse(os.path.exists(out))

        m = build_corpus([ok, weak], out)
        self.assertEqual(m["counts"]["dumps"], 2)
        self.assertIn("ok", m["counts"]["dumps_by_quality"])
        self.assertIn(dm_w["quality"]["quality_status"],
                      m["counts"]["dumps_by_quality"])


class TestC06_SeparateStreams(CorpusBase):
    def test_c06_raw_and_normalized_streams(self):
        """C-06: RAW = همان متن Dump (بایتی)؛ NORMALIZED مطابق policy؛
        هر فایل فقط متن جریان خودش را دارد."""
        d = self.make_dump("a", _book_paras("کتاب A"))
        out = self.out1()
        build_corpus([d], out)
        src = _read_jsonl(os.path.join(d, "blocks.jsonl"))

        raw_lines = _read_jsonl(os.path.join(out, "raw.jsonl"))
        norm_lines = _read_jsonl(os.path.join(out, "normalized.jsonl"))
        self.assertEqual(len(raw_lines), len(src))
        for s, r in zip(src, raw_lines):
            self.assertEqual(r["raw_text"], s["raw_text"])
            self.assertEqual(r["block_id"], s["block_id"])
            self.assertNotIn("normalized_text", r)
        for s, n in zip(src, norm_lines):
            self.assertEqual(n["normalized_text"], s["normalized_text"])
            self.assertEqual(n["norm_version"], s["norm_version"])
            self.assertEqual(n["content_hash"], s["content_hash"])
            self.assertNotIn("raw_text", n)

        # fixture حداقل یک بلوک raw != normalized دارد (فاصله/تب)
        diff = [s for s in src
                if s["type"] not in ("empty", "pagebreak", "table")
                and s["raw_text"] != s["normalized_text"]]
        self.assertTrue(diff, "expected at least one normalized block")
        # بلوک‌های غیرنرمال‌شده: raw == normalized
        for s in src:
            if s["type"] in ("empty", "pagebreak", "table"):
                self.assertEqual(s["raw_text"], s["normalized_text"])

        # raw_hash در فایل unique با بازمحاسبه می‌خواند
        for line in _read_jsonl(os.path.join(out, "raw.unique.jsonl")):
            self.assertEqual(line["raw_hash"],
                             "sha256:" + _sha256_bytes(
                                 line["raw_text"].encode("utf-8"))[:16])


class TestC07_Dedup(CorpusBase):
    SHARED = "این پاراگراف مشترک در هر سه کتاب تکرار می‌شود."

    def _three_books(self):
        base = [("Heading 1", "فصل مشترک"),
                ("Normal", self.SHARED)]
        return (
            self.make_dump("o1", base + [("Normal", "متن متمایز فایل ۱.")]),
            self.make_dump("o2", base + [("Normal", "متن متمایز فایل ۲.")]),
            self.make_dump("o3", base + [("Normal", "متن متمایز فایل ۳.")]),
        )

    def test_c07_cross_file_dedup(self):
        """C-07: پاراگراف تکراری در ۳ فایل → dedup + occurrence tracking."""
        d1, d2, d3 = self._three_books()
        out = self.out1()
        m = build_corpus([d1, d2, d3], out)

        raw = _read_jsonl(os.path.join(out, "raw.jsonl"))
        raw_u = _read_jsonl(os.path.join(out, "raw.unique.jsonl"))
        occ = [r for r in raw if r["raw_text"] == self.SHARED]
        self.assertEqual(len(occ), 3)
        self.assertEqual(m["counts"]["duplicates_raw"],
                         len(raw) - len(raw_u))
        self.assertGreater(m["counts"]["duplicates_raw"], 0)

        u_line = next(r for r in raw_u if r["raw_text"] == self.SHARED)
        self.assertEqual(u_line["occurrence_count"], 3)
        self.assertEqual(len(u_line["occurrences"]), 3)
        self.assertEqual(u_line["raw_text"], occ[0]["raw_text"])
        expected = {f"{r['provenance']['input_sha256'][:8]}:{r['block_id']}"
                    for r in occ}
        self.assertEqual(set(u_line["occurrences"]), expected)

    def test_c07_norm_unique_uses_content_hash(self):
        """C-07b: dedup normalized با content_hash — rawهای متفاوت با
        policy پیش‌فرض (digits=keep) → normalizedهای متفاوت."""
        d1 = self.make_dump("n1", [("Normal", "متن تکراری ۱۴۰۵ و فاصلهٔ   اضافی.")])
        d2 = self.make_dump("n2", [("Normal", "متن تکراری 1405 و فاصلهٔ   اضافی.")])
        out = self.out1()
        m = build_corpus([d1, d2], out)
        norm_u = _read_jsonl(os.path.join(out, "normalized.unique.jsonl"))
        texts = [r["normalized_text"] for r in norm_u
                 if "متن تکراری" in r["normalized_text"]]
        self.assertEqual(len(texts), 2)
        for r in norm_u:
            self.assertEqual(r["content_hash"],
                             content_hash(r["normalized_text"]))
        self.assertEqual(m["counts"]["blocks_unique_normalized"], len(norm_u))


class TestC08_Provenance(CorpusBase):
    def test_c08_provenance_complete_and_true(self):
        """C-08: provenance هر خط کامل است و مقادیر با Dump واقعی می‌خواند."""
        d = self.make_dump("a", _book_paras("کتاب A"))
        out = self.out1()
        build_corpus([d], out)
        dm = _load_json(os.path.join(d, "dump-manifest.json"))
        ident = dm["identifiers"]
        prov_src = dm["source"]["input_file"]

        raw = _read_jsonl(os.path.join(out, "raw.jsonl"))
        self.assertTrue(raw)
        p = raw[0]["provenance"]
        self.assertEqual(p["input_sha256"], dm["integrity"]["input_sha256"])
        self.assertEqual(p["input_sha256"], prov_src["sha256"])
        self.assertEqual(p["input_filename"], prov_src["filename"])
        self.assertEqual(p["factory_file_id"], ident["file_id"])
        self.assertEqual(p["work_id"], ident["work_id"])
        self.assertEqual(p["edition_id"], ident["edition_id"])
        self.assertEqual(p["volume_id"], ident["volume_id"])
        self.assertEqual(p["dump_dir"], os.path.abspath(d))
        self.assertEqual(p["dump_contract"], "d-1")
        self.assertEqual(p["dump_blocks_sha256"],
                         _sha256_file(os.path.join(d, "blocks.jsonl")))
        self.assertEqual(p["dump_manifest_sha256"],
                         _sha256_file(os.path.join(d, "dump-manifest.json")))
        self.assertEqual(p["versions"]["manifest"], dm["versions"]["manifest"])
        self.assertEqual(p["versions"]["normalizer"],
                         dm["versions"]["normalizer"])
        self.assertEqual(p["versions"]["factory"], dm["versions"]["factory"])

        # record_id قطعی + document fields + provenance همه‌ی خطوط
        for r in raw:
            self.assertEqual(
                r["record_id"],
                f"cb1:{dm['integrity']['input_sha256'][:12]}:{r['block_id']}")
            self.assertEqual(r["document"]["title"], dm["document"]["title"])
            self.assertEqual(r["provenance"]["factory_file_id"],
                             ident["file_id"])


class TestC09_Idempotent(CorpusBase):
    def test_c09_rebuild_same_dir(self):
        """C-09: build دوباره روی همان out_dir → بایتی یکسان، بدون فایل جدید."""
        d = self.make_dump("a", _book_paras("کتاب A"))
        out = self.out1()
        build_corpus([d], out)
        before = {n: _read_bytes(os.path.join(out, n))
                  for n in CORPUS_DATA_FILES}
        before_zip = _read_bytes(os.path.join(out, ARCHIVE_NAME))
        listing_before = sorted(os.listdir(out))
        hf_before = sorted(os.listdir(os.path.join(out, HF_DIR)))

        build_corpus([d], out)
        after = {n: _read_bytes(os.path.join(out, n))
                 for n in CORPUS_DATA_FILES}
        self.assertEqual(before, after)
        self.assertEqual(before_zip, _read_bytes(os.path.join(out, ARCHIVE_NAME)))
        self.assertEqual(listing_before, sorted(os.listdir(out)))
        self.assertEqual(hf_before, sorted(os.listdir(os.path.join(out, HF_DIR))))
        m = self.load_manifest(out)
        self.assertEqual(_sha256_file(os.path.join(out, ARCHIVE_NAME)),
                         m["archive"]["sha256"])


class TestC10_CrossDirDeterminism(CorpusBase):
    def test_c10_two_dirs_same_bytes(self):
        """C-10: build در دو دایرکتوری مستقل → داده‌های بایتی یکسان؛
        manifest جزو generated_at یکسان."""
        d = self.make_dump("a", _book_paras("کتاب A"))
        o1, o2 = self.out1("c1"), self.out1("c2")
        build_corpus([d], o1)
        build_corpus([d], o2)
        for name in CORPUS_DATA_FILES + (ARCHIVE_NAME,):
            self.assertEqual(_read_bytes(os.path.join(o1, name)),
                             _read_bytes(os.path.join(o2, name)), name)
        m1, m2 = self.load_manifest(o1), self.load_manifest(o2)
        m1.pop("generated_at")
        m2.pop("generated_at")
        self.assertEqual(m1, m2)


class TestC11_Archive(CorpusBase):
    def test_c11_zip_contents_and_determinism(self):
        """C-11: ZIP = ۴ JSONL به ترتیب قطعی؛ استخراج = بایت فایل‌ها؛
        دو build → zip بایتی یکسان."""
        d = self.make_dump("a", _book_paras("کتاب A"))
        o1, o2 = self.out1("c1"), self.out1("c2")
        m = build_corpus([d], o1)
        build_corpus([d], o2)

        zp = os.path.join(o1, ARCHIVE_NAME)
        with zipfile.ZipFile(zp) as zf:
            self.assertEqual(zf.namelist(), list(CORPUS_DATA_FILES))
            for name in zf.namelist():
                self.assertEqual(zf.read(name),
                                 _read_bytes(os.path.join(o1, name)), name)
        self.assertEqual(_read_bytes(zp),
                         _read_bytes(os.path.join(o2, ARCHIVE_NAME)))
        self.assertEqual(m["archive"]["sha256"], _sha256_file(zp))


class TestC12_StatsReal(CorpusBase):
    def test_c12_counts_recomputed(self):
        """C-12: همه‌ی آمار manifest با بازمحاسبه‌ی مستقل از فایل‌ها می‌خواند."""
        d1 = self.make_dump("a", _book_paras("کتاب A"))
        d2 = self.make_dump("b", _book_paras("کتاب B"))
        out = self.out1()
        m = build_corpus([d1, d2], out)

        raw = _read_jsonl(os.path.join(out, "raw.jsonl"))
        norm = _read_jsonl(os.path.join(out, "normalized.jsonl"))
        raw_u = _read_jsonl(os.path.join(out, "raw.unique.jsonl"))
        norm_u = _read_jsonl(os.path.join(out, "normalized.unique.jsonl"))

        c = m["counts"]
        self.assertEqual(c["dumps"], 2)
        self.assertEqual(c["blocks_total"], len(raw))
        self.assertEqual(c["blocks_unique_raw"], len(raw_u))
        self.assertEqual(c["blocks_unique_normalized"], len(norm_u))
        self.assertEqual(c["duplicates_raw"], len(raw) - len(raw_u))
        self.assertEqual(c["duplicates_normalized"],
                         len(norm) - len(norm_u))
        self.assertEqual(c["raw_chars"],
                         sum(len(r["raw_text"]) for r in raw))
        self.assertEqual(c["normalized_chars"],
                         sum(len(r["normalized_text"]) for r in norm))

        by_type: dict = {}
        for r in raw:
            by_type[r["type"]] = by_type.get(r["type"], 0) + 1
        self.assertEqual(c["by_type"], dict(sorted(by_type.items())))

        hist: dict = {}
        for d in (d1, d2):
            q = _load_json(os.path.join(d, "dump-manifest.json"))
            q = q["quality"]["quality_status"]
            hist[q] = hist.get(q, 0) + 1
        self.assertEqual(c["dumps_by_quality"], dict(sorted(hist.items())))

        for e in m["input_dumps"]:
            src = _read_jsonl(os.path.join(e["dir"], "blocks.jsonl"))
            self.assertEqual(e["counts"]["blocks"], len(src))


class TestC13_HfPackage(CorpusBase):
    def test_c13_local_package(self):
        """C-13: پکیج HF محلی — داده‌ها کپی بایتی + README با آمار واقعی."""
        d = self.make_dump("a", _book_paras("کتاب A"))
        out = self.out1()
        m = build_corpus([d], out)
        hf = os.path.join(out, HF_DIR)

        for name in CORPUS_DATA_FILES:
            self.assertEqual(_read_bytes(os.path.join(hf, name)),
                             _read_bytes(os.path.join(out, name)), name)
        self.assertEqual(
            _sha256_file(os.path.join(hf, "corpus-manifest.json")),
            _sha256_file(os.path.join(out, "corpus-manifest.json")))
        with open(os.path.join(hf, "README.md"), encoding="utf-8") as f:
            readme = f.read()
        self.assertIn("language: fa", readme)
        self.assertIn("license: cc-by-nc-sa-4.0", readme)
        self.assertIn(str(m["counts"]["blocks_total"]), readme)
        self.assertIn(str(m["counts"]["blocks_unique_raw"]), readme)
        self.assertIn("فقط محلی", readme)
        for name, h in m["hf_package"]["files"].items():
            self.assertEqual(_sha256_file(os.path.join(hf, name)), h, name)


class TestC14_Cli(CorpusBase):
    def _cli(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, "-m", "factory.cli", *args],
            cwd=BACKEND_DIR, capture_output=True, text=True,
            encoding="utf-8", timeout=120)

    def test_c14_build_ok(self):
        """C-14: CLI build-corpus → exit 0 + manifest قابل‌خواندن."""
        d = self.make_dump("a", _book_paras("کتاب A"))
        out = self.out1()
        r = self._cli("build-corpus", d, "--out", out, "--json")
        self.assertEqual(r.returncode, 0, r.stderr)
        m = json.loads(r.stdout)
        self.assertEqual(m["corpus_contract_version"], CORPUS_VERSION)
        self.assertTrue(os.path.isfile(os.path.join(out, "raw.jsonl")))

    def test_c14_build_rejects_bad(self):
        """C-14b: CLI روی Dump خراب → exit 1 + stderr + بدون خروجی."""
        d = self.make_dump("a", _book_paras("کتاب A"))
        os.remove(os.path.join(d, "document.json"))
        out = self.out1()
        r = self._cli("build-corpus", d, "--out", out)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("خطای Dump/Corpus", r.stderr)
        self.assertFalse(os.path.exists(out))

    def test_c14_legacy_dispatch_unchanged(self):
        """C-14c: زیردستور legacy (validate-dump) بدون تغییر کار می‌کند."""
        d = self.make_dump("a", _book_paras("کتاب A"))
        r = self._cli("validate-dump", d, "--json")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(json.loads(r.stdout)["valid"])


class TestC15_Isolation(CorpusBase):
    def test_c15_no_production_or_network_imports(self):
        """C-15: corpus.py — بدون import ماژول‌های production و شبکه (AST)."""
        path = os.path.join(BACKEND_DIR, "factory", "corpus.py")
        with open(path, encoding="utf-8") as f:
            tree = ast.parse(f.read())
        bad = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    top = a.name.split(".")[0]
                    if top in PRODUCTION_MODULES or a.name in NETWORK_MODULES:
                        bad.add(a.name)
            elif isinstance(node, ast.ImportFrom):
                mod = (node.module or "").split(".")[0]
                if mod in PRODUCTION_MODULES or mod in NETWORK_MODULES:
                    bad.add(node.module)
        self.assertEqual(bad, set())

    def test_c15_no_db_created(self):
        """C-15b: build هیچ فایل DB نمی‌سازد (نه در out، نه در fixtures)."""
        d = self.make_dump("a", _book_paras("کتاب A"))
        out = self.out1()
        build_corpus([d], out)
        for dirpath, _dn, fnames in os.walk(self.dir):
            for n in fnames:
                self.assertFalse(
                    n.endswith((".db", ".sqlite", ".sqlite3")),
                    f"db file created: {os.path.join(dirpath, n)}")


class TestC16_M1Compat(CorpusBase):
    def test_c16_policy_unrecorded_dump_accepted(self):
        """C-16: Dump با normalizer_policy ثبت‌نشده (شبیه m-1) — warning
        در validate، ولی پیکره‌سازی مجاز."""
        src = self.book("m1.docx", _book_paras("کتاب m-1"))
        doc = DocumentProcessingService(
            out_dir=self.out,
            norm_policy=NormalizationPolicy(digits="persian")).process(src)
        wf_dir = os.path.join(self.out, doc.file.file_id)
        # شبیه‌سازی m-1: policy از versions مانیفست WF حذف می‌شود
        mp = os.path.join(wf_dir, "manifest.json")
        m = _load_json(mp)
        m["manifest_version"] = "m-1"
        m["versions"].pop("normalizer_policy", None)
        with open(mp, "w", encoding="utf-8") as f:
            json.dump(m, f, ensure_ascii=False, indent=2)
        d = os.path.join(self.dir, "dump-m1")
        generate_dump(wf_dir, d)

        dm = _load_json(os.path.join(d, "dump-manifest.json"))
        self.assertIsNone(dm["versions"]["normalizer_policy"])
        ok, errors, warnings = validate_dump(d)
        self.assertTrue(ok, errors)
        self.assertTrue(any("re-normalization check skipped" in w
                            for w in warnings), warnings)

        out = self.out1()
        m = build_corpus([d], out)
        self.assertEqual(m["input_dumps"][0]["versions"]["manifest"], "m-1")
        self.assertEqual(m["input_dumps"][0]["versions"]["normalizer_policy"],
                         None)


if __name__ == "__main__":
    unittest.main(verbosity=2)

# -*- coding: utf-8 -*-
"""test_corpus_pcm207c.py — PCM-20.7C: تثبیت پیکره + غنی‌سازی معنایی (cs-20.7).

اجرا:  python -X utf8 -m unittest test_corpus_pcm207c -v

گروه‌های آزمون (بخش 3.8 مأموریت PCM-20.7C):
  G01  بازحساب شکاف (gap-report-2) — known-answer روی فیکستور کوچک +
       قطعی بودن content_sha256 + خطاهای ورودی.
  SU01-04 ماتسِ سوره — خودآزمون قطعی (رأی NOT_SUPPORTED؛ شواهد داده‌ای روی
       پیکره‌ی واقعی در docs/PCM-20.7C-SURAH-ASSESSMENT.md). این آزمون
       منطق ماتس را قفل می‌کند تا هر ارزیابی آتی همان قواعد را داشته باشد.
  E01  واحدهای enrich: normalize_summary + generate_summaries (chat_fn جعلی،
       resume، همه‌خطا، limit).
  V401-V408 build v0004 (cs-20.7): زنجیره‌ی v0001→v0002→v0003→checkpoint→
       v0004؛ سرشماری وضعیت‌ها + فیلدهای جدید؛ دست‌نخورده‌ها بایت‌به‌بایت؛
       manifest زنجیره‌ای (prev/previous_version/5 فایل)؛ validate_semantic
       (شامل S11) + validate_corpus؛ نشت (LEAK) — خلاصه نه در corpus.json
       عمومی نه در رکورد صفحه‌ی عنوان؛ REUSED idempotency؛ 5 حالت منفی
       rc=2؛ 3 تخلف (tamper) شامل LEAK دقیق.
  DS01-DS05 rebuild دیتاست + `--volume-id` (جلد بی‌شماره؛ افزایشی PCM-20.7C).

بدون شبکه؛ بدون دست‌به‌دبیری DB production؛ همه‌ی فیکستورها در tmpdir.
"""
import contextlib
import io
import json
import os
import re
import shutil
import tempfile
import unittest
import unicodedata

from corpus.tasnim import cli as CL
from corpus.tasnim import common as C
from corpus.tasnim import dataset as D
from corpus.tasnim import enrich as ENR
from corpus.tasnim import manifest as M
from corpus.tasnim import schema as S
from corpus.tasnim import semantic as SEM
from corpus.tasnim import validate as VAL
from corpus.tasnim import versioning as V
from corpus.tasnim.backfill import gap as GAP

from test_corpus_tasnim import fa, make_fixture, page_rec


# ===========================================================================
# G01 — بازحساب شکاف (gap-report-2)
# ===========================================================================
class TestG01GapRecompute(unittest.TestCase):
    """known-answer: present {1,2,4,5,9,10,15} + 1 تکراری + 1 بدون index."""

    def setUp(self):
        C.force_utf8_stdio()
        self.tmp = tempfile.mkdtemp(prefix="pct-pcm207c-gap-")

    def tearDown(self):
        try:
            shutil.rmtree(self.tmp)
        except Exception:
            pass

    def _write_pages(self, name, records):
        path = os.path.join(self.tmp, name)
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            for r in records:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        return path

    @staticmethod
    def _rec(i):
        vno = 1 if i < 10 else 2
        return {"item_index": i,
                "volume": {"volume_no": vno, "volume_title": "جلد %d" % vno}}

    def _fixture(self, name="pages.jsonl"):
        recs = [self._rec(i) for i in (1, 2, 4, 5, 9, 10, 15)]
        recs.append(self._rec(5))                        # item_index تکراری
        recs.append({"item_index": None, "volume": {}})   # بدون item_index
        return self._write_pages(name, recs)

    def test_g01_known_answer(self):
        rep = GAP.build_gap_report_v2(self._fixture())
        self.assertEqual(rep["contract"], "gap-report-2")
        pg = rep["pages"]
        self.assertEqual(pg["total_records"], 9)
        self.assertEqual(pg["with_item_index"], 8)
        self.assertEqual(pg["distinct_item_index"], 7)
        self.assertEqual(pg["dup_count"], 1)
        self.assertEqual(pg["no_index"], 1)
        self.assertEqual(pg["range_min"], 1)
        self.assertEqual(pg["range_max"], 15)
        self.assertEqual(pg["span"], 15)
        gp = rep["gaps"]
        self.assertEqual(gp["missing_count"], 8)
        self.assertEqual(gp["runs_count"], 3)
        runs = [(r["start"], r["end"], r["count"]) for r in gp["runs"]]
        self.assertEqual(runs, [(3, 3, 1), (6, 8, 3), (11, 14, 4)])
        r0, r1, r2 = gp["runs"]
        self.assertEqual((r0["before_item_index"], r0["after_item_index"]), (2, 4))
        self.assertEqual((r1["before_item_index"], r1["after_item_index"]), (5, 9))
        self.assertEqual((r2["before_item_index"], r2["after_item_index"]), (10, 15))
        self.assertEqual(r0["volume_before"]["volume_no"], 1)
        self.assertEqual(r2["volume_after"]["volume_no"], 2)
        self.assertEqual(GAP.runs_of(rep), [[3, 3], [6, 8], [11, 14]])

    def test_g01b_deterministic_content_sha(self):
        p = self._fixture()
        rep1 = GAP.build_gap_report_v2(p)
        rep2 = GAP.build_gap_report_v2(p)
        self.assertEqual(rep1["content_sha256"], rep2["content_sha256"])
        out = os.path.join(self.tmp, "report.json")
        GAP.write_gap_report_v2(rep1, out)
        with open(out, "r", encoding="utf-8") as f:
            back = json.load(f)
        self.assertEqual(back["content_sha256"], rep1["content_sha256"])
        self.assertEqual(back["source"]["pages_sha256"], C.sha256_file(p))

    def test_g01c_bad_inputs(self):
        p = self._write_pages("noindex.jsonl",
                              [{"item_index": None, "volume": {}}])
        with self.assertRaises(ValueError):
            GAP.build_gap_report_v2(p)
        with self.assertRaises(FileNotFoundError):
            GAP.build_gap_report_v2(os.path.join(self.tmp, "nope.jsonl"))


# ===========================================================================
# SU01-SU04 — ماتسِ سوره (رأی NOT_SUPPORTED قفل می‌شود)
# ===========================================================================
# جدول ۱۱۴ سوره (ar, fa) — همان جدولی که در ارزیابی PCM-20.7C §3.5
# ثبت و با خودآزمون 18 مورد تأیید شد.
SURAHS = [
    ("الفاتحة", "فاطمه"), ("البقرة", "بقره"), ("آل عمران", "آل‌عمران"),
    ("النساء", "نساء"), ("المائدة", "مائده"), ("الأنعام", "انعام"),
    ("الأعراف", "اعراف"), ("الأنفال", "انفال"), ("التوبة", "توبه"),
    ("يونس", "یونس"), ("هود", "هود"), ("يوسف", "یوسف"), ("الرعد", "رعد"),
    ("إبراهيم", "ابراهیم"), ("الحجر", "حجر"), ("النحل", "نحل"),
    ("الإسراء", "اسراء"), ("الكهف", "کهف"), ("مريم", "مریم"), ("طه", "طه"),
    ("الأنبياء", "انبیاء"), ("الحج", "حج"), ("المؤمنون", "مومنون"),
    ("النور", "نور"), ("الفرقان", "فرقان"), ("الشعراء", "شعراء"),
    ("النمل", "نمل"), ("القصص", "قصص"), ("العنكبوت", "عنکبوت"),
    ("الروم", "روم"), ("لقمان", "لقمان"), ("السجدة", "سجده"),
    ("الأحزاب", "احزاب"), ("سبأ", "سبا"), ("فاطر", "فاطر"),
    ("يس", "یس"), ("الصافات", "صافات"), ("ص", "ص"), ("الزمر", "زمر"),
    ("غافر", "غافر"), ("فصلت", "فصلت"), ("الشورى", "شورى"),
    ("الزخرف", "زخرف"), ("الدخان", "دخان"), ("الجاثية", "جاثیه"),
    ("الأحقاف", "احقاف"), ("محمد", "محمد"), ("الفتح", "فتح"),
    ("الحجرات", "حجرات"), ("ق", "ق"), ("الذاريات", "ذاریات"),
    ("الطور", "طور"), ("النجم", "نجم"), ("القمر", "قمر"),
    ("الرحمن", "رحمان"), ("الواقعة", "واقعه"), ("الحديد", "حديد"),
    ("المجادلة", "مجادله"), ("الحشر", "حشر"), ("الممتحنة", "ممحنه"),
    ("الصف", "صف"), ("الجمعة", "جمعه"), ("المنافقون", "منافقون"),
    ("التغابن", "تغابن"), ("الطلاق", "طلاق"), ("التحريم", "تهریم"),
    ("الملك", "ملک"), ("القلم", "قلم"), ("الحاقة", "حقّه"),
    ("المعارج", "معارج"), ("نوح", "نوح"), ("الجن", "جن"),
    ("المزمل", "مزمل"), ("المدثر", "مدثر"), ("القيامة", "قیامه"),
    ("الإنسان", "انسان"), ("المرسلات", "مرسلات"), ("النبأ", "نبأ"),
    ("النازعات", "نازعات"), ("عبس", "عبس"), ("التكوير", "تکویر"),
    ("الانفطار", "انفتاح"), ("المطففين", "مطففین"), ("الانشقاق", "انشقاق"),
    ("البروج", "بروج"), ("الطارق", "طارق"), ("الأعلى", "اعلی"),
    ("الغاشية", "غاشیه"), ("الفجر", "فجر"), ("البلد", "بلد"),
    ("الشمس", "شمس"), ("الليل", "لیل"), ("الضحى", "ضحی"),
    ("الشرح", "شرح"), ("التين", "تین"), ("العلق", "علق"),
    ("القدر", "قدر"), ("البينة", "بینه"), ("الزلزله", "زلزله"),
    ("العاديات", "عادیات"), ("القارعه", "قارعه"), ("التكاثر", "تکاثر"),
    ("العصر", "عصر"), ("الهمزه", "همزه"), ("الفيل", "فیل"),
    ("قريش", "قریش"), ("الماعون", "ماعون"), ("الكوثر", "کوثر"),
    ("الكافرون", "کافرون"), ("النصر", "نصر"), ("المسد", "مسد"),
    ("الإخلاص", "اخلاص"), ("الفلق", "فلک"), ("الناس", "ناس"),
]


def surah_match(heading_text):
    """Explicit-marker matching only: heading IS the surah title form.

    برگشت (surah_no, name_ar, name_fa, basis) یا None."""
    t = unicodedata.normalize("NFKC", (heading_text or "")).strip()
    if not t:
        return None
    for i, (ar, fa) in enumerate(SURAHS, 1):
        for name in (ar, fa, fa.replace("\u200c", ""), fa.replace("\u200c", " ")):
            if not name:
                continue
            if len(name) <= 2:  # ص / ق — فقط exact یا با پیشوند سور(ه)
                if t == name or t in ("سورة " + name, "سوره " + name,
                                      "سور" + name):
                    return (i, ar, fa, "exact")
            elif t == name or t in ("سورة " + name, "سوره " + name,
                                    "سور" + name):
                return (i, ar, fa, "exact")
            elif t.startswith("تفسیر " + "سوره " + name) \
                    or t.startswith("تفسير " + "سورة " + name) \
                    or t.startswith("تفسیر " + "سورة " + name) \
                    or t.startswith("تفسير " + "سوره " + name):
                return (i, ar, fa, "tafsir-prefixed")
    return None


def surah_mention(heading_text):
    """Heading «سوره/سورة NAME» دارد ولی خودِ عنوان نیست."""
    t = unicodedata.normalize("NFKC", (heading_text or "")).strip()
    m = re.search(r"سور[هي]\s*([^\s،:]{1,20})", t)
    if not m:
        return None
    cand = m.group(1).strip(" .:ـ-")
    for i, (ar, fa) in enumerate(SURAHS, 1):
        if cand in (ar, fa, fa.replace("\u200c", "")):
            return (i, ar, fa)
    return None


class TestSU1SurahExact(unittest.TestCase):
    def test_su01_table_is_114(self):
        self.assertEqual(len(SURAHS), 114)

    def test_su01_exact_and_prefixed(self):
        self.assertEqual(surah_match("سوره بقره"),
                         (2, "البقرة", "بقره", "exact"))
        self.assertEqual(surah_match("سورة البقرة"),
                         (2, "البقرة", "بقره", "exact"))
        self.assertEqual(surah_match("بقره"), (2, "البقرة", "بقره", "exact"))
        self.assertEqual(surah_match("تفسیر سوره بقره"),
                         (2, "البقرة", "بقره", "tafsir-prefixed"))
        self.assertEqual(surah_match("تفسير سورة الفاتحة"),
                         (1, "الفاتحة", "فاطمه", "tafsir-prefixed"))
        self.assertEqual(surah_match("یس"), (36, "يس", "یس", "exact"))
        self.assertEqual(surah_match("طه"), (20, "طه", "طه", "exact"))
        # آل‌عمران: fa با ZWNJ؛ فرم‌های ZWNJ-stripped و space-mapped هم خوراک
        self.assertEqual(surah_match("آل‌عمران"),
                         (3, "آل عمران", "آل‌عمران", "exact"))
        self.assertEqual(surah_match("آل عمران"),
                         (3, "آل عمران", "آل‌عمران", "exact"))


class TestSU2ShortNames(unittest.TestCase):
    """لنگرهای canonical: ص=38، ق=50 (فقط exact یا با پیشوند سور/سوره)."""

    def test_su02_saad(self):
        self.assertEqual(surah_match("ص"), (38, "ص", "ص", "exact"))
        self.assertEqual(surah_match("سوره ص"), (38, "ص", "ص", "exact"))
        self.assertEqual(surah_match("سورة ص"), (38, "ص", "ص", "exact"))
        self.assertEqual(surah_match("سورص"), (38, "ص", "ص", "exact"))

    def test_su03_qaf(self):
        self.assertEqual(surah_match("ق"), (50, "ق", "ق", "exact"))
        self.assertEqual(surah_match("سوره ق"), (50, "ق", "ق", "exact"))
        self.assertEqual(surah_match("سورق"), (50, "ق", "ق", "exact"))


class TestSU4NegativesAndMentions(unittest.TestCase):
    def test_su04_rejected(self):
        # عناوین عمومی پیکره (مفردات/تفسیر) و «سور» بدون نام → رد می‌شوند
        # (در پیکره‌ی واقعی 274 عنوان «سور...» عمومی همین‌جور رد شدند).
        for t in ("مفردات", "تفسیر", "سوره", "سور", "سوره بقره: آیات ۱-۵",
                  "", None):
            self.assertIsNone(surah_match(t), t)

    def test_su05_mentions(self):
        self.assertEqual(surah_mention("آیات سوره بقره درباره‌ی نزول"),
                         (2, "البقرة", "بقره"))
        # regex «سور[هي]» فقط فرمِ فارسی‌ی ه را می‌بیند؛ فرمِ عربی ة («سورة ...»)
        # در mention=None می‌شود ولی فرمِ عنوان آن در شاخه‌ی exact از surah_match
        # پوشش می‌خورد (pin روی رفتار واقعیِ verified — self-test 18/18).
        self.assertIsNone(surah_mention("سورة الناس"))
        self.assertEqual(surah_match("سورة الناس"),
                         (114, "الناس", "ناس", "exact"))
        self.assertIsNone(surah_mention("در آیه‌ای دیگر"))
        self.assertIsNone(surah_mention("سوره xyz"))


# ===========================================================================
# فیکستور غنی‌سازی — 12 صفحه (2 جلد)؛ همه‌ی 6 مقدار summary_status
# ===========================================================================
ED = "%s__%s" % (S.WORK, S.EDITION)
P = lambda i: "%s__vol001__p%d" % (ED, i)
P2 = lambda i: "%s__vol002__p%d" % (ED, i)
RID = lambda i: S.heading_record_id_of(P(i))
R2ID = lambda i: S.heading_record_id_of(P2(i))

LONG1 = ("این متن صفحه‌ی سوم است و شامل تفسیر آیه‌ای، روایات متعدد و نقل‌های "
         "گوناگون از علما و مفسران برای آزمون کامل خط تولید پیکره است؛ "
         "طول آن قطعاً از صد کاراکتر بیشتر می‌شود.")
LONG2 = ("متن صفحه‌ی پنجم با مجموعه‌ای از روایات و تفسیرهای آیه‌ای و نقل‌های "
         "متعدد از مفسران برای پوشش صحنه‌ی واجدشرطِ دوم در این آزمون آفلاین.")
SHORT50 = "متن پنجاه‌کاراکتری برای آزمونِ وضعیت skipped_next_too_short."
assert len(LONG1.strip()) >= 101
assert len(LONG2.strip()) >= 101
assert 0 < len(SHORT50.strip()) < 100

TEXTS = {
    1: "متن کامل صفحه‌ی اول با تفسیر و روایت کافی برای آزمون.",
    2: "سوره بقره",
    3: LONG1,
    4: "تفسیر",
    5: LONG2,
    6: "* * *",
    7: "مفردات",
    8: "متن کامل صفحه‌ی هشت از جلد دوم با نقل‌های کافی.",
    9: "تفسیر",
    10: SHORT50,
    11: "مفردات",
    12: "",
}

EXPECTED_STATUS = {
    RID(2): ENR.STATUS_OK,
    RID(4): ENR.STATUS_FAILED,
    RID(7): ENR.STATUS_VOLUME_END,
    R2ID(9): ENR.STATUS_NEXT_SHORT,
    R2ID(11): ENR.STATUS_NEXT_BLANK,
}
EXPECTED_NPI = {RID(2): 3, RID(4): 5, RID(7): None, R2ID(9): 10, R2ID(11): 12}
SUMMARY2 = ("خط اول: موضوع صفحه‌ی بعد (تفسیر آیه‌ای)\n"
            "خط دوم: نکته‌ی محوری نقل‌شده\n"
            "خط سوم: ارتباط با عنوان «سوره بقره»")


def _enrich_fixture(jsonl_path):
    recs = []
    for i in range(1, 13):
        section = 1 if i <= 7 else 2
        recs.append(page_rec(
            i,
            "https://tasnim.hamtaa.org/book/79?section=%d&item_index=%d"
            % (section, i),
            i, TEXTS[i], fa(i), barg_export=i))
    with open(jsonl_path, "w", encoding="utf-8", newline="\n") as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


class EnrichBase(unittest.TestCase):
    """زنجیره‌ی v0001→v0002→v0003 + checkpoint؛ هر test ادامه‌ی خود را دارد."""

    def setUp(self):
        C.force_utf8_stdio()
        self.tmp = tempfile.mkdtemp(prefix="pct-pcm207c-v4-")
        self.data_root = os.path.join(self.tmp, "data", "tasnim")
        self.fix = os.path.join(self.tmp, "src")
        os.makedirs(self.fix, exist_ok=True)
        self.jsonl = os.path.join(self.fix, "tasnim-corpus.jsonl")
        _enrich_fixture(self.jsonl)
        self.run_cli(["build-corpus", "--jsonl", self.jsonl,
                      "--data-root", self.data_root])
        self.run_cli(["build-semantic", "--data-root", self.data_root,
                      "--base", "v0001"])
        self.run_cli(["build-semantic", "--data-root", self.data_root,
                      "--base", "v0002", "--contract",
                      SEM.SEMANTIC_SCHEMA_VERSION_V3])
        self.ckpt = os.path.join(self.fix, "summaries.jsonl")
        with open(self.ckpt, "w", encoding="utf-8", newline="\n") as f:
            f.write(C.canonical_json_line(self._entry(RID(2))).decode("utf-8"))

    def tearDown(self):
        try:
            shutil.rmtree(self.tmp)
        except Exception:
            pass

    @staticmethod
    def _entry(rid, summary=SUMMARY2):
        return {"record_id": rid, "summary": summary,
                "model": "fake-model", "model_version": "1.0",
                "prompt_version": "hc-prompt/1.0", "temperature": 0.3,
                "max_tokens": 300, "generated_at": "2026-01-01T00:00:00Z"}

    def _write_ckpt(self, name, entry):
        p = os.path.join(self.fix, name)
        with open(p, "w", encoding="utf-8", newline="\n") as f:
            f.write(C.canonical_json_line(entry).decode("utf-8"))
        return p

    def run_cli(self, argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = CL.main(argv)
        self.assertEqual(rc, 0,
                         "CLI failed rc=%d: %s\n%s" % (rc, argv, out.getvalue()))
        return out.getvalue()

    def run_cli_expect(self, argv, rc):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            got = CL.main(argv)
        self.assertEqual(got, rc,
                         "expected rc=%d for %s\n%s" % (rc, argv,
                                                        out.getvalue()[:400]))
        return out.getvalue()

    def builds_dir(self):
        return os.path.join(self.data_root, "corpus", "builds")

    def build_v4(self):
        self.run_cli(["build-enriched", "--data-root", self.data_root,
                      "--base", "v0003", "--summaries", self.ckpt])
        v4 = os.path.join(self.builds_dir(), "v0004")
        self.assertTrue(os.path.isdir(v4))
        return v4


class TestE01EnrichUnits(EnrichBase):
    def test_e01_normalize_summary(self):
        self.assertIsNone(ENR.normalize_summary("a\nb\nc\nd"))
        self.assertIsNone(ENR.normalize_summary("  \n\n "))
        self.assertEqual(ENR.normalize_summary("  a \n\n b \n"), "a\nb")

    def test_e02_generate_summaries_fake_chat(self):
        v3 = os.path.join(self.builds_dir(), "v0003")

        def fake_chat(h, np_):
            return {"summary": "خط اول\nخط دوم\nخط سوم «%s»" % h["heading_text"],
                    "model": "fake-model", "model_version": "1.0",
                    "prompt_version": "hc-prompt/1.0",
                    "temperature": 0.3, "max_tokens": 300}

        gs = os.path.join(self.fix, "gen.jsonl")
        r1 = ENR.generate_summaries(v3, gs, fake_chat, pace_seconds=0)
        s1 = r1["stats"]
        self.assertEqual((s1["eligible"], s1["generated"], s1["skipped"]),
                         (2, 2, 3), s1)
        r2 = ENR.generate_summaries(v3, gs, fake_chat, pace_seconds=0)
        self.assertEqual((r2["stats"]["resumed"], r2["stats"]["generated"]),
                         (2, 0), r2["stats"])
        r3 = ENR.generate_summaries(
            v3, os.path.join(self.fix, "gen-fail.jsonl"),
            lambda h, n: None, pace_seconds=0)
        self.assertEqual(r3["stats"]["failed"], 2)
        self.assertEqual(r3["checkpoint_count"], 0)
        r4 = ENR.generate_summaries(
            v3, os.path.join(self.fix, "gen-limit.jsonl"), fake_chat,
            limit=1, resume=False, pace_seconds=0)
        self.assertEqual((r4["stats"]["generated"], r4["stats"]["filtered"]),
                         (1, 1), r4["stats"])


class TestV401BuildAndFields(EnrichBase):
    def test_v401_records_and_fields(self):
        v4 = self.build_v4()
        h3 = C.read_jsonl(os.path.join(self.builds_dir(), "v0003",
                                       S.HC_FILE_HEADING))
        h4 = C.read_jsonl(os.path.join(v4, S.HC_FILE_HEADING))
        self.assertEqual([r["record_id"] for r in h4],
                         [RID(2), RID(4), RID(7), R2ID(9), R2ID(11)])
        self.assertEqual([r["record_id"] for r in h4],
                         [r["record_id"] for r in h3])
        b_by = {r["record_id"]: r for r in h3}
        for r in h4:
            b = b_by[r["record_id"]]
            for f, v in b.items():
                if f == "heading_hash":
                    continue
                self.assertEqual(r.get(f), v, "base field %s changed" % f)
            for f in ENR.NEW_FIELDS:
                self.assertIn(f, r, "new field missing: %s" % f)
        by = {r["record_id"]: r for r in h4}
        for rid, st in EXPECTED_STATUS.items():
            self.assertEqual(by[rid]["summary_status"], st, rid)
        for rid, npi in EXPECTED_NPI.items():
            self.assertEqual(by[rid]["next_page_item_index"], npi, rid)
        r2 = by[RID(2)]
        self.assertEqual(r2["retrieval_context_summary"], SUMMARY2)
        self.assertEqual(r2["summary_sha256"], C.sha256_text(SUMMARY2))
        meta = r2["summary_meta"] or {}
        self.assertEqual(meta.get("method"), ENR.SUMMARY_METHOD)
        self.assertEqual(meta.get("model"), "fake-model")
        self.assertEqual(meta.get("max_lines"), 3)
        exp_rc = ENR.retrieval_context_of(r2, SUMMARY2)
        self.assertEqual(r2["retrieval_context"], exp_rc)
        self.assertEqual(r2["retrieval_context_sha256"], C.sha256_text(exp_rc))
        for k in (RID(4), RID(7), R2ID(9), R2ID(11)):
            self.assertIsNone(by[k]["retrieval_context_summary"])
            self.assertIsNone(by[k]["summary_meta"])
            self.assertIsNone(by[k]["summary_sha256"])
        for r in h4:
            meta2 = {k2: v2 for k2, v2 in r.items() if k2 != "heading_hash"}
            self.assertEqual(r.get("heading_hash"),
                             C.sha256_text(C.canonical_json(meta2).decode(
                                 "utf-8")))


class TestV402UntouchedAndManifest(EnrichBase):
    def test_v402_base_untouched_and_manifest_chain(self):
        v3 = os.path.join(self.builds_dir(), "v0003")
        pre = {n: C.sha256_file(os.path.join(v3, n)) for n in
               ("pages.jsonl", "context-records.jsonl", S.HC_FILE_CONTEXT,
                "heading-records.jsonl", "corpus.json", "manifest.json")}
        v4 = self.build_v4()
        for n in ENR.UNTOUCHED_FILES:
            self.assertEqual(C.sha256_file(os.path.join(v4, n)), pre[n],
                             "%s not byte-identical to base" % n)
        for n, sha in pre.items():
            self.assertEqual(C.sha256_file(os.path.join(v3, n)), sha,
                             "base v0003 %s modified" % n)
        self.assertEqual(sorted(os.listdir(self.builds_dir())),
                         ["v0001", "v0002", "v0003", "v0004"])
        m4 = M.load_manifest(v4)
        m3 = M.load_manifest(v3)
        prev = m4.get("prev") or {}
        self.assertEqual(prev.get("version"), "v0003")
        self.assertEqual(prev.get("sha256"),
                         C.sha256_text(C.canonical_json(m3).decode("utf-8")))
        d4 = m4.get("data") or {}
        self.assertEqual(d4.get("previous_version"), "v0003")
        self.assertEqual(len(d4.get("files") or {}), 5)


class TestV403Validation(EnrichBase):
    def test_v403_validate_semantic_and_corpus(self):
        v4 = self.build_v4()
        ok, errs, warns = SEM.validate_semantic(v4, self.data_root)
        self.assertTrue(ok, "validate_semantic: %s" % errs)
        ok2, errs2, warns2 = VAL.validate_corpus(v4)
        self.assertTrue(ok2, "validate_corpus: %s" % errs2)


class TestV404CorpusBlock(EnrichBase):
    def test_v404_cs207_corpus_block(self):
        v4 = self.build_v4()
        c4 = C.read_json(os.path.join(v4, "corpus.json"))
        m3 = M.load_manifest(os.path.join(self.builds_dir(), "v0003"))
        sem = c4["semantic"]
        self.assertEqual(sem["schema_version"], "cs-20.7")
        self.assertEqual(sem["prev_contract"], "cs-20.6")
        bc = sem.get("base_corpus") or {}
        self.assertEqual(bc.get("version"), "v0003")
        self.assertEqual(bc.get("content_sha256"),
                         (m3.get("data") or {}).get("content_sha256"))
        self.assertEqual(bc.get("path_rel"), "corpus/builds/v0003")
        enr = sem.get("enrichment") or {}
        exp_census = {"ok": 1, "failed": 1, "skipped_volume_end": 1,
                      "skipped_next_too_short": 1, "skipped_next_blank": 1,
                      "skipped_no_next": 0}
        self.assertEqual(enr.get("status_counts"), exp_census)
        self.assertEqual(enr.get("method"), "llm-summary/1.0")
        self.assertEqual(enr.get("prompt_version"), "hc-prompt/1.0")
        self.assertEqual(enr.get("model"), "fake-model")
        self.assertEqual(enr.get("model_version"), "1.0")
        self.assertEqual(enr.get("temperature"), 0.3)
        self.assertEqual(enr.get("max_tokens"), 300)
        self.assertEqual(enr.get("min_next_page_chars"), 100)
        self.assertEqual(enr.get("max_summary_lines"), 3)
        ss = enr.get("summaries_source") or {}
        self.assertEqual(ss.get("count"), 1)
        self.assertEqual(ss.get("file"), "summaries.jsonl")
        self.assertEqual(ss.get("sha256"), C.sha256_file(self.ckpt))
        self.assertEqual(((sem.get("hidden_context") or {})
                          .get("heading_records") or {})
                         .get("record_version"), "v2")
        en7 = (((c4.get("stats") or {}).get("semantic") or {})
               .get("hidden_context", {}).get("enrichment") or {})
        self.assertEqual(en7.get("summary_ok_count"), 1)
        self.assertEqual(en7.get("summary_failed_count"), 1)
        self.assertEqual(en7.get("summary_skipped_count"), 3)
        self.assertEqual(en7.get("status_counts"), exp_census)


class TestV405Leakage(EnrichBase):
    """قاعده‌ی سخت: خلاصه فقط متادیتای retrieval است و هرگز در خروجی
    عمومی (corpus.json) یا رکورد صفحه‌ی عنوان (pages.jsonl) نمی‌آید."""

    def test_v405_summary_not_in_public_outputs(self):
        v4 = self.build_v4()
        with open(os.path.join(v4, "corpus.json"), "rb") as f:
            pub = f.read()
        blob = SUMMARY2.encode("utf-8")
        self.assertNotIn(blob, pub, "summary leaked into public corpus.json")
        hpage = None
        with open(os.path.join(v4, "pages.jsonl"), "r", encoding="utf-8") as f:
            for line in f:
                rec = json.loads(line)
                if rec.get("page_id") == P(2):
                    hpage = rec
                    break
        self.assertIsNotNone(hpage, "heading page P(2) not found")
        hline = C.canonical_json_line(hpage)
        self.assertNotIn(blob, hline,
                         "summary leaked into heading page record")


class TestV406Idempotency(EnrichBase):
    def test_v406_reused_no_new_version(self):
        self.build_v4()
        out = self.run_cli(["build-enriched", "--data-root", self.data_root,
                            "--base", "v0003", "--summaries", self.ckpt])
        self.assertIn("REUSED v0004", out)
        self.assertEqual(sorted(os.listdir(self.builds_dir())),
                         ["v0001", "v0002", "v0003", "v0004"])


class TestV407Negatives(EnrichBase):
    def test_v407_five_negative_cases(self):
        base = ["--data-root", self.data_root]
        # 1) خلاصه برای heading واجدشرط‌نشدنی (پایان جلد)
        p1 = self._write_ckpt("ckpt-ineligible.jsonl", self._entry(RID(7)))
        self.run_cli_expect(["build-enriched"] + base + ["--base", "v0003",
                                     "--summaries", p1], 2)
        # 2) خلاصه‌ی 4 خطی (حد 3 خط)
        p2 = self._write_ckpt("ckpt-4line.jsonl",
                              self._entry(RID(2), summary="a\nb\nc\nd"))
        self.run_cli_expect(["build-enriched"] + base + ["--base", "v0003",
                                     "--summaries", p2], 2)
        # 3) فایل checkpoint موجود نیست
        self.run_cli_expect(["build-enriched"] + base + ["--base", "v0003",
                                     "--summaries",
                                     os.path.join(self.fix, "nope.jsonl")], 2)
        # 4) base v0002 قرارداد cs-20.6 ندارد
        self.run_cli_expect(["build-enriched"] + base + ["--base", "v0002",
                                     "--summaries", self.ckpt], 2)
        # 5) cs-20.7 فقط از مسیر build-enriched ساخته می‌شود
        self.run_cli_expect(["build-semantic"] + base + ["--base", "v0003",
                                     "--contract", "cs-20.7"], 2)


class TestV408Tamper(EnrichBase):
    def test_v408_clean_passes(self):
        v3 = os.path.join(self.builds_dir(), "v0003")
        v4 = self.build_v4()
        ok, errs, warns = ENR.validate_enriched(v4, v3)
        self.assertTrue(ok, errs)
        self.assertEqual(errs, [])

    def test_v408b_base_field_changed(self):
        v3 = os.path.join(self.builds_dir(), "v0003")
        v4 = self.build_v4()
        t1 = os.path.join(self.tmp, "tamper1")
        shutil.copytree(v4, t1)
        hp = os.path.join(t1, S.HC_FILE_HEADING)
        recs_t = C.read_jsonl(hp)
        for rt in recs_t:
            if rt["record_id"] == RID(2):
                rt["heading_text"] = "تغییری غیرمجاز"
        with open(hp, "w", encoding="utf-8", newline="\n") as f:
            for rt in recs_t:
                f.write(json.dumps(rt, ensure_ascii=False) + "\n")
        ok_t, errs_t, _ = ENR.validate_enriched(t1, v3)
        self.assertFalse(ok_t)
        self.assertTrue(any("base field changed" in e for e in errs_t),
                        errs_t[:5])

    def test_v408c_page_text_modified(self):
        v3 = os.path.join(self.builds_dir(), "v0003")
        v4 = self.build_v4()
        t2 = os.path.join(self.tmp, "tamper2")
        shutil.copytree(v4, t2)
        pp = os.path.join(t2, "pages.jsonl")
        pr = C.read_jsonl(pp)
        for r in pr:
            if r.get("page_id") == P(2):
                r["text"] = (r.get("text") or "") + "\n" + SUMMARY2
        with open(pp, "w", encoding="utf-8", newline="\n") as f:
            for r in pr:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        ok_t2, errs_t2, _ = ENR.validate_enriched(t2, v3)
        self.assertFalse(ok_t2)
        self.assertTrue(any(("LEAK" in e and "heading page" in e)
                            or "pages.jsonl" in e for e in errs_t2),
                        errs_t2[:5])

    def test_v408d_leak_when_summary_is_own_page_text(self):
        """خلاصه = متن خودِ صفحه‌ی عنوان، در حالی‌که pages.jsonl بایت‌به‌بایت
        با base است → باید دقیقاً خطای LEAK/heading page آگهی شود."""
        v3 = os.path.join(self.builds_dir(), "v0003")
        v4 = self.build_v4()
        t2b = os.path.join(self.tmp, "tamper2b")
        shutil.copytree(v4, t2b)
        hp2b = os.path.join(t2b, S.HC_FILE_HEADING)
        recs_2b = C.read_jsonl(hp2b)
        for rt in recs_2b:
            if rt["record_id"] == RID(2):
                rt["retrieval_context_summary"] = "سوره بقره"
        with open(hp2b, "w", encoding="utf-8", newline="\n") as f:
            for rt in recs_2b:
                f.write(json.dumps(rt, ensure_ascii=False) + "\n")
        ok_2b, errs_2b, _ = ENR.validate_enriched(t2b, v3)
        self.assertFalse(ok_2b)
        self.assertTrue(any(("LEAK" in e and "heading page" in e)
                            for e in errs_2b), errs_2b[:5])


# ===========================================================================
# DS01-DS05 — rebuild دیتاست + --volume-id (جلد بی‌شماره)
# ===========================================================================
class TestDS01VolumeId(unittest.TestCase):
    """فیکستور 21 رکوردی test_corpus_tasnim: جلد 1، جلد 2، جلد 31 +
    2 صفحه‌ی جلد بی‌شماره (volume_no=None)."""

    def setUp(self):
        C.force_utf8_stdio()
        self.tmp = tempfile.mkdtemp(prefix="pct-pcm207c-ds-")
        self.data_root = os.path.join(self.tmp, "data", "tasnim")
        self.fix = os.path.join(self.tmp, "src")
        os.makedirs(self.fix, exist_ok=True)
        self.jsonl = os.path.join(self.fix, "tasnim-corpus.jsonl")
        self.jsone = os.path.join(self.fix, "tasnim-corpus.json")
        self.summary = os.path.join(self.fix, "export-summary.json")
        make_fixture(self.jsonl, self.jsone, self.summary)
        self.tag = self._build_corpus()

    def tearDown(self):
        try:
            shutil.rmtree(self.tmp)
        except Exception:
            pass

    def _build_corpus(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = CL.main(["build-corpus", "--jsonl", self.jsonl,
                          "--json", self.jsone, "--summary", self.summary,
                          "--data-root", self.data_root])
        self.assertEqual(rc, 0, out.getvalue())
        builds = os.path.join(self.data_root, "corpus", "builds")
        return [t for t in os.listdir(builds) if t.startswith("v")][0]

    def _nameless_volume_id(self):
        pages = C.read_jsonl(os.path.join(self.data_root, "corpus", "builds",
                                          self.tag, "pages.jsonl"))
        for p in pages:
            if (p["volume"] or {}).get("volume_no") is None:
                return p["volume_id"]
        self.fail("no nameless-volume page in fixture corpus")

    def _latest_dataset(self, pct):
        ddir = os.path.join(self.data_root, "datasets", V.pct_dirname(pct))
        tags = sorted(t for t in os.listdir(ddir) if t.startswith("v"))
        self.assertTrue(tags)
        return os.path.join(ddir, tags[-1])

    def test_ds01_volume_id_100(self):
        vid = self._nameless_volume_id()
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = CL.main(["build-dataset", "--data-root", self.data_root,
                          "--corpus", self.tag, "--percentage", "100",
                          "--volume-id", vid])
        self.assertEqual(rc, 0, out.getvalue())
        dtag = self._latest_dataset(100)
        pages = C.read_jsonl(os.path.join(dtag, "pages.jsonl"))
        self.assertEqual(len(pages), 2)  # جلد بی‌شماره = 2 صفحه (17 و 18)
        self.assertTrue(all(p["volume_id"] == vid for p in pages))
        meta = C.read_json(os.path.join(dtag, "dataset.json"))
        self.assertEqual(meta["policy"]["volume_scope"], "volume_id=%s" % vid)
        m = M.load_manifest(dtag)
        self.assertEqual((m.get("data") or {}).get("volume_scope"),
                         {"volume_id": vid})

    def test_ds02_volume_no_compat(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = CL.main(["build-dataset", "--data-root", self.data_root,
                          "--corpus", self.tag, "--percentage", "100",
                          "--volume", "2"])
        self.assertEqual(rc, 0, out.getvalue())
        dtag = self._latest_dataset(100)
        pages = C.read_jsonl(os.path.join(dtag, "pages.jsonl"))
        self.assertTrue(all(p["volume"]["volume_no"] == 2 for p in pages))
        meta = C.read_json(os.path.join(dtag, "dataset.json"))
        self.assertEqual(meta["policy"]["volume_scope"], "volume=2")

    def test_ds03_both_volume_args_rejected(self):
        vid = self._nameless_volume_id()
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = CL.main(["build-dataset", "--data-root", self.data_root,
                          "--corpus", self.tag, "--percentage", "100",
                          "--volume", "2", "--volume-id", vid])
        self.assertEqual(rc, 2, out.getvalue())

    def test_ds04_unknown_volume_id_rejected(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = CL.main(["build-dataset", "--data-root", self.data_root,
                          "--corpus", self.tag, "--percentage", "100",
                          "--volume-id", "nosuchvolume"])
        self.assertEqual(rc, 2, out.getvalue())

    def test_ds05_pct50_of_nameless_volume(self):
        vid = self._nameless_volume_id()
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = CL.main(["build-dataset", "--data-root", self.data_root,
                          "--corpus", self.tag, "--percentage", "50",
                          "--volume-id", vid])
        self.assertEqual(rc, 0, out.getvalue())
        dtag = self._latest_dataset(50)
        pages = C.read_jsonl(os.path.join(dtag, "pages.jsonl"))
        self.assertEqual(len(pages), 1)  # 50٪ از 2 صفحه = 1
        self.assertTrue(all(p["volume_id"] == vid for p in pages))


if __name__ == "__main__":
    unittest.main()

# -*- coding: utf-8 -*-
"""test_corpus_backfill.py — PCM-20.6.3: سافکار Backfill (Track A, Phase 1).

اجرا:  python -X utf8 -m unittest test_corpus_backfill -v

همه‌ی آزمون‌ها **آفلاین** و بدون شبکه: transport تزریق‌شده (FakeTransport)
و فیکستورهای مصنوعی کوچک. هیچ فایل واقعی پیکره و هیچ درخواست زنده
مورد استفاده نیست.

آزمون‌ها:
  BF01  بازحساب شکاف: 8 بازه‌ی مفقود روی فیکستور کوچک (قطعی)
  BF01b بازتولید اعداد Phase-0 روی دیتای واقعی v0003 (skip اگر نبود)
  BF02  قطعی بودن گزارش + شمارنده‌ها
  BF03  ساخت URL + استخراج item_index + cross-check
  BF04  برنامه‌ی Fetch: ترتیب صعودی، jitter، budget-split، تخمین زمان
  BF05  پارس پاسخ chunk-detail + payload_sha256
  BF06  cross-check item_index (mismatch → ParseError)
  BF07  نسبت‌دادن جلد: resolved از شواهد (payload/section)
  BF08  ابهام جلد: شواهد متضاد → ambiguous (تخمین ممنوع)
  BF09  unresolved + همسایه‌ها فقط به‌عنوان راهنما
  BF10  بازگشت باگ barg: «۳۹٬۰۰۵» → 39005 (نه 39)
  BF11  flags کیفیت: ترتیب ثابت (empty/short/truncated/no_barg/...)
  BF12  تشخیص تغییر: new/unchanged/changed (سیاست old-wins)
  BF13  رکورد کامل Backfill: provenance + change + volume
  BF14  checkpoint: idempotency + save/load + done نهایی
  BF15  checkpoint: plan_sha mismatch → resume ممنوع
  BF16  fetch با retry/backoff: 500 → 200 (attempts + sleeps)
  BF17  404 = شکست دائمی (بدون retry)
  BF18  resume: budget 2 → دو اجرا → همه‌ی آیتم‌ها exact-once
  BF19  CLI dry-run end-to-end (بدون transport، بدون guard)
  BF20  guard زنده: flag بدون token / token غلط / بدون flag → block
  BF21  diff flags (new/changed/duplicate/absent) + registry rollback
  BF22  manifest v0004: prev ← v0003 + rollback metadata
"""
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

from corpus.tasnim import common as C
from corpus.tasnim import manifest as M
from corpus.tasnim import versioning as V
from corpus.tasnim.backfill import checkpoint as CK
from corpus.tasnim.backfill import cli as CL
from corpus.tasnim.backfill import fetch_plan as FP
from corpus.tasnim.backfill import gap as BG
from corpus.tasnim.backfill import manifest as BM
from corpus.tasnim.backfill import parse as P
from corpus.tasnim.backfill import runner as RN
from corpus.tasnim.backfill import transport as TR

# دیتای واقعی v0003 (اختیاری — با TASNIM_V0003_DIR قابل‌تنظیم)
REAL_V0003_PAGES = os.path.join(
    os.environ.get("TASNIM_V0003_DIR",
                   os.path.join("data", "tasnim", "pcm20_5",
                                "corpus", "builds", "v0003")),
    "pages.jsonl")

FIXED_TS = "2026-01-01 00:00:00"


# --------------------------------------------------------------------------- fixtures
def write_jsonl(path, records):
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        for r in records:
            f.write(C.canonical_json_line(r).decode("utf-8"))


def page(idx, text="متن پایه", vol_no=1):
    """رکورد pages.jsonl (فرمت build) برای فیکستورهای کوچک."""
    return {
        "page_id": "vol%03d__p%s" % (vol_no or 0, idx),
        "item_index": idx,
        "text": text,
        "volume": {"volume_id": "vol%03d" % (vol_no or 0),
                   "volume_no": vol_no,
                   "volume_title": "جلد %s" % (vol_no or "؟")},
        "content_hash": "h%04d" % idx,
    }


def body(idx, text, section=None, barg=None, include_idx=True):
    """بدنه‌ی JSON پاسخ chunk-detail برای item_index."""
    d = {"original_text": text}
    if section is not None:
        d["section"] = section
    if include_idx:
        d["item_index"] = idx
    if barg is not None:
        d["values"] = {"برگ": barg}
    return json.dumps(d, ensure_ascii=False)


def mini_pages_indices():
    """مجموعه‌ی 12 آیتم موجود → 6 بازه‌ی مفقود."""
    return [1, 2, 3, 4, 100, 200, 300, 400, 500, 600, 700, 800]


class BackfillBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="pct-bf-")
        self._sleeps = []

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def p(self, name):
        return os.path.join(self.tmp, name)

    def write_pages(self, name, indices, vol_no=1, texts=None):
        recs = [page(i, (texts or {}).get(i, "متن %d" % i), vol_no)
                for i in indices]
        path = self.p(name)
        write_jsonl(path, recs)
        return path


# --------------------------------------------------------------------------- BF01/02 gap
class TestBF01GapRecompute(unittest.TestCase):
    def test_bf01_six_ranges_from_synthetic_mini_corpus(self):
        tmp = tempfile.mkdtemp(prefix="pct-bf01-")
        try:
            pages = self_write_pages(mini_pages_indices())
            report = BG.build_gap_report_v2(pages)
            self.assertEqual(report["contract"], "gap-report-2")
            runs = BG.runs_of(report)
            self.assertEqual(runs, [[5, 99], [101, 199], [201, 299],
                                    [301, 399], [401, 499], [501, 599],
                                    [601, 699], [701, 799]])
            self.assertEqual(report["gaps"]["runs_count"], 8)
            self.assertEqual(report["gaps"]["missing_count"], 788)
            # attribute: همسایه‌های موجود ثبت شده‌اند
            d0 = report["gaps"]["runs"][0]
            self.assertEqual(d0["before_item_index"], 4)
            self.assertEqual(d0["after_item_index"], 100)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_bf01b_real_v0003_reproduces_phase0_numbers(self):
        if not os.path.exists(REAL_V0003_PAGES):
            self.skipTest("real v0003 data absent (worktree)")
        report = BG.build_gap_report_v2(REAL_V0003_PAGES)
        runs = BG.runs_of(report)
        self.assertEqual(runs, [
            [3649, 11182], [11205, 39003], [44957, 49956],
            [55699, 55701], [55715, 59590], [89280, 90310]])
        self.assertEqual(report["gaps"]["missing_count"], 45243)
        self.assertEqual(report["pages"]["total_records"], 45844)
        self.assertEqual(report["pages"]["distinct_item_index"], 45835)
        self.assertEqual(report["pages"]["dup_count"], 9)


def self_write_pages(indices):
    d = tempfile.mkdtemp(prefix="pct-bf01p-")
    recs = [page(i) for i in indices]
    path = os.path.join(d, "pages.jsonl")
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        for r in recs:
            f.write(C.canonical_json_line(r).decode("utf-8"))
    return path


class TestBF02GapDeterminism(BackfillBase):
    def test_bf02_same_input_same_content_sha(self):
        pages = self.write_pages("pages.jsonl", mini_pages_indices())
        r1 = BG.build_gap_report_v2(pages)
        r2 = BG.build_gap_report_v2(pages)
        self.assertEqual(r1["content_sha256"], r2["content_sha256"])
        self.assertEqual(len(r1["summary_fa"]) >= 4, True)
        self.assertIn("بازه", r1["summary_fa"][2])


# --------------------------------------------------------------------------- BF03/04 plan
class TestBF03Urls(BackfillBase):
    def test_bf03_url_build_and_item_index_extraction(self):
        url = FP.url_for_item_index(3649)
        self.assertEqual(
            url, "https://tasnim.hamtaa.org/api/v1/files/tasnim/"
                 "chunk-detail?item_index=3649")
        self.assertEqual(FP.parse_item_index_from_url(url), 3649)
        self.assertEqual(P.extract_item_index(url, 3649), 3649)
        with self.assertRaises(P.ParseError):
            P.extract_item_index(url, 3650)  # mismatch
        with self.assertRaises(P.ParseError):
            P.extract_item_index("https://x/y")  # بدون item_index


class TestBF04PlanMath(BackfillBase):
    def test_bf04_ordered_plan_jitter_budget_and_estimate(self):
        pages = self.write_pages(
            "pages.jsonl", [1, 2, 5, 6, 7, 10, 11])  # gaps: 3-4, 8-9
        report = BG.build_gap_report_v2(pages)
        plan = FP.build_fetch_plan(report, max_requests_per_run=3)
        self.assertEqual(plan["contract"], "fetch-plan-1")
        self.assertEqual(
            [it["item_index"] for it in plan["items"]], [3, 4, 8, 9])
        self.assertEqual(plan["totals"]["planned_requests"], 4)
        # jitter: همه‌ی delays در بازه‌ی 15 ± 30٪
        for it in plan["items"]:
            self.assertGreaterEqual(it["planned_delay_seconds"], 10.5)
            self.assertLessEqual(it["planned_delay_seconds"], 19.5)
            self.assertEqual(FP.parse_item_index_from_url(it["url"]),
                             it["item_index"])
        # budget-split
        self.assertEqual(len(FP.split_plan(plan, 0)), 3)
        self.assertEqual(len(FP.split_plan(plan, 1)), 1)
        self.assertEqual(FP.split_plan(plan, 1)[0]["item_index"], 9)
        # تخمین زمان: 4 درخواست × 15 ثانیه ≈ 0.2 ساعت
        self.assertEqual(plan["totals"]["estimated_runs_at_budget"], 2)
        self.assertAlmostEqual(plan["totals"]["estimated_minutes_at_target"],
                               1.0, places=1)
        # قطعی: دو بار ساخت → همان delays
        plan2 = FP.build_fetch_plan(report, max_requests_per_run=3)
        self.assertEqual(
            [i["planned_delay_seconds"] for i in plan["items"]],
            [i["planned_delay_seconds"] for i in plan2["items"]])


# --------------------------------------------------------------------------- BF05-06 parse
class TestBF05Parse(BackfillBase):
    def test_bf05_chunk_detail_parse(self):
        b = body(3, "متن کامل صفحه", section="تفسیر تسنیم جلد (12)")
        url = FP.url_for_item_index(3)
        parsed = P.parse_chunk_detail(b, url)
        self.assertEqual(parsed["text"], "متن کامل صفحه")
        self.assertEqual(parsed["section"], "تفسیر تسنیم جلد (12)")
        self.assertEqual(parsed["payload_item_index"], 3)
        self.assertIsNone(parsed["parse_error"])
        expect = C.sha256_text(
            C.canonical_json(json.loads(b)).decode("utf-8"))
        self.assertEqual(parsed["payload_sha256"], expect)

    def test_bf05b_non_json_and_missing_text(self):
        url = FP.url_for_item_index(3)
        with self.assertRaises(P.ParseError):
            P.parse_chunk_detail("<html>spa</html>", url)
        with self.assertRaises(P.ParseError):
            P.parse_chunk_detail(json.dumps({"section": "x"}), url)

    def test_bf06_payload_item_index_mismatch(self):
        b = body(4, "متن", section=None)  # payload idx=4
        url = FP.url_for_item_index(3)     # url idx=3
        with self.assertRaises(P.ParseError):
            P.parse_chunk_detail(b, url)


# --------------------------------------------------------------------------- BF07-09 volume
class TestBF07Volume(BackfillBase):
    def test_bf07_resolved_from_payload_section(self):
        url = FP.url_for_item_index(8)  # section ندارد
        vol = P.volume_candidates(url, "متنی بدون برچسب جلد",
                                  section="تفسیر تسنیم جلد (12)",
                                  vol_map={}, present_sorted=[1, 2, 5, 6, 7])
        self.assertEqual(vol["status"], P.VOL_RESOLVED)
        self.assertEqual(vol["volume_no"], 12)
        self.assertEqual(vol["candidates"][0]["evidence"], "payload_section")

    def test_bf07b_resolved_from_url_section_legacy(self):
        url = ("https://tasnim.hamtaa.org/payload?file_id=tasnim"
               "&section=tasnim-12&item_index=8")
        vol = P.volume_candidates(url, "متنی بدون برچسب",
                                  vol_map={}, present_sorted=[1, 2, 5, 6, 7])
        self.assertEqual(vol["status"], P.VOL_RESOLVED)
        self.assertEqual(vol["volume_no"], 12)
        self.assertEqual(vol["candidates"][0]["evidence"], "url_section")

    def test_bf08_ambiguous_evidence_never_guessed(self):
        url = ("https://tasnim.hamtaa.org/payload?file_id=tasnim"
               "&section=tasnim-12&item_index=8")
        vol = P.volume_candidates(url, "در ابتدای متن: جلد 5 آمده",
                                  vol_map={}, present_sorted=[1, 2, 5, 6, 7])
        self.assertEqual(vol["status"], P.VOL_AMBIGUOUS)
        self.assertTrue(vol["ambiguous"])
        self.assertIsNone(vol["volume_no"])  # هرگز انتخاب نمی‌شود
        self.assertEqual(sorted(c["volume_no"] for c in vol["candidates"]),
                         [5, 12])

    def test_bf09_unresolved_with_neighbor_guidance(self):
        vol_map = {7: (1, "جلد 1")}
        vol = P.volume_candidates(FP.url_for_item_index(8),
                                  "متنی ساده", vol_map=vol_map,
                                  present_sorted=[1, 2, 5, 6, 7])
        self.assertEqual(vol["status"], P.VOL_UNRESOLVED)
        self.assertIsNone(vol["volume_no"])
        # همسایه فقط راهنما (در شواهد نیست)
        self.assertEqual(vol["neighbors"]["before"]["item_index"], 7)
        self.assertEqual(vol["neighbors"]["before"]["volume_no"], 1)
        self.assertEqual(vol["candidates"], [])


# --------------------------------------------------------------------------- BF10-13 quality/change/record
class TestBF10BargRegression(BackfillBase):
    def test_bf10_known_barg_bug_regressed(self):
        # باگ parse_barg قدیمی: فقط اولین ریک → 39
        self.assertEqual(C.parse_barg_all_runs("۳۹٬۰۰۵"), 39005)
        self.assertEqual(C.parse_barg_all_runs("۵"), 5)
        self.assertIsNone(C.parse_barg_all_runs(None))
        self.assertIsNone(C.parse_barg_all_runs("بدون رقم"))

    def test_bf11_quality_flags_fixed_order(self):
        # ترتیب ثابت: empty → short → truncated → no_barg → missing → dup
        self.assertEqual(P.quality_flags("", None),
                         [S_F_EMPTY, S_F_NO_BARG, S_F_MISSING])
        self.assertEqual(P.quality_flags("کوتاه", None),
                         [S_F_SHORT, S_F_NO_BARG, S_F_MISSING])
        self.assertEqual(P.quality_flags("x" * 2000, 5, 3),
                         [S_F_TRUNC])
        self.assertEqual(P.quality_flags("x" * 2000, None, None),
                         [S_F_TRUNC, S_F_NO_BARG, S_F_MISSING])
        self.assertEqual(P.quality_flags("متن"*10, 5, 3, dup_in_base=True),
                         [S_F_DUP])
        self.assertEqual(P.quality_flags("متن "*6, 5, 3), [])


S_F_EMPTY = "empty"
S_F_SHORT = "short"
S_F_TRUNC = "truncated_at_2000"
S_F_DUP = "dup_item_index"
S_F_NO_BARG = "no_barg"
S_F_MISSING = "missing_item_index"


class TestBF12ChangeDetection(BackfillBase):
    def test_bf12_new_unchanged_changed(self):
        s1 = C.sha256_text("متن یک")
        s2 = C.sha256_text("متن دیگر")
        self.assertEqual(P.classify_change(s1, None, False), "new")
        self.assertEqual(P.classify_change(s1, s1, True), "unchanged")
        self.assertEqual(P.classify_change(s2, s1, True), "changed")
        self.assertEqual(P.classify_change(s2, None, True), "changed")


class TestBF13Record(BackfillBase):
    def test_bf13_full_backfill_record(self):
        pages = self.write_pages("pages.jsonl", [1, 2, 5, 6, 7])
        base = BM.base_index_from_pages(pages)
        vol_map = BG.volume_map_from_pages(pages)
        present = base["present_sorted"]

        b = body(8, "متن صفحه‌ی هشتم — کامل",
                 section="تفسیر تسنیم جلد (12)", barg="۳۹٬۰۰۵")
        url = FP.url_for_item_index(8)
        parsed = P.parse_chunk_detail(b, url)
        rec = P.build_backfill_record(
            8, url, 200, parsed, FIXED_TS, 1,
            RN.base_index_entry(base, 8), vol_map, present)

        self.assertEqual(rec["item_index"], 8)
        self.assertEqual(rec["change"], "new")  # idx 8 در base نیست
        self.assertFalse(rec["base_state"]["present_in_base"])
        self.assertEqual(rec["text_sha256"], C.sha256_text(rec["text"]))
        self.assertEqual(rec["barg"], 39005)  # parser اصلاح‌شده
        self.assertEqual(rec["barg_parse"], "ok")
        self.assertEqual(rec["volume"]["status"], P.VOL_RESOLVED)
        self.assertEqual(rec["volume"]["volume_no"], 12)
        self.assertEqual(rec["parser_version"], P.PARSER_VERSION)
        self.assertEqual(rec["policy_version"], P.POLICY_VERSION)
        self.assertEqual(rec["quality_flags"], [])


# --------------------------------------------------------------------------- BF14-15 checkpoint
class TestBF14Checkpoint(BackfillBase):
    def test_bf14_idempotent_stages_and_reload(self):
        path = self.p("ckpt.json")
        s = CK.CheckpointStore(path, "sha-X").load()
        s.mark(1, CK.STAGE_FETCHED, attempts=1)
        s.mark(1, CK.STAGE_PARSED)
        s.mark(1, CK.STAGE_WRITTEN)
        s.mark(1, CK.STAGE_DONE)
        s.mark(2, CK.STAGE_PERMANENT, reason="404")
        s.save()

        s2 = CK.CheckpointStore(path, "sha-X").load()
        self.assertTrue(s2.is_done(1))
        self.assertTrue(s2.is_terminal(2))
        # done نهایی است: mark دیگر روی آن اثر ندارد (idempotent)
        s2.mark(1, CK.STAGE_PERMANENT, reason="x")
        self.assertEqual(s2.state(1)["stage"], CK.STAGE_DONE)
        # resume: فقط آیتم 3 مانده
        plan_items = [{"item_index": 1}, {"item_index": 2},
                      {"item_index": 3}]
        self.assertEqual([i["item_index"]
                          for i in s2.pending_items(plan_items)], [3])
        c = s2.counts()
        self.assertEqual(c[CK.STAGE_DONE], 1)
        self.assertEqual(c[CK.STAGE_PERMANENT], 1)
        pf = s2.permanent_failures()
        self.assertEqual(pf[0]["item_index"], 2)
        self.assertEqual(pf[0]["reason"], "404")


class TestBF15CheckpointPlanLock(BackfillBase):
    def test_bf15_plan_sha_mismatch_blocks_resume(self):
        path = self.p("ckpt.json")
        s = CK.CheckpointStore(path, "sha-PLAN-A").load()
        s.mark(1, CK.STAGE_DONE)
        s.save()
        with self.assertRaises(CK.CheckpointError):
            CK.CheckpointStore(path, "sha-PLAN-B").load()
        # plan درست باز می‌شود
        s2 = CK.CheckpointStore(path, "sha-PLAN-A").load()
        self.assertTrue(s2.is_done(1))


# --------------------------------------------------------------------------- BF16-17 fetch/retry
class FlakyTransport:
    """n بار اول 500، بعدش 200 (بدون شبکه)."""

    def __init__(self, n_500, bodies):
        self.n_500 = n_500
        self.bodies = bodies
        self.calls = {}

    def get(self, url, user_agent=None, timeout=None):
        idx = FP.parse_item_index_from_url(url)
        c = self.calls.get(idx, 0)
        self.calls[idx] = c + 1
        if c < self.n_500:
            return {"status": 500, "body_text": ""}
        return {"status": 200, "body_text": self.bodies[idx]}


class TestBF16Retry(BackfillBase):
    def test_bf16_retry_with_exponential_backoff(self):
        sleeps = []
        t = FlakyTransport(2, {3: body(3, "متن", section="جلد (1)")})
        res = RN.fetch_with_retry(t, FP.url_for_item_index(3), "ua", 40.0,
                                  max_attempts=3, retry_base=30.0,
                                  sleep_fn=lambda s: sleeps.append(s))
        self.assertTrue(res["ok"])
        self.assertEqual(res["attempts"], 3)
        self.assertEqual(sleeps, [30.0, 90.0])  # backoff 30 → 90

    def test_bf17_404_is_permanent_no_retry(self):
        sleeps = []
        t = TR.FakeTransport(default_status=404)
        res = RN.fetch_with_retry(t, FP.url_for_item_index(9), "ua", 40.0,
                                  max_attempts=3, retry_base=30.0,
                                  sleep_fn=lambda s: sleeps.append(s))
        self.assertFalse(res["ok"])
        self.assertEqual(res["status"], 404)
        self.assertEqual(res["attempts"], 1)
        self.assertEqual(sleeps, [])
        self.assertIn("not_found", res["reason"])

    def test_bf17b_exhausted_attempts_permanent(self):
        sleeps = []
        t = FlakyTransport(99, {})  # همیشه 500
        res = RN.fetch_with_retry(t, FP.url_for_item_index(9), "ua", 40.0,
                                  max_attempts=3, retry_base=30.0,
                                  sleep_fn=lambda s: sleeps.append(s))
        self.assertFalse(res["ok"])
        self.assertEqual(res["attempts"], 3)
        self.assertEqual(sleeps, [30.0, 90.0])


# --------------------------------------------------------------------------- BF18 resume pipeline
class TestBF18Resume(BackfillBase):
    def _setup(self, out_dir):
        pages = self.write_pages("pages.jsonl", [1, 2, 5, 6, 7, 10, 11])
        report = BG.build_gap_report_v2(pages)
        plan = FP.build_fetch_plan(report, max_requests_per_run=500)
        base = BM.base_index_from_pages(pages)
        vol_map = BG.volume_map_from_pages(pages)
        return pages, plan, base, vol_map

    def test_bf18_exact_once_across_budget_chunks(self):
        pages, plan, base, vol_map = self._setup(self.p("run"))
        t1 = TR.FakeTransport()
        t1.add(3, body(3, "متن 3", section="جلد (1)"))
        t1.add(4, body(4, "متن 4", section="جلد (1)"))
        t1.add(8, body(8, "متن 8", section="جلد (1)"))
        t1.add(9, body(9, "متن 9", section="جلد (1)"))

        out = self.p("run")
        r1 = RN.run_pipeline(plan, base, vol_map, base["present_sorted"],
                             t1, out_dir=out, budget=2,
                             dry_run=False, sleep_fn=lambda s: None,
                             fetched_at_fn=lambda: FIXED_TS)
        self.assertEqual(r1["counts"]["fetched"], 2)
        self.assertEqual(r1["pending_remaining"], 2)
        self.assertEqual(len(t1.log), 2)

        # run 2: فقط ۲ آیتم باقی‌مانده (exact-once، بدون fetch تکراری)
        t2 = TR.FakeTransport()
        t2.add(8, body(8, "متن 8", section="جلد (1)"))
        t2.add(9, body(9, "متن 9", section="جلد (1)"))
        r2 = RN.run_pipeline(plan, base, vol_map, base["present_sorted"],
                             t2, out_dir=out, budget=500,
                             dry_run=False, sleep_fn=lambda s: None,
                             fetched_at_fn=lambda: FIXED_TS)
        self.assertEqual(r2["counts"]["fetched"], 2)
        self.assertEqual(len(t2.log), 2)
        self.assertEqual(r2["pending_remaining"], 0)
        self.assertEqual(t2.log[0]["url"], FP.url_for_item_index(8))

        # run 3: همه‌ی آیتم‌ها terminal → هیچ fetch جدیدی
        t3 = TR.FakeTransport()
        r3 = RN.run_pipeline(plan, base, vol_map, base["present_sorted"],
                             t3, out_dir=out, budget=500,
                             dry_run=False, sleep_fn=lambda s: None,
                             fetched_at_fn=lambda: FIXED_TS)
        self.assertEqual(r3["counts"]["fetched"], 0)
        self.assertEqual(len(t3.log), 0)

        # خروجی: 4 رکورد
        recs = C.read_jsonl(os.path.join(out, "backfill-records.jsonl"))
        self.assertEqual([r["item_index"] for r in recs], [3, 4, 8, 9])
        # verify
        v = RN.verify_output(out, plan, base_pages_jsonl=pages)
        self.assertTrue(v["ok"], v["errors"])
        self.assertEqual(v["records"], 4)


# --------------------------------------------------------------------------- BF19-20 CLI
class TestBF19CliDryRun(BackfillBase):
    def test_bf19_dry_run_end_to_end_no_transport(self):
        pages = self.p("pages.jsonl")
        write_jsonl(pages, [page(i) for i in [1, 2, 5, 6, 7, 10, 11]])
        gap_p = self.p("gap.json")
        plan_p = self.p("plan.json")
        out_dir = self.p("run")

        rc = CL.main(["gap-report", "--pages", pages, "--out", gap_p])
        self.assertEqual(rc, 0)
        rc = CL.main(["plan", "--gap-report", gap_p, "--out", plan_p])
        self.assertEqual(rc, 0)
        rc = CL.main(["run", "--plan", plan_p, "--base-pages", pages,
                      "--dry-run", "--out-dir", out_dir])
        self.assertEqual(rc, 0)

        report = C.read_json(os.path.join(out_dir, "run-report.json"))
        self.assertTrue(report["dry_run"])
        self.assertEqual(report["counts"]["budget_used"], 4)
        self.assertEqual(report["pending_remaining"], 4)
        # هیچ رکوردی نوشته نشده
        self.assertFalse(
            os.path.exists(os.path.join(out_dir, "backfill-records.jsonl")))

        # verify روی dry-run (records نیست → warning، نه error)
        rc = CL.main(["verify", "--plan", plan_p, "--out-dir", out_dir,
                      "--base-pages", pages])
        self.assertEqual(rc, 0)


class TestBF20LiveGuard(BackfillBase):
    def _setup(self):
        pages = self.p("pages.jsonl")
        write_jsonl(pages, [page(i) for i in [1, 2, 5, 6, 7]])
        gap_p = self.p("gap.json")
        plan_p = self.p("plan.json")
        self.assertEqual(0, CL.main(["gap-report", "--pages", pages,
                                     "--out", gap_p]))
        self.assertEqual(0, CL.main(["plan", "--gap-report", gap_p,
                                     "--out", plan_p]))
        return pages, plan_p

    def test_bf20_guard_blocks_live_without_approval(self):
        pages, plan_p = self._setup()
        env_no = {k: v for k, v in os.environ.items()
                  if k != "BACKFILL_APPROVED"}
        # (a) flag بدون token
        with mock.patch.dict(os.environ, env_no, clear=True):
            rc = CL.main(["run", "--plan", plan_p, "--base-pages", pages,
                          "--allow-live", "--out-dir", self.p("r1")])
        self.assertEqual(rc, 2)
        # (b) flag + token غلط
        with mock.patch.dict(os.environ, env_no, clear=True):
            os.environ["BACKFILL_APPROVED"] = "yes"
            rc = CL.main(["run", "--plan", plan_p, "--base-pages", pages,
                          "--allow-live", "--out-dir", self.p("r2")])
        self.assertEqual(rc, 2)
        # (c) token درست ولی بدون flag
        with mock.patch.dict(os.environ, env_no, clear=True):
            os.environ["BACKFILL_APPROVED"] = "approved"
            rc = CL.main(["run", "--plan", plan_p, "--base-pages", pages,
                          "--out-dir", self.p("r3")])
        self.assertEqual(rc, 2)
        # هیچ‌کدام transport واقعی نساخته → هیچ فایل run-report نیست
        for i in (1, 2, 3):
            self.assertFalse(os.path.exists(
                self.p("r%d" % i) + "/run-report.json"))

    def test_bf20b_fake_bodies_never_require_guard(self):
        # plan کوچک‌تر: فقط آیتم‌های [3,4] (گپ‌های 3-4) — بدون آیتم 404
        pages = self.p("pages.jsonl")
        write_jsonl(pages, [page(i) for i in [1, 2, 5]])
        gap_p = self.p("gap.json")
        plan_p = self.p("plan.json")
        self.assertEqual(0, CL.main(["gap-report", "--pages", pages,
                                     "--out", gap_p]))
        self.assertEqual(0, CL.main(["plan", "--gap-report", gap_p,
                                     "--out", plan_p]))
        bodies = self.p("bodies.json")
        C.write_json(bodies, {"3": body(3, "متن 3", section="جلد (1)"),
                              "4": body(4, "متن 4", section="جلد (1)")})
        env_no = {k: v for k, v in os.environ.items()
                  if k != "BACKFILL_APPROVED"}
        with mock.patch.dict(os.environ, env_no, clear=True):
            rc = CL.main(["run", "--plan", plan_p, "--base-pages", pages,
                          "--fake-bodies", bodies,
                          "--out-dir", self.p("r4")])
        self.assertEqual(rc, 0)
        recs = C.read_jsonl(self.p("r4") + "/backfill-records.jsonl")
        # idx 3,4 موجود در bodies → 200 (بدون guard، بدون شبکه)
        self.assertEqual([r["item_index"] for r in recs], [3, 4])
        rep = C.read_json(self.p("r4") + "/run-report.json")
        self.assertEqual(rep["counts"]["fetched"], 2)
        self.assertEqual(rep["counts"]["permanent"], 0)


# --------------------------------------------------------------------------- BF21-22 manifest
class TestBF21DiffAndRegistry(BackfillBase):
    def _rec(self, idx, change, present, dup=False, sha="abc123"):
        return {"item_index": idx, "url": FP.url_for_item_index(idx),
                "text_sha256": sha, "change": change,
                "base_state": {"present_in_base": present,
                               "dup_in_base": dup,
                               "base_page_ids": ["vol001__p%d" % idx],
                               "base_content_hash": "h"}}

    def test_bf21_diff_flags_and_absent(self):
        base = {"by_index": {}, "present_sorted": [1, 2, 7]}
        recs = [
            self._rec(3, "new", present=False),
            self._rec(5, "unchanged", present=True),
            self._rec(8, "changed", present=True, dup=True),
            self._rec(9, "changed", present=True),
        ]
        plan_items = [{"item_index": i} for i in (3, 5, 8, 9, 10)]
        d = BM.build_diff(base, recs, plan_items=plan_items)
        self.assertEqual(d["counts"][BM.STATUS_NEW], 1)
        self.assertEqual(d["counts"][BM.STATUS_UNCHANGED], 1)
        self.assertEqual(d["counts"][BM.STATUS_DUPLICATE], 1)
        self.assertEqual(d["counts"][BM.STATUS_CHANGED], 1)
        self.assertEqual(d["counts"][BM.STATUS_ABSENT], 1)
        self.assertEqual(d["total"], 5)
        self.assertEqual(d["absent"][0]["item_index"], 10)

    def test_bf21b_rollback_registry_entry_append_only(self):
        root = self.p("root")
        man_dir = os.path.join(root, "manifests")
        entry = BM.rollback_entry("v0004", "quality gate failed")
        self.assertEqual(entry["status"], "rolled_back")
        self.assertTrue(entry["active_base_unchanged"])
        reg = BM.register(root, "backfill", "v0004", entry)
        self.assertEqual(
            reg["chain"]["backfill:v0004"]["status"], "rolled_back")
        # entry قبلی (base) دست‌نخورده می‌ماند (append-only)
        V.update_registry(man_dir, "corpus", "v0003",
                          {"content_sha256": "base"})
        reg2 = V.read_registry(man_dir)
        self.assertIn("corpus:v0003", reg2["chain"])
        self.assertIn("backfill:v0004", reg2["chain"])


class TestBF22Manifest(BackfillBase):
    def test_bf22_v0004_manifest_prev_and_rollback(self):
        root = self.p("root")
        base_dir = os.path.join(root, "corpus", "builds", "v0003")
        os.makedirs(base_dir, exist_ok=True)
        base_man = M.build_manifest("corpus", "v0003",
                                    {"content_sha256": "base-sha"})
        M.write_manifest(base_dir, base_man)

        out_dir = os.path.join(root, "corpus", "builds", "v0004", "backfill")
        pages = self.write_pages("pages.jsonl", [1, 2, 5, 6, 7])
        plan = FP.build_fetch_plan(BG.build_gap_report_v2(pages))
        base_idx = BM.base_index_from_pages(pages)
        diff = BM.build_diff(base_idx, [])
        data = BM.backfill_manifest_data(base_man, base_dir, root, out_dir,
                                         {}, diff, plan, [])
        BM.write_backfill_manifest(out_dir, "v0004", data)
        m4 = C.read_json(os.path.join(out_dir, "manifest.json"))
        self.assertEqual(m4["kind"], "backfill")
        self.assertEqual(m4["version"], "v0004")
        self.assertEqual(m4["prev"]["version"], "v0003")
        self.assertEqual(m4["prev"]["kind"], "corpus")
        self.assertEqual(m4["data"]["base"]["version"], "v0003")
        self.assertTrue(m4["data"]["base"]["immutable"])
        self.assertTrue(m4["data"]["rollback"]["ready"])
        self.assertEqual(m4["data"]["rollback"]["strategy"], "keep-base")
        self.assertTrue(m4["data"]["policy"]["old_wins"])
        self.assertFalse(m4["data"]["policy"]["volume_guessing"])


if __name__ == "__main__":
    unittest.main(verbosity=2)

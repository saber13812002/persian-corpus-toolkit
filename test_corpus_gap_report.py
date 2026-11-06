# -*- coding: utf-8 -*-
"""test_corpus_gap_report.py — PCM-20.6 SUBTASK 02 / D2: تحلیل شکاف‌ها.

اجرا:  python -X utf8 -m unittest test_corpus_gap_report -v

آزمون‌ها:
  G01  runs قطعی روی مجموعه‌ی کوچک شناخته‌شده + پارس‌نشده‌ها
  G01b پایداری بازسازی: union(runs) == complement(present) در بازه
  G02  نسبت‌دادن به جلد از pages.jsonl build واقعی (فیکستور 21 رکوردی)
  G03  قطعی بودن: content_sha256 ثابت (دو بار، بدون شبکه)
  G04  نمونه‌گیری زنده روی server محلی (present/not_found/empty)
  G04b BLOCKED روی پورت ناموجود (بدون تکرار بی‌حد)
  G05  snapshot واقعی: 45,243 مفقود در 6 run + طرح Backfill (design-only)
"""
import contextlib
import io
import json
import os
import shutil
import socket
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

from corpus.tasnim import common as C
from corpus.tasnim import gap_report as GR
from corpus.tasnim import cli as CL

from test_corpus_tasnim import make_fixture as make_full_fixture

REAL_SNAPSHOT = os.path.join("data", "tasnim", "pcm20_4",
                             "source-snapshot", "tasnim-corpus.jsonl")


def write_jsonl(path, records):
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        for r in records:
            f.write(C.canonical_json_line(r).decode("utf-8"))


def rec(idx, text="متن نمونه", barg=None):
    return {"item_index": idx,
            "url": "https://tasnim.hamtaa.org/payload?file_id=tasnim"
                   "&item_index=%s" % idx,
            "captured_at": "2026-01-01 00:00:00",
            "content_hash": "h%04x" % (idx or 0),
            "barg": barg,
            "values": {"متن": text, "برگ": "برگ %s" % (barg or "?")}}


class TestG01Runs(unittest.TestCase):
    def test_g01_small_known_runs(self):
        tmp = tempfile.mkdtemp(prefix="pct-gap-")
        try:
            jl = os.path.join(tmp, "t.jsonl")
            write_jsonl(jl, [rec(i) for i in (1, 2, 5, 6, 10)])
            r = GR.missing_runs([1, 2, 5, 6, 10], 1, 10)
            self.assertEqual(r, [[3, 4], [7, 9]])
            loaded = GR.load_item_indexes(jl)
            self.assertEqual(loaded["distinct"], [1, 2, 5, 6, 10])
            self.assertEqual(loaded["dup_count"], 0)
            self.assertEqual(loaded["total_records"], 5)
            self.assertEqual(loaded["no_index"], 0)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_g01b_complement_invariant(self):
        tmp = tempfile.mkdtemp(prefix="pct-gap-")
        try:
            jl = os.path.join(tmp, "t.jsonl")
            present = [3, 7, 8, 20, 21, 22, 30]
            write_jsonl(jl, [rec(i) for i in present])
            loaded = GR.load_item_indexes(jl)
            lo, hi = present[0], present[-1]
            runs = GR.missing_runs(loaded["distinct"], lo, hi)
            missing = set()
            for s, e in runs:
                for x in range(s, e + 1):
                    missing.add(x)
            expect = set(range(lo, hi + 1)) - set(present)
            self.assertEqual(missing, expect)
            # runs مرتب و بدون هم‌پوشانی
            for i in range(1, len(runs)):
                self.assertLess(runs[i - 1][1] + 1, runs[i][0])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestG02VolumeAttribution(unittest.TestCase):
    def test_g02_report_consistency_on_real_fixture(self):
        # فیکستور 21 رکوردی: item_indexهای متمایز = 1..19 و 21
        # (رکوردِ page_id=20 در واقع دابلتِ item_index=5 است) →
        # شکافِ قطعی: [20,20]، دو طرفش هر دو جلد 2.
        tmp = tempfile.mkdtemp(prefix="pct-gap-")
        try:
            fx = os.path.join(tmp, "src")
            os.makedirs(fx, exist_ok=True)
            jl = os.path.join(fx, "tasnim-corpus.jsonl")
            jp = os.path.join(fx, "tasnim-corpus.json")
            sm = os.path.join(fx, "export-summary.json")
            make_full_fixture(jl, jp, sm)
            data_root = os.path.join(tmp, "data", "tasnim")
            with contextlib.redirect_stdout(io.StringIO()):
                rc = CL.main(["build-corpus", "--jsonl", jl,
                              "--data-root", data_root])
            self.assertEqual(rc, 0)
            pages = os.path.join(data_root, "corpus", "builds", "v0001",
                                 "pages.jsonl")
            rep = GR.build_gap_report(jl, pages)
            g, p = rep["gaps"], rep["pages"]
            self.assertEqual(p["total_records"], 21)
            self.assertEqual(p["dup_count"], 1)
            self.assertEqual(p["range_min"], 1)
            self.assertEqual(p["range_max"], 21)
            self.assertEqual(p["span"], 21)
            self.assertEqual(p["distinct_item_index"], 20)
            # بازسازی: span - distinct = missing (هرگسی‌گیریِ قطعی)
            self.assertEqual(
                p["span"] - p["distinct_item_index"], g["missing_count"])
            self.assertEqual(g["missing_count"], 1)
            self.assertEqual(g["runs_count"], 1)
            d = g["runs"][0]
            self.assertEqual((d["start"], d["end"]), (20, 20))
            self.assertEqual(d["count"], 1)
            self.assertEqual(d["before_item_index"], 19)
            self.assertEqual(d["after_item_index"], 21)
            self.assertEqual(d["volume_before"]["volume_no"], 2)
            self.assertEqual(d["volume_after"]["volume_no"], 2)
            # نسبت‌دادن: run داخل جلد 2
            self.assertEqual(len(g["missing_by_volume"]), 1)
            self.assertEqual(g["missing_by_volume"][0]["volume_no"], 2)
            self.assertEqual(g["missing_by_volume"][0]["missing_count"], 1)
            # pages.jsonl volume دارد (برای دیتای واقعی)
            vol_map = GR.volume_map_from_pages(pages)
            self.assertIn(1, vol_map)
            self.assertEqual(vol_map[1][0], 1)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_g02b_runs_attributed_to_volumes(self):
        # با شکافِ مصنوعی: نسبت‌دادن به جلد از طریق همسایه‌های موجود.
        tmp = tempfile.mkdtemp(prefix="pct-gap-")
        try:
            fx = os.path.join(tmp, "src")
            os.makedirs(fx, exist_ok=True)
            jl = os.path.join(fx, "t.jsonl")
            write_jsonl(jl, [rec(i) for i in (1, 2, 5, 6, 10)])
            # vol_map دستی: 1,2 → جلد 1؛ 5,6 → جلد 2؛ 10 → جلد 3
            rep = GR.build_gap_report(jl)
            # بدون pages.jsonl: همه‌ی runs "unknown"
            self.assertEqual(len(rep["gaps"]["missing_by_volume"]), 1)
            self.assertEqual(rep["gaps"]["missing_by_volume"][0]["volume_no"],
                             None)
            # vol_map دستی → نسبت‌دادن
            vol_map = {1: (1, "جلد 1"), 2: (1, "جلد 1"),
                       5: (2, "جلد 2"), 6: (2, "جلد 2"),
                       10: (3, "جلد 3")}
            present = [1, 2, 5, 6, 10]
            detail = [GR.attribute_run(r, vol_map, present)
                      for r in GR.missing_runs(present, 1, 10)]
            self.assertEqual([d["count"] for d in detail], [2, 3])
            self.assertEqual(detail[0]["volume_before"]["volume_no"], 1)
            self.assertEqual(detail[0]["volume_after"]["volume_no"], 2)
            self.assertEqual(detail[1]["volume_before"]["volume_no"], 2)
            self.assertEqual(detail[1]["volume_after"]["volume_no"], 3)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestG03Determinism(unittest.TestCase):
    def test_g03_same_content_sha(self):
        tmp = tempfile.mkdtemp(prefix="pct-gap-")
        try:
            jl = os.path.join(tmp, "t.jsonl")
            write_jsonl(jl, [rec(i) for i in range(1, 40) if i % 7])
            r1 = GR.build_gap_report(jl)
            r2 = GR.build_gap_report(jl)
            self.assertEqual(r1["content_sha256"], r2["content_sha256"])
            self.assertNotIn("generated_at", {k: v for k, v in r1.items()
                                              if k == "content_sha256"})
            # summary فارسی باید runها را ذکر کند
            joined = "\n".join(r1["summary_fa"])
            self.assertIn(str(r1["gaps"]["missing_count"]), joined)
            self.assertIn("Backfill", joined)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class _ProbeHandler(BaseHTTPRequestHandler):
    NOT_FOUND_IDX = 777

    def do_GET(self):
        q = parse_qs(urlparse(self.path).query)
        idx = int((q.get("item_index") or ["0"])[0])
        if idx == self.NOT_FOUND_IDX:
            self.send_response(404)
            self.end_headers()
            return
        empty = (idx % 500 == 0)
        body = json.dumps({"original_text": "" if empty else "متن زنده",
                           "section": "test"}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


class TestG04LiveSampling(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="pct-gap-")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _server(self):
        srv = HTTPServer(("127.0.0.1", 0), _ProbeHandler)
        t = threading.Thread(target=srv.serve_forever, daemon=True)
        t.start()
        return srv

    def test_g04_local_probe_statuses(self):
        srv = self._server()
        try:
            base = "http://127.0.0.1:%d/chunk-detail?item_index=" % srv.server_address[1]
            r = GR.live_probe(123, base=base, tries=1, sleep=0.1)
            self.assertEqual(r["status"], "present")
            self.assertEqual(r["text_len"], len("متن زنده"))
            self.assertEqual(r["text_sha256"], C.sha256_text("متن زنده"))
            r404 = GR.live_probe(_ProbeHandler.NOT_FOUND_IDX,
                                 base=base, tries=1, sleep=0.1)
            self.assertEqual(r404["status"], "not_found")
            self.assertEqual(r404["http"], 404)
            rempty = GR.live_probe(500, base=base, tries=1, sleep=0.1)
            self.assertEqual(rempty["status"], "empty")
            # sampling روی runs کوچک
            runs = [[100, 102], [500, 501]]
            present = [1, 99, 103, 499, 502]
            ls = GR.live_sampling(runs, present, base=base, tries=1,
                                  sleep=0.05)
            self.assertEqual(ls["status"], "OK")
            self.assertEqual(ls["probed"], len(ls["probes"]))
            self.assertLessEqual(ls["probed"], GR.MAX_LIVE_PROBES)
        finally:
            srv.shutdown()

    def test_g04b_blocked_on_unreachable(self):
        # پورتی که هیچ سرویس‌گری نمی‌شنود
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
        s.close()
        base = "http://127.0.0.1:%d/x?item_index=" % port
        runs = [[10, 11]]
        present = [5, 20]
        ls = GR.live_sampling(runs, present, base=base, tries=1, sleep=0.05)
        self.assertEqual(ls["status"], "BLOCKED")
        self.assertEqual(ls["blocked"], ls["probed"])
        for p in ls["probes"]:
            self.assertEqual(p["status"], "blocked")
            self.assertTrue(p.get("error"))
        # گزارش بدون live همچنان ساخته می‌شود
        jl = os.path.join(self.tmp, "t.jsonl")
        write_jsonl(jl, [rec(i) for i in (5, 10, 11, 20)])
        rep = GR.build_gap_report(jl)
        # بازه‌ی 5..20 (16 موقعیت) − 4 موجود = 12 مفقود
        self.assertEqual(rep["gaps"]["missing_count"], 12)
        self.assertEqual([(d["start"], d["end"]) for d in rep["gaps"]["runs"]],
                         [(6, 9), (12, 19)])
        self.assertEqual(rep["live_sampling"], None)


class TestG05RealSnapshot(unittest.TestCase):
    def test_g05_real_gap_facts(self):
        if not os.path.exists(REAL_SNAPSHOT):
            self.skipTest("real snapshot not present")
        rep = GR.build_gap_report(REAL_SNAPSHOT)
        g, p = rep["gaps"], rep["pages"]
        self.assertEqual(p["total_records"], 45844)
        self.assertEqual(p["distinct_item_index"], 45835)
        self.assertEqual(p["dup_count"], 9)
        self.assertEqual(g["missing_count"], 45243)
        self.assertEqual(g["runs_count"], 6)
        self.assertEqual([(d["start"], d["end"]) for d in g["runs"]],
                         [(3649, 11182), (11205, 39003), (44957, 49956),
                          (55699, 55701), (55715, 59590), (89280, 90310)])
        self.assertEqual(g["missing_count"],
                         sum(d["count"] for d in g["runs"]))
        bf = rep["backfill"]
        self.assertEqual(bf["status"], GR.BACKFILL_STATUS)
        self.assertFalse(bf["executed"])
        self.assertEqual(bf["estimates"]["requests"], 45243)
        self.assertTrue(rep["content_sha256"])
        self.assertTrue(any("45243" in line for line in rep["summary_fa"]))
        self.assertEqual(rep["live_sampling"], None)


if __name__ == "__main__":
    unittest.main()

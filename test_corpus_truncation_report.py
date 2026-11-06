# -*- coding: utf-8 -*-
"""test_corpus_truncation_report.py — PCM-20.6 SUBTASK 02 / D3: رسمی‌سازی سقف ۲۰۰۰.

اجرا:  python -X utf8 -m unittest test_corpus_truncation_report -v

آزمون‌ها:
  TR01 census + فهرست صفحات در‌سقف روی فیکستور کوچک (قطعی، بدون شبکه)
  TR02 قطعی بودن گزارش: content_sha256 ثابت (دو بار) + ساختار cap
  TR03 بازبینی زنده روی server محلی (at_cap/shorter/not_found) + BLOCKED
  TR04 دیتای واقعی v0001: ۲۸ صفحه در‌سقف (5+20+3) + انتخاب قطعی ≤3
"""
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
from corpus.tasnim import schema as S
from corpus.tasnim import truncation_report as TR

REAL_PAGES = os.path.join("data", "tasnim", "pcm20_5", "corpus", "builds",
                          "v0001", "pages.jsonl")
CAP = S.SOURCE_CHAR_CAP  # 2000


def page(page_id, idx, text, volume_no=None):
    return {
        "page_id": page_id,
        "item_index": idx,
        "text": text,
        "volume": ({"volume_id": "v%d" % volume_no, "volume_no": volume_no,
                    "volume_title": "جلد %d" % volume_no}
                   if volume_no is not None else None),
        "quality_status": {"status": "ok",
                           "flags": ["truncated_at_2000"]
                           if len(text) == CAP else []},
    }


def write_pages(path, recs):
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        for r in recs:
            f.write(C.canonical_json_line(r).decode("utf-8"))


class TestTR01Census(unittest.TestCase):
    def test_tr01_census_and_list(self):
        tmp = tempfile.mkdtemp(prefix="pct-tr-")
        try:
            pj = os.path.join(tmp, "pages.jsonl")
            recs = [
                page("vol001__p1", 1, "x" * (CAP - 5), 1),      # under
                page("vol001__p2", 2, "x" * CAP, 1),            # at cap
                page("vol001__p3", 3, "x" * (CAP + 7), 1),      # over cap
                page("vol001__p4", 4, "کوتاه", 1),              # short
                page("vol002__p5", 5, "y" * CAP, 2),            # at cap
                page("volkey__p6", 6, "z" * CAP, None),         # at cap, no vol
            ]
            write_pages(pj, recs)
            cen = TR.census(pj)
            self.assertEqual(cen["total_pages"], 6)
            self.assertEqual(cen["at_cap_count"], 3)
            self.assertEqual(cen["over_cap_count"], 1)
            lst = TR.at_cap_pages(pj)
            self.assertEqual([e["item_index"] for e in lst], [2, 5, 6])
            # مرتب: جلد 1 → 2 → بدون جلد
            self.assertEqual([e["volume_no"] for e in lst], [1, 2, None])
            self.assertEqual(TR.by_volume(lst), {"1": 1, "2": 1,
                                                 "unknown": 1})
            for e in lst:
                self.assertEqual(e["text_len"], CAP)
                self.assertEqual(len(e["tail"]), 40)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestTR02Determinism(unittest.TestCase):
    def test_tr02_report_stable(self):
        tmp = tempfile.mkdtemp(prefix="pct-tr-")
        try:
            pj = os.path.join(tmp, "pages.jsonl")
            write_pages(pj, [page("vol001__p1", 1, "x" * CAP, 1),
                             page("vol001__p2", 2, "متن کوتاه", 1)])
            r1 = TR.build_truncation_report(pj)
            r2 = TR.build_truncation_report(pj)
            self.assertEqual(r1["content_sha256"], r2["content_sha256"])
            self.assertEqual(r1["live_recheck"], None)
            self.assertEqual(r1["cap"]["source_char_cap"], CAP)
            self.assertEqual(r1["cap"]["evidence"]["sha256"],
                             S.GATE_1_5_EVIDENCE_SHA)
            self.assertEqual(r1["census"]["at_cap_count"], 1)
            self.assertIn("GATE 1.5", r1["cap"]["gate"])
            self.assertTrue(any("در سقف" in ln for ln in r1["summary_fa"]))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class _TrProbeHandler(BaseHTTPRequestHandler):
    """idx%1000==0 → not_found؛ idx%1000==1 → at-cap (2000)؛
    idx%1000==2 → کوتاه؛ غیر اینها → at-cap."""

    def do_GET(self):
        q = parse_qs(urlparse(self.path).query)
        idx = int((q.get("item_index") or ["0"])[0])
        if idx % 10 == 0:
            self.send_response(404)
            self.end_headers()
            return
        if idx % 10 == 2:
            text = "کوتاه"
        else:
            text = "ز" * CAP
        body = json.dumps({"original_text": text,
                           "section": "test"}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


class TestTR03LiveRecheck(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="pct-tr-")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _server(self):
        srv = HTTPServer(("127.0.0.1", 0), _TrProbeHandler)
        t = threading.Thread(target=srv.serve_forever, daemon=True)
        t.start()
        return srv

    def test_tr03_local_statuses(self):
        srv = self._server()
        try:
            base = ("http://127.0.0.1:%d/chunk-detail?item_index="
                    % srv.server_address[1])
            r = TR.live_recheck_page(101, base=base, tries=1, sleep=0.1)
            self.assertEqual(r["status"], "at_cap")
            self.assertEqual(r["live_len"], CAP)
            self.assertEqual(r["live_ws_norm_sha256"],
                             C.sha256_text("ز" * CAP))
            r2 = TR.live_recheck_page(102, base=base, tries=1, sleep=0.1)
            self.assertEqual(r2["status"], "shorter")
            self.assertEqual(r2["live_len"], len("کوتاه"))
            r4 = TR.live_recheck_page(1000, base=base, tries=1, sleep=0.1)
            self.assertEqual(r4["status"], "not_found")
            self.assertEqual(r4["http"], 404)
            # گزارش با live روی server محلی
            pj = os.path.join(self.tmp, "pages.jsonl")
            write_pages(pj, [page("vol001__p101", 101, "ز" * CAP, 1),
                             page("vol001__p102", 102, "ز" * CAP, 1)])
            rep = TR.build_truncation_report(pj, live=True, live_n=2,
                                             live_base=base,
                                             live_timeout=20.0,
                                             live_tries=1)
            lr = rep["live_recheck"]
            self.assertEqual(lr["status"], "OK")
            self.assertEqual(lr["checked"], 2)
            self.assertEqual(lr["blocked"], 0)
            self.assertEqual(lr["live_also_at_cap"], 1)
        finally:
            srv.shutdown()

    def test_tr03b_blocked(self):
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
        s.close()
        base = "http://127.0.0.1:%d/x?item_index=" % port
        pj = os.path.join(self.tmp, "pages.jsonl")
        write_pages(pj, [page("vol001__p303", 303, "ز" * CAP, 1)])
        lr = TR.live_recheck(pj, n=1, base=base, timeout=2.0, tries=1,
                             sleep=0.1)
        self.assertEqual(lr["status"], "BLOCKED")
        self.assertEqual(lr["blocked"], 1)
        rep = TR.build_truncation_report(pj, live=True, live_n=1,
                                         live_base=base, live_timeout=2.0,
                                         live_tries=1)
        self.assertEqual(rep["live_recheck"]["status"], "BLOCKED")
        self.assertTrue(any("BLOCKED" in ln for ln in rep["summary_fa"]))
        # content_sha256 نباید به live وابسته باشد
        rep2 = TR.build_truncation_report(pj)
        self.assertEqual(rep["content_sha256"], rep2["content_sha256"])


class TestTR04RealData(unittest.TestCase):
    def test_tr04_real_census_and_picks(self):
        if not os.path.exists(REAL_PAGES):
            self.skipTest("real v0001 pages not present")
        rep = TR.build_truncation_report(REAL_PAGES)
        c = rep["census"]
        self.assertEqual(c["total_pages"], 45844)
        self.assertEqual(c["at_cap_count"], 28)
        self.assertEqual(c["over_cap_count"], 0)
        self.assertEqual(rep["by_volume"], {"47": 5, "56": 20,
                                            "unknown": 3})
        self.assertEqual(len(rep["affected_pages"]), 28)
        for e in rep["affected_pages"]:
            self.assertEqual(e["text_len"], CAP)
        # انتخاب قطعی ≤3 و خارج از آیتم‌های چک‌شده‌ی قبلی (39137/66532)
        picks = TR.pick_recheck_pages(rep["affected_pages"], 3)
        self.assertEqual(len(picks), 3)
        for e in picks:
            self.assertNotIn(e["item_index"], {39137, 66532})
        self.assertEqual(picks,
                         TR.pick_recheck_pages(rep["affected_pages"], 3))
        self.assertEqual(rep["live_recheck"], None)
        self.assertTrue(rep["content_sha256"])


if __name__ == "__main__":
    unittest.main()

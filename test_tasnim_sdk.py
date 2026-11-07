# -*- coding: utf-8 -*-
"""Tasnim Web V1 — SDK tests (PCM-20.6.4, deliverable C).

Exercises the Python SDK (``tasnim/sdk/python/tasnim_client``) end-to-end
over **real HTTP** against the deterministic fixture read model from
``tasnim_test_support`` (Flask app served by a werkzeug dev server on an
ephemeral 127.0.0.1 port — no external network, no production read model).

Coverage per SDK method + contract behaviors that matter to third parties:

* all 12 endpoints via the client (catalog, volumes list/detail/iter,
  surahs 503, topics list/detail/iter, page, neighbors, search,
  statistics, health);
* envelope/meta (request_id, readmodel, generated_at);
* ETag 304 → ``from_cache=True`` (and ``clear_etag_cache``);
* pagination: ``next_page_token`` chain + ``iter_*`` generators (the full
  gap-spanning ``iter_pages`` walk is safe on the 10-page fixture);
* gap-aware references (``gap_before`` / ``in_missing_range`` / nested
  ``gap``) and PAGE_NOT_FOUND details;
* dup pages (dup_rank selection, canonical URL), ambiguous volumes;
* rate limiting with a fake server clock + fake client sleep: 429 →
  Retry-After honored → retry in the next window; ``rate_limit_backoff=
  False`` raises RATE_LIMITED with parsed ``retry_after``;
* transport-error mapping (connection refused → TasnimClientError);
* base_url normalization (trailing ``/api/v1/tasnim/`` is not doubled).

Plus one offline check of the JS/TS SDK: ``node --check`` on
``tasnim/sdk/javascript/tasnim-client.mjs`` (skipped, with reason, when
node is not on PATH — the JS client was separately live-smoked 22/22
against the real 45,844-page read model during Phase 5).

Run (worktree root):
    python -X utf8 -m unittest test_tasnim_sdk -v
"""
import os
import shutil
import socket
import subprocess
import sys
import threading
import unittest

_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_ROOT, "tasnim", "sdk", "python"))

import tasnim_test_support as fx  # noqa: E402
from tasnim_client import (Page, TasnimAPIError, TasnimClient,  # noqa: E402
                           TasnimClientError, TopicDetail)

BIG = 10 ** 6


def _teardown_state(state):
    for app in list(state.get("apps", [])):
        try:
            app.tasnim_shutdown()
        except Exception:
            pass
    shutil.rmtree(state.get("tmp", ""), ignore_errors=True)


def _start_server(app):
    """Run the Flask app on an ephemeral 127.0.0.1 port in a daemon
    thread. Returns (server, thread, base_url)."""
    from werkzeug.serving import make_server
    server = make_server("127.0.0.1", 0, app, threaded=True)
    port = server.server_address[1]
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    return server, t, "http://127.0.0.1:%d" % port


class SdkBase(unittest.TestCase):
    """Fixture read model behind a real HTTP server + one SDK client."""

    @classmethod
    def setUpClass(cls):
        cls.state = fx.reset()
        cls.app = fx.make_app(cls.state, rate_search=BIG, rate_read=BIG,
                              with_ssr=False)
        cls.server, cls.thread, cls.base_url = _start_server(cls.app)
        cls.client = TasnimClient(cls.base_url, timeout=15)

    def setUp(self):
        # Test isolation: the class-level client's in-memory ETag store
        # must not leak across tests (each test owns its cache state).
        self.client.clear_etag_cache()

    @classmethod
    def tearDownClass(cls):
        if getattr(cls, "server", None) is not None:
            cls.server.shutdown()
            cls.server.server_close()
            cls.thread.join(timeout=10)
        if fx._STATE.get("tmp") == cls.state["tmp"]:
            fx._STATE.clear()
            _teardown_state(cls.state)


# ---------------------------------------------------------------------------
# catalog / health / envelope
# ---------------------------------------------------------------------------

class TestSdkHealthAndCatalog(SdkBase):
    def test_health(self):
        h = self.client.get_health()
        self.assertEqual(h.data["status"], "ok")
        self.assertEqual(h.data["db_quick_check"], "ok")
        self.assertGreaterEqual(h.data["uptime_s"], 0.0)
        self.assertIn("db_sha256", h.data["readmodel"])
        self.assertTrue(str(h.request_id).startswith("req_"))

    def test_catalog_identity_counts(self):
        d = self.client.get_catalog().data
        self.assertEqual(d["work"]["work_id"], fx.WORK_ID)
        self.assertEqual(d["work"]["name"], "پیکره آزمایشی")
        self.assertEqual(d["edition"]["edition_id"], fx.EDITION_ID)
        self.assertEqual(d["edition"]["name"], "خروجی آزمایشی")
        self.assertEqual(
            d["counts"], {"pages": 10, "volumes": 2, "topics": 2,
                          "headings": 4, "missing_item_index": 6})

    def test_catalog_coverage_present_ratio(self):
        d = self.client.get_catalog().data
        self.assertEqual(d["coverage"]["present_ratio"], 0.625)  # 10/(10+6)

    def test_catalog_etag_304_from_cache(self):
        first = self.client.get_catalog()
        self.assertFalse(first.from_cache)
        self.assertIsNotNone(first.etag)
        again = self.client.get_catalog()
        self.assertTrue(again.from_cache)
        self.assertEqual(again.data["counts"]["pages"], 10)

    def test_clear_etag_cache(self):
        self.client.get_catalog()
        self.client.clear_etag_cache()
        self.assertFalse(self.client.get_catalog().from_cache)

    def test_envelope_and_request_ids(self):
        a = self.client.get_catalog()
        b = self.client.get_statistics()
        for r in (a, b):
            self.assertTrue(str(r.request_id).startswith("req_"))
            self.assertIn("version", r.readmodel)
            self.assertIn("content_sha256", r.readmodel)
            self.assertIn("generated_at", r.meta)
        self.assertNotEqual(a.request_id, b.request_id)

    def test_base_url_with_api_prefix(self):
        c = TasnimClient(self.base_url + "/api/v1/tasnim/")
        self.assertEqual(c.get_health().data["status"], "ok")


# ---------------------------------------------------------------------------
# volumes
# ---------------------------------------------------------------------------

class TestSdkVolumes(SdkBase):
    def test_list_volumes_shape(self):
        r = self.client.list_volumes()
        self.assertEqual(r.data["total"], 2)
        items = r.data["items"]
        self.assertEqual([v["volume_id"] for v in items], [fx.V1, fx.V2])
        self.assertEqual(items[0]["volume_no"], 1)
        self.assertEqual(items[0]["page_count"], 7)
        self.assertIsNone(r.next_page_token)

    def test_pagination_token_chain(self):
        p1 = self.client.list_volumes(limit=1)
        self.assertEqual(len(p1.data["items"]), 1)
        token = p1.next_page_token
        self.assertIsNotNone(token)
        p2 = self.client.list_volumes(limit=1, page_token=token)
        self.assertEqual(len(p2.data["items"]), 1)
        self.assertEqual(p2.data["items"][0]["volume_id"], fx.V2)
        self.assertIsNone(p2.next_page_token)

    def test_iter_volumes_token_chain(self):
        vols = list(self.client.iter_volumes(limit=1))
        self.assertEqual([v["volume_id"] for v in vols], [fx.V1, fx.V2])
        self.assertEqual(vols[1]["volume_no"], 2)

    def test_volume_detail(self):
        d = self.client.get_volume(fx.V1).data
        self.assertEqual(d["volume_no"], 1)
        self.assertEqual(d["title"], "جلد 1")
        self.assertEqual(d["strategy"], "url_section")
        self.assertEqual(d["page_count"], 7)
        self.assertEqual((d["item_index_min"], d["item_index_max"]), (0, 11))
        self.assertEqual(d["first_page"]["item_index"], 0)
        self.assertEqual(d["last_page"]["item_index"], 11)
        self.assertEqual(d["missing_ranges"],
                         [{"from": 4, "to": 9, "missing_count": 6,
                           "status": d["missing_ranges"][0]["status"]}])
        self.assertTrue(d["top_headings"])
        self.assertEqual(d["top_headings"][0]["text"], "بحث روایی")
        self.assertEqual(d["top_headings"][0]["count"], 2)

    def test_volume_ambiguity_overlap(self):
        d = self.client.get_volume(fx.V1).data
        self.assertTrue(d["ambiguity"]["flag"])
        note = d["ambiguity"]["overlap_note"][0]
        self.assertEqual(note["volume_id"], fx.V2)

    def test_volume_404(self):
        with self.assertRaises(TasnimAPIError) as cm:
            self.client.get_volume("nope__nope")
        e = cm.exception
        self.assertEqual(e.status, 404)
        self.assertEqual(e.code, "VOLUME_NOT_FOUND")
        self.assertEqual(e.details["volume_id"], "nope__nope")
        self.assertTrue(str(e.request_id).startswith("req_"))
        # `type` is the RFC-7807 error type, derived from the error CODE
        # slug (not the resource id): .../errors/volume-not-found
        self.assertEqual(e.type,
                         "https://tasnim.ai.ismc.ir/errors/volume-not-found")


# ---------------------------------------------------------------------------
# surahs (honest 503)
# ---------------------------------------------------------------------------

class TestSdkSurahs(SdkBase):
    def test_surahs_503(self):
        with self.assertRaises(TasnimAPIError) as cm:
            self.client.get_surahs()
        e = cm.exception
        self.assertEqual(e.status, 503)
        self.assertEqual(e.code, "SURAH_INDEX_NOT_SUPPORTED")
        self.assertEqual(e.details["coverage"], "0/114")
        self.assertEqual(e.details["status"], "not_supported")
        self.assertIn("evidence", e.details)

    def test_surah_detail_503(self):
        with self.assertRaises(TasnimAPIError) as cm:
            self.client.get_surah("2")
        self.assertEqual(cm.exception.details["surah_id"], "2")
        self.assertEqual(cm.exception.code, "SURAH_INDEX_NOT_SUPPORTED")


# ---------------------------------------------------------------------------
# topics
# ---------------------------------------------------------------------------

class TestSdkTopics(SdkBase):
    def _topic(self, r, display_text):
        t = [x for x in r.data["items"]
             if x["display_text"] == display_text]
        self.assertEqual(len(t), 1, r.data["items"])
        return t[0]

    def test_list_topics(self):
        r = self.client.list_topics()
        self.assertEqual(r.data["total"], 2)
        first = r.data["items"][0]
        self.assertEqual(first["display_text"], "بحث روایی")
        self.assertEqual(first["page_count"], 3)
        self.assertEqual(first["volume_count"], 2)
        self.assertTrue(first["topic_id"].startswith("t-"))
        self.assertIsNone(r.next_page_token)

    def test_list_topics_q_prefix(self):
        r = self.client.list_topics(q="بحث")
        self.assertEqual(r.data["total"], 1)
        self.assertEqual(r.data["items"][0]["display_text"], "بحث روایی")

    def test_iter_topics_token_chain(self):
        topics = list(self.client.iter_topics(limit=1))
        self.assertEqual(
            [t["display_text"] for t in topics],
            ["بحث روایی", "پیشگفتار مفسر"])

    def test_topic_detail(self):
        tid = self._topic(self.client.list_topics(), "بحث روایی")["topic_id"]
        td = self.client.get_topic(tid)
        self.assertIsInstance(td, TopicDetail)
        self.assertIsInstance(td, dict)
        self.assertEqual(td.display_text, "بحث روایی")
        self.assertEqual(td.page_count, 3)
        self.assertEqual(td.volume_count, 2)
        self.assertEqual(td.first_item_index, 2)
        self.assertEqual(td.occurrences_total, 3)
        self.assertEqual(
            [o["item_index"] for o in td.occurrences], [2, 3, 10])
        self.assertEqual(td.occurrences[2]["heading_text"],
                         "12) بحث روایی")
        self.assertTrue(td.occurrences[2]["is_heading_page"])
        self.assertEqual(td.occurrences[2]["volume_ref"]["volume_id"], fx.V2)
        self.assertEqual(
            [s["item_index"] for s in td.sample_pages], [2, 3, 10])
        self.assertEqual(td.parent_topic["display_text"],
                         "پیشگفتار مفسر")
        self.assertEqual(td.parent_topic["count"], 1)

    def test_topic_detail_no_parent(self):
        tid = self._topic(self.client.list_topics(),
                          "پیشگفتار مفسر")["topic_id"]
        td = self.client.get_topic(tid)
        self.assertEqual(td.page_count, 1)
        self.assertIsNone(td.parent_topic)
        self.assertEqual(td.first_item_index, 0)

    def test_topic_404(self):
        with self.assertRaises(TasnimAPIError) as cm:
            self.client.get_topic("t-" + "0" * 12)
        e = cm.exception
        self.assertEqual(e.status, 404)
        self.assertEqual(e.code, "TOPIC_NOT_FOUND")


# ---------------------------------------------------------------------------
# pages (the heart of the contract)
# ---------------------------------------------------------------------------

class TestSdkPages(SdkBase):
    def test_page_200_props(self):
        p = self.client.get_page(0)
        self.assertIsInstance(p, Page)
        self.assertIsInstance(p, dict)
        self.assertEqual(p.item_index, 0)
        self.assertEqual(p.dup_rank, 0)
        self.assertEqual(p.barg, 1)
        self.assertEqual(p.text, "تفسیر قرآن کریم از روایات")
        self.assertGreater(p.char_count, 0)
        self.assertEqual(p.record_class, "CONTENT_PAGE")
        self.assertEqual(p.volume_id, fx.V1)
        self.assertEqual(p.volume_no, 1)
        self.assertEqual(p.heading_text, "پیشگفتار مفسر")
        self.assertEqual(p.quality_status, "ok")
        self.assertEqual(p.flags, [])
        self.assertFalse(p.truncated_at_source)
        self.assertEqual(p.canonical_url,
                         "https://tasnim.ai.ismc.ir/page/0")
        self.assertTrue(p.source_url.startswith("https://example.org/"))
        self.assertEqual(p.source_page_id, 1000)
        self.assertIsNone(p.previous_item_index)   # beginning of corpus
        self.assertEqual(p.next_item_index, 1)

    def test_page_etag_304_from_cache(self):
        # Page (parity with the live probe) does not carry from_cache —
        # the flag lives on the raw response, so check via neighbors.
        # Note: the 304 branch returns the *same* stored object and flips
        # its from_cache in place, so record the first call's flag BEFORE
        # the second call.
        n1 = self.client.get_page_neighbors(1)
        first_from_cache = n1.from_cache
        self.assertFalse(first_from_cache)
        n2 = self.client.get_page_neighbors(1)
        self.assertTrue(n2.from_cache)
        self.assertEqual(n2.data["current"], 1)

    def test_page_gap_next(self):
        p = self.client.get_page(3)
        self.assertEqual(p.next_item_index, 10)
        ref = p["next_page_reference"]
        self.assertTrue(ref["exists"])
        self.assertEqual(ref["gap_before"], 7)
        self.assertEqual(ref["in_missing_range"], [4, 9])
        self.assertEqual(ref["next_available_item_index"], 10)
        self.assertEqual(ref["gap"]["item_index"], 4)
        self.assertFalse(ref["gap"]["exists"])
        self.assertEqual(ref["gap"]["in_missing_range"], [4, 9])
        prev = p["previous_page_reference"]
        self.assertEqual(prev["item_index"], 2)
        self.assertEqual(prev["gap_before"], 1)

    def test_page_gap_prev(self):
        p = self.client.get_page(10)
        self.assertEqual(p.previous_item_index, 3)
        ref = p["previous_page_reference"]
        self.assertEqual(ref["gap_before"], 7)
        self.assertEqual(ref["in_missing_range"], [4, 9])
        self.assertEqual(ref["prev_available_item_index"], 3)
        self.assertEqual(p.next_item_index, 11)

    def test_page_dup_anchor(self):
        p = self.client.get_page(2)
        self.assertEqual(p.dup_rank, 0)
        self.assertEqual(p.text, "متن سوم")
        self.assertEqual(p.quality_status, "dup_item_index")
        # The "dup_item_index" quality FLAG is cross-volume only (item
        # indexes appearing in >1 distinct volume); ii 2 is an
        # intra-volume dup, so the flag list stays empty while the
        # duplicate row is surfaced via `duplicates` + quality status.
        self.assertEqual(p.flags, [])
        self.assertEqual(p["duplicates"],
                         [{"dup_rank": 1, "page_id": fx._P["p2b"],
                           "volume_id": fx.V1}])

    def test_page_dup_rank_select(self):
        p = self.client.get_page(2, dup_rank=1)
        self.assertEqual(p.dup_rank, 1)
        self.assertEqual(p.text, "کوتاه")
        self.assertEqual(p.canonical_url,
                         "https://tasnim.ai.ismc.ir/page/2?dup_rank=1")

    def test_page_ambiguous_volume(self):
        # ii 10 exists in both volumes (overlap) — the anchor row may be
        # either one; the contract is the ambiguity flag.
        p = self.client.get_page(10)
        self.assertIn(p.volume_id, (fx.V1, fx.V2))
        self.assertTrue(p["volume"]["ambiguity"])
        self.assertEqual(p["volume"]["attribution"], "ambiguous")
        self.assertIn("dup_item_index", p.flags)

    def test_page_404_in_gap(self):
        with self.assertRaises(TasnimAPIError) as cm:
            self.client.get_page(5)
        e = cm.exception
        self.assertEqual(e.status, 404)
        self.assertEqual(e.code, "PAGE_NOT_FOUND")
        self.assertEqual(e.details["item_index"], 5)
        self.assertEqual(e.details["in_missing_range"], [4, 9])
        self.assertIn("3، 10", e.details["suggestion"])
        self.assertIn("page-not-found", e.type)

    def test_page_404_beyond_max(self):
        with self.assertRaises(TasnimAPIError) as cm:
            self.client.get_page(999)
        self.assertIsNone(cm.exception.details["in_missing_range"])
        self.assertEqual(cm.exception.code, "PAGE_NOT_FOUND")

    def test_page_truncated(self):
        p = self.client.get_page(12)
        self.assertEqual(p.quality_status, "truncated_at_2000")
        self.assertTrue(p.truncated_at_source)
        self.assertIn("truncated_at_2000", p.flags)
        self.assertEqual(p["quality"]["source_char_cap"], 2000)
        self.assertIsNone(p.next_item_index)        # end of corpus
        self.assertEqual(p.previous_item_index, 11)

    def test_page_empty_or_ok_ambiguous(self):
        # ii 11 exists in V1 (empty, barg None) and V2 (ok, barg 2).
        p = self.client.get_page(11)
        self.assertIn((p.volume_id, p.quality_status),
                      {(fx.V1, "empty"), (fx.V2, "ok")})
        if p.volume_id == fx.V1:
            self.assertEqual(p.text, "")
            self.assertIsNone(p.barg)
            self.assertIn("empty", p.flags)
        else:
            self.assertEqual(p.barg, 2)
            self.assertEqual(p.text, "متن یازدهم")

    def test_neighbors(self):
        d = self.client.get_page_neighbors(3).data
        self.assertEqual(d["current"], 3)
        self.assertEqual(d["prev"]["item_index"], 2)
        self.assertEqual(d["next"]["item_index"], 10)
        self.assertEqual(d["next"]["gap_before"], 7)
        self.assertEqual(d["next"]["in_missing_range"], [4, 9])
        self.assertIsNone(d["missing_nearby"]["prev_range"])
        self.assertEqual(d["missing_nearby"]["next_range"], [4, 9])

    def test_neighbors_gap_edge(self):
        d = self.client.get_page_neighbors(10).data
        self.assertEqual(d["prev"]["item_index"], 3)
        self.assertEqual(d["prev"]["gap_before"], 7)
        self.assertEqual(d["prev"]["in_missing_range"], [4, 9])
        self.assertEqual(d["next"]["item_index"], 11)
        self.assertEqual(d["missing_nearby"]["prev_range"], [4, 9])
        self.assertIsNone(d["missing_nearby"]["next_range"])

    def test_iter_pages_skip_gaps(self):
        # The full walk is safe on the 10-page fixture: 6 gap pages
        # (4..9) are skipped, 7 existing pages are yielded.
        pages = list(self.client.iter_pages(0, 12, on_missing="skip"))
        self.assertEqual([p.item_index for p in pages],
                         [0, 1, 2, 3, 10, 11, 12])

    def test_iter_pages_raise(self):
        with self.assertRaises(TasnimAPIError) as cm:
            list(self.client.iter_pages(0, 4, on_missing="raise"))
        self.assertEqual(cm.exception.code, "PAGE_NOT_FOUND")
        self.assertEqual(cm.exception.details["item_index"], 4)


# ---------------------------------------------------------------------------
# search
# ---------------------------------------------------------------------------

class TestSdkSearch(SdkBase):
    def test_search_single_token(self):
        d = self.client.search("زبان").data
        self.assertEqual(d["query"]["tokens"], ["زبان"])
        self.assertEqual(d["total"], 1)
        hit = d["results"][0]
        self.assertEqual(hit["item_index"], 12)
        self.assertEqual(hit["volume_ref"]["volume_id"], fx.V2)
        self.assertEqual(hit["volume_ref"]["volume_no"], 2)
        self.assertFalse(hit["volume_ref"]["ambiguous"])
        self.assertIn("<mark>زبان</mark>", hit["snippet"])
        self.assertIsNone(hit["heading"])
        self.assertEqual(hit["quality_status"], "truncated_at_2000")

    def test_search_multi_token(self):
        d = self.client.search("متن").data
        self.assertEqual(d["total"], 5)
        self.assertEqual(sorted(h["item_index"] for h in d["results"]),
                         [1, 2, 3, 10, 11])

    def test_search_volume_filter(self):
        d = self.client.search("قرآن", volume_id=fx.V2).data
        self.assertEqual(d["total"], 2)
        self.assertEqual(sorted(h["item_index"] for h in d["results"]),
                         [10, 12])

    def test_search_zero_results_suggestions(self):
        d = self.client.search("غایب").data
        self.assertEqual(d["total"], 0)
        self.assertEqual(d["results"], [])
        self.assertEqual(d["suggestions"],
                         ["بحث روایی", "پیشگفتار مفسر"])

    def test_search_estimated_3_tokens(self):
        d = self.client.search("متن قرآن زبان").data
        self.assertTrue(d["estimated"])
        self.assertEqual(d["total"], -1)

    def test_search_invalid_query(self):
        with self.assertRaises(TasnimAPIError) as cm:
            self.client.search("ا")
        self.assertEqual(cm.exception.status, 400)
        self.assertEqual(cm.exception.code, "INVALID_QUERY")

    def test_search_not_etag_cached(self):
        # search is no-store: even a repeat call re-fetches (no 304).
        self.assertFalse(self.client.search("متن", limit=1).from_cache)
        self.assertFalse(self.client.search("متن", limit=1).from_cache)


# ---------------------------------------------------------------------------
# statistics
# ---------------------------------------------------------------------------

class TestSdkStatistics(SdkBase):
    def test_statistics(self):
        d = self.client.get_statistics().data
        ii = d["item_index"]
        self.assertEqual(ii["distinct"], 7)
        self.assertEqual(ii["rows"], 10)
        self.assertEqual(ii["duplicates"], 3)
        self.assertEqual(ii["min"], 0)
        self.assertEqual(ii["max"], 12)
        self.assertEqual(ii["missing"]["count"], 6)
        self.assertEqual(ii["missing"]["ranges"], [[4, 9]])
        self.assertEqual(d["quality_status"]["ok"], 5)
        self.assertEqual(d["quality_status"]["dup_item_index"], 2)
        self.assertEqual(d["quality_status"]["empty"], 1)
        self.assertEqual(d["quality_status"]["truncated_at_2000"], 1)
        self.assertEqual(d["pages_by_class"]["CONTENT_PAGE"], 7)
        self.assertEqual(d["pages_by_class"]["SHORT_CONTENT"], 2)
        self.assertEqual(d["pages_by_class"]["EMPTY_PAGE"], 1)
        self.assertEqual(d["topics"]["distinct_normalized"], 2)
        self.assertEqual(d["topics"]["multi_page"], 1)
        self.assertEqual(d["surah"]["status"], "not_supported")
        self.assertEqual(d["surah"]["coverage"], "0/114")

    def test_statistics_etag_304(self):
        self.assertFalse(self.client.get_statistics().from_cache)
        self.assertTrue(self.client.get_statistics().from_cache)


# ---------------------------------------------------------------------------
# client plumbing
# ---------------------------------------------------------------------------

class TestSdkClientPlumbing(SdkBase):
    def test_transport_error(self):
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
        s.close()
        c = TasnimClient("http://127.0.0.1:%d" % port, timeout=5)
        with self.assertRaises(TasnimClientError) as cm:
            c.get_health()
        self.assertNotIsInstance(cm.exception, TasnimAPIError)
        self.assertIn("transport", str(cm.exception))


# ---------------------------------------------------------------------------
# rate limiting (fake server clock + fake client sleep)
# ---------------------------------------------------------------------------

class TestSdkRateLimiting(SdkBase):
    """429 → Retry-After → backoff, deterministic via fake clocks."""

    @classmethod
    def setUpClass(cls):
        cls.state = fx.reset()
        cls.fake = [1000.0]
        cls.app = fx.make_app(cls.state, rate_search=3, rate_read=BIG,
                              clock=lambda: cls.fake[0], with_ssr=False)
        cls.server, cls.thread, cls.base_url = _start_server(cls.app)
        cls.sleeps = []

        def fake_sleep(seconds):
            cls.sleeps.append(seconds)
            cls.fake[0] += seconds   # simulated time passes during backoff

        cls.client = TasnimClient(cls.base_url, timeout=15,
                                  sleep=fake_sleep, max_retries=3)

    def test_search_429_backoff_succeeds(self):
        self.fake[0] = 1000.0        # window 960 (fresh)
        self.sleeps[:] = []
        for _ in range(3):
            self.assertEqual(self.client.search("متن", limit=1).status, 200)
        self.assertEqual(self.sleeps, [])
        # 4th request in the window: server 429s (Retry-After 20); the
        # client sleeps exactly that, the clock crosses the window
        # boundary, and the retry succeeds.
        r = self.client.search("متن", limit=1)
        self.assertEqual(r.status, 200)
        self.assertEqual(self.sleeps, [20.0])

    def test_read_class_independent(self):
        self.fake[0] = 2000.0        # window 1980
        self.assertEqual(
            self.client.get_catalog().data["counts"]["pages"], 10)
        self.assertEqual(self.client.get_health().data["status"], "ok")
        self.assertEqual(self.sleeps, [])

    def test_no_backoff_raises(self):
        self.fake[0] = 1081.0        # window 1080 (fresh)
        c = TasnimClient(self.base_url, timeout=15,
                         rate_limit_backoff=False)
        for _ in range(3):
            c.search("متن", limit=1)
        with self.assertRaises(TasnimAPIError) as cm:
            c.search("متن", limit=1)
        e = cm.exception
        self.assertEqual(e.status, 429)
        self.assertEqual(e.code, "RATE_LIMITED")
        self.assertEqual(e.details["limit"], 3)
        self.assertEqual(e.details["window"], "60s")
        self.assertEqual(e.details["endpoint_class"], "search")
        self.assertEqual(e.retry_after, 59)   # window 1080 ends at 1140


# ---------------------------------------------------------------------------
# JS/TS SDK (offline syntax check; live smoke was done separately)
# ---------------------------------------------------------------------------

class TestJsSdk(unittest.TestCase):
    JS_DIR = os.path.join(_ROOT, "tasnim", "sdk", "javascript")

    def test_sdk_files_present(self):
        for name in ("tasnim-client.mjs", "tasnim.sdk.d.ts", "README.md"):
            self.assertTrue(
                os.path.isfile(os.path.join(self.JS_DIR, name)), name)
        for name in ("tasnim_client/client.py", "tasnim_client/__init__.py",
                     "tasnim_client/__main__.py", "README.md"):
            self.assertTrue(
                os.path.isfile(os.path.join(
                    _ROOT, "tasnim", "sdk", "python", name)), name)

    def test_node_check(self):
        node = shutil.which("node")
        if node is None:
            self.skipTest(
                "node not on PATH — JS SDK was live-smoked 22/22 against "
                "the real read model in Phase 5 (see e2e evidence)")
        r = subprocess.run([node, "--check",
                            os.path.join(self.JS_DIR, "tasnim-client.mjs")],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)


if __name__ == "__main__":
    unittest.main()

# -*- coding: utf-8 -*-
"""Tasnim Web V1 — API tests (PCM-20.6.4, spec §9.1 error contract /
pagination / rate limit / ETag, §9.2 I-2..I-4, and HP-1 layer 2+3:
T-HC-3 serializer whitelist, T-HC-4 response-body leak scan).

All tests are OFFLINE, run on the tiny deterministic fixture read model
from ``tasnim_test_support`` (Flask test client; no network, no port).

Run (worktree root):
    python -X utf8 -m unittest test_tasnim_api -v
"""
import base64
import json
import os
import shutil
import tempfile
import threading
import unittest

import tasnim_test_support as fx
from tasnim.web.readmodel import ReadModelBuilder, sha256_file
from tasnim.web.api import (CANONICAL_BASE, ERROR_BASE, SerializerError,
                            strict_pick)

P = "/api/v1/tasnim"
FORBIDDEN_SUBSTRINGS = ("hidden_summary", "retrieval_context",
                        "HIDDEN-CANARY-DO-NOT-LEAK", "secret text")
ENVELOPE_KEYS = {"type", "title", "status", "code", "message", "details",
                 "request_id"}
BIG = 10 ** 6


def _teardown_state(state):
    for app in list(state.get("apps", [])):
        try:
            app.tasnim_shutdown()
        except Exception:
            pass
    shutil.rmtree(state.get("tmp", ""), ignore_errors=True)


class ApiBase(unittest.TestCase):
    """Shared fixture app per class (spec §9.4: fresh reset per class)."""

    @classmethod
    def setUpClass(cls):
        cls.state = fx.reset()
        cls.app = fx.make_app(cls.state, rate_search=BIG, rate_read=BIG)
        cls.client = cls.app.test_client()

    @classmethod
    def tearDownClass(cls):
        if fx._STATE.get("tmp") == cls.state["tmp"]:
            fx._STATE.clear()
            _teardown_state(cls.state)

    # -- helpers -------------------------------------------------------------
    def get(self, path, **kw):
        return self.client.get(P + path, **kw)

    def assert_envelope(self, r, status, code):
        self.assertEqual(r.status_code, status, r.get_data(as_text=True)[:300])
        body = r.get_json()
        self.assertTrue(ENVELOPE_KEYS.issubset(body.keys()),
                        sorted(body.keys()))
        self.assertEqual(body["code"], code)
        self.assertEqual(body["status"], status)
        self.assertEqual(body["type"],
                         ERROR_BASE + "/" + code.lower().replace("_", "-"))
        self.assertTrue(body["request_id"].startswith("req_"))
        return body

    def assert_no_leak(self, r):
        body = r.get_data(as_text=True)
        for s in FORBIDDEN_SUBSTRINGS:
            self.assertNotIn(s, body,
                             "%r leaked in %s" % (s, r.request.path))


class TestCatalogAndHealth(ApiBase):
    def test_catalog_200_shape(self):
        r = self.get("/catalog")
        self.assertEqual(r.status_code, 200)
        d = r.get_json()["data"]
        self.assertEqual(d["work"], {"work_id": fx.WORK_ID,
                                     "name": "پیکره آزمایشی"})
        self.assertEqual(d["edition"]["edition_id"], fx.EDITION_ID)
        self.assertEqual(d["counts"],
                         {"pages": 10, "volumes": 2, "topics": 2,
                          "headings": 4, "missing_item_index": 6})
        self.assertEqual(d["coverage"]["present_ratio"], 0.625)
        self.assertIn("definition", d["coverage"])
        self.assertEqual(d["rag_status"], "not_connected")
        self.assertEqual(d["readmodel"]["version"], "v0099")
        self.assertEqual(d["readmodel"]["content_sha256"], "f" * 64)
        meta = r.get_json()["meta"]
        self.assertTrue(meta["request_id"].startswith("req_"))
        self.assertEqual(meta["readmodel"]["version"], "v0099")
        self.assert_no_leak(r)

    def test_catalog_cache_headers(self):
        r = self.get("/catalog")
        self.assertIn("max-age=60", r.headers.get("Cache-Control", ""))
        self.assertIn("stale-while-revalidate", r.headers.get("Cache-Control",
                                                              ""))

    def test_catalog_strong_etag_and_304(self):
        r1 = self.get("/catalog")
        etag = r1.headers.get("ETag")
        self.assertTrue(etag and etag.startswith('"'), etag)
        self.assertFalse(etag.startswith('W/"'), "catalog ETag must be strong")
        r2 = self.get("/catalog", headers={"If-None-Match": etag})
        self.assertEqual(r2.status_code, 304)
        self.assertEqual(r2.headers.get("ETag"), etag)
        # a different etag must NOT 304
        r3 = self.get("/catalog", headers={"If-None-Match": '"%s"' % "0" * 32})
        self.assertEqual(r3.status_code, 200)

    def test_health(self):
        r = self.get("/health")
        self.assertEqual(r.status_code, 200)
        d = r.get_json()["data"]
        self.assertEqual(d["status"], "ok")
        self.assertEqual(d["db_quick_check"], "ok")
        self.assertEqual(d["readmodel"]["version"], "v0099")
        self.assertEqual(d["readmodel"]["db_sha256"],
                         self.state["report"]["db_sha256"])
        self.assertGreaterEqual(d["uptime_s"], 0)
        self.assert_no_leak(r)


class TestVolumes(ApiBase):
    def test_list_200_shape(self):
        r = self.get("/volumes")
        self.assertEqual(r.status_code, 200)
        d = r.get_json()["data"]
        self.assertEqual(d["total"], 2)
        items = d["items"]
        self.assertEqual([i["volume_id"] for i in items],
                         [fx.V1, fx.V2])
        v1 = items[0]
        self.assertEqual(v1["volume_no"], 1)
        self.assertEqual(v1["title"], "جلد 1")
        self.assertEqual(v1["page_count"], 7)
        self.assertEqual(v1["item_index_min"], 0)
        self.assertEqual(v1["item_index_max"], 11)
        self.assertEqual(v1["first_page_item_index"], 0)
        self.assertEqual(v1["last_page_item_index"], 11)
        self.assertEqual(v1["coverage"],
                         {"missing_count": 6, "ranges": [[4, 9]],
                          "statuses": ["backfill_pending"]})
        self.assertTrue(v1["ambiguity"]["flag"])
        self.assertEqual(v1["ambiguity"]["overlap_note"][0]["volume_id"],
                         fx.V2)
        self.assertIsNone(r.get_json()["meta"].get("next_page_token"))
        self.assert_no_leak(r)

    def test_sort_page_count(self):
        r = self.get("/volumes", query_string={"sort": "page_count"})
        items = r.get_json()["data"]["items"]
        self.assertEqual(items[0]["volume_id"], fx.V1)  # 7 > 3
        self.assertEqual(items[0]["page_count"], 7)

    def test_bad_sort_400(self):
        self.assert_envelope(
            self.get("/volumes", query_string={"sort": "bogus"}),
            400, "INVALID_SORT")

    def test_pagination_token(self):
        r1 = self.get("/volumes", query_string={"limit": 1})
        d1 = r1.get_json()
        self.assertEqual(len(d1["data"]["items"]), 1)
        self.assertEqual(d1["data"]["items"][0]["volume_id"], fx.V1)
        token = d1["meta"]["next_page_token"]
        self.assertEqual(base64.urlsafe_b64decode(token.encode()), b"1")
        r2 = self.get("/volumes", query_string={"limit": 1,
                                                "page_token": token})
        d2 = r2.get_json()
        self.assertEqual(d2["data"]["items"][0]["volume_id"], fx.V2)
        self.assertIsNone(d2["meta"].get("next_page_token"))

    def test_bad_token_400(self):
        self.assert_envelope(
            self.get("/volumes", query_string={"page_token": "!!!"}),
            400, "INVALID_PAGE_TOKEN")

    def test_pagination_boundaries(self):
        # offset past the end → empty items, still 200
        r = self.get("/volumes", query_string={"offset": 2})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["data"]["items"], [])
        self.assertEqual(r.get_json()["data"]["total"], 2)
        # limit clamped to MAX_LIMIT (no 500, no token)
        r = self.get("/volumes", query_string={"limit": 500})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.get_json()["data"]["items"]), 2)
        self.assertIsNone(r.get_json()["meta"].get("next_page_token"))
        # negative offset → 400
        self.assert_envelope(
            self.get("/volumes", query_string={"offset": -1}),
            400, "INVALID_PARAMETER")
        # non-numeric limit → 400
        self.assert_envelope(
            self.get("/volumes", query_string={"limit": "abc"}),
            400, "INVALID_PARAMETER")

    def test_detail_200(self):
        r = self.get("/volumes/%s" % fx.V1)
        self.assertEqual(r.status_code, 200)
        d = r.get_json()["data"]
        self.assertEqual(d["volume_id"], fx.V1)
        self.assertEqual(d["strategy"], "url_section")
        self.assertEqual(d["top_headings"][0],
                         {"text": "بحث روایی", "count": 2})
        self.assertEqual(d["missing_ranges"],
                         [{"from": 4, "to": 9, "missing_count": 6,
                           "status": "backfill_pending"}])
        self.assertEqual(d["dup_item_index_with"][0]["volume_id"], fx.V2)
        self.assertEqual(d["first_page"],
                         {"page_id": fx._P["p0"], "item_index": 0})
        self.assertEqual(d["last_page"],
                         {"page_id": fx._P["p11a"], "item_index": 11})
        self.assertIn("max-age=3600", r.headers.get("Cache-Control", ""))
        self.assert_no_leak(r)

    def test_detail_404(self):
        body = self.assert_envelope(self.get("/volumes/nope"),
                                    404, "VOLUME_NOT_FOUND")
        self.assertEqual(body["details"]["volume_id"], "nope")
        self.assert_no_leak(self.get("/volumes/nope"))


class TestSurahs(ApiBase):
    def test_surahs_503_honest(self):
        r = self.get("/surahs")
        body = self.assert_envelope(r, 503, "SURAH_INDEX_NOT_SUPPORTED")
        self.assertEqual(body["details"]["status"], "not_supported")
        self.assertEqual(body["details"]["coverage"], "0/114")
        self.assertEqual(len(body["details"]["evidence"]), 4)
        self.assertIn("next_planned", body["details"])
        self.assertNotIn("surah_id", body["details"])
        self.assert_no_leak(r)

    def test_surah_detail_503_with_id(self):
        r = self.get("/surahs/al-baqarah")
        body = self.assert_envelope(r, 503, "SURAH_INDEX_NOT_SUPPORTED")
        self.assertEqual(body["details"]["surah_id"], "al-baqarah")


class TestTopics(ApiBase):
    def test_list_200(self):
        r = self.get("/topics")
        d = r.get_json()["data"]
        self.assertEqual(d["total"], 2)
        items = d["items"]
        self.assertEqual(items[0]["topic_id"].startswith("t-"), True)
        self.assertEqual(len(items[0]["topic_id"]), 14)
        self.assertEqual(items[0]["display_text"], "بحث روایی")
        self.assertEqual(items[0]["page_count"], 3)
        self.assertEqual(items[0]["volume_count"], 2)
        self.assertEqual(items[0]["first_item_index"], 2)
        self.assertEqual(items[0]["first_page_id"], fx._P["p2"])
        self.assertEqual(items[1]["display_text"], "پیشگفتار مفسر")
        self.assertEqual(items[1]["page_count"], 1)
        self.assert_no_leak(r)

    def test_q_prefix(self):
        r = self.get("/topics", query_string={"q": "بحث"})
        d = r.get_json()["data"]
        self.assertEqual(d["total"], 1)
        self.assertEqual(d["items"][0]["display_text"], "بحث روایی")

    def test_q_metachars_escaped(self):
        # "%" must be treated literally (LIKE escape), not as a wildcard
        r = self.get("/topics", query_string={"q": "بحث%"})
        self.assertEqual(r.get_json()["data"]["total"], 0)

    def test_min_pages(self):
        r = self.get("/topics", query_string={"min_pages": 2})
        d = r.get_json()["data"]
        self.assertEqual(d["total"], 1)
        self.assertEqual(d["items"][0]["display_text"], "بحث روایی")
        self.assert_envelope(
            self.get("/topics", query_string={"min_pages": "abc"}),
            400, "INVALID_PARAMETER")

    def test_sort_name(self):
        r = self.get("/topics", query_string={"sort": "name"})
        items = r.get_json()["data"]["items"]
        # BINARY (codepoint) order: ب U+0628 < پ U+067E
        self.assertEqual([i.get("normalized_text") or i["display_text"]
                          for i in items],
                         ["بحث روایی", "پیشگفتار مفسر"])
        self.assert_envelope(
            self.get("/topics", query_string={"sort": "nope"}),
            400, "INVALID_SORT")

    def test_detail_200(self):
        r = self.get("/topics")
        tid = r.get_json()["data"]["items"][0]["topic_id"]
        r = self.get("/topics/%s" % tid)
        d = r.get_json()["data"]
        self.assertEqual(d["topic_id"], tid)
        self.assertEqual(d["normalized_text"], "بحث روایی")
        self.assertEqual(d["page_count"], 3)
        self.assertEqual(d["occurrences_total"], 3)
        self.assertEqual([o["item_index"] for o in d["occurrences"]],
                         [2, 3, 10])
        self.assertTrue(all(o["is_heading_page"]
                            for o in d["occurrences"]))
        self.assertEqual(d["occurrences"][2]["volume_ref"]["volume_no"], 2)
        self.assertEqual(
            [s["item_index"] for s in d["sample_pages"]], [2, 3, 10])
        self.assertEqual(d["parent_topic"]["display_text"],
                         "پیشگفتار مفسر")
        self.assertEqual(d["parent_topic"]["count"], 1)
        self.assert_no_leak(r)

    def test_detail_404(self):
        body = self.assert_envelope(self.get("/topics/t-000000000000"),
                                    404, "TOPIC_NOT_FOUND")
        self.assertEqual(body["details"]["topic_id"], "t-000000000000")


class TestPages(ApiBase):
    def test_page_200_shape(self):
        r = self.get("/pages/0")
        self.assertEqual(r.status_code, 200)
        d = r.get_json()["data"]
        self.assertEqual(sorted(d.keys()), sorted([
            "page_id", "item_index", "dup_rank", "barg", "volume",
            "heading", "visible_content", "next_page_reference",
            "previous_page_reference", "metadata", "quality", "duplicates",
            "reference", "rag_status"]))
        self.assertEqual(d["page_id"], fx._P["p0"])
        self.assertEqual(d["item_index"], 0)
        self.assertEqual(d["dup_rank"], 0)
        self.assertEqual(d["barg"], 1)
        self.assertEqual(d["rag_status"], "not_connected")
        self.assertEqual(d["visible_content"]["text"],
                         "تفسیر قرآن کریم از روایات")
        self.assertEqual(d["visible_content"]["record_class"],
                         "CONTENT_PAGE")
        self.assertEqual(d["heading"]["text"], "پیشگفتار مفسر")
        self.assertEqual(d["duplicates"], [])
        self.assertEqual(d["volume"]["attribution"], "recorded")
        self.assertFalse(d["volume"]["ambiguity"])
        self.assertEqual(d["reference"]["canonical_url"],
                         CANONICAL_BASE + "/page/0")
        self.assertEqual(d["reference"]["work_id"], fx.WORK_ID)
        self.assertEqual(d["reference"]["edition_id"], fx.EDITION_ID)
        self.assert_no_leak(r)

    def test_page_prev_beginning(self):
        d = self.get("/pages/0").get_json()["data"]
        self.assertEqual(d["previous_page_reference"],
                         {"item_index": None, "page_id": None,
                          "exists": False, "gap_before": 0,
                          "reason": "beginning_of_corpus"})
        self.assertEqual(d["next_page_reference"]["item_index"], 1)
        # gap_before = item_index delta (nn - ii); consecutive pages → 1
        self.assertEqual(d["next_page_reference"]["gap_before"], 1)

    def test_page_next_across_gap(self):
        d = self.get("/pages/3").get_json()["data"]
        n = d["next_page_reference"]
        self.assertEqual(n["item_index"], 10)
        self.assertEqual(n["page_id"], fx._P["p10a"])
        self.assertTrue(n["exists"])
        self.assertEqual(n["gap_before"], 7)
        self.assertEqual(n["in_missing_range"], [4, 9])
        self.assertEqual(n["next_available_item_index"], 10)
        self.assertEqual(n["gap"]["item_index"], 4)
        self.assertFalse(n["gap"]["exists"])
        self.assertEqual(d["previous_page_reference"]["item_index"], 2)
        self.assertEqual(d["previous_page_reference"]["gap_before"], 1)

    def test_page_end_of_corpus_and_truncated(self):
        d = self.get("/pages/12").get_json()["data"]
        self.assertEqual(d["next_page_reference"],
                         {"item_index": None, "page_id": None,
                          "exists": False, "gap_before": 0,
                          "reason": "end_of_corpus"})
        self.assertEqual(d["quality"],
                         {"status": "truncated_at_2000",
                          "flags": ["truncated_at_2000"],
                          "truncated_at_source": True,
                          "source_char_cap": 2000})

    def test_page_dup_anchor(self):
        d = self.get("/pages/2").get_json()["data"]
        self.assertEqual(d["page_id"], fx._P["p2"])
        self.assertEqual(d["quality"]["status"], "dup_item_index")
        self.assertEqual(d["duplicates"],
                         [{"dup_rank": 1, "page_id": fx._P["p2b"],
                           "volume_id": fx.V1}])
        self.assertEqual(d["reference"]["canonical_url"],
                         CANONICAL_BASE + "/page/2")

    def test_page_dup_rank_select(self):
        d = self.get("/pages/2", query_string={"dup_rank": 1}).get_json()[
            "data"]
        self.assertEqual(d["page_id"], fx._P["p2b"])
        self.assertEqual(d["dup_rank"], 1)
        self.assertEqual(d["duplicates"],
                         [{"dup_rank": 0, "page_id": fx._P["p2"],
                           "volume_id": fx.V1}])
        self.assertEqual(d["reference"]["canonical_url"],
                         CANONICAL_BASE + "/page/2?dup_rank=1")
        self.assertEqual(d["visible_content"]["text"], "کوتاه")

    def test_page_ambiguous_volume(self):
        # ii=10 exists in BOTH volumes (both dup_rank 0): ambiguous
        d = self.get("/pages/10").get_json()["data"]
        self.assertIn(d["page_id"], (fx._P["p10a"], fx._P["p10b"]))
        self.assertTrue(d["volume"]["ambiguity"])
        self.assertEqual(d["volume"]["attribution"], "ambiguous")
        self.assertIn("dup_item_index", d["quality"]["flags"])
        other = [p for p in (fx._P["p10a"], fx._P["p10b"])
                 if p != d["page_id"]][0]
        self.assertEqual(d["duplicates"],
                         [{"dup_rank": 0, "page_id": other,
                           "volume_id": fx.V2
                           if other == fx._P["p10b"] else fx.V1}])

    def test_page_404_in_gap(self):
        r = self.get("/pages/9")
        body = self.assert_envelope(r, 404, "PAGE_NOT_FOUND")
        self.assertEqual(body["details"]["in_missing_range"], [4, 9])
        self.assertIn("10", body["details"]["suggestion"])
        self.assertIn("3", body["details"]["suggestion"])
        self.assert_no_leak(r)

    def test_page_404_beyond_max(self):
        body = self.assert_envelope(self.get("/pages/13"),
                                    404, "PAGE_NOT_FOUND")
        self.assertIsNone(body["details"]["in_missing_range"])
        self.assertIn("12", body["details"]["suggestion"])

    def test_page_bad_dup_rank(self):
        self.assert_envelope(
            self.get("/pages/2", query_string={"dup_rank": "abc"}),
            400, "INVALID_PARAMETER")
        self.assert_envelope(
            self.get("/pages/2", query_string={"dup_rank": "-1"}),
            400, "INVALID_PARAMETER")

    def test_page_missing_rank(self):
        # ii=2 has ranks 0,1 only — rank 2 does not exist
        self.assert_envelope(
            self.get("/pages/2", query_string={"dup_rank": 2}),
            404, "PAGE_NOT_FOUND")

    def test_page_304(self):
        r1 = self.get("/pages/5")  # in gap → 404; use /pages/1 instead
        r1 = self.get("/pages/1")
        etag = r1.headers.get("ETag")
        self.assertTrue(etag)
        r2 = self.get("/pages/1", headers={"If-None-Match": etag})
        self.assertEqual(r2.status_code, 304)


class TestNeighbors(ApiBase):
    def test_gap_next(self):
        r = self.get("/pages/3/neighbors")
        d = r.get_json()["data"]
        self.assertEqual(d["current"], 3)
        self.assertEqual(d["next"]["item_index"], 10)
        self.assertEqual(d["next"]["gap_before"], 7)
        self.assertEqual(d["next"]["in_missing_range"], [4, 9])
        self.assertEqual(d["missing_nearby"]["next_range"], [4, 9])
        self.assertIsNone(d["missing_nearby"]["prev_range"])
        self.assert_no_leak(r)

    def test_gap_prev(self):
        d = self.get("/pages/10/neighbors").get_json()["data"]
        self.assertEqual(d["prev"]["item_index"], 3)
        self.assertEqual(d["prev"]["gap_before"], 7)
        self.assertEqual(d["prev"]["prev_available_item_index"], 3)
        self.assertEqual(d["prev"]["gap"]["item_index"], 9)
        self.assertEqual(d["missing_nearby"]["prev_range"], [4, 9])
        self.assertIsNone(d["missing_nearby"]["next_range"])
        self.assertEqual(d["next"]["item_index"], 11)
        self.assertEqual(d["next"]["gap_before"], 1)

    def test_at_beginning(self):
        d = self.get("/pages/0/neighbors").get_json()["data"]
        self.assertFalse(d["prev"]["exists"])
        self.assertEqual(d["prev"]["reason"], "beginning_of_corpus")
        self.assertIsNone(d["missing_nearby"]["prev_range"])

    def test_404_in_gap(self):
        body = self.assert_envelope(self.get("/pages/6/neighbors"),
                                    404, "PAGE_NOT_FOUND")
        self.assertEqual(body["details"]["in_missing_range"], [4, 9])


class TestSearch(ApiBase):
    def test_single_token_hit(self):
        r = self.get("/search", query_string={"q": "زبان"})
        self.assertEqual(r.status_code, 200)
        d = r.get_json()["data"]
        self.assertEqual(d["query"]["raw"], "زبان")
        self.assertEqual(d["query"]["tokens"], ["زبان"])
        self.assertEqual(d["total"], 1)
        res = d["results"][0]
        self.assertEqual(res["item_index"], 12)
        self.assertEqual(res["page_id"], fx._P["p12"])
        self.assertEqual(res["volume_ref"]["volume_id"], fx.V2)
        self.assertEqual(res["volume_ref"]["volume_no"], 2)
        self.assertFalse(res["volume_ref"]["ambiguous"])
        self.assertIn("<mark>زبان</mark>", res["snippet"])
        self.assertIsNone(res["heading"])
        self.assertEqual(res["quality_status"], "truncated_at_2000")
        self.assert_no_leak(r)

    def test_and_query(self):
        r = self.get("/search", query_string={"q": "زبان قرآن"})
        d = r.get_json()["data"]
        self.assertEqual(d["total"], 1)
        self.assertEqual(d["results"][0]["item_index"], 12)

    def test_prefix_covers_suffix_morphology(self):
        # «تفسیر*» hits both «تفسیر» (p0) and «تفسیری» (p10b)
        r = self.get("/search", query_string={"q": "تفسیر"})
        d = r.get_json()["data"]
        self.assertEqual(d["total"], 2)
        self.assertEqual(sorted(x["item_index"] for x in d["results"]),
                         [0, 10])

    def test_multi_token_total(self):
        r = self.get("/search", query_string={"q": "متن"})
        d = r.get_json()["data"]
        self.assertEqual(sorted(x["item_index"] for x in d["results"]),
                         [1, 2, 3, 10, 11])
        self.assertEqual(d["total"], 5)

    def test_sort_item_index(self):
        r = self.get("/search", query_string={"q": "متن", "sort":
                                              "item_index"})
        d = r.get_json()["data"]
        self.assertEqual([x["item_index"] for x in d["results"]],
                         [1, 2, 3, 10, 11])
        self.assert_envelope(
            self.get("/search", query_string={"q": "متن", "sort": "bogus"}),
            400, "INVALID_SORT")

    def test_volume_filter(self):
        r = self.get("/search", query_string={"q": "قرآن", "volume_id":
                                              fx.V2})
        d = r.get_json()["data"]
        self.assertEqual(d["total"], 2)
        self.assertEqual(sorted(x["item_index"] for x in d["results"]),
                         [10, 12])

    def test_estimated_3_tokens(self):
        r = self.get("/search", query_string={"q": "متن قرآن زبان"})
        d = r.get_json()["data"]
        self.assertTrue(d.get("estimated"))
        self.assertEqual(d["total"], -1)

    def test_zero_results_suggestions(self):
        r = self.get("/search", query_string={"q": "غایب"})
        d = r.get_json()["data"]
        self.assertEqual(d["total"], 0)
        self.assertEqual(d["results"], [])
        self.assertEqual(d["suggestions"],
                         ["بحث روایی", "پیشگفتار مفسر"])

    def test_digit_query(self):
        r = self.get("/search", query_string={"q": "123"})
        d = r.get_json()["data"]
        self.assertEqual(d["total"], 0)
        self.assertIn("suggestions", d)

    def test_short_q_400(self):
        self.assert_envelope(self.get("/search", query_string={"q": "ا"}),
                             400, "INVALID_QUERY")
        self.assert_envelope(self.get("/search"), 400, "INVALID_QUERY")

    def test_no_token_q_400(self):
        self.assert_envelope(self.get("/search", query_string={"q": "!!"}),
                             400, "INVALID_QUERY")

    def test_weak_etag_no_store_304(self):
        r1 = self.get("/search", query_string={"q": "زبان"})
        etag = r1.headers.get("ETag")
        self.assertTrue(etag and etag.startswith('W/"'), etag)
        self.assertEqual(r1.headers.get("Cache-Control"), "no-store")
        r2 = self.get("/search", query_string={"q": "زبان"},
                      headers={"If-None-Match": etag})
        self.assertEqual(r2.status_code, 304)


class TestStatistics(ApiBase):
    def test_statistics_full(self):
        r = self.get("/statistics")
        self.assertEqual(r.status_code, 200)
        d = r.get_json()["data"]
        self.assertEqual(d["quality_status"],
                         {"ok": 5, "dup_item_index": 2, "short": 1,
                          "empty": 1, "truncated_at_2000": 1,
                          "definition":
                          d["quality_status"]["definition"]})
        self.assertEqual(d["pages_by_class"]["CONTENT_PAGE"], 7)
        self.assertEqual(d["pages_by_class"]["SHORT_CONTENT"], 2)
        self.assertEqual(d["pages_by_class"]["EMPTY_PAGE"], 1)
        ii = d["item_index"]
        self.assertEqual(ii["distinct"], 7)
        self.assertEqual(ii["rows"], 10)
        self.assertEqual(ii["duplicates"], 3)
        self.assertEqual(ii["min"], 0)
        self.assertEqual(ii["max"], 12)
        self.assertEqual(ii["missing"]["count"], 6)
        self.assertEqual(ii["missing"]["ranges"], [[4, 9]])
        tl = d["text_length"]
        self.assertEqual((tl["p50"], tl["p90"], tl["p99"], tl["max"]),
                         (100, 150, 190, 2000))
        self.assertEqual(d["topics"]["distinct_normalized"], 2)
        self.assertEqual(d["topics"]["multi_page"], 1)
        self.assertEqual(d["surah"]["status"], "not_supported")
        self.assertEqual(d["surah"]["coverage"], "0/114")
        self.assertIn("max-age=60", r.headers.get("Cache-Control", ""))
        self.assert_no_leak(r)


class TestOpenApiAndDocs(ApiBase):
    def test_openapi_3_1(self):
        r = self.get("/openapi.json")
        self.assertEqual(r.status_code, 200)
        spec = r.get_json()
        self.assertEqual(spec["openapi"], "3.1.0")
        self.assertEqual(len(spec["paths"]), 14)
        for path in ("/catalog", "/volumes", "/volumes/{volume_id}",
                     "/surahs", "/surahs/{surah_id}", "/topics",
                     "/topics/{topic_id}", "/pages/{item_index}",
                     "/pages/{item_index}/neighbors", "/search",
                     "/statistics", "/health"):
            self.assertIn(path, spec["paths"])
        self.assertIn("components", spec)
        self.assertNotIn("components", spec["paths"])

    def test_docs_offline(self):
        r = self.get("/docs")
        self.assertEqual(r.status_code, 200)
        self.assertIn("text/html", r.headers.get("Content-Type", ""))
        html = r.get_data(as_text=True)
        self.assertIn("openapi.json", html)
        self.assertNotIn("cdn", html.lower())


class TestErrorContract(ApiBase):
    """Every error code ≥ 1 test + RFC-7807 envelope + request_id
    uniqueness (spec §9.1 "error contract")."""

    def test_codes_present(self):
        # one probe per code (assert_envelope checks the full envelope)
        self.assert_envelope(self.get("/pages/9"), 404, "PAGE_NOT_FOUND")
        self.assert_envelope(self.get("/volumes/nope"), 404,
                             "VOLUME_NOT_FOUND")
        self.assert_envelope(self.get("/topics/t-000000000000"), 404,
                             "TOPIC_NOT_FOUND")
        self.assert_envelope(self.get("/surahs"), 503,
                             "SURAH_INDEX_NOT_SUPPORTED")
        self.assert_envelope(self.get("/search",
                                      query_string={"q": "!"}),
                             400, "INVALID_QUERY")
        self.assert_envelope(self.get("/volumes",
                                      query_string={"offset": "-1"}),
                             400, "INVALID_PARAMETER")
        self.assert_envelope(self.get("/volumes",
                                      query_string={"sort": "x"}),
                             400, "INVALID_SORT")
        self.assert_envelope(self.get("/topics",
                                      query_string={"page_token": "!!"}),
                             400, "INVALID_PAGE_TOKEN")
        self.assert_envelope(self.client.get(P + "/no-such-route"),
                             404, "NOT_FOUND")
        self.assert_envelope(self.client.post(P + "/catalog"),
                             405, "METHOD_NOT_ALLOWED")

    def test_request_id_unique(self):
        r1 = self.get("/catalog").get_json()["meta"]
        r2 = self.get("/catalog").get_json()["meta"]
        self.assertNotEqual(r1["request_id"], r2["request_id"])
        self.assertTrue(r1["request_id"].startswith("req_"))

    def test_405_allowed_methods(self):
        body = self.assert_envelope(self.client.post(P + "/catalog"),
                                    405, "METHOD_NOT_ALLOWED")
        # Flask valid_methods always include HEAD + OPTIONS
        self.assertEqual(body["details"]["allowed"],
                         ["GET", "HEAD", "OPTIONS"])

    def test_zz_internal_500(self):
        # destroy the read model → per-request open fails → honest 500
        # (INTERNAL envelope with request_id for the operator)
        os.remove(self.state["db_path"])
        r = self.get("/catalog")
        self.assert_envelope(r, 500, "INTERNAL")
        self.assertEqual(r.get_json()["details"], {})


class TestRateLimiting(ApiBase):
    """spec §9.1 "rate limit": 429 + Retry-After with a mocked clock,
    class independence, exempt paths, per-IP (X-Forwarded-For)."""

    @classmethod
    def setUpClass(cls):
        cls.state = fx.reset()
        cls.fake = [1000.0]   # t=1000 → window 960, ends at 1020
        cls.app = fx.make_app(cls.state, rate_search=3, rate_read=BIG,
                              clock=lambda: cls.fake[0])
        cls.client = cls.app.test_client()

    @classmethod
    def tearDownClass(cls):
        if fx._STATE.get("tmp") == cls.state["tmp"]:
            fx._STATE.clear()
            _teardown_state(cls.state)

    def _search(self, **headers):
        return self.client.get(P + "/search",
                               query_string={"q": "قرآن"}, **headers)

    def _fresh_window(self, t=1000.0):
        # each test gets its own rate-limit window (alphabetical order means
        # sibling tests would otherwise share window 960 and burn the budget)
        self.fake[0] = t

    def test_search_429_then_new_window(self):
        self._fresh_window(1000.0)
        for i in range(3):
            r = self._search()
            self.assertEqual(r.status_code, 200, "call %d" % (i + 1))
        r = self._search()
        body = self.assert_envelope(r, 429, "RATE_LIMITED")
        self.assertEqual(body["details"]["limit"], 3)
        self.assertEqual(body["details"]["endpoint_class"], "search")
        # window 960, now 1000 → Retry-After = 960+60-1000 = 20
        self.assertEqual(r.headers.get("Retry-After"), "20")
        # still 429 inside the same window
        self.assertEqual(self._search().status_code, 429)
        # next window (t=1021 → window 980) → allowed again
        self.fake[0] = 1021.0
        self.assertEqual(self._search().status_code, 200)

    def test_read_class_independent(self):
        self._fresh_window(2000.0)  # window 1980: fresh search budget
        for _ in range(3):
            self._search()
        self.assertEqual(self._search().status_code, 429)
        # read class (120+) unaffected by the search cap
        for _ in range(5):
            self.assertEqual(self.client.get(P + "/catalog").status_code,
                             200)

    def test_exempt_paths(self):
        for _ in range(10):
            self.assertEqual(self.client.get(P + "/health").status_code,
                             200)
            self.assertEqual(
                self.client.get(P + "/openapi.json").status_code, 200)
            self.assertEqual(self.client.get(P + "/docs").status_code, 200)

    def test_xff_separate_bucket(self):
        self._fresh_window(3000.0)  # window 2980: fresh search budget
        for _ in range(3):
            self._search()
        self.assertEqual(self._search().status_code, 429)
        # a different client IP has its own bucket
        r = self._search(headers={"X-Forwarded-For": "9.9.9.9, 10.0.0.1"})
        self.assertEqual(r.status_code, 200)

    def test_rate_limiter_thread_safe(self):
        # Regression: the real server runs threaded, and the rate limiter's
        # shared SQLite connection is created in the main thread. SQLite
        # objects are not usable across threads by default, so this raised
        # sqlite3.ProgrammingError -> 500 on worker threads. check_same_thread
        # = False + a lock must make it safe from any thread.
        rate = self.app.extensions["tasnim"]["rate"]
        errors = []

        def call(_i):
            try:
                rate.check("1.2.3.4", "read")
            except Exception as e:  # noqa: BLE001 - recorded, asserted below
                errors.append(e)

        ts = [threading.Thread(target=call, args=(i,)) for i in range(8)]
        for t in ts:
            t.start()
        for t in ts:
            t.join()
        self.assertEqual(errors, [])
        # main thread must still be able to use the same limiter
        rate.check("1.2.3.4", "read")


class TestEtagBuildChange(unittest.TestCase):
    """spec §9.1 "ETag": changing build (different db sha) → new ETag."""

    def test_etag_changes_with_build(self):
        s1 = fx.reset()
        app1 = fx.make_app(s1, rate_search=BIG, rate_read=BIG)
        c1 = app1.test_client()
        e1 = c1.get(P + "/catalog").headers.get("ETag")
        self.assertTrue(e1)

        tmp = tempfile.mkdtemp(prefix="pct_etag_")
        try:
            corpus = os.path.join(tmp, "v0099")
            out = os.path.join(tmp, "out")
            fx.build_fixture_corpus(corpus)
            # mutate one page's text → different db bytes → different sha
            p = os.path.join(corpus, "pages.jsonl")
            with open(p, encoding="utf-8") as f:
                lines = f.read().splitlines()
            rec = json.loads(lines[0])
            rec["text"] = "متن متفاوت برای تغییر ETag"
            lines[0] = json.dumps(rec, ensure_ascii=False)
            with open(p, "w", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")
            fx.rehash_file(corpus, "pages.jsonl")
            ReadModelBuilder(corpus, out).build()
            app2 = fx.make_app(s1, rate_search=BIG, rate_read=BIG,
                               rate_db_path=os.path.join(tmp, "r.db"))
            # point app2 at the mutated build via a fresh create_app
            from tasnim.web.api import create_app
            app2 = create_app(os.path.join(out, "tasnim_readmodel.db"),
                              rate_search=BIG, rate_read=BIG,
                              rate_db_path=os.path.join(tmp, "r2.db"))
            e2 = app2.test_client().get(P + "/catalog").headers.get("ETag")
            app2.tasnim_shutdown()
            self.assertTrue(e2)
            self.assertNotEqual(e1, e2)
        finally:
            _teardown_state(s1)
            shutil.rmtree(tmp, ignore_errors=True)
            fx._STATE.clear()


class TestHiddenContextApi(unittest.TestCase):
    """HP-1 layer 2+3 (T-HC-3, T-HC-4), spec §9.1.

    T-HC-3: serializer whitelist — any non-whitelisted field RAISES
            (deny-by-default); no silent drop.
    T-HC-4: scan the body of EVERY endpoint response for forbidden
            substrings (API-level analogue of the DOM scan).
    Plus: the corpus source tree stays byte-identical around API use.
    """

    @classmethod
    def setUpClass(cls):
        cls.state = fx.reset()
        cls.before = {}
        for name in rm_names():
            path = os.path.join(cls.state["corpus_dir"], name)
            cls.before[name] = sha256_file(path)
        cls.app = fx.make_app(cls.state, rate_search=BIG, rate_read=BIG)
        cls.client = cls.app.test_client()

    @classmethod
    def tearDownClass(cls):
        if fx._STATE.get("tmp") == cls.state["tmp"]:
            fx._STATE.clear()
            _teardown_state(cls.state)

    # -- T-HC-3 ---------------------------------------------------------------
    def test_hc3_non_whitelisted_key_raises(self):
        with self.assertRaises(SerializerError) as ctx:
            strict_pick({"text": "x", "hidden_summary": "s"},
                        {"text"}, "visible_content")
        self.assertIn("hidden_summary", str(ctx.exception))
        with self.assertRaises(SerializerError):
            strict_pick({"text": "x", "retrieval_context": "s"},
                        {"text", "char_count"})

    def test_hc3_copies_whitelisted_only(self):
        out = strict_pick({"text": "x", "char_count": 1,
                           "record_class": "CONTENT_PAGE"},
                          {"text", "char_count", "record_class"},
                          "visible_content")
        self.assertEqual(out, {"text": "x", "char_count": 1,
                               "record_class": "CONTENT_PAGE"})

    # -- T-HC-4 ----------------------------------------------------------------
    def test_hc4_no_leak_in_any_response(self):
        responses = [
            self.client.get(P + "/catalog"),
            self.client.get(P + "/volumes"),
            self.client.get(P + "/volumes/%s" % fx.V1),
            self.client.get(P + "/surahs"),
        ]
        tid = self.client.get(P + "/topics").get_json()["data"]["items"][0][
            "topic_id"]
        responses += [
            self.client.get(P + "/topics/%s" % tid),
            self.client.get(P + "/pages/0"),
            self.client.get(P + "/pages/2"),
            self.client.get(P + "/pages/10"),
            self.client.get(P + "/pages/12"),
            self.client.get(P + "/pages/3/neighbors"),
            self.client.get(P + "/search", query_string={"q": "زبان"}),
            self.client.get(P + "/search", query_string={"q": "غایب"}),
            self.client.get(P + "/statistics"),
            self.client.get(P + "/health"),
            self.client.get(P + "/openapi.json"),
            self.client.get(P + "/docs"),
            self.client.get(P + "/pages/9"),
            self.client.get(P + "/volumes/nope"),
            self.client.post(P + "/catalog"),
        ]
        self.assertGreaterEqual(len(responses), 18)
        for r in responses:
            self.assert_no_leak_body(r)

    def assert_no_leak_body(self, r):
        body = r.get_data(as_text=True)
        for s in FORBIDDEN_SUBSTRINGS:
            self.assertNotIn(s, body,
                             "%r leaked in %s" % (s, r.request.path))

    def test_corpus_byte_identical_after_api_use(self):
        # spec §9.2 I-6: the API never writes to the corpus/read model
        for name, sha in self.before.items():
            self.assertEqual(sha256_file(
                os.path.join(self.state["corpus_dir"], name)), sha,
                "corpus file %s changed" % name)
        self.assertEqual(sha256_file(self.state["db_path"]),
                         self.state["report"]["db_sha256"])


def rm_names():
    from tasnim.web import readmodel
    return list(readmodel.ALLOWED_SOURCE_FILES) + \
        list(readmodel.FORBIDDEN_SOURCE_FILES)


if __name__ == "__main__":
    unittest.main(verbosity=2)

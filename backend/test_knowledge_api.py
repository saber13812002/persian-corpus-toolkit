"""PCM-14A — Corpus Knowledge Studio (collections) tests.

KS-01 create Persian collection
KS-02 valid slug / collection_id / alias (deterministic)
KS-03 duplicate + invalid slug/name rejection
KS-04 list/detail after creation
KS-05 search, subject filter, pagination
Plus: PATCH rename (id/slug/alias stable), auth (401), subjects,
index-builds endpoint, studio page serving, slug prefill helper.

Follows the PCM-12.3 rule: import pct_test_support FIRST, then server.
"""
import hashlib
import re

import pct_test_support  # noqa: F401  (must precede `import server`)
import unittest

import server

PW = "test-secret-123"
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class Base(unittest.TestCase):
    def setUp(self):
        pct_test_support.reset_db()
        self.client = server.app.test_client()

    def login(self, password=PW):
        return self.client.post(
            "/api/auth/login", json={"password": password}
        )


class CollectionCreateTests(Base):
    """KS-01 / KS-02 / KS-03"""

    def test_ks01_create_persian_collection(self):
        self.login()
        r = self.client.post(
            "/api/knowledge/collections",
            json={
                "name": "کتابخانه علوم عقلی",
                "slug": "oloom-aqli",
                "description": "منابع علوم عقلی",
                "subject": "فلسفه",
            },
        )
        self.assertEqual(r.status_code, 201, r.get_data(as_text=True))
        j = r.get_json()
        self.assertTrue(j["ok"])
        c = j["collection"]
        self.assertEqual(c["name"], "کتابخانه علوم عقلی")
        self.assertEqual(c["slug"], "oloom-aqli")
        # c-51911bd0 == 'c-' + sha256(b'oloom-aqli')[:8]
        self.assertEqual(c["collection_id"], "c-51911bd0")
        self.assertEqual(c["es_alias"], "pct-col-oloom-aqli")
        self.assertEqual(c["book_count"], 0)
        self.assertEqual(c["chunk_count"], 0)
        self.assertEqual(c["indexing_status"], "none")
        self.assertEqual(c["validation_status"], "pending")
        self.assertEqual(c["collection_version"], 1)
        self.assertEqual(c["schema_version"], "s-1")
        self.assertEqual(c["normalization_version"], "n-1")
        self.assertEqual(c["chunking_version"], "c-1")

    def test_ks02_deterministic_ids_and_alias(self):
        self.login()
        r = self.client.post(
            "/api/knowledge/collections",
            json={"name": "تفاسیر قرآن", "slug": "tafasir-quran"},
        )
        self.assertEqual(r.status_code, 201)
        c = r.get_json()["collection"]
        expected_id = "c-" + hashlib.sha256(b"tafasir-quran").hexdigest()[:8]
        self.assertEqual(c["collection_id"], expected_id)
        self.assertTrue(SLUG_RE.match(c["slug"]))
        self.assertTrue(c["es_alias"].startswith("pct-col-"))
        self.assertEqual(len(c["es_alias"]), len("pct-col-") + len(c["slug"]))

    def test_ks03_duplicate_slug_rejected(self):
        self.login()
        self.client.post(
            "/api/knowledge/collections",
            json={"name": "اول", "slug": "dup-slug"},
        )
        r = self.client.post(
            "/api/knowledge/collections",
            json={"name": "دوم", "slug": "dup-slug"},
        )
        self.assertEqual(r.status_code, 409)
        self.assertFalse(r.get_json()["ok"])

    def test_ks03_invalid_slug(self):
        self.login()
        for bad in ("has space", "fa-کتاب", "a", "-lead", "trail-", "a" * 65):
            r = self.client.post(
                "/api/knowledge/collections",
                json={"name": "نام", "slug": bad},
            )
            self.assertEqual(
                r.status_code, 400, f"slug {bad!r} should be rejected"
            )
            self.assertEqual(r.get_json().get("field"), "slug")

    def test_ks03_uppercase_normalized_then_collides(self):
        self.login()
        r = self.client.post(
            "/api/knowledge/collections",
            json={"name": "بزرگ", "slug": "OloomAqli"},
        )
        self.assertEqual(r.status_code, 201, r.get_data(as_text=True))
        self.assertEqual(r.get_json()["collection"]["slug"], "oloomaqli")
        # a differently-cased duplicate must collide, not create a twin
        r2 = self.client.post(
            "/api/knowledge/collections",
            json={"name": "بزرگ‌تر", "slug": "OLOOMAQLI"},
        )
        self.assertEqual(r2.status_code, 409)

    def test_ks03_missing_name(self):
        self.login()
        r = self.client.post(
            "/api/knowledge/collections", json={"slug": "good-slug"}
        )
        self.assertEqual(r.status_code, 400)
        r2 = self.client.post(
            "/api/knowledge/collections", json={"name": "   ", "slug": "good-slug"}
        )
        self.assertEqual(r2.status_code, 400)

    def test_same_name_different_slug_allowed(self):
        self.login()
        self.assertEqual(
            self.client.post(
                "/api/knowledge/collections",
                json={"name": "تک", "slug": "single-1"},
            ).status_code,
            201,
        )
        self.assertEqual(
            self.client.post(
                "/api/knowledge/collections",
                json={"name": "تک", "slug": "single-2"},
            ).status_code,
            201,
        )


class CollectionListDetailTests(Base):
    """KS-04 / KS-05 + PATCH + subjects + builds"""

    def _make(self, name, slug, subject=None):
        r = self.client.post(
            "/api/knowledge/collections",
            json={"name": name, "slug": slug, "subject": subject},
        )
        self.assertEqual(r.status_code, 201, r.get_data(as_text=True))
        return r.get_json()["collection"]

    def test_ks04_detail_after_create(self):
        self.login()
        c = self._make("کتاب اول", "book-one", "فلسفه")
        r = self.client.get(
            f"/api/knowledge/collections/{c['id']}"
        )
        self.assertEqual(r.status_code, 200)
        j = r.get_json()["collection"]
        self.assertEqual(j["collection_id"], c["collection_id"])
        self.assertEqual(j["documents"], [])
        self.assertEqual(j["index_builds"], [])
        r404 = self.client.get("/api/knowledge/collections/9999")
        self.assertEqual(r404.status_code, 404)

    def test_ks05_search_subject_filter_pagination(self):
        self.login()
        self._make("کتابخانه فلسفه", "falsafeh", "فلسفه")
        self._make("تفاسیر قرآن", "tafasir", "قرآن")
        self._make("منطق رواقی", "mantegh", "فلسفه")

        # no filter: 3
        r = self.client.get("/api/knowledge/collections")
        self.assertEqual(r.get_json()["total"], 3)

        # search by name (Persian)
        r = self.client.get("/api/knowledge/collections?search=فلسفه")
        self.assertEqual(r.get_json()["total"], 1)
        self.assertEqual(
            r.get_json()["collections"][0]["slug"], "falsafeh"
        )

        # search by slug (Latin)
        r = self.client.get("/api/knowledge/collections?search=tafasir")
        self.assertEqual(r.get_json()["total"], 1)

        # subject filter
        r = self.client.get("/api/knowledge/collections?subject=فلسفه")
        self.assertEqual(r.get_json()["total"], 2)

        # pagination
        r = self.client.get("/api/knowledge/collections?per_page=2&page=1")
        j = r.get_json()
        self.assertEqual(len(j["collections"]), 2)
        self.assertEqual(j["total_pages"], 2)
        r = self.client.get("/api/knowledge/collections?per_page=2&page=2")
        j = r.get_json()
        self.assertEqual(len(j["collections"]), 1)

        # sort by name ASC
        r = self.client.get("/api/knowledge/collections?sort=name&order=ASC&per_page=10")
        slugs = [c["slug"] for c in r.get_json()["collections"]]
        self.assertEqual(len(slugs), 3)

    def test_patch_rename_keeps_identity_stable(self):
        self.login()
        c = self._make("نام قدیمی", "stable-slug")
        r = self.client.patch(
            f"/api/knowledge/collections/{c['id']}",
            json={
                "name": "نام جدید",
                "description": "توضیح تازه",
                "subject": "تاریخ",
            },
        )
        self.assertEqual(r.status_code, 200, r.get_data(as_text=True))
        c2 = r.get_json()["collection"]
        self.assertEqual(c2["name"], "نام جدید")
        self.assertEqual(c2["description"], "توضیح تازه")
        self.assertEqual(c2["subject"], "تاریخ")
        # identity must NOT move when only display fields change
        self.assertEqual(c2["collection_id"], c["collection_id"])
        self.assertEqual(c2["slug"], c["slug"])
        self.assertEqual(c2["es_alias"], c["es_alias"])
        self.assertEqual(c2["collection_version"], c["collection_version"])

    def test_patch_requires_content(self):
        self.login()
        c = self._make("نام", "patch-empty")
        r = self.client.patch(
            f"/api/knowledge/collections/{c['id']}", json={"bogus": 1}
        )
        self.assertEqual(r.status_code, 400)

    def test_subjects_grouped(self):
        self.login()
        self._make("الف", "subj-a", "فلسفه")
        self._make("ب", "subj-b", "فلسفه")
        self._make("ج", "subj-c", "قرآن")
        r = self.client.get("/api/knowledge/subjects")
        self.assertEqual(r.status_code, 200)
        subj = {s["subject"]: s["n"] for s in r.get_json()["subjects"]}
        self.assertEqual(subj, {"فلسفه": 2, "قرآن": 1})

    def test_index_builds_endpoint_and_record(self):
        self.login()
        c = self._make("با build", "with-build")
        # insert a build row directly (PCM-14D will own the API)
        import sqlite3
        conn = sqlite3.connect(server.DB_PATH)
        conn.row_factory = sqlite3.Row
        conn.execute(
            """INSERT INTO knowledge_index_builds
               (iv_id, collection_id, es_index, es_alias, schema_version,
                norm_version, chunking_version, chunk_count, status, created_at, completed_at)
               VALUES (?, ?, ?, ?, 's-1', 'n-1', 'c-1', 120, 'active',
                       '2026-10-26T10:00:00Z', '2026-10-26T10:05:00Z')""",
            (
                "iv-1", c["collection_id"],
                "pct-col-with-build-v0001", "pct-col-with-build",
            ),
        )
        conn.commit()
        conn.close()
        r = self.client.get(
            f"/api/knowledge/collections/{c['id']}/builds"
        )
        self.assertEqual(r.status_code, 200)
        j = r.get_json()
        self.assertEqual(len(j["builds"]), 1)
        self.assertEqual(j["builds"][0]["iv_id"], "iv-1")
        self.assertEqual(j["builds"][0]["es_index"], "pct-col-with-build-v0001")


class AuthSecurityTests(Base):
    """KS-22 (partial): /api/knowledge/* behind PCM-09 auth"""

    def test_unauthenticated_401(self):
        # GET on list/subjects/detail, POST on create — all must be 401
        # before login. (PATCH on detail is verified via the authenticated
        # path in CollectionListDetailTests.)
        for path, method in [
            ("/api/knowledge/collections", "GET"),
            ("/api/knowledge/collections", "POST"),
            ("/api/knowledge/subjects", "GET"),
            ("/api/knowledge/collections/1", "GET"),
        ]:
            r = (
                self.client.get(path)
                if method == "GET"
                else self.client.post(path, json={})
            )
            self.assertEqual(
                r.status_code, 401, f"{method} {path} should be 401"
            )

    def test_wrong_password_401(self):
        r = self.client.post(
            "/api/auth/login", json={"password": "wrong-password"}
        )
        self.assertEqual(r.status_code, 401)
        r = self.client.get("/api/knowledge/collections")
        self.assertEqual(r.status_code, 401)

    def test_studio_page_served_without_login(self):
        # Like /dashboard/ itself: the page is public, the data is protected.
        r = self.client.get("/dashboard/studio.html")
        self.assertEqual(r.status_code, 200)
        self.assertIn("استودیوی دانش", r.get_data(as_text=True))

    def test_existing_endpoints_still_open(self):
        # Extension write APIs must stay OPEN (AGENTS.md rule 6).
        r = self.client.get("/api/stats")
        self.assertEqual(r.status_code, 200)


class SlugPrefillTests(Base):
    """_slug_from_name: valid slug output for Persian names"""

    def test_persian_name_produces_valid_slug(self):
        from knowledge_api import _slug_from_name
        for name in (
            "کتابخانه علوم عقلی",
            "تفاسیر قرآن",
            "کتاب اول ۱۴۰۵",
            "منطق و فلسفه",
        ):
            slug = _slug_from_name(name)
            self.assertTrue(slug, f"empty slug for {name!r}")
            self.assertLessEqual(len(slug), 64)
            self.assertTrue(SLUG_RE.match(slug), f"invalid slug {slug!r} from {name!r}")

    def test_latin_name_passthrough(self):
        from knowledge_api import _slug_from_name
        self.assertEqual(_slug_from_name("Book One"), "book-one")


if __name__ == "__main__":
    unittest.main(verbosity=2)

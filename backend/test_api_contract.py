# -*- coding: utf-8 -*-
"""test_api_contract — PCM-19: OpenAPI↔app contract tests (CT-01..CT-06).

These tests make the additive OpenAPI specs (PCM-14D work registry,
PCM-15/17 file queue, PCM-20.9 pipeline/release) a machine-enforced
contract against the live app:

  CT-01 spec validity — both specs parse, openapi 3.x, info complete,
                        every operation has an operationId, every local
                        $ref resolves, path parameters are declared.
  CT-02 spec⊆app      — every (path, method) declared in the specs exists
                        as a route on server.app (spec drift fails here).
  CT-03 auth contract — every declared operation answers 401 to an
                        unauthenticated client (PCM-09, no silent opens).
  CT-04 schema↔live   — a live ImportBatch row, Work/Edition/Volume objects
                        and the list's queue counters carry at least the
                        properties declared by the spec schemas.
  CT-05 error contract — 400 carries ok=false + field + message
                        (field=collection_id / key / volume_no), 404 for
                        unknown ids, per_page clamps to 100 (not 400),
                        pagination fields are present and integral.
  CT-06 operation ids — operationIds are unique across both specs and
                        (path, method) is not declared twice.

PyYAML is only required by CT-01/02/03/04/06; those classes skip honestly
when yaml is unavailable (e.g. the 32-bit Python 3.14 default env), while
CT-05 needs no third-party imports. The full matrix runs on Python 3.13,
where pyyaml is installed.

Follows the PCM-12.3 rule: import pct_test_support FIRST, then server.
The production database is never opened (PCT_DB is always set by the
support module).
"""
import os
import re
import shutil
import tempfile
import unittest

import pct_test_support  # noqa: F401  (must precede `import server`)

import server

try:
    import yaml
except ImportError:  # environment without PyYAML (32-bit Python 3.14)
    yaml = None

PW = "test-secret-123"
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPEC_14D = os.path.join(REPO_ROOT, "docs", "openapi",
                        "pcm14d-knowledge-work-registry.openapi.yaml")
SPEC_15 = os.path.join(REPO_ROOT, "docs", "openapi",
                       "pcm15-file-queue.openapi.yaml")
SPEC_209 = os.path.join(REPO_ROOT, "docs", "openapi",
                        "pcm209-pipeline-release.openapi.yaml")
SPECS = [SPEC_14D, SPEC_15, SPEC_209]
HTTP_METHODS = ("get", "post", "put", "patch", "delete")


def load_specs():
    """Return {filename: parsed spec} (requires PyYAML)."""
    out = {}
    for path in SPECS:
        with open(path, encoding="utf-8") as fh:
            out[os.path.basename(path)] = yaml.safe_load(fh)
    return out


def iter_ops(spec):
    """Yield (path, METHOD, operation) for every operation in a spec."""
    for path, item in spec["paths"].items():
        if not isinstance(item, dict):
            continue
        for method in HTTP_METHODS:
            op = item.get(method)
            if isinstance(op, dict):
                yield path, method.upper(), op


def app_route_set():
    """{(template, METHOD)} for every /api/knowledge route on the app.

    Flask converters (<batch_id>, <int:coll_id>) are normalised to the
    OpenAPI template form ({batch_id}, {coll_id}).
    """
    routes = set()
    for rule in server.app.url_map.iter_rules():
        if not rule.rule.startswith("/api/knowledge"):
            continue
        template = re.sub(r"<(?:\w+:)?(\w+)>", r"{\1}", rule.rule)
        for method in rule.methods:
            if method in ("GET", "POST", "PUT", "PATCH", "DELETE"):
                routes.add((template, method))
    return routes


def _collect_refs(node, found):
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "$ref" and isinstance(value, str):
                found.append(value)
            else:
                _collect_refs(value, found)
    elif isinstance(node, list):
        for item in node:
            _collect_refs(item, found)
    return found


def _resolve_ref(spec, ref):
    """Resolve a local '#/...' pointer or raise AssertionError."""
    assert ref.startswith("#/"), "non-local $ref not expected: %r" % ref
    node = spec
    for part in ref[2:].split("/"):
        part = part.replace("~1", "/").replace("~0", "~")
        assert isinstance(node, dict), "ref %r does not resolve" % ref
        assert part in node, "unresolved $ref %r (missing key %r)" % (ref, part)
        node = node[part]
    return node


def _path_url(path):
    """Fill spec path templates with dummy ids (values never reach a view:
    the 401 auth check fires first). value_id is an <int:...> converter,
    so it must be numeric."""
    def repl(m):
        name = m.group(1)
        if name in ("value_id", "coll_id"):
           return "999999"
        return name.split("_")[0] + "-ffffffff"
    return re.sub(r"\{(\w+)\}", repl, path)


class Base(unittest.TestCase):
    def setUp(self):
        pct_test_support.reset_db()
        self._datadir = tempfile.mkdtemp(prefix="pct-contract-")
        self._old_dd = os.environ.get("PCT_KNOWLEDGE_DATA_DIR")
        os.environ["PCT_KNOWLEDGE_DATA_DIR"] = self._datadir
        self.client = server.app.test_client()

    def tearDown(self):
        if self._old_dd is None:
            os.environ.pop("PCT_KNOWLEDGE_DATA_DIR", None)
        else:
            os.environ["PCT_KNOWLEDGE_DATA_DIR"] = self._old_dd
        shutil.rmtree(self._datadir, ignore_errors=True)

    def login(self, password=PW):
        return self.client.post(
            "/api/auth/login", json={"password": password}
        )

    def make_collection(self, name="کتابخانه قرارداد", slug="contract-test"):
        r = self.client.post(
            "/api/knowledge/collections",
            json={"name": name, "slug": slug},
        )
        self.assertEqual(r.status_code, 201, r.get_data(as_text=True))
        return r.get_json()["collection"]


@unittest.skipUnless(yaml is not None, "PyYAML not installed")
class TestCT01_SpecValidity(unittest.TestCase):
    """CT-01: the two OpenAPI specs are machine-valid documents."""

    def setUp(self):
        self.specs = load_specs()

    def test_ct01a_parse_and_version(self):
        self.assertEqual(len(self.specs), 3)
        for name, spec in self.specs.items():
            with self.subTest(spec=name):
                self.assertTrue(
                    str(spec.get("openapi", "")).startswith("3."),
                    "openapi version missing/unsupported: %r" % spec.get("openapi"))
                self.assertTrue(spec["info"]["title"].strip())
                self.assertTrue(str(spec["info"]["version"]).strip())
                self.assertTrue(spec["paths"], "spec declares no paths")
                self.assertTrue(spec["components"]["schemas"],
                                "spec declares no schemas")

    def test_ct01b_every_operation_has_operation_id(self):
        for name, spec in self.specs.items():
            for path, method, op in iter_ops(spec):
                with self.subTest(spec=name, op=method + " " + path):
                    self.assertIn("operationId", op)
                    self.assertRegex(op["operationId"],
                                     r"^[A-Za-z][A-Za-z0-9]*$")

    def test_ct01c_local_refs_resolve(self):
        for name, spec in self.specs.items():
            refs = _collect_refs(spec, [])
            self.assertTrue(refs, "no $ref found at all (suspicious)")
            for ref in refs:
                with self.subTest(spec=name, ref=ref):
                    _resolve_ref(spec, ref)

    def test_ct01d_path_parameters_consistent(self):
        for name, spec in self.specs.items():
            for path, item in spec["paths"].items():
                if not isinstance(item, dict):
                    continue
                declared = set()
                for p in item.get("parameters") or []:
                    if p.get("in") == "path":
                        declared.add(p["name"])
                for method in HTTP_METHODS:
                    op = item.get(method)
                    if not isinstance(op, dict):
                        continue
                    for p in op.get("parameters") or []:
                        if p.get("in") == "path":
                            declared.add(p["name"])
                with self.subTest(spec=name, path=path):
                    self.assertEqual(
                        declared, set(re.findall(r"\{(\w+)\}", path)),
                        "declared path parameters do not match the template")


@unittest.skipUnless(yaml is not None, "PyYAML not installed")
class TestCT02_SpecCoverage(unittest.TestCase):
    """CT-02: every declared spec operation exists as a live app route."""

    def test_ct02a_every_spec_operation_exists_in_app(self):
        routes = app_route_set()
        missing = []
        total = 0
        for name, spec in load_specs().items():
            for path, method, op in iter_ops(spec):
                total += 1
                if (path, method) not in routes:
                    missing.append("%s %s %s" % (name, method, path))
        self.assertGreaterEqual(total, 19, "expected at least 19 operations")
        self.assertEqual(missing, [],
                         "spec operations missing from the app: %s" % missing)


@unittest.skipUnless(yaml is not None, "PyYAML not installed")
class TestCT03_AuthContract(Base):
    """CT-03: every declared operation is behind PCM-09 auth (401)."""

    def test_ct03a_all_declared_operations_require_auth(self):
        checked = 0
        for name, spec in load_specs().items():
            for path, method, op in iter_ops(spec):
                with self.subTest(spec=name, op=method + " " + path):
                    url = _path_url(path)
                    sender = {
                        "GET": self.client.get,
                        "POST": self.client.post,
                        "PUT": self.client.put,
                        "PATCH": self.client.patch,
                        "DELETE": self.client.delete,
                    }[method]
                    r = sender(url)
                    self.assertEqual(r.status_code, 401,
                                     "expected 401 unauthenticated for %s %s"
                                     % (method, path))
                    checked += 1
        self.assertGreaterEqual(checked, 19)


@unittest.skipUnless(yaml is not None, "PyYAML not installed")
class TestCT04_SchemaLiveShape(Base):
    """CT-04: live responses carry at least the declared schema properties."""

    def setUp(self):
        super().setUp()
        self.specs = load_specs()

    def _props(self, name):
        for spec in self.specs.values():
            schema = spec["components"]["schemas"].get(name)
            if schema is not None:
                return set(schema["properties"].keys())
        self.fail("schema %r not found in either spec" % name)

    def test_ct04a_batch_row_matches_importbatch(self):
        self.login()
        coll = self.make_collection()
        cid = coll["collection_id"]
        r = self.client.post("/api/knowledge/import/batches", json={
            "collection_id": cid, "folder_name": "contract",
            "files": [{"name": "contract.docx", "size": 1234,
                       "sha256": "a" * 64}],
        })
        self.assertEqual(r.status_code, 201, r.get_data(as_text=True))
        lst = self.client.get(
            "/api/knowledge/import/batches?collection_id=" + cid)
        self.assertEqual(lst.status_code, 200, lst.get_data(as_text=True))
        body = lst.get_json()
        self.assertEqual(body["total"], 1)
        row = body["batches"][0]
        missing = self._props("ImportBatch") - set(row)
        self.assertEqual(missing, set(),
                         "batch row misses schema properties: %r" % missing)
        self.assertIn(row["status"], ("planned", "processing", "done"))
        self.assertIn(row["paused"], (0, 1))
        counters = body["queue"]["counters"]
        missing = self._props("QueueCounters") - set(counters)
        self.assertEqual(missing, set(),
                         "queue counters miss schema properties: %r" % missing)

    def test_ct04b_work_edition_volume_match_schemas(self):
        self.login()
        r = self.client.post("/api/knowledge/works", json={
            "title": "الموجات", "author": "میرداماد", "language": "fa"})
        self.assertEqual(r.status_code, 201, r.get_data(as_text=True))
        body = r.get_json()
        self.assertTrue(body["ok"])
        self.assertTrue(body["created"])
        work = body["work"]
        missing = self._props("Work") - set(work)
        self.assertEqual(missing, set(),
                         "work misses schema properties: %r" % missing)
        self.assertRegex(work["work_id"], r"^w-[0-9a-f]{8}$")
        self.assertEqual(work["source"], "user")

        r2 = self.client.post(
            "/api/knowledge/works/" + work["work_id"] + "/editions",
            json={"publisher": "نشر علمی", "publish_year": "1399"})
        self.assertEqual(r2.status_code, 201, r2.get_data(as_text=True))
        edition = r2.get_json()["edition"]
        missing = self._props("Edition") - set(edition)
        self.assertEqual(missing, set(),
                         "edition misses schema properties: %r" % missing)
        self.assertEqual(edition["work_id"], work["work_id"])

        r3 = self.client.post(
            "/api/knowledge/editions/" + edition["edition_id"] + "/volumes",
            json={"volume_no": 1, "label": "جلد اول"})
        self.assertEqual(r3.status_code, 201, r3.get_data(as_text=True))
        volume = r3.get_json()["volume"]
        missing = self._props("Volume") - set(volume)
        self.assertEqual(missing, set(),
                         "volume misses schema properties: %r" % missing)
        self.assertEqual(volume["work_id"], work["work_id"])
        self.assertEqual(volume["volume_no"], 1)

        # idempotent re-create: created=False, same deterministic id
        r4 = self.client.post("/api/knowledge/works", json={
            "title": "الموجات", "author": "میرداماد", "language": "fa"})
        self.assertEqual(r4.status_code, 201)
        self.assertFalse(r4.get_json()["created"])
        self.assertEqual(r4.get_json()["work"]["work_id"], work["work_id"])


class TestCT05_ErrorContract(Base):
    """CT-05: documented error shapes (no PyYAML needed)."""

    def test_ct05a_missing_collection_id_400(self):
        self.login()
        r = self.client.get("/api/knowledge/import/batches")
        self.assertEqual(r.status_code, 400)
        body = r.get_json()
        self.assertIs(body["ok"], False)
        self.assertEqual(body["field"], "collection_id")
        self.assertIsInstance(body["message"], str)
        self.assertTrue(body["message"])

    def test_ct05b_unknown_collection_404(self):
        self.login()
        r = self.client.get(
            "/api/knowledge/import/batches?collection_id=c-nosuch1")
        self.assertEqual(r.status_code, 404)
        body = r.get_json()
        self.assertIs(body["ok"], False)
        self.assertEqual(body["field"], "collection_id")
        self.assertIn("message", body)

    def test_ct05c_per_page_clamped_to_100(self):
        self.login()
        coll = self.make_collection()
        r = self.client.get(
            "/api/knowledge/import/batches?collection_id=%s&per_page=500"
            % coll["collection_id"])
        self.assertEqual(r.status_code, 200, r.get_data(as_text=True))
        self.assertEqual(r.get_json()["per_page"], 100)

    def test_ct05d_pagination_fields_integral(self):
        self.login()
        coll = self.make_collection()
        r = self.client.get(
            "/api/knowledge/import/batches?collection_id=%s&page=2"
            % coll["collection_id"])
        self.assertEqual(r.status_code, 200, r.get_data(as_text=True))
        body = r.get_json()
        for key in ("total", "page", "per_page", "total_pages"):
            self.assertIsInstance(body[key], int, "pagination field %r" % key)
        self.assertEqual(body["page"], 2)
        self.assertEqual(body["total_pages"], 0)  # 0 rows -> (0+n-1)//n = 0

    def test_ct05e_unknown_work_404(self):
        self.login()
        r = self.client.get("/api/knowledge/works/w-ffffffff")
        self.assertEqual(r.status_code, 404)
        body = r.get_json()
        self.assertIs(body["ok"], False)
        self.assertIn("message", body)

    def test_ct05f_work_requires_key_400(self):
        self.login()
        r = self.client.post("/api/knowledge/works", json={"language": "fa"})
        self.assertEqual(r.status_code, 400)
        body = r.get_json()
        self.assertIs(body["ok"], False)
        self.assertEqual(body["field"], "key")
        self.assertIn("message", body)

    def test_ct05g_volume_no_non_numeric_400(self):
        self.login()
        work = self.client.post("/api/knowledge/works",
                                json={"title": "ت", "author": "ا"}).get_json()["work"]
        edition = self.client.post(
            "/api/knowledge/works/%s/editions" % work["work_id"],
            json={}).get_json()["edition"]
        r = self.client.post(
            "/api/knowledge/editions/%s/volumes" % edition["edition_id"],
            json={"volume_no": "یک"})
        self.assertEqual(r.status_code, 400)
        body = r.get_json()
        self.assertIs(body["ok"], False)
        self.assertEqual(body["field"], "volume_no")

    def test_ct05h_unknown_batch_resume_404(self):
        self.login()
        r = self.client.post(
            "/api/knowledge/import/batches/b-ffffffff/resume")
        self.assertEqual(r.status_code, 404)
        self.assertIs(r.get_json()["ok"], False)


@unittest.skipUnless(yaml is not None, "PyYAML not installed")
class TestCT06_OperationIds(unittest.TestCase):
    """CT-06: stable, unique machine identifiers across both specs."""

    def test_ct06a_operation_ids_unique(self):
        seen = {}
        for name, spec in load_specs().items():
            for path, method, op in iter_ops(spec):
                oid = op["operationId"]
                with self.subTest(spec=name, op=oid):
                    self.assertNotIn(oid, seen,
                                     "duplicate operationId across specs")
                seen[oid] = (name, method, path)

    def test_ct06b_no_duplicate_path_method(self):
        seen = {}
        for name, spec in load_specs().items():
            for path, method, op in iter_ops(spec):
                key = (path, method)
                with self.subTest(spec=name, op=key):
                    self.assertNotIn(key, seen,
                                     "same (path, method) declared twice")
                seen[key] = (name, op["operationId"])

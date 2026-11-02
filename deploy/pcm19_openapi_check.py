#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PCM-19 — OpenAPI machine-validity checker (CI job `openapi`).

A lightweight, dependency-light mirror of CT-01 in
backend/test_api_contract.py: every spec under docs/openapi/*.yaml must
parse, declare openapi 3.x, carry an operationId on every operation,
resolve every local $ref, and keep declared path parameters consistent
with the path template. No Flask, no DB — safe to run anywhere.

Usage:  python deploy/pcm19_openapi_check.py    (exit 0 = all valid)
Requires PyYAML (installed by the CI before_script).
"""
import glob
import os
import re
import sys

try:
    import yaml
except ImportError:
    sys.stderr.write("PyYAML is required (pip install pyyaml)\n")
    raise

HTTP_METHODS = ("get", "post", "put", "patch", "delete")


def _resolve(spec, ref):
    if not ref.startswith("#/"):
        raise AssertionError("non-local $ref: %r" % ref)
    node = spec
    for part in ref[2:].split("/"):
        part = part.replace("~1", "/").replace("~0", "~")
        if not isinstance(node, dict) or part not in node:
            raise AssertionError("unresolved $ref: %r" % ref)
        node = node[part]
    return node


def _refs(node, found):
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "$ref" and isinstance(value, str):
                found.append(value)
            else:
                _refs(value, found)
    elif isinstance(node, list):
        for item in node:
            _refs(item, found)


def check_spec(path):
    with open(path, encoding="utf-8") as fh:
        spec = yaml.safe_load(fh)
    assert str(spec.get("openapi", "")).startswith("3."), \
        "openapi version missing/unsupported"
    assert spec["info"]["title"].strip(), "info.title empty"
    assert spec["info"]["version"].strip(), "info.version empty"
    refs = []
    _refs(spec, refs)
    for ref in refs:
        _resolve(spec, ref)
    ops = 0
    for p, item in spec["paths"].items():
        if not isinstance(item, dict):
            continue
        declared = {q["name"] for q in (item.get("parameters") or [])
                    if q.get("in") == "path"}
        template = set(re.findall(r"\{(\w+)\}", p))
        for m in HTTP_METHODS:
            op = item.get(m)
            if not isinstance(op, dict):
                continue
            ops += 1
            assert op.get("operationId"), \
                "operation without operationId: %s %s" % (m, p)
            for q in (op.get("parameters") or []):
                if q.get("in") == "path":
                    declared.add(q["name"])
        assert declared == template, \
            "path parameters %r != template %r" % (declared, template)
    assert ops > 0, "spec declares no operations"
    return ops


def main():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    specs = sorted(glob.glob(os.path.join(root, "docs", "openapi", "*.yaml")))
    if not specs:
        print("NO SPECS FOUND under docs/openapi/", file=sys.stderr)
        return 1
    total = 0
    for p in specs:
        ops = check_spec(p)
        total += ops
        print("OK  %s  (%d operations, refs resolved)"
              % (os.path.relpath(p, root), ops))
    print("OpenAPI check passed: %d specs, %d operations"
          % (len(specs), total))
    return 0


if __name__ == "__main__":
    sys.exit(main())

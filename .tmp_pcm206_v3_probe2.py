# -*- coding: utf-8 -*-
"""PCM-20.6 D1 probe 2: find which keys differ in corpus.json across roots."""
import contextlib
import io
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from corpus.tasnim import cli as CL          # noqa: E402
from test_corpus_semantic import make_semantic_fixture  # noqa: E402


def chain(root):
    os.makedirs(root, exist_ok=True)
    fx = os.path.join(root, "src")
    os.makedirs(fx, exist_ok=True)
    jl = os.path.join(fx, "t.jsonl")
    make_semantic_fixture(jl)
    for a in (
        ["build-corpus", "--jsonl", jl, "--data-root", root],
        ["build-semantic", "--data-root", root, "--base", "v0001"],
        ["build-semantic", "--data-root", root, "--base", "v0002",
         "--contract", "cs-20.6"],
    ):
        with contextlib.redirect_stdout(io.StringIO()):
            rc = CL.main(a)
        assert rc == 0, (a, rc)


def diff_keys(x, y, path=""):
    if isinstance(x, dict) and isinstance(y, dict):
        for k in sorted(set(x) | set(y)):
            p = path + "." + k
            if k not in x:
                print("ONLY-B", p)
            elif k not in y:
                print("ONLY-A", p)
            else:
                diff_keys(x[k], y[k], p)
    elif x != y:
        print("DIFF", path, repr(x)[:80], "VS", repr(y)[:80])


def main():
    a = os.path.join(tempfile.mkdtemp(prefix="pctv3qa-"), "data", "tasnim")
    b = os.path.join(tempfile.mkdtemp(prefix="pctv3qb-"), "data", "tasnim")
    chain(a)
    chain(b)
    for tag in ("v0001", "v0002", "v0003"):
        print("=== %s corpus.json ===" % tag)
        da = os.path.join(a, "corpus", "builds", tag, "corpus.json")
        db = os.path.join(b, "corpus", "builds", tag, "corpus.json")
        diff_keys(json.load(open(da, encoding="utf-8")),
                  json.load(open(db, encoding="utf-8")))
    # manifest data section
    for tag in ("v0001", "v0002", "v0003"):
        print("=== %s manifest.json ===" % tag)
        da = os.path.join(a, "corpus", "builds", tag, "manifest.json")
        db = os.path.join(b, "corpus", "builds", tag, "manifest.json")
        diff_keys(json.load(open(da, encoding="utf-8")),
                  json.load(open(db, encoding="utf-8")))


if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
"""PCM-20.6 D1 probe: cross-root v3 determinism + file-level comparison."""
import contextlib
import io
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from corpus.tasnim import cli as CL          # noqa: E402
from corpus.tasnim import common as C        # noqa: E402
from test_corpus_semantic import make_semantic_fixture  # noqa: E402


def chain(root):
    os.makedirs(root, exist_ok=True)
    fx = os.path.join(root, "src")
    os.makedirs(fx, exist_ok=True)
    jl = os.path.join(fx, "t.jsonl")
    make_semantic_fixture(jl)
    args = (
        ["build-corpus", "--jsonl", jl, "--data-root", root],
        ["build-semantic", "--data-root", root, "--base", "v0001"],
        ["build-semantic", "--data-root", root, "--base", "v0002",
         "--contract", "cs-20.6"],
    )
    for a in args:
        with contextlib.redirect_stdout(io.StringIO()):
            rc = CL.main(a)
        assert rc == 0, (a, rc)


def main():
    a = os.path.join(tempfile.mkdtemp(prefix="pctv3pa-"), "data", "tasnim")
    b = os.path.join(tempfile.mkdtemp(prefix="pctv3pb-"), "data", "tasnim")
    chain(a)
    chain(b)
    bad = 0
    for tag in ("v0001", "v0002", "v0003"):
        da = os.path.join(a, "corpus", "builds", tag)
        db = os.path.join(b, "corpus", "builds", tag)
        names = sorted(set(os.listdir(da)) | set(os.listdir(db)))
        for name in names:
            fa, fb = os.path.join(da, name), os.path.join(db, name)
            ea, eb = os.path.exists(fa), os.path.exists(fb)
            if ea and not eb:
                print(tag, name, "MISSING in B")
                bad += 1
                continue
            if eb and not ea:
                print(tag, name, "MISSING in A")
                bad += 1
                continue
            sa = C.sha256_file(fa)
            sb = C.sha256_file(fb)
            print(tag, name, "OK" if sa == sb else "DIFF")
            if sa != sb:
                bad += 1
    print("RESULT:", "DIFF" if bad else "IDENTICAL")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())

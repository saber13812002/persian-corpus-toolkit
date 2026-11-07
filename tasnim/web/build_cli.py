# -*- coding: utf-8 -*-
"""Tasnim Web V1 — read model builder CLI (PCM-20.6.4).

Usage:
    python -X utf8 -m tasnim.web.build_cli build --corpus <v0003-dir> --out <readmodel-dir>

The builder is read-only w.r.t. the corpus: it opens only pages.jsonl,
heading-records.jsonl, corpus.json and manifest.json (HP-1). It never
touches the crawler DB.
"""
import argparse
import json

from tasnim.web.readmodel import ReadModelBuilder


def main(argv=None):
    p = argparse.ArgumentParser(
        prog="tasnim.web.build_cli", description="Tasnim read model builder")
    sub = p.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="build the read model from a corpus build dir")
    b.add_argument("--corpus", required=True,
                   help="corpus build dir (e.g. data/tasnim/pcm20_5/corpus/builds/v0003)")
    b.add_argument("--out", required=True,
                   help="output read model dir (e.g. tasnim/data/readmodel/v0003)")
    args = p.parse_args(argv)
    if args.cmd == "build":
        report = ReadModelBuilder(args.corpus, args.out).build()
        print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

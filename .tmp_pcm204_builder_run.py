# -*- coding: utf-8 -*-
"""PCM-20.4-C: اجرای واقعی ai-dump-builder (server52and53/_aidump) روی خروجی‌های
export-dump — فقط با --mock-embed (دeterministic، بدون شبکه/LiteLLM/Neo4j).

هر مرحله یک product دایرکتوری مجزا در data/tasnim/pcm20_4/builder-input/ دارد:
  * کد Builder دست‌نخورده است (فقط اجرا می‌شود، از cwd خود).
  * کالکشن عملیاتی (falsafe_siasi) هرگز لمس نمی‌شود.
"""
import io
import json
import os
import shutil
import subprocess
import sys
import hashlib

ROOT = os.path.dirname(os.path.abspath(__file__))  # toolkit root
AIDUMP = r"C:\Users\s.tabatabaei\Documents\saberprojects\server52and53\_aidump"
DATA = os.path.join(ROOT, "data", "tasnim", "pcm20_4")
BIN = os.path.join(DATA, "builder-input")

sys.path.insert(0, ROOT)
from corpus.tasnim import dump as DP  # noqa: E402

CASES = [
    ("vol56", os.path.join(DATA, "dumps", "10pct", "v0001", "books.json"), 2197, 772),
    ("10pct", os.path.join(DATA, "dumps", "10pct", "v0002", "books.json"), 3416, 1168),
    ("100pct", os.path.join(DATA, "dumps", "100pct", "v0001", "books.json"), 33443, 12401),
]


def sha256_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def git_head(repo):
    try:
        r = subprocess.run(["git", "-C", repo, "rev-parse", "HEAD"],
                           capture_output=True, text=True, timeout=20)
        return r.stdout.strip() or None
    except Exception:
        return None


def main():
    lines = []

    def out(s=""):
        print(s, flush=True)
        lines.append(s)

    out("=== PCM-20.4-C: real ai-dump-builder (mock-embed) ===")
    out("builder repo   : %s" % AIDUMP)
    out("builder commit : %s" % git_head(AIDUMP))
    out("toolkit commit : %s" % git_head(ROOT))
    out("")

    results = {}
    for name, books_src, exp_records, exp_skipped in CASES:
        pdir = os.path.join(BIN, "tasnim_tafsir_%s" % name)
        os.makedirs(pdir, exist_ok=True)
        shutil.copyfile(books_src, os.path.join(pdir, "books.json"))
        with open(os.path.join(pdir, "product.json"), "w", encoding="utf-8", newline="\n") as f:
            json.dump(DP.make_product(), f, ensure_ascii=False, indent=2)
        books_sha = sha256_file(os.path.join(pdir, "books.json"))
        books_mb = os.path.getsize(os.path.join(pdir, "books.json")) / 1e6
        out("--- CASE %s ---" % name)
        out("  product dir : %s" % os.path.relpath(pdir, ROOT).replace(os.sep, "/"))
        out("  books.json  : %s (%.1f MB)  sha256=%s" % (os.path.relpath(books_src, ROOT).replace(os.sep, "/"), books_mb, books_sha))

        r = subprocess.run(
            [sys.executable, "-m", "builder", "build", "--product", pdir,
             "--mock-embed", "--no-embed-reuse"],
            cwd=AIDUMP, capture_output=True, text=True, encoding="utf-8", timeout=1800)
        logp = os.path.join(pdir, "build.log")
        with open(logp, "w", encoding="utf-8") as f:
            f.write(r.stdout or "")
            if r.stderr:
                f.write("\n[stderr]\n" + r.stderr)
        out("  exit=%d  log=%s" % (r.returncode, os.path.relpath(logp, ROOT).replace(os.sep, "/")))
        tail = [l for l in (r.stdout or "").splitlines()
                if l.startswith(("STATUS=", "BUILD=", "  loaded", "  model", "  embedding", "  validation", "collection="))]
        for l in tail[-14:]:
            out("  | " + l)

        # find newest build dir
        broot = os.path.join(pdir, "builds")
        builds = [b for b in os.listdir(broot)] if os.path.isdir(broot) else []
        if not builds:
            out("  ERROR: no build dir created")
            continue
        build_id = max(builds, key=lambda b: os.path.getmtime(os.path.join(broot, b, "manifest.json"))
                       if os.path.exists(os.path.join(broot, b, "manifest.json")) else 0)
        bdir = os.path.join(broot, build_id)
        mf = json.load(open(os.path.join(bdir, "manifest.json"), encoding="utf-8"))
        dump_path = os.path.join(bdir, mf["dump_filename"])
        # validate subcommand
        rv = subprocess.run([sys.executable, "-m", "builder", "validate",
                             "--product", pdir, "--build", build_id],
                            cwd=AIDUMP, capture_output=True, text=True,
                            encoding="utf-8", timeout=600)
        try:
            vres = json.loads(rv.stdout)
        except Exception:
            vres = {"status": "PARSE_FAIL", "raw": (rv.stdout or "")[:200]}
        cur = os.path.join(pdir, "current-%s.txt" % (mf.get("embedding_model") or "").replace("Qwen3-Embedding-0.6B", "qwen3-embed-06b"))
        results[name] = {
            "build_id": build_id,
            "manifest_sha256": sha256_file(os.path.join(bdir, "manifest.json")),
            "chunks_sha256": sha256_file(dump_path),
            "chunks_size_mb": round(os.path.getsize(dump_path) / 1e6, 1),
            "mapping_sha256": sha256_file(os.path.join(bdir, "mapping.json")),
            "records": mf.get("dump_record_count"),
            "skipped_short": mf.get("skipped_document_count"),
            "truncated": mf.get("truncated_embed_count"),
            "dim": mf.get("embedding_dimension"),
            "backend": mf.get("embedding_backend"),
            "validation": mf.get("validation", {}).get("status"),
            "validate_cmd": vres.get("status"),
            "current": open(cur, encoding="utf-8").read().strip() if os.path.exists(cur) else None,
        }
        out("  build_id    : %s" % build_id)
        out("  dump        : %d records  skipped_short=%s  truncated=%s  dim=%s  backend=%s"
            % (results[name]["records"], results[name]["skipped_short"],
               results[name]["truncated"], results[name]["dim"], results[name]["backend"]))
        out("  validation  : %s   (validate cmd: %s)" % (results[name]["validation"], results[name]["validate_cmd"]))
        out("  chunks sha  : %s (%.1f MB)" % (results[name]["chunks_sha256"], results[name]["chunks_size_mb"]))
        out("  manifest sha: %s" % results[name]["manifest_sha256"])
        out("")

    # checks
    errors = []
    exp = {c[0]: (c[2], c[3]) for c in CASES}
    for name, (er, es) in exp.items():
        r = results.get(name)
        if not r:
            errors.append("%s: no result" % name)
            continue
        if r["records"] != er:
            errors.append("%s: records %s != expected %s" % (name, r["records"], er))
        if r["skipped_short"] != es:
            errors.append("%s: skipped_short %s != expected %s" % (name, r["skipped_short"], es))
        if r["validation"] not in ("DUMP_VALIDATED", "READY_WITH_WARNINGS"):
            errors.append("%s: validation %s" % (name, r["validation"]))
        if r["backend"] != "mock":
            errors.append("%s: backend %s != mock" % (name, r["backend"]))
        if r["current"] != r["build_id"]:
            errors.append("%s: current pointer %s != build %s" % (name, r["current"], r["build_id"]))
    out("BUILDER CHECK: %s" % ("PASS (0 errors)" if not errors else "FAIL (%d)" % len(errors)))
    for e in errors:
        out("  ERR " + e)

    with open(os.path.join(DATA, "validation", "builder-run.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump({"builder_commit": git_head(AIDUMP), "cases": results}, f, ensure_ascii=False, indent=2)
    with open(os.path.join(ROOT, ".tmp_pcm204_builder_out.txt"), "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines))
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())

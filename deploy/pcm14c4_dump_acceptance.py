# -*- coding: utf-8 -*-
"""PCM-14C.4 — operational acceptance of the d-1 Dump contract.

Runs the REAL CLI (python -m factory.cli) end-to-end in an isolated work
dir (default: wf-out/pcm14c4, gitignored). Produces acceptance_results.json
inside the work dir. No production/DB/ES/network involvement.

Usage:
    python deploy/pcm14c4_dump_acceptance.py <input.docx> [workdir]

Steps:
 1. WF run1 + run2 on the same DOCX (repeatability)
 2. make-dump from run1 -> dump1 (with --input hash check)
 3. validate-dump dump1 (expect VALID, exit 0)
 4. dump-summary dump1 (record)
 5. copy dump1 -> dump1-copy, validate (expect VALID, exit 0)
 6. tamper copy: flip one char in blocks.jsonl -> validate (expect INVALID, exit 1)
 7. m-1 compat: downgrade manifest to m-1 -> make-dump -> validate (expect VALID + warning)
 8. compare run1 vs run2 (file_id, blocks_hash, input sha, output hashes, byte-stability)

Exit code: 0 if every step matched expectations, 1 otherwise.
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # repo root
BACKEND = os.path.join(ROOT, "backend")
WORK = None
DOCX = None

results = {"steps": {}}


def sha256_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()


def run_cli(args, cwd=BACKEND):
    r = subprocess.run([sys.executable, "-m", "factory.cli"] + args,
                       cwd=cwd, capture_output=True, text=True, encoding="utf-8")
    return r.returncode, r.stdout, r.stderr


def load_json(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def record(name, code, extra=None):
    results["steps"][name] = {"exit_code": code, **(extra or {})}
    print("[%s] exit=%s" % (name, code))


def main():
    global WORK, DOCX
    if len(sys.argv) < 2:
        print("usage: pcm14c4_dump_acceptance.py <input.docx> [workdir]")
        return 2
    DOCX = os.path.abspath(sys.argv[1])
    WORK = os.path.abspath(sys.argv[2]) if len(sys.argv) > 2 else \
        os.path.join(ROOT, "wf-out", "pcm14c4")
    if os.path.isdir(WORK):
        shutil.rmtree(WORK)
    os.makedirs(WORK)
    assert os.path.isfile(DOCX), DOCX

    # ---- 1. WF run1 + run2 ------------------------------------------------
    out1 = os.path.join(WORK, "run1")
    out2 = os.path.join(WORK, "run2")
    c, o, e = run_cli([DOCX, "--out", out1, "--quiet"])
    record("wf_run1", c, {"stderr_tail": e.strip()[-200:]})
    wf1 = o.strip().splitlines()[-1] if o.strip() else os.path.join(out1, "?")
    fid1 = os.path.basename(wf1)

    c, o, e = run_cli([DOCX, "--out", out2, "--quiet"])
    record("wf_run2", c, {"stderr_tail": e.strip()[-200:]})
    wf2 = o.strip().splitlines()[-1] if o.strip() else os.path.join(out2, "?")
    fid2 = os.path.basename(wf2)
    results["file_ids"] = {"run1": fid1, "run2": fid2, "match": fid1 == fid2}

    # ---- 2. make-dump (with --input verification) --------------------------
    d1 = os.path.join(WORK, "dump1")
    c, o, e = run_cli(["make-dump", wf1, "--dump-dir", d1, "--input", DOCX, "--json"])
    record("make_dump", c, {"stderr_tail": e.strip()[-200:]})
    dm1 = load_json(os.path.join(d1, "dump-manifest.json"))

    # ---- 3. validate-dump ---------------------------------------------------
    c, o, e = run_cli(["validate-dump", d1, "--json"])
    v1 = json.loads(o) if o.strip() else {}
    record("validate_dump1", c, {"valid": v1.get("valid"),
                                 "errors": v1.get("errors"),
                                 "warnings": v1.get("warnings")})

    # ---- 4. dump-summary ----------------------------------------------------
    c, o, e = run_cli(["dump-summary", d1, "--json"])
    s1 = json.loads(o) if o.strip() else {}
    record("dump_summary", c, {"valid": s1.get("valid"),
                               "file_id": (s1.get("identifiers") or {}).get("file_id"),
                               "blocks": (s1.get("counts") or {}).get("blocks"),
                               "quality": (s1.get("quality") or {}).get("quality_status"),
                               "manifest": (s1.get("versions") or {}).get("manifest"),
                               "schema": (s1.get("versions") or {}).get("schema"),
                               "normalizer": (s1.get("versions") or {}).get("normalizer"),
                               "input_sha256": (s1.get("integrity") or {}).get("input_sha256")})

    # ---- 5. portable copy ---------------------------------------------------
    d1c = os.path.join(WORK, "dump1-copy")
    shutil.copytree(d1, d1c)
    c, o, e = run_cli(["validate-dump", d1c, "--json"])
    v1c = json.loads(o) if o.strip() else {}
    record("validate_copied", c, {"valid": v1c.get("valid"),
                                  "errors": v1c.get("errors"),
                                  "warnings": v1c.get("warnings")})

    # ---- 6. tamper (flip one char in blocks.jsonl) ---------------------------
    d1t = os.path.join(WORK, "dump1-tampered")
    shutil.copytree(d1, d1t)
    bp = os.path.join(d1t, "blocks.jsonl")
    raw = open(bp, encoding="utf-8").read()
    # flip one char inside the first record's raw_text value
    i = raw.find('"raw_text"')
    assert i != -1
    j = raw.find(":", i)
    k = raw.find('"', j + 1)          # opening quote of value
    flip_at = k + 1 + 10               # 10 chars inside the string value
    flipped = raw[:flip_at] + ("X" if raw[flip_at] != "X" else "x") + raw[flip_at + 1:]
    assert flipped != raw
    open(bp, "w", encoding="utf-8").write(flipped)
    c, o, e = run_cli(["validate-dump", d1t, "--json"])
    v1t = json.loads(o) if o.strip() else {}
    record("validate_tampered", c, {"valid": v1t.get("valid"),
                                    "error_count": len(v1t.get("errors") or []),
                                    "first_error": (v1t.get("errors") or [""])[:1]})

    # ---- 7. m-1 compatibility ------------------------------------------------
    wf1m1 = os.path.join(WORK, "run1-m1")
    shutil.copytree(wf1, wf1m1)
    mp = os.path.join(wf1m1, "manifest.json")
    m = load_json(mp)
    m["manifest_version"] = "m-1"
    m["versions"].pop("normalizer_policy", None)
    m["versions"].pop("factory", None)
    m.pop("blocks_hash", None)
    with open(mp, "w", encoding="utf-8") as f:
        json.dump(m, f, ensure_ascii=False, indent=2)
    dm1d = os.path.join(WORK, "dump-m1")
    c, o, e = run_cli(["make-dump", wf1m1, "--dump-dir", dm1d, "--json"])
    record("make_dump_m1", c, {"stderr_tail": e.strip()[-200:]})
    c, o, e = run_cli(["validate-dump", dm1d, "--json"])
    vm1 = json.loads(o) if o.strip() else {}
    has_pol_warn = any("normalizer_policy not recorded" in w
                       for w in (vm1.get("warnings") or []))
    dmm1 = load_json(os.path.join(dm1d, "dump-manifest.json"))
    record("validate_m1", c, {"valid": vm1.get("valid"),
                              "policy_warn": has_pol_warn,
                              "policy_null": dmm1["versions"]["normalizer_policy"] is None,
                              "blocks_hash_null": dmm1["integrity"]["blocks_hash"] is None})

    # ---- 8. repeatability run1 vs run2 ---------------------------------------
    cmp_ = {}
    m1 = load_json(os.path.join(wf1, "manifest.json"))
    m2 = load_json(os.path.join(wf2, "manifest.json"))
    # volatile keys mirror test_dump._VOLATILE (timestamps) + path keys
    VOL = ("started_at", "finished_at", "duration_ms", "created_at",
           "generated_at")

    def _strip(o):
        if isinstance(o, dict):
            return {k: _strip(v) for k, v in o.items()
                    if k not in VOL and k != "path"}
        if isinstance(o, list):
            return [_strip(v) for v in o]
        return o

    for key in ("file", "work_id", "edition_id", "volume_id", "versions",
                "blocks_hash", "counts"):
        cmp_[key] = _strip(m1.get(key)) == _strip(m2.get(key))
    # byte-stable files (contract S5)
    for name in ("blocks.jsonl", "quality-report.json"):
        cmp_["sha_" + name] = sha256_file(os.path.join(wf1, name)) == \
            sha256_file(os.path.join(wf2, name))
    # structurally-stable: manifest (also drop self-refs to volatile outputs,
    # mirroring test_dump._strip_wf_manifest) and document.json
    def _strip_wf_manifest(mf):
        mf = _strip(mf)
        outs = mf.get("outputs")
        if isinstance(outs, dict):
            for k in ("document", "report_md"):
                if isinstance(outs.get(k), dict):
                    outs[k].pop("sha256", None)
        return mf

    cmp_["struct_manifest.json"] = _strip_wf_manifest(
        load_json(os.path.join(wf1, "manifest.json"))) == _strip_wf_manifest(
        load_json(os.path.join(wf2, "manifest.json")))
    cmp_["struct_document.json"] = _strip(
        load_json(os.path.join(wf1, "document.json"))) == _strip(
        load_json(os.path.join(wf2, "document.json")))
    cmp_["input_sha256"] = (m1["file"]["sha256"] == m2["file"]["sha256"] ==
                            sha256_file(DOCX))
    results["repeatability"] = cmp_
    results["repeatability"]["all_match"] = all(cmp_.values())

    # dump manifest: contract identity
    policy = dm1["versions"].get("normalizer_policy") or {}
    results["dump_contract"] = {
        "dump_contract_version": dm1["dump_contract_version"],
        "file_id": dm1["identifiers"]["file_id"],
        "input_sha256": dm1["integrity"]["input_sha256"],
        "blocks_hash": dm1["integrity"]["blocks_hash"],
        "sha256_source": dm1["source"]["input_file"]["sha256_source"],
        "policy_version": policy.get("version"),
        "policy_keys": sorted(policy.keys()),
        "policy_rules": policy.get("rules"),
        "files": [{"name": f["name"], "sha256_16": f["sha256"][:16],
                   "format": f["format"], "size": f["size_bytes"]}
                  for f in dm1["files"]],
        "counts": dm1["counts"],
        "quality": dm1["quality"],
    }

    with open(os.path.join(WORK, "acceptance_results.json"), "w",
              encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print("DONE -> " + os.path.join(WORK, "acceptance_results.json"))

    # ---- expectations (acceptance criteria) ---------------------------------
    exp = {
        "wf_run1": 0, "wf_run2": 0,
        "make_dump": 0,
        "validate_dump1": 0,
        "dump_summary": 0,
        "validate_copied": 0,
        "validate_tampered": 1,   # tamper MUST be detected
        "make_dump_m1": 0,
        "validate_m1": 0,
    }
    ok = True
    for name, want in exp.items():
        got = results["steps"][name]["exit_code"]
        if got != want:
            ok = False
            print("ACCEPTANCE FAIL: %s exit=%s (want %s)" % (name, got, want))
    if not results["steps"]["validate_dump1"].get("valid"):
        ok = False
        print("ACCEPTANCE FAIL: dump1 not valid")
    if not results["steps"]["validate_copied"].get("valid"):
        ok = False
        print("ACCEPTANCE FAIL: copied dump not valid")
    if results["steps"]["validate_tampered"].get("valid") is not False:
        ok = False
        print("ACCEPTANCE FAIL: tampered dump reported valid")
    if not results["steps"]["validate_m1"].get("policy_warn"):
        ok = False
        print("ACCEPTANCE FAIL: m-1 policy warning missing")
    if not results["repeatability"]["all_match"]:
        ok = False
        print("ACCEPTANCE FAIL: repeatability mismatch: "
              + str({k: v for k, v in results["repeatability"].items() if v is False}))
    if not results["file_ids"]["match"]:
        ok = False
        print("ACCEPTANCE FAIL: file_id differs between runs")
    print("ACCEPTANCE " + ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

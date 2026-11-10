#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PCM-20.8 — LOCAL end-to-end run of the Word Studio pipeline on a
representative «تفسیر المیزان»-style volume.

WHY THIS FILE EXISTS
--------------------
The user built «تفسیر المیزان» in Word Studio on the live server and it is
stuck at some stage, but the live state is currently unreachable (no
credential/data has reached us). So we REPRODUCE the exact same pipeline
locally on a representative Mizan-like volume (large, Persian + heavy Arabic
quotations, headings, a table) and instrument EVERY stage to find where it
gets slow, stuck, or lands in `needs_review`.

It exercises the SAME code paths the Studio UI drives:
  1) DocumentProcessingService.process()  (intake → validate → parse →
     structure → metadata → normalize → quality → export) with an on_stage
     callback that timestamps each COMPLETED stage;
  2) the real Flask API flow (login → create collection → upload DOCX →
     plan batch → process batch → poll job/queue), using pct_test_support's
     temp DB so the production DB is never touched.

STRICTLY LOCAL / READ-ONLY-TO-PRODUCTION:
  - uses pct_test_support (temp PCT_DB, temp password) — never thesaurus.db;
  - all artifacts go to a temp dir;
  - no network, no deploy, no mutation of any committed file.

Usage:
    .venv\\Scripts\\python.exe deploy\\pcm208_mizan_local_e2e.py
    .venv\\Scripts\\python.exe deploy\\pcm208_mizan_local_e2e.py --paragraphs 20000
"""
from __future__ import annotations

import os
import sys
import time
import tempfile
import shutil
import hashlib
import io
import json

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
BACKEND = os.path.join(ROOT, "backend")
sys.path.insert(0, BACKEND)


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# A representative Mizan-style tafsir volume: long Persian exposition + heavy
# Arabic Quranic/ḥadīth quotations, chapter headings, and a table. The mix and
# volume mimic the real corpus so the hot paths (Arabic→Persian normalise,
# per-paragraph loss counting, full-text persian_ratio, semantic guard) are
# actually exercised at scale.
# ---------------------------------------------------------------------------
AR_VERSES = [
    "إِنَّا أَعْطَيْنَاكَ الْكَوْثَرَ",
    "فَصَلِّ لِرَبِّكَ وَانْحَرْ",
    "إِنَّ مَعَ الْعُسْرِ يُسْرًا",
    "فَإِنَّ مَعَ الْعُسْرِ يُسْرًا",
    "الْحَمْدُ لِلَّهِ رَبِّ الْعَالَمِينَ",
    "الرَّحْمَٰنِ الرَّحِيمِ",
    "صَاحِبِ يَوْمِ الدِّينِ",
]
FA_SENT = [
    "از آنجا که تفسیر المیزان بر مبانی قرآن با قرآن تأکید دارد، آیات را در کنار هم می‌گذارد.",
    "این آیه در رابطه با آیه پیشین، نکته‌ای ظریف در باب تفسیر اجمالی بیان می‌کند.",
    "تأکید بر معنا، نه صرف واژه، از ویژگی‌های روش تفسیری این اثر است.",
    "در اینجا مؤلف، دلالت برهانی آیه را با آیه دیگر ترکیب می‌کند.",
    "تفصیل موضوع نیازمند بررسی قرابت معنایی آیات در سوره است.",
    "نیم‌فاصله‌ها و علائم در متن اصلی رعایت شده و باید حفظ شوند.",
]
AR_NOTE = [
    "قوله تعالی",
    "و فی الحادیث المأثورة",
    "والمتبادر من الآیة",
]


def build_mizan_volume(path, n_paragraphs, seed=7):
    """Write a synthetic-but-representative Mizan tafsir DOCX."""
    from docx import Document

    doc = Document()
    # front matter (metadata extract-only looks at first 10 blocks)
    doc.add_paragraph("عنوان: تفسیر المیزان")
    doc.add_paragraph("نویسنده: سید روح‌الله خمینی")
    doc.add_paragraph("جلد: یک")
    doc.add_paragraph("ناشر: انتشارات نمونه")

    rng = seed
    for i in range(n_paragraphs):
        rng = (rng * 1103515245 + 12345) & 0x7FFFFFFF
        roll = rng % 10
        if i % 400 == 0:
            doc.add_paragraph(f"فصل {i // 400 + 1}", style="Heading 1")
        elif roll < 6:  # Persian exposition
            base = FA_SENT[rng % len(FA_SENT)]
            doc.add_paragraph(
                base + " " + FA_SENT[(rng // 7) % len(FA_SENT)]
                + " (پی‌نوشت: " + AR_NOTE[rng % len(AR_NOTE)] + ")")
        elif roll < 9:  # heavy Arabic quotation
            doc.add_paragraph(
                AR_VERSES[rng % len(AR_VERSES)] + " " +
                AR_VERSES[(rng // 5) % len(AR_VERSES)])
        else:  # mixed line with edge-case whitespace/digits
            doc.add_paragraph(
                "عدد ۱۴۰۵ و 2026 و\tتب و   فاصلهٔ   اضافی " +
                AR_VERSES[rng % len(AR_VERSES)])

    # one table (quality checks table_blocks; parser must keep it)
    t = doc.add_table(rows=2, cols=3)
    t.rows[0].cells[0].text = "آیه"
    t.rows[0].cells[1].text = "تفسیر"
    t.rows[0].cells[2].text = "موضوع"
    t.rows[1].cells[0].text = "1"
    t.rows[1].cells[1].text = "یاسین"
    t.rows[1].cells[2].text = "معجزه"
    doc.save(path)
    return path


# ---------------------------------------------------------------------------
# (A) Direct factory run with per-stage timing
# ---------------------------------------------------------------------------
def time_factory(volume, out_root):
    from factory.service import DocumentProcessingService

    print("\n" + "=" * 66)
    print("A) DIRECT FACTORY RUN — per-stage timing")
    print("=" * 66)
    stages = {}
    t_last = time.time()
    mark = time.time()

    def on_stage(name):
        nonlocal t_last
        now = time.time()
        stages[name] = (now - t_last) * 1000
        t_last = now
        print(f"  stage {name:<10} {stages[name]:>10.0f} ms  "
              f"(cum { (now - mark) * 1000:,.0f} ms)")

    svc = DocumentProcessingService(out_root)
    doc = svc.process(volume, on_stage=on_stage)
    total = (time.time() - mark) * 1000

    print(f"\n  blocks={len(doc.blocks)}  chars={doc.total_chars:,}")
    print(f"  quality: status={doc.quality.status} score={doc.quality.score}")
    print(f"  work_id={doc.work_id} edition_id={doc.edition_id} "
          f"volume_id={doc.volume_id}")
    print(f"  TOTAL {total:,.0f} ms")

    # hot-spot analysis
    order = ["intake", "validate", "parse", "structure", "metadata",
             "normalize", "quality", "export"]
    present = [s for s in order if s in stages]
    slow = max(present, key=lambda s: stages[s]) if present else None
    print(f"\n  HOTSPOT: {slow} = {stages.get(slow, 0):,.0f} ms")
    return doc, stages


# ---------------------------------------------------------------------------
# (B) Real Flask API flow (the exact Studio path)
# ---------------------------------------------------------------------------
def run_api_flow(volume, data_dir):
    print("\n" + "=" * 66)
    print("B) REAL API FLOW — Studio path via test_client (temp DB)")
    print("=" * 66)
    import pct_test_support  # noqa: F401  (sets temp PCT_DB + password first)
    import server

    pct_test_support.reset_db()  # fresh temp DB + seed auth hash
    client = server.app.test_client()

    # login
    r = client.post("/api/auth/login", json={"password": "test-secret-123"})
    print("  login:", r.status_code)
    assert r.status_code == 200, r.get_data(as_text=True)

    # create collection
    r = client.post("/api/knowledge/collections",
                    json={"name": "تفسیر المیزان (آزمون محلی)",
                          "slug": "mizan-local"})
    print("  create collection:", r.status_code)
    assert r.status_code == 201, r.get_data(as_text=True)
    coll = r.get_json()["collection"]
    cid = coll["collection_id"]
    coll_pk = coll["id"]

    # upload the volume
    with open(volume, "rb") as f:
        data = {"file": (io.BytesIO(f.read()), "mizan-j1.docx")}
    r = client.post(f"/api/knowledge/collections/{coll_pk}/documents",
                    data=data, content_type="multipart/form-data")
    print("  upload document:", r.status_code)
    assert r.status_code == 201, r.get_data(as_text=True)
    docrow = r.get_json()["document"]

    # plan a batch
    r = client.post("/api/knowledge/import/batches", json={
        "collection_id": cid,
        "folder_name": "mizan local",
        "files": [{"name": "mizan-j1.docx",
                   "size": os.path.getsize(volume),
                   "sha256": sha256_file(volume)}],
    })
    print("  plan batch:", r.status_code)
    assert r.status_code == 201, r.get_data(as_text=True)
    bid = r.get_json()["batch"]["batch_id"]

    # process the batch (starts the daemon worker)
    r = client.post(f"/api/knowledge/import/batches/{bid}/process")
    print("  process batch:", r.status_code)
    assert r.status_code in (200, 202), r.get_data(as_text=True)

    # poll job + queue until terminal
    deadline = time.time() + 300
    last_stage = None
    while time.time() < deadline:
        j = client.get("/api/knowledge/jobs").get_json()
        row = next((x for x in j.get("jobs", []) if x["job_id"]
                    and x.get("batch_id") == bid), None)
        if row:
            if (row.get("stage") or row.get("status")) != last_stage:
                print(f"    job {row.get('status'):<11} "
                      f"stage={row.get('stage')!r} "
                      f"progress={row.get('progress')}/{row.get('total')} "
                      f"err={row.get('error')!r}")
                last_stage = (row.get("stage"), row.get("status"))
            if row["status"] in ("succeeded", "failed", "interrupted"):
                break
        time.sleep(0.5)
    else:
        print("    !! job did not reach terminal state within 300s")

    # final doc + queue state
    d = client.get(f"/api/knowledge/collections/{coll_pk}/documents").get_json()
    for doc in d.get("documents", []):
        print("  FINAL doc:", json.dumps({
            "status": doc.get("status"), "quality": doc.get("quality_status"),
            "score": doc.get("quality_score"), "blocks": doc.get("blocks_count"),
            "error": (doc.get("error") or "")[:200]}, ensure_ascii=False))
    q = client.get(f"/api/knowledge/queue/summary?collection_id={cid}").get_json()
    if "counters" in q:
        print("  queue counters:", json.dumps(q["counters"], ensure_ascii=False))
    b = client.get(f"/api/knowledge/import/batches?collection_id={cid}").get_json()
    for bb in b.get("batches", []):
        print("  batch:", json.dumps({
            "status": bb.get("status"), "processed": bb.get("processed_count"),
            "failed": bb.get("failed_count"), "paused": bb.get("paused")},
            ensure_ascii=False))


def main():
    args = sys.argv[1:]
    n_paras = 6000
    if "--paragraphs" in args:
        n_paras = int(args[args.index("--paragraphs") + 1])

    work = tempfile.mkdtemp(prefix="pcm208-mizan-local-")
    out_root = os.path.join(work, "wf-out")
    os.makedirs(out_root, exist_ok=True)
    data_dir = os.path.join(work, "data")
    os.makedirs(data_dir, exist_ok=True)
    os.environ["PCT_KNOWLEDGE_DATA_DIR"] = data_dir

    volume = os.path.join(work, "mizan-j1.docx")
    print("Building representative Mizan volume (%d paragraphs) ..." % n_paras)
    t0 = time.time()
    build_mizan_volume(volume, n_paras)
    size_mb = os.path.getsize(volume) / (1 << 20)
    print(f"  volume: {volume}  ({size_mb:.1f} MB)  built in {time.time()-t0:.1f}s")

    try:
        doc, stages = time_factory(volume, out_root)
        run_api_flow(volume, data_dir)
    finally:
        shutil.rmtree(work, ignore_errors=True)

    print("\n" + "=" * 66)
    print("LOCAL E2E COMPLETE")
    print("=" * 66)


if __name__ == "__main__":
    main()

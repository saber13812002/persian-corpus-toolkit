# -*- coding: utf-8 -*-
"""Tasnim Web V1 — e2e screenshot capture (PCM-20.6.4, scope C).

Captures 8 representative views of the running SSR frontend as PNGs
into the gitignored ``tasnim/e2e/screenshots/`` directory.

Capability used: a headless Chromium-family browser (Microsoft Edge
on Windows, Google Chrome / Chromium as fallback) in its built-in
``--headless --screenshot`` mode. No third-party Python dependency.

Usage (worktree root, server already running on :5071):
    python -X utf8 tasnim/e2e/screenshot.py [--base http://127.0.0.1:5071]
                                             [--out tasnim/e2e/screenshots]

Exit codes: 0 = all captures OK, 1 = one or more captures failed,
2 = no usable browser found (BLOCKED for now).
"""
import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request

DEFAULT_BASE = "http://127.0.0.1:5071"

# worktree root: tasnim/e2e/screenshot.py -> two levels up from tasnim/
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BROWSER_CANDIDATES = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    "/usr/bin/google-chrome",
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
]


def find_browser():
    for cand in BROWSER_CANDIDATES:
        if os.path.exists(cand):
            return cand
    for name in ("msedge", "google-chrome", "chromium", "chromium-browser",
                 "chrome"):
        p = shutil.which(name)
        if p:
            return p
    return None


# (slug, path, viewport_width, viewport_height)
# Note: the search term is percent-encoded here on purpose; this file
# is kept pure-ASCII so no locale can corrupt the query (PCM-20.6.4).
VIEWS = [
    ("01-home", "/", 1440, 1800),
    ("02-volumes", "/volumes", 1440, 1800),
    ("03-volume-detail",
     "/volumes/tasnim_hamta__hamta-2026__vol047", 1440, 3000),
    ("04-reader", "/page/2?dup_rank=1", 1440, 3000),
    ("05-gap-recovery", "/page/5000", 1440, 1600),
    ("06-topics", "/topics", 1440, 2400),
    ("07-search", "/search?q=%D8%A8%D8%B3%D9%85%D9%87", 1440, 2000),
    ("08-about", "/about", 1440, 2600),
]


def wait_for_server(base, timeout=30.0):
    """Poll the API health endpoint until it answers 200."""
    url = base.rstrip("/") + "/api/v1/tasnim/health"
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=3) as r:
                if r.status == 200:
                    return True
                last = "HTTP %d" % r.status
        except Exception as e:  # noqa: BLE001
            last = repr(e)
        time.sleep(1.0)
    print("server not healthy at %s (last: %s)" % (url, last))
    return False


def shoot(browser, url, out, width, height, profile_dir, timeout=120):
    cmd = [
        browser,
        "--headless=new",
        "--disable-gpu",
        "--no-first-run",
        "--no-default-browser-check",
        "--hide-scrollbars",
        "--force-device-scale-factor=1",
        "--user-data-dir=" + profile_dir,
        "--window-size=%d,%d" % (width, height),
        "--virtual-time-budget=8000",
        "--screenshot=" + out,
        url,
    ]
    return subprocess.run(cmd, capture_output=True, text=True,
                          timeout=timeout)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--base", default=DEFAULT_BASE)
    ap.add_argument("--out",
                    default=os.path.join(ROOT, "tasnim", "e2e",
                                         "screenshots"))
    args = ap.parse_args(argv)

    browser = find_browser()
    if not browser:
        print("BLOCKED: no Chromium-family browser found on PATH")
        print("captured: 0 / %d" % len(VIEWS))
        return 2
    print("browser: %s" % browser)

    if not wait_for_server(args.base):
        print("ERROR: server did not become healthy; aborting")
        return 1

    os.makedirs(args.out, exist_ok=True)
    profile_dir = tempfile.mkdtemp(prefix="pct_screenshot_")
    rows = []
    all_ok = True
    try:
        for slug, path, w, h in VIEWS:
            url = args.base.rstrip("/") + path
            out = os.path.join(args.out, slug + ".png")
            try:
                r = shoot(browser, url, out, w, h, profile_dir)
                size = os.path.getsize(out) if os.path.exists(out) else 0
                # a real rendered RTL page is many KB; a blank/failed
                # capture is near zero or tiny
                good = size > 8000
                status = "OK" if good else "BAD(size=%d)" % size
                if r.returncode != 0 and good:
                    status += " rc=%d" % r.returncode
                rows.append((slug, path, status, size))
                all_ok = all_ok and good
            except Exception as e:  # noqa: BLE001
                rows.append((slug, path, "ERROR %r" % e, 0))
                all_ok = False
    finally:
        shutil.rmtree(profile_dir, ignore_errors=True)

    print("\n%-18s %-55s %-14s %8s" % ("view", "path", "status", "bytes"))
    for slug, path, status, size in rows:
        print("%-18s %-55s %-14s %8d" % (slug, path, status, size))
    ok_n = sum(1 for r in rows if r[2] == "OK")
    print("\ncaptured: %d / %d -> %s" % (ok_n, len(VIEWS), args.out))
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())

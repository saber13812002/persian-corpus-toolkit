# -*- coding: utf-8 -*-
"""PCM-20.6 D4 — پایلوت Hidden Context (خلاصه‌ی پنهان ۳خطی) روی مدل داخلی.

هدف (سند مأموریت §4.5): برای ~۳۰ تا ۵۰ عنوانِ دارای «صفحه‌ی بعدی»، یک
خلاصه‌ی پنهانِ ۳خطی فارسی با مدل داخلی Qwen3.8-27B-FP8 (OpenAI-compatible
روی 172.20.1.53:8000 — فقط استدلال خواندنی؛ سرویس جدیدی ساخته نمی‌شود)
تولید شود و کیفیت (پاسداشت ۳ خط، فارسی‌بودن، وفاداری به متن) نمره بخورد.

خروجی: یک فایل JSON (در data/، خارج از git) شامل:
  * پاسخ خام /v1/models (نام+نسخه‌ی مدل، دقیقاً همان‌طور که API داده)
  * برای هر آیتم: prompt کامل (system+user)، خروجی خام، SHA-256، زمان‌بندی
  * نمره‌ی خودکار هر آیتم + جمع‌بندی GO/STOP

قواعد:
  * فقط شبکه به سمت s53 (inference) — هیچ چیز دیگری تغییر نمی‌کند.
  * انتخاب آیتم‌ها قطعی است (ترتیب جلد/صفحه + سقف به‌ازای هر جلد).
  * در صورت BLOCKED (دسترس‌ناپذیری) نتیجه با شواهد ثبت می‌شود و اسکریپت
    خروجی می‌دهد (exit 2) — مطابق قاعده‌ی مأموریت: ثبت و ادامه.

استفاده:
  python -X utf8 deploy/pcm206_hc_pilot.py \
      --build data/tasnim/pcm20_5/corpus/builds/v0003 \
      --out data/tasnim/pcm20_6/pilot/hc-pilot.json
  --dry-run: بدون شبکه (فقط انتخاب + promptها) برای تست.
"""
import argparse
import hashlib
import io
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

LIVE_BASE_DEFAULT = "http://172.20.1.53:8000/v1"
N_DEFAULT = 40
PER_VOLUME_DEFAULT = 8
TIMEOUT_DEFAULT = 120.0
TRIES_DEFAULT = 3
MAX_TOKENS = 300
TEMPERATURE = 0.3
PILOT_ID = "hc-pilot-1"
MISSION = "PCM-20.6 SUBTASK 02 / D4"
CONTRACT = "hc-pilot-1"

# ---- نمره‌دهی (تعریف مکتوب، قابل‌تکثیر) ------------------------------------
# lines_ok     : خروجی دقیقاً ۳ خط
# near_lines   : ۲ تا ۴ خط (نزدیک هدف)
# persian_ok   : نسبت کاراکترهای فارسی/عربی (بجای الفبا) >= 0.70
# overlap_ok   : نسبت کلمه‌های بی‌تکرارِ خروجی (len>=3) که در متن صفحه‌ی
#                بعدی (با ی/ک نرمال‌شده) پیدا می‌شوند >= 0.40
# item verdict : PASS = lines_ok and persian_ok and overlap_ok
#                NEAR = near_lines and persian_ok and overlap_ok
#                FAIL = بقیه
# GO           : n_evaluated >= 10 and (PASS+NEAR)/n_evaluated >= 0.80
# STOP/REPORT  : غیر از آن


def _norm_fa(text):
    """نرمال‌سازی سبک برای مقایسه‌ی کلمات: ی->ي ، ک->ك ، فاصله‌های چسبیده."""
    t = (text or "").replace("ی", "ي").replace("ک", "K")
    return re.sub(r"\s+", " ", t).strip()


def _words(text, min_len=3):
    t = _norm_fa(text)
    out = set()
    for w in t.split(" "):
        w = w.strip(
            "\u060c.؛:!?()[]{}\u00ab\u00bb\u201c\u201d\u2018\u2019\u0640-"
            "\u2014\u2026")
        if len(w) >= min_len and any(c.isalpha() for c in w):
            out.add(w)
    return out


def score_item(output, next_text):
    """نمره‌ی خودکار یک خروجی (بنا بر تعریف مکتوب در بالای ماژول)."""
    lines = [l for l in (output or "").splitlines() if l.strip()]
    n_lines = len(lines)
    chars = [c for c in (output or "") if c.isalpha()]
    fa_chars = [c for c in chars
                if "\u0600" <= c <= "\u06FF" or c in "ی"]
    persian_ratio = (len(fa_chars) / len(chars)) if chars else 0.0
    out_words = _words(output)
    next_words = _words(next_text)
    hits = sum(1 for w in out_words if w in next_words)
    overlap = (hits / len(out_words)) if out_words else 0.0
    lines_ok = (n_lines == 3)
    near_lines = (2 <= n_lines <= 4)
    persian_ok = persian_ratio >= 0.70
    overlap_ok = overlap >= 0.40
    if lines_ok and persian_ok and overlap_ok:
        verdict = "PASS"
    elif near_lines and persian_ok and overlap_ok:
        verdict = "NEAR"
    else:
        verdict = "FAIL"
    return {
        "n_lines": n_lines,
        "lines_ok": lines_ok,
        "near_lines": near_lines,
        "persian_ratio": round(persian_ratio, 4),
        "persian_ok": persian_ok,
        "word_overlap": round(overlap, 4),
        "overlap_ok": overlap_ok,
        "verdict": verdict,
    }


# ---- بارگذاری داده‌ی ساخت‌شده (v0003 واقعی) ------------------------------
def load_pages(build_dir):
    path = os.path.join(build_dir, "pages.jsonl")
    out = {}
    with io.open(path, "r", encoding="utf-8") as f:
        for ln in f:
            ln = ln.strip()
            if not ln:
                continue
            r = json.loads(ln)
            out[r["page_id"]] = r.get("text") or ""
    return out


def load_headings(build_dir):
    path = os.path.join(build_dir, "heading-records.jsonl")
    out = []
    with io.open(path, "r", encoding="utf-8") as f:
        for ln in f:
            ln = ln.strip()
            if ln:
                out.append(json.loads(ln))
    return out


def select(headings, n=40, per_volume=8):
    """انتخاب قطعی: جلد به جلد (ترتیب شماره)، داخل هر جلد به ترتیب
    item_index؛ حداکثر per_volume از هر جلد تا رسیدن به n."""
    cands = [h for h in headings if h.get("next_page_id")]
    cands.sort(key=lambda h: (h.get("volume_no") is None,
                              h.get("volume_no") or 0,
                              h.get("item_index") or 0,
                              h.get("page_id") or ""))
    by_vol = {}
    for h in cands:
        by_vol.setdefault(h.get("volume_no"), []).append(h)
    picked = []
    for v in sorted(by_vol, key=lambda x: (x is None, x or 0)):
        picked.extend(by_vol[v][:per_volume])
    return picked[:n]


# ---- prompt -----------------------------------------------------------------
SYSTEM_PROMPT = (
    "شما دستیارِ داخلیِ یک پایگاه‌داده‌ی کتابخانه‌ای هستید که «بافت پنهان» "
    "(hidden context) برای ناوبری تولید می‌کند. این بافت هرگز به‌صورت "
    "عمومی نمایش داده نمی‌شود. شما فقط از اطلاعاتِ موجود در متنِ داده‌شده "
    "استفاده می‌کنید و هیچ چیز را ابداع نمی‌کنید (نه نام، نه عدد، نه "
    "ادعای جدید).")


def build_user_prompt(heading_text, next_text, heading_page, next_page):
    return (
        "عنوان فعلی: %s (صفحه‌ی %s)\n"
        "صفحه‌ی بعدی (به‌طور کامل یا تا حد قابل‌خواندن) را می‌بینید. "
        "یک بافت پنهانِ دقیقاً ۳ خطی بنویسید:\n"
        "خط ۱: صفحه‌ی بعدی درباره‌ی چیست (موضوع و موضوعات فرعی)؛\n"
        "خط ۲: نکته‌ی محوریِ صفحه‌ی بعدی که برای خواننده‌ی بعد لازم است؛\n"
        "خط ۳: ارتباط کوتاهِ آن با عنوان فعلی.\n"
        "قواعد خروجی: فقط ۳ خط فارسی؛ بدون شماره‌گذاری؛ بدون عنوان "
        "اضافی؛ بدون ابداع؛ متن صفحه‌ی بعدی:\n\n%s"
        % (heading_text, heading_page, next_text))


# ---- API (فقط استدلال، خواندنی) ---------------------------------------------
def _post_json(url, payload, timeout):
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _get_json(url, timeout):
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def fetch_models(base, timeout):
    """پاسخ خام /models — نام و نسخه‌ی مدل دقیقاً از API."""
    try:
        raw = _get_json(base.rstrip("/") + "/models", timeout)
        return {"status": "OK", "raw": raw}
    except (urllib.error.URLError, OSError, ValueError) as e:
        return {"status": "BLOCKED", "error": str(e)}


def chat(base, model, messages, timeout, tries):
    """یک مکالمه‌ی chat/completions؛ برگشت (text, meta) یا خطا.

    یادداشت: Qwen3.8-27B-FP8 مدل reasoning است؛ برای این وظیفه (خلاصه‌ی
    ۳خطی، بدون استدلال) thinking خاموش می‌شود تا کل budget روی content
    بیفتد (پروبتشده: enable_thinking=false → reasoning_tokens=0 و
    خروجی فارسی ۳خطی).
    """
    url = base.rstrip("/") + "/chat/completions"
    payload = {"model": model, "messages": messages,
               "temperature": TEMPERATURE, "max_tokens": MAX_TOKENS,
               "chat_template_kwargs": {"enable_thinking": False}}
    last_err = None
    for attempt in range(1, tries + 1):
        t0 = time.time()
        try:
            data = _post_json(url, payload, timeout)
            dt = time.time() - t0
            msg = (data.get("choices") or [{}])[0].get("message") or {}
            text = msg.get("content") or ""
            meta = {
                "attempt": attempt,
                "latency_ms": int(dt * 1000),
                "model_response": data.get("model"),
                "usage": data.get("usage"),
            }
            return text, meta
        except (urllib.error.URLError, OSError, ValueError, KeyError,
                IndexError) as e:
            last_err = str(e)
            if attempt < tries:
                time.sleep(2.0)
    return None, {"attempt": tries, "error": last_err}


# ---- گزارش ------------------------------------------------------------------
def summarize(items, dry_run=False):
    ev = [i for i in items if i.get("output") is not None]
    skipped = sum(1 for i in items if i.get("status") == "skipped")
    blocked = sum(1 for i in items if i.get("status") == "blocked")
    c = {"PASS": 0, "NEAR": 0, "FAIL": 0, "BLOCKED": 0, "skipped": 0}
    for i in items:
        st = i.get("status")
        if st == "skipped":
            c["skipped"] += 1
        elif i.get("output") is None and st not in ("dry_run",):
            c["BLOCKED"] += 1
        elif i.get("output") is not None:
            c[i["score"]["verdict"]] += 1
    n_eval = len(ev)
    good = c["PASS"] + c["NEAR"]
    if dry_run:
        decision, reason = "DRY_RUN", "no network; selection + prompts only"
    elif n_eval == 0:
        decision, reason = "BLOCKED", "no evaluated item (site unreachable?)"
    elif n_eval < 10:
        decision, reason = "STOP", "evaluated %d < 10" % n_eval
    elif good / n_eval >= 0.80:
        decision, reason = "GO", "%d/%d good (>=0.80)" % (good, n_eval)
    else:
        decision, reason = "STOP", "good %d/%d < 0.80" % (good, n_eval)
    return {
        "total": len(items),
        "evaluated": n_eval,
        "skipped": skipped,
        "blocked": blocked,
        "counts": c,
        "good": good,
        "good_rate": round(good / n_eval, 4) if n_eval else None,
        "decision": decision,
        "decision_reason": reason,
    }


def build_pilot(build_dir, n, per_volume, base, timeout, tries, dry_run):
    pages = load_pages(build_dir)
    headings = load_headings(build_dir)
    picked = select(headings, n=n, per_volume=per_volume)

    models = None
    model_id = None
    blocked = False
    if not dry_run:
        models = fetch_models(base, timeout)
        if models["status"] == "OK":
            raw = models["raw"]
            entries = raw.get("data") if isinstance(raw, dict) else raw
            if not isinstance(entries, list):
                entries = []
            ids = [m.get("id") for m in entries
                   if isinstance(m, dict) and m.get("id")]
            model_id = (ids[0] if ids else None)
            if not model_id:
                models["status"] = "BLOCKED"
                models["error"] = "no model id in /models"
        else:
            blocked = True

    items = []
    for h in picked:
        npid = h["next_page_id"]
        next_text = pages.get(npid)
        item = {
            "record_id": h.get("record_id"),
            "heading_text": h.get("heading_text"),
            "heading_page_id": h.get("page_id"),
            "next_page_id": npid,
            "volume_no": h.get("volume_no"),
            "source_class": h.get("source_class"),
        }
        if next_text is None:
            item["status"] = "skipped"
            item["reason"] = "next page text missing in pages.jsonl"
            items.append(item)
            continue
        item["next_text_len"] = len(next_text)
        user = build_user_prompt(h.get("heading_text") or "",
                                 next_text, h.get("page_id"), npid)
        item["prompt"] = {"system": SYSTEM_PROMPT, "user": user}
        if dry_run:
            item["status"] = "dry_run"
            items.append(item)
            continue
        if blocked or not model_id:
            item["status"] = "blocked"
            item["reason"] = (models or {}).get("error", "no model")
            items.append(item)
            continue
        text, meta = chat(base, model_id,
                          [{"role": "system", "content": SYSTEM_PROMPT},
                           {"role": "user", "content": user}],
                          timeout, tries)
        if text is None:
            item["status"] = "blocked"
            item["reason"] = meta.get("error")
            items.append(item)
            continue
        item["status"] = "ok"
        item["model"] = meta.get("model_response") or model_id
        item["output"] = text
        item["output_sha256"] = None  # پر می‌شود (نیاز به hashlib)
        item["meta"] = meta
        item["score"] = score_item(text, next_text)
        items.append(item)

    return {
        "mission": MISSION,
        "contract": CONTRACT,
        "pilot_id": PILOT_ID,
        "build_dir": build_dir,
        "selection": {
            "n_requested": n,
            "per_volume": per_volume,
            "picked": len(picked),
            "candidates_with_next_page": sum(
                1 for h in headings if h.get("next_page_id")),
        },
        "models_api": models,
        "model_id": model_id,
        "params": {
            "temperature": TEMPERATURE,
            "max_tokens": MAX_TOKENS,
            "enable_thinking": False,
            "note": ("Qwen3.8-27B-FP8 reasoning model: thinking disabled so "
                     "the token budget reaches content (verified: "
                     "reasoning_tokens=0, 3-line Persian output)"),
        },
        "scoring_policy": {
            "lines_ok": "exactly 3 non-empty lines",
            "near_lines": "2..4 lines",
            "persian_ok": "fa/ara alpha ratio >= 0.70",
            "overlap_ok": "unique words (len>=3) found in next page >= 0.40",
            "PASS": "lines_ok and persian_ok and overlap_ok",
            "NEAR": "near_lines and persian_ok and overlap_ok",
            "GO": "evaluated>=10 and good/evaluated>=0.80",
        },
        "items": items,
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--build",
                    default="data/tasnim/pcm20_5/corpus/builds/v0003")
    ap.add_argument("--out",
                    default="data/tasnim/pcm20_6/pilot/hc-pilot.json")
    ap.add_argument("--n", type=int, default=N_DEFAULT)
    ap.add_argument("--per-volume", type=int, default=PER_VOLUME_DEFAULT)
    ap.add_argument("--base", default=LIVE_BASE_DEFAULT)
    ap.add_argument("--timeout", type=float, default=TIMEOUT_DEFAULT)
    ap.add_argument("--tries", type=int, default=TRIES_DEFAULT)
    ap.add_argument("--dry-run", action="store_true",
                    help="بدون شبکه؛ فقط انتخاب + promptها")
    args = ap.parse_args(argv)

    report = build_pilot(args.build, args.n, args.per_volume,
                         args.base, args.timeout, args.tries,
                         args.dry_run)
    report["dry_run"] = bool(args.dry_run)
    # SHA روی خروجی‌ها (provenance) — بعد از جمع‌بندی
    for it in report["items"]:
        if it.get("output") is not None:
            it["output_sha256"] = hashlib.sha256(
                it["output"].encode("utf-8")).hexdigest()
    report["summary"] = summarize(report["items"], dry_run=args.dry_run)
    report["generated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                           time.gmtime())
    if not args.dry_run:
        d = os.path.dirname(args.out)
        if d:
            os.makedirs(d, exist_ok=True)
        with io.open(args.out, "w", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(report, ensure_ascii=False, indent=1)
                    + "\n")

    s = report["summary"]
    print("=== HC PILOT (PCM-20.6 D4) ===")
    print("model      :", report.get("model_id"))
    print("items      : %d (evaluated %d)" % (s["total"], s["evaluated"]))
    print("counts     :", s["counts"])
    print("good_rate  :", s["good_rate"])
    print("decision   : %s — %s" % (s["decision"], s["decision_reason"]))
    if not args.dry_run:
        print("out        :", args.out)
    if s["decision"] == "BLOCKED" and not args.dry_run:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())

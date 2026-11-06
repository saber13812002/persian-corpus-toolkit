# -*- coding: utf-8 -*-
"""پرو브 s53: Qwen3 thinking — چطور content پر شود؟
A) chat_template_kwargs enable_thinking=false
B) max_tokens بالا (budget برای reasoning + content)
"""
import io
import json
import urllib.request

BASE = "http://172.20.1.53:8000/v1"


def chat(payload, timeout=240):
    req = urllib.request.Request(
        BASE + "/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


USER = ("متن صفحه‌ی بعدی: «در این صفحه مفسر به تفسیر آیه‌ی «وَ جَعَلْنَا "
        "الَّیْلَ وَالنَّهَارَ آیَتَیْنِ» می‌پردازد و شب و روز را نشانه‌ای "
        "از قدرت خدا می‌داند.»\n"
        "یک بافت پنهانِ دقیقاً ۳ خطی فارسی بنویس؛ بدون شماره‌گذاری.")
MSGS = [{"role": "user", "content": USER}]
out = []

for tag, extra in [
    ("A_no_thinking", {"chat_template_kwargs": {"enable_thinking": False}}),
    ("B_big_budget", {"max_tokens": 2048}),
]:
    payload = {"model": "/models/Qwen3.8-27B-FP8", "messages": MSGS,
               "temperature": 0.3, "max_tokens": 300}
    payload.update(extra)
    try:
        data = chat(payload)
        msg = (data.get("choices") or [{}])[0].get("message") or {}
        out.append("=== %s ===" % tag)
        out.append("content: %r" % (msg.get("content") or ""))
        out.append("reasoning: %r" % (
            (msg.get("reasoning_content") or "")[:200]))
        out.append("usage: %s" % json.dumps(data.get("usage")))
    except Exception as e:
        out.append("=== %s === ERROR: %s" % (tag, e))
    out.append("")

with io.open(".tmp_pcm206_d4_llm_probe.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(out))
print("written")

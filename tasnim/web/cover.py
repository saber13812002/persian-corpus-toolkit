# -*- coding: utf-8 -*-
"""Deterministic SVG cover-plate generator (PCM-20.6.4, design system §7.8).

Binding rules:
- 3:4 plate, 600x800, zero raster, zero network (offline).
- Background gradient #F3EFE7 -> #EDE6D9.
- 8-point 1px line star in the inline-end (RTL: left) corner, accent
  #D97706 at 12% opacity.
- Work name in Amiri 700; volume number in Vazirmatn 700 (null ->
  «نامشخص» + an honest unknown-note).
- Edition label + the mandatory disclaimer «نمایهٔ اختصاصی — جلد رسمی نیست».
- Deterministic: only hash(volume_id) seeds the star rotation; no
  timestamps, no randomness. `cover_source` is always "generated-svg"
  in v1 (recorded by the builder via the covers/ directory).
"""
import hashlib
import math
from xml.sax.saxutils import escape

SIZE_W, SIZE_H = 600, 800
GRAD_TOP, GRAD_BOTTOM = "#F3EFE7", "#EDE6D9"
ACCENT = "#D97706"
STAR_OPACITY = "0.12"
TEXT = "#1C1917"
TEXT_MUTED = "#57534E"
TEXT_FAINT = "#78716C"
INK = "#92400E"
BORDER = "#E5DED2"
MANDATORY_LABEL = "نمایهٔ اختصاصی — جلد رسمی نیست"
UNKNOWN_NOTE = "شمارهٔ جلد در پیکره ثبت نشده است"

_PERSIAN = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")


def to_persian_digits(value):
    return str(value).translate(_PERSIAN)


def _star_lines(cx, cy, radius, rotation_deg):
    """Four full lines through the centre at 45° steps = 8-point star."""
    parts = []
    for i in range(4):
        a = math.radians(rotation_deg + i * 45.0)
        dx, dy = math.cos(a) * radius, math.sin(a) * radius
        parts.append(
            f'    <line x1="{cx - dx:.2f}" y1="{cy - dy:.2f}" '
            f'x2="{cx + dx:.2f}" y2="{cy + dy:.2f}"/>')
    return "\n".join(parts)


def generate_cover(volume_id, volume_no, work_name, edition_name):
    """Return the SVG text for one volume cover plate (deterministic)."""
    seed = int(hashlib.sha256(str(volume_id).encode("utf-8")).hexdigest()[:8], 16)
    rotation = (seed % 3600) / 10.0
    vol_label = to_persian_digits(volume_no) if volume_no is not None else "نامشخص"
    title = (f"{work_name} — جلد {vol_label}" if volume_no is not None
             else f"{work_name} — جلد نامشخص")
    unknown = ""
    if volume_no is None:
        unknown = (
            f'  <text x="300" y="500" text-anchor="middle" '
            f'font-family="Vazirmatn, \'Noto Naskh Arabic\', sans-serif" '
            f'font-size="16" fill="{TEXT_MUTED}">{UNKNOWN_NOTE}</text>\n')
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="600" height="800" '
        'viewBox="0 0 600 800" role="img" dir="rtl">\n'
        f"  <title>{escape(title)} (پوشش ساخت‌شدهٔ خواندنی؛ جلد رسمی نیست)</title>\n"
        "  <defs>\n"
        '    <linearGradient id="bg" x1="0" y1="0" x2="0" y2="1">\n'
        f'      <stop offset="0" stop-color="{GRAD_TOP}"/>\n'
        f'      <stop offset="1" stop-color="{GRAD_BOTTOM}"/>\n'
        "    </linearGradient>\n"
        "  </defs>\n"
        f'  <rect width="{SIZE_W}" height="{SIZE_H}" fill="url(#bg)"/>\n'
        f'  <rect x="24" y="24" width="{SIZE_W - 48}" height="{SIZE_H - 48}" '
        f'fill="none" stroke="{BORDER}" stroke-width="1"/>\n'
        f'  <g stroke="{ACCENT}" stroke-width="1" opacity="{STAR_OPACITY}">\n'
        f"{_star_lines(70, 730, 46, rotation)}\n"
        "  </g>\n"
        f'  <text x="300" y="170" text-anchor="middle" '
        f'font-family="Amiri, \'Noto Naskh Arabic\', serif" font-size="46" '
        f'font-weight="700" fill="{TEXT}">{escape(work_name)}</text>\n'
        f'  <text x="300" y="430" text-anchor="middle" '
        f'font-family="Vazirmatn, \'Noto Naskh Arabic\', sans-serif" '
        f'font-size="120" font-weight="700" fill="{INK}">{escape(vol_label)}</text>\n'
        f'  <text x="300" y="520" text-anchor="middle" '
        f'font-family="Vazirmatn, \'Noto Naskh Arabic\', sans-serif" '
        f'font-size="22" fill="{TEXT_MUTED}">{escape(edition_name)}</text>\n'
        f"{unknown}"
        f'  <text x="300" y="756" text-anchor="middle" '
        f'font-family="Vazirmatn, \'Noto Naskh Arabic\', sans-serif" '
        f'font-size="11" fill="{TEXT_FAINT}">{MANDATORY_LABEL}</text>\n'
        "</svg>\n"
    )

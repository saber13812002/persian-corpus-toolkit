# فونت‌های خودبست‌ر (self-hosted OFL fonts) — Tasnim Web V1

All fonts in this directory are licensed under the **SIL Open Font License 1.1**
(see [`OFL.txt`](OFL.txt)). They are served by
`tasnim/web/static/css/tasnim.css` via `@font-face` with `font-display: swap`,
and the Flask app sets `Cache-Control: public, max-age=86400` + correct
`font/ttf` content-type on `/static/fonts/*` (`tasnim/web/api.py`).

## Files

| File | Font | Weight(s) | Format | Upstream source (official) |
|---|---|---|---|---|
| `vazirmatn-regular.ttf` | Vazirmatn | 400 | TTF (static) | `rastikerdar/vazirmatn` → `fonts/ttf/Vazirmatn-Regular.ttf` |
| `vazirmatn-medium.ttf` | Vazirmatn | 500 | TTF (static) | `rastikerdar/vazirmatn` → `fonts/ttf/Vazirmatn-Medium.ttf` |
| `vazirmatn-bold.ttf` | Vazirmatn | 700 | TTF (static) | `rastikerdar/vazirmatn` → `fonts/ttf/Vazirmatn-Bold.ttf` |
| `noto-naskh-arabic.ttf` | Noto Naskh Arabic | 400–700 (variable, `wght`) | TTF (variable) | `google/fonts` → `ofl/notonaskharabic/NotoNaskhArabic[wght].ttf` |
| `OFL.txt` | SIL Open Font License 1.1 | — | text | canonical body from `google/fonts` |

- **UI font:** Vazirmatn (400 / 500 / 700) — body UI, headings, buttons.
- **Reading font:** Noto Naskh Arabic (variable 400–700) — reader page text,
  search snippets. Declared with a single `@font-face { font-weight: 400 700; }`
  range, which browsers map across the variable axis.
- **Amiri** is listed in the design system as *optional* and is **not** bundled
  (no `@font-face` references it); it remains in the footer's license line only
  as a documented deviation.

## Why TTF (not woff2)

Both official repositories ship **TTF only** — no woff2 subset files exist in
the upstream trees (verified: `fonts/woff2/*` in `rastikerdar/vazirmatn` is
404). The mission spec therefore binds to TTF. The CSS declares
`format("truetype")`; `api.py` maps the `.ttf` suffix to `font/ttf`.

## Provenance (exact download commands)

Fetched from the **official GitHub repositories** over HTTPS (no mirrors, no
`fonts.google.com` binary proxy). Run from `tasnim/web/static/fonts/`:

```bash
# --- Vazirmatn (OFL, © 2015 The Vazirmatn Project Authors) ---
curl -fL -o vazirmatn-regular.ttf \
  https://raw.githubusercontent.com/rastikerdar/vazirmatn/master/fonts/ttf/Vazirmatn-Regular.ttf
curl -fL -o vazirmatn-medium.ttf \
  https://raw.githubusercontent.com/rastikerdar/vazirmatn/master/fonts/ttf/Vazirmatn-Medium.ttf
curl -fL -o vazirmatn-bold.ttf \
  https://raw.githubusercontent.com/rastikerdar/vazirmatn/master/fonts/ttf/Vazirmatn-Bold.ttf

# --- Noto Naskh Arabic (OFL, © 2022 The Noto Project Authors) ---
curl -fL -o noto-naskh-arabic.ttf \
  "https://raw.githubusercontent.com/google/fonts/main/ofl/notonaskharabic/NotoNaskhArabic%5Bwght%5D.ttf"

# --- OFL 1.1 license text (canonical body) ---
curl -fL -o OFL.txt \
  https://raw.githubusercontent.com/google/fonts/main/ofl/notonaskharabic/OFL.txt
```

Equivalent PowerShell (Windows):

```powershell
curl.exe -fL -o vazirmatn-regular.ttf "https://raw.githubusercontent.com/rastikerdar/vazirmatn/master/fonts/ttf/Vazirmatn-Regular.ttf"
curl.exe -fL -o vazirmatn-medium.ttf  "https://raw.githubusercontent.com/rastikerdar/vazirmatn/master/fonts/ttf/Vazirmatn-Medium.ttf"
curl.exe -fL -o vazirmatn-bold.ttf    "https://raw.githubusercontent.com/rastikerdar/vazirmatn/master/fonts/ttf/Vazirmatn-Bold.ttf"
curl.exe -fL -o noto-naskh-arabic.ttf "https://raw.githubusercontent.com/google/fonts/main/ofl/notonaskharabic/NotoNaskhArabic%5Bwght%5D.ttf"
curl.exe -fL -o OFL.txt               "https://raw.githubusercontent.com/google/fonts/main/ofl/notonaskharabic/OFL.txt"
```

Copyright headers of the two OFL-licensed families:

- Vazirmatn — `Copyright 2015 The Vazirmatn Project Authors
  (https://github.com/rastikerdar/vazirmatn)` (see the repository's own
  `OFL.txt` at `https://raw.githubusercontent.com/rastikerdar/vazirmatn/master/OFL.txt`).
- Noto Naskh Arabic — `Copyright 2022 The Noto Project Authors
  (https://github.com/notofonts/arabic)` (the header of the bundled `OFL.txt`).

Both are the same OFL 1.1 license body; the bundled `OFL.txt` is the canonical
text as distributed by the google/fonts repository.

## Integrity (SHA-256, verified at fetch time 2026-11-07)

Recompute with `certutil -hashfile <file> SHA256` (Windows) or
`sha256sum <file>` (POSIX) and compare:

```text
b69fd4c680b8f3f225feabcc655a2c585d97627b8f5f5c0f9985e894069f3a56  vazirmatn-regular.ttf    (122,752 bytes)
b986623e4ddef10755e04be39f8ea7bcb1dc08bfe8dd0aa6af395736f256ad4a  vazirmatn-medium.ttf     (122,656 bytes)
f635fdbea28f265de395ba83b4b1570dcf2f58d13c65469e61903b1c2d2ae723  vazirmatn-bold.ttf       (123,036 bytes)
67b5a525a661b607971fbd3f96a81b89d3a768e74534fca84f18ac97e6fab72f  noto-naskh-arabic.ttf    (307,592 bytes)
```

All four files passed a TTF/OTF magic-byte check (`00 01 00 00` true-type
collection header) at fetch time.

## Notes

- No subsetting is performed; the full glyph sets ship as-is from upstream
  (Vazirmatn covers Arabic + Persian; Noto Naskh Arabic covers the Arabic
  script, which renders the Persian letters used in the corpus).
- The reader's A+/A− control (`tasnim/web/static/js/tasnim.js`) adjusts
  `--text-reading` between 16–24 px; it does not swap font files.

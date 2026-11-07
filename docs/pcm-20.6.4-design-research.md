# PCM-20.6.4 — Design Research (ui-ux-pro-max supplemental searches)

Generated: 2026-11-07 (execution half of PCM-20.6.4, Part A2).
Tool: `C:\Users\s.tabatabaei\.agents\skills\ui-ux-pro-max\scripts\search.py` (skill database, stdlib-only).
Each section below is the **verbatim stdout** of one search. Raw capture files: `.tmp_pcm2064_s*.txt` (mission worktree root).
Companion artifact: `design-system/tasnim-web/MASTER.md` (persisted design system, see that file for palette/typography/dials).

---

## "elegant serif editorial reading" (domain: typography)

```
## UI Pro Max Search Results
**Domain:** typography | **Query:** elegant serif editorial reading
**Source:** typography.csv | **Found:** 5 results

### Result 1
- **Font Pairing Name:** Classic Elegant
- **Category:** Serif + Sans
- **Heading Font:** Playfair Display
- **Body Font:** Inter
- **Mood/Style Keywords:** elegant, luxury, sophisticated, timeless, premium, editorial
- **Best For:** Luxury brands, fashion, spa, beauty, editorial, magazines, high-end e-commerce
- **Google Fonts URL:** https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=Playfair+Display:wght@400;500;600;700&display=swap
- **CSS Import:** @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=Playfair+Display:wght@400;500;600;700&display=swap');
- **Tailwind Config:** fontFamily: { serif: ['Playfair Display', 'serif'], sans: ['Inter', 'sans-serif'] }
- **Notes:** High contrast between elegant heading and clean body. Perfect for luxury/premium.

### Result 2
- **Font Pairing Name:** Bold Typography Mobile (Inter Poster)
- **Category:** Sans + Serif (Display) + Mono
- **Heading Font:** Inter
- **Body Font:** Playfair Display
- **Mood/Style Keywords:** bold typography, editorial, poster, near-black, vermillion, luxury, type-as-hero, manifesto, high-contrast
- **Best For:** Creative brand flagships, reading platforms, event apps, flash pages, luxury mobile experiences
- **Google Fonts URL:** https://fonts.googleapis.com/css2?family=Inter:ital,wght@0,400;0,500;0,600;0,700;0,800;1,400&family=JetBrains+Mono:wght@400&family=Playfair+Display:ital@1
- **CSS Import:** @import url('https://fonts.googleapis.com/css2?family=Inter:ital,wght@0,400;0,500;0,600;0,700;0,800;1,400&family=JetBrains+Mono:wght@400&family=Playfair+Display:ital@1&display=swap');
- **Tailwind Config:** fontFamily: { display: ['Inter', 'sans-serif'], quote: ['Playfair Display', 'serif'], mono: ['JetBrains Mono', 'monospace'] }
- **Notes:** Tri-stack: Inter 600–800 for UI and display type (letterSpacing -1.5px heroes, -0.5px subheads). Playfair Display Italic only for pull quotes. JetBrains Mono for labels and stats. Suggested scale: 12px labels, 16px body, 22px subhead, 32px section, 40px H2, 56px H1, 72px hero statement. Use lineHeig...

### Result 3
- **Font Pairing Name:** Minimalist Monochrome Editorial
- **Category:** Serif + Serif + Mono (Triple Stack)
- **Heading Font:** Playfair Display
- **Body Font:** Source Serif 4
- **Mood/Style Keywords:** monochrome, editorial, austere, typographic, pocket manifesto, luxury, high contrast, brutalist mobile
- **Best For:** Luxury fashion mobile apps, editorial publications, digital exhibitions, portfolio apps, high-contrast e-reader aesthetics
- **Google Fonts URL:** https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500&family=Playfair+Display:ital,wght@0,400;0,700;0,900;1,400&family=Source+Serif+4:ital,wght@0,300;0,400;0,600;1,300
- **CSS Import:** @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500&family=Playfair+Display:ital,wght@0,400;0,700;0,900;1,400&family=Source+Serif+4:ital,wght@0,300;0,400;0,600;1,300&display=swap');
- **Tailwind Config:** fontFamily: { display: ['Playfair Display', 'serif'], body: ['Source Serif 4', 'serif'], mono: ['JetBrains Mono', 'monospace'] }
- **Notes:** Triple stack: Playfair Display 900 tracking-tighter leading-[0.9] for heroes (text-5xl–text-6xl breaks words graphically). Source Serif 4 300–600 for body legibility. JetBrains Mono 400–500 uppercase tracking-widest for tags/dates/labels. NO UI sans-serif — 100% serif/mono.

### Result 4
- **Font Pairing Name:** Editorial Classic
- **Category:** Serif + Serif
- **Heading Font:** Cormorant Garamond
- **Body Font:** Libre Baskerville
- **Mood/Style Keywords:** editorial, classic, literary, traditional, refined, bookish
- **Best For:** Publishing, blogs, news sites, literary magazines, book covers
- **Google Fonts URL:** https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@400;500;600;700&family=Libre+Baskerville:wght@400;700&display=swap
- **CSS Import:** @import url('https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@400;500;600;700&family=Libre+Baskerville:wght@400;700&display=swap');
- **Tailwind Config:** fontFamily: { heading: ['Cormorant Garamond', 'serif'], body: ['Libre Baskerville', 'serif'] }
- **Notes:** All-serif pairing for traditional editorial feel.

### Result 5
- **Font Pairing Name:** Japanese Elegant
- **Category:** Serif + Sans
- **Heading Font:** Noto Serif JP
- **Body Font:** Noto Sans JP
- **Mood/Style Keywords:** japanese, elegant, traditional, modern, multilingual, readable
- **Best For:** Japanese sites, Japanese restaurants, cultural sites, anime/manga
- **Google Fonts URL:** https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@300;400;500;700&family=Noto+Serif+JP:wght@400;500;600;700&display=swap
- **CSS Import:** @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@300;400;500;700&family=Noto+Serif+JP:wght@400;500;600;700&display=swap');
- **Tailwind Config:** fontFamily: { serif: ['Noto Serif JP', 'serif'], sans: ['Noto Sans JP', 'sans-serif'] }
- **Notes:** Noto fonts excellent Japanese support. Traditional + modern feel.
```

---

## "long form reading line length" (domain: ux)

```
## UI Pro Max Search Results
**Domain:** ux | **Query:** long form reading line length
**Source:** ux-guidelines.csv | **Found:** 5 results

### Result 1
- **Category:** Typography
- **Issue:** Line Length
- **Platform:** Web
- **Description:** Long lines are hard to read
- **Do:** Limit to 65-75 characters per line
- **Don't:** Full-width text on large screens
- **Code Example Good:** max-w-prose
- **Code Example Bad:** Full viewport width text
- **Severity:** Medium

### Result 2
- **Category:** Typography
- **Issue:** Line Height
- **Platform:** All
- **Description:** Adequate line height improves readability
- **Do:** Use 1.5-1.75 for body text
- **Don't:** Cramped or excessive line height
- **Code Example Good:** leading-relaxed (1.625)
- **Code Example Bad:** leading-none (1)
- **Severity:** Medium

### Result 3
- **Category:** Forms
- **Issue:** Submit Feedback
- **Platform:** All
- **Description:** Confirm form submission status
- **Do:** Show loading then success/error state
- **Don't:** No feedback after submit
- **Code Example Good:** Loading -> Success message
- **Code Example Bad:** Button click with no response
- **Severity:** High

### Result 4
- **Category:** Content
- **Issue:** Truncation
- **Platform:** All
- **Description:** Handle long content gracefully
- **Do:** Truncate with ellipsis and expand option
- **Don't:** Overflow or broken layout
- **Code Example Good:** line-clamp-2 with expand
- **Code Example Bad:** Overflow or cut off
- **Severity:** Medium

### Result 5
- **Category:** Accessibility
- **Issue:** Form Labels
- **Platform:** All
- **Description:** Inputs must have associated labels
- **Do:** Use label with for attribute or wrap input
- **Don't:** Placeholder-only inputs
- **Code Example Good:** <label for='email'>
- **Code Example Bad:** placeholder='Email' only
- **Severity:** High
```

---

## "pagination list navigation" (domain: ux)

```
## UI Pro Max Search Results
**Domain:** ux | **Query:** pagination list navigation
**Source:** ux-guidelines.csv | **Found:** 5 results

### Result 1
- **Category:** Navigation
- **Issue:** Sticky Navigation
- **Platform:** Web
- **Description:** Fixed nav should not obscure content
- **Do:** Add padding-top to body equal to nav height
- **Don't:** Let nav overlap first section content
- **Code Example Good:** pt-20 (if nav is h-20)
- **Code Example Bad:** No padding compensation
- **Severity:** Medium

### Result 2
- **Category:** Accessibility
- **Issue:** Keyboard Navigation
- **Platform:** Web
- **Description:** Web users need complete keyboard navigation with visible focus on every operable control
- **Do:** Keep tab order aligned with visual order and test every action without a pointer
- **Don't:** Keyboard traps or illogical tab order
- **Code Example Good:** tabIndex for custom order
- **Code Example Bad:** Unreachable elements
- **Severity:** High

### Result 3
- **Category:** Navigation
- **Issue:** Breadcrumbs
- **Platform:** Web
- **Description:** Show user location in site hierarchy
- **Do:** Use for sites with 3+ levels of depth
- **Don't:** Use for flat single-level sites
- **Code Example Good:** Home > Category > Product
- **Code Example Bad:** Only on deep nested pages
- **Severity:** Low

### Result 4
- **Category:** Navigation
- **Issue:** Back Button
- **Platform:** Mobile
- **Description:** Users expect back to work predictably
- **Do:** Preserve navigation history properly
- **Don't:** Break browser/app back button behavior
- **Code Example Good:** history.pushState()
- **Code Example Bad:** location.replace()
- **Severity:** High

### Result 5
- **Category:** Accessibility
- **Issue:** Heading Hierarchy
- **Platform:** Web
- **Description:** Screen readers use headings for navigation
- **Do:** Use sequential heading levels h1-h6
- **Don't:** Skip heading levels or misuse for styling
- **Code Example Good:** h1 then h2 then h3
- **Code Example Bad:** h1 then h4
- **Severity:** Medium
```

---

## "search results loading" (domain: ux)

```
## UI Pro Max Search Results
**Domain:** ux | **Query:** search results loading
**Source:** ux-guidelines.csv | **Found:** 5 results

### Result 1
- **Category:** Search
- **Issue:** No Results
- **Platform:** Web
- **Description:** Dead ends frustrate users
- **Do:** Show 'No results' with suggestions
- **Don't:** Blank screen or '0 results'
- **Code Example Good:** Try searching for X instead
- **Code Example Bad:** No results found.
- **Severity:** Medium

### Result 2
- **Category:** Search
- **Issue:** Autocomplete
- **Platform:** Web
- **Description:** Help users find results faster
- **Do:** Show predictions as user types
- **Don't:** Require full type and enter
- **Code Example Good:** Debounced fetch + dropdown
- **Code Example Bad:** No suggestions
- **Severity:** Medium

### Result 3
- **Category:** Feedback
- **Issue:** Loading Indicators
- **Platform:** All
- **Description:** Loading feedback should match the expected wait and avoid flashing for near-instant work
- **Do:** Follow platform and component guidance; preserve layout focus and accessible busy status
- **Don't:** Apply one timing threshold to every operation or leave long waits unexplained
- **Code Example Good:** Stable skeleton or progress with aria-busy
- **Code Example Bad:** Flickering spinner or frozen UI
- **Severity:** High

### Result 4
- **Category:** Performance
- **Issue:** Lazy Loading
- **Platform:** All
- **Description:** Load content as needed
- **Do:** Lazy load below-fold images and content
- **Don't:** Load everything upfront
- **Code Example Good:** loading='lazy'
- **Code Example Bad:** All images eager load
- **Severity:** Medium

### Result 5
- **Category:** Animation
- **Issue:** Loading States
- **Platform:** All
- **Description:** Show feedback during async operations
- **Do:** Use skeleton screens or spinners
- **Don't:** Leave UI frozen with no feedback
- **Code Example Good:** animate-pulse skeleton
- **Code Example Bad:** Blank screen while loading
- **Severity:** High
```

---

## "editorial warm paper" (domain: color)

```
## UI Pro Max Search Results
**Domain:** color | **Query:** editorial warm paper
**Source:** colors.csv | **Found:** 5 results

### Result 1
- **Product Type:** Magazine/Blog
- **Primary:** #18181B
- **On Primary:** #FFFFFF
- **Secondary:** #3F3F46
- **On Secondary:** #FFFFFF
- **Accent:** #EC4899
- **On Accent:** #000000
- **Background:** #FAFAFA
- **Foreground:** #09090B
- **Card:** #FFFFFF
- **Card Foreground:** #09090B
- **Muted:** #E8ECF0
- **Muted Foreground:** #475569
- **Border:** #E4E4E7
- **Destructive:** #DC2626
- **On Destructive:** #FFFFFF
- **Ring:** #18181B
- **Notes:** Editorial black + accent pink

### Result 2
- **Product Type:** Podcast Platform
- **Primary:** #1E1B4B
- **On Primary:** #FFFFFF
- **Secondary:** #312E81
- **On Secondary:** #FFFFFF
- **Accent:** #F97316
- **On Accent:** #0F172A
- **Background:** #0F0F23
- **Foreground:** #F8FAFC
- **Card:** #1B1B30
- **Card Foreground:** #F8FAFC
- **Muted:** #27273B
- **Muted Foreground:** #94A3B8
- **Border:** #4338CA
- **Destructive:** #EF4444
- **On Destructive:** #000000
- **Ring:** #FFFFFF
- **Notes:** Dark audio + warm accent

### Result 3
- **Product Type:** Recipe & Cooking App
- **Primary:** #9A3412
- **On Primary:** #FFFFFF
- **Secondary:** #C2410C
- **On Secondary:** #FFFFFF
- **Accent:** #059669
- **On Accent:** #000000
- **Background:** #FFFBEB
- **Foreground:** #0F172A
- **Card:** #FFFFFF
- **Card Foreground:** #0F172A
- **Muted:** #F8F2F0
- **Muted Foreground:** #475569
- **Border:** #F2E6E2
- **Destructive:** #DC2626
- **On Destructive:** #FFFFFF
- **Ring:** #9A3412
- **Notes:** Warm terracotta + fresh green

### Result 4
- **Product Type:** Bookmark & Read-Later
- **Primary:** #D97706
- **On Primary:** #000000
- **Secondary:** #F59E0B
- **On Secondary:** #0F172A
- **Accent:** #2563EB
- **On Accent:** #FFFFFF
- **Background:** #FFFBEB
- **Foreground:** #0F172A
- **Card:** #FFFFFF
- **Card Foreground:** #0F172A
- **Muted:** #FCF6F0
- **Muted Foreground:** #475569
- **Border:** #FAEEE1
- **Destructive:** #DC2626
- **On Destructive:** #FFFFFF
- **Ring:** #D97706
- **Notes:** Warm amber + link blue

### Result 5
- **Product Type:** Music Instrument Learning
- **Primary:** #DC2626
- **On Primary:** #FFFFFF
- **Secondary:** #9A3412
- **On Secondary:** #FFFFFF
- **Accent:** #D97706
- **On Accent:** #000000
- **Background:** #FFFBEB
- **Foreground:** #0F172A
- **Card:** #FFFFFF
- **Card Foreground:** #0F172A
- **Muted:** #FCF1F1
- **Muted Foreground:** #475569
- **Border:** #FAE4E4
- **Destructive:** #DC2626
- **On Destructive:** #FFFFFF
- **Ring:** #DC2626
- **Notes:** Musical red + warm amber
```

---

## "rtl layout logical properties" (stack: html-tailwind)

> **Deviation note:** `--stack html-tailwind` returned **0 results** for the original query — no database
> match was found (the html-tailwind stack DB has no RTL entries). Per the skill's guidance, a broader
> retry was made, then the mandated `--domain web` fallback. All three outputs are included verbatim below.
> **Conclusion: no RTL guidance exists in the skill database; RTL specifics must come from general
> web standards (CSS logical properties `margin-inline-start`, `inset-inline-end`, `direction: rtl`).**

### 6a. Original attempt (`--stack html-tailwind`, query "rtl layout logical properties") — 0 results

```
## UI Pro Max Stack Guidelines
**Stack:** html-tailwind | **Query:** rtl layout logical properties
**Source:** stacks/html-tailwind.csv | **Found:** 0 results

No matches. This is not a match with an empty value -- the query did not hit the database. Retry with broader/different keywords before falling back to general defaults, and say explicitly that no database match was found if you do fall back.
```

### 6b. Broader retry (`--stack html-tailwind`, query "rtl direction text-align") — 0 results

```
## UI Pro Max Stack Guidelines
**Stack:** html-tailwind | **Query:** rtl direction text-align
**Source:** stacks/html-tailwind.csv | **Found:** 0 results

No matches. This is not a match with an empty value -- the query did not hit the database. Retry with broader/different keywords before falling back to general defaults, and say explicitly that no database match was found if you do fall back.
**Closest known terms:** direct, test, indication, context
```

### 6c. Fallback (`--domain web`, query "rtl layout logical properties") — 1 weak result

```
## UI Pro Max Search Results
**Domain:** web | **Query:** rtl layout logical properties
**Source:** app-interface.csv | **Found:** 1 results

### Result 1
- **Category:** Typography
- **Issue:** Dynamic Type Support
- **Platform:** iOS/Android/React Native
- **Description:** Support system text scaling without breaking layout
- **Do:** Set allowFontScaling and test large text
- **Don't:** Disable scaling on all text globally
- **Code Example Good:** <Text allowFontScaling>{label}</Text>
- **Code Example Bad:** <Text allowFontScaling={false}>{label}</Text>
- **Severity:** High
```

(The single fallback result is mobile-framework-specific and not directly applicable to an RTL web layout; included for completeness.)

"""
Phase 1: Raw Text Corpus Generator
Reads from crawled_data table, generates clean UTF-8 text corpus
for pre-training LLMs on Persian/Arabic rational sciences terminology.
"""

import sqlite3, json, os, re, hashlib
from pathlib import Path

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'backend', 'thesaurus.db')
OUTPUT_DIR = Path(__file__).parent / 'output'

def build_corpus():
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    
    terms = db.execute(
        "SELECT id, item_id, item_type, title, science_field, category_tree, "
        "full_data, source_text, crawled_at FROM crawled_data ORDER BY id"
    ).fetchall()
    
    db.close()
    
    print(f"Processing {len(terms)} crawled items...")
    
    corpus_lines = []
    
    # ── Header ──
    corpus_lines.append("# ============================================")
    corpus_lines.append("# پیکره اصطلاح‌نامه علوم عقلی اسلامی")
    corpus_lines.append("# Thesaurus of Islamic Rational Sciences - Raw Corpus")
    corpus_lines.append(f"# Total entries: {len(terms)}")
    corpus_lines.append("# Source: thesaurus.eiis.iki.ac.ir")
    corpus_lines.append("# Encoding: UTF-8")
    corpus_lines.append("# Format: One entry per section, metadata in YAML-like frontmatter")
    corpus_lines.append("# ============================================")
    corpus_lines.append("")
    
    stats = {"terms": 0, "keywords": 0, "indexes": 0, "grammars": 0, "empty": 0}
    
    for t in terms:
        title = (t['title'] or '').strip()
        item_type = t['item_type'] or 'term'
        science = (t['science_field'] or '').strip()
        category = (t['category_tree'] or '').strip()
        
        # Try to extract richer data from full_data JSON
        definition = ""
        related = []
        full_text = ""
        
        try:
            fd = json.loads(t['full_data'] or '{}')
            if isinstance(fd, dict):
                definition = fd.get('definition', fd.get('Description', fd.get('desc', '')))
                related = fd.get('related', fd.get('related_terms', []))
                # Build rich text from all available fields
                parts = []
                if fd.get('Title'):
                    parts.append(fd['Title'])
                if fd.get('Description'):
                    parts.append(f"تعریف: {fd['Description']}")
                if fd.get('Note'):
                    parts.append(f"یادداشت: {fd['Note']}")
                if fd.get('Source'):
                    parts.append(f"منبع: {fd['Source']}")
                full_text = '\n'.join(parts)
        except:
            pass
        
        if not title:
            stats['empty'] += 1
            continue
        
        # Build rich entry
        entry_lines = []
        entry_lines.append(f"---")
        entry_lines.append(f"entry_id: {t['item_id']}")
        entry_lines.append(f"type: {item_type}")
        entry_lines.append(f"title: {title}")
        if science:
            entry_lines.append(f"science: {science}")
        if category:
            entry_lines.append(f"category: {category}")
        entry_lines.append(f"---")
        entry_lines.append("")
        entry_lines.append(f"# {title}")
        entry_lines.append("")
        if full_text:
            entry_lines.append(full_text)
        else:
            entry_lines.append(f"اصطلاح: {title}")
            if science:
                entry_lines.append(f"رشته علمی: {science}")
            if category:
                entry_lines.append(f"رده: {category}")
        entry_lines.append("")
        
        corpus_lines.extend(entry_lines)
        stats[item_type + 's'] = stats.get(item_type + 's', 0) + 1
    
    # ── Write raw corpus ──
    corpus_text = '\n'.join(corpus_lines)
    
    raw_path = OUTPUT_DIR / 'thesaurus_raw_corpus.txt'
    raw_path.write_text(corpus_text, encoding='utf-8')
    
    # ── Write JSONL version (one JSON per line, for easy streaming) ──
    jsonl_entries = []
    for t in terms:
        entry = {
            'id': t['item_id'],
            'type': t['item_type'],
            'title': (t['title'] or '').strip(),
            'science_field': (t['science_field'] or '').strip(),
            'category': (t['category_tree'] or '').strip()
        }
        if entry['title']:
            jsonl_entries.append(json.dumps(entry, ensure_ascii=False))
    
    jsonl_path = OUTPUT_DIR / 'thesaurus_corpus.jsonl'
    jsonl_path.write_text('\n'.join(jsonl_entries), encoding='utf-8')
    
    # ── Write simple plain text corpus (title only, one per line) ──
    plain_lines = []
    for t in terms:
        title = (t['title'] or '').strip()
        if title:
            plain_lines.append(title)
    
    plain_path = OUTPUT_DIR / 'thesaurus_terms.txt'
    plain_path.write_text('\n'.join(plain_lines), encoding='utf-8')
    
    # ── Stats ──
    print(f"\n{'='*50}")
    print(f"Corpus generated successfully!")
    print(f"{'='*50}")
    print(f"\nFiles:")
    print(f"  1. {raw_path} ({raw_path.stat().st_size:,} bytes)")
    print(f"     → Full corpus with metadata (YAML + text)")
    print(f"  2. {jsonl_path} ({jsonl_path.stat().st_size:,} bytes)")
    print(f"     → JSONL format, one entry per line")
    print(f"  3. {plain_path} ({plain_path.stat().st_size:,} bytes)")
    print(f"     → Plain text, one term per line (for simple LM training)")
    print(f"\nStats:")
    print(f"  Total entries: {len(terms)}")
    print(f"  Terms: {stats.get('terms', 0)}")
    print(f"  Keywords: {stats.get('keywords', 0)}")
    print(f"  Indexes: {stats.get('indexes', 0)}")
    print(f"  Empty: {stats['empty']}")
    
    # ── HuggingFace README ──
    readme = f"""---
language:
  - fa
  - ar
license: cc-by-nc-sa-4.0
task_categories:
  - text-generation
  - fill-mask
tags:
  - persian
  - arabic
  - philosophy
  - theology
  - logic
  - islamic-studies
  - terminology
size_categories:
  - n<1K
pretty_name: Thesaurus of Islamic Rational Sciences
---

# پیکره اصطلاح‌نامه علوم عقلی اسلامی

**Thesaurus of Islamic Rational Sciences - Raw Corpus**

## Description

This corpus contains terminology from the thesaurus of Islamic rational sciences
(علوم عقلی اسلامی), sourced from the Imam Khomeini Research Center
(thesaurus.eiis.iki.ac.ir). It covers:

- **معرفت‌شناسی** (Epistemology)
- **منطق** (Logic)
- **منطق رواقی** (Stoic Logic)
- **فلسفه اسلامی** (Islamic Philosophy)
- **فلسفه اشراق** (Illuminationist Philosophy)
- **فلسفه دین** (Philosophy of Religion)
- **فلسفه اخلاق** (Philosophy of Ethics)
- **فلسفه حقوق** (Philosophy of Law)
- **فلسفه سیاسی** (Political Philosophy)

## Files

- `thesaurus_raw_corpus.txt` - Full corpus with YAML metadata headers
- `thesaurus_corpus.jsonl` - JSONL format, one JSON object per line
- `thesaurus_terms.txt` - Plain text, one term per line

## Statistics

- Total entries: {len(terms)}
- Language: Persian (Farsi) and Arabic
- Encoding: UTF-8

## License

CC BY-NC-SA 4.0 (for research and educational use)

## Citation

If you use this corpus, please cite:

```
@dataset{{thesaurus_rational_sciences,
  title={{Thesaurus of Islamic Rational Sciences}},
  year={{2026}},
  url={{https://thesaurus.eiis.iki.ac.ir}},
  publisher={{Imam Khomeini Research Center}}
}}
```
"""
    
    readme_path = OUTPUT_DIR / 'README.md'
    readme_path.write_text(readme, encoding='utf-8')
    print(f"\n  4. {readme_path}")
    print(f"     → HuggingFace dataset card (README.md)")


if __name__ == '__main__':
    build_corpus()

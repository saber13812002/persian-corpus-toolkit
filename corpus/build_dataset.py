"""
Phase 2: Instruction-Tuning Dataset Generator
Creates JSONL dataset in OpenAI/Gemini/Llama compatible format.
"""

import sqlite3, json, os, re, random
from pathlib import Path

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'backend', 'thesaurus.db')
OUTPUT_DIR = Path(__file__).parent / 'output'

QUESTION_TEMPLATES = [
    "مفهوم {title} در علوم عقلی چیست؟",
    "{title} را تعریف کن.",
    "در فلسفه، {title} به چه معناست؟",
    "اصطلاح {title} یعنی چه؟",
    "توضیح بده: {title}",
    "تعریف {title} در منطق و فلسفه چیست؟",
    "منظور از {title} در علوم اسلامی چیست؟",
    "مفهوم {title} در {science} چگونه تبیین می‌شود؟",
    "درباره اصطلاح {title} توضیح بده.",
    "{title} در چه شاخه‌ای از فلسفه مطرح می‌شود؟",
    "واژه {title} را در علوم عقلی معنا کن.",
    "فرق {title} با مفاهیم مشابه چیست؟",
]

SYSTEM_PROMPTS = [
    "شما یک استاد علوم عقلی اسلامی هستید. به سوالات درباره اصطلاحات فلسفی، منطقی و کلامی پاسخ دقیق و مستند بدهید.",
    "شما یک فرهنگ‌نامه تخصصی اصطلاحات فلسفه و منطق اسلامی هستید. تعاریف دقیق و علمی ارائه کنید.",
    "شما یک مرجع معتبر اصطلاحات علوم عقلی هستید. پاسخ‌های شما باید دقیق، علمی و مستند باشد.",
    "شما دانشنامه علوم عقلی اسلامی هستید. به پرسش‌های اصطلاح‌شناسی با دقت علمی پاسخ دهید.",
]


def _build_definition(term_row, title, science, category):
    parts = []
    try:
        fd = json.loads(term_row['full_data'] or '{}')
        if isinstance(fd, dict):
            if fd.get('description') or fd.get('Description'):
                parts.append(fd.get('description') or fd.get('Description'))
            if fd.get('definition') or fd.get('Definition'):
                parts.append(fd.get('definition') or fd.get('Definition'))
    except:
        pass
    
    if not parts:
        def_parts = [f"«{title}» یکی از اصطلاحات تخصصی در حوزه {science or 'علوم عقلی'} است."]
        if category:
            def_parts.append(f"این اصطلاح در ردهٔ «{category}» قرار می‌گیرد.")
        parts = [' '.join(def_parts)]
    
    definition = ' '.join(parts)
    if science:
        definition += f"\n\nاین مفهوم در شاخهٔ «{science}» از علوم عقلی اسلامی مورد بحث قرار می‌گیرد."
    
    return definition


def _validate_jsonl(filepath):
    path = Path(filepath)
    line_count = 0
    error_count = 0
    with open(filepath, 'r', encoding='utf-8') as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                json.loads(line)
                line_count += 1
            except json.JSONDecodeError as e:
                print(f"  ⚠️ Line {i}: {e}")
                error_count += 1
    
    status = "✅" if error_count == 0 else "❌"
    print(f"  {status} {path.name}: {line_count} valid lines, {error_count} errors")
    return error_count == 0


def build_dataset():
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    
    terms = db.execute(
        "SELECT id, item_id, item_type, title, science_field, category_tree, full_data "
        "FROM crawled_data WHERE title IS NOT NULL AND title != '' ORDER BY id"
    ).fetchall()
    
    db.close()
    
    print(f"Building dataset from {len(terms)} terms...")
    
    chatml_entries = []
    instruct_entries = []
    completion_entries = []
    
    random.seed(42)
    
    for t in terms:
        title = (t['title'] or '').strip()
        science = (t['science_field'] or '').strip()
        category = (t['category_tree'] or '').strip()
        
        if not title:
            continue
        
        definition = _build_definition(t, title, science, category)
        q_tmpl = random.choice(QUESTION_TEMPLATES)
        sys_prompt = random.choice(SYSTEM_PROMPTS)
        question = q_tmpl.format(title=title, science=science or "علوم عقلی")
        
        # ChatML
        chatml_entries.append({
            "messages": [
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": question},
                {"role": "assistant", "content": definition}
            ]
        })
        
        # Alpaca
        instruct_entries.append({
            "instruction": question,
            "input": "",
            "output": definition,
            "system": sys_prompt
        })
        
        # Completion
        completion_entries.append({
            "prompt": f"### System: {sys_prompt}\n\n### User: {question}\n\n### Assistant: ",
            "completion": definition
        })
    
    # Write
    files = {
        'thesaurus_dataset_chatml.jsonl': chatml_entries,
        'thesaurus_dataset_alpaca.jsonl': instruct_entries,
        'thesaurus_dataset_completion.jsonl': completion_entries,
    }
    
    for filename, entries in files.items():
        path = OUTPUT_DIR / filename
        with open(path, 'w', encoding='utf-8') as f:
            for entry in entries:
                f.write(json.dumps(entry, ensure_ascii=False) + '\n')
        _validate_jsonl(path)
    
    print(f"\n{'='*50}")
    print(f"Dataset generated successfully!")
    print(f"{'='*50}")
    print(f"\n  ChatML (OpenAI/Gemini): {len(chatml_entries)} entries")
    print(f"  Alpaca (Llama/Mistral): {len(instruct_entries)} entries")
    print(f"  Completion: {len(completion_entries)} entries")
    print(f"\nSample:")
    print(json.dumps(chatml_entries[0], ensure_ascii=False, indent=2)[:400])


if __name__ == '__main__':
    build_dataset()

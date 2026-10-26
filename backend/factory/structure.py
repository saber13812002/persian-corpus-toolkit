"""factory.structure — StructureExtractor (stage 5: سلسله‌مراتب تیترها).

ورودی: list[Block] از parser. خروجی: StructureTree.
- parent از تیک implicit (آخرین تیتر با level کوچک‌تر)
- chapters = تیترهای level 1
- front matter = بلوک‌های قبل از اولین heading (شمارش فقط — حدس نمی‌زنیم)
- confidence: 1.0 اگر heading وجود داشته باشد، وگرنه 0.5 (سند بدون ساختار)
"""
from __future__ import annotations

from .models import Block, StructureTree


def extract_structure(blocks: list[Block]) -> StructureTree:
    tree = StructureTree()
    tree.total_blocks = len(blocks)

    stack: list[tuple[int, int]] = []  # (level, block_index)
    for b in blocks:
        if b.type != "heading" or b.heading_level is None:
            continue
        while stack and stack[-1][0] >= b.heading_level:
            stack.pop()
        parent_index = stack[-1][1] if stack else None
        b.parent_block_id = (
            blocks[parent_index].block_id if parent_index is not None else None)
        tree.headings.append({
            "block_id": b.block_id,
            "block_index": b.block_index,
            "level": b.heading_level,
            "text": b.raw_text.strip()[:200],
            "parent_block_id": b.parent_block_id,
        })
        if b.heading_level == 1:
            tree.chapters.append({
                "block_id": b.block_id,
                "block_index": b.block_index,
                "text": b.raw_text.strip()[:200],
            })
        stack.append((b.heading_level, b.block_index))

    # front matter
    first_heading = next((h["block_index"] for h in tree.headings), None)
    if first_heading is None:
        tree.front_matter_blocks = len(blocks)
        tree.confidence = 0.5
        tree.notes.append("no headings found — document is flat")
    else:
        tree.front_matter_blocks = first_heading

    if not tree.headings:
        tree.notes.append("structure: no heading hierarchy (flat document)")
    return tree

"""factory.parser — DocumentParser / DocxParser (stage 4: استخراج بلوک‌ها).

علائم (interfaces):
- DocumentParser  : پروتکل عمومی (parse(file_record) -> ParseOutcome)
- DocxParser      : پیاده‌سازی DOCX (python-docx + خواندن parts خام برای footnotes)
- DocParserAdapter: تشخیص .doc + اعلام عدم پشتیبانی (WF-03) — هیچ parse نمی‌کند

اصل‌ها:
- ترتیب واقعی بلوک‌های body (پاراگراف/جدول به ترتیب XML) — WF-05
- تیترها از style (Heading1..9) + شناسه‌ی parent — WF-06
- footnotes/endnotes از parts جدا (footnotes.xml/endnotes.xml) — extract-only
- page number ساختگی ثبت نمی‌شود (null) — قانون PRD §4.2
- هر چیزی که استخراج کامل نمی‌شود (link/image/drawing/field) در `losses`
  شمارش می‌شود تا QualityValidator گزارش کند — ادعای استخراج کامل ممنوع.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .errors import ParseError, UnsupportedFormatError
from .intake import detect_format
from .models import (BLOCK_TYPES, Block, PARSER_VERSION, FileRecord)

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
W = "{%s}" % W_NS


@dataclass
class ParseOutcome:
    blocks: list[Block] = field(default_factory=list)
    losses: dict[str, int] = field(default_factory=dict)   # نوع ساختار گم‌شده -> count
    style_counts: dict[str, int] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    parser_version: str = PARSER_VERSION

    def to_dict(self) -> dict:
        return {
            "parser_version": self.parser_version,
            "block_count": len(self.blocks),
            "block_types": _tally(self.blocks),
            "losses": self.losses,
            "style_counts": self.style_counts,
            "warnings": self.warnings,
        }


def _tally(blocks: list[Block]) -> dict:
    d: dict[str, int] = {}
    for b in blocks:
        d[b.type] = d.get(b.type, 0) + 1
    return d


def _heading_level(style_name: Optional[str]) -> Optional[int]:
    """'Heading 1' / 'heading1' / 'Heading1' -> 1..9 ; وگرنه None."""
    if not style_name:
        return None
    s = style_name.strip().lower().replace(" ", "")
    if s.startswith("heading"):
        try:
            n = int(s[7:])
            if 1 <= n <= 9:
                return n
        except ValueError:
            pass
    return None


def _count_elements(elem, tags: tuple[str, ...]) -> int:
    """شمارش elements با tag مشخص در زیردرخت (برای losses)."""
    return sum(1 for e in elem.iter() if e.tag in tags)


class DocumentParser:
    """پروتکل: parse(rec) -> ParseOutcome. هر parser باید format خود را بررسی کند."""

    name = "base"

    def parse(self, rec: FileRecord) -> ParseOutcome:  # pragma: no cover - interface
        raise NotImplementedError


class DocParserAdapter(DocumentParser):
    """Adapter برای .doc قدیمی — فقط تشخیص و اعلام عدم پشتیبانی.

    این adapter هرگز .doc را به‌عنوان docx باز نمی‌کند (WF-03):
    با magic bytes OLE2 فرمت را تأیید و UnsupportedFormatError می‌دهد.
    """

    name = "doc"

    def parse(self, rec: FileRecord) -> ParseOutcome:
        fmt, how = detect_format(rec.path)
        if fmt == "doc":
            raise UnsupportedFormatError(
                ".doc (OLE2) در V0.1 پشتیبانی نمی‌شود؛ parser معتبر جدا لازم دارد.",
                format="doc", detected_by=how)
        if fmt == "docx":
            # پسوند .doc بود ولی محتوای docx — این را docx parser بگیرد
            raise UnsupportedFormatError(
                "پسوند .doc ولی محتوای DOCX است؛ با پسوند/مسیر صحیح دوباره دریافت کنید.",
                format="docx-in-doc-name", detected_by=how)
        raise UnsupportedFormatError(
            "فرمت برای DocParserAdapter نامشخص است", format=fmt, detected_by=how)


class DocxParser(DocumentParser):
    """parser اصلی DOCX."""

    name = "docx"

    def parse(self, rec: FileRecord) -> ParseOutcome:
        fmt, _how = detect_format(rec.path)
        if fmt != "docx":
            raise ParseError(f"فایل docx معتبر نیست برای parse (format={fmt})",
                             file_id=rec.file_id)

        from docx import Document
        from docx.table import Table
        from docx.text.paragraph import Paragraph

        try:
            doc = Document(rec.path)
        except Exception as e:
            raise ParseError(f"بازشدن docx ناموفق: {type(e).__name__}: {e}",
                             file_id=rec.file_id)

        outcome = ParseOutcome()
        body = doc.element.body

        idx = 0
        for child in body.iterchildren():
            tag = child.tag
            if tag == f"{W}p":
                para = Paragraph(child, doc)
                raw = "".join(run.text for run in para.runs) or para.text or ""
                # ساختارهای گمشده در این پاراگراف
                self._count_para_losses(child, outcome)
                style = para.style.name if para.style is not None else None
                lvl = _heading_level(style)
                b = Block(
                    block_index=idx,
                    type="heading" if lvl else "paragraph",
                    raw_text=raw,
                    style=style,
                    heading_level=lvl,
                )
                if not raw.strip():
                    b.type = "empty"
                outcome.style_counts[style or "None"] = outcome.style_counts.get(style or "None", 0) + 1
                outcome.blocks.append(b)
                idx += 1
            elif tag == f"{W}tbl":
                table = Table(child, doc)
                rows = []
                for r in table.rows:
                    rows.append([c.text.replace("\n", " ").strip() for c in r.cells])
                b = Block(block_index=idx, type="table", raw_text="", table_rows=rows)
                outcome.blocks.append(b)
                idx += 1
            elif tag == f"{W}sectPr":
                # sectPr = خواص بخش؛ در انتهای body همیشه وجود دارد و
                # «صفحه‌شکن محتوا» نیست → به‌عنوان بلوک ثبت نمی‌شود.
                continue
            else:
                outcome.losses[f"body:{tag.split('}')[-1]}"] = (
                    outcome.losses.get(f"body:{tag.split('}')[-1]}", 0) + 1)

        # ---------- footnotes / endnotes از parts خام ----------
        fn = self._extract_notes(doc, "footnotes")
        en = self._extract_notes(doc, "endnotes")
        for prefix, items in (("fn", fn), ("en", en)):
            for n in items:
                outcome.blocks.append(Block(
                    block_index=idx,
                    type="footnote" if prefix == "fn" else "endnote",
                    raw_text=n["text"],
                    ref_id=f"{prefix}-{n['id']}",
                ))
                idx += 1
        if fn:
            outcome.losses["footnotes_extracted"] = len(fn)  # ثبت (نه گم‌شده)
        if en:
            outcome.losses["endnotes_extracted"] = len(en)

        outcome.warnings = [w for w in outcome.warnings if w]
        return outcome

    # ---------- ابزارهای داخلی ----------
    @staticmethod
    def _count_para_losses(p_elem, outcome: ParseOutcome) -> None:
        losses = {
            "hyperlink": f"{W}hyperlink",
            "image": f"{W}drawing",
            "drawing": f"{W}pict",
            "field": f"{W}fldSimple",
            "object": f"{W}object",
            "sdt": f"{W}sdt",
        }
        for name, tag in losses.items():
            n = _count_elements(p_elem, (tag,))
            if n:
                outcome.losses[name] = outcome.losses.get(name, 0) + n
        # bookmarks/bookid را گم‌شده نمی‌دانیم (مهم نیست برای متن)
        if _count_elements(p_elem, (f"{W}footnoteReference",)):
            outcome.losses["footnote_ref_in_body"] = outcome.losses.get("footnote_ref_in_body", 0) + _count_elements(p_elem, (f"{W}footnoteReference",))
        if _count_elements(p_elem, (f"{W}endnoteReference",)):
            outcome.losses["endnote_ref_in_body"] = outcome.losses.get("endnote_ref_in_body", 0) + _count_elements(p_elem, (f"{W}endnoteReference",))

    @staticmethod
    def _extract_notes(doc, kind: str) -> list[dict]:
        """خواندن footnotes.xml / endnotes.xml مستقیم (python-docx footnote API محدود است)."""
        from lxml import etree
        result = []
        try:
            for rel in doc.part.rels.values():
                if kind in rel.reltype:
                    target = rel.target_part
                    root = etree.fromstring(target.blob)
                    for note in root.findall(f"{W}{kind[:-1]}"):
                        note_id = note.get(f"{W}id")
                        # footnote id=0/1 معمولاً separator/continuation — skip
                        if kind == "footnotes" and note_id in ("0", "1"):
                            continue
                        text = "".join(t.text or "" for t in note.iter(f"{W}t"))
                        if text.strip():
                            result.append({"id": note_id, "text": text})
                    break
        except Exception:
            pass  # part موجود نیست → خالی (نرم)
        return result


def make_parser(format_hint: Optional[str] = None) -> DocumentParser:
    """factory function: انتخاب parser بر اساس فرمت (doc → adapter)."""
    if format_hint == "doc":
        return DocParserAdapter()
    return DocxParser()

"""Turn a small Markdown subset into a clean Chinese Word document.

Supported: ## / ### headings, **bold**, bullet and numbered lists, > quotes,
tables, --- rules, page numbers in the footer. The H1 title is NOT taken from
the Markdown: pass --title so the doc has one title, not two.

Usage:
  python md2docx.py --md summary.md --out "活动总结.docx" \
      --title "微积分疑难讲座 · 活动总结" --subtitle "2026 年 11 月 · 依现场录音与课件整理"
"""
import argparse
import os
import re

from docx import Document
from docx.enum.section import WD_SECTION  # noqa: F401
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

CN_BODY = "宋体"
CN_HEAD = "黑体"
EN = "Times New Roman"


def set_run_font(run, cn=CN_BODY, size=None, bold=None, color=None, italic=None):
    run.font.name = EN
    rpr = run._element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.append(rfonts)
    rfonts.set(qn("w:eastAsia"), cn)
    if size:
        run.font.size = Pt(size)
    if bold is not None:
        run.font.bold = bold
    if italic is not None:
        run.font.italic = italic
    if color:
        run.font.color.rgb = color


def add_rich(p, text, size=11, bold_all=False, color=None, italic=None):
    for seg in re.split(r"(\*\*.+?\*\*)", text):
        if not seg:
            continue
        bold = seg.startswith("**") and seg.endswith("**")
        r = p.add_run(seg[2:-2] if bold else seg)
        set_run_font(r, size=size, bold=True if (bold or bold_all) else None,
                     color=color, italic=italic)


def shade(cell, fill):
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), fill)
    tc_pr.append(shd)


def add_page_number(paragraph):
    run = paragraph.add_run("第 ")
    set_run_font(run, size=9, color=RGBColor(0x80, 0x80, 0x80))
    run = paragraph.add_run()
    fld1 = OxmlElement("w:fldChar"); fld1.set(qn("w:fldCharType"), "begin")
    instr = OxmlElement("w:instrText"); instr.set(qn("xml:space"), "preserve"); instr.text = " PAGE "
    fld2 = OxmlElement("w:fldChar"); fld2.set(qn("w:fldCharType"), "end")
    run._r.append(fld1); run._r.append(instr); run._r.append(fld2)
    set_run_font(run, size=9, color=RGBColor(0x80, 0x80, 0x80))
    run = paragraph.add_run(" 页")
    set_run_font(run, size=9, color=RGBColor(0x80, 0x80, 0x80))


def build(md_path, out, title, subtitle=""):
    doc = Document()
    sec = doc.sections[0]
    sec.page_width, sec.page_height = Cm(21.0), Cm(29.7)
    sec.left_margin = sec.right_margin = Cm(2.6)
    sec.top_margin = sec.bottom_margin = Cm(2.3)

    normal = doc.styles["Normal"]
    normal.font.name = EN
    normal.font.size = Pt(11)
    normal.element.rPr.rFonts.set(qn("w:eastAsia"), CN_BODY)

    fp = sec.footer.paragraphs[0]
    fp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    add_page_number(fp)

    t = doc.add_paragraph()
    t.alignment = WD_ALIGN_PARAGRAPH.CENTER
    t.paragraph_format.space_before = Pt(6)
    t.paragraph_format.space_after = Pt(4)
    r = t.add_run(title)
    set_run_font(r, cn=CN_HEAD, size=20, bold=True)

    if subtitle:
        s = doc.add_paragraph()
        s.alignment = WD_ALIGN_PARAGRAPH.CENTER
        s.paragraph_format.space_after = Pt(18)
        r2 = s.add_run(subtitle)
        set_run_font(r2, size=10.5, color=RGBColor(0x66, 0x66, 0x66))

    lines = open(md_path, encoding="utf-8").read().splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].rstrip()
        if not line.strip() or line.strip().startswith("<!--"):
            i += 1
            continue
        if line.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                raw = lines[i].strip().strip("|")
                if not re.fullmatch(r"[\s:\-|]+", raw):
                    rows.append([c.strip() for c in raw.split("|")])
                i += 1
            if rows:
                ncol = len(rows[0])
                table = doc.add_table(rows=0, cols=ncol)
                table.style = "Table Grid"
                table.alignment = WD_TABLE_ALIGNMENT.CENTER
                table.autofit = True
                for ri, row in enumerate(rows):
                    cells = table.add_row().cells
                    for ci, val in enumerate(row[:ncol]):
                        cells[ci].text = ""
                        p = cells[ci].paragraphs[0]
                        p.paragraph_format.space_after = Pt(2)
                        p.paragraph_format.line_spacing = 1.15
                        if ri == 0:
                            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                        add_rich(p, val, size=9.5, bold_all=(ri == 0))
                        if ri == 0:
                            shade(cells[ci], "E8EEF7")
                tr_pr = table.rows[0]._tr.get_or_add_trPr()
                tbl_header = OxmlElement("w:tblHeader")
                tbl_header.set(qn("w:val"), "true")
                tr_pr.append(tbl_header)
                doc.add_paragraph().paragraph_format.space_after = Pt(2)
            continue

        if line.startswith("### "):
            p = doc.add_paragraph()
            p.paragraph_format.space_before = Pt(10)
            p.paragraph_format.space_after = Pt(4)
            p.paragraph_format.keep_with_next = True
            set_run_font(p.add_run(line[4:]), cn=CN_HEAD, size=12.5, bold=True)
        elif line.startswith("## "):
            p = doc.add_paragraph()
            p.paragraph_format.space_before = Pt(16)
            p.paragraph_format.space_after = Pt(6)
            p.paragraph_format.keep_with_next = True
            set_run_font(p.add_run(line[3:]), cn=CN_HEAD, size=15, bold=True)
        elif line.startswith("# "):
            p = doc.add_paragraph()
            p.paragraph_format.space_before = Pt(18)
            p.paragraph_format.space_after = Pt(8)
            set_run_font(p.add_run(line[2:]), cn=CN_HEAD, size=17, bold=True)
        elif line.startswith("> "):
            p = doc.add_paragraph()
            p.paragraph_format.left_indent = Cm(0.8)
            p.paragraph_format.space_after = Pt(6)
            p.paragraph_format.line_spacing = 1.4
            add_rich(p, line[2:], size=10.5, color=RGBColor(0x44, 0x44, 0x44), italic=True)
        elif re.match(r"^[-*] ", line):
            p = doc.add_paragraph(style="List Bullet")
            p.paragraph_format.space_after = Pt(4)
            p.paragraph_format.line_spacing = 1.45
            add_rich(p, line[2:], size=10.5)
        elif re.match(r"^\d+\. ", line):
            m = re.match(r"^(\d+)\. (.*)$", line)
            p = doc.add_paragraph()
            p.paragraph_format.left_indent = Cm(0.75)
            p.paragraph_format.first_line_indent = Cm(-0.75)
            p.paragraph_format.space_after = Pt(2)
            p.paragraph_format.line_spacing = 1.4
            add_rich(p, f"{m.group(1)}. {m.group(2)}", size=10.5)
        elif line.startswith("---"):
            p = doc.add_paragraph()
            p.paragraph_format.space_before = Pt(4)
            p.paragraph_format.space_after = Pt(4)
            pPr = p._p.get_or_add_pPr()
            pbdr = OxmlElement("w:pBdr")
            bottom = OxmlElement("w:bottom")
            bottom.set(qn("w:val"), "single"); bottom.set(qn("w:sz"), "6")
            bottom.set(qn("w:space"), "1"); bottom.set(qn("w:color"), "D9D9D9")
            pbdr.append(bottom); pPr.append(pbdr)
        else:
            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
            p.paragraph_format.space_after = Pt(6)
            p.paragraph_format.line_spacing = 1.5
            p.paragraph_format.first_line_indent = Pt(22)
            add_rich(p, line, size=11)
        i += 1

    doc.save(out)
    report(out)


def report(path):
    doc = Document(path)
    text = "\n".join(p.text for p in doc.paragraphs)
    for tb in doc.tables:
        for row in tb.rows:
            text += "\n" + "\t".join(c.text for c in row.cells)
    leftovers = [tok for tok in ("**", "##", "<!--", "| ---") if tok in text]
    print(f"saved {path} size={os.path.getsize(path)} paras={len(doc.paragraphs)} "
          f"tables={len(doc.tables)} chars={len(text)}")
    if leftovers:
        print(f"[warn] markdown leftovers in docx: {leftovers}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--md", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--title", required=True)
    ap.add_argument("--subtitle", default="")
    args = ap.parse_args()
    build(args.md, args.out, args.title, args.subtitle)


if __name__ == "__main__":
    main()

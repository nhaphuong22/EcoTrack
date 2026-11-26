import re
import os
import docx
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_ALIGN_VERTICAL
from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import nsdecls, qn

def set_cell_background(cell, hex_color):
    """Sets the background color of a table cell."""
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = parse_xml(f'<w:shd {nsdecls("w")} w:fill="{hex_color}"/>')
    tc_pr.append(shd)

def set_cell_margins(cell, top=100, bottom=100, left=150, right=150):
    """Sets internal padding for a cell (in twips: 20 twips = 1 pt)."""
    tc_pr = cell._tc.get_or_add_tcPr()
    tc_mar = parse_xml(
        f'<w:tcMar {nsdecls("w")}>'
        f'<w:top w:w="{top}" w:type="dxa"/>'
        f'<w:bottom w:w="{bottom}" w:type="dxa"/>'
        f'<w:left w:w="{left}" w:type="dxa"/>'
        f'<w:right w:w="{right}" w:type="dxa"/>'
        f'</w:tcMar>'
    )
    tc_pr.append(tc_mar)

def set_cell_border(cell, **kwargs):
    """
    kwargs: top, bottom, left, right
    values: dict(sz=12, val='single', color='0D9488', space='0')
    """
    tc_pr = cell._tc.get_or_add_tcPr()
    tc_borders = parse_xml(f'<w:tcBorders {nsdecls("w")}/>')
    for edge in ('top', 'left', 'bottom', 'right', 'insideH', 'insideV'):
        edge_data = kwargs.get(edge)
        if edge_data:
            tag = f'<w:{edge} {nsdecls("w")} w:val="{edge_data.get("val", "single")}" w:sz="{edge_data.get("sz", 4)}" w:space="{edge_data.get("space", 0)}" w:color="{edge_data.get("color", "CCCCCC")}"/>'
            tc_borders.append(parse_xml(tag))
        else:
            tag = f'<w:{edge} {nsdecls("w")} w:val="none"/>'
            tc_borders.append(parse_xml(tag))
    tc_pr.append(tc_borders)

def format_inline(paragraph, text, base_font_size=11, base_color=(31, 41, 55), italic_override=False):
    """Parses markdown inline bold (**), italic (*), and code (`) within a paragraph."""
    # Pattern to match bold-italic (***...***), bold (**...**), italic (*...*), code (`...`)
    tokens = re.split(r'(\*\*\*.*?\*\*\*|\*\*.*?\*\*|\*.*?\*|`.*?`)', text)
    for token in tokens:
        if not token:
            continue
        run = paragraph.add_run()
        run.font.name = "Calibri"
        run.font.size = Pt(base_font_size)
        run.font.color.rgb = RGBColor(*base_color)

        if token.startswith('***') and token.endswith('***'):
            run.text = token[3:-3]
            run.bold = True
            run.italic = True
        elif token.startswith('**') and token.endswith('**'):
            run.text = token[2:-2]
            run.bold = True
            run.italic = italic_override
        elif token.startswith('*') and token.endswith('*'):
            run.text = token[1:-1]
            run.italic = True
        elif token.startswith('`') and token.endswith('`'):
            run.text = token[1:-1]
            run.font.name = "Consolas"
            run.font.size = Pt(base_font_size - 0.5)
            run.font.color.rgb = RGBColor(185, 28, 28) # Dark Red for inline code
        else:
            run.text = token
            run.italic = italic_override

def convert_md_to_docx(md_path, docx_path):
    doc = Document()

    # Page setup: A4, 1-inch margins
    sections = doc.sections
    for section in sections:
        section.top_margin = Inches(1)
        section.bottom_margin = Inches(1)
        section.left_margin = Inches(1)
        section.right_margin = Inches(1)

    # Styles
    COLOR_PRIMARY = (30, 58, 138)    # Deep Navy Blue #1E3A8A
    COLOR_SECONDARY = (13, 148, 136) # Teal #0D9488
    COLOR_TEXT = (31, 41, 55)        # Charcoal #1F2937
    COLOR_MUTED = (75, 85, 99)       # Gray #4B5563
    COLOR_QUOTE = (55, 65, 81)       # Slate Gray

    with open(md_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    in_code_block = False
    code_block_lines = []
    in_table = False
    table_lines = []

    def flush_table(lines):
        if not lines:
            return
        # Parse table markdown
        rows_data = []
        for line in lines:
            if not line.strip().startswith('|'):
                continue
            cells = [c.strip() for c in line.strip().split('|')[1:-1]]
            # Skip separator line (e.g. |:---|:---:|)
            if all(re.match(r'^:?-+:?$', c) for c in cells):
                continue
            rows_data.append(cells)

        if not rows_data:
            return

        num_cols = max(len(row) for row in rows_data)
        table = doc.add_table(rows=len(rows_data), cols=num_cols)
        table.alignment = WD_TABLE_ALIGNMENT.CENTER
        table.autofit = True

        for r_idx, row in enumerate(rows_data):
            for c_idx, cell_value in enumerate(row):
                if c_idx >= num_cols:
                    break
                cell = table.cell(r_idx, c_idx)
                cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
                set_cell_margins(cell, top=140, bottom=140, left=180, right=180)
                
                # Header row
                if r_idx == 0:
                    set_cell_background(cell, "1E3A8A") # Navy
                    p = cell.paragraphs[0]
                    p.paragraph_format.space_before = Pt(2)
                    p.paragraph_format.space_after = Pt(2)
                    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                    run = p.add_run(cell_value)
                    run.bold = True
                    run.font.name = "Calibri"
                    run.font.size = Pt(10.5)
                    run.font.color.rgb = RGBColor(255, 255, 255)
                    set_cell_border(cell, 
                                    bottom=dict(sz=12, val='single', color='1E3A8A'),
                                    insideH=dict(sz=4, val='single', color='CBD5E1'),
                                    insideV=dict(sz=4, val='single', color='CBD5E1'))
                else:
                    # Alternating row colors
                    if r_idx % 2 == 1:
                        set_cell_background(cell, "F8FAFC") # Light Slate
                    else:
                        set_cell_background(cell, "FFFFFF")
                    p = cell.paragraphs[0]
                    p.paragraph_format.space_before = Pt(2)
                    p.paragraph_format.space_after = Pt(2)
                    format_inline(p, cell_value, base_font_size=10, base_color=COLOR_TEXT)
                    set_cell_border(cell, 
                                    bottom=dict(sz=4, val='single', color='E2E8F0'),
                                    top=dict(sz=4, val='single', color='E2E8F0'),
                                    left=dict(sz=4, val='single', color='E2E8F0'),
                                    right=dict(sz=4, val='single', color='E2E8F0'))

        doc.add_paragraph().paragraph_format.space_after = Pt(4)

    def flush_code_block(lines):
        if not lines:
            return
        # Add styled callout box for code block
        table = doc.add_table(rows=1, cols=1)
        table.alignment = WD_TABLE_ALIGNMENT.CENTER
        cell = table.cell(0, 0)
        set_cell_background(cell, "F1F5F9")
        set_cell_margins(cell, top=140, bottom=140, left=200, right=200)
        set_cell_border(cell, 
                        left=dict(sz=24, val='single', color='0D9488'),
                        top=dict(sz=4, val='single', color='E2E8F0'),
                        bottom=dict(sz=4, val='single', color='E2E8F0'),
                        right=dict(sz=4, val='single', color='E2E8F0'))
        
        p = cell.paragraphs[0]
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after = Pt(0)
        p.paragraph_format.line_spacing = 1.15
        
        for i, code_line in enumerate(lines):
            if i > 0:
                p = cell.add_paragraph()
                p.paragraph_format.space_before = Pt(0)
                p.paragraph_format.space_after = Pt(0)
                p.paragraph_format.line_spacing = 1.15
            run = p.add_run(code_line)
            run.font.name = "Consolas"
            run.font.size = Pt(9.5)
            run.font.color.rgb = RGBColor(30, 41, 59)
            
        doc.add_paragraph().paragraph_format.space_after = Pt(4)

    i = 0
    while i < len(lines):
        line = lines[i].rstrip('\r\n')

        # Code block handler
        if line.startswith('```'):
            if in_code_block:
                in_code_block = False
                flush_code_block(code_block_lines)
                code_block_lines = []
            else:
                if in_table:
                    in_table = False
                    flush_table(table_lines)
                    table_lines = []
                in_code_block = True
                code_block_lines = []
            i += 1
            continue

        if in_code_block:
            code_block_lines.append(line)
            i += 1
            continue

        # Table handler
        if line.strip().startswith('|') and '|' in line.strip()[1:]:
            if not in_table:
                in_table = True
                table_lines = []
            table_lines.append(line)
            i += 1
            continue
        else:
            if in_table:
                in_table = False
                flush_table(table_lines)
                table_lines = []

        # Empty line
        if not line.strip():
            i += 1
            continue

        # Horizontal rule
        if re.match(r'^-{3,}$', line.strip()):
            p = doc.add_paragraph()
            p.paragraph_format.space_before = Pt(6)
            p.paragraph_format.space_after = Pt(6)
            # Add light border line
            pBdr = parse_xml(f'<w:pBdr {nsdecls("w")}><w:bottom w:val="single" w:sz="6" w:space="1" w:color="CBD5E1"/></w:pBdr>')
            p._p.get_or_add_pPr().append(pBdr)
            i += 1
            continue

        # Headings
        if line.startswith('# '):
            p = doc.add_paragraph()
            p.paragraph_format.space_before = Pt(14)
            p.paragraph_format.space_after = Pt(4)
            p.paragraph_format.keep_with_next = True
            run = p.add_run(line[2:].strip())
            run.font.name = "Calibri"
            run.font.size = Pt(18)
            run.bold = True
            run.font.color.rgb = RGBColor(*COLOR_PRIMARY)
        elif line.startswith('## '):
            p = doc.add_paragraph()
            p.paragraph_format.space_before = Pt(12)
            p.paragraph_format.space_after = Pt(4)
            p.paragraph_format.keep_with_next = True
            run = p.add_run(line[3:].strip())
            run.font.name = "Calibri"
            run.font.size = Pt(14)
            run.bold = True
            run.font.color.rgb = RGBColor(*COLOR_PRIMARY)
        elif line.startswith('### '):
            p = doc.add_paragraph()
            p.paragraph_format.space_before = Pt(10)
            p.paragraph_format.space_after = Pt(3)
            p.paragraph_format.keep_with_next = True
            run = p.add_run(line[4:].strip())
            run.font.name = "Calibri"
            run.font.size = Pt(12)
            run.bold = True
            run.font.color.rgb = RGBColor(*COLOR_SECONDARY)
        elif line.startswith('#### '):
            p = doc.add_paragraph()
            p.paragraph_format.space_before = Pt(8)
            p.paragraph_format.space_after = Pt(2)
            p.paragraph_format.keep_with_next = True
            run = p.add_run(line[5:].strip())
            run.font.name = "Calibri"
            run.font.size = Pt(11)
            run.bold = True
            run.font.color.rgb = RGBColor(*COLOR_TEXT)
        # Blockquote (Speaker notes, quotes)
        elif line.startswith('> '):
            quote_text = line[2:].strip()
            # Look ahead for multiline quotes
            while i + 1 < len(lines) and lines[i+1].startswith('> '):
                i += 1
                quote_text += " " + lines[i][2:].strip()

            # Create styled callout box for quotes / speaker notes
            table = doc.add_table(rows=1, cols=1)
            table.alignment = WD_TABLE_ALIGNMENT.CENTER
            cell = table.cell(0, 0)
            set_cell_background(cell, "F0FDFA") # Very light teal #F0FDFA
            set_cell_margins(cell, top=120, bottom=120, left=180, right=180)
            set_cell_border(cell, 
                            left=dict(sz=24, val='single', color='0D9488'),
                            top=dict(sz=4, val='single', color='CCFBF1'),
                            bottom=dict(sz=4, val='single', color='CCFBF1'),
                            right=dict(sz=4, val='single', color='CCFBF1'))
            p = cell.paragraphs[0]
            p.paragraph_format.space_before = Pt(0)
            p.paragraph_format.space_after = Pt(0)
            p.paragraph_format.line_spacing = 1.15
            format_inline(p, quote_text, base_font_size=10.5, base_color=COLOR_QUOTE, italic_override=True)
            doc.add_paragraph().paragraph_format.space_after = Pt(3)

        # Bullet list
        elif re.match(r'^\s*[-*]\s+', line):
            indent_level = len(re.match(r'^\s*', line).group(0)) // 2
            content = re.sub(r'^\s*[-*]\s+', '', line)
            p = doc.add_paragraph(style='List Bullet')
            p.paragraph_format.space_before = Pt(1)
            p.paragraph_format.space_after = Pt(2)
            p.paragraph_format.line_spacing = 1.15
            if indent_level > 0:
                p.paragraph_format.left_indent = Inches(0.25 * (indent_level + 1))
            format_inline(p, content, base_font_size=11, base_color=COLOR_TEXT)

        # Numbered list
        elif re.match(r'^\s*\d+\.\s+', line):
            indent_level = len(re.match(r'^\s*', line).group(0)) // 2
            content = re.sub(r'^\s*\d+\.\s+', '', line)
            match_num = re.match(r'^\s*(\d+)\.\s+', line).group(1)
            p = doc.add_paragraph()
            p.paragraph_format.space_before = Pt(1)
            p.paragraph_format.space_after = Pt(2)
            p.paragraph_format.line_spacing = 1.15
            p.paragraph_format.left_indent = Inches(0.35 + 0.25 * indent_level)
            
            # Add number run
            num_run = p.add_run(f"{match_num}.  ")
            num_run.bold = True
            num_run.font.name = "Calibri"
            num_run.font.size = Pt(11)
            num_run.font.color.rgb = RGBColor(*COLOR_PRIMARY)
            
            format_inline(p, content, base_font_size=11, base_color=COLOR_TEXT)

        # Normal paragraph
        else:
            p = doc.add_paragraph()
            p.paragraph_format.space_before = Pt(2)
            p.paragraph_format.space_after = Pt(3)
            p.paragraph_format.line_spacing = 1.15
            format_inline(p, line, base_font_size=11, base_color=COLOR_TEXT)

        i += 1

    # End cleanup
    if in_table:
        flush_table(table_lines)
    if in_code_block:
        flush_code_block(code_block_lines)

    doc.save(docx_path)
    print(f"Successfully converted to {docx_path}")

if __name__ == '__main__':
    md_file = r"C:\Users\ADMIN\.gemini\antigravity\brain\8a00d1b3-1e48-49ea-90ca-767af4520946\bao-cao-tien-do-ecotrack-giang-vien.md"
    docx_file = r"C:\Users\ADMIN\Desktop\EcoTrack\Bao_Cao_Tien_Do_EcoTrack.docx"
    convert_md_to_docx(md_file, docx_file)

"""立项 / 发布文件的 Word 排版工具（python-docx）。

用法：
    import sys; sys.path.insert(0, '<skill>/scripts')
    from docx_kit import *          # 得到 doc、W（版心宽 cm）和下面的函数
    heading('一、需求分析', 1)
    para('**粗体**和普通文字')
    table(['渠道', '月销'], [['Amazon', '227 件']], [4, 4])
    comp_table(competitors, '我们贵 / 便宜…')   # 见函数说明
    save('xxx_立项.docx', pdf=True)            # 同时用 LibreOffice 转 PDF

检查：转 PDF 后 `pdftoppm -r 45 -png x.pdf pv/p` 逐页看；LibreOffice 会忽略自动列宽，
所以所有表格都经 fix_widths 设成固定宽度。不要在文字里用 emoji（PDF 中会变方框）。
"""
import html as _html
import os, subprocess
import docx.opc.constants
from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_CELL_VERTICAL_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt, Cm, RGBColor

FONT = '微软雅黑'
doc = Document()
_sec = doc.sections[0]
_sec.page_width, _sec.page_height = Cm(21), Cm(29.7)
_sec.left_margin = _sec.right_margin = Cm(1.6)
_sec.top_margin = _sec.bottom_margin = Cm(1.5)
W = 21 - 3.2
_st = doc.styles['Normal']
_st.font.name = FONT; _st.font.size = Pt(10)
_st.element.rPr.rFonts.set(qn('w:eastAsia'), FONT)
for _s, _z in (('Heading 1', 16), ('Heading 2', 13), ('Heading 3', 11), ('Title', 22)):
    _x = doc.styles[_s]; _x.font.name = FONT; _x.font.size = Pt(_z); _x.font.color.rgb = RGBColor(0x1f, 0x2d, 0x3d)
    _x.element.rPr.rFonts.set(qn('w:eastAsia'), FONT)

C_ = WD_ALIGN_PARAGRAPH.CENTER
ACC = RGBColor(0x2a, 0x78, 0xd6)
GREY_T = RGBColor(0x77, 0x77, 0x77)
GREEN, AMBER, RED, GREY = 'E3F2E6', 'FFF4D6', 'FBE3E3', 'F2F4F7'
BLUE_BOX, GREEN_BOX, YELLOW_BOX = 'EEF4FC', 'EAF6EE', 'FFF8E6'
CHN = {'amazon': 'Amazon', 'lowes': "Lowe's", 'homedepot': 'Home Depot', 'wayfair': 'Wayfair'}


def link_of(ch, pid):
    return {'amazon': f'https://www.amazon.com/dp/{pid}', 'lowes': f'https://www.lowes.com/pd/{pid}',
            'homedepot': f'https://www.homedepot.com/p/{pid}',
            'wayfair': f'https://www.wayfair.com/keyword.php?keyword={pid}'}[ch]


def heading(text, level):
    return doc.add_heading(text, level)


def add_runs(p, text, bold=False, size=None, color=None, italic=False):
    """text 中 **xx** 为粗体段。"""
    for i, t in enumerate(text.split('**')):
        if not t: continue
        r = p.add_run(t); r.bold = bold or (i % 2 == 1); r.italic = italic
        if size: r.font.size = Pt(size)
        if color: r.font.color.rgb = color
    return p


def para(text='', bold=False, size=None, color=None, align=None, after=4):
    p = doc.add_paragraph()
    if text: add_runs(p, text, bold=bold, size=size, color=color)
    p.paragraph_format.space_after = Pt(after)
    if align: p.alignment = align
    return p


def note(text):
    """数据来源 / 口径，灰色 8 号字。"""
    return para(text, size=8, color=GREY_T)


def bullet(text):
    p = doc.add_paragraph(style='List Bullet'); add_runs(p, text); p.paragraph_format.space_after = Pt(2)
    return p


def shade(cell, hexcolor):
    s = OxmlElement('w:shd'); s.set(qn('w:val'), 'clear'); s.set(qn('w:color'), 'auto'); s.set(qn('w:fill'), hexcolor)
    cell._tc.get_or_add_tcPr().append(s)


def fix_widths(t, widths):
    """固定列宽（cm），LibreOffice 转 PDF 才会按宽度排版。"""
    tblPr = t._tbl.tblPr
    lay = OxmlElement('w:tblLayout'); lay.set(qn('w:type'), 'fixed'); tblPr.append(lay)
    tw = tblPr.find(qn('w:tblW'))
    if tw is None: tw = OxmlElement('w:tblW'); tblPr.append(tw)
    tw.set(qn('w:w'), str(int(sum(widths) * 567))); tw.set(qn('w:type'), 'dxa')
    for i, gc in enumerate(t._tbl.tblGrid.findall(qn('w:gridCol'))):
        gc.set(qn('w:w'), str(int(widths[i] * 567)))
    for row in t.rows:
        for i, w in enumerate(widths): row.cells[i].width = Cm(w)


def callout(lines, fill=BLUE_BOX):
    """结论框：蓝=核心结论，绿=分析结论，黄=利润/提醒。"""
    t = doc.add_table(rows=1, cols=1); t.alignment = WD_TABLE_ALIGNMENT.CENTER
    fix_widths(t, [W]); c = t.cell(0, 0); shade(c, fill); c.paragraphs[0].text = ''
    for i, ln in enumerate(lines):
        p = c.paragraphs[0] if i == 0 else c.add_paragraph()
        add_runs(p, ln, size=10); p.paragraph_format.space_after = Pt(2)
    para(after=2)


def hyperlink(p, url, text, size=8):
    r_id = p.part.relate_to(url, docx.opc.constants.RELATIONSHIP_TYPE.HYPERLINK, is_external=True)
    h = OxmlElement('w:hyperlink'); h.set(qn('r:id'), r_id)
    r = OxmlElement('w:r'); rPr = OxmlElement('w:rPr')
    c = OxmlElement('w:color'); c.set(qn('w:val'), '2A78D6'); rPr.append(c)
    u = OxmlElement('w:u'); u.set(qn('w:val'), 'single'); rPr.append(u)
    sz = OxmlElement('w:sz'); sz.set(qn('w:val'), str(size * 2)); rPr.append(sz)
    r.append(rPr); tt = OxmlElement('w:t'); tt.text = text; r.append(tt); h.append(r); p._p.append(h)


def img_cell(path, w=2.0):
    def f(c):
        c.text = ''; c.paragraphs[0].add_run().add_picture(path, width=Cm(w)); c.paragraphs[0].alignment = C_
    return {'fn': f}


def link_cell(lines, url, label='打开链接'):
    def f(c):
        c.text = ''
        for j, ln in enumerate(lines):
            p = c.paragraphs[0] if j == 0 else c.add_paragraph()
            add_runs(p, ln, size=8); p.paragraph_format.space_after = Pt(0)
        p = c.add_paragraph(); p.paragraph_format.space_after = Pt(0); hyperlink(p, url, label)
    return {'fn': f}


def table(header, rows, widths, size=8, head_fill='DCE6F2', aligns=None):
    """rows 的单元格可以是字符串（\\n 换行，**粗体**），或 {'t': 文字, 'fill': 底色} / {'fn': 自定义填充}。"""
    t = doc.add_table(rows=1, cols=len(header)); t.style = 'Table Grid'; t.alignment = WD_TABLE_ALIGNMENT.CENTER
    t.autofit = False
    for i, h in enumerate(header):
        c = t.rows[0].cells[i]; c.text = ''; shade(c, head_fill)
        add_runs(c.paragraphs[0], h, bold=True, size=size); c.paragraphs[0].alignment = C_
        c.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
    for row in rows:
        cells = t.add_row().cells
        for i, v in enumerate(row):
            c = cells[i]; c.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            if isinstance(v, dict):
                if v.get('fill'): shade(c, v['fill'])
                if v.get('fn'): v['fn'](c); continue
                v = v.get('t', '')
            c.text = ''
            for j, ln in enumerate(str(v).split('\n')):
                p = c.paragraphs[0] if j == 0 else c.add_paragraph()
                add_runs(p, ln, size=size); p.paragraph_format.space_after = Pt(0)
                if aligns and aligns[i]: p.alignment = aligns[i]
    fix_widths(t, widths)
    para(after=2)
    return t


def pic(path, width=W):
    doc.add_picture(path, width=Cm(width)); doc.paragraphs[-1].alignment = C_


def usd(x):
    if x in (None, ''): return '—'
    x = float(x)
    return f'${x:,.0f}' if x >= 100 else f'${x:,.2f}'


def margin_fill(m):
    """利润率底色：≥10% 绿，0–10% 黄，<0 红。"""
    return GREEN if m >= 10 else (AMBER if m >= 0 else RED)


def comp_table(items, vs, group=None):
    """竞品表。items: 列表，每项 dict：
         ch（amazon/lowes/homedepot/wayfair）、pid、brand、title、img（本地图片路径）、price、
         rating、reviews、sales（月销）、config（多行配置文字，如 "整装，落地式\\n陶瓷盆\\nMDF"）
       vs: {pid: "和我们比" 文字}，差价按我们的促销价算。
       group: 层级名（如 "自营低价款"），写在表上方作小标题；按层级分组时每组调一次。"""
    if group: para(f'**{group}**', size=9, after=2)
    rows = []
    for x in items:
        rv = x.get('reviews')
        rt = f"{float(x['rating']):.1f}" if x.get('rating') else '—'
        if rv not in (None, '', 'None'): rt += f"\n{float(rv):,.0f} 条"  # 没有评论数（如 Amazon 导出）只写评分
        s = float(x.get('sales') or 0)
        sales = f'{s:,.0f}' if s >= 10 or s == 0 else f'{s:.1f}'
        rows.append([img_cell(x['img']) if x.get('img') else '',
                     link_cell([f"**{x.get('brand') or ''}**", f"型号：{x['pid']}", _html.unescape(x.get('title') or '')[:48]],
                               x.get('link') or link_of(x['ch'], x['pid'])),
                     usd(x['price']), rt, sales, x.get('config', ''), vs.get(x['pid'], '')])
    return table(['主图', '品牌 · 型号 · 链接', '售价', '评分\n评论数', '月销', '配置', '和我们比'], rows,
                 [2.3, 4.2, 1.4, 1.6, 1.3, 2.8, 4.2], size=7.5, aligns=[None, None, C_, C_, C_, None, None])


def forecast_text(name, pid, price, sales, rating, config, est):
    """发布文件"直接竞对与估算"固定 4 行。"""
    return f'直接竞对：{name}（{pid}）\n价格 {price}｜月销 {sales}｜评分 {rating}\n配置：{config}\n估算：{est}'


def save(path, pdf=True):
    doc.save(path)
    if pdf:
        subprocess.run(['soffice', '--headless', '--convert-to', 'pdf', '--outdir', os.path.dirname(os.path.abspath(path)), path],
                       capture_output=True)
    return path

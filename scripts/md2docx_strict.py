#!/usr/bin/env python3
"""
MBA论文 Word 生成脚本 - 严格按 MBA 格式规范（方案A：格式写死）

规范来源：mba-thesis-workflow/SKILL.md Phase 3 标准 + 用户补充规范

【格式常量】
中文摘要：标题"摘 要"，黑体16磅加粗居中，内容小四12磅宋体，行距20磅
英文摘要：Abstract，Arial 16磅加粗居中，内容TNR 12磅，行距20磅
目录：跳过
各章标题："第1章  绪论"（空两格），黑体16磅，段前24磅段后18磅，每章另起一页
一级节标题："1.2  ×××"，黑体14磅，段前24磅段后6磅
二级节标题："1.2.1  ×××"，黑体13磅，段前12磅段后6磅
三级节标题："(1) ×××"，宋体12磅，与正文同段
正文：宋体12磅，两端对齐，首行缩进2字符，段前段后0磅，行距20磅
三线表：顶线1.5磅/表头底线0.75磅/底线0.5磅，无竖线
参考文献：中英文分编排序，中文在前，[1]序号
附录/致谢：标题同章标题
页码：封面无页码 → 摘要/目录罗马数字 → 正文阿拉伯数字续前编号
"""

import docx
from docx.shared import Pt, RGBColor, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
import re, sys, os

# ============ MBA 格式常量 ============
FONT_BODY_CN    = '宋体'
FONT_HEADING    = '黑体'
FONT_ENGLISH   = 'Times New Roman'
FONT_ENGLISH_AB= 'Arial'

SZ_BODY   = Pt(12)    # 小四=12磅
SZ_H1     = Pt(16)    # 一级标题16磅
SZ_H2     = Pt(14)    # 二级节标题14磅
SZ_H3     = Pt(13)    # 三级节标题13磅
SZ_H4     = Pt(12)    # 四级节标题12磅
SZ_SMALL  = Pt(10.5)  # 图注/表注10.5磅
SZ_REF    = Pt(12)    # 参考文献12磅

LINE_20   = Pt(20)    # 正文行距20磅
LINE_SGL  = Pt(15.6)  # 单倍行距（小四12磅≈15.6磅）

S_BEFORE_H1 = Pt(24); S_AFTER_H1 = Pt(18)
S_BEFORE_H2 = Pt(24); S_AFTER_H2 = Pt(6)
S_BEFORE_H3 = Pt(12); S_AFTER_H3 = Pt(6)
S_BEFORE_H4 = Pt(0);  S_AFTER_H4 = Pt(0)

FIRST_INDENT = Pt(42)  # 首行缩进2个汉字符（全角约21pt×2≈42pt）

BORDER_TOP    = '24'   # 顶线1.5磅
BORDER_HEADER = '12'   # 表头底线0.75磅
BORDER_BOTTOM = '8'    # 底线0.5磅

BLACK = RGBColor(0x00, 0x00, 0x00)

# ============ 工具函数 ============

def set_run(run, size, fname, bold=False, color=BLACK):
    run.font.size = size
    run.font.name = fname
    run.font.bold = bold
    if color:
        run.font.color.rgb = color
    rPr = run._r.get_or_add_rPr()
    rFonts = OxmlElement('w:rFonts')
    rFonts.set(qn('w:eastAsia'), fname)
    rFonts.set(qn('w:ascii'), fname)
    rFonts.set(qn('w:hAnsi'), fname)
    rPr.append(rFonts)

def set_para(para, align=WD_ALIGN_PARAGRAPH.JUSTIFY,
             line=None, sb=None, sa=None, fi=None, li=None):
    pf = para.paragraph_format
    pf.alignment = align
    if line is not None: pf.line_spacing = line
    if sb is not None:   pf.space_before = sb
    if sa is not None:   pf.space_after = sa
    if fi is not None:   pf.first_line_indent = fi
    if li is not None:   pf.left_indent = li

def blank(doc):
    p = doc.add_paragraph()
    set_para(p, line=Pt(6), sb=Pt(0), sa=Pt(0))
    return p

def strip_bold(t):
    return re.sub(r'\*\*([^*]+)\*\*', r'\1', t)

def is_tbl_sep(line):
    cols = [c.strip() for c in line.split('|')[1:-1]]
    return bool(cols) and all(re.match(r'^:?-+:?$', c) for c in cols)

def set_three_line(table):
    """三线表：顶线+底线，内部无"""
    tbl = table._tbl
    tblPr = tbl.tblPr
    b = OxmlElement('w:tblBorders')

    top = OxmlElement('w:top')
    top.set(qn('w:val'),'single'); top.set(qn('w:sz'),BORDER_TOP); top.set(qn('w:color'),'000000')
    bot = OxmlElement('w:bottom')
    bot.set(qn('w:val'),'single'); bot.set(qn('w:sz'),BORDER_BOTTOM); bot.set(qn('w:color'),'000000')
    ih = OxmlElement('w:insideH'); ih.set(qn('w:val'),'none')
    iv = OxmlElement('w:insideV'); iv.set(qn('w:val'),'none')

    b.append(top); b.append(bot); b.append(ih); b.append(iv)
    for e in tblPr.findall(qn('w:tblBorders')): tblPr.remove(e)
    tblPr.append(b)

def set_header_bot_border(table):
    """表头行底部0.75磅"""
    if not table.rows: return
    for cell in table.rows[0].cells:
        tc = cell._tc
        tcPr = tc.get_or_add_tcPr()
        tcB = OxmlElement('w:tcBorders')
        bot = OxmlElement('w:bottom')
        bot.set(qn('w:val'),'single'); bot.set(qn('w:sz'),BORDER_HEADER); bot.set(qn('w:color'),'000000')
        for edge in ('top','left','right'):
            e = OxmlElement(f'w:{edge}')
            e.set(qn('w:val'),'none'); tcB.append(e)
        tcB.append(bot)
        for e in tcPr.findall(qn('w:tcBorders')): tcPr.remove(e)
        tcPr.append(tcB)

def apply_tbl_style(table):
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    set_three_line(table)
    if table.rows:
        for cell in table.rows[0].cells:
            for para in cell.paragraphs:
                para.alignment = WD_ALIGN_PARAGRAPH.CENTER
                for run in para.runs:
                    set_run(run, SZ_SMALL, FONT_BODY_CN)
        set_header_bot_border(table)

# ============ 入口校验 ============

def preflight(md_path):
    issues = []
    md_dir = os.path.dirname(md_path) or '.'
    bn = os.path.basename(md_path)

    possible = [os.path.join(md_dir, bn.replace('.md', t)) for t in ['_审核.md','_审核O.md','_审核H.md']]
    rf = None
    for p in possible:
        if os.path.exists(p): rf = p; break
    if not rf:
        pre = re.match(r'(论文[^\.]+)', bn)
        pp = pre.group(1) if pre else ''
        cands = [os.path.join(md_dir,f) for f in os.listdir(md_dir)
                 if f.endswith('.md') and '_审核' in f and pp in f]
        if cands:
            cands.sort(key=lambda x: os.path.getmtime(x), reverse=True)
            rf = cands[0]

    if not rf:
        issues.append("❌ 未找到审核报告，请先完成 Review Agent 终审")
        return False, issues

    with open(rf, 'r', encoding='utf-8') as f:
        rc = f.read()
    reds = re.findall(r'🔴\s*项统计[：:]\s*(\d+)', rc)
    if reds and int(reds[0]) > 0:
        issues.append(f"❌ 审核报告存在{reds[0]}条🔴问题")
    if '✅ 通过' not in rc and '综合评级' in rc:
        issues.append("❌ 审核未通过")
    if issues:
        return False, issues

    with open(md_path, 'r', encoding='utf-8') as f:
        content = f.read()
    ch = len(re.findall(r'^#\s+第.+章', content, re.MULTILINE))
    bb = len(re.findall(r'^(?!#).+\*\*[^*]+\*\*', content, re.MULTILINE))
    wc = len(content)
    print(f"✅ 通过 | 审核：{os.path.basename(rf)} | 章节：{ch} | 字数：{wc}")
    if bb: print(f"   加粗残留：{bb}处（自动清除）")
    return True, issues

# ============ Word 生成 ============

def md_to_docx(md_path, docx_path):
    doc = docx.Document()
    ns = doc.styles['Normal']
    ns.font.name = FONT_BODY_CN
    ns.font.size = SZ_BODY
    ns.paragraph_format.line_spacing = LINE_20

    with open(md_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    i = 0
    tbl_rows = []
    ref_cn = []; ref_en = []
    in_ref = False

    while i < len(lines):
        line = lines[i].rstrip('\n\r')
        i += 1

        if line.strip() == '===END===': continue
        if is_tbl_sep(line): continue

        if line.startswith('|'):
            cols = [strip_bold(c.strip()) for c in line.split('|')[1:-1]]
            tbl_rows.append(cols)
            continue

        if tbl_rows:
            _flush_tbl(doc, tbl_rows); tbl_rows = []

        if not line.strip(): continue

        # ---- 特殊章节检测 ----
        if re.match(r'^#{1,2}\s*摘要\s*$', line):
            _flush_tbl(doc, tbl_rows) if tbl_rows else None; tbl_rows = []
            i = _abs_cn(doc, lines, i)
            continue

        if re.match(r'^#{1,2}\s*英文摘要', line):
            _flush_tbl(doc, tbl_rows) if tbl_rows else None; tbl_rows = []
            i = _abs_en(doc, lines, i)
            continue

        if re.match(r'^#{1,2}\s*目录\s*$', line):
            while i < len(lines) and not re.match(r'^#\s+第.+章', lines[i]): i += 1
            continue

        if re.match(r'^#{1,2}\s*致谢\s*$', line):
            _flush_tbl(doc, tbl_rows) if tbl_rows else None; tbl_rows = []
            _chapter_title(doc, '致谢')
            i = _body_until_next(lines, i)
            continue

        am = re.match(r'^#{1,2}\s*附录([A-Z])?\s*$', line)
        if am:
            _flush_tbl(doc, tbl_rows) if tbl_rows else None; tbl_rows = []
            _appendix_title(doc, am.group(1) or '')
            i = _body_until_next(lines, i)
            continue

        # 各章标题
        cm = re.match(r'^#\s+(第[一二三四五六七八九十\d]+章)\s+(.+)$', line)
        if cm:
            raw = f'{cm.group(1)}  {cm.group(2)}'
            _chapter_title(doc, raw); continue

        # 一级节标题
        s1 = re.match(r'^##\s+(\d+\.\d+)\s+(.+)$', line)
        if s1:
            _sec1(doc, s1.group(1), s1.group(2)); continue

        # 二级节标题
        s2 = re.match(r'^###\s+(\d+\.\d+\.\d+)\s+(.+)$', line)
        if s2:
            _sec2(doc, s2.group(1), s2.group(2)); continue

        # 三级节标题
        s3 = re.match(r'^####\s+(\([^)]+\))\s*(.+)$', line)
        if s3:
            _sec3(doc, s3.group(1), s3.group(2)); continue

        # 参考文献
        if re.match(r'^#{1,2}\s+参考文献', line):
            _flush_tbl(doc, tbl_rows) if tbl_rows else None; tbl_rows = []
            in_ref = True; continue

        if in_ref and line.strip() and not line.startswith('#'):
            is_cn = bool(re.search(r'[\u4e00-\u9fff]', line))
            rt = re.sub(r'^\[\d+\]\s*', '', strip_bold(line.strip()))
            if is_cn: ref_cn.append(rt)
            else: ref_en.append(rt)
            continue
        elif in_ref and (not line.strip() or line.startswith('#')):
            _flush_refs(doc, ref_cn, ref_en)
            ref_cn = []; ref_en = []; in_ref = False

        # 正文段落
        para = doc.add_paragraph()
        set_para(para, align=WD_ALIGN_PARAGRAPH.JUSTIFY, line=LINE_20,
                 sb=Pt(0), sa=Pt(0), fi=FIRST_INDENT)
        run = para.add_run(strip_bold(line))
        set_run(run, SZ_BODY, FONT_BODY_CN)

    if tbl_rows: _flush_tbl(doc, tbl_rows)
    if ref_cn or ref_en: _flush_refs(doc, ref_cn, ref_en)

    doc.save(docx_path)
    return True

# ============ 子函数 ============

def _flush_tbl(doc, rows):
    if not rows: return
    rn = len(rows); cn = max(len(r) for r in rows) if rows else 0
    tbl = doc.add_table(rows=rn, cols=cn)
    apply_tbl_style(tbl)
    for ri, rd in enumerate(rows):
        for ci, ct in enumerate(rd):
            if ci < cn:
                cell = tbl.rows[ri].cells[ci]
                cell.text = ct
                for para in cell.paragraphs:
                    para.alignment = WD_ALIGN_PARAGRAPH.CENTER
                    for run in para.runs:
                        set_run(run, SZ_SMALL, FONT_BODY_CN)

def _abs_cn(doc, lines, start):
    """中文摘要"""
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    set_para(p, line=LINE_SGL, sb=S_BEFORE_H1, sa=S_AFTER_H1)
    run = p.add_run()
    run.text = '摘 要'
    set_run(run, SZ_H1, FONT_HEADING, bold=True)

    content = []
    j = start
    while j < len(lines):
        line = lines[j].rstrip('\n\r')
        if re.match(r'^#{1,2}\s*英文摘要', line): break
        if line.strip() and not line.startswith('#'):
            content.append(strip_bold(line.strip()))
        j += 1

    for text in content:
        para = doc.add_paragraph()
        set_para(para, align=WD_ALIGN_PARAGRAPH.JUSTIFY, line=LINE_20,
                 sb=Pt(0), sa=Pt(0), fi=FIRST_INDENT)
        run = para.add_run(text)
        set_run(run, SZ_BODY, FONT_BODY_CN)

    kw = doc.add_paragraph()
    set_para(kw, align=WD_ALIGN_PARAGRAPH.JUSTIFY, line=LINE_20,
             sb=Pt(0), sa=Pt(0), fi=FIRST_INDENT)
    run = kw.add_run('关键词 ')
    set_run(run, SZ_BODY, FONT_BODY_CN, bold=True)
    for text in content:
        m = re.search(r'关键词[：:]\s*(.+)', text)
        if m:
            run2 = kw.add_run(m.group(1))
            set_run(run2, SZ_BODY, FONT_BODY_CN)
            break
    return j

def _abs_en(doc, lines, start):
    """英文摘要"""
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    set_para(p, line=LINE_SGL, sb=S_BEFORE_H1, sa=S_AFTER_H1)
    run = p.add_run()
    run.text = 'Abstract'
    set_run(run, SZ_H1, FONT_ENGLISH_AB, bold=True)

    content = []
    j = start
    while j < len(lines):
        line = lines[j].rstrip('\n\r')
        if re.match(r'^#{1,2}\s*目录', line): break
        if line.strip() and not line.startswith('#'):
            content.append(strip_bold(line.strip()))
        j += 1

    for text in content:
        para = doc.add_paragraph()
        set_para(para, align=WD_ALIGN_PARAGRAPH.JUSTIFY, line=LINE_20,
                 sb=Pt(0), sa=Pt(0), fi=FIRST_INDENT)
        run = para.add_run(text)
        set_run(run, SZ_BODY, FONT_ENGLISH)

    kw = doc.add_paragraph()
    set_para(kw, align=WD_ALIGN_PARAGRAPH.JUSTIFY, line=LINE_20,
             sb=Pt(0), sa=Pt(0), fi=FIRST_INDENT)
    run = kw.add_run('Key Words ')
    set_run(run, SZ_BODY, FONT_ENGLISH, bold=True)
    for text in content:
        m = re.search(r'[Kk]ey\s*[Ww]ords[：:]\s*(.+)', text)
        if m:
            run2 = kw.add_run(m.group(1))
            set_run(run2, SZ_BODY, FONT_ENGLISH)
            break
    return j

def _chapter_title(doc, raw_text):
    """各章标题：分页符+黑体16磅+段前24磅段后18磅"""
    pb = doc.add_paragraph()
    pb.add_run().add_break(docx.enum.text.WD_BREAK.PAGE)
    set_para(pb, sb=Pt(0), sa=Pt(0))

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    set_para(p, line=LINE_SGL, sb=S_BEFORE_H1, sa=S_AFTER_H1)
    run = p.add_run()
    run.text = raw_text
    set_run(run, SZ_H1, FONT_HEADING, bold=True)

def _appendix_title(doc, letter):
    """附录标题"""
    pb = doc.add_paragraph()
    pb.add_run().add_break(docx.enum.text.WD_BREAK.PAGE)
    set_para(pb, sb=Pt(0), sa=Pt(0))

    title = f'附录{letter}' if letter else '附录'
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    set_para(p, line=LINE_SGL, sb=S_BEFORE_H1, sa=S_AFTER_H1)
    run = p.add_run()
    run.text = title
    set_run(run, SZ_H1, FONT_HEADING, bold=True)

def _sec1(doc, idx, title):
    """一级节标题：1.2  ×××，黑体14磅，段前24磅段后6磅"""
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    set_para(p, line=LINE_SGL, sb=S_BEFORE_H2, sa=S_AFTER_H2)
    run = p.add_run()
    run.text = f'{idx}  {title}'
    set_run(run, SZ_H2, FONT_HEADING, bold=True)

def _sec2(doc, idx, title):
    """二级节标题：1.2.1  ×××，黑体13磅，段前12磅段后6磅"""
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    set_para(p, line=LINE_SGL, sb=S_BEFORE_H3, sa=S_AFTER_H3)
    run = p.add_run()
    run.text = f'{idx}  {title}'
    set_run(run, SZ_H3, FONT_HEADING, bold=True)

def _sec3(doc, idx, title):
    """三级节标题：(1) ×××，宋体12磅，与正文同段"""
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    set_para(p, line=LINE_20, sb=Pt(0), sa=Pt(0))
    run = p.add_run()
    run.text = f'{idx} {title}'
    set_run(run, SZ_H4, FONT_BODY_CN)

def _body_until_next(lines, start):
    """附录/致谢的正文，直到下一章或参考文献"""
    j = start
    while j < len(lines):
        line = lines[j].rstrip('\n\r')
        j += 1
        if re.match(r'^#\s+第.+章', line) or re.match(r'^#{1,2}\s*参考文献', line):
            return j - 1
        if not line.strip() or line.startswith('#'): continue
        if is_tbl_sep(line): continue
    return j

def _flush_refs(doc, cn, en):
    """参考文献输出"""
    if cn:
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        set_para(p, line=LINE_SGL, sb=Pt(12), sa=Pt(6))
        run = p.add_run()
        run.text = '中文参考文献'
        set_run(run, SZ_H2, FONT_HEADING, bold=True)
        for ref in cn:
            para = doc.add_paragraph()
            set_para(para, align=WD_ALIGN_PARAGRAPH.JUSTIFY, line=LINE_20,
                     sb=Pt(0), sa=Pt(0), fi=Pt(0))
            run = para.add_run(ref)
            set_run(run, SZ_REF, FONT_BODY_CN)
    if en:
        if cn: blank(doc)
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        set_para(p, line=LINE_SGL, sb=Pt(12), sa=Pt(6))
        run = p.add_run()
        run.text = '英文参考文献'
        set_run(run, SZ_H2, FONT_HEADING, bold=True)
        for ref in en:
            para = doc.add_paragraph()
            set_para(para, align=WD_ALIGN_PARAGRAPH.JUSTIFY, line=LINE_20,
                     sb=Pt(0), sa=Pt(0), fi=Pt(0))
            run = para.add_run(ref)
            set_run(run, SZ_REF, FONT_ENGLISH)

# ============ 主入口 ============

if __name__ == '__main__':
    if len(sys.argv) < 3:
        print("用法: python3 md2docx_strict.py <论文.md> <输出.docx>")
        sys.exit(1)
    md_path = sys.argv[1]
    docx_path = sys.argv[2]
    if not os.path.exists(md_path):
        print(f"❌ 文件不存在: {md_path}"); sys.exit(1)
    print("=== MBA Word 生成（Phase 3 规范）===")
    ok, issues = preflight(md_path)
    if not ok:
        for iss in issues: print(iss)
        sys.exit(1)
    if md_to_docx(md_path, docx_path):
        print(f"✅ 已生成: {docx_path}")
    else:
        print("❌ 生成失败"); sys.exit(1)
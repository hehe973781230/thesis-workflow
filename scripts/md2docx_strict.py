#!/usr/bin/env python3
"""
MBA论文 Word 转换脚本 - 严格按格式规范
- 中文字体：宋体/黑体
- 英文字体：Times New Roman
- 三线表（无竖线）
- 每章后插入分页符
- 行距20磅
"""

from docx import Document
from docx.shared import Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.ns import qn, nsmap
from docx.oxml import OxmlElement
import re
import sys

def is_chinese(char):
    """判断是否为中文字符"""
    if isinstance(char, str):
        return '\u4e00' <= char <= '\u9fff' or '\u3000' <= char <= '\u303f'
    return False

def is_english(char):
    """判断是否为英文（拉丁）字符"""
    if isinstance(char, str):
        # 拉丁字母（英文）
        if 'a' <= char <= 'z' or 'A' <= char <= 'Z':
            return True
        # 数字也当作英文处理
        if '0' <= char <= '9':
            return True
        return False
    return False

def has_chinese(text):
    """判断文本是否包含中文"""
    return any(is_chinese(c) for c in text)

def split_chinese_english(text):
    """将文本拆分为中文和英文部分"""
    if not text:
        return []
    
    segments = []
    current_lang = None
    current_text = []
    
    for char in text:
        is_cn = is_chinese(char)
        is_en = is_english(char)
        
        if current_lang is None:
            current_lang = 'chinese' if is_cn else 'english'
        
        if is_en and current_lang == 'chinese':
            segments.append((current_lang, ''.join(current_text)))
            current_lang = 'english'
            current_text = [char]
        elif is_cn and current_lang == 'english':
            segments.append((current_lang, ''.join(current_text)))
            current_lang = 'chinese'
            current_text = [char]
        else:
            current_text.append(char)
    
    if current_text:
        segments.append((current_lang, ''.join(current_text)))
    
    return segments

def set_run_font(run, font_name, font_size, bold=False):
    """设置 run 的字体和字号"""
    run.font.name = font_name
    run.font.size = Pt(font_size)
    run.font.bold = bold
    try:
        run._element.rPr.rFonts.set(qn('w:eastAsia'), font_name)
    except:
        pass

def add_chinese_run(para, text, font_size=12, bold=False):
    """添加中文 run"""
    run = para.add_run(text)
    set_run_font(run, '宋体', font_size, bold)
    return run

def add_english_run(para, text, font_size=12, bold=False):
    """添加英文 run"""
    run = para.add_run(text)
    set_run_font(run, 'Times New Roman', font_size, bold)
    return run

def add_mixed_run(para, text, font_size=12, bold=False, default_font='宋体'):
    """添加混合文本 run，自动分离中英文"""
    segments = split_chinese_english(text)
    for lang, seg_text in segments:
        if lang == 'chinese':
            add_chinese_run(para, seg_text, font_size, bold)
        else:
            add_english_run(para, seg_text, font_size, bold)

def add_mixed_run_with_title_font(para, text, font_size=12, bold=False):
    """添加混合文本 run，标题字体使用黑体"""
    segments = split_chinese_english(text)
    for lang, seg_text in segments:
        if lang == 'chinese':
            run = para.add_run(seg_text)
            run.font.name = '黑体'
            run.font.size = Pt(font_size)
            run.font.bold = bold
            try:
                run._element.rPr.rFonts.set(qn('w:eastAsia'), '黑体')
            except:
                pass
        else:
            add_english_run(para, seg_text, font_size, bold)

def set_table_borders(table):
    """设置三线表边框"""
    tbl = table._tbl
    tblPr = tbl.tblPr if tbl.tblPr is not None else OxmlElement('w:tblPr')
    
    # 创建 tblBorders
    tblBorders = OxmlElement('w:tblBorders')
    
    # 顶线（最粗）
    top = OxmlElement('w:top')
    top.set(qn('w:val'), 'single')
    top.set(qn('w:sz'), '12')  # 1.5磅 = 12 half-points
    top.set(qn('w:space'), '0')
    top.set(qn('w:color'), 'auto')
    
    # 底线（中等）
    bottom = OxmlElement('w:bottom')
    bottom.set(qn('w:val'), 'single')
    bottom.set(qn('w:sz'), '6')  # 0.75磅
    bottom.set(qn('w:space'), '0')
    bottom.set(qn('w:color'), 'auto')
    
    # 表头底线（介于顶线和底线之间）
    insideH = OxmlElement('w:insideH')
    insideH.set(qn('w:val'), 'single')
    insideH.set(qn('w:sz'), '6')
    insideH.set(qn('w:space'), '0')
    insideH.set(qn('w:color'), 'auto')
    
    insideV = OxmlElement('w:insideV')
    insideV.set(qn('w:val'), 'single')
    insideV.set(qn('w:sz'), '6')
    insideV.set(qn('w:space'), '0')
    insideV.set(qn('w:color'), 'auto')
    
    tblBorders.append(top)
    tblBorders.append(bottom)
    tblBorders.append(insideH)
    tblBorders.append(insideV)
    
    tblPr.append(tblBorders)
    tbl.insert(0, tblPr)

def process_markdown_to_docx(input_file, output_file):
    """处理 markdown 文件并输出 docx"""
    
    with open(input_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    lines = content.split('\n')
    
    doc = Document()
    
    # 设置默认样式
    doc.styles['Normal'].font.size = Pt(12)
    
    i = 0
    while i < len(lines):
        line = lines[i].rstrip()
        
        if not line:
            i += 1
            continue
        
        # ===== 章节标题处理 =====
        if line.startswith('# 第'):
            # 第X章标题 - 黑体16磅居中加粗，每章后插入分页符
            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            # 移除 # 标记
            title_text = line.replace('# ', '')
            add_mixed_run_with_title_font(p, title_text, font_size=16, bold=True)
            doc.add_page_break()
        
        elif line.startswith('## '):
            # 一级节标题 - 黑体14磅左对齐加粗
            p = doc.add_paragraph()
            title_text = line.replace('## ', '')
            add_mixed_run_with_title_font(p, title_text, font_size=14, bold=True)
        
        elif line.startswith('### '):
            # 二级节标题 - 黑体13磅
            p = doc.add_paragraph()
            title_text = line.replace('### ', '')
            add_mixed_run_with_title_font(p, title_text, font_size=13, bold=True)
        
        elif line.startswith('#### '):
            # 三级节标题 - 宋体12磅
            p = doc.add_paragraph()
            title_text = line.replace('#### ', '')
            add_mixed_run(p, title_text, font_size=12, bold=False)
        
        # ===== 表格处理 =====
        elif line.startswith('|') and '---' not in line:
            # 收集所有连续表格行
            table_rows = []
            while i < len(lines) and lines[i].strip().startswith('|') and '---' not in lines[i]:
                row_str = lines[i].strip()
                cells = [c.strip() for c in row_str.split('|')[1:-1]]
                if cells and any(c for c in cells):
                    table_rows.append(cells)
                i += 1
            
            if table_rows:
                cols = max(len(row) for row in table_rows) if table_rows else 0
                if cols > 0:
                    # 创建表格
                    table = doc.add_table(rows=len(table_rows), cols=cols)
                    table.alignment = WD_TABLE_ALIGNMENT.CENTER
                    
                    # 设置三线表边框
                    set_table_borders(table)
                    
                    for r_idx, row_data in enumerate(table_rows):
                        for c_idx, cell_data in enumerate(row_data):
                            if c_idx < cols:
                                cell = table.rows[r_idx].cells[c_idx]
                                cell.text = ''
                                para = cell.paragraphs[0]
                                
                                # 表头行加粗
                                is_header = (r_idx == 0)
                                
                                # 添加单元格内容
                                add_mixed_run(para, cell_data, font_size=10.5, bold=is_header)
                                para.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.CENTER
                    
                    doc.add_paragraph()
            continue
        
        # ===== 正文段落处理 =====
        else:
            # 移除 markdown 加粗标记
            clean_line = re.sub(r'\*\*(.+?)\*\*', r'\1', line)
            
            p = doc.add_paragraph()
            p.paragraph_format.line_spacing = Pt(20)
            p.paragraph_format.space_before = Pt(0)
            p.paragraph_format.space_after = Pt(0)
            
            add_mixed_run(p, clean_line, font_size=12, bold=False)
        
        i += 1
    
    # 保存文件
    doc.save(output_file)
    print(f"✅ 文档已生成: {output_file}")

if __name__ == '__main__':
    if len(sys.argv) < 3:
        print("用法: python3 md2docx_strict.py <输入.md> <输出.docx>")
        sys.exit(1)
    
    input_file = sys.argv[1]
    output_file = sys.argv[2]
    
    process_markdown_to_docx(input_file, output_file)
#!/usr/bin/env python3
"""
outline_parser.py - 目录解析器 v1.0
基于 v1.2 算法（3样本验证），支持固定规则 + AI兜底 + 手动输入三层解析
"""

import re
import docx
import json
import xml.etree.ElementTree as ET
from typing import Optional, Tuple, List, Dict, Any
from collections import Counter

# ============================================================
# 固定规则层（v1.2 通用正则，已在3样本验证）
# ============================================================

# 一级章节：第X章 或 第[中文]章（空格容忍0或多个）
CH1_PATTERN = re.compile(r'^\s*第(\d+|[一二三四五六七八九十]+)章\s*(.+)$')

# 二级章节：X.Y（空格容忍0或多个）
CH2_PATTERN = re.compile(r'^\s*(\d+)\.(\d+)\s*(\S.*)$')

# 三级章节：X.Y.Z（空格容忍0或多个）
CH3_PATTERN = re.compile(r'^\s*(\d+)\.(\d+)\.(\d+)\s*(\S.*)$')

# 大纲锚点（起始/终止）
OUTLINE_START_ANCHORS = ["论文大纲", "目录", "目  录", "目 录"]
OUTLINE_END_ANCHOR = "参考文献"

# 中文数字转换
CHINESE_TO_INT = {
    '一': 1, '二': 2, '三': 3, '四': 4, '五': 5,
    '六': 6, '七': 7, '八': 8, '九': 9, '十': 10
}

# 手动输入示例
MANUAL_INPUT_TEMPLATE = """
## 目录结构示例（请按此格式输入）

第1章 绪论
1.1 研究背景
1.1.1 行业背景
1.1.2 研究意义
1.2 研究内容
第2章 理论基础与文献综述
2.1 战略管理理论
2.1.1 企业战略概念
2.1.2 竞争战略理论
2.2 文献综述

（提示：
- 一级标题用"第X章"
- 二级用"X.Y"
- 三级用"X.Y.Z"
- 不要加#号或markdown格式）
"""


def to_int(s: str) -> int:
    """将字符串数字转为int"""
    if s.isdigit():
        return int(s)
    return CHINESE_TO_INT.get(s, 0)


def extract_text_from_docx(docx_path: str) -> List[Tuple[int, str, str]]:
    """
    从 docx 文件读取段落列表
    返回: [(段落索引, 样式名, 文本), ...]
    """
    try:
        doc = docx.Document(docx_path)
        return [(i, p.style.name, p.text) for i, p in enumerate(doc.paragraphs)]
    except Exception:
        # docx 损坏时回退到 XML 直接解析
        import zipfile
        try:
            with zipfile.ZipFile(docx_path, 'r') as z:
                with z.open('word/document.xml') as f:
                    xml_content = f.read().decode('utf-8')
        except Exception:
            return []
        
        ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
        root = ET.fromstring(xml_content)
        paragraphs = root.findall('.//w:p', ns)
        result = []
        for i, p in enumerate(paragraphs):
            se = p.find('.//w:pStyle', ns)
            style = se.get('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}val') if se is not None else 'Normal'
            text = ''.join(x.text or '' for x in p.findall('.//w:t', ns))
            result.append((i, style, text))
        return result


def extract_outline_from_text(text: str) -> Tuple[List[Dict], List[Dict]]:
    """
    从纯文本（粘贴的开题报告内容）中解析目录
    返回: (nodes_list, issues_list)
    """
    lines = text.strip().split('\n')
    return _parse_outline_lines(lines)


def extract_outline_from_docx(docx_path: str) -> Tuple[List[Dict], List[Dict]]:
    """
    从 docx 文件解析目录
    返回: (nodes_list, issues_list)
    """
    paragraphs = extract_text_from_docx(docx_path)
    
    # 定位大纲区
    start_idx = end_idx = None
    for i, (_, _, t) in enumerate(paragraphs):
        ts = t.strip()
        if start_idx is None and ts in OUTLINE_START_ANCHORS:
            start_idx = i
        elif start_idx is not None and ts == OUTLINE_END_ANCHOR:
            end_idx = i
            break
    
    if end_idx is None:
        end_idx = len(paragraphs)
    
    if start_idx is None:
        return [], [{"type": "no_anchor", "message": "未找到大纲锚点（论文大纲/目录）"}]
    
    # 解析章节
    lines = [p[2].strip() for p in paragraphs[start_idx + 1:end_idx]]
    return _parse_outline_lines(lines)


def _parse_outline_lines(lines: List[str]) -> Tuple[List[Dict], List[Dict]]:
    """
    核心解析逻辑（通用规则）
    返回: (nodes_list, issues_list)
    """
    tree = []
    issues = []
    
    current_ch1 = None
    current_ch2 = None
    
    for raw_line in lines:
        # strip 段首段尾空格，处理段首空格
        text = raw_line.strip()
        if not text:
            continue
        
        m3 = CH3_PATTERN.match(text)
        m2 = CH2_PATTERN.match(text)
        m1 = CH1_PATTERN.match(text)
        
        if m3:
            # 三级章节
            num = f"{m3.group(1)}.{m3.group(2)}.{m3.group(3)}"
            ch3 = {
                "level": 3,
                "num": num,
                "title": m3.group(4),
                "children": []
            }
            if current_ch2:
                current_ch2["children_ids"].append(num)
                current_ch2["children"].append(ch3)
            else:
                issues.append({
                    "type": "orphan_ch3",
                    "num": num,
                    "title": m3.group(4),
                    "message": f"三级章节 {num} 缺少父级二级章节"
                })
        elif m2:
            # 二级章节
            num = f"{m2.group(1)}.{m2.group(2)}"
            ch2 = {
                "level": 2,
                "num": num,
                "title": m2.group(3),
                "children_ids": [],
                "children": []
            }
            if current_ch1:
                current_ch1["children_ids"].append(num)
                current_ch2 = ch2
                current_ch1["children"].append(ch2)
            else:
                issues.append({
                    "type": "orphan_ch2",
                    "num": num,
                    "title": m2.group(3),
                    "message": f"二级章节 {num} 缺少父级章节"
                })
        elif m1:
            # 一级章节
            ch1_num = to_int(m1.group(1))
            ch1 = {
                "level": 1,
                "num": ch1_num,
                "title": m1.group(2),
                "children_ids": [],
                "children": []
            }
            current_ch1 = ch1
            current_ch2 = None
            tree.append(ch1)
    
    # 编号唯一性 + 连续性校验（v1.2 新增）
    issues.extend(_validate_numbering(tree))
    
    return tree, issues


def _validate_numbering(tree: List[Dict]) -> List[Dict]:
    """编号唯一性 + 连续性校验"""
    issues = []
    
    for ch1 in tree:
        # 一级编号唯一性
        # （tree本身已保证）
        
        l2_nums = [c["num"] for c in ch1["children"]]
        l2_dupes = [n for n, cnt in Counter(l2_nums).items() if cnt > 1]
        for n in l2_dupes:
            issues.append({
                "type": "L2_duplicate",
                "path": n,
                "chapter": ch1["title"],
                "message": f"二级编号 {n} 在 {ch1['title']} 中重复"
            })
        
        for ch2 in ch1["children"]:
            l3_nums = [c["num"] for c in ch2["children"]]
            
            # 三级编号唯一性
            l3_dupes = [n for n, cnt in Counter(l3_nums).items() if cnt > 1]
            for n in l3_dupes:
                issues.append({
                    "type": "L3_duplicate",
                    "path": n,
                    "chapter": ch2["title"],
                    "message": f"三级编号 {n} 在 {ch2['title']} 中重复"
                })
            
            # 三级编号连续性
            expected = 1
            for ch3 in ch2["children"]:
                actual = int(ch3["num"].split('.')[-1])
                if actual != expected:
                    issues.append({
                        "type": "L3_not_continuous",
                        "actual": ch3["num"],
                        "expected": f"{ch2['num']}.{expected}",
                        "title": ch3["title"],
                        "message": f"三级编号 {ch3['num']} 不连续，期望 {ch2['num']}.{expected}"
                    })
                expected = actual + 1
    
    return issues


def build_outline_tree(tree: List[Dict], paper_title: str = None) -> Dict[str, Any]:
    """
    将嵌套树结构转为标准目录树JSON（含metadata和nodes_flatten）
    """
    nodes_flatten = []
    total_l1 = len(tree)
    total_l2 = sum(len(c["children"]) for c in tree)
    total_l3 = sum(len(c2["children"]) for c in tree for c2 in c["children"])
    
    def node_id(ch1_idx, ch2=None, ch3=None):
        if ch3:
            return ch3["num"]
        if ch2:
            return ch2["num"]
        return f"ch{ch1_idx + 1}"
    
    # 扁平化 + 构建兄弟关系
    prev_node_id = None
    for i, ch1 in enumerate(tree):
        nid = f"ch{i + 1}"
        nodes_flatten.append({
            "id": nid,
            "level": 1,
            "num": ch1["num"],
            "title": ch1["title"],
            "parent_id": None,
            "children_ids": ch1["children_ids"],
            "prev_sibling_id": prev_node_id,
            "next_sibling_id": None,
            "writing_status": "pending",
            "key_conclusion": None,
            "word_count": None
        })
        if prev_node_id:
            prev = nodes_flatten[-2]
            prev["next_sibling_id"] = nid
        prev_node_id = nid
        
        prev_l2_id = None
        for j, ch2 in enumerate(ch1["children"]):
            nid2 = ch2["num"]
            nodes_flatten.append({
                "id": nid2,
                "level": 2,
                "num": ch2["num"],
                "title": ch2["title"],
                "parent_id": f"ch{i + 1}",
                "children_ids": ch2["children_ids"],
                "prev_sibling_id": prev_l2_id,
                "next_sibling_id": None,
                "writing_status": "pending",
                "key_conclusion": None,
                "word_count": None
            })
            if prev_l2_id:
                idx = len(nodes_flatten) - 2
                nodes_flatten[idx]["next_sibling_id"] = nid2
            prev_l2_id = nid2
            
            prev_l3_id = None
            for k, ch3 in enumerate(ch2["children"]):
                nid3 = ch3["num"]
                nodes_flatten.append({
                    "id": nid3,
                    "level": 3,
                    "num": ch3["num"],
                    "title": ch3["title"],
                    "parent_id": nid2,
                    "children_ids": [],
                    "prev_sibling_id": prev_l3_id,
                    "next_sibling_id": None,
                    "writing_status": "pending",
                    "key_conclusion": None,
                    "word_count": None
                })
                if prev_l3_id:
                    nodes_flatten[-2]["next_sibling_id"] = nid3
                prev_l3_id = nid3
    
    return {
        "outline_tree": {
            "metadata": {
                "paper_title": paper_title,
                "total_l1": total_l1,
                "total_l2": total_l2,
                "total_l3": total_l3,
                "total_nodes": len(nodes_flatten),
                "created_at": None
            },
            "nodes": nodes_flatten
        }
    }


def outline_parse(text_or_docx: str, paper_title: str = None) -> Dict[str, Any]:
    """
    主入口：解析目录（文本或docx路径）
    返回标准目录树JSON
    
    解析失败返回: {"ok": False, "error": "...", "suggestion": "..."}
    """
    # 判断输入类型
    is_file = text_or_docx.strip().endswith('.docx') or \
              (len(text_or_docx) < 200 and text_or_docx.startswith('/'))
    
    if is_file:
        tree, issues = extract_outline_from_docx(text_or_docx)
    else:
        tree, issues = extract_outline_from_text(text_or_docx)
    
    if not tree:
        return {
            "ok": False,
            "error": "未解析到任何章节",
            "suggestion": MANUAL_INPUT_TEMPLATE
        }
    
    outline = build_outline_tree(tree, paper_title)
    
    return {
        "ok": True,
        "outline": outline,
        "issues": issues,
        "summary": {
            "l1": outline["outline_tree"]["metadata"]["total_l1"],
            "l2": outline["outline_tree"]["metadata"]["total_l2"],
            "l3": outline["outline_tree"]["metadata"]["total_l3"],
            "total": outline["outline_tree"]["metadata"]["total_nodes"]
        }
    }


def validate_manual_input(text: str) -> Dict[str, Any]:
    """
    验证用户手动输入的目录文本
    成功返回: {"ok": True, "outline": {...}}
    失败返回: {"ok": False, "error": "..."}
    """
    if not text or len(text.strip()) < 50:
        return {
            "ok": False,
            "error": "输入内容太少，至少需要包含完整的目录结构"
        }
    
    tree, issues = extract_outline_from_text(text)
    
    if not tree:
        error_msg = "未识别到任何章节，请检查格式是否正确"
        if issues:
            error_msg = issues[0].get("message", error_msg)
        return {
            "ok": False,
            "error": error_msg,
            "suggestion": MANUAL_INPUT_TEMPLATE
        }
    
    # 基本校验
    if len(tree) < 5:
        return {
            "ok": False,
            "error": f"章节数量太少（{len(tree)}章），至少需要5章，请检查输入是否完整"
        }
    
    # 有严重问题（编号重复）但有内容
    critical_issues = [i for i in issues if i.get("type") in ["L2_duplicate"]]
    if critical_issues:
        return {
            "ok": False,
            "error": f"发现编号重复问题：{critical_issues[0]['message']}",
            "suggestion": MANUAL_INPUT_TEMPLATE
        }
    
    outline = build_outline_tree(tree)
    return {
        "ok": True,
        "outline": outline,
        "issues": issues
    }


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("用法: python3 outline_parser.py <开题报告.docx 或 目录文本>")
        print("")
        print("测试样例:")
        print("  python3 outline_parser.py '/path/to/开题报告.docx'")
        print("  echo '第1章 绪论\\n1.1 研究背景' | python3 outline_parser.py")
        sys.exit(1)
    
    input_arg = sys.argv[1]
    result = outline_parse(input_arg)
    
    print(json.dumps(result, ensure_ascii=False, indent=2))

#!/usr/bin/env python3
"""
context_builder.py - Prompt 包生成器 v1.0
根据节点ID从目录树提取上下文，生成干净的写作 prompt 包
所有内容围绕目录动态生成，不写死
执行方式：严格串行（前置节点完成 → 后置节点才能生成）
"""

import re
import json
import os
from typing import Dict, Any, Optional, List
try:
    from .state_manager_v2 import outline_load, outline_get_node, outline_get_context
except ImportError:
    from state_manager_v2 import outline_load, outline_get_node, outline_get_context

try:
    from .outline_parser import build_outline_tree
except ImportError:
    from outline_parser import build_outline_tree


# ============================================================
# 动态主题推导（不写死，从节点标题推导）
# ============================================================

def extract_keyword(title: str) -> str:
    """从标题中提取核心关键词（去掉编号），注意顺序：先匹配三级，再匹配二级"""
    # 先去掉三级编号（如 1.1.1）
    t = re.sub(r'^\d+\.\d+\.\d+\s*', '', title)
    # 再去掉二级编号（如 1.1）
    t = re.sub(r'^\d+\.\d+\s*', '', t)
    # 最后去掉一级章节（如 第1章）
    t = re.sub(r'^第\d+章\s*', '', t)
    # 再处理中文数字章节
    t = re.sub(r'^第[一二三四五六七八九十]+章\s*', '', t)
    return t.strip()


def infer_topics(node: Dict, parent_node: Optional[Dict] = None) -> List[str]:
    """
    根据节点在目录树中的位置，动态推导分析维度
    不写死具体主题，只用通用推导规则
    """
    level = node.get("level", 0)
    title = node.get("title", "")
    keyword = extract_keyword(title)
    
    if level == 1:
        # 一级章节：内容由子节点决定，这里返回空
        return []
    
    elif level == 2:
        # 二级章节：根据标题关键词推导分析维度
        # 使用通用分析框架，不写死具体行业/公司相关内容
        
        if any(k in keyword for k in ["背景", "环境", "现状", "概述"]):
            return [
                "该领域的宏观环境与现状",
                "行业特征与竞争格局",
                "发展趋势与主要驱动因素"
            ]
        
        elif any(k in keyword for k in ["意义", "价值", "目的", "贡献"]):
            return [
                "理论层面的意义与贡献",
                "实践层面的应用价值"
            ]
        
        elif any(k in keyword for k in ["理论", "基础", "文献", "综述"]):
            return [
                "核心理论的定义与框架",
                "相关文献的主要观点",
                "理论在本研究中的应用"
            ]
        
        elif any(k in keyword for k in ["分析", "诊断", "评价"]):
            return [
                "该分析维度的核心内容",
                "在本研究中的具体应用",
                "分析结论与主要发现"
            ]
        
        elif any(k in keyword for k in ["战略", "选择", "制定", "定位"]):
            return [
                "战略目标与定位",
                "可选战略方案对比",
                "战略选择的依据与逻辑"
            ]
        
        elif any(k in keyword for k in ["实施", "保障", "措施", "计划"]):
            return [
                "实施路径与行动计划",
                "关键成功因素",
                "保障机制与资源配置"
            ]
        
        elif any(k in keyword for k in ["结论", "总结", "展望"]):
            return [
                "研究核心结论",
                "研究局限与未来方向"
            ]
        
        elif any(k in keyword for k in ["资源", "能力", "优势", "劣势", "核心竞争力"]):
            return [
                "资源/能力识别与分类",
                "核心资源/能力特征",
                "与战略目标的匹配度"
            ]
        
        elif any(k in keyword for k in ["威胁", "机会", "挑战", "SWOT"]):
            return [
                "内外部关键因素识别",
                "因素之间的关联分析",
                "战略启示"
            ]
        
        else:
            # 未知类型，返回标题本身作为分析方向
            return [keyword]
    
    elif level == 3:
        # 三级章节：直接返回节点标题作为分析方向
        return [keyword]
    
    return []


# ============================================================
# 承接段生成（基于 key_conclusion 实际内容，无则 null）
# ============================================================

def _truncate(text: str, max_len: int = 60) -> str:
    """截断文本到最大长度"""
    if not text:
        return ""
    text = text.strip()
    if len(text) <= max_len:
        return text
    return text[:max_len] + "..."


def _build_bridge_from_prev(prev: Dict, current: Dict, prev_conclusion: str) -> str:
    """基于前序节点的 key_conclusion 生成承接段"""
    prev_summary = _truncate(prev_conclusion, 60)
    return (
        f"在前文「{prev['title']}」中已阐明{prev_summary}，"
        f"本节将在此基础上深入探讨{current['title']}的具体内容。"
    )


def _build_bridge_from_parent(parent: Dict, current: Dict, parent_conclusion: str) -> str:
    """基于父节点的 key_conclusion 生成承接段"""
    parent_summary = _truncate(parent_conclusion, 60)
    return (
        f"在「{parent['title']}」章节中已指出{parent_summary}，"
        f"本节将进一步细化分析{current['title']}。"
    )


def _build_bridge_from_chapter_summary(prev_chapter_summary: Dict, current: Dict) -> str:
    """
    增强项1 P3 fallback：跨章节承接段生成

    当 P1（前序节点）和 P2（父节点）都拿不到 key_conclusion 时（如 2.1 是新章节首节点，
    前序 1.2 既不是 prev 也不是 parent），使用上一章节虚拟摘要节点作为承接依据。

    参数：
      prev_chapter_summary: {
        "chapter_id": "ch1",
        "chapter_title": "绪论",
        "key_conclusion": "本章系统梳理了..."  # 200-300 字摘要
      }
      current: 当前节点
    """
    summary_text = prev_chapter_summary.get("key_conclusion", "")
    if not summary_text:
        return None

    summary = _truncate(summary_text, 120)
    chapter_title = prev_chapter_summary.get("chapter_title", "上一章节")
    return (
        f"在「{chapter_title}」中，{summary}，"
        f"本章将在此基础上展开分析「{current.get('title', '本节')}」的具体内容。"
    )


def generate_bridge(context: Dict[str, Any]) -> Optional[str]:
    """
    根据前序节点的 key_conclusion 实际内容，生成承接段
    严格串行：前置节点未完成（无 key_conclusion）时返回 null

    优先级链（增强项1 P3 fallback）：
      P1: prev_node key_conclusion  → 同章节前序节点
      P2: parent_node key_conclusion → 父节点
      P3: prev_chapter_summary      → 上一章节虚拟摘要节点（跨章节首节点场景）
    """
    current = context.get("current_node", {})
    prev = context.get("prev_node")
    parent = context.get("parent_node")
    prev_chapter_summary = context.get("prev_chapter_summary")

    # 无任何上游上下文
    if not prev and not parent and not prev_chapter_summary:
        return None

    # P1: prev key_conclusion
    if prev:
        prev_conclusion = prev.get("key_conclusion")
        if prev_conclusion:
            return _build_bridge_from_prev(prev, current, prev_conclusion)

    # P2: parent key_conclusion
    if parent:
        parent_conclusion = parent.get("key_conclusion")
        if parent_conclusion:
            return _build_bridge_from_parent(parent, current, parent_conclusion)

    # P3 (增强项1): prev_chapter_summary
    if prev_chapter_summary:
        result = _build_bridge_from_chapter_summary(prev_chapter_summary, current)
        if result:
            return result

    # 前置节点未完成，无 key_conclusion，返回 null 让 NodeWriter 自行处理开头
    return None


# ============================================================
# 结尾提示生成（基于下一节点 title 动态生成）
# ============================================================

def generate_ending_hint(current: Dict, next_node: Optional[Dict] = None) -> str:
    """
    根据下一节点的 title 动态生成预告
    """
    if not next_node:
        return None  # 最后一个节点，无需预告
    
    next_title = next_node.get("title", "")
    next_level = next_node.get("level", 0)
    current_level = current.get("level", 0)
    
    if next_level == current_level:
        # 同级节点：并列关系
        return f"本节完成了「{current['title']}」的分析，下一节点「{next_title}」将从另一维度继续探讨。"
    elif next_level > current_level:
        # 进入子节点：递进关系
        return f"本节为「{current['title']}」的概述，下一节「{next_title}」将进行深入分析。"
    else:
        # 返回父节点或同级：总结关系
        return f"本节内容分析完毕，后续章节「{next_title}」将在此基础上进一步展开。"


# ============================================================
# 字数估算（给范围，不写死）
# ============================================================

def get_word_count_range(level: int) -> Dict[str, int]:
    """
    根据层级返回合理的字数范围
    """
    ranges = {
        1: {"min": 1500, "max": 3000},   # 一级章节：1500-3000字
        2: {"min": 600, "max": 1500},    # 二级章节：600-1500字
        3: {"min": 300, "max": 800},     # 三级章节：300-800字
    }
    return ranges.get(level, {"min": 500, "max": 1200})


# ============================================================
# 同级章节横向上下文注入（MECE 边界划定）
# ============================================================

def _get_node_status_tag(status: str) -> str:
    """根据节点状态返回标签"""
    if status == "completed":
        return "【已完成】"
    elif status == "writing":
        return "【正在写】"
    else:
        return "【待写】"


def _infer_scope_boundary(current_node: Dict, sibling: Dict, parent_id: str) -> str:
    """
    根据当前节点和同级节点的标题语义，自动生成 MECE 边界界定。
    返回 "✅"（本章负责）或 "❌"（本章不负责）或 ""（无关）
    """
    current_title = current_node.get("title", "")
    sibling_title = sibling.get("title", "")

    # 通用互斥关键词对（语义互斥，同级章节不会重复）
    # 如果当前节点和同级节点都包含同一高层级关键词，说明有边界重叠风险
    mutex_pairs = [
        # SWOT 内部互斥
        (["优势", "strength"], ["劣势", "weakness"]),
        (["机会", "opportunity"], ["威胁", "threat"]),
        # 战略选择类互斥
        (["成本领先", "cost leadership"], ["差异化", "differentiation"]),
        (["集中化", "focus", "集中"], ["成本领先", "差异化"]),
        # 实施类互斥
        (["实施", "路径", "行动计划"], ["保障", "组织架构", "资源配置"]),
        # 结论类
        (["结论", "总结"], ["背景", "现状", "分析"]),
    ]

    def contains_any(text: str, keywords: list) -> bool:
        return any(k.lower() in text.lower() for k in keywords)

    for pos_kw, neg_kw in mutex_pairs:
        current_has_pos = contains_any(current_title, pos_kw)
        sibling_has_neg = contains_any(sibling_title, neg_kw)
        sibling_has_pos = contains_any(sibling_title, pos_kw)
        current_has_neg = contains_any(current_title, neg_kw)

        # 如果同级章节包含当前章节的"不应该写"的关键词 → 标记 ❌
        if current_has_pos and sibling_has_neg:
            return "❌"
        if current_has_neg and sibling_has_pos:
            return "❌"

    # L2 节点：检查是否有明显的边界重叠
    # 例如：5.1 SWOT分析 和 5.2 竞争战略选择 → 5.1 负责分析，5.2 负责选择
    overlap_pairs = [
        (["swot", "分析"], ["战略", "选择", "定位"]),
        (["内部", "环境", "资源", "能力"], ["外部", "环境", "pestel", "五力"]),
        (["实施", "路径"], ["保障", "组织", "激励"]),
    ]

    for a_kw, b_kw in overlap_pairs:
        curr_in_a = contains_any(current_title, a_kw)
        sib_in_b = contains_any(sibling_title, b_kw)
        if curr_in_a and sib_in_b:
            return "✅"
        sib_in_a = contains_any(sibling_title, a_kw)
        curr_in_b = contains_any(current_title, b_kw)
        if sib_in_a and curr_in_b:
            return "❌"

    return ""


def build_sibling_chapter_context(paper_name: str, node_id: str) -> str:
    """
    构建同级章节预览上下文，用于 MECE 边界划定。

    返回格式化的字符串，供注入 prompt 使用。

    输出示例：
    【同级章节预览】（本章：5.1 SWOT分析）

     5.2 竞争战略选择
     → 方向：基于SWOT结论，对比成本领先/差异化/集中化三种战略优劣势

     5.3 战略实施路径
     → 方向：[无content_hint，仅标题]

    【本章范围界定】
     ✅ 5.1 负责：S/W/O/T四象限分析，各要素打分
     ❌ 5.2 负责：战略对比与选择结论（不要在5.1写最终战略结论）
     ❌ 5.3 负责：实施路径和执行细节（5.1 只需提出战略方向雏形）
    """
    # 动态导入避免循环依赖
    try:
        from .state_manager_v2 import outline_load, outline_get_node, outline_get_context
    except ImportError:
        from state_manager_v2 import outline_load, outline_get_node, outline_get_context

    state = outline_load(paper_name)
    if not state:
        return ""

    nodes = state.get("outline", {}).get("outline_tree", {}).get("nodes", [])
    if not nodes:
        # 兼容旧结构
        nodes = state.get("outline", {}).get("nodes", [])

    node_map = {n["id"]: n for n in nodes}
    current = node_map.get(node_id)
    if not current:
        return ""

    parent_id = current.get("parent_id")
    level = current.get("level", 0)

    # 确定父节点（用于找同级节点）
    if level == 1:
        # 一级章节：同级即其他一级章节
        siblings = [n for n in nodes if n.get("level") == 1 and n["id"] != node_id]
        parent_title = None
    else:
        # 非一级章节：通过 parent_id 找同级
        if parent_id:
            parent_node = node_map.get(parent_id)
            parent_title = parent_node["title"] if parent_node else None
            sibling_ids = parent_node.get("children_ids", []) if parent_node else []
            siblings = [node_map[sid] for sid in sibling_ids if sid in node_map and sid != node_id]
        else:
            siblings = []
            parent_title = None

    if not siblings:
        return ""

    lines = []
    chapter_label = f"（本章：{current['title']}）"
    if parent_title:
        chapter_label = f"（本章：{parent_title} / {current['title']}）"

    lines.append(f"【同级章节预览】{chapter_label}")
    lines.append("")

    # 收集边界界定
    scope_lines = []
    scope_lines.append("【本章范围界定】")

    for sibling in siblings:
        sid = sibling["id"]
        stitle = sibling["title"]
        hint = sibling.get("content_hint", "").strip()
        status = sibling.get("writing_status", "")
        status_tag = _get_node_status_tag(status)

        if hint:
            direction = f"方向：{hint}"
        else:
            direction = "方向：[无content_hint，仅标题]"

        lines.append(f" {sid} {stitle}")
        lines.append(f" → {direction} {status_tag}")
        lines.append("")

        # 自动生成边界界定
        boundary = _infer_scope_boundary(current, sibling, parent_id)
        if boundary:
            scope_lines.append(f" {boundary} {sid}：{stitle}")

    # 去重 + 保留空行
    scope_lines = [l for l in scope_lines if l.strip()]  # 去掉空行

    # 如果当前节点负责某项关键边界，加上自我说明
    # 检查 current 是否应该在 scope_lines 中
    current_has_responsibility = any(
        _infer_scope_boundary(sibling, current, parent_id) == "✅"
        for sibling in siblings
    )
    if current_has_responsibility and parent_title:
        scope_lines.insert(
            1,
            f" ✅ 本章（{current['title']}）负责：{parent_title} 核心分析内容"
        )

    lines.extend(scope_lines)

    return "\n".join(lines)


# ============================================================
# 目录位置展示（动态读取）
# ============================================================

def build_outline_position(current_node: Dict, context: Dict) -> str:
    """
    动态展示当前节点在目录树中的位置
    """
    parts = []
    
    # 父节点
    parent = context.get("parent_node")
    if parent:
        parts.append(parent["title"])
    
    # 当前节点
    parts.append(current_node["title"])
    
    # 子节点（如果有）
    children_ids = current_node.get("children_ids", [])
    if children_ids:
        parts.append(f"[{', '.join(children_ids)}]")
    
    # 同级节点（显示前后各一个）
    prev = context.get("prev_node")
    next_n = context.get("next_node")
    siblings = []
    if prev:
        siblings.append(f"← {prev['title']}")
    if next_n:
        siblings.append(f"→ {next_n['title']}")
    
    position = " → ".join(parts)
    if siblings:
        position += f"  ({' '.join(siblings)})"
    
    return position


# ============================================================
# 核心函数：生成 Prompt 包
# ============================================================

def build_prompt_package(paper_name: str, node_id: str) -> Dict[str, Any]:
    """
    生成 NodeWriter 可用的 prompt 包
    
    严格串行：
    - 如果前置节点未完成（无 key_conclusion），bridge_paragraph 为 null
    - ContextBuilder 不会等待，只基于已有数据生成
    
    返回结构：
    {
        "ok": True/False,
        "writing_instruction": "...",
        "node": {...},
        "bridge_paragraph": "...",       # 可能为 null
        "required_topics": [...],
        "ending_hint": "...",            # 可能为 null
        "word_count_min": 600,
        "word_count_max": 1500,
        "writing_style": "学术论文",
        "outline_position": "..."
    }
    """
    # 1. 查询上下文
    context = outline_get_context(paper_name, node_id)
    if not context or not context.get("current_node"):
        return {"ok": False, "error": f"节点不存在: {node_id}"}
    
    current = context["current_node"]
    parent = context.get("parent_node")
    level = current.get("level", 0)
    
    # 2. 优先使用用户自定义的分析维度（Phase 1.3）
    # 读取 chapter_hints（待 Phase 1.3 实现后接入）
    state = outline_load(paper_name)
    chapter_hints = {}
    if state and "chapter_hints" in state:
        chapter_hints = state["chapter_hints"]
    
    user_hints = chapter_hints.get(node_id, [])
    
    if user_hints:
        # 用户指定了分析维度，直接使用
        required_topics = user_hints
    else:
        # 用户未指定，用规则动态推导
        required_topics = infer_topics(current, parent)
    
    # 3. 生成承接段（严格串行，无 key_conclusion 则 null）
    bridge_paragraph = generate_bridge(context)
    
    # 4. 生成结尾提示
    next_node = context.get("next_node")
    ending_hint = generate_ending_hint(current, next_node)
    
    # 5. 字数范围
    word_range = get_word_count_range(level)
    
    # 6. 多工具检索补充（v2.0.9 新增）
    #    当节点属于核心章节（第3/4/5/6章）且有 research_keywords 时自动触发
    search_context = ""
    node_keywords = current.get("research_keywords", []) or []
    if node_keywords:
        try:
            from research_tools import quick_search
            kw = node_keywords[0] if isinstance(node_keywords[0], str) else str(next(
                (k for k in node_keywords if k), ""))
            if kw and len(kw) > 5:
                search_context = quick_search(kw)
        except Exception:
            pass  # 检索失败静默降级

    # 7. 组装 prompt 包
    # 增强项4: content_hint 字段（从 outline_state 节点字段读取，开题报告提取或用户手写）
    content_hint = current.get("content_hint", "").strip()

    # 8. 同级章节横向上下文（MECE 边界划定）
    sibling_context = build_sibling_chapter_context(paper_name, node_id)

    package = {
        "ok": True,
        "writing_instruction": f"请生成「{current['title']}」的内容",
        "node": {
            "id": current["id"],
            "level": level,
            "title": current["title"],
            "parent_title": parent["title"] if parent else None,
            "num": current.get("num", "")
        },
        "bridge_paragraph": bridge_paragraph,  # 可能为 null
        "required_topics": required_topics,
        "ending_hint": ending_hint,  # 可能为 null
        "content_hint": content_hint,  # 增强项4: 开题报告提取或用户手写
        "search_context": search_context,  # v2.0.9 多工具检索补充
        "sibling_context": sibling_context,  # 同级章节横向上下文（MECE 边界划定）
        "word_count_min": word_range["min"],
        "word_count_max": word_range["max"],
        "writing_style": "学术论文",
        "outline_position": build_outline_position(current, context)
    }

    return package


def build_prompt_package_text(package: Dict) -> str:
    """
    将 prompt 包转换为文本格式（供 NodeWriter 使用）
    """
    if not package.get("ok"):
        return f"错误: {package.get('error', '未知错误')}"
    
    parts = []
    
    parts.append(f"# 写作任务\n")
    parts.append(f"## 节点信息\n")
    parts.append(f"- 节点ID: {package['node']['id']}\n")
    parts.append(f"- 标题: {package['node']['title']}\n")
    parts.append(f"- 层级: {package['node']['level']}级\n")
    if package['node'].get('parent_title'):
        parts.append(f"- 所属章节: {package['node']['parent_title']}\n")
    parts.append(f"- 编号: {package['node']['num']}\n")
    
    parts.append(f"\n## 写作指令\n")
    parts.append(f"{package['writing_instruction']}\n")
    
    if package.get('bridge_paragraph'):
        parts.append(f"\n## 承接上文\n")
        parts.append(f"{package['bridge_paragraph']}\n")
    
    if package.get('required_topics'):
        parts.append(f"\n## 分析维度建议\n")
        for topic in package['required_topics']:
            parts.append(f"- {topic}\n")

    if package.get('content_hint'):
        parts.append(f"\n## 开题报告方向参考\n")
        parts.append(f"{package['content_hint']}\n")

    if package.get('sibling_context'):
        parts.append(f"\n{package['sibling_context']}")

    if package.get('search_context'):
        parts.append(f"\n## 行业/学术数据参考（多工具检索）\n")
        parts.append(f"{package['search_context']}\n")

    if package.get('ending_hint'):
        parts.append(f"\n## 结尾预告\n")
        parts.append(f"{package['ending_hint']}\n")
    
    parts.append(f"\n## 字数要求\n")
    parts.append(f"{package['word_count_min']} - {package['word_count_max']} 字\n")
    
    parts.append(f"\n## 写作风格\n")
    parts.append(f"{package['writing_style']}\n")
    
    parts.append(f"\n## 目录位置\n")
    parts.append(f"{package['outline_position']}\n")
    
    return "".join(parts)


if __name__ == "__main__":
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    
    if len(sys.argv) < 3:
        print("用法:")
        print("  python3 context_builder.py <论文名> <节点ID>")
        print("  python3 context_builder.py <论文名> <节点ID> --text")
        sys.exit(1)
    
    paper_name = sys.argv[1]
    node_id = sys.argv[2]
    as_text = "--text" in sys.argv
    
    package = build_prompt_package(paper_name, node_id)
    
    if as_text:
        print(build_prompt_package_text(package))
    else:
        print(json.dumps(package, ensure_ascii=False, indent=2))

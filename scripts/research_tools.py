#!/usr/bin/env python3
"""
research_tools.py - 研究工具封装（方案B+C）

核心原则：
  - 内容来源 = 开题报告（Phase 1.3 归因结果），多工具检索仅做补充/验证
  - Skill 本身不存储任何论文特定内容
  - 网络不可用时降级，不阻断写作流程

提供：
  - research_enrich(node_id, paper_name) → str：方案C强制前置补充（outline + 多工具检索）
  - research_enrich_from_outline(node_id, paper_name) → str：纯 outline 提取（无网络依赖）
  - multi_search(query) → str：直接调用多工具检索（供 Agent 层使用）

多工具策略（v2 新增）：
  - web_search  ：头条搜索（Agent 内置，Python 层不代理）
  - tavily      ：Tavily MCP（通过 mcporter）
  - arxiv       ：arXiv 论文搜索（通过 mcporter）
  - openalex    ：OpenAlex 学术文献（通过 scholar-search.py）
  四工具并行，取长补短，去重排序
"""

import sys
import os

# 兼容旧路径引用
try:
    from multi_search import multi_search_text, multi_search
except ImportError:
    # 兼容 from context_builder 导入
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from multi_search import multi_search_text, multi_search


# ============================================================
# Outline 读取（核心数据来源）
# ============================================================

def _get_outline_node(node_id: str, paper_name: str):
    """从 outline state 读取节点信息"""
    try:
        from state_manager_v2 import outline_load, outline_get_node
        outline_load(paper_name)
        return outline_get_node(paper_name, node_id)
    except Exception:
        return None


def research_enrich_from_outline(node_id: str, paper_name: str) -> str:
    """
    纯从 outline 提取，不调用网络（无网络依赖版本）。

    内容来源：
      - node.content_hint：Phase 1.3 归因的原始文本
      - node.research_keywords：Phase 1.3 提取的关键词

    用于：测试环境、多工具检索不可用时、Step 1 验证。
    """
    node = _get_outline_node(node_id, paper_name)
    if not node:
        return ""

    parts = []

    # 来源1：Phase 1.3 归因的 content_hint（主要来源）
    content_hint = node.get("content_hint", "") or ""
    if content_hint:
        parts.append(f"[开题报告相关描述]\n{content_hint}")

    # 来源2：从 outline 读取 research_keywords
    research_keywords = node.get("research_keywords", [])
    if research_keywords:
        kw_str = "、".join(str(k) for k in research_keywords if k)
        parts.append(f"[研究关键词]\n{kw_str}")

    return "\n\n".join(parts)


def research_enrich(node_id: str, paper_name: str, use_network: bool = True) -> str:
    """
    为节点补充 research context（方案C强制前置补充）。

    策略：
      1. 优先从 outline 提取 content_hint（Phase 1.3 归因结果）
      2. 如果 outline 内容贫瘠（<50字）且提供了 research_keywords，
         则调用多工具检索做补充（v2：4工具并行，取长补短）
      3. 完全无数据时返回空字符串（不阻断写作）

    参数：
      node_id: 节点ID
      paper_name: 论文名
      use_network: 是否调用多工具检索（默认True）

    返回：
      格式化研究背景字符串，供 context_builder 注入 prompt
    """
    node = _get_outline_node(node_id, paper_name)
    if not node:
        return ""

    content_hint = node.get("content_hint", "") or ""
    research_keywords = node.get("research_keywords", []) or []

    # 来源1：Phase 1.3 归因的 content_hint（主要来源）
    ctx_parts = []
    if content_hint:
        ctx_parts.append(f"[开题报告相关描述]\n{content_hint}")
    if research_keywords:
        kw_str = "、".join(str(k) for k in research_keywords if k)
        ctx_parts.append(f"[研究关键词]\n{kw_str}")

    existing_ctx = "\n\n".join(ctx_parts)

    # 来源2：如果 outline 内容贫瘠，用多工具并行检索补充（v2 升级）
    if use_network and len(existing_ctx) < 50 and research_keywords:
        kw = next((k for k in research_keywords if k), "")
        if kw:
            search_result = multi_search_text(str(kw))
            # 多工具无结果时返回空，不阻断
            if search_result and not search_result.startswith("[多工具检索无结果"):
                existing_ctx += f"\n\n[多工具并行检索: {kw}]\n{search_result}"

    return existing_ctx


def quick_search(query: str) -> str:
    """
    快速多工具检索（供外部直接调用）。

    参数：
      query: 搜索词

    返回：
      格式化文本结果字符串
    """
    try:
        return multi_search_text(query)
    except Exception:
        return f"[多工具检索不可用: {query}]"


# ============================================================
# P1-1 修复：可靠的 API Key 加载
# ============================================================

def load_minimax_api_key() -> str:
    """
    可靠加载 MiniMax API Key（方案 A:显式 source ~/.zshrc）

    解决：subprocess 中 bash -c 'source ~/.zshrc' 不加载 zsh 特有配置的问题
    龙哥的环境中 MINIMAX_API_KEY 写在 ~/.zshrc，用 bash -lc 才能可靠读取
    """
    import subprocess, os

    # 方案 A: bash -lc 加载 zshrc（-l=login shell, -c=执行命令）
    try:
        result = subprocess.run(
            ['bash', '-lc', 'printf "%s" "$MINIMAX_API_KEY"'],
            capture_output=True, text=True, timeout=5
        )
        key = result.stdout.strip()
        if key and len(key) > 10:
            return key
    except Exception:
        pass

    # 方案 B: 直接读 ~/.zshrc 文本（兜底）
    try:
        zshrc_path = os.path.expanduser('~/.zshrc')
        with open(zshrc_path, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip().startswith('export MINIMAX_API_KEY='):
                    # 提取引号内的值
                    val = line.strip().split('=', 1)[1].strip()
                    if val.startswith('"') and val.endswith('"'):
                        return val[1:-1]
                    elif val.startswith("'") and val.endswith("'"):
                        return val[1:-1]
    except Exception:
        pass

    return ''

#!/usr/bin/env python3
"""
orchestrator_v2.py - 论文写作流程编排器 v1.0

驱动完整流程：
  Phase 1: 目录解析（一次性，确认后锁定）
  Phase 2: 逐节点写作（串行，评审驱动）
  Phase 3: 整合输出

支持断点续跑：
  状态持久化到 state 文件，中断后可从上次位置继续

用法：
  result = orchestrate(paper_name, phase, llm_func=my_llm)
"""

import json
import os
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple

from context_builder import build_prompt_package_text, build_prompt_package
from node_writer import write_node_with_llm, extract_key_conclusion
from reviewer import review_node
from state_manager_v2 import (
    outline_load, outline_save, outline_update_status, outline_get_node, outline_get_context
)
from outline_parser import (
    insert_chapter_summary_nodes,
    get_chapter_summary_id,
    get_chapter_id_from_summary,
)


# ============================================================
# 状态管理
# ============================================================

def _get_orchestrate_state_path(paper_name: str) -> str:
    """获取编排状态文件路径"""
    # 复用 state_manager_v2 的路径逻辑
    from state_manager_v2 import _get_paper_dir
    return os.path.join(_get_paper_dir(paper_name), "_orchestrate_state.json")


def load_orchestrate_state(paper_name: str) -> Optional[Dict]:
    """加载编排状态"""
    path = _get_orchestrate_state_path(paper_name)
    if not os.path.exists(path):
        return None
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None


def save_orchestrate_state(paper_name: str, state: Dict) -> bool:
    """保存编排状态"""
    path = _get_orchestrate_state_path(paper_name)
    try:
        state["last_updated"] = datetime.now().strftime("%Y-%m-%dT%H:%M:%S+08:00")
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


def init_orchestrate_state(paper_name: str) -> Dict:
    """
    初始化编排状态
    """
    outline_state = outline_load(paper_name)
    if not outline_state:
        raise ValueError(f"论文 {paper_name} 的目录树未初始化")

    nodes = outline_state["outline"]["outline_tree"]["nodes"]
    total = len(nodes)

    state = {
        "paper_name": paper_name,
        "phase": "phase1",
        "current_node_id": None,
        "completed_nodes": [],
        "pending_review": [],     # 待用户确认（medium/low）
        "failed_nodes": [],       # 用户选择跳过的节点
        "phase1_confirmed": False,
        "progress": {
            "total": total,
            "completed": 0,
            "pending": 0,
            "failed": 0
        },
        "last_updated": datetime.now().strftime("%Y-%m-%dT%H:%M:%S+08:00")
    }
    save_orchestrate_state(paper_name, state)
    return state


def update_progress(state: Dict) -> Dict:
    """更新进度统计"""
    total = state["progress"]["total"]
    completed = len(state["completed_nodes"])
    pending = len(state["pending_review"])
    failed = len(state["failed_nodes"])

    state["progress"] = {
        "total": total,
        "completed": completed,
        "pending": pending,
        "failed": failed
    }
    return state


# ============================================================
# Phase 1: 目录解析
# ============================================================

def orchestrate_phase1(paper_name: str, docx_path: str = None,
                     outline_text: str = None) -> Dict[str, Any]:
    """
    Phase 1: 目录解析

    输入：docx 文件路径 或 目录文本
    返回：解析后的目录树，等待用户确认
    """
    state = load_orchestrate_state(paper_name)
    if not state:
        state = init_orchestrate_state(paper_name)

    # 如果已确认，不管当前是哪个 phase，都返回 confirmed
    if state.get("phase1_confirmed"):
        return {
            "ok": True,
            "phase": "phase1",
            "confirmed": True,
            "message": "目录已确认，无需重复操作"
        }

    if state["phase"] not in ("phase1",):
        return {
            "ok": False,
            "error": f"当前阶段为 {state['phase']}，不是 phase1"
        }

    return {
        "ok": True,
        "phase": "phase1",
        "confirmed": False,
        "message": "请确认目录结构，确认后进入 Phase 2"
    }


def confirm_phase1(paper_name: str) -> Dict[str, Any]:
    """
    用户确认 Phase 1 目录后调用
    锁定目录结构，进入 Phase 2
    """
    state = load_orchestrate_state(paper_name)
    if not state:
        return {"ok": False, "error": "状态文件不存在"}

    if state.get("phase1_confirmed"):
        return {"ok": True, "message": "目录已确认"}

    state["phase1_confirmed"] = True
    state["phase"] = "phase2"

    # 获取第一个节点
    outline_state = outline_load(paper_name)
    nodes = outline_state["outline"]["outline_tree"]["nodes"]
    first_node = nodes[0] if nodes else None
    state["current_node_id"] = first_node["id"] if first_node else None

    save_orchestrate_state(paper_name, state)

    return {
        "ok": True,
        "phase": "phase2",
        "current_node_id": state["current_node_id"],
        "message": f"目录已确认，Phase 2 开始，当前节点：{state['current_node_id']}"
    }


# ============================================================
# Phase 2: 逐节点写作
# ============================================================

def get_next_writing_node(paper_name: str, state: Dict) -> Optional[str]:
    """
    获取下一个待写作节点
    从 current_node_id 往后找，跳过已完成的
    """
    outline_state = outline_load(paper_name)
    if not outline_state:
        return None

    nodes = outline_state["outline"]["outline_tree"]["nodes"]
    node_ids = [n["id"] for n in nodes]

    current = state.get("current_node_id")
    if current is None:
        # 首次，从第一个开始
        return node_ids[0] if node_ids else None

    # 从 current 之后找下一个未完成的
    try:
        idx = node_ids.index(current)
        for i in range(idx + 1, len(node_ids)):
            nid = node_ids[i]
            if nid not in state["completed_nodes"]:
                return nid
        return None  # 全部完成
    except ValueError:
        return node_ids[0]


def write_single_node(paper_name: str, node_id: str,
                     llm_func: Callable[[str], str]) -> Dict[str, Any]:
    """
    执行单个节点的写作 + 评审流程

    返回：
      {
        ok: bool,
        action: "completed" | "pending_review" | "error",
        node_id: str,
        review_result: dict | None,
        error: str
      }
    """
    # Step 1: 构建 prompt 并写作
    from node_writer import write_node

    write_result = write_node(paper_name, node_id)
    if not write_result["ok"]:
        return {
            "ok": False,
            "action": "error",
            "node_id": node_id,
            "review_result": None,
            "error": write_result.get("error", "写作失败")
        }

    prompt_text = write_result.get("prompt", "")

    # Step 1.5 (增强项4): 写作前信息检查
    scarcity_check = check_info_scarcity(paper_name, node_id)
    if scarcity_check.get("action") == "needs_user_input":
        # 贫瘠 → 暂停，返回 needs_user_input
        return {
            "ok": True,
            "action": "needs_user_input",
            "node_id": node_id,
            "scarcity_info": scarcity_check,
            "review_result": None,
            "chapter_summary": None,
            "error": ""
        }

    # Step 2: 调用 LLM 生成内容
    system_prompt = (
        "你是一位专业的 MBA 学术论文写作者。\n"
        "请根据以下写作任务生成内容。\n"
        "生成完成后，请用 <key_conclusion>标签</key_conclusion> 包裹本节的核心结论，"
        "以便程序提取。\n\n"
        "写作要求：\n"
        "1. 内容需符合学术论文规范\n"
        "2. 逻辑清晰，论证充分\n"
        "3. 字数在指定范围内\n"
        "4. 结尾必须包含用 <key_conclusion> 包裹的结论摘要\n"
    )

    full_prompt = f"{system_prompt}\n\n{prompt_text}"

    try:
        response_text = llm_func(full_prompt)
    except Exception as e:
        return {
            "ok": False,
            "action": "error",
            "node_id": node_id,
            "review_result": None,
            "error": f"LLM 调用失败: {str(e)}"
        }

    # Step 3: 解析 response，提取 content 和 key_conclusion
    import re
    from node_writer import extract_key_conclusion_from_response, count_words

    content_clean = re.sub(
        r'<key_conclusion>.*?</key_conclusion>',
        '',
        response_text,
        flags=re.DOTALL
    ).strip()

    key_conclusion = extract_key_conclusion_from_response(response_text)
    word_count = count_words(content_clean)

    # Step 4: 写入 state
    outline_update_status(
        paper_name, node_id, "completed",
        content=content_clean,
        key_conclusion=key_conclusion,
        word_count=word_count
    )

    # Step 4.5: 增强项1 — 触发章节摘要合成（如适用）
    chapter_summary_result = None
    try:
        chapter_id = is_last_child_of_chapter(paper_name, node_id)
        if chapter_id:
            chapter_summary_result = synthesize_chapter_summary(
                paper_name, chapter_id, llm_func
            )
    except Exception as e:
        chapter_summary_result = {
            "ok": False,
            "action": "ask_user",
            "error": f"章节摘要合成异常: {str(e)}"
        }

    # Step 5: 评审
    # 先获取带 content 的节点（评审需要读取 content）
    node = outline_get_node(paper_name, node_id)
    node["content"] = content_clean

    # 调用评审（注入 mock outline_get_node）
    def mock_llm(prompt: str) -> str:
        return llm_func(prompt)

    review_result = review_node(paper_name, node_id, mock_llm)

    # action 规则：
    # high → 自动完成
    # medium/low → 需要用户确认
    quality = review_result.get("quality", "medium")
    action = "pending_review" if quality in ("medium", "low") else "completed"

    return {
        "ok": True,
        "action": action,
        "node_id": node_id,
        "review_result": review_result,
        "chapter_summary": chapter_summary_result,
        "error": ""
    }


def orchestrate_phase2(paper_name: str,
                      llm_func: Callable[[str], str]) -> Dict[str, Any]:
    """
    Phase 2: 逐节点写作 + 评审

    支持断点续跑：从 current_node_id 继续
    """
    state = load_orchestrate_state(paper_name)
    if not state:
        return {"ok": False, "error": "状态文件不存在，请先初始化 Phase 1"}

    if not state.get("phase1_confirmed"):
        return {"ok": False, "error": "Phase 1 目录未确认"}

    if state["phase"] not in ("phase2",):
        return {"ok": False, "error": f"当前阶段为 {state['phase']}，不是 phase2"}

    # 检查是否有待用户确认的节点
    if state.get("pending_review"):
        pending_node = state["pending_review"][0]
        return {
            "ok": True,
            "action": "wait_for_user",
            "reason": "pending_review",
            "node_id": pending_node,
            "message": f"节点 {pending_node} 需要您确认评审结果"
        }

    # 获取下一个待处理节点
    next_node = get_next_writing_node(paper_name, state)

    if next_node is None:
        # 全部完成
        state["phase"] = "phase3"
        save_orchestrate_state(paper_name, state)
        return {
            "ok": True,
            "action": "phase_complete",
            "phase": "phase3",
            "message": "所有节点写作完成，进入 Phase 3"
        }

    # 执行当前节点
    result = write_single_node(paper_name, next_node, llm_func)

    if not result["ok"]:
        return result

    # 更新 state
    state["current_node_id"] = next_node

    quality = result["review_result"].get("quality", "medium")

    if result["action"] == "completed":
        state["completed_nodes"].append(next_node)
        update_progress(state)

        # 继续下一节点
        next_next = get_next_writing_node(paper_name, state)
        return {
            "ok": True,
            "action": "continue",
            "node_id": next_node,
            "quality": quality,
            "review_result": result["review_result"],
            "next_node_id": next_next,
            "progress": state["progress"],
            "message": f"节点 {next_node} 完成（质量：{quality}），进入下一节点 {next_next}"
        }
    else:
        # 需要用户确认（medium/low）
        state["pending_review"].append(next_node)
        update_progress(state)
        save_orchestrate_state(paper_name, state)

        return {
            "ok": True,
            "action": "wait_for_user",
            "reason": "pending_review",
            "node_id": next_node,
            "quality": quality,
            "review_result": result["review_result"],
            "progress": state["progress"],
            "message": f"节点 {next_node} 需要您确认评审结果（质量：{quality}）"
        }


def handle_review_decision(paper_name: str, node_id: str,
                          decision: str) -> Dict[str, Any]:
    """
    处理用户对评审结果的决策

    decision: "continue" | "rewrite" | "skip"
      - continue: 接受当前版本，继续下一节点
      - rewrite: 要求重新生成
      - skip: 跳过该节点
    """
    state = load_orchestrate_state(paper_name)
    if not state:
        return {"ok": False, "error": "状态文件不存在"}

    if node_id not in state.get("pending_review", []):
        return {"ok": False, "error": f"节点 {node_id} 不在待确认列表中"}

    if decision == "continue":
        # 接受当前版本
        state["pending_review"].remove(node_id)
        if node_id not in state["completed_nodes"]:
            state["completed_nodes"].append(node_id)
        update_progress(state)

    elif decision == "skip":
        # 跳过
        state["pending_review"].remove(node_id)
        state["failed_nodes"].append(node_id)
        update_progress(state)

    elif decision == "rewrite":
        # 打回重写（从 pending 中移除，不加入 completed，下次会重新生成）
        state["pending_review"].remove(node_id)
        # 不加入 completed_nodes，下次会重新生成

    save_orchestrate_state(paper_name, state)

    # 获取下一节点
    next_node = get_next_writing_node(paper_name, state)

    return {
        "ok": True,
        "decision": decision,
        "next_node_id": next_node,
        "progress": state["progress"],
        "message": f"已处理节点 {node_id} 的决策 ({decision})，下一节点：{next_node}"
    }


# ============================================================
# Phase 3: 整合 + 修改 + 输出
# ============================================================

def orchestrate_phase3(paper_name: str) -> Dict[str, Any]:
    """
    Phase 3: 整合所有节点内容，生成完整论文
    """
    state = load_orchestrate_state(paper_name)
    if not state:
        return {"ok": False, "error": "状态文件不存在"}

    if state["phase"] != "phase3":
        return {"ok": False, "error": f"当前阶段为 {state['phase']}，不是 phase3"}

    # 加载所有节点内容
    outline_state = outline_load(paper_name)
    nodes = outline_state["outline"]["outline_tree"]["nodes"]

    completed_ids = set(state["completed_nodes"])

    # 按顺序拼接内容
    sections = []
    for node in nodes:
        if node["id"] in completed_ids or node["id"] in state.get("failed_nodes", []):
            node_data = outline_get_node(paper_name, node["id"])
            content = node_data.get("content", "") if node_data else ""
            if content:
                title = node.get("title", node["id"])
                sections.append(f"## {title}\n\n{content}")

    full_content = "\n\n".join(sections)

    # 标记为待用户确认状态
    state["phase3_status"] = "awaiting_review"
    save_orchestrate_state(paper_name, state)

    return {
        "ok": True,
        "phase": "phase3",
        "sub_status": "awaiting_review",
        "content": full_content,
        "word_count": len(full_content),
        "completed_count": len(state["completed_nodes"]),
        "failed_count": len(state.get("failed_nodes", [])),
        "message": "论文已整合，请预览并提出修改意见"
    }


def handle_phase3_feedback(paper_name: str,
                          feedback: List[Dict[str, str]],
                          llm_func: Callable[[str], str] = None) -> Dict[str, Any]:
    """
    Phase 3: 处理用户修改意见

    feedback 格式：
    [
        {"node_id": "1.1", "instruction": "补充行业数据支撑"},
        {"node_id": "2.1", "instruction": "逻辑不够清晰，重新组织"}
    ]

    返回：修改后的完整论文内容
    """
    state = load_orchestrate_state(paper_name)
    if not state:
        return {"ok": False, "error": "状态文件不存在"}

    if state["phase"] != "phase3":
        return {"ok": False, "error": f"当前阶段为 {state['phase']}，不是 phase3"}

    if not feedback:
        return {"ok": False, "error": "feedback 为空"}

    if not llm_func:
        return {"ok": False, "error": "修改需要提供 llm_func"}

    modified_count = 0
    for item in feedback:
        node_id = item.get("node_id")
        instruction = item.get("instruction", "")

        if not node_id:
            continue

        # 获取当前节点内容
        node = outline_get_node(paper_name, node_id)
        if not node:
            continue

        current_content = node.get("content", "")

        # 调用 LLM 修改
        prompt = f"""节点：{node.get('title', node_id)}

当前内容：
---
{current_content}
---

修改要求：{instruction}

请根据修改要求，生成修改后的完整内容。"""

        try:
            new_content = llm_func(prompt)
            # 去掉可能的 key_conclusion 标签
            import re
            new_content = re.sub(r'<key_conclusion>.*?</key_conclusion>', '', new_content, flags=re.DOTALL).strip()

            # 写入 state
            outline_update_status(paper_name, node_id, "completed", content=new_content)
            modified_count += 1
        except Exception as e:
            pass  # 单节点失败不影响其他

    # 重新整合
    result = orchestrate_phase3(paper_name)
    result["modified_count"] = modified_count
    result["message"] = f"已完成 {modified_count} 处修改，请再次预览"

    return result


def confirm_phase3_and_export(paper_name: str) -> Dict[str, Any]:
    """
    Phase 3: 用户确认整合结果，输出 Word
    """
    state = load_orchestrate_state(paper_name)
    if not state:
        return {"ok": False, "error": "状态文件不存在"}

    if state["phase"] != "phase3":
        return {"ok": False, "error": f"当前阶段为 {state['phase']}，不是 phase3"}

    # 整合最终内容
    outline_state = outline_load(paper_name)
    nodes = outline_state["outline"]["outline_tree"]["nodes"]
    completed_ids = set(state["completed_nodes"])

    sections = []
    for node in nodes:
        if node["id"] in completed_ids or node["id"] in state.get("failed_nodes", []):
            node_data = outline_get_node(paper_name, node["id"])
            content = node_data.get("content", "") if node_data else ""
            if content:
                title = node.get("title", node["id"])
                sections.append(f"## {title}\n\n{content}")

    full_content = "\n\n".join(sections)

    # 保存最终内容
    output_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..",
        f"papers/{paper_name}_final.md"
    )
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(full_content)

    return {
        "ok": True,
        "phase": "phase3",
        "sub_status": "exported",
        "output_path": output_path,
        "word_count": len(full_content),
        "message": f"论文已导出至 {output_path}，请使用 md2docx_strict.py 转换为 Word"
    }


# ============================================================
# 主入口
# ============================================================

def orchestrate(paper_name: str,
               phase: str = None,
               action: str = None,
               llm_func: Callable[[str], str] = None,
               **kwargs) -> Dict[str, Any]:
    """
    统一入口

    phase:
      None / "auto": 根据当前状态自动判断
      "phase1": 目录确认
      "phase2": 智能写作
      "phase3": 整合 + 修改 + 输出

    action（可选）:
      "phase3_review": 生成论文供用户预览
      "phase3_feedback": 处理用户修改意见
      "phase3_export": 确认并导出 Word

    llm_func: LLM 调用函数，Phase 2 和 phase3_feedback 需要提供

    kwargs: 额外参数（如 feedback, decision 等）
    """
    state = load_orchestrate_state(paper_name)

    if phase is None or phase == "auto":
        if not state:
            phase = "phase1"
        elif not state.get("phase1_confirmed"):
            phase = "phase1"
        elif state["phase"] == "phase1":
            phase = "phase2"
        else:
            phase = state.get("phase", "phase2")

    if phase == "phase1":
        return orchestrate_phase1(paper_name, **kwargs)

    elif phase == "phase2":
        if not llm_func:
            return {"ok": False, "error": "phase2 需要提供 llm_func"}
        return orchestrate_phase2(paper_name, llm_func)

    elif phase == "phase3":
        if action == "phase3_feedback":
            return handle_phase3_feedback(paper_name, llm_func=llm_func, **kwargs)
        elif action == "phase3_export":
            return confirm_phase3_and_export(paper_name)
        else:
            # 默认：生成论文供预览
            return orchestrate_phase3(paper_name)

    else:
        return {"ok": False, "error": f"未知阶段: {phase}"}


# ============================================================
# 写作前信息检查（增强项4）
# ============================================================

def check_info_scarcity(paper_name: str, node_id: str) -> Dict[str, Any]:
    """
    写作前信息贫瘠检查（增强项4）。

    检查 3 项信息源（拍板标准 A）：
      1. content_hint：开题报告提取或用户手写，存于 node.content_hint
      2. user_hints：用户自定义分析维度，存于 state.chapter_hints[node_id]
      3. bridge：prev_sibling_conclusion / parent_conclusion / prev_chapter_summary 任一非空

    拍板标准 A：任一为空 → action="needs_user_input"，全部非空 → action="proceed"。

    返回：
      {
        ok: True,
        action: "proceed" | "needs_user_input",
        node_id: str,
        node_title: str,
        current_info: {
          content_hint: str,
          user_hints: list,
          has_bridge: bool,
          bridge_source: str | None  # "prev" | "parent" | "chapter_summary"
        },
        missing_sources: ["content_hint", ...],  # 仅 needs_user_input 时填充
        prompt_options: {                        # 仅 needs_user_input 时填充
          "1": "用户提供 content_hint",
          "2": "AI 自行生成",
          "3": "跳过该节点"
        }
      }
    """
    node = outline_get_node(paper_name, node_id)
    if not node:
        return {"ok": False, "action": "proceed", "error": f"节点不存在: {node_id}"}

    state = outline_load(paper_name)
    if not state:
        return {"ok": False, "action": "proceed", "error": "目录树未初始化"}

    # 1. content_hint
    content_hint = (node.get("content_hint") or "").strip()

    # 2. user_hints (chapter_hints)
    chapter_hints = state.get("chapter_hints", {}) if state else {}
    user_hints = chapter_hints.get(node_id, [])

    # 3. bridge
    context = outline_get_context(paper_name, node_id)
    has_prev = bool(context.get("prev_sibling_conclusion"))
    has_parent = bool(context.get("parent_conclusion"))
    has_chapter_summary = bool(
        context.get("prev_chapter_summary", {}).get("key_conclusion")
        if context.get("prev_chapter_summary") else False
    )
    has_bridge = has_prev or has_parent or has_chapter_summary
    bridge_source = (
        "prev" if has_prev else
        "parent" if has_parent else
        "chapter_summary" if has_chapter_summary else None
    )

    current_info = {
        "content_hint": content_hint,
        "user_hints": user_hints,
        "has_bridge": has_bridge,
        "bridge_source": bridge_source
    }

    # 标准 A：任一为空 → needs_user_input
    missing = []
    if not content_hint:
        missing.append("content_hint")
    if not user_hints:
        missing.append("user_hints")
    if not has_bridge:
        missing.append("bridge")

    if missing:
        return {
            "ok": True,
            "action": "needs_user_input",
            "node_id": node_id,
            "node_title": node.get("title", ""),
            "current_info": current_info,
            "missing_sources": missing,
            "prompt_options": {
                "1": "用户提供 content_hint（覆盖写入 node.content_hint）",
                "2": "AI 自行生成（不补充，直接调用 LLM）",
                "3": "跳过该节点（记为 failed，后续手动重试）"
            }
        }

    return {
        "ok": True,
        "action": "proceed",
        "node_id": node_id,
        "node_title": node.get("title", ""),
        "current_info": current_info,
        "missing_sources": [],
        "prompt_options": {}
    }


def apply_user_decision(
    paper_name: str,
    node_id: str,
    decision: str,
    user_hint: str = None
) -> Dict[str, Any]:
    """
    处理 Orchestrator 收到的 user decision（贫瘠节点 3 选项）。

    参数：
      paper_name: 论文名
      node_id: 节点 ID
      decision: "1" (提供 hint) | "2" (AI 自行生成) | "3" (跳过)
      user_hint: 用户提供的新 content_hint（仅 decision=="1" 时使用）

    返回：
      {ok: True, action: "proceed" | "skipped" | "error", ...}
    """
    if decision == "1":
        # 用户提供 content_hint → 写入节点 → 继续写作
        if not user_hint or not user_hint.strip():
            return {"ok": False, "error": "decision='1' 必须提供 user_hint"}
        outline_update_status(
            paper_name, node_id, "pending",
            content_hint=user_hint.strip()
        )
        return {"ok": True, "action": "proceed", "decision": "1"}
    elif decision == "2":
        # AI 自行生成：不写入 hint，继续写作
        return {"ok": True, "action": "proceed", "decision": "2"}
    elif decision == "3":
        # 跳过该节点：记为 failed
        outline_update_status(paper_name, node_id, "failed", retry_count=999)
        return {"ok": True, "action": "skipped", "decision": "3"}
    else:
        return {"ok": False, "error": f"无效 decision: {decision}，必须是 '1'/'2'/'3'"}


# ============================================================
# 章节摘要合成（增强项1 — 跨父节点 Bridge）
# ============================================================

def is_last_child_of_chapter(paper_name: str, node_id: str) -> Optional[str]:
    """
    判断 node_id 是否是其所属 L1 章节最后一个已完成的 L2/L3 子节点。

    返回：
      - 章节 ID（如 "ch1"）如果是最后一个 → 触发摘要合成
      - None 如果不是

    实现：直接读 outline_state，定位章节 synthesizes 列表，检查是否全部 completed。
    """
    state = outline_load(paper_name)
    if not state:
        return None

    nodes = state["outline"]["outline_tree"]["nodes"]
    node_map = {n["id"]: n for n in nodes}

    target = node_map.get(node_id)
    if not target or target.get("is_virtual"):
        return None

    # 递归查 L1 父章节
    chapter_id = None
    cur = target
    while cur and cur.get("level", 0) > 1:
        parent_id = cur.get("parent_id")
        if not parent_id:
            return None
        cur = node_map.get(parent_id)
        if not cur:
            return None
        if cur.get("level") == 1 and not cur.get("is_virtual"):
            chapter_id = cur["id"]
            break

    if not chapter_id:
        return None

    # 查该章节的虚拟摘要节点
    summary_id = get_chapter_summary_id(chapter_id)
    summary_node = node_map.get(summary_id)
    if not summary_node:
        return None

    synthesizes = summary_node.get("synthesizes", [])
    if not synthesizes:
        return None

    # 检查 synthesizes 列表是否全部 completed
    all_done = True
    for sid in synthesizes:
        s = node_map.get(sid)
        if not s:
            continue
        if s.get("writing_status") != "completed":
            all_done = False
            break

    return chapter_id if all_done else None


def _build_summary_prompt(chapter_title: str, child_conclusions: List[Dict[str, str]],
                         user_input: str = None) -> str:
    """
    构建 LLM 合成章节摘要的 prompt

    参数：
      chapter_title: 章节标题（如"外部环境分析"）
      child_conclusions: [{"id": "3.1", "title": "...", "key_conclusion": "..."}, ...]
      user_input: 用户在 Phase 1.3 填的"本章核心问题"（可选补充）
    """
    child_text = "\n".join([
        f"- [{c['id']}] {c['title']}：{c['key_conclusion']}"
        for c in child_conclusions
    ])

    user_supplement = f"\n\n用户补充视角（本章核心问题）：\n{user_input}" if user_input else ""

    return f"""你是一位专业的 MBA 学术论文写作者。

任务：将以下章节的子节点关键结论合成为本章摘要。

章节标题：{chapter_title}

子节点关键结论：
{child_text}
{user_supplement}

要求：
1. 提炼本章核心发现与逻辑主线（不要罗列子节点）
2. 为下一章节提供承接基础
3. 字数严格控制在 200-300 字之间，不要超过 300
4. 输出格式：只输出摘要正文，不要任何标题或前缀

摘要正文："""


def synthesize_chapter_summary(
    paper_name: str,
    chapter_id: str,
    llm_func: Callable[[str], str],
    user_input: str = None
) -> Dict[str, Any]:
    """
    合成章节摘要。

    触发时机（自动）：章节最后一个 L2/L3 子节点写作完成时，由 write_single_node() 回调调用。
    失败处理（拍板要求 #3）：LLM 失败 → 返回 action="ask_user"，由 Orchestrator 询问用户。

    参数：
      paper_name: 论文名
      chapter_id: 章节 ID（如 "ch1"）
      llm_func: LLM 调用函数
      user_input: 用户在 Phase 1.3 填的"本章核心问题"（可选）

    返回：
      {
        ok: bool,
        action: "completed" | "ask_user",   # ask_user 时调用方应询问用户
        summary: str | None,                 # 摘要内容（成功时）
        source: "llm" | "user" | None,      # 摘要来源
        error: str,
        chapter_id: str,
        child_conclusions: list              # ask_user 时附带给 Orchestrator
      }
    """
    state = outline_load(paper_name)
    if not state:
        return {"ok": False, "action": "ask_user", "error": "目录树未初始化"}

    nodes = state["outline"]["outline_tree"]["nodes"]
    node_map = {n["id"]: n for n in nodes}

    summary_id = get_chapter_summary_id(chapter_id)
    summary_node = node_map.get(summary_id)
    if not summary_node:
        return {"ok": False, "action": "ask_user", "error": f"未找到虚拟摘要节点: {summary_id}"}

    # 收集子节点结论
    child_conclusions = []
    for cid in summary_node.get("synthesizes", []):
        c = node_map.get(cid)
        if c and c.get("key_conclusion"):
            child_conclusions.append({
                "id": cid,
                "title": c.get("title", ""),
                "key_conclusion": c["key_conclusion"]
            })

    if not child_conclusions:
        return {
            "ok": False,
            "action": "ask_user",
            "error": "该章节无可用子节点结论",
            "chapter_id": chapter_id,
            "child_conclusions": []
        }

    summary_text = None
    source = None

    # 路径 1：用户提供摘要
    if user_input:
        summary_text = user_input.strip()
        source = "user"

    # 路径 2：LLM 合成
    if not summary_text:
        prompt = _build_summary_prompt(
            chapter_title=summary_node.get("chapter_title", chapter_id),
            child_conclusions=child_conclusions,
            user_input=user_input
        )
        try:
            response_text = llm_func(prompt)
            summary_text = response_text.strip()
            source = "llm"
        except Exception as e:
            # LLM 失败 → 拍板要求 #3：询问用户
            return {
                "ok": False,
                "action": "ask_user",
                "error": f"LLM 调用失败: {str(e)}",
                "chapter_id": chapter_id,
                "chapter_title": summary_node.get("chapter_title", chapter_id),
                "child_conclusions": child_conclusions
            }

    # 路径 3：超长截断到 300 字以内（保底）
    if summary_text and len(summary_text) > 300:
        summary_text = summary_text[:300]

    # 写入虚拟节点
    outline_update_status(
        paper_name, summary_id, "completed",
        key_conclusion=summary_text,
        word_count=len(summary_text) if summary_text else 0
    )

    return {
        "ok": True,
        "action": "completed",
        "summary": summary_text,
        "source": source,
        "error": "",
        "chapter_id": chapter_id,
        "node_id": summary_id
    }


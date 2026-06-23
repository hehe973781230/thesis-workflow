#!/usr/bin/env python3
"""
run_workflow.py - thesis-workflow v2 真实入口 CLI（v2.0.6 新增）

P0-2 + P0-3 修复：补 v2 真实入口
  - CLI 入口（`python3 scripts/run_workflow.py <paper_name>`）
  - 9 个 HIL 节点 hard pause
  - 走 v2.0.4 推荐调用模式（write_single_node + apply_user_decision + bypass_scarcity）
  - 不直接调 outline_update_status（避免 B-2 bug）

用法：
  python3 scripts/run_workflow.py <paper_name>               # auto 模式
  python3 scripts/run_workflow.py <paper_name> --phase phase1  # 指定阶段
  python3 scripts/run_workflow.py <paper_name> --status     # 仅查看状态
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Callable, Dict, Optional

SCRIPT_DIR = Path(__file__).parent.resolve()
sys.path.insert(0, str(SCRIPT_DIR))

from orchestrator_v2 import (
    orchestrate, orchestrate_phase1_1, orchestrate_phase2,
    orchestrate_phase3, confirm_phase3_and_export,
    confirm_phase1_3, write_single_node, apply_user_decision,
    check_info_scarcity, confirm_phase1, skip_phase1_3
)
from state_manager_v2 import (
    load_orchestrate_state, save_orchestrate_state,
    outline_load, outline_get_node, init_orchestrate_state
)
from node_writer import write_node, extract_key_conclusion_from_response

WORKSPACE = Path(os.path.expanduser("~/.openclaw/workspace"))


# ============================================================
# HIL 硬暂停工具
# ============================================================

def hil_pause(hil_id: str, message: str, options: Optional[Dict[str, str]] = None) -> str:
    """HIL 硬暂停：打印清晰提示，等用户输入决策"""
    print()
    print("=" * 60)
    print(f"🛑 HIL #{hil_id}")
    print("=" * 60)
    print(message)
    if options:
        print("\n可选决策：")
        for k, v in options.items():
            print(f"  [{k}] {v}")
    print()

    while True:
        try:
            choice = input("请输入决策（输入 quit 退出）: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n⚠️ 输入中断，退出")
            sys.exit(0)

        if choice == "quit":
            sys.exit(0)

        if options and choice in options:
            return choice

        if not options and choice in ("", "y", "yes", "确认", "ok"):
            return choice

        print(f"⚠️ 无效输入: {choice}，请重新选择")


def get_paper_status(paper_name: str) -> Optional[Dict[str, Any]]:
    """打印当前 paper 状态"""
    state = load_orchestrate_state(paper_name)
    if not state:
        print(f"❌ 论文 {paper_name} 状态文件不存在")
        return None

    print(f"=== {paper_name} 状态 ===")
    print(f"  phase: {state.get('phase')}")
    print(f"  phase1_confirmed: {state.get('phase1_confirmed')}")
    print(f"  phase1_3_status: {state.get('phase1_3_status')}")
    print(f"  current_node_id: {state.get('current_node_id')}")
    print(f"  completed_nodes: {state.get('completed_nodes', [])}")
    print(f"  pending_review: {state.get('pending_review', [])}")
    print(f"  failed_nodes: {state.get('failed_nodes', [])}")
    progress = state.get('progress', {})
    print(f"  progress: {progress.get('completed', 0)}/{progress.get('total', 0)}")
    audit = state.get('audit_log', [])
    if audit:
        print(f"  audit_log: {len(audit)} 条")
    return state


# ============================================================
# Phase 1: 规划与归因
# ============================================================

def run_phase1(paper_name: str, llm_func: Optional[Callable] = None) -> bool:
    """Phase 1: 解析 + 大纲确认 + Phase 1.3"""
    state = load_orchestrate_state(paper_name)

    # Phase 1.1: 解析入口
    if not state:
        print(f"\n📝 Phase 1.1: 初始化论文 {paper_name}")
        print("  请提供开题报告 docx 路径（直接回车 = 手动录入文本）")
        try:
            docx_path = input("  docx 路径: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n⚠️ 输入中断")
            return False

        if docx_path and Path(docx_path).exists():
            r = orchestrate(paper_name, action="phase1_1_init",
                          input_type="docx", input_data=docx_path,
                          llm_func=llm_func)
        elif docx_path:
            print(f"❌ 文件不存在: {docx_path}")
            return False
        else:
            print("\n请粘贴开题报告文本（Ctrl+D 结束）:")
            lines = []
            try:
                while True:
                    line = input()
                    lines.append(line)
            except EOFError:
                pass
            outline_text = "\n".join(lines)
            if not outline_text.strip():
                print("❌ 文本为空，无法解析")
                return False
            r = orchestrate(paper_name, action="phase1_1_init",
                          input_type="text", input_data=outline_text,
                          llm_func=llm_func)

        if not r.get("ok"):
            print(f"❌ Phase 1.1 失败: {r.get('error')}")
            return False

        node_count = len(r.get("outline", {}).get("outline_tree", {}).get("nodes", []))
        print(f"✅ Phase 1.1 完成: 解析 {node_count} 个节点")

    # HIL #1: 大纲确认
    outline = outline_load(paper_name)
    nodes = outline["outline"]["outline_tree"]["nodes"]
    print(f"\n📋 论文大纲（共 {len(nodes)} 节点）:")
    for n in nodes[:30]:
        marker = " [虚拟]" if n.get("is_virtual") else ""
        print(f"  - {n['id']:10s} | L{n['level']} | {n['title']}{marker}")
    if len(nodes) > 30:
        print(f"  ... 还有 {len(nodes) - 30} 节点")

    hil_pause("1", "是否接受以上大纲？",
             {"1": "确认（继续 Phase 1.3）",
              "2": "取消（修改后重跑）"})

    # Phase 1.2 confirm
    r = orchestrate(paper_name, action="phase1_confirm")
    if not r.get("ok"):
        print(f"❌ Phase 1.2 confirm 失败: {r.get('error')}")
        return False
    print(f"✅ Phase 1.2 完成: 大纲已确认")

    # Phase 1.3: 开题报告归因
    state = load_orchestrate_state(paper_name)
    if state.get("phase1_3_status") == "pending":
        # 检查 state 里是否已经有 docx_path
        existing_path = state.get("phase1_3_docx_path")

        if not existing_path or not Path(existing_path).exists():
            print(f"\n📄 Phase 1.3: 需要开题报告做归因")
            print(f"  ⚠️ 拍板 #1：Phase 1.3 不允许跳过（v2.0.6 拦截）")
            try:
                new_path = input("  请输入开题报告 docx 路径（必填）: ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\n⚠️ 输入中断")
                return False
            if not new_path or not Path(new_path).exists():
                print("❌ 必须提供有效的 docx 路径，无法继续")
                return False
            existing_path = new_path
        else:
            print(f"\n📄 发现已有 docx: {existing_path}")

        # 提交 phase1_3_submit
        r = orchestrate(paper_name, action="phase1_3_submit",
                       docx_path=existing_path, llm_func=llm_func)
        if not r.get("ok"):
            print(f"❌ Phase 1.3 submit 失败: {r.get('error')}")
            return False
        print(f"✅ Phase 1.3 submit 完成")

    elif state.get("phase1_3_status") == "submitted":
        print(f"\n📄 Phase 1.3 已提交，等待确认归因")
    elif state.get("phase1_3_status") == "confirmed":
        print(f"\n✅ Phase 1.3 已确认，跳过")
    elif state.get("phase1_3_status") == "skipped":
        print(f"\n⚠️ Phase 1.3 状态为 skipped（v2.0.6 前可能跳过）")
        # v2.0.6 后 skip 需 reason + operator，新状态不应为 skipped
        # 旧状态给用户警告
        hil_pause("1.3x", "Phase 1.3 之前被跳过，但 v2.0.6 强制不允许。\n"
                         "是否重新走 Phase 1.3？",
                 {"1": "重新 submit Phase 1.3",
                  "2": "继续（不推荐）"})

    # HIL #2: 归因确认
    if state.get("phase1_3_status") in ("submitted",):
        # 显示归因结果
        p13_result = state.get("phase1_3_result", {})
        summary = p13_result.get("summary", {})
        node_details = p13_result.get("node_details", {})

        print(f"\n📊 归因摘要: {summary}")
        if node_details:
            print(f"\n各节点归因（前 10）:")
            for nid, info in list(node_details.items())[:10]:
                hint_preview = (info.get("content_hint", "") or "")[:60]
                print(f"  - {nid:10s} | {hint_preview}...")

        hil_pause("2", "归因结果是否接受？",
                 {"1": "确认（进入 Phase 2）",
                  "2": "调整 hint（手动 update）",
                  "3": "取消"})

        # 确认归因
        r = orchestrate(paper_name, action="phase1_3_confirm")
        if not r.get("ok"):
            print(f"❌ Phase 1.3 confirm 失败: {r.get('error')}")
            return False

    print(f"\n✅ Phase 1 全部完成")
    return True


# ============================================================
# Phase 2: 写作循环
# ============================================================

def run_phase2(paper_name: str, llm_func: Callable) -> bool:
    """Phase 2: 写作循环（v2.0.4 推荐调用模式）"""
    state = load_orchestrate_state(paper_name)
    if not state:
        print("❌ 状态文件不存在，请先跑 Phase 1")
        return False
    if state.get("phase1_3_status") != "confirmed":
        print(f"❌ Phase 1.3 未确认（当前: {state.get('phase1_3_status')}）")
        return False
    if not llm_func:
        print("❌ Phase 2 需要 llm_func 参数")
        return False

    total = state.get('progress', {}).get('total', 0)
    print(f"\n📝 Phase 2: 逐节点写作（共 {total} 节点）")

    iteration_count = 0
    max_iterations = total * 3  # 防止无限循环

    while iteration_count < max_iterations:
        iteration_count += 1

        # 找下一个未完成节点
        outline = outline_load(paper_name)
        nodes = outline["outline"]["outline_tree"]["nodes"]
        state = load_orchestrate_state(paper_name)

        next_node_id = None
        for n in nodes:
            if n.get("is_virtual"):
                continue  # 虚拟节点跳过
            if n["id"] not in state.get("completed_nodes", []) and \
               n["id"] not in state.get("failed_nodes", []):
                next_node_id = n["id"]
                break

        if not next_node_id:
            print(f"\n✅ 所有节点已完成")
            break

        # v2.0.4 推荐路径：write_single_node（内部含 check_info_scarcity + LLM + review）
        result = write_single_node(paper_name, next_node_id, llm_func, bypass_scarcity=False)

        if not result.get("ok"):
            print(f"❌ 节点 {next_node_id} 失败: {result.get('error')}")
            return False

        action = result.get("action")

        if action == "needs_user_input":
            # HIL #3: info_scarcity 触发
            scarcity = check_info_scarcity(paper_name, next_node_id)
            missing = scarcity.get("missing_sources", [])
            current_info = scarcity.get("current_info", {})
            node_title = scarcity.get("node_title", next_node_id)

            print(f"\n⚠️ 节点 {next_node_id} ({node_title}) 信息贫瘠")
            print(f"  缺失项: {missing}")
            print(f"  现有信息:")
            print(f"    content_hint: {(current_info.get('content_hint') or '(空)')[:80]}")
            print(f"    user_hints: {current_info.get('user_hints', [])}")
            print(f"    bridge_source: {current_info.get('bridge_source', '(无)')}")

            choice = hil_pause("3", f"节点 {next_node_id} 决策",
                             {"1": "用户提供 content_hint",
                              "2": "AI 自行生成",
                              "3": "跳过该节点"})

            if choice == "1":
                try:
                    new_hint = input(f"  请输入 {next_node_id} 的 content_hint: ").strip()
                except (EOFError, KeyboardInterrupt):
                    return False
                apply_user_decision(paper_name, next_node_id, "1", user_hint=new_hint)
                # 重新调 write_single_node（bypass_scarcity=True 因为 hint 已更新）
                result = write_single_node(paper_name, next_node_id, llm_func, bypass_scarcity=True)
                action = result.get("action")

            elif choice == "2":
                apply_user_decision(paper_name, next_node_id, "2")
                # 重新调 write_single_node
                result = write_single_node(paper_name, next_node_id, llm_func, bypass_scarcity=True)
                action = result.get("action")

            elif choice == "3":
                apply_user_decision(paper_name, next_node_id, "3")
                print(f"  ⏭️ 节点 {next_node_id} 已跳过（failed_nodes）")
                continue

        if action == "completed":
            quality = result.get("review_result", {}).get("quality", "medium")
            wc = result.get("word_count", 0)
            print(f"  ✅ {next_node_id} 完成 | 质量: {quality} | 字数: {wc}")

        elif action == "pending_review":
            # HIL #4: 评审质量 medium/low
            quality = result.get("review_result", {}).get("quality")
            summary = result.get("review_result", {}).get("summary", "")
            weaknesses = result.get("review_result", {}).get("weaknesses", [])
            suggestions = result.get("review_result", {}).get("suggestions", [])

            print(f"\n⚠️ 节点 {next_node_id} 评审质量: {quality}")
            if summary:
                print(f"  总结: {summary[:200]}")
            if weaknesses:
                print(f"  问题: {weaknesses}")
            if suggestions:
                print(f"  建议: {suggestions}")

            choice = hil_pause("4", f"节点 {next_node_id} 评审结果",
                             {"1": "接受（标记 completed）",
                              "2": "重写（再调一次 write_single_node）",
                              "3": "跳过该节点"})

            if choice == "1":
                # 接受：手动更新 state（走 v2 API，不直接 outline_update_status）
                # 使用 orchestrate 的 phase2 路径再调一次会死循环
                # v2.0.6 TODO: 需要 orchestrate_v2 提供 apply_review_decision() API
                # 当前 workaround: 直接更新 state.completed_nodes
                state = load_orchestrate_state(paper_name)
                if next_node_id not in state.get("completed_nodes", []):
                    state["completed_nodes"].append(next_node_id)
                if next_node_id in state.get("pending_review", []):
                    state["pending_review"].remove(next_node_id)
                from state_manager_v2 import update_progress
                update_progress(state)
                save_orchestrate_state(paper_name, state)
                print(f"  ✅ {next_node_id} 已接受")

            elif choice == "2":
                # 重写：调 write_single_node 一次（bypass_scarcity=True 跳过信息检查）
                write_single_node(paper_name, next_node_id, llm_func, bypass_scarcity=True)
                print(f"  🔄 {next_node_id} 已重写")

            elif choice == "3":
                # 跳过
                state = load_orchestrate_state(paper_name)
                if next_node_id not in state.get("failed_nodes", []):
                    state["failed_nodes"].append(next_node_id)
                if next_node_id in state.get("pending_review", []):
                    state["pending_review"].remove(next_node_id)
                from state_manager_v2 import update_progress
                update_progress(state)
                save_orchestrate_state(paper_name, state)
                print(f"  ⏭️ {next_node_id} 已跳过")

        elif action == "error":
            print(f"❌ 节点 {next_node_id} 写入失败")
            return False

    # HIL #5: Phase 2 完成确认
    state = load_orchestrate_state(paper_name)
    progress = state.get("progress", {})
    completed_count = progress.get('completed', 0)
    failed_count = progress.get('failed', 0)
    total = progress.get('total', 0)

    print(f"\n📊 Phase 2 完成: {completed_count}/{total} 节点 completed，{failed_count} failed")
    hil_pause("5", "Phase 2 内容是否接受？",
             {"1": "确认（进入 Phase 3）",
              "2": "返回修改（重新跑某个节点）"})

    # 推进 phase 到 phase3
    state["phase"] = "phase3"
    save_orchestrate_state(paper_name, state)
    print(f"✅ Phase 2 确认完成")
    return True


# ============================================================
# Phase 3: 整合
# ============================================================

def run_phase3(paper_name: str) -> bool:
    """Phase 3: 整合 + 导出"""
    state = load_orchestrate_state(paper_name)
    if state.get("phase") != "phase3":
        print(f"❌ Phase 2 未完成（当前 phase: {state.get('phase')}）")
        return False

    # 整合
    print(f"\n📝 Phase 3: 整合所有节点内容")
    r = orchestrate_phase3(paper_name)
    if not r.get("ok"):
        print(f"❌ Phase 3 整合失败: {r.get('error')}")
        return False

    # HIL #6: 整合版预览
    content = r.get("content", "")
    word_count = r.get("word_count", 0)
    print(f"\n📊 整合版生成: {word_count} 字符")
    print(f"\n--- 前 1000 字预览 ---")
    print(content[:1000])
    print(f"\n...（共 {word_count} 字符）...")

    hil_pause("6", "整合版是否接受？",
             {"1": "确认（进入 Phase 5 导出）",
              "2": "取消（修改）"})

    # Phase 5 export
    print(f"\n📤 Phase 5: 导出 Word")
    r = confirm_phase3_and_export(paper_name)
    if not r.get("ok"):
        print(f"❌ Phase 5 export 失败: {r.get('error')}")
        return False

    output_path = r.get("output_path")
    print(f"✅ 论文已导出: {output_path}")
    print(f"   字数: {r.get('word_count')}")

    # HIL #9: Word 输出确认
    hil_pause("9", "Word 文档是否接受？\n"
                  "（如需 md → docx 转换，请运行 md2docx_strict.py）",
             {"1": "接受（流程结束）",
              "2": "修改"})

    print(f"\n🎉 流程结束")
    return True


# ============================================================
# Main
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description="thesis-workflow v2 真实入口 CLI（v2.0.6 新增）"
    )
    parser.add_argument("paper_name", help="论文标识（与 orchestrate_state 文件名一致）")
    parser.add_argument("--phase", choices=["phase1", "phase2", "phase3", "auto"],
                       default="auto", help="指定阶段")
    parser.add_argument("--status", action="store_true", help="仅查看状态")
    parser.add_argument("--llm", help="LLM 调用函数（暂未实现交互式注入，留给 Phase 2 集成）")
    args = parser.parse_args()

    paper_name = args.paper_name

    print(f"=== thesis-workflow v2.0.6 CLI ===")
    print(f"  论文: {paper_name}")
    print(f"  模式: {args.phase}")

    if args.status:
        get_paper_status(paper_name)
        return 0

    llm_func = None  # 默认 None，Phase 2 必传
    if args.phase in ("phase2", "auto"):
        if not args.llm:
            print("⚠️ Phase 2 需要 llm_func")
            print("   当前实现：run_workflow.py 通过 stdin 与用户交互")
            print("   LLM 注入暂未实现（v2.0.6 + 后续 milestone）")
            print("   如需 Phase 2，请用 Python API 调用 orchestrate_phase2()")
            return 1

    # 按 phase 执行
    if args.phase in ("phase1", "auto"):
        if not run_phase1(paper_name, llm_func):
            return 1

    if args.phase in ("phase2", "auto"):
        if not run_phase2(paper_name, llm_func):
            return 1

    if args.phase in ("phase3", "auto"):
        if not run_phase3(paper_name):
            return 1

    print(f"\n🎉 全部完成")
    return 0


if __name__ == "__main__":
    sys.exit(main())
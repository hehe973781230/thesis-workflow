#!/usr/bin/env python3
"""
gatekeeper.py — 论文写作质量与流程门禁

角色：
  - 质量门禁：loop_self_check 校验
  - 流程门禁：Phase 切换合法性检查
  - 结果门禁：开题承诺 vs 产出对齐
  - 出口门禁：最终输出唯一出口
  - 异常日志：所有异常记录到 _gk_exception_log.json

用法：
  python3 gatekeeper.py --paper <论文名> --mode <check|daemon|report>
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

WORKSPACE = Path(os.environ.get(
    "THESIS_WORKSPACE",
    os.path.expanduser("~/.openclaw/workspace")
))

# ============================================================
# 异常日志管理
# ============================================================

def load_exception_log(paper_name: str) -> Dict:
    """加载或初始化异常日志"""
    log_path = _gk_log_path(paper_name)
    if log_path.exists():
        with open(log_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "paper_name": paper_name,
        "start_time": datetime.now().strftime("%Y-%m-%dT%H:%M:%S+08:00"),
        "exceptions": [],
        "summary": {"total": 0, "pending": 0, "fixed": 0, "skipped": 0}
    }


def save_exception_log(paper_name: str, log: Dict) -> None:
    """保存异常日志"""
    log_path = _gk_log_path(paper_name)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)


def _gk_log_path(paper_name: str) -> Path:
    return WORKSPACE / "papers" / paper_name / "_gk_exception_log.json"


def add_exception(
    paper_name: str,
    phase: str,
    node_id: str,
    gate_type: str,
    gate_name: str,
    description: str,
    severity: str = "error",
) -> int:
    """
    记录一个新异常，返回 exception id
    """
    log = load_exception_log(paper_name)
    exc_id = len(log["exceptions"]) + 1
    exc = {
        "id": exc_id,
        "timestamp": datetime.now().strftime("%Y-%m-%dT%H:%M:%S+08:00"),
        "phase": phase,
        "node_id": node_id,
        "gate_type": gate_type,
        "gate_name": gate_name,
        "description": description,
        "severity": severity,
        "status": "pending",
        "action_taken": None,
        "repaired_at": None,
        "repaired_by": None,
        "user_notified": False,
        "user_decision": None,
    }
    log["exceptions"].append(exc)
    log["summary"]["total"] += 1
    log["summary"]["pending"] += 1
    save_exception_log(paper_name, log)
    return exc_id


def resolve_exception(
    paper_name: str,
    exc_id: int,
    action: str,       # "fixed" | "skipped" | "manual"
    resolved_by: str = "user",
) -> bool:
    """
    更新异常状态为已处理
    """
    log = load_exception_log(paper_name)
    for exc in log["exceptions"]:
        if exc["id"] == exc_id:
            exc["status"] = "resolved"
            exc["action_taken"] = action
            exc["repaired_at"] = datetime.now().strftime("%Y-%m-%dT%H:%M:%S+08:00")
            exc["repaired_by"] = resolved_by
            break
    # 重新统计
    summary = {"total": log["summary"]["total"], "pending": 0, "fixed": 0, "skipped": 0}
    for exc in log["exceptions"]:
        if exc["status"] == "pending":
            summary["pending"] += 1
        elif exc["action_taken"] == "fixed":
            summary["fixed"] += 1
        elif exc["action_taken"] in ("skipped", "user_confirmed_skip"):
            summary["skipped"] += 1
    log["summary"] = summary
    save_exception_log(paper_name, log)
    return True


# ============================================================
# 流程门禁
# ============================================================

def check_process_gate(paper_name: str, state: Dict) -> List[Dict]:
    """
    检查 Phase 切换合法性，返回问题清单
    """
    issues = []
    phase = state.get("phase", "")
    phase1_3_status = state.get("phase1_3_status", "")
    phase3_5_status = state.get("phase3_5_status", "")

    # Phase 1 → Phase 2 必须 phase1_3_confirmed
    if phase == "phase2" and phase1_3_status != "confirmed":
        issues.append({
            "gate": "process_gate",
            "description": f"Phase 1.3 尚未确认（状态={phase1_3_status}），禁止进入 Phase 2",
            "severity": "error",
        })

    # Phase 3.5 必须 phase1_3_confirmed
    if phase == "phase3.5" and phase1_3_status != "confirmed":
        issues.append({
            "gate": "process_gate",
            "description": f"Phase 1.3 尚未确认，禁止进入 Phase 3.5",
            "severity": "error",
        })

    # Phase 4 必须 phase3_5_passed
    if phase == "phase4" and phase3_5_status != "passed":
        p0_count = len(state.get("phase3_5_result", {}).get("p0", []))
        issues.append({
            "gate": "process_gate",
            "description": f"HIL #8：Phase 3.5 尚未通过（当前 P0={p0_count}），禁止进入 Phase 4",
            "severity": "error",
        })

    # completed_nodes 检查
    completed = state.get("completed_nodes", [])
    if len(completed) != len(set(completed)):
        issues.append({
            "gate": "process_gate",
            "description": "completed_nodes 中存在重复节点ID",
            "severity": "warning",
        })

    return issues


# ============================================================
# 质量门禁（基于 loop_self_check）
# ============================================================

def check_quality_gate(paper_name: str) -> List[Dict]:
    """
    运行 loop_self_check 全量校验，返回问题清单
    """
    issues = []
    paper_dir = WORKSPACE / "papers" / paper_name

    # 尝试找整合版或最新章节内容
    possible_files = [
        paper_dir / f"{paper_name}_final.md",
        paper_dir / f"{paper_name}_整合版.md",
    ]
    md_path = None
    for pf in possible_files:
        if pf.exists():
            md_path = pf
            break

    if not md_path:
        return [{"gate": "quality_gate", "description": "未找到论文 Markdown 文件", "severity": "warning"}]

    try:
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from loop_self_check import run_checks
        with open(md_path, "r", encoding="utf-8") as f:
            content = f.read()
        results = run_checks(content)
        for r in results:
            if not r.get("passed", True):
                issues.append({
                    "gate": "quality_gate",
                    "gate_name": r.get("name", "unknown"),
                    "description": r.get("message", "检查未通过"),
                    "severity": "error",
                })
    except Exception as e:
        issues.append({
            "gate": "quality_gate",
            "description": f"loop_self_check 执行失败：{e}",
            "severity": "warning",
        })

    return issues


# ============================================================
# 巡检
# ============================================================

def inspect_state(paper_name: str) -> List[Dict]:
    """
    定期巡检当前 state，返回问题清单
    """
    issues = []
    state_path = WORKSPACE / "papers" / paper_name / "_orchestrate_state.json"
    if not state_path.exists():
        return [{"gate": "inspect", "description": "状态文件不存在", "severity": "error"}]

    with open(state_path, "r", encoding="utf-8") as f:
        state = json.load(f)

    # 流程门禁
    issues.extend(check_process_gate(paper_name, state))

    # Phase 3.5 轮次异常
    phase3_5_round = state.get("phase3_5_round", 0)
    if phase3_5_round > 5:
        issues.append({
            "gate": "inspect",
            "description": f"Phase 3.5 已连续 {phase3_5_round} 轮未通过，建议人工介入",
            "severity": "warning",
        })

    return issues


# ============================================================
# 汇报生成
# ============================================================

def generate_report(paper_name: str) -> str:
    """生成流程结束后的异常汇报"""
    log = load_exception_log(paper_name)
    s = log["summary"]

    lines = [
        "🤖 [Gatekeeper] 流程结束 — 异常报告",
        "",
        f"本次流程共发现 {s['total']} 个异常：",
        "",
    ]

    if s["total"] == 0:
        lines.append("✅ 无异常，流程正常结束")
        return "\n".join(lines)

    for exc in log["exceptions"]:
        status_icon = "✅" if exc["status"] == "resolved" else "⏳"
        lines.append(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        lines.append(f"【异常 #{exc['id']}】{status_icon}")
        lines.append(f"时间：{exc['timestamp']}")
        lines.append(f"环节：{exc['phase']}")
        if exc["node_id"]:
            lines.append(f"节点：{exc['node_id']}")
        lines.append(f"类型：{exc['gate_type']} - {exc['gate_name']}")
        lines.append(f"详情：{exc['description']}")
        if exc["action_taken"]:
            lines.append(f"处理：{exc['action_taken']}")
        lines.append("")

    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    lines.append("汇总：")
    lines.append(f"  总异常：{s['total']}")
    lines.append(f"  已修复：{s['fixed']}")
    lines.append(f"  已跳过：{s['skipped']}")
    lines.append(f"  待处理：{s['pending']}")
    lines.append("")
    lines.append("请选择：")
    lines.append("  [1] 查看异常详情")
    lines.append("  [2] 优化 skill 配置")
    lines.append("  [3] 结束")

    return "\n".join(lines)


# ============================================================
# CLI 入口
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="Gatekeeper 门禁")
    parser.add_argument("--paper", required=True, help="论文名")
    parser.add_argument("--mode", default="check", choices=["check", "daemon", "report"])
    parser.add_argument("--phase", default="", help="当前 Phase（用于 check 模式）")
    parser.add_argument("--node", default="", help="当前节点 ID")
    args = parser.parse_args()

    paper_name = args.paper

    if args.mode == "check":
        # 单次检查
        issues = []
        state_path = WORKSPACE / "papers" / paper_name / "_orchestrate_state.json"
        if state_path.exists():
            with open(state_path, "r", encoding="utf-8") as f:
                state = json.load(f)
            issues.extend(check_process_gate(paper_name, state))
        issues.extend(check_quality_gate(paper_name))

        if issues:
            print(f"⚠️ 发现 {len(issues)} 个问题：")
            for i, iss in enumerate(issues, 1):
                print(f"  {i}. [{iss['gate']}] {iss['description']}")
            # 记录到日志
            for iss in issues:
                if iss.get("severity") == "error":
                    add_exception(
                        paper_name=paper_name,
                        phase=args.phase,
                        node_id=args.node,
                        gate_type=iss["gate"],
                        gate_name=iss.get("gate_name", ""),
                        description=iss["description"],
                        severity=iss.get("severity", "error"),
                    )
            return 1
        else:
            print("✅ 门禁检查通过")
            return 0

    elif args.mode == "daemon":
        # 常驻巡检
        print(f"Gatekeeper 启动，监听论文：{paper_name}")
        print("每 30 秒巡检一次，按 Ctrl+C 停止")
        try:
            while True:
                state_path = WORKSPACE / "papers" / paper_name / "_orchestrate_state.json"
                if state_path.exists():
                    issues = inspect_state(paper_name)
                    for iss in issues:
                        print(f"[{datetime.now().strftime('%H:%M:%S')}] ⚠️ {iss['description']}")
                        if iss.get("severity") == "error":
                            add_exception(
                                paper_name=paper_name,
                                phase="",
                                node_id="",
                                gate_type=iss["gate"],
                                gate_name="",
                                description=iss["description"],
                                severity=iss.get("severity", "error"),
                            )
                time.sleep(30)
        except KeyboardInterrupt:
            print("\nGatekeeper 停止")
            return 0

    elif args.mode == "report":
        # 生成最终汇报
        print(generate_report(paper_name))
        return 0


if __name__ == "__main__":
    sys.exit(main())

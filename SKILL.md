---
name: thesis-workflow-v2
description: "v2 新框架（beta）：Phase 3.5/4/5 + BGE向量匹配 + multi-search。v2 重构为 outline-anchored 设计 + 9 HIL 节点 + 真实 CLI 入口。⚠️ 测试版，需独立安装（不覆盖 v1）。"
metadata:
  clawdbot:
    emoji: "📝"
    version: "2.1.1-beta.4"   # 单一真实来源，发布前必须先改这里。发布规则见 scripts/release.py
    requires: {}
    os: ["linux", "darwin", "win32"]
---

# MBA/学术论文多Agent协作工作流

> 完整文档见：`references/checklist.md`（学术规范清单）、`references/loop-design.md`（Loop 设计原理）

## ⚠️ 触发规则

当用户请求生成 Word 文档且满足以下任一条件时，**必须**调用本 skill 的 Word 输出流程，不得使用简单 md2docx 脚本：
- 输入文件路径匹配：`论文*.md`、`*thesis*.md`、`*dissertation*.md`
- 上下文中存在「论文」「MBA」「答辩」「开题」等关键词
- 用户明确要求导出 `.docx` 格式且文件性质为学术论文

**正确流程：** 写作语法预检 → Review Agent 终审（`scripts/loop_self_check.py` 校验通过）→ `scripts/md2docx_strict.py` 合规转换 → Word 输出

## 核心架构

```
Phase 1（规划）→ Phase 2（逐节点写作）→ Phase 2.5（内容确认）
→ Phase 3（整合）→ Phase 3.5（学术深度评审）
→ Phase 4（修复）→ Phase 5（终审 + Word 输出）
```

⚠️ **阶段强制顺序：** 全部 Phase 必须按顺序执行，不得跳过。Phase 2.5（人工确认门槛）和 Phase 3.5（深度评审）是固定节点，不得跳过。

## Agent 设计原则

**每个 Agent 只做一件事。** Agent 间通过文件传递结果，不共享上下文。Orchestrator 专注调度，不执行执行性工作。

| Agent | 调用方式 | 主责 |
|-------|---------|------|
| **Orchestrator** | 当前 session | 调度 / 推进 / 决策 |
| **NodeWriter** | `sessions_spawn` | 逐节点内容生成 |
| **Reviewer** | `sessions_spawn` | Phase 3/5 规则型审核 |
| **DeepReviewer** | `sessions_spawn` | Phase 3.5 学术深度评审 |
| **Integrator** | `sessions_spawn` | Phase 4 整合方案 |
| **WordAgent** | `exec python3` | md2docx执行 + 格式校验 |

## 关键实现说明

### 公司信息处理

- 用真实公司名搜索公开数据，填入正文时替换为代号（A公司/B公司）
- 搜索 prompt 用真实名，输出 prompt 用代号
- 映射关系不进入最终文档

### 检索同步规则

所有 Phase 调用数据查询工具（`web_search` / `academic-research`）时，必须：
1. 同步输出工具名称 + 查询条件 + 结果摘要（<50字）
2. Subagent 用 `sessions_send` 向主 session 发送同步
3. 大型检索完成后输出结构化结果摘要

### 数据查询工具（v2 多工具并行策略）

> **核心原则**：4个工具并行发出，取长补短，去重排序，任意失败不阻断。
> `web_search` 等内置工具 Agent 直接调用，无需经过 Python 层包装。

**工具矩阵：**

| 工具 | 来源 | 适用场景 |
|------|------|---------|
| `web_search` | OpenClaw 内置（头条搜索） | 行业数据、市场规模、新闻动态 |
| `tavily_search` | Tavily MCP（mcporter） | 结构化摘要、权威来源 |
| `arxiv_search` | arXiv MCP（mcporter） | 前沿学术论文、技术细节 |
| `openalex_search` | scholar-search.py（OpenAlex） | 学术文献、引用分析 |

**Python 层调用（`research_tools.py`）：**
```python
from research_tools import quick_search, research_enrich

# 快速检索（返回文本，供注入 prompt）
result = quick_search("竞争战略 市场规模 2024")

# 节点级检索（自动取 outline 中的 research_keywords）
ctx = research_enrich(node_id, paper_name)
```

**并行执行逻辑：**
1. 四工具同时发出，不串行等待
2. 各工具独立降级（超时/失败 → 静默忽略）
3. 结果按 URL 去重 + score 排序
4. 输出格式：`[来源] 标题\n  摘要\n  URL`

**Agent 视角：**
- Agent 可继续直接使用 `web_search(query=...)` 等内置工具
- `quick_search()` 是 Python 层的补充，用于学术/论文场景的结构化检索

## Phase 详解

### Phase 1：规划与定稿

通过问答输出确认清单，用户逐项确认后方可动笔。

**红色星标项（必填）：**
- ⭐ 实际公司名称（仅用于数据检索，正文以A公司/B公司呈现，不进入公开文档）
- ⭐ 大纲结构（7章大纲逐章确认）
- 论文基本信息（题目/作者/专业/学位类型/答辩年份）

→ 生成「写作任务书」用户签收后进入 Phase 2。

### Phase 2：逐节点写作

**前置检查：** Phase 1 必填项已确认

Orchestrator 遍历 outline 树中的每个节点，调用 `write_single_node()` 逐个生成内容。
每个节点写作前通过 `context_builder.py` 构建 prompt 包，自动注入：
- 承接上文（auto bridge）
- 分析维度建议（规则推导）
- 开题报告方向参考（content_hint）
- 行业数据参考（quick_search 多工具检索）

**Phase 2 强制检索要求**（关键词中的 `{论文主题行业}` 由 Orchestrator 自动提取）：
- 第3章 PESTEL 分析前 → 多工具并行搜索「{论文主题行业} 市场规模/趋势/政策」
- 第3章 五力模型分析前 → 多工具并行搜索「{论文主题行业} 主要竞争对手/市场份额」
- 战略理论部分 → 多工具并行搜索「{论文主题行业} 竞争战略 应用」
- 每章至少 1 个引用标注来源，全文检索记录 ≥ 3 次
- **多工具并行检索**：调用 `quick_search()` 或 `research_enrich()`，结果自动去重排序

**状态文件机制：** `_orchestrate_state.json`（`scripts/state_manager_v2.py`）

→ 全部节点写完且字数达标后进入 Phase 2.5（内容确认）。

### Phase 3：整合

Reviewer 对整合版论文进行审核。审核维度：格式 / 大纲 / 内容准确性 / 查重风险 / 学术规范 / 写作语法。

### Phase 3.5：深度学术评审（固定节点）

DeepReviewer 对 Phase 3 报告进行二次审查，输出 P0/P1/P2 分级问题清单。P0 问题进入修订 → 重审闭环（见审核 Loop）。

### Phase 4：整合

Integrator 汇总 Phase 3 + Phase 3.5 全部评审结果，制定整合方案。核心原则：取长补短，不为统一而破坏内容质量。

**自动验证：** 整合版运行 `python3 scripts/loop_self_check.py` 校验，100%通过方可输出 Word。

### Phase 5：终审与输出

- Phase 5：Reviewer 终审
- Phase 5.1：[可选] `humanize-chinese` skill 去AI味
- Phase 5.2：`python3 scripts/md2docx_strict.py` 生成 Word 文档

## Orchestrator 生命周期管理

### 真实入口（v2.0.6 新增）

> **执行脚本**：`scripts/run_workflow.py`（v2 真实入口 CLI）
> **状态文件**：`~/.openclaw/workspace/{paper_name}/_orchestrate_state.json`
> **设计原则**：驱动状态机 + 9 个 HIL 节点 hard pause

```bash
# 仅查看状态
python3 scripts/run_workflow.py <paper_name> --status

# auto 模式：根据 state 自动判断下一步
python3 scripts/run_workflow.py <paper_name> --phase auto

# 指定阶段
python3 scripts/run_workflow.py <paper_name> --phase phase1
python3 scripts/run_workflow.py <paper_name> --phase phase2  # 需 --llm
python3 scripts/run_workflow.py <paper_name> --phase phase3
```

### Python API（v2.0.9）

```python
import sys
sys.path.insert(0, "scripts")
from orchestrator_v2 import orchestrate, write_single_node, apply_user_decision

# Phase 1.1: 解析开题报告（docx 或文本）
r = orchestrate(paper_name, action="phase1_1_init",
                input_type="docx", input_data="path/to/proposal.docx")

# Phase 1.2: 确认大纲（用户 HIL）
r = orchestrate(paper_name, action="phase1_confirm")

# Phase 1.3: 提交开题报告归因
r = orchestrate(paper_name, action="phase1_3_submit",
                docx_path="path/to/proposal.docx", llm_func=my_llm)

# Phase 1.3: 确认归因（用户 HIL）
r = orchestrate(paper_name, action="phase1_3_confirm")

# Phase 2: 逐节点写作（v2.0.4 推荐调用模式）
for node_id in next_nodes:
    r = write_single_node(paper_name, node_id, llm_func=my_llm,
                          reviewer_func=my_reviewer)  # 独立评审

# Phase 3: 整合
r = orchestrate(paper_name, action="phase3_review")

# Phase 3.5: 深度学术评审（自动进入 Phase 3.5/4/5 链）
# Phase 3 → orchestrate_phase3_5() → P0修复 → Phase 4 → Phase 5
r = orchestrate(paper_name, phase="phase3", action="phase3_export")

# Phase 5: Word 输出提示
print(r.get("message", ""))
```

### HIL 节点（v2.0.6 完整 9 个）

| # | 触发位置 | 检查内容 | 决策 |
|---|---------|---------|------|
| 1 | Phase 1.1 后 | 大纲结构 | 接受 / 修改 |
| 2 | Phase 1.3 后 | 归因结果 | 接受 / 调整 hint |
| 3 | 在 write_single_node() 写入单节点前 | info_scarcity | 提供 hint / AI 生成 / 跳过 |
| 4 | Phase 2 评审后 | quality=medium/low | 接受 / 重写 |
| 5 | Phase 2 完成后 | 章节内容预览 | 通过 / 修改 |
| 6 | Phase 3 整合后 | 整合版内容 | 通过 / 修改反馈 |
| 7 | Phase 3.5 P0 修复 | 超 3 轮未收敛 | 接受 / 继续修订 |
| 8 | Phase 4 整合方案 | 方案是否接受 | 接受 / 修改 |
| 9 | Phase 5.2 后 | Word 输出 | 导出 / 修改 |

### v2.0.6 拦截规则（enforcement）

- **拍板 #1 强制**：Phase 1.3 不允许跳过
  - `orchestrate(action="phase1_3_skip")` → 拦截，返回 `拍板 #1 强制不允许跳过`
  - `skip_phase1_3()` 函数体加 `MBA_THESIS_PRODUCTION=1` env guard + 必填 `reason`/`operator` + audit log
- **B-2 幂等保护**：`outline_update_status()` 默认拒绝覆盖已 completed 节点的内容
  - 需重写请调 `write_single_node(bypass_scarcity=True)` 重走标准流程
  - 或显式传 `force=True`（调试用）
- **独立 Reviewer**：`write_single_node()` 接受 `reviewer_func` 参数
  - 防止生成和评审使用同一 LLM（自我审核）
  - 默认 reviewer_func == llm_func 时发警告
  - 调试场景可显式 `allow_self_review=True`

### 审核 Loop 自动重审

Phase 3.5 完成 → orchestrator 解析 P0 计数 → 有 P0？→ 自动进入修订
→ 修订完成 → 自动回到 Phase 3.5 重审 → 连续 2 轮无新 P0 → 通过
→ 超过 3 轮 → HIL 暂停

### Phase 内部自检

每 Phase 完成后，orchestrator 自动运行 `loop_self_check.py` 校验：
```bash
python3 scripts/orchestrator.py 状态文件.json --validate
```
校验失败 → RETRY 打回 → Agent 修复 → 再次校验（最多 3 次）

## ⚠️ Loop 设计原则

> 详细原理见 `references/loop-design.md`

| Loop 元素 | 作用 | 终止条件 |
|----------|------|---------|
| **Orchestrator Loop** | 每 Phase 完成后自动判断下一步 | 全部 7 Phase 完成 |
| **Phase 内部自检 Loop** | Observe → Think → Act → Verify 四步 | Guardrails 100% 通过 |
| **审核 Loop** | 审→改→重审→连续2轮无新P0→通过 | 连续 2 轮无新 P0/P1 |
| **Guardrails 校验** | `scripts/loop_self_check.py` 10项自动化检查 | 全部通过 |
| **Verification Loop** | Word 输出后自动校验格式 | Word 格式 100% 通过 |

**最大重试：** 每个 Loop 3 次，超过则强制 Human-in-the-loop。
**Human-in-the-loop检查点：** Phase 1/2.5/4/5.2 末尾，必须用户确认才能推进。

## Guardrails 校验（10 项）

```bash
python3 scripts/loop_self_check.py --file 论文_xxx.md   # 单文件
python3 scripts/loop_self_check.py --phase 2 --workspace ~/.openclaw/workspace/  # Phase 级别
python3 scripts/loop_self_check.py --file 论文_xxx.docx --verify-docx           # Word 校验
```

| # | 校验项 | 失败阻断 |
|---|--------|---------|
| 1 | 章节完整性（7章齐全） | Phase 2/4 |
| 2 | 字数门槛（每章≥100行） | Phase 2/4 |
| 3 | 参考文献存在 | Phase 4 |
| 4 | 无 `## 第X章` 混合格式 | Phase 2/4 |
| 5 | 无 `**正文加粗**` | Phase 2/4 |
| 6 | 引用完整性（逐章≥1处，全文≥10处） | Phase 2/4 |
| 7 | 三线表列数一致 | Phase 4 |
| 8 | 表标题在表上方 | Phase 4 |
| 9 | 无合并残留（`===END===`） | Phase 4 |
| 10 | 核心章节关键词（第5章战略/第6章实施） | Phase 2.5 |

## Word 输出质量保障

### 正文加粗过滤
- 正文段落（非标题级）内的 `**text**` → 去掉 `**` 转为普通文字
- 表格单元格内的 `**` 同步清除（`scripts/md2docx_strict.py` 的 `_strip_bold()` 函数）

### 三线表格式
- 顶线 1.5 磅 / 表头底线 0.75 磅 / 底线 0.5 磅，无竖线

### 分页
- 每章标题前插入分页符（首章跳过），附录/致谢前分页

## 附录：脚本与文档结构

```
thesis-workflow/
├── SKILL.md                    ← 本文件（简版触发器 + 核心逻辑）
├── README.md / README_EN.md    ← 安装/使用说明
├── CHANGELOG.md                ← 版本日志
├── config.template             ← 配置模板
├── install.sh                  ← 安装脚本
├── .clawhubignore / .github/workflows/skill-publish.yml
├── scripts/
│   ├── md2docx_strict.py       ← Word 合规转换
│   ├── loop_self_check.py      ← Guardrails 自动化校验（10项）
│   ├── state_manager.py        ← 状态文件管理
│   └── tests/                  ← 单元测试
└── references/
    ├── checklist.md            ← 学术规范人工对照清单
    └── loop-design.md          ← Loop 设计原理说明
```

## 附录 A：论文项目运行 Checklist（agent 必遵守）

> **来源**：v7.0 事故复盘 → 龙哥 22:19 反馈 / 2026-06-29  
> **适用对象**：跑 thesis-workflow-v2 的任何 agent（含 main session 和 isolated）  
> **生效日期**：2026-06-29 起

### A.1 触发即汇报

启动任何 thesis-workflow-v2 阶段前，先发一条汇报：
- 论文名 / 阶段 / 启动时间 / 监考路径（如有 PID/log）
- 5-30 字，简洁不啰嗦

### A.2 阶段切换必汇报

- Phase 1 → Phase 2（写作开始）
- Phase 2 → Phase 3（整合开始）
- Phase 3 → Phase 3.5（评审开始）
- Phase 3.5 → Phase 4 / Phase 5（终审/导出）

每切换发一条"已到 X 阶段"短汇报。

### A.3 长跑阶段主动节拍

Phase 2 写作阶段（如有 background 任务）：

| 进度节点 | 必汇报 |
|---------|--------|
| 启动 | ✅ |
| 完成 25% | ✅ |
| 完成 50% | ✅ |
| 完成 75% | ✅ |
| 完成 100% / 失败 | ✅ |

- 每次汇报含当前 `completed_nodes` 数量
- 用 `cat _orchestrate_state.json` 拿实时数据

### A.4 异常即停 + 主动汇报

触发任一异常情况，**立即**停下来汇报（不等用户问）：
- content_hint 覆盖率 < 50% → Phase 1.3 异常
- 大量节点 failed → Phase 2 失败
- 整合版字数异常（< 30k 或 > 200k）
- outline_state 节点结构与 _orchestrate_state 不一致

### A.5 完成必汇报（含产出清单）

论文交付时，必汇报：
- 终稿路径
- 字数（中文字数 / 总字符数）
- 章节完成情况
- 异常/缺陷（如有）
- 邮件/通知状态

### A.6 红线禁止（继承自 AGENTS.md）

- ❌ 跳过 run_workflow.py 操作状态文件
- ❌ 不汇报长任务进度
- ❌ Phase 1.3 / 1.1 直接调用 Python API
- ❌ 状态文件手工修改 phase*_status 字段

### A.7 辅助工具（可选）

如需手动查看状态，可用：
```bash
python3 ~/.openclaw/scripts/thesis_progress_reporter.py --idle-minutes 60
```

脚本全局通用，跨 macOS/Linux/Windows，纯 stdlib。idle 60min 自动静默。

## 附录 B：已批准改进方案 — 大纲约束注入（已实施 2026-06-30）

> **来源**：v7.0 事故复盘 → 龙哥 22:19 反馈，Q3=A / 2026-06-29  
> **实施状态**：✅ 已实施并验收（2026-06-30）
> **注意**：本附录不绑具体版本号。以 SKILL.md frontmatter 的 `metadata.clawdbot.version` 为当前 skill 真实版本。

### B.1 背景

v7.0 Phase 2 跑题事故显示：当 `node.content_hint` 为空时，LLM 写作完全依赖章节标题推断上下文，导致 LLM 写出通用 MBA 论文（"数字经济转型"），跑偏具体研究对象（A 公司 / vivo / 互联网分发）。

### B.2 目标

当 `node.content_hint` 为空时，**不**直接让 LLM 写，而是构造一个"大纲骨架 + 反面警示"的 prompt 约束，确保不跑题。

### B.3 实施方案

修改 `scripts/context_builder.py` 的 `build_prompt_package()` 函数：

```python
# 现有逻辑
content_hint = current.get("content_hint", "").strip()

# v2.x.x 新增（v7.0 跑题事故修复）：当 content_hint 为空时，注入大纲骨架 + 反面警示
if not content_hint and state:
    outline_skeleton = _build_outline_skeleton(state, node_id)
    paper_subject = _extract_paper_subject(paper_name, state)
    warning_block = _build_no_runoff_warning(paper_subject)
    content_hint = f"{warning_block}\n\n{outline_skeleton}"

package = { ..., "content_hint": content_hint, ... }
```

#### B.3.1 新增辅助函数

```python
def _extract_paper_subject(paper_name: str, outline_state: Optional[Dict] = None) -> str:
    """提取论文主题描述（用于 warning 主题锁定）

    策略：
      1. 优先从 outline_state["outline_tree"]["metadata"]["paper_title"] 读
      2. 否则从 paper_name 去掉版本号后缀
      3. 兜底返回 paper_name
    """
    if outline_state:
        try:
            title = outline_state.get("outline", {}).get("outline_tree", {}).get("metadata", {}).get("paper_title")
            if title and title.strip():
                return title.strip()
        except Exception:
            pass
    import re as _re
    subject = _re.sub(r'(_v\d+(?:\.\d+)*|_final|_\d{8}_\d{6})+$', '', paper_name)
    return subject if subject else paper_name


def _build_outline_skeleton(outline_state: Dict, target_node_id: str) -> str:
    """构造论文大纲骨架"""
    try:
        nodes = outline_state.get("outline", {}).get("outline_tree", {}).get("nodes", [])
    except Exception:
        return ""
    lines = ["【论文完整大纲（用于提供上下文）】", ""]
    for n in nodes:
        if n.get("is_virtual"):
            continue
        level = n.get("level", 2)
        prefix = "#" * level
        lines.append(f"{prefix} {n['id']} {n.get('title', '')}")
    lines.append("")
    lines.append("【你正在写的节点】")
    target = next((n for n in nodes if n.get("id") == target_node_id), None)
    if target:
        lines.append(f"→ {target.get('title', target_node_id)}（{target_node_id}）")
    return "\n".join(lines)


def _build_no_runoff_warning(paper_subject: str = "本研究主题") -> str:
    """反面警示：明确禁止跑题

    paper_subject: 论文研究对象描述（建议从 outline metadata.paper_title 取）
    """
    return (
        f"⚠️ 主题锁定：本论文研究对象是「{paper_subject}」。\n"
        "- ✅ 围绕论文具体研究对象的真实业务场景、技术路线、客户/竞争格局等具体实体\n"
        "- ✅ 引用与论文主题相关的权威数据源（行业报告 / 学术文献 / 公司财报）\n"
        "- ❌ 严禁写成通用 MBA 模板论文（如「数字经济 / 企业数字化转型 / 战略管理一般性理论」）\n"
        "- ❌ 严禁「党的二十大报告提出…」这类脱离论文研究主题的泛泛话语\n"
        "- ❌ 严禁用「企业四要素模型 / 波特钻石模型」等通用教科书内容代替研究主题的具体业务场景"
    )
```

#### B.3.2 关键设计要点

1. **不破坏现有 `content_hint` 非空的路径**：只有当 hint 为空时才插入骨架
2. **token 成本低**：大纲骨架 < 1 KB，比塞全文 content（100 KB+）省得多
3. **覆盖完整**：即使 50 个节点 hint 全空，prompt 里仍有大纲骨架明确"我在写论文 X 章节 Y"
4. **反面警示**：LLM 习惯正面 prompt，加"❌ 严禁"反向约束效果更好

### B.4 测试用例

```python
def test_content_hint_empty_should_use_skeleton():
    """given: node.content_hint = '' when: build_prompt_package then: package['content_hint'] 含大纲骨架 + 反面警示"""
    pass

def test_content_hint_present_should_unchanged():
    """given: node.content_hint = 'A公司2024年...' when: build_prompt_package then: package['content_hint'] == 原 hint"""
    pass
```

### B.5 验收标准

- [x] `_build_outline_skeleton` 输出 < 1500 字（实测 1281 字符）
- [x] `_build_no_runoff_warning` 输出含至少 3 个 ❌ 禁止项（实测 3 个）
- [x] 现有非空 hint 路径 PASS（7.2 节点回归通过）
- [x] Phase 2 跑 1 个节点，验证 prompt 含研究主题关键词（ch1 节点验证通过）
- [x] 完整 content_hint < 2500 字（实测 1566 字符）
- [x] 警告块参数化（_build_no_runoff_warning 接受 paper_subject 参数，不再硬编码 A 公司）

### B.6 已完成行动

- [x] 代码实施（context_builder.py + 3 个新函数 + 1 段 fallback 逻辑）
- [x] 单元级验收（5+1 项 全部通过）
- [x] 文档同步（SKILL.md 附录 B 代码块与实际代码一致）
- [ ] CHANGELOG.md 同步（待 v2.0.7 升级时补充）
- [ ] README.md 改进章节（待 v2.0.7 升级时补充）
- [ ] ClawHub publish（待 v2.0.7 升级时发布）

数据来源声明：本方案生成于 2026-06-29 龙哥对话，2026-06-30 完成 P0 修复。

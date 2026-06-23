# MBA/学术论文多Agent协作工作流

📝 多Agent协作完成MBA/学术论文写作的完整工作流，支持双版本起草、审核、整合、定稿。

适用于开题报告到毕业论文的全流程。

---

## ⚠️ 当前项目双版本并行

本仓库包含 **两条独立版本线**，互不干扰、并行发布：

| 版本线 | ClawHub Slug | 当前 latest | 状态 | 文档 |
|--------|--------------|-------------|------|------|
| **v1.x**（稳定） | `thesis-workflow` | **v1.7.3** | 长期维护，仅兼容性修复 | [CHANGELOG-v1.md](./CHANGELOG-v1.md) |
| **v2.x**（新框架） | `thesis-workflow-v2` | **v2.0.6** | ⚠️ 测试版，独立测试中 | [CHANGELOG-v2.md](./CHANGELOG-v2.md) |

### 选型指南

- **生产环境 / 已有 v1 用户** → `thesis-workflow` (v1.7.3，稳定)
- **新框架 / outline-anchored / 9 HIL 体验** → `thesis-workflow-v2` (v2.0.6，测试)
- **同时跑多篇论文** → 两个都装，**可共存**

### 怎么装两个？

```bash
# v1 稳定版（不依赖本仓库）
openclaw skills install thesis-workflow

# v2 测试版
openclaw skills install thesis-workflow-v2
```

两者安装路径、状态文件、依赖互不冲突。

详见 [`references/git-workflow.md`](./references/git-workflow.md) 和 [CHANGELOG.md](./CHANGELOG.md) 索引。

---

## 核心功能

- **双版本起草**：版本H（Hermes深度逻辑链）+ 版本O（OpenClaw格式规范）
- **Phase 3 审核**：7个维度严格审核（格式/大纲/内容准确性/查重/学术规范/文献完整/写作语法）
- **Phase 3.5 学术深度评审**：3轮深度审查（宏观结构→分章节→跨章节一致性）
- **Phase 4 整合**：Review Agent 出整合方案，OpenClaw 执行
- **Phase 5 Word输出**：md2docx_strict.py 合规脚本，中英文分离字体

### v1.7 新增：Loop Agent 架构

- **自动推进**：Orchestrator Loop 自动判断下一步动作（Phase 完成 → 下一 Phase / 打回 / 提示用户）
- **自检校验**：Guardrails 脚本 10 项自动化规范检查，Phase 退出前必须 100% 通过
- **智能审核**：审核 Loop 自动重审修订内容，连续 2 轮无新 P0 视为通过
- **人工把关**：4 个强制 Human-in-the-loop 检查点，确保关键决策不跳过

## 适用场景

- MBA毕业论文（战略管理/企业分析类）
- 学术研究报告（竞争战略/行业分析类）
- 需要多轮审核、多版本整合的正式长文

## 快速开始

### 方式一：直接安装

```bash
openclaw skills install git:hehe973781230/thesis-workflow
```

### 方式二：ClawHub

```bash
openclaw skills search "mba thesis workflow"
openclaw skills install thesis-workflow
```

ClawHub 页面：https://clawhub.ai/hehe973781230/thesis-workflow

### 方式三：v2.0.6 真实入口 CLI

```bash
# 仅查看状态
python3 scripts/run_workflow.py <paper_name> --status

# auto 模式
python3 scripts/run_workflow.py <paper_name>

# Python API
python3 -c "
import sys
sys.path.insert(0, 'scripts')
from orchestrator_v2 import orchestrate, write_single_node, apply_user_decision
r = orchestrate('my_paper', action='phase1_1_init',
                input_type='docx', input_data='proposal.docx')
print(r)
"
```

### v2.0.6 调用示例（完整流程）

```python
import sys
sys.path.insert(0, "scripts")
from orchestrator_v2 import orchestrate, write_single_node, apply_user_decision

# 定义 LLM 函数（示例：OpenAI / OpenClaw session / 本地 mock）
def my_llm(prompt: str) -> str:
    # 实际场景：调 OpenAI API / Hermes CLI / subagent
    return "<generated_content>...</generated_content>"

def my_reviewer(prompt: str) -> str:
    # v2.0.6 P1-2：独立评审函数（不是 my_llm）
    return '{"quality": "high", "summary": "...", "weaknesses": [], "suggestions": []}'

# === Phase 1: 规划 ===
# 1.1 解析开题报告
r = orchestrate("my_paper", action="phase1_1_init",
                input_type="docx", input_data="proposal.docx")
# HIL #1：用户确认大纲
r = orchestrate("my_paper", action="phase1_confirm")

# 1.3 提交开题报告归因
r = orchestrate("my_paper", action="phase1_3_submit",
                docx_path="proposal.docx", llm_func=my_llm)
# HIL #2：用户确认归因
r = orchestrate("my_paper", action="phase1_3_confirm")

# === Phase 2: 逐节点写作（v2.0.4 推荐调用模式）===
import json
with open("~/.openclaw/workspace/my_paper/_outline_state.json") as f:
    outline = json.load(f)
nodes = outline["outline"]["outline_tree"]["nodes"]

for n in nodes:
    if n.get("is_virtual"):
        continue  # 跳过虚拟摘要节点
    r = write_single_node("my_paper", n["id"], llm_func=my_llm,
                          reviewer_func=my_reviewer)
    if r["action"] == "needs_user_input":
        # HIL #3：3 决策路径
        apply_user_decision("my_paper", n["id"], "2")  # 2=AI 自行生成
        r = write_single_node("my_paper", n["id"], llm_func=my_llm,
                              reviewer_func=my_reviewer, bypass_scarcity=True)
    elif r["action"] == "pending_review":
        # HIL #4：用户决策
        pass  # 业务代码处理

# HIL #5：用户确认 Phase 2 完成

# === Phase 3: 整合 + 导出 ===
r = orchestrate("my_paper", action="phase3_review")  # HIL #6
r = orchestrate("my_paper", action="phase3_export")   # HIL #9
print(f"最终论文: {r['output_path']}")
```

## 工作流程

```
用户 → Phase 1（确认清单）→ Phase 2（双版本起草）→ Phase 2.5（用户确认）
     → Phase 3（审核）→ Phase 3.5（学术深度评审）→ Phase 4（整合）→ Phase 5（终审定稿）
     → [Phase 5.1 去AI味] → Phase 5.2（Word输出）
```

## v1.7.6 新增

- **Orchestrator Phase 1.3 集成**：原 Phase 1 只走「目录确认」直接进 Phase 2，**跳过了开题报告归因**。现在强制走 Phase 1.3：用户上传开题报告 → 自动提取内容 → AI 归因到目录节点 → 细粒度展示每个节点的 `content_hint` + `matched_paragraphs` → 用户可手动调整 → 确认后进 Phase 2
- **Phase 1.3 状态机**：用枚举字段 `phase1_3_status = "pending|submitted|confirmed|skipped"`，拍板 #1 强制：必须 `confirmed` 才能进 Phase 2
- **Orchestrator 入口新增 5 个 action**：`phase1_confirm` / `phase1_3_submit` / `phase1_3_update_hint` / `phase1_3_confirm` / `phase1_3_skip`
- **单元测试扩充**：增加 10 个测试用例（总 63 个），覆盖完整状态机 + 用户调整 + 强制检查 + 端到端集成

## v1.7.5 新增

- **写作前信息检查**（增强项4）：节点写作前自动检查 3 项信息源（content_hint / user_hints / bridge），任一为空（标准 A）→ 返回 `action="needs_user_input"`，Orchestrator 询问用户 3 个选项：用户提供 hint / AI 自行生成 / 跳过节点
- **content_hint 完整链路**：`extract_content_hints()` 提取 → `save_content_hints_to_outline()` 写入 state → `build_prompt_package()` 读取并加 `## 开题报告方向参考` section，LLM 基于开题报告写作更精准
- **单元测试扩充**：增加 8 个测试用例（总 53 个），含完整决策路径 + 端到端闭环

## v1.7.4 新增

- **跨父节点 Bridge — 章节摘要节点**（增强项1）：解决 `2.1` 找不到 `1.2` key_conclusion 的 bridge 断裂问题。每个 L1 章节末尾自动插入虚拟节点 `__ch{N}_summary__`，吸收本章所有 L2/L3 关键结论，LLM 合成 200-300 字摘要，为下一章节提供承接。
- **三级 Bridge 优先级**：`generate_bridge()` 新增 P3 fallback 链：P1 前序节点 → P2 父节点 → P3 上一章节虚拟摘要
- **LLM 失败安全降级**：`synthesize_chapter_summary()` LLM 调用失败时返回 `action="ask_user"`，Orchestrator 可收集用户手写摘要，不降级拼接错误结论
- **单元测试扩充**：增加 20 个测试用例（总 45 个），含完整端到端集成测试

## v2.0.0 🎉

**重大变更（破坏性）**：从 v1.7.3 升级是破坏性升级。

- **Phase 1.3 强制流程**：必须上传开题报告 docx 或粘贴目录文本，确认归因后才能进 Phase 2
- **outline_state 结构变化**：每个 L1 章节末尾自动插入虚拟节点 `__ch{N}_summary__`；节点字段新增 `content_hint`
- **orchestrate_state 新增 5 个 phase1_3_* 字段**（枚举字段 `pending|submitted|confirmed|skipped`）
- **generate_bridge 三级降级链**：P1 前序节点 → P2 父节点 → P3 上一章节虚拟摘要（新增）
- **写作前信息检查**：`check_info_scarcity()`，content_hint / user_hints / bridge 任一为空 → 返回 `action="needs_user_input"` + 3 决策路径

**新增能力**：

- **Step 9** — 跨父节点 Bridge：章节摘要节点 + P3 fallback
- **Step 10** — 写作前信息检查：3 项信息源 + 标准 A + 3 决策路径
- **Step 11** — Orchestrator Phase 1.3 集成：docx/text 解析入口 + 归因状态机
- **Step 12** — 全链路集成测试

**迁移指南**：详见 `CHANGELOG.md` v2.0.0 章节。

总测试数 **72 个**，全部通过 ✅。详见 `CHANGELOG.md`。

## v2.0.1 🐛

- **Bug 修复**：`_get_prev_chapter_summary()` 对 L3 首节点误判（增加 `parent_id != chapter_id` 过滤）
- **方案 C 端到端验证（按龙哥拍板）**：
  - 思路：方案 A（mock 边界） + 方案 B（真实样本）精华
  - 选项 X：扩到现有 `test_full_workflow.py`（不新建文件）
  - 推荐 α：commit + push（让 ClawHub 用户也能跑）
- **test_full_workflow.py 扩充**：从 3 个集成测试扩展到 10 个测试场景（Part 2 真实样本默认跳过）
  - Part 0：Step 12 全链路集成（A/B/C）— 3 个测试
  - Part 1：7 个 mock 边界测试（content_hint 一致性 / 章节摘要边界 / state schema / 3 决策路径 / 链式摘要 / 失败回退 / Phase 2 强制）
  - Part 2：真实 docx 端到端测试（**默认跳过**，需设 `MBA_REAL_SAMPLES_DIR` 环境变量）
- **隐私保护**：开题报告含学生姓名/学号/研究方向，**严禁上传到 GitHub**。真实样本测试仅本地可选，详细使用见 `tests/REAL_SAMPLES_README.md`

总测试数 **102 个**（v2.0.0 72 + Step 12 集成 3 + 方案 A 7 = 102），默认全部通过 ✅。

## v1.7.3 新增

- **Orchestrator 自动推进**：`scripts/orchestrator.py` 决策引擎 + 审核 Loop 自动重审
- **Verification Loop 真实校验**：字体/字号/行距/三线表/加粗残留/参考文献分编 6 项 Word 格式检查
- **Guardrails 10项校验**：章节完整性/字数/引用/标题层级/正文加粗/三线表/表标题位置/合并残留/关键词
- **单元测试**：25 个测试覆盖全部脚本

## 版本说明

| 版本 | 说明 |
|------|------|
| v1.0_*_H_*.md | Hermes版本（深度逻辑链） |
| v1.0_*_O_*.md | OpenClaw版本（格式规范） |
| v2.0_审核*.md | 审核报告 |
| v3.0_整合版.docx | 整合版Word |
| v4.0_终稿.docx | 终稿Word |

## 写作规范

- **引用格式**：GB/T 7714 作者年制（作者, 年）
- **正文字数**：≥3.5万字
- **写作语法**：正文段落禁止 `**加粗**` 强调术语
- **中文字体**：宋体12磅，行距20磅
- **英文字体**：Times New Roman
- **标题字体**：黑体16磅/14磅/13磅

## 技术栈

- OpenClaw subagent (sessions_spawn)
- Hermes CLI (深度推理)
- academic-thesis-review-skill (学术深度评审)
- md2docx_strict.py (Word转换)

## 开源协议

MIT-0 - 免费使用、修改和分发，无需署名

## 作者

GitHub: [hehe973781230](https://github.com/hehe973781230)

---

*如果这个skill对你有帮助，请给个 ⭐*

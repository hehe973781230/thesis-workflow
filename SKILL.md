---
name: mba-thesis-workflow
version: 1.7.0
description: "多Agent协作完成MBA/学术论文写作的完整工作流，支持双版本起草、审核、整合、定稿。"
metadata:
  clawdbot:
    emoji: "📝"
    requires: {}
    os: ["linux", "darwin", "win32"]
---

# MBA/学术论文多Agent协作工作流

## ⚠️ 触发规则（必须遵守）


**当用户请求生成 Word 文档且满足以下任一条件时，必须调用本 skill 的 Word 输出流程，不得使用简单 md2docx 脚本：**

- 输入文件路径匹配：`论文*.md`、`*thesis*.md`、`*dissertation*.md`
- 上下文中存在「论文」「MBA」「答辩」「开题」等关键词
- 用户明确要求导出 `.docx` 格式且文件性质为学术论文

**禁止的行为：**
- ❌ 用简单 ~50行 Python 脚本直接 md→docx 转换论文文件
- ❌ 跳过 Review Agent 终审直接输出 Word
- ❌ 不检查格式规范（分页/三线表/标题层级/加粗过滤）就交付

**正确流程：** 写作语法预检 → Review Agent 终审 → 合规 md2docx 转换 → Word 输出

## 适用场景

- MBA毕业论文（战略管理/企业分析类）
- 学术研究报告（竞争战略/行业分析类）
- 需要多轮审核、多版本整合的正式长文

## 核心架构

```
用户（决策者）
    ↓
Phase 1  →  Orchestrator 出「确认清单」→ 用户逐项确认 ✅

Phase 2  →  H-generator（Hermes）起草版本H
           Executor subagent 起草版本O
    ↓  ⚠️ Phase 2.5 前不得跳过任何阶段
Phase 2.5→  用户确认章节内容 → 再送审 ✅
    ↓  ⚠️ 此阶段不得跳过
Phase 3  →  Reviewer 审核双版本 → 输出审核报告H + 审核报告O
    ↓  ⚠️ Phase 3.5 前不得跳过
Phase 3.5→  DeepReviewer 深度学术评审（P0/P1/P2分级）← ⚠️ 固定节点，Phase 3 完成即触发，不得跳过
    ↓  ⚠️ 此阶段不得跳过
Phase 4  →  Integrator 出整合方案 → Orchestrator 执行整合
    ↓  ⚠️ 此阶段不得跳过
Phase 5  →  Reviewer 终审
Phase 5.1 → [可选] HumanizerAgent 调用 humanize-chinese skill 去AI味 → 输出差异报告
Phase 5.2 → WordAgent 调用 md2docx_strict.py 生成Word文档
```

## Agent 设计原则（职责单一化）

**⚠️ 核心原则：每个 Agent 只做一件事，泛化风险最低。**

| 原则 | 说明 |
|------|------|
| 职责单一 | 每个 Agent 只有一个主责；多性质任务须拆分为多个 Agent |
| 退出条件明确 | 每个 Agent 有清晰的完成标准和终止条件 |
| 信息不跨 Agent 记忆 | Agent 间通过文件传递结果，不共享上下文 |
| 调度者不执行 | Orchestrator 专注调度，Word 输出等执行任务交给专职 Agent |

**Agent 分工（6类）：**

| Agent | 调用方式 | 主责 | 泛化风险 |
|-------|---------|------|---------|
| **Orchestrator** | 当前 session（主持） | 调度任务/推进流程/节点决策 | 🟢 低（纯调度） |
| **H-generator** | `exec hermes chat` | 版本H起草（深度逻辑链） | 🟢 低（单一任务） |
| **Executor** | `sessions_spawn` | 版本O起草 + 格式执行 | 🟢 低 |
| **Reviewer** | `sessions_spawn` | Phase 3/5 规则型快速审核 | 🟢 低 |
| **DeepReviewer** | `sessions_spawn` | Phase 3.5 学术深度评审 | 🟢 低 |
| **Integrator** | `sessions_spawn` | Phase 4 整合方案设计 | 🟢 低 |
| **WordAgent** | `exec python3` | md2docx_strict.py 执行 + 发送 | 🟢 低 |

**⚠️ 不允许的模式：**
- ❌ Orchestrator 自己做执行工作（调度+起草+整合+Word输出 全混在一起）
- ❌ Review Agent 承接 Phase 3/3.5/4/5 四种性质完全不同的任务
- ❌ 同一个 Agent 在不同 Phase 多次重建 prompt（应复用定义）

**泛化风险来源：** Agent 职责越多 → 注意力被稀释 → 各任务质量下降 → 需要更多审核轮次弥补 → 效率降低。遵循「职责单一」原则可有效控制。

## 关键实现说明

### 版本H的调用方式（H是关键区分）

**⚠️ 首先检测 Hermes 可用性：**

```bash
# 检测 Hermes 是否安装并可用
if hermes --version &>/dev/null 2>&1; then
  AGENT_TYPE="hermes"
  echo "Hermes 可用，使用版本H（Hermes CLI）执行"
else
  AGENT_TYPE="openclaw"
  echo "Hermes 不可用，回退到 OpenClaw 单版本执行"
fi
```

**版本H（Hermes可用时）** 通过 `exec hermes chat` 调用真实Hermes Agent：

**正确调用方式：**
```bash
exec hermes chat -q "<完整写作任务>" -Q --max-turns 30
```

**版本H（Hermes不可用时 → 回退到OpenClaw）** 通过 `sessions_spawn` 启动subagent执行，prompt中同样包含数据查询工具说明：

```bash
# Hermes 不可用时的等效执行
sessions_spawn(mode="run", runtime="subagent", 
  task="<写作任务，包含数据查询工具说明>", 
  taskName="xxx")
```

**写入文件的方式（重要）：**
在prompt里指定输出路径，让Agent直接写文件：
```bash
exec hermes chat -q "...
保存到文件：{{WORKSPACE_ROOT}}/论文_A公司_v1.0_H_chapter3_4.md
..." -Q --max-turns 30
# 或者 OpenClaw 回退时：
sessions_spawn(..., task="...保存到文件：{{WORKSPACE_ROOT}}/论文_A公司_v1.0_H_chapter3_4.md...", ...)
```

**⚠️ 必须在prompt中显式告知可调用的数据查询工具：**

```
【数据查询工具】（按需主动调用，不要只靠内部知识）
- multi-search-engine — 行业数据、企业信息、市场规模、新闻事件（无需API Key）
  调用方式：web_search 或直接描述搜索需求
- academic-research — 学术文献搜索、文献综述、引用分析（OpenAlex 2.5亿+论文）
  调用方式：python3 scripts/scholar-search.py search "关键词"
- arxiv-search-collector — 追踪最新学术论文（arXiv）
  调用方式：arxiv-search-collector skill

【调用原则】
- 起草阶段：优先用 multi-search-engine 查行业数据、市场规模、企业背景
- 理论框架/文献综述：优先用 academic-research 搜学术论文
- 前沿研究/最新进展：优先用 arxiv-search-collector 追踪arXiv论文
- 每个数据/引用都必须标注来源，说明用了哪个工具查询得到
```

**原因：** Hermes CLI直接输出文字，无法通过sessions机制传递结果给后续流程，所以必须让Agent自己把结果写入指定文件路径。Hermes不可用时，OpenClaw subagent执行相同逻辑，结果写入同一文件路径。

### 版本O的调用方式

**版本O（OpenClaw）** 通过 `sessions_spawn` 启动subagent执行：
```bash
sessions_spawn(mode="run", runtime="subagent", task="<写作任务>", ...)
```

### 数据查询工具（Phase 1-4 可按需调用）

| 工具 | 适用场景 | 调用方式 |
|------|---------|---------|
| `multi-search-engine` | 行业数据、企业信息、市场规模、新闻事件 | 直接调用，17个搜索引擎无需API Key |
| `academic-research` | 学术文献搜索、文献综述、引用分析（OpenAlex 2.5亿+论文） | `python3 scripts/scholar-search.py search "关键词"` |
| `arxiv-search-collector` | 追踪最新学术论文（arXiv） | 初始化后批量抓取，适合前沿主题 |

**嵌入节点建议：**
- **Phase 1**（确认清单出具前）→ 用 `academic-research` 搜理论框架、确认研究定位；用 `multi-search-engine` 查公司公开信息（年报/官网/行业报告）
- **Phase 2**（起草时）→ 用真实公司名查行业数据、市场规模、企业信息；数据填入论文时将公司名替换为代号（如A公司）
- **Phase 2.5/3**（用户确认/审核时）→ 用 `arxiv-search-collector` 补充文献引用
- **Phase 4**（整合时）→ 填补数据空白或更新过时数据

**⚠️ 公司信息处理原则：**
- 用真实公司名搜索可验证的公开数据（年报、财报、行业报告、新闻）
- 填入论文正文时，将真实公司名替换为代号（A公司/B公司等），映射关系不进入最终文档
- 搜索 prompt 中使用真实公司名，输出 prompt 中使用代号

---

## Phase 详解

### Phase 1：规划与定稿（Q&A确认）

**目标：** 通过问答将所有维度明确清楚，用户确认后再动笔。

**执行步骤：**

1. **接收输入**：开题报告 / 论文要求文档 / 大纲
2. **输出确认清单**（包含以下维度）：

| 维度 | 内容 | 备注 |
|------|------|------|
| 论文基本信息 | 题目/作者/学号/专业/学位类型/答辩年份 | 红色星标项 |

| **公司信息映射表** | ⭐ **实际公司名称（必填，用于数据检索；论文正文中使用代号A公司/B公司）** | 用代号代替，如：A公司=真实公司名 |
| 大纲结构 | 7章大纲逐章确认保留/修改/增删 | 红色星标项 |
| 写作标准 | 字数(≥3.5万)/引用格式(GB\/T7714作者年制)/语言风格 | — |
| 审核维度 | 格式/大纲/内容准确性/查重风险/学术规范/完整性 | — |
| 参考资料 | 开题报告/文献/行业数据/公司背景资料 | — |
| 特殊要求 | 导师偏好/行业敏感点/竞品回避要求 | — |

3. **用户逐项确认**（红色星标项必填）

   - ⭐ **实际公司名称未填写时，必须提醒用户提供**，公司名称仅用于数据检索，正文以代号（A公司/B公司）呈现，不进入公开文档；未提供则无法进入 Phase 2 数据搜集阶段
4. **生成「写作任务书」** → 用户签收 → 进入 Phase 2

**⚠️ 硬规则：不确认不动笔。Phase 1 是守门人。**

---

### Phase 2：分工起草与合并

**目标：** 完成全章节初稿，核心章节双版本对比。

---

## ⚠️ Phase 2 执行前检查（强制，逐项确认后方可启动）

> 每次启动 Phase 2 前，Orchestrator 必须逐项确认，不得跳过。

- [ ] 确认已完成 Phase 1 必填确认清单（公司映射✅ / 大纲✅）
- [ ] 确认 Hermes 可用（`hermes --version`）
- [ ] 确认 Executor 可用（`sessions_spawn` 测试）

### 章节×版本对照表（必须全部 spawn，不得遗漏）

| 章节 | Executor（版本O） | Hermes（版本H） | 说明 |
|------|-----------------|----------------|------|
| 第1、2、7章 | ✅ 必须起草 | ❌ 不需要 | 基础章节，单版本即可 |
| 第3章 | ✅ 必须起草 | ✅ 必须起草 | **核心章节**，双版本对比 |
| 第4章 | ✅ 必须起草 | ✅ 必须起草 | **核心章节**，双版本对比 |
| 第5章 | ✅ 必须起草 | ✅ 必须起草 | **核心章节**，双版本对比 |
| 第6章 | ✅ 必须起草 | ✅ 必须起草 | **核心章节**，双版本对比 |

> ⚠️ **每个「✅ 必须起草」都是一个独立的 `sessions_spawn` / `hermes chat` 调用，不得合并。**
> 若只完成其中一个，视为 Phase 2 未完成，禁止进入 Phase 2.5。

**Phase 2 完成判定标准（全部满足方可进入 Phase 2.5）：**
- 版本O文件存在：第1-7章全部（ls 验证）
- 版本H文件存在：第3-6章全部（ls 验证）
- 任意一个文件缺失 → Phase 2 判定为**未完成**，禁止送审

---

**分工原则：**
- **所有章节** → 各出一份单版初稿
- **核心章节（通常第3-5章，战略分析类）** → 额外双版本：
  - **版本H**：通过 `exec hermes chat` 调用真实Hermes Agent（深度逻辑链优先）
  - **版本O**：通过 `sessions_spawn` 启动OpenClaw subagent（格式规范优先）

**执行方式：**
```bash
# 首先检测 Hermes 可用性
if hermes --version &>/dev/null 2>&1; then
  AGENT_TYPE="hermes"
  echo "Hermes 可用，使用版本H（Hermes CLI）执行"
else
  AGENT_TYPE="openclaw"
  echo "Hermes 不可用，回退到 OpenClaw 单版本执行"
fi

# 版本H：Hermes可用时使用Hermes CLI，不可用时回退到OpenClaw subagent
if [ "$AGENT_TYPE" = "hermes" ]; then
  # Hermes CLI（prompt中必须包含数据查询工具说明，见上文）
  exec hermes chat -q "<任务，包含数据查询工具说明>" -Q --max-turns 30
else
  # OpenClaw subagent（Hermes不可用时的回退路径）
  sessions_spawn(mode="run", runtime="subagent", task="<任务，包含数据查询工具说明>", taskName="xxx")
fi

# 版本O：OpenClaw subagent（始终使用）
sessions_spawn(mode="run", runtime="subagent", task="<任务>", taskName="xxx")
```

**⚠️ 版本H的prompt模板（可直接套用）：**
```
请为论文《{题目}》撰写第{章号}章内容。

【写作任务】
{具体写作要求}

【数据查询工具】（按需主动调用）
- multi-search-engine — 行业数据、企业信息、市场规模、新闻事件
  调用方式：描述搜索需求，让系统执行搜索
- academic-research — 学术文献搜索（OpenAlex 2.5亿+论文）
  调用方式：python3 ~/.openclaw/workspace/skills/academic-research/scripts/scholar-search.py search "关键词"
- arxiv-search-collector — 追踪最新学术论文
  调用方式：使用arxiv-search-collector skill

【写作要求】
- 每个数据/引用必须标注来源，说明用了哪个工具查询得到
- 引用他人观点时必须paraphrase，禁止直接复制原文
- **格式规范（必须严格遵守，否则Word转换会出错）：**
  - 章节标题：`# 第X章` / `## X.X` / `### X.X.X`，**禁止用 `## 第X章`/`### 第X.X` 混合格式**
  - **参考文献：必须用 `## 参考文献`，不得用 `### 参考文献` 或 `# 参考文献`**
  - 正文段落不得用 `**加粗**` 强调术语
  - 表格标题放在表格上方，不加粗
- 写完后保存到：{文件路径}
```

**输出物（Phase 2完成后应存在）：**
```
论文_A公司_v1.0_H_chapter3_4.md      （Hermes CLI写出）
论文_A公司_v1.0_H_chapter5_6.md      （Hermes CLI写出）
论文_A公司_v1.0_O_chapter3_4.md      （OpenClaw subagent写出）
论文_A公司_v1.0_O_chapter5_6.md      （OpenClaw subagent写出）
论文_A公司_v1.0_chapter1_2_7.md      （OpenClaw subagent写出，单版本）
```

**⚠️ 状态文件机制（防中断）**：
每次 Phase 2 启动时，在 `~/.openclaw/workspace/` 目录下创建/更新任务状态文件 `论文_{题目}_任务状态.json`：
```json
{
  "paper": "{论文标题}",
  "version": "v1.0",
  "phase": "Phase 2",
  "started_at": "YYYY-MM-DD HH:MM",
  "last_updated": "YYYY-MM-DD HH:MM",
  "chapters": {
    "chapter1_2_7": {"status": "completed", "file": "...", "lines": 0},
    "chapter3_4": {"status": "completed", "file": "...", "lines": 0},
    "chapter5_6": {"status": "pending", "file": null, "lines": 0}
  },
  "planned_chapters": ["chapter1_2_7", "chapter3_4", "chapter5_6"],
  "next_action": "补写 chapter5_6"
}
```
- **创建时机**：Phase 2 第一个 subagent 启动时
- **更新时机**：每个章节文件写入完成后立即更新 `status="completed"` 和 `file`/`lines`
- **读取时机**：每次 session 开始时（见 AGENTS.md "每次 Session 开始时"步骤），优先检查同目录是否存在 `*_任务状态.json`，若有则加载并告知用户未完成任务
- **删除时机**：Phase 2 全部章节完成后（验证通过），删除状态文件或标记 `phase": "Phase 2 完成"


**章节完整性自动校验（强制步骤）**：
Phase 2 最后一个 subagent 完成后，立即执行以下校验，**全部通过方可进入 Phase 3**：
```bash
# 伪代码
for ch in planned_chapters:
    if not os.path.exists(f"{paper_prefix}_{ch}.md"):
        abort("❌ 缺失章节: {ch}，无法进入 Phase 3")

# 字数门槛校验
for ch_file in chapter_files:
    lines = count_lines(ch_file)
    if lines < 100:  # 低于此行数认为内容不足
        abort("❌ {ch_file} 内容不足（{lines}行），请补充")


print("✅ 章节完整性校验通过：N/N 章存在，内容充足")
```

**起草约束（前置查重）：**
- 引用他人观点时必须 paraphrase，禁止直接复制原文
- 每引用一个理论/数据必须标注来源
- 连续≥30字与参考文献重合的内容需特殊标记

### 写作语法规范（必读）

撰写初稿时必须严格遵守以下语法规范，避免 Word 转换后出现视觉噪音：

| 语法元素 | 正确用法 | 错误用法（会导致排版问题） |
|---------|---------|--------------------------|
| 章节标题 | 使用 `# 第X章` / `## X.X` / `### X.X.X` 层级，**禁止使用 `## 第X章`/`### 第X.X` 等混合格式** | 不要用 `**` 包裹标题文字 |
| **参考文献** | **必须使用 `## 参考文献`（二级节标题）**，不得使用 `### 参考文献` 或 `# 参考文献` | 参考文献是正文后的独立部分，不是章也不是普通节，与一级节同级 |
| 列表项小标题 | 使用 `### 1.2.1 标题文字` 格式 | 不要写成 `**（1）标题**` 或 `**小节要点**` |
| **正文目录章节** | **严禁在正文内生成「目录」章节**（如 `## 目录` / `### 目录`），正文内容应直接按层级展开，不需要在章节内部再写目录 | 目录是论文整体结构页，由md2docx在摘要后自动生成，不得在正文章节内自建目录 |
| 正文段落 | 普通文字，首行缩进2字符 | 绝对不要在正文中使用 `**加粗**` 来强调术语 |
| 表格标题行 | 放在表格上方，另起段落 | 表格标题不要用 `**加粗**` |
| 图表编号说明 | 段落形式："图1.1展示了..." | 不要用 `**图1.1**` 加粗形式 |
| 矩阵/得分说明 | 段落形式："评分说明：..." | 不要写成 `**评分说明：**` 加粗 |

**核心原则：**
- `**文字**` 在 Word 中会变成「加粗」，只应用于**真正的标题层级**，不能用来强调正文中的术语或概念
- 正文段落中需要提及某个术语时，直接写普通文字，不加粗
- 每个 `**` 的使用都应有对应的 Word 样式（标题/加粗正文），而非语义标记

---

### Phase 2.5：用户确认节点（人工门槛）

**⚠️ 此节点不可跳过。**

将 Phase 2 输出的章节内容整理给用户，用户确认：
- 各章节核心观点是否符合预期
- 大方向无误后再送审

**Phase 2.5 核心章节完整性自动检查（强制步骤）**：
在展示章节内容给用户确认前，先执行自动检查，发现问题则弹窗提示，不展示确认按钮：
```bash
# 伪代码
# 第5章必须包含战略选择相关关键词
strategy_kw = ['战略选择', '竞争战略', '差异化', '集中化', '成本领先', 'QSPM']
if not any(kw in chapter5_content for kw in strategy_kw):
    abort("❌ 第5章未包含战略选择相关内容，请补充后再确认")

# 第6章必须包含实施保障相关关键词
protect_kw = ['实施', '保障', '组织', '人才', '财务', 'KPI', '考核']
if not any(kw in chapter6_content for kw in protect_kw):
    abort("❌ 第6章未包含实施保障相关内容，请补充后再确认")

# 字数门槛
if len(chapter5_content) < 2000:
    abort(f"⚠️ 第5章字数过少（{len(chapter5_content)}字），内容可能不足")
if len(chapter6_content) < 2000:
    abort(f"⚠️ 第6章字数过少（{len(chapter6_content)}字），内容可能不足")

print("✅ 核心章节完整性检查通过")
```

**如需大改，返回 Phase 2 对应章节重写。**

---

### Phase 3：双版本审核

**目标：** Review Agent 分别对版本H 和 版本O 输出独立审核报告。

**审核维度（逐项打分 + 修改建议）：**

#### 一、格式维度（详细标准）

| 检查项 | 具体标准 |
|--------|---------|
| **封面** | ✅ 包含：学校代码/分类号/密级/UDC/论文题目/作者/专业/方向/导师/答辩日期 |
| **原创性声明** | ✅ 含声明正文+签名栏+日期，位于封面之后、摘要之前 |
| **中文摘要** | 标题"摘要"两字间空两格，黑体16磅加粗居中，单倍行距，段前24磅，段后18磅；内容不少于800字，宋体12磅（小四），行距20磅，段前段后0磅；关键词3-5个，格式同正文，"关键词"三字加粗，分号分隔 |
| **英文摘要** | 标题"Abstract"，Arial 16磅加粗居中，单倍行距，段前24磅，段后18磅；内容Times New Roman 12磅，行距20磅；关键词3-5个，"Key Words"加粗，分号分隔，与中文关键词一一对应 |
| **目录** | 标题"目录"两字间空两格，黑体16磅加粗居中，单倍行距，段前24磅，段后18磅；从绪论开始列出章节名称与页码；各章目录：宋体12磅加粗，单倍行距，段前6磅，段后6磅，两端对齐，页码右对齐；一级节：宋体12磅，左缩进1汉字；二级节：仿宋10.5磅，左缩进2汉字；自动生成，纳入1-3级标题 |
| **正文各章标题** | "第X章 ×××"，黑体16磅加粗居中，单倍行距，段前24磅，段后18磅，章序号与章名称之间空两格，**每章另起一页** |
| **一级节标题** | "1.2 ×××"，黑体14磅顶左，单倍行距，段前24磅，段后6磅，序号与题名之间空两格 |
| **二级节标题** | "1.2.1 ×××"，黑体13磅，左缩进两字，单倍行距，段前12磅，段后6磅，序号与题名之间空两格 |
| **三级节标题** | "（1）×××"，宋体12磅，左缩进两字，单倍行距，与正文同段 |
| **正文** | 宋体12磅（英文Times New Roman 12磅），两端对齐，首行左缩进2个汉字符，段前段后0磅，**行距20磅** |
| **图号图题** | 图号+图题置于图下方，宋体10.5磅加粗居中，单倍行距，段前6磅，段后12磅；图注左缩进两字；图中文字宋体10.5磅（英文Times New Roman 10.5磅） |
| **表号表题** | 表号+表题置于表上方，宋体10.5磅加粗居中，单倍行距，段前6磅，段后6磅；表注左缩进两字；表中文字宋体10.5磅（英文Times New Roman 10.5磅） |
| **表格** | 三线表（顶线、表头底线、底线），无竖线 |
| **图表编号** | 阿拉伯数字分章依序连续编码，如"图1.1"、"表3.2" |
| **注释** | **页下注**，以①②③……连续编号（不得使用上标形式的脚注） |
| **参考文献** | 正文引用用作者年制（不得使用上标加序号形式）；文后"参考文献"标题左对齐；中文在前英文在后分别排序；中文用宋体小四号全角标点；英文用Times New Roman小四号，作者姓前名后缩写，杂志名书名斜体 |
| **页码** | 前置部分（封面/声明/摘要/目录）用罗马数字；正文部分（从绪论起）用阿拉伯数字 |
| **附录** | 标题格式同章标题；内容格式同正文；用大写字母A/B/C编序号（如附录A）；只有一个附录名为"附录"不编号；图表编号与正文分开如"图A.1" |
| **致谢** | 标题"致谢"两字间空两格，格式同章标题；内容格式同正文 |

#### 二、大纲维度

| 检查项 | 具体标准 |
|--------|---------|
| 大纲合规 | 每章内容不得超出原定大纲范围，超出章节标★ |
| 每章结构 | 每章≥2节，每节≥2点，每点≥5行 |

#### 三、内容准确性维度

| 检查项 | 具体标准 |
|--------|---------|
| 来源标注 | 每引用一个理论/数据必须标注来源，无来源结论标⚠️ |
| 数据一致 | 正文数据前后矛盾处标⚠️ |

#### 四、查重风险维度

| 检查项 | 具体标准 |
|--------|---------|
| 连续重合 | 连续≥30字与参考文献重合标🔴，需paraphrase |

#### 五、学术规范维度

| 检查项 | 具体标准 |
|--------|---------|
| 引用完整率 | 引用标注完整率必须达到100% |
| 术语规范 | 术语首次出现须全称+后续简称 |
| 正文中文格式 | 一个人：作者姓名（2018）；两个人：作者1和作者2（2018）；三个及以上：第一作者等（2018） |
| 正文英文格式 | 一个人：Betts（2018）；两个人：Betts和Taylor（2018）；三个及以上：Betts等（2018） |
| 文后中文格式 | 期刊：作者：《题名》，《刊名》，年份期次；专著：作者：《书名》，出版社年份；论文集：作者：《题名》，主编，《论文集名》，出版社年份 |
| 文后英文格式 | 作者姓写在前名缩写在后，杂志名书名斜体；同一作者同年多篇加a/b/c区分 |

#### 六、写作语法维度（新增）

| 检查项 | 具体标准 |
|--------|---------|
| 正文加粗 | 正文段落中出现 `**xxx**` 标🔴，应改为普通文字；标题级加粗（`## 标题`中的加粗）除外 |
| 列表项格式 | 小节内的要点不应以 `**（1）xxx**` 加粗形式呈现，应用 `###` 升为正式节标题或改为普通正文 |
| 表格标题行 | 表格标题行应是普通段落文字（如"表3-1 外部因素评价矩阵"），不应加粗或居中加粗 |
| 图表编号格式 | 引用图表时使用自然句式"如图1.1所示"，不应 `**图1.1**` 加粗形式 |
| 过渡句式 | 章节过渡段落应使用自然叙述，不应大量使用 `**xxx领域**` 加粗术语作为领起 |

**输出物：**
```
审核报告H（H版本的优劣势 + 问题清单 + 每条修改指令）
审核报告O（O版本的优劣势 + 问题清单 + 每条修改指令）
```

**⚠️ 整合指令模板：** 每条问题后面必须附带具体的整合指令，格式：
```
问题：{描述}
→ 整合指令：{采用哪个版本的什么部分，如何合并}
```

---

### Phase 3.5 深度学术评审（固定节点）

**⚠️ 强制执行，不得跳过。**

**目标：** 使用严格学术标准对 Phase 3 审核报告进行二次审查，补充格式审核之外的学术规范性检查（逻辑链、引用规范性、数据可信度、学术创新性）。

**前提：** Phase 3 审核报告已完成（审核报告H.md + 审核报告O.md）

**执行方式：**
```bash
# Phase 3：Reviewer 审核（规则型快速审核）
sessions_spawn(mode="run", runtime="subagent",
  task="执行 MBA 论文 Phase 3 双版本审核，输出审核报告H 和 审核报告O。",
  taskName="phase3_reviewer")

# Phase 3.5：DeepReviewer 深度学术评审（独立执行）
sessions_spawn(mode="run", runtime="subagent",
  task="执行 MBA 论文 Phase 3.5 深度学术评审，输出评审报告。",
  taskName="phase3_5_deep_reviewer")

```

**输出物：**
```
审核报告_Phase3.5_深度学术评审_v1.0.md
```

**Phase 3 vs Phase 3.5 区别：**
- Phase 3：格式+大纲+内容准确性审核（快速结构化Review Agent）
- Phase 3.5：学术深度评审（论证逻辑、引用规范性、数据可信度、学术写作规范）

**两者互补，不替代。Phase 3.5 是固定节点，Phase 3 完成即触发。**

**⚠️ 执行要点：**
- Phase 3.5 紧接在 Phase 3 三个子审核任务完成后立即执行，不等待用户指令
- Phase 3.5 完成后的 P0 问题清单是 Phase 4 整合修复的直接输入
- Phase 3.5 评审报告中的「修改优先级」直接指导 Phase 4 的修复顺序

---

### Phase 4：整合与升华

**目标：** Integrator 汇总 Phase 3 + Phase 3.5 的全部评审结果，制定整合方案，Orchestrator 执行整合。

**⚠️ 前提输入（两份报告必须齐全）：**
- Reviewer（Phase 3）输出：审核报告H + 审核报告O（格式/大纲/内容结构化问题清单）
- DeepReviewer（Phase 3.5）输出：深度学术评审报告（P0/P1/P2分级，逻辑链/引用/数据可信度问题）

**执行逻辑：**
1. Integrator 读取 Phase 3 两份审核报告 + Phase 3.5 评审报告
2. **合并去重问题清单**：同一问题被两方提及的，合并为一条，保留最高优先级
3. 按优先级排序（P0→P1→P2）
4. 对每个问题判断出在哪个版本，给出整合指令
5. 优先保留逻辑链完整、论证深入的版本
6. 对格式规范性问题参考版本O的处理方式
7. **不强行整合**——冲突时保留质量更高的版本
8. 确保全文语言风格、术语体系统一

**⚠️ 核心原则：取长补短，但不为统一而破坏内容质量。**

**Phase 4 整合后自动验证报告（强制步骤）**：
整合脚本执行完毕后、进入 Word 输出前，自动输出结构化验证报告，未全部通过则中止 Word 输出：
```bash
# 伪代码
chapters = re.findall(r'^# 第[1-7]章', content, re.MULTILINE)
end_markers = re.findall(r'===END===', content)
ref_pos = content.find('## 参考文献')
ch7_pos = content.find('# 第7章 结论')

report = f"""
=== 整合版验证报告 ===
✅ 章节数：{len(chapters)}/7
{'✅' if not end_markers else '❌'} 合并残留：{len(end_markers)} 处
{'✅' if ref_pos > 0 else '❌'} 参考文献：{'存在' if ref_pos > 0 else '缺失'}
字 数：{len(content)} 字
---
状态：{'✅ 可进入 Word 输出' if not end_markers and len(chapters)==7 else '❌ 需修复'}
"""
print(report)
if end_markers or len(chapters) != 7:
    abort("❌ 整合版存在致命问题，停止 Word 输出")
```

### Word 输出质量保障（新增）

md2docx 转换脚本需满足以下要求，否则会在 Word 中产生视觉噪音：

#### 1. 正文加粗过滤
- 脚本在转换时应识别：出现在正文段落（非标题级）内的 `**text**`，应**去掉 `**` 转为普通文字**，而非保留粗体
- 识别方法：行不以 `#` / `## ` / `### ` 开头，且不以 `**xxx**` 整段加粗（整段加粗的标题除外）
- **表格单元格内的 `**` 也须同步清除**，避免三线表表头出现裸星号
- **脚本实现要点**：`add_table()` 函数中，每个单元格写入前需执行 `re.sub(r'\*\*([^*]+)\*\*', r'\1', cell_text)`

#### 2. 表格标题行处理
- 表格上方通常应有图注/表注段落（如"表3-1 外部因素评价矩阵"），该段落应加粗居中
- 表格本身不使用竖线以外的多余边框线，输出为三线表样式

#### 3. 标题层级确认
- 每章标题（`# 第X章`）后应自动插入分页符（**标题后分页**，避免第一页空白）

---

### 规则型 vs 审核型分工原则（重要）

**核心原则：脚本管得了的，Agent 不重复检查；脚本管不了的，Agent 才来管。**

#### 规则型（脚本固定生成，Agent 跳过）

| 规范项 | 处理方式 |
|--------|---------|
| 摘要标题"摘要" | 黑体16磅加粗居中，单倍行距，段前24磅段后18磅 |
| 摘要内容 | 宋体12磅，行距20磅，段前段后0磅 |
| Abstract标题 | Arial 16磅加粗居中，单倍行距，段前24磅段后18磅 |
| 关键词/Key Words | 3-5个，对应关键词加粗 |
| 各章标题"第X章" | 黑体16磅加粗居中，段前24磅段后18磅，章后分页 |
| 一级节标题"1.2" | 黑体14磅，段前24磅段后6磅 |
| 二级节标题"1.2.1" | 黑体13磅，段前12磅段后6磅 |
| 三级节标题"（1）" | 宋体12磅，左缩进2字，与正文同段 |
| 正文段落 | 宋体12磅，首行缩进2汉字，行距20磅 |
| 图号/图题 | 图下方，宋体10.5磅加粗居中 |
| 表号/表题 | 表上方，宋体10.5磅加粗居中 |
| 三线表 | 顶线1.5磅/表头底线0.75磅/底线0.5磅，无竖线 |
| 注释 | 页下注，①、②、③连续编号 |
| 正文引用格式 | 作者年制（作者，2020），不得上标编号 |
| 参考文献中英文分编+字母排序 | `_flush_refs()` 分两块写 |
| 附录/致谢标题 | 格式同章标题 |
| 表格标题在表格上方 | 脚本校验告警 |
| `## 第X章` 等混合格式 | 脚本告警 |
| `**加粗**` 正文残留 | `strip_bold()` 清除 |

⚠️ **脚本已覆盖的规范，Agent 只校验输出结果是否符合预期，不重复检查。**

#### 审核型（Agent 判断，脚本无法处理）

| 审核项 | 判断说明 |
|--------|---------|
| 摘要内容字数≥800字 | 需全文字数统计 |
| 关键词数量3-5个 | 数量检查 |
| 正文字数≥3.5万字 | 需全文字数统计 |
| 正文结构（≥3章/章≥2节/节≥2点/点≥5行） | 结构化扫描+语义判断 |
| 参考文献在正文中有对应引用 | 全文交叉验证 |
| 引用格式细节（期刊名斜体、年份位置、作者顺序） | 对照规范5.2逐条核对 |
| 逻辑链完整性 | 需全文语义理解 |
| 学术创新性 | 需领域知识 |
| 数据可信度 | 需外部核实 |
| 论证深度 | 需语义理解 |
| 查重风险（连续≥30字重合） | 全文扫描 |

⚠️ **脚本处理过的格式输出结果，Agent 只抽查是否按预期工作，不做全面复检。**

**如需大改：**
- 细节问题 → 打回 Phase 4 局部修改
- 框架/逻辑问题 → 打回 Phase 2 重写对应章节

**输出物：**
```
论文_{题目}_v4.0_终稿.docx
```

---

### Phase 5.1：去AI味（可选）

**前置检测：** 判断 humanize-chinese skill 是否已安装。
```bash
HUMANIZE_DIR="~/.openclaw/workspace/skills/humanize-chinese"
if [ -d "$HUMANIZE_DIR/scripts" ]; then
    echo "SKILL_INSTALLED"
else
    echo "SKILL_NOT_INSTALLED"
fi
```
**分支逻辑：**
| 状态 | 行为 |
|------|------|
| skill已安装 | 直接展示「去AI味」选项 |
| skill未安装 | 展示选项但提示「需先安装」，用户确认后自动安装到 `~/.openclaw/workspace/skills/` |

**自动安装命令：**
```bash
git clone https://github.com/example/humanize-chinese.git ~/.openclaw/workspace/skills/humanize-chinese
```
> ⚠️ 安全检查：安装前需确认来源可信，参考 AGENTS.md skill安装安全规则。

**触发条件：** 用户勾选「去除AI味」选项时执行。

**执行方式：** HumanizerAgent 调用 humanize-chinese skill 的 CLI 脚本。

**执行流程：**

| 步骤 | 操作 | 工具 |
|------|------|------|
| 1 | 检测AI痕迹评分（原文） | `detect_cn.py {源文件} -s` |
| 2 | 学术风格降重 | `academic_cn.py {源文件} -o {润色后文件} -a --compare` |
| 3 | 验证降重效果 | `detect_cn.py {润色后文件} -s` 确认分数下降 |
| 4 | 生成差异报告 | `compare_cn.py {源文件}` 对比 |
| 5 | 输出两份md文件 | 写文件 |

**输出物：**
```
{论文名}_整合版.md                    （原文，不改动）
{论文名}_整合版_润色后.md             （去AI味后）
润色差异报告.md                       （差异对照）
```

**脚本路径：**
```bash
SKILL_DIR="~/.openclaw/workspace/skills/humanize-chinese"
python3 $SKILL_DIR/scripts/detect_cn.py "$src" -s
python3 $SKILL_DIR/scripts/academic_cn.py "$src" -o "$dst" -a --compare
python3 $SKILL_DIR/scripts/detect_cn.py "$dst" -s
```

**⚠️ 数据完整性保障：**
- EFE/IFE/QSPM矩阵数字**不得修改**
- 所有事实、数据、案例**保持原样**
- 仅改表达方式，不改内容实质

---

### Phase 5.2：Word文档生成

**目标：** 生成Word文档并告知存储位置

**执行步骤：**

1. **判断去AI味选项：**
   - 用户勾选 → 生成两份Word（Original + Polished）
   - 用户未勾选 → 仅生成一份Word（Original）

2. **生成Word：**
   ```bash
   MD2DOCX="~/.openclaw/skills/mba-thesis-workflow/scripts/md2docx_strict.py"
   python3 $MD2DOCX "{整合版.md}" "{论文名}_Original.docx"
   python3 $MD2DOCX "{整合版_润色后.md}" "{论文名}_Polished.docx"
   ```

3. **告知存储位置：**
   Word文档保存到 `~/.openclaw/workspace/` 目录，完成后告知用户具体文件路径。

---

## ⚠️ Loop 设计原则（v1.7 引入）

**本节为 v1.7 新增的架构层增强。** MBA 论文写作是一个**多阶段、有审核、有反馈、需要持续推进直到交付**的复杂任务，这正是 AI Agent Loop（ReAct / OpenAI Agents SDK "Agent loop" 模式）的最佳应用场景之一。本 skill 借鉴 Loop Agent 的"感知 → 思考 → 行动 → 观察"四步循环思想，在保持 7 阶段状态机主流程不变的前提下，**在架构层引入 5 个 Loop 元素**。

### 5 个 Loop 元素

| Loop 元素 | 作用 | 对应 Loop Agent 概念 |
|----------|------|---------------------|
| **① Orchestrator Loop** | 每 Phase 完成后自动判断下一步：通过 → 下一 Phase；缺条件 → 提示用户；出错 → 自动打回 | Agent loop（OpenAI Agents SDK 内置运行时） |
| **② Phase 内部自检 Loop** | 每个 Phase 内部 Observe → Think → Act → Verify 四步循环 | ReAct（Reasoning + Acting） |
| **③ 审核 Loop** | Phase 3 + 3.5 + 修订形成闭环：审→改→重审→...→连续2轮无新P0→通过 | Multi-turn Self-Correction |
| **④ Guardrails 校验** | 每 Phase 退出前必须通过规则脚本校验（章节完整性/引用/三线表/加粗/标题） | Guardrails（输入输出校验） |
| **⑤ Verification Loop** | Word 输出后自动校验格式，失败则提示并打回 Phase 4 修复 | Verification（输出验证） |

### Loop 终止条件（明确化）

每个 Loop 必须有**清晰的退出条件**，避免"无限循环"：

| Loop 类型 | 退出条件 |
|----------|---------|
| Orchestrator Loop | 全部 7 个 Phase 全部 `status="completed"` |
| Phase 内部自检 Loop | Guardrails 脚本 100% 通过 |
| 审核 Loop | 连续 2 轮无新 P0/P1 问题 |
| Verification Loop | Word 格式校验 100% 通过 |

**最大重试次数**：3 次（防止死循环）；超过则**强制触发 Human-in-the-loop** 让用户决策。

### Human-in-the-loop 检查点（关键决策）

以下节点**必须**用户确认才能推进，不能由 Loop 自动跳：

| 检查点 | 确认内容 | 不确认的后果 |
|-------|---------|------------|
| Phase 1 末尾 | 写作任务书（题目/公司映射/大纲） | 方向错了全白做 |
| Phase 2.5 末尾 | 章节内容是否符合预期 | 跑偏了审完也白审 |
| Phase 4 末尾 | 整合方案是否接受 | 整合错了质量更差 |
| Phase 5.2 末尾 | Word 文档是否符合预期 | 错版交付给导师 |

---

## Orchestrator Loop 自动化（v1.7 新增）

**目标**：取代"每步手动 trigger"模式，**让 Orchestrator 自动判断下一步动作**。

**实现方式**：每 Phase 完成后，Orchestrator 读取 `*_任务状态.json` 并执行以下决策：

```python
# 伪代码（Orchestrator 决策逻辑）
def decide_next_action(state):
    current_phase = state["phase"]
    if current_phase == "Phase 1 完成":
        if state.get("company_mapping") and state.get("outline_confirmed"):
            return "进入 Phase 2"
        else:
            return "提示用户补全公司映射表或大纲"
    
    elif current_phase == "Phase 2 完成":
        if all_chapters_exist(state) and word_count_check(state):
            return "进入 Phase 2.5（用户确认）"
        else:
            return "打回 Phase 2 补写缺失章节"
    
    elif current_phase == "Phase 3 完成":
        return "进入 Phase 3.5（自动触发，不得跳过）"
    
    elif current_phase == "Phase 3.5 完成":
        if has_p0_issues(state):
            return "进入 Phase 4 修订（修订后自动重审，最多 3 轮）"
        else:
            return "进入 Phase 4 整合"
    
    elif current_phase == "Phase 4 完成":
        if integration_validation_passed(state):
            return "进入 Phase 5 终审（用户确认是否继续）"
        else:
            return "打回 Phase 4 修复"
    
    elif current_phase == "Phase 5 完成":
        return "进入 Phase 5.1 [可选] / Phase 5.2 Word 输出"
```

**关键不变量**：
- ❌ 不允许 Phase 3.5 → Phase 4 的跳跃（必须等 Phase 3.5 完成）
- ❌ 不允许 Phase 2 → Phase 3 的跳跃（必须等 Phase 2.5 用户确认）
- ❌ 不允许跳过任何 Phase（即使 Guardrails 通过）

---

## Phase 内部自检 Loop（v1.7 新增）

**目标**：每个 Phase 内部遵循 Observe → Think → Act → Verify 四步循环，确保输出符合规范。

**通用模板**（所有 Phase 适用）：

```
1. Observe  ——  读取上一阶段产出 + 状态文件
                ↓
2. Think    ——  判断本 Phase 任务清单（必须完成什么）
                ↓
3. Act      ——  执行 spawn / exec / 文件写入
                ↓
4. Verify   ——  运行 Guardrails 脚本校验
                ↓
              通过？→ 退出 Phase，更新状态
              不通过？→ 回到 Step 2 修订（最多 3 次）
```

**Phase 2 内部自检示例**：

```
Observe：读取 Phase 1 任务书（题目/公司映射/大纲）
Think：判断需要起草的章节（1/2/7 单版本，3-6 双版本）
Act：spawn 6 个 subagent（H 3个 + O 6个）
Verify：运行 loop_self_check.py
  - 检查 7 个文件存在
  - 检查每章 ≥ 100 行
  - 检查无 **正文加粗**
  - 检查无 ## 第X章 混合格式
通过？→ 退出 Phase 2，进入 Phase 2.5
不通过？→ 打回补写，最多 3 次后强制用户决策
```

---

## 审核 Loop 强化（v1.7 新增）

**目标**：把 Phase 3 + Phase 3.5 + Phase 4 修订 + Phase 5 终审**串成闭环**，自动重审直到质量达标。

**审核 Loop 状态机**：

```
[Phase 3 快速审核] ─→ 输出审核报告H + 审核报告O
        ↓
[Phase 3.5 深度评审] ─→ 输出 P0/P1/P2 分级问题
        ↓
   ┌─ 有 P0 问题？──── 是 ─→ [Phase 4 修订] ─→ 自动回到 Phase 3.5 重审 ─┐
   │                                          ↑                         │
   │  否（仅 P1/P2）──→ [Phase 4 整合] ─→ [Phase 5 终审] ─→ 通过 → 退出│
   │                                          ↑                         │
   │                                          └────── 连续 2 轮无新 P0 ─┘
   │                                                                    │
   └──────────────────── 超过 3 轮仍有 P0 ──→ 强制 Human-in-the-loop ───┘
```

**自动重审触发条件**：
- Phase 3.5 输出有 P0 问题 → Phase 4 修订 → 自动重审
- 连续 2 轮 Phase 3.5 无新 P0 → 视为通过，进入 Phase 4 整合
- 累计修订超过 3 轮 → 强制触发用户决策

**重审范围**：
- 仅重审 P0 问题是否修复
- 不重复扫描全文（避免 LLM 上下文爆炸）
- 重审报告单独归档，命名 `审核报告_Phase3.5_v{轮次}.md`

---

## Guardrails 校验（v1.7 新增）

**目标**：把所有"应该遵守的规范"做成自动化校验脚本，**Agent 不再靠自觉**。

**Guardrails 校验脚本**：`scripts/loop_self_check.py`

**校验项**（所有 Phase 退出前必须 100% 通过）：

| # | 校验项 | 失败时影响 | 实现方式 |
|---|--------|-----------|---------|
| 1 | 章节完整性 | Phase 2/4 失败 | 扫描 `# 第[1-7]章` 数量 |
| 2 | 字数门槛 | Phase 2/4 失败 | `wc -l` 统计 |
| 3 | 参考文献存在 | Phase 4 失败 | 扫描 `## 参考文献` 标题 |
| 4 | 无 `## 第X章` 混合格式 | Phase 2/4 失败 | 正则匹配 |
| 5 | 无 `**正文加粗**` | Phase 2/4 失败 | 正则匹配（排除标题级） |
| 6 | 引用完整性 | Phase 2/4 失败 | 扫描 `(作者，年份)` 模式 |
| 7 | 三线表无竖线 | Phase 4 失败 | 扫描 `|` 模式 |
| 8 | 表格标题在表上方 | Phase 4 失败 | 上下文检查 |
| 9 | 合并残留检查（`===END===`） | Phase 4 失败 | 字符串扫描 |
| 10 | 核心章节关键词检查 | Phase 2.5 失败 | 关键词匹配（第5章战略/第6章实施） |

**使用方式**：

```bash
# 校验单个文件
python3 scripts/loop_self_check.py --file 论文_xxx.md

# 校验整个 Phase
python3 scripts/loop_self_check.py --phase 2 --workspace ~/.openclaw/workspace/

# 输出 JSON 报告
python3 scripts/loop_self_check.py --file 论文_xxx.md --json > check_report.json
```

**校验失败时的处理**：
- 软错误（可自动修复）→ 自动修复并重试
- 硬错误（需 Agent 决策）→ 打回当前 Phase 重做
- 累计 3 次失败 → 强制 Human-in-the-loop

---

## Verification Loop（v1.7 新增）

**目标**：Word 输出后自动校验格式，失败则提示并可选择打回 Phase 4 修复。

**实现方式**：

```bash
# Phase 5.2 完成后自动触发
python3 scripts/loop_self_check.py --file 论文_xxx_v4.0_终稿.docx --verify-docx
```

**校验项**（Word 文档）：

| 校验项 | 实现方式 |
|-------|---------|
| 分页符（每章后） | python-docx 扫描 page break |
| 三线表 | 扫描表格边框 |
| 标题层级（黑体 16/14/13 磅） | 扫描 run.font |
| 正文行距 20 磅 | 扫描段落格式 |
| `**加粗**` 已过滤 | 扫描 run.text 模式 |
| 参考文献中英文分编 | 扫描文档结构 |

**失败处理**：
- 软错误（脚本可修复）→ 自动修复并重新生成
- 硬错误（数据问题）→ 提示用户并打回 Phase 4

---

## 与 OpenClaw Agent Loop 的对应关系

| OpenClaw / Loop Agent 概念 | MBA Skill 实现 |
|--------------------------|---------------|
| Agent loop（自动推进） | Orchestrator Loop |
| Tool invocation | sessions_spawn / exec / hermes chat |
| Self-correction | 审核 Loop（Phase 3 + 3.5 + 修订） |
| Guardrails | loop_self_check.py 脚本 |
| Human-in-the-loop | Phase 1/2.5/4 强制用户确认 |
| Sessions（持久状态） | `*_任务状态.json` |
| Tracing（追踪） | 各 Phase 输出文件 + 状态文件 |
| Verification | Verification Loop（Word 格式校验） |

**关键差异**：MBA Skill 是**多阶段状态机 + 内部 Loop** 的混合架构，不是纯 Loop Agent。这是有意为之——MBA 论文是**高 stakes 任务**，需要明确的状态边界和人工检查点，不能完全自动化。

---

## v1.8 路线图（待实现，本节为设计预览）

> **本节为 v1.8 路线图，仅作设计预览。** v1.7 的 Guardrails 脚本与 Loop 元素已可用，v1.8 将把"决策逻辑"从伪代码（写在 SKILL.md 里）升级为可执行脚本。

### v1.8 的目标

将 v1.7 写在 SKILL.md 里的**伪代码决策逻辑**（Orchestrator Loop），升级为**可执行的 `orchestrator.py` 脚本**，实现"用户不用每步 trigger、Orchestrator 自己跑"。

### 4 个子任务

#### 子任务 1：状态文件自动生成与维护

**目标**：状态文件 `*_任务状态.json` 不再靠 agent 手写，由 orchestrator.py 自动管理。

**关键改动**：
- 引入 `orchestrator/state_manager.py`
- 提供 API：`load_state()` / `save_state()` / `update_phase()` / `increment_retry()`
- 状态文件 schema 文档化（v1.7 已有非正式 schema，v1.8 正式化）

**预计代码量**：~150 行

#### 子任务 2：Orchestrator 主循环可执行化

**目标**：把 v1.7 写在 SKILL.md 里的 `decide_next_action(state)` 伪代码，移植到 `orchestrator/main.py`。

**关键改动**：
- 引入 `orchestrator/main.py`（主循环）
- 决策树从伪代码 → Python 代码
- 集成 `loop_self_check.py`（v1.7 已实现）作为输入
- 输出：`Phase X → Phase Y` 决策 + 自动调用 `sessions_spawn` 触发下一 Phase

**预计代码量**：~300 行

**决策树示例**（v1.7 伪代码 → v1.8 Python）：
```python
# v1.7 伪代码（写在 SKILL.md）
def decide_next_action(state):
    if state["phase"] == "Phase 2 完成":
        if all_chapters_exist(state):
            return "进入 Phase 2.5"
        else:
            return "打回 Phase 2"

# v1.8 Python（写在 orchestrator/main.py）
def decide_next_action(state: dict) -> str:
    phase = state.get("phase")
    if phase == "Phase 2 完成":
        chapters = state.get("chapters", {})
        all_done = all(c.get("status") == "completed" for c in chapters.values())
        if all_done:
            return Action.ENTER_PHASE_2_5
        else:
            missing = [k for k, v in chapters.items() if v.get("status") != "completed"]
            return Action.ROLLBACK_TO_PHASE_2.with_reason(f"缺失章节: {missing}")
```

#### 子任务 3：自动 spawn 与状态联动

**目标**：Orchestrator 决策后**自动触发下一 Phase 的 subagent**，并把状态联动起来。

**关键改动**：
- 引入 `orchestrator/trigger.py`
- 接收决策结果 → 构造 `sessions_spawn` 调用 → 等待 subagent 完成 → 更新状态
- 失败重试机制（v1.7 概念 → v1.8 可执行）

**预计代码量**：~200 行

#### 子任务 4：Human-in-the-loop 检查点封装

**目标**：把 v1.7 列出的 4 个强制人工确认节点（Phase 1/2.5/4/5.2）做成"标准中断点"。

**关键改动**：
- 引入 `orchestrator/hil.py`
- 提供 `request_user_confirmation(checkpoint, content)` API
- Orchestrator 遇到检查点 → 暂停 → 发飞书消息 → 等用户回复 → 继续

**预计代码量**：~100 行

### v1.8 优先级与依赖

| 子任务 | 优先级 | 依赖 | 预计工期 |
|-------|--------|------|---------|
| **1. 状态文件管理** | 🔴 P0 | 无 | 1 天 |
| **2. Orchestrator 主循环** | 🔴 P0 | 子任务 1 | 2 天 |
| **3. 自动 spawn 联动** | 🟡 P1 | 子任务 1, 2 | 1 天 |
| **4. HIL 检查点封装** | 🟡 P1 | 子任务 1 | 0.5 天 |

**建议执行顺序**：1 → 2 → 3 → 4（串行）

### v1.8 改动影响范围

- ✅ **不破坏 v1.7**：v1.7 的 Guardrails 脚本、Loop 元素、文档全部保留
- ✅ **不破坏主流程**：7 阶段状态机不变
- 🆕 **新增**：`orchestrator/` 目录（4 个 Python 文件）
- 🆕 **新增**：`orchestrator.py` 主入口脚本
- 🆕 **可选**：把 v1.7 写在 SKILL.md 里的伪代码**搬走**（搬到 `orchestrator/main.py`），SKILL.md 只保留设计理念

### v1.8 成功标准

- [ ] 用户启动论文任务后，**不需要每步 trigger**
- [ ] Orchestrator 自动读取状态 → 决策 → 触发 → 更新 → 循环
- [ ] 4 个 Human-in-the-loop 节点正常工作
- [ ] Guardrails 失败时自动打回对应 Phase
- [ ] 累计 3 次失败强制 HIL
- [ ] 全部 7 个 Phase 完成后自动退出 Orchestrator Loop

### 何时启动 v1.8？

**建议条件**（任一满足即可启动）：
- v1.7 的 Guardrails 脚本在实际论文中验证 ≥ 3 次无 bug
- 用户提出"希望 Orchestrator 真的能自动跑"
- 出现手动 trigger 失误导致流程中断的情况

### 不在 v1.8 范围（v2.0+ 考虑）

- ❌ 多论文并行（依赖 v1.8 状态文件抽象）
- ❌ 导师反馈 Loop（需要外部接口）
- ❌ AI 辅助选题（前置 Loop，不在主流程内）
- ❌ 跨论文知识库（独立子系统）

---

## 附录：v1.7 → v1.8 → v2.0 演进路径

```
v1.7（当前）        v1.8（路线图）       v2.0（未来）
  │                   │                    │
  ├─ Loop 概念声明    ├─ Orchestrator.py  ├─ 多论文并行
  ├─ Guardrails 脚本  ├─ 状态文件管理     ├─ 导师反馈 Loop
  ├─ 参考文档         ├─ 自动 spawn 联动  ├─ AI 辅助选题
  └─ (伪代码决策树)   └─ HIL 检查点封装   └─ 跨论文知识库
       │                   │                    │
       └──── 渐进式升级 ────┴──── 长程演进 ─────┘
```

**设计原则**：
- 每个版本都是 additive changes（不破坏上一版）
- 每个版本都有独立可用价值
- 每个版本都有明确退出标准




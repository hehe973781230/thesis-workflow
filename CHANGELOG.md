# CHANGELOG - MBA/学术论文多Agent协作工作流

所有重要更新都会记录在此文件。

## [v1.7.5] - 2026-06-23

### 增强项4 — 写作前信息检查（content_hint 接入 + 信息贫瘠检查）

**问题**：节点写作前如果完全没有外部信息（content_hint 空 + 用户 hints 空 + bridge 三级全空），NodeWriter 拿到 prompt 后缺乏上下文，LLM 自由发挥质量差。

**拍板决策**（龙哥 2026-06-23 确认）：
- 判断标准 A：content_hint + user_hints + bridge **任一为空** → needs_user_input
- 3 个选项全保留：用户提供 hint / AI 自行生成 / 跳过节点
- Phase 1 完成时一次性写入 state（持久化）
- 允许用户手动覆盖 content_hint

### 代码变更

- **`outline_parser.py`**：
  - `save_content_hints_to_outline(paper, hints)`：提取的 content_hint 写入 outline_state，跳过特殊 key 和不存在节点
- **`state_manager_v2.py`**：
  - `outline_update_status()` 新增 `content_hint` 字段透传参数
- **`context_builder.py`**：
  - `build_prompt_package()` 新增 `content_hint` 字段
  - `build_prompt_package_text()` 新增 `## 开题报告方向参考` section
- **`orchestrator_v2.py`**：
  - `check_info_scarcity(paper, node_id)`：3 项数据源检查 + 标准 A 判断
  - `apply_user_decision(paper, node_id, decision, user_hint)`：3 个决策路径处理
  - `write_single_node()` Step 1.5：写作前信息检查，需要时返回 `action="needs_user_input"`

### 测试覆盖（8 个测试用例）

- `test_info_scarcity.py`：
  - save_content_hints 基本写入 + 跳过特殊 key
  - 3 项全空 → needs_user_input
  - 部分缺失 → needs_user_input（标准 A）
  - 3 项齐备 → proceed
  - 决策 1/2/3 三个路径
  - 完整端到端闭环

总测试数：25 (v1.7.3) + 20 (v1.7.4) + **8 (v1.7.5) = 53 个**

## [v1.7.4] - 2026-06-23

### 增强项1 — 跨父节点 Bridge（章节摘要节点）

**问题**：`2.1` 找不到 `1.2` 的 `key_conclusion`，bridge 断裂 → NodeWriter 拿不到承接段。

**方案 C**：在每个 L1 章节末尾插入虚拟章节摘要节点 `__ch{N}_summary__`，吸收本章所有 L2/L3 子节点的 `key_conclusion`，为下一章节 bridge 提供承接依据。

### 代码变更

- **`outline_parser.py`**（新增 3 函数）：
  - `insert_chapter_summary_nodes(outline)`：在每个 L1 章节末尾插入虚拟节点（幂等）
  - `get_chapter_summary_id(chapter_id)`：`ch1` → `__ch1_summary__`
  - `get_chapter_id_from_summary(summary_id)`：`__ch1_summary__` → `ch1`
- **`orchestrator_v2.py`**（新增 3 函数 + 修改 1 函数）：
  - `is_last_child_of_chapter(paper, node_id)`：判断节点是否是所属章节最后一个完成的子节点
  - `synthesize_chapter_summary(paper, chapter_id, llm_func, user_input=None)`：LLM 合成 200-300 字章节摘要，写入虚拟节点
  - `_build_summary_prompt(chapter_title, child_conclusions, user_input)`：合成 prompt
  - `write_single_node()` Step 4.5：节点完成回调中自动检测并触发章节摘要合成
- **`context_builder.py`**（新增 1 函数 + 修改 1 函数）：
  - `_build_bridge_from_chapter_summary(prev_chapter_summary, current)`：P3 fallback 跨章节桥接
  - `generate_bridge()`：新增 P3 优先级（P1 prev → P2 parent → P3 prev_chapter_summary）
- **`state_manager_v2.py`**（新增 1 函数 + 修改 1 函数）：
  - `_get_prev_chapter_summary(node, nodes, node_map)`：查上一章节虚拟摘要
  - `outline_get_context()`：自动附加 `prev_chapter_summary` 字段

### 测试覆盖（20 个测试用例）

- `test_chapter_summary.py`：单/多章节插入、L3 纳入 synthesizes、幂等性、边界、辅助函数（6 个）
- `test_synthesize_summary.py`：last_child 检测、LLM 路径、用户输入路径、LLM 失败 ask_user、空子节点、超长截断（6 个）
- `test_bridge_p3_fallback.py`：P1/P2 优先级、P3 跨章节桥接、不可用降级、首章节、context 自动附加（6 个）
- `test_integration_chapter_summary.py`：happy path + LLM 失败 fallback 端到端（2 个）

### 拍板决策（龙哥 2026-06-23 确认）

1. ✅ 方案 C（虚拟摘要节点）
2. ✅ 200-300 字够了
3. ✅ **LLM 失败时询问用户**（不是简单拼接）
4. ✅ 章节摘要不参与 Phase 3 评审（仅作内部辅助 bridge）
5. ✅ 在 `references/` 增加设计文档

## [v1.7.3] - 2026-06-19

### P0 修复

- **分页逻辑修正**：每章标题前分页（原为标题后分页导致空页），首章跳过
- **审核报告匹配增强**：改用 glob 通配匹配 + 结构化评分字段优先，不再依赖 emoji 硬编码
- **Verification Loop 真实校验**：新增字体/字号/行距/三线表边框/加粗残留/参考文献分编 6 项 Word 格式实质检查
- **空壳校验填补**：`check_table_format` 和 `check_table_caption_position` 从永远 `return True` 改为真实列数一致性和表标题位置检测
- **文件名泛化**：`*report*.md` 收窄为中文 `*报告*.md` + 大小写补充，`_find_review_report` Level 3 加论文关键词过滤
- **`_check_report_passed` 优先级重排**：综合评级 → 结构化评分 → emoji 回退，🔴 阈值从 5 放宽到 8
- **`_copy_proposal_cover` 锚点式匹配**：从硬编码"研究背景与研究问题"改为多锚点正则（第X章/1./研究背景/摘要等）
- **去重格式校验**：`md2docx_strict.py` 移除 `validate_md_format()`，统一由 `loop_self_check.py` 负责
- **硬编码参数化**：`min_lines`/`min_citations` 改为常量配置
- **代码风格统一**：8 个内部函数统一下划线 `_` 前缀

### Loop 架构落地

- **新增 `scripts/orchestrator.py`**：决策引擎 + 审核 Loop 自动重审 + Phase 完成自动校验
- **增强 `scripts/state_manager.py`**：新增 `parse_p0_from_report`、`set_hil_pause`、`clear_hil_pause`、`next_phase_name` 等 6 个方法
- **新增 `scripts/tests/`**：25 个单元测试覆盖 state_manager/loop_self_check/md2docx_strict
- **SKILL.md 精简**：1142 行 → 253 行（-78%），新增 Orchestrator 生命周期管理与 HIL 节点表

### 依赖变更

- `install.sh`：`pip install` → `python3 -m pip install --user python-docx`

## [v1.7] - 2026-06-17

### Loop Agent 架构（新增）

- **Orchestrator Loop**：每 Phase 完成后自动判断下一步，取代手动 trigger 模式
- **Phase 内部自检 Loop**：Observe → Think → Act → Verify 四步循环
- **审核 Loop**：Phase 3.5 → 修订 → 自动重审 → 连续 2 轮无新 P0 → 通过
- **Guardrails 校验**：10 项自动化规范检查（章节完整性/字数/引用/三线表/加粗等）
- **Verification Loop**：Word 输出后自动校验格式
- **Human-in-the-loop 检查点**：4 个强制人工确认节点

### 新增文件

- `scripts/loop_self_check.py`：Guardrails 自动化校验脚本（10 项校验 + JSON 输出）
- `references/checklist.md`：学术规范人工对照清单
- `references/loop-design.md`：Loop 设计原理说明文档

### 规则型 vs 审核型分工

- 脚本已覆盖的规范（字体/行距/标题层级/三线表），Agent 不再重复检查
- Agent 专注于脚本无法处理的事项（摘要字数/逻辑链/数据可信度/学术创新性）

---

## [v1.6] - 2026-06-02

### 新增功能

- **Phase 5.1 可选去AI味**：新增 HumanizerAgent，调用 humanize-chinese skill 执行学术风格降重，支持 CLI 脚本批量处理 + 差异报告
- **Phase 5.2 Word生成**：拆分独立步骤，支持生成两份Word（原版 + 润色后版）
- **前置检测机制**：去AI味前自动检测 humanize-chinese skill 是否安装，未安装则提示用户确认后自动安装
- **Phase 2 执行前检查表**：每次启动 Phase 2 前强制确认，包括 Phase 1 七项清单、章节×版本对照表、完成判定标准
- **章节×版本对照表**：枚举每个章节的 Executor（版本O）和 Hermes（版本H）要求，明确「必须」spawn，不可遗漏
- **Phase 2 强制检索要求**：新增5项强制检索检查项（PESTEL分析前/五力模型前/战略理论前/引用来源/检索记录≥3次），不满足则打回补充
- **Phase 2 完成判定标准**：版本O文件6个+版本H文件4个全部存在，ls验证，缺一则禁止进入 Phase 2.5
- **正文目录章节禁止规则**：写作规范新增，明确禁止在正文章节内自建「目录」章节
- **md2docx_strict.py 审核报告模糊匹配**：支持 `审核报告*.md` 命名规范模糊匹配（Level 1精确/Level 2模糊/Level 3候选列表）

### 移除功能

- **移除邮件发送流程**：Phase 5.2 改为仅生成Word并告知存储位置（`~/.openclaw/workspace/`）
- **移除联系方式必填**：Phase 1 确认清单去掉联系方式（微信/飞书ID）要求，去AI味后由用户自行取用文件
- **删除 Phase 5.5 成果发送**：整节移除，减少不必要的流程节点

### 架构升级

- **Agent 角色体系重构**：Orchestrator（调度）/ Executor（H-generator执行）/ Reviewer（规则型审核）/ DeepReviewer（学术深度评审）/ Integrator（整合方案）/ WordAgent（Word输出）/ HumanizerAgent（去AI味）七类专职分离
- **Agent 设计原则**：职责单一化，调度者不执行，执行者不调度；职责边界清晰
- **Phase 3.5 固定节点**：Phase 3 完成即触发，不得跳过，作为固定流程节点
- **Phase 3.5 分级标准**：P0（致命）/ P1（严重）/ P2（建议），审核报告结构化分级

### 修复问题

- **Phase 2 章节遗漏问题**：通过章节×版本对照表强制要求每个 ✅ 都是独立 spawn，防止核心章节（3/4/5/6）遗漏版本O或版本H
- **正文目录章节问题**：新增写作规范禁止正文内自建目录章节

---

## [v1.5] - 2026-06-01

### 新增功能

- **md2docx_strict.py 合规脚本**：严格按MBA论文格式规范转换（分页符/三线表/加粗过滤/标题层级/行距/中英文字体）
- **Phase 5 Word输出流程**：Review Agent终审 → 格式自检 → md2docx_strict.py → 发送，三步缺一不可

### 修复问题

- **Word格式问题**：分页符、标题层级、行距、加粗过滤、中英文参考文献格式
- **审核报告命名规范**：统一为 `审核报告_{论文题目}_Phase{N}_{版本}.md`

---

## [v1.0] - 2026-05-31

### 首次发布

- 多Agent协作工作流（Phase 1-5）
- 双版本起草机制（版本H + 版本O）
- Phase 3 审核（7个维度）
- Phase 4 整合方案
- md2docx 脚本（基础版）

# Outline-Anchored 重构待办项

> 记录 feature/outline-anchored 分支的重构计划和进度
> 分支: `feature/outline-anchored`，基于 `main` 分支

---

## ✅ 已完成

- [x] Step 1: 目录解析器 `outline_parser.py` + 状态管理器 `state_manager_v2.py`
- [x] Step 2: ContextBuilder `context_builder.py`

---

## 🔲 Step 3: NodeWriter 接入

将 ContextBuilder 的 prompt 包接入 NodeWriter，
NodeWriter 接收 `build_prompt_package()` 输出，不再接收 in-context prompt。

---

## 🔲 Step 4: Reviewer 接入

Reviewer 接收节点写作结果，执行学术评审，
评审通过后写入 `key_conclusion`。

---

## 🔲 Step 5: 全链路联调

Orchestrator 驱动完整流程：
Phase 1 → 目录解析 → 逐节点写作 → 评审 → 整合 → Word 输出

---

## 📋 增强项（Step 2 补充）

### 跨父节点 Bridge 支持 — 章节摘要节点（方案C）

**问题**：`2.1` 找不到 `1.2` 的 key_conclusion，bridge 断裂。

**方案**：
- 在每个一级章节末尾自动插入虚拟 `__chN_summary__` 节点
- 该节点吸收本章所有 L2/L3 的 `key_conclusion`，生成章节级摘要
- 下一章节的 bridge 可引用前一章节的摘要节点

**触发时机**：
- **时机A（自动）**：章节末尾最后一个 L2/L3 节点完成 → 自动触发章节摘要生成
- **时机B（补充）**：用户在 Phase 1.3 自定义分析维度时填的"本章核心问题"，作为摘要生成的**补充参考**，不直接作为摘要正文

**状态**：待开发

### 增强项：开题报告内容复用与归因体系

**目标**：将开题报告中的内容尽可能复用，避免遗漏，建立完整的节点内容管理机制。

**内容状态体系**：
- `proposal`（≥80%利用率）：直接复用开题报告内容
- `mixed`（30-80%）：复用 + AI扩写至目标字数
- `generated`（<30%）：AI基于content_hint重写
- `pending`：提取失败，需用户指定

**归因三步流程**：
1. **精确匹配**：段落标题与目录节点完全一致的，直接建立映射
2. **语义归因（AI）**：无法精确匹配的段落，逐段调用AI判断归属节点ID
3. **归因展示（用户确认）**：AI归因结果展示给用户确认，可调整

**游离内容处理（方案C）**：
- 无法归因的段落存入 `orphan_segments` 池
- Phase 1.3 额外展示"未分配内容"列表
- 用户可手动将游离内容分配到目标节点

**阈值**：利用率 ≥80% / ≥30% / <30% 三档划分

**状态**：待开发

### 增强项：开题报告内容提炼 → 目录节点方向提示

**问题**：Phase 1.3 用户填写"分析重点"时为空，需要从零填写，体验差。

**方案**：
1. `outline_parse()` 时同步提取开题报告正文：每个目录节点下方前 1-2 句作为 `content_hint`
2. 存入节点的 `content_hint` 字段（新增字段）
3. Phase 1.3 展示时预填这些 AI 提炼的方向提示，用户可查看、修改、新增

**实现位置**：
- `outline_parse()` 或新增 `extract_content_hints(docx_path, outline_tree)`
- `outline_tree` 节点新增 `content_hint: str`
- Phase 1.3 prompt 中引用 `node.content_hint` 作为预填参考

**状态**：待开发

# Changelog

All notable changes to this project will be documented in this file.

## [2.0.18-beta] - 2026-07-01

### Added

- **P0 修复 - LLM 一次性兑底补全空 hint 节点**：新增 `_llm_fill_empty_hints()` 函数，在 `extract_content_hints()` 末尾调用。
  - 背景：之前 hint 只从"开题报告匹配段落"提取，没匹配上的节点（orphan）就没 hint，导致 70%+ 节点空 hint。Phase 2 写作时 LLM 靠"大纲骨架"勉强写但容易跑题。
  - 策略：调一次 LLM，输入所有空 hint 节点 (id + title + 论文主题)，输出 JSON 数组 hint 字典。
  - 优势：v8.0 实测从 26% 覆盖 → 100% 覆盖。
  - 兑底安全：LLM 失败 → 返回原 content_hints，不阻断主流程。
  - 零额外调用：全部节点已有 hint 时不调 LLM。

### Technical

- `outline_parser.py` 新增辅助函数：`_llm_fill_empty_hints()` (~80 行)
- `extract_content_hints()` 末尾调用 LLM 兑底逻辑（~5 行）
- Prompt 优化：中文 MBA 论文语境，JSON 数组输出格式约束

### Impact

- 任何使用 v2 框架的论文都受益，不限于南大 MBA 模板
- 一次 LLM 调用可补全 30-50 个空 hint（token 友好）
- 后续 Phase 2 LLM 写作时上下文约束更精准，间接提升论文质量

## [2.0.17-beta] - 2026-07-01

### Fixed

- **P0 - 解析路径对 Word 自定义样式失效**：`outline_parser` 走 MinerU 路径时，docx 中的 Word 自定义样式（如南大 MBA 模板的 `MBA-章标题` / `MBA-一级节标题`）被降级为普通文本，结构信息丢失，导致 Phase 1.1 大纲解析严重错位。修复后 v8.0 解析从 13 个错位节点 → 55 个真实节点 + 7 虚拟 summary = 62 节点。
- **路径顺序重构**：主入口 `extract_outline_from_docx` 的解析顺序从 B → A 改为 C → B → A，新增 C 路径优先于 MinerU。

### Added

- **C 路径：`extract_outline_from_docx_with_custom_styles`** (~60 行)
  - 基于 `python-docx` 直接读 Word 段落 + 样式，不依赖 MinerU
  - 避免 MinerU 的隐私风险（不上传 docx 到云端）+ 速度更快
  - 通过 `CUSTOM_OUTLINE_STYLES` 配置项支持自定义样式名（默认含 `MBA-章标题` / `MBA-一级节标题` / `Heading 1/2/3`）
  - 大纲区起点：自定义 L1 样式 + 含"论文大纲"/"目录"等锚点词
  - 大纲区终点：含"参考文献"的段落
  - 章节行收集：L2/L3 样式（`MBA-一级节标题`）+ 文本模式 `^第N章`（L1 用 Normal 样式兜底）

### Technical

- `outline_parser.py` 新增常量：`CUSTOM_OUTLINE_STYLES`（dict of style tuples）
- `OUTLINE_START_ANCHORS` 扩展：增加 "4.  论文大纲" 等带编号前缀的锚点
- 主入口 `extract_outline_from_docx` 路径顺序：C → B → A（v2.0.7 文档同步更新）

### Impact

- **南大 MBA 论文模板**（`MBA-章标题` + `MBA-一级节标题`）：从完全无法解析 → 62 节点全对
- 其他使用 Word 自定义样式（非 Heading 1/2/3）的论文模板均受益
- 现有用户（v1 模板 / Heading 1/2/3 用户）行为不变（C 路径找不到锚点会降级到 B 路径）

## [2.0.16-beta] - 2026-06-28

### Fixed

- **P0 - 硬编码路径问题**：`save_content_hints_to_outline` 硬编码 `~/.openclaw/workspace` 路径，导致 THESIS_WORKSPACE 环境变量不生效。改用 `_get_state_path()` 统一路径计算。
- **P1 - 嵌套结构兼容层**：新增 `_get_outline_nodes()` / `_set_outline_nodes()` 两个 helper 函数，统一处理 3 种历史嵌套结构：
  - 结构 A: `state["outline"]["outline_tree"]["nodes"]` （期望结构）
  - 结构 B: `state["outline"]["nodes"]` （简化结构）
  - 结构 C: `state["outline"]["outline"]["outline_tree"]["nodes"]` （旧版嵌套）
- **P1 - 19 处硬编码替换**：state_manager_v2 (7处) + orchestrator_v2 (10处) + outline_parser (2处) 的 `state["outline"]["outline_tree"]["nodes"]` 全部替换为 `_get_outline_nodes(state)`
- **P1 - 隐藏 bug 修复**：`_set_outline_nodes` 中 `if not state` 改为 `if state is None`，修复空 dict `{}` 作为 falsy 值导致函数直接 return 的问题
- **P1 - 防御性压平逻辑**：`outline_save` 写盘前自动将 C 结构压平为 A 结构，保证磁盘持久化为标准结构

### Technical

- 新增 helper：`state_manager_v2._get_outline_nodes()` / `_set_outline_nodes()`
- orchestrator_v2.py 新增导入：`_get_outline_nodes`
- outline_parser.py 新增导入：`_get_state_path`, `_get_outline_nodes`, `_set_outline_nodes`
- `save_content_hints_to_outline` 重写：约 20 行（读+写统一走 helper）

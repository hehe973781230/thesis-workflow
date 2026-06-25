# CHANGELOG - MBA/学术论文多Agent协作工作流

所有重要更新都会记录在此文件。

## 当前推荐版本

| 版本线 | 当前 latest | ClawHub Slug | 状态 |
|--------|------------|--------------|------|
| **v1.x**（稳定版）| v1.7.3 | `thesis-workflow` | 长期维护，仅兼容性修复 |
| **v2.x**（新框架）| v2.0.8-beta | `thesis-workflow-v2` | ⚠️ 测试版，multi-search并行引擎 + RuntimeLLM |

> **重要**：v1 和 v2 是**两个独立发布的 skill**，用不同 ClawHub slug，**安装路径不同**，**互不影响**。
> 详见 `references/git-workflow.md` 和分支管理策略。

## 版本线索引

- **v1.x 历史**：见 [CHANGELOG-v1.md](./CHANGELOG-v1.md)
  - v1.0 → v1.7.3 完整历史
  - 当前 ClawHub `thesis-workflow` latest
- **v2.x 历史**：见 [CHANGELOG-v2.md](./CHANGELOG-v2.md)
  - v2.0.0 → v2.0.8-beta 完整历史
  - v1.7.4-v1.7.7 实际为 v2 早期 alpha 版本（commit hash 保留）
  - 当前 ClawHub `thesis-workflow-v2` latest

## 迁移指南

- **v1 → v1**：标准升级，无破坏
- **v1 → v2**：**不自动升级**。需手动 `openclaw skills install thesis-workflow-v2`，独立测试后再切换
- **v2 → v1**：降级需 `openclaw skills remove thesis-workflow-v2` + `install thesis-workflow`

## 选型决策

| 场景 | 推荐版本 |
|------|----------|
| 生产环境论文 | v1.7.3（稳定，已验证）|
| 新功能/新设计尝试 | v2.0.6（新框架，需测试）|
| 同时跑多篇论文 | 两个都装（互不干扰）|

## 详细历史

- 📄 [CHANGELOG-v1.md](./CHANGELOG-v1.md) — v1.x 完整历史
- 📄 [CHANGELOG-v2.md](./CHANGELOG-v2.md) — v2.x 完整历史 + alpha 阶段说明
- 📄 [references/git-workflow.md](./references/git-workflow.md) — 分支管理 + 发布流程

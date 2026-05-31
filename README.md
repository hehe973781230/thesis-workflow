# MBA Thesis Workflow

MBA 论文写作辅助 Skill，支持双版本对比（Hermes + OpenClaw）、多阶段审核、格式整改、Word 输出与邮件发送。

## 安装

### 方式一：手动安装

```bash
# 1. 复制到 skills 目录
cp -r mba-thesis-workflow ~/.openclaw/workspace/skills/

# 2. 填写配置
cp config.template config.env
# 编辑 config.env，填入实际值

# 3. 确认依赖 skill 已安装
openclaw skills check
```

### 方式二：打包安装

```bash
# 解压到 skills 目录
tar -xzf mba-thesis-workflow.tar.gz
cp -r mba-thesis-workflow ~/.openclaw/workspace/skills/
```

## 配置

首次使用前需要填写 `config.env`：

```bash
WORKSPACE_ROOT=~/.openclaw/workspace
USER_EMAIL=your_email@example.com
SENDER_EMAIL=your_qq_email@qq.com
AUTHOR_NAME=你的姓名
```

### 配置说明

| 变量 | 说明 | 示例 |
|------|------|------|
| `WORKSPACE_ROOT` | 论文文件的存放目录 | `~/.openclaw/workspace` |
| `USER_EMAIL` | 论文终稿发送目标邮箱 | `student@uni.edu.cn` |
| `SENDER_EMAIL` | 发件邮箱（QQ邮箱） | `123456789@qq.com` |
| `AUTHOR_NAME` | 作者姓名 | `张三` |

## 使用流程

### Phase 1：写作任务书签订

与 AI 对话确认：
- 论文题目、大纲结构
- 邮箱地址
- 特殊要求

### Phase 2：双版本起草

- **版本O**：OpenClaw subagent 执行
- **版本H**：Hermes CLI 执行（若 Hermes 不可用则自动回退到 OpenClaw）

### Phase 3：审核

- Review Agent 审核版本O
- Review Agent 审核版本H

### Phase 4：整合

- 生成整合方案
- 执行格式整改（清除加粗、三线表、引用标注）

### Phase 5：终审与输出

- 最终审核
- Word 文档输出（符合 MBA 格式）
- 邮件发送至 `USER_EMAIL`

## 依赖

### 必须

- `academic-research` skill（学术文献搜索）
- `multi-search-engine` skill（行业数据搜索）

### 可选

- `hermes` CLI（若安装则使用双版本模式，否则回退到单 OpenClaw 版本）

### 环境要求

- Python 3.11+
- python-docx 库

## 常见问题

### Q: Hermes 不可用时会怎样？
A: 自动检测 Hermes 可用性，不可用时回退到 OpenClaw subagent 执行版本H的任务。

### Q: 邮件发送失败怎么办？
A: 检查 `config.env` 中的 `SENDER_EMAIL` 是否正确，以及 QQ 邮箱 SMTP 授权码是否有效。

### Q: 如何查看生成进度？
A: 在工作区目录下执行 `ls -la 论文_A公司_v*.md` 查看各章节文件状态。

## 目录结构

```
mba-thesis-workflow/
├── SKILL.md              # 主配置
├── README.md             # 本文件
├── config.template       # 配置模板
└── scripts/
    └── md2docx_strict.py # Word转换脚本
```

## 更新日志

### v1.0.0 (2026-05-31)
- 初始版本
- 支持双版本对比（Hermes + OpenClaw）
- 支持多阶段审核与整合
- 支持 Word 格式输出与邮件发送
- Hermes 不可用时自动回退到 OpenClaw
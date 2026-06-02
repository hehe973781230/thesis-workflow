# MBA / Academic Thesis Multi-Agent Workflow

A complete workflow for writing MBA and academic theses using multi-agent collaboration, supporting dual-version drafting, review, integration, and finalization.

Suitable for the full lifecycle from thesis proposal to final graduation thesis.

## Core Features

- **Dual-Version Drafting**: Version H (Hermes deep reasoning) + Version O (OpenClaw format compliance)
- **Phase 3 Review**: 7-dimension strict review (format / outline / content accuracy / plagiarism check / academic standards / literature completeness / writing grammar)
- **Phase 3.5 Academic Deep Review**: 3-round deep review (macro structure → chapter-by-chapter → cross-chapter consistency)
- **Phase 4 Integration**: Review Agent produces integration plan, Orchestrator executes
- **Phase 5 Word Output**: md2docx_strict.py compliant script, Chinese/English font separation

## Supported Use Cases

- MBA graduation thesis (strategic management / corporate analysis)
- Academic research reports (competitive strategy / industry analysis)
- Formal long-form documents requiring multi-round review and multi-version integration

## Quick Start

### Method 1: Direct Install

```bash
openclaw skills install git:hehe973781230/thesis-workflow
```

### Method 2: ClawHub

```bash
openclaw skills search "mba thesis workflow"
openclaw skills install <slug>
```

## Workflow

```
User → Phase 1 (Confirmation Checklist) → Phase 2 (Dual-Version Drafting) → Phase 2.5 (User Confirmation)
     → Phase 3 (Review) → Phase 3.5 (Academic Deep Review) → Phase 4 (Integration) → Phase 5 (Finalization & Word Output)
```

## File Naming Convention

| Version | Description |
|---------|-------------|
| v1.0_*_H_*.md | Hermes version (deep reasoning) |
| v1.0_*_O_*.md | OpenClaw version (format compliance) |
| v2.0_Review*.md | Review report |
| v3.0_Integrated.docx | Integrated Word document |
| v4.0_Final.docx | Final Word document |

## Writing Standards

- **Citation Format**: GB/T 7714 Author-Year style (Author, Year)
- **Minimum Word Count**: 35,000 Chinese characters
- **Writing Grammar**: No `**bold**` emphasis in body paragraphs
- **Chinese Font**: SimSun 12pt, line spacing 20pt
- **English Font**: Times New Roman
- **Heading Fonts**: SimHei 16pt (level 1) / 14pt (level 2) / 13pt (level 3)

## Agent Architecture

| Role | Responsibility |
|------|---------------|
| Orchestrator | Task scheduling, workflow progression, node decisions |
| Executor | Version O drafting, format execution |
| H-generator | Version H drafting via Hermes CLI |
| Reviewer | Phase 3/5 rule-based rapid review |
| DeepReviewer | Phase 3.5 academic deep review |
| Integrator | Phase 4 integration plan design |
| WordAgent | md2docx execution + delivery |

## Tech Stack

- OpenClaw subagent (sessions_spawn)
- Hermes CLI (deep reasoning)
- academic-thesis-review-skill (academic deep review)
- md2docx_strict.py (Word conversion)

## License

MIT-0 — Free to use, modify, and distribute without attribution

## Author

GitHub: [hehe973781230](https://github.com/hehe973781230)

---

*If this skill is helpful to you, please give it a ⭐*

# Steering Template：project-doc-tracker

将以下内容复制到你的 AI 工具对应的规则文件中，让 AI 记住在每次有意义的变更后自动记录进展。

## 适配说明

| 工具 | 规则文件位置 |
| --- | --- |
| Kiro | `.kiro/steering/project-doc-tracker.md`（已内置，无需手动复制） |
| Claude Code | `CLAUDE.md` 或 `.claude/CLAUDE.md` |
| Cursor | `.cursorrules` 或 `.cursor/rules/*.mdc` |
| Windsurf | `.windsurfrules` |
| Codex | `AGENTS.md` |
| 其他 | 项目根目录的 `AGENTS.md` 或工具对应的规则文件 |

---

## 复制内容（粘贴到对应规则文件）

```markdown
## 项目进展跟踪规则

本项目使用 project-doc-tracker skill 持续记录开发进展。

### 何时记录

在以下情况发生后，主动更新跟踪文档，无需用户提醒：
- 完成一个功能或子功能的实现
- 修复了一个 bug
- 完成了一次重构或架构调整
- 一次对话中做了多个有意义的代码变更

### 如何记录

追加进展日志：
  python .agents/skills/project-doc-tracker/scripts/project_tracker.py \
    --project-root . log \
    --change-type <feature|bugfix|refactor|docs|research|decision> \
    --feature-id <功能ID> \
    --summary "本次做了什么" \
    --file "path/to/changed/file.py" \
    --next-step "下一步要做什么" \
    --confidence <high|medium|low>

同步更新概览：
  python .agents/skills/project-doc-tracker/scripts/project_tracker.py \
    --project-root . sync-item \
    --feature-id <功能ID> \
    --title "功能标题" \
    --status <in_progress|done|blocked> \
    --summary "当前状态一句话" \
    --next-step "下一步" \
    --file "关键文件"

### 置信度规则

- high：直接来自代码变更或用户明确说明
- medium：从多个信号推断
- low：推测性结论，需标注"待确认"

### 不要做的事

- 不要凭记忆写高置信度结论，先看 git status 或变更文件
- 不要删除或覆盖 PROGRESS.md 的历史记录
- 不要自动修改 AGENTS.md、CLAUDE.md、.cursorrules 等规则文件

### 跟踪文档位置

docs/project-tracker/OVERVIEW.md   — 项目概览，活跃事项表
docs/project-tracker/PROGRESS.md   — 追加式会话日志
docs/project-tracker/features/     — 各功能详细说明

如果 docs/project-tracker/ 不存在，先运行：
  python .agents/skills/project-doc-tracker/scripts/project_tracker.py --project-root . init
```

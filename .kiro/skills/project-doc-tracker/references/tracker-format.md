# Tracker Format

## Tracker Root

```text
docs/project-tracker/
├─ OVERVIEW.md
├─ PROGRESS.md
└─ features/
```

## OVERVIEW.md

Use explicit markers so updates are stable even if surrounding headings change.

```markdown
# Project Tracker

## 项目简介
<!-- project-tracker:intro:start -->
待补充。
<!-- project-tracker:intro:end -->

## 当前活跃事项
<!-- project-tracker:items:start -->
| feature_id | 标题 | 状态 | 最近更新 | 下一步 | 关键文件 | 正式文档 |
| --- | --- | --- | --- | --- | --- | --- |
<!-- project-tracker:items:end -->

## 最近一次会话
<!-- project-tracker:session:start -->
待补充。
<!-- project-tracker:session:end -->

## 下一步建议
<!-- project-tracker:next:start -->
- core-agent: 补充回归测试
- memory-system: 优化向量检索
<!-- project-tracker:next:end -->

## 已知阻塞
<!-- project-tracker:blockers:start -->
- memory-system: 向量存储仍在内存中
<!-- project-tracker:blockers:end -->
```

## PROGRESS.md entry shape

Append a new section per session:

```markdown
## 2026-03-13T11:20:00+08:00
- change_type: feature
- feature_id: project-doc-tracker
- summary: 将项目规格从通用 Python 库重构为 skill 结构
- files: a.py, b.md
- next_step: 实现 helper script
- blockers: 无
- confidence: high
```

## Feature note shape

Use stable filenames such as `features/project-doc-tracker.md`.

`feature_id` should be a slug-like identifier containing only letters, numbers, `-`, or `_`.

```markdown
# Feature Note: project-doc-tracker

- feature_id: project-doc-tracker
- title: 项目文档跟踪 skill
- updated_at: 2026-03-13T11:30:00+08:00
- status: in_progress

## 背景

...

## 当前实现摘要

...

## 状态判断依据

- 修改了核心文件
- 完成了对应 spec 的主要任务

## 关键文件

- ...

## 相关文档

- .kiro/specs/example/design.md
- docs/project-tracker/OVERVIEW.md

## 风险与已知问题

...

## 后续建议

...

## 正式文档

待补充
```

Keep feature notes intentionally lightweight. They are tracker-side memory aids, not replacements for full docs.
They can be slightly richer than a bare card, but should still stay much shorter than `docs/modules/*.md`.

## Overview block behavior

- `sync-item` should merge rows by `feature_id`, not overwrite the full table with a single item.
- `下一步建议` should prefer keyed bullets such as `- feature-id: next step`.
- `已知阻塞` should prefer keyed bullets such as `- feature-id: blocker`.
- When a blocker is cleared, remove that feature's keyed blocker entry instead of leaving stale text behind.
- If a row already contains a formal doc path, `sync-item` should preserve it unless a new path is explicitly provided.

## Formal document handoff

When a feature is mature, create a full document outside the tracker, usually in `docs/modules/`.

Recommended relationship:

- `docs/project-tracker/features/<feature-id>.md`: lightweight note
- `docs/modules/<module>.md`: formal long-form document

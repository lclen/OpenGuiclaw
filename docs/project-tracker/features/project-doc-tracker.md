# Feature Note: project-doc-tracker

- feature_id: project-doc-tracker
- title: 项目文档跟踪 skill
- updated_at: 2026-03-13T15:20:00+08:00
- status: done

## 背景

为了解决长周期项目推进过程中“做过但忘了”的问题，引入专门的 tracker skill，把项目进展、下一步、阻塞项和正式文档链接统一沉淀到仓库内。

## 当前实现摘要

该 skill 已具备 init、log、sync-item、feature-note、status 五个稳定写入能力；同时新增 promote-to-doc 工作流，正式长文档交由 professional-markdown 输出，而不是扩展 Python 脚本生成长文档。`sync-item` 现已支持按 `feature_id` 合并更新多事项，并在后续普通更新中保留已有正式文档链接。`feature_id` 也已收紧为 slug-like 格式，避免路径穿越写坏其他文档。

## 状态判断依据

- 已完成 `project_tracker.py` 的多事项 merge、正式文档链接保留和 `feature_id` 安全校验
- 已补充最小回归测试覆盖正式文档保留和路径穿越拒绝
- tracker 目录和模块文档已同步更新，能支撑后续持续使用

## 关键文件

- .agents/skills/project-doc-tracker/SKILL.md
- .agents/skills/project-doc-tracker/scripts/project_tracker.py
- .agents/skills/project-doc-tracker/references/workflow.md
- .agents/skills/project-doc-tracker/references/tracker-format.md
- .kiro/specs/project-doc-tracker/

## 相关文档

- docs/project-tracker/OVERVIEW.md
- docs/project-tracker/PROGRESS.md
- docs/modules/project_doc_tracker.md

## 风险与已知问题

还没有内建自动判定“模块成熟度”的规则；批量正式文档生成仍依赖 AI 基于代码和 tracker 判断优先级。

## 后续建议

结合 professional-markdown 为成熟模块批量补正式文档；后续再接 automation 做周期性跟进。

## 正式文档

docs/modules/project_doc_tracker.md

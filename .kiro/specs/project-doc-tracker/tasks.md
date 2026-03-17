# 实现计划：project-doc-tracker

## 概述

将 `project-doc-tracker` 从“通用 Python 库”重构为“skill + scripts + references”的结构，先完成可用骨架，再逐步增强自动采集、摘要能力，以及与 `professional-markdown` 的正式文档协作。

## 任务

- [x] 1. 创建 skill 目录骨架
  - 创建 `D:\openGuiclaw\.agents\skills\project-doc-tracker\`
  - 创建 `SKILL.md`
  - 创建 `agents/openai.yaml`
  - 创建 `scripts/`
  - 创建 `references/`

- [x] 2. 编写 `SKILL.md`
  - 写清楚触发场景
  - 写清楚四种主要工作模式：初始化、记录会话、恢复上下文、收束功能
  - 写清楚证据采集顺序和低置信度处理
  - 写清楚优先调用 `scripts/project_tracker.py`

- [x] 3. 编写 reference 文档
  - [x] 3.1 `references/workflow.md`
    - 说明推荐工作流
    - 说明什么时候需要补看 git/spec/task
  - [x] 3.2 `references/tracker-format.md`
    - 说明 `OVERVIEW.md`、`PROGRESS.md`、Feature Note 的格式
    - 说明标记块名称

- [x] 4. 实现辅助脚本 `scripts/project_tracker.py`
  - [x] 4.1 实现 `init` 子命令
    - 创建 `docs/project-tracker/`
    - 创建 `OVERVIEW.md`
    - 创建 `PROGRESS.md`
    - 创建 `features/`
  - [x] 4.2 实现 `log` 子命令
    - 追加结构化会话日志
  - [x] 4.3 实现 `sync-item` 子命令
    - 更新 `OVERVIEW.md` 活跃事项表
    - 更新“最近一次会话”“下一步建议”“已知阻塞”标记块
  - [x] 4.6 将 `sync-item` 升级为多事项 merge
    - 按 `feature_id` 合并更新活跃事项表
    - 避免单次写入覆盖整张表
    - 将“下一步建议”“已知阻塞”维护为按功能分项的 bullet 列表
  - [x] 4.4 实现 `feature-note` 子命令
    - 创建或更新稳定文件名的轻量功能卡片
  - [x] 4.5 实现 `status` 子命令
    - 输出概览和最近若干条记录

- [x] 5. 接入正式文档协作工作流
  - [x] 5.1 在 `SKILL.md` 中增加 `promote-to-doc` 模式说明
    - 说明何时把轻量 feature note 提升为正式文档
    - 明确正式文档由 `professional-markdown` 生成
  - [x] 5.2 在 reference 文档中补充协作规则
    - 轻量卡片 vs 正式文档 的边界
    - 正式文档默认输出到 `docs/modules/`
  - [x] 5.3 支持批量正式文档生成工作流
    - 允许基于代码和 tracker notes 选择多个成熟模块
    - 逐个调用 `professional-markdown` 生成正式文档

- [x] 6. 补齐最小验证
  - 运行一次 `init`
  - 运行一次 `log`
  - 运行一次 `status`
  - 确认写入文档结构稳定

- [x] 7. 编写 steering 文件（让 AI 记住写进度）
  - 创建 `.kiro/steering/project-doc-tracker.md`（Kiro 用）
  - 创建 `.agents/skills/project-doc-tracker/references/steering-template.md`（通用模板，供 Claude Code / Cursor / Windsurf 等工具参考）
  - steering 内容：说明何时应调用 skill 记录进展、调用哪个脚本命令、置信度规则

- [x] 8. 验证 skill 元数据
  - 检查 `SKILL.md` frontmatter 格式
  - 检查 `agents/openai.yaml` 格式

- [ ] 9. 预留后续增强项
  - 自动读取 `git diff`
  - 自动从 `.kiro/specs/` 提取事项
  - 结合 automation 周期性运行
  - 生成更智能的“下一步建议”
  - 批量识别成熟模块并触发 `professional-markdown`

## MVP 范围

第一阶段只做以下能力：

1. Skill 触发规则
2. 追踪目录初始化
3. 追加会话日志
4. 更新概览
5. 生成轻量功能说明卡片
6. 正式文档提升工作流

以下能力延后：

1. 自动推断 feature_id
2. 复杂 git 分析
3. 自动化周期调度
4. 历史纠错合并

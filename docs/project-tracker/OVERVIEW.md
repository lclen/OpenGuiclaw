# Project Tracker

## 项目简介
<!-- project-tracker:intro:start -->
**OpenGuiclaw v1.0.0** — 基于 Qwen（通义千问）的智能桌面 AI 伙伴框架。

支持 Web UI（FastAPI + Alpine.js）和 CLI 两种交互方式，核心能力：

- **智能对话**：OpenAI 兼容接口，Function Calling 多轮工具链
- **视觉感知**：后台线程定时截屏 + Vision 模型分析屏幕状态，可主动发起对话
- **记忆系统**：短期会话 + 长期记忆提取 + 向量语义检索（RAG）+ 知识图谱
- **自我进化**：每日回顾对话，自动更新用户画像和 PERSONA.md
- **GUI 自动化**：pyautogui + mss，归一化坐标（0-1000）视觉定位操作
- **计划执行**：多步骤计划，支持自驾/确认/普通三种模式
- **插件系统**：plugins/ 热加载，AI 可自主编写新插件
- **IM 频道**：DingTalk、Feishu、Telegram 适配器
- **3D 虚拟形象**：Three.js + VRM 渲染，多模型切换
<!-- project-tracker:intro:end -->

## 当前活跃事项
<!-- project-tracker:items:start -->
| feature_id | 标题 | 状态 | 最近更新 | 下一步 | 关键文件 | 正式文档 |
| --- | --- | --- | --- | --- | --- | --- |
| core-agent | Agent 主逻辑 | stable | 2026-03-13 | 持续维护 | core/agent.py | docs/modules/agent.md |
| web-server | FastAPI Web 服务 | stable | 2026-03-13 | 补正式模块文档 | core/server.py | - |
| memory-system | 记忆系统 | in_progress | 2026-03-13 | 向量检索优化 | core/memory.py, core/vector_memory.py | docs/modules/memory.md |
| self-evolution | 自我进化引擎 | in_progress | 2026-03-13 | 重构中（见 spec） | core/self_evolution.py | docs/modules/evolution.md |
| visual-context | 视觉感知 | stable | 2026-03-13 | 持续维护 | core/context.py | docs/modules/context.md |
| plugin-system | 插件系统 | stable | 2026-03-13 | 持续维护 | core/plugin_manager.py, plugins/ | docs/modules/plugins.md |
| im-channels | IM 频道接入 | in_progress | 2026-03-13 | 完善各适配器 | core/channels/ | docs/modules/channels.md |
| venv-packaging | venv 打包方案 | in_progress | 2026-03-13 | 见 spec | installer.iss | - |
| project-doc-tracker | 项目文档跟踪 skill | done | 2026-03-13T14:46:05+08:00 | 按需接入 automation | .agents/skills/project-doc-tracker/ | docs/modules/project_doc_tracker.md |
| project-initialization | 项目初始化 | done | 2026-03-13T14:51:30+08:00 | 开始功能开发或测试 | test_init.py | - |
| diary-system | AI 日记系统 | stable | 2026-03-13T15:00:28+08:00 | 持续维护 | core/diary.py, core/diary_index.py | - |
| journal-system | 对话日志系统 | stable | 2026-03-13T15:00:29+08:00 | 持续维护 | core/journal.py, core/journal_index.py | - |
| orchestrator | 多 Agent 编排器 | stable | 2026-03-13T15:00:31+08:00 | 持续维护 | core/orchestrator.py, core/profiles.py, core/tasks.py | - |
| memory-extractor | 记忆提取器 | stable | 2026-03-13T15:00:32+08:00 | 持续维护 | core/memory_extractor.py, core/daily_consolidator.py | - |
| state-management | 全局状态管理 | stable | 2026-03-13T15:00:33+08:00 | 持续维护 | core/state.py, core/presets.py | - |
| user-profile | 用户画像管理 | stable | 2026-03-13T15:00:35+08:00 | 持续维护 | core/user_profile.py | - |
| identity-system | 人设与身份管理 | stable | 2026-03-13T15:00:48+08:00 | 持续维护 | core/identity_manager.py, core/persona_audit.py | - |
| session-system | 会话管理 | stable | 2026-03-13T15:00:49+08:00 | 持续维护 | core/session.py | - |
| skills-system | 技能注册系统 | stable | 2026-03-13T15:00:50+08:00 | 持续维护 | core/skills.py | - |
| mcp-client | MCP 协议客户端 | stable | 2026-03-13T15:00:51+08:00 | 持续维护 | core/mcp_client.py | - |
| scheduler | 定时任务调度器 | stable | 2026-03-13T15:00:52+08:00 | 持续维护 | core/scheduler/ | - |
| knowledge-graph | 知识图谱 | stable | 2026-03-13T15:00:53+08:00 | 持续维护 | core/knowledge_graph.py | - |
| bootstrap | 启动引导 | stable | 2026-03-13T15:00:55+08:00 | 持续维护 | core/bootstrap.py, launcher.py | - |
| self-check | 自检系统 | in_progress | 2026-03-27T22:05:00+08:00 | 继续补齐磁盘残留扫描与多级心跳状态机 | core/self_check.py, core/routes/agents.py, frontend/src/components/DiagnosticsPanel.tsx, core/process_runtime.py | docs/modules/self_check.md |
| codex-style-workspace-ui | Codex 风格 Workspace UI 重构 | done | 2026-03-17T14:53:55+08:00 | 无（本次交付完毕） | tests/test_workspace_manager.py | - |
| config-panel-display-bug | 设置面板模型端点显示 bug | done | 2026-03-17T19:03:37+08:00 | 持续维护 | templates/panels/panel_config.html | - |
| react-frontend-migration | React 前端迁移（逐步替换 Alpine） | in_progress | 2026-03-18T08:13:01+08:00 | 阶段6：按evolution plan推进下一个组件 | frontend/src/components/SettingsOverlay.tsx | - |
<!-- project-tracker:items:end -->

## 最近一次会话
<!-- project-tracker:session:start -->
阶段5完成：SettingsNav已React化，build通过
<!-- project-tracker:session:end -->

## 下一步建议
<!-- project-tracker:next:start -->
- web-server: 补正式模块文档
- memory-system: 向量检索优化
- self-evolution: 继续推进 self-evolution-refactor
- im-channels: 完善各适配器
- venv-packaging: 根据 spec 收束打包方案
- project-doc-tracker: 按需接入 automation
- project-initialization: 开始功能开发或测试
- diary-system: 持续维护
- journal-system: 持续维护
- orchestrator: 持续维护
- memory-extractor: 持续维护
- state-management: 持续维护
- user-profile: 持续维护
- identity-system: 持续维护
- session-system: 持续维护
- skills-system: 持续维护
- mcp-client: 持续维护
- scheduler: 持续维护
- knowledge-graph: 持续维护
- bootstrap: 持续维护
- self-check: 继续补齐磁盘残留扫描与多级心跳状态机
- codex-style-workspace-ui: 无（本次交付完毕）
- config-panel-display-bug: 持续维护
- react-frontend-migration: 阶段6：按evolution plan推进下一个组件
<!-- project-tracker:next:end -->

## 已知阻塞
<!-- project-tracker:blockers:start -->
- 暂无
<!-- project-tracker:blockers:end -->

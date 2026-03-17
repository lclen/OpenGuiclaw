# 需求文档

## 简介

本次改造的目标，是把 OpenGuiclaw 当前“单项目 + 多面板”的前端，收敛成更接近 Codex 的工作台体验：

- 支持多个项目工作区（Workspace）
- 保留一个全局管理入口（Global Home）
- 左侧专注于项目与线程切换
- 主区专注于当前工作区的聊天与执行
- 设置、诊断、归档管理收敛到统一入口

本阶段的技术决策已经明确：

- 后端继续使用 FastAPI
- 模板继续由 Jinja2 提供入口 HTML
- 前端继续使用 HTML / CSS / Alpine.js / 原生 JavaScript
- 本次 **不** 引入 React 作为必需实现
- 允许在未来单独立项，将主壳逐步迁移到 React，但这不属于本次范围

这意味着本次是一次 **渐进式前端重构**，而不是一次全量前端框架迁移。

---

## 术语表

- **Workspace（工作区）**：绑定一个真实项目目录 `workspace_path` 的项目上下文，拥有独立线程、可选 persona 和模型覆盖配置。
- **Global Home（全局管理视图）**：应用级首页，不对应真实项目目录，用于浏览工作区、最近线程、创建工作区和打开设置。
- **Thread（线程）**：归属于某个工作区的一次完整会话。
- **Active Workspace（当前工作区）**：当前前端客户端正在查看的工作区，只是客户端状态，不应成为服务端的全局单例。
- **Frontend Shell（前端主壳）**：指左侧 Sidebar、顶部标题区、主聊天区、欢迎态和 Settings Overlay 组成的整体应用框架。

---

## 需求

### 需求 1：工作区数据模型与持久化

**用户故事：** 作为开发者，我希望每个项目工作区都能独立持久化，以便系统重启后恢复多个项目的状态与线程历史。

#### 验收标准

1. THE WorkspaceManager SHALL 将每个工作区存储于 `data/workspaces/<workspace_id>/workspace.json`。
2. THE `workspace.json` SHALL 包含：`id`、`name`、`workspace_path`、`created_at`、`updated_at`、`persona_file`、`model_overrides`、`archived`。
3. THE WorkspaceManager SHALL 将该工作区的线程存储在 `data/workspaces/<workspace_id>/sessions/` 目录下。
4. WHEN 系统首次启动且不存在任何工作区时，THE WorkspaceManager SHALL 创建一个默认工作区，其 `workspace_path` 指向当前应用根目录。
5. THE WorkspaceManager SHALL 拒绝创建 `workspace_path` 不存在或不是目录的工作区，并返回描述性错误。
6. THE WorkspaceManager SHALL 规范化 `workspace_path`，并阻止重复创建指向同一物理目录的工作区。
7. THE WorkspaceManager SHALL 支持归档工作区，归档后其数据文件仍保留在磁盘中。

### 需求 2：客户端作用域与当前工作区

**用户故事：** 作为用户，我希望切换项目时不会影响其他标签页或其他客户端，以便每个客户端都能稳定工作。

#### 验收标准

1. THE 系统 SHALL 将“当前工作区”视为前端客户端状态，而不是服务端全局单例。
2. THE 后端聊天与线程相关接口 SHALL 通过显式 `workspace_id` 定位数据，不得依赖服务端全局 `active_workspace_id`。
3. THE 前端 SHALL 在客户端状态中保存 `activeWorkspaceId`，并在刷新后恢复最近一次选择。
4. IF 某个客户端切换工作区，THEN 该行为 SHALL NOT 改变其他客户端当前正在查看的工作区。
5. THE 系统 MAY 持久化“最近一次打开的工作区”用于 UI 恢复，但它 SHALL NOT 决定服务端聊天路由的正确性。

### 需求 3：工作区与线程 REST API

**用户故事：** 作为前端，我需要一组显式按工作区寻址的 API，以便稳定管理多个项目与线程生命周期。

#### 验收标准

1. THE WorkspaceRouter SHALL 提供 `GET /api/workspaces`，返回所有非归档工作区列表。
2. THE WorkspaceRouter SHALL 提供 `GET /api/workspaces/archived`，返回已归档工作区列表。
3. THE WorkspaceRouter SHALL 提供 `POST /api/workspaces`，接收 `{"name", "workspace_path"}` 创建工作区。
4. THE WorkspaceRouter SHALL 提供 `GET /api/workspaces/{workspace_id}`，返回工作区详情。
5. THE WorkspaceRouter SHALL 提供 `PATCH /api/workspaces/{workspace_id}`，支持更新 `name`、`workspace_path`、`persona_file`、`model_overrides`。
6. THE WorkspaceRouter SHALL 提供 `DELETE /api/workspaces/{workspace_id}`，执行软删除（`archived=true`）。
7. THE WorkspaceRouter SHALL 提供 `POST /api/workspaces/{workspace_id}/unarchive`，恢复工作区。
8. THE WorkspaceRouter SHALL 提供 `GET /api/workspaces/{workspace_id}/sessions`，支持 `include_archived`，默认最多 50 条并按 `updated_at` 倒序。
9. THE WorkspaceRouter SHALL 提供线程归档、恢复、永久删除接口。
10. THE WorkspaceRouter SHALL 仅允许永久删除已归档线程。
11. THE WorkspaceRouter SHALL 提供 `GET /api/workspaces/{workspace_id}/files`，返回对应 `workspace_path` 的文件树。
12. THE `GET /api/workspaces` 返回项 SHALL 包含 `thread_count`，供前端 Sidebar 直接显示。

### 需求 4：聊天路由与线程隔离

**用户故事：** 作为用户，我希望每个项目工作区的对话历史严格隔离，以便切换项目时上下文不会串。

#### 验收标准

1. WHEN 用户在工作区中发起新对话时，THE 系统 SHALL 将新 Session 存储到该工作区的 `sessions/` 目录。
2. THE 工作区聊天读写逻辑 SHALL 始终通过显式 `workspace_id` + `session_id` 定位线程。
3. THE 工作区流式接口 SHALL 不修改全局 `agent.sessions._current`。
4. THE 工作区流式接口 SHALL 不写入全局 `data/sessions/`。
5. IF 用户切换工作区或线程时存在进行中的流式任务，THEN 前端 SHALL 先中止或等待完成，再切换。
6. THE 系统 SHALL 防止同一 `workspace_id/session_id` 被并发流式写回时产生静默覆盖。
7. WHEN 工作区配置了 `persona_file` 或 `model_overrides`，THEN 这些配置 SHALL 在该工作区聊天上下文中生效。

### 需求 5：Codex 风格的简洁前端主壳

**用户故事：** 作为用户，我希望界面更像 Codex，左侧只关注项目和线程，主区只关注当前任务，而不是堆满管理面板。

#### 验收标准

1. THE Frontend Shell SHALL 采用“固定 Sidebar + 主内容区 + Settings Overlay”的简洁结构。
2. THE Sidebar SHALL 固定为双段式结构：上半部分是 Global Home 与 Workspace List，下半部分是当前工作区的 Thread List。
3. THE Sidebar SHALL 提供“新建工作区”“新建对话”“打开设置”入口。
4. THE Sidebar SHALL 显示工作区名称、截断后的路径和线程数量。
5. THE 主区 SHALL 只承载三类主要视图：`home`、`chat`、`settings-overlay`。
6. THE 主区 SHALL 在没有活跃线程时显示欢迎态，而不是空白区。
7. THE 设置入口 SHALL 收敛为单一 Overlay 或全屏设置页，不再以多个独立侧板暴露。
8. THE 前端 SHALL 保留现有聊天、上传、slash commands、SSE 流式输出等核心能力。

### 需求 6：前端技术路线与渐进迁移

**用户故事：** 作为开发者，我希望这次重构能在不推倒现有前端的前提下完成，而不是引入一次高风险的前端框架迁移。

#### 验收标准

1. THE 本次改造 SHALL 继续基于 Jinja2 模板、HTML、CSS、Alpine.js 和现有 `static/js/app-logic.js` 完成。
2. THE 本次改造 SHALL NOT 以引入 React 作为交付前提。
3. THE 实现方案 SHALL 优先重构 Frontend Shell、Workspace 状态和主聊天工作流，而不是一次性重写全部配置与附属面板。
4. THE 现有复杂面板（如 memory、scheduler、skills、VRM、config）MAY 暂时保留旧结构，只要求入口被收敛。
5. THE 设计文档 SHALL 明确 React 仅作为未来可选演进方向，不在本次任务范围内。

### 需求 7：Global Home 与简洁设置页

**用户故事：** 作为用户，我希望有一个全局管理入口来查看项目概览和统一设置，而不是把所有内容塞到聊天页边上。

#### 验收标准

1. THE 应用 SHALL 提供一个 Global Home 视图，作为默认全局入口。
2. THE Global Home SHALL 展示最近工作区、最近线程、创建工作区入口和打开设置入口。
3. THE Settings Page SHALL 采用统一的 Overlay 或独立视图。
4. THE Settings Page SHALL 至少包含：`General`、`Appearance`、`Models & Persona`、`Integrations`、`Diagnostics`、`Archived`。
5. THE 已归档线程管理 SHALL 位于 Settings 中，并支持恢复与永久删除。
6. IF 用户修改了需要重启的配置，THEN Settings Page SHALL 显示明确的“需要重启”提示。

### 需求 8：数据迁移与向后兼容

**用户故事：** 作为现有用户，我希望升级后旧会话能迁移到新结构，同时尽量不破坏已有功能。

#### 验收标准

1. WHEN 系统检测到旧 `data/sessions/` 存在且尚未完成迁移时，THE WorkspaceManager SHALL 执行一次性迁移。
2. THE 迁移 SHALL 创建默认工作区，并将旧 Session 复制到默认工作区的 `sessions/` 目录。
3. THE 迁移 SHALL 保留原始 `data/sessions/` 不删除。
4. THE 系统 SHALL 使用 `.migrated` 或等效标记防止重复迁移。
5. IF 迁移中发生错误，THEN 系统 SHALL 记录错误并继续启动。
6. THE 迁移判断 SHALL 能识别“部分初始化”或脏状态，避免旧数据被静默忽略。

### 需求 9：测试与正确性

**用户故事：** 作为开发者，我希望工作区系统有清晰测试边界，以便避免 UI 改造后出现串写、回归和迁移遗漏。

#### 验收标准

1. THE WorkspaceManager SHALL 具备单元测试覆盖：创建、更新、归档、恢复、迁移、文件树、线程归档和删除。
2. THE Router 层 SHALL 具备 API 测试覆盖：404、422、归档过滤、线程排序、永久删除限制、`thread_count`。
3. THE 前端关键流程 SHALL 至少具备手工验收步骤：加载工作区、切换工作区、切换线程、打开设置、归档线程。
4. THE 测试策略 SHALL 覆盖“不同客户端切换工作区不串写”和“同一线程不发生并发覆盖”这两个关键场景。

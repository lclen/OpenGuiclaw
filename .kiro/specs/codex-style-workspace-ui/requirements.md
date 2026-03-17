# 需求文档

## 简介

为 openGuiclaw 添加类似 Codex 的工作区（Workspace）功能，并对前端进行大幅重构。核心目标是支持多工作区切换（每个工作区对应独立的 AI 人设、配置和聊天历史），同时将整体 UI 风格重构为 Codex 风格：左侧边栏展示工作区列表与聊天历史，左下角设置按钮打开全屏设置页面。

技术约束：纯 HTML/CSS/Alpine.js，无前端构建步骤，数据以 JSON 文件持久化，后端为 FastAPI + Jinja2。

---

## 词汇表

- **Workspace（工作区）**：一个独立的 Agent 运行时，绑定一个用户指定的文件夹路径（`workspace_path`），AI 在该路径下完成具体工作。工作区的内部数据存储在 `data/workspaces/<workspace_id>/` 目录，但 AI 操作的目标目录是 `workspace_path`。
- **workspace_path**：工作区绑定的用户项目目录，例如 `D:\myproject` 或 `~/projects/myapp`，AI 在此目录下读写文件、执行任务。类似 Codex 的"项目"概念。
- **Thread（线程/对话）**：一次完整的聊天会话，归属于某个工作区。对应现有的 Session 概念，存储为 JSON 文件。
- **Sidebar（左侧边栏）**：始终可见的左侧导航区域，展示工作区列表和当前工作区的聊天历史。
- **Settings（设置页）**：全屏覆盖的设置界面，通过左下角按钮打开，包含多个分类配置项。
- **WorkspaceManager**：后端负责工作区 CRUD 的管理模块。
- **WorkspaceRouter**：后端 FastAPI 路由，提供工作区相关 REST API。
- **Archived_Thread**：已归档的对话线程，不在主列表显示，但可在设置页查看。

---

## 需求

### 需求 1：工作区数据模型与持久化

**用户故事：** 作为开发者，我希望工作区数据能够持久化到磁盘，以便重启后恢复所有工作区和对话历史。

#### 验收标准

1. THE WorkspaceManager SHALL 将每个工作区存储为 `data/workspaces/<workspace_id>/workspace.json`，包含字段：`id`、`name`、`workspace_path`（用户指定的工作目录，如 `D:\myproject`）、`created_at`、`updated_at`、`persona_file`（可选）、`model_config`（可选覆盖）、`archived`（布尔值）。
2. THE WorkspaceManager SHALL 将属于该工作区的聊天线程存储在 `data/workspaces/<workspace_id>/sessions/` 目录下，每个线程为独立 JSON 文件。
3. WHEN 系统首次启动且不存在任何工作区时，THE WorkspaceManager SHALL 自动创建一个名为 "默认工作区" 的初始工作区，其 `workspace_path` 默认指向当前应用根目录。
4. THE WorkspaceManager SHALL 在 `data/workspaces/active.json` 中记录当前激活的工作区 ID，格式为 `{"active_workspace_id": "<id>"}`.
5. IF `data/workspaces/active.json` 不存在或记录的工作区 ID 无效，THEN THE WorkspaceManager SHALL 回退到第一个可用工作区。
6. THE WorkspaceManager SHALL 支持将现有 `data/sessions/` 目录下的历史会话迁移到默认工作区，迁移时保留原始文件内容不变。
7. WHEN 创建工作区时，IF 用户提供的 `workspace_path` 不存在，THEN THE WorkspaceManager SHALL 返回描述性错误，不创建工作区。

---

### 需求 2：工作区 REST API

**用户故事：** 作为前端，我需要通过 REST API 管理工作区，以便实现工作区的增删改查和切换。

#### 验收标准

1. THE WorkspaceRouter SHALL 提供 `GET /api/workspaces`，返回所有非归档工作区列表，每项包含 `id`、`name`、`workspace_path`、`created_at`、`thread_count`。
2. THE WorkspaceRouter SHALL 提供 `POST /api/workspaces`，接受 `{"name": "<name>", "workspace_path": "<path>"}` 创建新工作区，返回新工作区完整对象。
3. THE WorkspaceRouter SHALL 提供 `PATCH /api/workspaces/{workspace_id}`，支持更新工作区 `name`、`workspace_path`、`persona_file`、`model_config` 字段。
4. THE WorkspaceRouter SHALL 提供 `DELETE /api/workspaces/{workspace_id}`，将工作区标记为 `archived: true`（软删除），不物理删除文件。
5. THE WorkspaceRouter SHALL 提供 `POST /api/workspaces/{workspace_id}/activate`，切换当前激活工作区，返回 `{"status": "ok", "active_workspace_id": "<id>"}`.
6. THE WorkspaceRouter SHALL 提供 `GET /api/workspaces/active`，返回当前激活工作区的完整信息（含 `workspace_path`）。
7. THE WorkspaceRouter SHALL 提供 `GET /api/workspaces/{workspace_id}/sessions`，返回该工作区下的聊天线程列表（最多 50 条，按 `updated_at` 倒序）。
8. IF 请求的 `workspace_id` 不存在，THEN THE WorkspaceRouter SHALL 返回 HTTP 404 及描述性错误信息。
9. THE WorkspaceRouter SHALL 提供 `GET /api/workspaces/archived`，返回所有已归档工作区列表。
10. THE WorkspaceRouter SHALL 提供 `POST /api/workspaces/{workspace_id}/unarchive`，将已归档工作区恢复为正常状态。
11. THE WorkspaceRouter SHALL 提供 `GET /api/workspaces/{workspace_id}/files`，返回该工作区 `workspace_path` 下的文件树结构（用于设置页"工作树"展示），最大深度为 3 层。
12. IF 请求 `GET /api/workspaces/{workspace_id}/files` 时 `workspace_path` 目录不可访问，THEN THE WorkspaceRouter SHALL 返回 HTTP 422 及描述性错误信息。

---

### 需求 3：聊天路由与工作区上下文集成

**用户故事：** 作为用户，我希望在不同工作区发起的对话能够隔离存储，以便每个工作区保持独立的对话历史。

#### 验收标准

1. WHEN 用户在某工作区发起聊天时，THE WorkspaceRouter SHALL 将新建的 Session 存储到该工作区的 `sessions/` 目录，而非全局 `data/sessions/`。
2. WHEN 用户切换工作区时，THE WorkspaceManager SHALL 自动加载目标工作区最近一次的 Session 作为当前活跃会话。
3. IF 目标工作区没有任何历史 Session，THEN THE WorkspaceManager SHALL 为该工作区创建一个新的空 Session。
4. THE WorkspaceManager SHALL 确保同一时刻只有一个工作区处于激活状态，切换工作区时先保存当前 Session 再切换。
5. WHEN 工作区被激活时，IF 该工作区配置了 `persona_file`，THEN THE WorkspaceManager SHALL 通知 Agent 加载对应人设文件。

---

### 需求 4：Codex 风格左侧边栏重构

**用户故事：** 作为用户，我希望左侧边栏展示工作区列表和当前工作区的聊天历史，以便快速切换工作区和历史对话。

#### 验收标准

1. THE Sidebar SHALL 在顶部区域展示所有非归档工作区列表，每个工作区显示名称、绑定的 `workspace_path`（超过 24 字符时截断并显示省略号）和线程数量角标。
2. WHEN 用户点击某工作区时，THE Sidebar SHALL 高亮该工作区并在下方展开显示该工作区的聊天线程列表。
3. THE Sidebar SHALL 在工作区列表下方展示当前激活工作区的最近 20 条聊天线程，每条显示标题（取首条用户消息前 30 字）和相对时间。
4. WHEN 用户点击某条聊天线程时，THE Sidebar SHALL 加载该线程的历史消息到聊天区域，并将其设为当前活跃 Session。
5. THE Sidebar SHALL 在顶部提供 "新建工作区" 按钮（`+` 图标），点击后弹出表单，让用户输入工作区名称和 `workspace_path`（文本输入框，支持手动输入绝对路径）。
6. THE Sidebar SHALL 在每个工作区条目上提供右键菜单或悬停操作按钮，支持重命名和归档操作。
7. THE Sidebar SHALL 在底部提供 "新建对话" 按钮，在当前工作区创建新线程。
8. THE Sidebar SHALL 在最底部提供设置按钮（齿轮图标），点击后打开设置页面。
9. WHILE 工作区列表加载中，THE Sidebar SHALL 显示骨架屏占位动画，避免布局跳动。
10. THE Sidebar SHALL 宽度固定为 240px，不可折叠（桌面端），在移动端可通过汉堡菜单展开。

---

### 需求 5：Codex 风格设置页面

**用户故事：** 作为用户，我希望通过统一的设置页面管理所有配置项，以便替代当前分散在各面板中的设置入口。

#### 验收标准

1. THE Settings_Page SHALL 以全屏覆盖层（overlay）形式展示，通过左下角设置按钮触发，按 ESC 或点击关闭按钮退出。
2. THE Settings_Page SHALL 在左侧提供分类导航，包含以下分类：常规、外观（Appearance）、模型配置、个性化、MCP 服务器、IM 通道、环境与诊断、工作树、已归档线程。
3. WHEN 用户点击某分类时，THE Settings_Page SHALL 在右侧区域展示对应的配置内容，无需页面跳转。
4. THE Settings_Page 的 "常规" 分类 SHALL 包含：语言设置、启动行为、自动保存间隔、日记功能开关。
5. THE Settings_Page 的 "外观" 分类 SHALL 包含：主题色选择（当前仅 Noble Black + Stem Green）、VRM 系统开关、VRM 面板显示开关、字体大小调节。
6. THE Settings_Page 的 "模型配置" 分类 SHALL 迁移现有 `panel_config.html` 中的模型端点配置内容（聊天端点列表、角色功能增强模型）。
7. THE Settings_Page 的 "个性化" 分类 SHALL 迁移现有 `panel_persona.html` 中的人设管理内容。
8. THE Settings_Page 的 "MCP 服务器" 分类 SHALL 展示 MCP 服务器配置列表，支持增删改。
9. THE Settings_Page 的 "IM 通道" 分类 SHALL 迁移现有 `panel_im.html` 中的 IM 渠道配置内容。
10. THE Settings_Page 的 "环境与诊断" 分类 SHALL 迁移现有 `panel_config.html` 中的 "环境与诊断" Tab 内容及 `panel_debug.html` 内容。
11. THE Settings_Page 的 "工作树" 分类 SHALL 展示当前激活工作区绑定的 `workspace_path` 下的文件目录结构（通过 `GET /api/workspaces/{workspace_id}/files` 获取），而非 `data/workspaces/` 内部结构。
12. THE Settings_Page 的 "已归档线程" 分类 SHALL 展示所有已归档的聊天线程，支持恢复归档和永久删除。
13. IF 用户在设置页修改了需要重启的配置项，THEN THE Settings_Page SHALL 显示 "需要重启" 提示横幅，并提供重启按钮。

---

### 需求 6：主聊天区域重构

**用户故事：** 作为用户，我希望主聊天区域在没有活跃对话时展示欢迎页，并支持工作区选择，以便快速开始新对话。

#### 验收标准

1. WHEN 当前工作区没有活跃对话时，THE Chat_Area SHALL 展示欢迎页，包含：当前工作区名称、工作区切换下拉菜单、快速开始新对话的输入框。
2. THE Chat_Area SHALL 在顶部工具栏显示当前工作区名称和当前线程标题。
3. WHEN 用户在欢迎页的工作区下拉菜单中选择不同工作区时，THE Chat_Area SHALL 调用工作区切换 API 并刷新侧边栏。
4. THE Chat_Area SHALL 保留现有的消息渲染、流式输出、文件上传、斜杠命令等所有功能。
5. THE Chat_Area SHALL 在顶部工具栏提供 "归档当前线程" 按钮，点击后将当前 Session 标记为已归档并开始新线程。

---

### 需求 7：线程归档功能

**用户故事：** 作为用户，我希望能够归档不再需要的对话线程，以便保持侧边栏整洁，同时不丢失历史数据。

#### 验收标准

1. THE WorkspaceRouter SHALL 提供 `POST /api/workspaces/{workspace_id}/sessions/{session_id}/archive`，将指定线程标记为已归档（在 Session JSON 中添加 `"archived": true` 字段）。
2. THE WorkspaceRouter SHALL 提供 `POST /api/workspaces/{workspace_id}/sessions/{session_id}/unarchive`，恢复已归档线程。
3. WHEN 获取工作区线程列表时，THE WorkspaceRouter SHALL 默认过滤掉已归档线程，除非请求参数包含 `include_archived=true`。
4. THE Sidebar SHALL 不在主列表中显示已归档线程。
5. IF 用户归档了当前活跃线程，THEN THE WorkspaceManager SHALL 自动切换到该工作区最近的非归档线程，若无则创建新线程。

---

### 需求 8：前端状态管理与 Alpine.js 集成

**用户故事：** 作为开发者，我希望新的工作区状态能够无缝集成到现有的 Alpine.js `mainApp()` 中，以便不破坏现有功能。

#### 验收标准

1. THE mainApp SHALL 新增以下状态字段：`workspaces`（工作区列表）、`activeWorkspaceId`（当前激活工作区 ID）、`activeWorkspaceName`（当前工作区名称）、`activeWorkspacePath`（当前工作区绑定的文件夹路径）、`workspaceThreads`（当前工作区线程列表）、`showSettings`（设置页显示状态）、`settingsTab`（当前设置分类）。
2. THE mainApp SHALL 在 `init()` 中调用 `loadWorkspaces()` 和 `loadActiveWorkspace()`，在现有初始化流程之后执行。
3. WHEN `activeWorkspaceId` 变化时，THE mainApp SHALL 自动调用 `loadWorkspaceThreads()` 刷新线程列表。
4. THE mainApp SHALL 提供 `switchWorkspace(id)`、`createWorkspace(name)`、`renameWorkspace(id, name)`、`archiveWorkspace(id)` 等方法。
5. THE mainApp SHALL 提供 `archiveThread(sessionId)`、`loadThread(sessionId)` 方法。
6. THE mainApp SHALL 确保工作区切换操作完成后，`currentSessionId` 同步更新为新工作区的活跃 Session ID。
7. FOR ALL 现有功能（聊天、记忆、技能、Agent 等），THE mainApp SHALL 保持向后兼容，不因工作区重构而破坏。

---

### 需求 9：数据迁移兼容性

**用户故事：** 作为现有用户，我希望升级后历史数据不丢失，以便无缝过渡到新版本。

#### 验收标准

1. WHEN 系统检测到 `data/sessions/` 目录存在且 `data/workspaces/` 目录不存在时，THE WorkspaceManager SHALL 执行一次性迁移：创建默认工作区，并将 `data/sessions/` 下所有非 IM 前缀的 Session 文件复制到默认工作区的 `sessions/` 目录。
2. THE WorkspaceManager SHALL 在迁移完成后创建 `data/workspaces/.migrated` 标记文件，防止重复迁移。
3. THE WorkspaceManager SHALL 在迁移过程中保留原始 `data/sessions/` 目录不删除，仅复制文件。
4. IF 迁移过程中发生错误，THEN THE WorkspaceManager SHALL 记录错误日志并继续启动，不阻塞服务器启动流程。

# Tasks

## 1. Backend foundation

- [x] 1.1 新建 `core/workspace_manager.py`，实现工作区 CRUD、归档、恢复、路径规范化与去重
- [x] 1.2 实现线程枚举、线程归档、线程恢复、线程永久删除
- [x] 1.3 实现文件树读取，包含深度限制、忽略目录和权限错误处理
- [x] 1.4 实现旧 `data/sessions/` 的一次性迁移逻辑

## 2. Workspace API

- [x] 2.1 新建 `core/routes/workspace.py`
- [x] 2.2 实现工作区列表、详情、创建、更新、归档、恢复 API
- [x] 2.3 实现工作区线程列表、归档、恢复、永久删除 API
- [x] 2.4 实现 `GET /api/workspaces/{id}/files`
- [x] 2.5 实现 `GET /api/home`，为 Global Home 提供总览数据

## 3. Chat route integration

- [x] 3.1 改造 `core/routes/chat.py`，使工作区聊天和线程按显式 `workspace_id` 定位
- [x] 3.2 移除对服务端全局 active workspace 的正确性依赖
- [x] 3.3 处理工作区切换时的流式任务中止或收尾

## 4. Frontend shell refactor

- [x] 4.1 以当前 `templates/index.html` 为基础，重构出 Codex 风格的 Frontend Shell
- [x] 4.2 在左侧 Sidebar 中加入 Global Home、Workspace List、Thread List
- [x] 4.3 在主区实现 `home` / `chat` 两态主视图
- [x] 4.4 将设置入口收敛为单一 Settings Overlay 或全屏设置页
- [x] 4.5 保留现有聊天、上传、slash commands、SSE 等核心能力

## 5. Alpine.js state integration

- [x] 5.1 在 `static/js/workspace-logic.js` 中加入工作区状态、Global Home 状态和线程状态
- [x] 5.2 实现加载工作区、切换工作区、加载线程、新建线程
- [x] 5.3 实现归档线程与永久删除归档线程
- [x] 5.4 实现工作区切换 loading、中止和错误提示
- [x] 5.5 将前端主路径从旧 `/api/sessions/*` 迁移到 Workspace API

## 6. Settings consolidation

- [x] 6.1 收敛现有设置入口，统一进入 Settings Overlay
- [x] 6.2 将归档工作区和归档线程管理挂入 Settings
- [x] 6.3 保留旧配置内容，但按 `General / Appearance / Models & Persona / Integrations / Diagnostics / Archived` 重新分组

## 7. Verification

- [x] 7.1 编写 `tests/test_workspace_manager.py`
- [x] 7.2 编写 workspace API 测试
- [x] 7.3 验证迁移兼容性
- [x] 7.4 验证多客户端切换工作区不串写
- [x] 7.5 验证同一线程不会发生并发覆盖

## 8. Deferred work

- [ ] 8.1 评估 `app-logic.js` 在 Frontend Shell 完成后的复杂度是否继续上升
- [ ] 8.2 如果后续状态管理继续膨胀，再单独立项“React 化 Frontend Shell”
- [ ] 8.3 React 迁移必须作为后续独立项目，不纳入本次交付范围

# 技能商店与插件安装修复文档 (2026-03-06)

## 问题描述
在之前的版本中，用户反馈无法正常显示技能扩展库（Marketplace）中的插件，且在网络受限环境下插件安装成功率低。

## 修复总结

### 1. 后端：增强网络Resiliency (`core/server.py`)
*   **API 代理优化**：借鉴 `OpenAkita` 的实现，为 `/api/skills/marketplace` 增加了 **IPv4 强制连接备选方案**。当默认环境下的双栈网络导致连接 `skills.sh` 失败时，会自动切换到 IPv4 模式，极大提升了国内环境下的连通性。
*   **安装镜像站 Fallback**：在 `/api/skills/install` 中实现了三阶段安装策略：
    1.  **直连安装**：尝试通过 `pip` 直接从 GitHub 安装。
    2.  **镜像站下载**：若直连失败，自动通过多个 GitHub 镜像站（如 `gh-proxy.com`）下载项目的 ZIP 压缩包。
    3.  **本地安装**：下载完成后自动解压并进行本地 `pip` 安装。
*   **防御逻辑**：修复了空查询字符串导致 `skills.sh` 返回 400 错误的 Bug。

### 2. 前端：修复渲染崩溃与 Scope 冲突 (`panel_skills.html` & `app-logic.js`)
*   **修复 Duplicate Key 崩溃**：这是导致“列表不显示”的根本原因。之前的 `x-for` 使用 `item.name` 作为 Key，但商店中存在多个作者同名插件（如 `agent-browser`），导致 Alpine.js 内部索引冲突并停止渲染。现已改为使用唯一的 `item.id`（路径格式）。
*   **状态提升 (State Lifting)**：将 `skillTab` 和 `skillUrlInput` 从局部 `x-data` 提升到全局 `mainApp()` 作用域，解决了 Alpine.js 嵌套作用域导致的变量访问异常（Shadowing）。
*   **代码清理**：统一了全局变量命名，并移除了会导致语法错误的重复代码块。

## 验证方法
1. 启动 `python run_gui.py`。
2. 进入“技能管理” -> “技能扩展库”。
3. 观察是否能拉取出 Vercel、Supabase 等社区提供的 20+ 个技能。
4. 尝试安装任意技能，观察控制台输出的安装策略切换逻辑。

## 相关文件
- [server.py](file:///d:/openGuiclaw/core/server.py)
- [app-logic.js](file:///d:/openGuiclaw/static/js/app-logic.js)
- [panel_skills.html](file:///d:/openGuiclaw/templates/panels/panel_skills.html)

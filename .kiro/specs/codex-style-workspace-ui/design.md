# Design Document: codex-style-workspace-ui

## 概述

为 openGuiclaw 添加类 Codex 的多工作区（Workspace）功能，并对前端进行大幅重构。
每个工作区绑定一个用户指定的文件夹路径（`workspace_path`），拥有独立的聊天历史（Sessions）、可选人设和模型配置。
前端重构为三栏布局：240px 固定左侧边栏（工作区列表 + 聊天线程列表）+ 主聊天区 + 可选右侧面板；
左下角齿轮按钮打开全屏设置页，替代现有分散的面板入口。

---

## 1. 架构概览

```mermaid
graph TD
    subgraph Frontend["前端 (Alpine.js / HTML)"]
        UI_Sidebar["左侧边栏\n工作区列表 + 线程列表"]
        UI_Chat["主聊天区\n消息渲染 / 流式输出"]
        UI_Settings["设置页 (全屏 overlay)\n9 个分类"]
    end

    subgraph Backend["后端 (FastAPI)"]
        WS_Router["core/routes/workspace.py\nWorkspaceRouter"]
        WS_Manager["core/workspace_manager.py\nWorkspaceManager"]
        Chat_Router["core/routes/chat.py\n(已有，需适配)"]
        Config_Router["core/routes/config.py\n(已有，不变)"]
        Agent["core/agent.py\n(已有)"]
    end

    subgraph Storage["数据层 (JSON 文件)"]
        WS_Dir["data/workspaces/\n  <id>/workspace.json\n  <id>/sessions/*.json\n  active.json\n  .migrated"]
        Old_Sessions["data/sessions/\n(旧数据，迁移后保留)"]
    end

    UI_Sidebar -->|REST| WS_Router
    UI_Chat -->|REST / SSE| Chat_Router
    UI_Settings -->|REST| Config_Router
    WS_Router --> WS_Manager
    WS_Manager --> Storage
    Chat_Router --> Agent
    WS_Manager --> Agent
```

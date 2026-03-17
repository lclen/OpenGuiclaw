# Feature Note: web-server

- feature_id: web-server
- title: FastAPI Web 服务
- updated_at: 2026-03-13T13:16:22+08:00
- status: stable

## 背景

基于 FastAPI + Uvicorn 的 Web 服务层，提供 REST API 和 SSE 流式响应。前端使用 Alpine.js + Jinja2 模板，无构建步骤。内置 3D VRM 虚拟形象渲染（Three.js）。

## 当前实现摘要

core/server.py 注册所有路由；core/routes/ 下按功能拆分：chat（对话+SSE）、memory（记忆管理）、skills（技能列表）、agents（多 agent）、config（配置）、vrm（3D 模型）、im（IM 频道）。templates/index.html 为主页面，panels/ 下为各功能面板。

## 关键文件

- core/server.py
- core/routes/
- templates/

## 风险与已知问题

暂无

## 后续建议

持续维护，按需新增面板

## 正式文档

-

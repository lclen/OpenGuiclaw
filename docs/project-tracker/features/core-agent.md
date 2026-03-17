# Feature Note: core-agent

- feature_id: core-agent
- title: Agent 主逻辑
- updated_at: 2026-03-13T13:15:05+08:00
- status: stable

## 背景

OpenGuiclaw 的核心对话引擎，负责 LLM 调用、工具分发和多轮对话循环。基于 OpenAI 兼容接口，支持 Function Calling 工具链。

## 当前实现摘要

core/agent.py 实现 Agent 类，管理会话历史、调用 LLM、分发工具调用结果。支持流式响应（SSE）。通过 skills_manager 动态加载工具列表。

## 关键文件

- core/agent.py
- core/skills.py
- core/session.py

## 风险与已知问题

暂无

## 后续建议

持续维护，按需扩展工具调用能力

## 正式文档

docs/modules/agent.md

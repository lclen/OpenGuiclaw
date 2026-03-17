# Feature Note: plugin-system

- feature_id: plugin-system
- title: 插件系统
- updated_at: 2026-03-13T13:16:08+08:00
- status: stable

## 背景

plugins/ 目录热加载机制，每个插件实现 register(skills_manager) 函数。支持运行时热更新，无需重启。AI 可通过 skill_creator.py 自主编写新插件。

## 当前实现摘要

core/plugin_manager.py 负责扫描、加载、热更新插件。当前插件：autogui（GUI 自动化）、browser（浏览器操作）、plan_handler（多步骤计划）、sandbox_repl（Python 沙箱）、mcp_gateway（MCP 协议）、skill_creator（AI 自主创建插件）、scheduled（定时提醒）、web_search/web_reader（网页）、system（Shell 命令）等。

## 关键文件

- core/plugin_manager.py
- plugins/

## 风险与已知问题

暂无

## 后续建议

持续维护，按需新增插件

## 正式文档

docs/modules/plugins.md

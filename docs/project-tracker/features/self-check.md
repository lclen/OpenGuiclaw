# Feature Note: self-check

- feature_id: self-check
- title: 系统自检与运行时诊断
- updated_at: 2026-03-27T21:42:00+08:00
- status: in_progress

## 背景

项目同时存在两套“自检”语义：

- `core/self_check.py`：面向每日任务、日志分析与自动修复
- 设置页 Diagnostics：面向用户当前手动触发的运行时诊断

近期工作重点放在后者，目标是参考 OpenAkita 的 `StatusView` 体验，补齐“即时、只读、可解释”的运行时自检。

## 当前实现摘要

已具备环境诊断、LLM 端点只读测活、IM 通道状态查看，以及基于 React 的 DiagnosticsPanel。本轮进一步补齐进程运行记录、残留/冲突检测和人工触发的安全清理入口。

## 关键文件

- core/routes/agents.py
- core/server.py
- frontend/src/components/DiagnosticsPanel.tsx
- static/css/react-panels.css
- docs/openakita_runtime_self_check_followup_20260327.md

## 风险与已知问题

- 与 OpenAkita 相比，仍缺每日自动自检、自动修复与报告推送
- 服务可用性判断虽已加入 PID/残留扫描，但仍未扩展到磁盘残留与更复杂的多级心跳状态机

## 后续建议

- 继续沿 `docs/openakita_runtime_self_check_followup_20260327.md` 收尾剩余“自动化与深层环境检查”差距

## 正式文档

- docs/modules/self_check.md

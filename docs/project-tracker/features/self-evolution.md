# Feature Note: self-evolution

- feature_id: self-evolution
- title: 自我进化引擎
- updated_at: 2026-03-13T13:15:44+08:00
- status: in_progress

## 背景

每日自动回顾对话日志，提炼新记忆，自动更新用户画像（user_profile.py）和 PERSONA.md 人设。支持 persona_audit 审计人设变更。

## 当前实现摘要

self_evolution.py 实现每日进化逻辑；persona_audit.py 审计人设变更；identity_manager.py 管理人设文件切换；user_profile.py 维护用户画像。有独立 spec：.kiro/specs/self-evolution-refactor/

## 关键文件

- core/self_evolution.py
- core/persona_audit.py
- core/identity_manager.py
- core/user_profile.py

## 风险与已知问题

进化逻辑复杂，正在重构中

## 后续建议

推进 self-evolution-refactor spec 重构

## 正式文档

docs/modules/evolution.md

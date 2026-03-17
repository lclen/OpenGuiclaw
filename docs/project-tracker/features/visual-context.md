# Feature Note: visual-context

- feature_id: visual-context
- title: 视觉感知模块
- updated_at: 2026-03-13T13:16:39+08:00
- status: stable

## 背景

后台线程定时截屏，通过 Vision 模型（qwen3-vl-flash）分析屏幕状态，可主动发起对话。支持三种模式：静默/正常/活泼。

## 当前实现摘要

core/context.py 实现 ContextManager，独立后台线程每隔 N 分钟截屏并调用 Vision 模型分析。分析结果（Working/Entertainment/Error/Idle）决定是否主动打扰用户。截图仅内存处理，不落盘。

## 关键文件

- core/context.py

## 风险与已知问题

暂无

## 后续建议

持续维护

## 正式文档

docs/modules/context.md

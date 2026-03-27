# OpenAkita 风格自动化 `system selfcheck` 升级与去重方案

## 目标

把 `system:daily_selfcheck` 从“日志巡检”升级成：

- 每日自动巡检
- 运行时主动探测
- 低风险自动修复
- 会话完整报告 + IM 摘要推送

同时明确与 diagnostics 的职责边界，避免重复建设。

## 职责拆分

### Diagnostics

- 人工触发
- 即时排障
- 分项手动操作
- 允许用户手动处理冲突进程、逐个测活端点

### Automated Selfcheck

- 定时巡检
- 批量汇总
- 低风险自动修复
- 自动投递报告

## 共享底层能力

统一由 `core/runtime_diagnostics.py` 提供：

- 环境快照
- 服务运行态
- 进程残留扫描
- LLM endpoint 只读测活
- 网络矩阵探测
- IM 通道运行态读取

`/api/diagnostics` 与 `system:daily_selfcheck` 共同复用上述 helper，保证判断口径一致。

## 本轮已实现

### 自动化自检流水线

- 目录完整性检查与缺失目录重建
- stale run record 自动清理
- 服务 / PID / 运行时长 / 重启模式探测
- 进程冲突与 orphan / stale residue 识别
- LLM endpoints 批量只读测活
- 主端点网络矩阵：
  - `default`
  - `no_proxy`
  - `ipv4`
  - `no_proxy + ipv4`
- IM 通道运行态汇总
- 日志错误扫描
- 复用 `SelfChecker` 的能力层轻修复

### 报告投递

- 生成 Markdown 完整报告
- 生成 JSON 结构化结果
- 保存到 `data/selfcheck/latest.json` 与 `data/selfcheck/latest.md`
- 非 IM 目标接收完整报告
- IM 目标只接收摘要
- 仅有 IM 目标时，完整报告额外投递到 workspace inbox

## 风险边界

### 自动允许

- 重建缺失目录
- 清理 stale run record
- 执行 `SelfChecker` 已允许的低风险能力层修复

### 保持人工处理

- 清理仍存活的冲突进程
- 清理当前活跃 PID
- 自动重启服务
- 自动改模型配置、路由或 API Key

## 后续可继续做

- selfcheck 历史报告只读查询 API / UI
- 报告趋势聚合
- 调度器失败任务细项纳入报告
- IM 摘要模板按平台差异优化

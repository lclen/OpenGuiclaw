# OpenAkita 风格运行时自检补强计划（2026-03-27）

## 背景

当前 `openGuiclaw` 已经具备第一阶段运行时自检能力：

- `GET /api/diagnostics`：环境、代理、依赖、网络快照
- `POST /api/health/check`：LLM 端点只读测活
- `GET /api/im/channels`：IM 通道运行状态
- `DiagnosticsPanel`：服务状态、端点检查、IM 通道概览

这已经足够回答“现在哪里坏了、点一下能不能测出来”，但和 `OpenAkita` 的成熟体验相比，仍缺三类能力：更结构化的错误语义、更可操作的修复提示、更完整的服务运行态展示。

## 当前差距

### 1. 错误分类还不够结构化

现在端点测活主要返回 `status + error` 文本，用户能看到失败，但不容易快速区分：

- 鉴权失败
- 模型名不存在
- Base URL / 网络不可达
- 请求超时
- 配置缺失

### 2. 前端缺少“下一步怎么修”的直接提示

当前 UI 能展示错误摘要并支持复制，但还没有把“建议检查什么”直接放进卡片，用户仍需要自己推断。

### 3. 服务运行态仍偏轻量

`/api/health` 目前只返回 `{"status":"ok"}`，相比 OpenAkita 的心跳/进程态视图，还缺少：

- 进程 PID
- 版本
- 启动时间 / 运行时长
- 当前重启模式

## 本轮实施计划

### Phase 1 — 结构化后端诊断结果

- [x] 为 `POST /api/health/check` 增加结构化字段：
  - `status: healthy | unhealthy | unknown`
  - `error_code`
  - `hint`
  - `configured`
- [x] 将“配置缺失”从普通失败中拆出，归为 `unknown`
- [x] 保持接口只读，不修改 provider 健康状态、冷却计数、默认路由或会话状态

### Phase 2 — 补齐服务运行态

- [x] 扩展 `GET /api/health`
  - 返回 `pid`
  - 返回 `version`
  - 返回 `started_at`
  - 返回 `uptime_seconds`
  - 返回 `restart_mode`
- [x] 让诊断页服务状态卡直接消费这些字段

### Phase 3 — 前端可操作反馈

- [x] 在 `DiagnosticsPanel` 中展示端点健康摘要统计
- [x] 在端点卡片中展示 `hint`
- [x] 明确区分 `配置缺失 / 未检测 / 异常 / 正常`
- [x] 为 IM 区块补齐更清晰的状态摘要
- [x] 补最小前端行为测试，覆盖显式触发与结果合并

## 本轮不做

- 每日自动自检
- 自动修复 / 自动回归
- 自检报告定时推送
- 后台自治调度

## 完成标准

- 用户进入 diagnostics 页后，不自动发起 LLM 批量探测
- 用户点击后能看到更明确的失败类别和下一步提示
- 服务卡能看到基础运行态，而不只是在线/离线
- 后端与前端都有回归测试覆盖关键路径

## 本轮结果

本轮已完成：

- 后端只读端点测活返回结构化错误分类与修复提示
- `/api/health` 返回进程、版本、启动时间、运行时长与重启模式
- 诊断页新增端点/IM 摘要统计与更明确的状态文案
- 新增后端 pytest 与前端 vitest 覆盖关键路径

当前仍未引入：

- 每日自动自检
- 自动修复闭环
- 定时报告与推送

## 进程残留补强（新增）

已进一步补齐 OpenAkita 风格的进程残留诊断：

- 启动时写入 `data/run/openguiclaw-server-<pid>.json`
- shutdown 时清理当前进程运行记录
- `GET /api/diagnostics` 增加 `process_runtime`
- `POST /api/diagnostics/process/cleanup` 支持人工触发的安全清理
- DiagnosticsPanel 新增进程残留与冲突区块，可查看冲突并执行 `Cleanup`

本阶段仍未补齐的 OpenAkita 差距：

- 更深层的磁盘占用/缓存残留扫描
- 更强的前端心跳状态机（suspect/dead 多级状态）
- 自动报告与自动修复

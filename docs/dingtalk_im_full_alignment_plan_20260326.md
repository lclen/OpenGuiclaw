# 钉钉 IM 通道全链路优化实施方案（2026-03-26）

> **状态**: 待实施  
> **范围**: `Guiclaw` 钉钉通道对齐 `OpenAkita` 的配置体验、消息接收稳定性、消息发送体验、会话运营信息  
> **交付目标**: 形成一份可直接执行的改造方案，作为后续工程实现依据

---

## 目录

- [背景与目标](#背景与目标)
- [现状差异](#现状差异)
- [最终目标体验](#最终目标体验)
- [后端改造](#后端改造)
- [前端改造](#前端改造)
- [API 与类型变更](#api-与类型变更)
- [测试与验收](#测试与验收)
- [实施顺序与风险](#实施顺序与风险)

---

## 背景与目标

当前 `Guiclaw` 已完成 IM 多实例基础设施：`im_bots` 主存储、bot-aware 会话 ID、Bot 注册表、向导式创建入口，以及钉钉 `Stream` 模式的基础适配。

但与 `OpenAkita` 相比，钉钉通道仍有四类明显差距：

1. **配置体验不完整**：钉钉缺少 `extra` 步骤与专属运行开关，向导步骤比 `OpenAkita` 少。
2. **消息接收稳态不足**：当前仍是“处理后 ACK”，缺少去重、状态机、watchdog 与可观测运行指标。
3. **消息发送体验偏弱**：尚未接入钉钉 AI Card / StandardCard 流式卡片路径，`send_typing` 仍是空能力。
4. **会话运营信息不足**：缺少 alias、bot 级启停/响应模式、群策略、通道运行态摘要等运营能力。

本方案目标是：

- 让钉钉通道在 **配置页、运行时收发、会话运营** 上尽量对齐 `OpenAkita`
- 仅对 **钉钉** 做真实增强
- 同时把新增能力抽象成 **通用 IM 可选能力**，避免后续飞书 / Telegram 二次推翻设计
- 保持现有总原则：**保存后提示重启，不做热应用**

---

## 现状差异

### 关键代码参考

| 维度 | Guiclaw | OpenAkita |
|---|---|---|
| 钉钉适配器 | `core/channels/adapters/dingtalk.py` | `D:\openakita\src\openakita\channels\adapters\dingtalk.py` |
| IM 设置页 | `frontend/src/components/IntegrationsPanel.tsx` | `D:\openakita\apps\setup-center\src\views\IMView.tsx` |
| IM 路由 | `core/routes/im.py` | `D:\openakita\src\openakita\api\routes\im.py` |

### 差异总览

| 维度 | Guiclaw 当前 | OpenAkita 当前 | 本次目标 |
|---|---|---|---|
| 向导步骤 | `platform → basic → credentials → test → done` | `platform → agent → mode → idname → credentials → extra → done` | 对齐到后者 |
| 钉钉 extra 配置 | 无 | `footer_elapsed`、`footer_status` | 补齐 |
| 接收 ACK 时机 | 处理完成后 ACK | ACK 先返回，异步处理 | 对齐 |
| 去重 / 状态机 / watchdog | 无 | 有 | 补齐 |
| `send_typing` / 流式卡片 | 无 | 有 AI Card / StandardCard | 补齐 |
| `/api/im/sessions` 字段 | 仅 bot-aware 基础字段 | 含 alias、botEnabled、responseMode 等 | 补齐 |
| 运营接口 | 无 alias / group-policy / bot-config | 已具备 | 补齐 |

### 具体差异说明

#### 1. 配置体验

- `Guiclaw` 已经有平台画廊、Bot 注册表、创建向导和高级模式，但钉钉仅支持：
  - `client_id`
  - `client_secret`
  - `agent_id`
- `OpenAkita` 的钉钉配置在 `extra` 步骤还额外支持：
  - `footer_elapsed`
  - `footer_status`

#### 2. 接收链路

- `Guiclaw` 目前的钉钉 `process()` 里是 `await self.adapter._handle_stream_message(callback)` 后再 `return STATUS_OK`
- `OpenAkita` 改成了 `create_task(self._safe_handle(callback))` 后立即 `ACK`

这意味着：

- 当前 `Guiclaw` 更容易在长处理时触发钉钉平台重投
- 遇到重连、重复投递、抖动时，缺少 dedupe 与 watchdog 防线

#### 3. 发送链路

- 当前 `Guiclaw` 钉钉发送仍以：
  - webhook text / markdown
  - OpenAPI 文本 / 媒体
  - media upload 后 markdown 嵌入
  为主
- 当前 `ChannelAdapter.send_typing()` 默认是 no-op，钉钉没有覆写
- `OpenAkita` 钉钉支持：
  - `send_typing`
  - `stream_token`
  - `stream_thinking`
  - `stream_chain_text`
  - `finalize_stream`
  - AI Card 优先，StandardCard 降级

#### 4. 会话与运营信息

- `Guiclaw` 已实现 bot-aware 的：
  - `platform`
  - `bot_id`
  - `channel_name`
- 但仍缺：
  - `display_name`
  - `chat_type`
  - `chat_name`
  - `alias`
  - `bot_enabled`
  - `response_mode`
  - `stream_state`
  - `last_error`
- 也未提供：
  - `bot-config`
  - `chat-aliases`
  - `group-policy`

---

## 最终目标体验

### 配置体验目标

- 钉钉创建/编辑统一走多步向导：
  - `platform`
  - `agent/profile`
  - `mode`
  - `id/name`
  - `credentials`
  - `extra`
  - `done`
- 钉钉 `extra` 步骤支持：
  - **显示处理耗时**：`footer_elapsed`
  - **显示处理状态**：`footer_status`
- Bot 注册表卡片能直接展示：
  - Bot 名称 / ID
  - 启用状态
  - 最近测活结果
  - 待重启生效提示
  - 钉钉 extra 配置摘要

### 收发体验目标

- 收到钉钉消息后：
  - 先 ACK
  - 再异步进入主循环处理
  - 具备 dedupe 和 watchdog
- 长回复时：
  - 先出现“思考中”卡片
  - 再逐步更新思考 / 工具链 / 回复正文
  - 最终只保留一张完成态卡片
- AI Card 不可用时：
  - 自动降级 StandardCard
  - 再不行才退回普通文本发送

### 会话运营目标

- 管理页能看到：
  - 该会话属于哪个 `bot_id`
  - 单聊 / 群聊
  - 会话展示名 / alias
  - 当前 bot 是否对该会话启用
  - 当前响应模式
  - 通道运行状态与错误信息
- 钉钉与其它平台共用一套 bot-aware 运营接口，不再保留“单平台单实例”的假设。

---

## 后端改造

### 1. 钉钉适配器改造

#### 1.1 ACK-first 接收

- 将钉钉 SDK 的 `process()` 改为：
  - 立即 `ACK`
  - 使用后台任务处理真正的消息逻辑
- 处理函数必须包裹异常，避免后台任务未捕获异常造成静默掉消息

#### 1.2 稳态与可观测性

- 为钉钉适配器补充以下内部状态：

| 字段 | 用途 |
|---|---|
| `stream_state` | 记录 `idle / connecting / connected / running / reconnecting / stopped` |
| `messages_received` | 记录消息总数 |
| `last_message_at` | 记录最近一次收到消息时间 |
| `last_reconnect_at` | 记录最近一次重连时间 |
| `reconnect_count` | 记录累计重连次数 |
| `dedupe_hit_count` | 记录去重命中次数 |
| `last_error` | 记录最近一次流处理错误摘要 |

- 引入消息去重缓存：
  - key 以 `bot_id + msgId` 组合
  - 做 TTL 清理
  - 上限大小可控，防止内存无限增长
- 引入 watchdog：
  - 检查长时间无消息 / 线程异常 / 连接卡死
  - 触发受控重建流连接

#### 1.3 流式卡片能力

- 给钉钉适配器新增以下能力：
  - `send_typing(chat_id, thread_id=None)`
  - `stream_token(chat_id, token, ...)`
  - `stream_thinking(chat_id, thinking_text, ...)`
  - `stream_chain_text(chat_id, text, ...)`
  - `finalize_stream(chat_id, final_text, ...)`
- 实现策略：
  - 优先 AI Card
  - 失败自动回退 StandardCard
  - 再失败回退普通消息发送
- 针对钉钉卡片新增：
  - thinking card 状态缓存
  - 流式缓冲区
  - patch 节流
  - 最终完成态收尾逻辑

#### 1.4 统一发送路由

- 保留现有：
  - webhook 文本/markdown
  - OpenAPI 单聊 / 群聊
  - 图片 / 文件 / 语音媒体上传
- 但新增统一顺序：
  1. 若命中流式路径，优先卡片
  2. 若普通文本，优先 webhook
  3. 若 webhook 不可用，则回退 OpenAPI
  4. 若媒体能力不足，则回退文本提示

#### 1.5 footer 配置读取

- 从 `im_bots[].credentials` 读取：
  - `footer_elapsed`
  - `footer_status`
- 默认策略：
  - 缺失时按 `true`
  - 兼容布尔值和字符串 `"true" / "false"`

### 2. 通用 IM 抽象改造

#### 2.1 `ChannelAdapter` 可选流式能力

- 在基类中保留默认 no-op / false 返回，约定以下为可选能力：
  - `send_typing`
  - `stream_token`
  - `stream_thinking`
  - `stream_chain_text`
  - `finalize_stream`
- 其它平台不要求实现；网关按能力探测调用。

#### 2.2 `ChannelGateway` 处理阶段拆分

- 将 IM 处理流程拆成：
  1. `typing`
  2. `thinking`
  3. `tool chain`
  4. `final reply`
- 网关侧检测当前 adapter 是否支持流式卡片能力：
  - 支持时走钉钉卡片流
  - 不支持时维持现有一次性文本发送

### 3. 运营能力与会话元数据

#### 3.1 会话信息扩展

- 在 `/api/im/channels` 返回中增加：
  - `platform`
  - `bot_id`
  - `display_name`
  - `stream_state`
  - `last_error`
  - `session_count`
  - `last_active`
- 在 `/api/im/sessions` 返回中增加：
  - `chat_type`
  - `chat_name`
  - `display_name`
  - `alias`
  - `bot_enabled`
  - `response_mode`

#### 3.2 通用运营接口

- 新增 / 补齐：
  - `GET/POST/DELETE /api/im/bot-config`
  - `GET/POST/DELETE /api/im/chat-aliases`
  - `GET/POST /api/im/group-policy`
- 所有运营接口都以 bot-aware 标识工作：
  - 优先 `channel_name`
  - 或 `platform + bot_id`
- 禁止退回旧的“只有平台名”的唯一键假设。

---

## 前端改造

### 1. 钉钉向导步骤升级

- 将现有步骤：
  - `platform`
  - `basic`
  - `credentials`
  - `test`
  - `done`
- 升级为平台能力驱动的步骤系统：
  - `platform`
  - `agent/profile`
  - `mode`
  - `id/name`
  - `credentials`
  - `extra`
  - `test`
  - `done`

> [!IMPORTANT]
> 步骤必须由“平台能力表”驱动，而不是把钉钉逻辑硬编码在 JSX 条件分支里。钉钉先使用，飞书/Telegram 后续可直接复用。

### 2. 钉钉专属 extra 配置

- 在钉钉 `extra` 步骤新增两个开关：
  - `footer_elapsed`
  - `footer_status`
- 在编辑已有 bot 时：
  - 若旧配置中缺失这两个字段
  - 前端默认展示为 `开启`
  - 保存时写回到 `credentials`

### 3. 注册表展示增强

- 钉钉 Bot 卡片新增：
  - Stream 模式说明
  - 卡片流式支持说明
  - 群/单聊发送策略摘要
  - `footer_elapsed/footer_status` 状态
  - “保存后重启生效”持久提示

### 4. 运营视图预留

- IM 会话列表为后续运营功能预留展示位：
  - alias
  - 响应模式
  - bot 是否启用
  - 群策略状态
- 本轮前端不要求做完复杂运营面板，但字段与结构必须能承接后端返回。

---

## API 与类型变更

### 配置模型

```ts
type IMBotConfig = {
  id: string;
  name: string;
  platform: "dingtalk" | "telegram" | "feishu";
  enabled: boolean;
  credentials: Record<string, string | boolean>;
  last_health?: {
    status: string;
    error?: string | null;
    checked_at?: string | null;
  } | null;
};
```

钉钉 `credentials` 新增：

```ts
footer_elapsed?: boolean | "true" | "false";
footer_status?: boolean | "true" | "false";
```

### 接口变更

| 接口 | 变更 |
|---|---|
| `GET /api/im/channels` | 增加 `platform`、`bot_id`、`display_name`、`stream_state`、`last_error`、`session_count`、`last_active` |
| `GET /api/im/sessions` | 增加 `chat_type`、`chat_name`、`display_name`、`alias`、`bot_enabled`、`response_mode`，支持 `channel_name` 过滤 |
| `GET/POST/DELETE /api/im/bot-config` | 新增 bot-aware 会话启停 / 响应模式规则 |
| `GET/POST/DELETE /api/im/chat-aliases` | 新增会话别名管理 |
| `GET/POST /api/im/group-policy` | 新增群响应策略管理 |

### 兼容策略

- `im_bots` 继续是主存储
- `channels` 继续仅作为迁移来源和兼容镜像
- `channels.dingtalk` 不承载 `footer_elapsed/footer_status`
- 旧钉钉配置迁移到 `im_bots` 时默认：
  - `footer_elapsed = true`
  - `footer_status = true`

---

## 测试与验收

### 后端单测

- 旧 `channels.dingtalk` 迁移后默认带：
  - `footer_elapsed=true`
  - `footer_status=true`
- 钉钉适配器：
  - ACK-first
  - 消息去重
  - 状态机迁移
  - watchdog 恢复
  - AI Card → StandardCard 降级
- gateway：
  - 命中钉钉流式能力时走卡片流
  - 非流式平台保持原行为
- 路由：
  - `/api/im/channels`
  - `/api/im/sessions`
  - `/api/im/bot-config`
  - `/api/im/chat-aliases`
  - `/api/im/group-policy`
  均支持 bot-aware 查询与过滤

### 前端验证

- 钉钉创建向导出现 `extra` 步骤
- `footer_elapsed/footer_status` 可编辑、可回显、可保存
- 旧钉钉 bot 编辑时自动补默认值
- 注册表卡片可展示钉钉运行特性摘要

### 集成验收场景

1. 创建两个钉钉 bot，保存后提示重启，重启后两个 bot 都能注册成功。
2. 两个 bot 分别收到消息，session 不串线，`bot_id` / `channel_name` 正确。
3. 单聊和群聊各发一条消息，`chat_type` / `chat_name` 区分正确。
4. 触发长回复时，先出现 thinking card，再逐步更新，最终只保留完成态。
5. AI Card 创建失败时自动降级 StandardCard；StandardCard 再失败时回退文本发送。

---

## 实施顺序与风险

### 推荐实施顺序

1. **先补配置模型与前端 extra 字段**
2. **再补适配器 ACK-first、去重、状态机、watchdog**
3. **随后接入钉钉流式卡片能力**
4. **最后补通用 IM 运营接口与会话返回字段**

### 主要风险

| 风险 | 说明 | 处理方式 |
|---|---|---|
| 钉钉 AI Card 权限不稳定 | 不同企业 / 应用权限差异大 | 必须设计 StandardCard 和文本降级链路 |
| Stream 线程退出不彻底 | 可能造成重复连接与重复收消息 | 引入状态机 + watchdog + stop 时强制阻断重连 |
| bot-aware 运营接口与旧逻辑冲突 | 旧逻辑仍有单平台假设 | 统一改为 `channel_name` 或 `platform + bot_id` 主键 |
| 前端步骤硬编码导致后续平台重复开发 | 钉钉先做完后其它平台难复用 | 用平台能力表驱动步骤与字段 |

> [!IMPORTANT]
> 本轮只要求 **钉钉真实增强**。通用 IM 抽象的目标是“为以后复用留出稳定接口”，不是本轮顺手把飞书 / Telegram 一并重做。

---

## 实施默认约定

- 所有新增钉钉 extra 配置均 **保存后重启生效**
- 不做热重载
- 所有新接口与会话元数据都必须是 **bot-aware**
- 文档本身即为本轮开发的实施依据，不再另写一份平行说明


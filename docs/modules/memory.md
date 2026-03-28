# 记忆系统（Memory）

## 概述

记忆系统负责长期存储、提取和检索会在未来持续有用的信息。  
当前版本已经从“单池长期记忆”升级为 **按用途驱动的三层记忆**：

- **上下文层（context）**：给当前对话提供相关背景
- **偏好层（preference）**：塑造代理的行为、语言风格、工具偏好与规则约束
- **经验层（experience）**：沉淀可复用的任务经验、成功模式与避坑教训

**主要文件**：`core/memory.py`、`core/memory_extractor.py`、`core/vector_memory.py`

---

## 两种“三层”要区分

仓库里曾经有过“技术三层”的表述，它指的是：

- 会话历史
- 长期记忆
- 向量检索

这次重构新增的是 **用途三层**，它不是存储结构分层，而是“这些记忆拿来做什么”的分层。

---

## 用途三层

| 用途层 | 作用 | 典型内容 |
| --- | --- | --- |
| context | 对话时按需召回背景 | 用户环境、身份、长期背景事实 |
| preference | 影响代理行为与输出风格 | 用户偏好、沟通要求、持久规则 |
| experience | 提供复用经验与避坑提示 | 成功模式、失败教训、最佳实践 |

### 与现有 `type` 的关系

系统保留原有 `type` 字段，用来描述“内容类别”；新增 `usage_layer` 字段，用来描述“使用目的”。

默认映射如下：

| type | usage_layer |
| --- | --- |
| `fact` | `context` |
| `preference` | `preference` |
| `rule` | `preference` |
| `skill` | `experience` |
| `error` | `experience` |
| `experience` | `experience` |
| `general` / `profile`（兼容旧数据） | `context` |

---

## 数据结构

`data/memory/scene_memory.jsonl` 中的单条记录示例：

```json
{
  "id": "mem_abc123",
  "content": "用户偏好先给结论，再补充实现细节",
  "type": "rule",
  "usage_layer": "preference",
  "tags": ["reply", "style"],
  "source": "auto_extracted",
  "timestamp": 1774740000.0,
  "created_at": "2026-03-29 14:00:00"
}
```

`MemoryItem` 关键字段：

```python
class MemoryItem:
    id: str
    content: str
    type: str
    usage_layer: str
    tags: List[str]
    source: str
    timestamp: float
    created_at: str
```

---

## 运行机制

### 1. 启动迁移

`MemoryManager` 启动时会检查旧 JSONL：

- 如果发现缺少 `usage_layer`
- 先创建一次备份
- 再按 `type` 自动补齐 `usage_layer`
- 原位重写 `scene_memory.jsonl`

### 2. 记忆写入

新增记忆时：

- 默认优先按显式 `usage_layer`
- 若未提供，则按 `type` 自动推断
- 去重只在 **同一用途层** 内进行

这意味着同一内容如果分别承担“背景”和“行为约束”两种用途，可以并存。

### 3. 检索与提示注入

系统提示不再只注入一个泛化的“相关记忆”块，而是按层注入：

1. 偏好层
2. 上下文层
3. 经验层

这样做的原因是：

- 先让代理知道“应该怎么做”
- 再补“用户相关背景”
- 最后补“类似任务的经验和避坑”

---

## 核心接口

### Python 接口

```python
memory.add(
    content="用户喜欢中文界面",
    type="preference",
    usage_layer="preference",
    tags=["ui", "lang"],
    source="manual",
)

memory.search("中文界面", top_k=5, usage_layer="preference")
memory.list_by_usage_layer("experience")
memory.build_prompt_sections("如何优化首页输入框")
```

### REST API

```text
GET    /api/memory
POST   /api/memory
PUT    /api/memory/{id}
DELETE /api/memory/{id}
POST   /api/memory/batch_delete
```

#### `GET /api/memory`

支持：

- `type`
- `usage_layer`
- `q`

示例：

```bash
curl "http://localhost:8080/api/memory?usage_layer=preference"
```

#### `POST /api/memory`

```json
{
  "content": "用户希望首页文案全部中文",
  "type": "rule",
  "usage_layer": "preference",
  "tags": ["frontend", "copy"]
}
```

---

## MemoryExtractor

`MemoryExtractor` 现在在提示词里明确三层用途：

- `extract_from_turn()`：提取单轮里真正值得长期记住的信息
- `extract_from_conversation()`：提取整段对话中的稳定背景和长期偏好
- `extract_experience()`：只提取经验层内容

规则原则：

- 一次性任务请求不进长期记忆
- 用户背景进入 `context`
- 偏好、规则、风格进入 `preference`
- 经验、成功模式、错误教训进入 `experience`

---

## 前端面板

记忆面板改为三层用途优先：

- 顶部主筛选：`全部 / 上下文 / 偏好 / 经验`
- 卡片主标签显示用途层
- 卡片次标签显示原始 `type`
- 汇总区显示各层数量

旧英文 `type` 仍然保留，便于排查历史数据和内部分类。

---

## OpenAkita 借鉴点

这次改造借鉴的是 OpenAkita 的思路：  
记忆不只是“存起来”，更重要的是 **在不同决策环节里用起来**。

因此本项目从“存储型记忆”迈向“行为驱动型记忆”：

- 上下文层：解决“知道什么”
- 偏好层：解决“应该怎么做”
- 经验层：解决“以前怎么做过、哪里容易踩坑”

---

## 故障排查

### 启动后没有迁移旧记忆

- 检查 `data/memory/scene_memory.jsonl` 是否可写
- 检查日志中是否出现 `usage_layer 迁移` 相关输出

### 检索不到偏好层 / 经验层

- 检查对应记忆条目的 `usage_layer`
- 若旧数据只有 `type`，确认启动迁移是否成功

### 面板里层级显示异常

- 确认 `/api/memory` 返回中包含 `usage_layer`
- 检查是否存在历史脏数据（如空字符串、非法层名）

---

## 后续方向

1. 将三层记忆进一步接入工具选择和技能调度
2. 为偏好层增加更细的优先级或强弱约束
3. 将经验层与知识图谱、任务计划做更强联动

# 修复 `MEMORY.md` 迁移遗留的逻辑漏洞 (2026-03-06)

在将系统核心记忆库从静态的 `MEMORY.md` 彻底迁移到动态渲染的 `scene_memory.jsonl` 后，我们对相关代码进行了深度逻辑回查，成功排查并修复了一个由于组件解耦带来的隐藏 Bug。

## 发现逻辑漏洞（Bug 分析）

### 漏洞：`daily_consolidator.py` 残留的无效调用
在日常记录合并脚本 `core/daily_consolidator.py` 中，每天的日终大模型都会对日志记录进行总结（Insight），并将其提取为技术经验。
在旧版的代码中，提取出的 Insight 是通过如下代码写入过去的静态文件的：
```python
self.identity.add_experience(f"Insight {date_str}", insight)
```
但我们在迁移时，由于 `MEMORY.md` 物理文件被删除，`core/identity_manager.py` 中的 `add_experience` 方法也已随之被安全移除。此时如果系统运行到晚上进行日常整顿时，将会触发 `AttributeError: 'IdentityManager' object has no attribute 'add_experience'` 引发系统崩溃，导致记忆沉淀失败。

## 修复方案

我们审查了所有的内部核心服务如何与 `identity` 进行交互，并做出了正确的处理：

- **[修复] `core/daily_consolidator.py`**:
  将原先向 `identity` 强行追加 Markdown 的逻辑，修改为标准的向 `MemoryManager` 写入字典数据。修复后的代码如下：
  ```python
  insight = self._extract_daily_experience(date_str)
  if insight:
      self.memory.add(
          insight, 
          tags=["daily_insight", f"date:{date_str}"], 
          type="experience", 
          source="daily_consolidator"
      )
  ```
  这样大模型的每日提炼将无缝变成一条普通的 `experience`（经验），被放入 `scene_memory.jsonl` 中，且能够在下一次对话中被 `build_prompt()` 精准抓回。

### 全局清查结语

我们使用了全局搜索遍历了所有的 `identity.xxx` 及其内部调用。目前可以确信：
- `IdentityManager` 除了提供 `USER.md` 和 `HABITS.md` 的读写支持外，仅保留了统一拼接的 `build_prompt`。
- 其他业务系统不再对被弃用的特定内存工具（如 `update_active_task`）有任何依赖残留。
迁移在逻辑层面已经做到完全闭环和无损！

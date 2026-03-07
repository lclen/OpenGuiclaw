# 日记生成开关功能文档 (Diary Feature Toggle)

此功能允许用户在不中断 **认知进化**（Memory Extraction, Knowledge Graph Update, Persona Evolution）的前提下，单独关闭每日 **日记 (Diary)** 的生成。

## 1. 功能概述
- **默认行为**：每日进化过程会根据当日对话生成一篇第一人称 AI 日记。
- **关闭后行为**：进化核心（SelfEvolution）将跳过日记写入步骤，但仍会继续提取记忆碎片、更新用户画像、同步知识图谱，并执行主动探测任务。
- **前端联动**：关闭开关后，侧边栏的 "认知日志" 入口将自动隐藏。

---

## 2. 后端实现细节

### 核心逻辑修改 (`core/self_evolution.py`)
- `SelfEvolution` 类引入了 `_diary_enabled` 标志。
- 在 `evolve_from_journal` 方法的 Step 1（日记写入）之前插入了逻辑检查：
  ```python
  if not self._diary_enabled:
      print("[SelfEvolution] 📔 日记功能已关闭，跳过日记生成。")
      # 直接进入后续的记忆提取和 KG 进化步骤
  else:
      self._write_diary(journal_text, today_str)
  ```

### 配置读取 (`core/agent.py`)
- `Agent` 类初始化 `SelfEvolution` 时，从 `config.json` 中读取 `journal.enable_diary` 字段（默认为 `True` 以保持向后兼容）。

---

## 3. 前端集成细节

### 配置同步 (`static/js/app-logic.js`)
- `config` 对象初始化时包含 `journal: { enable_diary: true }`。
- `loadGlobalConfig` 方法负责从后端 `/api/config` 接口同步最新的日记开关状态。
- `saveGlobalConfig` 方法将前端修改后的开关状态即时写回后端配置文件。

### UI 入口控制 (`templates/panels/sidebar.html`)
- 侧边栏的 "认知日志 (Diary)" 按钮使用了 Alpine.js 的 `x-show` 指令进行显隐控制：
  ```html
  x-show="(btn.panel !== 'persona' || showVrm) && (btn.panel !== 'diary' || config.journal.enable_diary)"
  ```

### 设置界面 (`templates/panels/panel_config.html`)
- 在 "系统设置" 的 "系统环境" 选项卡中新增了 "认知日志 (Diary)" 开关项。
- 点击开关即时触发配置保存逻辑，并实现 UI 面板的联动切换（如在日记面板时关闭开关，系统会自动跳回聊天界面）。

---

## 4. 如何配置

### 通过界面操作（推荐）
1. 打开左侧菜单底部的 **系统设置**。
2. 切换至 **系统环境** 选项卡。
3. 找到 **认知日志 (Diary)** 开关进行切换。

### 手动配置文件
在 `config.json` 的顶层添加或修改以下配置：
```json
{
  "journal": {
    "enable_diary": false
  }
}
```

---

*功能实现时间: 2026-03-05 14:58*
*文档更新日期: 2026-03-05*
*Antigravity 维护*

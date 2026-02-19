# Qwen AutoGUI Agent 项目概览

## 1. 项目简介
**Qwen AutoGUI Agent** 是一个基于阿里云 Qwen（通义千问）大模型的智能桌面助理框架。它不仅具备传统的对话能力，还能通过视觉感知“看”到你的屏幕，通过 GUI 工具“操作”你的电脑，并拥有自我进化的长期记忆系统。

该项目旨在打造一个**有感知、有记忆、能干活、会主动关心**的 AI 伙伴 (Companion)。

---

## 2. 核心特性

### 🧠 智能核心
- **多模态能力**：基于 Qwen-Max/Plus 模型，支持文本对话和 Vision 视觉分析。
- **工具调用 (Tool Use)**：原生支持 OpenAI 格式的 Function Calling，可扩展无限能力。
- **联网搜索**：集成了 Qwen 的联网搜索能力，并提供 `web_fetch` 工具深入阅读网页。

### 👀 视觉感知 (Active Context)
- **后台观察**：独立的后台线程每隔一段时间（默认 5 分钟）截取屏幕。
- **状态分析**：利用 Vision 模型分析你当前的状态（Working/Entertainment/Error/Idle）。
- **主动交互**：根据截屏内容和当前模式，AI 会主动发起对话。例如：
    - 看到报错时主动询问是否需要帮助。
    - 发现你长时间发呆或在浏览娱乐内容时，通过弹幕或日志与你闲聊。
- **三种模式** (`/mode` 切换)：
    - **🤐 静默 (Silent)**：只记录日志，永不打扰。
    - **😐 正常 (Normal)**：仅在检测到异常（报错）或明显机会时打扰。
    - **🤩 活泼 (Lively)**：积极寒暄，是个话痨伙伴。

### 💾 记忆与进化
- **长期记忆**：自动提取对话中的关键事实（用户喜好、重要信息）存入 `data/memory.jsonl`。
- **向量检索 (RAG)**：支持记忆的向量化存储与语义搜索（基于 `text-embedding-v4`），让 AI 能“想起”模糊的往事。
- **自我进化 (Self-Evolution)**：
    - 每天（或跨天首次启动时）自动回顾昨天的日志。
    - 提炼新的长期记忆。
    - **人设微调**：根据交互历史，AI 会自动提议修改 `PERSONA.md`，让性格越来越贴合你的偏好。

### 🎮 GUI 自动化
- **全能控制**：封装了 `pyautogui` 和 `mss`，支持点击、双击、拖拽、滚轮、键盘输入。
- **视觉定位**：支持基于坐标（归一化 0-1000）的操作（配合视觉模型）。

### 🔌 插件系统
- **热加载**：支持在 `plugins/` 目录下放入 `.py` 文件扩展能力。
- **动态管理**：运行时通过 `/plugins reload` 指令热更新代码，无需重启主程序。

---

## 3. 项目架构

```
qwen_autogui/
├── main.py                 # 程序入口，CLI 交互循环，指令处理
├── PERSONA.md              # AI 人设定义（支持自动进化）
├── data/                   # 数据存储（记忆、日志、配置）
│   ├── config.json         # API Key 与模型配置
│   ├── memory.jsonl        # 长期记忆数据
│   ├── memory_vectors.jsonl# 记忆向量索引
│   ├── journal/            # 每日交互日志
│   └── sessions/           # 会话历史
├── core/                   # 核心模块
│   ├── agent.py            # Agent 主逻辑 (LLM 交互, Tool 分发)
│   ├── context.py          # 视觉感知线程 (Vision, Proactive logic)
│   ├── memory.py           # 记忆管理器
│   ├── vector_memory.py    # 向量存储与检索
│   ├── self_evolution.py   # 进化引擎 (日志分析, 人设更新)
│   ├── skills.py           # 技能注册装饰器
│   ├── plugin_manager.py   # 插件管理器
│   └── journal.py          # 日志管理器
└── skills/                 # 内置技能
    ├── autogui.py          # 屏幕控制 (PyAutoGUI)
    ├── basic.py            # 基础工具 (File/Time/Sys)
    └── web_search.py       # 网页阅读工具
```

---

## 4. 快速开始

### 安装依赖
```bash
pip install -r requirements.txt
# 核心依赖：openai, pyautogui, mss, pillow, requests, beautifulsoup4
```

### 配置
在 `data/config.json` 中填入你的 DashScope API Key：
```json
{
    "api": {
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "api_key": "sk-your-key-here",
        "model": "qwen-max"
    },
    "persona_name": "你的 AI 助理"
}
```

### 运行
```bash
python main.py
```

---

## 5. 常用指令

在控制台中输入以下 Slash 命令进行控制：

| 指令 | 说明 |
| :--- | :--- |
| `/new` | 开启新会话（存档当前对话） |
| `/mode` | 切换主动交互模式 (Silent/Normal/Lively) |
| `/context` | 查看视觉感知状态与日志开关 |
| `/memory` | 查看已记住的所有长期记忆 |
| `/skills` | 列出当前加载的所有技能 |
| `/plugins` | 查看或重载插件 (支持热更新) |
| `/sessions` | 列出历史会话列表 |
| `/help` | 显示帮助菜单 |
| `/quit` | 退出程序 |

---

## 6. 开发扩展

### 添加新技能
在 `skills/` 目录下新建 `.py` 文件，或在 `plugins/` 下新建插件。使用装饰器注册：

```python
def register(manager):
    @manager.skill(
        name="my_tool",
        description="工具描述",
        parameters={"properties": {"arg": {"type": "string"}}, "required": ["arg"]}
    )
    def my_tool(arg: str):
        return "执行结果"
```

### 自定义人设
修改根目录下的 `PERSONA.md`。注意，AI 的**自我进化**功能可能会经你确认后自动追加内容到此文件。

---

## 7. 特别说明
- **隐私**：视觉感知功能会定时截屏。所有图片仅发送给配置的 LLM API 临时分析，**不会**保存在本地硬盘（仅内存处理），分析完即丢弃。
- **Token 消耗**：开启 `/mode` (视觉感知) 会定期调用 Vision 模型，这会产生额外的 API 费用。静默模式下也会进行分析（用于记录日志），若想彻底关闭，可在代码中禁用 `ContextManager`。

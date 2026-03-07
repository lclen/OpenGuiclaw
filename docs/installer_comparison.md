# 📦 安装包方案深度对比：openGuiclaw vs. OpenAkita

本文档旨在对 `openGuiclaw` (基于 Inno Setup) 与 `OpenAkita` (基于 Tauri/NSIS) 的安装流程及核心逻辑进行横向对比，并提炼出值得借鉴的优化方案。

---

## 1. 核心逻辑点对照表

| 对比维度 | openGuiclaw (当前现状) | OpenAkita (借鉴亮点) | 评价与建议 |
| :--- | :--- | :--- | :--- |
| **安装技术栈** | [Inno Setup 6](https://jrsoftware.org/ishelp/index.php) | Tauri + NSIS (Nullsoft Scriptable Install System) | 两者均能实现高度自定义。Inno 脚本写法更接近 Pascal，NSIS 更底层。 |
| **现代风格** | 已开启 `WizardStyle=modern` | 完美支持 Win11 亚克力/现代阴影视觉 | 建议通过 Inno 进一步细化向导标题左侧图标及 Banner 图片。 |
| **进程强制清理** | 直接 `taskkill /IM name` | 1. 优先使用 PowerShell `Stop-Process` (静默且更快)<br>2. 通过 `.pid` 文件精准定位特定的 Python 后端进程。 | **可借鉴 1**：将 `taskkill` 调用升级为 PowerShell 以防闪烁黑框并适配更复杂的名字匹配逻辑。 |
| **数据路径嗅探** | 简单假设路径在 `%USERPROFILE%\.openguiclaw` | 通过 `custom_root.txt` 获取由前端自定义配置后的实际数据存放目录。 | **可借鉴 2**：若用户未来可以更改数据目录，安装程序卸载时必须能自动侦测到。 |
| **环境变量管理** | 直接读写注册表 (有 1024 字符截断风险) | 使用 PowerShell 辅助脚本逐条精确对比的分号分割 Path 值。 | **可借鉴 3**：改用 PowerShell 读写 Path，避免注册表长度限制导致 PATH 被无意清空。 |
| **安装后置参数** | `Filename: "{app}\openGuiclaw.exe"; ... Flags: postinstall` | 允许带 `--first-run` 或 `--clean-env` 参数启动后台以便完成状态同步。 | **可借鉴 4**：安装完成后不仅是单纯启动应用，还可以附带状态同步动作。 |

---

## 2. 值得借鉴并立即引入的功能点

### A. 更稳固的 PATH (环境变量) 写入方案
- **痛点**：当前 Pascal 脚本直接手动拼接字符串到注册表。如果用户的 PATH 比较长，或者含有 %USERPROFILE% 等引用，Inno Setup 的原生 `RegWriteStringValue` 可能处理不当导致截断。
- **优化**：将 OpenAkita 的 `WritePathHelper` 移植到 Inno Setup。在安装期间临时释放一个 `.ps1` 辅助脚本，通过 PowerShell 的 `Set-ItemProperty` 处理 PATH 增加/删除。

### B. 多进程精准清理 (双保险机制)
- **痛点**：目前 `taskkill` 对 `node.exe` 是全服扫描，可能误杀用户电脑里的其它生产环境 node 开发项目。
- **优化**：在应用主程序启动时生成 `.pid` 文件，并在安装/卸载时读取此文件中的 PID 进行精准定点清除 (仅限 backend 和 UI 两个相关进程)。

### C. 数据迁移及配置状态同步
- **亮点**：OpenAkita 在安装完成后会生成一个 `cli.json` 文件供 App 在界面上展示“安装成功且 CLI 已就绪”的标记。
- **建议**：openGuiclaw 可以在安装期间生成一个标记文件，避免前端页面在安装完后的首次启动时还需要经历漫长的“初始配置引导”。

---

## 3. 下一步优化行动建议

1. **[优先级：高]**：升级 `installer.iss` 中的 PATH 管理核心，改用 PowerShell 逻辑，彻底杜绝环境变量丢失隐患。
2. **[优先级：中]**：细化向导图片。引入大块位图 (Bitmap) 背景，让安装包看起来不仅是“标准”，而是“旗舰”。
3. **[优先级：低]**：当主程序后续支持选择非 `%USERPROFILE%` 的存放路径时，在 `installer.iss` 中引入数据路径动态侦测。


# 💡 OpenAkita 安装包功能亮点及借鉴方案

通过对 `OpenAkita` 安装源码 (`installer.nsi`) 的深度分析，以下功能点非常值得 `openGuiclaw` 借鉴，能够显著提升产品的专业感和安全性。

---

## 1. AI 风险须知页面 (Risk Acknowledgement)
**功能描述**：在安装过程中强制展示一个页面，告知用户 AI Agent 的局限性（行为不可完全预测、建议处于监督状态、API 费用风险等）。
**借鉴意义**：
- **专业性**：体现了开发者对 AI 安全性的重视。
- **合规性**：在涉及自动化文件操作的工具中，这是标准做法。
- **建议**：在 `openGuiclaw` 安装向导中增加一个类似的“使用声明”展示。

## 2. CLI 别名支持 (Command Alias)
**功能描述**：OpenAkita 允许用户同时勾选注册 `openakita` 和简短别名 `oa` 命令。
**借鉴意义**：
- **易用性**：`openGuiclaw` 单词较长，在命令行输入较慢。
- **建议**：支持注册 `og` (openGuiclaw) 或 `gc` (Guiclaw) 这种极致简短的命令到 PATH。

## 3. 极细粒度的“数据清理”选项
**功能描述**：OpenAkita 将“环境残留”与“个人数据”分得很开。
- **环境层**：Python venv、Runtime 缓存、模型缓存（可重下）。
- **数据层**：对话记录、API Key、工作区配置（不可恢复）。
**借鉴意义**：
- **容错性**：很多时候用户只是想解决“环境坏了”的问题，并不想丢掉对话历史。
- **建议**：我们在 `installer.iss` 中已经实现了分层，可以进一步细化描述，并增加“风险高亮”颜色。

## 4. 完成页面的“首航引导” (Onboarding Wizard)
**功能描述**：安装完成后启动时带上 `--first-run` 参数，直接跳转到 App 内部的引导界面，而不是直接进入主对话。
**借鉴意义**：
- **体验连贯性**：确保新用户第一次打开程序时一定能正确配置 API Key。

## 5. 卸载确认界面的“内嵌勾选项”
**功能描述**：在 Windows 标准的“确认卸载吗？”弹窗下方，直接嵌入一个勾选框：“同时删除用户数据”。
**借鉴意义**：
- **直观性**：比安装结束后再弹窗问要更符合 Windows 用户的习惯。
- **建议**：Inno Setup 可以通过 `[Code]` 修改卸载页面的按钮和复选框来实现。

---

## 🚀 针对 openGuiclaw 的下一步优化：

1.  **[已完成]** 现代风格 UI 开启。
2.  **[待增加]** 在 PATH 环境变量中额外注册一个名为 `og` 的快捷命令。
3.  **[待增加]** 优化向导中的文字描述，加入“风险告知”板块。
4.  **[待优化]** 进一步完善卸载时的文件清理逻辑，区分 `venv` 和 `config`。

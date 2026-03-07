# OpenAkita Agent 功能调研报告

## 概要
OpenAkita 的 Agent 系统是一个高度模块化、支持多 Agent 协作和自进化的架构。它不仅仅是一个简单的 LLM 调用循环，而是一个包含了感知（Reasoning）、记忆（Memory）、技能（Skills）和协作（Orchestration）的完整生态系统。

## 核心组件分析

### 1. 核心 Agent (core/agent.py)
Agent 是系统的基本单元。其核心职责包括：
- **推理引擎 (ReasoningEngine)**: 负责处理输入、规划任务并生成工具调用。
- **RalphLoop**: 一个自进化的感知-行动循环，允许 Agent 观察其行为结果并进行修正。
- **技能注册 (SkillRegistry)**: 动态加载和管理能力模块。
- **记忆管理 (MemoryManager)**: 处理短期对话历史、长期向量记忆以及知识图谱（Knowledge Graph）。

### 2. 多 Agent 编排器 (agents/orchestrator.py)
编排器负责管理多个 Agent 之间的协作：
- **分发与委派 (Dispatch & Delegation)**: 编排器可以根据任务复杂度决定是否将子任务委派给专门的子 Agent（Sub-Agent）。
- **会话路由 (Session Routing)**: 确保消息流转到正确的 Agent 实例。
- **健康检查与重试**: 监控子 Agent 状态，处理超时和故障切换。

### 3. Agent Profile (agents/profile.py)
Profile 定义了 Agent 的“人格”和“约束”：
- **身份定义**: 名字、图标、描述、分类。
- **技能限制 (SkillsMode)**: 决定 Agent 拥有哪些技能（全部、白名单、或黑名单）。
- **自定义提示词 (Custom Prompt)**: 为 Agent 设置特定的系统提示词。
- **降级方案 (Fallback)**: 当当前 Agent 无法处理时，可以回退到 `default` Agent。

### 4. 技能系统 (Skills System)
OpenAkita 的技能系统采用了一种基于 Markdown (`SKILL.md`) 的 SOP（标准作业程序）模式：
- **逻辑即文档**: 技能说明书不仅是给开发者看的，更是直接喂给 AI 的提示词。
- **模块化**: 每个技能是一个独立的文件夹，包含说明文档、预设代码片段和依赖声明。
- **按需加载**: Agent 启动时只加载 Profile 允许的技能，减少 Token 消耗。

---

## openGuiclaw 项目接入方案规划

### 背景对比
- **openGuiclaw 目前状态**: 使用单一的 `ScreenAgent` 类，硬编码了 PyAutoGUI 动作，依赖于连续的截图和文字 Prompt 循环。
- **OpenAkita 优势**: 支持更复杂的长链条任务、更精准的技能分割、持久化的知识图谱。

### 接入建议

#### 第一阶段：引入 Skill 系统
- **动作解耦**: 将 `agent.py` 中的 `click`, `type`, `scroll` 等硬编码动作提取为 OpenAkita 风格的 `SKILL.md` 文件。
- **SOP 驱动**: 编写针对 GUI 操作的 SOP，例如“如何安全地打开软件”、“如何处理弹窗阻塞”。

#### 第二阶段：集成知识图谱 (KG)
- **已完成任务**: 我们已经清理了 KG 中的干扰数据（工具日志）。
- **深化应用**: 令 Agent 在执行 GUI 任务前，先检索 KG 中关于“该软件的常见按钮位置”或“历史操作偏好”的记录，从而提高成功率。

#### 第三阶段：引入多 Agent 协作
- **角色分化**:
    - `ScreenAgent` (感知者): 负责观察屏幕和基础点击运动。
    - `Planner` (大脑): 使用 OpenAkita 的 Reasoning 逻辑，进行高层规划。
    - `Coder` (专家): 专门处理涉及 PowerShell/Python 代码生成的子任务。
- **委派机制**: 当主 Agent 识别到需要写脚本时，调用 `AgentOrchestrator` 将任务委派给 `Coder` Agent。

#### 第四阶段：配置化 Profile
- 为 openGuiclaw 定义不同的预设 Profile，例如：
    - `Automator`: 追求极速自动化的操作员。
    - `Analyst`: 侧重于观察和分析屏幕信息的助手。
    - `Debugger`: 专门用于排查系统故障的模式。

## 结论
OpenAkita 的设计哲学非常契合 openGuiclaw 的长远目标。通过引入其 Skill 和 Profile 体系，可以极大地提升 GUI Agent 的灵活性和可靠性。

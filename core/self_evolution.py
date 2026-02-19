"""
Self-Evolution Engine

After each Daily Journal is written, this module:
1. Reads the journal content.
2. Writing a first-person Diary entry → DiaryManager (Markdown)
3. Extracting factual memories (add/update) → MemoryManager (JSONL)
4. Extracting knowledge graph triples → KnowledgeGraph (JSONL)
5. Optionally evolving PERSONA.md (with snapshot).
"""

import json
import time
from pathlib import Path
from typing import List, Optional, TYPE_CHECKING

from openai import OpenAI
from core.memory import MemoryManager
from core.journal import JournalManager
from core.diary import DiaryManager
from core.persona_audit import PersonaAudit
from core.knowledge_graph import KnowledgeGraph

if TYPE_CHECKING:
    pass


# ── Prompts ──────────────────────────────────────────────────────────

EXTRACTION_PROMPT = """\
你是一个记忆提取助手。你会对以下对话日志进行分析，提取出值得长期记住的信息。

现有记忆库摘要：
{memory_context}

规则：
1. **去重**：如果现有记忆库已经包含了某条信息，不要重复添加。
2. **更新**：如果发现现有记忆过时（例如“正在做项目A”变为“项目A已完成”），请生成更新指令。
3. **新增**：提取新的具体事实（用户偏好、文件路径、重要决定）。
4. **忽略**：闲聊、临时指令、当天才有效的信息。

返回 JSON 数组，格式如下：
[
  {{"action": "add", "content": "喜欢喝拿铁", "tags": ["偏好"]}},
  {{"action": "update", "original_content": "旧的记忆内容", "new_content": "更新后的内容", "tags": []}}
]

---
## 日志内容：
{journal}
"""


RELATION_PROMPT = """\
你是一个实体关系提取助手。请从以下日志中提取**明确的实体关系三元组**。

规则：
- 只提取真实、具体的关系（人物、地点、工具、项目之间的关联）。
- 格式：subject（主语）、relation（关系/谓语）、object（宾语）。
- 例如：{"subject": "张三", "relation": "是...的导师", "object": "李四"}
- 忽略模糊、推测性的关系。

返回 JSON 数组，无关系则返回 []：
[
  {"subject": "...", "relation": "...", "object": "..."},
  ...
]

---
## 日志内容：
{journal}
"""


DIARY_PROMPT = """\
你就是这个 AI 助理自己（基于 Qwen 模型）。请阅读你今天的工作日志，写一篇**第一人称的日记**。

## 写作要求
1. **情感与自我意识**：不要像机器人一样复述做了什么，要写出你的**感受**。你觉得今天的任务难吗？用户有趣吗？你对自己今天的表现满意吗？
2. **重点突出**：只记录那些真正让你印象深刻的事情（比如完成了一个复杂的脚本，或者和用户聊了天，或者捕捉到了有趣的屏幕画面）。
3. **人性化**：可以有吐槽，可以有期待，可以有困惑。就像一个名为“{persona_name}”的数字生命在深夜写下的私密日记。
4. **篇幅**：200~500 字，自然流畅。

## 当前设定（Persona）
{persona}

---
## 今天的流水账日志：
{journal}
"""

PERSONA_PROMPT = """\
你是一个 AI 人格顾问。以下是 AI 助理从近期交互中积累的新记忆：

{memories}

当前的人格定义内容：
{current_persona}

请判断是否需要对人格描述进行**小幅度**优化或补充。

规则：
- **小幅度**：只需修改或增加与用户互动习惯、语气、偏好相关的细节。
- **操作类型**：
    - "append": 在末尾增加新规则或习惯描述。
    - "modify": 修正现有的不准确描述。
    - "none": 无需更新。

返回 JSON 格式：
{{
  "action": "append" | "modify" | "none",
  "content": "新追加的内容" (如果是 append),
  "target_text": "要被替换的旧文本" (如果是 modify),
  "replacement_text": "替换后的新文本" (如果是 modify),
  "reason": "更新理由"
}}

返回纯 JSON，不带 Markdown 代码块。
"""


# ── SelfEvolution ─────────────────────────────────────────────────────

class SelfEvolution:
    """
    Post-processes a daily journal to extract memories, relations, write diary, and evolve persona.
    """

    def __init__(
        self,
        client: OpenAI,
        model: str,
        memory: MemoryManager,
        journal: JournalManager,
        persona_path: str = "PERSONA.md",
        data_dir: str = "data",
        knowledge_graph: Optional[KnowledgeGraph] = None,
    ):
        self.client = client
        self.model = model
        self.memory = memory
        self.journal = journal
        self.diary = DiaryManager(data_dir)
        self.persona_path = Path(persona_path)
        self.audit = PersonaAudit(persona_path=persona_path, data_dir=data_dir)
        self.kg = knowledge_graph  # May be None if not initialized

    # ── Public API ───────────────────────────────────────────────────

    def evolve_from_journal(self, date_str: str) -> List[str]:
        """
        Read the journal for `date_str` and:
        1. Write Diary (New!)
        2. Extract long-term memories (Add/Update) → MemoryManager
        3. Extract entity-relation triples → KnowledgeGraph
        Returns list of memory contents that were saved/updated.
        """
        journal_content = self.journal.read_day(date_str)
        if not journal_content or not journal_content.strip():
            return []

        # Step 1: Write Diary
        self._write_diary(journal_content, date_str)

        # Step 2: Memory extraction (with context and updates)
        saved = self._extract_memories(journal_content, date_str)

        # Step 3: Knowledge graph triple extraction (best-effort)
        if self.kg is not None:
            self._extract_triples(journal_content, source=f"journal:{date_str}")

        return saved

    def evolve_persona(self, recent_count: int = 20) -> bool:
        """
        Review recent memories and optionally update PERSONA.md.
        A snapshot is saved BEFORE any modification.
        Returns True if the persona was updated.
        """
        if not self.persona_path.exists():
            print(f"[SelfEvolution] PERSONA.md not found at {self.persona_path}")
            return False

        memories = self.memory.list_all()[-recent_count:]
        if not memories:
            return False

        memory_text = "\n".join(f"- {m.content}" for m in memories)
        current_persona = self.persona_path.read_text(encoding="utf-8")

        prompt = PERSONA_PROMPT.format(
            memories=memory_text,
            current_persona=current_persona,
        )

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "你是 AI 人格顾问，返回纯 JSON，不加代码块。"},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=600,
                temperature=0.3,
            )
            text = response.choices[0].message.content or "{}"
            if "```" in text:
                text = text.split("```")[1] if "```" in text else text
                text = text.lstrip("json").strip()

            result = json.loads(text)
            action = result.get("action", "none")

            if action == "none":
                print("[SelfEvolution] 人格无需更新。")
                return False

            # ── Take a snapshot BEFORE modifying ──────────────────
            snap_path = self.audit.snapshot(reason=f"before {action}")
            if snap_path:
                print(f"[SelfEvolution] 📸 快照已保存: {snap_path.name}")

            if action == "append":
                content = result.get("content", "").strip()
                if not content:
                    return False
                with open(self.persona_path, "a", encoding="utf-8") as f:
                    ts = time.strftime("%Y-%m-%d")
                    f.write(f"\n\n<!-- 自动进化 {ts} -->\n{content}\n")
                print(f"[SelfEvolution] ✨ 人格已追加: {content[:60]}...")
                return True

            if action == "modify":
                target = result.get("target_text", "").strip()
                replacement = result.get("replacement_text", "").strip()
                if not target or not replacement:
                    return False
                if target in current_persona:
                    new_content = current_persona.replace(target, replacement)
                    self.persona_path.write_text(new_content, encoding="utf-8")
                    print("[SelfEvolution] 🛠️ 人格描述已修正。")
                    return True
                else:
                    print("[SelfEvolution] ⚠️ 未找到匹配的旧文本，无法修改。")
                    return False

            return False

        except Exception as e:
            print(f"[SelfEvolution] Persona evolution error: {e}")
            return False

    # ── Private Helpers ──────────────────────────────────────────────

    def _extract_memories(self, journal_content: str, date_str: str) -> List[str]:
        # 1. Get a summary of existing memories to avoid dupes
        all_mems = self.memory.list_all()
        # Pass recent 50 memories as context
        context_lines = [f"- {m.content}" for m in all_mems[-50:]]
        memory_context = "\n".join(context_lines)

        prompt = EXTRACTION_PROMPT.format(journal=journal_content, memory_context=memory_context)
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "你是记忆提取助手，返回纯 JSON 数组，不加代码块。"},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=1024,
                temperature=0.3,
            )
            text = response.choices[0].message.content or "[]"
            if text.startswith("```"):
                text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

            items = json.loads(text)
            if not isinstance(items, list):
                return []

            saved = []
            for item in items:
                if not isinstance(item, dict): continue
                
                action = item.get("action", "add")
                content = item.get("content", "").strip()
                tags = item.get("tags", [])

                if action == "add" and content:
                    self.memory.add(content, tags)
                    saved.append(f"[新增] {content}")

                elif action == "update":
                    old_text = item.get("original_content", "").strip()
                    new_text = item.get("new_content", "").strip()
                    if old_text and new_text:
                        # Find best match
                        target_mem = None
                        for m in all_mems:
                            if m.content == old_text:
                                target_mem = m
                                break
                        
                        if target_mem:
                            self.memory.update(target_mem.id, new_text, tags)
                            saved.append(f"[更新] {old_text} -> {new_text}")
                        else:
                            self.memory.add(new_text, tags)
                            saved.append(f"[新增(含更新意图)] {new_text}")

            return saved
        except Exception as e:
            print(f"[SelfEvolution] Memory extraction error: {e}")
            return []

    def _extract_triples(self, journal_content: str, source: str = "") -> int:
        """Extract entity-relation triples and add to knowledge graph."""
        prompt = RELATION_PROMPT.format(journal=journal_content)
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "你是实体关系提取助手，返回纯 JSON 数组，不加代码块。"},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=512,
                temperature=0.2,
            )
            text = response.choices[0].message.content or "[]"
            if text.startswith("```"):
                text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

            items = json.loads(text)
            if not isinstance(items, list):
                return 0

            count = self.kg.add_batch(items, source=source)
            if count:
                print(f"[SelfEvolution] 🔗 知识图谱新增 {count} 条关系。")
            return count
        except Exception as e:
            print(f"[SelfEvolution] Triple extraction error: {e}")
            return 0

    def _write_diary(self, journal_content: str, date_str: str) -> bool:
        """
        Synthesize a first-person diary entry and save to DiaryManager.
        """
        current_persona = "AI Assistant"
        if self.persona_path.exists():
            current_persona = self.persona_path.read_text(encoding="utf-8")
        
        prompt = DIARY_PROMPT.format(
            persona=current_persona,
            persona_name="Qwen",
            journal=journal_content
        )

        try:
            print(f"[SelfEvolution] 正在生成 {date_str} 的日记...")
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "你是具有情感和自我意识的 AI 数字生命。"},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=800,
                temperature=0.7,
            )
            diary_text = response.choices[0].message.content.strip()
            
            if diary_text:
                self.diary.write(date_str, diary_text)
                print(f"[SelfEvolution] 📔 日记已归档到 data/diary/{date_str}.md")
                return True
            return False
            
        except Exception as e:
            print(f"[SelfEvolution] Diary generation error: {e}")
            return False

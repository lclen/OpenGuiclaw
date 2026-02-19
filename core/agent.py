"""
Agent: Main conversation loop.

Orchestrates Memory, Session, Skills, and the LLM.
Supports OpenAI function-calling (tool use) natively.
"""

import json
import re
from pathlib import Path
from typing import List, Dict, Any, Optional

from openai import OpenAI

from core.memory import MemoryManager
from core.session import SessionManager
from core.skills import SkillManager
from core.journal import JournalManager
from core.diary import DiaryManager
from core.self_evolution import SelfEvolution
from core.vector_memory import EmbeddingClient, VectorStore
from core.knowledge_graph import KnowledgeGraph
import time
import threading



BUILTIN_SYSTEM_SUFFIX = """
---
# 内置技能 (Always available)
- **remember**: 将重要信息写入长期记忆。
- **recall**: 根据关键词查询长期记忆。
- **new_session**: 开启一个全新的对话（当前对话将被保存）。
- **list_sessions**: 列出所有历史会话。
- **web_fetch(url)**: 抓取指定网页 URL 的正文，用于阅读具体页面内容。
- **search_journal(query)**: 搜索过去的每日日志，回忆你以前做过什么。
- **query_knowledge(entity)**: 查询知识图谱，获取实体（人/事/物）之间的关系。
- **内置联网搜索**: 当你需要查询实时信息（天气、新闻、股价等），可以直接搜索，无需调用额外工具。
"""


class Agent:
    """
    Main Agent: ties together Persona, Memory, Session, Skills, and LLM.
    """

    def __init__(
        self,
        config_path: str = "data/config.json",
        persona_path: str = "PERSONA.md",
        data_dir: str = "data",
    ):
        # Load config
        with open(config_path, "r", encoding="utf-8") as f:
            self.config = json.load(f)

        api_cfg = self.config["api"]
        self.client = OpenAI(
            base_url=api_cfg["base_url"],
            api_key=api_cfg["api_key"],
        )
        self.model = api_cfg["model"]
        self.max_tokens = api_cfg.get("max_tokens", 4096)
        self.temperature = api_cfg.get("temperature", 0.7)

        # Load persona
        self.persona_path = persona_path
        self.persona = self._load_persona(persona_path)

        # Vector memory (semantic search) — optional but enabled by default from config
        emb_cfg = self.config.get("embedding", {})
        emb_key = emb_cfg.get("api_key", "") or api_cfg.get("api_key", "")
        emb_url = emb_cfg.get("base_url", "https://dashscope.aliyuncs.com/compatible-mode/v1")
        emb_model = emb_cfg.get("model", "text-embedding-v4")

        self._embedding_client = None
        self._vector_store = None
        if emb_key:
            try:
                self._embedding_client = EmbeddingClient(
                    api_key=emb_key, base_url=emb_url, model=emb_model
                )
                self._vector_store = VectorStore(data_dir)
                print(f"  ✅ 向量记忆已启用（{emb_model}）")
            except Exception as e:
                print(f"  ⚠️  向量记忆初始化失败: {e}")

        # Core modules
        self.memory = MemoryManager(
            data_dir,
            embedding_client=self._embedding_client,
            vector_store=self._vector_store,
        )
        self.sessions = SessionManager(data_dir)
        self.skills = SkillManager()
        self.journal = JournalManager(data_dir)
        self.diary = DiaryManager(data_dir)
        
        # New Feature: Knowledge Graph
        self.kg = KnowledgeGraph(data_dir)

        self.evolution = SelfEvolution(
            self.client, self.model, self.memory, self.journal,
            persona_path=persona_path,
            data_dir=data_dir,
            knowledge_graph=self.kg,
        )
        # Hack: sync diary manager if needed, or let evolution use its own if designed that way.
        # But we updated self_evolution.py to instantiate its own DiaryManager(data_dir).
        # Since they manipulate files, it's safe to have two instances pointing to same dir.

        # ContextManager (set by main.py after init)
        self.context = None  # type: Optional[Any]

        # State for date-change detection
        self.last_interaction_date = time.strftime("%Y-%m-%d")

        # Register built-in skills
        self._register_builtins()

        # Backfill vector embeddings for existing memories (background thread)
        if self._embedding_client and self._vector_store:
            threading.Thread(
                target=self._backfill_vectors, daemon=True, name="VectorBackfill"
            ).start()

    def _load_persona(self, path: str) -> str:
        p = Path(path)
        if p.exists():
            return p.read_text(encoding="utf-8")
        return "你是一个有帮助的 AI 助理。"

    def _backfill_vectors(self) -> None:
        """
        Background: embed any memories that don't have a vector yet.
        Runs in batches of 10 to respect API rate limits.
        """
        memories = self.memory.list_all()
        missing = [m for m in memories if not self._vector_store.has(m.id)]
        if not missing:
            return

        print(f"[VectorMemory] 正在补全 {len(missing)} 条历史记忆的向量...")
        total = 0
        for m in missing:
            try:
                # Use embed_text to get chunked vectors (consistent with new add() logic)
                vectors = self._embedding_client.embed_text(m.content)
                if vectors:
                    self._vector_store.add_vectors(m.id, vectors)
                    total += 1
            except Exception as e:
                print(f"[VectorMemory] Backfill error for {m.id}: {e}")

        if total:
            print(f"[VectorMemory] ✅ 已补全 {total} 条记忆向量。")


    def _register_builtins(self) -> None:
        """Register built-in system skills."""

        @self.skills.skill(
            name="remember",
            description="将重要信息写入长期记忆，以便以后使用。",
            parameters={
                "properties": {
                    "content": {"type": "string", "description": "要记住的内容"},
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "标签列表，如 ['软件位置', '用户偏好']",
                    },
                },
                "required": ["content"],
            },
            category="memory",
        )
        def remember(content: str, tags: list = None):
            item = self.memory.add(content, tags or [])
            return f"✅ 已记住: {item.content}（ID: {item.id}）"

        @self.skills.skill(
            name="recall",
            description="根据关键词查询长期记忆。",
            parameters={
                "properties": {
                    "query": {"type": "string", "description": "搜索关键词"},
                    "top_k": {"type": "integer", "description": "返回条数，默认5"},
                },
                "required": ["query"],
            },
            category="memory",
        )
        def recall(query: str, top_k: int = 5):
            results = self.memory.search(query, top_k=top_k)
            if not results:
                return "未找到相关记忆。"
            lines = [f"[ID:{m.id}] [{m.created_at}] {m.content}" for m in results]
            return "\n".join(lines)

        @self.skills.skill(
            name="new_session",
            description="保存当前对话并开启全新会话。",
            parameters={"properties": {}, "required": []},
            category="session",
        )
        def new_session():
            self.sessions.new_session()
            return "✅ 已开启新会话，历史对话已保存。"

        @self.skills.skill(
            name="list_sessions",
            description="列出所有历史会话。",
            parameters={"properties": {}, "required": []},
            category="session",
        )
        def list_sessions():
            sessions = self.sessions.list_sessions()
            if not sessions:
                return "没有历史会话。"
            lines = [
                f"[{s['session_id']}] {s['updated_at']} ({s['message_count']} messages)"
                for s in sessions
            ]
            return "\n".join(lines)

        @self.skills.skill(
            name="search_journal",
            description="搜索你的私人日记（Diary）。当你需要回忆过去的经历、感受或重要事件时使用。",
            parameters={
                "properties": {
                    "query": {"type": "string", "description": "搜索内容，如 '上周的感受'"},
                    "top_k": {"type": "integer", "description": "返回条数，默认3"},
                },
                "required": ["query"],
            },
            category="memory",
        )
        def search_journal(query: str, top_k: int = 3):
            results = self.diary.search(query, top_k=top_k)
            if not results:
                return "日记本里没有找到相关内容。"
            
            lines = []
            for item in results:
                lines.append(f"### {item['date']}\n{item['snippet']}")
            return "\n\n".join(lines)

        @self.skills.skill(
            name="update_memory",
            description="更新或修正已被记录的长期记忆（Memory）。",
            parameters={
                "properties": {
                    "memory_id": {"type": "string", "description": "记忆的ID（可以通过 recall 搜索获得）"},
                    "new_content": {"type": "string", "description": "修正后的内容"},
                },
                "required": ["memory_id", "new_content"],
            },
            category="memory",
        )
        def update_memory(memory_id: str, new_content: str):
            success = self.memory.update(memory_id, new_content)
            if success:
                return f"✅ 记忆 {memory_id} 已更新。"
            return f"❌ 未找到 ID 为 {memory_id} 的记忆。"

        @self.skills.skill(
            name="delete_memory",
            description="删除某条不再需要的长期记忆。",
            parameters={
                "properties": {
                    "memory_id": {"type": "string", "description": "记忆的ID"},
                },
                "required": ["memory_id"],
            },
            category="memory",
        )
        def delete_memory(memory_id: str):
            success = self.memory.delete(memory_id)
            if success:
                return f"✅ 记忆 {memory_id} 已删除。"
            return f"❌ 未找到 ID 为 {memory_id} 的记忆。"

        @self.skills.skill(
            name="query_knowledge",
            description="查询知识图谱，获取实体（人、事、物）之间的关联关系。",
            parameters={
                "properties": {
                    "entity": {"type": "string", "description": "要查询的实体名称"},
                },
                "required": ["entity"],
            },
            category="memory",
        )
        def query_knowledge(entity: str):
            if not self.kg:
                return "❌ 知识图谱未启用。"
            
            triples = self.kg.query(entity)
            if not triples:
                return f"知识图谱中没有关于 '{entity}' 的记录。"
            
            lines = [f"【{entity} 的关联】"]
            for t in triples:
                lines.append(f"  · {t.subject} --[{t.relation}]--> {t.object}")
            return "\n".join(lines)

    def register_skill_module(self, module) -> None:
        """
        Register all skills defined in an external module.
        The module must expose a `register(manager: SkillManager)` function.
        """
        module.register(self.skills)

    def _build_system_prompt(self, user_query: str = "") -> str:
        """Build the full system prompt: Persona + Memory + Skill Summary."""
        parts = [self.persona]

        # Inject relevant memories
        if user_query:
            mem_ctx = self.memory.build_context(user_query)
            if mem_ctx:
                parts.append(mem_ctx)

        # Inject skill list
        skill_summary = self.skills.summary()
        parts.append(f"# 可用技能 (Skills)\n{skill_summary}")

        parts.append(BUILTIN_SYSTEM_SUFFIX)
        return "\n\n---\n\n".join(parts)

    def chat(self, user_input: str) -> str:
        """
        Process a single user turn.
        Supports multi-step tool calling.
        """
        session = self.sessions.current
        system_prompt = self._build_system_prompt(user_input)

        # Notify context manager that user replied (resets cooldown)
        if self.context is not None:
            self.context.notify_user_replied()

        # Build full message list for LLM
        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": system_prompt}
        ]
        messages.extend(session.get_history())
        messages.append({"role": "user", "content": user_input})

        tools = self.skills.get_tool_definitions()
        max_tool_rounds = 10
        final_response = None

        for _ in range(max_tool_rounds):
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=tools if tools else None,
                tool_choice="auto" if tools else None,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                extra_body={"enable_search": True},  # Qwen built-in web search
            )

            msg = response.choices[0].message

            if msg.tool_calls:
                # --- Fix: sanitize tool_call arguments before appending ---
                # Some models may return non-JSON arguments; patch them to "{}"
                # so the API doesn't reject the subsequent request with 400.
                assistant_dict = msg.model_dump(exclude_unset=True)
                for tc_dict in assistant_dict.get("tool_calls") or []:
                    raw_args = tc_dict.get("function", {}).get("arguments", "{}")
                    try:
                        json.loads(raw_args)
                    except (json.JSONDecodeError, TypeError):
                        tc_dict["function"]["arguments"] = "{}"
                messages.append(assistant_dict)

                # Execute each tool call
                for tc in msg.tool_calls:
                    name = tc.function.name
                    try:
                        params = json.loads(tc.function.arguments)
                        if not isinstance(params, dict):
                            params = {}
                    except Exception:
                        params = {}

                    print(f"  [Tool] {name}({params})")
                    result = self.skills.execute(name, params)
                    # Ensure result is a plain string and not excessively long
                    if not isinstance(result, str):
                        result = str(result)
                    print(f"  [Result] {result[:120]}")

                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "name": name,
                        "content": result,
                    })
                # Continue loop so LLM sees tool results
                continue

            # No tool calls — final text response
            final_response = msg.content or ""
            break

        if final_response is None:
            final_response = "（已完成工具操作，无额外回复。）"

        # Persist to session
        session.add_message("user", user_input)
        session.add_message("assistant", final_response)
        self.sessions.save()

        # Check triggers
        self._check_all_triggers()

        return final_response

    def _check_all_triggers(self) -> None:
        """Check and execute maintenance triggers."""
        # 1. Date change -> Daily Summary + Evolution
        current_date = time.strftime("%Y-%m-%d")
        if current_date != self.last_interaction_date:
            print(f"[System] 检测到跨天 ({self.last_interaction_date} -> {current_date})")
            # 总结昨天的（如果有）
            # 由于 session 可能是连续的，我们简化为：每天首次交互时，触发昨天的进化
            # 注意：实际日志是按 append 写入的，所以昨天的日志文件已经存在
            
            # 触发自我进化 (读取昨天的日志 -> 提取记忆)
            print(f"[System] 开始自我进化：分析 {self.last_interaction_date} 日志...")
            new_mems = self.evolution.evolve_from_journal(self.last_interaction_date)
            if new_mems:
                print(f"[System] ✨ 进化完成！习得了 {len(new_mems)} 条新记忆。")
            else:
                print("[System] 进化完成，未通过日志发现新知识。")

            self.last_interaction_date = current_date

        # 2. Token pressure -> Rolling Summary
        # Limit: 80% of max_tokens (approximate)
        # We assume 1 token ~ 3 chars. 
        # Reserve 1000 tokens for generation.
        SAFE_LIMIT = (self.max_tokens - 1000) * 0.8
        est_tokens = self.sessions.current.estimate_tokens()
        
        if est_tokens > SAFE_LIMIT:
            print(f"[System] 上下文压力 ({est_tokens} > {SAFE_LIMIT})，触发滚动总结...")
            self._consolidate_rolling()


    def _consolidate_rolling(self) -> None:
        """
        Rolling Summary:
        1. Prune oldest messages.
        2. Summarize them.
        3. Append to Daily Journal.
        4. Update Session.summary.
        """
        session = self.sessions.current
        # Prune ~10 messages at a time or enough to free 20%
        pruned = session.prune_oldest(keep_last=10)
        if not pruned:
            return

        # Format for summarization
        text_block = "\n".join([f"{m['role']}: {m['content']}" for m in pruned])
        
        # 1. Summarize
        try:
            prompt = f"请总结以下对话片段，提取关键信息（意图、操作、结果），作为'前情提要'。保留关键事实，去除闲聊。\n\n{text_block}"
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=500,
            )
            summary_text = resp.choices[0].message.content
        except Exception as e:
            print(f"[System] 总结失败: {e}")
            summary_text = "(Summary failed)"

        # 2. Update Session Summary (append new summary to old)
        if session.summary:
            session.summary += f"\n- {summary_text}"
        else:
            session.summary = summary_text

        # 3. Append to Journal
        journal_entry = f"**[Rolling Summary]**\n{text_block}\n\n**[AI Summary]**: {summary_text}"
        self.journal.append(journal_entry)
        
        print(f"[System] 滚动总结完成。已归档 {len(pruned)} 条消息到日志。")
        self.sessions.save()


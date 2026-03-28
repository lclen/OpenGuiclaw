"""ChatRuntime / ToolRuntime: 将聊天编排与工具选择从 Agent 中拆出。"""

from __future__ import annotations

import asyncio
import json
import threading
from typing import Any


class ToolRuntime:
    """负责工具路由与工具定义选择。"""

    def __init__(self, agent):
        self._agent = agent

    def build_routing_plan(
        self,
        user_query: Any,
        allowed_skills: list[str] = None,
        skills_mode: str = "inclusive",
        workspace_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        agent = self._agent
        query_text = agent._normalize_query_text(user_query)
        visible_skills = agent.skills.list_visible(allowed_skills=allowed_skills, skills_mode=skills_mode)
        if not query_text or not visible_skills:
            return {"preferred_skills": [], "note": ""}
        resolved_workspace_context = agent._resolve_workspace_context(workspace_context)

        normalized_query = query_text.lower()
        scores: dict[str, int] = {}
        reasons: dict[str, list[str]] = {}

        def _add_score(skill_name: str, score: int, reason: str) -> None:
            scores[skill_name] = scores.get(skill_name, 0) + score
            reasons.setdefault(skill_name, []).append(reason)

        local_skill_hits = set(agent._find_relevant_skills(query_text))
        for skill in visible_skills:
            skill_name = str(skill.name or "")
            keys = {
                skill_name.lower(),
                str(skill.category or "").lower(),
                str(skill.plugin_name or "").lower(),
            }
            keys = {key for key in keys if len(key) >= 3}
            if skill_name in local_skill_hits:
                _add_score(skill_name, 3, "命中本地技能目录")
            for key in keys:
                if key and key in normalized_query:
                    _add_score(skill_name, 2, f"查询文本命中 {key}")

        memory_layer_weights = {"preference": 3, "experience": 4}
        for usage_layer, layer_weight in memory_layer_weights.items():
            for memory in agent.memory.search(
                query_text,
                top_k=4,
                usage_layer=usage_layer,
                workspace_id=(resolved_workspace_context or {}).get("workspace_id"),
                workspace_name=(resolved_workspace_context or {}).get("workspace_name"),
            ):
                memory_text = f"{memory.content} {' '.join(memory.tags or [])}".lower()
                for skill in visible_skills:
                    skill_name = str(skill.name or "")
                    candidate_tokens = {
                        skill_name.lower(),
                        str(skill.category or "").lower(),
                        str(skill.plugin_name or "").lower(),
                    }
                    candidate_tokens = {token for token in candidate_tokens if len(token) >= 3}
                    if any(token in memory_text for token in candidate_tokens):
                        _add_score(skill_name, layer_weight, f"{usage_layer} 记忆推荐")

        preferred_skills = [
            skill_name
            for skill_name, score in sorted(scores.items(), key=lambda item: (-item[1], item[0]))
            if score > 0
        ]
        if not preferred_skills:
            return {"preferred_skills": [], "note": ""}

        summary_lines = []
        for skill_name in preferred_skills[:3]:
            skill_reasons = "、".join(dict.fromkeys(reasons.get(skill_name, []))[:2])
            summary_lines.append(f"- `{skill_name}`：{skill_reasons}")

        return {
            "preferred_skills": preferred_skills,
            "note": "# 工具路由提示\n以下工具更适合作为本轮首选：\n" + "\n".join(summary_lines),
        }

    def get_tool_definitions(
        self,
        allowed_skills: list[str] = None,
        skills_mode: str = "inclusive",
        preferred_skills: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        try:
            return self._agent.skills.get_tool_definitions(
                allowed_skills=allowed_skills,
                skills_mode=skills_mode,
                preferred_skills=preferred_skills,
            )
        except TypeError:
            return self._agent.skills.get_tool_definitions(
                allowed_skills=allowed_skills,
                skills_mode=skills_mode,
            )

    def select_tools(
        self,
        user_query: Any,
        allowed_skills: list[str] = None,
        skills_mode: str = "inclusive",
        workspace_context: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        routing_plan = self.build_routing_plan(
            user_query,
            allowed_skills=allowed_skills,
            skills_mode=skills_mode,
            workspace_context=workspace_context,
        )
        tools = self.get_tool_definitions(
            allowed_skills=allowed_skills,
            skills_mode=skills_mode,
            preferred_skills=routing_plan.get("preferred_skills"),
        )
        return routing_plan, tools


class ChatRuntime:
    """负责上下文装配与同步聊天聚合。"""

    def __init__(self, agent):
        self._agent = agent

    def assemble_runtime_context(
        self,
        user_query: Any,
        *,
        session,
        system_prompt_override: str = None,
        allowed_skills: list[str] = None,
        skills_mode: str = "inclusive",
        workspace_context: dict[str, Any] | None = None,
        history_limit: int = 40,
    ) -> dict[str, Any]:
        agent = self._agent
        resolved_workspace_context = agent._resolve_workspace_context(workspace_context, session=session)
        query_text = agent._normalize_query_text(user_query)

        memory_sections: dict[str, str] = {}
        if query_text:
            try:
                memory_sections = agent.memory.build_prompt_sections(
                    query_text,
                    top_k_by_layer={"preference": 2, "context": 3, "experience": 2},
                    workspace_id=(resolved_workspace_context or {}).get("workspace_id"),
                    workspace_name=(resolved_workspace_context or {}).get("workspace_name"),
                )
            except Exception:
                memory_sections = {}

        tool_routing_plan = agent._build_tool_routing_plan(
            user_query,
            allowed_skills=allowed_skills,
            skills_mode=skills_mode,
            workspace_context=resolved_workspace_context,
        )

        return {
            "query_text": query_text,
            "session": session,
            "session_summary": getattr(session, "summary", "") or "",
            "history_messages": session.get_history(max_messages=history_limit, include_summary=False),
            "resolved_workspace_context": resolved_workspace_context,
            "memory_sections": memory_sections,
            "recent_visual_context": agent._build_recent_visual_context(session),
            "recent_tool_context": agent._build_recent_tool_context(session),
            "tool_routing_plan": tool_routing_plan,
            "system_prompt_override": system_prompt_override,
            "allowed_skills": allowed_skills,
            "skills_mode": skills_mode,
        }

    async def collect_stream_response(
        self,
        user_input: str,
        system_prompt_override: str = None,
        allowed_skills: list[str] = None,
        skills_mode: str = "inclusive",
        session_override=None,
        workspace_context: dict[str, Any] | None = None,
    ) -> str:
        chunks: list[str] = []
        waiting_for_user = False

        async for raw_event in self._agent.chat_stream(
            user_input,
            system_prompt_override=system_prompt_override,
            allowed_skills=allowed_skills,
            skills_mode=skills_mode,
            session_override=session_override,
            workspace_context=workspace_context,
        ):
            event = json.loads(raw_event) if isinstance(raw_event, str) else raw_event
            event_type = event.get("type")
            if event_type in {"text_delta", "message_chunk"}:
                chunks.append(str(event.get("content", "")))
            elif event_type == "message":
                chunks.append(str(event.get("content", "")))
            elif event_type == "ask_user_interrupt":
                waiting_for_user = True
            elif event_type == "error":
                raise RuntimeError(str(event.get("content", "Unknown stream error")))

        response = "".join(chunks).strip()
        if waiting_for_user and not response:
            return "（正在等待您做出选择...）"
        return response or "（已完成工具操作，无额外回复。）"

    def run_chat_stream_sync(self, coroutine) -> str:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coroutine)

        result_box: dict[str, str] = {}
        error_box: dict[str, Exception] = {}

        def _runner() -> None:
            try:
                result_box["value"] = asyncio.run(coroutine)
            except Exception as error:
                error_box["error"] = error

        thread = threading.Thread(target=_runner, name="ChatStreamSyncBridge", daemon=True)
        thread.start()
        thread.join()
        if "error" in error_box:
            raise error_box["error"]
        return result_box.get("value", "（已完成工具操作，无额外回复。）")

    def chat(
        self,
        user_input: str,
        system_prompt_override: str = None,
        allowed_skills: list[str] = None,
        skills_mode: str = "inclusive",
        session_override=None,
        workspace_context: dict[str, Any] | None = None,
    ) -> str:
        return self.run_chat_stream_sync(
            self.collect_stream_response(
                user_input,
                system_prompt_override=system_prompt_override,
                allowed_skills=allowed_skills,
                skills_mode=skills_mode,
                session_override=session_override,
                workspace_context=workspace_context,
            )
        )

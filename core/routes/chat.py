"""Chat, Sessions, and Diary API routes."""
import asyncio
import json
import os
import threading
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from core.automation_context import (
    reset_automation_source_context,
    set_automation_source_context,
)
from core.im_bots import is_im_session_id
from core.state import app_state, _APP_BASE, logger, get_profile_store

# ── Active stream registry ────────────────────────────────────────────────────
# Maps workspace_id:session_id -> threading.Event; set the event to request stream abort.
_active_streams: dict[str, threading.Event] = {}
_streams_lock = threading.Lock()

router = APIRouter(tags=["chat"])


# ── Pydantic models ───────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str
    model: Optional[str] = None      # per-request model override
    agent_id: Optional[str] = None   # per-request agent override


# ── Helpers ───────────────────────────────────────────────────────────────────

def _resolve_agent_overrides(request: ChatRequest):
    """Return (system_prompt_override, allowed_skills, skills_mode, orig_model_to_restore)."""
    agent = app_state.get("agent")
    orig_model = None
    system_prompt_override = None
    allowed_skills = None
    skills_mode = "inclusive"

    if request.model:
        orig_model = agent.model
        agent.model = request.model

    if request.agent_id:
        store = get_profile_store()
        profile = store.get(request.agent_id)
        if profile:
            if profile.preferred_model and not request.model:
                orig_model = agent.model
                agent.model = profile.preferred_model
            if profile.custom_prompt:
                system_prompt_override = profile.custom_prompt
            allowed_skills = profile.skills
            skills_mode = profile.skills_mode.value

    return system_prompt_override, allowed_skills, skills_mode, orig_model


def _stream_key(workspace_id: str, session_id: str) -> str:
    return f"{workspace_id}:{session_id}"


# ── Chat endpoints ────────────────────────────────────────────────────────────

@router.post("/api/chat/sync")
async def chat_sync(request: ChatRequest):
    """Synchronous chat endpoint. Blocks until the agent finishes."""
    agent = app_state.get("agent")
    if not agent:
        raise HTTPException(status_code=500, detail="Agent not initialized")

    system_prompt_override, allowed_skills, skills_mode, orig_model = _resolve_agent_overrides(request)
    current_session_id = getattr(getattr(agent, "sessions", None), "current", None)
    source_token = set_automation_source_context(
        source_kind="desktop",
        source_session_id=getattr(current_session_id, "session_id", None),
    )
    try:
        response = agent.chat(
            request.message,
            system_prompt_override=system_prompt_override,
            allowed_skills=allowed_skills,
            skills_mode=skills_mode,
        )
        return {"response": response}
    except Exception as e:
        logger.error(f"Chat error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Chat error: {str(e)}")
    finally:
        reset_automation_source_context(source_token)
        if orig_model is not None:
            agent.model = orig_model


@router.post("/api/chat/upload")
async def chat_upload(files: list[UploadFile] = File(...), prompt: str = Form(default="")):
    """Accept multiple image or text files and stream the agent response via SSE."""
    agent = app_state.get("agent")
    if not agent:
        raise HTTPException(status_code=500, detail="Agent not initialized")

    user_content_list = []
    
    for file in files:
        if not file.filename:
            continue
            
        content_type = (file.content_type or "").lower()
        raw = await file.read()

        if content_type.startswith("image/"):
            import base64
            b64 = base64.b64encode(raw).decode("utf-8")
            data_url = f"data:{content_type};base64,{b64}"
            user_content_list.append({"type": "image_url", "image_url": {"url": data_url}})
        elif content_type.startswith("text/") or file.filename.lower().endswith(
            (".txt", ".md", ".csv", ".log", ".py", ".js", ".html", ".css", ".json")
        ):
            try:
                text_body = raw.decode("utf-8", errors="replace")
            except Exception:
                text_body = raw.decode("latin-1", errors="replace")
            
            # 限制单个文件长度防止过载
            text_body_trunc = text_body[:8000]
            if len(text_body) > 8000:
                text_body_trunc += f"\n... (截断，剩余 {len(text_body)-8000} 字符)"
                
            user_content_list.append(
                {"type": "text", "text": f"【文件内容：{file.filename}】\n```\n{text_body_trunc}\n```\n\n"}
            )
        else:
            # 对于不支持的文件，我们可以记录一条提示或者抛出异常。
            # 这里选择将其内容尝试解析，或者直接给出文件名提示
            user_content_list.append(
                {"type": "text", "text": f"【附件：{file.filename} (内容不支持直接查阅，类型: {content_type})】\n\n"}
            )
            
    # Combine texts and images
    final_content = []
    text_parts = []
    
    for item in user_content_list:
        if item["type"] == "text":
            text_parts.append(item["text"])
        else:
            final_content.append(item)
            
    # Append the user prompt
    if prompt.strip():
        text_parts.append(prompt)
    elif not text_parts and final_content:
        text_parts.append("请分析以上内容。")
        
    if text_parts:
        final_content.append({"type": "text", "text": "".join(text_parts)})
        
    # 如果只有纯文本部分，降级为字符串格式，不使用 multimodal list 以适配更多模型
    if len(final_content) == 1 and final_content[0]["type"] == "text":
        user_content = final_content[0]["text"]
    else:
        user_content = final_content

    async def event_generator():
        try:
            async for chunk in agent.chat_stream(user_content):
                yield dict(data=chunk)
            yield dict(data="[DONE]")
        except Exception as e:
            logger.error(f"Upload stream error: {e}")
            yield dict(data=json.dumps({"type": "error", "content": str(e)}))

    return EventSourceResponse(event_generator())


@router.post("/api/chat/stream")
async def chat_stream(request: ChatRequest):
    """Streaming chat endpoint via Server-Sent Events."""
    agent = app_state.get("agent")
    if not agent:
        raise HTTPException(status_code=500, detail="Agent not initialized")

    system_prompt_override, allowed_skills, skills_mode, orig_model = _resolve_agent_overrides(request)

    async def event_generator():
        current_session = getattr(getattr(agent, "sessions", None), "current", None)
        source_token = set_automation_source_context(
            source_kind="desktop",
            source_session_id=getattr(current_session, "session_id", None),
        )
        try:
            async for chunk in agent.chat_stream(
                request.message,
                system_prompt_override=system_prompt_override,
                allowed_skills=allowed_skills,
                skills_mode=skills_mode,
            ):
                yield dict(data=chunk)
            yield dict(data="[DONE]")
        except Exception as e:
            logger.error(f"Streaming error: {e}")
            yield dict(data=json.dumps({"type": "error", "content": str(e)}))
        finally:
            reset_automation_source_context(source_token)
            if orig_model is not None:
                agent.model = orig_model

    return EventSourceResponse(event_generator())


# ── Sessions ──────────────────────────────────────────────────────────────────

@router.get("/api/sessions")
async def list_sessions():
    """Return a summary list of all past sessions (most recent first, max 30)."""
    sessions_dir = str(_APP_BASE / "data" / "sessions")
    if not os.path.exists(sessions_dir):
        return []
    result = []
    for fname in sorted(os.listdir(sessions_dir), reverse=True):
        if not fname.endswith(".json") or is_im_session_id(fname[:-5]):
            continue
        fpath = os.path.join(sessions_dir, fname)
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)
            messages = data.get("messages", [])
            title = next(
                (
                    (
                        m["content"]
                        if isinstance(m["content"], str)
                        else " ".join(
                            p.get("text", "")
                            for p in m["content"]
                            if isinstance(p, dict) and p.get("type") == "text"
                        )
                    )[:40]
                    for m in messages
                    if m.get("role") == "user" and m.get("content")
                ),
                "(空对话)",
            )
            result.append({
                "id": fname.replace(".json", ""),
                "title": title,
                "message_count": len([m for m in messages if m.get("role") in ("user", "assistant")]),
                "created_at": data.get("created_at", ""),
            })
        except Exception:
            continue
    return result[:30]


@router.post("/api/sessions/new")
async def new_session():
    """Start a fresh session."""
    agent = app_state.get("agent")
    if not agent:
        raise HTTPException(status_code=500, detail="Agent not initialized")
    agent.sessions.new_session()
    agent.sessions.save()
    session_id = getattr(agent.sessions.current, "session_id", "unknown")
    return {"status": "ok", "session_id": session_id}


@router.get("/api/sessions/current/info")
async def get_current_session():
    """Return the current active session ID."""
    agent = app_state.get("agent")
    if not agent:
        raise HTTPException(status_code=503, detail="Agent not ready")
    session_id = getattr(agent.sessions.current, "session_id", None)
    if not session_id:
        raise HTTPException(status_code=404, detail="No active session")
    return {"session_id": session_id}


@router.get("/api/sessions/{session_id}")
async def get_session(session_id: str):
    """Return the chat messages of a specific session."""
    agent = app_state.get("agent")
    if not agent:
        raise HTTPException(status_code=500, detail="Backend agent is not initialized.")
        
    # 同步切换后端的当前会话指针
    data = agent.sessions.load(session_id)
    if not data:
        raise HTTPException(status_code=404, detail="Session not found")
    data = data.to_dict() if hasattr(data, "to_dict") else data
    EXCLUDED_ROLES = {"system"}
    messages = [m for m in data.get("messages", []) if m.get("role") not in EXCLUDED_ROLES]

    # Estimate token count using the same logic as Session.estimate_tokens()
    import re
    _cjk_re = re.compile(r'[\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]')
    def _count(text: str) -> int:
        cjk = len(_cjk_re.findall(text))
        return cjk + (len(text) - cjk) // 4

    estimated_tokens = _count(data.get("summary", ""))
    for m in data.get("messages", []):
        if m.get("role") == "debug_log":
            continue
        content = m.get("content", "")
        if isinstance(content, str):
            estimated_tokens += _count(content)
        elif isinstance(content, list):
            for item in content:
                if isinstance(item, dict):
                    if item.get("type") == "text":
                        estimated_tokens += _count(item.get("text", ""))
                    elif item.get("type") == "image_url":
                        estimated_tokens += 1000
        if m.get("tool_calls"):
            try:
                estimated_tokens += _count(json.dumps(m["tool_calls"], ensure_ascii=False))
            except Exception:
                pass

    return {"session_id": session_id, "messages": messages, "estimated_tokens": estimated_tokens}


@router.delete("/api/sessions/{session_id}")
async def delete_session(session_id: str):
    """Delete a specific session file."""
    fpath = str(_APP_BASE / "data" / "sessions" / f"{session_id}.json")
    if not os.path.exists(fpath):
        raise HTTPException(status_code=404, detail="Session not found")
    try:
        os.remove(fpath)
        return {"status": "ok", "message": f"Session {session_id} deleted."}
    except Exception as e:
        logger.error(f"Failed to delete session {session_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── Diary ─────────────────────────────────────────────────────────────────────

@router.get("/api/diary")
async def list_diary():
    """Return a list of available diary dates."""
    diary_dir = str(_APP_BASE / "data" / "diary")
    if not os.path.exists(diary_dir):
        return []
    return sorted(
        [f.replace(".md", "") for f in os.listdir(diary_dir) if f.endswith(".md")],
        reverse=True,
    )


@router.get("/api/diary/{date}")
async def get_diary(date: str):
    """Return the content of a diary entry."""
    fpath = str(_APP_BASE / "data" / "diary" / f"{date}.md")
    if not os.path.exists(fpath):
        raise HTTPException(status_code=404, detail="Diary not found")
    with open(fpath, "r", encoding="utf-8") as f:
        content = f.read()
    return {"date": date, "content": content}


# ── Workspace-scoped session endpoints (Task 3) ───────────────────────────────

class WorkspaceChatRequest(BaseModel):
    message: str
    workspace_id: str
    session_id: Optional[str] = None
    model: Optional[str] = None
    agent_id: Optional[str] = None


def _ws_sessions_dir(workspace_id: str):
    """Return the sessions directory for a workspace, creating it if needed."""
    from core.workspace_manager import get_workspace_manager, WorkspaceNotFoundError
    wm = get_workspace_manager()
    try:
        wm.get_workspace(workspace_id)
    except WorkspaceNotFoundError:
        raise HTTPException(status_code=404, detail=f"Workspace not found: {workspace_id}")
    from pathlib import Path
    sessions_dir = Path(wm._workspaces_dir) / workspace_id / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)
    return sessions_dir


def _load_ws_session_data(workspace_id: str, session_id: str) -> dict:
    """Load a session JSON from a workspace's sessions directory."""
    sessions_dir = _ws_sessions_dir(workspace_id)
    path = sessions_dir / f"{session_id}.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_ws_session_data(workspace_id: str, session_data: dict):
    """Persist a session dict ONLY to the workspace's sessions directory."""
    sessions_dir = _ws_sessions_dir(workspace_id)
    session_id = session_data["session_id"]
    path = sessions_dir / f"{session_id}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(session_data, f, ensure_ascii=False, indent=2)


@router.post("/api/workspaces/{workspace_id}/sessions/new")
async def new_workspace_session(workspace_id: str):
    """在指定工作区创建新线程（不修改全局 agent session）。"""
    from core.session import Session
    _ws_sessions_dir(workspace_id)  # validate workspace exists
    session = Session()
    _save_ws_session_data(workspace_id, session.to_dict())
    return {"status": "ok", "workspace_id": workspace_id, "session_id": session.session_id}


@router.get("/api/workspaces/{workspace_id}/sessions/{session_id}/messages")
async def get_workspace_session_messages(workspace_id: str, session_id: str):
    """返回工作区内指定线程的消息列表。"""
    data = _load_ws_session_data(workspace_id, session_id)
    EXCLUDED_ROLES = {"system", "visual_log", "debug_log"}
    messages = [m for m in data.get("messages", []) if m.get("role") not in EXCLUDED_ROLES]
    return {
        "workspace_id": workspace_id,
        "session_id": session_id,
        "messages": messages,
        "created_at": data.get("created_at", ""),
        "updated_at": data.get("updated_at", ""),
    }


@router.post("/api/workspaces/{workspace_id}/sessions/{session_id}/load")
async def load_workspace_session(workspace_id: str, session_id: str):
    """
    旧版兼容端点，已废弃。
    Workspace shell 应改用 /messages 与 /stream。
    """
    raise HTTPException(
        status_code=410,
        detail="Deprecated endpoint. Use /api/workspaces/{workspace_id}/sessions/{session_id}/messages and /stream instead.",
    )


@router.post("/api/workspaces/{workspace_id}/sessions/{session_id}/stream")
async def stream_workspace_chat(workspace_id: str, session_id: str, request: WorkspaceChatRequest):
    """
    在指定工作区线程中发起流式聊天。

    关键设计：
    - 使用独立的 Session 对象，不修改全局 agent.sessions._current
    - 所有 session 读写只操作 workspace 目录，不写全局 data/sessions/
    - 并发请求各自持有独立 session 副本，互不干扰
    """
    agent = app_state.get("agent")
    if not agent:
        raise HTTPException(status_code=500, detail="Agent not initialized")

    # Load session data from workspace directory (not global sessions)
    session_data = _load_ws_session_data(workspace_id, session_id)

    from core.session import Session
    # Each request gets its own Session copy — no shared mutable state
    session = Session.from_dict(session_data)
    agent.ensure_session_skills_current(session)

    # Per-request model/agent overrides
    model = request.model or agent.model
    system_prompt_override = None
    allowed_skills = None
    skills_mode = "inclusive"

    if request.agent_id:
        store = get_profile_store()
        profile = store.get(request.agent_id)
        if profile:
            if profile.preferred_model and not request.model:
                model = profile.preferred_model
            if profile.custom_prompt:
                system_prompt_override = profile.custom_prompt
            allowed_skills = profile.skills
            skills_mode = profile.skills_mode.value

    # Register abort event for this session
    stream_key = _stream_key(workspace_id, session_id)
    abort_event = threading.Event()
    with _streams_lock:
        if stream_key in _active_streams:
            raise HTTPException(
                status_code=409,
                detail="Another stream is already active for this workspace session.",
            )
        _active_streams[stream_key] = abort_event

    async def event_generator():
        nonlocal session
        source_token = set_automation_source_context(
            source_kind="desktop",
            source_session_id=session_id,
        )
        try:
            # Build system prompt using agent's method (reads persona, memory, etc.)
            system_prompt = agent._build_system_prompt(
                request.message,
                system_prompt_override=system_prompt_override,
                allowed_skills=allowed_skills,
                skills_mode=skills_mode,
            )

            # Persist user message to local session copy
            import re as _re
            cleaned = _re.sub(r'【文件内容：[^】]+】\n```[^\n]*\n.*?```\n*', '', request.message, flags=_re.DOTALL)
            cleaned = _re.sub(r'【附件：[^】]+】\n*', '', cleaned).strip()
            session.add_message("user", cleaned or request.message)

            messages = [{"role": "system", "content": system_prompt}]
            messages.extend(session.get_history(max_messages=40))

            tools = agent.skills.get_tool_definitions(allowed_skills=allowed_skills, skills_mode=skills_mode)

            import copy
            max_rounds = 15
            full_content = ""

            for _ in range(max_rounds):
                if abort_event.is_set():
                    yield dict(data=json.dumps({"type": "aborted"}))
                    return

                yield dict(data=json.dumps({"type": "status", "content": "思考中..."}))

                loop = asyncio.get_event_loop()
                response = await loop.run_in_executor(
                    None,
                    lambda: agent.client.chat.completions.create(
                        model=model,
                        messages=messages,
                        tools=tools if tools else None,
                        tool_choice="auto" if tools else None,
                        max_tokens=agent.max_tokens,
                        temperature=agent.temperature,
                        **({"extra_body": {"enable_search": True}} if agent._qwen_search_enabled else {}),
                        stream=False,
                    )
                )
                agent._record_usage(getattr(response, "usage", None), model)

                msg = response.choices[0].message
                msg_content = msg.content or ""

                if msg_content:
                    full_content += msg_content
                    yield dict(data=json.dumps({"type": "message_chunk", "content": msg_content}))

                if msg.tool_calls:
                    assistant_dict = msg.model_dump(exclude_unset=True)
                    for tc_dict in assistant_dict.get("tool_calls") or []:
                        raw_args = tc_dict.get("function", {}).get("arguments", "{}")
                        try:
                            json.loads(raw_args)
                        except (json.JSONDecodeError, TypeError):
                            tc_dict["function"]["arguments"] = "{}"

                    messages.append(assistant_dict)
                    session.add_message(
                        role="assistant",
                        content=msg_content,
                        tool_calls=assistant_dict.get("tool_calls"),
                    )

                    for tc in msg.tool_calls:
                        if abort_event.is_set():
                            yield dict(data=json.dumps({"type": "aborted"}))
                            return

                        name = tc.function.name
                        try:
                            params = json.loads(tc.function.arguments)
                            if not isinstance(params, dict):
                                params = {}
                        except Exception:
                            params = {}

                        yield dict(data=json.dumps({"type": "tool_call", "id": tc.id, "name": name, "params": params}))

                        try:
                            result = await agent.skills.execute(name, params)
                            if not isinstance(result, str):
                                result = str(result)
                        except Exception as e:
                            result = f"❌ 执行出错: {e}"

                        if len(result) > 12000:
                            result = result[:12000] + f"\n[截断，原长 {len(result)} 字符]"

                        yield dict(data=json.dumps({"type": "tool_result", "id": tc.id, "name": name,
                                                    "result": result[:500] + "..." if len(result) > 500 else result}))

                        tool_msg = {"role": "tool", "tool_call_id": tc.id, "name": name, "content": result}
                        messages.append(tool_msg)
                        session.add_message(**tool_msg)

                    continue

                # Final text response
                session.add_message("assistant", msg_content)
                yield dict(data=json.dumps({"type": "message", "content": ""}))
                break

            else:
                session.add_message("assistant", "（已完成工具操作，无额外回复。）")
                yield dict(data=json.dumps({"type": "message", "content": ""}))

            yield dict(data="[DONE]")

        except Exception as e:
            logger.error(f"Workspace stream error [{workspace_id}/{session_id}]: {e}")
            yield dict(data=json.dumps({"type": "error", "content": str(e)}))
        finally:
            reset_automation_source_context(source_token)
            # Write session ONLY to workspace directory — never to global data/sessions/
            try:
                _save_ws_session_data(workspace_id, session.to_dict())
            except Exception as save_err:
                logger.warning(f"Failed to save workspace session: {save_err}")
            with _streams_lock:
                _active_streams.pop(stream_key, None)

    return EventSourceResponse(event_generator())


@router.post("/api/workspaces/{workspace_id}/sessions/{session_id}/abort")
async def abort_workspace_stream(workspace_id: str, session_id: str):
    """
    请求中止指定线程的进行中流式任务。
    前端在切换工作区前调用此接口，避免状态串写。
    """
    stream_key = _stream_key(workspace_id, session_id)
    with _streams_lock:
        event = _active_streams.get(stream_key)
    if event:
        event.set()
        return {"status": "ok", "message": f"Abort requested for session {session_id}"}
    return {"status": "ok", "message": "No active stream for this session"}

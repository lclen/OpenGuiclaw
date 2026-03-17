"""Workspace API routes — Task 2.1 ~ 2.5.

Endpoints:
  GET    /api/workspaces                              — 非归档工作区列表
  GET    /api/workspaces/archived                     — 归档工作区列表
  POST   /api/workspaces                              — 创建工作区
  GET    /api/workspaces/{workspace_id}               — 工作区详情
  PATCH  /api/workspaces/{workspace_id}               — 更新工作区
  DELETE /api/workspaces/{workspace_id}               — 归档工作区（软删除）
  POST   /api/workspaces/{workspace_id}/unarchive     — 恢复工作区
  GET    /api/workspaces/{workspace_id}/sessions      — 线程列表
  POST   /api/workspaces/{workspace_id}/sessions/{session_id}/archive   — 归档线程
  POST   /api/workspaces/{workspace_id}/sessions/{session_id}/pin       — 置顶线程
  POST   /api/workspaces/{workspace_id}/sessions/{session_id}/unpin     — 取消置顶线程
  POST   /api/workspaces/{workspace_id}/sessions/{session_id}/unarchive — 恢复线程
  DELETE /api/workspaces/{workspace_id}/sessions/{session_id}           — 永久删除线程
  GET    /api/workspaces/{workspace_id}/files         — 文件树
  GET    /api/home                                    — Global Home 总览数据
"""
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from core.workspace_manager import (
    DuplicateWorkspacePathError,
    WorkspaceNotFoundError,
    WorkspacePathError,
    get_workspace_manager,
)

router = APIRouter(tags=["workspace"])


# ── Request / Response models ─────────────────────────────────────────────────

class CreateWorkspaceRequest(BaseModel):
    name: str
    workspace_path: str


class UpdateWorkspaceRequest(BaseModel):
    name: Optional[str] = None
    workspace_path: Optional[str] = None
    persona_file: Optional[str] = None
    model_overrides: Optional[Dict[str, Any]] = None  # renamed from model_config


# ── Helpers ───────────────────────────────────────────────────────────────────

def _wm():
    return get_workspace_manager()


def _not_found(workspace_id: str):
    raise HTTPException(status_code=404, detail=f"Workspace not found: {workspace_id}")


# ── Workspace endpoints ───────────────────────────────────────────────────────

@router.get("/api/workspaces")
async def list_workspaces():
    """返回所有非归档工作区列表，每项附带 thread_count。"""
    wm = _wm()
    workspaces = wm.list_workspaces(include_archived=False)
    result = []
    for ws in workspaces:
        try:
            thread_count = wm.count_sessions(ws.id, include_archived=False)
        except Exception:
            thread_count = 0
        item = ws.model_dump()
        item["thread_count"] = thread_count
        result.append(item)
    return result


@router.get("/api/workspaces/archived")
async def list_archived_workspaces():
    """返回所有已归档工作区列表。"""
    wm = _wm()
    all_ws = wm.list_workspaces(include_archived=True)
    return [w.model_dump() for w in all_ws if w.archived]


@router.post("/api/workspaces", status_code=201)
async def create_workspace(body: CreateWorkspaceRequest):
    """创建新工作区。"""
    wm = _wm()
    try:
        info = wm.create_workspace(name=body.name, workspace_path=body.workspace_path)
        return info.model_dump()
    except WorkspacePathError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except DuplicateWorkspacePathError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.get("/api/workspaces/{workspace_id}")
async def get_workspace(workspace_id: str):
    """返回单个工作区详情。"""
    wm = _wm()
    try:
        info = wm.get_workspace(workspace_id)
        return info.model_dump()
    except WorkspaceNotFoundError:
        _not_found(workspace_id)


@router.patch("/api/workspaces/{workspace_id}")
async def update_workspace(workspace_id: str, body: UpdateWorkspaceRequest):
    """更新工作区字段（name / workspace_path / persona_file / model_config）。"""
    wm = _wm()
    fields = {k: v for k, v in body.model_dump().items() if v is not None}
    if not fields:
        raise HTTPException(status_code=400, detail="No fields to update")
    try:
        info = wm.update_workspace(workspace_id, **fields)
        return info.model_dump()
    except WorkspaceNotFoundError:
        _not_found(workspace_id)
    except WorkspacePathError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except DuplicateWorkspacePathError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.delete("/api/workspaces/{workspace_id}")
async def archive_workspace(workspace_id: str):
    """软删除工作区（archived=true），数据文件保留。"""
    wm = _wm()
    try:
        wm.archive_workspace(workspace_id)
        return {"status": "ok", "workspace_id": workspace_id}
    except WorkspaceNotFoundError:
        _not_found(workspace_id)


@router.post("/api/workspaces/{workspace_id}/unarchive")
async def unarchive_workspace(workspace_id: str):
    """恢复已归档工作区。"""
    wm = _wm()
    try:
        wm.unarchive_workspace(workspace_id)
        return {"status": "ok", "workspace_id": workspace_id}
    except WorkspaceNotFoundError:
        _not_found(workspace_id)
    except DuplicateWorkspacePathError as e:
        raise HTTPException(status_code=409, detail=str(e))


# ── Session endpoints ─────────────────────────────────────────────────────────

@router.get("/api/workspaces/{workspace_id}/sessions")
async def list_workspace_sessions(
    workspace_id: str,
    include_archived: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=200),
):
    """返回工作区线程列表，按 updated_at 倒序，默认最多 50 条。"""
    wm = _wm()
    try:
        sessions = wm.list_sessions(
            workspace_id=workspace_id,
            include_archived=include_archived,
            limit=limit,
        )
        return [s.model_dump() for s in sessions]
    except WorkspaceNotFoundError:
        _not_found(workspace_id)


@router.post("/api/workspaces/{workspace_id}/sessions/{session_id}/archive")
async def archive_session(workspace_id: str, session_id: str):
    """归档指定线程。"""
    wm = _wm()
    try:
        wm.archive_session(workspace_id, session_id)
        return {"status": "ok", "session_id": session_id}
    except WorkspaceNotFoundError:
        _not_found(workspace_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")


@router.post("/api/workspaces/{workspace_id}/sessions/{session_id}/pin")
async def pin_session(workspace_id: str, session_id: str):
    """置顶指定线程。"""
    wm = _wm()
    try:
        wm.set_session_pinned(workspace_id, session_id, True)
        return {"status": "ok", "session_id": session_id, "pinned": True}
    except WorkspaceNotFoundError:
        _not_found(workspace_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")


@router.post("/api/workspaces/{workspace_id}/sessions/{session_id}/unpin")
async def unpin_session(workspace_id: str, session_id: str):
    """取消置顶指定线程。"""
    wm = _wm()
    try:
        wm.set_session_pinned(workspace_id, session_id, False)
        return {"status": "ok", "session_id": session_id, "pinned": False}
    except WorkspaceNotFoundError:
        _not_found(workspace_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")


@router.post("/api/workspaces/{workspace_id}/sessions/{session_id}/unarchive")
async def unarchive_session(workspace_id: str, session_id: str):
    """恢复已归档线程。"""
    wm = _wm()
    try:
        wm.unarchive_session(workspace_id, session_id)
        return {"status": "ok", "session_id": session_id}
    except WorkspaceNotFoundError:
        _not_found(workspace_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")


@router.delete("/api/workspaces/{workspace_id}/sessions/{session_id}")
async def delete_session(workspace_id: str, session_id: str):
    """永久删除已归档线程（物理删除文件）。未归档线程不允许直接删除。"""
    wm = _wm()
    try:
        wm.delete_session(workspace_id, session_id)
        return {"status": "ok", "session_id": session_id}
    except WorkspaceNotFoundError:
        _not_found(workspace_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


# ── File tree endpoint ────────────────────────────────────────────────────────

@router.get("/api/workspaces/{workspace_id}/files")
async def get_workspace_files(
    workspace_id: str,
    max_depth: int = Query(default=3, ge=1, le=5),
):
    """返回工作区 workspace_path 的文件树，最大深度 3。"""
    wm = _wm()
    try:
        tree = wm.get_file_tree(workspace_id, max_depth=max_depth)
        return [node.model_dump() for node in tree]
    except WorkspaceNotFoundError:
        _not_found(workspace_id)
    except WorkspacePathError as e:
        raise HTTPException(status_code=422, detail=str(e))


# ── Global Home endpoint ──────────────────────────────────────────────────────

@router.get("/api/home")
async def get_home():
    """Global Home 总览数据：最近工作区 + 每个工作区最近线程。"""
    wm = _wm()
    workspaces = wm.list_workspaces(include_archived=False)

    recent_workspaces: List[Dict[str, Any]] = []
    for ws in workspaces[:10]:
        try:
            sessions = wm.list_sessions(ws.id, include_archived=False, limit=5)
        except Exception:
            sessions = []
        recent_workspaces.append({
            **ws.model_dump(),
            "recent_sessions": [s.model_dump() for s in sessions],
        })

    return {
        "workspaces": recent_workspaces,
        "total_workspaces": len(workspaces),
    }

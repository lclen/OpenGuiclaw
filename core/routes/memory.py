"""Memory & Persona API routes."""
import os
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.state import app_state, _APP_BASE

router = APIRouter(tags=["memory"])


# ── Pydantic models ───────────────────────────────────────────────────────────

class MemoryCreateRequest(BaseModel):
    content: str
    type: Optional[str] = "fact"
    tags: Optional[list] = []


class MemoryUpdateRequest(BaseModel):
    content: Optional[str] = None
    type: Optional[str] = None
    tags: Optional[list] = None


class MemoryBatchDeleteRequest(BaseModel):
    ids: list[str]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _require_memory():
    agent = app_state.get("agent")
    if not agent or not agent.memory:
        raise HTTPException(status_code=503, detail="Memory not available")
    return agent


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/api/memory")
async def list_memory(type: Optional[str] = None, q: Optional[str] = None):
    """Return memory items, optionally filtered by type or keyword."""
    agent = app_state.get("agent")
    if not agent or not agent.memory:
        return {"memories": []}
    items = agent.memory.list_by_type(type) if type else agent.memory.list_all()
    if q:
        q_lower = q.lower()
        items = [m for m in items if q_lower in m.content.lower()]
    return {"memories": [m.to_dict() for m in items]}


@router.post("/api/memory")
async def create_memory(req: MemoryCreateRequest):
    """Create a new memory item."""
    agent = _require_memory()
    item = agent.memory.add(req.content, tags=req.tags, type=req.type)
    return {"memory": item.to_dict()}


@router.delete("/api/memory/{memory_id}")
async def delete_memory(memory_id: str):
    """Delete a memory item by ID."""
    agent = _require_memory()
    if not agent.memory.delete(memory_id):
        raise HTTPException(status_code=404, detail="Memory not found")
    return {"status": "success"}


@router.put("/api/memory/{memory_id}")
async def update_memory(memory_id: str, req: MemoryUpdateRequest):
    """Update a memory item's content, type, or tags."""
    agent = _require_memory()
    ok = agent.memory.update(
        memory_id,
        new_content=req.content,
        new_tags=req.tags,
        new_type=req.type,
    )
    if not ok:
        raise HTTPException(status_code=404, detail="Memory not found")
    return {"status": "success"}


@router.post("/api/memory/batch_delete")
async def batch_delete_memory(req: MemoryBatchDeleteRequest):
    """Batch delete memories."""
    agent = _require_memory()
    deleted_count = sum(1 for mid in req.ids if agent.memory.delete(mid))
    return {"status": "success", "deleted_count": deleted_count}


@router.get("/api/persona")
async def get_persona():
    """Return all identity files as a name→content dict."""
    identities_dir = str(_APP_BASE / "data" / "identities")
    result = {}
    if os.path.exists(identities_dir):
        for fname in os.listdir(identities_dir):
            if fname.endswith(".md"):
                with open(os.path.join(identities_dir, fname), "r", encoding="utf-8") as f:
                    result[fname.replace(".md", "")] = f.read()
    return result

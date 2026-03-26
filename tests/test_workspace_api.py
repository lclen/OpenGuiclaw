"""
tests/test_workspace_api.py
============================
Workspace REST API 集成测试（AsyncClient + ASGITransport，无需启动真实服务器）。

运行：
    pytest tests/test_workspace_api.py -v
"""

import json
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI

from core.workspace_manager import WorkspaceManager


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def wm(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    return WorkspaceManager(data_dir=data_dir)


@pytest_asyncio.fixture
async def client(wm):
    """AsyncClient backed by ASGITransport — works with httpx 0.28 + starlette 0.27."""
    from core.routes.workspace import router

    app = FastAPI()
    app.include_router(router)

    with patch("core.routes.workspace.get_workspace_manager", return_value=wm):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as c:
            yield c


@pytest.fixture
def ws_path(tmp_path):
    p = tmp_path / "project"
    p.mkdir()
    return p


@pytest.fixture
def ws_path2(tmp_path):
    p = tmp_path / "project2"
    p.mkdir()
    return p


# ── Helpers ───────────────────────────────────────────────────────────────────

async def create_ws(client, ws_path, name="Test WS"):
    r = await client.post("/api/workspaces", json={"name": name, "workspace_path": str(ws_path)})
    assert r.status_code == 201, r.text
    return r.json()


def make_session(wm, ws_id, session_id="sess_test", archived=False):
    sessions_dir = wm._sessions_dir(ws_id)
    sessions_dir.mkdir(parents=True, exist_ok=True)
    data = {
        "session_id": session_id,
        "created_at": "2025-01-01T00:00:00Z",
        "updated_at": "2025-01-01T00:00:00Z",
        "archived": archived,
        "messages": [{"role": "user", "content": "Hello"}],
    }
    (sessions_dir / f"{session_id}.json").write_text(json.dumps(data), encoding="utf-8")
    return data


# ── GET /api/workspaces ───────────────────────────────────────────────────────

class TestListWorkspaces:

    async def test_empty_list(self, client):
        r = await client.get("/api/workspaces")
        assert r.status_code == 200
        assert r.json() == []

    async def test_returns_active_workspaces(self, client, wm, ws_path, ws_path2):
        ws1 = await create_ws(client, ws_path, "WS1")
        ws2 = await create_ws(client, ws_path2, "WS2")
        wm.archive_workspace(ws2["id"])

        r = await client.get("/api/workspaces")
        assert r.status_code == 200
        ids = [w["id"] for w in r.json()]
        assert ws1["id"] in ids
        assert ws2["id"] not in ids

    async def test_includes_thread_count(self, client, wm, ws_path):
        ws = await create_ws(client, ws_path)
        make_session(wm, ws["id"], "sess_1")
        make_session(wm, ws["id"], "sess_2")

        r = await client.get("/api/workspaces")
        ws_data = next(w for w in r.json() if w["id"] == ws["id"])
        assert ws_data["thread_count"] == 2


# ── GET /api/workspaces/archived ──────────────────────────────────────────────

class TestListArchivedWorkspaces:

    async def test_empty_when_none_archived(self, client, ws_path):
        await create_ws(client, ws_path)
        r = await client.get("/api/workspaces/archived")
        assert r.status_code == 200
        assert r.json() == []

    async def test_returns_archived_only(self, client, wm, ws_path, ws_path2):
        ws1 = await create_ws(client, ws_path, "WS1")
        ws2 = await create_ws(client, ws_path2, "WS2")
        wm.archive_workspace(ws2["id"])

        r = await client.get("/api/workspaces/archived")
        ids = [w["id"] for w in r.json()]
        assert ws2["id"] in ids
        assert ws1["id"] not in ids


# ── POST /api/workspaces ──────────────────────────────────────────────────────

class TestCreateWorkspace:

    async def test_create_success(self, client, ws_path):
        r = await client.post("/api/workspaces", json={"name": "New WS", "workspace_path": str(ws_path)})
        assert r.status_code == 201
        data = r.json()
        assert data["name"] == "New WS"
        assert data["archived"] is False

    async def test_create_invalid_path(self, client, tmp_path):
        r = await client.post("/api/workspaces", json={
            "name": "Bad",
            "workspace_path": str(tmp_path / "nonexistent"),
        })
        assert r.status_code == 422

    async def test_create_duplicate_path(self, client, ws_path):
        await create_ws(client, ws_path, "WS1")
        r = await client.post("/api/workspaces", json={"name": "WS2", "workspace_path": str(ws_path)})
        assert r.status_code == 409


# ── GET /api/workspaces/{id} ──────────────────────────────────────────────────

class TestGetWorkspace:

    async def test_get_existing(self, client, ws_path):
        ws = await create_ws(client, ws_path)
        r = await client.get(f"/api/workspaces/{ws['id']}")
        assert r.status_code == 200
        assert r.json()["id"] == ws["id"]

    async def test_get_not_found(self, client):
        r = await client.get("/api/workspaces/ws_ghost")
        assert r.status_code == 404


# ── PATCH /api/workspaces/{id} ────────────────────────────────────────────────

class TestUpdateWorkspace:

    async def test_update_name(self, client, ws_path):
        ws = await create_ws(client, ws_path)
        r = await client.patch(f"/api/workspaces/{ws['id']}", json={"name": "Renamed"})
        assert r.status_code == 200
        assert r.json()["name"] == "Renamed"

    async def test_update_no_fields(self, client, ws_path):
        ws = await create_ws(client, ws_path)
        r = await client.patch(f"/api/workspaces/{ws['id']}", json={})
        assert r.status_code == 400

    async def test_update_not_found(self, client):
        r = await client.patch("/api/workspaces/ws_ghost", json={"name": "X"})
        assert r.status_code == 404


# ── DELETE /api/workspaces/{id} (archive) ────────────────────────────────────

class TestArchiveWorkspace:

    async def test_archive(self, client, wm, ws_path):
        ws = await create_ws(client, ws_path)
        r = await client.delete(f"/api/workspaces/{ws['id']}")
        assert r.status_code == 200
        assert wm.get_workspace(ws["id"]).archived is True

    async def test_archive_not_found(self, client):
        r = await client.delete("/api/workspaces/ws_ghost")
        assert r.status_code == 404


# ── POST /api/workspaces/{id}/unarchive ──────────────────────────────────────

class TestUnarchiveWorkspace:

    async def test_unarchive(self, client, wm, ws_path):
        ws = await create_ws(client, ws_path)
        wm.archive_workspace(ws["id"])
        r = await client.post(f"/api/workspaces/{ws['id']}/unarchive")
        assert r.status_code == 200
        assert wm.get_workspace(ws["id"]).archived is False

    async def test_unarchive_duplicate_path_conflict(self, client, wm, ws_path):
        ws1 = await create_ws(client, ws_path, "WS1")
        wm.archive_workspace(ws1["id"])
        await create_ws(client, ws_path, "WS2")

        r = await client.post(f"/api/workspaces/{ws1['id']}/unarchive")
        assert r.status_code == 409

    async def test_unarchive_not_found(self, client):
        r = await client.post("/api/workspaces/ws_ghost/unarchive")
        assert r.status_code == 404


# ── GET /api/workspaces/{id}/sessions ────────────────────────────────────────

class TestListSessions:

    async def test_list_active_sessions(self, client, wm, ws_path):
        ws = await create_ws(client, ws_path)
        make_session(wm, ws["id"], "sess_active", archived=False)
        make_session(wm, ws["id"], "sess_archived", archived=True)

        r = await client.get(f"/api/workspaces/{ws['id']}/sessions")
        assert r.status_code == 200
        ids = [s["session_id"] for s in r.json()]
        assert "sess_active" in ids
        assert "sess_archived" not in ids

    async def test_list_with_archived(self, client, wm, ws_path):
        ws = await create_ws(client, ws_path)
        make_session(wm, ws["id"], "sess_active", archived=False)
        make_session(wm, ws["id"], "sess_archived", archived=True)

        r = await client.get(f"/api/workspaces/{ws['id']}/sessions?include_archived=true")
        assert r.status_code == 200
        ids = [s["session_id"] for s in r.json()]
        assert "sess_active" in ids
        assert "sess_archived" in ids

    async def test_list_sessions_workspace_not_found(self, client):
        r = await client.get("/api/workspaces/ws_ghost/sessions")
        assert r.status_code == 404


# ── POST /api/workspaces/{id}/sessions/{sid}/archive ─────────────────────────

class TestArchiveSession:

    async def test_archive_session(self, client, wm, ws_path):
        ws = await create_ws(client, ws_path)
        make_session(wm, ws["id"], "sess_001", archived=False)

        r = await client.post(f"/api/workspaces/{ws['id']}/sessions/sess_001/archive")
        assert r.status_code == 200

        sessions = wm.list_sessions(ws["id"], include_archived=True)
        s = next(x for x in sessions if x.session_id == "sess_001")
        assert s.archived is True

    async def test_archive_session_not_found(self, client, ws_path):
        ws = await create_ws(client, ws_path)
        r = await client.post(f"/api/workspaces/{ws['id']}/sessions/sess_ghost/archive")
        assert r.status_code == 404


# ── POST /api/workspaces/{id}/sessions/{sid}/unarchive ───────────────────────

class TestUnarchiveSession:

    async def test_unarchive_session(self, client, wm, ws_path):
        ws = await create_ws(client, ws_path)
        make_session(wm, ws["id"], "sess_001", archived=True)

        r = await client.post(f"/api/workspaces/{ws['id']}/sessions/sess_001/unarchive")
        assert r.status_code == 200

        sessions = wm.list_sessions(ws["id"], include_archived=True)
        s = next(x for x in sessions if x.session_id == "sess_001")
        assert s.archived is False


class TestUpdateSession:

    async def test_rename_session(self, client, wm, ws_path):
        ws = await create_ws(client, ws_path)
        make_session(wm, ws["id"], "sess_rename", archived=False)

        r = await client.patch(f"/api/workspaces/{ws['id']}/sessions/sess_rename", json={"title": "重命名后的线程"})
        assert r.status_code == 200

        sessions = wm.list_sessions(ws["id"], include_archived=True)
        renamed = next(x for x in sessions if x.session_id == "sess_rename")
        assert renamed.title == "重命名后的线程"

    async def test_rename_session_empty_title_rejected(self, client, wm, ws_path):
        ws = await create_ws(client, ws_path)
        make_session(wm, ws["id"], "sess_rename_empty", archived=False)

        r = await client.patch(f"/api/workspaces/{ws['id']}/sessions/sess_rename_empty", json={"title": "   "})
        assert r.status_code == 422


# ── DELETE /api/workspaces/{id}/sessions/{sid} ───────────────────────────────

class TestDeleteSession:

    async def test_delete_archived_session(self, client, wm, ws_path):
        ws = await create_ws(client, ws_path)
        make_session(wm, ws["id"], "sess_del", archived=True)

        r = await client.delete(f"/api/workspaces/{ws['id']}/sessions/sess_del")
        assert r.status_code == 200

        sessions = wm.list_sessions(ws["id"], include_archived=True)
        assert not any(s.session_id == "sess_del" for s in sessions)

    async def test_delete_non_archived_session_rejected(self, client, wm, ws_path):
        ws = await create_ws(client, ws_path)
        make_session(wm, ws["id"], "sess_active", archived=False)

        r = await client.delete(f"/api/workspaces/{ws['id']}/sessions/sess_active")
        assert r.status_code == 422

    async def test_delete_nonexistent_session(self, client, ws_path):
        ws = await create_ws(client, ws_path)
        r = await client.delete(f"/api/workspaces/{ws['id']}/sessions/sess_ghost")
        assert r.status_code == 404


# ── GET /api/home ─────────────────────────────────────────────────────────────

class TestHomeEndpoint:

    async def test_home_returns_workspaces(self, client, wm, ws_path):
        await create_ws(client, ws_path, "My WS")
        r = await client.get("/api/home")
        assert r.status_code == 200
        data = r.json()
        assert "workspaces" in data
        assert "total_workspaces" in data
        assert data["total_workspaces"] == 1

    async def test_home_empty(self, client):
        r = await client.get("/api/home")
        assert r.status_code == 200
        data = r.json()
        assert data["total_workspaces"] == 0
        assert data["workspaces"] == []

    async def test_home_excludes_archived(self, client, wm, ws_path, ws_path2):
        ws1 = await create_ws(client, ws_path, "WS1")
        ws2 = await create_ws(client, ws_path2, "WS2")
        wm.archive_workspace(ws2["id"])

        r = await client.get("/api/home")
        data = r.json()
        ids = [w["id"] for w in data["workspaces"]]
        assert ws1["id"] in ids
        assert ws2["id"] not in ids
        assert data["total_workspaces"] == 1

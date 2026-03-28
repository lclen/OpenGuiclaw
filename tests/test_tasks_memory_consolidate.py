import json
from pathlib import Path
from types import SimpleNamespace

import pytest


def _write_session(path: Path, session_id: str, user_text: str, assistant_text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "session_id": session_id,
                "messages": [
                    {"role": "user", "content": user_text},
                    {"role": "assistant", "content": assistant_text},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


class _FakeMemoryExtractor:
    def __init__(self):
        self.calls: list[list[dict]] = []

    def extract_from_conversation(self, messages):
        self.calls.append(messages)
        return [{"content": "记忆条目"}]


class _FakeMemory:
    def list_all(self):
        return []

    def list_by_type(self, _memory_type):
        return []


class _FakeCurrentSession:
    session_id = "sess_current"

    def add_message(self, *_args, **_kwargs):
        return None


class _FakeSessions:
    def __init__(self):
        self.current = _FakeCurrentSession()

    def save(self):
        return None


class _FakeAgent:
    def __init__(self):
        self.memory_extractor = _FakeMemoryExtractor()
        self.memory = _FakeMemory()
        self.sessions = _FakeSessions()


@pytest.mark.asyncio
async def test_memory_consolidate_scans_only_global_sessions(tmp_path, monkeypatch):
    from core import tasks

    (tmp_path / "data" / "sessions").mkdir(parents=True, exist_ok=True)
    global_session = tmp_path / "data" / "sessions" / "sess_global.json"
    workspace_session = tmp_path / "data" / "workspaces" / "ws_demo" / "sessions" / "sess_workspace.json"
    _write_session(global_session, "sess_global", "用户偏好黑色主题", "已记录偏好")
    _write_session(workspace_session, "sess_workspace", "工作区私有内容", "不应进入整理")

    fake_agent = _FakeAgent()
    pushed = []

    monkeypatch.setattr(tasks, "_APP_BASE", tmp_path)
    monkeypatch.setitem(tasks.app_state, "agent", fake_agent)
    monkeypatch.setattr(tasks, "_sync_current_session_to_workspace_mirrors", lambda _ag: [])

    success, status = await tasks._system_memory_consolidate(lambda event: pushed.append(event))

    assert success is True
    assert "扫描 1 个会话" in status
    assert len(fake_agent.memory_extractor.calls) == 1
    extracted_ids = [msg.get("content") for msg in fake_agent.memory_extractor.calls[0]]
    assert "用户偏好黑色主题" in extracted_ids
    assert "工作区私有内容" not in extracted_ids
    assert pushed[-1]["content"].startswith("## 🧠 记忆整理报告")

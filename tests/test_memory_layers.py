import json
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI

from core.memory import MemoryManager
from core.memory_extractor import MemoryExtractor
from core.routes.memory import router as memory_router
from core.state import app_state


def _write_legacy_memory(memory_file: Path, content: str, memory_type: str) -> None:
    memory_file.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "id": "mem_legacy001",
        "content": content,
        "type": memory_type,
        "tags": ["legacy"],
        "source": "manual",
        "timestamp": 1774740000.0,
        "created_at": "2026-03-29 14:00:00",
    }
    memory_file.write_text(json.dumps(payload, ensure_ascii=False) + "\n", encoding="utf-8")


def test_memory_manager_migrates_usage_layer_and_creates_backup(tmp_path: Path):
    memory_file = tmp_path / "memory" / "scene_memory.jsonl"
    _write_legacy_memory(memory_file, "user environment windows", "fact")

    manager = MemoryManager(data_dir=str(tmp_path))

    memories = manager.list_all()
    assert len(memories) == 1
    assert memories[0].usage_layer == "context"

    saved = json.loads(memory_file.read_text(encoding="utf-8").strip())
    assert saved["usage_layer"] == "context"

    backups = list((tmp_path / "memory").glob("scene_memory.usage_layer_backup_*.jsonl"))
    assert backups, "应该为旧记忆创建一次迁移备份"


def test_memory_manager_keeps_same_content_across_layers(tmp_path: Path):
    manager = MemoryManager(data_dir=str(tmp_path))

    first = manager.add("reply concise", type="rule")
    second = manager.add("reply concise", type="fact", usage_layer="context")

    assert first.id != second.id
    assert len(manager.list_all()) == 2
    assert {item.usage_layer for item in manager.list_all()} == {"preference", "context"}


def test_memory_manager_search_and_prompt_sections_by_usage_layer(tmp_path: Path):
    manager = MemoryManager(data_dir=str(tmp_path))
    manager.add("windows workstation environment", type="fact")
    manager.add("prefer concise reply format", type="rule")
    manager.add("cache fix restart service", type="experience")

    preference_results = manager.search("concise", usage_layer="preference")
    experience_results = manager.search("cache", usage_layer="experience")
    sections = manager.build_prompt_sections("windows concise cache")

    assert len(preference_results) == 1
    assert preference_results[0].usage_layer == "preference"
    assert len(experience_results) == 1
    assert experience_results[0].usage_layer == "experience"
    assert "# 用户偏好与行为约束" in sections["preference"]
    assert "# 相关长期背景" in sections["context"]
    assert "# 相关任务经验与避坑" in sections["experience"]


class _FakeCompletions:
    def __init__(self, content: str):
        self._content = content

    def create(self, **kwargs):
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=self._content))]
        )


def test_memory_extractor_writes_usage_layer(tmp_path: Path):
    manager = MemoryManager(data_dir=str(tmp_path))
    client = SimpleNamespace(chat=SimpleNamespace(completions=_FakeCompletions(
        '{"type":"rule","usage_layer":"preference","content":"prefer chinese ui"}'
    )))
    extractor = MemoryExtractor(client, manager, model="test-model")

    items = extractor.extract_from_turn("请全部用中文", "好的")

    assert len(items) == 1
    assert items[0].type == "rule"
    assert items[0].usage_layer == "preference"


@pytest_asyncio.fixture
async def memory_client(tmp_path: Path):
    app = FastAPI()
    app.include_router(memory_router)
    agent = SimpleNamespace(memory=MemoryManager(data_dir=str(tmp_path)))
    app_state["agent"] = agent

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        yield client, agent.memory

    app_state.pop("agent", None)


@pytest.mark.asyncio
async def test_memory_api_supports_usage_layer_filter_and_mapping(memory_client):
    client, memory = memory_client
    memory.add("windows environment", type="fact")
    memory.add("prefer concise reply", type="rule")

    response = await client.get("/api/memory", params={"usage_layer": "preference"})

    assert response.status_code == 200
    payload = response.json()
    assert len(payload["memories"]) == 1
    assert payload["memories"][0]["usage_layer"] == "preference"


@pytest.mark.asyncio
async def test_memory_api_create_and_update_derives_usage_layer(memory_client):
    client, memory = memory_client

    create_response = await client.post(
        "/api/memory",
        json={"content": "prefer chinese copy", "type": "rule", "tags": ["copy"]},
    )

    assert create_response.status_code == 200
    created = create_response.json()["memory"]
    assert created["usage_layer"] == "preference"

    update_response = await client.put(
        f"/api/memory/{created['id']}",
        json={"type": "error"},
    )

    assert update_response.status_code == 200
    updated = next(item for item in memory.list_all() if item.id == created["id"])
    assert updated.type == "error"
    assert updated.usage_layer == "experience"

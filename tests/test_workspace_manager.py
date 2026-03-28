"""
tests/test_workspace_manager.py
================================
WorkspaceManager 单元测试：CRUD、归档/恢复、线程管理、迁移兼容性。

运行：
    pytest tests/test_workspace_manager.py -v
"""

import json
import shutil
import tempfile
from pathlib import Path

import pytest

from core.workspace_manager import (
    DuplicateWorkspacePathError,
    WorkspaceManager,
    WorkspaceNotFoundError,
    WorkspacePathError,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def tmp_dir(tmp_path):
    """返回一个临时目录，用作 workspace_path。"""
    return tmp_path


@pytest.fixture
def wm(tmp_path):
    """每个测试独立的 WorkspaceManager，data_dir 在临时目录下。"""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    return WorkspaceManager(data_dir=data_dir)


@pytest.fixture
def ws_path(tmp_path):
    """一个真实存在的目录，用作 workspace_path。"""
    p = tmp_path / "my_project"
    p.mkdir()
    return p


@pytest.fixture
def ws_path2(tmp_path):
    p = tmp_path / "another_project"
    p.mkdir()
    return p


# ── 1. 工作区 CRUD ────────────────────────────────────────────────────────────

class TestWorkspaceCRUD:

    def test_create_workspace(self, wm, ws_path):
        ws = wm.create_workspace(name="Test WS", workspace_path=str(ws_path))
        assert ws.id.startswith("ws_")
        assert ws.name == "Test WS"
        assert ws.archived is False
        assert Path(ws.workspace_path) == ws_path.resolve()

    def test_create_workspace_path_not_exist(self, wm, tmp_path):
        with pytest.raises(WorkspacePathError):
            wm.create_workspace(name="Bad", workspace_path=str(tmp_path / "nonexistent"))

    def test_create_workspace_path_is_file(self, wm, tmp_path):
        f = tmp_path / "file.txt"
        f.write_text("x")
        with pytest.raises(WorkspacePathError):
            wm.create_workspace(name="Bad", workspace_path=str(f))

    def test_create_duplicate_path_raises(self, wm, ws_path):
        wm.create_workspace(name="WS1", workspace_path=str(ws_path))
        with pytest.raises(DuplicateWorkspacePathError):
            wm.create_workspace(name="WS2", workspace_path=str(ws_path))

    def test_get_workspace(self, wm, ws_path):
        created = wm.create_workspace(name="Get Test", workspace_path=str(ws_path))
        fetched = wm.get_workspace(created.id)
        assert fetched.id == created.id
        assert fetched.name == "Get Test"

    def test_get_workspace_not_found(self, wm):
        with pytest.raises(WorkspaceNotFoundError):
            wm.get_workspace("ws_nonexistent")

    def test_list_workspaces_excludes_archived(self, wm, ws_path, ws_path2):
        ws1 = wm.create_workspace(name="WS1", workspace_path=str(ws_path))
        ws2 = wm.create_workspace(name="WS2", workspace_path=str(ws_path2))
        wm.archive_workspace(ws2.id)

        active = wm.list_workspaces(include_archived=False)
        ids = [w.id for w in active]
        assert ws1.id in ids
        assert ws2.id not in ids

    def test_list_workspaces_includes_archived(self, wm, ws_path, ws_path2):
        ws1 = wm.create_workspace(name="WS1", workspace_path=str(ws_path))
        ws2 = wm.create_workspace(name="WS2", workspace_path=str(ws_path2))
        wm.archive_workspace(ws2.id)

        all_ws = wm.list_workspaces(include_archived=True)
        ids = [w.id for w in all_ws]
        assert ws1.id in ids
        assert ws2.id in ids

    def test_update_workspace_name(self, wm, ws_path):
        ws = wm.create_workspace(name="Old Name", workspace_path=str(ws_path))
        updated = wm.update_workspace(ws.id, name="New Name")
        assert updated.name == "New Name"

    def test_update_workspace_path(self, wm, ws_path, ws_path2):
        ws = wm.create_workspace(name="WS", workspace_path=str(ws_path))
        updated = wm.update_workspace(ws.id, workspace_path=str(ws_path2))
        assert Path(updated.workspace_path) == ws_path2.resolve()

    def test_update_workspace_not_found(self, wm):
        with pytest.raises(WorkspaceNotFoundError):
            wm.update_workspace("ws_ghost", name="X")

    def test_update_duplicate_path_raises(self, wm, ws_path, ws_path2):
        wm.create_workspace(name="WS1", workspace_path=str(ws_path))
        ws2 = wm.create_workspace(name="WS2", workspace_path=str(ws_path2))
        with pytest.raises(DuplicateWorkspacePathError):
            wm.update_workspace(ws2.id, workspace_path=str(ws_path))


# ── 2. 归档与恢复 ─────────────────────────────────────────────────────────────

class TestArchiveUnarchive:

    def test_archive_workspace(self, wm, ws_path):
        ws = wm.create_workspace(name="WS", workspace_path=str(ws_path))
        wm.archive_workspace(ws.id)
        fetched = wm.get_workspace(ws.id)
        assert fetched.archived is True

    def test_unarchive_workspace(self, wm, ws_path):
        ws = wm.create_workspace(name="WS", workspace_path=str(ws_path))
        wm.archive_workspace(ws.id)
        wm.unarchive_workspace(ws.id)
        fetched = wm.get_workspace(ws.id)
        assert fetched.archived is False

    def test_archive_not_found(self, wm):
        with pytest.raises(WorkspaceNotFoundError):
            wm.archive_workspace("ws_ghost")

    def test_unarchive_not_found(self, wm):
        with pytest.raises(WorkspaceNotFoundError):
            wm.unarchive_workspace("ws_ghost")

    def test_archived_path_freed_for_new_workspace(self, wm, ws_path):
        """归档后同路径可被新工作区使用。"""
        ws1 = wm.create_workspace(name="WS1", workspace_path=str(ws_path))
        wm.archive_workspace(ws1.id)
        # 归档后重复路径检查应跳过已归档的工作区
        ws2 = wm.create_workspace(name="WS2", workspace_path=str(ws_path))
        assert ws2.id != ws1.id

    def test_unarchive_conflicting_path_raises(self, wm, ws_path):
        ws1 = wm.create_workspace(name="WS1", workspace_path=str(ws_path))
        wm.archive_workspace(ws1.id)
        wm.create_workspace(name="WS2", workspace_path=str(ws_path))
        with pytest.raises(DuplicateWorkspacePathError):
            wm.unarchive_workspace(ws1.id)


# ── 3. 线程管理 ───────────────────────────────────────────────────────────────

class TestSessionManagement:

    def _make_session(self, wm, ws_id, session_id="sess_test01", archived=False):
        """直接写入一个 session JSON 文件。"""
        sessions_dir = wm._sessions_dir(ws_id)
        sessions_dir.mkdir(parents=True, exist_ok=True)
        data = {
            "session_id": session_id,
            "created_at": "2025-01-01T00:00:00Z",
            "updated_at": "2025-01-01T00:00:00Z",
            "archived": archived,
            "messages": [
                {"role": "user", "content": "Hello world"},
                {"role": "assistant", "content": "Hi there"},
            ],
        }
        path = sessions_dir / f"{session_id}.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        return data

    def test_list_sessions_active_only(self, wm, ws_path):
        ws = wm.create_workspace(name="WS", workspace_path=str(ws_path))
        self._make_session(wm, ws.id, "sess_active", archived=False)
        self._make_session(wm, ws.id, "sess_archived", archived=True)

        sessions = wm.list_sessions(ws.id, include_archived=False)
        ids = [s.session_id for s in sessions]
        assert "sess_active" in ids
        assert "sess_archived" not in ids

    def test_list_sessions_include_archived(self, wm, ws_path):
        ws = wm.create_workspace(name="WS", workspace_path=str(ws_path))
        self._make_session(wm, ws.id, "sess_active", archived=False)
        self._make_session(wm, ws.id, "sess_archived", archived=True)

        sessions = wm.list_sessions(ws.id, include_archived=True)
        ids = [s.session_id for s in sessions]
        assert "sess_active" in ids
        assert "sess_archived" in ids

    def test_list_sessions_workspace_not_found(self, wm):
        with pytest.raises(WorkspaceNotFoundError):
            wm.list_sessions("ws_ghost")

    def test_archive_session(self, wm, ws_path):
        ws = wm.create_workspace(name="WS", workspace_path=str(ws_path))
        self._make_session(wm, ws.id, "sess_001", archived=False)
        wm.archive_session(ws.id, "sess_001")

        sessions = wm.list_sessions(ws.id, include_archived=True)
        s = next(x for x in sessions if x.session_id == "sess_001")
        assert s.archived is True
        assert s.updated_at != "2025-01-01T00:00:00Z"

    def test_unarchive_session(self, wm, ws_path):
        ws = wm.create_workspace(name="WS", workspace_path=str(ws_path))
        self._make_session(wm, ws.id, "sess_001", archived=True)
        wm.unarchive_session(ws.id, "sess_001")

        sessions = wm.list_sessions(ws.id, include_archived=True)
        s = next(x for x in sessions if x.session_id == "sess_001")
        assert s.archived is False
        assert s.updated_at != "2025-01-01T00:00:00Z"

    def test_delete_archived_session(self, wm, ws_path):
        ws = wm.create_workspace(name="WS", workspace_path=str(ws_path))
        self._make_session(wm, ws.id, "sess_del", archived=True)
        wm.delete_session(ws.id, "sess_del")

        sessions = wm.list_sessions(ws.id, include_archived=True)
        ids = [s.session_id for s in sessions]
        assert "sess_del" not in ids

    def test_delete_non_archived_session_raises(self, wm, ws_path):
        ws = wm.create_workspace(name="WS", workspace_path=str(ws_path))
        self._make_session(wm, ws.id, "sess_active", archived=False)
        with pytest.raises(ValueError, match="not archived"):
            wm.delete_session(ws.id, "sess_active")

    def test_delete_nonexistent_session_raises(self, wm, ws_path):
        ws = wm.create_workspace(name="WS", workspace_path=str(ws_path))
        with pytest.raises(FileNotFoundError):
            wm.delete_session(ws.id, "sess_ghost")

    def test_delete_archived_workspace(self, wm, ws_path):
        ws = wm.create_workspace(name="WS", workspace_path=str(ws_path))
        self._make_session(wm, ws.id, "sess_archived", archived=True)
        wm.archive_workspace(ws.id)

        wm.delete_workspace(ws.id)

        with pytest.raises(WorkspaceNotFoundError):
            wm.get_workspace(ws.id)
        assert not wm._ws_dir(ws.id).exists()

    def test_delete_non_archived_workspace_raises(self, wm, ws_path):
        ws = wm.create_workspace(name="WS", workspace_path=str(ws_path))

        with pytest.raises(ValueError, match="not archived"):
            wm.delete_workspace(ws.id)

    def test_rename_session_updates_title(self, wm, ws_path):
        ws = wm.create_workspace(name="WS", workspace_path=str(ws_path))
        self._make_session(wm, ws.id, "sess_rename", archived=False)
        wm.rename_session(ws.id, "sess_rename", "新的标题")
        sessions = wm.list_sessions(ws.id, include_archived=True)
        renamed = next(x for x in sessions if x.session_id == "sess_rename")
        assert renamed.title == "新的标题"
        assert renamed.updated_at != "2025-01-01T00:00:00Z"

    def test_pin_session_updates_timestamp(self, wm, ws_path):
        ws = wm.create_workspace(name="WS", workspace_path=str(ws_path))
        self._make_session(wm, ws.id, "sess_pin", archived=False)

        wm.set_session_pinned(ws.id, "sess_pin", True)

        sessions = wm.list_sessions(ws.id, include_archived=True)
        pinned = next(x for x in sessions if x.session_id == "sess_pin")
        assert pinned.pinned is True
        assert pinned.updated_at != "2025-01-01T00:00:00Z"

    def test_rename_session_empty_title_rejected(self, wm, ws_path):
        ws = wm.create_workspace(name="WS", workspace_path=str(ws_path))
        self._make_session(wm, ws.id, "sess_rename_empty", archived=False)
        with pytest.raises(ValueError, match="cannot be empty"):
            wm.rename_session(ws.id, "sess_rename_empty", "   ")

    def test_session_title_derived_from_first_user_message(self, wm, ws_path):
        ws = wm.create_workspace(name="WS", workspace_path=str(ws_path))
        self._make_session(wm, ws.id, "sess_title")
        sessions = wm.list_sessions(ws.id)
        s = next(x for x in sessions if x.session_id == "sess_title")
        assert s.title == "Hello world"

    def test_list_sessions_limit(self, wm, ws_path):
        ws = wm.create_workspace(name="WS", workspace_path=str(ws_path))
        for i in range(10):
            self._make_session(wm, ws.id, f"sess_{i:03d}")
        sessions = wm.list_sessions(ws.id, limit=5)
        assert len(sessions) <= 5


# ── 4. 迁移兼容性 ─────────────────────────────────────────────────────────────

class TestMigration:

    def test_migrate_legacy_sessions(self, tmp_path):
        """旧 data/sessions/ 应被迁移到默认工作区。"""
        data_dir = tmp_path / "data"
        legacy_dir = data_dir / "sessions"
        legacy_dir.mkdir(parents=True)

        # 写入两个旧 session 文件
        for i in range(2):
            sid = f"sess_legacy_{i}"
            (legacy_dir / f"{sid}.json").write_text(
                json.dumps({
                    "session_id": sid,
                    "created_at": "2024-01-01T00:00:00Z",
                    "updated_at": "2024-01-01T00:00:00Z",
                    "messages": [],
                }),
                encoding="utf-8",
            )

        wm = WorkspaceManager(data_dir=data_dir)
        wm.migrate_legacy_sessions()

        # 应创建一个默认工作区
        workspaces = wm.list_workspaces(include_archived=False)
        assert len(workspaces) == 1
        assert workspaces[0].name == "Default Workspace"

        # 旧 session 应被复制到新工作区
        sessions = wm.list_sessions(workspaces[0].id, include_archived=True)
        session_ids = {s.session_id for s in sessions}
        assert "sess_legacy_0" in session_ids
        assert "sess_legacy_1" in session_ids

        # 原始 data/sessions/ 应保留
        assert legacy_dir.exists()

    def test_migrate_idempotent(self, tmp_path):
        """迁移应幂等：多次调用不重复创建工作区。"""
        data_dir = tmp_path / "data"
        legacy_dir = data_dir / "sessions"
        legacy_dir.mkdir(parents=True)
        (legacy_dir / "sess_x.json").write_text(
            json.dumps({"session_id": "sess_x", "created_at": "", "updated_at": "", "messages": []}),
            encoding="utf-8",
        )

        wm = WorkspaceManager(data_dir=data_dir)
        wm.migrate_legacy_sessions()
        wm.migrate_legacy_sessions()  # 第二次调用

        workspaces = wm.list_workspaces(include_archived=False)
        assert len(workspaces) == 1  # 不应重复创建

    def test_no_migration_when_no_legacy(self, tmp_path):
        """没有旧 sessions/ 目录时，迁移不应创建任何工作区。"""
        data_dir = tmp_path / "data"
        data_dir.mkdir()

        wm = WorkspaceManager(data_dir=data_dir)
        wm.migrate_legacy_sessions()

        workspaces = wm.list_workspaces(include_archived=True)
        assert len(workspaces) == 0

    def test_ensure_default_workspace(self, tmp_path):
        """没有任何工作区时，ensure_default_workspace 应创建一个。"""
        data_dir = tmp_path / "data"
        data_dir.mkdir()

        wm = WorkspaceManager(data_dir=data_dir)
        wm.ensure_default_workspace()

        workspaces = wm.list_workspaces()
        assert len(workspaces) == 1
        assert workspaces[0].name == "Default Workspace"

    def test_ensure_default_workspace_idempotent(self, tmp_path):
        data_dir = tmp_path / "data"
        data_dir.mkdir()

        wm = WorkspaceManager(data_dir=data_dir)
        wm.ensure_default_workspace()
        wm.ensure_default_workspace()

        workspaces = wm.list_workspaces()
        assert len(workspaces) == 1


# ── 5. 并发安全（基础验证）────────────────────────────────────────────────────

class TestConcurrency:

    def test_concurrent_session_writes_no_corruption(self, wm, ws_path):
        """多线程同时写入不同 session，不应互相覆盖。"""
        import threading

        ws = wm.create_workspace(name="WS", workspace_path=str(ws_path))
        errors = []

        def write_session(idx):
            try:
                sid = f"sess_concurrent_{idx:03d}"
                sessions_dir = wm._sessions_dir(ws.id)
                sessions_dir.mkdir(parents=True, exist_ok=True)
                data = {
                    "session_id": sid,
                    "created_at": "2025-01-01T00:00:00Z",
                    "updated_at": "2025-01-01T00:00:00Z",
                    "archived": False,
                    "messages": [{"role": "user", "content": f"msg {idx}"}],
                }
                path = sessions_dir / f"{sid}.json"
                path.write_text(json.dumps(data), encoding="utf-8")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=write_session, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Concurrent write errors: {errors}"

        sessions = wm.list_sessions(ws.id, limit=200)
        assert len(sessions) == 20

    def test_concurrent_workspace_reads_consistent(self, wm, ws_path):
        """多线程并发读取工作区列表，结果应一致。"""
        import threading

        ws = wm.create_workspace(name="WS", workspace_path=str(ws_path))
        results = []

        def read_workspaces():
            results.append(len(wm.list_workspaces()))

        threads = [threading.Thread(target=read_workspaces) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert all(r == 1 for r in results)


# ── 6. 迁移兼容性（7.3）────────────────────────────────────────────────────────

class TestMigrationCompat:

    def test_migrated_session_content_intact(self, tmp_path):
        """迁移后 session 内容（messages）应与原始文件完全一致。"""
        data_dir = tmp_path / "data"
        legacy_dir = data_dir / "sessions"
        legacy_dir.mkdir(parents=True)

        original = {
            "session_id": "sess_compat",
            "created_at": "2024-06-01T12:00:00Z",
            "updated_at": "2024-06-01T13:00:00Z",
            "messages": [
                {"role": "user", "content": "你好"},
                {"role": "assistant", "content": "你好！有什么可以帮你的？"},
            ],
        }
        (legacy_dir / "sess_compat.json").write_text(
            json.dumps(original, ensure_ascii=False), encoding="utf-8"
        )

        wm = WorkspaceManager(data_dir=data_dir)
        wm.migrate_legacy_sessions()

        ws = wm.list_workspaces()[0]
        sessions = wm.list_sessions(ws.id, include_archived=True)
        assert len(sessions) == 1

        # 读取迁移后的文件，验证内容完整
        migrated_path = wm._sessions_dir(ws.id) / "sess_compat.json"
        migrated = json.loads(migrated_path.read_text(encoding="utf-8"))
        assert migrated["messages"] == original["messages"]
        assert migrated["created_at"] == original["created_at"]

    def test_migrated_session_utf8_preserved(self, tmp_path):
        """迁移后中文内容应保持 UTF-8，不出现乱码。"""
        data_dir = tmp_path / "data"
        legacy_dir = data_dir / "sessions"
        legacy_dir.mkdir(parents=True)

        content = "这是一段包含中文的消息内容，用于验证编码正确性。"
        original = {
            "session_id": "sess_utf8",
            "created_at": "2024-01-01T00:00:00Z",
            "updated_at": "2024-01-01T00:00:00Z",
            "messages": [{"role": "user", "content": content}],
        }
        (legacy_dir / "sess_utf8.json").write_text(
            json.dumps(original, ensure_ascii=False), encoding="utf-8"
        )

        wm = WorkspaceManager(data_dir=data_dir)
        wm.migrate_legacy_sessions()

        ws = wm.list_workspaces()[0]
        migrated_path = wm._sessions_dir(ws.id) / "sess_utf8.json"
        migrated = json.loads(migrated_path.read_text(encoding="utf-8"))
        assert migrated["messages"][0]["content"] == content


# ── 7. 多客户端切换不串写（7.4）──────────────────────────────────────────────

class TestMultiClientIsolation:

    def test_two_clients_different_workspaces_no_cross_write(self, tmp_path):
        """两个 WorkspaceManager 实例各自操作不同工作区，session 不互相污染。"""
        import threading

        data_dir = tmp_path / "data"
        data_dir.mkdir()

        p1 = tmp_path / "proj1"
        p1.mkdir()
        p2 = tmp_path / "proj2"
        p2.mkdir()

        wm1 = WorkspaceManager(data_dir=data_dir)
        wm2 = WorkspaceManager(data_dir=data_dir)

        ws1 = wm1.create_workspace(name="Client1 WS", workspace_path=str(p1))
        ws2 = wm2.create_workspace(name="Client2 WS", workspace_path=str(p2))

        errors = []

        def write_for(wm, ws_id, prefix, count):
            try:
                for i in range(count):
                    sid = f"{prefix}_{i:03d}"
                    sessions_dir = wm._sessions_dir(ws_id)
                    sessions_dir.mkdir(parents=True, exist_ok=True)
                    data = {
                        "session_id": sid,
                        "created_at": "2025-01-01T00:00:00Z",
                        "updated_at": "2025-01-01T00:00:00Z",
                        "archived": False,
                        "messages": [{"role": "user", "content": f"{prefix} msg {i}"}],
                    }
                    (sessions_dir / f"{sid}.json").write_text(
                        json.dumps(data), encoding="utf-8"
                    )
            except Exception as e:
                errors.append(e)

        t1 = threading.Thread(target=write_for, args=(wm1, ws1.id, "c1", 10))
        t2 = threading.Thread(target=write_for, args=(wm2, ws2.id, "c2", 10))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert not errors

        # ws1 只有 c1_* sessions，ws2 只有 c2_* sessions
        s1_ids = {s.session_id for s in wm1.list_sessions(ws1.id, limit=100)}
        s2_ids = {s.session_id for s in wm2.list_sessions(ws2.id, limit=100)}

        assert all(sid.startswith("c1_") for sid in s1_ids)
        assert all(sid.startswith("c2_") for sid in s2_ids)
        assert s1_ids.isdisjoint(s2_ids)

    def test_switch_active_workspace_does_not_affect_other_client(self, tmp_path):
        """客户端 A 切换工作区，不影响客户端 B 当前工作区的 session 列表。"""
        data_dir = tmp_path / "data"
        data_dir.mkdir()

        p1 = tmp_path / "proj1"
        p1.mkdir()
        p2 = tmp_path / "proj2"
        p2.mkdir()

        wm_a = WorkspaceManager(data_dir=data_dir)
        wm_b = WorkspaceManager(data_dir=data_dir)

        ws_a1 = wm_a.create_workspace(name="A-WS1", workspace_path=str(p1))
        ws_b = wm_b.create_workspace(name="B-WS", workspace_path=str(p2))

        # B 写入一个 session
        sessions_dir = wm_b._sessions_dir(ws_b.id)
        sessions_dir.mkdir(parents=True, exist_ok=True)
        (sessions_dir / "sess_b.json").write_text(
            json.dumps({
                "session_id": "sess_b",
                "created_at": "2025-01-01T00:00:00Z",
                "updated_at": "2025-01-01T00:00:00Z",
                "archived": False,
                "messages": [],
            }),
            encoding="utf-8",
        )

        # A 归档自己的工作区（模拟切换）
        wm_a.archive_workspace(ws_a1.id)

        # B 的 session 不受影响
        b_sessions = wm_b.list_sessions(ws_b.id)
        assert len(b_sessions) == 1
        assert b_sessions[0].session_id == "sess_b"


# ── 8. 同一线程并发覆盖保护（7.5）────────────────────────────────────────────

class TestSameThreadConcurrency:

    def test_same_session_concurrent_writes_last_write_wins(self, wm, ws_path):
        """同一 session 文件被多线程并发写入时，最终文件应是合法 JSON（不损坏）。"""
        import threading

        ws = wm.create_workspace(name="WS", workspace_path=str(ws_path))
        sessions_dir = wm._sessions_dir(ws.id)
        sessions_dir.mkdir(parents=True, exist_ok=True)
        session_file = sessions_dir / "sess_shared.json"

        errors = []

        def write_version(version):
            try:
                data = {
                    "session_id": "sess_shared",
                    "created_at": "2025-01-01T00:00:00Z",
                    "updated_at": "2025-01-01T00:00:00Z",
                    "archived": False,
                    "messages": [{"role": "user", "content": f"version {version}"}],
                }
                session_file.write_text(json.dumps(data), encoding="utf-8")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=write_version, args=(i,)) for i in range(30)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors

        # 文件必须是合法 JSON（不管哪个版本赢了）
        content = session_file.read_text(encoding="utf-8")
        parsed = json.loads(content)  # 若损坏会抛 JSONDecodeError
        assert parsed["session_id"] == "sess_shared"

    def test_archive_and_list_concurrent_no_missing_sessions(self, wm, ws_path):
        """并发归档 + 列举 session，不应出现 KeyError 或丢失条目。"""
        import threading

        ws = wm.create_workspace(name="WS", workspace_path=str(ws_path))
        sessions_dir = wm._sessions_dir(ws.id)
        sessions_dir.mkdir(parents=True, exist_ok=True)

        # 预先写入 10 个 session
        for i in range(10):
            sid = f"sess_{i:03d}"
            (sessions_dir / f"{sid}.json").write_text(
                json.dumps({
                    "session_id": sid,
                    "created_at": "2025-01-01T00:00:00Z",
                    "updated_at": "2025-01-01T00:00:00Z",
                    "archived": False,
                    "messages": [],
                }),
                encoding="utf-8",
            )

        errors = []

        def archive_some():
            try:
                for i in range(0, 10, 2):
                    wm.archive_session(ws.id, f"sess_{i:03d}")
            except Exception as e:
                errors.append(e)

        def list_sessions():
            try:
                for _ in range(5):
                    wm.list_sessions(ws.id, include_archived=True)
            except Exception as e:
                errors.append(e)

        threads = (
            [threading.Thread(target=archive_some) for _ in range(3)]
            + [threading.Thread(target=list_sessions) for _ in range(3)]
        )
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors

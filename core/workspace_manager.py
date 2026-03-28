"""
core/workspace_manager.py — Workspace CRUD, archiving, path normalization, and migration.

Responsibilities:
  - WorkspaceInfo / SessionSummary / FileNode data models (pydantic v2)
  - WorkspaceManager: create / read / update / archive / unarchive workspaces
  - Session enumeration, archiving, unarchiving, permanent deletion
  - File tree reading with depth limit and ignore rules
  - One-time migration from legacy data/sessions/ to workspace-scoped sessions
  - Singleton factory: get_workspace_manager()

Storage layout:
  data/
  ├── workspaces/
  │   ├── .migrated
  │   ├── index.json          (optional UI hint)
  │   ├── ws_<id>/
  │   │   ├── workspace.json
  │   │   └── sessions/
  │   │       └── sess_<id>.json
  └── sessions/               (legacy, preserved after migration)
"""

from __future__ import annotations

import json
import logging
import shutil
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel
from pydantic import ConfigDict

logger = logging.getLogger("workspace_manager")

# ── Directories to skip when building file trees ─────────────────────────────
_SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "dist", "build", "__pycache__", ".pytest_cache"}


# ── Custom exceptions ─────────────────────────────────────────────────────────

class WorkspaceNotFoundError(Exception):
    """Raised when a workspace_id does not exist."""


class WorkspacePathError(Exception):
    """Raised when workspace_path is invalid (missing or not a directory)."""


class DuplicateWorkspacePathError(Exception):
    """Raised when another workspace already points to the same physical directory."""


# ── Data models ───────────────────────────────────────────────────────────────

class WorkspaceInfo(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    name: str
    workspace_path: str
    created_at: str
    updated_at: str
    persona_file: Optional[str] = None
    model_overrides: Optional[Dict[str, Any]] = None  # renamed from model_config to avoid pydantic v2 clash
    archived: bool = False
    is_default: bool = False


class SessionSummary(BaseModel):
    session_id: str
    created_at: str
    updated_at: str
    archived: bool = False
    pinned: bool = False
    message_count: int = 0
    title: Optional[str] = None


class FileNode(BaseModel):
    name: str
    path: str
    is_dir: bool
    children: Optional[List["FileNode"]] = None


FileNode.model_rebuild()


# ── ID helpers ────────────────────────────────────────────────────────────────

def _new_workspace_id() -> str:
    return "ws_" + uuid.uuid4().hex[:8]


def _new_session_id() -> str:
    return "sess_" + uuid.uuid4().hex[:8]


def _utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ── WorkspaceManager ──────────────────────────────────────────────────────────

class WorkspaceManager:
    """
    Manages workspaces and their sessions on disk.

    Thread-safe via a single reentrant lock.
    """

    def __init__(self, data_dir: str | Path = "data"):
        self._data_dir = Path(data_dir).resolve()
        self._workspaces_dir = self._data_dir / "workspaces"
        self._legacy_sessions_dir = self._data_dir / "sessions"
        self._lock = threading.RLock()
        self._workspaces_dir.mkdir(parents=True, exist_ok=True)

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _ws_dir(self, workspace_id: str) -> Path:
        return self._workspaces_dir / workspace_id

    def _ws_json(self, workspace_id: str) -> Path:
        return self._ws_dir(workspace_id) / "workspace.json"

    def _sessions_dir(self, workspace_id: str) -> Path:
        return self._ws_dir(workspace_id) / "sessions"

    def _read_workspace_json(self, workspace_id: str) -> WorkspaceInfo:
        path = self._ws_json(workspace_id)
        if not path.exists():
            raise WorkspaceNotFoundError(f"Workspace not found: {workspace_id}")
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return WorkspaceInfo(**data)

    def _write_workspace_json(self, info: WorkspaceInfo) -> None:
        ws_dir = self._ws_dir(info.id)
        ws_dir.mkdir(parents=True, exist_ok=True)
        self._sessions_dir(info.id).mkdir(parents=True, exist_ok=True)
        path = self._ws_json(info.id)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(info.model_dump(), f, ensure_ascii=False, indent=2)

    def _all_workspace_ids(self) -> List[str]:
        ids = []
        for entry in self._workspaces_dir.iterdir():
            if entry.is_dir() and (entry / "workspace.json").exists():
                ids.append(entry.name)
        return ids

    def _normalized_path(self, workspace_path: str) -> Path:
        return Path(workspace_path).resolve()

    # ── Workspace CRUD ────────────────────────────────────────────────────────

    def list_workspaces(self, include_archived: bool = False) -> List[WorkspaceInfo]:
        """Return all workspaces, optionally including archived ones."""
        with self._lock:
            result = []
            for ws_id in self._all_workspace_ids():
                try:
                    info = self._read_workspace_json(ws_id)
                    if include_archived or not info.archived:
                        result.append(info)
                except Exception as e:
                    logger.warning(f"Failed to read workspace {ws_id}: {e}")
            result.sort(key=lambda w: w.updated_at, reverse=True)
            return result

    def get_workspace(self, workspace_id: str) -> WorkspaceInfo:
        """Return a single workspace by ID. Raises WorkspaceNotFoundError if missing."""
        with self._lock:
            return self._read_workspace_json(workspace_id)

    def create_workspace(self, name: str, workspace_path: str) -> WorkspaceInfo:
        """
        Create a new workspace.

        Raises:
            WorkspacePathError: if workspace_path does not exist or is not a directory.
            DuplicateWorkspacePathError: if another workspace already uses the same path.
        """
        with self._lock:
            resolved = self._normalized_path(workspace_path)
            if not resolved.exists():
                raise WorkspacePathError(
                    f"workspace_path does not exist: {workspace_path!r}"
                )
            if not resolved.is_dir():
                raise WorkspacePathError(
                    f"workspace_path is not a directory: {workspace_path!r}"
                )

            # Duplicate check
            for ws_id in self._all_workspace_ids():
                try:
                    existing = self._read_workspace_json(ws_id)
                    if not existing.archived:
                        existing_resolved = Path(existing.workspace_path).resolve()
                        if existing_resolved == resolved:
                            raise DuplicateWorkspacePathError(
                                f"A workspace already exists for path: {resolved}"
                            )
                except (WorkspaceNotFoundError, DuplicateWorkspacePathError):
                    raise
                except Exception as e:
                    logger.warning(f"Error checking workspace {ws_id} for duplicates: {e}")

            now = _utcnow()
            info = WorkspaceInfo(
                id=_new_workspace_id(),
                name=name,
                workspace_path=str(resolved),
                created_at=now,
                updated_at=now,
                archived=False,
            )
            self._write_workspace_json(info)
            logger.info(f"Created workspace {info.id!r} -> {info.workspace_path!r}")
            return info

    def update_workspace(self, workspace_id: str, **fields) -> WorkspaceInfo:
        """
        Update allowed fields: name, workspace_path, persona_file, model_config.

        Raises WorkspaceNotFoundError if workspace does not exist.
        Raises WorkspacePathError / DuplicateWorkspacePathError if workspace_path is invalid.
        """
        with self._lock:
            info = self._read_workspace_json(workspace_id)

            allowed = {"name", "workspace_path", "persona_file", "model_overrides"}
            for key, value in fields.items():
                if key not in allowed:
                    continue
                if key == "workspace_path" and value is not None:
                    resolved = self._normalized_path(value)
                    if not resolved.exists():
                        raise WorkspacePathError(
                            f"workspace_path does not exist: {value!r}"
                        )
                    if not resolved.is_dir():
                        raise WorkspacePathError(
                            f"workspace_path is not a directory: {value!r}"
                        )
                    # Duplicate check (exclude self)
                    for ws_id in self._all_workspace_ids():
                        if ws_id == workspace_id:
                            continue
                        try:
                            other = self._read_workspace_json(ws_id)
                            if not other.archived:
                                if Path(other.workspace_path).resolve() == resolved:
                                    raise DuplicateWorkspacePathError(
                                        f"Another workspace already uses path: {resolved}"
                                    )
                        except (WorkspaceNotFoundError, DuplicateWorkspacePathError):
                            raise
                        except Exception:
                            pass
                    value = str(resolved)
                setattr(info, key, value)

            info.updated_at = _utcnow()
            self._write_workspace_json(info)
            return info

    def archive_workspace(self, workspace_id: str) -> None:
        """Soft-delete a workspace (archived=True). Data files are preserved."""
        with self._lock:
            info = self._read_workspace_json(workspace_id)
            info.archived = True
            info.updated_at = _utcnow()
            self._write_workspace_json(info)
            logger.info(f"Archived workspace {workspace_id!r}")

    def unarchive_workspace(self, workspace_id: str) -> None:
        """Restore an archived workspace."""
        with self._lock:
            info = self._read_workspace_json(workspace_id)
            resolved = Path(info.workspace_path).resolve()
            for ws_id in self._all_workspace_ids():
                if ws_id == workspace_id:
                    continue
                try:
                    other = self._read_workspace_json(ws_id)
                    if not other.archived and Path(other.workspace_path).resolve() == resolved:
                        raise DuplicateWorkspacePathError(
                            f"Another active workspace already uses path: {resolved}"
                        )
                except (WorkspaceNotFoundError, DuplicateWorkspacePathError):
                    raise
                except Exception as e:
                    logger.warning(f"Error checking workspace {ws_id} during unarchive: {e}")
            info.archived = False
            info.updated_at = _utcnow()
            self._write_workspace_json(info)
            logger.info(f"Unarchived workspace {workspace_id!r}")

    def delete_workspace(self, workspace_id: str) -> None:
        """Permanently delete an archived workspace directory from disk."""
        with self._lock:
            info = self._read_workspace_json(workspace_id)
            if not info.archived:
                raise ValueError(
                    f"Workspace {workspace_id} is not archived. "
                    "Archive it first before permanent deletion."
                )

            ws_dir = self._ws_dir(workspace_id)
            if not ws_dir.exists():
                raise WorkspaceNotFoundError(f"Workspace not found: {workspace_id}")

            shutil.rmtree(ws_dir)
            logger.info(f"Permanently deleted workspace {workspace_id!r}")

    # ── Session management ────────────────────────────────────────────────────

    def _read_session_json(self, workspace_id: str, session_id: str) -> Dict[str, Any]:
        path = self._sessions_dir(workspace_id) / f"{session_id}.json"
        if not path.exists():
            raise FileNotFoundError(f"Session not found: {session_id} in workspace {workspace_id}")
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _write_session_json(self, workspace_id: str, data: Dict[str, Any]) -> None:
        sessions_dir = self._sessions_dir(workspace_id)
        sessions_dir.mkdir(parents=True, exist_ok=True)
        session_id = data["session_id"]
        path = sessions_dir / f"{session_id}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _mark_session_updated(self, data: Dict[str, Any]) -> Dict[str, Any]:
        data["updated_at"] = _utcnow()
        return data

    def list_sessions(
        self,
        workspace_id: str,
        include_archived: bool = False,
        limit: int = 50,
    ) -> List[SessionSummary]:
        """
        List sessions for a workspace, sorted by updated_at descending.

        Raises WorkspaceNotFoundError if workspace does not exist.
        """
        with self._lock:
            # Validate workspace exists
            self._read_workspace_json(workspace_id)
            sessions_dir = self._sessions_dir(workspace_id)
            if not sessions_dir.exists():
                return []

            summaries = []
            for path in sessions_dir.glob("*.json"):
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    archived = data.get("archived", False)
                    if not include_archived and archived:
                        continue
                    pinned = data.get("pinned", False)
                    messages = data.get("messages", [])
                    # Prefer explicit title for system/inbox threads, then derive
                    # a title from the first user or assistant message.
                    title = data.get("title")
                    if not title:
                        for msg in messages:
                            role = msg.get("role")
                            if role not in {"user", "assistant"}:
                                continue
                            content = msg.get("content", "")
                            if isinstance(content, str) and content.strip():
                                title = content.strip()[:60]
                                break
                    summaries.append(SessionSummary(
                        session_id=data["session_id"],
                        created_at=data.get("created_at", ""),
                        updated_at=data.get("updated_at", ""),
                        archived=archived,
                        pinned=pinned,
                        message_count=len(messages),
                        title=title,
                    ))
                except Exception as e:
                    logger.warning(f"Failed to read session {path.name}: {e}")

            summaries.sort(key=lambda s: (s.pinned, s.updated_at), reverse=True)
            return summaries[:limit]

    def count_sessions(self, workspace_id: str, include_archived: bool = False) -> int:
        """Return the total session count for a workspace without applying list limits."""
        with self._lock:
            self._read_workspace_json(workspace_id)
            sessions_dir = self._sessions_dir(workspace_id)
            if not sessions_dir.exists():
                return 0

            count = 0
            for path in sessions_dir.glob("*.json"):
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    if include_archived or not data.get("archived", False):
                        count += 1
                except Exception as e:
                    logger.warning(f"Failed to count session {path.name}: {e}")
            return count

    def archive_session(self, workspace_id: str, session_id: str) -> None:
        """Mark a session as archived."""
        with self._lock:
            self._read_workspace_json(workspace_id)  # validate workspace
            data = self._read_session_json(workspace_id, session_id)
            data["archived"] = True
            self._mark_session_updated(data)
            self._write_session_json(workspace_id, data)

    def set_session_pinned(self, workspace_id: str, session_id: str, pinned: bool) -> None:
        """Set or clear the pinned state for a session."""
        with self._lock:
            self._read_workspace_json(workspace_id)
            data = self._read_session_json(workspace_id, session_id)
            data["pinned"] = bool(pinned)
            self._mark_session_updated(data)
            self._write_session_json(workspace_id, data)

    def rename_session(self, workspace_id: str, session_id: str, title: str) -> None:
        """Update a session title."""
        with self._lock:
            self._read_workspace_json(workspace_id)
            next_title = (title or "").strip()
            if not next_title:
                raise ValueError("Session title cannot be empty")
            data = self._read_session_json(workspace_id, session_id)
            data["title"] = next_title
            self._mark_session_updated(data)
            self._write_session_json(workspace_id, data)

    def unarchive_session(self, workspace_id: str, session_id: str) -> None:
        """Restore an archived session."""
        with self._lock:
            self._read_workspace_json(workspace_id)
            data = self._read_session_json(workspace_id, session_id)
            data["archived"] = False
            self._mark_session_updated(data)
            self._write_session_json(workspace_id, data)

    def delete_session(self, workspace_id: str, session_id: str) -> None:
        """Permanently delete a session file from disk. Only archived sessions may be deleted."""
        with self._lock:
            self._read_workspace_json(workspace_id)
            path = self._sessions_dir(workspace_id) / f"{session_id}.json"
            if not path.exists():
                raise FileNotFoundError(
                    f"Session not found: {session_id} in workspace {workspace_id}"
                )
            # Safety guard: only allow deletion of archived sessions
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if not data.get("archived", False):
                    raise ValueError(
                        f"Session {session_id} is not archived. "
                        "Archive it first before permanent deletion."
                    )
            except (json.JSONDecodeError, OSError) as e:
                raise ValueError(f"Cannot read session file: {e}") from e
            path.unlink()
            logger.info(f"Permanently deleted session {session_id!r} from workspace {workspace_id!r}")

    # ── File tree ─────────────────────────────────────────────────────────────

    def get_file_tree(self, workspace_id: str, max_depth: int = 3) -> List[FileNode]:
        """
        Return a file tree for the workspace's workspace_path.

        - Max depth: 3 (configurable)
        - Skips: .git, node_modules, .venv, dist, build, __pycache__, etc.
        - Skips symlink loops
        - Skips subtrees with permission errors (logs warning)
        """
        with self._lock:
            info = self._read_workspace_json(workspace_id)

        root = Path(info.workspace_path)
        if not root.exists() or not root.is_dir():
            raise WorkspacePathError(
                f"workspace_path is not accessible: {info.workspace_path!r}"
            )

        return self._build_tree(root, current_depth=0, max_depth=max_depth, seen_inodes=set())

    def _build_tree(
        self,
        path: Path,
        current_depth: int,
        max_depth: int,
        seen_inodes: set,
    ) -> List[FileNode]:
        nodes: List[FileNode] = []
        try:
            entries = sorted(path.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower()))
        except PermissionError:
            logger.warning(f"Permission denied reading directory: {path}")
            return nodes

        for entry in entries:
            if entry.name in _SKIP_DIRS:
                continue
            if entry.name.startswith(".") and entry.name not in (".kiro",):
                # Skip hidden files/dirs except .kiro (project config)
                continue

            is_dir = entry.is_dir()

            # Symlink loop detection
            if entry.is_symlink():
                try:
                    real = entry.resolve()
                    inode = real.stat().st_ino
                    if inode in seen_inodes:
                        continue
                    seen_inodes = seen_inodes | {inode}
                except Exception:
                    continue

            children = None
            if is_dir and current_depth < max_depth - 1:
                children = self._build_tree(
                    entry,
                    current_depth=current_depth + 1,
                    max_depth=max_depth,
                    seen_inodes=seen_inodes,
                )

            nodes.append(FileNode(
                name=entry.name,
                path=str(entry),
                is_dir=is_dir,
                children=children,
            ))

        return nodes

    # ── Migration ─────────────────────────────────────────────────────────────

    def migrate_legacy_sessions(self) -> None:
        """
        One-time migration from data/sessions/ to a default workspace.

        Conditions to run:
          - data/sessions/ exists
          - data/workspaces/.migrated does NOT exist
          - No valid workspace.json exists under data/workspaces/

        Steps:
          1. Create default workspace pointing to app root
          2. Copy legacy sessions to default workspace's sessions/
          3. Preserve original data/sessions/
          4. Write .migrated marker
          5. On error: log and continue (never block startup)
        """
        migrated_marker = self._workspaces_dir / ".migrated"

        if migrated_marker.exists():
            return  # Already migrated

        if not self._legacy_sessions_dir.exists():
            return  # No legacy data to migrate

        # Check for "partial init" / dirty state: any valid workspace.json present?
        has_valid_workspace = any(
            (self._workspaces_dir / d / "workspace.json").exists()
            for d in (
                entry.name
                for entry in self._workspaces_dir.iterdir()
                if entry.is_dir()
            )
            if not d.startswith(".")
        ) if self._workspaces_dir.exists() else False

        if has_valid_workspace:
            # Workspaces already exist — write marker to prevent future checks
            migrated_marker.touch()
            return

        logger.info("Migrating legacy sessions to default workspace...")
        try:
            # Determine app root (parent of data/)
            app_root = self._data_dir.parent
            now = _utcnow()
            default_ws = WorkspaceInfo(
                id=_new_workspace_id(),
                name="Default Workspace",
                workspace_path=str(app_root),
                created_at=now,
                updated_at=now,
                archived=False,
            )
            self._write_workspace_json(default_ws)

            dest_sessions = self._sessions_dir(default_ws.id)
            dest_sessions.mkdir(parents=True, exist_ok=True)

            copied = 0
            for src_file in self._legacy_sessions_dir.glob("*.json"):
                try:
                    shutil.copy2(src_file, dest_sessions / src_file.name)
                    copied += 1
                except Exception as e:
                    logger.warning(f"Failed to copy session {src_file.name}: {e}")

            # Write .migrated marker
            migrated_marker.write_text(
                json.dumps({
                    "migrated_at": now,
                    "default_workspace_id": default_ws.id,
                    "sessions_copied": copied,
                }, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            logger.info(
                f"Migration complete: created workspace {default_ws.id!r}, "
                f"copied {copied} sessions."
            )
        except Exception as e:
            logger.error(f"Migration failed (startup will continue): {e}", exc_info=True)

    # ── Default workspace bootstrap ───────────────────────────────────────────

    def ensure_default_workspace(self) -> None:
        """
        If no workspaces exist at all, create a default one pointing to the app root.
        Called on first startup after migration check.
        """
        with self._lock:
            if self._all_workspace_ids():
                return  # Already have workspaces

            app_root = self._data_dir.parent
            now = _utcnow()
            default_ws = WorkspaceInfo(
                id=_new_workspace_id(),
                name="Default Workspace",
                workspace_path=str(app_root),
                created_at=now,
                updated_at=now,
                archived=False,
            )
            self._write_workspace_json(default_ws)
            logger.info(
                f"Created default workspace {default_ws.id!r} -> {default_ws.workspace_path!r}"
            )

    def get_default_workspace(self, create_if_missing: bool = True) -> WorkspaceInfo:
        """
        Return the global/default workspace.

        Preference order:
        1. Active workspace named "Default Workspace" at app root
        2. Any active workspace at app root
        3. Any active workspace named "Default Workspace"
        4. Create a new default workspace at app root (if allowed)
        """
        with self._lock:
            app_root = self._data_dir.parent.resolve()
            name_and_path_match: list[WorkspaceInfo] = []
            path_match: list[WorkspaceInfo] = []
            name_match: list[WorkspaceInfo] = []

            for ws_id in self._all_workspace_ids():
                try:
                    info = self._read_workspace_json(ws_id)
                except Exception:
                    continue
                if info.archived:
                    continue

                try:
                    resolved = Path(info.workspace_path).resolve()
                except Exception:
                    resolved = None

                if info.name == "Default Workspace" and resolved == app_root:
                    name_and_path_match.append(info)
                elif resolved == app_root:
                    path_match.append(info)
                elif info.name == "Default Workspace":
                    name_match.append(info)

            if name_and_path_match:
                return name_and_path_match[0]
            if path_match:
                return path_match[0]
            if name_match:
                return name_match[0]

            if not create_if_missing:
                raise WorkspaceNotFoundError("Default workspace not found")

            now = _utcnow()
            default_ws = WorkspaceInfo(
                id=_new_workspace_id(),
                name="Default Workspace",
                workspace_path=str(app_root),
                created_at=now,
                updated_at=now,
                archived=False,
                is_default=True,
            )
            self._write_workspace_json(default_ws)
            logger.info(
                f"Created missing default workspace {default_ws.id!r} -> {default_ws.workspace_path!r}"
            )
            return default_ws

    def ensure_system_session(
        self,
        workspace_id: str,
        thread_type: str,
        title: str,
        pinned: bool = False,
    ) -> str:
        """Return a stable system thread id for the workspace, creating it if needed."""
        with self._lock:
            self._read_workspace_json(workspace_id)
            sessions_dir = self._sessions_dir(workspace_id)
            sessions_dir.mkdir(parents=True, exist_ok=True)

            for path in sessions_dir.glob("*.json"):
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    if data.get("system_thread_type") != thread_type:
                        continue
                    if data.get("title") != title or data.get("pinned") != bool(pinned):
                        data["title"] = title
                        data["pinned"] = bool(pinned)
                        self._write_session_json(workspace_id, data)
                    return data["session_id"]
                except Exception as e:
                    logger.warning(f"Failed to inspect system session {path.name}: {e}")

            from core.session import Session

            session = Session()
            session_data = session.to_dict()
            session_data["title"] = title
            session_data["system_thread_type"] = thread_type
            session_data["pinned"] = bool(pinned)
            self._write_session_json(workspace_id, session_data)
            return session.session_id


# ── Singleton factory ─────────────────────────────────────────────────────────

_manager_instance: Optional[WorkspaceManager] = None
_manager_lock = threading.Lock()


def get_workspace_manager(data_dir: str | Path | None = None) -> WorkspaceManager:
    """
    Return the singleton WorkspaceManager.

    On first call:
      1. Runs migrate_legacy_sessions()
      2. Runs ensure_default_workspace()

    data_dir defaults to <app_root>/data, resolved from APP_BASE_DIR env var.
    """
    global _manager_instance
    if _manager_instance is not None:
        return _manager_instance

    with _manager_lock:
        if _manager_instance is not None:
            return _manager_instance

        if data_dir is None:
            import os
            from pathlib import Path as _Path
            app_base = _Path(os.environ.get("APP_BASE_DIR", str(_Path(__file__).resolve().parent.parent)))
            data_dir = app_base / "data"

        manager = WorkspaceManager(data_dir=data_dir)
        manager.migrate_legacy_sessions()
        manager.ensure_default_workspace()
        _manager_instance = manager
        return _manager_instance

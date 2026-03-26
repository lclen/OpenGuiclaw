"""
定时任务定义

定义任务的数据结构和状态
"""

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from core.im_bots import is_im_session_id, make_im_session_id, parse_im_session_id
from .triggers import TriggerType

logger = logging.getLogger(__name__)

class TaskType(Enum):
    """任务类型"""
    REMINDER = "reminder"  # 简单提醒
    TASK = "task"          # Agent 执行
    SYSTEM = "system"      # 系统内置任务（不通过 LLM）


class TaskStatus(Enum):
    """任务状态"""
    PENDING = "pending"
    SCHEDULED = "scheduled"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    DISABLED = "disabled"
    CANCELLED = "cancelled"


class TaskTargetKind(Enum):
    """任务结果投递目标类型"""
    WORKSPACE_INBOX = "workspace_inbox"
    DESKTOP_SESSION = "desktop_session"
    IM_SESSION = "im_session"


class TaskExecutionStatus(Enum):
    """任务执行记录状态"""
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"


def _normalize_delivery_target(target: dict[str, Any]) -> dict[str, Any] | None:
    kind = str(target.get("kind") or "").strip()
    workspace_id = target.get("workspace_id")
    session_id = target.get("session_id")
    channel = target.get("channel")
    chat_id = target.get("chat_id")

    if not kind:
        if session_id:
            if is_im_session_id(str(session_id)):
                kind = TaskTargetKind.IM_SESSION.value
            else:
                kind = TaskTargetKind.DESKTOP_SESSION.value
        else:
            kind = TaskTargetKind.WORKSPACE_INBOX.value

    if kind == TaskTargetKind.WORKSPACE_INBOX.value:
        return {
            "kind": kind,
            "workspace_id": workspace_id,
            "session_id": None,
            "channel": None,
            "chat_id": None,
        }

    if kind == TaskTargetKind.DESKTOP_SESSION.value:
        if not session_id:
            return None
        return {
            "kind": kind,
            "workspace_id": None,
            "session_id": session_id,
            "channel": None,
            "chat_id": None,
        }

    if kind == TaskTargetKind.IM_SESSION.value:
        resolved_session_id = session_id
        resolved_channel = channel
        resolved_chat_id = chat_id
        if (not resolved_channel or not resolved_chat_id) and resolved_session_id:
            parsed = parse_im_session_id(str(resolved_session_id))
            if parsed:
                resolved_channel = parsed["channel_name"]
                resolved_chat_id = parsed["chat_id"]
        if not resolved_session_id and resolved_channel and resolved_chat_id:
            resolved_session_id = make_im_session_id(resolved_channel, resolved_chat_id)
        if not resolved_session_id:
            return None
        return {
            "kind": kind,
            "workspace_id": None,
            "session_id": resolved_session_id,
            "channel": resolved_channel,
            "chat_id": resolved_chat_id,
        }

    return None


@dataclass
class ScheduledTask:
    """定时任务"""

    id: str
    name: str
    description: str

    trigger_type: TriggerType
    trigger_config: dict

    task_type: TaskType = TaskType.TASK
    reminder_message: str | None = None
    prompt: str = ""
    action: str | None = None
    delivery_targets: list[dict[str, Any]] = field(default_factory=list)
    target_kind: str = TaskTargetKind.WORKSPACE_INBOX.value
    target_workspace_id: str | None = None
    target_session_id: str | None = None
    target_channel: str | None = None
    target_chat_id: str | None = None

    enabled: bool = True
    status: TaskStatus = TaskStatus.PENDING
    deletable: bool = True

    last_run: datetime | None = None
    next_run: datetime | None = None
    run_count: int = 0
    fail_count: int = 0

    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    def __post_init__(self) -> None:
        self.normalize_target()

    @classmethod
    def create(
        cls,
        name: str,
        description: str,
        trigger_type: TriggerType,
        trigger_config: dict,
        prompt: str = "",
        task_type: TaskType = TaskType.TASK,
        reminder_message: str | None = None,
        **kwargs,
    ) -> "ScheduledTask":
        kwargs = dict(kwargs)
        if not any(
            kwargs.get(key)
            for key in (
                "delivery_targets",
                "target_kind",
                "target_workspace_id",
                "target_session_id",
                "target_channel",
                "target_chat_id",
            )
        ):
            try:
                from core.automation_context import get_automation_source_context

                source = get_automation_source_context()
            except Exception:
                source = None

            if source and source.source_kind == "im" and source.source_session_id:
                kwargs["target_kind"] = TaskTargetKind.IM_SESSION.value
                kwargs["target_session_id"] = source.source_session_id
                kwargs["target_channel"] = source.source_channel
                kwargs["target_chat_id"] = source.source_chat_id

        return cls(
            id=f"task_{uuid.uuid4().hex[:12]}",
            name=name,
            description=description,
            trigger_type=trigger_type,
            trigger_config=trigger_config,
            task_type=task_type,
            reminder_message=reminder_message,
            prompt=prompt,
            **kwargs,
        )

    def normalize_target(self) -> None:
        """Fill compatible target fields for new and legacy tasks."""
        normalized_targets: list[dict[str, Any]] = []
        raw_targets = self.delivery_targets if isinstance(self.delivery_targets, list) else []
        for target in raw_targets:
            if not isinstance(target, dict):
                continue
            normalized = _normalize_delivery_target(target)
            if normalized and normalized not in normalized_targets:
                normalized_targets.append(normalized)

        if not normalized_targets:
            legacy_target = _normalize_delivery_target(
                {
                    "kind": self.target_kind,
                    "workspace_id": self.target_workspace_id,
                    "session_id": self.target_session_id,
                    "channel": self.target_channel,
                    "chat_id": self.target_chat_id,
                }
            )
            if legacy_target:
                normalized_targets.append(legacy_target)

        if not normalized_targets:
            normalized_targets.append(
                {
                    "kind": TaskTargetKind.WORKSPACE_INBOX.value,
                    "workspace_id": self.target_workspace_id,
                    "session_id": None,
                    "channel": None,
                    "chat_id": None,
                }
            )

        self.delivery_targets = normalized_targets
        primary_target = normalized_targets[0]
        self.target_kind = primary_target["kind"]
        self.target_workspace_id = primary_target.get("workspace_id")
        self.target_session_id = primary_target.get("session_id")
        self.target_channel = primary_target.get("channel")
        self.target_chat_id = primary_target.get("chat_id")

    def get_delivery_targets(self) -> list[dict[str, Any]]:
        self.normalize_target()
        return [dict(target) for target in self.delivery_targets]

    @property
    def resolved_target_kind(self) -> str:
        self.normalize_target()
        return self.target_kind

    def enable(self) -> None:
        self.enabled = True
        self.status = TaskStatus.SCHEDULED
        self.updated_at = datetime.now()

    def disable(self) -> None:
        self.enabled = False
        self.status = TaskStatus.DISABLED
        self.updated_at = datetime.now()

    def cancel(self) -> None:
        self.enabled = False
        self.status = TaskStatus.CANCELLED
        self.updated_at = datetime.now()

    def mark_running(self) -> None:
        self.status = TaskStatus.RUNNING
        self.next_run = None  # clear to prevent re-trigger while running
        self.updated_at = datetime.now()

    def mark_completed(self, next_run: datetime | None = None) -> None:
        self.last_run = datetime.now()
        self.run_count += 1
        self.updated_at = datetime.now()

        if self.trigger_type == TriggerType.ONCE:
            self.status = TaskStatus.COMPLETED
            self.enabled = False
            self.next_run = None  # explicitly clear so restart won't re-trigger
        else:
            self.status = TaskStatus.SCHEDULED
            self.next_run = next_run

    def mark_failed(self, error: str = None) -> None:
        self.last_run = datetime.now()
        self.fail_count += 1
        self.updated_at = datetime.now()

        if self.fail_count >= 5:
            self.status = TaskStatus.FAILED
            self.enabled = False
            logger.warning(f"Task {self.id} disabled after {self.fail_count} failures")
        else:
            self.status = TaskStatus.SCHEDULED

    @property
    def is_active(self) -> bool:
        return self.enabled and self.status in (TaskStatus.PENDING, TaskStatus.SCHEDULED)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "trigger_type": self.trigger_type.value,
            "trigger_config": self.trigger_config,
            "task_type": self.task_type.value,
            "reminder_message": self.reminder_message,
            "prompt": self.prompt,
            "action": self.action,
            "delivery_targets": self.get_delivery_targets(),
            "target_kind": self.target_kind,
            "target_workspace_id": self.target_workspace_id,
            "target_session_id": self.target_session_id,
            "target_channel": self.target_channel,
            "target_chat_id": self.target_chat_id,
            "enabled": self.enabled,
            "status": self.status.value,
            "deletable": self.deletable,
            "last_run": self.last_run.isoformat() if self.last_run else None,
            "next_run": self.next_run.isoformat() if self.next_run else None,
            "run_count": self.run_count,
            "fail_count": self.fail_count,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ScheduledTask":
        return cls(
            id=data["id"],
            name=data["name"],
            description=data["description"],
            trigger_type=TriggerType(data["trigger_type"]),
            trigger_config=data["trigger_config"],
            task_type=TaskType(data.get("task_type", "task")),
            reminder_message=data.get("reminder_message"),
            prompt=data.get("prompt", ""),
            action=data.get("action"),
            delivery_targets=data.get("delivery_targets") or [],
            target_kind=data.get("target_kind", ""),
            target_workspace_id=data.get("target_workspace_id"),
            target_session_id=data.get("target_session_id"),
            target_channel=data.get("target_channel"),
            target_chat_id=data.get("target_chat_id"),
            enabled=data.get("enabled", True),
            status=TaskStatus(data.get("status", "pending")),
            deletable=data.get("deletable", True),
            last_run=datetime.fromisoformat(data["last_run"]) if data.get("last_run") else None,
            next_run=datetime.fromisoformat(data["next_run"]) if data.get("next_run") else None,
            run_count=data.get("run_count", 0),
            fail_count=data.get("fail_count", 0),
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
        )


@dataclass
class TaskExecution:
    """任务执行记录"""

    id: str
    task_id: str
    started_at: datetime
    status: str = TaskExecutionStatus.RUNNING.value
    finished_at: datetime | None = None
    result_summary: str | None = None
    error: str | None = None
    delivery_targets: list[dict[str, Any]] = field(default_factory=list)
    target_kind: str | None = None
    target_workspace_id: str | None = None
    target_session_id: str | None = None
    target_channel: str | None = None
    target_chat_id: str | None = None
    trigger_source: str = "scheduler"

    @classmethod
    def create(cls, task: ScheduledTask, trigger_source: str) -> "TaskExecution":
        task.normalize_target()
        return cls(
            id=f"exec_{uuid.uuid4().hex[:12]}",
            task_id=task.id,
            started_at=datetime.now(),
            delivery_targets=task.get_delivery_targets(),
            target_kind=task.target_kind,
            target_workspace_id=task.target_workspace_id,
            target_session_id=task.target_session_id,
            target_channel=task.target_channel,
            target_chat_id=task.target_chat_id,
            trigger_source=trigger_source,
        )

    def mark_success(self, result_summary: str | None = None) -> None:
        self.status = TaskExecutionStatus.SUCCESS.value
        self.finished_at = datetime.now()
        self.result_summary = result_summary
        self.error = None

    def mark_failed(self, error: str | None = None, result_summary: str | None = None) -> None:
        self.status = TaskExecutionStatus.FAILED.value
        self.finished_at = datetime.now()
        self.error = error
        self.result_summary = result_summary

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "task_id": self.task_id,
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "status": self.status,
            "result_summary": self.result_summary,
            "error": self.error,
            "delivery_targets": self.delivery_targets,
            "target_kind": self.target_kind,
            "target_workspace_id": self.target_workspace_id,
            "target_session_id": self.target_session_id,
            "target_channel": self.target_channel,
            "target_chat_id": self.target_chat_id,
            "trigger_source": self.trigger_source,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "TaskExecution":
        return cls(
            id=data["id"],
            task_id=data["task_id"],
            started_at=datetime.fromisoformat(data["started_at"]),
            finished_at=datetime.fromisoformat(data["finished_at"]) if data.get("finished_at") else None,
            status=data.get("status", TaskExecutionStatus.RUNNING.value),
            result_summary=data.get("result_summary"),
            error=data.get("error"),
            delivery_targets=data.get("delivery_targets") or [],
            target_kind=data.get("target_kind"),
            target_workspace_id=data.get("target_workspace_id"),
            target_session_id=data.get("target_session_id"),
            target_channel=data.get("target_channel"),
            target_chat_id=data.get("target_chat_id"),
            trigger_source=data.get("trigger_source", "scheduler"),
        )

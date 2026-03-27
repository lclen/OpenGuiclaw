"""Context helpers for source-aware automation delivery."""

from __future__ import annotations

from contextvars import ContextVar, Token
from dataclasses import dataclass


@dataclass(frozen=True)
class AutomationSourceContext:
    """Carries the conversation source for async automation follow-ups."""

    source_kind: str
    source_session_id: str | None = None
    source_channel: str | None = None
    source_chat_id: str | None = None
    workspace_id: str | None = None
    workspace_name: str | None = None
    workspace_path: str | None = None


_automation_source_ctx: ContextVar[AutomationSourceContext | None] = ContextVar(
    "automation_source_context",
    default=None,
)


def set_automation_source_context(
    *,
    source_kind: str,
    source_session_id: str | None = None,
    source_channel: str | None = None,
    source_chat_id: str | None = None,
    workspace_id: str | None = None,
    workspace_name: str | None = None,
    workspace_path: str | None = None,
) -> Token:
    return _automation_source_ctx.set(
        AutomationSourceContext(
            source_kind=source_kind,
            source_session_id=source_session_id,
            source_channel=source_channel,
            source_chat_id=source_chat_id,
            workspace_id=workspace_id,
            workspace_name=workspace_name,
            workspace_path=workspace_path,
        )
    )


def get_automation_source_context() -> AutomationSourceContext | None:
    return _automation_source_ctx.get()


def get_request_workspace_path() -> str | None:
    context = get_automation_source_context()
    return context.workspace_path if context and context.workspace_path else None


def reset_automation_source_context(token: Token) -> None:
    _automation_source_ctx.reset(token)

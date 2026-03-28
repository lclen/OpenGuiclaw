"""IM bot, channel and session management API."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from core.im_selfcheck_subscriptions import (
    list_selfcheck_subscriptions,
    remove_selfcheck_subscription,
    upsert_selfcheck_subscription,
)
from core.im_bots import (
    COMING_SOON_IM_PLATFORMS,
    PLATFORM_LABELS,
    SUPPORTED_IM_PLATFORMS,
    clone_config,
    delete_im_bot,
    get_im_bot,
    load_im_bots_from_config,
    make_channel_name,
    parse_im_session_id,
    run_im_bot_healthcheck,
    sync_im_bots_into_config,
    update_im_bot_toggle,
    upsert_im_bot,
    with_persisted_health,
)
from core.state import _APP_BASE, app_state, logger

router = APIRouter(tags=["im"])


def _config_path() -> Path:
    return _APP_BASE / "config.json"


def _runtime_state_path() -> Path:
    return _APP_BASE / "data" / "im" / "runtime_state.json"


def _load_config_json() -> tuple[dict[str, Any], Path]:
    cfg_path = _config_path()
    if not cfg_path.exists():
        raise HTTPException(status_code=404, detail="config.json not found")
    with open(cfg_path, encoding="utf-8") as f:
        return json.load(f), cfg_path


def _save_config_json(data: dict[str, Any], cfg_path: Path) -> None:
    with open(cfg_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _default_runtime_state() -> dict[str, dict[str, Any]]:
    return {
        "bot_config": {},
        "chat_aliases": {},
        "group_policy": {},
    }


def _load_runtime_state() -> tuple[dict[str, Any], Path]:
    path = _runtime_state_path()
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        return _default_runtime_state(), path
    try:
        with open(path, encoding="utf-8") as f:
            payload = json.load(f)
    except Exception:
        payload = _default_runtime_state()
    merged = _default_runtime_state()
    if isinstance(payload, dict):
        for key in merged:
            if isinstance(payload.get(key), dict):
                merged[key] = payload[key]
    return merged, path


def _save_runtime_state(data: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _channel_chat_user_key(channel_name: str, chat_id: str = "*", user_id: str = "*") -> str:
    return f"{channel_name}::{chat_id or '*'}::{user_id or '*'}"


def _channel_chat_key(channel_name: str, chat_id: str = "*") -> str:
    return f"{channel_name}::{chat_id or '*'}"


def _resolve_channel_name(
    *,
    channel_name: str | None = None,
    platform: str | None = None,
    bot_id: str | None = None,
) -> str:
    if channel_name:
        return channel_name
    if platform and bot_id:
        return make_channel_name(platform, bot_id)
    raise HTTPException(status_code=400, detail="channel_name or (platform + bot_id) is required")


def _lookup_bot_entry(full_config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    bots = load_im_bots_from_config(full_config)
    return {
        make_channel_name(bot["platform"], bot["id"]): bot
        for bot in bots
    }


def _last_message_text(messages: list[dict[str, Any]]) -> str:
    for message in reversed(messages):
        if message.get("role") not in ("user", "assistant"):
            continue
        content = message.get("content", "")
        if isinstance(content, list):
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    text = str(item.get("text") or "")
                    if text:
                        return text[:120]
            continue
        return str(content)[:120]
    return ""


def _get_bot_config_value(runtime_state: dict[str, Any], channel_name: str, chat_id: str, user_id: str = "*") -> dict[str, Any] | None:
    bucket = runtime_state.get("bot_config", {})
    if not isinstance(bucket, dict):
        return None
    candidates = [
        _channel_chat_user_key(channel_name, chat_id, user_id),
        _channel_chat_user_key(channel_name, chat_id, "*"),
        _channel_chat_user_key(channel_name, "*", "*"),
    ]
    for key in candidates:
        value = bucket.get(key)
        if isinstance(value, dict):
            return value
    return None


def _get_chat_alias(runtime_state: dict[str, Any], channel_name: str, chat_id: str) -> str | None:
    bucket = runtime_state.get("chat_aliases", {})
    if not isinstance(bucket, dict):
        return None
    value = bucket.get(_channel_chat_key(channel_name, chat_id))
    if isinstance(value, dict):
        alias = value.get("alias")
        return str(alias) if alias else None
    return None


def _get_group_policy(runtime_state: dict[str, Any], channel_name: str, chat_id: str) -> dict[str, Any] | None:
    bucket = runtime_state.get("group_policy", {})
    if not isinstance(bucket, dict):
        return None
    value = bucket.get(_channel_chat_key(channel_name, chat_id))
    return value if isinstance(value, dict) else None


def _collect_session_entries(
    *,
    platform: str | None = None,
    bot_id: str | None = None,
    channel_name: str | None = None,
) -> list[dict[str, Any]]:
    sessions_dir = _APP_BASE / "data" / "sessions"
    if not sessions_dir.exists():
        return []

    full_config, _ = _load_config_json()
    bot_lookup = _lookup_bot_entry(full_config)
    runtime_state, _ = _load_runtime_state()
    entries: list[dict[str, Any]] = []

    for fpath in sessions_dir.glob("*.json"):
        sid = fpath.stem
        parsed = parse_im_session_id(sid)
        if not parsed:
            continue
        if platform and parsed["platform"] != platform:
            continue
        if bot_id and parsed["bot_id"] != bot_id:
            continue
        if channel_name and parsed["channel_name"] != channel_name:
            continue

        try:
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            continue

        messages = data.get("messages", []) if isinstance(data.get("messages"), list) else []
        metadata = data.get("metadata", {}) if isinstance(data.get("metadata"), dict) else {}
        channel = parsed["channel_name"]
        bot = bot_lookup.get(channel, {})
        alias = _get_chat_alias(runtime_state, channel, parsed["chat_id"])
        bot_config_value = _get_bot_config_value(runtime_state, channel, parsed["chat_id"])
        group_policy = _get_group_policy(runtime_state, channel, parsed["chat_id"])
        response_mode = None
        if isinstance(bot_config_value, dict):
            response_mode = bot_config_value.get("response_mode")
        if not response_mode and isinstance(group_policy, dict):
            response_mode = group_policy.get("response_mode")

        chat_name = str(metadata.get("chat_name") or parsed["chat_id"])
        display_name = str(
            alias
            or metadata.get("display_name")
            or metadata.get("chat_name")
            or parsed["chat_id"]
        )

        entries.append(
            {
                "id": sid,
                "session_id": sid,
                "channel": channel,
                "channel_name": channel,
                "platform": parsed["platform"],
                "bot_id": parsed["bot_id"],
                "chat_id": parsed["chat_id"],
                "chat_type": str(metadata.get("chat_type") or "private"),
                "chat_name": chat_name,
                "display_name": display_name,
                "alias": alias,
                "bot_enabled": bool(bot.get("enabled", True)),
                "response_mode": response_mode,
                "last_message": _last_message_text(messages),
                "message_count": len([m for m in messages if m.get("role") in ("user", "assistant")]),
                "updated_at": data.get("updated_at", "") or data.get("created_at", ""),
                "_mtime": fpath.stat().st_mtime,
            }
        )

    entries.sort(key=lambda item: item.get("_mtime", 0), reverse=True)
    for item in entries:
        item.pop("_mtime", None)
    return entries


class IMBotWriteRequest(BaseModel):
    id: str
    name: str
    platform: str
    enabled: bool = True
    credentials: dict[str, Any] = {}
    last_health: Optional[dict[str, Any]] = None


class IMBotUpdateRequest(BaseModel):
    id: Optional[str] = None
    name: str
    platform: str
    enabled: bool = True
    credentials: dict[str, Any] = {}
    last_health: Optional[dict[str, Any]] = None


class IMBotToggleRequest(BaseModel):
    enabled: bool


class IMBotHealthRequest(BaseModel):
    bot_id: Optional[str] = None
    platform: Optional[str] = None
    credentials: Optional[dict[str, Any]] = None
    persist: bool = False


class IMBotConfigRequest(BaseModel):
    channel_name: Optional[str] = None
    platform: Optional[str] = None
    bot_id: Optional[str] = None
    chat_id: str
    user_id: str = "*"
    enabled: bool = True
    response_mode: Optional[str] = None


class IMChatAliasRequest(BaseModel):
    channel_name: Optional[str] = None
    platform: Optional[str] = None
    bot_id: Optional[str] = None
    chat_id: str
    alias: str


class IMGroupPolicyRequest(BaseModel):
    channel_name: Optional[str] = None
    platform: Optional[str] = None
    bot_id: Optional[str] = None
    chat_id: str
    enabled: Optional[bool] = None
    response_mode: Optional[str] = None


class IMSelfcheckSubscriptionRequest(BaseModel):
    session_id: Optional[str] = None
    channel_name: Optional[str] = None
    platform: Optional[str] = None
    bot_id: Optional[str] = None
    chat_id: Optional[str] = None
    label: Optional[str] = None
    chat_name: Optional[str] = None


@router.get("/api/im/bots")
async def list_im_bots():
    full, _ = _load_config_json()
    bots = load_im_bots_from_config(full)
    return {
        "bots": bots,
        "supported_platforms": [
            {"id": platform, "name": PLATFORM_LABELS.get(platform, platform.title())}
            for platform in SUPPORTED_IM_PLATFORMS
        ],
        "coming_soon_platforms": [
            {"id": platform, "name": PLATFORM_LABELS.get(platform, platform.title())}
            for platform in COMING_SOON_IM_PLATFORMS
        ],
    }


@router.post("/api/im/bots")
async def create_im_bot(body: IMBotWriteRequest):
    full, cfg_path = _load_config_json()
    if get_im_bot(full, body.id):
        raise HTTPException(status_code=409, detail=f"Bot id={body.id!r} already exists")
    try:
        updated, bot = upsert_im_bot(full, body.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _save_config_json(updated, cfg_path)
    logger.info("[IM] Created bot platform=%s bot_id=%s requires_restart=true", body.platform, body.id)
    return {"status": "ok", "bot": bot, "requires_restart": True}


@router.put("/api/im/bots/{bot_id}")
async def update_im_bot(bot_id: str, body: IMBotUpdateRequest):
    full, cfg_path = _load_config_json()
    existing = get_im_bot(full, bot_id)
    if not existing:
        raise HTTPException(status_code=404, detail=f"Bot id={bot_id!r} not found")

    target_id = body.id or bot_id
    if target_id != bot_id and get_im_bot(full, target_id):
        raise HTTPException(status_code=409, detail=f"Bot id={target_id!r} already exists")

    next_config, _ = delete_im_bot(full, bot_id)
    try:
        updated, bot = upsert_im_bot(
            next_config,
            {
                "id": target_id,
                "name": body.name,
                "platform": body.platform,
                "enabled": body.enabled,
                "credentials": body.credentials,
                "last_health": body.last_health or existing.get("last_health"),
            },
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _save_config_json(updated, cfg_path)
    logger.info("[IM] Updated bot old_id=%s new_id=%s platform=%s", bot_id, bot["id"], body.platform)
    return {"status": "ok", "bot": bot, "requires_restart": True}


@router.delete("/api/im/bots/{bot_id}")
async def remove_im_bot(bot_id: str):
    full, cfg_path = _load_config_json()
    updated, deleted = delete_im_bot(full, bot_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Bot id={bot_id!r} not found")
    _save_config_json(updated, cfg_path)
    logger.info("[IM] Deleted bot bot_id=%s requires_restart=true", bot_id)
    return {"status": "ok", "deleted_id": bot_id, "requires_restart": True}


@router.post("/api/im/bots/{bot_id}/toggle")
async def toggle_im_bot(bot_id: str, body: IMBotToggleRequest):
    full, cfg_path = _load_config_json()
    updated, target = update_im_bot_toggle(full, bot_id, body.enabled)
    if not target:
        raise HTTPException(status_code=404, detail=f"Bot id={bot_id!r} not found")
    _save_config_json(updated, cfg_path)
    logger.info("[IM] Toggled bot bot_id=%s enabled=%s requires_restart=true", bot_id, body.enabled)
    return {"status": "ok", "bot": target, "requires_restart": True}


@router.post("/api/im/bots/health")
async def health_check_im_bot(body: IMBotHealthRequest):
    full, cfg_path = _load_config_json()
    payload_bot = get_im_bot(full, body.bot_id) if body.bot_id else None
    platform = (body.platform or (payload_bot or {}).get("platform") or "").strip().lower()
    credentials = clone_config((payload_bot or {}).get("credentials", {}))
    if isinstance(body.credentials, dict):
        credentials.update(body.credentials)

    if platform not in SUPPORTED_IM_PLATFORMS:
        raise HTTPException(status_code=400, detail="Unsupported or missing IM bot platform")

    health = await run_im_bot_healthcheck(platform, credentials)
    result = {
        "bot_id": body.bot_id,
        "platform": platform,
        "status": health["status"],
        "error": health.get("error"),
        "checked_at": health.get("checked_at"),
    }

    if body.persist and body.bot_id:
        updated, target = with_persisted_health(full, body.bot_id, health)
        if target:
            _save_config_json(updated, cfg_path)
            result["bot"] = target
    logger.info(
        "[IM] Healthcheck platform=%s bot_id=%s status=%s persist=%s",
        platform,
        body.bot_id,
        result["status"],
        body.persist,
    )

    return {"status": "ok", "result": result}


@router.get("/api/im/channels")
async def list_im_channels():
    """Return all configured IM bot channels and their runtime status."""
    full, _ = _load_config_json()
    bots = load_im_bots_from_config(full)
    gateway = app_state.get("gateway")
    adapters = gateway.adapters if gateway else {}
    sessions = _collect_session_entries()

    session_stats: dict[str, dict[str, Any]] = {}
    for session in sessions:
        item = session_stats.setdefault(
            session["channel_name"],
            {"session_count": 0, "last_active": None},
        )
        item["session_count"] += 1
        last_active = session.get("updated_at")
        if last_active and (not item["last_active"] or last_active > item["last_active"]):
            item["last_active"] = last_active

    channels = []
    for bot in bots:
        channel_name = make_channel_name(bot["platform"], bot["id"])
        adapter = adapters.get(channel_name)
        is_online = bool(adapter and getattr(adapter, "_running", False))
        stream_state = getattr(adapter, "_stream_state", None)
        if hasattr(stream_state, "value"):
            stream_state = stream_state.value
        stats = session_stats.get(channel_name, {})
        channels.append(
            {
                "id": channel_name,
                "channel_name": channel_name,
                "platform": bot["platform"],
                "bot_id": bot["id"],
                "name": bot["name"],
                "display_name": bot["name"],
                "status": "online" if is_online else "offline",
                "enabled": bot["enabled"],
                "stream_state": stream_state,
                "last_error": getattr(adapter, "_last_error", None) if adapter else None,
                "session_count": int(stats.get("session_count", 0)),
                "last_active": stats.get("last_active"),
            }
        )

    return {"channels": channels}


@router.get("/api/im/sessions")
async def list_im_sessions(
    platform: Optional[str] = None,
    bot_id: Optional[str] = None,
    channel_name: Optional[str] = None,
):
    """Return IM sessions, optionally filtered by platform, bot instance or channel name."""
    sessions = _collect_session_entries(
        platform=platform,
        bot_id=bot_id,
        channel_name=channel_name,
    )
    subscribed_ids = {
        item["session_id"]
        for item in list_selfcheck_subscriptions(base_path=_APP_BASE, session_entries=sessions)
    }
    return {
        "sessions": [
            {
                **item,
                "selfcheck_subscribed": item["session_id"] in subscribed_ids,
            }
            for item in sessions
        ]
    }


@router.get("/api/im/selfcheck-subscriptions")
async def list_im_selfcheck_subscriptions():
    sessions = _collect_session_entries()
    return {"subscriptions": list_selfcheck_subscriptions(base_path=_APP_BASE, session_entries=sessions)}


@router.post("/api/im/selfcheck-subscriptions")
async def create_im_selfcheck_subscription(body: IMSelfcheckSubscriptionRequest):
    sessions = _collect_session_entries()
    resolved_channel_name = body.channel_name
    if not resolved_channel_name and (body.platform and body.bot_id):
        resolved_channel_name = _resolve_channel_name(platform=body.platform, bot_id=body.bot_id)
    try:
        subscriptions = upsert_selfcheck_subscription(
            session_id=body.session_id,
            channel_name=resolved_channel_name,
            chat_id=body.chat_id,
            label=body.label,
            chat_name=body.chat_name,
            bot_id=body.bot_id,
            platform=body.platform,
            base_path=_APP_BASE,
            session_entries=sessions,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "ok", "subscriptions": subscriptions}


@router.delete("/api/im/selfcheck-subscriptions")
async def delete_im_selfcheck_subscription(
    session_id: Optional[str] = None,
    channel_name: Optional[str] = None,
    platform: Optional[str] = None,
    bot_id: Optional[str] = None,
    chat_id: Optional[str] = None,
):
    sessions = _collect_session_entries()
    resolved_channel_name = channel_name
    if not resolved_channel_name and (platform and bot_id):
        resolved_channel_name = _resolve_channel_name(platform=platform, bot_id=bot_id)
    try:
        deleted = remove_selfcheck_subscription(
            session_id=session_id,
            channel_name=resolved_channel_name,
            chat_id=chat_id,
            base_path=_APP_BASE,
            session_entries=sessions,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "status": "ok",
        "deleted": deleted,
        "subscriptions": list_selfcheck_subscriptions(base_path=_APP_BASE, session_entries=sessions),
    }


@router.get("/api/im/bot-config")
async def list_im_bot_config(
    channel_name: Optional[str] = None,
    platform: Optional[str] = None,
    bot_id: Optional[str] = None,
    chat_id: Optional[str] = None,
    user_id: Optional[str] = None,
):
    runtime_state, _ = _load_runtime_state()
    resolved_channel = None
    if channel_name or (platform and bot_id):
        resolved_channel = _resolve_channel_name(channel_name=channel_name, platform=platform, bot_id=bot_id)
    items = []
    for key, value in runtime_state["bot_config"].items():
        if not isinstance(value, dict):
            continue
        channel, item_chat_id, item_user_id = (key.split("::", 2) + ["*", "*"])[:3]
        if resolved_channel and channel != resolved_channel:
            continue
        if chat_id and item_chat_id != chat_id:
            continue
        if user_id and item_user_id != user_id:
            continue
        items.append(
            {
                "channel_name": channel,
                "chat_id": item_chat_id,
                "user_id": item_user_id,
                "enabled": bool(value.get("enabled", True)),
                "response_mode": value.get("response_mode"),
            }
        )
    return {"items": items}


@router.post("/api/im/bot-config")
async def upsert_im_bot_config(body: IMBotConfigRequest):
    runtime_state, runtime_path = _load_runtime_state()
    channel_name = _resolve_channel_name(channel_name=body.channel_name, platform=body.platform, bot_id=body.bot_id)
    runtime_state["bot_config"][_channel_chat_user_key(channel_name, body.chat_id, body.user_id)] = {
        "enabled": body.enabled,
        "response_mode": body.response_mode,
    }
    _save_runtime_state(runtime_state, runtime_path)
    logger.info(
        "[IM] Upsert bot-config channel=%s chat_id=%s user_id=%s enabled=%s response_mode=%s",
        channel_name,
        body.chat_id,
        body.user_id,
        body.enabled,
        body.response_mode,
    )
    return {"status": "ok"}


@router.delete("/api/im/bot-config")
async def delete_im_bot_config(
    channel_name: Optional[str] = None,
    platform: Optional[str] = None,
    bot_id: Optional[str] = None,
    chat_id: str = Query(...),
    user_id: str = Query("*"),
):
    runtime_state, runtime_path = _load_runtime_state()
    resolved_channel = _resolve_channel_name(channel_name=channel_name, platform=platform, bot_id=bot_id)
    deleted = runtime_state["bot_config"].pop(_channel_chat_user_key(resolved_channel, chat_id, user_id), None) is not None
    _save_runtime_state(runtime_state, runtime_path)
    logger.info("[IM] Delete bot-config channel=%s chat_id=%s user_id=%s deleted=%s", resolved_channel, chat_id, user_id, deleted)
    return {"status": "ok", "deleted": deleted}


@router.get("/api/im/chat-aliases")
async def list_im_chat_aliases(
    channel_name: Optional[str] = None,
    platform: Optional[str] = None,
    bot_id: Optional[str] = None,
    chat_id: Optional[str] = None,
):
    runtime_state, _ = _load_runtime_state()
    resolved_channel = None
    if channel_name or (platform and bot_id):
        resolved_channel = _resolve_channel_name(channel_name=channel_name, platform=platform, bot_id=bot_id)
    items = []
    for key, value in runtime_state["chat_aliases"].items():
        if not isinstance(value, dict):
            continue
        channel, item_chat_id = (key.split("::", 1) + ["*"])[:2]
        if resolved_channel and channel != resolved_channel:
            continue
        if chat_id and item_chat_id != chat_id:
            continue
        items.append(
            {
                "channel_name": channel,
                "chat_id": item_chat_id,
                "alias": value.get("alias"),
            }
        )
    return {"items": items}


@router.post("/api/im/chat-aliases")
async def upsert_im_chat_alias(body: IMChatAliasRequest):
    runtime_state, runtime_path = _load_runtime_state()
    channel_name = _resolve_channel_name(channel_name=body.channel_name, platform=body.platform, bot_id=body.bot_id)
    runtime_state["chat_aliases"][_channel_chat_key(channel_name, body.chat_id)] = {"alias": body.alias}
    _save_runtime_state(runtime_state, runtime_path)
    logger.info("[IM] Upsert chat-alias channel=%s chat_id=%s alias=%s", channel_name, body.chat_id, body.alias)
    return {"status": "ok"}


@router.delete("/api/im/chat-aliases")
async def delete_im_chat_alias(
    channel_name: Optional[str] = None,
    platform: Optional[str] = None,
    bot_id: Optional[str] = None,
    chat_id: str = Query(...),
):
    runtime_state, runtime_path = _load_runtime_state()
    resolved_channel = _resolve_channel_name(channel_name=channel_name, platform=platform, bot_id=bot_id)
    deleted = runtime_state["chat_aliases"].pop(_channel_chat_key(resolved_channel, chat_id), None) is not None
    _save_runtime_state(runtime_state, runtime_path)
    logger.info("[IM] Delete chat-alias channel=%s chat_id=%s deleted=%s", resolved_channel, chat_id, deleted)
    return {"status": "ok", "deleted": deleted}


@router.get("/api/im/group-policy")
async def list_im_group_policy(
    channel_name: Optional[str] = None,
    platform: Optional[str] = None,
    bot_id: Optional[str] = None,
    chat_id: Optional[str] = None,
):
    runtime_state, _ = _load_runtime_state()
    resolved_channel = None
    if channel_name or (platform and bot_id):
        resolved_channel = _resolve_channel_name(channel_name=channel_name, platform=platform, bot_id=bot_id)
    items = []
    for key, value in runtime_state["group_policy"].items():
        if not isinstance(value, dict):
            continue
        channel, item_chat_id = (key.split("::", 1) + ["*"])[:2]
        if resolved_channel and channel != resolved_channel:
            continue
        if chat_id and item_chat_id != chat_id:
            continue
        items.append(
            {
                "channel_name": channel,
                "chat_id": item_chat_id,
                "enabled": value.get("enabled"),
                "response_mode": value.get("response_mode"),
            }
        )
    return {"items": items}


@router.post("/api/im/group-policy")
async def upsert_im_group_policy(body: IMGroupPolicyRequest):
    runtime_state, runtime_path = _load_runtime_state()
    channel_name = _resolve_channel_name(channel_name=body.channel_name, platform=body.platform, bot_id=body.bot_id)
    runtime_state["group_policy"][_channel_chat_key(channel_name, body.chat_id)] = {
        "enabled": body.enabled,
        "response_mode": body.response_mode,
    }
    _save_runtime_state(runtime_state, runtime_path)
    logger.info(
        "[IM] Upsert group-policy channel=%s chat_id=%s enabled=%s response_mode=%s",
        channel_name,
        body.chat_id,
        body.enabled,
        body.response_mode,
    )
    return {"status": "ok"}

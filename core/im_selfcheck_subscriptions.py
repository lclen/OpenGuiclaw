from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from core.im_bots import load_im_bots_from_config, make_channel_name, make_im_session_id, parse_im_session_id
from core.state import _APP_BASE, logger


def _subscriptions_path(base_path: Path | None = None) -> Path:
    root = base_path or _APP_BASE
    return root / "data" / "im" / "selfcheck_subscriptions.json"


def _default_payload() -> dict[str, list[dict[str, Any]]]:
    return {"subscriptions": []}


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _load_config_bots(base_path: Path | None = None) -> dict[str, dict[str, Any]]:
    root = base_path or _APP_BASE
    config_path = root / "config.json"
    if not config_path.exists():
        return {}
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except Exception as exc:
        logger.warning("Failed to load IM bot config for selfcheck subscriptions: %s", exc)
        return {}
    return {
        make_channel_name(bot["platform"], bot["id"]): bot
        for bot in load_im_bots_from_config(payload)
    }


def _load_payload(base_path: Path | None = None) -> tuple[dict[str, Any], Path]:
    path = _subscriptions_path(base_path)
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        return _default_payload(), path
    try:
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except Exception:
        payload = _default_payload()
    if not isinstance(payload, dict):
        payload = _default_payload()
    raw_items = payload.get("subscriptions")
    if not isinstance(raw_items, list):
        raw_items = []
    return {"subscriptions": raw_items}, path


def _save_payload(payload: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def _normalize_subscription(
    raw: Any,
    *,
    default_session_id: str | None = None,
    session_lookup: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None

    session_id = str(raw.get("session_id") or default_session_id or "").strip()
    channel_name = str(raw.get("channel_name") or "").strip()
    chat_id = str(raw.get("chat_id") or "").strip()

    parsed = parse_im_session_id(session_id) if session_id else None
    if parsed:
        channel_name = channel_name or parsed["channel_name"]
        chat_id = chat_id or parsed["chat_id"]
    elif channel_name and chat_id:
        session_id = make_im_session_id(channel_name, chat_id)
        parsed = parse_im_session_id(session_id)

    if not session_id or not channel_name or not chat_id:
        return None

    session_info = session_lookup.get(session_id, {}) if session_lookup else {}
    now = _now_iso()
    created_at = str(raw.get("created_at") or session_info.get("created_at") or now)
    updated_at = str(raw.get("updated_at") or created_at)
    label = str(raw.get("label") or session_info.get("display_name") or session_info.get("chat_name") or "").strip() or None
    chat_name = str(raw.get("chat_name") or session_info.get("chat_name") or "").strip() or None
    bot_id = str(raw.get("bot_id") or session_info.get("bot_id") or (parsed or {}).get("bot_id") or "").strip() or None
    platform = str(raw.get("platform") or session_info.get("platform") or (parsed or {}).get("platform") or "").strip() or None
    last_sent_at = str(raw.get("last_sent_at") or "").strip() or None
    last_status = str(raw.get("last_status") or "").strip() or None
    last_error = str(raw.get("last_error") or "").strip() or None

    return {
        "session_id": session_id,
        "channel_name": channel_name,
        "chat_id": chat_id,
        "enabled": bool(raw.get("enabled", True)),
        "created_at": created_at,
        "updated_at": updated_at,
        "label": label,
        "chat_name": chat_name,
        "bot_id": bot_id,
        "platform": platform,
        "last_sent_at": last_sent_at,
        "last_status": last_status,
        "last_error": last_error,
    }


def _session_lookup(session_entries: list[dict[str, Any]] | None) -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}
    for item in session_entries or []:
        if not isinstance(item, dict):
            continue
        session_id = str(item.get("session_id") or item.get("id") or "").strip()
        if session_id:
            lookup[session_id] = item
    return lookup


def list_selfcheck_subscriptions(
    *,
    base_path: Path | None = None,
    session_entries: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    payload, _ = _load_payload(base_path)
    session_lookup = _session_lookup(session_entries)
    bots = _load_config_bots(base_path)
    items: list[dict[str, Any]] = []
    seen: set[str] = set()

    for raw in payload.get("subscriptions", []):
        item = _normalize_subscription(raw, session_lookup=session_lookup)
        if not item:
            continue
        session_id = item["session_id"]
        if session_id in seen:
            continue
        seen.add(session_id)

        session_info = session_lookup.get(session_id, {})
        channel_name = item["channel_name"]
        bot = bots.get(channel_name)
        valid = True
        invalid_reason = None
        if not bot:
            valid = False
            invalid_reason = "bot_missing"
        elif not bot.get("enabled", True):
            valid = False
            invalid_reason = "bot_disabled"
        elif not item["chat_id"]:
            valid = False
            invalid_reason = "chat_missing"

        item["display_name"] = (
            session_info.get("alias")
            or session_info.get("display_name")
            or item.get("label")
            or item["chat_id"]
        )
        item["alias"] = session_info.get("alias")
        item["chat_name"] = session_info.get("chat_name") or item.get("chat_name")
        item["chat_type"] = session_info.get("chat_type")
        item["updated_at"] = session_info.get("updated_at") or item["updated_at"]
        item["last_active"] = session_info.get("updated_at")
        item["message_count"] = session_info.get("message_count")
        item["last_message"] = session_info.get("last_message")
        item["valid"] = valid
        item["invalid_reason"] = invalid_reason
        item["bot_enabled"] = bool(bot.get("enabled", True)) if bot else False
        items.append(item)

    items.sort(key=lambda entry: str(entry.get("updated_at") or entry.get("created_at") or ""), reverse=True)
    return items


def list_active_selfcheck_subscriptions(
    *,
    base_path: Path | None = None,
    session_entries: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    return [
        item
        for item in list_selfcheck_subscriptions(base_path=base_path, session_entries=session_entries)
        if item.get("enabled") and item.get("valid")
    ]


def upsert_selfcheck_subscription(
    *,
    session_id: str | None = None,
    channel_name: str | None = None,
    chat_id: str | None = None,
    label: str | None = None,
    chat_name: str | None = None,
    bot_id: str | None = None,
    platform: str | None = None,
    base_path: Path | None = None,
    session_entries: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    payload, path = _load_payload(base_path)
    session_lookup = _session_lookup(session_entries)
    normalized = _normalize_subscription(
        {
            "session_id": session_id,
            "channel_name": channel_name,
            "chat_id": chat_id,
            "enabled": True,
            "label": label,
            "chat_name": chat_name,
            "bot_id": bot_id,
            "platform": platform,
        },
        session_lookup=session_lookup,
    )
    if not normalized:
        raise ValueError("session_id or (channel_name + chat_id) is required")

    now = _now_iso()
    next_items: list[dict[str, Any]] = []
    replaced = False
    for raw in payload.get("subscriptions", []):
        item = _normalize_subscription(raw, session_lookup=session_lookup)
        if not item:
            continue
        if item["session_id"] == normalized["session_id"]:
            item.update(
                {
                    "enabled": True,
                    "updated_at": now,
                    "label": normalized.get("label") or item.get("label"),
                    "chat_name": normalized.get("chat_name") or item.get("chat_name"),
                    "bot_id": normalized.get("bot_id") or item.get("bot_id"),
                    "platform": normalized.get("platform") or item.get("platform"),
                }
            )
            next_items.append(item)
            replaced = True
            continue
        next_items.append(item)

    if not replaced:
        normalized["created_at"] = now
        normalized["updated_at"] = now
        next_items.append(normalized)

    payload["subscriptions"] = next_items
    _save_payload(payload, path)
    return list_selfcheck_subscriptions(base_path=base_path, session_entries=session_entries)


def remove_selfcheck_subscription(
    *,
    session_id: str | None = None,
    channel_name: str | None = None,
    chat_id: str | None = None,
    base_path: Path | None = None,
    session_entries: list[dict[str, Any]] | None = None,
) -> bool:
    payload, path = _load_payload(base_path)
    session_lookup = _session_lookup(session_entries)
    normalized = _normalize_subscription(
        {
            "session_id": session_id,
            "channel_name": channel_name,
            "chat_id": chat_id,
        },
        session_lookup=session_lookup,
    )
    if not normalized:
        raise ValueError("session_id or (channel_name + chat_id) is required")

    target_session_id = normalized["session_id"]
    next_items: list[dict[str, Any]] = []
    removed = False
    for raw in payload.get("subscriptions", []):
        item = _normalize_subscription(raw, session_lookup=session_lookup)
        if not item:
            continue
        if item["session_id"] == target_session_id:
            removed = True
            continue
        next_items.append(item)
    if removed:
        payload["subscriptions"] = next_items
        _save_payload(payload, path)
    return removed


def record_selfcheck_delivery_status(
    session_id: str,
    *,
    status: str,
    error: str | None = None,
    base_path: Path | None = None,
    session_entries: list[dict[str, Any]] | None = None,
) -> None:
    if not session_id:
        return
    payload, path = _load_payload(base_path)
    session_lookup = _session_lookup(session_entries)
    now = _now_iso()
    changed = False
    next_items: list[dict[str, Any]] = []

    for raw in payload.get("subscriptions", []):
        item = _normalize_subscription(raw, session_lookup=session_lookup)
        if not item:
            continue
        if item["session_id"] == session_id:
            item["last_sent_at"] = now
            item["last_status"] = status
            item["last_error"] = str(error)[:500] if error else None
            item["updated_at"] = now
            changed = True
        next_items.append(item)

    if changed:
        payload["subscriptions"] = next_items
        _save_payload(payload, path)

"""
IM bot configuration helpers.

This module centralises:
- `im_bots` <-> legacy `channels` compatibility
- multi-instance channel/session identifiers
- lightweight validation and health checks
"""

from __future__ import annotations

import re
import time
from copy import deepcopy
from typing import Any

import httpx

SUPPORTED_IM_PLATFORMS = ("telegram", "feishu", "dingtalk")
COMING_SOON_IM_PLATFORMS = ("wework", "wechat", "qqbot")

PLATFORM_LABELS = {
    "telegram": "Telegram",
    "feishu": "飞书",
    "dingtalk": "钉钉",
    "wework": "企业微信",
    "wechat": "微信",
    "qqbot": "QQ Bot",
}

PLATFORM_CREDENTIAL_FIELDS: dict[str, tuple[str, ...]] = {
    "telegram": ("bot_token", "proxy", "pairing_code", "webhook_url"),
    "feishu": ("app_id", "app_secret", "verification_token", "encrypt_key"),
    "dingtalk": ("client_id", "client_secret", "agent_id", "footer_elapsed", "footer_status"),
}

LEGACY_CHANNEL_FIELDS: dict[str, tuple[str, ...]] = {
    "telegram": ("bot_token", "proxy", "pairing_code", "webhook_url"),
    "feishu": ("app_id", "app_secret", "verification_token", "encrypt_key"),
    "dingtalk": ("client_id", "client_secret", "agent_id"),
}

REQUIRED_CREDENTIAL_FIELDS: dict[str, tuple[str, ...]] = {
    "telegram": ("bot_token",),
    "feishu": ("app_id", "app_secret"),
    "dingtalk": ("client_id", "client_secret"),
}

CHANNEL_NAME_DELIMITER = "@@"
IM_SESSION_DELIMITER = "___"
BOT_ID_PATTERN = re.compile(r"[^a-z0-9_-]+")
CHANNEL_NAME_PATTERN = re.compile(rf"^({'|'.join(SUPPORTED_IM_PLATFORMS)}){re.escape(CHANNEL_NAME_DELIMITER)}(.+)$")


def default_platform_credentials(platform: str) -> dict[str, Any]:
    defaults: dict[str, Any] = {field: "" for field in PLATFORM_CREDENTIAL_FIELDS.get(platform, ())}
    if platform == "dingtalk":
        defaults["footer_elapsed"] = True
        defaults["footer_status"] = True
    return defaults


def default_legacy_channel_credentials(platform: str) -> dict[str, str]:
    return {field: "" for field in LEGACY_CHANNEL_FIELDS.get(platform, ())}


def _normalize_boolish(value: Any, default: bool = True) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"true", "1", "yes", "on"}:
        return True
    if text in {"false", "0", "no", "off"}:
        return False
    return default


def sanitize_bot_id(value: str | None, fallback: str = "bot") -> str:
    cleaned = BOT_ID_PATTERN.sub("-", (value or "").strip().lower()).strip("-_")
    return cleaned or fallback


def default_bot_name(platform: str, index: int = 1) -> str:
    return f"{PLATFORM_LABELS.get(platform, platform.title())} #{index}"


def make_channel_name(platform: str, bot_id: str) -> str:
    return f"{platform}{CHANNEL_NAME_DELIMITER}{sanitize_bot_id(bot_id, platform)}"


def parse_channel_name(channel_name: str | None) -> tuple[str | None, str | None]:
    if not channel_name:
        return None, None
    match = CHANNEL_NAME_PATTERN.match(channel_name)
    if match:
        return match.group(1), match.group(2)
    if channel_name in SUPPORTED_IM_PLATFORMS:
        return channel_name, channel_name
    return None, None


def make_im_session_id(channel_name: str, chat_id: str | None) -> str:
    return f"{channel_name}{IM_SESSION_DELIMITER}{chat_id or ''}"


def parse_im_session_id(session_id: str | None) -> dict[str, str] | None:
    if not session_id:
        return None
    if IM_SESSION_DELIMITER in session_id:
        channel_name, chat_id = session_id.split(IM_SESSION_DELIMITER, 1)
        platform, bot_id = parse_channel_name(channel_name)
        if platform and bot_id:
            return {
                "platform": platform,
                "bot_id": bot_id,
                "channel_name": channel_name,
                "chat_id": chat_id,
            }
    for platform in SUPPORTED_IM_PLATFORMS:
        prefix = f"{platform}_"
        if session_id.startswith(prefix):
            return {
                "platform": platform,
                "bot_id": platform,
                "channel_name": platform,
                "chat_id": session_id[len(prefix):],
            }
    return None


def is_im_session_id(session_id: str | None) -> bool:
    return parse_im_session_id(session_id) is not None


def _normalize_last_health(payload: Any) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    status = str(payload.get("status") or "").strip() or "unknown"
    checked_at = payload.get("checked_at") or payload.get("last_checked_at")
    error = payload.get("error")
    return {
        "status": status,
        "error": str(error)[:500] if error else None,
        "checked_at": checked_at,
    }


def normalize_im_bot(raw: Any, *, index: int = 1) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    platform = str(raw.get("platform") or raw.get("type") or "").strip().lower()
    if platform not in SUPPORTED_IM_PLATFORMS:
        return None
    raw_credentials = raw.get("credentials") if isinstance(raw.get("credentials"), dict) else {}
    credentials = default_platform_credentials(platform)
    for field in credentials:
        value = raw_credentials.get(field)
        if platform == "dingtalk" and field in {"footer_elapsed", "footer_status"}:
            credentials[field] = _normalize_boolish(value, default=True)
        else:
            credentials[field] = "" if value is None else str(value)
    raw_id = str(raw.get("id") or "").strip()
    bot_id = sanitize_bot_id(raw_id, fallback=f"{platform}-{index}")
    name = str(raw.get("name") or "").strip() or default_bot_name(platform, index)
    enabled = bool(raw.get("enabled", True))
    return {
        "id": bot_id,
        "name": name,
        "platform": platform,
        "enabled": enabled,
        "credentials": credentials,
        "last_health": _normalize_last_health(raw.get("last_health")),
    }


def has_any_credentials(platform: str, credentials: dict[str, Any] | None) -> bool:
    if not isinstance(credentials, dict):
        return False
    for field in LEGACY_CHANNEL_FIELDS.get(platform, ()):
        value = credentials.get(field)
        if isinstance(value, str) and value.strip():
            return True
        if value not in (None, ""):
            return True
    return False


def migrate_channels_to_im_bots(channels: Any) -> list[dict[str, Any]]:
    if not isinstance(channels, dict):
        return []
    bots: list[dict[str, Any]] = []
    index = 1
    for platform in SUPPORTED_IM_PLATFORMS:
        platform_cfg = channels.get(platform)
        if not isinstance(platform_cfg, dict):
            continue
        if not has_any_credentials(platform, platform_cfg):
            continue
        normalized = normalize_im_bot(
            {
                "id": platform,
                "name": default_bot_name(platform, index),
                "platform": platform,
                "enabled": True,
                "credentials": {
                    **platform_cfg,
                    **(
                        {"footer_elapsed": True, "footer_status": True}
                        if platform == "dingtalk"
                        else {}
                    ),
                },
            },
            index=index,
        )
        if normalized:
            bots.append(normalized)
            index += 1
    return bots


def derive_legacy_channels(bots: list[dict[str, Any]]) -> dict[str, dict[str, str]]:
    derived = {platform: default_legacy_channel_credentials(platform) for platform in SUPPORTED_IM_PLATFORMS}
    for platform in SUPPORTED_IM_PLATFORMS:
        matching = [bot for bot in bots if bot.get("platform") == platform]
        preferred = next((bot for bot in matching if bot.get("enabled")), None) or (matching[0] if matching else None)
        if not preferred:
            continue
        credentials = preferred.get("credentials") if isinstance(preferred.get("credentials"), dict) else {}
        for field in derived[platform]:
            value = credentials.get(field)
            derived[platform][field] = "" if value is None else str(value)
    return derived


def load_im_bots_from_config(full_config: dict[str, Any]) -> list[dict[str, Any]]:
    raw_bots = full_config.get("im_bots")
    if isinstance(raw_bots, list):
        normalized: list[dict[str, Any]] = []
        for index, raw in enumerate(raw_bots, start=1):
            bot = normalize_im_bot(raw, index=index)
            if bot:
                normalized.append(bot)
        if normalized:
            return normalized
    return migrate_channels_to_im_bots(full_config.get("channels"))


def sync_im_bots_into_config(full_config: dict[str, Any], bots: list[dict[str, Any]]) -> dict[str, Any]:
    normalized: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for index, raw in enumerate(bots, start=1):
        bot = normalize_im_bot(raw, index=index)
        if not bot:
            continue
        base_id = bot["id"]
        deduped_id = base_id
        suffix = 2
        while deduped_id in seen_ids:
            deduped_id = f"{base_id}-{suffix}"
            suffix += 1
        if deduped_id != bot["id"]:
            bot = {**bot, "id": deduped_id}
        seen_ids.add(bot["id"])
        normalized.append(bot)
    full_config["im_bots"] = normalized
    full_config["channels"] = derive_legacy_channels(normalized)
    return full_config


def upsert_im_bot(full_config: dict[str, Any], payload: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    bots = load_im_bots_from_config(full_config)
    incoming = normalize_im_bot(payload, index=len(bots) + 1)
    if not incoming:
        raise ValueError("Unsupported IM bot platform")
    existing_index = next((idx for idx, bot in enumerate(bots) if bot["id"] == incoming["id"]), None)
    if existing_index is None:
        bots.append(incoming)
    else:
        preserved_health = bots[existing_index].get("last_health")
        bots[existing_index] = {
            **incoming,
            "last_health": incoming.get("last_health") or preserved_health,
        }
    sync_im_bots_into_config(full_config, bots)
    saved = next(bot for bot in full_config["im_bots"] if bot["id"] == incoming["id"])
    return full_config, saved


def delete_im_bot(full_config: dict[str, Any], bot_id: str) -> tuple[dict[str, Any], bool]:
    bots = load_im_bots_from_config(full_config)
    next_bots = [bot for bot in bots if bot["id"] != bot_id]
    deleted = len(next_bots) != len(bots)
    sync_im_bots_into_config(full_config, next_bots)
    return full_config, deleted


def update_im_bot_toggle(full_config: dict[str, Any], bot_id: str, enabled: bool) -> tuple[dict[str, Any], dict[str, Any] | None]:
    bots = load_im_bots_from_config(full_config)
    target: dict[str, Any] | None = None
    for bot in bots:
        if bot["id"] == bot_id:
            bot["enabled"] = bool(enabled)
            target = bot
            break
    sync_im_bots_into_config(full_config, bots)
    return full_config, target


def get_im_bot(full_config: dict[str, Any], bot_id: str) -> dict[str, Any] | None:
    return next((bot for bot in load_im_bots_from_config(full_config) if bot["id"] == bot_id), None)


def validate_required_credentials(platform: str, credentials: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    for field in REQUIRED_CREDENTIAL_FIELDS.get(platform, ()):
        value = credentials.get(field)
        if not isinstance(value, str) or not value.strip():
            missing.append(field)
    return missing


async def run_im_bot_healthcheck(platform: str, credentials: dict[str, Any]) -> dict[str, Any]:
    checked_at = time.strftime("%Y-%m-%dT%H:%M:%S")
    missing = validate_required_credentials(platform, credentials)
    if missing:
        return {
            "status": "unhealthy",
            "error": f"缺少必填配置: {', '.join(missing)}",
            "checked_at": checked_at,
        }

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            if platform == "telegram":
                token = str(credentials.get("bot_token") or "").strip()
                proxy = str(credentials.get("proxy") or "").strip()
                if proxy:
                    async with httpx.AsyncClient(proxy=proxy, timeout=15) as proxy_client:
                        resp = await proxy_client.get(f"https://api.telegram.org/bot{token}/getMe")
                else:
                    resp = await client.get(f"https://api.telegram.org/bot{token}/getMe")
                resp.raise_for_status()
                data = resp.json()
                if not data.get("ok"):
                    raise RuntimeError(data.get("description", "Telegram API 返回错误"))
            elif platform == "feishu":
                resp = await client.post(
                    "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
                    json={
                        "app_id": str(credentials.get("app_id") or "").strip(),
                        "app_secret": str(credentials.get("app_secret") or "").strip(),
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                if data.get("code", -1) != 0:
                    raise RuntimeError(data.get("msg", "飞书验证失败"))
            elif platform == "dingtalk":
                resp = await client.post(
                    "https://api.dingtalk.com/v1.0/oauth2/accessToken",
                    json={
                        "appKey": str(credentials.get("client_id") or "").strip(),
                        "appSecret": str(credentials.get("client_secret") or "").strip(),
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                if not data.get("accessToken"):
                    raise RuntimeError(data.get("message", "钉钉验证失败"))
            else:
                raise RuntimeError(f"暂不支持平台: {platform}")
    except Exception as exc:
        return {
            "status": "unhealthy",
            "error": str(exc)[:500],
            "checked_at": checked_at,
        }

    return {
        "status": "healthy",
        "error": None,
        "checked_at": checked_at,
    }


def with_persisted_health(full_config: dict[str, Any], bot_id: str, health: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any] | None]:
    bots = load_im_bots_from_config(full_config)
    target: dict[str, Any] | None = None
    for bot in bots:
        if bot["id"] == bot_id:
            bot["last_health"] = _normalize_last_health(health)
            target = bot
            break
    sync_im_bots_into_config(full_config, bots)
    return full_config, target


def clone_config(data: dict[str, Any]) -> dict[str, Any]:
    return deepcopy(data)

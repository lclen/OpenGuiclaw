"""Shared runtime diagnostics helpers for diagnostics UI and automated selfcheck."""

from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import platform
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx

from core.im_bots import (
    load_im_bots_from_config,
    make_channel_name,
    parse_im_session_id,
    validate_required_credentials,
)
from core.process_runtime import collect_process_runtime, detect_runtime_mode
from core.state import app_state

ROLE_HEALTH_LABELS = {
    "api": "主模型",
    "vision": "视觉模型",
    "image_analyzer": "图像解析",
    "embedding": "嵌入模型",
    "autogui": "GUI 操作",
}

DIAGNOSTIC_DEPENDENCIES = ["fastapi", "uvicorn", "webview", "playwright", "mss", "numpy", "psutil"]
CONNECTIVITY_CHECK_URL = "https://mirrors.aliyun.com/"
NETWORK_MATRIX_PROFILES = [
    {"name": "default", "label": "默认网络", "no_proxy": False, "ipv4": False},
    {"name": "no_proxy", "label": "禁用代理", "no_proxy": True, "ipv4": False},
    {"name": "ipv4", "label": "强制 IPv4", "no_proxy": False, "ipv4": True},
    {"name": "no_proxy_ipv4", "label": "禁用代理 + IPv4", "no_proxy": True, "ipv4": True},
]


def safe_text(value: Any) -> str:
    return str(value or "").strip()


def load_config_json_optional(app_base: Path) -> tuple[dict[str, Any], Path]:
    cfg_path = app_base / "config.json"
    if not cfg_path.exists():
        return {}, cfg_path
    with open(cfg_path, encoding="utf-8") as f:
        payload = json.load(f)
    return payload if isinstance(payload, dict) else {}, cfg_path


def classify_health_error(exc: Exception) -> tuple[str, str, str]:
    raw = str(exc).strip()
    lowered = raw.lower()

    if "401" in lowered or "unauthorized" in lowered or "invalid_api_key" in lowered or "authentication" in lowered:
        return ("auth_failed", "API Key 无效或已过期", "请检查 API Key 是否正确，或确认服务端是否要求鉴权")
    if "403" in lowered or "forbidden" in lowered or "permission" in lowered:
        return ("permission_denied", "API Key 权限不足", "请检查当前 Key 的模型权限、组织权限或访问范围")
    if "404" in lowered or "not found" in lowered:
        return ("model_or_route_not_found", "模型不存在，或服务接口不可用", "请检查模型名、Base URL 与服务商协议路径是否匹配")
    if "timeout" in lowered or "timed out" in lowered:
        return ("timeout", "请求超时，请检查网络、代理或服务负载", "请检查代理、网络质量，或稍后重试")
    if (
        "connection refused" in lowered
        or "connect" in lowered
        or "unreachable" in lowered
        or "name resolution" in lowered
        or "nodename nor servname provided" in lowered
        or "temporary failure in name resolution" in lowered
    ):
        return ("connection_failed", "无法连接到服务，请检查 Base URL、网络或代理", "请检查 Base URL 是否可访问，并确认代理配置是否生效")
    if not raw:
        return ("unknown_error", "健康检查失败", "请查看服务端日志或复制完整错误继续排查")
    return ("unknown_error", raw[:240], "请查看服务端日志或复制完整错误继续排查")


def build_probe_result(
    target: dict[str, Any],
    *,
    status: str,
    latency_ms: int | None,
    error: str | None,
    error_code: str | None,
    hint: str | None,
    configured: bool,
    probe_mode: str | None = None,
    probe_label: str | None = None,
) -> dict[str, Any]:
    result = {
        "name": target["name"],
        "label": target.get("label"),
        "kind": target.get("kind"),
        "role": target.get("role"),
        "status": status,
        "latency_ms": latency_ms,
        "error": error,
        "error_code": error_code,
        "hint": hint,
        "configured": configured,
        "last_checked_at": datetime.now().isoformat(timespec="seconds"),
    }
    if probe_mode:
        result["probe_mode"] = probe_mode
    if probe_label:
        result["probe_label"] = probe_label
    return result


def check_target_configuration(target: dict[str, Any]) -> tuple[bool, str | None, str | None, str | None]:
    base_url = safe_text(target.get("base_url"))
    model = safe_text(target.get("model"))

    if not base_url:
        return (
            False,
            "missing_base_url",
            "Base URL 未配置",
            "请在模型设置中填写 Base URL 后再执行健康检查",
        )
    if not model:
        return (
            False,
            "missing_model",
            "模型名称未配置",
            "请在模型设置中填写模型名后再执行健康检查",
        )
    return (True, None, None, None)


def build_health_targets(config: dict[str, Any]) -> list[dict[str, Any]]:
    targets: list[dict[str, Any]] = []

    active_id = config.get("active_chat_endpoint_id")
    chat_endpoints = config.get("chat_endpoints", [])
    for index, endpoint in enumerate(chat_endpoints):
        endpoint_id = safe_text(endpoint.get("id")) or f"idx-{index}"
        targets.append(
            {
                "name": f"chat:{endpoint_id}",
                "label": safe_text(endpoint.get("name")) or safe_text(endpoint.get("model")) or f"聊天端点 {index + 1}",
                "kind": "chat",
                "role": "api",
                "endpoint_id": endpoint_id,
                "active": bool(active_id and endpoint_id == active_id),
                "base_url": safe_text(endpoint.get("base_url")),
                "api_key": safe_text(endpoint.get("api_key")),
                "model": safe_text(endpoint.get("model")),
            }
        )

    for role in ["api", "vision", "image_analyzer", "embedding", "autogui"]:
        section = config.get(role, {})
        if not isinstance(section, dict):
            continue
        base_url = safe_text(section.get("base_url"))
        api_key = safe_text(section.get("api_key"))
        model = safe_text(section.get("model"))
        if not (base_url or api_key or model):
            continue
        if role == "api" and targets:
            continue
        targets.append(
            {
                "name": f"role:{role}",
                "label": ROLE_HEALTH_LABELS.get(role, role),
                "kind": "role",
                "role": role,
                "active": role == "api" and not targets,
                "base_url": base_url,
                "api_key": api_key,
                "model": model,
            }
        )

    return targets


def _create_probe_http_client(*, timeout_seconds: float, no_proxy: bool, ipv4: bool) -> httpx.Client:
    transport = httpx.HTTPTransport(
        trust_env=not no_proxy,
        local_address="0.0.0.0" if ipv4 else None,
        retries=0,
    )
    return httpx.Client(
        timeout=timeout_seconds,
        trust_env=not no_proxy,
        transport=transport,
    )


def _run_health_probe_sync(
    target: dict[str, Any],
    *,
    timeout_seconds: float = 15.0,
    probe_mode: str = "default",
) -> dict[str, Any]:
    from openai import OpenAI

    profile = next((item for item in NETWORK_MATRIX_PROFILES if item["name"] == probe_mode), NETWORK_MATRIX_PROFILES[0])
    base_url = safe_text(target.get("base_url"))
    api_key = safe_text(target.get("api_key")) or "test"
    model = safe_text(target.get("model"))
    role = safe_text(target.get("role"))

    if not base_url:
        raise ValueError("Base URL 未配置")
    if not model:
        raise ValueError("模型名称未配置")

    with _create_probe_http_client(
        timeout_seconds=timeout_seconds,
        no_proxy=bool(profile["no_proxy"]),
        ipv4=bool(profile["ipv4"]),
    ) as http_client:
        client = OpenAI(
            base_url=base_url,
            api_key=api_key,
            timeout=timeout_seconds,
            max_retries=0,
            http_client=http_client,
        )

        if role == "embedding":
            client.embeddings.create(model=model, input="health-check", timeout=timeout_seconds)
        else:
            client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": "Reply with a single word: OK"}],
                max_tokens=8,
                timeout=timeout_seconds,
            )

    return build_probe_result(
        target,
        status="healthy",
        latency_ms=None,
        error=None,
        error_code=None,
        hint=None,
        configured=True,
        probe_mode=probe_mode,
        probe_label=profile["label"],
    )


async def probe_health_target(
    target: dict[str, Any],
    timeout_seconds: float = 15.0,
    *,
    probe_mode: str = "default",
) -> dict[str, Any]:
    started_at = time.perf_counter()
    configured, error_code, error, hint = check_target_configuration(target)
    profile = next((item for item in NETWORK_MATRIX_PROFILES if item["name"] == probe_mode), NETWORK_MATRIX_PROFILES[0])
    if not configured:
        return build_probe_result(
            target,
            status="unknown",
            latency_ms=None,
            error=error,
            error_code=error_code,
            hint=hint,
            configured=False,
            probe_mode=probe_mode,
            probe_label=profile["label"],
        )

    try:
        result = await asyncio.wait_for(
            asyncio.to_thread(
                _run_health_probe_sync,
                dict(target),
                timeout_seconds=timeout_seconds,
                probe_mode=probe_mode,
            ),
            timeout=timeout_seconds + 1,
        )
        result["latency_ms"] = int((time.perf_counter() - started_at) * 1000)
        return result
    except asyncio.TimeoutError:
        return build_probe_result(
            target,
            status="unhealthy",
            latency_ms=int((time.perf_counter() - started_at) * 1000),
            error=f"健康检查超时（{int(timeout_seconds)}s）",
            error_code="timeout",
            hint="请检查代理、网络质量，或稍后重试",
            configured=True,
            probe_mode=probe_mode,
            probe_label=profile["label"],
        )
    except Exception as exc:
        normalized_code, normalized_error, normalized_hint = classify_health_error(exc)
        return build_probe_result(
            target,
            status="unhealthy",
            latency_ms=int((time.perf_counter() - started_at) * 1000),
            error=normalized_error,
            error_code=normalized_code,
            hint=normalized_hint,
            configured=True,
            probe_mode=probe_mode,
            probe_label=profile["label"],
        )


def _summarize_status_bucket(statuses: list[str]) -> str:
    normalized = [item for item in statuses if item]
    if not normalized:
        return "unknown"
    if any(item == "unhealthy" for item in normalized):
        if any(item == "healthy" for item in normalized):
            return "degraded"
        return "unhealthy"
    if any(item == "healthy" for item in normalized):
        return "healthy"
    return "unknown"


def summarize_items_status(items: list[dict[str, Any]]) -> str:
    return _summarize_status_bucket([safe_text(item.get("status")) for item in items])


def collect_dependency_status() -> dict[str, bool]:
    return {name: importlib.util.find_spec(name) is not None for name in DIAGNOSTIC_DEPENDENCIES}


def current_proxy_settings() -> dict[str, str | None]:
    return {
        "http": os.environ.get("HTTP_PROXY") or os.environ.get("http_proxy"),
        "https": os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy"),
        "all": os.environ.get("ALL_PROXY") or os.environ.get("all_proxy"),
    }


def check_external_connectivity(url: str = CONNECTIVITY_CHECK_URL, timeout_seconds: float = 3.0) -> dict[str, Any]:
    try:
        started_at = time.time()
        urllib.request.urlopen(url, timeout=timeout_seconds)
        return {"status": "ok", "latency_ms": int((time.time() - started_at) * 1000)}
    except Exception as exc:
        return {"status": "error", "error": str(exc)}


def build_service_runtime_snapshot(
    *,
    current_pid: int,
    version: str,
    started_at: float,
    mode: str | None = None,
) -> dict[str, Any]:
    restart_mode = mode or detect_runtime_mode()
    return {
        "status": "ok",
        "pid": current_pid,
        "version": version,
        "started_at": datetime.fromtimestamp(started_at).isoformat(timespec="seconds"),
        "uptime_seconds": max(0, int(time.time() - started_at)),
        "restart_mode": restart_mode,
    }


def collect_diagnostics_snapshot(
    app_base: Path,
    *,
    current_pid: int,
    version: str,
    started_at: float,
    mode: str | None = None,
    is_frozen: bool | None = None,
) -> dict[str, Any]:
    restart_mode = mode or detect_runtime_mode()
    frozen = getattr(sys, "frozen", False) if is_frozen is None else bool(is_frozen)
    return {
        "system": {
            "os": f"{platform.system()} {platform.release()} ({platform.machine()})",
            "python_version": sys.version.replace("\n", " "),
            "python_executable": sys.executable,
            "app_dir": str(app_base),
            "frozen": frozen,
            "pid": current_pid,
        },
        "service": build_service_runtime_snapshot(
            current_pid=current_pid,
            version=version,
            started_at=started_at,
            mode=restart_mode,
        ),
        "restart": {
            "supported": restart_mode in {"watchdog", "reload"},
            "mode": restart_mode,
            "reason": None if restart_mode in {"watchdog", "reload"} else "当前运行模式不带 watchdog，也未启用 uvicorn --reload。",
        },
        "network": {"proxies": current_proxy_settings(), "connectivity": check_external_connectivity()},
        "dependencies": collect_dependency_status(),
        "process_runtime": collect_process_runtime(
            app_base,
            current_pid=current_pid,
            version=version,
            started_at=started_at,
            mode=restart_mode,
            is_frozen=frozen,
        ),
        "timestamp": int(time.time()),
    }


def _collect_im_session_stats(app_base: Path) -> dict[str, dict[str, Any]]:
    sessions_dir = app_base / "data" / "sessions"
    if not sessions_dir.exists():
        return {}

    stats: dict[str, dict[str, Any]] = {}
    for path in sessions_dir.glob("*.json"):
        parsed = parse_im_session_id(path.stem)
        if not parsed:
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                payload = json.load(f)
        except Exception:
            payload = {}
        item = stats.setdefault(parsed["channel_name"], {"session_count": 0, "last_active": None})
        item["session_count"] += 1
        last_active = payload.get("updated_at") or payload.get("created_at")
        if last_active and (not item["last_active"] or str(last_active) > str(item["last_active"])):
            item["last_active"] = str(last_active)
    return stats


def collect_im_channel_statuses(app_base: Path) -> list[dict[str, Any]]:
    config, _cfg_path = load_config_json_optional(app_base)
    bots = load_im_bots_from_config(config)
    gateway = app_state.get("gateway")
    adapters = gateway.adapters if gateway else {}
    session_stats = _collect_im_session_stats(app_base)

    channels: list[dict[str, Any]] = []
    for bot in bots:
        channel_name = make_channel_name(bot["platform"], bot["id"])
        adapter = adapters.get(channel_name)
        stream_state = getattr(adapter, "_stream_state", None)
        if hasattr(stream_state, "value"):
            stream_state = stream_state.value
        last_health = bot.get("last_health") if isinstance(bot.get("last_health"), dict) else None
        missing_credentials = validate_required_credentials(bot["platform"], bot.get("credentials", {}))
        is_online = bool(adapter and getattr(adapter, "_running", False))

        runtime_state = "unknown"
        status = "unknown"
        error = getattr(adapter, "_last_error", None) if adapter else None
        summary = "未执行运行时探测"

        if not bot.get("enabled", True):
            runtime_state = "disabled"
            summary = "通道已禁用"
        elif missing_credentials:
            runtime_state = "config_missing"
            status = "unhealthy"
            summary = f"缺少配置: {', '.join(missing_credentials)}"
            error = error or summary
        elif is_online:
            runtime_state = "online"
            status = "healthy"
            summary = "通道在线"
        else:
            runtime_state = "offline"
            if last_health and last_health.get("status") == "healthy":
                status = "unhealthy"
                summary = "最近健康检查通过，但当前运行时离线"
            elif last_health and last_health.get("status") == "unhealthy":
                status = "unhealthy"
                summary = "最近健康检查失败，且当前离线"
                error = error or last_health.get("error")
            else:
                status = "unknown"
                summary = "通道已配置，但当前未观测到在线实例"

        stats = session_stats.get(channel_name, {})
        channels.append(
            {
                "id": channel_name,
                "channel_name": channel_name,
                "platform": bot["platform"],
                "bot_id": bot["id"],
                "name": bot["name"],
                "display_name": bot["name"],
                "enabled": bool(bot.get("enabled", True)),
                "configured": not missing_credentials,
                "config_missing": missing_credentials,
                "status": status,
                "runtime_status": runtime_state,
                "summary": summary,
                "stream_state": stream_state,
                "last_error": error,
                "last_health": last_health,
                "session_count": int(stats.get("session_count", 0)),
                "last_active": stats.get("last_active"),
            }
        )

    return channels


def _diagnose_network_matrix(results: list[dict[str, Any]]) -> tuple[str, str, str | None, str | None]:
    by_mode = {item.get("probe_mode"): item for item in results}
    default_result = by_mode.get("default")
    no_proxy_result = by_mode.get("no_proxy")
    ipv4_result = by_mode.get("ipv4")
    no_proxy_ipv4_result = by_mode.get("no_proxy_ipv4")
    any_healthy = any(item.get("status") == "healthy" for item in results)

    if not default_result:
        return ("unknown", "未配置可探测端点", None, None)
    if not default_result.get("configured"):
        return ("unknown", default_result.get("error") or "主端点未配置", default_result.get("error_code"), default_result.get("hint"))
    if default_result.get("status") == "healthy":
        return ("healthy", "默认网络测活成功", None, None)
    if no_proxy_result and no_proxy_result.get("status") == "healthy":
        return ("degraded", "默认网络失败，但禁用代理后成功，疑似代理配置问题", "proxy_issue", no_proxy_result.get("hint") or "请检查 HTTP(S)_PROXY / ALL_PROXY 配置")
    if ipv4_result and ipv4_result.get("status") == "healthy":
        return ("degraded", "默认网络失败，但强制 IPv4 后成功，疑似 IPv6 / 路由问题", "ipv6_or_route_issue", ipv4_result.get("hint") or "请检查 DNS、IPv6 出口或本机网络栈")
    if no_proxy_ipv4_result and no_proxy_ipv4_result.get("status") == "healthy":
        return ("degraded", "仅在禁用代理 + IPv4 时成功，疑似代理与 IPv6 共同导致失败", "proxy_ipv6_combo_issue", no_proxy_ipv4_result.get("hint") or "请同时检查代理配置与 IPv6 路由")

    for item in results:
        if item.get("error_code") in {"auth_failed", "permission_denied", "model_or_route_not_found"}:
            return ("unhealthy", item.get("error") or "端点配置错误", item.get("error_code"), item.get("hint"))

    if any_healthy:
        healthy_modes = [item.get("probe_label") or item.get("probe_mode") for item in results if item.get("status") == "healthy"]
        return ("degraded", f"仅部分探测模式成功：{', '.join([str(mode) for mode in healthy_modes if mode])}", "partial_success", "请比较成功/失败模式的代理与网络差异")

    first_error = next((item for item in results if item.get("error")), None)
    return (
        "unhealthy",
        (first_error or {}).get("error") or "所有网络探测均失败",
        (first_error or {}).get("error_code"),
        (first_error or {}).get("hint"),
    )


async def probe_network_matrix(target: dict[str, Any] | None, timeout_seconds: float = 5.0) -> dict[str, Any]:
    if not target:
        return {
            "status": "unknown",
            "target_name": None,
            "summary": "当前没有可用于网络矩阵探测的主端点",
            "diagnosis_code": None,
            "hint": None,
            "results": [],
        }

    results = await asyncio.gather(
        *[
            probe_health_target(dict(target), timeout_seconds=timeout_seconds, probe_mode=profile["name"])
            for profile in NETWORK_MATRIX_PROFILES
        ]
    )
    status, summary, diagnosis_code, hint = _diagnose_network_matrix(results)
    return {
        "status": status,
        "target_name": target.get("name"),
        "target_label": target.get("label"),
        "summary": summary,
        "diagnosis_code": diagnosis_code,
        "hint": hint,
        "results": results,
    }


async def collect_runtime_selfcheck_snapshot(
    app_base: Path,
    *,
    current_pid: int,
    version: str,
    started_at: float,
    mode: str | None = None,
    is_frozen: bool | None = None,
    endpoint_timeout_seconds: float = 12.0,
    network_timeout_seconds: float = 5.0,
) -> dict[str, Any]:
    diagnostics = collect_diagnostics_snapshot(
        app_base,
        current_pid=current_pid,
        version=version,
        started_at=started_at,
        mode=mode,
        is_frozen=is_frozen,
    )
    config, _cfg_path = load_config_json_optional(app_base)
    targets = build_health_targets(config)
    endpoint_results = (
        await asyncio.gather(*[probe_health_target(target, timeout_seconds=endpoint_timeout_seconds) for target in targets])
        if targets
        else []
    )
    active_target = next((item for item in targets if item.get("active")), None) or (targets[0] if targets else None)
    network_matrix = await probe_network_matrix(active_target, timeout_seconds=network_timeout_seconds)
    im_channels = collect_im_channel_statuses(app_base)

    return {
        "environment": {
            "system": diagnostics["system"],
            "restart": diagnostics["restart"],
            "network": diagnostics["network"],
            "dependencies": diagnostics["dependencies"],
        },
        "runtime": {
            "service": diagnostics["service"],
            "process_runtime": diagnostics["process_runtime"],
        },
        "network_matrix": network_matrix,
        "endpoints": {
            "status": summarize_items_status(endpoint_results),
            "active_target": active_target.get("name") if active_target else None,
            "results": endpoint_results,
        },
        "im_channels": {
            "status": summarize_items_status(im_channels),
            "results": im_channels,
        },
    }


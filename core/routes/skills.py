"""Skills management, marketplace, install/uninstall routes."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.skill_runtime import install_skill_from_source
from core.state import _APP_BASE, _ctx_event_queue, app_state, logger

router = APIRouter(tags=["skills"])

_marketplace_cache: dict = {}
_MARKETPLACE_CACHE_TTL = 60


class SkillToggleRequest(BaseModel):
    name: str
    enabled: bool
    tools: Optional[list[str]] = None


class SkillConfigRequest(BaseModel):
    name: str
    config: Dict[str, Any]


class SkillInstallRequest(BaseModel):
    url: str
    name: str = ""


class SkillUninstallRequest(BaseModel):
    name: str


def _require_agent():
    agent = app_state.get("agent")
    if not agent:
        raise HTTPException(status_code=500, detail="Agent not initialized")
    return agent


def _broadcast_skills_version(agent, *, action: str, installed_skill_names: Optional[list[str]] = None) -> None:
    event = {
        "type": "skills_version",
        "action": action,
        "skills_version": agent.skills.get_version(),
        "installed_skill_names": installed_skill_names or [],
        "message": "新技能已加载，本线程后续消息可直接使用" if action == "install" else "",
    }
    try:
        _ctx_event_queue.put(event)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[Skills] Failed to broadcast skills_version event: %s", exc)


def _build_skill_records(agent) -> list[dict[str, Any]]:
    plugin_manager = app_state.get("plugin_manager")
    records: list[dict[str, Any]] = []
    seen_names: set[str] = set()

    if plugin_manager:
        for plugin in plugin_manager.list_plugins():
            tools = [agent.skills.get(name) for name in plugin.skills]
            tools = [tool for tool in tools if tool]
            enabled = all(tool.enabled for tool in tools) if tools else True
            records.append(
                {
                    "id": plugin.name,
                    "name": plugin.display_name,
                    "description": plugin.description,
                    "category": plugin.name,
                    "registry_category": plugin.name,
                    "type": "system_plugin",
                    "enabled": enabled,
                    "locked": True,
                    "source": str(plugin.path),
                    "tools": [tool.name for tool in tools],
                    "config_values": {},
                }
            )
            seen_names.add(plugin.name)

    catalog = getattr(agent, "_local_skills_catalog", {}) or {}
    for name, info in sorted(catalog.items(), key=lambda item: item[0].lower()):
        records.append(
            {
                "id": name,
                "name": name,
                "description": info.get("description", ""),
                "category": "skills",
                "registry_category": name,
                "type": "user_skill",
                "enabled": info.get("enabled", True),
                "locked": False,
                "source": info.get("source_url") or info.get("path", ""),
                "tools": info.get("tools", []) or [],
                "config_values": {},
            }
        )
        seen_names.add(name)

    for skill in sorted(agent.skills.list_all(), key=lambda item: item.name.lower()):
        if skill.plugin_name and skill.plugin_name in seen_names:
            continue
        if skill.name in seen_names:
            continue
        records.append(
            {
                "id": skill.name,
                "name": skill.name,
                "description": skill.description,
                "category": skill.category or "general",
                "registry_category": skill.category or "general",
                "type": skill.source_type or "builtin_skill",
                "enabled": skill.enabled,
                "locked": bool(skill.system_locked),
                "source": skill.source_path or skill.source_url or "runtime",
                "tools": [skill.name],
                "config_values": dict(skill.config_values or {}),
            }
        )

    return records


@router.get("/api/skills/list")
async def list_skills():
    agent = _require_agent()
    agent.ensure_session_skills_current(agent.sessions.current)
    return {"skills": _build_skill_records(agent), "skills_version": agent.skills.get_version()}


@router.post("/api/skills/config")
async def config_skill(request: SkillConfigRequest):
    agent = _require_agent()
    skill = agent.skills.get(request.name)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill '{request.name}' not found")
    agent.skills.update_config(request.name, request.config)
    _broadcast_skills_version(agent, action="config")
    return {"status": "success", "name": request.name, "config_values": skill.config_values}


@router.post("/api/skills/toggle")
async def toggle_skill(request: SkillToggleRequest):
    agent = _require_agent()

    target_names: list[str] = []
    if request.tools is not None:
        target_names = [tool for tool in request.tools if agent.skills.get(tool)]
    elif agent.skills.get(request.name):
        target_names = [request.name]
    else:
        matched = [skill.name for skill in agent.skills.list_all() if (skill.category or "general") == request.name]
        target_names = matched

    if not target_names:
        catalog = getattr(agent, "_local_skills_catalog", {}) or {}
        if request.name in catalog:
            version = agent.set_local_skill_enabled(request.name, request.enabled)
            _broadcast_skills_version(agent, action="toggle")
            return {
                "status": "success",
                "name": request.name,
                "enabled": request.enabled,
                "affected": 1,
                "skills_version": version,
            }
        raise HTTPException(status_code=404, detail=f"Skill or category '{request.name}' not found")

    locked = [name for name in target_names if getattr(agent.skills.get(name), "system_locked", False)]
    if locked:
        raise HTTPException(status_code=403, detail=f"系统能力不可关闭: {', '.join(locked)}")

    for name in target_names:
        if request.enabled:
            agent.skills.enable(name)
        else:
            agent.skills.disable(name)

    _broadcast_skills_version(agent, action="toggle")
    return {
        "status": "success",
        "name": request.name,
        "enabled": request.enabled,
        "affected": len(target_names),
        "skills_version": agent.skills.get_version(),
    }


@router.post("/api/skills/reload")
async def reload_skills():
    agent = _require_agent()
    version = agent.refresh_skill_runtime(reason="api_reload")
    _broadcast_skills_version(agent, action="reload")
    return {
        "status": "success",
        "message": "技能注册表已刷新",
        "skills_version": version,
        "requires_restart": False,
    }


@router.get("/api/skills/marketplace")
async def skills_marketplace(q: str = "agent"):
    try:
        import httpx
    except ImportError:
        from core.runtime_deps import DependencySpec, ensure_runtime_dependencies

        if not ensure_runtime_dependencies(
            DependencySpec(module="httpx", package="httpx>=0.24.0", reason="技能市场需要 httpx"),
            context="skills_marketplace",
        ):
            return {"skills": [], "error": "httpx not available"}
        import httpx

    q = q.strip() or "agent"
    cache_key = q.lower()
    now = time.time()
    if cache_key in _marketplace_cache:
        ts, cached = _marketplace_cache[cache_key]
        if now - ts < _MARKETPLACE_CACHE_TTL:
            return cached

    agent = app_state.get("agent")
    data = None
    timeout_val = 20.0
    url = f"https://skills.sh/api/search?q={q}"
    headers = {"User-Agent": "openGuiclaw/1.0"}

    try:
        async with httpx.AsyncClient(timeout=timeout_val, trust_env=True) as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            data = resp.json()
    except (httpx.ConnectTimeout, httpx.ConnectError, httpx.HTTPStatusError) as e:
        try:
            from httpx import AsyncHTTPTransport

            transport = AsyncHTTPTransport(local_address="0.0.0.0")
            async with httpx.AsyncClient(timeout=timeout_val + 5, transport=transport, trust_env=True) as client:
                resp = await client.get(url, headers=headers)
                resp.raise_for_status()
                data = resp.json()
        except Exception:
            return {"skills": [], "error": f"连接插件库(skills.sh)失败: {str(e)}"}
    except Exception as e:
        return {"skills": [], "error": f"同步异常: {str(e)}"}

    if not data:
        return {"skills": [], "error": "无法获取插件数据"}

    installed_urls: set = set()
    if agent:
        for skill in agent.skills.list_all():
            if skill.source_url:
                installed_urls.add(skill.source_url)
        for info in (getattr(agent, "_local_skills_catalog", {}) or {}).values():
            source_url = info.get("source_url")
            if source_url:
                installed_urls.add(source_url)

    enriched = []
    for item in data.get("skills", []):
        source = str(item.get("source", ""))
        skill_id = str(item.get("skillId", item.get("name", "")))
        install_url = f"{source}@{skill_id}" if source else skill_id
        description = item.get("description") or skill_id.replace("-", " ").replace("_", " ").title()
        tags: list = list(item.get("tags", []) or [])
        if not tags:
            if "/" in source:
                author = source.split("/")[0]
                if author not in tags:
                    tags.append(author)
            category = item.get("category")
            if category and category not in tags:
                tags.append(category.lower())
        enriched.append(
            {
                "id": str(item.get("id", "")),
                "name": skill_id,
                "description": str(description),
                "author": source.split("/")[0] if source else "community",
                "url": install_url,
                "installs": item.get("installs", 0),
                "stars": item.get("stars", 0),
                "tags": tags,
                "installed": install_url in installed_urls,
            }
        )

    result = {"skills": enriched}
    _marketplace_cache[cache_key] = (now, result)
    return result


@router.post("/api/skills/install")
async def install_skill(request: SkillInstallRequest):
    agent = _require_agent()
    try:
        installed = install_skill_from_source(request.url, _APP_BASE, requested_name=request.name)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=504, detail=f"安装失败: {exc}") from exc

    version = agent.refresh_skill_runtime(reason=f"api_install:{installed.name}")
    _broadcast_skills_version(agent, action="install", installed_skill_names=[installed.name])

    return {
        "status": "success",
        "message": f"技能 `{installed.name}` 已立即生效",
        "source_url": request.url,
        "applied_immediately": True,
        "skills_version": version,
        "installed_skill_names": [installed.name],
        "requires_restart": False,
    }


@router.post("/api/skills/uninstall")
async def uninstall_skill(request: SkillUninstallRequest):
    agent = _require_agent()
    catalog = getattr(agent, "_local_skills_catalog", {}) or {}
    entry = catalog.get(request.name)
    if not entry:
        raise HTTPException(status_code=404, detail=f"Skill '{request.name}' not found")

    skill_path = Path(entry.get("path", ""))
    if not skill_path.exists():
        raise HTTPException(status_code=404, detail=f"Skill '{request.name}' source path not found")
    skill_dir = skill_path.parent
    if not str(skill_dir.resolve()).startswith(str((_APP_BASE / "skills").resolve())):
        raise HTTPException(status_code=403, detail=f"'{request.name}' is locked and cannot be uninstalled")

    import shutil

    shutil.rmtree(skill_dir, ignore_errors=True)
    version = agent.refresh_skill_runtime(reason=f"uninstall:{request.name}")
    _broadcast_skills_version(agent, action="uninstall")
    return {
        "status": "success",
        "message": f"Skill '{request.name}' uninstalled",
        "skills_version": version,
        "requires_restart": False,
    }

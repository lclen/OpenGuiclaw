"""
Skill Manager: Plugin-style tool registration and execution.

Any Python function decorated with @skill can be registered.
Skills return (str) results that are fed back to the LLM.
"""

from typing import Callable, Dict, Any, List, Optional
from dataclasses import dataclass, field
import threading


@dataclass
class SkillDefinition:
    """Metadata for a registered skill / tool."""
    name: str
    description: str
    parameters: Dict[str, Any]          # JSON Schema style
    handler: Callable
    enabled: bool = True
    category: str = "general"
    ui_config: Optional[List[Dict[str, Any]]] = field(default_factory=list)
    config_values: Dict[str, Any] = field(default_factory=dict)
    source_type: str = "builtin_skill"
    source_path: str = ""
    source_url: str = ""
    system_locked: bool = False
    plugin_name: str = ""



class SkillManager:
    """
    Manages all registered skills.

    Usage:
        manager = SkillManager()

        @manager.skill(
            name="get_time",
            description="Returns the current date and time.",
            parameters={}
        )
        def get_time():
            import time
            return time.strftime("%Y-%m-%d %H:%M:%S")
    """

    def __init__(self, config_path: str = "data/skills.json"):
        self._registry: Dict[str, SkillDefinition] = {}
        self.config_path = config_path
        self._config_data: Dict[str, Any] = {}
        self._version = 1
        self._version_lock = threading.Lock()
        self._registration_context: Dict[str, Any] = {}
        self._load_config()

    def _load_config(self) -> None:
        import os, json
        if not os.path.exists(self.config_path):
            self._config_data = {}
            return
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                self._config_data = json.load(f)
        except Exception as e:
            print(f"[SkillManager] Failed to load config: {e}")
            self._config_data = {}

    def _save_config(self) -> None:
        import os, json
        os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
        data = {}
        for name, skill in self._registry.items():
            data[name] = {
                "enabled": skill.enabled,
                "config_values": skill.config_values
            }
        try:
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"[SkillManager] Failed to save config: {e}")

    def register(self, skill: SkillDefinition) -> None:
        """Register a skill."""
        context = self._registration_context or {}
        skill.source_type = context.get("source_type", skill.source_type)
        skill.source_path = context.get("source_path", skill.source_path)
        skill.source_url = context.get("source_url", skill.source_url)
        skill.system_locked = bool(context.get("system_locked", skill.system_locked))
        skill.plugin_name = context.get("plugin_name", skill.plugin_name)

        if skill.name in self._config_data:
            if not skill.system_locked:
                skill.enabled = self._config_data[skill.name].get("enabled", skill.enabled)
            skill.config_values = self._config_data[skill.name].get("config_values", skill.config_values)
        if skill.system_locked:
            skill.enabled = True
        self._registry[skill.name] = skill
        self.bump_version(f"register:{skill.name}")

    def skill(
        self,
        name: str,
        description: str,
        parameters: Dict[str, Any],
        category: str = "general",
        enabled: bool = True,
        ui_config: Optional[List[Dict[str, Any]]] = None,
    ):
        """Decorator to register a function as a skill."""
        def decorator(func: Callable) -> Callable:
            self.register(SkillDefinition(
                name=name,
                description=description,
                parameters=parameters,
                handler=func,
                enabled=enabled,
                category=category,
                ui_config=ui_config or [],
            ))
            return func
        return decorator

    def enable(self, name: str) -> None:
        if name in self._registry:
            if self._registry[name].system_locked:
                raise ValueError(f"Skill '{name}' is system locked")
            self._registry[name].enabled = True
            self._save_config()
            self.bump_version(f"enable:{name}")

    def disable(self, name: str) -> None:
        if name in self._registry:
            if self._registry[name].system_locked:
                raise ValueError(f"Skill '{name}' is system locked")
            self._registry[name].enabled = False
            self._save_config()
            self.bump_version(f"disable:{name}")

    def update_config(self, name: str, config: Dict[str, Any]) -> None:
        if name in self._registry:
            self._registry[name].config_values.update(config)
            self._save_config()
            self.bump_version(f"config:{name}")

    def unregister(self, name: str) -> None:
        if name in self._registry:
            del self._registry[name]
            self._save_config()
            self.bump_version(f"unregister:{name}")

    def get(self, name: str) -> Optional[SkillDefinition]:
        return self._registry.get(name)

    def list_all(self) -> List[SkillDefinition]:
        return list(self._registry.values())

    def list_enabled(self) -> List[SkillDefinition]:
        return [s for s in self.list_all() if s.enabled]

    def _normalize_allowed_values(self, allowed_skills: Optional[List[str]]) -> set[str]:
        values: set[str] = set()
        for value in allowed_skills or []:
            text = str(value or "").strip().lower()
            if text:
                values.add(text)
        return values

    def _skill_match_keys(self, skill: SkillDefinition) -> set[str]:
        keys = {
            str(skill.name or "").strip().lower(),
            str(skill.category or "").strip().lower(),
            str(skill.plugin_name or "").strip().lower(),
            str(skill.source_type or "").strip().lower(),
        }
        source_path = str(skill.source_path or "").replace("\\", "/").strip().lower()
        if source_path:
            keys.add(source_path)
            if "/" in source_path:
                keys.add(source_path.rsplit("/", 1)[-1])
        return {key for key in keys if key}

    def _is_builtin_always_available(self, skill: SkillDefinition) -> bool:
        return str(skill.source_type or "").strip().lower() == "builtin_skill"

    def _matches_allowed_scope(self, skill: SkillDefinition, allowed_skills: Optional[List[str]]) -> bool:
        allowed = self._normalize_allowed_values(allowed_skills)
        if not allowed:
            return False
        return bool(self._skill_match_keys(skill) & allowed)

    def is_skill_visible(
        self,
        skill: SkillDefinition,
        allowed_skills: Optional[List[str]] = None,
        skills_mode: str = "inclusive",
    ) -> bool:
        """Decide whether a skill should be exposed to the current agent profile."""
        mode = str(skills_mode or "inclusive").strip().lower()
        if mode == "all" or not allowed_skills:
            return True
        if self._is_builtin_always_available(skill):
            return True
        matched = self._matches_allowed_scope(skill, allowed_skills)
        if mode == "exclusive":
            return not matched
        return matched

    def list_visible(
        self,
        allowed_skills: Optional[List[str]] = None,
        skills_mode: str = "inclusive",
    ) -> List[SkillDefinition]:
        return [
            skill
            for skill in self.list_enabled()
            if self.is_skill_visible(skill, allowed_skills=allowed_skills, skills_mode=skills_mode)
        ]

    def set_registration_context(self, **kwargs: Any) -> None:
        self._registration_context = dict(kwargs)

    def clear_registration_context(self) -> None:
        self._registration_context = {}

    def get_version(self) -> int:
        return self._version

    def bump_version(self, reason: str = "") -> int:
        with self._version_lock:
            self._version += 1
            version = self._version
        if reason:
            print(f"[SkillManager] skills_version -> {version} ({reason})")
        return version

    async def execute(self, name: str, params: Dict[str, Any]) -> str:
        """Execute a skill by name with given parameters. Supports both sync and async handlers."""
        import asyncio
        skill = self._registry.get(name)
        if skill is None:
            return f"[SkillManager] Unknown skill: '{name}'"
        if not skill.enabled:
            return f"[SkillManager] Skill '{name}' is disabled."
        try:
            if asyncio.iscoroutinefunction(skill.handler):
                result = await skill.handler(**params)
            else:
                result = skill.handler(**params)
                if asyncio.iscoroutine(result):
                    result = await result
            return str(result) if result is not None else "Done."
        except Exception as e:
            return f"[SkillManager] Error executing '{name}': {e}"

    def get_tool_definitions(self, allowed_skills: List[str] = None, skills_mode: str = "inclusive") -> List[Dict[str, Any]]:
        """Return tool definitions in OpenAI function-calling format, filtered by profile scope."""
        tools = []
        for skill in self.list_visible(allowed_skills=allowed_skills, skills_mode=skills_mode):
            tools.append({
                "type": "function",
                "function": {
                    "name": skill.name,
                    "description": skill.description,
                    "parameters": {
                        "type": "object",
                        "properties": skill.parameters.get("properties", {}),
                        "required": skill.parameters.get("required", []),
                    },
                },
            })
        return tools

    def summary(self, allowed_skills: List[str] = None, skills_mode: str = "inclusive") -> str:
        """Return a text summary of visible skills. Highlights profile-preferred skills."""
        lines = []
        for skill in self.list_visible(allowed_skills=allowed_skills, skills_mode=skills_mode):
            is_specialized = self._matches_allowed_scope(skill, allowed_skills)

            if is_specialized:
                lines.append(f"- **{skill.name}** ({skill.category}) [✨优先核心技能]: {skill.description}")
            else:
                lines.append(f"- **{skill.name}** ({skill.category}): {skill.description}")
                
        return "\n".join(lines) if lines else "(No skills registered)"

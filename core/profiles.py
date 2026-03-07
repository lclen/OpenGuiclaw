import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import List, Dict, Optional, Any
import logging

logger = logging.getLogger(__name__)


class SkillsMode(Enum):
    ALL = "all"
    INCLUSIVE = "inclusive"
    EXCLUSIVE = "exclusive"


class AgentType(Enum):
    SYSTEM = "system"
    CUSTOM = "custom"
    DYNAMIC = "dynamic"


@dataclass
class AgentProfile:
    id: str
    name: str
    description: str
    type: AgentType
    skills: List[str] = field(default_factory=list)
    skills_mode: SkillsMode = SkillsMode.INCLUSIVE
    custom_prompt: str = ""
    icon: str = "🤖"
    color: str = "#4A90D9"
    category: str = "general"
    fallback_profile_id: Optional[str] = None
    created_by: str = "system"
    user_customized: bool = False
    preferred_model: Optional[str] = None

    @property
    def is_system(self) -> bool:
        return self.type == AgentType.SYSTEM

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "type": self.type.value,
            "skills": self.skills,
            "skills_mode": self.skills_mode.value,
            "custom_prompt": self.custom_prompt,
            "icon": self.icon,
            "color": self.color,
            "category": self.category,
            "fallback_profile_id": self.fallback_profile_id,
            "created_by": self.created_by,
            "user_customized": self.user_customized,
            "preferred_model": self.preferred_model,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AgentProfile":
        # Handle enum conversions
        t_val = data.get("type", "custom")
        type_val = AgentType(t_val) if isinstance(t_val, str) else t_val
        
        sm_val = data.get("skills_mode", "inclusive")
        skills_mode_val = SkillsMode(sm_val) if isinstance(sm_val, str) else sm_val

        return cls(
            id=data.get("id", ""),
            name=data.get("name", ""),
            description=data.get("description", ""),
            type=type_val,
            skills=data.get("skills", []),
            skills_mode=skills_mode_val,
            custom_prompt=data.get("custom_prompt", ""),
            icon=data.get("icon", "🤖"),
            color=data.get("color", "#4A90D9"),
            category=data.get("category", "general"),
            fallback_profile_id=data.get("fallback_profile_id"),
            created_by=data.get("created_by", "user"),
            user_customized=data.get("user_customized", False),
            preferred_model=data.get("preferred_model"),
        )


class ProfileStore:
    def __init__(self, profiles_dir: str | Path):
        self.profiles_dir = Path(profiles_dir)
        self.profiles_dir.mkdir(parents=True, exist_ok=True)
        self._cache: Dict[str, AgentProfile] = {}
        self._load_all()

    def _load_all(self):
        self._cache.clear()
        for filepath in self.profiles_dir.glob("*.json"):
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    profile = AgentProfile.from_dict(data)
                    self._cache[profile.id] = profile
            except Exception as e:
                logger.error(f"Failed to load profile {filepath}: {e}")

    def get(self, profile_id: str) -> Optional[AgentProfile]:
        return self._cache.get(profile_id)

    def get_all(self) -> List[AgentProfile]:
        return list(self._cache.values())

    def save(self, profile: AgentProfile):
        self._cache[profile.id] = profile
        self._persist(profile)

    def _persist(self, profile: AgentProfile):
        filepath = self.profiles_dir / f"{profile.id}.json"
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(profile.to_dict(), f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Failed to save profile {profile.id}: {e}")

    def exists(self, profile_id: str) -> bool:
        return profile_id in self._cache

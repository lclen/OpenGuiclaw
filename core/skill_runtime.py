"""Shared helpers for unified SKILL.md install, migration, and metadata parsing."""

from __future__ import annotations

import io
import json
import re
import shutil
import tempfile
import urllib.parse
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

import yaml


SKILLS_DIR_NAME = "skills"
LEGACY_SKILLS_DIR_NAME = ".agents/skills"
MIGRATION_MANIFEST_RELATIVE_PATH = Path("data") / "skill_migration_manifest.json"
PLUGIN_MIGRATION_MANIFEST_RELATIVE_PATH = Path("data") / "plugin_skill_migration_manifest.json"
INSTALL_METADATA_FILENAME = ".openguiclaw-skill.json"
_FRONT_MATTER_RE = re.compile(r"^---\s*\n(.*?)\n---", re.DOTALL)


@dataclass
class InstalledSkill:
    name: str
    description: str
    dest_dir: Path
    skill_md_path: Path
    source_url: str


def ensure_skills_dir(app_base: Path | str) -> Path:
    skills_dir = Path(app_base) / SKILLS_DIR_NAME
    skills_dir.mkdir(parents=True, exist_ok=True)
    return skills_dir


def get_legacy_skills_dir(app_base: Path | str) -> Path:
    return Path(app_base) / LEGACY_SKILLS_DIR_NAME


def parse_skill_metadata(skill_md_path: Path) -> Dict[str, Any]:
    content = skill_md_path.read_text(encoding="utf-8")
    return parse_skill_metadata_text(content, default_name=skill_md_path.parent.name)


def parse_skill_metadata_text(content: str, default_name: str = "skill") -> Dict[str, Any]:
    metadata: Dict[str, Any] = {}
    match = _FRONT_MATTER_RE.match(content)
    if match:
        parsed = yaml.safe_load(match.group(1)) or {}
        if isinstance(parsed, dict):
            metadata = parsed
    name = str(metadata.get("name") or default_name).strip() or default_name
    description = str(metadata.get("description") or "No description provided.").strip()
    return {
        "name": name,
        "description": description,
        "metadata": metadata,
        "content": content,
    }


def migrate_legacy_skills(app_base: Path | str) -> Dict[str, Any]:
    app_base = Path(app_base)
    skills_dir = ensure_skills_dir(app_base)
    legacy_dir = get_legacy_skills_dir(app_base)
    manifest_path = app_base / MIGRATION_MANIFEST_RELATIVE_PATH
    manifest_path.parent.mkdir(parents=True, exist_ok=True)

    manifest: Dict[str, Any] = {
        "migrated": [],
        "skipped": [],
        "legacy_source": str(legacy_dir),
        "skills_root": str(skills_dir),
    }

    if not legacy_dir.exists():
        manifest["status"] = "no_legacy_dir"
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        return manifest

    for entry in sorted(legacy_dir.iterdir(), key=lambda path: path.name.lower()):
        if not entry.is_dir():
            continue
        skill_md_path = entry / "SKILL.md"
        if not skill_md_path.exists():
            manifest["skipped"].append({"name": entry.name, "reason": "missing_skill_md", "path": str(entry)})
            continue
        dest_dir = skills_dir / entry.name
        if dest_dir.exists():
            manifest["skipped"].append({"name": entry.name, "reason": "already_exists", "path": str(dest_dir)})
            continue
        shutil.copytree(entry, dest_dir)
        manifest["migrated"].append({"name": entry.name, "from": str(entry), "to": str(dest_dir)})

    manifest["status"] = "migrated" if manifest["migrated"] else "noop"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def generate_plugin_migration_manifest(app_base: Path | str) -> Dict[str, Any]:
    app_base = Path(app_base)
    plugins_dir = app_base / "plugins"
    manifest_path = app_base / PLUGIN_MIGRATION_MANIFEST_RELATIVE_PATH
    manifest_path.parent.mkdir(parents=True, exist_ok=True)

    manifest: Dict[str, Any] = {
        "status": "scanned",
        "plugins_dir": str(plugins_dir),
        "system_plugins": [],
        "migrated_to_skills": [],
        "notes": [
            "当前默认策略为一次性收口运行时来源到 skills/，但无法安全转换的 Python 插件继续保留为 system_plugin。",
            "本清单可作为后续进一步拆分 plugins/ 的迁移基线。",
        ],
    }

    if plugins_dir.exists():
        for plugin_file in sorted(plugins_dir.glob("*.py"), key=lambda item: item.name.lower()):
            if plugin_file.name.startswith("_"):
                continue
            manifest["system_plugins"].append(
                {
                    "name": plugin_file.stem,
                    "path": str(plugin_file),
                    "action": "retain_as_system_plugin",
                }
            )
    else:
        manifest["status"] = "missing_plugins_dir"

    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def install_skill_from_source(source_url: str, app_base: Path | str, requested_name: str = "") -> InstalledSkill:
    app_base = Path(app_base)
    skills_dir = ensure_skills_dir(app_base)
    source_url = source_url.strip()
    if not source_url:
        raise ValueError("URL is required")

    if source_url.startswith(("http://", "https://")) and (
        source_url.endswith(".md") or "raw.githubusercontent.com" in source_url
    ):
        return _install_from_raw_skill_md(source_url, skills_dir, requested_name=requested_name)

    return _install_from_repository_source(source_url, skills_dir, requested_name=requested_name)


def _install_from_raw_skill_md(source_url: str, skills_dir: Path, requested_name: str = "") -> InstalledSkill:
    request = urllib.request.Request(source_url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=30) as response:
        content = response.read().decode("utf-8")

    parsed = parse_skill_metadata_text(content, default_name=requested_name or "remote-skill")
    target_name = _sanitize_skill_dir_name(requested_name or parsed["name"])
    dest_dir = skills_dir / target_name
    if dest_dir.exists():
        shutil.rmtree(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    skill_md_path = dest_dir / "SKILL.md"
    skill_md_path.write_text(content, encoding="utf-8")
    _write_install_metadata(dest_dir, source_url=source_url)
    return InstalledSkill(
        name=parsed["name"],
        description=parsed["description"],
        dest_dir=dest_dir,
        skill_md_path=skill_md_path,
        source_url=source_url,
    )


def _install_from_repository_source(source_url: str, skills_dir: Path, requested_name: str = "") -> InstalledSkill:
    repo_info = _parse_repo_source(source_url)
    owner = repo_info["owner"]
    repo = repo_info["repo"]
    sub_target = repo_info.get("subpath", "")
    branch_candidates = repo_info.get("branches", ["main", "master"])

    mirrors = [
        "https://gh-proxy.com/https://github.com/{owner}/{repo}/archive/refs/heads/{branch}.zip",
        "https://mirror.ghproxy.com/https://github.com/{owner}/{repo}/archive/refs/heads/{branch}.zip",
        "https://ghproxy.net/https://github.com/{owner}/{repo}/archive/refs/heads/{branch}.zip",
        "https://github.com/{owner}/{repo}/archive/refs/heads/{branch}.zip",
    ]

    last_error = "unknown install error"
    for branch in branch_candidates:
        for template in mirrors:
            download_url = template.format(owner=owner, repo=repo, branch=branch)
            try:
                request = urllib.request.Request(download_url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(request, timeout=30) as response:
                    zip_data = response.read()
                with tempfile.TemporaryDirectory(prefix="skill_install_") as tmpdir:
                    with zipfile.ZipFile(io.BytesIO(zip_data)) as archive:
                        archive.extractall(tmpdir)
                    extracted_items = [item for item in Path(tmpdir).iterdir()]
                    if not extracted_items:
                        raise FileNotFoundError("archive is empty")
                    repo_root = extracted_items[0]
                    source_dir = _resolve_skill_source_dir(repo_root, sub_target=sub_target)
                    skill_md_path = source_dir / "SKILL.md"
                    parsed = parse_skill_metadata(skill_md_path)
                    target_name = _sanitize_skill_dir_name(requested_name or parsed["name"] or source_dir.name or repo)
                    dest_dir = skills_dir / target_name
                    if dest_dir.exists():
                        shutil.rmtree(dest_dir)
                    shutil.copytree(source_dir, dest_dir)
                    _write_install_metadata(dest_dir, source_url=source_url)
                    return InstalledSkill(
                        name=parsed["name"],
                        description=parsed["description"],
                        dest_dir=dest_dir,
                        skill_md_path=dest_dir / "SKILL.md",
                        source_url=source_url,
                    )
            except Exception as exc:  # noqa: BLE001
                last_error = str(exc)
                continue

    raise RuntimeError(f"安装失败: {last_error}")


def _resolve_skill_source_dir(repo_root: Path, sub_target: str = "") -> Path:
    candidate = repo_root / sub_target if sub_target else repo_root
    candidate = candidate.resolve()
    if candidate.is_file() and candidate.name.upper() == "SKILL.MD":
        return candidate.parent
    if candidate.is_dir() and (candidate / "SKILL.md").exists():
        return candidate

    skill_candidates = sorted(candidate.rglob("SKILL.md") if candidate.exists() else repo_root.rglob("SKILL.md"))
    if not skill_candidates:
        raise FileNotFoundError("仓库中未找到 SKILL.md 文件")
    return skill_candidates[0].parent


def _parse_repo_source(source_url: str) -> Dict[str, Any]:
    source_url = source_url.strip()
    if source_url.startswith("https://github.com/"):
        parsed = urllib.parse.urlparse(source_url)
        parts = [part for part in parsed.path.strip("/").split("/") if part]
        if len(parts) < 2:
            raise ValueError(f"无法解析 GitHub 仓库地址: {source_url}")
        owner, repo = parts[0], parts[1].replace(".git", "")
        branches = ["main", "master"]
        subpath = ""
        if len(parts) >= 4 and parts[2] == "tree":
            branch = parts[3]
            branches = [branch] + [name for name in branches if name != branch]
            subpath = "/".join(parts[4:])
        return {"owner": owner, "repo": repo, "branches": branches, "subpath": subpath}

    base = source_url
    subpath = ""
    if "@" in source_url and "git+" not in source_url:
        base, subpath = source_url.split("@", 1)
    if "/" not in base:
        raise ValueError(f"无法解析安装源: {source_url}")
    owner, repo = base.split("/", 1)
    return {"owner": owner, "repo": repo.replace(".git", ""), "branches": ["main", "master"], "subpath": subpath}


def _sanitize_skill_dir_name(name: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9._-]+", "-", name.strip()).strip("-._")
    return cleaned or "skill"


def read_install_metadata(skill_dir: Path) -> Dict[str, Any]:
    metadata_path = skill_dir / INSTALL_METADATA_FILENAME
    if not metadata_path.exists():
        return {}
    try:
        return json.loads(metadata_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_install_metadata(skill_dir: Path, *, source_url: str) -> None:
    metadata_path = skill_dir / INSTALL_METADATA_FILENAME
    metadata_path.write_text(
        json.dumps({"source_url": source_url}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

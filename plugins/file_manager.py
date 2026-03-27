"""
Enhanced File Manager: Professional file system operations.
"""

import os
import shutil
from pathlib import Path
from core.skills import SkillManager
from core.automation_context import get_request_workspace_path
from core.tool_path_repair import (
    format_missing_path_message,
    format_repair_notice,
    log_path_resolution,
    resolve_tool_path,
)


def _resolve_path(path: str, *, expect: str = "any") -> tuple[Path, object]:
    workspace_path = get_request_workspace_path()
    base_path = Path(workspace_path) if workspace_path else Path.cwd()
    resolution = resolve_tool_path(path, cwd=base_path, workspace_path=workspace_path, expect=expect)
    log_path_resolution(tool_name="file_manager.resolve", result=resolution, cwd=base_path, workspace_path=workspace_path)
    return Path(resolution.resolved_path), resolution


def register(manager: SkillManager) -> None:
    """Register enhanced file management skills."""

    @manager.skill(
        name="read_file",
        description="读取本地文件的内容。支持文本编码处理。",
        parameters={
            "properties": {
                "path": {"type": "string", "description": "文件绝对或相对路径"},
            },
            "required": ["path"],
        },
        category="filesystem",
    )
    def read_file(path: str) -> str:
        p, resolution = _resolve_path(path, expect="file")
        if not p.exists():
            return f"错误: {format_missing_path_message(resolution, '文件不存在')}"
        try:
            content = p.read_text(encoding="utf-8")
            notice = format_repair_notice(resolution)
            return f"{notice}\n{content}" if notice else content
        except Exception as e:
            return f"读取失败: {e}"

    @manager.skill(
        name="write_file",
        description="将指定内容写入文件（直接覆盖）。如果父目录不存在会自动创建。",
        parameters={
            "properties": {
                "path": {"type": "string", "description": "目标文件路径"},
                "content": {"type": "string", "description": "要写入的文本内容"},
            },
            "required": ["path", "content"],
        },
        category="filesystem",
    )
    def write_file(path: str, content: str) -> str:
        p, resolution = _resolve_path(path, expect="parent")
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
            notice = format_repair_notice(resolution)
            base = f"[OK] 成功写入: {resolution.resolved_path if resolution.was_repaired else path}"
            return f"{notice}\n{base}" if notice else base
        except Exception as e:
            return f"写入异常: {e}"

    @manager.skill(
        name="list_dir",
        description="列出指定目录下的文件和子目录，并返回类型标识。",
        parameters={
            "properties": {
                "path": {"type": "string", "description": "目录路径，默认为当前目录"},
            },
            "required": [],
        },
        category="filesystem",
    )
    def list_dir(path: str = ".") -> str:
        p, resolution = _resolve_path(path, expect="dir")
        if not p.exists() or not p.is_dir():
            return f"错误: {format_missing_path_message(resolution, '路径无效')}"
        try:
            items = sorted(p.iterdir(), key=lambda x: (x.is_file(), x.name))
            lines = []
            for item in items:
                icon = "📁" if item.is_dir() else "📄"
                lines.append(f"{icon} {item.name}")
            body = "\n".join(lines) if lines else "(空目录)"
            notice = format_repair_notice(resolution)
            return f"{notice}\n{body}" if notice else body
        except Exception as e:
            return f"列目录失败: {e}"

    @manager.skill(
        name="move_path",
        description="移动或重命名文件或目录。",
        parameters={
            "properties": {
                "src": {"type": "string", "description": "源路径"},
                "dst": {"type": "string", "description": "目标路径"},
            },
            "required": ["src", "dst"],
        },
        category="filesystem",
    )
    def move_path(src: str, dst: str) -> str:
        try:
            src_path, src_resolution = _resolve_path(src, expect="any")
            dst_path, dst_resolution = _resolve_path(dst, expect="parent")
            shutil.move(src_path, dst_path)
            notices = [notice for notice in (format_repair_notice(src_resolution), format_repair_notice(dst_resolution)) if notice]
            base = f"[OK] 已将 {src_resolution.resolved_path if src_resolution.was_repaired else src} 移动到 {dst_resolution.resolved_path if dst_resolution.was_repaired else dst}"
            return "\n".join([*notices, base]) if notices else base
        except Exception as e:
            return f"移动失败: {e}"

    @manager.skill(
        name="delete_path",
        description="【慎用】删除文件或整个目录（递归删除）。",
        parameters={
            "properties": {
                "path": {"type": "string", "description": "要删除的路径"},
            },
            "required": ["path"],
        },
        category="filesystem",
    )
    def delete_path(path: str) -> str:
        p, resolution = _resolve_path(path, expect="any")
        if not p.exists():
            return f"跳过: {format_missing_path_message(resolution, '路径不存在')}"
        try:
            if p.is_file(): p.unlink()
            else: shutil.rmtree(p)
            notice = format_repair_notice(resolution)
            base = f"[OK] 已成功删除: {resolution.resolved_path if resolution.was_repaired else path}"
            return f"{notice}\n{base}" if notice else base
        except Exception as e:
            return f"删除失败: {e}"

    @manager.skill(
        name="search_files",
        description="在指定目录中搜索包含特定关键字的文件名，可选过滤后缀。",
        parameters={
            "properties": {
                "root": {"type": "string", "description": "起始目录"},
                "pattern": {"type": "string", "description": "文件名匹配模式（支持 * 通配符，如 *.py）"},
            },
            "required": ["pattern"],
        },
        category="filesystem",
    )
    def search_files(pattern: str, root: str = ".") -> str:
        try:
            root_path, resolution = _resolve_path(root, expect="dir")
            if not root_path.exists():
                return f"错误: {format_missing_path_message(resolution, '搜索目录不存在')}"
            results = list(root_path.rglob(pattern))
            if not results: return "未找到匹配项。"
            body = "\n".join([str(r) for r in results[:50]])
            notice = format_repair_notice(resolution)
            return f"{notice}\n{body}" if notice else body
        except Exception as e:
            return f"搜索异常: {e}"

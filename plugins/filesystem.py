import os
import shutil
from pathlib import Path
import logging
import aiofiles
import aiofiles.os
import re
from core.automation_context import get_request_workspace_path
from core.tool_path_repair import (
    format_missing_path_message,
    format_repair_notice,
    log_path_resolution,
    resolve_tool_path,
)

logger = logging.getLogger(__name__)

class FileTool:
    """内部文件操作工具，参考自 openakita 原生实现。"""
    
    def __init__(self, base_path: str = None):
        self.base_path = Path(base_path) if base_path else Path.cwd()

    def _resolve_path(self, path: str) -> Path:
        """解析路径（支持相对目录隔离）"""
        workspace_path = get_request_workspace_path()
        resolution = resolve_tool_path(
            path,
            cwd=self.base_path,
            workspace_path=workspace_path,
            expect="any",
        )
        log_path_resolution(
            tool_name="filesystem.resolve",
            result=resolution,
            cwd=self.base_path,
            workspace_path=workspace_path,
        )
        return Path(resolution.resolved_path)

    # 二进制文件扩展名判断防呆
    BINARY_EXTENSIONS = {
        ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".webp", ".svg",
        ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
        ".zip", ".rar", ".7z", ".tar", ".gz", ".bz2",
        ".exe", ".dll", ".so", ".dylib",
        ".mp3", ".mp4", ".avi", ".mkv", ".wav", ".flac",
        ".ttf", ".otf", ".woff", ".woff2",
        ".pyc", ".pyo", ".class",
    }

    async def read(self, path: str, encoding: str = "utf-8") -> str:
        workspace_path = get_request_workspace_path()
        resolution = resolve_tool_path(path, cwd=self.base_path, workspace_path=workspace_path, expect="file")
        log_path_resolution(
            tool_name="read_file",
            result=resolution,
            cwd=self.base_path,
            workspace_path=workspace_path,
        )
        file_path = Path(resolution.resolved_path)
        if not file_path.exists():
            raise FileNotFoundError(format_missing_path_message(resolution, "文件不存在"))
            
        suffix = file_path.suffix.lower()
        if suffix in self.BINARY_EXTENSIONS:
            stat = await aiofiles.os.stat(file_path)
            return f"[二进制文件: {file_path.name}, 类型: {suffix}, 大小: {stat.st_size / 1024:.1f}KB - 无法作为文本读取]"

        try:
            async with aiofiles.open(file_path, encoding=encoding) as f:
                content = await f.read()
                notice = format_repair_notice(resolution)
                return f"{notice}\n{content}" if notice else content
        except UnicodeDecodeError:
            stat = await aiofiles.os.stat(file_path)
            return f"[无法解码的文件: {file_path.name}, 大小: {stat.st_size / 1024:.1f}KB - 可能是二进制文件]"

    async def write(self, path: str, content: str, encoding: str = "utf-8") -> None:
        workspace_path = get_request_workspace_path()
        resolution = resolve_tool_path(path, cwd=self.base_path, workspace_path=workspace_path, expect="parent")
        log_path_resolution(
            tool_name="write_file",
            result=resolution,
            cwd=self.base_path,
            workspace_path=workspace_path,
        )
        file_path = Path(resolution.resolved_path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        async with aiofiles.open(file_path, mode="w", encoding=encoding) as f:
            await f.write(content)

    async def list_dir(self, path: str = ".", pattern: str = "*", recursive: bool = False) -> list[str]:
        workspace_path = get_request_workspace_path()
        resolution = resolve_tool_path(path, cwd=self.base_path, workspace_path=workspace_path, expect="dir")
        log_path_resolution(
            tool_name="list_directory",
            result=resolution,
            cwd=self.base_path,
            workspace_path=workspace_path,
        )
        dir_path = Path(resolution.resolved_path)
        if not dir_path.exists():
            raise FileNotFoundError(format_missing_path_message(resolution, "目录不存在"))
            
        if recursive:
            return [str(p.relative_to(dir_path)) for p in dir_path.rglob(pattern)]
        else:
            return [str(p.relative_to(dir_path)) for p in dir_path.glob(pattern)]

    async def search(self, pattern: str, path: str = ".", content_pattern: str | None = None) -> list[str]:
        workspace_path = get_request_workspace_path()
        resolution = resolve_tool_path(path, cwd=self.base_path, workspace_path=workspace_path, expect="dir")
        log_path_resolution(
            tool_name="search_file",
            result=resolution,
            cwd=self.base_path,
            workspace_path=workspace_path,
        )
        dir_path = Path(resolution.resolved_path)
        if not dir_path.exists():
            raise FileNotFoundError(format_missing_path_message(resolution, "搜索目录不存在"))
            
        matches = []
        for file_path in dir_path.rglob(pattern):
            if file_path.is_file():
                if content_pattern:
                    try:
                        content = file_path.read_text(encoding="utf-8")
                        if re.search(content_pattern, content):
                            matches.append(str(file_path.relative_to(dir_path)))
                    except Exception:
                        pass
                else:
                    matches.append(str(file_path.relative_to(dir_path)))
        return matches

    async def copy(self, src: str, dst: str) -> None:
        workspace_path = get_request_workspace_path()
        src_resolution = resolve_tool_path(src, cwd=self.base_path, workspace_path=workspace_path, expect="any")
        dst_resolution = resolve_tool_path(dst, cwd=self.base_path, workspace_path=workspace_path, expect="parent")
        log_path_resolution(tool_name="copy_path.src", result=src_resolution, cwd=self.base_path, workspace_path=workspace_path)
        log_path_resolution(tool_name="copy_path.dst", result=dst_resolution, cwd=self.base_path, workspace_path=workspace_path)
        src_path = Path(src_resolution.resolved_path)
        dst_path = Path(dst_resolution.resolved_path)
        if not src_path.exists():
            raise FileNotFoundError(format_missing_path_message(src_resolution, "源路径不存在"))
            
        if src_path.is_file():
            dst_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_path, dst_path)
        else:
            shutil.copytree(src_path, dst_path)

    async def move(self, src: str, dst: str) -> None:
        workspace_path = get_request_workspace_path()
        src_resolution = resolve_tool_path(src, cwd=self.base_path, workspace_path=workspace_path, expect="any")
        dst_resolution = resolve_tool_path(dst, cwd=self.base_path, workspace_path=workspace_path, expect="parent")
        log_path_resolution(tool_name="move_path.src", result=src_resolution, cwd=self.base_path, workspace_path=workspace_path)
        log_path_resolution(tool_name="move_path.dst", result=dst_resolution, cwd=self.base_path, workspace_path=workspace_path)
        src_path = Path(src_resolution.resolved_path)
        dst_path = Path(dst_resolution.resolved_path)
        if not src_path.exists():
            raise FileNotFoundError(format_missing_path_message(src_resolution, "源路径不存在"))
            
        dst_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(src_path, dst_path)


# =====================================================================
# Plugin Registration
# =====================================================================

def register(skills_manager):
    ft = FileTool()

    @skills_manager.skill(
        name="read_file",
        description="读取文本文件内容（代码、配置、日志等）。禁止用于二进制文件。",
        parameters={
            "properties": {
                "path": {"type": "string", "description": "要读取的文件绝对或相对路径"},
                "encoding": {"type": "string", "description": "文件编码，默认 utf-8", "default": "utf-8"}
            },
            "required": ["path"]
        },
        category="filesystem"
    )
    async def read_file(path: str, encoding: str = "utf-8") -> str:
        try:
            return await ft.read(path, encoding)
        except Exception as e:
            return f"❌ 文件读取失败: {e}"

    @skills_manager.skill(
        name="write_file",
        description="向目标文件写入完整的文本内容。如果目录不存在会自动创建。",
        parameters={
            "properties": {
                "path": {"type": "string", "description": "要写入的文件路径"},
                "content": {"type": "string", "description": "完整的文本内容"},
                "encoding": {"type": "string", "description": "文件编码，默认 utf-8", "default": "utf-8"}
            },
            "required": ["path", "content"]
        },
        category="filesystem"
    )
    async def write_file(path: str, content: str, encoding: str = "utf-8") -> str:
        try:
            await ft.write(path, content, encoding)
            resolution = resolve_tool_path(path, cwd=ft.base_path, workspace_path=get_request_workspace_path(), expect="parent")
            notice = format_repair_notice(resolution)
            base = f"✅ 成功写入文件: {resolution.resolved_path if resolution.was_repaired else path}"
            return f"{notice}\n{base}" if notice else base
        except Exception as e:
            return f"❌ 文件写入失败: {e}"

    @skills_manager.skill(
        name="list_directory",
        description="列出目录中的文件和子文件夹。",
        parameters={
            "properties": {
                "path": {"type": "string", "description": "要查看的目录路径，默认当前工作目录", "default": "."},
                "pattern": {"type": "string", "description": "匹配模式(如 *.py)，默认 *", "default": "*"},
                "recursive": {"type": "boolean", "description": "是否递归子目录，默认 false", "default": False}
            },
            "required": []
        },
        category="filesystem"
    )
    async def list_directory(path: str = ".", pattern: str = "*", recursive: bool = False) -> str:
        try:
            files = await ft.list_dir(path, pattern, recursive)
            resolution = resolve_tool_path(path, cwd=ft.base_path, workspace_path=get_request_workspace_path(), expect="dir")
            notice = format_repair_notice(resolution)
            body = "\\n".join(files) if files else "(空目录或无匹配文件)"
            return f"{notice}\n{body}" if notice else body
        except Exception as e:
            return f"❌ 目录读取失败: {e}"

    @skills_manager.skill(
        name="search_file",
        description="基于文件名模式和可选的内容正则在指定目录下搜索文件。",
        parameters={
            "properties": {
                "pattern": {"type": "string", "description": "文件名提取模式(如 *.py)必填"},
                "path": {"type": "string", "description": "要搜索的父目录，默认 .", "default": "."},
                "content_pattern": {"type": "string", "description": "正则表达式用于匹配文件内的文字(可选)"}
            },
            "required": ["pattern"]
        },
        category="filesystem"
    )
    async def search_file(pattern: str, path: str = ".", content_pattern: str = None) -> str:
        try:
            matches = await ft.search(pattern, path, content_pattern)
            resolution = resolve_tool_path(path, cwd=ft.base_path, workspace_path=get_request_workspace_path(), expect="dir")
            notice = format_repair_notice(resolution)
            body = "\\n".join(matches) if matches else "(未找到匹配的内容)"
            return f"{notice}\n{body}" if notice else body
        except Exception as e:
            return f"❌ 搜索文件失败: {e}"

    @skills_manager.skill(
        name="delete_path",
        description="永久删除文件或整个目录，请谨慎使用！",
        parameters={
            "properties": {
                "path": {"type": "string", "description": "要删除的文件或目录路径"}
            },
            "required": ["path"]
        },
        category="filesystem"
    )
    async def delete_path(path: str) -> str:
        try:
            workspace_path = get_request_workspace_path()
            resolution = resolve_tool_path(path, cwd=ft.base_path, workspace_path=workspace_path, expect="any")
            log_path_resolution(tool_name="delete_path", result=resolution, cwd=ft.base_path, workspace_path=workspace_path)
            p = Path(resolution.resolved_path)
            if not p.exists():
                return f"⚠️ {format_missing_path_message(resolution, '路径已被删除或不存在')}"
            if p.is_file():
                await aiofiles.os.remove(p)
            elif p.is_dir():
                shutil.rmtree(p)
            notice = format_repair_notice(resolution)
            base = f"✅ 成功删除: {resolution.resolved_path if resolution.was_repaired else path}"
            return f"{notice}\n{base}" if notice else base
        except Exception as e:
            return f"❌ 删除失败: {e}"

    @skills_manager.skill(
        name="copy_path",
        description="将文件或目录拷贝到目标位置。",
        parameters={
            "properties": {
                "src": {"type": "string", "description": "源文件或目录路径"},
                "dst": {"type": "string", "description": "目标路径"}
            },
            "required": ["src", "dst"]
        },
        category="filesystem"
    )
    async def copy_path(src: str, dst: str) -> str:
        try:
            await ft.copy(src, dst)
            src_resolution = resolve_tool_path(src, cwd=ft.base_path, workspace_path=get_request_workspace_path(), expect="any")
            dst_resolution = resolve_tool_path(dst, cwd=ft.base_path, workspace_path=get_request_workspace_path(), expect="parent")
            notices = [notice for notice in (format_repair_notice(src_resolution), format_repair_notice(dst_resolution)) if notice]
            base = f"✅ 成功从 {src_resolution.resolved_path if src_resolution.was_repaired else src} 复制到 {dst_resolution.resolved_path if dst_resolution.was_repaired else dst}"
            return "\n".join([*notices, base]) if notices else base
        except Exception as e:
            return f"❌ 复制失败: {e}"

    @skills_manager.skill(
        name="move_path",
        description="将文件或目录移动到新位置（也可重命名）。",
        parameters={
            "properties": {
                "src": {"type": "string", "description": "源文件或目录路径"},
                "dst": {"type": "string", "description": "目标路径"}
            },
            "required": ["src", "dst"]
        },
        category="filesystem"
    )
    async def move_path(src: str, dst: str) -> str:
        try:
            await ft.move(src, dst)
            src_resolution = resolve_tool_path(src, cwd=ft.base_path, workspace_path=get_request_workspace_path(), expect="any")
            dst_resolution = resolve_tool_path(dst, cwd=ft.base_path, workspace_path=get_request_workspace_path(), expect="parent")
            notices = [notice for notice in (format_repair_notice(src_resolution), format_repair_notice(dst_resolution)) if notice]
            base = f"✅ 成功从 {src_resolution.resolved_path if src_resolution.was_repaired else src} 移动到 {dst_resolution.resolved_path if dst_resolution.was_repaired else dst}"
            return "\n".join([*notices, base]) if notices else base
        except Exception as e:
            return f"❌ 移动失败: {e}"

    @skills_manager.skill(
        name="create_directory",
        description="创建目录，若父目录不存在则自动递归创建。",
        parameters={
            "properties": {
                "path": {"type": "string", "description": "要创建的目录路径"}
            },
            "required": ["path"]
        },
        category="filesystem"
    )
    async def create_directory(path: str) -> str:
        try:
            workspace_path = get_request_workspace_path()
            resolution = resolve_tool_path(path, cwd=ft.base_path, workspace_path=workspace_path, expect="parent")
            log_path_resolution(tool_name="create_directory", result=resolution, cwd=ft.base_path, workspace_path=workspace_path)
            p = Path(resolution.resolved_path)
            p.mkdir(parents=True, exist_ok=True)
            notice = format_repair_notice(resolution)
            base = f"✅ 成功创建目录: {resolution.resolved_path if resolution.was_repaired else path}"
            return f"{notice}\n{base}" if notice else base
        except Exception as e:
            return f"❌ 目录创建失败: {e}"

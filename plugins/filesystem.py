import os
import shutil
from pathlib import Path
import logging
import aiofiles
import aiofiles.os
import re

logger = logging.getLogger(__name__)

class FileTool:
    """内部文件操作工具，参考自 openakita 原生实现。"""
    
    def __init__(self, base_path: str = None):
        self.base_path = Path(base_path) if base_path else Path.cwd()

    def _resolve_path(self, path: str) -> Path:
        """解析路径（支持相对目录隔离）"""
        p = Path(path)
        if p.is_absolute():
            return p
        return self.base_path / p

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
        file_path = self._resolve_path(path)
        if not file_path.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")
            
        suffix = file_path.suffix.lower()
        if suffix in self.BINARY_EXTENSIONS:
            stat = await aiofiles.os.stat(file_path)
            return f"[二进制文件: {file_path.name}, 类型: {suffix}, 大小: {stat.st_size / 1024:.1f}KB - 无法作为文本读取]"

        try:
            async with aiofiles.open(file_path, encoding=encoding) as f:
                return await f.read()
        except UnicodeDecodeError:
            stat = await aiofiles.os.stat(file_path)
            return f"[无法解码的文件: {file_path.name}, 大小: {stat.st_size / 1024:.1f}KB - 可能是二进制文件]"

    async def write(self, path: str, content: str, encoding: str = "utf-8") -> None:
        file_path = self._resolve_path(path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        async with aiofiles.open(file_path, mode="w", encoding=encoding) as f:
            await f.write(content)

    async def list_dir(self, path: str = ".", pattern: str = "*", recursive: bool = False) -> list[str]:
        dir_path = self._resolve_path(path)
        if not dir_path.exists():
            raise FileNotFoundError(f"目录不存在: {dir_path}")
            
        if recursive:
            return [str(p.relative_to(dir_path)) for p in dir_path.rglob(pattern)]
        else:
            return [str(p.relative_to(dir_path)) for p in dir_path.glob(pattern)]

    async def search(self, pattern: str, path: str = ".", content_pattern: str | None = None) -> list[str]:
        dir_path = self._resolve_path(path)
        if not dir_path.exists():
            raise FileNotFoundError(f"搜索目录不存在: {dir_path}")
            
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
        src_path = self._resolve_path(src)
        dst_path = self._resolve_path(dst)
        if not src_path.exists():
            raise FileNotFoundError(f"源路径不存在: {src_path}")
            
        if src_path.is_file():
            dst_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_path, dst_path)
        else:
            shutil.copytree(src_path, dst_path)

    async def move(self, src: str, dst: str) -> None:
        src_path = self._resolve_path(src)
        dst_path = self._resolve_path(dst)
        if not src_path.exists():
            raise FileNotFoundError(f"源路径不存在: {src_path}")
            
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
            return f"✅ 成功写入文件: {path}"
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
            return "\\n".join(files) if files else "(空目录或无匹配文件)"
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
            return "\\n".join(matches) if matches else "(未找到匹配的内容)"
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
            p = ft._resolve_path(path)
            if not p.exists():
                return f"⚠️ 路径已被删除或不存在: {path}"
            if p.is_file():
                await aiofiles.os.remove(p)
            elif p.is_dir():
                shutil.rmtree(p)
            return f"✅ 成功删除: {path}"
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
            return f"✅ 成功从 {src} 复制到 {dst}"
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
            return f"✅ 成功从 {src} 移动到 {dst}"
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
            p = ft._resolve_path(path)
            p.mkdir(parents=True, exist_ok=True)
            return f"✅ 成功创建目录: {path}"
        except Exception as e:
            return f"❌ 目录创建失败: {e}"

---
name: file-manager
description: |
  高性能原生异步文件管理插件。
  提供 read_file, write_file, list_directory, search_file, delete_path, copy_path, move_path, create_directory 等原生方法。
  运行在 Python 事件循环中，速度远超 shell，具有二进制文件防呆安全机制。
  关键词: filesystem, 文件, 目录, 增删改查, aiofiles
license: MIT
metadata:
  author: OpenAkita Native Port
  version: "2.0.0"
---

# File Manager (Native Plugin)

此技能提供一套完整的原生异步**文件与目录操作系统**，用于代替早期较慢的系统 `shell` 方式操作。

## 功能特性 (Features)

该技能模块已经在 `plugins/filesystem.py` 中被作为内置插件加载，提供了以下原生 Python 方法，并且速度极快。

- `read_file`: 读取文本文件，并拦截大体积的二进制文件防止宕机。
- `write_file`: 快速写出文本，会自动递归创建所需的父目录。
- `list_directory`: 高效扫描目录结构。
- `search_file`: 使用 glob 与可选的纯文本 Regex 进行深度搜索。
- `delete_path`, `copy_path`, `move_path`, `create_directory`: 常见文件层级 API (增删改)。

## Implementation Details (技术细节)

- **工具执行位置**: 无需调用额外的 Python CLI 脚本，直接通过已挂载到 FastAPI 服务器内存中的 `plugins/filesystem.py` 进行 `FileTool` 类处理。
- **并发机制**: 默认使用 `aiofiles` 执行无阻塞文件 IO 支持高并发。

> 注意：此 `SKILL.md` 仅为大模型和系统的元信息注册使用说明，实际业务逻辑在 `openGuiclaw/plugins/filesystem.py` 控制，这里不需要独立的 `scripts` 文件夹包裹。

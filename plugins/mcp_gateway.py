"""
MCP (Model Context Protocol) 客户端网关

允许大模型连接并调用符合标准的本机 MCP Server（Stdio传输协议）。
支持配置文件加载和常用 MCP 服务器快捷方式。

配置文件格式 (config/mcp_servers.json):
{
    "mcpServers": {
        "server-name": {
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-filesystem", "D:/test_dir"],
            "env": {"KEY": "value"}
        }
    }
}
"""

import json
import os
from pathlib import Path
from typing import Dict, Any, Optional, List

# Cache for active MCP clients to reuse the expensive handshake process
# Key: server_command definition
_ACTIVE_CLIENTS: Dict[str, Any] = {}

# We use atexit to ensure child processes are terminated when main.py stops
import atexit


def cleanup_all_clients():
    """清理所有 MCP 客户端进程"""
    print("Cleaning up MCP Server subprocesses...")
    import asyncio
    for cmd, client in _ACTIVE_CLIENTS.items():
        try:
            if hasattr(client, 'process') and client.process and client.process.returncode is None:
                # 在新的事件循环中清理
                asyncio.run(client.cleanup())
        except Exception:
            pass
    _ACTIVE_CLIENTS.clear()


atexit.register(cleanup_all_clients)


# 预定义的常用 MCP 服务器模板
MCP_SERVER_TEMPLATES = {
    "filesystem": {
        "package": "@modelcontextprotocol/server-filesystem",
        "description": "文件系统操作 - 读写指定目录的文件",
        "example_args": ["D:/test_dir"]
    },
    "github": {
        "package": "@modelcontextprotocol/server-github",
        "description": "GitHub API - 搜索仓库、获取 Issue、PR 等",
        "example_args": [],
        "env_required": ["GITHUB_TOKEN"]
    },
    "brave-search": {
        "package": "@modelcontextprotocol/server-brave-search",
        "description": "Brave 搜索 - 网络搜索",
        "example_args": [],
        "env_required": ["BRAVE_API_KEY"]
    },
    "sequential-thinking": {
        "package": "@modelcontextprotocol/server-sequential-thinking",
        "description": "顺序思考 - 帮助 AI 进行逐步推理",
        "example_args": []
    },
    "puppeteer": {
        "package": "@modelcontextprotocol/server-puppeteer",
        "description": "浏览器自动化 - 使用 Puppeteer 控制浏览器",
        "example_args": []
    },
    "sqlite": {
        "package": "@modelcontextprotocol/server-sqlite",
        "description": "SQLite 数据库 - 执行 SQL 查询",
        "example_args": ["./database.db"]
    },
}


def get_template_info(template_name: str = None) -> Dict[str, Any]:
    """获取 MCP 服务器模板信息"""
    if template_name:
        return MCP_SERVER_TEMPLATES.get(template_name, {})
    return MCP_SERVER_TEMPLATES


def build_server_command(template: str, *args) -> str:
    """
    根据模板构建 MCP 服务器启动命令
    
    Args:
        template: 服务器模板名称 (filesystem, github, etc.)
        *args: 额外的参数
        
    Returns:
        完整的启动命令字符串
    """
    if template not in MCP_SERVER_TEMPLATES:
        raise ValueError(f"Unknown template: {template}. Available: {list(MCP_SERVER_TEMPLATES.keys())}")
    
    template_info = MCP_SERVER_TEMPLATES[template]
    package = template_info["package"]
    
    # 构建命令
    cmd_parts = ["npx", "-y", package] + list(args) + template_info.get("example_args", [])
    return " ".join(cmd_parts)


def load_servers_from_config(config_path: Path) -> Dict[str, Dict[str, Any]]:
    """
    从配置文件加载 MCP 服务器配置
    
    Args:
        config_path: 配置文件路径
        
    Returns:
        服务器配置字典
    """
    if not config_path.exists():
        return {}
    
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
        servers = data.get("mcpServers", {})
        print(f"Loaded {len(servers)} MCP servers from {config_path}")
        return servers
    except Exception as e:
        print(f"Failed to load MCP config: {e}")
        return {}


def register(skills_manager):
    """注册 MCP 技能到 SkillsManager"""
    
    @skills_manager.skill(
        name="mcp_list_templates",
        description="列出所有可用的 MCP 服务器模板。返回预定义的服务器类型及其描述，帮助用户选择合适的 MCP 服务。",
        parameters={
            "type": "object",
            "properties": {},
            "required": []
        },
        category="system"
    )
    def mcp_list_templates() -> str:
        """列出可用的 MCP 服务器模板"""
        out = ["📦 可用的 MCP 服务器模板:\n"]
        for name, info in MCP_SERVER_TEMPLATES.items():
            out.append(f"### {name}")
            out.append(f"- 描述: {info['description']}")
            out.append(f"- 包名: {info['package']}")
            if 'env_required' in info:
                out.append(f"- 需要环境变量: {', '.join(info['env_required'])}")
            out.append("")
        return "\n".join(out)
    
    @skills_manager.skill(
        name="call_mcp_tool",
        description="""调用外挂的 MCP (Model Context Protocol) 服务的工具。适用于文件系统、检索、GitHub、网络搜索等三方扩展。

📋 使用步骤：
1. 如果不确定有哪些工具，传入 tool_name="discover" 查看所有可用工具
2. 根据返回的工具列表，选择合适的工具传入

💡 常用服务器命令示例：
- 文件系统: npx -y @modelcontextprotocol/server-filesystem D:/path/to/dir
- GitHub: npx -y @modelcontextprotocol/server-github (需要 GITHUB_TOKEN 环境变量)
- Brave 搜索: npx -y @modelcontextprotocol/server-brave-search (需要 BRAVE_API_KEY)

🔧 快捷模板（推荐）:
使用 build_server_command("template_name", ...arg) 构建命令，例如：
- build_server_command("filesystem", "D:/qwen_autogui")
- build_server_command("github")""",
        parameters={
            "type": "object",
            "properties": {
                "server_command": {
                    "type": "string",
                    "description": "启动 MCP 服务的完整 Shell 命令，或使用模板快捷方式。模板格式: template:arg1:arg2，例如 'filesystem:D:/test'"
                },
                "tool_name": {
                    "type": "string",
                    "description": "如果不知道具体工具名，传入 'discover'，系统将返回所有可用工具。如果知道，传入工具在服务器上的真实名称。"
                },
                "arguments": {
                    "type": "string",
                    "description": "传递给该工具的参数列表（合法的 JSON 字符串）。如果是 discover 则可传 '{}'"
                }
            },
            "required": ["server_command", "tool_name", "arguments"]
        },
        category="system"
    )
    def call_mcp_tool(server_command: str, tool_name: str, arguments: str) -> str:
        """调用 MCP 工具"""
        # 解析模板快捷方式
        if ":" in server_command and not server_command.startswith("npx") and not server_command.startswith("python"):
            parts = server_command.split(":")
            template = parts[0]
            template_args = parts[1:]
            try:
                server_command = build_server_command(template, *template_args)
            except ValueError as e:
                return f"❌ {e}"
        
        try:
            args_dict = json.loads(arguments)
        except json.JSONDecodeError:
            return "❌ `arguments` 必须是合法的 JSON 字符串。"

        import asyncio
        from core.mcp_client import MCPStdioClient

        # We must run asynchronous client code within a synchronous function.
        # This wrapper handles setting up a temporary event loop.
        async def _run_mcp():
            client = _ACTIVE_CLIENTS.get(server_command)
            
            # 1. Provision & Handshake
            if not client:
                import shlex
                parts = shlex.split(server_command)
                if not parts:
                    return f"❌ 无效的启动命令: {server_command}"
                
                client = MCPStdioClient(parts[0], parts[1:])
                _ACTIVE_CLIENTS[server_command] = client
                
                try:
                    await client.connect()
                    # Handshake
                    await client.initialize()
                except Exception as e:
                    _ACTIVE_CLIENTS.pop(server_command, None)
                    return f"❌ MCP 建立连接或握手失败: {e}"
            
            # 2. Tool Discovery branch
            if tool_name.lower() == "discover":
                try:
                    tools = await client.list_tools()
                    # Formatting tools array to a readable string for the LLM
                    out = [f"✅ MCP 服务已上线。提供的工具共 {len(tools)} 个:"]
                    for t in tools:
                        name = t.get("name")
                        desc = t.get("description", "无描述")
                        schema = json.dumps(t.get("inputSchema", {}), ensure_ascii=False)
                        out.append(f" - [{name}]: {desc}\n   Schema: {schema}")
                    return "\n".join(out)
                except Exception as e:
                    return f"❌ MCP 获取工具列表失败: {e}"

            # 3. Execution branch
            try:
                result = await client.call_tool(tool_name, args_dict)
                return f"[MCP Result] {tool_name}:\n{result}"
            except Exception as e:
                return f"❌ MCP 工具 '{tool_name}' 调用失败: {e}"

        # Standard asyncio wrap
        return asyncio.run(_run_mcp())

    @skills_manager.skill(
        name="mcp_disconnect",
        description="断开并清理指定的 MCP 服务器连接。如果不再需要使用某个 MCP 服务，调用此函数可以释放资源。",
        parameters={
            "type": "object",
            "properties": {
                "server_command": {
                    "type": "string",
                    "description": "启动 MCP 服务的命令（与 call_mcp_tool 中使用的一致）"
                }
            },
            "required": ["server_command"]
        },
        category="system"
    )
    def mcp_disconnect(server_command: str) -> str:
        """断开 MCP 服务器连接"""
        import asyncio
        
        async def _disconnect():
            client = _ACTIVE_CLIENTS.get(server_command)
            if client:
                try:
                    await client.cleanup()
                except Exception as e:
                    return f"❌ 清理失败: {e}"
                _ACTIVE_CLIENTS.pop(server_command, None)
                return f"✅ 已断开 MCP 服务器: {server_command}"
            return f"⚠️ 未找到活跃的 MCP 服务器: {server_command}"
        
        return asyncio.run(_disconnect())

    @skills_manager.skill(
        name="mcp_list_active",
        description="列出当前所有活跃的 MCP 服务器连接。",
        parameters={
            "type": "object",
            "properties": {},
            "required": []
        },
        category="system"
    )
    def mcp_list_active() -> str:
        """列出活跃的 MCP 服务器"""
        if not _ACTIVE_CLIENTS:
            return "📭 当前没有活跃的 MCP 服务器连接"
        
        out = [f"🔌 活跃的 MCP 服务器 ({len(_ACTIVE_CLIENTS)} 个):"]
        for cmd, client in _ACTIVE_CLIENTS.items():
            tool_count = len(client.available_tools) if hasattr(client, 'available_tools') else 0
            status = "已连接" if client.process and client.process.returncode is None else "已断开"
            out.append(f"- 命令: {cmd[:60]}..." if len(cmd) > 60 else f"- 命令: {cmd}")
            out.append(f"  状态: {status}, 工具数: {tool_count}")
        return "\n".join(out)

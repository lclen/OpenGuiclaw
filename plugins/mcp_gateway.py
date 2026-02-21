"""
MCP (Model Context Protocol) 客户端网关

使用官方 MCP SDK 连接 MCP 服务器。
支持从配置文件加载 MCP 服务器。

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
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

# 官方 MCP SDK
try:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    MCP_SDK_AVAILABLE = True
except ImportError:
    MCP_SDK_AVAILABLE = False
    logging.warning("MCP SDK not installed. Run: pip install mcp")

# MCP 配置文件路径
MCP_CONFIG_PATH = Path(__file__).parent.parent / "config" / "mcp_servers.json"

logger = logging.getLogger("mcp_gateway")

# Cache for active MCP clients
_ACTIVE_CLIENTS: Dict[str, Any] = {}

import threading
import asyncio
import atexit

_mcp_loop = None
_mcp_thread = None

def _start_background_loop(loop):
    asyncio.set_event_loop(loop)
    loop.run_forever()

def _get_mcp_loop():
    global _mcp_loop, _mcp_thread
    if _mcp_loop is None:
        _mcp_loop = asyncio.new_event_loop()
        _mcp_thread = threading.Thread(target=_start_background_loop, args=(_mcp_loop,), daemon=True)
        _mcp_thread.start()
    return _mcp_loop

def _run_async(coro, timeout=None):
    """Run coroutine in the persistent background MCP thread."""
    loop = _get_mcp_loop()
    future = asyncio.run_coroutine_threadsafe(coro, loop)
    try:
        import concurrent.futures
        return future.result(timeout=timeout)
    except concurrent.futures.TimeoutError:
        return None


def cleanup_all_clients():
    """清理所有 MCP 客户端进程"""
    logger.info("Cleaning up MCP Server subprocesses...")
    
    # 复制一份 keys 避免迭代时修改
    names = list(_ACTIVE_CLIENTS.keys())
    for name in names:
        try:
            _run_async(_disconnect_server(name), timeout=1.5)
        except Exception:
            pass
    _ACTIVE_CLIENTS.clear()
    
    global _mcp_loop
    if _mcp_loop:
        _mcp_loop.call_soon_threadsafe(_mcp_loop.stop)


atexit.register(cleanup_all_clients)


async def _disconnect_server(server_name: str):
    """断开服务器连接"""
    if server_name in _ACTIVE_CLIENTS:
        conn = _ACTIVE_CLIENTS.pop(server_name)
        try:
            stack = conn.get("stack")
            if stack:
                import asyncio
                # Give it at most 2 seconds to close cleanly, otherwise forcefully drop it to prevent hanging at exit
                await asyncio.wait_for(stack.aclose(), timeout=2.0)
        except Exception as e:
            logger.debug(f"[MCP] Force closed {server_name} due to timeout/error: {e}")


def load_servers_from_config(config_path: Path = None) -> Dict[str, Dict[str, Any]]:
    """从配置文件加载 MCP 服务器配置"""
    if config_path is None:
        config_path = MCP_CONFIG_PATH
    
    if not config_path.exists():
        logger.warning(f"[MCP] Config file not found: {config_path}")
        return {}
    
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
        servers = data.get("mcpServers", {})
        logger.info(f"[MCP] Loaded {len(servers)} servers from {config_path}")
        return servers
    except Exception as e:
        logger.error(f"[MCP] Failed to load config: {e}")
        return {}


async def _connect_server(server_name: str, config: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """连接到 MCP 服务器"""
    if not MCP_SDK_AVAILABLE:
        return None
    
    command = config.get("command", "npx")
    args = config.get("args", [])
    env = config.get("env", {})
    
    # 设置环境变量
    full_env = os.environ.copy()
    for key, value in env.items():
        # 替换 ${VAR} 为实际环境变量值
        if value.startswith("${") and value.endswith("}"):
            var_name = value[2:-1]
            full_env[key] = os.environ.get(var_name, "")
        else:
            full_env[key] = value
    
    # 创建服务器参数
    server_params = StdioServerParameters(
        command=command,
        args=args,
        env=full_env if env else None,
    )
    
    import contextlib
    
    # 使用 AsyncExitStack 来管理 AnyIO/MCP 苛刻的上下文作用域
    stack = contextlib.AsyncExitStack()
    
    try:
        # 启动客户端
        stdio_cm = stdio_client(server_params)
        read, write = await stack.enter_async_context(stdio_cm)
        
        client_cm = ClientSession(read, write)
        client = await stack.enter_async_context(client_cm)
        await client.initialize()
        
        # 获取工具列表
        tools_result = await client.list_tools()
        tool_names = [t.name for t in tools_result.tools]
        
        return {
            "client": client,
            "stack": stack,
            "tools": tool_names,
        }
    except Exception as e:
        await stack.aclose()
        logger.error(f"MCP Connection failed: {e}")
        return None


async def _call_tool(server_name: str, tool_name: str, arguments: Dict[str, Any]) -> str:
    """调用 MCP 工具"""
    if server_name not in _ACTIVE_CLIENTS:
        return f"❌ 未连接到服务器: {server_name}"
    
    conn = _ACTIVE_CLIENTS[server_name]
    client = conn.get("client")
    
    if not client:
        return f"❌ 服务器连接无效: {server_name}"
    
    try:
        result = await client.call_tool(tool_name, arguments)
        
        # 解析结果
        content = []
        for item in result.content:
            if hasattr(item, "text"):
                content.append(item.text)
            elif hasattr(item, "data"):
                content.append(item.data)
        
        if not content:
            return "⚠️ 工具返回空结果"
        
        return "\n".join(content)
    except Exception as e:
        # 获取完整的错误信息
        import traceback
        error_msg = str(e) or type(e).__name__
        logger.error(f"[MCP] Tool call error: {error_msg}\n{traceback.format_exc()}")
        return f"❌ 调用失败: {error_msg}"


def register(skills_manager):
    """注册 MCP 技能到 SkillsManager"""
    
    @skills_manager.skill(
        name="mcp_list_servers",
        description="列出所有已配置的 MCP 服务器。从 config/mcp_servers.json 读取。",
        parameters={
            "type": "object",
            "properties": {},
            "required": []
        },
        category="system"
    )
    def mcp_list_servers() -> str:
        """列出已配置的 MCP 服务器"""
        servers = load_servers_from_config()
        
        if not servers:
            return "📭 未找到 MCP 服务器配置。请在 config/mcp_servers.json 中添加配置。"
        
        out = [f"📦 已配置的 MCP 服务器 ({len(servers)} 个):\n"]
        for name, config in servers.items():
            cmd = config.get("command", "")
            args = config.get("args", [])
            desc = config.get("description", "无描述")
            active = "✅ 已连接" if name in _ACTIVE_CLIENTS else "⚪ 未连接"
            
            out.append(f"### {name} ({active})")
            out.append(f"- 描述: {desc}")
            out.append(f"- 命令: {cmd} {' '.join(args)}")
            
            # 如果已连接，显示可用工具
            if name in _ACTIVE_CLIENTS:
                tools = _ACTIVE_CLIENTS[name].get("tools", [])
                out.append(f"- 工具: {', '.join(tools[:5])}{'...' if len(tools) > 5 else ''}")
            out.append("")
        
        return "\n".join(out)
    
    @skills_manager.skill(
        name="call_mcp_tool",
        description="""调用 MCP (Model Context Protocol) 服务的工具。

📋 使用步骤：
1. 先使用 mcp_list_servers 查看已配置的服务器
2. 如果服务器未连接，会自动连接
3. 如果不确定有哪些工具，传入 tool_name="discover"

⚠️ Context7 特殊用法（两阶段调用）：
1. 先调用 resolve-library-id，必须包含两个参数：{"libraryName": "库名", "query": "你的查询问题描述"} 获取库 ID
2. 再调用 query-docs，参数 {"libraryId": "上一步返回的ID", "query": "问题"}

💡 常用 MCP 服务器配置示例 (config/mcp_servers.json):
{
  "mcpServers": {
    "context7": {
      "command": "npx",
      "args": ["-y", "@upstash/context7-mcp@latest"]
    }
  }
}""",
        parameters={
            "type": "object",
            "properties": {
                "server_name": {
                    "type": "string",
                    "description": "服务器名称，对应 config/mcp_servers.json 中的键名"
                },
                "tool_name": {
                    "type": "string",
                    "description": "工具名称。如果不知道，传入 'discover' 查看所有工具"
                },
                "arguments": {
                    "type": "string",
                    "description": "工具参数（JSON 字符串）"
                }
            },
            "required": ["server_name", "tool_name", "arguments"]
        },
        category="system"
    )
    def call_mcp_tool(server_name: str, tool_name: str, arguments: str) -> str:
        """调用 MCP 工具"""
        if not MCP_SDK_AVAILABLE:
            return "❌ MCP SDK 未安装。请运行: pip install mcp"
        
        # 解析参数
        try:
            # We must ensure `arguments` becomes a proper python dict
            if not arguments or arguments.strip() == "{}":
                args_dict = {}
            else:
                args_dict = json.loads(arguments)
                # Ensure it's a dict representing the arguments object expected by the tool schema
                if not isinstance(args_dict, dict):
                    return "❌ arguments 必须是一个合法的 JSON 对象 (字典形式)"
        except json.JSONDecodeError:
            return "❌ arguments 必须是合法的 JSON 字符串"
        
        import asyncio
        
        async def _run():
            nonlocal server_name
            
            # 加载配置
            servers = load_servers_from_config()
            
            # 自动连接（如果未连接）
            if server_name not in _ACTIVE_CLIENTS:
                config = servers.get(server_name)
                if not config:
                    return f"❌ 未找到服务器配置: {server_name}"
                
                try:
                    logger.info(f"[MCP] Connecting to {server_name}...")
                    conn = await _connect_server(server_name, config)
                    if conn:
                        _ACTIVE_CLIENTS[server_name] = conn
                        logger.info(f"[MCP] Connected to {server_name}, tools: {conn.get('tools')}")
                    else:
                        return "❌ MCP SDK 不可用"
                except Exception as e:
                    import traceback
                    logger.error(f"[MCP] Connection failed: {e}\n{traceback.format_exc()}")
                    return f"❌ 连接失败: {e}"
            
            # discover 模式
            if tool_name.lower() == "discover":
                if server_name in _ACTIVE_CLIENTS:
                    tools = _ACTIVE_CLIENTS[server_name].get("tools", [])
                    return f"✅ 可用工具 ({len(tools)}):\n- " + "\n- ".join(tools)
                return "❌ 未连接服务器"
            
            # 调用工具
            return await _call_tool(server_name, tool_name, args_dict)
        
        return _run_async(_run())

    @skills_manager.skill(
        name="mcp_disconnect",
        description="断开指定的 MCP 服务器连接。",
        parameters={
            "type": "object",
            "properties": {
                "server_name": {"type": "string", "description": "服务器名称"}
            },
            "required": ["server_name"]
        },
        category="system"
    )
    def mcp_disconnect(server_name: str) -> str:
        """断开 MCP 服务器连接"""
        return _run_async(_disconnect_server(server_name)) or f"✅ 已断开: {server_name}"

    @skills_manager.skill(
        name="mcp_list_active",
        description="列出当前活跃的 MCP 服务器连接。",
        parameters={"type": "object", "properties": {}, "required": []},
        category="system"
    )
    def mcp_list_active() -> str:
        """列出活跃连接"""
        if not _ACTIVE_CLIENTS:
            return "📭 没有活跃的 MCP 连接"
        
        out = [f"🔌 活跃连接 ({len(_ACTIVE_CLIENTS)}):"]
        for name, conn in _ACTIVE_CLIENTS.items():
            tools = conn.get("tools", [])
            out.append(f"- {name}: {len(tools)} 个工具")
        return "\n".join(out)

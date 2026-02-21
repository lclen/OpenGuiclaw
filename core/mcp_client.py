"""
Asynchronous Model Context Protocol (MCP) Client over Stdio.

This module implements a lightweight, asynchronous JSON-RPC 2.0 client
that communicates with external MCP servers over standard input/output.
It handles the required initialization handshake, tool discovery, and tool execution.
"""

import asyncio
import json
import uuid
import logging
from typing import Dict, Any, Optional, List

# Setup a dedicated logger for MCP communication
logger = logging.getLogger("mcp_client")
logger.setLevel(logging.INFO)
if not logger.handlers:
    ch = logging.StreamHandler()
    formatter = logging.Formatter('[MCP Client] %(message)s')
    ch.setFormatter(formatter)
    logger.addHandler(ch)

class MCPClientError(Exception):
    """Exception raised for MCP Client errors."""
    pass

class MCPStdioClient:
    def __init__(self, command: str, args: List[str] = None, shell: bool = False):
        self.command = command
        self.args = args or []
        self.shell = shell  # 是否使用 shell 执行
        self.process: Optional[asyncio.subprocess.Process] = None
        
        self.request_id_counter = 1
        self.pending_requests: Dict[int, asyncio.Future] = {}
        
        # Reader task
        self._reader_task: Optional[asyncio.Task] = None
        
        # Tools caching
        self.available_tools: List[Dict[str, Any]] = []

    async def connect(self):
        """Creates the subprocess and starts the background reader."""
        if self.process is not None:
            return

        if self.shell:
            # Shell mode: combine command and args into a single string
            cmd_str = self.command
            if self.args:
                cmd_str += " " + " ".join(self.args)
            logger.info(f"Starting MCP Server process (shell): '{cmd_str}'")
            
            try:
                self.process = await asyncio.create_subprocess_shell(
                    cmd_str,
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
            except Exception as e:
                raise MCPClientError(f"Failed to start process '{cmd_str}': {e}")
        else:
            # Exec mode: command + args as separate list
            cmd_args = [self.command] + self.args
            cmd_str = " ".join(cmd_args)
            logger.info(f"Starting MCP Server process: '{cmd_str}'")
            
            try:
                self.process = await asyncio.create_subprocess_exec(
                    *cmd_args,
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
            except Exception as e:
                raise MCPClientError(f"Failed to start process '{cmd_str}': {e}")
        
        # Start reading stdout in background
        self._reader_task = asyncio.create_task(self._reader_loop())
        # We could also read stderr to log errors from the server, 
        # but for simplicity we'll just let it drop or log it silently.
        asyncio.create_task(self._stderr_reader_loop())

    async def _stderr_reader_loop(self):
        """Reads stderr from the subprocess and logs it."""
        try:
            while self.process and not self.process.stderr.at_eof():
                line = await self.process.stderr.readline()
                if not line:
                    break
                decoded = line.decode('utf-8', errors='replace').strip()
                if decoded:
                    logger.warning(f"Server STDERR: {decoded}")
        except Exception:
            pass

    async def _reader_loop(self):
        """Background task that reads lines from stdout and resolves Futures."""
        try:
            while self.process and not self.process.stdout.at_eof():
                line = await self.process.stdout.readline()
                if not line:
                    break
                
                decoded_line = line.decode('utf-8', errors='replace').strip()
                if not decoded_line:
                    continue
                
                # Check if it's a valid JSON-RPC message
                try:
                    payload = json.loads(decoded_line)
                except json.JSONDecodeError:
                    # Some servers output non-JSON log messages to stdout
                    # We should probably ignore them or log them as debug.
                    logger.debug(f"Received non-JSON from server stdout: {decoded_line}")
                    continue
                
                # If it has an ID, it's a response to one of our requests
                msg_id = payload.get("id")
                if msg_id is not None and msg_id in self.pending_requests:
                    future = self.pending_requests.pop(msg_id)
                    if not future.done():
                        # Check for JSON-RPC error
                        if "error" in payload:
                            future.set_exception(MCPClientError(payload["error"]))
                        else:
                            future.set_result(payload.get("result"))
                else:
                    # It might be a notification from the server (e.g. logMessage, telemetry)
                    method = payload.get("method")
                    if method:
                        logger.debug(f"Received Server Notification ({method}): {payload.get('params')}")

        except Exception as e:
            logger.error(f"Reader loop encountered error: {e}")
            self._fail_all_pending(e)

    def _fail_all_pending(self, exc: Exception):
        for msg_id, future in self.pending_requests.items():
            if not future.done():
                future.set_exception(exc)
        self.pending_requests.clear()

    async def _send_request(self, method: str, params: Optional[Dict[str, Any]] = None, timeout: float = 30.0) -> Any:
        """Sends a JSON-RPC request and waits for the response."""
        if not self.process or self.process.returncode is not None:
             raise MCPClientError("Process is not running. Cannot send request.")
             
        req_id = self.request_id_counter
        self.request_id_counter += 1
        
        payload = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": method
        }
        if params is not None:
            payload["params"] = params
            
        json_str = json.dumps(payload) + "\n"
        
        # Create a Future to wait for the response
        future = asyncio.get_event_loop().create_future()
        self.pending_requests[req_id] = future
        
        # Send
        self.process.stdin.write(json_str.encode('utf-8'))
        await self.process.stdin.drain()
        
        # Wait with timeout
        try:
            result = await asyncio.wait_for(future, timeout=timeout)
            return result
        except asyncio.TimeoutError:
            self.pending_requests.pop(req_id, None)
            raise MCPClientError(f"Request timeout for method '{method}' after {timeout} seconds.")

    async def _send_notification(self, method: str, params: Optional[Dict[str, Any]] = None):
        """Sends a JSON-RPC notification (does not expect a response)."""
        if not self.process or self.process.returncode is not None:
             raise MCPClientError("Process is not running. Cannot send notification.")
             
        payload = {
            "jsonrpc": "2.0",
            "method": method
        }
        if params is not None:
            payload["params"] = params
            
        json_str = json.dumps(payload) + "\n"
        self.process.stdin.write(json_str.encode('utf-8'))
        await self.process.stdin.drain()

    async def initialize(self) -> Dict[str, Any]:
        """Performs the MCP handshake sequence."""
        logger.info("Sending 'initialize' request...")
        
        init_params = {
            "protocolVersion": "2024-11-05",  # Current standard MCP version
            "clientInfo": {
                "name": "QwenAutoGUI-Client",
                "version": "1.0.0"
            },
            "capabilities": {
                # We don't support advanced sampling or roots yet
                "roots": {"listChanged": False},
                "sampling": {}
            }
        }
        
        result = await self._send_request("initialize", params=init_params, timeout=10.0)
        logger.info("Received 'initialize' response, sending 'initialized' notification.")
        
        # Complete handshake
        await self._send_notification("notifications/initialized")
        return result

    async def list_tools(self) -> List[Dict[str, Any]]:
        """Queries the server for available tools."""
        logger.info("Requesting 'tools/list'...")
        result = await self._send_request("tools/list", timeout=10.0)
        tools = result.get("tools", [])
        self.available_tools = tools
        logger.info(f"Discovered {len(tools)} tools from server.")
        return tools

    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> str:
        """Calls a specific tool on the server."""
        params = {
            "name": name,
            "arguments": arguments
        }
        logger.info(f"Calling tool '{name}'...")
        result = await self._send_request("tools/call", params=params, timeout=60.0)
        
        # Standard MCP tools/call returns an array of content blocks.
        # Format: {"content": [{"type": "text", "text": "result string"}]}
        content_blocks = result.get("content", [])
        
        # Find if it flagged as an error internally
        is_error = result.get("isError", False)
        
        # Combine text blocks
        output_parts = []
        for block in content_blocks:
            if block.get("type") == "text":
                output_parts.append(block.get("text", ""))
        
        final_text = "\n".join(output_parts)
        if is_error:
            return f"[Tool Error from Server]: {final_text}"
        return final_text

    async def cleanup(self):
        """Gracefully closes the connection and terminates the subprocess."""
        if self.process is None:
            return
            
        logger.info("Shutting down MCP Client...")
        self._fail_all_pending(MCPClientError("Client is shutting down"))
        
        if self._reader_task:
            self._reader_task.cancel()
            
        if self.process.returncode is None:
            try:
                # Close stdin to signal termination usually works for stdio servers
                self.process.stdin.close()
                await self.process.wait()
            except Exception:
                try:
                    self.process.terminate()
                except Exception:
                    pass
                    
        self.process = None
        logger.info("MCP Client terminated.")

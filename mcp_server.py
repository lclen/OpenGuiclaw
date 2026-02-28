import json
import base64
import sys
from pathlib import Path

import mss
import mss.tools
import pyautogui
from mcp.server.fastmcp import FastMCP

# 确保能 import 同目录的 agent.py
sys.path.insert(0, str(Path(__file__).parent))
from agent import ScreenAgent

mcp = FastMCP("openGuiclaw")

# 全局 agent 实例（懒加载）
_agent: ScreenAgent | None = None

def get_agent() -> ScreenAgent:
    global _agent
    if _agent is None:
        config_path = str(Path(__file__).parent / "config.json")
        _agent = ScreenAgent(config_path)
    return _agent


@mcp.tool()
def capture_screenshot() -> dict:
    """截取当前屏幕，返回 base64 编码的 PNG 图片"""
    with mss.mss() as sct:
        monitor = sct.monitors[1]
        screenshot = sct.grab(monitor)
        img_data = mss.tools.to_png(screenshot.rgb, screenshot.size)
        b64 = base64.b64encode(img_data).decode("utf-8")
    return {
        "image_base64": b64,
        "width": screenshot.size[0],
        "height": screenshot.size[1],
        "format": "png"
    }


@mcp.tool()
def execute_action(action_type: str, parameters: dict) -> str:
    """
    执行单步 GUI 动作。

    action_type 可选值：
      click, double_click, right_click, type, press,
      scroll, drag, move, wait, task_complete

    parameters 示例：
      click/double_click/right_click: {"x": 500, "y": 300}  (0-1000 归一化坐标)
      type: {"text": "hello"}
      press: {"keys": ["ctrl", "c"]}
      scroll: {"amount": 3, "x": 500, "y": 500}
      drag: {"start_x": 100, "start_y": 100, "end_x": 400, "end_y": 400}
      move: {"x": 500, "y": 500, "duration": 0.5}
      wait: {"seconds": 1.0}
    """
    from agent import Action
    agent = get_agent()
    action = Action(
        action_type=action_type,
        parameters=parameters,
        thought=""
    )
    return agent.execute_action(action)


@mcp.tool()
def run_task(task: str) -> str:
    """
    让 AI Agent 自主完成一个自然语言描述的任务。
    Agent 会循环截图 -> 分析 -> 执行动作，直到任务完成或达到最大迭代次数。

    示例：
      task = "打开记事本，输入 hello world，保存文件"
    """
    agent = get_agent()
    return agent.run(task)


@mcp.tool()
def get_screen_info() -> dict:
    """获取屏幕分辨率和显示器数量"""
    width, height = pyautogui.size()
    with mss.mss() as sct:
        monitor_count = len(sct.monitors) - 1  # monitors[0] 是虚拟合并屏
        monitors = [
            {"index": i, "left": m["left"], "top": m["top"],
             "width": m["width"], "height": m["height"]}
            for i, m in enumerate(sct.monitors[1:], start=1)
        ]
    return {
        "primary_width": width,
        "primary_height": height,
        "monitor_count": monitor_count,
        "monitors": monitors
    }


if __name__ == "__main__":
    mcp.run(transport="stdio")

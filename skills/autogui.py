"""
AutoGUI Skill Plugin

Wraps screen automation capabilities as a registered skill set.
Provides: screenshot_and_act (single-turn autonomous screen action).
"""

import json
import base64
import time
import re
from typing import Optional

import mss
import mss.tools
import pyautogui

from core.skills import SkillManager


def _capture_screen() -> str:
    """Capture screen and return base64-encoded PNG."""
    with mss.mss() as sct:
        monitor = sct.monitors[1]
        screenshot = sct.grab(monitor)
        img_data = mss.tools.to_png(screenshot.rgb, screenshot.size)
        return base64.b64encode(img_data).decode("utf-8")


def _map_coords(x: float, y: float) -> tuple[int, int]:
    """Map 0-1000 normalized coords to actual screen pixels."""
    w, h = pyautogui.size()
    return int(x / 1000 * w), int(y / 1000 * h)


def _execute_action(action_type: str, params: dict) -> str:
    """Execute a single GUI action."""
    t = action_type.lower()
    try:
        if t == "click":
            rx, ry = _map_coords(params.get("x", 500), params.get("y", 500))
            pyautogui.click(rx, ry)
            return f"点击 ({rx}, {ry})"
        elif t == "double_click":
            rx, ry = _map_coords(params.get("x", 500), params.get("y", 500))
            pyautogui.doubleClick(rx, ry)
            return f"双击 ({rx}, {ry})"
        elif t == "right_click":
            rx, ry = _map_coords(params.get("x", 500), params.get("y", 500))
            pyautogui.rightClick(rx, ry)
            return f"右键点击 ({rx}, {ry})"
        elif t == "type":
            text = params.get("text", "")
            import pyperclip
            pyperclip.copy(text)
            time.sleep(0.1)
            pyautogui.hotkey("ctrl", "v")
            return f"输入文字: {text}"
        elif t == "press":
            keys = params.get("keys", [])
            if isinstance(keys, str):
                keys = [keys]
            pyautogui.hotkey(*keys)
            return f"按键: {'+'.join(keys)}"
        elif t == "scroll":
            amount = params.get("amount", 3)
            x, y = params.get("x"), params.get("y")
            if x is not None and y is not None:
                rx, ry = _map_coords(x, y)
                pyautogui.scroll(amount, x=rx, y=ry)
            else:
                pyautogui.scroll(amount)
            return f"滚动: {amount}"
        elif t == "move":
            rx, ry = _map_coords(params.get("x", 500), params.get("y", 500))
            pyautogui.moveTo(rx, ry, duration=params.get("duration", 0.3))
            return f"移动鼠标到 ({rx}, {ry})"
        elif t == "drag":
            sx, sy = _map_coords(params.get("start_x", 0), params.get("start_y", 0))
            ex, ey = _map_coords(params.get("end_x", 0), params.get("end_y", 0))
            pyautogui.moveTo(sx, sy)
            pyautogui.drag(ex - sx, ey - sy, duration=params.get("duration", 0.5))
            return f"拖拽从 ({sx},{sy}) 到 ({ex},{ey})"
        elif t == "wait":
            s = params.get("seconds", 1.0)
            time.sleep(s)
            return f"等待 {s} 秒"
        elif t == "screenshot":
            return "[Screenshot captured]"
        else:
            return f"未知动作类型: {t}"
    except Exception as e:
        return f"动作执行失败: {e}"


def register(manager: SkillManager) -> None:
    """Register all AutoGUI skills into the provided SkillManager."""

    @manager.skill(
        name="autogui_action",
        description=(
            "执行一个屏幕 GUI 操作。支持 click / double_click / right_click / "
            "type / press / scroll / move / drag / wait。"
            "坐标使用 0-1000 归一化坐标系。"
        ),
        parameters={
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "click", "double_click", "right_click",
                        "type", "press", "scroll", "move", "drag", "wait"
                    ],
                    "description": "动作类型",
                },
                "params": {
                    "type": "object",
                    "description": (
                        "动作参数。"
                        "click/double_click/right_click: {x, y}。"
                        "type: {text}。"
                        "press: {keys: [key1, key2]}。"
                        "scroll: {amount, x?, y?}。"
                        "move: {x, y, duration?}。"
                        "drag: {start_x, start_y, end_x, end_y, duration?}。"
                        "wait: {seconds}。"
                    ),
                },
            },
            "required": ["action", "params"],
        },
        category="autogui",
    )
    def autogui_action(action: str, params: dict) -> str:
        return _execute_action(action, params)

    @manager.skill(
        name="get_screenshot",
        description="截取当前屏幕，返回 base64 编码的图像（约1MB+，仅在需要视觉分析时调用）。",
        parameters={"properties": {}, "required": []},
        category="autogui",
    )
    def get_screenshot() -> str:
        b64 = _capture_screen()
        return f"data:image/png;base64,{b64}"

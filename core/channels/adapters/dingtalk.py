"""
钉钉适配器

基于 dingtalk-stream SDK 实现 Stream 模式:
- WebSocket 长连接接收消息（无需公网 IP）
- 支持文本/图片/语音/文件/视频消息接收
- 支持文本/Markdown/图片/文件消息发送

参考文档:
- Stream 模式: https://opensource.dingtalk.com/developerpedia/docs/explore/tutorials/stream/overview
- 机器人接收消息: https://open-dingtalk.github.io/developerpedia/docs/learn/bot/appbot/receive/
- dingtalk-stream SDK: https://pypi.org/project/dingtalk-stream/
"""

import asyncio
import contextlib
import importlib.metadata
import json
import logging
import os
import re
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from ..base import ChannelAdapter
from ..markdown import contains_markdown
from ..types import (
    MediaFile,
    MediaStatus,
    MessageContent,
    OutgoingMessage,
    UnifiedMessage,
)
from core.runtime_deps import DependencySpec, ensure_runtime_dependencies, installed_version

logger = logging.getLogger(__name__)

# 延迟导入
httpx = None
dingtalk_stream = None
_dingtalk_runtime_checked = False
_dingtalk_runtime_ok = False


def _import_httpx():
    global httpx
    if httpx is None:
        import httpx as hx

        httpx = hx


def _import_dingtalk_stream():
    global dingtalk_stream
    if dingtalk_stream is None:
        try:
            import dingtalk_stream as ds

            dingtalk_stream = ds
        except ImportError as exc:
            raise ImportError(
                "钉钉 Stream SDK 未找到，请执行:\n  pip install dingtalk-stream"
            ) from exc

def _ensure_dingtalk_runtime() -> bool:
    global _dingtalk_runtime_checked, _dingtalk_runtime_ok, dingtalk_stream
    if _dingtalk_runtime_checked:
        return _dingtalk_runtime_ok

    _dingtalk_runtime_checked = True
    specs = (
        DependencySpec(
            module="dingtalk_stream",
            package="dingtalk-stream>=0.1.0",
            reason="钉钉 Stream SDK 缺失",
        ),
        DependencySpec(
            module="websockets",
            package="websockets>=11.0.2,<12",
            version_check=lambda: (_get_websockets_major_version() or 0) < 12,
            reason="钉钉 Stream 依赖 websockets < 12",
        ),
    )
    if not ensure_runtime_dependencies(*specs, context="dingtalk"):
        _dingtalk_runtime_ok = False
        return False
    dingtalk_stream = None

    try:
        _import_dingtalk_stream()
        websockets_major = _get_websockets_major_version()
        _dingtalk_runtime_ok = bool(websockets_major is not None and websockets_major < 12)
        if not _dingtalk_runtime_ok:
            logger.error(
                "[DingTalkAdapter] Runtime dependency check still failed after auto-fix. websockets_major=%s",
                websockets_major,
            )
        else:
            logger.info(
                "[DingTalkAdapter] Runtime dependency check passed. dingtalk-stream=%s websockets=%s python=%s",
                installed_version("dingtalk-stream"),
                installed_version("websockets"),
                sys.executable,
            )
        return _dingtalk_runtime_ok
    except Exception as exc:
        logger.error("[DingTalkAdapter] Runtime dependency import failed: %s", exc, exc_info=True)
        _dingtalk_runtime_ok = False
        return False


def _get_websockets_major_version() -> int | None:
    try:
        raw_version = importlib.metadata.version("websockets")
    except importlib.metadata.PackageNotFoundError:
        return None
    except Exception:
        return None

    try:
        return int(str(raw_version).split(".", 1)[0])
    except (TypeError, ValueError):
        return None


@dataclass
class DingTalkConfig:
    """钉钉配置"""

    app_key: str
    app_secret: str
    agent_id: str | None = None

    def __post_init__(self) -> None:
        if not self.app_key or not self.app_key.strip():
            raise ValueError("DingTalkConfig: app_key is required")
        if not self.app_secret or not self.app_secret.strip():
            raise ValueError("DingTalkConfig: app_secret is required")


class DingTalkStreamState(Enum):
    IDLE = "idle"
    CONNECTING = "connecting"
    RUNNING = "running"
    RECONNECTING = "reconnecting"
    STOPPED = "stopped"


@dataclass
class _StreamMetrics:
    connected_since: float | None = None
    last_message_at: float | None = None
    last_reconnect_at: float | None = None
    reconnect_count: int = 0
    dedupe_hit_count: int = 0
    messages_received: int = 0


@dataclass
class _CardState:
    card_id: str
    is_ai_card: bool = True


class DingTalkAdapter(ChannelAdapter):
    """
    钉钉适配器

    使用 Stream 模式接收消息（推荐）:
    - 无需公网 IP 和域名
    - 通过 WebSocket 长连接接收消息
    - 自动处理连接管理和重连

    支持消息类型:
    - 接收: text, picture, richText, audio, video, file
    - 发送: text, markdown, image, file
    """

    channel_name = "dingtalk"
    capabilities = {
        "streaming": True,
        "markdown": True,
        "send_image": True,
        "send_file": True,
        "send_voice": True,
    }

    API_BASE = "https://oapi.dingtalk.com"
    API_NEW = "https://api.dingtalk.com/v1.0"
    AI_CARD_TEMPLATE_ID = "382e4302-551d-4880-bf29-a30acfab2e71.schema"
    AI_CARD_CREATE_URL = "https://api.dingtalk.com/v1.0/card/instances"
    AI_CARD_DELIVER_URL = "https://api.dingtalk.com/v1.0/card/instances/deliver"
    AI_CARD_STREAM_URL = "https://api.dingtalk.com/v1.0/card/streaming"
    CARD_SEND_URL = "https://api.dingtalk.com/v1.0/im/v1.0/robot/interactiveCards/send"
    CARD_UPDATE_URL = "https://api.dingtalk.com/v1.0/im/robots/interactiveCards"
    _STREAM_WATCHDOG_INTERVAL = 15
    _STREAM_WATCHDOG_INITIAL_DELAY = 30
    _STREAM_RECONNECT_MIN_INTERVAL = 10
    _STREAM_RECONNECT_MAX_DELAY = 120
    _STREAM_STABLE_THRESHOLD = 300
    STALE_MESSAGE_THRESHOLD_S = 300
    _MARKDOWN_MAX_LENGTH = 3800

    def __init__(
        self,
        app_key: str,
        app_secret: str,
        agent_id: str | None = None,
        media_dir: Path | None = None,
        *,
        channel_name: str | None = None,
        bot_id: str | None = None,
        agent_profile_id: str = "default",
        footer_elapsed: bool | None = None,
        footer_status: bool | None = None,
    ):
        """
        Args:
            app_key: 应用 Client ID (原 AppKey，在钉钉开发者后台获取)
            app_secret: 应用 Client Secret (原 AppSecret，在钉钉开发者后台获取)
            agent_id: 应用 AgentId (发送消息时需要)
            media_dir: 媒体文件存储目录
            channel_name: 通道名称（多Bot时用于区分实例）
            bot_id: Bot 实例唯一标识
            agent_profile_id: 绑定的 agent profile ID
        """
        super().__init__(channel_name=channel_name, bot_id=bot_id, agent_profile_id=agent_profile_id)

        self.config = DingTalkConfig(
            app_key=app_key,
            app_secret=app_secret,
            agent_id=agent_id,
        )
        self.media_dir = Path(media_dir) if media_dir else Path("data/media/dingtalk")
        self.media_dir.mkdir(parents=True, exist_ok=True)

        # 旧版 access_token (oapi.dingtalk.com 接口用)
        self._old_access_token: str | None = None
        self._old_token_expires_at: float = 0
        # 新版 access_token (api.dingtalk.com/v1.0 接口用)
        self._access_token: str | None = None
        self._token_expires_at: float = 0
        self._http_client: Any | None = None
        self._token_lock = asyncio.Lock()
        self._old_token_lock = asyncio.Lock()

        # Stream 模式
        self._stream_client: Any | None = None
        self._stream_thread: threading.Thread | None = None
        self._stream_loop: asyncio.AbstractEventLoop | None = None
        self._main_loop: asyncio.AbstractEventLoop | None = None
        self._stream_watchdog_task: asyncio.Task | None = None
        self._stream_restart_count: int = 0
        self._stream_state = DingTalkStreamState.IDLE
        self._stream_metrics = _StreamMetrics()
        self._last_error: str | None = None

        # 缓存每个会话的 session webhook、发送者 userId、会话类型
        self._session_webhooks: dict[str, str] = {}
        self._conversation_users: dict[str, str] = {}  # conversationId -> senderId
        self._conversation_types: dict[str, str] = {}  # conversationId -> "1"(单聊)/"2"(群聊)
        self._seen_message_ids: dict[str, float] = {}
        self._seen_message_ids_max = 5000
        self._seen_message_ids_ttl = 60.0
        self._thinking_cards: dict[str, _CardState] = {}
        self._ai_card_available: bool = True
        self._streaming_buffers: dict[str, str] = {}
        self._streaming_last_patch: dict[str, float] = {}
        self._streaming_finalized: set[str] = set()
        self._streaming_throttle_ms: int = 800
        self._streaming_enabled: bool = True
        self._streaming_thinking: dict[str, str] = {}
        self._streaming_thinking_ms: dict[str, int] = {}
        self._streaming_chain: dict[str, list[str]] = {}
        self._typing_status: dict[str, str] = {}
        self._typing_start_time: dict[str, float] = {}
        self._footer_elapsed = footer_elapsed if footer_elapsed is not None else (
            os.environ.get("DINGTALK_FOOTER_ELAPSED", "true").lower() in ("true", "1", "yes")
        )
        self._footer_status = footer_status if footer_status is not None else (
            os.environ.get("DINGTALK_FOOTER_STATUS", "true").lower() in ("true", "1", "yes")
        )

    async def start(self) -> None:
        """启动钉钉适配器 (Stream 模式)"""
        _import_httpx()
        if not _ensure_dingtalk_runtime():
            logger.error(
                "[DingTalkAdapter] DingTalk runtime dependencies are unavailable after auto-fix; stream receiver will not start."
            )
            self._last_error = "DingTalk runtime dependencies unavailable"
            return
        _import_dingtalk_stream()

        websockets_major = _get_websockets_major_version()
        if websockets_major is not None and websockets_major >= 12:
            logger.error(
                "DingTalk Stream requires websockets < 12 for stable operation, "
                "but the current environment has websockets %s. "
                "Please reinstall with: pip install \"websockets>=11.0.2,<12\"",
                importlib.metadata.version("websockets"),
            )
            return

        self._http_client = httpx.AsyncClient()
        await self._refresh_token()

        self._running = True
        self._last_error = None

        # 记录主事件循环，用于从 Stream 线程投递协程
        try:
            self._main_loop = asyncio.get_running_loop()
        except RuntimeError:
            self._main_loop = None

        # 启动 Stream 长连接 (后台线程)
        self._start_stream()
        if self._main_loop and (self._stream_watchdog_task is None or self._stream_watchdog_task.done()):
            self._stream_watchdog_task = asyncio.create_task(self._stream_watchdog_loop())

        logger.info("DingTalk adapter started (Stream mode)")

    async def stop(self) -> None:
        """停止钉钉适配器，确保旧 Stream 连接被完全关闭。

        不关闭旧连接会导致钉钉平台在新旧连接间分发消息，
        发到旧连接上的消息因 _main_loop 已失效而被静默丢弃（与飞书同源 Bug）。
        """
        self._running = False
        self._main_loop = None
        self._set_stream_state(DingTalkStreamState.STOPPED)
        logger.info(
            "DingTalk adapter stopping: channel=%s bot_id=%s state=%s thread_alive=%s",
            self.channel_name,
            self.bot_id,
            self._stream_state.value,
            bool(self._stream_thread and self._stream_thread.is_alive()),
        )

        if self._stream_watchdog_task and not self._stream_watchdog_task.done():
            self._stream_watchdog_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._stream_watchdog_task
            self._stream_watchdog_task = None

        # 1) 停止 Stream 线程的事件循环
        stream_loop = self._stream_loop
        stream_client = self._stream_client
        if stream_client is not None:
            try:
                stream_client.open_connection = lambda: None
                logger.info("DingTalk Stream stop guard installed: open_connection disabled")
            except Exception as exc:
                logger.warning("Failed to disable DingTalk Stream reconnect entry: %s", exc)

            websocket = getattr(stream_client, "websocket", None)
            if websocket is not None:
                try:
                    close_result = websocket.close()
                    if asyncio.iscoroutine(close_result):
                        current_loop = None
                        with contextlib.suppress(RuntimeError):
                            current_loop = asyncio.get_running_loop()
                        if stream_loop is not None and stream_loop.is_running():
                            if current_loop is stream_loop:
                                await close_result
                            else:
                                future = asyncio.run_coroutine_threadsafe(close_result, stream_loop)
                                future.result(timeout=5)
                        else:
                            await close_result
                    logger.info("DingTalk Stream websocket close requested")
                except Exception as exc:
                    logger.warning("Failed to close DingTalk Stream websocket cleanly: %s", exc)

        if stream_loop is not None:
            try:
                stream_loop.call_soon_threadsafe(stream_loop.stop)
            except Exception:
                pass

        # 2) 等待 Stream 线程退出
        stream_thread = self._stream_thread
        if stream_thread is not None and stream_thread.is_alive():
            stream_thread.join(timeout=5)
            if stream_thread.is_alive():
                logger.warning("DingTalk Stream thread did not exit within 5s timeout")

        self._stream_client = None
        self._stream_thread = None
        self._stream_loop = None

        if self._http_client:
            await self._http_client.aclose()

        logger.info(
            "DingTalk adapter stopped (msgs=%s reconnects=%s dedup_hits=%s)",
            self._stream_metrics.messages_received,
            self._stream_metrics.reconnect_count,
            self._stream_metrics.dedupe_hit_count,
        )

    # ==================== Stream 模式 ====================

    def supports_streaming(self) -> bool:
        return True

    def _set_stream_state(self, state: DingTalkStreamState) -> None:
        if self._stream_state != state:
            logger.info("DingTalk Stream state: %s -> %s", self._stream_state.value, state.value)
            self._stream_state = state

    def _make_session_key(self, chat_id: str, thread_id: str | None = None) -> str:
        return f"{chat_id}:{thread_id or ''}"

    def _start_stream(self) -> None:
        """在后台线程中启动 Stream 长连接"""
        adapter = self

        class _ChatbotHandler(dingtalk_stream.ChatbotHandler):
            """自定义机器人消息处理器"""

            def __init__(self):
                # 官方 SDK 推荐的 init 模式：跳过 ChatbotHandler.__init__
                super(dingtalk_stream.ChatbotHandler, self).__init__()
                self.adapter = adapter

            async def process(self, callback: dingtalk_stream.CallbackMessage):
                """ACK 先返回，消息异步处理，避免钉钉重投。"""
                asyncio.get_running_loop().create_task(self._safe_handle(callback))
                return dingtalk_stream.AckMessage.STATUS_OK, "OK"

            async def _safe_handle(self, callback: dingtalk_stream.CallbackMessage):
                try:
                    await self.adapter._handle_stream_message(callback)
                except Exception as e:
                    logger.error(f"Error handling DingTalk message: {e}", exc_info=True)

        def _run_stream_in_thread() -> None:
            """在独立线程中运行 Stream 客户端"""
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
            self._stream_loop = new_loop
            self._set_stream_state(DingTalkStreamState.CONNECTING)

            try:
                # Monkey-patch dingtalk_stream 内部 logger，修复第三方库 bug：
                # SDK 内部调用 self.logger.exception('msg', exc) 传了额外位置参数，
                # 导致 "not all arguments converted during string formatting" TypeError。
                # 用安全的 wrapper 替换，避免触发该 bug。
                _ds_logger = logging.getLogger("dingtalk_stream")
                _orig_exception = _ds_logger.exception

                def _safe_exception(msg, *args, **kwargs):
                    # 如果第一个额外参数是 Exception，转为 exc_info 方式记录
                    if args and isinstance(args[0], BaseException):
                        _orig_exception("%s: %s", msg, args[0], **{k: v for k, v in kwargs.items() if k != "exc_info"}, exc_info=True)
                    else:
                        try:
                            _orig_exception(msg, *args, **kwargs)
                        except TypeError:
                            _orig_exception("%s", msg, exc_info=True)

                _ds_logger.exception = _safe_exception
                _ds_logger._openclaw_safe_exception_patched = True

                _ds_client_logger = logging.getLogger("dingtalk_stream.client")
                if not getattr(_ds_client_logger, "_openclaw_safe_exception_patched", False):
                    _orig_client_exception = _ds_client_logger.exception

                    def _safe_client_exception(msg, *args, **kwargs):
                        if args and isinstance(args[0], BaseException):
                            safe_kwargs = {k: v for k, v in kwargs.items() if k != "exc_info"}
                            _orig_client_exception("%s: %s", msg, args[0], **safe_kwargs, exc_info=True)
                        else:
                            try:
                                _orig_client_exception(msg, *args, **kwargs)
                            except TypeError:
                                _orig_client_exception("%s", msg, exc_info=True)

                    _ds_client_logger.exception = _safe_client_exception
                    _ds_client_logger._openclaw_safe_exception_patched = True

                credential = dingtalk_stream.Credential(
                    self.config.app_key, self.config.app_secret
                )
                client = dingtalk_stream.DingTalkStreamClient(credential)
                client.register_callback_handler(
                    dingtalk_stream.chatbot.ChatbotMessage.TOPIC,
                    _ChatbotHandler(),
                )
                self._stream_client = client
                logger.info("DingTalk Stream client starting...")
                logger.info(f"DingTalk AppKey configured: {self.config.app_key[:6]}***")
                self._stream_metrics.connected_since = time.time()
                self._set_stream_state(DingTalkStreamState.RUNNING)
                logger.info(
                    "DingTalk Stream event loop ready: thread=%s loop_id=%s",
                    threading.current_thread().name,
                    id(new_loop),
                )
                new_loop.run_until_complete(client.start())
            except Exception as e:
                if self._running:
                    self._last_error = str(e)
                    logger.error(f"DingTalk Stream error: {e}", exc_info=True)
            finally:
                logger.info(
                    "DingTalk Stream thread exiting: channel=%s state=%s last_error=%s",
                    self.channel_name,
                    self._stream_state.value,
                    self._last_error,
                )
                self._stream_loop = None
                new_loop.close()

        self._stream_thread = threading.Thread(
            target=_run_stream_in_thread,
            daemon=True,
            name="DingTalkStream",
        )
        self._stream_thread.start()
        logger.info("DingTalk Stream client started in background thread")

    async def _stream_watchdog_loop(self) -> None:
        await asyncio.sleep(self._STREAM_WATCHDOG_INITIAL_DELAY)
        last_restart_time = 0.0
        stable_since = asyncio.get_running_loop().time()

        while self._running:
            await asyncio.sleep(self._STREAM_WATCHDOG_INTERVAL)
            if not self._running:
                break

            stream_thread = self._stream_thread
            if stream_thread is not None and stream_thread.is_alive():
                now = asyncio.get_running_loop().time()
                if self._stream_restart_count > 0 and (now - stable_since) >= self._STREAM_STABLE_THRESHOLD:
                    self._stream_restart_count = 0
                    self._set_stream_state(DingTalkStreamState.RUNNING)
                continue

            self._set_stream_state(DingTalkStreamState.RECONNECTING)
            now = asyncio.get_running_loop().time()
            if now - last_restart_time < self._STREAM_RECONNECT_MIN_INTERVAL:
                continue

            self._stream_restart_count += 1
            self._stream_metrics.reconnect_count += 1
            self._stream_metrics.last_reconnect_at = time.time()
            backoff = min(
                self._STREAM_RECONNECT_MIN_INTERVAL * (2 ** min(self._stream_restart_count - 1, 6)),
                self._STREAM_RECONNECT_MAX_DELAY,
            )
            logger.warning(
                "DingTalk Stream watchdog: thread exited (restart #%s), reconnect in %ss",
                self._stream_restart_count,
                int(backoff),
            )
            await asyncio.sleep(backoff)
            if not self._running:
                break
            try:
                self._start_stream()
                last_restart_time = asyncio.get_running_loop().time()
                stable_since = last_restart_time
                logger.info(
                    "DingTalk Stream watchdog restarted connection: restart_count=%s reconnect_total=%s",
                    self._stream_restart_count,
                    self._stream_metrics.reconnect_count,
                )
            except Exception as exc:
                self._last_error = str(exc)
                logger.error(f"DingTalk Stream watchdog reconnect failed: {exc}", exc_info=True)

    async def _handle_stream_message(
        self, callback: "dingtalk_stream.CallbackMessage"
    ) -> None:
        """
        处理 Stream 模式收到的消息

        SDK 的 ChatbotMessage.from_dict() 仅解析 text/picture/richText，
        """
        raw_data = callback.data
        logger.info(f"[DingTalkAdapter] Received raw message callback: {raw_data}")

        if not raw_data:
            return

        # 解析基础字段
        msg_type = raw_data.get("msgtype", "text")
        sender_id = raw_data.get("senderStaffId") or raw_data.get("senderId", "")
        conversation_id = raw_data.get("conversationId", "")
        conversation_type = raw_data.get("conversationType", "1")
        msg_id = raw_data.get("msgId", "")

        create_at_ms = raw_data.get("createAt")
        if create_at_ms and isinstance(create_at_ms, (int, float)):
            age_s = time.time() - create_at_ms / 1000
            if age_s > self.STALE_MESSAGE_THRESHOLD_S:
                logger.info("DingTalk: stale message discarded age=%ss msg_id=%s", int(age_s), msg_id)
                return

        if msg_id:
            dedup_key = f"{self.bot_id}:{msg_id}"
            now = time.time()
            if dedup_key in self._seen_message_ids:
                self._stream_metrics.dedupe_hit_count += 1
                logger.debug(f"DingTalk: duplicate message ignored: {msg_id}")
                return
            if len(self._seen_message_ids) > self._seen_message_ids_max // 2:
                expired = [key for key, ts in self._seen_message_ids.items() if now - ts > self._seen_message_ids_ttl]
                for key in expired:
                    self._seen_message_ids.pop(key, None)
            if len(self._seen_message_ids) >= self._seen_message_ids_max:
                oldest = min(self._seen_message_ids, key=self._seen_message_ids.get)
                self._seen_message_ids.pop(oldest, None)
            self._seen_message_ids[dedup_key] = now

        self._stream_metrics.messages_received += 1
        self._stream_metrics.last_message_at = time.time()

        chat_type = "group" if conversation_type == "2" else "private"

        # 保存 session webhook 用于回复
        session_webhook = raw_data.get("sessionWebhook", "")
        if session_webhook and conversation_id:
            self._session_webhooks[conversation_id] = session_webhook
        if sender_id and conversation_id:
            self._conversation_users[conversation_id] = sender_id
        if conversation_id and conversation_type:
            self._conversation_types[conversation_id] = conversation_type
        metadata = {
            "session_webhook": session_webhook,
            "conversation_type": conversation_type,
            "is_group": chat_type == "group",
            "sender_name": raw_data.get("senderNick", ""),
            "chat_name": raw_data.get("conversationTitle", ""),
        }

        # 根据消息类型构建 content
        content = await self._parse_message_content(msg_type, raw_data)

        is_direct_message = conversation_type == "1"

        # 检测 @机器人：钉钉 isInAtList 字段，或检查 atUsers 列表
        is_mentioned = False
        if raw_data.get("isInAtList") is True:
            is_mentioned = True
        elif not is_mentioned:
            at_users = raw_data.get("atUsers") or []
            robot_code = self.config.app_key
            for at_user in at_users:
                if at_user.get("dingtalkId") == robot_code:
                    is_mentioned = True
                    break

        unified = UnifiedMessage.create(
            channel=self.channel_name,
            channel_message_id=msg_id,
            user_id=f"dd_{sender_id}",
            channel_user_id=sender_id,
            chat_id=conversation_id,
            content=content,
            chat_type=chat_type,
            is_mentioned=is_mentioned,
            is_direct_message=is_direct_message,
            raw=raw_data,
            metadata=metadata,
        )

        self._log_message(unified)

        self._log_message(unified)

        # 从 Stream 线程投递到主事件循环。
        # 必须使用 run_coroutine_threadsafe：当前线程已有运行中的事件循环（SDK 的 stream loop），
        # 不能使用 asyncio.run()，否则会触发 RuntimeError 导致消息丢失。
        if self._main_loop is not None and self._running and not self._main_loop.is_closed():
            logger.info(f"[DingTalkAdapter] Dispatching message {msg_id} to main loop")
            future = asyncio.run_coroutine_threadsafe(
                self._emit_message(unified), self._main_loop
            )
            def _on_emit_done(f: "asyncio.futures.Future") -> None:
                try:
                    f.result()
                except Exception as e:
                    logger.error(
                        f"Failed to dispatch DingTalk message to main loop: {e}",
                        exc_info=True,
                    )
            future.add_done_callback(_on_emit_done)
        else:
            logger.warning("DingTalk: dropping message (adapter stopping or main loop unavailable)")

    async def _parse_message_content(
        self, msg_type: str, raw_data: dict
    ) -> MessageContent:
        """根据消息类型解析内容"""

        if msg_type == "text":
            text_body = raw_data.get("text", {})
            text = text_body.get("content", "").strip()
            return MessageContent(text=text)

        elif msg_type == "picture":
            # 图片消息：content 可能是 dict 或 JSON 字符串
            content_raw = raw_data.get("content", {})
            if isinstance(content_raw, str):
                try:
                    content_raw = json.loads(content_raw)
                except (json.JSONDecodeError, TypeError):
                    content_raw = {}

            # 字段名: SDK 使用 downloadCode，部分版本可能用 pictureDownloadCode
            download_code = (
                content_raw.get("downloadCode", "")
                or content_raw.get("pictureDownloadCode", "")
            )

            if not download_code:
                # 兜底：尝试从 SDK ChatbotMessage 解析
                try:
                    incoming = dingtalk_stream.ChatbotMessage.from_dict(raw_data)
                    if hasattr(incoming, "image_content") and incoming.image_content:
                        download_code = getattr(
                            incoming.image_content, "download_code", ""
                        ) or ""
                except Exception as e:
                    logger.warning(f"DingTalk: failed to parse picture via SDK: {e}")

            if not download_code:
                logger.warning("DingTalk: picture message has no downloadCode")
                return MessageContent(text="[图片: 无法获取下载码]")

            media = MediaFile.create(
                filename=f"dingtalk_image_{download_code[:8]}.jpg",
                mime_type="image/jpeg",
                file_id=download_code,
            )
            return MessageContent(images=[media])

        elif msg_type == "richText":
            # 富文本消息：提取文本和图片
            content_raw = raw_data.get("content", {})
            if isinstance(content_raw, str):
                try:
                    content_raw = json.loads(content_raw)
                except (json.JSONDecodeError, TypeError):
                    content_raw = {}
            rich_text = content_raw.get("richText", [])
            text_parts = []
            images = []

            for section in rich_text:
                if "text" in section:
                    text_parts.append(section["text"])
                # 兼容两种字段名
                code = section.get("downloadCode") or section.get("pictureDownloadCode")
                if code:
                    media = MediaFile.create(
                        filename=f"dingtalk_richimg_{code[:8]}.jpg",
                        mime_type="image/jpeg",
                        file_id=code,
                    )
                    images.append(media)

            return MessageContent(
                text="\n".join(text_parts) if text_parts else None,
                images=images,
            )

        elif msg_type == "audio":
            # 语音消息 - SDK 不解析，从 raw_data 手动提取
            audio_content = raw_data.get("content", {})
            if isinstance(audio_content, str):
                try:
                    audio_content = json.loads(audio_content)
                except (json.JSONDecodeError, TypeError):
                    audio_content = {}
            download_code = audio_content.get("downloadCode", "")
            duration = audio_content.get("duration", 0)

            media = MediaFile.create(
                filename=f"dingtalk_voice_{download_code[:8]}.ogg",
                mime_type="audio/ogg",
                file_id=download_code,
            )
            media.duration = float(duration) / 1000.0 if duration else None
            return MessageContent(voices=[media])

        elif msg_type == "video":
            # 视频消息 - SDK 不解析
            video_content = raw_data.get("content", {})
            if isinstance(video_content, str):
                try:
                    video_content = json.loads(video_content)
                except (json.JSONDecodeError, TypeError):
                    video_content = {}
            download_code = video_content.get("downloadCode", "")
            duration = video_content.get("duration", 0)

            media = MediaFile.create(
                filename=f"dingtalk_video_{download_code[:8]}.mp4",
                mime_type="video/mp4",
                file_id=download_code,
            )
            media.duration = float(duration) / 1000.0 if duration else None
            return MessageContent(videos=[media])

        elif msg_type == "file":
            # 文件消息 - SDK 不解析
            file_content = raw_data.get("content", {})
            if isinstance(file_content, str):
                try:
                    file_content = json.loads(file_content)
                except (json.JSONDecodeError, TypeError):
                    file_content = {}
            download_code = file_content.get("downloadCode", "")
            file_name = file_content.get("fileName", "unknown_file")

            media = MediaFile.create(
                filename=file_name,
                mime_type="application/octet-stream",
                file_id=download_code,
            )
            return MessageContent(files=[media])

        else:
            # 未知消息类型，尝试提取文本
            logger.warning(f"Unknown DingTalk message type: {msg_type}")
            return MessageContent(text=f"[不支持的消息类型: {msg_type}]")

    # ==================== 消息发送 ====================

    def _is_group_chat(self, chat_id: str) -> bool:
        """判断 chat_id 是否为群聊会话"""
        # 优先使用缓存的 conversationType（来自接收消息时的回调数据）
        # "1" = 单聊, "2" = 群聊
        cached_type = self._conversation_types.get(chat_id)
        if cached_type is not None:
            return cached_type == "2"
        # 没有缓存时保守地认为是单聊（避免误调群聊API导致 robot 不存在）
        logger.warning(
            f"No cached conversationType for {chat_id[:20]}..., defaulting to private chat"
        )
        return False

    async def send_typing(self, chat_id: str, thread_id: str | None = None) -> None:
        sk = self._make_session_key(chat_id, thread_id)
        if sk in self._thinking_cards:
            return
        try:
            card_state = await self._create_card(chat_id)
            self._thinking_cards[sk] = card_state
            self._typing_start_time[sk] = time.time()
            self._typing_status[sk] = "思考中"
        except Exception as exc:
            logger.debug(f"DingTalk: send_typing card failed: {exc}")

    async def stream_token(
        self,
        chat_id: str,
        token: str,
        *,
        thread_id: str | None = None,
        is_group: bool = False,
    ) -> None:
        sk = self._make_session_key(chat_id, thread_id)
        card_state = self._thinking_cards.get(sk)
        if not card_state:
            return

        self._streaming_buffers[sk] = self._streaming_buffers.get(sk, "") + token
        self._typing_status[sk] = "生成回复"
        now = time.time() * 1000
        last = self._streaming_last_patch.get(sk, 0)
        if now - last < self._streaming_throttle_ms:
            return
        self._streaming_last_patch[sk] = now
        display = self._compose_thinking_display(sk)
        footer = self._build_footer_note(sk)
        await self._patch_card_content(card_state, display + footer)

    async def stream_thinking(
        self,
        chat_id: str,
        thinking_text: str,
        *,
        thread_id: str | None = None,
        is_group: bool = False,
        duration_ms: int = 0,
    ) -> None:
        sk = self._make_session_key(chat_id, thread_id)
        card_state = self._thinking_cards.get(sk)
        if not card_state:
            return
        self._streaming_thinking[sk] = thinking_text
        if duration_ms:
            self._streaming_thinking_ms[sk] = duration_ms
        self._typing_status[sk] = "深度思考"
        now = time.time() * 1000
        last = self._streaming_last_patch.get(sk, 0)
        if now - last < self._streaming_throttle_ms:
            return
        self._streaming_last_patch[sk] = now
        display = self._compose_thinking_display(sk)
        footer = self._build_footer_note(sk)
        await self._patch_card_content(card_state, display + footer)

    async def stream_chain_text(
        self,
        chat_id: str,
        text: str,
        *,
        thread_id: str | None = None,
        is_group: bool = False,
    ) -> None:
        sk = self._make_session_key(chat_id, thread_id)
        card_state = self._thinking_cards.get(sk)
        if not card_state:
            return
        chain = self._streaming_chain.setdefault(sk, [])
        chain.append(text)
        self._typing_status[sk] = "调用工具"
        now = time.time() * 1000
        last = self._streaming_last_patch.get(sk, 0)
        if now - last < self._streaming_throttle_ms:
            return
        self._streaming_last_patch[sk] = now
        display = self._compose_thinking_display(sk)
        footer = self._build_footer_note(sk)
        await self._patch_card_content(card_state, display + footer)

    async def finalize_stream(
        self,
        chat_id: str,
        final_text: str,
        *,
        thread_id: str | None = None,
    ) -> bool:
        sk = self._make_session_key(chat_id, thread_id)
        card_state = self._thinking_cards.pop(sk, None)
        footer = self._build_footer_note(sk, final=True)

        self._streaming_buffers.pop(sk, None)
        self._streaming_last_patch.pop(sk, None)
        self._streaming_thinking.pop(sk, None)
        self._streaming_thinking_ms.pop(sk, None)
        self._streaming_chain.pop(sk, None)
        self._typing_status.pop(sk, None)
        self._typing_start_time.pop(sk, None)

        if not card_state:
            return False
        try:
            content = final_text + footer
            if card_state.is_ai_card:
                await self._stream_ai_card(card_state.card_id, content, finished=True)
            else:
                await self._update_interactive_card(card_state.card_id, content)
            self._streaming_finalized.add(sk)
            return True
        except Exception as exc:
            logger.warning(f"DingTalk: finalize_stream failed: {exc}")
            return False

    async def clear_typing(self, chat_id: str, thread_id: str | None = None) -> None:
        sk = self._make_session_key(chat_id, thread_id)
        card_state = self._thinking_cards.pop(sk, None)
        self._streaming_thinking.pop(sk, None)
        self._streaming_thinking_ms.pop(sk, None)
        self._streaming_chain.pop(sk, None)
        self._typing_status.pop(sk, None)
        self._typing_start_time.pop(sk, None)
        if not card_state:
            return
        with contextlib.suppress(Exception):
            if card_state.is_ai_card:
                await self._stream_ai_card(card_state.card_id, "✅ 处理完成", finished=True)
            else:
                await self._update_interactive_card(card_state.card_id, "✅ 处理完成")

    async def _create_card(self, chat_id: str) -> _CardState:
        if self._ai_card_available:
            try:
                card_id = await self._create_ai_card(chat_id)
                if card_id:
                    return _CardState(card_id=card_id, is_ai_card=True)
            except Exception as exc:
                logger.info(f"DingTalk: AI Card unavailable, fallback to StandardCard: {exc}")
                self._ai_card_available = False
        return await self._create_standard_card(chat_id)

    async def _create_ai_card(self, chat_id: str) -> str | None:
        await self._refresh_token()
        out_track_id = f"ai_{uuid.uuid4().hex[:16]}"
        headers = {"x-acs-dingtalk-access-token": self._access_token}
        create_body = {
            "cardTemplateId": self.AI_CARD_TEMPLATE_ID,
            "outTrackId": out_track_id,
            "cardData": {
                "cardParamMap": {
                    "flowStatus": "PROCESSING",
                    "msgContent": "💭 正在思考中...",
                }
            },
        }
        create_resp = await self._http_client.post(self.AI_CARD_CREATE_URL, headers=headers, json=create_body)
        create_result = create_resp.json()
        if not create_result.get("outTrackId") and not create_result.get("success", False):
            raise RuntimeError(f"AI Card create failed: {create_result}")

        conv_type = self._conversation_types.get(chat_id, "1")
        if conv_type == "2":
            open_space_id = f"dtv1.card//IM_GROUP.{chat_id}"
        else:
            staff_id = self._conversation_users.get(chat_id)
            if not staff_id or staff_id.startswith("$:LWCP"):
                raise ValueError("No valid staffId for AI Card delivery")
            open_space_id = f"dtv1.card//IM_ROBOT.{staff_id}"

        deliver_body = {
            "outTrackId": out_track_id,
            "openSpaceId": open_space_id,
            "deliverType": "IM",
        }
        deliver_resp = await self._http_client.post(self.AI_CARD_DELIVER_URL, headers=headers, json=deliver_body)
        deliver_result = deliver_resp.json()
        if not deliver_result.get("spaceId") and not deliver_result.get("success", False):
            raise RuntimeError(f"AI Card deliver failed: {deliver_result}")
        return out_track_id

    async def _stream_ai_card(self, out_track_id: str, content: str, *, finished: bool = False) -> None:
        await self._refresh_token()
        headers = {"x-acs-dingtalk-access-token": self._access_token}
        if finished:
            body = {
                "outTrackId": out_track_id,
                "cardData": {
                    "cardParamMap": {
                        "flowStatus": "FINISHED",
                        "msgContent": content,
                    }
                },
            }
            response = await self._http_client.put(self.AI_CARD_CREATE_URL, headers=headers, json=body)
        else:
            body = {
                "outTrackId": out_track_id,
                "guid": uuid.uuid4().hex,
                "key": "msgContent",
                "content": content,
                "isFull": True,
            }
            response = await self._http_client.put(self.AI_CARD_STREAM_URL, headers=headers, json=body)
        result = response.json()
        if not result.get("success", True):
            raise RuntimeError(str(result))

    async def _create_standard_card(self, chat_id: str) -> _CardState:
        card_biz_id = f"thinking_{uuid.uuid4().hex[:16]}"
        await self._send_interactive_card(chat_id, card_biz_id, "💭 **正在思考中...**")
        return _CardState(card_id=card_biz_id, is_ai_card=False)

    async def _send_interactive_card(self, chat_id: str, card_biz_id: str, content: str) -> None:
        await self._refresh_token()
        card_data = json.dumps({
            "config": {"autoLayout": True, "enableForward": False},
            "header": {"title": {"type": "text", "text": ""}},
            "contents": [{"type": "markdown", "text": content, "id": "content_main"}],
        })
        body: dict[str, Any] = {
            "cardTemplateId": "StandardCard",
            "cardBizId": card_biz_id,
            "robotCode": self.config.app_key,
            "cardData": card_data,
            "pullStrategy": False,
        }
        conv_type = self._conversation_types.get(chat_id, "1")
        if conv_type == "2":
            body["openConversationId"] = chat_id
        else:
            staff_id = self._conversation_users.get(chat_id)
            if not staff_id or staff_id.startswith("$:LWCP"):
                raise ValueError("No valid staffId for single chat card")
            body["singleChatReceiver"] = json.dumps({"userId": staff_id})

        headers = {"x-acs-dingtalk-access-token": self._access_token}
        response = await self._http_client.post(self.CARD_SEND_URL, headers=headers, json=body)
        result = response.json()
        if "processQueryKey" not in result:
            raise RuntimeError(f"Card send failed: {result}")

    async def _update_interactive_card(self, card_biz_id: str, content: str) -> None:
        await self._refresh_token()
        card_data = json.dumps({
            "config": {"autoLayout": True, "enableForward": True},
            "header": {"title": {"type": "text", "text": ""}},
            "contents": [{"type": "markdown", "text": content, "id": "content_main"}],
        })
        body = {"cardBizId": card_biz_id, "cardData": card_data}
        headers = {"x-acs-dingtalk-access-token": self._access_token}
        response = await self._http_client.put(self.CARD_UPDATE_URL, headers=headers, json=body)
        result = response.json()
        if "processQueryKey" not in result:
            raise RuntimeError(f"Card update failed: {result}")

    def _compose_thinking_display(self, sk: str) -> str:
        thinking = self._streaming_thinking.get(sk, "")
        reply = self._streaming_buffers.get(sk, "")
        dur_ms = self._streaming_thinking_ms.get(sk, 0)
        chain_lines = self._streaming_chain.get(sk, [])

        parts: list[str] = []
        if thinking:
            dur_str = f" ({dur_ms / 1000:.1f}s)" if dur_ms else ""
            preview = thinking.strip()
            if len(preview) > 600:
                preview = preview[:600] + "..."
            parts.append(f"💭 **思考过程**{dur_str}\n> {preview.replace(chr(10), chr(10) + '> ')}")
        if chain_lines:
            parts.append("\n".join(chain_lines[-8:]))
        if reply:
            if parts:
                parts.append("---")
            parts.append(reply + " ▍")
        elif not thinking and not chain_lines:
            parts.append("💭 思考中...")
        return "\n".join(parts)

    def _build_footer_note(self, sk: str, *, final: bool = False) -> str:
        if not self._footer_elapsed and not self._footer_status:
            return ""

        start = self._typing_start_time.get(sk)
        elapsed_s = (time.time() - start) if start else 0.0
        status = self._typing_status.get(sk, "")
        parts: list[str] = []
        if final:
            if self._footer_elapsed:
                parts.append(f"⏱ 完成 ({elapsed_s:.1f}s)")
            elif self._footer_status:
                parts.append("✅ 完成")
        else:
            if self._footer_elapsed and elapsed_s > 0:
                parts.append(f"⏱ {elapsed_s:.1f}s")
            if self._footer_status and status:
                parts.append(status)
        if not parts:
            return ""
        return "\n\n<font color=gray>" + " · ".join(parts) + "</font>"

    async def _patch_card_content(
        self,
        card_state: _CardState,
        text: str,
        sk: str | None = None,
        *,
        final: bool = False,
    ) -> bool:
        if not card_state or not card_state.card_id:
            return False
        try:
            if card_state.is_ai_card:
                await self._stream_ai_card(card_state.card_id, text, finished=final)
            else:
                await self._update_interactive_card(card_state.card_id, text)
            return True
        except Exception as exc:
            logger.debug(f"DingTalk: _patch_card_content failed: {exc}")
            return False

    async def send_message(self, message: OutgoingMessage) -> str:
        """
        发送消息 - 智能路由

        路由策略：
        - 所有消息 → 优先 SessionWebhook
          - 纯文本 → text 类型
          - Markdown → markdown 类型
          - 媒体 → 转为 markdown 内嵌 (图片: ![img](@lAL...))
        - Webhook 不可用时 → 回退 OpenAPI
        - OpenAPI 失败时 → 降级为文本

        核心约束: 钉钉 Webhook 只支持 text/markdown/actionCard/feedCard，
        不支持 image/file/voice 原生类型。所有图片必须通过 markdown 嵌入。
        """
        sk = self._make_session_key(message.chat_id, message.thread_id)
        if sk in self._streaming_finalized:
            self._streaming_finalized.discard(sk)
            logger.debug(f"DingTalk: send_message skipped after finalize_stream: {sk}")
            return f"stream_finalized_{sk}"

        self._streaming_thinking.pop(sk, None)
        self._streaming_thinking_ms.pop(sk, None)
        self._streaming_chain.pop(sk, None)
        self._typing_status.pop(sk, None)

        # 解析文本中的本地路径图片并上传 (钉钉不支持直接发本地路径，且公网不可见)
        if message.content.text:
            message.content.text = await self._resolve_local_images(message.content.text)

        card_state = None if sk in self._streaming_buffers else self._thinking_cards.pop(sk, None)
        if card_state and message.content.text and not message.content.has_media:
            try:
                final_text = message.content.text + self._build_footer_note(sk, final=True)
                if card_state.is_ai_card:
                    await self._stream_ai_card(card_state.card_id, final_text, finished=True)
                else:
                    await self._update_interactive_card(card_state.card_id, final_text)
                self._streaming_buffers.pop(sk, None)
                self._streaming_last_patch.pop(sk, None)
                self._typing_start_time.pop(sk, None)
                return f"card_{card_state.card_id}"
            except Exception as exc:
                logger.warning(f"DingTalk: update thinking card failed, fallback to normal send: {exc}")

        # 获取 webhook
        session_webhook = message.metadata.get("session_webhook", "")
        if not session_webhook:
            session_webhook = self._session_webhooks.get(message.chat_id, "")

        # 媒体消息：转为 markdown 通过 webhook 发送
        has_media = (
            message.content.images
            or message.content.files
            or message.content.voices
        )

        if has_media and session_webhook:
            md_parts = []
            text_part = message.content.text or ""
            if text_part:
                md_parts.append(text_part)

            # 图片 → 上传获取 media_id，嵌入 markdown
            for img in message.content.images or []:
                mid = img.file_id
                if not mid and img.local_path:
                    try:
                        uploaded = await self.upload_media(
                            Path(img.local_path), img.mime_type or "image/png"
                        )
                        mid = uploaded.file_id
                    except Exception as e:
                        logger.warning(f"Image upload failed: {e}")
                if mid:
                    md_parts.append(f"![image]({mid})")
                else:
                    md_parts.append(f"📎 图片: {img.filename}")

            # 文件 → 只能发文件名
            for f in message.content.files or []:
                md_parts.append(f"📎 文件: {f.filename}")

            # 语音 → 只能发提示
            for v in message.content.voices or []:
                md_parts.append(f"🎤 语音: {v.filename}")

            md_text = "\n\n".join(md_parts)
            payload = {
                "msgtype": "markdown",
                "markdown": {
                    "title": md_text[:20] if md_text else "消息",
                    "text": md_text,
                },
            }
            try:
                response = await self._http_client.post(session_webhook, json=payload)
                result = response.json()
                if result.get("errcode", 0) == 0:
                    logger.info("Sent media via webhook markdown")
                    return f"webhook_{int(time.time())}"
                else:
                    logger.warning(f"Webhook media failed: {result.get('errmsg')}")
            except Exception as e:
                logger.warning(f"Webhook media error: {e}")

            # 降级为纯文本
            fallback_text = message.content.text or "[媒体消息]"
            fallback = OutgoingMessage.text(message.chat_id, fallback_text)
            if session_webhook:
                return await self._send_via_webhook(fallback, session_webhook)

        # 纯文本消息：优先走 Webhook（更快）
        if session_webhook:
            return await self._send_via_webhook(message, session_webhook)

        # 回退到 OpenAPI（文本消息）
        await self._refresh_token()
        is_group = message.metadata.get(
            "is_group", self._is_group_chat(message.chat_id)
        )
        try:
            if is_group:
                result_id = await self._send_group_message(message)
            else:
                result_id = await self._send_via_api(message)
        except RuntimeError as e:
            logger.error(f"OpenAPI send failed: {e}")
            raise

        for extra_img in (message.content.images or [])[1:]:
            if extra_img.local_path:
                with contextlib.suppress(Exception):
                    await self.send_image(message.chat_id, extra_img.local_path)
        for extra_file in (message.content.files or [])[1:]:
            if extra_file.local_path:
                with contextlib.suppress(Exception):
                    await self.send_file(message.chat_id, extra_file.local_path)
        self._streaming_buffers.pop(sk, None)
        self._streaming_last_patch.pop(sk, None)
        self._typing_start_time.pop(sk, None)
        return result_id

    async def _build_msg_key_param(
        self, message: OutgoingMessage
    ) -> tuple[str, dict]:
        """
        从 OutgoingMessage 构建钉钉消息类型参数

        Returns:
            (msgKey, msgParam) 元组

        消息类型参考: https://open.dingtalk.com/document/development/robot-message-type
        - sampleText:     {"content": "..."}
        - sampleMarkdown: {"title": "...", "text": "..."}
        - sampleImageMsg: {"photoURL": "..."}
        - sampleFile:     {"mediaId": "@...", "fileName": "...", "fileType": "..."}
        - sampleAudio:    {"mediaId": "@...", "duration": "3000"}
        """
        # 图片消息
        if message.content.images:
            image = message.content.images[0]
            photo_url = image.url  # 优先用已有的 URL
            media_id = image.file_id

            if not photo_url and image.local_path:
                try:
                    uploaded = await self.upload_media(
                        Path(image.local_path), image.mime_type or "image/png"
                    )
                    photo_url = uploaded.url  # 临时 URL（仅图片上传返回）
                    media_id = uploaded.file_id
                except Exception as e:
                    logger.error(f"Failed to upload image: {e}")

            # sampleImageMsg 需要 photoURL（可以是 URL 或 @mediaId）
            if photo_url:
                return "sampleImageMsg", {"photoURL": photo_url}
            elif media_id:
                return "sampleImageMsg", {"photoURL": media_id}
            return "sampleText", {"content": message.content.text or "[图片发送失败]"}

        # 文件消息
        if message.content.files:
            file = message.content.files[0]
            media_id = file.file_id

            if not media_id and file.local_path:
                try:
                    uploaded = await self.upload_media(
                        Path(file.local_path),
                        file.mime_type or "application/octet-stream",
                    )
                    media_id = uploaded.file_id
                except Exception as e:
                    logger.error(f"Failed to upload file: {e}")

            if media_id:
                ext = Path(file.filename).suffix.lstrip(".") or "file"
                return "sampleFile", {
                    "mediaId": media_id,
                    "fileName": file.filename,
                    "fileType": ext,
                }
            return "sampleText", {
                "content": message.content.text or f"[文件: {file.filename}]"
            }

        # 语音消息
        if message.content.voices:
            voice = message.content.voices[0]
            media_id = voice.file_id

            if not media_id and voice.local_path:
                try:
                    uploaded = await self.upload_media(
                        Path(voice.local_path), voice.mime_type or "audio/ogg"
                    )
                    media_id = uploaded.file_id
                except Exception as e:
                    logger.error(f"Failed to upload voice: {e}")

            if media_id:
                duration_ms = str(int((voice.duration or 3) * 1000))
                return "sampleAudio", {"mediaId": media_id, "duration": duration_ms}
            return "sampleText", {"content": "[语音发送失败]"}

        # 纯文本 / Markdown
        text = message.content.text or ""
        if message.parse_mode == "markdown" or contains_markdown(text):
            return "sampleMarkdown", {"title": text[:20], "text": text}
        return "sampleText", {"content": text}

    async def _send_via_webhook(
        self, message: OutgoingMessage, webhook_url: str
    ) -> str:
        """
        通过 SessionWebhook 发送消息

        仅支持 text 和 markdown 类型，不支持图片/文件/语音。
        参考: https://open.dingtalk.com/document/robots/custom-robot-access/
        """
        text = message.content.text or ""

        is_markdown = message.parse_mode == "markdown" or contains_markdown(text)
        chunks = self._chunk_markdown_text(text, self._MARKDOWN_MAX_LENGTH) if text else [text]
        result_id = ""
        for chunk in chunks:
            if is_markdown:
                payload = {
                    "msgtype": "markdown",
                    "markdown": {
                        "title": chunk[:20] if chunk else "消息",
                        "text": chunk,
                    },
                }
            else:
                payload = {
                    "msgtype": "text",
                    "text": {"content": chunk},
                }

            response = await self._http_client.post(webhook_url, json=payload)
            result = response.json()

            if result.get("errcode", 0) != 0:
                error_msg = result.get("errmsg", "Unknown error")
                logger.error(f"DingTalk webhook send failed: {error_msg}")
                raise RuntimeError(f"Failed to send via webhook: {error_msg}")
            result_id = f"webhook_{int(time.time())}"

        return result_id

    def _chunk_markdown_text(self, text: str, max_length: int) -> list[str]:
        if len(text) <= max_length:
            return [text]
        chunks: list[str] = []
        remaining = text
        while remaining:
            if len(remaining) <= max_length:
                chunks.append(remaining)
                break
            cut = remaining.rfind("\n\n", 0, max_length)
            if cut <= 0:
                cut = remaining.rfind("\n", 0, max_length)
            if cut <= 0:
                cut = max_length
            chunks.append(remaining[:cut].rstrip())
            remaining = remaining[cut:].lstrip()
        return chunks

    async def _send_group_message(self, message: OutgoingMessage) -> str:
        """
        通过 OpenAPI 发送群聊消息

        API: POST /v1.0/robot/groupMessages/send
        参考: https://open.dingtalk.com/document/group/the-robot-sends-a-group-message
        """
        url = f"{self.API_NEW}/robot/groupMessages/send"
        headers = {"x-acs-dingtalk-access-token": self._access_token}

        msg_key, msg_param = await self._build_msg_key_param(message)

        data = {
            "robotCode": self.config.app_key,
            "openConversationId": message.chat_id,
            "msgKey": msg_key,
            "msgParam": json.dumps(msg_param),
        }

        logger.info(f"Sending group message: msgKey={msg_key}, chat={message.chat_id[:20]}...")

        response = await self._http_client.post(url, headers=headers, json=data)
        result = response.json()

        if "processQueryKey" not in result:
            error = result.get("message", result.get("errmsg", "Unknown error"))
            logger.error(f"Failed to send group message: {error}, data={data}")
            raise RuntimeError(f"Failed to send group message: {error}")

        return result["processQueryKey"]

    async def _send_via_api(self, message: OutgoingMessage) -> str:
        """
        通过 OpenAPI 发送单聊消息

        API: POST /v1.0/robot/oToMessages/batchSend
        """
        url = f"{self.API_NEW}/robot/oToMessages/batchSend"
        headers = {"x-acs-dingtalk-access-token": self._access_token}

        msg_key, msg_param = await self._build_msg_key_param(message)

        # 优先使用缓存的 userId（chat_id 可能是 conversationId，不能直接当 userId 用）
        user_id = self._conversation_users.get(message.chat_id, message.chat_id)

        data = {
            "robotCode": self.config.app_key,
            "userIds": [user_id],
            "msgKey": msg_key,
            "msgParam": json.dumps(msg_param),
        }

        logger.info(f"Sending 1-on-1 message: msgKey={msg_key}, user={user_id[:12]}...")

        response = await self._http_client.post(url, headers=headers, json=data)
        result = response.json()

        if "processQueryKey" not in result:
            error = result.get("message", "Unknown error")
            raise RuntimeError(f"Failed to send message: {error}")

        return result["processQueryKey"]

    async def send_image(
        self,
        chat_id: str,
        image_path: str,
        caption: str | None = None,
        reply_to: str | None = None,
        **kwargs,
    ) -> str:
        """
        发送图片消息 - 钉钉定制实现

        策略 (按优先级):
        1. 上传图片获取 media_id
        2. 通过 SessionWebhook + Markdown 嵌入图片
           - 优先使用 upload 返回的 URL（如有）
           - 否则用 media_id（@lAL...格式，钉钉内部可渲染）
        3. 尝试旧版 API 工作通知（仅单聊，使用 media_id）
        4. 降级为文本

        参考: https://open.dingtalk.com/document/robots/custom-robot-access/
        """
        path = Path(image_path)

        # Step 1: 上传图片获取 media_id
        try:
            uploaded = await self.upload_media(path, "image/png")
        except Exception as e:
            logger.error(f"Failed to upload image: {e}")
            text = f"📎 图片: {path.name}"
            if caption:
                text = f"{caption}\n{text}"
            msg = OutgoingMessage.text(chat_id, text)
            return await self.send_message(msg)

        media_id = uploaded.file_id
        media_url = uploaded.url  # 可能为空
        if not media_id:
            text = f"[图片上传失败: {path.name}]"
            msg = OutgoingMessage.text(chat_id, text)
            return await self.send_message(msg)

        logger.info(
            f"Image uploaded: {path.name} -> media_id={media_id}, url={'YES' if media_url else 'NO'}"
        )

        # Step 2: 尝试 OpenAPI sampleImageMsg（需要权限）
        await self._refresh_token()
        is_group = self._is_group_chat(chat_id)
        # sampleImageMsg 的 photoURL 可以是 URL 或 media_id
        photo_url = media_url or media_id
        msg_param = json.dumps({"photoURL": photo_url})
        headers = {"x-acs-dingtalk-access-token": self._access_token}

        if is_group:
            url = f"{self.API_NEW}/robot/groupMessages/send"
            data = {
                "robotCode": self.config.app_key,
                "openConversationId": chat_id,
                "msgKey": "sampleImageMsg",
                "msgParam": msg_param,
            }
        else:
            user_id = self._conversation_users.get(chat_id, chat_id)
            url = f"{self.API_NEW}/robot/oToMessages/batchSend"
            data = {
                "robotCode": self.config.app_key,
                "userIds": [user_id],
                "msgKey": "sampleImageMsg",
                "msgParam": msg_param,
            }

        try:
            chat_mode = "group" if is_group else "private"
            logger.info(f"Sending image via OpenAPI ({chat_mode}): {path.name}")
            response = await self._http_client.post(url, headers=headers, json=data)
            result = response.json()
            logger.debug(f"OpenAPI image response: {result}")

            if "processQueryKey" in result:
                logger.info(f"Image sent via OpenAPI ({chat_mode}): {path.name}")
                return result["processQueryKey"]
            else:
                error = result.get("message", result.get("errmsg", "Unknown"))
                perm_hint = (
                    "'企业内部机器人发送群聊消息'" if is_group
                    else "'企业内部机器人发送单聊消息'"
                )
                logger.warning(
                    f"OpenAPI sampleImageMsg failed ({chat_mode}): {error} "
                    f"(hint: 需要在钉钉开发者后台开通{perm_hint}权限)"
                )
        except Exception as e:
            logger.warning(f"OpenAPI image send error: {e}")

        # Step 3: 降级为 webhook markdown 嵌入图片
        session_webhook = self._session_webhooks.get(chat_id, "")
        if session_webhook:
            img_ref = media_url or media_id
            md_text = f"![image]({img_ref})"
            if caption:
                md_text = f"{caption}\n\n{md_text}"

            payload = {
                "msgtype": "markdown",
                "markdown": {
                    "title": caption or "图片",
                    "text": md_text,
                },
            }

            try:
                response = await self._http_client.post(session_webhook, json=payload)
                result = response.json()
                if result.get("errcode", 0) == 0:
                    logger.info(
                        f"Sent image via webhook markdown: ref={img_ref[:40]}..."
                    )
                    return f"webhook_{int(time.time())}"
                else:
                    logger.warning(
                        f"Webhook markdown image failed: {result.get('errmsg')}"
                    )
            except Exception as e:
                logger.warning(f"Webhook image send error: {e}")

        # Step 4: 降级为文本
        text = f"📎 图片: {path.name}"
        if caption:
            text = f"{caption}\n{text}"
        msg = OutgoingMessage.text(chat_id, text)
        return await self.send_message(msg)

    async def send_file(
        self,
        chat_id: str,
        file_path: str,
        caption: str | None = None,
    ) -> str:
        """
        发送文件

        策略 (按优先级):
        1. 上传文件获取 media_id
        2. 尝试 OpenAPI 发送 sampleFile（需要权限）
        3. 降级为 webhook 文本提示
        """
        path = Path(file_path)

        # Step 1: 上传文件
        media_id = None
        try:
            uploaded = await self.upload_media(path, "application/octet-stream")
            media_id = uploaded.file_id
            logger.info(
                f"File uploaded: {path.name} -> media_id={media_id}, "
                f"url={'YES' if uploaded.url else 'NO'}"
            )
        except Exception as e:
            logger.warning(f"DingTalk upload_media failed for file: {e}")

        # Step 2: 尝试 OpenAPI sampleFile
        if media_id:
            await self._refresh_token()
            ext = path.suffix.lstrip(".") or "file"
            msg_param = json.dumps({
                "mediaId": media_id,
                "fileName": path.name,
                "fileType": ext,
            })

            is_group = self._is_group_chat(chat_id)
            headers = {"x-acs-dingtalk-access-token": self._access_token}

            if is_group:
                url = f"{self.API_NEW}/robot/groupMessages/send"
                data = {
                    "robotCode": self.config.app_key,
                    "openConversationId": chat_id,
                    "msgKey": "sampleFile",
                    "msgParam": msg_param,
                }
            else:
                user_id = self._conversation_users.get(chat_id, chat_id)
                url = f"{self.API_NEW}/robot/oToMessages/batchSend"
                data = {
                    "robotCode": self.config.app_key,
                    "userIds": [user_id],
                    "msgKey": "sampleFile",
                    "msgParam": msg_param,
                }

            try:
                chat_mode = "group" if is_group else "private"
                logger.info(f"Sending file via OpenAPI ({chat_mode}): {path.name}")
                response = await self._http_client.post(
                    url, headers=headers, json=data
                )
                result = response.json()
                logger.debug(f"OpenAPI file response: {result}")

                if "processQueryKey" in result:
                    logger.info(f"File sent via OpenAPI ({chat_mode}): {path.name}")
                    return result["processQueryKey"]
                else:
                    error = result.get("message", result.get("errmsg", "Unknown"))
                    perm_hint = (
                        "'企业内部机器人发送群聊消息'" if is_group
                        else "'企业内部机器人发送单聊消息'"
                    )
                    logger.warning(
                        f"OpenAPI sampleFile failed ({chat_mode}): {error} "
                        f"(hint: 需要在钉钉开发者后台开通{perm_hint}权限)"
                    )
            except Exception as e:
                logger.warning(f"OpenAPI file send error: {e}")

        # Step 3: 降级为 webhook 文本提示
        text = f"📎 文件: {path.name}"
        if caption:
            text = f"{caption}\n{text}"
        msg = OutgoingMessage.text(chat_id, text)
        return await self.send_message(msg)

    async def send_voice(
        self,
        chat_id: str,
        voice_path: str,
        caption: str | None = None,
    ) -> str:
        """
        发送语音

        钉钉 Webhook 不支持语音，降级为文件发送 → 文本
        """
        return await self.send_file(chat_id, voice_path, caption or "语音消息")

    # ==================== Markdown / 卡片 ====================

    async def send_markdown(
        self,
        user_id: str,
        title: str,
        text: str,
    ) -> str:
        """发送 Markdown 消息"""
        await self._refresh_token()

        url = f"{self.API_NEW}/robot/oToMessages/batchSend"
        headers = {"x-acs-dingtalk-access-token": self._access_token}

        data = {
            "robotCode": self.config.app_key,
            "userIds": [user_id],
            "msgKey": "sampleMarkdown",
            "msgParam": json.dumps({"title": title, "text": text}),
        }

        response = await self._http_client.post(url, headers=headers, json=data)
        result = response.json()
        return result.get("processQueryKey", "")

    async def send_action_card(
        self,
        user_id: str,
        title: str,
        text: str,
        single_title: str,
        single_url: str,
    ) -> str:
        """发送卡片消息"""
        await self._refresh_token()

        url = f"{self.API_NEW}/robot/oToMessages/batchSend"
        headers = {"x-acs-dingtalk-access-token": self._access_token}

        data = {
            "robotCode": self.config.app_key,
            "userIds": [user_id],
            "msgKey": "sampleActionCard",
            "msgParam": json.dumps(
                {
                    "title": title,
                    "text": text,
                    "singleTitle": single_title,
                    "singleURL": single_url,
                }
            ),
        }

        response = await self._http_client.post(url, headers=headers, json=data)
        result = response.json()
        return result.get("processQueryKey", "")

    async def _resolve_local_images(self, text: str) -> str:
        """
        解析 Markdown 中的本地图片路径，上传到钉钉服务器并替换为 media_id。
        解决 AI 发送本地缓存图片时钉钉端无法显示的问题。

        支持的路径格式：
          - 相对路径: data/screenshots/xxx.png, data\\screenshots\\xxx.png
          - 服务器路由路径: /screenshots/xxx.png (映射到 data/screenshots/)
          - 绝对路径: C:/xxx/yyy.png
        """
        if not text:
            return text

        # 匹配 ![alt](path)，路径可能是 windows 或 unix 风格
        pattern = r"!\[(.*?)\]\(([^)]+)\)"

        from core.state import _APP_BASE

        replacements = []
        for match in re.finditer(pattern, text):
            alt = match.group(1)
            path_str = match.group(2).strip()

            # 过滤公网 URL
            if path_str.startswith(("http://", "https://")):
                continue

            # 路径规范化与校验
            try:
                resolved: Path | None = None

                # 1. 服务器路由路径 /screenshots/xxx.png → data/screenshots/xxx.png
                if path_str.startswith("/screenshots/"):
                    filename = path_str[len("/screenshots/"):]
                    candidate = _APP_BASE / "data" / "screenshots" / filename
                    if candidate.exists() and candidate.is_file():
                        resolved = candidate

                # 2. 反斜杠路径规范化后直接查找
                if resolved is None:
                    clean = path_str.replace("\\", "/")
                    p = Path(clean)
                    if p.exists() and p.is_file():
                        resolved = p
                    else:
                        # 尝试相对于 _APP_BASE 的路径
                        p2 = _APP_BASE / clean
                        if p2.exists() and p2.is_file():
                            resolved = p2

                if resolved:
                    # 根据扩展名确认 mime_type
                    suffix = resolved.suffix.lower()
                    mime_map = {".png": "image/png", ".jpg": "image/jpeg",
                                ".jpeg": "image/jpeg", ".gif": "image/gif",
                                ".webp": "image/webp"}
                    mime = mime_map.get(suffix, "image/png")
                    replacements.append((match.group(0), resolved, alt, mime))

            except Exception as exc:
                logger.debug(f"DingTalk: path resolve error for '{path_str}': {exc}")
                continue

        for old_tag, p, alt, mime in replacements:
            try:
                uploaded = await self.upload_media(p, mime)
                if uploaded.file_id:
                    # 钉钉对 markdown 里的媒体 ID 渲染格式为 ![alt](media_id)
                    new_tag = f"![{alt}]({uploaded.file_id})"
                    text = text.replace(old_tag, new_tag)
                    logger.info(
                        f"DingTalk: Auto-uploaded markdown local image: {p} -> {uploaded.file_id}"
                    )
            except Exception as e:
                logger.warning(
                    f"DingTalk: Failed to auto-resolve markdown image {p}: {e}"
                )

        return text

    # ==================== 媒体处理 ====================

    async def download_media(self, media: MediaFile) -> Path:
        """下载媒体文件"""
        if media.local_path and Path(media.local_path).exists():
            return Path(media.local_path)

        if not media.file_id:
            raise ValueError("Media has no file_id (downloadCode)")

        # 使用钉钉新版文件下载 API（POST 方法，新版 token）
        token = await self._refresh_token()
        url = f"{self.API_NEW}/robot/messageFiles/download"
        headers = {"x-acs-dingtalk-access-token": token}
        body = {"downloadCode": media.file_id, "robotCode": self.config.app_key}

        response = await self._http_client.post(url, headers=headers, json=body)
        response.raise_for_status()
        result = response.json()

        download_url = result.get("downloadUrl")
        if not download_url:
            logger.error(
                f"DingTalk download API failed: status={response.status_code}, "
                f"body={result}, file_id={media.file_id[:16]}..."
            )
            raise RuntimeError(
                f"Failed to get download URL: {result.get('message', 'Unknown')}"
            )

        # 下载文件
        response = await self._http_client.get(download_url, timeout=60.0)
        response.raise_for_status()

        local_path = self.media_dir / media.filename
        with open(local_path, "wb") as f:
            f.write(response.content)

        media.local_path = str(local_path)
        media.status = MediaStatus.READY

        logger.info(f"Downloaded media: {media.filename}")
        return local_path

    async def upload_media(self, path: Path, mime_type: str) -> MediaFile:
        """
        上传媒体文件到钉钉

        使用钉钉旧版 media/upload API 上传文件，获取 media_id。
        注意: 此接口在 oapi.dingtalk.com 上，需要旧版 access_token。
        """
        old_token = await self._refresh_old_token()

        url = f"{self.API_BASE}/media/upload"
        params = {"access_token": old_token}

        # 根据 mime_type 确定类型
        if mime_type.startswith("image/"):
            media_type = "image"
        elif mime_type.startswith("audio/"):
            media_type = "voice"
        elif mime_type.startswith("video/"):
            media_type = "video"
        else:
            media_type = "file"

        try:
            with open(path, "rb") as f:
                files = {"media": (path.name, f, mime_type)}
                data = {"type": media_type}
                response = await self._http_client.post(
                    url, params=params, files=files, data=data
                )

            result = response.json()
            logger.debug(f"Upload response: {result}")

            if result.get("errcode", 0) != 0:
                raise RuntimeError(
                    f"Upload failed: {result.get('errmsg', 'Unknown error')}"
                )

            media_id = result.get("media_id", "")
            media_url = result.get("url", "")

            media = MediaFile.create(
                filename=path.name,
                mime_type=mime_type,
                file_id=media_id,
                url=media_url,
            )
            media.status = MediaStatus.READY

            logger.info(
                f"Uploaded media: {path.name} -> media_id={media_id}, "
                f"url={'YES' if media_url else 'NO'}, type={media_type}"
            )
            return media

        except Exception as e:
            logger.error(f"Failed to upload media {path.name}: {e}")
            # 返回基础 MediaFile（无 media_id）
            return MediaFile.create(
                filename=path.name,
                mime_type=mime_type,
            )

    # ==================== Token 管理 ====================

    async def _refresh_token(self) -> str:
        """
        刷新新版 access token (用于 api.dingtalk.com/v1.0 接口)

        新版 API (robot/groupMessages/send, robot/oToMessages/batchSend 等)
        需要通过 OAuth2 接口获取的 accessToken，
        放在请求头 x-acs-dingtalk-access-token 中。
        """
        if self._access_token and time.time() < self._token_expires_at:
            return self._access_token

        _import_httpx()
        async with self._token_lock:
            if self._access_token and time.time() < self._token_expires_at:
                logger.debug("Reuse cached new-style access token")
                return self._access_token

            url = f"{self.API_NEW}/oauth2/accessToken"
            body = {
                "appKey": self.config.app_key,
                "appSecret": self.config.app_secret,
            }

            logger.info("Refreshing new-style access token (OAuth2)")
            response = await self._http_client.post(url, json=body)
            response.raise_for_status()
            data = response.json()

            if "accessToken" not in data:
                raise RuntimeError(
                    f"Failed to get new access token: {data.get('message', data)}"
                )

            self._access_token = data["accessToken"]
            self._token_expires_at = time.time() + data.get("expireIn", 7200) - 60
            logger.info("Refreshed new-style access token (OAuth2)")

            return self._access_token

    async def _refresh_old_token(self) -> str:
        """
        刷新旧版 access token (用于 oapi.dingtalk.com 接口)

        旧版 API (media/upload, gettoken 等) 使用 access_token 查询参数。
        """
        if self._old_access_token and time.time() < self._old_token_expires_at:
            return self._old_access_token

        _import_httpx()
        async with self._old_token_lock:
            if self._old_access_token and time.time() < self._old_token_expires_at:
                logger.debug("Reuse cached old-style access token")
                return self._old_access_token

            url = f"{self.API_BASE}/gettoken"
            params = {
                "appkey": self.config.app_key,
                "appsecret": self.config.app_secret,
            }

            logger.info("Refreshing old-style access token (gettoken)")
            response = await self._http_client.get(url, params=params)
            response.raise_for_status()
            data = response.json()

            if data.get("errcode", 0) != 0:
                raise RuntimeError(f"Failed to get old access token: {data.get('errmsg')}")

            self._old_access_token = data["access_token"]
            self._old_token_expires_at = time.time() + data["expires_in"] - 60
            logger.info("Refreshed old-style access token (gettoken)")

            return self._old_access_token

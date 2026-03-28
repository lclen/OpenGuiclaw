"""
消息网关 (Message Gateway)

负责维护所有的通道适配器（DingTalk, Feishu, Telegram），
接收来自通道的消息，处理媒体文件，并将消息路由到 Agent，最后将回复发送回通道。
"""

import asyncio
import base64
import json
import logging
import mimetypes
from typing import Dict, Any

from .base import ChannelAdapter
from .markdown import contains_markdown, normalize_markdown_for_channel
from .types import UnifiedMessage, OutgoingMessage, MessageContent
from core.automation_context import (
    reset_automation_source_context,
    set_automation_source_context,
)
from core.im_selfcheck_subscriptions import (
    list_selfcheck_subscriptions,
    remove_selfcheck_subscription,
    upsert_selfcheck_subscription,
)
from core.im_bots import is_im_session_id, make_im_session_id, parse_channel_name
from core.session import Session

logger = logging.getLogger(__name__)

_SELFCHECK_SUBSCRIBE_COMMAND = "订阅每日自检"
_SELFCHECK_UNSUBSCRIBE_COMMAND = "取消订阅每日自检"
_SELFCHECK_STATUS_COMMAND = "查看自检订阅"


def _safe_json_dumps(payload: Any, limit: int = 500) -> str:
    try:
        text = json.dumps(payload, ensure_ascii=False)
    except Exception:
        text = str(payload)
    if len(text) > limit:
        return text[:limit] + "..."
    return text


class ChannelGateway:
    def __init__(self, agent: Any):
        """
        Args:
            agent: openGuiclaw 的核心 Agent 实例
        """
        self.agent = agent
        self.adapters: Dict[str, ChannelAdapter] = {}
        # 简单的并发锁，避免多通道或多用户同时处理消息时污染全局 session
        self._lock = asyncio.Lock()

    def register_adapter(self, adapter: ChannelAdapter) -> None:
        """注册一个通道适配器，并绑定消息回调"""
        self.adapters[adapter.channel_name] = adapter
        adapter.on_message(self._on_message)
        logger.info(f"Registered channel adapter: {adapter.channel_name}")

    async def start(self) -> None:
        """启动所有已注册的适配器"""
        logger.info("Starting Channel Gateway...")
        for name, adapter in self.adapters.items():
            try:
                await adapter.start()
                logger.info(f"Started adapter: {name}")
            except Exception as e:
                logger.error(f"Failed to start adapter {name}: {e}", exc_info=True)

    async def stop(self) -> None:
        """停止所有适配器"""
        logger.info("Stopping Channel Gateway...")
        for name, adapter in self.adapters.items():
            try:
                await adapter.stop()
                logger.info(f"Stopped adapter: {name}")
            except Exception as e:
                logger.error(f"Failed to stop adapter {name}: {e}", exc_info=True)

    async def _on_message(self, message: UnifiedMessage) -> None:
        """
        统一的消息处理入口
        """
        try:
            logger.info(f"[Gateway] Received message from {message.channel}:{message.chat_id}")
            
            # 使用后台任务处理消息，以免阻塞适配器的接收循环
            asyncio.create_task(self._process_message_task(message))
            
        except Exception as e:
            logger.error(f"[Gateway] Error handling message: {e}", exc_info=True)

    async def _process_message_task(self, message: UnifiedMessage) -> None:
        """实际处理单条消息的逻辑，包含下载媒体和调用 Agent"""
        adapter = self.adapters.get(message.channel)
        if not adapter:
            logger.error(f"[Gateway] Unknown channel: {message.channel}")
            return

        command_text = (message.content.text or "").strip()
        if command_text in {
            _SELFCHECK_SUBSCRIBE_COMMAND,
            _SELFCHECK_UNSUBSCRIBE_COMMAND,
            _SELFCHECK_STATUS_COMMAND,
        } and not (
            message.content.images or message.content.voices or message.content.files or message.content.videos
        ):
            handled = await self._handle_selfcheck_subscription_command(adapter, message, command_text)
            if handled:
                return

        # ==========================================
        # 1. 预处理媒体文件
        # ==========================================
        text_parts = []
        final_content = []

        if message.content.text:
            text_parts.append(message.content.text)

        # 处理图片
        for img in message.content.images:
            if not img.local_path:
                try:
                    await adapter.download_media(img)
                except Exception as e:
                    logger.error(f"[Gateway] Failed to download image {img.file_id}: {e}")
            
            if img.local_path:
                try:
                    with open(img.local_path, "rb") as f:
                        b64 = base64.b64encode(f.read()).decode("utf-8")
                    mime = img.mime_type or mimetypes.guess_type(img.local_path)[0] or "image/jpeg"
                    data_url = f"data:{mime};base64,{b64}"
                    final_content.append({"type": "image_url", "image_url": {"url": data_url}})
                except Exception as e:
                    logger.error(f"[Gateway] Failed to encode image: {e}")

        # 处理语音（如果没有集成 STT，目前直接给出提示）
        if message.content.voices:
            text_parts.append("[收到语音消息]")

        # 处理文件
        for file in message.content.files:
            text_parts.append(f"[收到文件附件: {file.filename}]")

        if text_parts:
            final_content.append({"type": "text", "text": "\n".join(text_parts).strip()})

        if not final_content:
            logger.warning("[Gateway] Message content is empty after processing.")
            return

        # 决定是以 list 还是纯文本发送 (适配 agent 的输入要求)
        if len(final_content) == 1 and final_content[0]["type"] == "text":
            user_input = final_content[0]["text"]
        else:
            user_input = final_content

        # ==========================================
        # 2. 会话管理与 Agent 调用
        # ==========================================
        session_id = make_im_session_id(message.channel, message.chat_id)
        session_platform, session_bot_id = parse_channel_name(message.channel)
        
        # 采用全局锁避免同时调用 agent 造成全局 session 相互覆盖
        async with self._lock:
            # ====== 记录当前 GUI 会话，稍后恢复 ======
            # 注意：直接保存 Session 对象引用，而不是 session_id，
            # 这样恢复时只需要修改指针，不需要从磁盘 load（避免覆盖正在进行中的 GUI 会话）
            gui_session = None
            if hasattr(self.agent.sessions, "_current") and self.agent.sessions._current:
                current_id = getattr(self.agent.sessions._current, "session_id", None)
                # 只有 GUI 的普通会话才需要恢复（IM 会话本身不需要恢复）
                is_im = is_im_session_id(current_id)
                if not is_im:
                    gui_session = self.agent.sessions._current

            # ====== 加载或创建 IM 专属会话 ======
            im_session = self.agent.sessions.load(session_id)
            if not im_session:
                im_session = Session(session_id)
                self.agent.sessions._current = im_session
                # 立即保存新会话到磁盘，防止数据丢失
                self.agent.sessions.save(im_session)
            if isinstance(getattr(im_session, "metadata", None), dict):
                im_session.metadata.update(
                    {
                        "platform": session_platform or message.channel,
                        "bot_id": session_bot_id or getattr(adapter, "bot_id", None) or message.channel,
                        "channel_name": message.channel,
                        "chat_id": message.chat_id,
                        "chat_type": message.chat_type,
                        "chat_name": str(message.metadata.get("chat_name") or ""),
                        "display_name": str(
                            message.metadata.get("sender_name")
                            or message.metadata.get("chat_name")
                            or message.channel_user_id
                            or message.chat_id
                        ),
                    }
                )
            
            try:
                source_token = set_automation_source_context(
                    source_kind="im",
                    source_session_id=session_id,
                    source_channel=message.channel,
                    source_chat_id=message.chat_id,
                )
                # 发送正在输入状态
                await adapter.send_typing(message.chat_id)
                logger.info(
                    "[Gateway] Start streaming agent reply channel=%s bot=%s chat=%s",
                    message.channel,
                    getattr(adapter, "bot_id", None),
                    message.chat_id,
                )

                full_response = ""
                used_streaming = False
                thinking_text = ""
                thinking_duration_ms = 0
                delta_count = 0
                # 调用 agent 的流式输出（兼容工具调用等复杂行为）
                async for chunk_str in self.agent.chat_stream(user_input):
                    try:
                        chunk = json.loads(chunk_str) if isinstance(chunk_str, str) else chunk_str
                    except Exception:
                        chunk = {}
                    if not isinstance(chunk, dict):
                        continue

                    chunk_type = chunk.get("type")
                    if chunk_type == "thinking_start":
                        logger.debug(
                            "[Gateway] thinking_start channel=%s chat=%s",
                            message.channel,
                            message.chat_id,
                        )
                    elif chunk_type in ("thinking_delta", "thinking_chunk"):
                        content = str(chunk.get("content") or "")
                        if content:
                            logger.debug(
                                "[Gateway] thinking_delta channel=%s chat=%s len=%s",
                                message.channel,
                                message.chat_id,
                                len(content),
                            )
                            thinking_text += content
                            if adapter.supports_streaming():
                                used_streaming = True
                                await adapter.stream_thinking(
                                    message.chat_id,
                                    content,
                                    thread_id=message.thread_id,
                                    is_group=message.is_group,
                                    duration_ms=thinking_duration_ms,
                                )
                    elif chunk_type == "thinking_end":
                        thinking_duration_ms = int(chunk.get("duration_ms") or thinking_duration_ms or 0)
                        logger.debug(
                            "[Gateway] thinking_end channel=%s chat=%s duration_ms=%s has_thinking=%s",
                            message.channel,
                            message.chat_id,
                            thinking_duration_ms,
                            bool(chunk.get("has_thinking")),
                        )
                    elif chunk_type == "tool_call":
                        logger.debug(
                            "[Gateway] tool_call channel=%s chat=%s tool=%s",
                            message.channel,
                            message.chat_id,
                            chunk.get("name"),
                        )
                        if adapter.supports_streaming():
                            used_streaming = True
                            tool_name = str(chunk.get("name") or "unknown")
                            tool_params = _safe_json_dumps(chunk.get("params") or {})
                            await adapter.stream_chain_text(
                                message.chat_id,
                                f"🔧 调用工具：`{tool_name}` {tool_params}",
                                thread_id=message.thread_id,
                                is_group=message.is_group,
                            )
                    elif chunk_type == "tool_result":
                        logger.debug(
                            "[Gateway] tool_result channel=%s chat=%s tool=%s",
                            message.channel,
                            message.chat_id,
                            chunk.get("name"),
                        )
                        if adapter.supports_streaming():
                            used_streaming = True
                            tool_name = str(chunk.get("name") or "unknown")
                            tool_result = str(chunk.get("result") or "")
                            await adapter.stream_chain_text(
                                message.chat_id,
                                f"✅ 工具结果：`{tool_name}`\n{tool_result}",
                                thread_id=message.thread_id,
                                is_group=message.is_group,
                            )
                    elif chunk_type in ("text_delta", "message_chunk"):
                        text = str(chunk.get("content") or "")
                        if text:
                            delta_count += 1
                            logger.debug(
                                "[Gateway] text_delta channel=%s chat=%s len=%s count=%s",
                                message.channel,
                                message.chat_id,
                                len(text),
                                delta_count,
                            )
                        full_response += text
                        if text and adapter.supports_streaming():
                            used_streaming = True
                            await adapter.stream_token(
                                message.chat_id,
                                text,
                                thread_id=message.thread_id,
                                is_group=message.is_group,
                            )
                    elif chunk_type == "done":
                        logger.info(
                            "[Gateway] stream_done channel=%s bot=%s chat=%s chars=%s deltas=%s streaming=%s",
                            message.channel,
                            getattr(adapter, "bot_id", None),
                            message.chat_id,
                            len(full_response),
                            delta_count,
                            used_streaming,
                        )

                # ==========================================
                # 3. 发送回复
                # ==========================================
                if full_response.strip():
                    final_text = full_response.strip()
                    if used_streaming:
                        finalized = await adapter.finalize_stream(
                            message.chat_id,
                            final_text,
                            thread_id=message.thread_id,
                        )
                        logger.info(
                            "[Gateway] finalize_stream channel=%s chat=%s finalized=%s len=%s",
                            message.channel,
                            message.chat_id,
                            finalized,
                            len(final_text),
                        )
                        if finalized:
                            return
                    rendered_text = normalize_markdown_for_channel(final_text, adapter.channel_name)
                    out_msg = OutgoingMessage.text(
                        chat_id=message.chat_id,
                        text=rendered_text,
                        thread_id=message.thread_id,
                        parse_mode="markdown" if contains_markdown(final_text) else None,
                        metadata={
                            "session_webhook": message.metadata.get("session_webhook", ""),
                            "is_group": message.is_group,
                            "chat_name": message.metadata.get("chat_name", ""),
                            "display_name": message.metadata.get("sender_name", ""),
                            "thinking": thinking_text,
                            "thinking_duration_ms": thinking_duration_ms,
                        },
                    )
                    await adapter.send_message(out_msg)
                    logger.info(
                        "[Gateway] reply sent channel=%s chat=%s len=%s streaming=%s",
                        message.channel,
                        message.chat_id,
                        len(rendered_text),
                        used_streaming,
                    )

            except Exception as e:
                logger.error(f"[Gateway] Error during agent execution: {e}", exc_info=True)
                rendered_text = normalize_markdown_for_channel(
                    f"机器人处理消息时发生异常：{str(e)}",
                    adapter.channel_name,
                )
                out_msg = OutgoingMessage.text(
                    chat_id=message.chat_id,
                    text=rendered_text,
                    thread_id=message.thread_id,
                    metadata={
                        "session_webhook": message.metadata.get("session_webhook", ""),
                        "is_group": message.is_group,
                        "chat_name": message.metadata.get("chat_name", ""),
                        "display_name": message.metadata.get("sender_name", ""),
                    },
                )
                await adapter.send_message(out_msg)

            finally:
                reset_automation_source_context(source_token)
                # 保存 IM 会话状态
                self.agent.sessions.save(self.agent.sessions._current)
                
                # ====== 恢复 GUI 会话指针（只修改内存指针，不从磁盘 load）======
                if gui_session is not None:
                    self.agent.sessions._current = gui_session
                    logger.debug(f"[Gateway] Restored GUI session: {gui_session.session_id}")

    async def _handle_selfcheck_subscription_command(
        self,
        adapter: ChannelAdapter,
        message: UnifiedMessage,
        command_text: str,
    ) -> bool:
        session_id = make_im_session_id(message.channel, message.chat_id)
        metadata = message.metadata if isinstance(message.metadata, dict) else {}
        label = str(
            metadata.get("sender_name")
            or metadata.get("chat_name")
            or message.channel_user_id
            or message.chat_id
        )
        chat_name = str(metadata.get("chat_name") or "")

        try:
            if command_text == _SELFCHECK_SUBSCRIBE_COMMAND:
                upsert_selfcheck_subscription(
                    session_id=session_id,
                    channel_name=message.channel,
                    chat_id=message.chat_id,
                    label=label,
                    chat_name=chat_name,
                )
                reply = (
                    "✅ 已订阅每日自检\n"
                    "- 后续系统每日自检会向当前会话推送摘要\n"
                    "- 完整报告仍保留在桌面会话 / 自动化收件箱"
                )
            elif command_text == _SELFCHECK_UNSUBSCRIBE_COMMAND:
                deleted = remove_selfcheck_subscription(
                    session_id=session_id,
                    channel_name=message.channel,
                    chat_id=message.chat_id,
                )
                reply = "✅ 已取消每日自检订阅" if deleted else "ℹ️ 当前会话尚未订阅每日自检"
            else:
                current = next(
                    (item for item in list_selfcheck_subscriptions() if item.get("session_id") == session_id),
                    None,
                )
                if current and current.get("enabled"):
                    last_status = current.get("last_status") or "尚未发送"
                    last_sent_at = current.get("last_sent_at") or "暂无记录"
                    reply = (
                        "📋 当前自检订阅状态：已订阅\n"
                        f"- 通道：{message.channel}\n"
                        f"- Chat：{chat_name or label or message.chat_id}\n"
                        f"- 最近投递：{last_status} / {last_sent_at}"
                    )
                else:
                    reply = (
                        "📋 当前自检订阅状态：未订阅\n"
                        f"- 通道：{message.channel}\n"
                        f"- Chat：{chat_name or label or message.chat_id}\n"
                        "- 发送“订阅每日自检”即可开启每日摘要推送"
                    )

            rendered_text = normalize_markdown_for_channel(reply, adapter.channel_name)
            out_msg = OutgoingMessage.text(
                chat_id=message.chat_id,
                text=rendered_text,
                thread_id=message.thread_id,
                parse_mode="markdown" if contains_markdown(reply) else None,
                metadata={
                    "session_webhook": metadata.get("session_webhook", ""),
                    "is_group": message.is_group,
                    "chat_name": metadata.get("chat_name", ""),
                    "display_name": metadata.get("sender_name", ""),
                },
            )
            await adapter.send_message(out_msg)
            logger.info(
                "[Gateway] handled selfcheck subscription command channel=%s chat=%s command=%s",
                message.channel,
                message.chat_id,
                command_text,
            )
            return True
        except Exception as exc:
            logger.error(
                "[Gateway] failed to handle selfcheck subscription command channel=%s chat=%s command=%s error=%s",
                message.channel,
                message.chat_id,
                command_text,
                exc,
                exc_info=True,
            )
            return False


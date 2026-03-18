import { useEffect, useRef, useState } from 'react';
import {
  getHostApp,
  type ChatAskOption,
  type ChatBlock,
  type ChatMessage,
  type OpenGuiclawApp,
  waitForHostApp
} from '../bridge/openGuiclaw';

type ChatSnapshot = {
  currentThreadId: string | null;
  threadLoading: boolean;
  messages: ChatMessage[];
};

function cloneChatBlock(block: ChatBlock): ChatBlock {
  return {
    ...block,
    options: Array.isArray(block.options) ? block.options.map((option) => ({ ...option })) : block.options
  };
}

function cloneChatMessage(message: ChatMessage): ChatMessage {
  return {
    ...message,
    blocks: Array.isArray(message.blocks) ? message.blocks.map(cloneChatBlock) : message.blocks
  };
}

function snapshotChat(app: OpenGuiclawApp): ChatSnapshot {
  return {
    currentThreadId: app.currentThreadId ?? null,
    threadLoading: !!app.threadLoading,
    messages: Array.isArray(app.messages) ? app.messages.map(cloneChatMessage) : []
  };
}

function HtmlBlock({ html }: { html?: string }) {
  return <div dangerouslySetInnerHTML={{ __html: html || '' }} />;
}

export function ChatMessageList() {
  const [hostApp, setHostApp] = useState<OpenGuiclawApp | null>(getHostApp());
  const [currentThreadId, setCurrentThreadId] = useState<string | null>(hostApp?.currentThreadId ?? null);
  const [threadLoading, setThreadLoading] = useState<boolean>(!!hostApp?.threadLoading);
  const [messages, setMessages] = useState<ChatMessage[]>(() =>
    hostApp && Array.isArray(hostApp.messages) ? hostApp.messages.map(cloneChatMessage) : []
  );
  const [errorText, setErrorText] = useState('');
  // 用于判断是否应该滚底：只跟踪消息数量和最后一条消息的内容/blocks长度
  const scrollAnchorRef = useRef<{ count: number; lastId: string; lastBlockCount: number } | null>(null);

  useEffect(() => {
    let mounted = true;

    const syncFromHost = (app: OpenGuiclawApp) => {
      if (!mounted) return;
      const next = snapshotChat(app);
      setCurrentThreadId(next.currentThreadId);
      setThreadLoading(next.threadLoading);
      setMessages(next.messages);
    };

    waitForHostApp()
      .then((app) => {
        if (!mounted) return;
        setHostApp(app);
        syncFromHost(app);
      })
      .catch((error: Error) => {
        if (!mounted) return;
        setErrorText(error.message);
      });

    const handleChatUpdated = () => {
      const app = getHostApp();
      if (!app) return;
      syncFromHost(app);
    };

    window.addEventListener('openguiclaw:chat-updated', handleChatUpdated);
    return () => {
      mounted = false;
      window.removeEventListener('openguiclaw:chat-updated', handleChatUpdated);
    };
  }, []);

  useEffect(() => {
    const container = document.getElementById('chat-container');
    if (!container) return;

    const last = messages[messages.length - 1];
    const count = messages.length;
    const lastId = last?.id ?? '';
    const lastBlockCount = last?.blocks?.length ?? 0;

    const prev = scrollAnchorRef.current;
    const shouldScroll =
      !prev ||
      count !== prev.count ||
      lastId !== prev.lastId ||
      lastBlockCount !== prev.lastBlockCount;

    scrollAnchorRef.current = { count, lastId, lastBlockCount };

    if (!shouldScroll) return;

    const rafId = window.requestAnimationFrame(() => {
      container.scrollTop = container.scrollHeight;
    });
    return () => window.cancelAnimationFrame(rafId);
  }, [currentThreadId, threadLoading, messages]);

  async function handleAskUserChoice(message: ChatMessage, block: ChatBlock, option: ChatAskOption) {
    if (!hostApp || block.answered) return;

    setMessages((current) =>
      current.map((item) => {
        if (item.id !== message.id) return item;
        return {
          ...item,
          blocks: (item.blocks || []).map((innerBlock) => {
            if (innerBlock.id !== block.id) return innerBlock;
            return {
              ...innerBlock,
              answered: true,
              resultStr: option.label
            };
          })
        };
      })
    );

    try {
      await hostApp.submitAskUserChoice(message, block, option);
    } catch (error) {
      setErrorText(error instanceof Error ? error.message : '提交选项失败');
    }
  }

  function toggleThinking(messageId: string) {
    setMessages((current) =>
      current.map((item) =>
        item.id === messageId ? { ...item, _thinkCollapsed: !item._thinkCollapsed } : item
      )
    );
  }

  function toggleToolBlock(messageId: string, blockId?: string) {
    if (!blockId) return;
    setMessages((current) =>
      current.map((item) => {
        if (item.id !== messageId) return item;
        return {
          ...item,
          blocks: (item.blocks || []).map((block) =>
            block.id === blockId ? { ...block, _collapsed: !block._collapsed } : block
          )
        };
      })
    );
  }

  if (!currentThreadId) return null;

  return (
    <>
      {errorText ? <div className="chat-react-error">{errorText}</div> : null}

      {threadLoading ? <div className="chat-empty-state">加载对话中...</div> : null}

      {!threadLoading && messages.length === 0 ? (
        <div className="chat-empty-state">
          <div className="chat-empty-icon">
            <svg width="20" height="20" fill="none" stroke="var(--shell-accent)" viewBox="0 0 24 24">
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth="1.5"
                d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z"
              />
            </svg>
          </div>
          <p className="chat-empty-title">对话已就绪</p>
          <p className="chat-empty-sub">随时可以开始。</p>
        </div>
      ) : null}

      {!threadLoading
        ? messages.map((message) => (
            <div key={message.id}>
              {message.role === 'visual_log' ? (
                <div className="chat-visual-log">
                  <span className="chat-visual-log-dot"></span>
                  <span className="md-body" dangerouslySetInnerHTML={{ __html: message.html || '' }} />
                </div>
              ) : null}

              {message.role === 'user' ? (
                <div className="chat-row chat-row-user">
                  <div className="chat-bubble-user">
                    <div
                      className="md-body"
                      dangerouslySetInnerHTML={{ __html: message.html || message.content || '' }}
                    />
                  </div>
                </div>
              ) : null}

              {message.role === 'assistant' ? (
                <div className="chat-row chat-row-assistant">
                  <div className="chat-assistant-body">
                    {message.thinkingHtml ? (
                      <div className="chat-think-block">
                        <div className="chat-think-header" onClick={() => toggleThinking(message.id)}>
                          <svg
                            width="11"
                            height="11"
                            fill="none"
                            stroke="var(--shell-accent)"
                            viewBox="0 0 24 24"
                            style={{
                              transform: message._thinkCollapsed ? 'rotate(-90deg)' : undefined,
                              transition: 'transform 0.2s',
                              flexShrink: 0,
                              opacity: 0.7
                            }}
                          >
                            <path
                              strokeLinecap="round"
                              strokeLinejoin="round"
                              strokeWidth="2.5"
                              d="M19 9l-7 7-7-7"
                            />
                          </svg>
                          <span>推理过程</span>
                        </div>
                        {!message._thinkCollapsed ? (
                          <div className="chat-think-body md-body font-mono">
                            <HtmlBlock html={message.thinkingHtml} />
                          </div>
                        ) : null}
                      </div>
                    ) : null}

                    {message._isThinking ? (
                      <div className="chat-thinking-indicator">
                        <span className="chat-thinking-dots">
                          <span></span>
                          <span></span>
                          <span></span>
                        </span>
                        <span>思考中</span>
                      </div>
                    ) : null}

                    {message.blocks && message.blocks.length > 0 ? (
                      <div className="chat-blocks">
                        {message.blocks.map((block, index) => (
                          <div key={block.id || `${message.id}-${block.type}-${index}`}>
                            {block.type === 'text' ? (
                              <div className="chat-text-block md-body">
                                <HtmlBlock html={block.html} />
                              </div>
                            ) : null}

                            {block.type === 'tool' ? (
                              <div className="chat-tool-block">
                                <div
                                  className="chat-tool-header"
                                  onClick={() => toggleToolBlock(message.id, block.id)}
                                >
                                  <div
                                    className={`chat-tool-icon ${
                                      block.status === 'done'
                                        ? 'chat-tool-icon-done'
                                        : 'chat-tool-icon-running'
                                    }`}
                                  >
                                    {block.status === 'running' ? (
                                      <svg
                                        width="10"
                                        height="10"
                                        fill="none"
                                        viewBox="0 0 24 24"
                                        style={{ animation: 'spin 1s linear infinite' }}
                                      >
                                        <circle
                                          cx="12"
                                          cy="12"
                                          r="10"
                                          stroke="rgba(99,179,237,0.9)"
                                          strokeWidth="3"
                                          strokeDasharray="30 70"
                                          strokeLinecap="round"
                                        />
                                      </svg>
                                    ) : (
                                      <svg
                                        width="10"
                                        height="10"
                                        fill="none"
                                        stroke="var(--shell-accent)"
                                        viewBox="0 0 24 24"
                                      >
                                        <path
                                          strokeLinecap="round"
                                          strokeLinejoin="round"
                                          strokeWidth="2.5"
                                          d="M5 13l4 4L19 7"
                                        />
                                      </svg>
                                    )}
                                  </div>
                                  <span className="chat-tool-name">{block.name}</span>
                                  <span
                                    className={`chat-tool-status ${
                                      block.status === 'running'
                                        ? 'chat-tool-status-running'
                                        : 'chat-tool-status-done'
                                    }`}
                                  >
                                    {block.status === 'running' ? '运行中' : '完成'}
                                  </span>
                                  <svg
                                    width="10"
                                    height="10"
                                    fill="none"
                                    stroke="var(--shell-text-muted)"
                                    viewBox="0 0 24 24"
                                    style={{
                                      transform: block._collapsed ? 'rotate(-90deg)' : undefined,
                                      transition: 'transform 0.2s',
                                      marginLeft: 'auto',
                                      flexShrink: 0
                                    }}
                                  >
                                    <path
                                      strokeLinecap="round"
                                      strokeLinejoin="round"
                                      strokeWidth="2.5"
                                      d="M19 9l-7 7-7-7"
                                    />
                                  </svg>
                                </div>
                                {!block._collapsed ? (
                                  <div className="chat-tool-body">
                                    <div className="chat-tool-code chat-tool-params">{block.paramsStr}</div>
                                    {block.resultStr ? (
                                      <div className="chat-tool-result-wrap">
                                        <div className="chat-tool-code chat-tool-result">
                                          {block.resultStr}
                                        </div>
                                      </div>
                                    ) : null}
                                  </div>
                                ) : null}
                              </div>
                            ) : null}

                            {block.type === 'status_done' ? (
                              <div className="chat-status-done">
                                <div className="chat-status-done-icon">
                                  <svg
                                    width="9"
                                    height="9"
                                    fill="none"
                                    stroke="var(--shell-accent)"
                                    viewBox="0 0 24 24"
                                  >
                                    <path
                                      strokeLinecap="round"
                                      strokeLinejoin="round"
                                      strokeWidth="3"
                                      d="M5 13l4 4L19 7"
                                    />
                                  </svg>
                                </div>
                                任务已完成                              </div>
                            ) : null}

                            {block.type === 'ask_user' ? (
                              <div className="chat-ask-block">
                                <p className="chat-ask-question">{block.question}</p>
                                {!block.answered ? (
                                  <div className="chat-ask-options">
                                    {(block.options || []).map((option) => (
                                      <button
                                        key={option.id}
                                        type="button"
                                        className="chat-ask-btn"
                                        onClick={() => handleAskUserChoice(message, block, option)}
                                      >
                                        {option.label}
                                      </button>
                                    ))}
                                  </div>
                                ) : null}
                                {block.answered ? (
                                  <div className="chat-ask-answered">已回答：{block.resultStr}</div>
                                ) : null}
                              </div>
                            ) : null}
                          </div>
                        ))}
                      </div>
                    ) : null}

                    {!message.blocks || message.blocks.length === 0 ? (
                      <div className="chat-text-block md-body">
                        <HtmlBlock html={message.html || message.content} />
                      </div>
                    ) : null}
                  </div>
                </div>
              ) : null}
            </div>
          ))
        : null}
    </>
  );
}

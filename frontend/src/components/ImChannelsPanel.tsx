import { useCallback, useEffect, useMemo, useState } from 'react';
import type { IMChannelSummary, IMSessionSummary, SessionMessagePayload } from '../bridge/openGuiclaw';
import { dispatchShellAction } from '../bridge/openGuiclaw';
import { buildImTimeline, type ImTimelineEntry } from './imSessionTransform';
import { UiButton } from './ui/UiButton';
import { UiCard } from './ui/UiCard';
import { UiStatusPill } from './ui/UiStatusPill';
import { cn } from '../utils/cn';
import { useWorkspaceShellBridge } from '../hooks/useWorkspaceShellBridge';

declare global {
  interface Window {
    marked?: {
      parse: (markdown: string) => string;
    };
  }
}

function escapeHtml(value: string) {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function renderMarkdown(value: string) {
  if (!value) return '';
  if (window.marked?.parse) return window.marked.parse(value);
  return `<p>${escapeHtml(value).replace(/\n/g, '<br />')}</p>`;
}

function parseResponse(response: Response) {
  const contentType = response.headers.get('content-type') || '';
  if (contentType.includes('application/json')) return response.json();
  return response.text();
}

async function readErrorMessage(response: Response, fallback: string) {
  try {
    const payload = await parseResponse(response);
    if (payload && typeof payload === 'object' && 'detail' in payload && typeof payload.detail === 'string') {
      return payload.detail;
    }
    if (typeof payload === 'string' && payload.trim()) return payload;
  } catch {
    // Ignore parse failures.
  }
  return fallback;
}

function parseDateLike(value?: string | Date | null) {
  if (!value) return null;
  if (value instanceof Date) return Number.isNaN(value.getTime()) ? null : value;
  const normalized = value.includes('T') ? value : value.replace(' ', 'T');
  const date = new Date(normalized);
  return Number.isNaN(date.getTime()) ? null : date;
}

function formatDateTime(value?: string | Date | null) {
  const date = parseDateLike(value);
  if (!date) return '暂无记录';
  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  }).format(date);
}

function formatDateLabel(value?: string | Date | null) {
  const date = parseDateLike(value);
  if (!date) return '';
  return new Intl.DateTimeFormat('zh-CN', {
    month: 'long',
    day: 'numeric',
    weekday: 'short'
  }).format(date);
}

function formatTime(value?: string | Date | null) {
  const date = parseDateLike(value);
  if (!date) return '';
  return new Intl.DateTimeFormat('zh-CN', {
    hour: '2-digit',
    minute: '2-digit'
  }).format(date);
}

function channelTone(channel: IMChannelSummary) {
  if (!channel.enabled) return 'disabled';
  if (channel.status === 'online') return 'success';
  if (channel.last_error) return 'danger';
  return 'neutral';
}

function getChannelLabel(channel: IMChannelSummary) {
  return channel.display_name || channel.name || channel.platform || channel.channel_name;
}

function getSessionLabel(session: IMSessionSummary) {
  return session.alias || session.display_name || session.chat_name || session.chat_id || session.session_id;
}

export function ImChannelsPanel() {
  const { snapshot } = useWorkspaceShellBridge();
  const [channels, setChannels] = useState<IMChannelSummary[]>([]);
  const [sessions, setSessions] = useState<IMSessionSummary[]>([]);
  const [selectedChannel, setSelectedChannel] = useState<string | null>(null);
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(null);
  const [timeline, setTimeline] = useState<ImTimelineEntry[]>([]);
  const [errorText, setErrorText] = useState('');
  const [refreshing, setRefreshing] = useState(false);
  const [messageLoading, setMessageLoading] = useState(false);
  const [deletingSessionId, setDeletingSessionId] = useState<string | null>(null);

  const selectedSession = useMemo(
    () => sessions.find((session) => session.session_id === selectedSessionId) || null,
    [sessions, selectedSessionId]
  );

  const onlineCount = channels.filter((channel) => channel.status === 'online').length;
  const offlineCount = channels.filter((channel) => channel.status !== 'online').length;

  const latestActivity = useMemo(() => {
    const source = [...channels.map((channel) => channel.last_active), ...sessions.map((session) => session.updated_at)];
    return source
      .map((value) => parseDateLike(value))
      .filter((value): value is Date => !!value)
      .sort((left, right) => right.getTime() - left.getTime())[0];
  }, [channels, sessions]);

  const fetchChannels = useCallback(async () => {
    const response = await fetch('/api/im/channels');
    if (!response.ok) {
      throw new Error(await readErrorMessage(response, '读取 IM 通道失败'));
    }
    const payload = (await parseResponse(response)) as { channels?: IMChannelSummary[] };
    return Array.isArray(payload.channels) ? payload.channels : [];
  }, []);

  const fetchSessions = useCallback(async (channelName: string) => {
    const response = await fetch(`/api/im/sessions?channel_name=${encodeURIComponent(channelName)}`);
    if (!response.ok) {
      throw new Error(await readErrorMessage(response, '读取 IM 会话失败'));
    }
    const payload = (await parseResponse(response)) as { sessions?: IMSessionSummary[] };
    return Array.isArray(payload.sessions) ? payload.sessions : [];
  }, []);

  const loadSessionMessages = useCallback(async (sessionId: string | null) => {
    setSelectedSessionId(sessionId);
    if (!sessionId) {
      setTimeline([]);
      return;
    }

    setMessageLoading(true);
    setErrorText('');
    try {
      const response = await fetch(`/api/sessions/${encodeURIComponent(sessionId)}`);
      if (!response.ok) {
        throw new Error(await readErrorMessage(response, '读取会话消息失败'));
      }
      const payload = (await parseResponse(response)) as SessionMessagePayload;
      setTimeline(buildImTimeline(Array.isArray(payload.messages) ? payload.messages : [], renderMarkdown));
    } catch (error) {
      setTimeline([]);
      setErrorText(error instanceof Error ? error.message : '读取会话消息失败');
    } finally {
      setMessageLoading(false);
    }
  }, []);

  const refreshOverview = useCallback(
    async (options?: { preferredChannel?: string | null; preferredSessionId?: string | null; preserveSelection?: boolean }) => {
      setRefreshing(true);
      setErrorText('');
      try {
        const nextChannels = await fetchChannels();
        setChannels(nextChannels);

        let nextChannel =
          options?.preferredChannel ?? (options?.preserveSelection ? selectedChannel : null);

        if (!nextChannel || !nextChannels.some((channel) => channel.channel_name === nextChannel)) {
          nextChannel = nextChannels[0]?.channel_name ?? null;
        }

        setSelectedChannel(nextChannel);

        if (!nextChannel) {
          setSessions([]);
          setSelectedSessionId(null);
          setTimeline([]);
          return;
        }

        const nextSessions = await fetchSessions(nextChannel);
        setSessions(nextSessions);

        let nextSessionId =
          options?.preferredSessionId ?? (options?.preserveSelection ? selectedSessionId : null);

        if (!nextSessionId || !nextSessions.some((session) => session.session_id === nextSessionId)) {
          nextSessionId = nextSessions[0]?.session_id ?? null;
        }

        await loadSessionMessages(nextSessionId);
      } catch (error) {
        setChannels([]);
        setSessions([]);
        setTimeline([]);
        setSelectedChannel(null);
        setSelectedSessionId(null);
        setErrorText(error instanceof Error ? error.message : '加载 IM 数据失败');
      } finally {
        setRefreshing(false);
      }
    },
    [fetchChannels, fetchSessions, loadSessionMessages, selectedChannel, selectedSessionId]
  );

  useEffect(() => {
    if (snapshot.currentView !== 'im') return;
    void refreshOverview({ preserveSelection: true });
  }, [refreshOverview, snapshot.currentView]);

  async function handleDeleteSession(sessionId: string) {
    if (!window.confirm('确定删除该 IM 会话记录吗？此操作无法撤销。')) return;

    setDeletingSessionId(sessionId);
    setErrorText('');
    try {
      const response = await fetch(`/api/sessions/${encodeURIComponent(sessionId)}`, { method: 'DELETE' });
      if (!response.ok) {
        throw new Error(await readErrorMessage(response, '删除 IM 会话失败'));
      }

      const remainingSessions = sessions.filter((session) => session.session_id !== sessionId);
      const nextSelectedSessionId =
        selectedSessionId === sessionId ? remainingSessions[0]?.session_id ?? null : selectedSessionId;

      await refreshOverview({
        preferredChannel: selectedChannel,
        preferredSessionId: nextSelectedSessionId,
        preserveSelection: false
      });
    } catch (error) {
      setErrorText(error instanceof Error ? error.message : '删除 IM 会话失败');
    } finally {
      setDeletingSessionId(null);
    }
  }

  function toggleThinking(entryId: string) {
    setTimeline((current) =>
      current.map((entry) => {
        if (entry.role !== 'assistant' || entry.id !== entryId) return entry;
        return {
          ...entry,
          _thinkCollapsed: !entry._thinkCollapsed
        };
      })
    );
  }

  function toggleToolBlock(entryId: string, blockId?: string) {
    if (!blockId) return;
    setTimeline((current) =>
      current.map((entry) => {
        if (entry.role !== 'assistant' || entry.id !== entryId) return entry;
        return {
          ...entry,
          blocks: entry.blocks.map((block) =>
            block.id === blockId
              ? {
                  ...block,
                  _collapsed: !block._collapsed
                }
              : block
          )
        };
      })
    );
  }

  return (
    <div className="im-view-shell custom-scrollbar">
      <header className="im-view-hero">
        <div>
          <div className="im-view-hero__eyebrow">IM Channel Monitor</div>
          <h2 className="im-view-hero__title">通道 / 会话 / 消息</h2>
          <p className="im-view-hero__meta">复用现有 IM 数据流，在主页面独立查看多通道会话记录。</p>
        </div>

        <div className="im-view-hero__actions">
          <UiStatusPill tone={onlineCount > 0 ? 'success' : 'neutral'}>{onlineCount} 在线</UiStatusPill>
          <UiStatusPill tone={offlineCount > 0 ? 'warning' : 'neutral'}>{offlineCount} 离线</UiStatusPill>
          <UiButton variant="secondary" onClick={() => void refreshOverview({ preserveSelection: true })} disabled={refreshing}>
            {refreshing ? '刷新中...' : '刷新'}
          </UiButton>
          <UiButton variant="ghost" onClick={() => dispatchShellAction({ type: 'openSettings', tab: 'integrations' })}>
            集成配置
          </UiButton>
        </div>
      </header>

      <div className="im-view-summary">
        <UiCard variant="subtle" className="im-view-summary__card">
          <span className="im-view-summary__label">通道数</span>
          <strong>{channels.length}</strong>
        </UiCard>
        <UiCard variant="subtle" className="im-view-summary__card">
          <span className="im-view-summary__label">会话数</span>
          <strong>{sessions.length}</strong>
        </UiCard>
        <UiCard variant="subtle" className="im-view-summary__card">
          <span className="im-view-summary__label">最近活跃</span>
          <strong>{latestActivity ? formatDateTime(latestActivity) : '暂无记录'}</strong>
        </UiCard>
      </div>

      {errorText ? <div className="im-view-error">{errorText}</div> : null}

      <div className="im-view-layout">
        <div className="im-view-sidebar">
          <UiCard variant="subtle" className="im-view-panel">
            <div className="im-view-panel__header">
              <div>
                <div className="im-view-panel__kicker">Channels</div>
                <h3 className="im-view-panel__title">IM 通道</h3>
              </div>
              <span className="im-view-panel__count">{channels.length}</span>
            </div>

            <div className="im-view-channel-list custom-scrollbar">
              {channels.length > 0 ? (
                channels.map((channel) => (
                  <button
                    key={channel.id}
                    type="button"
                    className={cn(
                      'im-view-channel',
                      selectedChannel === channel.channel_name && 'is-active'
                    )}
                    onClick={() => void refreshOverview({ preferredChannel: channel.channel_name })}
                  >
                    <div className="im-view-channel__row">
                      <strong>{getChannelLabel(channel)}</strong>
                      <UiStatusPill tone={channelTone(channel)}>{channel.status === 'online' ? '在线' : '离线'}</UiStatusPill>
                    </div>
                    <div className="im-view-channel__meta">
                      <span>{channel.platform}</span>
                      <span>{channel.session_count ?? 0} 会话</span>
                    </div>
                    <div className="im-view-channel__foot">
                      <span>{formatDateTime(channel.last_active)}</span>
                      {channel.last_error ? <span className="im-view-channel__error-badge">异常</span> : null}
                    </div>
                  </button>
                ))
              ) : (
                <div className="im-view-empty">
                  <strong>还没有 IM 通道</strong>
                  <p>先去集成配置中接入 Telegram、飞书或钉钉通道。</p>
                </div>
              )}
            </div>
          </UiCard>

          <UiCard variant="subtle" className="im-view-panel">
            <div className="im-view-panel__header">
              <div>
                <div className="im-view-panel__kicker">Sessions</div>
                <h3 className="im-view-panel__title">会话列表</h3>
              </div>
              <span className="im-view-panel__count">{sessions.length}</span>
            </div>

            <div className="im-view-session-list custom-scrollbar">
              {selectedChannel && sessions.length > 0 ? (
                sessions.map((session) => (
                  <button
                    key={session.session_id}
                    type="button"
                    className={cn(
                      'im-view-session',
                      selectedSessionId === session.session_id && 'is-active'
                    )}
                    onClick={() => void loadSessionMessages(session.session_id)}
                  >
                    <div className="im-view-session__row">
                      <strong>{getSessionLabel(session)}</strong>
                      <span>{session.message_count ?? 0}</span>
                    </div>
                    <p>{session.last_message || '媒体消息或空会话'}</p>
                    <div className="im-view-session__meta">
                      <span>{session.chat_id || '未知 chat_id'}</span>
                      <span>{formatDateTime(session.updated_at)}</span>
                    </div>
                  </button>
                ))
              ) : (
                <div className="im-view-empty">
                  <strong>{selectedChannel ? '当前通道暂无会话' : '先选择一个通道'}</strong>
                  <p>连接中的 IM 会话会在这里显示最近消息和活跃时间。</p>
                </div>
              )}
            </div>
          </UiCard>
        </div>

        <UiCard variant="elevated" className="im-view-thread">
          <div className="im-view-thread__header">
            <div className="im-view-thread__title-wrap">
              <div className="im-view-panel__kicker">Messages</div>
              <h3 className="im-view-thread__title">{selectedSession ? getSessionLabel(selectedSession) : '选择会话查看消息'}</h3>
              <div className="im-view-thread__meta">
                <span>{selectedSession?.channel_name || '未选择通道'}</span>
                {selectedSession?.response_mode ? <UiStatusPill tone="brand">{selectedSession.response_mode}</UiStatusPill> : null}
                <span>{selectedSession ? `${selectedSession.message_count ?? 0} 条消息` : '暂无消息'}</span>
              </div>
            </div>

            <div className="im-view-thread__actions">
              <UiButton
                variant="ghost"
                onClick={() => void loadSessionMessages(selectedSessionId)}
                disabled={!selectedSessionId || messageLoading}
              >
                {messageLoading ? '读取中...' : '刷新消息'}
              </UiButton>
              <UiButton
                variant="danger"
                onClick={() => (selectedSessionId ? void handleDeleteSession(selectedSessionId) : undefined)}
                disabled={!selectedSessionId || deletingSessionId === selectedSessionId}
              >
                {deletingSessionId === selectedSessionId ? '删除中...' : '删除会话'}
              </UiButton>
            </div>
          </div>

          <div className="im-view-thread__body custom-scrollbar">
            {!selectedSessionId ? (
              <div className="im-view-empty is-large">
                <strong>选择左侧会话后即可查看消息</strong>
                <p>这里会显示对应 IM 通道的完整消息时间线、工具调用结果和调试记录。</p>
              </div>
            ) : null}

            {selectedSessionId && messageLoading ? <div className="im-view-thread__loading">正在读取消息...</div> : null}

            {selectedSessionId && !messageLoading && timeline.length === 0 ? (
              <div className="im-view-empty is-large">
                <strong>当前会话没有可显示的消息</strong>
                <p>可能是空会话，或只有媒体消息尚未生成文本摘要。</p>
              </div>
            ) : null}

            {selectedSessionId && !messageLoading && timeline.length > 0
              ? timeline.map((entry, index) => {
                  const currentDate = formatDateLabel(entry.timestamp);
                  const previousDate = index > 0 ? formatDateLabel(timeline[index - 1].timestamp) : '';
                  const showDateDivider = currentDate && currentDate !== previousDate;

                  return (
                    <div key={entry.id}>
                      {showDateDivider ? (
                        <div className="im-view-date-divider">
                          <span>{currentDate}</span>
                        </div>
                      ) : null}

                      {entry.role === 'debug_log' ? (
                        <div className="im-view-debug">
                          <span className="im-view-debug__tag">{entry.debugType || 'debug'}</span>
                          <span className="im-view-debug__text">{entry.content}</span>
                          <span className="im-view-debug__time">{formatTime(entry.timestamp)}</span>
                        </div>
                      ) : null}

                      {entry.role === 'visual_log' ? (
                        <div className="chat-visual-log">
                          <span className="chat-visual-log-dot"></span>
                          <span className="md-body" dangerouslySetInnerHTML={{ __html: entry.html || '' }} />
                        </div>
                      ) : null}

                      {entry.role === 'user' ? (
                        <div className="im-view-timeline-row">
                          <div className="im-view-timeline-meta is-user">
                            <UiStatusPill tone="brand">用户</UiStatusPill>
                            <span>{formatTime(entry.timestamp)}</span>
                          </div>
                          <div className="chat-row chat-row-user">
                            <div className="chat-bubble-user">
                              <div className="md-body" dangerouslySetInnerHTML={{ __html: entry.html || '' }} />
                            </div>
                          </div>
                        </div>
                      ) : null}

                      {entry.role === 'assistant' ? (
                        <div className="im-view-timeline-row">
                          <div className="im-view-timeline-meta">
                            <UiStatusPill tone="success">机器人</UiStatusPill>
                            <span>{formatTime(entry.timestamp)}</span>
                          </div>
                          <div className="chat-row chat-row-assistant">
                            <div className="chat-assistant-body">
                              {entry.thinkingHtml ? (
                                <div className="chat-think-block">
                                  <div className="chat-think-header" onClick={() => toggleThinking(entry.id)}>
                                    <svg
                                      width="11"
                                      height="11"
                                      fill="none"
                                      stroke="var(--shell-accent)"
                                      viewBox="0 0 24 24"
                                      style={{
                                        transform: entry._thinkCollapsed ? 'rotate(-90deg)' : undefined,
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
                                  {!entry._thinkCollapsed ? (
                                    <div className="chat-think-body md-body font-mono">
                                      <div dangerouslySetInnerHTML={{ __html: entry.thinkingHtml }} />
                                    </div>
                                  ) : null}
                                </div>
                              ) : null}

                              <div className="chat-blocks">
                                {entry.blocks.map((block, blockIndex) => (
                                  <div key={block.id || `${entry.id}-${block.type}-${blockIndex}`}>
                                    {block.type === 'text' ? (
                                      <div className="chat-text-block md-body">
                                        <div dangerouslySetInnerHTML={{ __html: block.html || renderMarkdown(block.content || '') }} />
                                      </div>
                                    ) : null}

                                    {block.type === 'tool' ? (
                                      <div className="chat-tool-block">
                                        <div className="chat-tool-header" onClick={() => toggleToolBlock(entry.id, block.id)}>
                                          <div className="chat-tool-icon chat-tool-icon-done">✓</div>
                                          <span className="chat-tool-name">{block.name || 'tool'}</span>
                                          <span className="chat-tool-status chat-tool-status-done">完成</span>
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
                                            <div className="chat-tool-code chat-tool-params">{block.paramsStr || '{}'}</div>
                                            {block.resultStr ? (
                                              <div className="chat-tool-result-wrap">
                                                <div className="chat-tool-code chat-tool-result">{block.resultStr}</div>
                                              </div>
                                            ) : null}
                                          </div>
                                        ) : null}
                                      </div>
                                    ) : null}
                                  </div>
                                ))}
                              </div>
                            </div>
                          </div>
                        </div>
                      ) : null}
                    </div>
                  );
                })
              : null}
          </div>
        </UiCard>
      </div>
    </div>
  );
}

import { useEffect, useMemo, useState } from 'react';
import type { IMChannelSummary, IMSessionSummary } from '../bridge/openGuiclaw';
import { dispatchShellAction } from '../bridge/openGuiclaw';
import { UiButton } from './ui/UiButton';
import { UiCard } from './ui/UiCard';
import { UiStatusPill } from './ui/UiStatusPill';
import { useWorkspaceShellBridge } from '../hooks/useWorkspaceShellBridge';

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

function getChannelLabel(channel: IMChannelSummary) {
  return channel.display_name || channel.name || channel.platform || channel.channel_name;
}

export function ImOverviewCard() {
  const { snapshot } = useWorkspaceShellBridge();
  const [channels, setChannels] = useState<IMChannelSummary[]>([]);
  const [sessions, setSessions] = useState<IMSessionSummary[]>([]);
  const [loading, setLoading] = useState(false);
  const [errorText, setErrorText] = useState('');

  useEffect(() => {
    if (snapshot.currentView !== 'home') return;

    let cancelled = false;

    async function loadOverview() {
      setLoading(true);
      setErrorText('');
      try {
        const [channelsResponse, sessionsResponse] = await Promise.all([
          fetch('/api/im/channels'),
          fetch('/api/im/sessions')
        ]);

        if (cancelled) return;

        let nextError = '';

        if (channelsResponse.ok) {
          const payload = (await parseResponse(channelsResponse)) as { channels?: IMChannelSummary[] };
          setChannels(Array.isArray(payload.channels) ? payload.channels : []);
        } else {
          setChannels([]);
          nextError = await readErrorMessage(channelsResponse, '读取 IM 通道失败');
        }

        if (sessionsResponse.ok) {
          const payload = (await parseResponse(sessionsResponse)) as { sessions?: IMSessionSummary[] };
          setSessions(Array.isArray(payload.sessions) ? payload.sessions : []);
        } else {
          setSessions([]);
          nextError = nextError || (await readErrorMessage(sessionsResponse, '读取 IM 会话失败'));
        }

        setErrorText(nextError);
      } catch {
        if (!cancelled) {
          setChannels([]);
          setSessions([]);
          setErrorText('读取 IM 概览失败');
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    void loadOverview();
    return () => {
      cancelled = true;
    };
  }, [snapshot.currentView]);

  const onlineCount = channels.filter((channel) => channel.status === 'online').length;
  const latestActivity = useMemo(() => {
    return [...channels.map((channel) => channel.last_active), ...sessions.map((session) => session.updated_at)]
      .map((value) => parseDateLike(value))
      .filter((date): date is Date => !!date)
      .sort((left, right) => right.getTime() - left.getTime())[0];
  }, [channels, sessions]);

  return (
    <UiCard as="section" variant="subtle" className="home-im-card">
      <div className="home-im-card__head">
        <div>
          <div className="home-section-kicker">IM Channels</div>
          <h2>查看 IM 通道消息</h2>
          <p>直接进入通道消息视图，浏览在线状态、会话列表和最近消息。</p>
        </div>

        <div className="home-im-card__actions">
          <UiButton variant="primary" onClick={() => dispatchShellAction({ type: 'navigateView', view: 'im' })}>
            进入 IM
          </UiButton>
          <UiButton variant="ghost" onClick={() => dispatchShellAction({ type: 'openSettings', tab: 'integrations' })}>
            配置通道
          </UiButton>
        </div>
      </div>

      <div className="home-im-card__stats">
        <div className="home-im-card__stat">
          <span>在线通道</span>
          <strong>{onlineCount}</strong>
        </div>
        <div className="home-im-card__stat">
          <span>总会话</span>
          <strong>{sessions.length}</strong>
        </div>
        <div className="home-im-card__stat">
          <span>最近活跃</span>
          <strong>{latestActivity ? formatDateTime(latestActivity) : '暂无记录'}</strong>
        </div>
      </div>

      {errorText ? <div className="home-im-card__notice">{errorText}</div> : null}

      <div className="home-im-card__channels">
        {channels.length > 0 ? (
          channels.slice(0, 5).map((channel) => (
            <div key={channel.id} className="home-im-card__channel-pill">
              <span className={channel.status === 'online' ? 'is-online' : 'is-offline'}></span>
              <span>{getChannelLabel(channel)}</span>
              <UiStatusPill tone={channel.status === 'online' ? 'success' : 'neutral'}>
                {channel.session_count ?? 0}
              </UiStatusPill>
            </div>
          ))
        ) : (
          <div className="home-im-card__empty">
            {loading ? '正在读取 IM 通道状态...' : '还没有接入任何 IM 通道，去设置页完成 Telegram / 飞书 / 钉钉配置。'}
          </div>
        )}
      </div>
    </UiCard>
  );
}

import { useEffect, useState } from 'react';
import { emitShellUpdate } from '../bridge/openGuiclaw';
import { useWorkspaceShellBridge } from '../hooks/useWorkspaceShellBridge';

type ChannelsConfig = {
  telegram: {
    bot_token: string;
    proxy: string;
  };
  feishu: {
    app_id: string;
    app_secret: string;
  };
  dingtalk: {
    client_id: string;
    client_secret: string;
  };
};

type FullConfig = Record<string, unknown> & {
  channels?: Partial<ChannelsConfig>;
};

type ChannelKey = keyof ChannelsConfig;

type ChannelTestResult = {
  status?: string;
  error?: string;
};

type LoadState = {
  loading: boolean;
  errorText: string;
};

const EMPTY_CHANNELS: ChannelsConfig = {
  telegram: { bot_token: '', proxy: '' },
  feishu: { app_id: '', app_secret: '' },
  dingtalk: { client_id: '', client_secret: '' }
};

async function parseResponse(response: Response) {
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
    // Ignore parse failures and use fallback below.
  }
  return fallback;
}

function normalizeChannelsConfig(input: Partial<ChannelsConfig> | undefined): ChannelsConfig {
  return {
    telegram: {
      bot_token: input?.telegram?.bot_token || '',
      proxy: input?.telegram?.proxy || ''
    },
    feishu: {
      app_id: input?.feishu?.app_id || '',
      app_secret: input?.feishu?.app_secret || ''
    },
    dingtalk: {
      client_id: input?.dingtalk?.client_id || '',
      client_secret: input?.dingtalk?.client_secret || ''
    }
  };
}

export function IntegrationsPanel() {
  const { snapshot } = useWorkspaceShellBridge();
  const [fullConfig, setFullConfig] = useState<FullConfig | null>(null);
  const [channels, setChannels] = useState<ChannelsConfig>(EMPTY_CHANNELS);
  const [loadState, setLoadState] = useState<LoadState>({ loading: true, errorText: '' });
  const [saving, setSaving] = useState(false);
  const [statusText, setStatusText] = useState('');
  const [testingChannel, setTestingChannel] = useState<ChannelKey | null>(null);
  const [channelResults, setChannelResults] = useState<Record<string, ChannelTestResult | null>>({});
  const [showDingtalkSecret, setShowDingtalkSecret] = useState(false);

  useEffect(() => {
    if (!snapshot.showSettings || snapshot.settingsTab !== 'integrations') return;
    void loadConfig();
  }, [snapshot.showSettings, snapshot.settingsTab]);

  function pushStatus(message: string) {
    setStatusText(message);
    window.clearTimeout((pushStatus as typeof pushStatus & { timer?: number }).timer);
    (pushStatus as typeof pushStatus & { timer?: number }).timer = window.setTimeout(() => {
      setStatusText('');
    }, 3200);
  }

  async function loadConfig() {
    setLoadState({ loading: true, errorText: '' });
    try {
      const response = await fetch('/api/config');
      if (!response.ok) {
        throw new Error(await readErrorMessage(response, '加载集成配置失败'));
      }

      const payload = (await parseResponse(response)) as FullConfig;
      const nextChannels = normalizeChannelsConfig(payload.channels);

      setFullConfig(payload);
      setChannels(nextChannels);
      setLoadState({ loading: false, errorText: '' });
      emitShellUpdate();
    } catch (error) {
      setLoadState({
        loading: false,
        errorText: error instanceof Error ? error.message : '加载集成配置失败'
      });
    }
  }

  function updateChannel<K extends ChannelKey, F extends keyof ChannelsConfig[K]>(
    channelKey: K,
    field: F,
    value: ChannelsConfig[K][F]
  ) {
    setChannels((current) => ({
      ...current,
      [channelKey]: {
        ...current[channelKey],
        [field]: value
      }
    }));
  }

  async function saveChannels() {
    if (!fullConfig) {
      pushStatus('配置尚未加载完成');
      return;
    }

    setSaving(true);
    try {
      const response = await fetch('/api/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ...fullConfig,
          channels
        })
      });

      if (!response.ok) {
        throw new Error(await readErrorMessage(response, '保存集成配置失败'));
      }

      pushStatus('集成配置已保存');
      await loadConfig();
    } catch (error) {
      pushStatus(error instanceof Error ? error.message : '保存集成配置失败');
    } finally {
      setSaving(false);
    }
  }

  async function testChannel(channel: ChannelKey) {
    setTestingChannel(channel);
    setChannelResults((current) => ({ ...current, [channel]: null }));
    try {
      const response = await fetch('/api/config/channels/health', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          channel,
          config: channels
        })
      });

      if (!response.ok) {
        throw new Error(await readErrorMessage(response, `${channel} 测活失败`));
      }

      const payload = await parseResponse(response);
      const result =
        payload && typeof payload === 'object' && 'results' in payload && Array.isArray(payload.results)
          ? (payload.results[0] as ChannelTestResult | undefined)
          : null;

      setChannelResults((current) => ({
        ...current,
        [channel]: result || { status: 'healthy' }
      }));
    } catch (error) {
      setChannelResults((current) => ({
        ...current,
        [channel]: {
          status: 'unhealthy',
          error: error instanceof Error ? error.message : '网络请求失败'
        }
      }));
    } finally {
      setTestingChannel(null);
    }
  }

  function renderHealth(channel: ChannelKey) {
    const result = channelResults[channel];
    if (!result) return null;

    const isHealthy = result.status === 'healthy';
    return (
      <div className={`integrations-panel__notice ${isHealthy ? 'integrations-panel__notice--healthy' : 'integrations-panel__notice--error'}`}>
        {isHealthy ? '✓ 验证成功' : `✗ ${result.error || '连接异常'}`}
      </div>
    );
  }

  return (
    <div className="integrations-panel">
      <header className="integrations-panel__header">
        <div>
          <div className="integrations-panel__eyebrow">IM Channels</div>
          <h4 className="integrations-panel__title">即时通讯通道配置</h4>
          <p className="integrations-panel__meta">配置 Telegram、飞书、钉钉等平台的接入凭证，并在保存前直接测活。</p>
        </div>
        <div className="integrations-panel__toolbar">
          <button type="button" className="integrations-panel__ghost-btn" onClick={loadConfig} disabled={loadState.loading}>
            刷新
          </button>
          <button type="button" className="integrations-panel__accent-btn" onClick={saveChannels} disabled={saving || loadState.loading}>
            {saving ? '保存中...' : '保存所有配置'}
          </button>
        </div>
      </header>

      {loadState.errorText ? <div className="integrations-panel__notice integrations-panel__notice--error">{loadState.errorText}</div> : null}
      {loadState.loading ? <div className="integrations-panel__empty">正在加载集成配置...</div> : null}

      {!loadState.loading ? (
        <div className="integrations-panel__grid">
          <article className="integrations-panel__card integrations-panel__card--telegram">
            <div className="integrations-panel__card-head">
              <div className="integrations-panel__icon is-telegram">
                <svg className="integrations-panel__icon-svg" fill="currentColor" viewBox="0 0 24 24">
                  <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm4.64 6.8c-.15 1.58-.8 5.42-1.13 7.19-.14.75-.42 1-.68 1.03-.58.05-1.02-.38-1.58-.75-.88-.58-1.38-.94-2.23-1.5-.99-.65-.35-1.01.22-1.59.15-.15 2.71-2.48 2.76-2.69.01-.03.01-.14-.07-.18-.08-.05-.19-.02-.27 0-.11.03-1.84 1.18-5.22 3.46-.49.34-.94.5-1.35.49-.45-.01-1.32-.26-1.96-.46-.79-.26-1.42-.39-1.36-.83.03-.22.34-.44.93-.68 3.65-1.59 6.08-2.64 7.29-3.14 3.47-1.45 4.19-1.7 4.66-1.71.1 0 .34.02.49.13.13.1.17.24.19.34.01.05.02.16.02.24z" />
                </svg>
              </div>
              <div>
                <h5 className="integrations-panel__card-title">Telegram</h5>
                <p className="integrations-panel__card-desc">电报机器人接入</p>
              </div>
            </div>

            <div className="integrations-panel__field-stack">
              <label className="integrations-panel__field">
                <span className="integrations-panel__field-heading">
                  <span className="integrations-panel__field-title">Bot Token</span>
                  <span className="integrations-panel__field-key">TELEGRAM_BOT_TOKEN</span>
                </span>
                <input
                  type="password"
                  className="integrations-panel__input integrations-panel__input--mono"
                  placeholder="123456:ABC-DEF1234..."
                  value={channels.telegram.bot_token}
                  onChange={(event) => updateChannel('telegram', 'bot_token', event.target.value)}
                />
              </label>

              <label className="integrations-panel__field">
                <span className="integrations-panel__field-heading">
                  <span className="integrations-panel__field-title">Proxy URL</span>
                  <span className="integrations-panel__field-key">TELEGRAM_PROXY</span>
                </span>
                <input
                  type="text"
                  className="integrations-panel__input integrations-panel__input--mono"
                  placeholder="http://127.0.0.1:7890"
                  value={channels.telegram.proxy}
                  onChange={(event) => updateChannel('telegram', 'proxy', event.target.value)}
                />
              </label>
            </div>

            <div className="integrations-panel__card-actions">
              <button type="button" className="integrations-panel__soft-btn is-telegram" onClick={() => testChannel('telegram')} disabled={testingChannel === 'telegram'}>
                {testingChannel === 'telegram' ? '检测中...' : '网络测活'}
              </button>
            </div>
            {renderHealth('telegram')}
          </article>

          <article className="integrations-panel__card integrations-panel__card--feishu">
            <div className="integrations-panel__card-head">
              <div className="integrations-panel__icon is-feishu">飞</div>
              <div>
                <h5 className="integrations-panel__card-title">Feishu / Lark</h5>
                <p className="integrations-panel__card-desc">飞书自建应用接入</p>
              </div>
            </div>

            <div className="integrations-panel__field-stack">
              <label className="integrations-panel__field">
                <span className="integrations-panel__field-heading">
                  <span className="integrations-panel__field-title">App ID</span>
                  <span className="integrations-panel__field-key">FEISHU_APP_ID</span>
                </span>
                <input
                  type="text"
                  className="integrations-panel__input integrations-panel__input--mono"
                  placeholder="cli_..."
                  value={channels.feishu.app_id}
                  onChange={(event) => updateChannel('feishu', 'app_id', event.target.value)}
                />
              </label>

              <label className="integrations-panel__field">
                <span className="integrations-panel__field-heading">
                  <span className="integrations-panel__field-title">App Secret</span>
                  <span className="integrations-panel__field-key">FEISHU_APP_SECRET</span>
                </span>
                <input
                  type="password"
                  className="integrations-panel__input integrations-panel__input--mono"
                  placeholder="Secret"
                  value={channels.feishu.app_secret}
                  onChange={(event) => updateChannel('feishu', 'app_secret', event.target.value)}
                />
              </label>
            </div>

            <div className="integrations-panel__card-actions">
              <button type="button" className="integrations-panel__soft-btn is-feishu" onClick={() => testChannel('feishu')} disabled={testingChannel === 'feishu'}>
                {testingChannel === 'feishu' ? '检测中...' : '网络测活'}
              </button>
            </div>
            {renderHealth('feishu')}
          </article>

          <article className="integrations-panel__card integrations-panel__card--dingtalk">
            <div className="integrations-panel__card-head">
              <div className="integrations-panel__icon is-dingtalk">D</div>
              <div>
                <h5 className="integrations-panel__card-title">DingTalk</h5>
                <p className="integrations-panel__card-desc">钉钉企业内部机器人接入</p>
              </div>
            </div>

            <div className="integrations-panel__field-stack">
              <label className="integrations-panel__field">
                <span className="integrations-panel__field-heading">
                  <span className="integrations-panel__field-title">Client ID</span>
                  <span className="integrations-panel__field-key">DINGTALK_CLIENT_ID</span>
                </span>
                <input
                  type="text"
                  className="integrations-panel__input integrations-panel__input--mono"
                  placeholder="ding..."
                  value={channels.dingtalk.client_id}
                  onChange={(event) => updateChannel('dingtalk', 'client_id', event.target.value)}
                />
              </label>

              <label className="integrations-panel__field">
                <span className="integrations-panel__field-heading">
                  <span className="integrations-panel__field-title">Client Secret</span>
                  <span className="integrations-panel__field-key">DINGTALK_CLIENT_SECRET</span>
                </span>
                <span className="integrations-panel__secret-wrap">
                  <input
                    type={showDingtalkSecret ? 'text' : 'password'}
                    className="integrations-panel__input integrations-panel__input--mono integrations-panel__input--secret"
                    placeholder="Secret"
                    value={channels.dingtalk.client_secret}
                    onChange={(event) => updateChannel('dingtalk', 'client_secret', event.target.value)}
                  />
                  <button
                    type="button"
                    className="integrations-panel__visibility-btn"
                    onClick={() => setShowDingtalkSecret((current) => !current)}
                    aria-label={showDingtalkSecret ? '隐藏 Client Secret' : '显示 Client Secret'}
                    aria-pressed={showDingtalkSecret}
                  >
                    <svg className="integrations-panel__visibility-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      {showDingtalkSecret ? (
                        <>
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.8" d="M3 3l18 18" />
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.8" d="M10.58 10.58A3 3 0 0012 15a3 3 0 002.42-1.22" />
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.8" d="M9.88 5.09A9.77 9.77 0 0112 4.8c4.5 0 8.27 2.94 9.54 7.2a10.66 10.66 0 01-2.95 4.6M6.1 6.11A10.73 10.73 0 002.46 12c1.27 4.26 5.04 7.2 9.54 7.2 1.68 0 3.27-.41 4.68-1.13" />
                        </>
                      ) : (
                        <>
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.8" d="M2.46 12C3.73 7.74 7.5 4.8 12 4.8s8.27 2.94 9.54 7.2c-1.27 4.26-5.04 7.2-9.54 7.2S3.73 16.26 2.46 12z" />
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.8" d="M12 15a3 3 0 100-6 3 3 0 000 6z" />
                        </>
                      )}
                    </svg>
                  </button>
                </span>
              </label>
            </div>

            <div className="integrations-panel__card-actions">
              <button type="button" className="integrations-panel__soft-btn is-dingtalk" onClick={() => testChannel('dingtalk')} disabled={testingChannel === 'dingtalk'}>
                {testingChannel === 'dingtalk' ? '检测中...' : '网络测活'}
              </button>
            </div>
            {renderHealth('dingtalk')}
          </article>
        </div>
      ) : null}

      {statusText ? <div className="integrations-panel__notice integrations-panel__notice--status">{statusText}</div> : null}
    </div>
  );
}

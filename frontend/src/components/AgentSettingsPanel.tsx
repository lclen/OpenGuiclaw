import { useEffect, useState } from 'react';
import { emitShellUpdate, getHostApp } from '../bridge/openGuiclaw';
import { useWorkspaceShellBridge } from '../hooks/useWorkspaceShellBridge';

type ProactiveConfig = {
  interval_minutes: number | null;
  cooldown_minutes: number | null;
  verbose: boolean;
  mode: 'silent' | 'normal' | 'lively' | string;
};

type JournalConfig = {
  enable_diary: boolean;
  vrm_enabled?: boolean;
};

type GlobalConfig = {
  proactive: ProactiveConfig;
  journal: JournalConfig;
  channels?: Record<string, unknown>;
};

type PreferencesPayload = {
  browser_choice?: 'edge' | 'chrome' | string;
};

type LoadState = {
  loading: boolean;
  errorText: string;
};

const DEFAULT_CONFIG: GlobalConfig = {
  proactive: { interval_minutes: null, cooldown_minutes: null, verbose: true, mode: 'silent' },
  journal: { enable_diary: false, vrm_enabled: false },
  channels: {}
};

const PROACTIVE_PRESETS: Record<'silent' | 'normal' | 'lively', { interval_minutes: number | null; cooldown_minutes: number | null }> = {
  silent: { interval_minutes: null, cooldown_minutes: null },
  normal: { interval_minutes: 5, cooldown_minutes: 15 },
  lively: { interval_minutes: 5, cooldown_minutes: 1 }
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
    // Ignore parse failures.
  }
  return fallback;
}

function normalizeConfig(payload: unknown): GlobalConfig {
  const source = payload && typeof payload === 'object' ? (payload as Partial<GlobalConfig>) : {};
  const journal = source.journal && typeof source.journal === 'object' ? source.journal : {};
  const proactive = source.proactive && typeof source.proactive === 'object' ? source.proactive : {};
  return {
    ...DEFAULT_CONFIG,
    ...source,
    proactive: {
      ...DEFAULT_CONFIG.proactive,
      ...proactive
    },
    journal: {
      ...DEFAULT_CONFIG.journal,
      ...journal
    }
  };
}

function syncHostApp(config: GlobalConfig, browserChoice: string, vrmEnabled: boolean) {
  const app = getHostApp();
  if (!app) return;

  app.vrmSystemEnabled = vrmEnabled;
  app.config = {
    ...(app.config || {}),
    browser_choice: browserChoice,
    proactive: { ...(config.proactive || {}) },
    journal: { ...(config.journal || {}) },
    channels: { ...(config.channels || {}) }
  };

  emitShellUpdate();
}

function formatMinutes(value: number | null | undefined) {
  if (value == null) return 'OFF';
  return `${value}m`;
}

export function AgentSettingsPanel() {
  const { snapshot } = useWorkspaceShellBridge();
  const [loadState, setLoadState] = useState<LoadState>({ loading: true, errorText: '' });
  const [fullConfig, setFullConfig] = useState<GlobalConfig>(DEFAULT_CONFIG);
  const [browserChoice, setBrowserChoice] = useState<'edge' | 'chrome'>('edge');
  const [vrmEnabled, setVrmEnabled] = useState(false);
  const [savingSection, setSavingSection] = useState<string>('');
  const [statusText, setStatusText] = useState('');

  useEffect(() => {
    if (!snapshot.showSettings || snapshot.settingsTab !== 'agent') return;
    void loadAll();
  }, [snapshot.showSettings, snapshot.settingsTab]);

  function pushStatus(message: string) {
    setStatusText(message);
    window.clearTimeout((pushStatus as typeof pushStatus & { timer?: number }).timer);
    (pushStatus as typeof pushStatus & { timer?: number }).timer = window.setTimeout(() => {
      setStatusText('');
    }, 3200);
  }

  async function loadAll() {
    setLoadState({ loading: true, errorText: '' });
    try {
      const [configResponse, preferenceResponse] = await Promise.all([
        fetch('/api/config'),
        fetch('/api/config/preferences')
      ]);

      if (!configResponse.ok) {
        throw new Error(await readErrorMessage(configResponse, '加载 Agent 设置失败'));
      }

      const configPayload = normalizeConfig(await parseResponse(configResponse));
      const preferencePayload = preferenceResponse.ok
        ? ((await parseResponse(preferenceResponse)) as PreferencesPayload)
        : {};

      const nextBrowserChoice = preferencePayload.browser_choice === 'chrome' ? 'chrome' : 'edge';
      const nextVrmEnabled = !!configPayload.journal.vrm_enabled;

      setFullConfig(configPayload);
      setBrowserChoice(nextBrowserChoice);
      setVrmEnabled(nextVrmEnabled);
      syncHostApp(configPayload, nextBrowserChoice, nextVrmEnabled);
      localStorage.setItem('vrmSystemEnabled', String(nextVrmEnabled));
      setLoadState({ loading: false, errorText: '' });
    } catch (error) {
      setLoadState({
        loading: false,
        errorText: error instanceof Error ? error.message : '加载 Agent 设置失败'
      });
    }
  }

  async function saveConfig(nextConfig: GlobalConfig, sectionLabel: string) {
    setSavingSection(sectionLabel);
    try {
      const response = await fetch('/api/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(nextConfig)
      });

      if (!response.ok) {
        throw new Error(await readErrorMessage(response, '保存 Agent 设置失败'));
      }

      setFullConfig(nextConfig);
      syncHostApp(nextConfig, browserChoice, vrmEnabled);
      pushStatus(`${sectionLabel}已保存`);
    } catch (error) {
      pushStatus(error instanceof Error ? error.message : '保存 Agent 设置失败');
    } finally {
      setSavingSection('');
    }
  }

  async function handleVrmToggle(nextValue: boolean) {
    const hostApp = getHostApp();
    setVrmEnabled(nextValue);
    localStorage.setItem('vrmSystemEnabled', String(nextValue));
    if (nextValue) {
      localStorage.setItem('showVrm', 'true');
      hostApp?.toggleVrmSystem?.(true);
      if (!hostApp?.showVrm) {
        hostApp?.toggleVrm?.();
      }
    } else {
      localStorage.setItem('showVrm', 'false');
      hostApp?.toggleVrmSystem?.(false);
    }

    const nextConfig: GlobalConfig = {
      ...fullConfig,
      journal: {
        ...fullConfig.journal,
        vrm_enabled: nextValue
      }
    };

    syncHostApp(nextConfig, browserChoice, nextValue);
    await saveConfig(nextConfig, 'VRM 设置');
    window.setTimeout(() => window.dispatchEvent(new Event('resize')), 520);
  }

  async function handleDiaryToggle(nextValue: boolean) {
    const nextConfig: GlobalConfig = {
      ...fullConfig,
      journal: {
        ...fullConfig.journal,
        enable_diary: nextValue
      }
    };

    setFullConfig(nextConfig);
    syncHostApp(nextConfig, browserChoice, vrmEnabled);
    await saveConfig(nextConfig, '日记设置');
  }

  async function handleBrowserChoice(nextChoice: 'edge' | 'chrome') {
    setSavingSection('浏览器设置');
    setBrowserChoice(nextChoice);
    syncHostApp(fullConfig, nextChoice, vrmEnabled);

    try {
      const response = await fetch('/api/config/preferences', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ browser_choice: nextChoice })
      });

      if (!response.ok) {
        throw new Error(await readErrorMessage(response, '保存浏览器设置失败'));
      }

      pushStatus(`默认浏览器已切换为 ${nextChoice === 'edge' ? 'Microsoft Edge' : 'Google Chrome'}`);
    } catch (error) {
      pushStatus(error instanceof Error ? error.message : '保存浏览器设置失败');
    } finally {
      setSavingSection('');
    }
  }

  async function handleProactiveValue<K extends keyof ProactiveConfig>(key: K, value: ProactiveConfig[K], sectionLabel: string) {
    const nextConfig: GlobalConfig = {
      ...fullConfig,
      proactive: {
        ...fullConfig.proactive,
        [key]: value
      }
    };

    setFullConfig(nextConfig);
    syncHostApp(nextConfig, browserChoice, vrmEnabled);
    await saveConfig(nextConfig, sectionLabel);
  }

  async function handleProactivePreset(mode: 'silent' | 'normal' | 'lively') {
    const preset = PROACTIVE_PRESETS[mode];
    const nextConfig: GlobalConfig = {
      ...fullConfig,
      proactive: {
        ...fullConfig.proactive,
        mode,
        interval_minutes: preset.interval_minutes,
        cooldown_minutes: preset.cooldown_minutes
      }
    };

    setFullConfig(nextConfig);
    syncHostApp(nextConfig, browserChoice, vrmEnabled);
    await saveConfig(nextConfig, '主动感知预设');
  }

  return (
    <div className="agent-settings-panel">
      {loadState.errorText ? <div className="agent-settings-panel__notice agent-settings-panel__notice--error">{loadState.errorText}</div> : null}
      {loadState.loading ? <div className="agent-settings-panel__empty">正在加载 Agent 设置...</div> : null}

      {!loadState.loading ? (
        <>
          <section className="agent-settings-panel__section">
            <div className="agent-settings-panel__section-head">
              <div className="agent-settings-panel__icon is-purple">3D</div>
              <div>
                <h4>3D 虚拟形象</h4>
                <p>控制右侧 VRM 模型的显示与隐藏。</p>
              </div>
            </div>
            <article className="agent-settings-panel__toggle-card is-purple">
              <div>
                <div className="agent-settings-panel__card-title">显示 VRM 形象</div>
                <div className="agent-settings-panel__card-desc">关闭后聊天区域会自动扩展填满屏幕。</div>
              </div>
              <label className="agent-settings-panel__switch">
                <input
                  type="checkbox"
                  checked={vrmEnabled}
                  onChange={(event) => {
                    void handleVrmToggle(event.target.checked);
                  }}
                />
                <span />
              </label>
            </article>
          </section>

          <section className="agent-settings-panel__section">
            <div className="agent-settings-panel__section-head">
              <div className="agent-settings-panel__icon is-amber">日</div>
              <div>
                <h4>认知日志 (Diary)</h4>
                <p>每日根据对话自动生成 AI 第一人称日记。</p>
              </div>
            </div>
            <article className="agent-settings-panel__toggle-card is-amber">
              <div>
                <div className="agent-settings-panel__card-title">开启日记自动生成</div>
                <div className="agent-settings-panel__card-desc">关闭后记忆进化与知识图谱仍会继续运行，仅跳过日记写入。</div>
              </div>
              <label className="agent-settings-panel__switch">
                <input
                  type="checkbox"
                  checked={!!fullConfig.journal.enable_diary}
                  onChange={(event) => {
                    void handleDiaryToggle(event.target.checked);
                  }}
                />
                <span />
              </label>
            </article>
          </section>

          <section className="agent-settings-panel__section">
            <div className="agent-settings-panel__section-head">
              <div className="agent-settings-panel__icon is-green">浏</div>
              <div>
                <h4>浏览器执行环境</h4>
                <p>指定自动化与 UI 执行时的默认浏览器内核。</p>
              </div>
            </div>
            <div className="agent-settings-panel__choice-row">
              <button
                type="button"
                className={`agent-settings-panel__choice-btn${browserChoice === 'edge' ? ' is-active' : ''}`}
                onClick={() => {
                  void handleBrowserChoice('edge');
                }}
              >
                <span className="agent-settings-panel__choice-emoji">🌐</span>
                <span>Edge</span>
              </button>
              <button
                type="button"
                className={`agent-settings-panel__choice-btn${browserChoice === 'chrome' ? ' is-active' : ''}`}
                onClick={() => {
                  void handleBrowserChoice('chrome');
                }}
              >
                <span className="agent-settings-panel__choice-emoji">🔥</span>
                <span>Chrome</span>
              </button>
            </div>
          </section>

          <section className="agent-settings-panel__section">
            <div className="agent-settings-panel__section-head">
              <div className="agent-settings-panel__icon is-orange">AI</div>
              <div>
                <h4>主动感知逻辑</h4>
                <p>调整内核心跳检测与互动频次。</p>
              </div>
            </div>

            <div className="agent-settings-panel__metrics-grid">
              <article className="agent-settings-panel__metric-card">
                <div className="agent-settings-panel__metric-top">
                  <div>
                    <div className="agent-settings-panel__metric-title">视觉捕获频率</div>
                    <div className="agent-settings-panel__metric-code">VISION TICK</div>
                  </div>
                  <strong>{formatMinutes(fullConfig.proactive.interval_minutes)}</strong>
                </div>
                <input
                  type="range"
                  min="1"
                  max="60"
                  step="1"
                  value={fullConfig.proactive.interval_minutes ?? 1}
                  onChange={(event) => {
                    void handleProactiveValue('interval_minutes', Number(event.target.value), '视觉捕获频率');
                  }}
                />
              </article>

              <article className="agent-settings-panel__metric-card">
                <div className="agent-settings-panel__metric-top">
                  <div>
                    <div className="agent-settings-panel__metric-title">互动冷却期</div>
                    <div className="agent-settings-panel__metric-code">COOLING</div>
                  </div>
                  <strong>{formatMinutes(fullConfig.proactive.cooldown_minutes)}</strong>
                </div>
                <input
                  type="range"
                  min="1"
                  max="60"
                  step="1"
                  value={fullConfig.proactive.cooldown_minutes ?? 1}
                  onChange={(event) => {
                    void handleProactiveValue('cooldown_minutes', Number(event.target.value), '互动冷却期');
                  }}
                />
              </article>
            </div>

            <div className="agent-settings-panel__preset-wrap">
              <div className="agent-settings-panel__preset-label">响应预设方案</div>
              <div className="agent-settings-panel__preset-row">
                {(['silent', 'normal', 'lively'] as const).map((mode) => (
                  <button
                    key={mode}
                    type="button"
                    className={`agent-settings-panel__preset-btn${fullConfig.proactive.mode === mode ? ' is-active' : ''}`}
                    onClick={() => {
                      void handleProactivePreset(mode);
                    }}
                  >
                    {mode === 'silent' ? '静默运行' : mode === 'normal' ? '平衡' : '主动'}
                  </button>
                ))}
              </div>
            </div>

            <article className="agent-settings-panel__toggle-card is-blue">
              <div>
                <div className="agent-settings-panel__card-title">后端感知日志展现 (Verbose)</div>
                <div className="agent-settings-panel__card-desc">在界面中渲染后端分析决策原始数据。</div>
              </div>
              <label className="agent-settings-panel__switch">
                <input
                  type="checkbox"
                  checked={!!fullConfig.proactive.verbose}
                  onChange={(event) => {
                    void handleProactiveValue('verbose', event.target.checked, 'Verbose 设置');
                  }}
                />
                <span />
              </label>
            </article>
          </section>
        </>
      ) : null}

      {savingSection ? <div className="agent-settings-panel__notice agent-settings-panel__notice--status">正在保存{savingSection}...</div> : null}
      {statusText ? <div className="agent-settings-panel__notice agent-settings-panel__notice--status">{statusText}</div> : null}
    </div>
  );
}

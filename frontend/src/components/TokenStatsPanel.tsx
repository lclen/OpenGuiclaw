import { useEffect, useMemo, useState } from 'react';
import { emitShellUpdate } from '../bridge/openGuiclaw';
import { useWorkspaceShellBridge } from '../hooks/useWorkspaceShellBridge';

type TokenPeriod = '1d' | '3d' | '1w' | '1m' | '6m' | '1y' | 'all';

type TokenStats = {
  period?: string;
  total_prompt_tokens: number;
  total_completion_tokens: number;
  total_tokens: number;
  request_count: number;
  by_model: Record<string, { prompt: number; completion: number; total: number; count: number }>;
  timeline: Array<{ time: string; prompt: number; completion: number; total: number }>;
};

type LoadState = {
  loading: boolean;
  errorText: string;
};

const PERIOD_OPTIONS: Array<{ key: TokenPeriod; label: string }> = [
  { key: '1d', label: '一天' },
  { key: '3d', label: '三天' },
  { key: '1w', label: '一周' },
  { key: '1m', label: '一月' },
  { key: '6m', label: '半年' },
  { key: '1y', label: '一年' },
  { key: 'all', label: '全部' }
];

const EMPTY_STATS: TokenStats = {
  total_prompt_tokens: 0,
  total_completion_tokens: 0,
  total_tokens: 0,
  request_count: 0,
  by_model: {},
  timeline: []
};

function formatNum(value: number | null | undefined) {
  if (value == null) return '—';
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`;
  if (value >= 1_000) return `${(value / 1_000).toFixed(1)}K`;
  return String(value);
}

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
    // Ignore parse failures and use fallback.
  }
  return fallback;
}

export function TokenStatsPanel() {
  const { snapshot } = useWorkspaceShellBridge();
  const [period, setPeriod] = useState<TokenPeriod>('1d');
  const [stats, setStats] = useState<TokenStats>(EMPTY_STATS);
  const [loadState, setLoadState] = useState<LoadState>({ loading: true, errorText: '' });
  const [resetting, setResetting] = useState(false);
  const [statusText, setStatusText] = useState('');

  const timelineMax = useMemo(
    () => Math.max(1, ...stats.timeline.map((item) => Number(item.total) || 0)),
    [stats.timeline]
  );

  const modelEntries = useMemo(
    () =>
      Object.entries(stats.by_model || {}).sort((left, right) => {
        return (right[1]?.total || 0) - (left[1]?.total || 0);
      }),
    [stats.by_model]
  );

  useEffect(() => {
    if (!snapshot.showSettings || snapshot.settingsTab !== 'tokens') return;
    void loadStats(period);
  }, [snapshot.showSettings, snapshot.settingsTab]);

  function pushStatus(message: string) {
    setStatusText(message);
    window.clearTimeout((pushStatus as typeof pushStatus & { timer?: number }).timer);
    (pushStatus as typeof pushStatus & { timer?: number }).timer = window.setTimeout(() => {
      setStatusText('');
    }, 3200);
  }

  async function loadStats(nextPeriod: TokenPeriod) {
    setLoadState({ loading: true, errorText: '' });
    try {
      const response = await fetch(`/api/token-stats?period=${encodeURIComponent(nextPeriod)}`);
      if (!response.ok) {
        throw new Error(await readErrorMessage(response, '加载 Token 统计失败'));
      }
      const payload = await parseResponse(response);
      setStats({ ...EMPTY_STATS, ...(payload as Partial<TokenStats>) });
      setLoadState({ loading: false, errorText: '' });
      emitShellUpdate();
    } catch (error) {
      setStats(EMPTY_STATS);
      setLoadState({
        loading: false,
        errorText: error instanceof Error ? error.message : '加载 Token 统计失败'
      });
    }
  }

  async function handlePeriodChange(nextPeriod: TokenPeriod) {
    setPeriod(nextPeriod);
    await loadStats(nextPeriod);
  }

  async function handleReset() {
    const confirmed = window.confirm('确定要重置 Token 统计数据吗？');
    if (!confirmed) return;

    setResetting(true);
    try {
      const response = await fetch('/api/token-stats/reset', { method: 'POST' });
      if (!response.ok) {
        throw new Error(await readErrorMessage(response, '重置 Token 统计失败'));
      }
      pushStatus('Token 统计已重置');
      await loadStats(period);
    } catch (error) {
      pushStatus(error instanceof Error ? error.message : '重置 Token 统计失败');
    } finally {
      setResetting(false);
    }
  }

  const promptRatio = stats.total_tokens > 0 ? Math.round((stats.total_prompt_tokens / stats.total_tokens) * 100) : 0;
  const completionRatio = stats.total_tokens > 0 ? Math.round((stats.total_completion_tokens / stats.total_tokens) * 100) : 0;

  return (
    <div className="token-react-panel">
      <header className="token-react-panel__header">
        <div className="token-react-panel__hero">
          <div className="token-react-panel__icon-wrap">
            <svg className="token-react-panel__icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13 10V3L4 14h7v7l9-11h-7z" />
            </svg>
          </div>
          <div>
            <div className="token-react-panel__eyebrow">Token Stats</div>
            <h4 className="token-react-panel__title">Token 统计面板</h4>
            <p className="token-react-panel__meta">实时追踪请求频次、输入输出 token 配比和模型使用分布。</p>
          </div>
        </div>

        <div className="token-react-panel__header-actions">
          <button type="button" className="token-react-panel__ghost-btn" onClick={() => loadStats(period)} disabled={loadState.loading}>
            刷新
          </button>
          <button type="button" className="token-react-panel__danger-btn" onClick={handleReset} disabled={resetting}>
            {resetting ? '重置中...' : '清空统计'}
          </button>
        </div>
      </header>

      <div className="token-react-panel__periods">
        {PERIOD_OPTIONS.map((option) => (
          <button
            key={option.key}
            type="button"
            className={`token-react-panel__period-btn${period === option.key ? ' is-active' : ''}`}
            onClick={() => {
              void handlePeriodChange(option.key);
            }}
          >
            {option.label}
          </button>
        ))}
      </div>

      {loadState.errorText ? <div className="token-react-panel__notice token-react-panel__notice--error">{loadState.errorText}</div> : null}
      {loadState.loading ? <div className="token-react-panel__empty">正在加载 Token 统计...</div> : null}

      {!loadState.loading ? (
        <>
          <div className="token-react-panel__metric-grid">
            <article className="token-react-panel__metric-card">
              <span className="token-react-panel__metric-label">总 Token</span>
              <strong className="token-react-panel__metric-value">{formatNum(stats.total_tokens)}</strong>
            </article>
            <article className="token-react-panel__metric-card">
              <span className="token-react-panel__metric-label">请求次数</span>
              <strong className="token-react-panel__metric-value">{formatNum(stats.request_count)}</strong>
            </article>
            <article className="token-react-panel__metric-card is-prompt">
              <span className="token-react-panel__metric-label">输入 Token</span>
              <strong className="token-react-panel__metric-value">{formatNum(stats.total_prompt_tokens)}</strong>
            </article>
            <article className="token-react-panel__metric-card is-completion">
              <span className="token-react-panel__metric-label">输出 Token</span>
              <strong className="token-react-panel__metric-value">{formatNum(stats.total_completion_tokens)}</strong>
            </article>
          </div>

          {stats.total_tokens > 0 ? (
            <section className="token-react-panel__ratio-card">
              <div className="token-react-panel__section-head">
                <h5>输入输出配比</h5>
                <div className="token-react-panel__ratio-meta">
                  <span>In {promptRatio}% </span>
                  <span>Out {completionRatio}%</span>
                </div>
              </div>
              <div className="token-react-panel__ratio-bar">
                <div className="token-react-panel__ratio-fill is-prompt" style={{ width: `${promptRatio}%` }} />
                <div className="token-react-panel__ratio-fill is-completion" style={{ width: `${completionRatio}%` }} />
              </div>
            </section>
          ) : null}

          {stats.timeline.length > 0 ? (
            <section className="token-react-panel__chart-card">
              <div className="token-react-panel__section-head">
                <h5>Timeline</h5>
                <div className="token-react-panel__legend">
                  <span className="is-prompt">Input</span>
                  <span className="is-completion">Output</span>
                </div>
              </div>
              <div className="token-react-panel__bars">
                {stats.timeline.map((item) => {
                  const promptHeight = Math.max(6, Math.round(((item.prompt || 0) / timelineMax) * 100));
                  const completionHeight = Math.max(6, Math.round(((item.completion || 0) / timelineMax) * 100));
                  return (
                    <div key={item.time} className="token-react-panel__bar-group" title={`${item.time} · ∑ ${formatNum(item.total)}`}>
                      <div className="token-react-panel__bar-stack">
                        <div className="token-react-panel__bar is-completion" style={{ height: `${completionHeight}%` }} />
                        <div className="token-react-panel__bar is-prompt" style={{ height: `${promptHeight}%` }} />
                      </div>
                      <div className="token-react-panel__bar-label">{item.time}</div>
                    </div>
                  );
                })}
              </div>
            </section>
          ) : null}

          {modelEntries.length > 0 ? (
            <section className="token-react-panel__models">
              <div className="token-react-panel__section-head">
                <h5>模型分布</h5>
              </div>
              <div className="token-react-panel__model-list">
                {modelEntries.map(([model, stat]) => (
                  <article key={model} className="token-react-panel__model-card">
                    <div className="token-react-panel__model-head">
                      <strong className="token-react-panel__model-name">{model}</strong>
                      <span className="token-react-panel__model-count">{stat.count} CTX</span>
                    </div>
                    <div className="token-react-panel__model-metrics">
                      <span>In {formatNum(stat.prompt)}</span>
                      <span>Out {formatNum(stat.completion)}</span>
                      <span>Total {formatNum(stat.total)}</span>
                    </div>
                  </article>
                ))}
              </div>
            </section>
          ) : null}

          {stats.request_count === 0 ? (
            <div className="token-react-panel__empty">暂无统计轨迹，等发起几次请求后这里就会有数据。</div>
          ) : null}
        </>
      ) : null}

      {statusText ? <div className="token-react-panel__notice token-react-panel__notice--status">{statusText}</div> : null}
    </div>
  );
}

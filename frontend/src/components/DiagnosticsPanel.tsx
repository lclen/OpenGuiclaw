import { useEffect, useState } from 'react';
import { useWorkspaceShellBridge } from '../hooks/useWorkspaceShellBridge';

type DiagnosticsPayload = {
  system?: {
    os?: string;
    python_version?: string;
    python_executable?: string;
    app_dir?: string;
    frozen?: boolean;
  };
  restart?: {
    supported?: boolean;
    mode?: string;
    reason?: string | null;
  };
  network?: {
    proxies?: Record<string, string | null>;
    connectivity?: {
      status?: string;
      latency_ms?: number;
      error?: string;
    };
  };
  dependencies?: Record<string, boolean>;
  timestamp?: number;
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

function formatTimestamp(timestamp?: number) {
  if (!timestamp) return '未运行';
  try {
    return new Date(timestamp * 1000).toLocaleString('zh-CN', { hour12: false });
  } catch {
    return '未运行';
  }
}

export function DiagnosticsPanel() {
  const { snapshot } = useWorkspaceShellBridge();
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<DiagnosticsPayload | null>(null);
  const [errorText, setErrorText] = useState('');
  const [pokeStatus, setPokeStatus] = useState('');

  useEffect(() => {
    if (!snapshot.showSettings || snapshot.settingsTab !== 'diagnostics') return;
    if (result || running) return;
    void runDiagnostics();
  }, [snapshot.showSettings, snapshot.settingsTab]);

  async function runDiagnostics() {
    setRunning(true);
    setErrorText('');
    try {
      const response = await fetch('/api/diagnostics');
      if (!response.ok) {
        throw new Error(await readErrorMessage(response, '诊断失败'));
      }

      const payload = (await parseResponse(response)) as DiagnosticsPayload;
      setResult(payload);
    } catch (error) {
      setErrorText(error instanceof Error ? error.message : '诊断失败');
    } finally {
      setRunning(false);
    }
  }

  async function wakeModel() {
    setPokeStatus('唤醒中...');
    try {
      const response = await fetch('/api/context/poke', { method: 'POST' });
      if (!response.ok) {
        throw new Error(await readErrorMessage(response, '唤醒模型失败'));
      }
      setPokeStatus('模型唤醒请求已发送');
    } catch (error) {
      setPokeStatus(error instanceof Error ? error.message : '唤醒模型失败');
    }

    window.clearTimeout((wakeModel as typeof wakeModel & { timer?: number }).timer);
    (wakeModel as typeof wakeModel & { timer?: number }).timer = window.setTimeout(() => {
      setPokeStatus('');
    }, 3200);
  }

  const connectivity = result?.network?.connectivity;
  const dependencies = Object.entries(result?.dependencies || {});
  const proxies = Object.entries(result?.network?.proxies || {});

  return (
    <div className="diagnostics-panel">
      <header className="diagnostics-panel__header">
        <div>
          <div className="diagnostics-panel__eyebrow">Environment Diagnostics</div>
          <h4 className="diagnostics-panel__title">环境与依赖诊断</h4>
          <p className="diagnostics-panel__meta">检查系统环境、核心依赖、代理配置与外网连通性。</p>
        </div>

        <div className="diagnostics-panel__toolbar">
          <button type="button" className="diagnostics-panel__ghost-btn" onClick={runDiagnostics} disabled={running}>
            {running ? '诊断中...' : '运行诊断'}
          </button>
          <button
            type="button"
            className="diagnostics-panel__ghost-btn"
            onClick={() => {
              window.location.href = '/api/diagnostics/export';
            }}
            disabled={!result}
          >
            导出报告
          </button>
        </div>
      </header>

      {errorText ? <div className="diagnostics-panel__notice diagnostics-panel__notice--error">{errorText}</div> : null}
      {running && !result ? <div className="diagnostics-panel__empty">正在采集系统诊断信息...</div> : null}

      {result ? (
        <>
          <div className="diagnostics-panel__summary-grid">
            <article className="diagnostics-panel__summary-card">
              <div className="diagnostics-panel__summary-label">Python 版本</div>
              <div className="diagnostics-panel__summary-value">
                {(result.system?.python_version || '未知').split(' ')[0]}
              </div>
            </article>

            <article className="diagnostics-panel__summary-card">
              <div className="diagnostics-panel__summary-label">网络连通性</div>
              <div className={`diagnostics-panel__summary-value ${connectivity?.status === 'ok' ? 'is-healthy' : 'is-error'}`}>
                {connectivity?.status === 'ok' ? `正常 (${connectivity.latency_ms}ms)` : connectivity?.error || '失败'}
              </div>
            </article>

            <article className="diagnostics-panel__summary-card">
              <div className="diagnostics-panel__summary-label">最近诊断</div>
              <div className="diagnostics-panel__summary-value">{formatTimestamp(result.timestamp)}</div>
            </article>
          </div>

          <div className="diagnostics-panel__grid">
            <section className="diagnostics-panel__card">
              <h5 className="diagnostics-panel__card-title">系统信息</h5>
              <div className="diagnostics-panel__kv-list">
                <div className="diagnostics-panel__kv-row">
                  <span>操作系统</span>
                  <strong>{result.system?.os || '未知'}</strong>
                </div>
                <div className="diagnostics-panel__kv-row">
                  <span>Python 路径</span>
                  <strong className="is-mono">{result.system?.python_executable || '未知'}</strong>
                </div>
                <div className="diagnostics-panel__kv-row">
                  <span>应用目录</span>
                  <strong className="is-mono">{result.system?.app_dir || '未知'}</strong>
                </div>
                <div className="diagnostics-panel__kv-row">
                  <span>运行方式</span>
                  <strong>{result.system?.frozen ? '打包运行' : '源码运行'}</strong>
                </div>
                <div className="diagnostics-panel__kv-row">
                  <span>自动重启</span>
                  <strong>{result.restart?.supported ? '支持（watchdog）' : '不支持（开发模式）'}</strong>
                </div>
                {result.restart?.reason ? (
                  <div className="diagnostics-panel__kv-row">
                    <span>重启说明</span>
                    <strong>{result.restart.reason}</strong>
                  </div>
                ) : null}
              </div>
            </section>

            <section className="diagnostics-panel__card">
              <h5 className="diagnostics-panel__card-title">网络与代理</h5>
              <div className="diagnostics-panel__kv-list">
                {proxies.map(([key, value]) => (
                  <div key={key} className="diagnostics-panel__kv-row">
                    <span>{key.toUpperCase()}_PROXY</span>
                    <strong className="is-mono">{value || '未设置'}</strong>
                  </div>
                ))}
              </div>
            </section>
          </div>

          <section className="diagnostics-panel__card">
            <h5 className="diagnostics-panel__card-title">核心依赖检查</h5>
            <div className="diagnostics-panel__dep-grid">
              {dependencies.map(([name, ok]) => (
                <div key={name} className="diagnostics-panel__dep-item">
                  <span className={`diagnostics-panel__dep-dot ${ok ? 'is-ok' : 'is-bad'}`} />
                  <span className="diagnostics-panel__dep-name">{name}</span>
                  <span className={`diagnostics-panel__dep-status ${ok ? 'is-ok' : 'is-bad'}`}>{ok ? '已安装' : '缺失'}</span>
                </div>
              ))}
            </div>
          </section>
        </>
      ) : null}

      <button type="button" className="diagnostics-panel__accent-btn" onClick={wakeModel}>
        手动唤醒模型推理
      </button>

      {pokeStatus ? <div className="diagnostics-panel__notice diagnostics-panel__notice--status">{pokeStatus}</div> : null}
    </div>
  );
}

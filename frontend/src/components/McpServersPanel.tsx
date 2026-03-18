import { useEffect, useState } from 'react';
import { emitShellUpdate } from '../bridge/openGuiclaw';
import { useWorkspaceShellBridge } from '../hooks/useWorkspaceShellBridge';

type McpServerDraft = {
  name: string;
  command: string;
  argsText: string;
  envText: string;
  disabled: boolean;
};

type LoadState = {
  loading: boolean;
  errorText: string;
};

async function parseResponse(response: Response) {
  const contentType = response.headers.get('content-type') || '';
  if (contentType.includes('application/json')) {
    return response.json();
  }
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

function buildDrafts(payload: unknown): McpServerDraft[] {
  const entries =
    payload && typeof payload === 'object' && 'mcpServers' in payload && payload.mcpServers && typeof payload.mcpServers === 'object'
      ? Object.entries(payload.mcpServers as Record<string, Record<string, unknown>>)
      : [];

  return entries.map(([name, config]) => {
    const args = Array.isArray(config?.args) ? config.args.map((item) => String(item)) : [];
    const envEntries =
      config?.env && typeof config.env === 'object'
        ? Object.entries(config.env as Record<string, unknown>).map(([key, value]) => `${key}=${String(value)}`)
        : [];

    return {
      name,
      command: typeof config?.command === 'string' ? config.command : '',
      argsText: args.join('\n'),
      envText: envEntries.join('\n'),
      disabled: !!config?.disabled
    };
  });
}

function serializeDrafts(servers: McpServerDraft[]) {
  const mcpServers: Record<string, { command: string; args: string[]; env?: Record<string, string>; disabled?: true }> = {};

  servers.forEach((server) => {
    const name = server.name.trim();
    if (!name) return;

    const args = server.argsText
      .split(/\r?\n/)
      .map((item) => item.trim())
      .filter(Boolean);

    const env: Record<string, string> = {};
    server.envText
      .split(/\r?\n/)
      .map((item) => item.trim())
      .filter(Boolean)
      .forEach((line) => {
        const separatorIndex = line.indexOf('=');
        if (separatorIndex <= 0) return;
        const key = line.slice(0, separatorIndex).trim();
        const value = line.slice(separatorIndex + 1).trim();
        if (key) env[key] = value;
      });

    mcpServers[name] = {
      command: server.command.trim(),
      args,
      ...(Object.keys(env).length > 0 ? { env } : {}),
      ...(server.disabled ? { disabled: true as const } : {})
    };
  });

  return { mcpServers };
}

function createEmptyDraft(): McpServerDraft {
  return {
    name: '',
    command: '',
    argsText: '',
    envText: '',
    disabled: false
  };
}

export function McpServersPanel() {
  const { snapshot } = useWorkspaceShellBridge();
  const [servers, setServers] = useState<McpServerDraft[]>([]);
  const [loadState, setLoadState] = useState<LoadState>({ loading: true, errorText: '' });
  const [saving, setSaving] = useState(false);
  const [statusText, setStatusText] = useState('');

  useEffect(() => {
    if (!snapshot.showSettings || snapshot.settingsTab !== 'mcp') return;
    void loadServers();
  }, [snapshot.showSettings, snapshot.settingsTab]);

  function pushStatus(message: string) {
    setStatusText(message);
    window.clearTimeout((pushStatus as typeof pushStatus & { timer?: number }).timer);
    (pushStatus as typeof pushStatus & { timer?: number }).timer = window.setTimeout(() => {
      setStatusText('');
    }, 3200);
  }

  async function loadServers() {
    setLoadState({ loading: true, errorText: '' });
    try {
      const response = await fetch('/api/mcp/servers');
      if (!response.ok) {
        throw new Error(await readErrorMessage(response, '加载 MCP 工具配置失败'));
      }

      const payload = await parseResponse(response);
      setServers(buildDrafts(payload));
      setLoadState({ loading: false, errorText: '' });
      emitShellUpdate();
    } catch (error) {
      setLoadState({
        loading: false,
        errorText: error instanceof Error ? error.message : '加载 MCP 工具配置失败'
      });
      setServers([]);
    }
  }

  function updateServer(index: number, patch: Partial<McpServerDraft>) {
    setServers((current) => current.map((server, currentIndex) => (currentIndex === index ? { ...server, ...patch } : server)));
  }

  function addServer() {
    setServers((current) => [...current, createEmptyDraft()]);
  }

  function removeServer(index: number) {
    setServers((current) => current.filter((_, currentIndex) => currentIndex !== index));
  }

  async function saveServers() {
    setSaving(true);
    try {
      const response = await fetch('/api/mcp/servers', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(serializeDrafts(servers))
      });

      if (!response.ok) {
        throw new Error(await readErrorMessage(response, 'MCP 配置保存失败'));
      }

      pushStatus('MCP 工具配置已保存');

      emitShellUpdate();
      await loadServers();
    } catch (error) {
      pushStatus(error instanceof Error ? error.message : 'MCP 配置保存异常');
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="mcp-panel">
      <header className="mcp-panel__header">
        <div>
          <div className="mcp-panel__eyebrow">Model Context Protocol</div>
          <h4 className="mcp-panel__title">MCP Servers</h4>
          <p className="mcp-panel__meta">
            为外部工具服务器维护名称、启动命令、参数和环境变量。保存后会写入
            <span className="mcp-panel__meta-code">config/mcp_servers.json</span>。
          </p>
        </div>
        <div className="mcp-panel__toolbar">
          <button type="button" className="mcp-panel__ghost-btn" onClick={addServer}>
            + 新增 Server
          </button>
          <button type="button" className="mcp-panel__accent-btn" onClick={saveServers} disabled={saving}>
            {saving ? '保存中...' : '保存 MCP 配置'}
          </button>
        </div>
      </header>

      {loadState.errorText ? <div className="mcp-panel__notice mcp-panel__notice--error">{loadState.errorText}</div> : null}

      {loadState.loading ? <div className="mcp-panel__empty">正在加载 MCP 配置...</div> : null}

      {!loadState.loading && !loadState.errorText && servers.length === 0 ? (
        <div className="mcp-panel__empty">当前还没有配置 MCP 服务器，你可以先新增一个 server。</div>
      ) : null}

      {!loadState.loading && servers.length > 0 ? (
        <div className="mcp-panel__stack">
          {servers.map((server, index) => (
            <article key={`${server.name || 'draft'}-${index}`} className="mcp-panel__card">
              <div className="mcp-panel__card-top">
                <div className="mcp-panel__card-heading">
                  <span className="mcp-panel__card-label">Server</span>
                  <span className="mcp-panel__pill">{server.name.trim() || `未命名 #${index + 1}`}</span>
                </div>
                <button type="button" className="mcp-panel__danger-btn" onClick={() => removeServer(index)}>
                  删除
                </button>
              </div>

              <div className="mcp-panel__grid">
                <label className="mcp-panel__field">
                  <span className="mcp-panel__field-label">名称</span>
                  <input
                    type="text"
                    className="mcp-panel__input"
                    placeholder="例如 context7"
                    value={server.name}
                    onChange={(event) => updateServer(index, { name: event.target.value })}
                  />
                </label>

                <label className="mcp-panel__field">
                  <span className="mcp-panel__field-label">Command</span>
                  <input
                    type="text"
                    className="mcp-panel__input mcp-panel__input--mono"
                    placeholder="例如 npx"
                    value={server.command}
                    onChange={(event) => updateServer(index, { command: event.target.value })}
                  />
                </label>

                <label className="mcp-panel__field">
                  <span className="mcp-panel__field-label">Args</span>
                  <textarea
                    className="mcp-panel__textarea mcp-panel__input--mono"
                    placeholder={'-y\n@upstash/context7-mcp@latest'}
                    value={server.argsText}
                    onChange={(event) => updateServer(index, { argsText: event.target.value })}
                  />
                  <span className="mcp-panel__hint">每行一个参数，保存时会自动写成数组。</span>
                </label>

                <label className="mcp-panel__field">
                  <span className="mcp-panel__field-label">Env</span>
                  <textarea
                    className="mcp-panel__textarea mcp-panel__input--mono"
                    placeholder={'API_KEY=your-key\nBASE_URL=https://...'}
                    value={server.envText}
                    onChange={(event) => updateServer(index, { envText: event.target.value })}
                  />
                  <span className="mcp-panel__hint">
                    每行一个 <code>KEY=value</code>。
                  </span>
                </label>
              </div>

              <label className="mcp-panel__checkbox">
                <input
                  type="checkbox"
                  checked={server.disabled}
                  onChange={(event) => updateServer(index, { disabled: event.target.checked })}
                />
                <span>保存为 disabled</span>
              </label>
            </article>
          ))}
        </div>
      ) : null}

      {statusText ? <div className="mcp-panel__notice mcp-panel__notice--status">{statusText}</div> : null}
    </div>
  );
}

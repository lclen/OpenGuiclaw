import { useEffect, useState } from 'react';
import { emitShellUpdate } from '../bridge/openGuiclaw';
import { CaretDownIcon } from './icons/ShellIcons';
import { useWorkspaceShellBridge } from '../hooks/useWorkspaceShellBridge';
import { UiButton } from './ui/UiButton';
import { UiCard } from './ui/UiCard';
import { UiSection } from './ui/UiSection';
import { UiStatusPill } from './ui/UiStatusPill';

type McpToolInfo = {
  name: string;
  description?: string;
};

type McpServerStatus = {
  name: string;
  transport?: string;
  connected?: boolean;
  tool_count?: number;
  catalog_tool_count?: number;
  tools?: McpToolInfo[];
  last_connect_attempt_at?: string | null;
  last_connect_error?: string | null;
  last_connect_result?: 'connected' | 'error' | 'timeout' | 'not_attempted';
  auto_connected?: boolean;
};

type McpServerDraft = {
  savedName: string;
  name: string;
  command: string;
  argsText: string;
  envText: string;
  disabled: boolean;
  transport: string;
  connected: boolean;
  toolCount: number;
  catalogToolCount: number;
  tools: McpToolInfo[];
  lastConnectAttemptAt: string;
  lastConnectError: string;
  lastConnectResult: 'connected' | 'error' | 'timeout' | 'not_attempted';
  autoConnected: boolean;
};

type LoadState = {
  loading: boolean;
  errorText: string;
};

type McpServersResponse = {
  mcpServers?: Record<string, Record<string, unknown>>;
  servers?: McpServerStatus[];
  mcp_sdk_available?: boolean;
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
    // noop
  }
  return fallback;
}

function buildDrafts(payload: McpServersResponse): McpServerDraft[] {
  const statusMap = new Map((payload.servers || []).map((server) => [server.name, server]));
  const entries =
    payload.mcpServers && typeof payload.mcpServers === 'object'
      ? Object.entries(payload.mcpServers as Record<string, Record<string, unknown>>)
      : [];

  return entries.map(([name, config]) => {
    const status = statusMap.get(name);
    const args = Array.isArray(config?.args) ? config.args.map((item) => String(item)) : [];
    const envEntries =
      config?.env && typeof config.env === 'object'
        ? Object.entries(config.env as Record<string, unknown>).map(([key, value]) => `${key}=${String(value)}`)
        : [];

    return {
      savedName: name,
      name,
      command: typeof config?.command === 'string' ? config.command : '',
      argsText: args.join('\n'),
      envText: envEntries.join('\n'),
      disabled: !!config?.disabled,
      transport: typeof status?.transport === 'string' ? status.transport : 'stdio',
      connected: !!status?.connected,
      toolCount: Number(status?.tool_count ?? 0),
      catalogToolCount: Number(status?.catalog_tool_count ?? 0),
      tools: Array.isArray(status?.tools) ? status.tools : [],
      lastConnectAttemptAt: typeof status?.last_connect_attempt_at === 'string' ? status.last_connect_attempt_at : '',
      lastConnectError: typeof status?.last_connect_error === 'string' ? status.last_connect_error : '',
      lastConnectResult: status?.last_connect_result ?? 'not_attempted',
      autoConnected: !!status?.auto_connected,
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
      ...(server.disabled ? { disabled: true as const } : {}),
    };
  });

  return { mcpServers };
}

function createEmptyDraft(): McpServerDraft {
  return {
    savedName: '',
    name: '',
    command: '',
    argsText: '',
    envText: '',
    disabled: false,
    transport: 'stdio',
    connected: false,
    toolCount: 0,
    catalogToolCount: 0,
    tools: [],
    lastConnectAttemptAt: '',
    lastConnectError: '',
    lastConnectResult: 'not_attempted',
    autoConnected: false,
  };
}

function getServerIdentity(server: McpServerDraft, index: number) {
  return server.savedName || server.name.trim() || `draft-${index}`;
}

function getConnectionHint(server: McpServerDraft) {
  if (server.connected) {
    return server.autoConnected ? '启动时已自动连接' : '当前连接正常';
  }
  if (server.lastConnectResult === 'timeout') {
    return server.lastConnectError || '最近一次自动连接超时';
  }
  if (server.lastConnectResult === 'error') {
    return server.lastConnectError || '最近一次连接失败';
  }
  if (server.lastConnectResult === 'not_attempted') {
    return server.disabled ? '该服务器已禁用，不会自动连接' : '等待自动连接或手动连接';
  }
  return '';
}

export function McpServersPanel() {
  const { snapshot } = useWorkspaceShellBridge();
  const [servers, setServers] = useState<McpServerDraft[]>([]);
  const [loadState, setLoadState] = useState<LoadState>({ loading: true, errorText: '' });
  const [saving, setSaving] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [sdkAvailable, setSdkAvailable] = useState(true);
  const [statusText, setStatusText] = useState('');
  const [busyServer, setBusyServer] = useState<string | null>(null);
  const [expandedServer, setExpandedServer] = useState<string | null>(null);
  const [configServer, setConfigServer] = useState<string | null>(null);

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

  async function loadServers(options?: { silent?: boolean }) {
    if (!options?.silent) {
      setLoadState({ loading: true, errorText: '' });
    } else {
      setRefreshing(true);
    }

    try {
      const response = await fetch('/api/mcp/servers');
      if (!response.ok) {
        throw new Error(await readErrorMessage(response, '加载 MCP 工具配置失败'));
      }

      const payload = (await parseResponse(response)) as McpServersResponse;
      setServers(buildDrafts(payload));
      setSdkAvailable(payload.mcp_sdk_available !== false);
      setLoadState({ loading: false, errorText: '' });
      emitShellUpdate();
    } catch (error) {
      setLoadState({
        loading: false,
        errorText: error instanceof Error ? error.message : '加载 MCP 工具配置失败',
      });
      setServers([]);
    } finally {
      setRefreshing(false);
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
        body: JSON.stringify(serializeDrafts(servers)),
      });

      if (!response.ok) {
        throw new Error(await readErrorMessage(response, 'MCP 配置保存失败'));
      }

      pushStatus('MCP 工具配置已保存');
      await loadServers({ silent: true });
    } catch (error) {
      pushStatus(error instanceof Error ? error.message : 'MCP 配置保存异常');
    } finally {
      setSaving(false);
    }
  }

  async function connectServer(server: McpServerDraft, index: number) {
    const serverName = getServerIdentity(server, index);
    setBusyServer(serverName);
    try {
      const response = await fetch('/api/mcp/connect', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ server_name: serverName }),
      });
      if (!response.ok) {
        throw new Error(await readErrorMessage(response, `连接 MCP 服务器失败: ${serverName}`));
      }
      pushStatus(`已连接 MCP 服务器：${serverName}`);
      setExpandedServer(serverName);
      await loadServers({ silent: true });
    } catch (error) {
      pushStatus(error instanceof Error ? error.message : `连接 MCP 服务器失败: ${serverName}`);
    } finally {
      setBusyServer(null);
    }
  }

  async function disconnectServer(server: McpServerDraft, index: number) {
    const serverName = getServerIdentity(server, index);
    setBusyServer(serverName);
    try {
      const response = await fetch('/api/mcp/disconnect', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ server_name: serverName }),
      });
      if (!response.ok) {
        throw new Error(await readErrorMessage(response, `断开 MCP 服务器失败: ${serverName}`));
      }
      pushStatus(`已断开 MCP 服务器：${serverName}`);
      await loadServers({ silent: true });
    } catch (error) {
      pushStatus(error instanceof Error ? error.message : `断开 MCP 服务器失败: ${serverName}`);
    } finally {
      setBusyServer(null);
    }
  }

  function toggleExpanded(server: McpServerDraft, index: number) {
    const key = getServerIdentity(server, index);
    setExpandedServer((current) => (current === key ? null : key));
  }

  function toggleConfig(server: McpServerDraft, index: number) {
    const key = getServerIdentity(server, index);
    setConfigServer((current) => (current === key ? null : key));
  }

  return (
    <div className="mcp-panel">
      <header className="mcp-panel__header">
        <div>
          <div className="mcp-panel__eyebrow">Model Context Protocol</div>
          <h4 className="mcp-panel__title">MCP Servers</h4>
          <p className="mcp-panel__meta">
            将工具展示与连接状态前置；详细 MCP 配置收进每张卡片自己的配置区域。
            <span className="mcp-panel__meta-code">config/mcp_servers.json</span>
          </p>
        </div>
        <div className="mcp-panel__toolbar">
          <UiButton variant="secondary" className="mcp-panel__ghost-btn" onClick={addServer}>
            + 添加服务器
          </UiButton>
          <UiButton variant="secondary" className="mcp-panel__ghost-btn" onClick={() => void loadServers({ silent: true })} disabled={refreshing || loadState.loading}>
            {refreshing ? '刷新中...' : '刷新'}
          </UiButton>
          <UiButton variant="primary" className="mcp-panel__accent-btn" onClick={saveServers} disabled={saving}>
            {saving ? '保存中...' : '保存配置'}
          </UiButton>
        </div>
      </header>

      {!sdkAvailable ? <div className="mcp-panel__notice mcp-panel__notice--error">当前环境未安装 MCP SDK，请先执行 `pip install mcp`。</div> : null}
      {loadState.errorText ? <div className="mcp-panel__notice mcp-panel__notice--error">{loadState.errorText}</div> : null}
      {loadState.loading ? <div className="mcp-panel__empty">正在加载 MCP 配置...</div> : null}

      {!loadState.loading && !loadState.errorText && servers.length === 0 ? <div className="mcp-panel__empty">当前还没有配置 MCP 服务器，你可以先新增一个 server。</div> : null}

      {!loadState.loading && servers.length > 0 ? (
        <div className="mcp-panel__stack">
          {servers.map((server, index) => {
            const key = getServerIdentity(server, index);
            const renamePending = !!server.savedName && server.savedName !== server.name.trim();
            const actionDisabled = !server.name.trim() || renamePending || server.disabled || !sdkAvailable;
            const toolCount = server.connected ? server.toolCount : server.catalogToolCount;
            const isExpanded = expandedServer === key;
            const configOpen = configServer === key;

            return (
              <UiCard key={key} as="article" variant={server.connected ? 'status' : 'default'} className={`mcp-panel__card${server.connected ? ' is-connected' : ''}`}>
                <div className="mcp-panel__card-top">
                  <button type="button" className="mcp-panel__summary-btn" onClick={() => toggleExpanded(server, index)}>
                    <CaretDownIcon className={`mcp-panel__chevron${isExpanded ? ' is-open' : ''}`} />
                    <span className={`mcp-panel__live-dot${server.connected ? ' is-connected' : ''}`} />
                    <span className="mcp-panel__summary-name">{server.name.trim() || `未命名 #${index + 1}`}</span>
                    <UiStatusPill tone="neutral" className="mcp-panel__status-pill">{server.transport}</UiStatusPill>
                    <UiStatusPill tone={server.connected ? 'success' : 'warning'} className="mcp-panel__status-pill">{server.connected ? '在线' : '离线'}</UiStatusPill>
                    {server.disabled ? <UiStatusPill tone="disabled" className="mcp-panel__status-pill is-disabled">已禁用</UiStatusPill> : null}
                    <UiStatusPill tone="brand" className="mcp-panel__status-pill">{toolCount} 工具</UiStatusPill>
                  </button>

                  <div className="mcp-panel__card-actions">
                    <UiButton variant="secondary" className="mcp-panel__ghost-btn" onClick={() => toggleConfig(server, index)}>
                      {configOpen ? '收起配置' : '配置'}
                    </UiButton>
                    {server.connected ? (
                      <UiButton variant="secondary" className="mcp-panel__ghost-btn" onClick={() => void disconnectServer(server, index)} disabled={busyServer === key || actionDisabled}>
                        {busyServer === key ? '断开中...' : '断开'}
                      </UiButton>
                    ) : (
                      <UiButton variant="primary" className="mcp-panel__accent-btn" onClick={() => void connectServer(server, index)} disabled={busyServer === key || actionDisabled}>
                        {busyServer === key ? '连接中...' : '连接'}
                      </UiButton>
                    )}
                    <UiButton variant="danger" className="mcp-panel__danger-btn" onClick={() => removeServer(index)}>
                      删除
                    </UiButton>
                  </div>
                </div>

                {isExpanded ? (
                  <div className="mcp-panel__expand-body">
                    <div className="mcp-panel__command-line">
                      <span className="mcp-panel__status-label">命令</span>
                      <span className="mcp-panel__command-text">
                        {server.command ? `${server.command}${server.argsText ? ` ${server.argsText.replace(/\r?\n/g, ' ')}` : ''}` : '尚未配置命令，点击“配置”补充参数。'}
                      </span>
                    </div>

                    {!server.connected || server.autoConnected ? (
                      <div className="mcp-panel__command-line">
                        <span className="mcp-panel__status-label">连接状态</span>
                        <span className="mcp-panel__command-text">{getConnectionHint(server)}</span>
                      </div>
                    ) : null}

                    {!server.connected && server.lastConnectError ? (
                      <div className="mcp-panel__tool-empty">{server.lastConnectError}</div>
                    ) : null}

                    <UiSection
                      className="mcp-panel__tools"
                      open
                      title={`可用工具 (${server.tools.length || toolCount})`}
                      subtitle={server.connected ? '展示当前连接返回的工具清单。' : '连接后会自动发现可用工具。'}
                    >
                      {server.tools.length > 0 ? (
                        <div className="mcp-panel__tool-list">
                          {server.tools.map((tool) => (
                            <UiCard key={`${key}-${tool.name}`} variant="subtle" className="mcp-panel__tool-card">
                              <div className="mcp-panel__tool-name">{tool.name}</div>
                              {tool.description ? <div className="mcp-panel__tool-desc">{tool.description}</div> : null}
                            </UiCard>
                          ))}
                        </div>
                      ) : (
                        <div className="mcp-panel__tool-empty">{server.connected ? '当前服务器已连接，但没有返回可展示的工具。' : '请先连接 MCP 服务器以发现可用工具。'}</div>
                      )}
                    </UiSection>
                  </div>
                ) : null}

                {configOpen ? (
                  <UiSection className="mcp-panel__config-wrap" open title="服务器配置" subtitle="详细参数收束在这里，避免主卡片信息过载。">
                    <div className="mcp-panel__grid">
                      <label className="mcp-panel__field">
                        <span className="mcp-panel__field-label">名称</span>
                        <input type="text" className="mcp-panel__input" placeholder="例如 context7" value={server.name} onChange={(event) => updateServer(index, { name: event.target.value })} />
                      </label>

                      <label className="mcp-panel__field">
                        <span className="mcp-panel__field-label">Command</span>
                        <input type="text" className="mcp-panel__input mcp-panel__input--mono" placeholder="例如 npx" value={server.command} onChange={(event) => updateServer(index, { command: event.target.value })} />
                      </label>

                      <label className="mcp-panel__field">
                        <span className="mcp-panel__field-label">Args</span>
                        <textarea className="mcp-panel__textarea mcp-panel__input--mono" placeholder={'-y\n@upstash/context7-mcp@latest'} value={server.argsText} onChange={(event) => updateServer(index, { argsText: event.target.value })} />
                        <span className="mcp-panel__hint">每行一个参数，保存时会自动写成数组。</span>
                      </label>

                      <label className="mcp-panel__field">
                        <span className="mcp-panel__field-label">Env</span>
                        <textarea className="mcp-panel__textarea mcp-panel__input--mono" placeholder={'API_KEY=your-key\nBASE_URL=https://...'} value={server.envText} onChange={(event) => updateServer(index, { envText: event.target.value })} />
                        <span className="mcp-panel__hint">每行一个 <code>KEY=value</code>。</span>
                      </label>
                    </div>

                    <label className="mcp-panel__checkbox">
                      <input type="checkbox" checked={server.disabled} onChange={(event) => updateServer(index, { disabled: event.target.checked })} />
                      <span>保存为 disabled</span>
                    </label>
                  </UiSection>
                ) : null}
              </UiCard>
            );
          })}
        </div>
      ) : null}

      {statusText ? <div className="mcp-panel__notice mcp-panel__notice--status">{statusText}</div> : null}
    </div>
  );
}

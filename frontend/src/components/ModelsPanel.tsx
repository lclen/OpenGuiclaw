import { type KeyboardEvent, useEffect, useMemo, useState } from 'react';
import { emitShellUpdate } from '../bridge/openGuiclaw';
import { CaretDownIcon } from './icons/ShellIcons';
import { useWorkspaceShellBridge } from '../hooks/useWorkspaceShellBridge';
import { UiActionTray } from './ui/UiActionTray';
import { UiButton } from './ui/UiButton';
import { UiStatusPill } from './ui/UiStatusPill';

type ProviderPreset = {
  slug: string;
  name: string;
  category: string;
  api_type?: string;
  base_url: string;
  key_hint?: string;
  is_local?: boolean;
  desc?: string;
  models?: string[];
};

type RoleDefinition = {
  key: string;
  label: string;
  desc: string;
  icon?: string;
};

type ModelConfigPayload = {
  base_url?: string;
  api_key?: string;
  api_key_masked?: string;
  model?: string;
  max_tokens?: number | null;
  temperature?: number | null;
  context_window?: number | null;
  configured?: boolean;
};

type ChatEndpoint = {
  clientKey: string;
  id: string | null;
  name: string;
  provider: string;
  base_url: string;
  api_key: string;
  api_key_masked?: string;
  model: string;
  max_tokens: number;
  temperature: number;
  note?: string;
  _new?: boolean;
};

type RoleEndpoint = {
  clientKey: string;
  name: string;
  provider: string;
  base_url: string;
  api_key: string;
  api_key_masked?: string;
  model: string;
  _primary?: boolean;
  configured?: boolean;
  _new?: boolean;
};

type RoleEndpointMap = Record<string, RoleEndpoint[]>;
type TestResult = { status?: string; reply?: string; error?: string; model?: string };
type LoadState = { loading: boolean; errorText: string };

const CATEGORY_LABELS: Record<string, string> = {
  coding: '编程开发',
  cn_official: '国内官方',
  intl_official: '国际官方',
  relay: '聚合中转',
  local: '本地模型'
};

function makeClientKey(prefix: string) {
  return `${prefix}-${Math.random().toString(36).slice(2, 10)}`;
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
    // Ignore parse failures and use fallback below.
  }
  return fallback;
}

function normalizeBaseUrl(value: string) {
  return value.trim().replace(/\/$/, '');
}

function autoMatchProvider(baseUrl: string, provider: string | undefined, providers: ProviderPreset[]) {
  if (provider && provider !== 'custom') return provider;
  const normalized = normalizeBaseUrl(baseUrl);
  if (!normalized) return provider || 'custom';
  const matched = providers.find((item) => normalizeBaseUrl(item.base_url || '') === normalized);
  return matched?.slug || provider || 'custom';
}

function toChatEndpoint(raw: Partial<ChatEndpoint>, providers: ProviderPreset[]): ChatEndpoint {
  return {
    clientKey: makeClientKey('chat'),
    id: raw.id ?? null,
    name: raw.name || '',
    provider: autoMatchProvider(raw.base_url || '', raw.provider, providers),
    base_url: raw.base_url || '',
    api_key: raw.api_key || '',
    api_key_masked: raw.api_key_masked || '',
    model: raw.model || '',
    max_tokens: typeof raw.max_tokens === 'number' ? raw.max_tokens : 8000,
    temperature: typeof raw.temperature === 'number' ? raw.temperature : 0.7,
    note: raw.note || '',
    _new: !!raw._new
  };
}

function toRoleEndpoint(role: RoleDefinition, config: ModelConfigPayload | undefined, providers: ProviderPreset[]): RoleEndpoint {
  return {
    clientKey: makeClientKey(`role-${role.key}`),
    name: `${role.label}（主）`,
    provider: autoMatchProvider(config?.base_url || '', 'custom', providers),
    base_url: config?.base_url || '',
    api_key: config?.api_key || '',
    api_key_masked: config?.api_key_masked || '',
    model: config?.model || '',
    _primary: true,
    configured: !!config?.configured
  };
}

function toExtraRoleEndpoint(raw: Partial<RoleEndpoint>, roleKey: string, providers: ProviderPreset[]): RoleEndpoint {
  return {
    clientKey: makeClientKey(`role-${roleKey}`),
    name: raw.name || '',
    provider: autoMatchProvider(raw.base_url || '', raw.provider, providers),
    base_url: raw.base_url || '',
    api_key: raw.api_key || '',
    api_key_masked: raw.api_key_masked || '',
    model: raw.model || '',
    _new: !!raw._new
  };
}

function getProviderModels(providerSlug: string, providers: ProviderPreset[]) {
  return providers.find((provider) => provider.slug === providerSlug)?.models || [];
}

function endpointLabel(endpoint: { name: string; model: string; provider: string }) {
  return endpoint.name || endpoint.model || endpoint.provider || '未命名端点';
}

function onToggleKeyDown(event: KeyboardEvent<HTMLElement>, toggle: () => void) {
  if (event.key !== 'Enter' && event.key !== ' ') return;
  event.preventDefault();
  toggle();
}

export function ModelsPanel() {
  const { snapshot } = useWorkspaceShellBridge();
  const [loadState, setLoadState] = useState<LoadState>({ loading: true, errorText: '' });
  const [providers, setProviders] = useState<ProviderPreset[]>([]);
  const [roles, setRoles] = useState<RoleDefinition[]>([]);
  const [chatEndpoints, setChatEndpoints] = useState<ChatEndpoint[]>([]);
  const [roleEndpoints, setRoleEndpoints] = useState<RoleEndpointMap>({});
  const [activeEndpointId, setActiveEndpointId] = useState<string | null>(null);
  const [expandedChatKey, setExpandedChatKey] = useState<string | null>(null);
  const [expandedRoleKeys, setExpandedRoleKeys] = useState<Record<string, string | null>>({});
  const [savingChat, setSavingChat] = useState(false);
  const [savingRoles, setSavingRoles] = useState<Record<string, boolean>>({});
  const [switchingId, setSwitchingId] = useState<string | null>(null);
  const [testingKeys, setTestingKeys] = useState<Record<string, boolean>>({});
  const [testResults, setTestResults] = useState<Record<string, TestResult | null>>({});
  const [fetchingModels, setFetchingModels] = useState<Record<string, boolean>>({});
  const [fetchedModels, setFetchedModels] = useState<Record<string, string[]>>({});
  const [fetchErrors, setFetchErrors] = useState<Record<string, string>>({});
  const [showSecrets, setShowSecrets] = useState<Record<string, boolean>>({});
  const [modelSearch, setModelSearch] = useState<Record<string, string>>({});
  const [statusText, setStatusText] = useState('');

  const roleDefinitions = useMemo(() => roles.filter((role) => role.key !== 'api'), [roles]);
  const providerGroups = useMemo(() => {
    const seen = new Set<string>();
    return providers.filter((provider) => {
      if (seen.has(provider.category)) return false;
      seen.add(provider.category);
      return true;
    });
  }, [providers]);

  useEffect(() => {
    if (!snapshot.showSettings || snapshot.settingsTab !== 'models') return;
    void loadAll();
  }, [snapshot.showSettings, snapshot.settingsTab]);

  function pushStatus(message: string) {
    setStatusText(message);
    window.clearTimeout((pushStatus as typeof pushStatus & { timer?: number }).timer);
    (pushStatus as typeof pushStatus & { timer?: number }).timer = window.setTimeout(() => {
      setStatusText('');
    }, 3600);
  }

  async function loadAll() {
    setLoadState({ loading: true, errorText: '' });
    try {
      const providersResponse = await fetch('/api/config/model/providers');
      if (!providersResponse.ok) {
        throw new Error(await readErrorMessage(providersResponse, '加载模型供应商失败'));
      }

      const providersPayload = await parseResponse(providersResponse);
      const nextProviders = Array.isArray(providersPayload?.providers) ? (providersPayload.providers as ProviderPreset[]) : [];
      const nextRoles = Array.isArray(providersPayload?.roles) ? (providersPayload.roles as RoleDefinition[]) : [];

      const [chatResponse, modelResponse, roleExtrasResponse] = await Promise.all([
        fetch('/api/endpoints'),
        fetch('/api/config/model'),
        fetch('/api/config/role-endpoints')
      ]);

      if (!chatResponse.ok) throw new Error(await readErrorMessage(chatResponse, '加载聊天端点失败'));
      if (!modelResponse.ok) throw new Error(await readErrorMessage(modelResponse, '加载角色端点失败'));
      if (!roleExtrasResponse.ok) throw new Error(await readErrorMessage(roleExtrasResponse, '加载角色扩展端点失败'));

      const chatPayload = await parseResponse(chatResponse);
      const modelPayload = await parseResponse(modelResponse);
      const roleExtrasPayload = await parseResponse(roleExtrasResponse);

      const nextChatEndpoints: ChatEndpoint[] = Array.isArray(chatPayload?.endpoints)
        ? chatPayload.endpoints.map((endpoint: Partial<ChatEndpoint>) => toChatEndpoint(endpoint, nextProviders))
        : [];
      const nextActiveId = typeof chatPayload?.active_id === 'string' ? chatPayload.active_id : null;
      const modelConfig = (modelPayload?.config || {}) as Record<string, ModelConfigPayload>;
      const roleExtraEndpoints = (roleExtrasPayload?.role_extra_endpoints || {}) as Record<string, Partial<RoleEndpoint>[]>;
      const nextRoleMap: RoleEndpointMap = {};
      const nextExpandedRoleKeys: Record<string, string | null> = {};

      nextRoles
        .filter((role) => role.key !== 'api')
        .forEach((role) => {
          const primary = toRoleEndpoint(role, modelConfig[role.key], nextProviders);
          const extras = Array.isArray(roleExtraEndpoints[role.key])
            ? roleExtraEndpoints[role.key].map((endpoint) => toExtraRoleEndpoint(endpoint, role.key, nextProviders))
            : [];
          nextRoleMap[role.key] = [primary, ...extras];
          nextExpandedRoleKeys[role.key] = primary.model ? null : primary.clientKey;
        });

      setProviders(nextProviders);
      setRoles(nextRoles);
      setChatEndpoints(nextChatEndpoints);
      setRoleEndpoints(nextRoleMap);
      setActiveEndpointId(nextActiveId);
      setExpandedChatKey(nextChatEndpoints.find((endpoint) => endpoint._new)?.clientKey || null);
      setExpandedRoleKeys(nextExpandedRoleKeys);
      setLoadState({ loading: false, errorText: '' });
      emitShellUpdate();
    } catch (error) {
      setLoadState({
        loading: false,
        errorText: error instanceof Error ? error.message : '加载模型配置失败'
      });
    }
  }

  function updateChatEndpoint(clientKey: string, patch: Partial<ChatEndpoint>) {
    setChatEndpoints((current) =>
      current.map((endpoint) => (endpoint.clientKey === clientKey ? { ...endpoint, ...patch } : endpoint))
    );
  }

  function updateRoleEndpoint(roleKey: string, clientKey: string, patch: Partial<RoleEndpoint>) {
    setRoleEndpoints((current) => ({
      ...current,
      [roleKey]: (current[roleKey] || []).map((endpoint) =>
        endpoint.clientKey === clientKey ? { ...endpoint, ...patch } : endpoint
      )
    }));
  }

  function addChatEndpoint() {
    const endpoint = toChatEndpoint(
      { id: null, name: '', provider: 'custom', base_url: '', api_key: '', model: '', max_tokens: 8000, temperature: 0.7, _new: true },
      providers
    );
    setChatEndpoints((current) => [...current, endpoint]);
    setExpandedChatKey(endpoint.clientKey);
  }

  function deleteChatEndpoint(clientKey: string) {
    setChatEndpoints((current) => current.filter((endpoint) => endpoint.clientKey !== clientKey));
    setExpandedChatKey((current) => (current === clientKey ? null : current));
  }

  function addRoleEndpoint(roleKey: string) {
    const endpoint = toExtraRoleEndpoint({ name: '', provider: 'custom', base_url: '', api_key: '', model: '', _new: true }, roleKey, providers);
    setRoleEndpoints((current) => ({ ...current, [roleKey]: [...(current[roleKey] || []), endpoint] }));
    setExpandedRoleKeys((current) => ({ ...current, [roleKey]: endpoint.clientKey }));
  }

  function deleteRoleEndpoint(roleKey: string, clientKey: string) {
    setRoleEndpoints((current) => ({
      ...current,
      [roleKey]: (current[roleKey] || []).filter((endpoint) => endpoint.clientKey !== clientKey)
    }));
    setExpandedRoleKeys((current) => ({ ...current, [roleKey]: current[roleKey] === clientKey ? null : current[roleKey] }));
  }

  function applyProviderToChat(clientKey: string, providerSlug: string) {
    const provider = providers.find((item) => item.slug === providerSlug);
    if (!provider) {
      updateChatEndpoint(clientKey, { provider: 'custom' });
      return;
    }
    setChatEndpoints((current) =>
      current.map((endpoint) =>
        endpoint.clientKey === clientKey
          ? {
              ...endpoint,
              provider: provider.slug,
              base_url: provider.base_url || '',
              name: endpoint.name || provider.name,
              model: endpoint.model || provider.models?.[0] || ''
            }
          : endpoint
      )
    );
  }

  function applyProviderToRole(roleKey: string, clientKey: string, providerSlug: string) {
    const provider = providers.find((item) => item.slug === providerSlug);
    if (!provider) {
      updateRoleEndpoint(roleKey, clientKey, { provider: 'custom' });
      return;
    }
    setRoleEndpoints((current) => ({
      ...current,
      [roleKey]: (current[roleKey] || []).map((endpoint) =>
        endpoint.clientKey === clientKey
          ? {
              ...endpoint,
              provider: provider.slug,
              base_url: provider.base_url || '',
              name: endpoint.name || provider.name,
              model: endpoint.model || provider.models?.[0] || ''
            }
          : endpoint
      )
    }));
  }

  async function saveChatEndpoints() {
    setSavingChat(true);
    try {
      const payload = chatEndpoints.map((endpoint) => ({
        id: endpoint.id,
        name: endpoint.name,
        provider: endpoint.provider || 'custom',
        base_url: endpoint.base_url,
        api_key: endpoint.api_key,
        model: endpoint.model,
        max_tokens: endpoint.max_tokens,
        temperature: endpoint.temperature,
        note: endpoint.note || ''
      }));
      const response = await fetch('/api/endpoints', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      if (!response.ok) throw new Error(await readErrorMessage(response, '保存聊天端点失败'));
      const data = await parseResponse(response);
      pushStatus(`已保存 ${data?.count ?? payload.length} 个聊天端点`);
      await loadAll();
    } catch (error) {
      pushStatus(error instanceof Error ? error.message : '保存聊天端点失败');
    } finally {
      setSavingChat(false);
    }
  }

  async function switchChatEndpoint(endpointId: string) {
    if (!endpointId || endpointId === activeEndpointId) return;
    setSwitchingId(endpointId);
    try {
      const response = await fetch('/api/endpoints/active', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id: endpointId })
      });
      if (!response.ok) throw new Error(await readErrorMessage(response, '切换主聊天端点失败'));
      const data = await parseResponse(response);
      setActiveEndpointId(data?.active_id || endpointId);
      pushStatus(`已切换到 ${data?.name || '目标端点'}`);
    } catch (error) {
      pushStatus(error instanceof Error ? error.message : '切换主聊天端点失败');
    } finally {
      setSwitchingId(null);
    }
  }

  async function saveRoleEndpoints(roleKey: string) {
    setSavingRoles((current) => ({ ...current, [roleKey]: true }));
    try {
      const endpoints = roleEndpoints[roleKey] || [];
      const primary = endpoints.find((endpoint) => endpoint._primary);
      const extras = endpoints.filter((endpoint) => !endpoint._primary);

      if (primary && (primary.configured || primary.base_url || primary.api_key || primary.model)) {
        const primaryResponse = await fetch('/api/config/model', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            role: roleKey,
            base_url: primary.base_url || '',
            api_key: primary.api_key || '',
            model: primary.model || ''
          })
        });
        if (!primaryResponse.ok) throw new Error(await readErrorMessage(primaryResponse, `${roleKey} 主端点保存失败`));
      }

      const extrasResponse = await fetch('/api/config/role-endpoints', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          role: roleKey,
          endpoints: extras.map((endpoint) => ({
            name: endpoint.name,
            provider: endpoint.provider || 'custom',
            base_url: endpoint.base_url,
            api_key: endpoint.api_key,
            model: endpoint.model
          }))
        })
      });
      if (!extrasResponse.ok) throw new Error(await readErrorMessage(extrasResponse, `${roleKey} 扩展端点保存失败`));

      pushStatus(`${roleDefinitions.find((item) => item.key === roleKey)?.label || roleKey} 已保存`);
      await loadAll();
    } catch (error) {
      pushStatus(error instanceof Error ? error.message : `${roleKey} 保存失败`);
    } finally {
      setSavingRoles((current) => ({ ...current, [roleKey]: false }));
    }
  }

  async function testEndpoint(scope: 'chat' | 'role', roleKey: string, clientKey: string) {
    const endpoint =
      scope === 'chat'
        ? chatEndpoints.find((item) => item.clientKey === clientKey)
        : (roleEndpoints[roleKey] || []).find((item) => item.clientKey === clientKey);
    if (!endpoint?.model) {
      pushStatus('请先填写模型名称');
      return;
    }

    const testKey = `${scope}:${roleKey}:${clientKey}`;
    setTestingKeys((current) => ({ ...current, [testKey]: true }));
    setTestResults((current) => ({ ...current, [testKey]: null }));
    try {
      const response = await fetch('/api/config/model/test', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          role: roleKey,
          base_url: endpoint.base_url || '',
          api_key: endpoint.api_key || '',
          model: endpoint.model || ''
        })
      });
      const result = (await parseResponse(response)) as TestResult;
      if (!response.ok) {
        throw new Error(typeof result === 'object' && result && 'error' in result ? result.error || '测试失败' : '测试失败');
      }
      setTestResults((current) => ({ ...current, [testKey]: result }));
    } catch (error) {
      setTestResults((current) => ({
        ...current,
        [testKey]: { status: 'error', error: error instanceof Error ? error.message : '网络请求失败' }
      }));
    } finally {
      setTestingKeys((current) => ({ ...current, [testKey]: false }));
    }
  }

  async function fetchModels(scope: 'chat' | 'role', roleKey: string, clientKey: string) {
    const endpoint =
      scope === 'chat'
        ? chatEndpoints.find((item) => item.clientKey === clientKey)
        : (roleEndpoints[roleKey] || []).find((item) => item.clientKey === clientKey);
    if (!endpoint?.base_url) {
      pushStatus('请先填写 Base URL');
      return;
    }

    const fetchKey = `${scope}:${roleKey}:${clientKey}`;
    setFetchingModels((current) => ({ ...current, [fetchKey]: true }));
    setFetchErrors((current) => ({ ...current, [fetchKey]: '' }));
    try {
      const response = await fetch('/api/endpoints/fetch-models', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ base_url: endpoint.base_url, api_key: endpoint.api_key || '' })
      });
      const data = await parseResponse(response);
      if (!response.ok || data?.status !== 'ok') throw new Error(data?.error || '获取模型列表失败');
      const models = Array.isArray(data?.models) ? (data.models as string[]) : [];
      setFetchedModels((current) => ({ ...current, [fetchKey]: models }));
      if (!endpoint.model && models[0]) {
        if (scope === 'chat') updateChatEndpoint(clientKey, { model: models[0] });
        else updateRoleEndpoint(roleKey, clientKey, { model: models[0] });
      }
    } catch (error) {
      setFetchErrors((current) => ({
        ...current,
        [fetchKey]: error instanceof Error ? error.message : '获取模型列表失败'
      }));
    } finally {
      setFetchingModels((current) => ({ ...current, [fetchKey]: false }));
    }
  }

  function renderProviderSelect(value: string, onChange: (value: string) => void) {
    return (
      <select className="models-panel__select" value={value || 'custom'} onChange={(event) => onChange(event.target.value)}>
        <option value="custom">自定义</option>
        {providerGroups.map((group) => (
          <optgroup key={group.category} label={CATEGORY_LABELS[group.category] || group.category}>
            {providers
              .filter((provider) => provider.category === group.category)
              .map((provider) => (
                <option key={provider.slug} value={provider.slug}>
                  {provider.name}
                </option>
              ))}
          </optgroup>
        ))}
      </select>
    );
  }

  function renderModelChooser(
    scope: 'chat' | 'role',
    roleKey: string,
    endpoint: ChatEndpoint | RoleEndpoint,
    onChangeModel: (value: string) => void
  ) {
    const fetchKey = `${scope}:${roleKey}:${endpoint.clientKey}`;
    const models = fetchedModels[fetchKey] || [];
    const keyword = (modelSearch[fetchKey] || '').trim().toLowerCase();
    const filteredModels = models.filter((item) => !keyword || item.toLowerCase().includes(keyword));
    const presetModels = getProviderModels(endpoint.provider, providers);

    return (
      <div className="models-panel__field models-panel__field--full">
        <div className="models-panel__field-head">
          <span className="models-panel__field-label">Model ID</span>
          <UiButton
            type="button"
            variant="secondary"
            className="models-panel__action-btn models-panel__action-btn--small"
            onClick={() => fetchModels(scope, roleKey, endpoint.clientKey)}
            disabled={!!fetchingModels[fetchKey]}
          >
            {fetchingModels[fetchKey] ? '获取中...' : '获取模型列表'}
          </UiButton>
        </div>
        <input
          type="text"
          className="models-panel__input models-panel__input--mono"
          placeholder="gpt-4o, claude-sonnet..."
          value={endpoint.model}
          onChange={(event) => onChangeModel(event.target.value)}
        />
        {models.length > 0 ? (
          <div className="models-panel__model-picker">
            <input
              type="text"
              className="models-panel__input models-panel__input--search"
              placeholder="筛选已拉取模型..."
              value={modelSearch[fetchKey] || ''}
              onChange={(event) => setModelSearch((current) => ({ ...current, [fetchKey]: event.target.value }))}
            />
            <div className="models-panel__model-list">
              {filteredModels.length > 0 ? (
                filteredModels.map((item) => (
                  <button
                    key={item}
                    type="button"
                    className={`models-panel__model-chip ${endpoint.model === item ? 'is-active' : ''}`}
                    onClick={() => onChangeModel(item)}
                  >
                    {item}
                  </button>
                ))
              ) : (
                <div className="models-panel__hint">没有匹配的模型</div>
              )}
            </div>
          </div>
        ) : null}
        {fetchErrors[fetchKey] ? <div className="models-panel__error-text">{fetchErrors[fetchKey]}</div> : null}
        {presetModels.length > 0 ? (
          <div className="models-panel__preset-list">
            {presetModels.map((item) => (
              <button
                key={item}
                type="button"
                className={`models-panel__preset-chip ${endpoint.model === item ? 'is-active' : ''}`}
                onClick={() => onChangeModel(item)}
              >
                {item}
              </button>
            ))}
          </div>
        ) : null}
      </div>
    );
  }

  function renderTestResult(scope: 'chat' | 'role', roleKey: string, clientKey: string) {
    const testKey = `${scope}:${roleKey}:${clientKey}`;
    const result = testResults[testKey];
    if (!result) return null;
    const ok = result.status === 'ok';
    return (
      <div className={`models-panel__notice ${ok ? 'models-panel__notice--ok' : 'models-panel__notice--error'}`}>
        {ok ? `连通成功：${result.reply || result.model || 'OK'}` : result.error || '连接失败'}
      </div>
    );
  }

  return (
    <div className="models-panel">
      <header className="models-panel__header">
        <div>
          <div className="models-panel__eyebrow">Model Access</div>
          <h4 className="models-panel__title">模型与角色端点</h4>
          <p className="models-panel__meta">统一管理聊天端点、角色覆写端点、模型拉取与网络连通测试。</p>
        </div>
        <UiActionTray className="models-panel__header-actions">
          <UiButton type="button" variant="secondary" className="models-panel__action-btn" onClick={loadAll} disabled={loadState.loading}>
            刷新
          </UiButton>
          <UiButton type="button" variant="primary" className="models-panel__action-btn models-panel__action-btn--primary" onClick={addChatEndpoint} disabled={loadState.loading}>
            新增聊天端点
          </UiButton>
        </UiActionTray>
      </header>

      {loadState.errorText ? <div className="models-panel__notice models-panel__notice--error">{loadState.errorText}</div> : null}
      {loadState.loading ? <div className="models-panel__empty">正在加载模型配置...</div> : null}

      {!loadState.loading ? (
        <>
          <section className="models-panel__section">
            <div className="models-panel__section-head">
              <div>
                <div className="models-panel__section-title">聊天模型端点</div>
                <div className="models-panel__section-desc">管理主聊天模型池，支持一键切换当前激活端点。</div>
              </div>
              <UiButton type="button" variant="primary" className="models-panel__action-btn models-panel__action-btn--primary" onClick={saveChatEndpoints} disabled={savingChat}>
                {savingChat ? '保存中...' : '保存聊天端点'}
              </UiButton>
            </div>

            <div className="models-panel__stack">
              {chatEndpoints.length === 0 ? <div className="models-panel__empty">还没有聊天端点，先新增一个端点开始配置。</div> : null}

              {chatEndpoints.map((endpoint) => {
                const active = !!endpoint.id && endpoint.id === activeEndpointId;
                const expanded = expandedChatKey === endpoint.clientKey || endpoint._new;
                const secretVisible = !!showSecrets[endpoint.clientKey];
                const testKey = `chat:api:${endpoint.clientKey}`;
                return (
                  <article key={endpoint.clientKey} className={`models-panel__card ${active ? 'is-active' : ''}`}>
                    <div
                      className="models-panel__card-head"
                      role="button"
                      tabIndex={0}
                      onClick={() => setExpandedChatKey((current) => (current === endpoint.clientKey ? null : endpoint.clientKey))}
                      onKeyDown={(event) =>
                        onToggleKeyDown(event, () =>
                          setExpandedChatKey((current) => (current === endpoint.clientKey ? null : endpoint.clientKey))
                        )
                      }
                    >
                      <div className="models-panel__card-main">
                        <div className="models-panel__card-title-row">
                          <span className="models-panel__card-title">{endpointLabel(endpoint)}</span>
                          {active ? <UiStatusPill tone="brand" className="models-panel__pill is-accent">Active</UiStatusPill> : null}
                        </div>
                        <div className="models-panel__card-subtitle">
                          <span>{endpoint.provider || 'custom'}</span>
                          <span className="models-panel__dot">•</span>
                          <span>{endpoint.model || '未选择模型'}</span>
                        </div>
                      </div>
                      <UiActionTray className="models-panel__card-actions">
                        {endpoint.id && !active ? (
                          <UiButton
                            type="button"
                            variant="secondary"
                            className="models-panel__action-btn"
                            onClick={(event) => {
                              event.stopPropagation();
                              void switchChatEndpoint(endpoint.id!);
                            }}
                            disabled={switchingId === endpoint.id}
                          >
                            {switchingId === endpoint.id ? '切换中...' : '激活'}
                          </UiButton>
                        ) : null}
                        <CaretDownIcon className={`models-panel__chevron ${expanded ? 'is-open' : ''}`} />
                      </UiActionTray>
                    </div>

                    {expanded ? (
                      <div className="models-panel__card-body">
                        <div className="models-panel__grid">
                          <label className="models-panel__field">
                            <span className="models-panel__field-label">供应商预设</span>
                            {renderProviderSelect(endpoint.provider, (value) => applyProviderToChat(endpoint.clientKey, value))}
                          </label>

                          <label className="models-panel__field">
                            <span className="models-panel__field-label">端点备注</span>
                            <input
                              type="text"
                              className="models-panel__input"
                              placeholder="例如 OpenAI 主端点"
                              value={endpoint.name}
                              onChange={(event) => updateChatEndpoint(endpoint.clientKey, { name: event.target.value })}
                            />
                          </label>

                          <label className="models-panel__field models-panel__field--full">
                            <span className="models-panel__field-label">Base URL</span>
                            <input
                              type="text"
                              className="models-panel__input models-panel__input--mono"
                              placeholder="https://api.example.com/v1"
                              value={endpoint.base_url}
                              onChange={(event) => updateChatEndpoint(endpoint.clientKey, { base_url: event.target.value })}
                            />
                          </label>

                          <label className="models-panel__field models-panel__field--full">
                            <span className="models-panel__field-label">API Key</span>
                            <span className="models-panel__secret-row">
                              <input
                                type={secretVisible ? 'text' : 'password'}
                                className="models-panel__input models-panel__input--mono models-panel__input--secret"
                                placeholder={endpoint.api_key_masked || 'sk-...'}
                                value={endpoint.api_key}
                                onChange={(event) => updateChatEndpoint(endpoint.clientKey, { api_key: event.target.value })}
                              />
                              <UiButton
                                type="button"
                                variant="secondary"
                                className="models-panel__action-btn models-panel__action-btn--small"
                                onClick={() => setShowSecrets((current) => ({ ...current, [endpoint.clientKey]: !current[endpoint.clientKey] }))}
                              >
                                {secretVisible ? '隐藏' : '显示'}
                              </UiButton>
                            </span>
                          </label>

                          {renderModelChooser('chat', 'api', endpoint, (value) => updateChatEndpoint(endpoint.clientKey, { model: value }))}

                          <label className="models-panel__field">
                            <span className="models-panel__field-head">
                              <span className="models-panel__field-label">Temperature</span>
                              <strong>{endpoint.temperature.toFixed(2)}</strong>
                            </span>
                            <input
                              type="range"
                              min="0"
                              max="2"
                              step="0.05"
                              className="models-panel__range"
                              value={endpoint.temperature}
                              onChange={(event) => updateChatEndpoint(endpoint.clientKey, { temperature: Number(event.target.value) })}
                            />
                          </label>

                          <label className="models-panel__field">
                            <span className="models-panel__field-head">
                              <span className="models-panel__field-label">Max Tokens</span>
                              <strong>{endpoint.max_tokens}</strong>
                            </span>
                            <input
                              type="range"
                              min="1024"
                              max="128000"
                              step="1024"
                              className="models-panel__range"
                              value={endpoint.max_tokens}
                              onChange={(event) => updateChatEndpoint(endpoint.clientKey, { max_tokens: Number(event.target.value) })}
                            />
                          </label>
                        </div>

                        {renderTestResult('chat', 'api', endpoint.clientKey)}

                        <UiActionTray className="models-panel__toolbar">
                          <UiButton type="button" variant="danger" className="models-panel__action-btn models-panel__action-btn--danger" onClick={() => deleteChatEndpoint(endpoint.clientKey)}>
                            移除端点
                          </UiButton>
                          <div className="models-panel__spacer" />
                          <UiButton
                            type="button"
                            variant="secondary"
                            className="models-panel__action-btn"
                            onClick={() => void testEndpoint('chat', 'api', endpoint.clientKey)}
                            disabled={!!testingKeys[testKey]}
                          >
                            {testingKeys[testKey] ? '连接中...' : '网络测试'}
                          </UiButton>
                        </UiActionTray>
                      </div>
                    ) : null}
                  </article>
                );
              })}
            </div>
          </section>
          <section className="models-panel__section">
            <div className="models-panel__section-head">
              <div>
                <div className="models-panel__section-title">功能增强端点</div>
                <div className="models-panel__section-desc">为视觉、图像解析、嵌入和 GUI 操作分别指定独立模型。</div>
              </div>
            </div>

            <div className="models-panel__role-grid">
              {roleDefinitions.map((role) => {
                const endpoints = roleEndpoints[role.key] || [];
                return (
                  <article key={role.key} className="models-panel__role-card">
                    <div className="models-panel__role-head">
                      <div>
                        <div className="models-panel__role-title">{role.label}</div>
                        <div className="models-panel__role-desc">{role.desc}</div>
                      </div>
                      <UiActionTray className="models-panel__role-actions">
                        <UiButton type="button" variant="secondary" className="models-panel__action-btn" onClick={() => addRoleEndpoint(role.key)}>
                          新增扩展
                        </UiButton>
                        <UiButton
                          type="button"
                          variant="primary"
                          className="models-panel__action-btn models-panel__action-btn--primary"
                          onClick={() => void saveRoleEndpoints(role.key)}
                          disabled={!!savingRoles[role.key]}
                        >
                          {savingRoles[role.key] ? '保存中...' : '保存'}
                        </UiButton>
                      </UiActionTray>
                    </div>

                    <div className="models-panel__stack">
                      {endpoints.map((endpoint) => {
                        const expanded = expandedRoleKeys[role.key] === endpoint.clientKey || endpoint._new;
                        const secretVisible = !!showSecrets[endpoint.clientKey];
                        const testKey = `role:${role.key}:${endpoint.clientKey}`;
                        return (
                          <div key={endpoint.clientKey} className={`models-panel__subcard ${endpoint._primary ? 'is-primary' : ''}`}>
                            <div
                              className="models-panel__card-head"
                              role="button"
                              tabIndex={0}
                              onClick={() =>
                                setExpandedRoleKeys((current) => ({
                                  ...current,
                                  [role.key]: current[role.key] === endpoint.clientKey ? null : endpoint.clientKey
                                }))
                              }
                              onKeyDown={(event) =>
                                onToggleKeyDown(event, () =>
                                  setExpandedRoleKeys((current) => ({
                                    ...current,
                                    [role.key]: current[role.key] === endpoint.clientKey ? null : endpoint.clientKey
                                  }))
                                )
                              }
                            >
                              <div className="models-panel__card-main">
                                <div className="models-panel__card-title-row">
                                  <span className="models-panel__card-title">{endpointLabel(endpoint)}</span>
                                  {endpoint._primary ? <UiStatusPill tone="neutral" className="models-panel__pill">Primary</UiStatusPill> : null}
                                </div>
                                <div className="models-panel__card-subtitle">
                                  <span>{endpoint.provider || 'custom'}</span>
                                  <span className="models-panel__dot">•</span>
                                  <span>{endpoint.model || '未选择模型'}</span>
                                </div>
                              </div>
                              <CaretDownIcon className={`models-panel__chevron ${expanded ? 'is-open' : ''}`} />
                            </div>

                            {expanded ? (
                              <div className="models-panel__card-body">
                                <div className="models-panel__grid">
                                  <label className="models-panel__field">
                                    <span className="models-panel__field-label">供应商预设</span>
                                    {renderProviderSelect(endpoint.provider, (value) => applyProviderToRole(role.key, endpoint.clientKey, value))}
                                  </label>

                                  <label className="models-panel__field">
                                    <span className="models-panel__field-label">端点名称</span>
                                    <input
                                      type="text"
                                      className="models-panel__input"
                                      placeholder={endpoint._primary ? `${role.label} 主端点` : '扩展端点名称'}
                                      value={endpoint.name}
                                      onChange={(event) => updateRoleEndpoint(role.key, endpoint.clientKey, { name: event.target.value })}
                                    />
                                  </label>

                                  <label className="models-panel__field models-panel__field--full">
                                    <span className="models-panel__field-label">Base URL</span>
                                    <input
                                      type="text"
                                      className="models-panel__input models-panel__input--mono"
                                      placeholder="https://api.example.com/v1"
                                      value={endpoint.base_url}
                                      onChange={(event) => updateRoleEndpoint(role.key, endpoint.clientKey, { base_url: event.target.value })}
                                    />
                                  </label>

                                  <label className="models-panel__field models-panel__field--full">
                                    <span className="models-panel__field-label">API Key</span>
                                    <span className="models-panel__secret-row">
                                      <input
                                        type={secretVisible ? 'text' : 'password'}
                                        className="models-panel__input models-panel__input--mono models-panel__input--secret"
                                        placeholder={endpoint.api_key_masked || 'sk-...'}
                                        value={endpoint.api_key}
                                        onChange={(event) => updateRoleEndpoint(role.key, endpoint.clientKey, { api_key: event.target.value })}
                                      />
                                      <UiButton
                                        type="button"
                                        variant="secondary"
                                        className="models-panel__action-btn models-panel__action-btn--small"
                                        onClick={() => setShowSecrets((current) => ({ ...current, [endpoint.clientKey]: !current[endpoint.clientKey] }))}
                                      >
                                        {secretVisible ? '隐藏' : '显示'}
                                      </UiButton>
                                    </span>
                                  </label>

                                  {renderModelChooser('role', role.key, endpoint, (value) =>
                                    updateRoleEndpoint(role.key, endpoint.clientKey, { model: value })
                                  )}
                                </div>

                                {renderTestResult('role', role.key, endpoint.clientKey)}

                                <UiActionTray className="models-panel__toolbar">
                                  {!endpoint._primary ? (
                                    <UiButton
                                      type="button"
                                      variant="danger"
                                      className="models-panel__action-btn models-panel__action-btn--danger"
                                      onClick={() => deleteRoleEndpoint(role.key, endpoint.clientKey)}
                                    >
                                      删除扩展
                                    </UiButton>
                                  ) : (
                                    <div className="models-panel__hint">Primary 端点会写入 config.json 的顶层角色配置。</div>
                                  )}
                                  <div className="models-panel__spacer" />
                                  <UiButton
                                    type="button"
                                    variant="secondary"
                                    className="models-panel__action-btn"
                                    onClick={() => void testEndpoint('role', role.key, endpoint.clientKey)}
                                    disabled={!!testingKeys[testKey]}
                                  >
                                    {testingKeys[testKey] ? '连接中...' : '网络测试'}
                                  </UiButton>
                                </UiActionTray>
                              </div>
                            ) : null}
                          </div>
                        );
                      })}
                    </div>
                  </article>
                );
              })}
            </div>
          </section>
        </>
      ) : null}

      {statusText ? <div className="models-panel__notice models-panel__notice--status">{statusText}</div> : null}
    </div>
  );
}

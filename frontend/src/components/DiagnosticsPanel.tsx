import { useEffect, useState } from 'react';
import { useWorkspaceShellBridge } from '../hooks/useWorkspaceShellBridge';
import { UiActionTray } from './ui/UiActionTray';
import { UiButton } from './ui/UiButton';
import { UiStatusPill } from './ui/UiStatusPill';

type DiagnosticsPayload = {
  system?: {
    os?: string;
    python_version?: string;
    python_executable?: string;
    app_dir?: string;
    frozen?: boolean;
    pid?: number;
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
  process_runtime?: ProcessRuntimePayload;
  timestamp?: number;
};

type ProcessRunRecord = {
  record_id: string;
  file_path?: string;
  pid?: number | null;
  started_at?: string;
  mode?: string;
  version?: string;
  app_dir?: string;
  executable?: string;
  is_frozen?: boolean;
  runtime_status?: 'healthy_current' | 'running_conflict' | 'stale_record' | string;
  cleanup_allowed?: boolean;
};

type RunningProcessSummary = {
  pid: number;
  status: 'healthy_current' | 'running_conflict' | 'orphan_process' | string;
  name?: string;
  executable?: string;
  cmdline?: string[];
  started_at?: string;
  mode?: string;
  record_id?: string | null;
  summary?: string;
  cleanup_allowed?: boolean;
};

type ProcessConflictItem = {
  type: 'running_conflict' | 'stale_record' | 'orphan_process' | 'healthy_current' | string;
  pid?: number | null;
  record_id?: string | null;
  file_path?: string | null;
  summary?: string;
  cleanup_allowed?: boolean;
};

type ProcessRuntimePayload = {
  current_pid?: number;
  current_record?: {
    pid?: number;
    started_at?: string;
    mode?: string;
    version?: string;
    executable?: string;
    is_frozen?: boolean;
  };
  run_records?: ProcessRunRecord[];
  running_processes?: RunningProcessSummary[];
  conflicts?: ProcessConflictItem[];
  cleanup_supported?: boolean;
};

type ServiceHealthPayload = {
  status?: string;
  pid?: number;
  version?: string;
  started_at?: string;
  uptime_seconds?: number;
  restart_mode?: string;
};

type EndpointHealthResult = {
  name: string;
  label?: string;
  kind?: string;
  role?: string;
  status: 'healthy' | 'unhealthy' | 'unknown' | string;
  latency_ms?: number | null;
  error?: string | null;
  error_code?: string | null;
  hint?: string | null;
  configured?: boolean;
  last_checked_at?: string | null;
};

type EndpointSummary = {
  name: string;
  label: string;
  kind: 'chat' | 'role';
  role: string;
  model: string;
  baseUrl: string;
  keyPresent: boolean;
  active: boolean;
};

type EndpointsPayload = {
  endpoints?: Array<{
    id?: string | null;
    name?: string;
    model?: string;
    base_url?: string;
    api_key?: string;
    api_key_masked?: string;
  }>;
  active_id?: string | null;
};

type ModelConfigPayload = {
  config?: Record<
    string,
    {
      base_url?: string;
      api_key?: string;
      api_key_masked?: string;
      model?: string;
      configured?: boolean;
    }
  >;
};

type IMBotsPayload = {
  bots?: Array<{
    id: string;
    name: string;
    platform: string;
    enabled: boolean;
    credentials?: Record<string, unknown>;
  }>;
};

type IMChannelPayload = {
  channels?: Array<{
    channel_name?: string;
    status?: string;
    stream_state?: string | null;
    last_error?: string | null;
    session_count?: number;
    last_active?: string | null;
  }>;
};

type IMBotSummary = {
  id: string;
  name: string;
  platform: string;
  enabled: boolean;
  channelName: string;
  missingFields: string[];
};

type IMRuntimeState = {
  status?: string;
  stream_state?: string | null;
  last_error?: string | null;
  session_count?: number;
  last_active?: string | null;
};

const ROLE_LABELS: Record<string, string> = {
  api: '主模型',
  vision: '视觉模型',
  image_analyzer: '图像解析',
  embedding: '嵌入模型',
  autogui: 'GUI 操作'
};

const IM_REQUIRED_FIELDS: Record<string, string[]> = {
  telegram: ['bot_token'],
  feishu: ['app_id', 'app_secret'],
  dingtalk: ['client_id', 'client_secret']
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

function formatIsoTime(value?: string | null) {
  if (!value) return '未检测';
  try {
    return new Date(value).toLocaleString('zh-CN', { hour12: false });
  } catch {
    return value;
  }
}

function truncateText(value: string, max = 56) {
  if (!value) return '';
  return value.length > max ? `${value.slice(0, max)}…` : value;
}

function formatDuration(seconds?: number) {
  if (typeof seconds !== 'number' || Number.isNaN(seconds) || seconds < 0) return '未知';
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  const remain = seconds % 60;
  if (minutes < 60) return remain > 0 ? `${minutes}m ${remain}s` : `${minutes}m`;
  const hours = Math.floor(minutes / 60);
  const minuteRemain = minutes % 60;
  return minuteRemain > 0 ? `${hours}h ${minuteRemain}m` : `${hours}h`;
}

function buildEndpointSummaries(
  endpointsPayload: EndpointsPayload,
  modelConfigPayload: ModelConfigPayload
): EndpointSummary[] {
  const summaries: EndpointSummary[] = [];
  const chatEndpoints = Array.isArray(endpointsPayload?.endpoints) ? endpointsPayload.endpoints : [];
  const activeId = endpointsPayload?.active_id || null;
  const config = modelConfigPayload?.config || {};

  chatEndpoints.forEach((endpoint) => {
    const endpointId = String(endpoint.id || endpoint.name || endpoint.model || '');
    if (!endpointId) return;
    summaries.push({
      name: `chat:${endpointId}`,
      label: endpoint.name || endpoint.model || endpointId,
      kind: 'chat',
      role: 'api',
      model: endpoint.model || '',
      baseUrl: endpoint.base_url || '',
      keyPresent: !!(endpoint.api_key || endpoint.api_key_masked),
      active: activeId === endpoint.id
    });
  });

  const roleKeys: Array<'api' | 'vision' | 'image_analyzer' | 'embedding' | 'autogui'> = [
    'api',
    'vision',
    'image_analyzer',
    'embedding',
    'autogui'
  ];

  roleKeys.forEach((role) => {
    const section = config[role];
    if (!section || typeof section !== 'object') return;
    const hasAnyValue = !!(section.base_url || section.model || section.api_key || section.api_key_masked);
    if (!hasAnyValue) return;
    if (role === 'api' && summaries.length > 0) return;
    summaries.push({
      name: `role:${role}`,
      label: ROLE_LABELS[role] || role,
      kind: 'role',
      role,
      model: section.model || '',
      baseUrl: section.base_url || '',
      keyPresent: !!(section.api_key || section.api_key_masked),
      active: role === 'api' && summaries.length === 0
    });
  });

  return summaries;
}

function buildIMBotSummaries(payload: IMBotsPayload): IMBotSummary[] {
  const bots = Array.isArray(payload?.bots) ? payload.bots : [];
  return bots.map((bot) => {
    const requiredFields = IM_REQUIRED_FIELDS[bot.platform] || [];
    const credentials = bot.credentials || {};
    const missingFields = requiredFields.filter((field) => !String(credentials[field] || '').trim());
    return {
      id: bot.id,
      name: bot.name || bot.id,
      platform: bot.platform,
      enabled: !!bot.enabled,
      channelName: `${bot.platform}@@${bot.id}`,
      missingFields
    };
  });
}

function runtimeStatusClass(status: 'healthy' | 'unhealthy' | 'unknown') {
  if (status === 'healthy') return 'is-healthy';
  if (status === 'unhealthy') return 'is-error';
  return 'is-neutral';
}

function runtimeStatusTone(status: 'healthy' | 'unhealthy' | 'unknown'): 'success' | 'danger' | 'disabled' {
  if (status === 'healthy') return 'success';
  if (status === 'unhealthy') return 'danger';
  return 'disabled';
}

async function copyText(value: string) {
  if (!value) return false;
  if (!navigator.clipboard?.writeText) return false;
  try {
    await navigator.clipboard.writeText(value);
    return true;
  } catch {
    return false;
  }
}

function deriveEndpointRuntimeStatus(
  endpoint: EndpointSummary,
  resultItem?: EndpointHealthResult
): {
  status: 'healthy' | 'unhealthy' | 'unknown';
  label: string;
  hint: string;
} {
  const locallyConfigured = !!(endpoint.baseUrl && endpoint.model);

  if (resultItem) {
    if (resultItem.status === 'healthy') {
      return {
        status: 'healthy',
        label: `${resultItem.latency_ms ?? 0}ms`,
        hint: endpoint.keyPresent ? '' : '未提供 API Key；若服务要求鉴权，请补充后再测'
      };
    }

    if (resultItem.status === 'unknown') {
      return {
        status: 'unknown',
        label: '配置缺失',
        hint: resultItem.hint || '请先补全模型配置'
      };
    }

    return {
      status: 'unhealthy',
      label: '异常',
      hint: resultItem.hint || '请复制错误详情后继续排查'
    };
  }

  if (!locallyConfigured) {
    return {
      status: 'unknown',
      label: '配置缺失',
      hint: '请补全 Base URL 与模型名后再检测'
    };
  }

  return {
    status: 'unknown',
    label: '未检测',
    hint: endpoint.keyPresent ? '点击 Check 发起只读探测' : '可先检测；若服务要求鉴权，建议补充 API Key'
  };
}

function deriveProcessStatus(status?: string): {
  tone: 'healthy' | 'unhealthy' | 'unknown';
  label: string;
} {
  if (status === 'healthy_current') {
    return { tone: 'healthy', label: '当前服务' };
  }
  if (status === 'running_conflict') {
    return { tone: 'unhealthy', label: '运行冲突' };
  }
  if (status === 'orphan_process') {
    return { tone: 'unhealthy', label: '孤儿进程' };
  }
  if (status === 'stale_record') {
    return { tone: 'unknown', label: '残留记录' };
  }
  return { tone: 'unknown', label: '未知' };
}

export function DiagnosticsPanel() {
  const { snapshot } = useWorkspaceShellBridge();
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<DiagnosticsPayload | null>(null);
  const [errorText, setErrorText] = useState('');
  const [pokeStatus, setPokeStatus] = useState('');
  const [runtimeNotice, setRuntimeNotice] = useState('');

  const [overviewLoaded, setOverviewLoaded] = useState(false);
  const [serviceStatus, setServiceStatus] = useState<'online' | 'offline' | 'unknown'>('unknown');
  const [serviceInfo, setServiceInfo] = useState<ServiceHealthPayload | null>(null);
  const [endpointSummaries, setEndpointSummaries] = useState<EndpointSummary[]>([]);
  const [endpointResults, setEndpointResults] = useState<Record<string, EndpointHealthResult>>({});
  const [endpointChecking, setEndpointChecking] = useState<string | null>(null);
  const [imBots, setImBots] = useState<IMBotSummary[]>([]);
  const [imRuntime, setImRuntime] = useState<Record<string, IMRuntimeState>>({});
  const [imChecking, setImChecking] = useState(false);
  const [processRefreshing, setProcessRefreshing] = useState(false);
  const [processCleanupKey, setProcessCleanupKey] = useState<string | null>(null);

  useEffect(() => {
    if (!snapshot.showSettings || snapshot.settingsTab !== 'diagnostics') return;
    if (!result && !running) {
      void runDiagnostics();
    }
    if (!overviewLoaded) {
      void loadRuntimeOverview();
    }
  }, [snapshot.showSettings, snapshot.settingsTab, result, running, overviewLoaded]);

  function pushRuntimeNotice(message: string) {
    setRuntimeNotice(message);
    window.clearTimeout((pushRuntimeNotice as typeof pushRuntimeNotice & { timer?: number }).timer);
    (pushRuntimeNotice as typeof pushRuntimeNotice & { timer?: number }).timer = window.setTimeout(() => {
      setRuntimeNotice('');
    }, 3200);
  }

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

  async function refreshProcessRuntime(announce = true) {
    setProcessRefreshing(true);
    try {
      const response = await fetch('/api/diagnostics');
      if (!response.ok) {
        throw new Error(await readErrorMessage(response, '进程运行态刷新失败'));
      }
      const payload = (await parseResponse(response)) as DiagnosticsPayload;
      setResult(payload);
      if (announce) {
        pushRuntimeNotice('进程运行态已刷新');
      }
    } catch (error) {
      pushRuntimeNotice(error instanceof Error ? error.message : '进程运行态刷新失败');
    } finally {
      setProcessRefreshing(false);
    }
  }

  async function loadRuntimeOverview() {
    setOverviewLoaded(true);

    const servicePromise = (async () => {
      try {
        const response = await fetch('/api/health');
        if (!response.ok) {
          setServiceStatus('offline');
          setServiceInfo(null);
          return;
        }
        const payload = (await parseResponse(response)) as ServiceHealthPayload;
        setServiceInfo(payload);
        setServiceStatus(payload?.status === 'ok' ? 'online' : 'offline');
      } catch {
        setServiceStatus('offline');
        setServiceInfo(null);
      }
    })();

    const endpointPromise = (async () => {
      try {
        const [endpointsResponse, modelConfigResponse] = await Promise.all([
          fetch('/api/endpoints'),
          fetch('/api/config/model')
        ]);
        if (!endpointsResponse.ok || !modelConfigResponse.ok) return;
        const [endpointsPayload, modelConfigPayload] = (await Promise.all([
          parseResponse(endpointsResponse),
          parseResponse(modelConfigResponse)
        ])) as [EndpointsPayload, ModelConfigPayload];
        setEndpointSummaries(buildEndpointSummaries(endpointsPayload, modelConfigPayload));
      } catch {
        setEndpointSummaries([]);
      }
    })();

    const imBotsPromise = (async () => {
      try {
        const response = await fetch('/api/im/bots');
        if (!response.ok) return;
        const payload = (await parseResponse(response)) as IMBotsPayload;
        setImBots(buildIMBotSummaries(payload));
      } catch {
        setImBots([]);
      }
    })();

    await Promise.allSettled([servicePromise, endpointPromise, imBotsPromise]);
  }

  async function runEndpointHealthCheck(endpointName?: string) {
    const checkingKey = endpointName || 'all';
    setEndpointChecking(checkingKey);
    try {
      const response = await fetch('/api/health/check', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(endpointName ? { endpoint_name: endpointName } : {})
      });
      if (!response.ok) {
        throw new Error(await readErrorMessage(response, '端点测活失败'));
      }
      const payload = (await parseResponse(response)) as { results?: EndpointHealthResult[] };
      const nextResults = Array.isArray(payload?.results) ? payload.results : [];
      setEndpointResults((current) => {
        const next = { ...current };
        nextResults.forEach((item) => {
          next[item.name] = item;
        });
        return next;
      });
      pushRuntimeNotice(endpointName ? '端点状态已刷新' : '所有端点状态已刷新');
    } catch (error) {
      pushRuntimeNotice(error instanceof Error ? error.message : '端点测活失败');
    } finally {
      setEndpointChecking(null);
    }
  }

  async function refreshIMRuntimeStatus() {
    setImChecking(true);
    try {
      const response = await fetch('/api/im/channels');
      if (!response.ok) {
        throw new Error(await readErrorMessage(response, 'IM 通道状态读取失败'));
      }
      const payload = (await parseResponse(response)) as IMChannelPayload;
      const nextState: Record<string, IMRuntimeState> = {};
      (payload.channels || []).forEach((channel) => {
        const channelName = String(channel.channel_name || '');
        if (!channelName) return;
        nextState[channelName] = {
          status: channel.status,
          stream_state: channel.stream_state || null,
          last_error: channel.last_error || null,
          session_count: channel.session_count ?? 0,
          last_active: channel.last_active || null
        };
      });
      setImRuntime(nextState);
      pushRuntimeNotice('IM 通道状态已刷新');
    } catch (error) {
      pushRuntimeNotice(error instanceof Error ? error.message : 'IM 通道状态读取失败');
    } finally {
      setImChecking(false);
    }
  }

  async function cleanupProcessConflict(target: ProcessConflictItem) {
    const cleanupKey = target.record_id || (typeof target.pid === 'number' ? `pid:${target.pid}` : 'unknown');
    setProcessCleanupKey(cleanupKey);
    try {
      const response = await fetch('/api/diagnostics/process/cleanup', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          target_pids: typeof target.pid === 'number' ? [target.pid] : [],
          target_records: target.record_id ? [target.record_id] : []
        })
      });
      if (!response.ok) {
        throw new Error(await readErrorMessage(response, '进程清理失败'));
      }
      const payload = (await parseResponse(response)) as {
        results?: Array<{ status?: string; error?: string | null }>;
      };
      const failed = (payload.results || []).find((item) => item.status === 'failed');
      const skipped = (payload.results || []).find((item) => item.status === 'skipped' && item.error);
      await refreshProcessRuntime(false);
      if (failed?.error) {
        pushRuntimeNotice(`清理失败：${failed.error}`);
      } else if (skipped?.error) {
        pushRuntimeNotice(skipped.error);
      } else {
        pushRuntimeNotice('进程残留已清理并刷新');
      }
    } catch (error) {
      pushRuntimeNotice(error instanceof Error ? error.message : '进程清理失败');
    } finally {
      setProcessCleanupKey(null);
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
  const serviceSummaryLabel =
    serviceStatus === 'online' ? '在线' : serviceStatus === 'offline' ? '离线' : '未知';
  const restartModeLabel = result?.restart?.mode || 'unknown';
  const processRuntime = result?.process_runtime;
  const endpointStats = endpointSummaries.reduce(
    (acc, endpoint) => {
      const runtime = deriveEndpointRuntimeStatus(endpoint, endpointResults[endpoint.name]);
      acc.total += 1;
      acc[runtime.status] += 1;
      return acc;
    },
    { total: 0, healthy: 0, unhealthy: 0, unknown: 0 }
  );
  const imStats = imBots.reduce(
    (acc, bot) => {
      acc.total += 1;
      if (!bot.enabled) {
        acc.disabled += 1;
        return acc;
      }
      if (bot.missingFields.length > 0) {
        acc.misconfigured += 1;
        return acc;
      }
      const runtime = imRuntime[bot.channelName];
      if (!runtime) {
        acc.unknown += 1;
        return acc;
      }
      if (runtime.status === 'online') acc.online += 1;
      else acc.offline += 1;
      return acc;
    },
    { total: 0, online: 0, offline: 0, unknown: 0, disabled: 0, misconfigured: 0 }
  );
  const processStats = {
    runRecords: processRuntime?.run_records?.length || 0,
    running: processRuntime?.running_processes?.length || 0,
    conflicts: processRuntime?.conflicts?.length || 0
  };

  return (
    <div className="diagnostics-panel">
      <header className="diagnostics-panel__header">
        <div>
          <div className="diagnostics-panel__eyebrow">Runtime Diagnostics</div>
          <h4 className="diagnostics-panel__title">运行时自检中心</h4>
          <p className="diagnostics-panel__meta">区分环境诊断与运行时测活，帮助快速定位服务、模型端点和 IM 通道问题。</p>
        </div>

        <UiActionTray className="diagnostics-panel__toolbar diagnostics-panel__toolbar-tray">
          <UiButton type="button" variant="secondary" className="diagnostics-panel__action-btn" onClick={runDiagnostics} disabled={running}>
            {running ? '诊断中...' : '运行环境诊断'}
          </UiButton>
          <UiButton
            type="button"
            variant="secondary"
            className="diagnostics-panel__action-btn"
            onClick={() => {
              void loadRuntimeOverview();
            }}
          >
            刷新运行概览
          </UiButton>
          <UiButton
            type="button"
            variant="secondary"
            className="diagnostics-panel__action-btn"
            onClick={() => {
              window.location.href = '/api/diagnostics/export';
            }}
            disabled={!result}
          >
            导出报告
          </UiButton>
        </UiActionTray>
      </header>

      {errorText ? <div className="diagnostics-panel__notice diagnostics-panel__notice--error">{errorText}</div> : null}
      {runtimeNotice ? <div className="diagnostics-panel__notice diagnostics-panel__notice--status">{runtimeNotice}</div> : null}
      {running && !result ? <div className="diagnostics-panel__empty">正在采集系统诊断信息...</div> : null}

      <div className="diagnostics-panel__summary-grid">
        <article className="diagnostics-panel__summary-card">
          <div className="diagnostics-panel__summary-label">服务状态</div>
          <div className={`diagnostics-panel__summary-value ${runtimeStatusClass(serviceStatus === 'online' ? 'healthy' : serviceStatus === 'offline' ? 'unhealthy' : 'unknown')}`}>
            {serviceSummaryLabel}
          </div>
        </article>

        <article className="diagnostics-panel__summary-card">
          <div className="diagnostics-panel__summary-label">重启模式</div>
          <div className="diagnostics-panel__summary-value">{restartModeLabel}</div>
        </article>

        <article className="diagnostics-panel__summary-card">
          <div className="diagnostics-panel__summary-label">网络连通性</div>
          <div className={`diagnostics-panel__summary-value ${connectivity?.status === 'ok' ? 'is-healthy' : 'is-error'}`}>
            {connectivity?.status === 'ok' ? `正常 (${connectivity.latency_ms}ms)` : connectivity?.error || '失败'}
          </div>
        </article>
      </div>

      <section className="diagnostics-panel__card">
        <div className="diagnostics-panel__runtime-head">
          <div>
            <h5 className="diagnostics-panel__card-title">运行时概览</h5>
            <p className="diagnostics-panel__card-desc">这里展示当前服务在线状态与诊断页可见的基础运行信息，不触发额外模型调用。</p>
          </div>
        </div>
        <div className="diagnostics-panel__runtime-grid">
          <article className="diagnostics-panel__runtime-item">
            <div className="diagnostics-panel__runtime-main">
              <strong>后端服务</strong>
              <span>{serviceStatus === 'online' ? '接口可访问' : serviceStatus === 'offline' ? '接口不可访问' : '尚未检测'}</span>
            </div>
            <UiStatusPill tone={runtimeStatusTone(serviceStatus === 'online' ? 'healthy' : serviceStatus === 'offline' ? 'unhealthy' : 'unknown')} className={`diagnostics-panel__status-pill ${runtimeStatusClass(serviceStatus === 'online' ? 'healthy' : serviceStatus === 'offline' ? 'unhealthy' : 'unknown')}`}>
              {serviceSummaryLabel}
            </UiStatusPill>
          </article>
          <article className="diagnostics-panel__runtime-item">
            <div className="diagnostics-panel__runtime-main">
              <strong>服务运行态</strong>
              <span>
                PID {serviceInfo?.pid || result?.system?.pid || '未知'} · v{serviceInfo?.version || 'unknown'}
              </span>
            </div>
            <UiStatusPill tone={runtimeStatusTone(result ? 'healthy' : 'unknown')} className={`diagnostics-panel__status-pill ${runtimeStatusClass(result ? 'healthy' : 'unknown')}`}>
              {serviceInfo?.uptime_seconds ? formatDuration(serviceInfo.uptime_seconds) : result ? '已加载' : '未加载'}
            </UiStatusPill>
          </article>
          <article className="diagnostics-panel__runtime-item">
            <div className="diagnostics-panel__runtime-main">
              <strong>重启能力</strong>
              <span>{result?.restart?.reason || `模式：${serviceInfo?.restart_mode || restartModeLabel}`}</span>
            </div>
            <UiStatusPill
              tone={runtimeStatusTone(result?.restart?.supported ? 'healthy' : 'unhealthy')}
              className={`diagnostics-panel__status-pill ${runtimeStatusClass(result?.restart?.supported ? 'healthy' : 'unhealthy')}`}
            >
              {result?.restart?.supported ? '支持' : '受限'}
            </UiStatusPill>
          </article>
        </div>
      </section>

      <section className="diagnostics-panel__card">
        <div className="diagnostics-panel__runtime-head">
          <div>
            <h5 className="diagnostics-panel__card-title">进程残留与冲突</h5>
            <p className="diagnostics-panel__card-desc">识别旧实例、孤儿进程和残留运行记录；清理动作仅针对明确可处理目标，绝不处理当前活跃后端 PID。</p>
            <div className="diagnostics-panel__list-meta">
              <span>记录：{processStats.runRecords}</span>
              <span>·</span>
              <span>运行中：{processStats.running}</span>
              <span>·</span>
              <span>冲突：{processStats.conflicts}</span>
            </div>
          </div>
          <UiButton
            type="button"
            variant="secondary"
            className="diagnostics-panel__action-btn"
            onClick={() => {
              void refreshProcessRuntime();
            }}
            disabled={processRefreshing}
          >
            {processRefreshing ? '刷新中...' : '刷新进程状态'}
          </UiButton>
        </div>

        <div className="diagnostics-panel__runtime-grid">
          <article className="diagnostics-panel__runtime-item">
            <div className="diagnostics-panel__runtime-main">
              <strong>当前服务 PID</strong>
              <span>{processRuntime?.current_pid || serviceInfo?.pid || '未知'}</span>
            </div>
            <UiStatusPill tone={runtimeStatusTone(serviceStatus === 'online' ? 'healthy' : 'unknown')} className={`diagnostics-panel__status-pill ${runtimeStatusClass(serviceStatus === 'online' ? 'healthy' : 'unknown')}`}>
              {serviceSummaryLabel}
            </UiStatusPill>
          </article>
          <article className="diagnostics-panel__runtime-item">
            <div className="diagnostics-panel__runtime-main">
              <strong>当前记录模式</strong>
              <span>{processRuntime?.current_record?.mode || serviceInfo?.restart_mode || restartModeLabel}</span>
            </div>
            <UiStatusPill tone={runtimeStatusTone(processStats.conflicts > 0 ? 'unhealthy' : 'healthy')} className={`diagnostics-panel__status-pill ${runtimeStatusClass(processStats.conflicts > 0 ? 'unhealthy' : 'healthy')}`}>
              {processStats.conflicts > 0 ? '需处理' : '正常'}
            </UiStatusPill>
          </article>
          <article className="diagnostics-panel__runtime-item">
            <div className="diagnostics-panel__runtime-main">
              <strong>当前记录时间</strong>
              <span>{formatIsoTime(processRuntime?.current_record?.started_at || serviceInfo?.started_at)}</span>
            </div>
            <UiStatusPill tone={runtimeStatusTone(processRuntime?.cleanup_supported ? 'healthy' : 'unknown')} className={`diagnostics-panel__status-pill ${runtimeStatusClass(processRuntime?.cleanup_supported ? 'healthy' : 'unknown')}`}>
              {processRuntime?.cleanup_supported ? '可清理' : '只读'}
            </UiStatusPill>
          </article>
        </div>

        <div className="diagnostics-panel__stack">
          {(processRuntime?.running_processes || []).map((item) => {
            const statusInfo = deriveProcessStatus(item.status);
            return (
              <article key={`proc-${item.pid}-${item.record_id || 'none'}`} className="diagnostics-panel__list-item">
                <div className="diagnostics-panel__list-main">
                  <div className="diagnostics-panel__list-title-row">
                    <strong>{item.name || `PID ${item.pid}`}</strong>
                    <span className="diagnostics-panel__mini-muted">PID {item.pid}</span>
                    {item.record_id ? <span className="diagnostics-panel__mini-pill">{item.record_id}</span> : null}
                  </div>
                  <div className="diagnostics-panel__list-subtitle">
                    <span>{item.summary || '进程状态已采集'}</span>
                  </div>
                  <div className="diagnostics-panel__list-meta">
                    <span>{item.executable || '未知可执行文件'}</span>
                    {item.started_at ? (
                      <>
                        <span>·</span>
                        <span>启动：{formatIsoTime(item.started_at)}</span>
                      </>
                    ) : null}
                    {item.mode ? (
                      <>
                        <span>·</span>
                        <span>模式：{item.mode}</span>
                      </>
                    ) : null}
                  </div>
                </div>
                <div className="diagnostics-panel__list-actions">
                  <UiStatusPill tone={runtimeStatusTone(statusInfo.tone)} className={`diagnostics-panel__status-pill ${runtimeStatusClass(statusInfo.tone)}`}>{statusInfo.label}</UiStatusPill>
                </div>
              </article>
            );
          })}
          {processRuntime && (processRuntime.running_processes || []).length === 0 ? (
            <div className="diagnostics-panel__empty">当前未发现额外的服务进程。</div>
          ) : null}
        </div>

        <div className="diagnostics-panel__stack">
          <h6 className="diagnostics-panel__section-subtitle">冲突与残留记录</h6>
          {(processRuntime?.conflicts || []).length === 0 ? (
            <div className="diagnostics-panel__empty">没有发现进程冲突或残留运行记录。</div>
          ) : (
            (processRuntime?.conflicts || []).map((conflict) => {
              const statusInfo = deriveProcessStatus(conflict.type);
              const cleanupKey = conflict.record_id || (typeof conflict.pid === 'number' ? `pid:${conflict.pid}` : `${conflict.type}-none`);
              return (
                <article key={`conflict-${conflict.record_id || conflict.pid || conflict.type}`} className="diagnostics-panel__list-item">
                  <div className="diagnostics-panel__list-main">
                    <div className="diagnostics-panel__list-title-row">
                      <strong>{statusInfo.label}</strong>
                      {typeof conflict.pid === 'number' ? <span className="diagnostics-panel__mini-muted">PID {conflict.pid}</span> : null}
                      {conflict.record_id ? <span className="diagnostics-panel__mini-pill">{conflict.record_id}</span> : null}
                    </div>
                    <div className="diagnostics-panel__list-subtitle">
                      <span>{conflict.summary || '检测到需关注的进程问题'}</span>
                    </div>
                  </div>
                  <div className="diagnostics-panel__list-actions">
                    <UiStatusPill tone={runtimeStatusTone(statusInfo.tone)} className={`diagnostics-panel__status-pill ${runtimeStatusClass(statusInfo.tone)}`}>{statusInfo.label}</UiStatusPill>
                    {conflict.cleanup_allowed ? (
                      <UiButton
                        type="button"
                        variant="danger"
                        className="diagnostics-panel__action-btn diagnostics-panel__action-btn--small diagnostics-panel__action-btn--danger"
                        onClick={() => {
                          void cleanupProcessConflict(conflict);
                        }}
                        disabled={processCleanupKey !== null}
                      >
                        {processCleanupKey === cleanupKey ? '清理中...' : 'Cleanup'}
                      </UiButton>
                    ) : null}
                  </div>
                </article>
              );
            })
          )}
        </div>

        <div className="diagnostics-panel__stack">
          <h6 className="diagnostics-panel__section-subtitle">运行记录</h6>
          {(processRuntime?.run_records || []).length === 0 ? (
            <div className="diagnostics-panel__empty">当前还没有持久化运行记录。</div>
          ) : (
            (processRuntime?.run_records || []).map((record) => {
              const statusInfo = deriveProcessStatus(record.runtime_status);
              return (
                <article key={record.record_id} className="diagnostics-panel__list-item">
                  <div className="diagnostics-panel__list-main">
                    <div className="diagnostics-panel__list-title-row">
                      <strong>{record.record_id}</strong>
                      {typeof record.pid === 'number' ? <span className="diagnostics-panel__mini-muted">PID {record.pid}</span> : null}
                      <span className="diagnostics-panel__mini-muted">{record.mode || 'unknown'}</span>
                    </div>
                    <div className="diagnostics-panel__list-subtitle">
                      <span>{record.executable || '未知可执行文件'}</span>
                    </div>
                    <div className="diagnostics-panel__list-meta">
                      <span>写入时间：{formatIsoTime(record.started_at)}</span>
                      <span>·</span>
                      <span>{record.is_frozen ? '打包运行' : '源码运行'}</span>
                    </div>
                </div>
                <div className="diagnostics-panel__list-actions">
                  <UiStatusPill tone={runtimeStatusTone(statusInfo.tone)} className={`diagnostics-panel__status-pill ${runtimeStatusClass(statusInfo.tone)}`}>{statusInfo.label}</UiStatusPill>
                </div>
              </article>
            );
            })
          )}
        </div>
      </section>

      <section className="diagnostics-panel__card">
        <div className="diagnostics-panel__runtime-head">
          <div>
            <h5 className="diagnostics-panel__card-title">LLM Endpoints</h5>
            <p className="diagnostics-panel__card-desc">点击检测时才会发起只读探测，不修改当前运行中的模型健康状态。</p>
            <div className="diagnostics-panel__list-meta">
              <span>总数：{endpointStats.total}</span>
              <span>·</span>
              <span>正常：{endpointStats.healthy}</span>
              <span>·</span>
              <span>异常：{endpointStats.unhealthy}</span>
              <span>·</span>
              <span>未知：{endpointStats.unknown}</span>
            </div>
          </div>
          <UiButton
            type="button"
            variant="secondary"
            className="diagnostics-panel__action-btn"
            onClick={() => {
              void runEndpointHealthCheck();
            }}
            disabled={endpointChecking !== null}
          >
            {endpointChecking === 'all' ? '检测中...' : 'Check All'}
          </UiButton>
        </div>

        {endpointSummaries.length === 0 ? (
          <div className="diagnostics-panel__empty">当前没有可检测的模型端点。</div>
        ) : (
          <div className="diagnostics-panel__stack">
            {endpointSummaries.map((endpoint) => {
              const resultItem = endpointResults[endpoint.name];
              const runtime = deriveEndpointRuntimeStatus(endpoint, resultItem);
              const errorSummary = resultItem?.error ? truncateText(resultItem.error, 72) : '';

              return (
                <article key={endpoint.name} className="diagnostics-panel__list-item">
                  <div className="diagnostics-panel__list-main">
                    <div className="diagnostics-panel__list-title-row">
                      <strong>{endpoint.label}</strong>
                      {endpoint.active ? <span className="diagnostics-panel__mini-pill">Active</span> : null}
                      <span className="diagnostics-panel__mini-muted">{endpoint.kind === 'chat' ? '聊天端点' : ROLE_LABELS[endpoint.role] || endpoint.role}</span>
                    </div>
                    <div className="diagnostics-panel__list-subtitle">
                      <span>{endpoint.model || '未配置模型'}</span>
                      <span>·</span>
                      <span className="is-mono">{truncateText(endpoint.baseUrl || '未配置 Base URL', 52)}</span>
                    </div>
                    <div className="diagnostics-panel__list-meta">
                      <span>{runtime.hint}</span>
                      {!endpoint.keyPresent ? (
                        <>
                          <span>·</span>
                          <span>API Key 未提供</span>
                        </>
                      ) : null}
                      {resultItem?.error_code ? (
                        <>
                          <span>·</span>
                          <span>错误类别：{resultItem.error_code}</span>
                        </>
                      ) : null}
                    </div>
                    {resultItem?.last_checked_at ? (
                      <div className="diagnostics-panel__list-meta">最近检测：{formatIsoTime(resultItem.last_checked_at)}</div>
                    ) : null}
                    {errorSummary ? (
                      <div className="diagnostics-panel__error-row">
                        <span>{errorSummary}</span>
                        <UiButton
                          type="button"
                          variant="secondary"
                          className="diagnostics-panel__action-btn diagnostics-panel__action-btn--small"
                          onClick={async () => {
                            const ok = await copyText(resultItem?.error || '');
                            pushRuntimeNotice(ok ? '已复制错误详情' : '复制失败，请检查系统剪贴板权限');
                          }}
                        >
                          复制详情
                        </UiButton>
                      </div>
                    ) : null}
                  </div>
                  <div className="diagnostics-panel__list-actions">
                    <UiStatusPill tone={runtimeStatusTone(runtime.status)} className={`diagnostics-panel__status-pill ${runtimeStatusClass(runtime.status)}`}>{runtime.label}</UiStatusPill>
                    <UiButton
                      type="button"
                      variant="secondary"
                      className="diagnostics-panel__action-btn diagnostics-panel__action-btn--small"
                      onClick={() => {
                        void runEndpointHealthCheck(endpoint.name);
                      }}
                      disabled={endpointChecking !== null}
                    >
                      {endpointChecking === endpoint.name ? '检测中...' : 'Check'}
                    </UiButton>
                  </div>
                </article>
              );
            })}
          </div>
        )}
      </section>

      <section className="diagnostics-panel__card">
        <div className="diagnostics-panel__runtime-head">
          <div>
            <h5 className="diagnostics-panel__card-title">IM 通道</h5>
            <p className="diagnostics-panel__card-desc">优先展示配置状态；点击刷新时再读取当前运行中的在线/离线状态。</p>
            <div className="diagnostics-panel__list-meta">
              <span>总数：{imStats.total}</span>
              <span>·</span>
              <span>在线：{imStats.online}</span>
              <span>·</span>
              <span>离线：{imStats.offline}</span>
              <span>·</span>
              <span>配置缺失：{imStats.misconfigured}</span>
              <span>·</span>
              <span>未检测：{imStats.unknown}</span>
            </div>
          </div>
          <UiButton
            type="button"
            variant="secondary"
            className="diagnostics-panel__action-btn"
            onClick={() => {
              void refreshIMRuntimeStatus();
            }}
            disabled={imChecking}
          >
            {imChecking ? '刷新中...' : '检查通道状态'}
          </UiButton>
        </div>

        {imBots.length === 0 ? (
          <div className="diagnostics-panel__empty">当前没有已登记的 IM Bot。</div>
        ) : (
          <div className="diagnostics-panel__stack">
            {imBots.map((bot) => {
              const runtime = imRuntime[bot.channelName];
              const derivedStatus: 'healthy' | 'unhealthy' | 'unknown' =
                !bot.enabled
                  ? 'unknown'
                  : bot.missingFields.length > 0
                    ? 'unhealthy'
                    : runtime
                      ? runtime.status === 'online'
                        ? 'healthy'
                        : 'unhealthy'
                      : 'unknown';
              const statusLabel =
                !bot.enabled
                  ? '未启用'
                  : bot.missingFields.length > 0
                    ? `配置缺失：${bot.missingFields.join(', ')}`
                    : runtime
                      ? runtime.status === 'online'
                        ? '在线'
                        : '离线'
                      : '已配置未测';

              return (
                <article key={bot.channelName} className="diagnostics-panel__list-item">
                  <div className="diagnostics-panel__list-main">
                    <div className="diagnostics-panel__list-title-row">
                      <strong>{bot.name}</strong>
                      <span className="diagnostics-panel__mini-muted">{bot.platform}</span>
                    </div>
                    <div className="diagnostics-panel__list-subtitle">
                      <span className="is-mono">{bot.channelName}</span>
                    </div>
                    <div className="diagnostics-panel__list-meta">
                      {!bot.enabled
                        ? '该 Bot 当前未启用'
                        : bot.missingFields.length > 0
                          ? `请补全配置项：${bot.missingFields.join(', ')}`
                          : runtime
                            ? runtime.status === 'online'
                              ? '运行态正常，可继续使用'
                              : '通道已配置，但当前运行态离线'
                            : '已配置，点击“检查通道状态”读取实时运行态'}
                    </div>
                    {runtime ? (
                      <div className="diagnostics-panel__list-meta">
                        <span>会话数：{runtime.session_count ?? 0}</span>
                        <span>·</span>
                        <span>最近活动：{runtime.last_active ? formatIsoTime(runtime.last_active) : '无'}</span>
                        {runtime.stream_state ? (
                          <>
                            <span>·</span>
                            <span>Stream：{runtime.stream_state}</span>
                          </>
                        ) : null}
                      </div>
                    ) : null}
                    {runtime?.last_error ? (
                      <div className="diagnostics-panel__error-row">
                        <span>{truncateText(runtime.last_error, 72)}</span>
                        <UiButton
                          type="button"
                          variant="secondary"
                          className="diagnostics-panel__action-btn diagnostics-panel__action-btn--small"
                          onClick={async () => {
                            const ok = await copyText(runtime.last_error || '');
                            pushRuntimeNotice(ok ? '已复制通道错误详情' : '复制失败，请检查系统剪贴板权限');
                          }}
                        >
                          复制详情
                        </UiButton>
                      </div>
                    ) : null}
                  </div>
                  <div className="diagnostics-panel__list-actions">
                    <UiStatusPill tone={runtimeStatusTone(derivedStatus)} className={`diagnostics-panel__status-pill ${runtimeStatusClass(derivedStatus)}`}>{statusLabel}</UiStatusPill>
                  </div>
                </article>
              );
            })}
          </div>
        )}
      </section>

      {result ? (
        <>
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
                  <span>进程 PID</span>
                  <strong>{result.system?.pid || '未知'}</strong>
                </div>
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

      <UiButton type="button" variant="primary" className="diagnostics-panel__action-btn diagnostics-panel__action-btn--primary" onClick={wakeModel}>
        手动唤醒模型推理
      </UiButton>

      {pokeStatus ? <div className="diagnostics-panel__notice diagnostics-panel__notice--status">{pokeStatus}</div> : null}
    </div>
  );
}

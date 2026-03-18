import { useEffect, useMemo, useState } from 'react';
import { emitShellUpdate, type OpenGuiclawApp, getHostApp } from '../bridge/openGuiclaw';
import { useWorkspaceShellBridge } from '../hooks/useWorkspaceShellBridge';

type WorkspaceRecord = {
  id: string;
  name: string;
  workspace_path?: string | null;
  archived?: boolean;
};

type ArchivedThreadRecord = {
  session_id: string;
  title?: string | null;
  updated_at?: string | null;
  archived?: boolean;
  _wsId: string;
  _wsName: string;
};

type LoadState = {
  loading: boolean;
  errorText: string;
};

function formatSessionTime(value?: string | null) {
  if (!value) return '未知时间';
  const date = new Date(String(value).replace(' ', 'T'));
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString();
}

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
    // Ignore parse failure and use fallback below.
  }
  return fallback;
}

export function ArchivedPanel() {
  const { hostApp, snapshot } = useWorkspaceShellBridge();
  const [workspaces, setWorkspaces] = useState<WorkspaceRecord[]>([]);
  const [archivedWorkspaces, setArchivedWorkspaces] = useState<WorkspaceRecord[]>([]);
  const [archivedThreads, setArchivedThreads] = useState<ArchivedThreadRecord[]>([]);
  const [selectedWorkspaceId, setSelectedWorkspaceId] = useState('');
  const [workspaceState, setWorkspaceState] = useState<LoadState>({ loading: true, errorText: '' });
  const [threadState, setThreadState] = useState<LoadState>({ loading: true, errorText: '' });
  const [statusText, setStatusText] = useState('');
  const [busyKey, setBusyKey] = useState<string | null>(null);

  const workspaceOptions = useMemo(
    () =>
      workspaces
        .slice()
        .sort((left, right) => left.name.localeCompare(right.name, 'zh-CN')),
    [workspaces]
  );

  useEffect(() => {
    if (!snapshot.showSettings || snapshot.settingsTab !== 'archived') return;
    void loadArchivedData(hostApp ?? getHostApp());
  }, [snapshot.showSettings, snapshot.settingsTab]);

  async function loadArchivedData(app: OpenGuiclawApp | null) {
    await Promise.all([loadWorkspaceLists(app), loadArchivedThreads(app, selectedWorkspaceId)]);
  }

  async function loadWorkspaceLists(app: OpenGuiclawApp | null) {
    setWorkspaceState({ loading: true, errorText: '' });
    try {
      const [activeResponse, archivedResponse] = await Promise.all([
        fetch('/api/workspaces'),
        fetch('/api/workspaces/archived')
      ]);

      if (!activeResponse.ok) {
        throw new Error(await readErrorMessage(activeResponse, '加载工作区列表失败'));
      }
      if (!archivedResponse.ok) {
        throw new Error(await readErrorMessage(archivedResponse, '加载归档工作区失败'));
      }

      const activePayload = await parseResponse(activeResponse);
      const archivedPayload = await parseResponse(archivedResponse);
      const activeWorkspaces = Array.isArray(activePayload)
        ? activePayload
        : Array.isArray(activePayload?.workspaces)
          ? activePayload.workspaces
          : [];
      const archivedOnly = Array.isArray(archivedPayload)
        ? archivedPayload
        : Array.isArray(archivedPayload?.workspaces)
          ? archivedPayload.workspaces
          : [];

      const combined = [...activeWorkspaces, ...archivedOnly];
      setWorkspaces(combined);
      setArchivedWorkspaces(archivedOnly);

      if (selectedWorkspaceId && !combined.some((workspace) => workspace.id === selectedWorkspaceId)) {
        setSelectedWorkspaceId('');
      }

      setWorkspaceState({ loading: false, errorText: '' });

      if (app) {
        await app.loadWorkspaces?.();
        await app.loadHome?.();
        emitShellUpdate();
      }
    } catch (error) {
      setWorkspaceState({
        loading: false,
        errorText: error instanceof Error ? error.message : '加载工作区列表失败'
      });
      setWorkspaces([]);
      setArchivedWorkspaces([]);
    }
  }

  async function loadArchivedThreads(app: OpenGuiclawApp | null, workspaceFilter: string) {
    setThreadState({ loading: true, errorText: '' });
    try {
      const allWorkspaces =
        workspaces.length > 0
          ? workspaces
          : await (async () => {
              const [activeResponse, archivedResponse] = await Promise.all([
                fetch('/api/workspaces'),
                fetch('/api/workspaces/archived')
              ]);
              const activePayload = activeResponse.ok ? await parseResponse(activeResponse) : [];
              const archivedPayload = archivedResponse.ok ? await parseResponse(archivedResponse) : [];
              const activeItems = Array.isArray(activePayload)
                ? activePayload
                : Array.isArray(activePayload?.workspaces)
                  ? activePayload.workspaces
                  : [];
              const archivedItems = Array.isArray(archivedPayload)
                ? archivedPayload
                : Array.isArray(archivedPayload?.workspaces)
                  ? archivedPayload.workspaces
                  : [];
              return [...activeItems, ...archivedItems];
            })();

      const targetWorkspaces = workspaceFilter
        ? allWorkspaces.filter((workspace) => workspace.id === workspaceFilter)
        : allWorkspaces;

      const results = await Promise.all(
        targetWorkspaces.map(async (workspace) => {
          const response = await fetch(`/api/workspaces/${workspace.id}/sessions?include_archived=true`);
          if (!response.ok) return [];
          const payload = await parseResponse(response);
          const sessions = Array.isArray(payload)
            ? payload
            : Array.isArray(payload?.sessions)
              ? payload.sessions
              : [];

          return sessions
            .filter((session: { archived?: boolean }) => session.archived)
            .map((session: ArchivedThreadRecord) => ({
              ...session,
              _wsId: workspace.id,
              _wsName: workspace.name
            }));
        })
      );

      const nextThreads = results
        .flat()
        .sort((left, right) => String(right.updated_at || '').localeCompare(String(left.updated_at || '')));

      setArchivedThreads(nextThreads);
      setThreadState({ loading: false, errorText: '' });

      if (app) {
        emitShellUpdate();
      }
    } catch (error) {
      setThreadState({
        loading: false,
        errorText: error instanceof Error ? error.message : '加载归档对话失败'
      });
      setArchivedThreads([]);
    }
  }

  function pushStatus(message: string) {
    setStatusText(message);
    window.clearTimeout((pushStatus as typeof pushStatus & { timer?: number }).timer);
    (pushStatus as typeof pushStatus & { timer?: number }).timer = window.setTimeout(() => {
      setStatusText('');
    }, 3200);
  }

  async function refreshAll() {
    await loadArchivedData(hostApp ?? getHostApp());
  }

  async function handleWorkspaceFilterChange(nextWorkspaceId: string) {
    setSelectedWorkspaceId(nextWorkspaceId);
    await loadArchivedThreads(hostApp ?? getHostApp(), nextWorkspaceId);
  }

  async function restoreWorkspace(workspaceId: string) {
    setBusyKey(`restore-workspace:${workspaceId}`);
    try {
      const response = await fetch(`/api/workspaces/${workspaceId}/unarchive`, { method: 'POST' });
      if (!response.ok) {
        throw new Error(await readErrorMessage(response, '恢复工作区失败'));
      }
      pushStatus('工作区已恢复');
      await refreshAll();
    } catch (error) {
      pushStatus(error instanceof Error ? error.message : '恢复工作区失败');
    } finally {
      setBusyKey(null);
    }
  }

  async function restoreThread(workspaceId: string, sessionId: string) {
    setBusyKey(`restore-thread:${workspaceId}:${sessionId}`);
    try {
      const response = await fetch(`/api/workspaces/${workspaceId}/sessions/${sessionId}/unarchive`, {
        method: 'POST'
      });
      if (!response.ok) {
        throw new Error(await readErrorMessage(response, '恢复对话失败'));
      }
      pushStatus('对话已恢复');
      await refreshAll();
    } catch (error) {
      pushStatus(error instanceof Error ? error.message : '恢复对话失败');
    } finally {
      setBusyKey(null);
    }
  }

  async function deleteThread(workspaceId: string, sessionId: string) {
    const confirmed = window.confirm('确定永久删除该对话？此操作无法撤销。');
    if (!confirmed) return;

    setBusyKey(`delete-thread:${workspaceId}:${sessionId}`);
    try {
      const response = await fetch(`/api/workspaces/${workspaceId}/sessions/${sessionId}`, {
        method: 'DELETE'
      });
      if (!response.ok) {
        throw new Error(await readErrorMessage(response, '永久删除对话失败'));
      }
      pushStatus('对话已永久删除');
      await refreshAll();
    } catch (error) {
      pushStatus(error instanceof Error ? error.message : '永久删除对话失败');
    } finally {
      setBusyKey(null);
    }
  }

  return (
    <div className="archived-panel">
      <section className="archived-panel__section">
        <header className="archived-panel__section-header">
          <div>
            <div className="archived-panel__eyebrow">工作区归档</div>
            <h4 className="archived-panel__title">归档工作区</h4>
            <p className="archived-panel__meta">{archivedWorkspaces.length} 个已归档工作区</p>
          </div>
          <button type="button" className="archived-panel__ghost-btn" onClick={refreshAll}>
            刷新
          </button>
        </header>

        {workspaceState.errorText ? (
          <div className="archived-panel__notice archived-panel__notice--error">{workspaceState.errorText}</div>
        ) : null}

        {workspaceState.loading ? <div className="archived-panel__empty">正在加载归档工作区...</div> : null}

        {!workspaceState.loading && !workspaceState.errorText && archivedWorkspaces.length === 0 ? (
          <div className="archived-panel__empty">暂无归档工作区</div>
        ) : null}

        {!workspaceState.loading && archivedWorkspaces.length > 0 ? (
          <div className="archived-panel__stack">
            {archivedWorkspaces.map((workspace) => {
              const actionKey = `restore-workspace:${workspace.id}`;
              const busy = busyKey === actionKey;
              return (
                <article key={workspace.id} className="archived-panel__card">
                  <div className="archived-panel__card-main">
                    <h5 className="archived-panel__card-title">{workspace.name}</h5>
                    <div className="archived-panel__card-subtitle">{workspace.workspace_path || '未记录目录'}</div>
                  </div>
                  <button
                    type="button"
                    className="archived-panel__accent-btn"
                    onClick={() => restoreWorkspace(workspace.id)}
                    disabled={busy}
                  >
                    {busy ? '恢复中...' : '恢复'}
                  </button>
                </article>
              );
            })}
          </div>
        ) : null}
      </section>

      <section className="archived-panel__section">
        <header className="archived-panel__section-header">
          <div>
            <div className="archived-panel__eyebrow">对话归档</div>
            <h4 className="archived-panel__title">归档对话</h4>
            <p className="archived-panel__meta">{archivedThreads.length} 条已归档对话</p>
          </div>
          <label className="archived-panel__filter">
            <span className="archived-panel__filter-label">工作区</span>
            <select
              className="archived-panel__select"
              value={selectedWorkspaceId}
              onChange={(event) => {
                void handleWorkspaceFilterChange(event.target.value);
              }}
            >
              <option value="">全部工作区</option>
              {workspaceOptions.map((workspace) => (
                <option key={workspace.id} value={workspace.id}>
                  {workspace.name}
                </option>
              ))}
            </select>
          </label>
        </header>

        {threadState.errorText ? (
          <div className="archived-panel__notice archived-panel__notice--error">{threadState.errorText}</div>
        ) : null}

        {threadState.loading ? <div className="archived-panel__empty">正在加载归档对话...</div> : null}

        {!threadState.loading && !threadState.errorText && archivedThreads.length === 0 ? (
          <div className="archived-panel__empty">暂无归档对话</div>
        ) : null}

        {!threadState.loading && archivedThreads.length > 0 ? (
          <div className="archived-panel__stack">
            {archivedThreads.map((thread) => {
              const restoreKey = `restore-thread:${thread._wsId}:${thread.session_id}`;
              const deleteKey = `delete-thread:${thread._wsId}:${thread.session_id}`;
              return (
                <article key={`${thread._wsId}:${thread.session_id}`} className="archived-panel__card archived-panel__card--thread">
                  <div className="archived-panel__card-main">
                    <h5 className="archived-panel__card-title">{thread.title || thread.session_id}</h5>
                    <div className="archived-panel__thread-meta">
                      <span>{thread._wsName}</span>
                      <span className="archived-panel__thread-dot">•</span>
                      <span>{formatSessionTime(thread.updated_at)}</span>
                    </div>
                  </div>
                  <div className="archived-panel__actions">
                    <button
                      type="button"
                      className="archived-panel__accent-btn"
                      onClick={() => restoreThread(thread._wsId, thread.session_id)}
                      disabled={busyKey === restoreKey}
                    >
                      {busyKey === restoreKey ? '恢复中...' : '恢复'}
                    </button>
                    <button
                      type="button"
                      className="archived-panel__danger-btn"
                      onClick={() => deleteThread(thread._wsId, thread.session_id)}
                      disabled={busyKey === deleteKey}
                    >
                      {busyKey === deleteKey ? '删除中...' : '永久删除'}
                    </button>
                  </div>
                </article>
              );
            })}
          </div>
        ) : null}
      </section>

      {statusText ? <div className="archived-panel__notice archived-panel__notice--status">{statusText}</div> : null}
    </div>
  );
}

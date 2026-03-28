import { useMemo, useRef, useState } from 'react';
import { dispatchShellAction, type OpenGuiclawApp } from '../bridge/openGuiclaw';
import { useWorkspaceShellBridge } from '../hooks/useWorkspaceShellBridge';

type ToolbarSnapshot = {
  kicker: string;
  title: string;
  threadId: string | null;
  wsId: string | null;
  wsName: string;
  isPinned: boolean;
  isReceiving: boolean;
  currentView: string;
  vrmSystemEnabled: boolean;
  showVrm: boolean;
};

const EMPTY: ToolbarSnapshot = {
  kicker: '',
  title: '',
  threadId: null,
  wsId: null,
  wsName: '',
  isPinned: false,
  isReceiving: false,
  currentView: 'home',
  vrmSystemEnabled: false,
  showVrm: false
};

function buildSnapshot(app: OpenGuiclawApp): ToolbarSnapshot {
  const view = app.currentView ?? 'home';
  const wsName = app.activeWorkspace?.name ?? '';
  const thread = typeof app.getCurrentThread === 'function' ? app.getCurrentThread() : null;
  const threadId = app.currentThreadId ?? null;

  let title =
    typeof app.getTopbarTitle === 'function'
      ? app.getTopbarTitle()
      : wsName || '选择工作区';

  let kicker =
    typeof app.getTopbarKicker === 'function'
      ? app.getTopbarKicker()
      : view === 'chat'
        ? '当前线程'
        : view === 'skills'
          ? '技能'
          : view === 'scheduler'
            ? '自动化'
            : '工作区';

  if (!title) {
    if (view === 'chat') {
      title = thread?.title || (threadId ? `${threadId.slice(0, 16)}...` : wsName ? `${wsName} / 新线程` : '新线程');
    } else if (view === 'skills') {
      title = '技能';
    } else if (view === 'scheduler') {
      title = '自动化';
    } else if (view === 'im') {
      title = 'IM 通道';
    } else {
      title = wsName || '选择工作区';
    }
  }

  if (!kicker) {
    kicker = view === 'chat' ? '当前线程' : view === 'skills' ? '技能' : view === 'scheduler' ? '自动化' : view === 'im' ? 'IM 通道' : '工作区';
  }

  return {
    kicker,
    title,
    threadId,
    wsId: app.activeWorkspaceId ?? null,
    wsName,
    isPinned: !!thread?.pinned,
    isReceiving: !!app.isReceiving,
    currentView: view,
    vrmSystemEnabled: !!app.vrmSystemEnabled,
    showVrm: !!app.showVrm
  };
}

export function ChatThreadToolbar() {
  const [busy, setBusy] = useState(false);
  const appRef = useRef<OpenGuiclawApp | null>(null);
  const { hostApp, snapshot } = useWorkspaceShellBridge();
  const state = useMemo(() => {
    if (!hostApp) return EMPTY;
    appRef.current = hostApp;
    return buildSnapshot(hostApp);
  }, [hostApp, snapshot]);

  async function handleArchive() {
    const app = appRef.current;
    if (!app || !state.wsId || !state.threadId || busy) return;
    if (!window.confirm('归档此线程？之后可以从"已归档"中恢复。')) return;

    setBusy(true);
    try {
      await app.archiveThread?.(state.wsId, state.threadId);
    } finally {
      setBusy(false);
    }
  }

  async function handleTogglePin() {
    const app = appRef.current;
    if (!app || !state.wsId || !state.threadId || busy) return;

    setBusy(true);
    try {
      await app.toggleThreadPin?.(state.wsId, state.threadId, state.isPinned);
    } finally {
      setBusy(false);
    }
  }

  function handleNewThread() {
    const app = appRef.current;
    if (!app || state.isReceiving) return;
    app.newSession?.();
  }

  function handleOpenIntegrations() {
    dispatchShellAction({ type: 'openSettings', tab: 'integrations' });
  }

  function handleToggleVrm() {
    const app = appRef.current;
    if (!app || !state.vrmSystemEnabled) return;
    app.toggleVrm?.();
  }

  const inChat = state.currentView === 'chat';
  const hasThread = !!state.threadId;

  return (
    <div className="react-topbar-toolbar">
      <div className="react-topbar-breadcrumb">
        <span className="topbar-kicker">{state.kicker}</span>
        <div className="workspace-title">{state.title}</div>
      </div>

      {inChat && hasThread ? (
        <div className="react-topbar-thread-actions">
          {state.vrmSystemEnabled ? (
            <button
              type="button"
              className={`react-topbar-icon-btn${state.showVrm ? ' is-active' : ''}`}
              title={state.showVrm ? '隐藏 VRM 形象' : '显示 VRM 形象'}
              onClick={handleToggleVrm}
              aria-label={state.showVrm ? '隐藏 VRM 形象' : '显示 VRM 形象'}
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" aria-hidden="true">
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth="2"
                  d="M15 10l4.553-2.069A1 1 0 0121 8.87v6.26a1 1 0 01-1.447.894L15 14M3 8a2 2 0 012-2h10a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2V8z"
                />
              </svg>
            </button>
          ) : null}

          <button
            type="button"
            className={`react-topbar-icon-btn${state.isPinned ? ' is-active' : ''}`}
            title={state.isPinned ? '取消置顶' : '置顶线程'}
            disabled={busy}
            onClick={handleTogglePin}
            aria-label={state.isPinned ? '取消置顶' : '置顶线程'}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" aria-hidden="true">
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth="2.1"
                d="M9 3h6l-1.2 5.2L18 12v1H13v7l-2-1.8V13H6v-1l4.2-3.8L9 3z"
              />
            </svg>
          </button>

          <button
            type="button"
            className="react-topbar-icon-btn is-danger"
            title="归档线程"
            disabled={busy}
            onClick={handleArchive}
            aria-label="归档线程"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" aria-hidden="true">
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth="2"
                d="M5 8h14M5 8a2 2 0 110-4h14a2 2 0 110 4M5 8v10a2 2 0 002 2h10a2 2 0 002-2V8"
              />
            </svg>
          </button>
        </div>
      ) : null}

      <div className="react-topbar-right">
        {state.currentView !== 'im' && state.wsName ? <div className="topbar-chip">{state.wsName}</div> : null}

        {state.currentView === 'im' ? (
          <button type="button" className="btn-secondary" onClick={handleOpenIntegrations}>
            集成配置
          </button>
        ) : (
          <button type="button" className="btn-primary" disabled={state.isReceiving} onClick={handleNewThread}>
            新线程
          </button>
        )}

        <div className="topbar-status">
          <span className={`topbar-status-dot${state.isReceiving ? ' busy' : ''}`} />
          <span>{state.isReceiving ? '处理中' : '在线'}</span>
        </div>
      </div>
    </div>
  );
}

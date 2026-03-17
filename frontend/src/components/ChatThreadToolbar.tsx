import { useMemo, useRef, useState } from 'react';
import { type OpenGuiclawApp } from '../bridge/openGuiclaw';
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
};

const EMPTY: ToolbarSnapshot = {
  kicker: '',
  title: '',
  threadId: null,
  wsId: null,
  wsName: '',
  isPinned: false,
  isReceiving: false,
  currentView: 'home'
};

function buildSnapshot(app: OpenGuiclawApp): ToolbarSnapshot {
  const view = app.currentView ?? 'home';
  const wsName = app.activeWorkspace?.name ?? '';
  const thread = typeof app.getCurrentThread === 'function' ? app.getCurrentThread() : null;
  const threadId = app.currentThreadId ?? null;

  let title =
    typeof app.getTopbarTitle === 'function'
      ? app.getTopbarTitle()
      : wsName || 'Select Workspace';

  let kicker =
    typeof app.getTopbarKicker === 'function'
      ? app.getTopbarKicker()
      : view === 'chat'
        ? 'Current Thread'
        : view === 'skills'
          ? 'Skills'
          : view === 'scheduler'
            ? 'Automation'
            : 'Workspace';

  if (!title) {
    if (view === 'chat') {
      title = thread?.title || (threadId ? `${threadId.slice(0, 16)}...` : wsName ? `${wsName} / New Thread` : 'New Thread');
    } else if (view === 'skills') {
      title = 'Skills';
    } else if (view === 'scheduler') {
      title = 'Automation';
    } else {
      title = wsName || 'Select Workspace';
    }
  }

  if (!kicker) {
    kicker = view === 'chat' ? 'Current Thread' : view === 'skills' ? 'Skills' : view === 'scheduler' ? 'Automation' : 'Workspace';
  }

  return {
    kicker,
    title,
    threadId,
    wsId: app.activeWorkspaceId ?? null,
    wsName,
    isPinned: !!thread?.pinned,
    isReceiving: !!app.isReceiving,
    currentView: view
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
    if (!window.confirm('Archive this thread? You can restore it later from Archived.')) return;

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
          <button
            type="button"
            className={`react-topbar-icon-btn${state.isPinned ? ' is-active' : ''}`}
            title={state.isPinned ? 'Unpin thread' : 'Pin thread'}
            disabled={busy}
            onClick={handleTogglePin}
            aria-label={state.isPinned ? 'Unpin thread' : 'Pin thread'}
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
            title="Archive thread"
            disabled={busy}
            onClick={handleArchive}
            aria-label="Archive thread"
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
        {state.wsName ? <div className="topbar-chip">{state.wsName}</div> : null}

        <button type="button" className="btn-primary" disabled={state.isReceiving} onClick={handleNewThread}>
          New Thread
        </button>

        <div className="topbar-status">
          <span className={`topbar-status-dot${state.isReceiving ? ' busy' : ''}`} />
          <span>{state.isReceiving ? 'Working' : 'Online'}</span>
        </div>
      </div>
    </div>
  );
}

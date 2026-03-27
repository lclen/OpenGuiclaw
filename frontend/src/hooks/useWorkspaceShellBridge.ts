import { useEffect, useState } from 'react';
import {
  getHostApp,
  type OpenGuiclawApp,
  type WorkspaceShellSnapshot,
  waitForHostApp
} from '../bridge/openGuiclaw';

const EMPTY_SNAPSHOT: WorkspaceShellSnapshot = {
  workspaces: [],
  homeData: null,
  activeWorkspaceId: null,
  activeWorkspace: null,
  sidebarCollapsed: false,
  workspaceThreads: [],
  workspaceThreadMap: {},
  expandedWorkspaceIds: {},
  workspaceLoading: false,
  currentView: 'home',
  currentThreadId: null,
  showNewWorkspaceModal: false,
  showWorkspaceSwitcher: false,
  showSettings: false,
  settingsTab: 'models',
  previousViewBeforeSettings: 'home',
  newWorkspaceName: '',
  newWorkspacePath: '',
  newWorkspaceError: '',
  vrmSystemEnabled: false,
  showVrm: false,
  isReceiving: false
};

type ShellDetail = Partial<WorkspaceShellSnapshot>;
type ChatDetail = {
  currentThreadId?: string | null;
};

function cloneThreads(threads: OpenGuiclawApp['workspaceThreads']): WorkspaceShellSnapshot['workspaceThreads'] {
  return Array.isArray(threads) ? threads.map((thread) => ({ ...thread })) : [];
}

function cloneWorkspaces(workspaces: OpenGuiclawApp['workspaces']): WorkspaceShellSnapshot['workspaces'] {
  return Array.isArray(workspaces) ? workspaces.map((workspace) => ({ ...workspace })) : [];
}

function cloneHomeData(homeData: OpenGuiclawApp['homeData']): WorkspaceShellSnapshot['homeData'] {
  if (!homeData) return null;
  return {
    ...homeData,
    workspaces: Array.isArray(homeData.workspaces)
      ? homeData.workspaces.map((workspace) => ({
          ...workspace,
          recent_sessions: Array.isArray(workspace.recent_sessions)
            ? workspace.recent_sessions.map((thread) => ({ ...thread }))
            : []
        }))
      : []
  };
}

function cloneThreadMap(workspaceThreadMap: OpenGuiclawApp['workspaceThreadMap']): WorkspaceShellSnapshot['workspaceThreadMap'] {
  return Object.fromEntries(
    Object.entries(workspaceThreadMap || {}).map(([workspaceId, threads]) => [
      workspaceId,
      Array.isArray(threads) ? threads.map((thread) => ({ ...thread })) : []
    ])
  );
}

function resolveActiveWorkspace(
  workspaces: WorkspaceShellSnapshot['workspaces'],
  activeWorkspaceId: string | null,
  hostApp?: OpenGuiclawApp | null,
  previous?: WorkspaceShellSnapshot | null
): WorkspaceShellSnapshot['activeWorkspace'] {
  if (activeWorkspaceId) {
    const matched = workspaces.find((workspace) => workspace.id === activeWorkspaceId);
    if (matched) {
      return { id: matched.id, name: matched.name, workspace_path: matched.workspace_path ?? null };
    }
  }

  if (hostApp?.activeWorkspace) {
    return { ...hostApp.activeWorkspace };
  }

  return previous?.activeWorkspace ?? null;
}

function snapshotShell(app: OpenGuiclawApp): WorkspaceShellSnapshot {
  const workspaces = cloneWorkspaces(app.workspaces);
  const activeWorkspaceId = app.activeWorkspaceId ?? null;
  return {
    workspaces,
    homeData: cloneHomeData(app.homeData),
    activeWorkspaceId,
    activeWorkspace: resolveActiveWorkspace(workspaces, activeWorkspaceId, app),
    sidebarCollapsed: !!app.sidebarCollapsed,
    workspaceThreads: cloneThreads(app.workspaceThreads),
    workspaceThreadMap: cloneThreadMap(app.workspaceThreadMap),
    expandedWorkspaceIds: { ...(app.expandedWorkspaceIds || {}) },
    workspaceLoading: !!app.workspaceLoading,
    currentView: app.currentView || 'home',
    currentThreadId: app.currentThreadId ?? null,
    showNewWorkspaceModal: !!app.showNewWorkspaceModal,
    showWorkspaceSwitcher: !!app.showWorkspaceSwitcher,
    showSettings: !!app.showSettings,
    settingsTab: (app as OpenGuiclawApp & { settingsTab?: string }).settingsTab || 'models',
    previousViewBeforeSettings: (app as OpenGuiclawApp & { previousViewBeforeSettings?: string }).previousViewBeforeSettings || 'home',
    newWorkspaceName: app.newWorkspaceName || '',
    newWorkspacePath: app.newWorkspacePath || '',
    newWorkspaceError: app.newWorkspaceError || '',
    vrmSystemEnabled: !!app.vrmSystemEnabled,
    showVrm: !!app.showVrm,
    isReceiving: !!app.isReceiving
  };
}

function mergeShellDetail(
  previous: WorkspaceShellSnapshot,
  detail: ShellDetail,
  hostApp?: OpenGuiclawApp | null
): WorkspaceShellSnapshot {
  const workspaces =
    'workspaces' in detail ? cloneWorkspaces(detail.workspaces || []) : previous.workspaces;
  const activeWorkspaceId =
    'activeWorkspaceId' in detail ? detail.activeWorkspaceId ?? null : previous.activeWorkspaceId;

  return {
    workspaces,
    homeData: 'homeData' in detail ? cloneHomeData(detail.homeData || null) : previous.homeData,
    activeWorkspaceId,
    activeWorkspace: resolveActiveWorkspace(workspaces, activeWorkspaceId, hostApp, previous),
    sidebarCollapsed: 'sidebarCollapsed' in detail ? !!detail.sidebarCollapsed : previous.sidebarCollapsed,
    workspaceThreads:
      'workspaceThreads' in detail ? cloneThreads(detail.workspaceThreads || []) : previous.workspaceThreads,
    workspaceThreadMap:
      'workspaceThreadMap' in detail ? cloneThreadMap(detail.workspaceThreadMap || {}) : previous.workspaceThreadMap,
    expandedWorkspaceIds:
      'expandedWorkspaceIds' in detail ? { ...(detail.expandedWorkspaceIds || {}) } : previous.expandedWorkspaceIds,
    workspaceLoading: 'workspaceLoading' in detail ? !!detail.workspaceLoading : previous.workspaceLoading,
    currentView: 'currentView' in detail ? detail.currentView || 'home' : previous.currentView,
    currentThreadId: 'currentThreadId' in detail ? detail.currentThreadId ?? null : previous.currentThreadId,
    showNewWorkspaceModal:
      'showNewWorkspaceModal' in detail ? !!detail.showNewWorkspaceModal : previous.showNewWorkspaceModal,
    showWorkspaceSwitcher:
      'showWorkspaceSwitcher' in detail ? !!detail.showWorkspaceSwitcher : previous.showWorkspaceSwitcher,
    showSettings: 'showSettings' in detail ? !!detail.showSettings : previous.showSettings,
    settingsTab: 'settingsTab' in detail ? detail.settingsTab || 'models' : previous.settingsTab,
    previousViewBeforeSettings:
      'previousViewBeforeSettings' in detail
        ? detail.previousViewBeforeSettings || 'home'
        : previous.previousViewBeforeSettings,
    newWorkspaceName: 'newWorkspaceName' in detail ? detail.newWorkspaceName || '' : previous.newWorkspaceName,
    newWorkspacePath: 'newWorkspacePath' in detail ? detail.newWorkspacePath || '' : previous.newWorkspacePath,
    newWorkspaceError: 'newWorkspaceError' in detail ? detail.newWorkspaceError || '' : previous.newWorkspaceError,
    vrmSystemEnabled: 'vrmSystemEnabled' in detail ? !!detail.vrmSystemEnabled : previous.vrmSystemEnabled,
    showVrm: 'showVrm' in detail ? !!detail.showVrm : previous.showVrm,
    isReceiving: 'isReceiving' in detail ? !!detail.isReceiving : previous.isReceiving
  };
}

export function useWorkspaceShellBridge() {
  const [hostApp, setHostApp] = useState<OpenGuiclawApp | null>(getHostApp());
  const [snapshot, setSnapshot] = useState<WorkspaceShellSnapshot>(() =>
    hostApp ? snapshotShell(hostApp) : EMPTY_SNAPSHOT
  );
  const [errorText, setErrorText] = useState('');

  useEffect(() => {
    let mounted = true;

    const syncFromHost = (app: OpenGuiclawApp) => {
      if (!mounted) return;
      setHostApp((previous) => (previous === app ? previous : app));
      setSnapshot(snapshotShell(app));
    };

    waitForHostApp()
      .then((app) => syncFromHost(app))
      .catch((error: Error) => {
        if (!mounted) return;
        setErrorText(error.message);
      });

    const handleShellUpdated = (event: Event) => {
      const app = getHostApp();
      if (!app) return;
      setHostApp((previous) => (previous === app ? previous : app));

      const detail = (event as CustomEvent<ShellDetail>).detail;
      if (detail && typeof detail === 'object' && Object.keys(detail).length > 0) {
        setSnapshot((previous) => mergeShellDetail(previous, detail, app));
        return;
      }

      syncFromHost(app);
    };

    const handleChatUpdated = (event: Event) => {
      const detail = (event as CustomEvent<ChatDetail>).detail;
      if (detail && 'currentThreadId' in detail) {
        setSnapshot((previous) => {
          const nextThreadId = detail.currentThreadId ?? null;
          if (previous.currentThreadId === nextThreadId) return previous;
          return { ...previous, currentThreadId: nextThreadId };
        });
        return;
      }

      const app = getHostApp();
      if (app) syncFromHost(app);
    };

    window.addEventListener('openguiclaw:shell-updated', handleShellUpdated);
    window.addEventListener('openguiclaw:chat-updated', handleChatUpdated);

    return () => {
      mounted = false;
      window.removeEventListener('openguiclaw:shell-updated', handleShellUpdated);
      window.removeEventListener('openguiclaw:chat-updated', handleChatUpdated);
    };
  }, []);

  return { hostApp, snapshot, errorText };
}

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
  newWorkspaceName: '',
  newWorkspacePath: '',
  newWorkspaceError: '',
  isReceiving: false
};

function snapshotShell(app: OpenGuiclawApp): WorkspaceShellSnapshot {
  return {
    workspaces: Array.isArray(app.workspaces) ? app.workspaces.map((workspace) => ({ ...workspace })) : [],
    homeData: app.homeData
      ? {
          ...app.homeData,
          workspaces: Array.isArray(app.homeData.workspaces)
            ? app.homeData.workspaces.map((workspace) => ({
                ...workspace,
                recent_sessions: Array.isArray(workspace.recent_sessions)
                  ? workspace.recent_sessions.map((thread) => ({ ...thread }))
                  : []
              }))
            : []
        }
      : null,
    activeWorkspaceId: app.activeWorkspaceId ?? null,
    activeWorkspace: app.activeWorkspace ? { ...app.activeWorkspace } : null,
    sidebarCollapsed: !!app.sidebarCollapsed,
    workspaceThreads: Array.isArray(app.workspaceThreads) ? app.workspaceThreads.map((thread) => ({ ...thread })) : [],
    workspaceThreadMap: Object.fromEntries(
      Object.entries(app.workspaceThreadMap || {}).map(([workspaceId, threads]) => [
        workspaceId,
        Array.isArray(threads) ? threads.map((thread) => ({ ...thread })) : []
      ])
    ),
    expandedWorkspaceIds: { ...(app.expandedWorkspaceIds || {}) },
    workspaceLoading: !!app.workspaceLoading,
    currentView: app.currentView || 'home',
    currentThreadId: app.currentThreadId ?? null,
    showNewWorkspaceModal: !!app.showNewWorkspaceModal,
    showWorkspaceSwitcher: !!app.showWorkspaceSwitcher,
    showSettings: !!app.showSettings,
    settingsTab: (app as OpenGuiclawApp & { settingsTab?: string }).settingsTab || 'models',
    newWorkspaceName: app.newWorkspaceName || '',
    newWorkspacePath: app.newWorkspacePath || '',
    newWorkspaceError: app.newWorkspaceError || '',
    isReceiving: !!app.isReceiving
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
      setHostApp(app);
      setSnapshot(snapshotShell(app));
    };

    waitForHostApp()
      .then((app) => syncFromHost(app))
      .catch((error: Error) => {
        if (!mounted) return;
        setErrorText(error.message);
      });

    const handleShellUpdated = () => {
      const app = getHostApp();
      if (app) syncFromHost(app);
    };

    window.addEventListener('openguiclaw:shell-updated', handleShellUpdated);
    window.addEventListener('openguiclaw:chat-updated', handleShellUpdated);

    return () => {
      mounted = false;
      window.removeEventListener('openguiclaw:shell-updated', handleShellUpdated);
      window.removeEventListener('openguiclaw:chat-updated', handleShellUpdated);
    };
  }, []);

  return { hostApp, snapshot, errorText };
}

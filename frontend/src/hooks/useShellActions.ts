import { useCallback } from 'react';
import { dispatchShellAction, getHostApp } from '../bridge/openGuiclaw';

/**
 * useShellActions
 *
 * 第二层 React 化的核心 hook。
 * 把所有对宿主 Alpine shell 状态的写操作收成明确的桥接动作，
 * 组件不再直接读写 app.showSettings / app.showWorkspaceSwitcher 等字段。
 */
export function useShellActions() {
  const openSettings = useCallback((tab?: string) => {
    dispatchShellAction({ type: 'openSettings', tab });
  }, []);

  const closeSettings = useCallback(() => {
    dispatchShellAction({ type: 'closeSettings' });
  }, []);

  const switchSettingsTab = useCallback((tab: string) => {
    dispatchShellAction({ type: 'switchSettingsTab', tab });
  }, []);

  const openWorkspaceSwitcher = useCallback(() => {
    dispatchShellAction({ type: 'openWorkspaceSwitcher' });
  }, []);

  const closeWorkspaceSwitcher = useCallback(() => {
    dispatchShellAction({ type: 'closeWorkspaceSwitcher' });
  }, []);

  const toggleSidebar = useCallback(() => {
    dispatchShellAction({ type: 'toggleSidebar' });
  }, []);

  const setSidebarCollapsed = useCallback((collapsed: boolean) => {
    dispatchShellAction({ type: 'setSidebarCollapsed', collapsed });
  }, []);

  const navigateView = useCallback((view: string) => {
    dispatchShellAction({ type: 'navigateView', view });
  }, []);

  /** 切换工作区并跳转到其 home 视图 */
  const switchWorkspace = useCallback(async (wsId: string) => {
    const app = getHostApp();
    if (!app) return;
    await app.focusWorkspaceHome?.(wsId);
  }, []);

  return {
    openSettings,
    closeSettings,
    switchSettingsTab,
    openWorkspaceSwitcher,
    closeWorkspaceSwitcher,
    toggleSidebar,
    setSidebarCollapsed,
    navigateView,
    switchWorkspace,
  };
}

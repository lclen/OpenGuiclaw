import { useMemo } from 'react';
import { useShellActions } from '../hooks/useShellActions';
import { useWorkspaceShellBridge } from '../hooks/useWorkspaceShellBridge';

/**
 * WorkspaceSwitcherButton
 *
 * 第二层 React 化：工作区切换入口按钮。
 * 原来 Alpine 模板直接写 showWorkspaceSwitcher = true，
 * 现在通过 dispatchShellAction({ type: 'openWorkspaceSwitcher' }) 桥接。
 *
 * 同时渲染一个内联的工作区下拉列表（当 showWorkspaceSwitcher 为 true 时），
 * 替代原来散落在 sidebar_shell.html 中的 Alpine x-show 逻辑。
 */
export function WorkspaceSwitcherButton() {
  const { snapshot, hostApp } = useWorkspaceShellBridge();
  const { openWorkspaceSwitcher, closeWorkspaceSwitcher, switchWorkspace } = useShellActions();

  const isOpen = snapshot.showWorkspaceSwitcher;
  const activeWsName = snapshot.activeWorkspace?.name ?? null;
  const workspaces = snapshot.workspaces;

  const sortedWorkspaces = useMemo(() => {
    const active = snapshot.activeWorkspaceId;
    return [...workspaces].sort((a, b) => {
      if (a.id === active) return -1;
      if (b.id === active) return 1;
      return (a.name ?? '').localeCompare(b.name ?? '');
    });
  }, [workspaces, snapshot.activeWorkspaceId]);

  function handleToggle() {
    if (isOpen) {
      closeWorkspaceSwitcher();
    } else {
      openWorkspaceSwitcher();
    }
  }

  async function handleSelect(wsId: string) {
    closeWorkspaceSwitcher();
    await switchWorkspace(wsId);
  }

  function handleOpenNewModal() {
    closeWorkspaceSwitcher();
    hostApp?.openNewWorkspaceModal?.();
  }

  return (
    <div className="react-ws-switcher-wrap">
      <button
        type="button"
        className={`react-ws-switcher-btn${isOpen ? ' is-open' : ''}`}
        aria-haspopup="listbox"
        aria-expanded={isOpen}
        aria-label="切换工作区"
        onClick={handleToggle}
      >
        <svg
          className="react-ws-switcher-icon"
          width="14"
          height="14"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          aria-hidden="true"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth="2"
            d="M3 7h18M3 12h18M3 17h18"
          />
        </svg>
        <span className="react-ws-switcher-label">
          {activeWsName ?? '选择工作区'}
        </span>
        <svg
          className={`react-ws-switcher-chevron${isOpen ? ' open' : ''}`}
          width="12"
          height="12"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          aria-hidden="true"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.2" d="M6 9l6 6 6-6" />
        </svg>
      </button>

      {isOpen && (
        <>
          {/* 点击遮罩关闭 */}
          <div
            className="react-ws-switcher-backdrop"
            aria-hidden="true"
            onClick={closeWorkspaceSwitcher}
          />
          <ul
            className="react-ws-switcher-dropdown"
            role="listbox"
            aria-label="工作区列表"
          >
            {sortedWorkspaces.length === 0 && (
              <li className="react-ws-switcher-empty">还没有工作区</li>
            )}
            {sortedWorkspaces.map((ws) => {
              const isActive = ws.id === snapshot.activeWorkspaceId;
              return (
                <li key={ws.id} role="option" aria-selected={isActive}>
                  <button
                    type="button"
                    className={`react-ws-switcher-item${isActive ? ' is-active' : ''}`}
                    onClick={() => handleSelect(ws.id)}
                  >
                    <span className="react-ws-switcher-item-name">
                      {ws.name}
                      {ws.is_default ? ' · 默认' : ''}
                    </span>
                    {ws.thread_count != null && (
                      <span className="react-ws-switcher-item-count">{ws.thread_count}</span>
                    )}
                    {isActive && (
                      <svg
                        className="react-ws-switcher-item-check"
                        width="12"
                        height="12"
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="currentColor"
                        aria-hidden="true"
                      >
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M5 13l4 4L19 7" />
                      </svg>
                    )}
                  </button>
                </li>
              );
            })}
            <li className="react-ws-switcher-divider" role="separator" />
            <li role="option" aria-selected={false}>
              <button
                type="button"
                className="react-ws-switcher-item react-ws-switcher-add"
                onClick={handleOpenNewModal}
              >
                <svg
                  width="13"
                  height="13"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  aria-hidden="true"
                >
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.2" d="M12 5v14M5 12h14" />
                </svg>
                <span>新建工作区</span>
              </button>
            </li>
          </ul>
        </>
      )}
    </div>
  );
}

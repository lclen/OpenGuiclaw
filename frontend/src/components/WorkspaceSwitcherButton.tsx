import { useMemo } from 'react';
import { useShellActions } from '../hooks/useShellActions';
import { useWorkspaceShellBridge } from '../hooks/useWorkspaceShellBridge';
import { CaretDownIcon } from './icons/ShellIcons';
import { UiButton } from './ui/UiButton';
import { UiMenuDivider, UiMenuItem, UiMenuSurface } from './ui/UiMenu';

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
      <UiButton
        className={`react-ws-switcher-btn${isOpen ? ' is-open' : ''}`}
        variant="secondary"
        size="md"
        active={isOpen}
        aria-haspopup="listbox"
        aria-expanded={isOpen}
        aria-label="切换工作区"
        onClick={handleToggle}
        leading={
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
        }
        trailing={<CaretDownIcon className={`react-ws-switcher-chevron${isOpen ? ' open' : ''}`} />}
      >
        <span className="react-ws-switcher-label">
          {activeWsName ?? '选择工作区'}
        </span>
      </UiButton>

      {isOpen && (
        <>
          <UiMenuSurface
            className="react-ws-switcher-dropdown"
            role="listbox"
            aria-label="工作区列表"
            backdrop
            onBackdropClick={closeWorkspaceSwitcher}
          >
            {sortedWorkspaces.length === 0 && (
              <div className="react-ws-switcher-empty">还没有工作区</div>
            )}
            {sortedWorkspaces.map((ws) => {
              const isActive = ws.id === snapshot.activeWorkspaceId;
              return (
                <div key={ws.id} role="option" aria-selected={isActive}>
                  <UiMenuItem
                    className={`react-ws-switcher-item${isActive ? ' is-active' : ''}`}
                    selected={isActive}
                    onClick={() => handleSelect(ws.id)}
                    trailing={
                      <>
                        {ws.thread_count != null ? (
                          <span className="react-ws-switcher-item-count">{ws.thread_count}</span>
                        ) : null}
                        {isActive ? (
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
                        ) : null}
                      </>
                    }
                  >
                    <span className="react-ws-switcher-item-name">
                      {ws.name}
                      {ws.is_default ? ' · 默认' : ''}
                    </span>
                  </UiMenuItem>
                </div>
              );
            })}
            <UiMenuDivider />
            <div role="option" aria-selected={false}>
              <UiMenuItem
                className="react-ws-switcher-item react-ws-switcher-add"
                onClick={handleOpenNewModal}
                leading={
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
                }
              >
                <span>新建工作区</span>
              </UiMenuItem>
            </div>
          </UiMenuSurface>
        </>
      )}
    </div>
  );
}

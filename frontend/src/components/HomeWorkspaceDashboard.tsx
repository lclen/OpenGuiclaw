import { useEffect, useRef } from 'react';
import { dispatchShellAction } from '../bridge/openGuiclaw';
import { ChatComposer } from './ChatComposer';
import { CaretDownIcon } from './icons/ShellIcons';
import { ImOverviewCard } from './ImOverviewCard';
import { useWorkspaceShellBridge } from '../hooks/useWorkspaceShellBridge';

export function HomeWorkspaceDashboard() {
  const { hostApp, snapshot, errorText } = useWorkspaceShellBridge();
  const rootRef = useRef<HTMLDivElement | null>(null);

  function getDisplayWorkspaceName(name?: string | null) {
    if (!name || name === 'Default Workspace') return '默认工作区';
    return name;
  }

  useEffect(() => {
    if (!snapshot.showWorkspaceSwitcher) return undefined;

    const handleKeydown = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return;
      dispatchShellAction({ type: 'closeWorkspaceSwitcher' });
    };

    const handlePointerDown = (event: MouseEvent) => {
      if (!rootRef.current) return;
      if (rootRef.current.contains(event.target as Node)) return;
      dispatchShellAction({ type: 'closeWorkspaceSwitcher' });
    };

    window.addEventListener('keydown', handleKeydown);
    window.addEventListener('mousedown', handlePointerDown);
    return () => {
      window.removeEventListener('keydown', handleKeydown);
      window.removeEventListener('mousedown', handlePointerDown);
    };
  }, [snapshot.showWorkspaceSwitcher]);

  async function handleSelectWorkspace(workspaceId: string) {
    await hostApp?.focusWorkspaceHome?.(workspaceId);
  }

  function handleOpenWorkspaceModal() {
    hostApp?.openNewWorkspaceModal?.();
  }

  function toggleWorkspaceSwitcher() {
    if (snapshot.showWorkspaceSwitcher) {
      dispatchShellAction({ type: 'closeWorkspaceSwitcher' });
    } else {
      dispatchShellAction({ type: 'openWorkspaceSwitcher' });
    }
  }

  const activeWorkspaceName = snapshot.activeWorkspaceId
    ? getDisplayWorkspaceName(snapshot.workspaces.find((workspace) => workspace.id === snapshot.activeWorkspaceId)?.name) || '当前工作区'
    : '选择工作区';

  return (
    <div ref={rootRef} className="home-shell custom-scrollbar">
      {errorText ? <div className="chat-react-error">{errorText}</div> : null}

      <section className="home-hero">
        <div className="home-hero-orb">
          <span>O</span>
        </div>
        <div className="home-kicker">OpenGuiclaw 智能工作台</div>
        <h1>从这里开始你的下一项任务</h1>
        <p className="home-hero-copy">
          选择工作区，直接输入需求，让当前项目上下文自然接入接下来的每一次对话。
        </p>

        <div className="home-workspace-picker">
          <button type="button" className="home-active-pill home-active-pill-button" onClick={toggleWorkspaceSwitcher}>
            <span>{activeWorkspaceName}</span>
            <CaretDownIcon className={`home-pill-chevron ${snapshot.showWorkspaceSwitcher ? 'open' : ''}`} />
          </button>

          {snapshot.showWorkspaceSwitcher ? (
            <div className="home-workspace-dropdown">
              <div className="home-workspace-dropdown-label">选择工作区</div>

              <div className="home-workspace-dropdown-list">
                {snapshot.workspaces.map((workspace) => (
                  <button
                    key={workspace.id}
                    type="button"
                    className="home-workspace-dropdown-item"
                    onClick={() => handleSelectWorkspace(workspace.id)}
                  >
                    <span className="home-workspace-dropdown-icon">W</span>
                    <span className="home-workspace-dropdown-name">
                      {getDisplayWorkspaceName(workspace.name)}
                      {workspace.is_default ? ' · 默认' : ''}
                    </span>
                    {snapshot.activeWorkspaceId === workspace.id ? (
                      <span className="home-workspace-dropdown-check">当前</span>
                    ) : null}
                  </button>
                ))}
              </div>

              <button type="button" className="home-workspace-dropdown-add" onClick={handleOpenWorkspaceModal}>
                <span>+</span>
                <span>添加工作区</span>
              </button>
            </div>
          ) : null}
        </div>
      </section>

      {snapshot.workspaceLoading ? (
        <div className="home-loading">
          <svg width="14" height="14" fill="none" stroke="currentColor" viewBox="0 0 24 24" style={{ animation: 'spin 1s linear infinite' }}>
            <circle cx="12" cy="12" r="10" strokeWidth="3" strokeDasharray="30 70" strokeLinecap="round" />
          </svg>
          <span>正在加载工作区概览...</span>
        </div>
      ) : null}

      <section className={`home-compose-stage ${snapshot.workspaces.length === 0 ? 'is-empty' : ''}`}>
        <div className="home-compose-backdrop"></div>

        <div className="home-compose-panel">
          {snapshot.workspaces.length > 0 ? (
            <ChatComposer />
          ) : (
            <div className="welcome-placeholder">
              <svg width="48" height="48" fill="none" stroke="var(--shell-accent)" viewBox="0 0 24 24" style={{ opacity: 0.4 }}>
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7z" />
              </svg>
              <h2>先创建一个工作区</h2>
              <p>创建后这里会成为主页的主输入区，随时可以直接发起新任务。</p>
              <button type="button" className="btn-primary" onClick={handleOpenWorkspaceModal}>
                创建第一个工作区
              </button>
            </div>
          )}
        </div>
      </section>

      <ImOverviewCard />
    </div>
  );
}

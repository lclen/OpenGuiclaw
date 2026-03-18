import { useEffect, useRef } from 'react';
import { dispatchShellAction } from '../bridge/openGuiclaw';
import { useWorkspaceShellBridge } from '../hooks/useWorkspaceShellBridge';

export function HomeWorkspaceDashboard() {
  const { hostApp, snapshot, errorText } = useWorkspaceShellBridge();
  const rootRef = useRef<HTMLDivElement | null>(null);
  const recentWorkspaces = snapshot.homeData?.workspaces || [];
  const hasRecentThreads = recentWorkspaces.some((workspace) => (workspace.recent_sessions || []).length > 0);

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

  async function handleRecentThread(workspaceId: string, sessionId: string) {
    if (!hostApp) return;
    await hostApp.switchWorkspace?.(workspaceId, true);
    await hostApp.loadThread?.(workspaceId, sessionId);
  }

  async function handleNewThread() {
    if (!hostApp) return;
    if (snapshot.activeWorkspaceId) {
      await hostApp.createThread?.(snapshot.activeWorkspaceId);
    } else {
      hostApp.openNewWorkspaceModal?.();
    }
  }

  function handleOpenSettings() {
    dispatchShellAction({ type: 'openSettings' });
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
    ? snapshot.workspaces.find((workspace) => workspace.id === snapshot.activeWorkspaceId)?.name || '当前工作区'
    : '选择工作区';

  return (
    <div ref={rootRef} className="home-shell custom-scrollbar">
      {errorText ? <div className="chat-react-error">{errorText}</div> : null}

      <section className="home-hero">
        <div className="home-hero-orb">
          <span>O</span>
        </div>
        <div className="home-kicker">OpenGuiclaw 工作台</div>
        <h1>开始构建</h1>
        <p className="home-hero-copy">
          用更清晰的方式管理多个项目、线程和设置，把当前上下文始终留在视野中。
        </p>

        <div className="home-workspace-picker">
          <button type="button" className="home-active-pill home-active-pill-button" onClick={toggleWorkspaceSwitcher}>
            <span>{activeWorkspaceName}</span>
            <span className={`home-pill-chevron ${snapshot.showWorkspaceSwitcher ? 'open' : ''}`}>v</span>
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
                    <span className="home-workspace-dropdown-name">{workspace.name}</span>
                    {snapshot.activeWorkspaceId === workspace.id ? (
                      <span className="home-workspace-dropdown-check">OK</span>
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

        <div className="home-suggestion-grid">
          <button type="button" className="home-suggestion-card" onClick={handleNewThread}>
            <span className="home-suggestion-icon">+</span>
            <strong>开始新线程</strong>
            <p>在当前工作区中开启一个全新的任务上下文。</p>
          </button>
          <button type="button" className="home-suggestion-card" onClick={handleOpenSettings}>
            <span className="home-suggestion-icon">S</span>
            <strong>整理设置</strong>
            <p>检查模型、身份和集成，把常用配置放在顺手的位置。</p>
          </button>
          <button type="button" className="home-suggestion-card" onClick={handleOpenWorkspaceModal}>
            <span className="home-suggestion-icon">W</span>
            <strong>添加项目</strong>
            <p>通过目录选择器接入一个新项目，不再手动输入路径。</p>
          </button>
        </div>
      </section>

      {snapshot.workspaceLoading ? (
        <div className="home-loading">
          <svg width="14" height="14" fill="none" stroke="currentColor" viewBox="0 0 24 24" style={{ animation: 'spin 1s linear infinite' }}>
            <circle cx="12" cy="12" r="10" strokeWidth="3" strokeDasharray="30 70" strokeLinecap="round" />
          </svg>
          <span>正在加载工作区概览...</span>
        </div>
      ) : (
        <div className="home-columns">
          <section className="home-surface">
            <div className="home-section-header">
              <div>
                <div className="home-section-kicker">项目</div>
                <h2>工作区</h2>
              </div>
              <button type="button" className="home-link-button" onClick={handleOpenWorkspaceModal}>
                新建工作区
              </button>
            </div>

            {snapshot.workspaces.length > 0 ? (
              <div className="home-workspace-list">
                {snapshot.workspaces.map((workspace) => (
                  <button
                    key={workspace.id}
                    type="button"
                    className={`home-workspace-row ${snapshot.activeWorkspaceId === workspace.id ? 'active' : ''}`}
                    onClick={() => handleSelectWorkspace(workspace.id)}
                  >
                    <div className="home-workspace-main">
                      <div className="home-workspace-icon">W</div>
                      <div className="home-workspace-copy">
                        <div className="home-workspace-title">
                          <span>{workspace.name}</span>
                          {snapshot.activeWorkspaceId === workspace.id ? <span className="home-badge">当前</span> : null}
                        </div>
                        <div className="home-workspace-path">{workspace.workspace_path || ''}</div>
                      </div>
                    </div>
                    <div className="home-workspace-meta">{`${workspace.thread_count || 0} 个线程`}</div>
                  </button>
                ))}
              </div>
            ) : (
              <div className="welcome-placeholder">
                <svg width="48" height="48" fill="none" stroke="var(--shell-accent)" viewBox="0 0 24 24" style={{ opacity: 0.4 }}>
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7z" />
                </svg>
                <h2>暂无工作区</h2>
                <p>先创建一个项目入口，后面的对话和设置都会跟着更清晰。</p>
                <button type="button" className="btn-primary" onClick={handleOpenWorkspaceModal}>
                  创建第一个工作区
                </button>
              </div>
            )}
          </section>

          <section className="home-surface">
            <div className="home-section-header">
              <div>
                <div className="home-section-kicker">最近</div>
                <h2>最近线程</h2>
              </div>
            </div>

            {hasRecentThreads ? (
              <div className="home-thread-list">
                {recentWorkspaces.map((workspace) =>
                  (workspace.recent_sessions || []).map((thread) => (
                    <button
                      key={`${workspace.id}-${thread.session_id}`}
                      type="button"
                      className="home-thread-row"
                      onClick={() => handleRecentThread(workspace.id, thread.session_id)}
                    >
                      <div className="home-thread-main">
                        <span className="home-thread-dot"></span>
                        <div className="home-thread-copy">
                          <span className="home-thread-title">{thread.title || thread.session_id}</span>
                          <span className="home-thread-workspace">{workspace.name}</span>
                        </div>
                      </div>
                    </button>
                  ))
                )}
              </div>
            ) : (
              <div className="home-empty-inline">最近还没有值得回看的线程记录。</div>
            )}
          </section>
        </div>
      )}
    </div>
  );
}

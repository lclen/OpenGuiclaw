import { useEffect, useRef } from 'react';
import { emitShellUpdate } from '../bridge/openGuiclaw';
import { useWorkspaceShellBridge } from '../hooks/useWorkspaceShellBridge';

export function HomeWorkspaceDashboard() {
  const { hostApp, snapshot, errorText } = useWorkspaceShellBridge();
  const rootRef = useRef<HTMLDivElement | null>(null);
  const recentWorkspaces = snapshot.homeData?.workspaces || [];
  const hasRecentThreads = recentWorkspaces.some((workspace) => (workspace.recent_sessions || []).length > 0);

  useEffect(() => {
    if (!snapshot.showWorkspaceSwitcher) return undefined;

    const handleKeydown = (event: KeyboardEvent) => {
      if (event.key !== 'Escape' || !hostApp) return;
      hostApp.showWorkspaceSwitcher = false;
      emitShellUpdate();
    };

    const handlePointerDown = (event: MouseEvent) => {
      if (!hostApp || !rootRef.current) return;
      if (rootRef.current.contains(event.target as Node)) return;
      hostApp.showWorkspaceSwitcher = false;
      emitShellUpdate();
    };

    window.addEventListener('keydown', handleKeydown);
    window.addEventListener('mousedown', handlePointerDown);
    return () => {
      window.removeEventListener('keydown', handleKeydown);
      window.removeEventListener('mousedown', handlePointerDown);
    };
  }, [hostApp, snapshot.showWorkspaceSwitcher]);

  async function handleSelectWorkspace(workspaceId: string) {
    await hostApp?.focusWorkspaceHome?.(workspaceId);
    emitShellUpdate();
  }

  async function handleRecentThread(workspaceId: string, sessionId: string) {
    if (!hostApp) return;
    await hostApp.switchWorkspace?.(workspaceId, true);
    await hostApp.loadThread?.(workspaceId, sessionId);
    emitShellUpdate();
  }

  async function handleNewThread() {
    if (!hostApp) return;
    if (snapshot.activeWorkspaceId) {
      await hostApp.createThread?.(snapshot.activeWorkspaceId);
    } else {
      hostApp.openNewWorkspaceModal?.();
    }
    emitShellUpdate();
  }

  function handleOpenSettings() {
    if (!hostApp) return;
    hostApp.showSettings = true;
    emitShellUpdate();
  }

  function handleOpenWorkspaceModal() {
    hostApp?.openNewWorkspaceModal?.();
    emitShellUpdate();
  }

  function toggleWorkspaceSwitcher() {
    if (!hostApp) return;
    hostApp.showWorkspaceSwitcher = !snapshot.showWorkspaceSwitcher;
    emitShellUpdate();
  }

  const activeWorkspaceName = snapshot.activeWorkspaceId
    ? snapshot.workspaces.find((workspace) => workspace.id === snapshot.activeWorkspaceId)?.name || 'Current Workspace'
    : 'Choose your workspace';

  return (
    <div ref={rootRef} className="home-shell custom-scrollbar">
      {errorText ? <div className="chat-react-error">{errorText}</div> : null}

      <section className="home-hero">
        <div className="home-hero-orb">
          <span>O</span>
        </div>
        <div className="home-kicker">OpenGuiclaw Workspace Hub</div>
        <h1>Start Building</h1>
        <p className="home-hero-copy">
          Manage projects, threads, and settings with a cleaner shell so the current context always stays in view.
        </p>

        <div className="home-workspace-picker">
          <button type="button" className="home-active-pill home-active-pill-button" onClick={toggleWorkspaceSwitcher}>
            <span>{activeWorkspaceName}</span>
            <span className={`home-pill-chevron ${snapshot.showWorkspaceSwitcher ? 'open' : ''}`}>v</span>
          </button>

          {snapshot.showWorkspaceSwitcher ? (
            <div className="home-workspace-dropdown">
              <div className="home-workspace-dropdown-label">Choose your workspace</div>

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
                <span>Add workspace</span>
              </button>
            </div>
          ) : null}
        </div>

        <div className="home-suggestion-grid">
          <button type="button" className="home-suggestion-card" onClick={handleNewThread}>
            <span className="home-suggestion-icon">+</span>
            <strong>Start New Thread</strong>
            <p>Open a fresh task context in the current workspace.</p>
          </button>
          <button type="button" className="home-suggestion-card" onClick={handleOpenSettings}>
            <span className="home-suggestion-icon">S</span>
            <strong>Review Settings</strong>
            <p>Check models, identity, and integrations without leaving the shell.</p>
          </button>
          <button type="button" className="home-suggestion-card" onClick={handleOpenWorkspaceModal}>
            <span className="home-suggestion-icon">W</span>
            <strong>Add Workspace</strong>
            <p>Connect a project through the native directory picker instead of typing paths by hand.</p>
          </button>
        </div>
      </section>

      {snapshot.workspaceLoading ? (
        <div className="home-loading">
          <svg width="14" height="14" fill="none" stroke="currentColor" viewBox="0 0 24 24" style={{ animation: 'spin 1s linear infinite' }}>
            <circle cx="12" cy="12" r="10" strokeWidth="3" strokeDasharray="30 70" strokeLinecap="round" />
          </svg>
          <span>Loading workspace overview...</span>
        </div>
      ) : (
        <div className="home-columns">
          <section className="home-surface">
            <div className="home-section-header">
              <div>
                <div className="home-section-kicker">Projects</div>
                <h2>Workspaces</h2>
              </div>
              <button type="button" className="home-link-button" onClick={handleOpenWorkspaceModal}>
                New Workspace
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
                          {snapshot.activeWorkspaceId === workspace.id ? <span className="home-badge">Current</span> : null}
                        </div>
                        <div className="home-workspace-path">{workspace.workspace_path || ''}</div>
                      </div>
                    </div>
                    <div className="home-workspace-meta">{`${workspace.thread_count || 0} threads`}</div>
                  </button>
                ))}
              </div>
            ) : (
              <div className="welcome-placeholder">
                <svg width="48" height="48" fill="none" stroke="var(--shell-accent)" viewBox="0 0 24 24" style={{ opacity: 0.4 }}>
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7z" />
                </svg>
                <h2>No Workspaces Yet</h2>
                <p>Create your first project entry and the rest of the shell will become much easier to navigate.</p>
                <button type="button" className="btn-primary" onClick={handleOpenWorkspaceModal}>
                  Create First Workspace
                </button>
              </div>
            )}
          </section>

          <section className="home-surface">
            <div className="home-section-header">
              <div>
                <div className="home-section-kicker">Recent</div>
                <h2>Recent Threads</h2>
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
              <div className="home-empty-inline">There are no recent threads to revisit yet.</div>
            )}
          </section>
        </div>
      )}
    </div>
  );
}

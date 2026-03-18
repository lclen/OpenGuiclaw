import { dispatchShellAction, emitShellUpdate } from '../bridge/openGuiclaw';
import { useWorkspaceShellBridge } from '../hooks/useWorkspaceShellBridge';

function formatThreadTime(hostFormat: ((value?: string | null) => string) | undefined, value?: string | null) {
  if (typeof hostFormat === 'function') {
    return hostFormat(value);
  }

  if (!value) return '';
  const date = new Date(String(value).replace(' ', 'T'));
  if (Number.isNaN(date.getTime())) return '';

  const diffMs = Date.now() - date.getTime();
  const hourMs = 60 * 60 * 1000;
  const dayMs = 24 * hourMs;
  if (diffMs < hourMs) return `${Math.max(1, Math.round(diffMs / (60 * 1000)))} 分钟前`;
  if (diffMs < dayMs) return `${Math.round(diffMs / hourMs)} 小时前`;
  return `${Math.round(diffMs / dayMs)} 天前`;
}

export function WorkspaceSidebar() {
  const { hostApp, snapshot, errorText } = useWorkspaceShellBridge();

  async function handleNewThread() {
    if (!hostApp) return;
    if (snapshot.activeWorkspaceId) {
      await hostApp.createThread?.(snapshot.activeWorkspaceId);
    } else {
      hostApp.openNewWorkspaceModal?.();
    }
    emitShellUpdate();
  }

  async function handleOpenPanel(view: string) {
    await hostApp?.openSidebarPanel?.(view);
    emitShellUpdate();
  }

  async function handleToggleWorkspace(workspaceId: string) {
    await hostApp?.toggleWorkspaceGroup?.(workspaceId);
    emitShellUpdate();
  }

  async function handleOpenThread(workspaceId: string, sessionId: string) {
    await hostApp?.openSidebarThread?.(workspaceId, sessionId);
    emitShellUpdate();
  }

  async function handleTogglePin(workspaceId: string, sessionId: string, pinned: boolean) {
    await hostApp?.toggleThreadPin?.(workspaceId, sessionId, pinned);
    emitShellUpdate();
  }

  async function handleDeleteThread(workspaceId: string, sessionId: string) {
    if (!hostApp) return;
    const confirmed = window.confirm('删除此线程？此操作不可撤销。');
    if (!confirmed) return;
    await hostApp.deleteThread?.(workspaceId, sessionId);
    emitShellUpdate();
  }

  function handleOpenSettings() {
    dispatchShellAction({ type: 'openSettings' });
  }

  function handleOpenWorkspaceModal() {
    hostApp?.openNewWorkspaceModal?.();
    emitShellUpdate();
  }

  return (
    <aside className={`sidebar react-shell-sidebar${snapshot.sidebarCollapsed ? ' sidebar-collapsed' : ''}`}>
      <div className="sidebar-brand sidebar-brand-minimal">
        <button
          type="button"
          className={`sidebar-home-btn sidebar-brand-link${snapshot.currentView === 'home' ? ' active' : ''}`}
          onClick={() => handleOpenPanel('home')}
        >
          <span className="sidebar-logo">O</span>
          <span className="sidebar-home-copy">
            <strong>openGuiclaw</strong>
            <small>工作台</small>
          </span>
        </button>
      </div>

      <div className="sidebar-shortcuts">
        <button type="button" className="sidebar-shortcut-btn" onClick={handleNewThread}>
          <span className="sidebar-shortcut-icon">+</span>
          <span>New Thread</span>
        </button>
        <button
          type="button"
          className={`sidebar-shortcut-btn${snapshot.currentView === 'home' ? ' active' : ''}`}
          onClick={() => handleOpenPanel('home')}
        >
          <span className="sidebar-shortcut-icon">H</span>
          <span>Workspace</span>
        </button>
        <button
          type="button"
          className={`sidebar-shortcut-btn${snapshot.currentView === 'skills' ? ' active' : ''}`}
          onClick={() => handleOpenPanel('skills')}
        >
          <span className="sidebar-shortcut-icon">S</span>
          <span>Skills</span>
        </button>
        <button
          type="button"
          className={`sidebar-shortcut-btn${snapshot.currentView === 'scheduler' ? ' active' : ''}`}
          onClick={() => handleOpenPanel('scheduler')}
        >
          <span className="sidebar-shortcut-icon">A</span>
          <span>Automation</span>
        </button>
      </div>

      <div className="sidebar-divider"></div>

      <div className="sidebar-thread-groups custom-scrollbar">
        <div className="sidebar-section-row">
          <span className="sidebar-section-label">Threads</span>
          <div className="sidebar-section-tools">
            <button type="button" className="sidebar-section-tool" onClick={handleOpenWorkspaceModal} aria-label="Add workspace">
              +
            </button>
          </div>
        </div>

        {errorText ? <div className="sidebar-empty-state">{errorText}</div> : null}

        {snapshot.workspaces.map((workspace) => {
          const threads =
            typeof hostApp?.getSidebarWorkspaceThreads === 'function'
              ? hostApp.getSidebarWorkspaceThreads(workspace.id)
              : snapshot.workspaceThreadMap[workspace.id] || [];
          const expanded =
            typeof hostApp?.isWorkspaceExpanded === 'function'
              ? hostApp.isWorkspaceExpanded(workspace.id)
              : !!snapshot.expandedWorkspaceIds[workspace.id];

          return (
            <section key={workspace.id} className="sidebar-workspace-group">
              <button
                type="button"
                className={`sidebar-workspace-header${snapshot.activeWorkspaceId === workspace.id ? ' active' : ''}`}
                onClick={() => handleToggleWorkspace(workspace.id)}
              >
                <span className="sidebar-workspace-folder">W</span>
                <span className="sidebar-workspace-name">
                  {workspace.name}
                  {workspace.is_default ? ' · 默认' : ''}
                </span>
                <span className="sidebar-workspace-count">{workspace.thread_count || threads.length || 0}</span>
                <span className={`sidebar-workspace-chevron${expanded ? ' open' : ''}`}>^</span>
              </button>

              {expanded && threads.length > 0 ? (
                <div className="sidebar-group-threads sidebar-fade-scroll custom-scrollbar">
                  {threads.map((thread) => (
                    <div
                      key={thread.session_id}
                      className={`sidebar-thread-preview${snapshot.currentThreadId === thread.session_id ? ' active' : ''}`}
                    >
                      <button
                        type="button"
                        className={`sidebar-thread-pin-toggle${thread.pinned ? ' is-pinned' : ''}`}
                        title={thread.pinned ? 'Unpin thread' : 'Pin thread'}
                        onClick={() => handleTogglePin(workspace.id, thread.session_id, !!thread.pinned)}
                      >
                        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" aria-hidden="true">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.1" d="M9 3h6l-1.2 5.2L18 12v1H13v7l-2-1.8V13H6v-1l4.2-3.8L9 3z" />
                        </svg>
                      </button>

                      <button
                        type="button"
                        className="sidebar-thread-preview-main"
                        onClick={() => handleOpenThread(workspace.id, thread.session_id)}
                      >
                        <span className="sidebar-thread-preview-copy">
                          <span className="sidebar-thread-preview-title">{thread.title || `${thread.session_id.slice(0, 24)}...`}</span>
                          <span className="sidebar-thread-preview-meta">
                            {formatThreadTime(hostApp?.formatSidebarSessionTime, thread.updated_at)}
                          </span>
                        </span>
                      </button>

                      <div className="sidebar-thread-preview-actions">
                        <button
                          type="button"
                          className="sidebar-thread-action danger"
                          title="Delete thread"
                          onClick={() => handleDeleteThread(workspace.id, thread.session_id)}
                        >
                          x
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              ) : null}

              {expanded && threads.length === 0 ? <div className="sidebar-empty-caption">No threads yet</div> : null}
            </section>
          );
        })}

        {snapshot.workspaces.length === 0 ? <div className="sidebar-empty-state">No workspaces yet. Add one to begin.</div> : null}
      </div>

      <div className="sidebar-footer">
        <button type="button" className="sidebar-shortcut-btn sidebar-footer-btn" onClick={handleOpenSettings}>
          <span className="sidebar-shortcut-icon">S</span>
          <span>Settings</span>
        </button>
      </div>
    </aside>
  );
}

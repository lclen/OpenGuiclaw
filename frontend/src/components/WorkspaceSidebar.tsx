import { useEffect, useState } from 'react';
import { dispatchShellAction, emitShellUpdate } from '../bridge/openGuiclaw';
import { CaretDownIcon, MoreHorizontalIcon } from './icons/ShellIcons';
import { useWorkspaceShellBridge } from '../hooks/useWorkspaceShellBridge';

const CONTEXT_MENU_WIDTH = 196;
const CONTEXT_MENU_HEIGHT = 156;

type ThreadContextMenuState = {
  workspaceId: string;
  sessionId: string;
  workspaceName: string;
  title: string;
  pinned: boolean;
  x: number;
  y: number;
};

type RenameDialogState = {
  workspaceId: string;
  sessionId: string;
  initialTitle: string;
};

function getDisplayWorkspaceName(name?: string | null) {
  if (!name || name === 'Default Workspace') return '默认工作区';
  return name;
}

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
  const [contextMenu, setContextMenu] = useState<ThreadContextMenuState | null>(null);
  const [renameDialog, setRenameDialog] = useState<RenameDialogState | null>(null);
  const [renameDraft, setRenameDraft] = useState('');
  const [renameError, setRenameError] = useState('');

  useEffect(() => {
    if (!contextMenu && !renameDialog) return undefined;

    const closeContextMenu = () => setContextMenu(null);
    const handleKeydown = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return;
      setContextMenu(null);
      setRenameDialog(null);
      setRenameDraft('');
      setRenameError('');
    };

    window.addEventListener('mousedown', closeContextMenu);
    window.addEventListener('resize', closeContextMenu);
    window.addEventListener('scroll', closeContextMenu, true);
    window.addEventListener('keydown', handleKeydown);
    return () => {
      window.removeEventListener('mousedown', closeContextMenu);
      window.removeEventListener('resize', closeContextMenu);
      window.removeEventListener('scroll', closeContextMenu, true);
      window.removeEventListener('keydown', handleKeydown);
    };
  }, [contextMenu, renameDialog]);

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
    const confirmed = window.confirm('删除这条历史对话？此操作不可撤销。');
    if (!confirmed) return;
    await hostApp.deleteThread?.(workspaceId, sessionId);
    emitShellUpdate();
  }

  async function handleRenameThread(workspaceId: string, sessionId: string, title: string) {
    if (!hostApp) return;
    await hostApp.renameThread?.(workspaceId, sessionId, title);
    emitShellUpdate();
  }

  function handleOpenSettings() {
    dispatchShellAction({ type: 'openSettings' });
  }

  function handleOpenWorkspaceModal() {
    hostApp?.openNewWorkspaceModal?.();
    emitShellUpdate();
  }

  function handleThreadContextMenu(
    event: React.MouseEvent<HTMLDivElement>,
    workspaceId: string,
    workspaceName: string,
    sessionId: string,
    title: string,
    pinned: boolean
  ) {
    event.preventDefault();
    event.stopPropagation();
    const clampedX = Math.min(event.clientX, window.innerWidth - CONTEXT_MENU_WIDTH);
    const clampedY = Math.min(event.clientY, window.innerHeight - CONTEXT_MENU_HEIGHT);
    setContextMenu({
      workspaceId,
      workspaceName,
      sessionId,
      title,
      pinned,
      x: Math.max(12, clampedX),
      y: Math.max(12, clampedY)
    });
  }

  function handleStartRename() {
    if (!contextMenu) return;
    setRenameDialog({
      workspaceId: contextMenu.workspaceId,
      sessionId: contextMenu.sessionId,
      initialTitle: contextMenu.title
    });
    setRenameDraft(contextMenu.title);
    setRenameError('');
    setContextMenu(null);
  }

  async function handleSubmitRename(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!renameDialog) return;
    const nextTitle = renameDraft.trim();
    if (!nextTitle) {
      setRenameError('请输入新的对话名称');
      return;
    }

    try {
      await handleRenameThread(renameDialog.workspaceId, renameDialog.sessionId, nextTitle);
      setRenameDialog(null);
      setRenameDraft('');
      setRenameError('');
    } catch (error) {
      setRenameError(error instanceof Error ? error.message : '重命名失败，请稍后重试');
    }
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
          <span>新建对话</span>
        </button>
        <button
          type="button"
          className={`sidebar-shortcut-btn${snapshot.currentView === 'home' ? ' active' : ''}`}
          onClick={() => handleOpenPanel('home')}
        >
          <span className="sidebar-shortcut-icon">首</span>
          <span>主页</span>
        </button>
        <button
          type="button"
          className={`sidebar-shortcut-btn${snapshot.currentView === 'skills' ? ' active' : ''}`}
          onClick={() => handleOpenPanel('skills')}
        >
          <span className="sidebar-shortcut-icon">技</span>
          <span>技能</span>
        </button>
        <button
          type="button"
          className={`sidebar-shortcut-btn${snapshot.currentView === 'scheduler' ? ' active' : ''}`}
          onClick={() => handleOpenPanel('scheduler')}
        >
          <span className="sidebar-shortcut-icon">自</span>
          <span>自动化</span>
        </button>
      </div>

      <div className="sidebar-divider"></div>

      <div className="sidebar-thread-groups custom-scrollbar">
        <div className="sidebar-section-row">
          <span className="sidebar-section-label">工作区与历史对话</span>
          <div className="sidebar-section-tools">
            <button type="button" className="sidebar-section-tool" onClick={handleOpenWorkspaceModal} aria-label="添加工作区">
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
                <span className="sidebar-workspace-folder">区</span>
                <span className="sidebar-workspace-name">
                  {getDisplayWorkspaceName(workspace.name)}
                  {workspace.is_default ? ' · 默认' : ''}
                </span>
                <span className="sidebar-workspace-count">{workspace.thread_count || threads.length || 0}</span>
                <CaretDownIcon className={`sidebar-workspace-chevron${expanded ? ' open' : ''}`} />
              </button>

              {expanded && threads.length > 0 ? (
                <div className="sidebar-group-threads sidebar-fade-scroll custom-scrollbar">
                  {threads.map((thread) => (
                    <div
                      key={thread.session_id}
                      className={`sidebar-thread-preview${snapshot.currentThreadId === thread.session_id ? ' active' : ''}`}
                      onContextMenu={(event) =>
                        handleThreadContextMenu(
                          event,
                          workspace.id,
                          getDisplayWorkspaceName(workspace.name),
                          thread.session_id,
                          thread.title || `${thread.session_id.slice(0, 24)}...`,
                          !!thread.pinned
                        )
                      }
                    >
                      <button
                        type="button"
                        className="sidebar-thread-preview-main"
                        onClick={() => handleOpenThread(workspace.id, thread.session_id)}
                      >
                        <span className="sidebar-thread-preview-copy">
                          <span className="sidebar-thread-preview-header">
                            <span className="sidebar-thread-preview-title">{thread.title || `${thread.session_id.slice(0, 24)}...`}</span>
                            {thread.pinned ? <span className="sidebar-thread-preview-badge">置顶</span> : null}
                          </span>
                          <span className="sidebar-thread-preview-meta">
                            {formatThreadTime(hostApp?.formatSidebarSessionTime, thread.updated_at)}
                          </span>
                        </span>
                        <MoreHorizontalIcon className="sidebar-thread-preview-more" />
                      </button>
                    </div>
                  ))}
                </div>
              ) : null}

              {expanded && threads.length === 0 ? <div className="sidebar-empty-caption">还没有历史对话</div> : null}
            </section>
          );
        })}

        {snapshot.workspaces.length === 0 ? <div className="sidebar-empty-state">还没有工作区，先添加一个开始使用。</div> : null}
      </div>

      <div className="sidebar-footer">
        <button type="button" className="sidebar-shortcut-btn sidebar-footer-btn" onClick={handleOpenSettings}>
          <span className="sidebar-shortcut-icon">设</span>
          <span>设置</span>
        </button>
      </div>

      {contextMenu ? (
        <div
          className="sidebar-thread-context-menu"
          style={{ top: contextMenu.y, left: contextMenu.x }}
          onMouseDown={(event) => event.stopPropagation()}
        >
          <div className="sidebar-thread-context-header">
            <div className="sidebar-thread-context-title">{contextMenu.title}</div>
            <div className="sidebar-thread-context-subtitle">{contextMenu.workspaceName}</div>
          </div>
          <div className="sidebar-thread-context-divider"></div>
          <button
            type="button"
            className="sidebar-thread-context-item"
            onClick={() => {
              void handleTogglePin(contextMenu.workspaceId, contextMenu.sessionId, contextMenu.pinned);
              setContextMenu(null);
            }}
          >
            <span className="sidebar-thread-context-item-main">
              <span className={`sidebar-thread-context-icon ${contextMenu.pinned ? 'is-active' : ''}`}>↑</span>
              <span className="sidebar-thread-context-label">{contextMenu.pinned ? '取消置顶' : '置顶'}</span>
            </span>
            <span className="sidebar-thread-context-hint">{contextMenu.pinned ? '已固定' : '固定到顶部'}</span>
          </button>
          <button type="button" className="sidebar-thread-context-item" onClick={handleStartRename}>
            <span className="sidebar-thread-context-item-main">
              <span className="sidebar-thread-context-icon">✎</span>
              <span className="sidebar-thread-context-label">重命名</span>
            </span>
            <span className="sidebar-thread-context-hint">编辑标题</span>
          </button>
          <div className="sidebar-thread-context-divider"></div>
          <button
            type="button"
            className="sidebar-thread-context-item danger"
            onClick={() => {
              void handleDeleteThread(contextMenu.workspaceId, contextMenu.sessionId);
              setContextMenu(null);
            }}
          >
            <span className="sidebar-thread-context-item-main">
              <span className="sidebar-thread-context-icon danger">×</span>
              <span className="sidebar-thread-context-label">删除</span>
            </span>
            <span className="sidebar-thread-context-hint">归档到历史</span>
          </button>
        </div>
      ) : null}

      {renameDialog ? (
        <div className="sidebar-thread-rename-backdrop" onMouseDown={() => setRenameDialog(null)}>
          <div className="sidebar-thread-rename-dialog" onMouseDown={(event) => event.stopPropagation()}>
            <div className="sidebar-thread-rename-kicker">历史聊天</div>
            <h3>重命名对话</h3>
            <form onSubmit={handleSubmitRename}>
              <input
                type="text"
                className="sidebar-thread-rename-input"
                value={renameDraft}
                onChange={(event) => {
                  setRenameDraft(event.target.value);
                  if (renameError) setRenameError('');
                }}
                placeholder="输入新的对话名称"
                autoFocus
              />
              {renameError ? <div className="sidebar-thread-rename-error">{renameError}</div> : null}
              <div className="sidebar-thread-rename-actions">
                <button
                  type="button"
                  className="sidebar-thread-rename-btn ghost"
                  onClick={() => {
                    setRenameDialog(null);
                    setRenameDraft('');
                    setRenameError('');
                  }}
                >
                  取消
                </button>
                <button type="submit" className="sidebar-thread-rename-btn primary">
                  保存
                </button>
              </div>
            </form>
          </div>
        </div>
      ) : null}
    </aside>
  );
}

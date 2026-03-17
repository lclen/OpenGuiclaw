import { useEffect, useState } from 'react';
import { emitShellUpdate } from '../bridge/openGuiclaw';
import { useWorkspaceShellBridge } from '../hooks/useWorkspaceShellBridge';

export function WorkspaceCreateModal() {
  const { hostApp, snapshot } = useWorkspaceShellBridge();
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!snapshot.showNewWorkspaceModal) return undefined;

    const handleKeydown = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return;
      hostApp?.closeNewWorkspaceModal?.();
      emitShellUpdate();
    };

    window.addEventListener('keydown', handleKeydown);
    return () => window.removeEventListener('keydown', handleKeydown);
  }, [hostApp, snapshot.showNewWorkspaceModal]);

  async function handlePickPath() {
    await hostApp?.pickWorkspacePath?.();
    emitShellUpdate();
  }

  async function handleCreate() {
    if (!hostApp || submitting) return;
    setSubmitting(true);
    try {
      await hostApp.createWorkspace?.(snapshot.newWorkspaceName, snapshot.newWorkspacePath);
      emitShellUpdate();
    } finally {
      setSubmitting(false);
    }
  }

  function handleClose() {
    hostApp?.closeNewWorkspaceModal?.();
    emitShellUpdate();
  }

  function handleNameChange(value: string) {
    hostApp?.setNewWorkspaceName?.(value);
    emitShellUpdate();
  }

  if (!snapshot.showNewWorkspaceModal) return null;

  return (
    <div className="workspace-modal-backdrop react-workspace-modal-backdrop" onClick={handleClose}>
      <div className="workspace-modal-card react-workspace-modal-card" onClick={(event) => event.stopPropagation()}>
        <div className="workspace-modal-header">
          <div>
            <div className="home-section-kicker">New Workspace</div>
            <h3>Add Workspace</h3>
            <p>Attach a local project folder and keep the workspace shell focused on that context.</p>
          </div>
          <button type="button" className="workspace-modal-close" onClick={handleClose} aria-label="Close">
            x
          </button>
        </div>

        <div className="workspace-modal-body">
          <label className="workspace-field">
            <span className="workspace-field-label">Workspace Name</span>
            <input
              type="text"
              value={snapshot.newWorkspaceName}
              className="workspace-text-input"
              placeholder="Example: openGuiclaw"
              onChange={(event) => handleNameChange(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter') {
                  event.preventDefault();
                  void handleCreate();
                }
              }}
            />
          </label>

          <div className="workspace-field">
            <span className="workspace-field-label">Project Folder</span>
            <div className="workspace-path-row">
              <button type="button" className="workspace-picker-button" onClick={handlePickPath}>
                Choose Folder
              </button>
              <div className={`workspace-path-preview${snapshot.newWorkspacePath ? ' has-value' : ''}`}>
                {snapshot.newWorkspacePath || 'No folder selected'}
              </div>
            </div>
          </div>

          {snapshot.newWorkspaceError ? <p className="workspace-error-text">{snapshot.newWorkspaceError}</p> : null}
        </div>

        <div className="workspace-modal-actions">
          <button type="button" className="workspace-secondary-button" onClick={handleClose}>
            Cancel
          </button>
          <button
            type="button"
            className="btn-primary"
            onClick={handleCreate}
            disabled={submitting || !snapshot.newWorkspaceName.trim() || !snapshot.newWorkspacePath.trim()}
          >
            {submitting ? 'Creating...' : 'Create Workspace'}
          </button>
        </div>
      </div>
    </div>
  );
}

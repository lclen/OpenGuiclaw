import { render, screen } from '@testing-library/react';
import { WorkspaceSidebar } from './WorkspaceSidebar';
import type { OpenGuiclawApp } from '../bridge/openGuiclaw';

const bridgeState: {
  app: OpenGuiclawApp | null;
  snapshot: any;
} = {
  app: null,
  snapshot: null
};

vi.mock('../bridge/openGuiclaw', async () => {
  const actual = await vi.importActual<typeof import('../bridge/openGuiclaw')>('../bridge/openGuiclaw');
  return {
    ...actual,
    dispatchShellAction: vi.fn(),
    emitShellUpdate: vi.fn()
  };
});

vi.mock('../hooks/useWorkspaceShellBridge', () => ({
  useWorkspaceShellBridge: () => ({
    hostApp: bridgeState.app,
    snapshot: bridgeState.snapshot,
    errorText: ''
  })
}));

describe('WorkspaceSidebar thread count display', () => {
  it('prefers cached thread count over stale workspace.thread_count', () => {
    bridgeState.app = null;
    bridgeState.snapshot = {
      workspaces: [
        {
          id: 'ws_1',
          name: 'Workspace One',
          thread_count: 5
        }
      ],
      homeData: null,
      activeWorkspaceId: 'ws_1',
      activeWorkspace: { id: 'ws_1', name: 'Workspace One', workspace_path: null },
      sidebarCollapsed: false,
      workspaceThreads: [],
      workspaceThreadMap: {
        ws_1: [
          { session_id: 'sess_1', title: 'Thread 1', updated_at: '2026-03-29T10:00:00Z' },
          { session_id: 'sess_2', title: 'Thread 2', updated_at: '2026-03-29T11:00:00Z' }
        ]
      },
      expandedWorkspaceIds: { ws_1: false },
      workspaceLoading: false,
      currentView: 'home',
      currentThreadId: null,
      showNewWorkspaceModal: false,
      showWorkspaceSwitcher: false,
      showSettings: false,
      settingsTab: 'models',
      previousViewBeforeSettings: 'home',
      newWorkspaceName: '',
      newWorkspacePath: '',
      newWorkspaceError: '',
      vrmSystemEnabled: false,
      showVrm: false,
      isReceiving: false
    };

    render(<WorkspaceSidebar />);

    expect(screen.getByText('2')).toBeTruthy();
    expect(screen.queryByText('5')).toBeNull();
  });
});

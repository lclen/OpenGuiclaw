import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { ArchivedPanel } from './ArchivedPanel';
import type { OpenGuiclawApp } from '../bridge/openGuiclaw';

const bridgeState: {
  app: OpenGuiclawApp | null;
  snapshot: {
    showSettings: boolean;
    settingsTab: string;
  };
} = {
  app: null,
  snapshot: {
    showSettings: true,
    settingsTab: 'archived'
  }
};

vi.mock('../bridge/openGuiclaw', async () => {
  const actual = await vi.importActual<typeof import('../bridge/openGuiclaw')>('../bridge/openGuiclaw');
  return {
    ...actual,
    getHostApp: () => bridgeState.app,
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

function jsonResponse(payload: unknown, status = 200) {
  return Promise.resolve(
    new Response(JSON.stringify(payload), {
      status,
      headers: {
        'Content-Type': 'application/json'
      }
    })
  );
}

function createHostApp(): OpenGuiclawApp {
  return {
    skills: [],
    schedulerTasks: [],
    messages: [],
    workspaces: [],
    homeData: null,
    inputText: '',
    stagedFiles: [],
    showCommandMenu: false,
    filteredCommands: [],
    commandSelectedIndex: 0,
    currentThreadId: null,
    loadWorkspaceThreads: vi.fn(async () => {}),
    loadWorkspaces: vi.fn(async () => {}),
    loadHome: vi.fn(async () => {})
  } as unknown as OpenGuiclawApp;
}

describe('ArchivedPanel refresh behavior', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    bridgeState.app = createHostApp();
    bridgeState.snapshot = {
      showSettings: true,
      settingsTab: 'archived'
    };
  });

  it('reloads archived threads with cleared filter after restoring filtered workspace', async () => {
    const fetchMock = vi.fn();
    let stage = 'initial';

    fetchMock.mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);

      if (url === '/api/workspaces' && (!init || !init.method)) {
        return jsonResponse(stage === 'initial' ? [] : [{ id: 'ws_other', name: 'Other Workspace' }]);
      }

      if (url === '/api/workspaces/archived' && (!init || !init.method)) {
        return jsonResponse(
          stage === 'initial'
            ? [
                { id: 'ws_restore', name: 'Restore Me', archived: true },
                { id: 'ws_other', name: 'Other Workspace', archived: true }
              ]
            : []
        );
      }

      if (url === '/api/workspaces/ws_restore/sessions?include_archived=true') {
        return jsonResponse(
          stage === 'initial'
            ? [{ session_id: 'sess_restore', title: '待恢复线程', archived: true, updated_at: '2026-03-29T10:00:00Z' }]
            : []
        );
      }

      if (url === '/api/workspaces/ws_other/sessions?include_archived=true') {
        return jsonResponse([
          { session_id: 'sess_other', title: '其他归档线程', archived: true, updated_at: '2026-03-29T09:00:00Z' }
        ]);
      }

      if (url === '/api/workspaces/ws_restore/unarchive' && init?.method === 'POST') {
        stage = 'after-restore';
        return jsonResponse({ status: 'ok', workspace_id: 'ws_restore' });
      }

      throw new Error(`Unhandled fetch: ${url} ${init?.method || 'GET'}`);
    });

    vi.stubGlobal('fetch', fetchMock);

    render(<ArchivedPanel />);

    await screen.findByText('待恢复线程');

    fireEvent.change(screen.getByRole('combobox'), { target: { value: 'ws_restore' } });
    await waitFor(() => expect(screen.getByText('待恢复线程')).toBeTruthy());

    fireEvent.click(screen.getAllByRole('button', { name: '恢复' })[0]);

    await waitFor(() => expect(screen.getByText('工作区已恢复')).toBeTruthy());
    await waitFor(() => expect(screen.getAllByText('其他归档线程').length).toBe(1));
    expect(screen.queryByText('待恢复线程')).toBeNull();
  });

  it('refreshes workspace thread cache after restoring archived thread', async () => {
    const hostApp = createHostApp();
    bridgeState.app = hostApp;

    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);

      if (url === '/api/workspaces') {
        return jsonResponse([{ id: 'ws_a', name: 'Workspace A' }]);
      }
      if (url === '/api/workspaces/archived') {
        return jsonResponse([]);
      }
      if (url === '/api/workspaces/ws_a/sessions?include_archived=true') {
        return jsonResponse([
          { session_id: 'sess_archived', title: '待恢复线程', archived: true, updated_at: '2026-03-29T11:00:00Z' }
        ]);
      }
      if (url === '/api/workspaces/ws_a/sessions/sess_archived/unarchive' && init?.method === 'POST') {
        return jsonResponse({ status: 'ok' });
      }

      throw new Error(`Unhandled fetch: ${url} ${init?.method || 'GET'}`);
    });

    vi.stubGlobal('fetch', fetchMock);

    render(<ArchivedPanel />);

    await screen.findByText('待恢复线程');

    fireEvent.click(screen.getByRole('button', { name: '恢复' }));

    await waitFor(() => expect(hostApp.loadWorkspaceThreads).toHaveBeenCalledWith('ws_a', true));
  });
});

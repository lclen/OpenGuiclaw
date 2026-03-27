import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { DiagnosticsPanel } from './DiagnosticsPanel';

const bridgeState = {
  snapshot: {
    workspaces: [],
    homeData: null,
    activeWorkspaceId: null,
    activeWorkspace: null,
    sidebarCollapsed: false,
    workspaceThreads: [],
    workspaceThreadMap: {},
    expandedWorkspaceIds: {},
    workspaceLoading: false,
    currentView: 'home',
    currentThreadId: null,
    showNewWorkspaceModal: false,
    showWorkspaceSwitcher: false,
    showSettings: true,
    settingsTab: 'diagnostics',
    previousViewBeforeSettings: 'home',
    newWorkspaceName: '',
    newWorkspacePath: '',
    newWorkspaceError: '',
    vrmSystemEnabled: false,
    showVrm: false,
    isReceiving: false
  }
};

vi.mock('../hooks/useWorkspaceShellBridge', () => ({
  useWorkspaceShellBridge: () => ({
    hostApp: null,
    snapshot: bridgeState.snapshot,
    errorText: ''
  })
}));

function createJsonResponse(payload: unknown) {
  return Promise.resolve(
    new Response(JSON.stringify(payload), {
      status: 200,
      headers: {
        'Content-Type': 'application/json'
      }
    })
  );
}

describe('DiagnosticsPanel runtime checks', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    const diagnosticsPayload = {
      system: { os: 'Windows', python_executable: 'python', app_dir: 'D:/openGuiclaw', frozen: false, pid: 1234 },
      restart: { supported: true, mode: 'reload', reason: null },
      network: { proxies: {}, connectivity: { status: 'ok', latency_ms: 12 } },
      dependencies: { fastapi: true, psutil: true },
      process_runtime: {
        current_pid: 1234,
        current_record: {
          pid: 1234,
          started_at: '2026-03-27T10:00:00',
          mode: 'reload',
          version: '1.0.0',
          executable: 'python.exe',
          is_frozen: false
        },
        run_records: [
          {
            record_id: 'openguiclaw-server-1234.json',
            pid: 1234,
            started_at: '2026-03-27T10:00:00',
            mode: 'reload',
            executable: 'python.exe',
            is_frozen: false,
            runtime_status: 'healthy_current',
            cleanup_allowed: false
          },
          {
            record_id: 'openguiclaw-server-2222.json',
            pid: 2222,
            started_at: '2026-03-27T09:50:00',
            mode: 'reload',
            executable: 'python.exe',
            is_frozen: false,
            runtime_status: 'stale_record',
            cleanup_allowed: true
          }
        ],
        running_processes: [
          {
            pid: 1234,
            status: 'healthy_current',
            name: 'python.exe',
            executable: 'python.exe',
            started_at: '2026-03-27T10:00:00',
            summary: '当前正在服务的后端进程',
            cleanup_allowed: false
          }
        ],
        conflicts: [
          {
            type: 'stale_record',
            pid: 2222,
            record_id: 'openguiclaw-server-2222.json',
            summary: '运行记录文件仍存在，但对应 PID 已不存在',
            cleanup_allowed: true
          }
        ],
        cleanup_supported: true
      },
      timestamp: 1710000000
    };

    vi.stubGlobal(
      'fetch',
      vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);

        if (url === '/api/diagnostics') {
          return createJsonResponse(diagnosticsPayload);
        }

        if (url === '/api/health') {
          return createJsonResponse({
            status: 'ok',
            pid: 1234,
            version: '1.0.0',
            started_at: '2026-03-27T10:00:00',
            uptime_seconds: 90,
            restart_mode: 'reload'
          });
        }

        if (url === '/api/endpoints') {
          return createJsonResponse({
            endpoints: [
              { id: 'primary', name: 'Primary', model: 'gpt-4.1', base_url: 'https://example.invalid/v1', api_key_masked: 'sk***12' },
              { id: 'secondary', name: 'Secondary', model: 'gpt-4.1-mini', base_url: 'https://second.invalid/v1', api_key_masked: 'sk***34' }
            ],
            active_id: 'primary'
          });
        }

        if (url === '/api/config/model') {
          return createJsonResponse({
            config: {
              api: { configured: true },
              vision: { configured: false },
              image_analyzer: { configured: false },
              embedding: { configured: false },
              autogui: { configured: false }
            }
          });
        }

        if (url === '/api/im/bots') {
          return createJsonResponse({
            bots: [
              {
                id: 'dingtalk',
                name: 'DingTalk Bot',
                platform: 'dingtalk',
                enabled: true,
                credentials: { client_id: 'id', client_secret: 'secret' }
              }
            ]
          });
        }

        if (url === '/api/im/channels') {
          return createJsonResponse({
            channels: [
              {
                channel_name: 'dingtalk@@dingtalk',
                status: 'online',
                session_count: 2,
                last_active: '2026-03-27T10:05:00'
              }
            ]
          });
        }

        if (url === '/api/health/check' && init?.method === 'POST') {
          const body = JSON.parse(String(init.body || '{}'));
          if (body.endpoint_name === 'chat:primary') {
            return createJsonResponse({
              results: [
                {
                  name: 'chat:primary',
                  status: 'unhealthy',
                  error: 'API Key 无效或已过期',
                  error_code: 'auth_failed',
                  hint: '请检查 API Key 是否正确，或确认服务端是否要求鉴权',
                  last_checked_at: '2026-03-27T10:06:00'
                }
              ]
            });
          }
          if (body.endpoint_name === 'chat:secondary') {
            return createJsonResponse({
              results: [
                {
                  name: 'chat:secondary',
                  status: 'healthy',
                  latency_ms: 42,
                  last_checked_at: '2026-03-27T10:07:00'
                }
              ]
            });
          }
          return createJsonResponse({ results: [] });
        }

        if (url === '/api/diagnostics/process/cleanup' && init?.method === 'POST') {
          diagnosticsPayload.process_runtime.run_records = [
            {
              record_id: 'openguiclaw-server-1234.json',
              pid: 1234,
              started_at: '2026-03-27T10:00:00',
              mode: 'reload',
              executable: 'python.exe',
              is_frozen: false,
              runtime_status: 'healthy_current',
              cleanup_allowed: false
            }
          ];
          diagnosticsPayload.process_runtime.conflicts = [];
          return createJsonResponse({
            results: [{ pid: 2222, action: 'remove_record', status: 'cleaned' }],
            remaining_conflicts: []
          });
        }

        throw new Error(`Unhandled fetch: ${url}`);
      })
    );
  });

  it('loads overview without auto-triggering endpoint health checks', async () => {
    render(<DiagnosticsPanel />);

    await waitFor(() => expect(screen.getByText('运行时自检中心')).toBeTruthy());
    await waitFor(() => expect(screen.getByText('Primary')).toBeTruthy());
    await waitFor(() => expect(screen.getByText('进程残留与冲突')).toBeTruthy());

    const calls = (globalThis.fetch as unknown as ReturnType<typeof vi.fn>).mock.calls.map(([url]) => String(url));
    expect(calls).toContain('/api/diagnostics');
    expect(calls).toContain('/api/health');
    expect(calls).not.toContain('/api/health/check');
    expect(screen.getByText('记录：2')).toBeTruthy();
    expect(screen.getAllByText('当前服务').length).toBeGreaterThan(0);
    expect(screen.getByText('Cleanup')).toBeTruthy();
  });

  it('merges single endpoint check results without clearing previous ones', async () => {
    render(<DiagnosticsPanel />);

    await waitFor(() => expect(screen.getByText('Primary')).toBeTruthy());

    fireEvent.click(screen.getAllByRole('button', { name: 'Check' })[0]);

    await waitFor(() => expect(screen.getByText('错误类别：auth_failed')).toBeTruthy());
    expect(screen.getByText('请检查 API Key 是否正确，或确认服务端是否要求鉴权')).toBeTruthy();

    fireEvent.click(screen.getAllByRole('button', { name: 'Check' })[1]);

    await waitFor(() => expect(screen.getByText('42ms')).toBeTruthy());
    expect(screen.getByText('错误类别：auth_failed')).toBeTruthy();
  });

  it('cleans a process conflict and refreshes only diagnostics process state', async () => {
    render(<DiagnosticsPanel />);

    await waitFor(() => expect(screen.getByText('Cleanup')).toBeTruthy());

    fireEvent.click(screen.getByRole('button', { name: 'Cleanup' }));

    await waitFor(() => expect(screen.getByText('没有发现进程冲突或残留运行记录。')).toBeTruthy());
    expect(screen.queryByText('运行记录文件仍存在，但对应 PID 已不存在')).toBeNull();
  });
});

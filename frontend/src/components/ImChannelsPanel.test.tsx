import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { ImChannelsPanel } from './ImChannelsPanel';

const bridgeState = {
  snapshot: {
    currentView: 'im'
  }
};

vi.mock('../hooks/useWorkspaceShellBridge', () => ({
  useWorkspaceShellBridge: () => ({
    hostApp: null,
    snapshot: bridgeState.snapshot,
    errorText: ''
  })
}));

vi.mock('../bridge/openGuiclaw', async () => {
  const actual = await vi.importActual<typeof import('../bridge/openGuiclaw')>('../bridge/openGuiclaw');
  return {
    ...actual,
    dispatchShellAction: vi.fn()
  };
});

function jsonResponse(payload: unknown) {
  return Promise.resolve(createJsonResponse(payload));
}

function createJsonResponse(payload: unknown) {
  return new Response(JSON.stringify(payload), {
    status: 200,
    headers: {
      'Content-Type': 'application/json'
    }
  });
}

describe('ImChannelsPanel', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    bridgeState.snapshot.currentView = 'im';
    window.marked = {
      parse: (markdown: string) => `<p>${markdown}</p>`
    };
  });

  it('loads overview once and switching sessions only fetches session messages', async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);

      if (url === '/api/im/channels') {
        return jsonResponse({
          channels: [
            {
              id: 'telegram@@bot',
              channel_name: 'telegram@@bot',
              platform: 'telegram',
              name: 'Telegram Bot',
              display_name: 'Telegram',
              status: 'online',
              enabled: true,
              session_count: 2,
              last_active: '2026-03-29 10:00:00'
            }
          ]
        });
      }

      if (url === '/api/im/sessions?channel_name=telegram%40%40bot') {
        return jsonResponse({
          sessions: [
            {
              id: 'sess-1',
              session_id: 'sess-1',
              channel: 'telegram@@bot',
              channel_name: 'telegram@@bot',
              platform: 'telegram',
              chat_id: 'alice',
              display_name: 'Alice',
              last_message: 'hello',
              message_count: 3,
              updated_at: '2026-03-29 10:01:00'
            },
            {
              id: 'sess-2',
              session_id: 'sess-2',
              channel: 'telegram@@bot',
              channel_name: 'telegram@@bot',
              platform: 'telegram',
              chat_id: 'bob',
              display_name: 'Bob',
              last_message: 'second',
              message_count: 4,
              updated_at: '2026-03-29 10:02:00'
            }
          ]
        });
      }

      if (url === '/api/sessions/sess-1') {
        return jsonResponse({
          session_id: 'sess-1',
          messages: [{ role: 'user', content: 'hello', timestamp: '2026-03-29 10:01:00' }]
        });
      }

      if (url === '/api/sessions/sess-2') {
        return jsonResponse({
          session_id: 'sess-2',
          messages: [{ role: 'user', content: 'second', timestamp: '2026-03-29 10:02:00' }]
        });
      }

      throw new Error(`Unhandled fetch: ${url}`);
    });

    vi.stubGlobal('fetch', fetchMock);

    render(<ImChannelsPanel />);

    await screen.findByRole('button', { name: /Alice/ });
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith('/api/sessions/sess-1'));

    expect(fetchMock).toHaveBeenCalledWith('/api/im/channels');
    expect(fetchMock).toHaveBeenCalledWith('/api/im/sessions?channel_name=telegram%40%40bot');
    expect(fetchMock).toHaveBeenCalledWith('/api/sessions/sess-1');

    fireEvent.click(screen.getByRole('button', { name: /Bob/ }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith('/api/sessions/sess-2'));

    const urls = fetchMock.mock.calls.map((call) => String(call[0]));
    expect(urls.filter((url) => url === '/api/im/channels')).toHaveLength(1);
    expect(urls.filter((url) => url === '/api/im/sessions?channel_name=telegram%40%40bot')).toHaveLength(1);
    expect(urls.filter((url) => url === '/api/sessions/sess-1')).toHaveLength(1);
    expect(urls.filter((url) => url === '/api/sessions/sess-2')).toHaveLength(1);
  });

  it('ignores stale session lists when switching channels quickly', async () => {
    let resolveSlowSessions!: (value: Response) => void;
    const slowSessions = new Promise<Response>((resolve) => {
      resolveSlowSessions = resolve;
    });

    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);

      if (url === '/api/im/channels') {
        return jsonResponse({
          channels: [
            {
              id: 'alpha',
              channel_name: 'alpha',
              platform: 'telegram',
              display_name: 'Alpha',
              status: 'online',
              enabled: true,
              session_count: 1,
              last_active: '2026-03-29 10:00:00'
            },
            {
              id: 'beta',
              channel_name: 'beta',
              platform: 'feishu',
              display_name: 'Beta',
              status: 'online',
              enabled: true,
              session_count: 1,
              last_active: '2026-03-29 10:01:00'
            }
          ]
        });
      }

      if (url === '/api/im/sessions?channel_name=alpha') {
        return slowSessions;
      }

      if (url === '/api/im/sessions?channel_name=beta') {
        return jsonResponse({
          sessions: [
            {
              id: 'beta-1',
              session_id: 'beta-1',
              channel: 'beta',
              channel_name: 'beta',
              platform: 'feishu',
              chat_id: 'beta-user',
              display_name: 'Beta User',
              last_message: 'from beta',
              message_count: 2,
              updated_at: '2026-03-29 10:03:00'
            }
          ]
        });
      }

      if (url === '/api/sessions/beta-1') {
        return jsonResponse({
          session_id: 'beta-1',
          messages: [{ role: 'user', content: 'from beta', timestamp: '2026-03-29 10:03:00' }]
        });
      }

      if (url === '/api/sessions/alpha-1') {
        return jsonResponse({
          session_id: 'alpha-1',
          messages: [{ role: 'user', content: 'from alpha', timestamp: '2026-03-29 10:02:00' }]
        });
      }

      throw new Error(`Unhandled fetch: ${url}`);
    });

    vi.stubGlobal('fetch', fetchMock);

    render(<ImChannelsPanel />);

    fireEvent.click(await screen.findByRole('button', { name: /Beta/ }));

    await screen.findByRole('button', { name: /Beta User/ });
    resolveSlowSessions(
      createJsonResponse({
        sessions: [
          {
            id: 'alpha-1',
            session_id: 'alpha-1',
            channel: 'alpha',
            channel_name: 'alpha',
            platform: 'telegram',
            chat_id: 'alpha-user',
            display_name: 'Alpha User',
            last_message: 'from alpha',
            message_count: 1,
            updated_at: '2026-03-29 10:02:00'
          }
        ]
      })
    );

    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith('/api/sessions/beta-1'));

    const urls = fetchMock.mock.calls.map((call) => String(call[0]));
    expect(urls.filter((url) => url === '/api/im/sessions?channel_name=alpha')).toHaveLength(1);
    expect(urls.filter((url) => url === '/api/im/sessions?channel_name=beta')).toHaveLength(1);
    expect(urls.filter((url) => url === '/api/sessions/alpha-1')).toHaveLength(0);
    expect(screen.queryByRole('button', { name: /Alpha User/ })).toBeNull();
  });
});

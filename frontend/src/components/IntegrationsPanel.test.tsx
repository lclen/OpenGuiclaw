import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { IntegrationsPanel } from './IntegrationsPanel';

const bridgeState = {
  snapshot: {
    showSettings: true,
    settingsTab: 'integrations'
  }
};

vi.mock('../hooks/useWorkspaceShellBridge', () => ({
  useWorkspaceShellBridge: () => ({
    hostApp: null,
    snapshot: bridgeState.snapshot,
    errorText: ''
  })
}));

function jsonResponse(payload: unknown) {
  return Promise.resolve(
    new Response(JSON.stringify(payload), {
      status: 200,
      headers: { 'Content-Type': 'application/json' }
    })
  );
}

describe('IntegrationsPanel selfcheck subscriptions', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('subscribes a session from settings panel', async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const method = init?.method || 'GET';

      if (url === '/api/im/bots') {
        return jsonResponse({ bots: [] });
      }
      if (url === '/api/im/sessions') {
        return jsonResponse({
          sessions: [
            {
              id: 'sess-1',
              session_id: 'sess-1',
              channel: 'dingtalk@@ops-bot',
              channel_name: 'dingtalk@@ops-bot',
              platform: 'dingtalk',
              bot_id: 'ops-bot',
              chat_id: 'chat-001',
              chat_type: 'group',
              chat_name: '运维群',
              display_name: '运维群',
              updated_at: '2026-03-29 10:00:00',
              selfcheck_subscribed: false
            }
          ]
        });
      }
      if (url === '/api/im/selfcheck-subscriptions' && method === 'GET') {
        return jsonResponse({ subscriptions: [] });
      }
      if (url === '/api/im/selfcheck-subscriptions' && method === 'POST') {
        return jsonResponse({
          status: 'ok',
          subscriptions: [
            {
              session_id: 'sess-1',
              channel_name: 'dingtalk@@ops-bot',
              chat_id: 'chat-001',
              enabled: true
            }
          ]
        });
      }

      throw new Error(`Unhandled fetch: ${method} ${url}`);
    });

    vi.stubGlobal('fetch', fetchMock);

    render(<IntegrationsPanel />);

    await screen.findByText('每日自检订阅');
    const subscribeButton = await screen.findByRole('button', { name: '订阅每日自检' });
    fireEvent.click(subscribeButton);

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        '/api/im/selfcheck-subscriptions',
        expect.objectContaining({
          method: 'POST',
          headers: { 'Content-Type': 'application/json' }
        })
      )
    );
  });
});

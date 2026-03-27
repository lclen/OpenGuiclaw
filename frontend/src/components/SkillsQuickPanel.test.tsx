import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { SkillsQuickPanel } from './SkillsQuickPanel';
import type { OpenGuiclawApp } from '../bridge/openGuiclaw';

const bridgeState: {
  app: OpenGuiclawApp | null;
} = {
  app: null
};

vi.mock('../bridge/openGuiclaw', async () => {
  const actual = await vi.importActual<typeof import('../bridge/openGuiclaw')>('../bridge/openGuiclaw');
  return {
    ...actual,
    getHostApp: () => bridgeState.app,
    waitForHostApp: async () => {
      if (!bridgeState.app) {
        throw new Error('host app missing');
      }
      return bridgeState.app;
    }
  };
});

function createHostApp(installResult: boolean): OpenGuiclawApp {
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
    skillMarketplace: [],
    skillMarketLoading: false,
    skillMarketSearch: 'agent',
    skillInstallingId: null,
    skillInstallMsg: installResult ? { type: 'success', text: '✓ 技能安装成功，已立即生效' } : { type: 'error', text: '安装失败' },
    loadSkills: vi.fn(async () => {}),
    reloadSkills: vi.fn(async () => {}),
    toggleSkill: vi.fn(async () => {}),
    loadSchedulerTasks: vi.fn(async () => {}),
    toggleSchedulerTask: vi.fn(async () => {}),
    deleteSchedulerTask: vi.fn(async () => {}),
    triggerSchedulerTask: vi.fn(async () => {}),
    openSchedulerForm: vi.fn(),
    editSchedulerTask: vi.fn(),
    submitAskUserChoice: vi.fn(async () => {}),
    installSkillFromUrl: vi.fn(async () => installResult)
  };
}

describe('SkillsQuickPanel manual URL install', () => {
  beforeEach(() => {
    bridgeState.app = null;
  });

  it('keeps URL input when installSkillFromUrl returns false', async () => {
    const hostApp = createHostApp(false);
    bridgeState.app = hostApp;

    render(<SkillsQuickPanel />);

    await waitFor(() => expect(hostApp.loadSkills).toHaveBeenCalled());

    fireEvent.click(screen.getByRole('button', { name: '技能市场' }));

    const input = screen.getByPlaceholderText('粘贴 GitHub / URL 安装源') as HTMLInputElement;
    fireEvent.change(input, { target: { value: 'https://github.com/openai/skills/tree/main/skills/.curated/frontend-skill' } });

    fireEvent.click(screen.getByRole('button', { name: '立即安装' }));

    await waitFor(() => expect(hostApp.installSkillFromUrl).toHaveBeenCalled());
    expect(input.value).toBe('https://github.com/openai/skills/tree/main/skills/.curated/frontend-skill');
    expect(screen.getByText('安装失败')).toBeTruthy();
  });

  it('clears URL input when installSkillFromUrl returns true', async () => {
    const hostApp = createHostApp(true);
    bridgeState.app = hostApp;

    render(<SkillsQuickPanel />);

    await waitFor(() => expect(hostApp.loadSkills).toHaveBeenCalled());

    fireEvent.click(screen.getByRole('button', { name: '技能市场' }));

    const input = screen.getByPlaceholderText('粘贴 GitHub / URL 安装源') as HTMLInputElement;
    fireEvent.change(input, { target: { value: 'https://github.com/openai/skills/tree/main/skills/.curated/frontend-skill' } });
    fireEvent.click(screen.getByRole('button', { name: '立即安装' }));

    await waitFor(() => expect(hostApp.installSkillFromUrl).toHaveBeenCalled());
    await waitFor(() => expect(input.value).toBe(''));
    expect(screen.getByText('✓ 技能安装成功，已立即生效')).toBeTruthy();
  });
});

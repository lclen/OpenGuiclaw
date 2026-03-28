import { getTabMeta } from '../constants/settingsTabs';

export type SkillConfigField = {
  key: string;
  label: string;
  type: 'text' | 'secret' | 'select' | 'bool';
  default?: string;
  options?: string[];
};

export type SkillRecord = {
  name: string;
  description: string;
  category?: string;
  registry_category?: string;
  type?: 'system_plugin' | 'builtin_skill' | 'user_skill' | string;
  enabled: boolean;
  locked?: boolean;
  source?: string;
  tools?: string[];
  ui_config?: SkillConfigField[];
  config_values?: Record<string, unknown>;
};

export type SkillMarketplaceRecord = {
  id?: string;
  name: string;
  description: string;
  author?: string;
  url?: string;
  git_url?: string;
  version?: string;
  category?: string;
  installs?: number;
  stars?: number;
  tags?: string[];
  tools?: string[];
  installed?: boolean;
};

export type SkillInstallMessage = {
  type: 'success' | 'error' | string;
  text: string;
};

export type SchedulerTask = {
  id: string;
  name: string;
  description?: string;
  enabled: boolean;
  status?: string;
  task_type?: 'task' | 'reminder' | 'system' | string;
  prompt?: string;
  reminder_message?: string;
  trigger_type?: string;
  trigger_config?: Record<string, unknown>;
  last_run?: string | null;
  next_run?: string | null;
  deletable?: boolean;
  delivery_targets?: Array<{
    kind: string;
    workspace_id?: string | null;
    session_id?: string | null;
    channel?: string | null;
    chat_id?: string | null;
  }>;
  target_workspace_id?: string | null;
  target_session_id?: string | null;
  target_kind?: string | null;
  target_channel?: string | null;
  target_chat_id?: string | null;
  last_execution?: SchedulerExecution | null;
};

export type SchedulerExecution = {
  id: string;
  task_id: string;
  started_at?: string | null;
  finished_at?: string | null;
  status?: string;
  result_summary?: string | null;
  error?: string | null;
  trigger_source?: string | null;
  delivery_targets?: Array<{
    kind: string;
    workspace_id?: string | null;
    session_id?: string | null;
    channel?: string | null;
    chat_id?: string | null;
  }>;
  target_workspace_id?: string | null;
  target_session_id?: string | null;
  target_kind?: string | null;
  target_channel?: string | null;
  target_chat_id?: string | null;
};

export type ChatAskOption = {
  id: string;
  label: string;
};

export type ComposerCommand = {
  command: string;
  desc?: string;
  icon?: string;
  action?: string;
};

export type ChatBlock = {
  id?: string;
  type: 'text' | 'tool' | 'status_done' | 'ask_user' | string;
  content?: string;
  html?: string;
  name?: string;
  paramsStr?: string;
  resultStr?: string;
  status?: 'running' | 'done' | string;
  _collapsed?: boolean;
  question?: string;
  options?: ChatAskOption[];
  answered?: boolean;
};

export type ChatMessage = {
  id: string;
  role: 'user' | 'assistant' | 'visual_log' | string;
  content?: string;
  html?: string;
  thinkingHtml?: string;
  _thinkingRaw?: string;
  _thinkCollapsed?: boolean;
  _isThinking?: boolean;
  _streaming?: boolean;
  blocks?: ChatBlock[];
};

export type WorkspaceThread = {
  session_id: string;
  title?: string | null;
  pinned?: boolean;
  updated_at?: string | null;
};

export type Workspace = {
  id: string;
  name: string;
  workspace_path?: string | null;
  thread_count?: number;
  is_default?: boolean;
};

export type RecentThread = {
  session_id: string;
  title?: string | null;
  updated_at?: string | null;
  pinned?: boolean;
};

export type WorkspaceSummary = {
  id: string;
  name: string;
  workspace_path?: string | null;
  thread_count?: number;
  is_default?: boolean;
  recent_sessions?: RecentThread[];
};

export type HomeData = {
  workspaces?: WorkspaceSummary[];
};

export type WorkspaceThreadMap = Record<string, WorkspaceThread[]>;

export type ExpandedWorkspaceMap = Record<string, boolean>;

export type WorkspaceShellSnapshot = {
  workspaces: Workspace[];
  homeData: HomeData | null;
  activeWorkspaceId: string | null;
  activeWorkspace: { id?: string; name?: string; workspace_path?: string | null } | null;
  sidebarCollapsed: boolean;
  workspaceThreads: WorkspaceThread[];
  workspaceThreadMap: WorkspaceThreadMap;
  expandedWorkspaceIds: ExpandedWorkspaceMap;
  workspaceLoading: boolean;
  currentView: string;
  currentThreadId: string | null;
  showNewWorkspaceModal: boolean;
  showWorkspaceSwitcher: boolean;
  showSettings: boolean;
  settingsTab: string;
  previousViewBeforeSettings?: string;
  newWorkspaceName: string;
  newWorkspacePath: string;
  newWorkspaceError: string;
  vrmSystemEnabled: boolean;
  showVrm: boolean;
  isReceiving: boolean;
};

export type ShellAction =
  | { type: 'openSettings'; tab?: string }
  | { type: 'closeSettings' }
  | { type: 'switchSettingsTab'; tab: string }
  | { type: 'openWorkspaceSwitcher' }
  | { type: 'closeWorkspaceSwitcher' }
  | { type: 'toggleSidebar' }
  | { type: 'setSidebarCollapsed'; collapsed: boolean }
  | { type: 'navigateView'; view: string };

export type OpenGuiclawApp = {
  skills: SkillRecord[];
  schedulerTasks: SchedulerTask[];
  schedulerExecutions?: SchedulerExecution[];
  messages: ChatMessage[];
  workspaces: Workspace[];
  homeData: HomeData | null;
  inputText: string;
  stagedFiles: File[];
  showCommandMenu: boolean;
  filteredCommands: ComposerCommand[];
  commandSelectedIndex: number;
  currentThreadId: string | null;
  threadLoading?: boolean;
  currentController?: unknown;
  isReceiving?: boolean;
  activeWorkspaceId?: string | null;
  activeWorkspace?: { id?: string; name?: string; workspace_path?: string | null } | null;
  workspaceThreads?: WorkspaceThread[];
  workspaceThreadMap?: WorkspaceThreadMap;
  expandedWorkspaceIds?: ExpandedWorkspaceMap;
  workspaceLoading?: boolean;
  currentView?: string;
  showNewWorkspaceModal?: boolean;
  showWorkspaceSwitcher?: boolean;
  showSettings?: boolean;
  settingsTab?: string;
  configTab?: string;
  previousViewBeforeSettings?: string;
  vrmSystemEnabled?: boolean;
  showVrm?: boolean;
  config?: {
    browser_choice?: string;
    proactive?: Record<string, unknown>;
    journal?: Record<string, unknown>;
    channels?: Record<string, unknown>;
  };
  activePanel?: string;
  sidebarCollapsed?: boolean;
  newWorkspaceName?: string;
  newWorkspacePath?: string;
  newWorkspaceError?: string;
  contextDisplay?: string;
  getCurrentThread?: () => WorkspaceThread | null;
  getSidebarWorkspaceThreads?: (wsId: string) => WorkspaceThread[];
  isWorkspaceExpanded?: (wsId: string) => boolean;
  formatSidebarSessionTime?: (value?: string | null) => string;
  handleInput?: (event?: Event) => void;
  navigateCommand?: (dir: number, event?: KeyboardEvent) => void;
  handlePaste?: (event: ClipboardEvent) => void;
  handleDrop?: (event: DragEvent) => Promise<void> | void;
  handleFileSelect?: (event: { target: HTMLInputElement }) => void;
  removeStagedFile?: (index: number) => void;
  selectCommand?: (command: ComposerCommand) => void;
  sendMessage?: (isProactive?: boolean) => Promise<void> | void;
  abortReceiving?: () => void;
  newSession?: () => Promise<void> | void;
  createThread?: (wsId: string) => Promise<void>;
  loadThread?: (wsId: string, sessionId: string) => Promise<void>;
  archiveThread?: (wsId: string, sessionId: string) => Promise<void>;
  deleteThread?: (wsId: string, sessionId: string) => Promise<void>;
  renameThread?: (wsId: string, sessionId: string, title: string) => Promise<void>;
  toggleThreadPin?: (wsId: string, sessionId: string, pinned: boolean) => Promise<void>;
  loadHome?: () => Promise<void>;
  loadWorkspaces?: () => Promise<void>;
  loadWorkspaceThreads?: (wsId: string, force?: boolean) => Promise<void>;
  switchWorkspace?: (wsId: string, silent?: boolean) => Promise<void>;
  focusWorkspaceHome?: (wsId: string) => Promise<void>;
  toggleWorkspaceGroup?: (wsId: string) => Promise<void>;
  openSidebarThread?: (wsId: string, sessionId: string) => Promise<void>;
  openSidebarPanel?: (view: string) => Promise<void> | void;
  switchPanel?: (panel: string) => Promise<void> | void;
  toggleVrmSystem?: (nextValue?: boolean) => void;
  toggleVrm?: () => void;
  openNewWorkspaceModal?: () => void;
  pickWorkspacePath?: () => Promise<void>;
  createWorkspace?: (name?: string, path?: string) => Promise<void>;
  archiveWorkspace?: (wsId: string) => Promise<void>;
  setNewWorkspaceName?: (value: string) => void;
  setNewWorkspacePath?: (value: string) => void;
  closeNewWorkspaceModal?: () => void;
  loadSkills: () => Promise<void>;
  reloadSkills: () => Promise<void>;
  toggleSkill: (name: string, enabled: boolean) => Promise<void>;
  uninstallSkill?: (name: string) => Promise<void>;
  searchSkillMarketplace?: (query: string) => Promise<void>;
  installSkillFromUrl?: (url: string, skillId?: string | null) => Promise<boolean>;
  skillMarketplace?: SkillMarketplaceRecord[];
  skillMarketLoading?: boolean;
  skillMarketSearch?: string;
  skillInstallingId?: string | null;
  skillInstallMsg?: SkillInstallMessage | null;
  loadSchedulerTasks: () => Promise<void>;
  loadSchedulerExecutions?: () => Promise<void>;
  refreshSchedulerData?: () => Promise<void>;
  toggleSchedulerTask: (taskId: string, enabled: boolean) => Promise<void>;
  triggerSchedulerTask: (taskId: string) => Promise<void>;
  deleteSchedulerTask: (taskId: string) => Promise<void>;
  openSchedulerForm: () => void;
  editSchedulerTask: (task: SchedulerTask) => void;
  submitAskUserChoice: (msg: ChatMessage, block: ChatBlock, opt: ChatAskOption) => Promise<void>;
  getTopbarTitle?: () => string;
  getTopbarKicker?: () => string;
};

declare global {
  interface Window {
    __openGuiclawApp?: OpenGuiclawApp;
  }
}

export function getHostApp(): OpenGuiclawApp | null {
  return window.__openGuiclawApp ?? null;
}

export function dispatchShellAction(action: ShellAction): void {
  const app = getHostApp();
  if (!app) return;

  switch (action.type) {
    case 'openSettings':
      if (app.currentView !== 'settings') {
        app.previousViewBeforeSettings = app.currentView || 'home';
      }
      app.showSettings = true;
      app.currentView = 'settings';
      if (action.tab && 'settingsTab' in app) {
        (app as OpenGuiclawApp & { settingsTab: string }).settingsTab = action.tab;
        const tabMeta = getTabMeta(action.tab);
        const cfgTab = tabMeta.cfgTab;
        if (cfgTab) {
          app.activePanel = 'config';
          app.configTab = cfgTab;
          window.dispatchEvent(new CustomEvent('set-cfg-tab', { detail: cfgTab }));
        } else if (tabMeta.panel) {
          app.activePanel = tabMeta.panel;
          void app.switchPanel?.(tabMeta.panel);
        }
      }
      break;
    case 'closeSettings':
      app.showSettings = false;
      app.currentView = app.previousViewBeforeSettings || 'home';
      break;
    case 'switchSettingsTab': {
      const appWithTab = app as OpenGuiclawApp & { settingsTab?: string };
      appWithTab.settingsTab = action.tab;
      const tabMeta = getTabMeta(action.tab);
      const cfgTab = tabMeta.cfgTab;
      if (cfgTab) {
        app.activePanel = 'config';
        app.configTab = cfgTab;
        window.dispatchEvent(new CustomEvent('set-cfg-tab', { detail: cfgTab }));
      } else if (tabMeta.panel) {
        app.activePanel = tabMeta.panel;
        void app.switchPanel?.(tabMeta.panel);
      }
      break;
    }
    case 'openWorkspaceSwitcher':
      app.showWorkspaceSwitcher = true;
      break;
    case 'closeWorkspaceSwitcher':
      app.showWorkspaceSwitcher = false;
      break;
    case 'toggleSidebar':
      app.sidebarCollapsed = !app.sidebarCollapsed;
      break;
    case 'setSidebarCollapsed':
      app.sidebarCollapsed = action.collapsed;
      break;
    case 'navigateView':
      app.showSettings = false;
      app.openSidebarPanel?.(action.view);
      break;
  }

  emitShellUpdate();
}

export function emitShellUpdate() {
  window.dispatchEvent(new CustomEvent('openguiclaw:shell-updated'));
}

export function waitForHostApp(timeoutMs = 8000): Promise<OpenGuiclawApp> {
  const existing = getHostApp();
  if (existing) return Promise.resolve(existing);

  return new Promise((resolve, reject) => {
    let settled = false;
    const timer = window.setTimeout(() => {
      if (settled) return;
      settled = true;
      window.removeEventListener('openguiclaw:app-ready', onReady as EventListener);
      reject(new Error('OpenGuiclaw host app bridge timed out'));
    }, timeoutMs);

    const onReady = () => {
      const app = getHostApp();
      if (!app || settled) return;
      settled = true;
      window.clearTimeout(timer);
      window.removeEventListener('openguiclaw:app-ready', onReady as EventListener);
      resolve(app);
    };

    window.addEventListener('openguiclaw:app-ready', onReady as EventListener, { once: true });
  });
}

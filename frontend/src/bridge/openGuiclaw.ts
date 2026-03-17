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
  enabled: boolean;
  tools?: string[];
  ui_config?: SkillConfigField[];
  config_values?: Record<string, unknown>;
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
};

export type ChatAskOption = {
  id: string;
  label: string;
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

export type OpenGuiclawApp = {
  skills: SkillRecord[];
  schedulerTasks: SchedulerTask[];
  messages: ChatMessage[];
  currentThreadId: string | null;
  threadLoading?: boolean;
  loadSkills: () => Promise<void>;
  reloadSkills: () => Promise<void>;
  toggleSkill: (name: string, enabled: boolean) => Promise<void>;
  loadSchedulerTasks: () => Promise<void>;
  toggleSchedulerTask: (taskId: string, enabled: boolean) => Promise<void>;
  triggerSchedulerTask: (taskId: string) => Promise<void>;
  deleteSchedulerTask: (taskId: string) => Promise<void>;
  openSchedulerForm: () => void;
  editSchedulerTask: (task: SchedulerTask) => void;
  submitAskUserChoice: (msg: ChatMessage, block: ChatBlock, opt: ChatAskOption) => Promise<void>;
};

declare global {
  interface Window {
    __openGuiclawApp?: OpenGuiclawApp;
  }
}

export function getHostApp(): OpenGuiclawApp | null {
  return window.__openGuiclawApp ?? null;
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

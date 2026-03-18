import { ChatComposer } from './components/ChatComposer';
import { ChatMessageList } from './components/ChatMessageList';
import { ChatThreadToolbar } from './components/ChatThreadToolbar';
import { ArchivedPanel } from './components/ArchivedPanel';
import { AgentSettingsPanel } from './components/AgentSettingsPanel';
import { DiaryPanel } from './components/DiaryPanel';
import { DiagnosticsPanel } from './components/DiagnosticsPanel';
import { HomeWorkspaceDashboard } from './components/HomeWorkspaceDashboard';
import { IdentityPanel } from './components/IdentityPanel';
import { IntegrationsPanel } from './components/IntegrationsPanel';
import { MemoryPanel } from './components/MemoryPanel';
import { McpServersPanel } from './components/McpServersPanel';
import { ModelsPanel } from './components/ModelsPanel';
import { PersonaPanel } from './components/PersonaPanel';
import { SettingsMainHeader } from './components/SettingsMainHeader';
import { SettingsNav } from './components/SettingsNav';
import { SettingsButton } from './components/SettingsButton';
import { SidebarToggleButton } from './components/SidebarToggleButton';
import React from 'react';
import ReactDOM from 'react-dom/client';
import { SchedulerPanel } from './components/SchedulerPanel';
import { SkillsQuickPanel } from './components/SkillsQuickPanel';
import { TokenStatsPanel } from './components/TokenStatsPanel';
import { VrmDrawer } from './components/VrmDrawer';
import { WorkspaceCreateModal } from './components/WorkspaceCreateModal';
import { WorkspaceSidebar } from './components/WorkspaceSidebar';

const skillsRoot = document.querySelector<HTMLElement>('[data-react-skills-root]');
const legacyInstalledRoot = document.querySelector<HTMLElement>('[data-legacy-skills-installed-root]');
const schedulerRoot = document.querySelector<HTMLElement>('[data-react-scheduler-root]');
const legacySchedulerRoot = document.querySelector<HTMLElement>('[data-legacy-scheduler-main-root]');
const homeRoot = document.querySelector<HTMLElement>('[data-react-home-root]');
const legacyHomeRoot = document.querySelector<HTMLElement>('[data-legacy-home-root]');
const sidebarRoot = document.querySelector<HTMLElement>('[data-react-sidebar-root]');
const legacySidebarRoot = document.querySelector<HTMLElement>('[data-legacy-sidebar-root]');
const workspaceModalRoot = document.querySelector<HTMLElement>('[data-react-workspace-modal-root]');
const legacyWorkspaceModalRoot = document.querySelector<HTMLElement>('[data-legacy-workspace-modal-root]');
const chatRoot = document.querySelector<HTMLElement>('[data-react-chat-root]');
const legacyChatRoot = document.querySelector<HTMLElement>('[data-legacy-chat-message-root]');
const chatComposerRoot = document.querySelector<HTMLElement>('[data-react-chat-composer-root]');
const legacyChatComposerRoot = document.querySelector<HTMLElement>('[data-legacy-chat-composer-root]');
const vrmDrawerRoot = document.querySelector<HTMLElement>('[data-react-vrm-drawer-root]');
const settingsVrmRoot = document.querySelector<HTMLElement>('[data-react-settings-vrm-root]');
const toolbarRoot = document.querySelector<HTMLElement>('[data-react-topbar-toolbar]');
const legacyTopbarBreadcrumb = document.querySelector<HTMLElement>('[data-legacy-topbar-breadcrumb]');
const legacyTopbarActions = document.querySelector<HTMLElement>('[data-legacy-topbar-actions]');
// 第二层：settings 按钮 + workspace switcher
const settingsBtnRoot = document.querySelector<HTMLElement>('[data-react-settings-btn-root]');
const legacySettingsBtn = document.querySelector<HTMLElement>('[data-legacy-settings-btn]');
// 第二层：sidebar toggle 按钮
const sidebarToggleRoot = document.querySelector<HTMLElement>('[data-react-sidebar-toggle-root]');
const legacySidebarToggle = document.querySelector<HTMLElement>('[data-legacy-sidebar-toggle]');

if (skillsRoot) {
  skillsRoot.hidden = false;
  if (legacyInstalledRoot) {
    legacyInstalledRoot.hidden = true;
    legacyInstalledRoot.style.display = 'none';
  }
  ReactDOM.createRoot(skillsRoot).render(
    <React.StrictMode>
      <SkillsQuickPanel />
    </React.StrictMode>
  );
}

if (schedulerRoot) {
  schedulerRoot.hidden = false;
  if (legacySchedulerRoot) {
    legacySchedulerRoot.hidden = true;
    legacySchedulerRoot.style.display = 'none';
  }
  ReactDOM.createRoot(schedulerRoot).render(
    <React.StrictMode>
      <SchedulerPanel />
    </React.StrictMode>
  );
}

if (homeRoot) {
  homeRoot.hidden = false;
  if (legacyHomeRoot) {
    legacyHomeRoot.hidden = true;
    legacyHomeRoot.style.display = 'none';
  }
  ReactDOM.createRoot(homeRoot).render(
    <React.StrictMode>
      <HomeWorkspaceDashboard />
    </React.StrictMode>
  );
}

if (sidebarRoot) {
  sidebarRoot.hidden = false;
  if (legacySidebarRoot) {
    legacySidebarRoot.hidden = true;
    legacySidebarRoot.style.display = 'none';
  }
  ReactDOM.createRoot(sidebarRoot).render(
    <React.StrictMode>
      <WorkspaceSidebar />
    </React.StrictMode>
  );
}

if (workspaceModalRoot) {
  workspaceModalRoot.hidden = false;
  if (legacyWorkspaceModalRoot) {
    legacyWorkspaceModalRoot.hidden = true;
    legacyWorkspaceModalRoot.style.display = 'none';
  }
  ReactDOM.createRoot(workspaceModalRoot).render(
    <React.StrictMode>
      <WorkspaceCreateModal />
    </React.StrictMode>
  );
}

if (chatRoot) {
  chatRoot.hidden = false;
  if (legacyChatRoot) {
    legacyChatRoot.hidden = true;
    legacyChatRoot.style.display = 'none';
  }
  ReactDOM.createRoot(chatRoot).render(
    <React.StrictMode>
      <ChatMessageList />
    </React.StrictMode>
  );
}

if (chatComposerRoot) {
  chatComposerRoot.hidden = false;
  if (legacyChatComposerRoot) {
    legacyChatComposerRoot.hidden = true;
    legacyChatComposerRoot.style.display = 'none';
  }
  ReactDOM.createRoot(chatComposerRoot).render(
    <React.StrictMode>
      <ChatComposer />
    </React.StrictMode>
  );
}

if (vrmDrawerRoot) {
  vrmDrawerRoot.hidden = false;
  ReactDOM.createRoot(vrmDrawerRoot).render(
    <React.StrictMode>
      <VrmDrawer mode="chat" />
    </React.StrictMode>
  );
}

if (settingsVrmRoot) {
  settingsVrmRoot.hidden = false;
  ReactDOM.createRoot(settingsVrmRoot).render(
    <React.StrictMode>
      <VrmDrawer mode="settings" />
    </React.StrictMode>
  );
}

if (toolbarRoot) {
  toolbarRoot.hidden = false;
  if (legacyTopbarBreadcrumb) {
    legacyTopbarBreadcrumb.hidden = true;
    legacyTopbarBreadcrumb.style.display = 'none';
  }
  if (legacyTopbarActions) {
    legacyTopbarActions.hidden = true;
    legacyTopbarActions.style.display = 'none';
  }
  ReactDOM.createRoot(toolbarRoot).render(
    <React.StrictMode>
      <ChatThreadToolbar />
    </React.StrictMode>
  );
}

// ── 第二层：settings 按钮 ─────────────────────────────────────────────────
if (settingsBtnRoot) {
  settingsBtnRoot.hidden = false;
  if (legacySettingsBtn) {
    legacySettingsBtn.hidden = true;
    legacySettingsBtn.style.display = 'none';
  }
  ReactDOM.createRoot(settingsBtnRoot).render(
    <React.StrictMode>
      <SettingsButton variant="full" />
    </React.StrictMode>
  );
}

// ── 第二层：sidebar toggle 按钮 ───────────────────────────────────────────
if (sidebarToggleRoot) {
  if (legacySidebarToggle) {
    legacySidebarToggle.hidden = true;
    legacySidebarToggle.style.display = 'none';
  }
  ReactDOM.createRoot(sidebarToggleRoot).render(
    <React.StrictMode>
      <SidebarToggleButton />
    </React.StrictMode>
  );
}

// ── 阶段 5：settings nav ──────────────────────────────────────────────────
const settingsNavRoot = document.querySelector<HTMLElement>('[data-react-settings-nav-root]');
const legacySettingsNav = document.querySelector<HTMLElement>('[data-legacy-settings-nav]');

if (settingsNavRoot) {
  if (legacySettingsNav) {
    legacySettingsNav.hidden = true;
    legacySettingsNav.style.display = 'none';
  }
  ReactDOM.createRoot(settingsNavRoot).render(
    <React.StrictMode>
      <SettingsNav />
    </React.StrictMode>
  );
}

// ── 阶段 6：settings main header ──────────────────────────────────────────
const settingsHeaderRoot = document.querySelector<HTMLElement>('[data-react-settings-header-root]');
const legacySettingsHeader = document.querySelector<HTMLElement>('[data-legacy-settings-header]');
const archivedRoot = document.querySelector<HTMLElement>('[data-react-archived-root]');
const legacyArchivedRoot = document.querySelector<HTMLElement>('[data-legacy-archived-root]');
const mcpRoot = document.querySelector<HTMLElement>('[data-react-mcp-root]');
const legacyMcpRoot = document.querySelector<HTMLElement>('[data-legacy-mcp-root]');
const memoryRoot = document.querySelector<HTMLElement>('[data-react-memory-root]');
const legacyMemoryRoot = document.querySelector<HTMLElement>('[data-legacy-memory-root]');
const tokenRoot = document.querySelector<HTMLElement>('[data-react-token-root]');
const legacyTokenRoot = document.querySelector<HTMLElement>('[data-legacy-token-root]');
const integrationsRoot = document.querySelector<HTMLElement>('[data-react-integrations-root]');
const legacyIntegrationsRoot = document.querySelector<HTMLElement>('[data-legacy-integrations-root]');
const identityRoot = document.querySelector<HTMLElement>('[data-react-identity-root]');
const legacyIdentityRoot = document.querySelector<HTMLElement>('[data-legacy-identity-root]');
const diagnosticsRoot = document.querySelector<HTMLElement>('[data-react-diagnostics-root]');
const legacyDiagnosticsRoot = document.querySelector<HTMLElement>('[data-legacy-diagnostics-root]');
const modelsRoot = document.querySelector<HTMLElement>('[data-react-models-root]');
const legacyModelsRoot = document.querySelector<HTMLElement>('[data-legacy-models-root]');
const agentRoot = document.querySelector<HTMLElement>('[data-react-agent-root]');
const legacyAgentRoot = document.querySelector<HTMLElement>('[data-legacy-agent-root]');
const diaryRoot = document.querySelector<HTMLElement>('[data-react-diary-root]');
const personaRoot = document.querySelector<HTMLElement>('[data-react-persona-root]');

if (settingsHeaderRoot) {
  if (legacySettingsHeader) {
    legacySettingsHeader.hidden = true;
    legacySettingsHeader.style.display = 'none';
  }
  ReactDOM.createRoot(settingsHeaderRoot).render(
    <React.StrictMode>
      <SettingsMainHeader />
    </React.StrictMode>
  );
}

if (archivedRoot) {
  archivedRoot.hidden = false;
  if (legacyArchivedRoot) {
    legacyArchivedRoot.hidden = true;
    legacyArchivedRoot.style.display = 'none';
  }
  ReactDOM.createRoot(archivedRoot).render(
    <React.StrictMode>
      <ArchivedPanel />
    </React.StrictMode>
  );
}

if (memoryRoot) {
  memoryRoot.hidden = false;
  if (legacyMemoryRoot) {
    legacyMemoryRoot.hidden = true;
    legacyMemoryRoot.style.display = 'none';
  }
  ReactDOM.createRoot(memoryRoot).render(
    <React.StrictMode>
      <MemoryPanel />
    </React.StrictMode>
  );
}

if (tokenRoot) {
  tokenRoot.hidden = false;
  if (legacyTokenRoot) {
    legacyTokenRoot.hidden = true;
    legacyTokenRoot.style.display = 'none';
  }
  ReactDOM.createRoot(tokenRoot).render(
    <React.StrictMode>
      <TokenStatsPanel />
    </React.StrictMode>
  );
}

if (mcpRoot) {
  mcpRoot.hidden = false;
  if (legacyMcpRoot) {
    legacyMcpRoot.hidden = true;
    legacyMcpRoot.style.display = 'none';
  }
  ReactDOM.createRoot(mcpRoot).render(
    <React.StrictMode>
      <McpServersPanel />
    </React.StrictMode>
  );
}

if (integrationsRoot) {
  integrationsRoot.hidden = false;
  if (legacyIntegrationsRoot) {
    legacyIntegrationsRoot.hidden = true;
    legacyIntegrationsRoot.style.display = 'none';
  }
  ReactDOM.createRoot(integrationsRoot).render(
    <React.StrictMode>
      <IntegrationsPanel />
    </React.StrictMode>
  );
}

if (identityRoot) {
  identityRoot.hidden = false;
  if (legacyIdentityRoot) {
    legacyIdentityRoot.hidden = true;
    legacyIdentityRoot.style.display = 'none';
  }
  ReactDOM.createRoot(identityRoot).render(
    <React.StrictMode>
      <IdentityPanel />
    </React.StrictMode>
  );
}

if (diagnosticsRoot) {
  diagnosticsRoot.hidden = false;
  if (legacyDiagnosticsRoot) {
    legacyDiagnosticsRoot.hidden = true;
    legacyDiagnosticsRoot.style.display = 'none';
  }
  ReactDOM.createRoot(diagnosticsRoot).render(
    <React.StrictMode>
      <DiagnosticsPanel />
    </React.StrictMode>
  );
}

if (modelsRoot) {
  modelsRoot.hidden = false;
  if (legacyModelsRoot) {
    legacyModelsRoot.hidden = true;
    legacyModelsRoot.style.display = 'none';
  }
  ReactDOM.createRoot(modelsRoot).render(
    <React.StrictMode>
      <ModelsPanel />
    </React.StrictMode>
  );
}

if (agentRoot) {
  agentRoot.hidden = false;
  if (legacyAgentRoot) {
    legacyAgentRoot.hidden = true;
    legacyAgentRoot.style.display = 'none';
  }
  ReactDOM.createRoot(agentRoot).render(
    <React.StrictMode>
      <AgentSettingsPanel />
    </React.StrictMode>
  );
}

if (diaryRoot) {
  diaryRoot.hidden = false;
  ReactDOM.createRoot(diaryRoot).render(
    <React.StrictMode>
      <DiaryPanel />
    </React.StrictMode>
  );
}

if (personaRoot) {
  personaRoot.hidden = false;
  ReactDOM.createRoot(personaRoot).render(
    <React.StrictMode>
      <PersonaPanel />
    </React.StrictMode>
  );
}

import { ChatComposer } from './components/ChatComposer';
import { ChatMessageList } from './components/ChatMessageList';
import { ChatThreadToolbar } from './components/ChatThreadToolbar';
import { HomeWorkspaceDashboard } from './components/HomeWorkspaceDashboard';
import React from 'react';
import ReactDOM from 'react-dom/client';
import { SchedulerPanel } from './components/SchedulerPanel';
import { SkillsQuickPanel } from './components/SkillsQuickPanel';
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
const toolbarRoot = document.querySelector<HTMLElement>('[data-react-topbar-toolbar]');
const legacyTopbarBreadcrumb = document.querySelector<HTMLElement>('[data-legacy-topbar-breadcrumb]');
const legacyTopbarActions = document.querySelector<HTMLElement>('[data-legacy-topbar-actions]');

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

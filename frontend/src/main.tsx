import { ChatMessageList } from './components/ChatMessageList';
import React from 'react';
import ReactDOM from 'react-dom/client';
import { SchedulerPanel } from './components/SchedulerPanel';
import { SkillsQuickPanel } from './components/SkillsQuickPanel';

const skillsRoot = document.querySelector<HTMLElement>('[data-react-skills-root]');
const legacyInstalledRoot = document.querySelector<HTMLElement>('[data-legacy-skills-installed-root]');
const schedulerRoot = document.querySelector<HTMLElement>('[data-react-scheduler-root]');
const legacySchedulerRoot = document.querySelector<HTMLElement>('[data-legacy-scheduler-main-root]');
const chatRoot = document.querySelector<HTMLElement>('[data-react-chat-root]');
const legacyChatRoot = document.querySelector<HTMLElement>('[data-legacy-chat-message-root]');

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

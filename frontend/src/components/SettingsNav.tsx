import { dispatchShellAction } from '../bridge/openGuiclaw';
import { SETTINGS_TABS, type SettingsTabId } from '../constants/settingsTabs';
import { useWorkspaceShellBridge } from '../hooks/useWorkspaceShellBridge';
import { UiButton } from './ui/UiButton';
import { UiCard } from './ui/UiCard';

const TAB_ICONS: Record<SettingsTabId, string> = {
  models: 'M',
  agent: 'A',
  diary: 'J',
  persona: 'V',
  mcp: 'P',
  memory: 'R',
  tokens: 'T',
  integrations: 'I',
  identity: 'D',
  diagnostics: 'S',
  archived: 'H'
};

export function SettingsNav() {
  const { snapshot } = useWorkspaceShellBridge();
  const currentViewIsSettings = snapshot.currentView === 'settings';

  function handleTabClick(tabId: SettingsTabId) {
    dispatchShellAction({ type: 'switchSettingsTab', tab: tabId });
  }

  function handleBackClick() {
    dispatchShellAction({ type: 'closeSettings' });
  }

  return (
    <UiCard as="aside" variant="subtle" className="settings-nav">
      <div className="settings-nav-header">
        <div className="settings-nav-kicker">OpenGuiclaw</div>
        <h2>设置中心</h2>
        <p>把模型、身份和工具接入整理到同一处，减少层级和认知切换。</p>
      </div>
      {currentViewIsSettings ? (
        <UiButton type="button" variant="ghost" className="settings-nav-back" onClick={handleBackClick}>
          <span className="settings-nav-back-icon" aria-hidden="true">
            ←
          </span>
          <span className="settings-nav-back-copy">
            <strong>返回上一页</strong>
          </span>
        </UiButton>
      ) : null}
      <div className="settings-nav-list">
        {SETTINGS_TABS.map((tab) => (
          <UiButton
            key={tab.id}
            className={`settings-nav-item${snapshot.settingsTab === tab.id ? ' active' : ''}`}
            variant="ghost"
            active={snapshot.settingsTab === tab.id}
            onClick={() => handleTabClick(tab.id)}
          >
            <span className="settings-nav-icon" aria-hidden="true">
              {TAB_ICONS[tab.id]}
            </span>
            <span className="settings-nav-copy">
              <span className="settings-nav-title">{tab.title}</span>
            </span>
          </UiButton>
        ))}
      </div>
    </UiCard>
  );
}

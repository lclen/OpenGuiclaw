import { SETTINGS_TABS, getTabMeta, type SettingsTabId } from '../constants/settingsTabs';
import { dispatchShellAction } from '../bridge/openGuiclaw';
import { useWorkspaceShellBridge } from '../hooks/useWorkspaceShellBridge';

/**
 * SettingsNav
 *
 * 阶段 5：替换 settings_overlay.html 左侧 tab 导航。
 * tab 定义从 constants/settingsTabs.ts 单一来源导入。
 */
export function SettingsNav() {
  const { snapshot } = useWorkspaceShellBridge();

  function handleTabClick(tabId: SettingsTabId) {
    dispatchShellAction({ type: 'switchSettingsTab', tab: tabId });
  }

  return (
    <aside className="settings-nav">
      <div className="settings-nav-header">
        <div className="settings-nav-kicker">OpenGuiclaw</div>
        <h2>设置中心</h2>
        <p>把模型、身份和工具接入整理到同一处，减少层级和认知切换。</p>
      </div>
      <div className="settings-nav-list">
        {SETTINGS_TABS.map((tab) => (
          <button
            key={tab.id}
            type="button"
            className={`settings-nav-item${snapshot.settingsTab === tab.id ? ' active' : ''}`}
            onClick={() => handleTabClick(tab.id)}
          >
            <span className="settings-nav-title">{tab.title}</span>
            <span className="settings-nav-description">{tab.description}</span>
          </button>
        ))}
      </div>
    </aside>
  );
}

/**
 * SettingsMainHeader
 *
 * 阶段 6：替换 settings_overlay.html 右侧 .settings-main-header 区域。
 * 包含：kicker、当前 tab 标题、副标题、关闭按钮。
 * 与 SettingsNav 共享同一份 snapshot，状态源唯一。
 */
export function SettingsMainHeader() {
  const { snapshot } = useWorkspaceShellBridge();
  const tab = getTabMeta(snapshot.settingsTab);

  function handleClose() {
    dispatchShellAction({ type: 'closeSettings' });
  }

  return (
    <div className="settings-main-header">
      <div>
        <div className="settings-main-kicker">Workspace Preferences</div>
        <h3>{tab.title}</h3>
        <p>{tab.description}</p>
      </div>
      <button type="button" className="settings-close" onClick={handleClose}>
        关闭
      </button>
    </div>
  );
}

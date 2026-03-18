import { dispatchShellAction } from '../bridge/openGuiclaw';
import { getTabMeta } from '../constants/settingsTabs';
import { useWorkspaceShellBridge } from '../hooks/useWorkspaceShellBridge';

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

      <div className="settings-main-header__actions">
        <button type="button" className="settings-close" onClick={handleClose}>
          返回
        </button>
      </div>
    </div>
  );
}

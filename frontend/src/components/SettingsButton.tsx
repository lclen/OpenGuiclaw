import { useShellActions } from '../hooks/useShellActions';
import { useWorkspaceShellBridge } from '../hooks/useWorkspaceShellBridge';

type SettingsButtonProps = {
  /** 点击时默认打开的 tab，不传则保持上次 tab */
  defaultTab?: string;
  /** 按钮展示模式：icon-only 或 icon+label */
  variant?: 'icon' | 'full';
};

/**
 * SettingsButton
 *
 * 第二层 React 化：设置入口按钮。
 * 原来 Alpine 模板直接写 showSettings = true，
 * 现在通过 dispatchShellAction({ type: 'openSettings' }) 桥接。
 *
 * 支持 variant='full'（sidebar footer 样式）和 variant='icon'（topbar 图标样式）。
 */
export function SettingsButton({ defaultTab, variant = 'full' }: SettingsButtonProps) {
  const { snapshot } = useWorkspaceShellBridge();
  const { openSettings } = useShellActions();

  const isActive = snapshot.showSettings;

  function handleClick() {
    openSettings(defaultTab);
  }

  if (variant === 'icon') {
    return (
      <button
        type="button"
        className={`react-settings-icon-btn${isActive ? ' is-active' : ''}`}
        title="设置"
        aria-label="打开设置"
        onClick={handleClick}
      >
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" aria-hidden="true">
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth="1.8"
            d="M12 15a3 3 0 100-6 3 3 0 000 6z"
          />
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth="1.8"
            d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 010 2.83 2 2 0 01-2.83 0l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-4 0v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83-2.83l.06-.06A1.65 1.65 0 004.68 15a1.65 1.65 0 00-1.51-1H3a2 2 0 010-4h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 012.83-2.83l.06.06A1.65 1.65 0 009 4.68a1.65 1.65 0 001-1.51V3a2 2 0 014 0v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 2.83l-.06.06A1.65 1.65 0 0019.4 9a1.65 1.65 0 001.51 1H21a2 2 0 010 4h-.09a1.65 1.65 0 00-1.51 1z"
          />
        </svg>
      </button>
    );
  }

  // variant === 'full'：sidebar footer 样式
  return (
    <button
      type="button"
      className={`sidebar-shortcut-btn sidebar-footer-btn react-settings-full-btn${isActive ? ' is-active' : ''}`}
      aria-label="打开设置"
      onClick={handleClick}
    >
      <span className="sidebar-shortcut-icon" aria-hidden="true">
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" aria-hidden="true">
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth="1.8"
            d="M12 15a3 3 0 100-6 3 3 0 000 6z"
          />
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth="1.8"
            d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 010 2.83 2 2 0 01-2.83 0l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-4 0v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83-2.83l.06-.06A1.65 1.65 0 004.68 15a1.65 1.65 0 00-1.51-1H3a2 2 0 010-4h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 012.83-2.83l.06.06A1.65 1.65 0 009 4.68a1.65 1.65 0 001-1.51V3a2 2 0 014 0v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 2.83l-.06.06A1.65 1.65 0 0019.4 9a1.65 1.65 0 001.51 1H21a2 2 0 010 4h-.09a1.65 1.65 0 00-1.51 1z"
          />
        </svg>
      </span>
      <span>设置</span>
    </button>
  );
}

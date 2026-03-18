import { dispatchShellAction } from '../bridge/openGuiclaw';

/**
 * SidebarToggleButton
 * 替换 index.html 里的 Alpine sidebar-toggle 按钮。
 * 通过 dispatchShellAction 桥接，不直接写宿主字段。
 */
export function SidebarToggleButton() {
  function handleClick() {
    dispatchShellAction({ type: 'toggleSidebar' });
  }

  return (
    <button
      type="button"
      className="sidebar-toggle"
      aria-label="切换侧边栏"
      onClick={handleClick}
    >
      ☰
    </button>
  );
}

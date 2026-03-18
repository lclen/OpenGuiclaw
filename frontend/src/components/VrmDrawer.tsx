import { useEffect } from 'react';
import { useWorkspaceShellBridge } from '../hooks/useWorkspaceShellBridge';

type VrmDrawerMode = 'chat' | 'settings';

type RuntimeManager = {
  currentModel?: {
    scene?: {
      position: { x: number; y: number; z: number; set: (x: number, y: number, z: number) => void };
    };
  };
  interaction?: {
    enableMouseTracking?: (enabled: boolean) => void;
    enableFaceCamera?: boolean;
  };
  animation?: {
    _lastVrmaUrl?: string;
  };
  playVRMAAnimation?: (url: string, options?: Record<string, unknown>) => Promise<void> | void;
  stopVRMAAnimation?: () => void;
  _lookAtSmoother?: {
    enableSaccade?: boolean;
    userTarget?: unknown;
  };
  _shadowMesh?: {
    position?: { y?: number };
  };
};

const drawerStyle = {
  position: 'relative',
  display: 'flex',
  width: 0,
  minWidth: 0,
  maxWidth: 0,
  height: '100%',
  overflow: 'hidden',
  opacity: 0,
  pointerEvents: 'none',
  transition: 'width 260ms ease, max-width 260ms ease, opacity 260ms ease',
  flex: '0 0 auto'
} as const;

const drawerOpenStyle = {
  width: 'min(420px, 32vw)',
  maxWidth: 'min(420px, 32vw)',
  opacity: 1,
  pointerEvents: 'auto'
} as const;

const panelStyle = {
  width: 'min(420px, 32vw)',
  minWidth: '320px',
  height: '100%',
  display: 'flex',
  flexDirection: 'column',
  background: 'rgba(6, 10, 15, 0.94)',
  borderLeft: '1px solid rgba(255, 255, 255, 0.08)',
  boxShadow: '-24px 0 48px rgba(0, 0, 0, 0.45)',
  backdropFilter: 'blur(18px)',
  WebkitBackdropFilter: 'blur(18px)'
} as const;

const headerStyle = {
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
  gap: '16px',
  padding: '18px 18px 14px',
  borderBottom: '1px solid rgba(255, 255, 255, 0.08)',
  flex: '0 0 auto'
} as const;

const eyebrowStyle = {
  fontSize: '11px',
  fontWeight: 700,
  letterSpacing: '0.12em',
  textTransform: 'uppercase',
  color: 'rgba(182, 240, 89, 0.9)'
} as const;

const titleStyle = {
  margin: '4px 0 0',
  fontSize: '18px',
  fontWeight: 700,
  color: '#fff'
} as const;

const actionsStyle = {
  display: 'flex',
  alignItems: 'center',
  gap: '8px'
} as const;

const headerButtonStyle = {
  border: '1px solid rgba(255, 255, 255, 0.1)',
  background: 'rgba(255, 255, 255, 0.04)',
  color: 'rgba(255, 255, 255, 0.82)',
  borderRadius: '10px',
  padding: '8px 12px',
  fontSize: '12px',
  fontWeight: 600,
  cursor: 'pointer'
} as const;

const closeButtonStyle = {
  ...headerButtonStyle,
  color: 'rgba(182, 240, 89, 0.95)',
  borderColor: 'rgba(182, 240, 89, 0.28)',
  background: 'rgba(182, 240, 89, 0.08)'
} as const;

const canvasShellStyle = {
  position: 'relative',
  flex: '1 1 auto',
  minHeight: 0,
  background:
    'radial-gradient(circle at top, rgba(182, 240, 89, 0.12), transparent 30%), linear-gradient(180deg, rgba(16, 22, 30, 0.96), rgba(5, 8, 12, 0.98))'
} as const;

const canvasStyle = {
  display: 'block',
  width: '100%',
  height: '100%'
} as const;

const errorStyle = {
  position: 'absolute',
  left: '16px',
  right: '16px',
  bottom: '16px',
  display: 'none',
  padding: '10px 12px',
  borderRadius: '12px',
  background: 'rgba(140, 24, 42, 0.8)',
  border: '1px solid rgba(244, 63, 94, 0.3)',
  color: '#fff',
  fontSize: '12px',
  lineHeight: 1.5
} as const;

export function VrmDrawer({ mode = 'chat' }: { mode?: VrmDrawerMode }) {
  const { hostApp, snapshot } = useWorkspaceShellBridge();
  const inChat = snapshot.currentView === 'chat';
  const inPersonaSettings = snapshot.currentView === 'settings' && snapshot.settingsTab === 'persona';
  const shouldRender = mode === 'settings' ? inPersonaSettings : inChat && snapshot.vrmSystemEnabled;
  const isPinnedPreview = mode === 'settings' && inPersonaSettings;
  const isOpen = isPinnedPreview || (shouldRender && snapshot.showVrm);
  const runtimeApp = window.appInstance as (typeof window.appInstance & { ensureVRMReady?: () => Promise<boolean> }) | undefined;

  useEffect(() => {
    if (!isOpen) return;

    const timer = window.setTimeout(() => {
      void runtimeApp?.ensureVRMReady?.();
      window.dispatchEvent(new Event('resize'));
    }, 40);

    return () => window.clearTimeout(timer);
  }, [isOpen, runtimeApp]);

  useEffect(() => {
    if (!isOpen) return;

    const timer = window.setTimeout(() => {
      const manager = runtimeApp?.vrmManager as RuntimeManager | undefined;
      if (!manager) return;

      if (mode === 'settings') {
        manager.stopVRMAAnimation?.();
        if (manager.interaction) {
          manager.interaction.enableFaceCamera = false;
          manager.interaction.enableMouseTracking?.(false);
        }
        if (manager._lookAtSmoother) {
          manager._lookAtSmoother.enableSaccade = false;
          manager._lookAtSmoother.userTarget = null;
        }
        const scene = manager.currentModel?.scene;
        const shadowY = manager._shadowMesh?.position?.y;
        if (scene && typeof shadowY === 'number' && Number.isFinite(shadowY)) {
          scene.position.set(scene.position.x, -shadowY, scene.position.z);
        }
        window.dispatchEvent(new Event('resize'));
        return;
      }

      if (manager.interaction) {
        manager.interaction.enableFaceCamera = true;
        manager.interaction.enableMouseTracking?.(true);
      }
      if (manager._lookAtSmoother) {
        manager._lookAtSmoother.enableSaccade = true;
      }
      const idleUrl = manager.animation?._lastVrmaUrl;
      if (idleUrl && manager.playVRMAAnimation) {
        void manager.playVRMAAnimation(idleUrl, { loop: true, immediate: true });
      }
    }, 120);

    return () => window.clearTimeout(timer);
  }, [isOpen, mode, runtimeApp]);

  if (!shouldRender) return null;

  return (
    <aside
      className={`react-vrm-drawer${isOpen ? ' is-open' : ''}`}
      aria-hidden={!isOpen}
      style={isOpen ? { ...drawerStyle, ...drawerOpenStyle } : drawerStyle}
    >
      <div className="react-vrm-drawer__panel" style={panelStyle}>
        <div className="react-vrm-drawer__header" style={headerStyle}>
          <div>
            <div className="react-vrm-drawer__eyebrow" style={eyebrowStyle}>
              {isPinnedPreview ? 'VRM Preview' : 'VRM Avatar'}
            </div>
            <h3 className="react-vrm-drawer__title" style={titleStyle}>
              {isPinnedPreview ? '实时预览' : '3D 形象'}
            </h3>
          </div>

          <div className="react-vrm-drawer__actions" style={actionsStyle}>
            <button
              type="button"
              className="react-vrm-drawer__header-btn"
              style={headerButtonStyle}
              onClick={() => void runtimeApp?.ensureVRMReady?.()}
              title="重新初始化 VRM"
            >
              刷新
            </button>
            {isPinnedPreview ? null : (
              <button
                type="button"
                className="react-vrm-drawer__header-btn is-close"
                style={closeButtonStyle}
                onClick={() => hostApp?.toggleVrm?.()}
                title="关闭 VRM 抽屉"
              >
                收起
              </button>
            )}
          </div>
        </div>

        <div id="canvas-container" className="react-vrm-drawer__canvas-shell" style={canvasShellStyle}>
          <canvas id="vrm-canvas" className="react-vrm-drawer__canvas" style={canvasStyle} />
          <div id="vrm-load-error" className="react-vrm-drawer__error" style={errorStyle} />
        </div>
      </div>
    </aside>
  );
}

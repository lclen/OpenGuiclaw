import { useEffect, useMemo, useState } from 'react';
import { StorePanel } from './StorePanel';
import { useWorkspaceShellBridge } from '../hooks/useWorkspaceShellBridge';

type LoadState = {
  loading: boolean;
  errorText: string;
};

type PersonaMap = Record<string, string>;

type VrmModelRecord = {
  name: string;
  path: string;
};

type VrmAnimationRecord = {
  name: string;
  path: string;
};

type SaveState = '' | 'saving' | 'ok' | 'error';

declare global {
  interface Window {
    appInstance?: {
      vrmManager?: {
        camera?: {
          position: { x: number; y: number; z: number; set: (x: number, y: number, z: number) => void };
          quaternion: { x: number; y: number; z: number; w: number; set: (x: number, y: number, z: number, w: number) => void };
        };
        currentModel?: {
          url?: string;
          scene?: {
            position: { x: number; y: number; z: number; set: (x: number, y: number, z: number) => void };
            scale: { x: number; y: number; z: number; set: (x: number, y: number, z: number) => void };
            rotation: { x: number; y: number; z: number; set: (x: number, y: number, z: number) => void };
          };
        };
        animation?: {
          _lastVrmaUrl?: string;
          isIdleAnimation?: boolean;
          playVRMAAnimation?: (url: string, options?: Record<string, unknown>) => Promise<void>;
        };
        expression?: {
          setMood: (mood: string) => void;
        };
        interaction?: {
          enableMouseTracking?: (enabled: boolean) => void;
          enableFaceCamera?: boolean;
        };
        _lookAtSmoother?: {
          enableSaccade?: boolean;
          userTarget?: unknown;
        };
        _shadowMesh?: {
          position?: { x: number; y: number; z: number };
        };
        _cameraTarget?: { x: number; y: number; z: number };
        loadModel?: (path: string, options?: Record<string, unknown>) => Promise<void>;
        playVRMAAnimation?: (url: string, options?: Record<string, unknown>) => void;
        stopVRMAAnimation?: () => void;
      };
    };
    THREE?: {
      Vector3: new (x: number, y: number, z: number) => { x: number; y: number; z: number };
    };
  }
}

async function parseResponse(response: Response) {
  const contentType = response.headers.get('content-type') || '';
  if (contentType.includes('application/json')) return response.json();
  return response.text();
}

async function ensureVrmRuntimeReady() {
  const runtimeApp = window.appInstance as (typeof window.appInstance & {
    ensureVRMReady?: () => Promise<boolean>;
  }) | undefined;
  const ready = await runtimeApp?.ensureVRMReady?.();
  return ready !== false;
}

async function readErrorMessage(response: Response, fallback: string) {
  try {
    const payload = await parseResponse(response);
    if (payload && typeof payload === 'object' && 'detail' in payload && typeof payload.detail === 'string') {
      return payload.detail;
    }
    if (typeof payload === 'string' && payload.trim()) return payload;
  } catch {
    // Ignore parse failure and use fallback below.
  }
  return fallback;
}

function stabilizeSettingsPreview() {
  const vm = window.appInstance?.vrmManager;
  if (!vm) return;

  try {
    vm.stopVRMAAnimation?.();
  } catch {
    // ignore stop failure
  }

  try {
    if (vm.interaction) {
      vm.interaction.enableFaceCamera = false;
      vm.interaction.enableMouseTracking?.(false);
    }
  } catch {
    // ignore interaction update failure
  }

  try {
    if (vm._lookAtSmoother) {
      vm._lookAtSmoother.enableSaccade = false;
      vm._lookAtSmoother.userTarget = null;
    }
  } catch {
    // ignore smoother update failure
  }

  try {
    vm.expression?.setMood('neutral');
  } catch {
    // ignore neutral reset failure
  }

  try {
    const scene = vm.currentModel?.scene;
    const shadowY = vm._shadowMesh?.position?.y;
    if (scene && typeof shadowY === 'number' && Number.isFinite(shadowY)) {
      scene.position.set(scene.position.x, -shadowY, scene.position.z);
    }
  } catch {
    // ignore grounding failure
  }

  window.dispatchEvent(new Event('resize'));
}

const EXPRESSION_OPTIONS = [
  { key: 'happy', label: '开心' },
  { key: 'angry', label: '生气' },
  { key: 'sad', label: '难过' },
  { key: 'relaxed', label: '放松' },
  { key: 'surprised', label: '惊讶' }
] as const;

export function PersonaPanel() {
  const { snapshot } = useWorkspaceShellBridge();
  const [activeTab, setActiveTab] = useState<'local' | 'store'>('local');
  const [personas, setPersonas] = useState<PersonaMap>({});
  const [models, setModels] = useState<VrmModelRecord[]>([]);
  const [animations, setAnimations] = useState<VrmAnimationRecord[]>([]);
  const [loadState, setLoadState] = useState<LoadState>({ loading: true, errorText: '' });
  const [uploading, setUploading] = useState(false);
  const [busyKey, setBusyKey] = useState('');
  const [statusText, setStatusText] = useState('');
  const [saveState, setSaveState] = useState<SaveState>('');

  useEffect(() => {
    if (!snapshot.showSettings || snapshot.settingsTab !== 'persona') return;
    void loadAll();
  }, [snapshot.showSettings, snapshot.settingsTab]);

  useEffect(() => {
    if (snapshot.settingsTab === 'persona') {
      setActiveTab('local');
    }
  }, [snapshot.settingsTab]);

  useEffect(() => {
    if (!snapshot.showSettings || snapshot.settingsTab !== 'persona') return;
    const timer = window.setTimeout(() => {
      stabilizeSettingsPreview();
    }, 120);
    return () => window.clearTimeout(timer);
  }, [snapshot.showSettings, snapshot.settingsTab]);

  const personaEntries = useMemo(() => Object.entries(personas), [personas]);

  function pushStatus(message: string) {
    setStatusText(message);
    window.clearTimeout((pushStatus as typeof pushStatus & { timer?: number }).timer);
    (pushStatus as typeof pushStatus & { timer?: number }).timer = window.setTimeout(() => {
      setStatusText('');
    }, 3200);
  }

  async function loadAll() {
    setLoadState({ loading: true, errorText: '' });
    try {
      await Promise.all([loadPersona(), loadModels(), loadAnimations()]);
      setLoadState({ loading: false, errorText: '' });
    } catch (error) {
      setLoadState({
        loading: false,
        errorText: error instanceof Error ? error.message : '加载 VRM 面板失败'
      });
    }
  }

  async function loadPersona() {
    const response = await fetch('/api/persona');
    if (!response.ok) throw new Error(await readErrorMessage(response, '加载角色设定失败'));
    const payload = await parseResponse(response);
    setPersonas(payload && typeof payload === 'object' ? (payload as PersonaMap) : {});
  }

  async function loadModels() {
    const response = await fetch('/api/vrm/models');
    if (!response.ok) throw new Error(await readErrorMessage(response, '加载 VRM 模型列表失败'));
    const payload = await parseResponse(response);
    setModels(Array.isArray(payload?.models) ? payload.models : []);
  }

  async function loadAnimations() {
    const response = await fetch('/api/vrm/animations');
    if (!response.ok) throw new Error(await readErrorMessage(response, '加载动作列表失败'));
    const payload = await parseResponse(response);
    setAnimations(Array.isArray(payload?.animations) ? payload.animations : []);
  }

  async function handleUpload(file: File | null) {
    if (!file) return;
    if (!file.name.toLowerCase().endsWith('.vrm')) {
      pushStatus('请上传 .vrm 格式文件');
      return;
    }
    const formData = new FormData();
    formData.append('file', file);
    setUploading(true);
    try {
      const response = await fetch('/api/vrm/upload', { method: 'POST', body: formData });
      if (!response.ok) throw new Error(await readErrorMessage(response, '上传 VRM 模型失败'));
      const payload = await parseResponse(response);
      pushStatus('模型上传成功');
      await loadModels();
      if (payload && typeof payload === 'object' && 'path' in payload && typeof payload.path === 'string') {
        await switchVrmModel(payload.path);
      }
    } catch (error) {
      pushStatus(error instanceof Error ? error.message : '上传 VRM 模型失败');
    } finally {
      setUploading(false);
    }
  }

  async function switchVrmModel(modelPath: string) {
    const runtimeReady = await ensureVrmRuntimeReady();
    const vm = window.appInstance?.vrmManager;
    if (!runtimeReady) {
      pushStatus('VRM 预览容器尚未准备完成，请稍后重试');
      return;
    }
    if (!vm?.loadModel) {
      pushStatus('VRM 管理器尚未就绪');
      return;
    }

    setBusyKey(`model:${modelPath}`);
    try {
      const lastActionUrl = vm.animation?._lastVrmaUrl || '';
      const shouldResumeAction = !!lastActionUrl && vm.animation?.isIdleAnimation !== true;

      await vm.loadModel(modelPath, { autoPlay: false });
      stabilizeSettingsPreview();

      if (shouldResumeAction && vm.playVRMAAnimation) {
        try {
          await vm.playVRMAAnimation(lastActionUrl, { loop: true, immediate: true, isIdle: false });
        } catch {
          // ignore action resume failure; model switch itself already succeeded
        }
      }

      pushStatus('模型切换成功');
    } catch (error) {
      pushStatus(error instanceof Error ? error.message : '模型切换失败');
    } finally {
      setBusyKey('');
    }
  }

  function triggerExpression(mood: string) {
    const expression = window.appInstance?.vrmManager?.expression;
    if (!expression?.setMood) {
      pushStatus('表情控制器尚未就绪');
      return;
    }
    expression.setMood(mood);
    pushStatus(`已触发表情：${mood}`);
  }

  async function triggerAction(path: string) {
    const runtimeReady = await ensureVrmRuntimeReady();
    const manager = window.appInstance?.vrmManager;
    if (!runtimeReady) {
      pushStatus('VRM 预览容器尚未准备完成，请稍后重试');
      return;
    }
    if (!manager?.playVRMAAnimation) {
      pushStatus('动作控制器尚未就绪');
      return;
    }
    manager.playVRMAAnimation(path, { loop: true });
    pushStatus(`正在播放动作：${path.split('/').pop() || path}`);
  }

  async function deleteModel(name: string) {
    const confirmed = window.confirm(`确定要删除模型 ${name} 吗？`);
    if (!confirmed) return;
    setBusyKey(`delete:${name}`);
    try {
      const response = await fetch(`/api/vrm/models/${encodeURIComponent(name)}`, { method: 'DELETE' });
      if (!response.ok) throw new Error(await readErrorMessage(response, '删除模型失败'));
      pushStatus(`已删除模型 ${name}`);
      await loadModels();
    } catch (error) {
      pushStatus(error instanceof Error ? error.message : '删除模型失败');
    } finally {
      setBusyKey('');
    }
  }

  async function saveVrmConfig() {
    const vm = window.appInstance?.vrmManager;
    if (!vm?.currentModel?.scene || !vm.currentModel.url) {
      setSaveState('error');
      pushStatus('模型尚未加载，无法保存视角');
      window.setTimeout(() => setSaveState(''), 2000);
      return;
    }

    setSaveState('saving');
    try {
      const scene = vm.currentModel.scene;
      const camera = vm.camera;
      const target = vm._cameraTarget || { x: 0, y: 0, z: 0 };
      const payload = {
        model_path: vm.currentModel.url,
        position: { x: scene.position.x, y: scene.position.y, z: scene.position.z },
        scale: { x: scene.scale.x, y: scene.scale.y, z: scene.scale.z },
        rotation: { x: scene.rotation.x, y: scene.rotation.y, z: scene.rotation.z },
        viewport: { width: window.screen.width, height: window.screen.height },
        camera_position: camera
          ? {
              x: camera.position.x,
              y: camera.position.y,
              z: camera.position.z,
              qx: camera.quaternion.x,
              qy: camera.quaternion.y,
              qz: camera.quaternion.z,
              qw: camera.quaternion.w,
              targetX: target.x,
              targetY: target.y,
              targetZ: target.z
            }
          : null
      };
      const response = await fetch('/api/config/preferences', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      if (!response.ok) throw new Error(await readErrorMessage(response, '保存视角失败'));
      setSaveState('ok');
      pushStatus('视角配置已保存');
    } catch (error) {
      setSaveState('error');
      pushStatus(error instanceof Error ? error.message : '保存视角失败');
    } finally {
      window.setTimeout(() => setSaveState(''), 2200);
    }
  }

  return (
    <div className="persona-panel">
      <div className="persona-panel__tab-row">
        <button
          type="button"
          className={`persona-panel__tab-btn${activeTab === 'local' ? ' is-active' : ''}`}
          onClick={() => setActiveTab('local')}
        >
          本地配置
        </button>
        <button
          type="button"
          className={`persona-panel__tab-btn${activeTab === 'store' ? ' is-active' : ''}`}
          onClick={() => setActiveTab('store')}
        >
          VRM 商店
        </button>
      </div>

      {activeTab === 'local' ? (
        <>
          <section className="persona-panel__section">
            <header className="persona-panel__section-head">
              <div>
                <div className="persona-panel__eyebrow">角色人格</div>
                <h4 className="persona-panel__title">角色资料</h4>
                <p className="persona-panel__meta">查看当前启用的人格文本与角色底层设定。</p>
              </div>
              <button type="button" className="persona-panel__ghost-btn" onClick={() => void loadAll()}>
                刷新
              </button>
            </header>

            {loadState.errorText ? <div className="persona-panel__notice persona-panel__notice--error">{loadState.errorText}</div> : null}
            {loadState.loading ? <div className="persona-panel__empty">正在加载角色与 VRM 资源...</div> : null}

            {!loadState.loading ? (
              <div className="persona-panel__profile-grid">
                {personaEntries.length > 0 ? (
                  personaEntries.map(([name, content]) => (
                    <article key={name} className="persona-panel__profile-card">
                      <div className="persona-panel__profile-name">{name}</div>
                      <pre className="persona-panel__profile-content">{content}</pre>
                    </article>
                  ))
                ) : (
                  <div className="persona-panel__empty">当前没有可展示的人格文本。</div>
                )}
              </div>
            ) : null}
          </section>

          <section className="persona-panel__section">
            <header className="persona-panel__section-head">
                <div>
                <div className="persona-panel__eyebrow">模型资产</div>
                <h4 className="persona-panel__title">VRM 模型库</h4>
                <p className="persona-panel__meta">上传、切换、删除本地模型，并可单独保存当前视角。</p>
              </div>
              <div className="persona-panel__actions">
                <button type="button" className="persona-panel__accent-btn" onClick={() => void saveVrmConfig()}>
                  {saveState === 'saving' ? '保存中...' : saveState === 'ok' ? '已保存' : saveState === 'error' ? '异常' : '保存视角'}
                </button>
                <label className="persona-panel__upload-btn">
                  <span>{uploading ? '上传中...' : '上传 .vrm'}</span>
                  <input
                    type="file"
                    accept=".vrm"
                    disabled={uploading}
                    onChange={(event) => {
                      const file = event.target.files?.[0] || null;
                      void handleUpload(file);
                      event.currentTarget.value = '';
                    }}
                  />
                </label>
              </div>
            </header>

            <div className="persona-panel__model-list">
              {models.length > 0 ? (
                models.map((model) => {
                  const switchKey = `model:${model.path}`;
                  const deleteKey = `delete:${model.name}`;
                  return (
                    <article key={model.path} className="persona-panel__model-card">
                      <div className="persona-panel__model-main">
                        <strong>{model.name}</strong>
                        <span>{model.path}</span>
                      </div>
                      <div className="persona-panel__actions">
                        <button
                          type="button"
                          className="persona-panel__soft-btn"
                          disabled={busyKey === switchKey}
                          onClick={() => void switchVrmModel(model.path)}
                        >
                          {busyKey === switchKey ? '切换中...' : '载入'}
                        </button>
                        <button
                          type="button"
                          className="persona-panel__danger-btn"
                          disabled={busyKey === deleteKey}
                          onClick={() => void deleteModel(model.name)}
                        >
                          {busyKey === deleteKey ? '删除中...' : '删除'}
                        </button>
                      </div>
                    </article>
                  );
                })
              ) : (
                <div className="persona-panel__empty">尚未检测到本地 VRM 模型。</div>
              )}
            </div>
          </section>

          <section className="persona-panel__section">
            <header className="persona-panel__section-head">
              <div>
                <div className="persona-panel__eyebrow">互动控制</div>
                <h4 className="persona-panel__title">表情与动作</h4>
                <p className="persona-panel__meta">即时触发表情和 VRMA 动作，方便快速调试角色演出。</p>
              </div>
            </header>

            <div className="persona-panel__expression-grid">
              {EXPRESSION_OPTIONS.map((option) => (
                <button key={option.key} type="button" className="persona-panel__chip-btn" onClick={() => triggerExpression(option.key)}>
                  {option.label}
                </button>
              ))}
              <button type="button" className="persona-panel__chip-btn is-accent" onClick={() => triggerExpression('neutral')}>
                重置表情
              </button>
            </div>

            <div className="persona-panel__animation-grid">
              {animations.length > 0 ? (
                animations.map((animation) => (
                  <button
                    key={animation.path}
                    type="button"
                    className="persona-panel__animation-card"
                    onClick={() => void triggerAction(animation.path)}
                  >
                    <strong>{animation.name}</strong>
                    <span>{animation.path.split('/').pop()}</span>
                  </button>
                ))
              ) : (
                <div className="persona-panel__empty">尚未检测到本地 VRMA 动作。</div>
              )}
            </div>
          </section>
        </>
      ) : null}

      {activeTab === 'store' ? (
        <section className="persona-panel__section persona-panel__section--store">
          <StorePanel embedded />
        </section>
      ) : null}

      {statusText ? <div className="persona-panel__notice persona-panel__notice--status">{statusText}</div> : null}
    </div>
  );
}

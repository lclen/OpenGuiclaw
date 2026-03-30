import { Fragment, useEffect, useMemo, useState } from 'react';
import { useWorkspaceShellBridge } from '../hooks/useWorkspaceShellBridge';
import { UiButton } from './ui/UiButton';
import { UiStatusPill } from './ui/UiStatusPill';

type StoreItem = {
  id: string;
  name: string;
  author?: string;
  category?: string;
  thumb?: string;
  homepage?: string;
  url?: string;
};

type StorePayload = {
  models?: StoreItem[];
  animations?: StoreItem[];
};

type VrmModelRecord = {
  name: string;
  path: string;
};

type VrmAnimationRecord = {
  name: string;
  path: string;
};

type LoadState = {
  loading: boolean;
  errorText: string;
};

async function parseResponse(response: Response) {
  const contentType = response.headers.get('content-type') || '';
  if (contentType.includes('application/json')) return response.json();
  return response.text();
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

type StorePanelProps = {
  embedded?: boolean;
};

export function StorePanel({ embedded = false }: StorePanelProps) {
  const { snapshot } = useWorkspaceShellBridge();
  const [storePayload, setStorePayload] = useState<StorePayload>({ models: [], animations: [] });
  const [categories, setCategories] = useState<string[]>(['All']);
  const [selectedCategory, setSelectedCategory] = useState('All');
  const [models, setModels] = useState<VrmModelRecord[]>([]);
  const [animations, setAnimations] = useState<VrmAnimationRecord[]>([]);
  const [loadState, setLoadState] = useState<LoadState>({ loading: true, errorText: '' });
  const [downloadingIds, setDownloadingIds] = useState<string[]>([]);
  const [statusText, setStatusText] = useState('');

  useEffect(() => {
    if (!snapshot.showSettings) return;
    if (!embedded && snapshot.settingsTab !== 'store') return;
    if (embedded && snapshot.settingsTab !== 'persona') return;
    void loadAll();
  }, [embedded, snapshot.showSettings, snapshot.settingsTab]);

  const filteredModels = useMemo(() => {
    const items = storePayload.models || [];
    return selectedCategory === 'All' ? items : items.filter((item) => item.category === selectedCategory);
  }, [storePayload.models, selectedCategory]);

  const filteredAnimations = useMemo(() => {
    const items = storePayload.animations || [];
    return selectedCategory === 'All' ? items : items.filter((item) => item.category === selectedCategory);
  }, [storePayload.animations, selectedCategory]);

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
      await Promise.all([loadStoreItems(), loadModels(), loadAnimations()]);
      setLoadState({ loading: false, errorText: '' });
    } catch (error) {
      setLoadState({
        loading: false,
        errorText: error instanceof Error ? error.message : '加载 VRM 商店失败'
      });
    }
  }

  async function loadStoreItems() {
    const response = await fetch('/api/store/list');
    if (!response.ok) throw new Error(await readErrorMessage(response, '加载商店资源失败'));
    const payload = await parseResponse(response);
    const nextPayload = payload && typeof payload === 'object' ? (payload as StorePayload) : { models: [], animations: [] };
    setStorePayload(nextPayload);

    const nextCategories = Array.from(
      new Set([
        'All',
        ...((nextPayload.models || []).map((item) => item.category).filter(Boolean) as string[]),
        ...((nextPayload.animations || []).map((item) => item.category).filter(Boolean) as string[])
      ])
    );
    setCategories(nextCategories);
    if (!nextCategories.includes(selectedCategory)) {
      setSelectedCategory('All');
    }
  }

  async function loadModels() {
    const response = await fetch('/api/vrm/models');
    if (!response.ok) throw new Error(await readErrorMessage(response, '加载本地模型失败'));
    const payload = await parseResponse(response);
    setModels(Array.isArray(payload?.models) ? payload.models : []);
  }

  async function loadAnimations() {
    const response = await fetch('/api/vrm/animations');
    if (!response.ok) throw new Error(await readErrorMessage(response, '加载本地动作失败'));
    const payload = await parseResponse(response);
    setAnimations(Array.isArray(payload?.animations) ? payload.animations : []);
  }

  function isModelDownloaded(item: StoreItem) {
    const expectedName = item.name.endsWith('.vrm') ? item.name : `${item.name}.vrm`;
    return models.some((model) => model.name === expectedName);
  }

  function isAnimationDownloaded(item: StoreItem) {
    const expectedName = item.name.endsWith('.vrma') ? item.name : `${item.name}.vrma`;
    return animations.some((animation) => animation.name === item.name || `${animation.name}.vrma` === expectedName);
  }

  async function downloadItem(item: StoreItem, type: 'model' | 'animation') {
    if (!item.url || downloadingIds.includes(item.id)) return;
    setDownloadingIds((current) => [...current, item.id]);
    try {
      const response = await fetch('/api/store/download', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: item.url, type, name: item.name })
      });
      if (!response.ok) throw new Error(await readErrorMessage(response, '提交下载任务失败'));
      pushStatus(`${item.name} 已开始后台下载`);

      const expectedName = type === 'model' ? `${item.name}.vrm` : `${item.name}.vrma`;
      const deadline = Date.now() + 120000;
      let found = false;
      while (!found && Date.now() < deadline) {
        if (type === 'model') {
          const modelsResponse = await fetch('/api/vrm/models');
          const modelsPayload = await parseResponse(modelsResponse);
          const nextModels = Array.isArray(modelsPayload?.models) ? modelsPayload.models : [];
          setModels(nextModels);
          found = nextModels.some((model: VrmModelRecord) => model.name === expectedName);
        } else {
          const animationsResponse = await fetch('/api/vrm/animations');
          const animationsPayload = await parseResponse(animationsResponse);
          const nextAnimations = Array.isArray(animationsPayload?.animations) ? animationsPayload.animations : [];
          setAnimations(nextAnimations);
          found = nextAnimations.some(
            (animation: VrmAnimationRecord) => animation.name === item.name || `${animation.name}.vrma` === expectedName
          );
        }
        if (!found) {
          await new Promise((resolve) => window.setTimeout(resolve, 3000));
        }
      }

      pushStatus(found ? `${item.name} 下载完成` : `${item.name} 下载超时，请稍后手动刷新`);
    } catch (error) {
      pushStatus(error instanceof Error ? error.message : '下载资源失败');
    } finally {
      setDownloadingIds((current) => current.filter((id) => id !== item.id));
    }
  }

  const content = (
    <>
      {!embedded ? (
        <header className="store-panel__header">
          <div>
            <div className="store-panel__eyebrow">云端资源</div>
            <h4 className="store-panel__title">VRM 资源商店</h4>
            <p className="store-panel__meta">浏览模型与动作资源，并直接下载安装到本地库。</p>
          </div>
          <UiButton type="button" variant="secondary" className="store-panel__action-btn" onClick={() => void loadAll()}>
            刷新
          </UiButton>
        </header>
      ) : (
        <header className="persona-panel__section-head">
          <div>
            <div className="persona-panel__eyebrow">云端资源</div>
            <h4 className="persona-panel__title">VRM 资源商店</h4>
            <p className="persona-panel__meta">浏览模型与动作资源，并直接下载安装到本地库。</p>
          </div>
          <UiButton type="button" variant="secondary" className="persona-panel__action-btn" onClick={() => void loadAll()}>
            刷新
          </UiButton>
        </header>
      )}

      <div className="store-panel__category-row">
        {categories.map((category) => (
          <UiButton
            key={category}
            type="button"
            variant="secondary"
            size="sm"
            active={selectedCategory === category}
            className="store-panel__category-btn"
            onClick={() => setSelectedCategory(category)}
          >
            {category}
          </UiButton>
        ))}
      </div>

      {loadState.errorText ? <div className="store-panel__notice store-panel__notice--error">{loadState.errorText}</div> : null}
      {loadState.loading ? <div className="store-panel__empty">正在建立资源连接...</div> : null}

      {!loadState.loading ? (
        <>
          <section className="store-panel__section">
            <div className="store-panel__section-head">
              <h5>模型资源</h5>
              <UiStatusPill tone="disabled" className="store-panel__count-pill">
                {filteredModels.length} 项
              </UiStatusPill>
            </div>
            <div className="store-panel__grid is-models">
              {filteredModels.length > 0 ? (
                filteredModels.map((item) => {
                  const busy = downloadingIds.includes(item.id);
                  const downloaded = isModelDownloaded(item);
                  return (
                    <article key={item.id} className="store-panel__card">
                      <div className="store-panel__thumb">
                        {item.thumb ? <img src={item.thumb} alt={item.name} /> : <span>{item.name.slice(0, 1).toUpperCase()}</span>}
                        {item.homepage ? (
                          <a href={item.homepage} target="_blank" rel="noreferrer" className="store-panel__link-btn">
                            外链
                          </a>
                        ) : null}
                      </div>
                      <div className="store-panel__card-body">
                        <strong>{item.name}</strong>
                        <span>Creator: @{item.author || 'Anonymous'}</span>
                        <UiStatusPill tone="disabled" className="store-panel__category-pill">
                          {item.category || 'Uncategorized'}
                        </UiStatusPill>
                        <UiButton
                          type="button"
                          variant={!item.url ? 'secondary' : 'primary'}
                          size="sm"
                          className="store-panel__action-btn"
                          disabled={busy || downloaded}
                          onClick={() => {
                            if (!item.url && item.homepage) {
                              window.open(item.homepage, '_blank', 'noopener,noreferrer');
                              return;
                            }
                            void downloadItem(item, 'model');
                          }}
                        >
                          {!item.url ? '外部资源查看' : busy ? '加载中...' : downloaded ? '已部署' : '下载模型'}
                        </UiButton>
                      </div>
                    </article>
                  );
                })
              ) : (
                <div className="store-panel__empty">当前分类下没有可用模型资源。</div>
              )}
            </div>
          </section>

          <section className="store-panel__section">
            <div className="store-panel__section-head">
              <h5>动作资源</h5>
              <UiStatusPill tone="disabled" className="store-panel__count-pill">
                {filteredAnimations.length} 项
              </UiStatusPill>
            </div>
            <div className="store-panel__grid is-animations">
              {filteredAnimations.length > 0 ? (
                filteredAnimations.map((item) => {
                  const busy = downloadingIds.includes(item.id);
                  const downloaded = isAnimationDownloaded(item);
                  return (
                    <article key={item.id} className="store-panel__mini-card">
                      <div className="store-panel__mini-copy">
                        <strong>{item.name}</strong>
                        <span>{item.category || 'Uncategorized'}</span>
                      </div>
                      <UiButton
                        type="button"
                        variant={!item.url ? 'secondary' : 'primary'}
                        size="sm"
                        className="store-panel__action-btn"
                        disabled={busy || downloaded}
                        onClick={() => {
                          if (!item.url && item.homepage) {
                            window.open(item.homepage, '_blank', 'noopener,noreferrer');
                            return;
                          }
                          void downloadItem(item, 'animation');
                        }}
                      >
                        {!item.url ? '外部查看' : busy ? '加载中...' : downloaded ? '已就绪' : '下载动作'}
                      </UiButton>
                    </article>
                  );
                })
              ) : (
                <div className="store-panel__empty">当前分类下没有可用动作资源。</div>
              )}
            </div>
          </section>
        </>
      ) : null}

      {statusText ? <div className="store-panel__notice store-panel__notice--status">{statusText}</div> : null}
    </>
  );

  if (embedded) {
    return <Fragment>{content}</Fragment>;
  }

  return (
    <div className="store-panel">
      {content}
    </div>
  );
}

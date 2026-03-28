import { useEffect, useMemo, useState } from 'react';
import { emitShellUpdate } from '../bridge/openGuiclaw';
import { useWorkspaceShellBridge } from '../hooks/useWorkspaceShellBridge';
import { UiActionTray } from './ui/UiActionTray';
import { UiButton } from './ui/UiButton';
import { UiStatusPill } from './ui/UiStatusPill';

type UsageLayer = 'all' | 'context' | 'preference' | 'experience';

type MemoryRecord = {
  id: string;
  content: string;
  type?: string | null;
  usage_layer?: string | null;
  tags?: string[];
  created_at?: string | null;
  timestamp?: string | number | null;
  source?: string | null;
};

type MemoryItemView = MemoryRecord & {
  _selected: boolean;
  _editing: boolean;
  _editBuffer: string;
};

type LoadState = {
  loading: boolean;
  errorText: string;
};

const LAYER_OPTIONS: Array<{ value: UsageLayer; label: string }> = [
  { value: 'all', label: '全部' },
  { value: 'context', label: '上下文' },
  { value: 'preference', label: '偏好' },
  { value: 'experience', label: '经验' }
];

const LAYER_LABELS: Record<string, string> = {
  context: '上下文层',
  preference: '偏好层',
  experience: '经验层'
};

const TYPE_LABELS: Record<string, string> = {
  fact: 'fact',
  preference: 'preference',
  rule: 'rule',
  skill: 'skill',
  error: 'error',
  experience: 'experience',
  general: 'general',
  profile: 'profile'
};

const LAYER_ORDER: Record<string, number> = {
  context: 0,
  preference: 1,
  experience: 2
};

async function parseResponse(response: Response) {
  const contentType = response.headers.get('content-type') || '';
  if (contentType.includes('application/json')) {
    return response.json();
  }
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
    // Ignore parse failures and use fallback below.
  }
  return fallback;
}

function normalizeUsageLayer(value?: string | null): Exclude<UsageLayer, 'all'> {
  const normalized = (value || 'context').trim().toLowerCase();
  if (normalized === 'preference' || normalized === 'experience') return normalized;
  return 'context';
}

function normalizeType(value?: string | null) {
  return (value || 'fact').trim().toLowerCase() || 'fact';
}

function toViewItem(item: MemoryRecord): MemoryItemView {
  return {
    ...item,
    usage_layer: normalizeUsageLayer(item.usage_layer),
    type: normalizeType(item.type),
    _selected: false,
    _editing: false,
    _editBuffer: item.content || ''
  };
}

function getTimestampValue(item: MemoryRecord) {
  if (typeof item.timestamp === 'number') return item.timestamp;
  if (typeof item.timestamp === 'string') {
    const numeric = Number(item.timestamp);
    if (!Number.isNaN(numeric) && Number.isFinite(numeric)) return numeric;
    const parsed = Date.parse(item.timestamp);
    if (!Number.isNaN(parsed)) return parsed / 1000;
  }
  if (item.created_at) {
    const parsed = Date.parse(item.created_at.replace(' ', 'T'));
    if (!Number.isNaN(parsed)) return parsed / 1000;
  }
  return 0;
}

function formatMemoryTime(item: MemoryRecord) {
  return typeof item.created_at === 'string' && item.created_at.trim()
    ? item.created_at
    : typeof item.timestamp === 'string' || typeof item.timestamp === 'number'
      ? String(item.timestamp)
      : '无时间戳';
}

export function MemoryPanel() {
  const { snapshot } = useWorkspaceShellBridge();
  const [items, setItems] = useState<MemoryItemView[]>([]);
  const [loadState, setLoadState] = useState<LoadState>({ loading: true, errorText: '' });
  const [searchText, setSearchText] = useState('');
  const [layerFilter, setLayerFilter] = useState<UsageLayer>('all');
  const [statusText, setStatusText] = useState('');
  const [busyKey, setBusyKey] = useState<string | null>(null);

  useEffect(() => {
    if (!snapshot.showSettings || snapshot.settingsTab !== 'memory') return;
    void loadMemories();
  }, [snapshot.showSettings, snapshot.settingsTab]);

  const layerCounts = useMemo(
    () =>
      items.reduce(
        (accumulator, item) => {
          accumulator.all += 1;
          accumulator[normalizeUsageLayer(item.usage_layer)] += 1;
          return accumulator;
        },
        { all: 0, context: 0, preference: 0, experience: 0 }
      ),
    [items]
  );

  const filteredItems = useMemo(() => {
    const search = searchText.trim().toLowerCase();
    const nextItems = items.filter((item) => {
      const normalizedLayer = normalizeUsageLayer(item.usage_layer);
      const matchesLayer = layerFilter === 'all' || normalizedLayer === layerFilter;
      if (!matchesLayer) return false;
      if (!search) return true;
      const haystack = [
        item.content || '',
        item.type || '',
        normalizedLayer,
        LAYER_LABELS[normalizedLayer] || '',
        ...(Array.isArray(item.tags) ? item.tags : [])
      ]
        .join(' ')
        .toLowerCase();
      return haystack.includes(search);
    });

    return [...nextItems].sort((left, right) => {
      const layerDiff = LAYER_ORDER[normalizeUsageLayer(left.usage_layer)] - LAYER_ORDER[normalizeUsageLayer(right.usage_layer)];
      if (layerDiff !== 0) return layerDiff;
      return getTimestampValue(right) - getTimestampValue(left);
    });
  }, [items, layerFilter, searchText]);

  const selectedCount = useMemo(() => items.filter((item) => item._selected).length, [items]);
  const allFilteredSelected = filteredItems.length > 0 && filteredItems.every((item) => item._selected);

  function pushStatus(message: string) {
    setStatusText(message);
    window.clearTimeout((pushStatus as typeof pushStatus & { timer?: number }).timer);
    (pushStatus as typeof pushStatus & { timer?: number }).timer = window.setTimeout(() => {
      setStatusText('');
    }, 3200);
  }

  async function loadMemories() {
    setLoadState({ loading: true, errorText: '' });
    try {
      const response = await fetch('/api/memory');
      if (!response.ok) {
        throw new Error(await readErrorMessage(response, '加载记忆列表失败'));
      }
      const payload = await parseResponse(response);
      const nextItems = Array.isArray(payload?.memories)
        ? payload.memories.map((item: MemoryRecord) => toViewItem(item))
        : [];
      setItems(nextItems);
      setLoadState({ loading: false, errorText: '' });
      emitShellUpdate();
    } catch (error) {
      setItems([]);
      setLoadState({
        loading: false,
        errorText: error instanceof Error ? error.message : '加载记忆列表失败'
      });
    }
  }

  function updateItem(memoryId: string, patch: Partial<MemoryItemView>) {
    setItems((current) => current.map((item) => (item.id === memoryId ? { ...item, ...patch } : item)));
  }

  function toggleSelect(memoryId: string, selected: boolean) {
    updateItem(memoryId, { _selected: selected });
  }

  function toggleSelectAllFiltered() {
    const nextValue = !allFilteredSelected;
    const visibleIds = new Set(filteredItems.map((item) => item.id));
    setItems((current) =>
      current.map((item) => (visibleIds.has(item.id) ? { ...item, _selected: nextValue } : item))
    );
  }

  function startEdit(memoryId: string) {
    setItems((current) =>
      current.map((item) =>
        item.id === memoryId
          ? { ...item, _editing: true, _editBuffer: item.content || '' }
          : { ...item, _editing: false }
      )
    );
  }

  function cancelEdit(memoryId: string) {
    setItems((current) =>
      current.map((item) =>
        item.id === memoryId
          ? { ...item, _editing: false, _editBuffer: item.content || '' }
          : item
      )
    );
  }

  async function deleteMemory(memoryId: string) {
    setBusyKey(`delete:${memoryId}`);
    try {
      const response = await fetch(`/api/memory/${memoryId}`, { method: 'DELETE' });
      if (!response.ok) {
        throw new Error(await readErrorMessage(response, '删除记忆失败'));
      }
      pushStatus('记忆已成功删除');
      await loadMemories();
    } catch (error) {
      pushStatus(error instanceof Error ? error.message : '删除记忆失败');
    } finally {
      setBusyKey(null);
    }
  }

  async function saveEdit(item: MemoryItemView) {
    const content = item._editBuffer.trim();
    if (!content) {
      pushStatus('记忆内容不能为空');
      return;
    }

    setBusyKey(`save:${item.id}`);
    try {
      const response = await fetch(`/api/memory/${item.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content })
      });
      if (!response.ok) {
        throw new Error(await readErrorMessage(response, '更新记忆失败'));
      }
      setItems((current) =>
        current.map((entry) =>
          entry.id === item.id
            ? { ...entry, content, _editBuffer: content, _editing: false }
            : entry
        )
      );
      pushStatus('记忆已更新');
    } catch (error) {
      pushStatus(error instanceof Error ? error.message : '更新记忆失败');
    } finally {
      setBusyKey(null);
    }
  }

  async function batchDeleteSelected() {
    const ids = items.filter((item) => item._selected).map((item) => item.id);
    if (ids.length === 0) return;

    const confirmed = window.confirm(`确认删除选中的 ${ids.length} 条记忆吗？`);
    if (!confirmed) return;

    setBusyKey('batch-delete');
    try {
      const response = await fetch('/api/memory/batch_delete', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ids })
      });
      if (!response.ok) {
        throw new Error(await readErrorMessage(response, '批量删除记忆失败'));
      }
      pushStatus(`已删除 ${ids.length} 条记忆`);
      await loadMemories();
    } catch (error) {
      pushStatus(error instanceof Error ? error.message : '批量删除记忆失败');
    } finally {
      setBusyKey(null);
    }
  }

  return (
    <div className="memory-react-panel">
      <header className="memory-react-panel__toolbar">
        <div className="memory-react-panel__filters">
          <label className="memory-react-panel__search">
            <svg className="memory-react-panel__search-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M21 21l-4.35-4.35m1.85-5.15a7 7 0 11-14 0 7 7 0 0114 0z" />
            </svg>
            <input
              type="text"
              className="memory-react-panel__input"
              placeholder="搜索内容、用途层、标签或类型..."
              value={searchText}
              onChange={(event) => setSearchText(event.target.value)}
            />
          </label>

          <div className="memory-react-panel__layer-switch" role="tablist" aria-label="记忆用途层筛选">
            {LAYER_OPTIONS.map((option) => (
              <button
                key={option.value}
                type="button"
                className={`memory-react-panel__layer-btn${layerFilter === option.value ? ' is-active' : ''}`}
                onClick={() => setLayerFilter(option.value)}
              >
                {option.label}
              </button>
            ))}
          </div>
        </div>

        <UiActionTray className="memory-react-panel__actions">
          <UiButton
            type="button"
            variant="secondary"
            className="memory-react-panel__action-btn"
            onClick={loadMemories}
            disabled={loadState.loading}
          >
            刷新
          </UiButton>
          <UiButton
            type="button"
            variant="danger"
            className="memory-react-panel__action-btn memory-react-panel__action-btn--danger"
            onClick={batchDeleteSelected}
            disabled={selectedCount === 0 || busyKey === 'batch-delete'}
          >
            {busyKey === 'batch-delete' ? '删除中...' : '批量删除'}
          </UiButton>
        </UiActionTray>
      </header>

      <div className="memory-react-panel__summary">
        <div className="memory-react-panel__summary-main">
          <div className="memory-react-panel__summary-text">
            当前可见 <strong>{filteredItems.length}</strong> 条记忆
          </div>
          <div className="memory-react-panel__summary-text">
            已选 <strong>{selectedCount}</strong> 条
          </div>
          <button type="button" className="memory-react-panel__link-btn" onClick={toggleSelectAllFiltered}>
            {allFilteredSelected ? '取消全选' : '全选当前结果'}
          </button>
        </div>

        <div className="memory-react-panel__layer-stats">
          <div className="memory-react-panel__layer-stat">
            <span>上下文层</span>
            <strong>{layerCounts.context}</strong>
          </div>
          <div className="memory-react-panel__layer-stat">
            <span>偏好层</span>
            <strong>{layerCounts.preference}</strong>
          </div>
          <div className="memory-react-panel__layer-stat">
            <span>经验层</span>
            <strong>{layerCounts.experience}</strong>
          </div>
        </div>
      </div>

      {loadState.errorText ? <div className="memory-react-panel__notice memory-react-panel__notice--error">{loadState.errorText}</div> : null}
      {loadState.loading ? <div className="memory-react-panel__empty">正在加载记忆条目...</div> : null}

      {!loadState.loading && !loadState.errorText && filteredItems.length === 0 ? (
        <div className="memory-react-panel__empty">当前没有匹配的记忆条目，可以切换用途层或调整搜索词。</div>
      ) : null}

      {!loadState.loading && filteredItems.length > 0 ? (
        <div className="memory-react-panel__stack">
          {filteredItems.map((item) => {
            const deleteBusy = busyKey === `delete:${item.id}`;
            const saveBusy = busyKey === `save:${item.id}`;
            const normalizedLayer = normalizeUsageLayer(item.usage_layer);
            const normalizedType = normalizeType(item.type);

            return (
              <article key={item.id} className="memory-react-panel__card">
                <div className="memory-react-panel__card-main">
                  <label className="memory-react-panel__checkbox">
                    <input
                      type="checkbox"
                      checked={item._selected}
                      onChange={(event) => toggleSelect(item.id, event.target.checked)}
                    />
                  </label>

                  <div className="memory-react-panel__content-wrap">
                    <div className="memory-react-panel__card-top">
                      <div className="memory-react-panel__badges">
                        <UiStatusPill tone={normalizedLayer === 'context' ? 'brand' : normalizedLayer === 'preference' ? 'warning' : 'success'} className={`memory-react-panel__layer-pill is-${normalizedLayer}`}>
                          {LAYER_LABELS[normalizedLayer]}
                        </UiStatusPill>
                        <UiStatusPill tone={normalizedType === 'error' ? 'danger' : normalizedType === 'preference' ? 'warning' : normalizedType === 'experience' ? 'success' : 'neutral'} className={`memory-react-panel__type-pill is-${normalizedType}`}>
                          {TYPE_LABELS[normalizedType] || normalizedType}
                        </UiStatusPill>
                        <UiStatusPill tone="disabled" className="memory-react-panel__id">{item.id}</UiStatusPill>
                        {(item.tags || []).map((tag) => (
                          <UiStatusPill key={`${item.id}-${tag}`} tone="neutral" className="memory-react-panel__tag-pill">
                            {tag}
                          </UiStatusPill>
                        ))}
                      </div>

                      <UiActionTray className="memory-react-panel__card-actions">
                        {!item._editing ? (
                          <UiButton type="button" variant="secondary" className="memory-react-panel__action-btn memory-react-panel__action-btn--small" onClick={() => startEdit(item.id)}>
                            编辑
                          </UiButton>
                        ) : (
                          <UiButton type="button" variant="secondary" className="memory-react-panel__action-btn memory-react-panel__action-btn--small" onClick={() => cancelEdit(item.id)}>
                            取消
                          </UiButton>
                        )}

                        {item._editing ? (
                          <UiButton
                            type="button"
                            variant="primary"
                            className="memory-react-panel__action-btn memory-react-panel__action-btn--small memory-react-panel__action-btn--primary"
                            onClick={() => saveEdit(item)}
                            disabled={saveBusy}
                          >
                            {saveBusy ? '保存中...' : '保存'}
                          </UiButton>
                        ) : null}

                        <UiButton
                          type="button"
                          variant="danger"
                          className="memory-react-panel__action-btn memory-react-panel__action-btn--small memory-react-panel__action-btn--danger"
                          onClick={() => deleteMemory(item.id)}
                          disabled={deleteBusy}
                        >
                          {deleteBusy ? '删除中...' : '删除'}
                        </UiButton>
                      </UiActionTray>
                    </div>

                    {!item._editing ? (
                      <p className="memory-react-panel__content">{item.content}</p>
                    ) : (
                      <textarea
                        className="memory-react-panel__textarea"
                        value={item._editBuffer}
                        onChange={(event) => updateItem(item.id, { _editBuffer: event.target.value })}
                      />
                    )}

                    <footer className="memory-react-panel__card-footer">
                      <span>{formatMemoryTime(item)}</span>
                      <span className="memory-react-panel__dot">•</span>
                      <span>{item.source || 'Auto'}</span>
                    </footer>
                  </div>
                </div>
              </article>
            );
          })}
        </div>
      ) : null}

      {statusText ? <div className="memory-react-panel__notice memory-react-panel__notice--status">{statusText}</div> : null}
    </div>
  );
}

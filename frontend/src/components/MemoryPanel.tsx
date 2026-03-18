import { useEffect, useMemo, useState } from 'react';
import { emitShellUpdate } from '../bridge/openGuiclaw';
import { useWorkspaceShellBridge } from '../hooks/useWorkspaceShellBridge';

type MemoryType = 'all' | 'general' | 'fact' | 'preference' | 'profile' | 'error' | 'experience' | string;

type MemoryRecord = {
  id: string;
  content: string;
  type?: string | null;
  tags?: string[];
  created_at?: string | null;
  timestamp?: string | null;
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

const MEMORY_TYPE_OPTIONS: Array<{ value: MemoryType; label: string }> = [
  { value: 'all', label: '全部类型' },
  { value: 'general', label: 'general' },
  { value: 'fact', label: 'fact' },
  { value: 'preference', label: 'preference' },
  { value: 'profile', label: 'profile' },
  { value: 'error', label: 'error' },
  { value: 'experience', label: 'experience' }
];

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

function toViewItem(item: MemoryRecord): MemoryItemView {
  return {
    ...item,
    _selected: false,
    _editing: false,
    _editBuffer: item.content || ''
  };
}

function formatMemoryTime(item: MemoryRecord) {
  return item.timestamp || item.created_at || '无时间戳';
}

function normalizeType(value?: string | null) {
  return (value || 'general').trim() || 'general';
}

export function MemoryPanel() {
  const { snapshot } = useWorkspaceShellBridge();
  const [items, setItems] = useState<MemoryItemView[]>([]);
  const [loadState, setLoadState] = useState<LoadState>({ loading: true, errorText: '' });
  const [searchText, setSearchText] = useState('');
  const [typeFilter, setTypeFilter] = useState<MemoryType>('all');
  const [statusText, setStatusText] = useState('');
  const [busyKey, setBusyKey] = useState<string | null>(null);

  useEffect(() => {
    if (!snapshot.showSettings || snapshot.settingsTab !== 'memory') return;
    void loadMemories();
  }, [snapshot.showSettings, snapshot.settingsTab]);

  const filteredItems = useMemo(() => {
    const search = searchText.trim().toLowerCase();
    return items.filter((item) => {
      const matchesType = typeFilter === 'all' || normalizeType(item.type) === typeFilter;
      if (!matchesType) return false;
      if (!search) return true;
      const haystack = [item.content || '', item.type || '', ...(Array.isArray(item.tags) ? item.tags : [])]
        .join(' ')
        .toLowerCase();
      return haystack.includes(search);
    });
  }, [items, searchText, typeFilter]);

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
      const nextItems = Array.isArray(payload?.memories) ? payload.memories.map((item: MemoryRecord) => toViewItem(item)) : [];
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
              placeholder="搜索记忆内容、标签或类型..."
              value={searchText}
              onChange={(event) => setSearchText(event.target.value)}
            />
          </label>

          <select
            className="memory-react-panel__select"
            value={typeFilter}
            onChange={(event) => setTypeFilter(event.target.value)}
          >
            {MEMORY_TYPE_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </div>

        <div className="memory-react-panel__actions">
          <button
            type="button"
            className="memory-react-panel__ghost-btn"
            onClick={loadMemories}
            disabled={loadState.loading}
          >
            刷新
          </button>
          <button
            type="button"
            className="memory-react-panel__danger-btn"
            onClick={batchDeleteSelected}
            disabled={selectedCount === 0 || busyKey === 'batch-delete'}
          >
            {busyKey === 'batch-delete' ? '删除中...' : '批量删除'}
          </button>
        </div>
      </header>

      <div className="memory-react-panel__summary">
        <div className="memory-react-panel__summary-text">
          共 <strong>{filteredItems.length}</strong> 条可见记忆
        </div>
        <div className="memory-react-panel__summary-text">
          已选 <strong>{selectedCount}</strong> 条
        </div>
        <button type="button" className="memory-react-panel__link-btn" onClick={toggleSelectAllFiltered}>
          {allFilteredSelected ? '取消全选' : '全选当前结果'}
        </button>
      </div>

      {loadState.errorText ? <div className="memory-react-panel__notice memory-react-panel__notice--error">{loadState.errorText}</div> : null}
      {loadState.loading ? <div className="memory-react-panel__empty">正在加载记忆条目...</div> : null}

      {!loadState.loading && !loadState.errorText && filteredItems.length === 0 ? (
        <div className="memory-react-panel__empty">当前没有匹配的记忆条目，可以尝试调整搜索词或类型筛选。</div>
      ) : null}

      {!loadState.loading && filteredItems.length > 0 ? (
        <div className="memory-react-panel__stack">
          {filteredItems.map((item) => {
            const deleteBusy = busyKey === `delete:${item.id}`;
            const saveBusy = busyKey === `save:${item.id}`;
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
                        <span className={`memory-react-panel__type-pill is-${normalizeType(item.type)}`}>{normalizeType(item.type)}</span>
                        <span className="memory-react-panel__id">{item.id}</span>
                        {(item.tags || []).map((tag) => (
                          <span key={`${item.id}-${tag}`} className="memory-react-panel__tag-pill">
                            {tag}
                          </span>
                        ))}
                      </div>

                      <div className="memory-react-panel__card-actions">
                        {!item._editing ? (
                          <button type="button" className="memory-react-panel__soft-btn" onClick={() => startEdit(item.id)}>
                            编辑
                          </button>
                        ) : (
                          <button type="button" className="memory-react-panel__soft-btn" onClick={() => cancelEdit(item.id)}>
                            取消
                          </button>
                        )}

                        {item._editing ? (
                          <button
                            type="button"
                            className="memory-react-panel__accent-btn"
                            onClick={() => saveEdit(item)}
                            disabled={saveBusy}
                          >
                            {saveBusy ? '保存中...' : '保存'}
                          </button>
                        ) : null}

                        <button
                          type="button"
                          className="memory-react-panel__soft-danger-btn"
                          onClick={() => deleteMemory(item.id)}
                          disabled={deleteBusy}
                        >
                          {deleteBusy ? '删除中...' : '删除'}
                        </button>
                      </div>
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

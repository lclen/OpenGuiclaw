import { useEffect, useState } from 'react';
import { useWorkspaceShellBridge } from '../hooks/useWorkspaceShellBridge';
import { UiButton } from './ui/UiButton';

declare global {
  interface Window {
    marked?: {
      parse: (markdown: string) => string;
    };
  }
}

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
    // Ignore parse failure and fall back below.
  }
  return fallback;
}

export function DiaryPanel() {
  const { snapshot } = useWorkspaceShellBridge();
  const [dates, setDates] = useState<string[]>([]);
  const [selectedDate, setSelectedDate] = useState('');
  const [content, setContent] = useState('');
  const [loadState, setLoadState] = useState<LoadState>({ loading: true, errorText: '' });
  const [contentState, setContentState] = useState<LoadState>({ loading: false, errorText: '' });
  const [statusText, setStatusText] = useState('');

  useEffect(() => {
    if (!snapshot.showSettings || snapshot.settingsTab !== 'diary') return;
    void loadDiaryDates(true);
  }, [snapshot.showSettings, snapshot.settingsTab]);

  function pushStatus(message: string) {
    setStatusText(message);
    window.clearTimeout((pushStatus as typeof pushStatus & { timer?: number }).timer);
    (pushStatus as typeof pushStatus & { timer?: number }).timer = window.setTimeout(() => {
      setStatusText('');
    }, 3200);
  }

  async function loadDiaryDates(autoSelectFirst: boolean) {
    setLoadState({ loading: true, errorText: '' });
    try {
      const response = await fetch('/api/diary');
      if (!response.ok) {
        throw new Error(await readErrorMessage(response, '加载日记目录失败'));
      }
      const payload = await parseResponse(response);
      const nextDates = Array.isArray(payload) ? payload : [];
      setDates(nextDates);
      setLoadState({ loading: false, errorText: '' });

      const nextSelectedDate = selectedDate && nextDates.includes(selectedDate) ? selectedDate : nextDates[0] || '';
      if ((autoSelectFirst || !selectedDate) && nextSelectedDate) {
        await openDiary(nextSelectedDate);
      } else if (!nextSelectedDate) {
        setSelectedDate('');
        setContent('');
      }
    } catch (error) {
      setDates([]);
      setSelectedDate('');
      setContent('');
      setLoadState({
        loading: false,
        errorText: error instanceof Error ? error.message : '加载日记目录失败'
      });
    }
  }

  async function openDiary(date: string) {
    setSelectedDate(date);
    setContentState({ loading: true, errorText: '' });
    try {
      const response = await fetch(`/api/diary/${date}`);
      if (!response.ok) {
        throw new Error(await readErrorMessage(response, '加载日记内容失败'));
      }
      const payload = await parseResponse(response);
      const nextContent = payload && typeof payload === 'object' && 'content' in payload ? String(payload.content || '') : '';
      setContent(nextContent);
      setContentState({ loading: false, errorText: '' });
    } catch (error) {
      setContent('');
      setContentState({
        loading: false,
        errorText: error instanceof Error ? error.message : '加载日记内容失败'
      });
    }
  }

  return (
    <div className="diary-panel">
      <section className="diary-panel__sidebar">
        <header className="diary-panel__header">
          <div>
            <div className="diary-panel__eyebrow">认知日志</div>
            <h4 className="diary-panel__title">日记回溯</h4>
            <p className="diary-panel__meta">{dates.length} 份已生成记录</p>
          </div>
          <UiButton type="button" variant="secondary" className="diary-panel__action-btn" onClick={() => void loadDiaryDates(true)}>
            刷新
          </UiButton>
        </header>

        {loadState.errorText ? <div className="diary-panel__notice diary-panel__notice--error">{loadState.errorText}</div> : null}
        {loadState.loading ? <div className="diary-panel__empty">正在加载日记目录...</div> : null}

        {!loadState.loading && !loadState.errorText && dates.length === 0 ? (
          <div className="diary-panel__empty">暂时还没有日记记录。开启日记后，后续对话会自动生成。</div>
        ) : null}

        {!loadState.loading && dates.length > 0 ? (
          <div className="diary-panel__list">
            {dates.map((date) => (
              <button
                key={date}
                type="button"
                className={`diary-panel__item${selectedDate === date ? ' is-active' : ''}`}
                onClick={() => void openDiary(date)}
              >
                <span className="diary-panel__item-day">{date.slice(-2)}</span>
                <span className="diary-panel__item-copy">
                  <strong>{date}</strong>
                  <small>查看这一天的认知整理</small>
                </span>
              </button>
            ))}
          </div>
        ) : null}
      </section>

      <section className="diary-panel__content">
        <header className="diary-panel__header diary-panel__header--content">
          <div>
            <div className="diary-panel__eyebrow">详情</div>
            <h4 className="diary-panel__title">{selectedDate || '尚未选择日记'}</h4>
          </div>
          {selectedDate ? (
            <UiButton
              type="button"
              variant="secondary"
              className="diary-panel__action-btn"
              onClick={() => {
                setSelectedDate('');
                setContent('');
                setContentState({ loading: false, errorText: '' });
                pushStatus('已返回列表');
              }}
            >
              返回列表
            </UiButton>
          ) : null}
        </header>

        {contentState.errorText ? <div className="diary-panel__notice diary-panel__notice--error">{contentState.errorText}</div> : null}
        {contentState.loading ? <div className="diary-panel__empty">正在加载日记详情...</div> : null}

        {!contentState.loading && !content && !contentState.errorText ? (
          <div className="diary-panel__empty">从左侧选择一篇日记后，这里会显示完整内容。</div>
        ) : null}

        {!contentState.loading && content ? (
          <article className="diary-panel__article">
            {window.marked?.parse ? (
              <div className="diary-panel__markdown" dangerouslySetInnerHTML={{ __html: window.marked.parse(content) }} />
            ) : (
              <pre className="diary-panel__markdown">{content}</pre>
            )}
          </article>
        ) : null}
      </section>

      {statusText ? <div className="diary-panel__notice diary-panel__notice--status">{statusText}</div> : null}
    </div>
  );
}

import { useEffect, useState } from 'react';
import { emitShellUpdate } from '../bridge/openGuiclaw';
import { useWorkspaceShellBridge } from '../hooks/useWorkspaceShellBridge';

type IdentityFile = {
  name: string;
  type?: string;
  readonly?: boolean;
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
    // Ignore parse failures and use fallback below.
  }
  return fallback;
}

export function IdentityPanel() {
  const { snapshot } = useWorkspaceShellBridge();
  const [files, setFiles] = useState<IdentityFile[]>([]);
  const [activeFile, setActiveFile] = useState<string>('');
  const [fileContent, setFileContent] = useState('');
  const [isReadonly, setIsReadonly] = useState(false);
  const [loadState, setLoadState] = useState<LoadState>({ loading: true, errorText: '' });
  const [loadingFile, setLoadingFile] = useState(false);
  const [saving, setSaving] = useState(false);
  const [statusText, setStatusText] = useState('');

  useEffect(() => {
    if (!snapshot.showSettings || snapshot.settingsTab !== 'identity') return;
    void loadFiles();
  }, [snapshot.showSettings, snapshot.settingsTab]);

  function pushStatus(message: string) {
    setStatusText(message);
    window.clearTimeout((pushStatus as typeof pushStatus & { timer?: number }).timer);
    (pushStatus as typeof pushStatus & { timer?: number }).timer = window.setTimeout(() => {
      setStatusText('');
    }, 3200);
  }

  async function loadFiles(preferredFile?: string) {
    setLoadState({ loading: true, errorText: '' });
    try {
      const response = await fetch('/api/identity/files');
      if (!response.ok) {
        throw new Error(await readErrorMessage(response, '加载身份文件列表失败'));
      }

      const payload = await parseResponse(response);
      const nextFiles = Array.isArray(payload?.files) ? (payload.files as IdentityFile[]) : [];
      setFiles(nextFiles);
      setLoadState({ loading: false, errorText: '' });

      const target = preferredFile || activeFile || nextFiles[0]?.name || '';
      if (target) {
        await loadFile(target);
      } else {
        setActiveFile('');
        setFileContent('');
        setIsReadonly(false);
      }

      emitShellUpdate();
    } catch (error) {
      setFiles([]);
      setActiveFile('');
      setFileContent('');
      setIsReadonly(false);
      setLoadState({
        loading: false,
        errorText: error instanceof Error ? error.message : '加载身份文件列表失败'
      });
    }
  }

  async function loadFile(filename: string) {
    setLoadingFile(true);
    try {
      const response = await fetch(`/api/identity/file?filename=${encodeURIComponent(filename)}`);
      if (!response.ok) {
        throw new Error(await readErrorMessage(response, '加载身份文件失败'));
      }

      const payload = await parseResponse(response);
      setActiveFile(filename);
      setFileContent(typeof payload?.content === 'string' ? payload.content : '');
      setIsReadonly(!!payload?.readonly);
    } catch (error) {
      pushStatus(error instanceof Error ? error.message : '加载身份文件失败');
    } finally {
      setLoadingFile(false);
    }
  }

  async function saveFile() {
    if (!activeFile || isReadonly) return;

    setSaving(true);
    try {
      const response = await fetch('/api/identity/file', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ filename: activeFile, content: fileContent })
      });

      if (!response.ok) {
        throw new Error(await readErrorMessage(response, '保存身份文件失败'));
      }

      pushStatus('身份文件已保存');
      await loadFiles(activeFile);
    } catch (error) {
      pushStatus(error instanceof Error ? error.message : '保存身份文件失败');
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="identity-panel">
      <aside className="identity-panel__sidebar">
        <div className="identity-panel__sidebar-head">
          <div className="identity-panel__eyebrow">Identity Files</div>
          <h4 className="identity-panel__title">身份配置文件</h4>
          <p className="identity-panel__meta">维护角色设定、记忆摘要和只读快照。</p>
        </div>

        <button type="button" className="identity-panel__ghost-btn" onClick={() => loadFiles(activeFile)} disabled={loadState.loading}>
          刷新列表
        </button>

        {loadState.errorText ? <div className="identity-panel__notice identity-panel__notice--error">{loadState.errorText}</div> : null}
        {loadState.loading ? <div className="identity-panel__empty">正在加载身份文件...</div> : null}

        {!loadState.loading && files.length > 0 ? (
          <div className="identity-panel__file-list">
            {files.map((file) => (
              <button
                key={file.name}
                type="button"
                className={`identity-panel__file-btn${activeFile === file.name ? ' is-active' : ''}`}
                onClick={() => loadFile(file.name)}
              >
                <span className="identity-panel__file-name">{file.name}</span>
                {file.readonly ? <span className="identity-panel__readonly-pill">只读</span> : null}
              </button>
            ))}
          </div>
        ) : null}
      </aside>

      <section className="identity-panel__editor">
        <header className="identity-panel__editor-head">
          <div className="identity-panel__editor-meta">
            <div className="identity-panel__editor-label">当前文件</div>
            <div className="identity-panel__editor-name">{activeFile || '未选择文件'}</div>
          </div>

          <div className="identity-panel__editor-actions">
            {isReadonly ? <span className="identity-panel__readonly-banner">只读视图</span> : null}
            <button
              type="button"
              className="identity-panel__accent-btn"
              onClick={saveFile}
              disabled={!activeFile || saving || isReadonly}
            >
              {saving ? '保存中...' : isReadonly ? '只读' : '保存更改'}
            </button>
          </div>
        </header>

        <div className="identity-panel__editor-body">
          <textarea
            className="identity-panel__textarea"
            value={fileContent}
            disabled={!activeFile || isReadonly || loadingFile}
            onChange={(event) => setFileContent(event.target.value)}
            placeholder={loadingFile ? '正在加载文件内容...' : '文件内容...'}
            spellCheck={false}
          />
        </div>

        {statusText ? <div className="identity-panel__notice identity-panel__notice--status">{statusText}</div> : null}
      </section>
    </div>
  );
}

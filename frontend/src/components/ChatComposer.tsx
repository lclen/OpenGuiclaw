import { useEffect, useRef, useState } from 'react';
import { getHostApp, type ComposerCommand, type OpenGuiclawApp, waitForHostApp } from '../bridge/openGuiclaw';

type ComposerSnapshot = {
  inputText: string;
  stagedFiles: File[];
  showCommandMenu: boolean;
  filteredCommands: ComposerCommand[];
  commandSelectedIndex: number;
  isReceiving: boolean;
  workspaceName: string;
  threadTitle: string;
  contextDisplay: string;
  disableInput: boolean;
};

const EMPTY_SNAPSHOT: ComposerSnapshot = {
  inputText: '',
  stagedFiles: [],
  showCommandMenu: false,
  filteredCommands: [],
  commandSelectedIndex: 0,
  isReceiving: false,
  workspaceName: '',
  threadTitle: '',
  contextDisplay: '',
  disableInput: false
};

function snapshotComposer(app: OpenGuiclawApp): ComposerSnapshot {
  const currentThread = typeof app.getCurrentThread === 'function' ? app.getCurrentThread() : null;

  return {
    inputText: app.inputText || '',
    stagedFiles: Array.isArray(app.stagedFiles) ? [...app.stagedFiles] : [],
    showCommandMenu: !!app.showCommandMenu,
    filteredCommands: Array.isArray(app.filteredCommands)
      ? app.filteredCommands.map((command) => ({ ...command }))
      : [],
    commandSelectedIndex: Number.isFinite(app.commandSelectedIndex) ? app.commandSelectedIndex : 0,
    isReceiving: !!app.isReceiving,
    workspaceName: app.activeWorkspace?.name || '',
    threadTitle: currentThread?.title || '',
    contextDisplay: app.contextDisplay || '',
    disableInput: !!app.isReceiving && !app.currentController
  };
}

function dispatchChatUpdated() {
  window.dispatchEvent(new CustomEvent('openguiclaw:chat-updated'));
}

export function ChatComposer() {
  const [hostApp, setHostApp] = useState<OpenGuiclawApp | null>(getHostApp());
  const [composer, setComposer] = useState<ComposerSnapshot>(() =>
    hostApp ? snapshotComposer(hostApp) : EMPTY_SNAPSHOT
  );
  const [errorText, setErrorText] = useState('');
  const [isDragOver, setIsDragOver] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);

  useEffect(() => {
    let mounted = true;

    const syncFromHost = (app: OpenGuiclawApp) => {
      if (!mounted) return;
      setComposer(snapshotComposer(app));
    };

    waitForHostApp()
      .then((app) => {
        if (!mounted) return;
        setHostApp(app);
        syncFromHost(app);
      })
      .catch((error: Error) => {
        if (!mounted) return;
        setErrorText(error.message);
      });

    const handleChatUpdated = () => {
      const app = getHostApp();
      if (!app) return;
      setHostApp(app);
      syncFromHost(app);
    };

    window.addEventListener('openguiclaw:chat-updated', handleChatUpdated);
    return () => {
      mounted = false;
      window.removeEventListener('openguiclaw:chat-updated', handleChatUpdated);
    };
  }, []);

  useEffect(() => {
    const textarea = textareaRef.current;
    if (!textarea) return;
    textarea.style.height = 'auto';
    textarea.style.height = `${Math.min(textarea.scrollHeight, 120)}px`;
  }, [composer.inputText]);

  function syncNow() {
    const app = getHostApp();
    if (!app) return;
    setHostApp(app);
    setComposer(snapshotComposer(app));
  }

  function handleInputChange(event: React.ChangeEvent<HTMLTextAreaElement>) {
    if (!hostApp) return;
    hostApp.inputText = event.target.value;
    hostApp.handleInput?.(event.nativeEvent as Event);
    syncNow();
  }

  function handleKeyDown(event: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (!hostApp) return;

    if (event.key === 'ArrowUp' && composer.showCommandMenu && composer.filteredCommands.length > 0) {
      event.preventDefault();
      hostApp.navigateCommand?.(-1, event.nativeEvent as KeyboardEvent);
      syncNow();
      return;
    }

    if (event.key === 'ArrowDown' && composer.showCommandMenu && composer.filteredCommands.length > 0) {
      event.preventDefault();
      hostApp.navigateCommand?.(1, event.nativeEvent as KeyboardEvent);
      syncNow();
      return;
    }

    if (event.key === 'Escape') {
      hostApp.showCommandMenu = false;
      syncNow();
      return;
    }

    if (event.key !== 'Enter' || event.shiftKey) return;

    event.preventDefault();

    if (composer.showCommandMenu && composer.filteredCommands.length > 0) {
      const command = composer.filteredCommands[composer.commandSelectedIndex] || composer.filteredCommands[0];
      if (command) {
        hostApp.selectCommand?.(command);
        syncNow();
        dispatchChatUpdated();
      }
      return;
    }

    if (composer.isReceiving) {
      hostApp.abortReceiving?.();
      syncNow();
      return;
    }

    hostApp.sendMessage?.();
    syncNow();
  }

  async function handleDrop(event: React.DragEvent<HTMLDivElement>) {
    if (!hostApp) return;
    setIsDragOver(false);
    await hostApp.handleDrop?.(event.nativeEvent as DragEvent);
    syncNow();
  }

  function handlePaste(event: React.ClipboardEvent<HTMLDivElement>) {
    if (!hostApp) return;
    hostApp.handlePaste?.(event.nativeEvent as ClipboardEvent);
    syncNow();
  }

  function handleFileSelection(event: React.ChangeEvent<HTMLInputElement>) {
    if (!hostApp) return;
    hostApp.handleFileSelect?.({ target: event.target } as { target: HTMLInputElement });
    syncNow();
  }

  function handleCommandClick(command: ComposerCommand) {
    if (!hostApp) return;
    hostApp.selectCommand?.(command);
    syncNow();
    dispatchChatUpdated();
    window.requestAnimationFrame(() => {
      const textarea = textareaRef.current;
      if (!textarea) return;
      textarea.focus();
      textarea.setSelectionRange(textarea.value.length, textarea.value.length);
    });
  }

  function handleRemoveFile(index: number) {
    hostApp?.removeStagedFile?.(index);
    syncNow();
  }

  function handlePrimaryAction() {
    if (!hostApp) return;
    if (composer.isReceiving) {
      hostApp.abortReceiving?.();
    } else {
      hostApp.sendMessage?.();
    }
    syncNow();
  }

  const isReady = !!composer.inputText.trim() || composer.stagedFiles.length > 0;

  return (
    <>
      {errorText ? <div className="chat-react-error">{errorText}</div> : null}

      <div
        className="chat-composer-card"
        style={isDragOver ? { borderColor: 'rgba(182,240,89,0.6)', background: 'rgba(182,240,89,0.05)' } : undefined}
        onDragOver={(event) => {
          event.preventDefault();
          setIsDragOver(true);
        }}
        onDragLeave={(event) => {
          event.preventDefault();
          setIsDragOver(false);
        }}
        onDrop={handleDrop}
        onPaste={handlePaste}
      >
        {composer.showCommandMenu && composer.filteredCommands.length > 0 ? (
          <div className="composer-command-menu">
            {composer.filteredCommands.map((command, index) => (
              <button
                key={command.command}
                type="button"
                className={`composer-command-item ${index === composer.commandSelectedIndex ? 'is-active' : ''}`}
                onClick={() => handleCommandClick(command)}
              >
                <span className="composer-command-icon">{command.icon || '/'}</span>
                <span className="composer-command-copy">
                  <span className="composer-command-name">{command.command}</span>
                  <span className="composer-command-desc">{command.desc || ''}</span>
                </span>
              </button>
            ))}
          </div>
        ) : null}

        {isDragOver ? (
          <div className="composer-drop-overlay">
            <span className="composer-drop-copy">Drop files to stage them</span>
          </div>
        ) : null}

        {composer.stagedFiles.length > 0 ? (
          <div className="composer-staged-files">
            {composer.stagedFiles.map((file, index) => (
              <div className="staged-file-chip" key={`${file.name}-${index}`}>
                <svg width="11" height="11" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth="2"
                    d="M15.172 7l-6.586 6.586a2 2 0 102.828 2.828l6.414-6.586a4 4 0 00-5.656-5.656l-6.415 6.585a6 6 0 108.486 8.486L20.5 13"
                  />
                </svg>
                <span className="staged-file-chip-name">{file.name}</span>
                <button type="button" className="staged-file-chip-remove" onClick={() => handleRemoveFile(index)}>
                  x
                </button>
              </div>
            ))}
          </div>
        ) : null}

        <div className="composer-main-row">
          <div className="composer-leading">
            <label className="composer-attach-button" title="Add files">
              <svg width="16" height="16" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth="2"
                  d="M15.172 7l-6.586 6.586a2 2 0 102.828 2.828l6.414-6.586a4 4 0 00-5.656-5.656l-6.415 6.585a6 6 0 108.486 8.486L20.5 13"
                />
              </svg>
              <input type="file" multiple style={{ display: 'none' }} onChange={handleFileSelection} />
            </label>
          </div>

          <textarea
            ref={textareaRef}
            value={composer.inputText}
            className="composer-textarea"
            onChange={handleInputChange}
            onKeyDown={handleKeyDown}
            placeholder="Ask openGuiclaw, or type / for commands"
            rows={1}
            disabled={composer.disableInput}
          />

          <button
            type="button"
            onClick={handlePrimaryAction}
            className={`composer-send-button ${composer.isReceiving ? 'is-abort' : isReady ? 'is-ready' : ''}`}
            disabled={!composer.isReceiving && !isReady}
            aria-label={composer.isReceiving ? 'Stop response' : 'Send message'}
          >
            {composer.isReceiving ? (
              <svg width="14" height="14" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <rect x="6" y="6" width="12" height="12" rx="2" strokeWidth="2.5" />
              </svg>
            ) : (
              <svg width="14" height="14" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M12 19V5m-7 7l7-7 7 7" />
              </svg>
            )}
          </button>
        </div>

        <div className="composer-meta-row">
          <div className="composer-meta-left">
            <span className="composer-meta-chip">{composer.workspaceName || 'No workspace selected'}</span>
            {composer.threadTitle ? <span className="composer-meta-chip">{composer.threadTitle}</span> : null}
          </div>
          <div className="composer-meta-right">
            <span className="composer-meta-text">Enter sends</span>
            <span className="composer-meta-text">Shift+Enter inserts a line break</span>
            {composer.contextDisplay ? <span className="composer-meta-text">{composer.contextDisplay}</span> : null}
          </div>
        </div>
      </div>
    </>
  );
}

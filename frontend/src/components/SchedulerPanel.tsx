import { useState } from 'react';
import { type OpenGuiclawApp, type SchedulerTask } from '../bridge/openGuiclaw';
import { useHostCollection } from '../hooks/useHostCollection';

function snapshotTasks(app: OpenGuiclawApp): SchedulerTask[] {
  return Array.isArray(app.schedulerTasks) ? app.schedulerTasks.map((task) => ({ ...task })) : [];
}

function formatTaskType(taskType?: string) {
  if (taskType === 'task') return 'AI task';
  if (taskType === 'reminder') return 'Reminder';
  if (taskType === 'system') return 'System';
  return taskType || 'Unknown';
}

function formatDateTime(value?: string | null) {
  if (!value) return 'Not scheduled';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

export function SchedulerPanel() {
  const {
    hostApp,
    items: tasks,
    setItems: setTasks,
    loading,
    errorText,
    setErrorText
  } = useHostCollection<SchedulerTask>({
    eventName: 'openguiclaw:scheduler-updated',
    load: (app) => app.loadSchedulerTasks(),
    snapshot: snapshotTasks
  });
  const [busyTaskId, setBusyTaskId] = useState<string | null>(null);
  const [reloadBusy, setReloadBusy] = useState(false);

  const runningCount = tasks.filter((task) => task.status === 'running').length;

  async function handleRefresh() {
    if (!hostApp) return;
    setReloadBusy(true);
    setErrorText('');
    try {
      await hostApp.loadSchedulerTasks();
      setTasks(snapshotTasks(hostApp));
    } catch (error) {
      setErrorText(error instanceof Error ? error.message : 'Failed to refresh tasks');
    } finally {
      setReloadBusy(false);
    }
  }

  async function runTaskAction(taskId: string, action: () => Promise<void>) {
    setBusyTaskId(taskId);
    setErrorText('');
    try {
      await action();
      if (hostApp) {
        setTasks(snapshotTasks(hostApp));
      }
    } catch (error) {
      setErrorText(error instanceof Error ? error.message : 'Task action failed');
    } finally {
      setBusyTaskId(null);
    }
  }

  return (
    <section className="react-scheduler-panel">
      <header className="react-scheduler-panel__header">
        <div>
          <div className="react-scheduler-panel__eyebrow">React Pilot</div>
          <h3 className="react-scheduler-panel__title">Automation</h3>
          <p className="react-scheduler-panel__meta">
            <span>{tasks.length} tasks</span>
            <span className="react-scheduler-panel__meta-divider">/</span>
            <span>{runningCount} running</span>
          </p>
        </div>

        <div className="react-scheduler-panel__actions">
          <button
            type="button"
            className="react-scheduler-panel__secondary"
            onClick={handleRefresh}
            disabled={!hostApp || reloadBusy}
          >
            {reloadBusy ? 'Refreshing...' : 'Refresh'}
          </button>
          <button
            type="button"
            className="react-scheduler-panel__primary"
            onClick={() => hostApp?.openSchedulerForm()}
            disabled={!hostApp}
          >
            New Plan
          </button>
        </div>
      </header>

      {errorText ? <div className="react-scheduler-panel__error">{errorText}</div> : null}

      {loading ? <div className="react-scheduler-panel__empty">Loading automation tasks...</div> : null}

      {!loading && tasks.length === 0 ? (
        <div className="react-scheduler-panel__empty">No automation plans yet.</div>
      ) : null}

      {!loading && tasks.length > 0 ? (
        <div className="react-scheduler-panel__content">
          {tasks.map((task) => {
            const isBusy = busyTaskId === task.id;
            return (
              <article className="react-scheduler-card" key={task.id}>
                <div className="react-scheduler-card__row">
                  <div className="react-scheduler-card__main">
                    <div className="react-scheduler-card__heading">
                      <h4 className="react-scheduler-card__name">{task.name}</h4>
                      <span className={`react-scheduler-card__pill ${task.enabled ? 'is-on' : 'is-off'}`}>
                        {task.enabled ? 'enabled' : 'paused'}
                      </span>
                      {task.status === 'running' ? (
                        <span className="react-scheduler-card__pill is-running">running</span>
                      ) : null}
                      <span className="react-scheduler-card__type">{formatTaskType(task.task_type)}</span>
                    </div>
                    <p className="react-scheduler-card__description">
                      {task.description || 'No description provided.'}
                    </p>
                  </div>

                  <div className="react-scheduler-card__actions">
                    <button
                      type="button"
                      className={`react-scheduler-card__toggle ${task.enabled ? 'is-on' : 'is-off'}`}
                      onClick={() => runTaskAction(task.id, () => hostApp!.toggleSchedulerTask(task.id, !task.enabled))}
                      disabled={!hostApp || isBusy}
                    >
                      {isBusy ? '...' : task.enabled ? 'Pause' : 'Resume'}
                    </button>
                    <button
                      type="button"
                      className="react-scheduler-card__icon-btn"
                      onClick={() => runTaskAction(task.id, () => hostApp!.triggerSchedulerTask(task.id))}
                      disabled={!hostApp || isBusy}
                    >
                      Run
                    </button>
                    {task.deletable !== false && task.task_type !== 'system' ? (
                      <button
                        type="button"
                        className="react-scheduler-card__icon-btn"
                        onClick={() => hostApp?.editSchedulerTask(task)}
                        disabled={!hostApp || isBusy}
                      >
                        Edit
                      </button>
                    ) : null}
                    {task.deletable !== false && task.task_type !== 'system' ? (
                      <button
                        type="button"
                        className="react-scheduler-card__icon-btn is-danger"
                        onClick={() => runTaskAction(task.id, () => hostApp!.deleteSchedulerTask(task.id))}
                        disabled={!hostApp || isBusy}
                      >
                        Delete
                      </button>
                    ) : null}
                  </div>
                </div>

                <div className="react-scheduler-card__meta">
                  <div className="react-scheduler-card__meta-item">
                    <span className="react-scheduler-card__meta-label">Last run</span>
                    <span className="react-scheduler-card__meta-value">{formatDateTime(task.last_run)}</span>
                  </div>
                  <div className="react-scheduler-card__meta-item">
                    <span className="react-scheduler-card__meta-label">Next run</span>
                    <span className="react-scheduler-card__meta-value is-accent">{formatDateTime(task.next_run)}</span>
                  </div>
                </div>
              </article>
            );
          })}
        </div>
      ) : null}
    </section>
  );
}

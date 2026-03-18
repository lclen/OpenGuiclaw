import { useState } from 'react';
import { type OpenGuiclawApp, type SchedulerTask } from '../bridge/openGuiclaw';
import { useHostCollection } from '../hooks/useHostCollection';

function snapshotTasks(app: OpenGuiclawApp): SchedulerTask[] {
  return Array.isArray(app.schedulerTasks) ? app.schedulerTasks.map((task) => ({ ...task })) : [];
}

function formatTaskType(taskType?: string) {
  if (taskType === 'task') return 'AI 任务';
  if (taskType === 'reminder') return '提醒';
  if (taskType === 'system') return '系统';
  return taskType || '未知';
}

function formatDateTime(value?: string | null) {
  if (!value) return '未安排';
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
      setErrorText(error instanceof Error ? error.message : '刷新任务失败');
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
      setErrorText(error instanceof Error ? error.message : '任务操作失败');
    } finally {
      setBusyTaskId(null);
    }
  }

  return (
    <section className="react-scheduler-panel">
      <header className="react-scheduler-panel__header">
        <div>
          <div className="react-scheduler-panel__eyebrow">自动化</div>
          <h3 className="react-scheduler-panel__title">计划任务</h3>
          <p className="react-scheduler-panel__meta">
            <span>{tasks.length} 个任务</span>
            <span className="react-scheduler-panel__meta-divider">/</span>
            <span>{runningCount} 运行中</span>
          </p>
        </div>

        <div className="react-scheduler-panel__actions">
          <button
            type="button"
            className="react-scheduler-panel__secondary"
            onClick={handleRefresh}
            disabled={!hostApp || reloadBusy}
          >
            {reloadBusy ? '刷新中...' : '刷新'}
          </button>
          <button
            type="button"
            className="react-scheduler-panel__primary"
            onClick={() => hostApp?.openSchedulerForm()}
            disabled={!hostApp}
          >
            新建计划
          </button>
        </div>
      </header>

      {errorText ? <div className="react-scheduler-panel__error">{errorText}</div> : null}

      {loading ? <div className="react-scheduler-panel__empty">加载自动化任务中...</div> : null}

      {!loading && tasks.length === 0 ? (
        <div className="react-scheduler-panel__empty">暂无自动化计划。</div>
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
                        {task.enabled ? '已启用' : '已暂停'}
                      </span>
                      {task.status === 'running' ? (
                        <span className="react-scheduler-card__pill is-running">运行中</span>
                      ) : null}
                      <span className="react-scheduler-card__type">{formatTaskType(task.task_type)}</span>
                    </div>
                    <p className="react-scheduler-card__description">
                      {task.description || '暂无描述。'}
                    </p>
                  </div>

                  <div className="react-scheduler-card__actions">
                    <button
                      type="button"
                      className={`react-scheduler-card__toggle ${task.enabled ? 'is-on' : 'is-off'}`}
                      onClick={() => runTaskAction(task.id, () => hostApp!.toggleSchedulerTask(task.id, !task.enabled))}
                      disabled={!hostApp || isBusy}
                    >
                      {isBusy ? '...' : task.enabled ? '暂停' : '恢复'}
                    </button>
                    <button
                      type="button"
                      className="react-scheduler-card__icon-btn"
                      onClick={() => runTaskAction(task.id, () => hostApp!.triggerSchedulerTask(task.id))}
                      disabled={!hostApp || isBusy}
                    >
                      运行
                    </button>
                    {task.deletable !== false && task.task_type !== 'system' ? (
                      <button
                        type="button"
                        className="react-scheduler-card__icon-btn"
                        onClick={() => hostApp?.editSchedulerTask(task)}
                        disabled={!hostApp || isBusy}
                      >
                        编辑
                      </button>
                    ) : null}
                    {task.deletable !== false && task.task_type !== 'system' ? (
                      <button
                        type="button"
                        className="react-scheduler-card__icon-btn is-danger"
                        onClick={() => runTaskAction(task.id, () => hostApp!.deleteSchedulerTask(task.id))}
                        disabled={!hostApp || isBusy}
                      >
                        删除
                      </button>
                    ) : null}
                  </div>
                </div>

                <div className="react-scheduler-card__meta">
                  <div className="react-scheduler-card__meta-item">
                    <span className="react-scheduler-card__meta-label">上次运行</span>
                    <span className="react-scheduler-card__meta-value">{formatDateTime(task.last_run)}</span>
                  </div>
                  <div className="react-scheduler-card__meta-item">
                    <span className="react-scheduler-card__meta-label">下次运行</span>
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

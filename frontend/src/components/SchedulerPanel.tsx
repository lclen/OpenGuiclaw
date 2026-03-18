import { useMemo, useState } from 'react';
import { type OpenGuiclawApp, type SchedulerExecution, type SchedulerTask } from '../bridge/openGuiclaw';
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

function formatExecutionStatus(status?: string) {
  if (status === 'running') return '执行中';
  if (status === 'success') return '成功';
  if (status === 'failed') return '失败';
  return status || '未知';
}

function formatExecutionStatusClass(status?: string) {
  if (status === 'running') return 'react-scheduler-card__pill is-running';
  if (status === 'success') return 'react-scheduler-card__pill is-on';
  if (status === 'failed') return 'react-scheduler-card__pill is-danger';
  return 'react-scheduler-card__pill';
}

function getDeliveryTargets(item: SchedulerTask | SchedulerExecution) {
  if (Array.isArray(item.delivery_targets) && item.delivery_targets.length > 0) {
    return item.delivery_targets;
  }
  return [{
    kind: item.target_kind || 'workspace_inbox',
    workspace_id: item.target_workspace_id || undefined,
    session_id: item.target_session_id || undefined,
    channel: item.target_channel || undefined,
    chat_id: item.target_chat_id || undefined,
  }];
}

function formatTargetSummary(item: SchedulerTask | SchedulerExecution) {
  return getDeliveryTargets(item).map((target) => {
    if (target.kind === 'desktop_session' && target.session_id) {
      return `桌面对话 · ${target.session_id}`;
    }
    if (target.kind === 'im_session') {
      const channel = target.channel || 'im';
      const chatId = target.chat_id || target.session_id || 'unknown';
      return `IM 会话 · ${channel}/${chatId}`;
    }
    return `工作区收件箱 · ${target.workspace_id || '默认工作区'}`;
  }).join(' / ');
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
    load: (app) => app.refreshSchedulerData?.() ?? app.loadSchedulerTasks(),
    snapshot: snapshotTasks
  });
  const [busyTaskId, setBusyTaskId] = useState<string | null>(null);
  const [reloadBusy, setReloadBusy] = useState(false);
  const [viewTab, setViewTab] = useState<'tasks' | 'executions'>('tasks');

  const runningCount = tasks.filter((task) => task.status === 'running').length;
  const executions = useMemo(
    () => (Array.isArray(hostApp?.schedulerExecutions) ? hostApp!.schedulerExecutions.map((item) => ({ ...item })) : []),
    [hostApp?.schedulerExecutions]
  );
  const taskNameMap = useMemo(
    () => new Map(tasks.map((task) => [task.id, task.name])),
    [tasks]
  );

  async function handleRefresh() {
    if (!hostApp) return;
    setReloadBusy(true);
    setErrorText('');
    try {
      await (hostApp.refreshSchedulerData?.() ?? hostApp.loadSchedulerTasks());
      setTasks(snapshotTasks(hostApp));
    } catch (error) {
      setErrorText(error instanceof Error ? error.message : '刷新任务失败');
    } finally {
      setReloadBusy(false);
    }
  }

  async function runTaskAction(taskId: string, action: () => Promise<void>, nextTab?: 'tasks' | 'executions') {
    setBusyTaskId(taskId);
    setErrorText('');
    try {
      await action();
      if (nextTab) setViewTab(nextTab);
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

      <div className="react-scheduler-panel__tabbar">
        <button
          type="button"
          className={`react-scheduler-panel__tab ${viewTab === 'tasks' ? 'is-active' : ''}`}
          onClick={() => setViewTab('tasks')}
        >
          任务列表
        </button>
        <button
          type="button"
          className={`react-scheduler-panel__tab ${viewTab === 'executions' ? 'is-active' : ''}`}
          onClick={() => setViewTab('executions')}
        >
          执行历史
        </button>
      </div>

      {errorText ? <div className="react-scheduler-panel__error">{errorText}</div> : null}

      {loading ? <div className="react-scheduler-panel__empty">加载自动化任务中...</div> : null}

      {!loading && viewTab === 'tasks' && tasks.length === 0 ? (
        <div className="react-scheduler-panel__empty">暂无自动化计划。</div>
      ) : null}

      {!loading && viewTab === 'executions' && executions.length === 0 ? (
        <div className="react-scheduler-panel__empty">暂无执行记录。</div>
      ) : null}

      {!loading && viewTab === 'tasks' && tasks.length > 0 ? (
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
                      onClick={() => runTaskAction(task.id, () => hostApp!.triggerSchedulerTask(task.id), 'executions')}
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

                <div className="react-scheduler-card__meta react-scheduler-card__meta--single">
                  <div className="react-scheduler-card__meta-item">
                    <span className="react-scheduler-card__meta-label">投递目标</span>
                    <span className="react-scheduler-card__meta-value">{formatTargetSummary(task)}</span>
                  </div>
                </div>
              </article>
            );
          })}
        </div>
      ) : null}

      {!loading && viewTab === 'executions' && executions.length > 0 ? (
        <div className="react-scheduler-panel__content">
          {executions.map((execution) => (
            <article className="react-scheduler-card" key={execution.id}>
              <div className="react-scheduler-card__row">
                <div className="react-scheduler-card__main">
                  <div className="react-scheduler-card__heading">
                    <h4 className="react-scheduler-card__name">{taskNameMap.get(execution.task_id) || execution.task_id}</h4>
                    <span className={formatExecutionStatusClass(execution.status)}>
                      {formatExecutionStatus(execution.status)}
                    </span>
                    <span className="react-scheduler-card__type">{execution.trigger_source || 'scheduler'}</span>
                  </div>
                  <p className="react-scheduler-card__description">
                    {execution.result_summary || execution.error || '暂无摘要。'}
                  </p>
                </div>
                <div className="react-scheduler-card__actions">
                  <span className="react-scheduler-card__meta-label">ID</span>
                  <span className="react-scheduler-card__meta-value">{execution.id}</span>
                </div>
              </div>

              <div className="react-scheduler-card__meta">
                <div className="react-scheduler-card__meta-item">
                  <span className="react-scheduler-card__meta-label">开始时间</span>
                  <span className="react-scheduler-card__meta-value">{formatDateTime(execution.started_at)}</span>
                </div>
                <div className="react-scheduler-card__meta-item">
                  <span className="react-scheduler-card__meta-label">结束时间</span>
                  <span className="react-scheduler-card__meta-value is-accent">{formatDateTime(execution.finished_at)}</span>
                </div>
              </div>

              <div className="react-scheduler-card__meta react-scheduler-card__meta--single">
                <div className="react-scheduler-card__meta-item">
                  <span className="react-scheduler-card__meta-label">投递目标</span>
                  <span className="react-scheduler-card__meta-value">{formatTargetSummary(execution)}</span>
                </div>
              </div>
            </article>
          ))}
        </div>
      ) : null}
    </section>
  );
}

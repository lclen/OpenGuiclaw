import { useEffect, useMemo, useState } from 'react';
import { useWorkspaceShellBridge } from '../hooks/useWorkspaceShellBridge';
import { PlatformLogo } from './icons/PlatformLogos';

type PlatformId = 'telegram' | 'feishu' | 'dingtalk' | 'wework' | 'wechat' | 'qqbot' | 'onebot';

type HealthStatus = {
  status: string;
  error?: string | null;
  checked_at?: string | null;
};

type IMBot = {
  id: string;
  name: string;
  platform: Extract<PlatformId, 'telegram' | 'feishu' | 'dingtalk'>;
  enabled: boolean;
  credentials: Record<string, string | boolean>;
  last_health?: HealthStatus | null;
};

type PlatformOption = {
  id: PlatformId;
  title: string;
  subtitle: string;
  accent: string;
  supported: boolean;
};

type BotDraft = {
  originalId: string | null;
  id: string;
  name: string;
  platform: Extract<PlatformId, 'telegram' | 'feishu' | 'dingtalk'>;
  enabled: boolean;
  credentials: Record<string, string | boolean>;
};

type WizardStep = 'platform' | 'basic' | 'credentials' | 'extra' | 'test' | 'done';

type LoadState = {
  loading: boolean;
  errorText: string;
};

const PLATFORM_OPTIONS: PlatformOption[] = [
  { id: 'telegram', title: 'Telegram', subtitle: 'BotFather 机器人接入', accent: 'is-telegram', supported: true },
  { id: 'feishu', title: '飞书 / Lark', subtitle: '自建应用消息通道', accent: 'is-feishu', supported: true },
  { id: 'dingtalk', title: '钉钉', subtitle: '企业内部机器人 / Stream', accent: 'is-dingtalk', supported: true },
  { id: 'wework', title: '企业微信', subtitle: '即将支持', accent: 'is-muted', supported: false },
  { id: 'wechat', title: '微信', subtitle: '即将支持', accent: 'is-muted', supported: false },
  { id: 'qqbot', title: 'QQ Bot', subtitle: '即将支持', accent: 'is-muted', supported: false },
  { id: 'onebot', title: 'OneBot', subtitle: '即将支持', accent: 'is-muted', supported: false },
];

const PLATFORM_FIELDS: Record<Extract<PlatformId, 'telegram' | 'feishu' | 'dingtalk'>, Array<{ key: string; label: string; placeholder: string; secret?: boolean; hint?: string }>> = {
  telegram: [
    { key: 'bot_token', label: 'Bot Token', placeholder: '123456:ABC-DEF1234...', secret: true, hint: 'TELEGRAM_BOT_TOKEN' },
    { key: 'proxy', label: 'Proxy URL', placeholder: 'http://127.0.0.1:7890', hint: 'TELEGRAM_PROXY' },
    { key: 'pairing_code', label: '配对码', placeholder: '可选，6 位数字', hint: 'TELEGRAM_PAIRING_CODE' },
    { key: 'webhook_url', label: 'Webhook URL', placeholder: 'https://example.com/webhook', hint: 'TELEGRAM_WEBHOOK_URL' }
  ],
  feishu: [
    { key: 'app_id', label: 'App ID', placeholder: 'cli_xxx', hint: 'FEISHU_APP_ID' },
    { key: 'app_secret', label: 'App Secret', placeholder: 'Secret', secret: true, hint: 'FEISHU_APP_SECRET' },
    { key: 'verification_token', label: 'Verification Token', placeholder: 'Webhook 验证 token', hint: 'FEISHU_VERIFICATION_TOKEN' },
    { key: 'encrypt_key', label: 'Encrypt Key', placeholder: '事件加密 key（可选）', secret: true, hint: 'FEISHU_ENCRYPT_KEY' }
  ],
  dingtalk: [
    { key: 'client_id', label: 'Client ID / App Key', placeholder: 'dingxxxx', hint: 'DINGTALK_CLIENT_ID' },
    { key: 'client_secret', label: 'Client Secret / App Secret', placeholder: 'Secret', secret: true, hint: 'DINGTALK_CLIENT_SECRET' },
    { key: 'agent_id', label: 'Agent ID', placeholder: '可选，用于发送消息', hint: 'DINGTALK_AGENT_ID' }
  ]
};

const REQUIRED_FIELDS: Record<Extract<PlatformId, 'telegram' | 'feishu' | 'dingtalk'>, string[]> = {
  telegram: ['bot_token'],
  feishu: ['app_id', 'app_secret'],
  dingtalk: ['client_id', 'client_secret']
};

const STEP_LABELS: Record<WizardStep, string> = {
  platform: '平台',
  basic: '基本信息',
  credentials: '凭据',
  extra: '额外配置',
  test: '测活',
  done: '完成'
};

function getStepOrder(platform: Extract<PlatformId, 'telegram' | 'feishu' | 'dingtalk'>): WizardStep[] {
  return platform === 'dingtalk'
    ? ['platform', 'basic', 'credentials', 'extra', 'test', 'done']
    : ['platform', 'basic', 'credentials', 'test', 'done'];
}

function emptyCredentials(platform: Extract<PlatformId, 'telegram' | 'feishu' | 'dingtalk'>): Record<string, string | boolean> {
  const base = PLATFORM_FIELDS[platform].reduce<Record<string, string | boolean>>((accumulator, field) => {
    accumulator[field.key] = '';
    return accumulator;
  }, {});
  if (platform === 'dingtalk') {
    base.footer_elapsed = true;
    base.footer_status = true;
  }
  return base;
}

function buildDefaultDraft(platform: Extract<PlatformId, 'telegram' | 'feishu' | 'dingtalk'>): BotDraft {
  return {
    originalId: null,
    id: `${platform}-${Math.random().toString(36).slice(2, 7)}`,
    name: `${PLATFORM_OPTIONS.find((item) => item.id === platform)?.title ?? platform} #${Math.floor(Math.random() * 90) + 10}`,
    platform,
    enabled: true,
    credentials: emptyCredentials(platform)
  };
}

function normalizeHealth(result?: HealthStatus | null) {
  if (!result) return null;
  return {
    status: result.status || 'unknown',
    error: result.error || null,
    checked_at: result.checked_at || null
  };
}

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

function formatCheckTime(value?: string | null) {
  if (!value) return '未检测';
  return value.replace('T', ' ');
}

function healthTone(result?: HealthStatus | null) {
  if (!result) return 'is-idle';
  if (result.status === 'healthy') return 'is-healthy';
  if (result.status === 'unhealthy') return 'is-error';
  return 'is-idle';
}

function boolCredential(value: string | boolean | undefined, fallback = false) {
  if (typeof value === 'boolean') return value;
  if (typeof value === 'string') {
    const normalized = value.trim().toLowerCase();
    if (normalized === 'true') return true;
    if (normalized === 'false') return false;
  }
  return fallback;
}

function RestartBanner({
  visible,
  restarting,
  onRestart,
  onDismiss
}: {
  visible: boolean;
  restarting: boolean;
  onRestart: () => Promise<void>;
  onDismiss: () => void;
}) {
  if (!visible) return null;
  return (
    <div className="integrations-restart-banner">
      <div>
        <div className="integrations-restart-banner__title">已保存，重启后生效</div>
        <div className="integrations-restart-banner__desc">IM Bot 的创建、编辑、启停和删除都会在后端重启后正式加载到通道网关。</div>
      </div>
      <div className="integrations-restart-banner__actions">
        <button type="button" className="integrations-panel__ghost-btn" onClick={onDismiss}>
          稍后处理
        </button>
        <button type="button" className="integrations-panel__accent-btn" onClick={() => void onRestart()} disabled={restarting}>
          {restarting ? '重启中...' : '立即重启'}
        </button>
      </div>
    </div>
  );
}

function PlatformGallery({ onCreate }: { onCreate: (platform: Extract<PlatformId, 'telegram' | 'feishu' | 'dingtalk'>) => void }) {
  return (
    <section className="integrations-section">
      <div className="integrations-section__head">
        <div>
          <div className="integrations-section__eyebrow">Platform Gallery</div>
          <h5 className="integrations-section__title">选择通道平台</h5>
          <p className="integrations-section__desc">先选平台，再进入类似 OpenAkita 的引导创建流程。当前首版支持 Telegram、飞书、钉钉。</p>
        </div>
      </div>
      <div className="integrations-platform-grid">
        {PLATFORM_OPTIONS.map((platform) => (
          <button
            key={platform.id}
            type="button"
            className={`integrations-platform-card ${platform.accent}${platform.supported ? '' : ' is-disabled'}`}
            onClick={() => platform.supported && onCreate(platform.id as Extract<PlatformId, 'telegram' | 'feishu' | 'dingtalk'>)}
            disabled={!platform.supported}
          >
            <span className="integrations-platform-card__icon">
              <PlatformLogo platform={platform.id} />
            </span>
            <span className="integrations-platform-card__title">{platform.title}</span>
            <span className="integrations-platform-card__subtitle">{platform.subtitle}</span>
            <span className="integrations-platform-card__badge">{platform.supported ? '可创建' : '即将支持'}</span>
          </button>
        ))}
      </div>
    </section>
  );
}

function BotRegistry({
  bots,
  onCreate,
  onEdit,
  onDelete,
  onToggle,
  onTest
}: {
  bots: IMBot[];
  onCreate: (platform: Extract<PlatformId, 'telegram' | 'feishu' | 'dingtalk'>) => void;
  onEdit: (bot: IMBot) => void;
  onDelete: (bot: IMBot) => Promise<void>;
  onToggle: (bot: IMBot) => Promise<void>;
  onTest: (bot: IMBot) => Promise<void>;
}) {
  const grouped = useMemo(() => {
    return (['telegram', 'feishu', 'dingtalk'] as const).map((platform) => ({
      platform,
      title: PLATFORM_OPTIONS.find((item) => item.id === platform)?.title ?? platform,
      bots: bots.filter((bot) => bot.platform === platform)
    }));
  }, [bots]);

  return (
    <section className="integrations-section">
      <div className="integrations-section__head">
        <div>
          <div className="integrations-section__eyebrow">Bot Registry</div>
          <h5 className="integrations-section__title">Bot 注册表</h5>
          <p className="integrations-section__desc">按平台查看实例状态、最近测活结果，并进入编辑或高级模式。</p>
        </div>
      </div>

      {bots.length === 0 ? (
        <div className="integrations-empty-state">
          <div className="integrations-empty-state__icon">＋</div>
          <div className="integrations-empty-state__title">还没有任何 IM Bot</div>
          <div className="integrations-empty-state__desc">从上方平台画廊选择一个平台，进入引导创建，保存后即可等待重启生效。</div>
        </div>
      ) : (
        <div className="integrations-registry">
          {grouped.map((group) => (
            <div key={group.platform} className="integrations-registry__group">
              <div className="integrations-registry__group-head">
                <div>
                  <h6>{group.title}</h6>
                  <p>{group.bots.length > 0 ? `共 ${group.bots.length} 个实例` : '暂未创建实例'}</p>
                </div>
                <button type="button" className="integrations-panel__ghost-btn" onClick={() => onCreate(group.platform)}>
                  新建 {group.title}
                </button>
              </div>
              {group.bots.length > 0 ? (
                <div className="integrations-bot-grid">
                  {group.bots.map((bot) => (
                    <article key={bot.id} className={`integrations-bot-card ${bot.enabled ? '' : 'is-disabled'}`}>
                      <div className="integrations-bot-card__top">
                        <div>
                          <div className="integrations-bot-card__name">{bot.name}</div>
                          <div className="integrations-bot-card__meta">{bot.id}</div>
                        </div>
                        <span className={`integrations-status-pill ${bot.enabled ? 'is-online' : 'is-muted'}`}>
                          {bot.enabled ? '已启用' : '已停用'}
                        </span>
                      </div>
                      <div className="integrations-bot-card__health">
                        <span className={`integrations-health-pill ${healthTone(bot.last_health)}`}>
                          {bot.last_health?.status === 'healthy' ? '验证成功' : bot.last_health?.status === 'unhealthy' ? '验证失败' : '未检测'}
                        </span>
                        <span className="integrations-bot-card__checked">{formatCheckTime(bot.last_health?.checked_at)}</span>
                      </div>
                      {bot.platform === 'dingtalk' ? (
                        <div className="integrations-bot-card__meta">
                          Footer：耗时 {boolCredential(bot.credentials.footer_elapsed, true) ? '开' : '关'} / 状态 {boolCredential(bot.credentials.footer_status, true) ? '开' : '关'}
                        </div>
                      ) : null}
                      {bot.last_health?.error ? <div className="integrations-bot-card__error">{bot.last_health.error}</div> : null}
                      <div className="integrations-bot-card__actions">
                        <button type="button" className="integrations-panel__soft-btn is-neutral" onClick={() => void onTest(bot)}>
                          重新测活
                        </button>
                        <button type="button" className="integrations-panel__soft-btn is-neutral" onClick={() => onEdit(bot)}>
                          编辑 / 高级模式
                        </button>
                        <button type="button" className="integrations-panel__soft-btn is-neutral" onClick={() => void onToggle(bot)}>
                          {bot.enabled ? '停用' : '启用'}
                        </button>
                        <button type="button" className="integrations-panel__soft-btn is-danger" onClick={() => void onDelete(bot)}>
                          删除
                        </button>
                      </div>
                    </article>
                  ))}
                </div>
              ) : (
                <div className="integrations-registry__placeholder">这个平台还没有创建实例。</div>
              )}
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

function BotWizardModal({
  open,
  mode,
  draft,
  saving,
  testing,
  testResult,
  step,
  showAdvanced,
  onClose,
  onChangeStep,
  onChangeDraft,
  onToggleAdvanced,
  onTest,
  onSave
}: {
  open: boolean;
  mode: 'create' | 'edit';
  draft: BotDraft;
  saving: boolean;
  testing: boolean;
  testResult: HealthStatus | null;
  step: WizardStep;
  showAdvanced: boolean;
  onClose: () => void;
  onChangeStep: (step: WizardStep) => void;
  onChangeDraft: (draft: BotDraft) => void;
  onToggleAdvanced: () => void;
  onTest: () => Promise<void>;
  onSave: () => Promise<void>;
}) {
  if (!open) return null;
  const fields = PLATFORM_FIELDS[draft.platform];
  const stepOrder = getStepOrder(draft.platform);
  const currentIndex = stepOrder.indexOf(step);
  const missingRequired = REQUIRED_FIELDS[draft.platform].filter((key) => {
    const value = draft.credentials[key];
    return !(typeof value === 'string' && value.trim());
  });

  function updateCredential(key: string, value: string | boolean) {
    onChangeDraft({
      ...draft,
      credentials: {
        ...draft.credentials,
        [key]: value
      }
    });
  }

  function updateAdvancedJson(value: string) {
    try {
      const parsed = JSON.parse(value) as Record<string, string | boolean>;
      onChangeDraft({
        ...draft,
        credentials: {
          ...emptyCredentials(draft.platform),
          ...Object.fromEntries(
            Object.entries(parsed).map(([key, entry]) => {
              if (draft.platform === 'dingtalk' && (key === 'footer_elapsed' || key === 'footer_status')) {
                return [key, entry === true || String(entry).toLowerCase() === 'true'];
              }
              return [key, String(entry ?? '')];
            })
          )
        }
      });
    } catch {
      // Keep editor tolerant while typing malformed JSON.
    }
  }

  return (
    <div className="integrations-modal-backdrop" onClick={onClose}>
      <div className="integrations-modal" onClick={(event) => event.stopPropagation()}>
        <div className="integrations-modal__header">
          <div>
            <div className="integrations-section__eyebrow">{mode === 'create' ? 'Create Wizard' : 'Edit Wizard'}</div>
            <h5 className="integrations-modal__title">{mode === 'create' ? '引导创建 IM Bot' : '编辑 IM Bot'}</h5>
            <p className="integrations-modal__desc">参考 OpenAkita 的多步引导：先选平台，再补齐信息、测活并完成保存。</p>
          </div>
          <button type="button" className="integrations-modal__close" onClick={onClose} aria-label="关闭">
            ×
          </button>
        </div>

        <div className="integrations-stepper">
          {stepOrder.map((item, index) => (
            <button
              key={item}
              type="button"
              className={`integrations-stepper__item${index === currentIndex ? ' is-current' : index < currentIndex ? ' is-complete' : ''}`}
              onClick={() => index <= currentIndex && onChangeStep(item)}
            >
              <span className="integrations-stepper__dot">{index + 1}</span>
              <span>{STEP_LABELS[item]}</span>
            </button>
          ))}
        </div>

        <div className="integrations-modal__body">
          {step === 'platform' ? (
            <div className="integrations-platform-grid">
              {PLATFORM_OPTIONS.filter((item) => item.supported).map((platform) => (
                <button
                  key={platform.id}
                  type="button"
                  className={`integrations-platform-card ${platform.accent}${draft.platform === platform.id ? ' is-selected' : ''}`}
                  onClick={() => onChangeDraft(buildDefaultDraft(platform.id as Extract<PlatformId, 'telegram' | 'feishu' | 'dingtalk'>))}
                >
                  <span className="integrations-platform-card__icon">
                    <PlatformLogo platform={platform.id} />
                  </span>
                  <span className="integrations-platform-card__title">{platform.title}</span>
                  <span className="integrations-platform-card__subtitle">{platform.subtitle}</span>
                </button>
              ))}
            </div>
          ) : null}

          {step === 'basic' ? (
            <div className="integrations-form-grid">
              <label className="integrations-form-field">
                <span>Bot ID</span>
                <input value={draft.id} onChange={(event) => onChangeDraft({ ...draft, id: event.target.value.toLowerCase().replace(/[^a-z0-9_-]/g, '-') })} />
              </label>
              <label className="integrations-form-field">
                <span>显示名称</span>
                <input value={draft.name} onChange={(event) => onChangeDraft({ ...draft, name: event.target.value })} />
              </label>
              <label className="integrations-form-field integrations-form-field--toggle">
                <span>保存后默认启用</span>
                <button
                  type="button"
                  className={`integrations-toggle${draft.enabled ? ' is-on' : ''}`}
                  onClick={() => onChangeDraft({ ...draft, enabled: !draft.enabled })}
                >
                  <span />
                </button>
              </label>
            </div>
          ) : null}

          {step === 'credentials' ? (
            <div className="integrations-form-grid">
              {fields.map((field) => (
                <label key={field.key} className="integrations-form-field">
                  <span>{field.label}</span>
                  <small>{field.hint}</small>
                  <input
                    type={field.secret ? 'password' : 'text'}
                    value={String(draft.credentials[field.key] ?? '')}
                    placeholder={field.placeholder}
                    onChange={(event) => updateCredential(field.key, event.target.value)}
                  />
                </label>
              ))}

              {draft.platform === 'dingtalk' ? (
                <div className="integrations-panel__notice integrations-panel__notice--status">
                  钉钉默认走 Stream 接收；发送侧优先卡片流式回复，失败会自动降级到普通卡片或文本。
                </div>
              ) : null}

              <button type="button" className="integrations-advanced-toggle" onClick={onToggleAdvanced}>
                {showAdvanced ? '收起高级模式' : '展开高级模式'}
              </button>

              {showAdvanced ? (
                <label className="integrations-form-field integrations-form-field--wide">
                  <span>高级模式：原始凭据 JSON</span>
                  <small>用于 bot 级精细编辑，不再直接操作整页 `channels`。</small>
                  <textarea
                    value={JSON.stringify(draft.credentials, null, 2)}
                    onChange={(event) => updateAdvancedJson(event.target.value)}
                    rows={10}
                  />
                </label>
              ) : null}
            </div>
          ) : null}

          {step === 'extra' ? (
            <div className="integrations-form-grid">
              {draft.platform === 'dingtalk' ? (
                <>
                  <label className="integrations-form-field integrations-form-field--toggle">
                    <span>底栏显示处理耗时</span>
                    <button
                      type="button"
                      className={`integrations-toggle${boolCredential(draft.credentials.footer_elapsed, true) ? ' is-on' : ''}`}
                      onClick={() => updateCredential('footer_elapsed', !boolCredential(draft.credentials.footer_elapsed, true))}
                    >
                      <span />
                    </button>
                  </label>
                  <label className="integrations-form-field integrations-form-field--toggle">
                    <span>底栏显示当前状态</span>
                    <button
                      type="button"
                      className={`integrations-toggle${boolCredential(draft.credentials.footer_status, true) ? ' is-on' : ''}`}
                      onClick={() => updateCredential('footer_status', !boolCredential(draft.credentials.footer_status, true))}
                    >
                      <span />
                    </button>
                  </label>
                  <div className="integrations-panel__notice integrations-panel__notice--status">
                    Extra 步骤用于配置钉钉卡片底栏信息。保存后仍需重启，运行时不会热应用。
                  </div>
                </>
              ) : (
                <div className="integrations-test-panel__placeholder">当前平台没有额外配置项。</div>
              )}
            </div>
          ) : null}

          {step === 'test' ? (
            <div className="integrations-test-panel">
              <div className="integrations-test-panel__summary">
                <div>
                  <strong>{draft.name}</strong>
                  <span>{draft.platform} / {draft.id}</span>
                </div>
                <button type="button" className="integrations-panel__accent-btn" onClick={() => void onTest()} disabled={testing || missingRequired.length > 0}>
                  {testing ? '检测中...' : '开始测活'}
                </button>
              </div>
              {missingRequired.length > 0 ? (
                <div className="integrations-panel__notice integrations-panel__notice--error">
                  仍有必填项缺失：{missingRequired.join(', ')}
                </div>
              ) : null}
              {testResult ? (
                <div className={`integrations-test-result ${healthTone(testResult)}`}>
                  <div className="integrations-test-result__title">{testResult.status === 'healthy' ? '验证成功' : '验证失败'}</div>
                  <div className="integrations-test-result__time">{formatCheckTime(testResult.checked_at)}</div>
                  {testResult.error ? <div className="integrations-test-result__error">{testResult.error}</div> : null}
                </div>
              ) : (
                <div className="integrations-test-panel__placeholder">建议保存前至少测活一次，确认凭据和网络可用。</div>
              )}
            </div>
          ) : null}

          {step === 'done' ? (
            <div className="integrations-done-panel">
              <div className="integrations-done-panel__icon">✓</div>
              <div className="integrations-done-panel__title">配置已准备完成</div>
              <div className="integrations-done-panel__desc">保存后会进入注册表，并在页面顶部显示“已保存，重启后生效”的提醒。</div>
              <div className="integrations-done-panel__meta">
                <span>平台：{draft.platform}</span>
                <span>名称：{draft.name}</span>
                <span>ID：{draft.id}</span>
                {draft.platform === 'dingtalk' ? (
                  <span>
                    Footer：耗时 {boolCredential(draft.credentials.footer_elapsed, true) ? '开' : '关'} / 状态 {boolCredential(draft.credentials.footer_status, true) ? '开' : '关'}
                  </span>
                ) : null}
              </div>
            </div>
          ) : null}
        </div>

        <div className="integrations-modal__footer">
          <div>
            {currentIndex > 0 ? (
              <button type="button" className="integrations-panel__ghost-btn" onClick={() => onChangeStep(stepOrder[currentIndex - 1])}>
                上一步
              </button>
            ) : null}
          </div>
          <div className="integrations-modal__footer-actions">
            <button type="button" className="integrations-panel__ghost-btn" onClick={onClose}>
              取消
            </button>
            {step === 'done' ? (
              <button type="button" className="integrations-panel__accent-btn" onClick={() => void onSave()} disabled={saving}>
                {saving ? '保存中...' : mode === 'create' ? '创建 Bot' : '保存修改'}
              </button>
            ) : (
              <button
                type="button"
                className="integrations-panel__accent-btn"
                onClick={() => onChangeStep(stepOrder[currentIndex + 1])}
                disabled={(step === 'basic' && (!draft.id.trim() || !draft.name.trim())) || (step === 'credentials' && missingRequired.length > 0)}
              >
                下一步
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

export function IntegrationsPanel() {
  const { snapshot } = useWorkspaceShellBridge();
  const [bots, setBots] = useState<IMBot[]>([]);
  const [loadState, setLoadState] = useState<LoadState>({ loading: true, errorText: '' });
  const [statusText, setStatusText] = useState('');
  const [showRestartNotice, setShowRestartNotice] = useState(false);
  const [restarting, setRestarting] = useState(false);
  const [wizardOpen, setWizardOpen] = useState(false);
  const [wizardMode, setWizardMode] = useState<'create' | 'edit'>('create');
  const [wizardStep, setWizardStep] = useState<WizardStep>('platform');
  const [draft, setDraft] = useState<BotDraft>(buildDefaultDraft('telegram'));
  const [wizardSaving, setWizardSaving] = useState(false);
  const [wizardTesting, setWizardTesting] = useState(false);
  const [wizardTestResult, setWizardTestResult] = useState<HealthStatus | null>(null);
  const [showAdvanced, setShowAdvanced] = useState(false);

  useEffect(() => {
    if (!snapshot.showSettings || snapshot.settingsTab !== 'integrations') return;
    void loadBots();
  }, [snapshot.showSettings, snapshot.settingsTab]);

  function pushStatus(message: string) {
    setStatusText(message);
    window.clearTimeout((pushStatus as typeof pushStatus & { timer?: number }).timer);
    (pushStatus as typeof pushStatus & { timer?: number }).timer = window.setTimeout(() => {
      setStatusText('');
    }, 3600);
  }

  async function loadBots() {
    setLoadState({ loading: true, errorText: '' });
    try {
      const response = await fetch('/api/im/bots');
      if (!response.ok) {
        throw new Error(await readErrorMessage(response, '加载 IM Bot 列表失败'));
      }
      const payload = await parseResponse(response);
      const nextBots = Array.isArray(payload?.bots) ? (payload.bots as IMBot[]) : [];
      setBots(nextBots.map((bot) => ({ ...bot, last_health: normalizeHealth(bot.last_health) })));
      setLoadState({ loading: false, errorText: '' });
    } catch (error) {
      setLoadState({
        loading: false,
        errorText: error instanceof Error ? error.message : '加载 IM Bot 列表失败'
      });
    }
  }

  function openCreate(platform: Extract<PlatformId, 'telegram' | 'feishu' | 'dingtalk'>) {
    setWizardMode('create');
    setDraft(buildDefaultDraft(platform));
    setWizardStep('platform');
    setWizardTestResult(null);
    setShowAdvanced(false);
    setWizardOpen(true);
  }

  function openEdit(bot: IMBot) {
    setWizardMode('edit');
      setDraft({
        originalId: bot.id,
        id: bot.id,
        name: bot.name,
        platform: bot.platform,
        enabled: bot.enabled,
        credentials: { ...emptyCredentials(bot.platform), ...bot.credentials }
      });
      setWizardStep('basic');
    setWizardTestResult(normalizeHealth(bot.last_health));
    setShowAdvanced(false);
    setWizardOpen(true);
  }

  async function saveDraft() {
    setWizardSaving(true);
    try {
      const url = wizardMode === 'create' ? '/api/im/bots' : `/api/im/bots/${encodeURIComponent(draft.originalId || draft.id)}`;
      const response = await fetch(url, {
        method: wizardMode === 'create' ? 'POST' : 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          id: draft.id,
          name: draft.name,
          platform: draft.platform,
          enabled: draft.enabled,
          credentials: draft.credentials,
          last_health: wizardTestResult
        })
      });

      if (!response.ok) {
        throw new Error(await readErrorMessage(response, wizardMode === 'create' ? '创建 IM Bot 失败' : '保存 IM Bot 失败'));
      }

      setWizardOpen(false);
      setShowRestartNotice(true);
      pushStatus(wizardMode === 'create' ? 'IM Bot 已创建，重启后生效' : 'IM Bot 已更新，重启后生效');
      await loadBots();
    } catch (error) {
      pushStatus(error instanceof Error ? error.message : '保存 IM Bot 失败');
    } finally {
      setWizardSaving(false);
    }
  }

  async function runDraftHealthcheck() {
    setWizardTesting(true);
    try {
      const response = await fetch('/api/im/bots/health', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          platform: draft.platform,
          credentials: draft.credentials,
          persist: false
        })
      });
      if (!response.ok) {
        throw new Error(await readErrorMessage(response, 'IM Bot 测活失败'));
      }
      const payload = await parseResponse(response);
      setWizardTestResult(normalizeHealth(payload?.result));
      setWizardStep('done');
    } catch (error) {
      const fallback = error instanceof Error ? error.message : 'IM Bot 测活失败';
      setWizardTestResult({ status: 'unhealthy', error: fallback, checked_at: new Date().toISOString() });
      pushStatus(fallback);
    } finally {
      setWizardTesting(false);
    }
  }

  async function testSavedBot(bot: IMBot) {
    try {
      const response = await fetch('/api/im/bots/health', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ bot_id: bot.id, persist: true })
      });
      if (!response.ok) {
        throw new Error(await readErrorMessage(response, 'Bot 测活失败'));
      }
      pushStatus(`${bot.name} 已完成测活`);
      await loadBots();
    } catch (error) {
      pushStatus(error instanceof Error ? error.message : 'Bot 测活失败');
    }
  }

  async function toggleBot(bot: IMBot) {
    try {
      const response = await fetch(`/api/im/bots/${encodeURIComponent(bot.id)}/toggle`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled: !bot.enabled })
      });
      if (!response.ok) {
        throw new Error(await readErrorMessage(response, '切换 Bot 状态失败'));
      }
      setShowRestartNotice(true);
      pushStatus(`${bot.name} 已${bot.enabled ? '停用' : '启用'}，重启后生效`);
      await loadBots();
    } catch (error) {
      pushStatus(error instanceof Error ? error.message : '切换 Bot 状态失败');
    }
  }

  async function deleteBot(bot: IMBot) {
    if (!window.confirm(`确定删除 IM Bot「${bot.name}」吗？`)) return;
    try {
      const response = await fetch(`/api/im/bots/${encodeURIComponent(bot.id)}`, { method: 'DELETE' });
      if (!response.ok) {
        throw new Error(await readErrorMessage(response, '删除 IM Bot 失败'));
      }
      setShowRestartNotice(true);
      pushStatus(`${bot.name} 已删除，重启后生效`);
      await loadBots();
    } catch (error) {
      pushStatus(error instanceof Error ? error.message : '删除 IM Bot 失败');
    }
  }

  async function restartBackend() {
    setRestarting(true);
    try {
      const response = await fetch('/api/system/restart', { method: 'POST' });
      if (!response.ok) {
        throw new Error(await readErrorMessage(response, '自动重启失败'));
      }
      pushStatus('已触发后端重启，请稍候刷新状态');
      setShowRestartNotice(false);
    } catch (error) {
      pushStatus(error instanceof Error ? error.message : '自动重启失败');
    } finally {
      setRestarting(false);
    }
  }

  return (
    <div className="integrations-panel integrations-panel--im-bots">
      <header className="integrations-panel__header">
        <div>
          <div className="integrations-panel__eyebrow">IM Setup Center</div>
          <h4 className="integrations-panel__title">即时通讯通道配置</h4>
          <p className="integrations-panel__meta">从“固定三张表单”升级为“平台概览 + Bot 注册表 + 引导创建 + 高级模式”，并支持同平台多实例。</p>
        </div>
        <div className="integrations-panel__toolbar">
          <button type="button" className="integrations-panel__ghost-btn" onClick={() => void loadBots()} disabled={loadState.loading}>
            刷新
          </button>
          <button type="button" className="integrations-panel__accent-btn" onClick={() => openCreate('telegram')}>
            新建 IM Bot
          </button>
        </div>
      </header>

      <RestartBanner visible={showRestartNotice} restarting={restarting} onRestart={restartBackend} onDismiss={() => setShowRestartNotice(false)} />

      {loadState.errorText ? <div className="integrations-panel__notice integrations-panel__notice--error">{loadState.errorText}</div> : null}
      {statusText ? <div className="integrations-panel__notice integrations-panel__notice--status">{statusText}</div> : null}
      {loadState.loading ? <div className="integrations-panel__empty">正在加载 IM Setup Center...</div> : null}

      {!loadState.loading ? (
        <>
          <PlatformGallery onCreate={openCreate} />
          <BotRegistry bots={bots} onCreate={openCreate} onEdit={openEdit} onDelete={deleteBot} onToggle={toggleBot} onTest={testSavedBot} />
        </>
      ) : null}

      <BotWizardModal
        open={wizardOpen}
        mode={wizardMode}
        draft={draft}
        saving={wizardSaving}
        testing={wizardTesting}
        testResult={wizardTestResult}
        step={wizardStep}
        showAdvanced={showAdvanced}
        onClose={() => setWizardOpen(false)}
        onChangeStep={setWizardStep}
        onChangeDraft={setDraft}
        onToggleAdvanced={() => setShowAdvanced((current) => !current)}
        onTest={runDraftHealthcheck}
        onSave={saveDraft}
      />
    </div>
  );
}

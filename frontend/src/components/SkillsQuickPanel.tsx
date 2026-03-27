import { useDeferredValue, useEffect, useMemo, useState } from 'react';
import {
  getHostApp,
  type OpenGuiclawApp,
  type SkillInstallMessage,
  type SkillMarketplaceRecord,
  type SkillRecord,
  waitForHostApp
} from '../bridge/openGuiclaw';
import { CaretDownIcon } from './icons/ShellIcons';

type StatusFilter = 'all' | 'enabled' | 'disabled';
type SkillsTab = 'installed' | 'marketplace';

function snapshotSkills(app: OpenGuiclawApp | null): SkillRecord[] {
  return Array.isArray(app?.skills) ? app.skills.map((skill) => ({ ...skill })) : [];
}

function snapshotMarketplace(app: OpenGuiclawApp | null): SkillMarketplaceRecord[] {
  return Array.isArray(app?.skillMarketplace) ? app.skillMarketplace.map((skill) => ({ ...skill })) : [];
}

function snapshotInstallMessage(app: OpenGuiclawApp | null): SkillInstallMessage | null {
  return app?.skillInstallMsg ? { ...app.skillInstallMsg } : null;
}

export function SkillsQuickPanel() {
  const [hostApp, setHostApp] = useState<OpenGuiclawApp | null>(getHostApp());
  const [skills, setSkills] = useState<SkillRecord[]>(() => snapshotSkills(getHostApp()));
  const [marketplace, setMarketplace] = useState<SkillMarketplaceRecord[]>(() => snapshotMarketplace(getHostApp()));
  const [installMessage, setInstallMessage] = useState<SkillInstallMessage | null>(() => snapshotInstallMessage(getHostApp()));
  const [loading, setLoading] = useState(!getHostApp());
  const [marketplaceLoading, setMarketplaceLoading] = useState<boolean>(Boolean(getHostApp()?.skillMarketLoading));
  const [errorText, setErrorText] = useState('');
  const [searchText, setSearchText] = useState('');
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all');
  const [expandedNames, setExpandedNames] = useState<string[]>([]);
  const [busySkillAction, setBusySkillAction] = useState<string | null>(null);
  const [reloadBusy, setReloadBusy] = useState(false);
  const [activeTab, setActiveTab] = useState<SkillsTab>('installed');
  const [marketQuery, setMarketQuery] = useState(() => getHostApp()?.skillMarketSearch || 'agent');
  const [urlInput, setUrlInput] = useState('');
  const [marketInstallingId, setMarketInstallingId] = useState<string | null>(getHostApp()?.skillInstallingId ?? null);
  const deferredSearchText = useDeferredValue(searchText);

  function syncFromHost(nextApp: OpenGuiclawApp | null) {
    setSkills(snapshotSkills(nextApp));
    setMarketplace(snapshotMarketplace(nextApp));
    setInstallMessage(snapshotInstallMessage(nextApp));
    setMarketplaceLoading(Boolean(nextApp?.skillMarketLoading));
    setMarketInstallingId(nextApp?.skillInstallingId ?? null);
    if (typeof nextApp?.skillMarketSearch === 'string' && nextApp.skillMarketSearch.trim()) {
      setMarketQuery(nextApp.skillMarketSearch);
    }
  }

  useEffect(() => {
    let mounted = true;

    waitForHostApp()
      .then(async (app) => {
        if (!mounted) return;
        setHostApp(app);
        await app.loadSkills();
        if (!mounted) return;
        syncFromHost(app);
        setLoading(false);
      })
      .catch((error: Error) => {
        if (!mounted) return;
        setErrorText(error.message);
        setLoading(false);
      });

    const handleUpdated = () => {
      const nextApp = getHostApp();
      if (!nextApp || !mounted) return;
      setHostApp(nextApp);
      syncFromHost(nextApp);
    };

    window.addEventListener('openguiclaw:skills-updated', handleUpdated);
    return () => {
      mounted = false;
      window.removeEventListener('openguiclaw:skills-updated', handleUpdated);
    };
  }, []);

  useEffect(() => {
    if (activeTab !== 'marketplace') return;
    if (!hostApp?.searchSkillMarketplace) return;
    if (marketplaceLoading || marketplace.length > 0) return;
    void hostApp.searchSkillMarketplace(marketQuery || 'agent');
  }, [activeTab, hostApp, marketQuery, marketplace.length, marketplaceLoading]);

  const normalizedQuery = deferredSearchText.trim().toLowerCase();
  const filteredSkills = useMemo(
    () =>
      skills.filter((skill) => {
        const matchesQuery =
          !normalizedQuery ||
          skill.name.toLowerCase().includes(normalizedQuery) ||
          skill.description.toLowerCase().includes(normalizedQuery);

        if (!matchesQuery) return false;
        if (statusFilter === 'enabled') return skill.enabled;
        if (statusFilter === 'disabled') return !skill.enabled;
        return true;
      }),
    [normalizedQuery, skills, statusFilter]
  );

  const groupedSkills = useMemo(
    () =>
      Object.entries(
        filteredSkills.reduce<Record<string, SkillRecord[]>>((groups, skill) => {
          const category = skill.category || 'general';
          if (!groups[category]) groups[category] = [];
          groups[category].push(skill);
          return groups;
        }, {})
      ).sort((left, right) => left[0].localeCompare(right[0])),
    [filteredSkills]
  );

  const enabledCount = skills.filter((skill) => skill.enabled).length;

  function getTypeLabel(skill: SkillRecord): string {
    if (skill.locked || skill.type === 'system_plugin') return '系统能力';
    if (skill.type === 'builtin_skill') return '内置技能';
    return '用户技能';
  }

  function getMarketplaceItemKey(item: SkillMarketplaceRecord): string {
    return item.id || item.url || item.git_url || item.name;
  }

  function getMarketplaceActionLabel(item: SkillMarketplaceRecord): string {
    if (marketInstallingId === item.name || marketInstallingId === item.id) return '安装中...';
    if (item.installed) return '已安装';
    return '安装';
  }

  function toggleExpanded(name: string) {
    setExpandedNames((current) =>
      current.includes(name) ? current.filter((item) => item !== name) : [...current, name]
    );
  }

  async function handleReload() {
    if (!hostApp) return;
    setReloadBusy(true);
    setErrorText('');
    try {
      await hostApp.reloadSkills();
      syncFromHost(hostApp);
    } catch (error) {
      setErrorText(error instanceof Error ? error.message : '刷新技能失败');
    } finally {
      setReloadBusy(false);
    }
  }

  async function handleToggle(skill: SkillRecord) {
    if (!hostApp) return;
    setBusySkillAction(`${skill.name}:toggle`);
    setErrorText('');
    try {
      await hostApp.toggleSkill(skill.name, !skill.enabled);
      syncFromHost(hostApp);
    } catch (error) {
      setErrorText(error instanceof Error ? error.message : '更新技能失败');
    } finally {
      setBusySkillAction(null);
    }
  }

  async function handleUninstall(skill: SkillRecord) {
    if (!hostApp?.uninstallSkill) return;
    setBusySkillAction(`${skill.name}:uninstall`);
    setErrorText('');
    try {
      await hostApp.uninstallSkill(skill.name);
      syncFromHost(hostApp);
    } catch (error) {
      setErrorText(error instanceof Error ? error.message : '卸载技能失败');
    } finally {
      setBusySkillAction(null);
    }
  }

  async function handleMarketplaceSearch() {
    if (!hostApp?.searchSkillMarketplace) return;
    setErrorText('');
    try {
      await hostApp.searchSkillMarketplace(marketQuery || 'agent');
      syncFromHost(hostApp);
    } catch (error) {
      setErrorText(error instanceof Error ? error.message : '搜索技能失败');
    }
  }

  async function handleMarketplaceInstall(item: SkillMarketplaceRecord) {
    if (!hostApp?.installSkillFromUrl) return;
    const installSource = item.url || item.git_url || '';
    if (!installSource) {
      setErrorText(`技能 ${item.name} 缺少安装源`);
      return;
    }
    setErrorText('');
    try {
      const installed = await hostApp.installSkillFromUrl(installSource, item.name || item.id || null);
      if (!installed) return;
      syncFromHost(hostApp);
    } catch (error) {
      setErrorText(error instanceof Error ? error.message : '安装技能失败');
    }
  }

  return (
    <section className="react-skills-panel">
      <header className="react-skills-panel__header">
        <div>
          <div className="react-skills-panel__eyebrow">技能中心</div>
          <h3 className="react-skills-panel__title">统一技能目录</h3>
          <p className="react-skills-panel__meta">
            <span>{enabledCount} 已启用</span>
            <span className="react-skills-panel__meta-divider">/</span>
            <span>共 {skills.length} 个能力节点</span>
          </p>
        </div>
        <button
          type="button"
          className="react-skills-panel__reload"
          onClick={handleReload}
          disabled={!hostApp || reloadBusy}
        >
          {reloadBusy ? '刷新中...' : '刷新目录'}
        </button>
      </header>

      <div className="react-skills-panel__tabs">
        <button
          type="button"
          className={`react-skills-panel__tab ${activeTab === 'installed' ? 'is-active' : ''}`}
          onClick={() => setActiveTab('installed')}
        >
          已安装
        </button>
        <button
          type="button"
          className={`react-skills-panel__tab ${activeTab === 'marketplace' ? 'is-active' : ''}`}
          onClick={() => setActiveTab('marketplace')}
        >
          技能市场
        </button>
      </div>

      {installMessage ? (
        <div className={`react-skills-panel__banner ${installMessage.type === 'success' ? 'is-success' : 'is-error'}`}>
          <span>{installMessage.text}</span>
        </div>
      ) : null}

      {errorText ? <div className="react-skills-panel__error">{errorText}</div> : null}

      {activeTab === 'installed' ? (
        <>
          <div className="react-skills-panel__toolbar">
            <input
              type="text"
              className="react-skills-panel__search"
              value={searchText}
              onChange={(event) => setSearchText(event.target.value)}
              placeholder="搜索已安装技能"
            />
            <div className="react-skills-panel__filters">
              {(['all', 'enabled', 'disabled'] as StatusFilter[]).map((filter) => (
                <button
                  key={filter}
                  type="button"
                  className={`react-skills-panel__filter ${statusFilter === filter ? 'is-active' : ''}`}
                  onClick={() => setStatusFilter(filter)}
                >
                  {filter === 'all' ? '全部' : filter === 'enabled' ? '已启用' : '已禁用'}
                </button>
              ))}
            </div>
          </div>

          <div className="react-skills-panel__content">
            {loading ? <div className="react-skills-panel__empty">加载技能中...</div> : null}

            {!loading && groupedSkills.length === 0 ? (
              <div className="react-skills-panel__empty">没有符合当前筛选条件的技能。</div>
            ) : null}

            {!loading
              ? groupedSkills.map(([category, categorySkills]) => (
                  <section className="react-skills-group" key={category}>
                    <div className="react-skills-group__header">
                      <span className="react-skills-group__name">{category}</span>
                      <span className="react-skills-group__count">{categorySkills.length}</span>
                    </div>

                    <div className="react-skills-group__list">
                      {categorySkills.map((skill) => {
                        const isExpanded = expandedNames.includes(skill.name);
                        const isToggleBusy = busySkillAction === `${skill.name}:toggle`;
                        const isUninstallBusy = busySkillAction === `${skill.name}:uninstall`;
                        const canUninstall = !skill.locked && skill.type === 'user_skill' && !!hostApp?.uninstallSkill;
                        return (
                          <article className="react-skills-card" key={skill.name}>
                            <div className="react-skills-card__row">
                              <div className="react-skills-card__info">
                                <div className="react-skills-card__heading">
                                  <span className="react-skills-card__name">{skill.name}</span>
                                  <span className={`react-skills-card__status ${skill.enabled ? 'is-on' : 'is-off'}`}>
                                    {skill.locked ? '系统锁定' : skill.enabled ? '开启' : '关闭'}
                                  </span>
                                </div>
                                <p className="react-skills-card__description">{skill.description}</p>
                                <p className="react-skills-card__description">
                                  {getTypeLabel(skill)}
                                  {skill.locked ? ' / 不可关闭' : ''}
                                  {skill.source ? ` / ${skill.source}` : ''}
                                </p>
                                {skill.tools && skill.tools.length > 0 ? (
                                  <button
                                    type="button"
                                    className="react-skills-card__tools-toggle"
                                    onClick={() => toggleExpanded(skill.name)}
                                  >
                                    <span>{isExpanded ? '收起工具' : `展开工具 (${skill.tools.length})`}</span>
                                    <CaretDownIcon
                                      className={`react-skills-card__tools-chevron${isExpanded ? ' is-open' : ''}`}
                                    />
                                  </button>
                                ) : null}
                              </div>

                              {skill.locked ? (
                                <button type="button" className="react-skills-card__switch is-on" disabled>
                                  系统能力
                                </button>
                              ) : (
                                <div className="react-skills-card__actions">
                                  {canUninstall ? (
                                    <button
                                      type="button"
                                      className="react-skills-card__switch is-danger"
                                      onClick={() => handleUninstall(skill)}
                                      disabled={isToggleBusy || isUninstallBusy || !hostApp}
                                    >
                                      {isUninstallBusy ? '卸载中...' : '卸载'}
                                    </button>
                                  ) : null}
                                  <button
                                    type="button"
                                    className={`react-skills-card__switch ${skill.enabled ? 'is-on' : 'is-off'}`}
                                    onClick={() => handleToggle(skill)}
                                    disabled={isToggleBusy || isUninstallBusy || !hostApp}
                                  >
                                    {isToggleBusy ? '处理中...' : skill.enabled ? '禁用' : '启用'}
                                  </button>
                                </div>
                              )}
                            </div>

                            {isExpanded && skill.tools && skill.tools.length > 0 ? (
                              <div className="react-skills-card__tools">
                                {skill.tools.map((tool) => (
                                  <span className="react-skills-card__tool" key={tool}>
                                    {tool}
                                  </span>
                                ))}
                              </div>
                            ) : null}
                          </article>
                        );
                      })}
                    </div>
                  </section>
                ))
              : null}
          </div>
        </>
      ) : (
        <>
          <div className="react-skills-panel__toolbar">
            <div className="react-skills-market__search-row">
              <input
                type="text"
                className="react-skills-panel__search"
                value={marketQuery}
                onChange={(event) => setMarketQuery(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter') {
                    void handleMarketplaceSearch();
                  }
                }}
                placeholder="搜索技能市场"
              />
              <button
                type="button"
                className="react-skills-panel__reload"
                onClick={() => void handleMarketplaceSearch()}
                disabled={!hostApp?.searchSkillMarketplace || marketplaceLoading}
              >
                {marketplaceLoading ? '搜索中...' : '搜索'}
              </button>
            </div>
            <div className="react-skills-market__install-row">
              <input
                type="text"
                className="react-skills-panel__search is-mono"
                value={urlInput}
                onChange={(event) => setUrlInput(event.target.value)}
                placeholder="粘贴 GitHub / URL 安装源"
              />
              <button
                type="button"
                className="react-skills-panel__reload is-secondary"
                onClick={async () => {
                  if (!hostApp?.installSkillFromUrl) return;
                  setErrorText('');
                  const installed = await hostApp.installSkillFromUrl(urlInput, null);
                  if (!installed) {
                    syncFromHost(hostApp);
                    return;
                  }
                  setUrlInput('');
                  syncFromHost(hostApp);
                }}
                disabled={!hostApp?.installSkillFromUrl || !urlInput.trim()}
              >
                立即安装
              </button>
            </div>
          </div>

          <div className="react-skills-panel__content">
            {marketplaceLoading ? <div className="react-skills-panel__empty">正在同步技能市场...</div> : null}

            {!marketplaceLoading && marketplace.length === 0 ? (
              <div className="react-skills-panel__empty">还没有市场结果，试试搜索一个关键词。</div>
            ) : null}

            {!marketplaceLoading
              ? marketplace.map((item) => {
                  const itemKey = getMarketplaceItemKey(item);
                  const isExpanded = expandedNames.includes(itemKey);
                  const isInstalled = Boolean(item.installed);
                  const installDisabled = isInstalled || !hostApp?.installSkillFromUrl;
                  return (
                    <article className="react-skills-market-card" key={itemKey}>
                      <div className="react-skills-market-card__body">
                        <div className="react-skills-market-card__icon">✦</div>
                        <div className="react-skills-market-card__info">
                          <div className="react-skills-market-card__heading">
                            <div className="react-skills-market-card__title-wrap">
                              <span className="react-skills-card__name">{item.name}</span>
                              {item.version ? (
                                <span className="react-skills-market-card__version">v{item.version}</span>
                              ) : null}
                              {isInstalled ? (
                                <span className="react-skills-market-card__installed">已安装</span>
                              ) : null}
                            </div>
                            {item.tools && item.tools.length > 0 ? (
                              <button
                                type="button"
                                className="react-skills-card__tools-toggle"
                                onClick={() => toggleExpanded(itemKey)}
                              >
                                <span>{isExpanded ? '收起工具' : `展开工具 (${item.tools.length})`}</span>
                                <CaretDownIcon
                                  className={`react-skills-card__tools-chevron${isExpanded ? ' is-open' : ''}`}
                                />
                              </button>
                            ) : null}
                          </div>

                          <p className="react-skills-card__description">
                            {item.description || '暂无技能说明'}
                          </p>

                          <div className="react-skills-market-card__meta">
                            {item.author ? <span>作者 · {item.author}</span> : null}
                            {typeof item.stars === 'number' && item.stars > 0 ? <span>★ {item.stars}</span> : null}
                            {typeof item.installs === 'number' && item.installs > 0 ? <span>安装 {item.installs}</span> : null}
                            {item.category ? <span>{item.category}</span> : null}
                          </div>

                          {item.tags && item.tags.length > 0 ? (
                            <div className="react-skills-market-card__tags">
                              {item.tags.slice(0, 6).map((tag) => (
                                <span className="react-skills-market-card__tag" key={`${itemKey}-${tag}`}>
                                  {tag}
                                </span>
                              ))}
                            </div>
                          ) : null}
                        </div>
                      </div>

                      <div className="react-skills-market-card__actions">
                        <button
                          type="button"
                          className={`react-skills-card__switch ${isInstalled ? 'is-on' : 'is-off'}`}
                          onClick={() => void handleMarketplaceInstall(item)}
                          disabled={installDisabled}
                        >
                          {getMarketplaceActionLabel(item)}
                        </button>
                      </div>

                      {isExpanded && item.tools && item.tools.length > 0 ? (
                        <div className="react-skills-card__tools">
                          {item.tools.map((tool) => (
                            <span className="react-skills-card__tool" key={`${itemKey}-${tool}`}>
                              {tool}
                            </span>
                          ))}
                        </div>
                      ) : null}
                    </article>
                  );
                })
              : null}
          </div>
        </>
      )}
    </section>
  );
}

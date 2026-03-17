import { useDeferredValue, useState } from 'react';
import { type OpenGuiclawApp, type SkillRecord } from '../bridge/openGuiclaw';
import { useHostCollection } from '../hooks/useHostCollection';

type StatusFilter = 'all' | 'enabled' | 'disabled';

function snapshotSkills(app: OpenGuiclawApp): SkillRecord[] {
  return Array.isArray(app.skills) ? app.skills.map((skill) => ({ ...skill })) : [];
}

export function SkillsQuickPanel() {
  const {
    hostApp,
    items: skills,
    setItems: setSkills,
    loading,
    errorText,
    setErrorText
  } = useHostCollection<SkillRecord>({
    eventName: 'openguiclaw:skills-updated',
    load: (app) => app.loadSkills(),
    snapshot: snapshotSkills
  });
  const [searchText, setSearchText] = useState('');
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all');
  const [expandedNames, setExpandedNames] = useState<string[]>([]);
  const [busySkillName, setBusySkillName] = useState<string | null>(null);
  const [reloadBusy, setReloadBusy] = useState(false);
  const deferredSearchText = useDeferredValue(searchText);

  const normalizedQuery = deferredSearchText.trim().toLowerCase();
  const filteredSkills = skills.filter((skill) => {
    const matchesQuery =
      !normalizedQuery ||
      skill.name.toLowerCase().includes(normalizedQuery) ||
      skill.description.toLowerCase().includes(normalizedQuery);

    if (!matchesQuery) return false;
    if (statusFilter === 'enabled') return skill.enabled;
    if (statusFilter === 'disabled') return !skill.enabled;
    return true;
  });

  const groupedSkills = Object.entries(
    filteredSkills.reduce<Record<string, SkillRecord[]>>((groups, skill) => {
      const category = skill.category || 'general';
      if (!groups[category]) groups[category] = [];
      groups[category].push(skill);
      return groups;
    }, {})
  ).sort((left, right) => left[0].localeCompare(right[0]));

  const enabledCount = skills.filter((skill) => skill.enabled).length;

  async function handleReload() {
    if (!hostApp) return;
    setReloadBusy(true);
    setErrorText('');
    try {
      await hostApp.reloadSkills();
      setSkills(snapshotSkills(hostApp));
    } catch (error) {
      setErrorText(error instanceof Error ? error.message : 'Failed to reload skills');
    } finally {
      setReloadBusy(false);
    }
  }

  async function handleToggle(skill: SkillRecord) {
    if (!hostApp) return;
    setBusySkillName(skill.name);
    setErrorText('');
    try {
      await hostApp.toggleSkill(skill.name, !skill.enabled);
      setSkills(snapshotSkills(hostApp));
    } catch (error) {
      setErrorText(error instanceof Error ? error.message : 'Failed to update skill');
    } finally {
      setBusySkillName(null);
    }
  }

  function toggleExpanded(name: string) {
    setExpandedNames((current) =>
      current.includes(name) ? current.filter((item) => item !== name) : [...current, name]
    );
  }

  return (
    <section className="react-skills-panel">
      <header className="react-skills-panel__header">
        <div>
          <div className="react-skills-panel__eyebrow">React Pilot</div>
          <h3 className="react-skills-panel__title">Installed Skills</h3>
          <p className="react-skills-panel__meta">
            <span>{enabledCount} active</span>
            <span className="react-skills-panel__meta-divider">/</span>
            <span>{skills.length} total</span>
          </p>
        </div>
        <button
          type="button"
          className="react-skills-panel__reload"
          onClick={handleReload}
          disabled={!hostApp || reloadBusy}
        >
          {reloadBusy ? 'Refreshing...' : 'Refresh'}
        </button>
      </header>

      <div className="react-skills-panel__toolbar">
        <input
          type="text"
          className="react-skills-panel__search"
          value={searchText}
          onChange={(event) => setSearchText(event.target.value)}
          placeholder="Search installed skills"
        />
        <div className="react-skills-panel__filters">
          {(['all', 'enabled', 'disabled'] as StatusFilter[]).map((filter) => (
            <button
              key={filter}
              type="button"
              className={`react-skills-panel__filter ${statusFilter === filter ? 'is-active' : ''}`}
              onClick={() => setStatusFilter(filter)}
            >
              {filter}
            </button>
          ))}
        </div>
      </div>

      {errorText ? <div className="react-skills-panel__error">{errorText}</div> : null}

      <div className="react-skills-panel__content">
        {loading ? <div className="react-skills-panel__empty">Loading skills...</div> : null}

        {!loading && groupedSkills.length === 0 ? (
          <div className="react-skills-panel__empty">No installed skills match the current filter.</div>
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
                    const isBusy = busySkillName === skill.name;
                    return (
                      <article className="react-skills-card" key={skill.name}>
                        <div className="react-skills-card__row">
                          <div className="react-skills-card__info">
                            <div className="react-skills-card__heading">
                              <span className="react-skills-card__name">{skill.name}</span>
                              <span className={`react-skills-card__status ${skill.enabled ? 'is-on' : 'is-off'}`}>
                                {skill.enabled ? 'on' : 'off'}
                              </span>
                            </div>
                            <p className="react-skills-card__description">{skill.description}</p>
                            {skill.tools && skill.tools.length > 0 ? (
                              <button
                                type="button"
                                className="react-skills-card__tools-toggle"
                                onClick={() => toggleExpanded(skill.name)}
                              >
                                {isExpanded ? 'Hide tools' : `Show tools (${skill.tools.length})`}
                              </button>
                            ) : null}
                          </div>

                          <button
                            type="button"
                            className={`react-skills-card__switch ${skill.enabled ? 'is-on' : 'is-off'}`}
                            onClick={() => handleToggle(skill)}
                            disabled={isBusy || !hostApp}
                          >
                            {isBusy ? '...' : skill.enabled ? 'Disable' : 'Enable'}
                          </button>
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
    </section>
  );
}

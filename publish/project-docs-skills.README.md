# Project Docs Skills

> A small skill package for long-running project memory and publication-quality Markdown documentation.

This repository bundles two complementary skills:

- `project-doc-tracker`
- `professional-markdown`

Together they help an agent:

1. keep project progress from being forgotten over time
2. maintain lightweight tracker docs inside the repo
3. promote mature modules into polished long-form documentation

## Install

Install the whole package:

```bash
npx skills add lclen/project-docs-skills
```

Install only specific skills:

```bash
npx skills add lclen/project-docs-skills --skill project-doc-tracker --skill professional-markdown
```

## Included Skills

### `project-doc-tracker`

Use this skill to maintain lightweight project memory inside a repository.

It is designed for:

- project progress tracking
- append-only session logs
- lightweight feature notes
- project context recovery after a pause
- identifying modules that should later become formal docs

Typical outputs:

- `docs/project-tracker/OVERVIEW.md`
- `docs/project-tracker/PROGRESS.md`
- `docs/project-tracker/features/*.md`

### `professional-markdown`

Use this skill when the output should feel publication-ready rather than merely correct.

It is designed for:

- architecture documents
- module documentation
- high-quality READMEs
- structured technical explanations
- polished Markdown with diagrams, tables, and callouts

Typical outputs:

- `docs/modules/*.md`
- architecture guides
- public-facing technical documentation

## Recommended Workflow

1. Use `project-doc-tracker` to initialize or update the tracker documentation system.
2. Keep `OVERVIEW.md`, `PROGRESS.md`, and lightweight feature notes current during development, but treat `PROGRESS.md` as meaningful history rather than a transcript of every tiny fix.
3. When a feature or module becomes stable, use `professional-markdown` to create the long-form formal document.
4. Backfill the resulting formal doc path into the tracker.

Practical rule of thumb:

> If an entry would not noticeably help a future agent recover project state faster, it probably should not be a new `PROGRESS.md` entry.

## Persistent Tool Rules

`project-doc-tracker` also includes rule installers for major AI coding tools:

- `kiro` -> `.kiro/steering/project-doc-tracker.md`
- `claude` -> `CLAUDE.md`
- `cursor` -> `.cursorrules`
- `windsurf` -> `.windsurfrules`
- `codex` -> `AGENTS.md`

Install one with the generic entrypoint:

```bash
python .agents/skills/project-doc-tracker/scripts/setup_tool_rules.py --tool codex --project-root .
```

Or simply copy the matching template into the target rule file:

- `project-doc-tracker/references/tool-rule-templates/codex.md` -> `AGENTS.md`
- `project-doc-tracker/references/tool-rule-templates/claude.md` -> `CLAUDE.md`
- `project-doc-tracker/references/tool-rule-templates/cursor.md` -> `.cursorrules`
- `project-doc-tracker/references/tool-rule-templates/windsurf.md` -> `.windsurfrules`

For Kiro specifically, copy the rule block from `project-doc-tracker/references/steering-template.md` into:

```bash
.kiro/steering/project-doc-tracker.md
```

## Example Prompts

Initialize tracker docs for an existing codebase:

```text
Please use $project-doc-tracker to initialize the project tracker documentation system. This repository already has meaningful code, so do not leave empty templates. Scan the main modules and backfill the initial overview and feature notes.
```

Promote a mature module into a formal doc:

```text
Use $project-doc-tracker to identify whether memory-system is ready for promote-to-doc, then hand it off to $professional-markdown for a full formal document.
```

Write a polished module document directly:

```text
Please use $professional-markdown to write a high-quality module document for the plugin system, including overview, architecture, key files, usage, limitations, and future improvements.
```

## Repository Layout

```text
project-docs-skills/
├─ README.md
├─ project-doc-tracker/
└─ professional-markdown/
```

## Notes

- `skills.sh` does not currently use a separate publish button. Public Git repositories are shared directly, and wider usage helps them surface in the ecosystem.
- This repo is intentionally focused on documentation workflow, not on generic coding or project bootstrap.
- Installing the skill package does not automatically modify a target repository. Use the provided installer scripts when you want persistent tool-specific rules inside a project.

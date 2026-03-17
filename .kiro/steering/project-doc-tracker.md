---
inclusion: always
---

# Project Progress Tracking Rules

This project uses the `project-doc-tracker` skill to record development progress.

## When to Record

Guiding principle: **"Would this record help understand the current project state in a new conversation?"**

If yes, record it. If it wouldn't matter, skip it.

Typically worth recording: new feature implementation, architecture changes, significant multi-file fixes, key decisions.
Typically not worth recording: single-file minor bugfix, typo corrections, formatting tweaks, dependency version bumps.

## When to Read

When the user starts a new feature or significant task, read `docs/project-tracker/OVERVIEW.md` first to understand the current project state before beginning work.

## How to Record

Use the helper script to write entries — do not manually compose Markdown:

```bash
# Append a progress log entry
python .agents/skills/project-doc-tracker/scripts/project_tracker.py \
  --project-root . log \
  --change-type <feature|bugfix|refactor|docs|research|decision> \
  --feature-id <feature-id, e.g. venv-packaging> \
  --summary "What was done" \
  --file "path/to/changed/file.py" \
  --next-step "What to do next" \
  --blockers "Blockers, omit if none" \
  --confidence <high|medium|low>

# Sync active items in OVERVIEW.md
python .agents/skills/project-doc-tracker/scripts/project_tracker.py \
  --project-root . sync-item \
  --feature-id <feature-id> \
  --title "Feature title" \
  --status <in_progress|done|blocked> \
  --summary "One-line current status" \
  --next-step "Next step" \
  --file "key file"
```

## Confidence Rules

- `high`: Directly from code changes or explicit user statements
- `medium`: Inferred from multiple signals
- `low`: Speculative conclusion, must be marked "to be confirmed"

## Do Not

- Do not write high-confidence conclusions from memory — check git status or changed files first
- Do not delete or overwrite historical records in PROGRESS.md
- Do not automatically modify AGENTS.md, CLAUDE.md, .cursorrules, or similar rule files

## Tracking Document Location

```text
docs/project-tracker/
├─ OVERVIEW.md     # Project overview, active items table
├─ PROGRESS.md     # Append-only session log
└─ features/       # Detailed feature documentation
```

If `docs/project-tracker/` does not exist, run:

```bash
python .agents/skills/project-doc-tracker/scripts/project_tracker.py --project-root . init
```

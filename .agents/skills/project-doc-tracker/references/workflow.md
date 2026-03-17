# Workflow

## Recommended Operating Sequence

### Mode: init

This mode means "initialize tracker docs", not project bootstrap, dependency install, service startup, or test initialization.

1. Confirm the project root.
2. Run the helper script with `init`.
3. Verify that `docs/project-tracker/OVERVIEW.md` and `docs/project-tracker/PROGRESS.md` exist.
4. If the repo already has meaningful code, inspect the main modules, specs, and recent files.
5. Backfill the tracker instead of leaving it empty:
   - write an initial project summary into `OVERVIEW.md`
   - create or update feature notes for the major modules already present
   - identify which mature modules should later be promoted to formal docs
6. Tell the user how future updates will be captured.

### Mode: log

1. Inspect repo evidence first.
2. Summarize the session in one or two sentences.
3. Decide whether the change is large enough for `PROGRESS.md`:
   - log it when status, architecture, blockers, scope, or a meaningful milestone changed
   - skip a new progress entry when the change is only a tiny fix, wording tweak, or prompt-level back-and-forth
   - merge several nearby small fixes into one session entry when they belong to the same short work burst
4. Identify:
   - change type
   - feature or topic ID
   - changed files
   - next step
   - blockers
   - confidence
5. Run the helper script with `log` only if the session cleared the "meaningful progress" threshold.
6. Update `OVERVIEW.md` with `sync-item` if the active-item table changed.
7. Prefer reusing the same `feature_id` so the overview row is merged instead of duplicated.

Fast heuristic:

> Will this entry help a future agent recover the real project state faster?

If not, skip a new `PROGRESS.md` entry and update only the overview or feature note.

### Mode: recover

1. Read `OVERVIEW.md`.
2. Read the latest log entries from `PROGRESS.md`.
3. If needed, inspect the related spec or changed files.
4. Return a concise "where we are now" summary.

### Mode: feature-note

1. Reuse an existing note if the feature already has a stable ID.
2. Keep `feature_id` slug-like, for example `memory-system` or `project_doc_tracker`.
3. Reject path-like IDs such as `../foo`, `a/b`, or values containing spaces.
4. Capture background, current implementation, key files, risks, and next steps.
5. When useful, also record status evidence and related docs so the note is easier to recover later.
6. Update the note rather than generating a new dated file unless the user explicitly wants snapshots.

### Mode: sync-item

1. Reuse a stable `feature_id`.
2. Update the matching row in `OVERVIEW.md` when the feature already exists.
3. Append a new row only when the feature is new.
4. Maintain `Next Steps` as keyed bullets like `- feature-id: next step`.
5. Maintain `Known Blockers` as keyed bullets and remove a feature-specific blocker when it has been cleared.
6. Preserve an existing formal doc link unless the caller explicitly provides a replacement value.

### Mode: promote-to-doc

1. Confirm the feature is mature enough for a formal document.
2. Read the tracker note, recent progress entries, related specs, and key source files.
3. Decide the output path, typically `docs/modules/<module>.md`.
4. Use `$professional-markdown` to write the long-form document.
5. Update the tracker:
   - add or refresh the formal doc path in the lightweight feature note
   - update the overview row if needed

### Mode: batch-generate-docs

1. Identify mature modules from `OVERVIEW.md`, tracker notes, and the codebase.
2. Prioritize modules with stable architecture or repeated maintenance cost.
3. For each selected module, use `$professional-markdown` to draft the formal document.
4. Record the batch pass in `PROGRESS.md`.

## Evidence Priority

Prefer evidence in this order when multiple sources are available:

1. current repo changes
2. task/spec docs directly related to the current work
3. latest user instruction
4. existing tracker notes
5. existing formal docs under `docs/modules/` or other docs directories

## Confidence Guidance

- `high`: directly supported by current files or explicit user statements
- `medium`: strongly inferred from multiple signals
- `low`: plausible but not confirmed; write conservatively

## What Belongs in `PROGRESS.md`

Good fits:

- feature status changes
- meaningful milestones
- blockers introduced or cleared
- architecture or scope decisions
- batches of related fixes that materially changed the implementation state
- formal-doc promotion passes

Usually not worth a separate entry:

- a single typo fix
- a tiny cosmetic refactor
- a one-line prompt clarification
- several micro-bugfixes that can be summarized together later

When in doubt, ask: "Will this specific entry help a future agent recover project state faster?" If not, prefer updating only `OVERVIEW.md` or the relevant feature note.

## Persistent Rule Installation

When the user wants the tracker behavior to persist across coding sessions in a specific AI tool, prefer copying the matching template content into the target repo's rule file.

- Kiro: copy the rule block from `references/steering-template.md` into `.kiro/steering/project-doc-tracker.md`
- Claude Code: copy `references/tool-rule-templates/claude.md` into `CLAUDE.md`
- Cursor: copy `references/tool-rule-templates/cursor.md` into `.cursorrules`
- Windsurf: copy `references/tool-rule-templates/windsurf.md` into `.windsurfrules`
- Codex: copy `references/tool-rule-templates/codex.md` into `AGENTS.md`

Only use the helper scripts when the user explicitly wants scripted installation.

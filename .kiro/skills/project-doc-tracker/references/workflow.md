# Workflow

## Recommended Operating Sequence

### Mode: init

1. Confirm the project root.
2. Run the helper script with `init`.
3. Verify that `docs/project-tracker/OVERVIEW.md` and `docs/project-tracker/PROGRESS.md` exist.
4. Tell the user how future updates will be captured.

### Mode: log

1. Inspect repo evidence first.
2. Summarize the session in one or two sentences.
3. Identify:
   - change type
   - feature or topic ID
   - changed files
   - next step
   - blockers
   - confidence
4. Run the helper script with `log`.
5. Update `OVERVIEW.md` with `sync-item` if the active-item table changed.
6. Prefer reusing the same `feature_id` so the overview row is merged instead of duplicated.

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
4. Maintain `下一步建议` as keyed bullets like `- feature-id: next step`.
5. Maintain `已知阻塞` as keyed bullets and remove a feature-specific blocker when it has been cleared.
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

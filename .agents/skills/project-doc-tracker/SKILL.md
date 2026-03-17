---
name: project-doc-tracker
description: Track ongoing project progress, decisions, blockers, and next steps in project-local Markdown docs. Use when the user wants Codex to initialize project tracker docs, bootstrap tracker files from an existing codebase, record a coding session, recover context after a pause, generate or update a lightweight feature note, promote a completed feature into a formal module document, or keep long-running project work from being forgotten.
---

# Project Doc Tracker

Use this skill to maintain a lightweight project memory inside the repository.

Prefer this skill when the user asks things like:

- "Record this project update for me."
- "Show me where this project currently stands."
- "Add a short status note for this feature."
- "Help me save the current state so we do not forget it later."
- "Initialize a tracker for this project."
- "Backfill tracker docs for an existing codebase."

## Workflow

### 1. Collect evidence before writing

Before updating tracker docs, inspect the most relevant evidence available:

1. `git status` and, when useful, `git diff --stat` or a focused diff
2. recently modified files
3. relevant `.kiro/specs/` documents
4. the user's latest goal or instruction

Do not write high-confidence progress notes if evidence is weak. When needed, record a cautious summary and mark confidence as `low`.

### 2. Choose the right mode

Use one of these modes:

- `init`: initialize tracker docs only. Create `docs/project-tracker/` and, when the repo already has code, backfill the initial overview and feature notes from existing evidence
- `log`: append a structured session update after a meaningful change
- `sync-item`: merge one feature into the active item table and update keyed next-step or blocker bullets in `OVERVIEW.md`
- `feature-note`: create or update a stable feature note for one topic
- `promote-to-doc`: hand off a completed or stable feature to `$professional-markdown` for a full formal document
- `status`: read the overview and the most recent progress entries to restore context

Use slug-like `feature_id` values such as `memory-system` or `project_doc_tracker`. Do not use spaces, slashes, `..`, or other path-like fragments.

Here, "initialize" means initializing the tracker documentation system, not project bootstrap, dependency install, runtime setup, or test setup.

Treat `log` as a "meaningful progress entry", not a transcript of every prompt or every tiny fix.

### 3. Prefer the helper script for deterministic writes

Use `scripts/project_tracker.py` for file creation and updates instead of hand-editing tracker Markdown whenever practical.

Script path:

- `D:\openGuiclaw\.agents\skills\project-doc-tracker\scripts\project_tracker.py`

Do not use the helper script to generate long-form formal module documentation. That content should be written directly with `$professional-markdown`.

### 4. Promote mature features into formal docs

When a feature becomes `done`, `stable`, or is clearly important enough for long-term maintenance:

1. read the relevant tracker note, progress history, specs, and source files
2. decide the target formal doc location, usually `docs/modules/<name>.md` unless the user wants another docs area
3. invoke the `professional-markdown` skill to produce the long-form document
4. update the tracker note and overview row with the formal doc path

If a feature already has a formal doc path recorded, ordinary `sync-item` updates should preserve that link unless you are explicitly changing it.

Use this mode for both:

- single completed features
- batch documentation passes over multiple mature modules

### 5. Keep the tracker conservative

The tracker is a memory aid, not a source of fabricated truth.

- record what changed
- link the change to evidence when possible
- record blockers explicitly
- record the next step explicitly
- use `low` confidence when you are inferring rather than observing

### 6. Treat history as append-only

`PROGRESS.md` is an audit-style log. Do not delete or silently rewrite old entries. If you need to correct a previous note, append a new correction entry.

### 7. Keep `PROGRESS.md` selective

Only append a `PROGRESS.md` entry when the change is important enough to help future recovery. Good candidates include:

- a feature moved to a new status such as `planned`, `in_progress`, `blocked`, `done`, or `stable`
- a meaningful implementation milestone was reached
- architecture, behavior, or scope changed in a way that future work depends on
- a blocker appeared, changed, or was cleared
- a formal-document handoff happened
- a batch of related fixes together changed the practical state of the feature

Do not append a new progress entry for every user message, every small prompt refinement, every isolated typo fix, or every tiny bug fix that does not change the project's recoverable state.

When several small changes belong to the same short work burst, merge them into one session summary instead of creating multiple near-duplicate entries.

Use this one-line check before appending to `PROGRESS.md`:

> Will this specific entry noticeably help a future agent recover the real project state faster?

If the answer is no, prefer updating only `OVERVIEW.md` or the relevant feature note.

## Tracker Layout

Default project-local storage:

```text
docs/project-tracker/
├─ OVERVIEW.md
├─ PROGRESS.md
└─ features/
   └─ <feature-id>.md
```

Read `references/tracker-format.md` when you need the exact document structure or marker names.

Read `references/workflow.md` when you need the step-by-step operating procedure.

Read `references/prompt-examples.md` when you want ready-to-use prompt templates for initialization, daily updates, recovery, or promote-to-doc flows.

## Practical Rules

- When the user asks to "initialize" this skill, interpret it as "initialize tracker docs" unless they explicitly ask for runtime or bootstrap work.
- Do not auto-edit `AGENTS.md`, `CLAUDE.md`, `.cursorrules`, or similar rule files by default.
- Do not dump raw repo state into the tracker; summarize it.
- Do not treat `PROGRESS.md` as a chat transcript or full bug diary.
- Do not create duplicate feature notes when a stable file for the same feature already exists.
- Do not try to force formal docs into `docs/project-tracker/features/`; keep those notes lightweight.
- When generating formal documentation, reuse `$professional-markdown` instead of extending `project_tracker.py`.
- When the user wants continuous follow-up, explain that the skill can be paired with automation, but the skill alone is not a scheduler.
- If the repo already contains meaningful code, do not leave the freshly initialized tracker mostly empty; scan the codebase and backfill the initial `OVERVIEW.md`, key feature notes, and formal-doc candidates.
- Prefer `OVERVIEW.md` for the current state and `PROGRESS.md` for meaningful history. Most sessions should read the overview first and only inspect recent progress entries when needed.
- If a change only updates wording, formatting, or a trivial local fix without changing the recoverable project state, prefer updating `OVERVIEW.md` or the feature note without appending a new progress entry.
- For Kiro users, installation of the skill does not automatically create `.kiro/steering/project-doc-tracker.md`. Use `references/steering-template.md` as the source and copy the rule block into the target repo.
- For Claude Code, Cursor, Windsurf, and Codex users, use the matching file under `references/tool-rule-templates/` and copy it into the target repo's persistent rule file:
  - `claude.md` -> `CLAUDE.md`
  - `cursor.md` -> `.cursorrules`
  - `windsurf.md` -> `.windsurfrules`
  - `codex.md` -> `AGENTS.md`
- When the user asks for persistent project rules, prefer directly copying the matching template content into the target file rather than adding extra installation layers.

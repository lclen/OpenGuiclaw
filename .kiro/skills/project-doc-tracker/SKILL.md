---
name: project-doc-tracker
description: Track ongoing project progress, decisions, blockers, and next steps in project-local Markdown docs. Use when the user wants Codex to initialize a project tracker, record a coding session, recover context after a pause, generate or update a lightweight feature note, promote a completed feature into a formal module document, or keep long-running project work from being forgotten.
---

# Project Doc Tracker

Use this skill to maintain a lightweight project memory inside the repo.

Prefer this skill when the user asks things like:

- "帮我记录一下这次项目进展"
- "看看这个项目现在做到哪了"
- "给这个功能补一份阶段说明"
- "我怕后面忘了，帮我把当前状态记下来"
- "初始化一个持续跟进项目的文档"

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

- `init`: create `docs/project-tracker/` and the default tracker files
- `log`: append a structured session update after a meaningful change
- `sync-item`: merge one feature into the active item table and update keyed next-step or blocker bullets in `OVERVIEW.md`
- `feature-note`: create or update a stable feature note for one topic
- `promote-to-doc`: hand off a completed or stable feature to `$professional-markdown` for a full formal document
- `status`: read the overview and the most recent progress entries to restore context

Use slug-like `feature_id` values such as `memory-system` or `project_doc_tracker`. Do not use spaces, slashes, `..`, or other path-like fragments.

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

## Practical Rules

- Do not auto-edit `AGENTS.md`, `CLAUDE.md`, `.cursorrules`, or similar rule files by default.
- Do not dump raw repo state into the tracker; summarize it.
- Do not create duplicate feature notes when a stable file for the same feature already exists.
- Do not try to force formal docs into `docs/project-tracker/features/`; keep those notes lightweight.
- When generating formal documentation, reuse `$professional-markdown` instead of extending `project_tracker.py`.
- When the user wants continuous follow-up, explain that the skill can be paired with automation, but the skill alone is not a scheduler.

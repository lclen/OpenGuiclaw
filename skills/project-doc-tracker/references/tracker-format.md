# Tracker Format

## Tracker Root

```text
docs/project-tracker/
├─ OVERVIEW.md
├─ PROGRESS.md
└─ features/
```

## OVERVIEW.md

Use explicit markers so updates are stable even if surrounding headings change.

```markdown
# Project Tracker

## Project Summary
<!-- project-tracker:intro:start -->
To be filled in.
<!-- project-tracker:intro:end -->

## Active Items
<!-- project-tracker:items:start -->
| feature_id | Title | Status | Last Updated | Next Step | Key Files | Formal Doc |
| --- | --- | --- | --- | --- | --- | --- |
<!-- project-tracker:items:end -->

## Latest Session
<!-- project-tracker:session:start -->
To be filled in.
<!-- project-tracker:session:end -->

## Next Steps
<!-- project-tracker:next:start -->
- core-agent: add regression coverage
- memory-system: optimize vector retrieval
<!-- project-tracker:next:end -->

## Known Blockers
<!-- project-tracker:blockers:start -->
- memory-system: vector storage is still in-memory only
<!-- project-tracker:blockers:end -->
```

## PROGRESS.md Entry Shape

Append a new section only for a meaningful session-level update, not for every prompt or every tiny fix:

```markdown
## 2026-03-13T11:20:00+08:00
- change_type: feature
- feature_id: project-doc-tracker
- summary: Reworked the spec from a generic Python utility into a skill-based tracker
- files: a.py, b.md
- next_step: implement the helper script
- blockers: none
- confidence: high
```

## Feature Note Shape

Use stable filenames such as `features/project-doc-tracker.md`.

`feature_id` should be a slug-like identifier containing only letters, numbers, `-`, or `_`.

```markdown
# Feature Note: project-doc-tracker

- feature_id: project-doc-tracker
- title: Project Doc Tracker
- updated_at: 2026-03-13T11:30:00+08:00
- status: in_progress

## Background

...

## Current Implementation Summary

...

## Status Evidence

- changed key files
- completed the main spec tasks

## Key Files

- ...

## Related Docs

- .kiro/specs/example/design.md
- docs/project-tracker/OVERVIEW.md

## Risks and Known Issues

...

## Recommended Next Step

...

## Formal Document

To be filled in.
```

Keep feature notes intentionally lightweight. They are tracker-side memory aids, not replacements for full docs.
They can be slightly richer than a bare card, but should still stay much shorter than `docs/modules/*.md`.

## Progress Selectivity

Use `PROGRESS.md` for recoverable milestones, not exhaustive narration.

Good examples:

- a feature moved from `planned` to `in_progress`
- a blocker was identified or removed
- a group of related bug fixes changed the feature's practical state
- a completed feature was promoted into a formal document

Usually skip a separate entry for:

- a wording tweak
- a tiny isolated fix
- back-and-forth prompting with no meaningful state change

If a small change matters to the current state, prefer reflecting it in `OVERVIEW.md` or the feature note without growing `PROGRESS.md`.

Simple rule of thumb:

> If this entry would not noticeably help a future agent recover project state faster, it probably does not belong in `PROGRESS.md`.

## Overview Block Behavior

- `sync-item` should merge rows by `feature_id`, not overwrite the full table with a single item.
- `Next Steps` should prefer keyed bullets such as `- feature-id: next step`.
- `Known Blockers` should prefer keyed bullets such as `- feature-id: blocker`.
- When a blocker is cleared, remove that feature's keyed blocker entry instead of leaving stale text behind.
- If a row already contains a formal doc path, `sync-item` should preserve it unless a new path is explicitly provided.

## Formal Document Handoff

When a feature is mature, create a full document outside the tracker, usually in `docs/modules/`.

Recommended relationship:

- `docs/project-tracker/features/<feature-id>.md`: lightweight note
- `docs/modules/<module>.md`: formal long-form document

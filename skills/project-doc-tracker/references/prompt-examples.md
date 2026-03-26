# Prompt Examples

## Initialize the Tracker Documentation System

### Empty Repository or New Project

- `Please use $project-doc-tracker to initialize the project tracker documentation system. This should only create tracker docs, not install dependencies, run tests, or start services.`
- `Use $project-doc-tracker to create docs/project-tracker/ for the current repo, including OVERVIEW.md, PROGRESS.md, and features/ as the long-term tracking entry point.`
- `Please use $project-doc-tracker to initialize tracker docs only. Do not treat this as project bootstrap.`

### Existing Codebase

- `Please use $project-doc-tracker to initialize the project tracker documentation system. This repository already has meaningful code, so do not leave empty templates. Scan the main modules and backfill the initial overview and feature notes.`
- `Use $project-doc-tracker to add a progress-tracking documentation layer to this existing project: inspect the code, specs, and recent changes, then initialize the tracker and backfill the key feature cards.`
- `Please use $project-doc-tracker to initialize tracker docs, not the runtime environment. The repo already contains code, so identify the core modules and write an initial project overview.`

### Existing Codebase + Formal Doc Candidates

- `Please use $project-doc-tracker to initialize tracker docs for this existing project and identify which modules should later be handed off to professional-markdown for full formal documentation.`
- `Use $project-doc-tracker to establish long-term project memory for this codebase: initialize the tracker, backfill feature notes, and list formal doc candidates.`
- `Please use $project-doc-tracker to scan the current repository and initialize tracker docs. Do not stop at empty templates. If you find mature modules, mark them as formal-document candidates.`

## Record Daily Progress

- `Please use $project-doc-tracker to record this development update only if it represents meaningful project progress, then refresh OVERVIEW, PROGRESS, and the relevant feature note.`
- `Use $project-doc-tracker to sync the status of memory-system, preserve any existing formal document link, and add status evidence.`
- `Please use $project-doc-tracker to capture today's web-server changes as a single session summary if they meaningfully changed the current state, next step, or blockers.`
- `Please use $project-doc-tracker to log this work only if the entry would clearly help a future agent recover project state faster; otherwise just refresh OVERVIEW and the feature note.`

## Recover Project Context

- `Please use $project-doc-tracker to restore the current project context by reading the overview and recent progress entries, then summarize where we are now.`
- `Use $project-doc-tracker to show the current state, next step, and blockers for project-doc-tracker.`
- `Please use $project-doc-tracker to summarize the active work items and give me a short prioritized next-step list.`

## Maintain a Lightweight Feature Note

- `Please use $project-doc-tracker to update a lightweight feature note for plugin-system, including background, current implementation summary, status evidence, key files, related docs, risks, and the recommended next step.`
- `Use $project-doc-tracker to add a lightweight feature card for im-channels. Keep it concise, but make it strong enough to recover context later.`
- `Please use $project-doc-tracker to update the self-evolution feature note. If a note already exists, update it in place instead of creating a duplicate file.`

## Promote to a Formal Document

- `Please use $project-doc-tracker to identify which done or stable modules are ready for promote-to-doc and give me a candidate list.`
- `Use $project-doc-tracker to read the tracker notes and code, then hand memory-system off to professional-markdown for a full formal document.`
- `Please use $project-doc-tracker to run a batch documentation pass over the current repo, identify mature modules, and mark which ones should get docs/modules formal documentation.`

## Install Persistent Tool Rules

- `Please use $project-doc-tracker to install persistent Kiro steering into this repo by copying the steering template into .kiro/steering/project-doc-tracker.md.`
- `Please use $project-doc-tracker to install a CLAUDE.md rule file for this repo by copying the included Claude template into the project root.`
- `Please use $project-doc-tracker to install Cursor rules for this repository by copying the included Cursor template into .cursorrules.`
- `Please use $project-doc-tracker to install AGENTS.md guidance for Codex by copying the included Codex template into the project root so progress tracking stays persistent across sessions.`

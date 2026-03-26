---
name: professional-markdown
description: Produce highly polished, structured Markdown with strong information architecture, tasteful visual hierarchy, Mermaid diagrams, tables, callouts, and publication-quality formatting. Use when the user asks to write documentation, generate explanations, document architecture, create a README, or produce any high-quality Markdown artifact.
---

# Professional Markdown Architect

Use this skill when the output should feel publication-ready rather than merely correct.

The goal is not just to "write Markdown", but to produce Markdown that is:

- technically accurate
- easy to scan
- visually well-structured
- strong enough for long-term project documentation

## Core Principles

### 1. Gather context before writing

Do not write polished documentation from thin air.

Before drafting:

1. inspect the relevant source files, configs, or existing docs
2. extract the real terminology, architecture boundaries, and workflows
3. identify obvious missing sections and either infer conservatively or ask when the gap is important

### 2. Optimize for information architecture

A strong document should guide the reader from overview to detail.

Good defaults:

- start with a clear title
- immediately follow with a short quote block summarizing status, version, or purpose
- add a table of contents when the document is more than a few sections long
- separate major sections with `---`

### 3. Prefer structure over text walls

When the content is naturally structured, use structure.

Prefer:

- tables for comparisons, parameters, file roles, feature matrices, and settings
- Mermaid diagrams for systems, flows, and interactions
- callouts for important warnings or operational notes
- short paragraphs with strong headings

Avoid long, dense prose when a clearer format exists.

## Recommended Document Shape

### Header Pattern

Every substantial document should usually begin like this:

```markdown
# Document Title

> **Status**: Stable | **Last Updated**: 2026-03-13 | **Purpose**: Short one-line summary
```

### Table of Contents

For documents with more than three major sections, add:

```markdown
## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Usage](#usage)
```

### Standard Section Types

Depending on the task, prefer some combination of:

- Overview
- Goals
- Architecture
- Core Workflow
- Key Files
- Configuration
- Data Model
- Usage
- Troubleshooting
- Known Limitations
- Future Improvements

## Visual Style

### 1. Emphasis

- use bold text for key concepts
- use inline code for commands, file paths, variables, identifiers, and APIs
- keep emphasis intentional rather than noisy

### 2. Tables

Use Markdown tables whenever they increase clarity.

Common cases:

- feature comparison
- file responsibility mapping
- config reference
- component inventory
- risk summary

### 3. Callouts

Use GitHub-style callouts for warnings and high-value notes:

```markdown
> [!IMPORTANT]
> This is a key operational note.
```

### 4. Diagrams

If the structure or flow is easier to explain visually, use Mermaid.

Recommended types:

- `graph TD` or `graph LR` for architecture
- `sequenceDiagram` for workflows and interactions
- `stateDiagram-v2` for state transitions

## Writing Rules

### 1. Code blocks need context

Large code blocks should usually be introduced by a short line explaining what the reader is about to see.

Example:

```markdown
**Configuration example:**

```yaml
...
```
```

### 2. Cross-reference related docs

When other repo docs exist, link them with standard Markdown links instead of repeating everything.

### 3. Be tasteful with emoji

Emoji are optional and should be used sparingly.

Good use cases:

- major section headings in user-facing docs
- small status signals in lists or tables

Avoid emoji clutter in highly technical or operational documents.

## Review Checklist

Before finalizing, quickly check:

1. Did I inspect enough real context?
2. Is the opening summary immediately clear?
3. Should any section be converted into a table?
4. Would a Mermaid diagram help?
5. Are key warnings called out clearly?
6. Is the document easy to scan from top to bottom?
7. Does the output feel like durable documentation rather than chat text?

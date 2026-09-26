# ADR 0002 — Visibility of the history script

- **Status:** accepted (2026-09-26, maintainer's decision)

## Context

Every BlendSolid part is defined by a build123d script (the history). The spec left open whether users see and
edit that script or only interact through the viewport and panels.

## Decision

The script is **hidden from standard users** and **available to advanced users** through an add-on preference
("Show history scripts").

- The script is stored in a `Text` datablock whose name starts with a dot (e.g. `.Part.py`): Blender hides such
  datablocks from its ID menus, so it doesn't clutter the Text Editor for standard users.
- With the preference off: no *Edit Script* button; errors are shown as a plain message without script line numbers.
- With the preference on: *Edit Script* opens the script in a Text Editor; errors show the script line.
- The script remains the single source of truth either way (undo, file storage, Claude via MCP).

## Consequences

- Standard users get a Plasticity-like experience; advanced users and Claude keep "history as code".
- Hand edits by advanced users may produce scripts the interactive tools can't map back (e.g. no parameter block):
  the solid still recomputes, and the panel shows what it can.

# Design proposal: layered pie menu for commands, sidebar for context

- **Status:** proposal, to discuss with the maintainer (not decided, nothing to implement yet)
- **Date:** 2026-09-30
- **Research:** `docs/research/2026-09-30-pie-menus-and-command-access.md`

## Problem

Commands live in five places: the sidebar (New Part, a Draw Solid button, booleans, Edit Script, Recompute),
the toolbar (Draw Solid, Fillet, Push/Pull), Shift+A (primitives), the Object menu (booleans) and Ctrl+Numpad
(booleans). The maintainer finds the sidebar + toolbar mix really uncomfortable, and 3a–3e will add about 30
commands (sketch, extrude, revolve, I/O, mirror, arrays, shell, direct edits, loft/sweep, analysis). The toolbar
and the sidebar don't scale to that.

## Proposal (maintainer's idea, detailed)

1. **One key opens a pie at the cursor (level 0)** with the families of commands.
2. **Choosing a family opens its own pie (level 1)**, centred where the cursor is, with the commands.
3. **The sidebar shows context only**: the active part's parameters, references and warnings, booleans of the
   part, display settings. No command buttons except those that act on the shown context (e.g. a boolean's
   *Select Cutter*).
4. **Two levels, at most 8 items each** (Kurtenbach & Buxton: breadth 8 / depth 2 is the reliable limit; 64
   commands). The most used commands sit on the axes (N, S, E, W).
5. **Fixed positions.** An item that doesn't apply (Booleans with one part selected) stays in its place, greyed
   out, never moves — Blender's pie convention, and what makes the gesture memorable.
6. **Everything also findable by F3** (operators with clear English `bl_label`s), and the existing Shift+A and
   Ctrl+Numpad entries stay as secondary routes.

## The command tree (draft)

Level 0 (Blender fills W, E, S, N, NW, NE, SW, SE in that order):

| Slot | Family | Level 1 (now → later milestone) |
| --- | --- | --- |
| **W** | **Add** | Box, Cylinder, Sphere, Cone, Torus, Wedge, New Part (template) |
| **E** | **Sketch** (3a) | Line, Arc, Circle, Rectangle, Spline, Offset, Trim, Fillet 2D (3a) |
| **S** | **Edit** | Fillet, Chamfer, Push/Pull → Shell/Thicken (3b), Offset Face, Delete Face, Draft (3c) |
| **N** | **Draw Solid** | Box, Cylinder (activate the tool with that shape) → Polygon/Slot later |
| NW | Booleans | Union, Difference, Intersect, Select Cutter, Show Cutters, Remove Boolean |
| NE | Solid from sketch (3a) | Extrude, Revolve (3a) → Loft, Sweep, Pipe (3d) |
| SW | Pattern (3b) | Mirror, Linear Array, Polar Array |
| SE | Part & file | Import STEP/IGES/BREP, Export (3a), Recompute, Edit Script, Analysis (3e), Convert to Quads (3e) |

The four axis slots follow the maintainer's first pie (Add, Draw Solid, Sketch) plus Edit, which holds the
tools used most after a part exists (Fillet, Push/Pull). Families empty until their milestone show greyed out, so
the layout never changes as features arrive. Open: whether Draw Solid, a single tool today, should be a direct
item instead of a family.

## How to build it: three options

| | A. Native pies, chained | B. Pie drawn by BlendSolid | C. A now, B only if needed |
| --- | --- | --- | --- |
| How | `Menu.draw` with `layout.menu_pie()`; level-0 items call `wm.call_menu_pie` for level 1 | A modal operator draws the rings with `gpu`/`blf` and reads the mouse | — |
| Gesture | Two flicks: release (or click) on level 0, then move + click on level 1. One continuous gesture only if the user sets **Confirm Threshold** > 0 in Preferences (Blender source: a pie opened while the key is held inherits the hold) | One continuous gesture while the key is held; level 1 opens on hover or on crossing, like Fusion's second ring | — |
| Look & feel | Blender's own: theme, DPI, icons, numpad and letter accelerators, accessibility | Must re-create theme colours and DPI; Blender's built-in icons are hard to draw from `gpu` [unverified] | — |
| Cost | Small (menus + one keymap item) | Large (modal, drawing, hit testing, tests) and a custom widget in a "100% native UI" project | — |
| Risk | Chained pies may feel like two steps | Maintenance on every Blender UI change | — |

**Recommendation: C.** Build A first. It is native, small and reversible. The literature is on its side:
separate flicks per level are *more* accurate than one zig-zag (Zhao & Balakrishnan 2004: 93% vs 80%). Judge it
in the GUI test and in the 3a usage checkpoint. Build B only if the two-step feel is the complaint, and then as a
separate ADR.

## Which key

Candidates to choose with the maintainer. All go in the add-on keyconfig (user-rebindable), in Object Mode.

1. **A dedicated key**, e.g. one that Blender's default keymap leaves free in Object Mode: to be checked against
   `blender_default.py` and the common add-ons (HardOps uses Q/Shift+Q).
2. **`CLICK_DRAG` of an existing key**, Blender's own "Pie Menu on Drag" pattern: tap keeps the key's action,
   press-and-drag opens the pie. Natural for a gesture menu, since dragging is the gesture.
3. **Right-mouse drag**, like Fusion: right-click keeps the context menu, right-drag opens the pie. Conflicts with
   the right-click-select keymap.

An operator of our own (`blendsolid.call_pie`) with a `poll` lets the key pass through to Blender when BlendSolid
has nothing to offer (`wm_operator_invoke` in `wm_event_system.cc` starts from `OPERATOR_PASS_THROUGH` and
returns it when the poll fails [verified, source]; confirm with a keymap test).

## What happens to the toolbar

The tools (`WorkSpaceTool`) stay registered: the pie activates them with `wm.tool_set_by_id`, and the tool keeps
its header settings and hover gizmos. They collapse into **one BlendSolid group button** in the toolbar, so the
toolbar holds one entry instead of three (and 10+ later).

## First increment (if the maintainer agrees), with a criterion

- Level-0 pie + level-1 pies for the commands that exist today (Add, Draw Solid, Edit, Booleans, Part & file);
  empty families greyed out.
- The chosen key; the sidebar reduced to context; the tools grouped in the toolbar.
- **Criterion:** every command that exists today is reachable in at most two pie choices from the key; the
  sidebar has no command button that doesn't act on the context it shows; headless tests check that every
  pie item's operator is registered and polls correctly in the contexts of the test parts; `gui_check.py` gains
  a step that opens the pie, chooses Edit → Fillet and finds the Fillet tool active.

## Questions for the maintainer

1. Is the level-0 layout right (four axis families: Add W, Sketch E, Edit S, Draw Solid N)?
2. Which key option (dedicated / `CLICK_DRAG` of a key / right-drag)?
3. Are two flicks acceptable to start with (option A), or is the continuous gesture essential from day one?
4. Sidebar: anything you want to keep as buttons?

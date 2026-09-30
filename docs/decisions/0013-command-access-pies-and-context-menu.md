# ADR 0013: Commands from a two-level pie and a selection context menu; the sidebar shows context

- **Status:** accepted (2026-09-30, decided by the maintainer); the pie and its keys built on 2026-09-30 for the
  maintainer's GUI test (E + right-button drag, `docs/research/2026-09-30-pie-key.md`); the rest of the UI pass
  (plan `docs/superpowers/plans/2026-09-30-ui-pass.md`) not built yet
- **Date:** 2026-09-30
- **Research:** `docs/research/2026-09-30-pie-menus-and-command-access.md`
- **Design:** `docs/superpowers/specs/2026-09-30-pie-menus-design.md` (the full reasoning, options and command tree)

## Context

Commands live in five places (sidebar buttons, toolbar tools, Shift+A, the Object menu, Ctrl+Numpad); the
maintainer finds the sidebar + toolbar mix uncomfortable, and milestones 3a–3e add about 30 commands, which
neither the toolbar nor the sidebar scales to.

## Decision

1. **Three routes, one role each.**
   - A **two-level pie** (native Blender pies, chained with `wm.call_menu_pie`) holds the families of commands,
     above all those that create (Add, Draw Solid, Sketch, Solid from Sketch). At most 8 items per level, fixed
     positions; items that don't apply stay greyed out in place. Level 0: W Add, E Sketch, S Edit, N Draw Solid,
     NW Booleans, NE Solid from Sketch, SW Pattern, SE Part & File.
   - A **right-click menu that follows the selection**: BlendSolid entries at the top of
     `VIEW3D_MT_object_context_menu` by selection kind (edge, face, two or more parts, cutter), Blender's own
     entries below a separator.
   - The **sidebar shows context only** (parameters, references and warnings, the part's booleans, display);
     **F3** finds every operator; Shift+A and Ctrl+Numpad stay as secondary routes.
2. **Key:** the pie opens on `CLICK_DRAG` of an existing Object Mode key (tap keeps the key's action), through an
   operator of ours with a `poll` so the event passes through when BlendSolid has nothing to offer; in the add-on
   keyconfig, user-rebindable. **Which key is still open** (candidates to check against Blender 5.2's default
   keymap and HardOps' Q / Shift+Q; the maintainer confirms).
3. **Native chained pies first** (two flicks). A continuous-gesture pie drawn by BlendSolid only if two flicks
   annoy the maintainer in the GUI test, and then as its own ADR.
4. **Not chosen:** a popover at the cursor, single-letter tool keys, a floating bar near the selection, a
   Maya-style hotbox.
5. The WorkSpaceTools stay registered (the pie activates them with `wm.tool_set_by_id`) and collapse into one
   toolbar group.

## Consequences

- 3a's new commands (Sketch tools, Extrude, Revolve, STEP I/O) go into the pie and the right-click menu, not new
  sidebar buttons.
- Built as the "UI pass", once the 3a work in progress is stable and before the 3a usage checkpoint, after two
  cheap GUI checks (how far the level-1 pie recentres; a `CLICK_DRAG` keymap item leaves the tap intact).

# Research: layered pie menus and other ways to reach commands

Date: 2026-09-30. Context: after milestone 2, during 3a. BlendSolid's commands are spread over the sidebar
(`BLENDSOLID_PT_part`: New Part, a Draw Solid button, booleans, script buttons), the toolbar (Draw Solid, Fillet,
Push/Pull as `WorkSpaceTool`s), the Shift+A menu (primitives), the Object menu and Ctrl+Numpad keys (booleans).
The maintainer finds the mix of sidebar and toolbar really uncomfortable and proposes **the sidebar for context
plus a layered pie menu**: a first pie (Add, Draw Solid, Sketch, …) whose items open a second pie, centred where
the chosen item was, with that branch's commands. This note collects what the literature and other products say
before designing it (`docs/superpowers/specs/2026-09-30-pie-menus-design.md`).

Legend: **[verified]** = read in the cited page or source code; **[unverified]** = general product knowledge or
secondary sources that could not be fetched (Blender's manual and Maya's help pages returned only navigation or
were blocked for the fetch tool).

---

## 1. What the research on marking menus says

Marking menus are pie menus that are also gestures: novices wait for the menu and read it; experts flick in the
remembered direction without waiting, so the menu often never draws. Maya (hotbox), Fusion, Houdini and Blender's
own pies descend from them.

- **Breadth 8, depth 2 is the reliable limit for zig-zag gestures.** Kurtenbach and Buxton (CHI 1993) tested
  breadths 4, 8, 12 and depths 1–4 with pen and mouse: "error rates were below 10% for up to menus of breadth 8
  and depth 2"; breadth 8 at depth 3 or more became "error-prone, even for the expert"; breadth 4 stays usable to
  depth 4. The mouse was slower than the pen (2.07 s vs 1.69 s average). [verified]
  <https://www.billbuxton.com/MMExpert.html>
- **On-axis items are faster and more accurate.** Items at N, S, E, W beat diagonal ones significantly; put the
  most used commands on the axes. Breadths can be mixed between levels without problems. [verified] (same page)
- **Separate flicks beat one zig-zag.** Zhao and Balakrishnan (UIST 2004) compared *compound marks* (one
  continuous zig-zag through the levels, what the maintainer's sketch shows) with *simple marks* (one short
  straight flick per level, in quick succession): 93% vs 80% accuracy, about 6% faster, and 8×8×8 = 512 items
  "without degradation in selection accuracy", against about 112 items for compound marks. [verified]
  <https://www.dgp.toronto.edu/~ravin/papers/uist2004_simplemm.pdf>
- Kurtenbach's thesis (the design rationale: novice/expert transition, "press and wait" to show the menu).
  [not read in full] <https://www.research.autodesk.com/app/uploads/2023/03/the-design-and-evaluation.pdf_recHpUp1v9dc1n2CJ.pdf>

Consequence for BlendSolid: two levels of up to 8 items (64 commands) is inside the proven range; a third level is
acceptable only if each level is its own flick (chained pies) rather than one zig-zag.

## 2. Blender's own pie menus

- **8 items, fixed order.** A pie places items in the order W, E, S, N, NW, NE, SW, SE
  (`radial_dir_order` in `source/blender/editors/interface/interface.cc`); more than 8 prints a warning
  ("Pie menus with more than %i items are currently unsupported", `interface_layout.cc`). Enum operators
  with too many items get a **"More"** button that opens a new pie, which the source calls a new *level*
  (`pie_menu_level_create`, `interface_region_menu_pie.cc`). [verified, source on GitHub mirror, main branch]
- **Positions stay fixed.** The 2.72 manual: if some options are missing in a context, "other items won't move to
  fill in the blanks", to keep muscle memory. [verified]
  <https://archive.blender.org/wiki/2015/index.php/Doc:2.6/Manual/Interface/Pie_Menus/>
- **Click style and drag style.** Tap the key → the pie stays open and a click chooses; hold the key, move, release
  → the item under the direction runs. Numpad keys and underlined letters also choose. Preferences: Radius,
  Threshold, Confirm Threshold, Recenter/Tap Key/Animation timeouts. [verified for the styles and some
  preferences; the full list is in the 5.2 manual's Interface → Pie Menus, which the fetch tool couldn't read]
- **A pie can open another pie** (`wm.call_menu_pie` as an item). [verified]
  <https://blenderartists.org/t/my-pie-menu-nested-menu-question/630243>
- **How the second pie behaves — the key finding.** `pie_menu_begin` (`interface_region_menu_pie.cc`): a pie
  opened by a left click, a key release or a click event is always *click style*; a pie opened while the first
  pie's key is **still held** inherits that key (`win->pie_event_type_lock`) and stays in *hold/drag* style.
  [verified, source] So:
  - with default preferences, choosing a level-0 item means releasing the key (or clicking), and the level-1 pie
    opens in click style: **release (or click), then move, then click** — two separate flicks, not one gesture;
  - with **Confirm Threshold** > 0 (user preference `pie_menu_confirm`: "Distance threshold after which
    selection is made (zero to disable)" [verified, `rna_userdef.cc`]; off by default [unverified]), moving past the
    threshold chooses the item *without* releasing the key, so the second pie opens still held and the user can
    keep moving and release on the level-1 item: the continuous gesture of the maintainer's sketch. A 2019
    developer-forum question describes exactly this: chained pies come up in tapping state "unless i call it with
    the Confirm Threshold already enabled". [verified]
    <https://devtalk.blender.org/t/call-pie-menu-in-holding-state/6239>
  - Confirm Threshold is global (all pies in Blender); an add-on shouldn't change the user's preferences.
- **The new pie opens at the mouse**, which after a flick is near the chosen item — the maintainer's sketch.
  [unverified: to check in a GUI test how far it recentres]
- **"Pie Menu on Drag".** Blender's default keymap can bind a pie to `CLICK_DRAG` of a key while a plain
  `CLICK` keeps the key's normal action (`use_pie_click_drag`, `params.pie_value` in
  `scripts/presets/keyconfig/keymap_data/blender_default.py`; used for `` ` ``, Z, Tab, I). Tap = old action,
  press-and-drag = pie. [verified, source] Discussion of adding it to the N-key region pie:
  <https://projects.blender.org/blender/blender/pulls/116207> [verified]
- Blender's designers have pushed back on deep sub-pies because they fight the fast-gesture advantage
  (discussion in the pie design issue). [verified, secondary summary]
  <https://projects.blender.org/blender/blender/issues/56949>
- Native alternatives already present: **F3 Menu Search** (finds any registered operator by name),
  **Shift+Space** tool popup (toolbar at the cursor, with letter hotkeys), **Q Quick Favorites** (user-built
  menu). [unverified, product knowledge]

## 3. Blender add-ons

- **Pie Menu Editor (PME, commercial):** pies, regular menus, pop-up dialogs, *sticky keys* (different actions on
  press and release), *stack keys* (cycle commands on one key), macros, modal operators; nested menus and embedded
  panels in pies. [verified] <https://docs.pie-menu-editor.com/> — the reference for what users expect from custom
  pies in Blender; its hold/release handling of nested pies wasn't documented on the page.
- **3D Viewport Pie Menus** (official extension): Blender's classic set of pies (modes, views, shading, snapping…),
  one level each. [verified exists] <https://extensions.blender.org/add-ons/viewport-pie-menus/>
- **Hard Ops:** a **dynamic Q menu** whose first three items change with the workflow state ("based off of the
  workflow in HOPS and changes dynamically"; two objects selected → booleans appear), and a Shift+Q pie with the
  same dynamic options; object-type-specific menus. [verified]
  <https://hardops-manual.readthedocs.io/en/latest/menu_system/>
- **Gesture Helper** (extensions.blender.org): gesture menus drawn by the add-on, "sub-level gestures", per-mode
  menus, a Maya hotbox preset. [verified, extension page] <https://extensions.blender.org/add-ons/gesture-helper/>
  — proof that a custom-drawn, nested gesture menu is feasible in Blender's Python API.
- NodePie: nested pies to add nodes. [verified exists] <https://github.com/b-init/NodePie>

## 4. Other 3D and CAD products

- **Fusion — marking menu on right click.** Right-click on the canvas: a radial ring of 8 commands (Design
  workspace: Repeat last command, PressPull, Redo, Hole, Sketch, Move/Copy, Undo, Delete) plus an overflow
  context menu below it. **Moving over the bottom command reveals a second radial level** with 8 sketch commands
  (Line, Offset, 2-Point Rectangle, Fit Point Spline…) — a hover-opened level, like the maintainer's sketch.
  Gestures work without showing the menu ("right-click, hold, and drag down first, then in the direction of where
  the command appears"). The ring **changes with workspace, toolbar tab, environment and active command** (Surface
  tab: Hole → Patch). [verified]
  <https://help.autodesk.com/cloudhelp/ENU/Fusion-GetStarted/files/GUID-6514ABC1-CB75-4F0B-AB0E-316FAD36BA93.htm>
- **Houdini — radial menus.** 8 positions; three styles: hold the key and release, tap then click, press and drag
  (flick, "if you're used to marking menus"). Submenus open by **clicking** (double-click jumps into it) and the
  **opposite slot becomes "back"**; numpad 1–9 pick directions; menus can be generated by Python scripts from the
  current state. Defaults: X snapping, C "current" menu, V view. [verified]
  <https://www.sidefx.com/docs/houdini/basics/radialmenus.html>
- **Plasticity — radial menus + command palette.** Radial menus are user-bound (two defaults: selection mode,
  viewport settings) and defined in `.radial.json` files; a radial can call another radial; hold the key and
  release on an item, or click. **Not contextual** to the selection. The main command access is the **Command
  Palette (F)**: type to filter, Enter to run, right-click a command to bind a shortcut or add a favourite.
  [verified] <https://doc.plasticity.xyz/plasticity-essentials/radial-menu>,
  <https://doc.plasticity.xyz/plasticity-essentials/plasticity-interface/command-palette>
- **Shapr3D — selection-based adaptive UI.** Select first, and the tools that fit the selection are offered: a face
  → Offset Face; a sketch profile → Extrude; a body → Move/Rotate; a line + a face → Rotate around axis; profile +
  axis → Revolve; a "More" entry lists the other valid tools. Clicking empty space confirms. [verified]
  <https://support.shapr3d.com/hc/en-us/articles/7873882619548-Adaptive-user-interface>
- **Modo — pie menus and popovers.** Pies on keyboard shortcuts (Ctrl/Cmd+Space by default), max 8 items, built
  in the Forms Editor; option to open immediately or on an extra click. Popovers: any form at the cursor
  (Alt+Space quick-access popover with transform, snapping, workplane…), dismissed by leaving them, pinnable.
  [verified] <https://learn.foundry.com/modo/content/help/pages/modo_interface/ui_conventions.html>
- **Maya — hotbox.** Hold the spacebar: all menus around the cursor plus marking menus in five zones (north, south,
  east, west, centre), each user-customizable. [unverified: Autodesk's page blocked the fetch tool]
  <https://knowledge.autodesk.com/support/maya/learn-explore/caas/CloudHelp/cloudhelp/2018/ENU/Maya-Customizing/files/GUID-F182139D-1E00-44E6-9D79-4AF053860EDA-htm.html>

## 5. The patterns, side by side

| Pattern | Who | Strength | Weakness |
| --- | --- | --- | --- |
| Layered pie / marking menu | Fusion, Houdini, Maya, Blender, Modo | Fast, learnable into gestures; 64 commands in 2 flicks | Needs a free key; hard to discover beyond 2 levels |
| Command palette / search | Plasticity (F), Blender (F3) | Finds everything, nothing to learn | Typing; slow for frequent commands |
| Selection-based suggestions | Shapr3D, HOps dynamic Q, Fusion's contextual ring | Shows only what applies now | Items move, so no muscle memory |
| Tool shelf / toolbar | Blender, SolidWorks, Fusion | Discoverable, visible state | Far from the cursor; clutter (the current complaint) |
| Popover at the cursor | Modo, Blender Shift+Space | Full controls, not just commands | Not a gesture |

What the good products combine: **one gesture menu for frequent commands** + **search for everything** + **a
panel for the current object's parameters**. None relies on a toolbar alone.

## 6. Open points to settle in the design

1. Chained native pies (two flicks, or one continuous gesture only with Confirm Threshold) versus a pie drawn by
   BlendSolid (hover or crossing opens the next level while the key is held, like Fusion's second ring).
2. Which key: a dedicated key, `CLICK_DRAG` of an existing key (tap keeps its action), or right-mouse drag
   (Fusion's convention; conflicts with right-click-select keymaps).
3. Contextual or fixed first level: Blender's convention and the literature favour fixed positions; Shapr3D and
   HOps show the value of hiding what doesn't apply. Fixed positions with inactive items greyed out is the middle
   way.
4. What stays in the toolbar: `WorkSpaceTool`s must stay registered for the pie to activate them
   (`wm.tool_set_by_id`), but they can collapse into one BlendSolid group.

"""The worker starts as soon as the user shows intent to use BlendSolid, so the first part appears without the
worker's ~2 s start: warm_up() schedules a start; the sidebar panel, the Shift+A menu and the Draw Solid tool
call it."""
from types import SimpleNamespace

import bpy
import pytest

from blendsolid import ops_add, ops_draw, runtime, ui


@pytest.fixture
def calls(monkeypatch):
    seen = []
    monkeypatch.setattr(runtime, "warm_up", lambda: seen.append(1))
    return seen


def test_warm_start_starts_the_worker_once(clean):
    runtime.reset_state()
    runtime._warm_start()
    assert runtime.client().state in {"starting", "idle"}
    proc = runtime.client()._proc
    runtime._warm_start()  # already running: nothing new
    assert runtime.client()._proc is proc


class Layout:
    def __getattr__(self, name):
        return lambda *a, **k: self


def test_panel_menu_and_tool_warm_up(clean, calls):
    ui.BLENDSOLID_PT_part.draw(SimpleNamespace(layout=Layout()), SimpleNamespace(object=None, scene=bpy.context.scene))
    ops_add.VIEW3D_MT_blendsolid_add.draw(SimpleNamespace(layout=Layout()), bpy.context)
    ops_draw.BLENDSOLID_GGT_draw_hover.setup(SimpleNamespace(gizmos=SimpleNamespace(new=lambda idname: None)),
                                              bpy.context)
    assert len(calls) == 3

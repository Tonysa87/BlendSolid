"""Keeps every BlendSolid part's mesh in sync with its script, through the worker.

A timer runs tick(): it applies worker events, then submits every part whose script hash differs from the
hash stored on its mesh. Parameter edits, script edits, undo/redo and file loads all converge through this
single path; nothing is decided in undo handlers (evaluated data isn't ready there — spike finding).
"""
import bpy
from bpy.app.handlers import persistent

from . import part, paths
from .client import WorkerClient, WorkerStartError

TICK_INTERVAL = 0.05
_client = None
_inflight = {}  # object name -> script hash being computed
_failed = {}    # object name -> script hash that failed (not resubmitted until the script changes)


def client():
    global _client
    if _client is None:
        _client = WorkerClient(paths.python_executable(), paths.server_script(), paths.worker_libs(),
                               paths.pycache_dir(__package__))
    return _client


def reset_state():
    _inflight.clear()
    _failed.clear()


def force(obj):
    """Recompute even if the script is unchanged (the Recompute button)."""
    _failed.pop(obj.name, None)
    if part.HASH_KEY in obj.data:
        del obj.data[part.HASH_KEY]


def _handle(event):
    kind = event["type"]
    if kind == "crashed":
        for key, tag in event.get("dropped", []):
            if _inflight.get(key) == tag:
                del _inflight[key]      # resubmitted by the next tick (restarting the worker)...
            if event["key"] is None:    # ...unless the worker can't even start: don't loop
                _failed[key] = tag
                obj = bpy.data.objects.get(key)
                if obj is not None:
                    part.set_error(obj, f"The geometry worker failed: {event['error']}")
    if kind not in ("result", "crashed") or not event.get("key"):
        return
    key, tag = event["key"], event["tag"]
    if _inflight.get(key) == tag:
        del _inflight[key]
    obj = bpy.data.objects.get(key)
    if obj is None or obj.blendsolid_script is None:
        return
    if tag != part.source_hash(part.source_of(obj)):
        return  # stale: the script changed meanwhile, the next tick submits the new one
    if kind == "result" and event["ok"]:
        _failed.pop(key, None)
        part.apply_result(obj, event)
    else:
        _failed[key] = tag
        message = event["error"] if kind == "result" else f"The geometry worker crashed: {event['error']}"
        part.set_error(obj, message, event.get("line"))


def tick():
    c = client()
    for event in c.poll():
        _handle(event)
    part.ensure_unique_scripts()
    for obj in part.part_objects():
        source = part.source_of(obj)
        tag = part.source_hash(source)
        if tag == part.applied_hash(obj):
            if obj.blendsolid_error:  # the script matches the mesh again: any earlier error is now stale
                part.set_error(obj, "")
            continue
        if tag in (_inflight.get(obj.name), _failed.get(obj.name)):
            continue
        part.sync_params(obj, source)
        try:
            c.submit(obj.name, source, tag)
        except WorkerStartError as e:
            _failed[obj.name] = tag
            part.set_error(obj, f"Cannot start the geometry worker: {e}")
            continue
        _inflight[obj.name] = tag
    return TICK_INTERVAL


def _timer():
    try:
        return tick()
    except Exception as e:  # a timer that raises is unregistered by Blender: log and keep running
        print(f"BlendSolid: {type(e).__name__}: {e}")
        return 1.0


@persistent
def _on_load(*_):
    reset_state()


def register():
    bpy.app.handlers.load_post.append(_on_load)
    bpy.app.timers.register(_timer, first_interval=TICK_INTERVAL, persistent=True)


def unregister():
    global _client
    if bpy.app.timers.is_registered(_timer):
        bpy.app.timers.unregister(_timer)
    if _on_load in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_on_load)
    if _client is not None:
        _client.stop()
        _client = None
    reset_state()

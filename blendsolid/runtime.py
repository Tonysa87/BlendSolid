"""Keeps every BlendSolid part's mesh in sync with its script, through the worker.

A timer runs tick(): it applies worker events, then submits every part whose script hash differs from the
hash stored on its mesh. Parameter edits, script edits, undo/redo and file loads all converge through this
single path; nothing is decided in undo handlers (evaluated data isn't ready there — spike finding).
"""
import bpy
from bpy.app.handlers import persistent

from . import part, paths, trust
from .client import WorkerClient, WorkerStartError

TICK_INTERVAL = 0.05
_client = None
_inflight = {}  # object name -> script hash being computed
_failed = {}    # object name -> script hash that failed (not resubmitted until the script changes)
_synced = {}    # object name -> script hash its blendsolid_params were last synced from


def client():
    global _client
    if _client is None:
        _client = WorkerClient(paths.python_executable(), paths.server_script(), paths.worker_libs(),
                               paths.pycache_dir(__package__))
    return _client


def reset_state():
    _inflight.clear()
    _failed.clear()
    _synced.clear()


def force(obj):
    """Recompute even if the script is unchanged (the Recompute button)."""
    _failed.pop(obj.name, None)
    _synced.pop(obj.name, None)
    if part.HASH_KEY in obj.data:
        del obj.data[part.HASH_KEY]


def _handle(event):
    kind = event["type"]
    if kind == "crashed":
        for key, drop_tag in event.get("dropped", []):
            if _inflight.get(key) == drop_tag:
                del _inflight[key]      # resubmitted by the next tick (restarting the worker)...
            if event["key"] is None:    # ...unless the worker can't even start: don't loop
                _failed[key] = drop_tag
                obj = bpy.data.objects.get(key)
                if obj is not None:
                    part.set_error(obj, f"The geometry worker failed: {event['error']}", tag=drop_tag)
    if kind not in ("result", "crashed") or not event.get("key"):
        return
    key, tag = event["key"], event["tag"]
    if _inflight.get(key) == tag:
        del _inflight[key]
    obj = bpy.data.objects.get(key)
    if obj is None or obj.blendsolid_script is None or not trust.is_trusted(obj):
        return
    if tag != part.source_hash(part.source_of(obj)):
        return  # stale: the script changed meanwhile, the next tick submits the new one
    if kind == "result" and event["ok"]:
        _failed.pop(key, None)
        part.apply_result(obj, event)
    else:
        _failed[key] = tag
        message = event["error"] if kind == "result" else f"The geometry worker crashed: {event['error']}"
        part.set_error(obj, message, event.get("line"), tag)


def _mirror_to_siblings(primary, source, tag):
    """Objects sharing primary's mesh are never reconciled themselves (see part.primary_objects()), but
    their own blendsolid_params/blendsolid_error must still reflect the primary's current state. `source`
    and `tag` are whatever tick() already computed for primary (possibly None, if that failed early)."""
    siblings = part.mesh_siblings(primary)
    if not siblings:
        return
    primary_state = (primary.blendsolid_error, primary.blendsolid_error_line, part.error_tag(primary))
    for sib in siblings:
        if source is not None and _synced.get(sib.name) != tag:
            try:
                part.sync_params(sib, source)
                _synced[sib.name] = tag
            except Exception:
                pass  # mirroring must never break the tick over a params-parsing hiccup on a sibling
        sib_state = (sib.blendsolid_error, sib.blendsolid_error_line, part.error_tag(sib))
        if sib_state != primary_state:  # e.g. ui._on_param_value already wrote this same state to sib too
            part.set_error(sib, primary.blendsolid_error, primary.blendsolid_error_line, part.error_tag(primary))


def tick():
    c = client()
    for event in c.poll():
        try:
            _handle(event)
        except Exception as e:  # one malformed/unexpected event must not stop the others from being applied
            key, tag = event.get("key"), event.get("tag")
            if key:
                _inflight.pop(key, None)
                if tag is not None:
                    _failed[key] = tag  # don't resubmit the exact tag whose result we just failed to handle
                obj = bpy.data.objects.get(key)
                if obj is not None:
                    part.set_error(obj, f"Internal error handling the worker event: {type(e).__name__}: {e}",
                                   event.get("line"), tag)

    part.ensure_unique_scripts()
    worker_start_error = None  # once the worker itself fails to start, don't retry it for every other part
    for obj in part.primary_objects():
        source = tag = None
        try:
            source = part.source_of(obj)
            tag = part.source_hash(source)

            failed_tag = _failed.get(obj.name)
            if failed_tag is not None and failed_tag != tag:
                del _failed[obj.name]  # that record no longer refers to the current script: drop it

            error_tag = part.error_tag(obj)
            if error_tag is not None and error_tag != tag:
                # the error on record (runtime- or UI-set — see part.set_error) was for a script that's no
                # longer current: it is now stale. An error with no tag at all is never touched here.
                part.set_error(obj, "")

            if _synced.get(obj.name) != tag:
                part.sync_params(obj, source)
                _synced[obj.name] = tag

            if tag == part.applied_hash(obj):
                continue
            if not trust.is_trusted(obj):
                continue  # ADR 0004: keep showing the cached mesh, never run the script
            if tag in (_inflight.get(obj.name), _failed.get(obj.name)):
                continue

            if worker_start_error is not None:
                # the worker already failed to start earlier in this same tick: don't call submit() again
                # (it would just block up to start_timeout once more); mark this part failed the same way.
                _failed[obj.name] = tag
                part.set_error(obj, f"Cannot start the geometry worker: {worker_start_error}", tag=tag)
                continue
            try:
                c.submit(obj.name, source, tag)
            except WorkerStartError as e:
                worker_start_error = e
                _failed[obj.name] = tag
                part.set_error(obj, f"Cannot start the geometry worker: {e}", tag=tag)
                continue
            _inflight[obj.name] = tag
        except Exception as e:  # one object's failure must not stop the others from being reconciled
            _inflight.pop(obj.name, None)
            if tag is None:  # the exception happened before the tag was even computed: try once more
                try:
                    tag = part.source_hash(part.source_of(obj))
                except Exception:
                    tag = None  # still unknown: leave the error untagged rather than guess wrong
            if tag is not None:
                _failed[obj.name] = tag  # don't resubmit the exact tag that just failed to reconcile
            part.set_error(obj, f"Internal error while reconciling: {type(e).__name__}: {e}", tag=tag)
        finally:
            try:
                _mirror_to_siblings(obj, source, tag)
            except Exception:
                pass  # mirroring must never make the remaining primaries in this tick get skipped
    return TICK_INTERVAL


def _timer():
    try:
        return tick()
    except Exception as e:  # a timer that raises is unregistered by Blender: log and keep running
        print(f"BlendSolid: {type(e).__name__}: {e}")
        return 1.0


def part_status(obj):
    """What the panel says about obj's part beyond its error: "untrusted" (ADR 0004) or None."""
    if not trust.is_trusted(obj):
        return "untrusted"
    return None


def _reset_trust():
    trust.reset_for_file(bpy.context.preferences, bpy.data.filepath)


@persistent
def _on_load(*_):
    reset_state()
    _reset_trust()


def register():
    _reset_trust()  # the add-on may be enabled with a file already open: that file's parts came from disk
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

"""Keeps every BlendSolid part's mesh in sync with its script, through the worker.

A timer runs tick(): it applies worker events, then submits every part whose script hash differs from the
hash stored on its mesh. Parameter edits, script edits, undo/redo and file loads all converge through this
single path; nothing is decided in undo handlers (evaluated data isn't ready there — spike finding).
"""
import atexit

import bpy
from bpy.app.handlers import persistent

from . import deps, part, paths, trust
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


def _local_object(name):
    """Runtime state is keyed by the primary's object NAME: stable within a session (across undo/redo, unlike
    Python references), readable in errors, and unique, because only LOCAL objects are ever submitted
    (part.part_groups() leaves library parts out) and local object names are unique. The lookup must
    therefore also be local-only: a linked library object may carry the same name."""
    return bpy.data.objects.get((name, None))


def _handle(event, factor):
    kind = event["type"]
    if kind == "crashed":
        for key, drop_tag in event.get("dropped", []):
            if _inflight.get(key) != drop_tag:
                continue
            del _inflight[key]          # resubmitted by the next tick (restarting the worker)...
            if event["key"] is None:    # ...unless the worker can't even start: don't loop
                _failed[key] = drop_tag
                obj = _local_object(key)
                if obj is not None:
                    part.set_error(obj, f"The geometry worker failed: {event['error']}", tag=drop_tag)
    if kind not in ("result", "crashed") or not event.get("key"):
        return
    key, tag = event["key"], event["tag"]
    if _inflight.get(key) != tag:
        return  # not (or no longer) awaited, e.g. submitted before a file load reset the state: ignore it
    del _inflight[key]
    obj = _local_object(key)
    if obj is None or obj.blendsolid_script is None or part.is_linked(obj) or not trust.is_trusted(obj):
        return
    if tag != part.current_tag(obj, factor):
        return  # stale: the script changed meanwhile, the next tick submits the new one
    if obj.data.is_editmode:
        return  # a mesh can't be rebuilt in Edit Mode: drop it, the tick resubmits after leaving Edit Mode
    if kind == "result" and event["ok"]:
        _failed.pop(key, None)
        part.apply_result(obj, event, factor)
    else:
        _failed[key] = tag
        message = event["error"] if kind == "result" else f"The geometry worker crashed: {event['error']}"
        part.set_error(obj, message, event.get("line"), tag)


def _mirror_to_siblings(primary, siblings, source, tag):
    """Objects sharing primary's mesh are never reconciled themselves (see part.part_groups()), but their
    own blendsolid_params/blendsolid_error must still reflect the primary's current state. `source` and
    `tag` are whatever tick() already computed for primary (possibly None, if that failed early)."""
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


def _poll_events(factor):
    if _client is None:
        return
    for event in _client.poll():
        try:
            _handle(event, factor)
        except Exception as e:  # one malformed/unexpected event must not stop the others from being applied
            key, tag = event.get("key"), event.get("tag")
            if key:
                _inflight.pop(key, None)
                if tag is not None:
                    _failed[key] = tag  # don't resubmit the exact tag whose result we just failed to handle
                obj = _local_object(key)
                if obj is not None:
                    part.set_error(obj, f"Internal error handling the worker event: {type(e).__name__}: {e}",
                                   event.get("line"), tag)


def tick():
    factor = part.unit_factor()  # ADR 0003; part of every tag, so a unit scale change recomputes every part
    _poll_events(factor)
    groups = part.part_groups()  # built once per tick: everything below is linear in the number of objects
    index = deps.part_index(groups)
    part.ensure_unique_scripts(groups, lambda o: deps.tag_of(o, factor, index))
    part.ensure_unique_part_ids(groups)
    index = deps.part_index(groups)  # again: Shift+D copies just got their own script, hence their own id
    memo = {}  # dependency results shared by every part of this tick
    worker_error = None  # once the worker itself fails to start, don't retry it for every other part
    for objs in sorted(groups.values(), key=lambda g: g[0].name):
        obj, siblings = objs[0], objs[1:]
        source = tag = None
        try:
            source = part.source_of(obj)
            dep_error = None
            try:
                resolved = deps.resolve(obj, source, factor, index, memo)
            except deps.DepError as e:
                dep_error = str(e)
                resolved = deps.Resolved(deps.error_tag(source, factor, dep_error))
            tag = resolved.tag

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
            if dep_error is not None:  # a cutter is missing, untrusted, scaled, or parts form a loop
                if (obj.blendsolid_error, part.error_tag(obj)) != (dep_error, tag):
                    part.set_error(obj, dep_error, tag=tag)  # only on change: no property write per tick
                continue
            if obj.data.is_editmode:
                continue  # rebuilt once the mesh (shared by every object of the part) leaves Edit Mode
            if tag in (_inflight.get(obj.name), _failed.get(obj.name)):
                continue

            if worker_error is None:
                try:
                    client().submit(obj.name, source, tag, deps=resolved.deps)
                except (WorkerStartError, FileNotFoundError) as e:  # FileNotFoundError: no worker libraries
                    worker_error = e
            if worker_error is not None:
                # the worker failed to start (in this tick): don't try again for every other part (it could
                # block up to start_timeout each time); mark the part failed until its script changes.
                _failed[obj.name] = tag
                part.set_error(obj, f"Cannot start the geometry worker: {worker_error}", tag=tag)
                continue
            _inflight[obj.name] = tag
        except Exception as e:  # one object's failure must not stop the others from being reconciled
            _inflight.pop(obj.name, None)
            if tag is None:  # the exception happened before the tag was even computed: try once more
                try:
                    tag = deps.tag_of(obj, factor, index)
                except Exception:
                    tag = None  # still unknown: leave the error untagged rather than guess wrong
            if tag is not None:
                _failed[obj.name] = tag  # don't resubmit the exact tag that just failed to reconcile
            part.set_error(obj, f"Internal error while reconciling: {type(e).__name__}: {e}", tag=tag)
        finally:
            if siblings:
                try:
                    _mirror_to_siblings(obj, siblings, source, tag)
                except Exception:
                    pass  # mirroring must never make the remaining primaries in this tick get skipped
    global _last_activity
    activity = (frozenset(_inflight), _client.state if _client is not None else "stopped")
    if activity != _last_activity:  # the panel's "Computing…" line only changes here: redraw it then
        _last_activity = activity
        _redraw_panels()
    return TICK_INTERVAL


def _timer():
    try:
        return tick()
    except Exception as e:  # a timer that raises is unregistered by Blender: log and keep running
        print(f"BlendSolid: {type(e).__name__}: {e}")
        return 1.0


def part_status(obj):
    """What the panel says about obj's part beyond its error: "linked" (from a library, read-only),
    "untrusted" (ADR 0004), "edit_mode" (stale, rebuilt after leaving Edit Mode), "starting" (being
    computed while the worker is still starting), "computing", or None."""
    if part.is_linked(obj):
        return "linked"
    if not trust.is_trusted(obj):
        return "untrusted"
    if obj.data.is_editmode and part.current_tag(obj) != part.applied_hash(obj):
        return "edit_mode"
    mesh = obj.data
    for key in _inflight:  # keyed by the part's primary, which shares obj's mesh (few entries: no full scan)
        primary = _local_object(key)
        if primary is not None and primary.data == mesh:
            return "starting" if _client is not None and _client.state == "starting" else "computing"
    return None


def _redraw_panels():
    wm = getattr(bpy.context, "window_manager", None)
    for window in (wm.windows if wm is not None else ()):
        if window.screen is None:
            continue
        for area in window.screen.areas:
            if area.type == "VIEW_3D":
                for region in area.regions:
                    if region.type == "UI":
                        region.tag_redraw()


_last_activity = None


def _reset_trust():
    try:
        filepath = bpy.data.filepath
    except AttributeError:
        # enabled during Blender's startup, while bpy.data is still restricted: no file is open yet, and the
        # startup/command-line file's load_post (_on_load) will apply the rule to it. Until then: unsaved file.
        filepath = ""
    trust.reset_for_file(bpy.context.preferences, filepath)


@persistent
def _on_load(*_):
    reset_state()
    _reset_trust()


def _kill_worker_at_exit():
    """Blender doesn't call unregister() on quit: make sure the worker goes away with it (the worker also
    watches its parent by itself, for crashes and kills where atexit doesn't run)."""
    if _client is not None:
        _client.kill()


def register():
    atexit.register(_kill_worker_at_exit)
    _reset_trust()  # the add-on may be enabled with a file already open: that file's parts came from disk
    bpy.app.handlers.load_post.append(_on_load)
    bpy.app.timers.register(_timer, first_interval=TICK_INTERVAL, persistent=True)


def unregister():
    global _client
    atexit.unregister(_kill_worker_at_exit)
    if bpy.app.timers.is_registered(_timer):
        bpy.app.timers.unregister(_timer)
    if _on_load in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_on_load)
    if _client is not None:
        _client.stop()
        _client = None
    reset_state()

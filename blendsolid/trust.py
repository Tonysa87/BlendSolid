"""Script trust (ADR 0004): may BlendSolid run the history scripts of the open file?

A part's script is arbitrary Python, so running it is subject to the same rule Blender applies to scripts
embedded in a .blend (Preferences > Save & Load > Auto Run Python Scripts, and its excluded paths):

- parts of a loaded file run only if Auto Run is on and the file isn't under an excluded path, or after the
  user presses "Trust Scripts in This File" (session only: never saved, forgotten on the next file load);
- scripts created in this session (New Part, and copies of an already trusted script) are always trusted.

Trust is decided per Text datablock, by `session_uid` (stable across undo/redo and renames in a session):
an object that adopts an untrusted script (e.g. Link Object Data onto a loaded part) becomes untrusted.

bpy-free at module level: the preferences are passed in, so the matching rule is unit-testable.
"""
import fnmatch
import sys

_file_trusted = False
_trusted_texts = set()  # session_uid of the Text datablocks created (or trusted) in this session


def autoexec_excluded(filepath, entries, windows=sys.platform == "win32"):
    """Does one of Blender's excluded auto-run paths match `filepath`? `entries` are (path, use_glob)
    pairs. Mirrors BKE_autoexec_match(): a glob is an fnmatch pattern, any other entry is a plain prefix
    of the file path; both case-insensitive on Windows. Empty entries are ignored."""
    if windows:
        filepath = filepath.lower()
    for path, use_glob in entries:
        if not path:
            continue
        if windows:
            path = path.lower()
        if use_glob:
            if fnmatch.fnmatchcase(filepath, path):
                return True
        elif filepath.startswith(path):
            return True
    return False


def file_trusted_by_prefs(prefs, filepath):
    """Blender's own rule for the file at `filepath` ("" for an unsaved file, e.g. the startup file)."""
    if not prefs.filepaths.use_scripts_auto_execute:
        return False
    if not filepath:
        return True
    return not autoexec_excluded(filepath, [(p.path, p.use_glob) for p in prefs.autoexec_paths])


def reset_for_file(prefs, filepath):
    """A file was just loaded (or the add-on was just enabled with a file open): forget every session trust
    decision and apply Blender's auto-run rule to it."""
    global _file_trusted
    _trusted_texts.clear()
    _file_trusted = file_trusted_by_prefs(prefs, filepath)


def trust_file():
    """The "Trust Scripts in This File" button: every script of the open file may run, until the next load."""
    global _file_trusted
    _file_trusted = True


def file_trusted():
    return _file_trusted


def mark_trusted(text):
    _trusted_texts.add(text.session_uid)


def text_trusted(text):
    return _file_trusted or text.session_uid in _trusted_texts


def is_trusted(obj):
    script = obj.blendsolid_script
    return script is not None and text_trusted(script)

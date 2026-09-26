"""Pure part of the script-trust rule (ADR 0004): which files Blender's excluded auto-run paths cover."""
from types import SimpleNamespace

from blendsolid import trust


def prefs(auto_run, entries=()):
    return SimpleNamespace(filepaths=SimpleNamespace(use_scripts_auto_execute=auto_run),
                           autoexec_paths=[SimpleNamespace(path=p, use_glob=g) for p, g in entries])


def test_excluded_prefix_match():
    assert trust.autoexec_excluded("/home/u/downloads/a.blend", [("/home/u/downloads/", False)])
    assert not trust.autoexec_excluded("/home/u/work/a.blend", [("/home/u/downloads/", False)])


def test_excluded_glob_match():
    assert trust.autoexec_excluded("/x/y/untrusted_part.blend", [("*untrusted*", True)])
    assert not trust.autoexec_excluded("/x/y/part.blend", [("*untrusted*", True)])


def test_empty_entries_are_ignored():
    assert not trust.autoexec_excluded("/x/a.blend", [("", False), ("", True)])


def test_windows_comparison_is_case_insensitive():
    assert trust.autoexec_excluded("C:\\Users\\U\\Downloads\\a.blend", [("c:\\users\\u\\downloads", False)],
                                   windows=True)
    assert trust.autoexec_excluded("C:\\X\\A.BLEND", [("*.blend", True)], windows=True)
    assert not trust.autoexec_excluded("/X/A.blend", [("/x/", False)], windows=False)


def test_file_trusted_needs_auto_run():
    assert not trust.file_trusted_by_prefs(prefs(False), "/x/a.blend")
    assert trust.file_trusted_by_prefs(prefs(True), "/x/a.blend")
    assert not trust.file_trusted_by_prefs(prefs(True, [("/x/", False)]), "/x/a.blend")
    assert trust.file_trusted_by_prefs(prefs(True, [("/x/", False)]), "")  # unsaved file: only the switch

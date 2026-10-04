"""Imported solids' shapes, stored in the .blend (ADR 0016).

A blob is a solid as compressed binary BRep in base64, in a Text datablock of its own (`.<part>.brep`, hidden like
part scripts) tagged with its id (`bs_blob_id`, the SHA-256 of the compressed bytes). The script of a part that
imports it holds `bs_blobs = {id: <blob Text>}`: an ID pointer, so the blob is saved, appended, linked and copied
along with the script. The script's `imported("<id>")` is what counts: a blob is looked up by id in the script's
pointers first, then among every local blob Text.
"""
import bpy

BLOB_KEY = "bs_blob_id"
BLOBS_KEY = "bs_blobs"     # on a part's script: {blob id: blob Text}
SOURCE_KEY = "bs_source"   # on a blob Text: the file it was imported from (for a future Reload)
LINE = 76                  # base64 characters per line (worker exchange.BLOB_LINE)


def find(script, blob_id):
    """The blob Text of `blob_id` for the part whose script is `script`, or None."""
    owned = script.get(BLOBS_KEY) if script is not None else None
    if owned is not None:
        text = owned.get(blob_id)
        if isinstance(text, bpy.types.Text) and text.get(BLOB_KEY) == blob_id:
            return text
    library = script.library if script is not None else None
    for text in bpy.data.texts:
        if text.get(BLOB_KEY) == blob_id and text.library in (None, library):
            return text
    return None


def store(blob_id, data, name, source=""):
    """The blob Text of `blob_id`, created from base64 `data` unless the file already has it."""
    text = find(None, blob_id)
    if text is not None:
        return text
    text = bpy.data.texts.new(f".{name}.brep")
    text.from_string("\n".join(data[i:i + LINE] for i in range(0, len(data), LINE)) + "\n")
    text.use_fake_user = False  # texts.new() adds one: the part's script is what keeps the blob
    text[BLOB_KEY] = blob_id
    if source:
        text[SOURCE_KEY] = source
    return text


def attach(script, blob_text):
    """Make `script` (a part's Text) own `blob_text`."""
    owned = script.get(BLOBS_KEY)
    if owned is None:
        script[BLOBS_KEY] = {}
        owned = script[BLOBS_KEY]
    owned[blob_text[BLOB_KEY]] = blob_text


def data(text):
    """The base64 text of a blob Text, as the worker reads it."""
    return text.as_string()

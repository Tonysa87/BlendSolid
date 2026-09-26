"""Message framing between Blender and the worker, over a multiprocessing Connection.

A message is one JSON header frame followed by one raw frame per numpy array. No pickle: nothing received
can execute code. Imported as `protocol` inside the worker and as `blendsolid.worker.protocol` in Blender,
so it must not import other project modules.
"""
import json

import numpy as np

ALLOWED_DTYPES = {"float32", "int32"}


class ProtocolError(RuntimeError):
    pass


def send_message(conn, header, arrays=None):
    specs, blobs = [], []
    for name, arr in (arrays or {}).items():
        arr = np.ascontiguousarray(arr)
        if arr.dtype.name not in ALLOWED_DTYPES:
            raise ProtocolError(f"array '{name}' has unsupported dtype {arr.dtype.name}")
        specs.append({"name": name, "dtype": arr.dtype.name, "shape": list(arr.shape)})
        blobs.append(arr.tobytes())
    conn.send_bytes(json.dumps({**header, "buffers": specs}).encode("utf-8"))
    for blob in blobs:
        conn.send_bytes(blob)


def recv_message(conn):
    raw = conn.recv_bytes()
    try:
        header = json.loads(raw)
    except ValueError as e:
        raise ProtocolError(f"malformed header: {e}") from None
    if not isinstance(header, dict) or "type" not in header:
        raise ProtocolError("the header must be a JSON object with a 'type'")
    arrays = {}
    for spec in header.pop("buffers", []):
        if spec.get("dtype") not in ALLOWED_DTYPES:
            raise ProtocolError(f"unsupported dtype {spec.get('dtype')!r}")
        arr = np.frombuffer(conn.recv_bytes(), dtype=spec["dtype"])
        shape = [int(n) for n in spec["shape"]]
        if arr.size != int(np.prod(shape, dtype=np.int64)):
            raise ProtocolError(f"array '{spec['name']}': {arr.size} items, shape {shape}")
        arrays[spec["name"]] = arr.reshape(shape)
    return header, arrays

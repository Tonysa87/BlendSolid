"""Message framing between Blender and the worker, over a multiprocessing Connection.

A message is one JSON header frame followed by one raw frame per numpy array. No pickle: nothing received
can execute code. Imported as `protocol` inside the worker and as `blendsolid.worker.protocol` in Blender,
so it must not import other project modules.

`recv_message` raises `ProtocolError` for any malformed header or buffer spec, but it lets `EOFError` from
`conn.recv_bytes()` propagate unchanged: the worker server and client both catch `EOFError` to mean "the
peer closed the connection".
"""
import json

import numpy as np

ALLOWED_DTYPES = {"float32", "float64", "int32"}  # float64: exact face planes


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


def _validated_shape(spec):
    shape = spec["shape"]
    if not isinstance(shape, list) or not all(isinstance(n, int) and not isinstance(n, bool) and n >= 0
                                                for n in shape):
        raise ProtocolError(f"buffer spec 'shape' must be a list of non-negative integers, got {shape!r}")
    return shape


def recv_message(conn):
    raw = conn.recv_bytes()  # EOFError here means the peer closed; let it propagate.
    try:
        header = json.loads(raw)
    except ValueError as e:
        raise ProtocolError(f"malformed header: {e}") from None
    if not isinstance(header, dict) or "type" not in header:
        raise ProtocolError("the header must be a JSON object with a 'type'")
    buffers = header.pop("buffers", [])
    if not isinstance(buffers, list):
        raise ProtocolError(f"'buffers' must be a list, got {type(buffers).__name__}")
    arrays = {}
    for spec in buffers:
        if not isinstance(spec, dict):
            raise ProtocolError(f"buffer spec must be an object, got {type(spec).__name__}")
        missing = [key for key in ("name", "dtype", "shape") if key not in spec]
        if missing:
            raise ProtocolError(f"buffer spec is missing {missing}")
        if spec["dtype"] not in ALLOWED_DTYPES:
            raise ProtocolError(f"unsupported dtype {spec['dtype']!r}")
        shape = _validated_shape(spec)
        arr = np.frombuffer(conn.recv_bytes(), dtype=spec["dtype"])  # EOFError here also propagates.
        if arr.size != int(np.prod(shape, dtype=np.int64)):
            raise ProtocolError(f"array '{spec['name']}': {arr.size} items, shape {shape}")
        arrays[spec["name"]] = arr.reshape(shape)
    return header, arrays

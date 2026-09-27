import json
from multiprocessing import Pipe

import numpy as np
import pytest

import protocol  # imported as the worker does (blendsolid/worker on sys.path)


def test_roundtrip_header_and_arrays():
    a, b = Pipe()
    verts = np.arange(12, dtype=np.float32).reshape(4, 3)
    tris = np.array([[0, 1, 2], [0, 2, 3]], dtype=np.int32)
    protocol.send_message(a, {"type": "result", "job": 7}, {"verts": verts, "tris": tris})
    header, arrays = protocol.recv_message(b)
    assert header == {"type": "result", "job": 7}
    np.testing.assert_array_equal(arrays["verts"], verts)
    np.testing.assert_array_equal(arrays["tris"], tris)


def test_empty_array_keeps_its_shape():
    a, b = Pipe()
    protocol.send_message(a, {"type": "result"}, {"tris": np.zeros((0, 3), dtype=np.int32)})
    _, arrays = protocol.recv_message(b)
    assert arrays["tris"].shape == (0, 3)


def test_message_without_arrays():
    a, b = Pipe()
    protocol.send_message(a, {"type": "ping"})
    assert protocol.recv_message(b) == ({"type": "ping"}, {})


def test_rejects_unsupported_dtype_on_send():
    a, _ = Pipe()
    with pytest.raises(protocol.ProtocolError):
        protocol.send_message(a, {"type": "x"}, {"v": np.zeros(3, dtype=np.int64)})


def test_rejects_malformed_header():
    a, b = Pipe()
    a.send_bytes(b"not json")
    with pytest.raises(protocol.ProtocolError):
        protocol.recv_message(b)


def test_rejects_header_without_type():
    a, b = Pipe()
    a.send_bytes(json.dumps({"job": 1}).encode())
    with pytest.raises(protocol.ProtocolError):
        protocol.recv_message(b)


def test_rejects_buffer_size_mismatch():
    a, b = Pipe()
    a.send_bytes(json.dumps({"type": "r", "buffers": [{"name": "v", "dtype": "float32", "shape": [4, 3]}]}).encode())
    a.send_bytes(np.zeros(5, dtype=np.float32).tobytes())
    with pytest.raises(protocol.ProtocolError):
        protocol.recv_message(b)


def test_rejects_non_list_buffers():
    a, b = Pipe()
    a.send_bytes(json.dumps({"type": "r", "buffers": "oops"}).encode())
    with pytest.raises(protocol.ProtocolError):
        protocol.recv_message(b)


def test_rejects_buffer_spec_missing_shape():
    a, b = Pipe()
    a.send_bytes(json.dumps({"type": "r", "buffers": [{"name": "v", "dtype": "float32"}]}).encode())
    with pytest.raises(protocol.ProtocolError):
        protocol.recv_message(b)


def test_closed_peer_raises_eof_error():
    a, b = Pipe()
    a.close()
    with pytest.raises(EOFError):
        protocol.recv_message(b)


def test_float64_arrays_round_trip():
    # Exact face planes travel as float64.
    a, b = Pipe()
    planes = np.array([[0.0, 0.0, 1.0, 130.0], [np.nan] * 4], dtype=np.float64)
    protocol.send_message(a, {"type": "r"}, {"planes": planes})
    _, arrays = protocol.recv_message(b)
    np.testing.assert_array_equal(arrays["planes"], planes)

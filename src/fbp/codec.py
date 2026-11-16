"""Blueprint string <-> JSON dict. Format: '0' + base64(zlib(json))."""

from __future__ import annotations

import base64
import json
import zlib


def decode(string: str) -> dict:
    string = string.strip()
    if not string or string[0] != "0":
        raise ValueError("not a blueprint string (must start with version byte '0')")
    try:
        return json.loads(zlib.decompress(base64.b64decode(string[1:])))
    except Exception as exc:  # noqa: BLE001 - any failure means "malformed string"
        raise ValueError(f"malformed blueprint string: {exc}") from exc


def encode(data: dict) -> str:
    raw = json.dumps(data, separators=(",", ":")).encode()
    return "0" + base64.b64encode(zlib.compress(raw, 9)).decode()

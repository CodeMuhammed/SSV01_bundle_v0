"""
Hex and file input helpers (small, focused)

Goals
- Centralize hex parsing and validation with clear error messages.
- Provide a convenient "file or hex" reader for CLI flags.
"""
from __future__ import annotations

import binascii
import re
from typing import Optional


_HEX_RE = re.compile(r"^[0-9a-fA-F]+$")


def is_hex_str(s: str) -> bool:
    return bool(_HEX_RE.fullmatch(s or ""))


def parse_hex(name: str, s: Optional[str], length: Optional[int] = None) -> bytes:
    """Parse a hex string into bytes with optional fixed-length validation.

    Args:
        name: human-readable name for error messages.
        s: hex string (case-insensitive, even length required).
        length: expected length in bytes (optional). If set, enforce exact length.

    Returns:
        Decoded bytes.
    """
    if s is None:
        raise ValueError(f"{name} is required")
    s = s.strip()
    if not is_hex_str(s) or len(s) % 2 != 0:
        raise ValueError(f"Invalid hex for {name}")
    try:
        b = binascii.unhexlify(s)
    except Exception:
        raise ValueError(f"Invalid hex for {name}")
    if length is not None and len(b) != length:
        raise ValueError(f"{name} must be {length} bytes (got {len(b)})")
    return b


def file_or_hex(name: str, hex_value: Optional[str], file_path: Optional[str], *, length: Optional[int] = None) -> bytes:
    """Read bytes from a hex string or a file containing hex.

    Precedence: hex_value if provided; otherwise file_path is used.
    Raises if neither is provided.
    """
    if hex_value:
        return parse_hex(name, hex_value, length)
    if file_path:
        with open(file_path, 'rt') as f:
            return parse_hex(name, f.read().strip(), length)
    raise ValueError(f"{name} required")

from __future__ import annotations

import binascii
from typing import List, Tuple

from .tapscript import tagged_sha256


def parse_control_block_hex(cb_hex: str) -> Tuple[int, bytes, List[bytes]]:
    b = binascii.unhexlify(cb_hex)
    if len(b) < 33:
        raise ValueError('control block too short')
    hdr = b[0]
    leaf_ver = hdr & 0xFE
    xonly = b[1:33]
    nodes = [b[i:i+32] for i in range(33, len(b), 32)]
    return leaf_ver, xonly, nodes


def _merkle_ascend(leaf_hash: bytes, nodes: List[bytes]) -> bytes:
    h = leaf_hash
    for n in nodes:
        a, b = (h, n)
        if a > b:
            a, b = b, a
        h = tagged_sha256('TapBranch', a + b)
    return h


def compute_output_key_xonly(internal_xonly: bytes, leaf_hash: bytes, nodes: List[bytes]) -> bytes:
    """Compute the Taproot output x-only pubkey from internal key and path.

    Returns the 32-byte x-only output key (Q.x).
    """
    try:
        import importlib
        _cc = importlib.import_module('coincurve')
        PublicKey = getattr(_cc, 'PublicKey')
        PrivateKey = getattr(_cc, 'PrivateKey')
    except Exception as e:
        raise ImportError(f'coincurve not available: {e}')

    merkle = _merkle_ascend(leaf_hash, nodes)
    tweak = tagged_sha256('TapTweak', internal_xonly + merkle)
    t_int = int.from_bytes(tweak, 'big')
    try:
        p = PublicKey.from_xonly(internal_xonly)
    except Exception:
        p = PublicKey(b'\x02' + internal_xonly)
    t_pub = PrivateKey.from_int(t_int).public_key
    q = PublicKey.combine_keys([p, t_pub])
    return q.format(compressed=True)[1:33]


def scriptpubkey_from_xonly(xonly_q: bytes) -> bytes:
    return b"\x51\x20" + xonly_q

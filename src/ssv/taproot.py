from __future__ import annotations

import binascii
from dataclasses import dataclass
from typing import Any, List, Tuple, Optional

from .tapscript import tagged_sha256

SECP256K1_ORDER = int(
    "FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141", 16
)


@dataclass(frozen=True)
class ControlBlock:
    """Parsed Taproot control block details.

    Attributes:
        leaf_version: Tapscript leaf version (low bit cleared).
        parity: Parity bit of the Taproot output key (0=even, 1=odd).
        internal_key: 32-byte x-only internal key.
        merkle_nodes: Tuple of 32-byte Merkle proof nodes (may be empty).
    """

    leaf_version: int
    parity: int
    internal_key: bytes
    merkle_nodes: Tuple[bytes, ...]

    def __iter__(self):
        """Allow tuple-unpacking for backward compatibility."""
        yield self.leaf_version
        yield self.internal_key
        yield list(self.merkle_nodes)


def parse_control_block_hex(cb_hex: str) -> ControlBlock:
    """Parse a Taproot control block and surface structure constraints."""

    try:
        b = binascii.unhexlify(cb_hex)
    except (binascii.Error, TypeError) as exc:  # pragma: no cover - defensive
        raise ValueError("control block must be hex") from exc

    if len(b) < 33:
        raise ValueError('control block too short')
    if (len(b) - 33) % 32 != 0:
        raise ValueError('control block length must be 33 + 32*n bytes')

    hdr = b[0]
    parity = hdr & 0x01
    leaf_ver = hdr & 0xFE  # low bit cleared, per BIP-341 control block layout

    internal = b[1:33]
    if len(internal) != 32:
        raise ValueError('internal pubkey in control block must be 32 bytes')

    nodes = [b[i:i + 32] for i in range(33, len(b), 32)]
    for node in nodes:
        if len(node) != 32:
            raise ValueError('merkle node in control block must be 32 bytes')

    return ControlBlock(
        leaf_version=leaf_ver,
        parity=parity,
        internal_key=internal,
        merkle_nodes=tuple(nodes),
    )


def _merkle_ascend(leaf_hash: bytes, nodes: List[bytes]) -> bytes:
    h = leaf_hash
    for n in nodes:
        a, b = (h, n)
        if a > b:
            a, b = b, a
        h = tagged_sha256('TapBranch', a + b)
    return h


def compute_output_key(internal_xonly: bytes, leaf_hash: bytes, nodes: List[bytes]) -> Tuple[bytes, int]:
    """Compute the Taproot output x-only pubkey from internal key and path.

    Returns:
        (x_only, parity) where x_only is the 32-byte Taproot output key and
        parity is the secp256k1 y-parity bit (0=even, 1=odd).
    """
    if len(internal_xonly) != 32:
        raise ValueError('internal key must be 32 bytes')
    if len(leaf_hash) != 32:
        raise ValueError('leaf hash must be 32 bytes')
    for node in nodes:
        if len(node) != 32:
            raise ValueError('each merkle node must be 32 bytes')
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
    if t_int >= SECP256K1_ORDER:
        raise ValueError('tap tweak exceeds curve order')

    base_pk: Optional[Any] = None
    from_xonly = getattr(PublicKey, 'from_xonly', None)
    if callable(from_xonly):
        try:
            base_pk = from_xonly(internal_xonly)
        except Exception:
            base_pk = None
    if base_pk is None:
        try:
            base_pk = PublicKey(b'\x02' + internal_xonly)
        except Exception as exc:
            raise ValueError(f'invalid internal key: {exc}')

    if t_int == 0:
        tweaked = base_pk
    else:
        try:
            tweak_pub = PrivateKey.from_int(t_int).public_key
        except Exception as exc:
            raise ValueError(f'failed to derive tweak public key: {exc}')
        try:
            tweaked = PublicKey.combine_keys([base_pk, tweak_pub])
        except Exception as exc:
            raise ValueError(f'failed to apply tap tweak: {exc}')
        if tweaked is None:
            raise ValueError('failed to compute tweaked output key (infinity)')

    compressed = tweaked.format(compressed=True)
    parity = compressed[0] & 1
    return compressed[1:33], parity


def compute_output_key_xonly(internal_xonly: bytes, leaf_hash: bytes, nodes: List[bytes]) -> bytes:
    """Compat shim that keeps returning just the x-only output key."""
    x_only, _parity = compute_output_key(internal_xonly, leaf_hash, nodes)
    return x_only


def scriptpubkey_from_xonly(xonly_q: bytes) -> bytes:
    if len(xonly_q) != 32:
        raise ValueError('x-only pubkey must be 32 bytes')
    return b"\x51\x20" + xonly_q

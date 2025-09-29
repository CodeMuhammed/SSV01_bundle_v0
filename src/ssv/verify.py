"""
Taproot path verification utilities.

Given a tapscript hex and a control block, recompute the expected Taproot
output scriptPubKey and compare with an actual witness_utxo spk.
"""
from __future__ import annotations

import binascii
from typing import Tuple, List, Optional, TypedDict

from .tapscript import tapleaf_hash_tagged
from .taproot import parse_control_block_hex, compute_output_key_xonly, scriptpubkey_from_xonly


def _parse_control_block(cb_hex: str) -> Tuple[int, bytes, List[bytes]]:
    return parse_control_block_hex(cb_hex)


class VerifyResult(TypedDict):
    ok: Optional[bool]
    expected_spk: Optional[str]
    actual_spk: str
    reason: Optional[str]


def verify_taproot_path(tapscript_hex: str, control_block_hex: str, witness_spk_hex: str) -> VerifyResult:
    script = binascii.unhexlify(tapscript_hex)
    leaf_ver, xonly, nodes = _parse_control_block(control_block_hex)
    leaf = tapleaf_hash_tagged(script, leaf_ver)
    try:
        qx = compute_output_key_xonly(xonly, leaf, nodes)
        expected_spk = scriptpubkey_from_xonly(qx).hex()
    except Exception as e:
        return {
            'ok': None,
            'expected_spk': None,
            'actual_spk': witness_spk_hex.lower(),
            'reason': str(e),
        }
    actual_spk = witness_spk_hex.lower()
    ok = (expected_spk == actual_spk)
    return {
        'ok': ok,
        'expected_spk': expected_spk,
        'actual_spk': actual_spk,
        'reason': None if ok else 'scriptPubKey mismatch',
    }

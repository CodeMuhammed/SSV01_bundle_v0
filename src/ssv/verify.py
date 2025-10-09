"""
Taproot path verification utilities.

Given a tapscript hex and a control block, recompute the expected Taproot
output scriptPubKey and compare with an actual witness_utxo spk.
"""
from __future__ import annotations

import binascii
from typing import Optional, TypedDict

from .tapscript import tapleaf_hash_tagged
from .taproot import (
    ControlBlock,
    compute_output_key,
    parse_control_block_hex,
    scriptpubkey_from_xonly,
)


class VerifyResult(TypedDict):
    ok: Optional[bool]
    expected_spk: Optional[str]
    actual_spk: str
    reason: Optional[str]


def verify_taproot_path(tapscript_hex: str, control_block_hex: str, witness_spk_hex: str) -> VerifyResult:
    script = binascii.unhexlify(tapscript_hex)
    cb: ControlBlock = parse_control_block_hex(control_block_hex)
    leaf = tapleaf_hash_tagged(script, cb.leaf_version)
    try:
        qx, parity = compute_output_key(cb.internal_key, leaf, cb.merkle_nodes)
        expected_spk = scriptpubkey_from_xonly(qx).hex()
    except Exception as e:
        return {
            'ok': None,
            'expected_spk': None,
            'actual_spk': witness_spk_hex.lower(),
            'reason': str(e),
        }

    if parity != cb.parity:
        return {
            'ok': False,
            'expected_spk': expected_spk,
            'actual_spk': witness_spk_hex.lower(),
            'reason': 'control block parity mismatch',
        }

    actual_spk = witness_spk_hex.lower()
    ok = (expected_spk == actual_spk)
    return {
        'ok': ok,
        'expected_spk': expected_spk,
        'actual_spk': actual_spk,
        'reason': None if ok else 'scriptPubKey mismatch',
    }

import os

import pytest

from ssv.tapscript import build_tapscript, tapleaf_hash_tagged
from ssv.taproot import scriptpubkey_from_xonly, compute_output_key_xonly
from ssv.verify import verify_taproot_path


@pytest.mark.skipif('coincurve' not in {m.__name__ for m in list(__import__('sys').modules.values()) if m}, reason='coincurve import may not be available')
def test_verify_path_with_synthetic_control_block():
    try:
        import coincurve  # noqa: F401
    except Exception:
        pytest.skip('coincurve not installed')

    # Build a tapscript from deterministic params
    h = '00' * 32
    pb = '11' * 32
    pp = '22' * 32
    csv = 10
    script = build_tapscript(h, pb, csv, pp)
    leaf_ver = 0xC0
    leaf = tapleaf_hash_tagged(script, leaf_ver)

    # Synthetic internal x-only key (32 bytes of 0x33)
    internal = bytes.fromhex('33' * 32)

    # Control block: [leaf_ver | parity=0] + internal + no nodes
    ctrl = bytes([leaf_ver]) + internal
    ctrl_hex = ctrl.hex()

    # Compute expected output SPK from taproot helper
    qx = compute_output_key_xonly(internal, leaf, [])
    spk_hex = scriptpubkey_from_xonly(qx).hex()

    # Verify
    res = verify_taproot_path(script.hex(), ctrl_hex, spk_hex)
    assert res['ok'] is True
    assert res['expected_spk'] == spk_hex
    assert res['actual_spk'] == spk_hex


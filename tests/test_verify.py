import pytest

from ssv.tapscript import build_tapscript, tapleaf_hash_tagged
from ssv.taproot import compute_output_key, scriptpubkey_from_xonly
from ssv.verify import verify_taproot_path


def test_verify_path_with_synthetic_control_block():
    pytest.importorskip('coincurve', reason='coincurve not installed')

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

    # Compute expected output SPK from taproot helper (parity included)
    qx, parity = compute_output_key(internal, leaf, [])
    spk_hex = scriptpubkey_from_xonly(qx).hex()

    # Control block: [leaf_ver | parity] + internal + no nodes
    ctrl = bytes([(leaf_ver & 0xFE) | parity]) + internal
    ctrl_hex = ctrl.hex()

    # Verify
    res = verify_taproot_path(script.hex(), ctrl_hex, spk_hex)
    assert res['ok'] is True
    assert res['expected_spk'] == spk_hex
    assert res['actual_spk'] == spk_hex


def test_verify_path_rejects_parity_mismatch():
    pytest.importorskip('coincurve', reason='coincurve not installed')

    h = '00' * 32
    pb = '11' * 32
    pp = '22' * 32
    csv = 10
    script = build_tapscript(h, pb, csv, pp)
    leaf_ver = 0xC0
    leaf = tapleaf_hash_tagged(script, leaf_ver)
    internal = bytes.fromhex('33' * 32)
    qx, parity = compute_output_key(internal, leaf, [])
    spk_hex = scriptpubkey_from_xonly(qx).hex()

    wrong_parity = parity ^ 0x01
    ctrl = bytes([(leaf_ver & 0xFE) | wrong_parity]) + internal

    res = verify_taproot_path(script.hex(), ctrl.hex(), spk_hex)
    assert res['ok'] is False
    assert res['reason'] == 'control block parity mismatch'

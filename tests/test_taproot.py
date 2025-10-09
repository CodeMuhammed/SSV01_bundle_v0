import pytest

from ssv.taproot import (
    ControlBlock,
    compute_output_key,
    compute_output_key_xonly,
    parse_control_block_hex,
)


def test_parse_control_block_hex_valid_minimal():
    cb = parse_control_block_hex('c0' + '33' * 32)
    assert isinstance(cb, ControlBlock)
    assert cb.leaf_version == 0xC0
    assert cb.parity == 0
    assert cb.internal_key == bytes.fromhex('33' * 32)
    assert cb.merkle_nodes == ()
    # Backwards compatible tuple unpacking
    leaf_ver, internal, nodes = cb
    assert leaf_ver == 0xC0
    assert internal == bytes.fromhex('33' * 32)
    assert nodes == []


def test_parse_control_block_hex_rejects_short_or_misaligned():
    # Too short (<33 bytes total)
    with pytest.raises(ValueError, match='control block too short'):
        parse_control_block_hex('c0' + '33' * 31)

    # Length not equal to 33 + 32*n
    with pytest.raises(ValueError, match='33 \\+ 32\\*n'):
        parse_control_block_hex('c0' + '33' * 32 + '44' * 16)


def test_compute_output_key_returns_parity():
    pytest.importorskip('coincurve', reason='coincurve not installed')
    xonly = bytes.fromhex('33' * 32)
    leaf = bytes.fromhex('22' * 32)
    # No merkle nodes is fine; parity should be 0 or 1
    qx, parity = compute_output_key(xonly, leaf, [])
    assert qx == compute_output_key_xonly(xonly, leaf, [])
    assert parity in (0, 1)


def test_compute_output_key_xonly_rejects_invalid_lengths():
    pytest.importorskip('coincurve', reason='coincurve not installed')
    from ssv.taproot import compute_output_key_xonly

    with pytest.raises(ValueError, match='internal key'):
        compute_output_key_xonly(b'\x00' * 31, b'\x11' * 32, [])
    with pytest.raises(ValueError, match='leaf hash'):
        compute_output_key_xonly(b'\x00' * 32, b'\x11' * 31, [])
    with pytest.raises(ValueError, match='merkle node'):
        compute_output_key_xonly(b'\x00' * 32, b'\x11' * 32, [b'\x22'])

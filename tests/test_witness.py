import pytest

from ssv.witness import Branch, build_witness, IF_SELECTOR, ELSE_SELECTOR


def test_build_witness_close_and_liquidate():
    sig = bytes.fromhex('aa'*64)
    s = bytes.fromhex('bb'*32)
    taps = bytes.fromhex('51')  # OP_TRUE dummy
    ctrl = bytes.fromhex('c0' + '33'*32)  # leafver + xonly

    w_close = build_witness(Branch.CLOSE, sig, taps, ctrl, preimage=s)
    assert w_close[0] == sig
    assert w_close[1] == s
    assert w_close[2] == IF_SELECTOR
    assert w_close[3] == taps and w_close[4] == ctrl

    w_liq = build_witness(Branch.LIQUIDATE, sig, taps, ctrl)
    assert w_liq[0] == sig
    assert w_liq[1] == ELSE_SELECTOR
    assert w_liq[2] == taps and w_liq[3] == ctrl


def test_build_witness_close_requires_preimage():
    with pytest.raises(ValueError):
        build_witness(Branch.CLOSE, b'\x00'*64, b'\x51', b'\xc0' + b'\x33'*32)


def test_build_witness_rejects_invalid_signature_length():
    taps = bytes.fromhex('51')
    ctrl = bytes.fromhex('c0' + '33'*32)
    with pytest.raises(ValueError, match='signature'):
        build_witness(Branch.CLOSE, b'\xaa' * 63, taps, ctrl, preimage=bytes.fromhex('bb'*32))


def test_build_witness_rejects_empty_tapscript():
    ctrl = bytes.fromhex('c0' + '33'*32)
    with pytest.raises(ValueError, match='tapscript'):
        build_witness(Branch.CLOSE, bytes.fromhex('aa'*64), b'', ctrl, preimage=bytes.fromhex('bb'*32))


def test_build_witness_rejects_bad_control_block_length():
    taps = bytes.fromhex('51')
    bad_control = bytes.fromhex('c0' + '33'*31)  # 1 + 31 bytes (invalid)
    with pytest.raises(ValueError, match='control'):
        build_witness(Branch.CLOSE, bytes.fromhex('aa'*64), taps, bad_control, preimage=bytes.fromhex('bb'*32))


def test_build_witness_rejects_non_32_byte_preimage():
    taps = bytes.fromhex('51')
    ctrl = bytes.fromhex('c0' + '33'*32)
    with pytest.raises(ValueError, match='preimage'):
        build_witness(Branch.CLOSE, bytes.fromhex('aa'*64), taps, ctrl, preimage=b'\x01'*31)

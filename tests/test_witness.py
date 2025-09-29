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


import pytest

from ssv.cli import verify_anchor_output, verify_opret_output
from ssv.tapscript import pushdata


class _DummyScript:
    def __init__(self, hex_str: str) -> None:
        self._hex = hex_str.lower()

    def hex(self) -> str:
        return self._hex


class _DummyOutput:
    def __init__(self, script_hex: str, value: int) -> None:
        self.scriptPubKey = _DummyScript(script_hex)
        self.nValue = value


class _DummyTx:
    def __init__(self, outputs):
        self.vout = outputs


class _DummyPsbt:
    def __init__(self, script_hex: str, value: int):
        self.tx = _DummyTx([_DummyOutput(script_hex, value)])


def _opret_script_hex(data_hex: str) -> str:
    data = bytes.fromhex(data_hex)
    return (b"\x6a" + pushdata(data)).hex()


def test_verify_anchor_output_stub_success():
    script = '5120' + '11' * 32
    psbt = _DummyPsbt(script, 1234)
    res = verify_anchor_output(psbt, 0, script.upper(), 1234)
    assert res.ok is True
    assert res.reason is None
    assert res.expected_spk == script
    assert res.actual_spk == script
    assert res.expected_value == 1234
    assert res.actual_value == 1234


def test_verify_anchor_output_rejects_bad_inputs():
    script = '5120' + '11' * 32
    psbt = _DummyPsbt(script, 1)
    with pytest.raises(ValueError, match='hex'):
        verify_anchor_output(psbt, 0, 'zz', 1)
    with pytest.raises(ValueError, match='non-negative'):
        verify_anchor_output(psbt, 0, script, -5)


def test_verify_opret_output_stub_success():
    data_hex = 'deadbeef'
    script = _opret_script_hex(data_hex)
    psbt = _DummyPsbt(script, 0)
    res = verify_opret_output(psbt, 0, data_hex.upper(), 0)
    assert res.ok is True
    assert res.expected_spk == script
    assert res.actual_spk == script
    assert res.expected_value == 0
    assert res.actual_value == 0


def test_verify_opret_output_validation_errors():
    script = _opret_script_hex('aa')
    psbt = _DummyPsbt(script, 1)
    with pytest.raises(ValueError, match='hex'):
        verify_opret_output(psbt, 0, 'zz', None)
    with pytest.raises(ValueError, match='non-negative'):
        verify_opret_output(psbt, 0, 'aa', -1)


def test_verify_opret_output_reports_mismatch():
    # Actual script pushes empty data, expectation pushes 0xaa
    psbt = _DummyPsbt('6a00', 0)
    res = verify_opret_output(psbt, 0, 'aa', None)
    assert res.ok is False
    assert res.reason == 'spk mismatch'

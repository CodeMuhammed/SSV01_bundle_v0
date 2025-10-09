import os
import tempfile
import importlib
import pytest

from typing import Sequence
from ssv.cli import main as ssv_main


def _psbt_available() -> bool:
    try:
        m = importlib.import_module('bitcointx.core.psbt')
        return any(hasattr(m, attr) for attr in ('PSBT', 'PartiallySignedTransaction'))
    except Exception:
        return False


def run_cli(argv: Sequence[str]) -> str:
    import sys
    old = sys.argv[:]
    try:
        sys.argv = ['ssv'] + list(argv)
        from io import StringIO
        import contextlib
        buf = StringIO()
        with contextlib.redirect_stdout(buf):
            ssv_main()
        return buf.getvalue()
    finally:
        sys.argv = old


@pytest.mark.skipif(not _psbt_available(), reason='python-bitcointx PSBT API not available')
def test_finalize_anchor_guard_mismatch_raises_early():
    # Build a PSBT with a tx that has a single output that doesn't match the guard
    psbt_mod = importlib.import_module('bitcointx.core.psbt')
    PSBT = getattr(psbt_mod, 'PSBT', getattr(psbt_mod, 'PartiallySignedTransaction'))
    core = importlib.import_module('bitcointx.core')
    CTransaction = core.CTransaction
    CTxIn = core.CTxIn
    CTxOut = core.CTxOut
    COutPoint = core.COutPoint
    CScript = core.script.CScript
    lx = core.lx
    # Put some P2TR-like spk
    xonly = bytes.fromhex('11'*32)
    spk = bytes.fromhex('5120') + xonly
    tx = CTransaction([CTxIn(COutPoint(lx('00'*32), 0))], [CTxOut(5000, CScript(spk))], 2)
    try:
        psbt = PSBT(unsigned_tx=tx)
    except Exception:
        pytest.skip('PSBT implementation rejected minimal unsigned tx')
    with tempfile.TemporaryDirectory() as td:
        p = os.path.join(td, 't.psbt')
        with open(p, 'wt') as f:
            f.write(psbt.to_base64())
        with pytest.raises(ValueError, match='Anchor guard failed'):
            run_cli([
                'finalize', '--mode', 'borrower', '--psbt-in', p, '--psbt-out', os.path.join(td, 'out.psbt'),
                '--sig', '00'*64, '--preimage', '00'*32, '--control', 'c0' + '33'*32,
                '--hash-h', '00'*32, '--borrower-pk', '11'*32, '--csv-blocks', '5', '--provider-pk', '22'*32,
                '--require-anchor-index', '0', '--require-anchor-spk', ('5120' + '00'*32), '--require-anchor-value', '9999'
            ])


@pytest.mark.skipif(not _psbt_available(), reason='python-bitcointx PSBT API not available')
def test_finalize_opret_guard_mismatch_raises_early():
    psbt_mod = importlib.import_module('bitcointx.core.psbt')
    PSBT = getattr(psbt_mod, 'PSBT', getattr(psbt_mod, 'PartiallySignedTransaction'))
    core = importlib.import_module('bitcointx.core')
    CTransaction = core.CTransaction
    CTxIn = core.CTxIn
    CTxOut = core.CTxOut
    COutPoint = core.COutPoint
    CScript = core.script.CScript
    lx = core.lx
    # Create an OP_RETURN with one data
    data = bytes.fromhex('aabbcc')
    def _pushdata(b: bytes) -> bytes:
        n = len(b)
        if n < 0x4c:
            return bytes([n]) + b
        elif n <= 0xff:
            return b"\x4c" + bytes([n]) + b
        elif n <= 0xffff:
            return b"\x4d" + n.to_bytes(2, 'little') + b
        else:
            return b"\x4e" + n.to_bytes(4, 'little') + b
    opret_spk = b"\x6a" + _pushdata(data)
    tx = CTransaction([CTxIn(COutPoint(lx('00'*32), 0))], [CTxOut(0, CScript(opret_spk))], 2)
    try:
        psbt = PSBT(unsigned_tx=tx)
    except Exception:
        pytest.skip('PSBT implementation rejected minimal unsigned tx')
    with tempfile.TemporaryDirectory() as td:
        p = os.path.join(td, 't.psbt')
        with open(p, 'wt') as f:
            f.write(psbt.to_base64())
        with pytest.raises(ValueError, match='OP_RETURN guard failed'):
            run_cli([
                'finalize', '--mode', 'borrower', '--psbt-in', p, '--psbt-out', os.path.join(td, 'out.psbt'),
                '--sig', '00'*64, '--preimage', '00'*32, '--control', 'c0' + '33'*32,
                '--hash-h', '00'*32, '--borrower-pk', '11'*32, '--csv-blocks', '5', '--provider-pk', '22'*32,
                '--require-opret-index', '0', '--require-opret-data', 'deadbeef'
            ])

import os
import tempfile
import importlib

import pytest

from typing import Sequence
from ssv.cli import main as ssv_main


def _psbt_available() -> bool:
    try:
        m = importlib.import_module('bitcointx.core.psbt')
        return hasattr(m, 'PSBT')
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
def test_anchor_verify_positive():
    PSBT = importlib.import_module('bitcointx.core.psbt').PSBT
    core = importlib.import_module('bitcointx.core')
    CTransaction = core.CTransaction
    CTxIn = core.CTxIn
    CTxOut = core.CTxOut
    COutPoint = core.COutPoint
    CScript = core.script.CScript
    lx = core.lx

    # Build a minimal unsigned tx with 1 input and 1 output (taproot-like SPK)
    xonly = bytes.fromhex('11' * 32)
    spk = bytes.fromhex('5120') + xonly
    txin = CTxIn(COutPoint(lx('00' * 32), 0))
    txout = CTxOut(12345, CScript(spk))
    tx = CTransaction([txin], [txout], 2)

    psbt = PSBT()
    # attach the unsigned transaction
    if hasattr(psbt, 'tx'):
        psbt.tx = tx
    elif hasattr(psbt, 'unsigned_tx'):
        psbt.unsigned_tx = tx
    else:
        pytest.skip('PSBT object has no tx/unsigned_tx attribute')

    with tempfile.TemporaryDirectory() as td:
        p = os.path.join(td, 't.psbt')
        # write base64 via PSBT API
        with open(p, 'wt') as f:
            f.write(psbt.to_base64())
        out = run_cli(['anchor-verify', '--psbt-in', p, '--index', '0', '--spk', (b'5120' + xonly).hex(), '--value', '12345', '--json'])
        import json
        data = json.loads(out)
        assert data['ok'] is True
        assert data['index'] == 0
        assert data['expected_spk'] == (b'5120' + xonly).hex()
        assert data['actual_spk'] == (b'5120' + xonly).hex()
        assert data['expected_value'] == 12345
        assert data['actual_value'] == 12345


@pytest.mark.skipif(not _psbt_available(), reason='python-bitcointx PSBT API not available')
def test_anchor_verify_mismatch():
    PSBT = importlib.import_module('bitcointx.core.psbt').PSBT
    core = importlib.import_module('bitcointx.core')
    CTransaction = core.CTransaction
    CTxIn = core.CTxIn
    CTxOut = core.CTxOut
    COutPoint = core.COutPoint
    CScript = core.script.CScript
    lx = core.lx

    xonly = bytes.fromhex('22' * 32)
    good_spk = bytes.fromhex('5120') + xonly
    bad_spk = bytes.fromhex('5120' + '00' * 32)
    tx = CTransaction([CTxIn(COutPoint(lx('00' * 32), 0))], [CTxOut(9999, CScript(good_spk))], 2)

    psbt = PSBT()
    if hasattr(psbt, 'tx'):
        psbt.tx = tx
    elif hasattr(psbt, 'unsigned_tx'):
        psbt.unsigned_tx = tx
    else:
        pytest.skip('PSBT object has no tx/unsigned_tx attribute')

    import json
    with tempfile.TemporaryDirectory() as td:
        p = os.path.join(td, 't.psbt')
        with open(p, 'wt') as f:
            f.write(psbt.to_base64())
        out = run_cli(['anchor-verify', '--psbt-in', p, '--index', '0', '--spk', bad_spk.hex(), '--value', '9999', '--json'])
        data = json.loads(out)
        assert data['ok'] is False
        assert data['reason'] == 'spk mismatch'


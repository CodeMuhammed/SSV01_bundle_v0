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


@pytest.mark.skipif(not _psbt_available(), reason='python-bitcointx PSBT API not available')
def test_opret_verify_positive_and_mismatch():
    psbt_mod = importlib.import_module('bitcointx.core.psbt')
    PSBT = getattr(psbt_mod, 'PSBT', getattr(psbt_mod, 'PartiallySignedTransaction'))
    core = importlib.import_module('bitcointx.core')
    CTransaction = core.CTransaction
    CTxIn = core.CTxIn
    CTxOut = core.CTxOut
    COutPoint = core.COutPoint
    CScript = core.script.CScript
    lx = core.lx

    data = bytes.fromhex('aabbcc')
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
        # Positive
        out = run_cli(['opret-verify', '--psbt-in', p, '--index', '0', '--data', data.hex(), '--json'])
        import json
        j = json.loads(out)
        assert j['ok'] is True
        # Mismatch
        out2 = run_cli(['opret-verify', '--psbt-in', p, '--index', '0', '--data', 'deadbeef', '--json'])
        j2 = json.loads(out2)
        assert j2['ok'] is False and j2['reason'] == 'spk mismatch'

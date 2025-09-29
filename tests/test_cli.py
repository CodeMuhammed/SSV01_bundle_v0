import json
import sys

import pytest

from typing import Sequence
from ssv.cli import main as ssv_main


def run_cli(argv: Sequence[str]) -> str:
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


def test_cli_build_json_output():
    h = 'aa'*32
    xb = 'bb'*32
    xp = 'cc'*32
    out = run_cli(['build-tapscript', '--hash-h', h, '--borrower-pk', xb, '--csv-blocks', '5', '--provider-pk', xp, '--json'])
    data = json.loads(out)
    assert 'tapscript_hex' in data and 'tapleaf_hash_simple' in data and 'tapleaf_hash_tagged' in data


def test_cli_verify_json_success():
    pytest.importorskip('coincurve', reason='coincurve not installed')
    h = '00' * 32
    pb = '11' * 32
    pp = '22' * 32
    csv = '10'
    # Build tapscript using CLI
    bout = run_cli(['build-tapscript', '--hash-h', h, '--borrower-pk', pb, '--csv-blocks', csv, '--provider-pk', pp, '--json'])
    bdata = json.loads(bout)
    taps_hex = bdata['tapscript_hex']
    # Create a control block & expected SPK using taproot helpers
    from ssv.tapscript import tapleaf_hash_tagged
    from ssv.taproot import scriptpubkey_from_xonly, compute_output_key_xonly
    leaf_ver = 0xC0
    internal = bytes.fromhex('33'*32)
    ctrl_hex = (bytes([leaf_ver]) + internal).hex()
    leaf = tapleaf_hash_tagged(bytes.fromhex(taps_hex), leaf_ver)
    qx = compute_output_key_xonly(internal, leaf, [])
    spk_hex = scriptpubkey_from_xonly(qx).hex()
    vout = run_cli(['verify-path', '--tapscript', taps_hex, '--control', ctrl_hex, '--witness-spk', spk_hex, '--json'])
    vdata = json.loads(vout)
    assert vdata['ok'] is True and vdata['expected_spk'] == spk_hex and vdata['actual_spk'] == spk_hex

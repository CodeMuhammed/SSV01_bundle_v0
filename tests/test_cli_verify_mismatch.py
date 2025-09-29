import json
import pytest

from typing import Sequence
from ssv.cli import main as ssv_main


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


def test_cli_verify_json_mismatch():
    pytest.importorskip('coincurve', reason='coincurve not installed')

    # Build tapscript JSON
    h = '00' * 32
    pb = '11' * 32
    pp = '22' * 32
    csv = '10'
    bout = run_cli(['build-tapscript', '--hash-h', h, '--borrower-pk', pb, '--csv-blocks', csv, '--provider-pk', pp, '--json'])
    taps_hex = json.loads(bout)['tapscript_hex']

    # Construct control block for the path
    from ssv.tapscript import tapleaf_hash_tagged
    from ssv.taproot import compute_output_key_xonly
    leaf_ver = 0xC0
    internal = bytes.fromhex('33'*32)
    ctrl_hex = (bytes([leaf_ver]) + internal).hex()
    leaf = tapleaf_hash_tagged(bytes.fromhex(taps_hex), leaf_ver)
    _ = compute_output_key_xonly(internal, leaf, [])  # ensure coincurve path operational

    # Provide a wrong spk (flip one nibble)
    wrong_spk = '5120' + ('00'*31)  # invalid but structurally correct length

    vout = run_cli(['verify-path', '--tapscript', taps_hex, '--control', ctrl_hex, '--witness-spk', wrong_spk, '--json'])
    vdata = json.loads(vout)
    assert vdata['ok'] is False
    assert vdata['reason'] == 'scriptPubKey mismatch'

import importlib
import os
import tempfile

import pytest

from ssv.psbtio import load_psbt_from_file, write_psbt, to_raw_tx_hex, get_input_witness_spk_hex


def _psbt_available() -> bool:
    try:
        m = importlib.import_module('bitcointx.core.psbt')
        return hasattr(m, 'PSBT')
    except Exception:
        return False


@pytest.mark.skipif(not _psbt_available(), reason='python-bitcointx PSBT API not available')
def test_psbt_load_and_write_roundtrip():
    from bitcointx.core.psbt import PSBT
    psbt = PSBT()
    with tempfile.TemporaryDirectory() as td:
        p = os.path.join(td, 'a.psbt')
        write_psbt(psbt, p)
        psbt2 = load_psbt_from_file(p)
        assert isinstance(psbt2, PSBT)


@pytest.mark.skipif(not _psbt_available(), reason='python-bitcointx PSBT API not available')
def test_psbt_to_raw_and_witness_errors():
    from bitcointx.core.psbt import PSBT
    psbt = PSBT()
    with pytest.raises(Exception):
        _ = to_raw_tx_hex(psbt)
    with pytest.raises(Exception):
        _ = get_input_witness_spk_hex(psbt, 0)


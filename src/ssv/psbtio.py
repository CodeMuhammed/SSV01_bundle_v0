"""
PSBT IO helpers (thin wrappers around python-bitcointx via dynamic import).

Provides functions to load PSBTs from files (auto-detect hex vs base64),
write PSBTs back to files, extract witness_utxo scriptPubKey, and convert
to raw transaction hex.
"""
from __future__ import annotations

import base64
import binascii
from typing import Any

from .hexutil import is_hex_str


def _imp_psbt():
    import importlib
    return importlib.import_module('bitcointx.core.psbt').PSBT


def _imp_core_script_witness():
    import importlib
    return importlib.import_module('bitcointx.core.script').CScriptWitness


def _imp_b2x():
    import importlib
    return importlib.import_module('bitcointx.core').b2x


def load_psbt_from_file(path: str) -> Any:
    """Load a PSBT from file contents which may be hex or base64.

    Returns:
        A bitcointx.core.psbt.PSBT object.
    Raises:
        ImportError if python-bitcointx is not installed.
    """
    PSBT = _imp_psbt()
    with open(path, 'rt') as f:
        s = f.read().strip()
    if is_hex_str(s):
        raw = binascii.unhexlify(s)
        s = base64.b64encode(raw).decode()
    return PSBT.from_base64(s)


def write_psbt(psbt: Any, path: str) -> None:
    """Write PSBT to file as base64."""
    with open(path, 'wt') as f:
        f.write(psbt.to_base64())


def to_raw_tx_hex(psbt: Any) -> str:
    """Convert PSBT to raw transaction hex (or raise on failure)."""
    b2x = _imp_b2x()
    tx = psbt.to_tx()
    return b2x(tx.serialize())


def get_input_witness_spk_hex(psbt: Any, index: int = 0) -> str:
    """Return the witness_utxo scriptPubKey hex for the given input index."""
    iu = psbt.inputs[index].witness_utxo
    if not iu:
        raise ValueError(f'PSBT input {index} missing witness_utxo')
    return iu.scriptPubKey.hex()


def cscript_witness():
    """Accessor for CScriptWitness class to avoid importing in callers."""
    return _imp_core_script_witness()


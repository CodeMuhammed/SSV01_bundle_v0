"""
Policy model for the SSV tapscript.

Provides a lightweight, explicit container for parameters that define the
two-branch Taproot policy used by this toolkit.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

MAX_CSV_BLOCKS = 0xFFFF  # BIP-68 block-based CSV uses low 16 bits only


def normalize_csv_blocks(value: Any) -> int:
    """Coerce CSV blocks to int and enforce the BIP-68 constraints."""
    try:
        n = int(value)
    except Exception as exc:  # pragma: no cover - defensive, rethrown below
        raise ValueError("csv_blocks must be an integer") from exc
    if n <= 0:
        raise ValueError("csv_blocks must be a positive integer")
    if n > MAX_CSV_BLOCKS:
        raise ValueError(f"csv_blocks must be <= {MAX_CSV_BLOCKS} (BIP-68 block-based CSV limit)")
    return n


@dataclass
class PolicyParams:
    """Parameters defining the tapscript policy.

    Attributes:
        hash_h: 32-byte hex string of sha256(s) preimage commitment.
        borrower_xonly: 32-byte hex x-only pubkey for CLOSE path.
        provider_xonly: 32-byte hex x-only pubkey for LIQUIDATE path.
        csv_blocks: positive integer (1-65535) for CSV timelock (blocks).
    """
    hash_h: str
    borrower_xonly: str
    provider_xonly: str
    csv_blocks: int

    def validate(self) -> None:
        from .hexutil import is_hex_str
        if not is_hex_str(self.hash_h) or len(self.hash_h) != 64:
            raise ValueError("hash_h must be 32-byte hex (64 chars)")
        if not is_hex_str(self.borrower_xonly) or len(self.borrower_xonly) != 64:
            raise ValueError("borrower_xonly must be 32-byte hex (x-only)")
        if not is_hex_str(self.provider_xonly) or len(self.provider_xonly) != 64:
            raise ValueError("provider_xonly must be 32-byte hex (x-only)")
        self.csv_blocks = normalize_csv_blocks(self.csv_blocks)

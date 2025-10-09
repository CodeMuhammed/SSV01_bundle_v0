from __future__ import annotations

from enum import Enum
from typing import List, Optional


IF_SELECTOR = b"\x01"     # selects the IF branch (CLOSE)
ELSE_SELECTOR = b"\x00"   # selects the ELSE branch (LIQUIDATE)


class Branch(Enum):
    CLOSE = "close"         # borrower path (reveals preimage s)
    LIQUIDATE = "liquidate" # provider path (after CSV)


def _validate_signature(sig: bytes) -> None:
    if len(sig) not in (64, 65):
        raise ValueError("signature must be 64 bytes (or 65 bytes including sighash byte)")


def _validate_control(control: bytes) -> None:
    if len(control) < 33 or (len(control) - 33) % 32 != 0:
        raise ValueError("control block must be 33 + 32*n bytes (Taproot BIP-341 structure)")


def _validate_tapscript(tapscript: bytes) -> None:
    if not tapscript:
        raise ValueError("tapscript must not be empty")
    if len(tapscript) > 10_000:
        raise ValueError("tapscript exceeds 10k byte BIP-342 limit")


def build_witness(branch: Branch, sig: bytes, tapscript: bytes, control: bytes, *, preimage: Optional[bytes] = None) -> List[bytes]:
    """Build Taproot script-path witness stack for the given branch.

    CLOSE (borrower):   [sig_b, s, 0x01, tapscript, control]
    LIQUIDATE (provider): [sig_p, 0x00, tapscript, control]
    """
    _validate_signature(sig)
    _validate_tapscript(tapscript)
    _validate_control(control)

    if branch is Branch.CLOSE:
        if preimage is None:
            raise ValueError("preimage is required for CLOSE branch")
        if len(preimage) != 32:
            raise ValueError("preimage must be 32 bytes")
        return [sig, preimage, IF_SELECTOR, tapscript, control]
    elif branch is Branch.LIQUIDATE:
        return [sig, ELSE_SELECTOR, tapscript, control]
    else:
        raise ValueError("unknown branch")

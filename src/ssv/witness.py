from __future__ import annotations

from enum import Enum
from typing import List, Optional


IF_SELECTOR = b"\x01"     # selects the IF branch (CLOSE)
ELSE_SELECTOR = b"\x00"   # selects the ELSE branch (LIQUIDATE)


class Branch(Enum):
    CLOSE = "close"         # borrower path (reveals preimage s)
    LIQUIDATE = "liquidate" # provider path (after CSV)


def build_witness(branch: Branch, sig: bytes, tapscript: bytes, control: bytes, *, preimage: Optional[bytes] = None) -> List[bytes]:
    """Build Taproot script-path witness stack for the given branch.

    CLOSE (borrower):   [sig_b, s, 0x01, tapscript, control]
    LIQUIDATE (provider): [sig_p, 0x00, tapscript, control]
    """
    if branch is Branch.CLOSE:
        if preimage is None:
            raise ValueError("preimage is required for CLOSE branch")
        return [sig, preimage, IF_SELECTOR, tapscript, control]
    elif branch is Branch.LIQUIDATE:
        return [sig, ELSE_SELECTOR, tapscript, control]
    else:
        raise ValueError("unknown branch")


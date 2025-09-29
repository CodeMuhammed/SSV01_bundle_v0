import binascii
from typing import Tuple, List

from .tapscript import tapleaf_hash_tagged, tagged_sha256


def _parse_control_block(cb_hex: str) -> Tuple[int, bytes, List[bytes]]:
    b = binascii.unhexlify(cb_hex)
    if len(b) < 33:
        raise ValueError('control block too short')
    hdr = b[0]
    leaf_ver = hdr & 0xFE
    xonly = b[1:33]
    nodes = [b[i:i+32] for i in range(33, len(b), 32)]
    return leaf_ver, xonly, nodes


def verify_taproot_path(tapscript_hex: str, control_block_hex: str, witness_spk_hex: str) -> dict:
    try:
        from coincurve import PublicKey, PrivateKey
    except Exception as e:
        return {
            'ok': None,
            'expected_spk': None,
            'actual_spk': witness_spk_hex.lower(),
            'reason': f'coincurve not available: {e}',
        }

    script = binascii.unhexlify(tapscript_hex)
    leaf_ver, xonly, nodes = _parse_control_block(control_block_hex)
    leaf = tapleaf_hash_tagged(script, leaf_ver)
    # hash up path (lexicographic each step)
    for n in nodes:
        a, b = (leaf, n)
        if a > b:
            a, b = b, a
        leaf = tagged_sha256('TapBranch', a + b)

    tweak = tagged_sha256('TapTweak', xonly + leaf)
    t_int = int.from_bytes(tweak, 'big')
    # Build Q = P + tweak*G
    try:
        P = PublicKey.from_xonly(xonly)
    except Exception:
        P = PublicKey(b'\x02' + xonly)
    T = PrivateKey.from_int(t_int).public_key
    Q = PublicKey.combine_keys([P, T])
    qx = Q.format(compressed=True)[1:33]
    expected_spk = (b"\x51\x20" + qx).hex()
    actual_spk = witness_spk_hex.lower()
    ok = (expected_spk == actual_spk)
    return {
        'ok': ok,
        'expected_spk': expected_spk,
        'actual_spk': actual_spk,
        'reason': None if ok else 'scriptPubKey mismatch',
    }


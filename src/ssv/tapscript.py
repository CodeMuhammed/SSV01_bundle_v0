"""
SSV tapscript utilities (lean)

Policy (two branches)
OP_IF
  OP_SHA256 <h> OP_EQUALVERIFY
  <pk_b> OP_CHECKSIG
OP_ELSE
  <csv> OP_CHECKSEQUENCEVERIFY OP_DROP
  <pk_p> OP_CHECKSIG
OP_ENDIF

Witness (script-path)
- Borrower: [sig_b, s, 0x01, tapscript, control]
- Provider: [sig_p, 0x00, tapscript, control]

This module provides helpers to build the tapscript for the policy, compute
TapLeaf hashes, and produce a simple disassembly for debugging.
"""
from __future__ import annotations

import binascii
import hashlib
from typing import Dict

# Opcodes
OP_IF = 0x63
OP_ELSE = 0x67
OP_ENDIF = 0x68
OP_SHA256 = 0xa8
OP_EQUALVERIFY = 0x88
OP_CHECKSEQUENCEVERIFY = 0xb2
OP_DROP = 0x75
OP_CHECKSIG = 0xac

LEAF_VERSION = 0xC0  # BIP-342 tapscript leaf version


def pushdata(data: bytes) -> bytes:
    n = len(data)
    if n < 0x4c:
        return bytes([n]) + data
    elif n <= 0xff:
        return b"\x4c" + bytes([n]) + data
    elif n <= 0xffff:
        return b"\x4d" + n.to_bytes(2, "little") + data
    else:
        return b"\x4e" + n.to_bytes(4, "little") + data


def encode_scriptnum(n: int) -> bytes:
    if n == 0:
        return b""
    neg = n < 0
    n = abs(n)
    result = bytearray()
    while n:
        result.append(n & 0xff)
        n >>= 8
    if result[-1] & 0x80:
        result.append(0x80 if neg else 0x00)
    elif neg:
        result[-1] |= 0x80
    return bytes(result)


def push_scriptnum(n: int) -> bytes:
    return pushdata(encode_scriptnum(n))


def build_tapscript(hash_h_hex: str, borrower_pk_hex: str, csv_blocks: int, provider_pk_hex: str) -> bytes:
    """Build tapscript for the two-branch policy.

    Args:
        hash_h_hex: 32-byte hex string, sha256(s).
        borrower_pk_hex: 32-byte x-only borrower pubkey hex.
        csv_blocks: positive integer CSV timelock (blocks).
        provider_pk_hex: 32-byte x-only provider pubkey hex.
    """
    h = binascii.unhexlify(hash_h_hex)
    if len(h) != 32:
        raise ValueError("hash_h must be 32 bytes hex")
    pb = binascii.unhexlify(borrower_pk_hex)
    pp = binascii.unhexlify(provider_pk_hex)
    if len(pb) != 32 or len(pp) != 32:
        raise ValueError("borrower_pk and provider_pk must be 32-byte x-only pubkeys (hex)")
    if csv_blocks <= 0:
        raise ValueError("csv_blocks must be positive")

    script = bytearray()
    script += bytes([OP_IF])
    script += bytes([OP_SHA256]) + pushdata(h) + bytes([OP_EQUALVERIFY])
    script += pushdata(pb) + bytes([OP_CHECKSIG])
    script += bytes([OP_ELSE])
    script += push_scriptnum(csv_blocks) + bytes([OP_CHECKSEQUENCEVERIFY, OP_DROP])
    script += pushdata(pp) + bytes([OP_CHECKSIG])
    script += bytes([OP_ENDIF])
    return bytes(script)


def compactsize(n: int) -> bytes:
    if n < 0xfd:
        return bytes([n])
    elif n <= 0xffff:
        return b"\xfd" + n.to_bytes(2, "little")
    elif n <= 0xffffffff:
        return b"\xfe" + n.to_bytes(4, "little")
    else:
        return b"\xff" + n.to_bytes(8, "little")


def tapleaf_hash(script: bytes, leaf_version: int = LEAF_VERSION) -> bytes:
    data = bytes([leaf_version]) + compactsize(len(script)) + script
    return hashlib.sha256(data).digest()


def disasm(script: bytes) -> str:
    names: Dict[int, str] = {
        OP_IF: 'OP_IF',
        OP_ELSE: 'OP_ELSE',
        OP_ENDIF: 'OP_ENDIF',
        OP_SHA256: 'OP_SHA256',
        OP_EQUALVERIFY: 'OP_EQUALVERIFY',
        OP_CHECKSEQUENCEVERIFY: 'OP_CHECKSEQUENCEVERIFY',
        OP_DROP: 'OP_DROP',
        OP_CHECKSIG: 'OP_CHECKSIG',
    }
    out: list[str] = []
    i = 0
    while i < len(script):
        op = script[i]; i += 1
        if op in names:
            out.append(names[op])
        else:
            n = op
            if n < 0x4c:
                data = script[i:i+n]; i += n
            elif n == 0x4c:
                ln = script[i]; i += 1
                data = script[i:i+ln]; i += ln
            elif n == 0x4d:
                ln = int.from_bytes(script[i:i+2], 'little'); i += 2
                data = script[i:i+ln]; i += ln
            elif n == 0x4e:
                ln = int.from_bytes(script[i:i+4], 'little'); i += 4
                data = script[i:i+ln]; i += ln
            else:
                raise ValueError("Unexpected opcode/push")
            out.append(data.hex())
    return ' '.join(out)


def tagged_sha256(tag: str, msg: bytes) -> bytes:
    t = hashlib.sha256(tag.encode()).digest()
    return hashlib.sha256(t + t + msg).digest()


def tapleaf_hash_tagged(script: bytes, leaf_version: int = LEAF_VERSION) -> bytes:
    """BIP-341 tagged TapLeaf hash helper (for Merkle/tweak tooling)."""
    data = bytes([leaf_version]) + compactsize(len(script)) + script
    return tagged_sha256("TapLeaf", data)

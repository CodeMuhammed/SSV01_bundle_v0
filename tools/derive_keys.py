#!/usr/bin/env python3
"""
derive_keys.py — convenience helper to fetch compressed and x-only pubkeys

Usage examples (regtest):
  # Derive a new bech32m address from the vault wallet and print keys
  python tools/derive_keys.py --wallet vault --new

  # Use an existing address (borrower wallet)
  python tools/derive_keys.py --wallet borrower --address <BECH32M_ADDR>

  # Derive keys for all three wallets (creates new addresses)
  python tools/derive_keys.py --all

Notes
- Requires bitcoin-cli and loaded wallets (vault/borrower/provider) on regtest.
- Outputs JSON with: wallet, address, pubkey_compressed (33B hex), xonly (32B hex).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from typing import Any, Dict, Optional, Sequence


def run_cli(args: Sequence[str]) -> str:
    try:
        return subprocess.check_output(args, stderr=subprocess.STDOUT).decode().strip()
    except subprocess.CalledProcessError as e:
        print(e.output.decode(), file=sys.stderr)
        raise


def get_address_info(wallet: str, address: str, network: str) -> Dict[str, Any]:
    cli = ["bitcoin-cli", f"-{network}", f"-rpcwallet={wallet}", "getaddressinfo", address]
    out = run_cli(cli)
    return json.loads(out)


def get_new_address(wallet: str, network: str) -> str:
    cli = ["bitcoin-cli", f"-{network}", f"-rpcwallet={wallet}", "getnewaddress", "", "bech32m"]
    return run_cli(cli)


def compress_to_xonly(pubkey_hex: str) -> str:
    pubkey_hex = pubkey_hex.strip().lower()
    if len(pubkey_hex) != 66 or pubkey_hex[:2] not in ("02", "03"):
        raise ValueError("Expected 33-byte compressed pubkey hex (starts with 02/03)")
    return pubkey_hex[2:]


def derive_for_wallet(wallet: str, address: Optional[str], network: str) -> Dict[str, str]:
    if not address:
        address = get_new_address(wallet, network)
    info = get_address_info(wallet, address, network)
    comp = info.get("pubkey")
    if not comp:
        raise RuntimeError("Address info missing 'pubkey' (ensure descriptor wallet and correct address)")
    return {
        "wallet": wallet,
        "address": address,
        "pubkey_compressed": comp,
        "xonly": compress_to_xonly(comp),
    }


def main():
    ap = argparse.ArgumentParser(description="Derive compressed and x-only pubkeys from Core wallets (regtest)")
    ap.add_argument("--wallet", help="wallet name (e.g., vault|borrower|provider)")
    ap.add_argument("--address", help="existing address to query (bech32m)")
    ap.add_argument("--new", action="store_true", help="derive a new address if --address not supplied")
    ap.add_argument("--all", action="store_true", help="derive for vault,borrower,provider (new addresses)")
    ap.add_argument("--network", default="regtest", help="bitcoin network flag (default: regtest)")
    args = ap.parse_args()

    if args.all:
        results: list[Dict[str, str]] = []
        for w in ("vault", "borrower", "provider"):
            results.append(derive_for_wallet(w, None, args.network))
        print(json.dumps(results, indent=2))
        return

    if not args.wallet:
        ap.error("--wallet required (or use --all)")

    address = args.address
    if not address and not args.new:
        # default to new if none supplied
        args.new = True
    if args.new and not address:
        address = None

    out = derive_for_wallet(args.wallet, address, args.network)
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()

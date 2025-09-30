#!/usr/bin/env python3
"""
SSV CLI — minimal tapscript builder + PSBT finalizer + path verifier

Quick start (regtest sketch)
1) bitcoind -regtest; create wallets provider/borrower/vault
2) Collect params: h=sha256(s), borrower_xonly, provider_xonly, csv_blocks; import Taproot descriptor in vault wallet
3) Build tapscript:
   python -m ssv.cli build-tapscript --hash-h <h> --borrower-pk <xonly_b> --csv-blocks <n> --provider-pk <xonly_p>
4) Finalize PSBT witness once you have sigs + control block:
   Borrower: python -m ssv.cli finalize --mode borrower ... --sig <SIG_B> --preimage <s> --control <CTRL>
   Provider: python -m ssv.cli finalize --mode provider ... --sig <SIG_P>          --control <CTRL>

Notes
- Control block and signatures come from your wallet/descriptor engine.
- pk_b/pk_p are x-only; descriptor enforces the policy on-chain.
"""
import argparse
import sys

from .tapscript import build_tapscript, tapleaf_hash, tapleaf_hash_tagged, disasm
from .verify import verify_taproot_path
from .hexutil import parse_hex, file_or_hex
from .policy import PolicyParams
from .psbtio import load_psbt_from_file, write_psbt, to_raw_tx_hex, cscript_witness, get_input_witness_spk_hex
from .witness import Branch, build_witness


def cmd_build(args: argparse.Namespace) -> None:
    # validate via PolicyParams for clearer errors
    PolicyParams(args.hash_h, args.borrower_pk, args.provider_pk, args.csv_blocks).validate()
    script = build_tapscript(args.hash_h, args.borrower_pk, args.csv_blocks, args.provider_pk)
    leaf_simple = tapleaf_hash(script)
    leaf_tagged = tapleaf_hash_tagged(script)
    if args.json:
        import json
        out = {
            'tapscript_hex': script.hex(),
            'tapleaf_hash_simple': leaf_simple.hex(),
            'tapleaf_hash_tagged': leaf_tagged.hex(),
        }
        if args.disasm:
            out['disasm'] = disasm(script)
        print(json.dumps(out))
    else:
        print("tapscript_hex       =", script.hex())
        print("tapleaf_hash_simple =", leaf_simple.hex())
        print("tapleaf_hash_tagged =", leaf_tagged.hex())
        if args.disasm:
            print("disasm        =", disasm(script))


def finalize_witness(args: argparse.Namespace) -> None:
    try:
        CScriptWitness = cscript_witness()
    except Exception:
        print("ERROR: finalize requires python-bitcointx. Install with: pip install python-bitcointx", file=sys.stderr)
        raise

    # tapscript can come from hex or file, else we build
    if args.tapscript or getattr(args, 'tapscript_file', None):
        tapscript = file_or_hex('tapscript', args.tapscript, getattr(args, 'tapscript_file', None))
    else:
        if not (args.hash_h and args.borrower_pk and args.csv_blocks and args.provider_pk):
            raise ValueError("Either --tapscript[(-file)] or (--hash-h --borrower-pk --csv-blocks --provider-pk) must be supplied")
        PolicyParams(args.hash_h, args.borrower_pk, args.provider_pk, args.csv_blocks).validate()
        tapscript = build_tapscript(args.hash_h, args.borrower_pk, args.csv_blocks, args.provider_pk)

    # control block from hex or file
    control = file_or_hex('control', args.control, getattr(args, 'control_file', None))
    sig = parse_hex('sig', args.sig)

    # Load PSBT (auto-detect hex or base64)
    psbt = load_psbt_from_file(args.psbt_in)

    if args.input_index < 0 or args.input_index >= len(psbt.inputs):
        raise IndexError(f"Input index {args.input_index} out of range")

    if args.mode == 'borrower':
        if not args.preimage:
            raise ValueError("--preimage required in borrower mode")
        preimage = parse_hex('preimage', args.preimage)
        stack_items = build_witness(Branch.CLOSE, sig, tapscript, control, preimage=preimage)
    else:
        stack_items = build_witness(Branch.LIQUIDATE, sig, tapscript, control)

    psbt.inputs[args.input_index].final_scriptwitness = CScriptWitness(stack_items)
    pi = psbt.inputs[args.input_index]
    pi.partial_sigs = {}
    if hasattr(pi, 'taproot_leaf_script'):
        pi.taproot_leaf_script = []
    if hasattr(pi, 'taproot_bip32_derivations'):
        pi.taproot_bip32_derivations = {}
    if hasattr(pi, 'taproot_internal_key'):
        pi.taproot_internal_key = None

    write_psbt(psbt, args.psbt_out)

    if args.tx_out:
        try:
            raw = to_raw_tx_hex(psbt)
            with open(args.tx_out, 'wt') as f:
                f.write(raw)
        except Exception as e:
            print(f"Note: could not produce raw tx: {e}", file=sys.stderr)
            print("Finalized PSBT written; broadcast via bitcoin-cli.", file=sys.stderr)


def main():
    epilog = (
        "Quick start (regtest):\n"
        "  1) bitcoind -regtest; create wallets provider/borrower/vault\n"
        "  2) Import Taproot descriptor in vault wallet (internal_pub, h, pk_b, pk_p, CSV) and fund it\n"
        "  3) Build tapscript: python -m ssv.cli build-tapscript --hash-h <h> --borrower-pk <b> --csv-blocks <n> --provider-pk <p>\n"
        "  4) Finalize witness (borrower/provider) once you have sig(s) + control block\n"
        "Notes: control block and signatures come from your wallet/descriptor engine."
    )
    ap = argparse.ArgumentParser(description="SSV CLI (build tapscript, finalize PSBT)", epilog=epilog,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)

    ap_b = sub.add_parser('build-tapscript', help='build the tapscript and compute tapleaf hash')
    ap_b.add_argument('--hash-h', required=True, help='32B hex, SHA256(s)')
    ap_b.add_argument('--borrower-pk', required=True, help='32B hex x-only pubkey')
    ap_b.add_argument('--csv-blocks', required=True, type=int, help='relative timelock in blocks')
    ap_b.add_argument('--provider-pk', required=True, help='32B hex x-only pubkey')
    ap_b.add_argument('--disasm', action='store_true', help='print simple disassembly')
    ap_b.add_argument('--json', action='store_true', help='print JSON output')
    ap_b.set_defaults(func=cmd_build)

    ap_f = sub.add_parser('finalize', help='finalize a PSBT input with Taproot script-path witness')
    ap_f.add_argument('--mode', choices=['borrower','provider'], required=True, help='borrower=CLOSE (IF); provider=LIQUIDATE (ELSE)')
    ap_f.add_argument('--psbt-in', required=True, help='input PSBT file (base64 or hex)')
    ap_f.add_argument('--psbt-out', required=True, help='output PSBT file (base64)')
    ap_f.add_argument('--tx-out', help='optional raw tx hex file to write')
    ap_f.add_argument('--input-index', type=int, default=0, help='which input to finalize')
    ap_f.add_argument('--sig', required=True, help='Schnorr signature hex (64/65 bytes)')
    ap_f.add_argument('--preimage', help='borrower mode only: preimage s hex')
    ap_f.add_argument('--control', help='Taproot control block hex')
    ap_f.add_argument('--control-file', help='read control block hex from file')
    ap_f.add_argument('--tapscript', help='explicit tapscript hex for this path')
    ap_f.add_argument('--tapscript-file', help='read tapscript hex from file')
    ap_f.add_argument('--hash-h', help='if no --tapscript, provide these to build tapscript')
    ap_f.add_argument('--borrower-pk', help='x-only, 32B hex')
    ap_f.add_argument('--csv-blocks', type=int, help='relative timelock blocks')
    ap_f.add_argument('--provider-pk', help='x-only, 32B hex')
    ap_f.set_defaults(func=finalize_witness)

    ap_v = sub.add_parser('verify-path', help='verify tapscript/control block against input witness_utxo spk')
    ap_v.add_argument('--tapscript', help='tapscript hex')
    ap_v.add_argument('--tapscript-file', help='read tapscript hex from file')
    ap_v.add_argument('--control', help='control block hex')
    ap_v.add_argument('--control-file', help='read control block hex from file')
    ap_v.add_argument('--witness-spk', help='witness scriptPubKey hex (v1 segwit taproot)')
    ap_v.add_argument('--psbt-in', help='optional PSBT (base64 or hex) to extract witness_utxo spk from input 0')
    ap_v.add_argument('--json', action='store_true', help='print JSON output')
    def cmd_verify(args: argparse.Namespace) -> None:
        taps_hex = file_or_hex('tapscript', args.tapscript, args.tapscript_file).hex()
        ctrl_hex = file_or_hex('control', args.control, args.control_file).hex()
        from typing import Optional
        spk_hex: Optional[str] = args.witness_spk
        psbt_in: Optional[str] = args.psbt_in
        if spk_hex is None and psbt_in is not None:
            try:
                psbt = load_psbt_from_file(psbt_in)
            except Exception:
                print('Install python-bitcointx to read PSBTs for verification', file=sys.stderr)
                raise
            spk_hex = get_input_witness_spk_hex(psbt, 0)
        if spk_hex is None:
            raise ValueError('Provide --witness-spk or --psbt-in')
        res = verify_taproot_path(taps_hex, ctrl_hex, spk_hex)
        if args.json:
            import json
            print(json.dumps(res))
        else:
            ok = res.get('ok')
            if ok:
                print('[OK] taproot path verified')
            else:
                print('[FAIL] taproot path mismatch')
            print('expected_spk =', res.get('expected_spk'))
            print('actual_spk   =', res.get('actual_spk'))
            if res.get('reason'):
                print('reason      =', res.get('reason'))
    ap_v.set_defaults(func=cmd_verify)

    # anchor-verify: lean check that a given output index matches expected SPK/value
    ap_a = sub.add_parser('anchor-verify', help='verify that a PSBT has an output matching index/SPK/value (TapRet anchor check)')
    ap_a.add_argument('--psbt-in', required=True, help='input PSBT file (base64 or hex)')
    ap_a.add_argument('--index', required=True, type=int, help='output index to check')
    ap_a.add_argument('--spk', required=True, help='expected scriptPubKey hex at the index (TapRet P2TR)')
    ap_a.add_argument('--value', required=True, type=int, help='expected output value in sats at the index')
    ap_a.add_argument('--json', action='store_true', help='print JSON output')
    def cmd_anchor_verify(args: argparse.Namespace) -> None:
        try:
            psbt = load_psbt_from_file(args.psbt_in)
        except Exception as e:
            print(f'ERROR: anchor-verify requires python-bitcointx to read PSBTs ({e})', file=sys.stderr)
            raise

        # Access the unsigned transaction and outputs
        tx = getattr(psbt, 'tx', None) or getattr(psbt, 'unsigned_tx', None)
        if tx is None:
            raise RuntimeError('PSBT does not expose unsigned transaction (tx)')
        vout = getattr(tx, 'vout', None)
        if vout is None:
            raise RuntimeError('Transaction has no outputs list (vout)')
        if args.index < 0 or args.index >= len(vout):
            raise IndexError(f'output index {args.index} out of range (num_outputs={len(vout)})')
        out = vout[args.index]
        # scriptPubKey hex
        actual_spk = out.scriptPubKey.hex()
        # value
        actual_value = getattr(out, 'nValue', None)
        if actual_value is None:
            # alternative attribute name in some variants
            actual_value = getattr(out, 'value', None)
        if actual_value is None:
            raise RuntimeError('Could not read output value')

        ok_spk = (actual_spk.lower() == args.spk.lower())
        ok_value = (int(actual_value) == int(args.value))
        ok = ok_spk and ok_value
        if args.json:
            import json
            print(json.dumps({
                'ok': ok,
                'index': args.index,
                'expected_spk': args.spk.lower(),
                'actual_spk': actual_spk.lower(),
                'expected_value': int(args.value),
                'actual_value': int(actual_value),
                'reason': None if ok else ('spk mismatch' if not ok_spk else 'value mismatch'),
            }))
        else:
            print('[OK] anchor output matches' if ok else '[FAIL] anchor output mismatch')
            print('index         =', args.index)
            print('expected_spk  =', args.spk.lower())
            print('actual_spk    =', actual_spk.lower())
            print('expected_sat  =', int(args.value))
            print('actual_sat    =', int(actual_value))
            if not ok:
                print('reason        =', 'spk mismatch' if not ok_spk else 'value mismatch')
    ap_a.set_defaults(func=cmd_anchor_verify)

    args = ap.parse_args()
    args.func(args)

if __name__ == '__main__':
    main()

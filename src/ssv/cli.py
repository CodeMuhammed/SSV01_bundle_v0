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
import argparse, sys, binascii

from .tapscript import build_tapscript, tapleaf_hash, tapleaf_hash_tagged, disasm
from .verify import verify_taproot_path


def h2b(name, s):
    try:
        return binascii.unhexlify(s)
    except Exception:
        raise ValueError(f"Invalid hex for {name}")


def cmd_build(args):
    script = build_tapscript(args.hash_h, args.borrower_pk, args.csv_blocks, args.provider_pk)
    leaf_simple = tapleaf_hash(script)
    leaf_tagged = tapleaf_hash_tagged(script)
    print("tapscript_hex       =", script.hex())
    print("tapleaf_hash_simple =", leaf_simple.hex())
    print("tapleaf_hash_tagged =", leaf_tagged.hex())
    if args.disasm:
        print("disasm        =", disasm(script))


def finalize_witness(args):
    try:
        from bitcointx.core.psbt import PSBT
        from bitcointx.core.script import CScriptWitness
        from bitcointx.core import b2x
    except Exception:
        print("ERROR: finalize requires python-bitcointx. Install with: pip install python-bitcointx", file=sys.stderr)
        raise

    # tapscript can come from hex or file, else we build
    if args.tapscript:
        tapscript = h2b('tapscript', args.tapscript)
    elif getattr(args, 'tapscript_file', None):
        with open(args.tapscript_file, 'rt') as f:
            tapscript = h2b('tapscript_file', f.read().strip())
    else:
        if not (args.hash_h and args.borrower_pk and args.csv_blocks and args.provider_pk):
            raise ValueError("Either --tapscript or (--hash-h --borrower-pk --csv-blocks --issuer-pk) must be supplied")
        tapscript = build_tapscript(args.hash_h, args.borrower_pk, args.csv_blocks, args.provider_pk)

    # control block from hex or file
    control_hex = args.control
    if not control_hex and getattr(args, 'control_file', None):
        with open(args.control_file, 'rt') as f:
            control_hex = f.read().strip()
    if not control_hex:
        raise ValueError("Control block required: provide --control or --control-file")
    control = h2b('control', control_hex)
    sig = h2b('sig', args.sig)

    # Load PSBT (base64 or hex file contents)
    import base64, re
    with open(args.psbt_in, 'rt') as f:
        s = f.read().strip()
    def is_hex_str(x: str) -> bool:
        return re.fullmatch(r'[0-9a-fA-F]+', x) is not None
    if is_hex_str(s):
        raw = binascii.unhexlify(s)
        psbt_b64 = base64.b64encode(raw).decode()
    else:
        psbt_b64 = s
    psbt = PSBT.from_base64(psbt_b64)

    if args.input_index < 0 or args.input_index >= len(psbt.inputs):
        raise IndexError(f"Input index {args.input_index} out of range")

    if args.mode == 'borrower':
        if not args.preimage:
            raise ValueError("--preimage required in borrower mode")
        preimage = h2b('preimage', args.preimage)
        stack_items = [sig, preimage, b'\x01', tapscript, control]
    else:
        stack_items = [sig, b'\x00', tapscript, control]

    psbt.inputs[args.input_index].final_scriptwitness = CScriptWitness(stack_items)
    pi = psbt.inputs[args.input_index]
    pi.partial_sigs = {}
    if hasattr(pi, 'taproot_leaf_script'):
        pi.taproot_leaf_script = []
    if hasattr(pi, 'taproot_bip32_derivations'):
        pi.taproot_bip32_derivations = {}
    if hasattr(pi, 'taproot_internal_key'):
        pi.taproot_internal_key = None

    with open(args.psbt_out, 'wt') as f:
        f.write(psbt.to_base64())

    if args.tx_out:
        try:
            tx = psbt.to_tx()
            with open(args.tx_out, 'wt') as f:
                f.write(b2x(tx.serialize()))
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
    def cmd_verify(args):
        import base64, binascii, re
        def read_hex_arg(name, val, fpath):
            if val: return val.strip()
            if fpath:
                with open(fpath, 'rt') as f:
                    return f.read().strip()
            raise ValueError(f"{name} required")
        taps_hex = read_hex_arg('tapscript', args.tapscript, args.tapscript_file)
        ctrl_hex = read_hex_arg('control', args.control, args.control_file)
        spk_hex = args.witness_spk
        if not spk_hex and args.psbt_in:
            try:
                from bitcointx.core.psbt import PSBT
            except Exception:
                print('Install python-bitcointx to read PSBTs for verification', file=sys.stderr)
                raise
            with open(args.psbt_in,'rt') as f:
                s = f.read().strip()
            def is_hex_str(x: str) -> bool:
                return re.fullmatch(r'[0-9a-fA-F]+', x) is not None
            if is_hex_str(s):
                raw = binascii.unhexlify(s)
                s = base64.b64encode(raw).decode()
            psbt = PSBT.from_base64(s)
            iu = psbt.inputs[0].witness_utxo
            if not iu:
                raise ValueError('PSBT input 0 missing witness_utxo')
            spk_hex = iu.scriptPubKey.hex()
        if not spk_hex:
            raise ValueError('Provide --witness-spk or --psbt-in')
        res = verify_taproot_path(taps_hex, ctrl_hex, spk_hex)
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

    args = ap.parse_args()
    args.func(args)

if __name__ == '__main__':
    main()

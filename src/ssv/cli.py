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
from typing import Any, Optional, List, Dict, NamedTuple

from .tapscript import build_tapscript, tapleaf_hash, tapleaf_hash_tagged, disasm, pushdata as script_pushdata
from .verify import verify_taproot_path
from .hexutil import parse_hex, file_or_hex
from .policy import PolicyParams
from .psbtio import load_psbt_from_file, write_psbt, to_raw_tx_hex, cscript_witness, get_input_witness_spk_hex
from .witness import Branch, build_witness


class AnchorCheckResult(NamedTuple):
    ok: bool
    reason: Optional[str]
    expected_spk: str
    actual_spk: str
    expected_value: int
    actual_value: Optional[int]


class OpretCheckResult(NamedTuple):
    ok: bool
    reason: Optional[str]
    expected_spk: str
    actual_spk: str
    expected_value: Optional[int]
    actual_value: Optional[int]


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


# PSBT/tx helpers and verifiers
def _tx_from_psbt(psbt: Any) -> Any:
    return getattr(psbt, 'tx', None) or getattr(psbt, 'unsigned_tx', None)


def _get_vout_list(tx: Any) -> List[Any]:
    vout = getattr(tx, 'vout', None)
    if vout is None:
        raise RuntimeError('Transaction has no outputs list (vout)')
    return list(vout)


def _get_out_value(out: Any) -> Optional[int]:
    v = getattr(out, 'nValue', None)
    if v is None:
        v = getattr(out, 'value', None)
    return None if v is None else int(v)


def _require_non_negative_int(name: str, value: Any) -> int:
    try:
        ivalue = int(value)
    except Exception as exc:  # pragma: no cover - defensive
        raise ValueError(f'{name} must be an integer') from exc
    if ivalue < 0:
        raise ValueError(f'{name} must be non-negative')
    return ivalue


def _canonicalize_script_hex(name: str, script_hex: str) -> str:
    return parse_hex(name, script_hex).hex()


def _normalize_hex_arg(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    return ''.join(value.split()).lower()


def verify_anchor_output(psbt: Any, index: int, spk_hex: str, value: int) -> AnchorCheckResult:
    tx = _tx_from_psbt(psbt)
    if tx is None:
        raise RuntimeError('PSBT does not expose unsigned transaction (tx)')
    vout = _get_vout_list(tx)
    if index < 0 or index >= len(vout):
        raise IndexError(f'output index {index} out of range (num_outputs={len(vout)})')
    out_obj: Any = vout[index]
    expected_spk = _canonicalize_script_hex('spk', spk_hex)
    expected_value = _require_non_negative_int('value', value)
    actual_spk: str = out_obj.scriptPubKey.hex().lower()
    actual_value = _get_out_value(out_obj)
    if actual_value is None:
        raise RuntimeError('Could not read output value')
    actual_value_int = int(actual_value)
    ok_spk = (actual_spk == expected_spk)
    ok_value = (actual_value_int == expected_value)
    ok = ok_spk and ok_value
    reason: Optional[str] = None if ok else ('spk mismatch' if not ok_spk else 'value mismatch')
    return AnchorCheckResult(ok, reason, expected_spk, actual_spk, expected_value, actual_value_int)


def verify_opret_output(psbt: Any, index: int, data_hex: str, value: Optional[int] = None) -> OpretCheckResult:
    tx = _tx_from_psbt(psbt)
    if tx is None:
        raise RuntimeError('PSBT does not expose unsigned transaction (tx)')
    vout = _get_vout_list(tx)
    if index < 0 or index >= len(vout):
        raise IndexError(f'output index {index} out of range (num_outputs={len(vout)})')
    out_obj: Any = vout[index]
    actual_spk: str = out_obj.scriptPubKey.hex().lower()
    data_bytes = parse_hex('data', data_hex)
    expected_spk: str = (b"\x6a" + script_pushdata(data_bytes)).hex()
    ok_spk = (actual_spk == expected_spk)
    actual_value_raw = _get_out_value(out_obj)
    actual_value = None if actual_value_raw is None else int(actual_value_raw)
    ok_value = True
    expected_value: Optional[int] = None
    if value is not None:
        expected_value = _require_non_negative_int('value', value)
        if actual_value is None:
            raise RuntimeError('Could not read output value')
        ok_value = (actual_value == expected_value)
    ok = ok_spk and ok_value
    reason: Optional[str] = None if ok else ('spk mismatch' if not ok_spk else 'value mismatch')
    return OpretCheckResult(ok, reason, expected_spk, actual_spk, expected_value, actual_value)


def cmd_verify_path(args: argparse.Namespace) -> None:
    taps_hex = file_or_hex('tapscript', args.tapscript, args.tapscript_file).hex()
    ctrl_hex = file_or_hex('control', args.control, args.control_file).hex()
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


def cmd_anchor_verify(args: argparse.Namespace) -> None:
    try:
        psbt = load_psbt_from_file(args.psbt_in)
    except Exception as e:
        print(f'ERROR: anchor-verify requires python-bitcointx to read PSBTs ({e})', file=sys.stderr)
        raise
    spk_arg = _normalize_hex_arg(args.spk)
    res = verify_anchor_output(psbt, args.index, spk_arg, args.value)
    if args.json:
        import json
        print(json.dumps({
            'ok': res.ok,
            'index': args.index,
            'expected_spk': spk_arg,
            'actual_spk': res.actual_spk,
            'expected_value': res.expected_value,
            'actual_value': res.actual_value,
            'reason': res.reason,
        }))
    else:
        print('[OK] anchor output matches' if res.ok else '[FAIL] anchor output mismatch')
        print('index         =', args.index)
        print('expected_spk  =', spk_arg)
        print('actual_spk    =', res.actual_spk)
        print('expected_sat  =', res.expected_value)
        print('actual_sat    =', res.actual_value)
        if not res.ok and res.reason:
            print('reason        =', res.reason)


def cmd_opret_verify(args: argparse.Namespace) -> None:
    try:
        psbt = load_psbt_from_file(args.psbt_in)
    except Exception as e:
        print(f'ERROR: opret-verify requires python-bitcointx to read PSBTs ({e})', file=sys.stderr)
        raise
    res = verify_opret_output(psbt, args.index, args.data, args.value)
    if args.json:
        import json
        print(json.dumps({
            'ok': res.ok,
            'index': args.index,
            'expected_spk': res.expected_spk,
            'actual_spk': res.actual_spk,
            'expected_value': res.expected_value,
            'actual_value': res.actual_value,
            'reason': res.reason,
        }))
    else:
        print('[OK] OP_RETURN output matches' if res.ok else '[FAIL] OP_RETURN output mismatch')
        print('index         =', args.index)
        print('expected_spk  =', res.expected_spk)
        print('actual_spk    =', res.actual_spk)
        if res.expected_value is not None:
            print('expected_sat  =', res.expected_value)
            print('actual_sat    =', res.actual_value)
        if not res.ok and res.reason:
            print('reason        =', res.reason)


def cmd_anchor_show(args: argparse.Namespace) -> None:
    try:
        psbt = load_psbt_from_file(args.psbt_in)
    except Exception as e:
        print(f'ERROR: anchor-show requires python-bitcointx to read PSBTs ({e})', file=sys.stderr)
        raise
    tx = _tx_from_psbt(psbt)
    if tx is None:
        raise RuntimeError('PSBT does not expose unsigned transaction (tx)')
    vout = _get_vout_list(tx)
    rows: List[Dict[str, Any]] = []
    for i, out_obj in enumerate(vout):
        spk = out_obj.scriptPubKey.hex()
        val = _get_out_value(out_obj)
        rows.append({'index': i, 'value': val, 'spk': spk})
    if args.json:
        import json
        print(json.dumps(rows))
    else:
        for r in rows:
            print(f"{r['index']}: value={r['value']} spk={r['spk']}")
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

    # Optional guards: verify presence of anchors before finalizing

    # TapRet anchor guard
    if any(getattr(args, k, None) is not None for k in ('require_anchor_index','require_anchor_spk','require_anchor_value')):
        if args.require_anchor_index is None or args.require_anchor_spk is None or args.require_anchor_value is None:
            raise ValueError('When using --require-anchor-*, provide all of: --require-anchor-index, --require-anchor-spk, --require-anchor-value')
        res = verify_anchor_output(
            psbt,
            int(args.require_anchor_index),
            _normalize_hex_arg(args.require_anchor_spk),
            int(args.require_anchor_value),
        )
        if not res.ok:
            raise ValueError(f'Anchor guard failed: {res.reason}')

    # OP_RETURN guard
    if any(getattr(args, k, None) is not None for k in ('require_opret_index','require_opret_data','require_opret_value')):
        if args.require_opret_index is None or args.require_opret_data is None:
            raise ValueError('When using --require-opret-*, provide at least: --require-opret-index and --require-opret-data [--require-opret-value optional]')
        res = verify_opret_output(psbt, int(args.require_opret_index), args.require_opret_data, args.require_opret_value)
        if not res.ok:
            raise ValueError(f'OP_RETURN guard failed: {res.reason}')

    if args.input_index < 0 or args.input_index >= len(psbt.inputs):
        raise IndexError(f"Input index {args.input_index} out of range")

    if args.mode == 'borrower':
        if not args.preimage:
            raise ValueError("--preimage required in borrower mode")
        preimage = parse_hex('preimage', args.preimage, length=32)
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
    ap_b.add_argument('--csv-blocks', required=True, type=int, help='relative timelock in blocks (1-65535, BIP-68)')
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
    ap_f.add_argument('--csv-blocks', type=int, help='relative timelock blocks (1-65535, BIP-68)')
    ap_f.add_argument('--provider-pk', help='x-only, 32B hex')
    # Optional guards to enforce anchors before finalizing
    ap_f.add_argument('--require-anchor-index', type=int, help='require a TapRet anchor at this output index')
    ap_f.add_argument('--require-anchor-spk', help='expected TapRet anchor SPK hex at the index')
    ap_f.add_argument('--require-anchor-value', type=int, help='expected anchor value (sats) at the index')
    ap_f.add_argument('--require-opret-index', type=int, help='require an OP_RETURN output at this index')
    ap_f.add_argument('--require-opret-data', help='expected OP_RETURN data (hex)')
    ap_f.add_argument('--require-opret-value', type=int, help='optional expected OP_RETURN value (sats)')
    ap_f.set_defaults(func=finalize_witness)

    ap_v = sub.add_parser('verify-path', help='verify tapscript/control block against input witness_utxo spk')
    ap_v.add_argument('--tapscript', help='tapscript hex')
    ap_v.add_argument('--tapscript-file', help='read tapscript hex from file')
    ap_v.add_argument('--control', help='control block hex')
    ap_v.add_argument('--control-file', help='read control block hex from file')
    ap_v.add_argument('--witness-spk', help='witness scriptPubKey hex (v1 segwit taproot)')
    ap_v.add_argument('--psbt-in', help='optional PSBT (base64 or hex) to extract witness_utxo spk from input 0')
    ap_v.add_argument('--json', action='store_true', help='print JSON output')
    ap_v.set_defaults(func=cmd_verify_path)

    # anchor-verify: lean check that a given output index matches expected SPK/value
    ap_a = sub.add_parser('anchor-verify', help='verify that a PSBT has an output matching index/SPK/value (TapRet anchor check)')
    ap_a.add_argument('--psbt-in', required=True, help='input PSBT file (base64 or hex)')
    ap_a.add_argument('--index', required=True, type=int, help='output index to check')
    ap_a.add_argument('--spk', required=True, help='expected scriptPubKey hex at the index (TapRet P2TR)')
    ap_a.add_argument('--value', required=True, type=int, help='expected output value in sats at the index')
    ap_a.add_argument('--json', action='store_true', help='print JSON output')
    ap_a.set_defaults(func=cmd_anchor_verify)

    # opret-verify: verify an OP_RETURN output contains the expected data push (and optional value)
    ap_o = sub.add_parser('opret-verify', help='verify that a PSBT has an OP_RETURN output with expected data at index')
    ap_o.add_argument('--psbt-in', required=True, help='input PSBT file (base64 or hex)')
    ap_o.add_argument('--index', required=True, type=int, help='output index to check')
    ap_o.add_argument('--data', required=True, help='expected OP_RETURN data (hex)')
    ap_o.add_argument('--value', type=int, help='optional expected output value in sats (commonly 0)')
    ap_o.add_argument('--json', action='store_true', help='print JSON output')
    ap_o.set_defaults(func=cmd_opret_verify)

    # anchor-show: list outputs for convenience
    ap_s = sub.add_parser('anchor-show', help='list transaction outputs (index, value, scriptPubKey hex) from a PSBT')
    ap_s.add_argument('--psbt-in', required=True, help='input PSBT file (base64 or hex)')
    ap_s.add_argument('--json', action='store_true', help='print JSON output')
    ap_s.set_defaults(func=cmd_anchor_show)

    args = ap.parse_args()
    args.func(args)

if __name__ == '__main__':
    main()

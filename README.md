SSV — Taproot Vault Toolkit (Lean)

## Why SSV exists
SSV gives borrowers and liquidity providers a minimal, auditable Taproot vault workflow that can be coupled with RGB or other covenant layers. The toolkit focuses on:
- A two-branch Taproot script that enforces either atomic repayment (`CLOSE`) or timelocked liquidation (`LIQUIDATE`).
- CLI helpers to build the tapscript, verify Taproot paths/control blocks, and finalize PSBTs with strong optional guards (TapRet/OP_RETURN anchors).
- Thin Python modules that you can reuse from your own orchestration code.

If you understand the high-level flow below, the rest of the repository will feel familiar.

```
Borrower funds vault  ─┬─> Provider sees collateral locked under Taproot policy
                       │
                       ├─> Repay path (happy):
                       │      • Borrower reveals preimage `s` in CLOSE spend
                       │      • RGB TapRet anchor assures provider receives principal+interest
                       │      • Borrower reclaims BTC collateral
                       │
                       └─> Liquidation (default):
                              • If borrower fails to repay before CSV expires
                              • Provider waits `csv_blocks` then spends LIQUIDATE branch
                              • Provider receives BTC collateral on L1
```

## Core policy at a glance
The tapscript that SSV builds is intentionally simple:

```
OP_IF
  OP_SHA256 `h` OP_EQUALVERIFY
  `pk_b` OP_CHECKSIG        # Borrower must reveal preimage `s` such that sha256(s)=h
OP_ELSE
  `csv_blocks` OP_CHECKSEQUENCEVERIFY OP_DROP
  `pk_p` OP_CHECKSIG        # Provider can claim after the CSV delay
OP_ENDIF
```

- **Borrower path (CLOSE)**: witness stack `[sig_b, s, 0x01, tapscript, control]`
- **Provider path (LIQUIDATE)**: witness stack `[sig_p, 0x00, tapscript, control]`

Shared parameters the parties must agree on:

| Parameter | Purpose |
|-----------|---------|
| `h` | Commitment to borrower’s preimage `s` (`h = sha256(s)`) |
| `csv_blocks` | Relative timelock for provider liquidation (BIP-68 range 1–65535) |
| `pk_b`, `pk_p` | X-only Taproot keys for borrower/provider script branches |
| `principal_usdt`, `interest_usdt` | RGB settlement terms (off-chain agreement) |
| Optional `maturity_height` | Extra RGB-side guard if desired |

## Repository map

| Path | Description |
|------|-------------|
| `src/ssv/tapscript.py` | Builds tapscript bytes, TapLeaf hashes, disassembly. |
| `src/ssv/policy.py` | Validates high-level policy parameters (`PolicyParams`). |
| `src/ssv/taproot.py` | Taproot control block parsing, TapTweak computation, scriptPubKey helpers. |
| `src/ssv/witness.py` | Builds borrower/provider script-path witness stacks with input validation. |
| `src/ssv/psbtio.py` | python-bitcointx shims for loading/writing PSBTs, converting to raw hex. |
| `src/ssv/cli.py` | Entry point for `ssv` command: build tapscript, finalize PSBTs, verify anchors. |
| `examples/` | Regtest helper scripts (`make demo-close`, `make demo-liq`). |
| `tests/` | Pytest suite covering every CLI subcommand and taproot/tapscript primitive. |

## Typical lifecycle

1. **Agree on policy**  
   Select borrower/provider keys, choose `csv_blocks`, draw a random `s` (preimage) and compute `h = sha256(s)`.  
   Use `ssv build-tapscript` to render the tapscript and verify the TapLeaf hash matches what goes on-chain.

2. **Fund the Taproot vault**  
   Import the descriptor into the vault wallet (`tr(internal, { …script branches… })`), fund the P2TR output, and share the resulting UTXO details.

3. **Attach RGB anchor (optional but expected)**  
   While preparing the borrower’s CLOSE PSBT, add a TapRet or OP_RETURN anchor tying the repayment transfer to the on-chain spend.

4. **Finalize borrower PSBT**  
   Run `ssv finalize --mode borrower ...` supplying:
   - Borrower signature (`sig_b`)
   - `s` (preimage)
   - Control block and tapscript (or have the CLI rebuild tapscript from parameters)
   - Optional guards `--require-anchor-*` or `--require-opret-*` so the script refuses to finalize if the anchor is missing.

5. **Liquidation fallback**  
   If repayment fails, the provider constructs a PSBT with `nSequence = csv_blocks` on the vault input, signs with `pk_p`, and finalizes via `ssv finalize --mode provider ...`.

6. **Auditability**  
   Additional commands (`verify-path`, `anchor-verify`, `opret-verify`) let either side prove the control block matches the P2TR output and the anchor outputs are still intact before signatures are revealed.

## CLI reference

```
ssv build-tapscript  --hash-h <H> --borrower-pk <XONLY_B> --csv-blocks <N> --provider-pk <XONLY_P> [--disasm] [--json]
ssv finalize         --mode {borrower|provider} --psbt-in <PATH> --psbt-out <PATH> --sig <SIG> --control <HEX|FILE> \
                     [--preimage <S>] [--tapscript <HEX|FILE> | --hash-h/--borrower-pk/--csv-blocks/--provider-pk] \
                     [--tx-out <RAW_TX_FILE>] \
                     [--require-anchor-index <I> --require-anchor-spk <HEX> --require-anchor-value <SAT>] \
                     [--require-opret-index <I> --require-opret-data <HEX> --require-opret-value <SAT>]
ssv verify-path      --tapscript <HEX|FILE> --control <HEX|FILE> (--witness-spk <HEX> | --psbt-in <PATH>) [--json]
ssv anchor-verify    --psbt-in <PATH> --index <I> --spk <HEX> --value <SAT> [--json]
ssv opret-verify     --psbt-in <PATH> --index <I> --data <HEX> [--value <SAT>] [--json]
ssv anchor-show      --psbt-in <PATH> [--json]
```

### Key CLI idioms
- Supply hex directly or via files using `--tapscript` / `--tapscript-file`, `--control` / `--control-file`.
- When `python-bitcointx` exposes `PartiallySignedTransaction` instead of `PSBT`, SSV adapts automatically.
- Add `--json` to get machine-friendly output for automation.
- `finalize --tx-out` dumps a fully signed raw transaction if the PSBT is now broadcast-ready (subject to python-bitcointx capabilities).

## RGB anchoring

### TapRet (preferred)
1. Use RGB tooling (v0.12) to compute the TapRet anchor scriptPubKey and value—choose a dust-safe amount.
2. Insert the anchor output in the borrower CLOSE PSBT before signatures.
3. `ssv anchor-verify` to assert index/SPK/value are still present.
4. `ssv finalize --require-anchor-*` so the borrower cannot finalize without the anchor or if an RBF rewrite drops it.

### OP_RETURN fallback
If TapRet support is unavailable, you may anchor via an OP_RETURN output:
1. Add `OP_RETURN <DATA>` output to the repayment PSBT.
2. `ssv opret-verify` to ensure the commitment is intact.
3. Use the same guard flags when finalizing.

## Working with control blocks
- Descriptor wallets usually export the Taproot leaf script and control block when you select a script-path spend.
- Ensure the control block’s internal key matches the descriptor’s internal key and the merkle path/parity correspond to your leaf.
- `ssv verify-path` recomputes the Taproot tweak and parity; it fails fast if the control block is malformed.

## CSV quick facts
- `csv_blocks` lives in the low 16 bits of nSequence (`0x0000NNNN`), type flag = 0 (block-based).
- Transactions must be version ≥ 2 for CSV to activate.
- Provider-side PSBT should set `nSequence = csv_blocks` and wait until the vault input has that many confirmations.

## Development & tests

Create a virtualenv (optional but recommended):
```
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Run the full test suite:
```
pytest -q
```

Highlights from `tests/`:
- `test_taproot.py` validates control block parsing, TapTweak parity detection, and coincurve fallbacks.
- `test_cli.py`, `test_finalize_guards.py`, `test_anchor_verify.py`, `test_opret_verify.py` cover CLI contract-level behaviour, including guard failures and JSON output.
- `test_psbtio.py` ensures python-bitcointx shims work for both legacy `PSBT` and new `PartiallySignedTransaction` APIs.

The repository assumes coincurve and python-bitcointx are available. Docker images (see `docker-compose.yml`) bundle these dependencies for deterministic demos.

## Appendix: descriptor template

```
tr(
  `internal_pub`,
  {
    and_v( v:sha256(`h`), pk(`pk_b`) ),
    and_v( v:older(`csv_blocks`), pk(`pk_p`) )
  }
)
```

Use `getdescriptorinfo` to canonicalize and checksum before calling `importdescriptors`.

### Deriving keys with Core (regtest, docker)

```
# Internal key for tr()
VAULT_ADDR=$(docker compose exec -T bitcoin bitcoin-cli -regtest -rpcwallet=vault getnewaddress "" bech32m)
INTERNAL_PUB=$(docker compose exec -T bitcoin bitcoin-cli -regtest -rpcwallet=vault getaddressinfo "$VAULT_ADDR" | jq -r .pubkey)

# Borrower / provider x-only keys for tapscript
BORR_ADDR=$(docker compose exec -T bitcoin bitcoin-cli -regtest -rpcwallet=borrower getnewaddress "" bech32m)
BORR_COMP=$(docker compose exec -T bitcoin bitcoin-cli -regtest -rpcwallet=borrower getaddressinfo "$BORR_ADDR" | jq -r .pubkey)
pk_b=${BORR_COMP:2}

PROV_ADDR=$(docker compose exec -T bitcoin bitcoin-cli -regtest -rpcwallet=provider getnewaddress "" bech32m)
PROV_COMP=$(docker compose exec -T bitcoin bitcoin-cli -regtest -rpcwallet=provider getaddressinfo "$PROV_ADDR" | jq -r .pubkey)
pk_p=${PROV_COMP:2}
```

If `jq` is unavailable, Python one-liners inside the container offer the same functionality (see `README` history or `tools/derive_keys.py`).

### Generating preimage and hash

```
s=$(openssl rand -hex 32)
h=$(printf "%s" "$s" | xxd -r -p | openssl dgst -sha256 -binary | xxd -p -c 256)
# or
python - <<'PY'
import os, hashlib
s = os.urandom(32).hex()
h = hashlib.sha256(bytes.fromhex(s)).hexdigest()
print("s =", s)
print("h =", h)
PY
```

---

For a complete walkthrough, run the regtest demos:

```
make docker-up
make demo-close   # borrower repayment flow (prompts for RGB anchor)
make demo-liq     # provider liquidation after CSV
```

They build the descriptor, fund the Taproot vault, guide you through the RGB anchor insertion, and show how to finalize both borrower and provider PSBTs using the CLI commands described above.
- Use `h` when building the tapscript and keep `s` for CLOSE (borrower path).


Docker usage (step‑by‑step)

Use Docker for a reproducible setup with bitcoind (regtest), SSV, and rgb.

1) Build and start containers
- `make docker-up`
- `make docker-logs` to tail Core logs (Ctrl+C to stop tailing)

2) Run the CLOSE+REPAY demo skeleton
- `make demo-close`
- The script will:
  - Create vault/borrower/provider wallets in bitcoind
  - Derive keys via the ssv container
  - Build tapscript, import descriptor, and fund the vault
  - Pause to let you anchor RGB REPAY using `docker compose exec ssv rgb ...`
  - Finalize borrower witness with `ssv finalize`

3) CSV LIQUIDATION demo
- `make demo-liq` to run the provider path after CSV blocks elapse

Troubleshooting
- Ensure PSBTs include `witness_utxo` (use walletprocesspsbt if necessary).
- CSV spends require tx version ≥ 2 and input nSequence=CSV.
- Control block and signatures come from your signing wallet when preparing the Taproot script‑path spend.


Developer notes (modules and helpers)
- ssv.tapscript: tapscript builder for the two-branch policy; tapleaf hashing; disasm.
- ssv.policy: PolicyParams dataclass + validate() for input invariants.
- ssv.taproot: Taproot helpers (parse control block, compute output key, scriptPubKey build).
 - ssv.psbtio: PSBT load/write utilities (hex/base64 auto-detect), raw tx conversion, witness_utxo SPK extraction.
 - ssv.witness: witness stack builder with Branch enum (CLOSE / LIQUIDATE) and IF/ELSE selectors.
 - ssv.cli anchor-verify: lean check that a PSBT contains the expected TapRet anchor output at the given index.
  - ssv.cli opret-verify: lean check for an OP_RETURN output with expected data.
  - ssv.cli anchor-show: convenience listing of PSBT outputs.



Dockerized setup (reproducible)

If you prefer to run everything in containers (bitcoind + SSV + rgb CLI), use the provided Dockerfile and docker-compose.yml.

Quick start
- Build and start: `make docker-up`
- Tail bitcoind logs: `make docker-logs`
- Run CLOSE+REPAY demo (dockerized helpers):
  - `bash examples/close_repay_demo_docker.sh`
  - The script uses:
    - `docker compose exec bitcoin bitcoin-cli ...` for Core RPC calls, and
    - `docker compose exec ssv ssv ...` / `docker compose exec ssv python ...` for SSV and helpers.
- Run CSV LIQUIDATE demo (dockerized):
  - `bash examples/liq_demo_docker.sh`
- Stop containers: `make docker-down`

Notes
- The `ssv` container image includes Python deps and the `rgb` CLI pinned to v0.12 (installed via Cargo) so you can attach RGB anchors inside the same container.
- The `bitcoin` service uses regtest with txindex and default RPC auth (see docker-compose.yml). Adjust RPC options as needed.
- Example scripts still require manual signatures and a control block obtained from your signing wallet.


Development and tests
- Create a virtualenv and install dev extras:
  - `python3 -m venv .venv && source .venv/bin/activate`
  - `pip install -r requirements-dev.txt`  # installs editable package with dev deps
  - Alternatively: `pip install -e '.[dev]'`
  - Note: python-bitcointx is pinned (>=1.1.0) to ensure PSBT API availability for tests.
- Run tests: `make test` (or `pytest -q`)
- Editor (VS Code/Pylance): select the same virtualenv interpreter so pytest/coincurve are resolved and import warnings disappear.
- Some tests are skipped if optional deps are not installed (coincurve, python-bitcointx).

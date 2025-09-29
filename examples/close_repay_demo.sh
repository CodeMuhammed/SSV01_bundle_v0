#!/usr/bin/env bash
set -euo pipefail

# close_repay_demo.sh — skeleton (regtest)
# Prereqs: bitcoind -regtest, wallets: vault/borrower/provider

NET=regtest

echo "== Deriving keys (compressed + x-only) =="
python tools/derive_keys.py --all | tee .keys.json

VAULT_PUB=$(python - <<'PY'
import json
print([x for x in json.load(open('.keys.json')) if x['wallet']=='vault'][0]['pubkey_compressed'])
PY
)
BORR_X=$(python - <<'PY'
import json
print([x for x in json.load(open('.keys.json')) if x['wallet']=='borrower'][0]['xonly'])
PY
)
PROV_X=$(python - <<'PY'
import json
print([x for x in json.load(open('.keys.json')) if x['wallet']=='provider'][0]['xonly'])
PY
)

echo "VAULT_PUB=$VAULT_PUB"
echo "BORR_X=$BORR_X"
echo "PROV_X=$PROV_X"

echo "== Compute s and h =="
s=$(openssl rand -hex 32)
h=$(printf "%s" "$s" | xxd -r -p | openssl dgst -sha256 -binary | xxd -p -c 256)
echo "s=$s"; echo "h=$h"; echo "$h" > .h.txt; echo "$s" > .s.txt

CSV=144

echo "== Build tapscript =="
PYTHONPATH=src python -m ssv.cli build-tapscript --hash-h "$h" --borrower-pk "$BORR_X" --csv-blocks "$CSV" --provider-pk "$PROV_X" | tee .taps.out
grep '^tapscript_hex' .taps.out | awk '{print $3}' > tapscript.hex

echo "== Build Taproot descriptor and import to vault wallet =="
DESC="tr($VAULT_PUB,{and_v(v:sha256($h),pk($BORR_X)),and_v(v:older($CSV),pk($PROV_X))})"
DESC_CHK=$(bitcoin-cli -$NET -rpcwallet=vault getdescriptorinfo "$DESC" | jq -r .descriptor)
bitcoin-cli -$NET -rpcwallet=vault importdescriptors "[{\"desc\":\"$DESC_CHK\",\"active\":true,\"timestamp\":\"now\"}]"
VAULT_ADDR=$(bitcoin-cli -$NET -rpcwallet=vault deriveaddresses "$DESC_CHK" | jq -r '.[0]')
echo "Vault address: $VAULT_ADDR"

echo "== Fund and confirm vault =="
bitcoin-cli -$NET -rpcwallet=provider sendtoaddress "$VAULT_ADDR" 0.07000000
bitcoin-cli -$NET -rpcwallet=provider -generate 1 >/dev/null
UTXO=$(bitcoin-cli -$NET -rpcwallet=vault listunspent 0 | jq -r '.[0]')
TXID=$(jq -r .txid <<<"$UTXO"); VOUT=$(jq -r .vout <<<"$UTXO")

DEST=$(bitcoin-cli -$NET -rpcwallet=borrower getnewaddress "" bech32m)
AMT=0.06900000

echo "== Create CLOSE PSBT (RGB REPAY anchor to be attached) =="
PSBT=$(bitcoin-cli -$NET -rpcwallet=vault createpsbt "[{\"txid\":\"$TXID\",\"vout\":$VOUT}]" "[{\"$DEST\":$AMT}]" 0 true)
PSBT=$(bitcoin-cli -$NET -rpcwallet=vault walletprocesspsbt "$PSBT" false | jq -r .psbt)
echo "$PSBT" > close.psbt

cat <<EOF
== TODO: Attach RGB REPAY anchor ==
Use your RGB library/tooling to attach the REPAY transition (including preimage s) to close.psbt as a Tapret/Opret commitment.
Ensure the anchor remains with the CLOSE spending input.
EOF

read -p "Press Enter after RGB anchor is attached to close.psbt..." _

SIG_B_HEX="<BORROWER_SIG_HEX_HERE>"   # replace with real Schnorr signature
CTRL_HEX="<CONTROL_BLOCK_HEX_HERE>"  # replace with real control block

echo "== Finalize borrower witness =="
PYTHONPATH=src python -m ssv.cli finalize \
  --mode borrower \
  --psbt-in close.psbt --psbt-out close.final.psbt --tx-out close.final.tx \
  --sig "$SIG_B_HEX" --preimage "$s" \
  --hash-h "$h" --borrower-pk "$BORR_X" --csv-blocks "$CSV" --provider-pk "$PROV_X" \
  --control "$CTRL_HEX"

echo "Done. Inspect close.final.psbt / close.final.tx and broadcast as desired."


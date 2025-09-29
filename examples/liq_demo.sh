#!/usr/bin/env bash
set -euo pipefail

# liq_demo.sh — CSV liquidation skeleton (regtest)
# Prereqs: bitcoind -regtest, wallets: vault/provider loaded; vault UTXO funded earlier

NET=regtest
CSV=144

echo "== Find vault UTXO =="
UTXO=$(bitcoin-cli -$NET -rpcwallet=vault listunspent 0 | jq -r '.[0]')
if [ -z "${UTXO:-}" ] || [ "$UTXO" = "null" ]; then
  echo "No vault UTXO found in vault wallet. Fund the vault first." >&2
  exit 1
fi
TXID=$(jq -r .txid <<<"$UTXO"); VOUT=$(jq -r .vout <<<"$UTXO")

echo "== Mine blocks until CSV is satisfiable =="
bitcoin-cli -$NET -rpcwallet=provider -generate $((CSV+1)) >/dev/null

DEST=$(bitcoin-cli -$NET -rpcwallet=provider getnewaddress "" bech32m)
AMT=0.06800000

echo "== Create LIQUIDATE PSBT with nSequence=CSV =="
INPUTS="[{\"txid\":\"$TXID\",\"vout\":$VOUT,\"sequence\":$CSV}]"
OUTPUTS="[{\"$DEST\":$AMT}]"
PSBT=$(bitcoin-cli -$NET -rpcwallet=vault createpsbt "$INPUTS" "$OUTPUTS" 0)
PSBT=$(bitcoin-cli -$NET -rpcwallet=vault walletprocesspsbt "$PSBT" false | jq -r .psbt)
echo "$PSBT" > liq.psbt

echo "== Finalize provider witness (placeholders) =="
SIG_P_HEX="<PROVIDER_SIG_HEX_HERE>"
CTRL_HEX="<CONTROL_BLOCK_HEX_HERE>"

PYTHONPATH=src python -m ssv.cli finalize \
  --mode provider \
  --psbt-in liq.psbt --psbt-out liq.final.psbt --tx-out liq.final.tx \
  --sig "$SIG_P_HEX" \
  --hash-h "<h_hex>" --borrower-pk "<xonly_b>" --csv-blocks "$CSV" --provider-pk "<xonly_p>" \
  --control "$CTRL_HEX"

echo "Done. Inspect liq.final.psbt / liq.final.tx and broadcast as desired."


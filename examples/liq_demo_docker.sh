#!/usr/bin/env bash
set -euo pipefail

# liq_demo_docker.sh — CSV liquidation skeleton (docker compose)

BTC="docker compose exec -T bitcoin bitcoin-cli -regtest"
SSV="docker compose exec -T ssv"

CSV=144

echo "== Find vault UTXO =="
UTXO_JSON=$($BTC -rpcwallet=vault listunspent 0)
if [ -z "${UTXO_JSON:-}" ] || [ "$UTXO_JSON" = "null" ]; then
  echo "No vault UTXO found in vault wallet. Fund the vault first (see close_repay_demo_docker.sh)." >&2
  exit 1
fi
TXID=$(printf '%s' "$UTXO_JSON" | $SSV python - <<'PY'
import sys,json
arr=json.load(sys.stdin)
print(arr[0]["txid"]) 
PY
)
VOUT=$(printf '%s' "$UTXO_JSON" | $SSV python - <<'PY'
import sys,json
arr=json.load(sys.stdin)
print(arr[0]["vout"]) 
PY
)

echo "== Mine blocks until CSV is satisfiable =="
$BTC -rpcwallet=provider -generate $((CSV+1)) >/dev/null

DEST=$($BTC -rpcwallet=provider getnewaddress "" bech32m)
AMT=0.06800000

echo "== Create LIQUIDATE PSBT with nSequence=CSV =="
INPUTS="[{\"txid\":\"$TXID\",\"vout\":$VOUT,\"sequence\":$CSV}]"
OUTPUTS="[{\"$DEST\":$AMT}]"
PSBT=$($BTC -rpcwallet=vault createpsbt "$INPUTS" "$OUTPUTS" 0)
PSBT=$($BTC -rpcwallet=vault walletprocesspsbt "$PSBT" false | $SSV python - <<'PY'
import sys,json
print(json.load(sys.stdin)["psbt"]) 
PY
)
echo "$PSBT" > liq.psbt

echo "== Finalize provider witness (placeholders) =="
SIG_P_HEX="<PROVIDER_SIG_HEX_HERE>"
CTRL_HEX="<CONTROL_BLOCK_HEX_HERE>"

$SSV ssv finalize \
  --mode provider \
  --psbt-in liq.psbt --psbt-out liq.final.psbt --tx-out liq.final.tx \
  --sig "$SIG_P_HEX" \
  --hash-h "<h_hex>" --borrower-pk "<xonly_b>" --csv-blocks "$CSV" --provider-pk "<xonly_p>" \
  --control "$CTRL_HEX"

echo "Done. Inspect liq.final.psbt / liq.final.tx and broadcast as desired."
echo "Broadcast with: docker compose exec -T bitcoin bitcoin-cli -regtest sendrawtransaction $(cat liq.final.tx)"

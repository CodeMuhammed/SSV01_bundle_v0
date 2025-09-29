#!/usr/bin/env bash
set -euo pipefail

# close_repay_demo_docker.sh — skeleton using docker compose (bitcoind + ssv container)

BTC="docker compose exec -T bitcoin bitcoin-cli -regtest"
SSV="docker compose exec -T ssv"

echo "== Ensure containers are up =="
docker compose ps >/dev/null

echo "== Create wallets (idempotent) =="
$BTC createwallet vault || true
$BTC createwallet borrower || true
$BTC createwallet provider || true

echo "== Deriving keys (compressed + x-only) =="
$SSV python tools/derive_keys.py --all | tee .keys.json

VAULT_PUB=$($SSV python - <<'PY'
import json
print([x for x in json.load(open('.keys.json')) if x['wallet']=='vault'][0]['pubkey_compressed'])
PY
)
BORR_X=$($SSV python - <<'PY'
import json
print([x for x in json.load(open('.keys.json')) if x['wallet']=='borrower'][0]['xonly'])
PY
)
PROV_X=$($SSV python - <<'PY'
import json
print([x for x in json.load(open('.keys.json')) if x['wallet']=='provider'][0]['xonly'])
PY
)

echo "VAULT_PUB=$VAULT_PUB"
echo "BORR_X=$BORR_X"
echo "PROV_X=$PROV_X"

echo "== Compute s and h =="
read -r s h < <($SSV python - <<'PY'
import os,hashlib
s=os.urandom(32).hex()
h=hashlib.sha256(bytes.fromhex(s)).hexdigest()
print(s,h)
PY
)
echo "s=$s"; echo "h=$h"; echo "$h" > .h.txt; echo "$s" > .s.txt

CSV=144

echo "== Build tapscript =="
$SSV ssv build-tapscript --hash-h "$h" --borrower-pk "$BORR_X" --csv-blocks "$CSV" --provider-pk "$PROV_X" | tee .taps.out
TAPS_HEX=$($SSV python - <<'PY'
import re
s=open('.taps.out').read()
m=re.search(r'^tapscript_hex\s*=\s*([0-9a-fA-F]+)', s, re.M)
print(m.group(1) if m else '')
PY
)
echo "$TAPS_HEX" > tapscript.hex

echo "== Build Taproot descriptor and import to vault wallet =="
DESC="tr($VAULT_PUB,{and_v(v:sha256($h),pk($BORR_X)),and_v(v:older($CSV),pk($PROV_X))})"
DESC_CHK=$($BTC -rpcwallet=vault getdescriptorinfo "$DESC" | $SSV python - <<'PY'
import sys,json
print(json.load(sys.stdin)["descriptor"])
PY
)
$BTC -rpcwallet=vault importdescriptors "[{\"desc\":\"$DESC_CHK\",\"active\":true,\"timestamp\":\"now\"}]"
VAULT_ADDR=$($BTC -rpcwallet=vault deriveaddresses "$DESC_CHK" | $SSV python - <<'PY'
import sys,json
print(json.load(sys.stdin)[0])
PY
)
echo "Vault address: $VAULT_ADDR"

echo "== Fund and confirm vault =="
$BTC -rpcwallet=provider sendtoaddress "$VAULT_ADDR" 0.07000000
$BTC -rpcwallet=provider -generate 1 >/dev/null
UTXO_JSON=$($BTC -rpcwallet=vault listunspent 0)
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

DEST=$($BTC -rpcwallet=borrower getnewaddress "" bech32m)
AMT=0.06900000

echo "== Create CLOSE PSBT (RGB REPAY anchor to be attached) =="
PSBT=$($BTC -rpcwallet=vault createpsbt "[{\"txid\":\"$TXID\",\"vout\":$VOUT}]" "[{\"$DEST\":$AMT}]" 0 true)
PSBT=$($BTC -rpcwallet=vault walletprocesspsbt "$PSBT" false | $SSV python - <<'PY'
import sys,json
print(json.load(sys.stdin)["psbt"]) 
PY
)
echo "$PSBT" > close.psbt

cat <<EOF
== TODO: Attach RGB REPAY anchor ==
In another terminal or here using the container, use 'rgb' inside the ssv container to attach the REPAY transition as an anchor to close.psbt.

Examples (adapt to your contract and wallet setup):
  docker compose exec ssv rgb pay -n regtest <INVOICE> out.consig out.psbt --print
  # Or use 'rgb exec' with a YAML script and then 'rgb complete' on your signed PSBT

Ensure the REPAY transition verifies sha256(s)=h and pays provider ≥ principal+interest.
EOF

read -p "Press Enter after RGB anchor is attached to close.psbt..." _

SIG_B_HEX="<BORROWER_SIG_HEX_HERE>"   # replace with real Schnorr signature
CTRL_HEX="<CONTROL_BLOCK_HEX_HERE>"  # replace with real control block

echo "== Finalize borrower witness =="
$SSV ssv finalize \
  --mode borrower \
  --psbt-in close.psbt --psbt-out close.final.psbt --tx-out close.final.tx \
  --sig "$SIG_B_HEX" --preimage "$s" \
  --hash-h "$h" --borrower-pk "$BORR_X" --csv-blocks "$CSV" --provider-pk "$PROV_X" \
  --control "$CTRL_HEX"

echo "Done. Inspect close.final.psbt / close.final.tx and broadcast as desired."
echo "Broadcast with: docker compose exec -T bitcoin bitcoin-cli -regtest sendrawtransaction $(cat close.final.tx)"

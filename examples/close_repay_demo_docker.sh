#!/usr/bin/env bash
set -euo pipefail

# close_repay_demo_docker.sh — skeleton using single SSV container (embedded bitcoind)

BITCOIN_RPCUSER=${BITCOIN_RPCUSER:-ssv}
BITCOIN_RPCPASS=${BITCOIN_RPCPASS:-ssvpass}
BITCOIN_RPCPORT=${BITCOIN_RPCPORT:-18443}

BTC="docker compose exec -T ssv bitcoin-cli -regtest -rpcuser=$BITCOIN_RPCUSER -rpcpassword=$BITCOIN_RPCPASS -rpcconnect=127.0.0.1 -rpcport=$BITCOIN_RPCPORT"
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

# Save baseline outputs before RGB anchoring for auto-detection later
$SSV python - <<'PY'
import json
from bitcointx.core.psbt import PSBT
s=open('close.psbt').read().strip()
try:
    psbt=PSBT.from_base64(s)
except Exception:
    psbt=PSBT.deserialize(bytes.fromhex(s))
tx=getattr(psbt,'tx',None) or getattr(psbt,'unsigned_tx',None)
vout=list(getattr(tx,'vout',[]))
rows=[]
for i,out in enumerate(vout):
    spk=out.scriptPubKey.hex()
    val=int(getattr(out,'nValue',getattr(out,'value',0)))
    rows.append({'index':i,'value':val,'spk':spk})
open('.outs.pre.json','wt').write(json.dumps(rows))
PY

echo "== Attach RGB REPAY anchor (RGB v0.12 TapRet) =="
echo "The script will use the rgb v0.12 CLI inside the ssv container to update close.psbt with a TapRet anchor."
read -p "Enter RGB invoice (provider’s receiving invoice): " RGB_INVOICE

echo "-- rgb version --"
$SSV bash -lc 'rgb --version || true'

echo "-- running rgb transfer (tapret) --"
set +e
$SSV bash -lc \
  'rgb transfer -n regtest --invoice "$RGB_INVOICE" --method tapret --psbt close.psbt --consignment out.consig --psbt-out close.psbt'
RC=$?
set -e
if [[ $RC -ne 0 ]]; then
  echo "rgb transfer failed (exit=$RC). Please run your RGB tool manually to anchor TapRet into close.psbt, then continue." >&2
fi

echo "== Attempting to detect TapRet anchor output (diff vs baseline) =="
OUTS_JSON=$($SSV python - <<'PY'
import json, sys
from bitcointx.core.psbt import PSBT
try:
    s=open('close.psbt').read().strip()
    try:
        psbt=PSBT.from_base64(s)
    except Exception:
        psbt=PSBT.deserialize(bytes.fromhex(s))
    tx=getattr(psbt,'tx',None) or getattr(psbt,'unsigned_tx',None)
    vout=list(getattr(tx,'vout',[]))
    rows=[]
    for i,out in enumerate(vout):
        spk=out.scriptPubKey.hex()
        val=int(getattr(out,'nValue',getattr(out,'value',0)))
        rows.append({'index':i,'value':val,'spk':spk})
    # Attempt to diff vs baseline
    try:
        pre=json.load(open('.outs.pre.json'))
    except Exception:
        pre=None
    out={'post':rows,'pre':pre}
    print(json.dumps(out))
except Exception as e:
    print(json.dumps({'error':str(e)}))
PY
)

DEF_INDEX=""
DEF_SPK=""
DEF_VALUE=""
if [[ "$OUTS_JSON" == *"error"* || -z "$OUTS_JSON" ]]; then
  echo "Could not auto-detect outputs from PSBT; falling back to manual entry."
else
  echo "Outputs detected:" 
  echo "$OUTS_JSON" | $SSV python - <<'PY'
import sys, json
data=json.load(sys.stdin)
rows=data['post'] if isinstance(data,dict) and 'post' in data else data
for r in rows:
    print(f"  {r['index']}: value={r['value']} spk={r['spk']}")
PY
  # compute defaults: prefer new outputs vs baseline, then P2TR, else last
  DEF_INDEX=$($SSV python - <<'PY'
import sys,json
data=json.loads(sys.stdin.read())
post=data['post'] if isinstance(data,dict) and 'post' in data else data
pre=data.get('pre') if isinstance(data,dict) else None

def p2tr_idx(rows):
    return [r['index'] for r in rows if isinstance(r.get('spk'),str) and r['spk'].lower().startswith('5120')]

idx=None
if pre:
    # multiset of (spk,value) from pre
    from collections import Counter
    cpre=Counter((r['spk'].lower(), int(r['value'])) for r in pre)
    new=[r for r in post if cpre[(r['spk'].lower(), int(r['value']))] == 0]
    cand = [r['index'] for r in new]
    if not cand:
        cand = [r['index'] for r in post if (r['spk'].lower(), int(r['value'])) not in cpre]
    # filter p2tr if multiple
    if len(cand) > 1:
        cand = [i for i in cand if post[i]['spk'].lower().startswith('5120')]
    if cand:
        idx = max(cand)
if idx is None:
    p = p2tr_idx(post)
    idx = (max(p) if p else (len(post)-1 if post else 0))
print(idx)
PY
  <<< "$OUTS_JSON")
  DEF_SPK=$($SSV python - <<'PY'
import sys,json
data=json.loads(sys.stdin.read())
rows=data['post'] if isinstance(data,dict) and 'post' in data else data
idx=int(sys.argv[1]) if len(sys.argv)>1 else 0
print(rows[idx]['spk'])
PY
  "$DEF_INDEX" <<< "$OUTS_JSON")
  DEF_VALUE=$($SSV python - <<'PY'
import sys,json
data=json.loads(sys.stdin.read())
rows=data['post'] if isinstance(data,dict) and 'post' in data else data
idx=int(sys.argv[1]) if len(sys.argv)>1 else 0
print(rows[idx]['value'])
PY
  "$DEF_INDEX" <<< "$OUTS_JSON")
  echo "Defaulting to index=$DEF_INDEX value=$DEF_VALUE"
fi

read -p "Enter anchor output index [${DEF_INDEX}]: " ANCHOR_INDEX
ANCHOR_INDEX=${ANCHOR_INDEX:-$DEF_INDEX}
read -p "Enter anchor SPK hex (TapRet P2TR) [${DEF_SPK}]: " ANCHOR_SPK
ANCHOR_SPK=${ANCHOR_SPK:-$DEF_SPK}
read -p "Enter anchor value (sats) [${DEF_VALUE}]: " ANCHOR_VALUE
ANCHOR_VALUE=${ANCHOR_VALUE:-$DEF_VALUE}

echo "== Verify anchor output =="
$SSV ssv anchor-verify --psbt-in close.psbt --index "$ANCHOR_INDEX" --spk "$ANCHOR_SPK" --value "$ANCHOR_VALUE"

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
echo "Broadcast with: docker compose exec -T ssv bitcoin-cli -regtest -rpcuser=$BITCOIN_RPCUSER -rpcpassword=$BITCOIN_RPCPASS -rpcconnect=127.0.0.1 -rpcport=$BITCOIN_RPCPORT sendrawtransaction $(cat close.final.tx)"

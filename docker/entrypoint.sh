#!/usr/bin/env bash
set -euo pipefail

BITCOIN_DATA=${BITCOIN_DATA:-/data/bitcoin}
BITCOIN_RPCUSER=${BITCOIN_RPCUSER:-ssv}
BITCOIN_RPCPASS=${BITCOIN_RPCPASS:-ssvpass}
BITCOIN_RPCPORT=${BITCOIN_RPCPORT:-18443}
BITCOIN_P2PPORT=${BITCOIN_P2PPORT:-18444}
BITCOIN_ZMQ_BLOCK=${BITCOIN_ZMQ_BLOCK:-28332}
BITCOIN_ZMQ_TX=${BITCOIN_ZMQ_TX:-28333}

mkdir -p "$BITCOIN_DATA"

BITCOIN_ARGS=(
  -regtest
  -server
  -txindex=1
  -fallbackfee=0.0002
  -rpcuser="$BITCOIN_RPCUSER"
  -rpcpassword="$BITCOIN_RPCPASS"
  -rpcbind=0.0.0.0
  -rpcallowip=0.0.0.0/0
  -rpcport="$BITCOIN_RPCPORT"
  -port="$BITCOIN_P2PPORT"
  -zmqpubrawblock="tcp://0.0.0.0:${BITCOIN_ZMQ_BLOCK}"
  -zmqpubrawtx="tcp://0.0.0.0:${BITCOIN_ZMQ_TX}"
  -prune=0
  -keypool=100
)

echo "Starting bitcoind (regtest)…"
/usr/local/bin/bitcoind "${BITCOIN_ARGS[@]}" -printtoconsole=1 -datadir="$BITCOIN_DATA" &
BITCOIN_PID=$!

cleanup() {
  echo "Stopping bitcoind…"
  /usr/local/bin/bitcoin-cli \
    -regtest \
    -rpcuser="$BITCOIN_RPCUSER" \
    -rpcpassword="$BITCOIN_RPCPASS" \
    -rpcport="$BITCOIN_RPCPORT" \
    -rpcconnect=127.0.0.1 \
    -datadir="$BITCOIN_DATA" stop >/dev/null 2>&1 || true
  wait "$BITCOIN_PID" 2>/dev/null || true
}
trap cleanup EXIT

echo -n "Waiting for bitcoind to signal readiness"
for _ in {1..60}; do
  if /usr/local/bin/bitcoin-cli \
      -regtest \
      -rpcuser="$BITCOIN_RPCUSER" \
      -rpcpassword="$BITCOIN_RPCPASS" \
      -rpcport="$BITCOIN_RPCPORT" \
      -rpcconnect=127.0.0.1 \
      -datadir="$BITCOIN_DATA" getblockchaininfo >/dev/null 2>&1; then
    echo " — up"
    break
  fi
  echo -n "."
  sleep 1
done

echo "bitcoind ready (RPC user=$BITCOIN_RPCUSER, pass=$BITCOIN_RPCPASS, port=$BITCOIN_RPCPORT)"

if [ "$#" -gt 0 ]; then
  exec "$@"
else
  exec sleep infinity
fi

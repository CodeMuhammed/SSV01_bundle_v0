FROM python:3.11-slim

ARG BITCOIN_VERSION=27.0

ENV DEBIAN_FRONTEND=noninteractive \
    CARGO_HOME=/usr/local/cargo \
    RUSTUP_HOME=/usr/local/rustup \
    PATH=/usr/local/cargo/bin:/usr/local/bin:$PATH \
    BITCOIN_DATA=/data/bitcoin \
    BITCOIN_RPCUSER=ssv \
    BITCOIN_RPCPASS=ssvpass \
    BITCOIN_RPCPORT=18443 \
    BITCOIN_P2PPORT=18444 \
    BITCOIN_ZMQ_BLOCK=28332 \
    BITCOIN_ZMQ_TX=28333

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl git bash jq xxd openssl wget \
    build-essential pkg-config libffi-dev libssl-dev \
  && rm -rf /var/lib/apt/lists/*

# Install Bitcoin Core binaries (matching container architecture)
RUN set -eux; \
    arch="$(dpkg --print-architecture)"; \
    case "$arch" in \
      amd64) btc_arch="x86_64-linux-gnu";; \
      arm64) btc_arch="aarch64-linux-gnu";; \
      armhf) btc_arch="arm-linux-gnueabihf";; \
      *) echo "Unsupported architecture: $arch"; exit 1;; \
    esac; \
    url="https://bitcoincore.org/bin/bitcoin-core-${BITCOIN_VERSION}/bitcoin-${BITCOIN_VERSION}-${btc_arch}.tar.gz"; \
    wget -qO bitcoin.tgz "$url"; \
    tar -xzf bitcoin.tgz --strip-components=2 -C /usr/local/bin "bitcoin-${BITCOIN_VERSION}/bin/bitcoind" "bitcoin-${BITCOIN_VERSION}/bin/bitcoin-cli"; \
    rm -f bitcoin.tgz

# Install Rust toolchain and rgb CLI (pinned to v0.12)
RUN curl -sSf https://sh.rustup.rs | sh -s -- -y \
  && cargo install rgb --locked --version "^0.12"

WORKDIR /app
COPY . /app

# Python dependencies (editable install to make CLI available as `ssv`)
RUN python -m pip install -U pip setuptools wheel \
  && pip install -e . \
  && pip install coincurve

RUN chmod +x docker/entrypoint.sh && mkdir -p "$BITCOIN_DATA"

EXPOSE 18443 18444 28332 28333

ENTRYPOINT ["/app/docker/entrypoint.sh"]
CMD ["sleep", "infinity"]

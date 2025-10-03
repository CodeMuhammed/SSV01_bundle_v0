FROM python:3.11-slim

ENV DEBIAN_FRONTEND=noninteractive \
    CARGO_HOME=/usr/local/cargo \
    RUSTUP_HOME=/usr/local/rustup \
    PATH=/usr/local/cargo/bin:$PATH

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl git bash jq xxd openssl \
    build-essential pkg-config libffi-dev libssl-dev \
  && rm -rf /var/lib/apt/lists/*

# Install Rust toolchain and rgb CLI (pinned to v0.12)
RUN curl -sSf https://sh.rustup.rs | sh -s -- -y \
  && cargo install rgb --locked --version "^0.12"

WORKDIR /app
COPY . /app

# Python dependencies (editable install to make CLI available as `ssv`)
RUN python -m pip install -U pip setuptools wheel \
  && pip install -e . \
  && pip install coincurve

# Default to an interactive shell; use `docker compose exec ssv ...` to run commands
ENTRYPOINT ["/bin/bash"]

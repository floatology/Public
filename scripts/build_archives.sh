#!/usr/bin/env bash
# Full-history archive build for the tokens listed below, one at a time.
#
# SERIAL BY DESIGN. The RPC rate-limits globally rather than per query, so two
# bulk scans running together starve one of them — that is documented in
# src/rhc/rpc.py and it killed a 40-minute run anyway.
#
# Every step is resumable. token_archive.py stores scanned block RANGES, so a
# rerun after any interruption asks the node only for what is missing, and the
# STATUS file below records which stage each token reached.
set -u
cd "$(dirname "$0")/.."
STATUS=data/tokens/STATUS.md

note() {  # stage marker, flushed immediately so a killed run is still legible
  printf '%s  %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" >> "$STATUS"
  echo "[$(date -u +%H:%M:%S)] $*"
}

mkdir -p data/tokens
[ -f "$STATUS" ] || printf '# Archive build status\n\n' > "$STATUS"

build() {
  local name=$1 token=$2 pool=$3 proto=$4 q0=$5
  local flag=""; [ "$q0" = "1" ] && flag="--quote-is-token0"
  note "$name: transfers starting"
  .venv/bin/python scripts/token_archive.py --token "$token" --transfers \
    && note "$name: transfers DONE" || { note "$name: transfers FAILED"; return 1; }
  note "$name: swaps starting"
  .venv/bin/python scripts/token_archive.py --token "$token" --pool "$pool" \
    --protocol "$proto" $flag --swaps \
    && note "$name: swaps DONE" || { note "$name: swaps FAILED"; return 1; }
  note "$name: attributing"
  .venv/bin/python scripts/attribute_trades.py \
    --swaps "data/tokens/${token,,}/swaps.parquet" \
    --transfers "data/tokens/${token,,}/transfers.parquet" \
    --pool "$pool" --out "data/tokens/${token,,}/swaps_attributed.parquet" \
    && note "$name: attributed DONE" || { note "$name: attribution FAILED"; return 1; }
}

build WALLET 0x0339f5459FC690aC85F1782e15782A151b4A9E1b \
      0x9501a20bedb8bea0798fe5d4c411f5e270965d49 v3 0
build HH     0x6835dbF2D7D5852f84bF0a80DE00CAB3864F44b1 \
      0x34321f090a123d52473ae1a2473e8ed97dd9f770 v2 1
note "all builds finished"

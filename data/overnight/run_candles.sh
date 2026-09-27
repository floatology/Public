#!/usr/bin/env bash
# Resumable: skips pools already in data/chain/candles.jsonl
cd "$(dirname "$0")/../.."
exec .venv/bin/python scripts/gt_history.py candles

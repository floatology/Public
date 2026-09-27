#!/usr/bin/env bash
# Build every registered token except the six watchlist coins (those wait for
# step 9 of PLAN.md). Resumable: rerunning skips finished work.
cd "$(dirname "$0")/../.."
SYMS=$(python3 -c "
import json;r=json.load(open('data/tokens/tokens.json'))
six={'WALLET','HH','ORBIO','ASKR','AXON','ERHA'}
print(' '.join(sorted({e['symbol'] for e in r.values() if e['symbol'] not in six})))")
exec .venv/bin/python scripts/track_tokens.py build --only $SYMS

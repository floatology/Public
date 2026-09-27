#!/usr/bin/env bash
# Waits for batch 1 to finish, then: reprice, register U (PancakeSwap pool)
# and the batch-2 case-control coins, build them, reprice again. Every step is
# resumable, so a check-in can rerun this script safely.
cd "$(dirname "$0")/../.."
log() { echo "$(date -u +%FT%TZ) $*" >> data/overnight/LOG.md; }
while pgrep -f "scripts/track_tokens.py build" > /dev/null; do sleep 60; done
log "batch1 finished; repricing"
.venv/bin/python scripts/track_tokens.py reprice > data/overnight/reprice1.log 2>&1
B2=$(python3 -c "import json;d=json.load(open('data/overnight/batch2.json'));print(' '.join(d['cases']+d['controls']))")
.venv/bin/python scripts/track_tokens.py add U $B2 > data/overnight/add_batch2.log 2>&1
log "batch2 registered; building"
data/overnight/run_batch.sh > data/overnight/build_batch2.log 2>&1
.venv/bin/python scripts/track_tokens.py reprice > data/overnight/reprice2.log 2>&1
log "batch2 built and repriced"

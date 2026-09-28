#!/usr/bin/env bash
# Build U (now with its PancakeSwap pool) and the batch-2 case-control coins,
# reprice, then run the wallet-level backtest at 14 and 7 days. Resumable.
cd "$(dirname "$0")/../.."
log() { echo "$(date -u +%FT%TZ) $*" >> data/overnight/LOG.md; }
SYMS=$(python3 -c "
import json
r=json.load(open('data/tokens/tokens.json')); d=json.load(open('data/overnight/batch2.json'))
want=set(a.lower() for a in d['cases']+d['controls'])|{'0xce24439f2d9c6a2289f741120fe202248b666666'}
print(' '.join(sorted({e['symbol'] for t,e in r.items() if t in want and e.get('pools')})))")
log "batch2 build starting: $SYMS"
.venv/bin/python scripts/track_tokens.py build --only $SYMS > data/overnight/build_batch2.log 2>&1
.venv/bin/python scripts/track_tokens.py reprice > data/overnight/reprice2.log 2>&1
log "batch2 built and repriced; running wallet backtests"
.venv/bin/python scripts/wallet_signals_backtest.py --horizon 14 > data/overnight/wallet_signals_h14.txt 2>/dev/null
.venv/bin/python scripts/wallet_signals_backtest.py --horizon 7 > data/overnight/wallet_signals_h7.txt 2>/dev/null
log "wallet backtests done"

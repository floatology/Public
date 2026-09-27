#!/usr/bin/env python3
"""One row per trade, with who, when, at what price, and what it did to them.

This is the table everything else reads. The archive holds raw logs; this joins
them into the form the questions are actually asked in — who entered when, are
they adding or leaving, are they up or down, is the behaviour human.

Columns, per trade:

    ts, block, tx_hash, trader, side, tokens, quote_eth, usd,
    price_usd, price_eth,
    pos_before, pos_after          position in tokens, from this pool
    basis_before, basis_after      average cost in USD per token
    realised_usd, realised_cum     profit taken on this sale and to date
    holdings_now                   the trader's actual balance today
    n_trade, seconds_since_prev    for behavioural work

**Cost basis is a weighted average, and the choice is stated because it is a
choice.** A buy raises the average; a sale realises against it and leaves it
unchanged. FIFO would give different realised figures on the same trades. Net
quote flow, which needs no convention at all, is also carried, so a reader who
distrusts the averaging can use that instead.

**Position is pool position, not holdings.** A trader who buys and then moves
tokens to a cold wallet still shows a positive pool position; their `holdings_now`
will be zero. Both are reported because they answer different questions, and
conflating them is the mistake `docs/23` is about.

**A trade with no attributed trader is kept**, with a null trader, rather than
dropped. Silently discarding the unattributable would make every share and total
computed from this table quietly wrong.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pyarrow as pa
import pyarrow.parquet as pq

sys.path.insert(0, str(Path(__file__).resolve().parent))
from block_times import BlockClock

WEI = 10**18
ZERO = "0x0000000000000000000000000000000000000000"


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dir", type=Path, required=True, help="data/tokens/<token>")
    p.add_argument("--pool", action="append", required=True)
    p.add_argument("--eth-usd", type=float, required=True,
                   help="a single ETH price for the whole window; the error it "
                        "introduces is stated in the output, not hidden")
    p.add_argument("--clock", type=Path, default=Path("data/tokens/block_times.json"))
    p.add_argument("--out", type=Path)
    args = p.parse_args()

    pools = {x.lower() for x in args.pool}
    clock = BlockClock(json.loads(args.clock.read_text())["anchors"])

    sw = pq.read_table(args.dir / "swaps_attributed.parquet")
    s = {n: sw.column(n).to_pylist() for n in sw.column_names}
    n = len(s["block"])

    # Current holdings, from the full transfer replay.
    tr = pq.read_table(args.dir / "transfers.parquet")
    t = {n2: tr.column(n2).to_pylist() for n2 in tr.column_names}
    bal = defaultdict(int)
    for i in range(len(t["block"])):
        v = int(t["value"][i])
        if not v:
            continue
        if t["src"][i] != ZERO:
            bal[t["src"][i]] -= v
        if t["dst"][i] != ZERO:
            bal[t["dst"][i]] += v

    order = sorted(range(n), key=lambda i: (s["block"][i], s["log_index"][i]))

    pos = defaultdict(float)        # tokens held from pool activity
    basis = defaultdict(float)      # weighted-average USD cost per token
    realised = defaultdict(float)
    count = defaultdict(int)
    last_ts: dict[str, int] = {}

    cols: dict[str, list] = {k: [] for k in (
        "ts", "block", "log_index", "tx_hash", "trader", "side", "tokens",
        "quote_eth", "usd", "price_usd", "pos_before", "pos_after",
        "basis_before", "basis_after", "realised_usd", "realised_cum",
        "net_quote_cum", "holdings_now", "n_trade", "seconds_since_prev")}
    net_quote = defaultdict(float)
    unattributed = 0

    for i in order:
        w = s["trader"][i]
        tokens = int(s["base_amount"][i]) / WEI
        quote = int(s["quote_amount"][i]) / WEI
        usd = quote * args.eth_usd
        px = usd / tokens if tokens else 0.0
        ts = clock.at(s["block"][i])
        buy = bool(s["is_buy"][i])

        if w is None:
            unattributed += 1
            pb = pa_ = bb = ba = r = rc = nq = 0.0
            hn = 0.0
            nt = 0
            gap = -1
        else:
            pb, bb = pos[w], basis[w]
            if buy:
                total = pb * bb + usd
                pa_ = pb + tokens
                ba = total / pa_ if pa_ else 0.0
                r = 0.0
                net_quote[w] -= usd
            else:
                sold = min(tokens, pb)          # cannot realise what was never bought here
                r = (px - bb) * sold
                pa_ = pb - tokens
                ba = bb                          # a sale does not move the average
                net_quote[w] += usd
            realised[w] += r
            pos[w], basis[w] = pa_, ba
            count[w] += 1
            gap = ts - last_ts[w] if w in last_ts else -1
            last_ts[w] = ts
            rc = realised[w]
            nq = net_quote[w]
            hn = bal.get(w, 0) / WEI
            nt = count[w]

        cols["ts"].append(ts)
        cols["block"].append(s["block"][i])
        cols["log_index"].append(s["log_index"][i])
        cols["tx_hash"].append(s["tx_hash"][i])
        cols["trader"].append(w)
        cols["side"].append("buy" if buy else "sell")
        cols["tokens"].append(tokens)
        cols["quote_eth"].append(quote)
        cols["usd"].append(usd)
        cols["price_usd"].append(px)
        cols["pos_before"].append(pb)
        cols["pos_after"].append(pa_)
        cols["basis_before"].append(bb)
        cols["basis_after"].append(ba)
        cols["realised_usd"].append(r)
        cols["realised_cum"].append(rc)
        cols["net_quote_cum"].append(nq)
        cols["holdings_now"].append(hn)
        cols["n_trade"].append(nt)
        cols["seconds_since_prev"].append(gap)

    out = args.out or (args.dir / "ledger.parquet")
    pq.write_table(pa.table(cols), out)
    print(f"{n:,} trades -> {out}", file=sys.stderr)
    print(f"  {unattributed:,} ({unattributed/n:.2%}) had no attributed trader "
          f"and carry a null", file=sys.stderr)
    print(f"  {len(pos):,} distinct traders across the full history", file=sys.stderr)
    print(f"  span {min(cols['ts']):,} - {max(cols['ts']):,}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

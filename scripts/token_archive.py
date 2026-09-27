#!/usr/bin/env python3
"""Keep a resumable on-disk archive of one token's chain activity.

Rescanning 64 million blocks to learn what happened since yesterday is the
difference between a six-minute wait and a six-second one, and on a token this
project revisits it is the whole cost. The archive stores what it has already
read and, on the next run, asks the node only for the gap.

Layout, one directory per token:

    data/tokens/<token>/
        meta.json          scanned ranges, counts, when
        transfers.parquet  every ERC-20 Transfer
        swaps.parquet      every pool Swap, with resolved senders where done

**The checkpoint is a block range, not a block number.** A single "last block"
cannot tell a gap from a fresh start, and appending a second range that does not
touch the first would leave an invisible hole in the middle of the history. The
ranges are stored, merged when they touch, and a scan that would leave a gap is
refused rather than silently written.

**Scans commit in segments.** A single flush at the end of a ten-minute scan
means a rate limit at 10% discards all of it, which is what happened on the
first full WALLET build. Each `--segment` blocks is written, and its range
recorded, before the next begins, so an interruption costs one segment and a
rerun resumes from the stored ranges.

**Reorg margin.** The last `--reorg-margin` blocks of a previous scan are read
again, because a log read at the chain tip can be reorganised out from under
the archive. Re-read rows replace rather than duplicate: rows are keyed on
(block, log_index), which is unique per log.

**Transfers carry their transaction hash**, which is what lets a swap be
attributed to the address that actually ended up with the tokens: replay the
transfers of that one transaction and the trader is whoever's balance moved.
That costs no RPC calls at all, which is what makes full-history attribution
affordable where per-swap `tx.from` resolution is not.

**Sender resolution is stored per swap and never recomputed.** It costs one RPC
call each — the expensive part of the whole pipeline — so a swap whose sender is
already known is skipped on every later run.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pyarrow as pa
import pyarrow.parquet as pq

from rhc.features import decode_v2_swaps, decode_v3_swaps
from rhc.rpc import TOPIC_TRANSFER, TOPIC_V2_SWAP, TOPIC_V3_SWAP, Rpc, RpcError

REORG_MARGIN = 5_000


def merge(ranges: list[list[int]]) -> list[list[int]]:
    """Collapse touching or overlapping ranges; keeps gaps visible."""
    if not ranges:
        return []
    out = [list(r) for r in sorted(ranges)]
    merged = [out[0]]
    for lo, hi in out[1:]:
        if lo <= merged[-1][1] + 1:
            merged[-1][1] = max(merged[-1][1], hi)
        else:
            merged.append([lo, hi])
    return merged


def covered_to(ranges: list[list[int]], start: int) -> int | None:
    """The highest block covered by a contiguous run containing `start`."""
    for lo, hi in ranges:
        if lo <= start <= hi:
            return hi
    return None


@dataclass
class Archive:
    root: Path
    token: str

    @property
    def dir(self) -> Path:
        return self.root / self.token.lower()

    @property
    def meta_path(self) -> Path:
        return self.dir / "meta.json"

    def meta(self) -> dict:
        if self.meta_path.exists():
            return json.loads(self.meta_path.read_text())
        return {"token": self.token.lower(), "transfers": {"ranges": []},
                "swaps": {"ranges": [], "pool": None, "protocol": None}}

    def write_meta(self, meta: dict) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        meta["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        self.meta_path.write_text(json.dumps(meta, indent=1))

    def read(self, name: str) -> dict[str, list]:
        path = self.dir / f"{name}.parquet"
        if not path.exists():
            return {}
        t = pq.read_table(path)
        return {n: t.column(n).to_pylist() for n in t.column_names}

    def write(self, name: str, rows: dict[str, list]) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        pq.write_table(pa.table(rows), self.dir / f"{name}.parquet")


def dedupe(old: dict[str, list], new: dict[str, list]) -> dict[str, list]:
    """Union of two row sets keyed on (block, log_index); `new` wins a tie.

    A re-read of the reorg margin returns rows the archive already holds. Keying
    on the log's own coordinates makes the re-read idempotent, and lets a
    reorganised block legitimately replace what was there before.
    """
    cols = list(new.keys()) if new else list(old.keys())
    table: dict[tuple[int, int], dict] = {}
    for src in (old, new):
        if not src:
            continue
        for i in range(len(src["block"])):
            table[(src["block"][i], src["log_index"][i])] = {
                c: src[c][i] for c in cols if c in src
            }
    out: dict[str, list] = {c: [] for c in cols}
    for key in sorted(table):
        row = table[key]
        for c in cols:
            out[c].append(row.get(c))
    return out


MAX_LOGS_PER_SEGMENT = 600_000   # busiest normal token seen: WALLET, 176k in one segment


class TooHeavy(RuntimeError):
    """A token whose log volume would stall a batch; the caller skips it."""


def scan(rpc: Rpc, *, topic: str, address: str, lo: int, hi: int, label: str) -> list[dict]:
    started = time.time()

    def progress(block: int, span: int, yielded: int) -> None:
        if yielded > MAX_LOGS_PER_SEGMENT:
            raise TooHeavy(f"{yielded:,} logs by block {block:,}")
        done = (block - lo) / max(1, hi - lo)
        print(f"  {label} {done:6.1%}  block {block:,}  span {span:,}  "
              f"logs {yielded:,}  {time.time()-started:.0f}s", file=sys.stderr, flush=True)

    return list(rpc.iter_logs(from_block=lo, to_block=hi, topics=[[topic]],
                              address=address, initial_span=100_000,
                              on_progress=progress))


def collect(rpc: Rpc, kind: str, args, lo: int, hi: int) -> dict[str, list]:
    """Read one segment's logs and shape them into the archive's columns."""
    if kind == "transfers":
        logs = scan(rpc, topic=TOPIC_TRANSFER, address=args.token,
                    lo=lo, hi=hi, label="tr")
        rows = {"block": [], "log_index": [], "tx_hash": [],
                "src": [], "dst": [], "value": []}
        for lg in logs:
            t = lg.get("topics") or []
            if len(t) < 3:
                continue
            rows["block"].append(int(lg["blockNumber"], 16))
            rows["log_index"].append(int(lg.get("logIndex", "0x0"), 16))
            # tx_hash is what joins a transfer to the swap that caused it,
            # which is how a trade is attributed to the address that ended up
            # with the tokens rather than to a router.
            rows["tx_hash"].append(lg.get("transactionHash"))
            rows["src"].append("0x" + t[1][-40:])
            rows["dst"].append("0x" + t[2][-40:])
            rows["value"].append(str(int(lg.get("data") or "0x0", 16)))
        return rows

    topic = TOPIC_V2_SWAP if args.protocol == "v2" else TOPIC_V3_SWAP
    decode = decode_v2_swaps if args.protocol == "v2" else decode_v3_swaps
    logs = scan(rpc, topic=topic, address=args.pool, lo=lo, hi=hi, label="sw")
    tx_of = {(int(lg["blockNumber"], 16), int(lg.get("logIndex", "0x0"), 16)):
             lg["transactionHash"] for lg in logs}
    trades = decode(logs, quote_is_token0=args.quote_is_token0)
    rows = {"block": [], "log_index": [], "recipient": [], "sender": [],
            "tx_hash": [], "is_buy": [], "quote_amount": [], "base_amount": []}
    for t in trades:
        rows["block"].append(t.block)
        rows["log_index"].append(t.log_index)
        rows["recipient"].append(t.wallet)
        rows["sender"].append(None)   # filled by --resolve-senders
        rows["tx_hash"].append(tx_of.get((t.block, t.log_index)))
        rows["is_buy"].append(t.is_buy)
        rows["quote_amount"].append(str(t.quote_amount))
        rows["base_amount"].append(str(t.base_amount))
    return rows


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--token", required=True)
    p.add_argument("--pool", help="required for --swaps")
    p.add_argument("--protocol", choices=("v2", "v3"), default="v3")
    p.add_argument("--quote-is-token0", action="store_true")
    p.add_argument("--from-block", type=int, default=1)
    p.add_argument("--root", type=Path, default=Path("data/tokens"))
    p.add_argument("--transfers", action="store_true")
    p.add_argument("--swaps", action="store_true")
    p.add_argument("--resolve-senders", type=int, default=0,
                   help="resolve tx.from for up to N swaps that lack it, newest "
                        "first. One RPC call each; already-resolved swaps are free.")
    p.add_argument("--reorg-margin", type=int, default=REORG_MARGIN)
    p.add_argument("--segment", type=int, default=8_000_000,
                   help="commit to disk every this many blocks, so an "
                        "interrupted scan keeps what it already read")
    p.add_argument("--rescan", action="store_true", help="discard and start over")
    args = p.parse_args()

    if args.swaps and not args.pool:
        print("--swaps needs --pool", file=sys.stderr)
        return 2
    if not (args.transfers or args.swaps):
        args.transfers = args.swaps = bool(args.pool)
        if not args.transfers:
            args.transfers = True

    arc = Archive(args.root, args.token)
    meta = arc.meta() if not args.rescan else {
        "token": args.token.lower(), "transfers": {"ranges": []},
        "swaps": {"ranges": [], "pool": None, "protocol": None}}

    # A pool or protocol change invalidates the stored swaps entirely.
    if args.swaps and meta["swaps"]["ranges"]:
        if (meta["swaps"].get("pool") or "").lower() != args.pool.lower() \
                or meta["swaps"].get("protocol") != args.protocol:
            print("pool/protocol changed; discarding cached swaps", file=sys.stderr)
            meta["swaps"] = {"ranges": [], "pool": None, "protocol": None}

    with Rpc() as rpc:
        head = rpc.block_number()
        print(f"head {head:,}", file=sys.stderr, flush=True)

        for kind, want in (("transfers", args.transfers), ("swaps", args.swaps)):
            if not want:
                continue
            ranges = [list(r) for r in meta[kind]["ranges"]]
            have_to = covered_to(ranges, args.from_block)
            if have_to is None:
                lo = args.from_block
            else:
                lo = max(args.from_block, have_to - args.reorg_margin + 1)
            if lo > head:
                print(f"{kind}: already current to {have_to:,}", file=sys.stderr)
                continue
            gap = have_to is not None and lo > have_to + 1
            if gap:
                print(f"{kind}: refusing a scan that would leave a hole "
                      f"({have_to:,} -> {lo:,})", file=sys.stderr)
                return 1
            print(f"{kind}: scanning {lo:,}-{head:,} "
                  f"({'resuming' if have_to else 'fresh'})", file=sys.stderr, flush=True)

            seg_lo = lo
            while seg_lo <= head:
                hi = min(seg_lo + args.segment - 1, head)
                rows = collect(rpc, kind, args, seg_lo, hi)
                merged = dedupe(arc.read(kind), rows)
                arc.write(kind, merged)
                ranges = merge(ranges + [[seg_lo, hi]])
                meta[kind]["ranges"] = ranges
                meta[kind]["rows"] = len(merged["block"])
                if kind == "swaps":
                    meta[kind]["pool"] = args.pool.lower()
                    meta[kind]["protocol"] = args.protocol
                arc.write_meta(meta)
                print(f"{kind}: committed {seg_lo:,}-{hi:,}  "
                      f"+{len(rows['block']):,} rows, {len(merged['block']):,} total",
                      file=sys.stderr, flush=True)
                seg_lo = hi + 1

    # -- sender resolution, newest first, skipping what is already known -------
    if args.resolve_senders:
        rows = arc.read("swaps")
        if rows:
            todo = [i for i in range(len(rows["block"]))
                    if not rows["sender"][i] and rows["tx_hash"][i]]
            todo.sort(key=lambda i: rows["block"][i], reverse=True)
            todo = todo[:args.resolve_senders]
            known = sum(1 for s in rows["sender"] if s)
            print(f"senders: {known:,} known, {len(todo):,} to resolve now",
                  file=sys.stderr, flush=True)
            done = failed = 0
            with Rpc(min_interval=0.2) as rpc:
                for pos, i in enumerate(todo):
                    try:
                        tx = rpc.call("eth_getTransactionByHash", [rows["tx_hash"][i]])
                    except RpcError:
                        failed += 1
                        continue
                    if not tx:
                        failed += 1
                        continue
                    rows["sender"][i] = tx["from"].lower()
                    done += 1
                    if pos and pos % 1000 == 0:
                        arc.write("swaps", rows)   # checkpoint; a kill loses ~1000
                        print(f"  {pos:,}/{len(todo):,} ({failed:,} failed)",
                              file=sys.stderr, flush=True)
            arc.write("swaps", rows)
            meta["swaps"]["senders_known"] = sum(1 for s in rows["sender"] if s)
            arc.write_meta(meta)
            print(f"senders: resolved {done:,}, {failed:,} failed, "
                  f"{meta['swaps']['senders_known']:,} known in total", file=sys.stderr)

    print(json.dumps(arc.meta(), indent=1))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except TooHeavy as exc:
        print(f"TOO_HEAVY: {exc}", file=sys.stderr)
        raise SystemExit(3)

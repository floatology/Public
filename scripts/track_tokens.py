#!/usr/bin/env python3
"""Register tokens and build their full-history forensic archives, all pools.

Two commands:

    track_tokens.py add ORBIO ASKR ...      # resolve and register
    track_tokens.py build [--only ORBIO]    # scan, attribute, ledger

**Every pool, not the main one.** ORBIO trades in 22 pools, one of them quoted
in a stock token, and ASKR across two DEXes. A single-pool archive would miss
most of its trading. `add` registers every pool with at least `--min-liq` of
liquidity on a DEX whose Swap event this project can decode, and records the
ones it had to skip and why.

**Each pool has its own checkpoint.** Pools are scanned into
`data/tokens/<token>/pools/<key>.parquet` with their own scanned block ranges in
`pools.json`, so adding a pool later scans only that pool, and an interrupted
build resumes pool by pool. `swaps.parquet` is then rebuilt as the union, with
a `pool` column, which is what attribution and the ledger read.

**Quote assets are priced per pool.** A pool's quote may be ETH, WETH, USDG or a
stock token. Each pool's quote is priced in USD from DexScreener at build time
(base price in USD over base price in quote), with its decimals read from the
chain. That is a present-day price applied to history, the same approximation
already made for ETH, and it is recorded so the report can say so.

**V4 pools live in one contract.** Their swaps are read from the PoolManager
filtered on the PoolId, and for attribution the PoolManager is the pool: V4
token transfers go to and from it, never to a per-pool address.

Serial by design: the node rate-limits globally (src/rhc/rpc.py). Progress is
appended to data/tokens/STATUS.md so an interrupted build says where it was.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import pyarrow as pa
import pyarrow.parquet as pq

from rhc.dexscreener import DexScreener
from rhc.features import decode_v2_swaps, decode_v3_swaps, decode_v4_swaps
from rhc.rpc import (TOPIC_PCS_V3_SWAP, TOPIC_V2_SWAP, TOPIC_V3_SWAP, TOPIC_V4_SWAP,
                     V4_POOL_MANAGER, Rpc, RpcError)
from token_archive import covered_to, dedupe, merge

REG = ROOT / "data/tokens/tokens.json"
STATUS = ROOT / "data/tokens/STATUS.md"
PY = str(ROOT / ".venv/bin/python")
ZERO = "0x0000000000000000000000000000000000000000"
REORG = 5_000
SEGMENT = 8_000_000


def note(msg: str) -> None:
    STATUS.parent.mkdir(parents=True, exist_ok=True)
    if not STATUS.exists():
        STATUS.write_text("# Archive build status\n\n")
    with STATUS.open("a") as f:
        f.write(f"{dt.datetime.utcnow():%Y-%m-%dT%H:%M:%SZ}  {msg}\n")
    print(f"[{dt.datetime.utcnow():%H:%M:%S}] {msg}", flush=True)


def load_reg() -> dict:
    return json.loads(REG.read_text()) if REG.exists() else {}


def save_reg(reg: dict) -> None:
    REG.parent.mkdir(parents=True, exist_ok=True)
    REG.write_text(json.dumps(reg, indent=1))


def decimals(rpc: Rpc, token: str) -> int:
    if token.lower() == ZERO:
        return 18
    raw = rpc.call("eth_call", [{"to": token, "data": "0x313ce567"}, "latest"])
    return int(raw, 16)


def kind_of(pair: dict) -> str | None:
    labels = [x.lower() for x in (pair.get("labels") or [])]
    dex = (pair.get("dexId") or "").lower()
    if "v4" in labels:
        return "v4"
    if "v3" in labels and dex.startswith("pancakeswap"):
        return "pcs3"
    if "v3" in labels:
        return "v3"          # Uniswap and CL forks; verified by a probe below
    if "v2" in labels or dex in ("uniswap",):
        return "v2" if "v3" not in labels else "v3"
    return None


def cmd_add(args) -> int:
    reg = load_reg()
    ds = DexScreener()
    with Rpc() as rpc:
        head = rpc.block_number()
        for q in args.symbols:
            r = ds.get(f"/latest/dex/search?q={q}")
            pairs = [p for p in r.get("pairs") or []
                     if p.get("chainId") == "robinhood"
                     and (p["baseToken"]["symbol"].upper() == q.upper()
                          or p["baseToken"]["address"].lower() == q.lower())]
            if not pairs:
                print(f"{q}: no Robinhood Chain pairs found")
                continue
            # Tickers are unpoliced and liquidity is forgeable: a lookalike can
            # seed a pool with its own tokens and a dust of ETH, and DexScreener
            # values that at millions. The first version of this picked the
            # deepest pair and chose "Ambire Wallet" ($4.59M of liquidity, $0 of
            # volume) over the real WALLET. So: a token already archived here
            # wins; otherwise the one with the most real 24h volume.
            by_addr: dict[str, float] = {}
            for p in pairs:
                a = p["baseToken"]["address"].lower()
                by_addr[a] = by_addr.get(a, 0) + ((p.get("volume") or {}).get("h24") or 0)
            archived = [a for a in by_addr if (ROOT / "data/tokens" / a).exists()]
            token = archived[0] if archived else max(by_addr, key=by_addr.get)
            for a, v in by_addr.items():
                if a != token:
                    print(f"   {q}: rejected lookalike {a} (24h volume ${v:,.0f})")
            pairs.sort(key=lambda p: -((p.get("liquidity") or {}).get("usd") or 0))
            pairs = [p for p in pairs if p["baseToken"]["address"].lower() == token]
            # Tokenized stocks and stablecoins are not what this studies, and
            # a stock token's price follows its share, not on-chain flow.
            nm = pairs[0]["baseToken"].get("name") or ""
            if nm.strip().lower().endswith("robinhood token") or args.skip_symbols and \
                    pairs[0]["baseToken"]["symbol"].upper() in args.skip_symbols:
                print(f"{q}: skipped ({nm})")
                continue
            entry = reg.get(token, {"symbol": pairs[0]["baseToken"]["symbol"],
                                    "name": pairs[0]["baseToken"]["name"], "pools": {}})
            skipped = []
            entry["decimals"] = decimals(rpc, token)
            deepest = pairs[0]["pairAddress"].lower()
            for p in pairs:
                liq = (p.get("liquidity") or {}).get("usd") or 0
                # The deepest pool is always kept, however shallow: a small
                # token's only market is still its market.
                if liq < args.min_liq and p["pairAddress"].lower() != deepest:
                    continue
                k = kind_of(p)
                key = p["pairAddress"].lower()
                if key in entry["pools"]:
                    entry["pools"][key]["liq_at_add"] = liq
                    continue
                if not k:
                    skipped.append((key, p.get("dexId"), p.get("labels"), liq, "unknown pool type"))
                    continue
                quote = p["quoteToken"]["address"].lower()
                q0 = int(quote, 16) < int(token, 16)
                pool = {"kind": k, "dex": p.get("dexId"), "quote": quote,
                        "quote_symbol": p["quoteToken"]["symbol"],
                        "quote_is_token0": q0, "quote_decimals": decimals(rpc, quote),
                        "liq_at_add": liq, "created_ms": p.get("pairCreatedAt")}
                # Probe: a pool whose logs this decoder cannot see is skipped
                # and recorded, not silently archived as empty.
                if k in ("v2", "v3", "pcs3"):
                    topic = {"v2": TOPIC_V2_SWAP, "v3": TOPIC_V3_SWAP, "pcs3": TOPIC_PCS_V3_SWAP}[k]
                    got = rpc.get_logs(from_block=head - 400_000, to_block=head,
                                       topics=[[topic]], address=key)
                    txns = sum(((p.get("txns") or {}).get("h24") or {}).values())
                    if not got and txns:
                        skipped.append((key, p.get("dexId"), p.get("labels"), liq,
                                        f"{k} Swap topic absent despite {txns} txns/24h"))
                        continue
                entry["pools"][key] = pool
            entry["skipped"] = [{"pool": a, "dex": b, "labels": c, "liq": d, "why": e}
                                for a, b, c, d, e in skipped]
            reg[token] = entry
            cov = sum(v["liq_at_add"] for v in entry["pools"].values())
            tot = sum((p.get("liquidity") or {}).get("usd") or 0 for p in pairs)
            print(f"{entry['symbol']} {token}: {len(entry['pools'])} pools covering "
                  f"${cov:,.0f} of ${tot:,.0f} liquidity ({cov/max(1,tot):.0%}); "
                  f"skipped {len(skipped)}")
            for s in skipped:
                print(f"   skipped {s[0][:14]} {s[1]} {s[2]} ${s[3]:,.0f}: {s[4]}")
    save_reg(reg)
    return 0


def scan_pool(rpc: Rpc, key: str, pool: dict, lo: int, hi: int) -> dict[str, list]:
    if pool["kind"] == "v4":
        address, topics = V4_POOL_MANAGER, [[TOPIC_V4_SWAP], [key]]
        decode = decode_v4_swaps
    else:
        address = key
        topics = [[{"v2": TOPIC_V2_SWAP, "v3": TOPIC_V3_SWAP,
                    "pcs3": TOPIC_PCS_V3_SWAP}[pool["kind"]]]]
        decode = decode_v2_swaps if pool["kind"] == "v2" else decode_v3_swaps
    started = time.time()

    def progress(block: int, span: int, n: int) -> None:
        print(f"    {key[:10]} {(block-lo)/max(1,hi-lo):6.1%} block {block:,} "
              f"logs {n:,} {time.time()-started:.0f}s", flush=True)

    logs = list(rpc.iter_logs(from_block=lo, to_block=hi, topics=topics, address=address,
                              initial_span=100_000, on_progress=progress))
    tx_of = {(int(l["blockNumber"], 16), int(l.get("logIndex", "0x0"), 16)):
             l["transactionHash"] for l in logs}
    rows = {"block": [], "log_index": [], "pool": [], "recipient": [], "sender": [],
            "tx_hash": [], "is_buy": [], "quote_amount": [], "base_amount": []}
    for t in decode(logs, quote_is_token0=pool["quote_is_token0"]):
        rows["block"].append(t.block); rows["log_index"].append(t.log_index)
        rows["pool"].append(key); rows["recipient"].append(t.wallet)
        rows["sender"].append(None)
        rows["tx_hash"].append(tx_of.get((t.block, t.log_index)))
        rows["is_buy"].append(t.is_buy)
        rows["quote_amount"].append(str(t.quote_amount))
        rows["base_amount"].append(str(t.base_amount))
    return rows


def read(path: Path) -> dict[str, list]:
    if not path.exists():
        return {}
    t = pq.read_table(path)
    return {n: t.column(n).to_pylist() for n in t.column_names}


def migrate_single_pool(tdir: Path, token: str, reg_entry: dict) -> None:
    """Carry an archive built before multi-pool support into the per-pool layout."""
    old = tdir / "swaps.parquet"
    pj = tdir / "pools.json"
    meta = tdir / "meta.json"
    if pj.exists() or not old.exists() or not meta.exists():
        return
    m = json.loads(meta.read_text())
    key = (m.get("swaps") or {}).get("pool")
    if not key or key not in reg_entry["pools"]:
        return
    rows = read(old)
    rows["pool"] = [key] * len(rows["block"])
    (tdir / "pools").mkdir(exist_ok=True)
    pq.write_table(pa.table(rows), tdir / "pools" / f"{key}.parquet")
    pj.write_text(json.dumps({key: {"ranges": m["swaps"]["ranges"]}}, indent=1))
    note(f"{reg_entry['symbol']}: migrated existing single-pool archive for {key[:10]}")


def first_transfer_block(tdir: Path) -> int | None:
    t = read(tdir / "transfers.parquet")
    return min(t["block"]) if t.get("block") else None


MAX_TRANSFERS = 2_000_000


def estimate_transfers(rpc: Rpc, token: str, head: int) -> tuple[int, int]:
    """Projected lifetime Transfer count, from density near the head.

    Some tokens emit several transfers per swap (reflection and tax mechanics,
    or bot churn). musebook ran at 2.7 per block, which projects to ~26 million
    over its life and would have stalled an overnight batch for hours. The
    density is measured on the last 20,000 blocks and projected back to the
    token's first transfer, found by a coarse search, so the check costs a
    handful of calls.
    """
    from rhc.rpc import TOPIC_TRANSFER
    try:
        recent = len(rpc.get_logs(from_block=head - 20_000, to_block=head,
                                  topics=[[TOPIC_TRANSFER]], address=token))
    except RpcError:
        recent = 10_000          # at or over the node's cap: dense
    lo, hi = 1, head
    for _ in range(14):          # binary search for any activity, coarse
        mid = (lo + hi) // 2
        try:
            got = rpc.get_logs(from_block=lo, to_block=mid, topics=[[TOPIC_TRANSFER]],
                               address=token)
        except RpcError:
            got = [1]
        if got:
            hi = mid
        else:
            lo = mid + 1
    life = head - lo
    return int(recent / 20_000 * life), lo


def build_token(token: str, entry: dict, eth_usd: float) -> bool:
    sym = entry["symbol"]
    tdir = ROOT / "data/tokens" / token
    if entry.get("skipped_heavy") and not entry.get("force"):
        note(f"{sym}: skipped (too heavy: {entry['skipped_heavy']})")
        return True
    note(f"{sym}: transfers starting")
    r = subprocess.run([PY, str(ROOT / "scripts/token_archive.py"), "--token", token,
                        "--transfers"], cwd=ROOT)
    if r.returncode == 3:
        # More than 600k transfer logs in one 8M-block segment. Projections from
        # a sample underestimated WALLET threefold, because launches are far
        # denser than later trading, so the cap is enforced during the scan.
        entry["skipped_heavy"] = "over 600k transfers in one segment"
        note(f"{sym}: SKIPPED — over 600k transfers in one segment; set force=true to build")
        return True
    if r.returncode:
        note(f"{sym}: transfers FAILED — rerun build to resume"); return False
    note(f"{sym}: transfers DONE")
    migrate_single_pool(tdir, token, entry)

    start = first_transfer_block(tdir) or 1
    pj = tdir / "pools.json"
    pmeta = json.loads(pj.read_text()) if pj.exists() else {}
    (tdir / "pools").mkdir(exist_ok=True)
    with Rpc() as rpc:
        head = rpc.block_number()
        for key, pool in entry["pools"].items():
            ranges = [list(x) for x in pmeta.get(key, {}).get("ranges", [])]
            have = covered_to(ranges, start)
            lo = start if have is None else max(start, have - REORG + 1)
            path = tdir / "pools" / f"{key}.parquet"
            note(f"{sym}: pool {key[:10]} ({pool['kind']}/{pool['quote_symbol']}) "
                 f"{'resuming' if have else 'fresh'} from {lo:,}")
            seg = lo
            while seg <= head:
                hi = min(seg + SEGMENT - 1, head)
                try:
                    rows = scan_pool(rpc, key, pool, seg, hi)
                except RpcError as e:
                    note(f"{sym}: pool {key[:10]} FAILED at {seg:,}: {e} — rerun to resume")
                    pj.write_text(json.dumps(pmeta, indent=1)); return False
                merged = dedupe(read(path), rows)
                if merged:
                    pq.write_table(pa.table(merged), path)
                ranges = merge(ranges + [[seg, hi]])
                pmeta[key] = {"ranges": ranges, "rows": len(merged.get("block", []))}
                pj.write_text(json.dumps(pmeta, indent=1))
                seg = hi + 1
            note(f"{sym}: pool {key[:10]} DONE, {pmeta[key]['rows']:,} swaps")

    # Union of every pool, which is what attribution and the ledger read.
    parts = [read(tdir / "pools" / f"{k}.parquet") for k in entry["pools"]]
    parts = [p for p in parts if p]
    cols = ["block", "log_index", "pool", "recipient", "sender", "tx_hash", "is_buy",
            "quote_amount", "base_amount"]
    union = {c: [] for c in cols}
    for p in parts:
        for c in cols:
            union[c].extend(p.get(c, [None] * len(p["block"])))
    pq.write_table(pa.table(union), tdir / "swaps.parquet")

    market = sorted({V4_POOL_MANAGER if p["kind"] == "v4" else k
                     for k, p in entry["pools"].items()})
    cmd = [PY, str(ROOT / "scripts/attribute_trades.py"), "--swaps", str(tdir / "swaps.parquet"),
           "--transfers", str(tdir / "transfers.parquet"),
           "--out", str(tdir / "swaps_attributed.parquet")]
    for m in market:
        cmd += ["--pool", m]
    if subprocess.run(cmd, cwd=ROOT).returncode:
        note(f"{sym}: attribution FAILED"); return False
    note(f"{sym}: attributed DONE")

    # Per-pool quote prices, recorded beside the ledger.
    ds = DexScreener()
    quotes = {}
    for pair in ds.pairs_for_tokens([token]):
        key = pair["pairAddress"].lower()
        if key in entry["pools"]:
            pu, pn = float(pair.get("priceUsd") or 0), float(pair.get("priceNative") or 0)
            quotes[key] = {"quote_usd": (pu / pn) if pn else None,
                           "decimals": entry["pools"][key]["quote_decimals"],
                           "symbol": entry["pools"][key]["quote_symbol"],
                           "base_usd": pu}
    for k, p in entry["pools"].items():
        if k not in quotes or not quotes[k]["quote_usd"]:
            # Fallback for a quote DexScreener did not price: ETH/WETH at the
            # ETH price; anything else is left unpriced and says so.
            eth_like = p["quote"] in (ZERO, "0x0bd7d308f8e1639fab988df18a8011f41eacad73")
            quotes[k] = {"quote_usd": eth_usd if eth_like else None,
                         "decimals": p["quote_decimals"], "symbol": p["quote_symbol"]}
    (tdir / "quotes.json").write_text(json.dumps(
        {"priced_at": dt.datetime.utcnow().isoformat(timespec="seconds") + "Z",
         "eth_usd": eth_usd, "pools": quotes}, indent=1))
    cmd = [PY, str(ROOT / "scripts/build_ledger.py"), "--dir", str(tdir),
           "--eth-usd", str(eth_usd), "--quotes", str(tdir / "quotes.json"),
           "--base-decimals", str(entry.get("decimals", 18))]
    for m in market:
        cmd += ["--pool", m]
    if subprocess.run(cmd, cwd=ROOT).returncode:
        note(f"{sym}: ledger FAILED"); return False
    note(f"{sym}: ledger DONE")
    return True


def eth_price() -> float:
    ds = DexScreener()
    r = ds.get("/latest/dex/search?q=WETH%20USDG")
    best, px = 0, None
    for p in r.get("pairs") or []:
        if p.get("chainId") == "robinhood" and p["baseToken"]["symbol"] in ("WETH", "ETH"):
            liq = (p.get("liquidity") or {}).get("usd") or 0
            if liq > best:
                best, px = liq, float(p["priceUsd"])
    return px


def cmd_build(args) -> int:
    reg = load_reg()
    todo = [(t, e) for t, e in reg.items()
            if not args.only or e["symbol"].upper() in {x.upper() for x in args.only}]
    subprocess.run([PY, str(ROOT / "scripts/block_times.py"), "--verify", "5"], cwd=ROOT,
                   stdout=subprocess.DEVNULL)
    eth = eth_price()
    note(f"build starting for {', '.join(e['symbol'] for _, e in todo)} (ETH ${eth:,.2f})")
    ok = True
    for token, entry in todo:
        ok &= build_token(token, entry, eth)
        save_reg(reg)
    note("build finished" if ok else "build finished WITH FAILURES — rerun to resume")
    return 0 if ok else 1


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add"); a.add_argument("symbols", nargs="+")
    a.add_argument("--min-liq", type=float, default=20_000)
    a.add_argument("--skip-symbols", nargs="*", default=["USDC", "USDT", "USDG", "WETH", "ETH", "DAI"])
    b = sub.add_parser("build"); b.add_argument("--only", nargs="*")
    args = p.parse_args()
    return cmd_add(args) if args.cmd == "add" else cmd_build(args)


if __name__ == "__main__":
    raise SystemExit(main())

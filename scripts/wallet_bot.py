#!/usr/bin/env python3
"""Limit-buy bot for WALLET on Robinhood Chain.

Watches the WALLET/WETH Uniswap V3 pool every second. When the USD price sits
inside the buy band, it swaps ETH for WALLET through the Universal Router and
has the router deliver the WALLET straight to the forward (safe) address in the
same transaction, so the bot wallet never holds the tokens.

Config lives in bot/wallet_bot.json. The private key is read only from the
BOT_PRIVATE_KEY environment variable (a GitHub Actions secret) and is never
logged. With "live": false (the default) the bot simulates the swap with
eth_call and sends nothing.

One buy per wallet: after a buy the bot wallet has spent its ETH, so a repeat
is impossible without refunding it. The bot also exits right after a buy.

Selling is implemented behind "sell.enabled" (default off). It needs the
tokens in the bot wallet, and approves through Permit2 before swapping.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import httpx
from eth_account import Account

ROOT = Path(__file__).resolve().parent.parent
RPC = os.environ.get("RHC_RPC", "https://rpc.mainnet.chain.robinhood.com")
CHAIN_ID = 4663

WALLET = "0x0339f5459fc690ac85f1782e15782a151b4a9e1b"      # token0 of the pool, 18 dp
WETH = "0x0bd7d308f8e1639fab988df18a8011f41eacad73"        # token1, 18 dp
POOL = "0x9501a20bedb8bea0798fe5d4c411f5e270965d49"        # WALLET/WETH V3, fee 1%
POOL_FEE = 10_000
ETH_USD_POOL = "0x52e65b17fb6e5ba00ed806f37afcd2daa50271ca"  # WETH(18)/USDG(6) V3
ROUTER = "0x204faca1764b154221e35c0d20abb3c525710498"      # Universal Router
PERMIT2 = "0x000000000022d473030f116ddee9f6b43ac78ba3"

CMD_V3_SWAP_EXACT_IN = 0x00
CMD_WRAP_ETH = 0x0B
CMD_UNWRAP_WETH = 0x0C
ADDRESS_THIS = "0x0000000000000000000000000000000000000002"
Q96 = 2**96


def log(msg: str) -> None:
    print(time.strftime("%H:%M:%S", time.gmtime()), msg, flush=True)


class Chain:
    def __init__(self, url: str = RPC):
        self.http = httpx.Client(timeout=15)
        self.url = url
        self.id = 0

    def rpc(self, method: str, params: list):
        self.id += 1
        for attempt in range(5):
            try:
                r = self.http.post(self.url, json={"jsonrpc": "2.0", "id": self.id,
                                                   "method": method, "params": params})
                if r.status_code == 429:
                    time.sleep(2 + attempt * 2)
                    continue
                d = r.json()
                if "error" in d:
                    raise RuntimeError(d["error"])
                return d["result"]
            except (httpx.HTTPError, ValueError):
                time.sleep(1 + attempt)
        raise RuntimeError(f"{method} failed after retries")

    def call(self, to: str, data: str, frm: str | None = None, value: int = 0,
             overrides: dict | None = None) -> str:
        tx = {"to": to, "data": data}
        if frm:
            tx["from"] = frm
        if value:
            tx["value"] = hex(value)
        params = [tx, "latest"] + ([overrides] if overrides else [])
        return self.rpc("eth_call", params)

    def balance(self, addr: str) -> int:
        return int(self.rpc("eth_getBalance", [addr, "latest"]), 16)


def word(x: int | str | bool) -> str:
    if isinstance(x, bool):
        x = int(x)
    if isinstance(x, str):
        return x.lower().removeprefix("0x").rjust(64, "0")
    return format(x, "064x")


def enc_bytes(b: bytes) -> str:
    """ABI tail for a dynamic `bytes`: length + right-padded data."""
    h = b.hex()
    return word(len(b)) + h.ljust((len(h) + 63) // 64 * 64, "0")


def v3_swap_input(recipient: str, amount_in: int, min_out: int, path: bytes, payer_is_user: bool) -> bytes:
    # This router is Universal Router v2.1, whose V3 swap input carries a sixth
    # field after payerIsUser: a per-hop price-limit array, left empty here.
    # abi.encode(address, uint256, uint256, bytes path, bool, uint256[] limits)
    p = enc_bytes(path)
    limits_off = 6 * 32 + len(p) // 2
    return bytes.fromhex(word(recipient) + word(amount_in) + word(min_out) + word(6 * 32)
                         + word(payer_is_user) + word(limits_off) + p + word(0))


def execute_calldata(commands: bytes, inputs: list[bytes], deadline: int) -> str:
    # execute(bytes commands, bytes[] inputs, uint256 deadline)
    sel = "3593564c"
    head = word(3 * 32)
    cmd_tail = enc_bytes(commands)
    inputs_off = 3 * 32 + len(cmd_tail) // 2
    head += word(inputs_off) + word(deadline)
    # bytes[]: length, then offsets relative to the start of the offsets block
    arr = word(len(inputs))
    offs, tails, cur = "", "", 32 * len(inputs)
    for b in inputs:
        t = enc_bytes(b)
        offs += word(cur)
        tails += t
        cur += len(t) // 2
    return "0x" + sel + head + cmd_tail + arr + offs + tails


def path(a: str, fee: int, b: str) -> bytes:
    return bytes.fromhex(a[2:]) + fee.to_bytes(3, "big") + bytes.fromhex(b[2:])


def sqrt_price(c: Chain, pool: str) -> int:
    return int(c.call(pool, "0x3850c7bd")[2:66], 16)


def prices(c: Chain) -> tuple[float, float, float]:
    """(WALLET in ETH, ETH in USD, WALLET in USD)."""
    s = sqrt_price(c, POOL)
    wallet_eth = (s / Q96) ** 2                      # token1 per token0, both 18 dp
    e = sqrt_price(c, ETH_USD_POOL)
    eth_usd = (e / Q96) ** 2 * 10 ** (18 - 6)        # USDG(6) per WETH(18)
    return wallet_eth, eth_usd, wallet_eth * eth_usd


def build_buy(cfg: dict, amount_in: int, wallet_eth: float) -> str:
    expected = amount_in / wallet_eth * (1 - POOL_FEE / 1e6)
    min_out = int(expected * (1 - cfg["slippage_pct"] / 100))
    cmds = bytes([CMD_WRAP_ETH, CMD_V3_SWAP_EXACT_IN])
    inputs = [
        bytes.fromhex(word(ADDRESS_THIS) + word(amount_in)),
        v3_swap_input(cfg["forward_to"], amount_in, min_out, path(WETH, POOL_FEE, WALLET), False),
    ]
    return execute_calldata(cmds, inputs, int(time.time()) + 120), min_out


def erc20_balance(c: Chain, token: str, who: str) -> int:
    return int(c.call(token, "0x70a08231" + word(who)), 16)


def send(c: Chain, acct, to: str, data: str, value: int = 0) -> str:
    tx = {"from": acct.address, "to": to, "data": data, "value": hex(value)}
    gas = int(int(c.rpc("eth_estimateGas", [tx]), 16) * 1.3)
    base = int(c.rpc("eth_gasPrice", []), 16)
    signed = acct.sign_transaction({
        "chainId": CHAIN_ID, "nonce": int(c.rpc("eth_getTransactionCount", [acct.address, "pending"]), 16),
        "to": to, "data": data, "value": value, "gas": gas,
        "maxFeePerGas": base * 2, "maxPriorityFeePerGas": 0, "type": 2,
    })
    h = c.rpc("eth_sendRawTransaction", ["0x" + signed.raw_transaction.hex().removeprefix("0x")])
    for _ in range(60):
        rc = c.rpc("eth_getTransactionReceipt", [h])
        if rc:
            if rc["status"] != "0x1":
                raise RuntimeError(f"tx {h} reverted")
            return h
        time.sleep(1)
    raise RuntimeError(f"tx {h} not mined in 60s")


def sell(c: Chain, acct, cfg: dict, wallet_eth: float, live: bool) -> None:
    amt = erc20_balance(c, WALLET, acct.address)
    if amt == 0:
        log("sell: bot wallet holds no WALLET; nothing to sell")
        return
    min_eth = int(amt * wallet_eth * (1 - POOL_FEE / 1e6) * (1 - cfg["slippage_pct"] / 100))
    cmds = bytes([CMD_V3_SWAP_EXACT_IN, CMD_UNWRAP_WETH])
    inputs = [v3_swap_input(ADDRESS_THIS, amt, 0, path(WALLET, POOL_FEE, WETH), True),
              bytes.fromhex(word(cfg["forward_to"]) + word(min_eth))]
    data = execute_calldata(cmds, inputs, int(time.time()) + 120)
    if not live:
        log(f"DRY sell {amt / 1e18:,.0f} WALLET for >= {min_eth / 1e18:.5f} ETH (not sent)")
        return
    max160, far = 2**160 - 1, int(time.time()) + 3600
    if int(c.call(WALLET, "0xdd62ed3e" + word(acct.address) + word(PERMIT2)), 16) < amt:
        log("approve WALLET -> Permit2: " + send(c, acct, WALLET, "0x095ea7b3" + word(PERMIT2) + word(2**256 - 1)))
    log("Permit2 approve router: " + send(c, acct, PERMIT2, "0x87517c45" + word(WALLET) + word(ROUTER)
                                         + word(max160) + word(far)))
    log("SOLD: " + send(c, acct, ROUTER, data))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--config", default=str(ROOT / "bot/wallet_bot.json"))
    ap.add_argument("--minutes", type=float, default=None, help="stop after this long")
    ap.add_argument("--once", action="store_true", help="one price check and simulation, then exit")
    a = ap.parse_args()
    cfg = json.load(open(a.config))
    live = bool(cfg.get("live")) and not a.once
    minutes = a.minutes if a.minutes is not None else cfg.get("run_minutes", 345)
    c = Chain()

    key = os.environ.get("BOT_PRIVATE_KEY", "").strip()
    acct = Account.from_key(key) if key else None
    if live and not acct:
        log("live mode needs BOT_PRIVATE_KEY; refusing to run")
        return 2
    sender = acct.address if acct else "0x000000000000000000000000000000000000dEaD"
    lo, hi, usd = cfg["buy_min_usd"], cfg["buy_max_usd"], cfg["buy_usd"]
    log(f"{'LIVE' if live else 'DRY-RUN'}  band ${lo}-${hi}  size ${usd}  forward {cfg['forward_to']}"
        + (f"  bot {sender}" if acct else ""))

    if acct and not cfg.get("sell", {}).get("enabled"):
        bal = c.balance(acct.address)
        log(f"bot wallet balance {bal / 1e18:.6f} ETH")
        if live and bal <= int(cfg.get("gas_reserve_eth", 0.0003) * 1e18):
            log("no ETH to buy with (already bought, or not funded yet); exiting")
            return 0

    end, last_log = time.time() + minutes * 60, 0.0
    while time.time() < end:
        try:
            wallet_eth, eth_usd, px = prices(c)
        except Exception as e:  # keep polling through transient RPC errors
            log(f"price read failed: {e}")
            time.sleep(cfg.get("poll_seconds", 1))
            continue
        if time.time() - last_log >= cfg.get("log_every_seconds", 60) or a.once:
            log(f"WALLET ${px:.5f}  (ETH ${eth_usd:,.0f})")
            last_log = time.time()

        s = cfg.get("sell", {})
        if s.get("enabled") and (px >= (s.get("take_profit_usd") or 1e9) or px <= (s.get("stop_usd") or -1)):
            log(f"sell trigger at ${px:.5f}")
            sell(c, acct, cfg, wallet_eth, live)
            return 0

        in_band = lo <= px <= hi
        if in_band or a.once:
            amount_in = int(usd / eth_usd * 1e18)
            if acct:
                bal = c.balance(acct.address)
                reserve = int(cfg.get("gas_reserve_eth", 0.0003) * 1e18)
                amount_in = min(amount_in, bal - reserve)
                if amount_in <= 0:
                    log(f"bot wallet has {bal / 1e18:.6f} ETH, below the gas reserve; nothing to buy with")
                    return 0
            data, min_out = build_buy(cfg, amount_in, wallet_eth)
            # Simulate first, always. A state override gives the simulated sender the ETH.
            try:
                out = c.call(ROUTER, data, frm=sender, value=amount_in,
                             overrides={sender: {"balance": hex(amount_in + 10**18)}})
                sim = "simulation OK"
            except Exception as e:
                sim = f"simulation FAILED: {e}"
            log(f"{'IN BAND' if in_band else 'test'}: buy {amount_in / 1e18:.6f} ETH -> "
                f">= {min_out / 1e18:,.0f} WALLET to {cfg['forward_to']}; {sim}")
            if not in_band:
                return 0
            if live and sim == "simulation OK":
                h = send(c, acct, ROUTER, data, amount_in)
                got = erc20_balance(c, WALLET, cfg["forward_to"])
                log(f"BOUGHT: tx {h}; forward address now holds {got / 1e18:,.0f} WALLET")
                return 0
            if live:
                log("not sending because the simulation failed; will retry")
        time.sleep(cfg.get("poll_seconds", 1))
    log("run window over")
    return 0


if __name__ == "__main__":
    sys.exit(main())

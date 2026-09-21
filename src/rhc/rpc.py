"""Archive log scanning over the official RPC.

`rpc.mainnet.chain.robinhood.com` serves **unauthenticated archive access** back
to block 1 (2026-04-30), verified 2026-09-20. This is the population-scan data
source, and it replaces both Dune (paid since 2026-09-10) and SQD (which does
not carry this chain). publicnode's mirror is not equivalent — it rejects
archive queries without a personal token.

The node caps `eth_getLogs` at **10,000 results per call**, not by block range,
and separately times out on windows that are merely expensive. A fixed-span
scanner therefore either wastes calls on quiet periods or dies on busy ones.
`iter_logs` adapts its span against both failure modes, halving and retrying the
same window so nothing is skipped, and growing again when a window comes back
sparse.

**The node rate-limits under concurrent load, and it does so globally rather
than per-query.** Running a bulk scan alongside any other RPC work will starve
the second caller: during a 10,000-pool extraction even a bare `eth_blockNumber`
exhausted its retries. Treat bulk scans as exclusive — schedule them serially,
or raise `min_interval` on every client sharing the node.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Iterator

import httpx

RPC_URL = "https://rpc.mainnet.chain.robinhood.com"
MAX_LOGS_PER_CALL = 10_000

# Event topic0 hashes for the pool-creation and swap events this chain's DEXes emit.
TOPIC_V2_PAIR_CREATED = "0x0d3648bd0f6ba80134a33ba9275ac585d9d315f0ad8355cddefde31afa28d0e9"
TOPIC_V2_SWAP = "0xd78ad95fa46c994b6551d0da85fc275fe613ce37657fb8d5e3d130840159d822"
TOPIC_V3_POOL_CREATED = "0x783cca1c0412dd0d695e784568c96da2e9c22ff989357a2e8b1d9b2b4e6b7118"
TOPIC_V3_SWAP = "0xc42079f94a6350d7e6235f29174924f928cc2ac818eb64fed8004e115fbcca67"
TOPIC_TRANSFER = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
# V2 pairs emit Sync(uint112 reserve0, uint112 reserve1) after every swap, so
# a pool's exact reserves at any historical block are recoverable from logs.
# This is what makes a *historical* execution model possible despite no free
# source carrying historical liquidity composition (docs/03 §1.4).
TOPIC_V2_SYNC = "0x1c411e9a96e071241c2f21f7726b17ae89e3cab4c78be50e062b03a9fffbbad1"


class RpcError(RuntimeError):
    """The node returned an error, carrying its message for span-adaptation checks."""


def _needs_smaller_span(message: str) -> bool:
    """Whether an error means 'this window was too big' rather than a real failure.

    Two distinct node responses mean the same thing operationally. The result
    cap is reported as an explicit limit breach, but a window that is merely
    *expensive* — many blocks in a busy region — comes back as a timeout
    instead, with no mention of limits. Both are fixed by narrowing the window
    and retrying, and treating only the first as retryable aborts long scans
    partway through, which is exactly what happened on the first full census.
    """
    lowered = message.lower()
    return (
        "exceeds limit" in lowered
        or "more than" in lowered
        or "too many" in lowered
        or "timed out" in lowered
        or "timeout" in lowered
    )


@dataclass
class Rpc:
    """Minimal JSON-RPC client with adaptive log-range scanning."""

    url: str = RPC_URL
    min_interval: float = 0.15
    max_retries: int = 4
    timeout: float = 60.0
    _client: httpx.Client = field(init=False, repr=False)
    _last_request: float = field(default=0.0, init=False, repr=False)
    _request_id: int = field(default=0, init=False, repr=False)

    def __post_init__(self) -> None:
        self._client = httpx.Client(
            timeout=self.timeout,
            headers={"Content-Type": "application/json", "User-Agent": "rhc-research/0.1"},
        )

    def __enter__(self) -> Rpc:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    def call(self, method: str, params: list[Any]) -> Any:
        """One JSON-RPC call, retrying transport and 5xx failures.

        Raises:
            RpcError: carrying the node's own message, so callers can inspect it
                (``_needs_smaller_span`` depends on this).
        """
        last_error: Exception | None = None
        for attempt in range(self.max_retries):
            elapsed = time.monotonic() - self._last_request
            if elapsed < self.min_interval:
                time.sleep(self.min_interval - elapsed)
            self._last_request = time.monotonic()
            self._request_id += 1
            try:
                response = self._client.post(
                    self.url,
                    json={
                        "jsonrpc": "2.0",
                        "method": method,
                        "params": params,
                        "id": self._request_id,
                    },
                )
            except httpx.HTTPError as exc:
                last_error = exc
                time.sleep(2**attempt)
                continue

            if response.status_code >= 500 or response.status_code == 429:
                last_error = RpcError(f"HTTP {response.status_code}")
                time.sleep(2**attempt)
                continue

            payload = response.json()
            if "error" in payload:
                raise RpcError(str(payload["error"].get("message", payload["error"])))
            return payload.get("result")
        raise RpcError(f"Exhausted retries for {method}") from last_error

    def block_number(self) -> int:
        return int(self.call("eth_blockNumber", []), 16)

    def block_timestamp(self, block: int) -> int:
        result = self.call("eth_getBlockByNumber", [hex(block), False])
        if not result:
            raise RpcError(f"No block {block}")
        return int(result["timestamp"], 16)

    def get_logs(
        self,
        *,
        from_block: int,
        to_block: int,
        topics: list[Any] | None = None,
        address: str | list[str] | None = None,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {
            "fromBlock": hex(from_block),
            "toBlock": hex(to_block),
        }
        if topics:
            params["topics"] = topics
        if address:
            params["address"] = address
        return self.call("eth_getLogs", [params]) or []

    def iter_logs(
        self,
        *,
        from_block: int,
        to_block: int,
        topics: list[Any] | None = None,
        address: str | list[str] | None = None,
        initial_span: int = 100_000,
        min_span: int = 128,
        on_progress: Any = None,
    ) -> Iterator[dict[str, Any]]:
        """Yield every matching log across a range, adapting span to the result cap.

        Halves the span on an overflow and retries the same window, so no logs
        are skipped; grows it by 50% when a window returns comfortably under the
        cap, so quiet regions are not scanned in needlessly small steps.

        Args:
            on_progress: optional callable(current_block, span, yielded_so_far).
        """
        span = initial_span
        cursor = from_block
        yielded = 0
        while cursor <= to_block:
            end = min(cursor + span - 1, to_block)
            try:
                logs = self.get_logs(
                    from_block=cursor, to_block=end, topics=topics, address=address
                )
            except RpcError as exc:
                if not _needs_smaller_span(str(exc)):
                    raise
                if span <= min_span:
                    raise RpcError(
                        f"Cannot serve blocks {cursor}-{end} even at minimum span "
                        f"({min_span}); node said: {exc}"
                    ) from exc
                span = max(min_span, span // 2)
                continue  # retry the same cursor with a tighter window

            yield from logs
            yielded += len(logs)
            if on_progress:
                on_progress(end, span, yielded)

            # Grow back toward the cap when the window came back sparse.
            if len(logs) < MAX_LOGS_PER_CALL // 2:
                span = int(span * 1.5)
            cursor = end + 1

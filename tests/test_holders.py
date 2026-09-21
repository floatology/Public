"""Holder distribution — catalogue section 2, previously untested.

This code has never run against the chain: it needs a Transfer replay, and the
RPC rate-limits globally so it has been queued behind every bulk scan. It does
not need the chain to be tested, though, and an untested replay is a poor thing
to trust with a whole metric domain.

Two things it must get right, both of which were flagged as live problems when
the catalogue was written:

**The pool is not a holder.** $WALLET's largest holder is its own liquidity
pool at 6.82%, and the second is the burn address at 5.48%. A concentration
metric that counts them measures the pool, not the crowd.

**Mints and burns are transfers.** They appear as transfers from and to the zero
address, so they must flow through the replay and be excluded only from the
final tally. Excluding the zero address from the replay itself would leave
every minted token unaccounted for.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rhc.features import holder_features, replay_balances

ZERO = "0x" + "0" * 40
DEAD = "0x000000000000000000000000000000000000dead"


def A(name: str) -> str:
    """A canonical 20-byte address from a readable name.

    Real addresses are 40 hex characters and the topic decoder takes the last
    20 bytes of a 32-byte word, so short stand-ins like A("a") decode to
    something else entirely -- which is how the first version of this file
    failed.
    """
    body = name.lower().encode().hex()
    return "0x" + body.rjust(40, "0")[-40:]


def topic(address: str) -> str:
    return "0x" + "0" * 24 + address[2:].lower()


def transfer(block: int, sender: str, recipient: str, value: int) -> dict:
    return {
        "blockNumber": hex(block),
        "topics": ["0xddf252ad", topic(sender), topic(recipient)],
        "data": "0x" + f"{value:064x}",
    }


def test_mint_then_distribute():
    logs = [transfer(1, ZERO, A("deployer"), 1000 * 10**18)]
    for i in range(4):
        logs.append(transfer(10 + i, A("deployer"), A(f"holder{i}"), 100 * 10**18))
    balances, applied = replay_balances(logs)
    assert applied == 5
    # The zero address is excluded from the tally, not from the replay.
    assert ZERO not in balances
    assert balances[A("deployer")] == 600 * 10**18
    assert balances[A("holder0")] == 100 * 10**18
    assert sum(balances.values()) == 1000 * 10**18


def test_burn_removes_supply():
    logs = [transfer(1, ZERO, A("a"), 100), transfer(2, A("a"), DEAD, 40)]
    balances, _ = replay_balances(logs)
    assert DEAD not in balances
    assert balances[A("a")] == 60
    assert sum(balances.values()) == 60


def test_pool_and_burn_are_excludable():
    logs = [transfer(1, ZERO, A("pool"), 700), transfer(2, ZERO, A("a"), 200),
            transfer(3, ZERO, A("b"), 100)]
    unfiltered, _ = replay_balances(logs)
    assert holder_features(unfiltered).top1_share == 0.7  # the pool dominates

    filtered, _ = replay_balances(logs, exclude={A("pool").upper()})
    features = holder_features(filtered)
    assert A("pool") not in filtered
    # Now the largest real holder is 0xa at two thirds of circulating supply.
    assert abs(features.top1_share - 2 / 3) < 1e-9, features.top1_share
    assert features.holder_count == 2


def test_up_to_block_is_point_in_time():
    logs = [transfer(1, ZERO, A("a"), 100), transfer(50, A("a"), A("b"), 100)]
    early, applied = replay_balances(logs, up_to_block=10)
    assert applied == 1 and early[A("a")] == 100 and A("b") not in early
    late, _ = replay_balances(logs, up_to_block=100)
    assert A("a") not in late and late[A("b")] == 100


def test_concentration_metrics_move_in_the_right_direction():
    even = {A(str(i)): 100 for i in range(10)}
    skewed = {A("whale"): 910, **{A(str(i)): 10 for i in range(9)}}

    flat, sharp = holder_features(even), holder_features(skewed)
    assert flat.top1_share < sharp.top1_share
    assert flat.hhi < sharp.hhi
    assert flat.gini < sharp.gini
    assert flat.entropy > sharp.entropy
    # Ten equal holders is maximum entropy for ten holders.
    assert abs(flat.normalised_entropy - 1.0) < 1e-9
    assert sharp.normalised_entropy < 0.5


def test_dust_holders_are_counted_separately():
    # One real holder and 500 airdropped dust addresses. Holder count alone
    # would read as adoption.
    balances = {A("real"): 10**18, **{A(f"dust{i}"): 1 for i in range(500)}}
    features = holder_features(balances)
    assert features.holder_count == 501
    assert features.holders_with_dust_only == 500
    assert features.top1_share > 0.99


def test_deployer_and_cohort_shares():
    balances = {A("deployer"): 400, A("e1"): 300, A("e2"): 200, A("late"): 100}
    features = holder_features(balances, deployer=A("deployer").upper(),
                               early_buyers={A("e1").upper(), A("e2")})
    assert features.deployer_share == 0.4
    assert features.early_buyer_share == 0.5


def test_malformed_logs_are_skipped_not_fatal():
    logs = [
        {"blockNumber": "0x1", "topics": ["0xddf252ad"], "data": "0x01"},  # ERC-721
        transfer(2, ZERO, A("a"), 100),
        {"blockNumber": "0x3", "topics": ["0xddf252ad", topic(A("a")), topic(A("b"))],
         "data": "0x"},  # no value word
        transfer(4, ZERO, A("b"), 0),  # zero-value transfer
    ]
    balances, applied = replay_balances(logs)
    assert applied == 1 and balances == {A("a"): 100}


def test_empty_is_safe():
    balances, applied = replay_balances([])
    assert balances == {} and applied == 0
    features = holder_features({})
    assert features.holder_count == 0 and features.hhi is None


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"  pass  {name}")
            except AssertionError as exc:
                failures += 1
                print(f"  FAIL  {name}: {exc}")
    print(f"\n{failures} failures")
    raise SystemExit(1 if failures else 0)

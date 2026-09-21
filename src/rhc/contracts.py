"""Contract-level structural checks — catalogue section 6.

These are **filters, not predictors**. The open-source scanner the original
document cited is explicit about its own class of tool: it "filters traps, it
does not pick winners." Treat a failed check as a reason to exclude, never a
clean check as a reason to buy.

Everything here reads the explorer's verified source and ABI rather than
decompiling bytecode, which means an **unverified contract yields almost no
information**. That absence is itself recorded: `is_verified=False` is a
meaningful state, not a missing measurement, and conflating the two would let
unverified contracts look clean.

Privileged functions are detected from the ABI rather than by string-matching
source text. A function named `mint` in a comment, a variable, or a dead branch
matches a text search; only an ABI entry means the function is actually callable.

**Proxies are followed to their implementation.** A proxy's own ABI is nearly
empty — the callable functions live in the contract it delegates to. Reading the
proxy address alone returned zero functions and therefore zero privileged
capabilities for two tokens that certainly have them, which is a *falsely clean*
result and the most dangerous kind of error a risk filter can make.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, asdict
from typing import Any

from .chain import Blockscout, BlockscoutError

# Function names granting the deployer ongoing power over holders. Matched
# against ABI entry names, case-insensitively, as whole names or prefixes.
PRIVILEGED_PATTERNS = {
    "mint": re.compile(r"^(_)?mint", re.IGNORECASE),
    "burn_from": re.compile(r"^burnfrom", re.IGNORECASE),
    "pause": re.compile(r"^(_)?(pause|unpause|setpaused|settradingenabled)", re.IGNORECASE),
    "blacklist": re.compile(r"(blacklist|blocklist|denylist|setbot|setbots)", re.IGNORECASE),
    "fee_control": re.compile(r"(setfee|settax|updatefee|updatetax|setbuytax|setselltax)",
                              re.IGNORECASE),
    "max_limits": re.compile(r"(setmaxtx|setmaxwallet|setmaxbuy|updatemax)", re.IGNORECASE),
    "withdraw_all": re.compile(r"(withdrawall|rescue|sweep|claimstuck|emergencywithdraw)",
                               re.IGNORECASE),
    "ownership": re.compile(r"(transferownership|renounceownership)", re.IGNORECASE),
}

# An owner that is the zero or dead address means ownership was renounced.
RENOUNCED_OWNERS = {
    "0x0000000000000000000000000000000000000000",
    "0x000000000000000000000000000000000000dead",
}


@dataclass
class ContractRisk:
    """Structural properties of a token contract."""

    address: str
    is_verified: bool = False
    is_proxy: bool = False
    compiler_version: str | None = None
    abi_function_count: int = 0
    implementation: str | None = None

    # Privileged capability flags, keyed by PRIVILEGED_PATTERNS.
    has_mint: bool = False
    has_burn_from: bool = False
    has_pause: bool = False
    has_blacklist: bool = False
    has_fee_control: bool = False
    has_max_limits: bool = False
    has_withdraw_all: bool = False
    has_ownership_controls: bool = False

    privileged_count: int = 0
    # True only when a privileged function exists *and* ownership is live, i.e.
    # somebody can still call it.
    live_privilege_risk: bool = False
    ownership_renounced: bool | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _abi_function_names(abi: list[dict]) -> list[str]:
    return [
        entry.get("name", "")
        for entry in abi or []
        if entry.get("type") == "function" and entry.get("name")
    ]


def inspect(client: Blockscout, address: str, *, owner: str | None = None) -> ContractRisk:
    """Read a contract's structural risk properties from the explorer.

    Args:
        owner: the current owner if already known. When omitted, ownership is
            reported as unknown rather than guessed — reading it needs an
            `eth_call` against the contract's `owner()` and this module
            deliberately does not touch the RPC, which rate-limits globally.
    """
    risk = ContractRisk(address=address)
    try:
        contract = client.get(f"/api/v2/smart-contracts/{address}")
    except BlockscoutError as exc:
        risk.error = str(exc)[:200]
        return risk

    risk.is_verified = bool(contract.get("is_verified"))
    risk.compiler_version = contract.get("compiler_version")
    implementations = contract.get("implementations") or []
    risk.is_proxy = bool(contract.get("proxy_type")) or bool(implementations)

    # Follow a proxy to its implementation; the proxy's own ABI is near-empty
    # and reading it would report a contract with every privilege as clean.
    if risk.is_proxy and implementations:
        target = implementations[0].get("address") or implementations[0].get("address_hash")
        if target:
            risk.implementation = target
            try:
                impl = client.get(f"/api/v2/smart-contracts/{target}")
            except BlockscoutError as exc:
                risk.error = f"proxy implementation unreadable: {str(exc)[:120]}"
                return risk
            if impl.get("abi"):
                contract = impl
                risk.is_verified = bool(impl.get("is_verified"))
        else:
            risk.error = "proxy with no resolvable implementation"
            return risk

    if not risk.is_verified:
        # Unverified is a state, not a gap. Leaving the capability flags False
        # here would make an unverified contract read as clean.
        risk.error = "unverified: capabilities unknown"
        return risk

    names = _abi_function_names(contract.get("abi") or [])
    risk.abi_function_count = len(names)
    if not names:
        # No callable functions is not a clean bill of health, it is an
        # unreadable one.
        risk.error = "no ABI functions resolved: capabilities unknown"
        return risk
    found: dict[str, bool] = {}
    for key, pattern in PRIVILEGED_PATTERNS.items():
        found[key] = any(pattern.search(name) for name in names)

    risk.has_mint = found["mint"]
    risk.has_burn_from = found["burn_from"]
    risk.has_pause = found["pause"]
    risk.has_blacklist = found["blacklist"]
    risk.has_fee_control = found["fee_control"]
    risk.has_max_limits = found["max_limits"]
    risk.has_withdraw_all = found["withdraw_all"]
    risk.has_ownership_controls = found["ownership"]

    # Ownership controls are not themselves a risk; they are the mechanism by
    # which the others get renounced.
    risk.privileged_count = sum(
        1 for key, present in found.items() if present and key != "ownership"
    )

    if owner is not None:
        risk.ownership_renounced = owner.lower() in RENOUNCED_OWNERS
        risk.live_privilege_risk = risk.privileged_count > 0 and not risk.ownership_renounced
    elif risk.privileged_count > 0:
        # Privileges exist but callability is unknown, so this stays False and
        # the ambiguity is visible through ownership_renounced being None.
        risk.live_privilege_risk = False
    return risk


def creator_of(client: Blockscout, address: str) -> str | None:
    """The address that deployed a contract, for deployer-age checks.

    This is a separate call on purpose. `ContractRisk` used to carry a `creator`
    field that `inspect` never populated, so it read as None for every token
    while the information was sitting one endpoint away — an absent value that
    looks like "unknown" when it is really "never asked". The field is gone;
    callers that want a deployer call this.
    """
    try:
        return client.get(f"/api/v2/addresses/{address}").get("creator_address_hash")
    except BlockscoutError:
        return None

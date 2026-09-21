"""Social metrics from sources that are actually free.

The original plan specified LunarCrush's free tier for social volume and Galaxy
Score. **That tier is now market-data only** — social, creator and AI endpoints
moved behind a paid plan, and Santiment did the same. X killed free API access
in 2023. So the social half of the catalogue is mostly paid now.

**Telegram is the exception and it is a real one.** A public channel's preview
page (`t.me/s/<channel>`) renders member count, post text and per-post view
counts as plain HTML, with no API key, no account and no rate-limit tier. That
yields the two social metrics that matter most — audience size and *engagement
per post* — plus a growth derivative once sampled over time.

Engagement per post is the more interesting of the two. A follower count is a
stock and trivially bought; views per post are a flow and much harder to fake
convincingly, because purchased followers do not read.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field, asdict
from typing import Any

import httpx

TELEGRAM_PREVIEW = "https://t.me/s/{channel}"

_BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
)

# The /s/ preview page renders counters as paired spans:
#   <span class="counter_value">9.51M</span> <span class="counter_type">subscribers</span>
# The plain channel page uses a different layout, which is why this reads
# the preview URL rather than t.me/<channel> directly.
_MEMBERS = re.compile(
    r'<span class="counter_value">([^<]+)</span>\s*'
    r'<span class="counter_type">(?:subscribers|members)</span>',
    re.IGNORECASE,
)
_VIEWS = re.compile(r'<span class="tgme_widget_message_views">([\d.,KkMm\s]+)</span>')
_CHANNEL_IN_URL = re.compile(r"(?:t\.me|telegram\.me)/(?:s/)?(@?[A-Za-z0-9_]{4,32})")


class SocialError(RuntimeError):
    """The source could not be read."""


def parse_count(text: str) -> int | None:
    """Parse Telegram's count formats: '1 234', '12.3K', '1.2M'."""
    cleaned = text.strip().replace(" ", "").replace(" ", "").replace(" ", "")
    cleaned = cleaned.replace(",", "")
    if not cleaned:
        return None
    multiplier = 1
    if cleaned[-1] in "Kk":
        multiplier, cleaned = 1_000, cleaned[:-1]
    elif cleaned[-1] in "Mm":
        multiplier, cleaned = 1_000_000, cleaned[:-1]
    try:
        return int(float(cleaned) * multiplier)
    except ValueError:
        return None


def channel_from_url(url: str) -> str | None:
    """Extract a channel handle from any Telegram URL form."""
    match = _CHANNEL_IN_URL.search(url or "")
    if not match:
        return None
    handle = match.group(1).lstrip("@")
    # These path segments are Telegram's own, not channels.
    if handle.lower() in {"joinchat", "share", "proxy", "socks", "addstickers"}:
        return None
    return handle


@dataclass
class TelegramMetrics:
    """What a public channel preview page exposes."""

    channel: str
    member_count: int | None = None
    posts_sampled: int = 0
    views_median: float | None = None
    views_mean: float | None = None
    views_max: int | None = None
    views_per_member: float | None = None
    reachable: bool = False
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Telegram:
    """Reader for public Telegram channel previews. No key, no account."""

    min_interval: float = 1.0
    max_retries: int = 3
    timeout: float = 20.0
    _client: httpx.Client = field(init=False, repr=False)
    _last_request: float = field(default=0.0, init=False, repr=False)

    def __post_init__(self) -> None:
        self._client = httpx.Client(
            timeout=self.timeout,
            follow_redirects=True,
            headers={"User-Agent": _BROWSER_UA, "Accept-Language": "en"},
        )

    def __enter__(self) -> Telegram:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    def fetch(self, channel: str) -> TelegramMetrics:
        """Read a channel's member count and recent post view counts.

        Never raises for an unreadable channel — a missing or private channel is
        itself information, and a scan over many tokens must not abort because
        one link is dead.
        """
        handle = channel.lstrip("@")
        metrics = TelegramMetrics(channel=handle)
        last_error: Exception | None = None

        for attempt in range(self.max_retries):
            elapsed = time.monotonic() - self._last_request
            if elapsed < self.min_interval:
                time.sleep(self.min_interval - elapsed)
            self._last_request = time.monotonic()
            try:
                response = self._client.get(TELEGRAM_PREVIEW.format(channel=handle))
            except httpx.HTTPError as exc:
                last_error = exc
                time.sleep(2**attempt)
                continue
            if response.status_code == 404:
                metrics.error = "channel not found"
                return metrics
            if response.status_code >= 500 or response.status_code == 429:
                last_error = SocialError(f"HTTP {response.status_code}")
                time.sleep(2 ** (attempt + 1))
                continue
            if response.status_code >= 400:
                metrics.error = f"HTTP {response.status_code}"
                return metrics

            html = response.text
            # A non-existent channel still returns 200 with a generic page, so
            # reachability is judged by finding channel markup, not by status.
            metrics.reachable = "tgme_channel_info" in html or "tgme_widget_message" in html
            if not metrics.reachable:
                metrics.error = "no channel content"
                return metrics
            member_match = _MEMBERS.search(html)
            if member_match:
                metrics.member_count = parse_count(member_match.group(1))

            views = [
                v for v in (parse_count(m) for m in _VIEWS.findall(html)) if v is not None
            ]
            if views:
                views.sort()
                metrics.posts_sampled = len(views)
                metrics.views_median = float(views[len(views) // 2])
                metrics.views_mean = sum(views) / len(views)
                metrics.views_max = views[-1]
                if metrics.member_count:
                    # Engagement rate. A bought audience inflates the
                    # denominator without moving the numerator, so this falls
                    # where a follower count alone would not.
                    metrics.views_per_member = metrics.views_median / metrics.member_count
            return metrics

        metrics.error = f"unreachable: {last_error}"
        return metrics

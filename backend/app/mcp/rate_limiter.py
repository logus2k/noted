"""In-memory token bucket rate limiter for MCP tool calls.

Tiered by tool category:
  - Read tier:     30/min, burst 10
  - Write tier:    10/min, burst 3
  - Workflow tier:  3/min, burst 1

Rate limiting applies strictly at the MCP client-to-server boundary.
Internal execution triggered by tool calls is exempt.
"""

import time
import logging

logger = logging.getLogger(__name__)


class TokenBucket:
    """Simple token bucket for rate limiting."""

    def __init__(self, rate_per_minute: float, burst: int):
        self.rate_per_second = rate_per_minute / 60.0
        self.burst = burst
        self.tokens = float(burst)
        self.last_refill = time.monotonic()

    def _refill(self):
        now = time.monotonic()
        elapsed = now - self.last_refill
        self.tokens = min(self.burst, self.tokens + elapsed * self.rate_per_second)
        self.last_refill = now

    def consume(self) -> bool:
        """Try to consume one token. Returns True if allowed, False if rate limited."""
        self._refill()
        if self.tokens >= 1.0:
            self.tokens -= 1.0
            return True
        return False

    def retry_after(self) -> float:
        """Seconds until the next token is available."""
        self._refill()
        if self.tokens >= 1.0:
            return 0.0
        deficit = 1.0 - self.tokens
        return deficit / self.rate_per_second


class RateLimiter:
    """Per-session, tiered rate limiter for MCP tool calls."""

    # Tier configuration: (rate_per_minute, burst)
    TIERS = {
        "read": (30, 10),
        "write": (10, 3),
        "workflow": (3, 1),
    }

    WORKFLOW_TOOLS = {"run_workflow"}

    def __init__(self):
        # session_id -> {tier_name -> TokenBucket}
        self._buckets: dict[str, dict[str, TokenBucket]] = {}

    def _get_buckets(self, session_id: str) -> dict[str, TokenBucket]:
        if session_id not in self._buckets:
            self._buckets[session_id] = {
                tier: TokenBucket(rate, burst)
                for tier, (rate, burst) in self.TIERS.items()
            }
        return self._buckets[session_id]

    def _classify(self, tool_name: str, is_write: bool) -> str:
        if tool_name in self.WORKFLOW_TOOLS:
            return "workflow"
        if is_write:
            return "write"
        return "read"

    def check(self, session_id: str, tool_name: str, is_write: bool) -> tuple[bool, float]:
        """Check if a tool call is within rate limits.

        Args:
            session_id: Client session identifier
            tool_name: Name of the tool being called
            is_write: Whether the tool is write-tier

        Returns:
            (allowed, retry_after_seconds)
            If allowed is True, retry_after is 0.
            If allowed is False, retry_after is the wait time in seconds.
        """
        tier = self._classify(tool_name, is_write)
        buckets = self._get_buckets(session_id)
        bucket = buckets[tier]

        if bucket.consume():
            return True, 0.0

        retry = bucket.retry_after()
        logger.info(
            "Rate limited: session=%s tool=%s tier=%s retry_after=%.1fs",
            session_id[:8], tool_name, tier, retry,
        )
        return False, retry

    def cleanup_session(self, session_id: str):
        """Remove rate limit state for a disconnected session."""
        self._buckets.pop(session_id, None)

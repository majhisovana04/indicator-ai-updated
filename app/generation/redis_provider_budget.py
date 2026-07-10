# app/generation/redis_provider_budget.py
"""
Redis-backed per-provider daily budget tracker.
Drop-in replacement for the in-memory ProviderDailyBudget.

How it works:
    - Key format: "provider_budget:{provider_name}:{YYYY-MM-DD}"
    - The date in the key acts as automatic daily reset — a new day = new key
    - Key TTL is set to expire at midnight, so old keys auto-clean up
    - All operations (INCR, GET) are atomic — safe across multiple workers

Graceful fallback:
    - If Redis is down, always returns can_call=True and remaining=daily_limit
    - Fail open: better to risk a small quota overrun than to block all LLM calls
"""

import time
from datetime import datetime, timedelta
from app.redis_client import get_redis


class RedisProviderBudget:
    """
    Drop-in replacement for ProviderDailyBudget.
    Same interface: can_call(), record_call(), exhaust(), remaining().
    Shared across all server workers via Redis.
    """

    KEY_PREFIX = "provider_budget"

    def __init__(self, provider_name: str, daily_limit: int):
        self.provider_name = provider_name
        self.daily_limit = daily_limit

    def _key(self) -> str:
        """Today's key, e.g. 'provider_budget:Gemini:2024-01-15'"""
        today = datetime.now().date().isoformat()
        return f"{self.KEY_PREFIX}:{self.provider_name}:{today}"

    def _seconds_until_midnight(self) -> int:
        """Seconds remaining until midnight today — used as Redis TTL."""
        now = datetime.now()
        midnight = datetime.combine(now.date() + timedelta(days=1), datetime.min.time())
        return int((midnight - now).total_seconds()) + 60  # +60s buffer past midnight

    def can_call(self) -> bool:
        """True if this provider has quota remaining today."""
        r = get_redis()
        if r is None:
            return True   # fail open

        try:
            value = r.get(self._key())
            used = int(value) if value is not None else 0
            return used < self.daily_limit
        except Exception as e:
            print(f"[RedisProviderBudget] {self.provider_name}: Redis error in can_call — {e}")
            return True   # fail open

    def record_call(self):
        """Increment this provider's call count for today atomically."""
        r = get_redis()
        if r is None:
            return

        try:
            key = self._key()
            new_count = r.incr(key)
            # Set TTL only on first call of the day (when count goes 0→1)
            if new_count == 1:
                r.expire(key, self._seconds_until_midnight())
        except Exception as e:
            print(f"[RedisProviderBudget] {self.provider_name}: Redis error in record_call — {e}")

    def exhaust(self):
        """Force-exhaust today's budget (called after a 429 quota error)."""
        r = get_redis()
        if r is None:
            return

        try:
            key = self._key()
            r.set(key, self.daily_limit, ex=self._seconds_until_midnight())
        except Exception as e:
            print(f"[RedisProviderBudget] {self.provider_name}: Redis error in exhaust — {e}")

    def remaining(self) -> int:
        """How many calls are left today for this provider."""
        r = get_redis()
        if r is None:
            return self.daily_limit

        try:
            value = r.get(self._key())
            used = int(value) if value is not None else 0
            return max(0, self.daily_limit - used)
        except Exception as e:
            print(f"[RedisProviderBudget] {self.provider_name}: Redis error in remaining — {e}")
            return self.daily_limit

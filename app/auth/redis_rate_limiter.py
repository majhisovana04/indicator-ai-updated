

# app/auth/redis_rate_limiter.py
"""
Redis-backed per-user rate limiter using a sliding window algorithm.

How it works:
    - Each user gets a Redis Sorted Set (ZSET) key: "rl:{user_id}"
    - Each request adds an entry with the current timestamp as score
    - On each check: remove entries older than the window, count remaining
    - If count >= max_requests → deny
    - Key expires automatically after the window ends (no manual cleanup)

Graceful fallback:
    - If Redis is down, requests are ALLOWED (fail open)
    - Fail open is correct here: it's better to let a burst through
      than to lock out all users because Redis had a hiccup
    - A warning is logged so you know degraded mode is active
"""

import time
import uuid
from app.redis_client import get_redis


class RedisRateLimiter:
    """
    Drop-in replacement for the in-memory RateLimiter.
    Same interface: is_allowed(user_id) -> bool
    Works correctly across multiple server workers.
    """

    KEY_PREFIX = "rl"

    def __init__(self, max_requests: int = 10, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds

    def is_allowed(self, user_id: str) -> bool:
        """
        Returns True if the user is within their rate limit, False if exceeded.
        Falls back to True (allow) if Redis is unavailable.
        """
        r = get_redis()

        # Graceful fallback — Redis is down, fail open
        if r is None:
            print(f"[RedisRateLimiter] Redis unavailable — allowing user {user_id} (degraded mode)")
            return True

        key = f"{self.KEY_PREFIX}:{user_id}"
        now = time.time()
        window_start = now - self.window_seconds

        try:
            # Step 1: Remove all requests older than the sliding window
            r.zremrangebyscore(key, "-inf", window_start)

            # Step 2: Count how many requests are left in the window
            current_count = r.zcard(key)

            # Step 3: Check limit BEFORE adding current request
            if current_count >= self.max_requests:
                return False  # limit exceeded

            # Step 4: Add this current request
            member = f"{now}:{uuid.uuid4()}"   # unique member per request
            r.zadd(key, {member: now})

            # Step 5: Set the key to expire after the window (auto-cleanup)
            r.expire(key, self.window_seconds)

            return True

        except Exception as e:
            print(f"[RedisRateLimiter] Redis error — allowing user {user_id}: {e}")
            return True   # fail open


    def get_remaining(self, user_id: str) -> int:
        """
        Returns how many requests the user has left in their current window.
        Returns max_requests if Redis is down.
        """
        r = get_redis()
        if r is None:
            return self.max_requests

        key = f"{self.KEY_PREFIX}:{user_id}"
        now = time.time()
        window_start = now - self.window_seconds

        try:
            r.zremrangebyscore(key, "-inf", window_start)
            used = r.zcard(key)
            return max(0, self.max_requests - used)
        except Exception:
            return self.max_requests

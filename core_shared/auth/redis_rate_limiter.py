import time
import uuid
from core_shared.redis_client import get_redis


class RedisRateLimiter:
    KEY_PREFIX = "rl"

    def __init__(self, max_requests: int = 10, window_seconds: int = 60, redis_getter=None):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.redis_getter = redis_getter or get_redis

    def is_allowed(self, user_id: str) -> bool:
        r = self.redis_getter()
        if r is None:
            print(f"[RedisRateLimiter] Redis unavailable — allowing user {user_id} (degraded mode)")
            return True

        key = f"{self.KEY_PREFIX}:{user_id}"
        now = time.time()
        window_start = now - self.window_seconds

        try:
            # Round trip 1: clean expired entries + get current count, PIPELINED (1 HTTP call instead of 2)
            pipe = r.pipeline()
            pipe.zremrangebyscore(key, "-inf", window_start)
            pipe.zcard(key)
            results = pipe.exec()
            current_count = results[1]  # zcard's result — 2nd command in the pipeline

            if current_count >= self.max_requests:
                return False  # limit exceeded — no write needed, saves a round trip entirely

            # Round trip 2: add this request + refresh expiry, PIPELINED (1 HTTP call instead of 2)
            member = f"{now}:{uuid.uuid4()}"
            pipe2 = r.pipeline()
            pipe2.zadd(key, {member: now})
            pipe2.expire(key, self.window_seconds)
            pipe2.exec()

            return True

        except Exception as e:
            print(f"[RedisRateLimiter] Redis error — allowing user {user_id}: {e}")
            return True

    def get_remaining(self, user_id: str) -> int:
        r = self.redis_getter()
        if r is None:
            return self.max_requests

        key = f"{self.KEY_PREFIX}:{user_id}"
        now = time.time()
        window_start = now - self.window_seconds

        try:
            pipe = r.pipeline()
            pipe.zremrangebyscore(key, "-inf", window_start)
            pipe.zcard(key)
            results = pipe.exec()
            used = results[1]
            return max(0, self.max_requests - used)
        except Exception:
            return self.max_requests
import time
from datetime import datetime, timedelta
from app.redis_client import get_redis


class RedisProviderBudget:
    KEY_PREFIX = "provider_budget"

    def __init__(self, provider_name: str, daily_limit: int):
        self.provider_name = provider_name
        self.daily_limit = daily_limit

    def _key(self) -> str:
        today = datetime.now().date().isoformat()
        return f"{self.KEY_PREFIX}:{self.provider_name}:{today}"

    def _seconds_until_midnight(self) -> int:
        now = datetime.now()
        midnight = datetime.combine(now.date() + timedelta(days=1), datetime.min.time())
        return int((midnight - now).total_seconds()) + 60

    def can_call(self) -> bool:
        r = get_redis()
        if r is None:
            return True
        try:
            value = r.get(self._key())
            used = int(value) if value is not None else 0
            return used < self.daily_limit
        except Exception as e:
            print(f"[RedisProviderBudget] {self.provider_name}: Redis error in can_call — {e}")
            return True

    def record_call(self):
        """
        PIPELINED: combines the increment + expiry-refresh into ONE
        HTTP round trip instead of two. Safe to refresh expiry every
        call — it always targets the same real midnight instant.
        """
        r = get_redis()
        if r is None:
            return
        try:
            key = self._key()
            pipe = r.pipeline()
            pipe.incr(key)
            pipe.expire(key, self._seconds_until_midnight())
            pipe.exec()
        except Exception as e:
            print(f"[RedisProviderBudget] {self.provider_name}: Redis error in record_call — {e}")

    def exhaust(self):
        r = get_redis()
        if r is None:
            return
        try:
            key = self._key()
            r.set(key, self.daily_limit, ex=self._seconds_until_midnight())
        except Exception as e:
            print(f"[RedisProviderBudget] {self.provider_name}: Redis error in exhaust — {e}")

    def remaining(self) -> int:
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
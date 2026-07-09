import time
from collections import defaultdict


class RateLimiter:
    def __init__(self, max_requests: int = 10, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.user_requests = defaultdict(list)

    def is_allowed(self, user_id: str) -> bool:
        now = time.time()
        recent = [t for t in self.user_requests[user_id] if now - t < self.window_seconds]
        self.user_requests[user_id] = recent

        if len(recent) >= self.max_requests:
            return False

        self.user_requests[user_id].append(now)
        return True